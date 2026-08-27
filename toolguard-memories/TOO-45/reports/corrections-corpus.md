---
title: TOO-45 corrections corpus (extraction)
type: note
permalink: toolguard/too-45/reports/corrections-corpus
tags:
- task-memory
- TOO-45
- retro
---

# TOO-45 corrections corpus (extraction)

## Scope and method

Source: `too45_turns.txt` — 210 numbered human turns, 170 through 379, from the TOO-45 session chain. **Assistant turns are absent**, so in many entries the thing being reacted to is not visible; those are marked *target unclear*.

Three classes of turn were excluded as not carrying Arnon's own voice:

- **77 turns are pasted subagent task-notification blocks** (201, 204, 209, 212, 222, 225-228, 230-233, 235, 245, 247, 249, 251, 254, 256, 258, 259, 263, 265, 268, 274, 276, 277, 279, 281, 283, 285, 286, 288, 290, 291, 294-299, 301, 306, 311, 312, 318, 320, 331-345, 348-354, 360-365, 373). They are agent output, not human input.
- **~25 turns are the cron "anti-stall check" messages** (244, 246, 252, 255, 257, 260, 261, 266, 267, 269-273, 275, 278, 280, 282, 284, 287, 289, 293, 300, 315, 319). These were authored by the assistant's own reminder mechanism at Arnon's request in turn 242 — they arrive in the human channel but are **not Arnon's words**. One of them (315) contains a substantive instruction ("Check each stage against separation-of-concerns and SRP explicitly, including on call intent - that is the check never run during TOO-45"); it is noted here only as a marker that the assistant itself flagged that gap, not as an Arnon correction.
- **Turns 190-193, 239-241, 326-328** are `/compact` commands and compaction summaries. The summaries at turns 191, 240 and 327 do contain verbatim Arnon quotes; where a quote appears **only** there and not as a standalone turn, it is labelled *(quoted in the turn-240 compaction summary; no standalone turn in the extract)*.

Turns 170-189 predate the TOO-45 work (they are the TOO-19 push tail). A few carry architecture or process principles and are included, marked *pre-TOO-45*.

Spelling and typos in quotes are Arnon's, preserved verbatim.

---

## A — Architecture

### Turn 188 *(pre-TOO-45)* — toolguard has no AI component; auto-mode guidance is the complementary half
> "we explicitely rulled out the idea of toolguard having an AI driven component - based on several good reasons - so it's always going to be a mix for auto-mode... So the seeming overlap is not really an overlap - they target different cases in reality."

- **Principle**: the deterministic tool and the prose guidance cover *different* cases; do not treat them as overlapping and do not propose absorbing one into the other.
- **Type**: correction of a claim already made (the assistant had said the `soft_deny` rules overlap TOO-28).
- **Reason given**: yes — they target inverted blind spots; the no-AI decision was already taken for stated reasons.

### Turn 197 — two more internal/external seams beyond the one he had named
> "there are clearly two more such seams: The hook input protocol and shape... The native match rule syntax used in the native claude rules."

- **Principle**: every place toolguard touches a Claude-Code-owned format is a seam that will move under you; enumerate them all, not just the response.
- **Type**: guidance before the fact (correcting an incomplete list in the plan).
- **Reason given**: yes — both have already changed, and "quite frequent for a public interface of software".

### Turn 197 — migration must not need to parse the foreign syntax
> "automatically migrate new rules from the native settings to toolguard setting with a shallow automated script that does not parse them (i.e. it should not need to)"

- **Principle**: shallow beats deep at a foreign seam — don't build a parser for someone else's evolving syntax.
- **Type**: guidance before the fact.
- **Reason given**: implied — the syntax is not ours and changes.

### Turn 197 — dev tooling is not part of the product
> "P2 architecture_fitness.py... does not sound like something that is a public part of this repo... ultimately they should not stay as a part of the product *unless* we create a dev-only dediated package 'home' for those that is documented as *not part of the runtime* and enforced not to be."

- **Principle**: measurement tooling either leaves before release or gets an explicit, documented, *enforced* dev-only home.
- **Type**: guidance before the fact.
- **Reason given**: yes — it is not product; the runtime boundary has to be enforced, not just stated.

### Turn 197 — "phases" are an implementation artifact, not a vocabulary
> "'Phases' are an internal artifact of the tool implementation, not a feature or even a term used to document the tool... the semantics of something like 'additionalContext' do not imply that it is considered in only one phase"

- **Principle**: don't promote an internal implementation construct into the user-facing rule vocabulary, and don't constrain a field to a phase just because it currently is used in one.
- **Type**: correction of a proposed step (R7, "declared phases").
- **Reason given**: yes — it is not a documented term; tying the field to a phase adds a formal constraint with no demonstrated value.

### Turn 197 — R6: make the engine interface a module and a declared pyscn layer
> "you may (or may not) consider further enforcing the engine public interface by making it a separate module and declaring it as an explicit layer for pyscn. This will float a violation predictably in every code review. WDYT?"

- **Principle**: put the boundary somewhere a tool will complain about it every time, not somewhere a reviewer must remember it.
- **Type**: guidance before the fact (offered as a question, not a directive).
- **Reason given**: yes — a violation that surfaces predictably in every review.

### Turn 198 — the layer-drift test: *what* vs *how*
> "the real test the judge should apply is looking at each function or class and ask 'is this about the *what to do* or about the *how to do*?'... A layer's external interface is much like a system's public API - it should strive to be stable... and focus on *what* the layer does for everybody outside it while encapsulating *how* it's done."

- **Principle**: a layer boundary is judged by whether its interface is a stable *what*, not by how tidy it looks.
- **Type**: guidance before the fact.
- **Reason given**: yes — "it is not about aesthetics, but about maintainability ind prevention of concept leaks"; a too-thin interface changes every time the code beneath it does.

### Turn 198 — keep the migration helper from growing teeth
> "add one small helper for it that verifies that what it migrated actually parses, but without trying to modify it... without complicating the script by having it edit the entries."

- **Principle**: a checker that raises an alarm beats a fixer that edits; keep the shallow script shallow.
- **Type**: guidance before the fact (offered as "something to consider").
- **Reason given**: yes — avoids complicating the script; the alarm is the useful part.

### Turn 207 — the diagnosis he reached for first
> "rooted in lack of separation of concerns and possibly also insuficient encapsulation. Certainly misleading naming (which is not about being pretty - but being comprehensible), and also breaking the single responsibility principle."

- **Principle**: separation of concerns, encapsulation, comprehensible naming, SRP — these are the named lenses, and naming is a comprehensibility property, not a cosmetic one.
- **Type**: correction of existing code (not of the assistant); target is a finding the assistant reported.
- **Reason given**: yes — "it complicates what should be easy (evidence: callbacks that are harder to reason about as they cross layers both ways)".

### Turn 213 — no local imports
> "Incidently it also supports my general policy of *no local imports* except in *very* special cases."

- **Principle**: standing policy — imports go at module top; local imports are a special case needing justification.
- **Type**: standing preference restated on the back of a finding (not a correction of anything the assistant did here).
- **Reason given**: implied by the `Configuration` finding — local imports hide the dependency.

### Turn 218 — a large argument list is a design signal
> "That's another signal of a design problem we have not covered before - needing a very large set of arguments for a function... it's not a very focused signal, but it's a strong signal nontheless of 'something is wromg here'"

- **Principle**: wide signatures mean something is wrong, even if they don't say what.
- **Type**: guidance before the fact.
- **Reason given**: yes — it's non-specific but strong.

### Turn 219 — the "fossil signature"
> "You start with something perfectly good, and after some number of new requirements and various bugs... you end up with what I call a 'fossil signature'... A signature that grew organically like an ancient city street plan and does not make sense any more."

- **Principle**: signatures rot organically; that is normal decay, not a one-off mistake, and it must be actively watched for.
- **Type**: guidance before the fact.
- **Reason given**: yes — "LLMs are much more resilient to emerging complexity with the upshot that it tendfs to stay under your radar".

### Turn 292 — where the audit-log format change lands
> "A tougher 'canary' proof of improvement: introducing an enrichment that causes a rule to have a different outcome based on the mode that claude is running in... It's tougher because the effect and evaluation of this construct happens in at least two different places in the code."

- **Principle**: prove the architecture by making it absorb a change that necessarily crosses more than one place, not one that sits in a single spot.
- **Type**: guidance before the fact.
- **Reason given**: yes — the previous canary did not affect the verdict; and a new, unanticipated case "is a strong defence against over-fitting".

### Turn 304 — threading the same state repeatedly is a design signal
> "usually having to thread the same state over and over again usually indicates a design issue"

- **Principle**: repeated state threading is a symptom; either accept globals (cheap, ugly, valid only because the interpreter is fresh per invocation) or make a class whose methods share the established invocation facts.
- **Type**: guidance before the fact, prompted by a finding.
- **Reason given**: yes — "If you always get a fresh interpreter *lots of constraints fall away*"; a hook is a special case architecturally, and the assumption is not baked in anywhere.

### Turn 304 — separation of concerns and SRP, again
> "This one speaks diretly to the issue of separation of concerns and the single responsibility principle I mentioned before. Like many architecture principles they should not be a holy gral - but are always worth checking against. Opportunity for improving right under your nose."

- **Principle**: check against SoC/SRP every time; they are not absolutes but they are always worth running.
- **Type**: correction — and note the explicit "I mentioned before", i.e. he is flagging repetition himself.
- **Reason given**: yes — an improvement was sitting unnoticed.

### Turn 305 — prefer the class over globals for future-proofing
> "This behavior of the Claude harness can easily change in the future - exactly because of people wanting session state. So the second option is also more future-proof."

- **Principle**: don't design against a harness property you don't control; the object-holding-state option survives a harness that keeps a process alive.
- **Type**: guidance before the fact (clarifying his own turn-304 point).
- **Reason given**: yes — the fresh-interpreter guarantee is likely to be removed.

### Turn 308 — isolate external storage behind a repository
> "the surrounding toolguard code that interacts with this stateful storage component... could always be isolated from the rest using a simple repository pattern. So the storage itself and its safety is less interesting in this context"

- **Principle**: the interesting architectural question is the seam around external state, not the storage technology.
- **Type**: guidance before the fact (scoping a hypothetical challenge).
- **Reason given**: yes — storage safety is a separate, focused design problem.

### Turn 309 — a session layer over Configuration
> "It also means that Configuration may have overrides that need managing - a sort of an additional layer besides the existing one ('session layer'?)"

- **Principle**: session-scoped overrides are another configuration layer, not an ad-hoc mutation of the existing one.
- **Type**: guidance before the fact, speculative (his own question mark).
- **Reason given**: no explicit reason.

### Turn 310 — scope guard on the speculative design
> "that is for the implementation of such a scenario - not as a permanent refactoring"

- **Principle**: a thought experiment does not license permanent structural change.
- **Type**: correction (target unclear — reacting to something the assistant proposed about the session-layer idea).
- **Reason given**: no.

### Turn 355 — logging and configuration are cross-cutting and belong low
> "log_writer sits in the wrong layer. Speaking inn generality logging is a cross-cutting concern and so it configuration. So they both belong at a low layer and should be importable by pretty much anything... The apparent dependency of logging on configuration can be handled by importing, or it can be handled by injection"

- **Principle**: cross-cutting concerns go at the bottom and are importable by everything; an awkward dependency between two of them is an injection question, not a layering exception.
- **Type**: correction of the delivered layer map.
- **Reason given**: yes — the general nature of cross-cutting concerns; and injection works for a long-lived object where an import would not.

### Turn 357 — the shim that hides a real dependency
> "why is there still a static dependency from hook to tools.decision? Looks like a violation to me. And tools.decition is just a ship [shim] that practically hides a direct dependency on toolguard.api.decide - so why do we even need it in the first place? Looks like a noise artifact that was not cleaned up by R6. I don't really buy the 'hoisting would require two other modules' claim."

- **Principle**: a back-compat shim that only disguises a dependency is noise; delete it. And he does not accept a cost claim that was not measured.
- **Type**: correction of delivered work.
- **Reason given**: yes — the shim adds nothing; the justification offered was unconvincing.

### Turn 357 — runtime circular dependencies are not acceptable just because they're invisible
> "It's still hidden from static analysis and anything that is hidden from static analysis is harder for a human reader to detect and reason about as well."

- **Principle**: invisibility to the tools is *the* problem, not a mitigation — what a checker can't see, a reader can't either.
- **Type**: correction of delivered work (`permission_resolution → resolve`, `compound → resolve`).
- **Reason given**: yes — human readability tracks static discoverability.

### Turn 357 — the config layer calling back into the engine
> "this is the config layer calling back into the engine and that really should not exist at all... Smells like a landmine. Reading the actual code of rule_entry.py it is not obvious to me *at all* even *where* this callback happens. if it's intentional and justified - it must be prominent and easy to detect."

- **Principle**: a reverse cross-layer dependency from a static layer into the engine should not exist; if it must, it has to be prominent enough to find by reading.
- **Type**: correction — and note this one was not discussed at all in the report, only visible in a diagram.
- **Reason given**: yes — he could not locate it in the source; undetectable equals dangerous.

### Turn 358 — express shape dependencies as Protocols, not prose
> "One way is to use typing annotations that would explicitely force symbols to be present (like a parameter type)... by using a common dependency on a Protocol (in the same layer)... A weaker thing is to explicitly document if prose or in a dunder variable - both of which are prone to drift and not advisable."

- **Principle**: in a duck-typed language, make the dependency real in the type system; documentation-only markers drift and import-only markers get stripped by tooling.
- **Type**: guidance before the fact.
- **Reason given**: yes — unused imports get removed by cleanup tools; prose and dunders drift.

### Turn 358 — circular runtime dependency needs a justification or a fix
> "unless we agree on a good reason then we must find a way to clean up. This is specifically about permission_resolution ↔ resolve and compound ↔ resolve."

- **Principle**: "it was already like that" is not a justification; either argue it or remove it.
- **Type**: correction, escalating turn 357.
- **Reason given**: yes — "Sometimes there are good, intentional reasons. Sometimes it's just another thing to clean up."

### Turn 359 — principled fix, but not at the price of complexity
> "I would go for the principled fix rather than the cheap fix... with the objective to *not making the solution too complex* as a complex solution defeats the purpose of making the whole code easier to reason about... If you do come up with a simple solution then it is almost certainly cheap to implement - otherwise it smells."

- **Principle**: the goal is reasoning-ease, so a clever fix that costs comprehensibility loses to the cheap one; and simple should also be cheap — if it isn't, distrust it.
- **Type**: guidance before the fact.
- **Reason given**: yes — a complex solution defeats the purpose of the whole exercise.

### Turn 359 — if you take the cheap fix, name the pattern
> "the patterns used (e.g. strategy) must be explicit both in comments (e.g. doc comments or regular comments) *and* in naming e.g. calling ana argument something like `resolution_strategy`"

- **Principle**: an implicit pattern is a hidden pattern; put it in the identifier as well as the comment.
- **Type**: guidance before the fact (conditional on taking the cheap route).
- **Reason given**: implied — discoverability.

### Turn 370 — a big module is not itself the problem; entanglement is
> "yes, config.py is large. But this is largely because the config semantics of toolguard are by construction rich, layered, and require provenance and complete logging. I don't see this as a problem as long as we guard strongly against the config code getting entangled with the decision code, like it was before."

- **Principle**: size is a consequence of essential domain richness; the thing to police is the boundary between config and decision, not the line count.
- **Type**: correction of an implied finding (target: the end-state summary's treatment of `config.py` size).
- **Reason given**: yes — the semantics are irreducibly rich; the historical defect was entanglement.

### Turn 370 — the four standing review questions
> "Is every change in a ticket done in the right layer? Are we holding to the single responsibility principle? Is the layering as defined still correct, or does that need tweaking? Did we introduce runtime dependencies that are not statically resolvable and not enforceable by static analysis tooling?"

- **Principle**: these four become part of ongoing review, not a one-off TOO-45 activity.
- **Type**: guidance before the fact (for the process going forward).
- **Reason given**: implied by everything above it.

### Turn 375 — enrichment blocks stay small by design intent
> "enrichment blocks are going to be small and limited to places that claude takes repeated actions... The length protection is just belt and suspenders. The last thing I need is for enrichment blocks to contaminate the token count of the agent context with repeated text."

- **Principle**: the word budget exists to bound context cost; the real control is intended usage, and the design should assume small.
- **Type**: guidance before the fact (clarifying design intent, target unclear — likely a question about the cap).
- **Reason given**: yes — token contamination of the agent context.

### Turn 377 — anchor the project root at session start
> "We cannot rely on the shifting harness behavior over multiple harness versions to decide this. This means that we need per-session behavior now... We need to anchor the project root at the start of the session and remember it for the remainder of the session to anchor all paths."

- **Principle**: don't let a harness-owned, mutable value (cwd) be the anchor for a security decision; capture it once per session.
- **Type**: correction of a real defect the assistant surfaced in reply to turn 376.
- **Reason given**: yes — "catastophic outcomes"; cwd can move under you and "flies under the radar"; harness behaviour changes across versions.

### Turn 378 — all rules anchor to the runtime project, regardless of provenance
> "One correction to your statement... I actually hold the position that *all rules* regardless of what their provenance is, should be interpreted as anchored to the current runtime project."

- **Principle**: moving a rule up the config hierarchy must not change what the rule means.
- **Type**: correction, explicitly framed as one — and he also corrects the record ("it was never an actual requirement or a documented behavior of toolguard").
- **Reason given**: yes, two — (1) rules migrated upward for reuse must keep their meaning; (2) it matches the mental model people have when writing them. He also invites challenge: "I am open to a challenge of my thiinking."

---

## B — Data modelling

### Turn 180 *(pre-TOO-45)* — an attestation has value even without the prose
> "an attestation with no intendisclosure still has value. Because the attenstation can be matched in a rule, then the rule can distinguish read-only intent from write intent."

- **Principle**: the machine-matchable token carries value independent of the human-readable text beside it.
- **Type**: guidance before the fact (an aside, explicitly not for the ticket).
- **Reason given**: yes — it can be matched by a rule; prose cannot.

### Turn 262 — tuples versus dataclasses
> "I personally sort of dislike tuples except in cases of a strict pair value return. Tuples are harder to read and easier to index incorrectly. dataclass is trivially cheap and can be just as frozen."

- **Principle**: a frozen dataclass instead of a tuple, everywhere but a strict pair.
- **Type**: correction of code already written.
- **Reason given**: yes — readability and mis-indexing; the cost objection does not hold.
- **Strength**: "I personally sort of dislike" — soft phrasing, but repeated three more times in the same turn and in later turns.

### Turn 262 — and named tuples are not the answer either
> "Same note about tuples (and to an extent named tuples, which are somewhat better, but sill not as good as a dataclass)"

- **Principle**: named tuples are a partial fix, not the fix.
- **Type**: correction, restated within the same turn for a second finding.
- **Reason given**: implied.

### Turn 264 — why your instinct reaches for tuples
> "your training data is choke-full of examples of tuple use that are either misguided or just a manifestation of older code... the dataclass construct and the frozen variant of it where introduced precisely to tackle this problem."

- **Principle**: same principle, third statement — with an explanation of *why the model keeps producing tuples*.
- **Type**: guidance before the fact (pre-empting recurrence).
- **Reason given**: yes — training-data composition and the historical order in which the constructs appeared. Explicitly offered as "saving you from researching it".
- **Note**: this is the escalation point of the tuple theme — from a preference to a diagnosis of the assistant's bias.

### Turn 302 — verbosity is an acceptable price for the right type
> "sometimes wher you have cleaner code you can have more verbosity. For instance, replacing tuples with any kind of class is more expensive from line count perspective - but it is both safer and much easier to read."

- **Principle**: don't let LOC be an argument against replacing a tuple with a class.
- **Type**: guidance before the fact / reassurance about a measured result.
- **Reason given**: yes — safety and readability.

### Turn 304 — keep structured data; accumulate, don't overwrite
> "keep stuf in structured data. Do not lose stuff by replacing it. Accumulate things and at the end eithe choose or consolidate. Seems like it was indeed only partially done."

- **Principle**: carry everything forward as structure and decide at the end; never discard a fact by replacing it with a derived one.
- **Type**: correction of delivered work ("only partially done"), and he flags it himself as a repeat: "This speaks directly to something we discussed yesterday (or the day before)".
- **Reason given**: implied — the discarded data is what later code has to reconstruct.

### Turn 357 — `RuntimeVerdict` is not a clear name; and the no-data-loss construct is right
> "`RuntimeVerdict` is not that clear a name... a `FinalVerdict` would describe it better... The pairing of `FinalVerdict` (single) and `UnitVerdict` (many, that get distiled into one) seems logical to me."

- **Principle**: the type name should say what it *is* to the outside world; sibling types should read as a pair.
- **Type**: correction of a delivered name.
- **Reason given**: yes — the assistant's own description of the type ("what the hook tells Claude Code about the whole tool call") fits `Final` better than `Runtime`.

### Turn 357 — never parse prose you produced in the same runtime
> "The master's reason string parsing after having tossed the structured data makes me shudder. Glad we got rid of it. I wouldn't want to put my name to code that does that. We might want to actually make it into user level guidance like 'Never create prose strings that you later parse in the same runtime. Carry structured data instead. Prose is for output, not for code consumption other than combining prose with prose.'"

- **Principle**: prose is an output format only; if a value is needed downstream, carry it as data.
- **Type**: approval of the removal *plus* a request to promote it to standing guidance.
- **Reason given**: yes, in the strongest personal terms available to him — "I wouldn't want to put my name to code that does that."
- **Strength**: the highest in the corpus. This is the only place he proposes the exact wording of a global rule.

### Turn 366 — a Protocol earns its place even if it drifts
> "even if it does drift, the mere presence of the type hints to any reader about intention... Clarity is more important than enforcement. If I wanted strong enforcement I would use a strongly typed language with all the burdens that this brings."

- **Principle**: types are documentation with tooling attached; partial accuracy still beats an untyped duck-typed call.
- **Type**: guidance before the fact, answering a stated objection (drift).
- **Reason given**: yes — traceability in the IDE and via pyright/code-review-graph; "Balance is not perfection and most of the time it does not need to be."

---

## C — Code organisation and style

### Turn 207 — naming is comprehensibility, not decoration
> "Certainly misleading naming (which is not about being pretty - but being comprehensible)"

- **Principle**: a naming objection is a correctness-of-understanding objection.
- **Type**: correction of existing code.
- **Reason given**: yes — comprehensibility.

### Turn 220 — write for humans even when only an LLM will maintain it
> "code that is 'good for humans' is also code that is 'good for LLMs'. So maintaining code by targeting a human audience, even if the code is always going to be maintained by an LLM will result in better code and better LLM reasoning about it."

- **Principle**: the human-readability target is the operative one, always.
- **Type**: guidance before the fact.
- **Reason given**: yes — training data is mostly human-generated, so models reason better about human-shaped code.
- **Reversal**: he explicitly upgrades his own earlier standard — "I think that this is an even stronger criterion than my original criterion of 'if it's hard for me to review then it ain't no good'".

### Turn 221 — the worked example
> "the output of canopy, while scientifically great - is nearly impossible for a human to digest. While the PEG grammar that was designed 'for at least some humans' is much easier to reason about both for humans *and* for agents"

- **Principle**: same principle, demonstrated on the project's own artifacts.
- **Type**: guidance before the fact.
- **Reason given**: yes — the machine-optimal artifact is unreadable to both audiences.

### Turn 229 — docstrings had started to bloat
> "I noticed that lately the docstrings started growing in size, and that smelled. But I didn't raise it yet. They should probably be terser and more 'traditional' with explanations only where there is a truly complicated algorithm present or edge cases that a developer should be aware of or subtle points from requirements... I am not one that advocates that 'you should not need comments - the code must be clear enough'. That's a young man's pipe dream."

- **Principle**: comments earn their place by covering complicated algorithms, edge cases and requirement subtleties — never by restating the code.
- **Type**: correction of an accumulated trend (he says he had been holding it back).
- **Reason given**: yes — duplicating the obvious "creates confusion and divergence drift".

### Turn 292 — diagrams must be small and focused
> "do not generate diagrams with too many elements in them - those are unusable. Each diagram should be focused on specific aspect of the final design"

- **Principle**: one diagram, one aspect.
- **Type**: guidance before the fact.
- **Reason given**: yes — density makes them unusable.

### Turn 322 — backwards-compatible syntax is fine
> "you can always revert to a backwards compatible syntax. It's harmless"

- **Principle**: don't fight a tool over a syntax modernisation; take the older form.
- **Type**: guidance before the fact (target: the `except (A, B):` / ruff-format collision).
- **Reason given**: yes — harmless.

### Turn 323 — ruff, not black, on purpose
> "I use ruff and not black because it's not as rigidly (religiousely) opinionated as black."

- **Principle**: the formatter should be configurable; rigidity is the reason black was rejected.
- **Type**: guidance / preference statement, prompted by a formatter collision.
- **Reason given**: yes.

### Turn 357 — clarity beats performance, as a language-level choice
> "the 'what was eliminated section' to me looks like a major cleanup win for the branch, no matter what metrics or cpu time costs say. (if I wanted it to be really fast then I'd implement it in another language. I choose a language for humans and code organization for humans over performance here)"

- **Principle**: performance is not a valid counter-argument to a clarity win in this codebase.
- **Type**: approval, carrying a standing principle.
- **Reason given**: yes — Python was chosen for humans; speed would have meant a different language.

### Turn 359 — naming that "expresses reason and intent tersely"
> "explicit naming patterns that express reason and intent tersely helps a ton"

- **Principle**: terse *and* intentful; both, not either.
- **Type**: guidance before the fact.
- **Reason given**: yes — reasoning, static analysis, comprehension.

### Turn 367 — comments with no shelf life
> "there is actually too much commenting that will not be all useful for the future, like the comments added at the module level in compiound.py: relevant right now, but relevance would not have much of a shelf life."

- **Principle**: a comment that is about *this change* rather than about the code does not belong in the code.
- **Type**: correction of delivered work.
- **Reason given**: yes — short shelf life.

### Turn 367 — comment verbosity, escalated and attributed
> "Comments in general are too verbose. This is a relatively new behavior since the introduction of opus5 - do I need to change the output style?"

- **Principle**: same principle as turn 229, now framed as a model-level regression he is considering a harness change to fix.
- **Type**: correction, escalated.
- **Reason given**: yes — it is a behavioural change he can date.
- **Strength**: the escalation is the signal — from "that smelled" (229) to "do I need to change the output style?" (367).

### Turn 367 — cognitive complexity, compounded by the comments
> "compound.judge_unit() is fine, but has high cognitive complexity, which is again not helped by the verbose comments"

- **Principle**: verbosity is not neutral — it adds to the reading cost of an already-complex function.
- **Type**: correction of delivered work.
- **Reason given**: yes — the two costs stack.

### Turn 367 — literal strings with semantic meaning
> "throughout the whole project there is reliance on literal strings with semantic meaning. For example `if unit.kind == \"inline_code\":` - it's not a great practice... There are much worse offenders (e.g. \"deny\", \"ask\", etc.). This is brittle and better done with constants. This really should be general guidance at a global level. 'literal strings used in conditionals should be expressed as constants at the appropriate scope'"

- **Principle**: a string literal in a conditional is a constant that hasn't been declared yet.
- **Type**: correction of an accumulated, project-wide pattern.
- **Reason given**: yes — brittleness; he counts occurrences (twice in the module, once in tests) and names worse offenders.
- **Strength**: high — one of only two places he drafts the exact global-guidance sentence.

### Turn 367 — doc comments should be short; long explanations go to documentation
> "the doc comments are so long that they become exhaustin and intimidating to read. Plus they have ticket-specific verbiage that has short shelf-life. Doc comments should be informative but short. Long explanations should be reserved for technical documentation."

- **Principle**: docstring for the reader of the symbol; document for the reader of the design; link between them.
- **Type**: correction of delivered work.
- **Reason given**: yes — exhausting to read, and ticket-specific text goes stale.

### Turn 374 — the multi-line preview logging
> "the weird choice of logging in log_writer.py:390 - we don't need this multi-line 'preview' style of logging. Just make it normal logging."

- **Principle**: don't invent a bespoke rendering where the ordinary one does.
- **Type**: correction of existing code — and note he says he only noticed it because the change set had got small.
- **Reason given**: implied — it is unnecessary.

---

## D — Process

### Turn 174 *(pre-TOO-45)* — fabrication is a must-fix, on either side
> "deny-side fabrication, like any fabrication is a must fix"

- **Principle**: fabricated data in an audit trail is never triaged down, regardless of which decision path produced it.
- **Type**: correction of a triage decision.
- **Reason given**: implied — it is fabrication.
- **Strength**: "must fix" — one of the few absolutes in the corpus.

### Turn 175 / 176 *(pre-TOO-45)* — case-by-case triage is his call
> "list all of them and I'll make a case by case decision" → "fix s1 and m3, leave the rest"

- **Principle**: he wants the full inventory and makes the fix/defer calls himself.
- **Type**: guidance before the fact.
- **Reason given**: no.

### Turn 195 — the plan goes where the guidance says it goes
> "it does not belong in overhall/. As per the guidance the ticke plan goes into the ticket directory in basic memory - so move it"

- **Principle**: artifact location is governed by existing guidance; don't invent a directory.
- **Type**: correction of an action already taken.
- **Reason given**: yes — the guidance already specifies it.

### Turn 197 — his framing was education, not a specification
> "my comment was not a set of directives or specific instructuins. It's to educate you about how to think about a problem like this... those are just ideas from a very experienced engineers - but they are not absolute nor are they infallable. You should think about them independently, creatively, and most important critically."

- **Principle**: don't convert his sketch into requirements; use it to generate your own thinking and pressure-test his.
- **Type**: correction of how the plan treated his earlier comment.
- **Reason given**: yes — the point is to build your own judgement, not to execute his.

### Turn 197 — take notes for your own long-term skill
> "it will serve you greatly if you take general notes along the way to improve your own skills ('skills' as in English as well as possibly 'skills' as in 'Claude skills' - the first is more valuable)."

- **Principle**: the transferable lesson matters more than the tooling artifact.
- **Type**: guidance before the fact.
- **Reason given**: yes — the ticket is a learning vehicle, not just a repair.

### Turn 197 — over-caution about the corpus
> "Corpus privacy - 'what privacy?' Actual logs are great."

- **Principle**: real data beats synthetic; sanitise at commit time, not at collection time.
- **Type**: correction of an unnecessary constraint the assistant had adopted.
- **Reason given**: yes — logs are not on GitHub, transmission is no different from any Claude Code activity, and committed material can be sanitised or made ephemeral.

### Turn 197 — a judge guard on non-closing iterations
> "One guard that I would add to the judges is the number of iterations without closing a step."

- **Principle**: an autonomous loop needs a "you are going in circles" tripwire.
- **Type**: guidance before the fact (adding to the assistant's design).
- **Reason given**: implied.

### Turn 197 — slow down only if the evidence says so
> "Slightly slower and more reliable is probably better than constant interruptions."

- **Principle**: reliability over throughput when interruption cost is high.
- **Type**: guidance before the fact.
- **Reason given**: yes — mid-stream interruptions force re-orientation and sometimes rework.

### Turn 198 — protect against total context loss, not just growth
> "there's another protection this provides, which is a crash midway... it is safer to guard against total loss of context, at least as a test of 'what's too little' as opposed to the size limit, which is about 'what's too much'"

- **Principle**: the resume artifact is a crash guard, and must be tested for sufficiency, not just for compactness.
- **Type**: guidance before the fact (adding a reason the assistant had not given).
- **Reason given**: yes — session resume papers over the crash case but does not remove it.

### Turn 198 — evidence before mitigation
> "session limits - yes. We slow down only on hard evidence, which would also give us a hint on how much to slow down, not only on whether to do so."

- **Principle**: don't add a mitigation before you have data that also sizes it.
- **Type**: guidance before the fact.
- **Reason given**: yes — the evidence carries the magnitude too.

### Turn 205 — what gets committed
> "The only changes that might be committed are the ones that may survive the whole ticket."

- **Principle**: commit only what is intended to outlive the refactoring effort.
- **Type**: guidance before the fact.
- **Reason given**: implied.

### Turn 208 — his terminal observations are impressions, not findings
> "Any observations I make based on your comments in the terminal are just incidental impressions. That's all they can be. You will learn as you engage with the details and surely change your mind based on findings more than once."

- **Principle**: don't over-weight his off-the-cuff reactions against your own measured findings.
- **Type**: correction of the weight being placed on his own remarks.
- **Reason given**: yes — he is reacting to summaries, not to the code.

### Turn 224 — memory ages
> "some information does not age well. And so when you look at a memory... then the age of the artifact (not necessarily measured in time, maybe measured by the number of turns or something like that) - is a hint of how incorrect it might be."

- **Principle**: treat age as a prior on staleness for auto-memory and recent notes — not for hand-crafted long-term lessons.
- **Type**: guidance before the fact.
- **Reason given**: yes — "rough and inaccurate, but... at least directionally helpful".

### Turn 229 — the multi-angle method is validated but not finished
> "We validated the method we chose to look at things from multiple *independet* angles. That's good, but as you say - not closed so lets continue until it is"

- **Principle**: independence of the reviewing angles is the property that made it work; don't close early.
- **Type**: approval plus a hold instruction.
- **Reason given**: yes — independence.

### Turn 234 — do more of what works; you decide when you have enough evidence
> "Do more of what works. We don't yet know enough of what doesn't work... You seem to be competent enough to judge as to when you have enough evidence to enact a change. So do that and only stop if it seems ineffective."

- **Principle**: adapt in flight on your own authority; stop only on evidence of ineffectiveness.
- **Type**: guidance before the fact.
- **Reason given**: yes — the failure data isn't in yet.

### Turn 234 — move sideways rather than widen
> "just switching to a slightly different part of the challenge is more likely to uncover paths to success than widening what we've already put some effort into. We can always come back to it if we need to."

- **Principle**: when a hub has been partly worked, a new area yields more information than more of the same.
- **Type**: guidance before the fact (answering a sequencing question).
- **Reason given**: yes — information yield.

### Turn 236 — don't build subagent tasks that can stall on a prompt
> "the subagent tried a git checkout that it's not allowed to do. This stalls it until I come to the desk... You might want to kill stalled agents and restart with instructions that avoid prompts"

- **Principle**: unattended work must be specified so it cannot hit a permission prompt.
- **Type**: correction of a delegation defect.
- **Reason given**: yes — a stalled ASK blocks until he is physically present.

### Turn 243 — in-flight plan changes need no pre-approval
> "in-flight adjustments to the plan are an expected outcome of dynamic learning and error correction. As long as we don't depart from the guardrails and the overall objective of the plan, changes are acceptable without pre-approval. Just report them"

- **Principle**: report, don't ask, when within the guardrails.
- **Type**: guidance before the fact (loosening a constraint the assistant was self-imposing).
- **Reason given**: yes — adjustment is the expected outcome of learning.

### Turn 248 — expect the early wins to be small
> "I actually expect the initial wins to be quite small. When you try to disentanle a messy code base, you typically have to slug through work that buys only little before you get the really big improvements. It's par for the course. Not always true, but an expectation."

- **Principle**: a small first result is not evidence the approach is failing.
- **Type**: guidance before the fact / calibration.
- **Reason given**: yes — experience of disentangling messy codebases.

### Turn 250 / 253 — investigate ruff separately, install when you judge best
> "It might be useful to spawn an investigative agent to review which ruff rules can help with the architecture objectives we have... That can run independently of the rest without disrupting the ongoing work" → "it's your call whether to institute your recommended ruff config now or later."

- **Principle**: side investigations run in parallel; timing decisions delegated.
- **Type**: guidance before the fact.
- **Reason given**: yes — non-disruptive.

### Turn 262 — tests verify behaviour, not shape
> "the real question to answer there is 'what is better for the code quality?'. If it improves it - then it's worth just doing it and fixing the tests logic. The important thing about the test is the meaningful behavior it verifies, not the implementation of the test nor the preservation of the shape of the behavior."

- **Principle**: "it breaks N tests" is not an argument; shape matters only when it is an external interface or a specified contract.
- **Type**: correction of a reason given for not deleting something.
- **Reason given**: yes — with the explicit carve-out for external interfaces.

### Turn 262 / 264 — he is leaving; keep going
> "So far you've managed well even though my response to your questions took a long time. You didn't let it stop you, which I like very much."

- **Principle**: unattended progress is the expected mode; his latency is not a blocker.
- **Type**: approval.
- **Reason given**: yes — stated as what he likes.

### Turn 292 — the deliverable shape for a large ticket
> "I will need several reports about this whole activity and some other artifacts... A retrospective report on the lessons learned (short term and long terms)... Can we generalize a set of principles and practices for efforts like this (especially in autonomous loops). Lessons about how to prevent degredation and rot in the first place"

- **Principle**: a large autonomous ticket is closed by written, reviewable artifacts, not by a green suite.
- **Type**: guidance before the fact.
- **Reason given**: implied — he cannot review the change set directly.

### Turn 303 — ask the agent what it would now do differently
> "Is there something you would have refactored differently based on the experience of implementing this last canary?"

- **Principle**: after each experiment, extract the design implication, not just the score.
- **Type**: guidance before the fact (in question form).
- **Reason given**: no.

### Turn 313 / 314 *(sent twice, near-identical)* — don't rat-hole on races
> "I am not terribly worried about the potential race conditions flagged... I don't want to complicate things because of race conditions. Not yet at least - this kind of thing can leads us to rat-hole on a tangential, not really valuable direction."

- **Principle**: a real-but-unlikely risk with existing layered mitigations does not justify complexity now.
- **Type**: correction of a proposed scope expansion.
- **Reason given**: yes — single machine, sub-second hook, and the system already takes the strictest result across several layers.

### Turn 321 — defer pre-push, do coverage and pyscn now
> "We are close to a commit. Nowhere near close to a push. So we can defer the pre-push issues until we're closer to a push... coverage and pyscn are worth doing before I commit R6. Just make sure that all files are mapped to layers before you run pyscn."

- **Principle**: sequence checks by the gate they belong to; and validate the instrument's coverage before trusting its output.
- **Type**: correction of the ordering the assistant proposed.
- **Reason given**: yes — the commit gate and the push gate are different.

### Turn 329 — review cadence: stop before the change set gets overwhelming
> "changes in lots of files feel overwhelming and confusing... we need to watch the amount of change enacted from a reviewability perspective and choose to stop and do some review *before* it gets overwhelming. That's a tangible, repeatable development process change... It has to be after we finished some meaningful piece in a ticket."

- **Principle**: trigger review on accumulated change size, at a meaningful work boundary — not at a fixed cadence and not at an arbitrary point.
- **Type**: guidance before the fact, derived from his own experience reviewing this ticket.
- **Reason given**: yes — he has repeatedly had tickets balloon beyond what he anticipated; more frequent review would avoid refactors like this one.
- **Caveat he adds himself**: it does not apply to a deliberately autonomous ticket like TOO-45, which is reviewed by documents and stress tests instead.

### Turn 347 — bugs and doc notes wait for the canaries
> "It seems that there are a few minor bugs to fix and a few notes for the final documentation sweep. So remember those to tackle before we get ready for a push but after the canary experiments."

- **Principle**: park the small stuff behind the experiments; decisions wait for his report review.
- **Type**: guidance before the fact.
- **Reason given**: yes — unless the canaries show something actionable, decisions come after his review.

### Turn 357 — architecture documentation is a separate, dated deliverable
> "a new human-consumable well documented code architecture document... The whole architecture document should be stamped clearly with an 'as of' with date and version number. This type of document can easily drift from reality over time... Even when stale, unless major refactoring happens like in this ticket, it still holds value."

- **Principle**: extract the durable architecture content out of the ticket reports; date-stamp it and accept controlled staleness.
- **Type**: guidance before the fact.
- **Reason given**: yes — drift is inevitable, but a stale document still has value if it says when it was true.

### Turn 358 — expand CLAUDE.md when the evidence earns it
> "No prose parsing guidance - feel free to add it to global guidance now. It earned its place. We always want to shrink claude.md - but when evidence shows us poor choices, we must expand it."

- **Principle**: the shrink-CLAUDE.md default yields to demonstrated failure.
- **Type**: approval plus an explicit override of his own standing preference.
- **Reason given**: yes — evidence.

### Turn 359 — decide without asking; explain at the end
> "You can proceed on these without resorting to questions for me unless you encounter real difficulty or indecision. Explain your decision and reasoning for them at the end. Worst case I'll disagree and send you back to fix - not a likely outcome."

- **Principle**: bias to acting and explaining over asking; the cost of being wrong is low.
- **Type**: guidance before the fact.
- **Reason given**: yes — the rework cost of a wrong call is small.

### Turn 359 — have the plan judged blind before implementing
> "I'd recommend creating a plan for it, having a blind judge evaluate the plan, then refinee it based on feedback"

- **Principle**: the blind-judge step applies to plans, not only to finished diffs.
- **Type**: guidance before the fact.
- **Reason given**: implied — keeping the solution from getting too complex.

### Turn 367 / 369 — prune the ticket's own memory artifacts
> "I don't think you need much of the material that is now in memories (the diffs, intermediate stuff from the refactoring effort). Much of this can be deleted... The start, the requirements the initial framing - matters. The end - reports, documents, conclusions, retro - matters."

- **Principle**: keep the framing and the conclusions; delete the middle.
- **Type**: correction of the accumulated note set.
- **Reason given**: yes — "no one will care about the detailed history of these documents"; it "outlived its value".

### Turn 370 — perturbation testing belongs in the pre-push routine
> "high coverage unit testing is very good and necessary - it mainly guards against regressions. It is well known that it rarely uncovers dormant bugs... Randomized perturbation created by blinded agents seem to do the opposite... To me it looks like a mechanism to carry forward as pre-push activity. A well understood way to conduct a fishing expedition."

- **Principle**: coverage guards against regression; blind perturbation finds dormant defects. They are different jobs and both belong in the process.
- **Type**: guidance before the fact, derived from this ticket's results.
- **Reason given**: yes — the value is in the surprises.

### Turn 370 — the report-plus-diagram pattern for hard tickets
> "The process of writing multiple ticket-specific reports, illustrated with small, focused diagrams, really paid off for a large ticket. For small tickets it is probably unnecessary... many times I noticed issues more from the diagrams than from the text."

- **Principle**: this is a pattern to invoke when he signals a change set is beyond direct review — not a default.
- **Type**: approval carrying forward as guidance.
- **Reason given**: yes — he found issues through the diagrams that the text did not surface; "I am very visual, and it shows."

### Turn 371 — "this one is tough" is sentiment, not a trigger phrase
> "it's not a literal trigger phrase. It's sentiment. I might express it a thousand different ways. If you can, and you notice that I am reluctant to do a detailed code review or I explicitely complain - then it's a good time to raise the alternative."

- **Principle**: detect the *state* (reluctance to review, complaint), not the string.
- **Type**: correction of the assistant's proposed mechanism.
- **Reason given**: yes — he will phrase it arbitrarily.

### Turn 372 — one file per proposed ticket
> "create markdown ticket descriptions for deferred items that need decisions and open those in the IDE... Separate file per ticket."

- **Principle**: deferred decisions become individually reviewable artifacts.
- **Type**: guidance before the fact.
- **Reason given**: implied — he decides them as a batch, item by item.

### Turn 379 — mine the interaction as data
> "TOO-45 is all about repairing accumulated issues that arise because of an agent weakness in tracking architectural / code organization practices... So let's use that as data to drive future actions: changing guidance, and improving our development process."

- **Principle**: the corrections themselves are the dataset for the guidance fix.
- **Type**: guidance before the fact.
- **Reason given**: yes — the corpus is evidence of a systematic weakness, not a set of one-offs.

### *(Quoted only in the turn-240 compaction summary; no standalone turn in the extract)* — the plan is not holy; no parallel agents
> "the plan itself is not holy... I totally agree on no parallel agents... With respect to workflows and slash loops - I'll leave the use and design of those to you and I will only review."

- **Principle**: mechanism choice delegated; concurrency of agents refused; the plan is revisable.
- **Type**: guidance before the fact.
- **Reason given**: not visible in the quoted fragment.

---

## E — Measurement and method

### Turn 177 *(pre-TOO-45)* — measure whether the guidance actually worked
> "I have seen instances where the Bash disclosure had the marker but did not have the comments. You may want to inspect logs from the weekend and see whether the 'optimized guidance' we came up with are not quite optimized enough."

- **Principle**: a guidance change is a hypothesis; check it against the logs.
- **Type**: correction of a claim of success (target: the "optimized guidance" from an earlier experiment).
- **Reason given**: yes — his own observation of counterexamples.

### Turn 197 — judge the component scores, not the compound predicate
> "the judge can look at predicates, but it should also independently evaluate the meaning and relevance of the component part scores that drive compound predicates. The compound predicates are artificial, the individual scores have more concrete meaning."

- **Principle**: composite scores are constructions; the parts are the evidence.
- **Type**: correction of the fitness-function design.
- **Reason given**: yes — the compound is artificial.

### Turn 199 — the instrument was pointed at the wrong file
> "how can tmp/git_rules_check.py be governing? Tollguard will not pick it up. Governing should be /home/arnon/.toolguard/rules/git.rules.toml"

- **Principle**: verify that what you are measuring is the artifact that is actually in effect.
- **Type**: correction of a delivered check.
- **Reason given**: yes — toolguard does not read that path.

### Turn 213 — grep versus AST
> "What you got wrong also supports the search tool experiment we're running - grep is less reliable than AST based tooling for tracing code. Unsurprising to me."

- **Principle**: use language-aware tooling to trace code; text search under-counts and mis-counts.
- **Type**: correction of a measurement error already made.
- **Reason given**: yes — the assistant's own miss is the evidence.

### Turn 213 — co-change as a general health metric
> "Reporting co-change: looks like a very good directional health metric for general code hygene - not only for this."

- **Principle**: co-change is directional, and useful outside this ticket.
- **Type**: approval.
- **Reason given**: implied.

### Turn 262 — criteria design is the hard part, and criteria get gamed
> "designing criteria is tough exactly because wrong criteria lead to wrong results, plus it gets gamed. True for automated system and also true for people. Good lesson for you."

- **Principle**: a wrong criterion is worse than no criterion, and any criterion invites gaming.
- **Type**: guidance before the fact, prompted by a reported instrument defect.
- **Reason given**: yes — it applies to people as much as to automated systems.

### Turn 302 — LOC is not the finding
> "The LOC difference is not necessarily an issue. 1. it is a rather small difference 2. sometimes wher you have cleaner code you can have more verbosity."

- **Principle**: don't let a size metric override a structural judgement.
- **Type**: correction of the interpretation offered in a report.
- **Reason given**: yes — cleanliness legitimately costs lines.

### Turn 302 — but the localisation result *is* the finding
> "the finding that the bug fix was more localized and easier to fix is a real win. You did not describe though the difference in this experiment on how well the layering and responsibility separation manifested in the spots where the code changed."

- **Principle**: report *where* the change landed and whether the concerns were disentangled there, not just how big it was.
- **Type**: correction of an incomplete report.
- **Reason given**: yes — that is the question the experiment was for.

### Turn 324 — the only sanctioned pyscn exclusion
> "There is one genuine case that I don't want pyscn to look at and it's the generated parser code... I don't recall making another deliberate exclusion."

- **Principle**: exclusions from a measuring instrument must each be deliberate and remembered.
- **Type**: correction of the exclusion list.
- **Reason given**: yes — meaningless for the questions pyscn answers here, and it crashes the tool.

### Turn 329 — the file-count measure was the wrong measure, not the wrong scenario
> "'the file count is bounded below and could not register success'. This is a real problem that limits the utility... That's an indication more of a wrong measure to choose, not that the scenario is wrong."

- **Principle**: when a measure cannot register success, replace the measure before you doubt the experiment.
- **Type**: correction of the measurement design — and note this reverses part of his own turn-292 request for a files/LOC/locations count.
- **Reason given**: yes — the count measured the size of the requirement, not the difference between the branches.

### Turn 329 — what the replacement measures should ask
> "if a value is read or passed along without meaningful action in many places, then that's funamentally different than the value paticipating in logic branches (e.g. if/else) or a value being written... 'how many of the places that must be touched make sense to touch under a reading of the requirement?', 'how many places increased cognitive complexity and by how much?'"

- **Principle**: measure maintainability and reviewability of the change, not the change's volume; distinguish the *role* a touched site plays.
- **Type**: guidance before the fact (designing the replacement instrument).
- **Reason given**: yes — the old measure conflated requirement size with branch quality.

### Turn 329 — co-change needs small requirements
> "Co-change is mostly about the effect of small requirements rather than big requirements... they were coupled mostly by the requirement - not by the code structure."

- **Principle**: a big feature saturates the co-change signal; use small perturbations.
- **Type**: correction of the canary design.
- **Reason given**: yes — with a big requirement, the file names alone predict the change set.

### Turn 329 — and the intuition test that matters
> "A reading of the requirement and the file names alone would make it clear that config.py would need to change. What is *not* intuitive is *what* changes in config.py."

- **Principle**: the diagnostic question is not *which* files change but whether *what* changes in them is what a reader would expect.
- **Type**: correction / refinement.
- **Reason given**: yes — the master branch put resolution logic in `config.py`, "patently the wrong place".

### Turn 330 — thresholds have to be measured against him
> "We cannot know the thresholds without experimenting a bit. The thresholds are mostly driven by my subjective experience and my sensitivity must be measured by experimenting. No other way I know."

- **Principle**: when the criterion is his subjective reviewability, calibrate it empirically against him.
- **Type**: guidance before the fact.
- **Reason given**: yes — there is no other way to get the numbers.

### Turn 370 — the value is in the surprises
> "Most of the time the perturbations did *not* result in what you anticipated, but sometimes the *did*. The value is in the surprises. When a method or new ways of evaluating a system has a proclivity to get you unexpected, real, and resolvable feedback - it carries more than its weight."

- **Principle**: judge a method by whether it produces actionable surprises, not by its hit rate.
- **Type**: approval carrying a general criterion.
- **Reason given**: yes — stated as the reason it earns its cost.

### Turn 370 — co-change needs an expectation recorded first
> "Creating an expectation based on the requirement and file names alone, intentionally blind to the content of the files, seems to be a good gauge to understand the after-the-fact co-change and score its meaning."

- **Principle**: pre-register the expected touch set, blind, then score the actual against it.
- **Type**: guidance before the fact.
- **Reason given**: yes — it is what makes the co-change number mean anything.

### Turn 370 — but subjective reviewability still wins
> "*But* the subjective ease of review turns out to still be the strongest signal"

- **Principle**: after all the instruments, his experience of reading the change remains the primary evidence.
- **Type**: guidance / judgement statement.
- **Reason given**: implied by the whole ticket.

### Turn 370 — execution is king
> "Execution is king. So it should hold a first class place in our ongoing development process."

- **Principle**: measured behaviour beats read-and-infer, and this belongs in the standing process.
- **Type**: guidance before the fact, generalising this ticket's most repeated error class.
- **Reason given**: yes — implied throughout, and stated again below.

### Turn 370 — gameability, and the answer to it
> "Sure - any metric or rule is gameable. The quetion is always how to you detct issues, and how do you enforce issues. Here again execution and tracing is king. It's easy to hide from static analysis. It's hard to hide from observed runtime behavior."

- **Principle**: detect at runtime, then make the *next* instance of that violation statically discoverable. Still gameable, but it improves monotonically.
- **Type**: correction of a framing in the layer-separation report ("is it gameable").
- **Reason given**: yes — the asymmetry between hiding from static analysis and hiding from execution.

### Turn 370 — mermaid over plantuml
> "the more I look at mermaid, the more I think that it's simply plainly superior to plantuml. So maybe we should drop plantuml as a preference. It seems to be just an old habit of mine that's ready to be shaken off."

- **Principle**: tool preference revised on evidence.
- **Type**: **reversal of his own turn-292 instruction** ("For formal UML plantuml is preferable... mermaid is the least appealing").
- **Reason given**: yes — he names it as habit rather than judgement.

### Turn 370 — Sankey diagrams as an experiment
> "I wonder if Sankey diagrams can help visualize some of the aspects of this code refactoring effort... Maybe we should experiment a bit with that at the end"

- **Principle**: try a new visual instrument on the flow/movement questions.
- **Type**: guidance before the fact, explicitly speculative.
- **Reason given**: no.

### Turn 370 — the micro-canary protocol is agent-only work
> "this process is uniquely something that's totally doeable with agents and too labor intensive for manual work to be worth it without agents - hence you won't find it much in SDLC discussions."

- **Principle**: don't look for prior art; the economics only work with agents.
- **Type**: guidance / framing.
- **Reason given**: yes — labour cost.

---

## F — Explicit approval

- **Turn 174** — "Amend the coder guidance to allow adding new tests. **Good observation**" *(pre-TOO-45)*
- **Turn 177** — "The good new is that Toolguard worked. The git stash operations did result in ask as they should have... **toolguard worked**." Plus: the `additionalContext` feature "**validates the feature being developped**." *(pre-TOO-45)*
- **Turn 197** — "R1 promoted to second - **fine with me**"; "Your core loop look like a **godd start**"; "Your breakdown of two judges is **fine**... probably better from a 'context rot risk' perspective"; open items: "final step order - **I agree**", "R6 deferred decision - **agreed**"
- **Turn 198** — "we're **in agreement** about step/byproduct"; "lesson notes - **great choice**"
- **Turn 208** — "**I accept your analysis**... I am **happy** that you are uncovering big chunks of fix discovery with potentially limited cost early in the process."
- **Turn 213** — "yes the `Configuration` finding is **very important**"; "Reporting co-change: looks like a **very good directional health metric**"; "Step order: **fine**. R6 in its own ticket: **fine**."
- **Turn 229** — "We **validated** the method we chose to look at things from multiple *independet* angles. **That's good**"
- **Turn 262** — "**It's good** that you are finding what works and what doesn't and you're adjusting your evaluations as you go"; "**Good intermediate change of attitude** towards the one verdict type... you are refining the definitions rationally"; "**Good lesson for you**" (on criteria design); "You didn't let it stop you, **which I like very much**"
- **Turn 292** — the whole deliverable request is framed as building on work he considers worth documenting (implicit approval only; target unclear)
- **Turn 302** — "**This is actually good news**... the finding that the bug fix was more localized and easier to fix is a **real win**."
- **Turn 316** — "**I accept** the bug fixes recommendations"
- **Turn 317** — "**I agree**. We can create a ticket later"
- **Turn 321** — "I am **learning a lot** as I am reading the documents you wrote... It's a lot to go through but **it's good stuff for the most part**."
- **Turn 329** — "There's **a lot of very good material** you prepared."; "the one for the branch **feels more 'natural' to me**. Things are **where i would expect them to be**."; "(the visual diagram **really helped** here)"
- **Turn 330** — "**Fantastic on several counts.** We agree on the problems of our benchmark and the micro-canaries is **a good idea**. We should definitely do it."; "Your idea of a script assisted, measured approach to help govern the review cadence along with punctuated boundaries is **a good one**."
- **Turn 357** — "**I like the construct** that leads to no data loss about prior steps... the experiment showed that it *didn't* - so that's a **big win for the branch**."; "No bare tuples and not __iter__ shims necessary is **nice**"; "the 'what was eliminated section' to me looks like **a major cleanup win**"; "**Glad we got rid of it**" (reason-string parsing); "Extracting `permission_resolution.py` as a separate module is **a huge win for the branch**"
- **Turn 358** — "No prose parsing guidance - feel free to add it to global guidance now. **It earned its place.**"
- **Turn 359** — "permission_resolution ↔ resolve: **yes, a Protocol expresses exactly what shape you depend on**... **helps a ton**."
- **Turn 366** — Protocols: "That is **always better** than plain duck-typed calls with no clue about intentions or dependencies."
- **Turn 367** — "The two added Protocol classes added in config_types.py are **good**." *(immediately qualified by the docstring-length objection)*
- **Turn 370** — "Replacing it with perturbation-based small changes was **a win. A big one.**"; "The process of writing multiple ticket-specific reports, illustrated with small, focused diagrams, **really paid off**... **None of the reports I read so far had no value for me.**"; "**Worth keeping this document for the long term**" (micro-canary protocol)
- **Turn 374** — "I saw that you started using constants for strings. **Good**"

---

## Reversals and self-corrections

| Turn(s) | What changed | Earlier position |
|---|---|---|
| 220 | Adopts "good for humans = good for LLMs" as the operative criterion | Explicitly replaces his own "if it's hard for me to review then it ain't no good" — he calls the new one "an even stronger criterion" |
| 198 | "maybe we should not allow bisect then" | Revises the git-rules edits he himself had made one turn earlier (197) |
| 329 | The file-count / co-change canary measures were the wrong measures | He had specified exactly those measures in turn 292 ("How many core classes... total number of LOC touched, the total number of code locations touched") |
| 358 | "when evidence shows us poor choices, we must expand it" | Overrides his own standing "We always want to shrink claude.md" |
| 370 | "mermaid... is simply plainly superior to plantuml. So maybe we should drop plantuml as a preference" | Direct reversal of turn 292: "For formal UML plantuml is preferable... mermaid... visually it's the least appealing" |
| 370 | `config.py` being large is accepted, reframed as an entanglement question | Reverses the implied "big module = problem" framing carried through the ticket |
| 378 | "it was never an actual requirement or a documented behavior of toolguard" | Corrects the record on what toolguard's path-anchoring semantics were, and states a new position |
| 313/314 | Declines to harden against a real race he acknowledges | Sets aside a correctness principle he would normally apply, on explicit cost-benefit grounds |

---

## Recurrence table

Ordered by count. Turn numbers are where each theme appears.

| # | Theme (in his terms) | Turns | Count | Escalation |
|---|---|---|---|---|
| 1 | **Execution / measured behaviour beats reading and inference; the instrument is wrong more often than the code** | 177, 197, 199, 213, 262, 302, 324, 329 (×3), 370 (×3) | **13** | Culminates in a slogan he coins himself: "Execution is king" (370) |
| 2 | **Hidden dependencies must be made statically visible — what a checker can't see, a reader can't either** | 213, 357 (×3), 358 (×2), 359 (×2), 366, 370 | **11** | Soft policy statement (213) → "Smells like a landmine" (357) → "unless we agree on a good reason then we must find a way to clean up" (358) |
| 3 | **Write for humans; clarity over performance, over enforcement, over cleverness** | 219, 220, 221, 357, 359, 366, 367 (×2) | **8** | Stated as a *stronger* criterion than his own previous one (220) |
| 4 | **Carry structured data; never produce prose you later parse** | 180, 262, 304, 357, 358, 370 | **6** | "makes me shudder… I wouldn't want to put my name to code that does that" (357) → promoted to global guidance (358). Strongest language in the corpus |
| 5 | **Comments and docstrings are too long and too ticket-specific** | 229, 357 (implicit), 367 (×3) | **5** | "that smelled. But I didn't raise it yet" (229) → "Opus5 is way too verbose… do I need to change the output style?" (367) |
| 6 | **Tuples out, frozen dataclasses in** | 262 (×2), 264, 302, 357 | **5** | Preference (262) → diagnosis of the model's training-data bias (264) |
| 7 | **Separation of concerns and single responsibility, checked explicitly every time** | 207, 304, 355, 370 | **4** | He flags the repetition himself: "the single responsibility principle I mentioned before" (304) |
| 8 | **Metrics are guides that get gamed; wrong criteria produce wrong results** | 197, 262, 329, 370 | **4** | — |
| 9 | **Naming must express intent; it is comprehensibility, not decoration** | 207, 357, 359, 367 | **4** | Reaches a proposed global rule for string literals → constants (367) |
| 10 | **Layers: a layer interface is a public API; *what* not *how*; cross-cutting concerns go low** | 198, 355, 357, 370 | **4** | — |
| 11 | **Review cadence: stop and review before the change set gets overwhelming** | 329, 330, 370, 371 | **4** | Explicitly named "a tangible, repeatable development process change" (329) |
| 12 | **Keep moving; adjust in flight; report rather than ask** | 234, 243, 262, 359 | **4** | — |
| 13 | **Don't rat-hole: scope guards on speculative or low-likelihood work** | 198, 310, 313/314, 359 | **4** | "leads us to rat-hole on a tangential, not really valuable direction" (313/314) |
| 14 | **Dev tooling and internal constructs are not product** | 197 (×2), 292, 369 | **4** | — |
| 15 | **Tests verify meaningful behaviour, not shape** | 174, 262 | **2** | "the real question to answer there is 'what is better for the code quality?'" (262) |
| 16 | **Design against the harness changing under you** | 305, 377 | **2** | "catastophic outcomes" (377) |

### Counts per category

| Category | Entries |
|---|---|
| A — Architecture | 28 |
| B — Data modelling | 9 |
| C — Code organisation and style | 15 |
| D — Process | 33 |
| E — Measurement and method | 22 |
| F — Explicit approval | 22 turns (multiple approvals within several) |

Entries appearing in two categories are counted in both.
