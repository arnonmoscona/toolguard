"""
Module-level STATIC import graph for toolguard, as Mermaid.

Only module-level ``import``/``from`` statements are followed: no runtime
callbacks, no injected dependencies, no string-named dynamic imports. Two views:

  --view hooks   everything reachable from the entry points, by package
  --view tools   the internal structure of toolguard/tools/

Nodes are ``package.module``; ``toolguard.`` is stripped throughout.
"""

from __future__ import annotations

import argparse
import ast
from collections import defaultdict
from pathlib import Path
from typing import Dict, Set

#: Resolved from this file, matching architecture_fitness.py, so the tool works
#: from any working directory and in any checkout.
REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLGUARD = REPO_ROOT / "toolguard"

#: Entry points the "hooks going down" view starts from.
ENTRY_POINTS = ("hook", "session_start", "subagent")

#: Package -> fill colour. Ordered lowest layer first, so the legend reads
#: like the layer stack.
PACKAGE_COLOURS = {
    "integration": "#d9d2e9",
    "foundation": "#d0e0e3",
    "decision_model": "#cfe8dc",
    "install": "#d9ead3",
    "observability": "#fff2cc",
    "configuration": "#fce5cd",
    "engine": "#f4cccc",
    "parser": "#f4cccc",
    "api": "#ead1dc",
    "runtime": "#cfe2f3",
    "tools": "#e6e6e6",
    "scripts": "#e6e6e6",
    "testing": "#e6e6e6",
}

#: Top-level modules that are not in a layer package.
FLAT_MODULES = {"hook", "session_start", "subagent", "api"}

#: Packages drawn inside one outer box, for READABILITY only -- it is not a
#: layer and the layer map knows nothing about it. Grouping the decision
#: machinery keeps `decision_model` next to its main consumer instead of being
#: pulled toward `configuration`, which also depends on it and was dragging
#: arrows across the diagram.
CLUSTERS = {
    "decision machinery": ("decision_model", "engine", "parser"),
}


def module_name(path: Path) -> str:
    """``toolguard/configuration/config.py`` -> ``configuration.config``."""
    rel = path.relative_to(TOOLGUARD)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return ".".join(parts)


def inert_packages() -> Set[str]:
    """
    Packages whose ``__init__`` is docstring-only.

    ``from toolguard.foundation import ambient`` imports the package as well as
    the module, but when the package body does nothing that edge records an
    import form rather than a dependency, so it is dropped from the picture.
    """
    inert = set()
    for init in TOOLGUARD.glob("*/__init__.py"):
        body = ast.parse(init.read_text()).body
        live = [
            node
            for node in body
            if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant))
        ]
        if not live:
            inert.add(init.parent.name)
    return inert


def build_graph() -> Dict[str, Set[str]]:
    """Every module-level toolguard import, as ``{module: {imported, ...}}``."""
    graph: Dict[str, Set[str]] = defaultdict(set)
    skip = inert_packages()
    modules = {module_name(p) for p in TOOLGUARD.rglob("*.py")} - skip
    for path in sorted(TOOLGUARD.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        name = module_name(path)
        graph.setdefault(name, set())
        for node in ast.parse(path.read_text()).body:
            targets = []
            if isinstance(node, ast.Import):
                targets = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                base = node.module
                targets = [base] + [f"{base}.{a.name}" for a in node.names]
            for target in targets:
                if not target.startswith("toolguard"):
                    continue
                stripped = target[len("toolguard.") :] if target != "toolguard" else ""
                if stripped and stripped in modules and stripped != name:
                    graph[name].add(stripped)
    return graph


def reachable(graph: Dict[str, Set[str]], roots) -> Set[str]:
    """Every module reachable from *roots*, following imports downward."""
    seen: Set[str] = set()
    stack = list(roots)
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(graph.get(current, ()))
    return seen


def find_cycles(graph: Dict[str, Set[str]], nodes: Set[str]) -> list:
    """Return every simple cycle among *nodes*, as lists of module names."""
    cycles = []
    path: list = []
    on_path: Set[str] = set()
    visited: Set[str] = set()

    def walk(node: str) -> None:
        path.append(node)
        on_path.add(node)
        for target in sorted(graph.get(node, ())):
            if target not in nodes:
                continue
            if target in on_path:
                cycles.append(path[path.index(target) :] + [target])
            elif target not in visited:
                walk(target)
        on_path.discard(node)
        path.pop()
        visited.add(node)

    for node in sorted(nodes):
        if node not in visited:
            walk(node)
    return cycles


def transitive_reduction(
    graph: Dict[str, Set[str]], nodes: Set[str]
) -> Dict[str, Set[str]]:
    """
    Drop every edge implied by a longer path, so the picture shows structure
    rather than every consequence of it. Meaningful only on a DAG.
    """
    reach: Dict[str, Set[str]] = {}

    def reachable_from(node: str) -> Set[str]:
        if node in reach:
            return reach[node]
        reach[node] = set()  # guards against a cycle rather than recursing forever
        found: Set[str] = set()
        for target in graph.get(node, ()):
            if target in nodes:
                found.add(target)
                found |= reachable_from(target)
        reach[node] = found
        return found

    reduced: Dict[str, Set[str]] = {}
    for source in nodes:
        direct = {t for t in graph.get(source, ()) if t in nodes}
        implied = set()
        for target in direct:
            implied |= reachable_from(target)
        reduced[source] = direct - implied
    return reduced


def package_of(module: str) -> str:
    """The package a module belongs to; flat modules report themselves."""
    return module.split(".")[0] if "." in module else module


def node_id(module: str) -> str:
    """A mermaid-safe node id: dots and spaces are not valid in one."""
    return module.replace(".", "_").replace(" ", "_")


def render(graph: Dict[str, Set[str]], nodes: Set[str], title: str) -> str:
    """Render *nodes* and the edges among them as a Mermaid flowchart."""
    by_package: Dict[str, list] = defaultdict(list)
    for module in sorted(nodes):
        by_package[package_of(module)].append(module)

    def emit_package(package: str, indent: str) -> None:
        """One package subgraph and its modules."""
        lines.append(f'{indent}subgraph {node_id(package)}_pkg["{package}/"]')
        for module in by_package[package]:
            label = module.split(".", 1)[1] if "." in module else module
            lines.append(f'{indent}    {node_id(module)}["{label}"]')
        lines.append(f"{indent}end")

    lines = [f"%% {title}", "flowchart BT"]
    clustered = {p for members in CLUSTERS.values() for p in members}
    emitted: Set[str] = set()

    for cluster, members in CLUSTERS.items():
        present = [p for p in members if p in by_package]
        if not present:
            continue
        lines.append(f'    subgraph {node_id(cluster)}["{cluster}"]')
        for package in present:
            emit_package(package, "        ")
            emitted.add(package)
        lines.append("    end")

    for package in sorted(by_package, key=lambda p: (p in FLAT_MODULES, p)):
        if package in emitted or (package in clustered and package not in by_package):
            continue
        if package in FLAT_MODULES:
            for module in by_package[package]:
                lines.append(f'    {node_id(module)}["{module}"]')
            continue
        emit_package(package, "    ")

    lines.append("")
    for source in sorted(nodes):
        for target in sorted(graph.get(source, ())):
            if target in nodes:
                lines.append(f"    {node_id(source)} --> {node_id(target)}")

    # Rank pinning. Mermaid's auto-layout places a package wherever its edges
    # pull it, which drags `model` sideways and makes configuration's arrows to
    # foundation cross it. Invisible links (`~~~`) between the package subgraphs,
    # in layer order, constrain the ranks without drawing anything. In `BT` an
    # invisible `A ~~~ B` puts B above A, so the chain runs top-of-stack first.
    #: The clustered packages are pinned by their cluster, not individually --
    #: pinning a package inside a nested subgraph fights the cluster's own box.
    order = (
        "support",
        "tooling",
        "runtime",
        "api",
        "decision machinery",
        "configuration",
        "observability",
        "install",
        "foundation",
        "integration",
    )
    stack = []
    for name in order:
        if name in CLUSTERS:
            if any(p in by_package for p in CLUSTERS[name]):
                stack.append(node_id(name))
        elif name in by_package and name not in FLAT_MODULES:
            stack.append(f"{node_id(name)}_pkg")
    if len(stack) > 1:
        lines.append("")
        lines.append("    %% invisible links: pin the layer order, draw nothing")
        for lower, upper in zip(stack, stack[1:]):
            lines.append(f"    {lower} ~~~ {upper}")

    lines.append("")
    for package, colour in PACKAGE_COLOURS.items():
        members = by_package.get(package, [])
        if not members:
            continue
        lines.append(f"    classDef {package} fill:{colour},stroke:#666,color:#000")
        ids = ",".join(node_id(m) for m in members)
        lines.append(f"    class {ids} {package}")
    flat = [m for m in sorted(nodes) if m in FLAT_MODULES]
    if flat:
        lines.append(
            "    classDef entry fill:#cfe2f3,stroke:#1a5276,stroke-width:2px,color:#000"
        )
        lines.append(f"    class {','.join(node_id(m) for m in flat)} entry")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--view", choices=("hooks", "tools", "stats", "cycles"), default="hooks"
    )
    parser.add_argument(
        "--full", action="store_true", help="keep edges implied by a longer path"
    )
    args = parser.parse_args()

    graph = build_graph()

    if args.view == "cycles":
        for label, nodes in (
            ("whole package", set(graph)),
            ("from the hooks", reachable(graph, ENTRY_POINTS)),
            ("within tools/", {m for m in graph if m.startswith("tools")}),
        ):
            found = find_cycles(graph, nodes)
            print(f"{label}: {len(found)} cycle(s)")
            for cycle in found[:10]:
                print("   " + " -> ".join(cycle))
        return 0

    if args.view == "stats":
        for module in sorted(graph):
            print(f"{module}: {len(graph[module])}")
        return 0

    if args.view == "tools":
        nodes = {m for m in graph if m.startswith("tools")}
        shown = graph if args.full else transitive_reduction(graph, nodes)
        print(render(shown, nodes, "toolguard/tools/ -- internal static imports"))
        print()
        print("%% outward dependencies, per tools module (targets outside tools/)")
        for module in sorted(nodes):
            outward = sorted(t for t in graph[module] if not t.startswith("tools"))
            if outward:
                print(f"%%   {module}: {', '.join(outward)}")
        return 0

    nodes = reachable(graph, ENTRY_POINTS)
    shown = graph if args.full else transitive_reduction(graph, nodes)
    print(render(shown, nodes, "hooks and everything below them -- static imports"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
