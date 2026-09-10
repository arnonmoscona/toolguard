"""
Render the hooks dependency graph in several notations and layout engines.

Same graph every time -- built by ``import_graph.py``, transitively reduced --
so the only variable is the drawing. Emits Mermaid, Graphviz DOT and PlantUML,
each with the same grouping, and lets a driver render them with whatever engines
are installed.

Grouping, in all three:
  - ``top_level``  the flat entry points (hook, session_start, subagent, api)
  - ``decision machinery``  decision_model + engine + parser
  - one box per remaining layer package

Usage:
    diagram_experiments.py --format mermaid|dot|puml [--layout <engine>]
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_graph import (
    ENTRY_POINTS,
    PACKAGE_COLOURS,
    build_graph,
    package_of,
    reachable,
    transitive_reduction,
)

#: Flat modules, grouped so they stop scattering to the edges and dragging
#: long edges across the whole drawing.
TOP_LEVEL = ("hook", "session_start", "subagent", "api")

#: Outer boxes: label -> member packages, in draw order.
CLUSTERS = {
    "top_level": TOP_LEVEL,
    "decision machinery": ("decision_model", "engine", "parser"),
}

#: Vertical order, deepest last. Used for rank pinning where the notation
#: supports it.
STACK = (
    "top_level",
    "decision machinery",
    "configuration",
    "observability",
    "install",
    "foundation",
    "integration",
)


def safe(name: str) -> str:
    """An identifier safe in all three notations."""
    return name.replace(".", "_").replace(" ", "_").replace("-", "_")


def graph_and_groups():
    """The reduced hooks graph, plus ``{group label: [members]}``."""
    graph = build_graph()
    nodes = reachable(graph, ENTRY_POINTS)
    reduced = transitive_reduction(graph, nodes)

    by_package: Dict[str, List[str]] = defaultdict(list)
    for module in sorted(nodes):
        by_package[package_of(module)].append(module)
    return reduced, nodes, by_package


#: Colours for the ``tools`` view, which has no packages to colour by. The
#: bands are structural, not decorative: they say where a module sits in the
#: package's own dependency order.
ROLE_COLOURS = {
    "entry": "#cfe2f3",  # nothing in tools/ imports it -- a skill or console script
    "middle": "#fce5cd",  # shared analysis
    "leaf": "#d9ead3",  # imports nothing in tools/ -- a primitive
    "isolated": "#eeeeee",  # neither imports nor is imported here
}


def tools_graph():
    """
    The reduced intra-``tools`` graph, with each module's structural role.

    ``tools/`` has no sub-packages, so there is nothing to group by. Roles give
    the drawing the information a package box would otherwise carry: which
    modules are entry points, which are shared, which are primitives.
    """
    graph = build_graph()
    nodes = {m for m in graph if m.startswith("tools")}
    reduced = transitive_reduction(graph, nodes)

    incoming = {m: 0 for m in nodes}
    for source in nodes:
        for target in reduced.get(source, ()):
            incoming[target] += 1

    roles: Dict[str, str] = {}
    for module in nodes:
        has_out = bool(reduced.get(module))
        has_in = incoming[module] > 0
        if has_in and has_out:
            roles[module] = "middle"
        elif has_out:
            roles[module] = "entry"
        elif has_in:
            roles[module] = "leaf"
        else:
            roles[module] = "isolated"
    return reduced, nodes, roles


def render_tools_dot(reduced, nodes, roles, engine: str) -> str:
    """
    The ``tools`` view as DOT, tuned for *engine*.

    ``dot`` gets a layered top-to-bottom drawing; the radial engines get the
    spacing and overlap settings that make them legible, and no rank direction,
    since they do not honour one.
    """
    if engine == "dot":
        header = [
            "    rankdir=TB;",
            "    newrank=true;",
            "    splines=ortho;",
            "    nodesep=0.3;",
            "    ranksep=0.7;",
        ]
    else:
        header = [
            "    overlap=prism;",
            "    ranksep=2.0;",
            "    nodesep=0.5;",
            "    root=tools_maintenance;",
            "    splines=spline;",
        ]

    lines = ["digraph tools {", *header]
    lines.append(
        '    node [shape=box, style="filled,rounded", '
        'fontname="Helvetica", fontsize=10];'
    )
    lines.append('    edge [color="#666666", arrowsize=0.6];')
    for module in sorted(nodes):
        short = module.split(".", 1)[1] if "." in module else module
        lines.append(
            f'    {safe(module)} [label="{short}", '
            f'fillcolor="{ROLE_COLOURS[roles[module]]}"];'
        )
    lines.append("")
    for source in sorted(nodes):
        for target in sorted(reduced.get(source, ())):
            lines.append(f"    {safe(source)} -> {safe(target)};")
    lines.append("}")
    return "\n".join(lines)


def colour_for(package: str) -> str:
    """Fill colour for a package, defaulting to a neutral grey."""
    return PACKAGE_COLOURS.get(package, "#eeeeee")


def render_mermaid(reduced, nodes, by_package, layout: str) -> str:
    """Mermaid flowchart. *layout* selects the renderer via a config header."""
    lines: List[str] = []
    if layout and layout != "dagre":
        lines.append("---")
        lines.append("config:")
        lines.append(f"  layout: {layout}")
        lines.append("---")
    lines.append("flowchart BT")

    emitted: Set[str] = set()
    for label, members in CLUSTERS.items():
        present = [m for m in members if m in by_package]
        if not present:
            continue
        lines.append(f'    subgraph {safe(label)}["{label}"]')
        for package in present:
            if package in TOP_LEVEL:
                # A flat module is a node, not a package: boxing it alone adds
                # a frame around one item and says nothing.
                for module in by_package[package]:
                    lines.append(f'        {safe(module)}["{module}"]')
                emitted.add(package)
                continue
            lines.append(f'        subgraph {safe(package)}_pkg["{package}/"]')
            for module in by_package[package]:
                short = module.split(".", 1)[1] if "." in module else module
                lines.append(f'            {safe(module)}["{short}"]')
            lines.append("        end")
            emitted.add(package)
        lines.append("    end")

    for package in sorted(by_package):
        if package in emitted:
            continue
        lines.append(f'    subgraph {safe(package)}_pkg["{package}/"]')
        for module in by_package[package]:
            short = module.split(".", 1)[1] if "." in module else module
            lines.append(f'        {safe(module)}["{short}"]')
        lines.append("    end")

    lines.append("")
    for source in sorted(nodes):
        for target in sorted(reduced.get(source, ())):
            lines.append(f"    {safe(source)} --> {safe(target)}")

    pins = [
        safe(name) if name in CLUSTERS else f"{safe(name)}_pkg"
        for name in STACK
        if (name in CLUSTERS and any(p in by_package for p in CLUSTERS[name]))
        or (name not in CLUSTERS and name in by_package)
    ]
    if len(pins) > 1:
        lines.append("")
        for lower, upper in zip(pins, pins[1:]):
            lines.append(f"    {lower} ~~~ {upper}")

    lines.append("")
    for package in sorted(by_package):
        lines.append(
            f"    classDef {safe(package)} fill:{colour_for(package)},"
            "stroke:#666,color:#000"
        )
        ids = ",".join(safe(m) for m in by_package[package])
        lines.append(f"    class {ids} {safe(package)}")
    return "\n".join(lines)


def render_dot(reduced, nodes, by_package) -> str:
    """
    Graphviz DOT.

    ``rankdir=BT`` matches the Mermaid orientation. ``newrank=true`` lets ranks
    be assigned across cluster boundaries, which is what stops a cluster being
    dragged away from its dependents.
    """
    # rankdir=TB and splines=ortho won the 2026-09-10 comparison against
    # Mermaid (dagre and elk), PlantUML, and the graphviz force/radial engines.
    # TB puts the entry points at the top and `foundation` at the bottom, which
    # is both reading order and the layer stack's own orientation; BT inverted
    # the stack. Orthogonal routing removes the long curved sweeps.
    lines = [
        "digraph toolguard {",
        "    rankdir=TB;",
        "    newrank=true;",
        "    compound=true;",
        # concentrate merges parallel edges: it warned about degenerate ranks
        # here and buys nothing visible, while making the drawing show fewer
        # edges than the graph has.
        "    concentrate=false;",
        "    splines=ortho;",
        "    nodesep=0.25;",
        "    ranksep=0.6;",
        '    node [shape=box, style="filled,rounded", fontname="Helvetica", fontsize=10];',
        '    edge [color="#666666", arrowsize=0.7];',
        '    graph [fontname="Helvetica", fontsize=11, style=filled, color="#cccccc", fillcolor="#fbfbf3"];',
    ]

    emitted: Set[str] = set()
    for label, members in CLUSTERS.items():
        present = [m for m in members if m in by_package]
        if not present:
            continue
        lines.append(f"    subgraph cluster_{safe(label)} {{")
        lines.append(f'        label="{label}";')
        lines.append('        fillcolor="#f4f4ea";')
        for package in present:
            if package in TOP_LEVEL:
                for module in by_package[package]:
                    lines.append(
                        f'        {safe(module)} [label="{module}", '
                        f'fillcolor="{colour_for("runtime")}"];'
                    )
                emitted.add(package)
                continue
            lines.append(f"        subgraph cluster_{safe(package)} {{")
            lines.append(f'            label="{package}/";')
            lines.append(f'            fillcolor="{colour_for(package)}";')
            for module in by_package[package]:
                short = module.split(".", 1)[1] if "." in module else module
                lines.append(
                    f'            {safe(module)} [label="{short}", '
                    f'fillcolor="{colour_for(package)}"];'
                )
            lines.append("        }")
            emitted.add(package)
        lines.append("    }")

    for package in sorted(by_package):
        if package in emitted:
            continue
        lines.append(f"    subgraph cluster_{safe(package)} {{")
        lines.append(f'        label="{package}/";')
        lines.append(f'        fillcolor="{colour_for(package)}";')
        for module in by_package[package]:
            short = module.split(".", 1)[1] if "." in module else module
            lines.append(
                f'        {safe(module)} [label="{short}", '
                f'fillcolor="{colour_for(package)}"];'
            )
        lines.append("    }")

    lines.append("")
    for source in sorted(nodes):
        for target in sorted(reduced.get(source, ())):
            lines.append(f"    {safe(source)} -> {safe(target)};")
    lines.append("}")
    return "\n".join(lines)


def render_puml(reduced, nodes, by_package) -> str:
    """PlantUML component diagram: packages as components inside folders."""
    lines = [
        "@startuml",
        "skinparam componentStyle rectangle",
        "skinparam shadowing false",
        "skinparam defaultFontName Helvetica",
        "skinparam defaultFontSize 10",
        "skinparam ArrowColor #666666",
        "left to right direction",
        "",
    ]

    emitted: Set[str] = set()
    for label, members in CLUSTERS.items():
        present = [m for m in members if m in by_package]
        if not present:
            continue
        lines.append(f'package "{label}" {{')
        for package in present:
            if package in TOP_LEVEL:
                for module in by_package[package]:
                    lines.append(f"  [{module}] as {safe(module)}")
                emitted.add(package)
                continue
            lines.append(
                f'  package "{package}/" #{colour_for(package).lstrip("#")} {{'
            )
            for module in by_package[package]:
                short = module.split(".", 1)[1] if "." in module else module
                lines.append(f"    [{short}] as {safe(module)}")
            lines.append("  }")
            emitted.add(package)
        lines.append("}")

    for package in sorted(by_package):
        if package in emitted:
            continue
        lines.append(f'package "{package}/" #{colour_for(package).lstrip("#")} {{')
        for module in by_package[package]:
            short = module.split(".", 1)[1] if "." in module else module
            lines.append(f"  [{short}] as {safe(module)}")
        lines.append("}")

    lines.append("")
    for source in sorted(nodes):
        for target in sorted(reduced.get(source, ())):
            lines.append(f"{safe(source)} --> {safe(target)}")
    lines.append("@enduml")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("mermaid", "dot", "puml"), required=True)
    parser.add_argument("--layout", default="dagre", help="mermaid layout name")
    parser.add_argument("--view", choices=("hooks", "tools"), default="hooks")
    parser.add_argument(
        "--engine",
        default="dot",
        help="with --view tools --format dot: tune the output for this engine",
    )
    args = parser.parse_args()

    if args.view == "tools":
        if args.format != "dot":
            parser.error("--view tools is only implemented for --format dot")
        reduced, nodes, roles = tools_graph()
        print(render_tools_dot(reduced, nodes, roles, args.engine))
        return 0

    reduced, nodes, by_package = graph_and_groups()
    if args.format == "mermaid":
        print(render_mermaid(reduced, nodes, by_package, args.layout))
    elif args.format == "dot":
        print(render_dot(reduced, nodes, by_package))
    else:
        print(render_puml(reduced, nodes, by_package))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
