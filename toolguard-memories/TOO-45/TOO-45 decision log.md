---
title: TOO-45 decision log
type: note
permalink: toolguard/too-45/too-45-decision-log
tags:
- task-memory
- TOO-45
- decision-log
---

# TOO-45 decision log

Append-only. One entry per iteration: what was attempted, what the guards said, what each judge
said, which interface drafts survived contact, which predicates turned out wrong, and cost.

Written *during*, not reconstructed afterwards — a methodology guide written from memory is
fiction; written from this it is evidence. Companion: [[TOO-45 lessons]] (transferable lessons,
kept separate from this record of what happened).

Plan: [[TOO-45 architecture overhaul execution plan]].

---

## P.0 — planning, 2026-08-03/04

Draft 1 written, reviewed by Arnon, revised to draft 2. Four contested changes proposed; three
survived, one was corrected.

| proposed | outcome |
|---|---|
| R0 demoted to a prerequisite | accepted |
| R1 promoted from fifth to second | accepted |
| Two judges (blinded reviewer + architect judge) | accepted |
| R7 "directives as data with declared phases" as a step | **corrected** — see below |

**R7 was wrong in two ways and the correction matters.** Arnon rejected "declared phases":
phases are an internal implementation artifact, not a documented concept, and formalising them
into rule semantics would constrain something with no demonstrated need. The decisive concrete
argument: `additionalContext` is *already* multi-phase — accumulated across command parts, then
rendered into both the hook response and the decision log — so the first and only directive
would falsify a single-phase tag.

He also rejected it as a *step*: the real abstraction should emerge from the refactoring
iterations rather than being declared against 14 grep hits. Accepted, with the failure mode
named rather than assumed away — the enrichment footprint is tracked as a first-class diagnostic
and a flat canary at a step boundary is a finding that drives the next iteration.

**Root cause of my error:** I read Arnon's first-principles flow sketch as a specification. It
was a demonstration of how to frame a problem *before* committing to structure. Recorded in
[[TOO-45 lessons]].

**Superseded framing:** draft 1 justified R1 as "one verdict type" (tidiness). Draft 2 replaces
that with a principle covering three seams — input shape, output shape, native rule syntax —
unified by the property that **all three change on someone else's schedule**. R1 became a
consequence rather than the principle.

Cost: planning only, no code.

---

## P.4 — git guardrails, 2026-08-04. DONE.

Invariant 6 existed only as prose. Now enforced in `~/.toolguard/rules/git.rules.toml` inside
`<TEMPORARY>` fences (revert = delete fences).

Arnon relaxed git for branch `too-45` and asked me to validate his edits. Findings:

1. **`git clean` was allowed** — would delete `toolguard-memories/` (this log), `logs/` and
   `tmp/` with `-x`. Denied.
2. **`git stash` was allowed.** Arnon argued it is safe because the rules confine work to this
   branch. Agreed on containment, disagreed on relevance: the risk is **silent desync** — a
   stashed change leaves a tree that no longer matches what the loop believes it is testing, so
   the invariants and the corpus pass against the wrong state. Redundant now that the loop can
   commit. Denied.
3. `git bisect` allowed while `checkout` was only ask, though bisect *is* a checkout. Denied.
4. `git rm -r` and `git commit --amend` denied.

Verified two ways: `tmp/git_rules_check.py` (145 cases, 0 failures) and `toolguard --eval`
end-to-end. Read-only forms (`stash list`, `bisect log`, `rm <file>`) did not regress.

**Drift found:** `tmp/git_rules_check.py` validated `tmp/git.rules.toml` — a stale copy loaded by
nobody — while toolguard reads `~/.toolguard/rules/git.rules.toml`. The file's own header
instructs re-running it after every edit, so it was an instruction that actively manufactured
false confidence. Repointed at the governing file. `tmp/git.rules.toml` still exists and is still
named like the real thing; deletion or renaming offered to Arnon, not yet decided.

**Mechanic worth remembering:** with `no_match_fallback = "allow_with_no_warnings"`, removing a
rule from `allow` does NOT stop a command — it falls through and is silently allowed. Anything
that must be stopped needs an explicit `deny`.

Still open in P4: `Write`/`Edit` denies for `logs/**`, `**/.env`, `**/.claude.env`,
`~/.toolguard/rules/**`, `~/.claude/settings.json`, both `toolguard_hook.toml` files.

---

## P.1 — corpus scouting, 2026-08-04

Read-only scout over the 48 log files before designing anything.

| | |
|---|---|
| entries | 16,906 = 9,896 with a command + 7,010 Discovery |
| distinct (tool, target) | **4,982** |
| shapes | 2,214 compound · 448 multi-line · 110 heredoc |
| tools | Bash 6,865 · Read 1,531 · Edit 1,269 · Write 231 |
| verdicts | EXECUTED 9,335 · ASK 541 · **REFUSED 20** |
| secret-shaped matches | **none** across 8 patterns |

**Correction: I had twice quoted "17,167 recorded decisions."** That came from
`grep -c "^## "`, which counted Discovery headings — 41% of the file. The real figure is 9,896.
The parser is validated by the three counts summing exactly to the entry total.

**Design consequence:** real traffic is 0.2% deny. The deny surface, the ASK floors and every
fallback value are essentially unexercised by it, so the synthetic fixtures carry that entire
surface — they are load-bearing, not supplementary.

**Design decisions taken:**
- Harness entry point is `toolguard.tools.decision.decide()`, whose own docstring names it "the
  single entry point for the replay harness". Config loaded once per fixture, not per case —
  `Sandbox.evaluate` re-invalidates the config cache on every call.
- **Two-tier goldens.** `verdict` is a hard invariant; `reason`, `additional_context` and
  `provenance` are tracked and diffed with an explicit acknowledgement path. A single-tier
  golden would either block R3's legitimate rewording or hide a real regression.

Build delegated to `feature-coder` with a spec pinning the fixture matrix. Delegation is safe
here **because the acceptance gate is a mutation test I run myself**, which does not care who
wrote the code.

Status: in progress.

---

## P.1 — corpus delivered, CP1 mutation gate run, 2026-08-04

`feature-coder` delivered: `tools/corpus_build.py` (extract/generate/verify),
`test/verdict_corpus/` (14 fixtures, 5,290 cases), `test/unit/test_verdict_corpus.py` (two-tier
replay). Suite 2,189 tests / 8.7s / OK. Double regeneration byte-identical. Ruff clean.

It also found two things I got wrong in the spec: a literal backtick-parity parsing rule breaks
on a real command containing an unpaired backtick, and the log counts drift upward continuously
because `logs/toolguard-2026-08-04.md` is being appended to **by this very session**. Both are
correct findings.

### The gate: 5 seeded mutations, run by me, not by the builder

The agent had reported success on the strength of one seeded mutation. One is not a battery.

| mutation | expected | first run | after re-aiming |
|---|---|---|---|
| consolidation ignores a denied sub-command | caught | — | **CAUGHT** |
| undecidable floor collapsed to allow (both sites) | caught | — | **CAUGHT** |
| parse-failure ASK floor disabled (TOO-19 fail-open restored) | caught | CAUGHT | CAUGHT |
| enrichment dropped inside `decide()` | caught | skipped | **CAUGHT** |
| enrichment dropped at the hook OUTPUT seam | *gap* | MISSED | MISSED (confirmed) |

### The interesting part: my first two mutations proved nothing, and why

First run reported `strictness_swap` and `undecidable_floor_off` as MISSED, and I briefly
concluded the corpus was weak. Wrong. Both mutations **produced no behaviour change at all**:

- `_DECISION_STRICTNESS` is *deliberately* not the ordering `_combine_strictest` uses — that
  function filters lists and picks by priority, with a 12-line comment citing TOO-19's
  reuse-vs-coupling reasoning for keeping them separate.
- The undecidable floor is applied at **two sites**: `_apply_undecidable_floor` (compound.py:325)
  and a direct `_UNDECIDABLE_FLOOR_DECISION` lookup for `UndecidableSegment` (compound.py:896),
  which the comment says takes the fallback "DIRECTLY, not via `_apply_undecidable_floor`".

Mutating one site of a duplicated concept changes nothing observable. Re-aimed at
`if denied:` and at the shared table, both were caught immediately.

**Finding for P3, recorded now while it is concrete:** the same decision concept is expressed in
more than one place in `compound.py`, with the duplication documented and defended rather than
accidental. That does not make it wrong — the two cases genuinely differ (clamp an
already-decided leaf vs supply a decision where no rule matched) — but it is a concrete instance
of the pattern TOO-45 exists to examine, found by the safety gate before any refactoring started.
Carry it into the as-is picture rather than assuming a verdict either way.

### Remaining gap: the output seam

Disabling the `additionalContext` write in `create_hook_output` removes the field from the hook's
JSON entirely and the corpus does not notice, because it stops at `decide()`.

This is not a generic hole. **R1 is specifically about that seam**, and the ticket's defect #1 is
that `--eval` and the sandbox once "silently under-reported a live output field" — same seam,
same failure, already shipped once. Sent back to `feature-coder` to add ~25-40 end-to-end cases
through `Sandbox.run_hook`, goldening the full response JSON including key presence.

Explicit design constraint given: do NOT close it by calling `create_hook_output` directly with
`Decision` fields — that re-implements hook.py's derivation inside the test and would still miss a
mutation in the derivation itself.

**CP1 is not passed until that mutation is caught.** Status: in progress.

---

## P.4 — file-tool guardrails applied, 2026-08-04. DONE.

`<TEMPORARY>` deny fence added to `.claude/toolguard_hook.toml`. Verified against the live hook:
6 intended denies land (`logs/**`, `.env`, `.claude.env`, project + user `toolguard_hook.toml`,
`settings.json`, `settings.local.json`, `~/.toolguard/rules/**`), and 4 normal-work paths still
allow — including **`Read` on `logs/**`**, which the corpus builder depends on and which a
careless pattern would have taken out.

Now self-locked: `Edit(./.claude/toolguard_hook.toml)` is denied, so removal at ticket close is
Arnon's action via the IDE. Intended.

`tmp/git.rules.toml` deleted — the stale copy that made the harness drift possible. Only
references remaining are prose in these notes describing the drift.

Telegram notification path verified end-to-end before CP1 rather than at it (chat_id recovered
from this session's earlier transcript). Same discipline as the rules harness: an unexercised
channel is not a channel.

---

## P.3 — as-is picture, structural first cut, 2026-08-04

Method note: fan-in below is grep-based. Checked first whether that is a valid proxy — 172
absolute `from toolguard...` imports against **3** relative ones, so it is ~98% sound. The 3
relatives are a known small error bar, not an unknown one. (Lesson 2 applied deliberately: the
proxy was validated before being trusted, not after being contradicted.)

### Zone sizes

| zone | modules | LOC |
|---|---:|---:|
| `toolguard/` (core) | 28 | 14,042 |
| `toolguard/tools/` | **31** | **13,346** |
| `toolguard/parser/` | 5 | 8,875 |
| `toolguard/scripts/` | 2 | 1,264 |
| `toolguard/testing/` | 2 | 730 |

**The operator tooling is now the same size as the engine it wraps** — 31 modules to the core's
28, 13.3k LOC to 14.0k. The ticket called it "a second product grafted onto the first". The
measurement says the graft is as large as the host, and it has grown since the ticket was
written (30 modules then, 31 now).

### Fan-in, and the contradiction that matters

| module | fan-in |
|---|---:|
| `config` | **28** of 67 others (42%) |
| `constants` | 10 |
| `rule_entry` | 9 |
| `rule_sort` | 6 |
| `issues` | 3 |
| `permissions` / `compound` / `resolve` | **2 each** |
| `hook` / `log_writer` | 1 each |

`config` is up from the ticket's 25 to 28 — the hub kept growing during TOO-19.

**The finding is the disagreement.** `permissions`, `compound` and `resolve` have fan-in of
**2**. By the import graph they are leaves. By co-change they are the most entangled files in the
repo — `compound.py` has *never* been changed without also changing both `config.py` and
`permissions.py` (100% coupling, 6 observations each).

Structure says "well-isolated modules". History says "one module in three files". Both
measurements are correct; they are measuring different things, and **the gap between them is
precisely the diagnosis**: these modules are not reached directly, they are reached *through*
`config`, so the import graph cannot see the coupling that every change actually pays for.

Consequence for the ideal picture: a fan-in metric would have scored this codebase as fine, and
did — the ticket already warns that dead code 0 / LCOM 100 / CBO 95 say nothing is wrong. This is
a second, independent instance of the same trap. **Do not let R6's success be judged by import
counts.** The what-vs-how test and co-change are the instruments that can see this; fan-in is not.

Next in P3: the ideal picture at the same altitude, then the delta.

---

## P.1 — CLOSED. Corpus passes the full gate, 2026-08-04

Output-seam gap closed: 30 end-to-end cases replayed through the real hook binary via
`Sandbox.run_hook`, goldening the **full hook JSON response** including key presence — not
`create_hook_output` called with `Decision` fields, which would have re-implemented hook.py's own
derivation inside the test and left a mutation in that derivation still invisible.

**Independent re-run of the battery (mine, not the builder's):**

| seeded change | result |
|---|---|
| denied sub-command no longer wins consolidation | CAUGHT |
| undecidable floor collapsed to allow, both sites | CAUGHT |
| parse-failure ASK floor disabled | CAUGHT |
| enrichment dropped inside `decide()` | CAUGHT |
| enrichment dropped at the hook output seam | **CAUGHT** (was the blind spot) |

5/5. All production files restored, sha256-verified.

**Independent verification:** 5,389 in-process + 30 e2e cases; `corpus_build.py --verify` reports
no differences against committed goldens; 2,192 tests OK; ruff check and format clean.

**The builder found two latent fixture bugs of its own** while adding e2e coverage: `hard_deny`
and `pattern_forms` never declared `governed_tools` (which defaults to `('Bash',)`, so their
Read/Write cases were silently testing tool-governance rather than the rule under test), and
`hard_deny`'s relative `Read(**/.env)` patterns never matched anything because relative patterns
anchor to the sandbox's ephemeral project root. Both had silently affected 5 in-process goldens
since first delivery. So the goldens my first gate ran against were partly wrong — the mutations
were still caught, so the result stands, but it is a reminder that a fixture can be green and
meaningless at the same time. Same shape as lesson 1.

**Note on where P4's config edit actually landed:** `.claude` in this repo is a symlink to
`/home/arnon/projects/dot_files/claude/projects/toolguard/.claude`. The deny fence is therefore
version-controlled in the **dot_files** repo, not toolguard, and currently shows there as an
uncommitted modification. Relevant for revert-at-close.

## P.2 — delegated, 2026-08-04

`tools/architecture_fitness.py` sent to `feature-coder`: `--layers` (completeness + direction,
AST-based), `--predicates --json` (component diagnostics, never bare booleans),
`--metrics` (co-change per TICKET not per commit), `--guard` (deterministic safety checks).

Spec carries the P.3 finding as a hard framing requirement: fan-in must be printed adjacent to
co-change, never alone, with a standing caveat in the output that it cannot see coupling routed
through `config` and must not be read as evidence R6 succeeded.

## CP1 status

- [x] corpus mutation battery — 5/5, independently run
- [x] guardrails as rules (git + file tools), verified against the live hook
- [x] decision log, lessons note, resume discipline
- [ ] `architecture_fitness.py` first full report — in progress
- [ ] as-is / ideal / delta picture — structural half done, ideal + delta outstanding
- [ ] proposed final step order — depends on the delta

**Not at CP1 yet.**

---

## P.2 — CLOSED. `architecture_fitness.py` delivered and run, 2026-08-04

~1,180 lines, stdlib only, 74 tests on synthetic fixtures plus real-tree smoke tests. Suite
2,266 OK. Ruff and doc links clean. `--guard` passes and dogfoods on its own diff.

### Three corrections to numbers I reported

All three of mine came from grep. All three are superseded by AST.

1. **R3 is 5 sites, not 3.** I told Arnon "3 real sites, not 6 — R3 is roughly half the size
   budgeted." The AST scan finds **5**: the two I missed are `resolve.py:692` and `:699`, which
   operate on a variable named `reason_body`, so a `reason\.`-shaped grep cannot see them. This
   is **lesson 2 committed again, after writing it down** — measure by mechanism, not by expected
   shape. R3 is 5 of the ticket's 6, i.e. barely smaller, not half.
2. **Max fan-in is 25, not 28.** My grep alternation over-counted. The ticket's original 25 was
   right and my "it grew during TOO-19" claim was an artifact.
3. **Longest dependency chain is 12 hops, not 13** — and it routes
   `tools.maintenance -> ... -> hook=tools.decision -> auto_migrate -> scripts.migrate_permissions
   -> config_divergence -> config -> ... -> issues`, confirming the entry-point-and-migration-script
   detour the ticket described.

### Live predicate state

| predicate | state | detail |
|---|---|---|
| R1 | FAIL | **7** verdict-ish types (ticket said 4+1): `ResolvedDecision`, `BashResolution`, `FileResolution`, `Decision`, `LedgerDecision`, `SingleDecision`, `ProjectRootResolution`. **5** `__iter__` shims, **all with 0 callers** |
| R2 | FAIL | 3 parallel-array pairs on `ToolPatternLayer`: `allow/allow_entries`, `deny/deny_entries`, `ask/ask_entries` |
| R3 | FAIL | 5 sites (above) |
| R5 | FAIL | 7 non-leaf runtime/scripts modules; 2 cycles (`parser.multiline <-> command_extractor`, `tools.decision <-> hook`) |
| R6 | FAIL | **exactly ONE violation**: `tools.takeover_audit:87` imports private `_strip_tool_wrapper` from `config` |
| enrichment footprint | 14 files | matches |

`--layers`: **completeness passes** (every module maps to exactly one layer — the unmappable-
sandbox hole is closed). 3 direction violations: `auto_migrate -> scripts.migrate_permissions`
[local import], `config_divergence -> error_log`, `hook -> tools.decision` [local import].

Note **two of the three layer violations are function-local imports** — hidden inside function
bodies as circular-import escapes. Consistent with the theme: the worst coupling is the least
visible.

Plan inaccuracy found: `config_divergence` does NOT import `scripts.migrate_permissions`; only
`auto_migrate` does.

### R6's predicate is measuring the wrong thing — now proven

The ticket calls R6 "the largest single piece of work in the programme", "plausibly larger than
R0+R3+R5+R1+R2 combined". Its predicate evaluates to **one import in one file**.

This is exactly the failure I flagged when C2 landed: the predicate asks *what is imported*, and
the tooling boundary problem is not about imports. A one-line fix would satisfy R6 and change
nothing. **The predicate must be rewritten before R6 is scheduled**, and this is a live instance
of the plan's own warning that a satisfied predicate with an unconvinced judge means the
predicate was wrong.

### The co-change metric is degenerate at this sample size — my design error

Reported: max co-change partners **69** (config.py), **71** 100%-coupled pairs, p90 **45**
production files per logical change, 40% single-zone.

Against the ticket's baseline of 17 partners / 3 pairs / p90 11 (per-commit). The difference is
not drift — it is the grouping. The ticket and my spec both mandated grouping **per ticket** to
remove the commit-splitting gaming vector. On this repo that yields **10 production-touching
logical changes**, each averaging tens of files, so nearly everything co-changes with nearly
everything and "100% coupled" stops discriminating.

**The anti-gaming prescription destroyed the signal.** Both were my call — in the plan and in the
spec — so this is a design error, not a tool bug.

Fix to propose at CP1: report **both** views. Per-commit carries the signal (N=41, discriminating);
per-ticket is the anti-gaming cross-check. Where they disagree, that disagreement is itself the
diagnostic. Do not use per-ticket pair-coupling as evidence at N=10.

---

## CP1 REACHED, 2026-08-04

All six evidence items complete. Suite **2,279 tests OK**. `--guard` PASS with 12/12 canaries.
Ruff and doc links clean.

| CP1 evidence | outcome |
|---|---|
| corpus mutation battery | 5/5 caught, independently re-run after the seam fix |
| guardrails as rules | git + file-tool fences, verified live; canary check now detects their loss |
| decision log / lessons / resume discipline | in place, 11 lessons recorded |
| `architecture_fitness.py` first full report | 4 modes, live numbers on the real tree |
| as-is / ideal / delta | three artifacts, six claims tested |
| proposed step order | R3 -> D4 -> D1 -> R1 -> R5 -> R2, R6 split out |

### Canary detection verified end-to-end, and how

The obvious test — delete a deny rule, watch the canary fire — is **impossible by design**: the
TOO-45 guards deny edits to both permission files, so I am locked out of the thing I would need
to break. The lock is correct and I would not weaken it to test it.

Tested from the other side instead: flipped one canary *expectation* to disagree with the live
config. Result: exit 1, `canary mismatch: Bash 'git clean -fdx' expected 'allow', got 'deny'`,
file restored sha256-clean. Same evidence — expectation and reality disagree and the tool says
so — reached without touching a permission file.

Worth keeping as a pattern: when a guard prevents you from testing it directly, invert the test
rather than weakening the guard.

### Corrections I made to my own numbers during P1-P3

All from grep, all superseded by AST or by the tool:

- R3 is **5** sites, not the 3 I reported (missed two using a `reason_body` variable)
- max fan-in is **25**, not 28 — the ticket's original number was right
- longest chain is **12** hops, not 13
- "17,167 logged decisions" was **9,896** — the rest were Discovery entries

### Design errors of mine found by building the instruments

- **Co-change per-ticket is degenerate at this sample size.** N=10 production-touching logical
  changes, p90 45 files, 71 "100%-coupled" pairs. The anti-gaming prescription (mine, in both
  plan and spec) destroyed the signal. Fix: report per-commit AND per-ticket; disagreement is
  itself diagnostic.
- **R6's predicate did not describe R6's problem.** 1 violation under the old predicate, **21 of
  33 modules** under a correct one.

### Open for the CP1 review

1. Approve the step order and the R6 split.
2. Approve the corrected R6 predicate.
3. Approve reporting co-change both ways.
4. `ProjectRootResolution` in R1's list of 7 is probably a detector false positive — needs a
   judgement call, not a code change.
5. Nothing is committed. The tree carries 5 new untracked paths plus `CLAUDE.md`/`uv.lock`.

---

## R3 begins, 2026-08-04 — and the predicate under-reports

### The diagnosis sharpened on contact

R3 is **not** "stop parsing prose". It is **stop discarding structured data you already hold**.
Every one of the sites recovers a value that was in hand at the point of decision:

- `config.py:1707` writes provenance INTO the reason (`_append_provenance`); `resolve.py:692`
  strips it back OUT (`rindex("  [")`) while `ResolvedDecision.provenance` sits there as a field.
- `_resolve_permission_detailed_unclamped` HAS `matched_pattern` — it is what provenance and the
  winning entry are looked up BY — then discards it into prose that four sites parse back out.

Precedent found in the code: `fallback_warning`'s own docstring says it replaced a
substring-marker approach for this exact reason. R3 finishes a job someone already started once.

### A SIXTH site, invisible to the predicate

`hook.py:395 _parse_compound_match_details(reason)` regex-matches the compound reason and
`rsplit(" -> ", 1)`s out `(sub_command, matched_rule)` pairs — while `BashResolution.sub_matches`
already holds them as `SubMatch` objects.

**The fitness tool's R3 predicate cannot see it.** The detector looks for
`reason.split`/`startswith`/`endswith`; this is a regex parse inside a dedicated function. So
`--predicates` would have reported R3 SATISFIED with this site intact.

This is the plan's own warning arriving as fact: a predicate is a scoping device, not a
definition. Two lessons compound here — the detector is itself a proxy measurement (lesson 2),
and a satisfied predicate is not a finished step (the judge-decides design).

**Action:** the R3 detector needs widening to catch regex/`re.match` parses of a reason variable.
Not done yet; recorded so it is not lost. Do NOT let `--predicates` reporting R3 clean be taken
as R3 being done.

### It also changed the fix for the better

Original plan: add `matched_rule` as another parameter to `_log_allowed_command`. Better: consume
`result.sub_matches`, which **deletes** a parse instead of adding to a parameter spread that is
already eleven wide. Same predicate satisfied, opposite direction of travel.

### Done before delegating (3 edits, suite green at 2279)

1. `ResolvedDecision.matched_rule` field added, reasoning in the docstring.
2. Populated in `config.py` from `matched_pattern` already in hand.
3. `matched_rule` added to `BashResolution` and `FileResolution`.

Conversion of the six sites delegated to `feature-coder` with the analysis above, the hard
verdict-equivalence invariant, and an explicit instruction NOT to reach casually for
`TOOLGUARD_CORPUS_ACCEPT_PROSE=1` — R3 should be behaviour-preserving including the prose, so a
prose change is a signal that a rendering path was altered.

`resolve.py:563` (the "Command" -> "Path" no-match reword) held out of scope: it is a rendering
concern, not data recovery, and needs its own decision.

### Measurement in flight

Threading ONE structured field through today's types: ~6 production files. The agent will report
the honest final count. After R1 the same exercise should cost 2-3, and that delta is R1's
justification in numbers.

---

## R3 conversion complete, 2026-08-04

`--predicates` R3: **6 sites -> 1**, and the one remaining is the ticket-sanctioned out-of-scope
`resolve:588` "Command" -> "Path" reword (rendering, not data recovery).

**Invariants, verified by me not the builder:** suite 2,279 OK; corpus `--verify` **no
differences at all** — verdicts *and* prose unchanged, with `TOOLGUARD_CORPUS_ACCEPT_PROSE`
never used; `--guard` PASS 12/12; ruff clean.

Prose being unchanged is the strong result. R3 moved where values come FROM without altering
what anything says.

### The R1 measurement

**4 production files, +264/-99 lines** to thread one structured field end-to-end
(`config_types`, `config`, `resolve`, `hook`), plus 2 test files. Lower than my ~6 estimate
because `sub_matches` already carried part of it. Record this: after R1 the same exercise should
cost 2 files, and that delta is R1's justification in numbers rather than assertion.

### I was wrong about `_parse_compound_match_details`

I specified deleting it because `BashResolution.sub_matches` "already holds" the same pairs.
**It does not.** For an ask-floor leaf (foreign inline code / heredoc), `SubMatch` records the
resolution of a *truncated outer-command stub*, which can genuinely match a real allow rule —
while `compound.py` treats that leaf as an escape-hatch allow regardless. That classification is
computed inside `compound.py` and never crosses back through the `resolve_one` 3-tuple.

The agent found this by **running the tests**, not by reasoning from my spec, and kept the
function with a documented reason rather than expanding scope. Correct call on both counts.

Lesson 7 restated from the other side: I assumed two representations were equivalent because
they *looked* equivalent. Only execution distinguished them.

### THE PATTERN: narrow tuple contracts between engine stages

Three instances now, each individually judged "disproportionate to widen":

| contract | blocked | when |
|---|---|---|
| `resolve_one` 3-tuple | `fallback_warning` as structured data | TOO-19, documented in its docstring |
| `resolve_one` 3-tuple | the ask-floor escape-hatch classification | found today |
| `_check_file_path_hard_deny` 3-tuple | the hard-deny matched pattern | found today |

Same shape as the eleven-parameter signature: **a missing type, worked around locally three
times.** Each local judgement was defensible; the aggregate is the defect.

**This sharpens R1.** R1 is not "merge some dataclasses" — it is *replace the positional tuple
contracts between engine stages with the verdict type*. The `__iter__` shims exist to keep those
tuples working, so deleting them is the visible surface of a change whose real content is the
contracts underneath. Carry this into R1's interface draft.

### Accepted behaviour change, and a corpus gap it reveals

File-path hard-deny now logs the FULL reason in "Violated Rules"
(`"Path matches hard_deny pattern: X (cannot be overridden)"`) where it previously logged the
colon-split remainder (`"X (cannot be overridden)"`). More verbose; nothing lost, nothing
fabricated. **Accepted.**

Cause: `_check_file_path_hard_deny` computes the matched pattern internally but returns a
3-tuple that does not include it (instance 3 above), so `matched_rule=None` and the logger falls
through to the full reason.

**The corpus could not see this.** It goldens the hook's JSON response, not log lines — but
TOO-19 treated the audit log as a product surface in its own right (finding M1 was a fabricated
rule *in the log*). **Candidate corpus extension: golden the log output for a subset of e2e
cases.** Not done; recorded so the gap is known rather than discovered later.

### Asymmetry to close later

Bash hard-deny carries its pattern (via `check_hard_deny`'s pattern-as-its-own-element
convention, TOO-19 m3); file-path hard-deny does not. Same concept, two conventions. Belongs
with R1 or R4.

---

## CORRECTION: R3 is at 2 sites, not 1. And the fix to the tooling caught it.

I recorded above that R3 went "6 sites -> 1". **Wrong. It is 6 -> 2.**

Cause: I told the fitness-tool agent that `_parse_compound_match_details` had been removed. It had
not — the R3 agent deliberately kept it, with a documented reason, and said so in its report. I
carried a stale claim forward without checking it against the tree. The widened detector then
caught it immediately.

Worth noting what that means: **the widened R3 detector earned its keep within minutes of
existing, by catching my error rather than the code's.** It also validates the widening — the old
detector was blind to `_COMPOUND_MATCH_PATTERN.match(reason)` and would have agreed with me.

This is a *measurement* error, not a decision error — consistent with every other thing I have got
wrong on this ticket. Measurements rot and need re-taking; decisions have held.

### Tooling fixes landed (all three)

1. **Generated code excluded**, by banner scan (`generated from`, `do not edit`, `@generated`,
   `autogenerated`) rather than a hardcoded filename, and **named explicitly** in the output under
   `generated_files_excluded`. One file found: `parser/bash_parser.py`. `--layers` deliberately
   still sees it, since the import graph is real regardless of provenance.
2. **`toolguard/parser/` excluded from R1's scope**, with the five excluded modules named in the
   output. **R1's shim count: 5 -> 2** (`BashResolution`, `FileResolution`). The `TreeNode` shim
   that could only have been "fixed" by hand-editing generated code is gone from the count.
3. **R3 detector widened** to catch argument-position regex parsing
   (`PATTERN.match(reason)`), plus `rsplit`/`partition`/`rpartition`/`rindex`/`index`/`find`, and
   a regression test pinning the reassigned-local case (`reason_body = resolved.reason`).

Suite **2,300 OK** (+21 new tests, 2 existing extended, nothing weakened). `--guard` PASS 12/12.
Ruff and doc links clean.

### R3 goes to the judges with a FALSE predicate, deliberately

Two remaining sites, both documented exceptions rather than oversights:

- `resolve:588` — the "Command" -> "Path" no-match reword. A *rendering* concern, held out of
  scope by decision.
- `hook:522` — `_parse_compound_match_details`. Kept because `sub_matches` genuinely does not
  carry the ask-floor escape-hatch classification; removing the parse broke two TOO-19 regression
  tests. Widening the `resolve_one` 3-tuple to fix it properly is R1's job.

This is the exact case the plan anticipated: *unsatisfied predicate + convinced judge = the
predicate was wrong; record it and move on.* First real test of judge-over-predicate, and it
arrived on its own rather than being manufactured.

Blinded reviewer and architect judge both running. Canary (fresh naive agent, `auditNote` key
end-to-end, working in a scratch copy) also running.

---

## CANARY RESULT after R3: 7 production files. The canary did NOT move.

Fresh naive agent, no knowledge of the plan, adding an `auditNote` enrichment key end-to-end
(TOML parse -> validation -> verdict -> audit log), working in a scratch copy.

**7 production files, +338/-92 lines**: `rule_entry`, `config_types`, `config`, `resolve`,
`compound`, `hook`, `log_writer`.

Ticket baseline was ~9 for `additionalContext`. **This is not an improvement, and I will not
present it as one.** `auditNote` is deliberately *simpler* than `additionalContext` — it never
reaches the JSON response, so a whole path is skipped. A simpler feature costing 7 files against
a harder one costing 9 is flat at best.

**This is the expected result and it is a finding, not a failure.** R3 was never aimed at
enrichment cost; the plan says so explicitly, and says a flat canary at a boundary drives the
next iteration rather than being shrugged off. It is now measured rather than predicted.

### The qualitative half is worth more than the number

The canary, with no knowledge of any of this ticket's analysis, independently reported:

> `additionalContext` is not a single feature to clone — it's a value threaded **positionally
> through five separate tuple/dataclass shapes across three modules**, each with its own
> backward-compatibility constraint.

That is the tuple-contract diagnosis, arrived at from scratch by an agent that had never seen it.
Independent corroboration, not agreement with a leading question.

### NEW FINDING: the test suite is holding the bad contract in place

The canary had to keep `_resolve_leaf` and `resolve_compound_permission` **externally unchanged**,
padding and dropping the new field internally, because **~20 existing tests call them directly
with 3-tuple stubs**. It first widened `_resolve_leaf`, broke ~15 test call sites, and reverted.

So the narrow tuple contracts are not merely inherited — they are **actively pinned by the tests**.
Every test that stubs a 3-tuple is a vote against widening it.

Consequences for R1, which I had not accounted for:

1. **R1's test cost will be substantial and is not optional.** Those tests must move to the verdict
   type or R1 cannot land. That is legitimate test change (the code they pin is changing), not
   test weakening — but the distinction has to be argued case by case and recorded, per invariant 1.
2. It explains why widening was judged "disproportionate" three separate times. Each time the true
   cost included ~20 test rewrites, so each local judgement was *correct in isolation*. The defect
   is that nobody ever paid it once.
3. **The verdict corpus is what makes paying it safe now** — behaviour is pinned independently of
   those unit tests, so they can be rewritten without losing the guarantee they were providing.
   This is the corpus's first real payoff beyond gating.

### Measurement hygiene, unprompted

The canary flagged that `git diff --stat` against HEAD would have **overstated its own change by
~2x**, because the working tree already carried uncommitted R3 work in the same files. It diffed
against the live source tree instead.

It caught a baseline trap that I set for it and did not warn it about. Same theme as every
measurement error on this ticket: the number is only as good as what it is measured against.

---

# R3 CLOSED — and this is CP2. 2026-08-04

Final: **8 files, +394/-150**. Suite 2,279 -> **2,321** (+42 tests). Corpus: no differences, no
prose acceptance, ever. `--guard` PASS 12/12. Doc links OK. Ruff clean.

Closure basis: architect judge said close; blinded reviewer gave a conditional close on four named
fixes; all four done and **verified by mutation, not by assertion**.

## What R3 actually bought

| | |
|---|---|
| prose-parse sites | 6 -> 2, both documented exceptions |
| enrichment footprint | 14 files (unchanged) |
| canary | **7 files — did not move** |
| narration removed | ~90 net docstring lines |

**Defects found and fixed that would otherwise have shipped:**

1. `matched_rule` naming an **allow** rule as the decider of a deny verdict (found independently
   by both judges).
2. A new field whose **wrong value passed all 2,300 tests** — `assertIn`/`assertIsNotNone` pin
   absence, not correctness.
3. The **hook wiring pinned by nothing**: swapping `matched_rule` and `provenance` at the call
   site corrupts every audit entry and 2,314 tests stayed green.
4. A silent **audit-log provenance regression** — data loss in a product surface.
5. A docstring stating a **false invariant** ("can never diverge").
6. Two **false documentation claims**, one in `log_harvest.py`, the module whose job is parsing
   that log.
7. A test **weakened into a tautology**.

## The honest negatives

- **The canary did not move.** 7 files for a simpler feature than the 9-file baseline. R3 was
  never aimed at enrichment, but the acceptance test is flat and that is the recorded result.
- **Two reopenings, and both were the same failure of mine.** Round 1: the value was not pinned.
  Round 2: the wiring was not pinned. Identical shape, one layer up, immediately after being shown
  the first. **I fixed the instance and not the class, twice**, with the technique already in hand.
- The original diff was **71% prose**, which I wrote without noticing.
- Cost is high relative to architectural movement: R3 moved one boundary and cost roughly 2M
  subagent tokens across six runs.

## Method findings — the part worth keeping

**1. Two judges asking DIFFERENT QUESTIONS is the highest-value component of the loop.** Every
significant finding came from the split, and neither lens could see the other's:

- architect = *what does this contain?* -> found the wrong value in the field
- blinded = *what would notice if it were wrong?* -> found that nothing would

The split happened by accident. **Make it deliberate**: same artifact, assigned questions. Both
judges independently recommended this.

**2. Mutation beat review twice, and beat me three times.** The wrong-value gap, the wiring gap,
and my own stale claim about a removed function were all found by something that ran. Review found
none of the three.

**3. Predicates were wrong in three different directions on one ticket** — R6 measuring the wrong
thing, R3 under-reporting, R1 over-reporting. None was visible without going to look. They scope
work; they are not evidence.

**4. Judges disagreed on a FACT and the blinded one was right.** The architect said `hook:522` was
blocked on R1; `compound.py:722` already builds the data as a list and joins it for `hook.py` to
split back apart in the same process. Neither had it fully — building the list itself parses leaf
reasons, so converting moves the parse rather than removing it. Verified directly.

## Instance five, as a rate not a count

R3's own follow-up introduced
`single_provenance = provenance if single_matched_rule == matched_rule else None` — a *derived*
classification inferring "the guard fired" by comparing output to input, because no structured
flag exists to receive. **One step, one new compensation.** There are now three downstream
compensations for the missing escape-hatch flag, and **none of them lives in `Configuration`**, so
D1 removes none of them.

## Open decisions for Arnon at CP2

1. **Continue the loop, adjust it, or stop?** Data above.
2. **Ordering: widen `resolve_one`'s contract BEFORE moving orchestration out of `Configuration`?**
   Argued for by: three compensations none of which D1 touches; a countable bounded cost
   (**exactly 18** test closures, verified); and the decisive one — only the contract step has a
   falsifiable acceptance test today. Against: D1 is higher-leverage on co-change and gates R6.
3. **Audit-log format changed** (new `Provenance` field, `Matched Rule` content narrowed). Needs
   the pre-push maintenance-skill question and release notes. I absorbed this as part of a
   regression fix instead of raising it as a decision — that was wrong.
4. **Nothing is committed.** 8 production files plus tests and tooling.

---

# D4 DONE and PROVEN, 2026-08-04. Commit `d4123f4`.

R3 committed as `d5bdab3` first, as a restore point.

## Arnon's CP2 answers

1. **Continue.** Do more of what works; adjust dynamically without asking; stop only if
   ineffective.
2. **Ordering left to me** — but with an argument I had under-weighted, and it changed my
   decision. I was choosing by *which step is easier to judge*; he argued by *which is more
   likely to surface what we do not know*. R3 already worked the `resolve_one` territory, so
   widening that contract deepens partly-mapped ground, while `Configuration` is unexplored and is
   where the co-change evidence points. **Exploration value beats judgeability at this stage.**
   Going with D1. Contract-widening remains available and is not lost.
3. Newly-discovered issues (e.g. the audit-log format change) get **logged as additional steps
   after the main refactor**, not folded in.

## D4 executed with a prediction recorded first

The architect judge warned D4's real risk was **proving nothing** — closing green with every
diagnostic flat. So, before touching code:

- **Predicted**: 45 undecidable-fixture cases, 27 containing `<(` process substitution, should
  reach `compound.py:895`.
- **Verified the prediction by mutation**: broke that site, corpus FAILED. So the corpus genuinely
  covers it and D4 would be meaningfully verified rather than vacuous.

Only then made the change: the direct `_UNDECIDABLE_FLOOR_DECISION.get(...)` lookup became
`_apply_undecidable_floor("allow", undecidable_fallback)`.

## The proof, which is the most satisfying result of the ticket so far

At CP1, mutating `_apply_undecidable_floor`'s comparison was **MISSED** — it changed no behaviour,
because the second implementation carried the path the tests exercised. That miss is what
*revealed* the duplication in the first place.

After D4, **the identical mutation is CAUGHT.**

That is a direct, falsifiable proof that the unification is real and not cosmetic. It also
demonstrates the general technique: *a duplicated concept makes each copy unfalsifiable, so
mutating one site and seeing nothing is itself the signal* — and the same mutation flipping from
MISSED to CAUGHT is the proof the duplication is gone.

Corpus: no differences. Suite 2,321 OK. Ruff clean. Floor sites: 2 -> 1.

## A dynamic adjustment, made without asking (per Arnon's authorisation)

**Deferring D4's judge round and batching it with D1's.** Reasoning: D4 is a five-line change
whose correctness is established by the strongest instrument available, and the judges' value on
R3 came from areas mutation cannot reach — unpinned wiring, false documentation, direction. On a
five-line surface with a decisive mutation proof, a full two-judge round (~$10, ~30 min) buys
little. Scaling review effort to step surface, not running it ritually.

Recording this as a decision rather than a silent omission, so it can be judged later. If D1's
judges find anything that D4 introduced, this adjustment was wrong.

## Operational hazard hit and fixed

The temp filesystem filled to **0MB** mid-session and every Bash command silently returned nothing
(`ENOSPC` on stdout). Cause: each subagent I told to "work on a copy" ran `cp -r` of the whole
repo **including `.git`**, and the copies accumulated.

Fixed by deleting finished agents' copies. **Standing change: copies exclude `.git`, and each is
removed when its agent finishes.** Worth noting the failure mode — commands did not error, they
returned empty, which reads like "no matches found" rather than "the disk is full".

# D1a — predictions recorded BEFORE the result (2026-08-05, agent in flight)

Recorded ahead of the implementing agent finishing, so they can be scored honestly rather than rationalised afterwards. The discipline is the one that made D4 mean something: state the prediction, then verify by mutation.

## Design decision made without asking, and its justification

The plan said D1a keeps `Configuration.resolve_permission_detailed` as a **thin delegating shim** so only ~3 tests break instead of 47. **I dropped the shim and did the full move.** Reason, measured now rather than assumed: the only production callers are **three lines, all in `toolguard/resolve.py`**, which already sits in the `engine` pyscn layer. A shim on `Configuration` would have meant `config` importing `engine` — an upward dependency and a strict-mode layer violation — to save edits in tests that are mechanical. The staging existed to reduce risk; here it *created* the only architectural cost in the step.

The extracted module imports **only `config_types`**, never `toolguard.config`. Everything it needs arrives through the object passed in. That is what makes the port narrow enough to state as a claim, and it removes any circular-import pressure that would have invited a local import.

## The finding that changed the design mid-flight

`test/unit/test_hook.py` and `test/unit/test_configuration.py` both define fake configurations that **implement `resolve_permission_detailed` by hand** — their own comments say "API-sync with Configuration.resolve_permission_detailed". That is a hand-maintained reimplementation of the cascade living in the test suite, and it is exactly the kind of duplication that makes each copy unfalsifiable. The current method is a *narrow port* the fakes exploit; removing it forces the fakes to supply queries instead of answers, and the real engine then runs against them.

So D1a is not only an extraction. It deletes a second implementation of the cascade that nobody had counted.

## Predictions

1. **The fake's no-match reason string does not match the real one.** Fake: `"Command does not match any allow patterns; no_match_fallback=ask"`. Real: `"Command does not match any allow patterns; awaiting a decision (no_match_fallback=ask)"`. If any `test_hook.py` assertion has to change, the test was asserting on text the real system never emits — a test that could not have caught a regression in the string it was checking.
2. **The corpus reports no differences.** All 6,401 cases. If it does not, the step failed outright.
3. **The suite count moves.** Not because tests were deleted, but I do not expect exactly 2,321 to survive an interface change of this width. Any movement must be explained, not absorbed.
4. **The narrow-surface claim will need execution to confirm.** I asserted six members. I have been wrong about this class of count three times on this ticket, always when the claim came from reading rather than from running. Treat "six" as unverified until something runs.
5. **The canary count moves.** It measured 7 files after R3 and did not move after D4. D1a is the step that should move it. If it does not, the canaries are measuring the wrong thing and that is a finding about the instrument.

# D1a — result, and the architect judge's findings (2026-08-05)

Acceptance re-run by me, not taken from the implementing agent's report: suite **2,321 OK** (baseline exactly), corpus **6,401 in-process + 61 e2e, no differences**, `--guard` **PASS 12/12**, ruff clean. `config.py` 2,913 -> 2,594. New module `toolguard/permission_resolution.py` in the `engine` layer, importing only `config_types` — verified at link time: importing it in a virgin interpreter leaves `toolguard.config` absent from `sys.modules`.

## Predictions, scored

| # | prediction | outcome |
|---|---|---|
| 1 | a fake assertion must change (divergent reason string) | **LOST, and the miss is the finding.** No assertion ever pinned the fake's string. It was dead prose in a test double — a copy of the cascade that nothing checked. |
| 2 | corpus reports no differences | **WON.** The one that had to hold. |
| 3 | the suite count moves | **LOST.** Exactly 2,321, no test deleted or weakened. My intuition about the churn cost of an interface move of this width was wrong when the call sites are mechanical. |
| 4 | the six-member claim needs execution to confirm | **WON, and correctly left open.** See below. |
| 5 | the canary moves | **open, and now predicted to fail** — see change-cost below. |

## P4 closed by execution, and it came back narrower than claimed

The judge instrumented `Configuration.__getattribute__` with the calling frame's module and replayed the whole 6,401-case corpus. The engine module's own frames touched exactly six members and no seventh: `permission_levels_with_provenance` (9070), `parse_failures` (9070), `has_any_rules` (5088), `resolved_no_match_fallback` (5034), `provenance_for_pattern` (4023), `entry_for_pattern` (3982).

**But it is really a four-member surface.** `provenance_for_pattern` and `entry_for_pattern` are staticmethods — `config.provenance_for_pattern is Configuration.provenance_for_pattern` is `True` — taking `layers` as a parameter, i.e. data the engine already holds and hands straight back. They carry no configuration state. They are pure functions over `ToolPatternLayer`, reached through the config object by convention only, and their real home is beside `ToolPatternLayer` — **R2's territory**, since their whole job is defending the parallel-array index invariant R2 exists to delete. **Carry this into R2's brief as an explicit input.**

Also worth stating precisely: the *engine layer* surface is ten, not six — `resolve.py` is in the same layer and additionally touches `resolve_config_path` (7,671), `resolved_undecidable_fallback` (5,631), `parse_failures`, `hard_deny`, `hard_deny_entries`. All ten are public, zero private, which is R6's predicate satisfied in advance for the engine half. The "six" claim is about one module and must be stated that way.

## The inversion is relocated, not removed — and our artefacts say otherwise

The ideal picture's correction was "config hands rules to the engine, not a callback handed to config". D1a delivers the first clause completely. It does **not** deliver the second: the callback is still handed into the walk, and from inside the walk still round-trips into `Configuration` — 3,643 `resolve_config_path` calls occur *during* an engine resolution (corroborating the D1 trace's 3,258 on a narrower scope). What changed is `engine -> config -> engine` became `engine -> engine`, converting a layer inversion into an ordinary strategy pattern. That is a sufficient win for this step, but the decision log and the module docstring both read as though the inversion is gone. **Fix the wording; R6 will meet this again.**

## Change cost did not improve, and the canary is predicted to stay flat

`--predicates` reports the enrichment footprint as 15 files, up from 14. Before citing it the judge checked what it measures: `find_enrichment_footprint` is a raw substring scan, so a docstring mention counts like a call. Re-run with a tokenizer splitting identifier tokens from string/comment tokens: **9 of the 15 have real code coupling, 6 are prose-only.** `config.py` had 3 real references at HEAD and has **0** now, but retains 5 docstring mentions, so it still counts. `permission_resolution.py` joined with 3.

**True code footprint: 9 files before D1a, 9 after.** The metric rose by one because a file that stopped participating still talks about participating. So the judge predicts the canary **will not move** — falsifying prediction 5.

That is not an argument against D1a; layering and change cost are different goods and D1a bought the first. It is an argument about what R1 must prove. What holds the footprint at 9 is the **multiplicity of verdict types** (seven verdict-ish types), not where the cascade lives — which is exactly R1's target.

**Adopted: re-run the canary BEFORE starting R1, not after.** R1's entire justification is a change-cost delta and it deserves a fresh baseline rather than one measured two steps back. Two flat readings in a row is the kind of thing to say out loud before the third, not after.

## The D4 deferral was correct, and the reasoning generalises

D4's claim was "these two expressions compute the same function over a small finite domain". The judge ran both over the full declared value domain plus junk (13 inputs including `None`, `0`, `True`, wrong case, nonsense) — identical in all 13. A judge reading a diff is a strictly weaker instrument for that kind of claim than ninety seconds of execution.

**Keep the rule: scale review to the *kind of claim*, not to ritual.** It was recorded in advance so it could be scored, and it scored well.

## What is now visible that was not before

**The engine's dependency on configuration is a measurable quantity.** Before D1a the walk was a method, so `self` was the surface and "what does the engine need from config?" was not a well-formed question — the probe could not have been written, because there was no boundary to instrument. The measurement *is* the new capability.

**A second implementation of the cascade was found and deleted, and it lived in the test suite.** Executed: during a `test_hook` run the real engine cascade is now entered **10 times through the double** where previously it was entered **zero** times — those hook tests were exercising a hand-written copy, not the product. Same pathology D4 fixed in production code, found one layer out.

## Debts this step created, to be paid before the ticket closes

1. **Docstring re-inflation.** The new module is 370 lines carrying ~118 executable lines: **202 docstring lines, 55% of the file** (AST-measured). R3's recorded win included cutting ~90 net lines of narration; the habit grew back one step later. Some is load-bearing (the HARD INVARIANT block earns its space); much is not.
2. **No `test_permission_resolution.py`.** Coverage is inherited, not owned — 28 cascade call sites still live in `test_configuration.py`. A maintainer looking for the tests of the module that decides permissions finds them in the file named after the module that no longer decides them.
3. **The module docstring's "a double only needs these six members" is over-broad** — true for this module, false for a double driven through `resolve.py`, which also needs `resolve_config_path` and `resolved_undecidable_fallback`.
4. **`RESUME HERE` still describes the superseded D1a/D1b shim split.**

## Component scores (judge's, breakdown not average)

Design **8/10** — right seam, cleanly cut, no upward dependency; loses points for the two misfiled staticmethods and for artefacts claiming the inversion is gone. Evidence **9/10** — strongest on the ticket so far; predictions recorded before the result, and P4 explicitly marked unverified until something ran, which is why the number survived scrutiny. Test coverage of the change **9/10** — all 48 non-def/import body statements covered; corpus alone misses exactly one line (`return reason` when provenance is None), covered by units. Documentation accuracy **7/10**.

## The blinded reviewer's findings (same batch, independent lens)

12 mutations, each with a full suite run and most with a full corpus replay. All four mutated files restored and sha256-verified against pre-mutation backups. **The two lenses overlapped on almost nothing**, which is the strongest evidence yet that the two-judge split is doing real work rather than buying a second opinion on the same questions.

**The finding that matters (medium-high).** `permission_resolution.py:160` — deleting `or resolved.decision == "deny"` from `_apply_ask_floor` left the **entire suite and the golden corpus green**, yet it changes real output. With a parse failure present and a matching deny rule carrying `additionalContext`, the guard is what preserves `provenance`, `additional_context` and `matched_rule`; without it all three are silently nulled while the deny still fires. So a user with one TOML syntax error somewhere loses the explanation their deny rule exists to deliver, with nothing to tell them.

**Decision: the behaviour is intended, the guard stays, and the missing thing is the test.** The floor never weakens a deny, and a deny genuinely made by a rule should keep its explanation. Note that the early return at `:160` and the identical-looking predicate at `:122` **share a predicate but do different jobs** — one decides whether to clamp, the other whether to preserve fields. A comment must say so, or a future reader will "simplify" one away. This is pre-existing, not introduced by D1a.

**Two claims we made that nothing enforced.** (1) The new module's "never imports `toolguard.config`" — a reviewer added `from toolguard.config import Configuration` and everything stayed green, because `.pyscn.toml` explicitly permits `engine -> config` and `test_architecture.py`'s `LAYERS` tuple omits the module. (2) Layer-map completeness — deleting `permission_resolution` from `.pyscn.toml` left 2,321 tests green; only a manual `--layers` run notices, and the one real-tree test asserts merely that it returns without raising. **`.pyscn.toml`'s own comment says the completeness check exists so this is "not a matter of remembering" — and it was exactly a matter of remembering.**

**The corpus is blind to two fields it should observe.** Nulling `matched_rule` at source (11 unit failures) and nulling the overridden deny's provenance (3 unit failures) both left `--verify` reporting no differences. The corpus is this refactor's equivalence oracle; widening it is item E.

**Also: `--verify`'s CLI exit status is more permissive than the suite's.** On one mutation it printed "OK (verdicts/output unchanged); tracked-field differences above are informational" while `test_verdict_corpus.test_tracked_fields_unchanged_or_acknowledged` failed on the same 22 reason differences. **Read the suite, not the CLI banner.**

**`toolguard/permission_resolution.py` was untracked.** `git add`ed. A `git commit -a` would have shipped a package whose `resolve.py` import fails at load — and a toolguard hook that cannot launch fails *silently*, since Claude Code blocks only on exit code 2.

**What it confirmed sound, by execution.** D4 is exactly behaviour-preserving (10 inputs, 0 mismatches) and now load-bearing (M1: 46 test failures + corpus). D1a is a genuinely pure move — an AST-level diff of all seven moved functions, docstrings stripped and `ast.unparse`-normalised against `git show HEAD:toolguard/config.py`, shows *only* `self.X` -> parameter substitution; no reason string, argument order, `None` handling or short-circuit changed. `_append_provenance` byte-identical. No fail-open path found: every permissive-direction guard it could reach is pinned.

## The instrument itself is wrong, and it is the one R1 will be scored on

`find_enrichment_footprint` is a raw substring scan, so a docstring mention counts like a call. It reports 15 files; only **9** have identifier-level coupling. `config.py` went from 3 real references to **0** and still counts, on the strength of 5 docstring mentions. Fixing it to tokenize is item J — and it must be fixed *before* R1, because R1's entire justification is a change-cost delta and an instrument that counts prose cannot measure one.

Noting a provenance failure of my own: this note previously recorded the change-cost canary as "7 files after R3". I cannot reconstruct where 7 came from, and the two measurements available now are 15 (raw) and 9 (tokenized). **Treating the 7 as unreliable rather than reconciling it against numbers I can actually reproduce.** Same standing failure as ever — a number recorded from a representation, reused later as if measured.

# Ruff configuration installed (2026-08-05), between the D1a debts and R1

Arnon left the timing to me. Installed **before R1, not after**, for one reason that matters: **PLR0913's suppression on `log_writer.log_command` is R1's acceptance test.** `log_command` takes 12 arguments against `max-args = 8`. Install the rule afterwards and the criterion is fitted to whatever R1 happened to produce; install it now and it is pre-registered. Same discipline as declaring R1 a change-cost step in advance — an instrument has to exist before the thing it judges.

Four rules on top of the stock defaults: **PLC0415** (no function-level imports, a stated prohibition that was unenforced), **TID251** banning `threading`/`asyncio`/`multiprocessing`/`concurrent.futures` (zero occurrences — a true ratchet on a stated hard rule), **PLR0913** at `max-args = 8`, and **RUF100** so every suppression is self-cleaning.

**Line-precise `# noqa` rather than per-file-ignores**, for everything except `test/**` (which legitimately imports inside functions for config isolation). A per-file-ignore on `hook.py` would blind the whole file to *new* violations; a marker on the line blinds only that line. Combined with RUF100 this is self-cleaning: when R1 gets `log_command` under 8 arguments, the now-unnecessary marker **fails the lint** rather than lingering.

## Three things that only showed up by running it

1. **`preview = true` under `[tool.ruff]` turns on the preview FORMATTER too** — 55 files that `ruff format` had called clean would have been reformatted. Scoped it to `[tool.ruff.lint]`; back to 148 files already formatted, matching baseline exactly.
2. **`extend-select` with preview on pulled in 2,164 findings** — pyupgrade and simplify churn nobody asked for, because preview widens ruff's *default* selection. Pinned `select` explicitly, listing the stock defaults, so preview cannot silently change what this project lints for.
3. **Writing the literal marker text inside a comment creates an invalid directive** — ruff parses it anywhere in a comment, not just at end of line. Reworded.

## A dead assertion, found by verifying a claim instead of inheriting it

The ruff investigation reported that `test_architecture.py`'s hand-maintained `GRANDFATHERED_LOCAL_IMPORTS` had drifted. **Confirmed by execution:** of its three entries, `("log_writer.py", "json")` no longer exists — the only indented import-looking line in that file is inside a docstring. The test had been carrying an entry for a violation that had been fixed, and nothing noticed.

The other two are genuine circular-import escapes (`hook -> tools.decision`, `auto_migrate -> scripts.migrate_permissions`) and are both **R5 targets**; they now carry the suppression marker the convention always called for, with a note that it comes off when R5 breaks the cycle. **The grandfather list is deleted — the ratchet reached zero.**

That is the second hand-maintained list on this ticket found to have drifted (the first was the test double's hand-written cascade). Both drifted silently, in the direction of claiming more coverage than existed.

## On the test-vs-ruff redundancy

`test_architecture.py` still checks local imports, and ruff now checks PLC0415 too. **This is deliberate redundancy, not the D4 pathology.** The harmful kind is duplicated *logic* where changing one copy silently does nothing; here they are independent *guards* — remove either and the other still fires. The test runs in the suite on every change; ruff runs when someone remembers. Said so in the test's docstring so a future reader does not "simplify" one away.

## Verified by construction, not by a clean run

A clean lint result proves nothing about whether the rules are live. Built a probe file with one deliberate violation of each — `import threading`, a 9-argument function, a function-level `import json`, and an unused `# noqa: F401` — and confirmed **all four fire** against the project config. Then deleted it. Same principle as the mutation gate: an instrument that never fails is a decoration, and the way to find out is to hand it a known positive.

Acceptance after install: ruff check clean (`--no-cache`), 148 files already formatted, suite **2,325 OK**, corpus **no differences**, `--guard` 12 canaries.

# R1: instruments fixed first (R1b), and the pre-registered baseline

R1 is the first step classified **change-cost** rather than structural, so a flat acceptance reading is a genuine failure. The scoping trace then found that **all three instruments R1 would be scored on were wrong**, so they were fixed before any R1 work touched the tree. Verified by me, not taken from the report: suite **2,335 OK**, corpus no differences, `--guard` 12/12, ruff clean with `--no-cache`.

## The corrected baseline — pre-registered, measured with zero R1 work done

```
R1: FAIL
  verdict-ish types (5):  ResolvedDecision, SubMatch, BashResolution, FileResolution, Decision
  __iter__ shims (2):     BashResolution  callers: 0 (prod=0, test=0, tools=0)
                          FileResolution  callers: 8 (prod=0, test=8, tools=0)
  enrichment footprint:   9 coupled / 6 prose-only / 69 total identifier-level occurrences
                          hook 26, compound 11, log_writer 8, config_types 1
```

## What was wrong with each instrument

**`find_verdict_types` matched on name substrings** — the same defect the enrichment footprint had before it was fixed to tokenize. A runtime census (instrumented `__init__`, full corpus replay plus the whole suite) showed only 4 of the 7 reported types were ever constructed on a decision path; `ProjectRootResolution`, `LedgerDecision` and `SingleDecision` never are. It also **missed `SubMatch`** — 8,314 constructions on the decision path, carrying `(sub_command, decision, matched_rule, provenance)`, which is the ideal picture's phase-6 unit verdict and squarely in R1's scope. Replaced with a structural rule (a field named `decision`/`verdict` plus at least two of reason/provenance/matched_rule/additional_context), **not** a hand-maintained allowlist — this ticket has now caught two of those drifting.

**`find_iter_shims` reported "0 callers" for both shims, and that was false.** It scanned only inside `toolguard/`; `FileResolution` has 8 test callers. I had relayed "free deletion" to Arnon on the strength of that number. Same error as the footprint: quoting an instrument without checking what it measures. Counts are now reported per area, and `BashResolution`'s remaining 0 is documented as a heuristic limitation rather than asserted as fact.

**The footprint's file count is bounded below at ~7** by files that must legitimately name the field, so a fully successful R1 would move it 9 -> 8 at best while removing ~44 of 59 real references. **The pre-registered "flat = failure" criterion would have produced a false failure.** Added a total-occurrence count alongside it. This is the second time a metric on this ticket has been about to be read as evidence when it could not support the reading.

## C1's mechanism is disproved; its conclusion survives

The hook response path is a **verbatim projection on 6,401/6,401 cases** — nothing is rendered from scratch and the output seam is already clean. The real mechanism is narrower: `hook.py`'s handlers return a bare `(decision, reason, additional_context)` tuple, **discarding 5 of `BashResolution`'s 8 fields**, so the verdict dies at the handler boundary; the log path is then a wide decomposition of the same object plus three hand-written adjustment rules. **Correct C1 in the ideal picture from "two symmetric consumers" to "one lossy projection and one wide decomposition, with almost no common surface".** Also invisible to the predicate: 16 functions return bare `(str, str, ...)` verdict tuples, 6 of them in `compound.py`.

## A live defect, escalated to Arnon

`hook.py:529` keeps only reason segments containing `" -> "`; `compound.py:748`'s `else` branch appends a leaf's raw reason, which for a `no_match_fallback`-allowed leaf contains no `" -> "`. Those sub-commands are **silently dropped from the audit trail**. I confirmed the mechanism by reading both halves of the round trip; the magnitude is the scout's corpus measurement — **813 of 975 compound allow cases (83%) under-log, 1,943 sub-commands with no audit entry**, 811 of the 813 in the real-traffic fixture. Worst observed: 10 sub-commands, 1 entry. Plus 79 logged `matched_rule` values carrying a stray trailing `]` from a greedy regex.

**I sanctioned `hook:524` as one of R3's two permitted prose-parse exceptions at CP2. That call was wrong** — TOO-19 was about audit-trail integrity and this is a hole in it. The fix lands as R1e (consumers take `sub_matches` directly), which is where `hook.py`'s own docstring already says it belongs, so it does not need to jump the queue — but it stops being "cosmetic follow-up".

## Staged split, blast radius measured by rename-and-count

R1b instruments (done) -> **R1a shims** (10 tests) -> R1c one runtime verdict type (~110, dominated by a single import cascade, mostly mechanical) -> R1d consumers take objects (7 production + 41 test call sites) -> R1e structured breakdown, which fixes the audit defect. Unifying `tools.decision.Decision` (32 sites) defers to R6.

# Arnon's directives, 2026-08-05 (recorded before acting on them)

**1. Fix the audit-trail defect — timing is my call.** Decision: **keep it as R1e, immediately after R1d.** Not sooner, and the reason is not convenience. The fix is "take the compound breakdown from `sub_matches` instead of a regex over the reason prose", and `hook.py`'s own docstring already explains why it could not be done at the time: building that list still parses each leaf's reason, so doing it now would *move* the parse rather than remove it. Worse, a blinded reviewer established earlier that **`sub_matches` does not yet hold what the prose recovers for ask-floor leaves** — so a standalone fix today would build a temporary path that R1d immediately rewrites, and would risk papering over the gap rather than closing it. R1d makes the consumers take objects; R1e is then a real fix rather than a second prose reader. **If R1d slips or grows, revisit this — a live audit-integrity hole does not get to wait indefinitely on a refactor's convenience.**

**2. Tuples are not an acceptable internal representation.** Arnon: *"I personally sort of dislike tuples except in cases of a strict pair value return. Tuples are harder to read and easier to index incorrectly. dataclass is trivially cheap and can be just as frozen."* NamedTuple is somewhat better but still worse than a dataclass.

This is directly load-bearing for what remains of R1. The scoping trace found **16 functions returning bare `(str, str, ...)` verdict tuples, 6 of them in `compound.py`** — invisible to the predicate, because a predicate over class definitions cannot see a tuple that was never a class. **R1d and R1e briefs must convert these to frozen dataclasses**, and the R1 predicate should be extended to count bare multi-value verdict tuple returns, or it will keep reporting progress it cannot see. Strict pairs stay as tuples.

**3. Blast radius is information, not an objection.** Arnon: *"the real question to answer there is 'what is better for the code quality?' If it improves it - then it's worth just doing it and fixing the tests logic. The important thing about the test is the meaningful behavior it verifies, not the implementation of the test nor the preservation of the shape of the behavior."* The one exception: **shape matters when it is part of an external interface or a specified contract** — for toolguard that means the hook input/output protocol and native permission syntax, which are exactly the three seams S1 already isolates.

This retires a habit visible in my own briefs: quoting "~110 affected tests" as though it were a risk to be justified. It is a cost estimate. The corpus is what establishes safety, not the test count.

## On criteria design, recorded because it generalises

Arnon on the R1 predicate declaring PASS on half its own definition: *"designing criteria is tough exactly because wrong criteria lead to wrong results, plus it gets gamed. True for automated systems and also true for people."*

And on the altitude refinement: *"Good intermediate change of attitude towards the one verdict type. Probably not the last change. But you are refining the definitions rationally."* **Expect the verdict-type definition to change again.** That is the process working, not drift — provided each change is argued from evidence and recorded here, so the final choice comes with the reasoning that produced it.

# R1c and R1d — and the pre-registration discipline catching its own error

All numbers below re-verified by me, not taken from the implementing agents' reports.

## R1c — one runtime verdict type

`ResolvedDecision` + `BashResolution` + `FileResolution` collapsed into **`RuntimeVerdict`** carrying `tool` and `target`; `SubMatch` renamed **`UnitVerdict`**. Both landed in `config_types.py`, not `resolve.py` — `permission_resolution.py` constructs `RuntimeVerdict` directly and importing `resolve.py` would have reintroduced a cycle. That constraint only surfaced by trying it.

Suite **2,337 OK** (+4 tests, zero deletions), corpus no differences, `--guard` 12/12.

**The altitude distinction came out structural**, which was the thing most at risk of becoming a carve-out. Nesting via `List[...]` field types identifies the unit altitude; package membership identifies tooling. No class names hard-coded, and each exclusion prints its reason in `--predicates` output.

## The fourth instrument defect: the predicate cannot see a verdict that was never a class

R1 flipped to **PASS** the moment R1c landed. It was still wrong. The predicate inspects **class definitions**, so the 16 functions returning bare `(str, str, ...)` verdict tuples — about a third of R1's real problem — were structurally invisible to it.

Fixed in R1b2 as an instrument-only task, deliberately isolated so no refactor could tune the measurement it is scored on. The detector combines two structural signals to a fixpoint: a tuple-literal return whose first element is `"allow"`/`"deny"`/`"ask"`, plus delegation propagation for wrappers returning an already-classified verdict function's result (`compound.py`'s chain needed two rounds). **No hand-maintained list.**

Worth recording: the agent tested the annotation-shape signal alone and **found a false positive by looking for one** — `log_writer._parse_discovery_line` returns a timestamp/root/levels triple that passes the shape check but carries no decision. Decision evidence is now always required on top of shape. It also reported **13 found against the trace's estimated 16**, with the search it ran to look for the missing three, rather than stretching the criterion to hit the number.

**Four instrument defects on this ticket now, each a different shape:** name-substring matching; a caller scan confined to one directory; a gate on half the predicate's own definition; and a scan that can only see classes. Every one reported success it had not earned, and every one was caught by execution rather than review.

## R1d — the consumers take objects

```
suite 2350 OK              corpus 6401 + 61, no differences
--guard PASS 12/12         ruff clean; both in-scope PLR0913 markers gone
bare verdict tuples        13 -> 10   (hook's three eliminated)
enrichment footprint       68 -> 53 occurrences   (hook 26 -> 14, log_writer 8 -> 5)
coupled FILE count          9 -> 9    UNCHANGED
```

`log_command` went from **12 parameters to 4**, via a hoisted public `LogRecord` — the private `_LogRecord` already existed with the right shape, built at the writer boundary instead of the caller boundary. The agent also converted `_log_allowed_command` / `_log_non_allow_decision` to take the verdict object, one call-frame beyond the brief, and stated plainly that **this, not the three named bullets, is what moved the number**. Same defect one frame out; disclosed rather than smuggled.

## The lesson of the day: right discipline, wrong instrument

I pre-registered "flat = failure" against the **coupled file count**. R1d left it at 9 — while removing **15 of 68 real references** and nearly halving `hook.py`'s. Scored on my own stated criterion, the step that finally delivered R1's change-cost win would have been recorded as a failure.

The only reason it read correctly is that a scout checked **what the metric could express** before the step ran, found it bounded below at ~7 by files that must legitimately name the field, and added an occurrence count.

**Pre-registering a criterion is necessary but not sufficient — the instrument must first be shown capable of expressing the outcome.** A pre-registered criterion against an instrument that cannot move is not rigour; it is a false failure waiting to happen, and it carries all the authority of having been committed to in advance. Generalise before R5 and R2: for each, confirm the predicate can *distinguish* success from failure before treating its reading as evidence.

# R1 COMPLETE (R1a - R1g), 2026-08-05

Final state, re-verified by me rather than taken from any report: suite **2,355 OK**, corpus **6,401 + 61 with no differences**, `--guard` PASS 12/12, ruff clean (`--no-cache`), doc links resolve. **R1 predicate PASS.**

```
RUNTIME verdict types (1):  RuntimeVerdict
UNIT   excluded (1):        UnitVerdict  -- nested in RuntimeVerdict.sub_matches / Decision.sub_matches
TOOLING excluded (1):       Decision     -- package 'tools', unified in R6
LEVEL  excluded (1):        LevelMatch   -- carries no Provenance; raw match at one hierarchy level
__iter__ shims:             0  (was 2)
bare verdict-tuple returns: 0  (was 13)
```

## The result that matters

**The audit trail is provably complete where it was 83% lossy.** 0 of 978 compound-allow cases under-log, 0 missing entries — down from 813 of 975 and 1,943 sub-commands executing with no audit record. `log_command` went from **12 parameters to 4**. R3's prose-parse sites dropped 2 -> 1.

Closing that defect exposed a **second, independent bug**: `resolve._deciding_sub_match` and `tools.decision._decide_bash` both attributed provenance with heuristics (`len(sub_matches)==1`, "first sub-command") that only worked *because* escape-hatch leaves were missing from `sub_matches`. Fixing the audit loss made them appear and broke the heuristics. The original defect had been masking the second one.

Two of the five "lost" values were correctly left as `None` rather than restored: that `grep` case is a single ask-floor leaf resolved entirely through the escape hatch, so writing `'grep *'` back would have re-introduced the fabrication bug TOO-19 exists to prevent. Established by probe, not by argument.

## The acceptance instrument failed, and I reported a number that meant less than I said

I told Arnon R1d moved the enrichment footprint 68 -> 53. R1e then took it to **72**, worse than R1's own starting point — and it is not a regression. 14 of `compound.py`'s occurrences are now `additional_context=` keyword arguments where the same values previously rode in **tuple positions**. The metric counts identifiers; a tuple slot has none.

**So the footprint cannot distinguish "coupling removed" from "coupling made visible", and it under-counts precisely the tuple-shaped coupling R1 exists to eliminate.** It was the instrument I pre-registered as R1's acceptance test. The defensible claims about R1 are the ones that do not route through it: audit completeness, 12 parameters to 4, 13 bare tuples to 0.

## Six instrument defects in one day, and the sixth was ours

1. `find_verdict_types` matched name substrings — over- and under-counted at once.
2. `find_iter_shims` scanned only `toolguard/` — "0 callers" when one had 8.
3. R1's gate tested `len(shims) == 0`, half its own stated definition — reported PASS on a two-method deletion.
4. The predicate could only see classes — 13 tuple-shaped verdicts invisible.
5. The enrichment footprint counts identifiers — blind to positional coupling (above).
6. **R1f named a field `matched_pattern` rather than `matched_rule` explicitly so the detector would not count `LevelMatch`.** Disclosed in its report, which is to its credit, but R1's PASS then rested on a field name.

Fixed in R1g by declaring a fourth **LEVEL** altitude, classified structurally on "carries no `Provenance`" — a criterion that never inspects the pattern field, with a test that renames it to `matched_rule` and asserts the classification does not move. `LevelMatch`'s own docstring, which still boasted about the naming dodge, is corrected.

**The general rule, worth carrying to R5 and R2: the cheapest way to satisfy a predicate is almost never the work.** An agent optimising honestly will still find that path unless the predicate is checked against the thing it proxies for. Five of these six were caught only by running something.

## Process failure of mine

Nine stages of verified-green work sit **uncommitted**, so when R1e half-failed there was no clean rollback point — reverting it alone would have taken D1a through R1d with it. I offered Arnon a commit command after D1a and never re-offered one after each subsequent green stage. **Commit at every verified checkpoint; it makes the next partial failure cheap instead of entangled.**

Also: an R1e agent went **85 minutes with no filesystem write while holding a failing tree** and had to be killed. I caught it by checking file mtimes, not by waiting. Its last line showed it mid-verification, most likely hung on a permission prompt. Briefs now ask agents to report progress as they go.

# R5 COMPLETE, 2026-08-05

Verified by me: suite **2,368 OK**, corpus **no differences**, `--guard` 12/12, ruff clean, hook smoke-tested on both the installed copy and the working tree. **R5 predicate PASS.** Layer direction violations **3 -> 1**, the survivor being `hook -> tools.decision`, deliberately left for R6.

## Fixing the instrument deleted more work than it created

R5a-0 was instrument-only, and it changed the shape of the whole step:

| before | after |
|---|---|
| 7 non-leaf modules, 2 cycles | 2 real violations |

- **R5 was UNPASSABLE.** `find_import_cycles` had no out-of-scope filter, so an intra-`toolguard/parser/` cycle counted — and parser/ is explicitly out of scope. The scout broke the real cycle and R5 still said FAIL.
- **It flagged the architecture we are building.** Four of nine edges were intra-`runtime` `hook -> {log_writer, error_log, session_warnings, subagent}`. The ideal picture defines `runtime = ingest, record, externalise`; `hook -> log_writer` *is* that design. The plan's predicate says "entry points are leaves"; the code asked "does the layer labelled runtime have fan-in". Different questions, and the second one was wrong.
- **A 3-line `.pyscn.toml` edit passed R5 with zero Python** — demonstrated, non-leaves 7 -> 2, all 147 architecture tests green. Entry points now come from `pyproject.toml [project.scripts]`: a fact about what ships, not an editable label. Two regression tests pin that the relabelling trick no longer moves the verdict.
- **`config_divergence -> error_log`, slated as a whole stage (R5d, ~34 tests), was never an R5 violation at all** — it was a layer violation, which is a different thing, and got fixed on its own merits.

## The work itself

**R5a — one line, zero tests.** `tools/decision.py` imported `FILE_PATH_TOOLS` from `hook`; `hook.py` defines it as a bare alias of foundation-layer `constants.FILE_TOOLS`, which two sibling tooling modules already imported directly. Cycle gone.

Both comments justifying the old arrangement were rewritten, because both became false. Worth keeping: the surviving local import in `hook.py` is **no longer a cycle — it is a layer violation**, runtime reaching into tooling, and it stays local *deliberately* because the hook is a per-process-per-call binary and hoisting it would load the whole tooling layer on the hot path of every invocation. A comment still describing a solved problem is how "someone will fix this someday" gets written into a codebase.

**R5b / R5c — the same defect twice: a console script that is also a library.** `permission_migration` split out of `scripts.migrate_permissions` (config layer); `install_update` split out of `update_check` (foundation, chosen on import-shape grounds against sibling `install_provenance`, not forced by a violation). Both console scripts smoke-tested end-to-end, unmocked — the check that catches a split passing unit tests while breaking the shipped binary.

**R5d** — `check_and_warn_divergence` now returns a frozen `DivergenceCheckResult` and `hook.py` does the logging, removing the upward config -> runtime import.

## Estimates were wrong in the safe direction, twice

R5b was estimated at ~88 affected tests and the suite ended at **2,367 either side**. On that evidence I **overrode the scout's recommendation to defer R5c** (~180 estimated) — it finished at 2,368. Both "blast radii" were mechanical call-site updates, not behaviour.

**Arnon's framing is doing real work here:** blast radius is a cost estimate, not an objection. Deferring the last instance of a pattern already fixed twice would have left R5 arbitrarily incomplete. I gave the agent an explicit out — stop if the work is *different in kind* rather than merely bigger — which is the distinction that makes overriding an estimate safe rather than reckless.

## A stale test found in passing

`test_architecture_fitness.py`'s "gamed `.pyscn.toml`" regression test had two silently no-op `str.replace()` calls, one introduced by R5b and one by R5c — the test was passing while exercising only part of the gaming move it existed to block. Fixed. **Third hand-maintained fixture on this ticket found drifting**, and the first to drift *because of our own changes*.

# R2 COMPLETE, 2026-08-05 — and the ticket's approved scope is essentially done

Verified by me: suite **2,387 OK**, corpus **no differences**, `--guard` 12/12, ruff clean, hook smoke-tested. **R1, R2 and R5 all PASS.** R3 has one site left; R6 is its own ticket. Layer violations: 1, the R6-deferred `hook -> tools.decision`.

## R2's result, stated without routing through a predicate

Index-parallel access sites **3 -> 0**. Prose index-alignment invariant statements **4 -> 0**. Both drift guards deleted. **Misaligned `ToolPatternLayer` state is now unconstructible** — a `TypeError`, proven by a new test — rather than merely guarded.

`ToolPatternLayer.allow`/`deny`/`ask` are derived `@property`s over the entry tuples, which are now the only stored fields, backed by a new `RuleEntry.stripped_pattern`. `provenance_for_pattern`/`entry_for_pattern` moved off `Configuration` to sit beside the layer type as linear searches over entries — no `.index()` anywhere.

The step was cheap for a reason worth remembering: **the pattern tuples were already computed as `tuple(_strip_tool_wrapper(e.pattern) for e in scoped)`. R2 deleted a materialised copy of a derivation that already existed.**

## The R2 instrument was the worst on the ticket, and fixing it found a hazard nobody knew about

`find_parallel_arrays` AST-matched a **hard-coded class name** and a `_entries` suffix. Given nine synthetic classes carrying the identical hazard, **it fired on exactly one — today's spelling.** Rename the suffix, use a dict-of-lists, use properties, rename the class, move to a sibling: all pass. **A `sed` satisfied R2.** It also could not see `Configuration.hard_deny`/`hard_deny_entries` — same hazard, same prose invariant, same guard — because a method pair is not an annotated field. R2 could have PASSed with it untouched.

The replacement matches on **use sites** (`A[B.index(x)]`, `zip(A, B)` with differing operands), so it is independent of class name, field spelling and container shape — and catches the method pair with **zero special-casing**, because inspecting usage makes the method-vs-field distinction irrelevant.

**It immediately found a third instance nobody had:** `config:1341`, a `zip(allow, allow_entries)` in `permission_layers`' takeover filter, invisible to the scout's `.index(`-only search.

For the clause that genuinely is not mechanically checkable — "stripped patterns are a derived property of `RuleEntry`" — it **prints the clause as explicitly unchecked with the reason**, rather than inventing a proxy that would look like coverage. That is the right answer to a predicate you cannot fully automate, and it follows the exclusion-visibility principle R1 and R5 already use.

## The guard everyone was protecting was dead code

Instrumented replay over 6,401 + 61 cases: **3,996 index lookups, drift guard fired 0 times, and the index answer never once disagreed** with a direct search over `RuleEntry.pattern`. The `resolve.py` guard was pinned by **zero** tests; the two tests pinning the `config.py` one existed solely to fire it synthetically and were deleted with the hazard.

## Rename-and-count measures NAME COUPLING, not work

The sharpest measurement of the day: renaming `hard_deny` breaks **106 tests**. The actual R2c change — same code, changed behaviour — breaks **0**.

That retroactively explains R5b's "88" and R5c's "180" both resolving to **zero net suite change**, and it means I have been quoting blast-radius numbers all day as though they indicated risk. They indicate how many places spell a name. **Report mechanical versus behavioural separately, or do not report the number.**

## Seven instrument defects, one day

Name-substring matching; a caller scan confined to one directory; a gate on half a predicate's own definition; a scan that could only see classes; a footprint metric blind to positional coupling; a field named to dodge a detector; and a class-name-hardcoded parallel-array scan a `sed` could defeat. **Every one reported success or failure it had not earned. Six of seven were caught only by running something.**

## Next

R3's last sanctioned prose-parse site (`resolve:423`) is under investigation — sanctioning was wrong once, in a way nobody noticed for months, so the remaining sanction gets re-earned on evidence or removed. R6 stays a separate ticket.
