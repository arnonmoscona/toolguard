"""Unit tests for toolguard.tools.danger -- static risk finding detection."""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
    TakeoverConfig,
)
from toolguard.tools.config_access import per_layer_rules
from toolguard.tools.danger import (
    DangerFinding,
    Severity,
    danger,
)


def _make_provenance(
    path: str = "/fake/.claude/toolguard_hook.toml",
    source_type: str = "toolguard_hook",
    specificity: int = 0,
) -> Provenance:
    """Build a minimal Provenance for test use."""
    return Provenance(
        level="project",
        source_type=source_type,
        file_format="toml",
        path=Path(path),
        specificity=specificity,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    is_native: bool = False,
    specificity: int = 0,
) -> ConfigLayer:
    """Build a ConfigLayer whose allow/deny patterns are wrapped as ``Tool(inner)``."""
    prefix = f"{tool}("
    wrapped_allow = [f"{prefix}{p})" for p in (allow or [])]
    wrapped_deny = [f"{prefix}{p})" for p in (deny or [])]
    source_type = "claude" if is_native else "toolguard_hook"
    prov = _make_provenance(
        path=f"/fake/.claude/{'settings.json' if is_native else 'toolguard_hook.toml'}",
        source_type=source_type,
        specificity=specificity,
    )
    content = MappingProxyType(
        {
            "permissions": {
                "allow": wrapped_allow,
                "deny": wrapped_deny,
                "ask": [],
            }
        }
    )
    return ConfigLayer(provenance=prov, content=content)


def _make_config(
    *layers: ConfigLayer,
    takeover_enabled: bool = False,
) -> Configuration:
    """Build a Configuration with optional takeover settings."""
    if takeover_enabled:
        # Distinct path: Provenance is a frozen dataclass and per_layer_rules keys a
        # dict by it, so a takeover layer equal to a rule layer silently collapses the
        # two and every finding from that layer is reported twice.
        takeover_prov = _make_provenance(path="/fake/.claude/takeover_hook.toml")
        takeover_content = MappingProxyType(
            {
                "takeover_mode": {
                    "enabled": True,
                    "ignored_allow_patterns": [
                        "Bash(*)",
                        "Read(*)",
                        "Write(*)",
                        "Edit(*)",
                        "mcp__jetbrains__execute_terminal_command(*)",
                    ],
                    "additional_ignored_patterns": [],
                    "no_match_fallback": "deny",
                },
                "governed_tools": ["Bash", "Read", "Write", "Edit"],
            }
        )
        takeover_layer = ConfigLayer(provenance=takeover_prov, content=takeover_content)
        return Configuration(layers=(takeover_layer,) + tuple(layers), start_dir=None)
    return Configuration(layers=tuple(layers), start_dir=None)


def _ids(findings: List[DangerFinding]) -> List[str]:
    """Extract detector IDs from a list of findings."""
    return [f.detector_id for f in findings]


def _patterns(findings: List[DangerFinding]) -> List[str]:
    """Extract patterns from a list of findings."""
    return [f.pattern for f in findings]


class TestArbitraryExecAllow(unittest.TestCase):
    """Tests for the arbitrary-exec-allow CRITICAL detector."""

    def test_uv_run_python_wildcard_flagged(self):
        """
        Given an allow rule 'uv run python:*' for Bash (the required fixture)
        When danger() is called
        Then a CRITICAL finding with detector_id='arbitrary-exec-allow' is returned
        """
        layer = _make_layer("Bash", allow=["uv run python:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)
        self.assertEqual(exec_findings[0].severity, Severity.CRITICAL)
        self.assertEqual(exec_findings[0].tool, "Bash")
        self.assertIn("uv run python:*", _patterns(exec_findings))

    def test_bare_python_wildcard_flagged(self):
        """
        Given an allow rule 'python3:*' for Bash
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["python3:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)

    def test_node_flagged(self):
        """
        Given an allow rule 'node script.js:*' for Bash
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["node script.js:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)

    def test_bash_c_flagged(self):
        """
        Given an allow rule 'bash -c:*' for Bash
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["bash -c:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)

    def test_exec_flagged(self):
        """
        Given an allow rule 'exec:*' for Bash
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["exec:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)
        self.assertEqual(exec_findings[0].severity, Severity.CRITICAL)

    def test_regex_anchored_python_flagged(self):
        """
        Given an anchored regex allow rule '[regex]^python:.*' for Bash
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        """
        layer = _make_layer("Bash", allow=[r"[regex]^python:.*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)
        self.assertEqual(exec_findings[0].severity, Severity.CRITICAL)

    def test_regex_anchored_node_ruby_perl_flagged(self):
        """
        Given anchored regex allow rules '[regex]^node:.*', '[regex]^ruby:.*',
        and '[regex]^perl:.*' for Bash
        When danger() is called on each
        Then a CRITICAL arbitrary-exec-allow finding is returned for each
        """
        for body in (r"[regex]^node:.*", r"[regex]^ruby:.*", r"[regex]^perl:.*"):
            with self.subTest(pattern=body):
                layer = _make_layer("Bash", allow=[body])
                config = _make_config(layer)
                findings = danger(config)
                exec_findings = [
                    f for f in findings if f.detector_id == "arbitrary-exec-allow"
                ]
                self.assertGreater(len(exec_findings), 0)
                self.assertEqual(exec_findings[0].severity, Severity.CRITICAL)

    def test_named_script_after_interpreter_still_flagged(self):
        """
        Given an allow rule 'uv run python manage.py test:*', which names a specific
        script rather than leaving the interpreter open
        When danger() is called
        Then it is still flagged CRITICAL: the detector matches the 'uv run python'
        prefix followed by a space, so naming a script does not narrow it
        """
        layer = _make_layer("Bash", allow=["uv run python manage.py test:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)
        self.assertEqual(exec_findings[0].severity, Severity.CRITICAL)


class TestFindingOrdering(unittest.TestCase):
    """Tests for danger()'s documented descending-severity, tool, pattern ordering."""

    def test_findings_ordered_by_descending_severity(self):
        """
        Given one Bash layer whose allow list holds a MEDIUM, then a HIGH, then a
        CRITICAL pattern -- i.e. written in ascending severity
        When danger() is called
        Then the findings come back CRITICAL, HIGH, MEDIUM, the reverse of the order
        the patterns were written in
        """
        layer = _make_layer(
            "Bash", allow=["[regex]find", "rm -rf:*", "uv run python:*"]
        )
        findings = danger(_make_config(layer))
        self.assertEqual(
            [f.severity for f in findings],
            [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM],
        )
        self.assertEqual(
            _ids(findings),
            [
                "arbitrary-exec-allow",
                "destructive-cmd-allow",
                "unanchored-regex-allow",
            ],
        )

    def test_severity_outranks_tool_in_ordering(self):
        """
        Given a HIGH Bash finding and a CRITICAL Read finding, with Bash audited first
        because tools are discovered in sorted name order
        When danger() is called
        Then the CRITICAL Read finding is first: severity outranks the tool name
        """
        findings = danger(
            _make_config(
                _make_layer("Bash", allow=["rm -rf:*"], specificity=0),
                _make_layer("Read", allow=["*"], specificity=1),
            )
        )
        self.assertEqual(
            [(f.severity, f.tool) for f in findings],
            [(Severity.CRITICAL, "Read"), (Severity.HIGH, "Bash")],
        )

    def test_equal_severity_findings_ordered_by_pattern(self):
        """
        Given two equally severe (HIGH) Bash allow patterns written in descending
        alphabetical order
        When danger() is called
        Then they come back in ascending pattern order
        """
        layer = _make_layer("Bash", allow=["rm -rf zzz:*", "rm -rf aaa:*"])
        findings = danger(_make_config(layer))
        self.assertEqual(_patterns(findings), ["rm -rf aaa:*", "rm -rf zzz:*"])


class TestDestructiveCmdAllow(unittest.TestCase):
    """Tests for the destructive-cmd-allow HIGH detector."""

    def test_rm_rf_wildcard_flagged(self):
        """
        Given an allow rule 'rm -rf:*' for Bash
        When danger() is called
        Then a HIGH finding with detector_id='destructive-cmd-allow' is returned
        """
        layer = _make_layer("Bash", allow=["rm -rf:*"])
        config = _make_config(layer)
        findings = danger(config)
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        self.assertGreater(len(dest_findings), 0)
        self.assertEqual(dest_findings[0].severity, Severity.HIGH)

    def test_rm_rf_with_specific_path_flagged(self):
        """
        Given 'rm -rf /tmp/testdir:*'
        When danger() is called
        Then a HIGH destructive finding is returned
        """
        layer = _make_layer("Bash", allow=["rm -rf /tmp/testdir:*"])
        config = _make_config(layer)
        findings = danger(config)
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        self.assertGreater(len(dest_findings), 0)

    def test_regex_rm_rf_flagged(self):
        """
        Given an anchored regex allow rule '[regex]^rm -rf\\b' for Bash
        When danger() is called
        Then a HIGH destructive-cmd-allow finding is returned -- the detector's REGEX
        branch matches the literal inside the body, not the fnmatch prefix table
        """
        layer = _make_layer("Bash", allow=[r"[regex]^rm -rf\b"])
        config = _make_config(layer)
        findings = danger(config)
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        self.assertGreater(len(dest_findings), 0)
        self.assertEqual(dest_findings[0].severity, Severity.HIGH)

    def test_safe_rm_without_rf_not_flagged(self):
        """
        Given 'rm /tmp/file.txt:*' (no -rf flag)
        When danger() is called
        Then no destructive-cmd-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["rm /tmp/file.txt:*"])
        config = _make_config(layer)
        findings = danger(config)
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        self.assertEqual(dest_findings, [])


class TestSecretsExposureAllow(unittest.TestCase):
    """Tests for the secrets-exposure-allow HIGH detector."""

    def test_dot_env_pattern_flagged(self):
        """
        Given an allow rule for Read with '.env' in the pattern
        When danger() is called
        Then a HIGH secrets-exposure-allow finding is returned
        """
        layer = _make_layer("Read", allow=[".env"])
        config = _make_config(layer)
        findings = danger(config)
        secret_findings = [
            f for f in findings if f.detector_id == "secrets-exposure-allow"
        ]
        self.assertGreater(len(secret_findings), 0)
        self.assertEqual(secret_findings[0].severity, Severity.HIGH)

    def test_dot_ssh_pattern_flagged(self):
        """
        Given an allow rule for Read with '~/.ssh/**'
        When danger() is called
        Then a HIGH secrets-exposure-allow finding is returned
        """
        layer = _make_layer("Read", allow=["~/.ssh/**"])
        config = _make_config(layer)
        findings = danger(config)
        secret_findings = [
            f for f in findings if f.detector_id == "secrets-exposure-allow"
        ]
        self.assertGreater(len(secret_findings), 0)

    def test_bash_dotenv_cat_flagged(self):
        """
        Given 'cat .env:*' as a Bash allow rule
        When danger() is called
        Then a HIGH secrets-exposure-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["cat .env:*"])
        config = _make_config(layer)
        findings = danger(config)
        secret_findings = [
            f for f in findings if f.detector_id == "secrets-exposure-allow"
        ]
        self.assertGreater(len(secret_findings), 0)

    def test_regex_dot_env_flagged(self):
        """
        Given an anchored regex allow rule '[regex]^cat .*\\.env$' for Bash
        When danger() is called
        Then a HIGH secrets-exposure-allow finding is returned from the detector's
        REGEX branch
        """
        layer = _make_layer("Bash", allow=[r"[regex]^cat .*\.env$"])
        config = _make_config(layer)
        findings = danger(config)
        secret_findings = [
            f for f in findings if f.detector_id == "secrets-exposure-allow"
        ]
        self.assertGreater(len(secret_findings), 0)
        self.assertEqual(secret_findings[0].severity, Severity.HIGH)

    def test_normal_read_pattern_not_flagged(self):
        """
        Given an allow rule for Read with '~/projects/**' (no secrets indicators)
        When danger() is called
        Then no secrets-exposure-allow finding is returned
        """
        layer = _make_layer("Read", allow=["~/projects/**"])
        config = _make_config(layer)
        findings = danger(config)
        secret_findings = [
            f for f in findings if f.detector_id == "secrets-exposure-allow"
        ]
        self.assertEqual(secret_findings, [])


class TestUnanchoredRegexAllow(unittest.TestCase):
    """Tests for the unanchored-regex-allow MEDIUM detector."""

    def test_unanchored_regex_flagged(self):
        """
        Given an allow rule '[regex]find' (no ^ anchor)
        When danger() is called
        Then a MEDIUM finding with detector_id='unanchored-regex-allow' is returned
        """
        layer = _make_layer("Bash", allow=["[regex]find"])
        config = _make_config(layer)
        findings = danger(config)
        regex_findings = [
            f for f in findings if f.detector_id == "unanchored-regex-allow"
        ]
        self.assertGreater(len(regex_findings), 0)
        self.assertEqual(regex_findings[0].severity, Severity.MEDIUM)
        self.assertEqual(regex_findings[0].pattern, "[regex]find")

    def test_anchored_regex_not_flagged(self):
        """
        Given an allow rule '[regex]^git\\b' (has ^ anchor)
        When danger() is called
        Then no unanchored-regex-allow finding is returned
        """
        layer = _make_layer("Bash", allow=[r"[regex]^git\b"])
        config = _make_config(layer)
        findings = danger(config)
        regex_findings = [
            f for f in findings if f.detector_id == "unanchored-regex-allow"
        ]
        self.assertEqual(regex_findings, [])

    def test_unanchored_regex_with_word_boundary(self):
        """
        Given '[regex]\\bfind\\b(?!.*exec)' (word-bounded but no ^ anchor)
        When danger() is called
        Then a MEDIUM unanchored-regex-allow finding is returned
        """
        layer = _make_layer("Bash", allow=[r"[regex]\bfind\b(?!.*exec)"])
        config = _make_config(layer)
        findings = danger(config)
        regex_findings = [
            f for f in findings if f.detector_id == "unanchored-regex-allow"
        ]
        self.assertGreater(len(regex_findings), 0)

    def test_non_regex_wildcard_not_flagged_as_unanchored(self):
        """
        Given a DEFAULT pattern 'git *' (not a regex)
        When danger() is called
        Then no unanchored-regex-allow finding is returned
        """
        layer = _make_layer("Bash", allow=["git *"])
        config = _make_config(layer)
        findings = danger(config)
        regex_findings = [
            f for f in findings if f.detector_id == "unanchored-regex-allow"
        ]
        self.assertEqual(regex_findings, [])


class TestTakeoverModeAwareness(unittest.TestCase):
    """Tests for takeover-mode awareness in danger()."""

    def test_native_blanket_allow_is_stripped_before_danger_sees_it(self):
        """
        Given takeover mode is ON and Bash(*) is in native settings + in the ignored set
        When danger() is called
        Then no blanket finding is returned, and the reason is upstream: the pattern is
        already absent from the allow list danger() reads. With takeover OFF the same
        native pattern survives and IS flagged
        """
        native_layer = _make_layer("Bash", allow=["*"], is_native=True, specificity=1)
        config = _make_config(native_layer, takeover_enabled=True)
        takeover = config.takeover_mode()
        self.assertTrue(takeover.enabled)

        visible = [p for lr in per_layer_rules(config, "Bash") for p in lr.allow]
        self.assertEqual(visible, [])
        self.assertEqual(danger(config, takeover=takeover), [])

        off = _make_config(native_layer)
        self.assertEqual(
            [p for lr in per_layer_rules(off, "Bash") for p in lr.allow], ["*"]
        )
        self.assertEqual(_ids(danger(off)), ["blanket-allow-outside-takeover"])

    def test_caller_supplied_takeover_suppresses_native_blanket_allow(self):
        """
        Given a native Bash(*) allow that the config's own takeover state does not strip
        (takeover is OFF in the config), and a caller-supplied takeover that is ON and
        lists Bash(*) as ignored
        When danger() is called with that divergent takeover
        Then the blanket finding is suppressed while the unlisted native allow in the
        same layer is still reported
        """
        native = _make_layer(
            "Bash", allow=["*", "rm -rf:*"], is_native=True, specificity=1
        )
        config = _make_config(native)
        self.assertEqual(
            sorted(_ids(danger(config))),
            ["blanket-allow-outside-takeover", "destructive-cmd-allow"],
        )

        divergent = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=("Bash(*)",),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )
        self.assertEqual(
            _ids(danger(config, takeover=divergent)), ["destructive-cmd-allow"]
        )

    def test_caller_supplied_takeover_suppresses_native_content_finding(self):
        """
        Given the same divergent takeover, but listing the non-blanket native allow
        'Bash(rm -rf:*)' as ignored instead
        When danger() is called with it
        Then the destructive finding is suppressed while the blanket allow is still
        reported -- the two loops in _audit_tool consult the guard independently
        """
        native = _make_layer(
            "Bash", allow=["*", "rm -rf:*"], is_native=True, specificity=1
        )
        config = _make_config(native)
        divergent = TakeoverConfig(
            enabled=True,
            ignored_allow_patterns=("Bash(rm -rf:*)",),
            additional_ignored_patterns=(),
            no_match_fallback="deny",
        )
        self.assertEqual(
            _ids(danger(config, takeover=divergent)),
            ["blanket-allow-outside-takeover"],
        )

    def test_toolguard_layer_allow_is_not_suppressed_by_ignored_patterns(self):
        """
        Given takeover mode ON with Bash(*) in the ignored set, and Bash(*) written in a
        TOOLGUARD layer rather than in native settings
        When danger() is called
        Then it is still reported CRITICAL: the ignored set neutralizes native allows only
        """
        config = _make_config(_make_layer("Bash", allow=["*"]), takeover_enabled=True)
        self.assertIn("Bash(*)", config.takeover_mode().ignored_allow_patterns)
        findings = danger(config)
        self.assertEqual(_ids(findings), ["blanket-allow-outside-takeover"])
        self.assertEqual(findings[0].severity, Severity.CRITICAL)

    def test_real_toolguard_allow_still_flagged_when_takeover_on(self):
        """
        Given takeover mode is ON and a toolguard rule allows 'uv run python:*'
        When danger() is called
        Then the CRITICAL finding IS returned
        """
        tg_layer = _make_layer("Bash", allow=["uv run python:*"], specificity=0)
        config = _make_config(tg_layer, takeover_enabled=True)
        takeover = config.takeover_mode()
        findings = danger(config, takeover=takeover)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)

    def test_takeover_read_from_config_when_not_provided(self):
        """
        Given a toolguard-layer allow that produces a finding either way, and no
        takeover argument
        When danger() is called on a config with takeover ON and again with it OFF
        Then the findings carry the config's takeover state, in both takeover_active
        and the rationale
        """
        layer = _make_layer("Bash", allow=["*"])

        on = danger(_make_config(layer, takeover_enabled=True))
        self.assertEqual([f.takeover_active for f in on], [True])
        self.assertIn("Takeover mode is ON", on[0].rationale)

        off = danger(_make_config(layer))
        self.assertEqual([f.takeover_active for f in off], [False])
        self.assertIn("Takeover mode is OFF", off[0].rationale)

    def test_live_blanket_allow_is_critical(self):
        """
        Given a toolguard rule that allows '*' for Bash with takeover OFF (live)
        When danger() is called
        Then a CRITICAL blanket-allow-outside-takeover finding is returned
        """
        tg_layer = _make_layer("Bash", allow=["*"])
        config = _make_config(tg_layer)
        findings = danger(config)
        blanket = [
            f for f in findings if f.detector_id == "blanket-allow-outside-takeover"
        ]
        self.assertEqual(len(blanket), 1)
        self.assertEqual(blanket[0].severity, Severity.CRITICAL)

    def test_glob_blanket_allow_is_critical(self):
        """
        Given a toolguard rule allowing '[glob]*' (and '[glob]**') for Bash, takeover OFF
        When danger() is called
        Then each is reported as a CRITICAL blanket-allow-outside-takeover finding
        """
        for body in ("[glob]*", "[glob]**"):
            with self.subTest(pattern=body):
                findings = danger(_make_config(_make_layer("Bash", allow=[body])))
                self.assertEqual(_ids(findings), ["blanket-allow-outside-takeover"])
                self.assertEqual(findings[0].severity, Severity.CRITICAL)

    def test_blanket_pattern_not_double_reported(self):
        """
        Given a '[regex].*' allow that is BOTH a blanket allow AND an unanchored regex
        When danger() is called
        Then the pattern is reported exactly ONCE (as blanket-allow-outside-takeover),
        not also as unanchored-regex-allow
        """
        tg_layer = _make_layer("Bash", allow=["[regex].*"])
        config = _make_config(tg_layer)
        findings = danger(config)
        for_pattern = [f for f in findings if f.pattern == "[regex].*"]
        self.assertEqual(len(for_pattern), 1)
        self.assertEqual(for_pattern[0].detector_id, "blanket-allow-outside-takeover")


class TestDangerFindingAttributes(unittest.TestCase):
    """Tests for finding attribute population."""

    def test_finding_fields_come_from_the_flagged_rule(self):
        """
        Given a single dangerous allow rule in a known layer
        When danger() returns the finding for it
        Then every field carries that rule's own detector, severity, tool, pattern,
        provenance and remediation kind, and the rationale names the pattern and tool
        """
        layer = _make_layer("Bash", allow=["rm -rf:*"])
        config = _make_config(layer)
        findings = danger(config)
        self.assertEqual(len(findings), 1)
        f = findings[0]
        self.assertEqual(f.detector_id, "destructive-cmd-allow")
        self.assertEqual(f.severity, Severity.HIGH)
        self.assertEqual(f.tool, "Bash")
        self.assertEqual(f.pattern, "rm -rf:*")
        self.assertEqual(f.provenance, layer.provenance)
        self.assertIn("rm -rf:*", f.rationale)
        self.assertIn("Bash", f.rationale)
        self.assertNotEqual(f.remediation, "")
        self.assertIs(f.takeover_active, False)
        self.assertEqual(f.list_type, "allow")
        self.assertEqual(f.remediation_kind, "remove")

    def test_safe_config_no_findings(self):
        """
        Given a configuration with only safe, specific allow rules
        When danger() is called
        Then no findings are returned
        """
        layer = _make_layer(
            "Bash",
            allow=[
                "git status:*",
                "git log:*",
                r"[regex]^\bls\b",
                "uv run pytest test/:*",
            ],
        )
        config = _make_config(layer)
        self.assertEqual(danger(config), [])

    def test_empty_config_no_findings(self):
        """
        Given a configuration with no allow rules
        When danger() is called
        Then no findings are returned
        """
        config = Configuration(layers=(), start_dir=None)
        findings = danger(config)
        self.assertEqual(findings, [])
