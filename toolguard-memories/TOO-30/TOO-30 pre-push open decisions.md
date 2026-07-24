---
title: TOO-30 pre-push open decisions
type: note
permalink: toolguard/too-30/too-30-pre-push-open-decisions
tags:
- project
- TOO-30
- pre-push
---

## Open decisions before TOO-30 ships (as of 2026-07-23, awaiting Arnon at his console)

Arnon asked (via Telegram) to draft release notes now assuming a version bump, but wants
to review everything and decide these in person rather than over Telegram:

1. **Version bump**: `pyproject.toml` still says `0.4.1` -- NOT yet changed.
   `release-notes/0.5.0.md` has been drafted assuming `0.5.0` (semver minor bump, new
   feature), but this is a draft/assumption only. Confirm the number (or pick a
   different one) and apply it to `pyproject.toml` before shipping -- the release notes
   filename and header both assume `0.5.0` and would need renaming/editing if a
   different version is chosen.
2. **`Configuration.validation_issues()` complexity**: pyscn flagged it high-risk
   (complexity 25). Pre-existing trend, TOO-30 added one more check block to it. A
   refactor (extract each check into its own helper method) was suggested by the code
   review; recommended deferring rather than touching security-relevant code under
   push-time pressure, but Arnon's call.
3. **toolguard-maintenance skill timing**: this project's own `.claude/toolguard_hook.toml`
   is currently in the deliberately-loosened auto-mode-experiment state
   (`no_match_fallback = allow_with_warning`, two `ask` rules commented out -- see
   [[TOO-30 no_match_fallback loosened for auto-mode evidence]]). Suggested running
   maintenance after that's reverted, not while the config is known-abnormal.
4. Nothing has been committed or pushed yet.

See [[TOO-30 XDG rules directory - Requirements and Plan]] for the full ticket history.
