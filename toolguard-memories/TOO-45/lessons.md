---
title: lessons
type: note
permalink: toolguard/too-45/lessons
---

## Three corrections from Arnon after the validation canary (2026-08-06)

**1. Threading state repeatedly is evidence, not cost.** `permission_mode` reached ~11-12 functions in BOTH trees and I reported that as the inherent price of a cross-cutting concern. Arnon: *"usually having to thread the same state over and over again usually indicates a design issue."*

He also named an architectural fact about this system that **was never written down anywhere, which is why nobody exploited it**: a hook gets a fresh Python interpreter per invocation, so constraints that a long-running service would impose simply do not apply. Options he listed, cheapest first: globals (fine when the facts are fixed for the process lifetime); a class holding the state with the functions as methods, constructed once the facts are established; or other shapes chosen deliberately.

**My objection, specific to this codebase rather than purist:** production is one invocation per interpreter, but **the verification harness is not** — the corpus replays 6,401 cases in a single process, the suite runs 2,387 tests in one, and `--eval`/`sandbox`/replay all drive many decisions per interpreter. A global would be correct in production and would silently leak case *n*'s mode into case *n+1* in exactly the machinery relied on to prove correctness. Note the symmetry with the earlier trap where a module-level "once per session" guard was a no-op *because* the process dies each call: the same property makes globals safe for invocation-scoped facts and useless for session-scoped state, and both are easy to get backwards.

So option 2, with a constraint written into the ticket rather than trusted to judgement: **an invocation-scoped object must hold invocation facts and nothing else.** The moment it accretes config lookups or policy "because it is already there", it becomes `Configuration` 2.0 and the ticket has gone in a circle.

**2. "Accumulate, then choose or consolidate at the end" — and the audit-loss bug is its canonical instance.** Arnon restated the principle: keep things in structured data, do not lose things by replacing them.

The 83% audit loss is exactly that failure. The structured per-sub-command breakdown was **replaced** by a rendered string; recovering it required parsing; the parser dropped every segment lacking `" -> "`; 1,943 sub-commands executed unrecorded. Had the structure been accumulated and the prose rendered *from* it, the data would never have been recoverable-in-principle-but-lost-in-practice.

**R3 fixed the parsing and left the replacement in place.** Prose is now write-only, but it is still the only channel for explanation — which is why the canary had to rewrite reason text in both trees at identical cost. The remaining work is a structured annotation channel on the verdict, with prose rendered from it.

**3. Separation of concerns and SRP were the principles I never checked against.** Every step of this ticket was checked against representation principles — one verdict type, no parallel arrays, no prose parsing. The property that actually paid off in the canary was `_resolve_outer` being separate from `_resolve_one`: **single responsibility applied to CALL INTENT** (a speculative probe versus an authoritative resolution), which R1e produced by accident for an unrelated reason.

Arnon: *"Like many architecture principles they should not be a holy grail - but are always worth checking against. Opportunity for improving right under your nose."*

**Practice to adopt:** alongside the representation predicates, check each step against separation-of-concerns and SRP explicitly — including on *call intent*, not just on data shape.