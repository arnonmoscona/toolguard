---
title: verify_config_text accepts any JSON document, so a verified write can overwrite
  settings.json with "null"
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/40-verify-config-text-is-a-parse-check-not-a-loadability-check
---

**PARTIALLY FIXED in `05f786d`.** A dict-shape check was added (`toolguard/config_write_guard.py:125-130`); still open: an empty-string write still succeeds, `expected_patterns` still iterates characters instead of the parsed structure, and file-mode checking is still limited to 0644 -> 0600.

# The parse check is not a loadability check

**Found 2026-08-13 by the test-repair campaign. A RED test asserting the correct behaviour is already in the tree.**

## The defect

`verify_config_text` checks only that the text **parses**. toolguard's own loader additionally requires a **top-level table/object** — `config.py:_parse_source_recording_failures` raises `TypeError: expected a top-level object/table`, records a parse failure, and **clamps every governed decision to `ask`**.

So the guard accepts documents the loader will reject. Measured: `null`, `[]`, `3`, `"hello"` all pass `verify_config_text(..., "json")`.

Worst case, executed:

```
verified_write_config(path, "null", "json")
```

**overwrites a real `settings.json` with `null` and returns success.** The resulting config cannot be loaded, so every decision clamps to `ask` — the exact outcome the module's own docstring says it exists to prevent.

## Mutate toward the fix

Adding an `isinstance(parsed, dict)` check to `verify_config_text` takes the repaired module **from 5 failures to 0** and breaks nothing else.

**At HEAD, that same fix produced 0 failures** — the suite could see neither the defect nor its correction. That is the strictly stronger statement ticket 31's method note asks for.

## Status in the tree

`test_json_parsing_to_a_non_object_is_refused` is **deliberately RED**, asserting the correct behaviour. Per the campaign's phase 2 it goes green when the fix lands. It must not be made green by weakening it.

## Two smaller holes in the same guard, both pinned

- **Both checks succeed on empty input.** `expected_patterns=[]` verifies nothing and reports success; `verify_config_text("", "toml")` accepts the empty string, since empty TOML is a valid empty table. Together, `verified_write_config(path, "", "toml", expected_patterns=set())` **writes a zero-byte config file and reports it verified.** (Refusal is not the right fix — a genuinely rule-free original legitimately yields an empty set. The fix is a signal the caller can see: report *what was checked*, not just success. Same remedy as tickets 29 and 37.)
- **`expected_patterns` accepts a bare `str` and iterates its characters.** `expected_patterns="Bash(ls)"` refuses the write with `missing pattern(s): (, ), B, a, h, l, s`. A caller-side footgun with a nonsense diagnostic and no type guard.

## Also found: an unreviewed side effect

**A verified write silently resets the destination's file mode to 0600.** An existing 0644 config comes back 0600, because `os.replace` carries the `mkstemp` file's mode onto the destination. Invisible to git, which tracks only the executable bit. Pinned by a characterization test so a phase-2 change is visible — not a claim that 0600 is wrong, only that it was never decided.

## What the module was NOT blind to

Worth recording, since this ticket is otherwise all bad news: the pattern-loss check and the parse refusal are both genuinely load-bearing — deleting either fails tests, at HEAD and more so now. **Atomicity was the blind spot**: replacing `_atomic_write` with a truncate-in-place that still called `os.replace(path, path)` left all 19 original tests green. The only atomicity signal was that *something* called `os.replace`, noticed incidentally by a temp-file-cleanup test. Now genuinely observed — one rename, from a sibling temp file, with the destination holding its original bytes until it fires, and `fsync` before it.