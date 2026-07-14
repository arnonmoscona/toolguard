---
title: TOO-15 Coder Task Recall - no_match_fallback default ask
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-no-match-fallback-default-ask
tags:
- task-memory
- TOO-15
- coder-recall
---

# Task: Change --no-match-fallback default from allow_with_warning to ask

## Ticket
TOO-15

## Background
Design decision already agreed with project owner: `toolguard-install enable-takeover`'s
`--no-match-fallback` flag currently defaults to `"allow_with_warning"` when omitted. This
should change to default to `"ask"` instead. Rationale: `ask` is safer (never lets an
unmatched command execute silently, always prompts, matching Claude Code's own native
default behavior for anything unconfigured), and it's the value the user is already
familiar with. `allow_with_warning` remains a fully valid, supported choice -- just no
longer the default. `deny` unaffected.

docs/install.md already updated (Phase 10.2, checklist, Phase 2 discussion, Wrap-up
section) to recommend `ask` as starting fallback. This task is the CLI-level fix so the
tool's actual default matches the docs.

## Required production fix (DO NOT DO YET - RED phase only first)
In `toolguard/tools/installer.py`:
1. `enable-takeover` subparser's `--no-match-fallback` add_argument call (~line 1471):
   change `default="allow_with_warning"` to `default="ask"`; update help= string
   "...none match (default: allow_with_warning)" -> "(default: ask)".
2. `_ENABLE_TAKEOVER_HELP` docstring constant (~line 673-691): currently says
   allow_with_warning is the gentle default; rewrite to describe `ask` as default
   (prompts, matches Claude Code native behavior), describe allow_with_warning/deny as
   other two accepted values. Keep concise/factual, --help tone (not persuasive docs
   tone).
3. Search rest of installer.py for other places referencing allow_with_warning "as the
   default" (4 total hits for the string existed before this task) - fix ones describing
   it as default, leave neutral listings alone.

## Tests to update (RED phase - THIS IS WHAT WE DO NOW)
`test/unit/test_tools_installer.py`:
- ~line 219-224: --help text test asserting "allow_with_warning" appears. Likely stays
  passing unchanged (still a valid choice, should still appear in help). Read carefully -
  only change if it implicitly asserts allow_with_warning is "the default" via substring.
- ~line 817-829: test running enable-takeover WITHOUT --no-match-fallback, asserts TOML
  has `no_match_fallback = "allow_with_warning"`. MUST change: update docstring
  Given/When/Then to match new assertion, update assertion to expect `"ask"`.
- ~line 834-845: neighboring test passing explicit `--no-match-fallback deny`, asserts
  deny written. Should be unaffected - confirm still makes sense, don't change unless it
  depended on old default.
- Search whole test file + rest of test/unit/ for other tests relying on old default
  indirectly (e.g. enable-takeover called without flag for unrelated purpose, then
  asserting something that assumed allow_with_warning).

## Workflow (STRICT RED-then-checkpoint)
1. Read relevant sections of installer.py and test_tools_installer.py IN FULL first
   (line numbers may have shifted).
2. Make TEST changes ONLY first. Run full suite:
   `uv run python -m unittest discover -s test -t .`
   Confirm now-red test(s) fail for the RIGHT reason (production code still defaults to
   allow_with_warning, test now expects ask). Baseline: 1431 tests all passing before
   changes. Report exact before/after counts.
3. STOP. Report which files/tests changed, before/after full-suite counts, confirmation
   of why affected test(s) fail. Do NOT touch installer.py production default yet - wait
   for explicit approval of red state.
4. Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples here) -
   `uv run ruff check .` is fine for linting.
5. Use `uv run python ...` for everything, never bare python.
6. Write report file at
   /tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-fallback-default-report.md
   with exact file paths, function/test names, full-suite pass counts before/after.

## Success criteria
- Only intended test(s) go red, for the right documented reason.
- Baseline count of 1431 confirmed before, and after change only the target test(s)
  fail (net test count may grow by 0, since we're editing not adding, unless we add
  new tests - not requested here, just editing existing pinned tests).
- Report written to scratchpad path above.
- STOP before touching production code in installer.py.