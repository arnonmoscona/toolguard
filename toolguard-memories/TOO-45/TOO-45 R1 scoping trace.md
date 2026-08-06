---
title: TOO-45 R1 scoping trace
type: note
permalink: toolguard/too-45/too-45-r1-scoping-trace
tags:
- task-memory
- TOO-45
- architecture
- R1
---

# TOO-45 R1 scoping trace

2026-08-05. MEASURE-AND-PROPOSE scope of step R1. Nothing in production code was changed: every probe that mutated a repository file backed the original bytes up first and restored them in a `finally` block with sha256 verification. **Restoration verified: `git status --porcelain` is byte-identical to the baseline captured before the first probe, zero residual mutation markers in `toolguard/`, suite 2,325 OK, corpus 6,401 in-process + 61 e2e with no differences, `ruff check --no-cache` clean.** Probes preserved under `scratchpad/r1-probes/`, backups and per-mutation suite output under `scratchpad/r1-backups/`.

Every claim below is labelled **DEMONSTRATED BY EXECUTION** or **INFERRED BY READING**. The distinction earns its keep here: the R1 predicate turned out to be wrong in two directions at once, and reading alone would have confirmed it.

---

## Lead: the recommended split

R1 is worth doing and is bigger than "one verdict type", but **its stated justification is aimed at the wrong seam**. Measured: the *output* seam (phase 11) is already clean — `create_hook_output` takes three arguments and, on 6,401 of 6,401 corpus cases, receives the resolution object's own `decision` / `reason` / `additional_context` verbatim. Nothing is re-derived there. The mess is entirely on the *record* seam (phase 10), and the audit log is not merely awkwardly fed — **it is losing records**. R1's justification should be restated as the audit seam.

| # | stage | affected tests | independent? |
|---|---|---:|---|
| **R1b** | fix the two instruments *first* (`find_verdict_types`, `find_iter_shims`, and add an occurrence count to the enrichment footprint) | 0 production risk | yes — do before anything else |
| **R1a** | delete both `__iter__` shims + the 2 tests that pin them + 8 incidental unpackings | **10** | yes |
| **R1c** | one runtime verdict type: `ResolvedDecision` + `BashResolution` + `FileResolution` collapse into one carrying `tool` and `target` | **~110 gross, dominated by one import cascade** | no — R1d depends on it |
| **R1d** | both consumers take objects: `log_command(verdict, invocation, settings)`, `create_hook_output(verdict)` | 7 production call sites + 41 test call sites | after R1c |
| **R1e** | the compound audit breakdown comes from `sub_matches`, not from a regex over the reason prose | behaviour-changing; needs golden acknowledgement | after R1c; **flag to Arnon** |
| *deferred* | unify `tools.decision.Decision` with the runtime verdict | 32 | R6 territory |

**R1e is the one to escalate.** It was scoped in the plan as a cosmetic follow-up ("audit-log format changed in R3 ... log as an additional step after the main refactor"). It is not cosmetic. It is a defect fix — see the audit-loss finding below.

---

## Blast-radius table (DEMONSTRATED BY EXECUTION)

Method as in the D1a trace: rename the symbol across `toolguard/**/*.py` **only** (tests untouched), run the full suite, count, restore, verify sha256. Baseline is 2,325 tests, 0 failures. "Affected" = tests that failed **plus** tests that never ran because a test module failed to import — a pure rename usually takes out a whole module at import time, and counting only the reported failures understates it badly.

| probe | ran | not run | errors | **affected** | what actually broke |
|---|---:|---:|---:|---:|---|
| delete both `__iter__` shims (real deletion, not a rename) | 2325 | 0 | 10 | **10** | 8 incidental `a, b, c = resolver(...)` unpackings in `test_hard_deny` / `test_hierarchical`, plus 2 tests that exist solely to pin the shims |
| rename `BashResolution` | 2245 | 80 | 1 | **81** | `test.unit.test_resolve` unloadable |
| rename `FileResolution` | 2245 | 80 | 1 | **81** | `test.unit.test_resolve` unloadable (same module — the two are **not additive**) |
| rename `ResolvedDecision` | 2300 | 25 | 3 | **28** | `test.unit.test_logging_streams` unloadable + 2 in `test_architecture.TestReExportIdentity` |
| rename `SubMatch` | 2300 | 25 | 1 | **26** | `test.unit.test_tools_decision` unloadable |
| rename `Decision` (tools) | 2295 | 30 | 2 | **32** | `test_tools_decision` + `test_verdict_corpus` unloadable |
| rename `log_command` | — | — | 1 | **2325 (all)** | `test/unit/__init__.py` calls `install()` in `_real_log_dir_guard.py`, which monkeypatches `log_writer.log_command`; the whole suite dies at package import |

Two things the table teaches that a static grep does not.

**The class renames are not additive.** `BashResolution` and `FileResolution` both take down `test_resolve.py` and its 80 tests, so unifying both is ~81 affected, not 162. Adding `ResolvedDecision` brings a different module. A realistic R1c is roughly **110 affected tests, of which ~105 are a mechanical import/name edit** — the same shape D1a found, where 44 of 47 breaks were coupled to a name rather than to machinery.

**`log_command` cannot be probed by rename at all**, and the reason is itself a finding: the test package's `__init__` monkeypatches it by name to guard against tests writing into the real log directory. Any R1d that renames or relocates `log_command` must update `test/unit/_real_log_dir_guard.py:201` in the same commit or the entire suite becomes unrunnable with a single `AttributeError` and no useful signal. Static call-site counts (DEMONSTRATED BY EXECUTION, `grep` verified against the probe): **7 production call sites, all in `hook.py`**; 39 direct calls in `test_log_writer.py`; 2 in the guard. `create_hook_output`: 9 production sites, 12 in `test_hook.py`.

---

## Q1. The predicate's list is dishonest in BOTH directions

`find_verdict_types` matches on the name substrings `decision` / `resolution` / `verdict` (`tools/architecture_fitness.py:623`) — a pure name-pattern rule, INFERRED BY READING and then confirmed by the census below. It over-counts and under-counts simultaneously.

**Runtime census — DEMONSTRATED BY EXECUTION.** Every one of the 7 classes had its `__init__` instrumented; the counts below are constructions during a full replay of all 6,401 corpus cases through `hook._handle_command_tool` / `_handle_file_path_tool`, and separately over the entire 2,325-test suite.

| class | fields | built on the hook decision path | built anywhere in the suite | constructed by | verdict? |
|---|---:|---:|---:|---|---|
| `ResolvedDecision` | 7 | 9,102 | 10,850 | `permission_resolution._resolve_unclamped` / `_apply_ask_floor` | **YES** |
| `BashResolution` | 8 | 5,631 | 7,272 | `resolve.resolve_bash_permission_detailed` | **YES** |
| `FileResolution` | 7 | 770 | 847 | `resolve.resolve_file_path_permission_detailed` | **YES** |
| `Decision` | 8 | **0** | 7,973 | `tools.decision._decide_bash` / `_decide_file_path` | **YES**, but on the tooling path only |
| `ProjectRootResolution` | 4 | **0** | 145 | `path_utils.resolve_project_root` | **NO — false positive** |
| `LedgerDecision` | 8 | **0** | 26 | `tools.decision_ledger.new_decision` | **NO — false positive** |
| `SingleDecision` | 3 | **0** | 5 | `tools.replay.replay_single` | **NO — it *contains* a verdict** |

`ProjectRootResolution` carries `status, root, candidates, reason` — a migration-gate boundary classification, zero fields in common with a permission verdict, and it is never constructed while deciding a permission. `LedgerDecision` carries `kind, family_id, target, decision, rationale, recorded_at, toolguard_version, level` — a persisted maintenance-ledger row whose `decision` is a user's curation choice. `SingleDecision` is `(LogEntry, Decision, matches_observed)` — a replay result row that holds a verdict alongside the observed outcome.

**Corrected list: 4 genuine permission-verdict types, not 7** — and only 3 of those 4 exist on the hook path.

**The under-count is the more interesting half.** A structural scan for classes declaring a field named `decision`/`verdict` found one the name rule misses entirely:

> **`SubMatch` (`resolve.py:68`) — fields `sub_command, decision, matched_rule, provenance`, constructed 8,314 times on the hook decision path.** That is precisely the ideal picture's phase-6 unit verdict, and the predicate is blind to it because its name contains none of the three magic words.

**`find_iter_shims` is wrong too, and in the way that matters most.** It reports "2 `__iter__` shims, **both with 0 callers**" — the plan and the delta both call this a "free deletion". It counts callers only within `toolguard/` (`iter_source_files(toolguard_dir)`). **Deleting both shims breaks 10 tests with `TypeError: cannot unpack non-iterable ... object`** (DEMONSTRATED BY EXECUTION). The callers are real; they live in the test suite. Free deletion is a 10-test deletion.

**Verdict on the instrument: `find_verdict_types` and `find_iter_shims` both need fixing, and I have not fixed either.** Recommendations for the implementation step:

- classify by **structure**, not by name: a class is a verdict candidate when it declares a field named `decision`/`verdict` **and** at least two of `{reason, provenance, matched_rule, additional_context}`. That rule, run over the tree, returns exactly the four genuine types plus `SubMatch`, and drops all three false positives — which is the point, since it moves the count in both directions.
- keep an explicit, **commented** exclusion list for anything the structural rule still catches wrongly, with a stated reason per entry, so an exclusion the operator cannot see never happens again.
- `find_iter_shims` must count callers in `test/` as well, and report them separately from production callers. A shim with zero production callers and ten test callers is a different (and much cheaper) fact than a shim with zero callers, but it is not the same fact.

This is the **third instrument on this ticket found wrong at the moment of use** (after the raw-substring enrichment scan and the unreconstructable "7 files" canary reading). The standing rule holds: predicates scope work, they are not evidence.

---

## Q2. C1 — the conclusion survives, the mechanism does not

C1 says the decision is *rendered twice from scratch*, and that this is why `hook.py` and `log_writer.py` are 100% co-coupled. **The stated mechanism is FALSE on the response side and only partly true on the log side.** Reporting the disproof, because the ideal picture is falsifiable on purpose.

Method (DEMONSTRATED BY EXECUTION): replay all 6,401 corpus cases through the two `hook.py` handlers with `log_command` replaced by a recorder and the resolver wrapped to capture the resolution object, then classify every recorded `log_command` argument against the resolution object that produced it. 7,074 `log_command` calls over 6,401 cases.

**The response path is a faithful projection, not a rendering.**

> `decision`, `reason`, `additional_context` reaching `create_hook_output` are the resolution object's own field values, verbatim, on **6,401 of 6,401** cases. Zero divergences.

**The log path is a decomposition of the *same object*, with three independent adjustment rules and one genuine re-derivation.**

| `log_command` argument | same as the resolution's field | differs |
|---|---:|---|
| `additional_context` | 7,074 / 7,074 | — |
| `provenance` | 7,040 / 7,074 | 34 **dropped** — the `ask` branch of `_log_non_allow_decision` passes no provenance at all |
| `matched_rule` | 4,156 / 7,074 | **2,777 present in the log where the resolution had `None`**; 136 dropped; 5 a different value |
| `command_str` | 6,138 / 7,074 is the tool target | **936 are sub-command strings recovered by regex from the reason prose** |

So the real mechanism has three parts, and only the third is a second rendering:

1. **The verdict dies at the handler boundary.** `_handle_command_tool` and `_handle_file_path_tool` are annotated `-> Tuple[str, str, Optional[str]]`. They discard **5 of `BashResolution`'s 8 fields** and **4 of `FileResolution`'s 7** before returning. `main()` then hands that 3-tuple to `create_hook_output`. The response is faithful because it is a projection of a projection — there is nothing left to be unfaithful about. That is a *narrower* seam than C1 describes, and a better one to attack.
2. **`log_command`'s 12 loose parameters force a manual decomposition**, with three hand-written adjustment rules living in `hook.py` (`_reason_suffix_or_placeholder`, the `logged_provenance if suffix == matched_rule` suppression, and the `ask` branch that silently drops provenance).
3. **The compound audit breakdown is genuinely re-derived from prose** — `_parse_compound_match_details` regex-parses `"All N sub-commands allowed: [...]"` back apart. This is the only true "rendered twice" on either path, it exists only on the log side, and it is where the damage is.

**Fields where the two paths could disagree today:** only `additional_context` reaches both, it is the same object on both, so it cannot disagree in *value* — but it is rendered differently by design (full text in the JSON response, word-capped preview via `_preview_additional_context` in the log). Everything else the log carries — `matched_rule`, `provenance`, `violated_rules`, `note`, `status` — never reaches the response at all. **The two consumers are not two renderings of one verdict. They are one lossy projection and one wide decomposition, and they have almost no surface in common.** C1's picture of symmetric siblings should be corrected to that.

**What C1 misses entirely, and it is larger than what it names.** 16 functions in `toolguard/` return a bare `(str, str, ...)` verdict tuple — **6 in `compound.py`**, 3 in `hook.py`, plus `permission_resolution`, `permissions`, and 4 in tooling. `compound.py` threads `(decision, reason, additional_context, fallback_warning)` as an unnamed quad through `_resolve_leaf_detailed` → `_combine_strictest` → `resolve_compound_permission_detailed`. That is the "one verdict end-to-end" problem in its purest form and **the predicate cannot see a single one of them**, because they are not classes and have no names.

### The finding that changes R1's priority: the prose round-trip is losing audit records

DEMONSTRATED BY EXECUTION, over the whole corpus:

> **813 of 975 compound allow cases (83%) write fewer audit entries than the command had sub-commands. 1,943 sub-commands ran and received no audit-log entry at all.** 811 of the 813 cases are in the `realistic` fixture — the one built from real traffic.

Mechanism, confirmed against the live reason strings: `_COMPOUND_MATCH_PATTERN` splits the reason on `", "` and keeps only segments containing `" -> "`. A sub-command resolved by `no_match_fallback` contributes a segment with no `" -> "` in it (e.g. `Command does not match any allow patterns; allowed with no warning by no_match_fallback=allow ...`), so it is silently discarded and never logged. Concrete cases:

- `ls -la && echo done` — 2 sub-commands, **1** audit entry.
- `ls -la | wc -l` — 2 sub-commands, **1** audit entry.
- a 10-sub-command real-traffic block (`echo ... && diff ... && uv run python -c ... && toolguard --eval ...`) — 10 sub-commands, **1** audit entry.

Two more artefacts of the same round trip: **79 logged `matched_rule` values carry a stray trailing `]`** (`'[fallback allow -- no rule matched]]'`) from the greedy `(.+)` capture. And one case was observed where the reason says "All 6 sub-commands allowed" while `sub_matches` holds 7 — I am **not** claiming that as a defect, only flagging it as its own check, because I did not trace where the count comes from.

**`hook.py`'s own load-bearing claim about this was tested, not inherited.** `_parse_compound_match_details`'s docstring argues `sub_matches` "is NOT a safe substitute", citing two TOO-19 m5 regression tests. Measured over every compound allow whose reason parses (402 cases): **240 differ in arity — `sub_matches` always has MORE entries** — and 162 differ in `matched_rule`, because the prose carries the provenance suffix glued into the rule text while `sub_matches` carries the bare pattern. So the docstring is right that the two are not drop-in interchangeable, but **the direction is the opposite of what it implies: the structured data is the complete one and the prose is the lossy one.** The genuine blocker it names — an ask-floor leaf whose truncated stub matched a real rule — is a narrow case that needs *one field on the unit verdict*, not a parse of a sentence.

---

## Q3. What the single verdict type must carry

Derived from the union of the four genuine types (DEMONSTRATED BY EXECUTION — field lists read off `__dataclass_fields__` at runtime) and from the executed classification of `log_command`'s 12 parameters.

| field | on the verdict? | evidence |
|---|---|---|
| `decision` / `verdict` | **yes** | all four types; consumed by both paths |
| `reason` | **yes** | all four; the response's `permissionDecisionReason` and the log's `note` |
| `provenance` | **yes** | all four; 7,040 log calls carry it |
| `matched_rule` | **yes** | all four; the audit record's core |
| `additional_context` | **yes** | all four; both consumers |
| `fallback_warning` | **yes** | three of four; routes to the WARNING stream |
| `override` / `overrides` | **yes**, reconciled | `BashResolution` has a list, `FileResolution`/`ResolvedDecision` a singular — a unified type has to pick, and the list generalises |
| `sub_matches` (unit verdicts) | **yes** | 8,314 constructions; the *only* complete record of what a compound did |
| `tool`, `target` | **yes** | `Decision` already carries them; the runtime types do not, which is exactly why `log_command` needs a separate `command_str` |
| escape-hatch kind | **new field** | today recovered from prose by `fallback_kind_for_reason`; R1e needs it structured |

**And these must NOT go on the verdict** — they are rendering concerns of one consumer, established by classifying `log_command`'s 12 parameters against the trace:

- **verdict data (3):** `matched_rule`, `provenance`, `additional_context`
- **invocation / ingest data (3):** `command_str`, `extra_info` (agent), `permission_mode` — these are phase-1 facts about the *call*, not about the decision
- **environment (3):** `log_dir`, `config`, `log_format`
- **log-rendering derivations (3):** `status` (the decision remapped to `executed`/`refused`/`ask`), `violated_rules` (derived from `matched_rule`, falling back to the whole reason on 40 calls), `note` (`== reason` on all 164 ask calls)

**Consequence worth stating plainly: a verdict object alone does not get `log_command` under 8 arguments.** It needs verdict + invocation + environment. That is 3 objects, or verdict + invocation + 3 environment parameters = 5. Either way it clears `max-args = 8`.

**Which of the 7 are subsumed:** `ResolvedDecision`, `BashResolution`, `FileResolution` collapse into one. **`Decision` should become that same type** — argued rather than assumed: it already carries `tool` and `target`, which is precisely the field the log path has to reconstruct today, so its shape is *closer to correct* than the runtime pair's. But unifying it costs 32 tests and lands in R6's api-surface territory, so it is deferred with the explicit condition that **R1c must put `tool`/`target` on the runtime verdict anyway**, or R1d cannot be done cleanly.

**Which stay, and why (arguing it, per the brief):** `SubMatch` stays, renamed to something honest like `UnitVerdict` — it is a genuinely different altitude (phase 6, one decidable unit) and collapsing it into the compound verdict would destroy the only structured record of a compound command. `ProjectRootResolution` is not a permission verdict in any sense and stays where it is. `LedgerDecision` and `SingleDecision` stay **and the argument for keeping them is not just "they're tooling"**: `LedgerDecision` is a persisted on-disk schema and `SingleDecision` is a replay row pairing a verdict with the *observed* historical outcome. Folding either into the engine's verdict type would couple a file format and a diagnostic report shape to the engine's internal decision representation — the wrong direction, and exactly the kind of thing R6 exists to prevent.

---

## Q4. Recommended split, with reasoning

**R1b first — fix the instruments before touching production.** This is D1a's "item J" lesson applied one step earlier: an instrument that counts wrong cannot score a change-cost step. Three fixes: structural `find_verdict_types`, test-aware `find_iter_shims`, and an occurrence count on the enrichment footprint (see Q5). Zero production risk, and it changes the R1 baseline from "7 types / 2 free-to-delete shims" to "5 types (4 verdicts + 1 unit verdict) / 2 shims with 10 test callers", which is the number R1 should actually be scored against.

**R1a — delete the shims.** 10 tests: 2 exist only to pin the shims and are deleted with them; 8 are incidental 3-tuple unpackings in `test_hard_deny` / `test_hierarchical` that become attribute access. Genuinely independent of every other stage. **It must not be allowed to count as R1 progress on its own** — it changes the predicate from 2 to 0 and improves nothing about either seam.

**R1c — one runtime verdict type.** ~110 affected tests, of which ~105 are import/name churn concentrated in `test_resolve.py` (80) and `test_logging_streams.py` (25). The D1a lesson applies directly: high gross count, low real risk, because the corpus is the equivalence oracle and it is watching. Carry `tool` and `target` on it even though nothing consumes them yet — R1d needs them.

**R1d — both consumers take objects.** 7 production call sites and 41 test call sites. `test/unit/_real_log_dir_guard.py:201` must move in the same commit. This is where both `# noqa: PLR0913` markers come off and where the enrichment occurrence count actually falls.

**R1e — structured compound audit breakdown.** Fixes 1,943 missing audit entries and removes the last `hook.py` reason-parse site (which R3 left behind and which `--predicates` still reports). Needs one new field on the unit verdict for the escape-hatch classification. **This is behaviour-changing** — the log gains entries — so it needs the corpus's two-tier golden acknowledgement, which is exactly what that mechanism was built for. Arnon's standing call was that audit-log format changes go in a separate step after the main refactor; this should be that step, and he should be told it has become a defect fix rather than a formatting change.

---

## Q5. Predicted acceptance numbers — and a warning about the pre-registered metric

**Baseline, measured on the current settled tree (DEMONSTRATED BY EXECUTION): enrichment footprint 9 coupled / 6 prose-only.**

I also counted the identifier-level occurrences the file count hides. **59 code lines across the 9 coupled files:** `hook.py` 21, `compound.py` 11, `resolve.py` 8, `log_writer.py` 7, `testing/sandbox.py` 4, `permission_resolution.py` 3, `tools/decision.py` 3, `config_types.py` 1, `rule_entry.py` 1.

Classifying those 59 by what they *do*:

- **irreducible** — `config_types` declares the field (1), `rule_entry` is the config-syntax accessor (1), `permission_resolution` produces the value (3), `log_writer` renders it (4 of its 7), `hook` names the JSON key (2 of its 21), `testing/sandbox` renders it (4). That is **~15 lines across 6 files that must survive any refactor.**
- **pure threading** — the other ~44, of which `hook.py`'s 17 and `compound.py`'s 11 are the bulk.

**Prediction: coupled 9 → 8, prose-only 6 → 7.** `tools/decision` drops out only if `Decision` is unified in the same step (deferred), so realistically **the file count moves by at most one, and may not move at all.**

**That is a problem with the instrument, not with R1, and it needs saying before R1 starts rather than after.** The coupled-file count is bounded below at 7 by files that must legitimately name enrichment — declare, produce, render, or sit on the syntax seam. A step that removes 44 of 59 threading references and leaves the file count at 8 would be scored **flat**, and R1 has been pre-committed as a change-cost step where flat is a genuine failure. That would be a false negative produced by the same class of defect that made the metric over-count before it was tokenized.

**Recommendation, and it must land before R1 for the same reason the ruff config did: add an identifier-OCCURRENCE count (per file and total) alongside the file count.** Current value 59. **Predicted after R1c + R1d: ~28-32, with `hook.py` going 21 → ~4.** That is the change-cost delta R1 is actually justified by, it is measurable today, and pre-registering it is what makes the eventual number a score rather than a rationalisation.

**The `# noqa: PLR0913` prediction: both markers come off.** There are two in R1's scope — `log_writer.log_command` (12 args, the pre-registered acceptance test) and `hook._log_non_allow_decision` (9 args, "feeds log_command; see TOO-45 R1"). Q3's decomposition puts `log_command` at 5 parameters, comfortably under `max-args = 8`, and `_log_non_allow_decision` collapses with it. RUF100 makes this self-enforcing — leaving either marker behind fails the lint. The other two PLR0913 markers (`scripts/migrate_permissions._apply_migration`, `tools/consolidate._check_family1_safe`) are explicitly out of scope and stay.

---

## Q6. The gaming move for each stage

Named in advance, per the plan's rule that a satisfied predicate plus an unconvinced judge means the predicate was wrong.

- **R1b (instruments).** Fix `find_verdict_types` by excluding `tools/` wholesale. The count drops from 7 to 3, the predicate looks closer to passing, and no code changed. **Tell:** a corrected instrument must *add* `SubMatch`, not only remove three names. An instrument revision that only ever reduces the count is fitting the metric to the code.
- **R1a (shims).** Delete the shims and delete the two tests that pin them, declare the `__iter__` component green. It moves 2 → 0 and changes nothing about either seam. **Tell:** it is a one-line predicate improvement with zero effect on the 59-line enrichment count or on either `noqa`.
- **R1c (one verdict type).** Introduce a `Verdict` base class and have all three existing classes inherit from it. "Exactly one type represents a permission verdict" is arguable, three classes still exist, three are still constructed. **Tell:** re-run the runtime census. If three distinct classes are still instantiated on the decision path (9,102 / 5,631 / 770 today), nothing happened. Constructions, not `isinstance` relationships, are the measurement.
- **R1d (consumers take objects).** Bundle the 12 parameters into a `LogCommandArgs` dataclass with 12 fields. Argument count goes to 1, PLR0913 disappears, RUF100 is satisfied — and every field still has to be named at the call site, so the enrichment occurrence count barely moves. **This is the direct analogue of R3's "consolidate three parse sites into one helper" and it is the single most likely thing to actually happen.** Tell: the acceptance test is the occurrence count and the disappearance of the three adjustment rules in `hook.py`, never the argument count.
- **R1e (structured breakdown).** Keep `_parse_compound_match_details` and add a structured path beside it, then declare the structured path authoritative. **Tell:** assert `_COMPOUND_MATCH_PATTERN` is *deleted*, and assert on the corpus that the number of audit entries equals `len(sub_matches)` for every compound allow. Today that assertion fails on 813 of 975 cases; it is a ready-made acceptance test and it should be written before the code.

---

## Restoration statement

Every repository file touched by a probe was copied to `scratchpad/r1-backups/<mutation>/` before mutation and restored from that copy in a `finally` block, with the restored file's sha256 compared to the pre-mutation value; all restores reported `verified: True`. No `git checkout` / `restore` / `stash` / `reset` was used, no git write of any kind was issued, no commit was made, and nothing outside the repository was edited. The repository was not copied anywhere. Final state: `git status --porcelain` identical to the baseline captured before the first probe (both saved under `r1-backups/`), zero residual `ZZ` mutation markers in `toolguard/`, `ruff check --no-cache .` clean, suite **2,325 OK**, corpus **6,401 + 61, no differences**.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- tests [[TOO-45 ideal picture]]
- extends [[TOO-45 delta - as-is against ideal]]
- informs [[TOO-45 decision log]]
