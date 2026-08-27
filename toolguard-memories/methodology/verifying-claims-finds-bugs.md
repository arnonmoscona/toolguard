---
title: Verifying claims finds bugs - methodology
type: guide
tags:
- methodology
- review
- comments
permalink: toolguard/methodology/verifying-claims-finds-bugs
---

# Verifying claims finds bugs

A method for reviewing comments, docstrings and operator-facing strings by **executing what they assert**, developed and measured on the TOO-45 comment sweep and the prose-review rounds that followed it (toolguard, Aug 2026). It is codebase-agnostic; toolguard appears below only as the worked example.

**This is the companion to [[in-process-mutation-testing]]** — same campaign, different instrument. Mutation asks what the tests can detect; this asks what the prose asserts and whether the code does it.

**Boundary, so nothing here duplicates it:** `TOO-45/TOO-45 comment standard.md` is the *writing* standard — what a comment should say and how short it should be. This file is the *method* — how to run a verification sweep, and why a sweep aimed at prose comes back carrying code defects.

## Why bother — the measured argument

The sweep was scoped as a tidy-up: comments and docstrings only, no code changes. It produced **seventeen proposed defect tickets** (`proposed-tickets/17` through `33`), and the index records why: *"All eleven were found by executing a claim rather than reading it."* Several tickets carry more than one defect — twelve false claims in one analyzer module with four of them load-bearing, eight rows in another, eight defects in already-reviewed code from the back-test — which is how Arnon's running count reached *"something like 40 by now."*

They were not cosmetic. Among them: a matcher whose end anchor made `deny` and `ask` rules silently fail to fire; an over-matching pattern type live in five seeded self-permission rules; a consolidation analyzer documented as "EQUIVALENCE-PRESERVING" that escalates `ask` to `allow` and whose `--apply` writes it; a hook path that could exit with no decision at all.

**The technique keeps getting rediscovered and under-counted**, which is why this file exists. It reads like editing, it gets scheduled like editing, and it returns like debugging.

## Why it works

**The only way to judge whether a comment is true is to run the code it describes.** There is no reading-only version of the check. So a comment review, done honestly, *is* a behavioural review — one aimed precisely at the places a previous author thought worth explaining, which is a good prior for where the subtle behaviour lives.

**The finding is often that the code is wrong, not the sentence.** The prose is what makes the defect visible: someone wrote down the intent, the intent was reasonable, and the implementation quietly does not meet it.

**Corollary, and it governs how the work is scheduled: a wrong comment and a wrong function look identical until you run it.** The reviewer cannot triage by reading, cannot skim for the "obviously fine" ones, and cannot estimate the yield in advance. A pass that reads the prose and edits what sounds off has done none of this work — it has only made the prose sound better.

**Where to aim, if you cannot sweep everything: a claim that reaches outside its own file is where the falsehoods live.** Measured across five modules in this campaign, nearly every false statement found was an assertion about *another* module's behaviour — what the caller does, what the package guarantees. Nothing reviewing this file will ever check those. (The writing-side consequences are the comment standard's business; the method-side consequence is that an outward-reaching sentence is worth a probe and an inward-facing one usually is not.)

The corpus of claims worth executing is wider than docstrings. Three kinds paid out repeatedly:

- **Docstrings on the function that implements the mechanism** — the densest source.
- **Test docstrings and Given/When/Then lines.** A test's own claim about what it pins is a claim about production behaviour. One config-cache defect was found entirely through a test docstring: it claimed a same-mtime rewrite still invalidates the cache; the test passed only because its fixture happened to grow from 26 to 79 bytes, so the `st_size` component of the key changed. Take the size change away and the claim fails.
- **Operator-facing strings** — a count, a category or a "no changes needed" printed to a human is an assertion with the same standing as a comment, and nothing reviews it.

## What it caught — worked examples

Each of these came out of a round whose brief was prose, and each was verified against the repo before being written down here.

**A checker that counted what it never checked.** `--mocks` printed `N target(s) resolved to a repo module attribute`. The split was purely syntactic: `patch("pkg.source.NOSUCHNAME")` yields `resolved_targets=1`, no failures, headline `PASS`. A typo'd patch target counted toward the clean number, and the count also gated the "zero targets were actually checked" guard. The prose was wrong *and* it exposed a real gap. Now: *"target(s) split into a repo module and one attribute name (existence not checked)"*.

**An exclusion that held on one side only.** A comment said test modules were excluded from the scan "on purpose". True of the *evidence* side — a test's own by-value import is not evidence about production. False of the *suppression* side, where every module in the scanned roots counts as a reader, so a test's own read through the module suppresses a finding about that name. The review forced the measurement: narrowing the reader set changed the live result by zero findings, the asymmetry was kept deliberately, and it is now pinned by a test that executes both halves rather than by a sentence claiming it.

**A door with a second door inside it.** `ambient.env_var()` did not answer through `ambient.env()`, so patching one did not affect the other — a second read point inside the module built to remove second read points. Now routed, and the docstring says so: *"Answers from `env`, so an override there governs this too."*

**An off-by-one, found from the sentence above it.** A docstring read *"Returns None when the dots walk above the top-level package."* The guard was `level - 1 > len(parts)` and could not be true; it is `>=` now. The review round that reported it recorded it as `CODE CHANGE` — the only one in a prose pass.

**A stale measurement wearing fresh clothes.** A docstring's `"Measured: 2 files per run"` re-measured at **8**. Both that figure and an unverifiable "1,622 accumulated" were deleted rather than updated; the mechanism sentence stayed.

**A message that named 2 of the 6 markers the code searched.** `CONFIG_ROOT_INDICATORS` holds six entries; the "project root not found" error named two of them, so an operator debugging a failed walk-up was given a third of the truth. The fix derives the list from the constant, which is the only version that cannot go stale.

**Three tests that never ran.** A prose pass on a test module found three tests sitting below the `if __name__ == "__main__"` guard, silently dropped whenever the file was run directly. Confirmed by execution: 19 tests collected afterwards, where the three had been invisible.

## Running a round

**Blind the reviewer.** Give the standard and the code. Do not give the author's intent, the ticket, or a previous reviewer's findings — a reviewer handed a prior list checks that list instead of reading cold. The strongest evidence for this: a fresh blinded reviewer caught a false claim that the *previous repair pass had just introduced*, which a reviewer working from the previous list would have skipped as already handled.

**Verify by execution before writing the replacement sentence, not after.** This is the single highest-yield rule in the method. Measured over consecutive rounds: the passes that verified first found every one of the coordinator's claims held, adopted them, and shipped no new false sentence; the passes that did not each shipped one. Sentences dictated by the coordinator are not exempt — one sentence describing which `patch` helpers a scan skips was rewritten three times and was confidently wrong in a different way each time: first about what the helpers name, then about their targets being expressions, then about a count with twelve counterexamples in the same repo.

**Prefer deletion to rewording.** Deletion is the only edit that cannot introduce a new false claim. A claim that resists compression is usually carrying more detail than it is worth, and the precise version often already exists, correctly hedged, on the function that computes it — a compressed copy elsewhere drops the hedge and becomes false. Three of the four findings in one late round were fixed by deleting the sentence.

**Label the bucket; do not explain it.** A statement of a *category* ("an attribute of an object"), a *count* ("all 232 are stdlib"), a *resolution* ("resolved to a repo module attribute") or a *universal* ("every call", "nothing reads it") must either be verifiable by running the code — in which case verify it before writing it — or say less. A bucket named after the scan's own limit (*"this scan resolves only `patch()`'s literal target"*) cannot go stale. A bucket named after what its members supposedly *are* goes stale the moment one member does not fit.

**Watch for the mechanical-substitution hazard.** A rename or an API migration applied across many files lands inside paragraphs that were *already* stale and refreshes their surface without touching their content. One near-miss is documented: a test docstring saying *"`Path.home()` redirected"* was accurate, because that test really does patch `pathlib.Path.home` — mechanically substituting the new accessor name would have created the exact defect the pass existed to remove. The consequence for the reviewer: **a recently-edited sentence is not evidence of a current one**, and edit recency is worthless as a triage signal.

**The repairer verifies the reviewer, too.** A review finding is itself a claim, written by someone who was reading rather than running, and it arrives with more authority than it has earned. Tell the repairer explicitly that the brief is a hypothesis and that reporting an error in it is part of the job — in phase 1 of this campaign roughly thirty coordinator notes came back corrected, including the same figure wrong three times. It works: one dictated replacement clause (*"callers must fail soft, never raise"*) was rejected as a false universal because a private helper deliberately converts an unresolvable path into an `OSError` and documents that its callers catch it; another (*"the binding is released after `main` returns"*) was rejected because release happens in a `finally`, so it is already gone by then. Both would have been new false claims, adopted on authority.

**File the finding as its reproduction, not as its argument.** The probe output *is* the ticket. Every defect ticket out of this sweep leads with an executable line — `match_pattern(NATIVE, "*a", "aa") -> False # should be True` — and the one that needed more evidence brought it as data: 79,401 pattern pairs brute-forced against 798 commands through the real matcher. A prose finding decays into an opinion someone can argue with a year later; a two-line reproduction either still fails or has been fixed.

**Decide up front whether the round may change code, and record what it defers.** The sweep was comments-only by design — verifying a prose pass is confusing enough without code changes mixed in — so a false *string* was recorded and left alone even while the comment beside it was corrected. That is a defensible trade and it has a bill: ticket `33` exists to pay it, and it documents a codebase left deliberately contradicting its own documentation until the follow-up lands. Whichever way you choose, the finding must leave the round as a filed ticket, not as a queue entry: two of this campaign's largest findings sat unactioned in working notes, and the standing rule that came out of it is that **a defect recorded only in a working queue is a defect that will never be actioned.**

## Probing — the mechanics that made verification cheap

A probe here is three to twenty lines that imports the real module, feeds it the case the sentence is about, and prints what came back. They are disposable, they go in a scratch directory, and they are the whole difference between a verified round and a plausible one. Four habits carried most of the weight.

**Construct the counterexample; do not look for one.** A claim about what a scan classifies is settled by building the input that would break it, not by reading the branch that classifies. `patch("pkg.source.NOSUCHNAME")` in a synthetic tree settled the existence question in one run. A class-body import — the shape a "module-level" qualifier quietly excludes — settled another. Synthetic trees are legitimate evidence and often stronger than the real one, because the real tree may simply contain no member of the disputed category today.

**Probe both directions.** A claim survives if the thing it asserts happens *and* the thing it denies does not. One hedge about which call shapes a scan sees needed both: `from unittest.mock import patch as p` is silently missed (zero examined calls), while an unrelated `Thing().patch(...)` is counted and can even produce a finding. Verifying only the first direction would have produced a sentence that was true and still misleading.

**Enumerate the bucket before you name it.** Where a comment names a category, print its actual members. One bucket held exactly 8 entries: 7 were a stdlib module imported into the target module and 1 was a from-imported class attribute — which confirmed the proposed parenthetical, and would have refuted it just as cheaply.

**Probe the ambient facts, not only the code path.** Several verified claims in one round were about the environment the code runs in rather than its logic: which modules are actually on the hook's import path, how many call sites a new context manager has, which readers bypass the accessor. Each was one live probe and each replaced a guess that read as a fact.

**The best outcome of a verified claim is a test, not a better sentence.** Where the claim is load-bearing and the answer was a deliberate design choice, spend the round's last twenty minutes converting it: one asymmetry that had been asserted in a comment is now pinned by a test with two near-identical fixtures differing only by the disputed read, asserting one finding and then zero. That claim cannot go stale, and the next reviewer does not have to re-derive it.

## Convergence, and when to stop

Findings per round, measured on two tickets: **14, 14, 7, 4, 0** and **12+, 3, 4**. The first sequence converges; the second was still moving when it was stopped, and the shape of the two together is the useful part — a clean round is achievable, but not on the schedule the first round's yield suggests.

Two stopping rules, in order of authority:

1. **A round that returns nothing is the finish line**, and it is the only reliable one. A round returning a small number is not converging by itself — round 3 of the first sequence returned 7 after two rounds of 14.
2. **A *new* false claim introduced by the previous repair means the loop is circling, and the answer is wholesale deletion, not another rewording.** Three attempts at one sentence, each wrong differently, is the signature. Delete the sentence and re-run; do not schedule a fourth attempt at saying it accurately.

**Nothing here converges on a count.** The reviewer must never check whether the number of comments went down, and the coordinator must not report the running total to the reviewer — both make the metric the target, and the campaign has already produced one pass that deleted ticket references, left the useless prose in place, satisfied its own metric and made the codebase worse.

## Cost, stated honestly

Roughly **100k tokens per review round**, five rounds on one ticket, plus a repair pass between each. Individual repair passes measured at ~27 minutes / ~$2.25 and ~40 minutes / ~$4-6; a blinded review pass over a diff measured at ~10 minutes / ~$3 on an earlier step. Call it a few hundred dollars and most of a day for one module's prose, and understand that most of the spend buys sentences nobody will read.

**What makes it worth paying**: the module is one where a wrong belief is expensive — a matcher, a permission gate, a safety analyzer, an instrument other decisions are made from — or the prose is dense enough that someone will act on it. Every ticket named at the top of this file came from that kind of module.

**What makes it not worth paying**: prose on code whose behaviour is cheap to re-derive, or a module where the honest answer is to delete most of the comments unread. Deleting an unverified claim costs one round and cannot introduce a new one. **If the budget only covers one pass, spend it deleting, not verifying** — and reserve verification for the claims someone actually relies on.

## Limits

- **It finds defects where prose exists.** A mechanism nobody documented is invisible to this instrument, which is exactly where mutation testing pays; the two campaigns were run against overlapping code and their findings barely intersect.
- **It is bounded by what you can execute cheaply.** Claims about matching semantics, counts and resolutions are strong candidates because a probe is three lines. Claims about concurrency, failure ordering or another process's behaviour resist the method, and the right move there is deletion rather than a longer probe.
- **The reviewer's own additions carry the same burden as what they found.** Text written to fill a gap left by a deletion has *less* evidence behind it than the text it replaced, and on one measured module every defect in a pass came from prose the pass wrote rather than from what it cut. When a deletion leaves a gap, the default is to leave the gap.
