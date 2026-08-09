---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
- coder-latest
---

# Task: TOO-45 punch-list #10 fix pass (branch too-45)

Full code review at `toolguard-memories/latest-code-review-report.md`. Original spec:
`toolguard-memories/TOO-45/TOO-45 punch-list 10 ToolSpec - coder task spec.md`.

Corpus stayed byte-identical in the original consolidation; this pass fixes contract
problems the review found, no behaviour change intended.

## Fix list (from Arnon's fix-pass prompt)

1. **M1**: `governed_by_default()` names a set that isn't the runtime default
   (`config.py:975` default is `("Bash",)`). Rename `ToolSpec.governed_by_default` field
   -> `ToolSpec.is_builtin`; rename `tool_spec.governed_by_default()` -> `builtin_tools()`
   (later folded into M2's frozenset conversion, so final name is `BUILTIN_TOOLS`). Fix
   docstrings to say what it is (builtin knowledge set) and explicitly NOT a default.
   Check whether `constants.GOVERNED_TOOLS` should follow the rename -- verify each
   importer's actual intended semantics (builtin vs effective-governed); report a live
   bug if found, don't quietly fix behaviour.

2. **M2**: one registry, two view semantics -- `constants.py` snapshots at import time,
   but `installer.py`/`hook.py`/`transcript_harvest.py` call the tool_spec functions live.
   Fix: make the three derived views module-level frozensets in tool_spec.py
   (`KNOWN_TOOL_NAMES`, `BUILTIN_TOOLS`, `FILE_KIND_TOOLS`), keep `payload_key()` as the
   only function. Correct tool_spec.py's docstring (drops dynamism claim).

3. **Minors** (explicitly listed, do all):
   - constants.py docstring falsely claims "imports nothing from toolguard" (it imports
     tool_spec).
   - tool_spec.py:7-10 docstring wrongly describes `Configuration.governed_tools()` as
     consuming the registry -- it doesn't; only `config_validation.KNOWN_SUPPORTED_TOOLS`
     does.
   - Half-converted payload-key dispatch: `fixture_loader.py:680` and
     `transcript_harvest.py:226-229` still hardcode `"command"` next to a registry lookup.
     Fix both to `spec = TOOLS_BY_NAME.get(tool); key = spec.payload_key if spec else "command"`.
   - `hook.py:734` and `:1107` hardcode "No file_path provided" after the key became
     dynamic -- interpolate the resolved key. (Text is unchanged for current registry
     contents since Read/Write/Edit resolve to "file_path", so `test_hook_eval.py:166`'s
     `assertIn("No file_path provided", ...)` still passes -- confirmed, no test edit
     needed for that specific assertion.)
   - `assertRaises(Exception)` in test_tool_spec.py's frozen-dataclass test -> assert
     `dataclasses.FrozenInstanceError` specifically.
   - `TOOLS_BY_NAME` needs a duplicate-name guard -- must fail loudly at import if
     `_REGISTRY` has a repeated name.

4. **Close the test gap**: test:production ratio was 0.8:1 vs repo norm 1.9:1, gap sits on
   the unpinned seam (snapshot vs live). Once item 2 done, pin the resulting contract.
   Plan: add registry-integrity test (`len(TOOLS_BY_NAME) == len(_REGISTRY)`, all
   payload_keys non-empty), a duplicate-name-guard test, an identity pin
   (`constants.BUILTIN_TOOLS is tool_spec.BUILTIN_TOOLS`), and seam-pin tests in each
   consumer's existing test file (test_hook.py for `_handle_file_path_tool`,
   test_hook_eval.py for `_resolve_event`, test_tools_transcript_harvest.py for
   `_command_for_tool`, test_verdict_corpus.py for `fixture_loader.build_hook_payload`)
   that inject a fake `ToolSpec` via `patch.dict(tool_spec.TOOLS_BY_NAME, ...)` and prove
   dispatch genuinely reads through the registry rather than a hardcoded literal.

## Explicit DO NOT

- Do not change `governed_tools()`'s resolution or any default.
- Do not touch `config.py`'s `_DEFAULT_IGNORED_ALLOW_PATTERNS`.
- No behaviour change at all -- golden verdict corpus must stay byte-identical.

## Verification bar

- Golden verdict corpus byte-identical (the check that matters most).
- Full suite green (was 2721).
- `uv run python tools/architecture_fitness.py --layers` clean.
- `uv run ruff format .` and `uv run ruff check .`.

## Process

Intent disclosure before any authored Bash logic (heredocs, `python -c`, scratch scripts,
authored shell). `# INTENT:` / `# TOUCHES:` / `# INLINE BECAUSE:` plus `TG_INTENT=1` or
`TG_ATTEST_READONLY=1`.

## Decisions made during planning (to record in report)

- **constants.GOVERNED_TOOLS renamed to BUILTIN_TOOLS.** Checked all 4 real importers
  (`security_audit.py:353`, `maintenance.py:184,715`, `transcript_harvest.py:281`) --
  every one iterates "every tool we know how to analyze/harvest", never "the config's
  effective governed set". No live bug found. Since the name carries the exact same
  false-default-implication risk M1 flagged at the tool_spec layer, renaming it there too
  is the consistent fix, not scope creep. Not part of the documented public API/docs
  surface (grepped README.md, docs/, api.py -- no hits), so safe to rename with no
  external-compat concern.
- Explicitly NOT doing: m6 (private alias `_tool_payload_key` import), s1 (collapse
  `FILE_PATH_TOOLS` alias chain), s4 (typing style FrozenSet/Mapping -> builtin
  generics) -- none of these are in the fix-pass prompt's itemized list; keeping scope to
  what was asked.