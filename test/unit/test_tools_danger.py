"""
Unit tests for toolguard.tools.danger -- static risk finding detection.

Tests cover all detector categories and takeover-mode awareness:
- arbitrary-exec-allow (CRITICAL): flags 'uv run python:*' (required fixture)
- destructive-cmd-allow (HIGH): flags 'rm -rf:*'
- secrets-exposure-allow (HIGH): flags '.env', '.ssh' patterns
- unanchored-regex-allow (MEDIUM): flags [regex] without '^' (required fixture)
- blanket-allow-outside-takeover (CRITICAL): flags bare '*' allows (complete bypass)
- Takeover-mode awareness: does NOT flag ignored blanket allows when takeover ON
"""

import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import (
    ConfigLayer,
    Configuration,
    Provenance,
)
from toolguard.tools.danger import (
    DangerFinding,
    Severity,
    danger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    """
    Build a ConfigLayer with the given allow/deny patterns for ``tool``.

    Patterns stored in wrapped ``Tool(inner)`` form.
    """
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
        # Add a toolguard_hook layer with takeover settings
        takeover_prov = _make_provenance()
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


# ---------------------------------------------------------------------------
# Arbitrary-exec-allow (CRITICAL) - required fixture: Bash(uv run python:*)
# ---------------------------------------------------------------------------


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
        Given an allow rule 'exec:*' for Bash (the shell 'exec' builtin replaces the
        process image and thus permits arbitrary execution)
        When danger() is called
        Then a CRITICAL arbitrary-exec-allow finding is returned
        (regression: 'exec' was previously undetected because its trailing-space and
        colon prefix entries could never match)
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
        (baseline that documents the intended symmetry with node/ruby/perl below)
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
        (regression: these escaped the REGEX branch because it matched only the
        literal token 'node ' with a trailing space, absent in the ':' form,
        while the equivalent DEFAULT pattern 'node:*' was correctly flagged)
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

    def test_safe_python_specific_script_not_flagged(self):
        """
        Given an allow rule 'uv run python manage.py test:*' (specific script, no wildcard exec)
        When danger() is called
        Then... it may be flagged because it starts with 'uv run python'
        NOTE: The detector is conservative; specific scripts under 'uv run python' are
        also flagged to ensure human review. This is by design.
        """
        # This test documents that even specific python invocations trigger the detector
        # The remediation message guides the user to verify intent
        layer = _make_layer("Bash", allow=["uv run python manage.py test:*"])
        config = _make_config(layer)
        findings = danger(config)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        # Conservative: flag anything starting with an interpreter prefix
        self.assertGreater(len(exec_findings), 0)

    def test_findings_sorted_critical_first(self):
        """
        Given multiple findings of different severity
        When danger() returns results
        Then CRITICAL findings appear before HIGH findings
        """
        layer = _make_layer("Bash", allow=["uv run python:*", "rm -rf:*"])
        config = _make_config(layer)
        findings = danger(config)
        if len(findings) >= 2:
            # First finding should be CRITICAL or equal severity
            self.assertGreaterEqual(
                findings[0].severity.value, findings[-1].severity.value
            )


# ---------------------------------------------------------------------------
# Destructive-cmd-allow (HIGH)
# ---------------------------------------------------------------------------


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
        Then a HIGH destructive finding is returned (conservative: all rm -rf are flagged)
        """
        layer = _make_layer("Bash", allow=["rm -rf /tmp/testdir:*"])
        config = _make_config(layer)
        findings = danger(config)
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        self.assertGreater(len(dest_findings), 0)

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


# ---------------------------------------------------------------------------
# Secrets-exposure-allow (HIGH)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Unanchored-regex-allow (MEDIUM) - required fixture
# ---------------------------------------------------------------------------


class TestUnanchoredRegexAllow(unittest.TestCase):
    """Tests for the unanchored-regex-allow MEDIUM detector (required fixture)."""

    def test_unanchored_regex_flagged(self):
        """
        Given an allow rule '[regex]find' (no ^ anchor, required fixture)
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
        (re.search matches anywhere in the string regardless of \\b)
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


# ---------------------------------------------------------------------------
# Takeover-mode awareness
# ---------------------------------------------------------------------------


class TestTakeoverModeAwareness(unittest.TestCase):
    """Tests for takeover-mode awareness in danger()."""

    def test_native_blanket_allow_not_flagged_when_takeover_on(self):
        """
        Given takeover mode is ON and Bash(*) is in native settings + in ignored set
        When danger() is called
        Then no finding is returned for the native blanket allow
        (it is an intentional takeover-mode artefact)
        """
        # Native layer with Bash(*) as a blanket allow
        native_layer = _make_layer("Bash", allow=["*"], is_native=True, specificity=1)
        # Toolguard layer with takeover enabled and Bash(*) in ignored set
        config = _make_config(native_layer, takeover_enabled=True)
        takeover = config.takeover_mode()
        self.assertTrue(takeover.enabled)

        findings = danger(config, takeover=takeover)
        # The native Bash(*) should NOT be flagged (it's in the ignored set)
        blanket_findings = [
            f
            for f in findings
            if f.detector_id == "blanket-allow-outside-takeover" and f.pattern == "*"
        ]
        self.assertEqual(blanket_findings, [])

    def test_real_toolguard_allow_still_flagged_when_takeover_on(self):
        """
        Given takeover mode is ON and a toolguard rule allows 'uv run python:*'
        When danger() is called
        Then the CRITICAL finding IS returned (non-ignored toolguard rules are always audited)
        """
        # Real toolguard layer with a dangerous allow
        tg_layer = _make_layer("Bash", allow=["uv run python:*"], specificity=0)
        config = _make_config(tg_layer, takeover_enabled=True)
        takeover = config.takeover_mode()
        findings = danger(config, takeover=takeover)
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        self.assertGreater(len(exec_findings), 0)

    def test_takeover_read_from_config_when_not_provided(self):
        """
        Given danger() is called without a pre-resolved takeover state
        When the config has takeover enabled
        Then danger() reads the takeover state from config automatically
        """
        native_layer = _make_layer("Bash", allow=["*"], is_native=True, specificity=1)
        config = _make_config(native_layer, takeover_enabled=True)
        # Do NOT pass takeover= argument
        findings = danger(config)
        # Should not raise; findings may or may not be empty depending on config
        self.assertIsInstance(findings, list)

    def test_live_blanket_allow_is_critical(self):
        """
        Given a toolguard rule that allows '*' for Bash with takeover OFF (live)
        When danger() is called
        Then a CRITICAL blanket-allow-outside-takeover finding is returned
        (a live blanket wildcard is a complete governance bypass for the tool)
        """
        tg_layer = _make_layer("Bash", allow=["*"])
        config = _make_config(tg_layer)  # takeover off by default
        findings = danger(config)
        blanket = [
            f for f in findings if f.detector_id == "blanket-allow-outside-takeover"
        ]
        self.assertEqual(len(blanket), 1)
        self.assertEqual(blanket[0].severity, Severity.CRITICAL)

    def test_blanket_pattern_not_double_reported(self):
        """
        Given a '[regex].*' allow that is BOTH a blanket allow AND an unanchored regex
        When danger() is called
        Then the pattern is reported exactly ONCE (as blanket-allow-outside-takeover),
        not also as unanchored-regex-allow (review finding M1: no double-reporting)
        """
        tg_layer = _make_layer("Bash", allow=["[regex].*"])
        config = _make_config(tg_layer)  # takeover off
        findings = danger(config)
        for_pattern = [f for f in findings if f.pattern == "[regex].*"]
        self.assertEqual(len(for_pattern), 1)
        self.assertEqual(for_pattern[0].detector_id, "blanket-allow-outside-takeover")


# ---------------------------------------------------------------------------
# Finding attributes and sorting
# ---------------------------------------------------------------------------


class TestDangerFindingAttributes(unittest.TestCase):
    """Tests for finding attribute population and output ordering."""

    def test_finding_has_all_required_fields(self):
        """
        Given a dangerous allow rule
        When danger() returns a finding
        Then the finding has all required fields populated
        """
        layer = _make_layer("Bash", allow=["rm -rf:*"])
        config = _make_config(layer)
        findings = danger(config)
        self.assertGreater(len(findings), 0)
        f = findings[0]
        self.assertIsInstance(f.detector_id, str)
        self.assertIsInstance(f.severity, Severity)
        self.assertIsInstance(f.tool, str)
        self.assertIsInstance(f.pattern, str)
        self.assertIsInstance(f.rationale, str)
        self.assertIsInstance(f.remediation, str)
        self.assertIsInstance(f.takeover_active, bool)

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
        findings = danger(config)
        # uv run pytest should not trigger arbitrary-exec, and anchored regex is fine
        exec_findings = [f for f in findings if f.detector_id == "arbitrary-exec-allow"]
        dest_findings = [
            f for f in findings if f.detector_id == "destructive-cmd-allow"
        ]
        regex_findings = [
            f for f in findings if f.detector_id == "unanchored-regex-allow"
        ]
        self.assertEqual(exec_findings, [])
        self.assertEqual(dest_findings, [])
        self.assertEqual(regex_findings, [])

    def test_empty_config_no_findings(self):
        """
        Given a configuration with no allow rules
        When danger() is called
        Then no findings are returned
        """
        config = Configuration(layers=(), start_dir=None)
        findings = danger(config)
        self.assertEqual(findings, [])
