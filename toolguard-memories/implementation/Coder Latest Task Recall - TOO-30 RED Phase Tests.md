---
title: Coder Latest Task Recall - TOO-30 RED Phase Tests
type: note
permalink: toolguard/implementation/coder-latest-task-recall-too-30-red-phase-tests
---

## Task

TDD phase 1 (RED) for TOO-30 in toolguard. ONLY write new unit tests in
`test/unit/test_configuration.py`. Do NOT touch `toolguard/config.py` or any other
production code. Do NOT modify any other file.

## Feature under test (not yet implemented)

TOO-30 adds an optional discovery step: scan `$XDG_CONFIG_HOME/toolguard/rules/`
(default `~/.config/toolguard/rules/`) for any number of `*.toml`/`*.json` files
(flat, non-recursive). Each file uses the toolguard_hook schema but restricted to
`[permissions]` and `[hard_deny]` only. All merge into the existing USER level (same
specificity as `~/.claude/toolguard_hook.toml`) -- not a new hierarchy level.

## Exact API contract to test against

1. `toolguard.config._rules_dir() -> Path` (new): `$XDG_CONFIG_HOME/toolguard/rules` if
   XDG_CONFIG_HOME set+non-empty, else `~/.config/toolguard/rules`.
2. `toolguard.config._discover_rules_files(rules_dir: Path) -> List[Tuple[Path, str]]`
   (new): flat scan for `*.toml`/`*.json`. Missing/empty dir -> `[]`. Same stem
   `.toml`+`.json` -> only `.toml` entry (format string "toml"), json sibling dropped.
   Other extensions/subdirs ignored. Sorted lexicographically by filename stem asc.
   Entries `(path, "toml"|"json")`.
3. `toolguard.config._discover_levels()` (existing): gains entries per rules file, each
   `(path, "toolguard_hook_rules", file_format, specificity)` where specificity == same
   int as user `~/.claude` level (`len(level_dirs) - 1`). Come AFTER the 4 primary
   `~/.claude` candidates. Only test end-to-end via `load_configuration()` -- do not
   import this private name at module level.
4. `toolguard.config._level_for_path(path)` (existing): must also return 'user' for
   paths under `_rules_dir()`, 'project' otherwise (unchanged).
5. `toolguard.config.ConfigLayer` (existing frozen dataclass): new field
   `unexpected_keys: Tuple[str, ...] = ()` default empty, backward compatible.
6. `toolguard.config.load_configuration()`: for layers with
   `source_type == "toolguard_hook_rules"`, `layer.content` restricted to only
   `"permissions"`/`"hard_deny"` top-level keys; other keys dropped from content and
   recorded in `unexpected_keys`. `~/.claude` layers unaffected (`unexpected_keys` stays
   `()`).
7. `toolguard.config.Configuration.validation_issues()` (existing): new check -- for
   every layer with non-empty `unexpected_keys`, append one error-level `Issue` naming
   the file (via `layer.provenance.describe_brief()`) and the offending key(s). Does NOT
   block that layer's valid permissions/hard_deny content from taking effect.
8. CLAUDE_SETTINGS_PATH: explicit-single-file branch in `load_configuration()` returns
   BEFORE `_discover_levels()` is called -- rules-dir files never scanned. No new prod
   code needed -- just a test.
9. hard_deny pooling, `toolguard_permissions()`, `[regex]`/`[glob]`/`[native]` extended
   syntax, more-specific-wins, deny-wins-within-level all need NO new code (already
   iterate `self.layers` generically) -- write tests confirming rules-dir-sourced
   permissions flow through these EXISTING paths correctly once layers exist.

## Test scenarios (from prompt, one test method per scenario, add more if gaps found)

Discovery: missing dir no-op; empty dir no-op; N files all become layers in
lexicographic-by-stem order; same-stem toml+json -> only toml layer + "both formats"
validation warning fires for rules-dir files too; XDG_CONFIG_HOME set vs unset default;
.txt file and subdirectory ignored.

Merge semantics: rules-dir file's permissions merge into same level as
~/.claude/toolguard_hook.toml (single level entry in
`permission_levels_with_provenance`); project-level deny still overrides rules-dir
allow; within user level, rules-dir deny beats ~/.claude allow (deny-wins-within-level
spanning sources); rules-dir hard_deny pooled by `hard_deny()`; rules-dir file setting
governed_tools/no_match_fallback/takeover_mode.enabled has ZERO effect (confirms
section restriction actually filters, not just records); `toolguard_permissions()`
includes rules-dir patterns; regex/glob/native prefix pass-through works (one test).

Validation/provenance: unexpected top-level key alongside valid permissions ->
validation_issues() reports exactly one error Issue naming file+key, valid permissions
still resolve; rules-dir layer has provenance.level == 'user' and exact path;
`resolve_permission_detailed()`'s reason string cites the rules-dir file path.

CLAUDE_SETTINGS_PATH: set + rules-dir files present on disk -> none appear in
config.layers.

## Test hygiene

Keep existing top-of-file `from toolguard.config import (...)` UNCHANGED (only
currently-existing names). For not-yet-implemented names
(`_rules_dir`, `_discover_rules_files`, new `_level_for_path` behavior,
`ConfigLayer.unexpected_keys`, new validation_issues check): either drive end-to-end
via public `load_configuration()`/`Configuration` API (preferred), or for true
white-box unit tests of `_rules_dir()`/`_discover_rules_files()` in isolation, do
`import toolguard.config as config_module` near the new test classes and reference
`config_module._rules_dir(...)` etc. INSIDE test method bodies only (never at module
level) so a missing attribute fails only that one test, not collection.

Follow existing file conventions: `unittest.TestCase` classes, BDD Given/When/Then
docstrings per CLAUDE.md, `_make_project()` helper pattern. Isolate rules dir via
`tempfile.TemporaryDirectory()` + `patch.dict(os.environ, {"XDG_CONFIG_HOME": tmp},
clear=True)` mirroring existing CLAUDE_SETTINGS_PATH tests. New TestCase classes
appended at end of file (after `TestExplicitModeAdjacentToml`):
`TestRulesDirectoryDiscovery`, `TestRulesDirectoryMergeSemantics`,
`TestRulesDirectoryValidationAndProvenance`, `TestRulesDirectoryExplicitModeBypass`.

## What to run/report

1. `uv run python -m unittest discover -s test -t .` -- full tally, all pre-existing
   tests must still pass (collection must succeed). New tests expected to fail --
   report each: assertion failure (feature not wired) vs attribute/name error (helper
   not implemented) -- both valid red states.
2. `uv run ruff check .` must be clean. Do NOT run `uv run ruff format` (project
   override: no ruff style config, format corrupts `except (A, B):` tuples).
3. Report to basic-memory project='toolguard' directory='TOO-30' documenting exactly
   which test methods added per scenario + red-state tally.

## Constraints

- Do NOT touch toolguard/config.py or any other production code.
- Do NOT modify any file other than test/unit/test_configuration.py.
