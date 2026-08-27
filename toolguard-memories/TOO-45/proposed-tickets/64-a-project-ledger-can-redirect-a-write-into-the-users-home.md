---
title: A project ledger whose body claims level=user redirects the next write into
  the user's home, and the ledger writer has no lock
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/64-a-project-ledger-can-redirect-a-write-into-the-users-home
---

**PARTIALLY FIXED in `05f786d`.** Defect 1 is fixed — level is now derived from the path, not the body (`toolguard/decision_ledger.py:295`); still open: defect 2, `record_decision` remains unlocked and non-atomic (`:340-366`).

# The file's contents decide where the next write goes

**Found 2026-08-13. Two RED tests in the tree. Queue item DL1, executed.**

## Defect 1 — `load_ledger` trusts the file body for `level`, not the path it read

A **project** ledger whose body contains `"level": "user"` loads as `user` — **and re-recording it writes the user's home directory.**

So a file inside a project can redirect a subsequent write outside the project. A checked-in or generated `toolguard_decisions.json` is enough; nothing validates that the body's claim matches where the file was found.

The compounding direction is also broken: **a hand-written user ledger with no `"level"` key loads as `project`.**

Both RED tests are written **mechanism-agnostically** — they pass whether the fix raises `LedgerError` on a mismatch or simply labels by path. And both have the **mutate-toward-the-fix** property: three separate mutants each turn exactly one of them green.

**Fix shape** (from the queue, and it holds): pass the level in from the path; keep `"level"` in the body as a written-only provenance tag, or raise on mismatch.

## Defect 2 — the ledger writer is an unlocked, non-atomic read-modify-write

`record_decision` does `load` → filter → `append` → `write_text`, with **no lock and no atomic replace.**

**TOO-45 item 15 gave `migrate()` an OS file lock for exactly this shape. This writer did not get one.** And the module's raise-on-corrupt policy makes a truncated write maximally painful: a half-written ledger doesn't degrade, it throws.

## What the module could not see

**Round-tripping asserted two fields.** `test_record_then_load_roundtrips` checked only `rationale` and `level`, so dropping `recorded_at` or `toolguard_version` from **either the writer or the reader** had **zero detection** — as did dropping the persisted `id`, which `--ledger-show` re-emits to the skill. Now `assertEqual(load_ledger(path), (dec,))` — full frozen-dataclass equality.

`test_entry_missing_required_field_raises` omitted **two** required fields at once, so making any single one optional still raised. Now a per-field `subTest`.

Mutation: **21 of 48 survivors → 1**, and the survivor is documented below.

## The isolation trap this module was one line away from

`decision_ledger.USER_LEDGER_PATH` is built from `Path.home()` **at import**, so patching `Path.home` cannot move it. There is now a `LedgerIsolationMixin` across all nine test classes that redirects the constant, verifies the redirect **through the production read site** (`ledger_path_for_level("user", ".")`), and adds a cleanup guard asserting the developer's real ledger's `(exists, size, mtime)` is unchanged after **every** test.

**Correction to proposed ticket 57**: its "2 of 4 ledger tests fail with one decoy entry" refers to `test_tools_maintenance.TestLedgerMode`, **not** this module. Measured here, a decoy at the user-ledger location produces **zero** failures at HEAD — the one test that reads the user ledger already patched the constant inline. **The trap did not bite this module; it was one line away from doing so.**

## Two judgement calls worth recording

- **`LEDGER_SCHEMA` is written and never read back** (queue DL2). **Deliberately not pinned in either direction** — "reject an unknown schema" versus "migrate it" is an open design choice, and a test either way would preempt it.
- **The sole surviving mutant is a *partial fix* of DL1**, not a gap: it changes the absent-`"level"` default from `project` to `user`, turning one RED test green while the other stays red. Pinning the current default would enshrine the defect, and the branch disappears under any real fix. **Non-equivalent, and not worth pinning.**

## A precise equivalent-mutant analysis, kept because the reasoning generalises

Removing half of `load_ledger`'s `"decisions" not in data` guard is **equivalent for list- and string-shaped JSON** — `"decisions" not in [1,2]` is `True`, so `LedgerError` raises either way. It is non-equivalent **only for JSON scalars** (`5`, `null`), where the mutant raises an uncaught `TypeError`. The new test uses `5`, the discriminating case.

Same family as proposed tickets 46 and 55: **the JSON-is-a-dict assumption, in a fifth place.**
---

## DEFECT 2 MEASURED 2026-08-20 — and both mechanisms it needs already exist

`decision_ledger.record_decision` (now at `:350`, the amendment says `:340-366`) is a read-modify-write with **no lock and no atomic replace**:

```python
existing = [d for d in load_ledger(path) if d.id != decision.id]
existing.append(decision)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(...) + "\n", encoding="utf-8")
```

`grep` for `file_lock|FileLock|_atomic|replace(` in that module returns **nothing** — it uses neither.

Two consequences, both real:

- **Non-atomic.** `write_text` truncates before writing. A crash or a full disk mid-write leaves a **truncated ledger**, and `load_ledger` raises `LedgerError` on a malformed file — so one interrupted write makes every later read fail.
- **Unlocked.** Two concurrent `record_decision` calls each read the old list, each append their own entry, and the last writer wins. **One decision is silently lost** — no error, no warning, and the ledger looks well-formed afterwards.

### This is ticket 74's shape, not a missing-feature problem

**Both mechanisms already exist in this package and this caller uses neither:**

- `toolguard/file_lock.py` — added under punch-list item 15 so `migrate()` serialises itself against concurrent runs. Same class of read-modify-write, same file-corruption risk, already solved once.
- `config_write_guard._atomic_write` — write-to-temp-then-replace, used by the config write path.

So the fix is **adopting existing primitives**, not designing new ones, which should keep it small. Confirm both are reachable from this layer without inverting a dependency (`decision_ledger` sits in `tools/`; `file_lock` is a foundation module, so downward is fine).

### Worth deciding explicitly

**What should happen when the lock cannot be acquired?** `migrate()` already answers this for its own case, and ticket 32's item 1 records that its four `LockUnavailable` reasons get collapsed into one and mis-reported — so the precedent is available *and* carries a known defect. Do not copy the collapsing.

### Exposure

toolguard runs one process per tool call, so two overlapping tool calls can interleave, and operator tooling can run while a hook fires. **Not measured against the corpus** — a lost ledger entry leaves no trace, so the corpus cannot show it. Per the evidence rule, that is a zero measuring observability rather than absence.
