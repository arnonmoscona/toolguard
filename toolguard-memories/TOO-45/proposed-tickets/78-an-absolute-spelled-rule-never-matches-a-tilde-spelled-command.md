---
title: An absolute-spelled rule never matches a tilde-spelled command, because normalize_path
  never expands ~
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/78-an-absolute-spelled-rule-never-matches-a-tilde-spelled-command
---

# `deny Bash(cat /home/arnon/.ssh/id_rsa)` does not fire on `cat ~/.ssh/id_rsa`

**Found 2026-08-14, measured through the real matcher against a `git archive HEAD` copy.** Pre-existing at HEAD — not introduced by this campaign, and not covered by any test, so it is not one of the 137 phase-1 reds.

`normalize_path` never expands `~`. Normalization runs in the collapsing direction only: an absolute path can be rewritten to its `~` spelling, but a `~`-spelled path is never rewritten to its absolute form. So matching is **asymmetric**:

| rule spelling | command spelling | result |
|---|---|---|
| `~/.ssh/id_rsa` | `/home/arnon/.ssh/id_rsa` | matches (fixed today) |
| `/home/arnon/.ssh/id_rsa` | `~/.ssh/id_rsa` | **does not match** |

**On a deny rule this is a fail-open.** Anyone who writes their deny rules with absolute paths — which is the more natural spelling for a security-minded user, and the spelling most documentation examples use — has rules that an agent evades simply by writing `~`. No trick is required and no warning is produced.

## Relationship to the fix that landed today

Today's work fixed the *other* direction. `match_command` built its candidate spellings as `[raw, fully_normalized]`, and because full normalization resolves symlinks, the resolved form **replaced** the home-collapsed form rather than joining it. `_command_variants` now returns a deduplicated trio — raw, home-collapsed, symlink-resolved — which restores `~`-spelled rules against absolute commands.

The inverse needs a **fourth variant, tilde-expanded**, which was deliberately out of scope for that change. It is the same family and the same one-line-of-reasoning cause: *a spelling was discarded rather than accumulated.*

## Why it deserves its own ticket rather than a footnote

The trio was verified to change **zero** verdicts across the ~6,500-input corpus. A fourth variant may not be free — every added variant widens what both allow and deny rules catch, and `~` expansion depends on `Path.home()`, which this campaign has just been reminded can fail (`log_crash` threw `RuntimeError('Could not determine home directory')` straight out of the hook's own except clause). A variant that raises during matching would be worse than the gap it closes.

So: measure the corpus impact before adopting, and make the expansion non-throwing.