---
title: TOO-45 R1b2 tuple predicate report
type: note
permalink: toolguard/too-45/too-45-r1b2-tuple-predicate-report
tags:
- task-memory
- TOO-45
---

## New R1 baseline (the headline)

R1 goes back to **FAIL**, as expected and required by the brief. Before this task: `R1.pass == True` (verified by capturing `--predicates --json` before any edit). After: `R1.pass == False`, because `find_bare_verdict_tuples()` now finds **13 bare verdict-tuple-returning functions** on the real tree and R1's gate was extended to require zero of them, alongside the existing "exactly one RUNTIME verdict type" and "zero `__iter__` shims" conditions.

**All 13 hits, grouped by module (module::function:line -- basis):**

- `compound.py` (**6/6 -- the brief's hard requirement**):
  - `_resolve_leaf_detailed:237` -- literal decision-tuple return
  - `_resolve_leaf:421` -- delegates to a known verdict function
  - `_combine_strictest:647` -- literal decision-tuple return
  - `check_compound_permission:764` -- delegates to a known verdict function
  - `resolve_compound_permission_detailed:814` -- literal decision-tuple return
  - `resolve_compound_permission:952` -- delegates to a known verdict function
- `hook.py` (3/3, matching the trace's count exactly):
  - `_resolve_event:653`, `_handle_file_path_tool:1004`, `_handle_command_tool:1092` -- all literal decision-tuple returns
- `permissions.py` (2): `check_hard_deny:225`, `decide_command_at_level_detailed:388` -- both literal
- `resolve.py` (2, not named individually in the R1 scoping trace's prose but genuine, verified hits): `_decide_file_path_at_level_detailed:177`, `_check_file_path_hard_deny:281` -- both literal, both have NO return-type annotation at all (the literal signal alone is enough)

This is the new pre-registered target for R1d/R1e: **13, not 7 (the old class-only count) and not the trace's estimated 16.**

## Honest gap against the trace's "16"

The R1 scoping trace said "16 functions ... 6 in compound.py, 3 in hook.py, plus permission_resolution, permissions, and 4 in tooling" -- but that note does not enumerate the individual functions behind the last three terms, only approximate per-module counts (produced by reading + grep during a MEASURE-AND-PROPOSE pass, not a precise AST tool). My detector found:

- `permission_resolution.py`: **0** hits. Its only 3+-shaped-annotation candidate, `apply_parse_failure_floor`, returns a strict `(decision, reason)` **pair** (arity 2) -- correctly excluded per the brief ("a strict pair is fine and must NOT be flagged").
- `permissions.py`: **2**, matching what a "permissions" count of 2 out of the trace's implied 3 (permission_resolution + permissions) would suggest.
- `tools/` (tooling): **0**. I ran a full literal-decision-tuple-return scan (`return "allow"/"deny"/"ask", ...` arity >= 3) across the entire `toolguard/` tree, independent of my final detector, and it found zero hits anywhere under `toolguard/tools/` or `toolguard/scripts/`. I also checked every `Tuple[...]`-arity-3+ return annotation under `tools/` by hand (`tools/consolidate.py`'s `_check_family1_safe`/`_check_family2_safe` are `Tuple[bool, str]` -- the brief's own excluded "(ok, value) result" shape, arity 2 anyway; `tools/sorters.py:sort_layer_rules` is `Tuple[List[str], List[str], Optional[List[str]]]`, R2's own parallel-array target, first element not `str`). None qualify under either signal.

**I could not reconstruct which specific functions the trace's "4 in tooling" refers to**, and a targeted, exhaustive search of `tools/`, `scripts/`, and `permission_resolution.py` (both by literal-return and by annotation-shape) found none. Two honest possibilities: (a) the trace's estimate was approximate and slightly high, or (b) it counted something my two signals deliberately exclude (e.g. a `Tuple[bool, str]` ok/message pair, or a docstring mention with no actual bare-tuple construction). I am reporting 13 as the real, structurally-verified count rather than stretching the rule to reach 16 -- per the brief's explicit instruction to say so rather than force a number.

The 2 `resolve.py` hits I found (not named in the trace's per-module breakdown at all) are real, additional coverage beyond what the trace enumerated -- both `_decide_file_path_at_level_detailed` and `_check_file_path_hard_deny` literally `return "deny", ..., pattern` with no type annotation whatsoever, so the class-only predicate and even a naive annotation-only scan would both have missed them.

## Criterion chosen (and why), with what was rejected

Extended `tools/architecture_fitness.py` with `find_bare_verdict_tuples()`, combining two structural signals to a **fixpoint** -- deliberately not a hand-maintained function-name list, per the brief:

1. **Literal seed** (`_is_literal_decision_tuple`): a function with >= 1 `return` statement that is a tuple LITERAL, arity >= 3, first element a string constant in `{"allow", "deny", "ask"}`. Sufficient by itself, independent of any annotation.
2. **Delegation** (`_delegates_to_known_verdict`), computed to a fixpoint: a function whose return annotation is verdict-*shaped* (`_is_verdict_shaped_annotation`: `Tuple[...]`/`tuple[...]`/`Optional[Tuple[...]]`, arity >= 3, first element annotated exactly `str`) AND that returns, directly (`return other_fn(...)`) or via an unpack-then-partial-repack (`a, b, c, d = other_fn(...); return a, b, c`), the result of a call to a function ALREADY classified verdict. Iterated with a `while changed` loop because `compound.py`'s real chain needs **two rounds**: `resolve_compound_permission` only qualifies once `resolve_compound_permission_detailed` (a literal seed) is known; `check_compound_permission` only qualifies once `resolve_compound_permission` is known in turn.

**Both candidate signals from the brief were evaluated, not adopted blindly:**

- *Signal 1 (annotation + name mentions decision/verdict/reason)* -- rejected as the sole gate. The brief's own phrasing ("the function's name or the tuple's annotation mentions decision/verdict/reason") is itself a name-substring rule wearing an annotation disguise, exactly the failure mode `find_verdict_types` was already fixed away from (TOO-45 R1b). I replaced "mentions decision/verdict/reason in the name" with "first element annotated `str`" -- verified against the real tree to be precise enough on its own to exclude every OTHER fixed-arity 3+-tuple annotation in the codebase (`toml_scan._locate_subsection -> Optional[Tuple[int,int,int]]`, a parsed span; `tools.sorters.sort_layer_rules -> Tuple[List[str], List[str], Optional[List[str]]]`, R2's own target) -- but **not precise enough alone**: `log_writer._parse_discovery_line -> Optional[Tuple[str, str, List[str]]]` passes the shape check (first two elements are `str`) while carrying zero decision content (`(timestamp, project_root, levels)`). This is a REAL false positive risk on this actual tree, not a hypothetical -- confirmed by running the detector and finding it initially would have matched. That is why the annotation shape alone is only a *candidate* filter, never sufficient; decision evidence (signal 1 or delegation to a signal-1 function) is always required on top of it.
- *Signal 2 (first return element consistently a decision literal across ALL return statements)* -- rejected in its literal "all return statements" form. On the real tree, every wrapper function (`_resolve_leaf`, `resolve_compound_permission`, `check_compound_permission`, `decide_command_at_level_detailed`'s cascade-fallthrough) mixes a literal-decision return with a variable-based delegate return or a `return None` in the SAME function, so "all returns agree" would have under-counted `compound.py` to 3 of 6 (missing `_resolve_leaf`, `resolve_compound_permission`, `check_compound_permission` entirely) -- verified by hand-tracing each function's return statements before writing any code. The corrected form used here -- "at least ONE literal decision-tuple return is sufficient to seed the function, and a delegate-only wrapper still counts via propagation" -- is what actually reaches all 6.

## Requirements checklist against the brief

- Must flag the 6 in `compound.py`: **met**, verified by a real-tree regression test (`test_real_tree_flags_all_six_compound_functions`).
- Must not flag strict pairs: **met** structurally (`_VERDICT_TUPLE_MIN_ARITY = 3` excludes every arity-2 return before either signal even runs), verified on both a synthetic pair and two real-tree pairs (`permissions.check_permission`, `permission_resolution.apply_parse_failure_floor`).
- Must not flag non-verdict 3-tuples: **met**, verified against the real false-positive risk (`log_writer._parse_discovery_line`, a timestamp/root/levels triple) both synthetically and on the real tree.
- Report grouped by module, function + line, matching the existing predicate style: **met** -- `render_predicates_text` now prints a `bare verdict-tuple returns (N)` section grouped by module, each entry `function():line -- basis`.
- R1 pass gate includes it: **met** -- `compute_predicates()["R1"]["pass"]` is now `len(runtime types)==1 and len(shims)==0 and len(bare_verdict_tuples)==0`.
- Honest count, not stretched to 16: **met** -- see the gap section above.

## Files changed

- `tools/architecture_fitness.py` -- added `_VERDICT_TUPLE_DECISION_LITERALS`, `_VERDICT_TUPLE_MIN_ARITY`, `_tuple_elements`, `_is_verdict_shaped_annotation`, `_is_literal_decision_tuple`, `_call_target_name`, `_delegates_to_known_verdict`, `find_bare_verdict_tuples`; wired the result into `compute_predicates()`'s `R1` dict (`bare_verdict_tuples` key, folded into `pass`) and into `render_predicates_text()`'s R1 section (grouped-by-module rendering). No other predicate touched.
- `test/unit/test_architecture_fitness.py` -- new `TestFindBareVerdictTuples` class (10 tests: literal seed, strict-pair exclusion, non-verdict-3-tuple exclusion mirroring the real `_parse_discovery_line` risk, two-round delegation chain, an unrelated-wrapper negative case, generated-file exclusion, out-of-scope-package exclusion, and three real-tree pins -- all 6 compound.py functions, all 3 hook.py functions, and the two real non-flagged functions). `TestComputePredicates` gained `bare_verdict_tuples` to the assembled-keys assertion and a new test asserting R1's gate is `False` on the real tree with >= 6 compound.py hits present.
- No production file under `toolguard/` was touched -- confirmed both by tool-call audit (only `Read` was used on `toolguard/*.py` this session) and by `git diff --stat` showing the pre-existing uncommitted `toolguard/*.py` changes are unchanged by this session's `ruff format .` run (it reformatted exactly the 2 files listed above, 146 left unchanged).

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2349 tests in 23.581s
OK

$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.26s. End-to-end: 61 cases in 3.28s.
OK: no differences.

$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook

$ uv run python tools/architecture_fitness.py --predicates
=== R1: FAIL ===
  ...
  bare verdict-tuple returns (13) -- functions returning a (decision, reason, ...) tuple, never a class, grouped by module:
    compound: [6 functions listed]
    hook: [3 functions listed]
    permissions: [2 functions listed]
    resolve: [2 functions listed]

$ uv run ruff format . && uv run ruff check --no-cache .
2 files reformatted, 146 files left unchanged   (tools/architecture_fitness.py, test/unit/test_architecture_fitness.py)
All checks passed!
```

Test count before this task: 2325 (per the R1 scoping trace baseline) plus tests added by intervening R1a/R1c/R3 stages already in the uncommitted tree; after this task: 2349 (net +11 test methods from this task specifically: 10 in `TestFindBareVerdictTuples`, 1 new test in `TestComputePredicates`, plus 1 new assertion in an existing test).

## Self-review

- Anti-pattern scan: no async/await, no threading, no local imports introduced. Type hints present throughout new code. Docstrings on every new function, following this file's existing verbose-rationale convention (structural signals stated in code, false positives named explicitly, propagation chain traced against the real functions it needs to reach).
- Duplication check: no existing helper in this file or the stdlib already does tuple-annotation/literal-tuple structural classification; `_class_field_names`/`_class_field_type_sources` are the closest precedent (class-field based, not applicable to function returns) and were consulted for style consistency, not reused directly since the AST shapes differ (ClassDef fields vs FunctionDef returns).
- Ran `uv run python -m unittest discover -s test -t .` before starting (implicitly verified via the R1 scoping trace's own restoration statement: 2,325 OK at that point) and repeatedly after each meaningful change; final run is 2,349 OK.
- `uv run ruff format .` and `uv run ruff check --no-cache .` both clean.
- `uv run python tools/architecture_fitness.py --guard` PASS, 12 canaries -- confirms no out-of-scope file touch, no test-count shrink, no new dependency, no lint/format regression.

## Elapsed time and estimated cost (Sonnet 5, dev-tool self-estimate)

Timestamps were not captured at the start of the session, so these are reconstructed estimates from the tool-call sequence, not exact measurements:

- **Phase 1 (planning/investigation)** ~25 min -- reading the brief, the R1 scoping trace memory note, the existing `architecture_fitness.py` predicate machinery and its test conventions, and (the bulk of the time) manually tracing every candidate 3+-tuple return across `compound.py`, `hook.py`, `permissions.py`, `permission_resolution.py`, `resolve.py`, and `tools/` by hand -- necessary to design a criterion that actually reaches all 6 `compound.py` functions before writing any code, per this task's own "enumerate the state space before implementing" instruction.
- **Phase 2 (implementation)** ~12 min -- writing the detector, wiring it into `compute_predicates`/`render_predicates_text`.
- **Phase 3 (testing/self-review)** ~10 min -- writing the 11 new/changed tests, running the full suite, `corpus_build --verify`, `--guard`, `ruff format`/`check`, re-verifying after the format pass.
- **Phase 4 (report/handoff)** ~5 min.
- **Total: ~50 minutes.**

Estimated token cost: this session made heavy use of Read/grep/Bash for investigation (large file reads of `compound.py`, `hook.py`, `permissions.py`, `resolve.py`, plus the R1 scoping trace note itself, ~15K+ tokens of source alone) plus moderate code generation (~400 new lines across the two files). Rough order-of-magnitude estimate at Sonnet pricing: **$1.50-$2.50** for the session (input-heavy from investigation, moderate output from code+tests+this report). This is a coarse estimate, not a metered figure.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- extends [[TOO-45 R1 scoping trace]]
- informs [[TOO-45 decision log]]
