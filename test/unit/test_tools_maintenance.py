"""
Unit tests for the maintenance aggregator (toolguard.tools.maintenance).

Verifies that run_maintenance composes the individual maintenance engines into a
single structured report, and that render produces a readable summary.
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
from typing import List, Optional, Tuple
from unittest import mock

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.config_write_guard import ConfigWriteVerificationError
from toolguard.tools import decision_ledger
from toolguard.tools.clarity import InteractionFinding
from toolguard.tools.consolidate import BroadeningProposal, ConsolidationProposal
from toolguard.tools.hierarchy import CrossLayerRedundancy
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.maintenance import (
    MaintenanceReport,
    ToolMaintenance,
    _collect_annotations,
    _nosecurity_block_reason,
    _partition_nosecurity,
    _permission_patterns_in_text,
    _render_apply,
    _render_ledger,
    _render_replay,
    _run_annotate,
    _run_apply,
    _run_record_decision,
    _run_replay_candidate,
    change_report_to_dict,
    collect_consolidations,
    consolidation_to_edit_proposal,
    main,
    replay_diff_to_dict,
    report_to_dict,
    run_maintenance,
    render,
)
from toolguard.tools.mining import CommandGroup, MiningReport
from toolguard.tools.redundancy import RedundancyFinding
from toolguard.tools.replay import replay
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

    def test_consolidations_receive_the_corpus(self):
        """
        Given a static-subsumption candidate that only tightens a corpus
              command outside its two synthetic probes ('uv run python -m
              pytest' loses coverage once 'uv run python:*' is dropped)
        When run_maintenance is called WITHOUT a corpus, then WITH one
        Then the proposal is present in the first report and absent from the
             second -- run_maintenance must pass its corpus argument through
             to propose_consolidations, not just to redundancy/broadening/mining.
        """
        config = _make_config(
            _make_layer(
                "Bash",
                allow=["uv run", "uv run python:*", "[regex]^uv run python( --x)?$"],
            )
        )
        corpus = [_make_log_entry("Bash", "uv run python -m pytest")]

        report_no_corpus = run_maintenance(config, tools=["Bash"])
        self.assertTrue(
            any(
                p.kind == "static-subsumption"
                for p in report_no_corpus.tools[0].consolidations
            )
        )

        report_with_corpus = run_maintenance(config, tools=["Bash"], corpus=corpus)
        self.assertFalse(
            any(
                p.kind == "static-subsumption"
                for p in report_with_corpus.tools[0].consolidations
            )
        )

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

    def test_redundancy_and_cross_layer_findings_reach_the_report(self):
        """
        Given a user layer and a more-specific project layer that both allow
            'git:*', the project layer holding it twice
        When run_maintenance is called
        Then the Bash report carries BOTH the within-layer redundancy and the
            cross-layer redundancy -- the two engines whose output the
            aggregator otherwise wires up unobserved.

        Asserts only that the aggregator surfaces what the engines returned.
        Proposed ticket 22 establishes that these findings can name a rule
        whose removal changes decisions, so their CONTENT is not endorsed here.
        """
        user = _make_layer(
            "Bash",
            allow=["git:*"],
            provenance=Provenance(
                level="user",
                source_type="toolguard_hook",
                file_format="toml",
                path=Path("/fake/home/.claude/toolguard_hook.toml"),
                specificity=0,
            ),
        )
        project = _make_layer(
            "Bash", allow=["git:*", "git:*"], provenance=_make_provenance(specificity=5)
        )
        report = run_maintenance(_make_config(user, project), tools=["Bash"])
        bash = report.tools[0]
        self.assertEqual(
            [(r.redundant_pattern, r.kind) for r in bash.redundancies],
            [("git:*", "static")],
        )
        self.assertEqual([x.pattern for x in bash.cross_layer_redundancies], ["git:*"])
        self.assertTrue(report.has_any_findings)

    def test_report_order_follows_the_requested_tool_order(self):
        """
        Given the same config inspected twice with the tool list reversed
        When run_maintenance is called
        Then the report's tool order mirrors the requested order both times --
            report order is part of the output, not an accident of iteration.
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        self.assertEqual(
            [t.tool for t in run_maintenance(config, tools=["Read", "Bash"]).tools],
            ["Read", "Bash"],
        )
        self.assertEqual(
            [t.tool for t in run_maintenance(config, tools=["Bash", "Read"]).tools],
            ["Bash", "Read"],
        )

    def test_default_inspects_the_four_builtin_tools_in_sorted_order(self):
        """
        Given no explicit tool list
        When run_maintenance is called
        Then it inspects exactly Bash, Edit, Read and Write, in that order.

        CHARACTERIZATION of the current default, not an endorsement: the
        follow-up queue's row M7 records that the default should come from
        Configuration.governed_tools(), so a user-governed MCP terminal tool is
        silently skipped today. This test exists so that change is visible.
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        report = run_maintenance(config)
        self.assertEqual(
            [t.tool for t in report.tools], ["Bash", "Edit", "Read", "Write"]
        )


def _report_with_counts(
    redundancies: int = 1,
    consolidations: int = 1,
    broadenings: int = 1,
    cross_layer: int = 1,
    interactions: int = 1,
    mining: int = 1,
) -> MaintenanceReport:
    """
    A hand-built report with a chosen number of findings in each category, plus
    a second tool with none.

    Hand-built rather than engine-derived so the renderer is measured against
    known counts: the engines emit at most two categories from any fixture
    small enough to keep in a test.  The per-category counts are separately
    settable because equal counts make a transposed category invisible.
    """
    provenance = _make_provenance()
    bash = ToolMaintenance(
        tool="Bash",
        redundancies=redundancies
        * (
            RedundancyFinding(
                redundant_pattern="git diff:*",
                provenance=provenance,
                kind="static",
                list_type="allow",
                tool="Bash",
                covered_by="git:*",
                note="duplicate of 'git:*'",
            ),
        ),
        consolidations=consolidations
        * (
            ConsolidationProposal(
                kind="literal-alternation",
                tool="Bash",
                list_type="allow",
                layer_provenance=provenance,
                removed_patterns=("git log:*", "git status:*"),
                added_pattern="[regex]^git (log|status)",
                rationale="the subcommand varies",
                replay_summary="10 probes unchanged; no corpus",
            ),
        ),
        broadenings=broadenings
        * (
            BroadeningProposal(
                kind="prefix-broadening",
                tool="Bash",
                list_type="allow",
                layer_provenance=provenance,
                removed_patterns=("git log:*",),
                added_pattern="git :*",
                rationale="admits every git subcommand",
                newly_admitted_commands=("git push origin main",),
                overlaps_guard_rules=("deny 'git push:*'",),
                probe_admitted_surface=(),
            ),
        ),
        cross_layer_redundancies=cross_layer
        * (
            CrossLayerRedundancy(
                tool="Bash",
                pattern="git fetch:*",
                redundant_provenance=provenance,
                covered_by_provenance=provenance,
                note="a broader copy exists at user level",
            ),
        ),
        interactions=interactions
        * (
            InteractionFinding(
                tool="Bash",
                provenance=provenance,
                kind="deny-shadows-allow",
                allow_pattern="uv run alembic:*",
                guard_section="deny",
                guard_pattern="uv run:*",
                explanation="the deny wins at this level",
                guard_provenance=None,
            ),
        ),
    )
    quiet = ToolMaintenance(
        tool="Read",
        redundancies=(),
        consolidations=(),
        broadenings=(),
        cross_layer_redundancies=(),
        interactions=(),
    )
    mining_report = MiningReport(
        groups=mining
        * (
            CommandGroup(
                tool="Bash",
                command_key="npm publish",
                signal="allow-candidate",
                distinct_commands=("npm publish --dry-run",),
                occurrences=4,
                current_verdict="ask",
                observed_counts={"EXECUTED": 4},
            ),
        )
    )
    return MaintenanceReport(tools=(bash, quiet), mining=mining_report)


class TestRenderMaintenance(unittest.TestCase):
    """Rendering of the aggregate maintenance summary."""

    def test_headline_counts_every_category_separately(self):
        """
        Given a report whose six categories hold a DIFFERENT number of findings
            each (1..6)
        When it is rendered
        Then the headline reports each count against its own label.

        The counts are deliberately unequal: with one finding per category a
        transposed pair -- reporting the clarity count as the redundancy count,
        say -- produces an identical line.
        """
        report = _report_with_counts(
            redundancies=1,
            consolidations=2,
            broadenings=3,
            cross_layer=4,
            interactions=5,
            mining=6,
        )
        out = render(report, "text")
        self.assertIn(
            "1 redundancy, 2 strict-consolidation, 3 broadening (agent-judged), "
            "4 cross-layer, 5 clarity, 6 mining candidate(s).",
            out,
        )

    def test_every_finding_category_appears_in_the_body(self):
        """
        Given a report carrying one finding of every category
        When it is rendered as text
        Then each category contributes its own line naming the rule it is
            about -- the redundancy, the consolidation's before/after, the
            broadening, the cross-layer finding, the clarity interaction, and
            the corpus-mining section.
        """
        out = render(_report_with_counts(), "text")
        self.assertIn("redundant: `git diff:*` -- duplicate of 'git:*'", out)
        self.assertIn(
            "consolidate (literal-alternation): ['git log:*', 'git status:*'] "
            "-> `[regex]^git (log|status)` [UNVERIFIED]",
            out,
        )
        self.assertIn("broaden (prefix-broadening, AGENT-JUDGED): -> `git :*`", out)
        self.assertIn("cross-layer redundant: `git fetch:*`", out)
        self.assertIn("clarity (deny-shadows-allow): the deny wins at this level", out)
        self.assertIn("Corpus mining", out)
        self.assertIn("npm publish", out)

    def test_a_tool_with_no_findings_gets_no_section(self):
        """
        Given a report whose second tool produced nothing
        When it is rendered
        Then only the tool that found something gets a section heading.
        """
        out = render(_report_with_counts(), "markdown")
        self.assertIn("## Bash", out)
        self.assertNotIn("## Read", out)

    def test_render_lists_headline_and_tool_section(self):
        """
        Given an engine-derived report with Bash findings
        When render is called in markdown
        Then the headline reports the one consolidation and the one broadening
            the engines found, and the Bash section names the broadened rule.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        out = render(report, "markdown")
        self.assertIsInstance(report, MaintenanceReport)
        self.assertIn("Maintenance summary", out)
        self.assertIn("1 strict-consolidation, 1 broadening (agent-judged)", out)
        self.assertIn("## Bash", out)
        self.assertIn("broaden (prefix-broadening, AGENT-JUDGED): -> `git :*`", out)


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

    def test_consolidation_verification_serializes_alongside_replay_summary(self):
        """
        Given a report with a consolidation built WITHOUT a corpus
        When report_to_dict serializes it
        Then the consolidation carries a 'verification' key equal to
             'unverified' -- not just embedded, unreachably, inside the
             'replay_summary' prose string.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        report = run_maintenance(config, tools=["Bash"])
        payload = report_to_dict(report)
        consolidation = payload["tools"][0]["consolidations"][0]
        self.assertEqual(consolidation["verification"], "unverified")


class TestMaintenanceCLI(unittest.TestCase):
    """The toolguard-maintain CLI entry point."""

    def test_main_runs_read_only_and_prints_summary(self):
        """
        Given a config with Bash findings (load_config patched to return it)
        When main(['--tool', 'Bash', '--format', 'text']) is invoked
        Then it returns 0 and prints a summary OF THAT CONFIG -- naming the
            git family it proposes to merge, so the run is known to have
            analysed the injected config rather than whatever config happens
            to exist in the current directory.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        buffer = io.StringIO()
        with mock.patch("toolguard.tools.maintenance.load_config", return_value=config):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--format", "text"])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("Maintenance summary", out)
        self.assertIn("1 strict-consolidation", out)
        self.assertIn("[regex]^git (diff|log|status)", out)

    def test_json_format_prints_valid_serialized_report(self):
        """
        Given a config with Bash findings
        When main(['--tool', 'Bash', '--format', 'json']) is invoked
        Then it returns 0 and stdout is valid JSON whose Bash entry carries the
            findings of the injected config -- not merely a Bash entry, which
            any config at all produces.
        """
        config = _make_config(
            _make_layer("Bash", allow=["git diff:*", "git status:*", "git log:*"])
        )
        buffer = io.StringIO()
        with mock.patch("toolguard.tools.maintenance.load_config", return_value=config):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual([t["tool"] for t in payload["tools"]], ["Bash"])
        self.assertEqual(
            [c["added_pattern"] for c in payload["tools"][0]["consolidations"]],
            ["[regex]^git (diff|log|status)(?=\\s|$)"],
        )

    def test_a_misspelled_tool_name_is_distinguishable_from_a_clean_run(self):
        """
        Given the same config inspected as '--tool Bash' and as '--tool Bahs'
        When main runs both
        Then the two runs are distinguishable -- either the misspelled one is
            rejected, or its output differs.

        RED, asserting the correct behaviour (follow-up-queue row M8, proposed
        ticket 29's family). Measured at HEAD: an unrecognised tool name yields
        five empty finding tuples, so the run exits 0 and prints a clean
        'No maintenance findings' report byte-identical to a real run over a
        rule-free config. Nothing distinguishes "checked and found nothing"
        from "checked nothing", which is the failure mode that hides a typo in
        a skill-generated command line.
        """
        config = _make_config(_make_layer("Bash", allow=[]))

        def _run(tool):
            buffer = io.StringIO()
            with mock.patch(
                "toolguard.tools.maintenance.load_config", return_value=config
            ):
                try:
                    with redirect_stdout(buffer):
                        code = main(["--tool", tool, "--format", "text"])
                except SystemExit as exc:
                    return ("exit", exc.code)
            return ("returned", code, buffer.getvalue())

        known = _run("Bash")
        unknown = _run("Bahs")
        self.assertNotEqual(
            unknown,
            known,
            "an unrecognised tool name produced the same clean report as a real "
            "run over a rule-free config",
        )

    def test_corpus_off_by_default_does_not_harvest(self):
        """
        Given no --corpus flag
        When main is invoked
        Then run_maintenance is called with corpus=None and the corpus harvester
            is never touched (static-only is the fast default).
        """
        config = _make_config(_make_layer("Bash", allow=[]))
        with (
            mock.patch("toolguard.tools.maintenance.load_config", return_value=config),
            mock.patch("toolguard.tools.maintenance.harvest_corpus") as harvest,
            mock.patch(
                "toolguard.tools.maintenance.run_maintenance",
                wraps=run_maintenance,
            ) as run,
        ):
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
        with (
            mock.patch("toolguard.tools.maintenance.load_config", return_value=config),
            mock.patch(
                "toolguard.tools.maintenance.harvest_corpus", return_value=corpus
            ) as harvest,
            mock.patch(
                "toolguard.tools.maintenance.run_maintenance",
                wraps=run_maintenance,
            ) as run,
        ):
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
        Then it returns the one strict consolidation, carrying the family it
            merges and the kind that named it.
        """
        report = run_maintenance(self._git_config(), tools=["Bash"])
        proposals = collect_consolidations(report)
        self.assertEqual([p.kind for p in proposals], ["literal-alternation"])
        self.assertEqual(
            set(proposals[0].removed_patterns),
            {"git diff:*", "git log:*", "git status:*"},
        )

    def test_collect_consolidations_excludes_agent_judged_broadenings(self):
        """
        Given a report whose Bash tool carries BOTH a strict consolidation and
            a prefix-broadening over the same three git rules
        When collect_consolidations runs
        Then it returns exactly the strict consolidations and nothing else --
            the broadening (which admits 'git anything') must never reach the
            apply path, which enacts whatever this function returns.
        """
        report = run_maintenance(self._git_config(), tools=["Bash"])
        bash = report.tools[0]
        self.assertTrue(bash.consolidations)
        self.assertTrue(bash.broadenings, "fixture must produce a broadening too")
        proposals = collect_consolidations(report)
        self.assertEqual(proposals, list(bash.consolidations))
        self.assertNotIn("git :*", [p.added_pattern for p in proposals])

    def test_static_subsumption_becomes_a_pure_removal(self):
        """
        Given a static-subsumption proposal, whose added_pattern is None
        When consolidation_to_edit_proposal converts it
        Then the edit removes the subsumed rule and adds NOTHING -- a
            synthesized `None` pattern would be written into the allow list.
        """
        prop = ConsolidationProposal(
            kind="static-subsumption",
            tool="Bash",
            list_type="allow",
            layer_provenance=_make_provenance(),
            removed_patterns=("uv run python:*",),
            added_pattern=None,
            rationale="subsumed by 'uv run:*'",
            replay_summary="2 positive probes pass; no corpus",
        )
        ep = consolidation_to_edit_proposal(prop)
        self.assertEqual(ep.edits[0].removed_patterns, ("uv run python:*",))
        self.assertEqual(ep.edits[0].added_patterns, ())

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
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.apply_proposals",
                return_value=ChangeReport(files=()),
            ),
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(len(payload["edit_proposals"]), 1)
        self.assertEqual(payload["edit_proposals"][0]["action"], "replace")
        edits = payload["edit_proposals"][0]["edits"]
        self.assertEqual(
            set(edits[0]["removed_patterns"]),
            {"git diff:*", "git log:*", "git status:*"},
        )
        self.assertEqual(
            edits[0]["added_patterns"], ["[regex]^git (diff|log|status)(?=\\s|$)"]
        )
        # The same fixture also yields a 'git :*' broadening; it is agent-judged
        # and must not be handed to the audit-and-apply path.
        self.assertNotIn(
            "git :*",
            [pat for e in edits for pat in e["added_patterns"]],
        )

    def test_apply_json_edit_proposal_carries_verification(self):
        """
        Given --apply --format json, built without a corpus
        When main runs
        Then each edit_proposals[] entry carries verification='unverified' --
             the SafetyResult the gate returned, not silently dropped when the
             consolidation crosses into the general EditProposal shape.
        """
        buffer = io.StringIO()
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.apply_proposals",
                return_value=ChangeReport(files=()),
            ),
        ):
            with redirect_stdout(buffer):
                code = main(["--tool", "Bash", "--apply", "--format", "json"])
        self.assertEqual(code, 0)
        payload = json.loads(buffer.getvalue())
        self.assertEqual(payload["edit_proposals"][0]["verification"], "unverified")

    def test_apply_json_applied_change_carries_verification(self):
        """
        Given --apply --write --format json where a proposal actually applies
        When main runs
        Then payload["files"][*]["applied"][*]["verification"] carries the
             SafetyResult, alongside removed_patterns/added_pattern/rationale.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "toolguard_hook.toml"
            cfg_path.write_text(
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(git diff:*)",\n'
                '  "Bash(git status:*)",\n'
                '  "Bash(git log:*)",\n'
                "]\n"
            )
            provenance = Provenance(
                level="project",
                source_type="toolguard_hook",
                file_format="toml",
                path=cfg_path,
                specificity=0,
            )
            config = _make_config(
                _make_layer(
                    "Bash",
                    allow=["git diff:*", "git status:*", "git log:*"],
                    provenance=provenance,
                )
            )
            buffer = io.StringIO()
            with (
                mock.patch(
                    "toolguard.tools.maintenance.load_config", return_value=config
                ),
                mock.patch(
                    "toolguard.tools.maintenance.migration_preflight"
                ) as mock_preflight,
            ):
                mock_preflight.return_value = mock.Mock(blockers=[])
                with redirect_stdout(buffer):
                    code = main(
                        [
                            "--tool",
                            "Bash",
                            "--apply",
                            "--write",
                            "--format",
                            "json",
                            "--dir",
                            tmp,
                        ]
                    )
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            applied = payload["files"][0]["applied"]
            self.assertEqual(len(applied), 1)
            self.assertEqual(applied[0]["verification"], "unverified")

    def test_default_apply_preview_shows_verification_tag(self):
        """
        Given --apply with no --write, no --format (defaults to markdown) and
             no --corpus, against a REAL config file (so apply_proposals runs
             for real, unmocked, and actually applies the proposal in memory)
        When main runs
        Then the default preview -- the screen an operator reads before adding
             --write -- names the proposal's verification state, not just JSON.
        """
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "toolguard_hook.toml"
            cfg_path.write_text(
                "[permissions]\n"
                "allow = [\n"
                '  "Bash(git diff:*)",\n'
                '  "Bash(git status:*)",\n'
                '  "Bash(git log:*)",\n'
                "]\n"
            )
            provenance = Provenance(
                level="project",
                source_type="toolguard_hook",
                file_format="toml",
                path=cfg_path,
                specificity=0,
            )
            config = _make_config(
                _make_layer(
                    "Bash",
                    allow=["git diff:*", "git status:*", "git log:*"],
                    provenance=provenance,
                )
            )
            buffer = io.StringIO()
            with mock.patch(
                "toolguard.tools.maintenance.load_config", return_value=config
            ):
                with redirect_stdout(buffer):
                    code = main(["--tool", "Bash", "--apply"])
        self.assertEqual(code, 0)
        out = buffer.getvalue()
        self.assertIn("[UNVERIFIED]", out)
        self.assertIn("DRY RUN", out)

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
        self.assertEqual(payload["files"][0]["diff"], "--- a\n+++ b\n")
        self.assertEqual(payload["files"][0]["patterns_removed"], ["Bash(git diff:*)"])
        self.assertEqual(
            payload["files"][0]["patterns_added"],
            ["Bash([regex]^git (diff|log|status))"],
        )
        self.assertEqual(
            payload["files_written"], ["/proj/.claude/toolguard_hook.toml"]
        )

    def test_render_apply_inlines_each_changed_file_diff(self):
        """
        Given a change report with one file carrying a unified diff
        When _render_apply renders it
        Then the file's path and its diff body appear under the summary -- for
            a preview the diff is the whole point, and render_change_report
            deliberately leaves it out.
        """
        fchange = FileChange(
            path=Path("/proj/.claude/toolguard_hook.toml"),
            file_format="toml",
            applied=(),
            skipped=(),
            patterns_removed=("Bash(git diff:*)",),
            patterns_added=("Bash([regex]^git (diff|log|status))",),
            diff="--- a\n+++ b\n-Bash(git diff:*)\n",
            written=False,
        )
        out = _render_apply(ChangeReport(files=(fchange,)), "text")
        self.assertIn("Diff: /proj/.claude/toolguard_hook.toml", out)
        self.assertIn("-Bash(git diff:*)", out)

    def test_apply_preview_is_dry_run_and_writes_nothing(self):
        """
        Given --apply without --write
        When main runs (apply_proposals patched to observe the call)
        Then apply_proposals is called with dry_run=True, the pre-flight gate is
            NOT consulted, and the banner reports a dry run.
        """
        buffer = io.StringIO()
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.apply_proposals",
                return_value=ChangeReport(files=()),
            ) as apply,
            mock.patch("toolguard.tools.maintenance.migration_preflight") as preflight,
        ):
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
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.migration_preflight", return_value=blocked
            ),
            mock.patch("toolguard.tools.maintenance.apply_proposals") as apply,
        ):
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
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.migration_preflight", return_value=clean
            ),
            mock.patch(
                "toolguard.tools.maintenance.apply_proposals",
                return_value=ChangeReport(files=()),
            ) as apply,
        ):
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
        with (
            mock.patch(
                "toolguard.tools.maintenance.load_config",
                return_value=self._git_config(),
            ),
            mock.patch(
                "toolguard.tools.maintenance.apply_proposals",
                return_value=ChangeReport(files=()),
            ),
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

    def _config_with_real_file(
        self, tmpdir: str, tagged: bool, reason: str = ": audited manually"
    ) -> Configuration:
        """Write a real toolguard_hook.toml, optionally #NOSECURITY-tagging 'git diff:*', and return its Configuration."""
        lines = []
        for body in self._ALLOWS:
            if tagged and body == "git diff:*":
                lines.append(f"    'Bash({body})',  # NOSECURITY{reason}")
            else:
                lines.append(f"    'Bash({body})',")
        text = (
            "[permissions]\nallow = [\n"
            + "\n".join(lines)
            + "\n]\ndeny = []\nask = []\n"
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

    def test_a_bare_nosecurity_tag_with_no_reason_still_withholds(self):
        """
        Given 'git diff:*' tagged '# NOSECURITY' with NO reason after it
        When _partition_nosecurity runs over the collected consolidations
        Then the proposal is still withheld, carrying the empty reason --
            an untagged rule and a rule tagged without a reason are both
            falsy, and only the untagged one may be rewritten.
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True, reason=""), tools=["Bash"]
            )
            proposals = collect_consolidations(report)
            self.assertTrue(proposals)
            self.assertEqual(_nosecurity_block_reason(proposals[0]), "")
            appliable, withheld = _partition_nosecurity(proposals)
            self.assertEqual(appliable, [])
            self.assertEqual([r for _p, r in withheld], [""])

    def test_a_withheld_proposal_is_never_handed_to_the_writer(self):
        """
        Given the same git family, once #NOSECURITY-blessed and once not
        When _run_apply runs over each
        Then apply_proposals -- the function that actually edits the file --
            is handed the proposal in the untagged case and NOTHING in the
            blessed case.

        Both directions are checked because the JSON payload's edit_proposals
        list is built separately from the apply call: a report that correctly
        names the rule as withheld can sit above an apply call that rewrites it
        anyway, and an empty hand-off proves nothing without the control.
        """

        def _handed_to_apply(tagged: bool):
            with tempfile.TemporaryDirectory() as d:
                report = run_maintenance(
                    self._config_with_real_file(d, tagged=tagged), tools=["Bash"]
                )
                self.assertTrue(collect_consolidations(report), "fixture must propose")
                args = argparse.Namespace(write=False, format="json", dir=d)
                with mock.patch(
                    "toolguard.tools.maintenance.apply_proposals",
                    return_value=ChangeReport(files=()),
                ) as apply:
                    with redirect_stdout(io.StringIO()):
                        self.assertEqual(_run_apply(args, report), 0)
                handed = apply.call_args.args[0]
                return [p for prop in handed for p in prop.removed_patterns]

        self.assertIn("git diff:*", _handed_to_apply(tagged=False))
        self.assertEqual(_handed_to_apply(tagged=True), [])

    def test_apply_text_output_names_the_withheld_rule_and_its_reason(self):
        """
        Given --apply in text mode over a #NOSECURITY-blessed git family
        When _run_apply renders the preview
        Then the human-readable output states that the rule was withheld and
            why -- the JSON contract is not the only surface a user reads.
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True), tools=["Bash"]
            )
            args = argparse.Namespace(write=False, format="text", dir=d)
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(_run_apply(args, report), 0)
            out = buf.getvalue()
            self.assertIn("Withheld (blessed by #NOSECURITY", out)
            self.assertIn("git diff:*", out)
            self.assertIn("#NOSECURITY: audited manually", out)

    def test_a_write_that_applied_nothing_reports_zero_files_written(self):
        """
        Given --apply --write where EVERY proposal was withheld
        When _run_apply runs with a clean pre-flight
        Then the output still reports '0 file(s) written' alongside its
            "APPLIED" banner, so a run that changed nothing is distinguishable
            from one that changed something (the banner alone is not).
        """
        with tempfile.TemporaryDirectory() as d:
            report = run_maintenance(
                self._config_with_real_file(d, tagged=True), tools=["Bash"]
            )
            args = argparse.Namespace(write=True, format="text", dir=d)
            buf = io.StringIO()
            with (
                mock.patch(
                    "toolguard.tools.maintenance.migration_preflight",
                    return_value=mock.Mock(blockers=[]),
                ),
                mock.patch(
                    "toolguard.tools.maintenance.apply_proposals",
                    return_value=ChangeReport(files=()),
                ),
            ):
                with redirect_stdout(buf):
                    self.assertEqual(_run_apply(args, report), 0)
            self.assertIn("0 applied, 0 skipped, 0 file(s) written.", buf.getvalue())
            self.assertIn("Withheld (blessed by #NOSECURITY", buf.getvalue())

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


class TestAnnotateMode(unittest.TestCase):
    """The --annotate mode previews/writes '# toolguard:' clarity comments, gated."""

    def _confusing_config(self, tmpdir: str) -> Configuration:
        """Write a real toolguard_hook.toml with a confusing git:*/git push:* interaction and return its Configuration."""
        text = (
            "[permissions]\n"
            "allow = [\n"
            "    # human note stays\n"
            "    'Bash(git:*)',\n"
            "]\n"
            "deny = [\n"
            "    'Bash(git push:*)',\n"
            "]\n"
            "ask = []\n"
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
        layer = _make_layer("Bash", allow=["git:*"], deny=["git push:*"])
        layer = ConfigLayer(provenance=prov, content=layer.content)
        return _make_config(layer)

    def test_collect_annotations_groups_confusing_rule_by_file(self):
        """
        Given a config with a confusing 'git:*' allow
        When _collect_annotations runs for Bash
        Then the rule's file maps 'Bash(git:*)' to at least one note
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            merged = _collect_annotations(config, ["Bash"])
            path = Path(d) / "toolguard_hook.toml"
            self.assertIn(path, merged)
            self.assertIn("Bash(git:*)", merged[path])

    def test_dry_run_json_shows_diff_and_writes_nothing(self):
        """
        Given --annotate --format json (no --write)
        When _run_annotate runs
        Then it reports dry_run True with a diff adding a '# toolguard:' line, and
            the file on disk is unchanged
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            path = Path(d) / "toolguard_hook.toml"
            before = path.read_text(encoding="utf-8")
            args = argparse.Namespace(write=False, format="json", dir=d, tool=["Bash"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = _run_annotate(args, config)
            self.assertEqual(code, 0)
            payload = json.loads(buf.getvalue())
            self.assertTrue(payload["dry_run"])
            self.assertEqual(payload["total_changed"], 1)
            self.assertIn("# toolguard:", payload["files"][0]["diff"])
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_write_refused_when_no_project_boundary_can_be_established(self):
        """
        Given --annotate --write in a bare directory holding no project marker
        When _run_annotate runs
        Then it refuses (exit 2), NAMES the project-boundary blocker, and
            leaves the file untouched.

        The blocker is asserted because a bare temp dir trips the project-root
        gate, not the work-tree gate this test was previously described as
        exercising -- exit code 2 alone cannot tell the two apart.
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            path = Path(d) / "toolguard_hook.toml"
            before = path.read_text(encoding="utf-8")
            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = _run_annotate(args, config)
            self.assertEqual(code, 2)
            self.assertIn("Refusing to write annotations", buf.getvalue())
            self.assertIn("project boundary cannot be established", buf.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_write_refused_when_the_project_root_is_not_a_git_work_tree(self):
        """
        Given --annotate --write where a project marker exists but the root is
            not a git work tree
        When _run_annotate runs
        Then it refuses (exit 2) naming the work-tree blocker -- a change that
            could not be reviewed or reverted is never written.
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            (Path(d) / "CLAUDE.md").write_text("marker\n", encoding="utf-8")
            path = Path(d) / "toolguard_hook.toml"
            before = path.read_text(encoding="utf-8")
            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            buf = io.StringIO()
            with redirect_stdout(buf):
                code = _run_annotate(args, config)
            self.assertEqual(code, 2)
            self.assertIn("not a git work tree", buf.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_write_with_clean_preflight_routes_through_verified_write_config(self):
        """
        Given --annotate --write with a clean (no-blocker) pre-flight
        When _run_annotate runs
        Then toolguard.tools.maintenance.verified_write_config is called with
            file_format="toml" and expected_patterns covering every rule
            pattern that was already in the file (TOO-19 corrective change:
            annotation must never silently drop a rule)
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            path = Path(d) / "toolguard_hook.toml"
            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            clean = mock.Mock(blockers=[])
            with mock.patch(
                "toolguard.tools.maintenance.migration_preflight", return_value=clean
            ):
                with mock.patch(
                    "toolguard.tools.maintenance.verified_write_config"
                ) as mock_write:
                    buf = io.StringIO()
                    with redirect_stdout(buf):
                        code = _run_annotate(args, config)
            self.assertEqual(code, 0)
            mock_write.assert_called_once()
            call_args, call_kwargs = mock_write.call_args
            self.assertEqual(call_args[0], path)
            self.assertEqual(call_args[2], "toml")
            self.assertEqual(
                set(call_kwargs["expected_patterns"]),
                {"Bash(git:*)", "Bash(git push:*)"},
            )

    def test_an_annotation_that_would_drop_a_rule_is_refused(self):
        """
        Given --annotate --write, a clean pre-flight, and an annotator that
            (contrary to its contract) returns text with 'Bash(git push:*)'
            deleted
        When _run_annotate runs
        Then verified_write_config refuses, the exception names the dropped
            pattern, and the file on disk is untouched.

        This is the TOO-19 corrective change the sibling test names but cannot
        observe: annotation never changes a rule, so expected_patterns taken
        from the PRE-annotation text and from the post-annotation text agree on
        every real input. Only a would-be loss separates them.
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            path = Path(d) / "toolguard_hook.toml"
            before = path.read_text(encoding="utf-8")

            def _lossy(target: Path, notes) -> Tuple[str, str]:
                old = target.read_text(encoding="utf-8")
                return old, old.replace("    'Bash(git push:*)',\n", "")

            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            with (
                mock.patch(
                    "toolguard.tools.maintenance.migration_preflight",
                    return_value=mock.Mock(blockers=[]),
                ),
                mock.patch("toolguard.tools.maintenance.annotate_config_file", _lossy),
            ):
                with redirect_stdout(io.StringIO()):
                    with self.assertRaises(ConfigWriteVerificationError) as caught:
                        _run_annotate(args, config)
            self.assertIn("Bash(git push:*)", str(caught.exception))
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_annotating_an_already_annotated_file_writes_nothing(self):
        """
        Given a config file that a previous --annotate --write pass already
            annotated
        When _run_annotate runs again
        Then it reports zero changed files and says there is nothing to write
            -- the documented idempotence, and the reason the results list is
            filtered to files whose text actually changed.
        """
        with tempfile.TemporaryDirectory() as d:
            config = self._confusing_config(d)
            path = Path(d) / "toolguard_hook.toml"
            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            clean = mock.Mock(blockers=[])
            with mock.patch(
                "toolguard.tools.maintenance.migration_preflight", return_value=clean
            ):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(_run_annotate(args, config), 0)
                annotated = path.read_text(encoding="utf-8")
                self.assertIn("# toolguard:", annotated)

                buf = io.StringIO()
                with redirect_stdout(buf):
                    self.assertEqual(_run_annotate(args, config), 0)
            self.assertIn("No clarity annotations to write", buf.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), annotated)

    def test_permission_patterns_in_text_without_a_permissions_section(self):
        """
        Given text with no [permissions] section at all
        When _permission_patterns_in_text extracts expected_patterns
        Then it returns an empty list rather than raising or scanning the
            whole file.
        """
        self.assertEqual(_permission_patterns_in_text(""), [])
        self.assertEqual(
            _permission_patterns_in_text("[hard_deny]\ndeny = ['Bash(rm -rf /)']\n"), []
        )

    def test_permission_patterns_in_text_excludes_malformed_entry(self):
        """
        Given [permissions] text whose allow list holds a valid string entry
            AND a structured entry MISSING its "match" key
        When _permission_patterns_in_text() extracts expected_patterns
        Then only the real pattern is returned -- the malformed entry's
            synthesized repr()-based value is excluded (TOO-19 review-round-2
            fix): it can never appear in the annotated text this function's
            caller writes, so including it previously made annotation on such
            a file always refuse (confirmed repro)
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls)",\n'
            '  { additionalContext = "oops" },\n'
            "]\n"
        )
        self.assertEqual(_permission_patterns_in_text(text), ["Bash(ls)"])

    def test_annotate_write_survives_a_malformed_structured_entry_in_the_file(self):
        """
        Given a real toolguard_hook.toml whose [permissions] allow list
            includes a confusing rule (annotatable) PLUS a structured entry
            missing its "match" key, and a clean pre-flight
        When --annotate --write runs via _run_annotate
        Then the write succeeds (no ConfigWriteVerificationError bubbling
            out) and the malformed entry survives verbatim in the file --
            end-to-end confirmation of the maintenance.py-side fix
        """
        with tempfile.TemporaryDirectory() as d:
            text = (
                "[permissions]\n"
                "allow = [\n"
                "    'Bash(git:*)',\n"
                '    { additionalContext = "oops" },\n'
                "]\n"
                "deny = [\n"
                "    'Bash(git push:*)',\n"
                "]\n"
                "ask = []\n"
            )
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(text, encoding="utf-8")
            prov = Provenance(
                level="project",
                source_type="toolguard_hook",
                file_format="toml",
                path=path,
                specificity=0,
            )
            layer = _make_layer("Bash", allow=["git:*"], deny=["git push:*"])
            layer = ConfigLayer(provenance=prov, content=layer.content)
            config = _make_config(layer)

            args = argparse.Namespace(write=True, format="text", dir=d, tool=["Bash"])
            clean = mock.Mock(blockers=[])
            with mock.patch(
                "toolguard.tools.maintenance.migration_preflight", return_value=clean
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = _run_annotate(args, config)

            self.assertEqual(code, 0)
            written = path.read_text(encoding="utf-8")
            self.assertIn('{ additionalContext = "oops" }', written)
            self.assertIn("# toolguard:", written)

    def test_apply_and_annotate_are_mutually_exclusive(self):
        """
        Given both --apply and --annotate
        When main parses the arguments
        Then it errors out (they are separate modes)
        """
        with self.assertRaises(SystemExit):
            main(["--apply", "--annotate"])

    def test_write_requires_apply_or_annotate(self):
        """
        Given --write with neither --apply nor --annotate
        When main parses the arguments
        Then it errors out
        """
        with self.assertRaises(SystemExit):
            main(["--write"])


class TestReplayCandidate(unittest.TestCase):
    """Corpus-validation mode: replay the corpus against current vs candidate config."""

    def _broadened_and_tightened(self):
        """
        Build (config_a, config_b, corpus) where one command is broadened and one
        tightened, then return the resulting ReplayDiff.
        """
        config_a = _make_config(
            _make_layer("Bash", allow=["rm:*"], deny=["git push:*"])
        )
        config_b = _make_config(
            _make_layer("Bash", allow=["git push:*"], deny=["rm:*"])
        )
        corpus = [
            _make_log_entry("Bash", "git push origin main"),
            _make_log_entry("Bash", "rm -rf /tmp/x"),
        ]
        return replay(corpus, config_a, config_b)

    def test_serializer_reports_broadened_and_tightened(self):
        """
        Given a candidate that admits a previously-denied command and denies a
          previously-allowed one
        When the replay diff is serialized for the skill
        Then the counts and the broadened/tightened command lists reflect both
        """
        diff = self._broadened_and_tightened()
        payload = replay_diff_to_dict(diff, corpus_size=2)["replay_candidate"]

        self.assertEqual(payload["corpus_size"], 2)
        self.assertEqual(payload["broadened"], 1)
        self.assertEqual(payload["tightened"], 1)
        broadened = payload["broadened_commands"]
        self.assertEqual(len(broadened), 1)
        self.assertEqual(broadened[0]["command"], "git push origin main")
        self.assertEqual(broadened[0]["verdict_before"], "deny")
        self.assertEqual(broadened[0]["verdict_after"], "allow")
        self.assertEqual(payload["tightened_commands"][0]["command"], "rm -rf /tmp/x")

    def test_render_flags_broadened_with_caveat(self):
        """
        Given a replay diff with a broadened command
        When it is rendered as text
        Then the broadened command and the necessary-not-sufficient caveat are shown
        """
        diff = self._broadened_and_tightened()
        text = _render_replay(diff, corpus_size=2)

        self.assertIn("BROADENED", text)
        self.assertIn("git push origin main", text)
        self.assertIn("Necessary, not sufficient", text)

    def test_empty_corpus_is_reported_vacuous_not_clean(self):
        """
        Given an empty corpus (no observations to replay)
        When the result is rendered
        Then it is called out as vacuous rather than presented as a clean pass
        """
        from toolguard.tools.replay import ReplayDiff

        text = _render_replay(ReplayDiff(), corpus_size=0)
        self.assertIn("vacuous", text)
        self.assertNotIn("BROADENED", text)

    def test_a_clean_replay_is_not_reported_the_way_a_vacuous_one_is(self):
        """
        Given a corpus replayed against an unchanged candidate (nothing moved)
        When the result is rendered
        Then it reports the observations it actually replayed and does NOT use
            the empty-corpus 'proves NOTHING' wording.

        The sibling test asserts the vacuous case; this is the other half. A
        clean pass and a replay that examined nothing both produce zero
        broadened and zero tightened counts, so only the wording separates
        them.
        """
        config = _make_config(_make_layer("Bash", allow=["rm:*"], deny=["git push:*"]))
        corpus = [
            _make_log_entry("Bash", "git push origin main"),
            _make_log_entry("Bash", "rm -rf /tmp/x"),
        ]
        diff = replay(corpus, config, config)
        text = _render_replay(diff, corpus_size=len(corpus))

        self.assertIn("Observations replayed: 2", text)
        self.assertIn("unchanged:                     2", text)
        self.assertNotIn("vacuous", text)
        self.assertNotIn("BROADENED", text)
        self.assertIn("Necessary, not sufficient", text)

    def test_cli_missing_candidate_dir_returns_2(self):
        """
        Given a --replay-candidate directory that does not exist
        When the CLI runs
        Then it prints an error and returns exit code 2 (no bogus clean result)
        """
        args = argparse.Namespace(
            dir=".",
            replay_candidate="/nonexistent/candidate/dir",
            max_age_days=2,
            format="json",
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _run_replay_candidate(args)
        self.assertEqual(rc, 2)
        self.assertIn("not found", buf.getvalue())

    def test_cli_dispatch_emits_replay_json(self):
        """
        Given a valid candidate directory and mocked config/corpus loading
        When the CLI runs in --replay-candidate JSON mode
        Then it emits the replay_candidate payload with the broadened command
        """
        config_a = _make_config(
            _make_layer("Bash", allow=["rm:*"], deny=["git push:*"])
        )
        config_b = _make_config(
            _make_layer("Bash", allow=["git push:*"], deny=["rm:*"])
        )
        corpus = [_make_log_entry("Bash", "git push origin main")]
        with tempfile.TemporaryDirectory() as candidate:
            with (
                mock.patch(
                    "toolguard.tools.maintenance.load_config",
                    side_effect=[config_a, config_b],
                ),
                mock.patch(
                    "toolguard.tools.maintenance.harvest_corpus",
                    return_value=corpus,
                ),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = main(
                        [
                            "--dir",
                            ".",
                            "--replay-candidate",
                            candidate,
                            "--format",
                            "json",
                        ]
                    )
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())["replay_candidate"]
        self.assertEqual(payload["broadened"], 1)
        self.assertEqual(
            payload["broadened_commands"][0]["command"], "git push origin main"
        )

    def test_cli_rejects_combining_with_apply(self):
        """
        Given --replay-candidate combined with --apply
        When the CLI parses arguments
        Then it exits (the two modes are mutually exclusive)
        """
        with self.assertRaises(SystemExit):
            main(["--replay-candidate", ".", "--apply"])


class TestLedgerMode(unittest.TestCase):
    """The prior-decision ledger CLI modes (--ledger-show / --record-decision)."""

    def setUp(self):
        """
        Redirect the USER ledger into this test's own temp dir.

        ``--ledger-show`` merges the user ledger with the project one, so
        without this every assertion on the merged result silently depends on
        the developer not having a ``~/.toolguard/decisions.json`` -- measured:
        one entry in that file fails two tests in this class.
        """
        self._user_ledger_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._user_ledger_dir.cleanup)
        self.user_ledger = Path(self._user_ledger_dir.name) / "decisions.json"
        patcher = mock.patch.object(
            decision_ledger, "user_ledger_path", return_value=self.user_ledger
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_user_level_decisions_are_merged_into_the_shown_ledger(self):
        """
        Given one decision recorded at project level and one at user level
        When --ledger-show --format json runs
        Then both are listed, each labelled with the level it came from.
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            for level, family in (("project", "proj-fam"), ("user", "user-fam")):
                entry = root / f"{level}.json"
                entry.write_text(
                    json.dumps({"kind": "custom", "family_id": family, "target": "t"})
                )
                with redirect_stdout(io.StringIO()):
                    rc = main(
                        [
                            "--dir",
                            str(root),
                            "--record-decision",
                            str(entry),
                            "--ledger-level",
                            level,
                        ]
                    )
                self.assertEqual(rc, 0)
            self.assertTrue(self.user_ledger.exists())
            buf = io.StringIO()
            with redirect_stdout(buf):
                self.assertEqual(
                    main(["--dir", str(root), "--ledger-show", "--format", "json"]), 0
                )
            payload = json.loads(buf.getvalue())
            self.assertEqual(
                sorted((d["family_id"], d["level"]) for d in payload),
                [("proj-fam", "project"), ("user-fam", "user")],
            )

    def test_record_then_show_roundtrips_via_cli(self):
        """
        Given a decision JSON recorded through --record-decision
        When --ledger-show --format json is run for the same project
        Then the recorded decision is listed with its level
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            entry = root / "dec.json"
            entry.write_text(
                json.dumps(
                    {
                        "kind": "reject-consolidation",
                        "family_id": "git-diff",
                        "target": "^git (diff|log)",
                        "rationale": "keep apart",
                    }
                )
            )
            with redirect_stdout(io.StringIO()):
                rc = main(
                    [
                        "--dir",
                        str(root),
                        "--record-decision",
                        str(entry),
                        "--ledger-level",
                        "project",
                    ]
                )
            self.assertEqual(rc, 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--dir", str(root), "--ledger-show", "--format", "json"])
            self.assertEqual(rc, 0)
            payload = json.loads(buf.getvalue())
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["family_id"], "git-diff")
            self.assertEqual(payload[0]["level"], "project")

    def test_show_empty_ledger_text(self):
        """
        Given a project with no recorded decisions
        When --ledger-show runs in text mode
        Then it reports that no prior decisions exist (not an error)
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--dir", str(root), "--ledger-show"])
            self.assertEqual(rc, 0)
            self.assertIn("No prior maintenance decisions", buf.getvalue())

    def test_render_ledger_lists_each_decision(self):
        """
        Given a merged ledger with one decision
        When it is rendered as text
        Then the level, disposition, kind, family, and rationale appear
        """
        from toolguard.tools.decision_ledger import new_decision

        text = _render_ledger(
            [
                new_decision(
                    "reject-promotion",
                    "rm",
                    "promote:user",
                    "reject",
                    "too broad",
                    "user",
                )
            ]
        )
        self.assertIn("[user] reject: reject-promotion on rm", text)
        self.assertIn("too broad", text)

    def test_record_missing_file_returns_2(self):
        """
        Given a --record-decision path that does not exist
        When _run_record_decision runs
        Then it prints an error and returns exit code 2
        """
        args = argparse.Namespace(
            dir=".", record_decision="/nonexistent/dec.json", ledger_level="project"
        )
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _run_record_decision(args)
        self.assertEqual(rc, 2)
        self.assertIn("cannot read", buf.getvalue())

    def test_record_malformed_entry_returns_2(self):
        """
        Given a decision JSON missing the required 'target' field
        When _run_record_decision runs
        Then it reports the malformed entry and returns exit code 2
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            entry = root / "bad.json"
            entry.write_text(json.dumps({"kind": "custom", "family_id": "x"}))
            args = argparse.Namespace(
                dir=str(root), record_decision=str(entry), ledger_level="project"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = _run_record_decision(args)
            self.assertEqual(rc, 2)
            self.assertIn("malformed", buf.getvalue())

    def test_record_omitting_decision_defaults_to_reject(self):
        """
        Given a decision entry that omits the optional 'decision' field
        When it is recorded and read back
        Then the recorded disposition is 'reject' (the documented default)
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            entry = root / "dec.json"
            entry.write_text(
                json.dumps({"kind": "custom", "family_id": "fam", "target": "t"})
            )
            args = argparse.Namespace(
                dir=str(root), record_decision=str(entry), ledger_level="project"
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(_run_record_decision(args), 0)
            buf = io.StringIO()
            with redirect_stdout(buf):
                main(["--dir", str(root), "--ledger-show", "--format", "json"])
            self.assertEqual(json.loads(buf.getvalue())[0]["decision"], "reject")

    def test_record_batch_with_bad_entry_is_atomic(self):
        """
        Given a JSON list of decisions whose last entry is malformed
        When --record-decision processes the batch
        Then it returns 2 AND persists none of the earlier valid entries (atomic)
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            entry = root / "batch.json"
            entry.write_text(
                json.dumps(
                    [
                        {"kind": "custom", "family_id": "a", "target": "t"},
                        {"kind": "custom", "family_id": "b", "target": "t"},
                        {"kind": "custom", "family_id": "c"},
                    ]
                )
            )
            args = argparse.Namespace(
                dir=str(root), record_decision=str(entry), ledger_level="project"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = _run_record_decision(args)
            self.assertEqual(rc, 2)
            self.assertIn("malformed", buf.getvalue())
            self.assertFalse((root / ".claude" / "toolguard_decisions.json").exists())

    def test_record_rejects_combining_with_apply(self):
        """
        Given --record-decision combined with --apply
        When the CLI parses arguments
        Then it exits (the ledger write mode and apply are mutually exclusive)
        """
        with self.assertRaises(SystemExit):
            main(["--record-decision", "x.json", "--apply"])

    def test_ledger_show_malformed_returns_2(self):
        """
        Given a project whose ledger file is corrupt JSON
        When --ledger-show runs
        Then it reports the error and returns exit code 2 (never a bogus empty list)
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / ".git").mkdir()
            (root / ".claude").mkdir()
            (root / ".claude" / "toolguard_decisions.json").write_text("{ not json")
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = main(["--dir", str(root), "--ledger-show"])
            self.assertEqual(rc, 2)
            self.assertIn("cannot read", buf.getvalue())

    def test_ledger_show_rejects_combining_with_record(self):
        """
        Given --ledger-show combined with --record-decision
        When the CLI parses arguments
        Then it exits (the ledger modes are mutually exclusive)
        """
        with self.assertRaises(SystemExit):
            main(["--ledger-show", "--record-decision", "x.json"])


if __name__ == "__main__":
    unittest.main()
