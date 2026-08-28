---
title: TOO-73 user CLAUDE.md shortening
type: note
permalink: toolguard/too-73/too-73-user-claude.md-shortening
tags:
- task-memory
- TOO-73
---

# TOO-73 — draft changes to the user-level `CLAUDE.md`

**Branch**: `too-73` in `~/projects/claude_tooling`. toolguard is on `master`, released 0.6.1, clean.

**Shape**: plan → review → draft into `claude_tooling/user-claude-md-changes/` → review → migrate. **Nothing touches `~/.claude` until Arnon migrates.** `claude_tooling` is private, so machine-specific config is fine there.

**State 2026-08-28: all 13 punch-list items done. Awaiting Arnon's review of the draft, then a discussion of whether to do more about U7.**

- Plan: `claude_tooling/tmp/TOO-73-plan.md`
- Punch list and outcomes: `claude_tooling/user-claude-md-changes/PUNCH-LIST.md`

## What shipped as drafts

`claude/CLAUDE.md` (U1–U6, U8, U9), `claude/rules/comments.md` (extracted, with `paths:` frontmatter so it auto-loads), `rules-fragment.toml` (validated), `tools/disclosure_compliance.py`.

## Findings worth keeping

- **The file barely shrank: 318 → 306 context-bearing lines (−12), against a plan predicting ~112 out.** Moves removed 78; approved additions (U4's decision procedure, U9's marker semantics, U1–U3, U5b) put back 66. My headline claim was wrong by an order of magnitude and the correctness pass caught it.
- **Disclosure-compliance baseline: 10.9% over 238 trigger-carrying commands** (16,733 commands, 13 files). **Control flow is 160 of 238 — two thirds — and is structurally invisible to a permission rule**, because toolguard matches extracted leaves and a `for` loop is judged as its body. So the deployed rule reaches at most a third of the gap; the offline report covers the rest.
- **A rule file only auto-loads if it declares `paths:` frontmatter.** `rules/comments.md` lacked it and would have silently failed to load, collapsing the "rule file beats skill" argument. Found by checking how `rules/python.md` loads rather than assuming.
- **`toolguard/CLAUDE.md:200-204` still claims the disclosure markers are inert.** False since 2026-08-28. Different repo, out of scope here — flagged.
- **Marker mechanics, all measured**: the marker must lead the leaf it attests (`cd x && TG_...` attests nothing); a pipeline needs every leaf permitted, and 60% of attested commands are pipelines; foreign code (heredoc, `-c`, `awk`) takes an undecidable floor that no attestation lifts, answering only to `undecidable_fallback`.

## Clarifications from discussion

- **U7's hook was rejected** as heavy-handed and token-expensive. Replaced by an `allow` + `additionalContext` rule needing no new toolguard feature. Arnon's correction: the `allow`-not-`ask` argument holds only in auto-mode; **after TOO-28 sub-part 3 (per-rule auto-mode override) it becomes `ask` with an override**, and the regex and context text carry over unchanged.
- Arnon's `[multiline]length>8` idea was measured against the corpus and rejected: **204 of 235 trigger-carrying commands are a single line**, so a length threshold targets the wrong axis.
- Marker spelling variation is **compliance variation, not a defect** — Arnon: *"as long as you comply and the rule works, everything is great."*
- **D3** `git commit --amend` stays denied. **D4** *Tickets*, *Prose is output*, *Task memory* held back so the effect stays attributable. **D5** `tmp/` now gitignored.
- **Open**: U9 arguably violates U4's own rule — its bullets are mechanics, and the whole *Disclose* section is ~60 lines of tier-4 procedure. Largest remaining reduction available; deliberately not taken.

Relates to [[TOO-45 retrospective]].
