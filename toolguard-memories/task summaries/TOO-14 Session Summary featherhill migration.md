---
title: TOO-14 Session Summary featherhill migration
type: note
permalink: toolguard/task-summaries/too-14-session-summary-featherhill-migration
tags:
- task-summary
- TOO-14
---

# TOO-14 Session Summary: featherhill/.claude/ migration

**Date**: 2026-06-11
**Status**: Deployed (hooks/statusline/commands live); feature-coder drafts await review

## What was done

Scanned `~/projects/flowers/featherhill/.claude/` for content that could be promoted to
user-level `~/.claude/`. Analyzed, planned, and deployed the project-independent content.

## Deployed to `~/.claude/` (live)

- `hooks/log-conversation.sh` + `README.md` -- session-end transcript archiver
- `statusline/combined_statusline.js` + `ctx_monitor.js`
- `commands/`: sort-permissions, critical-thinking, denied-summary (checked_bash stripped), recall (1 line), reread-directives (2 paragraphs), use-subagents (feature-coder only)
- `settings.json` -- added `hooks.SessionEnd` + `statusLine` wiring
- Backup at `~/.claude/backups/2026-06-11_16-38-04/`

## Staged in `toolguard/tmp/drafts/` (awaiting review)

- `dot-claude/agents/feature-coder.md` -- generic user-level base, reads `.claude/feature-coder-addendum.md` at startup
- `featherhill/.claude/feature-coder-addendum.md` -- featherhill stack/tools/patterns (~60 lines)
- `design-notes/project-customization.md` -- addendum pattern vs TOML capabilities analysis

## Key decision

Generic feature-coder reads an optional per-project addendum. Methodology (85%) in generic; stack specifics (15%) in addendum. TOML/XML capabilities rejected (complexity without benefit).

## Next steps

1. Review `toolguard/tmp/drafts/` (feature-coder + featherhill addendum)
2. If approved: deploy to `~/.claude/agents/` and featherhill `.claude/`
3. Commit `dot_files` repo (all `~/.claude/` changes are untracked symlink target)
