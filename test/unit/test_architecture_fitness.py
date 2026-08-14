"""
Unit tests for ``tools/architecture_fitness.py``.

Graph and layer logic are tested against small SYNTHETIC fixture trees (temp
directories built per test), not the live ``toolguard/`` tree -- assertions pinned
to today's real module set would break on every refactor step, which is what this
tool exists to survive. A handful of smoke tests at the bottom exercise the real
tree/repo and assert only that each mode runs without crashing and returns a sane
shape.
"""

import ast
import inspect
import io
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

# Repo-root ``tools/`` (dev-only, NOT ``toolguard/tools/``) is importable when the
# suite runs with ``-t .`` (top-level dir on sys.path); mirror that explicitly so
# this file also runs standalone via ``python -m unittest test.unit....``.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools import architecture_fitness as af


def _write(path: Path, content: str) -> None:
    """Create *path*'s parent directories and write *content* to it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _run(cmd, cwd):
    """Run *cmd* in *cwd*, raising on failure -- a thin subprocess.run wrapper for fixtures."""
    subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)


def _init_git_repo(root: Path) -> None:
    """Initialise a git repo at *root* with a committer identity, for fixtures."""
    _run(["git", "init", "-q"], cwd=root)
    _run(["git", "config", "user.email", "test@example.com"], cwd=root)
    _run(["git", "config", "user.name", "Test"], cwd=root)


def _commit_all(root: Path, message: str) -> str:
    """Stage everything and commit with *message*; return the new commit's SHA."""
    _run(["git", "add", "-A"], cwd=root)
    _run(["git", "commit", "-q", "-m", message], cwd=root)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _write_stub_hook_binary(path: Path, body: str) -> Path:
    """Write an executable stub at *path* mimicking the hook's PreToolUse I/O contract; *body* is a Python expression bound to ``event`` that yields the verdict string."""
    script = (
        f"#!{sys.executable}\n"
        "import json, sys\n"
        "event = json.loads(sys.stdin.read())\n"
        f"verdict = ({body})\n"
        'print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", '
        '"permissionDecision": verdict, "permissionDecisionReason": "stub"}}))\n'
    )
    path.write_text(script, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


class TestModulePathHelpers(unittest.TestCase):
    """Tests for the pure path/module-name helpers."""

    def test_relative_module_path_top_level_module(self):
        """
        Given a top-level file directly under the package root
        When relative_module_path is called
        Then it returns the bare filename with no extension
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "hook.py"
            f.touch()
            self.assertEqual(af.relative_module_path(f, root), "hook")

    def test_relative_module_path_nested_module(self):
        """
        Given a file nested one package deep
        When relative_module_path is called
        Then it returns a dotted path with the package as the first segment
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "tools" / "decision.py"
            f.parent.mkdir()
            f.touch()
            self.assertEqual(af.relative_module_path(f, root), "tools.decision")

    def test_relative_module_path_package_init(self):
        """
        Given a subpackage's __init__.py
        When relative_module_path is called
        Then it maps to the containing package name, not "__init__"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "tools" / "__init__.py"
            f.parent.mkdir()
            f.touch()
            self.assertEqual(af.relative_module_path(f, root), "tools")

    def test_relative_module_path_root_init_is_empty(self):
        """
        Given the package root's own __init__.py
        When relative_module_path is called
        Then it returns "" -- the container, not a layer member
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "__init__.py"
            f.touch()
            self.assertEqual(af.relative_module_path(f, root), "")

    def test_first_segment(self):
        """
        Given dotted paths of varying depth
        When first_segment is called
        Then it returns the leading component, or "" for the empty string
        """
        self.assertEqual(af.first_segment("tools.decision"), "tools")
        self.assertEqual(af.first_segment("hook"), "hook")
        self.assertEqual(af.first_segment(""), "")

    def test_resolve_toolguard_import_absolute(self):
        """
        Given an absolute "toolguard.tools.decision" import
        When resolve_toolguard_import is called
        Then it strips the "toolguard." prefix
        """
        self.assertEqual(
            af.resolve_toolguard_import("toolguard.tools.decision", 0, "hook"),
            "tools.decision",
        )

    def test_resolve_toolguard_import_absolute_non_toolguard_is_none(self):
        """
        Given an absolute import of an unrelated package
        When resolve_toolguard_import is called
        Then it returns None
        """
        self.assertIsNone(af.resolve_toolguard_import("os.path", 0, "hook"))

    def test_resolve_toolguard_import_relative_level_1(self):
        """
        Given a "from . import x" (level=1) inside a nested module
        When resolve_toolguard_import is called
        Then it resolves relative to the importer's own package
        """
        self.assertEqual(
            af.resolve_toolguard_import("sorters", 1, "tools.decision"), "tools.sorters"
        )

    def test_resolve_toolguard_import_relative_level_2(self):
        """
        Given a "from .. import x" (level=2) inside a nested module
        When resolve_toolguard_import is called
        Then it climbs one more package level than level=1
        """
        self.assertEqual(
            af.resolve_toolguard_import("hook", 2, "tools.decision"), "hook"
        )

    def test_zone_of_and_zone_of_repo_path(self):
        """
        Given toolguard-relative and repo-relative paths in each zone
        When zone_of / zone_of_repo_path are called
        Then core defaults apply and tools/parser/scripts/testing are recognised
        """
        self.assertEqual(af.zone_of("hook"), "core")
        self.assertEqual(af.zone_of("tools.decision"), "tools")
        self.assertEqual(af.zone_of("parser.bash_parser"), "parser")
        self.assertEqual(af.zone_of("scripts.migrate_permissions"), "scripts")
        self.assertEqual(af.zone_of("testing.sandbox"), "testing")
        self.assertEqual(af.zone_of_repo_path("toolguard/hook.py"), "core")
        self.assertEqual(af.zone_of_repo_path("toolguard/tools/decision.py"), "tools")

    def test_production_files_filters_non_toolguard_paths(self):
        """
        Given a mix of toolguard, test, and doc paths
        When production_files is called
        Then only toolguard/*.py paths survive
        """
        files = [
            "toolguard/hook.py",
            "test/unit/test_hook.py",
            "README.md",
            "toolguard/tools/decision.py",
        ]
        self.assertEqual(
            af.production_files(files),
            ["toolguard/hook.py", "toolguard/tools/decision.py"],
        )

    def test_production_files_drops_excluded_paths(self):
        """
        Given a set of toolguard/*.py paths and an explicit excluded set
            (the shape --metrics passes for generated files)
        When production_files is called
        Then the excluded path is dropped even though it otherwise matches
        """
        files = ["toolguard/hook.py", "toolguard/parser/bash_parser.py"]
        self.assertEqual(
            af.production_files(files, frozenset({"toolguard/parser/bash_parser.py"})),
            ["toolguard/hook.py"],
        )


class TestGeneratedFileDetection(unittest.TestCase):
    """Tests for is_generated_file / iter_source_files / list_generated_files / generated_repo_paths."""

    def test_is_generated_file_detects_each_marker(self):
        """
        Given a file whose header carries each of the documented generated-code banners
        When is_generated_file is called
        Then it returns True for every one, case-insensitively
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            banners = [
                "# This file was generated from grammar.peg\n",
                "# DO NOT EDIT -- hand edits will be overwritten\n",
                "# @generated by some-tool\n",
                "# autogenerated, do not touch\n",
                "# GENERATED FROM foo.peg\n",  # case-insensitivity
            ]
            for i, banner in enumerate(banners):
                f = root / f"g{i}.py"
                _write(f, banner + "x = 1\n")
                self.assertTrue(af.is_generated_file(f), banner)

    def test_is_generated_file_false_for_ordinary_file(self):
        """
        Given an ordinary hand-written file with no banner
        When is_generated_file is called
        Then it returns False
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "a.py"
            _write(f, '"""An ordinary module."""\nx = 1\n')
            self.assertFalse(af.is_generated_file(f))

    def test_iter_source_files_excludes_generated(self):
        """
        Given one generated file and one ordinary file
        When iter_source_files is called
        Then only the ordinary file is returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "generated.py", "# generated from x.peg\nx = 1\n")
            _write(root / "hand_written.py", "x = 1\n")
            names = {p.name for p in af.iter_source_files(root)}
            self.assertEqual(names, {"hand_written.py"})

    def test_list_generated_files_reports_dotted_path(self):
        """
        Given a generated file nested one package deep
        When list_generated_files is called
        Then its toolguard-relative dotted path is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "parser" / "gen.py", "# generated from x.peg\nx = 1\n")
            self.assertEqual(af.list_generated_files(root), ["parser.gen"])

    def test_generated_repo_paths_reports_repo_relative_posix_path(self):
        """
        Given a generated file inside a synthetic toolguard/ under a synthetic repo root
        When generated_repo_paths is called
        Then it reports the path relative to the repo root, matching git's own spelling
        """
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            toolguard_dir = repo_root / "toolguard"
            _write(
                toolguard_dir / "parser" / "gen.py", "# generated from x.peg\nx = 1\n"
            )
            paths = af.generated_repo_paths(toolguard_dir, repo_root)
            self.assertEqual(paths, {"toolguard/parser/gen.py"})


class TestImportGraphExtraction(unittest.TestCase):
    """Tests for extract_toolguard_imports and build_import_graph on synthetic trees."""

    def test_extract_toolguard_imports_module_level(self):
        """
        Given a module-level "from toolguard.x import y"
        When extract_toolguard_imports is called
        Then the edge is reported with is_local=False
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "from toolguard.b import thing\n")
            edges = af.extract_toolguard_imports(root / "a.py", root)
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].imported, "b")
            self.assertFalse(edges[0].is_local)

    def test_extract_toolguard_imports_function_local(self):
        """
        Given a function-local "from toolguard.x import y" (the hook.py<->tools.decision shape)
        When extract_toolguard_imports is called
        Then the edge is still found, marked is_local=True
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def f():\n    from toolguard.b import thing\n    return thing\n",
            )
            edges = af.extract_toolguard_imports(root / "a.py", root)
            self.assertEqual(len(edges), 1)
            self.assertTrue(edges[0].is_local)

    def test_extract_toolguard_imports_ignores_stdlib(self):
        """
        Given only stdlib/third-party imports
        When extract_toolguard_imports is called
        Then no edges are reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "import os\nimport sys\nfrom pathlib import Path\n")
            self.assertEqual(af.extract_toolguard_imports(root / "a.py", root), [])

    def test_build_import_graph_synthetic_tree(self):
        """
        Given a small synthetic package with two cross-referencing modules
        When build_import_graph is called
        Then the graph contains both nodes and the edge between them
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "from toolguard.b import thing\n")
            _write(root / "b.py", "x = 1\n")
            graph = af.build_import_graph(root)
            self.assertIn("a", graph)
            self.assertIn("b", graph)
            self.assertEqual(graph["a"], {"b"})


SYNTHETIC_ARCH_TOML = """
[architecture]
enabled = true

[[architecture.layers]]
name = "base"
packages = ["a"]

[[architecture.layers]]
name = "top"
packages = ["b"]

[[architecture.rules]]
from = "base"
allow = ["base"]

[[architecture.rules]]
from = "top"
allow = ["top", "base"]
"""


class TestArchitectureConfigParsing(unittest.TestCase):
    """Tests for parse_architecture_config against a small synthetic .pyscn.toml."""

    def test_parse_architecture_config(self):
        """
        Given a minimal synthetic .pyscn.toml with two layers and two rules
        When parse_architecture_config is called
        Then layers and rules are parsed with the expected names and members
        """
        with tempfile.TemporaryDirectory() as tmp:
            toml_path = Path(tmp) / ".pyscn.toml"
            toml_path.write_text(SYNTHETIC_ARCH_TOML, encoding="utf-8")
            arch = af.parse_architecture_config(toml_path)
            self.assertEqual({layer.name for layer in arch.layers}, {"base", "top"})
            self.assertEqual(arch.package_to_layer(), {"a": "base", "b": "top"})
            self.assertEqual(arch.allow_for("base"), ("base",))
            self.assertEqual(arch.allow_for("top"), ("top", "base"))
            self.assertEqual(arch.allow_for("nonexistent"), ())


class TestCheckLayers(unittest.TestCase):
    """Tests for check_layers against small synthetic trees."""

    def _arch(self, tmp: Path):
        """Write SYNTHETIC_ARCH_TOML into *tmp* and return the parsed ArchitectureConfig."""
        toml_path = tmp / ".pyscn.toml"
        toml_path.write_text(SYNTHETIC_ARCH_TOML, encoding="utf-8")
        return af.parse_architecture_config(toml_path)

    def test_completeness_all_mapped(self):
        """
        Given every module's first path segment matches a declared package
        When check_layers is called
        Then the report is ok with no unmapped or multiply-mapped modules
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arch = self._arch(root)
            _write(root / "a.py", "x = 1\n")
            _write(root / "b.py", "x = 1\n")
            report = af.check_layers(root, arch)
            self.assertEqual(report.unmapped, [])
            self.assertEqual(report.multiply_mapped, {})

    def test_completeness_flags_unmapped_module(self):
        """
        Given a module whose first path segment matches no declared package
        When check_layers is called
        Then it is named in report.unmapped and the report is not ok
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arch = self._arch(root)
            _write(root / "a.py", "x = 1\n")
            _write(root / "mystery.py", "x = 1\n")
            report = af.check_layers(root, arch)
            self.assertIn("mystery", report.unmapped)
            self.assertFalse(report.ok)

    def test_direction_flags_upward_import(self):
        """
        Given "base" (allowed only to import itself) importing from "top"
        When check_layers is called
        Then a violation is reported naming both modules, layers, and the line
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arch = self._arch(root)
            _write(root / "a.py", "from toolguard.b import thing\n")
            _write(root / "b.py", "x = 1\n")
            report = af.check_layers(root, arch)
            self.assertFalse(report.ok)
            self.assertEqual(len(report.violations), 1)
            v = report.violations[0]
            self.assertEqual(v["source_module"], "a")
            self.assertEqual(v["source_layer"], "base")
            self.assertEqual(v["target_module"], "b")
            self.assertEqual(v["target_layer"], "top")

    def test_direction_allows_downward_import(self):
        """
        Given "top" (allowed to import "top" and "base") importing from "base"
        When check_layers is called
        Then no violation is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arch = self._arch(root)
            _write(root / "a.py", "x = 1\n")
            _write(root / "b.py", "from toolguard.a import thing\n")
            report = af.check_layers(root, arch)
            self.assertEqual(report.violations, [])

    def test_render_layers_text_produces_readable_output(self):
        """
        Given a LayerReport with one violation
        When render_layers_text is called
        Then the output is a non-empty string mentioning the violation
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            arch = self._arch(root)
            _write(root / "a.py", "from toolguard.b import thing\n")
            _write(root / "b.py", "x = 1\n")
            report = af.check_layers(root, arch)
            text = af.render_layers_text(report)
            self.assertIn("VIOLATIONS", text)
            self.assertIn("a", text)


class TestGraphAlgorithms(unittest.TestCase):
    """Tests for tarjan_scc, fan_in, and longest_dependency_chain on synthetic graphs."""

    def test_tarjan_scc_finds_a_cycle(self):
        """
        Given a graph with a 2-node cycle and one unrelated leaf
        When tarjan_scc is called
        Then one component contains both cyclic nodes and another is the leaf alone
        """
        graph = {"x": {"y"}, "y": {"x"}, "z": set()}
        components = af.tarjan_scc(graph)
        sizes = sorted(len(c) for c in components)
        self.assertEqual(sizes, [1, 2])
        cyclic = next(c for c in components if len(c) == 2)
        self.assertEqual(set(cyclic), {"x", "y"})

    def test_tarjan_scc_dag_has_only_singletons(self):
        """
        Given a pure DAG (no cycles)
        When tarjan_scc is called
        Then every component has size 1
        """
        graph = {"a": {"b"}, "b": {"c"}, "c": set()}
        components = af.tarjan_scc(graph)
        self.assertTrue(all(len(c) == 1 for c in components))

    def test_find_import_cycles_reports_only_multi_node_components(self):
        """
        Given a graph with one 2-node cycle and one acyclic chain
        When find_import_cycles is called
        Then only the cycle is returned
        """
        graph = {"x": {"y"}, "y": {"x"}, "a": {"b"}, "b": set()}
        cycles = af.find_import_cycles(graph)
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"x", "y"})

    def test_find_import_cycles_drops_an_out_of_scope_cycle_entirely(self):
        """
        Given a graph with a cycle entirely inside an out-of-scope package
            and a genuine in-scope cycle
        When find_import_cycles is called with out_of_scope_packages naming
            the first cycle's package
        Then only the in-scope cycle is reported
        """
        graph = {
            "parser.a": {"parser.b"},
            "parser.b": {"parser.a"},
            "hook": {"tools.decision"},
            "tools.decision": {"hook"},
        }
        cycles = af.find_import_cycles(graph, out_of_scope_packages=("parser",))
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]), {"hook", "tools.decision"})

    def test_find_import_cycles_default_out_of_scope_packages_is_unfiltered(self):
        """
        Given the same out-of-scope-package cycle as above
        When find_import_cycles is called WITHOUT out_of_scope_packages
        Then it is still reported -- the default reproduces the original,
            unfiltered behaviour exactly, so every pre-existing caller is
            unaffected
        """
        graph = {"parser.a": {"parser.b"}, "parser.b": {"parser.a"}}
        cycles = af.find_import_cycles(graph)
        self.assertEqual(len(cycles), 1)

    def test_fan_in_counts_distinct_importers(self):
        """
        Given two modules importing a shared third module
        When fan_in is called
        Then the shared module's count equals the number of importers
        """
        graph = {"a": {"c"}, "b": {"c"}, "c": set()}
        counts = af.fan_in(graph)
        self.assertEqual(counts["c"], 2)
        self.assertEqual(counts["a"], 0)

    def test_longest_dependency_chain_linear(self):
        """
        Given a linear chain a -> b -> c
        When longest_dependency_chain is called
        Then it returns all three nodes in dependency order
        """
        graph = {"a": {"b"}, "b": {"c"}, "c": set()}
        chain = af.longest_dependency_chain(graph)
        self.assertEqual(chain, ["a", "b", "c"])

    def test_longest_dependency_chain_collapses_cycles(self):
        """
        Given a chain with a 2-node cycle in the middle (a -> x <-> y -> c)
        When longest_dependency_chain is called
        Then the cycle is rendered as one combined node, not expanded infinitely
        """
        graph = {"a": {"x"}, "x": {"y"}, "y": {"x", "c"}, "c": set()}
        chain = af.longest_dependency_chain(graph)
        self.assertEqual(len(chain), 3)  # a, {x,y}, c
        self.assertIn("x=y", chain)


class TestFindVerdictTypes(unittest.TestCase):
    """Tests for find_verdict_types."""

    def test_finds_verdict_types_by_structure_not_by_name(self):
        """
        Given a class whose NAME says nothing about verdicts but declares a
            decision-like field plus 2 aux fields (structurally a verdict),
            and a class whose NAME looks verdict-ish (matches the OLD
            name-substring rule) but declares no fields at all
        When find_verdict_types is called
        Then only the structurally-verdict-ish class is returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class TotallyUnrelatedName:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n\n"
                "class FileResolution:\n"
                "    pass\n\n"
                "class Decision:\n"
                "    pass\n",
            )
            found = {t["class"] for t in af.find_verdict_types(root)}
            self.assertEqual(found, {"TotallyUnrelatedName"})

    def test_verdict_field_requires_at_least_two_aux_fields(self):
        """
        Given a class with a decision-like field but only ONE aux field
            (below the :data:`_VERDICT_MIN_AUX_FIELDS` threshold)
        When find_verdict_types is called
        Then it is NOT reported -- a bare "decision" field alone (or with a
            single incidental aux field) is not enough to call a class a
            verdict; this is what keeps LedgerDecision/SingleDecision (each
            0 aux fields) and any similarly thin future class excluded
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Thin:\n    decision: str\n    reason: str\n",
            )
            self.assertEqual(af.find_verdict_types(root), [])

    def test_unitverdict_included_and_false_positives_excluded_on_real_tree(self):
        """
        Given the real toolguard/ tree
        When find_verdict_types is called
        Then RuntimeVerdict and UnitVerdict are reported, and
            ProjectRootResolution, LedgerDecision, and SingleDecision are not
        """
        found = {t["class"] for t in af.find_verdict_types()}
        self.assertIn("UnitVerdict", found)
        self.assertIn("RuntimeVerdict", found)
        self.assertNotIn("Decision", found)
        for false_positive in (
            "ProjectRootResolution",
            "LedgerDecision",
            "SingleDecision",
        ):
            self.assertNotIn(false_positive, found)

    def test_excludes_generated_files(self):
        """
        Given a verdict-ish class defined in a file carrying a generated-code banner
        When find_verdict_types is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from x.peg\nclass FileResolution:\n    pass\n",
            )
            self.assertEqual(af.find_verdict_types(root), [])

    def test_excludes_r1_out_of_scope_packages(self):
        """
        Given a verdict-ish class defined under toolguard/parser/ (out of scope)
        When find_verdict_types is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "parser" / "x.py",
                "class SomeResolution:\n    pass\n",
            )
            self.assertEqual(af.find_verdict_types(root), [])


class TestClassifyVerdictAltitudes(unittest.TestCase):
    """Tests for classify_verdict_altitudes -- the altitude split the R1 gate uses to require exactly one RUNTIME verdict type without hand-listing class names."""

    def test_nested_list_field_class_is_unit_not_runtime(self):
        """
        Given a verdict-ish class ("Container") whose sub_matches field is
            typed List[Leaf], and Leaf is ITSELF a verdict-ish class
        When classify_verdict_altitudes is called
        Then Leaf is reported as UNIT (nested inside Container.sub_matches),
            Container is reported as RUNTIME, and neither is reported TOOLING
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Container:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n"
                "    sub_matches: List[Leaf]\n\n"
                "class Leaf:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n",
            )
            alt = af.classify_verdict_altitudes(root)
            self.assertEqual([t["class"] for t in alt["runtime"]], ["Container"])
            self.assertEqual([t["class"] for t in alt["unit"]], ["Leaf"])
            self.assertEqual(alt["tooling"], [])
            self.assertEqual(
                alt["unit"][0]["nested_in"],
                [{"container": "Container", "field": "sub_matches"}],
            )

    def test_class_under_tooling_package_is_tooling_not_runtime(self):
        """
        Given a verdict-ish class defined under a tools/ package (R1_TOOLING_PACKAGES)
        When classify_verdict_altitudes is called
        Then it is reported as TOOLING, with its package recorded, and NOT
            reported as RUNTIME
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "b.py",
                "class ToolingThing:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n",
            )
            alt = af.classify_verdict_altitudes(root)
            self.assertEqual(alt["runtime"], [])
            self.assertEqual(alt["unit"], [])
            self.assertEqual([t["class"] for t in alt["tooling"]], ["ToolingThing"])
            self.assertEqual(alt["tooling"][0]["package"], "tools")

    def test_unrelated_verdict_ish_class_is_runtime(self):
        """
        Given a verdict-ish class that is neither nested inside another
            verdict-ish class nor under a tooling package
        When classify_verdict_altitudes is called
        Then it is reported as RUNTIME
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Standalone:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n",
            )
            alt = af.classify_verdict_altitudes(root)
            self.assertEqual([t["class"] for t in alt["runtime"]], ["Standalone"])

    def test_real_tree_has_exactly_one_runtime_verdict_type(self):
        """
        Given the real toolguard/ tree
        When classify_verdict_altitudes is called
        Then RuntimeVerdict is the only runtime-altitude type, UnitVerdict is
            unit-altitude (nested inside RuntimeVerdict.sub_matches), and the
            TOOLING altitude bucket is empty
        """
        alt = af.classify_verdict_altitudes()
        self.assertEqual([t["class"] for t in alt["runtime"]], ["RuntimeVerdict"])

        unit_by_class = {t["class"]: t for t in alt["unit"]}
        self.assertIn("UnitVerdict", unit_by_class)
        containers = {n["container"] for n in unit_by_class["UnitVerdict"]["nested_in"]}
        self.assertEqual(containers, {"RuntimeVerdict"})

        self.assertEqual(alt["tooling"], [])

    def test_real_tree_reports_levelmatch_as_a_visible_level_altitude(self):
        """
        Given the real toolguard/ tree, where LevelMatch (config_types.py)
            carries only 1 aux field -- below find_verdict_types' own 2-field
            threshold, so it never appears in find_verdict_types' output
        When classify_verdict_altitudes is called
        Then LevelMatch is present, classified LEVEL, and RuntimeVerdict
            remains the only RUNTIME-altitude type
        """
        alt = af.classify_verdict_altitudes()
        level_by_class = {t["class"]: t for t in alt["level"]}
        self.assertIn("LevelMatch", level_by_class)
        self.assertIn("Provenance", level_by_class["LevelMatch"]["reason"])
        self.assertEqual([t["class"] for t in alt["runtime"]], ["RuntimeVerdict"])
        self.assertNotIn("LevelMatch", [t["class"] for t in alt["runtime"]])

    def test_class_with_no_provenance_field_is_level_not_runtime(self):
        """
        Given a synthetic class shaped exactly like LevelMatch --
            (decision, reason, matched_pattern), no provenance field or
            reference anywhere on the class
        When classify_verdict_altitudes is called
        Then it is classified LEVEL, with a reason explaining why, and it is
            NOT reported as RUNTIME, UNIT, or TOOLING
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class SyntheticLevelMatch:\n"
                "    decision: str\n"
                "    reason: str\n"
                "    matched_pattern: str\n",
            )
            alt = af.classify_verdict_altitudes(root)
            self.assertEqual(
                [t["class"] for t in alt["level"]], ["SyntheticLevelMatch"]
            )
            self.assertTrue(alt["level"][0]["reason"])
            self.assertEqual(alt["runtime"], [])
            self.assertEqual(alt["unit"], [])
            self.assertEqual(alt["tooling"], [])

    def test_provenance_bearing_class_is_never_classified_level(self):
        """
        Given a synthetic RUNTIME-shaped class carrying a genuine
            provenance-typed field (decision, matched_rule, provenance)
        When classify_verdict_altitudes is called
        Then it is classified RUNTIME and never appears in the LEVEL bucket
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class SyntheticRuntimeVerdict:\n"
                "    decision: str\n"
                "    matched_rule: str\n"
                "    provenance: object\n",
            )
            alt = af.classify_verdict_altitudes(root)
            self.assertEqual(
                [t["class"] for t in alt["runtime"]], ["SyntheticRuntimeVerdict"]
            )
            self.assertEqual(alt["level"], [])

    def test_level_classification_is_invariant_to_matched_pattern_vs_matched_rule_rename(
        self,
    ):
        """
        Given two otherwise-identical synthetic classes shaped like
            LevelMatch, one spelling its winning-pattern field
            "matched_pattern" (today's real spelling) and the other
            "matched_rule" (the one other real aux-field name, which would
            clear find_verdict_types' own threshold)
        When classify_verdict_altitudes is called on each tree separately
        Then both are classified LEVEL, and neither is classified RUNTIME --
            the detector does not depend on which spelling was chosen
        """
        with tempfile.TemporaryDirectory() as tmp_a:
            root_a = Path(tmp_a)
            _write(
                root_a / "a.py",
                "class SyntheticLevelMatch:\n"
                "    decision: str\n"
                "    reason: str\n"
                "    matched_pattern: str\n",
            )
            alt_a = af.classify_verdict_altitudes(root_a)

        with tempfile.TemporaryDirectory() as tmp_b:
            root_b = Path(tmp_b)
            _write(
                root_b / "a.py",
                "class SyntheticLevelMatch:\n"
                "    decision: str\n"
                "    reason: str\n"
                "    matched_rule: str\n",
            )
            alt_b = af.classify_verdict_altitudes(root_b)

        for label, alt in (
            ("matched_pattern spelling", alt_a),
            ("matched_rule spelling", alt_b),
        ):
            self.assertEqual(
                [t["class"] for t in alt["level"]],
                ["SyntheticLevelMatch"],
                f"expected LEVEL classification with the {label}",
            )
            self.assertEqual(
                alt["runtime"],
                [],
                f"expected NOT RUNTIME with the {label}",
            )


class TestFindBareVerdictTuples(unittest.TestCase):
    """Tests for find_bare_verdict_tuples: catches decision literals returned as bare tuples, invisible to find_verdict_types since that detector only inspects class definitions."""

    def test_flags_a_literal_decision_tuple_return(self):
        """
        Given a function whose return type is a 3-element Tuple[str, str, ...]
            and whose body literally returns ("deny", reason, pattern)
        When find_bare_verdict_tuples is called
        Then it is reported, with basis "literal decision-tuple return"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "from typing import Optional, Tuple\n\n"
                "def check(cmd: str) -> Optional[Tuple[str, str, str]]:\n"
                "    if cmd == 'rm':\n"
                "        return 'deny', 'blocked', 'rm *'\n"
                "    return None\n",
            )
            found = af.find_bare_verdict_tuples(root)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["function"], "check")
            self.assertEqual(found[0]["module"], "a")
            self.assertEqual(found[0]["basis"], "literal decision-tuple return")

    def test_does_not_flag_a_strict_pair(self):
        """
        Given a function returning a strict ("decision", reason) PAIR (arity 2)
        When find_bare_verdict_tuples is called
        Then it is NOT reported -- a strict pair must never be flagged
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "from typing import Tuple\n\n"
                "def check(cmd: str) -> Tuple[str, str]:\n"
                "    return 'deny', 'blocked'\n",
            )
            self.assertEqual(af.find_bare_verdict_tuples(root), [])

    def test_does_not_flag_a_non_verdict_three_tuple(self):
        """
        Given a function whose return annotation is shaped like a verdict
            (Optional[Tuple[str, str, List[str]]], first element str, arity
            3) but whose actual return carries no decision at all -- a
            (timestamp, project_root, levels) parse result, mirroring the
            real toolguard.log_writer._parse_discovery_line
        When find_bare_verdict_tuples is called
        Then it is NOT reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "from typing import Optional, Tuple, List\n\n"
                "def parse_line(line: str) -> Optional[Tuple[str, str, List[str]]]:\n"
                "    parts = line.split('\\t', 2)\n"
                "    if len(parts) != 3:\n"
                "        return None\n"
                "    timestamp, project_root, levels_blob = parts\n"
                "    return timestamp, project_root, [levels_blob]\n",
            )
            self.assertEqual(af.find_bare_verdict_tuples(root), [])

    def test_flags_wrapper_functions_by_two_round_delegation(self):
        """
        Given three functions shaped exactly like compound.py's real chain:
            _detailed() has a literal decision-tuple return (a seed);
            _wrapper() unpacks _detailed()'s 4-tuple and repacks 3 of its
            names into its own return (delegation via unpack-then-repack);
            _outer() directly returns _wrapper(...) (delegation via a
            direct call, only resolvable once _wrapper is itself known --
            i.e. this REQUIRES a second fixpoint round)
        When find_bare_verdict_tuples is called
        Then all three are reported: _detailed with basis "literal
            decision-tuple return", _wrapper and _outer with basis
            "delegates to a known verdict function"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "from typing import Optional, Tuple\n\n"
                "def _detailed(x: str) -> Tuple[str, str, Optional[str], bool]:\n"
                "    if x:\n"
                "        return 'deny', 'no', None, False\n"
                "    return 'allow', 'ok', None, True\n\n"
                "def _wrapper(x: str) -> Tuple[str, str, Optional[str]]:\n"
                "    decision, reason, ctx, _fw = _detailed(x)\n"
                "    return decision, reason, ctx\n\n"
                "def _outer(x: str) -> Tuple[str, str, Optional[str]]:\n"
                "    return _wrapper(x)\n",
            )
            found = {
                h["function"]: h["basis"] for h in af.find_bare_verdict_tuples(root)
            }
            self.assertEqual(
                found,
                {
                    "_detailed": "literal decision-tuple return",
                    "_wrapper": "delegates to a known verdict function",
                    "_outer": "delegates to a known verdict function",
                },
            )

    def test_does_not_flag_an_unrelated_wrapper_with_no_decision_evidence(self):
        """
        Given a verdict-shaped-annotation function that neither constructs a
            decision literal itself NOR delegates to any known verdict
            function (it wraps an ordinary helper instead)
        When find_bare_verdict_tuples is called
        Then it is NOT reported -- the annotation shape alone
            (_is_verdict_shaped_annotation) is never sufficient by itself
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "from typing import Tuple\n\n"
                "def helper(x: str) -> Tuple[str, str, str]:\n"
                "    return x, x.upper(), x.lower()\n\n"
                "def wrapper(x: str) -> Tuple[str, str, str]:\n"
                "    a, b, c = helper(x)\n"
                "    return a, b, c\n",
            )
            self.assertEqual(af.find_bare_verdict_tuples(root), [])

    def test_excludes_generated_files(self):
        """
        Given a bare verdict-tuple-returning function defined in a file
            carrying a generated-code banner
        When find_bare_verdict_tuples is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from x.peg\n"
                "from typing import Tuple\n\n"
                "def check(x: str) -> Tuple[str, str, str]:\n"
                "    return 'deny', 'no', 'p'\n",
            )
            self.assertEqual(af.find_bare_verdict_tuples(root), [])

    def test_excludes_r1_out_of_scope_packages(self):
        """
        Given a bare verdict-tuple-returning function defined under
            toolguard/parser/ (out of scope)
        When find_bare_verdict_tuples is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "parser" / "x.py",
                "from typing import Tuple\n\n"
                "def check(x: str) -> Tuple[str, str, str]:\n"
                "    return 'deny', 'no', 'p'\n",
            )
            self.assertEqual(af.find_bare_verdict_tuples(root), [])

    def test_real_tree_no_longer_flags_any_compound_function_after_r1e(self):
        """
        Given the real toolguard/ tree
        When find_bare_verdict_tuples is called
        Then compound.py contributes zero hits
        """
        found = {
            h["function"]
            for h in af.find_bare_verdict_tuples()
            if h["module"] == "compound"
        }
        self.assertEqual(found, set())

    def test_real_tree_no_longer_flags_the_three_hook_functions_after_r1d(self):
        """
        Given the real toolguard/ tree
        When find_bare_verdict_tuples is called
        Then hook.py contributes zero hits
        """
        found = {
            h["function"]
            for h in af.find_bare_verdict_tuples()
            if h["module"] == "hook"
        }
        self.assertEqual(found, set())

    def test_does_not_flag_parse_discovery_line_on_real_tree(self):
        """
        Given the real toolguard/ tree, which includes
            toolguard.log_writer._parse_discovery_line (annotated
            Optional[Tuple[str, str, List[str]]] -- verdict-shaped, but a
            (timestamp, project_root, levels) parse result, not a decision)
        When find_bare_verdict_tuples is called
        Then it is not reported
        """
        found = {h["function"] for h in af.find_bare_verdict_tuples()}
        self.assertNotIn("_parse_discovery_line", found)

    def test_does_not_flag_strict_pair_functions_on_real_tree(self):
        """
        Given the REAL toolguard/ tree, which includes several genuine
            strict-pair (decision, reason) returns --
            toolguard.permissions.check_permission and
            toolguard.permission_resolution.apply_parse_failure_floor
        When find_bare_verdict_tuples is called
        Then neither is reported
        """
        found = {h["function"] for h in af.find_bare_verdict_tuples()}
        self.assertNotIn("check_permission", found)
        self.assertNotIn("apply_parse_failure_floor", found)


class TestFindIterShims(unittest.TestCase):
    """Tests for find_iter_shims, including its producer/caller heuristic."""

    def test_finds_class_with_iter_and_no_callers(self):
        """
        Given a class defining __iter__ with no tuple-unpacking call sites
        When find_iter_shims is called
        Then it is reported with an empty callers list
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Res:\n    def __iter__(self):\n        yield 1\n",
            )
            shims = af.find_iter_shims(root)
            self.assertEqual(len(shims), 1)
            self.assertEqual(shims[0]["class"], "Res")
            self.assertEqual(shims[0]["callers"], [])

    def test_finds_tuple_unpack_caller_of_a_producer(self):
        """
        Given a producer function returning Res(...) and a caller that tuple-unpacks it
        When find_iter_shims is called
        Then the caller site is reported against the Res shim
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Res:\n"
                "    def __iter__(self):\n"
                "        yield self.x\n"
                "        yield self.y\n\n"
                "def make():\n"
                "    return Res()\n",
            )
            _write(
                root / "b.py",
                "from toolguard.a import make\n\n"
                "def caller():\n"
                "    x, y = make()\n"
                "    return x, y\n",
            )
            shims = af.find_iter_shims(root)
            self.assertEqual(len(shims), 1)
            callers = shims[0]["callers"]
            self.assertEqual(len(callers), 1)
            self.assertEqual(callers[0]["unpack_via"], "make")
            self.assertEqual(callers[0]["module"], "b")

    def test_attribute_access_caller_is_not_reported(self):
        """
        Given a caller that uses attribute access (not tuple-unpacking) on a producer's result
        When find_iter_shims is called
        Then no caller is reported for that site
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Res:\n    def __iter__(self):\n        yield self.x\n\n"
                "def make():\n    return Res()\n",
            )
            _write(
                root / "b.py",
                "from toolguard.a import make\n\n"
                "def caller():\n    result = make()\n    return result.x\n",
            )
            shims = af.find_iter_shims(root)
            self.assertEqual(shims[0]["callers"], [])

    def test_excludes_generated_files(self):
        """
        Given a class defining __iter__ in a file carrying a generated-code banner
            (the real bash_parser.py's TreeNode shape)
        When find_iter_shims is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from grammar.peg\n"
                "class TreeNode:\n    def __iter__(self):\n        yield 1\n",
            )
            self.assertEqual(af.find_iter_shims(root), [])

    def test_excludes_r1_out_of_scope_packages(self):
        """
        Given a hand-written class defining __iter__ under toolguard/parser/
            (out of scope, e.g. LeafCommand/UndecidableSegment)
        When find_iter_shims is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "parser" / "command_extractor.py",
                "class LeafCommand:\n    def __iter__(self):\n        yield 1\n",
            )
            self.assertEqual(af.find_iter_shims(root), [])

    def test_r1_out_of_scope_modules_lists_parser_package(self):
        """
        Given a synthetic tree with modules under toolguard/parser/
        When r1_out_of_scope_modules is called
        Then every parser module is listed, sorted
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "parser" / "a.py", "x = 1\n")
            _write(root / "parser" / "b.py", "x = 1\n")
            _write(root / "hook.py", "x = 1\n")
            self.assertEqual(af.r1_out_of_scope_modules(root), ["parser.a", "parser.b"])

    def test_default_extra_caller_dirs_matches_old_toolguard_only_scan(self):
        """
        Given a producer/caller pair entirely inside toolguard_dir and NO
            extra_caller_dirs argument (the default)
        When find_iter_shims is called
        Then behaviour is unchanged from before extra_caller_dirs existed --
            one caller found, tagged with area "production"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Res:\n    def __iter__(self):\n        yield self.x\n\n"
                "def make():\n    return Res()\n",
            )
            _write(
                root / "b.py",
                "def caller():\n    x, y = make()\n    return x, y\n",
            )
            shims = af.find_iter_shims(root)
            self.assertEqual(len(shims), 1)
            callers = shims[0]["callers"]
            self.assertEqual(len(callers), 1)
            self.assertEqual(callers[0]["area"], "production")
            self.assertEqual(shims[0]["caller_counts_by_area"], {"production": 1})

    def test_extra_caller_dirs_finds_callers_outside_toolguard_dir(self):
        """
        Given a shim + producer inside toolguard_dir, and a tuple-unpacking
            caller living in a SEPARATE directory passed via
            extra_caller_dirs (simulating test/)
        When find_iter_shims is called with that extra_caller_dirs entry
        Then the outside caller is found and tagged with the given area
            label, distinct from the "production" area
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            toolguard_dir = root / "toolguard"
            outside_dir = root / "outside"
            _write(
                toolguard_dir / "a.py",
                "class Res:\n    def __iter__(self):\n        yield self.x\n\n"
                "def make():\n    return Res()\n",
            )
            _write(
                outside_dir / "test_a.py",
                "def caller():\n    x, y = make()\n    return x, y\n",
            )
            shims = af.find_iter_shims(
                toolguard_dir, extra_caller_dirs=[("test", outside_dir)]
            )
            self.assertEqual(len(shims), 1)
            callers = shims[0]["callers"]
            self.assertEqual(len(callers), 1)
            self.assertEqual(callers[0]["area"], "test")
            self.assertEqual(
                shims[0]["caller_counts_by_area"], {"production": 0, "test": 1}
            )

    def test_extra_caller_dirs_missing_directory_is_skipped_not_an_error(self):
        """
        Given an extra_caller_dirs entry pointing at a directory that does
            not exist
        When find_iter_shims is called
        Then it does not raise, and simply contributes 0 callers for that area
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Res:\n    def __iter__(self):\n        yield 1\n",
            )
            shims = af.find_iter_shims(
                root, extra_caller_dirs=[("nowhere", root / "does_not_exist")]
            )
            self.assertEqual(shims[0]["callers"], [])

    def test_no_iter_shims_remain_on_real_tree_after_r1a(self):
        """
        Given the real toolguard/ tree, with test/ passed as an extra
            "test"-area caller directory
        When find_iter_shims is called
        Then neither BashResolution nor FileResolution is reported as an
            __iter__ shim
        """
        shims = {
            s["class"]: s
            for s in af.find_iter_shims(
                extra_caller_dirs=[("test", af.REPO_ROOT / "test")]
            )
        }
        self.assertNotIn("BashResolution", shims)
        self.assertNotIn("FileResolution", shims)


class TestFindParallelArrays(unittest.TestCase):
    """Tests for find_parallel_arrays."""

    def test_finds_base_and_entries_pairs(self):
        """
        Given a dataclass with allow/allow_entries and deny/deny_entries fields,
            plus an unpaired field
        When find_parallel_arrays is called
        Then only the two paired groups are reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    allow: tuple\n"
                "    allow_entries: tuple\n"
                "    deny: tuple\n"
                "    deny_entries: tuple\n"
                "    unrelated: str\n",
            )
            groups = af.find_parallel_arrays(root)
            pairs = {(g["base_field"], g["entries_field"]) for g in groups}
            self.assertEqual(
                pairs, {("allow", "allow_entries"), ("deny", "deny_entries")}
            )

    def test_no_pairs_when_no_matching_class(self):
        """
        Given no class named ToolPatternLayer anywhere in the tree
        When find_parallel_arrays is called
        Then it returns an empty list
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "class Other:\n    x: int\n    x_entries: int\n")
            self.assertEqual(af.find_parallel_arrays(root), [])

    def test_excludes_generated_files(self):
        """
        Given a ToolPatternLayer-named class with a parallel-array shape in a
            file carrying a generated-code banner
        When find_parallel_arrays is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from x.peg\n"
                "class ToolPatternLayer:\n    allow: tuple\n    allow_entries: tuple\n",
            )
            self.assertEqual(af.find_parallel_arrays(root), [])


class TestFindIndexParallelAccess(unittest.TestCase):
    """Tests for find_index_parallel_access: structural, class/field-name-agnostic detection of index-parallel-array lookups. Variants 0-7 are gaming moves that must still be detected; variant 8 is the real fix and must not be."""

    def test_variant_0_control_todays_shape_is_detected(self):
        """
        Given today's real shape: annotated allow/allow_entries fields plus
            an entries[candidates.index(pattern)] lookup
        When find_index_parallel_access is called
        Then the index-lookup site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    allow: tuple\n"
                "    allow_entries: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["kind"], "index_lookup")

    def test_variant_1_entries_renamed_to_rules_is_still_detected(self):
        """
        Given the `_entries` suffix renamed to `_rules` (a `sed`-only gaming
            move against the old name-based check) with the same index lookup
        When find_index_parallel_access is called
        Then the site is still detected -- the rename changes nothing here
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    allow: tuple\n"
                "    allow_rules: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_rules[layer.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_2_dict_of_lists_keyed_by_kind_is_detected(self):
        """
        Given the parallel arrays reshaped into two dicts keyed by kind
        When find_index_parallel_access is called
        Then the index-lookup site is still detected
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    def __init__(self):\n"
                "        self.patterns_by_kind = {}\n"
                "        self.entries_by_kind = {}\n"
                "\n"
                "def lookup(layer, kind, pattern):\n"
                "    return layer.entries_by_kind[kind][\n"
                "        layer.patterns_by_kind[kind].index(pattern)\n"
                "    ]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_3_entries_behind_property_is_detected(self):
        """
        Given `allow` computed as a @property over `allow_entries`, but the
            lookup code still indexes into it manually
        When find_index_parallel_access is called
        Then the index-lookup site is still detected -- the hazard survives
            the property wrapper because the USE SITE is unchanged
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    allow_entries: tuple = ()\n"
                "\n"
                "    @property\n"
                "    def allow(self):\n"
                "        return tuple(e.pattern for e in self.allow_entries)\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_4_renamed_class_shape_identical_is_detected(self):
        """
        Given the class renamed away from ToolPatternLayer, shape unchanged
        When find_index_parallel_access is called
        Then the index-lookup site is still detected -- no class name is
            ever inspected
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternPairing:\n"
                "    allow: tuple\n"
                "    allow_entries: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_5_arrays_moved_to_sibling_class_is_detected(self):
        """
        Given the two arrays split across two sibling classes
        When find_index_parallel_access is called
        Then the index-lookup site is still detected -- the two sequences
            need not live on the same object
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Patterns:\n"
                "    allow: tuple\n"
                "\n"
                "class Entries:\n"
                "    allow: tuple\n"
                "\n"
                "def lookup(patterns, entries, pattern):\n"
                "    return entries.allow[patterns.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_6_prose_only_invariant_unpaired_names_is_detected(self):
        """
        Given two fields with unrelated (non-suffix-paired) names, related
            only by a prose docstring invariant, still consumed by index
        When find_index_parallel_access is called
        Then the index-lookup site is still detected -- no field-name
            spelling convention is ever inspected
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                '    """Invariant: order[i] corresponds to meta[i], index-for-index."""\n'
                "\n"
                "    order: tuple\n"
                "    meta: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.meta[layer.order.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_7_init_assignment_instead_of_annotation_is_detected(self):
        """
        Given the two fields assigned in __init__ rather than declared as
            class-level annotations
        When find_index_parallel_access is called
        Then the index-lookup site is still detected -- only USE sites are
            inspected, never how a field was populated
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    def __init__(self, allow, allow_entries):\n"
                "        self.allow = allow\n"
                "        self.allow_entries = allow_entries\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)

    def test_variant_8_real_fix_entries_only_derived_pattern_is_not_detected(self):
        """
        Given only `allow_entries` stored, `allow` a derived @property, and
            the lookup finding the entry by a direct predicate search rather
            than by shared index
        When find_index_parallel_access is called
        Then nothing is reported -- this is the actual fix, not a gaming move
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class ToolPatternLayer:\n"
                "    allow_entries: tuple = ()\n"
                "\n"
                "    @property\n"
                "    def allow(self):\n"
                "        return tuple(e.pattern for e in self.allow_entries)\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return next(\n"
                "        e for e in layer.allow_entries if e.pattern == pattern\n"
                "    )\n",
            )
            self.assertEqual(af.find_index_parallel_access(root), [])

    def test_method_pair_instance_is_detected_without_class_or_field_hint(self):
        """
        Given a method-pair shape (hard_deny/hard_deny_entries-like): two
            methods, not two fields, each returning a sequence, consumed by
            a separate function via index -- the shape the old
            find_parallel_arrays (which only ever inspects annotated CLASS
            FIELDS) is structurally blind to
        When find_index_parallel_access is called
        Then the index-lookup site is detected
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class Configuration:\n"
                "    def hard_deny(self, tool_name):\n"
                "        return ()\n"
                "\n"
                "    def hard_deny_entries(self, tool_name):\n"
                "        return ()\n"
                "\n"
                "def lookup(config, tool_name, matched):\n"
                "    deny_patterns = config.hard_deny(tool_name)\n"
                "    deny_entries = config.hard_deny_entries(tool_name)\n"
                "    return deny_entries[deny_patterns.index(matched)]\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["kind"], "index_lookup")

    def test_two_arg_zip_over_different_sequences_is_detected(self):
        """
        Given code that zips two different sequences together (the
            takeover-filter shape) rather than indexing one via .index()
        When find_index_parallel_access is called
        Then the zip site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def rebuild(allow, allow_entries, ignored):\n"
                "    kept = [\n"
                "        (p, e)\n"
                "        for p, e in zip(allow, allow_entries)\n"
                "        if p not in ignored\n"
                "    ]\n"
                "    return kept\n",
            )
            hits = af.find_index_parallel_access(root)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["kind"], "zip")

    def test_zip_over_the_same_expression_twice_is_not_detected(self):
        """
        Given zip called with the literal SAME expression on both sides (not
            a parallel-array hazard -- there is only one sequence involved)
        When find_index_parallel_access is called
        Then nothing is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def self_pairs(xs):\n    return list(zip(xs, xs))\n",
            )
            self.assertEqual(af.find_index_parallel_access(root), [])

    def test_index_call_on_the_same_expression_is_not_detected(self):
        """
        Given A[A.index(x)] -- subscripting and indexing the SAME sequence
            (a trivial, harmless self-lookup, not a parallel-array hazard)
        When find_index_parallel_access is called
        Then nothing is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def first_after(xs, pattern):\n    return xs[xs.index(pattern)]\n",
            )
            self.assertEqual(af.find_index_parallel_access(root), [])

    def test_excludes_generated_files(self):
        """
        Given an index-parallel access site in a file carrying a
            generated-code banner
        When find_index_parallel_access is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from x.peg\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            self.assertEqual(af.find_index_parallel_access(root), [])

    def test_rename_invariance_field_suffix_and_class_name_do_not_change_verdict(self):
        """
        Given two fixtures that are IDENTICAL except one uses the
            ToolPatternLayer/_entries spelling and the other a renamed class
            with an unrelated field-name suffix
        When find_index_parallel_access is called on each
        Then both report exactly one, structurally equivalent, hit -- proving
            a rename-only gaming move cannot change the verdict
        """
        with (
            tempfile.TemporaryDirectory() as tmp_a,
            tempfile.TemporaryDirectory() as tmp_b,
        ):
            original_root = Path(tmp_a)
            renamed_root = Path(tmp_b)
            _write(
                original_root / "original.py",
                "class ToolPatternLayer:\n"
                "    allow: tuple\n"
                "    allow_entries: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            _write(
                renamed_root / "renamed.py",
                "class GatedPatternSet:\n"
                "    allow: tuple\n"
                "    allow_backing: tuple\n"
                "\n"
                "def lookup(layer, pattern):\n"
                "    return layer.allow_backing[layer.allow.index(pattern)]\n",
            )
            original_hits = af.find_index_parallel_access(original_root)
            renamed_hits = af.find_index_parallel_access(renamed_root)
            self.assertEqual(len(original_hits), 1)
            self.assertEqual(len(renamed_hits), 1)
            self.assertEqual(original_hits[0]["kind"], renamed_hits[0]["kind"])

    def test_real_tree_finds_no_instances_after_r2(self):
        """
        Given the real toolguard/ tree
        When find_index_parallel_access is called with no directory override
        Then it reports nothing -- there is no longer a second, independently
            populated sequence anywhere on this tree for an index or a zip to
            correlate against
        """
        hits = af.find_index_parallel_access()
        self.assertEqual(hits, [])


class TestFindDriftGuards(unittest.TestCase):
    """Tests for find_drift_guards -- the co-located proxy for R2's clause 3."""

    def test_guard_co_located_with_index_access_is_detected(self):
        """
        Given a len(A) != len(B) guard in the SAME function as an
            index-parallel read of A and B
        When find_drift_guards is called
        Then the guard is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def lookup(layer, pattern):\n"
                "    candidates, entries = layer.allow, layer.allow_entries\n"
                "    if len(entries) != len(candidates):\n"
                "        return None\n"
                "    return entries[candidates.index(pattern)]\n",
            )
            hits = af.find_drift_guards(root)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["function"], "lookup")

    def test_guard_not_co_located_with_any_index_access_is_not_detected(self):
        """
        Given a len(A) != len(B) guard in a function that performs NO
            index-parallel read at all (an unrelated length check, e.g. a
            string-prefix boundary test)
        When find_drift_guards is called
        Then nothing is reported -- an unscoped scan would false-positive on
            this shape (see the function's own docstring for the confirmed
            real-tree false positive this scoping avoids)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def boundary(bn, prefix):\n"
                "    return len(bn) == len(prefix) or not bn[len(prefix):]\n",
            )
            self.assertEqual(af.find_drift_guards(root), [])

    def test_duplicate_check_shape_is_not_a_drift_guard(self):
        """
        Given len(set(x)) != len(x) (a duplicate-value check on ONE sequence)
            co-located with an unrelated index-parallel read in the same
            function
        When find_drift_guards is called
        Then the duplicate-check comparison itself is not reported as a
            drift guard, even though the function also contains a real one
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def lookup(layer, pattern, varying_tokens):\n"
                "    if len(set(varying_tokens)) != len(varying_tokens):\n"
                "        pass\n"
                "    if len(layer.allow_entries) != len(layer.allow):\n"
                "        return None\n"
                "    return layer.allow_entries[layer.allow.index(pattern)]\n",
            )
            hits = af.find_drift_guards(root)
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["left"], "layer.allow_entries")

    def test_real_tree_finds_no_drift_guards_after_r2(self):
        """
        Given the real toolguard/ tree
        When find_drift_guards is called with no directory override
        Then it reports nothing -- in particular not
            toolguard/tools/consolidate.py's duplicate-check shape or
            parser/command_extractor.py's unrelated boundary check, both
            confirmed real-tree false positives an unscoped scan would catch
        """
        self.assertEqual(af.find_drift_guards(), [])


class TestFindReasonParsingSites(unittest.TestCase):
    """Tests for find_reason_parsing_sites, including the sanctioned-site exclusion."""

    def test_finds_split_and_startswith_on_reason_named_values(self):
        """
        Given a function doing reason.split(...) and another doing reason.startswith(...)
        When find_reason_parsing_sites is called
        Then both sites are reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def f(reason):\n    return reason.split(': ', 1)\n\n"
                "def g(reason):\n    return reason.startswith('x')\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 2)
            functions = {s["function"] for s in sites}
            self.assertEqual(functions, {"f", "g"})

    def test_finds_in_membership_check_on_reason_named_variable(self):
        """
        Given a function checking "marker in reason"
        When find_reason_parsing_sites is called
        Then the site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def f(reason):\n    if 'x' in reason:\n        return True\n    return False\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 1)

    def test_ignores_string_methods_on_unrelated_names(self):
        """
        Given a .split() call on a variable unrelated to "reason"
        When find_reason_parsing_sites is called
        Then no site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "def f(command):\n    return command.split(' ')\n")
            self.assertEqual(af.find_reason_parsing_sites(root), [])

    def test_dedupes_two_hits_on_the_same_line(self):
        """
        Given one line containing both a .split() call and an "in reason" check
            (the real hook.py shape: reason.split(...) if ": " in reason else None)
        When find_reason_parsing_sites is called
        Then only one site is reported for that line
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def f(reason):\n"
                "    return reason.split(': ', 1)[1] if ': ' in reason else None\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 1)

    def test_sanctioned_site_is_excluded(self):
        """
        Given a reason.split site inside compound.py's fallback_kind_for_reason
            (the documented sanctioned exclusion)
        When find_reason_parsing_sites is called against a synthetic compound.py
        Then it is NOT reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "compound.py",
                "def fallback_kind_for_reason(decision, reason):\n"
                "    if 'x' in reason:\n        return 'y'\n    return None\n",
            )
            self.assertEqual(af.find_reason_parsing_sites(root), [])

    def test_excludes_generated_files(self):
        """
        Given a reason.split(...) call inside a file carrying a generated-code banner
        When find_reason_parsing_sites is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py",
                "# generated from x.peg\ndef f(reason):\n    return reason.split(':')\n",
            )
            self.assertEqual(af.find_reason_parsing_sites(root), [])

    def test_finds_new_string_methods_on_reason_named_receiver(self):
        """
        Given calls using each newly widened string method (rsplit, partition,
            rpartition, rindex, index, find) on a reason-named receiver
        When find_reason_parsing_sites is called
        Then every one is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "\n".join(
                f"def f{i}(reason):\n    return reason.{method}('x')"
                for i, method in enumerate(
                    ["rsplit", "partition", "rpartition", "rindex", "index", "find"]
                )
            )
            _write(root / "a.py", body + "\n")
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 6)

    def test_finds_compiled_pattern_match_with_reason_as_argument(self):
        """
        Given a module-level compiled pattern's .match(reason) call -- the real,
            previously-missed false negative in hook.py's
            _parse_compound_match_details (reason is the ARGUMENT, not the receiver)
        When find_reason_parsing_sites is called
        Then it is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "import re\n"
                "_PATTERN = re.compile(r'x')\n\n"
                "def f(reason):\n"
                "    m = _PATTERN.match(reason)\n"
                "    return m\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["function"], "f")

    def test_finds_module_level_re_match_with_reason_as_argument(self):
        """
        Given a module-level re.search(pattern, reason) call
        When find_reason_parsing_sites is called
        Then it is reported (reason is an argument, not the receiver "re")
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "import re\n\ndef f(reason):\n    return re.search(r'x', reason)\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 1)

    def test_does_not_flag_match_call_unrelated_to_reason(self):
        """
        Given a .match(...) call whose receiver and arguments are unrelated to "reason"
        When find_reason_parsing_sites is called
        Then no site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "import re\n_P = re.compile(r'x')\n\ndef f(command):\n    return _P.match(command)\n",
            )
            self.assertEqual(af.find_reason_parsing_sites(root), [])

    def test_catches_a_reassigned_reason_local(self):
        """
        Given "reason_body = resolved.reason" followed by reason_body.rsplit(...) --
            the live case that also slipped past the original detector
        When find_reason_parsing_sites is called
        Then the rsplit site is reported (the new local's OWN name still contains "reason")
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "def f(resolved):\n"
                "    reason_body = resolved.reason\n"
                "    cmd, rule = reason_body.rsplit(' -> ', 1)\n"
                "    return cmd, rule\n",
            )
            sites = af.find_reason_parsing_sites(root)
            self.assertEqual(len(sites), 1)
            self.assertIn("rsplit", sites[0]["expression"])


class TestFindPrivateImports(unittest.TestCase):
    """Tests for find_private_imports/scan_private_reaches (R6): private-name reaches into config/engine-layer modules, derived from .pyscn.toml's layer map, via from-import, module-attribute access, getattr, and re-export following."""

    def test_flags_private_import_from_guarded_module(self):
        """
        Given tools/x.py importing a private name from toolguard.config
        When find_private_imports is called
        Then the site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py", "from toolguard.config import _private_thing\n"
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["private_name"], "_private_thing")
            self.assertEqual(sites[0]["target_module"], "config")
            self.assertEqual(sites[0]["defining_module"], "config")
            self.assertEqual(sites[0]["route"], "from_import")

    def test_allows_public_import_from_guarded_module(self):
        """
        Given tools/x.py importing a public name from toolguard.config
        When find_private_imports is called
        Then no site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "from toolguard.config import load_configuration\n",
            )
            self.assertEqual(af.find_private_imports(root), [])

    def test_allows_dunder_import(self):
        """
        Given tools/x.py importing a dunder name from toolguard.config
        When find_private_imports is called
        Then it is not treated as private (dunder is excluded)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py", "from toolguard.config import __version__\n"
            )
            self.assertEqual(af.find_private_imports(root), [])

    def test_flags_private_import_from_runtime_module(self):
        """
        Given hook.py (runtime layer) importing a private name from toolguard.config
        When find_private_imports is called
        Then the site is reported -- runtime modules are checked the same as
            tooling modules
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "hook.py", "from toolguard.config import _private_thing\n")
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["importer"], "hook")

    def test_ignores_private_import_from_unguarded_module(self):
        """
        Given tools/x.py importing a private name from a module not in a
            guarded (config/engine) .pyscn.toml layer
        When find_private_imports is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py", "from toolguard.constants import _something\n"
            )
            self.assertEqual(af.find_private_imports(root), [])

    def test_excludes_generated_files(self):
        """
        Given a private import of a guarded module inside a generated tools/ file
        When find_private_imports is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "gen.py",
                "# generated from x.peg\nfrom toolguard.config import _private_thing\n",
            )
            self.assertEqual(af.find_private_imports(root), [])

    def test_excludes_parser_package_from_guarded_set(self):
        """
        Given tools/x.py importing a private name from toolguard.parser
        When find_private_imports is called
        Then it is NOT reported -- toolguard/parser/ is explicitly out of
            scope (the same exclusion R1/R5 apply), even though `parser` is
            listed under the engine layer's packages in .pyscn.toml and
            would otherwise be guarded
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "from toolguard.parser import _internal_thing\n",
            )
            self.assertEqual(af.find_private_imports(root), [])

    def test_flags_private_attribute_access_via_aliased_import(self):
        """
        Given tools/x.py doing `import toolguard.config as cfg` then reading
            `cfg._private_thing` (module-attribute access, not a from-import)
        When find_private_imports is called
        Then the site is reported via the attribute_access route
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "import toolguard.config as cfg\ncfg._private_thing()\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["route"], "attribute_access")
            self.assertEqual(sites[0]["private_name"], "_private_thing")
            self.assertEqual(sites[0]["target_module"], "config")

    def test_flags_private_attribute_access_via_dotted_bare_import(self):
        """
        Given tools/x.py doing `import toolguard.config` (no `as`) then
            reading `toolguard.config._private_thing`
        When find_private_imports is called
        Then the site is reported -- the multi-hop chain resolves because
            config.py genuinely exists on disk in this fixture
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "config.py", "_private_thing = 1\n")
            _write(
                root / "tools" / "x.py",
                "import toolguard.config\nprint(toolguard.config._private_thing)\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["route"], "attribute_access")
            self.assertEqual(sites[0]["target_module"], "config")

    def test_flags_private_attribute_access_via_from_toolguard_import(self):
        """
        Given tools/x.py doing `from toolguard import config` (binding the
            SUBMODULE, not a value -- distinguished by config.py existing on
            disk) then reading `config._private_thing`
        When find_private_imports is called
        Then the site is reported via the attribute_access route
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "config.py", "_private_thing = 1\n")
            _write(
                root / "tools" / "x.py",
                "from toolguard import config\nprint(config._private_thing)\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["route"], "attribute_access")
            self.assertEqual(sites[0]["target_module"], "config")

    def test_flags_getattr_with_literal_private_name(self):
        """
        Given tools/x.py calling getattr(config, "_private_thing") on a
            module-aliased import, with a string-literal attribute name
        When find_private_imports is called
        Then the site is reported via the getattr route
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "import toolguard.config as config\ngetattr(config, '_private_thing')\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["route"], "getattr")
            self.assertEqual(sites[0]["private_name"], "_private_thing")

    def test_flags_private_import_from_permission_resolution(self):
        """
        Given tools/x.py importing a private name from
            toolguard.permission_resolution
        When find_private_imports is called
        Then the site is reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "from toolguard.permission_resolution import _decide_internal\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["target_module"], "permission_resolution")

    def test_follows_reexport_through_unguarded_module_to_guarded_origin(self):
        """
        Given a foundation-layer module (constants) that re-exports a private
            name originally defined in a guarded config-layer module
            (rule_entry), and tools/x.py importing the private name from the
            FOUNDATION module rather than the guarded one directly
        When find_private_imports is called
        Then the reach is still reported, attributed to the TRUE defining
            module -- proves re-export following works generally
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "rule_entry.py", "def _strip_tool_wrapper(x):\n    return x\n"
            )
            _write(
                root / "constants.py",
                "from toolguard.rule_entry import _strip_tool_wrapper as _strip_tool_wrapper\n",
            )
            _write(
                root / "tools" / "x.py",
                "from toolguard.constants import _strip_tool_wrapper\n",
            )
            sites = af.find_private_imports(root)
            self.assertEqual(len(sites), 1)
            self.assertEqual(sites[0]["target_module"], "constants")
            self.assertEqual(sites[0]["defining_module"], "rule_entry")

    def test_repointing_import_at_reexport_origin_does_not_clear_violation(self):
        """
        Given a config-layer module (config) that re-exports a private name
            (_strip_tool_wrapper) defined in another guarded config-layer
            module (rule_entry), and a tooling module importing the name from
            either the re-exporting module or the true origin directly
        When find_private_imports is called against each variant
        Then both variants report the violation, attributed to the true
            defining module (rule_entry)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "rule_entry.py", "def _strip_tool_wrapper(x):\n    return x\n"
            )
            _write(
                root / "config.py",
                "from toolguard.rule_entry import _strip_tool_wrapper as _strip_tool_wrapper\n",
            )
            _write(
                root / "tools" / "takeover_audit.py",
                "from toolguard.config import _strip_tool_wrapper\n",
            )
            via_reexport = af.find_private_imports(root)
            self.assertEqual(len(via_reexport), 1)
            self.assertEqual(via_reexport[0]["defining_module"], "rule_entry")

            _write(
                root / "tools" / "takeover_audit.py",
                "from toolguard.rule_entry import _strip_tool_wrapper\n",
            )
            via_direct = af.find_private_imports(root)
            self.assertEqual(
                len(via_direct),
                1,
                "re-pointing the import at rule_entry must NOT clear the "
                "violation -- doing so is the exact gaming move this "
                "regression test exists to block",
            )
            self.assertEqual(via_direct[0]["target_module"], "rule_entry")
            self.assertEqual(via_direct[0]["defining_module"], "rule_entry")

    def test_reports_dynamic_getattr_as_unresolvable_not_a_violation(self):
        """
        Given tools/x.py calling getattr(config, name) where name is a
            variable, not a string literal
        When scan_private_reaches is called
        Then it is NOT reported as a violation (cannot be verified
            statically) but IS reported in `unresolvable`
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "tools" / "x.py",
                "import toolguard.config as config\n"
                "name = '_private_thing'\ngetattr(config, name)\n",
            )
            report = af.scan_private_reaches(root)
            self.assertEqual(report.sites, [])
            self.assertEqual(len(report.unresolvable), 1)
            self.assertIn("literal", report.unresolvable[0]["reason"])

    def test_reexport_cycle_reported_as_unresolvable(self):
        """
        Given two guarded-layer modules that re-export the same private name
            from each other in a cycle
        When scan_private_reaches is called
        Then the reach is reported as unresolvable, not silently dropped and
            not misattributed to either module
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "config.py", "from toolguard.resolve import _x as _x\n")
            _write(root / "resolve.py", "from toolguard.config import _x as _x\n")
            _write(root / "tools" / "y.py", "from toolguard.config import _x\n")
            report = af.scan_private_reaches(root)
            self.assertEqual(report.sites, [])
            self.assertEqual(len(report.unresolvable), 1)
            self.assertIn("cycle", report.unresolvable[0]["reason"])


class TestR6GuardedAndCheckedModules(unittest.TestCase):
    """Tests for _r6_guarded_modules/_r6_checked_modules against the real .pyscn.toml layer map."""

    def test_guarded_modules_includes_post_d1a_engine_module(self):
        """
        Given the real .pyscn.toml architecture config
        When _r6_guarded_modules is called
        Then permission_resolution, resolve, and rule_entry are included
        """
        arch = af.parse_architecture_config()
        guarded = af._r6_guarded_modules(arch)
        self.assertIn("permission_resolution", guarded)
        self.assertIn("resolve", guarded)
        self.assertIn("rule_entry", guarded)

    def test_guarded_modules_excludes_parser(self):
        """
        Given the real .pyscn.toml architecture config, where `parser` is
            listed under the engine layer's packages
        When _r6_guarded_modules is called
        Then parser is excluded, per R1_OUT_OF_SCOPE_PACKAGES
        """
        arch = af.parse_architecture_config()
        guarded = af._r6_guarded_modules(arch)
        self.assertNotIn("parser", guarded)

    def test_checked_modules_includes_runtime_and_tooling(self):
        """
        Given the real .pyscn.toml architecture config
        When _r6_checked_modules is called
        Then it includes both tooling (tools, scripts) and runtime (hook,
            among others) modules
        """
        arch = af.parse_architecture_config()
        checked = af._r6_checked_modules(arch)
        self.assertIn("tools", checked)
        self.assertIn("scripts", checked)
        self.assertIn("hook", checked)

    def test_checked_modules_excludes_config_and_engine(self):
        """
        Given the real .pyscn.toml architecture config
        When _r6_checked_modules is called
        Then config/engine-layer modules are not themselves in the
            reach-from scope
        """
        arch = af.parse_architecture_config()
        checked = af._r6_checked_modules(arch)
        self.assertNotIn("config", checked)
        self.assertNotIn("resolve", checked)


class TestParseEntryPointModules(unittest.TestCase):
    """Tests for parse_entry_point_modules: derives an "entry point" from pyproject.toml's [project.scripts] block."""

    def test_strips_toolguard_prefix_and_function_suffix(self):
        """
        Given a [project.scripts] block naming three toolguard-implemented
            console scripts, one of them nested two packages deep
        When parse_entry_point_modules is called
        Then it returns each target's module path with the leading
            "toolguard." stripped and the ":function" suffix dropped
        """
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                "[project.scripts]\n"
                'toolguard = "toolguard.hook:main"\n'
                'toolguard-migrate = "toolguard.scripts.migrate_permissions:main"\n'
                'toolguard-audit = "toolguard.tools.security_audit:main"\n',
                encoding="utf-8",
            )
            modules = af.parse_entry_point_modules(pyproject)
            self.assertEqual(
                modules,
                frozenset(
                    {"hook", "scripts.migrate_permissions", "tools.security_audit"}
                ),
            )

    def test_skips_a_target_outside_the_toolguard_package(self):
        """
        Given a [project.scripts] target implemented by a module outside the
            toolguard package
        When parse_entry_point_modules is called
        Then that target is silently skipped, not raised on
        """
        with tempfile.TemporaryDirectory() as tmp:
            pyproject = Path(tmp) / "pyproject.toml"
            pyproject.write_text(
                '[project.scripts]\nother-tool = "some_other_package.cli:main"\n',
                encoding="utf-8",
            )
            self.assertEqual(af.parse_entry_point_modules(pyproject), frozenset())

    def test_matches_the_real_pyproject_toml(self):
        """
        Given this repo's real pyproject.toml
        When parse_entry_point_modules is called
        Then it returns exactly the 7 declared console-script modules
        """
        modules = af.parse_entry_point_modules()
        self.assertEqual(
            modules,
            frozenset(
                {
                    "hook",
                    "session_start",
                    "update_check",
                    "tools.security_audit",
                    "tools.maintenance",
                    "tools.installer",
                    "scripts.migrate_permissions",
                }
            ),
        )


class TestFindNonLeafEntryPoints(unittest.TestCase):
    """Tests for find_non_leaf_entry_points (R5)."""

    def test_flags_declared_entry_point_module_imported_by_another(self):
        """
        Given hook.py, declared as a pyproject.toml console-script entry
            point, imported by tools/decision.py
        When find_non_leaf_entry_points is called
        Then hook is reported as a non-leaf entry point with tools.decision
            as its importer
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "hook.py", "x = 1\n")
            _write(root / "tools" / "decision.py", "from toolguard.hook import x\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, frozenset({"hook"}))
            modules = {r["module"] for r in results}
            self.assertIn("hook", modules)
            hit = next(r for r in results if r["module"] == "hook")
            self.assertEqual(hit["reason"], "entry_point")
            self.assertEqual(hit["importers"], ["tools.decision"])

    def test_leaf_entry_point_module_not_flagged(self):
        """
        Given hook.py, declared as an entry point, with no importers
        When find_non_leaf_entry_points is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "hook.py", "x = 1\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, frozenset({"hook"}))
            self.assertEqual(results, [])

    def test_flags_scripts_package_module_imported_by_another_even_when_not_a_declared_entry_point(
        self,
    ):
        """
        Given scripts/helper.py, NOT itself a declared [project.scripts]
            target, imported by another module
        When find_non_leaf_entry_points is called
        Then it is still reported as a non-leaf -- scripts/ package
            membership is a second, independent criterion, not subsumed by
            the declared-entry-point set
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "scripts" / "helper.py", "x = 1\n")
            _write(root / "hook.py", "from toolguard.scripts.helper import x\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, frozenset())
            modules = {r["module"] for r in results}
            self.assertIn("scripts.helper", modules)
            hit = next(r for r in results if r["module"] == "scripts.helper")
            self.assertEqual(hit["reason"], "scripts_package")

    def test_intra_runtime_service_module_is_not_flagged_even_though_imported_by_an_entry_point(
        self,
    ):
        """
        Given hook.py (a declared entry point) importing log_writer.py (a
            plain service module, NOT itself a declared entry point and NOT
            under scripts/)
        When find_non_leaf_entry_points is called
        Then log_writer is NOT reported as a non-leaf -- only a module that
            is itself an entry point (or a scripts/ package member) is
            judged
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "log_writer.py", "x = 1\n")
            _write(root / "hook.py", "from toolguard.log_writer import x\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, frozenset({"hook"}))
            modules = {r["module"] for r in results}
            self.assertNotIn("log_writer", modules)
            self.assertEqual(modules, set())

    def test_relabeling_the_pyscn_toml_layer_map_has_no_effect(self):
        """
        Given every module relabelled into one "foundation" layer, installed by
            patching parse_architecture_config -- the anchor that IS consulted
            at call time (see the class-level note on PYSCN_TOML)
        When find_non_leaf_entry_points is called with the same graph and
            entry_point_modules under the real map and under the gamed one
        Then its result is unchanged, WHILE check_layers -- which does read the
            map -- maps the same two modules differently under the two, so the
            invariance is evidence about the predicate rather than evidence
            that the relabelling never happened
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "hook.py", "x = 1\n")
            _write(root / "tools" / "decision.py", "from toolguard.hook import x\n")
            graph = af.build_import_graph(root)
            self.assertNotIn(
                "arch",
                inspect.signature(af.find_non_leaf_entry_points).parameters,
            )
            before = af.find_non_leaf_entry_points(graph, frozenset({"hook"}))
            real_arch = af.parse_architecture_config()
            gamed_arch = af.ArchitectureConfig(
                layers=(af.LayerDef("foundation", ("hook", "tools")),),
                rules=(af.LayerRule("foundation", ("foundation",)),),
            )
            with mock.patch.object(
                af, "parse_architecture_config", return_value=gamed_arch
            ):
                after = af.find_non_leaf_entry_points(graph, frozenset({"hook"}))
                gamed_layers = af.check_layers(root)
            self.assertEqual(before, after)
            self.assertNotEqual(
                af.check_layers(root, real_arch).module_layer,
                gamed_layers.module_layer,
                "the gamed layer map reached nothing -- the invariance above is vacuous",
            )


class TestFindEnrichmentFootprint(unittest.TestCase):
    """Tests for find_enrichment_footprint: separates NAME-token references (real code coupling) from STRING/COMMENT-token mentions (prose only)."""

    def test_finds_files_with_a_real_identifier_reference_as_coupled(self):
        """
        Given a file that USES additional_context as a real Python identifier
            (an assignment target -- a NAME token)
        When find_enrichment_footprint is called
        Then that file is reported in the coupled bucket, not the prose bucket
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "additional_context = None\n")
            _write(root / "c.py", "x = 1\n")
            footprint = af.find_enrichment_footprint(root)
            self.assertEqual(set(footprint.coupled), {"a"})
            self.assertEqual(set(footprint.prose_only), set())

    def test_finds_files_with_only_a_string_mention_as_prose_only(self):
        """
        Given a file that mentions additionalContext ONLY inside a string
            literal (a dict key, e.g. how the hook's JSON output is built --
            there is no Python NAME token spelled 'additionalContext'
            anywhere in real production code, only the string form)
        When find_enrichment_footprint is called
        Then that file is reported in the prose_only bucket, not coupled
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "b.py", 'x = {"additionalContext": None}\n')
            footprint = af.find_enrichment_footprint(root)
            self.assertEqual(set(footprint.coupled), set())
            self.assertEqual(set(footprint.prose_only), {"b"})

    def test_docstring_only_mention_lands_in_prose_bucket_not_coupling(self):
        """
        Given a synthetic file whose ONLY reference to additional_context is
            inside its module docstring (prose narration, no real code
            reference anywhere)
        When find_enrichment_footprint is called
        Then it is reported in the prose_only bucket and NOT in the coupled
            bucket
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "d.py",
                '"""This module used to reference additional_context here."""\nx = 1\n',
            )
            footprint = af.find_enrichment_footprint(root)
            self.assertEqual(set(footprint.coupled), set())
            self.assertEqual(set(footprint.prose_only), {"d"})

    def test_excludes_generated_files(self):
        """
        Given a file referencing additional_context but carrying a generated-code banner
        When find_enrichment_footprint is called
        Then it is not reported in either bucket
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py", "# generated from x.peg\nadditional_context = None\n"
            )
            footprint = af.find_enrichment_footprint(root)
            self.assertEqual(footprint.coupled, [])
            self.assertEqual(footprint.prose_only, [])

    def test_occurrence_count_per_file_and_total(self):
        """
        Given one file with THREE real identifier-level references and
            another with ONE
        When find_enrichment_footprint is called
        Then occurrences_by_file reports the exact per-file count and
            total_occurrences reports their sum
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "additional_context = None\n"
                "def f(additional_context):\n"
                "    return additional_context\n",
            )
            _write(root / "b.py", "additional_context = 1\n")
            footprint = af.find_enrichment_footprint(root)
            self.assertEqual(footprint.occurrences_by_file["a"], 3)
            self.assertEqual(footprint.occurrences_by_file["b"], 1)
            self.assertEqual(footprint.total_occurrences, 4)

    def test_occurrence_count_excludes_prose_only_files(self):
        """
        Given a file that mentions additionalContext only inside a string
        When find_enrichment_footprint is called
        Then it does not appear in occurrences_by_file at all (0 identifier
            references, by definition -- occurrences_by_file only covers the
            coupled bucket)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "b.py", 'x = {"additionalContext": None}\n')
            footprint = af.find_enrichment_footprint(root)
            self.assertNotIn("b", footprint.occurrences_by_file)
            self.assertEqual(footprint.total_occurrences, 0)


class TestGuardPureHelpers(unittest.TestCase):
    """Tests for the guard's pure (non-git) helper functions."""

    def test_is_forbidden_path_logs_dir(self):
        """
        Given a path under logs/
        When _is_forbidden_path is called
        Then it returns True
        """
        self.assertTrue(af._is_forbidden_path("logs/toolguard-2026-08-04.md"))

    def test_is_forbidden_path_env_files(self):
        """
        Given .env and .claude.env paths at any depth
        When _is_forbidden_path is called
        Then both return True
        """
        self.assertTrue(af._is_forbidden_path(".env"))
        self.assertTrue(af._is_forbidden_path("sub/.claude.env"))

    def test_is_forbidden_path_permission_config(self):
        """
        Given the toolguard_hook.toml and settings.json permission-config paths
        When _is_forbidden_path is called
        Then both return True
        """
        self.assertTrue(af._is_forbidden_path(".claude/toolguard_hook.toml"))
        self.assertTrue(af._is_forbidden_path(".claude/settings.json"))

    def test_is_forbidden_path_ordinary_file_is_allowed(self):
        """
        Given an ordinary production file path
        When _is_forbidden_path is called
        Then it returns False
        """
        self.assertFalse(af._is_forbidden_path("toolguard/hook.py"))

    def test_count_test_methods(self):
        """
        Given source with two test_ methods and one helper method
        When _count_test_methods is called
        Then it counts only the test_-prefixed ones
        """
        source = (
            "class T:\n"
            "    def test_a(self):\n        pass\n"
            "    def test_b(self):\n        pass\n"
            "    def helper(self):\n        pass\n"
        )
        self.assertEqual(af._count_test_methods(source), 2)

    def test_project_dependencies_reads_project_table(self):
        """
        Given pyproject.toml text with [project].dependencies
        When _project_dependencies is called
        Then the declared list is returned
        """
        text = '[project]\nname = "x"\ndependencies = ["foo", "bar"]\n'
        self.assertEqual(af._project_dependencies(text), ["foo", "bar"])

    def test_project_dependencies_defaults_to_empty(self):
        """
        Given pyproject.toml text with no dependencies key
        When _project_dependencies is called
        Then it returns an empty list
        """
        self.assertEqual(af._project_dependencies('[project]\nname = "x"\n'), [])

    def test_guard_report_ok_property(self):
        """
        Given a GuardReport with and without failures
        When .ok is read
        Then it reflects whether failures is empty
        """
        self.assertTrue(af.GuardReport().ok)
        self.assertFalse(af.GuardReport(failures=["x"]).ok)


class TestGuardIntegration(unittest.TestCase):
    """Integration tests for run_guard against a real, tiny synthetic git repo."""

    def _make_repo(self, tmp: Path) -> str:
        """Build a minimal repo with one test file and a bare pyproject.toml; return the base SHA."""
        _init_git_repo(tmp)
        _write(
            tmp / "test" / "unit" / "test_x.py",
            "def test_one():\n    pass\n\ndef test_two():\n    pass\n",
        )
        _write(tmp / "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n')
        return _commit_all(tmp, "TOO-1 initial")

    def test_guard_passes_on_clean_tree(self):
        """
        Given a repo with no changes since the base ref
        When run_guard is called
        Then the report is ok
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._make_repo(root)
            report = af.run_guard(
                since=base, run_lint=False, repo_root=root, run_canaries=False
            )
            self.assertTrue(report.ok, report.failures)

    def test_guard_fails_on_guarded_path_touch(self):
        """
        Given an untracked file added under logs/ since the base ref
        When run_guard is called
        Then the report fails, naming the guarded path
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._make_repo(root)
            _write(root / "logs" / "toolguard-today.md", "# log\n")
            report = af.run_guard(
                since=base, run_lint=False, repo_root=root, run_canaries=False
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("logs" in f for f in report.failures))

    def test_guard_fails_when_test_count_decreases(self):
        """
        Given a test file rewritten to have fewer test_ methods since the base ref
        When run_guard is called
        Then the report fails on a test-count-decreased failure
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._make_repo(root)
            _write(root / "test" / "unit" / "test_x.py", "def test_one():\n    pass\n")
            report = af.run_guard(
                since=base, run_lint=False, repo_root=root, run_canaries=False
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("test count decreased" in f for f in report.failures))

    def test_guard_fails_when_test_file_deleted(self):
        """
        Given the test file present at the base ref has been deleted
        When run_guard is called
        Then the report fails naming the deleted file
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._make_repo(root)
            (root / "test" / "unit" / "test_x.py").unlink()
            report = af.run_guard(
                since=base, run_lint=False, repo_root=root, run_canaries=False
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("test file deleted" in f for f in report.failures))

    def test_guard_fails_on_new_dependency(self):
        """
        Given pyproject.toml's [project].dependencies gained a new entry since base
        When run_guard is called
        Then the report fails naming the new dependency
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = self._make_repo(root)
            _write(
                root / "pyproject.toml",
                '[project]\nname = "x"\ndependencies = ["requests"]\n',
            )
            report = af.run_guard(
                since=base, run_lint=False, repo_root=root, run_canaries=False
            )
            self.assertFalse(report.ok)
            self.assertTrue(any("requests" in f for f in report.failures))

    def test_render_guard_text_pass_and_fail(self):
        """
        Given an ok and a failing GuardReport
        When render_guard_text is called
        Then PASS/FAIL are reflected in the text
        """
        self.assertIn("PASS", af.render_guard_text(af.GuardReport()))
        self.assertIn("FAIL", af.render_guard_text(af.GuardReport(failures=["x"])))

    def test_render_guard_text_includes_canary_summary_and_warnings(self):
        """
        Given a GuardReport with canary_results and a warning
        When render_guard_text is called
        Then the canary count and the warning both appear in the text
        """
        report = af.GuardReport(
            warnings=["canary check SKIPPED: no binary found"],
            canary_results=[
                {
                    "tool": "Bash",
                    "target": "x",
                    "expected": "deny",
                    "actual": "deny",
                    "error": None,
                }
            ],
        )
        text = af.render_guard_text(report)
        self.assertIn("canaries: 1 evaluated", text)
        self.assertIn("WARNINGS", text)
        self.assertIn("SKIPPED", text)


class TestGuardCanaries(unittest.TestCase):
    """Tests for the guard's canary check, using a stubbed hook binary so results don't depend on this machine's real permission config."""

    def test_all_canaries_pass_against_a_matching_stub(self):
        """
        Given two synthetic canary cases and a stub binary that echoes back
            exactly the expected verdict for each
        When run_guard_canaries is called
        Then it reports not-skipped, zero mismatches, and one result per case
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_hook_binary(
                root / "stub_toolguard",
                'event["tool_name"] == "Bash" and "deny" or "allow"',
            )
            fake_cases = (
                af.CanaryCase("Bash", "git clean -fdx", "deny"),
                af.CanaryCase("Write", "{repo}/toolguard/compound.py", "allow"),
            )
            with mock.patch.object(af, "GUARD_CANARIES", fake_cases):
                outcome = af.run_guard_canaries(repo_root=root, binary=str(stub))
            self.assertFalse(outcome["skipped"])
            self.assertEqual(outcome["mismatches"], [])
            self.assertEqual(len(outcome["results"]), 2)

    def test_mismatch_is_reported_with_target_expected_and_actual(self):
        """
        Given one canary case expecting "deny" and a stub that always returns "allow"
        When run_guard_canaries is called
        Then one mismatch is reported naming the target, expected, and actual verdict
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_hook_binary(root / "stub_toolguard", '"allow"')
            fake_cases = (af.CanaryCase("Bash", "git clean -fdx", "deny"),)
            with mock.patch.object(af, "GUARD_CANARIES", fake_cases):
                outcome = af.run_guard_canaries(repo_root=root, binary=str(stub))
            self.assertEqual(len(outcome["mismatches"]), 1)
            msg = outcome["mismatches"][0]
            self.assertIn("git clean -fdx", msg)
            self.assertIn("'deny'", msg)
            self.assertIn("'allow'", msg)

    def test_unparseable_output_is_reported_as_a_canary_error(self):
        """
        Given a stub binary that prints garbage instead of JSON
        When run_guard_canaries is called
        Then the case is reported as a "canary error", not a silent pass
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub_path = root / "stub_toolguard"
            stub_path.write_text(
                f"#!{sys.executable}\nprint('not json')\n", encoding="utf-8"
            )
            stub_path.chmod(stub_path.stat().st_mode | stat.S_IEXEC)
            fake_cases = (af.CanaryCase("Bash", "git clean -fdx", "deny"),)
            with mock.patch.object(af, "GUARD_CANARIES", fake_cases):
                outcome = af.run_guard_canaries(repo_root=root, binary=str(stub_path))
            self.assertEqual(len(outcome["mismatches"]), 1)
            self.assertIn("canary error", outcome["mismatches"][0])
            self.assertIsNone(outcome["results"][0]["actual"])
            self.assertIsNotNone(outcome["results"][0]["error"])

    def test_skipped_when_no_binary_resolves(self):
        """
        Given resolve_toolguard_binary() finds nothing (patched)
        When run_guard_canaries is called with binary=None
        Then it reports skipped=True with a clear reason and zero mismatches --
            a missing binary must never read as a canary FAILURE
        """
        with mock.patch.object(af, "resolve_toolguard_binary", return_value=None):
            outcome = af.run_guard_canaries(repo_root=Path("."), binary=None)
        self.assertTrue(outcome["skipped"])
        self.assertIsNotNone(outcome["skip_reason"])
        self.assertEqual(outcome["mismatches"], [])

    def test_resolve_toolguard_binary_prefers_local_bin(self):
        """
        Given a toolguard executable at ~/.local/bin/toolguard (simulated via a
            patched home directory)
        When resolve_toolguard_binary is called
        Then it returns that path without consulting PATH
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            local_bin = home / ".local" / "bin" / "toolguard"
            local_bin.parent.mkdir(parents=True)
            local_bin.write_text("stub", encoding="utf-8")
            with (
                mock.patch.object(af.Path, "home", return_value=home),
                mock.patch.object(
                    af.shutil, "which", return_value="/should/not/be/used"
                ),
            ):
                self.assertEqual(af.resolve_toolguard_binary(), str(local_bin))

    def test_resolve_toolguard_binary_falls_back_to_path(self):
        """
        Given no ~/.local/bin/toolguard but "toolguard" resolves on PATH
        When resolve_toolguard_binary is called
        Then the PATH-resolved location is returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with (
                mock.patch.object(af.Path, "home", return_value=home),
                mock.patch.object(
                    af.shutil, "which", return_value="/usr/local/bin/toolguard"
                ),
            ):
                self.assertEqual(
                    af.resolve_toolguard_binary(), "/usr/local/bin/toolguard"
                )

    def test_resolve_toolguard_binary_returns_none_when_unresolvable(self):
        """
        Given neither ~/.local/bin/toolguard nor a PATH match exists
        When resolve_toolguard_binary is called
        Then None is returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            with (
                mock.patch.object(af.Path, "home", return_value=home),
                mock.patch.object(af.shutil, "which", return_value=None),
            ):
                self.assertIsNone(af.resolve_toolguard_binary())

    def test_guard_canaries_only_skips_diff_checks(self):
        """
        Given a synthetic repo with an untracked file under logs/ (which the
            normal diff-based checks would flag) and canaries disabled
        When run_guard is called with only_canaries=True
        Then the report is ok -- the diff-based checks never ran
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git_repo(root)
            _write(root / "test" / "unit" / "test_x.py", "def test_one():\n    pass\n")
            _write(
                root / "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n'
            )
            _commit_all(root, "TOO-1 initial")
            _write(root / "logs" / "probe.md", "# would normally fail the guard\n")
            report = af.run_guard(
                since="HEAD", repo_root=root, only_canaries=True, run_canaries=False
            )
            self.assertTrue(report.ok)
            self.assertEqual(report.failures, [])

    def test_guard_canaries_only_reports_canary_mismatches(self):
        """
        Given only_canaries=True and a stub binary that fails one canary case
        When run_guard is called
        Then the report fails on exactly that canary mismatch, and no
            diff-based check ran (there is nothing to compare against)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_hook_binary(root / "stub_toolguard", '"allow"')
            fake_cases = (af.CanaryCase("Bash", "git clean -fdx", "deny"),)
            with mock.patch.object(af, "GUARD_CANARIES", fake_cases):
                report = af.run_guard(
                    repo_root=root, only_canaries=True, canary_binary=str(stub)
                )
            self.assertFalse(report.ok)
            self.assertEqual(len(report.failures), 1)
            self.assertEqual(len(report.canary_results), 1)

    def test_full_guard_mode_includes_canary_check_alongside_diff_checks(self):
        """
        Given a clean synthetic repo AND a stub binary that fails one canary case
        When run_guard is called WITHOUT only_canaries (the normal full mode)
        Then the report fails, carrying the canary mismatch even though every
            diff-based check passed
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git_repo(root)
            _write(root / "test" / "unit" / "test_x.py", "def test_one():\n    pass\n")
            _write(
                root / "pyproject.toml", '[project]\nname = "x"\ndependencies = []\n'
            )
            base = _commit_all(root, "TOO-1 initial")
            stub = _write_stub_hook_binary(root / "stub_toolguard", '"allow"')
            fake_cases = (af.CanaryCase("Bash", "git clean -fdx", "deny"),)
            with mock.patch.object(af, "GUARD_CANARIES", fake_cases):
                report = af.run_guard(
                    since=base,
                    run_lint=False,
                    repo_root=root,
                    canary_binary=str(stub),
                )
            self.assertFalse(report.ok)
            self.assertEqual(len(report.failures), 1)
            self.assertIn("canary mismatch", report.failures[0])


class TestPassHavingCheckedNothing(unittest.TestCase):
    """
    A fitness instrument must not report a clean result when its input set is
    empty. Every test here asserts the CORRECT behaviour and currently fails;
    each names the checker that reports success having examined nothing.
    """

    def test_run_guard_does_not_pass_with_an_empty_canary_set(self):
        """
        Given GUARD_CANARIES emptied -- reachable by a rename, a relocation, a
            filter that narrows to nothing, or a load path that returns empty
        When run_guard is called in canaries-only mode against a stub binary
        Then it must not report ok=True: nothing in the result distinguishes
            "every canary passed" from "there were no canaries"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_hook_binary(root / "stub_toolguard", '"allow"')
            with mock.patch.object(af, "GUARD_CANARIES", ()):
                report = af.run_guard(
                    repo_root=root, only_canaries=True, canary_binary=str(stub)
                )
            self.assertEqual(report.canary_results, [])
            self.assertFalse(
                report.ok,
                "the guard reported PASS having evaluated zero canary cases",
            )

    def test_run_guard_canaries_does_not_report_a_clean_unskipped_empty_run(self):
        """
        Given the same emptied GUARD_CANARIES
        When run_guard_canaries is called
        Then it must not report skipped=False with zero mismatches and zero
            results -- an empty case set is a configuration error, and the one
            state it must never be confused with is a clean pass
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stub = _write_stub_hook_binary(root / "stub_toolguard", '"allow"')
            with mock.patch.object(af, "GUARD_CANARIES", ()):
                outcome = af.run_guard_canaries(repo_root=root, binary=str(stub))
            self.assertEqual(outcome["results"], [])
            self.assertTrue(
                outcome["skipped"] or outcome["mismatches"],
                "an empty canary set read as a clean, un-skipped run",
            )

    def test_check_layers_does_not_pass_over_a_tree_with_no_modules(self):
        """
        Given a source tree containing no Python modules at all -- what a
            mistyped or relocated toolguard_dir produces
        When check_layers is called with the real architecture config
        Then it must not report ok=True having mapped zero modules; the
            --layers half of the tool degrades as quietly here as the canary
            guard does
        """
        with tempfile.TemporaryDirectory() as tmp:
            empty_tree = Path(tmp) / "toolguard"
            empty_tree.mkdir()
            report = af.check_layers(empty_tree, af.parse_architecture_config())
            self.assertEqual(report.module_layer, {})
            self.assertFalse(
                report.ok,
                "check_layers reported PASS having examined zero modules",
            )

    def test_check_layers_reports_a_declared_package_with_no_module_behind_it(self):
        """
        Given a layer declaring a package name that matches no module in the
            tree -- the residue a rename or a deletion leaves in the map
        When check_layers is called
        Then the dead entry is reported and the report is not ok; a map entry
            that protects nothing is indistinguishable from one that does
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "x = 1\n")
            _write(root / "b.py", "x = 1\n")
            arch = af.ArchitectureConfig(
                layers=(
                    af.LayerDef("base", ("a",)),
                    af.LayerDef("top", ("b", "a_package_that_no_longer_exists")),
                ),
                rules=(
                    af.LayerRule("base", ("base",)),
                    af.LayerRule("top", ("top", "base")),
                ),
            )
            report = af.check_layers(root, arch)
            self.assertFalse(
                report.ok,
                "a layer package with no module behind it was never reported",
            )

    def test_compute_predicates_does_not_pass_every_step_over_an_empty_tree(self):
        """
        Given a source tree containing no Python modules
        When compute_predicates is called against it
        Then the predicates that examine that tree must not all report pass --
            R2, R3, R5 and R6 currently do, so four of the five step gates say
            PASS on the strength of having found nothing to look at
        """
        with tempfile.TemporaryDirectory() as tmp:
            empty_tree = Path(tmp) / "toolguard"
            empty_tree.mkdir()
            predicates = af.compute_predicates(toolguard_dir=empty_tree)
            passing = sorted(
                key
                for key, value in predicates.items()
                if isinstance(value, dict) and value.get("pass") is True
            )
            self.assertEqual(
                passing,
                [],
                f"predicates {passing} passed over a tree with zero modules",
            )


class TestMetricsPureHelpers(unittest.TestCase):
    """Tests for the pure helper functions behind --metrics."""

    def test_ticket_token_found(self):
        """
        Given a commit message containing a TOO-nn token
        When _ticket_token is called
        Then the token is returned
        """
        self.assertEqual(
            af._ticket_token("TOO-45: do the thing\n\nmore body"), "TOO-45"
        )

    def test_ticket_token_absent(self):
        """
        Given a commit message with no ticket token
        When _ticket_token is called
        Then None is returned
        """
        self.assertIsNone(af._ticket_token("just a fix, no ticket"))

    def test_percentile_nearest_rank(self):
        """
        Given a small sorted-able list of integers
        When _percentile is called at p90
        Then it returns a value present in the list, at the expected rank
        """
        values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        self.assertEqual(af._percentile(values, 90), 9.0)
        self.assertEqual(af._percentile([], 90), 0.0)


class TestMetricsIntegration(unittest.TestCase):
    """Integration tests for collect_logical_changes/compute_metrics on a tiny git repo."""

    def _make_repo(self, tmp: Path) -> None:
        """Build a 3-commit repo: two TOO-1 commits touching related files, one untagged."""
        _init_git_repo(tmp)
        _write(tmp / "toolguard" / "a.py", "x = 1\n")
        _write(tmp / "toolguard" / "b.py", "y = 1\n")
        _commit_all(tmp, "TOO-1 first part")
        _write(tmp / "toolguard" / "a.py", "x = 2\n")
        _write(tmp / "toolguard" / "b.py", "y = 2\n")
        _commit_all(tmp, "TOO-1 second part, same ticket")
        _write(tmp / "toolguard" / "c.py", "z = 1\n")
        _commit_all(tmp, "untagged tweak")

    def test_collect_logical_changes_groups_by_ticket(self):
        """
        Given two commits sharing a TOO-1 token and one untagged commit
        When collect_logical_changes is called
        Then the two TOO-1 commits collapse into one logical change
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_repo(root)
            changes = af.collect_logical_changes(repo_root=root)
            self.assertEqual(len(changes), 2)
            keyed = {c.key: c for c in changes}
            self.assertIn("TOO-1", keyed)
            self.assertEqual(
                set(keyed["TOO-1"].files), {"toolguard/a.py", "toolguard/b.py"}
            )

    def test_compute_metrics_runs_on_synthetic_repo(self):
        """
        Given the tiny synthetic repo (production files under its own toolguard/)
        When compute_metrics is called with matching repo_root/toolguard_dir
        Then it returns the documented keys with sane values, no crash
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._make_repo(root)
            metrics = af.compute_metrics(
                repo_root=root,
                toolguard_dir=root / "toolguard",
                min_coupling_observations=1,
            )
            self.assertEqual(metrics["logical_changes"], 2)
            self.assertIn("fan_in_caveat", metrics)
            self.assertIsInstance(metrics["coupled_100pct_pairs"], list)

    def test_compute_metrics_excludes_generated_files_from_every_figure(self):
        """
        Given a synthetic repo where a generated file co-changes with a
            hand-written file across every commit (which would otherwise make
            it the strongest possible co-change/fan-in signal)
        When compute_metrics is called
        Then the generated file is named in generated_files_excluded and
            contributes to NO other figure (no co-change pair, no production
            file count crediting it)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _init_git_repo(root)
            _write(root / "toolguard" / "hand.py", "x = 1\n")
            _write(root / "toolguard" / "gen.py", "# generated from x.peg\nx = 1\n")
            _commit_all(root, "TOO-1 first")
            _write(root / "toolguard" / "hand.py", "x = 2\n")
            _write(root / "toolguard" / "gen.py", "# generated from x.peg\nx = 2\n")
            _commit_all(root, "TOO-1 second")
            metrics = af.compute_metrics(
                repo_root=root,
                toolguard_dir=root / "toolguard",
                min_coupling_observations=1,
            )
            self.assertEqual(metrics["generated_files_excluded"], ["toolguard/gen.py"])
            self.assertEqual(metrics["coupled_100pct_pairs"], [])
            mc = metrics["max_co_change_partners"]
            self.assertIsNone(mc)


class TestComputePredicates(unittest.TestCase):
    """Tests for compute_predicates' assembly against the real tree."""

    def test_assembles_all_predicate_keys(self):
        """
        Given the real tree
        When compute_predicates is called
        Then every documented predicate key and the enrichment footprint are present
        """
        predicates = af.compute_predicates()
        for key in (
            "R1",
            "R2",
            "R3",
            "R5",
            "R6",
            "enrichment_footprint",
            "generated_files_excluded",
        ):
            self.assertIn(key, predicates)
        self.assertIn("pass", predicates["R3"])
        self.assertIn("out_of_scope_excluded", predicates["R1"])
        self.assertIn("bare_verdict_tuples", predicates["R1"])
        self.assertIn("out_of_scope_excluded", predicates["R5"])
        self.assertIn("entry_point_modules", predicates["R5"])
        r6 = predicates["R6"]
        for key in (
            "sites",
            "unresolvable",
            "guarded_layers",
            "guarded_modules",
            "checked_layers",
            "checked_modules",
            "out_of_scope_excluded",
            "known_limitations",
        ):
            self.assertIn(key, r6)
        self.assertIn("permission_resolution", r6["guarded_modules"])
        self.assertNotIn("parser", r6["guarded_modules"])
        self.assertIn("hook", r6["checked_modules"])
        self.assertTrue(
            any(m.startswith("parser") for m in r6["out_of_scope_excluded"]["modules"])
        )
        self.assertTrue(r6["known_limitations"])

    def test_r6_out_of_scope_module_list_matches_r1s(self):
        """
        Given the real tree
        When compute_predicates is called
        Then R6's out_of_scope_excluded names the same parser modules R1/R5
            already exclude, via the same r1_out_of_scope_modules helper --
            not a second, drifting scan
        """
        predicates = af.compute_predicates()
        self.assertEqual(
            predicates["R6"]["out_of_scope_excluded"]["modules"],
            predicates["R1"]["out_of_scope_excluded"]["modules"],
        )

    def test_r5_out_of_scope_excludes_the_parser_package(self):
        """
        Given the real tree, which has a genuine import cycle entirely inside
            toolguard/parser/ (parser.command_extractor <-> parser.multiline)
        When compute_predicates is called
        Then R5's out_of_scope_excluded names the parser modules explicitly
            (mirroring R1's own out_of_scope_excluded), and R5's reported
            cycles contain no parser-only component
        """
        predicates = af.compute_predicates()
        r5 = predicates["R5"]
        self.assertTrue(
            any(m.startswith("parser.") for m in r5["out_of_scope_excluded"]["modules"])
        )
        for cycle in r5["cycles"]:
            self.assertFalse(all(m.startswith("parser.") for m in cycle))

    def test_r5_entry_point_modules_match_pyproject_toml(self):
        """
        Given the real tree
        When compute_predicates is called
        Then R5's entry_point_modules matches parse_entry_point_modules'
            output exactly -- compute_predicates' default wiring is correct
        """
        predicates = af.compute_predicates()
        self.assertEqual(
            predicates["R5"]["entry_point_modules"],
            sorted(af.parse_entry_point_modules()),
        )

    def test_relabeling_pyscn_toml_layer_map_does_not_change_r5_verdict(self):
        """
        Given the real tree's predicates under the real layer map
        When every package is relabelled into a single "foundation" layer and
            that map is installed by patching parse_architecture_config -- the
            anchor that IS consulted (patching the PYSCN_TOML constant is not:
            parse_architecture_config binds it as a default argument, so the
            substitution never reaches any caller)
        Then R5's non_leaf_entry_points, cycles and pass verdict are unchanged,
            WHILE R6's guarded_modules -- derived from the layer map -- does
            change, which is what proves the relabelling reached
            compute_predicates at all
        """
        baseline = af.compute_predicates()
        real_arch = af.parse_architecture_config()
        gamed_arch = af.ArchitectureConfig(
            layers=(
                af.LayerDef(
                    "foundation",
                    tuple(
                        sorted(pkg for lyr in real_arch.layers for pkg in lyr.packages)
                    ),
                ),
            ),
            rules=(af.LayerRule("foundation", ("foundation",)),),
        )
        self.assertNotEqual(gamed_arch, real_arch)
        with mock.patch.object(
            af, "parse_architecture_config", return_value=gamed_arch
        ) as parse:
            gamed = af.compute_predicates()
        self.assertGreater(parse.call_count, 0)
        self.assertNotEqual(
            baseline["R6"]["guarded_modules"],
            gamed["R6"]["guarded_modules"],
            "the gamed layer map reached nothing -- the R5 invariance below is vacuous",
        )
        self.assertEqual(baseline["R5"]["pass"], gamed["R5"]["pass"])
        self.assertEqual(
            baseline["R5"]["non_leaf_entry_points"],
            gamed["R5"]["non_leaf_entry_points"],
        )
        self.assertEqual(baseline["R5"]["cycles"], gamed["R5"]["cycles"])

    def test_r5_out_of_scope_packages_matches_r1s(self):
        """
        Given the module-level constants
        When compared
        Then R5_OUT_OF_SCOPE_PACKAGES is the same tuple as
            R1_OUT_OF_SCOPE_PACKAGES, not a predicate-specific list
        """
        self.assertEqual(af.R5_OUT_OF_SCOPE_PACKAGES, af.R1_OUT_OF_SCOPE_PACKAGES)

    def test_r1_shims_list_is_empty_after_r1a(self):
        """
        Given the real tree
        When compute_predicates is called
        Then R1's iter_shims list is empty
        """
        predicates = af.compute_predicates()
        shims = predicates["R1"]["iter_shims"]
        self.assertEqual(shims, [])

    def test_enrichment_footprint_reports_total_occurrences(self):
        """
        Given the real tree
        When compute_predicates is called
        Then enrichment_footprint carries total_occurrences and
            occurrences_by_file alongside the existing coupled/prose-only
            file counts, and the total is at least as large as the coupled
            file count (every coupled file has at least 1 occurrence)
        """
        predicates = af.compute_predicates()
        ef = predicates["enrichment_footprint"]
        self.assertIn("total_occurrences", ef)
        self.assertIn("occurrences_by_file", ef)
        self.assertGreaterEqual(ef["total_occurrences"], ef["coupled_count"])

    def test_r1_gate_passes_on_the_real_tree_after_r1f_closes_the_last_four(self):
        """
        Given the real tree, where the former bare verdict-tuple returns in
            permissions.py and resolve.py now return LevelMatch (a frozen
            dataclass the R1 verdict-type detector does not count -- see
            LevelMatch's own docstring for why)
        When compute_predicates is called
        Then R1's "bare_verdict_tuples" key is empty and R1's "pass" is True
        """
        predicates = af.compute_predicates()
        self.assertEqual(predicates["R1"]["bare_verdict_tuples"], [])
        self.assertTrue(predicates["R1"]["pass"])


class TestShippedCodeDoesNotImportDevTools(unittest.TestCase):
    """Guards a naming hazard: repo-root ``tools/`` (dev-only) and ``toolguard/tools/`` (shipped) share a name but not a shipping status, and no shipped module may import the bare ``tools`` package."""

    def test_no_toolguard_module_imports_repo_root_tools(self):
        """
        Given every real *.py file under toolguard/
        When each is parsed for "import tools" / "from tools import ..." (the bare,
            repo-root package -- NOT "toolguard.tools", which is a normal internal import)
        Then none are found
        """
        offenders = []
        for py_file in af.iter_python_files(af.TOOLGUARD_DIR):
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "tools" or alias.name.startswith("tools."):
                            offenders.append(f"{py_file}:{node.lineno}")
                elif isinstance(node, ast.ImportFrom):
                    if (
                        node.level == 0
                        and node.module
                        and (node.module == "tools" or node.module.startswith("tools."))
                    ):
                        offenders.append(f"{py_file}:{node.lineno}")
        self.assertEqual(offenders, [])


class TestSmokeAgainstRealTree(unittest.TestCase):
    """Smoke tests against the real toolguard tree and this repo's own git history: each mode must run without crashing and produce the documented shape, not specific counts."""

    def test_check_layers_runs_on_real_tree(self):
        """
        Given the real toolguard/ tree and the real .pyscn.toml
        When check_layers is called
        Then it returns a LayerReport without raising; module_layer is
            populated, unmapped is empty (layer-map completeness holds), and
            ok is True (no completeness or direction violations)
        """
        report = af.check_layers()
        self.assertIsInstance(report.module_layer, dict)
        self.assertGreater(len(report.module_layer), 0)
        self.assertEqual(report.unmapped, [])
        self.assertTrue(report.ok, report.violations)

    def test_api_layer_is_seen_and_populated_in_real_tree_layer_map(self):
        """
        Given the real toolguard/ tree and the real .pyscn.toml, which
            declares a dedicated "api" layer directly above "engine"
        When check_layers is called
        Then toolguard/api.py maps to the "api" layer specifically -- not
             unmapped, not multiply-mapped, and not silently absorbed into a
             neighbouring layer
        """
        report = af.check_layers()
        self.assertEqual(report.module_layer.get("api"), "api")
        self.assertNotIn("api", report.unmapped)
        self.assertNotIn("api", report.multiply_mapped)

    def test_api_layer_rule_allows_only_engine_and_below(self):
        """
        Given the real .pyscn.toml's declared architecture rules
        When the "api" layer's allow-list is read
        Then it permits "api", "engine", "config", "observability" and
             "foundation" only -- not "runtime", "tooling", or "support"
        """
        arch = af.parse_architecture_config()
        allowed = set(arch.allow_for("api"))
        self.assertEqual(
            allowed, {"api", "engine", "config", "observability", "foundation"}
        )
        self.assertNotIn("runtime", allowed)
        self.assertNotIn("tooling", allowed)
        self.assertNotIn("support", allowed)

    def test_every_layer_allow_list_is_pinned_against_a_silent_loosening(self):
        """
        Given the real .pyscn.toml, which is simultaneously the specification
            --layers checks against AND the only thing it is checked against
        When every declared layer's allow-list is compared with the expected
            map held here
        Then they match exactly. Measured: an import that violates the map can
            be erased either by fixing the import or by adding the target layer
            to the source layer's allow-list, and check_layers' report is
            identical in both cases. Only the "api" layer was pinned before, so
            loosening any of the other seven was invisible. This pin makes such
            an edit a deliberate, two-file change.
        """
        arch = af.parse_architecture_config()
        actual = {rule.from_layer: rule.allow for rule in arch.rules}
        self.assertEqual(
            actual,
            {
                "foundation": ("foundation",),
                "observability": ("observability", "foundation"),
                "config": ("config", "observability", "foundation"),
                "engine": ("engine", "config", "observability", "foundation"),
                "api": ("api", "engine", "config", "observability", "foundation"),
                "runtime": (
                    "runtime",
                    "api",
                    "engine",
                    "config",
                    "observability",
                    "foundation",
                ),
                "tooling": (
                    "tooling",
                    "runtime",
                    "api",
                    "engine",
                    "config",
                    "observability",
                    "foundation",
                ),
                "support": (
                    "support",
                    "tooling",
                    "runtime",
                    "api",
                    "engine",
                    "config",
                    "observability",
                    "foundation",
                ),
            },
        )

    def test_compute_predicates_runs_on_real_tree(self):
        """
        Given the real toolguard/ tree
        When compute_predicates is called
        Then it returns a dict with every documented predicate key, no crash
        """
        predicates = af.compute_predicates()
        for key in ("R1", "R2", "R3", "R5", "R6", "enrichment_footprint"):
            self.assertIn(key, predicates)

    def test_compute_metrics_runs_on_real_repo(self):
        """
        Given this repo's real git history
        When compute_metrics is called
        Then it returns a dict with every documented metric key, no crash,
            and the real bash_parser.py (generated) is named in
            generated_files_excluded
        """
        metrics = af.compute_metrics()
        for key in (
            "generated_files_excluded",
            "logical_changes",
            "max_co_change_partners",
            "coupled_100pct_pairs",
            "pct_confined_to_one_zone",
            "p90_production_files_per_change",
            "scripts_co_change_hubs",
            "max_module_fan_in",
            "import_cycle_count",
            "longest_dependency_chain",
            "fan_in_caveat",
        ):
            self.assertIn(key, metrics)
        self.assertIn(
            "toolguard/parser/bash_parser.py", metrics["generated_files_excluded"]
        )

    def test_run_guard_runs_on_real_repo_without_lint(self):
        """
        Given this repo's current state
        When run_guard is called with run_lint=False
        Then it returns a GuardReport without raising
        """
        report = af.run_guard(since="HEAD", run_lint=False)
        self.assertIsInstance(report.failures, list)

    def test_guard_canaries_only_runs_on_real_repo(self):
        """
        Given this machine's real installed toolguard binary (if any) and real
            permission config
        When run_guard is called with only_canaries=True and no stub binary
        Then it either skipped with one stated reason and no results, or ran
            and evaluated EVERY declared case -- branching on the skip warning
            rather than on the result list, so "ran and evaluated nothing"
            fails here by design instead of falling into the skip branch
        """
        report = af.run_guard(only_canaries=True)
        skips = [w for w in report.warnings if "SKIPPED" in w]
        if skips:
            self.assertEqual(len(skips), 1)
            self.assertEqual(report.canary_results, [])
        else:
            self.assertGreater(len(report.canary_results), 0)
            self.assertEqual(len(report.canary_results), len(af.GUARD_CANARIES))

    def test_main_layers_mode_smoke(self):
        """
        Given the --layers CLI flag
        When main() is invoked
        Then it returns an int exit code without raising
        """
        with redirect_stdout(io.StringIO()):
            code = af.main(["--layers"])
        self.assertIn(code, (0, 1))

    def test_main_predicates_json_mode_smoke(self):
        """
        Given the --predicates --json CLI flags
        When main() is invoked
        Then it returns 0 and prints valid JSON containing the predicates key
        """
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = af.main(["--predicates", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(buf.getvalue())
        self.assertIn("predicates", payload)

    def test_main_requires_at_least_one_mode(self):
        """
        Given no mode flags at all
        When main() is invoked
        Then it exits via argparse.error (SystemExit)
        """
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            af.main([])

    def test_main_guard_canaries_only_flag_smoke(self):
        """
        Given the --guard-canaries-only --json CLI flags
        When main() is invoked
        Then it returns an int exit code and prints JSON with a guard/canary_results key
        """
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = af.main(["--guard-canaries-only", "--json"])
        self.assertIn(code, (0, 1))
        payload = json.loads(buf.getvalue())
        self.assertIn("canary_results", payload["guard"])


if __name__ == "__main__":
    unittest.main()
