---
title: A disclosure comment can make toolguard reject the command it describes
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/36-disclosure-comments-are-not-inert-to-the-extractor
---

# Comment text is not inert to the extractor

**Found 2026-08-12 by a test-repair agent, incidentally, while trying to comply with the disclosure rule.**

## What happened

A `# INTENT:` disclosure comment containing **backticks** and a `<<` token caused toolguard to reject the whole command with `"No valid commands found in command line"`.

The comment was doing exactly what `CLAUDE.md` instructs: describing authored code before running it. The command it described was fine. **The disclosure text itself broke extraction.**

## Why this matters more than an ordinary parser bug

`CLAUDE.md` states, in the section that mandates disclosure:

> A leading comment does not affect rule matching -- the PEG parser discards it and matches the real leaf command.

That claim is **false for at least some comment text**, and it is load-bearing: it is the reason agents are told they can prepend disclosure blocks freely. The disclosure rule requires comments on exactly the commands that carry heredocs and shell metacharacters — so **the text most likely to break extraction is the text the rule most often demands.**

Worse, the failure is fail-closed to `deny` with a message about the *command*, not the comment. An agent hitting this sees "No valid commands found" and has no reason to suspect its own disclosure block. The natural recovery is to drop the comment — i.e. **the failure mode trains agents out of disclosing.**

## What is not yet known

- **Which construct is responsible** — backticks, `<<`, or the pair. Not isolated yet.
- Whether it is grammar-side (the `.peg` comment rule) or extractor-side.
- Whether the same text in a trailing comment behaves differently.
- Whether this has been silently costing disclosures already. **The logs would show it**: rejected commands whose text contains a `# INTENT:` block.

## Fix direction

Grammar territory, so the two-phase rule applies (`.claude/rules/bash-grammar.md`): `.peg` plus canopy regeneration first, reviewed, then Python. Never hand-rolled.

Whatever the fix, **`CLAUDE.md`'s claim should be corrected or made true** — it is currently an unverified universal, in a document whose whole purpose is instructing agents.

## Related

The same agent separately reported that one of its own commands went out undisclosed (a heredoc into `cat`). Both facts belong together: the disclosure rule is being followed imperfectly *and* the mechanism can punish following it.

---

# CLOSED 2026-08-23 — RE-MEASURED, fixed

Flagged during the memory-extraction pass as *"may have been fixed outright by 105's grammar comment node, never re-measured"*. Re-measured against HEAD with `allow = ["Bash(ls -la)"]` and `no_match_fallback = "ask"`:

| command | decision |
|---|---|
| `ls -la` (control) | allow |
| `# INTENT: list files` + newline + `ls -la` | allow |
| full three-line `# INTENT:` / `# TOUCHES:` / `# INLINE BECAUSE:` block + `ls -la` | allow |
| `ls -la # note` | allow |

**A disclosure comment no longer changes the decision, in any of the forms this repo's own convention produces.** That matters here specifically: the project mandates `# INTENT:` blocks before authored commands, so a comment that altered matching would have mis-decided the agent's own disclosed work.

Closed on evidence. Note the fix is now structural rather than incidental — since item 105 the grammar recognises comments as labelled nodes and the extractor excludes them from leaf text by default, rather than a pre-pass stripping them with its own quote scanner.
