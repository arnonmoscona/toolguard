---
title: coder-latest-task-recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall-1
tags:
- TOO-8
- coder-state-for-recovery
- task-memory
---

# TOO-8 Phase 4 -- Task Recall (coder)

Implementing Phase 4: logging streams + conflict logging + provenance in reasons.
Baseline: 654 tests green both ways at start.

## Scope (exactly 6 items)
1. FOUR log streams, one file per concern:
   - logs/toolguard-YYYY-MM-DD.md (resolution, existing)
   - logs/toolguard-error-YYYY-MM-DD.md (REAL errors only, log_error)
   - logs/toolguard-warning-YYYY-MM-DD.md (log_warning moves here: both-formats warn, ungoverned/unsupported tool warnings)
   - logs/toolguard-conflict-YYYY-MM-DD.md (NEW logger, on by default, human-readable, NOT JSON)
   Refactor error_log.py: error/warning/conflict each own file + writer. Keep stderr echo + per-file MD entry format.
2. Takeover notice OUT of logs: issue_takeover_warning -> stderr + once-per-session marker only. NO log write.
3. Conflict logging: allow-over-deny overrides ONLY. Winning decision stays the more-specific allow; write conflict entry citing BOTH provenances + command. hard_deny denials NOT conflicts (resolution log). Detection: when winning decision is allow at level k, scan LESS-specific levels for a deny match on same command -> log override.
4. Provenance in reasons/resolution log. Provenance-carrying level view; decider reports WHICH pattern matched -> map to ToolPatternLayer.provenance. resolve_permission returns (decision, reason, winning provenance, optional override info). COMPAT: append bracketed suffix to reason strings e.g. "...matches allow pattern: git *  [project: .claude/toolguard_hook.toml]". Apply to Bash, compound sub-commands, Read/Write/Edit.
5. Once-per-session discovery diagnostic (M2): emit to RESOLUTION log "discovered N config levels: <level: path>, ..." using once-per-session guard pattern in hook.py.
6. M1: single source of truth for both-.toml-and-.json warning. Currently emitted twice (stderr print in _discover_in_dir AND Issue in validation_issues that can't fire). Consolidate to ONE routing to WARNING stream. Remove dead path.

## OUT of scope
Session-start "last run had conflicts" alert (Phase 6). Takeover cross-level conflict (Phase 5). No changes to governed_tools/takeover/scalar resolution semantics.

## Tooling
- Suite green BOTH ways: `uv run python -m unittest discover -s test -t .` AND with `env -u CLAUDE_SETTINGS_PATH`.
- NO ruff format. Use `uv run ruff check`. Coverage: `uv run python tools/coverage_stdlib.py`.
- Don't edit parser/bash_parser.py.
- unittest, NOT pytest; every test needs Given/When/Then docstring.

## Known test-intent change (authorized by spec)
test_session_warnings.py asserts issue_takeover_warning writes to error log. Spec item 2 explicitly removes this. New tests assert takeover notice NOT in any persisted log. This is an authorized intent change.

## Key code locations
- error_log.py: log_warning/log_error both -> toolguard-error file
- log_writer.py: log_command -> resolution log
- session_warnings.py: issue_takeover_warning
- hook.py: main(), _run_startup_validation (line 83 log_warning), resolve paths, once-per-session guards (_validation_done, _divergence_check_done)
- config.py: resolve_permission (~1152), permission_levels (~1124, strips provenance), permission_layers (~1076, carries ToolPatternLayer.provenance), Provenance dataclass (~785)
- permissions.py: decide_command_at_level, make_command_level_decider, check_permission, check_hard_deny
- compound.py: resolve_compound_permission
- config_divergence.py:262 also calls log_warning (-> warning stream)

## Status: COMPLETE -- 670 tests green both ways, ruff clean. Report at implementation/coder-latest-implementation-report.
