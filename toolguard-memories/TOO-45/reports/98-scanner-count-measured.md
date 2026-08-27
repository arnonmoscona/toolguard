---
title: 98-scanner-count-measured
type: note
permalink: toolguard/too-45/reports/98-scanner-count-measured
---

# Ticket 98 - how many quote scanners are actually left, measured

**Measured 2026-08-21, after chunk 2 (`b8947a4`), before chunk 3.** Recorded because chunk 4's documentation page is supposed to open with this claim, and the tidy version of it is **false**.

`multiline.py`'s own docstring admitted, before this ticket: *"The quote scanners across steps 2-4 do not agree; each documents its own model."*

## The count

| | pre-98 (`f11ba43`) | after chunk 2 (`b8947a4`) |
|---|---|---|
| file lines | 683 | **794** |
| top-level functions | 12 | 19 |
| functions tracking quote state | 4 | 4 |
| **independent quote MODELS** | **4** | **3** |

Pre-98 the four were `_join_backslash_continuations`, `_split_on_unquoted_pipe`, `_statement_bounds_containing`, `_strip_comments`.

After chunk 2 the four are `_join_backslash_continuations`, `_strip_comments`, `_line_quote_states`, `_unescaped_count` -- **but the last two are one model, not two**: `_unescaped_count` is called only by `_line_quote_states`, which is called only by `_find_heredocs_in_line`. So two ad-hoc scanners were deleted and one shared, named scanner replaced them.

## What this means for the chunk 4 write-up

**Do not write "four scanners became one."** The measured result is:

- **4 independent models -> 3.** The two the ticket targeted are gone; `_join_backslash_continuations` and `_strip_comments` still carry their own, and this ticket never claimed to touch them.
- **The file got BIGGER**, 683 -> 794 lines, +16%. Attribution from a parse tree is more code than a token scan, not less. Chunk 3 moves that code out of this file, so the final number for `multiline.py` is not known yet -- **take it after chunk 3, not from this note.**

The honest framing is not "fewer scanners" but **"the two scanners that decided a SECURITY-RELEVANT question were replaced by the grammar; the two that remain do lexical bookkeeping."** That is a claim about which decisions rest on a hand-rolled model, not about a line count -- and it is the claim that actually matters.

## Why this is recorded rather than just used

The satisfying number (4 -> 1) was available and would have gone unchallenged; the docstring's own wording invites it. Measuring gave a smaller, less quotable, true number. This campaign has now produced several claims that were *nearly* true in the flattering direction -- the compression failure mode named in the global comment rules, appearing in a design document rather than in a comment.