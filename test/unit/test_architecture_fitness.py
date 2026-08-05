"""
Unit tests for ``tools/architecture_fitness.py`` (TOO-45's per-iteration fitness
instrument).

Per the tool's own testing brief: graph and layer logic are tested against small
SYNTHETIC fixture trees (temp directories built in each test), not against the
live ``toolguard/`` tree -- assertions pinned to today's real module set would
break on every refactor step, which is exactly what this tool exists to survive.
A handful of smoke tests at the bottom exercise the real tree/repo and assert
only that each mode runs without crashing and returns a sane shape.
"""

import ast
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

from tools import architecture_fitness as af  # noqa: E402


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
    """
    Write a small, self-contained Python script to *path* that mimics
    ``toolguard --eval``'s I/O contract (read one JSON event on stdin, print a
    ``{"hookSpecificOutput": {"permissionDecision": ...}}`` JSON object to
    stdout) and make it executable. *body* is a Python expression string
    evaluated with ``event`` (the parsed input dict) bound, that must produce
    the verdict string to report.

    Exists so canary-logic tests never depend on the real installed toolguard
    binary or this machine's real permission config -- the whole point of a
    stub.
    """
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


# =============================================================================
# Module-path helpers
# =============================================================================


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
        # tools/decision.py doing "from . import sorters" -> tools.sorters
        self.assertEqual(
            af.resolve_toolguard_import("sorters", 1, "tools.decision"), "tools.sorters"
        )

    def test_resolve_toolguard_import_relative_level_2(self):
        """
        Given a "from .. import x" (level=2) inside a nested module
        When resolve_toolguard_import is called
        Then it climbs one more package level than level=1
        """
        # tools/decision.py doing "from .. import hook" -> hook
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


# =============================================================================
# Generated-file detection (excluded from --predicates and --metrics)
# =============================================================================


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


# =============================================================================
# Import graph extraction
# =============================================================================


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


# =============================================================================
# .pyscn.toml architecture parsing
# =============================================================================

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


# =============================================================================
# --layers: completeness and direction
# =============================================================================


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


# =============================================================================
# Graph algorithms: Tarjan SCC, fan-in, longest chain
# =============================================================================


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


# =============================================================================
# --predicates: component detectors
# =============================================================================


class TestFindVerdictTypes(unittest.TestCase):
    """Tests for find_verdict_types."""

    def test_finds_decision_and_resolution_classes(self):
        """
        Given classes named Decision, Resolution, and an unrelated Foo
        When find_verdict_types is called
        Then only the verdict-ish names are returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "a.py",
                "class FileResolution:\n    pass\n\n"
                "class Decision:\n    pass\n\n"
                "class Foo:\n    pass\n",
            )
            found = {t["class"] for t in af.find_verdict_types(root)}
            self.assertEqual(found, {"FileResolution", "Decision"})

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
        Given a verdict-ish class defined under toolguard/parser/ (out of scope for TOO-45)
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
            (out of scope for TOO-45, e.g. LeafCommand/UndecidableSegment)
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
    """Tests for find_private_imports (R6)."""

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

    def test_ignores_private_import_outside_tools_and_scripts(self):
        """
        Given a private import from a module OUTSIDE tools/ or scripts/
        When find_private_imports is called
        Then it is not reported (the predicate only guards tools/ and scripts/)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "hook.py", "from toolguard.config import _private_thing\n")
            self.assertEqual(af.find_private_imports(root), [])

    def test_ignores_private_import_from_unguarded_module(self):
        """
        Given tools/x.py importing a private name from a module NOT in R6_GUARDED_MODULES
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


class TestFindNonLeafEntryPoints(unittest.TestCase):
    """Tests for find_non_leaf_entry_points (R5)."""

    SYNTHETIC_TOML = """
[architecture]
enabled = true

[[architecture.layers]]
name = "runtime"
packages = ["hook"]

[[architecture.layers]]
name = "tooling"
packages = ["tools", "scripts"]

[[architecture.rules]]
from = "runtime"
allow = ["runtime"]

[[architecture.rules]]
from = "tooling"
allow = ["tooling", "runtime"]
"""

    def test_flags_runtime_module_imported_by_another(self):
        """
        Given hook.py (runtime) imported by tools/decision.py (tooling)
        When find_non_leaf_entry_points is called
        Then hook is reported as a non-leaf with tools.decision as its importer
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            toml_path = root / ".pyscn.toml"
            toml_path.write_text(self.SYNTHETIC_TOML, encoding="utf-8")
            arch = af.parse_architecture_config(toml_path)
            _write(root / "hook.py", "x = 1\n")
            _write(root / "tools" / "decision.py", "from toolguard.hook import x\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, arch)
            modules = {r["module"] for r in results}
            self.assertIn("hook", modules)

    def test_leaf_runtime_module_not_flagged(self):
        """
        Given hook.py (runtime) with no importers
        When find_non_leaf_entry_points is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            toml_path = root / ".pyscn.toml"
            toml_path.write_text(self.SYNTHETIC_TOML, encoding="utf-8")
            arch = af.parse_architecture_config(toml_path)
            _write(root / "hook.py", "x = 1\n")
            graph = af.build_import_graph(root)
            results = af.find_non_leaf_entry_points(graph, arch)
            self.assertEqual(results, [])


class TestFindEnrichmentFootprint(unittest.TestCase):
    """Tests for find_enrichment_footprint."""

    def test_finds_files_referencing_either_spelling(self):
        """
        Given one file using additional_context and one using additionalContext
        When find_enrichment_footprint is called
        Then both files are reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(root / "a.py", "additional_context = None\n")
            _write(root / "b.py", 'x = {"additionalContext": None}\n')
            _write(root / "c.py", "x = 1\n")
            found = set(af.find_enrichment_footprint(root))
            self.assertEqual(found, {"a", "b"})

    def test_excludes_generated_files(self):
        """
        Given a file referencing additional_context but carrying a generated-code banner
        When find_enrichment_footprint is called
        Then it is not reported
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write(
                root / "gen.py", "# generated from x.peg\nadditional_context = None\n"
            )
            self.assertEqual(af.find_enrichment_footprint(root), [])


# =============================================================================
# --guard: pure helpers
# =============================================================================


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


# =============================================================================
# --guard: integration against a tiny synthetic git repo
# =============================================================================


class TestGuardIntegration(unittest.TestCase):
    """
    Integration tests for run_guard against a real (tiny, synthetic) git repo,
    since the guard's job is fundamentally "what changed since a git ref".
    """

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
    """
    Tests for the guard's canary check (are the loop's own permission rules
    still loaded?), using a small STUBBED hook binary throughout -- never the
    real installed toolguard binary or this machine's real permission config,
    so these tests stay correct on any machine and after the TOO-45
    <TEMPORARY> fences are eventually removed.
    """

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


# =============================================================================
# --metrics: pure helpers and a tiny synthetic-repo integration
# =============================================================================


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
        # nearest-rank via round(pct/100 * (n-1)): round(0.9*9) = index 8 -> value 9.
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


# =============================================================================
# --predicates assembly
# =============================================================================


class TestComputePredicates(unittest.TestCase):
    """Tests for compute_predicates' assembly against a small synthetic tree."""

    def test_assembles_all_predicate_keys(self):
        """
        Given a trivial synthetic toolguard tree and a matching architecture config
        When compute_predicates is called (with the real .pyscn.toml, since the
            R5/R6 helpers need SOME layer map)
        Then every documented predicate key and the enrichment footprint are present
        """
        # compute_predicates() takes no toolguard_dir override for the architecture
        # parse (it always reads the real .pyscn.toml), so exercise it against the
        # real tree here rather than trying to fabricate a matching pair -- this is
        # one of the "couple of smoke tests" the brief allows.
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


# =============================================================================
# Smoke tests against the real repo/tree
# =============================================================================


class TestShippedCodeDoesNotImportDevTools(unittest.TestCase):
    """
    Guards the naming hazard the TOO-45 plan calls out explicitly (P2): repo-root
    ``tools/`` (dev-only, not shipped) and ``toolguard/tools/`` (operator tooling,
    shipped) share a name but not a shipping status. No module under the shipped
    ``toolguard/`` package may import the bare ``tools`` package.
    """

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
    """
    A handful of smoke tests against the real toolguard tree and this repo's own
    git history. These assert only that each mode runs without crashing and
    produces the documented shape -- NOT specific counts, which would break on
    every refactor step (the whole reason this tool exists).
    """

    def test_check_layers_runs_on_real_tree(self):
        """
        Given the real toolguard/ tree and the real .pyscn.toml
        When check_layers is called
        Then it returns a LayerReport without raising
        """
        report = af.check_layers()
        self.assertIsInstance(report.module_layer, dict)
        self.assertGreater(len(report.module_layer), 0)

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
        Then it returns a dict with every documented metric key, no crash
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
        # The real bash_parser.py must be named, not silently dropped -- a
        # tool that could exclude generated code without saying so would
        # reproduce exactly the silent-degradation failure mode this feature
        # exists to prevent.
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
            permission config -- the one thing the canary check is FOR
        When run_guard is called with only_canaries=True and no stub binary
        Then it returns a GuardReport without raising, and either evaluated
            every real canary case or skipped cleanly with a stated reason --
            NOT specific verdicts, which change if the TEMPORARY fences do
        """
        report = af.run_guard(only_canaries=True)
        if report.canary_results:
            self.assertEqual(len(report.canary_results), len(af.GUARD_CANARIES))
        else:
            self.assertEqual(len(report.warnings), 1)

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
