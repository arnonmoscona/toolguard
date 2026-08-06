---
title: TOO-45 R2 coder task recall
type: note
permalink: toolguard/too-45/too-45-r2-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Implement TOO-45 step R2 in /home/arnon/projects/toolguard on branch too-45 (feature-coder subagent run).

Goal: no parallel arrays; stripped patterns are a DERIVED property of `RuleEntry`; no prose-defended index-alignment invariant remains. `--predicates` currently reports 3 index-parallel access sites (config:1341 zip, config:1505 index, resolve:294 index) and 2 drift guards (config:1503, resolve:292), all gating 'pass'. Must go to 0/0.

Do R2a+R2b+R2c as one change, then R2d, per the brief. Drift guards are dead code (0/0 hits over 3996 corpus lookups) -- delete them, delete the two tests that exist only to fire the config.py one synthetically (test_configuration.TestEntryForPatternDrift), keep/adapt the third (aligned-layer) test. resolve.py's guard is pinned by zero tests.

## Plan (confirmed by reading source before editing)

1. `toolguard/rule_entry.py`: add `RuleEntry.stripped_pattern` property (wraps `_strip_tool_wrapper(self.pattern)`).
2. `toolguard/config_types.py`:
   - `ToolPatternLayer`: drop `allow`/`deny`/`ask` as stored fields; keep only `provenance`, `allow_entries`, `deny_entries`, `ask_entries` (all default `()`); add `allow`/`deny`/`ask` as derived `@property` (tuple of `entry.stripped_pattern` over the entries). Rewrite the class docstring to drop the "index-for-index invariant" paragraph (config_types.py:161-165) -- misaligned state becomes unconstructible, nothing to invariant-check.
   - Add module-level `_entries_for_kind(layer, kind)`, `provenance_for_pattern(layers, pattern, kind)`, `entry_for_pattern(layers, pattern, kind)` -- moved from `Configuration` (R2d), reimplemented as a direct linear search over entries (`entry.stripped_pattern == pattern`), no `.index()`, no drift guard needed (only one sequence).
3. `toolguard/config.py`:
   - `_extract_tool_entries`: return only `Tuple[RuleEntry, ...]` (drop the `patterns` tuple -- every caller already discards or can discard it).
   - `_pool_hard_deny_entries`: update the two call sites to the new one-value return.
   - `hard_deny()`: build stripped patterns via `entry.stripped_pattern` instead of `_strip_tool_wrapper(entry.pattern)`.
   - `permission_layers()`: build `ToolPatternLayer(provenance=..., allow_entries=..., deny_entries=..., ask_entries=...)` (no `allow=`/`deny=`/`ask=` kwargs); takeover filter rewritten to filter `allow_entries` directly on `entry.stripped_pattern not in ignored` -- deletes the `zip(allow, allow_entries)` at config.py:1341.
   - DELETE the `provenance_for_pattern`/`entry_for_pattern` `@staticmethod`s (config.py:1418-1506) entirely -- moved to config_types.py, no pass-through shim left on `Configuration`.
   - Remove `from toolguard.rule_entry import _strip_tool_wrapper` import if it becomes unused (verify after edits -- only 3 call sites existed, all removed/replaced).
   - Reword `hard_deny_entries()`'s docstring (config.py:1221-1224) to drop the "index-aligned...never populate one without the other" invariant framing -- nothing relies on it after R2c.
4. `toolguard/resolve.py`: `_hard_deny_additional_context` -- rewrite to call only `config.hard_deny_entries(tool_name)` and do a direct linear search (`entry.stripped_pattern == matched_pattern`) instead of `config.hard_deny()` + `.index()` + length guard. Drop the length-guard clause and its docstring paragraph (resolve.py:268-272, resolve.py:292).
5. `toolguard/permission_resolution.py`: import `provenance_for_pattern`, `entry_for_pattern` from `toolguard.config_types` directly (not through `config.`); update both call sites (`_detect_override`, `_resolve_unclamped`); update the module docstring's "six-member surface" list to drop the two relocated members (now four).
6. Doc-drift sweep (mechanical, same string in >1 place): `toolguard/permissions.py:134` (`Configuration.provenance_for_pattern` reference) and `tools/corpus_build.py:474` (`Configuration.provenance_for_pattern` / `entry_for_pattern` reference) -- update to point at `config_types.provenance_for_pattern`/`entry_for_pattern`. Light tense fix in `tools/architecture_fitness.py`'s `find_index_parallel_access`/`find_drift_guards` docstrings if time permits (optional, not required for acceptance).

## Test changes (mechanical, per the brief's explicit sign-off)

- `test/unit/test_configuration.py::TestEntryForPatternDrift`: DELETE `test_misaligned_layer_returns_none_instead_of_falling_through` and `test_drift_does_not_change_the_resolved_verdict` (construct a drifted `ToolPatternLayer` by passing mismatched `allow=`/`allow_entries=` -- unconstructible once `allow` is a derived property, not a field). KEEP `test_aligned_layer_still_resolves_normally`, adapted: call `entry_for_pattern` (imported from `config_types`) instead of `Configuration.entry_for_pattern`; drop the now-nonexistent `allow=`/`deny=` constructor kwargs. Consider renaming the class since "drift" no longer applies, and adding one new positive test that constructing `ToolPatternLayer(allow=..., ...)` now raises `TypeError` (misaligned state is unconstructible -- the actual R2 claim, worth a regression test).
- `test/unit/test_logging_streams.py::TestProvenanceHelpers.test_provenance_for_pattern_returns_none_on_miss`: update call target from `Configuration.provenance_for_pattern` to the `config_types` import.
- `test/unit/test_hook.py::_make_config`'s `_FakeConfig`: DELETE the `provenance_for_pattern`/`entry_for_pattern` stub methods (lines ~168-177) -- production no longer calls them through `config` at all after R2d, so the fake no longer needs to model them. Update the comment at line ~152 that references them.
- `test/unit/test_architecture_fitness.py`: `test_real_tree_finds_all_three_known_instances` (line ~1943) and `test_real_tree_finds_both_known_drift_guards` (line ~2030) currently pin the PRE-R2 real-tree state (3 sites / 2 guards) -- these are tests of the fitness DETECTOR pinned against the very hazard R2 deletes, so update them to assert the post-R2 state (0 hits) with an updated Given/When/Then, per the "delete/update tests that pin exactly the deleted code" exception. The detector functions themselves (`find_index_parallel_access`, `find_drift_guards`) are NOT being touched -- only what they find on the real tree changes.

## Acceptance commands (must paste real output)

```
uv run python -m unittest discover -s test -t .
uv run python tools/corpus_build.py --verify
uv run python tools/architecture_fitness.py --guard
uv run python tools/architecture_fitness.py --layers
uv run python tools/architecture_fitness.py --predicates
uv run ruff format . && uv run ruff check --no-cache .
```

## Hard rules for this session

- No git writes of any kind (read-only git only).
- Backups to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r2-backups/` BEFORE any edit, verified with sha256sum.
- INTENT/TOUCHES disclosure + `TG_INTENT=1`/`TG_ATTEST_READONLY=1` on any inline/heredoc/scratch-script Bash command.
- uv run python, never bare python. unittest, not pytest.
- Do not touch the two permission files (denied to agent).
- Report to basic-memory `TOO-45/TOO-45 R2 implementation report.md`, tagged task-memory + TOO-45.
