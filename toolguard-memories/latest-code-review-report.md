---
title: latest-code-review-report.md
date: 2026-06-26
tags:
- code-review
- TOO-15
permalink: toolguard/latest-code-review-report
---

# Code Review Report -- TOO-15

Date: 2026-06-26  
Scope: toolguard/tools/config_access.py, toolguard/tools/danger.py, toolguard/tools/security_audit.py, test/unit/test_tools_config_access.py, test/unit/test_tools_security_audit.py, skills/toolguard-security-audit/SKILL.md  
Files reviewed: 6  
Tests run: 89 (all passing)  
Total time: ~12 minutes  

## Summary

The three production modules show clean architecture -- good separation between the config facade (config_access.py), the rule-danger detector (danger.py), and the unified aggregator (security_audit.py). The test suites are thorough, well-structured with BDD docstrings, and all 89 tests pass. Two real bugs were confirmed by running the code: the `exec` command is not detected by the `arbitrary-exec-allow` detector despite being listed in the module docstring, and the CLI `main()` bypasses the env-override protection that `load_config()` provides. A severity mismatch in the module docstring for `blanket-allow-outside-takeover` (documented as LOW, fires as CRITICAL) is a silent trap for future maintainers.

---

## MAJOR

### M1 -- exec command undetected in arbitrary-exec-allow detector
**File**: toolguard/tools/danger.py, lines 225-295  
**Verified**: `_is_arbitrary_exec('Bash', 'exec /bin/bash', PatternType.DEFAULT)` returns False; same for `exec:*`, `exec /bin/sh`, bare `exec`.

The module docstring (line 27) explicitly lists `exec` as a covered interpreter. It is NOT detected for any DEFAULT or GLOB pattern form.

Root cause: `"exec "` and `"exec:"` in `_ARBITRARY_EXEC_PREFIXES` do not match real-world bodies. `_body_fnmatch_matches_any` checks `startswith(prefix + " ")`, so prefix `"exec "` requires `"exec  "` (double space) to match. `"exec"` is also absent from `_ARBITRARY_EXEC_BARE`. The REGEX path also has no `exec` entry.

**Fix**: Add `"exec"` to `_ARBITRARY_EXEC_BARE`. Remove the now-redundant `"exec "` and `"exec:"` from `_ARBITRARY_EXEC_PREFIXES`.

---

### M2 -- CLI main() bypasses CLAUDE_SETTINGS_PATH env-override protection
**File**: toolguard/tools/security_audit.py, line 470

`main()` calls `load_configuration(Path(args.dir))` directly. The `load_config()` wrapper in config_access.py adds `ignore_env_override=True` to prevent a stale `CLAUDE_SETTINGS_PATH` from diverting the hierarchy walk. The CLI therefore behaves differently from programmatic use of `load_config()` when that env var is set.

**Fix**: Import `load_config` from `toolguard.tools.config_access` and replace line 470 with `config = load_config(Path(args.dir))`.

---

### M3 -- Severity documented as LOW, implemented as CRITICAL
**File**: toolguard/tools/danger.py, lines 49 and 641

Module docstring (line 49) lists `blanket-allow-outside-takeover` as severity LOW. Implementation (line 641) fires it as `Severity.CRITICAL`. Any engineer reading the docstring will have a wrong mental model, which matters when writing severity-filtering logic or evaluating findings.

**Fix**: Update the module docstring entry from LOW to CRITICAL and add a brief rationale (e.g., "A live blanket allow is a complete governance bypass, hence CRITICAL").

---

## MINOR

### m1 -- Dead entries in _ARBITRARY_EXEC_PREFIXES
**File**: toolguard/tools/danger.py, lines 228-243

Entries with trailing spaces (`"python "`, `"python3 "`, `"node "`, `"ruby "`, `"perl "`) never match because `_body_fnmatch_matches_any` checks `startswith(prefix + " ")` -- so prefix `"python "` would require `"python  "` (double space). Detection of `"python script.py"` and `"python:*"` is actually done by `_ARBITRARY_EXEC_BARE`. The colon-suffixed entries (`"python:"`, etc.) also fail to catch `"python:*"` for the same structural reason.

The comment on line 236 says "handle toolguard pattern form python:*" but `_ARBITRARY_EXEC_BARE` is what handles it, not these entries.

**Fix**: Remove trailing-space and colon-suffix entries for python/python3/node/ruby/perl from `_ARBITRARY_EXEC_PREFIXES`. Move the "toolguard pattern form" comment to the `_ARBITRARY_EXEC_BARE` loop.

---

### m2 -- Local imports inside test methods (convention violation)
**File**: test/unit/test_tools_config_access.py, ~28 test methods

Every test method in this file imports from `toolguard.tools.config_access` inside the function body (e.g., `from toolguard.tools.config_access import load_config`). Per rules/python.md, local imports inside functions are prohibited unless a circular dependency is documented and approved. No circular dependency applies.

Note: test_tools_security_audit.py does NOT have this problem -- all its imports are at module level.

**Fix**: Move all `config_access` imports to module level in test_tools_config_access.py.

---

### m3 -- Dead code in test_json_with_context_is_ascii_safe
**File**: test/unit/test_tools_security_audit.py, lines 1200-1203

```python
data_str, _ = (
    lambda: (
        io.StringIO(),
        None,
    )
)()
```

This creates a lambda, calls it immediately, assigns `data_str` to an `io.StringIO()`, then never uses `data_str`. The actual output capture happens on the `captured = io.StringIO()` line that follows.

**Fix**: Delete lines 1200-1203 entirely.

---

### m4 -- load_config type annotation missing Optional
**File**: toolguard/tools/config_access.py, line 77

`def load_config(start_dir: Path = None)` -- the default value is `None` but the annotation says `Path`, not `Optional[Path]`. The `Optional` alias is already imported on line 16.

**Fix**: Change to `def load_config(start_dir: Optional[Path] = None)`.

---

### m5 -- Duplicate one-liner wrappers with inconsistent names
**Files**: toolguard/tools/config_access.py line 152, toolguard/tools/takeover_audit.py line 459

`effective_takeover(config)` and `effective_takeover_state(config)` are both one-line wrappers over `config.takeover_mode()`. They do the same thing under different names in different modules with no cross-reference.

**Fix**: Add a docstring cross-reference in each pointing to the other.

---

### m6 -- _audit_tool iterates lr.allow twice (parse_pattern called twice per pattern)
**File**: toolguard/tools/danger.py, lines 586 and 631

Two separate `for pattern in lr.allow:` loops both call `parse_pattern` and `_is_blanket_allow`, doubling parse work per pattern. For realistic configs the impact is negligible, but the structure is unnecessarily redundant.

**Fix**: Integrate blanket-allow detection into the first loop using a deferred findings list or accumulator set for blanket patterns.

---

### m7 -- SKILL.md argument-hint omits key CLI options
**File**: skills/toolguard-security-audit/SKILL.md, line 12

Current: `"[directory (default: current project)] [--strict]"`  
The CLI also accepts `--format json|markdown|text` and `--with-context`, which the skill itself uses (Pass 1 and Pass 2 respectively). A user following the hint would not discover these.

**Fix**: Update to `"[--dir DIR] [--format json|markdown|text] [--strict] [--with-context]"`.

---

## Suggestions

### S1 -- Document single-finding-per-pattern rule in _audit_tool
**File**: toolguard/tools/danger.py, line 626

The `break` after a detector fires means one pattern gets at most one finding (highest-severity wins because detectors are ordered highest-severity first). This is a deliberate design choice not documented in the function docstring. A future maintainer adding a new detector may not understand why ordering matters.

### S2 -- Consider shared test fixture module
**Files**: test/unit/test_tools_config_access.py, test/unit/test_tools_security_audit.py

`_prov`, `_native_layer`, and `_make_config` have minor structural duplication. A shared `test/unit/helpers.py` would reduce future drift. The `_toolguard_layer` signatures intentionally differ between files.

---

## Issue Counts

| Severity | Count |
|----------|-------|
| Major    | 3     |
| Minor    | 7     |
| Suggestion | 2   |