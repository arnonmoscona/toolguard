---
title: TOO-45 compound-resolve cycle - plan B
type: note
permalink: toolguard/too-45/reports/compound-cycle-plan-b
tags:
- task-memory
- TOO-45
- plan
---

# TOO-45 compound <-> resolve cycle: plan B

## Verdict up front

**Remove the cycle. It is cheap, and the ASK floor does not move.**

The callback exists for exactly one reason: `compound` has to decide *which string to resolve* (the PEG sub-commands of a leaf, or the truncated outer-command stub of an inline/heredoc leaf) before anything can be resolved, and that decision is decomposition knowledge. Turn "which strings to resolve" into **data on the decomposition result** and the callback's whole reason for existing evaporates. The floor, the wording, the strictest-wins combine, the fallback branches -- all the security-relevant code -- stay exactly where they are, unmoved and untouched, in `compound`. What is deleted is plumbing: two callback protocol types (`ResolveOuterProbe`, `RecordUnitVerdict`), two closures in `resolve.py`, one 7-tuple, one 5-tuple, one 3-tuple, and roughly ninety lines of docstring whose only job is to explain the side-channel.

The accepted fallback (rename to `resolution_strategy`, type it `Callable[[str], UnitVerdict]`) fixes aggravating factor #1 and nothing else. It cannot fix `record_unit`, which is the part that actually hurts: a callee mutating the caller's list through a *second* callback is not a strategy pattern, and no amount of typing makes it one. See "Why not the fallback" at the end.

## Target design

Three pure functions in `compound`, and an explicit loop in `resolve`.

### What crosses the boundary

Request direction: `str` (a command to decide). Return direction: `UnitVerdict` (already exists, already carries `decision`/`reason`/`matched_rule`/`provenance`/`additional_context`/`fallback_kind` -- i.e. every field the lossy 3-tuple dropped and the `ResolveOuterProbe` 5-tuple was invented to smuggle back). No new verdict type. `ResolveOuterProbe` disappears not because it is widened but because `UnitVerdict` already *is* the wide version of it.

### One new type

```python
@dataclass(frozen=True)
class CommandUnit:
    """One decidable element of a compound command line, in extraction order.

    Produced by :func:`decompose`; consumed by :func:`judge_unit`. Carries the
    element's own text plus the command strings a rule engine must decide on
    its behalf -- so a caller can resolve them without compound calling back.
    """

    text: str                  # the unit's real, full source text (-> UnitVerdict.sub_command)
    kind: str                  # 'plain' | 'inline_code' | 'undecidable' | 'unknown'
    parts: Tuple[str, ...]     # command strings to resolve, in order
    note: Optional[str] = None # UndecidableSegment.reason; None for every other kind
```

`parts` by kind: `plain` -> `extract_commands(leaf.text)` (0, 1, or many); `inline_code` -> exactly one element, the **untruncated** `_extract_outer_command(leaf.text)` stub; `undecidable` / `unknown` -> empty.

### Three functions in `compound`

```python
def decompose(command: str) -> List[CommandUnit]:
    """Split a command line into decidable units. Pure structure -- decides nothing."""

def judge_unit(unit: CommandUnit,
               part_verdicts: List[UnitVerdict],
               undecidable_fallback: str = "ask") -> UnitVerdict:
    """Verdict for ONE unit, given what the rules said about its parts.

    Owns the ASK floor for inline/heredoc foreign code and the
    undecidable_fallback floor -- byte-identical branches and wording to
    _resolve_leaf_detailed's today. part_verdicts must be in unit.parts order
    and the same length.
    """

def _combine_strictest(unit_verdicts: List[UnitVerdict]) -> RuntimeVerdict:
    """Unchanged logic; now takes UnitVerdicts instead of 5-tuples."""
```

`decompose` is `[_unit_for(e) for e in extract_structured(command)]`, where `_unit_for` is a ten-line mapping over the two parser types. `judge_unit` is `_resolve_leaf_detailed`'s body with `probe(outer_cmd)` replaced by `part_verdicts[0]` and the `for cmd in sub_commands: resolve_one(cmd)` loop replaced by iterating `part_verdicts`, plus the `UndecidableSegment` branch lifted in from `resolve_compound_permission_detailed` (it belongs beside the other floor branch, not in the driver). Every `record_unit(...)` call inside it is deleted; the caller records.

The 5-tuple `(decision, reason, leaf_text, context, fallback_kind)` that `_combine_strictest` takes today is field-for-field `UnitVerdict.(decision, reason, sub_command, additional_context, fallback_kind)`. Switching it to `List[UnitVerdict]` is a free deletion of a lossy tuple, and it is what makes the driver loop below read as one line.

### What `resolve.py` does

`_decide` (already factored out, already pure) stops returning a 7-tuple and returns a strict pair -- allowed by convention, and not flagged by `find_bare_verdict_tuples` (there is a real-tree test pinning that strict pairs are not flagged):

```python
def _decide(sub_command: str) -> Tuple[UnitVerdict, Optional[ConflictOverride]]:
    """Pure per-sub-command decision: hard-deny first, then the cascade. Records nothing."""
```

`_resolve_one`, `_resolve_outer` and `_record_unit` are deleted outright. The single `resolve_compound_permission_detailed(...)` call becomes:

```python
unit_verdicts: List[UnitVerdict] = []
for unit in decompose(command):
    part_verdicts = []
    for part in unit.parts:
        verdict, override = _decide(part)
        part_verdicts.append(verdict)
        if unit.kind == "plain" and verdict.decision == "allow" and override is not None:
            overrides.append((part, override))
    judged = judge_unit(unit, part_verdicts, config.resolved_undecidable_fallback())
    unit_verdicts.append(judged)
    # A plain unit's audit entries are its own sub-commands. A floored or
    # undecidable unit is audited as ONE entry, because the floor -- not any
    # part's rule match -- is what decided it (TOO-45 R1e).
    if unit.kind == "plain":
        sub_matches.extend(part_verdicts)
    else:
        sub_matches.append(judged)
combined = _combine_strictest(unit_verdicts)
```

That is the whole orchestration, in one place, readable top to bottom, with `sub_matches` and `overrides` populated by ordinary `append`/`extend` on lines you can see. No closure, no callback, no side-channel. Everything downstream (`apply_parse_failure_floor` at the compound boundary, `_deciding_sub_match`, the final `RuntimeVerdict` construction) is untouched.

### The legacy driver stays, and it is not a cycle

`check_compound_permission`, `resolve_compound_permission`, `resolve_compound_permission_detailed` and `_resolve_leaf` are called by ~40 test sites and by the pattern-list API, all with a 3-tuple `resolve_one` closure. They stay, reimplemented as a ten-line driver over the same three primitives, so no policy is duplicated and drift is impossible:

```python
def resolve_compound_permission_detailed(command, resolve_one, undecidable_fallback="ask"):
    """Convenience driver for callers with no UnitVerdict-producing resolver.

    Used by check_compound_permission (which closes over permissions.check_permission)
    and by tests. The production path (resolve.py) does NOT use it -- it drives
    decompose/judge_unit/_combine_strictest directly.
    """
    verdicts = [
        judge_unit(unit, [_unit_from_tuple(p, resolve_one(p)) for p in unit.parts],
                   undecidable_fallback)
        for unit in decompose(command)
    ]
    return _combine_strictest(verdicts)
```

`_unit_from_tuple(part, (decision, reason, context))` builds a `UnitVerdict` with `matched_rule=None`, `provenance=None`, and `fallback_kind=fallback_kind_for_reason(decision, reason)` -- which is exactly what today's `lambda cmd: (*resolve_one(cmd), None, None)` fallback probe already does, and it confines the text-based `fallback_kind_for_reason` heuristic to the one caller that genuinely has only text. `resolve_outer` and `record_unit` are deleted as parameters; no test passes them (verified: only `resolve.py` does).

Crucially this is **not** the cycle coming back. The cycle is specifically `resolve -> compound -> resolve`. `compound -> permissions` is a one-way edge; `test -> compound` is not an architectural edge at all. After the change, profiling one real decision shows `resolve -> compound` and `compound -> parser/permissions` and nothing returning.

## Where the ASK floor ends up, and why

**It stays in `compound`, in `judge_unit`. It does not move an inch, and neither does its wording.**

That is the crux answer, and it is deliberate rather than lazy. Three reasons, in order of force:

1. **`compound` has a second caller that never touches `resolve.py`.** `check_compound_permission` resolves against raw pattern lists via `permissions.check_permission`. If the floor moved into `resolve.py`, that caller -- and roughly forty tests that exercise the floor through `resolve_compound_permission` -- would either silently lose the floor (a fail-open security regression) or force a second implementation of it. A floor with two implementations is precisely the defect TOO-45 D4 already fixed once in this same file.
2. **The floor is triggered by parser facts, not rule facts.** `leaf.ask_floor` and `UndecidableSegment` come from the grammar layer. `compound` is the module that reads them; `resolve.py` is the module that knows about rules, levels, provenance and hard-deny pools. "This fragment is foreign inline code, so no allow may stand unexamined" is a statement about the *shape* of the command. Moving it into `resolve.py` would make the rules module the god module and would put ~150 lines of reason-string composition next to provenance plumbing.
3. **Nothing about the floor required the callback.** Re-read `_resolve_leaf_detailed`'s ask-floor branch: it needs the *result* of resolving the stub, not the *ability* to resolve it. Once `decompose` publishes the stub as `unit.parts[0]`, the caller resolves it and hands the result in. The floor becomes a pure function of `(unit, part_verdicts, fallback)` -- same branches, same order, same strings.

Because the floor does not move, its existing tests do not change, its wording does not churn, and the security review surface of this refactor is "did every unit still reach `judge_unit` with the right `kind`", which is a ten-line function and one new unit test.

The one thing that *does* move out of `judge_unit` is the `record_unit(unit)` call at the end of each floor branch -- the recording, not the deciding. That is the correct split: deciding is policy (compound), recording is bookkeeping for the caller's own audit list (resolve).

## `UndecidableSegment` handling (R1e)

An undecidable segment becomes `CommandUnit(text=segment.original, kind="undecidable", parts=(), note=segment.reason)`. `judge_unit` receives an empty `part_verdicts` list, applies `_apply_undecidable_floor("allow", undecidable_fallback)` exactly as today, builds the same four reason strings from `note`, and returns a `UnitVerdict` with `matched_rule=None`, `provenance=None`, and `fallback_kind` in `{'warned','silent','denied',None}`.

Note what this stops being: today "an `UndecidableSegment` never calls `resolve_one`, so it has no path onto `sub_matches`, so it needs a special `record_unit` call the leaf path does not need" is a special case that has to be explained (and it was, at length, after having been a real audit-loss defect). In the new shape it is not a special case at all -- it is simply a unit with zero parts, and the caller's recording branch (`kind != "plain"` -> append the judged verdict) covers it by the same rule that covers an ask-floor leaf. **The R1e fix stops being a patch and becomes a consequence of the structure.** That is the single biggest comprehensibility gain in this plan.

The `unknown` kind preserves the unreachable defensive branch (`logger.warning` + an `ask` verdict) rather than deleting it.

## How `sub_matches` is populated

By `append`/`extend` in the loop above, in `resolve.py`, in one place, on visible lines. No closure captures it; nothing outside `resolve_bash_permission_detailed` can touch it.

**Ordering** is guaranteed structurally: `decompose` preserves `extract_structured`'s order, `unit.parts` preserves `extract_commands`' order, and the loop appends as it goes. `diff <(cat a) <(cat b) && ls -la` decomposes to `[undecidable(diff ...), plain(ls -la)]` and records two entries -- the judged undecidable verdict, then `ls -la`'s own part verdict -- in that order. Every leaf and every segment gets at least one entry; a plain leaf gets one per PEG sub-command. This matches today's behaviour exactly, and unlike today it can be read off the loop rather than reconstructed from three call sites in another module.

## Behaviour preservation

**Must be byte-identical** (guarded by 6,401 in-process + 61 end-to-end golden cases, `uv run python tools/corpus_build.py --verify --strict-prose`):

- `RuntimeVerdict.decision` for every case (hard invariant).
- `reason`, `additional_context`, `provenance`, `matched_rule` (the corpus's TRACKED_FIELDS -- run with `--strict-prose` so a prose diff fails the build rather than printing for review).
- The end-to-end `hookSpecificOutput` payload, including presence/absence of the `additionalContext` key.
- Every reason string built by the floor branches: the four inline/heredoc strings and the four undecidable-segment strings, verbatim.
- `sub_matches` content (`sub_command`, `decision`, `matched_rule`, `provenance`, `fallback_kind`, `reason`) **and order**. This is *not* in the corpus goldens -- see step 0, which adds the characterization test that pins it before anything is touched.
- Which strings get resolved, and how many times: `plain` parts resolve exactly the PEG sub-commands, `inline_code` resolves exactly the untruncated outer stub once. Tests that count or capture resolver calls keep passing unchanged.
- `overrides`: still recorded only for allowed `plain` parts, never for an ask-floor stub probe.

**Legitimately changes** (state these to the reviewer; both should be invisible):

1. For a `plain` part, the `fallback_kind` `judge_unit` sees is now the **structural** one `_decide` computed (`allow` + `matched_rule is None` -> `warned`/`silent`), rather than one re-derived from the reason text by `fallback_kind_for_reason`. These agree for the real resolver by construction, and the structural one is the value that TOO-19 code review M1 argued for in the first place; the text heuristic survives only in the legacy tuple adapter, which genuinely has nothing else. If any prose diff appears in the corpus, this is the first suspect -- investigate, do not regenerate goldens.
2. The unreachable `unknown` extraction branch now also contributes one `sub_matches` entry (today it contributes a verdict but no record). Unreachable by construction (`extract_structured` returns exactly two types); called out for honesty.

Nothing else changes. In particular: the second, compound-boundary application of `apply_parse_failure_floor` in `resolve.py` stays exactly where it is -- it is the only thing covering an undecidable-segment-only command line, and removing it as "redundant" would silently reopen a fail-open bypass.

## Step order (every step leaves the suite green)

0. **Characterization test for `sub_matches`** (test-only; no production change). Pin `(sub_command, decision, matched_rule, fallback_kind)` in order for: a single plain command; a multi-part plain leaf (`git status && ls`); a multi-leaf multi-line command; an ask-floor leaf under each of the four `undecidable_fallback` values; `diff <(cat a) <(cat b) && ls -la` (two entries); a hard-denied sub-command. The corpus does not cover `sub_matches`; this test is the actual safety net for the rest of the plan, and it is worth keeping afterwards.
1. **`_combine_strictest` takes `List[UnitVerdict]`.** Update its two call sites to build `UnitVerdict`s (using `dataclasses.replace` for the deny/ask pre-formatted reasons). Internal to `compound`. Kills the 5-tuple.
2. **Add `CommandUnit` + `decompose`.** Rewrite `resolve_compound_permission_detailed`'s body to iterate `decompose(command)` and dispatch on `unit.kind`, still calling `resolve_one` / `resolve_outer` / `record_unit` exactly as today. Pure restructure with the callbacks intact -- the mechanically riskiest step, isolated with nothing else in it.
3. **Extract `judge_unit`.** Move `_resolve_leaf_detailed`'s body and the `UndecidableSegment` branch into it, with no callbacks: the driver resolves `unit.parts` first (via `resolve_one` for a plain unit, `resolve_outer` for an `inline_code` unit) and passes the results in; the driver, not `judge_unit`, calls `record_unit`. Re-point `_resolve_leaf` at `_unit_for(leaf)` + `judge_unit`.
4. **`resolve.py` drives it directly.** `_decide` returns `(UnitVerdict, Optional[ConflictOverride])`; delete `_resolve_one`, `_resolve_outer`, `_record_unit`; add the explicit loop. **The cycle is gone at the end of this step** -- verify with the same `sys.setprofile` run that found it.
5. **Delete `resolve_outer` / `record_unit` parameters** from `compound`'s public functions and reduce the legacy driver to the ten-line adapter loop. Removes ~90 lines of docstring describing a mechanism that no longer exists.
6. **Docstring sweep.** `resolve._deciding_sub_match` and `resolve_bash_permission_detailed`, `config_types.UnitVerdict` / `RuntimeVerdict` (both reference `record_unit` and "recorded as a SIDE EFFECT"), `hook.py`'s comment at ~495, `compound`'s module docstring. These are load-bearing in this codebase; leaving them stale would cost more than the refactor gains.
7. **Verify:** full `unittest` suite; `tools/corpus_build.py --verify --strict-prose`; `uv run python -m unittest test.unit.test_architecture_fitness` (R1's `bare_verdict_tuples` must stay empty and R1 `pass` must stay `True`); `uv run ruff format . && uv run ruff check .`.

Abandonable at any boundary: after step 1 the lossy 5-tuple is gone; after 3 the decomposition and the floor are named, pure and independently testable; after 4 the cycle is gone; 5-6 are cleanup.

## Effort estimate

**3-5 hours** for one careful implementer, plus a review pass. Concretely: `compound.py` ~250 lines touched, of which ~150 are code physically moved without edit and ~90 are docstring *deletion*; `resolve.py` ~100 lines touched; test churn near zero because `_resolve_leaf`, `resolve_compound_permission`, `check_compound_permission`, `_combine_strictest`'s name, `_extract_outer_command`, `_apply_undecidable_floor`, `_accumulate_contexts` and `cap_context_words` all survive with their existing signatures (verified against `test/unit/test_compound.py`'s import list and the ~40 call sites). New tests: step 0's characterization test, plus ~4 small tests for `decompose` and `judge_unit` -- which are the first units of this logic that can be tested without writing a fake resolver.

The estimate being small is the point. If an implementer finds themselves at eight hours, the design has drifted and they should stop and say so.

## What gets HARDER

Honest list, not a formality.

1. **Two hops instead of one for the leaf path.** To answer "what happens to `git status && ls`" you now read `decompose`, then the loop, then `judge_unit`, where today you read `_resolve_leaf_detailed`. Mitigation: the loop is twelve lines and sits at the only place that matters. Net I judge this a wash at worst, because the current single function is only "one hop" if you already know what the three injected callables do -- which requires reading the other module anyway.
2. **A new positional invariant across a module boundary**: `part_verdicts` must be in `unit.parts` order and the same length. This class of bug cannot exist today (the callback resolved and consumed in the same expression). Mitigation: `judge_unit` raises `ValueError` on a length mismatch, with a test. Cheap, and a loud failure rather than a silent misattribution.
3. **One more type.** `CommandUnit` is a third representation of "a piece of a command line", alongside `LeafCommand` and `UndecidableSegment`. I considered avoiding it -- have `decompose` return the parser's own elements plus two accessor functions (`parts_to_resolve(element)`, `records_own_parts(element)`) -- and rejected it: two accessors read worse at the call site than one object with four visible fields, and the parser types deliberately do not know about "strings a rule engine should decide". The cost is real; I think it is the cheaper of the two.
4. **Two eight-line drivers** (the production loop in `resolve.py`, the legacy adapter in `compound.py`). They cannot diverge in *policy* -- both call the same `decompose`/`judge_unit`/`_combine_strictest` -- but they could diverge in *orchestration* (e.g. someone adds a step to one). Mitigation: a cross-reference comment in both, and the legacy one is deliberately written as a single comprehension so there is visibly nowhere to hide a step.
5. **Coverage of the new adapter.** `_unit_from_tuple` is new code on the legacy path; it needs its own small test rather than relying on transitive coverage.

## Risks

**The ASK floor is security-relevant; these are the failure modes that matter.**

- **R1 -- `ask_floor` lost in translation (FAILS OPEN, most serious).** If `decompose` mis-maps a `LeafCommand(ask_floor=True)` to `kind="plain"`, the leaf is PEG-split and resolved normally, so `python -c "<anything>"` could be allowed outright by a `python *` rule. Mitigations: the mapping is a single `if leaf.ask_floor` in a ten-line function; add a direct test asserting `decompose('python -c "import os"')[0] == CommandUnit(text=..., kind="inline_code", parts=("python -c",))`; the existing floor tests in `test_compound.py` cover it end-to-end under all four fallback values; step 0's characterization test pins the resulting `sub_matches`.
- **R2 -- resolving a truncated stub.** `_extract_outer_command` deliberately does *not* length-truncate, because truncating before matching would weaken explicit-deny detection; only `_truncate_for_display` truncates, at render time. `parts` must carry the **untruncated** stub and `judge_unit` must keep doing the display truncation itself. `test_compound.py` already has a test class for exactly this (~line 1865); confirm it still exercises the resolved string, not just the reason.
- **R3 -- a unit dropped from the outer combine (FAILS OPEN).** If any unit fails to produce a verdict, an undecidable segment or a floored leaf could stop forcing ask/deny. Mitigation: assert `len(unit_verdicts) == len(units)` in a test; the loop structure makes it hard to violate, but it is worth pinning because the consequence is silent.
- **R4 -- attribution drift.** The recording branch decides what `_deciding_sub_match` sees, which decides the final `matched_rule`/`provenance`. Both are corpus-tracked fields, so `--verify --strict-prose` catches drift; step 0's test catches it earlier and localises it.
- **R5 -- goldens regenerated to "fix" a failure.** The corpus README already warns about this; repeat it in the coder task spec. Any prose diff in this refactor is a defect until proven otherwise -- the whole design premise is that nothing observable changes.
- **R6 -- the second `apply_parse_failure_floor` call looks redundant during the rewrite.** It is not; it is the only floor covering a command line made entirely of undecidable segments. Its existing comment says so at length. Do not touch it.

## Why not the fallback

The fallback (`resolution_strategy: Callable[[str], UnitVerdict]`, documented as a strategy pattern) costs about an hour and genuinely fixes aggravating factor #1: the lossy 3-tuple and the closure smuggling of `matched_rule`/`provenance` both disappear, because `UnitVerdict` carries them. `ResolveOuterProbe` collapses into the same type. That is a real improvement and I would take it over the status quo.

What it cannot fix is `record_unit`. Under the fallback, `compound` still reaches into `resolve.py`'s list to append entries the caller cannot see itself producing, still applies the floor at a point where the caller has no visibility, and still leaves `sub_matches` -- the audit trail, the thing R1e existed to repair -- populated from two modules by two different mechanisms (a side effect inside the injected resolver, plus an out-of-band recorder). Naming that arrangement "the strategy pattern" would document a shape that is not a strategy pattern, which is worse than documenting nothing: a reader who trusts the name will not go looking for the second callback.

And the removal is cheap *because* the floor stays put. This is not a rewrite of the decision logic; it is moving a call site so that decomposition publishes its intent as data. The measured cost -- roughly a hundred lines of real change, ninety lines of docstring deleted, near-zero test churn -- is the evidence that the design is the simple one rather than the elaborate one. If the floor had had to move, or a new verdict type had been needed, or fifty tests had had to change, I would be arguing for the fallback instead.
