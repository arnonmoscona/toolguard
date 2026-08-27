---
title: Blind estimate (predictions) - item 15 migrate lock
type: note
permalink: toolguard/too-45/reports/surprise/15-estimate-predictions
tags:
- task-memory
- TOO-45
- measurement
---

## 1. Predicted touch set

| path | add / modify / delete | production or test | confidence | reason |
|---|---|---|---|---|
| `toolguard/permission_migration.py` | modify | production | high | `migrate()` is the subject: acquires/releases the lock, decides and reports the decline path |
| `toolguard/file_lock.py` | add | production | high (path: medium) | the "one wrapper function over `flock` and `msvcrt.locking`" has to live somewhere; a small new leaf module is the obvious home |
| `.pyscn.toml` | modify | production | high | every module must appear in exactly one layer or it is silently unmapped; a new module forces a layer declaration |
| `test/unit/test_migration.py` | modify | test | high | existing `migrate()` tests must survive the new serialisation and the decline path needs coverage next to them |
| `test/unit/test_file_lock.py` | add | test | high (path: medium) | new production module gets its own test module by convention; also the natural home for the two-real-processes tests |
| `toolguard/scripts/migrate_permissions.py` | modify | production | medium | the unserialised CLI caller must surface "declined, another migration is running" as an outcome/exit status |
| `test/unit/test_architecture.py` | modify | test | medium | layering invariants are asserted in tests as well as in the fitness tool; a new module changes the expected map |
| `test/unit/_migration_lock_isolation.py` | add | test | medium | strong convention: a module that writes under `~/.toolguard` gets a shared isolation helper redirecting its path |
| `test/unit/__init__.py` | modify | test | medium | 117 lines of package-level test setup; new isolation/guard seams are likely registered here |
| `technical-notes.md` | modify | production | medium | `flock` vs `lockf` and the chosen failure behaviour are exactly the kind of rationale this file carries |
| `test/unit/_real_migration_lock_home_guard.py` | add | test | low | the guard convention mirrors the once-per guard, but the existing guard may already cover all of `~/.toolguard` |
| `toolguard/constants.py` | modify | production | low | lockfile name / directory constant, if it is not simply local to the new module |
| `test/unit/test_auto_migrate.py` | modify | test | low | the already-safe caller now runs through a lock in tests too; may need isolation wiring even with no behaviour change |

## 2. Concentration set

- `toolguard/permission_migration.py` — the acquire/release scope, the failure decision, and the error-reporter calls
- `toolguard/file_lock.py` (new) — the cross-platform wrapper, the per-project lockfile path, and the timeout semantics
- `test/unit/test_file_lock.py` (new) — the only place the ticket's real verification lives: two actual concurrent processes, no-lost-update, different-projects-do-not-block, release-on-exception, release-on-death

Everything else is bookkeeping: layer map, isolation seams, caller plumbing, docs.

## 3. Expected counts

- Files modified: **9** (production 5, test 4)
- Files added: **4** (production 1, test 3)
- Files deleted: **0** (production 0, test 0)
