"""Unit tests for the ``[hard_deny]`` safety valve: pooling, carve-outs, and enforcement."""

import os
import unittest
from pathlib import Path
from types import MappingProxyType
from unittest.mock import patch

from test.unit._config_isolation import ConfigIsolationMixin
from toolguard.compound import resolve_compound_permission
from toolguard.config import ConfigLayer, Configuration, Provenance, load_configuration
from toolguard.config_divergence import DivergenceCheckResult
from toolguard.hook import resolve_file_path_permission_detailed
from toolguard.permission_resolution import resolve_command_permission
from toolguard.permissions import check_hard_deny
from toolguard.rule_entry import _strip_tool_wrapper


def _write(claude_dir: Path, filename: str, content: str) -> None:
    """Create a .claude directory (if needed) and write a config file in it."""
    claude_dir.mkdir(parents=True, exist_ok=True)
    (claude_dir / filename).write_text(content)


class _IsolatedEnvTestCase(unittest.TestCase):
    """Base class that removes ``CLAUDE_SETTINGS_PATH``, which would bypass the temp hierarchy."""

    def setUp(self):
        """Remove CLAUDE_SETTINGS_PATH for the duration of each test."""
        self._env_patch = patch.dict(os.environ, {}, clear=False)
        self._env_patch.start()
        os.environ.pop("CLAUDE_SETTINGS_PATH", None)
        self.addCleanup(self._env_patch.stop)


def _layer(specificity, *, hard_deny=None, allow=None, deny=None, native=False):
    """Build one ConfigLayer at *specificity* (0 = most specific); ``native`` models Claude settings."""
    content = {}
    if hard_deny is not None:
        content["hard_deny"] = hard_deny
    if allow is not None or deny is not None:
        content["permissions"] = {"allow": allow or [], "deny": deny or []}
    source_type = "claude" if native else "toolguard_hook"
    fmt = "json" if native else "toml"
    prov = Provenance(
        "project", source_type, fmt, Path(f"/fake/{specificity}.{fmt}"), specificity
    )
    return ConfigLayer(provenance=prov, content=MappingProxyType(content))


class TestHardDenyAccessor(_IsolatedEnvTestCase):
    """Test Configuration.hard_deny pooling and tool scoping."""

    def test_hard_deny_pooled_across_multiple_levels(self):
        """
        Given two toolguard_hook levels each declaring different hard_deny.deny
            Bash patterns
        When Configuration.hard_deny('Bash') is read
        Then the returned deny pool is the UNION across both levels
        """
        config = Configuration(
            layers=(
                _layer(0, hard_deny={"deny": ["Bash(curl *)"]}),
                _layer(1, hard_deny={"deny": ["Bash(wget *)"]}),
            )
        )
        deny, allow = config.hard_deny("Bash")
        self.assertIn("curl *", deny)
        self.assertIn("wget *", deny)
        self.assertEqual(allow, ())

    def test_hard_deny_is_tool_scoped(self):
        """
        Given a hard_deny pool with both Bash and Read deny patterns
        When Configuration.hard_deny is read for each tool
        Then only that tool's patterns are returned (wrapper stripped)
        """
        config = Configuration(
            layers=(_layer(0, hard_deny={"deny": ["Bash(curl *)", "Read(/etc/**)"]}),)
        )
        bash_deny, _ = config.hard_deny("Bash")
        read_deny, _ = config.hard_deny("Read")
        self.assertEqual(bash_deny, ("curl *",))
        self.assertEqual(read_deny, ("/etc/**",))

    def test_hard_deny_ignored_in_native_claude_layers(self):
        """
        Given a NATIVE Claude settings layer carrying a hard_deny section
        When Configuration.hard_deny('Bash') is read
        Then it is ignored -- hard_deny is a toolguard extension only
        """
        config = Configuration(
            layers=(_layer(0, hard_deny={"deny": ["Bash(curl *)"]}, native=True),)
        )
        deny, allow = config.hard_deny("Bash")
        self.assertEqual(deny, ())
        self.assertEqual(allow, ())

    def test_hard_deny_empty_when_unconfigured(self):
        """
        Given a layer with no hard_deny section
        When Configuration.hard_deny is read
        Then both pools are empty
        """
        config = Configuration(layers=(_layer(0, allow=["Bash(git *)"]),))
        self.assertEqual(config.hard_deny("Bash"), ((), ()))

    def test_hard_deny_malformed_section_ignored(self):
        """
        Given a layer whose hard_deny key is not a table/dict (a malformed value)
        When Configuration.hard_deny is read
        Then the malformed section is ignored and both pools are empty
        """
        prov = Provenance("project", "toolguard_hook", "toml", Path("/fake/x.toml"), 0)
        layer = ConfigLayer(
            provenance=prov, content=MappingProxyType({"hard_deny": "not-a-table"})
        )
        config = Configuration(layers=(layer,))
        self.assertEqual(config.hard_deny("Bash"), ((), ()))


class TestHardDenyStructuredEntries(_IsolatedEnvTestCase):
    """Test structured (``{match=..., ...}``) entries in ``[hard_deny]`` and their metadata."""

    def test_hard_deny_structured_deny_entry_contributes_pattern(self):
        """
        Given a hard_deny.deny list containing a STRUCTURED entry
            ({match=..., additionalContext=...}) for Bash
        When Configuration.hard_deny('Bash') is read
        Then the structured entry's pattern is present in the returned deny
            tuple -- it is no longer silently dropped (the bug this
            increment fixes)
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": [
                            {
                                "match": "Bash(curl *)",
                                "additionalContext": "use the internal proxy instead",
                            }
                        ]
                    },
                ),
            )
        )
        deny, _allow = config.hard_deny("Bash")
        self.assertEqual(deny, ("curl *",))

    def test_hard_deny_structured_allow_entry_contributes_pattern(self):
        """
        Given a hard_deny.allow carve-out list containing a STRUCTURED entry
            for Bash
        When Configuration.hard_deny('Bash') is read
        Then the structured entry's pattern is present in the returned allow
            tuple -- the same silent-drop bug fixed for deny also applies to
            the allow carve-out
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": ["Bash(curl *)"],
                        "allow": [
                            {
                                "match": "Bash(curl localhost*)",
                                "additionalContext": "internal only",
                            }
                        ],
                    },
                ),
            )
        )
        _deny, allow = config.hard_deny("Bash")
        self.assertEqual(allow, ("curl localhost*",))

    def test_hard_deny_entries_returns_metadata_and_wrapper_intact_pattern(self):
        """
        Given a hard_deny.deny structured entry carrying additionalContext
        When Configuration.hard_deny_entries('Bash') is read
        Then the returned deny entry's .pattern is wrapper-INTACT
            ('Bash(curl *)') and its .metadata carries the additionalContext
            value
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": [
                            {
                                "match": "Bash(curl *)",
                                "additionalContext": "use the internal proxy instead",
                            }
                        ]
                    },
                ),
            )
        )
        deny_entries, allow_entries = config.hard_deny_entries("Bash")
        self.assertEqual(len(deny_entries), 1)
        self.assertEqual(deny_entries[0].pattern, "Bash(curl *)")
        self.assertEqual(
            deny_entries[0].metadata["additionalContext"],
            "use the internal proxy instead",
        )
        self.assertEqual(allow_entries, ())

    def test_hard_deny_and_hard_deny_entries_are_index_aligned(self):
        """
        Given multiple hard_deny.deny patterns (plain and structured, mixed)
            plus an allow carve-out
        When both Configuration.hard_deny and .hard_deny_entries are read for
            the same tool
        Then hard_deny()[i] is the wrapper-stripped form of
            hard_deny_entries()[i].pattern, for both deny and allow tuples
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": [
                            "Bash(wget *)",
                            {"match": "Bash(curl *)", "additionalContext": "x"},
                        ],
                        "allow": ["Bash(curl localhost*)"],
                    },
                ),
            )
        )
        deny, allow = config.hard_deny("Bash")
        deny_entries, allow_entries = config.hard_deny_entries("Bash")
        self.assertEqual(len(deny), len(deny_entries))
        self.assertEqual(len(allow), len(allow_entries))
        for pattern, entry in zip(deny, deny_entries):
            self.assertEqual(pattern, _strip_tool_wrapper(entry.pattern))
        for pattern, entry in zip(allow, allow_entries):
            self.assertEqual(pattern, _strip_tool_wrapper(entry.pattern))

    def test_hard_deny_pooling_dedup_first_occurrence_metadata_wins(self):
        """
        Given the SAME hard_deny.deny pattern declared at two levels, where
            only the MORE-SPECIFIC (level 0) occurrence carries
            additionalContext metadata and the less-specific (level 1)
            occurrence is a plain string
        When Configuration.hard_deny_entries('Bash') is read
        Then the pool contains exactly one entry for that pattern, and it is
            the metadata-carrying, most-specific occurrence (consistent with
            today's first-occurrence-wins pooling)
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": [
                            {
                                "match": "Bash(curl *)",
                                "additionalContext": "most specific",
                            }
                        ]
                    },
                ),
                _layer(1, hard_deny={"deny": ["Bash(curl *)"]}),
            )
        )
        deny_entries, _allow_entries = config.hard_deny_entries("Bash")
        self.assertEqual(len(deny_entries), 1)
        self.assertEqual(deny_entries[0].metadata["additionalContext"], "most specific")

    def test_hard_deny_native_layer_structured_entry_contributes_nothing(self):
        """
        Given a NATIVE Claude settings layer whose hard_deny.deny holds a
            STRUCTURED entry for Bash
        When Configuration.hard_deny_entries and .hard_deny are read
        Then both return empty -- native layers are skipped wholesale,
            before the structured entry is ever normalized
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    hard_deny={
                        "deny": [{"match": "Bash(curl *)", "additionalContext": "x"}]
                    },
                    native=True,
                ),
            )
        )
        self.assertEqual(config.hard_deny_entries("Bash"), ((), ()))
        self.assertEqual(config.hard_deny("Bash"), ((), ()))

    def test_hard_deny_malformed_entry_does_not_raise(self):
        """
        Given a hard_deny.deny list containing a malformed element (an int,
            which normalize_entry rejects with an error Issue)
        When Configuration.hard_deny and .hard_deny_entries are read
        Then no exception is raised and the malformed element contributes
            nothing to either pool
        """
        config = Configuration(
            layers=(_layer(0, hard_deny={"deny": [123, "Bash(curl *)"]}),)
        )
        deny, _allow = config.hard_deny("Bash")
        self.assertEqual(deny, ("curl *",))
        deny_entries, _allow_entries = config.hard_deny_entries("Bash")
        self.assertEqual(len(deny_entries), 1)

    def test_hard_deny_non_list_deny_value_tolerated(self):
        """
        Given a hard_deny section whose 'deny' value is not a list (a
            scalar misconfiguration)
        When Configuration.hard_deny is read
        Then it is tolerated as empty rather than raising
        """
        config = Configuration(layers=(_layer(0, hard_deny={"deny": "not-a-list"}),))
        self.assertEqual(config.hard_deny("Bash"), ((), ()))


class TestHardDenyCommand(_IsolatedEnvTestCase):
    """Test the unoverridable hard-deny behaviour for commands."""

    def _resolve(self, config, command):
        """Resolve a command, checking hard_deny first then the cascade; return (decision, reason)."""
        hd_deny, hd_allow = config.hard_deny("Bash")

        def _resolve_one(sub):
            hard = check_hard_deny(sub, list(hd_deny), list(hd_allow))
            if hard is not None:
                return hard.decision, hard.reason, None

            resolved = resolve_command_permission(config, "Bash", sub)
            return resolved.decision, resolved.reason, resolved.additional_context

        _verdict = resolve_compound_permission(command, _resolve_one)
        decision, reason, _context = (
            _verdict.decision,
            _verdict.reason,
            _verdict.additional_context,
        )
        return decision, reason

    def test_hard_deny_overrides_more_specific_allow(self):
        """
        Given a MORE-SPECIFIC level that allows 'curl *' and a less-specific level
            that hard-denies 'curl *'
        When 'curl http://x' is resolved
        Then the hard_deny wins and the command is denied (unoverridable),
            despite the more-specific allow
        """
        config = Configuration(
            layers=(
                _layer(0, allow=["Bash(curl *)"]),
                _layer(1, hard_deny={"deny": ["Bash(curl *)"]}),
            )
        )
        decision, reason = self._resolve(config, "curl http://x")
        self.assertEqual(decision, "deny")
        self.assertIn("hard_deny", reason)
        self.assertIn("cannot be overridden", reason)

    def test_hard_deny_allow_carveout_exempts_command(self):
        """
        Given hard_deny.deny 'curl *' with a hard_deny.allow carve-out
            'curl localhost*' and a normal allow for 'curl *'
        When 'curl localhost:8080' is resolved
        Then the carve-out exempts it from the hard deny and the normal cascade
            allows it
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    allow=["Bash(curl *)"],
                    hard_deny={
                        "deny": ["Bash(curl *)"],
                        "allow": ["Bash(curl localhost*)"],
                    },
                ),
            )
        )
        decision, _reason = self._resolve(config, "curl localhost:8080")
        self.assertEqual(decision, "allow")

    def test_hard_deny_allow_carveout_does_not_exempt_other_commands(self):
        """
        Given hard_deny.deny 'curl *' with a hard_deny.allow carve-out
            'curl localhost*'
        When a NON-carved-out 'curl http://evil' is resolved
        Then it is still hard-denied
        """
        config = Configuration(
            layers=(
                _layer(
                    0,
                    allow=["Bash(curl *)"],
                    hard_deny={
                        "deny": ["Bash(curl *)"],
                        "allow": ["Bash(curl localhost*)"],
                    },
                ),
            )
        )
        decision, _reason = self._resolve(config, "curl http://evil")
        self.assertEqual(decision, "deny")

    def test_hard_deny_at_ancestor_blocks_project_allow(self):
        """
        Given a hard_deny declared at the least-specific (user) level and a
            project-level normal allow for the same command
        When the command is resolved
        Then the ancestor hard_deny still blocks the project allow
        """
        config = Configuration(
            layers=(
                _layer(0, allow=["Bash(rm -rf *)"]),
                _layer(1),
                _layer(2, hard_deny={"deny": ["Bash(rm -rf *)"]}),
            )
        )
        decision, _reason = self._resolve(config, "rm -rf /tmp/x")
        self.assertEqual(decision, "deny")

    def test_compound_hard_denied_if_any_subcommand_hard_denied(self):
        """
        Given a compound 'git status && curl http://x' where curl is hard-denied
            and git is allowed
        When the compound is resolved
        Then the whole compound is denied because one sub-command is hard-denied
        """
        config = Configuration(
            layers=(
                _layer(0, allow=["Bash(git *)", "Bash(curl *)"]),
                _layer(1, hard_deny={"deny": ["Bash(curl *)"]}),
            )
        )
        decision, _reason = self._resolve(config, "git status && curl http://x")
        self.assertEqual(decision, "deny")

    def test_no_hard_deny_leaves_cascade_unchanged(self):
        """
        Given no [hard_deny] configured and a normal allow for 'git *'
        When 'git status' is resolved
        Then Phase 2 behaviour is unchanged: the command is allowed
        """
        config = Configuration(layers=(_layer(0, allow=["Bash(git *)"]),))
        decision, _reason = self._resolve(config, "git status")
        self.assertEqual(decision, "allow")

    def test_hard_deny_not_weakened_by_broken_config_ask_floor(self):
        """
        TOO-19: Given a hard_deny match for 'rm -rf /' AND a Configuration
            recording a broken (unparseable) config file elsewhere
        When 'rm -rf /' is resolved (hard_deny checked first, same as
            resolve_bash_permission_detailed does in production)
        Then the decision is still 'deny' -- the fail-open ASK floor never
            reaches hard_deny (it is checked and returned BEFORE
            resolve_command_permission is ever called), so hard_deny
            protection is never weakened to 'ask' even while the config is
            broken
        """
        broken = Path("/fake/broken.toml")
        config = Configuration(
            layers=(_layer(0, hard_deny={"deny": ["Bash(rm -rf *)"]}),),
            parse_failures=((broken, "bad TOML"),),
        )
        decision, reason = self._resolve(config, "rm -rf /")
        self.assertEqual(decision, "deny")
        self.assertIn("hard_deny", reason)
        self.assertIn("cannot be overridden", reason)

    def test_non_hard_denied_command_clamped_to_ask_by_broken_config(self):
        """
        TOO-19: Given a normal allow for 'git *' (no hard_deny match) AND a
            Configuration recording a broken config file
        When 'git status' is resolved
        Then the decision is 'ask' (clamped, not silently allowed) and the
            reason names the broken file -- this is the actual security fix:
            a command that would otherwise have been allowed now requires a
            human decision while the config is broken
        """
        broken = Path("/fake/broken.toml")
        config = Configuration(
            layers=(_layer(0, allow=["Bash(git *)"]),),
            parse_failures=((broken, "bad TOML"),),
        )
        decision, reason = self._resolve(config, "git status")
        self.assertEqual(decision, "ask")
        self.assertIn(str(broken), reason)


class TestCheckHardDenyUnit(unittest.TestCase):
    """Direct unit tests for permissions.check_hard_deny."""

    def test_returns_none_when_no_deny_patterns(self):
        """
        Given an empty hard_deny.deny list
        When check_hard_deny runs
        Then it returns None (fall through to the normal cascade)
        """
        self.assertIsNone(check_hard_deny("curl x", [], []))

    def test_returns_none_when_no_deny_match(self):
        """
        Given a command that matches no hard_deny.deny pattern
        When check_hard_deny runs
        Then it returns None
        """
        self.assertIsNone(check_hard_deny("git status", ["curl *"], []))

    def test_denies_on_deny_match_without_carveout(self):
        """
        Given a command matching a hard_deny.deny pattern and no carve-out
        When check_hard_deny runs
        Then it returns a deny decision with an unoverridable reason and the
            matched pattern as its own field (TOO-19 code review m3; a
            LevelMatch field as of TOO-45 R1f)
        """
        result = check_hard_deny("curl http://x", ["curl *"], [])
        self.assertIsNotNone(result)
        self.assertEqual(result.decision, "deny")
        self.assertIn("cannot be overridden", result.reason)
        self.assertEqual(result.matched_pattern, "curl *")

    def test_carveout_returns_none(self):
        """
        Given a command matching both a hard_deny.deny pattern and a hard_deny.allow
            carve-out
        When check_hard_deny runs
        Then it returns None (the carve-out exempts the command)
        """
        self.assertIsNone(
            check_hard_deny("curl localhost", ["curl *"], ["curl localhost*"])
        )


class TestHardDenyFilePath(ConfigIsolationMixin, _IsolatedEnvTestCase):
    """Test the unoverridable hard-deny behaviour for Read/Write/Edit."""

    def _build_config(self, home, project, target_level, hard_deny_toml, project_allow):
        """Write a hard_deny section at the chosen level plus a project-level allow."""
        target = {
            "project": project / ".claude",
            "user": home / ".claude",
        }[target_level]
        _write(target, "toolguard_hook.toml", hard_deny_toml)
        if target_level != "project":
            _write(
                project / ".claude",
                "toolguard_hook.toml",
                f"[permissions]\nallow = {project_allow}\n",
            )

    def test_read_hard_deny_overrides_project_allow(self):
        """
        Given a project-level normal allow for Read of '**' and a user-level
            hard_deny denying Read of '**/.env'
        When a Read of <project>/.env is resolved
        Then the hard_deny wins and the read is denied (unoverridable)
        """
        home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Read(**)"]\n',
        )
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            '[hard_deny]\ndeny = ["Read(**/.env)"]\n',
        )

        target_file = str(project / ".env")
        config = load_configuration(project)
        result = resolve_file_path_permission_detailed("Read", target_file, config)
        self.assertEqual(result.decision, "deny")
        self.assertIn("hard_deny", result.reason)

    def test_write_hard_deny_allow_carveout(self):
        """
        Given a hard_deny denying Write of '**' under the project with an allow
            carve-out for Write of '**/scratch/**'
        When a Write of <project>/scratch/x is resolved
        Then the carve-out exempts it and the normal allow permits the write
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Write(**)"]\n'
            '[hard_deny]\ndeny = ["Write(**)"]\nallow = ["Write(**/scratch/**)"]\n',
        )

        allowed_file = str(project / "scratch" / "x.txt")
        denied_file = str(project / "src" / "y.txt")
        config = load_configuration(project)
        allow_result = resolve_file_path_permission_detailed(
            "Write", allowed_file, config
        )
        deny_result = resolve_file_path_permission_detailed(
            "Write", denied_file, config
        )
        self.assertEqual(allow_result.decision, "allow")
        self.assertEqual(deny_result.decision, "deny")

    def test_edit_hard_deny_relative_pattern_anchors_to_project_root(self):
        """
        Given a hard_deny with a RELATIVE Edit pattern 'secrets/**' declared at the
            user level and a project-level allow for Edit of '**'
        When an Edit of <project>/secrets/key is resolved
        Then the relative hard_deny pattern is anchored to the project root and
            the edit is denied (unoverridable) -- and a same-named path OUTSIDE
            the project root is NOT hard-denied (proving the anchoring, not a
            leaky pattern): it falls through to the shared no_match_fallback
            resolution instead, which is 'ask' by default (TOO-15); the
            hard_deny enforcement itself (the security-relevant assertion) is
            unaffected and stays 'deny'
        """
        home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Edit(**)"]\n',
        )
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            '[hard_deny]\ndeny = ["Edit(secrets/**)"]\n',
        )

        inside = str(project / "secrets" / "key.txt")
        outside = str(home / "secrets" / "key.txt")
        config = load_configuration(project)
        inside_result = resolve_file_path_permission_detailed("Edit", inside, config)
        outside_result = resolve_file_path_permission_detailed("Edit", outside, config)
        self.assertEqual(inside_result.decision, "deny")
        self.assertEqual(outside_result.decision, "ask")
        self.assertNotIn("hard_deny", outside_result.reason)

    def test_no_hard_deny_leaves_file_path_cascade_unchanged(self):
        """
        Given no [hard_deny] configured and a project allow for Read of 'src/**'
        When a Read of <project>/src/x.py is resolved
        Then Phase 2 file-path behaviour is unchanged: the read is allowed
        """
        _home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            '[permissions]\nallow = ["Read(src/**)"]\n',
        )
        target_file = str(project / "src" / "x.py")
        config = load_configuration(project)
        result = resolve_file_path_permission_detailed("Read", target_file, config)
        self.assertEqual(result.decision, "allow")


class TestHardDenyThroughMain(ConfigIsolationMixin, _IsolatedEnvTestCase):
    """End-to-end test of hard_deny via the hook main() entry point for Bash."""

    def test_main_bash_hard_deny_denies_despite_project_allow(self):
        """
        Given a project-level normal allow for 'curl *' and a user-level hard_deny
            denying 'curl *', driven through the hook's main() entry point
        When a Bash 'curl http://x' invocation is processed
        Then main() emits a deny decision citing the unoverridable hard_deny
        """
        import json as _json
        from io import StringIO

        from toolguard.hook import main

        home, project = self.isolate_config_environment()
        _write(
            project / ".claude",
            "toolguard_hook.toml",
            'governed_tools = ["Bash"]\n[permissions]\nallow = ["Bash(curl *)"]\n',
        )
        _write(
            home / ".claude",
            "toolguard_hook.toml",
            '[hard_deny]\ndeny = ["Bash(curl *)"]\n',
        )

        hook_input = {
            "tool_name": "Bash",
            "tool_input": {"command": "curl http://x"},
            "hook_event_name": "PreToolUse",
            "cwd": str(project),
        }

        with patch("sys.stdin", StringIO(_json.dumps(hook_input))):
            with patch("sys.stdout", new_callable=StringIO) as mock_stdout:
                with patch("toolguard.hook.log_command"):
                    with patch(
                        "toolguard.hook.check_and_warn_divergence",
                        return_value=DivergenceCheckResult(divergent_patterns=[]),
                    ):
                        try:
                            main()
                        except SystemExit:
                            pass
                output = _json.loads(mock_stdout.getvalue())

        self.assertEqual(output["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn(
            "hard_deny", output["hookSpecificOutput"]["permissionDecisionReason"]
        )


if __name__ == "__main__":
    unittest.main()
