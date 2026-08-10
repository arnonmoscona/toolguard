"""
Unit tests for TOO-8 Phase 4: log streams, conflict logging, and provenance.

Covers:
- Four separate per-concern log streams (error/warning/conflict/resolution),
  each writing to its OWN file.
- Conflict logging: an allow-over-deny override IS recorded to the conflict log
  citing both provenances; no conflict entry when there is no override; hard_deny
  denials are NOT conflicts (they go to the resolution log).
- Provenance threaded into resolution reasons.
- Change-detecting config-discovery diagnostic in the resolution log (TOO-19).
- M1: the both-.toml-and-.json warning is emitted exactly once, to the warning
  stream.

These tests use unittest (NOT pytest) with Given/When/Then docstrings, per the
project's testing convention.
"""

import json
import unittest
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    RuntimeVerdict,
)
from toolguard.config_divergence import DivergenceCheckResult
from toolguard.config_types import provenance_for_pattern
from toolguard.error_log import log_conflict, log_error, log_warning
from toolguard.log_writer import (
    _DISCOVERY_LOG_FILENAME,
    _DISCOVERY_TAIL_READ_BYTES,
    _parse_discovery_line,
    log_discovery,
)
from toolguard.permission_resolution import resolve_command_permission


def _bash_layer(allow, deny, specificity, path):
    """Build a toolguard_hook ConfigLayer with Bash permissions at a specificity."""
    content = {
        "permissions": {
            "allow": [f"Bash({p})" for p in allow],
            "deny": [f"Bash({p})" for p in deny],
        }
    }
    prov = Provenance("project", "toolguard_hook", "toml", Path(path), specificity)
    return ConfigLayer(provenance=prov, content=MappingProxyType(content))


class TestLogStreamSeparation(unittest.TestCase):
    """Each concern writes to its OWN per-date file."""

    def test_error_warning_conflict_are_separate_files(self):
        """
        Given a log directory
        When an error, a warning, and a conflict are each logged
        Then three distinct files exist (error/warning/conflict), each holding
             only its own entry
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_error("boom", "fix the error", log_dir)
            log_warning("careful", "fix the warning", log_dir)
            log_conflict("overlap", "resolve the conflict", log_dir)

            error_files = list(log_dir.glob("toolguard-error-*.md"))
            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            conflict_files = list(log_dir.glob("toolguard-conflict-*.md"))
            self.assertEqual(len(error_files), 1)
            self.assertEqual(len(warning_files), 1)
            self.assertEqual(len(conflict_files), 1)

            error_text = error_files[0].read_text()
            warning_text = warning_files[0].read_text()
            conflict_text = conflict_files[0].read_text()

            self.assertIn("boom", error_text)
            self.assertNotIn("careful", error_text)
            self.assertNotIn("overlap", error_text)

            self.assertIn("careful", warning_text)
            self.assertNotIn("boom", warning_text)

            self.assertIn("overlap", conflict_text)
            self.assertIn("CONFLICT", conflict_text)

    def test_error_log_holds_only_errors(self):
        """
        Given a log directory
        When only warnings and conflicts are logged (no errors)
        Then no toolguard-error-*.md file is created
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_warning("w", "s", log_dir)
            log_conflict("c", "s", log_dir)
            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])


class TestTakeoverNoticeNotPersisted(unittest.TestCase):
    """The takeover notice is a stderr echo only, never a persisted log."""

    def test_takeover_notice_writes_no_log_file(self):
        """
        Given a fresh log directory
        When issue_takeover_warning runs
        Then no toolguard log stream file is created, and the notice is
             echoed to stderr -- issue_takeover_warning no longer touches
             the claim store at all (TOO-45 punch-list #01)
        """
        from toolguard.session_warnings import issue_takeover_warning

        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp) / "logs"

            with patch("sys.stderr", new_callable=StringIO) as err:
                issue_takeover_warning(to_stdout=True)

            self.assertEqual(
                list(log_dir.glob("toolguard-*.md")) if log_dir.exists() else [], []
            )
            self.assertIn("Takeover mode is active", err.getvalue())


class TestProvenanceInReasons(unittest.TestCase):
    """The engine's resolve_command_permission appends matched-rule provenance to the reason."""

    def test_allow_reason_carries_provenance_and_stays_compatible(self):
        """
        Given a single project level allowing 'git *'
        When 'git status' resolves
        Then the reason still contains 'matches allow pattern: git *' AND a
             bracketed provenance suffix naming the source file/level, and
             reason.split(': ', 1) still yields the pattern (+ suffix)
        """
        config = Configuration(
            layers=(_bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),)
        )
        resolved = resolve_command_permission(config, "Bash", "git status")
        self.assertIsInstance(resolved, RuntimeVerdict)
        self.assertEqual(resolved.decision, "allow")
        # Backward-compatible substring still present.
        self.assertIn("matches allow pattern: git *", resolved.reason)
        # Provenance suffix appended.
        self.assertIn("[project: /proj/.claude/toolguard_hook.toml]", resolved.reason)
        # Existing split-based extraction still recovers the pattern (+ suffix).
        extracted = resolved.reason.split(": ", 1)[1]
        self.assertTrue(extracted.startswith("git *"))
        self.assertIsNotNone(resolved.provenance)

    def test_default_no_match_fallback_has_no_provenance(self):
        """
        Given a level that matches nothing
        When a non-matching command resolves via the default no_match_fallback
        Then the result ('ask', TOO-15's default) carries no provenance and the
            expected reason text
        """
        config = Configuration(
            layers=(_bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),)
        )
        resolved = resolve_command_permission(config, "Bash", "rm -rf /")
        self.assertEqual(resolved.decision, "ask")
        self.assertIsNone(resolved.provenance)
        self.assertEqual(
            resolved.reason,
            "Command does not match any allow patterns; awaiting a decision "
            "(no_match_fallback=ask)",
        )


class TestConflictDetection(unittest.TestCase):
    """Allow-over-deny override detection in the engine's resolve_command_permission."""

    def test_allow_over_deny_records_override_with_both_provenances(self):
        """
        Given a more-specific level allowing 'git *' and a less-specific level
            denying 'git *'
        When 'git push' resolves
        Then the decision is the more-specific allow AND an override is reported
             citing both sides' patterns and provenance
        """
        config = Configuration(
            layers=(
                _bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),
                _bash_layer([], ["git *"], 1, "/home/.claude/toolguard_hook.toml"),
            )
        )
        resolved = resolve_command_permission(config, "Bash", "git push")
        self.assertEqual(resolved.decision, "allow")
        # RuntimeVerdict.overrides (TOO-45 R1c) is a list of (identifier,
        # ConflictOverride) pairs -- at this internal per-level layer the
        # identifier is always None (no sub_command/target in scope here;
        # see RuntimeVerdict's docstring's "overrides" reconciliation).
        self.assertEqual(len(resolved.overrides), 1)
        identifier, override = resolved.overrides[0]
        self.assertIsNone(identifier)
        self.assertEqual(override.winning_pattern, "git *")
        self.assertEqual(override.overridden_pattern, "git *")
        self.assertEqual(override.winning_provenance.specificity, 0)
        self.assertEqual(override.overridden_provenance.specificity, 1)

    def test_no_override_when_no_less_specific_deny(self):
        """
        Given a single more-specific level allowing 'git *' and no deny anywhere
        When 'git push' resolves
        Then the decision is allow and NO override is reported
        """
        config = Configuration(
            layers=(_bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),)
        )
        resolved = resolve_command_permission(config, "Bash", "git push")
        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(resolved.overrides, [])

    def test_deny_decision_reports_no_override(self):
        """
        Given a more-specific level that denies the command
        When the command resolves
        Then the decision is deny with NO override (overrides are allow-only)
        """
        config = Configuration(
            layers=(
                _bash_layer([], ["rm *"], 0, "/proj/.claude/toolguard_hook.toml"),
                _bash_layer(["rm *"], [], 1, "/home/.claude/toolguard_hook.toml"),
            )
        )
        resolved = resolve_command_permission(config, "Bash", "rm -rf /")
        self.assertEqual(resolved.decision, "deny")
        self.assertEqual(resolved.overrides, [])


class TestProvenanceHelpers(unittest.TestCase):
    """Branch coverage for the small provenance helpers."""

    def test_append_provenance_none_returns_reason_unchanged(self):
        """
        Given a None provenance
        When _append_provenance is called
        Then the reason is returned unchanged (no bracketed suffix)
        """
        from toolguard.permission_resolution import _append_provenance

        self.assertEqual(_append_provenance("some reason", None), "some reason")

    def test_provenance_for_pattern_returns_none_on_miss(self):
        """
        Given layers that do not contain the queried pattern
        When provenance_for_pattern is called
        Then None is returned
        """
        layer = _bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml")

        # The ToolPatternLayer view is what provenance_for_pattern consumes.
        cfg = Configuration(layers=(layer,))
        tool_layers = cfg.permission_layers("Bash")
        self.assertIsNone(provenance_for_pattern(tool_layers, "no-such", "allow"))

    def test_override_skips_level_without_deny_then_finds_deeper_deny(self):
        """
        Given a most-specific allow, a middle level with NO deny, and a least-
            specific level denying the command
        When the command resolves
        Then the override is detected against the deepest deny (the empty middle
             level is skipped)
        """
        config = Configuration(
            layers=(
                _bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),
                _bash_layer(["ls *"], [], 1, "/mid/.claude/toolguard_hook.toml"),
                _bash_layer([], ["git *"], 2, "/home/.claude/toolguard_hook.toml"),
            )
        )
        resolved = resolve_command_permission(config, "Bash", "git push")
        self.assertEqual(resolved.decision, "allow")
        self.assertEqual(len(resolved.overrides), 1)
        self.assertEqual(resolved.overrides[0][1].overridden_provenance.specificity, 2)


class TestDiscoveryDiagnostic(unittest.TestCase):
    """
    The change-detecting discovery diagnostic (TOO-19).

    toolguard is a fresh process on every PreToolUse invocation, so there is
    no in-process "once per session" to rely on. log_discovery itself is the
    guard: it writes (to both the plain-text discovery log and the main
    resolution log) only when the discovered levels differ from the last
    recorded entry for the given project root; otherwise it writes nothing to
    either file.

    TOO-19 code review M3: the discovery log is plain text, one record per
    line (``timestamp\\tproject_root\\tlevels``), not JSON -- the only thing
    ever read back is the single most recent matching line, so JSON's
    structure bought nothing. These tests were rewritten from JSON-record
    assertions to plain-text ones for that reason; the scenarios they cover
    (write-on-change, no-write-on-no-change, multi-project isolation,
    tolerance of a torn line) are unchanged.
    """

    _LEVELS_A = [
        "project: /proj/.claude/toolguard_hook.toml",
        "user: /home/.claude/toolguard_hook.toml",
    ]
    _LEVELS_B = [
        "project: /proj/.claude/toolguard_hook.toml",
        "user: /home/.claude/toolguard_hook.toml",
        "org: /org/.claude/toolguard_hook.toml",
    ]

    def _discovery_log_path(self, log_dir):
        """Return the path to the plain-text discovery log under log_dir."""
        return log_dir / _DISCOVERY_LOG_FILENAME

    def _discovery_lines(self, log_dir):
        """Return the discovery log's lines (split, no trailing newline)."""
        path = self._discovery_log_path(log_dir)
        if not path.exists():
            return []
        return path.read_text(encoding="utf-8").splitlines()

    def _resolution_log_path(self, log_dir):
        """Return today's main resolution-log path under log_dir."""
        from datetime import datetime

        return log_dir / f"toolguard-{datetime.now().strftime('%Y-%m-%d')}.md"

    def test_first_call_writes_both_files(self):
        """
        Given no prior discovery record for this project root
        When log_discovery runs for the first time
        Then it appends a discovery-log line AND writes the main-log entry
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")

            lines = self._discovery_lines(log_dir)
            self.assertEqual(len(lines), 1)
            timestamp, project_root, levels = _parse_discovery_line(lines[0])
            self.assertEqual(project_root, "/proj")
            self.assertEqual(levels, self._LEVELS_A)

            resolution_text = self._resolution_log_path(log_dir).read_text()
            self.assertIn("discovered 2 config levels", resolution_text)
            self.assertIn("project: /proj/.claude/toolguard_hook.toml", resolution_text)

    def test_unchanged_second_call_writes_nothing(self):
        """
        Given a first call already recorded a set of levels for this project root
        When a second call runs immediately with the SAME levels
        Then neither the discovery log nor the main-log file changes at all (byte-identical)
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")

            discovery_path = self._discovery_log_path(log_dir)
            resolution_path = self._resolution_log_path(log_dir)
            discovery_before = discovery_path.read_bytes()
            resolution_before = resolution_path.read_bytes()

            log_discovery(self._LEVELS_A, log_dir, "/proj")

            self.assertEqual(discovery_path.read_bytes(), discovery_before)
            self.assertEqual(resolution_path.read_bytes(), resolution_before)

    def test_different_levels_writes_both_again(self):
        """
        Given a first call recorded levels A for this project root
        When a second call runs with DIFFERENT levels B
        Then both files gain a new entry reflecting the change
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            log_discovery(self._LEVELS_B, log_dir, "/proj")

            lines = self._discovery_lines(log_dir)
            self.assertEqual(len(lines), 2)
            _timestamp, _root, second_levels = _parse_discovery_line(lines[1])
            self.assertEqual(second_levels, self._LEVELS_B)

            resolution_text = self._resolution_log_path(log_dir).read_text()
            self.assertEqual(resolution_text.count("**Discovery**"), 2)
            self.assertIn("discovered 3 config levels", resolution_text)

    def test_reverting_to_a_previously_seen_value_still_logs(self):
        """
        Given levels went A -> B (two prior discovery-log records for this project root)
        When a third call reverts to A, which differs only from the LAST entry (B)
        Then it logs again -- comparison is against the last entry, not the whole history
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            log_discovery(self._LEVELS_B, log_dir, "/proj")
            log_discovery(self._LEVELS_A, log_dir, "/proj")

            lines = self._discovery_lines(log_dir)
            self.assertEqual(len(lines), 3)
            _timestamp, _root, last_levels = _parse_discovery_line(lines[-1])
            self.assertEqual(last_levels, self._LEVELS_A)

            resolution_text = self._resolution_log_path(log_dir).read_text()
            self.assertEqual(resolution_text.count("**Discovery**"), 3)

    def test_two_project_roots_sharing_a_log_dir_do_not_flap(self):
        """
        Given a TOOLGUARD_LOG_DIR shared by two different project roots
        When calls alternate A, B, A, B (each unchanged for ITS OWN root)
        Then every call logs (comparison is per-root, so B's entry never
             suppresses A's next unchanged call) but a repeat for the SAME
             root (A, A back to back) logs nothing on the repeat
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj-a")  # 1: A first ever
            log_discovery(self._LEVELS_A, log_dir, "/proj-b")  # 2: B first ever
            log_discovery(self._LEVELS_A, log_dir, "/proj-a")  # 3: A unchanged for A,
            # but the most recent discovery-log record overall is B's -- must
            # still compare against A's own last entry (1), not B's (2), so
            # this must NOT log.
            log_discovery(self._LEVELS_A, log_dir, "/proj-b")  # 4: same for B

            lines = self._discovery_lines(log_dir)
            self.assertEqual(len(lines), 2)  # only calls 1 and 2 logged

            # Now change A's levels: must log even though B's record is the
            # most recent line in the file.
            log_discovery(self._LEVELS_B, log_dir, "/proj-a")
            lines = self._discovery_lines(log_dir)
            self.assertEqual(len(lines), 3)
            _timestamp, last_root, _levels = _parse_discovery_line(lines[-1])
            self.assertEqual(last_root, "/proj-a")

            # A repeat call for A with its now-current levels logs nothing.
            discovery_before = self._discovery_log_path(log_dir).read_bytes()
            log_discovery(self._LEVELS_B, log_dir, "/proj-a")
            self.assertEqual(
                self._discovery_log_path(log_dir).read_bytes(), discovery_before
            )

    def test_corrupt_final_line_is_tolerated_as_no_prior_entry(self):
        """
        Given a discovery log whose final line is torn (missing its second
            tab, as if a concurrent write were interrupted mid-record)
        When log_discovery runs for that project root
        Then it does not crash, treats it as having no prior entry, and logs
             a new (duplicate-looking) record rather than raising
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            discovery_path = self._discovery_log_path(log_dir)
            discovery_path.write_text("2026-01-01T00:00:00\t/proj")  # torn: no 2nd tab

            log_discovery(self._LEVELS_A, log_dir, "/proj")

            lines = self._discovery_lines(log_dir)
            # The torn line plus the freshly appended, valid one.
            self.assertEqual(len(lines), 2)
            _timestamp, _root, levels = _parse_discovery_line(lines[-1])
            self.assertEqual(levels, self._LEVELS_A)

    def test_main_log_entry_format_unchanged(self):
        """
        Given a discovery call that does write (first-ever for its root)
        When the main resolution log entry is inspected
        Then it matches the exact pre-existing format that log_harvest.py
             relies on to skip Discovery sections (no Status field)
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            text = self._resolution_log_path(log_dir).read_text()
            expected = (
                "- **Discovery**: discovered 2 config levels: "
                "project: /proj/.claude/toolguard_hook.toml, "
                "user: /home/.claude/toolguard_hook.toml\n"
            )
            self.assertIn(expected, text)
            # Not routed to other streams.
            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])

    def test_oversized_file_no_longer_degrades_to_permanent_append_mode(self):
        """
        Given a discovery log padded well past the OLD 1 MB read-size cap
            (TOO-19 code review M3: exceeding that cap used to degrade to
            "no prior entry", making EVERY subsequent call append -- a
            self-accelerating bug)
        When log_discovery runs again with the SAME levels as the last real
            record
        Then it still finds that record (via the bounded tail read) and logs
             NOTHING -- proving there is no size cap that can trip this bug
             any more
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            discovery_path = self._discovery_log_path(log_dir)

            # Pad the file well past the old 1 MB cap with harmless filler
            # records for OTHER project roots FIRST, so the real "/proj"
            # entry (written after the padding) is the LAST line -- still
            # within the bounded tail read even though the file overall is
            # large.
            filler_line = "2026-01-01T00:00:00\t/other-project\t" + ("x" * 200)
            padding = (filler_line + "\n") * 6000  # ~1.3 MB of filler
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(discovery_path, "a", encoding="utf-8") as f:
                f.write(padding)

            log_discovery(self._LEVELS_A, log_dir, "/proj")
            self.assertGreater(discovery_path.stat().st_size, 1_000_000)

            before = discovery_path.read_bytes()
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            after = discovery_path.read_bytes()

            self.assertEqual(
                before,
                after,
                "an oversized file must not make log_discovery think there "
                "is no prior entry and append again",
            )

    def test_entry_outside_the_tail_window_degrades_to_no_prior_entry(self):
        """
        Given a discovery log whose real "/proj" record has been pushed
            outside the bounded tail read window by enough filler records
            for a DIFFERENT project root
        When log_discovery runs again with the SAME levels as that
            now-out-of-window record
        Then it degrades to "no prior entry" and logs again -- a redundant
             line, not a wrong verdict, which is the documented trade-off of
             bounding the read instead of the file
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            discovery_path = self._discovery_log_path(log_dir)

            filler_line = "2026-01-01T00:00:00\t/other-project\t" + ("x" * 200)
            # Enough filler to push the real record well outside the tail
            # window (_DISCOVERY_TAIL_READ_BYTES).
            needed_lines = (_DISCOVERY_TAIL_READ_BYTES // len(filler_line)) + 50
            padding = (filler_line + "\n") * needed_lines
            with open(discovery_path, "a", encoding="utf-8") as f:
                f.write(padding)

            before_lines = len(self._discovery_lines(log_dir))
            log_discovery(self._LEVELS_A, log_dir, "/proj")
            after_lines = len(self._discovery_lines(log_dir))

            self.assertEqual(after_lines, before_lines + 1)


class TestHookConflictLogging(unittest.TestCase):
    """End-to-end: the hook logs conflicts and hard_deny correctly."""

    def _config_with_levels(self, layers):
        return Configuration(layers=tuple(layers))

    def test_hook_logs_conflict_on_allow_over_deny(self):
        """
        Given a project level allowing 'git *' and a user level denying 'git *'
        When the hook resolves a 'git push' Bash command
        Then it allows the command AND writes an entry to the conflict log citing
             both provenances, and nothing to the resolution-as-conflict
        """
        from toolguard import hook as hook_mod

        config = self._config_with_levels(
            [
                _bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),
                _bash_layer([], ["git *"], 1, "/home/.claude/toolguard_hook.toml"),
            ]
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git push"},
            "hook_event_name": "PreToolUse",
        }
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            env_config = {
                "log_dir": log_dir,
                "logging_enabled": True,
                "create_log_dir": True,
                "extended_syntax": True,
            }
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch("toolguard.hook._run_startup_validation"):
                                with patch(
                                    "toolguard.hook.check_and_warn_divergence",
                                    return_value=DivergenceCheckResult(
                                        divergent_patterns=[]
                                    ),
                                ):
                                    try:
                                        hook_mod.main()
                                    except SystemExit:
                                        pass
            output = json.loads(out.getvalue())
            self.assertEqual(
                output["hookSpecificOutput"]["permissionDecision"], "allow"
            )
            conflict_files = list(log_dir.glob("toolguard-conflict-*.md"))
            self.assertEqual(len(conflict_files), 1)
            conflict_text = conflict_files[0].read_text()
            self.assertIn("allow-over-deny override", conflict_text)
            self.assertIn("/proj/.claude/toolguard_hook.toml", conflict_text)
            self.assertIn("/home/.claude/toolguard_hook.toml", conflict_text)

    def test_hook_does_not_log_conflict_without_override(self):
        """
        Given a single project level allowing 'git *' (no deny anywhere)
        When the hook resolves 'git status'
        Then it allows the command and writes NO conflict-log file
        """
        from toolguard import hook as hook_mod

        config = self._config_with_levels(
            [_bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml")]
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "git status"},
            "hook_event_name": "PreToolUse",
        }
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            env_config = {
                "log_dir": log_dir,
                "logging_enabled": True,
                "create_log_dir": True,
                "extended_syntax": True,
            }
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch("toolguard.hook._run_startup_validation"):
                                with patch(
                                    "toolguard.hook.check_and_warn_divergence",
                                    return_value=DivergenceCheckResult(
                                        divergent_patterns=[]
                                    ),
                                ):
                                    try:
                                        hook_mod.main()
                                    except SystemExit:
                                        pass
            output = json.loads(out.getvalue())
            self.assertEqual(
                output["hookSpecificOutput"]["permissionDecision"], "allow"
            )
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])

    def test_hard_deny_goes_to_resolution_not_conflict(self):
        """
        Given a project-level hard_deny of 'rm *' and an allow of '*'
        When the hook resolves 'rm -rf /'
        Then the command is denied, NO conflict file is written, and the denial
             is recorded in the resolution log (toolguard-YYYY-MM-DD.md)
        """
        from toolguard import hook as hook_mod

        content = {
            "permissions": {"allow": ["Bash(*)"], "deny": []},
            "hard_deny": {"deny": ["Bash(rm *)"], "allow": []},
        }
        prov = Provenance(
            "project",
            "toolguard_hook",
            "toml",
            Path("/proj/.claude/toolguard_hook.toml"),
            0,
        )
        config = Configuration(
            layers=(ConfigLayer(provenance=prov, content=MappingProxyType(content)),)
        )
        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "rm -rf /"},
            "hook_event_name": "PreToolUse",
        }
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            env_config = {
                "log_dir": log_dir,
                "logging_enabled": True,
                "create_log_dir": True,
                "extended_syntax": True,
            }
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch("toolguard.hook._run_startup_validation"):
                                with patch(
                                    "toolguard.hook.check_and_warn_divergence",
                                    return_value=DivergenceCheckResult(
                                        divergent_patterns=[]
                                    ),
                                ):
                                    try:
                                        hook_mod.main()
                                    except SystemExit:
                                        pass
            output = json.loads(out.getvalue())
            self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
            self.assertIn(
                "hard_deny", output["hookSpecificOutput"]["permissionDecisionReason"]
            )
            # No conflict file.
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])
            # Resolution log holds the refused entry.
            resolution_files = [
                p for p in log_dir.glob("toolguard-2*.md") if p.name.count("-") == 3
            ]
            self.assertEqual(len(resolution_files), 1)
            self.assertIn("REFUSED", resolution_files[0].read_text())


class TestM1SingleSourceWarning(ConfigIsolationMixin, unittest.TestCase):
    """M1: the both-formats warning is emitted exactly once, to the warning stream."""

    def test_both_formats_warning_once_to_warning_stream(self):
        """
        Given a project .claude dir holding BOTH toolguard_hook.toml and .json
        When the hook runs startup validation
        Then exactly ONE both-formats warning is written, to the warning stream,
             and nothing to the error/conflict streams
        """
        from toolguard import hook as hook_mod
        from toolguard.config import load_configuration

        _home, proj_root = self.isolate_config_environment()
        claude = proj_root / ".claude"
        claude.mkdir()
        (claude / "toolguard_hook.toml").write_text(
            'governed_tools = ["Bash"]\n[permissions]\nallow=["Bash(git *)"]\n'
        )
        (claude / "toolguard_hook.json").write_text(
            '{"permissions": {"allow": ["Bash(ls *)"]}}'
        )

        log_dir = proj_root / "logs"
        env_config = {"log_dir": log_dir}
        config = load_configuration(proj_root, ignore_env_override=True)

        hook_mod._run_startup_validation(env_config, str(proj_root), config)

        warning_files = list(log_dir.glob("toolguard-warning-*.md"))
        self.assertEqual(len(warning_files), 1)
        text = warning_files[0].read_text()
        occurrences = text.count("Both toolguard_hook.toml and toolguard_hook.json")
        self.assertEqual(occurrences, 1)
        # Not routed to error/conflict streams.
        self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])
        self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])


class TestDivergenceWarningLogging(ConfigIsolationMixin, unittest.TestCase):
    """
    TOO-45 R5d: config_divergence.check_and_warn_divergence no longer writes
    to the structured error log itself -- a config-layer module must not
    depend on error_log, a runtime-layer module. It returns the warning text
    (DivergenceCheckResult) and toolguard.hook does the logging. This is the
    end-to-end regression test for that hand-off actually happening: every
    OTHER test touching this path mocks check_and_warn_divergence entirely,
    so none of them would notice hook.py forgetting to log the result.
    """

    def test_divergence_check_writes_warning_log_via_hook(self):
        """
        Given a project whose settings.local.json allows a Bash pattern absent
            from its toolguard config
        When toolguard.hook._run_divergence_check runs for that project
        Then a toolguard-warning-*.md file is written containing the divergent
             pattern -- proving hook.py, not config_divergence.py, performs
             the structured log write
        """
        from toolguard import hook as hook_mod
        from toolguard import once_per_store
        from toolguard.config import load_configuration

        _home, proj_root = self.isolate_config_environment()
        store_patcher = patch.object(
            once_per_store, "_STORE_PATH", _home / ".toolguard" / "once_per.db"
        )
        store_patcher.start()
        self.addCleanup(store_patcher.stop)
        claude = proj_root / ".claude"
        claude.mkdir()
        (claude / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
        )
        (claude / "toolguard_hook.json").write_text(
            json.dumps({"permissions": {"allow": []}})
        )

        log_dir = proj_root / "logs"
        env_config = {"log_dir": log_dir}
        config = load_configuration(proj_root, ignore_env_override=True)
        takeover_dict = hook_mod._resolve_takeover_mode(config, env_config)

        hook_mod._run_divergence_check(config, env_config, takeover_dict)

        warning_files = list(log_dir.glob("toolguard-warning-*.md"))
        self.assertEqual(len(warning_files), 1)
        self.assertIn("Bash(git push:*)", warning_files[0].read_text())

    def test_failed_migration_is_not_retried_same_day(self):
        """
        Given a project with a divergent Bash pattern, auto_migrate enabled,
            and migrate() rigged to always fail
        When toolguard.hook._run_divergence_check runs TWICE for that
            project (simulating two separate tool-call invocations the same
            day)
        Then migrate() is attempted exactly ONCE -- the divergence_warning
             claim the first call takes gates every later same-day call
             before it ever reaches run_auto_migration, so a failed
             migration is retried the next day, not the same day (TOO-45
             D4). A test that called run_auto_migration directly instead of
             going through the hook would not exercise that gate at all --
             which is exactly what hid this defect the first time.
        """
        from toolguard import hook as hook_mod
        from toolguard import once_per_store
        from toolguard.config import load_configuration

        _home, proj_root = self.isolate_config_environment()
        store_patcher = patch.object(
            once_per_store, "_STORE_PATH", _home / ".toolguard" / "once_per.db"
        )
        store_patcher.start()
        self.addCleanup(store_patcher.stop)
        claude = proj_root / ".claude"
        claude.mkdir()
        (claude / "settings.local.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
        )
        (claude / "toolguard_hook.json").write_text(
            json.dumps(
                {
                    "permissions": {"allow": []},
                    "config_sync": {"auto_migrate": True},
                }
            )
        )

        log_dir = proj_root / "logs"
        env_config = {"log_dir": log_dir}
        config = load_configuration(proj_root, ignore_env_override=True)
        takeover_dict = hook_mod._resolve_takeover_mode(config, env_config)

        with patch("toolguard.auto_migrate.migrate", return_value=1) as mock_migrate:
            hook_mod._run_divergence_check(config, env_config, takeover_dict)
            hook_mod._run_divergence_check(config, env_config, takeover_dict)

        self.assertEqual(mock_migrate.call_count, 1)


class TestValidationIssueRoutingByLevel(unittest.TestCase):
    """P1: startup validation routes each Issue to the stream matching its level."""

    class _FakeConfig:
        """Minimal stand-in exposing only validation_issues() for routing tests."""

        def __init__(self, issues):
            self._issues = issues
            self.project_root = None

        def validation_issues(self):
            """Return the pre-canned Issue tuple for this fake config."""
            return tuple(self._issues)

    def test_error_level_issue_routed_to_error_stream(self):
        """
        Given a validation Issue whose level is 'error'
        When the hook runs startup validation
        Then the message lands in the ERROR stream and not the warning/conflict streams
        """
        from toolguard import hook as hook_mod
        from toolguard.config import Issue

        with TemporaryDirectory() as proj:
            log_dir = Path(proj) / "logs"
            env_config = {"log_dir": log_dir}
            issue = Issue(
                level="error", message="bad config", corrective_steps="fix it"
            )
            config = self._FakeConfig([issue])

            hook_mod._run_startup_validation(env_config, proj, config)

            error_files = list(log_dir.glob("toolguard-error-*.md"))
            self.assertEqual(len(error_files), 1)
            self.assertIn("bad config", error_files[0].read_text())
            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])

    def test_warning_level_issue_routed_to_warning_stream(self):
        """
        Given a validation Issue whose level is 'warning'
        When the hook runs startup validation
        Then the message lands in the WARNING stream and not the error/conflict streams
        """
        from toolguard import hook as hook_mod
        from toolguard.config import Issue

        with TemporaryDirectory() as proj:
            log_dir = Path(proj) / "logs"
            env_config = {"log_dir": log_dir}
            issue = Issue(
                level="warning", message="heads up", corrective_steps="review it"
            )
            config = self._FakeConfig([issue])

            hook_mod._run_startup_validation(env_config, proj, config)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertIn("heads up", warning_files[0].read_text())
            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])


if __name__ == "__main__":
    unittest.main()
