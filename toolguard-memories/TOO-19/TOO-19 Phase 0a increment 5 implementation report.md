---
title: TOO-19 Phase 0a increment 5 implementation report
type: report
permalink: toolguard/too-19/too-19-phase-0a-increment-5-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Fixed two defects in `toolguard/tools/config_access.py::with_layer_rules_replaced`
(delegated to by `with_layer_allow_replaced`):

- **Defect A**: crashed with `TypeError: cannot use 'dict' as a set element` when a
  target permission list contained a structured (dict) entry, because removal
  membership was tested via `element not in wrapped_removed` (a `Set[str]`).
- **Defect B**: the rebuilt `ConfigLayer` silently reset `unexpected_keys`,
  `duplicate_format`, and `shadowed_path` to their defaults.

## Fix (diff shape)

Single production file changed: `toolguard/tools/config_access.py`.

1. Added `from toolguard.rule_entry import normalize_entry` (leaf-module import,
   confirmed against `test/unit/test_architecture.py` layering rules -- passes).
2. Added `replace` to the existing `from dataclasses import dataclass` import.
3. Replaced the one-line list comprehension with an explicit loop: each element of
   `target_list` is run through `normalize_entry(element, is_native=layer.is_native)`;
   removal is decided on `entry.pattern` (wrapper-intact, matches `wrapped_removed`'s
   form) rather than the raw element. A kept element is re-appended as the SAME
   object (str stays str, dict stays the identical dict) -- no re-rendering. An
   element that fails to normalize (`entry is None`) is kept as-is, with a comment
   noting `validate_permissions` (increment 4) is the place that surfaces those
   issues, not this function.
4. Replaced the `ConfigLayer(provenance=..., content=...)` reconstruction with
   `dataclasses.replace(layer, content=MappingProxyType(new_content))`.

No other production files touched. `with_layer_allow_replaced` needed no code change
-- it inherits both fixes purely through delegation, verified by a dedicated test.

`ruff format` was run on the whole touched file (not just the new lines), which
also reformatted several pre-existing lines elsewhere in the file (line-wrap only,
no semantic change) -- e.g. `perm[len(prefix) : -1]` spacing, a couple of
line-wrapped function signatures/calls. Confirmed via `git diff` that every removed
line has a semantically identical, only-reformatted replacement.

## Test files -- which one actually exercises these functions

Confirmed via grep (both before writing tests and empirically) that
`with_layer_rules_replaced` / `with_layer_allow_replaced` are exercised in:
- `test/unit/test_tools_edit_proposal.py` (`TestWithLayerRulesReplaced` -- the
  general, all-list-types function; also has the allow-only delegation smoke test)
- `test/unit/test_tools_consolidate.py` (`TestWithLayerAllowReplaced` -- allow-only
  usage from the consolidation engine's perspective)

`test/unit/test_tools_config_access.py` has zero references to either function --
matches the plan's claim exactly. New tests were added to the two files above, not
to `test_tools_config_access.py`.

New tests added (all with Given/When/Then docstrings, TDD red-then-green, confirmed
red for the exact `TypeError` / metadata-loss `AssertionError` before the fix):

`test/unit/test_tools_edit_proposal.py::TestWithLayerRulesReplaced`:
- `test_removing_plain_pattern_preserves_untouched_structured_entry` -- no raise,
  structured entry survives as the identical object (`assertIs`).
- `test_removing_structured_entry_by_pattern` -- removed by wrapper-free pattern body.
- `test_adding_pattern_to_list_with_structured_entry` -- append order preserved.
- `test_malformed_entry_is_preserved_not_dropped` -- dict with no `match` key kept.
- `test_layer_metadata_survives_rebuild` -- `unexpected_keys`/`duplicate_format`/
  `shadowed_path` survive (defect B).

`test/unit/test_tools_consolidate.py::TestWithLayerAllowReplaced`:
- `test_inherits_structured_entry_preservation_from_delegate` -- proves the fix is
  inherited through delegation, not re-implemented.

No isolation mixin needed for any of these (confirmed against
`test/unit/CLAUDE.md`'s checklist): all build `Configuration` directly from
hand-constructed `ConfigLayer`/`Provenance` with zero file I/O, matching the
existing pattern in both files.

## dataclasses.replace on ConfigLayer

Worked directly, no field enumeration needed. `ConfigLayer` in
`toolguard/config_types.py` is a plain `@dataclass(frozen=True)` with no
`__post_init__`/custom `__new__` that would interfere -- confirmed by reading the
class before using `replace`.

## Self-review results

- Full suite: 1587 baseline + 6 new = 1593 tests, `OK`.
- `uv run ruff check .` -- all checks passed (project-wide, not just touched files).
- `uv run ruff format` run on the 3 touched files only.
- `test/unit/test_architecture.py` -- all 7 tests green, including the layering test
  that would have caught a bad import direction; the new
  `from toolguard.rule_entry import normalize_entry` import is leaf-module-safe.
- Anti-pattern grep on touched files: no `async def`/`await`, no `threading`/`Thread`,
  no local (function-body) imports, no new bash-based file edits.
- `py_compile` clean on all 3 touched files.
- No new helper function/predicate added (avoids the duplicate-predicate risk the
  spec flagged) -- the fix is an inline loop in the one existing function.

## Nothing contradicted the spec

Everything matched: the exact crash, the exact fix shape, the test-file location
claim, and `ConfigLayer`'s dataclass-replace-ability. No scope inflation -- 1
production file modified, 2 test files extended (no new files created).
