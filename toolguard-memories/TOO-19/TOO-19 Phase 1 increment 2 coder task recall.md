---
title: TOO-19 Phase 1 increment 2 coder task recall
type: note
permalink: toolguard/too-19/too-19-phase-1-increment-2-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task
TOO-19 Phase 1 ("additionalContext" feature), increment 2 only. Thread `additional_context`
through the FILE-PATH resolution path only (not compound.py, hook.py, log_writer.py).

## Already done (increment 1, do not redo)
`toolguard/rule_entry.py` has `ADDITIONAL_CONTEXT_KEY = "additionalContext"`,
`KNOWN_ENRICHMENT_KEYS`, `_additional_context_issues()`, `RuleEntry.additional_context` property
(returns non-blank str or None).

## Scope for increment 2
1. `config_types.py`: `ResolvedDecision` (~line 281) gains `additional_context: Optional[str] = None`
   as last field. Update docstring Attributes.
2. `config.py`: add static `_entry_for_pattern(layers, pattern, kind) -> Optional[RuleEntry]`
   mirroring `_provenance_for_pattern` (~line 1384). Must read `ToolPatternLayer` docstring
   (~config_types.py line 149) re index correspondence between layer.allow (stripped) and
   layer.allow_entries[i].pattern (wrapper-intact). Match by index, not string compare. Consider
   extending `_provenance_for_pattern` to return both instead - pick cleaner, justify in report.
3. `config.py::_resolve_permission_detailed_unclamped` (~1509): populate additional_context from
   winning entry's property on matched branch (~1545). No-match/no-rules branches keep None.
4. `_apply_parse_failure_ask_floor` (~1456): clamped ResolvedDecision must have
   additional_context=None (like provenance/override are cleared). Add specific test.
5. `resolve.py`: `FileResolution` (~135) gains `additional_context: Optional[str] = None`.
   Must NOT be added to `__iter__` (stays 3-tuple: decision, reason, override) - backwards compat.
6. `resolve_file_path_permission_detailed` (~397): pass resolved.additional_context through.
7. Hard-deny early-return (`_check_file_path_hard_deny`): `Configuration.hard_deny_entries(tool_name)`
   exists (config.py ~1173), parallel to hard_deny(). Populate additional_context there too if
   matched pattern is (or can cleanly be) surfaced. If bigger than rest of increment combined, STOP
   and report instead of half-doing it.

## Tests
Extend test/unit/test_configuration.py and whichever covers resolve.py (verify names, don't trust
plan note). Cover: allow/ask/deny structured entry surfaces additionalContext on ResolvedDecision
and FileResolution for Read/Write/Edit; plain-string rule -> None; structured rule w/o key -> None;
parse-failure ASK floor clears it; hard-deny carries it; FileResolution 3-tuple unpacking still
works (explicit assert).

## Verification
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` must pass (baseline 1885 tests).
- `uv run ruff check .` clean; `uv run ruff format` only on touched files.
- Self-check duplication: check against `_provenance_for_pattern`, `Configuration._detect_override`,
  permissions.py.

## Report
basic-memory project toolguard, path `TOO-19/TOO-19 Phase 1 increment 2 implementation report.md`,
tags task-memory + TOO-19. Include wrapper-intact-vs-stripped decision + evidence, hard-deny
finding, dup self-check, anything out of scope. Do not commit to git.

## Constraints
stdlib-only runtime; unittest not pytest; BDD Given/When/Then docstrings on tests; no local
imports; docstrings on every function/class.
