---
title: TOO-45 delta - as-is against ideal
type: note
permalink: toolguard/too-45/too-45-delta-as-is-against-ideal
tags:
- task-memory
- TOO-45
- architecture
---

# TOO-45 delta: as-is against ideal

2026-08-04. Third of the three P3 artifacts. As-is structure: [[TOO-45 decision log]] P.3.
Ideal: [[TOO-45 ideal picture]]. This is the boundary-by-boundary comparison the step order is
derived from.

Evidence base: `tools/architecture_fitness.py` (AST import graph, predicates, history metrics),
the 5-mutation corpus battery, and call-site reading. Where an earlier grep-based number of mine
disagreed with the AST tool, **the AST number is used and mine is recorded as wrong**.

---

## Boundary-by-boundary

| # | ideal boundary | holds? | evidence |
|---|---|---|---|
| 1 | Ingest: hook event -> invocation | **partly** | no separate ingest phase; `hook.py` main() parses the event and threads fields onward |
| 2 | Strategy selection per tool | **yes** | Bash and file-path paths are distinct (`resolve_bash_permission_detailed` vs `resolve_file_path_permission_detailed`) — though R4 (out of scope) is about them being *two pipelines* |
| 3 | Decompose -> units | **yes** | PEG grammar; `LeafCommand` / `UndecidableSegment` are already unit kinds |
| 4 | Configure: load, order, expose | **NO — the central defect** | `Configuration` runs the decision. See D1 |
| 5-7 | Match / unit verdict / consolidate | **partly** | live in `permissions`/`compound`, but orchestrated from `config` via callback |
| 8 | Post-decision directives | **n/a** | no directive concept exists; see D3 |
| 9 | One internal verdict type | **NO** | 7 verdict-ish types, 5 dead `__iter__` shims. See D2 |
| 10 / 11 | Record and externalise as siblings | **NO** | rendered twice from loose parts. See D2 |
| seam: input | **partly** | no isolated seam, but engine is clean of hook shapes |
| seam: output | **NO** | `create_hook_output` exists but is fed by hand-assembled parts |
| seam: native syntax | **untested** | `migrate_permissions` should be transport-not-translation; not yet verified |
| layering | **near** | completeness passes; 3 direction violations, 2 of them function-local imports |

---

## D1. `Configuration` is the decision orchestrator (boundary 4/5-7)

The largest divergence, and the one that explains the measurements that contradicted each other.

`resolve.py:560,684` pass a callback **into** the config object; `Configuration` walks the
hierarchy, resolves provenance, extracts enrichment, detects overrides via a *second* callback
pass, and constructs `ResolvedDecision`.

Explains: `config` fan-in 25 of 67 (control hub, not data hub); `compound`/`permissions`/
`resolve` fan-in 2 while being the most co-changed files in the repo; `compound <-> config` at
100% co-change; and the structure/history disagreement in P.3.

**Cost may be low relative to leverage.** `permission_levels_with_provenance()` is already
public — the engine can walk the levels itself. The encapsulation is drawn around the
*algorithm* when it should be around the *data*, so the fix is relocation of a ~25-line loop, not
new plumbing.

**Invisible to three instruments.** `config` is *below* `engine`, so calling `decide_detailed` is
an **upward call** — a layer violation that no import-based checker can see, because the callback
is passed as a value. Fan-in, import graph and pyscn layer compliance are all blind. Only
co-change saw it. This is why `--layers` reports 3 violations and none of them is the worst one.

**Not covered by any existing predicate.** Candidate new step.

## D2. One verdict, rendered twice, from loose parts (boundaries 9/10/11)

- **7 verdict-ish types**: `ResolvedDecision`, `BashResolution`, `FileResolution`, `Decision`,
  `LedgerDecision`, `SingleDecision`, `ProjectRootResolution` (the last is likely a false
  positive of the detector — it concerns project roots, not permissions; needs a judgement pass).
- **5 `__iter__` tuple-compat shims, all with ZERO callers.** Free deletion.
- `log_writer.log_command()` takes **eleven loose parameters**. `hook.py` decomposes the verdict
  into eleven arguments for the log and separately reassembles it for the response.

So `hook.py <-> log_writer.py` cannot change independently: the interface between them is
"spread the verdict out by hand". Mechanical coupling, not cultural.

## D3. Per-decision data has no home — and the pattern has already repeated

`additionalContext` spans **14 production files**. Then:

**`fallback_warning` is the same pattern, second instance.** A single `bool`, carried on
`ResolvedDecision`, `FileResolution` and `BashResolution` — three of the verdict types — routed
to the log but not the response.

This matters for how the enrichment work is justified. It is not "a future directive might need
this". Two pieces of per-decision data have now been added, and **both were added the same way**:
a named field on several verdict types plus a parameter on `log_command` plus a key in the
response. The third will cost the same unless the shape changes.

Ideal-picture phase 6 ("preserve any warning the rule produced") **does not exist**. There is one
boolean for one case. C6 is therefore *partly* confirmed: the audience distinction is real, the
collection is not.

## D4. Undecidable handling is duplicated, and the duplication is provably removable

Two sites apply the undecidable floor: `_apply_undecidable_floor` (compound:325) and a direct
`_UNDECIDABLE_FLOOR_DECISION` lookup (compound:896). Found by **mutation**, not reading — a
single-site mutation changed no behaviour.

The duplication is documented and defended ("no underlying decision to floor"). But the two
compute the same function: `_apply_undecidable_floor("allow", fb)` equals
`_UNDECIDABLE_FLOOR_DECISION.get(fb, "ask")` for every value — `ask->ask`, `deny->deny`,
`allow_with_warning->allow`, `allow->allow`, unknown->`ask`.

So modelling an undecidable unit as one whose pre-floor decision is `allow` collapses them. The
equivalence is arithmetic rather than self-evidently semantic, so it needs empirical
confirmation — and **the corpus is exactly that instrument**: make the substitution, run the
corpus, a pass is evidence the unification preserves behaviour. Using the corpus to *prove a
refactor safe before committing to it*, rather than only to gate it afterwards.

## D5. R6's predicate does not describe R6's problem

Predicate: "no `tools/` or `scripts/` module imports a private name from `config`, `permissions`,
`compound`, `resolve`."

Live value: **one violation** — `tools.takeover_audit:87` imports `_strip_tool_wrapper`.

The ticket calls R6 "plausibly larger than R0+R3+R5+R1+R2 combined". A one-line fix satisfies the
predicate and changes nothing. The tooling boundary problem is not about which names are
imported; `tools/` is 31 modules and 13,346 LOC — the same size as the engine it wraps — and its
coupling runs through `Configuration` like everything else (D1).

**R6 cannot be scheduled until its predicate is rewritten.** This is a live instance of the
plan's own rule: satisfied predicate + unconvinced judge means the predicate was wrong.

## D6. Smaller, real, cheap

- **R2**: 3 parallel-array pairs on `ToolPatternLayer` (`allow/allow_entries`,
  `deny/deny_entries`, `ask/ask_entries`). Exactly as the ticket described.
- **R3**: **5** sites, not the 3 I reported (`hook:461`, `hook:978`, `resolve:563`, and
  `resolve:692`/`:699` which use a `reason_body` variable my grep could not see). Not "half the
  budgeted size" — 5 of 6.
- **R5**: 7 non-leaf runtime/scripts modules; 2 cycles. `scripts/migrate_permissions.py` is a
  co-change hub, as the ticket said.

---

## What the delta does NOT cover, stated so it is not mistaken for complete

- **The tooling half.** 31 modules, 13,346 LOC, and the ideal picture says almost nothing about
  it. A picture that explains the engine and is silent on half the codebase is half a picture.
  This is the main known weakness of P3 and the reason R6's size is still unknown.
- **The native-syntax seam.** The transport-not-translation claim about `migrate_permissions` is
  untested. It matters because that script is a top-five co-change hub and should be a leaf.
- **R4** is out of scope by decision, but D1 touches the same machinery; the boundary between a
  reorganised orchestration and R4's pipeline unification will need care.

---

# R6's real size, and the corrected predicate

Measured 2026-08-04. Current predicate ("no private-name imports") = **1 violation**. Under a
predicate that describes the actual problem — *tooling reaches into the engine at all* —
**21 of 33** `tools/`+`scripts/` modules import `config`, `permissions`, `compound`, `resolve`,
`config_types`, `rule_entry` or `rule_sort` directly. 64%.

Dominant shape: `from toolguard.config import Configuration, Provenance`, in roughly a dozen
modules. So the surface the tooling needs is largely "a queryable configuration with
provenance" — which is designable, and is also exactly what `Configuration` should have been
before it absorbed the decision (D1).

**Proposed replacement predicate:** no `tools/` or `scripts/` module imports from `config`,
`permissions`, `compound` or `resolve` at all — only from the declared `api` module. Checkable,
strictly stronger, and it cannot be satisfied by renaming one private symbol.

**Recommendation: R6 becomes its own ticket.** 21 modules, and it *depends on D1* — the api
surface cannot be designed while `Configuration` is simultaneously the config object and the
decision orchestrator. Answers the question deferred at plan time.

---

# Proposed step order

TOO-45 becomes: **R3 -> D4 -> D1 -> R1 -> R5 -> R2**, with R6 split out and enrichment tracked
rather than scheduled.

### 1. R3 — decisions carry structured data (5 sites) . **CP2 here**

Small, real, needs judgement (which sites are rendering and which are parsing), spans two files.

**The original reason for putting R3 first no longer applies.** The plan said R3 must come first
because reason strings were an undocumented data channel, so any reword was a silent behaviour
change. The corpus's two-tier goldens now catch exactly that and force explicit acknowledgement.
**The corpus does the job R3-first was meant to do.** R3 stays first anyway — but as a
well-sized probe of the loop, not as a safety prerequisite. Being honest about which argument is
load-bearing matters, because the old one would have justified it at any size.

### 2. D4 — unify the two undecidable-floor sites

Tiny, and the equivalence is provable on paper (see D4 above). Its real value is method: it is
the first use of the corpus to **prove a refactor safe before committing to it**, and the first
use of mutation to check that a claimed unification actually happened. Cheap place to establish
both habits.

### 3. D1 — the engine owns the decision; config answers questions

Highest leverage. Unblocks the api surface (R6) and moves verdict construction to one place
(R1). Possibly modest cost since `permission_levels_with_provenance()` is already public.

Deliberately **not** first: it is the largest structural change, and putting it before CP2 would
mean assessing the loop only after the most expensive step. If the loop is not working, that is
the worst possible moment to find out.

### 4. R1 — one verdict type

Includes the 5 zero-caller `__iter__` shims (free deletion) and making `log_command` and the
response both consume the verdict instead of eleven loose parameters. **The enrichment footprint
should fall here**; the canary measures whether it did. Per Arnon, enrichment is not scheduled as
a step — but a flat canary at this boundary is a finding, not a shrug.

### 5. R5 — entry points and scripts are leaves

7 non-leaf runtime/scripts modules, 2 cycles. Partly downstream of D1: `tools.decision <-> hook`
may resolve once the engine owns the decision.

### 6. R2 — one rule representation

3 parallel-array pairs on `ToolPatternLayer`. Independent and well understood; last because it is
the least entangled, not because it is least important.

### Removed from the ordering

- **R0** — a prerequisite, delivered.
- **R6** — its own ticket, after D1.
- **Enrichment / directives** — tracked outcome measured by the canary, per Arnon's correction.

### What would change this order

If D4 or R3 reveals that the corpus is weaker in practice than the mutation battery suggested,
everything after it stops being safe and the order is moot until that is fixed. That is the
single dependency the whole sequence rests on, which is why CP2 sits immediately after the first
real step rather than later.

---

# D1 EXECUTED TRACE, 2026-08-04 — the "~25-line loop" claim is dead

Measured over the 5,389-case corpus with `sys.setprofile`, `sys.settrace`, wrapped
`Configuration` members and two reversible rename mutations. Method and probes preserved so any
number can be re-run. This supersedes every reading-derived statement about D1's size and shape.

## The claim that does not survive

**"D1 is relocation of a ~25-line loop."** The cascade loop proper is 32 lines / 26 executable —
so the figure is literally true of the span it names and **false as a description of D1**.

| what actually moves | total lines | executable |
|---|---:|---:|
| `_resolve_permission_detailed_unclamped` | 107 | **65** |
| `_detect_override` | 38 | 18 |
| `_parse_failure_reason` | 22 | 9 |
| `_apply_parse_failure_ask_floor` | 40 | 5 |
| `resolve_permission_detailed` | 45 | 2 |
| `apply_parse_failure_floor` | 39 | 0 |
| `_append_provenance` (module fn) | 26 | ~19 |
| **total** | **317** | **~118** |

The 26-line loop is **26 of 118**. Immediately after it sit **55 more lines (39 executable) of
no-match fallback policy**, reached by **56% of all resolutions** (4,369 of 7,781). That tail is
decision policy by any reading; it moves with the loop or nothing moves.

**12.7x by total lines, 4.5x by executable lines.** I recorded that estimate in this very note and
it was wrong — the seventh instance on this ticket of a reading-derived claim failing on contact.

## What the trace confirmed, and it is better than expected

- **`_resolve_permission_detailed_unclamped` reads ZERO `self.*` data attributes.** None, across
  5,389 cases. It touches `Configuration` only through method calls.
- **Zero attribute writes during the walk.** No state mutation.
- **Callback nesting depth: 1. Re-entrant orchestration entries: 0.** No recursion.
- `_provenance_for_pattern`, `_entry_for_pattern`, `_detect_override` are all `staticmethod`s
  touching no instance state.
- Only **3 production call sites**, all in `resolve.py`. **Zero `tools/`/`scripts/` callers at
  runtime** — static grep and the trace agree exactly.

So the barrier to moving the machinery is **not** entanglement with private state.

## The real barrier is the NAME, and it is measurable

Two reversible mutations settled this:

| mutation | tests broken |
|---|---:|
| rename the **public** entry points on `Configuration`, patch the 3 production call sites | **47** |
| rename only the **five private internals** | **3** |

Zero tests call `_resolve_permission_detailed_unclamped`, `_apply_parse_failure_ask_floor` or
`_detect_override` by name. **44 of the 47 are coupled to the public name
`Configuration.resolve_permission_detailed`, not to the machinery.**

**This changes D1's shape.** It can be staged:

- **D1a — move the decision machinery out, keep `Configuration.resolve_permission_detailed` as a
  thin delegating shim.** Cost ~3 tests. Nearly all the architectural gain, minimal blast radius.
- **D1b — remove the shim and update the 47 tests.** Separable, and can wait for R6, which is
  about exactly this public surface.

That staging is only visible because the two mutations were run. No amount of reading gives it.

## What reading could not have found

**(a) The callback re-enters `Configuration`.** `resolve.py:_anchor_file_pattern` calls
`config.resolve_config_path()` **3,258 times from inside the walk**, on **all 654 file-tool
cases**, reaching `self.project_root` -> `self.start_dir`. The real flow is
`config -> engine -> config -> engine -> return`. **My framing said one-way inversion; it is a
round trip.** The call site reads `decide_detailed(allow, deny, ask)` — the callee is an opaque
parameter, so this is structurally invisible to reading.

**(b) `permission_levels_with_provenance()` is not a cheap accessor.** Nothing is cached. 7,781
calls re-derive everything: 12,150 `permission_layers` -> 143,232 `_extract_tool_entries` -> a
large share of **2,501,914** `normalize_entry` calls. "The engine can just walk the levels itself"
is not free.

**(c) Layer construction is takeover-sensitive.** `takeover_mode()` is consulted **12,178 times
from inside the orchestration**. Handing the engine "ordered layers" is not a pure data handoff.

**(d) `_detect_override` is a hot path with a 0.2% yield.** Fires on **58% of cases** (3,107),
invokes the callback a second time 2,678 times, and produces an actual override **7 times across 6
cases**.

**(e) The orchestration is computationally negligible** — 31,401 of 39,856,158 calls, **0.079%**.
Any performance argument about relocation is noise. (The real cost is the PEG parser at ~38% and
`normalize_entry` at 6.3%.)

**(f) A duck-typed test stub fails SILENTLY.** Under the public-rename mutation, 9 `test_hook.py`
tests failed with `JSONDecodeError` rather than `AttributeError` — the hook emitted nothing at all.
A grep finds the stub; only execution shows the failure mode is a silent no-output hook.

## Config knowledge vs decision knowledge — the cleanest output of the trace

| name | verdict |
|---|---|
| `permission_levels_with_provenance`, `has_any_rules`, `resolved_no_match_fallback` | config knowledge (public) |
| `_provenance_for_pattern`, `_entry_for_pattern` | genuinely config knowledge — pure functions over a `ToolPatternLayer`; encode its parallel-array invariant. Need public names, not relocation |
| `_detect_override` | **decision knowledge that migrated.** All five parameters are decision state; touches no config state; invokes the engine callback |
| `_apply_parse_failure_ask_floor`, `_parse_failure_reason` | **decision knowledge** — construct a `ResolvedDecision` and a user-facing reason |
| `_append_provenance` | **decision/presentation knowledge** — reason formatting, one production caller: the loop |
| the no-match fallback tail | **decision policy**, 39 executable lines, 56% of resolutions |

## The corpus gap this exposed, and why it is being closed FIRST

Line coverage of the orchestration is 100%, but **hit distribution is savagely skewed**. Distinct
cases reaching each `no_match_fallback` branch:

`allow` **2,336** : `ask` **34** : `allow_with_warning` **6** : `deny` **6**

Plus: unconfigured-tool branch 32, parse-failure floor firing 14, `ask`-rule provenance 4,
`_detect_override` yielding an override 6. Three defensive lines are reached **zero** times.

D1's real size lives in that tail (39 of 118 executable lines). Refactoring it would be guarded by
thousands of cases for one branch and **single digits for three others**.

**Action taken before any D1 code change: corpus strengthening delegated**, with mutation-based
acceptance (mutate each branch, prove the corpus catches it) rather than case counts. Refactoring
the tail before closing this would be refactoring behind a guard that cannot see it.
