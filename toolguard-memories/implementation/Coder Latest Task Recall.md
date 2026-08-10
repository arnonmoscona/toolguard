---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
- coder-latest
---

## TOO-45 punch-list #03, stage 1 of 3

Branch: `too-45`. Working dir: `/home/arnon/projects/toolguard`.

### Context

`resolve.py` (928 lines) and `permission_resolution.py` form a bidirectional runtime cycle. Chosen plan: three staged commits. This is **stage 1 only**: extract the file-path matching cluster out of `resolve.py` into `toolguard/file_matching.py`. Rename-only, no behaviour change, no rewiring. Stage 2 (invert the seam) and stage 3 (point cascade tests at pure fold) are explicitly NOT part of this task.

### What to do

- Identify the file-path matching cluster in `toolguard/resolve.py`: matching a filesystem path against glob-style permission patterns, plus path anchoring/normalisation helpers used only by that path.
- Move to new `toolguard/file_matching.py`.
- Rename-only: no restructuring, no renamed functions, no "improvements". If something looks wrong in the moved code, leave it and report it.
- Layer: `engine`, alongside `resolve`/`permission_resolution`. Add to `.pyscn.toml` engine packages list (line ~212) or completeness check fails.
- Decide per-helper whether it's genuinely file-path-only vs shared with Bash path (stays put). Report uncertain calls.
- Keep `resolve.py`'s public surface unchanged -- importers of `resolve` must not need editing.

### Do NOT

- Touch `permission_resolution.py`, `DecideDetailed` Protocol, any `decide_detailed` closure (stage 2).
- Touch the cascade's unit tests (stage 3).
- Add a fitness predicate for the cycle (Arnon's decision: code-review checks by measurement instead).

### Verification required

- Golden verdict corpus byte-identical (part of main suite, `test_verdict_corpus.py`, ~in the 2733 count).
- Full suite green (2733 at last count baseline confirmed before starting).
- `uv run python tools/architecture_fitness.py --layers` clean.
- `uv run ruff format .` and `uv run ruff check .`.
- Report line counts before/after for `resolve.py` and size of new module.

### Process

- No git commits -- Arnon does all git write ops.
- Intent disclosure before any authored Bash logic (heredocs, python -c, scratch scripts, authored shell loops): `# INTENT:` / `# TOUCHES:` / `# INLINE BECAUSE:` plus `TG_INTENT=1` or `TG_ATTEST_READONLY=1`.
- Write implementation report to basic-memory.

## Analysis performed before implementing

Read `toolguard/resolve.py` fully (928 lines). Candidate cluster:

- `_anchor_file_pattern` -- file-path only
- `_collapse_slashes` -- only called from `_match_file_path_pattern`; docstring itself says "file path or GLOB path pattern" -- file-path only (verified via repo-wide grep, no other callers)
- `_match_file_path_pattern` -- file-path only
- `_first_matching_file_pattern` -- file-path only
- `_decide_file_path_at_level_detailed` -- file-path only
- `_check_file_path_hard_deny` -- file-path only

**Stays in resolve.py (shared with Bash path):**
- `_hard_deny_additional_context` -- called by BOTH `resolve_file_path_permission_detailed` (file path) and `resolve_bash_permission_detailed`'s `_decide` closure (Bash). Confirmed shared -- explicit task guidance says shared helpers stay put.
- `resolve_file_path_permission_detailed` -- the public top-level file-path resolver. Decided to KEEP this in resolve.py rather than move it, because it calls `_hard_deny_additional_context` (shared, stays in resolve.py). Moving it to file_matching.py would require file_matching to import back from resolve.py, while resolve.py needs to import from file_matching.py (to re-export the moved helpers for backward-compat imports) -- that's a new import cycle between resolve and file_matching, which would be exactly the kind of thing this whole punch-list is trying to eliminate. Keeping the public entry point in resolve.py avoids that; file_matching.py has zero dependency back on resolve.py.
- `_deciding_sub_match`, `resolve_bash_permission_detailed` -- Bash-only, untouched.

### External references needing preservation

Tests import several of these "private" helpers directly from `toolguard.resolve` (not `toolguard.hook`):
- `test_hierarchical.py`: `from toolguard.resolve import _anchor_file_pattern` (4 call sites)
- `test_hook.py`: `from toolguard.resolve import (_decide_file_path_at_level_detailed, resolve_bash_permission_detailed)`
- `test_hard_deny.py`, `test_resolve.py`, `hook.py`, `api.py`: import `resolve_file_path_permission_detailed` from `toolguard.hook` or `toolguard.resolve`.

Since `resolve.py`'s public surface must stay unchanged, resolve.py will import the moved names from `file_matching` and re-export them (mirroring the existing `LevelMatch as LevelMatch` re-export idiom already in the file), so no test file needs editing.

### Docstring/doc-drift updates anticipated

- `resolve.py` module docstring lists functions moved from hook.py; needs updating to reflect new home for the ones that move again.
- `config_types.py` docstrings reference `toolguard.resolve._decide_file_path_at_level_detailed`, `toolguard.resolve._check_file_path_hard_deny`, `toolguard.resolve._anchor_file_pattern` -- update to `toolguard.file_matching.*`. `_hard_deny_additional_context` references stay pointed at resolve.py (unchanged).
- `tools/architecture_fitness.py` references `toolguard.resolve._check_file_path_hard_deny` in a comment -- update.
- Test file comments (test_hierarchical, test_recommended_protections, test_resolve, test_hook) reference `resolve.py`'s `_anchor_file_pattern` etc in prose/docstrings -- these are NOT the cascade's unit tests being restricted (that's about permission_resolution/resolve fold tests specifically), but since instructions say don't touch cascade tests and to keep tests working via re-export, I will leave test files untouched entirely (imports keep working via re-export) unless a test file's own prose docstring is factually wrong about location -- decided to leave test file prose alone since the import continues to work correctly and the task's explicit restriction is "do not touch the cascade's unit tests"; broadly avoiding touching any test file is the safer/smaller diff.

### .pyscn.toml layer map

Engine layer packages line ~212: `packages = ["permissions", "compound", "resolve", "parser", "permission_resolution"]` -- need to add `"file_matching"`.

### Baseline test run (before any changes)

`uv run python -m unittest discover -s test -t .` => Ran 2733 tests in 48.787s, OK. Confirms baseline matches ticket's expected count before starting.
