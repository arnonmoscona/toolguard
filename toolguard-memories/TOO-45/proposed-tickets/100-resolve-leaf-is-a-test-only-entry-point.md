---
title: 100-resolve-leaf-is-a-test-only-entry-point
type: note
permalink: toolguard/too-45/proposed-tickets/100-resolve-leaf-is-a-test-only-entry-point
---

# 100 - two module-private functions that no production code calls

**Found 2026-08-21** while verifying ticket 95's commit, by following a pyright "not accessed" warning. **Pre-existing** -- present at HEAD before ticket 95 (line 768 there, 808 now). Ticket 95 is a pure relocation and neither caused nor worsened this.

## The finding

`toolguard/compound.py:_resolve_leaf` has **no caller in production code.** Verified: no `__all__` in the module, no dynamic dispatch, no re-export, and the only non-docstring references outside its own definition are in `test/unit/test_compound.py` and `test/unit/test_compound_resolve_seam.py` -- roughly 30 call sites across both.

Its body is:

```python
unit = _unit_for(leaf)
part_verdicts = [_unit_from_result(part, resolve_one(part)) for part in unit.parts]
outcome = judge_unit(unit, part_verdicts, undecidable_fallback)
return RuntimeVerdict(decision=..., reason=..., additional_context=...)
```

Production does the same work in `resolve_compound_permission_detailed`, per unit, and then combines:

```python
unit_verdicts = [judge_unit(unit, [_unit_from_result(p, resolve_one(p)) for p in unit.parts], undecidable_fallback) for unit in units]
return _combine_strictest(unit_verdicts)
```

## Severity - deliberately stated at its real size, not its dramatic size

**This is NOT "30 tests test dead code."** `_unit_for`, `_unit_from_result` and `judge_unit` are the live production logic and those tests genuinely exercise them. What is orphaned is the ~10-line wrapper.

The real cost is narrower and still worth fixing: **those tests reach the production logic by a route production never takes.** They bypass `_combine_strictest` entirely, so a divergence between the single-leaf shape and the combined shape cannot be caught there. And the wrapper constructs a `RuntimeVerdict` with `matched_rule`/`provenance` left at defaults -- a shape production never produces, which is exactly the kind of "structure that exists only in tests" this project has been burned by.

## Reachability

Zero. It cannot fire in the field because nothing calls it. **This is not a fail-open** -- it is dead weight plus a test seam that has quietly drifted from the production path.

## Fix directions, for Arnon to choose between

1. **Delete it and repoint its tests** at `resolve_compound_permission_detailed` with a single-unit input. Highest value: the tests then exercise the path production actually runs, combining step included. Highest cost: ~30 test call sites.
2. **Keep it, and say what it is.** If a single-leaf seam is genuinely wanted for testing, that is legitimate -- but it should be named as such and its divergence from the production path documented, so nobody reads its coverage as covering production.
3. Delete it and drop the tests that duplicate coverage available elsewhere.

**Recommendation: (1)**, on the grounds that this project's repeated finding is *a structure that exists in two shapes and cannot disagree loudly*. But it is a real cost and Arnon should pick.

## Before scheduling - the evidence rule applies

Per `.claude/rules/evidence-before-fixing.md`, measure before implementing. Here the exposure measurement is trivial and already done: **zero field reachability by construction.** So this is queued on *code-health* grounds, not on risk, and it should be ordered accordingly -- below anything with a live failure mode.

---

## MEASURED 2026-08-21 - the class is bounded at TWO, and that is the point

Both findings came from following a pyright "not accessed" warning, one at a time. That is a poor way to find a *class* of defect, so I swept the package instead: an AST walk over all module-private (`_name`, not `__dunder__`) functions, counting whether each is named anywhere in `toolguard/`.

**78 production files, 383 module-private functions, exactly 2 orphans** -- the two already known. `bash_parser.py` excluded as canopy-generated machine output.

| function | site | live sibling that IS called |
|---|---|---|
| `_resolve_leaf` | `toolguard/compound.py:808` | `resolve_compound_permission_detailed`, which does the same work per unit then combines |
| `_discover_rules_files` | `toolguard/config.py:398` | `_discover_rules_files_multi` at line 441 |

**`_discover_rules_files` is the cleaner case of the two.** Its plural sibling sits 43 lines below it and is the only one production calls. The singular form is pre-existing at HEAD and looks like the residue of a widening from one rules directory to several -- the same "one structure grew a second question" shape this campaign keeps meeting, except here the old shape was left standing rather than merged.

**Why the bounded count matters more than either finding.** Two orphans in 383 is a clean codebase, not a systemic problem. It means this should be fixed for tidiness and then *checked*, not treated as evidence of decay. Do not let it justify a broad audit.

## Proposed instrument: `architecture_fitness.py --orphans`

Per `.claude/rules/evidence-before-fixing.md`, an instrument must name the declaration it checks against or be labelled a heuristic. **This one has a declaration: the leading underscore.** A developer writing `_name` is declaring "internal to this package"; the check tests conformance to that declaration and nothing else. It never judges whether a function *deserves* to exist -- only whether the intent its own name declares is met.

That puts it in the **strong** column alongside `--layers` completeness, not with `--mocks` or the complexity thresholds.

**Known blind spots, which must be stated rather than discovered:** a function reached only through `getattr`, a dispatch table keyed by string, or a plugin registry will read as an orphan. None exist in this package today (verified: no `__all__` in `compound.py`, no dynamic reference to either name), but the check should report rather than fail, or it will fail wrongly the first time someone adds one.
