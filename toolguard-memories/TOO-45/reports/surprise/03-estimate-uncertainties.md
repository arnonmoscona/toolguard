---
title: Blind estimate (uncertainties) - item 03 resolution cycle
type: note
permalink: toolguard/too-45/reports/surprise/03-estimate-uncertainties
tags:
- task-memory
- TOO-45
- measurement
---

## Named uncertainties

Deliberately no file paths below — these are mechanisms, questions and searches.

### U1. Does the injected callable carry anything besides matches?

**Question:** what is the full return payload of `_decide_detailed`, and does the calling side consume more than "which rules matched at this level" — provenance, config-issue objects, a fallback marker, an override-breadth comparison, a reason string?

**Check:** read the return annotation and every attribute access on its result at the call sites (`grep -n "_decide_detailed"` for the sites, then LSP `findReferences` on the return type's fields). Also `grep -nE "provenance|issues|fallback|breadth"` inside the 364-line orchestrator.

**What changes:** if the payload is matches-and-nothing-else, "matches as data" is a small, honest refactor and my counts hold. If it carries provenance or issue accumulation, then "pass matches as data" is under-specified — and the failure mode is precisely the one this project has already paid for: a boundary that discards structure, with the loss invisible because the surviving verdict object still compares equal. In that case the correct shape is a richer per-level *result record*, not a match list, and the work grows by whatever produces those extras.

### U2. Is the seam re-entrant?

**Question:** does the callback ever land back in the orchestrator (compound sub-commands each taking a full resolution pass), or is the interleaving flat?

**Check:** the ticket's own asymmetric profile (4 in, 3 out) is a hint but not proof; settle it by adding a depth counter to the injected callable for one compound and one simple command, or by `incomingCalls` on the orchestrator entry point to see whether a sub-command path reaches it.

**What changes:** flat interleaving makes both suggested shapes viable. Re-entrancy makes "matches as data" require materializing a *tree* of per-level matches per sub-command before deciding anything — usually a worse artefact than the cycle it removes — and effectively forces the inverted-iteration shape. This is the single highest-leverage fact for the design choice.

### U3. Is the cascade's laziness load-bearing?

**Question:** in a real decision, how many hierarchy levels are *consulted* versus how many exist? Does the cascade short-circuit on the first decisive level?

**Check:** count invocations of the callable per decision against the number of discovered config levels, on a project with a deep hierarchy (a home + project + rules-dir setup). If consulted < available, laziness is real.

**What changes:** if the cascade short-circuits, converting to eager data changes *when* matching runs. That is not merely slower — matching that can warn, raise, or record a config issue would now do so for levels that are currently never reached, altering observable behavior in a way a verdict-object comparison may or may not catch. If nothing short-circuits, eager data is free and simpler.

### U4. Does per-level matching have side effects?

**Question:** does anything on the callback's transitive path write a log line, emit a session warning, register a once-per claim, or report an error/notice?

**Check:** `grep -nE "error_reporter|log_writer|session_warnings|once_per|error_log"` across the two engine modules involved and anything they call on the resolution path.

**What changes:** this is the blind spot the golden corpus explicitly does not cover — it compares verdict objects and is blind to where output goes. Re-ordering or eagerly evaluating a side-effecting matcher can duplicate, drop, or re-order log and warning emissions with a fully green suite. If side effects exist on that path, the change needs its own output-assertion tests, and the touch set grows to include whichever test module owns logging/warning assertions. If the path is pure, the corpus really is the safety net the ticket assumes.

### U5. How much of the corpus actually exercises multiple levels? (I think the safety claim is overstated)

**Question:** of the corpus fixtures, how many are multi-level hierarchies rather than a single flat config file?

**Check:** count fixture directories containing both a `home/` and a `project/` tree versus flat single `.toml` fixtures, then count how many of the ~6,400 in-process cases resolve against each.

**Why I flag it:** from the inventory alone, only about five fixture families are multi-level (`ask_provenance`, `hierarchy_conflict`, `override_breadth`, `parse_failure`, `realistic`); the rest are single flat config files. This refactor is *entirely* about per-level matching. So the corpus's enormous case count is largely irrelevant to the changed code path, and its sensitivity is concentrated in a handful of fixtures. "6,400 cases pass" would read as strong evidence and would be weak evidence.

**What changes:** if the multi-level share is small, the refactor needs new multi-level cases *before* it starts, not a green run afterwards. If it turns out most cases run against the multi-level `realistic` fixture, the existing net is genuinely tight and this concern dissolves. Either way, measure the ratio rather than quoting the total.

### U6. Is there a machine-checkable record of this cycle at all?

**Question:** is the intra-layer runtime cycle recorded anywhere a test can fail on — a known-cycle registry, a fitness predicate, a per-iteration count — or does it exist only in prose?

**Check:** search the fitness instrument and its tests for the two module names and for terms like `cycle`, `known`, `expected`, `waiver`, `allowlist`.

**What changes:** if a registry entry exists, removal must delete it and a test asserting its presence must be inverted — an easy touch to miss, and a green suite after a *partial* removal. If no such record exists, then there is currently nothing stopping the cycle from being reintroduced, and the honest scope includes adding a predicate. That is scope the ticket does not mention.

### U7. Layer checking cannot see this at all — is that understood?

**Question:** does any mechanism validate *intra*-layer dependencies?

**Check:** read the layer checker's validation logic for whether same-layer edges are inspected or skipped.

**Why I flag it:** both modules are in `engine`. The declared layer order governs imports *between* layers, so it is structurally incapable of detecting or preventing this cycle. Including the layer map in the briefing invites the inference that the architecture machinery has an opinion here. It does not.

### U8. Where does policy live on this path?

**Question:** are the hard-deny valve, the ASK floor and `no_match_fallback` evaluated inside the callback, inside the orchestrator, or above both?

**Check:** `grep -nE "hard_deny|no_match_fallback|ask" ` in the two modules and note which side owns the decision.

**What changes:** the ticket's core claim is that this cycle is *narrower* than the compound one because no policy has to move. If any of those three policies sits inside the callback, inverting the iteration relocates policy — exactly the thing that made the sibling hard — and the 3-6h estimate is wrong by the same factor the sibling was.

### U9. Is the estimate calibrated or just asserted?

**Question:** what did the sibling cycle removal actually cost in files and lines?

**Check:** `git show --stat` on the sibling commit (`3bb21b7`), plus its implementation report. That is a directly comparable, already-measured number, and it is sitting right there.

**What changes:** the ticket says "estimated by analogy, unvalidated" while the analogy's real cost is one command away. If the sibling touched far more test lines than production lines, expect the same ratio here and plan the test work first.

### U10. Who else depends on the seam being injectable?

**Question:** do tests, the sandbox, the replay tooling, or the public decision interface substitute their own implementation of the injected callable?

**Check:** LSP `findReferences` on the `DecideDetailed` Protocol name and on the injection parameter name; look for fakes and partials in test support code.

**What changes:** if test doubles rely on the injection point, removing it deletes their seam and the test rewrite dominates the work — my added-file prediction becomes an understatement. If injection exists purely to break the import, removal is clean.

---

## The design question: matches-as-data versus inverted iteration

This is the part I would most want two independent designers to answer with evidence rather than taste. The two shapes are not equivalent, and three facts decide between them:

**Data wins when:** per-level matching is pure, cheap and bounded; every level is consulted anyway (no short-circuit); and the per-level result is genuinely just "which rules matched". Then the orchestrator becomes a fold over a list, testable with hand-written inputs and no config at all — a large testability win, and the cheapest thing to review.

**Inverted iteration wins when:** the seam is re-entrant (U2); the cascade short-circuits and that laziness is load-bearing (U3); matching can raise, warn or emit (U4); or a level's evaluation depends on state accumulated from earlier levels — override-breadth comparisons and "more-specific-wins" both smell like exactly that. Any one of these makes eager data either wrong or a lie, because you would end up passing thunks and calling the result "data".

**The deciding evidence, in priority order:** (1) re-entrancy — settle U2 first, it can eliminate the data shape outright; (2) consulted-versus-available level counts from a real deep hierarchy — settle U3, it tells you whether eagerness costs correctness or only cycles; (3) the true payload of the per-level result — settle U1, because if it carries provenance or issues, "matches" is the wrong noun and the design should name the real record type before choosing an iteration direction.

A third shape worth naming, since the ticket offers only two: **decompose into a pure per-level matcher plus a pure decision fold, with a thin driver above both**. That removes the cycle by making neither module call the other — the driver calls both. It costs one more module but is the only shape where the direction question stops mattering, and it matches the "decompose then decide" move the ticket credits for the sibling.

## What in the briefing looks misleading

1. **The layer map is a red herring for this ticket.** It is prominent, detailed, and structurally incapable of saying anything about two modules that are both in `engine`. Do not let its presence imply the architecture machinery covers this.
2. **The corpus's headline number oversells its relevance** (U5). ~6,400 cases, but the changed path is per-level hierarchy resolution and most fixtures look single-level. Large N, narrow overlap.
3. **A test file's name does not predict what it tests here.** At least one file named for the resolver describes itself as an `api.decide()` anti-drift contract test, and the dedicated test file for the 364-line orchestrator is only 168 lines. Actual behavioral coverage of this path is therefore diffuse and lives mostly in the very large compound and hook test modules. Anyone scoping "the tests for this change" from filenames will scope it wrong in both directions.
4. **"Typed but not removed" may read as "no work was lost".** The Protocols were added to describe the existing shape; if the shape changes, some of those Protocols are now *scaffolding for a design being discarded*, and deleting them is part of the job rather than a regression.
5. **The estimate is presented as an estimate while a measured comparable exists** (U9). "By analogy, unvalidated" is a choice not to run one `git show --stat`.
