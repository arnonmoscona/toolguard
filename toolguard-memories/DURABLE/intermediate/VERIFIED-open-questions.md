---
title: VERIFIED-open-questions
type: note
tags:
- TOO-45
- durable
- verification
permalink: toolguard/durable/intermediate/verified-open-questions
---

# Verification of `intermediate/open-questions.md`

**Target**: `toolguard-memories/DURABLE/intermediate/open-questions.md` (245 lines, 37,029 bytes, mtime **2026-08-23 16:10:09**).
**Verifier**: a different agent from the author. Stance per `DURABLE/VERIFICATION-PROTOCOL.md` — try to refute.
**Verified at**: branch `too-45` HEAD `9b4ff1d`, 2026-08-23.

**Claims checked: 133.** CONFIRMED 112 · REFUTED 9 · MISATTRIBUTED 2 · TRUE BUT MISLEADING 7 · UNVERIFIABLE 3. Plus one **omission that makes the surrounding text misleading** (F9), which is not a numbered claim.

---

## LEAD: the failures

### F1 — REFUTED. §2 says ticket 108 is "IN FLIGHT" and "**Not committed at `715cdbd`**". It was committed **three minutes before this file was written**, and the seam question it calls unresolved was resolved *in the commit message*.

This is the exact failure `VERIFIED-defect-taxonomy.md` found in its own target: **outcome derived from ticket-file text while git history said otherwise.**

| | |
|---|---|
| commit `9b4ff1d` "TOO-45 Item 108 - reading a hook event moves to the contract and takes a source" | **2026-08-23 16:07:18** |
| `open-questions.md` written | **2026-08-23 16:10:09** |

The document's framing device — "State of the branch at extraction time: `too-45` at `715cdbd`" — is false. At extraction time the branch was at `9b4ff1d`. `715cdbd` was already the *parent*.

What the doc says is open, and what the tree says:

| doc, §2 | HEAD `9b4ff1d` |
|---|---|
| "**Not committed at `715cdbd`.**" | committed as `9b4ff1d`; `toolguard/claude_code_contract.py` +68, `toolguard/hook.py` -70/+... , `test/unit/test_hook.py` |
| "**What is not settled is where required-field validation lives**" | settled: it stays with the reader, in the contract |
| "**Proposed resolution, flagged rather than silently decided**: the contract raises on a missing required field (a shape violation, not a policy call)" | **that justification was rejected.** Commit body: *"I argued the required-field check belongs in the contract because 'required fields are shape'. That does not match the code... The real reason it belongs there is that the check runs against the RAW parsed dict"* |
| "**Also decided in flight**: `EmptyStdinError` becomes `EmptyHookInputError`" | shipped — `claude_code_contract.py:96` |
| "**Blocked on**: a decision, plus finishing the work." | neither |
| "**If lost**: the ticket is half-built with a documented reversal of a documented instruction and no record of why." | the record is the commit message, which is more complete than §2 |

The commit also records two facts §2 does not have: the proposed signature `source: TextIO = sys.stdin` binds `sys.stdin` at import and **broke 78 tests**, fixed with a `None` sentinel; and the measured testability gain is **68 → 64** stdin-patching tests, "smaller than hoped".

**Consequence if this summary is kept as-is**: a reader re-opens a closed, correctly-decided ticket and re-litigates a justification that its own implementer already refuted.

---

### F2 — REFUTED. "77 commits" is wrong at extraction time; the correct number is 78.

`git rev-list --count master..too-45` = **78** at `9b4ff1d`. 77 is the count at `715cdbd`, one commit behind. The error propagates into the §3 heading, "**Seventy-seven commits are unpushed**". "Nothing pushed" is CONFIRMED — `origin` has no `too-45` ref.

---

### F3 — REFUTED. The header's "**nothing is blocked on work**" is contradicted three times inside the same document.

The cited source (`TOO-45 phase 3 resume.md`, FINAL STATE) says only: *"The punch list is exhausted; everything remaining needs a decision from him."* The clause **"and nothing is blocked on work"** is the summarising agent's addition, and the document then says:

- §2: "**Blocked on**: a decision, plus finishing the work."
- §4: "(3), (5), (7), (8) are small work items nobody has scheduled."
- §11: "**Blocked on**: work — running enough reviews under the deliberate split."

An unhedged summary sentence that the body refutes three times is worse than no sentence, because the header is what gets quoted.

---

### F4 — REFUTED. §9: "**The exact command that blocked both agents would block again.**" It would not. `.claude/toolguard_hook.toml:61` already allows it — and did when the doc was written.

```
59:  "Bash(canopy *)",
60:  "Bash(npx canopy *)",
61:  "Bash(npx canopy@latest *)",     <-- inside allow = [ ... ]
62:  "Bash(git worktree *)",
```

The document cites **line 59 and line 60 of that same list** and did not read line 61. The file's mtime is **2026-08-22 18:06:47** — roughly 22 hours before extraction — so this was not a race; the source note (`TOO-45 phase 3 resume.md:675`) was carried forward without re-measuring the live config, in a document whose own §9 says *"Date every tool measurement; re-take rather than carry forward."*

Two downstream errors follow:

- "**Two open options, both Arnon's call**: widen to `Bash(npx canopy@* *)`, or symlink `canopy` onto `PATH`" — a **third** route was already taken (`npx canopy@latest *` added verbatim), so neither option is open.
- The same paragraph's "**`git worktree` ALWAYS prompts** (Arnon), so never dispatch an agent with `isolation: "worktree"`" sits two lines above `Bash(git worktree *)` at line 62. The Arnon attribution is verbatim from the source; the operational conclusion is stale for this project's config.

Both lines are uncommitted working-tree additions in `~/projects/dot_files` — confirmed by `git -C ~/projects/dot_files diff`.

---

### F5 — MISATTRIBUTED. §5, ticket 107: *"A single-character test is the simplest parsing there is"* is presented as Arnon's reframing. It is the ticket author's own sentence.

The doc writes: *"**Reframed 2026-08-23 by Arnon** ... the criterion is **the package boundary, not correctness**. *"A single-character test is the simplest parsing there is"* and is acceptable **so long as it stays inside `toolguard/parser/`**"*.

Arnon's actual words, from the ticket's blockquote:

> *"while the check to see whether the first character is '#' is strictly 'wrong'. As far as parsing goes, it's just about the simplest parsing one can think of."*

The quoted sentence is from the coordinator's commentary *below* Arnon's block: *"A single-character test is the simplest parsing there is; it passes no hard-to-reason-about parsing responsibility up."*

**The substance survives** — Arnon did say the equivalent, and the boundary criterion is his. **The attribution does not.** Protocol item 5: "A paraphrase presented as a decision is a fabricated mandate." Here it is a paraphrase presented as a *quotation* of a decision, which is the same defect one notch quieter. The document's other 107 quote — *"We have plenty of future work before we do get into subtle things like this."* — **is** verbatim Arnon and is CONFIRMED.

---

### F6 — REFUTED (stale by 101 seconds). §5/92 and §7/36 are both closed with appended evidence, and the closures quote this document's own wording.

| file | mtime |
|---|---|
| `open-questions.md` | 2026-08-23 **16:10:09** |
| `proposed-tickets/92-heredoc-piped-to-a-shell-loses-its-ask-floor.md` | 2026-08-23 **16:11:50** |
| `proposed-tickets/36-disclosure-comments-are-not-inert-to-the-extractor.md` | 2026-08-23 **16:11:50** |

Both now carry `# CLOSED 2026-08-23 — RE-MEASURED, fixed`, each opening *"Flagged during the memory-extraction pass as..."* and quoting the flag this document raised. **92**: the piped form now floors identically to the unpiped control (`('python __HEREDOC_TO_python__', True)` both), fixed by 98 chunk 2. **36**: all four disclosure-comment forms decide `allow` against an `allow = ["Bash(ls -la)"]` / `no_match_fallback = "ask"` config; the fix is structural via item 105's grammar comment node.

**Verdict is REFUTED-as-of-now, CORRECT-at-write-time.** The document caused its own obsolescence, which is the best outcome a flag can have — but the surviving artifact now points a future reader at two closed threads and describes 36's "`CLAUDE.md` asserts *'A leading comment does not affect rule matching'* and that claim is **false**" as live. It is no longer false.

---

### F7 — TRUE BUT MISLEADING. §9: "**pyscn duplication (15.9%) is NOT triaged and no recommendation was made.**" A recommendation was made, and the document reproduces it two sentences later.

`reports/pyscn-2026-08-22-disposition.md:74`: *"**Recommendation: treat duplication as its own scoped task**, read the fragments, and expect the honest number to be well below 15.9%."* The doc quotes that sentence verbatim in the same paragraph in which it says no recommendation was made. The source's own "**Not triaged, and I am not recommending anything on it**" refers to per-clone triage; compressing the two into "no recommendation was made" makes the paragraph self-contradictory.

---

### F8 — MISATTRIBUTED (source section). §8 attributes all ten entries to `00-INDEX.md`'s "Open — genuinely awaiting a decision". Three of them are not in it.

That section (`00-INDEX.md:43-55`) contains **02, 06, 07, 08, 09, 11, 12, 13, 16**. Entries **31, 32 and 33** come from a different section, "Open — found by the #07 sweep, none filed to YouTrack" (`:57-79`). And the cited section's **07** and **09** are silently dropped — correctly (07 has commits `7460ffb` and `549abc3`; 09's deliverable is `docs/architecture-as-built.md` via `d245d0c`), but the drop is invisible, so the reader cannot audit the accompanying claim "cross-checked against `git log --grep=TOO-45` (none of these appears)".

That claim is otherwise **CONFIRMED**: none of 02, 06, 08, 11, 12, 13, 16, 31, 33 has a commit on `master..too-45`; 32's item 1 is `bd44605` exactly as stated.

---

### F9 — Omission that makes the surrounding text misleading. `check_doc_links` **fails at HEAD**, with a broken link introduced by commit `715cdbd` — the very commit §1d praises.

```
$ uv run python tools/check_doc_links.py
missing file    skills/toolguard-security-audit/SKILL.md: ../../../docs/agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception
1 broken link(s).
```

The anchor exists (`docs/agent-guides.md:207`); the relative path carries one `../` too many. It was added by `715cdbd` (line 120 of its diff to that file). §1d says that commit "fixed the two files"; §9 discusses `check_doc_links`'s blind spot and concludes *"'check_doc_links passes' is a weaker invariant than it has been reported as"* — without noting that it does not currently pass at all. Two sections that each touch the fact, neither of which states it.

---

### F10 — TRUE BUT MISLEADING. §1's "~60 `NN-prereg.md` / `NN-scored.md` **pairs**".

`ls reports/surprise/ | grep -cE 'prereg|scored'` = **62 files**, i.e. roughly **31 pairs**. The count is right for files and 2x wrong for pairs. (Directory total: 110 files. `RESULTS-LOG.md` at **57,375 bytes** — the "57 KB" is exact.)

---

### F11 — Citation path error. §1 lists `surprise-factor-protocol.md` among the files in `reports/surprise/`. It is at `reports/surprise-factor-protocol.md`, one level up.

Every other source path in the document resolves.

---

### F12 — Truncated quotation. §5, ticket 91.

Doc: *"Still open for Arnon: ticket 70's AE2, and the disposition of 91 and 92."*
Source (`TOO-45-punch-list-2026-08-20.md:382`): *"**Still open for Arnon**: ticket 70's **AE2**, and the disposition of **91** and **92** now that their evidence is measured."*

A full stop substituted for a trailing clause, no ellipsis. Harmless to the meaning here, but it is the "quote that stops one sentence early" mechanic that `.claude/rules/native-fidelity-claims.md` exists because of.

---

### F13 — §3's dot_files inventory is incomplete, and "superseded" is doing more work than the hedge admits.

Doc: "Commit `715cdbd` **appears to** have superseded them ... `bash-grammar.md`, `test-config-isolation.md`, `toolguard_hook.toml` and maintenance pass 3 are **still dirty**".

`git -C ~/projects/dot_files status --porcelain` on the toolguard subtree shows **six** modified files, not four: the named four plus **`toolguard-maintenance/passes/2-consolidate-and-group.md`** and **`toolguard-security-audit/SKILL.md`** — which are precisely the two files the "two owed commits" concerned. So the owed work is still sitting uncommitted in `dot_files`; `715cdbd` fixed the *shipped* counterparts, it did not supersede the install-target edits. The hedge ("appears to") keeps this out of REFUTED, but the dirty-file list understates by two.

---

## Judgements dressed as measurements — the protocol's specific carve-out

Per the protocol a judgement is not a finding **provided it is labelled**. The document's recurring `**If lost**:` blocks are conditional and read as judgement; that is acceptable. Three superlatives are not labelled:

| text | status |
|---|---|
| §1 "**the single most useful thing it produced** is the scope asymmetry" | **sourced, not a bare judgement** — `CONSOLIDATED-REPORT.md` calls it "the most useful thing the whole experiment produced" |
| §1 "That is **the most misleading possible resting place**" | unlabelled judgement. Reasonable, but nothing measures it |
| §1b "the **sharpest recorded instance** of confidence outrunning evidence **in the whole campaign**" | unlabelled judgement, and a universal over a corpus nobody ranked. `105-scored.md` says only *"the cleanest instance in it"*, scoped to the estimator series |
| §4 "**item 7 is the costly one**" | judgement, adequately framed by "If lost" |
| §6 "that one may be moot" | correctly hedged; auto-memory does record subagent ID as broken/logging-only |

None of these are numeric claims, so none is REFUTED. Flagged because §1b's superlative widens its source's scope from "the estimator series" to "the whole campaign".

---

## Claim-by-claim

### Header block

| # | claim | verdict | evidence |
|---|---|---|---|
| 1 | branch at `715cdbd` at extraction time | **REFUTED** | HEAD was `9b4ff1d` (16:07:18) before the file was written (16:10:09) |
| 2 | 77 commits | **REFUTED** | 78 on `master..too-45` |
| 3 | nothing pushed | CONFIRMED | no `origin/too-45` ref |
| 4 | Suite 4008 OK (4 expected failures) | CONFIRMED | re-run: `Ran 4008 tests ... OK (expected failures=4)` |
| 5 | `corpus_build.py --verify` clean | CONFIRMED | re-run: 6401 in-process + 61 e2e, "OK: no differences" |
| 6 | ruff clean | CONFIRMED | `All checks passed!` |
| 7 | `--stdlib --ambient --layers --orphans --undeclared-types` all pass | CONFIRMED | re-run; layers 78 modules, ambient 79 files, stdlib PASS, orphans OK |
| 8 | version 0.6.0 unreleased | CONFIRMED | `pyproject.toml:3`; no tag |
| 9 | "everything remaining needs a decision from Arnon, **and nothing is blocked on work**" | **REFUTED** | F3 |
| 10 | punch list exhausted | CONFIRMED | `TOO-45 phase 3 resume.md` FINAL STATE |

### §1 — surprise-factor experiment

| # | claim | verdict | evidence |
|---|---|---|---|
| 11 | source files exist | CONFIRMED except path | F11 — `surprise-factor-protocol.md` is in `reports/`, not `reports/surprise/` |
| 12 | `RESULTS-LOG.md` 57 KB | CONFIRMED | 57,375 bytes |
| 13 | "~60 prereg/scored pairs" | **TRUE BUT MISLEADING** | F10 — 62 files ≈ 31 pairs |
| 14 | Arnon 2026-08-21 *"The estimator is not the objective here..."* | CONFIRMED **verbatim** | `CONSOLIDATED-REPORT.md:145` |
| 15 | fifteen items scored phase 1-2, recall 15.2%–100% | CONFIRMED | `CONSOLIDATED-REPORT.md` "Results — 15 items scored"; 15 `*-scored.md` files pre-batch-2; range matches |
| 16 | second batch of thirteen | CONFIRMED | `CONSOLIDATED-BATCH-2.md` table = 13 rows |
| 17 | item 03: 64.4% raw / 12.0% unleaked | CONFIRMED | `CONSOLIDATED-REPORT.md` |
| 18 | item 77 design-leaked → 9/9; item 80 same day without → 5/9 | CONFIRMED **verbatim** | ibid. |
| 19 | 608 of item 10's 620 unpredicted lines belong to three other bodies of work | CONFIRMED | `RESULTS-LOG.md:273` |
| 20 | 3 of 32 missed production files carry 811 of 958 missed lines (85%) | CONFIRMED | `CONSOLIDATED-REPORT.md` addendum |
| 21 | every large under-scope is a new module or control-flow relocation, never a call-site sweep | CONFIRMED | ibid., stated verbatim |
| 22 | Arnon's two decisions 2026-08-21 (continue to 20 human-authored; production-files-only headline) | CONFIRMED | `CONSOLIDATED-REPORT.md:168-169` |
| 23 | **eligibility is destroyed by whoever MEASURES first, not whoever NOTICES** | **CONFIRMED — not the summariser's invention** | `RESULTS-LOG.md:387` and **:420**, near-verbatim twice |
| 24 | tickets 98 and 99 were Arnon's findings, spent before an estimate existed | CONFIRMED | `RESULTS-LOG.md:387` eligibility table (98: *"Human-originated but coordinator-measured"*; 99: *"Not yet measured... an estimate from me is already informed"*) and `CONSOLIDATED-BATCH-2.md` |
| 25 | "to reach 20, the estimate must be locked at filing time, before any investigation" | CONFIRMED **verbatim** | `RESULTS-LOG.md:387,420` |
| 26 | **ZERO of 20**; batch 2 added none | CONFIRMED (derived) | batch-2 states "this batch added none" verbatim. The "0 of 20" total is the summariser's arithmetic, sound: every post-08-21 item (95, 97, 98, 99, 88, 89, 100, 101, 103, 104, 105, 108) is coordinator-filed or explicitly labelled an informed estimate — `108-prereg.md` says so in its own second line. **Label it a derivation; no source states the number.** |
| 27 | `CONSOLIDATED-BATCH-2.md` warns near-100% recall is not evidence the estimator works | CONFIRMED **verbatim** | Caveat 2 |

### §1a–§1d

| # | claim | verdict | evidence |
|---|---|---|---|
| 28 | two-estimate (raw/informed) protocol agreed per Arnon 2026-08-21 | CONFIRMED | `CONSOLIDATED-REPORT.md:188` |
| 29 | the 2x2, incl. the "raw good / informed bad" cell | CONFIRMED | ibid. |
| 30 | must record plan-stage kills and scope changes with direction | CONFIRMED | ibid. |
| 31 | grep finds raw/informed vocabulary only in `108-prereg`, `95-prereg`, `98-chunk2-prereg` + two consolidated reports | **CONFIRMED — re-run exactly** | `grep -l` over `reports/surprise/*.md` returns those five and no others |
| 32 | never as a pair; not one ticket has both | CONFIRMED | 95 and 98-chunk2 both self-label a single *informed* estimate; 108 likewise |
| 33 | 105 "PREMISE REFUTED", recall 0/0, precision 0/2 | CONFIRMED **verbatim** | `105-scored.md` |
| 34 | grammar `comment` rule fires **zero times** on `echo hi # trailing comment`; `#` treated like an ordinary word | CONFIRMED | `105-scored.md` probe table |
| 35 | *"I treated 'the parse succeeded' as 'the parse was correct'"* | CONFIRMED **verbatim** | `105-scored.md:34` |
| 36 | Arnon suspected a PEG gap, coordinator said no, **he was right** | CONFIRMED **verbatim** | ibid. |
| 37 | the series has no scoring rule for PREMISE REFUTED | CONFIRMED | stated in source; nothing added since |
| 38 | cause code `N` — 3 instances, all caught pre-commit, two failed closed and one open | CONFIRMED **verbatim** | `CONSOLIDATED-BATCH-2.md` cause table + *"`N` deserves separate reporting and separate severity"* |
| 39 | 101's brace-group change was the fail-**open** one (deny → allow) | CONFIRMED | ibid. |
| 40 | cause code `S` fired twice, on 99 and 104; corrective was written into a per-ticket file, never re-read, fired again three days later | CONFIRMED | `CONSOLIDATED-BATCH-2.md`; `104-scored.md:38` — *"Twice now, in the same ticket family, three days apart"* |
| 41 | Arnon on cause `A`: *"Absorbed is not a bad classification..."* | CONFIRMED **verbatim** | `RESULTS-LOG.md:139` |
| 42 | "what did this make false?" proposed for the next batch, never adopted | CONFIRMED | `CONSOLIDATED-BATCH-2.md` Caveat 1 |
| 43 | 98 chunk 4 touched 5 files against a predicted 2; the missed three were docs an earlier chunk invalidated | CONFIRMED | ibid. (0/0 production, 40% on files overall) |
| 44 | the touch-set metric cannot see `.claude/`; 88 and 89 both affected; for 89 the skill file was the ticket's named root cause | CONFIRMED **verbatim** | `RESULTS-LOG.md`, "The two findings that are about the INSTRUMENT" |
| 45 | `715cdbd` found the deeper version: `.claude/skills/` is the install target and a **stale** copy | CONFIRMED | commit body |
| 46 | *"Editing it is editing site-packages."* | CONFIRMED **verbatim** | `715cdbd` commit body |
| 47 | that commit fixed the two files | CONFIRMED, but see **F9** | 2 files changed; one gained a broken link |

### §2 — ticket 108

| # | claim | verdict | evidence |
|---|---|---|---|
| 48 | "IN FLIGHT", "Not committed at `715cdbd`" | **REFUTED** | F1 |
| 49 | Arnon: *"hook.parse_hook_input() looks like part of the contract..."* | CONFIRMED **verbatim** | quoted identically in `108-prereg.md`, the ticket, and the `9b4ff1d` commit body |
| 50 | ticket 104's brief: *"DO NOT add validation to the dataclass..."* | CONFIRMED **verbatim** | `proposed-tickets/108-...md:31`; corroborated `104-scored.md:38` |
| 51 | the required set is not the dataclass's non-Optional fields | CONFIRMED | commit body: *"three of six non-Optional fields were ever enforced"* |
| 52 | `EmptyStdinError` → `EmptyHookInputError`, with the stale-name rationale | CONFIRMED **verbatim**, and **shipped** | `claude_code_contract.py:96` |
| 53 | prereg locked 2026-08-23 15:43 | CONFIRMED | `108-prereg.md` header + ticket mtime 15:43:00 |
| 54 | the prereg hedge *"if it argues the other way I want the argument"* | CONFIRMED **verbatim**, and **it did** | U1 in `108-prereg.md`; the implementer argued the other way and won |
| 55 | "**Blocked on**: a decision, plus finishing the work" | **REFUTED** | both done in `9b4ff1d` |

### §3 — pre-push

| # | claim | verdict | evidence |
|---|---|---|---|
| 56 | "Seventy-seven commits are unpushed" | **REFUTED** | 78 |
| 57 | `/documentation-review` is user-invoked; docs changed a great deal (new `heredoc-parsing-design.md`, `multiline-parsing-flow.md`, diagrams, plus the named edits) | CONFIRMED | `git diff --name-only master..too-45` lists all named files, plus README/AGENTS/llms.txt/CLAUDE.md/architecture-as-built/architecture/config-sync/native-pattern-reference/uninstall not named — an illustrative list, not a false one |
| 58 | smoke-test command and the silent-failure rationale | CONFIRMED | matches project `CLAUDE.md` verbatim |
| 59 | two `dot_files` commits owed; the dirty-file list | **TRUE BUT MISLEADING** | F13 — six files dirty, not four; the two owed files are among the omitted |

### §4 — retrospective §12

| # | claim | verdict | evidence |
|---|---|---|---|
| 60 | all eight open questions, substance | CONFIRMED, condensed faithfully | `reports/retrospective.md` §12, items 1-8 compared line by line |
| 61 | item 1 squash-merge → 7x sample size | CONFIRMED **verbatim** | ibid. |
| 62 | item 4 **CLOSED** by `1deb328` / `--stdlib` | CONFIRMED | commit exists; `--stdlib` passes today |
| 63 | item 7: `run_guard_canaries` still defaults to the installed binary; `--guard` still does not print which binary | **CONFIRMED at HEAD** | `tools/architecture_fitness.py:3277` falls back to `resolve_toolguard_binary()` (tries `~/.local/bin/toolguard` then PATH); `render_guard_text` prints only `canaries: N evaluated against the live hook` |
| 64 | therefore every `--guard PASS 12/12` in the record describes shipped v0.5.1 | CONFIRMED | retrospective states it verbatim |

### §5 — dispositions

| # | claim | verdict | evidence |
|---|---|---|---|
| 65 | 102: Arnon *"if no evidence - then tell me and I'll defer as a new YouTrack ticket."* | CONFIRMED **verbatim** | ticket 102 DISPOSITION section |
| 66 | 102 evidence: featherhill 0, instagram 0, toolguard 3 raw / 2 false positives / third a JSON latency benchmark | CONFIRMED **verbatim** | ibid. |
| 67 | 102: whether the YouTrack ticket was filed is unverified | **UNVERIFIABLE** — and correctly labelled as such | not checked here either |
| 68 | 102: fix earns its place on silent leaf corruption, not on the deny bypass | CONFIRMED | ticket's own analysis |
| 69 | 91 open, never investigated beyond the ticket-79 round-3 finding, no reproduction | CONFIRMED **verbatim** | ticket 91 "Status" |
| 70 | 91 contradicts `CLAUDE.md`'s hardest rule | CONFIRMED | ticket 91 "Why it matters" |
| 71 | punch-list quote *"Still open for Arnon..."* | **TRUE BUT MISLEADING** | F12 — truncated |
| 72 | 92 "probably closed by ticket 98, never confirmed" | **REFUTED (stale)** | F6 |
| 73 | 70 AE2 open; *"half a narrowing is a broadening"*; 70 committed as `92e6edd` | CONFIRMED **verbatim** | ticket 70:53; commit in log |
| 74 | 107 reframed 2026-08-23 by Arnon around the package boundary | CONFIRMED | ticket 107 REFRAMED section |
| 75 | 107: *"A single-character test is the simplest parsing there is"* as Arnon | **MISATTRIBUTED** | F5 |
| 76 | 107: *"We have plenty of future work before we do get into subtle things like this."* | CONFIRMED **verbatim** Arnon | ibid. |
| 77 | 107: risk already retired by 105 phase 2's grammar label; related to TOO-69; LOW, not scheduled | CONFIRMED | ibid. |
| 78 | 106 DECIDED — not doing it (Arnon, 2026-08-23) | CONFIRMED | ticket 106 `# DECISION 2026-08-23 (Arnon): NOT DOING IT`, with *"I agree about not doing 106, now that I understand it."* |
| 79 | 106: `audit_parts`/`deny_check_parts` checked identically, differ only in audit visibility; propagates into `judge_unit` as three parallel length-matched sequences | CONFIRMED **verbatim** | ticket 106 |
| 80 | 106: the concept-map bargain quote | CONFIRMED in substance, **lightly paraphrased** | ticket: *"if the map turned out easy to write, ship it and stop; if hard, the difficulty is the refactor spec"*; doc: *"if it is easy to write, ship the map and stop..."*. Not attributed to a person, so not a fabricated mandate — but it is inside quotation marks and is not verbatim |
| 81 | §5 heading "Tickets whose DISPOSITION was never made" | **TRUE BUT MISLEADING** | two of six rows (106, 107) are explicitly decided, as the rows themselves say. The heading contradicts its own table |

### §6 — `--undeclared-types`

| # | claim | verdict | evidence |
|---|---|---|---|
| 82 | four findings, still present, verbatim block | **CONFIRMED — re-measured live at `9b4ff1d`** | output byte-identical, including "examined 353 public function(s)/method(s); 12 exempt by serialiser-name convention, 0 exempt via explicit allowlist, 3 return an undeclared dict but are never called outside their own module" and all four sites at `config:164`, `config:2222`, `rule_sort:488`, `subagent:141` |
| 83 | check is report-only and does not fail the build | CONFIRMED | header line says so; exit 0 |
| 84 | *"None fixed; that is Arnon's call, not a subagent's."* | CONFIRMED **verbatim** | `TOO-45 punch-list 2026-08-22.md:65` |
| 85 | `subagent.identify_current_agent` may be moot | CONFIRMED as a hedge | auto-memory records subagent ID broken / logging-only |

### §7 — deferred with a reason

| # | claim | verdict | evidence |
|---|---|---|---|
| 86 | 17 CLOSED on zero exposure across **42,113** native-intent rules; immunity structural; revisit trigger = first deny rule not ending in `*` | CONFIRMED **verbatim** | `TOO-45-punch-list-2026-08-20.md:58`; `resolved/17-...md:157` |
| 87 | 21 skipped — featherhill "blanket allow" was toolguard's own dev traffic on **2 days of 49** | CONFIRMED **verbatim** | punch-list :56 |
| 88 | 34 — 98 occurrences, all dogfood; fix direction never chosen; one deliberate RED test in the tree | CONFIRMED | punch-list :87; `DECISIONS-PENDING.md` A4 |
| 89 | 36 — 652 of 657 are this repo's own disclosure markers | CONFIRMED **verbatim** | punch-list :56; retriage :33 |
| 90 | 36 kept alive by the false `CLAUDE.md` claim + fail-closed message that trains agents out of disclosing; **never re-measured against 105** | **REFUTED (stale)** | F6 — re-measured and closed 101 s later; the `CLAUDE.md` claim is now true |
| 91 | 83, 84, 87 zero occurrences, skipped at Arnon's direction | CONFIRMED | punch-list :56; retriage :57 |
| 92 | 40 dead under TOO-67; 93 → Arnon filed TOO-68; 90 → Arnon: skip | CONFIRMED | `phase 3 resume.md:202,506`; punch-list :378 |
| 93 | advisory tier 37, 53, 56, 61, 62, 66, 72, 75 skipped without tickets; *"a defect in an advisory analyzer cannot silently permit anything"* | CONFIRMED **verbatim** | retriage :16; punch-list :60 |
| 94 | **75 is the closest call and the one to revisit first** | CONFIRMED **verbatim** | punch-list :60 — *"**75** is the closest call — it feeds rule proposals — and is the one to revisit first if any are."* |
| 95 | 75: `_command_key` hand-rolls tokenization; every disclosed command keys on `#` | CONFIRMED | `DECISIONS-PENDING.md:241`; ticket 75 §1 |
| 96 | "only about a third of the open queue has a log signature at all" | CONFIRMED **verbatim** | `TOO-45-retriage-2026-08-20.md:14` |

### §8 — design tickets awaiting a decision

| # | claim | verdict | evidence |
|---|---|---|---|
| 97 | source section attribution | **MISATTRIBUTED** | F8 |
| 98 | none of the listed tickets appears in `git log --grep=TOO-45` | CONFIRMED | verified against all 78 commits |
| 99 | 02 *"deferred, needs a design decision"* | CONFIRMED **verbatim** | `00-INDEX.md:47` |
| 100 | 06 *"deferred at Arnon's request, for discussion before push"*; ~90 tests; classifier and scorer both proven biased; residual silent loss in **13 of 24** implementation styles | CONFIRMED **verbatim** | `00-INDEX.md:48`; ticket 06 :20, :30 |
| 101 | 08 deferred; global guidance carries the rule | CONFIRMED **verbatim** | `00-INDEX.md:50` |
| 102 | 11 PARTIALLY FIXED, measurement benign, **one doc sentence still wrong** | **CONFIRMED, and still wrong at HEAD** | `00-INDEX.md:52`; `docs/configuration.md:517` still says "the Bash-only inline/heredoc-foreign-code floor". Note: the ticket file has been moved to `TOO-45/resolved/`, which the doc does not mention |
| 103 | "the ask floor" names two different mechanisms and the campaign briefed one as the other | CONFIRMED **verbatim** | `DECISIONS-PENDING.md` A7 |
| 104 | 12 deferred | CONFIRMED | `00-INDEX.md:53` |
| 105 | 13 *"Arnon: needed before RC1"*, not trivial | CONFIRMED **verbatim** | `00-INDEX.md:54` |
| 106 | 16 found by Arnon at the #10 review; *"#10 made this look solved without solving it"*; residual → TOO-51 | CONFIRMED **verbatim** | `00-INDEX.md:55` |
| 107 | 31 is a decision and a stopping rule, not a work order; the ~65 figure conflates vacuous with non-distinguishing | CONFIRMED **verbatim** | `00-INDEX.md:77`; ticket 31 :107-123 (*"Do not re-report the ~65 figure without re-deriving it"*) |
| 108 | 33 headline contradiction still live in `config.py` | **UNVERIFIABLE at HEAD** | true to `00-INDEX.md:79` (2026-08-20) and to `DECISIONS-PENDING.md` A6; not re-measured against the tree by me, and the #07 sweep commits touched that file |
| 109 | 32 item 2 **DEMOTED**, justification measured false; item 1 shipped as `bd44605` | CONFIRMED **verbatim** | `TOO-45-punch-list-2026-08-20.md:374`; `phase 3 resume.md:466`; commit in log |

### §9 — standing hazards

| # | claim | verdict | evidence |
|---|---|---|---|
| 110 | `npx canopy@latest` prompts; two grammar agents blocked 90+ minutes each; both misread as stalled | CONFIRMED **verbatim** | `phase 3 resume.md:684`; `105-phase1-scored.md:42` |
| 111 | `git worktree` ALWAYS prompts (Arnon) | CONFIRMED as attribution; **stale in this project** | `phase 3 resume.md:685`; but `toolguard_hook.toml:62` allows `Bash(git worktree *)` |
| 112 | use bare `npx canopy`, run from `toolguard/parser/`, canopy not on PATH | CONFIRMED **verbatim** | `phase 3 resume.md:664-670` |
| 113 | rule at `:60`, existing `Bash(canopy *)` at `:59` | CONFIRMED (line numbers exact) | file lines 59, 60 |
| 114 | "**The exact command that blocked both agents would block again**" + "two open options" | **REFUTED** | F4 — line 61 |
| 115 | pyscn: AST census 79 files / 951 functions; pyscn 49 files / **213 functions — 22%**; `config.py` 19 of 58; `bash_parser.py` (182 functions) absent | CONFIRMED **verbatim** | `phase 3 resume.md:719` |
| 116 | so "avg complexity 7.8" and "Health 72/100" must not be quoted as package-level | CONFIRMED **verbatim** | ibid. |
| 117 | corrects an older note claiming most offenders were canopy-generated | CONFIRMED **verbatim** | ibid. |
| 118 | Arnon 2026-08-23: a function over a threshold is a place to look, not a verdict; `judge_unit` at 20 worth splitting, `node_kind` at 15 not | CONFIRMED | `pyscn-2026-08-22-disposition.md` — Arnon's standing-position blockquote plus *"Watch, do not refactor — the ordering comments are the asset"* |
| 119 | duplication 15.9% "not triaged and **no recommendation was made**" | **TRUE BUT MISLEADING** | F7 |
| 120 | *"Severity from a clone detector is not severity in this codebase's sense"*; earlier campaign changed its conclusion three times | CONFIRMED **verbatim** | `pyscn-2026-08-22-disposition.md:72` |
| 121 | `check_doc_links.py` `LINK_RE` uses `[^\]]+`, skipping `` [`[native]`](...) ``; still present at **:42** | **CONFIRMED — line number exact** | `tools/check_doc_links.py:42` |
| 122 | "measured: 4 of 425 links skipped, one genuinely broken" | **UNVERIFIABLE** | no source cited and I did not find the measurement record; I did not re-derive the 425 denominator. Separately, the tool **fails** at HEAD — see F9 |
| 123 | `tmp/scratch_annotations.py` exists, explores `PUBLIC`/`PRIVATE`/`PACKAGE_PRIVATE`, `package_private()`, `annotationlib.get_annotations`; gitignored; never a task | CONFIRMED | file present, 1,033 bytes, mtime 2026-08-21 18:20; the doc labels its relevance "as inference, not as anything he said", which is the correct labelling |

### §10 — provisional conclusions

| # | claim | verdict | evidence |
|---|---|---|---|
| 124 | exec-wrapper bar resolved by CONFIG not code; user-level `find` allow + `hard_deny`; featherhill's copy removed; no ticket | CONFIRMED **verbatim** | `TOO-45-punch-list-2026-08-20.md:379` |
| 125 | `no_match_fallback = "allow_with_no_warnings"` at `.claude/toolguard_hook.toml:4`, marked TEMPORARY pending TOO-28 | **CONFIRMED — line number exact** | line 4, with the TEMPORARY comment above it |
| 126 | toolguard **9,848 of 51,918 (19%)** fallbacks vs featherhill **0 of 3,675** | CONFIRMED **verbatim** | `reports/replay-instrument-blind-spot.md:63-64`; `phase 3 resume.md:188` |
| 127 | Arnon's better method — re-score as if the fallback were `ask` | CONFIRMED | `.claude/rules/evidence-before-fixing.md`, quoted there |

### §11 and cross-cutting

| # | claim | verdict | evidence |
|---|---|---|---|
| 128 | lessons §6 prediction and falsifiable condition, "Revisit at CP2" | CONFIRMED **verbatim** | `TOO-45 lessons.md` §6, which is literally headed "(open)" |
| 129 | retrospective adds *"the split's evidence comes mostly from before it was deliberate"* | CONFIRMED **verbatim** | `reports/retrospective.md` §12 item 6 |
| 130 | three measured instances of a clean corpus not being evidence (18, 98 chunk 2, 101) | CONFIRMED **verbatim** | `CONSOLIDATED-BATCH-2.md` |
| 131 | `test/unit/test_deny_penetrates_constructs.py` exists — 17 constructs, one subTest each, plus a benign control | CONFIRMED (file exists at HEAD) | present; construct coverage is via subTest, so the "17" is not a test-function count |
| 132 | featherhill is NOT immune to probe traffic; 8 of 9 `find -exec`/`-delete` are probes | CONFIRMED **verbatim** | `.claude/rules/evidence-before-fixing.md` |
| 133 | four instrument errors in one day, all caught by contradiction (golden keyed on non-existent fields; 90-char truncated brace check; coverage through `tail -40`; a glob matching a test's `.cover`) | CONFIRMED **verbatim** | `phase 3 resume.md:721` |

---

## What survives

The document's **analytical core is sound and unusually well-cited**. Every number I could re-measure reproduced: the four `--undeclared-types` findings are byte-identical; the suite, corpus, ruff and all five fitness modes are as stated; `check_doc_links.py:42`, `toolguard_hook.toml:4`, `toolguard_hook.toml:59-60` are exact line numbers; 42,113 / 652 of 657 / 98 dogfood / 9,848 of 51,918 / 0 of 3,675 / 608 of 620 / 811 of 958 / 13 of 24 / ~90 tests all trace to a named file and line. Every Arnon quote but one is verbatim.

**The failures are all one shape: state read at a moment and written as though timeless.** Six of the seven REFUTED verdicts (F1, F2, F4, F6 ×2, and §3's commit count) are *staleness*, not error — three of them by minutes, one by 22 hours, and two caused by this document's own flags being acted on. That is the sister document's finding restated: **ticket-file text and hand-carried notes were treated as the state of the world, and git and the live config were not consulted.** F4 is the worst of them, because the doc quoted line 59 and line 60 of a file whose line 61 refutes its conclusion.

**The single most damaging item is F5**, because it is the only one a later reader cannot detect: a paraphrase inside quotation marks, immediately after "Reframed 2026-08-23 by Arnon", in a document about to become the only surviving record.

## Minimum repairs before the sources are deleted

1. §2 and the header: replace "IN FLIGHT / not committed / blocked on a decision" with `9b4ff1d`, and carry the commit body's *rejected* justification — it contradicts §2's "proposed resolution".
2. Header and §3: 78 commits, and drop "nothing is blocked on work".
3. §5/107: attribute the paraphrase to the ticket author, or replace it with Arnon's actual sentence.
4. §5/92 and §7/36: mark closed, with the re-measurement evidence now in the ticket files.
5. §9: delete "the exact command would block again" and the "two open options"; record that `Bash(npx canopy@latest *)` and `Bash(git worktree *)` are in the project allow list (uncommitted in `dot_files`).
6. §9: delete "no recommendation was made".
7. §1d/§9: record that `check_doc_links` fails at HEAD on a link `715cdbd` introduced.
