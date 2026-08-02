---
title: TOO-19 documentation review fixes 2026-08-01 - coder task recall
type: note
permalink: toolguard/too-19/too-19-documentation-review-fixes-2026-08-01-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task
Documentation-only fixes for TOO-19, repo /home/arnon/projects/toolguard, branch too-19.
No production code changes. Source findings: tmp/doc-review-2026-07-31.md.

**Reserved files - DO NOT TOUCH**: toolguard/log_writer.py, toolguard/hook.py,
test/unit/test_log_writer.py, test/unit/test_hook.py (another agent editing concurrently).

## Per-finding direction from Arnon

- **Finding 1 - FIX**: `undecidable_fallback` missing from AGENTS.md, llms.txt,
  docs/agent-guides.md, docs/install.md, docs/takeover-mode.md, docs/auto-mode.md.
  Also `additionalContext` missing from docs/agent-guides.md.
  Fix proportionally per doc purpose, not paste same paragraph 6x:
  - AGENTS.md: one line beside existing no_match_fallback line
  - llms.txt: index-style mention
  - agent-guides.md: real short entry covering both fallbacks + additionalContext
  - install.md/takeover-mode.md/auto-mode.md: only where they already discuss
    no_match_fallback and omission would mislead
  - Every mention links to docs/configuration.md authoritative section.
  Verify behavior against toolguard/config.py and
  toolguard/compound.py::_apply_undecidable_floor (not from prompt restatement).
  Key facts: values ask(default)/deny/allow_with_warning; top-level key only, no
  [takeover_mode] alias, no warn_deny spelling; FLOOR resolved strictest-wins (explicit
  deny/ask rule never weakened); config-parse-failure ASK floor overrides it entirely;
  allow_with_warning raises HIGH security-audit finding.

- **Finding 2 - FIX, SCOPED**: Do NOT create docs/ page, don't add to llms.txt or
  README doc table. 
  1. Complete CLI surface in technical-notes.md's existing "Isolated experiment sandbox
     (TOO-19)" section: add --user-config, --tool, --hard-deny, --json (currently only
     --config, --command documented). Get real list from toolguard/testing/sandbox.py
     argparse. Explain briefly what each is for, especially --tool (needed for Read/
     Write/Edit eval) and --user-config (hierarchy/precedence reproduction).
  2. Short cross-reference from docs/architecture.md - sentence + link, framed as dev/
     testing support element not core architecture. Not a section.

- **Finding 3 - FIX**: AGENTS.md:55 and docs/security.md:59 make absolute claim
  "[hard_deny] cannot be overridden by any allow" - false, hard_deny has its own allow
  carve-out (correctly documented at configuration.md:866 and agent-guides.md:186).
  Fix minimally: qualify claim (e.g. "by a [permissions] allow") and/or point at
  carve-out. Do NOT restate carve-out rules in either file.

- **Finding 4 - IGNORED** (Arnon 2026-08-01, "not important enough"). Do NOT touch
  agent-map.md's preamble wording.

- **Finding 5 - FIX**: Add `## Contents` section to docs/security.md (493 lines, 11
  headings), docs/architecture.md (335 lines, 15), docs/permission-patterns.md (315
  lines, 18). Match format docs/configuration.md already uses. Skip config-sync.md.
  Rationale to honor in writing: terse, scannable, jump-to-friendly - docs mainly serve
  agents.

## Style requirements
- Plain ASCII only.
- Single hyphens in any NEW heading (not double/em-dash runs) - GitHub doesn't collapse
  hyphen runs, has caused 3 real breakages. Prefer "Phase 0: Preflight" over
  "Phase 0 -- Preflight".
- Do not mass-rename existing headings (inbound links would break).
- docs/agent-map.md summarizes every doc, no other sync mechanism - update its master
  TOC and Q&A entries for EVERY heading added (separate from Finding 4's untouched
  preamble).

## Verification required
- `uv run python tools/check_doc_links.py` MUST exit 0.
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run
  python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` - still OK, report
  what's seen (other agent may change test count).
- Do not run ruff format (no Python edited).

## Update findings file inline
For each finding as completed, update tmp/doc-review-2026-07-31.md's per-finding
heading and the "Resolutions" table with outcome, following convention from
tmp/doc-review-2026-07-29.md. Mark Finding 4 IGNORED (Arnon, 2026-08-01) with reason.

## Report
basic-memory project toolguard, path
"TOO-19/TOO-19 documentation review fixes 2026-08-01.md", tagged task-memory, TOO-19.
List every file/anchor changed per finding; note anything judged out of scope; confirm
the 4 reserved files were not touched.
