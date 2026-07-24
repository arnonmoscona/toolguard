"""
Unit tests for TOO-8 Phase 4: log streams, conflict logging, and provenance.

Covers:
- Four separate per-concern log streams (error/warning/conflict/resolution),
  each writing to its OWN file.
- Conflict logging: an allow-over-deny override IS recorded to the conflict log
  citing both provenances; no conflict entry when there is no override; hard_deny
  denials are NOT conflicts (they go to the resolution log).
- Provenance threaded into resolution reasons.
- Once-per-session config-discovery diagnostic in the resolution log.
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
    ResolvedDecision,
)
from toolguard.error_log import log_conflict, log_error, log_warning
from toolguard.log_writer import log_discovery
from toolguard.permissions import decide_command_at_level_detailed


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


def _detailed_decider(command):
    """Return a per-level detailed decider bound to a command (for Bash)."""

    def _decide(allow, deny, ask=()):
        return decide_command_at_level_detailed(
            command, list(allow), list(deny), ask_patterns=list(ask)
        )

    return _decide


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
    """The takeover notice is stderr + marker only, never a persisted log."""

    def test_takeover_notice_writes_no_log_file(self):
        """
        Given a fresh log directory
        When issue_takeover_warning runs
        Then no toolguard log stream file is created (only a marker), and the
             notice is echoed to stderr
        """
        from toolguard.session_warnings import issue_takeover_warning

        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            with patch("sys.stderr", new_callable=StringIO) as err:
                issue_takeover_warning(log_dir, to_stdout=True)

            self.assertEqual(list(log_dir.glob("toolguard-*.md")), [])
            # Marker present (once-per-session guard) and stderr echoed.
            self.assertTrue(list(log_dir.glob(".toolguard-warned-*")))
            self.assertIn("Takeover mode is active", err.getvalue())


class TestProvenanceInReasons(unittest.TestCase):
    """resolve_permission_detailed appends matched-rule provenance to the reason."""

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
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("git status")
        )
        self.assertIsInstance(resolved, ResolvedDecision)
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
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("rm -rf /")
        )
        self.assertEqual(resolved.decision, "ask")
        self.assertIsNone(resolved.provenance)
        self.assertEqual(
            resolved.reason,
            "Command does not match any allow patterns; awaiting a decision "
            "(no_match_fallback=ask)",
        )


class TestConflictDetection(unittest.TestCase):
    """Allow-over-deny override detection in resolve_permission_detailed."""

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
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("git push")
        )
        self.assertEqual(resolved.decision, "allow")
        self.assertIsNotNone(resolved.override)
        self.assertEqual(resolved.override.winning_pattern, "git *")
        self.assertEqual(resolved.override.overridden_pattern, "git *")
        self.assertEqual(resolved.override.winning_provenance.specificity, 0)
        self.assertEqual(resolved.override.overridden_provenance.specificity, 1)

    def test_no_override_when_no_less_specific_deny(self):
        """
        Given a single more-specific level allowing 'git *' and no deny anywhere
        When 'git push' resolves
        Then the decision is allow and NO override is reported
        """
        config = Configuration(
            layers=(_bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml"),)
        )
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("git push")
        )
        self.assertEqual(resolved.decision, "allow")
        self.assertIsNone(resolved.override)

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
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("rm -rf /")
        )
        self.assertEqual(resolved.decision, "deny")
        self.assertIsNone(resolved.override)


class TestProvenanceHelpers(unittest.TestCase):
    """Branch coverage for the small provenance helpers."""

    def test_append_provenance_none_returns_reason_unchanged(self):
        """
        Given a None provenance
        When _append_provenance is called
        Then the reason is returned unchanged (no bracketed suffix)
        """
        from toolguard.config import _append_provenance

        self.assertEqual(_append_provenance("some reason", None), "some reason")

    def test_provenance_for_pattern_returns_none_on_miss(self):
        """
        Given layers that do not contain the queried pattern
        When _provenance_for_pattern is called
        Then None is returned
        """
        layer = _bash_layer(["git *"], [], 0, "/proj/.claude/toolguard_hook.toml")
        from toolguard.config import Configuration as _Cfg

        # The ToolPatternLayer view is what _provenance_for_pattern consumes.
        cfg = Configuration(layers=(layer,))
        tool_layers = cfg.permission_layers("Bash")
        self.assertIsNone(_Cfg._provenance_for_pattern(tool_layers, "no-such", "allow"))

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
        resolved = config.resolve_permission_detailed(
            "Bash", _detailed_decider("git push")
        )
        self.assertEqual(resolved.decision, "allow")
        self.assertIsNotNone(resolved.override)
        self.assertEqual(resolved.override.overridden_provenance.specificity, 2)


class TestDiscoveryDiagnostic(unittest.TestCase):
    """The once-per-session discovery diagnostic writes to the resolution log."""

    def test_discovery_entry_written_to_resolution_log(self):
        """
        Given a list of discovered level descriptions
        When log_discovery runs
        Then a resolution-log entry 'discovered N config levels: ...' is written
             to toolguard-YYYY-MM-DD.md (not a warning/error/conflict file)
        """
        with TemporaryDirectory() as tmp:
            log_dir = Path(tmp)
            log_discovery(
                [
                    "project: /proj/.claude/toolguard_hook.toml",
                    "user: /home/.claude/toolguard_hook.toml",
                ],
                log_dir,
            )
            resolution_files = list(log_dir.glob("toolguard-2*.md"))
            # Filter out any per-concern streams (they have a word after toolguard-).
            resolution_files = [p for p in resolution_files if p.name.count("-") == 3]
            self.assertEqual(len(resolution_files), 1)
            text = resolution_files[0].read_text()
            self.assertIn("discovered 2 config levels", text)
            self.assertIn("project: /proj/.claude/toolguard_hook.toml", text)
            # Not routed to other streams.
            self.assertEqual(list(log_dir.glob("toolguard-warning-*.md")), [])
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])


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
            hook_mod._discovery_diagnostic_done = True
            hook_mod._validation_done = True
            hook_mod._divergence_check_done = True
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch(
                                "toolguard.hook.check_and_warn_divergence",
                                return_value=[],
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
            hook_mod._discovery_diagnostic_done = True
            hook_mod._validation_done = True
            hook_mod._divergence_check_done = True
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch(
                                "toolguard.hook.check_and_warn_divergence",
                                return_value=[],
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
            hook_mod._discovery_diagnostic_done = True
            hook_mod._validation_done = True
            hook_mod._divergence_check_done = True
            with patch("sys.stdin", StringIO(json.dumps(hook_input))):
                with patch("sys.stdout", new_callable=StringIO) as out:
                    with patch(
                        "toolguard.hook.load_configuration", return_value=config
                    ):
                        with patch(
                            "toolguard.hook.get_env_config", return_value=env_config
                        ):
                            with patch(
                                "toolguard.hook.check_and_warn_divergence",
                                return_value=[],
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

        # Reset the once-per-session guard so validation runs here.
        hook_mod._validation_done = False
        hook_mod._run_startup_validation(env_config, str(proj_root), config)

        warning_files = list(log_dir.glob("toolguard-warning-*.md"))
        self.assertEqual(len(warning_files), 1)
        text = warning_files[0].read_text()
        occurrences = text.count("Both toolguard_hook.toml and toolguard_hook.json")
        self.assertEqual(occurrences, 1)
        # Not routed to error/conflict streams.
        self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])
        self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])


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

            hook_mod._validation_done = False
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

            hook_mod._validation_done = False
            hook_mod._run_startup_validation(env_config, proj, config)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            self.assertIn("heads up", warning_files[0].read_text())
            self.assertEqual(list(log_dir.glob("toolguard-error-*.md")), [])
            self.assertEqual(list(log_dir.glob("toolguard-conflict-*.md")), [])


if __name__ == "__main__":
    unittest.main()
