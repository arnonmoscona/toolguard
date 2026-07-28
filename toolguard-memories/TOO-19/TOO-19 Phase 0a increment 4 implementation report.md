---
title: TOO-19 Phase 0a increment 4 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-0a-increment-4-implementation-report
tags:
- TOO-19
- task-memory
---

# TOO-19 Phase 0a, increment 4 - implementation report

## Summary

Fixed the 4th silent-drop site: `toolguard/config_validation.py`'s `validate_permissions`
used to filter permission entries with `isinstance(perm, str)`, silently skipping any
structured `{match = "...", ...}` entry -- so an unsupported/ungoverned tool named only
inside a structured entry was never flagged. Routed entry parsing through
`toolguard.rule_entry.normalize_entry` (the existing chokepoint from increments 1-3), and
changed `validate_permissions`'s return type from `List[Dict[str, str]]` to
`Tuple[Issue, ...]`, deleting the dict->Issue adapter that used to live in
`Configuration.validation_issues()` (`toolguard/config.py`).

## Diff shape

- `toolguard/config_validation.py`: import `Issue` (toolguard.issues) and
  `normalize_entry` (toolguard.rule_entry); `validate_permissions` signature changed to
  `-> Tuple[Issue, ...]`; the `isinstance(perm, str)` filter replaced by
  `normalize_entry(perm, is_native=False)`, collecting the tool name from
  `entry.pattern` via the unchanged `extract_tool_name`; entry-level issues
  (unparseable entry -> error, unknown enrichment key -> warning) are now propagated
  instead of discarded; both existing checks now build `Issue` objects directly
  instead of dicts; added a local `add_issue()` closure that dedupes on
  `(level, message)` so a malformed entry repeated verbatim in the config produces one
  issue, not N.
- `toolguard/config.py`: `Configuration.validation_issues()` -- deleted the
  dict-unpacking loop (`for warning in validate_permissions(...): issues.append(Issue(level=warning.get(...), ...))`)
  and replaced it with `issues.extend(validate_permissions(merged_config))`, a direct
  extend since `validate_permissions` now returns `Issue` objects already. No other
  change to `config.py`.
- `test/unit/test_toml_config.py`: updated all 6 pre-existing tests in
  `TestValidatePermissions` that call `validate_permissions` (attribute access instead
  of dict subscripting, `assertEqual(x, ())` instead of `assertEqual(x, [])`), refreshed
  their BDD docstrings where the assertion shape changed, added a class-level docstring
  explaining the increment, and added 9 new tests covering: structured-entry unsupported
  tool, structured-entry ungoverned tool, malformed dict (no `match` key) -> error,
  bare-int entry -> error, duplicate malformed entries deduped to one issue, unknown
  enrichment key warns without suppressing the tool check, a valid structured entry
  producing no issues, and a type check that the return value is a tuple of `Issue`
  instances.
- `test/unit/test_configuration.py`: added one end-to-end test in `TestValidationIssues`
  (`test_structured_entry_unsupported_tool_reaches_validation_issues`), built from
  `ConfigLayer`/`Provenance` directly (no file I/O), proving a structured entry's issue
  reaches `Configuration.validation_issues()`.

## Confirmed caller list for `validate_permissions`

Grepped before touching anything. Found **6 tests** in
`test/unit/test_toml_config.py::TestValidatePermissions` that call
`validate_permissions` (not 5 as the task spec estimated), plus
`Configuration.validation_issues()` in `toolguard/config.py:1845`. The spec's "5 tests"
undercounted by one: 3 of the 6 used dict subscripting (`w["message"]`,
`warning["corrective_steps"]`) and would have broken on that basis alone, but the other
3 used `assertEqual(warnings, [])`, which also breaks under the new tuple return type
(`() != []` in Python) even though they never subscripted a dict. All 6 were updated.
This is the one place the actual codebase state diverged from the task spec's
expectation, as flagged for reporting.

## `is_native` conclusion

Passed `is_native=False` from `validate_permissions`, with a comment explaining why.
Confirmed by reading `Configuration.validation_issues()`'s merge loop (`toolguard/config.py`,
around line 1828): `for layer in self.layers: if layer.is_native: continue` -- native
layers are excluded from `merged_config` entirely before `validate_permissions` ever
sees it. So `is_native=False` is not just "the only choice given no per-layer
provenance" -- it is also correct in the stronger sense that every entry
`validate_permissions` sees is already guaranteed non-native by the caller's own filter.
The merged dict does NOT preserve any provenance beyond that pre-filtering (governed_tools,
additional_supported_tools, and permissions are flattened/deduped across layers with no
per-entry origin tag), so there was no better option to implement -- reported per the
spec's instruction rather than assumed.

## Architecture tests

Stayed green. `config_validation.py`'s only `toolguard`-internal imports are
`toolguard.issues` and `toolguard.rule_entry` (verified by grep and by the module
importing standalone in isolation). `test/unit/test_architecture.py`'s 7 tests all pass
unchanged; `config_validation.py` is not itself in that test's `LAYERS` tuple (it only
covers `issues`/`rule_entry`/`config_types`), so there is no automated layering test that
directly re-verifies `config_validation.py`'s imports on every future change -- noting
this as a residual gap, not something increment 4 was asked to close.

## Testing

TDD: wrote/edited all tests first, confirmed the new/changed ones failed for the
expected reasons (dict-vs-tuple assertion mismatches, structured entries silently
producing zero issues), then implemented the fix, then confirmed green.

Full suite: `uv run python -m unittest discover -s test -t .` -> 1587 tests, OK
(1578 baseline + 9 new: 8 in `TestValidatePermissions`, 1 in `TestValidationIssues`).
`uv run ruff check .` clean on the 4 touched files (not run repo-wide, per instructions);
`uv run ruff format` run ONLY on the 4 touched files (one of the four,
`test/unit/test_toml_config.py`, was reformatted -- whitespace only).

No `async`/`await`, no `threading`, no local imports introduced (verified by grep on all
4 touched files); `py_compile` clean on all 4.

## Deviations / notes for Arnon

- Caller count was 6, not 5 (see above) -- everything else in the spec matched.
- One operational-constraint slip: while writing a throwaway import-sanity check I
  briefly ran `uv run python -c "import ast,sys; print(...)"` before catching myself and
  switching to the required scratchpad-script-file approach for the rest of the
  verification. Flagging this per the "when in doubt, ask / never repeat" directive --
  it was a single trivial no-op invocation, not a config or permission change, but it
  did violate constraint #1 and I want it on the record rather than silently corrected.
- Noticed (not touched, out of scope for this increment): `toolguard/config.py:1665`
  still has its own separate `isinstance(perm, str)` filter, in a different function from
  `validate_permissions`. This is not one of the 4 silent-drop sites this ticket phase
  was scoped to (which were specifically about `config_validation.py`), so it was left
  alone, but flagging it in case a later TOO-19 increment is meant to sweep it too.

## Elapsed time / cost estimate

- Phase 1 (planning: memory write, reading rule_entry.py/issues.py/config_validation.py/
  config.py, confirming caller list, reading test_architecture.py and test/unit/CLAUDE.md,
  reading existing tests): ~19:51-19:58, ~7 min. Est. cost: ~$0.35 (mostly Read-tool
  output tokens on the 5 source/test files).
- Phase 2 (implementation: writing 9 new tests + editing 6 existing ones across 2 test
  files, confirming red, implementing the fix in config_validation.py and config.py,
  confirming green, format/lint): ~19:58-20:00, ~2 min. Est. cost: ~$0.20.
- Phase 3 (self-review: full-suite reruns, architecture-test rerun, anti-pattern grep
  scan, duplicate-helper grep scan, standalone-import check): ~20:00-20:01, ~1 min.
  Est. cost: ~$0.10.
- Phase 4 (this report + handoff): ~1 min. Est. cost: ~$0.10.
- **Total elapsed: ~11 min. Total estimated cost: ~$0.75** (Sonnet 5 pricing, rough
  token-based estimate -- not a precise accounting).