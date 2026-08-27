---
title: TOO-45 punch-list 10 ToolSpec - coder task spec
type: note
permalink: toolguard/too-45/too-45-punch-list-10-toolspec-coder-task-spec
tags:
- task-memory
- TOO-45
---

# TOO-45 punch-list #10 — make "a supported tool" a described thing

Ticket: `toolguard-memories/TOO-45/proposed-tickets/10-tool-as-a-described-thing.md`. Read it first.

## Facts established by measurement before this spec was written

| question | answer |
|---|---|
| Is the supported-tool set open at runtime? | **Yes, but only for validation.** `additional_supported_tools` (config) is unioned into `all_supported_tools` in `config_validation.py:92`. It gives a tool a *name* only — never a kind or a payload key — and an ungoverned tool's payload is never read, because `hook.main()` returns early for anything not in `config.governed_tools()`. |
| Is the *governed* set configurable? | **Yes.** `config.governed_tools()` is a hierarchy-wide union defaulting to `('Bash',)`. `constants.GOVERNED_TOOLS` is a **default**, not the effective set. |
| How many structural membership tests use literal tool names? | Two outside the named sets: `api.py:90` (a docstring) and **`tools/installer.py:900`, a live hardcoded `("Read", "Write", "Edit")` tuple the ticket does not mention.** |
| Payload-key sites? | Three reads (`hook.py:737`, `hook.py:1100`, `tools/transcript_harvest.py:226`) plus a **constructor** at `tools/architecture_fitness.py:3738`, with the same knowledge restated as prose at `:3673`. |
| Which layer can own the registry? | **`foundation`.** Clients span config (`config_validation`), api (`api`), runtime (`hook`) and tooling (`danger`, `transcript_harvest`, `installer`). `config_types.py` is config-layer and therefore illegal — this settles the ticket's open "constants.py or config_types.py" question. |

**The registry is static. The configurable parts stay configurable.** The structural facts — kind, payload key, governed-by-default — belong to the registry. `governed_tools()` and `additional_supported_tools` keep their current semantics and consume the registry rather than duplicating it.

## What to build

### 1. `toolguard/tool_spec.py` — new module, `foundation` layer

Add it to `.pyscn.toml`'s foundation packages list; the completeness check fails if you forget.

A frozen dataclass per tool — name, kind, the payload key its subject lives under, whether it is governed by default — and one registry holding the instances. Use an `Enum` for kind (this codebase uses them: `once_per.Repeat`, `once_per_store.ClaimStatus`, `permission_migration.MigrationOutcome`), not a bare string.

`Bash`'s subject lives under `command`; `Read`/`Write`/`Edit`'s under `file_path`. The two MCP terminal names currently in `hook.COMMAND_TOOLS` are command-kind and must be registered.

Expose derived views as functions or module-level frozensets computed from the registry — never as second copies.

### 2. The four membership sets become derived, in place

- `constants.GOVERNED_TOOLS` and `constants.FILE_TOOLS` stay where they are, with their current names, but are **computed from the registry**. `constants` is foundation, so importing `tool_spec` is legal and same-layer. This keeps every existing importer working untouched — `api.py`, `tools/danger.py`, `tools/transcript_harvest.py`, `hook.py` — while leaving exactly one source of truth.
- `hook.COMMAND_TOOLS` derives from the registry.
- `config_validation.KNOWN_SUPPORTED_TOOLS` derives from the registry. Its union with `additional_supported_tools` stays exactly as it is.

**Do not leave a name defined in two places.** If a constant survives, it is because it is derived, not because it was left alone.

### 3. The payload key stops being a string literal

`tool_input.get("file_path", "")` at `hook.py:737` and `hook.py:1100`, and `tool_input.get("file_path")` at `tools/transcript_harvest.py:226`, look the key up from the registry. This is the standing rule that a literal the code depends on is a constant, and it is the part of the ticket with real teeth: it is what makes adding `NotebookEdit` a one-line change instead of a grep hunt.

### 4. The fifth copy the ticket missed

`tools/installer.py:900` builds `(f"{tool}(~/.toolguard/**)", "allow") for tool in ("Read", "Write", "Edit")` from a bare tuple wired to no constant. That is exactly the shape the ticket says was previously found "only by grepping for literal tuples". Point it at the derived file-tools view.

### 5. The dev instrument encodes the same map

`tools/architecture_fitness.py:3738` constructs `{"file_path": target}` and `:3673` restates the rule in a comment. It is dev-only and repo-root `tools/`, which is the `support`/`tooling` end and may legally import from foundation. Point it at the registry and delete the comment that duplicates it — a comment restating a fact the code can now state is drift waiting to happen.

## Out of scope

- **`NotebookEdit`.** Adding it is user-visible and pulls in configuration docs, release notes and a version bump. The whole point is that it *becomes* a one-entry addition; do not take it here. Say in your report how many lines adding it would now be.
- Changing `governed_tools()`'s resolution, `additional_supported_tools`' semantics, or any default.
- Any behaviour change at all. See below.

## The trap to watch for

**Unifying divergent normalisations is a behaviour change wearing a refactor's clothes.** Before you derive anything, check whether the existing membership tests agree on case and on the scoped `Tool(pattern)` form. If one site compares a raw payload field and another a lowercased or scope-stripped name, deriving them from one registry silently changes what some input decides.

If they already agree, **the golden verdict corpus must stay byte-identical**, and a red corpus means you made a mistake. If they do not agree, **stop and report** — that is a decision about which behaviour is correct, not a refactor, and it needs recording rather than absorbing.

## Constraints

- **Stdlib only.** No new runtime dependency.
- `unittest` under `test/`, `uv run python -m unittest discover -s test -t .`. Not pytest.
- `uv run ruff format .` and `uv run ruff check .` before reporting.
- Doc comments 1-5 lines. No ticket narrative in code.
- Frozen dataclass over a tuple; `Enum` over a bare string for anything the code branches on.

## Verification

- **The golden verdict corpus unchanged.** This is the single most important check: it is sensitive to any change in what a decision *is*, which is exactly what a botched derivation would alter.
- A test that each derived view equals what the hand-written set contained before this change — pin the sets by literal value once, so a future registry edit that silently drops a tool fails loudly.
- A test that the payload key for each file-kind tool resolves correctly, driven from the registry rather than restating `"file_path"`.
- Full suite green (2710 at last count), `uv run python tools/architecture_fitness.py --layers` clean.

## Process

Intent disclosure before any Bash command carrying logic you authored — heredocs, `python -c`, scratch scripts, **and authored shell** (`sed -e`/`-i`, `awk`, `for`/`while` loops). The `# INTENT:` / `# TOUCHES:` / `# INLINE BECAUSE:` block plus `TG_INTENT=1`, or `TG_ATTEST_READONLY=1` when every leaf is read-only. Required even when the command will be blocked — the disclosure feeds after-the-fact analysis, not just the approval prompt.

## Report

Cover: whether the existing membership tests agreed on normalisation (and what you did if not); how many lines adding `NotebookEdit` would now be; any further copies you found that this spec does not list; and a duplication self-check confirming no tool set is defined twice anywhere.
