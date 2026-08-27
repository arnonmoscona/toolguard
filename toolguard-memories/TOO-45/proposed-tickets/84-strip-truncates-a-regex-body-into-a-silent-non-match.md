---
title: parse_pattern's .strip() truncates a REGEX body ending in escaped whitespace,
  and the error is swallowed
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/84-strip-truncates-a-regex-body-into-a-silent-non-match
---

# A `[regex]` deny rule ending in `\ ` silently never fires

**Found and verified 2026-08-20**, incidentally, while implementing ticket 78's follow-up.

`parse_pattern` calls `.strip()` on the pattern body. A `[regex]` body ending in **escaped whitespace** — `\ ` or `\t` — loses the whitespace and keeps the backslash. The result is a dangling backslash, `re.compile` raises `re.error`, and the error is **swallowed and treated as a non-match**.

So a deny rule of that shape does not fail loudly, does not warn, and does not deny. It silently matches nothing.

## Why the swallow is the serious half

An invalid regex in a **deny** rule is not a neutral event: the rule was written to stop something, and the outcome is that it stops nothing while appearing configured. Whether the right answer is to refuse the write, surface a validation issue, or raise the ask floor for that tool is the decision this ticket carries — but "compile it, fail, and continue as if it did not match" is wrong under every reading.

Note the pattern this repeats: **a mechanism that fails open and says nothing.** The same shape as `log_crash` throwing out of the hook's own except clause, as the corpus that could not observe the ASK floor, and as the checkers that reported PASS having examined nothing. It is the campaign's most common single defect.

## Scope

Two questions, both cheap to answer and neither answered yet:

1. **Is `.strip()` right for any pattern type?** It is plausibly wrong for `[glob]` too, and for a DEFAULT pattern whose trailing space is meaningful. The fix may be narrower or wider than the regex case.
2. **Where else is a pattern compiled and its failure swallowed?** The bug here is the swallow, not the strip; fixing the strip alone leaves every other malformed regex silently inert.

Exposure today is unmeasured — no rule in this repository ends that way — so this is prospective rather than live. That is not a reason to defer it, since the failure mode is silent by construction and would not announce itself if it ever became live.
---

## FIELD EXPOSURE MEASURED 2026-08-20 — 57,148 real decisions

Corpora: `~/projects/flowers/featherhill/logs` (49 daily logs, 4,722 decisions — **a real user project, the corpus that counts**), `toolguard/logs` (51 logs, 52,191 — dogfood, biased to this repo's own development), `instagram-downloader/logs` (7 logs, 235).

| shape this ticket needs | featherhill | toolguard | instagram | total |
|---|---|---|---|---|
| rule ending in escaped whitespace | **0** | **0** | **0** | **0** |

Confirms the ticket's own "exposure today is unmeasured" as **zero**.

**PARTIAL DEFER CANDIDATE — flagged for Arnon.** The `.strip()` half is prospective and can wait. **The swallow half arguably should not**: the ticket's own framing is that *"the bug here is the swallow, not the strip"*, and a silently-inert deny rule is this campaign's most repeated defect shape. Splitting the ticket is the likely right answer — measure how many *other* pattern compiles swallow their failure before deciding, since that count is the real exposure and it has not been taken.
