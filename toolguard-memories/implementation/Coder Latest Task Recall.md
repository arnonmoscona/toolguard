---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- implementation
- TOO-8
- coder-recall
---

# Coder Latest Task Recall -- TOO-8 Phase 1

## Ticket / Task
TOO-8 Hierarchical Configuration. Implement **Phase 1 ONLY** (behavior-preserving
config-abstraction refactor). Plan note:
`toolguard/too-8/too-8-hierarchical-configuration-implementation-plan`.

## Phase 1 scope
Behavior-preserving refactor that fixes broken abstraction in config module. NO runtime
behavior change. Build a public `Configuration` abstraction; no code outside config module
may open config files, parse JSON/TOML, or branch on file format/location.

### Public API (names refinable)
- `load_configuration(start_dir=None) -> Configuration`
- `Configuration.governed_tools() -> tuple[str,...]` (union; default ('Bash',))
- `Configuration.takeover_mode() -> TakeoverConfig` (resolved as TODAY: enabled=OR,
  pattern lists=union, no_match_fallback=priority/last). NO Phase 5 special-case.
- `Configuration.permission_layers(tool_name) -> tuple[ConfigLayer,...]` per-layer
  allow/deny WITH provenance, most-specific first. Phase 1 callers flatten+union.
- `Configuration.validation_issues() -> tuple[Issue,...]` replaces hand-rolled walk.
- `Configuration.scalar(name, default)` resolved scalars (config-sync, backup_dir).
- Keep `CLAUDE_SETTINGS_PATH` single-file behavior, internal to module.

### Separation of concerns (hard)
- Sourcing/parsing only inside config module. Pattern matching stays in
  permissions.py/compound.py. Config has NO logging side effects: returns Issue/Conflict
  objects; hook logs. Config may READ files, not WRITE logs.
- Provenance: each layer carries display-only origin (level + path/format). No mutation.

### Immutability
tuples not lists; MappingProxyType / frozen dataclasses for Configuration / ConfigLayer /
TakeoverConfig / Issue. No deep recursive wrappers.

### Behavior-preserving constraints (critical)
- TWO levels only (project .claude + user ~/.claude). NO traversal.
- Today's resolution: union + global deny-first. NO more-specific-wins.
- ALL existing tests under test/ MUST pass UNCHANGED. If a requirement contradicts an
  existing test, STOP and report. Do not edit main test dir.
- Migrate all external clients: hook.py (main, _run_startup_validation,
  load_file_path_patterns, divergence/auto-migrate wiring) + anything else outside config
  consuming discover_config_files/load_permissions/load_governed_tools/
  load_takeover_mode_config/load_toml_config.

## Environment findings
- Project uses **unittest**, NOT pytest. pytest + pytest-cov NOT installed; `python -m
  pytest` fails. Run tests: `uv run python -m unittest discover -s test -p "test_*.py"`.
- Baseline: 563 tests, OK (clean).
- `coverage` not in venv but `uvx coverage` works (v7.14.1).
- Python >=3.14, zero runtime deps (stdlib only). Must stay stdlib-only.
- test/unit/test_config.py imports these from toolguard.config and locks their behavior:
  discover_config_files, load_governed_tools, load_governed_tools_from_file,
  load_permissions, load_permissions_from_file, merge_governed_tools, merge_permissions.
  => Must KEEP these importable with same behavior (internal shims OK).

## External clients to migrate
- hook.py: imports discover_config_files, find_project_root, load_governed_tools,
  load_permissions, load_takeover_mode_config; uses load_toml_config; _run_startup_validation
  walk; load_file_path_patterns.
- config_divergence.py get_toolguard_permissions(config_files) + check_and_warn_divergence
  (does local import of discover_config_files).
- auto_migrate.py load_config_sync_settings(config_files); run_auto_migration local-imports
  discover_config_files.
- scripts/migrate_permissions.py is a CLI tool (not hook runtime). Uses discover_config_files,
  load_takeover_mode_config. Lower priority; evaluate.
- log_writer.py / env_config.py use find_project_root only (path discovery, not config
  parsing) -- acceptable to keep.

## Success criteria
1. New config abstraction with separation of concerns.
2. All external clients migrated; zero file/format/location decisions outside config module.
3. Existing tests pass unchanged; ruff format + check clean.
4. New unit tests for public API + migrated paths; coverage target >90% new/changed.
5. Report to implementation/coder-latest-implementation-report.md.

## Stop-and-ask triggers
Abstraction ambiguity, requirement vs existing test conflict, new dependency, scope creep
beyond Phase 1. No git writes.
