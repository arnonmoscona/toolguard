---
title: TOO-45 D1a coder task recall
type: note
permalink: toolguard/too-45/too-45-d1a-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-recall
---

## Task

Implement TOO-45 step D1a in /home/arnon/projects/toolguard, branch too-45. Full spec at /tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/d1a_brief.md (copied below in full). Report goes to basic-memory toolguard project, TOO-45/TOO-45 D1a implementation report.md.

## Discrepancy noted before starting

"TOO-45 RESUME HERE" memory note (written before compaction) proposed a STAGED D1a: keep `Configuration.resolve_permission_detailed` as a thin delegating shim, defer the public rename + ~47 test updates to D1b/R6. The brief I was actually given describes the FULL move: delete everything from config.py, no shim, no re-export, update all ~25 call sites (3 production + ~22 tests) plus two fake test doubles. Per my instructions, the brief is authoritative ("already decided -- implement it, do not redesign"); RESUME HERE is background context only. I will implement per the brief and flag this discrepancy in my report.

## Design summary (from brief)

New module `toolguard/permission_resolution.py` in pyscn `engine` layer. Imports ONLY `toolguard.config_types` + stdlib. NOT `toolguard.config`. Duck-types the config argument via a narrow 6-member query surface:
- `permission_levels_with_provenance(tool_name)`
- `provenance_for_pattern(layers, pattern, kind)`
- `entry_for_pattern(layers, pattern, kind)`
- `has_any_rules(tool_name)`
- `resolved_no_match_fallback()`
- `parse_failures` (attribute)

If a 7th is needed -> stop and report as a finding.

### Functions to move out of config.py into permission_resolution.py (delete from config.py, no shim):
- `Configuration.resolve_permission_detailed` -> `resolve_permission_detailed(config, tool_name, decide_detailed)`
- `Configuration._resolve_permission_detailed_unclamped` -> `_resolve_unclamped(config, tool_name, decide_detailed)`
- `Configuration.apply_parse_failure_floor` -> `apply_parse_failure_floor(parse_failures, decision, reason)` (signature change: takes parse_failures tuple not config)
- `Configuration._apply_parse_failure_ask_floor` -> `_apply_ask_floor(parse_failures, resolved)`
- `Configuration._parse_failure_reason` -> `_parse_failure_reason(parse_failures)`
- `Configuration._detect_override` -> `_detect_override(config, levels, winning_index, winning_pattern, winning_prov, decide_detailed)`
- module-level `_append_provenance` in config.py -> same name in new module

### Stay on Configuration but renamed (public, no aliases):
- `_provenance_for_pattern` -> `provenance_for_pattern`
- `_entry_for_pattern` -> `entry_for_pattern`
Update every reference: production, tests, docstrings, tools/corpus_build.py comments.
`_detect_override` must call `config.provenance_for_pattern(...)` through the passed object, not `Configuration._provenance_for_pattern` statically.

Stay untouched: `permission_levels_with_provenance`, `has_any_rules`, `resolved_no_match_fallback`.

### Production callers (toolguard/resolve.py, 3 lines, ~598, ~792, ~829):
- `config.resolve_permission_detailed(tool_name, _decide_detailed)` -> import `resolve_permission_detailed` from new module, call `resolve_permission_detailed(config, tool_name, _decide_detailed)`
- same at ~792 for "Bash"
- `config.apply_parse_failure_floor(decision, reason)` -> `apply_parse_failure_floor(config.parse_failures, decision, reason)`

### pyscn layer map
Add "permission_resolution" to engine layer's packages list in .pyscn.toml (~line 175). Verify with `uv run python tools/architecture_fitness.py --layers`.

## Test doubles (important)

- test/unit/test_hook.py ~line 148: local fake class inside helper fn, hand-reimplements resolve_permission_detailed (~35 lines) + apply_parse_failure_floor (~196). Replace with query-surface methods per brief's example code (permission_levels_with_provenance, has_any_rules, resolved_no_match_fallback, parse_failures attr). May need provenance_for_pattern/entry_for_pattern stubs returning None if reached with layers=() -- check by running tests, don't guess.
- test/unit/test_configuration.py ~3797: `_FakeConfig` similarly.
- WATCH REASON STRINGS: fake's old no-match reason: "Command does not match any allow patterns; no_match_fallback=ask". Real engine's: "Command does not match any allow patterns; awaiting a decision (no_match_fallback=ask)". If test_hook.py asserts on old text, must change assertion -- report as a finding (test name + both strings). Do NOT reintroduce old string into fake.

## Other test call sites (~22 across test_configuration.py, test_logging_streams.py, test_hierarchical.py, test_takeover_mode.py, test_hard_deny.py)

Change `config.resolve_permission_detailed(...)` -> `resolve_permission_detailed(config, ...)` with module-level import.
- test_logging_streams.py:260 imports `_append_provenance` from toolguard.config -> repoint to new module.
- test_logging_streams.py:276, test_configuration.py:3736,3753 call `_provenance_for_pattern`/`_entry_for_pattern` -> use new public names.

Update every Given/When/Then docstring invalidated, same edit. Repoint stale `:meth:` cross-refs to `Configuration.resolve_permission_detailed` in toolguard/hook.py, resolve.py, compound.py, session_start.py, config_types.py, config.py itself, tools/corpus_build.py.

## Docstrings

Keep terser. Preserve substance of TOO-19 HARD INVARIANT on apply_parse_failure_floor (never consults undecidable_fallback, no settings param threaded in) and TOO-15 unconfigured-vs-no-match distinction. Drop restatements of what code plainly says. Do not expand.

## Acceptance commands (must paste real output)

```
uv run python -m unittest discover -s test -t .          # expect: Ran 2321 tests ... OK
uv run python tools/corpus_build.py --verify              # expect: no differences
uv run python tools/architecture_fitness.py --guard        # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --layers        # every module mapped, no violations
uv run ruff format . && uv run ruff check .
```

## Hard operating rules

1. NEVER git checkout/restore/stash/reset or any git write. Denied by permission rule, will HANG. To make changes reversible: copy original bytes to /tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/d1a-backups/ before first edit of each file; restore by copying back; verify sha256sum. Read-only git (diff/status/log/show) fine.
2. Do NOT commit. Arnon commits.
3. Do NOT copy the repository anywhere (previous incident filled temp fs -> empty output masquerading as "no matches").
4. uv run python always, never bare python. unittest not pytest.
5. No local imports (imports inside functions) -- design should not need any.
6. Do not edit anything outside repo.

## Success criteria

All 5 acceptance commands pass with pasted real output. Test count stays at 2321 (or deviation explained). Corpus verify: zero differences across 6401 cases. Report written to basic-memory before declaring done.
