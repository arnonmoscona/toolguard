---
title: 80-estimate-predictions
type: note
tags:
- TOO-45
- surprise-measurement
permalink: toolguard/too-45/reports/surprise/80-estimate-predictions
---

# Blinded touch-set prediction — ticket 80 (`Path.resolve()` is a fifth route to cwd)

Prediction made from the ticket body and the file inventory only. No source file, no grep, no test run, no git history.

## Convention used for the counts

"Production" = anything under `toolguard/` **and** `tools/` (the dev instruments are shipped-adjacent source that the ticket explicitly asks to extend). "Test" = anything under `test/`. Non-Python config/docs are listed separately and excluded from both counts unless noted.

## What I read the ticket as committing to

Four distinct work items, each with a different centre of gravity:

1. **Move `expanduser` out of `ambient` into `path_utils`** — stated outright. Touches the two modules plus every caller of `ambient.expanduser()`.
2. **Migrate relative `Path.resolve()` / `Path.absolute()` sites to resolve explicitly against `ambient.cwd()`** — 17 named sites plus whatever `absolute()` adds. This is the widest, shallowest part.
3. **Build the deny-by-default AST checker** (`os` closed at import level, `pathlib` closed over an enumerated API) — this is the deepest, most concentrated part, and I expect it to land as a new mode in the existing architecture instrument rather than a new tool.
4. **Two guard tests**: a runtime `dir(Path)` enumeration compared against a stored classification (fails on an unclassified member), and a `sys.version_info[:2]` pin with a message naming the five classified members.

## Predicted touch set

### Production — `toolguard/`

| file | why | confidence |
|---|---|---|
| `toolguard/ambient.py` | `expanduser()` removed; module reduced to facts-only (`home`, `cwd`, `env`, `env_var`). Explicitly stated. | high |
| `toolguard/path_utils.py` | receives `expanduser()`; also the most likely home for an explicit "resolve relative against a given base" helper, and itself a heavy relative-path resolver | high |
| `toolguard/normalization.py` | "Path normalization for consistent pattern matching" is the single most likely place a relative path is resolved before matching | high |
| `toolguard/config.py` | 2095 lines of discovery/project-root/relative-path work; near-certain to hold several of the 17 | high |
| `toolguard/env_config.py` | `.env` location + `~` expansion — a caller of both the moved `expanduser` and cwd-relative resolution | medium |
| `toolguard/file_matching.py` | file-path pattern matching against relative tool inputs | medium |
| `toolguard/log_writer.py` | `resolve_log_dir` resolves a configured (possibly relative, possibly `~`) log directory | medium |
| `toolguard/hook.py` | the entry point that takes `cwd` off the hook event; a `.resolve()` on a tool-supplied relative path is likely here | medium |
| `toolguard/config_write_guard.py` | self-protection compares candidate write paths to protected roots — exactly the code that must not silently use the process cwd | medium |
| `toolguard/install_provenance.py` | resolves the installed package location and compares it to a repo path | medium |
| `toolguard/testing/sandbox.py` | builds a throwaway project tree; resolves paths under it | medium |
| `toolguard/tools/installer.py` | 2338 lines of path manipulation against a user-supplied target directory | medium |
| `toolguard/tools/config_access.py` | per-layer views keyed by resolved config paths | low |
| `toolguard/tools/working_tree.py` | resolves the repo path handed to the git check | low |
| `toolguard/session_start.py` | resolves project/session paths at hook start | low |
| `toolguard/tools/project_root.py` | thin re-export; only touched if the `path_utils` surface it re-exports changes | low |

### Production — `tools/` (dev instruments)

| file | why | confidence |
|---|---|---|
| `tools/architecture_fitness.py` | "five modes over this tree" — the AST `os`-import ban and the enumerated-`pathlib` check are a sixth mode here, riding the import graph `--layers` already walks. This is the centre of the ticket. | high |
| `tools/comment_hygiene.py` | a sibling AST instrument; touched only if the classification table or a shared AST walker is factored out of it | low |

### Additions

| file | why | confidence |
|---|---|---|
| `test/unit/test_path_utils.py` (**added**) | the inventory shows **no dedicated test module for `path_utils`** despite 318 lines. The `expanduser` tests moving out of `test_ambient.py` need a home, and the ticket's precedent (ticket 44) means those tests exist and are substantive. | medium |
| a new small module holding the pathlib member classification (**added**), e.g. `tools/pathlib_surface.py` or `toolguard/…` equivalent | the ticket wants the classification stored and version-checked; it may be split out rather than embedded in the 4002-line instrument | low |
| a new `test/unit/test_stdlib_surface.py` or similar (**added**) for the `dir(Path)` enumeration + version pin | plausible alternative to folding both into `test_architecture.py` | low |

### Deletions

None predicted. `ambient.expanduser` moves rather than disappears, and no module in the inventory exists solely to host it.

### Test

| file | why | confidence |
|---|---|---|
| `test/unit/test_architecture.py` | "architectural invariant tests for module layering" — the natural home for the `os`-import ban invariant, the `dir(Path)` enumeration guard and the `sys.version_info` pin | high |
| `test/unit/test_architecture_fitness.py` | 4175 lines of tests for the instrument; a new mode requires new tests here | high |
| `test/unit/test_ambient.py` | `expanduser` tests removed/relocated; facts-only surface asserted | high |
| `test/unit/_config_isolation.py` | the mixin the ticket names as the proximate cause (clears `os.environ` with no `HOME`); a cwd-pinning fix belongs here so the isolation actually isolates | medium |
| `test/unit/test_normalization.py` | follows the normalization change | medium |
| `test/unit/test_config.py` | project-root/relative-path discovery tests follow the config change | medium |
| `test/unit/test_env_config.py` | follows the `expanduser` caller change | medium |
| `test/unit/test_hook.py` | follows any cwd-resolution change at the entry point | medium |
| `test/unit/test_log_writer.py` | follows `resolve_log_dir` | low |
| `test/unit/test_config_write_guard.py` | follows the write-guard path comparison | low |
| `test/unit/test_sandbox.py` | follows sandbox path resolution | low |
| `test/unit/test_tools_project_root.py` | follows any `path_utils` primitive rename | low |
| `test/unit/test_tools_installer.py` | follows installer path handling | low |

### Non-Python (excluded from the counts)

| file | why | confidence |
|---|---|---|
| `.pyscn.toml` | only if the checker needs a declared whitelist or a layer note; the layer map itself should not need to move | low |
| `docs/architecture-as-built.md` / `technical-notes.md` | the route table is called "the durable artifact"; it plausibly gets written down somewhere permanent | low |

## Concentration set

The change is centred in six files, and I expect the large majority of added/changed lines to be here:

- `tools/architecture_fitness.py` (the checker — the single biggest block of new code)
- `test/unit/test_architecture_fitness.py` (its tests)
- `test/unit/test_architecture.py` (the two guard tests: enumeration + version pin)
- `toolguard/ambient.py` (the facts-only contraction)
- `toolguard/path_utils.py` (the destination for `expanduser` and the resolve helper)
- `test/unit/test_ambient.py`

Everything else in the list is expected to be a one-to-three-line-per-site migration.

## Expected counts

**Production** (`toolguard/` + `tools/`)

- modified: **12** (plausible range 8–16)
- added: **0** (30% chance of 1, if the classification table is split out)
- deleted: **0**

**Test** (`test/`)

- modified: **8** (plausible range 5–12)
- added: **1** (`test/unit/test_path_utils.py`; plausible range 0–2)
- deleted: **0**

**Non-Python**: 0–2 modified, 0 added, 0 deleted.
