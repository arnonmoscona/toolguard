---
title: TOO-30 documentation review - findings and fixes
type: note
permalink: toolguard/too-30/too-30-documentation-review-findings-and-fixes
tags:
- project
- TOO-30
- documentation
- review
---

## Documentation review (2026-07-23)

Ran `/documentation-review` (delegated the full 3-pass sweep to a general-purpose subagent
since it's a large, self-contained, already-fully-specified task -- doing it inline would
have burned a lot of main-context for no added judgment). Findings written to
`tmp/doc-review-2026-07-23.md`, spot-checked 2 of 5 independently (both confirmed accurate)
before trusting the rest.

5 findings, all MEDIUM/LOW, no criticals:
1. MEDIUM -- `configuration.md`'s env-var table omitted `XDG_CONFIG_HOME`.
2. MEDIUM -- 8 broken self-referencing anchor links (4 in `agent-map.md`, 4 in
   `technical-notes.md`) from a systematic underscore-stripping bug in whatever
   slug-generation script was used for a past TOC regeneration (script itself was never
   committed to the repo -- nothing persistent to fix there, just the resulting bad anchors).
3. MEDIUM -- TOO-30's rules directory had no pointer from `agent-guides.md`'s "share rules
   across many projects" recipe or `agent-map.md`'s Q&A list.
4. LOW -- `agent-map.md`'s own opening line linked to a nonexistent `../quickstart.md`.
5. LOW -- `architecture.md`'s new TOO-30 log example showed a `~`-abbreviated path that
   `describe_brief()` never actually outputs (matches a pre-existing, previously-reviewed
   stylization convention though).

Arnon triaged via Telegram: "Fix all 5 of them." All fixed same session:
- Added `XDG_CONFIG_HOME` row to the env-var table.
- Corrected all 8 broken anchors by hand (verified against real GitHub slugs).
- Added a rules-directory pointer to `agent-guides.md`'s recipe and a new Q&A entry in
  `agent-map.md`.
- Fixed the `../quickstart.md` -> `quickstart.md` link.
- Kept the existing abbreviated-path convention in `architecture.md` (consistency with its
  sibling example) but added one clarifying sentence that real provenance is always the full
  absolute path.

`tmp/doc-review-2026-07-23.md` updated in place with a "Fix applied" note under each finding
and the status line marked all-FIXED, matching the established convention from the two prior
TOO-15 doc audits. Full suite re-verified green (1513 tests) and `ruff check` clean after all
doc edits (docs-only changes, but verified anyway since the working tree also has the TOO-30
code changes from the same session).

## Note on process

Both `/code-review` runs this session hit a real limitation: `mcp__basic-memory__write_note`
was unavailable in that subagent context, so neither could persist its own report as the
skill's own instructions require. Findings were returned directly instead; the report was
written to `latest-code-review-report.md` by the orchestrating (main) session itself after
independently verifying a discrepancy between the two runs (see
[[TOO-30 XDG rules directory - Requirements and Plan]] for the crash-bug story). Worth
knowing this limitation exists if `/code-review` is used again before it's addressed.
