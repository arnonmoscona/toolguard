---
title: TOO-15 P1 Audit Context Export Implementation Report
type: note
permalink: toolguard/implementation/too-15-p1-audit-context-export-implementation-report
tags:
- TOO-15
- implementation-report
- feature-coder
---

# TOO-15 P1 Audit Context Export Implementation Report

## Summary

Implemented deterministic "audit context" export for TOO-15 Phase P1. The
implementation adds two shared helpers (drift removal from danger.py), three new
frozen dataclasses, an audit_context() builder, a --with-context CLI flag, and
comprehensive tests -- all following existing project patterns.

## Phase Timing and Cost Estimates

- Phase 1 (reading/planning): ~5 minutes, ~$0.08
- Phase 2 (implementation): ~12 minutes, ~$0.25
- Phase 3 (self-review/fixes): ~5 minutes, ~$0.10
- Phase 4 (report/handoff): ~3 minutes, ~$0.05
- Total estimated cost: ~$0.48

## Files Changed

### Modified Source Files (4)

1. `toolguard/tools/config_access.py` -- Added `Set` import, two helper functions
   (`discover_tools`, `neutralized_by_takeover`), three dataclasses (`LayerContext`,
   `ToolContext`, `AuditContext`), and `audit_context()` builder.

2. `toolguard/tools/danger.py` -- Added `discover_tools` and `neutralized_by_takeover`
   to import from config_access; replaced inline tool-discovery loop and two inline
   neutralization checks with calls to the new helpers.

3. `toolguard/tools/security_audit.py` -- Added `audit_context` import; added
   `--with-context` argparse argument; added context serialization block in JSON
   output path.

4. `test/unit/test_tools_config_access.py` -- Added imports (moved to top per ruff
   E402); added fixture helpers; added TestDiscoverTools (7 tests),
   TestNeutralizedByTakeover (5 tests), TestAuditContext (9 tests).

5. `test/unit/test_tools_security_audit.py` -- Added TestWithContextFlag (11 tests).

## Extracted Helpers vs. Inline Code (Drift Removal Proof)

### discover_tools() -- extracted from danger.py lines ~548-555

OLD inline code in danger():
```python
tools_seen = set()
for layer in config.layers:
    permissions = layer.content.get("permissions", {})
    if isinstance(permissions, dict):
        for perm in permissions.get("allow", []) + permissions.get("deny", []) + permissions.get("ask", []):
            if isinstance(perm, str) and "(" in perm and perm.endswith(")"):
                tool_name = perm[: perm.index("(")]
                tools_seen.add(tool_name)

for tool in sorted(tools_seen):
    findings.extend(_audit_tool(...))
```

NEW in danger():
```python
for tool in discover_tools(config):
    findings.extend(_audit_tool(...))
```

No logic change. discover_tools() encapsulates the same loop, returns sorted tuple.

### neutralized_by_takeover() -- extracted from danger.py ~596 (and ~640)

OLD inline code in _audit_tool() (two occurrences):
```python
if takeover.enabled and is_native and pattern in ignored_extracted:
    continue
```

NEW in _audit_tool():
```python
if neutralized_by_takeover(pattern, is_native, takeover):
    continue
```

No logic change. The function body is: `takeover.enabled and is_native and
pattern in takeover.normalized_ignored_patterns()`. The `ignored_extracted`
variable (pre-computed at caller) is replaced by calling the method directly
inside the helper (equivalent).

### Important Discovery: neutralized_by_takeover is Dead Code in danger.py

`permission_layers()` (called by `per_layer_rules`) already filters out
takeover-suppressed patterns BEFORE returning them. So the
neutralized_by_takeover checks in _audit_tool never actually fire. This is
preserved behavior -- the helper is accurately extracted dead-code.

For `AuditContext.neutralized_allow_patterns`, the fix is to scan raw native
layer content BEFORE per_layer_rules filtering, to actually discover which
patterns were suppressed. This is documented in the audit_context() docstring.

## AuditContext Shape

```python
@dataclass(frozen=True)
class AuditContext:
    summary: ConfigSummary         # existing type, reused
    takeover: TakeoverConfig       # existing type, reused
    tools: Tuple[ToolContext, ...]  # per-tool rule hierarchy
    neutralized_allow_patterns: Tuple[str, ...]  # extracted patterns suppressed by takeover
```

## --with-context JSON Contract

Added to existing payload ONLY when --format json AND --with-context:
```json
{
  "context": {
    "summary": {"start_dir": str|null, "project_root": str|null,
                "sources": [...], "governed_tools": [...], "layer_count": int},
    "takeover": {"enabled": bool, "no_match_fallback": str,
                 "ignored_allow_patterns": [...], "additional_ignored_patterns": [...],
                 "conflict": str|null, "neutralized_allow_patterns": [...]},
    "tools": [{"tool": str, "layers": [
        {"locus": str, "is_native": bool, "allow": [...], "deny": [...], "ask": [...]}
    ]}]
  }
}
```

Existing keys (takeover_active, highest_severity, counts, findings) are unchanged.

## Test Results

- Baseline: 975 tests (all passing before change)
- After implementation: 1008 tests (33 new), all passing
- New test breakdown:
  - TestDiscoverTools: 7 tests
  - TestNeutralizedByTakeover: 5 tests
  - TestAuditContext: 9 tests
  - TestWithContextFlag: 11 tests (in test_tools_security_audit.py)
  - All BDD Given/When/Then docstrings present

## Ruff Status

Clean: `uv run ruff check .` -- All checks passed!
Note: `ruff format` NOT run (project rule - mangles PEP 758 except syntax).

## Demo Output Head

```
context.summary:
  start_dir: "."
  project_root: "."
  sources: [... 2 config files ...]
  governed_tools: ["Bash", "mcp__jetbrains__execute_terminal_command", ...]
  layer_count: 2

context.takeover:
  enabled: true
  neutralized_allow_patterns: ["*"]
  
context.tools: 6 tools discovered
```

## Deviations from Spec

1. **neutralized_allow_patterns computation**: The spec implied computing this via
   `per_layer_rules` output, but that output is already filtered by permission_layers.
   Corrected to scan raw native layer content. This is the only correct approach and
   produces the expected result. The spec had an implicit assumption that didn't hold.

2. No other deviations.

## Self-Review Findings

- No async/await, no threading, no local imports
- All public functions have full docstrings
- Security: no auth bypass, read-only operations only
- Scope: exactly 5 files changed as specified
- All existing tests still pass (975 -> 1008, +33)
