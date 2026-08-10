---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-45
- coder-latest-implementation-report
---

## TOO-45 punch-list #03, stage 1 of 3 -- extract file-path matching cluster

Branch `too-45`, `/home/arnon/projects/toolguard`. Rename-only extraction of the
file-path pattern-matching cluster out of `toolguard/resolve.py` into a new
`toolguard/file_matching.py`. No behaviour change, no rewiring of
`permission_resolution.py` (stage 2) or the cascade's tests (stage 3) -- neither
was touched.

## Summary of what moved

New module `toolguard/file_matching.py` (267 lines) now defines, byte-for-byte
identical to their pre-move bodies (verified programmatically, see below):

- `_anchor_file_pattern`
- `_collapse_slashes`
- `_match_file_path_pattern`
- `_first_matching_file_pattern`
- `_decide_file_path_at_level_detailed`
- `_check_file_path_hard_deny`

Only `_check_file_path_hard_deny`'s docstring differs from its pre-move body,
and only in its cross-module references (bare names -> fully-qualified
`~toolguard.resolve.X`, since the functions it references stay in
`resolve.py`). No logic changed anywhere.

`resolve.py` now imports these six names from `toolguard.file_matching` with
`as`-aliasing (`_anchor_file_pattern as _anchor_file_pattern`, etc. -- the same
re-export idiom the file already used for `LevelMatch as LevelMatch` and
friends), so every existing importer of `toolguard.resolve` (including four
test files that import these "private" helpers directly) keeps working with
no test-file edits.

## What stayed in resolve.py, and why

- `_hard_deny_additional_context` -- called by BOTH
  `resolve_file_path_permission_detailed` (file path) and
  `resolve_bash_permission_detailed`'s `_decide` closure (Bash). Genuinely
  shared with the Bash path, so per the ticket's own instruction it stays put.
- `resolve_file_path_permission_detailed` -- the public top-level file-path
  resolver. **This is the one judgment call worth flagging explicitly.** It
  reads at first glance like part of "the file-path matching cluster," but it
  calls `_hard_deny_additional_context`, which must stay in `resolve.py`
  (shared). Moving the public function too would force `file_matching.py` to
  import back from `resolve.py` for that one call, while `resolve.py` already
  needs to import `file_matching.py` to re-export the six moved helpers --
  i.e. a fresh two-module import cycle, exactly the category of problem this
  whole punch-list exists to remove (even though this particular cycle would
  be new, not the resolve/permission_resolution one named in the ticket). Kept
  it in `resolve.py` instead; `file_matching.py` ends up with zero import edge
  back to `resolve.py`. Flagging this because it's a judgment call rather than
  a mechanical one -- reasonable people could draw the "cluster" boundary
  differently, and the alternative (accept the cycle, or duplicate the
  lookup) both seemed worse.
- `_deciding_sub_match`, `resolve_bash_permission_detailed` -- Bash-only,
  untouched.

## Files changed

- **New**: `toolguard/file_matching.py` (267 lines)
- `toolguard/resolve.py`: 928 -> 714 lines. Removed the six moved function
  bodies; added the import/re-export block; updated the module docstring
  (two places) and one inline docstring cross-reference to point at the new
  module/location instead of claiming the functions are defined "here"/"below".
- `toolguard/config_types.py`: five docstring cross-references
  (`LevelMatch`, `ResolveConfig.resolve_config_path`,
  `ResolveConfig.hard_deny`, `DecideDetailed`) updated from
  `toolguard.resolve.X` / `` resolve.py``'s X`` to `toolguard.file_matching.X`
  / ``file_matching.py``'s X`` for the four moved functions. No code changed
  in this file.
- `.pyscn.toml`: added `"file_matching"` to the `engine` layer's package list
  (line ~212) so the layer-completeness check doesn't flag the new module as
  unmapped.
- `tools/architecture_fitness.py`: one docstring example
  (`_is_literal_decision_tuple`) updated from
  `` toolguard.resolve._check_file_path_hard_deny `` to
  `` toolguard.file_matching._check_file_path_hard_deny ``. No code changed.
- `docs/architecture.md`: added a two-line entry for `file_matching.py` in the
  package-structure tree diagram, next to `resolve.py`, since it's now a real
  module in the engine layer and the existing tree lists every other engine
  module individually. This is the only doc I touched beyond code
  docstrings -- worth a `/documentation-review` pass before push per the
  project's own pre-push checklist, since this changed `docs/`.

## Doc-drift found but deliberately NOT fixed (out of scope for stage 1)

`technical-notes.md` lines 328 and 385 already say `hook._check_file_path_hard_deny`
and `hook._decide_file_path_at_level_detailed` -- stale from a PRIOR move (these
functions have lived in `resolve.py`, not `hook.py`, since before this stage
started; `resolve.py`'s own docstring documents that earlier move). This
predates my change and isn't something stage 1 introduced, so I left it alone
rather than scope-creep into fixing pre-existing drift unrelated to this move.
Flagging it here so it doesn't get lost.

## Verification

- **Byte-for-byte check**: wrote a one-off comparison script (git HEAD copy of
  `resolve.py` vs `file_matching.py`, extracting each function's source text)
  confirming all six moved functions are identical except the one documented
  docstring cross-reference update in `_check_file_path_hard_deny`. Deleted
  the scratch script and temp file afterward.
- `uv run python -m py_compile` on all touched/new files: clean.
- Baseline (before any change): `uv run python -m unittest discover -s test -t .`
  -> **2733 tests, OK** (confirms the ticket's stated baseline).
- After the move: same command -> **2733 tests, OK** (identical count, no
  failures -- this includes `test_verdict_corpus.py`'s golden verdict corpus,
  which compares verdict objects and would have caught any behaviour drift).
- `uv run python tools/architecture_fitness.py --layers` -> completeness and
  direction both clean.
- `uv run python tools/architecture_fitness.py --guard --since HEAD` -> PASS,
  no violations, 12 canaries evaluated against the live hook (ran this in
  addition to the ticket's required `--layers` check, since it was cheap and
  covers diff/test-count/dependency/lint together).
- `uv run ruff format .` -> 173 files left unchanged (no reformatting needed).
- `uv run ruff check .` -> All checks passed.
- `git status` confirms the changed-file set is exactly the five files above
  plus the new module (and my own task-memory note) -- no test files touched,
  `permission_resolution.py` untouched, `DecideDetailed` Protocol untouched.
  (`toolguard/suppression.py` shows as `AD` in `git status` but that predates
  this session entirely -- unrelated prior work, not touched by me.)

## Line counts (as requested)

- `resolve.py`: 928 -> 714 lines (-214)
- `file_matching.py`: new, 267 lines

## Anti-pattern scan

No async/await, no threading, no local (in-function) imports introduced in
either file. All moved/new functions retain their original docstrings.

## Known pre-existing oddity in the moved code (left untouched, per "rename-only, report don't fix")

`_match_file_path_pattern` (both before and after the move) has
`except ValueError, TypeError:` -- looks like Python 2 syntax at a glance, but
this project runs 3.14 where that's valid, real-tuple except-without-parens
syntax (per the project's own auto-memory note: "ruff strips except-tuple
parens ... valid and still a real tuple -- don't 'fix' it back"). Moved
verbatim, unchanged, correctly.

## Process notes

- No git commits made -- all git write operations left to Arnon.
- Two Bash commands carrying logic I authored (both read-only verification
  scripts comparing function source text) were disclosed with
  `# INTENT:`/`# TOUCHES:`/`# INLINE BECAUSE:` plus `TG_ATTEST_READONLY=1`.

## Time and cost (estimated)

- Phase 1 (planning: read resolve.py, grep for external references, read
  config_types.py/.pyscn.toml/architecture_fitness.py, write task recall):
  ~19:13-19:19, ~6 min. Est. cost: ~$0.35 (heavy file reading).
- Phase 2 (implementation: write file_matching.py, edit resolve.py,
  config_types.py, .pyscn.toml, architecture_fitness.py, docs/architecture.md;
  compile/test/lint iterations): ~19:19-19:24, ~5 min. Est. cost: ~$0.30.
- Phase 3/4 (byte-for-byte verification script, final full-suite + guard +
  ruff reruns, this report): ~19:24-19:26, ~2 min. Est. cost: ~$0.15.
- **Total elapsed: ~13 minutes. Total estimated cost: ~$0.80** (Sonnet 5,
  moderate context/output volume, no extended thinking).
