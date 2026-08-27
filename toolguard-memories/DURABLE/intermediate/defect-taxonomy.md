---
title: TOO-45 defect taxonomy — what the campaign actually found, and what the distribution
  says
tags:
- TOO-45
- durable
- taxonomy
permalink: toolguard/durable/intermediate/defect-taxonomy
---

# TOO-45 defect taxonomy

**Corrected 2026-08-23 against an adversarial verification pass** (`VERIFIED-defect-taxonomy.md`, which re-read all 77 numbered ticket files plus the index in full and checked 32 claims). Corrections are marked inline as **Corrected 2026-08-23**. The defects it found concentrate in two places: **the outcome census, which was derived from ticket text that the branch had already moved past**, and **three interpretive sentences that reached further than the counts underneath them**. What it found solid: every quotation checked is verbatim and correctly attributed (8 of 8, across 7 tickets); every mechanism description in "The cases worth carrying forward" that could be checked against its ticket (18, 20, 21, 29, 37, 56, 66, 72, 73, 79, 82, 96, 97, 105, 106, 107) is accurate; the failure-direction and discovery-method lists partition the 76 exactly; and the ~39% corrections figure survived an independent strict recount.

## What was read, and what "one ticket" means here

Source: every file directly in `toolguard-memories/TOO-45/proposed-tickets/` — **78 files: 77 numbered ticket documents plus `00-INDEX.md`.** Each was read to the bottom, because a large fraction carry an amendment, `CORRECTION`, `MEASURED`, `DISPOSITION`, `REFUTED` or `DECISION` section that changes or reverses the framing at the top. In several cases the bottom of the file says the opposite of the title.

**Counting decision**: `04-config-layer-stderr-consolidation.md` is explicitly superseded by `04-error-reporter-and-config-layer-stderr.md`, so the two are counted as **one** subject. That gives **76 distinct tickets** as the primary corpus, and every count below is out of 76 unless stated otherwise.

**The `resolved/` subdirectory holds 31 more files (29 distinct subjects — the three `15-*` files are one chain) and was NOT part of the assignment.** I read their headline framing but not their bodies, so they appear only in a clearly-labelled secondary section at the end. This matters for interpretation: `resolved/` is where the *fixed* work went, so the primary corpus is biased toward what remained open.

~~**Four tickets referenced in the index have no file anywhere** — 11, 16, 17 and 57.~~ **REFUTED 2026-08-24. All four exist, in `TOO-45/resolved/`** — a sibling of the `proposed-tickets/` directory that was searched: `11-ask-floor-scope-non-bash-tools.md`, `16-toolspec-cannot-describe-a-user-declared-tool.md`, `17-native-wildcard-end-anchor-false-negative.md`, `57-maintenance-apply-could-enact-a-broadening-and-ignores-nosecurity-withholding.md`. So this is not a gap in the record; the four are the *resolved* set, and their location is the answer to what happened to them.

**Two things make this worth more than the correction itself.** First, the adversarial verification **confirmed the false claim** (`VERIFIED-defect-taxonomy.md` claim 4: *"absent from both directories"*) — the independent check searched the same two directories and reproduced the identical under-match, so a second pair of eyes bought nothing because it inherited the scope. Second, **ticket 16 turned out to be the single best piece of evidence in the escaped-defects analysis** (`07-escaped-defects.md` chain C1): the missing file was not an incidental gap but the most load-bearing document in the set. An under-scoped search does not fail uniformly — it removed the one file that mattered most.

---

## The counts

### Failure direction

| direction | count | share |
|---|---|---|
| **fails open** — permits, or fails to block, or an instrument certifies something it never examined | **31** | 41% |
| **fails closed** — blocks or asks where it should not | **5** | 7% |
| **neither** — structure, readability, docs, tests, dead code, instruments without a decision consequence | **39** | 51% |
| **refuted before a direction could be assigned** | **1** (82) | 1% |

Fails open: 13, 14, 18, 19, 20, 21, 22, 34, 37, 39, 40, 42, 52, 56, 61, 64, 66, 70, 73, 74, 75, 77, 78, 79, 83, 84, 89, 91, 92, 93, 102.
Fails closed: 36, 72, 86, 87, 101.
Refuted: 82.

**Corrected 2026-08-23 (verification claim #6):** the original sentence said *six* tickets are bidirectional and counted under fails-open, and named 72 among them — but 72 appears in the **fails-closed** list above, not the fails-open one. The lists are what the counts were computed from, so the counts stand and the prose was wrong. Restated: **five tickets are bidirectional and counted once, under fails-open**: 20 (escalates `ask`→`allow` *and* silently tightens `allow`→`ask`), 22 (reports an unsafe deletion as safe in both directions), 61 (false negative on a loose fallback, false positive on a hardened one), 77 (`FOO=1 rm` evades a deny *and* `TG_INTENT=1 ls` loses its allow), 102 (leaf corruption plus a deny evasion under one config). **72 is also bidirectional** (cries wolf *and* cannot see a `.peg` change) but was counted under fails-closed. Two more are directionally awkward and I made a call: **40** is a guard failing *open* (it accepts a write it should refuse) whose runtime consequence is fail-*closed* (the config becomes unloadable and every decision clamps to `ask`); **13** is filed here because a shared-level `deny` anchored to the project "fails open relative to what the author probably intended", though its measured symptom is a scattered audit trail.

**The ratio that matters is 31:5 — roughly six fails-open findings for every fails-closed one.** That is not a property of toolguard; it is a property of what is *findable*. A fails-closed defect produces a spurious prompt that a human notices and can report. A fails-open defect produces silence. The campaign found six times as many of the silent kind because the loud kind had already been reported and fixed by ordinary use.

### Discovery method

| method | count | share |
|---|---|---|
| **mutation testing / the test-repair campaign** — delete or invert a mechanism, run the suite, see nothing fail | **18** | 24% |
| **direct measurement or probing** — A/B trees, sandbox runs, corpus probes, executed reproductions | **15** | 20% |
| **Arnon asking a question, reviewing, or instructing** | **14** | 18% |
| **a tool reported it** — pyscn, pyright, the architecture judge, the MR-10 change canary, an AST sweep | **8** | 11% |
| **static analysis / code reading alone** | **8** | 11% |
| **executing the code's own comments and docstrings** (the #07 sweep method) | **6** | 8% |
| **a blinded review round on another ticket's fix** | **5** | 7% |
| **field evidence — it actually happened, both times to this repo's own agent, never to a user** (see the correction below) | **2** | 3% |

Mutation/test-repair: 31, 34, 37, 39, 40, 47, 52, 53, 56, 61, 62, 64, 66, 70, 72, 73, 74, 75.
Measurement/probing: 13, 14, 42, 71, 77, 78, 79, 80, 82, 83, 84, 87, 88, 101, 102.
Arnon: 06, 07, 09, 38, 44, 45, 85, 98, 99, 103, 104, 105, 106, 108. (Verified 13 of the 14: all but **06** open with a verbatim Arnon quote or *"you asked for this"*. 06 was found by the agent — files swept in by a `git add -A` — and only its deferral was Arnon's. Within the ±3 this axis is admitted to carry.)
Tool: 10, 32, 81, 94, 95, 96, 100, 107.
Reading: 01, 02, 03, 04, 05, 08, 12, 97.
Executing the code's own claims: 18, 19, 20, 21, 22, 33.
Review round: 89, 90, 91, 92, 93.
Field: 36, 86.

**The "executing the code's own claims" figure of 6 understates the method badly, and the index says so.** The #07 comment sweep produced eleven findings by that route (tickets 17–27); of those, 17 has no file at all, 23–27 are in `resolved/`, and **five** (18, 19, 20, 21, 22) survive in this corpus. **Corrected 2026-08-23 (verification F9):** the earlier wording said *"eleven findings, of which six are visible here"*, which reached six by counting ticket 33 — but 33 is the sweep's *residue* ticket and is not one of the eleven. The honest statement is **eleven findings from executing docstrings, of which five survive here, plus a separate residue ticket (33).** Every one of those eleven was a claim the code made about itself, in plausible prose, that was false when run — and two of them (`_find_heredocs_in_line` counting *unescaped* quotes, and the backslash-continuation claim) were written down in the source *as correct behaviour*, so reading the comments could not have found them.

**Only two tickets in the entire corpus originate from something actually going wrong during use rather than from analysis.** Ticket 86 (`HOME` unset makes the hook deny every tool call) is a real crash report written by the live hook while a subagent ran tests with `HOME` cleared. Ticket 36 (a `# INTENT:` disclosure comment containing backticks makes toolguard reject the command it describes) was hit by an agent trying to comply with the project's own disclosure rule. Everything else was manufactured by looking.

**Corrected 2026-08-23 (verification F10) — the row label "field evidence" oversells both.** Both incidents happened to **this repository's own agent**, in toolguard's own development environment: 86 while a subagent ran the test suite here, 36 while a test-repair agent complied with this repo's disclosure rule. Neither came from a user. Per the project's own `evidence-before-fixing.md`, dogfood is the corpus that counts least, so the honest statement is **zero tickets originate from a user, and two from the agent that develops toolguard.** The verification further notes that 36 arguably belongs in the mutation/test-repair bucket by this document's own rule, since a test-repair agent hit it.

### Field evidence

Only **8 of 76 tickets carry an explicit numeric exposure or reachability statement**, of which — **corrected 2026-08-23 (verification F7)** — only **six are actual measurements against the three log corpora** (featherhill ~4,722 decisions, toolguard ~52,191, instagram 235): 18, 101, 83, 84, 92, 102. The other two rows in the table below are not corpus measurements at all: **100** is an AST sweep of 383 module-private functions ("zero field reachability by construction", no corpus involved), and **106** is a statement that the proposal is a pure refactor with no behaviour change, which is a claim about the change rather than a measurement of exposure. That is itself a finding: the "measure exposure before fixing" rule was instituted on 2026-08-20, roughly two-thirds of the way through the campaign, and everything committed before then (`05f786d`, 2026-08-19) was fixed without one.

| ticket | measured exposure | disposition |
|---|---|---|
| **18** — multi-token prefix over-grant | **752 rules, 748 of them in featherhill** — see the unit correction below | **PROMOTED** from last to first |
| 101 — grammar rejects a bare `{}` word | 19 raw hits → **~9 genuine** after discarding probe traffic | "should not be sold as a security fix"; **committed** (`03d922c`, 08-22) |
| 83 — tilde-spelled extended-type rules | **0** (1,557 tilde rules and 3,141 extended-type rules, **disjoint**) | DEFER CANDIDATE, flagged for Arnon |
| 84 — regex body ending in escaped whitespace | **0** | PARTIAL DEFER — split proposed, the *swallow* half kept |
| 92 — heredoc piped to a shell | **0** | **FIX anyway** — accidental + silent; the ticket file now ends `# CLOSED 2026-08-23 — RE-MEASURED, fixed` |
| 102 — here-strings misparsed | 3 raw → **0 genuine** (2 false positives, 1 benign) | **DEFERRED by Arnon** to a new YouTrack ticket |
| 100 — orphaned private functions | **0 reachability by construction**; class bounded at 2 of 383 — **AST sweep, not a corpus measurement** | code-health only; **committed** (`b63257c`, `e32d3da`, 08-22) |
| 106 — audit-visibility partition | **0** — no behaviour change at all; **a claim about the change, not a measurement of exposure** | **DECLINED by Arnon** |

**Corrected 2026-08-23 (verification F7/F13): four of the six corpus-measured tickets measured zero or effectively zero** — 83, 84, 92 and 102. The earlier wording, *"six of the eight measured zero or effectively zero"*, was arithmetically right only over a set that included the two non-measurements (100, 106). The conclusion is unchanged and the narrower set states it just as well: **only one — ticket 18 — had mass real exposure**, and it had been scheduled *last* on cost grounds before the measurement reversed the ordering.

**Corrected 2026-08-23 (verification F8) — the unit on ticket 18's headline number.** The table row above originally read *"752 rules, 748 of them in featherhill — ~1 in 5 real decisions."* The thing counted is **rules**, not decisions, and the "1 in 5" comes from dividing by featherhill's **matched** rules: ticket 18's amendment says *"748 of featherhill's 3,675 matched rules"* (= 20%), while featherhill's decision count is 4,722 (748 / 4,722 = 15.8%). The conflation originates in ticket 18 and was inherited here unflagged — a transitive citation. The substance is unaffected: mass real exposure, concentrated in the real user project.

**Was the project's own rule followed?** The rule is: *zero occurrences + accidental reachability + silent failure = still a fix; zero + deliberate-evasion-only = defer.* **In every case where a measurement existed, yes, and the split was applied at sub-ticket granularity rather than per ticket.** Ticket 102 is the cleanest instance: its deny-bypass half needs `bash <<< "..."` deliberately written, so that half defers; its leaf-corruption half fires on any ordinary here-string and is invisible, so that half qualifies. Ticket 84 splits the same way (the `.strip()` half defers, the swallowed `re.error` does not). Ticket 92 measured zero and was still recommended for fix on exactly the stated grounds. And critically, **no defer was taken unilaterally** — 83, 84 and 102 were all flagged back to Arnon, which is what the rule demands.

**The rule was also applied against the campaign's own evidence.** Tickets 101 and 102 both discard raw hits as probe traffic — `find -exec echo {}` matrices, and in 102's case *my own grep pattern from the previous day's measurement session*, logged because toolguard governs this repo's agent. In 102 the raw count overstated exposure by 3x. In 101, six of featherhill's seven hits were probes.

### Outcome

| outcome | count as first published | **corrected 2026-08-23** |
|---|---|---|
| **partially fixed** — an amendment naming exactly what is still open | **21** | 21 (unchanged) |
| **open / awaiting a decision** | ~~**35**~~ | **at most ~20** — overcount of at least 15 |
| **fixed and closed** | ~~**14**~~ | **at least 29** — undercount of at least 15 |
| **deferred with evidence** | **3** | 3 (unchanged) |
| **refuted** — the premise was wrong | **1** | 1, but see the note on 82 below |
| **refuted then redirected** — premise wrong, but the underlying concern vindicated | **1** | 1 (unchanged) |
| **declined by Arnon after full understanding** | **1** | 1 (unchanged) |

Fixed, as first published: 01, 03, 04, 05, 07, 10, 38, 44, 77, 78, 79, 80, 85, 95.
Partially fixed: 14, 18, 19, 20, 22, 31, 32, 33, 37, 39, 40, 52, 53, 61, 62, 64, 66, 70, 72, 73, 75.
Deferred: 83, 84, 102. Refuted: 82. Refuted-then-redirected: 105. Declined: 106.

**Corrected 2026-08-23 (verification F1) — the outcome census was wrong, and the error ran in the flattering direction.** At least **15** of the tickets counted above as "open / awaiting a decision" have a dedicated, named TOO-45 commit on the `too-45` branch, every one of them landed **before** this taxonomy was written (the file's mtime is 2026-08-23 16:11). Measured by the verification against `git log master..too-45`:

| ticket | commit | committed |
|---|---|---|
| 42 | `618a19b` Item 42 — a rejected permission entry stops vanishing | 08-20 |
| 45 | `db23d17` ticket 45 — a static check for inert mocks | 08-19 |
| 74 | `c335e22` Item 74 — the hook honours the tool registry | 08-20 |
| 81 | `5577f9d` Item 81 — a sentinel that watches the receiver | 08-21 |
| 88 | `2648423`, `715cdbd` Items 88 and 89 | 08-21, 08-23 15:51 |
| 89 | `52be738`, `715cdbd` | 08-21, 08-23 15:51 |
| 94 | `dd59c24` Item 94 — the config validator becomes nine questions | 08-21 13:55 |
| 96 | `b9e8592` Item 96 — the file-path handler stops inlining | 08-21 13:37 |
| 97 | `efe7847` steps 1-2, `f11ba43` step 3 | 08-21 |
| 98 | `f8c373a`, `b8947a4`, `4509665`, `726fd09` chunks 1-4 | 08-21 |
| 99 | `4d62339` Item 99 — the contract module gains the shapes | 08-21 15:52 |
| 100 | `b63257c`, `e32d3da` | 08-22 |
| 101 | `03d922c` Item 101 — a bare `{}` is a word | 08-22 |
| 104 | `61ecd7b`, `e32d3da` | 08-22 |
| 108 | `9b4ff1d` Item 108 — reading a hook event moves to the contract | 08-23 16:07 |

The latest, Item 108, landed **four minutes** before this taxonomy was written. Each commit subject matches its ticket's stated ask (94 = split `validation_issues`; 96 = call `_log_allowed_command`; 97 = steps 1-3 of the corrected plan; 100 = delete the two orphans; 108 = `read_pre_tool_use_event(source)`). **Caveat carried from the verification: matching a commit subject to a ticket ask establishes that the work landed, not that no residual remains** — several of these may belong under "partially fixed" rather than "fixed". Either way they are not "open". So the corrected shape is roughly **29 fixed, ~20 open** rather than 14 and 35, and the individual re-classification of each of the 15 is not established here.

**Corrected 2026-08-23 (verification F6): tickets 36 and 92 are also not open.** Both files carry a trailing section headed `# CLOSED 2026-08-23 — RE-MEASURED, fixed` with a measurement table. Honest caveat, because it cuts the other way: both files' mtimes are the same minute as this taxonomy's, so this may be a race rather than a misreading. The 15 tickets above have no such excuse.

**Why this matters beyond arithmetic.** The paragraph immediately below praises the corpus's trustworthiness *because* the 2026-08-19 status audit stamped every ticket against what `05f786d` closed, and quotes the index's warning that *"several `Status:` lines are stale in the misleading direction."* This taxonomy then reproduced exactly that defect: it derived outcome from ticket-file text, and the ticket files were not updated when the 08-21/08-22/08-23 commits landed. **And the method was applied inconsistently** — tickets 95, 80 and 85 were classified `fixed` although none of their files says so, so outside knowledge was consulted for some tickets and not for others, with no stated rule for which.

**Corrected 2026-08-23 (verification claim #22): filing 82 under a bare "refuted" understates it.** The premise was refuted, but the corrected scope shipped as `221eba9` *"Item 82 — toolguard strips the wrappers Claude Code strips"*. The refutation produced a real security fix; the label hides that.

**"Partially fixed" is the campaign's characteristic outcome and it is a deliberate artifact.** On 2026-08-19 a status audit went through every ticket and stamped it with what `05f786d` actually closed and what it did not — *"still open: `cmd_seed_hard_deny` remains unguarded at `installer.py:1675-1689`"*. That is the reason the corpus is trustworthy: the index exists because *"several `Status:` lines are stale in the misleading direction"*, and it says so in its own opening paragraph.

### Subject

| subject | count |
|---|---|
| parser / grammar / command extraction | 12 |
| architecture, types and module structure | 10 |
| config loading, write guards, ledger | 10 |
| maintenance and audit tooling (consolidate, redundancy, danger, security audit, mining, replay, edit-apply) | 10 |
| dev instruments and the test suite itself | 9 |
| matching semantics (patterns, normalisation, wrappers) | 8 |
| audit trail, logging, error routing | 6 |
| compound / verdict-combination design | 5 |
| documentation and comments | 4 |
| session warnings and installer | 2 |

**Unverifiable as published (verification claim #23).** This is the only one of the four axes with **no ticket lists** — the arithmetic sums to 76, but the classification behind it cannot be re-measured by a reader, and the verification could check nothing here beyond the arithmetic and the two figures quoted in the note below.

**Note the shape**: only 8 tickets are about *matching*, which is what a permission tool is nominally for. **Corrected 2026-08-23 (verification F3):** the original sentence continued *"Twenty-two are about the tools that check toolguard, the tests that check toolguard, and the instruments that check the tests"* — but **22 is not derivable from this table**. The two rows matching that description are `maintenance and audit tooling` = 10 and `dev instruments and the test suite itself` = 9, giving **19**; no natural row combination yields 22 (adding `documentation and comments` gives 23, adding `audit trail, logging, error routing` gives 25). Read the instrument figure as **19**, and note that it rests on a classification that was never published as a list.

---

## The cases worth carrying forward

### The one with real field exposure — 18

`Bash(git commit:*)` matches `git commit-tree`, because the token-boundary guard covers the first token only and every later token is matched as a bare string prefix. Found by brute-forcing a *docstring's* claim in `pattern_overlap.py` (79,401 pattern pairs against 798 commands), not by testing the matcher. It turned out to be a documented divergence from Claude Code's own published semantics, and — the part that made it stop being abstract — **all five multi-token Bash rules toolguard seeds into the user's own config at install time over-grant**, including `rm -rf <skilldir>:*` admitting `rm -rf <skilldir> /etc/passwd`. Measured exposure: **748 over-granting rules in the real user project, out of that project's 3,675 matched rules** (**corrected 2026-08-23, verification F8** — the unit is *rules*, not decisions; featherhill's decision count is 4,722, so "~1 in 5" holds only against matched rules). It had been scheduled last.

### The two whose premise was wrong

**82** claimed `sudo rm -rf x` and `env rm -rf x` evading `deny Bash(rm:*)` were toolguard defects. Arnon challenged it and fetched the documentation: neither `sudo` nor `env` is in Claude Code's stripped-wrapper list, so toolguard was **faithful**. The refutation then found a real defect in the *opposite* direction — native strips nine wrappers and toolguard strips none — and it retracted a design note that had been marked *"not to be re-derived"*, which would otherwise have propagated the error into the implementation. **Corrected 2026-08-23 (verification claim #22):** that corrected scope **shipped**, as `221eba9` *"Item 82 — toolguard strips the wrappers Claude Code strips"*. Counting 82 as merely "refuted" hides that a refuted ticket produced a real security fix.

**105** claimed `_strip_comments` was redundant because the PEG grammar already parsed comments. The implementing agent refused to build on it and disproved it: the `comment` rule fires **zero times** while parsing `echo hi # trailing comment`; `#` is absorbed as an ordinary word. The failure mode is named precisely in the ticket — *"I treated 'the parse succeeded' as 'the parse was correct'"* — and it is the campaign's own signature error committed by the campaign. Arnon's original suspicion ("that extra parsing is masking a PEG problem") was then vindicated, and the fix was redirected into the grammar.

### The instrument failures — the largest coherent cluster

**Corrected 2026-08-23 (verification F5/#26): eight tickets *within this 76-ticket corpus*, not nine.** The ninth, **29** (`run_guard` reports `ok=True` over zero cases), is in `resolved/` and therefore outside the corpus every count in this document is drawn from — the document's stated `resolved/` limitation did not travel into the body, and this is one of three places where it should have. The eight in-corpus tickets are: **66** (the architecture-fitness tool reports PASS over an empty tree, and cannot distinguish fixing an import from loosening the layer map), **73** (`"corpus replay N entries, 0 broadened"` carries zero information when the corpus is all-undecidable or empty), **20** (`_check_family2_safe` returns `True` with no corpus at all, its honest evidence string saying `no corpus` while the boolean the caller branches on says safe), **56** (a security audit that narrows to `BUILTIN_TOOLS` and reports clean on a governed MCP tool it never looked at), **21** (four of six advertised destructive categories never fire), **37** (the installer reporting "already present" having seeded zero self-integrity rules), **72** (a staleness banner that cannot see a change to the file `CLAUDE.md` calls the single source of truth), **79** (the golden corpus is structurally incapable of observing an ASK-floor change, because its fixture sets `undecidable_fallback = "allow_with_no_warnings"`).

Tickets 66 and 79 are the sharpest, because they are instruments whose *own* null results had already been quoted as safety evidence.

### The self-inflicted measurement errors

**31** discovered its own headline number was wrong: "~65 assertions that cannot fail" conflated *cannot fail* with *cannot distinguish*, and the second is the worse defect because it actively certifies the wrong thing while reading as thorough. **96** shows a tool being wrong in the tidy direction: pyscn flagged an 80-line clone at 0.98 similarity, and stripping the docstrings showed the code was not similar at all — the *real* duplication was much smaller and real. **62** and **65** and **60** and **69** are findings where **production was correct and only the detection was missing**, which is a category worth naming separately from a defect. **Corrected 2026-08-23 (verification F5/#28): only 62 is in this corpus** — 60, 65 and 69 are all in `resolved/` and so cannot be counted against the 76.

### The one that trained the agent out of the right behaviour — 36

A `# INTENT:` disclosure comment containing backticks and `<<` made toolguard reject the whole command with `"No valid commands found in command line"`. The message names the command, not the comment, so the natural recovery is to drop the disclosure. `CLAUDE.md`'s claim that *"a leading comment does not affect rule matching"* was load-bearing and false, in a document whose entire purpose is instructing agents. **Corrected 2026-08-23 (verification F6): this is no longer a live problem** — ticket 36's file ends with `# CLOSED 2026-08-23 — RE-MEASURED, fixed` and a measurement table, so the section above should be read as history, not as an open defect. (Caveat: 36's mtime is the same minute as this taxonomy's, so which was written first is not established.)

### The architecture findings Arnon caught and no metric did

**97** (`CommandUnit.kind` decides both whether the ASK floor applies *and* how the leaf is decomposed) is the diagnosis of why ticket 79 cost eleven agent runs, four review rounds, and **three security weakenings each introduced by the fix for the previous one** — an unoverridable `hard_deny` downgraded to `ask`, an explicit `ask` lost, a `no_match_fallback` warning dropped. All three were caught before commit, **none by the suite**. **106** is the same shape found by a concept-map diagnostic, fully costed, and then declined — which the ticket correctly records as the diagnostic succeeding, not as waste. **107** was reframed by Arnon from a consistency argument into a package-boundary criterion, at which point the current state became acceptable.

---

## Interpretation — clearly separated from the counts above

Everything below is my reading, not a count.

**1. ~~This was a bug hunt in the instruments, not in the product.~~ Corrected 2026-08-23 (verification F3/F4): the counts do not support that sentence, and it was the document's sharpest interpretive claim.** Two things were wrong. First, the instrument figure: **19**, not the 22 originally printed here — the subject table's two matching rows are 10 + 9 (see the correction under that table). Second, and more important, the split the sentence implies is not 8:22 in the instruments' favour. Taking the subject table at face value, the **product** rows are parser/grammar 12 + matching 8 + config/write-guards/ledger 10 + compound 5 = **35**, against **19** instrument rows. The verification's own reading of all 77 files agrees: the extractor and grammar tickets (19, 34, 79, 87, 91, 92, 98, 101, 102, 105) are permission bypasses and floor losses **in the product**, not in an instrument, and ticket 19 says explicitly that extractor defects are *"different layer, and worse"* than matcher defects. The honest, narrower version: **matching narrowly construed produced few tickets; the parser and the instruments produced most of them.** The original wording invited the reader to conclude that toolguard's enforcement path was largely clean, which the corpus does not say. What survives unchanged is the project's own strongest datum — ticket 78 fixed a genuine deny-rule bypass and a replay of 26,530 real commands produced zero decision changes — and the narrower reading of it: **toolguard's ability to know whether it was right was mostly absent.**

**Reconciled 2026-08-23, later the same day, and the original sentence turns out to be right in a currency nobody had measured.** `DURABLE/05-campaign-statistics.md` counted **lines** rather than tickets: the package took **15,118 insertions**, while the six new `tools/` instruments plus their four test modules took **21,093 — 39% more**, and with the verdict corpus included **38.6% of every non-memory insertion is measuring apparatus, its tests or its fixtures.** So *"a bug hunt in the instruments"* is **refuted on ticket counts and close to true on line counts**, and the two readings are not in conflict — they measure different things. **No document in the corpus stated both**, which is how one of them could stand unchallenged. The correction above stands as written; treat it as scoped to ticket counts, and cite `05` whenever the effort question is what is actually being asked.

**2. The fails-open/fails-closed ratio of 6:1 measures observability, not risk.** A permission tool that fails closed generates a prompt somebody complains about. A permission tool that fails open generates nothing. So a campaign that goes looking finds predominantly the silent kind — and that is exactly why it was worth going looking. The corollary that the project itself derived is sound: for a failure mode that is silent by construction, a zero field count measures the observability of the bug rather than its absence.

**3. The single most productive method was mutation, and it beat reading by a wide margin.** Eighteen tickets came from deleting a mechanism and watching nothing fail. Several tickets record read-only review passes on the *same files* concluding "nothing substantive" hours before mutation found five to twenty blind mechanisms in them — ticket 75 calls this the "eleventh confirmed instance". The durable lesson is not "write more tests"; it is that **a read-only verdict of "none found" is not a measurement and must never be quoted as one.**

**4. The second most productive method was a human asking a question.** Fourteen tickets originate directly from Arnon, and the two most consequential *refutations* (82 and 105) came from him challenging a premise, not from a review or a metric. Ticket 85 states this outright: *"every architectural error in TOO-45 was caught by a question from Arnon, never by a metric."* Every blinded review round in the corpus was checking prose against *this repository's* code, which structurally cannot validate a claim about Claude Code's external behaviour — and that gap let a false native-semantics claim survive two review rounds and get built into a design decision.

**5. The most surprising thing in the distribution: the campaign's confident analysis was wrong often enough to be a category.** By my count **about 30 of 76 tickets (~39%) carry an explicit correction, refutation, downgrade or reframing of something this campaign had previously asserted** — a count, a mechanism, a cause, a native-behaviour claim, an ownership attribution, a severity. Two premises were wholly wrong (82, 105); nine were materially reframed (21, 31, 38, 83, 84, 97, 100, 102, 107); the rest correct a specific fact. That figure is a judgement call — I counted a ticket once regardless of how many corrections it contains, and "correction" versus "refinement" is a line I drew by hand — so treat ~39% as approximate and directionally solid rather than exact. (The ~39% figure is the one part of this document that survived a hostile independent recount: the verification applied a strict test — the file must explicitly say something previously asserted was wrong, overstated, miscounted, misattributed or must be reframed — and got exactly **30 of 76 = 39.5%**, with a looser reading giving ~50.)

**Corrected 2026-08-23 (verification F2) — the direction claim was wrong.** The original sentence read *"the corrections are almost always in the direction of the ticket having overstated its case."* Classifying the direction of all 30 gives roughly **13-15 overstated, 9-11 understated, 5-7 misattribution-or-mixed** — 2:1 at best, not "almost uniformly". The supportable restatement: **corrections were roughly twice as likely to shrink a ticket as to grow it, and the ones that grew it were among the most consequential.** That is a materially different conclusion, because "uniformly overstated" invites a reader to discount the corpus's severities across the board. The understating corrections include 18 (*"the result is worse than the ticket described"* — three divergences, not one, and the ticket was promoted from last to first), 19 (*"P1 is a DISCLOSURE-FLOOR bypass as well as a deny-rule bypass, and this ticket does not say so"*), 56 (*"That is wrong, and the truth is worse... I recorded only the harmless one"*), 66 (*"TICKET 30's FIX DIRECTION IS MEASURABLY WRONG"*), 70 (*"the title understates it"*), 75 (a read-only pass judged three defects; mutation found 20), 80 (`Path.absolute()` absent from the ticket body and six review rounds), 85 and 98. **This document contained its own counter-evidence and did not reconcile it** — it reports 18's promotion and quotes 56 in the same file as the uniformity claim. What does hold unchanged is that the corrections were found by executing rather than by reviewing.

**6. The corpora contaminate themselves, and the project measured this rather than assuming it.** toolguard governs the agent investigating toolguard, so every probe run while investigating a defect is logged as a command exhibiting that defect's shape. Ticket 102's raw count overstated by 3x; ticket 101's featherhill count overstated by 7x. The correction that "featherhill is unaffected" was itself measured false within two hours of being written — probe traffic follows the agent, not the project. **Any count under ~50 must be read line by line, in every corpus.**

**7. What I could not classify cleanly.** Six tickets are genuinely bidirectional; **corrected 2026-08-23 (verification claim #6): five of them were forced into fails-open (20, 22, 61, 77, 102) and the sixth, 72, was in fact counted under fails-closed** — the original text listed all six as fails-open, contradicting the list the counts were computed from. Two more resisted the axis entirely and I made a call I would not defend hard: **40** (a guard failing open whose runtime consequence is fail-closed) and **13** (whose measured symptom is a scattered audit trail, not a permission error). **Corrected 2026-08-23 (verification F5/#27): six tickets — not nine — are "the code is correct, only detection was missing" within this corpus.** The original list was 60, 62, 65, 69, 45, 12, 100, 81, 96; **60, 65 and 69 are in `resolved/`** and therefore were never in the 76-ticket census and cannot have been filed under "neither". The in-corpus six are 62, 45, 12, 100, 81, 96, which is neither a defect nor a non-defect, and I filed them under "neither" for lack of a better home. **And the discovery-method axis is the weakest of the four**: several tickets were found by one method while investigating something found by another, and I assigned a single primary method per ticket, so those counts should be read as ±3.

---

## Secondary: the 31 files in `resolved/` — index-derived, NOT read in full

Out of scope for this pass and included only so the primary corpus is not mistaken for the whole campaign. **29 distinct subjects** (the three `15-*` files are one chain). All are `[FIXED]` or `[DONE]` per the index and the file headers, which I read; the bodies I did not.

Coarse reading of the headline framing:

- **Fails open**: 14 (the hook's error paths emit their deny on stderr, so Claude Code sees nothing), 23 (`log_crash` fail-open — the hook can exit with no decision at all; the module reported 89/89 OK while `stdout == ""`), 25 (a newline makes a deny rule silently inert), 27 (config cache serves stale data after an equal-length same-mtime rewrite), 41 (`sudo rm -rf ~/.toolguard` is `ask`, not `deny`), 48 (a dangling symlink evades a deny on its target — and writing through it creates the target), 49 (takeover silently replaces a configured fail-closed fallback with `ask`, in the *canonical* setup), 63 (the recommended protection set denies `Write` but not `Edit` of SSH and AWS credentials), 67 (wrapping foreign inline code in an `if` defeats the ASK floor entirely), 15 (`migrate()` rewrites the permission config with no cross-process lock).
- **Fails closed / corrupting**: 24 (`rule_sort` can render a config that no longer parses, bricking it to permanent `ask`), 46 (a JSON array in `settings.local.json` crashes the divergence check on the hook path).
- **Instrument or test blindness where production was correct**: 28, 29, 30, 35, 43, 60, 65, 69 — eight of twenty-nine. Ticket **35** is the sharpest in the whole campaign: `test_hard_deny.py`'s main class had re-implemented production's ordering in its own helper, so ten tests exercised the fixture's copy and detected nothing.
- **Audit / diagnostics**: 26, 50, 51, 58, 68, 76. Ticket **51** measured 4.84% of real audit-log `Command` fields as unreadable back; **76** wrote a factually false annotation into the user's own config.
- **Neither / structural**: 54, 55, 59.

**The important asymmetry**: roughly a third of the *closed* work was fixing instruments and tests rather than the product, which reinforces the primary corpus's headline shape rather than diluting it.