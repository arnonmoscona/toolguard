---
title: 'TOO-30 pre-push follow-up: suite-wide test isolation cleanup'
type: note
permalink: toolguard/too-30/too-30-pre-push-follow-up-suite-wide-test-isolation-cleanup
tags:
- project
- TOO-30
- testing
- pre-push
---

## Reminder: before pushing TOO-30

Arnon flagged (2026-07-23) that most of the test suite does not isolate `Path.home()`
from the real machine, so tests can silently depend on whatever is actually in this
dogfooded repo's real `~/.claude/toolguard_hook.toml` (or, after TOO-30 ships,
`~/.config/toolguard/rules/`). Confirmed real, not hypothetical: `test_takeover_mode.py`
had 2 tests actually failing on this machine because of it (fixed inline as part of
TOO-30, see below).

**Scope check performed 2026-07-23:**

| test file | config-discovery calls | `Path.home()` isolated |
|---|---|---|
| test_hierarchical.py | 18 | 0 |
| test_hard_deny.py | 4 | 0 |
| test_takeover_mode.py | 4 | 0 (now fixed for the 2 affected tests only) |
| test_toml_config.py | 2 | 0 |
| test_logging_streams.py | 1 | 0 |
| test_config.py | 3 | 1 |
| test_configuration.py | 28+ | 2 (now more, from TOO-30's new tests) |
| test_migration.py | 1 | 4 |

**Decision:** Do NOT fold a full retrofit into TOO-30 (would roughly double its size and
is unrelated to the split-rules-directory feature). Instead:
1. Fixed only the 2 tests in `test_takeover_mode.py` that were ACTUALLY failing (added
   `patch.object(Path, "home", return_value=fake_home)` around their `load_configuration()`
   calls, mirroring the isolation pattern already used by TOO-30's new
   `_isolated_hierarchy()` helper in `test_configuration.py`).
2. Left `test_hierarchical.py`, `test_hard_deny.py`, `test_toml_config.py`,
   `test_logging_streams.py` untouched -- they happen to pass today on this machine's
   real config, but are NOT hermetically isolated and could break (or silently pass for
   the wrong reason) on a different machine/config state.
3. **BEFORE PUSHING TOO-30**: build a common, reusable test-isolation pattern (Arnon's
   suggestion: a mixin class or similar shared helper) that consistently redirects the
   three controllable filesystem anchors `config.py` discovery goes through --
   `Path.home()`, `toolguard.config.find_project_root()`, and the `XDG_CONFIG_HOME` env
   var -- into an isolated tempdir, then retrofit it across the 5 unguarded files above.
   Ruled out `pyfakefs` as a dependency: every filesystem access in `config.py` is
   reachable from exactly those 3 anchors, so a full fake-filesystem library solves a
   broader problem than exists here and would add a dev dependency this project doesn't
   otherwise need. The stdlib redirect-patch pattern (already proven by TOO-30's
   `_isolated_hierarchy()`) is the right-sized fix -- promote it out of
   `test_configuration.py` into a shared helper the other files can reuse.
4. Add this to the standard pre-push checklist review for this ticket (alongside
   coverage, docs, pyscn, toolguard-maintenance).
