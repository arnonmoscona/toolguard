---
title: Conversational multi-pass maintenance redesign (design)
type: design
permalink: toolguard/too-15/conversational-multi-pass-maintenance-redesign-design
tags:
- TOO-15
- maintenance
- design
- skill
---

# Conversational multi-pass maintenance redesign (design)

Converged design from the 2026-07-03/04 discussion after the featherhill dry-run
exposed gaps in the maintenance skill's report. NOT yet a ticket -- likely its own
ticket (see Open decisions). Nothing implemented yet.

## Framing

The maintenance skill is judgement-heavy permission-rule refactoring where user
intent cannot be fully inferred. This is the OPPOSITE of the mechanical
`migrate_permissions.py` (which moves rules without changing level/semantics/risk).
The tool/code is only the **mechanical executor of decisions the user already made
in conversation**. The skill (not code) exists precisely because consent here is a
dialogue. The featherhill run proved the point: the "presumably safe" replay-verified
merges (`git diff...` family; the welded mkdir regex) were exactly what the user did
NOT want -- "safe" is a property of user intent the tool can't hold.

## Consent model

- **No change is ever applied automatically, no matter how trivial.** Even strict,
  replay-verified consolidations are per-case user decisions.
- **Replay-verification is evidence, not consent.** Demote the "strict consolidation =
  bulk-appliable/safe" tier: bulk-apply remains available but only as an explicit user
  opt-in ("just do the whole thing"), never a default or a tool-assigned "safe" label.
- SOFTEN the current `--apply` "bulk-apply, obviously safe" wording and the SKILL.md
  apply framing accordingly.
- Flow: present clear whole-changeset report -> case-by-case approval discussion ->
  user says what they accept / want different / or "apply it all" -> code executes.

## Heterogeneity as a discussion trigger (alembic case)

Rule: when a command family contains an **outlier in shape or scope**, do NOT
consolidate -- raise it for discussion. featherhill example: `uv run alembic -x db=test`
(targets a specific DB) among plain subcommands (`current`, `heads`, `upgrade head`,
`revision --autogenerate`).

- **Agent-guidance, NOT a deterministic detector** (deterministic outlier-detection is
  another rat-hole; the example may not generalize). Give the agent suspicion CUES, not
  a checklist: a sibling narrower/broader in scope than the rest; a token shaped like a
  flag-with-value; anything reading as a target/selector (db, env, host, path).
- Explicit ceiling: **flag for discussion, do NOT self-research the tool.** General
  programming knowledge is enough to notice "one of these looks DB-specific."
- Non-repeatable run-to-run; accepted under the same variable-trust banner as the
  audit's AI pass.

## Multi-pass pipeline (per-pass instruction files)

SKILL.md = orchestrator; `passes/*.md` loaded per pass (progressive disclosure; avoids
"too much at once -> mistakes"). Off-the-cuff pipeline (user's sketch + refinements):

1. Initial raw recommendations (identify what WOULD consolidate; no regex consolidation yet)
2. **Layer-targeting pass** -- MUST precede consolidation (this is the fix for the mkdir
   welding bug: you cannot correctly merge rules headed for different levels)
3. Consolidation + refinement (AI-level)
4. Initial report + prep for security audit
5. Run security audit (as-if-enacted, via `toolguard-audit --edits`)
6. Post-audit AI pass (fold in audit findings, modify recommendations) -- **bound the
   5->6 loop** (one revise + re-audit, else escalate to user; no ping-pong)
7. Corpus validation of the "final recommendation" -- **necessary, not sufficient**:
   replay only proves decision-equivalence over OBSERVED commands (the corpus-scoped
   -equivalence limit that made us punt #4(b)); understanding section + user stay the gate
8. Produce user-facing "understanding section" + cut/paste-ready concrete recommendation

- **Define the inter-pass state artifact first** (a working "recommendation set" JSON/MD
  that passes read + annotate) -- that contract is the orchestration glue.
- **AI-level family consolidation, not deterministic.** Deterministic single-token
  alternation stays only as a candidate-finder.

## Cut/paste provenance: authored by AI, certified by tool

Once consolidation is AI-driven the final TOML can't be purely tool-derived (accepted).
Mitigation: before the user pastes, run the assembled file BACK through the tool -- parse
it, load as config, replay the corpus, re-audit it. Bytes are AI-authored but
tool-verified to (i) parse, (ii) resolve consistently, (iii) pass the audit. The
understanding section explains; the certification backstops. Acceptable IF the
understanding section is clear enough for the user to vet.

## Report shape (fixes to featherhill output)

- **Understanding view**: grouped by command FAMILY, across all sections
  (allow/ask/deny/hard_deny), each rule marked no-change|edit|consolidate|remove|new,
  before->after, with a plain-English paragraph per family. UNCHANGED rules shown (a
  findings list is not a proposal; omitting unchanged rules makes the final state
  impossible to reconstruct).
- **Cut/paste section**: separate, exact resulting TOML per file in final-sort order.
- Collapse duplicate-explanation findings (the 5 identical alembic ask-overlap sentences
  -> one family block).

## First-run vs periodic

First maintenance is large/complex; periodic runs produce few/no changes -> different
user confidence in delegating. Implies:
- A **trust level** the user can dial (first run: discuss everything; periodic: surface
  only what's NEW; may pre-authorize no-ops).
- **Memory of prior decisions** so periodic runs don't re-litigate settled questions.

## Prior-decision memory / ledger

Two stores hide in "prior decisions":
- **Machine-read decision ledger** the skill re-parses each run ("don't re-suggest merging
  this family"; "this rule is intentionally project-scoped"). CANNOT be outsourced to an
  arbitrary human memory system -- needs a canonical, tool-owned format/location.
- **Human-facing narrative** -- can live in whatever notes system the user prefers;
  collected at install time.

Refinements:
1. **Decisions are level-scoped like the rules.** Ledger mirrors the config hierarchy:
   project ledger in `.claude/` (git-tracked, travels) + user ledger under `~/.toolguard/`,
   discovered the same way config is.
2. **Prefer in-file annotations** (`# toolguard:` / `#NOSECURITY`) where a decision
   attaches to a surviving rule (visible, versioned, travels). Reserve the sidecar ledger
   for META-decisions with no rule to hang on. Agreed: in-file is fine for SHORT things.
   For long rationales: start simple; if needed, in-file annotation becomes a short
   POINTER (note ID/link) to a longer write-up -- no new machinery, degrades gracefully.
   Only design real long-storage if in-file demonstrably stops working.
- Default fallback location when the user has no memory system: `~/.toolguard/memories/maintenance-skill/`.
- Install-time questions become concrete: (a) where is the USER ledger -- their system or
  the `~/.toolguard` default; (b) do they want PROJECT ledgers committed to the repo.

## Open decisions
- **DECIDED 2026-07-04: FOLDED INTO TOO-15** (not a new ticket). Arnon accepted the
  scope expansion -- the solution is not good enough to ship without this redesign. It
  now PRECEDES the TOO-15 pre-push (#6) and completion (#7) gates.
- **Layer-promotion** (moving rules to user level) = cross-context broadening (security
  dimension; only the developer can approve) -- flag-only candidates; coordinates with
  TOO-8 but stays inside TOO-15 for this work.
- Next step: PLAN the pass pipeline + the inter-pass state-artifact contract on paper
  before writing code. Audit-side dry-run files still owe Arnon's review and may reshape
  passes 5/6.

## Refinements from the featherhill dry-run (2026-07-04/05)

- **Top-level (non-permission) config is in scope.** The skill must detect and inform on
  `[takeover_mode]`, `governed_tools`, `[config_sync]`, `additional_supported_tools`
  (schema `config_settings`; pass 1 step 6, pass 3 step 1b). Detect-and-inform + doc
  links; never auto-change these.
- **Takeover is RESTRICTIVE, not broadening (framing correction).** It makes toolguard the
  gatekeeper, neutralizes *blanket* native allows, applies fail-closed. A broad native
  allow broadens only Claude's auto-approval, which the hook overrides. Do NOT alarm about
  takeover being on. Real failure conditions are narrow: (1) hook not registered (flag on
  but inert), (2) broad native allow on a tool no toolguard layer governs. Nuance:
  takeover neutralizes only *blanket* native allows; a *specific* native allow is still
  honored as a toolguard layer (so native can still broaden toolguard via non-blanket
  allows). Otherwise overlap = double-prompt annoyance.
- **Incomplete user-level toolguard config = strong alert (audit + maintenance).**
  User-level toolguard *rules* only enforce where toolguard actually runs. Rules at user
  level WITHOUT the full user-level setup (hook registered globally + base config) do
  nothing in toolguard-less projects -> false sense of security, worst for safety denies.
  Audit: flag HIGH+ (future deterministic detector candidate). Maintenance: recommend
  user-level layering BUT with a strong admonition to stand up the full setup together;
  never rules without setup, and never omit the recommendation.
- **Promotion is a first-class recommendation, biased DENY-eager / allow-cautious.**
  Promoted deny restricts everywhere (safe -- "when in doubt, restrict"); promoted allow
  broadens everywhere (risky, cross-context). Recommend promoting universal safety denies
  (.env/.ssh/rm -rf/secret paths) eagerly; promote allows only if clearly project-agnostic
  and benign; never execution-broad.
- **Post-audit remediation must VERIFY its own fix.** Real finding: `uv run python:*`
  arbitrary-exec CRITICAL cannot be cleared by any rewrite (bin/ scoping still flagged --
  running any python is arbitrary exec). Escalate as a user decision (#NOSECURITY vs
  remove vs tighten-as-hygiene), never report a tightened rule as a fix.
- **Stern warning on #NOSECURITY for code-exec allows** -- ungoverned arbitrary code
  execution the tooling cannot analyze; do not soft-pedal (pass 3a).
- **Open toolguard-semantics question:** does a user-level *deny* enforce without takeover
  enabled, and what is the correct user-level `[takeover_mode]` posture for
  promotion? Deferred to Arnon / docs -- do not assert.

Relates to [[too-15-p2-dry-run-featherhill-maintenance-security-audit]].

## Refinements 2 (2026-07-05, from report review)

- **Deny consolidation may TIGHTEN; allow consolidation must be behavior-preserving.**
  A superset deny is safe/preferred ("when in doubt, restrict"). When a tool-agnostic deny
  applies, it subsumes per-reader/per-path specifics -> adopt it and DELETE the specifics
  as redundant. Where tool-agnostic does not apply, a superset regex deny is still valid.
  Give broad denies a clarifying trailing comment (`# applies to ANY command-line tool`).
  Regex: use groups `(a|b)` + escaped dots, not char classes `[a|b]`.
- **Complete a read/write split on well-known tools (confident hardening).** e.g. git with
  read subcommands allowed and mutating ones absent -> recommend explicit deny/hard_deny
  for destructive ops (force-push, history rewrite, reset --hard, clean -f). Value =
  robustness if the allow side drifts; fail-closed already blocks them today. Optional.
- **Toolguard general config -> lean USER-level centralization.** governed_tools (incl.
  dev-tooling MCP tools), takeover posture, no_match_fallback. "Project-specific" MCP tools
  are a harmless superset at user level; centralizing reduces per-project setup + future
  contradiction. Only project-relative settings (backup_dir) stay project.
- **Inline interaction comments in cut/paste TOML.** Annotate rules whose effect depends on
  another (`# more-specific override of ask "Bash(uv run alembic:*)"`), same spirit as
  --annotate.
- **Audit: two user-level findings.** HIGH = rules at user level without full setup
  (false security); MEDIUM = project runs toolguard but NO user-level baseline at all
  (project-local governance only). Both future deterministic-detector candidates.
- All verified against featherhill: deny consolidation certified (16 -> 12 findings,
  introduces nothing, clears the head/tail deny-shadow LOWs).

## Cold-agent test outcome (2026-07-05)

Ran a cold subagent (fresh context) through the maintenance passes against featherhill.
**Result: strong validation.** It reproduced the whole report faithfully (family grouping,
uv-python honest framing + stern warning, mkdir weld split, alembic heterogeneity, takeover
accurate framing + hook-registered check, promotion admonition, certified end-state with
inline # DECISION) -- and BEAT our reference report in two ways: it anchored the MEDIUM
unanchored-regex findings (4M->0M) and it caught a real regex bug in our report.

Real defects it found (FIXED in passes):
- #1 (SERIOUS) certification staging false-clean: `audit --dir <tempdir>` on a bare temp
  dir doesn't load the staged config (no project root) -> takeover flips false, bogus
  hook-not-registered, ALL rule findings suppressed -> lying "clean". Fix: pass 3 now
  requires making the temp dir a project root (git init) + verifying takeover_active and
  context.summary.sources include the staged file before trusting the delta.
- #7 `.ssh` deny regex: `/\.ssh/` (leading slash) misses relative `.ssh/`; corrected to
  `\.ssh/` in pass 2 (also present in the featherhill report -- backport pending).
- #8 config_settings paths under `context.summary.*`, not top-level `summary` (null).

Real gaps still to address: #2 audit in-repo module form undocumented + 3 names
(toolguard-audit / security_audit / toolguard-security-audit); #3 two unreconciled cert
paths (`--edits` can't represent hand-authored TOML, so the "mandatory --edits review"
can't cover pass-2 judgement -- staging `--dir` cert is the authoritative one); #9 family
ownership of cross-cutting findings + "most-consequential" ordering tie-break; #10
self-permission rules name the console script not the module form; #6 recommendation-set
JSON deliverable status (it is internal scratch).

NOT skill defects (Headroom artifacts): #4/#5 "SKILL.md truncated/garbled" -- verified the
file is complete; headroom lossily compressed the subagent's file READS (dropped words).
Concrete context-correctness failure of the headroom compression -> flag to Arnon
(Headroom watch). Subagent still produced excellent output despite corrupted input.
