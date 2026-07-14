---
title: latest-code-review-report.md
date: 2026-07-14
tags:
- code-review
permalink: toolguard/latest-code-review-report
---

# Toolguard Code Review Report

Date: 2026-07-14 (generated 10:10 local)
Scope: whole-tree review of `toolguard/` and `test/` (not a diff).
Excluded: `toolguard/parser/bash_parser.py` (canopy-generated), everything outside `toolguard/`+`test/`.
External analysis: `uvx pyscn analyze --json --skip-deps toolguard` (v1.24.3) incorporated below.

## Summary

The codebase is in strong shape for a security-critical permission tool. The decision core
is well-factored: a single pure resolver layer (`toolguard/resolve.py`) backs BOTH the live
hook and the `--eval`/tooling path via `tools/decision.decide()`, so I verified there is no
eval-vs-live drift by construction. Fail-closed defaults are sound (unconfigured tool -> ask;
configured-no-match -> `no_match_fallback`; hard-deny pooled and checked first). Test quality
is exemplary: all 1431 tests pass and every one carries a Given/When/Then docstring. The main
issues are (1) a real quoting bypass in the Bash path-component matcher, (2) genuine triplicated
"daily marker file" logic across three modules, and (3) a handful of high-complexity functions
flagged by pyscn.

Verification performed this run:
- `except A, B:` (resolve.py:269, patterns.py:94, normalization.py, auto_migrate.py:100) is
  NOT a Python 2 bug: PEP 758 (Python 3.14) makes parenthesis-free `except` tuples valid; I
  confirmed at runtime it catches BOTH types and correctly lets others escape. Intentional and
  correct on this 3.14-pinned project. No action.
- Full suite: `Ran 1431 tests ... OK`.
- Quoting bypass reproduced directly against `match_command` (see Major #1).

## Critical

None. No bypass defeats the tool's primary/recommended protection path, eval/live parity holds,
and defaults fail closed.

## Major

### M1 (SECURITY) - Quoted args bypass Bash path-component deny patterns
`toolguard/permissions.py:62` `contains_path_component` (used by `match_command` for DEFAULT
patterns of the form `**/x/**`, e.g. the `**/.env/**` deny advertised in `match_command`'s own
docstring at permissions.py:106). It splits each arg on whitespace and `/` but never strips shell
quotes, so:
- `cat .env`      -> MATCH (denied)
- `cat './.env'` / `cat '.env'` -> MISS (allowed)  <-- bypass
- `cat ".env"`    -> MISS (allowed) <-- bypass
Reproduced directly against `match_command(..., ['**/.env/**'])`.

Mitigation that lowers (but does not eliminate) severity: the tool's *recommended* .env defense
(`tools/recommended_protections.py`) uses `Read(**/.env)`/`Write(**/.env)`/`Edit(**/.env)` on the
file tools, which go through the GLOB matcher (`PurePath.full_match`), NOT `contains_path_component`,
and are not quote-bypassable. So a canonical install is protected. But any user who hand-writes a
`Bash(**/.env/**)`-style deny (a documented, advertised feature) gets a rule that a quote trivially
evades.

Recommended fix: strip a single layer of surrounding quotes from each arg token in
`contains_path_component` before the `/`-split (and ideally apply the same in
`normalize_path_in_command`). Add regression tests for quoted, double-quoted, and mixed forms.
Longer term this is another symptom of hand-rolled `.split()` command parsing (see m3).

### M2 (DRY / reimplementation) - Triplicated "daily marker file" logic across 3 modules
`toolguard/auto_migrate.py`, `toolguard/config_divergence.py`, and `toolguard/session_warnings.py`
each independently define the SAME four functions -- `get_marker_file_path`, `marker_exists_for_today`,
`create_marker_file`, `cleanup_old_markers` -- differing ONLY in the filename prefix
(`.toolguard-migration-`, `.toolguard-divergence-warned-`, `.toolguard-warned-`). pyscn flags the
whole cluster (auto_migrate 21-35/52-73/76-105 <=> config_divergence 19-33/50-71/74-103 <=>
session_warnings 14-28/45-69/72-104, sim ~0.85 cross-file). Textbook accidental duplication.
Recommended fix: extract one parameterized helper, e.g. `DailyMarker(prefix: str)` (or module
functions taking `prefix`) in a small shared module (path_utils or a new `daily_marker.py`), and have
all three call it. Consolidate the three near-identical test suites accordingly.

### M3 (complexity) - High-cyclomatic functions (pyscn)
pyscn: 17 high-risk functions; avg cyclomatic 8.3, max 44. Worst offenders:
- `scripts/migrate_permissions.py:614 migrate` -- cx=44, cognitive=113 (critical). CLI script,
  lower blast radius than the decision path, but should be decomposed (per-phase helpers: backup,
  add, remove, report). Guard-clause + extract-function.
- `hook.py:501 main` -- cx=28, cog=56. The file-tool branch and the command-tool branch (each ~70
  lines incl. logging) are natural `_handle_file_tool()` / `_handle_command_tool()` extractions;
  the once-per-session setup block (discovery/validation/takeover/divergence) is another.
- `config.py:1525 Configuration.validation_issues` -- cx=22, cog=52. Extract per-issue-kind detectors.
- `log_writer.py:16 log_command` -- cx=20; `permissions.py:98 match_command` -- cx=18/cog=67;
  `rule_sort.py:119 parse_permissions_section_with_comments` -- cx=18; `patterns.py:64 match_pattern`
  -- cx=15 (dispatch table by PatternType instead of if/elif chain).
Maintainability, not correctness; `match_command`/`match_pattern` sit on the hot decision path and
would benefit most from clarity (dispatch table by PatternType).

## Minor

### m1 - "Reason string as a data channel" fragility
Several places recover structured data by re-parsing human-readable reason strings:
- `resolve.py:511-553` extracts `matched_rule` by slicing hard-deny/allow/deny/ask reason text and
  stripping the ` [provenance]` suffix.
- `hook.py:306 _parse_compound_match_details` regex-parses "All N sub-commands allowed: [...]".
- Many `reason.split(": ", 1)[1]` idioms in hook.py.
If any reason wording changes, provenance/sub-match/logging extraction silently degrades (the
`match_command` docstring at permissions.py:130 already warns about a related coupling). Prefer
threading matched pattern/provenance as structured fields rather than re-deriving from prose.

### m2 - `normalize_path` does filesystem I/O in the matching hot path
`normalization.py:45-53` calls `Path.exists()`, `is_symlink()`, `resolve()` during normalization,
which runs for every governed command: (a) makes matching depend on live FS state (mild TOCTOU
surface: symlink swap between normalize and execution), and (b) adds syscalls to the hot path. Also
the comment "Only resolve if the path ... not its parent directories" doesn't match `resolve()`,
which canonicalizes the whole path. Behaviour is the safer direction; reconcile comment/behaviour and
reconsider whether symlink resolution belongs in a permission matcher.

### m3 - Hand-rolled `.split()` command parsing (recurring anti-pattern)
`permissions.normalize_path_in_command` and `contains_path_component` tokenize commands with plain
`str.split()` rather than the PEG-derived structure. They operate on already-extracted sub-commands so
blast radius is limited, but M1 is a direct consequence. Flagged per CLAUDE.md's noted tendency.

### m4 - `config_validation.py:84-109` near-duplicate warning-dict blocks (pyscn sim=1.0)
The "unsupported tool" and "ungoverned tool" loops build near-identical warning dicts. Small local
extraction (`_tool_warning(level, message, corrective_steps)`), low priority.

## Suggestions

- CBO: `Configuration` depends on 10 classes (pyscn "critical coupling"); it mixes discovery, parsing,
  and resolution (god-object tendency). A future split (discovery/IO layer vs a pure resolution layer
  over already-loaded layers) would reduce coupling and aid testing.
- `patterns.match_pattern` and `permissions.match_command`: replace `if/elif` chains on `PatternType`
  with a dispatch dict of small handlers.
- pyscn intra-file clones in `tools/danger.py`, `tools/installer.py`, `tools/consolidate.py`,
  `tools/clarity.py`, `update_check.py`, `parser/command_model.py`, `parser/command_extractor.py`
  are candidates for small parameterized extractions; opportunistic, none pressing.
- BENIGN pyscn false positives (no action): `error_log.py` "clones" are thin one-line wrappers over
  `_log_entry`; `replay.py`<=>`self_permission.py` similarity is two loops that both correctly reuse
  `decide()` (structural, not logic duplication).

## Positives (keep doing)

- Single pure resolver (`resolve.py`) shared by hook + tooling => eval and live cannot drift.
- Fail-closed, well-documented defaults (unconfigured->ask, hard-deny pooled+first, no_match_fallback).
- Exemplary tests: 1431/1431 pass, every one has a Given/When/Then docstring (0 missing, 0 partial).
- Clean dead-code (pyscn: 0 findings) and no dependency cycles (0 modules in cycles).
- Strong module/function docstrings and clear provenance threading.

## pyscn metrics snapshot
- Files analyzed 55; functions 159; avg cyclomatic 8.26; max 44; high-risk 17; medium 22.
- Clones: 99 clones / 64 pairs / 39 groups; avg similarity 0.82.
- Dead code: 0 findings. Dependency cycles: 0. Max depth: 0.
- Report JSON: `.pyscn/reports/analyze_20260714_100302.json`.

## Review meta
- Files reviewed in depth: resolve.py, permissions.py, patterns.py, normalization.py, path_utils.py,
  compound.py, hook.py, tools/decision.py, config.py (core methods), parser/multiline.py (head),
  config_validation.py, auto_migrate.py + the two marker siblings, error_log.py, recommended_protections.py;
  plus structural scan of all 55 source + 53 test files and full pyscn report.
- Elapsed: ~9 minutes. Includes full suite run, pyscn run, and targeted empirical checks
  (except-tuple semantics, quoting bypass).
