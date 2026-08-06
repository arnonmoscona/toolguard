---
title: TOO-45 ideal picture
type: note
permalink: toolguard/too-45/too-45-ideal-picture
tags:
- task-memory
- TOO-45
- architecture
---

# TOO-45 ideal picture

Drafted 2026-08-04, before the delta. Derived from Arnon's eleven-step flow sketch, but **argued
with rather than transcribed** — his explicit instruction was that the sketch is a way of framing
a problem before committing to structure, not a specification. Where I depart from it, the reason
is stated. Where I add to it, the addition is written as a falsifiable claim so the delta can
kill it.

Not locked in. This is a reasoning aid; contact with the code revises it. Companion:
[[TOO-45 decision log]] (P.3 carries the as-is structural half).

---

## The phases

| # | phase | responsibility |
|---|---|---|
| 1 | **Ingest** | hook event -> normalised invocation (tool, target(s), cwd, session, permission mode) |
| 2 | **Strategy** | pick the governance strategy for the tool |
| 3 | **Decompose** | tool-specific: Bash -> parts via the PEG grammar; file tools -> one target. Yields *decidable units* and, where the grammar cannot cope, *undecidable units* |
| 4 | **Configure** | discover -> parse -> order by authority -> a queryable rule set |
| 5 | **Match** | unit x rules -> matched rules, each with section, provenance, directives |
| 6 | **Unit verdict** | reconcile one unit's matches -> verdict + provenance + directives + warnings |
| 7 | **Consolidate** | units -> one verdict (strictest-wins, floors, documented tie-break) |
| 8 | **Post-decision** | apply directives that only make sense once a winner exists |
| 9 | **Verdict** | one internal type, complete: verdict, provenance, directives, warnings |
| 10 | **Record** | the decision log |
| 11 | **Externalise** | the hook response |

Phases 1-8 are a pipeline. **10 and 11 are not — they are siblings**, two independent consumers
of 9. See claim C1.

---

## Three seams, and one rule that follows from them

The organising principle (see the plan, S1): isolate what changes on **someone else's schedule**.

| seam | phase | external spec |
|---|---|---|
| input | 1 | Claude Code hook event shape |
| output | 11 | Claude Code hook response shape |
| syntax | 4 | Claude native permission syntax |

All three sit at the **runtime/config boundary, never inside the engine**. Which yields a rule
sharp enough to check:

> **The engine must not know what a hook is.** Phases 3-8 should be expressible against
> invocations and rules, with no reference to hook event shapes, response shapes, or JSON.

That is checkable and is claim C4 below.

The syntax seam carries Arnon's constraint: migration from native settings is **transport, not
translation** — a shallow script that does not need to parse native rules, because toolguard
accepts the syntax as a drop-in. A post-overhaul helper may *verify* that what it migrated parses
and raise an alarm if not (e.g. Anthropic introduced new syntax), but must not rewrite entries.

---

## Where I depart from, or add to, the sketch

### C1. Recording and externalising are siblings, not sequence

The sketch lists log (10) then package for the hook (11). I claim they are two consumers of one
verdict, neither downstream of the other.

**Falsifiable:** `hook.py` and `log_writer.py` are **100% co-coupled** — 7 co-changes, the rarer
never changing without the other. If that is because the decision is *rendered twice from
scratch* rather than rendered once and consumed twice, C1 is right and the fix is concrete. If
they are coupled for another reason, C1 is wrong and this table needs revising.

### C2. Config LOAD and config QUERY are different phases

The sketch has one step 4. I split it: discovery/parse/authority-ordering is a load-time concern;
matching and deciding query the result. One module doing both is what fan-in 28-of-67 looks like.

**Falsifiable:** if `config.py`'s 2,905 lines do not separate cleanly along that line — if
matching logic is genuinely entangled with loading — the split is wrong and the real seam is
elsewhere.

### C3. "Undecidable" is an outcome of decomposition, not an error

The grammar either produces a unit it can decide or one it cannot. Both are units; the second
carries a floor. This is a departure worth stating because the alternative — treating
undecidability as an exception threaded through the pipeline — is what produces special cases at
every stage.

**Evidence it matters, found before this was written:** the undecidable floor is applied at
**two sites** (`_apply_undecidable_floor`, and a direct table lookup for `UndecidableSegment`),
which is why a single-site mutation of it changed nothing. Modelling undecidable-ness as a unit
kind makes those two sites one. The existing duplication is documented and defended, so this
claim has to beat a stated argument, not just an accident.

### C4. The engine must not know what a hook is

Stated above. **Falsifiable by grep**: any reference to hook event/response shapes inside phases
3-8. If the engine already honours this, C4 costs nothing and R1 is smaller than budgeted; if it
does not, that is R1's real work and the seam is the deliverable.

### C5. Directives are data on the verdict, with no declared phase

Per Arnon's correction, and independently supported: `additionalContext` is already consumed at
more than one point (accumulated across parts, then rendered into both the response and the log),
so any single-phase tag would be falsified by the only directive that exists. Directives travel
as data on the verdict; where each is consumed is an internal detail, not a rule-level
declaration.

### C6. Warnings are part of the verdict, and their audiences differ

Not in the sketch as a distinct concern, but it falls out of phase 6 preserving rule warnings.
Warnings reach the log (10) whether or not their rule decided; they do not necessarily reach the
response (11). So the verdict carries a warning collection, and the two consumers filter it
differently. Arnon flagged the noise trade-off in the ticket — that is a policy on one field, not
an architectural question, which is the point of making it a field.

---

## Mapping onto layers

```
foundation   constants, paths, patterns, issues, normalisation
config       load + represent + query          <- SEAM: native syntax
engine       decompose, match, decide, consolidate, directives
api          the public surface                <- proposed (R6)
runtime      ingest, record, externalise       <- SEAMS: input, output
tooling      tools/, scripts/
support      testing/
```

Two things this makes explicit:

- **The seams are all at the edges.** Nothing in `engine` faces an external spec. That is what
  makes an emergency spec change survivable — it is C4 restated as a layer property.
- **`api` sits between engine and runtime deliberately**, so `runtime` consumes the same surface
  the tooling does. An interface only its second-class consumers use drifts from what the engine
  really does, because the primary path bypasses it.

---

## What would falsify the whole picture

If the delta shows the code is organised along a *different* clean axis — one that also explains
the co-change data — then this picture is the thing that is wrong, not the code. Recording that
now, before seeing the delta, so the possibility is live rather than retrofitted.

The specific thing to watch for: this picture is derived from **one central use case** (govern a
Bash command). The tooling is now the same size as the engine (31 modules vs 28). A picture that
explains the engine and says nothing about half the codebase is not yet an architecture — it is
half of one. R6 is where that gets tested, and it is the reason R6's size cannot be judged until
the delta exists.

---

# First contact, 2026-08-04 — two claims tested immediately

## C4 is ALREADY TRUE, and that shrinks R1

Searched the engine (`compound`, `resolve`, `permissions`, `config`, `rule_entry`, `rule_sort`)
for hook event/response shapes. **Two hits, both docstring prose** —
`compound.py:521` and `config.py:1659` each *mention* `permissionDecisionReason` in
documentation. Zero code references.

So the engine genuinely does not know what a hook is. The layer property I wrote as an
aspiration already holds.

**Consequence: R1's work is not what the plan implied.** There is no hook knowledge to extract
from the engine — that axis is already clean. R1 is entirely about the *multiplicity of verdict
types* and about what happens at the boundary. Which is C1.

## C1 is CONFIRMED, with a mechanism

`log_writer.log_command()` takes **eleven loose parameters**:

```
command_str, status, violated_rules, log_dir, extra_info, config,
matched_rule, note, permission_mode, additional_context, log_format
```

Not a verdict. So `hook.py` must **decompose the verdict into eleven arguments** for the log, and
**separately reassemble** it into the response dict for `create_hook_output`. The decision is
rendered twice, from scratch, in two files.

That is the mechanism behind the 100% co-coupling of `hook.py` and `log_writer.py`, and it is
mechanical rather than cultural: **any new field on a verdict requires a new parameter here AND a
new key there, always in the same change.** The files cannot change independently because the
interface between them is "spread the verdict out by hand".

It also explains the enrichment footprint directly. `additional_context` is parameter #10 on
`log_command`, *and* a key in `create_hook_output`, *and* a field on four verdict types. Adding a
second directive repeats all of it.

**Concrete R1 deliverable, now stated in one sentence:** make both consumers take the verdict
object, so a new field is added once. That is precisely what the canary measures, which is a good
sign the two are aimed at the same thing.

## Status of the six claims

| claim | status |
|---|---|
| C1 record/externalise are siblings | **CONFIRMED** — rendered twice from loose parts |
| C2 config load vs query | untested — needs the delta |
| C3 undecidable as a unit kind | supported by the two-site duplication; must still beat a documented counter-argument |
| C4 engine must not know what a hook is | **ALREADY TRUE** — costs nothing, shrinks R1 |
| C5 directives are data, no declared phase | settled by argument, unchanged |
| C6 warnings on the verdict, audiences differ | untested |

Two of six survived first contact with evidence, one was already satisfied. Recording that the
picture was drafted *before* these checks, so the confirmations are predictions rather than
retrofits.

---

# C2 REVISED, 2026-08-04 — and the revision is the main finding of P3 so far

My drafted C2 said config **load** and config **query** are two phases wrongly fused. Testing it
showed that split is real but secondary, and that something larger is going on. Recording the
original claim as partly wrong rather than quietly upgrading it.

## What the structure actually shows

`config.py` splits roughly as expected at first glance:

- lines 166-827: load and discovery (parse, discover levels, rules dirs, shadowing) — ~660 lines
- line 874: `class Configuration`, 33 methods, ~1,640 lines
- lines 2515-2864: more parsing plus `load_configuration`

So load-vs-query is *already* mostly separated. But `Configuration`'s 33 methods are not one
responsibility. Classified:

| group | methods |
|---|---|
| config query (legitimate) | `project_root`, `governed_tools`, `takeover_mode`, `hard_deny*`, `permission_layers`, `permission_levels_with_provenance`, `_provenance_for_pattern`, `_entry_for_pattern`, `has_any_rules`, `scalar`, `allow_deny_for`, `describe_*` ... |
| fallback semantics (arguably query) | `_resolve_fallback_setting`, `resolved_no_match_fallback`, `resolved_undecidable_fallback`, `unrecognized_fallback_settings` |
| **decision engine (does not belong here)** | **`resolve_permission_detailed`, `_resolve_permission_detailed_unclamped`, `apply_parse_failure_floor`, `_apply_parse_failure_ask_floor`, `_parse_failure_reason`** |
| validation | `validation_issues` (~224 lines) |

## The inversion

`resolve.py:560` and `:684`:

```python
resolved = config.resolve_permission_detailed(tool_name, _decide_detailed)
```

The engine passes a **callback into the config object**, and `Configuration` orchestrates the
hierarchy walk, invoking engine logic from inside. Control flow:

```
hook -> resolve -> config.resolve_permission_detailed(callback) -> callback -> permissions/compound
```

**`Configuration` is not a configuration object. It is the decision orchestrator.**

## This one fact explains every measurement that previously disagreed

- **`config` fan-in 28 of 67.** Everything that needs a decision must import `config`, because the
  decision entry point lives on it. The hub is not a data hub; it is a control hub.
- **`compound`/`permissions`/`resolve` fan-in 2.** They are not imported by consumers — they are
  reached *through* the callback. The import graph cannot see the traffic.
- **`compound.py` <-> `config.py` 100% co-change**, `config` <-> `permissions` 89%. Any change to
  how a leaf is decided touches both the callback implementation and the orchestration that calls
  it. They are two halves of one mechanism.
- **The structure/history disagreement recorded in decision-log P.3.** Structure said "isolated
  leaf modules", history said "one module in three files". Both were right: inversion of control
  makes the dependency real but invisible to imports.

Note `compound.py` does not import `config` at all — its imports are `parser` and `permissions`.
The coupling is entirely through the callback, which is precisely why it does not show up
structurally.

## Against the ideal picture

Walking the hierarchy, applying authority order and picking a winner are phases **5-7**
(match / unit verdict / consolidate) — the **engine**. Phase 4 (configure) should *provide*
ordered rule layers and answer questions about them. It should not run the decision.

So the ideal-picture correction is: **`Configuration` provides ordered layers; the engine walks
them.** Not a callback handed to config, but config handing rules to the engine.

## Consequences for the plan

1. **This is probably a step, and it is not currently one.** It is not R6 (that is the
   tooling boundary), not R2 (rule representation), not R1 (verdict type). Candidate: *the engine
   owns the decision; config answers questions*. Sizing needs the fitness tool.
2. **It plausibly outranks R6 in leverage**, since it is the mechanism behind the co-change hubs
   that motivated the whole ticket. Deferred to the step-order proposal at CP1.
3. **It explains the enrichment footprint from a second direction.** A new directive must be
   threaded through both the orchestration in `config` and the callback in `resolve`/`compound`,
   on top of the two renderings found in C1.
4. **R6's predicate needs care.** "No `tools/` module imports a private name from `config`..."
   would be satisfiable while the inversion stands, because the problem is not what is imported.

## Confidence and what could still overturn it

Read from call sites and the method inventory, not yet from a full call graph. The fitness tool's
import and call analysis is the check. Specifically: if `resolve_permission_detailed` turns out to
be a thin ordered-iteration helper rather than real orchestration, this is overstated and the
finding shrinks to "a badly-placed helper". The 150-line body and the parse-failure floor living
beside it argue otherwise, but that is the falsifier to look for.
