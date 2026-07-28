---
title: TOO-19 Coder Task Recall
type: note
permalink: toolguard/implementation/too-19-coder-task-recall
tags:
- TOO-19
- task-memory
- coder-recall
---

# Task: TOO-19 code-review fixes, branch too-19

Started 2026-07-27 09:55 local. Baseline: must confirm 1713 tests green first.

Conventions: stdlib unittest (test/ dir), `uv run python -m unittest discover -s test -t .`,
every test needs BDD Given/When/Then docstring. `uv run ruff format .` / `uv run ruff check .`.
No local imports, no async, no threading. Doc comments for new funcs/classes. NO git write ops.

## CHANGE 1 (CRITICAL): find_section_boundaries not line-anchored
File: toolguard/rule_sort.py:281 `find_section_boundaries`.
`text.find(section_header)` matches `[permissions]` anywhere incl. inside quoted TOML strings.
Repro at /tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/probe6.py
Fix: module-level compiled regex from re.escape(section_name), anchored multiline,
allow leading/trailing horizontal whitespace: `^[ \t]*\[NAME\][ \t]*$`. Keep generic over section_name.
ALSO line-anchor END scan: currently breaks on any newline+`[`; must detect actual section header
line matching `^[ \t]*\[[^\]]+\][ \t]*$`.
Verify callers still correct: annotate.py, config_access._layer_comment_map,
find_multiline_structured_entry_line, write_toml_config.
Tests in test/unit/test_rule_sort.py: [permissions] inside quoted string in earlier section;
inside a comment; section header with leading whitespace; end-boundary case.

## CHANGE 2 (CRITICAL, architectural): never write a config that doesn't parse
New module toolguard/config_write_guard.py - stdlib only (tomllib, json, os, pathlib, typing).
Must NOT import toolguard.config, toolguard.rule_sort, or anything else from toolguard (true leaf,
enforced by test/unit/test_architecture.py LAYERS).

API:
```
class ConfigWriteVerificationError(Exception):
    """path, reason, parser message. Raised when text about to be written fails verification;
    original file left untouched."""

def verify_config_text(text: str, file_format: str) -> None:
    """Parse text ('toml'/'json'), raise ConfigWriteVerificationError if invalid. No I/O."""

def verified_write_config(path, text, file_format, *, expected_patterns=None) -> None:
    """1. verify_config_text - refuse on failure.
    2. if expected_patterns is not None: confirm every pattern is present in parsed structure
       (scan permissions.allow/deny/ask and hard_deny.*, plain-string and structured {match=...}
       via 'match' key). Missing pattern -> ConfigWriteVerificationError naming missing patterns
       (content-loss guard, distinct from syntax guard).
    3. Atomic write: sibling temp file same dir, flush+os.fsync, os.replace() onto path.
       Clean up temp file on any failure.
    """
```
Wire into:
- migrate_permissions.py write_toml_config - ALL 3 branches (new-file, append no-section,
  section replace). expected_patterns derived from `permissions` arg being written.
- migrate_permissions.py write_json_config - same, file_format='json'.
- maintenance.py:791 Path(path).write_text(new, ...) - read surrounding function for format/patterns.
- search for other config-file write sites; route through. Do NOT route audit/decision-ledger/
  log-writer JSON writes (not permission config).

Tests (test/unit/test_config_write_guard.py + wiring tests):
- corrupt TOML refused, exception names path, ORIGINAL FILE UNCHANGED (byte-identical).
- write that drops a pattern refused by content-loss guard.
- valid write succeeds, temp file does not survive.
- guard rejects Change-1 corruption scenario if reintroduced (belt & braces regression test).

## CHANGE 3 (MAJOR): per_layer_rules drops structured ask entries
File: toolguard/tools/config_access.py:142-148.
Fix: `ask = tl.ask if (tl is not None and not layer.is_native) else ()`; delete hand-rolled loop.
Verify ToolPatternLayer.ask really populated + native-gated as assumed - read permission_layers().
Add test in test/unit/test_tools_config_access.py: structured ask entry surfaces via per_layer_rules
(no such coverage currently).

## CHANGE 4 (MAJOR): write path corrupts same-pattern entries w/ differing metadata
File: toolguard/rule_sort.py:824 and :838 (rule_lines / rule_comments).
Keyed by PATTERN ALONE -> last-parsed wins; two entries same pattern differing additionalContext
both re-emitted as 2nd's text, destroying 1st's enrichment. Confirm via write_toml_config.
Reachable: merge_entries case 3 deliberately preserves both conflicting entries for human
resolution, writer then destroys one.
Fix: key by full entry identity (RuleEntry.identity() exists - use it; plain string entry
identity = pattern). Parse side: derive same identity from parsed chunk.
If identity-keying doesn't work for comment-association, fallback (pattern, occurrence_index)
w/ consistent ordering - acceptable, but report which chosen and why.
Existing inline comment ~866-879 recognizes hazard but only guards synthesized case - update it.
Tests: two entries same pattern diff additionalContext survive write_toml_config round-trip w/
BOTH metadata values intact.

## CHANGE 5 (MAJOR): governed_tool_names skips structured entries
File: toolguard/tools/config_access.py:236.
Tool governed ONLY by structured entries never discovered by maintenance/audit.
Fix: route through normalize_entry like other fixed sites.
DO NOT "fix": isinstance(perm, str) checks in takeover_audit.py and config_access.py:773 are
native-layer only by design - leave, confirm checked in report.
Add test: tool discovery via structured-only entry.

## CHANGE 6 (MINOR): _parse_source duplicates _parse_source_recording_failures
File: toolguard/config.py:2148 and :2177. pyscn 0.80 similarity.
Fix: `_parse_source` delegates: `return _parse_source_recording_failures(path, file_format, [])`.
Normal def, not lambda. Preserve docstring content (fail-open policy, which callers use which)
but update to describe delegation. Confirm behavior identical for BOTH file-missing and
file-broken cases before collapsing.

## WRAP-UP
- Full suite green, report number >= 1713 + new tests.
- ruff format . then ruff check . clean.
- Update test/unit/test_architecture.py LAYERS: add toolguard.config_write_guard leaf AND add
  missing toolguard.rule_sort entry (currently absent - future rule_sort->config import would
  create uncaught cycle). Verify architecture tests still pass.
- Write implementation report to
  toolguard-memories/TOO-19/TOO-19 Review Fixes - Correctness Implementation Report.md
  frontmatter title/type:note/tags:[TOO-19, task-memory]. Cover: changes per item, identity-keying
  decision (Change 4), anything contradicting spec, any incomplete fix + why. Be honest, no
  false success claims.
- No git write ops.