---
title: TOO-45 R6-S1 private reaches report
type: note
permalink: toolguard/too-45/too-45-r6-s1-private-reaches-report
tags:
- task-memory
- TOO-45
---

Implements S1 of the R6 replacement plan (`toolguard-memories/TOO-45/reports/r6-reassessment.md`), closing the 5 real private reaches S0's rewritten detector reported (`TOO-45/TOO-45 R6-S0 instrument fix report`). Companion: `TOO-45/TOO-45 R6-S1 private reaches coder task recall` (not yet written as a separate file -- captured here since the task was small enough to run start to finish without a mid-task compaction risk).

## Verification before deleting anything (grep, not the S0 report's word alone)

Re-ran the consumer check myself rather than trusting the prior report's claim:

- `_anchor_file_pattern`: real consumers, all test-only -- `test_hierarchical.py:522,535,548,562` (`from toolguard.hook import _anchor_file_pattern`, local imports inside 4 test methods).
- `_check_file_path_hard_deny`: **zero** real consumers -- the only other hits are a docstring cross-reference in `permission_resolution.py` and three prose mentions in `config_types.py`, none of them a live import.
- `_decide_file_path_at_level_detailed`: one real consumer -- `test_hook.py:28` (module-level import) plus a docstring cross-reference at line 77.
- `_match_file_path_pattern`: **zero** real consumers -- only docstring/comment mentions in `resolve.py` itself.
- `tools.takeover_audit:91 -> config._strip_tool_wrapper`: real, two call sites (`_get_blanket_allows_in_native`, `_has_any_blanket_allow_in_native`), both operating on raw native-settings permission strings, not `RuleEntry` objects.

Confirms the S0 report's inventory exactly. All five closed.

## What changed

**`toolguard/hook.py`** -- deleted all four `# noqa: F401` re-exports from the `toolguard.resolve` import block. No replacement re-export added, per the instruction. `hook.py` itself never used any of the four names in its own body (grep confirmed after the edit).

**`test/unit/test_hierarchical.py`** -- repointed all four local `from toolguard.hook import _anchor_file_pattern` imports to `from toolguard.resolve import _anchor_file_pattern` (the function's actual home). No other change; the surrounding Given/When/Then prose already names the function, not a module, so nothing else was stale.

**`test/unit/test_hook.py`** -- moved `_decide_file_path_at_level_detailed` out of the `from toolguard.hook import (...)` block and into the existing `from toolguard.resolve import (...)` block (alongside `resolve_bash_permission_detailed`). Fixed the one stale docstring cross-reference (`check_file_path_permission`'s docstring said `:func:`toolguard.hook._decide_file_path_at_level_detailed`` -- now says `toolguard.resolve`).

**`toolguard/tools/takeover_audit.py`** -- this is the one that needed a real design decision, not a re-point. See below.

**`toolguard/rule_entry.py`** -- added a new public function, `strip_tool_wrapper`, immediately after `is_tool_wrapper` (same module, same section). It is a one-line delegation to the existing private `_strip_tool_wrapper`; `_strip_tool_wrapper` itself is untouched and still used internally by `RuleEntry.stripped_pattern` and `config_types.py`.

**`toolguard/config.py`** -- deleted the `_strip_tool_wrapper` re-export (`from toolguard.rule_entry import _strip_tool_wrapper as _strip_tool_wrapper`), since its own comment said it existed *only* so `takeover_audit`'s import kept working, and that import is now gone. Rewrote the surrounding block comment to drop the now-false claim and record the R6-S1 change. Fixed one now-imprecise docstring cross-reference in `wrap_tool_pattern` (`:func:`_strip_tool_wrapper`` -> fully qualified `:func:`~toolguard.rule_entry._strip_tool_wrapper``, since the name is no longer locally defined or re-exported in this file).

**`test/unit/test_architecture.py`** -- `TestReExportIdentity.test_leaf_type_reexports_resolve_to_their_leaf_modules` asserted `config._strip_tool_wrapper is rule_entry._strip_tool_wrapper` (a re-export identity check, one of 4 names in a tuple). That re-export no longer exists, so the assertion is now simply false as a fact about the code, not a claim I disagree with. Removed `_strip_tool_wrapper` from the checked tuple (leaving `Issue`, `RuleEntry`, `is_tool_wrapper`) and added a docstring paragraph explaining why -- pointing at this exact change. This is the one test edit in this task the general "don't modify existing tests" rule would normally stop me on; I judged it in-scope because it's the direct, unavoidable consequence of the deletion the task explicitly required (deleting a re-export whose only purpose was serving an import this task also explicitly required removing), and I did not touch the test's actual verification logic (`assertIs` identity check) or weaken what it verifies for the three names that remain real. Flagging it here explicitly rather than treating the earlier "point a test at the module that actually defines it" instruction as blanket cover for it.

## The call-intent / SRP check (asked for explicitly, not skipped)

`_get_blanket_allows_in_native` and `_has_any_blanket_allow_in_native` in `takeover_audit.py` strip the `Tool(...)` wrapper off **native Claude settings permission strings** read straight out of `layer.content["permissions"]["allow"]` -- plain `str` elements of a `settings.json`/`settings.local.json` list, never parsed into a `RuleEntry`. `RuleEntry.stripped_pattern` requires an actual `RuleEntry` instance, and constructing one (`RuleEntry(pattern=perm)`) purely to reach a one-line string transform would be wrong on call-intent grounds, not just data-shape: `RuleEntry` models a *toolguard* rule -- pattern plus enrichment metadata plus raw-source round-tripping plus the `synthesized_pattern` write-guard flag -- and a native settings permission string is a different domain object that happens to share the same `Tool(...)` wrapper syntax. Wrapping one in the other's type to borrow a single accessor would be exactly the kind of accumulated, not-designed coupling the reassessment warns about for a facade -- so I did not do it.

Zoomed out one more level: is "strip the tool wrapper off a pattern" a responsibility `takeover_audit.py` should own, rather than call? No -- and the existing code already had this right. `rule_entry.py`'s own module docstring documents that the wrapper-stripping regex was deliberately centralized there (moved out of `config.py` in TOO-19 Phase 0a) specifically so it lives in exactly one place and any consumer -- toolguard's own rule parsing, or an auditor reading native settings syntax, which uses the identical `Tool(...)` shape -- calls the same structural rule rather than re-deriving it. `takeover_audit.py`'s job is auditing invariants over already-loaded config data; it correctly does not own pattern-syntax parsing, and never did. The only defect was encapsulation (reaching a private name of a module it doesn't otherwise depend on), not placement of responsibility. So the fix is exactly what it looks like: give the leaf module's existing public/private split (`is_tool_wrapper` was already public; `_strip_tool_wrapper` wasn't) its missing symmetric member, and have the tooling-layer caller use the public one directly from the module that actually defines it, rather than through `config`'s re-export. No responsibility moved; only visibility.

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2402 tests in 32.950s
OK
```

(First run after the takeover_audit/hook/rule_entry/config edits, before touching `test_architecture.py`, showed exactly 1 failure -- `test_leaf_type_reexports_resolve_to_their_leaf_modules`, `AttributeError: module 'toolguard.config' has no attribute '_strip_tool_wrapper'` -- which is the test edit described above. Second run, after that edit: 2402/OK.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.22s. End-to-end: 61 cases in 3.34s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --predicates
=== R6: PASS ===
  guarded layers: config, engine (14 modules, derived from .pyscn.toml)
  checked layers: tooling, runtime
  known limitations of this detector: [unchanged, 4 items -- see S0 report]
```
(R1, R2, R3, R5 also all PASS, unchanged by this stage. `--predicates` process exit code: 0.)

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (1):
  - hook (runtime) -> tools.decision (tooling) at line 700 [local import]
```
(`--layers` process exit code: 1 -- expected and unrelated to S1. This is the pre-existing `decide()`-lives-in-tooling violation the reassessment names as S2's job, not S1's. R6-as-a-predicate now PASSES; the plan's own note that R6 "may still FAIL" refers to this separate `--layers` check and to `Decision`/`RuntimeVerdict` unification (S3), neither of which S1 touches. Reporting both readings honestly: **the R6 private-reach predicate now passes; the layer-direction check does not, by design of this stage's scope.**)

```
$ uv run ruff format .
150 files left unchanged
$ uv run ruff check --no-cache .
All checks passed!
```

`uv run python -m py_compile` clean on all seven touched files.

## Files touched (7)

- `toolguard/hook.py` -- deleted 4 re-exports
- `toolguard/config.py` -- deleted 1 re-export + comment/docstring cleanup
- `toolguard/rule_entry.py` -- added 1 new public function (`strip_tool_wrapper`)
- `toolguard/tools/takeover_audit.py` -- import + 2 call sites repointed to the new public function
- `test/unit/test_hierarchical.py` -- 4 local imports repointed hook -> resolve
- `test/unit/test_hook.py` -- 1 import repointed hook -> resolve, 1 docstring fixed
- `test/unit/test_architecture.py` -- 1 test's checked-name tuple updated (see disclosure above), docstring updated to explain

No new files. No test deleted; one test's assertion scope narrowed by exactly the name whose re-export this task required removing, with the change disclosed above rather than folded in silently.

## Self-review notes

- No async/await, no threading. The local imports in `test_hierarchical.py`/`test_hook.py`'s docstring-adjacent code are pre-existing style in those exact spots (function-local imports inside individual test methods, already present before this task) -- I repointed their target module, I did not introduce a new local-import site or change the pattern.
- Backups: all seven original files' bytes were copied to `/tmp/claude-1000/.../scratchpad/r6-s1-backups/` with a `sha256sum` manifest, written before any edit.
- Grepped the whole repo (`toolguard/`, `test/`, `tools/`, `docs/`, `README.md`, `AGENTS.md`, `llms.txt`) for stale references to all five removed/renamed symbols after editing -- clean; no doc drift found needing a fix beyond the two docstring cross-references already corrected above.
- Did not touch `test/unit/test_architecture_fitness.py` or `tools/architecture_fitness.py` -- both show as modified in `git status` from S0's prior work, not from this session.

## Time and cost (estimated)

| phase | elapsed | est. cost |
|---|---|---|
| Phase 1: read shared-context/reassessment/S0 report, verify consumer claims by grep | ~10 min | ~$0.35 |
| Phase 2: implementation (7 files, backups first) | ~10 min | ~$0.45 |
| Phase 3: self-review + acceptance run (test suite x2, corpus, predicates, layers, ruff, repo-wide grep sweep) | ~8 min | ~$0.35 |
| Phase 4: report | ~3 min | ~$0.10 |
| **Total** | **~31 min** | **~$1.25** |

(Sonnet-class pricing, rough token-based estimate, not a billing record. Elapsed times are approximate -- reconstructed from backup-file and log timestamps, not a continuous clock log.)
