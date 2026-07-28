Run a comprehensive review of toolguard's own documentation (README.md, AGENTS.md, llms.txt,
everything under docs/, technical-notes.md, and the skills' SKILL.md/passes files). This
codifies the method used for the doc audits recorded in
tmp/too15-doc-audit-findings.md and tmp/too15-doc-audience-audit.md -- read those first if
they still exist, both for the method and to avoid re-flagging something already discussed
and deliberately deferred/ignored there.

Scope: unless the user names a git ref/tag to diff against (an "since we last did a big pass"
style request), review the CURRENT state of the docs, not a diff -- this command is meant to
be run periodically (e.g. before a push), not just once after a large ticket.

Do THREE passes. Do not skip any of them; they catch different things.

## Pass 1 -- fact-accuracy audit

For every doc, find every claim that names a specific config key, CLI flag/subcommand, file
path, default value, or behavior, and VERIFY it against the actual source code -- grep/read
the real implementation, don't just check that two docs agree with each other (two docs can
agree and both be wrong; this has happened before in this project). Specifically hunt for:

- A config key or CLI flag documented that doesn't actually exist in code (a fabricated or
  since-removed capability).
- A config key or CLI flag that exists in code but isn't documented anywhere.
- A "complete"/"full reference" section (e.g. configuration.md's Configuration reference)
  that is stale relative to the actual schema.
- Stale invocation forms -- `uv run python -m toolguard.scripts.X` or similar dev-only forms
  shown as the default where an installed console script now exists (this exact bug has
  recurred multiple times across different files; grep for `uv run python -m
  toolguard.scripts.migrate_permissions` and similar patterns specifically).
- A setting documented in one place with a nested/qualified form (e.g. inside a `[section]`)
  when the code treats it as a different location (top-level vs nested), or vice versa.
- Claims about a safety/protection mechanism ("can never be deleted", "always enforced") that
  don't hold in every case the doc's own context implies -- verify the mechanism's actual
  scope, don't take the doc's own confidence at face value.

Verify claims independently -- read the actual source (`toolguard/`, `toolguard/tools/`,
`toolguard/scripts/`), not just other docs, and where a claim depends on Claude Code's own
external behavior (not toolguard's code), say so explicitly rather than asserting it as fact.

## Pass 2 -- audience and structure audit

Read every doc in full against three audiences:

- **Impatient humans**: will read a couple of README paragraphs and maybe the quickstart, if
  short and clearly signposted. Nothing else, ever.
- **Agents**: the primary readership of most of this documentation (AGENTS.md, llms.txt,
  agent-guides.md, docs/agent-map.md, install.md, uninstall.md are explicitly agent-facing).
- **Diligent humans**: will read a whole doc, or hunt down one specific section, and need
  navigation to work either way.

Check specifically:

- Is the impatient-human path clearly and prominently signposted from README (not buried)?
- Do the docs billed as "usually enough on its own" for agents (agent-guides.md, AGENTS.md)
  actually cover the capabilities that exist, or silently omit whole areas (a silent gap
  reads as "not needed," which is worse than an explicit "see X for this")?
- Do large files (roughly 400+ lines, or 15+ headings) have adequate internal navigation --
  a table of contents, or at minimum well-anchored, jump-to-friendly headers?
- Does every file state its audience/purpose in its opening paragraph? (Every doc in this
  project is expected to, following technical-notes.md's fix for this.)

## Pass 3 -- agent-map.md and cross-reference link freshness

A dedicated pass, not a bullet inside Pass 2 -- `docs/agent-map.md` is the single biggest
drift risk in the whole documentation set (it summarizes every other doc's headings plus a
curated Q&A list, and nothing else keeps it in sync automatically), and stale internal links
are a mechanical, easy-to-miss bug class distinct from the judgment-heavy work of Pass 1/2.

1. **Regenerate `docs/agent-map.md`'s master table of contents.** Walk every doc's
   `##`/`###` headers (skip anything inside code fences), compute GitHub's anchor-slug
   algorithm, and disambiguate duplicate slugs the way GitHub does (`-1`, `-2`, ...). Diff the
   result against what the file currently has. Any file added, removed, renamed, or re-headed
   since the map was last updated will show up here as a diff.
2. **Spot-check the "Questions and pointers" section.** For each entry, confirm the linked
   anchor still exists in the target file -- headings get renamed or reordered without anyone
   remembering to update every pointer to them. This section has no regeneration path, so it
   is the most likely piece to silently drift.
3. **Sweep for broken or stale internal links project-wide**, not just in agent-map.md: every
   `[text](file#anchor)` reference across README.md, AGENTS.md, llms.txt, and everything under
   docs/ should resolve to a heading that actually exists in the target file. Pay particular
   attention to anchors for sections that get renamed or moved between files -- this has
   broken before (relocating a section, or reordering/renaming headings, silently orphaned a
   link elsewhere that still pointed at the old anchor).
4. **Confirm `llms.txt` and `AGENTS.md` both list every doc under `docs/`.** A new doc file
   added without updating either is the same class of gap as the missing `auto-mode.md` entry
   found and fixed this session -- check for it explicitly rather than assuming it can't
   recur.

## Output

Write findings to a new markdown file in tmp/ (name it for this run, e.g.
tmp/doc-review-<date>.md), each with a distinct number, verified evidence (not just
assertion), and enough context to discuss without re-deriving it. Follow the exact format of
the two prior audit files in tmp/ if they're still present. Open the file in the IDE. Do NOT
make any changes to the documentation itself in this pass -- this command only produces
findings for discussion, exactly like the two prior audits. Wait for explicit per-finding
direction (fix / defer / ignore) before editing anything, and keep the findings file updated
with the outcome of each as you go, the same way the two prior audits recorded resolutions
inline.
