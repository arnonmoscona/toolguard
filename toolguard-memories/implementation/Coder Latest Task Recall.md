---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- TOO-8
- task-memory
- session-start
---

# TOO-8 Phase 6: SessionStart Hook Implementation

## Task Summary

Implement a `SessionStart` hook that surfaces toolguard configuration conflicts at the
start of each Claude Code session.

## Key Requirements

### Entry Point
- Add `toolguard-session-start = "toolguard.session_start:main"` to `pyproject.toml [project.scripts]`
- Leave `toolguard = "toolguard.hook:main"` unchanged

### New Module
- `toolguard/session_start.py` with `def main() -> None`

### Input
- SessionStart JSON payload from stdin
- `hook_event_name == "SessionStart"`, has `cwd` and `session_id`, NO `tool_name`/`tool_input`
- Be tolerant: fall back to `os.getcwd()` if `cwd` absent
- NEVER raise to user; wrap body so any error => silent exit 0 (optional one-line stderr)

### Config Loading
- `config = load_configuration(cwd)` -- same as PreToolUse hook
- `log_dir = config.project_root / 'logs'` (handle project_root is None => no log dir => only static check)

### Two Detection Sources

1. **STATIC (recomputed live, self-clears when config fixed)**:
   - `config.takeover_mode().conflict` -- a `TakeoverEnabledConflict` or None
   - If present: levels disagree on `takeover_mode.enabled`, failed safe to OFF
   - Use `.describe()` / sources for message

2. **DYNAMIC (previously recorded, read from log files)**:
   - Read conflict log file(s) in `log_dir` named `toolguard-conflict-*.md`
   - Report the MOST RECENT such file that has recorded entries
   - Count entry headers (look at how `error_log.log_conflict` writes entries)
   - Each entry starts with `## YYYY-MM-DD HH:MM:SS - CONFLICT`

### Output
- If any conflicts found: print BRIEF human-readable summary to STDOUT
  (Claude Code injects SessionStart stdout into session context)
- If NO conflicts: print nothing and exit 0
- Exit 0 ALWAYS

### Output Format (example)
```
toolguard: configuration conflicts detected --
- takeover_mode.enabled disagrees across levels; failed safe to OFF (<provenance>)
- conflict log logs/toolguard-conflict-YYYY-MM-DD.md has N recorded entr(y/ies)
Review and resolve; see the conflict log for details.
```

### Behavior
- Nag every session while conflicts remain (no dedup marker)
- A SessionStart hook must never block or break a session

## Tests Required

File: `test/unit/test_session_start.py`

1. Static takeover conflict present -> summary mentions it
2. Conflict log with entries -> summary reports count + path
3. No conflicts -> no stdout
4. Malformed/empty stdin -> graceful exit 0 no traceback
5. Missing project_root/log_dir -> still handles static check
6. >90% coverage on new module

## Other Changes

- Add "Phase 6" section to `technical-notes.md`
- Update `pyproject.toml`

## Conflict Log Format (from error_log.py)

Each entry in `toolguard-conflict-YYYY-MM-DD.md` starts with:
```
## YYYY-MM-DD HH:MM:SS - CONFLICT
```
Count lines starting with `## ` and containing `- CONFLICT` to count entries.
