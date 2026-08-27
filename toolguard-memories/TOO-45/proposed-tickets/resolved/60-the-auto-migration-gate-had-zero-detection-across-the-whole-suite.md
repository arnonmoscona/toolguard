---
title: Removing the auto-migration gate - so toolguard rewrites a config the user
  never opted into - was undetected across the entire suite
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/60-the-auto-migration-gate-had-zero-detection-across-the-whole-suite
---

**FIXED in `05f786d` (TOO-45 phase 2).** The gate was already intact; the zero-detection was a test coverage gap, now closed — see `toolguard/hook.py:908` and `test/unit/test_hook_eval.py:784`.

# The gate on unasked config writes had no detector anywhere

**Found 2026-08-13. Not a production defect — the gate is correct. The finding is that nothing in 3,000 tests would notice if it stopped working.**

## The measurement

`_run_divergence_check` gates `run_auto_migration` on `config_sync.auto_migrate`, which **defaults to `False`**. Auto-migration **writes the user's permission configuration without being asked**, so that gate is the entire consent mechanism.

Mutants, measured across **all five modules that touch `_run_divergence_check`** (126 tests):

| mutant | detection |
|---|---|
| `M13` — the gate never fires (auto-migration never runs) | detected by `test_logging_streams` |
| **`M12` — the gate is REMOVED, so auto-migration fires when the user did NOT enable it** | **ZERO real detection** |

The one test whose state changed under `M12` was `test_config_divergence.test_warns_when_sqlite_unavailable`, and **its traceback shows an incidental stderr-capture collision, not gate semantics** — a false positive that would have read as coverage in a failure count.

**So: toolguard rewriting a user's permission config unasked was invisible to the entire suite.** The safe direction was covered; the unsafe direction was not.

Now held by `TestAutoMigrationGate` — three tests, both directions plus the no-divergence case.

## Why it hid

`test_hook_eval.py` **mocked `run_auto_migration` itself**, so the gate's condition was never exercised from the hook seam. Worse, measured with a spy: **`run_auto_migration` is unreachable from every path that module drove, including the live one** — 0 real calls in a whole-module run. Both `assert_not_called()` assertions were therefore **structurally incapable of failing** (catalogue shape 2).

This is the same shape as proposed ticket 43: a mock that reads as a guard and enforces nothing.

## A cross-project leak found in the same pass

`_run_live` did **not** stub `check_and_warn_divergence`, so the live-hook path ran it for real — **5 times per module run, against whatever project the process happened to sit in** (`config.project_root` resolves through `Path.cwd()` for a `start_dir=None` fixture).

Proven, not inferred: run from a foreign cwd holding a divergent fixture project, the module printed

```
[TOOLGUARD WARNING] New permission(s) found in settings.local.json ... Bash(rsync:*), Bash(scp:*)
```

— an **unrelated project's configuration leaking into a test module's output**, and a path that can take a day-claim in `~/.toolguard/once_per.db`. Closed.

## The class named for drift-detection was the vacuous one

`TestResolveEventAntiDrift` asserted `_resolve_event(...) == decide(...)` — and `_resolve_event`'s entire non-guard body **is** `return decide(...)`. Catalogue shape 8, proven: replacing `api.decide` with a constant in **both** holders left both tests green; patching only one made them fail. So they *can* fail, but **cannot detect drift** — the mutant replacing the delegation with the pre-refactor hand-rolled dispatch had **zero detection**.

Meanwhile the file's *real* drift detector was the unnamed eval-vs-live comparison class. **The name pointed at the wrong test.**

## Other zero-detection mechanisms closed here

- `--eval` falling through to the live path: 1 incidental detection → **8**
- `extended_syntax` forced `False`: **0** → 2
- `ignore_env_override=True` dropped: **0** → 1
- `--eval` ignoring the project's `extended_syntax`: **0** → 1
- **two of `_run_eval_mode`'s three fail-safe branches emitted a deny with no engine consulted**, both untested — ticket 29's family

## Method note — the by-value trap bit an agent that had read the warning

The agent's own first gate measurement read **zero detection for `M12`/`M13` against the repaired module** — a **false zero**, because the test module now imports `_run_divergence_check` by value and the harness patched only `toolguard.hook`.

**Third recorded instance of this trap catching someone who had already been warned about it.** It is not a knowledge problem; it is a checklist problem. The mitigation that works is asserting the patch took effect, not remembering to patch every holder.