---
title: Escaped defects — what one ticket missed and a later one paid for
tags:
- TOO-45
- durable
- verification
permalink: toolguard/durable/07-escaped-defects
---

# Escaped defects — where insufficient verification cost money later

**The question this document answers**: which defects escaped one ticket, were found by a later ticket, and were findable at the earlier ticket's time by a verification technique the campaign already had in hand?

## TWO QUESTIONS, AND THIS DOCUMENT ONLY ANSWERS THE NARROW ONE — Arnon, 2026-08-25

**An earlier draft of this document conflated two questions and then answered the wrong one in its verdict.** They must be kept apart, because the evidence answers them differently and in opposite directions.

| | question | answer from this corpus |
|---|---|---|
| **Narrow** — the one in the header, and the only one this document measures | Did *insufficient verification at ticket N* cost measurable money at ticket N+k, when the technique was already on the shelf? | **Not clear.** 6 confirmed chains of 23 candidates, a 43% false-lead rate, recoverable cost on the order of 4–8 agent-hours. The mechanism is demonstrated; the magnitude is not. |
| **General** | Does verification pay for itself? | **Clearly yes**, and the evidence is the campaign as a whole rather than anything in the chain analysis below. |

**Arnon, 2026-08-25**, and it is a correction to this document's verdict:

> *"In an agentic loop scenario that was originally aimed narrowly at architectural **refactoring**, various verification techniques yielded numerous real and material bugs that were fixed. Yes, also false positives and low-value bugs. But from a big picture perspective — this crop very clearly affirms the more general question of 'does verification pay for itself'. The narrower question stated at the beginning of the analysis document is not so clear though."*

**The framing that makes this decisive is what the campaign was *for*.** TOO-45 was set up as an **architecture refactor**, not a defect hunt. The bug crop was a by-product. So the general question is answered by a nearly-free experiment: point verification at a codebase nobody was auditing, and it returns 76 tickets, three security regressions caught before commit on a single ticket, and — as a **lower bound of partly-verified provenance, not a count** — roughly fifty production defect tickets from mutation testing alone (`intermediate/practices-with-evidence.md`: fifty is *"a floor, not a ceiling"*, 1 of 3 supporting batches independently verified). **A yield that large, from an activity aimed at something else entirely, does not need a cost model to justify itself.** The false positives and the low-value findings are the expected tax on that, not an argument against it.

**So read the VERDICT below as scoped to the narrow question.** Every caveat there — small recovered cost, no user reached, small sample — is a caveat about *chain attribution*, and none of it bears on whether verification was worth doing. That distinction was missing and is now stated in the verdict too.

## Headline

| | count |
|---|---|
| candidate chains examined | **23** |
| **CONFIRMED** — all four evidence elements | **6** |
| **JUDGED** — some elements measured, the rest a stated opinion with confidence | **5** |
| **UNCERTAIN** — no basis for an opinion | **2** |
| **REJECTED** — examined and found not to be an escape | **10** |

**The rejected count is the load-bearing number.** Ten of twenty-three candidates that *look* like escapes when you read the cross-references are not: the defect was pre-existing and correctly scoped out, or the premise was refuted, or the two tickets are one commit apart with no verification opportunity between them, or the later ticket's own text says the earlier one made the right call. This corpus rewards a credulous reader with chains that do not exist, which is why the tiers below are kept separate.

**A correction to the DURABLE record, found while doing this.** `intermediate/defect-taxonomy.md` states: *"**Four tickets referenced in the index have no file anywhere** — 11, 16, 17 and 57."* **All four exist**, in `TOO-45/resolved/` — a different directory from `TOO-45/proposed-tickets/resolved/`, which is the one that was searched. Ticket 16's file is the single strongest piece of evidence in this whole document (case C1 below), so the error was not cosmetic: the taxonomy's own "gap in the record" was a search that stopped at one directory.

**A structural caveat on the whole exercise, stated up front.** The campaign's own defect taxonomy records that **only 2 of 76 tickets originate from something going wrong in use, and zero from a user** (`intermediate/defect-taxonomy.md`) — everything else was manufactured by looking. So this document measures *how efficiently the campaign found its own defects*, not how much escaped to the field. Nothing here shows a user was harmed by a missing verification step, because nothing in the corpus could show that.

## The evidence bar

Tier 1 requires all four of: (1) the later finding quoted verbatim; (2) a link to the earlier ticket, quoted where possible; (3) a named, concrete technique that would have caught it at the earlier ticket's time; (4) a citation showing that technique was already in use in this project *before* the earlier ticket. Tier 2 states which elements are measured, which are inferred, the opinion, the confidence, and what single piece of evidence would settle it. Costs are labelled as estimates wherever they are estimates; the campaign's own cost data conflicts with itself on several tickets and I use the measured git-timestamp figures, per `02-campaign-cost-data.md`'s own resolution of those conflicts.

---

# TIER 1 — CONFIRMED (6)

## C1. Item 10's own review found the defect class, fixed two of three instances, and left the third in the component that governs

**This is the strongest case in the corpus, and it is stronger than a missing verification step: the verification ran, found the right class, and stopped one file short.**

**1. The later finding, verbatim** (`TOO-45/resolved/16-toolspec-cannot-describe-a-user-declared-tool.md`, *"found by Arnon at the manual review of punch-list #10, 2026-08-09"*):

> ```
> Bash                  -> allow   Command matches allow pattern: ls*
> WebFetch              -> deny    No command provided in tool input
> mcp__acme__fetch_doc  -> deny    No command provided in tool input
> ```
>
> **Governing such a tool does not restrict it — it bricks it.** Every call is denied, the message names a payload key the tool never had, and the user's `WebFetch(https://example.com/*)` allow rule is never evaluated.

**2. The link to the earlier ticket, verbatim** — the same file, and this sentence carries elements 2, 3 and 4 at once:

> **The registry is authoritative on the file branch and ignored on every other.** Punch-list #10 converted the file-path reads and left the command read as a literal — **the same half-converted dispatch its own review flagged in two other files, present in the hook itself and missed by everyone.**

And, recorded as a deliberate decision rather than an oversight:

> **One residual left in the code deliberately**, recorded so it is not mistaken for an oversight: punch-list #10's review flagged half-converted dispatch — reading the payload key from the registry on one branch and hardcoding it on the other — as *worse than no conversion, because it looks finished*. That was fixed in `fixture_loader.py` and `transcript_harvest.py` and **left in `hook.py` itself**, which is where the pattern originates.

**3. What would have caught it at item 10's time** — apply the review's own finding to every consumer, not to the two it happened to name. The review had already identified the class ("half-converted dispatch ... worse than no conversion, because it looks finished"); finding the third instance is a sweep of the same shape across the consumers of the same registry. Ticket 16 also demonstrates the empirical check, and labels it: *"## Measured, not argued"* — run the real hook against a governed non-builtin tool and read the three-line output above.

**4. That technique was in use — it was item 10's own review, on item 10's own commit day.** The review found the class and fixed two instances on 2026-08-09; the third was found by Arnon by hand the same day.

**The second escape, which is the expensive one.** Ticket 16 was **promoted to `TOO-51` and parked**. Five days later, ticket 74 re-derived the identical defect from scratch, with no reference anywhere in its file or its two implementation reports to ticket 16 or TOO-51 (verified by grep):

> `hook._resolve_event` and `_handle_command_tool` read the target from a literal `"command"` key and call `payload_key()` **only on the file-path branch**. Meanwhile `transcript_harvest` and `test.verdict_corpus.fixture_loader` honour the registry for command tools.
>
> **So the contract exists, two consumers follow it, and the hook does not.** A command tool registered with any other `payload_key` is read from the wrong field by the component that actually governs.

Ticket 74's own framing of the provenance: *"Punch-list item **#10, "a supported tool becomes a described thing"**, replaced scattered tool literals with `tool_spec`'s registry. These are the two places the conversion did not reach."* And, on a third divergence found the same day: *"it is the third place item #10's single description of a tool has not actually become single."*

Item 10 is commit `2113d02`, 2026-08-09. Ticket 16 is dated 2026-08-09. Ticket 74 records **Found 2026-08-14**; the fix is `c335e22`, 2026-08-20 — *"Item 74 — the hook honours the tool registry, and an empty one fails closed"*.

**The two findings ticket 74 added that ticket 16 did not have**, and which mutation testing would have produced at item 10's time: an equivalent mutant showing *"deleting Bash's entire registry entry is unobservable"*, and the sort-priority table as a third divergence. On those, the mutation-check element below applies in its own right:

> Measured consequence in the tests: **`payload_key` hardcoded to return `"command"` survived the whole module** at the behaviour tier, because nothing drove the hook through a registered key.

And, for the registry's central claim: *"Proven by an equivalent mutant: **deleting Bash's entire registry entry is unobservable.**"*

**4. That technique was already in use, before item 10.** Mutation-checking a new mechanism was a *required* step in the preceding ticket, TOO-19, whose notes are git-tracked from 2026-07-28 and 2026-08-01 — eight to twelve days before item 10:

- `TOO-19/TOO-19 RESUME HERE - state after Phase 0 commit.md`: *"**Mutation-test new regression tests**: neutralize the fix, confirm the test fails."*
- `TOO-19/TOO-19 parse-failure floor bypass via undecidable segments - fix report.md` carries a section headed **"## Mutation check (required)"**, describing commenting out the new line and confirming the new test fails.

Item 10 added `toolguard/tool_spec.py` (125 lines) and a new `test/unit/test_tool_spec.py` (172 lines) — `reports/surprise/10-scored.md` — and also changed `test/unit/test_hook.py` for the reason *"payload key read from the registry"*. Applying TOO-19's own required step to that new mechanism is what ticket 74 later did, and it fired.

**Cost of the miss** — measured where the corpus measures it, estimated where it does not.

Measured: ticket 74 ran **1h16m wall-clock** (bundled with a RED sweep; git timestamps, `02-campaign-cost-data.md` C-8), **1 implementation pass + 2 blinded review rounds** with a round curve of 5 blocking findings → 1 → commit, and its implementation agent cost **~$1.50–2.50** (A84). Measured on the product side: for eleven days, **every non-builtin governed tool was denied on every call with a message naming a payload key it never had**, and the residual `hook.py:1130` is *still* open, tracked as TOO-51.

Estimated, with the reasoning shown: the marginal cost of the review sweeping the third consumer on 2026-08-09 is minutes — it had already found the class and was already editing two of the three files. The rediscovery in ticket 74 is close to a full duplicate investigation; I would put the recoverable share of its 1h16m at **roughly half**, since 74 also produced genuinely new findings (the vacuous Bash guarantee, the sort-priority table, the empty-registry fail-open). **Estimated saving: ~40 minutes of agent time plus 2 review rounds, and eleven days of a shipped tool bricking any governed MCP tool.** The larger cost is not in hours: a defect found by the user at manual review, correctly diagnosed, and then re-derived from scratch by an agent five days later, is a **tracking** failure as much as a verification one.

**Two honest qualifications.**

- Ticket 74's *second* finding — an empty registry silently disables the hook including hard-deny — is a zero-input defect, and the campaign's zero-input probe family only becomes visible in the corpus on 2026-08-12 (ticket 29, below), three days *after* item 10. Element 4 does not hold for that finding; the chain does not rest on it.
- The `hook.py` residual was **left deliberately and documented**, with a stated reason (*"It is not a one-line fix: the else branch would need a default for tools absent from the registry"*). So the escape is not "nobody noticed". It is that a known, documented, security-relevant residual in the governing component was parked in a working note and then cost a second investigation — which is exactly the failure `00-INDEX.md` records elsewhere: *"a product defect recorded only in the queue is a defect that will never be actioned."*

## C2. A prose-parsing exception sanctioned rather than measured — three later tickets, and it is still live at HEAD

This is the campaign's own founding defect, escaping four times.

**1. The later finding, verbatim** (`TOO-45/proposed-tickets/38-fallback-kind-is-re-derived-from-prose.md`, **Found 2026-08-13**):

> `compound.fallback_kind_for_reason(decision: str, reason: str)` classifies an outcome by **substring-matching the prose the program itself just built**
>
> This is the **exact** shape TOO-45 already measured and fixed once at the audit-trail level, where the cost was **813 of 975 compound-allow decisions under-logged and 1,943 sub-commands with no audit record at all.** Nothing failed and nothing warned; the log simply looked complete.

**2. The link to the earlier work, verbatim** (`TOO-45/reports/retrospective.md` §5.6, headed *"Sanctioning a prose-parse exception that was hiding 1,943 missing audit records"*):

> At CP2, two remaining prose-parse sites were sanctioned as documented exceptions rather than oversights. One of them, `hook.py`'s `_parse_compound_match_details`, kept only reason segments containing `" -> "` … Those sub-commands were **silently dropped from the audit trail**: 813 of 975 compound-allow corpus cases under-logging, **1,943 sub-commands executed with no audit record**, worst observed 10 sub-commands producing 1 entry.
>
> The log records the self-assessment without hedging: *"I sanctioned `hook:524` as one of R3's two permitted prose-parse exceptions at CP2. That call was wrong"*.

**Two** sites were sanctioned. One blew up immediately (the 813/975 incident). The other is `fallback_kind_for_reason`, which is ticket 38.

**3. What would have caught it at CP2** — run the corpus query on the sanctioned exception instead of reasoning about it. The retrospective states this itself, and it is the sharpest sentence in the corpus on this subject:

> **The exception was reasoned about; it was never measured.** Its magnitude was one corpus query away and nobody ran it until R1's scoping trace did.

**4. That technique was already in use, before CP2.** The golden verdict corpus and the R3 prose-parse-site instrument were both built and committed in `d5bdab3`, *"TOO-45: verdict corpus, architecture fitness tool, and step R3"*, 2026-08-04, and strengthened in `11d1fd0` on the same day. The R3 counter was itself reporting *"prose-parse sites 6 → 1"* (`intermediate/rejected-methods-and-metrics.md`) — i.e. the campaign had an instrument that could enumerate these sites, and used its output as a score rather than as a work list.

**Where the chain ran after ticket 38**, because this is the part that bounds the cost:

- **Ticket 90** (2026-08-21, found by the ticket-79 round-3 reviewer) found a *third* live instance, at `toolguard/compound.py:1111` in `_combine_strictest`: *"The leaf's own inner join already contains ` -> `, so this split takes only the text after the LAST arrow and drops everything before it."*
- **At HEAD `305caa3`, 2026-08-23**, `DECISIONS-PENDING.md` records that the *instrument built to catch this antipattern* passes over that same site, because its detector only sees receivers whose own name contains `reason` and the site's receiver is named `r`. Verbatim:

> So the position today is: **the codebase contains an instance of its most expensively-documented antipattern, and the instrument built to catch that antipattern reports PASS.** That is this campaign's signature failure — a mechanism that fails open and says nothing — occurring in the very check meant to prevent it.

And the instrument's sanction list still names `compound.py::fallback_kind_for_reason`, *"a function that no longer exists"*.

**Cost of the miss.** Measured for the first escape: **813 of 975 compound-allow decisions (83%) under-logged, 1,943 sub-commands with no audit record**, plus the retrospective's note that closing it exposed two *further* provenance heuristics that only worked because the missing data was missing. Measured for ticket 38: the punch-list priced it at **3h** (`TOO-45-punch-list-2026-08-20.md` row 7a), fixed as `c6dfdf5`, 2026-08-21. Ticket 90 and the R3 detector gap are **still open**. **Estimated total: 4+ hours of direct rework across three tickets, an unquantified audit-integrity hole that ran for months, and a fourth instance shipping today under a green check.**

## C3. A replay that could not see the change it was clearing — ticket 78's harness existed, ticket 18's did not use it

**1. The later finding, verbatim** (`TOO-45/reports/replay-instrument-blind-spot.md`, **Found 2026-08-20** by the ticket-18 blinded reviewer):

> **Measured instance, not hypothetical.** This repo's own rule `Bash(\obsidian search:context *)` matched **nothing** at HEAD and matches **now**; the real command appears 5 times in `logs/`. The ticket-18 implementation reported *"zero flips across 53,112 logged decisions"* and concluded the change was safe. The correct reading is that **zero flips is evidence of neither safety nor inertness** — it is a null result over a transition the instrument cannot observe.

**2. The link to the earlier ticket, verbatim** — the same report, naming the precedent that existed and was not followed:

> - **Ticket 78**: *"26,530 real commands x 2 package trees, 0 newly-deny, 0 newly-allow, 0 newly-ask, 0 matched-rule changes"* — that one **did** compare matched rules, so it is sound.
> - **Ticket 18 (this session)**: verdict-only. **Not sound as safety evidence.**

**3. What would have caught it** — compare `matched_rule` alongside `decision` in the replay, and, better, re-score the corpus as if `no_match_fallback` were `ask`. The report states the cheap version plainly: *"Ticket 78's harness already did this; it should be the standard rather than the exception."*

**4. That technique was already in use, before ticket 18.** Item 78 is commit `8867367` and item 18 is `c5e50a5`; on the `too-45` branch **`8867367` precedes `c5e50a5`**, so 78's matched-rule-comparing harness was on the branch when 18's replay was run. *Caveat stated deliberately*: both landed on 2026-08-20 and the two tickets' working windows overlapped, so I can prove commit ordering and not clock ordering. The finding does not rest on the hour — the harness was a sibling artifact of the same phase, not a later invention.

**Cost of the miss.** Measured: ticket 18 ran **4h15m** wall-clock and **6 blinded review rounds** — the most of any ticket in the campaign — with a round curve of 2 → 2 → 1 → 3 → 3 → 2 that, in the campaign's own words, *"never converged"* (`05-campaign-statistics.md`). The blind spot was found in that review series. The retrospective damage was then bounded by a follow-up measurement: **featherhill, the real-user corpus, has 0 fallback verdicts in 3,675 decisions, so claims measured there were never masked; toolguard's own logs are 19% fallback.** **Estimated cost: not the whole 4h15m — most of that was the matcher itself — but the invalidation sweep across every prior "zero flips" claim on the branch, plus the permanent downgrade of a body of safety evidence, is real and was avoidable by copying a harness that already existed one commit earlier.**

## C4. Ticket 30's stated fix direction was measurably false — ticket 66 found it one day later

**1. The later finding, verbatim** (`TOO-45/proposed-tickets/66-the-architecture-fitness-tool-passes-over-nothing-and-cannot-see-a-loosened-map.md`, section headed **"TICKET 30's FIX DIRECTION IS MEASURABLY WRONG, AND THIS TICKET INHERITED IT"**):

> **Measured 2026-08-14 on ruff 0.15.14.** Ticket 30 states: *"`ruff format` will leave a three-name parenthesised tuple alone (it only strips the two-name form), so the fix is stable."*
>
> **False.** `except (ValueError, TypeError, OSError):` is reformatted **straight back to the bare form**. So anyone applying ticket 30's fix will have it **silently reverted by this project's own mandated `uv run ruff format .`**, re-blinding pyscn with no signal at all.

**2. The link to the earlier ticket, verbatim** (`TOO-45/proposed-tickets/resolved/30-pyscn-parse-guard-does-not-cover-tools-or-test.md`, Fix direction):

> Cheapest correct fix: parenthesise those three clauses. `ruff format` will leave a three-name parenthesised tuple alone (it only strips the two-name form), so the fix is stable.

Ticket 30's own provenance line: *"TOO-45 #07 … 2026-08-12."* Ticket 66: *"Found 2026-08-13."*

**3. What would have caught it at ticket 30's time** — one command: write the parenthesised three-name clause, run `uv run ruff format .`, diff. Ticket 66 also corrected ticket 30's *enumeration* — *"`comment_hygiene.py` has **three** such clauses (106, 351, 427), not one; repo-wide the totals are **6 three-name clauses across 4 files** and **23 unparenthesized clauses**, not 3 and 22"* — findable by re-running the same census ticket 30 claimed to have run.

**4. That technique was already in use, in the very sweep that produced ticket 30.** `00-INDEX.md`, on tickets 17–27: *"All eleven were found by *executing* a claim rather than reading it."* Ticket 30 is from that sweep, committed as `7460ffb` on 2026-08-12. The sweep's method was applied to the code's claims and not to the ticket's own claim about ruff.

**Cost of the miss.** Small in hours, large as a lesson: ticket 66 records the correction, ticket 66 is **still PARTIALLY FIXED**, and the fact reached the user's permanent auto-memory as *"[ruff strips except-tuple parens] — `except (A, B):` becomes `except A, B:`; harmless at TWO names, but **arity 3+ silently blinds pyscn**, and ticket 30's fix is reverted by ruff itself."* **Estimate: had ticket 30's fix been applied as written, the repo would have carried a fix that its own mandated formatter silently undoes — a defect class this campaign names "green for the wrong reason" — with no signal until someone next measured. The measurement cost about one command.**

## C5. Ticket 80's `--ambient` check had a gap its own author found, and the closing instrument was already in the repo

**1. The later finding, verbatim** (`TOO-45/proposed-tickets/81-ast-cannot-prove-a-receiver-relative.md`):

> **Gap B — a new relative `resolve()` inside a module that already has an owner entry is not reported at all.** The `(module, member)` key already matches, so the site is skipped before any fatality question is asked. Nothing changes in the output.

**2. The link to the earlier ticket, verbatim** — the same file's header:

> **Found 2026-08-19 while building ticket 80's `--ambient` check, by the agent that built it.**

**3. What would have caught it** — a runtime sentinel: wrap `Path.resolve` and `Path.absolute` for the duration of the suite and record any call whose receiver is relative. Ticket 81 states why it is the right instrument: *"Runtime sees exactly what AST cannot — the receiver."*

**4. That technique was already in the repository, and ticket 81 says so verbatim:**

> **This project already has that shape and it already works.** `test/unit/_real_log_dir_guard.py` wraps toolguard's log-writing entry points, records any call resolving to the real repo `logs/` directory, and a companion test asserts the record is empty … That guard exists because a checklist alone failed three times to stop the same leak — the same argument applies here.

Independently confirmed: `git log` shows `test/unit/_real_log_dir_guard.py` first appearing in `51045fe`, 2026-08-01 — eighteen days before ticket 80.

**Cost of the miss.** Measured: item 80 plus two follow-ups ran **3h03m** (C-3), and item 81 became its own commit `5577f9d` with a follow-up agent run of **~1h40m / ~$3.45** (A109). The ticket's own summary of the sequence is the cost statement:

> The route history on this one mechanism: `expanduser` escaped four blinded review rounds and was a **live isolation hole** returning the developer's real home under a patched `Path.home`; `resolve` escaped five; `absolute` escaped six and was found only by enumerating pathlib's surface rather than by review. Every one was invisible to the instrument used to clear the round before it.

**Estimated saving had the sentinel been chosen first: the AST checker's construction, three tickets' worth of route-table enumeration, and the fifteen-odd review rounds those three routes survived.** I would put that at several hours across 44/80/81, against a sentinel that is a ~100-line file the repo already had a working example of. This is the single best-supported "the tool was on the shelf" case in the corpus.

## C6. Ticket 29's zero-input defect had four more instances in the same tool — ticket 66, one day later

**1. The later finding, verbatim** (ticket 66):

> **Newly measured, same shape, four more places:**
>
> - `check_layers` reports **`ok=True` over a tree with zero modules**
> - `compute_predicates` reports **R2, R3, R5 and R6 all `pass=True`** over the same empty tree

**2. The link to the earlier ticket, verbatim** — the same file: *"## 1 — Ticket 29 reproduces exactly, and in four more sub-commands than it names."*

**3. What would have caught it at ticket 29's time** — apply ticket 29's own probe to the tool's sibling entry points. Ticket 29 names the general form itself: *"An empty input to a checker is a configuration error, not a pass"* and *"The general form, worth applying wherever a guard iterates a collection it did not build itself."*

**4. The technique was in use — it is ticket 29's own.** Ticket 29's provenance: *"Found by an explicit probe — 'make the rule set empty or unloadable and see whether anything fails' — rather than by reading the code"*, 2026-08-12. Ticket 29 did apply it to one sibling (*"Emptying `.pyscn.toml`'s layers and rules is **not** fail-open"*) and stopped there; the empty-*tree* mutation, one step away, was not tried.

**Cost of the miss: near zero, and I am flagging that deliberately.** Ticket 29 and ticket 66's findings both landed in the same commit `05f786d`, one day apart, so almost no rework was incurred. **This case is included because it is a clean, verbatim instance of the mechanism — instance-fixing rather than class-fixing — not because it cost anything.** The campaign's own retrospective names the habit in §5.7: *"I fixed the instance and not the class, twice, with the technique already in hand."* A reader tallying dollars should score this one at zero.

---

# TIER 2 — JUDGED (5)

Each of these has real evidence and a gap I am filling with an opinion. The confidence and the settling evidence are stated for each.

## J1. Ticket 44 closed the `expanduser` route and left `resolve` open — ticket 80, same day

**Elements I have (measured):** (1) the later finding, verbatim, from ticket 80 — *"`Path.resolve()` on a **relative** path consults `os.getcwd()` internally. A test that patches `Path.cwd` does not affect it, so a module that resolves a relative path reaches the real process working directory while appearing isolated."* (2) The link, verbatim, from the same file: *"This is the same shape as the `expanduser` hole ticket 44 closed, one fact over: **a derived stdlib call that reads an ambient fact by a route the obvious patch target does not cover.**"* (4) The technique — a runtime sentinel, per C5 — was in the repo from 2026-08-01.

**The element I am inferring:** (3) that ticket 44 *should* have caught `resolve`, not merely that it is the same shape. Ticket 44's remit is ambient state read at point of use; cwd is ambient state and `ambient.cwd()` already existed. Ticket 80's own generalisation is the argument: *"When consolidating reads of an ambient fact, enumerate the stdlib calls that read it *indirectly*, not just the ones that name it."*

**Opinion:** ticket 44 scoped itself to the fact it was chasing (home) and enumerated known-bad routes rather than the fact's surface, which is precisely the weakness ticket 80 then names. A route-enumeration or sentinel pass at 44's time would have produced `resolve` and `absolute` in the same sitting.

**Confidence: high.** **What would settle it:** ticket 44's brief or task recall stating whether cwd was in or out of scope. `TOO-45/TOO-45 ticket 44 ambient facts - coder task recall.md` and `reports/surprise/44-briefing.md` exist and I did not read them.

**Cost, estimated:** item 44 plus follow-up measured **6h56m**; item 80 plus two follow-ups **3h03m**; item 81 a further commit and a ~1h40m follow-up. If 44 had covered the fact's whole surface, my estimate is that **80 and most of 81 collapse into it — call it 3–4 hours saved**, plus the review rounds those routes survived.

## J2. TOO-19 verified "the parser discards comments" with one sample — ticket 36 found the claim false

**Elements I have (measured):** (1) the later finding, verbatim (`36-disclosure-comments-are-not-inert-to-the-extractor.md`, **Found 2026-08-12**): *"A `# INTENT:` disclosure comment containing **backticks** and a `<<` token caused toolguard to reject the whole command with `"No valid commands found in command line"`."* (2) The link — the same file quotes the claim it falsifies: *"`CLAUDE.md` states, in the section that mandates disclosure: > A leading comment does not affect rule matching -- the PEG parser discards it and matches the real leaf command. That claim is **false for at least some comment text**."* The claim's provenance is TOO-19: `TOO-19/Deferred - parser comment preservation for intent disclosure.md` records *"a rule cannot match on a `# INTENT:` comment block, verified 2026-07-29 in the sandbox."* (4) The technique — `toolguard.testing.sandbox` — was in use on 2026-07-29, by definition.

**The element I am inferring:** (3) that a matrix of comment texts, rather than one, was an available and obvious step at the time. The sandbox takes arbitrary command text; varying the comment body across backticks, `<<`, quotes and `$(` is the same experiment run five more times.

**Opinion:** this is the sharpest case in the corpus of *verification that happened and was too narrow*. A universal claim ("a leading comment does not affect rule matching") was established from a single sample and then written into a document whose purpose is instructing agents to prepend comments containing exactly the metacharacters that break it. Ticket 36 puts the consequence well: *"the failure mode trains agents out of disclosing."*

**Confidence: moderate-to-high.** The reason it is not tier 1 is that I cannot show a *matrix-style* sandbox probe in use before 2026-07-29 — only the sandbox itself.

**What would settle it:** any TOO-19-era artifact showing a multi-case sandbox matrix rather than a single probe.

**Cost, estimated:** ticket 36 is one of only two tickets in the whole campaign arising from something actually going wrong rather than from analysis, and the corpus does not record it as fixed. Downstream, ticket 105's grammar work (`63644a7`, `2ca11b2`, 2026-08-22) is the comment-handling rework. **Estimate: a low direct cost, a real and unmeasured compliance cost — every disclosure an agent dropped after being denied for its own comment text is invisible by construction.**

## J3. Ticket 19's P2 fix named the cause and did not reach it — ticket 92

**Elements I have (measured):** (1) verbatim (`92-heredoc-piped-to-a-shell-loses-its-ask-floor.md`, **Found 2026-08-21**): *"`_classify_pipeline_sink` … takes the **last** `|`-separated segment as the heredoc's sink. Here that segment is `bash`, so the heredoc is classified bash-family and its body is spliced back in as **shell source**, reaching the matcher as ordinary shell leaves with no floor."* (2) The link, verbatim: *"Ticket 19's P2 wording — *"segments on `|` alone"* — names this cause, but every example it gives is separator-based, so the fix does not reach it."*

**The elements I am inferring:** (3) and (4). The technique that would have caught it is a **case matrix over sink shapes** rather than over the examples in the ticket text — precisely what ticket 98's spikes later did: *"All three fix cases 15 and 16, which the shipped module fails — P4's escaped apostrophe and ticket 92's `python <<HD | bash`. Neither was targeted; the architectures simply lack those failure modes."* Case-matrix probing against the real parser was in use from at least 2026-08-14 (ticket 78: *"measured through the real matcher against a `git archive HEAD` copy"*, and its 2×2 probe table).

**Opinion:** the fix was scoped from the ticket's *examples* rather than from its *stated cause*, which is a specific and repeatable failure. Enumerating the sink shapes named in the ticket's own sentence would have surfaced it.

**Confidence: moderate.** Ticket 92 explicitly says the exclusion was correct — *"it is not a regression and was correctly kept out of that ticket's scope"* — and I am disagreeing with that judgement only about *finding*, not about *fixing in the same change*. Filing it at ticket 19's time would have been right; folding it into the same commit would not.

**What would settle it:** ticket 19's fix brief, to see whether the `|`-segment case was considered and deferred or simply not enumerated.

**Cost, estimated:** ticket 92 measured **zero occurrences** in all three log corpora and was recommended for fix anyway on the reachability-plus-silence rule; it was ultimately closed by ticket 98 chunk 2, whose single agent run measured **~3h05m** (C-19). **Estimate: modest — the fix rode along with a larger architectural change that was going to happen anyway. The counterfactual saving is the separate investigation round, not the fix.**

## J4. Ticket 79 fixed the prose re-parse for one unit kind — ticket 90 found the other

**Elements I have (measured):** (1) verbatim (`90-plain-unit-prose-still-re-parsed-by-combine-strictest.md`, found 2026-08-21 by the ticket-79 round-3 reviewer): *"A `'plain'` leaf's own multiple sub-commands are still combined into one already-rendered `"cmd -> pattern"`-joined summary string. When the WHOLE compound … is combined a second time, `_combine_strictest`'s own multi-unit branch re-parses that summary as if it were a single match."* (2) The link, verbatim: *"Ticket 79 fixed exactly this shape for `'inline_code'` units … It did not touch the `'plain'`-unit path, where the same re-parse still runs on a different unit kind's own summary."*

**The elements I am inferring:** (3) and (4) — that regenerating the goldens and inspecting *every* changed line was the technique, and that it was available. It demonstrably was: the reviewer used it, on the same corpus (`test/verdict_corpus/`) that has existed since 2026-08-04, and found the survivor by comparing two golden lines.

**Opinion:** this is the same instance-not-class habit as C2 and C6, in the same file, on the same antipattern. Ticket 79's fix author had the corpus diff in front of them; line 2807 was still unbalanced after the fix.

**Confidence: moderate.** Ticket 90 itself calls the defect pre-existing and out of 79's scope, and the reviewer *did* catch it — so this is as much a verification success as an escape. I include it because the same site is the one still live at HEAD under a passing check (see C2).

**What would settle it:** whether the ticket-79 implementer inspected both changed golden lines or only the one that improved.

**Cost, estimated:** none directly attributable — ticket 90 is open, and its own scope note says `verdict`/`sub_matches` are unaffected and only human-readable prose is garbled. **Estimated cost: low today, unbounded later, since it is the input to the audit trail this project has already lost 1,943 records to once.**

## J5. The status audit asserted file-path matching was safe — the ticket-78 implementer disproved it

**What I have (measured):** the false claim, verbatim, in `TOO-45/ticket-status-audit-2026-08-19.md`: *"**File-path tools are symmetric and safe** - all four combinations deny"*, repeated in that file's conclusions as *"#78 is Bash-only; file-path tools are symmetric and safe."* And the correction, verbatim, in ticket 83 (**Measured 2026-08-20**): *"Ticket 78 recorded that file-path tools were "symmetric and safe", so its scope was narrowed to Bash. **That is half true.** … In the **reverse** direction, a `[regex]` or `[native]` file rule written with `~` does **not** match the absolute spelling of the same path."*

**Why this is JUDGED and not CONFIRMED, and why I am arguing against my own thesis here:** the claim was caught **within one day, by the next agent to touch it, precisely because that agent verified rather than relied**. Its own report says so: *"The brief's "file-path tools are symmetric and safe" is half true, and I verified rather than relied on it. … Measured, not reasoned."*

**Opinion:** as an *escape* this is weak — the verification worked. As evidence for the thesis it is strong in the other direction: a claim that would have scoped a security ticket incorrectly was killed by one agent spending minutes on a 2×2 probe. **Confidence that this is an escape: low. Confidence that it is a verification success: high.** I list it in JUDGED rather than in the successes section only because it began as a false claim admitted into a decision artifact.

**Cost:** the defect it exposed (ticket 83) measured **0 occurrences across 57,148 real decisions** — 1,557 tilde-spelled rules and 3,141 extended-type rules, **disjoint** — and was made a defer candidate. **Estimate: the verification cost minutes and saved a wrongly-scoped security change; the underlying defect is worth approximately nothing today.**

---

# TIER 3 — UNCERTAIN (2)

- **Ticket 71's `governed_tools` default.** The ticket itself refuses to resolve the provenance: *"**Worth checking against the punch-list**: item *"governed_tools default change"* touched exactly this default. If the seeded `[]` predates it, this is long-standing; if not, it is a regression from that change."* Nobody ran the check. I have no basis to call it either way; `reports/surprise/10-scored.md` shows the governed-tools default change riding inside item 10's commit, which makes the question answerable but does not answer it.
- **Ticket 74's empty-registry fail-open as an item-10 escape.** Real defect, real link to item 10's registry, but the zero-input probe family enters the corpus on 2026-08-12, three days after item 10 shipped. Whether an agent in 2026-08-09 could reasonably have thought to empty the table is a question about what the campaign knew, and I cannot answer it from the record. Counted separately from C1, which stands without it.

---

# REJECTED (10) — chains that look real and are not

The corpus is dense with cross-references that read as provenance and are not. Each of these was examined and dropped:

| candidate | why rejected |
|---|---|
| ticket 79 → ticket 91 | Ticket 91 states outright: *"Pre-existing, not introduced by ticket 79 -- confirmed present against base (`7d0646d`) too"* and *"Ticket 79 did not introduce the underlying gap."* No evidence 79's remit covered it. |
| ticket 77 → ticket 82 | Ticket 82's premise was **refuted** — the taxonomy lists it as the campaign's one refuted ticket. `sudo`/`env` turned out to be faithful to native, and the ticket's own investigation found a real defect in the opposite direction. Not an escape. |
| ticket 78 → ticket 83 as a code defect | Ticket 78's narrowing was based on a false claim, but 78's *code* was correct and 83's defect is pre-existing and measured at zero exposure. Kept as J5 for the claim, rejected as a code escape. |
| item 04 (error reporter) → ticket 44 | Ticket 44 mentions #04 only as *"an I/O writer is what `error_reporter` already is, introduced by item #04 for routing and suppression"* — a reuse note, not a defect. |
| ticket 18 → tickets 20 and 22 | `00-INDEX.md`: *"20 and 22 are downstream of 18 — fixing the matcher moves their answers."* That is scheduling coupling, not an escaped defect. |
| ticket 51 → ticket 73 | 73 cites 51's 4.3% unparseable measurement as an input to its own argument. No claim that 51 should have found 73's defect. |
| ticket 65 → ticket 74 | 74 says it *"compounds ticket 65"*. Both are test-blindness findings in the same family; neither is the other's parent. Ticket 65's own resolution says *"was test blindness, production was never broken."* |
| ticket 98 → ticket 92 | 98 **fixed** 92. That is the repair direction, not an escape. |
| ticket 84, ticket 102, ticket 86 | No earlier ticket in the corpus is claimed to have touched or scoped these. 84 and 102 measured zero exposure and were deferred; 86 is a field crash (see below). |
| ticket 13, ticket 105 | 13 has no predecessor. 105's premise was **REFUTED 2026-08-22** — *"`_strip_comments` is load-bearing, not redundant"* — so there is no defect to trace. |

---

# NOT DISCOVERABLE AT THE TIME — the counterweight

These are escaped or late-found defects where I can find **no technique in use at the time that would have produced them**. They bound the claim that verification pays, and there are enough of them to matter.

**1. `Path.absolute()`, found only by enumerating the stdlib's surface.** Ticket 80, verbatim: *"**`Path.absolute()` was found by this enumeration** — it prepends `os.getcwd()`, is invisible to a `Path.cwd` patch, and appears in neither this ticket's original body nor the repair agent's route table **nor six review rounds**."* Six blinded reviews by competent agents did not find it, and the technique that did — `dir(Path)` classified member by member, *"70 members, of which exactly 5 read ambient state"* — appears nowhere in the corpus before ticket 80 invented it. **This is the honest counter-case to C5**: the sentinel would have caught `absolute` at *runtime if a test exercised it*, but the enumeration is what found it as a class, and enumeration was not on the shelf.

**2. Contract drift from upstream.** Ticket 85 states the limit of any static instrument, verbatim: *"It can find *known* contract strings that escaped the module. It cannot find a field Claude Code added upstream that we have never heard of — no static rule can, because the vocabulary is the thing being checked."* No amount of verification discipline reaches this class; only a periodic re-read of an external document does.

**3. `HOME` unset denies every tool call (ticket 86).** *"**Observed in production, not constructed.** A crash report was written by the *live* hook at 2026-08-20 11:20:00 while a subagent was running tests with `HOME` unset — the agent's environment leaked into the real hook governing its commands."* This is one of only two field-originated tickets in the campaign, and the environment that produced it (an agent clearing `HOME` inside a governed session) is not a state any test fixture in the corpus was constructing.

**4. The heredoc/substitution shapes that no fix targeted.** Ticket 98, verbatim: *"All three fix cases 15 and 16, which the shipped module fails … **Neither was targeted; the architectures simply lack those failure modes.** That is the strongest evidence that the structure, not its bugs, is the problem."* And: *"**Arnon predicted that before the spikes were built.** Worth recording as a calibration point: the architectural instinct was ahead of the measurement here."* Some defects are dissolved by getting the structure right and are not reachable by any amount of testing the wrong structure.

**5. The discovery-method distribution itself is a counterweight.** The campaign's taxonomy attributes **18 of 76 findings to mutation testing, 15 to direct measurement, and 14 to Arnon asking a question, reviewing, or instructing** (`intermediate/defect-taxonomy.md`). Roughly one in five findings came from a human noticing something, not from an instrument. That share does not shrink with better verification discipline.

---

# VERIFICATION SUCCESSES — where it worked, and why the record is biased

If verification only appeared in this corpus when it failed, the analysis above would be worthless. It does not.

**Read this section as the answer to the general question, not as a counterweight to the narrow one** (added 2026-08-25). Its earlier framing — a balancing item against the escape chains — undersold it. These six items are the campaign-level evidence that verification pays, and they are stronger than anything in the chain analysis, because the yield below came out of work aimed at an architecture refactor rather than at finding defects.

**1. Every surviving blinded review round found something.** `05-campaign-statistics.md`, marked MEASURED-HERE: *"all 27 surviving review-round files report at least one blocking finding."* **The bias is stated in the same source and I repeat it here rather than burying it**: *"The only zero-blocking round anywhere in the record is ticket 45's round 5, and it has **no surviving file** — it exists solely as the terminal entry of a table."* So the population is rounds that produced a document, which correlates with rounds that found something. Treat "27 of 27" as a floor on yield, not as a rate.

**2. Review caught three security regressions that the suite could not.** Ticket 97, verbatim: *"**Eleven agent runs, four review rounds, and three security weakenings** — an unoverridable `hard_deny` downgraded to `ask`, an explicit `ask` lost entirely, and a `no_match_fallback` warning silently dropped — **each introduced by the fix for the previous one.** All three were caught before commit, none by the suite."* This is the strongest single datum in the corpus for review-as-backstop, and it is also the strongest datum for *tests not being the backstop*.

**3. Mutation testing repeatedly found that production was fine and the tests were lying.** Ticket 65 — *"the canonical MCP-terminal decisions could lose provenance and hard-deny could stop applying"* — resolves as *"**was test blindness, production was never broken**"*, and ticket 60 the same: *"the gate was already intact; it was a test coverage gap."* Verification that returns "no defect, but you could not have known" is a success, and it is cheap.

**4. The one agent who checked a brief's claim saved a security ticket from being scoped wrong** — J5 above, verbatim: *"I verified rather than relied on it … Measured, not reasoned."*

**5. The blinded reviewer who found the replay blind spot** (C3) invalidated a body of the campaign's own safety evidence from inside a routine review round.

**6. The corpus replay's `--verify` did work where it was pointed correctly.** Ticket 78's replay compared matched rules and is recorded as sound; `evidence-before-fixing.md` records the strongest null in the corpus: *"a replay of **26,530 real commands across pre- and post-fix trees produced 0 decision changes, 0 matched-rule changes, 0 digest differences.** A real bug, correctly fixed, that had never once fired."*

---

# VERDICT

**What this supports.** Six chains meet the full bar, and in every one of them the technique that would have caught the defect was not merely conceivable but **already running in this repository, on other code, before the ticket that missed it**. That is a narrow and defensible claim, and it is the claim the user's hypothesis needs: these are not hindsight. The dominant pattern across all six is not "we lacked a tool" — it is **instance-fixing rather than class-fixing**, which the campaign's own retrospective names in its own voice: *"I fixed the instance and not the class, twice, with the technique already in hand."* C1, C2, C6 and J4 are four separate occurrences of exactly that, on four different mechanisms.

**What this does not support — and note carefully what it is scoped to.** It does not support **a costed, chain-by-chain** "insufficient verification at ticket N was paid for at ticket N+k" conclusion. **It is not a verdict on whether verification pays for itself** — see the two-question table at the top of this document; that broader question is answered *yes* by the campaign as a whole, and nothing in the five points below bears on it. Each point is a limit on *chain attribution*, which is a much narrower thing. Five reasons I want on the record:

1. **The costs recovered are small and mostly internal.** The recoverable rework across all six confirmed chains is on the order of **4–8 hours of agent time** — my estimate, built from the git-timestamp figures in `02-campaign-cost-data.md` (C1: ~40m of 74's 1h16m plus 2 review rounds; C5: 80+81 ≈ 4h45m, of which perhaps half; C2: ticket 38 priced at ~3h; C4, C6: near zero because they landed in one commit with the tickets they corrected) and deliberately discounted wherever the later ticket did work that was needed anyway. Against a campaign whose phase 3 alone measured **35h38m**, this is real and not decisive.
2. **Two confirmed chains cost essentially nothing** (C4, C6), and I said so rather than padding the total.
3. **Zero of these defects reached a user.** The corpus contains no user-originated ticket. The 813/975 audit-logging loss (C2) and the eleven days of bricked MCP tools (C1) are the only two with a measured product consequence, and both were measured against a corpus or a probe, not a complaint.
4. **The not-discoverable section is not short.** `Path.absolute()` survived six review rounds and needed a technique nobody had; upstream contract drift is unreachable by any static instrument; roughly one finding in five came from Arnon noticing something. A verification-discipline story that ignores those overstates its case.
5. **The strongest case is not a verification failure at all.** In C1 the review ran, was competent, and identified the correct defect *class*; what failed was sweeping the third instance and then tracking the one that was knowingly deferred. That points at follow-through and at where findings are recorded — not at buying more verification.

**Is the sample large enough to generalise? No.** Six confirmed chains out of twenty-three candidates, drawn from one codebase, one campaign, and one agent's working style, with **ten candidates rejected on inspection** — a 43% false-lead rate on chains that looked real from the cross-references alone. The honest summary is: **the mechanism is demonstrated and the magnitude is not.** What generalises from this corpus is the *shape* — a technique in daily use on one mechanism, not applied to the adjacent mechanism, with the gap found days later by the same technique — and the shape recurs often enough (six confirmed, plus five judged) that it is worth building a habit against. What does not generalise is any dollar figure.

**What the corpus DOES support, and it is the bigger finding — added 2026-08-25.** The general question is settled in the affirmative, and the strongest argument for it is the one this document kept walking past: **the `VERIFICATION SUCCESSES` section above is not a counterweight to the chain analysis, it is the answer to the more important question.** Twenty-seven of twenty-seven surviving review rounds found something blocking. Ticket 97 alone had three security weakenings caught before commit, *"none by the suite."* Mutation testing repeatedly proved production sound and the tests lying — a result that is cheap and that nothing else produces. And all of it came out of a campaign **aimed at an architecture refactor**, where finding defects was a side effect rather than the objective. **Verification paid for itself many times over here; what this document could not do is price any individual escape.** Those are different claims and only the second one is weakly evidenced.

**The one recommendation this evidence actually earns.** Every confirmed chain would have been closed by the same one-line habit, and it is cheaper than any instrument in the campaign: **when a verification technique finds a defect, run it once more against the sibling — the other unit kind, the other branch, the other sub-command, the other stdlib route, the other consumer of the same registry.** C1, C2, C4, C5 and C6 are all one sibling away. That is not a process; it is a question asked at the end of a fix.
