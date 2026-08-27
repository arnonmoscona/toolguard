---
title: TOO-45 surprise factor - ticket 64 pre-registration
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/64-prereg
---

# Pre-registration, ticket 64 — NO ESTIMATOR WILL RUN, and the reason is recorded before implementation

## Disposition: EXCLUDED from the touch-set series

Ticket 64's file carries a coordinator appendix from 2026-08-20 (line 61): *"DEFECT 2 MEASURED — and both mechanisms it needs already exist."*

That is not merely a touch-set leak. **It answers the character-of-fix question outright** — the question that finding 23 established is the only unleaked signal worth collecting. An estimator reading it is told the fix is *adoption of existing mechanisms*, which is the entire inference.

Running an estimator here would produce a number that measures nothing. **Recorded as an exclusion rather than silently skipped**, per the standing rule that a skipped scoring step must be justified in writing.

Contaminated-by-appendix list is now: **20, 39, 57, 64, 70.**

## Coordinator predictions, locked before implementation

Not a substitute for the estimator — these are mine, and I have been wrong twice today (ticket 22's prose-or-structure, and ticket 64's module identity).

1. **The atomic write is the whole valuable fix; the lock is deferrable.** Measured: `record_decision` is CLI-only, so a lost update needs two concurrent human invocations, while a torn write needs one interrupted process. **Falsifier**: evidence that `record_decision` reaches the hook path after all, or that some other caller makes concurrency ordinary.
2. **The touch set is `toolguard/tools/decision_ledger.py` plus `test/unit/test_tools_decision_ledger.py`, and nothing else.** `os.replace` needs no new import beyond `os`, and no caller changes because the signature is unchanged. **Falsifier**: any change to `maintenance.py`, which would mean the fix leaked into the CLI layer.
3. **A second atomic-write implementation will be tempting and should be refused.** `config_write_guard._atomic_write` and `installer._atomic_write_text` already exist. Adding a third is *one concept, many enumerations* — the failure this campaign has now paid for four times. **Predicted: the implementer reuses or extracts rather than writing a third.** This is the interesting one, because the two existing versions live in modules the ledger has no business importing.

## What would make this ticket cost more than it should

Extracting a shared atomic-write helper touches three modules and invites a discussion about where it lives. **If that starts to happen, stop and split it** — the ledger's own atomicity is the fix; the consolidation is ticket 64's second half and can be its own commit.

---

# OUTCOME, 2026-08-21 — commit `250f2a6`, 3 files, 65 lines. TWO OF MY THREE PREDICTIONS FALSIFIED.

No estimator ran (excluded above), so these are only the coordinator's.

| # | prediction | outcome |
|---|---|---|
| 1 | the atomic write is the whole valuable fix; the lock is deferrable | **HELD** — caller graph confirmed by the implementer; lock not added; nothing surfaced arguing it is more urgent |
| 2 | touch set is `decision_ledger.py` + its test, nothing else | **FALSIFIED** — also `tools/architecture_fitness.py` |
| 3 | the implementer reuses or extracts rather than writing a third atomic write | **FALSIFIED** — a third, local implementation |

## Prediction 2 — falsified by the project's OWN GUARD, which is the good outcome

Adding `import os` required an `OS_IMPORT_OWNERS` entry, because `--ambient` fails on any `os` import with no declared owner. **That is the check working exactly as designed** — an ambient-state import must declare an owner — and it is the "conformance to a declared intent" class that `.claude/rules/evidence-before-fixing.md` calls *strong*, not heuristic.

**So the miss is a fact about the codebase, not about the estimate**: this repo has a machine-checked declaration that makes certain one-line fixes touch a second file *by construction*. Any future estimate on a ticket that adds an `os`, home, cwd, or `resolve()` read should include the owners table automatically.

**Generalisable**: a repo with fitness declarations has a *predictable* extra file per class of change. That is cheaply learnable and nobody has been folding it in.

## Prediction 3 — falsified, and MY BRIEF MADE IT UNSATISFIABLE

I predicted reuse-or-extract. The implementer wrote a third local `_atomic_write` and justified it: both existing versions are module-private and shaped for their own call sites (`installer`'s docstring explicitly disclaims reuse for config-like data), the ledger has no business importing `config_write_guard` or `installer`, and extraction would touch three modules.

**The brief forbade every route to my own prediction.** It said, in order: *do not write a third*; *do not import across a bad boundary*; *stop and report if extracting starts touching three modules*. Those three constraints leave exactly one option — a local implementation — which is the thing the first constraint prohibited.

**This is a coordinator error of a kind not yet in the cause list.** Not `E`, `C`, `P`, `D`, `A`, `X` or `I`: the prediction was not wrong about the world, it was **incompatible with the instructions issued alongside it.** Call it **`B` (brief-constrained)** — the estimate and the brief disagreed, and the brief wins because the implementer obeys it.

**It matters for the aggregate.** Any item where I both predict and instruct can produce a "miss" that measures my own inconsistency. **The estimator does not have this problem — it never writes the brief.** That is a real argument for keeping estimation and briefing in separate hands, beyond blinding.

The implementer took the only coherent option and **named the duplication in the docstring** so a later consolidation can find it, which is the correct disposition of a constraint conflict it could not resolve.
