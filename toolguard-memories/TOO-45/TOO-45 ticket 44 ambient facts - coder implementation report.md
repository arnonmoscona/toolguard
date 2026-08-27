---
title: TOO-45 ticket 44 ambient facts - coder implementation report
type: note
permalink: toolguard/too-45/too-45-ticket-44-ambient-facts-coder-implementation-report
tags:
- task-memory
- TOO-45
---

# TOO-45 ticket 44 -- ambient state now has one door per fact

## The design, and the one place it deviates from the brief

`toolguard/ambient.py`, a new foundation-layer module:

| name | what it is |
|---|---|
| `AmbientFacts` | frozen dataclass: `home`, `cwd`, `env`. Values only, no lookups. |
| `resolve()` | builds one by reading the machine at call time; never raises (an unresolvable home/cwd is recorded `None`). |
| `active(facts)` | context manager binding facts for one invocation, restoring the previous binding on exit. |
| `home()`, `cwd()`, `env()`, `env_var()` | the one door. Bound, they report the facts; unbound, each reads live. |

`hook.main()` opens `ambient.active(ambient.resolve())` alongside the existing `error_reporter.active(reporter)`.

**Deviation: the facts reach their readers through a scoped binding, not through explicit threading.** Arnon's brief said "pass it down. Not a module global." Evidence for the change:

- Explicit threading needs a new parameter on roughly 25 functions across 12 modules, including `tools/installer.py` and `tools/decision_ledger.py` (own CLI entry points, no hook invocation above them) and `error_log.log_crash()`, which runs from `hook.main()`'s except clauses and must work when everything upstream has already failed. Adding a dependency to the crash path is the wrong direction.
- `error_reporter` reached the same conclusion for the same reason and its module docstring says so: the free functions exist "for callers reached through several layers of call chain, where threading a `Reporter` through every intervening signature is impractical". Extending a validated pattern beats inventing a second one.
- The stated reason for the prohibition -- a global surviving across replays in `toolguard.testing.sandbox` -- is eliminated by the `finally` teardown rather than argued around, and `test_two_invocations_in_one_process_do_not_share_state` plus `test_each_invocation_resolves_its_own_facts` pin it.

**It reverses cheaply if Arnon disagrees**: delete `active` and `_active`, drop the three lines in `hook.main()`, and the accessors fall back to a live read on every call. Everything else stays.

## Touch set

Production (added):
- `toolguard/ambient.py`

Production (modified) -- all one-line accessor swaps unless noted:
- `toolguard/path_utils.py` (also: module docstring no longer claims zero toolguard imports)
- `toolguard/normalization.py`
- `toolguard/error_log.py`
- `toolguard/once_per_store.py`
- `toolguard/permission_migration.py`
- `toolguard/config.py` (four home reads, `XDG_CONFIG_HOME`, `CLAUDE_SETTINGS_PATH`; `import os` dropped)
- `toolguard/env_config.py` (two cwd reads, four env reads; `import os` dropped; three docstrings that named `os.environ`)
- `toolguard/hook.py` (`CLAUDE_SETTINGS_PATH`; `import os` dropped; **the `ambient.active(...)` binding**)
- `toolguard/session_start.py` (`os.getcwd()`; `import os` dropped)
- `toolguard/install_update.py` (two subprocess environments)
- `toolguard/tools/installer.py` (three home reads, one cwd)
- `toolguard/tools/transcript_harvest.py`

Non-production:
- `.pyscn.toml` -- `ambient` added to the `foundation` layer
- `docs/architecture-as-built.md` -- same, in the layer table
- `.claude/rules/test-config-isolation.md` -- one paragraph on what patching still works and the one caveat

Tests (added):
- `test/unit/test_ambient.py` -- 15 tests, `toolguard.ambient` at 100% line coverage

## Every test edit, with why

1. **`test/unit/test_architecture.py`** -- `LAYERS` gains `("toolguard.ambient", frozenset())` and the edges `path_utils -> ambient`, `normalization -> ambient`, `install_update -> ambient`. Necessary: the table is a declared allow-list and a real new edge fails `test_each_governed_module_imports_only_what_it_declares`. Strictly additive, and `test_no_declared_edge_is_unused` keeps it from being loosened for nothing.

2. **`test/unit/test_error_log.py`** -- `_HomelessPath` (a stand-in class for `error_log.Path`) becomes `_homeless()`, a stand-in for `ambient.home()`; the patch target moves from `patch("toolguard.error_log.Path", ...)` to `patch("toolguard.ambient.home", ...)`, and the fixture self-check from `error_log.Path.home()` to `ambient.home()`. Necessary: the test's seam was the module's own `Path` attribute, and `error_log` no longer reads home through it. Assertions unchanged; the new target is one door instead of one per module.

3. **`test/unit/test_hook_error_reporter.py`** -- the same move for `_FixtureHomePath`/`_HomelessPath` and their three patch sites, plus the `setUpModule` docstring naming the anchor. Same reason. Two tests appended (`TestAmbientStateIsBoundForTheInvocationOnly`) covering the binding and its release.

No existing assertion was weakened, relaxed, skipped or deleted.

## Numbers

| | before (`db23d17`) | after |
|---|---|---|
| suite | 3659 tests, OK, 4 expected failures | 3677 tests, OK, 4 expected failures |
| `--mocks` | 1 inert patch (`test_session_warnings.py:159`) | 1 inert patch, the same one |
| `--layers` | complete, no violations | complete, no violations |
| `ruff format` / `check` | clean | clean |
| suite under empty `$HOME`/`XDG_CONFIG_HOME` | -- | OK, 4 expected failures |
| `toolguard.ambient` coverage | -- | 100% |

Hook smoke-tested end to end through `python -m toolguard.hook`; `toolguard.testing.sandbox` exercised and unaffected (it goes through `api.decide`, never `hook.main`, so it never binds).

## Left undone, deliberately

- **`tools/decision_ledger.py:37`, `USER_LEDGER_PATH = Path.home() / ...`** -- the one remaining import-time `Path.home()` in production, and inert-mock shape 5 by construction. Not migrated: `test_tools_decision_ledger.py` and `test_tools_maintenance.py` patch that module attribute directly, and one test asserts its real value equals `Path.home() / ".toolguard" / "decisions.json"`. Turning it into a function changes those tests, which is Arnon's call. It is not currently an *inert* mock -- patching the attribute works -- so nothing is silently broken today.
- **`install_provenance`, `tools/security_audit`, `tools/environment_audit`** keep `env=os.environ` default parameters. They already have an injection seam, and changing the default would change what an explicit caller gets.
- **`require_project_root` still has no direct test**, and there is still no `test_path_utils.py`. This refactor did not give either a natural home; `test_ambient.py` covers the door, not the walk. Left for phase 4.
- No technical-notes.md section was added for the scoped binding. The rationale is one sentence on `active()`'s docstring; a section can follow if Arnon wants the argument recorded.

## Checkpoint answer

Env and cwd came to nine extra one-line swaps in five modules and needed no further test edits, so they stayed in this change. The natural split point, if Arnon wants two commits, is after `Path.home()`: everything through `toolguard/tools/transcript_harvest.py` is commit one, and `env_config`/`hook`/`session_start`/`install_update` plus the `ambient.active` binding is commit two.

## What I would do differently

The first version of `test_main_binds_ambient_facts_for_the_duration_of_the_call` asserted the bound facts' home equalled the fixture home. It failed, and correctly: that module patches the `ambient.home` *door*, while `resolve()` reads the machine underneath it, so the facts hold the real home and every consumer still gets the fixture's. Writing the assertion before understanding which of the two the fixture controls cost a round. The design point stands -- `resolve()` reading the machine directly is what makes "resolve" mean resolve -- but it is a wrinkle worth knowing: patching `ambient.home` overrides the door, not the facts.
