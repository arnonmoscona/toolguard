---
title: latest-code-review-report
type: note
permalink: latest-code-review-report
tags:
- code-review
- TOO-19
---

# Code Review Report -- 2026-07-27

**Scope:** `toolguard/tools/installer.py`, `toolguard/rule_sort.py`,
`test/unit/test_tools_installer.py`, `test/unit/test_rule_sort.py` (TOO-19)
**Reviewer:** code-reviewer subagent
**Elapsed:** ~7 minutes | **Files reviewed:** 4 | **Est. cost:** ~$3

## Summary

The change set is high quality overall. Routing every config write through
`config_write_guard.verified_write_config` is a genuine security improvement, the
`RuleEntry` normalization at the seed-command boundaries fixes real, reproducible
crashes, and `_ensure_trailing_comma` correctly handles the comma-in-inline-comment
edge case. Test quality is strong (168 tests pass, BDD docstrings throughout, ruff
clean). Two Major issues stand out: a **silent comment-loss regression** in the
rewritten `[permissions]` parser, and a **content-loss guard that was deliberately
skipped for `settings.json` on a factually incorrect premise**.

**Findings:** Critical 0 | Major 2 | Minor 5 | Suggestions 2

---

## Major

### M1. Comments after the last `]` in `[permissions]` are now silently deleted

**File:** `toolguard/rule_sort.py:747-775` (`parse_permissions_section_with_comments`)

The rewritten parser iterates located subsections and captures gap text only
*between* them (`gap_text = section_text[prev_end:match_start]`). Text after the
**final** subsection's closing `]` -- still inside the `[permissions]` section slice
returned by `find_section_boundaries` -- is never collected, so it does not appear in
`parsed_structure` and is dropped by `reassemble_permissions_section`. The old
line-by-line parser flushed it as a bottom comment_block.

Confirmed end-to-end through `migrate_permissions.write_toml_config`:

```toml
[permissions]
allow = ["Bash(git:*)"]

# IMPORTANT: hard_deny below protects secrets. Do not remove.

[hard_deny]
```
After a write cycle the `# IMPORTANT:` line is gone. This is unrecoverable comment
loss in a security tool's config, and it is exactly the defect class the
`verified_write_config` work was introduced to stop (the guard only checks
*patterns*, not comments, so it does not catch this).

**Fix:** after the `for match_start, perm_type, ... in located:` loop, take
`section_text[prev_end:]`, run it through
`_flush_comment_lines(_trailing_comment_source_lines(...))`, and append it as a
trailing `comment_block` to the last located `perm_type`. Add a regression test.

### M2. `cmd_register_hooks` skips the content-loss guard on `settings.json`, on a false premise

**File:** `toolguard/tools/installer.py:579-583`

```python
# No expected_patterns: this is Claude's settings.json (hooks/matchers), not a
# toolguard permissions/hard_deny config -- the guard's pattern-preservation
# check has no meaning for this file's shape.
verified_write_config(settings_path, json.dumps(data, indent=2) + "\n", "json")
```

The premise is wrong. Claude Code's `settings.json` **does** carry a
`permissions.allow/deny/ask` block (that is the native config toolguard is a drop-in
replacement for), and `config_write_guard.patterns_in_config_text` explicitly
supports `file_format="json"` and extracts under `permissions`/`hard_deny`. This
function does a full read-modify-write of the entire settings file, so a bug in the
hook-merging code could silently drop a user's native permission rules -- the exact
scenario the guard exists to refuse.

**Fix:** capture the original text before mutation and pass
`expected_patterns=patterns_in_config_text(original_text, "json")` (guarding for the
file-does-not-exist case). Correct the comment. Add a test that an existing native
`permissions` block survives `register-hooks`.

---

## Minor

### m1. `.pattern if isinstance(entry, RuleEntry) else entry` triplicated

- `toolguard/rule_sort.py:121` (inline in `get_tool_priority`)
- `toolguard/rule_sort.py:171` (`_pattern_of`)
- `toolguard/tools/installer.py:98` (`_entry_pattern`)

`installer._entry_pattern`'s docstring justifies the copy as "rather than importing
that private name" -- but the right move is to make it public. Rename `_pattern_of`
to `pattern_of`, export it, use it in all three sites (including inside
`get_tool_priority`). One-line helper, three implementations, twenty lines of
justification is a poor trade.

### m2. `cmd_seed_self_perms` complexity (pyscn: CC 23 / cognitive 25, "high") and duplication with `cmd_seed_hard_deny`

**File:** `toolguard/tools/installer.py:715-880` and `1600-1690`

pyscn also flags these two as a Type-4 clone pair (similarity 0.70). Both perform the
identical sequence: normalize `[hard_deny]` deny/allow via
`normalize_entries_preserving` -> build an `existing_patterns` set -> loop the
required protections -> `_render_hard_deny_section` -> `_replace_or_append_toml_section`
-> compute `expected_patterns` via `patterns_in_config_text | real_patterns(...)` ->
`verified_write_config`. That is ~35 duplicated lines carrying security-relevant
logic in two places, where they can drift.

**Suggested refactor:** extract
`_apply_hard_deny_protections(config_path, original_text, protections) -> (added, already_present)`
and have both commands call it. That alone should drop `cmd_seed_self_perms` well
under CC 10.

### m3. `reassemble_permissions_section` complexity (pyscn: CC 16 / cognitive 40 / nesting 5, "high")

**File:** `toolguard/rule_sort.py:754-925`

Cognitive complexity 40 is the highest in either file. The function does four
distinct jobs in one body.

**Suggested refactor:** extract
`_classify_parsed_items(parsed_items) -> (top_comments, bottom_comments, rule_lines, rule_comments)`
and `_key_entries(entries) -> List[Tuple[entry, key]]`. The remaining emit loop then
reads as a straight render.

### m4. `_render_toml_scalar` turns `None` into the literal string `"None"`

**File:** `toolguard/rule_sort.py:233-243`

A JSON config's `null` element (deliberately preserved by
`normalize_entries_preserving`) round-trips into TOML as the string `"None"` -- an
invented, non-matchable rule pattern that now looks like a real one in the file.
`test_none_entry_value_renders_without_crashing` locks this behavior in.
"Does not crash" is the right goal; "silently fabricates a rule" is not.

**Suggested fix:** handle `None` explicitly -- either skip the element with a warning,
or render it in a form that is unmistakably not a pattern. At minimum, state the
chosen semantics in the docstring rather than letting it fall through the `str()`
catch-all.

### m5. Docstring drift in `reassemble_permissions_section`

**File:** `toolguard/rule_sort.py:815-816`

"patterns are sorted using :func:`sort_patterns`" -- the code now sorts inline with
`sorted(keyed_entries, key=lambda pair: get_tool_priority(pair[0]))`. Behaviorally
equivalent, but the reference is stale. Point at `get_tool_priority` instead.

---

## Suggestions

### s1. Comment volume has crossed into archaeology

Roughly 60% of the installer diff and a large share of the `rule_sort` diff is prose
recording review-fix history: ticket phase numbers, "confirmed repro", "TOO-19 review
fix M3/M5", what the *previous* implementation did wrong. `_entry_pattern` is a
one-line function with a twenty-line docstring; `_toml_value_of_chunk`'s docstring is
~40 lines for a two-line body.

Docstrings should state the current contract. The "why this changed" belongs in the
commit message and the ticket, where it cannot go stale. As written, a future edit
that changes behavior will leave a paragraph of confidently-wrong history behind --
and this codebase's own memory notes already record stale-narrative incidents.

### s2. Test gaps

Test quality is otherwise excellent (clear Given/When/Then, real regression framing,
no over-mocking). Missing:

1. Comment after the last `]` inside `[permissions]` (finding M1) -- untested, which
   is why the regression landed. `test_comment_before_first_rule_and_after_last_rule_both_captured`
   covers only *inside* the array.
2. Inter-subsection gap-comment attribution -- documented at length in
   `parse_permissions_section_with_comments`'s docstring, no direct test. (Verified
   manually: it works, and moves the comment inside the following array.)
3. `cmd_register_hooks` preserving an existing native `permissions` block (finding M2).

---

## What is done well

- **`verified_write_config` wiring is complete and correct** for the toolguard TOML
  paths. All remaining `_atomic_write_text` calls (journal x3, state-dir README) are
  genuinely non-config, and the docstring at `installer.py:230` says so explicitly.
- **`_ensure_trailing_comma`** (`rule_sort.py:579`) correctly ignores commas inside an
  inline comment -- the obvious naive version would have been wrong.
- **`SyntheticPattern` / `real_patterns` interplay** is a neat solution to the
  "malformed entry must not look like a dropped rule to the write guard" problem.
- **Duplicate-pattern `(pattern, occurrence_index)` keying** correctly preserves two
  same-pattern entries with different `additionalContext`, with a test proving it.
- `ruff check` clean; 168 tests pass in 0.18s.

## pyscn summary (project grade B)

Only two functions in scope are flagged high-risk: `cmd_seed_self_perms` (CC 23) and
`reassemble_permissions_section` (cognitive 40). Both are addressed above (m2, m3).
Clone pairs flagged at `installer.py:412<->1555` and `254<->1135` are docstring
boilerplate and not actionable; `696<->1594` is the real one (m2).
