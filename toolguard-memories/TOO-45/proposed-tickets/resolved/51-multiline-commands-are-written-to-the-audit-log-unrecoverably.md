---
title: 4.3% of audit-log Command fields cannot be parsed back, and heredocs are hit
  hardest
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/51-multiline-commands-are-written-to-the-audit-log-unrecoverably
---

**FIXED in `05f786d` (TOO-45 phase 2).** Loss is now loud rather than silent (historical loss re-measured at 4.84%, higher than the ticket's original 4.3% estimate) — see `toolguard/log_writer.py:257,318` and `toolguard/log_harvest.py:224,232`.

# The audit trail records commands it cannot read back

**Found 2026-08-13. Two RED tests are in the tree. Measured against this repository's own `logs/`, not a fixture.**

## The measurement

**1,783 of 41,442 written Command fields — 4.3% — cannot be recovered by the only reader of the format.** Every day since 2026-07-31.

## Two mechanisms

1. **Raw newlines.** `_render_markdown_entry` emits a multi-line command's newlines verbatim. `log_harvest._COMMAND_RE` matches per line and requires a closing backtick, so a multi-line command's **entire audit entry** is unparseable.
2. **A `## ` line inside a command.** It splits the section in `_iter_sections`: the head has no closing backtick, the tail has no Status, and **both halves are discarded.** Measured: zero entries recovered from a `git commit -F - <<EOF` / `## Release notes` / `EOF` entry.

## Why this one stings

**This is the 813/975 defect one layer downstream.** The record is in the file. It looks complete to a human reading the log. It is invisible to the only program that reads the format. Nothing fails and nothing warns — the same signature as the original.

And the loss is not uniformly distributed: **it falls hardest on heredocs and multi-line commands**, which are precisely the commands `CLAUDE.md`'s disclosure rules exist to make auditable. The disclosure block is written, the command runs, and the record is unrecoverable. **The audit trail is weakest exactly where it was designed to be strongest.**

## INDEPENDENTLY RE-MEASURED 2026-08-13 from the reader side — larger, and worse

Measured across all 48 daily log files:

| | |
|---|---|
| sections found | 49,665 |
| parsed into entries | 40,707 |
| Discovery sections (legitimately skipped) | 7,014 |
| **lost sections carrying a Status or Command field** | **1,856** |
| headerless remnants | 88 |
| Command fields written | 42,563 → **4.4% loss** |
| **days affected** | **22 of 48** |

**All 88 remnants are tail-halves of `## `-split entries** (`## Summary`, `## Reproduction` from heredoc bodies) and **none carries a valid timestamp header** — mechanism 2 confirmed independently. The sampled losses are exactly the disclosure-block and heredoc commands.

## NOTHING REPORTS THE LOSS, ON ANY CHANNEL

`parse_log_file` skips a section and appends nothing. `harvest` swallows `OSError` per file and returns `[]` for an unreadable directory. `log_harvest` imports nothing from `error_reporter`, emits no `warnings`, writes no stderr, and returns no count.

**A harvest of 40,707 entries and a harvest of 40,707 entries that silently dropped 1,856 are byte-identical in every observable.** That is why a 4.4% loss ran unnoticed since July — ticket 29's family, now confirmed a seventh time, on the audit trail itself.

## THE FIX HAS A TRAP IN IT — measured, not predicted

**7,014 Discovery sections are legitimately skipped.** A naive "report every skipped section" fix therefore emits **four times more noise than signal — a 79% false-positive rate** — and would be turned off within a day.

This was proven rather than argued, by mutating toward three candidate fixes in process:

- **Fix A** — report only *entry-shaped* sections that failed to parse: **3 of 4 red tests go green, zero other tests break.**
- **Fix B** — report every skipped section: the discrimination test **correctly stays red**, proving that half of the contract is load-bearing rather than a vacuous extra assertion.
- **Fix C** — recover a multi-line Command field: the multi-line test goes green and the heredoc/`## ` test **stays red**, confirming the two mechanisms are separately pinned.

**So the two mechanisms need two fixes.** A section-level retry cannot touch the `## `-split case, because the damage happens in `_iter_sections` **before** `_parse_section` ever runs.

## Why the reader needs its own tests even if the writer is fixed

The four red tests here assert **recover-or-report**, which is deliberately fix-direction-neutral. Even a perfect writer-side fix leaves **48 days of existing logs** that still need reading — so the reader's behaviour on unparseable input is a separate contract, not a duplicate of `test_log_writer`'s round-trip pair.

## Fix direction

Either end works and the tests do not prejudge it:

- **the writer** escapes or encodes the command (fenced block, escaped newlines, or a JSON-encoded field), or
- **the harvester** learns the multi-line shape.

The two RED tests assert the **observable contract** — write it, read it back, get the same command — so whichever end is fixed, they go green.

## Status in the tree

- `test_log_writer.test_a_multiline_command_round_trips` (:1462)
- `test_log_writer.test_a_command_containing_a_markdown_heading_round_trips` (:1482)

## The 813/975 fix itself IS well pinned — checked, not assumed

`test_hook.TestLogAllowedCommand` drives the real `resolve_bash_permission_detailed` pipeline and asserts one `log_command` call per sub-command. Mutating `hook._log_allowed_command`'s `for unit in verdict.sub_matches:` to `verdict.sub_matches[:1]` — reinstating the pre-fix "one entry per command" behaviour — **fails 4 of 6 tests**, including the fallback-leaf case that was the original defect. That regression cannot land silently.

## A third inert-mock shape, for proposed ticket 43's sweep

`test_log_writer.py` imports `log_command` **by value**, and what it imports is the TOO-19 **guard wrapper** (`_guard_log_command`), not the raw function. So mutating `log_writer.log_command` is inert **twice over** — a probe must re-wrap the mutant in the guard *and* rebind it in the test module's namespace.

Before that was corrected, five mutations read as **zero detection** (write-nothing, truncate-instead-of-append, both format selectors, `logging_enabled` ignored). Afterwards they produce 22, 3, 3, 8 and 3 failures.

**Any probe against a decorated or guarded function will hit this.** It is a strictly harder case than ticket 43's, because the by-value name and the wrapper hide each other.