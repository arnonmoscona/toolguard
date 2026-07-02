---
title: TOO-15 P2 Open TODOs
type: note
permalink: toolguard/too-15/too-15-p2-open-todos
tags:
- task-memory
- TOO-15
- P2
- open-todos
---

# TOO-15 P2 Open TODOs

Detailed, self-contained list of **all remaining P2 work** as of 2026-07-01, after
the maintenance skill + the S1-S4 maintenance<->audit edit-proposal loop landed
(uncommitted; commit message prepared). Full design detail lives in
`TOO-15 Toolguard Skills and Config Tooling - Requirements and Plan.md`. Session
progress/resume anchor is the auto-memory `project_too15_p2_wrapup.md`.

## Already DONE (do NOT redo)
2a corpus harvest (`tools/corpus.py`), 2b JSON output, 2c apply CLI
(`toolguard-maintain --apply[/--write]`), Step-1 maintenance SKILL.md, **2e**
structured + audience-aware audit remediations (done as S2: `Remediation(text,
proposal)`, json = agent sidecar), and the full S1-S4 loop:
- S1 `tools/edit_proposal.py` (RuleEdit/EditProposal/apply_edits) +
  `config_access.with_layer_rules_replaced` (section-generic).
- S2 structured `RankedFinding.remediation` + danger `remediation_kind`.
- S3 `toolguard-audit --edits` as-if-enacted review + `context.proposed_edits.delta`.
- S4 `consolidation_to_edit_proposal` + `--apply --format json` emits
  `edit_proposals`; maintenance skill mandates audit review before `--write`.

## OPEN -- roughly in priority order

### 0. Phase-end gate for the S1-S4 loop (do BEFORE closing the commit)
- `/code-review changed TOO-15` over the changed set (danger.py, security_audit.py,
  edit_proposal.py NEW, config_access.py, maintenance.py, corpus.py NEW, both
  SKILL.md, tests).
- Coverage check on the new code (see #5). See [[feedback-phase-end-gate]].

### 1. 2d -- `#NOSECURITY` tag  (acknowledge-not-hide)
- **PREREQ:** expose per-rule inline comments in `config_access.audit_context`
  (the audit currently cannot see the comment attached to a rule).
- Behavior: Pass-1 STILL reports a `#NOSECURITY`-tagged finding, but marks it
  `acknowledged (#NOSECURITY: <reason>)` and de-prioritizes it (never silently
  hidden).
- A **scoped reason BLOCKS migration/edit** of that rule: the migration/apply flow
  must refuse to move or rewrite a rule the user explicitly annotated
  intentionally-insecure-with-reason.

### 2. 2f -- Self-permissioning  (plan "Self-permissioning 2026-06-26")
- Under takeover, running `toolguard-maintain` / `toolguard-audit` is itself a
  governed `Bash` command, and `--apply --write` edits config files (Write/Edit).
  These get DENIED unless toolguard's own tools are allow-listed.
- The setup/maintenance skills must OFFER (with user consent, at chosen scope) to
  add allow rules for the toolguard console scripts + the config-file edits.

### 3. 2g -- Wire `migration_preflight` into the hierarchy-migration flow
- `migration_preflight` is currently only consulted by the maintenance `--apply`
  gate (in-file consolidations). The actual hierarchy MIGRATION flow (promote a
  rule up a layer via `hierarchy.migrate_config`/`evaluate_migration`) does NOT
  yet consult it.
- Make the migration flow refuse on blockers (dirty tree / unresolved root) or ask,
  same as apply.

### 4. P2-F continuation -- clarity analyzer (plan #3)
- **More detectors:** same-command-multi-section (a command family with rules in
  several sections that interact); cross-layer-dependent (effective verdict depends
  on a rule in another layer).
- **Clearer-EQUIVALENT rewrite mode:** when a provably-equivalent clearer config
  exists (replay-verified same result), offer it as a rewrite; when none provably
  exists, ANNOTATE instead (never guess).
- **`# toolguard:`-marked GENERATED COMMENTS:** stable marker so re-apply REPLACES
  the generated comment (not accretes); NEVER clobbers human comments; rides the
  comment-preserving apply writer.

### 5. Coverage top-ups (plan #4 + new S1-S4 code)
- Original gaps: `project_root` non-DEFAULT / dedup / len<2 branches; `working_tree`
  edges; `consolidate` static-subsumption; `transcript_harvest._extract_text`.
- New code to verify: `edit_proposal` (stale-edit skip), `corpus` (missing dirs),
  danger `remediation_kind` paths, security_audit `_danger_proposal` edge branches,
  `_finding_delta`, `--edits` malformed, maintenance apply `edit_proposals`/corpus.
- Tool: stdlib `tools/coverage_stdlib.py`; grep `'>>>>>>'` in `cover/` for gaps.

### 6. Pre-push gate (plan #4)
- Run `pyscn analyze toolguard --html` -> `.pyscn/`; triage (not every finding is
  required); ensure `.pyscn/` is gitignored.
- Bump version in `pyproject.toml`.
- Release notes.
- Glob-defect user docs (document the glob defect referenced in the plan).

### 7. TOO-15 completion gate  (see [[project-too15-completion-gate]])
- Remove temp skill symlinks.
- Install skills via the setup/maintenance facilities: must DETECT a partial global
  install (older `uv tool`) -> remind `uv tool upgrade toolguard`; install MISSING
  skills at user-chosen scope (local vs user).

## ADDITIONAL P2 completion requirements (Arnon 2026-07-01)

These are REQUIRED before declaring P2 finished (not optional). Refinements agreed
with Claude 2026-07-01 are folded in below.

### 8. Functional: cross-project security audit (user's local projects together)
- **What:** the security audit must be able to analyze the toolguard + Claude
  permissions across ALL of the current USER's relevant local projects together
  (this user's projects only -- NOT other machine users).
- **Why:** auditing from the current project UP the hierarchy gives a complete
  picture for THAT project, but refactoring rules at higher levels (e.g. the user
  level) can affect OTHER projects that were never in scope. Concretely, this is a
  HOLE in the S3 `--edits` as-if-enacted review: it only evaluates the current
  project's hierarchy, so a user-level refactor can show "0 introduced" here while
  silently breaking project B. That is a misleading safety signal, not just a
  missing feature.
- **REFINEMENT 1 -- gate on the layer being touched (not every run):** only edits
  whose provenance is a SHARED layer (user `~/.claude`, enterprise) can affect other
  projects; project-level edits never can. Detect "this edit touches a shared layer"
  and only THEN trigger the cross-project prompt. Most refactors are project-local
  and skip the expensive sweep entirely -- this largely defuses the cost concern.
- **REFINEMENT 2 -- safety floor MUST ship in P2 (higher status than the rest of
  #8):** whatever we decide about the full sweep, the flow must AT MINIMUM warn
  "these edits change a user-level rule; N other projects inherit it" before
  `--write`. That warning is nearly free and closes the dangerous silent gap. The
  full multi-project as-if-enacted analysis MAY be deferred (even to TOO-16); the
  detection + warning must NOT be.
- **How to find relevant projects (hard evidence) -- REFINEMENT 3, FILTER don't just
  list:**
  - `~/.claude/projects/` -- each entry has had Claude activity (encoded absolute
    path, `/` -> `-`). This is a SUPERSET: most entries have only transcript/chat
    history and NO permission config, and some point to deleted/moved dirs.
  - `~/.claude.json` -- its `projects` map (keyed by absolute path) is the more
    precise "has explicit Claude config" source.
  - Candidate list must be FILTERED to projects that (a) still exist and (b) actually
    have a `.claude/settings*.json` or `.claude/toolguard_hook.toml`. Reuse point:
    `transcript_harvest.transcript_dir_for_project` already does the `/`<->`-`
    encoding (decode it to recover project paths).
- **Design dependency:** the audit CLI is single-`--dir`; cross-project needs a
  multi-root mode. Flag so it is not a surprise.
- **UX (expensive analysis -> ask first):** when triggered, prompt whether to run,
  LISTING the (filtered) candidate projects. Let the user (a) select specific ones,
  (b) approve all, or (c) manually ADD projects not on the list (e.g. cloned repos
  with Claude configs they have not started working in).

### 9. Testing: real-world dry-runs on intentionally-dirty projects
Before finishing, run READ-ONLY maintenance on both `toolguard` and
`flowers/featherhill` (both left intentionally "dirty" -- real security risks AND
non-trivial maintenance opportunities), across the matrix:
- with and without security audits,
- in different scopes,
- with and without AI-driven analysis.
Purpose: assess how well the skills actually perform on real situations (unit tests
cannot judge skill JUDGMENT or UX).
- **REFINEMENT -- capture outputs as evidence/fixtures** (the reports + deltas), so
  this is not a one-time vibe-check: it documents what the tools caught and makes
  regressions catchable later.
- **Sequence LAST** (depends on #8 + AI analysis being wired); prioritize the matrix
  cells most likely to break rather than running the full cross-product mechanically.

### 10. Documentation update (before finish)
- Maintenance skill: capabilities + usage, and its interaction with the security
  audit skill (the edit-proposal review loop).
- The toolguard configuration options ADDED during P2 and their defaults.
- `technical-notes.md`: update based on the key decisions made during P2
  implementation (opt-in corpus, `--format json` = agent sidecar / no audience flag,
  shared EditProposal model, as-if-enacted `--edits` review, apply gated by
  migration_preflight).
- **REFINEMENT -- write the tech-notes decision log NOW, while fresh** (rationale
  decays fast); user-facing capability docs can wait for the end.
  STATUS 2026-07-01: tech-notes decision log being written now by Claude.


### 8. Functional: cross-project security audit (user's local projects together)
- **What:** the security audit must be able to analyze the toolguard + Claude
  permissions across ALL of the current USER's relevant local projects together
  (this user's projects only -- NOT other machine users).
- **Why:** auditing from the current project UP the hierarchy gives a complete
  picture for THAT project, but refactoring rules at higher levels (e.g. the user
  level) can affect OTHER projects that were never in scope for the refactoring.
  A cross-project pass catches that blast radius.
- **How to find relevant projects (hard evidence):**
  - `~/.claude/projects/` -- each entry identifies a project that has had Claude
    activity in it (encoded absolute path, `/` -> `-`).
  - `~/.claude.json` -- projects Claude has explicit configuration for.
- **UX (expensive analysis -> ask first):** prompt the user whether to run it,
  LISTING all projects that would be analyzed. Let the user (a) select specific
  projects from the list, (b) approve all, or (c) manually ADD projects not on the
  list (e.g. cloned repos with Claude configs they have not started working in yet).

### 9. Testing: real-world dry-runs on intentionally-dirty projects
Before finishing, run READ-ONLY maintenance on both `toolguard` and
`flowers/featherhill` (both left intentionally "dirty" -- real security risks AND
non-trivial maintenance opportunities), across the matrix:
- with and without security audits,
- in different scopes,
- with and without AI-driven analysis.
Purpose: assess how well the skills actually perform on real situations.

### 10. Documentation update (before finish)
- Maintenance skill: capabilities + usage, and its interaction with the security
  audit skill (the edit-proposal review loop).
- The toolguard configuration options ADDED during P2 and their defaults.
- `technical-notes.md`: update based on the key decisions made during P2
  implementation (e.g. opt-in corpus, `--format json` = agent sidecar / no audience
  flag, shared EditProposal model, as-if-enacted `--edits` review, apply gated by
  migration_preflight).

## Minor / tech-debt noted (optional)
- **3 provenance serializers** now exist: `edit_proposal._provenance_to_dict`
  (round-trippable, no describe), `maintenance._provenance_to_dict` (with describe),
  `hierarchy.migration_effect_to_dict` (inline). Justified by different contracts;
  candidate for future consolidation.
- **Optional:** decision-replay neutrality quantification inside `toolguard-audit
  --edits` (currently the delta is finding-based; command-replay neutrality is on
  the maintenance side, which replay-verifies strict consolidations). Only add if
  the audit itself should quantify command-level changes (would need a corpus in
  the audit).
- **Distribution (TOO-16, separate ticket):** global `uv tool` install pins a
  commit; remind `uv tool upgrade` after landing fixes. See [[project-distribution-model]].

## Related memories
[[project-too15-p2-wrapup]] (session resume anchor), [[project-too15-completion-gate]],
[[feedback-phase-end-gate]], [[project-headroom-watch]],
[[project-experimental-tooling-local-only]], [[project-distribution-model]].


## 2026-07-02: #4 CLOSED via annotation; equivalent-rewrite PUNTED to new ticket

Decision (Arnon): #4 (rule-interaction clarity remediation) ships with #4(c) generated
`# toolguard:` annotations as the remediation. #4(b) equivalent-rewrite mode is PUNTED
to a NEW TICKET (create in YouTrack), not built in TOO-15.

Rationale (soundness): `tools/replay.replay` only proves equivalence OVER THE RECORDED
CORPUS, not universally -- two patterns can agree on all logged commands then diverge on
the first unseen one. Offering an auto-rewrite labeled "equivalent" on that basis is a
trap for a security tool. The truly-sound-and-clearer rewrite set is nearly empty
(ask-overlaps-allow / cross-layer-dependent are confusing precisely because of the
more-specific-wins interaction; the one clean case -- an allow fully shadowed by a
same-file deny -> drop dead allow -- is essentially redundancy removal we already have).
#4(c) annotation already delivers the clarity value honestly (explains real resolution,
changes no behavior).

NEW TICKET content to file: "Equivalent-rewrite mode for confusing rule interactions."
- Generate a clearer config for a confusing interaction and offer it ONLY when provably
  decision-equivalent.
- CAVEAT to solve: replay-equivalence is corpus-scoped, not a universal proof. Either
  (a) restrict to universally-provable structural no-ops (dead-allow removal, redundant-
  rule removal) with replay as a secondary guard, or (b) if using corpus replay, label
  LOUDLY as "verified over recorded history only, not a universal equivalence proof."
- Revisit once corpus/coverage matures. Primitive already exists: `tools/replay.replay`
  (ReplayDiff: broadened/tightened/unchanged) + `tools/decision.decide`.
