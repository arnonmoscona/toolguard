---
title: 10-tool-as-a-described-thing
type: note
permalink: toolguard/too-45/proposed-tickets/10-tool-as-a-described-thing
---

# Proposed: make "a supported tool" a described thing

**Status:** deferred from TOO-45. Found by the MR-10 change canary, verified against the live code.

## Problem

A governed tool is not a modelled concept. It is a name appearing in **four independent membership sets**:

```
config_validation.py:9    KNOWN_SUPPORTED_TOOLS
constants.py:22           GOVERNED_TOOLS   = {Bash, Read, Write, Edit}
constants.py:26           FILE_TOOLS       = {Read, Write, Edit}
hook.py:54                COMMAND_TOOLS
```

plus, until the current bug batch, **two more hardcoded copies** of the file-tools list inside `tools/danger.py` wired to no constant at all. There is no tool registry, no `ToolSpec` type, and **no tool-to-payload-key map** — the path is a string literal at each read site (`tool_input.get("file_path", "")` in `hook.py` twice, once in `transcript_harvest.py`).

## What the canary showed

Both MR-10 implementers, working independently in different trees, had to touch **three path-extraction sites and four-plus membership sets**, and **both found the `danger.py` duplicates only by grepping for literal tuples** — neither found them by following code. The failure mode of missing one is **silent under-enforcement**, which is the worst kind of bug this product can have.

## The sharpest evidence that this is a real gap

TOO-45 grew `config_types.py` from 369 to 822 lines, and **every type it added describes a verdict** — `LevelMatch`, `UnitVerdict`, `RuntimeVerdict`. Not one describes a tool. The project demonstrably knows how to promote a scattered concept into a described thing with attributes, and left the tool as a bare string.

## Proposed

A `ToolSpec` in `constants.py` or `config_types.py`: name, kind (command vs file-path), the payload key its subject lives under, and whether it is governed by default. The four membership sets become derived views. Adding a tool becomes one entry.

## Size

Medium. The types are easy; finding every membership test and payload read is the work — and that search is exactly what the canary showed is currently done by grep and luck.

## Decision needed

Worth doing, or is the tool set stable enough that four lists are tolerable? Note `NotebookEdit` is a real pending case — it modifies files on disk and is currently ungovernable without `additional_supported_tools`.