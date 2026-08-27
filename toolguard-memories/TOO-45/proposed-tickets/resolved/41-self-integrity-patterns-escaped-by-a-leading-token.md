---
title: A leading token or absolute path escapes the self-integrity hard-deny patterns
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/41-self-integrity-patterns-escaped-by-a-leading-token
---

**FIXED in `05f786d` (TOO-45 phase 2).** Self-integrity patterns now match on a token/path boundary (`^rm\b` -> `(^|[\s/])rm\b`), closing the leading-token and absolute-path escape — see `toolguard/tools/self_integrity.py:46,57`.

# `sudo rm -rf ~/.toolguard` is `ask`, not `deny`

**Found 2026-08-13. A RED test asserting the correct behaviour is in the tree.** No ticket existed for this — it was recorded only as a footnote in ticket 37.

## The defect

The self-integrity hard-deny patterns are anchored with `^`, so anything before the command name escapes them. Verified by direct probe (`decision='ask', matched_rule=None`):

| command | resolves to |
|---|---|
| `sudo rm -rf ~/.toolguard` | **ask** |
| `/bin/rm -rf ~/.toolguard` | **ask** |
| `sudo find ~/.toolguard -delete` | **ask** |
| `rm -rf ~/.toolguard` | deny |

A one-token prefix defeats the protection.

## Why this is a defect and not an accepted limit

The module's own docstring names `sudo` and the absolute-path form as known escapes, which is why the previous test pinned them as characterization. Two things make that the wrong call:

- **The same docstring says the patterns are deliberately broad and that "a false positive here costs nothing."** The design intent is over-blocking. An escape contradicts the stated trade-off rather than following it.
- **This module exists because an agent, unprompted, ran `rm -rf ~/.toolguard`.** Auto-memory records `~/.toolguard` being wiped **four times** during TOO-15 install testing, with doc-only mitigation proven insufficient each time. The protection's entire purpose is not to depend on the agent's judgement in the moment — and `sudo` is exactly the token an agent reaches for when a command does not work the first time.

`ask` is not nothing, but under a permissive auto-mode or a broad allow it is a prompt the agent can satisfy itself.

## Fix direction

Relax the leading `^` anchor in both regexes to permit a leading token or absolute path, while keeping the `.toolguard` requirement that scopes them. The `\b` in `^rm\b` should be preserved — it correctly excludes `rmdir`, which is a different program.

## Status in the tree

`test_self_integrity.test_a_prefix_token_or_absolute_path_does_not_escape_the_patterns` is **deliberately RED**, three subtests, asserting each form is denied **by a self-integrity hard-deny pattern** — it checks `matched_rule`, so a fail-closed extraction error cannot satisfy it. Goes green when the fix lands. Must not be weakened.

## Deliberately left as characterization

`rmdir ~/.toolguard/backups` is `ask`, and that is **not** covered by this fix. Whether `rmdir` deserves a pattern of its own is an open question, recorded in `test_rmdir_is_outside_the_patterns` with a docstring saying it records where the table stops rather than specifying it.