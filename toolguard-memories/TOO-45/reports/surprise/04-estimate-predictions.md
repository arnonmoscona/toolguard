---
title: Blind estimate (predictions) - item 04 error reporter
type: note
permalink: toolguard/too-45/reports/surprise/04-estimate-predictions
tags:
- task-memory
- TOO-45
- measurement
---

## 1. Predicted touch set

| path | add / modify / delete | production or test | confidence | reason |
|---|---|---|---|---|
| `toolguard/error_reporter.py` | add | production | high | The one new module the ticket promises: severity-in, routing-out, throttle policy owned here. |
| `test/unit/test_error_reporter.py` | add | test | high | Per-severity destination tests are the named verification; they need a home of their own. |
| `toolguard/auto_migrate.py` | modify | production | high | Named in the ticket: 6 of the 16 stderr writes. |
| `toolguard/config_divergence.py` | modify | production | high | Named in the ticket: 5 of the 16 stderr writes. |
| `toolguard/config.py` | modify | production | high | Named in the ticket: 3 of the 16 stderr writes. Mechanical relative to its size. |
| `toolguard/env_config.py` | modify | production | high | Named in the ticket: 2 of the 16 stderr writes. |
| `toolguard/session_warnings.py` | modify | production | high | The takeover notice is the "routine notice" category; classifying it is explicitly in scope. |
| `.pyscn.toml` | modify | production | high | A new module must be declared in a layer or it is silently unmapped; the reporter sits at/below `observability`. |
| `toolguard/error_log.py` | modify | production | medium | The reporter routes *to* the warning/error log; likely needs a callable seam or a severity-aware entry point. |
| `toolguard/hook.py` | modify | production | medium | The catch-all handler is a fault-and-a-decision; classifying it is in scope even though the fail-open fix is not. |
| `tools/architecture_fitness.py` | modify | production | medium | The natural enforcement for "no hand-rolled stderr outside the reporter" is a fitness predicate, and this repo reaches for one. |
| `test/unit/test_auto_migrate.py` | modify | test | high | Existing tests almost certainly assert on captured stderr for these 6 sites. |
| `test/unit/test_config_divergence.py` | modify | test | high | Same, for 5 sites. |
| `test/unit/test_env_config.py` | modify | test | medium | Same, for 2 sites; may or may not assert stderr today. |
| `test/unit/test_config.py` | modify | test | medium | Same, for 3 sites, spread across a broad test file. |
| `test/unit/test_session_warnings.py` | modify | test | high | 103 lines, entirely about the notice being reclassified. |
| `test/unit/test_hook.py` | modify | test | medium | Home of the "an uneventful invocation writes nothing to stderr" test, and of the catch-all handler's tests. |
| `test/unit/test_architecture.py` | modify | test | medium | Layer-membership invariants must learn about the new module. |
| `test/unit/test_architecture_fitness.py` | modify | test | medium | If a stderr-ban predicate is added, this file grows with it. |
| `docs/architecture.md` | modify | production | medium | New module plus a routing policy is exactly what this doc describes. |
| `technical-notes.md` | modify | production | medium | The routing/throttling policy is design rationale, not a code comment. |

## 2. Concentration set

The substance lives in five places; everything else is bookkeeping.

- `toolguard/error_reporter.py` — the policy: the severity/kind vocabulary, the destination matrix, the throttle decision, and the "the throttle store is the thing that broke" fallback.
- `test/unit/test_error_reporter.py` — the per-severity destination assertions, which are the only thing that actually pins the policy down.
- `toolguard/session_warnings.py` — small, but it is where the false premise ("nothing in stderr normally") gets resolved by declaring the takeover notice a routine notice.
- `toolguard/config_divergence.py` and `toolguard/auto_migrate.py` — 11 of the 16 sites, and the two files where the call-site *classification* (fault vs notice vs fault-and-decision) is a judgement call rather than a rename.
- `.pyscn.toml` — one line, but it is the difference between the new module being governed and being silently unmapped.

## 3. Expected counts

| | production | test |
|---|---|---|
| modified | 11 | 8 |
| added | 1 | 1 |
| deleted | 0 | 0 |
