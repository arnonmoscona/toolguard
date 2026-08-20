#!/usr/bin/env python
"""
Dev instrument for the TOO-45 architecture-refactoring loop, over this repo's own
source, test tree, layer map and git history. Not shipped. Stdlib only, like
toolguard's own runtime.

Every number printed here is an INSTRUMENT, not a TARGET. A predicate or metric
going the "right" way is evidence to bring to a human or a judge subagent, never a
self-sufficient stopping condition.

**An exclusion the operator cannot see is indistinguishable from a bug.** That is
the standing rule behind the ``*_excluded``, ``sanctioned_exclusions``,
``known_limitations``, ``unseen`` and ``unchecked_predicate_clauses`` entries in
the output: each names something a detector left out, or cannot check at all.
Stated once, here, rather than at every site that follows it.

Six modes
---------
``--layers``
    Validate every module under ``toolguard/`` against the ``[architecture]``
    block of ``.pyscn.toml``, the single source of truth for the layer map. Two
    reports: DIRECTION, every import that violates the from-layer's allow list;
    and COMPLETENESS, every module that maps to no layer or to more than one.

    Completeness is the half pyscn itself does not give you. It stops validating
    an unmapped module without naming it, and its compliance score stays
    plausible while it does -- so the map degrades quietly instead of failing.

``--predicates``
    Emit the COMPONENT diagnostics behind each TOO-45 step predicate (R1, R2,
    R3, R5, R6), plus the enrichment-footprint tracked diagnostic (not a
    predicate). Add ``--json`` for machine consumption; the judges read the
    components, not a bare boolean.

Generated code
    A generated file (banner-detected -- see
    :func:`tools.generated_files.is_generated_file`) is excluded from
    ``--predicates`` and ``--metrics``: a predicate only satisfiable by
    hand-editing generated code is a trap. NOT excluded from ``--layers`` or
    ``--mocks``, whose job is validating the real import graph, which a
    generated file is still part of.

``--metrics``
    History-based metrics from ``git log``, grouped by logical change (the
    ``TOO-nn`` ticket token in the full commit message, not by raw commit --
    grouping by ticket is what removes the commit-splitting gaming vector).

``--mocks``
    Report each ``patch("mod.name")`` in the test tree that a by-value consumer
    makes inert.

``--ambient``
    Report reads of home, the working directory or the environment under
    ``toolguard/`` that bypass ``toolguard.ambient`` with no owner entry, plus
    ``not checked`` counts for the reads this scan cannot see. ``os`` may be
    imported only by the modules in :data:`OS_IMPORT_OWNERS`, and a ``pathlib``
    ambient member only where :data:`PATH_AMBIENT_OWNERS` has an entry for that
    ``(module, member)`` pair. An unowned ``os`` import or
    :data:`PATH_AMBIENT_FATAL_MEMBERS` read fails the check; an unowned
    ``resolve`` is inventoried instead and does not fail the run. The
    classification of ``dir(Path)`` is re-derived on every run, so a Python
    release that adds a member fails the check instead of widening it silently.

``--guard``
    The deterministic half of the loop's safety inspector: fails on an
    out-of-scope file touch, a shrinking test count, a new runtime dependency,
    or a failing lint/format/doc-link check. Also evaluates a fixed CANARY set
    through the LIVE toolguard hook binary -- see the canary section further
    down for why that is a different question from all the rest.
    ``--guard-canaries-only`` runs just the canary check, skipping the
    diff/test-count/dependency/lint checks.

Usage::

    uv run python tools/architecture_fitness.py --layers
    uv run python tools/architecture_fitness.py --predicates --json
    uv run python tools/architecture_fitness.py --metrics
    uv run python tools/architecture_fitness.py --mocks
    uv run python tools/architecture_fitness.py --ambient
    uv run python tools/architecture_fitness.py --guard --since HEAD
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import re
import shutil
import subprocess
import sys
import tokenize
import tomllib
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Sequence, Set, Tuple

from tools.generated_files import is_generated_file

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLGUARD_DIR = REPO_ROOT / "toolguard"
PYSCN_TOML = REPO_ROOT / ".pyscn.toml"


# =============================================================================
# Shared: python file discovery and module-path helpers
# =============================================================================


def iter_python_files(directory: Path) -> Iterable[Path]:
    """
    Yield every ``*.py`` file under *directory*, skipping ``__pycache__``, in
    sorted order -- a loop diffs this tool's output between iterations, so the
    order must not vary.
    """
    yield from sorted(
        p for p in directory.rglob("*.py") if "__pycache__" not in p.parts
    )


def iter_source_files(directory: Path = TOOLGUARD_DIR) -> List[Path]:
    """
    Return every ``*.py`` file under *directory* EXCLUDING generated code.

    The scan the style/debt detectors use. :func:`check_layers` deliberately
    takes the unfiltered one instead: a generated file's imports are real
    architecture even though its internal style is exempt.
    """
    return [p for p in iter_python_files(directory) if not is_generated_file(p)]


def list_generated_files(directory: Path = TOOLGUARD_DIR) -> List[str]:
    """
    Return every generated ``*.py`` file under *directory*, as toolguard-relative
    dotted paths, sorted -- what ``--predicates``/``--metrics`` print to name the
    files they excluded.
    """
    return sorted(
        relative_module_path(p, directory)
        for p in iter_python_files(directory)
        if is_generated_file(p)
    )


def generated_repo_paths(
    directory: Path = TOOLGUARD_DIR, repo_root: Path = REPO_ROOT
) -> Set[str]:
    """
    Return every generated file's path relative to *repo_root*, POSIX-style
    (``"toolguard/parser/bash_parser.py"``) -- the spelling ``--metrics`` gets
    back from ``git diff-tree --name-only``, so history figures can exclude
    generated files by direct comparison rather than counting a file nobody could
    have hand-edited toward "how coupled is this codebase".
    """
    return {
        p.resolve().relative_to(repo_root.resolve()).as_posix()
        for p in iter_python_files(directory)
        if is_generated_file(p)
    }


def relative_module_path(py_file: Path, package_root: Path = TOOLGUARD_DIR) -> str:
    """
    Return *py_file*'s dotted path relative to *package_root*, e.g.
    ``toolguard/tools/sorters.py`` -> ``"tools.sorters"``.

    ``__init__.py`` maps to its containing package (``toolguard/tools/__init__.py``
    -> ``"tools"``); *package_root*'s own ``__init__.py`` maps to ``""`` -- it is
    the container, not a layer member, and callers should treat that specially.
    """
    rel = py_file.resolve().relative_to(package_root.resolve())
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def first_segment(rel_dotted: str) -> str:
    """Return the first dotted segment of *rel_dotted*, or ``""`` for the root."""
    return rel_dotted.split(".", 1)[0] if rel_dotted else ""


def resolve_toolguard_import(
    module_name: Optional[str], level: int, importer_rel: str
) -> Optional[str]:
    """
    Resolve an ``import``/``from`` statement to a toolguard-relative dotted path.

    Args:
        module_name: The ``module`` part of an ``ast.ImportFrom`` (``None`` for a
            bare relative ``from . import x``), or the dotted name of an
            ``ast.Import`` alias.
        level: The ``ast.ImportFrom.level`` (0 for absolute, N for N leading dots).
            ``0`` for a plain ``ast.Import``.
        importer_rel: The toolguard-relative dotted path of the importing module
            (from :func:`relative_module_path`), used to resolve relative imports.

    Returns:
        The imported module's path relative to ``toolguard`` (e.g. ``"tools.sorters"``,
        or ``""`` for the ``toolguard`` package itself), or ``None`` if the import
        does not target anything inside ``toolguard`` at all (stdlib/third-party).
    """
    if level == 0:
        if module_name is None:
            return None
        if module_name == "toolguard":
            return ""
        if module_name.startswith("toolguard."):
            return module_name[len("toolguard.") :]
        return None
    importer_parts = importer_rel.split(".") if importer_rel else []
    package_parts = importer_parts[:-1] if importer_parts else []
    # level=1 means "from the importer's own package"; each extra level strips one more.
    strip = level - 1
    base_parts = (
        package_parts[: len(package_parts) - strip]
        if strip <= len(package_parts)
        else []
    )
    if module_name:
        base_parts = base_parts + module_name.split(".")
    return ".".join(base_parts)


@dataclass(frozen=True)
class ImportEdge:
    """One import found in the AST, resolved to toolguard-relative module paths."""

    importer: str  # toolguard-relative dotted path of the file doing the import
    imported: str  # toolguard-relative dotted path of the imported module
    line: int
    is_local: bool  # True when the Import/ImportFrom node is NOT at module top level


def _is_module_level(node: ast.AST, tree: ast.Module) -> bool:
    """Return True when *node* is a direct child of the module body (not nested)."""
    return node in tree.body


def extract_toolguard_imports(
    py_file: Path, package_root: Path = TOOLGUARD_DIR
) -> List[ImportEdge]:
    """
    Parse *py_file* and return every import that resolves to another module
    under *package_root*, at ANY nesting depth. Function-local imports count:
    they are the shape a circular-import workaround takes, so a module-level-only
    scan would be blind to exactly the cycles worth finding.

    Note that ``from toolguard.pkg import mod`` resolves to ``pkg``, not
    ``pkg.mod`` -- only the ``module`` part of the statement is resolved, so an
    edge to a submodule imported this way is recorded against its package.
    """
    source = py_file.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(py_file))
    importer_rel = relative_module_path(py_file, package_root)
    edges: List[ImportEdge] = []
    for node in ast.walk(tree):
        is_local = not _is_module_level(node, tree)
        if isinstance(node, ast.Import):
            for alias in node.names:
                target = resolve_toolguard_import(alias.name, 0, importer_rel)
                if target is not None and target != importer_rel:
                    edges.append(
                        ImportEdge(importer_rel, target, node.lineno, is_local)
                    )
        elif isinstance(node, ast.ImportFrom):
            target = resolve_toolguard_import(node.module, node.level, importer_rel)
            if target is not None and target != importer_rel:
                edges.append(ImportEdge(importer_rel, target, node.lineno, is_local))
    return edges


# =============================================================================
# .pyscn.toml architecture parsing
# =============================================================================


@dataclass(frozen=True)
class LayerDef:
    """One ``[[architecture.layers]]`` entry."""

    name: str
    packages: Tuple[str, ...]


@dataclass(frozen=True)
class LayerRule:
    """One ``[[architecture.rules]]`` entry: what *from_layer* may import from."""

    from_layer: str
    allow: Tuple[str, ...]


@dataclass(frozen=True)
class ArchitectureConfig:
    """Parsed ``[architecture]`` block of ``.pyscn.toml``."""

    layers: Tuple[LayerDef, ...]
    rules: Tuple[LayerRule, ...]

    def package_to_layer(self) -> Dict[str, str]:
        """Return a ``{first-path-segment: layer name}`` map built from ``layers``."""
        mapping: Dict[str, str] = {}
        for layer in self.layers:
            for package in layer.packages:
                mapping[package] = layer.name
        return mapping

    def allow_for(self, layer_name: str) -> Tuple[str, ...]:
        """Return the set of layers *layer_name* is allowed to import from."""
        for rule in self.rules:
            if rule.from_layer == layer_name:
                return rule.allow
        return ()


def parse_architecture_config(pyscn_toml_path: Path = PYSCN_TOML) -> ArchitectureConfig:
    """Parse the ``[architecture]`` block of *pyscn_toml_path* via ``tomllib``."""
    with pyscn_toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    arch = data.get("architecture", {})
    layers = tuple(
        LayerDef(name=entry["name"], packages=tuple(entry.get("packages", [])))
        for entry in arch.get("layers", [])
    )
    rules = tuple(
        LayerRule(from_layer=entry["from"], allow=tuple(entry.get("allow", [])))
        for entry in arch.get("rules", [])
    )
    return ArchitectureConfig(layers=layers, rules=rules)


# =============================================================================
# --layers
# =============================================================================


@dataclass
class LayerReport:
    """Result of :func:`check_layers`."""

    unmapped: List[str] = field(default_factory=list)
    multiply_mapped: Dict[str, List[str]] = field(default_factory=dict)
    module_layer: Dict[str, str] = field(default_factory=dict)
    violations: List[Dict[str, object]] = field(default_factory=list)
    #: Declared layer packages matching no module in the tree examined -- the
    #: residue a rename or a deletion leaves in the map.
    dead_packages: List[str] = field(default_factory=list)
    #: Modules actually mapped or unmapped; zero means the tree was never
    #: examined, which must not read as a clean pass.
    examined_modules: int = 0

    @property
    def ok(self) -> bool:
        """True when something was examined and there is no completeness, dead-package, or direction problem."""
        return (
            self.examined_modules > 0
            and not self.unmapped
            and not self.multiply_mapped
            and not self.violations
            and not self.dead_packages
        )


def check_layers(
    toolguard_dir: Path = TOOLGUARD_DIR, arch: Optional[ArchitectureConfig] = None
) -> LayerReport:
    """
    Validate every module under *toolguard_dir* against *arch* (or the parsed
    ``.pyscn.toml`` if omitted). See the module docstring's ``--layers`` section.
    """
    if arch is None:
        arch = parse_architecture_config()
    package_map = arch.package_to_layer()
    report = LayerReport()

    py_files = list(iter_python_files(toolguard_dir))
    rel_paths: Dict[Path, str] = {}
    for py_file in py_files:
        rel = relative_module_path(py_file, toolguard_dir)
        if rel == "":
            continue  # the toolguard/__init__.py container itself
        rel_paths[py_file] = rel
        seg = first_segment(rel)
        matches = [layer for pkg, layer in package_map.items() if pkg == seg]
        if not matches:
            report.unmapped.append(rel)
        elif len(matches) > 1:
            report.multiply_mapped[rel] = matches
        else:
            report.module_layer[rel] = matches[0]

    report.examined_modules = len(rel_paths)
    seen_packages = {first_segment(rel) for rel in rel_paths.values()}
    report.dead_packages = sorted(
        pkg for pkg in package_map if pkg not in seen_packages
    )

    for py_file in py_files:
        rel = rel_paths.get(py_file)
        if rel is None or rel not in report.module_layer:
            continue
        source_layer = report.module_layer[rel]
        allowed = set(arch.allow_for(source_layer))
        for edge in extract_toolguard_imports(py_file, toolguard_dir):
            if edge.imported == "":
                continue  # importing the toolguard package itself carries no layer info
            target_layer = report.module_layer.get(edge.imported)
            if target_layer is None:
                continue  # target itself unmapped; already reported separately
            if target_layer not in allowed:
                report.violations.append(
                    {
                        "source_module": rel,
                        "source_layer": source_layer,
                        "target_module": edge.imported,
                        "target_layer": target_layer,
                        "line": edge.line,
                        "local_import": edge.is_local,
                    }
                )
    return report


def render_layers_text(report: LayerReport) -> str:
    """Render *report* as human-readable text."""
    lines = [
        f"=== --layers: completeness ({report.examined_modules} modules examined) ==="
    ]
    if report.examined_modules == 0:
        lines.append("EXAMINED ZERO MODULES -- not a pass.")
    if report.unmapped:
        lines.append(f"UNMAPPED ({len(report.unmapped)}) -- matches zero layers:")
        for mod in report.unmapped:
            lines.append(f"  - {mod}")
    else:
        lines.append("All modules map to exactly one layer.")
    if report.multiply_mapped:
        lines.append(
            f"MULTIPLY-MAPPED ({len(report.multiply_mapped)}) -- matches more than one layer:"
        )
        for mod, layers in report.multiply_mapped.items():
            lines.append(f"  - {mod}: {', '.join(layers)}")
    if report.dead_packages:
        lines.append(
            f"DEAD PACKAGES ({len(report.dead_packages)}) -- declared but match no module:"
        )
        for pkg in report.dead_packages:
            lines.append(f"  - {pkg}")

    lines.append("")
    lines.append("=== --layers: direction ===")
    if report.violations:
        lines.append(f"VIOLATIONS ({len(report.violations)}):")
        for v in report.violations:
            local = " [local import]" if v["local_import"] else ""
            lines.append(
                f"  - {v['source_module']} ({v['source_layer']}) -> "
                f"{v['target_module']} ({v['target_layer']}) at line {v['line']}{local}"
            )
    else:
        lines.append("No cross-layer direction violations.")
    return "\n".join(lines)


# =============================================================================
# --predicates: shared import-graph helpers (R5, R6, metrics fan-in)
# =============================================================================


def build_import_graph(toolguard_dir: Path = TOOLGUARD_DIR) -> Dict[str, Set[str]]:
    """
    Build ``{module: {modules it imports}}`` for every module under *toolguard_dir*.

    Nodes are toolguard-relative dotted paths (:func:`relative_module_path`); the
    root ``toolguard/__init__.py`` (``""``) is not a node. Generated files are not
    scanned, so their own imports contribute no edges.
    """
    graph: Dict[str, Set[str]] = defaultdict(set)
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        if rel == "":
            continue
        graph.setdefault(rel, set())
        for edge in extract_toolguard_imports(py_file, toolguard_dir):
            if edge.imported and edge.imported != rel:
                graph[rel].add(edge.imported)
    return dict(graph)


def tarjan_scc(graph: Dict[str, Set[str]]) -> List[List[str]]:
    """
    Return the strongly connected components of *graph* (Tarjan's algorithm).

    Nodes referenced only as import targets (no outgoing edges of their own)
    are included with an empty adjacency set. A component of size > 1 is an
    import cycle; a component of size 1 is a cycle only if the node imports
    itself (excluded upstream by :func:`build_import_graph`).
    """
    index_counter = [0]
    stack: List[str] = []
    on_stack: Set[str] = set()
    indices: Dict[str, int] = {}
    lowlink: Dict[str, int] = {}
    result: List[List[str]] = []
    all_nodes = set(graph.keys()) | {n for targets in graph.values() for n in targets}

    def strongconnect(node: str) -> None:
        """Visit *node* in Tarjan's DFS, closing a component when a root is found."""
        indices[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack.add(node)
        for target in graph.get(node, ()):
            if target not in indices:
                strongconnect(target)
                lowlink[node] = min(lowlink[node], lowlink[target])
            elif target in on_stack:
                lowlink[node] = min(lowlink[node], indices[target])
        if lowlink[node] == indices[node]:
            component = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                component.append(w)
                if w == node:
                    break
            result.append(component)

    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(all_nodes) * 4 + 1000))
    for node in sorted(all_nodes):
        if node not in indices:
            strongconnect(node)
    return result


def fan_in(graph: Dict[str, Set[str]]) -> Counter:
    """Return ``{module: number of distinct toolguard modules importing it}``."""
    counts: Counter = Counter()
    for _source, targets in graph.items():
        for target in targets:
            counts[target] += 1
    return counts


def longest_dependency_chain(graph: Dict[str, Set[str]]) -> List[str]:
    """
    Return one longest simple path through the import DAG obtained by
    condensing every strongly-connected component of *graph* into one node
    (a cycle has no finite "longest path" of its own, so it must be collapsed
    before this makes sense).
    """
    components = tarjan_scc(graph)
    comp_of: Dict[str, int] = {}
    for i, comp in enumerate(components):
        for node in comp:
            comp_of[node] = i
    condensed: Dict[int, Set[int]] = defaultdict(set)
    for source, targets in graph.items():
        for target in targets:
            if comp_of[source] != comp_of[target]:
                condensed[comp_of[source]].add(comp_of[target])
    all_ids = set(comp_of.values())

    memo: Dict[int, int] = {}

    def longest_from(cid: int) -> int:
        """Return the longest downstream hop-count from condensed node *cid*, memoized."""
        if cid in memo:
            return memo[cid]
        best = 0
        for nxt in condensed.get(cid, ()):
            best = max(best, 1 + longest_from(nxt))
        memo[cid] = best
        return best

    sys.setrecursionlimit(max(sys.getrecursionlimit(), len(all_ids) * 4 + 1000))
    best_len = -1
    best_start: Optional[int] = None
    for cid in all_ids:
        length = longest_from(cid)
        if length > best_len:
            best_len = length
            best_start = cid
    if best_start is None:
        return []
    chain_ids = [best_start]
    current = best_start
    while True:
        nxts = [n for n in condensed.get(current, ()) if memo[n] == memo[current] - 1]
        if not nxts:
            break
        current = nxts[0]
        chain_ids.append(current)
    # Render each condensed node back to its member module names (joined with "=" for a cycle).
    return ["=".join(sorted(components[cid])) for cid in chain_ids]


# =============================================================================
# --predicates: R1 -- one verdict type
# =============================================================================

#: Field names that mark a class as carrying the DECISION ITSELF. Every verdict
#: type on the tree spells it ``decision``; ``verdict`` is accepted too, so the
#: detector does not hinge on a single spelling.
_VERDICT_DECISION_FIELD_NAMES = frozenset({"decision", "verdict"})

#: Field names that mark a class as carrying VERDICT-SUPPORTING data, on top
#: of the decision-like field above. A class needs a decision-like field
#: TOGETHER WITH at least :data:`_VERDICT_MIN_AUX_FIELDS` of these to count.
_VERDICT_AUX_FIELD_NAMES = frozenset(
    {"reason", "provenance", "matched_rule", "additional_context"}
)

#: How many of :data:`_VERDICT_AUX_FIELD_NAMES` a class must declare, in
#: addition to a decision-like field, to count as a verdict type. Calibrated
#: against the real tree, not guessed: ``LedgerDecision`` and ``SingleDecision``
#: each declare a field literally named ``decision`` and ZERO aux fields, and
#: must not count. 1 would separate them too; 2 leaves a field of slack against
#: a future class that happens to name one incidental field ``reason`` while
#: also having a ``decision`` field meaning something else entirely.
_VERDICT_MIN_AUX_FIELDS = 2


def _class_field_names(node: ast.ClassDef) -> Set[str]:
    """
    Return the class-level annotated-assignment field names declared
    DIRECTLY in *node*'s body -- the shape both a ``@dataclass`` and a
    ``typing.NamedTuple`` subclass use (``name: type`` or ``name: type = default``).

    KNOWN LIMIT: inherited fields are not resolved -- this is a single-file AST
    scan with no MRO walk, so a verdict type that declares its fields on a base
    class is invisible here.
    """
    return {
        stmt.target.id
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


#: Packages the TOO-45 ticket puts out of scope ("Out of scope, unchanged: ...
#: toolguard/parser/ including the generated parser" -- the execution plan). The
#: ticket does not touch them, so a finding inside one could not be acted on.
#:
#: Applied by R1, R5 and R6; R2's use-site scans do not apply it and do read
#: ``parser``. R5's cycle check needs it to be passable at all --
#: ``parser.command_extractor <-> parser.multiline`` is a live intra-parser cycle
#: no in-scope change could clear. R6 needs it because ``parser`` is listed under
#: the engine layer in ``.pyscn.toml``, so a layer-derived guarded set would
#: otherwise pull it in.
R1_OUT_OF_SCOPE_PACKAGES = ("parser",)

#: R5's spelling of :data:`R1_OUT_OF_SCOPE_PACKAGES`. Separate name, same tuple,
#: so an R5 call site reads as R5's own decision.
R5_OUT_OF_SCOPE_PACKAGES = R1_OUT_OF_SCOPE_PACKAGES


def r1_out_of_scope_modules(toolguard_dir: Path = TOOLGUARD_DIR) -> List[str]:
    """
    Return every toolguard-relative module (including generated ones) under an
    :data:`R1_OUT_OF_SCOPE_PACKAGES` package, for the ``out_of_scope_excluded``
    report. R5 and R6 exclude the same packages, so all three print this list.
    """
    return sorted(
        relative_module_path(p, toolguard_dir)
        for p in iter_python_files(toolguard_dir)
        if first_segment(relative_module_path(p, toolguard_dir))
        in R1_OUT_OF_SCOPE_PACKAGES
    )


def _scan_decision_classes(
    toolguard_dir: Path, min_aux_fields: int
) -> List[Dict[str, object]]:
    """
    Return every class declaring a :data:`_VERDICT_DECISION_FIELD_NAMES` field
    plus at least *min_aux_fields* of :data:`_VERDICT_AUX_FIELD_NAMES`, as
    ``{"class", "module", "line"}`` dicts.

    One walk shared by two thresholds, so they cannot drift apart -- see each
    caller for why its own threshold was chosen. Skips generated files and
    :data:`R1_OUT_OF_SCOPE_PACKAGES`.
    """
    found = []
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        if first_segment(rel) in R1_OUT_OF_SCOPE_PACKAGES:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            fields = _class_field_names(node)
            has_decision_field = bool(fields & _VERDICT_DECISION_FIELD_NAMES)
            aux_hits = fields & _VERDICT_AUX_FIELD_NAMES
            if has_decision_field and len(aux_hits) >= min_aux_fields:
                found.append({"class": node.name, "module": rel, "line": node.lineno})
    return found


def find_verdict_types(toolguard_dir: Path = TOOLGUARD_DIR) -> List[Dict[str, object]]:
    """
    Return every class that STRUCTURALLY represents a permission verdict: one
    declaring a decision-like field (:data:`_VERDICT_DECISION_FIELD_NAMES`)
    together with at least :data:`_VERDICT_MIN_AUX_FIELDS` of
    :data:`_VERDICT_AUX_FIELD_NAMES`.

    Structural on purpose. Two cheaper rules were tried on this tree and both
    failed, so do not reinstate either:

    - **Matching class NAMES** for "decision"/"resolution"/"verdict" was wrong in
      both directions at once. A runtime census (instrumented ``__init__`` over
      the full corpus and suite) found three of its hits are never constructed on
      a decision path at all, and that it missed the per-sub-command verdict type
      entirely -- 8,314 constructions on the live hook path, invisible because its
      name contained none of the three words.
    - **A hand-maintained allowlist** drifts. This ticket has already caught two
      of them claiming more coverage than they had.

    Altitude is a separate question this function does not answer: it returns
    verdict-shaped classes undifferentiated, and the R1 gate needs exactly one
    RUNTIME one. :func:`classify_verdict_altitudes` splits them, over a wider
    pool than this function's own -- see :data:`_LEVEL_MIN_AUX_FIELDS`.
    """
    return _scan_decision_classes(toolguard_dir, _VERDICT_MIN_AUX_FIELDS)


#: Packages holding the TOOLING verdict altitude -- see
#: :func:`classify_verdict_altitudes`. One declared PACKAGE name, printed with
#: its reason, rather than a list of individual class names.
R1_TOOLING_PACKAGES = ("tools",)

#: Aux-field floor for :func:`classify_verdict_altitudes`' candidate pool,
#: deliberately lower than :data:`_VERDICT_MIN_AUX_FIELDS`. A hierarchy-level
#: match carries only ``reason`` from :data:`_VERDICT_AUX_FIELD_NAMES` (its
#: winning-pattern field is spelled ``matched_pattern``), so the higher
#: threshold never reaches that altitude at all.
#:
#: Lowering it to 1 does not readmit the classes 2 was calibrated against: they
#: declare ZERO aux fields, not one. And the floor does none of the
#: LEVEL-vs-other distinguishing work itself -- that is
#: :func:`_is_provenance_capable`'s job; this only keeps a bare
#: ``decision``-only class out of the pool.
_LEVEL_MIN_AUX_FIELDS = 1


def _class_field_type_sources(node: ast.ClassDef) -> Dict[str, str]:
    """
    Map each field name declared DIRECTLY in *node*'s body to the unparsed
    source text of its type annotation (e.g. ``"Optional[List[UnitVerdict]]"``).

    The annotation TEXT, not the name -- :func:`classify_verdict_altitudes`
    needs it to spot a ``List[OtherVerdictClass]`` embedding and a
    ``Provenance`` reference.
    """
    return {
        stmt.target.id: ast.unparse(stmt.annotation)
        for stmt in node.body
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
    }


def _is_provenance_capable(fields: Set[str], field_types: Dict[str, str]) -> bool:
    """
    Return True when the class CAN carry a matched rule's provenance: either a
    field literally named ``provenance``, or any field whose annotation TEXT
    mentions ``Provenance`` (the ``winning_provenance: Optional["Provenance"]``
    shape).

    This is the LEVEL-altitude test, and it is a structural fact rather than a
    convenient correlation: a hierarchy-level match is built one layer below the
    point where any ``Provenance`` object is in scope, so it cannot carry one.
    That is what makes the altitude genuinely different, not just differently
    named.

    Both signals are needed, and neither looks at the winning-pattern field:

    - Name alone misses a class that carries provenance under another field name.
    - Annotation alone rejects the synthetic fixtures in
      ``TestClassifyVerdictAltitudes``, which spell the field
      ``provenance: object``. They predate this check and must not be rewritten
      to fit it.

    Rejected alternative worth naming, because it looks sufficient and is not:
    "declares no ``tool``/``target`` field" does not separate LEVEL from UNIT --
    the unit-altitude type declares neither either, and would be misclassified.
    """
    return "provenance" in fields or any(
        "Provenance" in type_src for type_src in field_types.values()
    )


#: Human-readable reason attached to every LEVEL-altitude entry
#: :func:`classify_verdict_altitudes` returns, printed verbatim by
#: ``--predicates``.
_LEVEL_ALTITUDE_REASON = (
    "no field named or typed as a Provenance reference -- this is the raw "
    "match at one hierarchy level or hard-deny pool, before any provenance "
    "lookup is attached one layer up (see the class's own docstring). "
    "The winning-pattern field is never inspected by this check, so "
    "classification is unchanged whether it is spelled matched_pattern or "
    "matched_rule."
)


def classify_verdict_altitudes(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> Dict[str, List[Dict[str, object]]]:
    """
    Split the verdict-shaped classes into FOUR ALTITUDES, so the R1 gate can
    require exactly one RUNTIME verdict type without hand-listing class names.

    R1's plan text says "exactly one type represents a permission verdict
    end-to-end". Measured, that is too blunt: four distinct altitudes are
    legitimate here, and flattening them would be worse design, not better --

    1. LEVEL -- the raw match at ONE hierarchy level or hard-deny pool, before
       any provenance lookup is attached one layer up.
    2. UNIT -- one decidable unit inside a compound. Collapsing it into the
       runtime verdict would destroy the only structured record of what a
       compound command did.
    3. RUNTIME -- the altitude the gate requires exactly one of.
    4. TOOLING -- the replay/analysis layer's own DTO. Empty on this tree today;
       the rule still fires if such a class is reintroduced.

    Three tests, applied in this ORDER, with everything left over classed
    RUNTIME. No class name appears in any of them.

    - LEVEL: :func:`_is_provenance_capable` is False. First because it is the
      more fundamental fact -- can this class attach a provenance at all --
      and the two tests below only mean anything once it can.
    - UNIT: embedded via a ``List[...]`` field annotation inside another
      candidate class. Nesting like that makes it an ELEMENT of a compound
      record by construction, not a standalone end-to-end verdict.
    - TOOLING: module under :data:`R1_TOOLING_PACKAGES`.

    The candidate pool is drawn at :data:`_LEVEL_MIN_AUX_FIELDS`, a superset of
    :func:`find_verdict_types`' own -- the LEVEL altitude does not clear that
    function's higher threshold.

    Each returned entry carries why it was classed as it was (``reason`` for
    level, ``nested_in`` for unit, ``package`` for tooling), so ``--predicates``
    can print the reason and not just the name.

    Returns:
        ``{"runtime": [...], "unit": [...], "tooling": [...], "level": [...]}``,
        each a list of the same per-class dicts :func:`_scan_decision_classes`
        returns, with ``level`` entries additionally carrying ``reason``,
        ``unit`` entries additionally carrying ``nested_in`` (a list of
        ``{"container": class_name, "field": field_name}``), and ``tooling``
        entries additionally carrying ``package``.
    """
    by_class: Dict[str, Dict[str, object]] = {
        c["class"]: c
        for c in _scan_decision_classes(toolguard_dir, _LEVEL_MIN_AUX_FIELDS)
    }
    verdict_names = set(by_class)

    provenance_capable: Dict[str, bool] = {}
    nested_in: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        if first_segment(rel) in R1_OUT_OF_SCOPE_PACKAGES:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef) or node.name not in verdict_names:
                continue
            field_types = _class_field_type_sources(node)
            provenance_capable[node.name] = _is_provenance_capable(
                _class_field_names(node), field_types
            )
            for field_name, type_src in field_types.items():
                for other_name in verdict_names:
                    if other_name == node.name:
                        continue
                    if re.search(rf"List\[[^\]]*\b{re.escape(other_name)}\b", type_src):
                        nested_in[other_name].append(
                            {"container": node.name, "field": field_name}
                        )

    runtime: List[Dict[str, object]] = []
    unit: List[Dict[str, object]] = []
    tooling: List[Dict[str, object]] = []
    level: List[Dict[str, object]] = []
    for name, info in by_class.items():
        if not provenance_capable.get(name, False):
            level.append({**info, "reason": _LEVEL_ALTITUDE_REASON})
        elif name in nested_in:
            unit.append({**info, "nested_in": nested_in[name]})
        elif first_segment(str(info["module"])) in R1_TOOLING_PACKAGES:
            tooling.append({**info, "package": first_segment(str(info["module"]))})
        else:
            runtime.append(info)
    return {"runtime": runtime, "unit": unit, "tooling": tooling, "level": level}


def _best_effort_label(py_file: Path, repo_root: Path = REPO_ROOT) -> str:
    """
    Return *py_file*'s path relative to *repo_root*, POSIX-style, falling back to
    the absolute path when it is outside *repo_root* -- a synthetic fixture's temp
    directory must produce a label, not an exception.
    """
    try:
        return py_file.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return str(py_file)


def find_iter_shims(
    toolguard_dir: Path = TOOLGUARD_DIR,
    extra_caller_dirs: Sequence[Tuple[str, Path]] = (),
) -> List[Dict[str, object]]:
    """
    Return every class under *toolguard_dir* defining ``__iter__`` -- the shape a
    tuple-compatibility shim takes -- together with every call site that
    tuple-unpacks a call to a function whose body constructs that class.

    The producer link is a heuristic: exact call-graph tracing needs type
    inference this AST-only tool does not do. It catches the
    ``return Producer(...)`` / ``result = Producer(...)`` shape and no more.

    Scan the callers wherever they live
    -----------------------------------
    R1's predicate requires the shims to be gone "along with their callers", and
    a scan confined to *toolguard_dir* cannot score that: when this was first
    written that way it reported both of the real shims as having zero callers,
    because every caller was in ``test/``. Hence *extra_caller_dirs* --
    :func:`compute_predicates` passes ``test/`` and ``tools/``. Each caller site
    is tagged with its area, and ``caller_counts_by_area`` carries one entry per
    area including ``0``, so an area the operator expects is never just absent.

    Shim CLASSES are still collected from *toolguard_dir* only, skipping generated
    files and :data:`R1_OUT_OF_SCOPE_PACKAGES`: a shim is defined by the engine
    that owns it, never by a test or a tooling script. An *extra_caller_dirs*
    directory that does not exist contributes zero callers rather than raising.
    """
    shims: List[Dict[str, object]] = []
    producers_by_class: Dict[str, Set[str]] = defaultdict(set)

    # Pass 1: parse every production file once (trees cached for pass 2) and
    # record every class defining __iter__. The class map must be complete
    # before pass 2 runs -- a producer can live in a different module from the
    # class it constructs.
    production_trees: Dict[str, ast.Module] = {}
    class_defs: Dict[str, Dict[str, object]] = {}
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        production_trees[rel] = tree
        if first_segment(rel) in R1_OUT_OF_SCOPE_PACKAGES:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                has_iter = any(
                    isinstance(child, ast.FunctionDef) and child.name == "__iter__"
                    for child in node.body
                )
                if has_iter:
                    class_defs[node.name] = {
                        "class": node.name,
                        "module": rel,
                        "line": node.lineno,
                    }

    # Pass 2a: a function is a "producer" of ClassName when its body constructs
    # it anywhere. Production-only, deliberately: a caller outside the engine
    # reaches a shim through its producer function, never by constructing it.
    for rel, tree in production_trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            for inner in ast.walk(node):
                if (
                    isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Name)
                    and inner.func.id in class_defs
                ):
                    producers_by_class[inner.func.id].add(node.name)

    # Extra-area files are labelled by repo-relative POSIX path
    # ("test/unit/test_resolve.py"), not a toolguard-relative dotted path --
    # they are not inside toolguard_dir.
    areas: List[Tuple[str, Dict[str, ast.Module]]] = [("production", production_trees)]
    for area_label, directory in extra_caller_dirs:
        if not directory.is_dir():
            continue
        area_trees: Dict[str, ast.Module] = {}
        for py_file in iter_python_files(directory):
            area_trees[_best_effort_label(py_file)] = ast.parse(
                py_file.read_text(encoding="utf-8"), filename=str(py_file)
            )
        areas.append((area_label, area_trees))

    # Pass 2b: a caller of the shim tuple-unpacks the result of a producer
    # call, across every area built above.
    callers: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    counts_by_area: Dict[str, Dict[str, int]] = {
        class_name: {area_label: 0 for area_label, _ in areas}
        for class_name in class_defs
    }
    for area_label, trees in areas:
        for rel, tree in trees.items():
            for node in ast.walk(tree):
                targets = None
                call = None
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target = node.targets[0]
                    if (
                        isinstance(target, (ast.Tuple, ast.List))
                        and len(target.elts) >= 2
                    ):
                        targets = target.elts
                        call = node.value
                elif isinstance(node, ast.For):
                    if (
                        isinstance(node.target, (ast.Tuple, ast.List))
                        and len(node.target.elts) >= 2
                    ):
                        targets = node.target.elts
                        call = node.iter
                if targets is None or not isinstance(call, ast.Call):
                    continue
                func = call.func
                func_name = (
                    func.id
                    if isinstance(func, ast.Name)
                    else (func.attr if isinstance(func, ast.Attribute) else None)
                )
                if func_name is None:
                    continue
                for class_name, producer_funcs in producers_by_class.items():
                    if func_name in producer_funcs and class_name in class_defs:
                        callers[class_name].append(
                            {
                                "module": rel,
                                "line": node.lineno,
                                "unpack_via": func_name,
                                "area": area_label,
                            }
                        )
                        counts_by_area[class_name][area_label] += 1

    for class_name, info in class_defs.items():
        shims.append(
            {
                **info,
                "callers": callers.get(class_name, []),
                "caller_counts_by_area": counts_by_area[class_name],
            }
        )
    return shims


# =============================================================================
# --predicates: R1 -- bare verdict TUPLES
# =============================================================================
#
# find_verdict_types (above) inspects CLASS definitions, so it is structurally
# blind to a verdict that was never a class -- a bare `(decision, reason, ...)`
# tuple return. This section is that missing half.

#: The decision strings this engine returns. A function that constructs and
#: returns a tuple whose first element is one of these IS building a verdict
#: tuple, whatever return annotation it does or does not carry.
_VERDICT_TUPLE_DECISION_LITERALS = frozenset({"allow", "deny", "ask"})

#: Minimum tuple width counted as a possible verdict record rather than a
#: strict pair. A 2-tuple is never reported, whatever it contains: a strict
#: pair return is wanted style here, not debt.
_VERDICT_TUPLE_MIN_ARITY = 3


def _tuple_elements(node: Optional[ast.expr]) -> Optional[List[ast.expr]]:
    """
    Return the element-annotation expressions of *node* when it is a
    ``Tuple[...]``/``tuple[...]`` SUBSCRIPT, after stripping at most one
    outer ``Optional[...]`` -- so ``Optional[Tuple[str, str, str]]`` and
    ``Tuple[str, str, str]`` both yield the same 3-element list.

    Returns ``None`` for anything else, including a variadic tuple
    (``Tuple[str, ...]``): an arbitrary-length sequence of one type is a
    different animal from a fixed-arity verdict record.
    """
    if node is None:
        return None
    inner = node
    if (
        isinstance(inner, ast.Subscript)
        and isinstance(inner.value, ast.Name)
        and inner.value.id == "Optional"
    ):
        inner = inner.slice
    if not (
        isinstance(inner, ast.Subscript)
        and isinstance(inner.value, ast.Name)
        and inner.value.id in ("Tuple", "tuple")
    ):
        return None
    elts = inner.slice.elts if isinstance(inner.slice, ast.Tuple) else [inner.slice]
    if any(isinstance(e, ast.Constant) and e.value is Ellipsis for e in elts):
        return None
    return elts


def _is_verdict_shaped_annotation(node: Optional[ast.expr]) -> bool:
    """
    Return True when *node* is a fixed-arity ``Tuple``/``tuple`` return
    annotation (see :func:`_tuple_elements`) with at least
    :data:`_VERDICT_TUPLE_MIN_ARITY` elements whose FIRST element is annotated
    exactly ``str`` -- the shape every real ``(decision, reason, ...)`` verdict
    tuple here shares.

    NECESSARY, NOT SUFFICIENT, and this matters: ``log_writer._parse_discovery_line
    -> Optional[Tuple[str, str, List[str]]]`` is a timestamp/project-root/levels
    triple with no decision in it, and passes. So this only narrows a CANDIDATE
    set; :func:`find_bare_verdict_tuples` then demands actual decision evidence.
    Used alone it produces false positives on this tree.
    """
    elts = _tuple_elements(node)
    if elts is None or len(elts) < _VERDICT_TUPLE_MIN_ARITY:
        return False
    return ast.unparse(elts[0]) == "str"


def _is_literal_decision_tuple(value: ast.expr) -> bool:
    """
    Return True when *value* is a tuple LITERAL of arity >=
    :data:`_VERDICT_TUPLE_MIN_ARITY` whose first element is a string constant in
    :data:`_VERDICT_TUPLE_DECISION_LITERALS` -- the unambiguous case. A function
    writing ``return "deny", reason, pattern`` is constructing a bare verdict
    tuple whether or not it carries a return annotation, and several real hits
    here carried none.
    """
    return (
        isinstance(value, ast.Tuple)
        and len(value.elts) >= _VERDICT_TUPLE_MIN_ARITY
        and isinstance(value.elts[0], ast.Constant)
        and value.elts[0].value in _VERDICT_TUPLE_DECISION_LITERALS
    )


def _call_target_name(call: ast.Call) -> Optional[str]:
    """Return a `Call`'s bare called-name (``f(...)`` -> ``"f"``, ``self.f(...)`` -> ``"f"``)."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _delegates_to_known_verdict(
    func_node: ast.AST, known_verdict_names: Set[str]
) -> bool:
    """
    Return True when *func_node* (already confirmed :func:`_is_verdict_shaped_annotation`
    by the caller) returns, directly or via a same-function tuple-unpack-then-repack, the
    result of a call to a function whose BARE name is in *known_verdict_names*.

    Two delegation shapes, neither involving a hand-listed function name -- only
    the already-discovered verdict-function names, which grow by fixpoint in
    :func:`find_bare_verdict_tuples`:

    1. ``return other_function(...)`` -- direct pass-through.
    2. ``a, b, c, d = other_function(...)`` ... ``return a, b, c`` -- an
       unpack-then-partial-repack. Detected by scanning for a tuple/list
       assignment target of arity >= :data:`_VERDICT_TUPLE_MIN_ARITY` fed by a
       known verdict function, then checking every ``Name`` in a later
       ``return`` tuple against that target's names.

    Two known limits, both from the fact that this is a bare :func:`ast.walk`
    over one function with no import resolution:

    - Names match by BARE IDENTIFIER. An unrelated same-named function elsewhere
      could collide, but only if it also satisfied
      :func:`_is_verdict_shaped_annotation` independently.
    - A ``return``/``Assign`` inside a nested function or lambda is not told
      apart from one in *func_node*'s own body.
    """
    repacked_from_verdict: Set[str] = set()
    for stmt in ast.walk(func_node):
        if (
            isinstance(stmt, ast.Assign)
            and len(stmt.targets) == 1
            and isinstance(stmt.targets[0], (ast.Tuple, ast.List))
            and len(stmt.targets[0].elts) >= _VERDICT_TUPLE_MIN_ARITY
            and isinstance(stmt.value, ast.Call)
            and _call_target_name(stmt.value) in known_verdict_names
        ):
            for elt in stmt.targets[0].elts:
                if isinstance(elt, ast.Name):
                    repacked_from_verdict.add(elt.id)

    for stmt in ast.walk(func_node):
        if not isinstance(stmt, ast.Return) or stmt.value is None:
            continue
        value = stmt.value
        if isinstance(value, ast.Call):
            if _call_target_name(value) in known_verdict_names:
                return True
        elif (
            isinstance(value, ast.Tuple) and len(value.elts) >= _VERDICT_TUPLE_MIN_ARITY
        ):
            names_in_return = [e.id for e in value.elts if isinstance(e, ast.Name)]
            if names_in_return and all(
                n in repacked_from_verdict for n in names_in_return
            ):
                return True
    return False


def find_bare_verdict_tuples(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> List[Dict[str, object]]:
    """
    Return every function under *toolguard_dir* that returns a BARE verdict
    tuple -- ``(decision, reason, ...)`` as a plain tuple literal, never wrapped
    in a class. Skips generated files and :data:`R1_OUT_OF_SCOPE_PACKAGES`.

    Two structural signals, computed to a FIXPOINT and never a hand-maintained
    list of function names:

    1. **Literal seed** (:func:`_is_literal_decision_tuple`) -- sufficient on its
       own, independent of any annotation.
    2. **Delegation** (:func:`_delegates_to_known_verdict`) -- a
       verdict-SHAPED return annotation AND a return of an already-classified
       verdict function's result. The annotation alone is not enough; see
       :func:`_is_verdict_shaped_annotation`.

    The fixpoint is not decoration: propagation chains more than one hop here. A
    public entry point can delegate to a wrapper that itself only qualifies by
    unpack-then-repack of a literal seed, so it joins in round 2. A single pass
    would report the seed and miss both functions above it.

    A closure is discovered like any other function and reported at its own
    ``lineno``.

    Returns:
        ``{"module", "function", "line", "basis"}`` dicts sorted by
        ``(module, line, function)``. ``basis`` names which signal matched.
    """
    functions: Dict[Tuple[str, str], Dict[str, object]] = {}
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        if first_segment(rel) in R1_OUT_OF_SCOPE_PACKAGES:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            key = (rel, node.name)
            functions[key] = {
                "node": node,
                "module": rel,
                "line": node.lineno,
                "annotation_candidate": _is_verdict_shaped_annotation(node.returns),
            }

    verdict_keys: Set[Tuple[str, str]] = set()
    basis: Dict[Tuple[str, str], str] = {}

    # Pass 1 (seed): literal decision-tuple return, independent of annotation.
    for key, info in functions.items():
        for stmt in ast.walk(info["node"]):
            if isinstance(stmt, ast.Return) and stmt.value is not None:
                if _is_literal_decision_tuple(stmt.value):
                    verdict_keys.add(key)
                    basis[key] = "literal decision-tuple return"
                    break

    # Pass 2 (propagation to fixpoint): an annotation-candidate function that
    # delegates to an already-classified verdict function joins the set too.
    changed = True
    while changed:
        changed = False
        known_names = {name for (_mod, name) in verdict_keys}
        for key, info in functions.items():
            if key in verdict_keys or not info["annotation_candidate"]:
                continue
            if _delegates_to_known_verdict(info["node"], known_names):
                verdict_keys.add(key)
                basis[key] = "delegates to a known verdict function"
                changed = True

    found = [
        {
            "module": key[0],
            "function": key[1],
            "line": functions[key]["line"],
            "basis": basis[key],
        }
        for key in verdict_keys
    ]
    return sorted(found, key=lambda d: (d["module"], d["line"], d["function"]))


# =============================================================================
# --predicates: R2 -- ToolPatternLayer parallel arrays
# =============================================================================


def find_parallel_arrays(
    toolguard_dir: Path = TOOLGUARD_DIR, class_name: str = "ToolPatternLayer"
) -> List[Dict[str, object]]:
    """
    Return the ``(base, base_entries)`` annotated-field pairs declared on
    *class_name* -- the parallel-array shape R2 targets.

    **Informational only; this does not gate R2.** It is a NAME-based check -- a
    hardcoded class name plus an ``_entries`` suffix -- and the same hazard
    survives a rename, a dict-of-lists, a ``@property``, a sibling class, or
    ``__init__`` assignment untouched. Of the nine synthetic gaming variants in
    ``TestFindIndexParallelAccess`` it catches one. It is also blind to the
    hazard expressed as a method pair rather than fields. Kept only so runs
    stay comparable with past ones; :func:`find_index_parallel_access` is the
    real gate.
    """
    groups: List[Dict[str, object]] = []
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                field_names = [
                    stmt.target.id
                    for stmt in node.body
                    if isinstance(stmt, ast.AnnAssign)
                    and isinstance(stmt.target, ast.Name)
                ]
                for name in field_names:
                    if name.endswith("_entries"):
                        continue
                    paired = f"{name}_entries"
                    if paired in field_names:
                        groups.append(
                            {
                                "class": class_name,
                                "module": rel,
                                "line": node.lineno,
                                "base_field": name,
                                "entries_field": paired,
                            }
                        )
    return groups


def _expr_key(expr: ast.expr) -> str:
    """
    Return a normalized source string for *expr*, used only to decide whether
    two AST expressions denote the same thing. Falls back to ``ast.dump`` for
    anything ``ast.unparse`` cannot render.
    """
    try:
        return ast.unparse(expr)
    except Exception:
        return ast.dump(expr)


def _index_call_receiver(node: ast.expr) -> Optional[ast.expr]:
    """
    If *node* is a call of the exact shape ``<receiver>.index(<arg>, ...)``,
    return the receiver expression; otherwise return ``None``.
    """
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "index"
        and node.args
    ):
        return node.func.value
    return None


def _is_two_different_index_lookup(node: ast.AST) -> bool:
    """
    Return ``True`` when *node* is an ``A[B.index(x)]`` Subscript whose
    subscripted expression ``A`` and ``.index()`` receiver ``B`` are
    syntactically different.
    """
    if not isinstance(node, ast.Subscript):
        return False
    receiver = _index_call_receiver(node.slice)
    if receiver is None:
        return False
    return _expr_key(node.value) != _expr_key(receiver)


def find_index_parallel_access(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> List[Dict[str, object]]:
    """
    Return every site reading TWO DIFFERENT sequences by a SHARED, derived index
    -- the R2 hazard itself. **Gates R2's pass/fail, together with
    :func:`find_drift_guards`.**

    It inspects USE sites only, never declarations, so no class name and no
    field-name suffix appears anywhere below. That is the whole point: it is
    exactly as blind to a class rename, an ``_entries``-to-``_rules`` rename, or
    a fields-to-dict-of-lists reshape as the hazard itself is.

    Two shapes, both modelled on real instances measured here:

    - ``A[B.index(x)]`` -- a ``Subscript`` whose slice calls ``.index()`` on a
      different expression than the one being subscripted. This catches the
      method-pair instance the name-based check could never reach, with no
      special-casing, because it never asks where either sequence came from.
    - ``zip(A, B, ...)`` over two or more syntactically different sequences --
      the same "two collections, one shared index" hazard in a filtering guise
      rather than a lookup one, and invisible to a ``.index(``-only search
      because it calls no ``.index()`` at all.

    "Different expression" is source-text comparison (:func:`_expr_key`), not
    alias resolution to an originating attribute chain. Deliberate: every
    instance observed here already uses two differently-named locals or chains
    at the point of indexing, so alias resolution would improve the REPORT --
    an attribute chain instead of a local name -- and not the detection.
    """
    hits: List[Dict[str, object]] = []
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Subscript):
                receiver = _index_call_receiver(node.slice)
                if receiver is not None:
                    container_key = _expr_key(node.value)
                    index_key = _expr_key(receiver)
                    if container_key != index_key:
                        hits.append(
                            {
                                "module": rel,
                                "line": node.lineno,
                                "kind": "index_lookup",
                                "container": container_key,
                                "index_source": index_key,
                            }
                        )
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "zip"
                and len(node.args) >= 2
            ):
                arg_keys = [_expr_key(a) for a in node.args]
                if len(set(arg_keys)) >= 2:
                    hits.append(
                        {
                            "module": rel,
                            "line": node.lineno,
                            "kind": "zip",
                            "sequences": arg_keys,
                        }
                    )
    return sorted(hits, key=lambda d: (d["module"], d["line"]))


def _len_call_arg(expr: ast.expr) -> Optional[ast.expr]:
    """If *expr* is exactly ``len(<x>)``, return ``<x>``; otherwise ``None``."""
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "len"
        and len(expr.args) == 1
    ):
        return expr.args[0]
    return None


def _unwrap_set_call(expr: ast.expr) -> ast.expr:
    """If *expr* is exactly ``set(<x>)``, return ``<x>``; otherwise *expr* unchanged."""
    if (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "set"
        and len(expr.args) == 1
    ):
        return expr.args[0]
    return expr


def find_drift_guards(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> List[Dict[str, object]]:
    """
    Return every ``if len(A) != len(B)`` (or ``==``) comparison sitting in the
    SAME FUNCTION as an index-parallel read -- a machine-visible PROXY for
    clause 3 of R2's predicate, "no prose-defended index-alignment invariant
    remains".

    Nothing here reads a docstring. The proxy works in one direction only:
    defensively comparing two sequences' lengths before trusting an
    index-parallel read of them is the shape a hand-written alignment invariant
    takes once someone has worried about it drifting. **The converse does not
    hold, and this is the honest limit of R2's clause 3: an invariant defended
    by prose alone, with no length check, is invisible here.** (Not invisible to
    R2 as a whole -- :func:`find_index_parallel_access` still catches the
    index-parallel read such an invariant is protecting, whatever the fields are
    called. What escapes is the prose clause specifically.)

    Requiring co-location with an actual index-parallel read is deliberate. An
    unscoped ``len(A) != len(B)`` scan has live false positives here -- e.g.
    ``parser.command_extractor``'s ``len(bn) == len(prefix)``, a string-prefix
    boundary check with no array in sight. Scoping to the hazard's own function
    separates those out without a name-based heuristic. (The separate
    ``len(set(x)) != len(x)`` duplicate-check shape is filtered below by
    :func:`_unwrap_set_call`, not by this scoping.)
    """
    hits: List[Dict[str, object]] = []
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            has_index_access = any(
                _is_two_different_index_lookup(n) for n in ast.walk(func)
            )
            if not has_index_access:
                continue
            for node in ast.walk(func):
                if not isinstance(node, ast.Compare):
                    continue
                if len(node.ops) != 1 or not isinstance(
                    node.ops[0], (ast.NotEq, ast.Eq)
                ):
                    continue
                left = _len_call_arg(node.left)
                right = _len_call_arg(node.comparators[0])
                if left is None or right is None:
                    continue
                if _expr_key(_unwrap_set_call(left)) == _expr_key(
                    _unwrap_set_call(right)
                ):
                    continue  # `len(set(x)) != len(x)` duplicate-check shape, not an alignment guard
                hits.append(
                    {
                        "module": rel,
                        "function": func.name,
                        "line": node.lineno,
                        "left": _expr_key(left),
                        "right": _expr_key(right),
                    }
                )
    return sorted(hits, key=lambda d: (d["module"], d["line"]))


#: Clauses of R2's stated predicate this module cannot mechanically verify,
#: printed rather than silently dropped, and judged by human or judge-subagent
#: review instead.
#:
#: R2 has three clauses. Two are covered above -- no parallel arrays, and no
#: prose-defended index-alignment invariant, the latter only by the
#: one-directional proxy :func:`find_drift_guards` describes. This register
#: holds the third.
R2_UNCHECKED_CLAUSES: Tuple[Dict[str, str], ...] = (
    {
        "clause": "stripped patterns are a derived property of RuleEntry",
        "reason": (
            "not mechanically checkable by AST inspection alone -- would "
            "require confirming a stripped-pattern collection is PRODUCED "
            "BY mapping over RuleEntry objects (e.g. a "
            "RuleEntry.stripped_pattern property consumed via a "
            "comprehension/property) rather than independently constructed "
            "and merely co-located; both the real fix and a same-shaped "
            "rename read identically to this detector's siblings"
        ),
    },
)


# =============================================================================
# --predicates: R3 -- reason-string parsing
# =============================================================================

#: The one sanctioned reason-parsing site: the canonical fallback-marker
#: classifier, public precisely so this pattern is not duplicated ad hoc. It is
#: the structured contract other code calls into instead of parsing reason text
#: itself, so it is excluded from the R3 count rather than counted as a
#: violation -- and it is the site R3 may eventually replace outright.
R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}

#: String methods that recover STRUCTURED DATA -- a substring, a position, an
#: index -- out of a reason-named string when called ON it, e.g.
#: ``reason.split``. Wider than the obvious ``{split, startswith, endswith}``
#: after a real miss: a helper recovering a ``(sub_command, matched_rule)`` pair
#: via ``rsplit(" -> ", 1)`` went undetected.
_REASON_STRING_METHODS = {
    "split",
    "rsplit",
    "startswith",
    "endswith",
    "partition",
    "rpartition",
    "rindex",
    "index",
    "find",
}

#: ``re`` methods whose reason-bearing operand is an ARGUMENT rather than the
#: receiver. Both ``re.match(pattern, reason)`` and
#: ``SOME_PATTERN.match(reason)`` put ``reason`` in the argument list, so a
#: receiver-only scan misses them entirely -- which is what happened.
_REASON_REGEX_METHODS = {"match", "search", "fullmatch"}


def _name_of(node: ast.expr) -> Optional[str]:
    """Return a Name's id or an Attribute's trailing attr, else None."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _is_reason_named(node: ast.expr) -> bool:
    """Return True when *node* is a Name/Attribute whose own name contains "reason"."""
    name = _name_of(node)
    return bool(name) and "reason" in name.lower()


def _enclosing_function_name(tree: ast.Module, target: ast.AST) -> Optional[str]:
    """Return the name of the nearest enclosing function/method of *target*, if any."""
    best: Optional[str] = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if target in ast.walk(node):
                best = node.name
    return best


def find_reason_parsing_sites(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> List[Dict[str, object]]:
    """
    Return every production site that extracts structured meaning from a
    ``reason``-named string, excluding :data:`R3_SANCTIONED_SITES`.

    Three shapes, all keyed on a Name/Attribute whose OWN name contains "reason"
    (case-insensitive) -- which is why a reassignment like
    ``reason_body = resolved.reason`` stays caught:

    1. A :data:`_REASON_STRING_METHODS` call on a reason-named RECEIVER.
    2. A :data:`_REASON_REGEX_METHODS` call with a reason-named ARGUMENT.
    3. An ``in`` membership test against a reason-named value.

    KNOWN LIMIT: name-based, not data-flow. A value split out of a reason string
    into a differently-named local is not followed past the rename -- the
    ``reason.split`` is caught, a further parse of ``part`` is not, because
    nothing in "part" says where it came from.
    """
    sites: List[Dict[str, object]] = []
    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        lines = source.splitlines()
        for node in ast.walk(tree):
            expr = None
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _REASON_STRING_METHODS
                and _is_reason_named(node.func.value)
            ):
                expr = lines[node.lineno - 1].strip()
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in _REASON_REGEX_METHODS
                and any(_is_reason_named(arg) for arg in node.args)
            ):
                expr = lines[node.lineno - 1].strip()
            elif isinstance(node, ast.Compare) and any(
                isinstance(op, ast.In) for op in node.ops
            ):
                if any(_is_reason_named(c) for c in node.comparators):
                    expr = lines[node.lineno - 1].strip()
            if expr is None:
                continue
            func_name = _enclosing_function_name(tree, node)
            if (py_file.name, func_name) in R3_SANCTIONED_SITES:
                continue
            sites.append(
                {
                    "module": rel,
                    "line": node.lineno,
                    "expression": expr,
                    "function": func_name,
                }
            )
    # One line can trip two patterns at once -- `reason.split(...) if ": " in
    # reason else None` matches shapes 1 and 3 -- so report one site per
    # (module, line) rather than double-counting.
    seen: Set[Tuple[str, int]] = set()
    unique_sites = []
    for site in sites:
        key = (site["module"], site["line"])
        if key in seen:
            continue
        seen.add(key)
        unique_sites.append(site)
    return unique_sites


# =============================================================================
# --predicates: R5 -- runtime/scripts leafness + cycles
# =============================================================================


#: Default location of the project manifest whose ``[project.scripts]`` block
#: :func:`parse_entry_point_modules` reads.
PYPROJECT_TOML = REPO_ROOT / "pyproject.toml"


def parse_entry_point_modules(
    pyproject_toml_path: Path = PYPROJECT_TOML,
) -> FrozenSet[str]:
    """
    Return every toolguard-relative module dotted path
    (:func:`relative_module_path`'s spelling, e.g. ``"hook"``,
    ``"tools.security_audit"``, ``"scripts.migrate_permissions"``) that
    *pyproject_toml_path*'s ``[project.scripts]`` block names as a console
    script's IMPLEMENTING module -- the left-hand side of each
    ``"module.path:function"`` target, with the leading ``toolguard.``
    stripped.

    **``[project.scripts]``, not the ``.pyscn.toml`` layer label, defines "entry
    point" for R5, and that choice is load-bearing.** The layer label is an
    editable annotation: a 3-line ``.pyscn.toml`` edit took R5's non-leaf list
    from 7 to 2 with every architecture test still green -- the predicate could
    be satisfied without touching a line of Python. ``[project.scripts]`` cannot
    be gamed that way, because editing it changes what ``pip``/``uv`` install.

    A target pointing outside ``toolguard`` is skipped rather than raising: a
    console script implemented by another package is not this predicate's
    business.
    """
    with pyproject_toml_path.open("rb") as fh:
        data = tomllib.load(fh)
    scripts = data.get("project", {}).get("scripts", {})
    modules: Set[str] = set()
    for target in scripts.values():
        module_path = target.split(":", 1)[0]
        if module_path == "toolguard":
            modules.add("")
        elif module_path.startswith("toolguard."):
            modules.add(module_path[len("toolguard.") :])
    return frozenset(modules)


def find_non_leaf_entry_points(
    graph: Dict[str, Set[str]],
    entry_point_modules: FrozenSet[str],
) -> List[Dict[str, object]]:
    """
    Return every module that is EITHER a declared console-script entry point
    (*entry_point_modules*, from :func:`parse_entry_point_modules`) OR a
    member of the ``scripts`` package, that has fan-in > 0 (something else in
    toolguard imports it) -- i.e. is NOT a leaf -- with its importers.

    **This function does not read ``.pyscn.toml`` at all.** Deliberate, not an
    oversight: it is what makes relabelling a layer unable to move this
    predicate's verdict. See :func:`parse_entry_point_modules`.

    An ordinary module is not judged at all -- only something that should be
    invoked as a process rather than imported. A layer-based version also flagged
    the service modules the hook imports, which is intra-layer fan-in the design
    calls for, not a violation.

    ``scripts`` package membership stays as a second, independent criterion:
    not every module under ``toolguard/scripts/`` need be a declared
    ``[project.scripts]`` target, and the package boundary is a real fact about
    the repo layout either way.
    """
    incoming: Dict[str, List[str]] = defaultdict(list)
    for source, targets in graph.items():
        for target in targets:
            incoming[target].append(source)

    results = []
    for module in sorted(graph.keys()):
        is_entry_point = module in entry_point_modules
        is_scripts_pkg = first_segment(module) == "scripts"
        if not (is_entry_point or is_scripts_pkg):
            continue
        importers = sorted(incoming.get(module, []))
        if importers:
            results.append(
                {
                    "module": module,
                    "reason": "scripts_package" if is_scripts_pkg else "entry_point",
                    "importers": importers,
                }
            )
    return results


def _drop_packages_from_graph(
    graph: Dict[str, Set[str]], packages: Sequence[str]
) -> Dict[str, Set[str]]:
    """
    Return a copy of *graph* with every node -- and every edge into or out of
    it -- whose :func:`first_segment` is in *packages* removed entirely, as if
    that package had never been scanned.

    Dropped from the node set rather than filtered out of the report, so an
    all-excluded-package cycle cannot survive: none of its edges exist in the
    returned graph to form one.
    """
    return {
        source: {t for t in targets if first_segment(t) not in packages}
        for source, targets in graph.items()
        if first_segment(source) not in packages
    }


def find_import_cycles(
    graph: Dict[str, Set[str]], out_of_scope_packages: Sequence[str] = ()
) -> List[List[str]]:
    """
    Return every strongly connected component of size > 1 (an import cycle) in
    *graph*, after dropping every module under an *out_of_scope_packages*
    package entirely (:func:`_drop_packages_from_graph`).

    Without a filter R5 is unpassable: ``parser.command_extractor <->
    parser.multiline`` is a live cycle entirely inside the package the ticket
    puts out of scope, so no in-scope change can ever clear it.
    :func:`compute_predicates` passes :data:`R5_OUT_OF_SCOPE_PACKAGES` for that
    reason. ``--metrics`` calls this with the default ``()`` and does report
    that cycle -- it is measuring raw structure, not scoring a step.
    """
    scoped_graph = (
        _drop_packages_from_graph(graph, out_of_scope_packages)
        if out_of_scope_packages
        else graph
    )
    return [comp for comp in tarjan_scc(scoped_graph) if len(comp) > 1]


# =============================================================================
# --predicates: R6 -- private-name reaches into the config+engine layers
# =============================================================================

#: R6's GUARDED side: every module in one of these ``.pyscn.toml`` layers holds
#: names that must not be reached from outside by their private
#: (leading-underscore) spelling.
#:
#: Derived from the layer map rather than hand-listed, because the hand-listed
#: version drifted: it named four modules from the pre-TOO-45 architecture and
#: could not see anything added since -- including modules squarely in "the
#: engine" or "the config model" by any reading of R6's own title.
R6_GUARDED_LAYERS = ("config", "engine")

#: R6's REACH-FROM side: where a private reach into :data:`R6_GUARDED_LAYERS`
#: counts as a violation.
#:
#: ``runtime`` belongs here as much as ``tooling`` does -- R6's own stated
#: extension is that the live hook must consume the same interface tooling does,
#: and an earlier version restricted to ``tools``/``scripts`` missed 4 of the 5
#: real private reaches on the tree, all of them in ``runtime``.
R6_CHECKED_LAYERS = ("tooling", "runtime")

#: Clauses of R6's stated predicate this detector cannot mechanically verify,
#: printed rather than silently dropped -- the ticket requires the instrument to
#: report what it CANNOT check.
R6_KNOWN_LIMITATIONS: Tuple[Dict[str, str], ...] = (
    {
        "clause": "value flowing through a non-import intermediate variable",
        "reason": (
            "aliases are traced back to an import statement only -- "
            "`cfg = config; helper = cfg; helper._x` is not followed past "
            "the second assignment, since that requires general dataflow "
            "analysis, not AST pattern matching"
        ),
    },
    {
        "clause": "fully dynamic name access",
        "reason": (
            "`mod.__dict__['_x']`, `vars(mod)['_x']`, `globals()['_x']`, and "
            "`importlib.import_module(...)` are not detected at all; "
            "`getattr(mod, name_var)` with a non-literal second argument IS "
            "detected as a site but cannot be resolved -- see `unresolvable`"
        ),
    },
    {
        "clause": "re-export bindings created inside a function/if/try body",
        "reason": (
            "`resolve_defining_module` only inspects a module's TOP-LEVEL "
            "statements when following a re-export chain -- a conditional or "
            "lazily-computed re-export is invisible to it"
        ),
    },
    {
        "clause": "a module `.pyscn.toml` does not map to any layer",
        "reason": (
            "invisible on either side (guarded or reach-from) of this "
            "predicate -- see `--layers`' completeness check for what is "
            "unmapped; a module that never made it into the layer map was "
            "never in scope for R6 to begin with"
        ),
    },
)


def _r6_guarded_modules(arch: ArchitectureConfig) -> FrozenSet[str]:
    """
    Return every top-level module name in a :data:`R6_GUARDED_LAYERS` layer of
    *arch*, MINUS :data:`R1_OUT_OF_SCOPE_PACKAGES`.

    That subtraction is the whole reason this is a function. ``parser`` is
    listed under the engine layer -- it is decision-adjacent parsing code -- so
    a plain layer lookup would pull an out-of-scope package into R6's guarded
    set.
    """
    return frozenset(
        pkg
        for layer in arch.layers
        if layer.name in R6_GUARDED_LAYERS
        for pkg in layer.packages
        if pkg not in R1_OUT_OF_SCOPE_PACKAGES
    )


def _r6_checked_modules(arch: ArchitectureConfig) -> FrozenSet[str]:
    """Return every top-level module name in a :data:`R6_CHECKED_LAYERS` layer of *arch*."""
    return frozenset(
        pkg
        for layer in arch.layers
        if layer.name in R6_CHECKED_LAYERS
        for pkg in layer.packages
    )


def _is_private_name(name: str) -> bool:
    """True for a leading-underscore, non-dunder name -- what this predicate treats as private."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _module_source_path(module_rel: str, toolguard_dir: Path) -> Optional[Path]:
    """
    Return the source file for toolguard-relative dotted module *module_rel*
    (as produced by :func:`resolve_toolguard_import`), or ``None`` if no such
    file exists under *toolguard_dir*. Handles both a plain module
    (``"config"`` -> ``config.py``) and a package (``"parser"`` ->
    ``parser/__init__.py``).
    """
    if module_rel == "":
        candidate = toolguard_dir / "__init__.py"
        return candidate if candidate.exists() else None
    parts = module_rel.split(".")
    as_module = toolguard_dir.joinpath(*parts).with_suffix(".py")
    if as_module.exists():
        return as_module
    as_package_init = toolguard_dir.joinpath(*parts, "__init__.py")
    return as_package_init if as_package_init.exists() else None


def _find_top_level_binding(
    tree: ast.Module, name: str, module_rel: str
) -> Tuple[str, Optional[Tuple[Optional[str], str]]]:
    """
    Find how *name* is bound at *tree*'s top level (*tree* being *module_rel*'s
    own parsed source).

    Returns a ``(kind, info)`` pair:

    - ``("defined", None)`` -- *name* is a ``def``/``class``/assignment target
      in this module, i.e. this module is where the name actually lives.
    - ``("reexport", (origin_module, origin_name))`` -- *name* is bound by a
      top-level ``from X import Y [as name]``; *origin_module* is ``X``
      resolved to a toolguard-relative path (``None`` if ``X`` is outside
      ``toolguard`` entirely, e.g. stdlib/third-party), *origin_name* is ``Y``
      (the name as spelled in the origin module, before any ``as``).
    - ``("undefined", None)`` -- *name* is not bound at this module's top
      level at all (dynamic construction, or simply not present).

    Module-level statements only; a binding created inside a function, ``if`` or
    ``try`` is invisible here and is registered in :data:`R6_KNOWN_LIMITATIONS`.
    """
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if stmt.name == name:
                return "defined", None
        elif isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return "defined", None
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.target.id == name:
                return "defined", None
        elif isinstance(stmt, ast.ImportFrom):
            for alias in stmt.names:
                bound = alias.asname or alias.name
                if bound == name:
                    origin_module = resolve_toolguard_import(
                        stmt.module, stmt.level, module_rel
                    )
                    return "reexport", (origin_module, alias.name)
    return "undefined", None


def resolve_defining_module(
    module_rel: str,
    name: str,
    toolguard_dir: Path,
    depth: int = 0,
    visited: FrozenSet[Tuple[str, str]] = frozenset(),
) -> Tuple[Optional[str], Optional[str]]:
    """
    Follow re-exports to find where *name* is actually DEFINED, starting from
    *module_rel* (a toolguard-relative dotted module path).

    This is what stops a violation being cleared by re-pointing the import at
    the module that DEFINES the private name instead of the one that re-exports
    it -- a move that changes nothing about what tooling can reach, and which
    did once make the only reported violation disappear.

    Returns ``(defining_module, failure_reason)``: exactly one is ``None``.
    *defining_module* is the toolguard-relative module that actually owns
    *name*. *failure_reason* is a human-readable string explaining why no
    defining module could be pinned down -- EXCEPT the sentinel
    ``"reexport-external"``, which means the chain legitimately terminates
    outside ``toolguard`` (e.g. a private helper re-exported from a
    third-party library) and is therefore not a toolguard-internal reach at
    all; callers must treat that as "not a violation", not "cannot check".

    Depth 0 and deeper are treated differently on purpose. At depth 0 -- the
    module the caller literally named -- a missing source file, or one that does
    not define *name*, falls back to *module_rel* itself rather than being
    called unresolvable: a real import could not have executed otherwise, and a
    synthetic fixture naming a guarded module without writing its source stays
    meaningful. Only a FOLLOWED re-export hop that fails to resolve is genuinely
    ambiguous.
    """
    if (module_rel, name) in visited:
        return None, f"cycle following re-export chain back to '{module_rel}.{name}'"
    path = _module_source_path(module_rel, toolguard_dir)
    if path is None:
        if depth == 0:
            return module_rel, None
        return (
            None,
            f"re-export target module '{module_rel}' has no source file on disk",
        )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    kind, info = _find_top_level_binding(tree, name, module_rel)
    if kind == "defined":
        return module_rel, None
    if kind == "reexport":
        origin_module, origin_name = info  # type: ignore[misc]
        if origin_module is None:
            return None, "reexport-external"
        return resolve_defining_module(
            origin_module,
            origin_name,
            toolguard_dir,
            depth + 1,
            visited | {(module_rel, name)},
        )
    # kind == "undefined"
    if depth == 0:
        return module_rel, None
    return (
        None,
        f"name '{name}' not found at the top level of re-export target '{module_rel}'",
    )


def _bind_module_aliases(
    tree: ast.Module, importer_rel: str, toolguard_dir: Path
) -> Dict[str, str]:
    """
    Return ``{local_name: toolguard-relative module path}`` for every
    WHOLE-MODULE import binding anywhere in *tree* -- ``import
    toolguard.config``, ``import toolguard.config as cfg``, ``from toolguard
    import config``, ``from toolguard import config as cfg`` -- so a later
    attribute/``getattr`` access can be traced back to the module it targets.

    Does NOT track a from-import of a specific NAME (``from toolguard.config
    import load_configuration``) -- that binds a name to a VALUE, not a module;
    :func:`scan_private_reaches` handles that case on its own.

    Walks the whole tree, not just the top level: an alias bound inside a
    function must not be invisible.

    ``from toolguard import X`` is syntactically identical whether ``X`` is a
    submodule or a name defined in ``toolguard/__init__.py``, so ``X`` is bound
    as a module alias only when it has a source file on disk -- the same rule
    Python itself applies by trying the submodule import first.
    """
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    target = resolve_toolguard_import(alias.name, 0, importer_rel)
                    if target is not None:
                        aliases[alias.asname] = target
                else:
                    # Bare `import toolguard.config` binds only `toolguard`;
                    # `_resolve_expr_to_module` walks the rest of the chain.
                    first = alias.name.split(".")[0]
                    target = resolve_toolguard_import(first, 0, importer_rel)
                    if target is not None:
                        aliases[first] = target
        elif isinstance(node, ast.ImportFrom):
            module_target = resolve_toolguard_import(
                node.module, node.level, importer_rel
            )
            if module_target is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                candidate = (
                    f"{module_target}.{alias.name}" if module_target else alias.name
                )
                if _module_source_path(candidate, toolguard_dir) is not None:
                    aliases[alias.asname or alias.name] = candidate
    return aliases


def _resolve_expr_to_module(
    node: ast.expr, aliases: Dict[str, str], toolguard_dir: Path
) -> Optional[str]:
    """
    Resolve *node* -- the object being attribute-accessed, or ``getattr``'s
    first argument -- back to a toolguard-relative module path, using
    *aliases* (:func:`_bind_module_aliases`). Returns ``None`` when *node* is
    not a traceable module reference -- an arbitrary object, a call result, an
    instance attribute. Deliberately conservative: it must never manufacture a
    module path for an expression it did not trace back to an import.

    A multi-hop chain is followed past the first hop only when the accumulated
    path is a real file on disk. Otherwise ``resolve.public_thing._private`` --
    an attribute of a module-level object, not a module -- would read as a reach
    into a fabricated submodule.
    """
    if isinstance(node, ast.Name):
        return aliases.get(node.id)
    if isinstance(node, ast.Attribute):
        base = _resolve_expr_to_module(node.value, aliases, toolguard_dir)
        if base is None:
            return None
        candidate = f"{base}.{node.attr}" if base else node.attr
        return (
            candidate
            if _module_source_path(candidate, toolguard_dir) is not None
            else None
        )
    return None


@dataclass
class PrivateReachReport:
    """Result of :func:`scan_private_reaches`: violations plus what could not be checked."""

    sites: List[Dict[str, object]] = field(default_factory=list)
    unresolvable: List[Dict[str, object]] = field(default_factory=list)


def scan_private_reaches(
    toolguard_dir: Path = TOOLGUARD_DIR, arch: Optional[ArchitectureConfig] = None
) -> PrivateReachReport:
    """
    Find every private-name (leading-underscore, non-dunder) reach from a
    :data:`R6_CHECKED_LAYERS` module into a :data:`R6_GUARDED_LAYERS` one, by
    three routes: ``from mod import _x``, attribute access (``mod._x``, including
    through an aliased or dotted import), and ``getattr(mod, "_x")`` with a
    literal name. Re-exports are followed to the DEFINING module
    (:func:`resolve_defining_module`). Skips generated files.

    Returns violations (``sites``) AND everything it could not resolve either way
    (``unresolvable``), which is the point of returning a report rather than a
    list -- see :data:`R6_KNOWN_LIMITATIONS`.
    """
    if arch is None:
        arch = parse_architecture_config()
    package_map = arch.package_to_layer()
    guarded = _r6_guarded_modules(arch)
    checked = _r6_checked_modules(arch)
    report = PrivateReachReport()

    def record_reach(
        importer: str, line: int, target_module: str, name: str, route: str
    ) -> None:
        defining_module, reason = resolve_defining_module(
            target_module, name, toolguard_dir
        )
        if defining_module is not None:
            if first_segment(defining_module) in guarded:
                report.sites.append(
                    {
                        "importer": importer,
                        "line": line,
                        "target_module": target_module,
                        "defining_module": defining_module,
                        "private_name": name,
                        "route": route,
                        "layer": package_map.get(first_segment(defining_module)),
                    }
                )
            return
        if reason == "reexport-external":
            return
        report.unresolvable.append(
            {
                "importer": importer,
                "line": line,
                "target_module": target_module,
                "private_name": name,
                "route": route,
                "reason": reason,
            }
        )

    for py_file in iter_source_files(toolguard_dir):
        rel = relative_module_path(py_file, toolguard_dir)
        if first_segment(rel) not in checked:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        aliases = _bind_module_aliases(tree, rel, toolguard_dir)

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                target = resolve_toolguard_import(node.module, node.level, rel)
                if target is None:
                    continue
                for alias in node.names:
                    if _is_private_name(alias.name):
                        # alias.lineno, not node.lineno: each name in a
                        # multi-line `from X import (a, b, c)` reports on its
                        # own line.
                        record_reach(
                            rel,
                            alias.lineno,
                            target,
                            alias.name,
                            "from_import",
                        )
            elif isinstance(node, ast.Attribute):
                if not _is_private_name(node.attr):
                    continue
                base = _resolve_expr_to_module(node.value, aliases, toolguard_dir)
                if base is not None:
                    record_reach(rel, node.lineno, base, node.attr, "attribute_access")
            elif isinstance(node, ast.Call):
                if not (isinstance(node.func, ast.Name) and node.func.id == "getattr"):
                    continue
                if len(node.args) < 2:
                    continue
                base = _resolve_expr_to_module(node.args[0], aliases, toolguard_dir)
                if base is None:
                    continue
                name_arg = node.args[1]
                if isinstance(name_arg, ast.Constant) and isinstance(
                    name_arg.value, str
                ):
                    if _is_private_name(name_arg.value):
                        record_reach(rel, node.lineno, base, name_arg.value, "getattr")
                else:
                    report.unresolvable.append(
                        {
                            "importer": rel,
                            "line": node.lineno,
                            "target_module": base,
                            "private_name": None,
                            "route": "getattr",
                            "reason": (
                                "getattr() attribute name is not a string "
                                "literal -- cannot verify statically"
                            ),
                        }
                    )

    report.sites.sort(key=lambda s: (str(s["importer"]), int(s["line"])))
    report.unresolvable.sort(key=lambda s: (str(s["importer"]), int(s["line"])))
    return report


def find_private_imports(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> List[Dict[str, object]]:
    """
    Violations-only view of :func:`scan_private_reaches`, for callers that want
    the sites and not the full report.
    """
    return scan_private_reaches(toolguard_dir).sites


# =============================================================================
# --predicates: enrichment footprint (tracked diagnostic, not a predicate)
# =============================================================================


#: Both spellings this footprint tracks: the Python identifier (snake_case,
#: used for the dataclass field/property/parameter name throughout the
#: engine) and the JSON field (camelCase, used only as a string literal --
#: Claude Code's hookSpecificOutput key).
_ENRICHMENT_SPELLINGS = ("additional_context", "additionalContext")


@dataclass
class EnrichmentFootprint:
    """
    Identifier-level vs. prose-only references to the enrichment feature.

    Tokenized, not substring-scanned. A raw text scan counts a docstring mention
    exactly like a real call, and did over-report here: a module can keep several
    docstring mentions and zero real references after its logic moves elsewhere,
    yet still be counted as coupled.

    Attributes:
        coupled: Files with at least one ``NAME``-token reference -- real code
            coupling.
        prose_only: Files mentioning either spelling ONLY inside a
            ``STRING``/``COMMENT`` token. Reported separately rather than
            dropped, so a file that talks about enrichment without
            participating in it does not vanish.
        occurrences_by_file: ``{coupled file: NAME-token occurrence count}``.
            The FILE count has a floor -- some files must legitimately name the
            field to declare, produce or render it -- so a step that removes
            most of the THREADING can look completely flat on ``coupled``
            alone. Counting occurrences keeps that change visible. Only coupled
            files appear; a prose-only file has zero by definition.
    """

    coupled: List[str] = field(default_factory=list)
    prose_only: List[str] = field(default_factory=list)
    occurrences_by_file: Dict[str, int] = field(default_factory=dict)

    @property
    def total_occurrences(self) -> int:
        """Sum of :attr:`occurrences_by_file` -- the total identifier-level reference count."""
        return sum(self.occurrences_by_file.values())


def find_enrichment_footprint(
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> EnrichmentFootprint:
    """
    Classify every production file's enrichment references as real
    identifier-level coupling or prose-only mentions. Skips generated files.

    NOT a pass/fail predicate. It is tracked so that a flat count at a step
    boundary registers as a finding rather than a silent non-event.
    """
    footprint = EnrichmentFootprint()
    for py_file in iter_source_files(toolguard_dir):
        text = py_file.read_text(encoding="utf-8")
        code_ref_count = 0
        has_prose_ref = False
        tokens = tokenize.generate_tokens(io.StringIO(text).readline)
        for tok in tokens:
            if tok.type == tokenize.NAME and tok.string in _ENRICHMENT_SPELLINGS:
                code_ref_count += 1
            elif tok.type in (tokenize.STRING, tokenize.COMMENT) and any(
                spelling in tok.string for spelling in _ENRICHMENT_SPELLINGS
            ):
                has_prose_ref = True
        rel = relative_module_path(py_file, toolguard_dir)
        if code_ref_count > 0:
            footprint.coupled.append(rel)
            footprint.occurrences_by_file[rel] = code_ref_count
        elif has_prose_ref:
            footprint.prose_only.append(rel)
    return footprint


# =============================================================================
# --predicates: assembly
# =============================================================================


def compute_predicates(
    toolguard_dir: Path = TOOLGUARD_DIR,
    test_dir: Path = REPO_ROOT / "test",
    tools_dir: Path = REPO_ROOT / "tools",
    entry_point_modules: Optional[FrozenSet[str]] = None,
) -> Dict[str, object]:
    """
    Compute every R-predicate's components plus the enrichment footprint.

    Args:
        toolguard_dir: Package to analyse.
        test_dir, tools_dir: Extra caller-scan areas for
            :func:`find_iter_shims`, so R1's shim callers are counted across
            the whole repo. Defaulted to this repo's real directories, since
            this is only exercised against the real tree.
        entry_point_modules: R5's entry points. ``None`` parses the real
            ``pyproject.toml``.

    ``.pyscn.toml`` is read only for R6's layer map here. R5 does not consult it
    at all, which is what keeps a layer relabelling from moving R5's verdict.
    """
    graph = build_import_graph(toolguard_dir)
    if entry_point_modules is None:
        entry_point_modules = parse_entry_point_modules()

    #: An empty tree makes every "zero findings" predicate trivially true. It
    #: must read as "nothing was examined", never as a clean pass.
    examined_modules = len(iter_source_files(toolguard_dir))
    tree_examined = examined_modules > 0

    r3_sites = find_reason_parsing_sites(toolguard_dir)
    r1_types = find_verdict_types(toolguard_dir)
    r1_altitudes = classify_verdict_altitudes(toolguard_dir)
    r1_shims = find_iter_shims(
        toolguard_dir,
        extra_caller_dirs=(("test", test_dir), ("tools", tools_dir)),
    )
    r1_bare_tuples = find_bare_verdict_tuples(toolguard_dir)
    r5_non_leaves = find_non_leaf_entry_points(graph, entry_point_modules)
    r5_cycles = find_import_cycles(
        graph, out_of_scope_packages=R5_OUT_OF_SCOPE_PACKAGES
    )
    r6_arch = parse_architecture_config()
    r6_report = scan_private_reaches(toolguard_dir, arch=r6_arch)
    r2_groups = find_parallel_arrays(toolguard_dir)
    r2_index_sites = find_index_parallel_access(toolguard_dir)
    r2_drift_guards = find_drift_guards(toolguard_dir)
    footprint = find_enrichment_footprint(toolguard_dir)
    generated = list_generated_files(toolguard_dir)

    return {
        "examined_modules": examined_modules,
        "generated_files_excluded": {
            "count": len(generated),
            "files": generated,
            "reason": (
                "machine-generated (banner-detected, see is_generated_file); "
                "excluded from every style/debt predicate and from --metrics, "
                "never from --layers"
            ),
        },
        "R3": {
            "pass": len(r3_sites) == 0 and tree_examined,
            "sites": r3_sites,
            "sanctioned_exclusions": sorted(
                f"{f}::{fn}" for f, fn in R3_SANCTIONED_SITES
            ),
        },
        "R1": {
            # Three parts, and all three are needed. Gating on the shims alone
            # let this report PASS the moment the tuple-compatibility shims were
            # deleted, with the verdict types they were the cheap half of still
            # standing. A predicate that can declare victory on the easy part of
            # its own definition is worse than no predicate.
            #
            # The other two parts each close a blind spot in the first:
            # counting RUNTIME altitude only, because the plan's "exactly one
            # verdict type" flattens four legitimate altitudes into one; and
            # counting bare verdict TUPLES, because a class-definition scan
            # cannot see a verdict that was never a class.
            "pass": (
                tree_examined
                and len(r1_altitudes["runtime"]) == 1
                and len(r1_shims) == 0
                and len(r1_bare_tuples) == 0
            ),
            "verdict_types": r1_types,
            "altitudes": r1_altitudes,
            "iter_shims": r1_shims,
            "bare_verdict_tuples": r1_bare_tuples,
            "out_of_scope_excluded": {
                "modules": r1_out_of_scope_modules(toolguard_dir),
                "reason": (
                    "toolguard/parser/ is explicitly out of scope for TOO-45 "
                    "per the execution plan"
                ),
            },
        },
        "R5": {
            "pass": len(r5_non_leaves) == 0 and len(r5_cycles) == 0 and tree_examined,
            "non_leaf_entry_points": r5_non_leaves,
            "cycles": r5_cycles,
            "entry_point_modules": sorted(entry_point_modules),
            "out_of_scope_excluded": {
                "modules": r1_out_of_scope_modules(toolguard_dir),
                "reason": (
                    "toolguard/parser/ is explicitly out of scope for TOO-45 "
                    "per the execution plan (the same exclusion R1 applies); "
                    "an intra-parser import cycle is not evidence toward or "
                    "against R5's leafness/cycle predicate"
                ),
            },
        },
        "R6": {
            # `unresolvable` is reported alongside `sites` but does NOT gate
            # `pass`: an ambiguous case is not evidence of a violation.
            "pass": len(r6_report.sites) == 0 and tree_examined,
            "sites": r6_report.sites,
            "unresolvable": r6_report.unresolvable,
            "guarded_layers": list(R6_GUARDED_LAYERS),
            "guarded_modules": sorted(_r6_guarded_modules(r6_arch)),
            "checked_layers": list(R6_CHECKED_LAYERS),
            "checked_modules": sorted(_r6_checked_modules(r6_arch)),
            "out_of_scope_excluded": {
                "modules": r1_out_of_scope_modules(toolguard_dir),
                "reason": (
                    "toolguard/parser/ is explicitly out of scope for TOO-45 "
                    "per the execution plan (the same exclusion R1/R5 apply); "
                    "it is excluded from R6's guarded set explicitly, not by "
                    "accident of an incomplete module list"
                ),
            },
            "known_limitations": list(R6_KNOWN_LIMITATIONS),
        },
        "R2": {
            # `r2_groups` is reported but does NOT gate `pass` -- it is the old
            # class/field-name scan, kept only for comparison with past runs.
            # See find_parallel_arrays for why it cannot be trusted alone.
            "pass": len(r2_index_sites) == 0
            and len(r2_drift_guards) == 0
            and tree_examined,
            "index_parallel_access_sites": r2_index_sites,
            "drift_guards": r2_drift_guards,
            "parallel_array_groups": r2_groups,
            "unchecked_predicate_clauses": list(R2_UNCHECKED_CLAUSES),
        },
        "enrichment_footprint": {
            "coupled_count": len(footprint.coupled),
            "coupled_files": footprint.coupled,
            "prose_only_count": len(footprint.prose_only),
            "prose_only_files": footprint.prose_only,
            "occurrences_by_file": footprint.occurrences_by_file,
            "total_occurrences": footprint.total_occurrences,
        },
    }


def render_predicates_text(predicates: Dict[str, object]) -> str:
    """Render :func:`compute_predicates`' output as human-readable text."""
    lines = []
    gen = predicates["generated_files_excluded"]
    lines.append(
        f"=== generated files excluded ({gen['count']}) -- {gen['reason']} ==="
    )
    for f in gen["files"]:
        lines.append(f"  - {f}")
    lines.append("")
    for pid in ("R1", "R2", "R3", "R5", "R6"):
        data = predicates[pid]
        lines.append(f"=== {pid}: {'PASS' if data['pass'] else 'FAIL'} ===")
        if pid == "R3":
            for s in data["sites"]:
                lines.append(
                    f"  - {s['module']}:{s['line']} in {s['function']}(): {s['expression']}"
                )
            if data["sanctioned_exclusions"]:
                lines.append(
                    f"  (excluded as sanctioned: {', '.join(data['sanctioned_exclusions'])})"
                )
        elif pid == "R1":
            alt = data["altitudes"]
            lines.append(
                f"  RUNTIME verdict types ({len(alt['runtime'])}) -- must be exactly 1:"
            )
            for t in alt["runtime"]:
                lines.append(f"    - {t['class']} ({t['module']}:{t['line']})")
            lines.append(
                f"  UNIT verdict types, excluded ({len(alt['unit'])}) -- one "
                f"decidable unit inside a compound, not a standalone verdict:"
            )
            for t in alt["unit"]:
                nested = ", ".join(
                    f"{n['container']}.{n['field']}" for n in t["nested_in"]
                )
                lines.append(
                    f"    - {t['class']} ({t['module']}:{t['line']}) -- "
                    f"nested inside: {nested}"
                )
            lines.append(
                f"  TOOLING verdict types, excluded ({len(alt['tooling'])}) -- "
                f"the replay/analysis layer's own DTO, unified only in R6:"
            )
            for t in alt["tooling"]:
                lines.append(
                    f"    - {t['class']} ({t['module']}:{t['line']}) -- "
                    f"package '{t['package']}'"
                )
            lines.append(
                f"  LEVEL verdict types, excluded ({len(alt['level'])}) -- "
                f"a raw match at one hierarchy level, not a standalone verdict:"
            )
            for t in alt["level"]:
                lines.append(
                    f"    - {t['class']} ({t['module']}:{t['line']}) -- {t['reason']}"
                )
            lines.append(f"  __iter__ shims ({len(data['iter_shims'])}):")
            for shim in data["iter_shims"]:
                by_area = ", ".join(
                    f"{area}={count}"
                    for area, count in shim["caller_counts_by_area"].items()
                )
                lines.append(
                    f"    - {shim['class']} ({shim['module']}:{shim['line']}), "
                    f"callers: {len(shim['callers'])} ({by_area})"
                )
                for c in shim["callers"]:
                    lines.append(
                        f"        [{c['area']}] {c['module']}:{c['line']} via {c['unpack_via']}(...)"
                    )
            bare_tuples = data["bare_verdict_tuples"]
            lines.append(
                f"  bare verdict-tuple returns ({len(bare_tuples)}) -- functions "
                f"returning a (decision, reason, ...) tuple, never a class, "
                f"grouped by module:"
            )
            by_module: Dict[str, List[Dict[str, object]]] = defaultdict(list)
            for hit in bare_tuples:
                by_module[str(hit["module"])].append(hit)
            for module in sorted(by_module):
                lines.append(f"    {module}:")
                for hit in by_module[module]:
                    lines.append(
                        f"      - {hit['function']}():{hit['line']} -- {hit['basis']}"
                    )
            oos = data["out_of_scope_excluded"]
            if oos["modules"]:
                lines.append(
                    f"  (out of scope -- {oos['reason']}: {', '.join(oos['modules'])})"
                )
        elif pid == "R5":
            lines.append(
                f"  entry point modules ({len(data['entry_point_modules'])}, from "
                f"pyproject.toml [project.scripts]): {', '.join(data['entry_point_modules'])}"
            )
            for nl in data["non_leaf_entry_points"]:
                lines.append(
                    f"  - {nl['module']} ({nl['reason']}) imported by: {', '.join(nl['importers'])}"
                )
            for cyc in data["cycles"]:
                lines.append(f"  - cycle: {' <-> '.join(cyc)}")
            oos = data["out_of_scope_excluded"]
            if oos["modules"]:
                lines.append(
                    f"  (out of scope -- {oos['reason']}: {', '.join(oos['modules'])})"
                )
        elif pid == "R6":
            lines.append(
                f"  guarded layers: {', '.join(data['guarded_layers'])} "
                f"({len(data['guarded_modules'])} modules, derived from .pyscn.toml)"
            )
            lines.append(f"  checked layers: {', '.join(data['checked_layers'])}")
            for s in data["sites"]:
                via = (
                    f" -- actually defined in {s['defining_module']} ({s['layer']})"
                    if s["defining_module"] != s["target_module"]
                    else f" ({s['layer']})"
                )
                lines.append(
                    f"  - {s['importer']}:{s['line']} reaches private "
                    f"`{s['private_name']}` via {s['target_module']} "
                    f"[{s['route']}]{via}"
                )
            if data["unresolvable"]:
                lines.append(f"  CANNOT VERIFY ({len(data['unresolvable'])}):")
                for u in data["unresolvable"]:
                    lines.append(f"    - {u['importer']}:{u['line']} -- {u['reason']}")
            oos = data["out_of_scope_excluded"]
            if oos["modules"]:
                lines.append(
                    f"  (out of scope -- {oos['reason']}: {', '.join(oos['modules'])})"
                )
            lines.append("  known limitations of this detector:")
            for lim in data["known_limitations"]:
                lines.append(f"    - {lim['clause']}: {lim['reason']}")
        elif pid == "R2":
            sites = data["index_parallel_access_sites"]
            lines.append(
                f"  index-parallel access sites ({len(sites)}) -- the hazard "
                f"itself, class/field-name-agnostic (gates 'pass'):"
            )
            for h in sites:
                if h["kind"] == "index_lookup":
                    lines.append(
                        f"    - {h['module']}:{h['line']} -- "
                        f"{h['container']}[{h['index_source']}.index(...)]"
                    )
                else:
                    lines.append(
                        f"    - {h['module']}:{h['line']} -- "
                        f"zip({', '.join(h['sequences'])})"
                    )
            guards = data["drift_guards"]
            lines.append(
                f'  drift guards ({len(guards)}) -- proxy for "no '
                f'prose-defended index-alignment invariant remains" (gates '
                f"'pass'; one-directional proxy, see find_drift_guards):"
            )
            for g in guards:
                lines.append(
                    f"    - {g['module']}:{g['line']} in {g['function']}(): "
                    f"len({g['left']}) != len({g['right']})"
                )
            legacy = data["parallel_array_groups"]
            lines.append(
                f"  legacy class/suffix-name scan ({len(legacy)}, "
                f"informational only -- does NOT gate 'pass', see "
                f"find_parallel_arrays):"
            )
            for g in legacy:
                lines.append(
                    f"    - {g['module']}:{g['class']}: {g['base_field']} / {g['entries_field']}"
                )
            lines.append("  predicate clauses this module cannot mechanically check:")
            for c in data["unchecked_predicate_clauses"]:
                lines.append(f'    - "{c["clause"]}" -- {c["reason"]}')
        lines.append("")
    ef = predicates["enrichment_footprint"]
    lines.append(
        f"=== enrichment footprint (tracked, not a predicate): "
        f"{ef['coupled_count']} coupled (real code), "
        f"{ef['prose_only_count']} prose-only, "
        f"{ef['total_occurrences']} total identifier-level occurrences ==="
    )
    for f in ef["coupled_files"]:
        lines.append(f"  [coupled] {f}: {ef['occurrences_by_file'][f]} occurrence(s)")
    for f in ef["prose_only_files"]:
        lines.append(f"  [prose]   {f}")
    return "\n".join(lines)


# =============================================================================
# --metrics
# =============================================================================

ZONE_PREFIXES = (
    ("tools", "tools"),
    ("parser", "parser"),
    ("scripts", "scripts"),
    ("testing", "testing"),
)


def zone_of(rel_module: str) -> str:
    """Return the zone name for a toolguard-relative dotted module path."""
    seg = first_segment(rel_module)
    for prefix, zone in ZONE_PREFIXES:
        if seg == prefix:
            return zone
    return "core"


def zone_of_repo_path(repo_relative_path: str) -> str:
    """
    Return the zone name for a repo-relative ``toolguard/...`` path, e.g.
    ``"toolguard/tools/sorters.py"`` -> ``"tools"`` -- git's path spelling
    adapted to :func:`zone_of`'s dotted-module one.
    """
    without_prefix = repo_relative_path[len("toolguard/") :]
    dotted = without_prefix.removesuffix(".py").replace("/", ".")
    return zone_of(dotted)


def _run_git(args: Sequence[str], repo_root: Path = REPO_ROOT) -> str:
    """
    Run a read-only git command against *repo_root* and return its stdout.
    *repo_root* is overridable so tests can point the ``--metrics``/``--guard``
    machinery at a small synthetic repo instead of this project's own history.
    """
    result = subprocess.run(
        ["git", *args], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout


@dataclass(frozen=True)
class LogicalChange:
    """One logical change: a ticket-tagged group of commits, or a lone untagged commit."""

    key: str  # "TOO-45" or "commit:<sha>" for an untagged commit
    files: Tuple[
        str, ...
    ]  # repo-relative paths touched, across every commit in the group


_TICKET_TOKEN_RE = re.compile(r"TOO-\d+")


def _ticket_token(message: str) -> Optional[str]:
    """Return the first ``TOO-\\d+`` token in *message*, or ``None``."""
    match = _TICKET_TOKEN_RE.search(message)
    return match.group(0) if match else None


def collect_logical_changes(
    max_commits: Optional[int] = None, repo_root: Path = REPO_ROOT
) -> List[LogicalChange]:
    """
    Group *repo_root*'s commit history into logical changes by the ``TOO-nn``
    ticket token in each commit's FULL message (subject + body); an untagged
    commit is its own singleton group. Grouping by ticket rather than by commit
    is what defeats commit-splitting as a gaming vector -- otherwise an
    iteration could hide co-change across several small commits.

    Two subprocess calls per commit rather than one combined
    ``--name-only --pretty=format:``: in the combined form git does not
    delimit the message body from the file list, and both are newline-separated
    with no marker between them. On a history of dozens of commits the extra
    calls are cheap.
    """
    shas = _run_git(["log", "--format=%H"], repo_root=repo_root).splitlines()
    if max_commits:
        shas = shas[:max_commits]

    groups: Dict[str, List[str]] = defaultdict(list)
    order: List[str] = []
    for sha in shas:
        message = _run_git(["log", "-1", "--format=%B", sha], repo_root=repo_root)
        files = [
            f
            for f in _run_git(
                ["diff-tree", "--no-commit-id", "--name-only", "-r", sha],
                repo_root=repo_root,
            ).splitlines()
            if f
        ]
        token = _ticket_token(message)
        key = token if token else f"commit:{sha}"
        if key not in groups:
            order.append(key)
        groups[key].extend(files)

    return [
        LogicalChange(key=key, files=tuple(dict.fromkeys(groups[key]))) for key in order
    ]


def production_files(
    files: Iterable[str], excluded: FrozenSet[str] = frozenset()
) -> List[str]:
    """
    Filter *files* (repo-relative paths) down to production ``toolguard/*.py``
    files, dropping any path in *excluded* -- ``--metrics`` passes
    :func:`generated_repo_paths` so generated files never reach the
    co-change/zone figures.
    """
    return [
        f
        for f in files
        if f.startswith("toolguard/") and f.endswith(".py") and f not in excluded
    ]


def _percentile(values: Sequence[int], pct: float) -> float:
    """Nearest-rank percentile (no interpolation) over sorted *values*."""
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, int(round(pct / 100 * (len(ordered) - 1)))))
    return float(ordered[idx])


#: How many times the rarer file of a pair must have been touched before the
#: pair can be reported as 100%-coupled. Two files landing in one commit
#: trivially reads as 100% coupling and carries no signal at this sample size;
#: the floor keeps the list to repeated coupling rather than one big commit's
#: incidental co-touch.
MIN_COUPLING_OBSERVATIONS = 3


def compute_metrics(
    max_commits: Optional[int] = None,
    min_coupling_observations: int = MIN_COUPLING_OBSERVATIONS,
    repo_root: Path = REPO_ROOT,
    toolguard_dir: Path = TOOLGUARD_DIR,
) -> Dict[str, object]:
    """
    Compute every history-based metric described in the module docstring.

    Generated files are excluded from every figure: a file nobody hand-edits
    should not count toward "how coupled is this codebase". *repo_root* and
    *toolguard_dir* are overridable so a test can point this at a synthetic repo.

    The returned ``fan_in_caveat`` is not decoration -- the fan-in figure and the
    co-change figures disagree on this codebase, and reading fan-in alone gets
    the diagnosis backwards.
    """
    changes = collect_logical_changes(max_commits=max_commits, repo_root=repo_root)
    excluded = frozenset(generated_repo_paths(toolguard_dir, repo_root))
    prod_changes = [
        (c.key, production_files(c.files, excluded))
        for c in changes
        if production_files(c.files, excluded)
    ]

    co_change: Counter = Counter()
    partners: Dict[str, Set[str]] = defaultdict(set)
    file_touch_count: Counter = Counter()
    for _key, files in prod_changes:
        for f in files:
            file_touch_count[f] += 1
        for i, a in enumerate(files):
            for b in files[i + 1 :]:
                pair = tuple(sorted((a, b)))
                co_change[pair] += 1
                partners[a].add(b)
                partners[b].add(a)

    max_partner_file = max(partners, key=lambda f: len(partners[f]), default=None)
    coupled_100pct = []
    for (a, b), count in co_change.items():
        rarer = min(file_touch_count[a], file_touch_count[b])
        if rarer >= min_coupling_observations and count == rarer:
            coupled_100pct.append(
                {"pair": [a, b], "co_changes": count, "rarer_total": rarer}
            )
    coupled_100pct.sort(key=lambda d: -d["co_changes"])

    confined = 0
    for _key, files in prod_changes:
        zones = {zone_of_repo_path(f) for f in files}
        if len(zones) == 1:
            confined += 1
    pct_confined = 100.0 * confined / len(prod_changes) if prod_changes else 0.0

    files_per_change = [len(files) for _key, files in prod_changes]

    scripts_hubs = [
        {"file": f, "partners": len(partners[f])}
        for f in partners
        if f.startswith("toolguard/scripts/")
    ]
    scripts_hubs.sort(key=lambda d: -d["partners"])

    graph = build_import_graph(toolguard_dir)
    fan_in_counts = fan_in(graph)
    max_fan_in_module = fan_in_counts.most_common(1)[0] if fan_in_counts else None
    cycles = find_import_cycles(graph)
    chain = longest_dependency_chain(graph)

    return {
        "generated_files_excluded": sorted(excluded),
        "logical_changes": len(changes),
        "production_logical_changes": len(prod_changes),
        "max_co_change_partners": (
            {"file": max_partner_file, "count": len(partners[max_partner_file])}
            if max_partner_file
            else None
        ),
        "coupled_100pct_pairs": coupled_100pct,
        "pct_confined_to_one_zone": round(pct_confined, 1),
        "p90_production_files_per_change": _percentile(files_per_change, 90),
        "scripts_co_change_hubs": scripts_hubs,
        "max_module_fan_in": (
            {"module": max_fan_in_module[0], "fan_in": max_fan_in_module[1]}
            if max_fan_in_module
            else None
        ),
        "import_cycle_count": len(cycles),
        "import_cycles": cycles,
        "longest_dependency_chain": chain,
        "fan_in_caveat": (
            "Fan-in is measured but KNOWN MISLEADING on this codebase: permissions/compound/"
            "resolve show fan-in 2 (looking like leaves) while co-change shows them as the "
            "most entangled files in the repo (compound.py has never changed without both "
            "config.py and permissions.py). The import graph cannot see coupling routed "
            "through config -- do not read fan-in alone, and do not read it as evidence R6 "
            "succeeded. See coupled_100pct_pairs above for what fan-in misses."
        ),
    }


def render_metrics_text(metrics: Dict[str, object]) -> str:
    """Render :func:`compute_metrics`' output as human-readable text."""
    lines = ["=== --metrics ==="]
    gen = metrics["generated_files_excluded"]
    if gen:
        lines.append(f"generated files excluded ({len(gen)}): {', '.join(gen)}")
    lines.append(
        f"logical changes: {metrics['logical_changes']} total, {metrics['production_logical_changes']} touching production toolguard/*.py"
    )
    mc = metrics["max_co_change_partners"]
    lines.append(
        f"max co-change partners: {mc['file']} ({mc['count']} partners)"
        if mc
        else "max co-change partners: n/a"
    )
    all_pairs = metrics["coupled_100pct_pairs"]
    shown_pairs = all_pairs[:30]
    lines.append(
        f"100%-coupled pairs ({len(all_pairs)}, showing top {len(shown_pairs)} by co-change count; "
        f"--json for the full list):"
    )
    for p in shown_pairs:
        lines.append(
            f"  - {p['pair'][0]} <-> {p['pair'][1]} ({p['co_changes']}/{p['rarer_total']})"
        )
    lines.append(
        f"% logical changes confined to one zone: {metrics['pct_confined_to_one_zone']}"
    )
    lines.append(
        f"p90 production files per logical change: {metrics['p90_production_files_per_change']}"
    )
    lines.append(f"scripts co-change hubs ({len(metrics['scripts_co_change_hubs'])}):")
    for h in metrics["scripts_co_change_hubs"]:
        lines.append(f"  - {h['file']}: {h['partners']} partners")
    lines.append("")
    mf = metrics["max_module_fan_in"]
    lines.append(
        f"max module fan-in: {mf['module']} ({mf['fan_in']})"
        if mf
        else "max module fan-in: n/a"
    )
    lines.append(f"import cycle count: {metrics['import_cycle_count']}")
    for cyc in metrics["import_cycles"]:
        lines.append(f"  - cycle: {' <-> '.join(cyc)}")
    lines.append(
        f"longest dependency chain ({len(metrics['longest_dependency_chain'])} hops): "
        f"{' -> '.join(metrics['longest_dependency_chain'])}"
    )
    lines.append("")
    lines.append("CAVEAT: " + metrics["fan_in_caveat"])
    return "\n".join(lines)


# =============================================================================
# --guard
# =============================================================================

GUARD_FORBIDDEN_PATH_PARTS = ("logs",)
GUARD_FORBIDDEN_NAMES = {".env", ".claude.env"}
GUARD_FORBIDDEN_SUBSTRINGS = (
    ".claude/toolguard_hook.toml",
    ".claude/settings.json",
    ".claude/settings.local.json",
)


def _changed_paths_since(ref: str, repo_root: Path = REPO_ROOT) -> List[str]:
    """
    Return every repo-relative path touched relative to *ref*, including
    uncommitted and untracked changes -- the guard must catch in-progress
    iteration work, not just committed history.
    """
    tracked = _run_git(["diff", "--name-only", ref], repo_root=repo_root).splitlines()
    untracked = _run_git(
        ["ls-files", "--others", "--exclude-standard"], repo_root=repo_root
    ).splitlines()
    return sorted(set(tracked) | set(untracked))


def _is_forbidden_path(rel_path: str) -> bool:
    """Return True when *rel_path* (repo-relative) is in a guarded location."""
    parts = Path(rel_path).parts
    if parts and parts[0] in GUARD_FORBIDDEN_PATH_PARTS:
        return True
    if Path(rel_path).name in GUARD_FORBIDDEN_NAMES:
        return True
    if any(sub in rel_path for sub in GUARD_FORBIDDEN_SUBSTRINGS):
        return True
    return False


def _count_test_methods(source: str) -> int:
    """Count ``test_*`` functions/methods (unittest style) in *source* via AST."""
    tree = ast.parse(source)
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _test_files_at_ref(ref: str, repo_root: Path = REPO_ROOT) -> Dict[str, int]:
    """
    Return ``{repo-relative path: test-method count}`` for every ``test/**/*.py``
    file as it existed at *ref*, read via ``git show`` (read-only; no checkout).
    """
    listing = _run_git(
        ["ls-tree", "-r", "--name-only", ref, "--", "test"], repo_root=repo_root
    ).splitlines()
    counts: Dict[str, int] = {}
    for path in listing:
        if not path.endswith(".py"):
            continue
        source = _run_git(["show", f"{ref}:{path}"], repo_root=repo_root)
        counts[path] = _count_test_methods(source)
    return counts


def _test_files_now(repo_root: Path = REPO_ROOT) -> Dict[str, int]:
    """Return ``{repo-relative path: test-method count}`` for the current working tree."""
    counts: Dict[str, int] = {}
    test_dir = repo_root / "test"
    if not test_dir.is_dir():
        return counts
    for py_file in iter_python_files(test_dir):
        rel = str(py_file.relative_to(repo_root))
        counts[rel] = _count_test_methods(py_file.read_text(encoding="utf-8"))
    return counts


def _project_dependencies(pyproject_text: str) -> List[str]:
    """Return the ``[project].dependencies`` list from *pyproject_text*."""
    data = tomllib.loads(pyproject_text)
    return list(data.get("project", {}).get("dependencies", []))


# =============================================================================
# --guard: canary check -- are the loop's own guard rules actually loaded?
# =============================================================================
#
# WHY THIS EXISTS. The loop's safety net rests on two permission files, neither
# of them version-controlled in this repo: `.claude/toolguard_hook.toml` (which
# lives in a separate dotfiles repo, reached through a symlinked `.claude/`) and
# `~/.toolguard/rules/git.rules.toml` (outside any repository at all). If either
# is reverted or overwritten, the rules simply vanish -- and this project sets
# no_match_fallback = "allow_with_no_warnings", so a MISSING deny rule raises
# nothing. It silently becomes a permission.
#
# Every other --guard check asks "did the diff do something forbidden". This one
# asks the logically prior question: are the forbidding rules still loaded, right
# now, in the live hook. The only honest way to answer is to ask the hook -- so
# this evaluates a fixed canary set through the real `toolguard --eval` binary
# (read-only) rather than reading the rule files and hoping they parse as
# expected.
#
# The allow cases carry as much weight as the deny cases. A set that only probed
# for denies would pass happily while the rules over-reached and started denying
# ordinary work, because a false deny reads as "deny" here too.

#: File-path tools use "file_path" in tool_input; everything else uses "command".
#: Deliberately NOT imported from toolguard.tool_spec: this canary exists to
#: detect drift between the installed hook and this repo, and a check that
#: derives the fact it verifies from the thing it verifies can only agree with
#: itself.
_CANARY_FILE_TOOLS = frozenset({"Read", "Write", "Edit"})


@dataclass(frozen=True)
class CanaryCase:
    """One fixed (tool, target) probe and the verdict it must currently produce."""

    tool: str
    #: May contain "{repo}", substituted with the repo root at evaluation time.
    target_template: str
    expect: str  # "allow" | "deny" | "ask"


#: MAINTENANCE, and read this before changing it. A mismatch reported against
#: these cases means one of two things and this tool cannot tell you which:
#: either the guard rules were genuinely lost -- the failure the check exists to
#: catch -- or they were changed deliberately and this tuple is now stale. Look
#: at the rules files and at these expectations and decide. Updating an
#: expectation to match whatever the hook now returns defeats the whole check.
GUARD_CANARIES: Tuple[CanaryCase, ...] = (
    # Bash: TOO-45's git-relaxation fences (~/.toolguard/rules/git.rules.toml).
    CanaryCase("Bash", "git clean -fdx", "deny"),
    CanaryCase("Bash", "git stash", "deny"),
    CanaryCase("Bash", "git commit --amend", "deny"),
    CanaryCase("Bash", "git rm -r toolguard/tools", "deny"),
    CanaryCase("Bash", "git bisect start", "deny"),
    CanaryCase("Bash", "git commit -m x", "allow"),
    CanaryCase("Bash", "git stash list", "allow"),
    # File tools: .claude/toolguard_hook.toml's <TEMPORARY> deny fence.
    CanaryCase("Write", "{repo}/logs/probe.md", "deny"),
    CanaryCase("Edit", "{repo}/.claude/toolguard_hook.toml", "deny"),
    CanaryCase("Write", str(Path.home() / ".claude" / "settings.json"), "deny"),
    CanaryCase("Write", "{repo}/toolguard/compound.py", "allow"),
    CanaryCase("Read", "{repo}/logs/probe.md", "allow"),
)


def resolve_toolguard_binary() -> Optional[str]:
    """
    Resolve the toolguard hook binary for canary evaluation: ``~/.local/bin/
    toolguard`` (the documented ``uv tool install`` location) first, then PATH.

    ``None`` when neither is found. Callers must treat that as SKIP, not FAIL --
    a missing binary is an environment problem, not evidence of a lost rule.
    """
    local_bin = Path.home() / ".local" / "bin" / "toolguard"
    if local_bin.is_file():
        return str(local_bin)
    return shutil.which("toolguard")


def _run_canary_case(
    binary: str, case: CanaryCase, repo_root: Path, timeout: float = 15.0
) -> Tuple[Optional[str], Optional[str]]:
    """
    Evaluate *case* through *binary* in ``--eval`` (read-only) mode.

    Returns ``(actual_verdict, error)``, exactly one of which is ``None``.
    *error* names what went wrong -- non-zero exit, timeout, unparseable output
    -- so a failure is diagnosable rather than a bare "None != deny".
    """
    target = case.target_template.format(repo=repo_root)
    tool_input = (
        {"file_path": target}
        if case.tool in _CANARY_FILE_TOOLS
        else {"command": target}
    )
    event = {
        "session_id": "architecture-fitness-guard-canary",
        "hook_event_name": "PreToolUse",
        "tool_name": case.tool,
        "tool_input": tool_input,
        "cwd": str(repo_root),
    }
    try:
        result = subprocess.run(
            [binary, "--eval"],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, "timed out"
    except OSError as e:
        return None, f"failed to run binary: {e}"
    stream = (
        result.stdout if result.returncode == 0 else (result.stdout or result.stderr)
    )
    try:
        payload = json.loads(stream)
        verdict = payload["hookSpecificOutput"]["permissionDecision"]
    except (
        json.JSONDecodeError,
        KeyError,
        TypeError,
    ):
        return None, f"unparseable output (exit {result.returncode}): {stream[:200]!r}"
    return verdict, None


def run_guard_canaries(
    repo_root: Path = REPO_ROOT, binary: Optional[str] = None
) -> Dict[str, object]:
    """
    Evaluate every :data:`GUARD_CANARIES` case through the live toolguard hook
    and compare against its expected verdict.

    Args:
        repo_root: Repo root substituted into each case's ``{repo}`` template.
        binary: Path to the toolguard binary to invoke. Defaults to
            :func:`resolve_toolguard_binary`'s result; overridable so tests can
            point this at a stub binary instead of the real installed one.

    Returns:
        A dict with ``skipped``/``skip_reason`` (when no binary could be
        resolved -- SKIP, not FAIL), ``mismatches`` (human-readable strings,
        one per failing case, naming target/expected/actual), and ``results``
        (every case's raw outcome, for ``--json`` consumers).
    """
    resolved_binary = binary if binary is not None else resolve_toolguard_binary()
    if resolved_binary is None:
        return {
            "skipped": True,
            "skip_reason": (
                "canary check SKIPPED: toolguard binary not found "
                "(tried ~/.local/bin/toolguard and PATH)"
            ),
            "mismatches": [],
            "results": [],
        }
    if not GUARD_CANARIES:
        # An empty case set is a configuration error (a rename/relocation that
        # left nothing to check), never a clean pass -- report it as a
        # mismatch, not a skip, so it fails the guard rather than warning.
        return {
            "skipped": False,
            "skip_reason": None,
            "mismatches": ["canary case set is empty: zero cases were evaluated"],
            "results": [],
        }

    results: List[Dict[str, object]] = []
    mismatches: List[str] = []
    for case in GUARD_CANARIES:
        actual, error = _run_canary_case(resolved_binary, case, repo_root)
        target = case.target_template.format(repo=repo_root)
        results.append(
            {
                "tool": case.tool,
                "target": target,
                "expected": case.expect,
                "actual": actual,
                "error": error,
            }
        )
        if error is not None:
            mismatches.append(f"canary error: {case.tool} {target!r}: {error}")
        elif actual != case.expect:
            mismatches.append(
                f"canary mismatch: {case.tool} {target!r} expected "
                f"{case.expect!r}, got {actual!r}"
            )
    return {
        "skipped": False,
        "skip_reason": None,
        "mismatches": mismatches,
        "results": results,
    }


@dataclass
class GuardReport:
    """Result of :func:`run_guard`."""

    failures: List[str] = field(default_factory=list)
    #: Notices that must surface without failing the guard -- a skipped canary
    #: check is not evidence of a lost rule.
    warnings: List[str] = field(default_factory=list)
    #: Every canary case's raw outcome, when the check ran at all.
    canary_results: List[Dict[str, object]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when nothing failed."""
        return not self.failures


def _apply_canary_results(
    report: GuardReport, repo_root: Path, binary: Optional[str]
) -> None:
    """
    Run :func:`run_guard_canaries` and fold its outcome into *report* in place:
    a skip becomes a warning, a mismatch becomes a failure, and every raw result
    is kept for ``--json``.
    """
    canary = run_guard_canaries(repo_root=repo_root, binary=binary)
    if canary["skipped"]:
        report.warnings.append(canary["skip_reason"])
    else:
        report.failures.extend(canary["mismatches"])
    report.canary_results = canary["results"]


def run_guard(
    since: str = "HEAD",
    run_lint: bool = True,
    repo_root: Path = REPO_ROOT,
    only_canaries: bool = False,
    run_canaries: bool = True,
    canary_binary: Optional[str] = None,
) -> GuardReport:
    """
    Run every deterministic check described in the module docstring's
    ``--guard`` section and return a :class:`GuardReport`.

    Args:
        since: Git ref to compare the current state (including uncommitted
            changes) against. Defaults to ``HEAD``.
        run_lint: When False, skip the ``ruff``/``check_doc_links.py``
            subprocess checks -- they depend on the ambient lint state and are
            meaningless against a synthetic fixture repo.
        repo_root: Repository root to guard.
        only_canaries: Run ONLY the canary check (CLI:
            ``--guard-canaries-only``).
        run_canaries: When False, skip the canary check, so the other checks can
            be tested without a real installed binary or this machine's real
            permission config.
        canary_binary: Toolguard binary for the canary check. Defaults to
            :func:`resolve_toolguard_binary`; overridable to point at a stub.
    """
    report = GuardReport()

    if only_canaries:
        if run_canaries:
            _apply_canary_results(report, repo_root=repo_root, binary=canary_binary)
        return report

    changed = _changed_paths_since(since, repo_root=repo_root)
    for rel_path in changed:
        abs_path = (repo_root / rel_path).resolve()
        try:
            abs_path.relative_to(repo_root.resolve())
        except ValueError:
            report.failures.append(f"file touched outside the repository: {rel_path}")
            continue
        if _is_forbidden_path(rel_path):
            report.failures.append(f"file touched in a guarded location: {rel_path}")

    ref_tests = _test_files_at_ref(since, repo_root=repo_root)
    now_tests = _test_files_now(repo_root=repo_root)
    deleted = sorted(set(ref_tests) - set(now_tests))
    for f in deleted:
        report.failures.append(f"test file deleted: {f}")
    ref_total = sum(ref_tests.values())
    now_total = sum(now_tests.values())
    if now_total < ref_total:
        report.failures.append(
            f"test count decreased: {ref_total} ({since}) -> {now_total} (current)"
        )

    try:
        ref_pyproject = _run_git(
            ["show", f"{since}:pyproject.toml"], repo_root=repo_root
        )
        ref_deps = set(_project_dependencies(ref_pyproject))
    except subprocess.CalledProcessError:
        ref_deps = set()
    now_deps = set(
        _project_dependencies(
            (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        )
    )
    new_deps = now_deps - ref_deps
    if new_deps:
        report.failures.append(
            f"new pyproject.toml dependency: {', '.join(sorted(new_deps))}"
        )

    if run_lint:
        checks = [
            (["uv", "run", "ruff", "check", "."], "ruff check"),
            (["uv", "run", "ruff", "format", "--check", "."], "ruff format --check"),
            (
                ["uv", "run", "python", "tools/check_doc_links.py"],
                "tools/check_doc_links.py",
            ),
        ]
        for cmd, label in checks:
            result = subprocess.run(cmd, cwd=repo_root, capture_output=True, text=True)
            if result.returncode != 0:
                report.failures.append(f"{label} failed (exit {result.returncode})")

    if run_canaries:
        _apply_canary_results(report, repo_root=repo_root, binary=canary_binary)

    return report


def render_guard_text(report: GuardReport) -> str:
    """Render :func:`run_guard`'s output as human-readable text."""
    if report.ok:
        lines = ["=== --guard: PASS === (no violations)"]
    else:
        lines = [f"=== --guard: FAIL ({len(report.failures)} violation(s)) ==="]
        for f in report.failures:
            lines.append(f"  - {f}")
    if report.canary_results:
        lines.append(
            f"canaries: {len(report.canary_results)} evaluated against the live hook"
        )
    if report.warnings:
        lines.append(f"WARNINGS ({len(report.warnings)}):")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)


# =============================================================================
# --mocks: patches aimed at a binding nothing reads
# =============================================================================

# `patch("mod.name")` rebinds an attribute on `mod`. A consumer that did
# `from mod import name` copied the reference at import time, so that name never
# consults `mod` again: the patch is inert for it and the effective target is
# `consumer.name`. The same patch is exactly right for a consumer that does
# `import mod` and calls `mod.name()` -- telling those apart is the whole job.

#: Packages whose by-value imports count as evidence. A test's own by-value
#: import is not evidence -- but a test's *read* still suppresses, since every
#: module in *roots* is scanned for readers.
INERT_PATCH_SUBJECT_PACKAGES = ("toolguard", "tools")

#: Whether a finding fails the run. False while known findings are unrepaired.
INERT_PATCH_CHECK_IS_FATAL = False

UNSEEN_NON_LITERAL_TARGET = "patch target is not a literal string"
UNSEEN_PATCH_HELPER = (
    "patch.object/.dict/.multiple -- this scan resolves only patch()'s literal target"
)
UNSEEN_FOREIGN_TARGET = "target is not a repo module attribute (stdlib, third party)"
UNSEEN_OBJECT_ATTRIBUTE = (
    "target names more than one attribute below a repo module "
    "(class member, or a module imported into it)"
)

PATCH_HELPER_ATTRS = frozenset({"object", "dict", "multiple"})


@dataclass(frozen=True)
class RepoModule:
    """A module found under one of the scanned package roots."""

    dotted: str
    path: Path
    is_package: bool


@dataclass(frozen=True)
class ValueBinding:
    """A ``from source import name [as local]`` outside any function, where *name* is not itself a module."""

    source: str
    name: str
    local: str


@dataclass(frozen=True)
class ModuleBindings:
    value_bindings: Tuple[ValueBinding, ...]
    #: ``(module, name)`` imported inside a function body, so re-read per call.
    late_bindings: FrozenSet[Tuple[str, str]]
    #: ``(module, attribute)`` read through a module alias.
    attribute_reads: FrozenSet[Tuple[str, str]]
    #: Every bare name loaded anywhere in this module.
    global_reads: FrozenSet[str]


@dataclass(frozen=True)
class PatchSite:
    """One ``patch("target")`` call in the scanned test tree."""

    file: str
    line: int
    target: str


@dataclass(frozen=True)
class InertPatch:
    """A patch site a by-value consumer makes inert."""

    site: PatchSite
    module: str
    name: str
    #: Dotted ``module.local`` of each stale reference.
    stale_bindings: Tuple[str, ...]


@dataclass
class InertPatchReport:
    inert: List[InertPatch] = field(default_factory=list)
    examined_files: int = 0
    examined_calls: int = 0
    #: Targets split into a repo module and one attribute name (existence not checked).
    resolved_targets: int = 0
    #: Construct -> how many patch calls this scan could not resolve to a target.
    unseen: Dict[str, int] = field(default_factory=dict)
    #: Why the check could not do its job; any entry means not ok.
    failures: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failures and not (INERT_PATCH_CHECK_IS_FATAL and self.inert)


def map_repo_modules(roots: Optional[Dict[str, Path]] = None) -> Dict[str, RepoModule]:
    """
    Map the dotted name of every module under *roots* to a RepoModule.

    Args:
        roots: Top-level package name -> that package's own directory. Defaults
            to this repo's ``toolguard``, ``tools`` and ``test`` trees. A
            missing directory contributes nothing.
    """
    if roots is None:
        roots = {
            "toolguard": TOOLGUARD_DIR,
            "tools": REPO_ROOT / "tools",
            "test": REPO_ROOT / "test",
        }
    found: Dict[str, RepoModule] = {}
    for package, directory in roots.items():
        if not directory.is_dir():
            continue
        for py_file in iter_python_files(directory):
            parts = list(py_file.relative_to(directory).parts)
            is_package = parts[-1] == "__init__.py"
            if is_package:
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1][: -len(".py")]
            dotted = ".".join([package] + parts)
            found[dotted] = RepoModule(dotted, py_file, is_package)
    return found


def _absolute_import_module(
    module: Optional[str], level: int, importer: RepoModule
) -> Optional[str]:
    """
    Resolve an import statement's module part to an absolute dotted name.

    *level* is ``ast.ImportFrom.level``: 0 for an absolute import, N for N
    leading dots. Returns None when the dots walk above the top-level package.
    """
    if level == 0:
        return module
    base = (
        importer.dotted if importer.is_package else importer.dotted.rpartition(".")[0]
    )
    parts = base.split(".") if base else []
    if level - 1 >= len(parts):
        return None
    parts = parts[: len(parts) - (level - 1)]
    if module:
        parts = parts + module.split(".")
    return ".".join(parts) or None


def _dotted_expr(node: ast.expr) -> Optional[str]:
    """Return the dotted name of a pure ``a.b.c`` attribute chain, or None for anything else."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return ".".join(reversed(parts))


def _split_on_module_prefix(
    dotted: str, known_modules: Dict[str, RepoModule]
) -> Optional[Tuple[str, List[str]]]:
    """
    Split *dotted* into its longest known-module proper prefix and the remaining
    attribute names, or None when no proper prefix is a known module.
    """
    parts = dotted.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        head = ".".join(parts[:cut])
        if head in known_modules:
            return head, parts[cut:]
    return None


def _function_scoped_node_ids(tree: ast.Module) -> Set[int]:
    """Return the ids of every node in a function definition subtree in *tree*."""
    inside: Set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            inside.update(id(child) for child in ast.walk(node))
    return inside


def analyse_module_bindings(
    module: RepoModule, known_modules: Dict[str, RepoModule]
) -> ModuleBindings:
    """
    Parse *module* and record how it binds and reads names from other repo modules.

    ``global_reads`` over-approximates -- it collects every bare name loaded in
    the file, locals included. That direction is deliberate: a spurious reader
    suppresses a finding rather than inventing one.
    """
    tree = ast.parse(module.path.read_text(encoding="utf-8"), filename=str(module.path))
    in_function = _function_scoped_node_ids(tree)
    aliases: Dict[str, str] = {}
    value_bindings: List[ValueBinding] = []
    late_bindings: Set[Tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                aliases[alias.asname or root] = alias.name if alias.asname else root
        elif isinstance(node, ast.ImportFrom):
            source = _absolute_import_module(node.module, node.level, module)
            if source is None:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                submodule = f"{source}.{alias.name}"
                if submodule in known_modules:
                    aliases[local] = submodule
                elif id(node) in in_function:
                    late_bindings.add((source, alias.name))
                else:
                    value_bindings.append(ValueBinding(source, alias.name, local))

    attribute_reads: Set[Tuple[str, str]] = set()
    global_reads: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            global_reads.add(node.id)
            continue
        if not isinstance(node, ast.Attribute):
            continue
        dotted = _dotted_expr(node)
        if dotted is None:
            continue
        head, _, rest = dotted.partition(".")
        if head not in aliases:
            continue
        split = _split_on_module_prefix(
            f"{aliases[head]}.{rest}" if rest else aliases[head], known_modules
        )
        if split is not None:
            attribute_reads.add((split[0], split[1][0]))
    return ModuleBindings(
        value_bindings=tuple(value_bindings),
        late_bindings=frozenset(late_bindings),
        attribute_reads=frozenset(attribute_reads),
        global_reads=frozenset(global_reads),
    )


def _patch_call_name(func: ast.expr) -> Optional[str]:
    """Return the trailing name of a called expression (``patch``, ``mock.patch`` -> ``patch``)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def collect_patch_sites(
    test_root: Path, repo_root: Path = REPO_ROOT
) -> Tuple[List[PatchSite], Counter, int]:
    """
    Find ``patch(...)`` calls under *test_root*.

    Returns the sites carrying a literal target string, a counter of constructs
    that name no resolvable target, and the number of files read.

    Matching is on the called name, so an unrelated method named ``patch`` is
    counted and ``patch`` bound under another name is not seen.
    """
    sites: List[PatchSite] = []
    unseen: Counter = Counter()
    files = list(iter_python_files(test_root)) if test_root.is_dir() else []
    for py_file in files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        label = py_file.resolve().relative_to(repo_root.resolve()).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _patch_call_name(node.func)
            if name in PATCH_HELPER_ATTRS:
                if _patch_call_name(getattr(node.func, "value", None)) == "patch":
                    unseen[UNSEEN_PATCH_HELPER] += 1
                continue
            if name != "patch":
                continue
            target = node.args[0] if node.args else None
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                sites.append(PatchSite(label, node.lineno, target.value))
            else:
                unseen[UNSEEN_NON_LITERAL_TARGET] += 1
    return sites, unseen, len(files)


def check_inert_patches(
    test_root: Path = REPO_ROOT / "test",
    roots: Optional[Dict[str, Path]] = None,
    subject_packages: Sequence[str] = INERT_PATCH_SUBJECT_PACKAGES,
    repo_root: Path = REPO_ROOT,
) -> InertPatchReport:
    """
    Report each ``patch("mod.name")`` under *test_root* that a by-value consumer
    makes inert.

    A site is inert when some module in *subject_packages* holds ``name`` as a
    by-value import from ``mod``, and no module anywhere in *roots* reads
    ``mod.name`` through a route the patch would reach.

    Args:
        test_root: Directory scanned for patch call sites.
        roots: Package name -> directory, as :func:`map_repo_modules` takes.
        subject_packages: Packages whose by-value bindings count as evidence.
        repo_root: Base for the repo-relative paths reported in each finding.
    """
    modules = map_repo_modules(roots)
    sites, unseen, examined_files = collect_patch_sites(test_root, repo_root)
    report = InertPatchReport(
        examined_files=examined_files, examined_calls=len(sites) + sum(unseen.values())
    )

    stale: Dict[Tuple[str, str], List[str]] = defaultdict(list)
    observed: Set[Tuple[str, str]] = set()
    for dotted, module in sorted(modules.items()):
        bindings = analyse_module_bindings(module, modules)
        if first_segment(dotted) in subject_packages:
            for binding in bindings.value_bindings:
                stale[(binding.source, binding.name)].append(
                    f"{dotted}.{binding.local}"
                )
        observed |= bindings.late_bindings
        observed |= bindings.attribute_reads
        observed |= {(dotted, name) for name in bindings.global_reads}

    for site in sites:
        split = _split_on_module_prefix(site.target, modules)
        if split is None:
            unseen[UNSEEN_FOREIGN_TARGET] += 1
            continue
        module_name, attributes = split
        if len(attributes) > 1:
            unseen[UNSEEN_OBJECT_ATTRIBUTE] += 1
            continue
        report.resolved_targets += 1
        name = attributes[0]
        holders = stale.get((module_name, name))
        if holders and (module_name, name) not in observed:
            report.inert.append(
                InertPatch(site, module_name, name, tuple(sorted(holders)))
            )
    report.unseen = dict(unseen)

    if not modules:
        report.failures.append("mapped zero repo modules: nothing could be resolved")
    elif examined_files == 0:
        report.failures.append(f"examined zero test files under {test_root}")
    elif report.examined_calls == 0:
        report.failures.append(
            f"found zero patch(...) calls in {examined_files} test file(s)"
        )
    elif report.resolved_targets == 0:
        report.failures.append(
            f"none of {report.examined_calls} patch-family call(s) split into a repo "
            "module and one attribute name: zero targets were actually checked"
        )
    return report


def render_inert_patch_text(report: InertPatchReport) -> str:
    """
    Render :func:`check_inert_patches`'s output. Headlines are kept distinct so
    a run that examined nothing cannot read as a clean pass.
    """
    if report.failures:
        headline = "FAIL -- the check examined nothing usable"
    elif not report.inert:
        headline = "PASS -- no inert patch found"
    elif INERT_PATCH_CHECK_IS_FATAL:
        headline = f"FAIL -- {len(report.inert)} inert patch(es)"
    else:
        headline = f"FINDINGS -- {len(report.inert)} inert patch(es), not fatal yet"
    lines = [
        f"=== --mocks: {headline} ===",
        f"examined: {report.examined_files} test file(s), {report.examined_calls} "
        f"patch-family call(s), {report.resolved_targets} target(s) split into a repo "
        "module and one attribute name (existence not checked)",
    ]
    for construct, count in sorted(report.unseen.items()):
        lines.append(f"  not checked: {count} x {construct}")
    for failure in report.failures:
        lines.append(f"  CHECK FAILURE: {failure}")
    for found in report.inert:
        lines.append(
            f'  - {found.site.file}:{found.site.line} patch("{found.site.target}")'
        )
        lines.append(
            f"      effective targets (patch each): {', '.join(found.stale_bindings)}"
        )
    return "\n".join(lines)


# =============================================================================
# --ambient: direct reads of home, cwd and the environment
# =============================================================================


#: Python feature version the pathlib classification below was read against.
#: Bump only after the revalidation :data:`AMBIENT_PIN_MESSAGE` describes.
AMBIENT_PYTHON_PIN = (3, 14)

#: ``Path`` members that answer from machine state rather than from their
#: receiver alone. ``home`` and ``cwd`` always do; ``absolute``, ``resolve`` and
#: ``expanduser`` do so for a relative or ``~``-prefixed receiver.
PATH_AMBIENT_MEMBERS = frozenset({"absolute", "cwd", "expanduser", "home", "resolve"})

#: Ambient members a module may not name without a :data:`PATH_AMBIENT_OWNERS`
#: entry for that ``(module, member)`` pair -- an entry for one member exempts
#: only that member. ``resolve``'s absence is pragmatic, not principled: it and ``absolute``
#: both read the working directory only for a relative receiver, which this scan
#: does not evaluate, so no rule tells the two apart. ``absolute`` has no site in
#: this tree to exempt, while ``resolve`` has one in most modules that handle
#: paths, so its sites are inventoried rather than failed.
PATH_AMBIENT_FATAL_MEMBERS = frozenset({"absolute", "cwd", "expanduser", "home"})

#: ``Path`` members inherited from ``PurePath``.
PATH_PURE_MEMBERS = frozenset(
    {
        "anchor",
        "as_posix",
        "as_uri",
        "drive",
        "full_match",
        "is_absolute",
        "is_relative_to",
        "is_reserved",
        "joinpath",
        "match",
        "name",
        "parent",
        "parents",
        "parser",
        "parts",
        "relative_to",
        "root",
        "stem",
        "suffix",
        "suffixes",
        "with_name",
        "with_segments",
        "with_stem",
        "with_suffix",
    }
)

#: ``Path`` members that reach the filesystem. A separate concern from ambient
#: state and not policed here.
PATH_FILESYSTEM_MEMBERS = frozenset(
    {
        "chmod",
        "copy",
        "copy_into",
        "exists",
        "from_uri",
        "glob",
        "group",
        "hardlink_to",
        "info",
        "is_block_device",
        "is_char_device",
        "is_dir",
        "is_fifo",
        "is_file",
        "is_junction",
        "is_mount",
        "is_socket",
        "is_symlink",
        "iterdir",
        "lchmod",
        "lstat",
        "mkdir",
        "move",
        "move_into",
        "open",
        "owner",
        "read_bytes",
        "read_text",
        "readlink",
        "rename",
        "replace",
        "rglob",
        "rmdir",
        "samefile",
        "stat",
        "symlink_to",
        "touch",
        "unlink",
        "walk",
        "write_bytes",
        "write_text",
    }
)

AMBIENT_PIN_MESSAGE = (
    "pathlib's ambient-reading members were classified against Python "
    f"{AMBIENT_PYTHON_PIN[0]}.{AMBIENT_PYTHON_PIN[1]}: "
    + ", ".join(sorted(PATH_AMBIENT_MEMBERS))
    + ". Enumerating dir(Path) sees a member added or removed; it cannot see an "
    "existing member start to consult the working or home directory, and only a "
    "person reading the release notes can. Read them for changes to how those "
    "five resolve, re-check the classification in tools/architecture_fitness.py, "
    "and update AMBIENT_PYTHON_PIN last."
)

AMBIENT_RULE_OS_IMPORT = "os-import"
AMBIENT_RULE_PATH_MEMBER = "path-member"

AMBIENT_UNSEEN_SELF_ATTRIBUTE = (
    "attribute read off self/cls -- this scan does not follow an object's fields"
)
AMBIENT_UNSEEN_MODULE_ALIAS = (
    "attribute read through an imported module alias (e.g. ambient.resolve)"
)

#: Module (toolguard-relative dotted) -> why it may import ``os``. Every other
#: module reaches the environment through :mod:`toolguard.ambient`, which makes
#: ``os.environ``, ``os.getcwd``, ``os.getenv`` and ``os.path.expanduser``
#: unreachable elsewhere rather than merely undetected.
OS_IMPORT_OWNERS: Dict[str, str] = {
    "ambient": "the facade: os.environ is the environment fact it reports",
    "config_write_guard": "atomic write: os.fdopen, os.fsync, os.replace",
    "file_lock": "advisory locking: os.open, os.lseek, os.close and the O_/SEEK_ flags",
    "install_provenance": "os.pathsep to split PYTHONPATH",
    "log_writer": "os.SEEK_END for the tail read",
    "testing.sandbox": "builds a child process environment and guards real writes",
    "tools.installer": "os.access and os.X_OK to test an executable",
}

#: (module, ``Path`` member) -> why that module may read the fact directly.
PATH_AMBIENT_OWNERS: Dict[Tuple[str, str], str] = {
    ("ambient", "cwd"): "the facade",
    ("ambient", "home"): "the facade",
    ("path_utils", "expanduser"): "pathlib's own expanduser, for the ~user form",
    ("config", "resolve"): "compares discovered config directories",
    (
        "install_provenance",
        "resolve",
    ): "install-location paths: __file__, git rev-parse output, a checkout root",
    ("install_update", "resolve"): "__file__",
    (
        "normalization",
        "resolve",
    ): "the home directory's two spellings, and a rule-matching path's",
    ("path_utils", "resolve"): "anchors against ambient.cwd() first",
    (
        "permission_migration",
        "resolve",
    ): "keys a lockfile on the project directory, and scopes a file search to it",
    ("session_start", "resolve"): "compares two package roots",
    ("testing.sandbox", "home"): "reads its own fake-home field off a Sandbox",
    (
        "testing.sandbox",
        "resolve",
    ): "the sandbox root, a guarded write's target, and __file__",
    ("tools.installer", "resolve"): "follows the console-script symlink to its venv",
    ("tools.transcript_harvest", "resolve"): "builds Claude Code's project key",
}


@dataclass(frozen=True)
class PathSurface:
    """``dir(Path)`` split against the stored classification."""

    ambient: Tuple[str, ...]
    pure: Tuple[str, ...]
    filesystem: Tuple[str, ...]
    #: Present on ``Path`` and in no stored bucket.
    unclassified: Tuple[str, ...]
    #: In a stored bucket and no longer present on ``Path``.
    missing: Tuple[str, ...]


@dataclass(frozen=True)
class AmbientSite:
    """One direct read of machine state in the scanned tree."""

    file: str
    line: int
    module: str
    rule: str
    #: The imported name for an ``os`` import, the member name for a ``Path`` read.
    name: str


@dataclass
class AmbientReport:
    findings: List[AmbientSite] = field(default_factory=list)
    surface: Optional[PathSurface] = None
    examined_files: int = 0
    examined_os_imports: int = 0
    examined_path_reads: int = 0
    #: Owner entries that matched no site, so nothing keeps them true.
    stale_owners: List[str] = field(default_factory=list)
    #: Construct -> how many attribute reads this scan deliberately passed over.
    unseen: Dict[str, int] = field(default_factory=dict)
    #: Why the check could not do its job; any entry means not ok.
    failures: List[str] = field(default_factory=list)

    @staticmethod
    def is_fatal(site: AmbientSite) -> bool:
        """Whether *site* fails the check rather than being inventoried."""
        return (
            site.rule == AMBIENT_RULE_OS_IMPORT
            or site.name in PATH_AMBIENT_FATAL_MEMBERS
        )

    @property
    def fatal_findings(self) -> List[AmbientSite]:
        return [site for site in self.findings if self.is_fatal(site)]

    @property
    def ok(self) -> bool:
        return not self.failures and not self.fatal_findings


def classify_path_surface() -> PathSurface:
    """
    Enumerate ``dir(Path)`` on the running interpreter and split it against the
    stored buckets, so a version that adds or removes a member cannot widen the
    classification silently.
    """
    present = {name for name in dir(Path) if not name.startswith("_")}
    stored = PATH_AMBIENT_MEMBERS | PATH_PURE_MEMBERS | PATH_FILESYSTEM_MEMBERS
    return PathSurface(
        ambient=tuple(sorted(PATH_AMBIENT_MEMBERS & present)),
        pure=tuple(sorted(PATH_PURE_MEMBERS & present)),
        filesystem=tuple(sorted(PATH_FILESYSTEM_MEMBERS & present)),
        unclassified=tuple(sorted(present - stored)),
        missing=tuple(sorted(stored - present)),
    )


def _module_alias_names(tree: ast.Module, modules: Dict[str, RepoModule]) -> Set[str]:
    """
    Local names in *tree* bound to a module rather than to a value.

    ``import a.b`` binds ``a`` and ``import a.b as x`` binds ``x``;
    ``from p import n`` binds ``n`` only where ``p.n`` is a module in *modules*,
    so a package outside the scanned roots contributes nothing.
    """
    aliases: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases.add(alias.asname or alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if f"{node.module}.{alias.name}" in modules:
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_os_import(node: ast.AST) -> Optional[str]:
    """Return the imported text where *node* imports ``os`` or a submodule of it."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            if alias.name == "os" or alias.name.startswith("os."):
                return alias.name
    elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
        if node.module == "os" or node.module.startswith("os."):
            return f"{node.module} import {', '.join(a.name for a in node.names)}"
    return None


def scan_ambient_routes(
    scan_root: Path = TOOLGUARD_DIR,
    repo_root: Path = REPO_ROOT,
    modules: Optional[Dict[str, RepoModule]] = None,
) -> Tuple[List[AmbientSite], Counter, int]:
    """
    Find every ``os`` import and every ``Path`` ambient-member read under
    *scan_root*.

    Args:
        scan_root: Package directory to walk. Module names in the result are
            relative to it.
        repo_root: Base for the repo-relative path reported on each site.
        modules: Repo module map, as :func:`map_repo_modules` returns, used to
            recognise ``from package import module`` aliases.

    Returns:
        The sites, a counter of attribute reads deliberately passed over, and
        the number of files read.
    """
    if modules is None:
        modules = map_repo_modules()
    sites: List[AmbientSite] = []
    unseen: Counter = Counter()
    files = list(iter_python_files(scan_root)) if scan_root.is_dir() else []
    for py_file in files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        label = py_file.resolve().relative_to(repo_root.resolve()).as_posix()
        module = relative_module_path(py_file, scan_root)
        aliases = _module_alias_names(tree, modules)
        for node in ast.walk(tree):
            imported = _is_os_import(node)
            if imported is not None:
                sites.append(
                    AmbientSite(
                        label, node.lineno, module, AMBIENT_RULE_OS_IMPORT, imported
                    )
                )
                continue
            if not isinstance(node, ast.Attribute):
                continue
            if node.attr not in PATH_AMBIENT_MEMBERS:
                continue
            receiver = node.value
            if isinstance(receiver, ast.Name):
                if receiver.id in ("self", "cls"):
                    unseen[AMBIENT_UNSEEN_SELF_ATTRIBUTE] += 1
                    continue
                if receiver.id in aliases:
                    unseen[AMBIENT_UNSEEN_MODULE_ALIAS] += 1
                    continue
            sites.append(
                AmbientSite(
                    label, node.lineno, module, AMBIENT_RULE_PATH_MEMBER, node.attr
                )
            )
    return sites, unseen, len(files)


def check_ambient_routes(
    scan_root: Path = TOOLGUARD_DIR,
    repo_root: Path = REPO_ROOT,
    os_owners: Optional[Dict[str, str]] = None,
    path_owners: Optional[Dict[Tuple[str, str], str]] = None,
    modules: Optional[Dict[str, RepoModule]] = None,
) -> AmbientReport:
    """
    Report every read of machine state under *scan_root* that no owner entry
    accounts for, plus the state of the pathlib classification itself.

    Args:
        scan_root: Package directory to walk.
        repo_root: Base for the repo-relative paths reported.
        os_owners: Module -> reason it may import ``os``.
        path_owners: ``(module, member)`` -> reason it may read that fact.
        modules: Repo module map, as :func:`map_repo_modules` returns.
    """
    os_owners = OS_IMPORT_OWNERS if os_owners is None else os_owners
    path_owners = PATH_AMBIENT_OWNERS if path_owners is None else path_owners

    sites, unseen, examined_files = scan_ambient_routes(scan_root, repo_root, modules)
    report = AmbientReport(
        surface=classify_path_surface(), examined_files=examined_files
    )
    report.unseen = dict(unseen)

    used_os_owners: Set[str] = set()
    used_path_owners: Set[Tuple[str, str]] = set()
    for site in sites:
        if site.rule == AMBIENT_RULE_OS_IMPORT:
            report.examined_os_imports += 1
            if site.module in os_owners:
                used_os_owners.add(site.module)
                continue
        else:
            report.examined_path_reads += 1
            if (site.module, site.name) in path_owners:
                used_path_owners.add((site.module, site.name))
                continue
        report.findings.append(site)

    report.stale_owners = sorted(
        [f"os import: {module}" for module in set(os_owners) - used_os_owners]
        + [
            f"{member} in {module}"
            for module, member in set(path_owners) - used_path_owners
        ]
    )

    if sys.version_info[:2] != AMBIENT_PYTHON_PIN:
        report.failures.append(
            f"running Python {sys.version_info[0]}.{sys.version_info[1]}. "
            + AMBIENT_PIN_MESSAGE
        )
    if report.surface.unclassified:
        report.failures.append(
            "pathlib gained "
            + ", ".join(f"`{name}`" for name in report.surface.unclassified)
            + "; classify each as ambient-reading or not in "
            "tools/architecture_fitness.py"
        )
    if report.surface.missing:
        report.failures.append(
            "the stored classification names "
            + ", ".join(f"`{name}`" for name in report.surface.missing)
            + ", which pathlib no longer has; drop them from the buckets"
        )
    if examined_files == 0:
        report.failures.append(f"examined zero python files under {scan_root}")
    elif not sites:
        report.failures.append(
            f"found no os import and no Path ambient-member read in {examined_files} "
            "file(s): nothing was actually checked"
        )
    for stale in report.stale_owners:
        report.failures.append(
            f"owner entry matched no site and nothing keeps it true: {stale}"
        )
    return report


def render_ambient_text(report: AmbientReport) -> str:
    """
    Render :func:`check_ambient_routes`'s output. Headlines are kept distinct so
    a run that examined nothing cannot read as a clean pass.
    """
    fatal = report.fatal_findings
    inventory = [site for site in report.findings if not report.is_fatal(site)]
    if report.failures:
        headline = "FAIL -- the check could not do its job"
    elif fatal:
        headline = f"FAIL -- {len(fatal)} unowned read(s) of machine state"
    elif inventory:
        headline = f"FINDINGS -- {len(inventory)} unowned resolve() site(s)"
    else:
        headline = "PASS -- every read of machine state has an owner"
    surface = report.surface
    lines = [
        f"=== --ambient: {headline} ===",
        f"examined: {report.examined_files} file(s), {report.examined_os_imports} "
        f"os import(s), {report.examined_path_reads} Path ambient-member read(s)",
        f"pathlib surface on Python {sys.version_info[0]}.{sys.version_info[1]}: "
        f"{len(surface.ambient)} ambient, {len(surface.pure)} pure, "
        f"{len(surface.filesystem)} filesystem, {len(surface.unclassified)} "
        "unclassified",
        "  not checked: whether a receiver is relative, which is what decides "
        "whether resolve()/absolute() read the working directory",
    ]
    for construct, count in sorted(report.unseen.items()):
        lines.append(f"  not checked: {count} x {construct}")
    for failure in report.failures:
        lines.append(f"  CHECK FAILURE: {failure}")
    for site in fatal:
        lines.append(f"  - {site.file}:{site.line} [{site.rule}] {site.name}")
    for site in inventory:
        lines.append(f"  - {site.file}:{site.line} [inventory] {site.name}")
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Parse arguments and dispatch to the selected mode(s). Multiple modes may
    be combined in one invocation; each prints its own section.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--layers",
        action="store_true",
        help="Validate the layer map (completeness + direction).",
    )
    parser.add_argument(
        "--predicates",
        action="store_true",
        help="Emit TOO-45 step predicate components.",
    )
    parser.add_argument(
        "--metrics",
        action="store_true",
        help="Emit history-based co-change/structure metrics.",
    )
    parser.add_argument(
        "--mocks",
        action="store_true",
        help="Report patch() targets a by-value consumer makes inert.",
    )
    parser.add_argument(
        "--ambient",
        action="store_true",
        help="Report reads of home/cwd/environment that bypass toolguard.ambient.",
    )
    parser.add_argument(
        "--guard",
        action="store_true",
        help="Run the deterministic safety-inspector checks.",
    )
    parser.add_argument(
        "--guard-canaries-only",
        action="store_true",
        help=(
            "Run ONLY the guard's canary check (are the loop's own permission "
            "rules still loaded?) -- skips the diff/test-count/dependency/lint "
            "checks."
        ),
    )
    parser.add_argument(
        "--since",
        default="HEAD",
        help="Git ref for --guard's comparison base (default: HEAD).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON output instead of text.",
    )
    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="With --guard, skip the ruff/check_doc_links.py subprocess checks.",
    )
    args = parser.parse_args(argv)

    if not any(
        [
            args.layers,
            args.predicates,
            args.metrics,
            args.mocks,
            args.ambient,
            args.guard,
            args.guard_canaries_only,
        ]
    ):
        parser.error(
            "at least one of --layers, --predicates, --metrics, --mocks, --ambient, "
            "--guard, --guard-canaries-only is required"
        )

    exit_code = 0
    payload: Dict[str, object] = {}

    if args.layers:
        report = check_layers()
        payload["layers"] = {
            "ok": report.ok,
            "unmapped": report.unmapped,
            "multiply_mapped": report.multiply_mapped,
            "violations": report.violations,
        }
        if not args.json:
            print(render_layers_text(report))
            print()
        if not report.ok:
            exit_code = 1

    if args.predicates:
        predicates = compute_predicates()
        payload["predicates"] = predicates
        if not args.json:
            print(render_predicates_text(predicates))
            print()

    if args.metrics:
        metrics = compute_metrics()
        payload["metrics"] = metrics
        if not args.json:
            print(render_metrics_text(metrics))
            print()

    if args.mocks:
        mock_report = check_inert_patches()
        payload["mocks"] = {
            "ok": mock_report.ok,
            "examined_files": mock_report.examined_files,
            "examined_calls": mock_report.examined_calls,
            "resolved_targets": mock_report.resolved_targets,
            "unseen": mock_report.unseen,
            "failures": mock_report.failures,
            "inert": [
                {
                    "file": found.site.file,
                    "line": found.site.line,
                    "target": found.site.target,
                    "stale_bindings": list(found.stale_bindings),
                }
                for found in mock_report.inert
            ],
        }
        if not args.json:
            print(render_inert_patch_text(mock_report))
            print()
        if not mock_report.ok:
            exit_code = 1

    if args.ambient:
        ambient_report = check_ambient_routes()
        surface = ambient_report.surface
        payload["ambient"] = {
            "ok": ambient_report.ok,
            "examined_files": ambient_report.examined_files,
            "examined_os_imports": ambient_report.examined_os_imports,
            "examined_path_reads": ambient_report.examined_path_reads,
            "unseen": ambient_report.unseen,
            "stale_owners": ambient_report.stale_owners,
            "failures": ambient_report.failures,
            "surface": {
                "ambient": list(surface.ambient),
                "pure": list(surface.pure),
                "filesystem": list(surface.filesystem),
                "unclassified": list(surface.unclassified),
                "missing": list(surface.missing),
            },
            "findings": [
                {
                    "file": site.file,
                    "line": site.line,
                    "module": site.module,
                    "rule": site.rule,
                    "name": site.name,
                    "fatal": ambient_report.is_fatal(site),
                }
                for site in ambient_report.findings
            ],
        }
        if not args.json:
            print(render_ambient_text(ambient_report))
            print()
        if not ambient_report.ok:
            exit_code = 1

    if args.guard or args.guard_canaries_only:
        report = run_guard(
            since=args.since,
            run_lint=not args.no_lint,
            only_canaries=args.guard_canaries_only,
        )
        payload["guard"] = {
            "ok": report.ok,
            "failures": report.failures,
            "warnings": report.warnings,
            "canary_results": report.canary_results,
        }
        if not args.json:
            print(render_guard_text(report))
            print()
        if not report.ok:
            exit_code = 1

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
