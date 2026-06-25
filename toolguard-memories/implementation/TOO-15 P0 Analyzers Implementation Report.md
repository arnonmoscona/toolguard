---
title: TOO-15 P0 Analyzers Implementation Report
type: note
permalink: toolguard/implementation/too-15-p0-analyzers-implementation-report
tags:
- TOO-15
- TOO-11
- implementation
---

# TOO-15 P0 Analyzers Implementation Report

**Date:** 2026-06-25
**Status:** COMPLETE - all tests pass
**Baseline tests:** 833 (pre-implementation)
**Final tests:** 905 (72 new tests added)

## Summary

Built four analyzer modules in `toolguard/tools/` as the second slice of the P0
deterministic foundation for TOO-15 skills and config tooling. All four modules
are side-effect-free, reuse existing core APIs, and follow the project's stdlib
unittest + BDD docstring conventions.

## Files Created

### New module files
- `toolguard/tools/sorters.py` - Canonical rule-array sorting
- `toolguard/tools/redundancy.py` - Redundant rule detection
- `toolguard/tools/danger.py` - Ranked static risk findings
- `toolguard/tools/takeover_audit.py` - Takeover invariant checker

### Modified files
- `toolguard/tools/__init__.py` - Added docstring entries for the 4 new modules

### New test files
- `test/unit/test_tools_sorters.py` - 15 tests
- `test/unit/test_tools_redundancy.py` - 15 tests
- `test/unit/test_tools_danger.py` - 22 tests
- `test/unit/test_tools_takeover_audit.py` - 20 tests
- Total: 72 new tests, all pass

## Module Design Details

### sorters.py

Sort key: `(type_rank, normalised_body)` where:
- type_rank: REGEX=0, GLOB=1, NATIVE=2, DEFAULT=3 (extended-syntax types first)
- normalised_body: lowercased, whitespace-stripped body

Uses Python's stable sort. Never mutates input. File rewriting deferred to P2.

**Public API:**
- `sort_patterns(patterns) -> List[str]`
- `sort_layer_rules(allow, deny, ask) -> Tuple[List, List, Optional[List]]`
- `stable_rule_key(pattern) -> Tuple[int, str]`

### redundancy.py

Two detection strategies:

**Static (exact/normalised-equal duplicates):**
- Uses `parse_pattern()` to get type prefix + body
- Normalises DEFAULT patterns by collapsing whitespace around `:` separator
- This makes `uv run pytest :*` and `uv run pytest:*` normalise to same key
- Checks within each layer's allow/deny/ask lists independently

**Corpus-backed subsumption:**
- Builds `config_without` by removing one allow pattern from the config's raw layers
- Runs `replay(corpus, config, config_without)` 
- Rule is corpus-redundant if diff has zero broadened + zero tightened entries
- Only tests allow rules (deny/ask removal semantics are more complex)

**Key design note on normalization:** The `:` separator in DEFAULT patterns strips
whitespace around it so that `uv run pytest :*` (space before colon) and
`uv run pytest:*` normalise identically. This matches how `permissions.py`
actually evaluates these patterns (the trailing space in the command part is
ignored when args is `*`).

**Public API:**
- `find_redundancy(config, tool, corpus=None) -> List[RedundancyFinding]`
- `find_static_duplicates(patterns, provenance, tool, list_type) -> List[RedundancyFinding]`
- `find_static_duplicates_across_layers(config, tool) -> List[RedundancyFinding]`
- `find_corpus_redundant_allows(config, tool, corpus) -> List[RedundancyFinding]`

### danger.py

Data-driven detector table with 5 detectors:

| ID                               | Severity | Description                                                          |
| -------------------------------- | -------- | -------------------------------------------------------------------- |
| `arbitrary-exec-allow`           | CRITICAL | Bash allows uv run python, python3, node, ruby, perl, sh -c, bash -c |
| `destructive-cmd-allow`          | HIGH     | Bash allows rm -rf, shred, dd if=, mkfs, wipefs                      |
| `secrets-exposure-allow`         | HIGH     | Any tool allows .env, .ssh, id_rsa, .pem, .key etc                   |
| `unanchored-regex-allow`         | MEDIUM   | [regex] allow without ^ anchor (re.search is unanchored)             |
| `blanket-allow-outside-takeover` | LOW      | Wildcard (*) allow that is live (not suppressed by takeover)         |

**Takeover-mode awareness:** Native blanket allows in the ignored set (extracted
body `*` in `normalized_ignored_patterns()`) are skipped. Real toolguard rules
are always audited regardless of takeover state.

**Public API:**
- `danger(config, takeover=None) -> List[DangerFinding]`
- `Severity` IntEnum (LOW=1, MEDIUM=2, HIGH=3, CRITICAL=4)
- `DangerFinding` dataclass with detector_id, severity, tool, pattern, provenance, rationale, remediation, takeover_active

### takeover_audit.py

Verifies 4 invariants:

| ID                                      | Severity | Invariant                                               |
| --------------------------------------- | -------- | ------------------------------------------------------- |
| `hook-not-registered`                   | CRITICAL | Toolguard not in PreToolUse hooks for a governed tool   |
| `takeover-conflict-with-blanket-allows` | HIGH     | Cross-level enabled conflict + blanket allows in native |
| `uncovered-blanket-allow`               | HIGH     | Native blanket allow NOT in raw ignored_allow_patterns  |
| `loose-no-match-fallback`               | MEDIUM   | no_match_fallback != 'deny'                             |

**Key design decision on uncovered-blanket-allow:** The check uses the RAW
(wrapped) form of ignored patterns rather than the normalised (stripped) form.
This is because `normalized_ignored_patterns()` strips all tool wrappers to `*`,
making every `Tool(*)` pattern appear "covered" by the defaults. Using raw
wrapper matching means `mcp__custom__tool(*)` is NOT covered by having `Bash(*)`
in the ignored set -- users must explicitly list each tool.

**Correctly-configured setup returns empty list** (verified by test).

**Public API:**
- `audit_takeover(config, takeover=None) -> List[AuditFinding]`
- `effective_takeover_state(config) -> TakeoverConfig`
- `AuditSeverity` IntEnum
- `AuditFinding` dataclass with finding_id, severity, tool, provenance, description, impact, remediation

## Reuse Points

- `toolguard.config.Configuration` and dataclasses (TakeoverConfig, ConfigLayer, Provenance, etc.)
- `toolguard.config._strip_tool_wrapper` (in takeover_audit)
- `toolguard.patterns.parse_pattern, PatternType` (in sorters, redundancy, danger)
- `toolguard.tools.config_access.per_layer_rules` (in redundancy, danger)
- `toolguard.tools.replay.replay` (in redundancy corpus check)
- `toolguard.tools.log_harvest.LogEntry` (in redundancy)

## Deferred to P2

- Static family-based subsumption (literal-alternation, glob expansion)
- Comment-preserving file rewriting in sorters
- Cross-level redundancy detection (rule at project level redundant due to user level)
- Deny/ask rule corpus redundancy analysis

## Required Fixtures Verified

All three required test fixtures from the spec pass:
1. `danger` flags `Bash(uv run python:*)` -> CRITICAL arbitrary-exec-allow finding
2. `danger` flags unanchored `[regex]find` -> MEDIUM unanchored-regex-allow finding
3. `takeover_audit` yields NO findings for featherhill-style correct setup
4. `takeover_audit` DOES flag broken setup (missing hook -> CRITICAL)
5. `redundancy` finds `uv run pytest :*`/`uv run pytest:*` static duplicate

## Phase Timing

- Phase 1 (Planning + reading context): ~12 minutes
- Phase 2 (Implementation): ~35 minutes
- Phase 3 (Self-review + bug fixes): ~8 minutes
- Phase 4 (Report): ~5 minutes
- Total: ~60 minutes

## Estimated Cost

Using claude-sonnet-4-6, approximately:
- Input tokens: ~90K (large due to reading all keystone modules, config.py, permissions.py)
- Output tokens: ~25K (4 modules + 4 test files + reports)
- Estimated cost: ~$0.80-1.10 USD
