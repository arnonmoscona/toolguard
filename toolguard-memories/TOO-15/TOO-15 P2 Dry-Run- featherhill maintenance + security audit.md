---
title: 'TOO-15 P2 Dry-Run: featherhill maintenance + security audit'
type: report
permalink: toolguard/too-15/too-15-p2-dry-run-featherhill-maintenance-security-audit
tags:
- TOO-15
- dry-run
- security-audit
- maintenance
---

# TOO-15 P2 Dry-Run: featherhill maintenance + security audit

Read-only test-case run of the toolguard-maintenance and toolguard-security-audit
skills against a real external project, exercising the **working branch** (not the
installed release). Date: 2026-07-03. **No config was written** and none will be
until TOO-15 is complete -- the current project state is a fixed test case.

Target: `~/projects/flowers/featherhill` (governs Bash + Read/Write/Edit + a couple
of MCP exec tools; takeover ACTIVE, fail-closed `no_match_fallback=deny`, native `*`
allow neutralized by takeover).

## Commands used (all read-only)

```bash
# Stage 1 maintenance report
uv run python -m toolguard.tools.maintenance --dir ~/projects/flowers/featherhill --format json
# Dry-run preview -> edit_proposals (writes nothing; files_written=[])
uv run python -m toolguard.tools.maintenance --dir ~/projects/flowers/featherhill --apply --format json
# As-if-enacted security audit of the proposed edits (+ full context for AI pass)
uv run python -m toolguard.tools.security_audit --dir ~/projects/flowers/featherhill \
    --edits fh_edits.json --format json --with-context
```

## Maintenance findings (24, all Bash, project layer toolguard_hook.toml)

**Redundancies -- exact dups (3):** `uv run pytest:*` = `uv run pytest :*`;
`uv run uvicorn flowers.app.main:app:*` = `... :*`; `~/bin/open_note_by_title.sh:*`
= `... :*`. (Space-before-`:*` variants normalise identical. Reported, not
auto-applied.)

**Consolidations -- appliable, replay-verified (8 proposals, 7 applied / 1 skipped):**
- literal-alternation: 6 git rules -> `[regex]^git (diff|flake8|isort|log|ls-files|status)` (26 probes unchanged)
- literal-alternation: 4 mkdir rules -> `[regex]^mkdir -p (/tmp/|/tmp/claude-code|flowers/|~/projects/flowers/)` (18 unchanged)
- literal-alternation: 2 alembic -> `[regex]^uv run alembic (current|heads)` (10 unchanged)
- static-subsumption: `mkdir -p /tmp/claude-code:*` <= `mkdir -p /tmp/:*` (SKIPPED -- already claimed by the mkdir alternation)
- static-subsumption: `uv run python ./bin/recall_main_agent_conversation.py` <= `uv run python:*`
- static-subsumption: `uv run python .bin/local_tools_mcp.py` <= `uv run python:*`
- static-subsumption: `uv run python bin/start_test_server.py` <= `uv run python:*`
- static-subsumption: `uv run ruff format:*` <= `uv run ruff:*`

**Broadenings -- NOT auto-applied, human judgement (5). Two are risky:**
- `cat :*` (from `cat ./:*` + `cat /tmp/:*`) -- overlaps the `.env`/`.ssh` deny guards; do NOT take.
- `uv run :*` (from pytest/python/ruff) -- effectively arbitrary exec via uv run; overlaps `ask uv run alembic:*`. Do NOT take.
- `git :*`, `mkdir -p :*`, `uv run alembic :*` -- lower-risk widenings.

**Clarity interactions -- same file (8):** `ask lsof:*` vs `allow lsof -i:*`;
`ask uv run alembic:*` vs 5 more-specific alembic allows; `deny head .env:*`
shadows `allow head:*`; `deny tail .env:*` shadows `allow tail:*`.

## Security audit of the PROPOSED edits (as-if-enacted)

Deterministic (takeover ACTIVE): **CRITICAL 1, MEDIUM 4, LOW 6.**
- CRITICAL `arbitrary-exec-allow`: `uv run python:*` (arbitrary code execution). PRE-EXISTING; not caused by the edits.
- MEDIUM `unanchored-regex-allow` x4: `[regex]\bfind\b(?!...)` (missing write trapdoors); `rm .../memory/.*` (Bash); `.../memory/.*` (Edit, Write) -- all `re.search`, unanchored.
- LOW: ask-overlaps-allow x4 (lsof, alembic x3), deny-shadows-allow x2 (head/tail .env).

**delta.introduced = 0** (the consolidations create NO new finding) and
**delta.resolved = 5** (3 CRITICAL `arbitrary-exec-allow` + 2 LOW ask-overlaps).
Caveat: the 3 resolved CRITICALs are largely COSMETIC -- they were redundant
`uv run python <script>` allows already subsumed by the broad `uv run python:*`,
which remains as the 1 surviving CRITICAL. Net posture: security-neutral, count
reduced. **Verdict: the consolidations are safe to enact.**

## AI (Pass 2) leads on the config itself (pre-existing, not edit-caused)

1. HIGH conf / CRITICAL -- `uv run python:*` is the master escape hatch: `uv run python -c "..."` bypasses EVERY Bash/Read/Write/Edit deny (.env, .ssh, rm -rf). On a solo dev box this may be intentional convenience -- accept via `#NOSECURITY` or narrow to specific scripts. Same class: `uv run pytest:*` (tests run arbitrary python).
2. MEDIUM -- secret-read denies are PREFIX-anchored, not token-anchored: `deny cat .env:*` / `head .env:*` catch only CWD-relative `.env`; `head /abs/path/.env`, `grep -r X ~/.ssh/`, `tail ../.env`, and readers `ag/ack/sort/wc` slip through. Fix (skill few-shot #2): replace with `Bash([regex]\.env\b)` and `Bash([regex]/\.ssh/)` covering all readers.
3. MEDIUM -- unanchored memory regexes allow path traversal past `.../memory/` via the trailing `.*`. Anchor with `^...$`.

## Process notes / possible feature gap

- **auto-mode classifier blocked the dry-run.** `--apply` WITHOUT `--write` writes
  nothing (files_written=[]) but the classifier read the `--apply` verb as a config
  write and hard-denied it. Output redirect location was irrelevant. UX/naming smell:
  consider a `--preview`/`--dry-run` alias or an explicit `--edits-out FILE` export so
  the read-only intent is legible to the classifier AND humans. Revisit as a small
  follow-up; do not change behaviour now.
- Confirmed the dry-run pipeline (report -> --apply preview -> --edits audit) works
  end-to-end against an external project via `--dir` on the working branch.

Relates to [[too-15-p2-8-cross-project-security-audit-safety-floor-agreed-design]].
