---
title: Architectural delta judge - back-test results
type: note
permalink: toolguard/too-45/reports/architecture-judge-backtest
tags:
- task-memory
- TOO-45
- measurement
- retro
---

# Architectural delta judge — back-test, 2026-08-10

Tests Arnon's hypothesis: *a judge whose only task is architecture will weight the architecture training data more heavily than a coder or a general reviewer does, because the dominant causes of the weakness are attention dilution and task focus rather than capability.*

Eight blind judges, one brief, one subject each. **Arm A** = the five committed punch-list diffs (false-positive control). **Arm B** = the three surviving pre-implementation specs (the hypothesis test — Arnon caught his findings at proposal stage, so the merged commits no longer contain them). Scoring key pre-registered before any report was read.

## Ground truth

| id | subject | defect | result |
|---|---|---|---|
| T1 | B1 — #04 spec | `hook.py`'s three fail-open handlers explicitly excluded from the reporter that exists to remove stream decisions from call sites | **miss** |
| T2 | B2 — #15 spec | `migrate()` keeps `-> int`; spec asks only for a named constant | **hit**, primary axis 9 as predicted |
| T3 | B3 — #10 spec | closed registry cannot describe a user-declared MCP tool | **hit**, primary axis 8 |
| T4 | A5 — #10 commit | same defect, still present in committed code | **miss** |

**2 of 4 — and both hits are in arm B.** T4 is literally T3 in a different substrate and was missed there, which is the sharpest structural result of the exercise: **the judge sees architectural defects in proposals and not in diffs.** That matches where Arnon caught all of his — from proposals, never from reading merged code.

### Why T1 was missed, and the fix

The spec deferred the fail-open *to a named successor item*. The brief said an exclusion is a finding "unless justified by something other than effort", and a named successor item reads as exactly such a justification. The judge applied an underspecified rule correctly.

**Brief fix**: an exclusion assigned to another item must still be tested with *"are these actually one item?"* — which is precisely what Arnon's question established. Add to the scope-completeness rule.

## Live defects found in committed, reviewed code

Ranked. The first four are verified against HEAD, not taken on the judge's word.

1. **`migrate()` discards the structured decline reason, and `auto_migrate` then states a false cause** (A4). `permission_migration.py:1250` branches on `e.reason`, renders prose, returns one `DECLINED_LOCKED` for all four causes. `auto_migrate.py:174` announces *"Another migration is already running for this project"* — false when the cause is an unwritable lock dir or a platform with no locking primitive. **And the day's `once_per` claim is consumed**, silently disabling auto-migration until tomorrow. The comment defending that ("the other process holding the lock is doing the work itself") is true only of the timeout branch. This is the project's own prose-is-output rule, one level up from where TOO-45 removed it.
2. **Dynamic dispatch hides a call edge from the repo's own semantic tooling** (A3). `_ROUTING` stores `log_fn_name: str` and `_dispatch` does `getattr(error_log, name)`, so `log_warning`/`log_error` have no static caller from the reporter — pyright's `incomingCalls` and `callers_of` both see zero. Directly contrary to Arnon's stated principle that what static analysis cannot see, a reader cannot either. Introduced to keep `patch("toolguard.error_log.log_warning")` working: test mechanics driving production indirection.
3. **`hook.py` builds the Reporter and keeps four hand-rolled `log_error`/`log_warning` calls** (A3), one of which (`hook.py:96-100`) is a second copy of the severity routing table. Verified: those four are the only remaining static callers in the package. The mechanism's own owner is the largest remaining instance of the problem it was built to remove.
4. **`once_per` re-introduced an invisible upward runtime edge** (A2). `auto_migrate` (config) hands `_migrate` to `OncePer.run`, whose body is `return action()`, so an observability module executes config-layer code at runtime with no import edge. `--layers` reports clean. Same class as the cycle #03 removed — introduced in #01, before the reviewer gained the measure-the-runtime-topology instruction.
5. **`is_builtin` conflates structural description with enforcement policy** (A5), and `test_tool_spec.py:82` pins `DEFAULT_GOVERNED_TOOLS == BUILTIN_TOOLS`, so the first tool that should be *understood* without being *governed by default* fails a test. This makes TOO-51 harder, not easier.
6. **`TOOLS_BY_NAME` is a live mutable public dict; its derived frozensets are import-time snapshots** (A5). Tests patch the dict, moving `payload_key()` while leaving the frozensets behind — so they exercise a state production can never be in.
7. **The golden verdict corpus is structurally blind to payload-key changes** (B3). The in-process corpus replays with the target already extracted; the e2e path goes through `fixture_loader.py:679`, which contains a *sixth* hardcoded copy of the tool→key map and stays self-consistent with whatever the registry does. "Corpus unchanged" was the spec's headline verification for the item it could not see.
8. **`hook.COMMAND_TOOLS` is dead code** (B3) — zero readers anywhere, and a mutable `set` among frozensets. It is also the only place `mcp__local-tools__checked_bash` appears, which is what made the #10 spec's derivation unsatisfiable.

## The near-miss worth naming

**B3 would have stopped an instruction that destroyed an independent test oracle.** The #10 spec's item 5 told the coder to point `tools/architecture_fitness.py`'s canary at the new registry *and delete the comment explaining why it was deliberately not imported*. The canary treats the installed hook as a black box invoked by subprocess; sharing the source makes a wrong payload key invisible, because probe and probed would agree. The judge: *"This is the one instruction I would reject outright; the duplication there is an oracle, not drift."*

It was never carried out — `_CANARY_FILE_TOOLS` and its comment survive at `architecture_fitness.py:3674-3679`. **The coder's silent non-compliance is the only thing that saved it.** No review caught it.

## Method findings

- **Two-sidedness held.** Every judge reported degraded axes alongside improved ones, including on the axis each change was proudest of. None produced a one-sided improvement narrative.
- **No manufactured findings on the small change.** A1 (the shim deletion) returned **flat on 8 of 12 axes**. The flat rate tracked change size, which is what it should do.
- **They measured rather than asserted.** Import censuses, AST counts of stderr writes, `--layers` runs, call-frame counts from diffs. B1 independently re-derived the stderr census and confirmed the ticket's "16" was stale and the spec's corrected "8" was right — while separately catching that the config layer holds *five* such modules, not four.
- **Convergence across independent judges.** A5 and B3 arrived at the same behaviour change (the governed-tools default widening) from opposite directions without either seeing the other.
- **Judges beat the artefacts they judged.** B2 named the concrete mechanism (`auto_migrate` collapsing declined into failed, wrong remediation text, burned day-claim) where the original human catch was a one-line prompt to look.

## Declared limitations

1. **One-sided blinding.** The judges were blind; the axis list was not — three of twelve axes map onto known defects. Nine map to nothing known, which dilutes but does not remove the steering. A clean replication needs axes chosen by someone who has not seen the corrections.
2. **n = 4 positives.** Establishes existence, not a rate.
3. **This codebase cannot exercise most architectural axes** — no persistence layer, no request lifecycle, no schema, no deployment topology. Silence on those is not evidence about them.
4. **The control arm was not run.** Comparing against the general `/code-review` reports for the same five commits is the direct test of "focused beats general" and remains to be done.

## Verdict

**Supported, with the mechanism sharper than stated.** The dedicated judge found eight live defects in code that had already passed review, caught two of four known architectural errors from proposals alone, and stayed disciplined enough to return mostly-flat on a mechanical change. It did not find them by being cleverer — it found them by having nothing else to do.

The actionable design consequence: **run it on proposals, not on diffs.** Both hits and the near-miss were in arm B; the one arm-A subject carrying a known defect missed it.
