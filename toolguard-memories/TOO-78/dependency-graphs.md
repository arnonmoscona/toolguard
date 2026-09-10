---
title: TOO-78 module dependency graphs
tags:
- task-memory
- TOO-78
permalink: toolguard/too-78/dependency-graphs
---

# Module dependency graphs

**These now live in the architecture document.** `docs/architecture-as-built.md` carries both, with the package descriptions around them: the module graph in section 6, and `toolguard/tools/`'s internal shape in section 4. Renders and sources are in `docs/diagrams/module-hooks.*` and `docs/diagrams/module-tools.*`.

Regenerate:

```bash
uv run python tools/diagram_experiments.py --format dot > docs/diagrams/module-hooks.dot
dot -Tsvg docs/diagrams/module-hooks.dot -o /tmp/sharp.svg
uv run python tools/round_svg_corners.py /tmp/sharp.svg docs/diagrams/module-hooks.svg --radius 8
rsvg-convert -f png -o docs/diagrams/module-hooks.png docs/diagrams/module-hooks.svg
```

Add `--view tools --engine dot` for the tools view. `tools/import_graph.py --view cycles` is the check worth keeping regardless of how the picture looks.

## How the notation was chosen, 2026-09-10

Eleven variants rendered and compared by eye -- `dot`, `plantuml` and `mmdc` are all installed here, so this was measured rather than guessed.

**Winner: Graphviz `dot`, `rankdir=TB`, `splines=ortho`, corners rounded by a post-pass.** Graphviz has no rounded-ortho mode, hence `tools/round_svg_corners.py`.

| notation / engine | verdict |
|---|---|
| graphviz `dot` TB + ortho | compact, clean bands, entry points on top and `foundation` at the bottom where a layer stack belongs |
| graphviz `dot` BT | same, but inverts the stack |
| PlantUML component | good local structure, sweeps long curves across the canvas and over boxes |
| Mermaid dagre | wide, large empty regions, full-height edges |
| Mermaid elk | worse -- very tall, a dead zone, a full-height bundle of long edges |
| graphviz `neato` | best of the force/radial family: reveals component structure and hubs, but no ordering and lots of dead space |
| graphviz `twopi` | untuned it overlaps boxes and is unusable; tuned (`overlap`, `ranksep`, `nodesep`, `root`) it becomes legible but still loses |
| graphviz `fdp` | clusters placed, no layer ordering, many crossings |
| graphviz `sfdp` | fails to render this graph at all |

**What the force/radial family is good for.** It does not beat `dot` on clarity, but it surfaces what `dot` buries: on the flat `tools/` view, `neato` and `twopi` both make the two disconnected sub-systems obvious at a glance. Hub-and-component structure is what they show; layer order is what they cannot.

**Why they fail on the hooks view specifically**: `foundation` modules are imported from everywhere, so a force layout pulls them apart toward their many consumers. That is exactly the case where an explicit cluster beats emergent proximity.

The one-off analysis scripts from this ticket are in `scripts/`. The durable generators were promoted to the repo's `tools/`.