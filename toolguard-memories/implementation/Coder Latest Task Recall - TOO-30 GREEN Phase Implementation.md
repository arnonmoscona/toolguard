---
title: Coder Latest Task Recall - TOO-30 GREEN Phase Implementation
type: note
permalink: toolguard/implementation/coder-latest-task-recall-too-30-green-phase-implementation
---

## Task
TDD phase 2 (GREEN) for TOO-30. RED phase (test/unit/test_configuration.py,
test/unit/test_takeover_mode.py) is done and reviewed. Implement ONLY toolguard/config.py
(plus 3 doc files) so all 16 currently-red tests go green, zero test changes, zero
regressions.

## Exact design contract
1. `_rules_dir() -> Path` (new private fn): XDG_CONFIG_HOME/toolguard/rules if
   XDG_CONFIG_HOME set+non-empty in env, else Path.home()/.config/toolguard/rules.
   Empty-string XDG_CONFIG_HOME = unset, fall back to default.
2. `_discover_rules_files(rules_dir: Path) -> List[Tuple[Path, str]]` (new private fn):
   flat non-recursive scan for *.toml/*.json. Missing/empty dir -> []. Same-stem
   toml+json -> only toml entry ("toml"). Sorted lexicographically by stem ascending.
   Each entry (path, "toml"|"json").
3. `_discover_levels()`: after building level_dirs (ends with ~/.claude at index
   len(level_dirs)-1), append entries for every file from
   _discover_rules_files(_rules_dir()), each as
   (path, "toolguard_hook_rules", file_format, user_specificity) where
   user_specificity = len(level_dirs)-1. Must come AFTER existing per-level_dir loop
   results (append at very end of function).
4. `_level_for_path(path)`: also return 'user' for paths under _rules_dir(), 'project'
   otherwise (unchanged for all other cases).
5. `ConfigLayer` dataclass: add field `unexpected_keys: Tuple[str, ...] = ()` (default
   empty tuple, backward compatible with existing direct-construction call sites).
6. `load_configuration()`: in loop building layers from _discover_levels(), for entries
   with source_type == "toolguard_hook_rules": compute
   unexpected_keys = tuple(k for k in content if k not in {"permissions", "hard_deny"}),
   then replace content with dict containing only permissions/hard_deny keys actually
   present, before wrapping in MappingProxyType and constructing ConfigLayer with that
   unexpected_keys. Layers from ~/.claude files (source_type 'claude'/'toolguard_hook')
   unaffected.
7. `Configuration.validation_issues()`: for every layer with non-empty unexpected_keys,
   append one Issue(level="error", message=..., corrective_steps=...). Message MUST
   include layer.provenance.describe_brief() AND the offending key name(s) (test asserts
   both substrings present plus literal "governed_tools" for the test fixture). Does NOT
   gate/block anything else.
8. CLAUDE_SETTINGS_PATH: no code change needed - explicit-single-file branch already
   returns before _discover_levels(). Just confirm
   TestRulesDirectoryExplicitModeBypass passes.
9. Everything else (hard_deny(), permission_layers(), permission_levels_with_provenance(),
   resolve_permission_detailed(), allow_deny_for(), governed_tools(), scalar(),
   takeover_mode(), resolved_no_match_fallback(), toolguard_permissions()) needs NO
   changes - already generic over self.layers.

## What NOT to do
- Do not touch any test file.
- No feature toggle to disable rules-dir.
- Do not change discover_config_files() (legacy 2-level, used by migrate_permissions.py).
- No new runtime dependency, stdlib only.
- No PEG/grammar files involved.

## Documentation (after tests green)
- docs/configuration.md "Configuration hierarchy" section
- docs/architecture.md provenance example
- Worked example referencing docs/gh-cli-rules-example.toml as
  ~/.config/toolguard/rules/gh.toml

## Verification steps
1. uv run python -m unittest discover -s test -t . -> 1511+ passing, 0 fail/error
2. uv run ruff check . -> clean. Do NOT run ruff format (project override - would
   corrupt except tuples / churn quotes)
3. git diff --stat -> only toolguard/config.py + 3 doc files changed, no test files
4. Write report to basic-memory project='toolguard' directory 'TOO-30'

## Baseline before starting
1511 tests, 16 failing (6 failures + 10 errors) all in
test.unit.test_configuration.TestRulesDirectory* classes. Everything else including
test_takeover_mode.py green.
