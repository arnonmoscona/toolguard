---
title: TOO-28 specification
type: note
tags:
- task-memory
- TOO-28
- specification
permalink: toolguard/too-28/too-28-specification
---

# TOO-28 — auto-mode-aware toolguard behaviour: what we are building, and why

**Status: DRAFT FOR REVIEW.** Synthesis of the ticket description plus all nine comments, several of which retract or reverse the description. Written 2026-09-03, before any planning.

> ## AMENDED 2026-09-05 — read this before the body
>
> **The body below is unchanged on purpose.** The raw touch-set estimate was sealed against it on 2026-09-04, so rewriting it would destroy the record of what was estimated against. Four things in it are now superseded. The amendments live in `TOO-28 implementation plan.md` §7; in summary:
>
> 1. **§4.3** — *"the per-interpreter file-flag detection above is new work"* is **partly false**. `_ExecutorFlags.program_file_letters` and `bare_program` already exist and are populated for `awk` and `php`. The work is completing coverage, not building detection.
> 2. **§9** — the **"blocking prerequisite" status is lifted**. Documentation fetched 2026-09-05 plus this repository's own `<TEMPORARY>` fallback (which exists *because* toolguard ASKs stalled unattended auto-mode runs) settle that a toolguard `ask` and `deny` both bind in auto mode. Nothing in the design is contingent.
> 3. **§9** — `autoMode.classifyAllShell` **appears in neither current documentation page**. Renamed, removed, or never there. A worked example of why a `[native]` claim carries a date.
> 4. **§4.1's tail** — *"Install, security-audit and possibly maintenance flows must become aware..."* is **out of scope for TOO-28**, decided 2026-09-05. It is **TOO-77**, linked to this ticket. Without this amendment the ticket would be unfinishable against its own text.
> 5. **§6.1 STANDS. One clarification only — 2026-09-07.** It is **`no_match_fallback`** that covers an unrecognised interpreter, not `undecidable_fallback`: the command is never classified undecidable, so the ASK floor does not apply. Both are §4.1 settings and both are now auto-mode-aware, so §6.1's conclusion — that the question dissolves into a capability this ticket already has — is correct as written.
>
>     I briefly recorded this as a false premise and a security gap. **That was wrong**, and Arnon corrected it: writing a rule for an interpreter toolguard has not been told about takes that command out of fallback coverage, which is what a rule does; toolguard cannot know `lua` is an interpreter without being told, and inferring it would need the heuristic this project deliberately does not have. The residue is one documentation line, not a defect — see §4.5.

    **For §4.5**: a user who sets `undecidable_fallback` stricter than `no_match_fallback` is expressing *"I distrust foreign inline code"*, and that protection reaches only the interpreters in `FOREIGN_EXECUTORS`. Worth one sentence where those settings are documented, so nobody assumes it is exhaustive.
>
> **A provenance gap worth knowing**: this file was uncommitted when the raw estimate was sealed — it is one of the five paths in that record's `ignored_dirty`. So the exact bytes estimated against are not recoverable from git. Nothing to fix retroactively; a reason to commit a spec before sealing against it next time.

**This states WHAT and WHY, never HOW.** It names no module, no file and no design choice. That is deliberate twice over: choosing a shape is planning, and this document is also the input to a blinded touch-set estimate, so naming files would turn the estimate into transcription.

**Open questions are named, not resolved.** Where the thread deliberately left two options side by side, both are recorded as open. Resolving them here would make this a plan.

---

## 1. The design goal, stated for the first time in comment 2

> **"More security with less friction."**

And the boundary that goes with it: *"we do not and will not claim 100% secure."* Both halves matter. A change that adds security by adding friction is not automatically a win, and a gap that cannot be closed without unacceptable friction is an accepted limit rather than a defect.

## 2. Why this ticket exists at all — the division of labour

From comment 8, and this is the frame everything else hangs on.

| | decides by | strong where | blind where |
|---|---|---|---|
| **toolguard** | exact pattern match | anything expressible as a rule; exact, testable, versioned, auditable | anything it cannot parse or pattern |
| **auto-mode guidance** | semantic judgement | undecomposable blobs, intent, novel shapes | exactness, repeatability, auditability |

These are complementary halves with inverted strengths, **not two implementations of one control**. toolguard's blind spot is constitutive, not an unimplemented gap: compound commands it cannot decompose, heredocs, foreign inline code, a script whose contents it never sees. The ASK floor and `undecidable_fallback` exist precisely to announce it — toolguard saying *"I cannot read this."*

**Therefore TOO-28 is about the INTERFACE, not absorption.** Every setting it adds is a **handoff point**: a declaration of how much to trust the other half for a specific class of case. They are not "auto-mode variants of existing settings."

**The design smell to avoid:** *"make toolguard smarter so it can handle X."* If X requires reading intent, the answer is auto-mode guidance, not a cleverer rule.

## 3. The trigger fact

`permission_mode` is present on **every** `PreToolUse` hook call. toolguard does not currently read it. No transcript parsing is needed to know the mode at decision time.

This supersedes an earlier assumption on file that permission-mode was visible only by scanning the session transcript.

## 4. What is IN scope

### 4.1 Auto-mode-aware fallbacks — **two settings, not one**

toolguard must be able to resolve a *different* fallback when running under auto mode:

- **no-match** — "no rule matched this action"
- **undecidable** — "I could not decompose this command safely"

**They must be independently configurable.** You might reasonably trust the classifier with an unmatched-but-parseable command while still refusing to hand it something toolguard itself could not read. A single flag would silently couple two different decisions.

**Why this is wanted:** in an unattended run, an ASK that nobody answers stalls the session. Where the user trusts Claude Code's auto-mode classifier, toolguard's ASK in these two cases is redundant friction rather than protection — the classifier is a second gate, and toolguard's `deny` and `hard_deny` still resolve first. Only the ASK tier relaxes.

Install, security-audit and possibly maintenance flows must become aware of the new configuration, and the install flow should explain it and seek the user's decision rather than choosing for them.

### 4.2 Per-rule auto-mode override

An individual rule must be able to declare that its decision differs under auto mode.

**Both directions are wanted, on one field:**

- **Widening** (`ask`/floor → `allow` in auto mode) — the primary case. Intent-disclosure and read-only-attestation: today an attested, undecidable-but-declared operation costs a prompt in every mode.
- **Narrowing** (`ask` → `deny` in auto mode) — the config-protection case: friction exactly where human judgement is absent. Unaffected by the retraction in §7, because a `deny` blocks in either mode.

**Live use case, comment 9:** the disclosure-nudge rule added 2026-08-28 is currently an `allow` with `additionalContext`. Once this ticket lands it should become an `ask` with an auto-mode override.

**Constraint:** an auto-mode override on an `allow` entry must never carve an exception out of a `[hard_deny]`.

### 4.3 Input-source constraint on a rule

Express "treat this command differently depending on whether its executable material comes from a file".

**The distinction is VISIBILITY, and it is binary.** Decided 2026-09-04. The vocabulary is *is a file* versus *is not a file* — not an enumeration of heredoc, pipe, stdin, redirect, inline. Enumerating is cumbersome and no case has been identified where a pipe and a heredoc would be treated differently.

What actually separates the two cases is whether the executable material is **visible**, and it is invisible in two distinct ways at once:

- **To the human**, at an ASK prompt: you can see what is printed in the terminal; you cannot see what is inside a file without extra work.
- **To toolguard**: it cannot match against the contents of a file. A rule can constrain what it can read, and only that.

A redirect *from a file* counts as a file. The relevant question is where the material is, not how it arrived.

**Shape: the existing rule-enrichment mechanism, not a new pattern-syntax variant.** Decided 2026-09-04, as more flexible than adding a fifth dialect alongside DEFAULT/REGEX/GLOB/NATIVE, and because it composes with all four unchanged. A plausible structure is pairs or a mapping of matcher → outcome; the exact form is a design question, not a requirement.

**Scope: all known interpreters, not Bash only.** Decided 2026-09-04. For each known interpreter, toolguard must be able to detect that the executable material is in a file — `awk -f file`, `awk --file script`, and the equivalents for the shells, Python and the other recognised foreign interpreters.

**The underlying classification largely exists already** — it is what drives the current ASK floor. This exposes it to rule authors rather than deriving it anew, though the per-interpreter *file-flag* detection above is new work.

**A smell to look at, with no conclusion attached.** A search for the interpreter list turned up several different lists in the same module, covering different sets. Not investigated further, and **not a requirement**. It might be cleanup; it might be something this requirement makes a material difference to; it might be deliberate. Look at it during design, establish what each list was for, and decide then — collapsing a distinction somebody made on purpose would be worse than leaving three lists alone.

### 4.4 Data collection for the auto-mode gap

**In scope.** Decided 2026-09-04. When no toolguard rule matched **and** the mode is auto, record what happened in a dedicated log — independently of Claude Code's own transcripts.

**Why:** it enables after-the-fact analysis of what the auto-mode classifier actually allows, in order to improve the auto-mode guidance and to add toolguard rules where a pattern turns out to be expressible. That is the **feedback loop for the other half of §2's division of labour**, which currently has none.

**This does not contradict §2.** The analysis is offline, out-of-band and human-directed. Nothing in the decision path judges meaning; toolguard only records what it deferred and what came back.

**A SEPARATE log, not the normal decision log.** Decided 2026-09-04, resolving a question the ticket description left open. The existing toolguard log continues unchanged; this is a distinct log whose sole purpose is analysing Claude's auto-mode decisions. Keeping them apart keeps the normal log's meaning stable and gives the analysis a corpus that is about one question.

**Why a dedicated log rather than transcripts:** measured during this campaign — dedicated logs proved more effective for analysis than reconstructing the same information from transcripts, which have real gaps. Since `permission_mode` is available live on every call (§3), toolguard can record this itself going forward rather than reconstructing it afterwards.

**It also removes the need for an escape hatch.** See §6, decided question 7.

### 4.5 Documentation

Part of this ticket, not a follow-up. Verified 2026-08-03: none of §2 is written down anywhere.

- The division of labour, stating plainly that toolguard's blind spot is by design.
- A pointer early enough that someone orienting themselves meets it.
- The new settings framed as **handoff points**, not as auto-mode variants.
- The design smell in §2, named explicitly.

**Why it is in scope:** a load-bearing architectural decision that lives only in one person's head is one refactor away from being silently optimised away with no test failing.

## 5. What is OUT

**toolguard will not ship a classifier, and will never judge meaning.** Sub-part 2's "pluggable auto-mode classifier" is cut. toolguard has no AI-driven component by deliberate design.

The **data-collection** half of sub-part 2 survives and is in scope — see §4.4.

## 6. Questions raised and settled

**No open questions remain.** Recorded here rather than deleted, so nobody re-derives them from the ticket thread.

### 6.1 Unknown interpreters — settled 2026-09-04, and the answer is §4.1

**Not a gap for this ticket to close. It is the thing the fallbacks are for.**

An interpreter toolguard does not recognise is something it can never directly handle, so it falls through to the fallback — and making those fallbacks auto-mode-aware is exactly what §4.1 does. The question dissolves into a capability the ticket already has.

**No user-supplied interpreter list.** There is no evidence of need for one yet.

**The governing principle, which belongs on the record:**

> **toolguard features are developed in response to a need supported by evidence.**

The existing interpreter list was built on two criteria: the interpreter is **super-common**, and there is **evidence of Claude using it**. Logs are collected and analysed often enough that new interpreter behaviour will surface; if it does, the list can be extended then. Building for interpreters nobody has been observed using is speculative work.

This also bounds §1 from the other side: we will not claim watertight, and we will not pre-emptively add machinery for a need that has not appeared.

### 6.2 Decided 2026-09-04 — recorded so they are not reopened

| # | question | answer |
|---|---|---|
| 1 | Input-source shape | **The existing rule-enrichment mechanism**, not a fifth pattern syntax. More flexible; composes with all four existing types. Plausible structure: pairs or a matcher → outcome mapping |
| 2 | Input-source vocabulary | **Binary: is a file / is not a file.** The distinction is visibility, not transport. See §4.3 |
| 3 | Allow-list vs deny-list | **Dissolved by 2.** With a binary distinction there is nothing to list — a rule states which of the two cases it requires |
| 4 | Bash only? | **No — all known interpreters**, with per-interpreter detection of the read-program-from-file flag |
| 5 | Does the data collector survive? | **Yes** — §4.4 |
| 7 | An explicit escape hatch (`dangerously_allow_as_floor_in_auto_mode`) | **Not needed.** A top-level fallback setting plus the §4.4 audit trail leaves it no remaining function |
| 6 | Unknown-interpreter coverage | **Handled by the fallbacks** — see §6.1. No user-supplied list |
| 8 | TOO-40 low-hanging fruit | **Out of scope for now** |
| — | Where the auto-mode log lives | **Its own log**, separate from the normal decision log — §4.4. Resolves a question the description left open |
| — | Consolidating the interpreter lists | **A smell, not a requirement** — §4.3. Look, establish what each list was for, decide during design |

## 7. Retracted — do not re-derive from the thread

**An earlier comment claimed a toolguard ASK does not block in auto mode.** That is **false** and was retracted twice, in comments 5 and 7.

An ASK returned by a `PreToolUse` hook is a real permission request; auto mode does not bypass it. The "auto-accepts ask" behaviour belongs to the *native* permission path, which is not in play under takeover mode.

Two consequences, both load-bearing:

- The 2026-07-25 live-config incident is **not** explained by ask-bypass. The agent's edits matched an explicit broad `Edit` allow rule. An allow let them through — a plainer and more actionable diagnosis.
- The per-rule override's motivation **inverts**: from "add friction where nobody is watching" to "remove redundant friction where a second gate already exists". The narrowing direction remains wanted, but it is no longer the justification.

The word *"Measured"* in the retracted comment was not justified: a logged ASK followed by execution is exactly what an approved prompt looks like, and the log cannot distinguish the two.

## 8. Invariant

**Parse failure is permanently exempt.** No auto-mode flag, present or future, may downgrade a parse-failure ASK.

A parse failure is not a policy question: toolguard does not know what its rules *are*, so it has no basis for any verdict, and the classifier cannot compensate for rules it never saw. Relaxing it would produce a genuine silent-allow. **Any future flag touching fallback behaviour must carry a test asserting the parse-failure path is unaffected.**

## 9. Blocking prerequisite

**Does a `PreToolUse` hook returning `allow` bypass the auto-mode classifier?**

The entire rationale for relaxing ASK in auto mode assumes the classifier still judges an action toolguard allowed. **If a hook `allow` causes Claude Code to skip the classifier, then relaxing ASK removes BOTH gates rather than one, and the reasoning inverts completely.**

Not hypothetical: narrow *native* Bash allow rules are documented to bypass the classifier unless `autoMode.classifyAllShell` is set. A hook allow behaving the same way is the likely default, not the surprising case. If it does, the capability would need `autoMode.classifyAllShell` alongside it to be safe, at a per-command latency cost.

**To be settled by an explicit manual test** — not by inference from toolguard's logs, and not from documentation alone. That is a prerequisite for the design, not a detail to discover during it. (This project's own rule applies: a claim about native behaviour must be fetched and quoted with a date, never recalled.)

## 10. Related

- **TOO-19** — its rule-enrichment mechanism is the natural carrier for both the auto-mode override and the input-source field. Whether it already provides what is needed is a scoping question.
- **TOO-40** — out of scope for now (decided 2026-09-04).
- **TOO-18** — **defunct.** The original idea; its claims are not entirely correct. Retained for preservation and cross-check only. **Not an input to this work.**

---

## Sign-off checklist — round 3

**No open questions remain.** Everything raised across two rounds is settled and recorded in §6.

What is left is confirming that the writing is faithful. Two sentences are mine rather than yours, and both are load-bearing:

- [ ] **§4.3** — *"the distinction is visibility, and it is binary"*, invisible in two ways at once: to the human at an ASK prompt, and to toolguard which cannot match file contents. Also that a redirect *from a file* counts as a file, since the question is where the material is rather than how it arrived. Faithful, or over-tightened?
- [ ] **§4.4** — the data collector framed as the feedback loop for the *guidance* half of §2: offline, out-of-band, human-directed, never in the decision path. That framing is what keeps it consistent with "toolguard never judges meaning".

And a last read of the scope itself:

- [ ] §1 — the goal as you mean it, including §6.1's evidence principle as its other bound?
- [ ] §4.1 / §4.2 — two independent settings; both directions on one field?
- [ ] Anything in §4 that should be dropped or deferred to its own ticket?

**When this reads right, the spec is done and the raw estimate can be sealed against it.**