---
title: Coder Latest Task Recall
type: note
permalink: implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
- implementation
---

## Task

Rewrite every comment and docstring in `toolguard/session_start.py` so the module makes sense to read cold, per the TOO-45 punch-list #07 comment standard.

## Instructions given

1. Read `toolguard-memories/TOO-45/TOO-45 comment standard.md` in full, and the accepted exemplars `toolguard/config.py` and `toolguard/compound.py`.
2. Rule 0 (claims reaching outside the file) is the biggest source of falsehoods; verify what is KEPT, not only what is written; walk every Args/Returns/Raises against signature and body; when a deletion leaves a gap, leave the gap; never invent a rationale.
3. Two module-specific things to check:
   - "Once per session" is a trap in this codebase (toolguard is a process per tool call) -- verify any such claim against an actual `once_per` call. (Checked: no such claim exists in this file.)
   - `install_provenance.source_checkout_root` must be called with a package directory, not the project root -- verify what `_detect_shadow_status` actually passes and what the docstring says about it.
4. Comments and docstrings ONLY -- strings are code, do not change even when wrong; flag false strings in `toolguard-memories/TOO-45/reports/follow-up-queue.md`'s code-level defects table.
5. `uv run python tools/comment_hygiene.py --compare-against HEAD` must report ZERO code-shape drift for `session_start.py` (`tools/architecture_fitness.py` differing is expected/ignored).
6. Full suite green (2733 tests). Golden verdict corpus byte-identical. `ruff format`/`ruff check` clean.
7. No git write commands. Do not modify any file except `session_start.py` and the follow-up queue.
8. Do not edit `technical-notes.md` and do not add pointers to it -- propose additions verbatim in the report instead (none were needed this pass).

## Success criteria

- Module reads coherently cold.
- Every verifiable claim checked against the actual code (permission_resolution, install_provenance, error_log, config_types).
- Zero code-shape drift, full green suite, clean ruff.
- Findings reported: cuts, kept-at-length items with reasons, follow-up-queue flags, split-not-explain candidates.
