---
title: TOO-45 ticket 44 broken isolation seam - coder implementation report
type: note
permalink: toolguard/implementation/too-45-ticket-44-broken-isolation-seam-coder-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Repaired the isolation seam ticket 44 broke in `test/unit/test_hook.py`. One file changed, tests only. No production code touched. Nothing committed.

## The defect, reproduced

`TestDecisionReachesStdoutWhenCrashLoggingFails` isolated `log_crash` by rebinding `toolguard.error_log.Path` to a `_HomelessPath` whose `home()` raised. Ticket 44 moved `log_crash` to `ambient.home()`, so the rebind intercepted nothing: `log_crash` succeeded against the developer's real home and wrote three crash reports per run, while the tests still passed.

Measured 2026-08-19: running that class alone took `~/.toolguard/errors/` from **1765 to 1768**.

## The fix

`test/unit/test_hook.py` only:

- Deleted the nested `_HomelessPath` class; added a module-level `_homeless()` that raises, matching `test_hook_error_reporter.py` and `test_error_log.py` verbatim in shape and docstring.
- `patch("toolguard.error_log.Path", self._HomelessPath)` -> `patch("toolguard.ambient.home", _homeless)`, carrying the same "Patching the accessor, not isolating config" justification the two sibling modules use (required by `.claude/rules/test-config-isolation.md`).
- Negative-case self-check `error_log.Path.home()` -> `ambient.home()`.
- Rewrote the class docstring clause "error_log builds ~/.toolguard/errors ABOVE its own try", false since ticket 44 put the resolve inside the try.
- `from toolguard import error_log, once_per_store` -> `from toolguard import ambient, once_per_store` (`error_log` had no remaining code use).

No assertion changed, no test added or removed.

## Evidence

`log_crash` is still called and now genuinely fails, rather than never being reached: a spy around `toolguard.hook.log_crash` under the repaired fixture recorded **1 call returning None**, test passing, zero files written.

| Check | Result |
|---|---|
| Class alone, before fix | 1765 -> 1768 |
| Class alone, after fix | 1768 -> 1768 |
| Full suite, real `$HOME` | 3684 tests, OK, 4 expected failures; 1768 -> 1768 |
| Full suite, empty `$HOME`/`XDG_CONFIG_HOME` | 3684 tests, OK, 4 expected failures; 0 crash reports in the throwaway home |
| `ruff format` / `ruff check` | 177 files unchanged / All checks passed |
| `tools/architecture_fitness.py --mocks` | 1 finding, the pre-existing `test_session_warnings.py:159` |

## Sweep for the same shape

Searched all of `test/` for the genuinely-broken shape -- rebinding a *module attribute* that a ticket-44-migrated module no longer reads through:

- `patch("<anything>.Path"|".os")` and `patch.object(<module>, "Path"|"os")`: **zero hits repo-wide** after this fix. `error_log.Path` was the only one.
- `patch("toolguard.<module>.Path.home")`-style (attribute *below* the alias): 4 hits. `test_hierarchical.py:143` resolves through `toolguard.config.Path` to the `pathlib.Path` class and patches `home` on the class itself, so it is a global `Path.home` patch, which an unbound ambient accessor still falls through to. The three `test_config_write_guard.py` hits target `os.replace`/`os.fsync`, outside ambient's scope.
- Ticket 44 added and removed **no function definitions** (`git diff -U0 -- toolguard/` on `def` lines is empty), so no test can be patching a symbol the migration deleted.
- `patch("pathlib.Path.home")`, `patch.object(Path, "home")`, `patch.dict(os.environ)` and `HOME=`-setting forms are all global and unaffected; the one caveat (a patch installed *after* `main()` binds facts) is already documented in the rule.

## `--mocks` gap, for proposed ticket 45

Worth recording. The checker's inertness test is "does the target attribute exist on the named module" -- `error_log.Path` did, so the defect passed cleanly. The defect class is one level up: **the target exists but the module never calls it**. `error_log` retains `Path` purely as a type annotation; nothing in it calls `Path(...)` or `Path.home()` any more, so rebinding it can affect no call site. That is statically decidable from the AST the tool already parses -- flag `patch("<repo module>.<symbol>")` where the symbol is imported rather than defined there and appears in no call or attribute-access position in that module's body. A cheap second inertness class, not a rewrite.

## Recommended, deliberately not done

The repaired fixture has no guard against re-drifting. Its self-check asserts `ambient.home()` raises, which stays true whether or not `log_crash` still reads it -- so a future migration would silently re-break it exactly as ticket 44 did. `test_hook_error_reporter.py` solves this with `TestFixtureIsolationIsLive`, which asserts the crash report lands under the fixture home; that shape is unavailable here because the fixture's home *raises*, so no report lands anywhere. The workable equivalent is asserting stderr carries log_crash's own `Failed to write crash report` warning, which is precisely what the spy proved. That is an added assertion, outside the scope this task set, so it is a recommendation for Arnon rather than a change.

## Housekeeping: `~/.toolguard/errors/`

**Nothing deleted.** 1768 files total. 136 are dated 2026-08-19; the newest 3 (19:57) are my deliberate one-class reproduction, and the other 133 predate this session -- notably more than the "roughly 4" the handoff estimated (57 in the 16:00 hour, 27 in 17:00, 33 in 18:00, 16 in 19:00). Earlier dates account for 1632, with 806 on 2026-08-12 alone.

## Process note

One disclosure miss: an `ls | sed | cut | sort | uniq -c` tally of crash-report dates went out without a disclosure block. `sed 's/toolguard-error-//'` is an authored sed program (case 4). Self-reported and disclosed correctly on the following command.

## Cost

| Phase | Elapsed | Est. cost |
|---|---|---|
| 1 -- read context, reproduce the leak, capture requirements | ~8m | ~$1.20 |
| 2 -- implement, prove the seam live, sweep | ~11m | ~$1.60 |
| 3/4 -- full-suite verification x2, lint, report | ~8m | ~$1.00 |
| Total | ~27m | ~$3.80 |
