---
title: TOO-30 no_match_fallback loosened for auto-mode evidence
type: note
permalink: toolguard/too-30/too-30-no-match-fallback-loosened-for-auto-mode-evidence
tags:
- project
- TOO-30
- automode
---

Project-level `.claude/toolguard_hook.toml` in the toolguard repo got a top-level
`no_match_fallback = "allow_with_warning"` added 2026-07-23, overriding the user-level
`[takeover_mode].no_match_fallback = "ask"` default for this project only.

**Why:** Arnon is running this session in Claude Code auto mode to collect behavioral
evidence for the auto-mode classifier investigation ([[Auto-mode classifier investigation]]).
Leaving the default `"ask"` would prompt (block) on any unmatched command, defeating the
point of running unattended.

**How to apply:** This is a deliberate, TEMPORARY weakening of this project's own
fail-safe default -- not a permanent policy change. Remind Arnon to revert it (delete the
`no_match_fallback` line and comment in `.claude/toolguard_hook.toml`) once the evidence
-collection session(s) are done, especially before resuming normal (non-auto-mode) work or
pushing. Flag it again at the next pre-push checklist pass.
