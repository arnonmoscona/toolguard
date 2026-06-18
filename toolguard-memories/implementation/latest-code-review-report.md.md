---
title: latest-code-review-report.md
type: report
permalink: toolguard/implementation/latest-code-review-report.md
tags:
- code-review
- TOO-8
---

# Code Review Report

Date: 2026-06-18
Scope: changed (working-tree diff vs HEAD), ticket TOO-8 (Phase 5 -- hierarchical
non-permission cross-level resolution).

Files reviewed:
- toolguard/config.py
- toolguard/hook.py
- test/unit/test_configuration.py
- test/unit/test_hook.py
- technical-notes.md

## Summary

High-quality, well-documented change. Phase 5 introduces single-owner / fail-safe
takeover_mode.enabled resolution, more-specific-wins for scalars/config_sync, and
hierarchical union for governed_tools and takeover pattern lists. All 682 unit tests
pass. Docstrings, BDD test descriptions, and technical-notes are consistent with the
code. No correctness bugs found. Findings are minor: one dead-code consistency trap and
a couple of low-priority robustness/clarity notes.

## Findings

### Critical
None.

### Major
None.

### Minor

1. config.py:1594 `Configuration.bash_permissions()` -- stale resolution path / dead code.
   `bash_permissions()` still delegates to the legacy 2-level `_load_permissions()`
   (union + global deny-first over project+user only), while the actual runtime Bash path
   in `hook.main` resolves through the hierarchical, more-specific-wins cascade
   (`config.resolve_permission_detailed('Bash', ...)`) and the hierarchical
   `allow_deny_for('Bash')` fail-closed check. `bash_permissions()` now has NO runtime
   caller (only its own definition and `test_configuration.py::TestBashPermissionsDelegation`
   exercise it). It is a latent trap: a future caller would silently get non-hierarchical,
   non-more-specific-wins results inconsistent with every other resolver.
   Recommended fix: either remove `bash_permissions()` (and its test) or reimplement it
   over `self.layers` via `allow_deny_for('Bash')` so it matches the runtime path. If kept
   transitionally, add a `# FIXME(TOO-8)` noting it is the only non-hierarchical resolver
   left and is unused at runtime. (The module docstring already flags `_load_permissions`
   et al. as transitional, but does not call out that `bash_permissions` itself is now
   unused.)

2. config.py:1269 `takeover_mode()` -- `bool(section['enabled'])` coerces non-bool values.
   A TOML/JSON `enabled = "false"` (string) coerces to `True`, and `enabled = 0` to
   `False`, silently. Given enabled is a fail-safe security-relevant policy, consider
   treating a non-bool `enabled` as a validation Issue (surfaced via `validation_issues()`)
   rather than coercing. Low priority -- TOML authors will normally use real booleans, and
   the conflict machinery already fail-safes on disagreement.

### Suggestions

3. config.py:1656 `config_sync_settings()` duplicates the default values
   (`False`, `'logs/config-backups'`, `True`) that also appear in
   `config_sync_settings_from_sources()` (config.py:1955) and in the hook fake
   (test_hook.py:134). Three copies of the same defaults can drift. Consider a single
   module-level `_CONFIG_SYNC_DEFAULTS` mapping referenced by both production resolvers
   (mirroring how `_DEFAULT_IGNORED_ALLOW_PATTERNS` / `_DEFAULT_NO_MATCH_FALLBACK` were
   already centralized in this same change -- a good pattern to extend).

4. hook.py:595-606 The enabled-conflict branch reuses `issue_takeover_warning(...)`, the
   same warning surface as the takeover-active notice. This is intentional per
   technical-notes (shared once-per-session marker), but the warning text is generic; a
   reader of the warning stream cannot distinguish "takeover active" from "takeover
   conflict, failed safe OFF". The conflict log entry carries the detail, so this is
   acceptable; worth a one-line note in the warning copy if/when that function is touched.

## Verification

- Test suite: `uv run python -m unittest discover -s test -t .` -> Ran 682 tests, OK.
- Anti-pattern scan of changed source (config.py, hook.py): no async/await, no threading,
  no function-body imports (test-only `import toolguard.hook as hook_module` is acceptable).
- Toggle interaction confirmed: when `hierarchical_configuration = false`,
  `_discover_levels` limits `self.layers` to project+user, so the new over-`self.layers`
  resolvers (scalar/governed_tools/takeover) correctly operate on the reduced set.
