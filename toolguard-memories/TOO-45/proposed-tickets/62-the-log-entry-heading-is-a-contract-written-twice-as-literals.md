---
title: The log entry heading is a writer/reader contract duplicated as literals, and
  breaking it was undetectable across the whole suite
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/62-the-log-entry-heading-is-a-contract-written-twice-as-literals
---

**PARTIALLY FIXED in `05f786d`.** Test blindness is closed (`test/unit/test_logging_streams.py:108`); still open: the heading is still a literal written twice, in `toolguard/error_log.py:95` and `toolguard/session_start.py:91`, not a shared constant.

# `## <timestamp> - <LEVEL>` is a contract, and nothing held it

**Found 2026-08-13. Not a live defect — the format is currently correct. The finding is that changing it would have been invisible.**

## The measurement

Mutating the heading shape from `## <ts> - <LEVEL>` to `### <ts> (<LEVEL>)` produced **zero detection across the entire 2,820-test suite.**

`session_start._count_conflict_entries` **parses that heading**. It is how the SessionStart nag knows there are unresolved conflicts to report. So the writer could have stopped being countable by the only recurring notification channel toolguard has, **with a green suite.**

## Why nothing caught it

**Every test on both sides supplies its own literal text.** `test_session_start.py` writes `f"## ... - CONFLICT\n\n"` **by hand** rather than calling `log_conflict`. So the reader's tests and the writer's tests each verified their own copy of the format, and neither verified that the two agree.

**The format lives twice, as literals, in a writer and a reader with no shared constant and no shared test.** That is the "literal strings with semantic meaning belong in constants" rule with a measured consequence: not a typo risk in the abstract, but a specific silent failure of the user's only recurring alert.

Now held by `test_a_conflict_entry_is_countable_by_the_session_start_nag`, which **round-trips a real `log_conflict` write through `_count_conflict_entries`** rather than asserting either side's literal.

## Fix direction

A shared constant for the heading shape, used by both `error_log._log_entry` and `session_start._count_conflict_entries` — so a change to one is a change to both, and a typo is a syntax error rather than a silent decoupling.

The round-trip test is the belt; the constant is the braces. Both are cheap.

## Three more mechanisms that had zero detection, now held here

- **`_detect_override`'s allow-only guard** — the fixture had no less-specific level at all, so the override scan walked an empty tail
- **`_parse_discovery_line`'s `None` return** on a torn final line
- the **auto-migration claim's independent share** of the same-day gate

This module is now the **only** detector repo-wide for those three plus the heading contract.

## An equivalent-mutant judgement worth recording, because it is subtler than the usual case

`lines = lines[1:]` (the tail-window partial-line discard) is **NOT equivalent — and should still not be tested.**

Measured across five cut offsets: at cuts inside the ISO timestamp, HEAD returns `None` while the mutant returns the **correct** levels; at a cut past the first tab both return `None`, because `_parse_discovery_line` already rejects a two-field line.

So the guard is **strictly conservative**: it can cost one redundant log line and can never produce a wrong verdict. **Pinning HEAD's behaviour would enshrine the redundant write** as a specification. Left unpinned deliberately.

That is a third category beyond the campaign's usual two — not "equivalent, do not test" and not "a real gap", but **"non-equivalent, and pinning it would be worse than the gap."**

## Method note — a "floor" correctly refused

Two failures from `test_tools_takeover_audit` appeared in every repo-wide run during this work. **They were not an environmental floor**: a re-baseline five minutes later showed a sibling agent had added them mid-measurement. **Explained, not subtracted** — which is the rule this project learned the hard way after a real fixture defect was subtracted as a "floor" three times.