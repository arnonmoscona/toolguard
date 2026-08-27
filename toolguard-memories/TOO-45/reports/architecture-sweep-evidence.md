---
title: architecture-sweep-evidence
type: note
permalink: toolguard/too-45/reports/architecture-sweep-evidence
---

# Evidence dossier — TOO-45 architecture-sweep article

Working document. Terse, no thesis, no narrative. Over-collected on purpose. Compiled from four
parallel research passes over the architecture-phase sources (retrospective.md, corrections-analysis.md,
corrections-corpus.md, r6-reassessment.md, change-challenges.md, architecture-judge-backtest.md,
architecture-judge-brief.md, proposed-tickets/32, surprise-factor-protocol.md + reports/surprise/*,
micro-canary-protocol.md, micro-requirements-blind.md, canary-before-after.md, canary-results.md,
boundary-canaries-preregistration.md, mr07-preregistration.md, canary-automode-experiment.md,
layer-separation-before-after.md, dependencies-before-after.md, end-state-summary.md, 03-design-A.md,
03-design-B.md, compound-cycle-*.md, proposed-tickets/00-INDEX.md + 01-16 + 06, tools/architecture_fitness.py,
.pyscn.toml, technical-notes.md, git log), plus direct spot-checks by the coordinator. Each item:
finding / number / pointer. Disconfirming evidence recorded at equal weight, not filtered out.

## A. Scope and caveat facts

- Same single-codebase, no-control-group caveat as the sibling #07 sweep applies here — one repo,
  one team (human + agent), stdlib-only runtime, unusual safety criticality (a permission hook).
  Nothing in the architecture-phase sources contradicts or extends that caveat differently.
- The architecture phase precedes the #07 comment sweep chronologically and is the larger, messier
  part of TOO-45: punch-list stages D1a, R0-R6 (sub-staged a-e), D4, D5, CP1/CP2, plus 16 follow-on
  numbered tickets (01-16) opened afterward. -- retrospective.md throughout; 00-INDEX.md.
- No canonical "R1 through R6, defined" legend was located in any source read. Meanings are
  reconstructed from scattered references: R1 = verdict-type/tuple unification + log_command arity;
  R2 = parallel-array/index-alignment fix; R3 = prose-parsing sites; R5 = import-cycle/layer
  violations; R6 = "the engine has a public interface." -- retrospective.md, various; flagged as
  reconstructed, not quoted from a single index.
- Test-count discrepancy, unreconciled in source: 2,387 (retrospective.md:84,732) vs. "2,600 passing
  tests" (corrections-analysis.md:30) vs. end-state-summary.md's own progression 2,186 -> 2,387 (with
  later mentions of 2,404/2,587/2,604 as work continued). Likely different snapshots in time, not
  contradictory, but no single authoritative count for "the" test suite size exists across sources.
- Module count for pre-TOO-45 master: 66 (dependencies-before-after.md) vs. 67
  (layer-separation-before-after.md, core-types-and-clarity.md) — unreconciled, likely a scope
  difference (one module in/out), not resolved in the sources.

## B. The central question — what instruments were built to answer "did this help"

Five distinct instruments, built for five distinct reasons, with five different survival records:

1. Layer/dependency fitness checks (`tools/architecture_fitness.py --layers`, `--predicates`) —
   static, always-on, checked into the fitness tool.
2. Co-change / `--metrics` history mining — static-history-based, part of same tool.
3. Surprise-factor protocol — blind touch-set prediction before each punch-list item, scored after.
4. Micro-canary / boundary-canary suite — blind micro-requirements implemented independently in
   old and new trees, compared.
5. Architecture-judge back-test — a blinded LLM judge re-reviewing already-committed, already
   reviewed punch-list diffs and pre-implementation specs against a 12-axis architecture rubric.

Each is detailed below (C-H). None of the five was rubber-stamped as unambiguously worth its cost;
every one produced at least one explicit negative or null finding about itself (see I).

## C. Structural before/after measurements (layer map, dependency graph, end state)

Trees compared throughout: pre-TOO-45 master `532de02` vs. branch `a3e3f27` (an earlier
"bulk, squashed" branch snapshot — several more TOO-45 commits landed after this point; see M).

**Layer map** (layer-separation-before-after.md):
- Direction violations: 3 -> 1 (the 1 remaining was deliberate, deferred to R6).
- Modules mapped: 67 -> 70; unmapped/multiply-mapped modules: 0 -> 0 in both trees.
- Import edges (deduped): 166 -> 173.
- Upward edges: 3 (2%) -> 1 (1%); intra-layer 87 (52%) -> 95 (55%); downward 76 (46%) -> 77 (45%).
  Framed in-source as "99% of the branch's import graph is permitted by construction."
- `tooling` layer = 33 modules, 47% of the codebase, internally UNCONSTRAINED by the layer check
  (the check governs edges between layers, not within one).
- 2x2 control (master code / branch code, each measured against master map and branch map):
  the map edit alone removes zero violations; under master's map, branch code shows only 3
  unmapped modules (the 3 new TOO-45 modules) — used as evidence the map edit was completeness
  work, not violation-hiding. "All improvement is in the Python."
- Gameability probe: 3 of 5 one-line `.pyscn.toml` mutations erase the last violation with nothing
  to catch them; only map *completeness* is pinned by a real test
  (`test_check_layers_runs_on_real_tree`) — direction has no test anchor. Framed in-source: "the
  map is simultaneously the specification and the thing being satisfied."
- The instrument under-reported the "before" state: master's `Configuration.resolve_permission_detailed`
  (config layer) called back into `resolve.py` (engine layer) via an injected callable — a real
  upward dependency, invisible to `--layers` because it produces no import edge.

**Dependency graph** (dependencies-before-after.md):
- Modules: 66 -> 69 (this report's own count; cf. the 67->70 figure above from a different report —
  see the module-count discrepancy noted in A).
- Import cycles: 2 -> 1 total; 1 -> 0 within "R1 scope."
- Console-script modules with fan-in > 0 (entry-point code imported as if it were a library, an
  architectural smell): 3 -> 0.
- Longest dependency chain: 12 -> 11.
- Runtime (not static) coupling: `config` and `resolve` called each other 46,481 times over a
  6,401-case replay with zero import edge in either direction, pre-fix — entirely invisible to
  static tooling. Post-fix: same call volume, now both ends sit inside the `engine` layer
  (`permission_resolution` <-> `resolve`) — "half-visible instead of entirely invisible," not
  eliminated as *volume*, only reclassified as a place static tools can in principle see.
- `config`-layer runtime calls on the decide path: 2,941,971 -> 380,483 (-87%), while `config`'s
  STATIC fan-in count went UP, 25 -> 26 over the same change — flagged explicitly in-source as
  evidence that fan-in, as a metric, misleads on this codebase.
- Audit trail volume: `log_command` calls 242 -> 447 (+85%); audit lines written 2,104 -> 3,480
  (+65%) over the same 150 compound commands (this is the fix for the under-logging defect, not
  new work — more entries because each sub-command now gets its own record).

**End-state summary** (end-state-summary.md, written 2026-08-06 — see M for why it is a
mid-ticket, not final, snapshot):
- `config.py` lines: 2,905 -> 2,509 (-13.6%).
- Bare verdict tuples: 13 -> 0. `__iter__` tuple-compat shims: 2 -> 0. Index-parallel array access:
  3 -> 0. Drift guards (redundant consistency checks papering over the above): 2 -> 0.
  Prose-parsing sites: 7 -> 0 (this document's own text notes an earlier draft had this wrong as
  "3" and corrects it in place). `log_command` parameter count: 11 -> 4 (also corrected in place
  from an earlier wrong "12").
- Console-script-secretly-a-library lines: 1,840 -> 175.
- Diff size at this snapshot: production-only 23 files / +4,143 / -3,088; full diff (incl.
  tooling/tests) 52 files / +15,704 / -10,946.
- Headline defect fixed: compound-command audit under-logging, 813/975 cases (83%) -> 0/978;
  sub-commands with zero audit record, 1,943 -> 0.
- Wasted computation removed, over the 6,401-case replay: materialized parallel pattern strings
  2,298,537 -> 0; parallel tuples 119,400 -> 0; `_strip_tool_wrapper` calls 2.38M -> 1.90M (-20.2%);
  reason render-then-re-parse round trips 8,304 -> 0.
- Explicitly NO measurable wall-clock win claimed: 9.03s -> 8.76s, characterized in-source as
  "noise... the gain is... not as measurable time" (i.e., the value is in correctness/legibility,
  not speed — the document does not claim a performance win it can't support).
- Self-correction on record: the document states plainly that four of its own numbers (prose-parsing
  site count, live prose-invariant count, `log_command` arity, `config.py` line count) were found
  wrong in an earlier draft of itself and fixed in place — described in-source as "the ticket's own
  central failure mode, committed while writing the summary of that ticket."

## D. Competing designs for cycle removal — two separate cycles, two separate design contests

**1. `compound <-> resolve` cycle** — shipped as commit `3bb21b7`.
- Plan A vs. Plan B (compound-cycle-plan-B.md, -judgment.md, -implementation.md). A blind judge
  subagent (read both plans + code, no other report) chose Plan B: "simpler for a reason that
  survives inspection" — Plan B maps 1:1 onto existing altitudes (`judge_unit`, `_combine_strictest`,
  driver); Plan A bundles three jobs into one `combine` function.
- Effort estimates: Plan A claimed 11-13h, Plan B claimed 3-5h. Judge attributed ~1/3 of the gap to
  Plan B under-budgeting (missing a docstring sweep and an evidence step) and ~2/3 to Plan A's
  design genuinely costing more.
- Concept-count method: today 10 concepts -> Plan B 7 -> Plan A 9 (Plan A removes the cycle but
  grows its biggest function — judged not the outcome the exercise was for).
- Judge found factual errors in BOTH plans (numbered B1-B5, A1-A5) and added 5 refinements (R1-R5)
  to Plan B before accepting it — notably moving a "records itself as one audited unit" flag onto
  `CommandUnit` as data (`audits_as_one: bool`), specifically to prevent the audit-log-loss defect
  class from recurring.
- Implementation report: concept count moved 10 -> 7 as projected; cycle verified gone both
  structurally (no `Callable` parameter left) and dynamically (`sys.settrace` trace: 14
  resolve->compound calls, 0 compound->resolve calls); came in cheaper than either original estimate.

**2. `permission_resolution <-> resolve` cycle** — a separate, later cycle; shipped as commit
`19299d9` ("Item 03"). Design A vs. Design B (03-design-A.md, 03-design-B.md).
- Design A ("move the callee, keep the injection"): relocate the injected callable's code below
  `permission_resolution` so nothing in `resolve.py` executes under its stack frame; the injection
  itself survives.
- Design B ("move the matchers below the cascade" — Shape 3, "decompose into three"): matchers move
  into a new module (`file_matching.py`) and `permission_resolution` imports them directly; no
  injection at all — "a strict DAG, nothing calls back, nothing is injected across a module boundary."
- Design B's own text corrects two of the briefing's stated facts as wrong before proceeding: the
  test-double count was undercounted roughly 10x (41 call sites / 11 closures, not "4" as briefed),
  and the laziness argument for keeping injection was "nearly void" — measured eager-vs-lazy cost as
  +0.6%, not the significant win the brief assumed. Design B rests its case on structure (an
  unbounded user-regex cost on the tail latency path) instead.
- The commit message for `19299d9` confirms Design B (or a design matching its description) is what
  shipped: "permission_resolution now imports its per-level matchers directly from permissions and
  file_matching instead of receiving one back as a callable... The alternative design kept the
  injection and relocated the callee's body, which would have left the real dependency invisible
  and then needed new predicates to detect the pattern it was itself introducing." This is a direct,
  in-commit argument for why Design A was rejected: it would have solved the visible symptom while
  leaving the underlying invisible-dependency problem, and required new tooling just to keep
  re-detecting the thing the design itself re-introduced.
- No standalone blind-judgment report (parallel to the compound-cycle one) was found for this
  decision in the sources read; the commit message is the only located record of why B beat A.
- Both design docs independently proposed a new fitness predicate to catch a recurrence of this
  exact runtime-cycle shape (Design A: AST scan for callback-cycle shapes; Design B: augment the
  import graph with injection edges and reuse the existing cycle detector) — both explicitly note
  the existing `--layers` check is structurally blind to this class of cycle, because both modules
  sit in the same layer and the check only governs edges *between* layers.

## E. `tools/architecture_fitness.py` — what it actually checks

- Four modes: `--layers`, `--predicates`, `--metrics`, `--guard`.
- `--layers`: reads `.pyscn.toml`'s `[architecture]` block as the layer map; checks completeness
  (every module mapped to exactly one layer) and direction (no import, including deferred/
  function-local ones, crosses against the declared allow-list).
- `--predicates`: diagnostics behind specific punch-list rules — verdict-type structural detection,
  altitude classification, tuple-compat shim census, bare-verdict-tuple tracing (R1); parallel-array
  detection (informational/gameable) and index-parallel-access detection (the real gate) for R2;
  import-cycle detection (Tarjan SCC), entry-point leafness, and private-import checks (R5/R6).
- `--metrics`: co-change history, deliberately grouped by `TOO-nn` ticket token in commit messages
  rather than by raw commit, explicitly to remove a commit-splitting gaming vector — the same
  design choice end-state-summary.md later reports as having backfired (see I).
- `--guard`: a deterministic safety inspector for the unattended dev loop itself (out-of-scope file
  touches, shrinking test count, new runtime dependency, failing lint/format/doc-link checks, plus a
  fixed CANARY set run through the live hook binary). Does not run `--layers`.
- Module docstring states its own philosophy: "Every number printed here is an INSTRUMENT, not a
  TARGET... never a self-sufficient stopping condition"; exclusions are tracked explicitly
  (`*_excluded`, `sanctioned_exclusions`, `known_limitations` fields) on the stated principle that
  "an exclusion the operator cannot see is indistinguishable from a bug."
- Generated code (parser/) is excluded from `--predicates`/`--metrics` but NOT from `--layers`.
- Confirmed via git log: `architecture_fitness.py` and `.pyscn.toml`'s architecture block are
  TOO-45-native (first added at commit `d5bdab3`, "verdict corpus, architecture fitness tool, and
  step R3"), not pre-existing infrastructure repurposed for the ticket.

## F. Punch-list ticket 06 — did the measurement tools earn their keep? (verdict-in-full)

proposed-tickets/06-measurement-tools-keep-or-remove.md concerns three specific dev-instrument
scripts (`change_role_classifier.py`, `touch_set_inventory.py`, `touch_set_score.py`), NOT the full
set of five instruments in section B. Status: **open, undecided, explicitly deferred from TOO-45
"for discussion before push."** No verdict was reached in the ticket text itself.

- These three tools were tracked in git only "by accident" — swept in by a `git add -A` inside a
  commit command given to an agent, not a deliberate decision to productionize them.
- Case for removal, as stated: "experiment instrumentation, not product," nothing in toolguard calls
  them; two of the three headline metrics were shown biased by adversarial testing (see I); neither
  contributed to any conclusion reached anywhere in the ticket ("every canary finding came from
  implementer prose and direct verification"); they carry roughly 90 tests that must keep passing
  indefinitely for tools nobody runs.
- Case for keeping, as stated: one sub-feature (an occurrence-count) was independently proven exact
  twice against an AST oracle; the inventory's file-access-blindness guarantee was audit-verified
  (170 file opens, none outside the tree, no subprocess/VCS access); rebuilding later would cost
  more than keeping now.
- Even the "keep" case is qualified in the ticket's own text: "must be re-attacked before any
  reuse" — the last adversarial pass found residual silent value loss in 13 of 24 implementation
  styles tested.
- The ticket ends with an explicit decision menu, not a recommendation: "Remove all three; or keep
  the inventory and delete the two scorers; or keep all three with a README stating they are
  unvalidated instruments."
- **This is not a "paid for itself: yes/no" verdict.** It is an unresolved decision with a mixed,
  honestly-stated record: real wins on narrow sub-claims, a proven-biased headline metric, and zero
  demonstrated causal contribution to any conclusion in the ticket.

## G. Pre-registration: the surprise-factor protocol

Source: surprise-factor-protocol.md + reports/surprise/{01,03,04,05,10,15}-*.md. Designed by Arnon,
2026-08-08.

- Mechanism: before each of 7 in-scope punch-list items, a blinded agent (ticket text + file
  inventory of path/line-count/first-docstring-line only + the `.pyscn.toml` layer map; explicitly
  "no repository access") predicts which files will be touched, where change concentrates, expected
  insert/delete counts, and names its own uncertainties.
- Scoring: hit = predicted-and-actual overlap; surprise = actual-not-predicted; overshoot =
  predicted-not-actual. Headline metric became recall = hits / |actual|; precision = hits /
  |predicted| carried alongside.
- The `|actual|/|predicted|` "surprise ratio" was explicitly DROPPED 2026-08-09 after its ranking
  inverted against recall on every one of four items where both were computed (item pairs/triples at
  05/01, 05/04/01, and a four-way 05/15/04/01 comparison) — never once agreed with recall.
- Every surprise gets a cause code: E (estimator ignorance, no alarm), C (hidden coupling — ALARM),
  P (prose coupling — ALARM, added after item 05 where prose coupling was 31% of the touch set), S
  (scope creep, attributed to the implementer not the estimator), D (latent defect — ALARM), and
  later R (requirement reversal/change), added at item 01.
- Blinding failure: item 05's estimate leaked into the coordinator's context automatically via a
  background-task notification. Fix from item 04 onward: estimator writes to a file and returns only
  a completion token, not its content.
- Abandon gate: if after 3 items every surprise classifies as E, the protocol would be dropped or
  revised. Never fired.
- Major correction, Arnon, 2026-08-09 (direct quote): "The surprise metric is not supposed to
  predict the actual. It is supposed to align with my expectations... Recall against the actual
  touch set is a property of the world, not of the instrument." Two stated purposes: (1) an initial
  size-of-ask impression, (2) once aligned, a surprise becomes a trigger to ask WHY (mess in the
  code, a dormant bug, a conceptual-model mismatch).
- A separate "complexity rating" sub-protocol: two independent low/medium/high ratings per item — a
  blind judge (diff + ticket, no implementer report) and Arnon (ground truth). Item 04 produced
  maximum disagreement: judge said "high," Arnon said "low" — this triggered a rewrite of the
  judge's brief (5 corrections). Items 15, 10, 03 then agreed (low, low, medium) — item 03 was the
  first non-"low" item under the corrected brief.

**Per-item results table** (predicted footprint / actual / recall / precision / dominant cause):

| Item | Predicted | Actual | Recall | Precision | Dominant cause(s) |
|---|---|---|---|---|---|
| 01 suppression store | ~20 (range 14-28) | 15 (pass 1) -> 20 (after 5 passes) | 67% -> 60% (final) | 36% -> 43% | 5 E (pass 1); final: 5 E, 3 R (spec moved mid-work) |
| 03 resolution cycle | 12 | 22 | 36% (worst of series) | 67% (best of series) | 7 E, 5 P (rename-driven prose coupling), 2 R (new design stage) |
| 04 error reporter | 21 | 14 | 79% raw / 88% prod-only | 52% (69% excluding scoped-out items) | 3 E only — first all-E item |
| 05 decision.py shim | ~16 (range 11-24) | 26 (pass 1) | 46% | 41% | 8 P (31% of touch set, largest prose-coupling instance), 6 E — item flagged CONTAMINATED (blinding failed) |
| 10 ToolSpec registry | 25 | 10 -> 16 (after fix pass) | 80% (best of series) -> 63% | 32% -> 40% | 1 C (first genuine hidden-coupling hit: a hardcoded tuple in tools/installer.py), 1 E, 4 R |
| 15 migrate lock | 13 | 11 | 64% | 54% | 1 C (auto_migrate.py hidden coupling), 3 S, 0 E for the first time |

- Cross-item pattern: the estimator predicted its own future misses in advance, in the uncertainties
  section, on items 01 (5 of 5 misses named in advance — quoted: "Five for five. Every miss was
  described in advance, by mechanism, by the thing that missed it"), 04, 15, and 10.
- Goodhart effect observed directly: once the estimator learned precision was scored, its behavior
  changed between items 10 and 03 — item 10 cast a wide net (25 predictions, 80% recall / 32%
  precision); item 03 cast a narrow one (12 predictions, 36% recall / 67% precision) after writing,
  in its own estimate: "predicting them would be hedging, and hedging is what precision scoring
  punishes."
- Two tickets' own headline claims were falsified by the estimation process itself: item 04's ticket
  claimed 16 hand-rolled stderr writes; actual count was 8. Item 10's ticket claimed "four
  independent membership sets"; actual was three live plus one dead, plus 3 more undocumented copies
  not mentioned in the ticket at all. Both flagged in-source as evidence the tickets were "written
  from a code reading rather than a count."
- No blanket "the protocol overall earned its keep" statement exists anywhere in these sources — the
  protocol's own closing text explicitly defers that judgment: the deliverable is described as "not
  a verdict on which measures work" but "a measure plus a mechanism that keeps measuring it," on a
  timescale of "months, not days... Nothing here is provable yet."

## H. Blinding: micro-canaries, boundary canaries, guard canaries

Three distinct instruments share the word "canary" in these sources; do not conflate them.

**1. Micro-canary / boundary-canary suite** (micro-canary-protocol.md, micro-requirements-blind.md,
canary-results.md). A "micro-canary" is a small requirement (MR-NN), authored blind by an agent that
read only public docs (never source), then implemented independently once against pre-TOO-45 master
and once against the branch by separate blind implementers, then compared.

- Mechanical scoring was explicitly ABANDONED before a single real canary ran. Two proposed metrics
  (M1: a role-classifier ratio; M2: a touch-set rate) were shown by Monte Carlo simulation (3,000
  draws, n=1..12, p=1.0..0.4) to be structurally biased toward whichever tree happens to be more
  coarse-grained: "the count picks the coarse tree in 64.7% of draws at p=0.8 and 90.9% at p=0.5."
  Conclusion stated directly: "There is no per-location common unit between two codebases that
  decompose a problem differently." A third metric (M3, cognitive-complexity delta) was never built
  at all — flagged in-source as "a placeholder, not a measure."
  In-source reframing: "Three of the four numbers this suite was designed to produce were proven
  biased before a single canary ran. That cost four agents and no implementations" — presented as a
  result, not a failure.
- Replacement method: judged, blinded, per-location adjudication — "would a careful reader of the
  requirement expect this location to change, and in this way?" — a count of adjudicated leaked
  concepts, not a computed rate.
- Twelve MRs were pre-registered; only 4 were actually run and reported (canary-results.md): MR-07
  (project-root marker), MR-08 (log-format env var), MR-10 (NotebookEdit as a governed tool), MR-12
  (compound part N of M). A staged "Wave 1 of 6, contingent Wave 2 of 6" plan
  (micro-canary-protocol.md) does not match the 4 actually reported — MR-09, MR-06, MR-02 (named in
  the Wave 1 plan) do not appear in canary-results.md, and MR-08 (not named in either wave as
  planned) does. No file in the set read reconciles this discrepancy; flagged as unresolved.
- Results: MR-12 — branch wins clearly. MR-10 and MR-07 — null (identical footprint / same defect
  found in both trees). MR-08 — a full reversal: master was self-rated "straightforward" and branch
  "fiddly," but master's ease came from silently introducing a real layering violation (`env_config.py`
  importing `log_writer` upward, config -> runtime, with no check able to see it); branch's extra
  difficulty came from correctly discovering and respecting the boundary. Quoted: "So 'straightforward'
  was straightforwardly wrong." This finding led to a real fix — introducing a new `observability`
  layer — so the null/negative canary result was itself productive.
- Every one of the 4 canaries surfaced a pre-existing product defect neither implementer was
  looking for (e.g., MR-07 found two indicator constants disagreeing about `package.json`; MR-10
  found two hardcoded file-tool tuples in `tools/danger.py`, found independently by both
  implementers "not by following code — only by grepping literal tuples"). Quoted conclusion:
  "implementing a plausible small requirement is a better defect-detector than reviewing the code."
- Honest limits stated directly in-source: "n = 4. No claim of significance." Implementer variance
  uncontrolled. No mechanical measure contributed to any conclusion — "Every finding above came from
  implementer prose and from my own verification against the live repo."

**2. The "tougher canary" / automode experiment** (canary-automode-experiment.md). A single
deliberately hard, cross-cutting feature (`allow_in_auto_mode`) built independently and completely
in both the master copy and the branch copy by the SAME agent, single ~4-4.5 hour session.

- Headline verdict, stated up front: "Natural in both trees, not free in either." Scatter across
  6-7 modules is inherent to any input-payload-dependent, verdict-changing, compound-surviving
  feature — no refactor eliminates that scatter.
- Diff size: branch is NOT smaller than master (13 files / 1,044 insertions vs. 12 files / 934
  insertions).
- Three concrete, execution-verified wins credited to branch: a real security-relevant edge case was
  cleanly closeable in branch (via a pre-existing split unrelated to this feature) and not cleanly
  closeable in master at all; a hand-rolled test double broke in master (9 test errors) and not in
  branch, because branch's function takes narrow duck-typed input vs. master's method taking a full
  object; the fitness tests caught a wiring mistake immediately in branch with a two-line fix, and
  "master has no equivalent mechanism to trip or satisfy."
- Over-fitting check: the benefit transferred to a feature TOO-45 never targeted — several unrelated
  punch-list changes (verdict unification, matcher reuse, a `subject` parameter avoiding
  reason-string parsing, layering enforcement) all paid off despite being built for other reasons.
- Named gap: R6 (Decision/RuntimeVerdict unification), explicitly deferred by TOO-45, was still felt
  directly — an adapter function had to learn about a new field "for no reason intrinsic to the
  feature." Recommendation: prioritize R6 if more such enrichments are coming.

**3. Guard canaries** (12 fixed probes inside `tools/architecture_fitness.py --guard`, safety-netting
the unattended dev loop's own permission fences — distinct from both instruments above).
canary-before-after.md's verdict: "earned its keep, but not for the reason usually stated." Measured
sensitivity to the actual TOO-45 code change: ZERO — for most of the ticket they ran against the
INSTALLED `~/.local/bin/toolguard` binary (byte-identical to pre-TOO-45 master throughout), not the
branch under test, so 0 of 12 disagreed by construction; when pointed directly at the branch, still
0 of 12 disagreed (demonstrated by direct execution, not assumed). The reframed value credited to
them is environment-integrity checking (catching a stale-install class of problem), not
refactor-correctness validation — the purpose they were originally built for.

## I. Negative and null results — consolidated

Required reading for this article per its own brief; collected here at the same weight as positive
findings, deliberately not folded into other sections so they aren't diluted.

- Co-change ("100%-coupled pairs") metric distortion: went 71 -> 134 (+89%) under per-ticket commit
  grouping vs. only 39 -> 42 (+7.7%) under per-commit grouping — traced to 63 of 63 newly-reported
  pairs moving from a 2-observation floor (suppressed by the tool's own coincidence filter) to a
  3-observation floor (reported), an artifact of TOO-45 being committed as fewer, larger commits, not
  a real change in coupling. -- retrospective.md. This is the specific mechanism by which the
  `--metrics` tool's own anti-gaming design (grouping by ticket token to remove a commit-splitting
  gaming vector, see E) backfired: end-state-summary.md separately reports the enrichment-footprint
  reading as "worse than R1's starting point" for the same underlying reason — one large refactor
  ticket collapses into one logical change, so co-change metrics report everything as coupled with
  everything.
- The change-cost canary (`architecture_fitness.py --predicates` enrichment-footprint metric) judged,
  after full measurement, "a compromised instrument; must be replaced" (canary-before-after.md).
  Three defects: (A) bounded below at ~9 files — read exactly 9 at every measured point through the
  whole ticket despite the ticket provably removing 13 bare tuples and cutting hook.py's enrichment
  references from 26 to 14, so it "could not register success"; (B) occurrence count ROSE by 19
  (53->72) on one step precisely because coupling was removed (positions became named fields instead
  of anonymous tuple slots) — "coupling removed and the number rose"; (C) gameable by a field rename,
  disclosed by the implementer who found the dodge. Even so, canary-before-after.md credits it with
  three secondary benefits, including "a forcing function for the discipline that saved the ticket" —
  "a bad instrument that is examined is worth more than a plausible one that is not."
- `run_guard_canaries` contributed nothing for 15 stages (see H.3) — a stale-install measurement gap,
  not a refactor-validation one.
- A naive "7 files" change-cost figure from an early canary run was later found unreconstructable and
  discarded outright: "I cannot reconstruct where 7 came from... treating the 7 as unreliable."
  -- retrospective.md.
- PLC2701 (ruff's import-private-name rule) rejected as a substitute for the layer checker: it
  reports clean on the exact line the layer predicate flags as a failure — demonstrated by direct
  comparison, not assumed. -- retrospective.md.
- pydocstyle (`D` rules) rejected as a docstring-quality proxy: 11,010 findings, 97.6% pure
  punctuation/placement noise; "not one `D` rule measures verbosity, redundancy or restatement" — the
  one docstring problem this codebase actually has. -- retrospective.md.
- A docstring-verbosity-ratio metric was proposed and never built. -- retrospective.md.
- General-purpose health signals from `pyscn` (dead-code count, LCOM, CBO) reported nothing wrong on
  a codebase later shown to have real entanglement — described as hitting "a second independent
  instance of the same trap" after an earlier one involving fan-in metrics. -- retrospective.md.
- A 3-line `.pyscn.toml` edit passed the R5 gate with zero Python code changed — a direct,
  demonstrated instance of gaming the layer-map predicate rather than fixing the underlying code.
  -- retrospective.md.
- R6's stated performance justification (that hoisting an import "loads the whole tooling layer on
  the hot path") was measured and found false: actual cost was 2 modules / 0.52ms, 1.6% of import
  time — and hoisting would not even have removed the layer violation, only moved its reported line
  number. -- r6-reassessment.md; corrected on Arnon's direct challenge.
- R6 itself was reassessed and recommended for retirement as originally scoped: its own detector
  (`find_private_imports`) is blind to 5 of 6 evasion routes, and its one reported violation was an
  artifact fixable by re-pointing a single import line — replaced with four narrower stages (S0-S4),
  one of which (S4, a 32-name config facade) was recommended DROPPED entirely rather than re-scoped,
  described as "accumulated, not designed." -- r6-reassessment.md.
- Four measuring instruments (the file-count and co-change measures among them) were, by the
  coordinator's own account, "built properly, adversarially tested, and then discarded when the
  design flaw surfaced" — proposed remedy: prototype on one case before building the general
  instrument next time. -- corrections-analysis.md.
- A sanctioned exception to the "carry structured data, don't parse your own prose" rule, granted at
  an earlier checkpoint (CP2), was later judged wrong and is the direct cause of the 1,943-record
  audit-trail loss surviving undetected for months — self-assessed in-source: "That call was wrong."
  -- retrospective.md.
- A specific failure shape (fixing one instance of a bug class rather than the class itself) recurred
  twice in immediate succession on the same punch-list stage (R3), the second time immediately after
  the first instance had already been shown. -- retrospective.md.
- The 12-guard-canary and change-cost-canary findings above both independently support a broader,
  explicitly-stated conclusion: "the metrics failed to automatically flag your apparent inability to
  follow industry architectural good practices... Every one was caught by Arnon, with a single
  question. None by any metric, blind agent, or test... Manual review is the control that works for
  architectural error... Bugs, by contrast, are being caught by process improvements. The two failure
  classes have different detectors, and only one of them is automatable so far." -- surprise-factor-protocol.md.
- Micro-canary mechanical scoring (M1/M2) abandoned before use — see H.1. M3 never built — see H.1.
- Ticket 06 (measurement tools keep-or-remove) remains explicitly undecided — see F.

## J. Instrument-measures-itself: candidate instances

The brief asked specifically for cases where a probe and the thing it probes share a source, making
a defect invisible. The clearest, most literal match found:

- **The layer map is both the specification and the graded artifact.** `.pyscn.toml`'s
  `[architecture]` block is simultaneously (a) the ground truth the `--layers` direction check
  validates every import against, and (b) a plain-text file editable with zero Python change to
  flip a reported violation to "pass." Demonstrated directly: 3 of 5 one-line map mutations erase
  the sole remaining violation with nothing in the toolchain able to catch the edit itself (only map
  *completeness* has a real test; direction does not). This is a strong match for "the probe and the
  probed system share a source" in a generalized sense — the check's own configuration is drawn from
  the same layer the code being checked lives in, conceptually, and can be edited independently of
  the code.
- **A weaker, adjacent match**: R6's detector (`find_private_imports`) is blind to 5 of 6 evasion
  routes for the exact violation class it exists to catch, and its one reported hit turned out to be
  an artifact fixable by relabeling rather than restructuring — a probe with a large blind spot in
  the exact dimension it claims to measure, though not literally sharing source code with a specific
  measured defect. -- r6-reassessment.md.
- **A related but distinct shape, not a literal match**: ticket 12 documents that the fix built in
  response to the 83%-audit-loss defect (a guard on `decide()`'s construction of the
  `sub_matches` breakdown) does not also guard `hook.py`'s actual file-write loop one hop downstream
  — so the same class of silent loss could recur past the exact point the fix was built to close.
  This is "the fix's blind spot reopens one hop downstream," not "probe and probed code share a
  literal defect," but is worth noting as a nearby failure shape in the same family.
- **Also worth noting, a different failure shape entirely (not a match)**: ticket 06 records that the
  `change_role_classifier.py` instrument's headline metric was anti-correlated with code quality —
  factored code scored WORSE than copy-paste code. This is a metric measuring the opposite of what it
  claims, not an instrument blind to a defect it shares with the measured code — flagged here only to
  avoid conflating it with the requested failure shape.
- No instance was found in the sources read of a probe and a specific measured defect sharing a
  literal, identifiable line or mechanism of source code (e.g., both built from the same buggy
  helper function). The judge-back-test defect #4 (an `OncePer.run` call executing a config-layer
  closure from an observability module with zero import edge, invisible to `--layers`) is the same
  *class* of invisibility as the compound-cycle and permission_resolution-cycle defects this whole
  phase was built to fix, but it is a recurrence of the class, not a literal shared-source instance.

## K. The architecture-judge back-test — the sharpest single result

Source: architecture-judge-backtest.md, architecture-judge-brief.md, proposed-tickets/32,
follow-up-queue.md:71-88.

- Design: 8 blind judge instances, one brief each, one subject each. Two arms — Arm A: 5 committed
  punch-list diffs (a false-positive control). Arm B: 3 surviving pre-implementation specs (the
  actual hypothesis test — Arnon's own review already caught findings at proposal stage for these,
  so the merged commits no longer contain them).
- Blinding: judges forbidden from reading any prior TOO-45 report (only the brief itself) and from
  reading other judges' output; scoring axes fixed before any report was read. Judges explicitly
  scoped to architecture only ("If you find a bug, ignore it") across 12 named axes (information
  hiding, single responsibility, coupling surface, indirection depth, dependency direction, cycles,
  data boundary integrity, failure-mode architecture, type boundaries, declared vs. hidden state,
  locality of change, single source of truth).
- Ran 2026-08-10, after the punch-list commits it reviewed had already landed and already passed
  review.
- Result: 8 live defects found in already-committed, already-reviewed code; 2 marked "fix before
  push." Confirmed identically worded across three independent sources (backtest.md, ticket 32,
  follow-up-queue.md). This is separate from a 4-item ground-truth hypothesis table (T1-T4, testing
  whether the judge catches 4 known/planted defects), on which the judge scored 2 of 4.
- **What kind of defect each of the 8 was** (the transferable part — what survives review):
  1. A structured-error type collapsed 4 distinct lock-failure reasons into one enum value, so a
     caller renders a false remediation message and silently loses a day's worth of intended work —
     a prose-is-output violation of the kind the sibling article's rule-0 material also documents,
     but found here in shipped code rather than a comment.
  2. A hidden call edge via dynamic dispatch (`getattr(module, fn_name)`) invisible to
     call-hierarchy tooling (`incomingCalls`), introduced solely to keep a test's patch target
     working.
  3. An incomplete migration — the calling module still hand-rolls the exact duplicated logic a
     new component was built to remove, including a second copy of a severity-routing table.
  4. A runtime layering cycle invisible to the static layer checker — the same defect *class* the
     phase's two headline cycle removals (D above) were built to eliminate, recurring in new code
     written after those fixes shipped.
  5. Two conflated concepts sharing one boolean flag, with a test that pins the conflation by
     asserting the two concepts' derived sets are equal, making them impossible to decouple without
     breaking a test that exists specifically to prevent decoupling.
  6. A live mutable global dict with import-time-snapshot derived collections that can silently
     diverge from it.
  7. A test oracle that cannot detect a class of real change because the path it exercises replays
     data captured after the exact transformation it's meant to verify.
  8. Genuinely dead code (a mutable set with zero readers) sitting among otherwise-immutable
     structures — a minor type-hygiene smell, included for completeness of the count.
  - A near-miss, not counted in the 8: a spec instruction that would have deleted an independent
    test oracle's deliberate duplication was silently NOT carried out by the implementing agent —
    "the coder's silent non-compliance is the only thing that saved it. No review caught it."
- Verified against the live working tree (not merely asserted): **neither "fix before push" defect
  has actually been fixed.** Defect #1's fix (a distinct enum value or carried reason) is absent —
  the code still collapses to one value and returns it unconditionally. Defect #2's `getattr`-based
  dispatch is untouched; the file's only uncommitted changes are unrelated doc-comment trims from the
  separate #07 sweep. Neither defect appears in the 00-INDEX "Done" table; both remain in the
  still-open table, queued since 2026-08-10.
- No cost figure (time, agent-calls, tokens) is given anywhere in these sources for running the
  8-judge back-test itself. A cost figure that DOES exist in the corpus ("roughly $3 and ten minutes
  for the blinded pass") belongs to a different, more general two-judge review practice described in
  retrospective.md, not to this back-test specifically — flagged explicitly to avoid the mix-up.
- Declared limitations, stated directly in-source: (1) one-sided blinding — judges were blind but the
  12-axis list was not; 3 of 12 axes map onto known defects, diluting but not removing the steering,
  and a clean replication would need axes chosen by someone who hasn't seen the corrections; (2) n=4
  ground-truth positives — establishes existence, not a rate; (3) this codebase can't exercise most
  architectural axes (no persistence layer, no request lifecycle, no schema, no deployment topology)
  — silence on those axes is not evidence about them; (4) the control arm (comparing against general
  `/code-review` reports for the same five commits, to directly test "focused beats general") was
  never run.
- The single sharpest negative result is a MISS, not a hit: T4 is the same defect as T3 (a closed
  tool registry unable to describe a user-declared MCP tool) in a different substrate — caught by the
  judge in the pre-implementation spec (T3) but missed by the judge in the committed diff (T4).
  Stated directly: "the judge sees architectural defects in proposals and not in diffs" — which
  directly bounds the instrument's claimed usefulness, and led to an explicit revision of the brief's
  own guidance ("prefer proposals over diffs").
- A second, smaller rubric failure is also on record: on item T1, the judge applied the brief's own
  exclusion rule correctly, by that rule's original wording, and still missed a real defect (a
  fail-open deferred to a named successor item) — the brief itself needed a follow-up fix as a
  result.

## L. Punch-list tickets 01-16 — one line each, status reconciled against 00-INDEX.md

| # | One-liner | Status |
|---|---|---|
| 01 | Once-per-session warnings: wanted three times, built zero; four duplicate ad-hoc mechanisms existed, none keyed on session_id | Done (e3da420) |
| 02 | Pattern-string is the non-unique join key between a match and its rule entry; a latent provenance-conflation hazard, not observed in the wild | Open, needs a design decision |
| 03 | permission_resolution <-> resolve runtime callback cycle, invisible to the import graph | Done (19299d9) |
| 04 | 16 hand-rolled stderr writes in config-layer modules bypassing layering; merged into a broader error-reporter design | Done (ee9aa94) |
| 05 | tools/decision.py: a 38-line dead re-export shim over toolguard.api, still imported by 6 modules and ~11 test files | Done (dbdd797) |
| 06 | Whether to keep 3 unvalidated dev-measurement tools swept into git by accident | Open, no verdict (see F) |
| 07 | Doc-comment/docstring cleanup sweep | Sibling article's subject, not this one's |
| 08 | Replace semantic string literals with named constants; a typo risk that fails open silently | Open, deferred |
| 09 | Write docs/architecture-as-built.md, human-consumable, from branch-side report material | Open, pending |
| 10 | "A governed tool" was a bare string across 4+ independent membership sets, no shared registry | Done (2113d02) — flagged by ticket 16 as having "looked solved without solving it" |
| 11 | Whether the ASK floor covers non-Bash command tools (e.g. an IDE terminal tool) — undocumented, security-relevant | Open; recommended to measure before push regardless |
| 12 | The audit-trail fix guards decide()'s construction of sub_matches but not hook.py's actual log-write loop one hop downstream | Open, deferred; recommended soon (see J) |
| 13 | Project root is re-resolved from cwd on every tool call rather than anchored once per session; two resolvers can disagree mid-session | Open; flagged as needed before RC1, semantics decided, mechanism not yet built |
| 14 | The hook's error-path handlers print decision JSON to stderr and exit 0, so Claude Code sees no opinion at all — a fail-open in a permission tool | Done, folded into #04 (ee9aa94) |
| 15 | migrate()'s read-modify-write across two config files had no lock of its own; safe only by accident of its one caller's gating | Done (caa83e7); severity assessed low, built partly for methodological reasons (a control case for the surprise/canary measurement series) |
| 16 | ToolSpec/dispatch describes built-in tools only; a registered non-file/non-Bash tool is silently mishandled | Promoted to a separate ticket (TOO-51), deferred past RC1 |

## M. Numbers/claims checked and found to need correction or flagging

- End-state-summary.md is a 2026-08-06 snapshot; several more TOO-45 commits landed after it
  (e46900b, 3bb21b7, 46de79c, e3da420, ee9aa94, caa83e7, 2113d02, 19299d9, dbdd797 — confirmed via
  `git log --oneline --grep=TOO-45`). Its numbers describe an intermediate state, not the ticket's
  final shape — use with an explicit "as of 08-06" qualifier if cited.
- Module-count and test-count discrepancies noted in A are real, unreconciled, and both sides are
  sourced — report both or pick one and flag the source explicitly; do not present either as the
  single authoritative figure.
- "Threefold budget misjudgment" and "roughly 2,000 prose claims verified" (both flagged unsourced by
  the sibling article's own evidence pass) belong to the #07 phase, not this one — not used here.
- Wave 1/Wave 2 canary staging vs. the 4 canaries actually reported does not reconcile in the sources
  read (H.1) — presented as an open discrepancy, not resolved.
- Confirmed by direct commit-message read (not secondhand): Design B, not Design A, shipped for the
  permission_resolution/resolve cycle (D.2) — this required checking git show 19299d9 and the two
  design docs' own "chosen shape" headers directly, since no blind-judgment report equivalent to the
  compound-cycle one exists for this decision.
- The claim "the judge back-test found 8 defects, 2 fix-before-push" was independently verified
  against three sources using identical wording — high confidence, not merely asserted once.