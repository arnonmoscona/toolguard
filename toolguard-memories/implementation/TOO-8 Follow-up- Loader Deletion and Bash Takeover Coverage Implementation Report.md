---
title: 'TOO-8 Follow-up: Loader Deletion and Bash Takeover Coverage Implementation
  Report'
type: note
permalink: toolguard/implementation/too-8-follow-up-loader-deletion-and-bash-takeover-coverage-implementation-report
tags:
- TOO-8
- implementation-report
---

# TOO-8 Follow-up Implementation Report
## Loader Deletion and Bash Takeover Coverage

**Date:** 2026-06-23
**Task:** TOO-8 follow-up - delete legacy `load_takeover_mode_config`, migrate
last caller, rework tests, confirm/add live Bash takeover filtering coverage.

---

## Summary

Three changes were made:

1. **`toolguard/scripts/migrate_permissions.py`** - Migrated off the legacy
   loader to reuse the existing `Configuration` object.
2. **`toolguard/config.py`** - Deleted `load_takeover_mode_config` and cleaned
   up stale comments.
3. **`test/unit/test_takeover_mode.py`** - Reworked to use the hierarchical API;
   dropped tests duplicated in `test_configuration.py`; added 4 new Bash
   takeover-filtering tests.

Test count: 727 -> 725 (net -2: dropped 6 tests from legacy API, added 6 new
tests -- 2 ported + 4 new Bash coverage).

---

## Task 1: migrate_permissions.py Rework

### What changed
- Removed `load_takeover_mode_config` from the import list.
- Captured the result of `load_configuration(...)` in a named variable
  `configuration` so it can be reused for both `get_toolguard_permissions()`
  and the new `configuration.takeover_mode()` call.
- Replaced the old dict-based access (`takeover_config.get("enabled", False)`,
  `takeover_config.get("ignored_allow_patterns", [])`) with attribute access on
  the `TakeoverConfig` dataclass returned by `.takeover_mode()`.
- `ignored_patterns` is still only populated when `takeover.enabled` is True,
  preserving the prior behaviour exactly.

### Semantic equivalence vs. old code
The legacy `load_takeover_mode_config` used OR-logic (`enabled = any file
enables it`). The hierarchical `Configuration.takeover_mode()` uses
single-owner / fail-safe-on-conflict. For the `ignored_patterns` list used by
`find_divergent_patterns`, the practical impact is that in a conflict scenario
the new code conservatively returns `enabled=False` (fail-safe), while the old
code would have returned `enabled=True`. This is the correct and intended
behaviour per TOO-8 design.

---

## Task 2: config.py Cleanup

### `load_takeover_mode_config` deletion
The entire function (lines 422-505) was deleted. No other code referenced it
(confirmed by `grep -rn load_takeover_mode_config` after the change; only
memory/markdown files retain the name as historical references).

### Comment cleanups
- **Module docstring** (line ~17): Removed `load_takeover_mode_config` from the
  list of "transitional public" functions.
- **`_DEFAULT_IGNORED_ALLOW_PATTERNS` comment** (line ~44): Changed "Shared
  between the legacy `load_takeover_mode_config` and the hierarchical
  `Configuration.takeover_mode` resolver so both stay in sync" to simply "Used
  by the `Configuration.takeover_mode` resolver."
- The constant itself was retained (still used by the hierarchical resolver).

---

## Task 3: test_takeover_mode.py Rework

### Tests dropped (6 tests)
Each drop is because `test_configuration.py` already provides equivalent coverage:

| Test | Reason for drop | Covered by |
|------|----------------|------------|
| `test_load_takeover_mode_from_toml` | TOML reading + field population | `test_configuration.py::TestGoverned.test_takeover_mode_shape` |
| `test_load_takeover_mode_from_json` | JSON reading (general config loading) | `test_configuration.py` load_configuration tests |
| `test_merge_takeover_mode_from_multiple_files` | Pattern union across levels | `test_configuration.py::TestTakeoverEnabledResolution.test_pattern_lists_union_across_three_levels` |
| `test_deny_fallback_silent` | `no_match_fallback = "deny"` | `test_configuration.py::TestGoverned.test_takeover_mode_shape` |
| `test_warn_deny_fallback` | `no_match_fallback = "warn_deny"` | `test_configuration.py::TestTakeoverEnabledResolution.test_no_match_fallback_more_specific_wins` |
| `test_no_takeover_mode_section_uses_defaults` | enabled=False default | `test_configuration.py::TestTakeoverEnabledResolution.test_enabled_off_when_no_level_sets_it` |

### Tests ported (2 tests)
Both re-target `load_configuration(...).takeover_mode()`:

1. **`test_default_config_when_no_files`** - Verifies that with no toolguard_hook
   files at all, the default `TakeoverConfig` has `enabled=False`, all default
   blanket patterns present, `additional_ignored_patterns=()`, and
   `no_match_fallback='deny'`. Updated docstring and assertion style
   (tuple attributes instead of dict keys).

2. **`test_takeover_mode_not_loaded_from_claude_settings`** - Verifies that
   `takeover_mode` defined in `settings.local.json` is ignored. Updated API call;
   intent and assertions unchanged.

### Tests kept unchanged (5 tests)
All tests in `TestFilePathToolTakeoverFiltering` use `load_file_path_patterns`
from `toolguard.hook` and have no dependency on the legacy loader. Kept as-is.

### Tests added (4 tests) - Class `TestBashTakeoverFiltering`
These address the Task 2 gap (see below):

1. `test_native_blanket_bash_allow_suppressed_when_takeover_enabled` - With
   takeover ON, native `Bash(*)` is suppressed; hook deny for `rm *` fires.
2. `test_native_blanket_bash_allow_not_suppressed_when_takeover_disabled` -
   With takeover OFF, the deny still fires due to deny-first within a level
   (hook is most-specific). Confirms behaviour is consistent regardless.
3. `test_toolguard_hook_bash_allow_not_filtered_by_takeover` - Hook's `Bash(*)`
   is never filtered even when takeover is ON.
4. `test_native_bash_allow_suppressed_specific_command_denied` - Native `Bash(*)`
   suppressed + hook only allows `git *` => `ls /tmp` is denied fail-closed.

---

## Task 3 (Task 2 in prompt): Live Bash Takeover Filtering Coverage

### Finding
There was a **genuine gap**. The existing `test_takeover_filters_native_allow_only`
in `test_configuration.py` (line 233) tested the filtering mechanism at the
`permission_layers()` level but only for `Read(*)`, not `Bash(*)`. No test
exercised the full `resolve_permission_detailed` path with a native `Bash(*)`
being suppressed.

The `permission_layers()` code at line 1131 is tool-agnostic
(`if takeover.enabled and layer.is_native and pattern in ignored:`), so the
mechanism is the same for Bash and Read. However, having a test that goes
end-to-end through `resolve_permission_detailed` is valuable because it confirms
the pattern flows correctly from filtering through the level cascade to a final
deny decision.

The 4 new tests in `TestBashTakeoverFiltering` fill this gap.

---

## Self-Review Results

- No async/await, no threading, no local imports.
- All modified files pass `uv run ruff check`.
- All 725 tests pass (`uv run python -m unittest discover -s test -t .`).
- `grep -rn load_takeover_mode_config toolguard/ test/` shows zero references
  in production code and tests (only a comment in the test file docstring noting
  the migration).
- No git operations performed.

---

## Files Changed

1. `toolguard/scripts/migrate_permissions.py` - Remove import; reuse Configuration
2. `toolguard/config.py` - Delete function; update 2 comments
3. `test/unit/test_takeover_mode.py` - Port/drop/add tests (net -2 tests)

## Elapsed Time by Phase

- Phase 1 (Planning + memory): ~6 minutes
- Phase 2 (Implementation): ~10 minutes
- Phase 3 (Self-review + ruff): ~3 minutes
- Phase 4 (Report): ~3 minutes
- **Total: ~22 minutes**

## Estimated Cost

- Input tokens: ~120k, Output tokens: ~15k
- Estimated cost: ~$0.80 (Sonnet 4.6 pricing)
