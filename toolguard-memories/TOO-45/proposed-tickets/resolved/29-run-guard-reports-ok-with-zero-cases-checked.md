---
title: run_guard reports ok=True when GUARD_CANARIES is empty -- a guard that passes
  having checked nothing
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/29-run-guard-reports-ok-with-zero-cases-checked
---

**FIXED in `05f786d` (TOO-45 phase 2).** `run_guard` now treats an empty `GUARD_CANARIES` set as a mismatch rather than reporting `ok=True` with zero cases checked — see `tools/architecture_fitness.py:3251-3260`.

> **FAMILY COUNT 2026-08-13: twelfth confirmed instance, and this one is in the golden verdict corpus.**
>
> `test_verdict_corpus` measured it two ways. **An empty corpus raises `SkipTest`, which reports green.** And the realistic shape is worse than a one-sided shrink: **halving `cases.jsonl` and `goldens.jsonl` together (3200 of 6401) left all 4 relevant tests green with no skips** — which is exactly what `--extract` + `--generate` does on a tree whose `logs/` is smaller or absent, and the realistic corpus is **94%** of the total. One-sided shrink *was* caught in both directions; the symmetric one was not.
>
> Now closed by `TestCorpusPopulation`, deliberately in its own class **with no `setUpClass`**, because a skip is precisely the failure mode being guarded.
>
> **A second finding from the same probe, different family**: the corpus honours `TOOLGUARD_CORPUS_ACCEPT_PROSE=1`, and with it **exported** both tracked-tier tests cannot fail — hiding 5 of 10 mutants including one worth **3,557 diffs**. The hatch was verified genuinely narrow (the hard tiers still fail under it) and that narrowness is now pinned by two tests, one of which fails if the hatch stops being required.

# `run_guard` reports `ok=True` when `GUARD_CANARIES` is empty

**A guard whose empty case is indistinguishable from its passing case.** Found in the TOO-45 #07 sweep by emptying the canary set and watching the guard succeed.

## The defect

`tools/architecture_fitness.py`'s `run_guard` iterates `GUARD_CANARIES` and reports `ok=True` if nothing failed. With `GUARD_CANARIES` empty it reports `ok=True` **having checked zero cases**. Nothing in the result distinguishes "all canaries passed" from "there were no canaries."

This is the fail-open shape, in the one place it is least acceptable: a fitness guard exists to make a silent regression loud, and this one goes quiet in exactly the circumstance where it has stopped working at all.

Reachable by ordinary means: a refactor that renames or relocates the canary constant, a filter that narrows to nothing, a load path that returns empty on error. None of those announce themselves; all of them turn the guard into a no-op that reports success.

## What is NOT affected, measured in the same pass

Emptying `.pyscn.toml`'s layers and rules is **not** fail-open -- 76 modules come back unmapped and the real-tree smoke test correctly fails. So the layer-mapping side of architecture fitness degrades loudly. The defect is specific to the canary guard.

## The test that "covers" it does not

One test does fail when `GUARD_CANARIES` is emptied. **It fails through an incidental branch mismatch, not through any designed check on the canary count.** So a failure count reads as coverage while nothing asserts the property that matters.

That is the third instance in this sweep of a mutation producing failures without the mechanism being covered, and the method note is worth repeating: **read the tracebacks; a mutation that produces failures is not necessarily detected.**

## Fix direction

Assert the population, not just the outcome. `run_guard` should fail -- or at minimum report `ok=False` with a distinct reason -- when it has zero cases to run. The general form, worth applying wherever a guard iterates a collection it did not build itself:

> **An empty input to a checker is a configuration error, not a pass.**

Then add a test that asserts a non-zero case count, so the property is pinned rather than implied.

## Scope note

`tools/architecture_fitness.py` is a **dev instrument**, not shipped runtime, so this cannot mis-govern a permission decision. It can let an architecture regression through silently, which is the thing the tool exists to prevent.

## Provenance

TOO-45 #07, `test_architecture_fitness.py` sweep, 2026-08-12. `reports/follow-up-queue.md` section `AFT`. Found by an explicit probe -- *"make the rule set empty or unloadable and see whether anything fails"* -- rather than by reading the code.
