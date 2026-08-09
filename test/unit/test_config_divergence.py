"""
Unit tests for config_divergence module.
"""

import json
import subprocess
import sys
import time
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import MappingProxyType
from unittest.mock import patch

from toolguard import once_per_store
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_divergence import (
    DIVERGENCE_WARNING,
    check_and_warn_divergence,
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)
from toolguard.once_per_store import ClaimStatus

from test.unit._once_per_isolation import IsolatedStoreMixin as _IsolatedStoreMixin

#: test/unit/test_config_divergence.py -> parents[0]=test/unit, [1]=test, [2]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]


class TestGetNativePermissions(unittest.TestCase):
    """Test extracting permissions from settings.local.json."""

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
                        "mcp__basic-memory__read_note",  # Not a governed tool
                        "WebSearch",  # Not a governed tool
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

    def test_missing_file(self):
        """
        Given a path to a settings.local.json that does not exist
        When get_native_permissions reads it
        Then it returns empty allow, deny, and ask lists
        """
        result = get_native_permissions(Path("/nonexistent/settings.local.json"))

        self.assertEqual(result, {"allow": [], "deny": [], "ask": []})

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


def _config_from_layers(*layers):
    """
    Build a Configuration from explicit (source_type, content) layer specs.

    Each spec is a ``(source_type, content_dict)`` pair; layers are ordered
    most-specific first. Lets divergence tests exercise get_toolguard_permissions
    against the public Configuration surface without touching files.
    """
    built = []
    for i, (source_type, content) in enumerate(layers):
        prov = Provenance("project", source_type, "json", Path(f"/fake/{i}.json"), i)
        built.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(built))


class TestGetToolguardPermissions(unittest.TestCase):
    """Test extracting permissions from the resolved toolguard configuration."""

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

        # Should be empty since we ignore claude settings
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

        # Should only appear once
        self.assertEqual(result["allow"].count("Bash(git status:*)"), 1)


class TestFindDivergentPatterns(unittest.TestCase):
    """Test finding divergent patterns."""

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

        # Should not include ignored patterns
        self.assertEqual(result["allow"], [])

    def test_exact_string_matching(self):
        """
        Given a native pattern that differs from a toolguard pattern only by trailing whitespace
        When find_divergent_patterns compares them
        Then the whitespace-different pattern is reported as divergent (matching is exact)
        """
        native = {
            "allow": ["Bash(git status:*)", "Bash(git status:*)  "],  # Trailing space
            "deny": [],
            "ask": [],
        }

        toolguard = {"allow": ["Bash(git status:*)"], "deny": [], "ask": []}

        result = find_divergent_patterns(native, toolguard, [])

        # Trailing space makes it different
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
    """
    Regression guard for TOO-19 Phase 0a increment 7.

    Locks in that the divergence pipeline (get_toolguard_permissions ->
    find_divergent_patterns) compares RuleEntry objects by ``.pattern`` ALONE
    (comparison #1 in RuleEntry.identity()'s docstring), never by
    ``identity()`` (which folds in metadata). An entry carrying metadata on
    one side and none -- or different metadata -- on the other is the SAME
    rule, not a divergence. Were this ever switched to identity(), migration
    would re-add the "missing" native twin forever, since it would never
    stop looking divergent.
    """

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

        result = get_toolguard_permissions(config)  # must not raise

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

        # Pattern-only de-dup: exactly one occurrence despite differing
        # metadata across the two layers.
        self.assertEqual(toolguard["allow"].count("Bash(git status:*)"), 1)

        native = {
            "allow": ["Bash(git status:*)", "Bash(git commit:*)"],
            "deny": [],
            "ask": [],
        }
        result = find_divergent_patterns(native, toolguard, [])

        # The shared, differently-annotated pattern is not divergent...
        self.assertNotIn("Bash(git status:*)", result["allow"])
        # ...but a genuinely different pattern absent from toolguard still is.
        self.assertEqual(result["allow"], ["Bash(git commit:*)"])


class TestDivergenceWarningKey(unittest.TestCase):
    """Locks in the key string other tests here claim directly against the store."""

    def test_key_matches_the_literal_used_by_other_tests(self):
        """
        Given the module-level DIVERGENCE_WARNING throttled-thing
        When its private key is compared to the literal string other tests
            in this file claim against directly
        Then they match -- if this ever drifts, those tests would silently
             stop exercising the real gate
        """
        self.assertEqual(DIVERGENCE_WARNING._key, "divergence_warning")


class TestCheckAndWarnDivergence(_IsolatedStoreMixin, unittest.TestCase):
    """Test the main divergence check function."""

    def test_no_divergence(self):
        """
        Given matching native settings and toolguard_hook configs in a project
        When check_and_warn_divergence runs
        Then it returns a DivergenceCheckResult with an empty divergent_patterns
             list and no warning_message/corrective_steps (nothing to warn about)
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            # Create matching configs
            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result = check_and_warn_divergence(project_root, takeover_config)

            # No divergence
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
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {
                "permissions": {"allow": ["Bash(git status:*)", "Bash(git push:*)"]}
            }

            settings_path.write_text(json.dumps(config))

            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_config = {"permissions": {"allow": ["Bash(git status:*)"]}}

            hook_path.write_text(json.dumps(hook_config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result = check_and_warn_divergence(project_root, takeover_config)

            # Should find divergence
            self.assertIn("Bash(git push:*)", result.divergent_patterns)
            self.assertIsNotNone(result.warning_message)
            self.assertIn("Bash(git push:*)", result.warning_message)
            self.assertIsNotNone(result.corrective_steps)

    def test_deduplication(self):
        """
        Given a divergent native pattern with no matching toolguard config
        When check_and_warn_divergence runs twice in a row
        Then the first call reports the divergence and the second is deduplicated to
             an empty divergent_patterns list with no warning_message
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {"permissions": {"allow": ["Bash(git push:*)"]}}

            settings_path.write_text(json.dumps(config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            # First call should find divergence
            result1 = check_and_warn_divergence(project_root, takeover_config)
            self.assertIn("Bash(git push:*)", result1.divergent_patterns)

            # Second call should be deduplicated
            result2 = check_and_warn_divergence(project_root, takeover_config)
            self.assertEqual(result2.divergent_patterns, [])
            self.assertIsNone(result2.warning_message)

    def test_takeover_mode_ignored_patterns(self):
        """
        Given takeover mode ignoring one of two divergent native patterns
        When check_and_warn_divergence runs
        Then only the non-ignored pattern is reported as divergent
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)

            # Create project marker so discover_config_files works
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)

            config = {
                "permissions": {"allow": ["Bash(uv run pytest:*)", "Bash(git push:*)"]}
            }

            settings_path.write_text(json.dumps(config))

            takeover_config = {
                "enabled": True,
                "ignored_allow_patterns": ["Bash(uv run pytest:*)"],
                "additional_ignored_patterns": [],
            }

            result = check_and_warn_divergence(project_root, takeover_config)

            # Should only find git push, not pytest
            self.assertIn("Bash(git push:*)", result.divergent_patterns)
            self.assertNotIn("Bash(uv run pytest:*)", result.divergent_patterns)

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
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status:*)"]}})
            )
            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git status:*)"]}})
            )

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result1 = check_and_warn_divergence(project_root, takeover_config)
            self.assertEqual(result1.divergent_patterns, [])

            settings_path.write_text(
                json.dumps(
                    {
                        "permissions": {
                            "allow": ["Bash(git status:*)", "Bash(git push:*)"]
                        }
                    }
                )
            )

            result2 = check_and_warn_divergence(project_root, takeover_config)
            self.assertIn("Bash(git push:*)", result2.divergent_patterns)

    def test_warning_claims_todays_slot(self):
        """
        Given a project with a divergent pattern
        When check_and_warn_divergence runs and reports it
        Then today's slot for this module's key is held -- proving the
             dedup goes through the once-per-day claim store, not a marker
             file
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
            )

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}
            check_and_warn_divergence(project_root, takeover_config)

            still_claimed = (
                once_per_store.claim(
                    project_root,
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
             warning fails OPEN -- see toolguard.session_warnings.OncePer.warn),
             plus a one-time notice explaining that it can no longer be
             throttled to once per day
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
            )

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            with patch.object(once_per_store, "sqlite3", None):
                with patch("builtins.print") as mock_print:
                    result = check_and_warn_divergence(project_root, takeover_config)

            self.assertIn("Bash(git push:*)", result.divergent_patterns)
            printed = " ".join(
                str(c.args[0]) for c in mock_print.call_args_list if c.args
            )
            self.assertIn("sqlite3 is unavailable", printed)
            self.assertIn("the configuration divergence warning", printed)


class TestCheckAndWarnDivergenceExceptionSafety(_IsolatedStoreMixin, unittest.TestCase):
    """TOO-45 follow-up defect 1 regression: a crash must not leak the claim."""

    def test_exception_during_analysis_leaves_period_unclaimed(self):
        """
        Given load_configuration raises during the analysis phase (e.g. a
            malformed config file), before any warning is ever produced
        When check_and_warn_divergence is called
        Then the exception propagates AND a subsequent, successful call the
             same day can still detect and report divergence -- the crash
             must not have consumed the day's warning slot
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
            )

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}
            boom = RuntimeError("malformed config file")

            with patch(
                "toolguard.config_divergence.load_configuration", side_effect=boom
            ):
                with self.assertRaises(RuntimeError):
                    check_and_warn_divergence(project_root, takeover_config)

            result = check_and_warn_divergence(project_root, takeover_config)

            self.assertIn("Bash(git push:*)", result.divergent_patterns)
            self.assertIsNotNone(result.warning_message)


class TestDivergenceCheckCreatesNoStorageWhenNothingToReport(
    _IsolatedStoreMixin, unittest.TestCase
):
    """TOO-45 follow-up defect 2 regression."""

    def test_no_divergence_creates_no_legacy_logs_dir_or_db(self):
        """
        Given a project with matching native and toolguard permissions (no
            divergence) and a project logs directory that does not yet exist
        When check_and_warn_divergence runs -- this is what every hook
            invocation calls, regardless of whether takeover mode is on
        Then the project's logs directory is never created -- a healthy,
             non-diverging project must not gain a logs/ directory or claim
             database it never asked for
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            logs_dir = project_root / "logs"
            (project_root / "pyproject.toml").touch()

            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            config = {"permissions": {"allow": ["Bash(git status:*)"]}}
            settings_path.write_text(json.dumps(config))

            hook_path = project_root / ".claude" / "toolguard_hook.json"
            hook_path.write_text(json.dumps(config))

            takeover_config = {"enabled": False, "ignored_allow_patterns": []}

            result = check_and_warn_divergence(project_root, takeover_config)

            self.assertEqual(result.divergent_patterns, [])
            self.assertFalse(logs_dir.exists())


class TestConcurrentDivergenceWarning(_IsolatedStoreMixin, unittest.TestCase):
    """Two processes racing the new claim-immediately-before-the-print ordering."""

    def test_two_processes_only_one_warns(self):
        """
        Given two separate OS processes, both able to detect the same
            divergent pattern in a shared project, racing
            check_and_warn_divergence against the same logs_dir,
            synchronized via a barrier file
        When both processes run concurrently
        Then exactly one reports a warning_message and the other reports
             none -- claiming only immediately before the stderr notice
             still closes the race
        """
        with TemporaryDirectory() as tmpdir:
            project_root = Path(tmpdir)
            barrier = Path(tmpdir) / "go"
            # Each subprocess is a fresh interpreter, outside this suite's
            # own guard machinery -- it MUST isolate the shared store itself,
            # or it would touch the developer's real ~/.toolguard/once_per.db.
            store_path = Path(tmpdir) / "once_per.db"

            (project_root / "pyproject.toml").touch()
            settings_path = project_root / ".claude" / "settings.local.json"
            settings_path.parent.mkdir(parents=True)
            settings_path.write_text(
                json.dumps({"permissions": {"allow": ["Bash(git push:*)"]}})
            )

            script = (
                "import sys, time\n"
                "from pathlib import Path\n"
                "from toolguard import once_per_store\n"
                "from toolguard.config_divergence import check_and_warn_divergence\n"
                "once_per_store._STORE_PATH = Path(sys.argv[3])\n"
                "project_root = Path(sys.argv[1])\n"
                "barrier = Path(sys.argv[2])\n"
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
                subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(project_root),
                        str(barrier),
                        str(store_path),
                    ],
                    cwd=str(_REPO_ROOT),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for _ in range(2)
            ]

            # Give both children time to reach the busy-wait loop, then release them together.
            time.sleep(0.3)
            barrier.touch()

            outputs = []
            for proc in procs:
                stdout, stderr = proc.communicate(timeout=15)
                self.assertEqual(proc.returncode, 0, msg=stderr)
                outputs.append(stdout.strip())

            self.assertEqual(sorted(outputs), ["0", "1"])


if __name__ == "__main__":
    unittest.main()
