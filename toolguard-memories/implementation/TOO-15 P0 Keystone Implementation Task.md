---
title: TOO-15 P0 Keystone Implementation Task
type: note
permalink: toolguard/implementation/too-15-p0-keystone-implementation-task
tags:
- TOO-15
- TOO-11
- task-memory
- implementation
---

# TOO-15 P0 Keystone Implementation Task

## Start time
2026-06-25 13:06 EDT

## Task scope
Build `toolguard/tools/` sub-package with 4 modules + tests:
1. `config_access.py` - thin facade over `Configuration`
2. `decision.py` - side-effect-free evaluation primitive
3. `log_harvest.py` - parse daily log files into structured corpus
4. `replay.py` - THE KEYSTONE - corpus + config A vs B -> decision diff

## Key reuse points identified
- `config.load_configuration()` -> `Configuration` object
- `permissions.decide_command_at_level_detailed` for Bash decisions
- `hook.resolve_bash_permission_detailed` for compound Bash (has side effects - log writes)
- `hook.resolve_file_path_permission_detailed` for Read/Write/Edit (has side effects)
- `hook._check_file_path_hard_deny` for file tool hard deny

## Side-effect isolation approach
`hook.resolve_bash_permission_detailed` and `hook.resolve_file_path_permission_detailed`
have side effects (log writes via log_command, log_conflict). For replay/decision module,
we CANNOT use these directly. Instead:
- For Bash: replicate the core logic inline using `resolve_compound_permission` +
  `decide_command_at_level_detailed` + `check_hard_deny` - these are pure.
  `config.resolve_permission_detailed` is also pure.
- For file tools: use `_check_file_path_hard_deny` and `_decide_file_path_at_level_detailed`
  from hook.py - these are pure helpers. Or replicate the key parts.

IMPORTANT: the `_` prefixed functions in hook.py are internal, but we can import them
since the tools package is product code in the same package.

## Log format observed
```
## 2026-06-23 10:27:35

- **Status**: EXECUTED
- **Command**: `ls -la`
- **Matched Rule**: `ls:*  [explicit: /path/to/config]`
- **Agent**: main
```

For REFUSED:
```
## 2026-01-08 17:00:44

- **Status**: REFUSED
- **Command**: `whoami`
- **Violated Rules**: `Command does not match any allow patterns`
```

File tools are logged as:
- **Command**: `Read(/abs/path/to/file)`
- **Command**: `Edit(/abs/path/to/file)`
- **Command**: `Write(/abs/path/to/file)`

Also "Discovery" sections exist - these should be ignored by harvester.

## Constraints
- stdlib unittest (NOT pytest)
- Tests in test/unit/ as test_tools_<module>.py
- BDD Given/When/Then docstrings required
- NO ruff format (manges code)
- uv run python for everything
- No async, no threading, no in-function imports

## Test plan
- Broadening test: rule moving `uv run alembic:*` from ask -> allow (alembic landmine)
- Tightening test: rule moving from allow -> deny
- Unchanged test: identical configs
- Log harvest: parse real format, handle malformed sections, time window
