---
title: TOO-19 documentation review fixes 2026-08-01
type: note
permalink: toolguard/too-19/too-19-documentation-review-fixes-2026-08-01
tags:
- task-memory
- TOO-19
---

## Summary

Documentation-only fixes for TOO-19 per Arnon's per-finding direction on
`tmp/doc-review-2026-07-31.md`. Findings 1, 2 (scoped), 3, 5 fixed; Finding 4 marked
IGNORED per Arnon's explicit instruction. No production code touched. All edits are to
`.md`/`llms.txt` files.

## Files changed, per finding

**Finding 1 -- `undecidable_fallback` missing from agent-facing docs (FIXED)**
- `AGENTS.md` -- new bullet in "Key facts" pointing to
  `docs/configuration.md#undecidable-fallback` (combined in the same edit as the Finding 3
  qualifier on the adjacent `[hard_deny]` bullet).
- `llms.txt` -- extended the existing agent-map.md index line to mention the
  no_match_fallback/undecidable_fallback distinction question.
- `docs/agent-guides.md` -- new "Ground rules" bullet covering both fallbacks and
  `additionalContext` together, linking all three `configuration.md` sections.
- `docs/install.md` -- one sentence appended to the Phase 2 `no_match_fallback` decision
  block (the only substantive discussion site in that file; three passing mentions
  elsewhere at lines ~199/438/785 left untouched as judged non-misleading).
- `docs/takeover-mode.md` -- one paragraph after the main `no_match_fallback` explanation
  block (after the `configuration.md#no-match-fallback` link).
- `docs/auto-mode.md` -- a full paragraph after "The honest tradeoff" / "Say this plainly"
  block, since this page's entire premise (unattended-run hangs) applies identically to
  `undecidable_fallback` and tuning only `no_match_fallback` would leave a false sense of
  full coverage.
- `docs/configuration.md`, `docs/security.md`, `docs/agent-map.md` already had it correctly
  -- confirmed, not edited for this finding (agent-map.md's Q&A section already has a
  correct entry covering both settings and `additionalContext`).

**Finding 2 -- sandbox CLI half-documented (FIXED, scoped per Arnon: no `docs/` page)**
- `technical-notes.md` -- "Isolated experiment sandbox (TOO-19)" section gained the full
  flag list (`--config`, `--user-config`, `--command`, `--tool`, `--hard-deny`, `--json`),
  each with a one-line purpose explanation, sourced directly from
  `toolguard/testing/sandbox.py::_build_argparser` (read, not guessed).
- `docs/architecture.md` -- one cross-reference sentence added after the parser-generator
  paragraph, framed as dev/testing support rather than core architecture (per Arnon), linking
  to the technical-notes.md section.
- No `docs/` page created; `llms.txt` and README's doc table untouched, as directed.

**Finding 3 -- `[hard_deny]` absolute claim omits carve-out (FIXED)**
- `AGENTS.md` -- "cannot be overridden by any allow" -> "cannot be overridden by a
  `[permissions]` allow at any level (it has its own narrow `hard_deny.allow` carve-out
  list...)" with a link to `docs/configuration.md#configuration-reference`.
- `docs/security.md` -- same qualifier added to the "Blanket allow risks" section's
  `[hard_deny]` sentence. Neither file restates the carve-out rules themselves (both point
  to `configuration.md`, where they already live correctly).

**Finding 4 -- agent-map.md preamble overstates coverage (IGNORED per Arnon, 2026-08-01,
"not important enough")** -- not touched, as instructed.

**Finding 5 -- four large docs lack internal navigation (FIXED)**
- `docs/security.md`, `docs/architecture.md`, `docs/permission-patterns.md` each gained a
  `## Contents` section (annotated bullet list matching `docs/configuration.md`'s existing
  format, with nested sub-bullets for `###` headings), inserted after the opening
  paragraph(s) and before the first content heading.
- `docs/config-sync.md` left untouched, as instructed (borderline case Arnon did not ask
  for).
- `docs/agent-map.md` -- added a `[Contents](...#contents)` entry to the master TOC for all
  three files, matching how `configuration.md`'s own Contents heading is already listed
  there (this satisfies the "update agent-map.md for every heading you add" requirement --
  the only new headings added anywhere in this pass were these three `## Contents`
  sections).

## Findings file updated
`tmp/doc-review-2026-07-31.md` -- each finding's heading annotated with its outcome
(FIXED / FIXED (scoped) / IGNORED), Finding 4's body got an explicit "Disposition (Arnon,
2026-08-01): IGNORED" line, and the "Resolutions" table plus a new detailed per-finding
"What was done" section were added, following the convention established in
`tmp/doc-review-2026-07-29.md`. Note: `tmp/` is gitignored in this repo, so this file will
not show in `git status` -- confirmed via `git ls-files`.

## Verification
- `uv run python tools/check_doc_links.py` -> "All internal documentation links resolve."
  (exit 0)
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python
  -m unittest discover -s test -t .` -> `Ran 2039 tests in 1.152s` / `OK`. (Full suite,
  isolated HOME -- ran after all doc edits.)
- No `ruff format`/`ruff check` run -- no Python files edited, per the task's own
  instruction.

## Reserved-files check
Confirmed via `git diff --stat` that `toolguard/log_writer.py`, `toolguard/hook.py`,
`test/unit/test_log_writer.py`, `test/unit/test_hook.py` are modified in the working tree
(by the concurrent agent) but none of my `Edit`/`Write` tool calls this session referenced
any of the four reserved paths. My changes are confined to: `AGENTS.md`, `llms.txt`,
`docs/agent-guides.md`, `docs/install.md`, `docs/takeover-mode.md`, `docs/auto-mode.md`,
`docs/security.md`, `docs/architecture.md`, `docs/permission-patterns.md`,
`docs/agent-map.md`, `technical-notes.md`, plus the findings file under `tmp/`.

## Judged out of scope (not done, with reasoning)
- `docs/agent-guides.md:186` and `:255`'s own `[hard_deny]`-related phrasing -- these are
  already correctly qualified ("carve-out, not a forced allow" / advises changing the rule
  itself) and were not among Finding 3's two named locations (`AGENTS.md:55`,
  `docs/security.md:59`), so left untouched per the "fix minimally, only where named"
  instruction.
- `docs/install.md`'s three passing `no_match_fallback` mentions (CLAUDE_SETTINGS_PATH
  footgun example, uninstall-readiness rules, wrap-up summary) -- judged non-substantive
  and non-misleading without an `undecidable_fallback` mention, so left as-is; only the
  Phase 2 decision block got the addition.
- No new Q&A entries added to `docs/agent-map.md` -- it already had a correct, current Q&A
  entry covering both fallback settings and `additionalContext`; only its master TOC needed
  updating for the new `## Contents` headings.

## Self-review
Read back every edited section after writing it; verified anchors against the real
`## Contents`/heading text before adding links; verified the sandbox CLI flag list and the
`undecidable_fallback` behavioural claims directly against `toolguard/testing/sandbox.py`
and `toolguard/config.py`/`toolguard/compound.py` source (not restated from the task
prompt). Link checker and full test suite both pass.
