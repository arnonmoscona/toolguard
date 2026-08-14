"""Unit tests for toolguard.api: the side-effect-free decide() primitive."""

import dataclasses
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from test.unit._real_log_dir_guard import get_leak_events
from toolguard.api import _decide_bash, decide
from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.config_types import RuntimeVerdict
from toolguard.file_matching import check_file_path_hard_deny
from toolguard.resolve import (
    UnitVerdict,
    resolve_bash_permission_detailed,
    resolve_file_path_permission_detailed,
)


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


class TestDecideSimpleBash(unittest.TestCase):
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
        Then the verdict is 'deny' (deny checked first within a level),
            attributed to the deny pattern at the project level -- the
            fail-closed empty-extraction deny carries no matched_rule, so the
            two are distinguishable
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
        self.assertEqual("rm -rf:*", decision.matched_rule)
        self.assertIsNotNone(decision.provenance)
        self.assertEqual("project", decision.provenance.level)

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
        Then the verdict is 'deny' (hard-deny cannot be overridden by any
            allow), attributed to the hard_deny pattern with no provenance --
            the pool is shared across levels, and the fail-closed
            empty-extraction deny would name no rule at all
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
        self.assertEqual("rm -rf:*", decision.matched_rule)
        self.assertIsNone(decision.provenance)

    @staticmethod
    def _carve_out_config(carve_out):
        """A hard_deny of 'rm -rf:*' with *carve_out* as its only exemption."""
        return _make_config(
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
                            "allow": [carve_out],
                        },
                    },
                )
            ]
        )

    def test_hard_deny_carve_out_exempts_command(self):
        """
        Given a hard_deny that blocks 'rm -rf:*' with a '[glob]' carve-out for
            'rm -rf /tmp/*'
        When decide is called with 'rm -rf /tmp/foo' and with 'rm -rf /etc'
        Then the first is 'allow' (the carve-out exempts it, so the allow rule
            'rm:*' decides) and the second is still hard-denied
        """

        config = self._carve_out_config("Bash([glob]rm -rf /tmp/*)")
        exempted = decide(config, "Bash", "rm -rf /tmp/foo")
        self.assertEqual("allow", exempted.decision)
        self.assertEqual("rm:*", exempted.matched_rule)

        uncarved = decide(config, "Bash", "rm -rf /etc")
        self.assertEqual("deny", uncarved.decision)
        self.assertEqual("rm -rf:*", uncarved.matched_rule)

    def test_hard_deny_carve_out_stops_at_the_path_boundary(self):
        """
        Given the same hard_deny with the prefix-form carve-out
            'rm -rf /tmp:*'
        When decide is called with 'rm -rf /tmpfoo' -- a DIFFERENT path that
            merely shares the carve-out's last token as a text prefix
        Then the verdict is 'deny': a carve-out for /tmp must not exempt
            /tmpfoo
        """

        config = self._carve_out_config("Bash(rm -rf /tmp:*)")
        decision = decide(config, "Bash", "rm -rf /tmpfoo")
        self.assertEqual("deny", decision.decision)
        self.assertEqual("rm -rf:*", decision.matched_rule)


class TestDecideCompoundBash(unittest.TestCase):
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


class TestDecideFilePath(unittest.TestCase):
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
        self.assertEqual("[glob]/home/*/project/.env", decision.matched_rule)
        self.assertEqual("project", decision.provenance.level)

    def test_file_path_hard_deny_blocks_path_and_names_its_pattern(self):
        """
        Given a config with Read allow='*' and '[glob]/etc/**' in hard_deny.deny
        When decide is called for Read on '/etc/passwd'
        Then the verdict is 'deny', and because the file-path resolver leaves
            matched_rule None on the hard-deny branch, the pattern that did it
            is read back from check_file_path_hard_deny instead
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Read(*)"],
                            "deny": [],
                        },
                        "hard_deny": {
                            "deny": ["Read([glob]/etc/**)"],
                            "allow": [],
                        },
                    },
                )
            ]
        )
        decision = decide(config, "Read", "/etc/passwd")
        self.assertEqual("deny", decision.decision)
        self.assertIsNone(decision.provenance)

        hard = check_file_path_hard_deny("Read", "/etc/passwd", config, True)
        self.assertIsNotNone(hard)
        self.assertEqual("deny", hard.decision)
        self.assertEqual("[glob]/etc/**", hard.matched_pattern)

    def test_write_tool_uses_the_file_path_branch(self):
        """
        Given a config whose only rule is a Write allow glob under ~/projects/
        When decide is called with tool='Write' and a path under it
        Then the verdict is 'allow' -- Write is routed to the file-path
            resolver, not the Bash one, which would find no Bash rule and ask
        """

        home = str(Path.home())
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": [f"Write([glob]{home}/projects/**)"],
                            "deny": [],
                        }
                    },
                )
            ]
        )
        decision = decide(config, "Write", f"{home}/projects/notes.md")
        self.assertEqual("allow", decision.decision)
        self.assertEqual(f"[glob]{home}/projects/**", decision.matched_rule)
        self.assertEqual("Write", decision.tool)

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


class TestDecideSideEffectFree(unittest.TestCase):
    """Tests that decide() has no logging or process-exit side effects."""

    def test_decide_does_not_write_to_log_files(self):
        """
        Given TOOLGUARD_LOG_DIR pointing at a fresh empty directory -- the
            directory a decide() that logged would actually resolve, unlike an
            anonymous temp directory it is never told about
        When decide is called several times (simulating a replay scenario)
        Then that directory stays empty, and the suite's real-log-dir guard
            records no suppressed write -- which covers the other route, a
            decide() resolving the repository's own logs/ directory
        """

        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {
                            "allow": ["Bash(ls:*)"],
                            "deny": ["Bash(rm -rf:*)"],
                        }
                    },
                )
            ]
        )
        log_dir = Path(self.enterContext(tempfile.TemporaryDirectory())) / "logs"
        log_dir.mkdir()
        self.enterContext(patch.dict(os.environ, {"TOOLGUARD_LOG_DIR": str(log_dir)}))
        leaks_before = len(get_leak_events())

        decide(config, "Bash", "ls -la")
        decide(config, "Bash", "whoami")
        decide(config, "Bash", "rm -rf /")
        decide(config, "Read", "/etc/passwd")

        self.assertEqual([], sorted(log_dir.rglob("*")))
        self.assertEqual(leaks_before, len(get_leak_events()))

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
        Given a config allowing 'git:*' and the command 'git status'
        When decide is called
        Then it returns a RuntimeVerdict whose tool, target and reason echo the
            call, and whose decision is the 'allow' this fixture must produce
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
        self.assertEqual("allow", result.decision)
        self.assertEqual("git:*", result.matched_rule)
        self.assertIn("git:*", result.reason)


class TestProvenanceRegression(unittest.TestCase):
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
        Then RuntimeVerdict.sub_matches[0].matched_rule is the hard-deny
             PATTERN, wrapper-stripped -- not the command, which shares its
             leading text -- and sub_matches[0].provenance is None (hard-deny
             is pooled)
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
        self.assertEqual("rm -rf:*", sm.matched_rule)
        self.assertIsNone(sm.provenance)


class TestDecideAdditionalContext(unittest.TestCase):
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
            hardcoded 'Bash', and a rule the command genuinely matches (so
            reason, matched_rule and provenance are all populated and a lost
            one is observable)
        When _decide_bash is called
        Then the returned verdict's tool field is the caller's own tool name,
             and putting 'Bash' back yields a verdict equal in EVERY field to
             the resolver's own un-overridden result
        """
        config = _make_config(
            [("project", "toolguard_hook", {"permissions": {"allow": ["Bash(ls *)"]}})]
        )
        hard_deny_deny, hard_deny_allow = config.hard_deny("Bash")
        baseline = resolve_bash_permission_detailed(
            "ls -la", config, True, hard_deny_deny, hard_deny_allow
        )
        self.assertEqual("Bash", baseline.tool)
        self.assertEqual("ls *", baseline.matched_rule)
        self.assertIsNotNone(baseline.provenance)

        result = _decide_bash(config, "mcp__terminal__run", "ls -la", True)
        self.assertEqual("mcp__terminal__run", result.tool)
        self.assertEqual("allow", result.decision)
        self.assertEqual(baseline, dataclasses.replace(result, tool="Bash"))

    def test_mcp_terminal_tool_is_still_subject_to_the_bash_hard_deny_pool(self):
        """
        Given a Bash hard_deny of 'rm -rf:*' and an MCP terminal tool name
        When decide is called with that tool name and 'rm -rf /'
        Then the verdict is 'deny' naming the hard_deny pattern: the pool is
            looked up under 'Bash', not under the caller's own tool name,
            which has no rules of its own
        """
        config = _make_config(
            [
                (
                    "project",
                    "toolguard_hook",
                    {
                        "permissions": {"allow": ["Bash(rm:*)"], "deny": []},
                        "hard_deny": {"deny": ["Bash(rm -rf:*)"], "allow": []},
                    },
                )
            ]
        )
        decision = decide(config, "mcp__terminal__run", "rm -rf /")
        self.assertEqual("deny", decision.decision)
        self.assertEqual("rm -rf:*", decision.matched_rule)
        self.assertEqual("mcp__terminal__run", decision.tool)


class TestDecideRoutesWithoutAddingLogic(unittest.TestCase):
    """decide() is a router: it picks a resolver and forwards its arguments
    unchanged. Anything it drops or rewrites on the way is a defect here."""

    CONTENT = {
        "permissions": {
            "allow": [
                r"Bash([regex]^git\s+status$)",
                r"Read([regex]^/tmp/[a-z]+\.txt$)",
            ],
            "deny": ["Bash(rm -rf:*)"],
        },
        "hard_deny": {"deny": ["Bash(curl:*)"], "allow": []},
    }

    def setUp(self):
        """One config carrying a Bash and a file rule of every kind used below."""
        self.config = _make_config([("project", "toolguard_hook", self.CONTENT)])

    def test_bash_decision_equals_the_resolver_called_directly(self):
        """
        Given a config with Bash allow, deny and hard_deny rules
        When decide() and resolve_bash_permission_detailed() are given the same
            command, extended_syntax and the config's own Bash hard-deny pools
        Then the two verdicts are equal field for field, for a rule match, an
            unmatched command and a hard-denied command alike
        """
        hard_deny_deny, hard_deny_allow = self.config.hard_deny("Bash")
        for command in ("git status", "whoami", "curl http://x"):
            with self.subTest(command=command):
                self.assertEqual(
                    resolve_bash_permission_detailed(
                        command, self.config, True, hard_deny_deny, hard_deny_allow
                    ),
                    decide(self.config, "Bash", command),
                )

    def test_file_path_decision_equals_the_resolver_called_directly(self):
        """
        Given the same config with a Read rule
        When decide() and resolve_file_path_permission_detailed() are given the
            same tool, path and extended_syntax
        Then the two verdicts are equal field for field, for each file tool
        """
        for tool in ("Read", "Write", "Edit"):
            for path in ("/tmp/abc.txt", "/etc/passwd"):
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(
                        resolve_file_path_permission_detailed(
                            tool, path, self.config, True
                        ),
                        decide(self.config, tool, path),
                    )

    def test_extended_syntax_false_reaches_the_bash_matcher(self):
        """
        Given a Bash allow rule written with a '[regex]' prefix
        When decide() is called with extended_syntax=False
        Then the prefix is not honoured, so the command no longer matches and
            the verdict falls back to 'ask' -- where extended_syntax=True
            allows it and names the rule
        """
        honoured = decide(self.config, "Bash", "git status", True)
        self.assertEqual("allow", honoured.decision)
        self.assertEqual(r"[regex]^git\s+status$", honoured.matched_rule)

        opted_out = decide(self.config, "Bash", "git status", False)
        self.assertEqual("ask", opted_out.decision)
        self.assertIsNone(opted_out.matched_rule)

    def test_extended_syntax_false_reaches_the_file_path_matcher(self):
        """
        Given a Read allow rule written with a '[regex]' prefix
        When decide() is called with extended_syntax=False
        Then the prefix is not honoured and the verdict falls back to 'ask' --
            where extended_syntax=True allows it and names the rule
        """
        honoured = decide(self.config, "Read", "/tmp/abc.txt", True)
        self.assertEqual("allow", honoured.decision)
        self.assertEqual(r"[regex]^/tmp/[a-z]+\.txt$", honoured.matched_rule)

        opted_out = decide(self.config, "Read", "/tmp/abc.txt", False)
        self.assertEqual("ask", opted_out.decision)
        self.assertIsNone(opted_out.matched_rule)
