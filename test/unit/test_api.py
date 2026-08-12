"""Unit tests for toolguard.api: the side-effect-free decide() primitive."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from toolguard.api import _decide_bash, decide
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.config_types import RuntimeVerdict
from toolguard.resolve import UnitVerdict


def _make_config(layers_content):
    """Build a Configuration from (level, source_type, content) tuples; specificity is the index."""
    layers = []
    for i, (level, source_type, content) in enumerate(layers_content):
        prov = Provenance(
            level=level,
            source_type=source_type,
            file_format="toml",
            path=Path(f"/fake/{level}/{source_type}"),
            specificity=i,
        )
        layers.append(ConfigLayer(provenance=prov, content=MappingProxyType(content)))
    return Configuration(layers=tuple(layers), start_dir=None)


class _IsolatedEnvTestCase(unittest.TestCase):
    """Base: removes CLAUDE_SETTINGS_PATH for isolation."""

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("CLAUDE_SETTINGS_PATH", None)
        self.addCleanup(self._env_patch.stop)


class TestDecideSimpleBash(_IsolatedEnvTestCase):
    """Tests for decide() with simple Bash commands."""

    def test_allow_pattern_matches_command(self):
        """
        Given a config with Bash allow pattern 'ls:*'
        When decide is called with tool='Bash' and command='ls -la'
        Then the verdict is 'allow'
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "ls -la")
        self.assertEqual("allow", decision.decision)
        self.assertEqual("Bash", decision.tool)
        self.assertEqual("ls -la", decision.target)

    def test_no_allow_pattern_yields_no_match_fallback(self):
        """
        Given a config with only an allow pattern for Bash (no deny)
        When decide is called with tool='Bash' and a command not covered by
            the allow pattern
        Then the verdict is 'ask' (TOO-15 default no_match_fallback: no match
            prompts rather than silently denying)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "whoami")
        self.assertEqual("ask", decision.decision)

    def test_deny_pattern_blocks_command(self):
        """
        Given a config with 'rm -rf:*' in deny and 'rm:*' in allow
        When decide is called with 'rm -rf /tmp/foo'
        Then the verdict is 'deny' (deny checked first within a level)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(rm:*)"],
                            "deny": ["Bash(rm -rf:*)"],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "rm -rf /tmp/foo")
        self.assertEqual("deny", decision.decision)

    def test_more_specific_allow_at_project_level_wins_over_user_deny(self):
        """
        Given a user-level config that denies 'git push:*' and a project-level
        config that allows 'git push:*'
        When decide is called with 'git push origin main'
        Then the verdict is 'allow' (more-specific-wins: project beats user)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git push:*)"],
                            "deny": [],
                        }
                    },
                ),
                (
                    "user",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [],
                            "deny": ["Bash(git push:*)"],
                        }
                    },
                ),
            ]
        )
        decision = decide(config, "Bash", "git push origin main")
        self.assertEqual("allow", decision.decision)

    def test_hard_deny_cannot_be_overridden(self):
        """
        Given a config with 'rm -rf:*' in hard_deny.deny and 'rm:*' in allow
        When decide is called with 'rm -rf /'
        Then the verdict is 'deny' (hard-deny cannot be overridden by any allow)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(rm:*)"],
                            "deny": [],
                        },
                        "hard_deny": {
                            "deny": ["Bash(rm -rf:*)"],
                            "allow": [],
                        },
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "rm -rf /")
        self.assertEqual("deny", decision.decision)

    def test_hard_deny_carve_out_exempts_command(self):
        """
        Given a hard_deny that blocks 'rm -rf:*' but has a carve-out for
        'rm -rf /tmp:*'
        When decide is called with 'rm -rf /tmp/foo'
        Then the verdict is 'allow' (hard-deny carve-out exempts the path)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(rm:*)"],
                            "deny": [],
                        },
                        "hard_deny": {
                            "deny": ["Bash(rm -rf:*)"],
                            "allow": ["Bash(rm -rf /tmp:*)"],
                        },
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "rm -rf /tmp/foo")
        self.assertEqual("allow", decision.decision)


class TestDecideCompoundBash(_IsolatedEnvTestCase):
    """Tests for decide() with compound Bash commands."""

    def test_compound_all_allowed_yields_allow(self):
        """
        Given a config that allows 'git:*' and 'ls:*'
        When decide is called with the compound command 'git status && ls -la'
        Then the verdict is 'allow' (both sub-commands are allowed)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "git status && ls -la")
        self.assertEqual("allow", decision.decision)

    def test_compound_one_unmatched_yields_ask(self):
        """
        Given a config that allows 'git:*' but not 'whoami'
        When decide is called with 'git status && whoami'
        Then the verdict is 'ask' (any sub-command not fully allowed drags the
            whole compound down; the unmatched 'whoami' sub-command resolves
            via the TOO-15 default no_match_fallback, and compound strictness
            propagates that 'ask' to the overall verdict)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Bash", "git status && whoami")
        self.assertEqual("ask", decision.decision)


class TestDecideFilePath(_IsolatedEnvTestCase):
    """Tests for decide() with file-path tools (Read, Write, Edit)."""

    def test_read_allowed_by_glob_pattern(self):
        """
        Given a config with Read allow pattern '[glob]~/projects/**'
        When decide is called with tool='Read' and a path under ~/projects/
        Then the verdict is 'allow'
        """

        home = str(Path.home())
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [f"Read([glob]{home}/projects/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Read", f"{home}/projects/foo/bar.py")
        self.assertEqual("allow", decision.decision)

    def test_read_asks_when_no_allow_pattern_matches(self):
        """
        Given a config with Read allow pattern for ~/projects/ only
        When decide is called with tool='Read' and a path outside that directory
        Then the verdict is 'ask' (TOO-15 default no_match_fallback)
        """

        home = str(Path.home())
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [f"Read([glob]{home}/projects/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Read", "/etc/passwd")
        self.assertEqual("ask", decision.decision)

    def test_file_path_deny_pattern_blocks_path(self):
        """
        Given a config with Read allow='*' and deny='[glob]/home/*/project/.env'
            (an ABSOLUTE glob pattern -- deliberately not anchored to a project
            root, so it matches the target path directly and unambiguously)
        When decide is called for Read on '/home/user/project/.env'
        Then the verdict is 'deny' (deny-first within a level)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read(*)"],
                            "deny": ["Read([glob]/home/*/project/.env)"],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Read", "/home/user/project/.env")
        self.assertEqual("deny", decision.decision)

    def test_edit_tool_uses_same_file_path_logic(self):
        """
        Given a config with Edit allow pattern '[glob]~/projects/**'
        When decide is called with tool='Edit' and a path under ~/projects/
        Then the verdict is 'allow' (Edit uses same file-path logic as Read)
        """

        home = str(Path.home())
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [f"Edit([glob]{home}/projects/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Edit", f"{home}/projects/myfile.py")
        self.assertEqual("allow", decision.decision)


class TestDecideSideEffectFree(_IsolatedEnvTestCase):
    """Tests that decide() has no logging or process-exit side effects."""

    def test_decide_does_not_write_to_log_files(self):
        """
        Given a config with allow and deny patterns
        When decide is called multiple times (simulating a replay scenario)
        Then no log files are written (no side effects from the decision primitive)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            logs_dir = Path(tmpdir)
            initial_files = set(logs_dir.iterdir())
            decide(config, "Bash", "ls -la")
            decide(config, "Bash", "whoami")
            decide(config, "Bash", "git status")
            after_files = set(logs_dir.iterdir())
            self.assertEqual(initial_files, after_files)

    def test_decide_does_not_call_sys_exit(self):
        """
        Given a config that allows 'ls:*' only (no deny)
        When decide is called with an unmatched command
        Then sys.exit is never called (no process exit side effect) and the
            decision returns normally with the TOO-15 default 'ask' verdict
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        original_exit = sys.exit
        exit_called = []
        sys.exit = lambda code=0: exit_called.append(code)
        try:
            decision = decide(config, "Bash", "rm -rf /")
        finally:
            sys.exit = original_exit
        self.assertEqual([], exit_called)
        self.assertEqual("ask", decision.decision)

    def test_decide_returns_decision_dataclass(self):
        """
        Given any valid configuration and command
        When decide is called
        Then it returns a RuntimeVerdict instance with tool, target, decision,
            and reason fields
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status")
        self.assertIsInstance(result, RuntimeVerdict)
        self.assertEqual("Bash", result.tool)
        self.assertEqual("git status", result.target)
        self.assertIn(result.decision, ("allow", "ask", "deny"))
        self.assertIsInstance(result.reason, str)
        self.assertGreater(len(result.reason), 0)


class TestProvenanceRegression(_IsolatedEnvTestCase):
    """Regression guards for provenance surfacing through the decision layer."""

    def test_file_allow_provenance_is_non_none(self):
        """
        Given a config that allows Read under /tmp/**
        When decide() is called with tool='Read' and a matching path
        Then RuntimeVerdict.provenance is non-None and identifies the allowing layer
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Read", "/tmp/some/file.txt")
        self.assertEqual("allow", result.decision)
        self.assertIsNotNone(
            result.provenance,
            "provenance must be non-None for a normal (non-conflict) file allow",
        )
        self.assertEqual("project", result.provenance.level)

    def test_file_no_match_provenance_is_none(self):
        """
        Given a config that has no allow pattern covering /etc/passwd
        When decide() is called with tool='Read' and /etc/passwd
        Then RuntimeVerdict.provenance is None (no rule matched -- resolves via the
            TOO-15 default no_match_fallback 'ask')
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Read", "/etc/passwd")
        self.assertEqual("ask", result.decision)
        self.assertIsNone(result.provenance)

    def test_bash_single_allow_provenance_is_non_none(self):
        """
        Given a config that allows 'git:*' at the project level
        When decide() is called with a single allowed Bash command
        Then RuntimeVerdict.provenance is non-None and identifies the project layer
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status")
        self.assertEqual("allow", result.decision)
        self.assertIsNotNone(
            result.provenance,
            "provenance must be non-None for a matched Bash allow",
        )
        self.assertEqual("project", result.provenance.level)

    def test_bash_compound_mixed_escape_hatch_provenance_matches_matched_rule(self):
        """
        Given a config allowing 'Bash(ls)' and 'Bash(python *)' (so the
            ask-floor leaf's own truncated stub also allows) with
            undecidable_fallback set to 'allow_with_warning'
        When decide() is called with the two-leaf compound
            'python -c "print(1)" && ls' (the escape-hatch ask-floor leaf
            extracts FIRST, the genuine match 'ls' second)
        Then RuntimeVerdict.provenance is non-None and identifies the project
            layer, consistent with RuntimeVerdict.matched_rule ('ls') -- NOT None
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "undecidable_fallback": "allow_with_warning",
                        "permissions": {
                            "allow": ["Bash(ls)", "Bash(python *)"],
                            "deny": [],
                        },
                    },
                )
            ]
        )
        result = decide(config, "Bash", 'python -c "print(1)" && ls')
        self.assertEqual("allow", result.decision)
        self.assertEqual(result.matched_rule, "ls")
        self.assertIsNotNone(
            result.provenance,
            "provenance must be non-None and consistent with matched_rule",
        )
        self.assertEqual("project", result.provenance.level)

    def test_bash_compound_sub_matches_populated(self):
        """
        Given a config that allows 'git:*' and 'ls:*'
        When decide() is called with the compound command 'git status && ls -la'
        Then RuntimeVerdict.sub_matches has two entries, one per sub-command,
             each with a non-None matched_rule and provenance
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)", "Bash(ls:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status && ls -la")
        self.assertEqual("allow", result.decision)
        self.assertIsNotNone(result.sub_matches)
        self.assertEqual(2, len(result.sub_matches))

        for sm in result.sub_matches:
            self.assertIsInstance(sm, UnitVerdict)
            self.assertEqual("allow", sm.decision)
            self.assertIsNotNone(
                sm.matched_rule,
                "matched_rule must be non-None for an allowed sub-command",
            )
            self.assertIsNotNone(
                sm.provenance, "provenance must be non-None for an allowed sub-command"
            )

    def test_bash_compound_unmatched_sub_identifiable_in_sub_matches(self):
        """
        Given a config that allows 'git:*' but not 'whoami'
        When decide() is called with 'git status && whoami'
        Then RuntimeVerdict.decision is 'ask' (TOO-15 default no_match_fallback,
             propagated from the unmatched 'whoami' sub-command), sub_matches
             has two entries, and the second sub-command ('whoami') has
             decision='ask' in sub_matches
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status && whoami")
        self.assertEqual("ask", result.decision)
        self.assertIsNotNone(result.sub_matches)
        self.assertEqual(2, len(result.sub_matches))

        git_match = result.sub_matches[0]
        whoami_match = result.sub_matches[1]

        self.assertEqual("allow", git_match.decision)
        self.assertIn("git", git_match.sub_command)

        self.assertEqual("ask", whoami_match.decision)
        self.assertIn("whoami", whoami_match.sub_command)
        self.assertIsNone(whoami_match.matched_rule)
        self.assertIsNone(whoami_match.provenance)

    def test_bash_hard_deny_sub_matches_has_matched_rule(self):
        """
        Given a config with 'rm -rf:*' in hard_deny.deny
        When decide() is called with 'rm -rf /'
        Then RuntimeVerdict.sub_matches[0].matched_rule contains the hard-deny pattern
             and sub_matches[0].provenance is None (hard-deny is pooled)
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(rm:*)"],
                            "deny": [],
                        },
                        "hard_deny": {
                            "deny": ["Bash(rm -rf:*)"],
                            "allow": [],
                        },
                    },
                )
            ]
        )
        result = decide(config, "Bash", "rm -rf /")
        self.assertEqual("deny", result.decision)
        self.assertIsNotNone(result.sub_matches)
        self.assertEqual(1, len(result.sub_matches))

        sm = result.sub_matches[0]
        self.assertEqual("deny", sm.decision)
        self.assertIsNotNone(sm.matched_rule)
        self.assertIn("rm -rf", sm.matched_rule)
        self.assertIsNone(sm.provenance)


class TestDecideAdditionalContext(_IsolatedEnvTestCase):
    """RuntimeVerdict.additional_context as decide() populates it, for both branches."""

    def test_file_allow_structured_entry_surfaces_additional_context(self):
        """
        Given a Read allow structured entry for '/tmp/**' carrying
            additionalContext = 'scratch space only'
        When decide() is called with tool='Read' and a matching path
        Then RuntimeVerdict.additional_context is 'scratch space only'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Read([glob]/tmp/**)",
                                    "additionalContext": "scratch space only",
                                }
                            ],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Read", "/tmp/some/file.txt")
        self.assertEqual("allow", result.decision)
        self.assertEqual("scratch space only", result.additional_context)

    def test_file_plain_string_rule_yields_none_context(self):
        """
        Given a Read allow entry that is a plain string (no enrichment)
        When decide() is called with tool='Read' and a matching path
        Then RuntimeVerdict.additional_context is None
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read([glob]/tmp/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Read", "/tmp/some/file.txt")
        self.assertEqual("allow", result.decision)
        self.assertIsNone(result.additional_context)

    def test_bash_single_allow_structured_entry_surfaces_additional_context(self):
        """
        Given a Bash allow structured entry for 'git:*' carrying
            additionalContext = 'prefer git status --short'
        When decide() is called with tool='Bash' and a matching command
        Then RuntimeVerdict.additional_context is 'prefer git status --short'
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [
                                {
                                    "match": "Bash(git:*)",
                                    "additionalContext": "prefer git status --short",
                                }
                            ],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status")
        self.assertEqual("allow", result.decision)
        self.assertEqual("prefer git status --short", result.additional_context)

    def test_bash_plain_string_rule_yields_none_context(self):
        """
        Given a Bash allow entry that is a plain string (no enrichment)
        When decide() is called with tool='Bash' and a matching command
        Then RuntimeVerdict.additional_context is None
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(git:*)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        result = decide(config, "Bash", "git status")
        self.assertEqual("allow", result.decision)
        self.assertIsNone(result.additional_context)


class TestDecideBashToolOverride(unittest.TestCase):
    """_decide_bash's documented tool-name override (see its own docstring)."""

    def test_tool_override_replaces_only_the_tool_field(self):
        """
        Given a caller-supplied tool name that differs from the resolver's
            hardcoded 'Bash'
        When _decide_bash is called
        Then the returned verdict's tool field is the caller's own tool name,
             with every other field unchanged from the resolver's own result
        """
        config = _make_config(
            [("project", "toolguard_hook", {"permissions": {"allow": ["Bash(ls *)"]}})]
        )
        result = _decide_bash(config, "mcp__terminal__run", "ls -la", True)
        self.assertEqual(result.tool, "mcp__terminal__run")
        self.assertEqual(result.decision, "allow")
