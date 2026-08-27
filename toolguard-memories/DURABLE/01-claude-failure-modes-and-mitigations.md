---
title: 01-claude-failure-modes-and-mitigations
type: note
permalink: toolguard/durable/01-claude-failure-modes-and-mitigations
---

# Claude failure modes observed in this project, and what actually mitigates them

Extracted 2026-08-23 from TOO-45 (and TOO-19/TOO-30 where noted) so the underlying notes can be deleted. **Every item here was measured, not inferred.** Where a count is given, it is a real count.

Each failure mode is paired with its mitigation, because a mitigation recorded elsewhere does not get applied — see §0.

---

## 0. The meta-failure: a lesson recorded in the wrong place is inert

**Measured twice, three days apart.** Cause `S` (predicting an outcome that required violating a constraint I had written myself) fired on ticket 99. I named the cause, wrote the fix — *"state the metric as of the dispatched scope"* — into that ticket's scoring file, and **never re-read it**. It fired again identically on ticket 104.

**Mitigation, and it is the one that makes the rest of this document worth writing:** a corrective must live where it will be *re-encountered*, not where it was discovered. In this setup that means auto-memory (loaded every session) or a `.claude/rules/` file (loaded on path match). A per-ticket artifact is a record, not a control.

---

## 1. "The parse succeeded" read as "the parse was correct" — green for the wrong reason

**The single most repeated instrument failure, four measured instances:**

| instance | what looked true | what was true |
|---|---|---|
| ticket 18 replay | "zero flips across 53,112 decisions" | a permissive `no_match_fallback` made the transition unobservable |
| ticket 19 isolation | HEAD and working tree "agreed exactly" | both runs imported the working tree; `sys.path[0]` differs between `-c` and a script |
| ticket 98 chunk 2 | corpus reported zero decision changes | none of its 6,401 cases contained the three shapes being fixed |
| ticket 105 | grammar "already recognises comments" | the `comment` rule fired **zero times**; `#` was absorbed as an ordinary word |
| ticket 88 | 6/6 dangerous `find` invocations excluded | 2 of the 6 would have been excluded with the rule **deleted** |

**Mitigations, in order of strength:**
1. **Include a control that SHOULD fail.** If it passes too, the instrument is broken, not the code. This caught the `extract_structured_from_grammar` string-vs-tree bug immediately.
2. **A passing control validates the instrument for ONE class of error only.** In ticket 105 a control passed, which is exactly why confidence was high — it caught a different mistake than the one being made. Name the specific wrong answer the control would catch, and check it is the wrong answer you are worried about.
3. **Delete the mechanism under test and confirm the result changes.** Two of ticket 88's six green rows survived deletion of the rule.
4. **Treat a symmetric or universally-clean null as suspicious**, not as proof.

---

## 2. Judging a thing by its shape instead of reading it

**Three instances, all mine, all wrong in the tidy direction:**
- `DEFAULT_COMMAND_PAYLOAD_KEY = _COMMAND_PAYLOAD_KEY` flagged as an alias re-export. Its docstring says it is the fallback payload key for a tool with no registry entry — a **policy default defined by reference to the contract**. Judged by the assignment's form, not its meaning.
- Ticket 88 filed as *"deny-with-exception recipe needs a workable example"*, which reads as *the recipe is missing*. The body said the recipe's **example** was wrong. I satisfied the title and contradicted the body.
- `.claude/skills/…/SKILL.md` edited as if it were the source. It is an **install target**; the distributed copy is `skills/` at the repo root. The defect kept shipping.

**Mitigation:** before acting on a ticket, re-read its **body** immediately before committing, not when the work was planned. Before editing a file found by grep, ask *"is this the source or a copy?"* — a symlink or an install target looks exactly like the real file.

---

## 3. Stating a count or a sole-consumer claim from partial reading

**Four times an implementer corrected a factual claim in my brief**, always the same shape:
- "`mining.py` is the one real consumer of `LeafCommand`" — `compound.py` imports it too.
- "`_discover_rules_files` has zero callers" — five tests called it.
- "case 16 was already fixed by the ticket-19 repair" — it was not; it also leaked the heredoc body into the leaf list.
- "`additionalContext` is wire-protocol material" — it is toolguard's own TOML rule-schema key.

**Mitigation, and it demonstrably works:** put *"do not take my word for any of this — verify it yourself"* in every brief. All four corrections came back from agents that were told to check. The cost is one paragraph; the alternative is building on a false premise.

---

## 4. Under-modelling: dicts where a type belongs, and the literals that follow

**A dict crossing a module boundary is a type nobody declared.** Every `d["key"]` at the far end is a field access on it. The string literals proliferate *because there is no type to hang them on* — which is why a dedicated literals-to-constants cleanup ticket did not stop the pattern recurring in every new module.

**Mitigation:** `architecture_fitness.py --undeclared-types`, which flags public functions returning a bare dict across a module boundary. **The return annotation is the declaration it checks against**, so it measures conformance rather than supplying a judgement. Reported 4 findings at the end of TOO-45.

---

## 5. One structure answering two questions

Recurring across the whole campaign:
- `CommandUnit.kind` decided both *which policy applies* and *whether there is anything to resolve* (ticket 97).
- `audit_parts` / `deny_check_parts` are checked identically and differ only in **audit visibility** — one concept partitioned by a reporting property (ticket 106, declined on evidence).
- A shared `CommandSpellings` pair widened for one consumer silently changed the other, twice — once downgrading an unoverridable `hard_deny` to `ask` with a green suite.

**Mitigation:** when a docstring must explain how field B differs from field A, that is the signal. Ask whether the difference is a *property of an element* rather than a *partition between fields*. And never widen a shared structure for one consumer without checking the other.

---

## 6. Widening a shared surface to admit one case

**Ticket 101, caught pre-commit.** To accept a bare `{}`, the first attempt removed `{` and `}` from the grammar's shared `delimiter` class. The target cases parsed — and `{ rm -rf /tmp/zz; }` went **deny → allow**, because `brace_group` needs `}` to be a delimiter in order to close.

**Mitigation:** never widen or narrow a shared character class, table, or type to admit one token. Add an explicit alternative at the specific position: `unquoted_word <- (escaped_char / var_ref / "{}" / !delimiter .)+`, braces left alone.

---

## 7. Compression introducing false universals

Measured across seven consecutive comment-editing passes: shortening a hedged statement reliably produces "only", "every", "never" where the original was qualified, because the short form wants a crisp rule and reality is not crisp.

**Mitigation:** when shortening makes a statement inaccurate, ask whether it earns its place at all. A claim that resists compression is usually carrying more detail than it is worth — deleting it outright is often better than a more careful short form.

---

## 8. Silence mistaken for failure — the diagnosis that was mine

Two grammar agents went 90+ minutes without a write. I diagnosed "the agent went quiet", took both over, and reported it as agent behaviour. **They were blocked on a permission prompt, and my own briefs specified `npx canopy@latest`** — a network fetch that prompts. Running canopy myself, I used a cached path and was never prompted, so I never saw what I had handed them. The second agent had been working correctly throughout.

**Mitigation:** before putting a command in a brief, ask whether it prompts. **A blocked agent is indistinguishable from a stalled one and cannot tell you which it is.** Check for a pending prompt before concluding an agent stalled.

## 9. Declaring completion over work that was not done — added 2026-08-25

**Arnon named this as a repeating failure mode and it was missing from this list**, which is itself an instance of the mode: a document enumerating my failures, delivered as complete, with this one absent.

> *"You tend to forget what you were supposed to do and declare early completion before work is actually done."*

**Three measured instances in this corpus, none of which any test, review or instrument could have caught:**

- **A mandated step, dropped campaign-wide.** The TOO-19 plan mandates four TDD steps ending *"refactor while green."* **All three** implementation reports restate it as **three**, and **0** files anywhere in `toolguard-memories/` carry a phase-shaped refactor line — while the control fires (planning 20, implementation 32). (`12` A11)
- **A class fixed in 2 of 3 instances, reported as fixed.** Item 10's review identified the right defect class; the sweep left the third file — `hook.py`, *the component that governs*. **Every non-builtin governed tool was bricked for eleven days**, and ticket 74 re-derived it from scratch five days later. (`07` C1)
- **23 of 28 open tickets lost across one compaction.** My resume note said *"then batches 2-4 from `<file>`"*; I acted on the two inline items, never opened the file, and reported a five-item queue. **Arnon caught it by noticing the queue looked short against his own recollection** — no check of mine would ever have fired.

**The mechanism, and it is the one §8 and C4 both name in other clothes: "done" is unfalsifiable unless something enumerated it first.** A11's diagnosis is exact — *"the agent tracked the steps that could be checked… and did not perceive the one that could not. **Not refusal, not eagerness — not encoded.**"* This is not forgetting in the ordinary sense. It is that **nothing in the work makes an absent step observable**: the code compiles, the tests pass, the report reads as finished, and the omission leaves no artifact. It is the campaign's signature defect — *fails open and says nothing* — applied to the work plan rather than to a mechanism.

**Mitigation: a punch list, enumerated inline, reviewable by both of us.** Convert any non-trivial sequence into individually checkable items before starting, and report against that list rather than in prose. This converts "done" from an assertion into conformance with a declaration, which is the same principle that makes an architecture check strong (`12` A10). **Arnon's assessment**: *"whenever we did that, the likelihood of forgetting parts dropped significantly. Not 100% eliminated, but much better."* **Checked 2026-08-25 and supported for the one incident that has both halves**: the 5-reported-against-28 queue was followed by `TOO-45-punch-list-2026-08-20.md` — 34 items enumerated inline, no pointers — and **no successor artifact reintroduces the failure**. The evidence is structural rather than an absence of complaints: the successors carry the rule in their own text (*"Every item spelled out inline. Do not replace an item with a pointer to another file"*), so the remediation lives in the artifact instead of in someone's memory. **One incident, a five-day window, no rate.** Full treatment in `09` §13.

**The boundary where this actually bites is compaction, and it has a second mitigation** (added 2026-08-25). All three instances above involve losing track across a discontinuity, and the worst — 23 of 28 — happened **across a compaction**. Arnon's habit: *"I started telling you every time I was about to either exit the session or compact… you started responding by writing down continuation memories."* **This is not verification — it preserves context rather than checking anything** — and its effectiveness is **not measurable here**: there is no counterfactual, and he says so himself. Recorded as his dated subjective assessment, corroborated only by the fact that the campaign's single worst tracking loss was compaction-caused. **The receiving half can be automated and the plumbing already exists** — a `SessionStart` hook with matcher `compact` has its stdout added to context, and one already fires in this repo. See `12` B13.

**The mitigation has its own failure mode and it is the one that bit hardest.** A punch list that *points* — *"batches 2-4 from X"* — reads like a finished sentence while carrying none of the content, so nothing triggers a re-read. **Enumerate every item inline, by identifier and one line; a cross-reference is for detail, never for membership.** (`feedback_punch_lists_must_enumerate`)

---

# CORRECTIONS FROM THE VERIFICATION PASS, 2026-08-23

This document was written before any verification and is **not exempt** from it. Four adversarial passes over the sibling summaries checked roughly 460 claims and refuted or misattributed about 24. Two of those corrections apply directly to claims repeated here, and a third is a claim I relayed to Arnon that this document is now the only surviving record of.

## C1 — §1's instance list is right; the "three instances" phrasing elsewhere is not

The green-for-the-wrong-reason table above lists five instances and is accurate. But a sibling summary claimed **"three instances"** where **four** are recorded, and I repeated a three-instance framing to Arnon in conversation. **Use the table, not the count.**

## C2 — the two-phase `.peg` practice: direction confirmed, "clean" is wrong

I have described the two `.peg`-only reviews as the only clean passes in ~24 review rounds. Verified: the census is **30 rounds, 2 PASS, 28 non-peg** — direction confirmed and **understated**. But the PASSes were **not clean**: the first raised M1, *"four bypasses that defeat the ticket's purpose"*, and required a second phase-1 round.

**And its only stated cost was false.** *"Ticket 101 stood down mid-task with zero net change shipped"* — commit `03d922c` shipped Item 101 plus `test_deny_penetrates_constructs.py`. What stood down was one coder run. The practice is well supported; the cost line was not.

## C3 — "blinded recall predicts cost" is REFUTED, and I relayed it as a headline

I told Arnon this was among the findings most likely to change future work. It rests on ticket 79 being the campaign's most expensive item. **The corpus itself retracts that**, under a heading reading *"THE CORRECTION THAT MATTERS — I have been costing tickets in the wrong currency"*: **4h15m wall-clock, below the phase-3 average, less than half of ticket 78.**

The recall range quoted with it (**"100% down to 15.2%"**) also mixes two instruments under one label: under the **production-only** scoring Arnon selected, the floor is **13.8%** and **five** items reach 100%. 15.2% is the all-files column.

**Do not carry this claim forward.** If the relationship is real it has not been shown, and the ticket that anchored it was mis-costed.

## C4 — the mechanism behind every verification failure, which belongs in §1

Across ~460 checked claims the failures fell into exactly three shapes, and all three are refinements of §1 rather than new items:

1. **A number taken one link up the chain** — quoted from a summary rather than measured from source. Transitive citation. One figure stamped `[MEASURED]` re-measured to more than three times its stated value.
2. **A note read as an outcome where git says otherwise.** Two independent summaries did this; one called a ticket "IN FLIGHT" that had been committed **three minutes earlier**, another counted 15 closed tickets as open.
3. **A qualitative sentence promoted to a measurement** — an author's own commentary later quoted as the user's decision, or a hedged phrase re-quoted with its scoping clause elided.

**Mitigation, and it is the one that generalises:** for any claim resting on what a note SAYS, check what the repo DID. `git log`, the file itself, a re-run of the tool. The corpus is a record of what people believed at the time, not of what is true now.

---

## An agent destroying another agent's evidence in shared state

**Rescued 2026-08-23 from `TOO-45/reports/TOO-45 review-18-round4 repair - coder implementation report.md`, which is on the delete list and is untracked.** Nothing else in this corpus records the incident, and it is a failure mode none of the other entries here covers.

**What happened, in the agent's own words:** *"While cleaning up my own probe scripts I ran `rm -rf *.py` in the session scratchpad ... assuming it only held files from this task. It does not -- that directory is shared across the whole TOO-45 review/repair campaign and contained hundreds of files from prior rounds. My glob deleted, at minimum, `probe_counterexample.py`, `probe_guidance.py`, `probe_old_vs_new.py`, and `scan_rules.py` -- exactly the four files review-18-round4.md cites as "Evidence:" for B1/B2/B3 ... This is very likely unrecoverable."*

**The mechanism, which is what generalises.** The agent's model of the directory was *"my working area for this task"*. The directory's actual scope is *the whole campaign*. Nothing in the path says so, nothing warned, and the glob was scoped to a file type rather than to the files it had authored. **It deleted precisely the artifacts a previous round had cited by name as its evidence** — not a random sample, because probe scripts are exactly what a review cites and exactly what a cleanup targets.

**Why the damage was survivable, and why that is not reassurance.** The agent noted honestly that the round's prose already quoted the material output (the 8/8 vs 1/8 table, the 14/15-DENY table), and that its own task required re-verifying every claim by fresh execution — which it did, *"with results consistent with or slightly stronger than the deleted probes'."* So no finding rested solely on the deleted files. **That is luck plus an unrelated task requirement, not a safeguard.** Had the next round been a citation check rather than a re-verification, the evidence would simply have been gone.

**Its own recommended mitigation:** *"`ls` the scratchpad before any wildcard delete there, and prefer deleting only the specific filenames just written rather than a glob."*

**This is live, not historical — recorded 2026-08-23.** The scratchpad path in that report (`/tmp/claude-1000/.../19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad`) is **the same directory this session is writing probe scripts into tonight**, and it currently holds eight of them. The shared-state hazard was never mitigated by anything structural; the campaign simply did not repeat the mistake. **A per-agent subdirectory, or a rule against wildcard deletes in a shared scratchpad, would make it structural** — which is the difference this corpus repeatedly finds between an instruction and a mechanism.
