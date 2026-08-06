---
title: TOO-45 R1a shim removal report
type: note
permalink: toolguard/too-45/too-45-r1a-shim-removal-report
tags:
- task-memory
- TOO-45
---

## Summary

Deleted the `__iter__` tuple-compatibility shims on `BashResolution` and `FileResolution` (`toolguard/resolve.py`), converted the 8 test call sites that unpacked `FileResolution` as a 3-tuple to attribute access, deleted the 2 tests that existed solely to pin the `__iter__` behavior, and updated 2 more tests (discovered independently, not in the brief's caller list) that asserted the shims' presence on the live tree. Corpus verified with no differences (6,401 in-process + 61 e2e). No production behavior changed -- only removal of dead compatibility machinery and its direct test dependents.

## Files changed

- `toolguard/resolve.py` -- deleted `BashResolution.__iter__` and `FileResolution.__iter__`; updated the module docstring and both class/field docstrings that described the now-removed backwards-compatible-iteration behavior.
- `test/unit/test_hard_deny.py` -- converted 6 tuple-unpack call sites (`decision, reason, _override = resolve_file_path_permission_detailed(...)` and variants) to `result = resolve_file_path_permission_detailed(...)` + `result.decision` / `result.reason`.
- `test/unit/test_hierarchical.py` -- converted 2 tuple-unpack call sites the same way.
- `test/unit/test_resolve.py` -- deleted `test_file_resolution_three_tuple_unpacking_still_works` (in `TestFilePathAdditionalContext`) and `test_bash_resolution_three_tuple_unpacking_still_works` (in `TestBashAdditionalContext`). Both tests existed for no purpose other than demonstrating the `__iter__` shim's 3-tuple unpacking worked; their only subject was the removed method itself, so per the exception in the testing rules ("if you delete production code, you may delete the tests that pin exactly that code") they were deleted along with it. Both docstrings named exactly what they pinned ("Given a FileResolution/BashResolution... When it is unpacked as a 3-tuple... the legacy calling convention"), so there is no ambiguity about what they were testing.
- `test/unit/test_architecture_fitness.py` (untracked, part of the prior R1b stage's work, not mine to begin with) -- found independently while searching for other tuple-unpacking dependents, NOT in the brief's caller list. Two tests here exercised `tools/architecture_fitness.py`'s `find_iter_shims`/`compute_predicates` against the REAL toolguard tree and asserted the shims were present (that was their whole point in R1b -- demonstrating the OLD scanner's blind spot). Since I deleted the exact production code (`__iter__` on both classes) these two live-tree tests pinned, I updated rather than deleted them, per the same exception clause, because rewriting them to assert the new correct state (shim list now empty) preserves real regression value and matches the brief's own acceptance criterion for `--predicates`:
  - `test_shims_with_callers_only_in_test_area_on_real_tree` -> renamed `test_no_iter_shims_remain_on_real_tree_after_r1a`; now asserts neither class appears in `find_iter_shims()`'s output.
  - `test_r1_shims_are_scanned_for_test_and_tools_callers` -> renamed `test_r1_shims_list_is_empty_after_r1a`; now asserts `predicates["R1"]["iter_shims"] == []`.
  Both new docstrings explain what the test asserted before R1a and why the assertion flipped.

## Independent search for other tuple-unpacking dependents (per the brief's "don't trust the list" instruction)

Grepped the entire repo (`test/`, `toolguard/`, `tools/`) for every call site of `resolve_bash_permission_detailed` / `resolve_file_path_permission_detailed`, for `for x, y in ...`, `list(...)`/`tuple(...)` conversions, and starred unpacking of any variable that could hold one of these two objects. Result: the brief's 8-site list for `FileResolution` was exactly complete (confirmed independently via grep, not just trusted), and `BashResolution` genuinely has zero unpacking call sites anywhere. Three near-miss patterns were checked and ruled out as unrelated:

- `test_hard_deny.py`/`test_hierarchical.py`/`test_takeover_mode.py` all have `_resolve(...)` helper methods that unpack `decision, reason = self._resolve(...)` -- but `_resolve` itself returns a hand-built plain tuple (`return resolved.decision, resolved.reason`), not a `BashResolution`/`FileResolution` instance. Not a shim caller.
- `toolguard/permission_resolution.py:147,173` unpacks a variable named `result` -- but that `result` comes from `decide_detailed(...)` (`_decide_file_path_at_level_detailed` / `decide_command_at_level_detailed`), which returns a plain `(decision, reason, matched_pattern)` tuple by design, not a resolution dataclass.
- `toolguard/hook.py:1146` does `for sub_command, override in result.overrides:` -- iterating `.overrides`, a plain list of 2-tuples, not the resolution object itself.

## Watch-for check: was unpacking genuinely disabled, or did it survive via another protocol?

**Genuinely disabled.** Both `BashResolution` and `FileResolution` are plain `@dataclass(frozen=True)` classes -- confirmed neither is a `NamedTuple` subclass nor defines `__getitem__` (grepped `toolguard/resolve.py` for both before touching anything). Demonstrated by execution with a scratch probe (`/tmp/.../scratchpad/probe_unpack.py`, deleted after use, not committed):

```python
bash_res = BashResolution(decision="allow", reason="r", overrides=[])
file_res = FileResolution(decision="allow", reason="r", override=None, provenance=None)
a, b, c = bash_res   # raises
a, b, c = file_res   # raises
```

Actual traceback (both classes, verbatim):

```
Traceback (most recent call last):
  File ".../probe_unpack.py", line 15, in <module>
    a, b, c = obj
    ^^^^^^^
TypeError: cannot unpack non-iterable BashResolution object

Traceback (most recent call last):
  File ".../probe_unpack.py", line 15, in <module>
    a, b, c = obj
    ^^^^^^^
TypeError: cannot unpack non-iterable FileResolution object
```

`iter(obj)` also confirmed to raise `TypeError: 'BashResolution' object is not iterable` / `'FileResolution' object is not iterable` -- no escape hatch through any other protocol.

## Acceptance -- verbatim output

```
$ uv run python -m unittest discover -s test -t .
Ran 2333 tests in 21.353s

OK
```

(Baseline before any change: 2335 tests, OK. 2335 - 2 deleted pinning tests = 2333; the 2 architecture_fitness tests were renamed/updated, not deleted, so they still count.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.51s. End-to-end: 61 cases in 3.20s.

OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --predicates
=== R1: PASS ===
  verdict-ish types (5):
    - ResolvedDecision (config_types:329)
    - SubMatch (resolve:66)
    - BashResolution (resolve:96)
    - FileResolution (resolve:162)
    - Decision (tools.decision:46)
  __iter__ shims (0):
  (out of scope -- toolguard/parser/ is explicitly out of scope for TOO-45 per the execution plan: parser, parser.bash_parser, parser.command_extractor, parser.command_model, parser.multiline)
```

R1's `__iter__ shims` list is now empty, as required. (R2/R3/R5/R6 in the same `--predicates` run show pre-existing FAIL states unrelated to R1a -- out of this stage's scope, not touched.)

```
$ uv run ruff format .
1 file reformatted, 147 files left unchanged   # test_hard_deny.py -- line-wrap only, no logic change

$ uv run ruff check --no-cache .
All checks passed!
```

## Restoration / safety notes

Originals of `toolguard/resolve.py`, `test/unit/test_hard_deny.py`, `test/unit/test_hierarchical.py`, and `test/unit/test_resolve.py` were copied to `scratchpad/r1a-backups/*.orig` with sha256 recorded BEFORE any edit. `test/unit/test_architecture_fitness.py` is untracked (created during the prior R1b stage of this same ticket, before my session) and I edited it without backing it up first -- a process miss on my part; I backed up its post-edit state afterward as a safety net for the remainder of the session, but there is no pre-edit copy to restore from if that turns out to be wrong. No `git checkout`/`restore`/`stash`/`reset` was run at any point; only read-only git (`git status`, `git diff --stat`) was used. No commit was made. The repository was not copied. Nothing outside the repository was touched. Final `git status --porcelain` shows only the 4 intentionally-tracked files plus the pre-existing (not mine) uncommitted work from earlier TOO-45 stages -- verified by diffing scope against `git diff --stat` on the 4 tracked files and confirming no drift on the untracked one beyond my own edits.

## Elapsed time / cost estimate

No reliable start timestamp was captured at session start (a process gap -- should have run `date` as the first action). Based on the number and size of tool calls, the session ran roughly 30-40 minutes end to end:

- Phase 1 (planning, reading brief + scoping trace + resolve.py): ~8 min
- Phase 2 (implementation: independent caller search, shim deletion, docstring updates, 8 call-site conversions, 2 test deletions, 2 test updates): ~15 min
- Phase 3 (self-review: suite runs x4, corpus verify, guard, predicates, ruff, probe, git status audit): ~10 min
- Phase 4 (report + IDE open): ~5 min

Total estimated cost: low -- this was a Sonnet-tier subagent session with no large file rewrites, roughly 100K-150K tokens processed across reads/greps/edits. Estimated cost order of magnitude: **under $1** (a handful of moderate-sized tool calls, no long-running generation).

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- implements [[TOO-45 R1 scoping trace]]
