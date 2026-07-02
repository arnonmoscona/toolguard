"""
Unit tests for the maintenance aggregator (toolguard.tools.maintenance).

These verify that run_maintenance composes the individual maintenance engines into
a single structured report, and that render produces a readable summary.  Local
fixture helpers mirror the other maintenance-tool tests for consistency.
"""

import argparse
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional
from unittest import mock

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.maintenance import (
    MaintenanceReport,
    _nosecurity_block_reason,
    _partition_nosecurity,
    _run_apply,
    change_report_to_dict,
    collect_consolidations,
    consolidation_to_edit_proposal,
    main,
    report_to_dict,
    run_maintenance,
    render,
)
from toolguard.tools.rule_apply import ChangeReport, FileChange


def _make_provenance(specificity: int = 0) -> Provenance:
    """Build a minimal project-level Provenance for tests."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=specificity,
    )


def _make_layer(
    tool: str,
    allow: List[str],
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    provenance: Optional[Provenance] = None,
) -> ConfigLayer:
    """Build a ConfigLayer with wrapped allow/deny/ask bodies for ``tool``."""
    provenance = provenance or _make_provenance()
    prefix = f"{tool}("
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"{prefix}{p})" for p in (allow or [])],
                "deny": [f"{prefix}{p})" for p in (deny or [])],
                "ask": [f"{prefix}{p})" for p in (ask or [])],
            }
        }
    )
    return ConfigLayer(provenance=provenance, content=content)


def _make_config(*layers: ConfigLayer) -> Configuration:
    """Build a Configuration from the given layers."""
    return Configuration(layers=tuple(layers), start_dir=None)


def _make_log_entry(tool: str, command: str) -> LogEntry:
    """Build an EXECUTED LogEntry for the corpus."""
    return LogEntry(
        timestamp=datetime(2026, 6, 25, 10, 0, 0),
        tool=tool,
        command=command,
        status="EXECUTED",
        rule_text=None,
        agent="main",
        log_file=None,
    )


class TestRunMaintenance(unittest.TestCase):
    """Aggregation of the maintenance engines into a single report."""

    def test_aggregates_consolidations_and_broadenings_for_a_tool(self):
        """
        Given a Bash config with a consolidatable git-family allow set
        When run_maintenance is called
        Then the Bash tool report carries both strict consolidations and
            agent-judged broadenings, and the report reports findings.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        self.assertEqual(len(report.tools), 1)
        bash = report.tools[0]
        self.assertEqual(bash.tool, "Bash")
        self.assertTrue(bash.consolidations)
        self.assertTrue(bash.broadenings)
        self.assertTrue(report.has_any_findings)

    def test_restricts_to_requested_tools(self):
        """
        Given a config and an explicit single-tool request
        When run_maintenance is called with tools=['Bash']
        Then only the Bash tool is inspected (no Read/Write/Edit entries).
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        self.assertEqual([t.tool for t in report.tools], ["Bash"])

    def test_mining_included_when_corpus_supplied(self):
        """
        Given a corpus with an executed command the config does not allow
        When run_maintenance is called with that corpus
        Then the report's mining section contains at least one candidate group.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        report = run_maintenance(config, tools=["Bash"], corpus=corpus)
        self.assertTrue(report.mining.groups)

    def test_clarity_interactions_surface_in_report(self):
        """
        Given a Bash config with a same-file allow overlapped by a broader deny
        When run_maintenance is called
        Then the Bash tool report carries a clarity interaction finding and the
            rendered summary mentions it.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run alembic upgrade:*"],
                deny=["uv run:*"],
            )
        )
        report = run_maintenance(config, tools=["Bash"])
        self.assertTrue(report.tools[0].interactions)
        self.assertIn("clarity", render(report))

    def test_empty_config_reports_no_findings(self):
        """
        Given a config with no rules
        When run_maintenance is called and the report is rendered
        Then has_any_findings is False and the rendered summary says so.
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        report = run_maintenance(config, tools=["Bash"])
        self.assertFalse(report.has_any_findings)
        self.assertIn("No maintenance findings", render(report))


class TestRenderMaintenance(unittest.TestCase):
    """Rendering of the aggregate maintenance summary."""

    def test_render_lists_headline_and_tool_section(self):
        """
        Given a report with Bash findings
        When render is called in markdown
        Then the output carries the headline counts and a Bash section naming a
            broadening proposal.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        out = render(report, "markdown")
        self.assertIsInstance(report, MaintenanceReport)
        self.assertIn("Maintenance summary", out)
        self.assertIn("Bash", out)
        self.assertIn("broaden", out)


class TestReportToDict(unittest.TestCase):
    """JSON serialization of a MaintenanceReport (the skill's structured contract)."""

    def test_serializes_findings_with_expanded_provenance(self):
        """
        Given a report carrying Bash consolidation/broadening findings
        When report_to_dict serializes it
        Then the payload mirrors the report (top-level counts, a Bash tool entry
            with the finding lists) and each finding's provenance is expanded to
            a dict including a describe string.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        payload = report_to_dict(report)
        self.assertEqual(payload["total_findings"], report.total_findings)
        self.assertTrue(payload["has_any_findings"])
        self.assertEqual([t["tool"] for t in payload["tools"]], ["Bash"])
        bash = payload["tools"][0]
        self.assertTrue(bash["broadenings"])
        prov = bash["broadenings"][0]["layer_provenance"]
        self.assertEqual(prov["level"], "project")
        self.assertIn("describe", prov)

    def test_serializes_mining_groups_when_corpus_supplied(self):
        """
        Given a report built with a corpus that yields a mining group
        When report_to_dict serializes it
        Then the payload's mining.groups carries the group with its observed
            counts, and the whole payload round-trips through json.dumps.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        report = run_maintenance(config, tools=["Bash"], corpus=corpus)
        payload = report_to_dict(report)
        self.assertTrue(payload["mining"]["groups"])
        group = payload["mining"]["groups"][0]
        self.assertEqual(group["tool"], "Bash")
        self.assertIsInstance(group["observed_counts"], dict)
        # Must be JSON-serializable end to end.
        self.assertIsInstance(json.dumps(payload), str)

    def test_empty_report_serializes_to_empty_findings(self):
        """
        Given a config with no rules
        When report_to_dict serializes the resulting report
        Then has_any_findings is False and the tool entry has empty finding lists.
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        report = run_maintenance(config, tools=["Bash"])
        payload = report_to_dict(report)
        self.assertFalse(payload["has_any_findings"])
        self.assertEqual(payload["tools"][0]["broadenings"], [])
        self.assertEqual(payload["mining"]["groups"], [])


class TestMaintenanceCLI(unittest.TestCase):
    """The toolguard-maintain CLI entry point."""

    def test_main_runs_read_only_and_prints_summary(self):
        """
        Given a config with Bash findings (load_config patched to return it)
        When main(['--tool', 'Bash', '--format', 'text']) is invoked
        Then it returns 0 and prints the maintenance summary to stdout.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        buffer = io.StringIO()
        with mock.patch(
            "toolguard.tools.maintenance.load_config", return_value=config
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--format", "text"])
        self.assertEqual(code, 0)
        self.assertIn("Maintenance summary", buffer.getvalue())

    def test_json_format_prints_valid_serialized_report(self):
        """
        Given a config with Bash findings
        When main(['--tool', 'Bash', '--format', 'json']) is invoked
        Then it returns 0 and stdout is valid JSON carrying the Bash tool entry.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        buffer = io.StringIO()
        with mock.patch(
            "toolguard.tools.maintenance.load_config", return_value=config
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual([t["tool"] for t in payload["tools"]], ["Bash"])

    def test_corpus_off_by_default_does_not_harvest(self):
        """
        Given no --corpus flag
        When main is invoked
        Then run_maintenance is called with corpus=None and the corpus harvester
            is never touched (static-only is the fast default).
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        with mock.patch(
            "toolguard.tools.maintenance.load_config", return_value=config
        ), mock.patch(
            "toolguard.tools.maintenance.harvest_corpus"
        ) as harvest, mock.patch(
            "toolguard.tools.maintenance.run_maintenance",
            wraps=run_maintenance,
        ) as run:
            with redirect_stdout(io.StringIO()):
                code = main(["--tool", "Bash"])
        self.assertEqual(code, 0)
        harvest.assert_not_called()
        self.assertIsNone(run.call_args.kwargs["corpus"])

    def test_corpus_flag_harvests_and_passes_corpus_through(self):
        """
        Given the --corpus flag with a max-age bound
        When main is invoked (harvester patched to a fixed corpus)
        Then harvest_corpus is called with that max_age_days and its result is
            forwarded to run_maintenance.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        with mock.patch(
            "toolguard.tools.maintenance.load_config", return_value=config
        ), mock.patch(
            "toolguard.tools.maintenance.harvest_corpus", return_value=corpus
        ) as harvest, mock.patch(
            "toolguard.tools.maintenance.run_maintenance",
            wraps=run_maintenance,
        ) as run:
            with redirect_stdout(io.StringIO()):
                code = main(["--tool", "Bash", "--corpus", "--max-age-days", "7"])
        self.assertEqual(code, 0)
        self.assertEqual(harvest.call_args.kwargs["max_age_days"], 7)
        self.assertIs(run.call_args.kwargs["corpus"], corpus)


class TestApplyMode(unittest.TestCase):
    """The toolguard-maintain --apply path (preview by default, --write to commit)."""

    def _git_config(self) -> Configuration:
        """A Bash config whose git-family allows are consolidatable."""
        return _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )

    def test_collect_consolidations_flattens_proposals(self):
        """
        Given a report with a consolidatable git-family allow set
        When collect_consolidations runs
        Then it returns the strict consolidation proposal(s) only.
        """
        report = run_maintenance(self._git_config(), tools=["Bash"])
        proposals = collect_consolidations(report)
        self.assertTrue(proposals)
        self.assertTrue(all(p.kind for p in proposals))

    def test_consolidation_to_edit_proposal_maps_to_replace(self):
        """
        Given a consolidation proposal (git family -> one merged allow)
        When consolidation_to_edit_proposal converts it
        Then it is a 'replace' EditProposal whose single edit removes the family
            and adds the merged pattern in the allow section at the same layer.
        """
        report = run_maintenance(self._git_config(), tools=["Bash"])
        prop = collect_consolidations(report)[0]
        ep = consolidation_to_edit_proposal(prop)
        self.assertEqual(ep.action, "replace")
        self.assertEqual(len(ep.edits), 1)
        edit = ep.edits[0]
        self.assertEqual(edit.list_type, "allow")
        self.assertEqual(set(edit.removed_patterns), set(prop.removed_patterns))
        self.assertEqual(edit.added_patterns, (prop.added_pattern,))
        self.assertTrue(ep.origin.startswith("consolidation:"))

    def test_apply_json_includes_edit_proposals_for_audit_review(self):
        """
        Given --apply --format json
        When main runs
        Then the payload carries an 'edit_proposals' array (one per consolidation)
            that the maintenance skill can feed to `toolguard-audit --edits`.
        """
        buffer = io.StringIO()
        with mock.patch(
            "toolguard.tools.maintenance.load_config",
            return_value=self._git_config(),
        ), mock.patch(
            "toolguard.tools.maintenance.apply_proposals",
            return_value=ChangeReport(files=()),
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["edit_proposals"])
        self.assertEqual(payload["edit_proposals"][0]["action"], "replace")

    def test_change_report_to_dict_includes_diff_and_outcome(self):
        """
        Given a ChangeReport with one written file carrying a diff
        When change_report_to_dict serializes it
        Then the payload exposes the file path, the diff, the written flag, and
            the applied/removed/added patterns.
        """
        fchange = FileChange(
            path=Path("/proj/.claude/toolguard_hook.toml"),
            file_format="toml",
            applied=(),
            skipped=(),
            patterns_removed=("Bash(git diff:*)",),
            patterns_added=("Bash([regex]^git (diff|log|status))",),
            diff="--- a\n+++ b\n",
            written=True,
        )
        payload = change_report_to_dict(ChangeReport(files=(fchange,)))
        self.assertEqual(payload["files"][0]["written"], True)
        self.assertIn("diff", payload["files"][0])
        self.assertEqual(
            payload["files_written"], ["/proj/.claude/toolguard_hook.toml"]
        )

    def test_apply_preview_is_dry_run_and_writes_nothing(self):
        """
        Given --apply without --write
        When main runs (apply_proposals patched to observe the call)
        Then apply_proposals is called with dry_run=True, the pre-flight gate is
            NOT consulted, and the banner reports a dry run.
        """
        buffer = io.StringIO()
        with mock.patch(
            "toolguard.tools.maintenance.load_config",
            return_value=self._git_config(),
        ), mock.patch(
            "toolguard.tools.maintenance.apply_proposals",
            return_value=ChangeReport(files=()),
        ) as apply, mock.patch(
            "toolguard.tools.maintenance.migration_preflight"
        ) as preflight:
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply"])
        self.assertEqual(code, 0)
        self.assertTrue(apply.call_args.kwargs["dry_run"])
        preflight.assert_not_called()
        self.assertIn("DRY RUN", buffer.getvalue())

    def test_write_refused_when_preflight_has_blockers(self):
        """
        Given --apply --write but a pre-flight that reports blockers (dirty tree)
        When main runs
        Then it returns 2, prints the blockers, and never calls apply_proposals
            (the config is left untouched).
        """
        buffer = io.StringIO()
        blocked = mock.Mock(blockers=["The working tree has uncommitted changes: x"])
        with mock.patch(
            "toolguard.tools.maintenance.load_config",
            return_value=self._git_config(),
        ), mock.patch(
            "toolguard.tools.maintenance.migration_preflight", return_value=blocked
        ), mock.patch(
            "toolguard.tools.maintenance.apply_proposals"
        ) as apply:
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--write"])
        self.assertEqual(code, 2)
        apply.assert_not_called()
        self.assertIn("Refusing to write", buffer.getvalue())

    def test_write_applies_when_preflight_is_clean(self):
        """
        Given --apply --write and a clean pre-flight (no blockers)
        When main runs (apply_proposals patched)
        Then apply_proposals is called with dry_run=False and exit code is 0.
        """
        buffer = io.StringIO()
        clean = mock.Mock(blockers=[])
        with mock.patch(
            "toolguard.tools.maintenance.load_config",
            return_value=self._git_config(),
        ), mock.patch(
            "toolguard.tools.maintenance.migration_preflight", return_value=clean
        ), mock.patch(
            "toolguard.tools.maintenance.apply_proposals",
            return_value=ChangeReport(files=()),
        ) as apply:
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--write"])
        self.assertEqual(code, 0)
        self.assertFalse(apply.call_args.kwargs["dry_run"])
        self.assertIn("APPLIED", buffer.getvalue())

    def test_apply_json_emits_change_report_with_dry_run_flag(self):
        """
        Given --apply --format json
        When main runs
        Then stdout is a JSON change report carrying a dry_run=true flag.
        """
        buffer = io.StringIO()
        with mock.patch(
            "toolguard.tools.maintenance.load_config",
            return_value=self._git_config(),
        ), mock.patch(
            "toolguard.tools.maintenance.apply_proposals",
            return_value=ChangeReport(files=()),
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertTrue(payload["dry_run"])
        self.assertIn("files", payload)

    def test_write_requires_apply(self):
        """
        Given --write without --apply
        When main runs
        Then argparse errors out (SystemExit), guarding against an accidental
            bare --write.
        """
        with self.assertRaises(SystemExit):
            main(["--write"])


class TestNoSecurityWithholding(unittest.TestCase):
    """A #NOSECURITY-blessed rule is never auto-migrated/rewritten by --apply."""

    _ALLOWS = ["git diff:*", "git status:*", "git log:*"]

    def _config_with_real_file(self, tmpdir: str, tagged: bool) -> Configuration:
        """
        Write a real toolguard_hook.toml (with a #NOSECURITY comment on 'git diff:*'
        when *tagged*) and return a Configuration whose layer provenance points at it,
        so the comment can be recovered from disk during consolidation withholding.
        """
        lines = []
        for body in self._ALLOWS:
            if tagged and body == "git diff:*":
                lines.append(f"    'Bash({body})',  # NOSECURITY: audited manually")
            else:
                lines.append(f"    'Bash({body})',")
        text = (
            "[permissions]\nallow = [\n" + "\n".join(lines) + "\n]\ndeny = []\nask = []\n"
        )
        path = Path(tmpdir) / "toolguard_hook.toml"
        path.write_text(text, encoding="utf-8")
        prov = Provenance(
            level="project",
            source_type="toolguard_hook",
            file_format="toml",
            path=path,
            specificity=0,
        )
        return _make_config(_make_layer("Bash", allow=self._ALLOWS, provenance=prov))

    def test_partition_withholds_consolidation_touching_blessed_rule(self):
        """
        Given a consolidatable git family in which 'git diff:*' is #NOSECURITY-blessed
        When _partition_nosecurity runs over the collected consolidations
        Then the proposal is withheld (nothing appliable) with the reason recovered
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True), tools=["Bash"]
            )
            proposals = collect_consolidations(report)
            self.assertTrue(proposals)
            appliable, withheld = _partition_nosecurity(proposals)
            self.assertEqual(appliable, [])
            self.assertTrue(withheld)
            self.assertEqual(withheld[0][1], "audited manually")

    def test_partition_applies_when_no_rule_is_blessed(self):
        """
        Given the same consolidatable git family with NO #NOSECURITY comment
        When _partition_nosecurity runs
        Then nothing is withheld; every consolidation stays appliable
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=False), tools=["Bash"]
            )
            proposals = collect_consolidations(report)
            self.assertTrue(proposals)
            appliable, withheld = _partition_nosecurity(proposals)
            self.assertEqual(withheld, [])
            self.assertEqual(len(appliable), len(proposals))

    def test_nosecurity_block_reason_matches_removed_rule(self):
        """
        Given a consolidation whose removed family includes the blessed 'git diff:*'
        When _nosecurity_block_reason inspects it
        Then it returns the blocking reason string
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True), tools=["Bash"]
            )
            prop = collect_consolidations(report)[0]
            self.assertEqual(_nosecurity_block_reason(prop), "audited manually")

    def test_apply_json_lists_withheld_and_omits_blessed_edit(self):
        """
        Given --apply --format json over a config with a #NOSECURITY-blessed rule
        When _run_apply renders the change report (dry run)
        Then the payload lists the withheld consolidation under 'withheld_nosecurity'
            and no emitted edit_proposal removes the blessed 'git diff:*' rule
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True), tools=["Bash"]
            )
            args = argparse.Namespace(write=False, format="json", dir=d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = _run_apply(args, report)
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["withheld_nosecurity"])
            self.assertEqual(
                payload["withheld_nosecurity"][0]["reason"], "audited manually"
            )
            emitted_removed = {
                pat
                for ep in payload["edit_proposals"]
                for edit in ep["edits"]
                for pat in edit["removed_patterns"]
            }
            self.assertNotIn("git diff:*", emitted_removed)


if __name__ == "__main__":
    unittest.main()
