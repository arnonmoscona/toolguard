---
title: Conversational multi-pass maintenance — implementation plan
type: plan
permalink: toolguard/too-15/conversational-multi-pass-maintenance-implementation-plan
tags:
- TOO-15
- maintenance
- plan
- skill
---

# Conversational multi-pass maintenance -- implementation plan

Executes [[conversational-multi-pass-maintenance-redesign-design]]. Folded into TOO-15
(decided 2026-07-04). Phased, not big-bang. Bulk is skill/prompt authoring; minimal new
Python. Audit report is "good enough" (Arnon 2026-07-04) -- do NOT refine it now.

## Guiding constraints (from design)

- No auto-apply EVER. Replay-verification = evidence, not consent. Bulk = explicit opt-in.
- Layer-targeting BEFORE consolidation (fixes mkdir welding).
- AI-level family consolidation, NOT deterministic. Tool's deterministic consolidation
  demoted to a mere candidate-finder the skill re-evaluates.
- Heterogeneity -> discussion trigger (agent guidance + cues, not a detector).
- Cut/paste TOML: authored by AI, CERTIFIED by tool (parse + audit + corpus replay of the
  assembled file before the user pastes).
- Report: group by command family, ALL sections, show UNCHANGED rules, per-family
  narrative; separate cut/paste section.

## Architecture

- `SKILL.md` = orchestrator (overview + pass sequencing + hard constraints).
- `passes/*.md` = per-pass instructions, loaded as each pass runs (progressive disclosure).
- Inter-pass state artifact = a "recommendation set" JSON the passes read + annotate
  (schema in `passes/recommendation-set-schema.md`). Lives in the session scratchpad, not
  the repo.
- Tool (`toolguard/tools/maintenance.py`) changes kept minimal (see phases).

## Phase A -- honest consent + reshaped report (the shippable core)

Delivers the "good enough" report + honest consent with (near) zero new Python. Deferring
promotion keeps all edits project-level so certification-by-staging is simple.

- A1. Soften consent wording: SKILL.md apply framing + maintenance.py `--apply` help so
  "strict/replay-verified" is never labelled auto-safe; bulk = explicit opt-in. (tiny)
- A2. Author `passes/recommendation-set-schema.md` (inter-pass contract). DONE-scaffold.
- A3. Orchestrator SKILL.md rewrite + passes: gather (findings JSON + audit --with-context
  + --apply edit_proposals) -> layer-targeting (project-only for now) -> family grouping ->
  understanding view + cut/paste TOML. Start with fewer, larger passes; split toward the
  full 8 as needed.
- A4. Certification by staging: copy project config to a temp dir, overwrite the toml with
  the AI-assembled candidate, run `toolguard-audit --dir <temp>` (parse-check + as-if-enacted
  audit). Corpus replay deferred to Phase B pass 7. Uses EXISTING tools; no new Python.
- Acceptance: re-run the featherhill dry-run; report shows alembic/git/mkdir families
  grouped with unchanged rules, marked no-change|edit|consolidate|remove, per-family
  narrative, plus a separate paste-ready TOML block; NOTHING auto-applied. Arnon reviews.
  Python bits (A1) get unittest coverage.

## Phase B -- discussion loop, heterogeneity, trust levels, corpus gate

- B1. Heterogeneity-cue guidance pass (alembic `-x db=test` style outliers -> flag, ask;
  ceiling: do not self-research the tool).
- B2. Case-by-case approval loop in the skill (present family -> user accepts/rejects/modifies
  -> record in recommendation set); bounded audit<->revise loop (5<->6).
- B3. Corpus validation pass 7 (replay the assembled candidate; necessary-not-sufficient;
  surface, don't gate on it alone).
- B4. First-run-vs-periodic + a dial-able trust level (periodic: surface only NEW; may
  pre-authorize no-ops).
- Acceptance: dry-run drives a real per-family conversation; alembic outlier triggers a
  question; periodic re-run is quiet.

## Phase C -- prior-decision ledger + install-time integration

- C1. In-file annotations for rule-attached decisions (extend existing `--annotate`
  `# toolguard:` mechanism; short pointer for long rationales).
- C2. Sidecar meta-decision ledger: level-scoped (project `.claude/` + user `~/.toolguard/`),
  default `~/.toolguard/memories/maintenance-skill/`; skill reads it to avoid re-litigating.
- C3. Setup-skill integration: collect memory-system preference, ledger locations, trust
  default at install (ties to TOO-15 completion gate #7).
- Acceptance: a rejected suggestion is not re-raised on the next run.

## Phase D -- layer-promotion candidates (coordinates TOO-8)

- D1. Skill identifies promotion candidates (project-agnostic tokens), FLAG-ONLY; STOP
  welding cross-level paths (handled by targeting-before-consolidation, so likely no tool
  change -- skill re-derives merges under level constraints).
- D2. Certification must then stage user-level files too (harder) OR restrict promotion
  preview to a described diff without live user-level audit. Decide during D.
- Acceptance: git/user-level candidates surfaced as suggestions with the cross-context
  broadening caveat; user decides.

## Then: TOO-15 close-out (unchanged, now AFTER the redesign)

- #6 pre-push gate (pyscn, coverage, version bump, release notes).
- #7 completion gate (skill install via setup facilities; C3 lands here).

## Sequencing / delegation

Do A -> B -> C -> D. Skill/prompt authoring in the main agent (Arnon reviews live in IDE);
Python slices (A1 wording, any tool support) delegated to feature-coder per standing
directive. Phase-end gate each phase: code-reviewer subagent + coverage check.

## Next phase: agentic toolguard install + project-setup skill (noted 2026-07-05)

- Build a **simple agentic toolguard installation + project-setup skill** that AUTOMATES
  correct project-level AND user-level base setup -- hook registration + base config
  (`[takeover_mode]`, `governed_tools`) -- done correctly, so users do not hand-assemble it.
- Once it exists, the **security-audit and maintenance skills must be aware of it** and
  recommend **follow-up actions** for: (a) missing user-level setup, and (b)
  incomplete / contradictory setups. The detect-and-inform alerts we just added
  (incomplete-user-level-config alert; the promotion "must be a FULL setup" admonition)
  should then hand off to the setup skill as the concrete remediation, instead of only
  telling the user to do it manually.
- This is the concrete home for the "full user-level setup" that the promotion guidance
  references, and it is where the open user-level base-config / takeover-posture question
  gets resolved by making the setup skill produce the correct config.
- Overlaps the existing completion-gate work (#7: skill install via setup facilities);
  fold together.

Relates to [[conversational-multi-pass-maintenance-redesign-design]].
