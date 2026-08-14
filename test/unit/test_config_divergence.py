"""
Unit tests for config_divergence module.
"""

import io
import json
import os
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import MagicMock, patch

from toolguard import error_reporter, once_per_store
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    load_configuration,
)
from toolguard.config_divergence import (
    DIVERGENCE_WARNING,
    check_and_warn_divergence,
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)
from toolguard.once_per_store import ClaimStatus

from test.unit._config_isolation import ConfigIsolationMixin
from test.unit._once_per_isolation import IsolatedStoreMixin as _IsolatedStoreMixin
from test.unit._subprocess_harness import release_barrier_when_ready, run_child


class TestGetNativePermissions(unittest.TestCase):
    def test_extract_bash_patterns(self):
        """
        Given a settings.local.json with Bash and non-governed-tool patterns across allow/deny/ask
        When get_native_permissions reads it
        Then only the governed Bash patterns are returned in each permission list
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            config = {
                "permissions": {
                    "allow": [
                        "Bash(git status:*)",
                        "Bash(ls:*)",
                        "mcp__basic-memory__read_note",
                        "WebSearch",
                    ],
                    "deny": ["Bash(rm -rf:*)"],
                    "ask": ["Bash(git push:*)"],
                }
            }

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertEqual(result["allow"], ["Bash(git status:*)", "Bash(ls:*)"])
            self.assertEqual(result["deny"], ["Bash(rm -rf:*)"])
            self.assertEqual(result["ask"], ["Bash(git push:*)"])

    def test_extract_file_tool_patterns(self):
        """
        Given a settings.local.json with Read, Write, Edit, and Bash allow patterns
        When get_native_permissions reads it
        Then all four governed file-tool and Bash patterns are present in allow
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"

            config = {
                "permissions": {
                    "allow": [
                        "Read(/tmp/**)",
                        "Write(/tmp/**)",
                        "Edit(/tmp/**)",
                        "Bash(ls:*)",
                    ]
                }
            }

            settings_path.write_text(json.dumps(config))

            result = get_native_permissions(settings_path)

            self.assertIn("Read(/tmp/**)", result["allow"])
            self.assertIn("Write(/tmp/**)", result["allow"])
            self.assertIn("Edit(/tmp/**)", result["allow"])
            self.assertIn("Bash(ls:*)", result["allow"])

    def test_missing_file_is_empty_and_silent(self):
        """
        Given a path to a settings.local.json that does not exist
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists AND reports nothing --
             a project with no settings.local.json is the normal case, not a
             fault, and this runs on every hook invocation

        The empty result alone cannot distinguish the two: letting the open()
        fail instead reaches the same three empty lists through the error path,
        differing only by the warning nobody was asserting was absent.
        """
        buf = io.StringIO()
        with patch("sys.stderr", buf):
            result = get_native_permissions(Path("/nonexistent/settings.local.json"))

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})
        self.assertEqual(buf.getvalue(), "")

    def test_invalid_json(self):
        """
        Given a settings.local.json containing invalid JSON
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists without raising
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings_path.write_text("{ invalid json }")

            result = get_native_permissions(settings_path)

            self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

    def test_non_object_json_top_level_is_treated_as_unreadable(self):
        """
        Given a settings.local.json that is well-formed JSON but whose top
            level is a list rather than an object
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists without raising --
             a file toolguard cannot make sense of is handled the same way as
             an unparseable one, because this runs on the live hook path

        Currently RED: the try/except wraps only json.load, so the
        config.get("permissions", {}) below it raises AttributeError out of
        check_and_warn_divergence (TOO-45 follow-up row V2).
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings_path.write_text(json.dumps(["Bash(git status:*)"]))

            result = get_native_permissions(settings_path)

            self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

    def test_invalid_json_reports_a_warning_to_stderr(self):
        """
        Given a settings.local.json containing invalid JSON
        When get_native_permissions reads it
        Then the failure, naming the path, reaches stderr (TOO-45 punch-list
             #04: via error_reporter.report_warning)
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings_path.write_text("{ invalid json }")

            buf = io.StringIO()
            with patch("sys.stderr", buf):
                get_native_permissions(settings_path)

            self.assertIn(str(settings_path), buf.getvalue())
            self.assertIn("Failed to load", buf.getvalue())

    def test_invalid_json_reaches_the_warning_log_with_an_active_reporter(self):
        """
        Given a settings.local.json containing invalid JSON, AND a
            registered error_reporter.Reporter with a resolvable log
            directory is active (TOO-45 punch-list #04 fix pass item 8a: a
            real converted call site, not a synthetic message)
        When get_native_permissions reads it
        Then the failure, naming the path, lands in the WARNING log file,
             not just stderr
        """
        with TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.local.json"
            settings_path.write_text("{ invalid json }")
            log_dir = Path(tmpdir) / "logs"
            log_dir.mkdir()

            with error_reporter.active(error_reporter.Reporter(log_dir=log_dir)):
                get_native_permissions(settings_path)

            warning_files = list(log_dir.glob("toolguard-warning-*.md"))
            self.assertEqual(len(warning_files), 1)
            content = warning_files[0].read_text()
            self.assertIn(str(settings_path), content)
            self.assertIn("Failed to load", content)


def _config_from_layers(*layers):
    """Build a Configuration from (source_type, content) layer specs, most-specific first."""
    built = []
    for i, (source_type, content) in enumerate(layers):
        prov = Provenance("project", source_type, "json", Path(f"/fake/{i}.json"), i)
        built.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(built))


class TestGetToolguardPermissions(unittest.TestCase):
    def test_extract_from_json(self):
        """
        Given a toolguard_hook layer with allow and deny permissions
        When get_toolguard_permissions reads the resolved Configuration
        Then the allow and deny patterns are returned and ask is empty
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": ["Bash(git status:*)", "Read(/tmp/**)"],
                        "deny": ["Bash(rm -rf:*)"],
                    }
                },
            )
        )
        result = get_toolguard_permissions(config)

        self.assertEqual(result["allow"], ["Bash(git status:*)", "Read(/tmp/**)"])
        self.assertEqual(result["deny"], ["Bash(rm -rf:*)"])
        self.assertEqual(result["ask"], [])

    def test_ignore_claude_settings(self):
        """
        Given a native ('claude') layer with permissions
        When get_toolguard_permissions reads the resolved Configuration
        Then it returns empty permissions because native layers are ignored
        """
        config = _config_from_layers(
            ("claude", {"permissions": {"allow": ["Bash(git push:*)"]}})
        )
        result = get_toolguard_permissions(config)

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

    def test_merge_multiple_files(self):
        """
        Given two toolguard_hook layers each with a distinct allow pattern
        When get_toolguard_permissions merges them
        Then both patterns appear in the merged allow list
        """
        config = _config_from_layers(
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
            ("toolguard_hook", {"permissions": {"allow": ["Bash(ls:*)"]}}),
        )
        result = get_toolguard_permissions(config)

        self.assertIn("Bash(git status:*)", result["allow"])
        self.assertIn("Bash(ls:*)", result["allow"])

    def test_deduplicate_patterns(self):
        """
        Given two toolguard_hook layers with the same allow pattern
        When get_toolguard_permissions merges them
        Then the shared pattern appears only once
        """
        config = _config_from_layers(
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
            ("toolguard_hook", {"permissions": {"allow": ["Bash(git status:*)"]}}),
        )
        result = get_toolguard_permissions(config)

        self.assertEqual(result["allow"].count("Bash(git status:*)"), 1)


class TestFindDivergentPatterns(unittest.TestCase):
    def test_find_new_patterns(self):
        """
        Given a native allow list with one pattern absent from toolguard
        When find_divergent_patterns compares them
        Then only the native-only pattern is reported as divergent
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(git push:*)"],
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result["allow"], ["Bash(git push:*)"])
        self.assertEqual(result["deny"], [])
        self.assertEqual(result["ask"], [])

    def test_governed_filter_excludes_ungoverned_tools(self):
        """
        Given native patterns for governed (Bash/Read) AND ungoverned (WebFetch/Skill)
            tools, none present in toolguard, and a governed_tools set of {Bash,Read,Write,Edit}
        When find_divergent_patterns is given that governed_tools set
        Then only the governed-tool patterns are reported divergent; WebFetch/Skill
            patterns are excluded (so migration never moves and disables them -- issue #1)
        """
        native = {
            "allow": [
                "Bash(git push:*)",
                "Read(/tmp/**)",
                "WebFetch(domain:docs.anthropic.com)",
                "Skill(recall)",
            ],
            "deny": [],
            "ask": [],
        }
        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(
            native, toolguard, [], governed_tools={"Bash", "Read", "Write", "Edit"}
        )

        self.assertEqual(result["allow"], ["Bash(git push:*)", "Read(/tmp/**)"])

    def test_governed_filter_none_keeps_all_backward_compatible(self):
        """
        Given native patterns for governed and ungoverned tools
        When find_divergent_patterns is called WITHOUT a governed_tools argument
            (the default None)
        Then no tool filtering happens -- every divergent pattern is reported
            (preserving the pre-existing behavior for callers that pass no filter)
        """
        native = {
            "allow": ["Bash(git push:*)", "WebFetch(domain:x)"],
            "deny": [],
            "ask": [],
        }
        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertIn("Bash(git push:*)", result["allow"])
        self.assertIn("WebFetch(domain:x)", result["allow"])

    def test_governed_filter_is_dynamic_includes_webfetch_when_governed(self):
        """
        Given a governed_tools set that INCLUDES WebFetch (the list changes over time
            -- WebFetch is slated to become governed)
        When find_divergent_patterns filters an unmatched WebFetch pattern
        Then the WebFetch pattern IS reported divergent, proving the filter tracks the
            actual governed set rather than a hardcoded Bash/Read/Write/Edit literal
        """
        native = {
            "allow": ["WebFetch(domain:x)", "Skill(recall)"],
            "deny": [],
            "ask": [],
        }
        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(
            native,
            toolguard,
            [],
            governed_tools={"Bash", "Read", "Write", "Edit", "WebFetch"},
        )

        self.assertEqual(result["allow"], ["WebFetch(domain:x)"])

    def test_governed_filter_applies_to_deny_and_ask_too(self):
        """
        Given ungoverned-tool patterns in the deny and ask lists as well as allow
        When find_divergent_patterns filters by governed_tools
        Then ungoverned patterns are excluded from ALL three permission lists
        """
        native = {
            "allow": ["WebFetch(domain:x)"],
            "deny": ["Skill(danger)"],
            "ask": ["WebFetch(domain:y)"],
        }
        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(
            native, toolguard, [], governed_tools={"Bash", "Read", "Write", "Edit"}
        )

        self.assertEqual(result["allow"], [])
        self.assertEqual(result["deny"], [])
        self.assertEqual(result["ask"], [])

    def test_ignore_patterns_in_takeover_mode(self):
        """
        Given native-only patterns that are all listed as ignored
        When find_divergent_patterns is given that ignored list
        Then no divergent allow patterns are reported
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(uv run pytest:*)", "Bash(open:*)"],
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        ignored = ["Bash(uv run pytest:*)", "Bash(open:*)"]

        result = find_divergent_patterns(native, toolguard, ignored)

        self.assertEqual(result["allow"], [])

    def test_exact_string_matching(self):
        """
        Given a native pattern that differs from a toolguard pattern only by trailing whitespace
        When find_divergent_patterns compares them
        Then the whitespace-different pattern is reported as divergent (matching is exact)
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(git status:*)  "],
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertIn("Bash(git status:*)  ", result["allow"])

    def test_all_permission_types(self):
        """
        Given native allow, deny, and ask patterns absent from toolguard
        When find_divergent_patterns compares them
        Then divergences are reported for all three permission types
        """
        native = {
            "allow": ["Bash(ls:*)"],
            "deny": ["Bash(rm:*)"],
            "ask": ["Bash(git push:*)"],
        }

        toolguard = {"allow": [], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result["allow"], ["Bash(ls:*)"])
        self.assertEqual(result["deny"], ["Bash(rm:*)"])
        self.assertEqual(result["ask"], ["Bash(git push:*)"])

    def test_no_divergence(self):
        """
        Given identical native and toolguard permission sets
        When find_divergent_patterns compares them
        Then no divergences are reported in any permission type
        """
        native = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})


class TestDivergenceComparisonSemanticsGuard(unittest.TestCase):
    def test_structured_toolguard_entry_does_not_raise(self):
        """
        Given a toolguard_hook layer with a structured ({match=..., metadata})
            allow entry
        When get_toolguard_permissions extracts patterns from the resolved
            Configuration
        Then it returns normally without raising, and the plain pattern is
            what comes back (metadata is not part of this projection)
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": [
                            {
                                "match": "Bash(git status:*)",
                                "additionalContext": "read-only",
                            }
                        ]
                    }
                },
            )
        )

        result = get_toolguard_permissions(config)

        self.assertEqual(result["allow"], ["Bash(git status:*)"])

    def test_structured_entry_pattern_present_w1_regression_guard(self):
        """
        Given a toolguard_hook layer with ONLY a structured deny entry (no
            plain-string twin anywhere)
        When get_toolguard_permissions extracts patterns
        Then the structured entry's pattern IS present in the result -- the
            W1 silent-drop regression this whole increment guards against: an
            old isinstance(perm, str) filter would have silently dropped it,
            making find_divergent_patterns compare against a pool missing an
            entry it never actually lost
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "deny": [
                            {"match": "Bash(rm -rf:*)", "additionalContext": "danger"}
                        ]
                    }
                },
            )
        )

        result = get_toolguard_permissions(config)

        self.assertIn("Bash(rm -rf:*)", result["deny"])

    def test_metadata_only_on_one_side_is_not_divergent(self):
        """
        Given a native allow pattern present as a PLAIN string, and the same
            pattern present on the toolguard side as a STRUCTURED entry
            carrying metadata
        When find_divergent_patterns compares native against
            get_toolguard_permissions()'s projection
        Then the pattern is NOT reported divergent -- metadata present on one
            side only does not make it a different rule (comparison #1,
            `.pattern` alone; not `identity()`)
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": [
                            {
                                "match": "Bash(git status:*)",
                                "additionalContext": "read-only",
                            }
                        ]
                    }
                },
            )
        )
        toolguard = get_toolguard_permissions(config)
        native = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        self.assertEqual(result["allow"], [])

    def test_same_pattern_different_metadata_not_divergent_different_pattern_is(self):
        """
        Given two toolguard_hook layers that both define allow entries for the
            SAME pattern with DIFFERENT metadata values (a genuine
            contradiction if fed to merge_entries), plus a second, genuinely
            distinct pattern that only the more-specific layer defines and
            that is absent from native
        When get_toolguard_permissions merges the layers (comparison #1,
            pattern-only de-dup: most-specific layer wins) and
            find_divergent_patterns compares against a native snapshot that
            has the shared pattern but not the distinct one
        Then the shared, differently-annotated pattern appears exactly ONCE in
            the merged toolguard permissions (proving the merge is keyed on
            `.pattern`, not `identity()` -- identity() would keep both and
            the pattern would then still reduce to one string but the
            underlying bug this guards is a future switch to identity()-based
            SET comparison, which would double-count or never converge) and
            is NOT reported divergent, while the genuinely different pattern
            (absent from native) still IS reported divergent
        """
        config = _config_from_layers(
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": [
                            {"match": "Bash(git status:*)", "additionalContext": "A"},
                            {"match": "Bash(git push:*)", "additionalContext": "B"},
                        ]
                    }
                },
            ),
            (
                "toolguard_hook",
                {
                    "permissions": {
                        "allow": [
                            {
                                "match": "Bash(git status:*)",
                                "additionalContext": "different",
                            },
                        ]
                    }
                },
            ),
        )
        toolguard = get_toolguard_permissions(config)

        self.assertEqual(toolguard["allow"].count("Bash(git status:*)"), 1)

        native = {
            "allow": ["Bash(git status:*)", "Bash(git commit:*)"],
            "deny": [],
            "ask": [],
        }
        result = find_divergent_patterns(native, toolguard, [])

        self.assertNotIn("Bash(git status:*)", result["allow"])
        self.assertEqual(result["allow"], ["Bash(git commit:*)"])


class TestDivergenceWarningKey(unittest.TestCase):
    def test_key_matches_the_literal_used_by_other_tests(self):
        """
        Given the module-level DIVERGENCE_WARNING throttled-thing
        When its private key is compared to the literal string other tests
            in this file claim against directly
        Then they match -- if this ever drifts, those tests would silently
             stop exercising the real gate
        """
        self.assertEqual(DIVERGENCE_WARNING._key, "divergence_warning")


class _DivergenceFixture(ConfigIsolationMixin, _IsolatedStoreMixin):
    """
    Isolated home, project root, log dir and claim store, plus writers for the
    two config files check_and_warn_divergence compares.

    check_and_warn_divergence calls load_configuration, whose discovery reads
    ~/.claude and the rules directories. Without ConfigIsolationMixin these
    tests read the developer's real config: measured 2026-08-13, five real
    files were loaded and a home config allowing Bash(git push:*) turned eight
    of them red.
    """

    #: Preserved through the mixin's clear=True environment patch so child
    #: processes launched from a test still get a usable PATH.
    _EXTRA_ENV = {"PATH": os.environ.get("PATH", "")}

    def setUp(self):
        """Isolate the store, then the config hierarchy, and create the project's .claude."""
        super().setUp()
        self.home, self.project = self.isolate_config_environment(
            extra_env=dict(self._EXTRA_ENV)
        )
        self.claude_dir = self.project / ".claude"
        self.claude_dir.mkdir()

    def write_native(self, allow=(), deny=(), ask=()):
        """Write the project's native settings.local.json with these patterns."""
        self._write("settings.local.json", allow, deny, ask)

    def write_hook(self, allow=(), deny=(), ask=()):
        """Write the project's toolguard_hook.json with these patterns."""
        self._write("toolguard_hook.json", allow, deny, ask)

    def _write(self, name, allow, deny, ask):
        permissions = {"allow": list(allow), "deny": list(deny), "ask": list(ask)}
        (self.claude_dir / name).write_text(json.dumps({"permissions": permissions}))


#: The takeover_config shape used by tests that are not about takeover mode.
_NO_TAKEOVER = {"enabled": False, "ignored_allow_patterns": []}


class TestCheckAndWarnDivergence(_DivergenceFixture, unittest.TestCase):
    def test_no_divergence(self):
        """
        Given matching native settings and toolguard_hook configs in a project
        When check_and_warn_divergence runs
        Then it returns a DivergenceCheckResult with an empty divergent_patterns
             list and no warning_message/corrective_steps (nothing to warn about)
        """
        self.write_native(allow=["Bash(git status:*)"])
        self.write_hook(allow=["Bash(git status:*)"])

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, [])
        self.assertIsNone(result.warning_message)
        self.assertIsNone(result.corrective_steps)

    def test_with_divergence(self):
        """
        Given native settings allowing a pattern that the toolguard_hook config lacks
        When check_and_warn_divergence runs
        Then the divergent pattern is included in divergent_patterns, and
             warning_message/corrective_steps are populated (TOO-45 R5d: this
             module hands the warning text to its caller rather than logging
             it itself)
        """
        self.write_native(allow=["Bash(git status:*)", "Bash(git push:*)"])
        self.write_hook(allow=["Bash(git status:*)"])

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, ["Bash(git push:*)"])
        self.assertIsNotNone(result.warning_message)
        self.assertIn("Bash(git push:*)", result.warning_message)
        self.assertNotIn("Bash(git status:*)", result.warning_message)
        self.assertIsNotNone(result.corrective_steps)

    def test_deduplication(self):
        """
        Given a divergent native pattern with no matching toolguard config
        When check_and_warn_divergence runs twice in a row
        Then the first call reports the divergence and the second is deduplicated to
             an empty divergent_patterns list with no warning_message
        """
        self.write_native(allow=["Bash(git push:*)"])

        result1 = check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertIn("Bash(git push:*)", result1.divergent_patterns)

        result2 = check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertEqual(result2.divergent_patterns, [])
        self.assertIsNone(result2.warning_message)

    def test_already_warned_day_skips_the_config_analysis_entirely(self):
        """
        Given a project already warned about a divergent pattern today
        When check_and_warn_divergence is called again the same day
        Then load_configuration is not called a second time -- the once-per-day
             pre-check short-circuits before the analysis, so an already-warned
             day costs nothing on the hook's critical path

        The dedup outcome alone cannot see this: .warn()'s own claim also
        returns an empty result, so removing the pre-check leaves
        test_deduplication green while re-running the whole analysis on every
        PreToolUse call.
        """
        self.write_native(allow=["Bash(git push:*)"])
        spy = MagicMock(wraps=load_configuration)

        with patch("toolguard.config_divergence.load_configuration", spy):
            first = check_and_warn_divergence(self.project, _NO_TAKEOVER)
            self.assertIn("Bash(git push:*)", first.divergent_patterns)

            second = check_and_warn_divergence(self.project, _NO_TAKEOVER)
            self.assertEqual(second.divergent_patterns, [])

            self.assertEqual(spy.call_count, 1)

    def test_a_claim_taken_after_the_pre_check_still_suppresses_the_warning(self):
        """
        Given the day's slot already taken by another process, and this call's
            once-per-day pre-check answering False -- the interleaving the
            claim exists to close, where both processes get past their
            pre-checks and only one may print
        When check_and_warn_divergence runs
        Then it reports nothing: the claim taken immediately before the notice
             is a second, independent gate, not a restatement of the pre-check

        done() is stubbed to reproduce that interleaving in one process.
        Without the stub the pre-check answers first and masks this branch
        entirely, which is why deleting either gate on its own leaves
        test_deduplication green.
        """
        self.write_native(allow=["Bash(git push:*)"])
        once_per_store.claim(
            self.project,
            "divergence_warning",
            once_per_store.day_scope(),
            timedelta(days=1),
        )

        with patch.object(DIVERGENCE_WARNING, "done", return_value=False) as pre_check:
            result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertTrue(pre_check.called, "the pre-check stub was never consulted")
        self.assertEqual(result.divergent_patterns, [])
        self.assertIsNone(result.warning_message)

    def test_ungoverned_native_patterns_are_not_reported_divergent(self):
        """
        Given native settings allowing both a Bash pattern and a WebFetch
            pattern, neither present in toolguard config, and no configured
            governed_tools (so the default Bash/Read/Write/Edit applies)
        When check_and_warn_divergence runs
        Then only the Bash pattern is reported -- check_and_warn_divergence
             passes the configuration's governed tools down to
             find_divergent_patterns, so migrating the warning's contents can
             never move a WebFetch rule out of settings.local.json and leave
             it enforced by nobody
        """
        self.write_native(
            allow=["Bash(git push:*)", "WebFetch(domain:docs.anthropic.com)"]
        )

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, ["Bash(git push:*)"])
        self.assertNotIn("WebFetch", result.warning_message)

    def test_governed_tools_filter_follows_the_configured_set(self):
        """
        Given the same native WebFetch pattern, and a toolguard_hook config
            that DOES list WebFetch in governed_tools
        When check_and_warn_divergence runs
        Then the WebFetch pattern IS reported divergent -- the filter reads the
             resolved configuration's governed_tools rather than a hardcoded
             default set
        """
        self.write_native(allow=["WebFetch(domain:docs.anthropic.com)"])
        (self.claude_dir / "toolguard_hook.json").write_text(
            json.dumps({"governed_tools": ["Bash", "WebFetch"], "permissions": {}})
        )

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(
            result.divergent_patterns, ["WebFetch(domain:docs.anthropic.com)"]
        )

    def test_stale_claude_settings_path_does_not_supply_the_toolguard_side(self):
        """
        Given CLAUDE_SETTINGS_PATH pointing at an unrelated project whose
            adjacent toolguard_hook config already allows the pattern that
            diverges in THIS project
        When check_and_warn_divergence runs
        Then the divergence is still reported -- the comparison is between one
             project's settings.local.json and that same project's toolguard
             config, so the environment override is ignored here even though
             the hook honours it everywhere else
        """
        self.write_native(allow=["Bash(git push:*)"])

        unrelated = self.project.parent / "unrelated"
        unrelated.mkdir()
        (unrelated / "settings.local.json").write_text(json.dumps({"permissions": {}}))
        (unrelated / "toolguard_hook.json").write_text(
            json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
        )

        with patch.dict(
            os.environ,
            {"CLAUDE_SETTINGS_PATH": str(unrelated / "settings.local.json")},
        ):
            result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, ["Bash(git push:*)"])

    def test_warning_lists_ten_patterns_then_a_count_of_the_rest(self):
        """
        Given twelve divergent native patterns
        When check_and_warn_divergence runs
        Then all twelve are returned in divergent_patterns, but the warning
             text lists only the first ten in sorted order and ends with a
             count of the remaining two
        """
        patterns = [f"Bash(cmd{i:02d}:*)" for i in range(12)]
        self.write_native(allow=patterns)

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, patterns)
        listed = [
            line.strip()[2:]
            for line in result.warning_message.splitlines()
            if line.startswith("  - ")
        ]
        self.assertEqual(listed, patterns[:10])
        self.assertIn("... and 2 more", result.warning_message)

    def test_takeover_mode_ignored_patterns(self):
        """
        Given takeover mode ignoring one of two divergent native patterns
        When check_and_warn_divergence runs
        Then only the non-ignored pattern is reported as divergent
        """
        self.write_native(allow=["Bash(uv run pytest:*)", "Bash(git push:*)"])
        takeover_config = {
            "enabled": True,
            "ignored_allow_patterns": ["Bash(uv run pytest:*)"],
            "additional_ignored_patterns": [],
        }

        result = check_and_warn_divergence(self.project, takeover_config)

        self.assertEqual(result.divergent_patterns, ["Bash(git push:*)"])

    def test_ignored_allow_patterns_apply_with_takeover_disabled(self):
        """
        Given takeover mode DISABLED and one of two divergent native patterns
            listed in ignored_allow_patterns
        When check_and_warn_divergence runs
        Then the ignored pattern is not reported -- ignored_allow_patterns is
             honoured whatever the takeover flag says

        Pins today's behaviour, and nothing more. auto_migrate.run_auto_migration
        ignores nothing unless takeover is enabled, so with takeover off a
        pattern can be excluded from this warning and still be migrated by the
        migration this warning gates (TOO-45 follow-up rows 20/EL3). Which of
        the two is right is a product decision that has not been made; do not
        read this test as settling it.
        """
        self.write_native(allow=["Bash(uv run pytest:*)", "Bash(git push:*)"])
        takeover_config = {
            "enabled": False,
            "ignored_allow_patterns": ["Bash(uv run pytest:*)"],
            "additional_ignored_patterns": [],
        }

        result = check_and_warn_divergence(self.project, takeover_config)

        self.assertEqual(result.divergent_patterns, ["Bash(git push:*)"])

    def test_additional_ignored_patterns_apply_only_when_takeover_is_enabled(self):
        """
        Given a single divergent native pattern listed only in
            additional_ignored_patterns
        When check_and_warn_divergence runs first with takeover ENABLED and
            then, the same day, with takeover DISABLED
        Then the enabled run reports nothing and the disabled run reports the
             pattern -- additional_ignored_patterns is gated on the takeover
             flag where ignored_allow_patterns is not

        The two runs share a day deliberately: the enabled run finds nothing,
        and finding nothing does not consume the day's warning slot.
        """
        self.write_native(allow=["Bash(git push:*)"])
        takeover_config = {
            "enabled": True,
            "ignored_allow_patterns": [],
            "additional_ignored_patterns": ["Bash(git push:*)"],
        }

        enabled = check_and_warn_divergence(self.project, takeover_config)
        self.assertEqual(enabled.divergent_patterns, [])

        disabled = check_and_warn_divergence(
            self.project, {**takeover_config, "enabled": False}
        )
        self.assertEqual(disabled.divergent_patterns, ["Bash(git push:*)"])

    def test_no_divergence_releases_claim_so_later_scan_same_day_still_works(self):
        """
        Given a project with no divergence on the first check, then a
            divergent pattern added to settings.local.json before a second
            check the same day
        When check_and_warn_divergence runs twice
        Then the first call reports nothing, and the second call (same day)
             DOES report the newly-added divergence -- finding nothing does
             not consume the day's warning slot, only actually warning does
        """
        self.write_native(allow=["Bash(git status:*)"])
        self.write_hook(allow=["Bash(git status:*)"])

        result1 = check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertEqual(result1.divergent_patterns, [])

        self.write_native(allow=["Bash(git status:*)", "Bash(git push:*)"])

        result2 = check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertIn("Bash(git push:*)", result2.divergent_patterns)

    def test_warning_claims_todays_slot(self):
        """
        Given a project with a divergent pattern
        When check_and_warn_divergence runs and reports it
        Then today's slot for this module's key is held -- proving the
             dedup goes through the once-per-day claim store, not a marker
             file
        """
        self.write_native(allow=["Bash(git push:*)"])

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertIn("Bash(git push:*)", result.divergent_patterns)

        still_claimed = (
            once_per_store.claim(
                self.project,
                "divergence_warning",
                once_per_store.day_scope(),
                timedelta(days=1),
            ).status
            == ClaimStatus.HELD_BY_SOMEONE_ELSE
        )
        self.assertTrue(still_claimed)

    def test_warns_when_sqlite_unavailable(self):
        """
        Given a project with a divergent pattern and sqlite3 unavailable
        When check_and_warn_divergence runs
        Then it still reports the divergence and prints the warning (a
             warning fails OPEN -- see toolguard.once_per.OncePer.warn),
             plus a one-time notice explaining that it can no longer be
             throttled to once per day
        """
        self.write_native(allow=["Bash(git push:*)"])

        with patch.object(once_per_store, "sqlite3", None):
            with patch("builtins.print") as mock_print:
                result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertIn("Bash(git push:*)", result.divergent_patterns)
        printed = " ".join(str(c.args[0]) for c in mock_print.call_args_list if c.args)
        self.assertIn("sqlite3 is unavailable", printed)
        self.assertIn("the configuration divergence warning", printed)


class TestCheckAndWarnDivergenceExceptionSafety(_DivergenceFixture, unittest.TestCase):
    def test_exception_during_analysis_leaves_period_unclaimed(self):
        """
        Given load_configuration raises during the analysis phase (e.g. a
            malformed config file), before any warning is ever produced
        When check_and_warn_divergence is called
        Then the exception propagates AND a subsequent, successful call the
             same day can still detect and report divergence -- the crash
             must not have consumed the day's warning slot
        """
        self.write_native(allow=["Bash(git push:*)"])
        boom = RuntimeError("malformed config file")

        with patch(
            "toolguard.config_divergence.load_configuration", side_effect=boom
        ) as failing_load:
            with self.assertRaises(RuntimeError):
                check_and_warn_divergence(self.project, _NO_TAKEOVER)
        self.assertTrue(failing_load.called)

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertIn("Bash(git push:*)", result.divergent_patterns)
        self.assertIsNotNone(result.warning_message)


class TestDivergenceCheckCreatesNoStorageWhenNothingToReport(
    _DivergenceFixture, unittest.TestCase
):
    def test_no_divergence_creates_no_legacy_logs_dir_or_db(self):
        """
        Given a project with matching native and toolguard permissions (no
            divergence), a project logs directory that does not yet exist, and
            a claim database that has never been written
        When check_and_warn_divergence runs -- this is what every hook
            invocation calls, regardless of whether takeover mode is on
        Then neither the project's logs directory nor the claim database is
             created: a healthy, non-diverging project must gain no storage it
             never asked for, which holds only because the day's claim is taken
             at the end, once there is something to show for it
        """
        logs_dir = self.project / "logs"
        store_path = once_per_store._STORE_PATH
        self.assertFalse(store_path.exists(), "store pre-exists; fixture is not clean")

        self.write_native(allow=["Bash(git status:*)"])
        self.write_hook(allow=["Bash(git status:*)"])

        result = check_and_warn_divergence(self.project, _NO_TAKEOVER)

        self.assertEqual(result.divergent_patterns, [])
        self.assertFalse(logs_dir.exists())
        self.assertFalse(store_path.exists())


class TestConcurrentDivergenceWarning(_DivergenceFixture, unittest.TestCase):
    def test_two_processes_only_one_warns(self):
        """
        Given two separate OS processes, both able to detect the same
            divergent pattern in a shared project, racing
            check_and_warn_divergence against the same claim store,
            synchronized via a barrier file
        When both processes run concurrently
        Then exactly one reports a warning_message and the other reports
             none -- claiming only immediately before the stderr notice
             still closes the race
        """
        # The children are real processes and inherit no in-process patching:
        # HOME and the store path have to travel to them explicitly, or they
        # read the developer's real config and real ~/.toolguard/once_per.db.
        store_path = once_per_store._STORE_PATH
        child_env = {**os.environ, "HOME": str(self.home)}

        ipc = self.project.parent / "ipc"
        ipc.mkdir()
        barrier = ipc / "go"
        ready_markers = [ipc / f"ready_{i}" for i in range(2)]

        self.write_native(allow=["Bash(git push:*)"])

        script = (
            "import sys, time\n"
            "from pathlib import Path\n"
            "from toolguard import once_per_store\n"
            "from toolguard.config_divergence import check_and_warn_divergence\n"
            "once_per_store._STORE_PATH = Path(sys.argv[3])\n"
            "project_root = Path(sys.argv[1])\n"
            "barrier = Path(sys.argv[2])\n"
            "Path(sys.argv[4]).touch()\n"
            "deadline = time.monotonic() + 10\n"
            "while not barrier.exists() and time.monotonic() < deadline:\n"
            "    pass\n"
            "result = check_and_warn_divergence(\n"
            "    project_root,\n"
            "    {'enabled': False, 'ignored_allow_patterns': []},\n"
            ")\n"
            "print(1 if result.warning_message else 0)\n"
        )

        procs = [
            run_child(
                script,
                str(self.project),
                str(barrier),
                str(store_path),
                str(ready),
                env=child_env,
            )
            for ready in ready_markers
        ]

        self.assertTrue(
            release_barrier_when_ready(barrier, ready_markers, timeout=10),
            "children never reached the barrier wait loop",
        )

        outputs = []
        for proc in procs:
            stdout, stderr = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 0, msg=stderr)
            outputs.append(stdout.strip())

        self.assertEqual(sorted(outputs), ["0", "1"])


if __name__ == "__main__":
    unittest.main()
