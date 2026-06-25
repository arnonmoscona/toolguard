---
title: latest-code-review-report.md
type: code-review
project: toolguard
date: 2026-06-25
tags:
- code-review
- TOO-15
permalink: toolguard/latest-code-review-report
---

# Code Review Report — TOO-15 tooling layer
**Date:** 2026-06-25  
**Scope:** 12 files — `toolguard/tools/` (config_access, decision, log_harvest, replay, redundancy, danger, takeover_audit, sorters), `toolguard/resolve.py`, `toolguard/rule_sort.py`, `toolguard/hook.py`, `toolguard/scripts/migrate_permissions.py`  
**Tests run:** 925 tests — all pass  

---

## Summary

The tooling layer is well-architected and clearly structured. The delegation model (tools layer -> resolve -> config) is clean and the fidelity guarantee (replay gives exact same result as the live hook) is well-implemented. Documentation and docstrings are thorough. Three findings require attention: one dead-code block (minor correctness), one double-finding emission issue in the danger detector (output quality), and one false-positive scenario in the takeover audit. No security issues found.

---

## Findings

### Major

**M1 — `toolguard/tools/danger.py` lines 629-657: Blanket-allow patterns that also fire an earlier detector receive a DOUBLE finding**

The `_audit_tool` function contains two independent loops over `lr.allow`. The first loop (lines 591-624) runs all `_DETECTORS` and `break`s after the first matching detector. The second loop (lines 629-657) checks `_is_blanket_allow` unconditionally. Any pattern that is both (a) flagged by a detector in the first loop AND (b) a blanket allow fires TWO `DangerFinding` records for the same pattern.

Concrete example: a rule `[regex].*` triggers `unanchored-regex-allow` in the first loop AND `blanket-allow-outside-takeover` in the second loop — two findings for one pattern. The `blanket-allow-outside-takeover` detector is explicitly noted as "handled separately" in the table comment, but the first loop does not skip blanket patterns to avoid the double-count.

**Recommended fix:** Add a `_is_blanket_allow` pre-check inside the first loop to skip blanket patterns there (they will be handled by the second loop):
```python
# Inside the first loop, before the detector table:
ptype, body = parse_pattern(pattern, extended_syntax=True)
if _is_blanket_allow(tool, body, ptype):
    continue  # handled by the blanket-allow loop below
```
Or alternatively, consolidate both checks into a single loop with explicit ordering.

---

**M2 — `toolguard/tools/redundancy.py` lines 272-277: Dead code in `_config_without_allow`**

The comment at line 274 reads "Only remove first occurrence if there are duplicates" but the implementation is incorrect in two ways:

1. `new_allow = [p for p in allow_list if p != wrapped_target]` removes ALL occurrences of `wrapped_target`, not just the first.
2. The guard `if new_allow == allow_list: continue` at lines 275-276 is dead code — it can never be `True` because the enclosing `if wrapped_target in allow_list:` at line 272 guarantees `wrapped_target` is in the list, so the list comprehension will always produce a shorter list.

For redundancy checking purposes, removing all occurrences is arguably correct (we are testing whether the pattern is redundant at all), but the comment and unreachable guard are misleading and the intent is unclear.

**Recommended fix:** Remove the dead guard and update the comment:
```python
if wrapped_target in allow_list:
    new_allow = [p for p in allow_list if p != wrapped_target]
    # Removes ALL occurrences (intentional: testing if any instance is redundant)
    new_perms = dict(permissions)
    ...
```

---

### Minor

**N1 — `toolguard/tools/takeover_audit.py` line 157: False-positive `hook-not-registered` finding when toolguard is registered with a wildcard matcher**

`_get_registered_toolguard_tools` adds `matcher` verbatim to the `registered` set (line 157). If a user registers toolguard with `"matcher": "*"` (Claude Code supports wildcard matchers), the function adds `"*"` to `registered` — but `governed_set & registered` computes intersection with `{"Bash", "Read", ...}`, which yields an empty set. This causes `audit_takeover` to flag every governed tool as `hook-not-registered` even though the hook IS registered.

The documentation consistently shows per-tool matchers so this is unlikely in practice, but a user following alternative Claude configuration patterns could hit it.

**Recommended fix:** After building `registered`, expand wildcard matchers against `governed_set`:
```python
if "*" in registered:
    registered |= governed_set  # wildcard covers all governed tools
```

---

**N2 — `toolguard/hook.py` lines 280-300: Legacy compound-match log parser is comma-brittle**

`_parse_compound_match_details` splits the compound reason string on `", "` (line 299 in the `for part in m.group(1).split(", ")` expression). If a sub-command itself contains `, ` (e.g. `printf 'a, b'` or shell substitutions), the split produces wrong sub-command/rule pairs. The actual permission decision is not affected — this is logging only — but the logged entries for compound commands containing commas may be garbled.

This is a pre-existing issue inherited from `compound.py`'s format. The new `sub_matches` field in `BashResolution` already provides per-sub-command data that could replace this parsing entirely.

**Recommended fix (deferred):** When `bash_result.sub_matches` is non-empty in `hook.py`'s `main()`, use `sub_matches` directly in `_log_allowed_command` rather than parsing the reason string. This eliminates the brittle regex altogether.

---

**N3 — `toolguard/tools/log_harvest.py` line 312: `harvest()` uses UTC date for `max_age_days` but log entries have no timezone**

`today = datetime.now(tz=timezone.utc).date()` produces a UTC date (line 312). `floor_dt = datetime(floor.year, floor.month, floor.day)` (line 347) is naive (no timezone). Log entry timestamps are parsed with `strptime` and are also naive (local time). The comparison `e.timestamp >= floor_dt` is naive-vs-naive, which is consistent, but the `today` calculation could be off by one calendar day around midnight for users in timezones ahead of UTC.

**Recommended fix:** Use `date.today()` (local) instead of `datetime.now(tz=timezone.utc).date()` since all other timestamps in the pipeline are local:
```python
today = date.today()
```

---

### Suggestions / Nitpicks

**S1 — `toolguard/tools/redundancy.py` line 89: `_normalised_body` only collapses double-spaces in DEFAULT patterns; single-space normalisation is incomplete**

The regex `re.sub(r"  +", " ", norm)` (line 118) collapses TWO OR MORE spaces to one, but leaves a single trailing space before `:` to be caught by the subsequent `\s*:\s*` regex. This is correct but the two-step approach is easy to misread. A single `re.sub(r"\s+", " ", norm)` would be cleaner and handle mixed whitespace.

**S2 — `toolguard/tools/danger.py` lines 221-248: `_ARBITRARY_EXEC_PREFIXES` and `_ARBITRARY_EXEC_BARE` have overlapping entries**

`"python "` (with trailing space) appears in `_ARBITRARY_EXEC_PREFIXES`, and `"python"` appears in `_ARBITRARY_EXEC_BARE`. The `_is_arbitrary_exec` function checks `_ARBITRARY_EXEC_PREFIXES` first (via `_body_fnmatch_matches_any`), then `_ARBITRARY_EXEC_BARE`. For the input `"python "` both could match. This redundancy causes no incorrect behaviour (the function returns `True` either way) but is confusing.

**S3 — `toolguard/tools/takeover_audit.py` imports `_strip_tool_wrapper` as a private function**

Line 50: `from toolguard.config import ... _strip_tool_wrapper`. Importing a private function from another module creates a fragile coupling. Consider promoting `_strip_tool_wrapper` to a public name (`strip_tool_wrapper`) in `config.py`, or inlining the simple extraction logic.

**S4 — `toolguard/scripts/migrate_permissions.py` lines 532-539: `write_json_config` silently ignores JSON/OS errors when reading existing config**

```python
except json.JSONDecodeError, OSError:
    pass
```
A corrupted JSON config file silently produces an empty `config = {}`, which on the next `json.dump` would overwrite the file with only the new permissions, destroying all non-permissions keys. Consider logging a warning or raising when the file exists but cannot be parsed.

**S5 — `toolguard/resolve.py` lines 473-481: Hard-coded reason-string prefix parsing is fragile**

`resolve_bash_permission_detailed` extracts `sub_matched_rule` by stripping a hardcoded reason prefix (`"Command matches allow pattern: "`, `"Command matches deny pattern: "`). If the reason format changes in `permissions.py`, this extraction silently yields `None` with no error. The function-call boundary between `compound.py`, `permissions.py`, and `resolve.py` is correct, but the string parsing is a maintenance burden. A structured return from the inner resolver would be more robust.

---

## Test Coverage

All 925 tests pass. Dedicated test files exist for every reviewed module. Test docstrings appear to follow the required BDD/Given-When-Then format in the test files reviewed (`test_tools_danger.py`, `test_tools_redundancy.py`, `test_tools_takeover_audit.py`). No coverage gaps were detected via inspection for the primary code paths; the edge cases flagged above (double-finding for blanket+unanchored regex, wildcard matcher audit, comma-in-command log parsing) appear to lack targeted test cases.

---

## Files reviewed (12)
1. `/home/arnon/projects/toolguard/toolguard/tools/config_access.py`
2. `/home/arnon/projects/toolguard/toolguard/tools/decision.py`
3. `/home/arnon/projects/toolguard/toolguard/tools/log_harvest.py`
4. `/home/arnon/projects/toolguard/toolguard/tools/replay.py`
5. `/home/arnon/projects/toolguard/toolguard/tools/redundancy.py`
6. `/home/arnon/projects/toolguard/toolguard/tools/danger.py`
7. `/home/arnon/projects/toolguard/toolguard/tools/takeover_audit.py`
8. `/home/arnon/projects/toolguard/toolguard/tools/sorters.py`
9. `/home/arnon/projects/toolguard/toolguard/resolve.py`
10. `/home/arnon/projects/toolguard/toolguard/rule_sort.py`
11. `/home/arnon/projects/toolguard/toolguard/hook.py`
12. `/home/arnon/projects/toolguard/toolguard/scripts/migrate_permissions.py`

---

*Review elapsed time: ~25 minutes. Estimated cost: ~$0.50 (Sonnet 4.6 pricing). 925 tests run, all passing.*