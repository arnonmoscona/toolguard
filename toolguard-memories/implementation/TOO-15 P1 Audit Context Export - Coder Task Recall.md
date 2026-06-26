---
title: TOO-15 P1 Audit Context Export - Coder Task Recall
type: note
permalink: toolguard/implementation/too-15-p1-audit-context-export-coder-task-recall
tags:
- TOO-15
- task-memory
- feature-coder
---

# TOO-15 P1 Audit Context Export - Implementation Recall

## Task
Add deterministic "audit context" export so a skill can feed an AI pass the same consolidated material the deterministic analyzers see. This is assembly over EXISTING functions plus two small behavior-preserving refactors.

## Files to Edit (ONLY these)
1. `toolguard/tools/config_access.py` -- add helpers + dataclasses + builder
2. `toolguard/tools/danger.py` -- refactor to use new helpers
3. `toolguard/tools/security_audit.py` -- add --with-context CLI flag
4. `test/unit/test_tools_config_access.py` -- new tests
5. `test/unit/test_tools_security_audit.py` -- new tests

## Deliverable 1: Two helpers in config_access.py (drift removal)

### `discover_tools(config: Configuration) -> Tuple[str, ...]`
- Returns sorted tuple of all tool names in any layer's allow/deny/ask
- A tool name is the text before first "(" in a "Tool(body)" pattern
- This is EXACTLY what danger() does inline at ~548-555; MOVE that logic here

### `neutralized_by_takeover(pattern: str, is_native: bool, takeover: TakeoverConfig) -> bool`
- Returns `takeover.enabled and is_native and pattern in takeover.normalized_ignored_patterns()`
- This is the rule at danger.py ~596

Then REFACTOR danger.py to CALL these helpers instead of inline code. Preserve behavior exactly.

## Deliverable 2: audit_context in config_access.py

New frozen dataclasses:
```python
@dataclass(frozen=True)
class LayerContext:
    locus: str            # provenance.describe()
    is_native: bool       # provenance.source_type == "claude"
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...]

@dataclass(frozen=True)
class ToolContext:
    tool: str
    layers: Tuple[LayerContext, ...]  # most-specific first, per per_layer_rules

@dataclass(frozen=True)
class AuditContext:
    summary: ConfigSummary
    takeover: TakeoverConfig
    tools: Tuple[ToolContext, ...]
    neutralized_allow_patterns: Tuple[str, ...]  # flat, sorted, de-duped
```

### `audit_context(config: Configuration) -> AuditContext`
- summary = config_summary(config); takeover = effective_takeover(config)
- For each tool in discover_tools(config): build ToolContext from per_layer_rules
- neutralized_allow_patterns = sorted set of allow patterns where neutralized_by_takeover() is True
- NO detection logic

## Deliverable 3: --with-context CLI flag in security_audit.py

- argparse `--with-context` (store_true, default False)
- Only meaningful with `--format json`
- When set + json: add top-level `"context"` key to JSON payload
- Context JSON shape:
  ```json
  {
    "summary": {"start_dir": str|null, "project_root": str|null, "sources": [...], "governed_tools": [...], "layer_count": int},
    "takeover": {"enabled": bool, "no_match_fallback": str, "ignored_allow_patterns": [...], 
                 "additional_ignored_patterns": [...], "conflict": str|null,
                 "neutralized_allow_patterns": [...]},
    "tools": [{"tool": str, "layers": [{"locus": str, "is_native": bool, "allow": [...], "deny": [...], "ask": [...]}]}]
  }
  ```
- neutralized_allow_patterns is from AuditContext.neutralized_allow_patterns
- Existing payload keys (takeover_active, highest_severity, counts, findings) UNCHANGED
- With markdown/text: no-op (not an error)
- Default (no --with-context): output byte-for-byte unchanged

## Deliverable 4: Tests

### test_tools_config_access.py additions:
- `discover_tools` tests: finds tools across allow/deny/ask, sorted, deduped
- `neutralized_by_takeover` tests: True only when enabled+native+in-ignored; False otherwise
- `audit_context` tests: summary/takeover/tools populated; native vs toolguard layers flagged; neutralized list correct; empty when takeover off

### test_tools_security_audit.py additions:
- `--with-context` adds well-formed `context` key in json
- neutralized list appears under takeover in context
- WITHOUT flag: no `context` key (backward compat)
- `--with-context` with text/markdown: no error, no context added

## Anti-duplication Rule
Do NOT reimplement config consolidation, takeover logic, or pattern parsing. Consume existing functions.

## Important Constraints
- Do NOT run `ruff format` (mangles PEP 758 except syntax)
- Tests use stdlib `unittest` (NOT pytest)
- Baseline test count was 975
