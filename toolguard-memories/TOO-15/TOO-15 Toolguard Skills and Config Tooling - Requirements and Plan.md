---
title: TOO-15 Toolguard Skills and Config Tooling - Requirements and Plan
type: guide
permalink: toolguard/too-15/too-15-toolguard-skills-and-config-tooling-requirements-and-plan
tags:
- task-memory
- TOO-15
- TOO-11
- skills
- toolguard
---

# TOO-15 / TOO-11 - Toolguard Skills and Config Tooling: Requirements and Implementation Plan

Status: **design / explore-discuss converged**. Not yet implementation-approved. This note
captures the agreed requirements and a proposed plan for Arnon's review.

TOO-11 is a strict subset of TOO-15 (it is the config-maintenance/analysis skill, #3 below).

## Context and problem

Toolguard is a Claude Code permission hook with extended rule syntax (regex/glob/native on
top of Claude-native patterns). Today there is no first-class, repeatable way to: get
toolguard set up in a project, migrate native Claude permissions into toolguard config,
keep a toolguard config healthy over time (consolidate, sort, de-dup, move rules up the
hierarchy, mine logs for missing rules), or audit a permission config for risk. Arnon does
this ad hoc today via two personal slash commands (`~/.claude/commands/denied-summary.md`,
`~/.claude/commands/sort-permissions.md`) - rough prototypes of this work. The goal is a
set of well-authored skills (mostly bundled into toolguard, heavy logic in testable Python)
that make these tasks safe, repeatable, and agent-driven.

Guiding philosophy (Arnon): skills are cheap to author and meant to be **iterated**, not
"once and done". Ship a useful first-order version backed by cheap deterministic helpers,
learn from real use, refine. Over-assuming up front is its own risk. Time is shared with
other projects - bias to high-value, low-maintenance slices.

## Scope: six artifacts and their homes

Resolution of the "general vs personal" split: general -> bundled into the toolguard repo
(`skills/` dir, installer wires into `~/.claude/skills`); personal -> staged in project
`tmp/skills/`, later moved by Arnon into his version-controlled `~/.claude`. At the end we
review `tmp/skills` for what can be generalized back into the bundled set.

1. **Bootstrap install** *(context i: toolguard NOT installed)*. A **fetchable instruction
   document** (e.g. `claude-install.md`), NOT a bundled skill - the package is not on the
   machine yet, so it cannot bundle this. Claude reads it once, interrogates the env
   (uv/pip/node, existing `~/.claude` layout), interviews the user, explains the
   recommended path, negotiates, executes, verifies, then discards it. Leans on TOO-16's
   `uv tool install` mechanism for the actual install. Throwaway / one-shot by nature.
2. **Project wiring + native->toolguard migration** *(context ii: toolguard installed,
   repeatable, bundled)*. Wire toolguard hooks into a project and import native Claude
   permissions into a `toolguard_hook.toml/json`, **semantics-preserving** (see glob defect
   below). May call the maintenance core (#3) as a building block.
3. **Config maintenance / analysis = TOO-11 core** *(context iii, bundled)*. Read the whole
   config hierarchy; sort; detect redundancy/subsumption; consolidate (3 strict families +
   1 agent-judged, see below); migrate rules up the hierarchy; mine logs for ASK/DENY cases
   that should become rules. Human-in-the-loop: propose -> diff/pros-cons/risk -> approve ->
   apply -> change report.
4. **Personal new-project setup** *(personal, `tmp/skills`)*. Arnon's raw-project
   bootstrapper: dir structure, per-dir CLAUDE.md, uv venv + standard deps, Obsidian vault
   linking, ticket-id patterns, wiring standard hooks (incl. toolguard via #2). Has a
   maintenance aspect (add a capability/stack to an existing project).
5. **Addendum assembly** *(personal, design-only for now)*. Compose
   `.claude/feature-coder-addendum.md` from reusable capability/stack sections (web-app,
   db-access, web-testing) maintained centrally and referenced per-project. Design and
   discuss; likely templating or `@`/markdown includes.
6. **Security-risk flagging** *(bundled, read-only, NEW - added this session)*. Ranked
   security findings across the *entire* toolguard+Claude permission hierarchy. Invokable
   at session start or on demand. Read-only: it reports, it does not edit. First real test
   cases already found: `Bash(uv run python:*)` allow (arbitrary code exec) and the
   unanchored `[regex]` find rule. **Must be takeover-mode-aware (see below).**

Plus a **discovered engine defect** (Read/Write/Edit glob infidelity) - see its own section.

## Cross-cutting architecture

- **Thin skill, deterministic core.** Heavy logic lives in testable Python (`toolguard` CLI
  subcommands / library functions) reusing existing modules: `config.py`,
  `config_divergence.py`, `normalization.py`, `patterns.py`, `permissions.py`,
  `auto_migrate.py`, `error_log.py`, `log_writer.py`. The SKILL.md layer does judgement:
  generalization, hierarchy placement, interviewing, risk narration.
- **Deterministic vs agent split.** Deterministic: load hierarchy, normalize, exact
  redundancy/subsumption, sort, log aggregation, static danger patterns, **decision-replay**
  (pure-Python match over a command corpus). Agent: propose generalizations, choose
  hierarchy level, multi-option scoped broadening, judge ASK->allow safety, write reports.

## Key design principles (agreed)

- **Allow/deny asymmetry (load-bearing).** Deny-direction work biases bold (broaden,
  consolidate freely - broadening a deny is fail-safe). Allow-direction work biases
  conservative (verified-equivalent by default; broadening only with explicit warning +
  risk assessment). Over-broad deny = workflow friction (visible, self-correcting);
  over-broad allow = silent security hole. Same wrongness, very different blast radius.
- **Decision-replay diff = the safety keystone.** Don't trust the agent's self-reported
  safety. Harvest a corpus of real commands (logs/transcripts), evaluate each under old vs
  proposed config using toolguard's OWN matcher (`patterns.match_pattern`), diff the
  allow/ask/deny decisions across the WHOLE config, and require the diff to match the
  approved change-set. A "strict" consolidation must yield a null-or-tightening diff; a
  loose one is allowed to broaden but must carry a warning, and replay *quantifies* exactly
  which new commands it admits (perfect input for the risk note). This is mandatory because
  toolguard's pattern dialect is quirky/inconsistent (below) - abstract reasoning about
  "glob semantics" would reason about the wrong engine. **Replay itself is free (pure
  Python, zero tokens);** token cost is only in harvesting transcripts + agent reasoning
  over the *changed* decisions. Corpus scope is the USER's knob (e.g. "<= 6 months"); their
  cost, their security, their call. Warn when the corpus is large.
- **Human-in-the-loop for every edit.** Refuse to run on a dirty git tree. Clear proposals
  with pros/cons + risk prioritization, explicit approval, then apply, then a change report
  for final human review. North star: every config edit toolguard makes must be MORE
  transparent and reversible than Claude's native "don't ask me again" (which writes a
  durable project rule with zero analysis or warning).
- **Reversibility (belt-and-suspenders, not top priority).** Preserve superseded rules
  (commented block and/or a sidecar changelog) so they cannot be lost; manual rollback
  first, mechanical rollback later if it earns its place. Git is the real backstop, but a
  toolguard-scoped mechanism is friendlier than digging through unrelated git history across
  repos.
- **Complex pattern = smell.** The skill never *generates* a pattern outside the simple
  verifiable families (below); if a consolidation needs a complex regex/glob it is left
  as-is OR offered as an explicitly-flagged agent-judged option. The same simplicity bar
  doubles as an audit finding: flag existing complex/unanchored patterns for human eyes
  (e.g. the `[regex]find` rule - which here is intentional and good, hence FLAG not rewrite).
- **The whole config is the unit of meaning (final reasoning only).** Intermediate work on
  isolated allow/deny groups is fine; never make the FINAL reasoning in isolation - the
  final evaluation must account for the whole picture (enforced by decision-replay over all
  decisions). Real landmine in featherhill: `uv run alembic <sub>:*` rules sit in **allow**
  while `uv run alembic:*` sits in **ask**; naively consolidating the allow rules into
  `uv run alembic:*` would collide with and override the ask rule -> silently allow ALL
  alembic commands. Only full-decision replay catches this.

## Takeover mode awareness (Arnon emphasized - critical)

Takeover mode (`docs/takeover-mode.md`) is a *specified feature*: native settings carry
blanket allows (`Bash(*)`, `Read(*)`, ...) so Claude never prompts, while toolguard is the
real gatekeeper. Toolguard strips those blanket allows from native config as it loads them
via `ignored_allow_patterns` (5 built-in defaults, additive, unioned across hierarchy).
`enabled` is recomputed live across levels and **fails safe to OFF** if levels disagree.

Implications for the skills:
- **#6 (security flagging) must be conditional on takeover state.** A bare `Bash(*)` in
  `settings.local.json` is NOT a finding when takeover is ON, the pattern is in the ignored
  set, and the hook is actually registered for that tool. It IS a critical finding when:
  takeover is OFF (or silently flipped OFF by a cross-level conflict) while blanket allows
  are present; or a blanket allow is present but not covered by `ignored_allow_patterns`; or
  the toolguard hook is not registered for a governed tool (then blanket allows are live and
  toolguard never runs); or `no_match_fallback` is unexpectedly loose. So #6 must first
  determine effective takeover state and verify the takeover *invariants*, then flag
  deviations. Misconfigured takeover is the single scariest real risk (full bypass), and it
  can look superficially fine.
- **#2 (migration) must not treat takeover blanket allows as real intent.** When takeover is
  ON, native allows are deliberately fake; the real rules live in toolguard config. Migrate
  intent, not the blanket allows.

## Discovered engine defect: Read/Write/Edit DEFAULT glob infidelity

Verified against Claude docs (code.claude.com/docs/en/permissions): "Read and Edit rules
both follow the **gitignore** specification ... `*` matches within a single path segment ...
`**` matches across directories." Bash has no gitignore path semantics (literal + greedy
`*`; `:*` == trailing ` *`); toolguard is faithful there.

Toolguard's matcher (`patterns.py`, `permissions.py`) has four types:
- `[regex]` -> `re.search` (UNANCHORED - security flag, not a bug; assume Claude not
  malicious but warn the user).
- `[glob]` -> `PurePath.full_match` -> standard globstar (`*` single-segment, `**`
  recursive). **CORRECT - not a bug.**
- bare/DEFAULT -> collapses `**`->`*` (`permissions.py:173-174`) then `fnmatch`, where `*`
  crosses `/`. **This is the bug** for Read/Write/Edit: a migrated `Read(src/*)` silently
  widens from one segment to fully recursive - broader than Claude. For Bash it is fine.
- `[native]` -> word-level wildcard (Claude 2.10 style).

Consequences:
- **Migration mapping correction.** Arnon's proposed `Read(tmp/*)` -> `Read(tmp/**)` would
  OVER-broaden (Claude `tmp/*` is single-segment). Correct semantics-preserving migration:
  emit the `[glob]` form to preserve the segment distinction, e.g. Claude `Read(tmp/*)` ->
  `Read([glob]tmp/*)` and Claude `Read(tmp/**)` -> `Read([glob]tmp/**)`. Also handle
  gitignore "bare filename matches any depth" (`Read(.env)` == `Read(**/.env)`) and the
  `//abs`, `~/home`, `/project-root`, `./cwd` anchors. `[glob]`/PurePath is close to but not
  a perfect gitignore implementation (bare-filename any-depth differs) - the migrator must
  bridge that.
- **Two fix options to decide (likely a separate ticket):** (a) migration-time only -
  always emit `[glob]` for path tools; cheaper, leaves the engine's bare semantics broad.
  (b) make bare/DEFAULT path-tool matching gitignore-faithful in the engine - matches
  Arnon's stated "bare must be 100% Claude semantics", but it NARROWS existing toolguard
  configs that rely on current broad `*` and risks regressions; needs its own replay-backed
  validation and likely its own ticket. Recommend tracking the engine fix separately and
  doing (a) in the migrator regardless.

## Consolidation families (grounded in featherhill real config)

Generator proposes only simple, verifiable candidates; replay verifies.
1. **Strict literal-alternation.** Rules identical except one slot of literal values.
   Real: `git diff:*` `git flake8:*` `git isort:*` `git log:*` `git ls-files:*`
   `git status:*` -> `[regex]^git (diff|flake8|isort|log|ls-files|status)\b`. Note the `^`
   (regex is unanchored). Verify by alternation expansion + replay.
2. **Strict subsumption elimination.** Drop a rule whose match-set is subset of another's.
   Real: `mkdir -p /tmp/claude-code:*` subsumed by `mkdir -p /tmp/:*`; `uv run pytest :*`
   ~= `uv run pytest:*`. Verify: dropped rule changes no decision in corpus.
3. **Loose wildcard-widening (warning required) -> now MULTI-OPTION.** Offer 2-3 broadening
   forms (native / `[glob]` / `[regex]`), each scoped to MINIMIZE blast radius, ranked by
   risk. E.g. for several `uv run python cli/scriptN.py`: prefer
   `[glob]uv run python cli/*.py` (bounded to project scripts) over `uv run *` (arbitrary
   exec). The agent inspects the real project tree/docs to pick the tightest pattern that
   covers observed usage. Replay quantifies the broadening for the risk note.
4. **Agent-judged, replay-verified (the "not black and white" middle).** The skill MAY
   propose pattern-complex consolidations it cannot statically prove, provided they pass
   replay and carry an honest risk assessment. SKILL.md guidance calibrated from real
   configs (featherhill + a few public GitHub `settings.local.json` examples) to be
   responsible without locking out too much.

## Testing strategy (autonomous + interruption-tolerant - Arnon's constraints)

No human-in-the-loop labeling; must survive the low-cost plan's 5h/weekly limit walls and
cross-session restarts; produce a report and a continue/stop decision.
- **Deterministic core: ordinary unittest** (BDD Given/When/Then docstrings, stdlib
  `unittest`). Containment/subsumption check, redundancy, sort, danger regexes, log
  aggregation. Every line made deterministic shrinks the non-deterministic surface.
- **Decision-replay diff: the keystone** (built first). Reuse toolguard's matcher; assert
  strict consolidations yield null/tightening diffs, loose ones only the approved
  broadening. Converts "did the agent do something unsafe?" into a deterministic check.
- **Auto-labeled ablation** (replaces hand-labeling). Remove rules, test if mining recovers
  them; ground truth from LOGS: a removed rule "had real need" iff some historical command
  changes decision when it is removed - mechanically derivable, no human. Recall on the
  real-need subset; false-positive rate on the spurious subset.
- **Adversarial fixtures** for danger-recall: planted `rm -rf`/`.env` allow + a "trap"
  consolidation that looks clean but broadens; assert skill + containment check catch both.
- **Structured-findings golden tests + multi-run variance.** Assert on structured claims,
  never prose. Variance in safety-critical findings (a danger flag appearing 3/5 runs) is
  itself a bug. Can lean on `skill-creator` variance tooling.
- **Durable harness.** Text-file work queue (one case/line, pending/running/done + result),
  results appended as completed, final consolidation pass. On restart: skip done, resume
  pending. Survives limit resets and session restarts.

## Open decisions for Arnon
**RESOLVED 2026-06-25** (Arnon will still review full spec/plan detail before implementation):

1. **Engine glob fix** -> APPROVED: migrator emits semantics-preserving `[glob]` for path
   tools now; the bare/DEFAULT gitignore-faithful engine fix is tracked as a **separate
   ticket**.
2. **Shared core for #3 + #6** -> YES (lean). Revisit at implementation if it needs
   splitting.
3. **Phasing / first slice** -> AGREED (P0 deterministic foundation -> #6 -> #3 -> #2/#1 ->
   personal). Testing aid: create **fake projects outside the repo** (e.g.
   `/tmp/test-toolguard-agents/*`) as fixtures. Late-stage: Arnon will manually test the
   install script on a **completely different machine**.

Overall shape approved; detailed spec/plan review by Arnon still pending before coding.

## Proposed phasing (for discussion, not committed)

- **P0 (foundation, deterministic):** hierarchy loader reuse + sort + exact
  redundancy/subsumption + **decision-replay harness** + danger-pattern library +
  takeover-state/invariant checker. All unit-tested; powers #3 and #6.
- **P1:** Security-flagging skill (#6) - read-only, lowest risk, immediately useful, exercises
  the danger lib + takeover awareness on real configs.
- **P2:** Maintenance skill (#3 / TOO-11) - sort/dedupe/consolidate (families 1-2 strict
  first, then 3-4), hierarchy migration, log-mining; all replay-gated.
- **P3:** Project wiring + migration skill (#2), incl. the corrected semantics-preserving
  glob mapping; bootstrap doc (#1) tied to TOO-16.
- **P4 (personal, tmp/skills):** new-project setup (#4) + addendum assembly (#5); then review
  for generalization back into the bundled set.

## Success criteria (verifiable - to firm up at plan time)

- Deterministic core has unit tests (BDD) incl. the alembic-style landmine and the planted
  danger fixtures; replay diff proves strict consolidations never broaden.
- #6 correctly classifies featherhill: flags `uv run python:*`; does NOT false-flag takeover
  blanket allows when invariants hold; DOES flag a deliberately broken takeover config.
- Migration of a sample Claude config is semantics-preserving under replay (esp. path-tool
  single-`*` vs `**`).
- Testing harness demonstrably resumes after a simulated interruption.

## Key references

- Prototypes: `~/.claude/commands/denied-summary.md`, `~/.claude/commands/sort-permissions.md`
- Real corpus: `~/projects/flowers/featherhill/.claude/toolguard_hook.toml`,
  `.claude/settings.local.json`, `logs/toolguard-*.md`
- Engine: `toolguard/patterns.py`, `toolguard/permissions.py` (`:173-174` `**`->`*`),
  `toolguard/config_divergence.py`, `toolguard/auto_migrate.py`
- Docs: `docs/takeover-mode.md`; Claude permission spec
  https://code.claude.com/docs/en/permissions (gitignore semantics quote)
- Related: [[TOO-16 uv tool distribution]] (bootstrap install mechanism)
## Implementation considerations (added 2026-06-25, Arnon)

- **Package segregation.** Automation-tooling-specific code lives in its **own package**,
  bolted onto core toolguard - not mixed into the existing core files. This keeps the core
  reasoning/debugging focused. Exception: pieces that are genuine **bug fixes / refinements
  of core toolguard** (e.g. the glob defect) belong in the existing core files.
- **Test-support code: ephemeral vs durable.** Some test code is throwaway (only for the
  duration of a testing run); some is worth keeping as **long-term, reusable test-support**
  (e.g. log-mining helpers, the ablation/run/evaluation cycle, the durable harness) - and
  conceivably reusable in other projects later (a big maybe). Use judgement per piece;
  separate the durable test-support into its own long-term location.
- **Human-in-the-middle development pattern.** Claude works mostly independently *within* a
  phase; at the **end of each phase** we review / discuss / fix / commit, then start the
  next phase from a **clean git tree**. Exceptions may apply as we go.
- **Verifiable families are not frozen.** Keep the agreed 4 families for now. We may discover
  more verifiable patterns from our own history or inspected GitHub projects; tackle such
  opportunities when encountered, not speculatively.
- **Glob defect - documentation requirement.** The fix is needed AND the
  context-dependent-semantics subtlety (same `*`/`**` syntax meaning different things in
  bare/DEFAULT vs `[glob]` vs Claude-native gitignore) MUST be clearly documented in
  toolguard's **user-facing docs** and in **technical-notes.md**. Editorial framing (Arnon):
  both Anthropic's choice to follow `.gitignore` semantics and git's original choice to
  overload globstar syntax for fnmatch-ish behavior are confusing; the least we can do is
  document it so users have a fair chance to understand it.
- **Possible P5 (low priority, discuss when we get there).** An additional bundled skill that
  reads the **latest Claude permission-rule documentation** and detects (a) semantic changes
  that cause divergence from toolguard behavior, and/or (b) new rule syntax that is
  unsupported - especially un-migrateable - or incompatible with toolguard. If built, it may
  need an **agent-targeted, semi-structured file** that tersely and accurately lists
  toolguard's permission semantics, written for the skill's agent to diff against Anthropic's
  docs (NOT for human consumption). Plenty of work before this.
- **GitHub harvest as a first-class STATIC corpus (was under-weighted).** Harvest real-world
  public permission configs via web/GitHub search, e.g.
  `site:github.com "settings.local.json" "months ago" "at main"` (or `"weeks ago"`). KEY
  DISTINCTION: GitHub gives us **configs/rules only, not transcripts/logs**. So it feeds the
  **static** analyses - consolidation-family calibration, danger-pattern discovery, "what
  real syntax appears in the wild" - but it CANNOT feed **decision-replay** or **ablation**,
  which need actual command history (only the user's own logs/transcripts provide that).
  GitHub = cross-user breadth for static heuristics; user logs = ground truth for replay.
