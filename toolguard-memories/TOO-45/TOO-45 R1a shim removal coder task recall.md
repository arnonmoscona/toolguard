---
title: TOO-45 R1a shim removal coder task recall
type: note
permalink: toolguard/too-45/too-45-r1a-shim-removal-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task: TOO-45 step R1a — delete __iter__ tuple-compat shims

Source brief: `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1a_shims_brief.md`
Backing measurement: basic-memory `TOO-45/TOO-45 R1 scoping trace.md`.

### What to do
- Delete `__iter__` on `BashResolution` (toolguard/resolve.py:98, method at ~169-178) and on
  `FileResolution` (toolguard/resolve.py:182, method at ~240-251).
- `BashResolution.__iter__`: measured 0 callers anywhere — straight deletion.
- `FileResolution.__iter__`: measured 8 test call sites unpacking
  `resolve_file_path_permission_detailed(...)`:
  - test/unit/test_hard_deny.py lines 633, 657, 660, 694, 701, 727
  - test/unit/test_hierarchical.py lines 478, 586
  Convert each to explicit attribute access. Update Given/When/Then docstrings if the change
  alters what's being demonstrated (.claude/rules/testing.md).
- Caller list is a STARTING POINT — heuristic was wrong before (reported 0 for both when
  FileResolution has 8). Must independently search for other tuple-unpacking of BashResolution/
  FileResolution: starred unpacking, list(...), tuple(...), for-iteration, anywhere in repo
  (not just toolguard/ — test/ and tools/ too).
- The scoping trace also flagged: 2 tests exist "solely to pin the shims" (10 affected = 8
  incidental + 2 shim-pinning tests) — need to find and handle these 2 as well (likely delete
  them, since they test the __iter__ behavior itself which is being removed).
- Must check: does deleting __iter__ actually disable unpacking, or does another protocol
  (NamedTuple, __getitem__) still allow it? Both are `@dataclass(frozen=True)`, not NamedTuple,
  and no __getitem__ visible in the class bodies — but must PROVE via probe: `a,b,c = resolution`
  raises TypeError after deletion. Report actual traceback.

### Acceptance (paste real output)
```
uv run python -m unittest discover -s test -t .           # expect OK
uv run python tools/corpus_build.py --verify              # expect: no differences
uv run python tools/architecture_fitness.py --guard       # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates  # R1 shim list must now be EMPTY
uv run ruff format . && uv run ruff check --no-cache .
```
No verdict may change (6,401 in-process + 61 e2e corpus cases).

### Hard rules
- NEVER git checkout/restore/stash/reset. Read-only git only. Backup originals to
  `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1a-backups/`,
  restore by copy + sha256 verify if needed.
- Tree has substantial uncommitted work — do not disturb, do not commit.
- Do NOT copy the repo anywhere.
- uv run python always; unittest not pytest; ruff check --no-cache.
- No local imports, no async, no threading.

### Report destination
basic-memory project `toolguard`, note `TOO-45/TOO-45 R1a shim removal report.md`, tagged
task-memory + TOO-45. Include acceptance output verbatim, TypeError demonstration, and whether
unpacking was genuinely disabled or survived via another protocol. No hard-wrapped paragraphs.

## Clarifications from discussion
(none yet — auto mode, proceeding on the brief as written)
