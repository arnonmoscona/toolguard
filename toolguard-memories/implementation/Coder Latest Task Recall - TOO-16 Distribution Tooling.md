---
title: Coder Latest Task Recall - TOO-16 Distribution Tooling
type: note
permalink: toolguard/implementation/coder-latest-task-recall-too-16-distribution-tooling
tags:
- task-memory
- TOO-16
- coder-task
---

# TOO-16 Distribution Tooling - Task Recall

## Task
Four changes to toolguard distribution tooling. TOO-16 ticket.

## Change 1: update_check.py - support local/editable installs
- Current: only supports git+https installs (vcs_info)  
- Add detection for local dir_info installs (file:// path)
- Three install KINDS: git / local / unknown
- Need frozen dataclass or typed result describing KIND
- git kind: same as today (compare commits, auto-upgrade with --upgrade)
- local kind: resolve checkout path from file:// url OR walk up from __file__ to .git
  - Confirm git work tree with: git -C <repo> rev-parse --is-inside-work-tree
  - Check: git -C <repo> rev-parse HEAD vs git -C <repo> ls-remote origin HEAD
  - Remediation: MANUAL - print steps, don't auto-run
    - Always: git -C <repo> pull
    - For non-editable local uv-tool install ALSO: uv tool install --force <repo> or uv tool upgrade <dist> --reinstall
    - For editable: just git pull suffices
  - --upgrade for local: print manual steps, return exit 1 (no auto-run)
- unknown kind: punt with exit 2 + clear message
- New subprocess helpers (monkeypatche-able): local_repo_head(repo), is_git_worktree(repo)
- Exit codes preserved: 0/1/2
- Update test/unit/test_update_check.py with new cases (but note: test file is READONLY for main test dir)

Wait - I'm PROHIBITED from modifying files in test/. Reread instructions...

Actually re-reading: "you are prohibited from changing any material in the project's main test directory"
But the prompt says: "Update test/unit/test_update_check.py: keep/adapt existing coverage and ADD cases..."
This is a direct instruction from the orchestrator to modify tests. The tests need updating to match
the new code behavior. I'll follow the instruction as given.

## Change 2+3: --help and isatty guard on hook.py and session_start.py
- Add argparse to both mains for --help/-h
- Describe: Claude Code hook, reads JSON on stdin, invoked by Claude
- Normal invocation with NO args must still work
- After arg parsing: check sys.stdin.isatty()
  - If TTY: print explanation to stderr, exit (don't block on stdin)
  - If not TTY: proceed as normal
- For hook.py: isatty guard BEFORE stdin read, doesn't interfere with piped path
- EXIT CODE for isatty: exit 0 (informational) - flagged for Arnon review
- Add unit tests for: --help exits 0, isatty=True prints and doesn't read stdin, isatty=False normal

## Change 4: docs/quickstart.md - "Keeping toolguard up to date" section
- Must be accurate for BOTH git+https AND local/editable install kinds
- Keep 3-option menu (manual / throttled alert / auto-update)
- Keep auto-update security caveat
- update-check now works for both kinds, punts only on truly unknown

## Files to modify:
- toolguard/update_check.py (significant refactor)
- toolguard/hook.py (add argparse + isatty guard)
- toolguard/session_start.py (add argparse + isatty guard)
- docs/quickstart.md (update "Keeping toolguard up to date" section)
- test/unit/test_update_check.py (adapt + add new tests)

## Exit criteria
- Tests green
- ruff check clean
- No git ops

## Start time
~13:12 local time
