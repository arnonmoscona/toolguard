---
title: TOO-45 — what is still open
type: note
tags:
- TOO-45
- durable
- open-questions
permalink: toolguard/durable/intermediate/open-questions
---

# TOO-45 — what is still open

**Extracted 2026-08-23 from `toolguard-memories/TOO-45/`, so that the notes can be deleted.** Every item below is something that was started and not finished, decided provisionally, disagreed about, or explicitly deferred. A finished conclusion survives in the code and in git; these do not.

**State of the branch at extraction time**: `too-45` at `9b4ff1d`, **78 commits, nothing pushed**. Suite 4008 OK (4 expected failures), `corpus_build.py --verify` clean, ruff clean, `--stdlib --ambient --layers --orphans --undeclared-types` all pass, version 0.6.0 unreleased. The punch list is exhausted; **everything remaining needs a decision from Arnon.**

**Corrected 2026-08-23 (three corrections to the paragraph above).** (1) The original said the branch was at `715cdbd` with **77 commits**. Verification measured HEAD as `9b4ff1d`, committed 16:07:18 — three minutes before this file was written at 16:10:09 — with `git rev-list --count master..too-45` = **78**. `715cdbd` was already the parent. (2) "Nothing pushed" is confirmed: `origin` has no `too-45` ref. (3) The original ended *"and nothing is blocked on work"*. That clause is the summarising agent's addition — the cited source (`TOO-45 phase 3 resume.md`, FINAL STATE) says only *"The punch list is exhausted; everything remaining needs a decision from him"* — and the body of this document contradicts it three times: §4 lists items (3), (5), (7), (8) as unscheduled work, and §11 is explicitly blocked on running more reviews. The clause is removed rather than rephrased.

Three distinctions are kept explicit throughout, because the notes blur them: **decided-but-not-implemented** vs **genuinely undecided**; **deferred with a reason** vs **dropped silently**; **an experiment still running** vs **one concluded**.

---

## 1. The surprise-factor experiment is RUNNING, and it is 0 of 20 through its restarted count

**Sources**: `TOO-45/reports/surprise/CONSOLIDATED-REPORT.md` (the verdict plus Arnon's 2026-08-21 decision), `CONSOLIDATED-BATCH-2.md` (current position), `RESULTS-LOG.md` (57 KB of primitives and per-item findings — 57,375 bytes exactly), `TOO-45/reports/surprise-factor-protocol.md` (the fixed scoring rules), `PRODUCTION-ONLY-SCORING.md`, and **62 `NN-prereg.md` / `NN-scored.md` files, i.e. roughly 31 pairs** (directory total 110 files).

**Corrected 2026-08-23:** the original said *"~60 pairs"*, which is right for the file count and 2x wrong for the pair count; and it placed `surprise-factor-protocol.md` inside `reports/surprise/` when it is one level up, in `reports/`.

**The question.** Before a ticket is implemented, a blinded estimator predicts which files it will touch. The gap between prediction and the final diff is the "surprise factor". The original question was *"is the estimator accurate?"* — Arnon corrected that on 2026-08-21: *"The estimator is not the objective here - it's a means to an end. The value is in surfacing what we really need to look at so that we catch problems early and don't let them slide."* **A low recall is a prompt to investigate, not a grade.**

**What is already known.** Fifteen items scored in phase 1-2 (recall 15.2% to 100%), then a second batch of thirteen. As a predictor the measure is **weak and heavily confounded** — by ticket leak (some tickets name their own files, sometimes with line numbers, so recall measures transcription: item 03 scores 64.4% raw and **12.0% unleaked**), by design leak (item 77 got its design and scored 9/9 production; item 80 the same day without it scored 5/9), and by scope impurity (**608 of item 10's 620 unpredicted lines belong to three bodies of work its ticket does not contain**). As an instrument for finding things out about the codebase it **earned its cost**: it produced the doc-file and test-file identity findings, the fitness-ratchet property, and two cases where a blinded estimator saw something the coordinator missed.

The single most useful thing it produced is the **scope asymmetry**: over-scoping is the normal failure and is nearly free; under-scoping is rare and expensive — **3 of 32 missed production files carry 811 of 958 missed lines (85%)**, and *every* large under-scope is a new module or a control-flow relocation, never a call-site sweep. Hence the one question worth asking an estimator: **"does this change carve out a new module, or relocate control flow?"**

**Arnon's two decisions, 2026-08-21, both still in force**: (1) **continue until at least 20 human-authored tickets have completed through the normal process** — plan authored, reviewed and discussed, then implemented; (2) **switch the headline metric to production files only** (`toolguard/`, `tools/`).

**Distance from the target: ZERO of 20** — *this total is a derivation, not a figure any source states*. `CONSOLIDATED-BATCH-2.md` states verbatim only that *"this batch added none"*; the zero follows from every post-2026-08-21 item (95, 97, 98, 99, 88, 89, 100, 101, 103, 104, 105, 108) being coordinator-filed or explicitly labelled an informed estimate, which `108-prereg.md` says of itself in its second line. Verification re-checked the derivation and found it sound. Batch 2 added none. The reason is the eligibility rule and it is the operational heart of the whole thing: **eligibility is destroyed by whoever MEASURES the target first, not by whoever NOTICES the problem.** Tickets 98 and 99 were substantively Arnon's findings and would have been exactly the human-authored data points the restarted count needs; the coordinator's own spike-and-plan work spent them before an estimate was locked. **To reach 20, the estimate must be locked at the moment a ticket is filed, before any investigation** — a change to *when* the step happens, not to the step. Lose that sentence and the count will never move, because every future ticket will be investigated before it is estimated, exactly as these were.

**What would settle it**: 20 tickets, each with a raw estimate locked at filing time. Nothing else.

**Blocked on**: more data — 20 tickets' worth, arriving through normal development, not through a cleanup campaign.

**If lost**: the experiment silently ends at "production recall is near 100%", which `CONSOLIDATED-BATCH-2.md` explicitly warns is **not evidence the estimator works** — it is evidence that an author predicts their own scope well, because the coordinator wrote the tickets, the briefs and the estimates. That is a badly misleading resting place: a confident-looking number produced by a population the report itself calls unrepresentative. (*"The most misleading possible resting place"* in the original was an unlabelled superlative that nothing measures; the caveat itself is verbatim from batch 2.)

### 1a. The two-estimate (raw / informed) protocol was AGREED and has NEVER BEEN RUN

**Source**: `CONSOLIDATED-REPORT.md`, section "The two-estimate protocol, per Arnon 2026-08-21".

Score **both**: a **raw** estimate against the ticket, and an **informed** estimate against the agreed plan. Raw measures *how well-specified the request was*; informed measures *whether we understood the work before starting*; raw→informed measures *what the planning conversation added*; informed→actual measures *what planning still could not see*. **The 2x2 between them is the actual instrument**, and the cell nobody looks for is **raw good / informed bad — planning made it worse**, which is the only cell that would justify planning *less* on some ticket class.

Two things must be recorded or the numbers lie: **tickets killed during planning** (no commit to score, so they vanish from the data while being planning's single clearest win — count them as a headline, *"N tickets killed at plan stage"*), and **scope changed during planning, with direction** (if planning halves the scope, the informed estimate scores against a smaller actual and looks better for the wrong reason).

**Not one ticket has both estimates.** Grep of `reports/surprise/*.md` finds the raw/informed vocabulary only in `108-prereg.md`, `95-prereg.md`, `98-chunk2-prereg.md` and the two consolidated reports — and in each case as a *label on a single informed estimate*, never as a pair. **Decided, never implemented.**

**What would settle it**: one ticket run with both estimates, in order, raw before the planning conversation.

### 1b. "PREMISE REFUTED" is a new outcome category with no scoring rule

**Source**: `TOO-45/reports/surprise/105-scored.md`.

Ticket 105 was dispatched, investigated, and **returned unbuilt because the ticket's premise was false** — the coordinator claimed `_strip_comments` was redundant; measurement showed the grammar's `comment` rule fires **zero times** on `echo hi # trailing comment` and that `#` is treated exactly like an ordinary word. Recall 0/0, precision 0/2. **The metric cannot express what happened**, which is why it was recorded. Every prior item either landed or was deferred on measured exposure; this is a third outcome and the series has no rule for it.

**What would settle it**: a decision on whether a refuted premise counts as a headline (like a plan-stage kill) or as excluded data. Given §1a already decided that plan-stage kills are a headline, the consistent answer is probably "headline" — but nobody has said so.

**If lost**: what `105-scored.md` calls *"the cleanest instance"* of confidence outrunning evidence **within the estimator series** goes with it. (**Corrected 2026-08-23:** the original called it the sharpest recorded instance *in the whole campaign* — a universal over a corpus nobody ranked, widening the source's scope from the estimator series to everything.) Arnon suspected the pre-pass was masking a PEG gap; the coordinator told him it was not; **he was right**. The mechanism is named in that file: *"I treated 'the parse succeeded' as 'the parse was correct'"*, with a passing control from a different error class making the instrument feel validated.

### 1c. Four instrument refinements proposed and never adopted

- **Cause code `N`** (defect introduced by the change itself) — three instances, all caught pre-commit. `CONSOLIDATED-BATCH-2.md`: *"`N` deserves separate reporting and separate severity"*, because two of the three failed **closed** and the third (ticket 101's brace-group delimiter change) failed **open** — deny → allow — and *"we caught it" reads identically in both cases*. A blinded touch-set estimate **can never predict `N`**, so counting it against recall is wrong.
- **Cause code `S`** (scope-conditioning failure: predicting the whole ticket while dispatching part of it). Fired twice, on 99 and 104. The corrective from the first instance was written into a per-ticket scoring file, never re-read, and **fired again three days later**. Now in auto-memory instead. Standing lesson: **a corrective recorded only in a per-ticket artifact is inert.**
- **Cause code `A`** (absorbed — a predicted spread that a seam contained). Arnon: *"Absorbed is not a bad classification as it goes. I wouldn't drop it so easily. Not yet at least. We'll see after we have stats on this large list."* **Explicitly deferred to the aggregate; the aggregate has not been taken.**
- **The "what did this make false?" question.** Proposed in `CONSOLIDATED-BATCH-2.md` for the next batch: for a behaviour-changing ticket, ask *"what did this make false?"* rather than *"what needs describing?"* Ticket 98 chunk 4 touched 5 files against a predicted 2, and the three missed were documents an **earlier chunk had silently invalidated**. Never adopted.

### 1d. The touch-set metric CANNOT SEE `.claude/`, and every affected item under-counts silently

**Source**: `RESULTS-LOG.md`, "The two findings that are about the INSTRUMENT".

`.claude/` is a symlink into `~/projects/dot_files`, so a ticket that edits a rule or skill file produces edits invisible to this repo's `git status` and to the scorer. Tickets 88 and 89 both did — for 89 the skill file was *the ticket's named root cause*. **Every earlier ticket touching a rule or skill file has the same hole.** Known, stated, unfixed.

**Related and now partly self-correcting**: commit `715cdbd` (2026-08-23) found the deeper version of this — the 88/89 fixes had gone into `.claude/skills/`, which is toolguard's **install target**, not its source. The shipped copies in `skills/` were still broken, and `.claude/skills/` turned out to be a **stale** copy predating a source fix. *"Editing it is editing site-packages."* That commit fixed the two files; the general hazard remains.

**Added 2026-08-23 (omission found in verification): that same commit broke a doc link, and `check_doc_links` FAILS at HEAD.** `uv run python tools/check_doc_links.py` reports `missing file skills/toolguard-security-audit/SKILL.md: ../../../docs/agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception` — *1 broken link(s)*. The anchor exists (`docs/agent-guides.md:207`); the relative path carries one `../` too many, and it was introduced by `715cdbd` itself (line 120 of its diff to that file). The original text praised the commit here and discussed the checker's blind spot in §9 without either place stating that the checker does not currently pass. **SUPERSEDED, same day, and this entry is itself an instance of the failure it describes.** The break was real at `715cdbd`, but the very next commit — **`305caa3`, subject *"TOO-45 - fix a link broken by porting the skill between directory depths"*** — fixed it. Re-run at `305caa3` on 2026-08-23 evening: *"All internal documentation links resolve."* The verification was written while HEAD was `715cdbd` and said "fails at HEAD" correctly for that moment; carrying the phrase forward one commit made it false. **Nothing to do before the push.** The transferable point is that "at HEAD" is a claim with a commit attached, and a document outlives the commit it was written against.

---

## 2. Ticket 108 is CLOSED — shipped as `9b4ff1d`, and the seam question was settled in the commit

**Corrected 2026-08-23. This section was wrong end to end and is the most important correction in the document.** It was written at 16:10:09; the ticket had been committed at 16:07:18, three minutes earlier, as `9b4ff1d` *"TOO-45 Item 108 - reading a hook event moves to the contract and takes a source"* (`toolguard/claude_code_contract.py` +68, `toolguard/hook.py`, `test/unit/test_hook.py`). The original said **"IN FLIGHT"**, **"Not committed at `715cdbd`"**, **"What is not settled is where required-field validation lives"**, and **"Blocked on: a decision, plus finishing the work"** — all four are false, and the failure is the campaign's signature one: **ticket-file text read as the state of the world while git said otherwise.** Nothing here is open. It is kept because the *reasoning* is worth having and because a reader who finds only the old text would re-litigate a decision the implementer already settled.

**Sources**: commit `9b4ff1d` (the authority), `TOO-45/proposed-tickets/108-parse-hook-input-belongs-to-the-contract.md`, `TOO-45/reports/surprise/108-prereg.md` (locked 2026-08-23 15:43), `TOO-45/TOO-45 ticket 108 - coder task recall.md`.

**The question.** Arnon, 2026-08-23: *"hook.parse_hook_input() looks like part of the contract. Also, it uses sys.stdin directly, which is less testable. It should be better to have a function in the contract that takes a source that defaults to sys.stdin."* The move was agreed, and made. The open sub-question at the time was where required-field validation lives, because moving the function moves the validation with it — and ticket 104's brief had said the opposite in writing: *"DO NOT add validation to the dataclass. Describing what Claude Code sends is the contract's job; rejecting a malformed event is hook.py's policy call."*

**How it was actually resolved — and note that the justification this section proposed was REJECTED.** The validation stays with the reader, in the contract. But not for the reason given here. The original text proposed *"the contract raises on a missing required field (a shape violation, not a policy call); `hook.py` decides what the raise means"*; the commit body rejects exactly that: *"I argued the required-field check belongs in the contract because 'required fields are shape'. That does not match the code... The real reason it belongs there is that the check runs against the RAW parsed dict"* — `field not in data`, so an explicitly-sent empty string passes and a missing key does not; relocating it to run post-hoc on the returned dataclass would either change behaviour or force the contract to hand back the raw dict, defeating the point. **The correction worth keeping**: the "required" set (`tool_name`, `tool_input`, `hook_event_name`) is **not** the dataclass's non-Optional fields — the commit records that only three of six non-Optional fields were ever enforced, so this is toolguard's own operational choice, not a claim about Claude Code's spec.

**Two facts the commit carries that this section never had**: the proposed signature `source: TextIO = sys.stdin` binds `sys.stdin` at import and **broke 78 tests**, fixed with a `None` sentinel; and the measured testability gain was **68 to 64** stdin-patching tests, which the commit itself calls "smaller than hoped".

**Also shipped**: `EmptyStdinError` became `EmptyHookInputError` — *"a class named for stdin, taking any source, would be exactly the kind of stale name this campaign keeps finding."* Live at `claude_code_contract.py:96`.

**What the episode is worth keeping for**: the prereg's hedge — *"if it argues the other way I want the argument, since I may be rationalising a reversal rather than resolving one"* — was taken up. The implementer did argue the other way and won, and the commit message is the fuller record. **Blocked on: nothing.**

---

## 3. Seventy-eight commits are unpushed and the pre-push checklist is unticked

**Corrected 2026-08-23:** the heading said seventy-seven, the count at `715cdbd`. `git rev-list --count master..too-45` at `9b4ff1d` is **78**.

**Sources**: `TOO-45/TOO-45 phase 3 resume.md` (final section), `TOO-45/TOO-45 punch-list 2026-08-22.md`, `CLAUDE.md` pre-push section.

- [ ] **`/documentation-review`** — **user-invoked; an agent cannot run it.** `docs/` changed a great deal: new `heredoc-parsing-design.md` and `multiline-parsing-flow.md` plus diagrams, and edits to `agent-guides.md`, `configuration.md`, `security.md`, `permission-patterns.md`, `agent-map.md`, `technical-notes.md`, `install.md`. `CLAUDE.md` names this as the main defence against doc drift and singles out `docs/agent-map.md` as the most likely thing to go stale silently.
- [ ] **The push itself** (Arnon does all git writes).
- [ ] **After the push**: `uv tool upgrade toolguard`, **then the smoke test** — `echo '{"session_id":"t","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"'$PWD'"}' | ~/.local/bin/toolguard`. **A hook that cannot launch fails SILENTLY**: Claude Code treats only exit code 2 as blocking, so a broken registration means no permission hook at all, with no error anywhere.
- [x] ~~Fix the broken doc link `715cdbd` introduced~~ — **done in `305caa3`**; re-verified 2026-08-23 evening, all internal links resolve. See §1d.
- [ ] **Two `dot_files` commits from 2026-08-21** were listed as owed for two days. **Corrected 2026-08-23:** the original said `715cdbd` *"appears to have superseded them"* by fixing the shipped `skills/` copies, and listed four dirty files. `git -C ~/projects/dot_files status --porcelain` over the toolguard subtree shows **six** modified files: the named `bash-grammar.md`, `test-config-isolation.md`, `toolguard_hook.toml` and maintenance pass 3, **plus `toolguard-maintenance/passes/2-consolidate-and-group.md` and `toolguard-security-audit/SKILL.md`** — which are precisely the two files the owed commits concerned. So the owed work is **not** superseded: `715cdbd` fixed the shipped counterparts and the install-target edits are still sitting uncommitted in `dot_files`. All six are outside the standing grant and were deliberately excluded rather than guessed at.

**If lost**: the smoke-test step is the dangerous one. It is the only check between a bad registration and a machine running with **no permission hook and no error message**.

---

## 4. Eight questions the retrospective could not settle

**Source**: `TOO-45/reports/retrospective.md` §12, *"What I could not verify, and what is still open"*. Verbatim substance, condensed:

1. **Does the project squash-merge as a policy?** If so the fitness tool's per-ticket co-change grouping buys nothing and costs **7x the sample size**, and removing it is a pure win. **A one-question decision with a measured payoff.**
2. **What does a scoping trace cost?** None of the three records wall-clock or tokens. The return looks enormous but is qualitative; the next one should be timestamped so the practice can be defended with a number rather than a story.
3. **The docstring-ratio metric was proposed and never built.** A few lines on an AST pass that already exists, and the only instrument identified that addresses this repo's actual docstring problem.
4. **The stdlib-only constraint is enforced by nothing.** — **CLOSED since**: commit `1deb328`, `tools/architecture_fitness.py --stdlib`. Recorded so nobody re-opens it.
5. **The corpus does not golden the audit log**, which TOO-19 established as a product surface and where this ticket's headline defect (813/975 under-logged decisions) lived. Identified during R3, still not done.
6. **Whether the *designed* two-judge split outperforms the accidental one is untested** — see §11 below.
7. **`run_guard_canaries` still defaults to the installed binary, and `--guard` still does not print which binary it exercised.** Two small changes — default to the working tree, print the target and its version — retire the defect permanently. **Until then every `--guard PASS 12/12` in the decision log and the resume notes is a statement about the shipped v0.5.1, not about the branch**, and must not be counted as acceptance evidence for any step.
8. **`--layers` has no runtime or historical companion.** Not fixable inside an import-graph instrument; it needs a second lens. The cheapest candidate already worked once on this ticket — instrument the boundary, replay the corpus, count which module's frames touch which — and it exists as one-off scratch code rather than as a mode of the fitness tool.

**Blocked on**: (1) is a one-word answer from Arnon. (3), (5), (7), (8) are small work items nobody has scheduled. (2) is a discipline change for the next similar effort.

**If lost**: **item 7 is the costly one.** It means a class of green readings in the permanent record is known-unreliable, and the note saying so is the only thing preventing them being quoted as evidence.

---

## 5. Tickets whose DISPOSITION was never made

**Corrected 2026-08-23:** the heading over-claims and its own table contradicts it. **106 and 107 are explicitly decided** (106: not doing it; 107: filed LOW and not scheduled on a criterion Arnon stated), and **92 has since been closed** — see its row. Read the heading as *"tickets carried in this table, only some of which are still undecided."* They are kept together because the *analysis* in each row is the part worth preserving.

| # | state | what is unresolved |
|---|---|---|
| **102** here-strings misparsed as heredocs | **measured, reported, awaiting Arnon's YouTrack deferral** | Arnon: *"if no evidence - then tell me and I'll defer as a new YouTrack ticket."* Evidence was checked and reported (featherhill **0**, instagram **0**, toolguard 3 raw of which **2 are false positives** and the third is a latency benchmark feeding JSON). **Whether the YouTrack ticket was ever filed is unverified** — and remained unchecked at verification on 2026-08-23, so it is still the one thing to look up before assuming this was handed off. The analysis that must survive: the fix earns its place on **silent leaf corruption** (`read -r x <<< "$s"` produces the leaf `read -r x <__HEREDOC_TO_read__`, and that corrupted text is what every rule matches against), **not** on the deny bypass, which needs `bash <<< "..."` plus `undecidable_fallback = "allow"` — deliberate evasion, outside the threat model. Also unresolved: **should a here-string feeding a bash-family sink have its content spliced in as source, the way a heredoc does?** Ticket 98 answered that for heredocs and the answers should probably match. |
| **91** substitution body matched as one leaf | **open** | Never investigated beyond the ticket-79 round-3 finding — no reproduction, no measured itemisation-inflation example. It contradicts `CLAUDE.md`'s hardest rule (a substitution body *is* a compound command and is not split before matching). `TOO-45-punch-list-2026-08-20.md:382` closes with *"Still open for Arnon: ticket 70's AE2, and the disposition of 91 and 92 now that their evidence is measured."* (**Corrected 2026-08-23:** the original stopped the quote at "92" and substituted a full stop for the trailing clause, with no ellipsis — the same quote-stops-one-sentence-early mechanic that `.claude/rules/native-fidelity-claims.md` exists because of. The trailing clause matters: the disposition was owed *after* evidence, not instead of it.) |
| **92** heredoc piped to a shell loses its ASK floor | **CLOSED 2026-08-23 — re-measured, fixed** (corrected; was *"probably closed by ticket 98, never confirmed"*) | **Corrected 2026-08-23:** this row said no one had re-measured 92 against the shipped tree. Someone did — **101 seconds after this document was written**, prompted by this very flag. `proposed-tickets/92-heredoc-piped-to-a-shell-loses-its-ask-floor.md` (mtime 16:11:50) now carries `# CLOSED 2026-08-23 — RE-MEASURED, fixed`, opening *"Flagged during the memory-extraction pass as..."*: the piped form now floors identically to the unpiped control (`('python __HEREDOC_TO_python__', True)` for both), fixed by ticket 98 chunk 2. What survives is the reasoning, not the question: `TOO-45 phase 3 resume.md` had recorded *"92 — both spikes fix this"*, and the evidence note was careful — zero occurrences, but *"treat it as 'no evidence found', not as 'does not occur'"*, and `cmd <<HD \| bash` arises by ordinary intent with a silent failure, which under `.claude/rules/evidence-before-fixing.md` is still a fix. |
| **70** AE2 | **open** | *"a missed removal still applies its addition: half a narrowing is a broadening."* Ticket 70 itself is committed (`92e6edd`); AE2 was carved out and left. |
| **107** proc_subst identified by characters | **filed, LOW, explicitly not scheduled** | **Reframed 2026-08-23 by Arnon**, and the reframing is the durable part: the criterion is **the package boundary, not correctness**. Arnon's actual words: *"while the check to see whether the first character is '#' is strictly 'wrong'. As far as parsing goes, it's just about the simplest parsing one can think of."* The check is acceptable **so long as it stays inside `toolguard/parser/`**; what would matter is a consumer *outside* the package sniffing characters to learn what the grammar already knew. (**Corrected 2026-08-23:** the original put the coordinator's own commentary — *"A single-character test is the simplest parsing there is"* — inside quotation marks directly after "Reframed by Arnon", presenting a paraphrase as his words. The substance is his; the sentence was not. Verification calls this the single most damaging item in the document, because it is the only one a later reader cannot detect once the sources are gone.) By that criterion the current state is fine, and the risk the coordinator actually cared about was already retired by 105 phase 2, which identifies comments by a grammar label. Related to **TOO-69** (explicit module and package usage boundaries). Arnon: *"We have plenty of future work before we do get into subtle things like this."* |
| **106** audit visibility is a property, not a partition | **DECIDED — not doing it** (Arnon, 2026-08-23) | Included because the *finding* is worth keeping if `compound.py` is ever reopened: `audit_parts` and `deny_check_parts` are checked identically and differ **only in audit visibility**, and the split propagates into `judge_unit` as three parallel length-matched verdict sequences. Also because the decision validates the concept-map bargain — ticket 106's wording is *"if the map turned out easy to write, ship it and stop; if hard, the difficulty is the refactor spec"* (**corrected 2026-08-23**: the original quoted a lightly paraphrased form inside quotation marks) — and **a ticket declined on a clear understanding is a success of the diagnostic.** |

---

## 6. Four `--undeclared-types` findings, reported and unfixed by instruction

**Sources**: `TOO-45/TOO-45 punch-list 2026-08-22.md`, `TOO-45/TOO-45 phase 3 resume.md`. **Re-measured live 2026-08-23, and re-measured again at verification at `9b4ff1d` with byte-identical output** (the original said `715cdbd`, one commit behind) — all four still present:

```
examined 353 public function(s)/method(s); 12 exempt by serialiser-name convention, 0 exempt via explicit allowlist,
3 return an undeclared dict but are never called outside their own module
  - config:164   load_config_file (annotated)
  - config:2222  config_sync_settings_from_sources (annotated)
  - rule_sort:488 parse_permissions_section_with_comments (annotated)
  - subagent:141 identify_current_agent (annotated)
```

The check is **report-only and does not fail the build**, which is exactly how it comes to be forgotten. *"None fixed; that is Arnon's call, not a subagent's."*

**What would settle it**: four decisions — declare a type, add an allowlist exemption, or leave it reported. **Note `subagent.identify_current_agent`**: auto-memory records subagent identification as broken and logging-only, so that one may be moot.

**If lost**: a green pre-push run hides four standing findings behind a "report-only" label, and the reason they were left is unrecorded.

---

## 7. Tickets deferred WITH A REASON, and the trigger that would revive each

These were not dropped. Each has measured evidence and, in several cases, a precise revival condition. **Sources**: `TOO-45/TOO-45-retriage-2026-08-20.md`, `TOO-45/TOO-45-punch-list-2026-08-20.md`, `TOO-45/proposed-tickets/00-INDEX.md`.

- **17** `[native]` end-anchor under-match — **CLOSED** by Arnon on zero exposure across **42,113 native-intent rules**, and *the immunity is structural*: prefix rules end in `*`, and Claude Code's own dialog writes prefix rules by construction. **Revisit trigger, stated precisely: the first deny rule that does not end in `*`.** That trigger is the durable artifact.
- **21** danger-analyzer coverage gaps — skipped after its featherhill "blanket allow" evidence turned out to be **toolguard's own development traffic on 2 days of 49**.
- **34** nested backtick substitution never descended into — 98 occurrences, **all dogfood**. **The fix direction was never chosen**: descend into the nesting (grammar work, two-phase rule) or treat the nesting as undecidable and let the ask floor take it (cheaper, arguably safer). One deliberate RED test sits in the tree for it.
- **36** a disclosure comment can make toolguard reject the command it describes — **CLOSED 2026-08-23, re-measured and fixed.** **Corrected 2026-08-23:** this entry said 36 had **never been re-measured against ticket 105** and that `CLAUDE.md`'s assertion *"A leading comment does not affect rule matching"* was **false**. Both statements were overtaken 101 seconds after this document was written, by a re-measurement this flag prompted: `proposed-tickets/36-disclosure-comments-are-not-inert-to-the-extractor.md` (mtime 16:11:50) now carries `# CLOSED 2026-08-23 — RE-MEASURED, fixed` — all four disclosure-comment forms decide `allow` against an `allow = ["Bash(ls -la)"]` / `no_match_fallback = "ask"` config, fixed structurally by item 105's grammar comment node. **The `CLAUDE.md` claim is now true.** What remains worth keeping is the exposure measurement (652 of 657 occurrences are this repo's own mandated disclosure markers, so the evidence was process, not users) and the reason it was kept alive despite that: the failure was fail-closed with a message about the *command*, so **the failure mode trained agents out of disclosing.**
- **83**, **84**, **87** — zero occurrences across all corpora; skipped at Arnon's direction.
- **40** — **dead**, dies with JSON config retirement under **TOO-67**.
- **93** — Arnon filed **TOO-68**. **90** — Arnon: skip.
- **Advisory tooling tier: 37, 53, 56, 61, 62, 66, 72, 75** — skipped **without tickets**, on the reasoning that *"a defect in an advisory analyzer cannot silently permit anything"* — the operator runs it deliberately and reads the output. **`75` is the closest call and is named as the one to revisit first**, because it feeds rule proposals: `mining._command_key` hand-rolls bash tokenization against this project's hardest architectural rule, and **every disclosed command the disclosure rule mandates keys on `#`**, landing in one meaningless bucket.

**If lost**: the *reasons* go, and the tickets read as untouched work. The retriage's structural finding goes with them — **only about a third of the open queue has a log signature at all**, because a ticket fires in the logs only when its trigger is a command or rule shape; everything else is internal correctness where no corpus can speak and severity judgement is the only axis.

---

## 8. Design tickets deferred for a decision that was never taken

**Sources**: `TOO-45/proposed-tickets/00-INDEX.md`, **two** sections of it — "Open — genuinely awaiting a decision" (`:43-55`) for **02, 06, 08, 11, 12, 13, 16**, and "Open — found by the #07 sweep, none filed to YouTrack" (`:57-79`) for **31, 32 and 33**. Cross-checked against `git log --grep=TOO-45`: none of the listed tickets appears in the 78 commits on `master..too-45`, and 32's item 1 is `bd44605` exactly as stated.

**Corrected 2026-08-23 (two things).** (1) The original attributed all ten entries to the first section; three come from the second. (2) The first section also contains **07** and **09**, which this list silently drops. The drop is *correct* — 07 has commits `7460ffb` and `549abc3`, and 09's deliverable is `docs/architecture-as-built.md` via `d245d0c` — but it was invisible, so a reader could not audit the "none of these appears in git log" claim against the cited section. They are named here so the list can be reconciled with its source.

- **02 pattern-string join key** — *"deferred, needs a design decision."*
- **06 measurement tools: keep or remove** — *"deferred at Arnon's request, for discussion before push."* The tools (`tools/change_role_classifier.py`, `tools/touch_set_inventory.py`, `tools/touch_set_score.py` plus four test files) became **tracked by accident**, swept in by a `git add -A`. **Case for removing**: experiment instrumentation, not product; the classifier and the touch-set scorer were both *proven biased*; ~90 tests to maintain forever for tools nothing calls. **Case for keeping**: the classifier's occurrence finding was independently proven exact twice and the inventory's blindness guarantee was audit-verified — both could serve a future change canary, though they would need re-attacking first (the last adversarial pass left residual silent loss in **13 of 24** implementation styles). **This decision is still owed and the pre-push list names it.**
- **08 literal strings to constants** — deferred; global guidance now carries the rule, this is the sweep of existing code.
- **11 ASK-floor scope for non-Bash tools** — **PARTIALLY FIXED**: the measurement was done and is benign; **one doc sentence is still wrong — confirmed still wrong at HEAD, `docs/configuration.md:517`, which says "the Bash-only inline/heredoc-foreign-code floor".** (**Added 2026-08-23:** the ticket file has been moved to `TOO-45/resolved/`, which the original did not mention — so a reader looking for it in `proposed-tickets/` will not find it.) Note the correction that matters — "the ask floor" names **two different mechanisms** (the TOO-19 parse-failure floor and the inline/heredoc foreign-code floor), and the campaign briefed one as the other.
- **12 guard the audit write loop** — deferred; closes the residual half of that ticket's headline defect.
- **13 anchor project root per session** — **Arnon: needed before RC1**, not necessarily in TOO-45. Not trivial.
- **16 ToolSpec cannot describe a user-declared tool** — found by Arnon at the manual review of #10; **#10 made this look solved without solving it.** Documented; code residual promoted to **TOO-51**.
- **31 suite blindness** — a decision about triage and a **stopping rule**, explicitly *not* a work order to fix 65 tests. Related and unresolved: the `~65` figure conflates *cannot fail* (vacuous) with *cannot distinguish* (load-bearing but blind), which are different defects needing different fixes. **The open question is whether re-deriving the total is worth the time, or whether the 22-shape catalogue is the durable artifact and the total never mattered.**
- **33 code-level residue from the 07 sweep** — the headline contradiction was code and comments actively contradicting each other in `config.py`, plus a user-facing string telling the user the opposite of what happened. **Scoped 2026-08-23:** "still live" is **as recorded on 2026-08-20** (`00-INDEX.md:79`, `DECISIONS-PENDING.md` A6) and was **not re-measured against the tree**; the #07 sweep commits touched that file, so re-read `config.py` before acting on this entry.
- **32 item 2** — **DEMOTED** from "fix before push"; its justification was measured false. (Item 1 shipped as `bd44605`.)

---

## 9. Standing hazards recorded in the notes and nowhere else

These are not tickets. They are facts that will cost someone time if they are lost.

**Commands that PROMPT will block an agent indefinitely** (measured 2026-08-22, `TOO-45 phase 3 resume.md`). `npx canopy@latest` fetches from the network and prompted — **two grammar agents sat blocked on it for 90+ minutes each**, and both were misread as stalled. **A blocked agent is indistinguishable from a stalled one and cannot tell you which it is** — so ask, before putting any command in a brief, whether it prompts. *That* is the durable lesson; the two specific commands below are no longer the example.

**Corrected 2026-08-23 — this hazard is CLOSED for both commands, and the original's conclusion was already false when written.** The original said *"**The exact command that blocked both agents would block again**"* and offered *"two open options, both Arnon's call: widen to `Bash(npx canopy@* *)`, or symlink `canopy` onto `PATH`."* Neither option is open: a **third** route had already been taken. `.claude/toolguard_hook.toml` line **61** is `"Bash(npx canopy@latest *)"`, inside the same `allow = [ ... ]` list whose lines 59 and 60 the original quoted — it read two lines of the list and not the third. The file's mtime is 2026-08-22 18:06:47, about 22 hours before extraction, so this was not a race: a source note was carried forward without re-measuring the live config, **in the same section that says "Date every tool measurement; re-take rather than carry forward."** Likewise **`git worktree` ALWAYS prompts** is verbatim Arnon and true as attribution, but the operational conclusion drawn from it — *never dispatch an agent with `isolation: "worktree"`* — is stale **for this project**, because line 62 is `"Bash(git worktree *)"`. Both allow lines are **uncommitted working-tree additions in `~/projects/dot_files`**, so they are real today and would be lost if that tree were reverted.

**The canopy invocation itself (unchanged and still worth having).** Use bare `npx canopy` where you can; run it **from `toolguard/parser/`** (from the repo root the generated header changes and the diff explodes); canopy is not on `PATH` and lives in the npx cache. The rules are `Bash(canopy *)` at `.claude/toolguard_hook.toml:59`, `Bash(npx canopy *)` at `:60` and `Bash(npx canopy@latest *)` at `:61`. The matching subtlety that produced the original hazard is still true in general and worth remembering: the wildcard follows a space, so `canopy@latest` is a **different word** from `canopy` and a rule for one does not cover the other.

**`pyscn` scores a FILTERED SUBSET and its aggregate must never be quoted.** AST census: 79 files, 951 functions. pyscn reports 49 files and **213 functions — 22%** — filtering per file (`config.py`: 19 of 58), with `bash_parser.py` (182 functions) absent entirely. So *"avg complexity 7.8"* is an average over non-trivial functions only and **"Health 72/100" is not a package-level measure.** Use its per-function findings; never its aggregate. **This also corrects an older note** claiming most offenders were canopy-generated — no longer true. **Date every tool measurement; re-take rather than carry forward.** Arnon's standing position, 2026-08-23: a function over a threshold is a place to go **look**, not a verdict — `judge_unit` at 20 was worth splitting, `node_kind` at 15 is a flat ordered dispatch whose ordering is documented and load-bearing, and splitting it would destroy what makes it readable. **Same number, opposite conclusions.**

**pyscn duplication (15.9%) is not triaged per clone — but a recommendation WAS made.** *"Severity from a clone detector is not severity in this codebase's sense."* An earlier campaign found the conclusion changed **three times** once the actual fragments were read. `reports/pyscn-2026-08-22-disposition.md:74`: **"Recommendation: treat duplication as its own scoped task, read the fragments, and expect the honest number to be well below 15.9%."** (**Corrected 2026-08-23:** the original headline said *"no recommendation was made"* and then reproduced the recommendation two sentences later. The source's own *"Not triaged, and I am not recommending anything on it"* refers to **per-clone** triage; compressing the two made the paragraph contradict itself. What is open is the scoped task, not the recommendation.)

**`tools/check_doc_links.py` has a blind spot in this project's own vocabulary — and it does not currently pass at all.** `LINK_RE` uses `[^\]]+` for link text, so any link written as `` [`[native]`](...) `` or `` [`[hard_deny]`](...) `` is **silently skipped**; confirmed still present at `tools/check_doc_links.py:42`. The figure *"4 of 425 links skipped, one of them genuinely broken"* is **unverified — no source was cited for it and verification could not find the measurement record, including the 425 denominator.** Treat it as an unsourced recollection, not a measurement; re-derive it if it matters. The blind spot itself is confirmed by reading the regex. **The "it FAILS at HEAD" claim added earlier on 2026-08-23 was true at `715cdbd` and is false at `305caa3`**, which fixed that link; re-run confirms all internal links resolve (see §1d). So *"check_doc_links passes"* is a **weaker invariant than reported** — that remains the finding here — but it is currently a true statement.

**`tmp/scratch_annotations.py` — a loose thread Arnon left open and never assigned.** It explores **runtime access-control annotations**: `PUBLIC` / `PRIVATE` / `PACKAGE_PRIVATE` constants, a `package_private()` class decorator writing into `cls.__annotations__`, and `annotationlib.get_annotations` reading them back at runtime. Plausibly relevant — **as inference, not as anything he said** — to the API-visibility criterion (*"privatize by whether non-test code should call it"*) and to ticket 100, where a leading underscore is the only declaration of internal-use intent that `--orphans` checks against; an explicit annotation would be a **stronger declaration**. One observation offered rather than acted on: the decorator is named `package_private()` but assigns `PUBLIC`, and the print's trailing comment says `# => "access:public"`, so it may be deliberate scratch behaviour. **It is in `tmp/` (gitignored), was never a task, and the standing instruction is: ask before doing anything with it.**

---

## 10. Two provisional conclusions that could reverse

**The exec-wrapper bar was resolved by CONFIG, not code** — user-level `find` allow plus `hard_deny` applied, featherhill's copy removed, no ticket filed. That is a configuration state, not a code property, and nothing enforces it.

**`no_match_fallback = "allow_with_no_warnings"` in `.claude/toolguard_hook.toml:4` is marked TEMPORARY pending TOO-28**, and it silently weakens every corpus replay run in this repo: **9,848 of 51,918 toolguard decisions (19%) were fallbacks**, versus **0 of 3,675 in featherhill**. The better method Arnon specified — **re-score the corpus as if `no_match_fallback` were `ask`, regardless of what this repo sets** — makes the instrument sensitive instead of requiring a second field to be eyeballed, and models the shipped default. This is already in `.claude/rules/evidence-before-fixing.md`; it is recorded here because the TEMPORARY marker is the kind that expires silently.

---

## 11. Lesson 6, explicitly marked "(open)": does the two-judge split survive contact?

**Source**: `TOO-45/TOO-45 lessons.md` §6, corroborated by `reports/retrospective.md` §12 item 6.

**Prediction, recorded before evidence**: separating the **blinded reviewer** (no goal, judges reviewability) from the **architect judge** (full context, judges direction) will produce disagreements that a single judge would have resolved silently, and **those disagreements will be the most informative output of the loop**.

**Falsifiable**: if the two always agree, the split is ceremony and one judge plus a checklist would do. Revisit at CP2.

**Why it is still open**: the retrospective adds the reason the evidence cannot settle it — *"the split's evidence comes mostly from before it was deliberate."* Whether the **designed** split outperforms the **accidental** one is untested.

**Blocked on**: work — running enough reviews under the deliberate split to see whether disagreements appear.

**If lost**: a falsifiable prediction with a stated revisit point becomes an unexamined habit. That is precisely the shape this campaign spent twenty days finding in the code.

---

## Cross-cutting: the three findings that make "no evidence" hard to read here

Recorded because they govern how every deferral above should be re-read, and because two of them were discovered *by correcting the third*.

1. **A clean corpus is not evidence of no regression — three measured instances.** Ticket 18's replay reported zero flips because a permissive fallback made the transition unobservable; 98 chunk 2 fixed three real defects with **zero** corpus decision changes because none of the 6,401 cases contained the shapes; ticket 101's brace-group deny bypass would have passed `--verify` cleanly because **the corpus contains no brace groups**. The corpus is harvested from real logs, so it measures what the agent *has* emitted — excellent for regression detection, **structurally blind to anything rare.** The permanent answer is in the tree: `test/unit/test_deny_penetrates_constructs.py`, a denied command in all 17 constructs with one subTest each plus a benign control so it cannot pass by denying everything.
2. **The dogfood corpus records the investigation, so it inflates its own evidence** — and **featherhill is NOT immune**, which was the dangerous half of an earlier claim. Any directory the agent stands in while investigating toolguard receives probe traffic; of 9 apparently-genuine `find -exec`/`-delete` commands in featherhill, **8 are probes.** **A corpus is evidence about a DATE RANGE, not about a project.**
3. **Four instrument errors in one day, every one caught by CONTRADICTION rather than by care** — a golden comparison keyed on fields that do not exist (producing a false *"zero verdict changes"*); a brace check run against 90-char truncated prefixes; a coverage run piped through `tail -40` that silently dropped every core module; a glob matching a test file's `.cover` instead of the module's. **The practice that caught all four was having a second number that disagreed with the first.** That is cheaper and more reliable than resolving to be more careful, and it should be a standing practice rather than a lesson.