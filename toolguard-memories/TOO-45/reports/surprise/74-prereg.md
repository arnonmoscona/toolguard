---
title: TOO-45 surprise factor - ticket 74 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/74-prereg
---

# Pre-registration, proposed ticket 74 (the hook bypasses the tool registry; an empty registry fails open)

Written **before** the briefing is regenerated, before the estimator runs, and before implementation.

## Scored under the REDEFINED metric

Arnon, 2026-08-20: what is measured is *"expected and final complexity... the final outcome reflects the human time to review. A large discrepancy between the apriori estimate and the postpriori final outcome is where the surprises I want to measure are."*

So for this item and everything after: **headline is recall against the final committed diff, weighted by changed lines, not by file count.** Precision is retained only as an integrity guard and must not be averaged in. `T` (transient) is not recorded. `A` (absorbed) is still classified but stays out of the headline pending the aggregate.

## LEAK STATUS: HIGH on location, and the ticket hands over the fix shape

Named: `hook._resolve_event`, `_handle_command_tool`, `payload_key()`, `_REGISTRY`, `governed_tools()`, `transcript_harvest` and `test.verdict_corpus.fixture_loader` as the two consumers that *do* honour the contract, and the existing RED test `test_the_hook_reads_a_command_tools_target_from_the_registered_key`.

Little is hidden about **where**. The prediction task is about **how far it spreads**.

## No log signature at all — this is a severity-only item, and worth saying why that is fine

Neither finding is a command or rule shape, so the corpus cannot speak to either. `_REGISTRY = ()` is a **code-level** condition, not user-reachable — nobody can configure their way into it.

**That does not lower the severity, and the reason is the campaign's own repeated lesson.** The failure is *fail-open in the last line of defence*: with an empty registry, `_resolve_event` allows every tool including a hard-denied `rm -rf`. Per `.claude/rules/evidence-before-fixing.md`, a zero count measures the observability of a defect, not its absence — and this one is silent by construction. Arnon's rule as of 2026-08-20: **fail-open tickets are high priority.**

## The genuinely open question, which is the whole measurement

**Does the fix stay inside `hook.py`, or does it pull in the registry's other consumers?**

The ticket's own framing is that **the contract exists, two consumers follow it, and the hook does not**. Two shapes follow from that, and they differ by an order of magnitude in touch set:

1. **Narrow** — teach the hook to call `payload_key()` on the command branch as it already does on the file-path branch, and guard the empty-registry case. Two functions, one file.
2. **Wide** — treat "every consumer reads the target through the registry" as an invariant and enforce it, which reaches `transcript_harvest`, the verdict-corpus fixture loader, `tool_spec` itself, and plausibly a new architecture test.

The estimator is **not** told which. This is a clean test of whether it reasons about *invariants* or about *the named defect site*, and under the redefined metric a wrong answer here is exactly the expensive kind — unexpected files in the final diff.

## Falsifiable prediction, locked

**The empty-registry guard will require a decision about what an empty registry MEANS**, and that decision will show up as prose somewhere, not only as a guard clause. Three defensible answers: refuse to start; treat it as "govern nothing" and say so loudly; or treat it as a programming error and raise. **If the fix lands as a bare `if not registry: return deny` with no statement of intent anywhere, that is a finding in itself** — this campaign's single most repeated defect is a mechanism whose behaviour nobody wrote down, and this ticket is the fail-open case of exactly that.

## Ordering discipline

The estimator writes `74-estimate-predictions.md` and `74-estimate-uncertainties.md` and returns only `DONE`. Neither is opened until the ticket is green.
