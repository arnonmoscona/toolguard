---
title: TOO-30 Coder Implementation Report - GREEN Phase
type: note
permalink: toolguard/too-30/too-30-coder-implementation-report-green-phase
---

## Summary

Implemented `toolguard/config.py` to make all 16 previously-red TOO-30 rules-directory
tests (in `test/unit/test_configuration.py`) pass, with zero test changes and zero
regressions. Also updated documentation per the ticket's checklist. Final suite: 1511
tests, 0 failures, 0 errors. `ruff check .` clean.

## Files changed

- `toolguard/config.py` (+221/-11) -- the only production code change
- `docs/configuration.md` (+48) -- new "Split user-level rules directory" subsection under
  "Configuration hierarchy", plus a worked example referencing `gh-cli-rules-example.toml`
- `docs/architecture.md` (+13) -- second resolution-log example entry showing a
  rules-dir-sourced provenance tag (`[user: ~/.config/toolguard/rules/gh.toml]`)

No test file was modified (verified: `git diff --stat` shows `test_configuration.py`/
`test_takeover_mode.py` changes are the pre-existing RED-phase diff, not touched this
session).

## What was implemented (matches the 9-item contract)

1. `_rules_dir()` -- new private fn, XDG_CONFIG_HOME-aware with empty-string treated as unset.
2. `_discover_rules_files(rules_dir) -> List[Tuple[Path, str]]` -- flat scan, TOML-over-JSON
   per stem, lexicographic order. Refactored to share a `_group_rules_files_by_stem()`
   helper (see deviation #1 below).
3. `_discover_levels()` -- appends rules-dir entries after the primary `~/.claude`
   candidates, at `specificity = len(level_dirs) - 1` (the user level).
4. `_level_for_path()` -- extended to also recognize paths under `_rules_dir()` as `'user'`.
5. `ConfigLayer.unexpected_keys: Tuple[str, ...] = ()` -- added as specified.
6. `load_configuration()` -- for `toolguard_hook_rules` entries, computes
   `unexpected_keys` and filters `content` down to `{"permissions", "hard_deny"}` before
   constructing the layer.
7. `Configuration.validation_issues()` -- new check appends an error `Issue` per layer with
   non-empty `unexpected_keys`, citing `provenance.describe_brief()` and the key name(s);
   does not block the layer's valid content from resolving.
8. `CLAUDE_SETTINGS_PATH` -- confirmed no code change needed; the explicit-branch already
   returns before `_discover_levels()`. `TestRulesDirectoryExplicitModeBypass` passes.
9. Confirmed no changes needed to `hard_deny()`, `permission_layers()`,
   `permission_levels_with_provenance()`, `resolve_permission_detailed()`,
   `allow_deny_for()`, `governed_tools()`, `scalar()`, `takeover_mode()`,
   `resolved_no_match_fallback()`, `toolguard_permissions()` -- all already generic over
   `self.layers`.

## Deviation from the exact spec (with justification)

**Added one extra field beyond the specified `unexpected_keys`: `ConfigLayer.duplicate_format:
bool = False`, plus a small shared helper `_group_rules_files_by_stem()`.**

Reason: `test_rules_dir_duplicate_toml_json_only_toml_layer_and_warning_end_to_end` calls
`config.validation_issues()` *after* both the `_isolated_hierarchy` context manager and the
outer `tempfile.TemporaryDirectory()` have exited -- i.e. after the rules directory has
been deleted from disk. The pre-existing "both TOML and JSON exist" detection in
`validation_issues()` (item 1, pre-dating this ticket) has two paths: (a) two literal
layers of differing format at the same base -- not applicable here, since
`_discover_rules_files()` is contractually required to drop the JSON sibling and produce
only one layer; or (b) a live on-disk `.exists()` check as a fallback for exactly the
single-surviving-layer case -- which fails once the directory is gone.

Since the directory is guaranteed to exist while `_discover_rules_files()` runs (inside
`load_configuration()`, still inside the test's `with` blocks), I record the "this stem had
a same-format sibling that lost precedence" fact on the layer itself at discovery time,
so `validation_issues()` never needs to touch the filesystem again. Implementation:
extracted the existing by-stem grouping logic already inside `_discover_rules_files()` into
a small shared private helper (`_group_rules_files_by_stem`), reused it once (memoized per
`load_configuration()` call) to compute the duplicate-stem set, and set
`ConfigLayer.duplicate_format` accordingly. `validation_issues()` item 1 now ORs this flag
in alongside the pre-existing disk check, leaving the `~/.claude` code path (and the
existing `test_duplicate_toml_json_issue` unit test, which constructs two literal layers
directly) completely unaffected.

Both new fields default to falsy values (`()` / `False`), so every existing direct-
construction call site (production and tests) is unaffected -- same backward-compatibility
property the task spec required for `unexpected_keys` alone.

I considered NOT adding a new field and instead re-deriving the warning purely from
`self.layers` data, but since `_discover_rules_files()`'s own unit tests (and this same
end-to-end test) fix the contract at exactly one surviving layer per duplicate stem, there
is no way to reconstruct "a sibling existed" from the surviving layer alone without some
persisted signal. This was the smallest, most DRY, most backward-compatible way to do it.

## Verification results

1. `uv run python -m unittest discover -s test -t .` -- **1511 tests, 0 failures, 0
   errors** (all 16 target tests flipped green; `test_takeover_mode.py` and everything
   else stayed green).
2. `uv run ruff check .` -- **All checks passed.** (`ruff format` was NOT run, per the
   project-specific override in the task brief and `project_ruff_strips_except_parens`
   memory.)
3. `uv run python -m py_compile toolguard/config.py` -- compiles cleanly.
4. Anti-pattern scan of the diff: no `async`/`await`, no `threading`/`Thread`, no local
   (in-function) imports, no unused imports.
5. `git diff --stat` confirms only `toolguard/config.py` + the two doc files changed by
   this session; no test file was touched.

## Notes / limitations

- The doc task said "the three doc files" but only two files needed edits
  (`docs/configuration.md`, `docs/architecture.md`); the third checklist item ("worked
  example referencing `docs/gh-cli-rules-example.toml`") is satisfied as *content inside*
  `docs/configuration.md` referencing the existing example file -- that file itself needed
  no changes (verified it already contains only a `[permissions]` section, so it's a valid
  rules-directory file as-is).
- Did not touch `discover_config_files()` (legacy two-level, migrate_permissions.py target
  selection) or any PEG/grammar file, per the explicit "do not" list.
- Left the suite-wide `Path.home()` test-isolation retrofit (tracked separately in
  "TOO-30 pre-push follow-up: suite-wide test isolation cleanup") untouched -- out of
  scope for this GREEN phase.

## Elapsed time / cost estimate

- Setup (ticket/memory read, baseline test run): ~7 min
- Reading config.py + test file in full, understanding contract: ~10 min
- Implementation (items 1-7) + first full test run: ~10 min
- Debugging + fixing the one remaining failure (duplicate_format field): ~10 min
- Documentation updates: ~8 min
- Self-review, ruff/compile checks, report writing: ~8 min
- **Total elapsed: ~53 min**
- Estimated cost (Sonnet 5, this size of task -- file reads, several edits, a few test
  runs): roughly $2-3.
