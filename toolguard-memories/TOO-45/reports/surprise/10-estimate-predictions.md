---
title: Blind estimate (predictions) - item 10 ToolSpec
type: note
permalink: toolguard/too-45/reports/surprise/10-estimate-predictions
tags:
- task-memory
- TOO-45
- measurement
---

# Blind estimate (predictions) - item 10 ToolSpec

Estimated from the ticket text and the file inventory only. Files marked **[named]** are transcribed from the ticket and should be discounted when scoring.

## 1. Predicted touch set

| path | add/modify/delete | prod/test | confidence | reason |
|---|---|---|---|---|
| `toolguard/constants.py` | modify | production | high | **[named]** the registry's most likely home: it is the lowest layer everything else may import, and `GOVERNED_TOOLS`/`FILE_TOOLS` become derived views here |
| `toolguard/config_validation.py` | modify | production | high | **[named]** `KNOWN_SUPPORTED_TOOLS` becomes a derived view over the registry |
| `toolguard/hook.py` | modify | production | high | **[named]** `COMMAND_TOOLS` plus both `tool_input.get("file_path")` reads become spec lookups |
| `toolguard/tools/danger.py` | modify | production | high | **[named]** the two hardcoded file-tool tuples wired to no constant |
| `toolguard/tools/transcript_harvest.py` | modify | production | high | **[named]** the third payload-key literal |
| `toolguard/rule_entry.py` | modify | production | high | its docstring is literally "shape normalization and **tool scoping**" — a rule scoped to a tool must test membership and normalize a tool name, so it holds a fifth de facto membership set |
| `toolguard/config.py` | modify | production | medium | loads `additional_supported_tools` and indexes rules per tool; the supported-tool question is answered here at load time, not only in validation |
| `toolguard/resolve.py` | modify | production | medium | the resolver must branch command-tool vs file-tool to choose the subject and the matcher; that branch is a membership test by another name |
| `toolguard/permissions.py` | modify | production | medium | file-tool path matching vs Bash command matching is selected by tool identity |
| `toolguard/api.py` | modify | production | medium | the public `decide(tool_name, tool_input)` seam is the natural place for "extract this tool's subject from its payload" once a payload-key map exists |
| `toolguard/config_types.py` | modify | production | medium | either the alternative home named in the ticket, or gains the `ToolKind`/`ToolSpec` type while `constants.py` holds the instances |
| `toolguard/testing/sandbox.py` | modify | production | low | it constructs synthetic tool payloads for experiments, so it carries tool-name and payload-key literals of its own |
| `test/verdict_corpus/fixture_loader.py` | modify | test | low | it must build `tool_input` per case, which requires a tool-to-payload-key mapping it currently hardcodes |
| `toolguard/tools/takeover_audit.py` | modify | production | low | takeover invariants are asserted per governed tool, so it enumerates the governed set |
| `toolguard/tool_spec.py` | add | production | low | the alternative to `constants.py`: a dedicated module, matching the project's recent habit of promoting a concept into its own described thing |
| `.pyscn.toml` | modify | production | low | required only if the registry lands in a new module, which must be mapped to a layer or it is silently unmapped |
| `test/unit/test_hook.py` | modify | test | high | the payload-key and `COMMAND_TOOLS` changes are directly under test here |
| `test/unit/test_tool_spec.py` | add | test | medium | this project adds a dedicated test module per new module; the registry and its derived views need one |
| `test/unit/test_architecture.py` | modify | test | medium | the natural place to assert the new invariant "there is exactly one tool registry and the membership sets are derived from it" |
| `test/unit/test_tools_danger.py` | modify | test | medium | the duplicated tuples were the canary's find; a regression test that they stay derived belongs here |
| `test/unit/test_rule_entry.py` | modify | test | medium | tool-scoping tests move to the registry vocabulary |
| `test/unit/test_configuration.py` | modify | test | medium | supported-tool validation and `additional_supported_tools` behaviour |
| `test/unit/test_api.py` | modify | test | low | subject extraction at the public seam |
| `test/unit/test_tools_transcript_harvest.py` | modify | test | low | follows its module's payload-key change |
| `technical-notes.md` | modify | production | medium | the design rationale for a new described concept is exactly what this file collects |

Deliberately **not** predicted, though plausible: `compound.py`, `patterns.py`, `normalization.py`, `permission_resolution.py`, `tools/self_permission.py`, `tools/uninstall_readiness.py`, `tools/recommended_protections.py`, `tools/security_audit.py`, `rule_sort.py`, `tools/sorters.py`, `tools/replay.py`, `docs/configuration.md`, `README.md`. Each has a story, but the ticket scopes to membership tests and payload reads, and padding costs precision.

## 2. Concentration set

The substance is in three places:

1. **`toolguard/constants.py`** — the registry itself: `ToolSpec` (name, kind, payload key, governed-by-default) plus the four sets re-expressed as comprehensions over it. Small in lines, decisive in shape.
2. **`toolguard/hook.py`** — the only file that holds both a membership set *and* repeated payload-key literals, so it is where the change proves it removed real duplication rather than adding a layer.
3. **`toolguard/rule_entry.py`** — my main non-transcribed bet. "Tool scoping" cannot be implemented without a normalize-and-test-membership step, and the ticket's inventory of four sets does not mention it, which is the classic signature of a fifth copy that grep for `{"Bash", "Read"` would find but reading the ticket would not.

The rest of the diff should be mechanical substitution: literal set or literal string in, registry lookup out.

## 3. Expected counts

| | production | test |
|---|---|---|
| modified | 11 | 6 |
| added | 1 | 1 |
| deleted | 0 | 0 |

Total expected touched files: **19**.
