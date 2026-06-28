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
## P0 implementation sub-plan (started 2026-06-25)

**Package decision (Arnon):** sub-package **`toolguard/tools/`** (import root `toolguard.tools.*`),
NOT a top-level sibling. Ships with core; directory-level segregation. Tests under
`test/unit/` as `test_tools_<module>.py` (stdlib unittest, BDD docstrings). Surface:
**library-first, no CLI yet** (CLI added per-skill in P1/P2). Durable replay/harvest harness
lives in `toolguard/tools/` (it is product + test-support); only throwaway eval scripts go
under `test/`/`tmp/`.

**Reuse points (no reimplementation):**
- Hierarchy + takeover: `config.load_configuration()` -> `Configuration` (with
  `ResolvedDecision`, `Provenance`, `TakeoverConfig`, `TakeoverEnabledConflict`).
- Decision primitive: `permissions.decide_command_at_level_detailed` / `check_permission`;
  `hook.resolve_bash_permission_detailed` / `hook.resolve_file_path_permission_detailed`.
- Matcher: `patterns.match_pattern`, `permissions.match_command`.
- Corpus: daily logs `logs/toolguard-*.md` (md sections: `Status`, `Command`,
  `Matched Rule`/`Violated Rules`, `Agent`).

**Components (dependency / build order):**
1. `config_access` - facade over `Configuration` (load hierarchy, per-layer allow/deny/ask +
   provenance, effective takeover). Mostly reuse.
2. `decision` - `decide(config, tool, command|path) -> ResolvedDecision`. Single eval primitive.
3. `log_harvest` - parse daily logs into a structured corpus; user-bounded time window. Logs
   only in P0 (transcripts later).
4. `replay` (**keystone, built + checkpointed first**) - corpus + config A vs B -> per-command
   decision diff classified `unchanged/tightened/broadened` + summary stats.
5. `redundancy` - exact/normalized duplicate detection + replay-backed subsumption (rule
   redundant iff removal changes no corpus decision). Static family subsumption deferred to P2.
6. `danger` - ranked static findings over allow rules (rm -rf, .env/.ssh, `uv run python`-class
   arbitrary exec, unanchored `[regex]`, HEREDOC_TO non-bash, blanket allows outside takeover);
   takeover-aware.
7. `takeover_audit` - effective takeover state + invariant checks (enabled-consistency, blanket
   allows covered by ignored set, hook registered for governed tools, `no_match_fallback`).
8. `sorters` - deterministic stable rule-array sort (comment-preserving file rewrite = P2).

**Build staging:** keystone slice first = `config_access` + `decision` + `log_harvest` +
`replay` (+ unit tests) -> main-agent review/checkpoint -> then analyzers (redundancy, danger,
takeover_audit, sorters). Dev gotchas: stdlib unittest (NOT pytest); do NOT run `ruff format`
in this repo; PEP 758 except style is valid (3.14); verify with `uv run python -m py_compile`.
## P0 status: COMPLETE (2026-06-25) - awaiting Arnon review + commit

All in new sub-package `toolguard/tools/` (core files untouched - segregation held). Built by
feature-coder in two slices, main-agent reviewed.
- Keystone: `config_access`, `decision` (side-effect-free, faithful to hook), `log_harvest`,
  `replay` (broaden/tighten/unchanged classification). Report:
  [[TOO-15 P0 Keystone Implementation Report]].
- Analyzers: `redundancy` (static dup + corpus-backed subsumption), `danger` (data-driven
  detector table, takeover-aware), `takeover_audit` (4 invariants), `sorters`. Report:
  [[TOO-15 P0 Analyzers Implementation Report]].
- Tests: 131 new (`test/unit/test_tools_*.py`), full suite **905 OK**, ruff clean.

**Items for Arnon's phase-end review / possible fixes before commit:**
- `danger.py` detector set added `secret`/`password`/`credentials` substring matches beyond
  the spec'd `.env`/`.ssh`/keys - noisier; tune the table if undesired.
- A test prints "Migration completed..." to stdout (cosmetic stdout leak; not a failure).
- Recommended core refactor (deferred): move pure file-path helpers out of `hook.py` into a
  `file_permissions.py` (`decision.py` currently imports `hook._*`).
- `decision.decide` returns `provenance=None` for compound Bash (reason string carries source)
  - fine for P0; matters when P2 consolidation needs per-subcommand rule attribution.
- `takeover_audit` is the most security-consequential analyzer (feeds skill #6 in P1) - worth
  focused review (e.g. /code-review) before P1 relies on it.

Next: P1 = security-flagging skill (#6) on top of `danger` + `takeover_audit`.
## P0 cleanups deferred to END OF P0 (not end of all phases) - 2026-06-25

### Done already this session
- Resolver duplication removed: pure resolver layer extracted to `toolguard/resolve.py`;
  `hook.py` and `tools/decision.py` both delegate (drift-proof by shared code). Anti-drift
  contract test now in the discovered suite at `test/unit/test_resolve.py` (was wrongly placed
  in `coder-test/` by feature-coder, citing a non-existent CLAUDE.md constraint - corrected).
  Suite now **910 OK**.

### Deferred to P0 end
1. **Bash provenance (Arnon: required, not optional).** `decision.decide` currently returns
   `provenance=None` for compound Bash. Compound provenance is inherently a COLLECTION (one
   winning rule per sub-command), so the natural representation is an **extensible list of
   per-sub-command match records** `[(sub_command, decision, matched_rule, provenance)]` plus
   the overall verdict - NOT a tree (toolguard flattens sub-commands; the decision rule is
   "any deny->deny, else any ask->ask, else allow", so nested boolean structure is not used).
   This aligns with what already exists: `compound.resolve_compound_permission` resolves per
   sub-command, the hook collects `bash_overrides` as a list, and
   `hook._parse_compound_match_details` parses "All N sub-commands allowed: [cmd -> rule, ...]".
   Plan: extend the resolver to surface ALL per-sub-command matches (not just overrides) and
   carry an optional `sub_matches` list on `Decision`. Needed by P2 consolidation (per-rule
   attribution) and richer audit/redundancy. Can be a bit messy -> do at P0 end.

2b. **DISCOVERY (Arnon's recall, confirmed): comment-preserving, section-aware sort ALREADY
   EXISTS AND IS TESTED** in `toolguard/scripts/migrate_permissions.py`:
   `parse_permissions_section_with_comments()` (items typed comment_block/rule/header),
   `reassemble_permissions_section()` (associates each comment block with the FOLLOWING rule,
   preserves inline + top/bottom comments, sorts), `find_section_boundaries()`, and
   `sort_patterns()`/`get_tool_priority()`. Tested in `test/unit/test_migration.py`:
   test_preserves_inline_comments, test_preserves_comment_blocks_above_rules,
   test_preserves_top_of_section_comments, test_preserves_bottom_of_section_comments,
   test_preserves_blank_lines_in_comment_blocks, **test_comments_move_with_sorted_rules**.
   => Do NOT rebuild this for P2; REUSE it. PROBLEM: `tools/sorters.py` (new) reimplemented
   `sort_patterns` with a DIVERGENT order (pattern-TYPE-first vs migration's TOOL-priority),
   so migration auto-sort and the maintenance skill would flip-flop the config (diff churn).
   CLEANUP (P0-end): (a) standardize on migration's `get_tool_priority` order (the shipped
   one); (b) extract the comment-preserving machinery + the single canonical sort out of
   `scripts/migrate_permissions.py` into a shared module (same move as `resolve.py`) reused by
   migration + tools (hands us the P2 comment-aware file-rewrite for free); (c) collapse
   `tools/sorters.py` to a thin adapter or delete it.
   PROCESS NOTE: 2nd time a subagent rebuilt existing tested code (resolver, now sorter) ->
   future P0-end/P2 briefs MUST instruct: inventory `migrate_permissions.py`/`auto_migrate.py`
   first and reuse.

2. **`sorters.py` comment preservation (Arnon).** Current `sorters.py` sorts bare pattern
   strings (`List[str] -> List[str]`) and has NO comment awareness - this was the EXPLICIT P0
   scope (file rewrite + comments deferred to P2; documented in the module docstring). Arnon's
   point is the design requirement for the eventual rewriter: in TOML, **a comment is
   associated with the rule that FOLLOWS it**, so sorting must move "leading comment block (+
   trailing inline comment) + rule" as an ATOMIC unit. The string-list API must evolve to a
   rule-entry model (e.g. `RuleEntry(leading_comments, pattern, inline_comment)`).
   ADDED HAZARD to design for: **group / section-header comments** (e.g. `# Git operations`
   above several git rules) get semantically BROKEN by alphabetical sorting that scatters the
   group. The comment-preserving sorter (P2, or pulled earlier if needed) must decide how to
   handle these - e.g. treat a blank-line-delimited commented group as a unit and sort within
   it, or WARN/skip reordering across comment boundaries rather than orphaning a header. Do not
   ship a naive file-rewriter that orphans header comments.
## FUTURE WORK: transcript harvesting (Arnon flagged 2026-06-25)

`tools/log_harvest.py` is **logs-only by P0 design**; harvesting **Claude conversation
transcripts** (`~/.claude/projects/<hash>/*.jsonl`) is deferred but is the RICHER source and
must be added (likely P2, when the log-mining / rule-suggestion skill needs it).

Why transcripts beat toolguard's own logs:
- toolguard logs capture only GOVERNED tool calls + the decision toolguard made.
- Transcripts capture **ASK resolutions** (Claude asked -> user approved/denied -> "don't ask
  again" rule written) -- the core signal the TOO-11 log-mining skill needs to suggest new
  rules. Much of this never reaches toolguard's logs.
- Transcripts give a fuller command corpus (denied/ungoverned commands) + surrounding context
  for risk assessment and ablation ground truth.

REUSE (don't rebuild): toolguard already parses transcripts via
`hook.identify_current_agent(transcript_path)` / `subagent.py`; also `~/bin/recall_main_agent_conversation`
and the local-tools MCP read the `*.jsonl` transcripts. Transcript harvesting should reuse that
parsing and emit the SAME `LogEntry` corpus shape so `replay`/`redundancy`/ablation are unchanged.
### Transcript harvesting — second advantage: COLD START / onboarding (Arnon 2026-06-25)

Beyond richer ongoing mining, transcripts are the **only** governance history a NEW toolguard
user has (they have zero toolguard logs yet). This makes transcript harvesting a prerequisite
for the **setup/migration skill (#2)**, not just maintenance (#3): the onboarding pitch is
"you've been working without toolguard — let me mine your transcripts and propose a starting
ruleset," paired with decision-replay (replay transcript commands against a candidate config to
propose rules that would have allowed the legit work and surfaced the rest).

**Auto-mode users are the strongest case AND the worst-served by logs-only:** they accumulate
NO `settings` history either (no "don't ask again" rules, no recorded prompt decisions) — the
transcript is the SOLE record of what ran. Exactly the users who most need an independent
guardrail are invisible without transcripts.

**Positioning (Arnon's view, endorsed with nuance):** Anthropic's auto-mode answer to approval
fatigue is structurally weak — the same model that ISSUED the call also CLEARS it, in-the-moment,
opaque, with no durable user-authored policy and no audit trail (self-judgment, no independent
check). Nuance: the auto classifier is configurable for "trusted infrastructure" and framed as a
separate safety check, so not purely "trust me" — but still not transparent/user-controllable at
the decision boundary and leaves no reusable policy behind. This is a core argument FOR toolguard:
deterministic, transparent, user-owned policy independent of the model's in-the-moment judgement.


## Future / out-of-scope idea: auto-mode activity forensics (raised 2026-06-26)

Idea: have the security audit also analyze what Claude actually DID in **auto mode**
(auto mode reportedly emits its own dedicated log format).

Decision/analysis (Claude's critical take, Arnon to confirm):

- **Does NOT belong in the #6 security-CONFIG audit.** That skill is a *static
  configuration* analyzer (what rules COULD permit). Auto-mode log review is
  *behavioral/forensic* (what DID happen). Different activity, different trust model;
  folding it in dilutes a clean purpose.
- **Redundant when toolguard governs.** If toolguard is installed (esp. takeover mode),
  every tool call is intercepted regardless of auto mode -- "what auto mode did" == "what
  toolguard allowed," already in toolguard's own resolution/decision logs. So marginal
  value is low for existing toolguard users (Arnon's own point).
- **Where it IS valuable:** users with NO toolguard logs -- exactly the auto-mode-without-
  toolguard cohort. Same target + same "what did the agent actually do" source class as the
  planned **P2 transcript harvesting**. So auto-mode logs = one more optional forensic
  source for rule discovery / risk spotting, not a config-audit feature.
- **Thematic fit / placement:** strong toolguard adoption-motivator ("here's what auto mode
  did without your oversight") aligned with toolguard's mission as a transparent, user-owned
  alternative to opaque auto-approve. But keep it a SEPARATE skill/tool (or even separate
  project), not part of #6. Likely a new ticket, P2-adjacent (shares transcript-parsing
  plumbing: hook.identify_current_agent, subagent.py, recall_main_agent_conversation).
- **Risk:** auto-mode log format is undocumented/Anthropic-internal and can change without
  notice -- gate behind a tolerant parser; treat as optional source.


## Pre-completion cleanup gate + setup-skill partial-install requirement (2026-06-26)

**Cleanup before closing TOO-15 (REMIND Arnon):**
- Remove the temporary dogfood symlinks: project `~/projects/toolguard/.claude/skills ->
  ../skills` (gitignored), and confirm no stray links under `~/.claude/skills/`.
- Install the bundled skills "properly" via the setup facilities built in TOO-15, not hand
  symlinks.
- Rationale: repo is intentionally left "dirty" during TOO-15 to continuously evaluate the
  tooling against imperfect/realistic configs (already surfaced real findings on the toolguard
  repo and on featherhill). Clean up + switch to the real install path at ticket close.

**New requirement for the setup "disposable" skill (#4) and the bundled maintenance skill
(#3): detect + handle a PARTIAL install.** This machine has toolguard installed globally but
NOT the full post-TOO-15 setup. The flow must:
- detect a stale/partial install and prompt `uv tool upgrade`;
- detect which bundled skills are NOT installed -- check BOTH project `.claude/skills/` and
  user `~/.claude/skills/`, and account for broken/dangling/incorrect symlinks (we hit several
  relative-symlink footguns this session; a dangling link "exists" but doesn't resolve -- the
  detector must not be fooled);
- offer to install the missing skills, letting the USER choose scope: local-project vs
  user-level (explain trade-off: audit/maintenance skills lean user-level; project-specific
  lean local).
- Detection should be deterministic (Python), driven by the skill. Reinforces the open TOO-16
  "skill install story" item.


## Self-permissioning: skills must get toolguard's own tools allowed (2026-06-26)

Problem: bundled/private/disposable skills shell out to the installed toolguard console
scripts (e.g. `toolguard-audit`). Under toolguard governance (esp. takeover mode), those
are `Bash` commands toolguard must permit, or the skill's own call is denied
(chicken-and-egg).

Design (Arnon + Claude, to implement when authoring setup/maintenance skills):
- The setup/maintenance skill **suggests concrete allow rules** for the toolguard tools the
  skills actually invoke, gets **explicit user consent**, then writes them to the chosen
  config level. **Never hard-code / auto-apply** -- toolguard must not make security
  decisions for the user; every allow stays explicit and auditable. (Auto-self-grant is a
  privilege-escalation smell and contradicts toolguard's mission.)
- **Refine the set (Claude's pushback): do NOT blanket-allow all pyproject `[project.scripts]`.**
  `toolguard` and `toolguard-session-start` are HOOK entry points run by Claude Code's hook
  machinery, NOT as Bash tool calls -- they never need Bash allow rules. Allow only what
  skills actually run via Bash (today: `toolguard-audit`; later: maintenance/update CLIs).
  Minimal + skill-specific = more auditable.
- **Granularity by tool risk:** read-only tools (`toolguard-audit:*`) are fine to allow
  broadly. A future config-MUTATING maintenance tool must NOT be blanket-allowed -- use
  ask-mode or per-invocation consent, else the model could mutate the security config via
  the tool and bypass the human-approves-edits principle.
- **Scope symmetry:** write the allow rules at the SAME level the skill is installed
  (user-level vs project-level) -- unify with the installer's local-vs-user choice
  ([[too15-completion-gate]]).
- **Bootstrapping:** handle the allow-rule suggestion at INSTALL time (the user is already
  consenting to scope/upgrade there) so the audit/maintenance skills "just work"; plus a
  self-healing fallback (a skill detects its own command was denied and offers to add the
  rule, then retries).
- **Docs:** add a short note (security.md / skills doc) that toolguard's skills depend on
  toolguard's own console scripts, and those must be allowed to be fully functional under
  governance. The need is sharpest in takeover mode.

**TOO-19 (raw, do not rely on yet):** Arnon has future ideas in ticket TOO-19 relevant to the
self-permissioning / "always-ask" approach for the toolguard tools. Consider it when authoring
the setup/maintenance skills (read it then -- it is raw now). Arnon leans toward agreement on
ask-mode for mutating tools.

## P2 KICKOFF (2026-06-26) - decisions + P2-A spec

P1 committed (fc16ce9), not pushed. Arnon: "ready for p2".

**P0-end prerequisites: ALL LANDED** (verified this session) - so P2 starts from a solid base:
- Shared canonical sort + comment-preserving file machinery extracted to `toolguard/rule_sort.py`
  (`parse_permissions_section_with_comments`, `reassemble_permissions_section(parsed, new_permissions, auto_sort)`);
  `tools/sorters.py` is now a thin delegate (no more divergent order / diff churn).
- Bash provenance done: `tools/decision.Decision.sub_matches` carries per-sub-command `SubMatch`
  records (per-rule attribution P2 consolidation needs).

**P2 scoping decisions (AskUserQuestion):** start = **consolidation engine first** (P2-A);
surface = **library-first, CLI/skill last** (CLI + SKILL.md land in P2-E). Same rhythm as P0/P1.

**Proposed P2 slicing:** P2-A consolidation engine + apply + change-report -> P2-B transcript
harvesting -> P2-C mining->rule-suggestion + hierarchy migration -> P2-D families 3-4 (agent-judged)
-> P2-E maintenance SKILL.md + CLI.

**NEW cross-skill requirement (Arnon 2026-06-26):** the maintenance skill (#3) must be able to
**invoke the security-audit skill (#6) and turn its remediations into reviewable edit proposals**
(e.g. tighten/narrow/remove a flagged dangerous allow). Primarily P2-E wiring, BUT the P2-A
proposal data model must be general enough to represent a remediation EDIT, not only a
consolidation - so audit findings can be ingested as proposals later. `danger` findings already
carry `remediation`; the maintenance core ingests finding -> proposal -> replay-gate -> human approve.

### P2-A sub-plan (keystone-first, mirrors P0)

Reuse map (INVENTORY FIRST - do NOT rebuild; 2 prior subagent rebuilds of existing tested code):
- `config_access.per_layer_rules(config, tool) -> List[LayerRules(provenance, allow/deny/ask tuples)]`.
- `replay.replay(corpus, A, B) -> ReplayDiff` (broadened/tightened/unchanged) = THE GATE.
- `redundancy._config_without_allow(config, tool, pattern)` = existing "build synthetic Configuration
  with a layer's allow list modified (MappingProxyType rebuild) then replay" technique. GENERALIZE
  it into one shared primitive; refactor `_config_without_allow` to delegate (anti-drift).
- `patterns.parse_pattern(pattern, extended_syntax=True) -> (PatternType, body)` for tokenizing/building.
- `rule_sort.reassemble_permissions_section` for the (P2-A.2) comment-preserving file rewrite (TOML-only
  today; JSON writer is a P2-A.2 open item).

**P2-A.1 (library-only, NO file I/O) - the keystone, build + checkpoint first:**
New `toolguard/tools/consolidate.py`.
- Step 0: extract `with_layer_allow_replaced(config, tool, provenance, removed:Set, added:List) -> Configuration`
  (generalize `_config_without_allow`; make it delegate). Single "make config B" primitive.
- Family 1 literal-alternation: per layer+list, find >=2 DEFAULT rules token-identical except ONE
  literal (wildcard-free) slot; propose `[regex]^<prefix> (v1|v2|..)<suffix>` honoring DEFAULT `:*`==trailing ` *`.
  STRICT acceptance = BOTH (a) self-contained probe-equivalence (synth positive probes = literal
  expansions all stay allow; negative near-miss probes change NO config-A verdict) AND (b) historical
  replay broadened_count==0. Else DO NOT emit as strict (defer to P2-D agent-judged).
- Family 2 static subsumption: conservative, corpus-INDEPENDENT subset proof (DEFAULT glob/`:*`
  structural superset, e.g. `mkdir -p /tmp/claude-code:*` ⊆ `mkdir -p /tmp/:*`); drop subsumed rule.
  Replay as secondary guard. Distinct from redundancy's corpus-only subsumption.
- `ConsolidationProposal(kind, tool, list_type, layer_provenance, removed_patterns, added_pattern,
  rationale, replay_evidence)` - general enough to also model a remediation edit (see cross-skill req).
- `propose_consolidations(config, tool, corpus=None) -> List[ConsolidationProposal]` (strict, verified only).
- Allow/deny asymmetry: allow-direction conservative (this slice); deny broadening is later.
- Tests (BDD): git-family family-1 happy path; **alembic landmine REJECTED** (ask->allow broadening
  caught by probe+replay); mkdir family-2 subsumption; conservative non-claim; synthetic-config
  builder + redundancy delegation still green. Suite must stay OK (currently ~1009).

**P2-A.2 (after checkpoint):** comment-preserving apply (rule_sort) writing approved proposals to
toolguard_hook.toml (+ JSON-writer decision); structured change-report; dirty-tree guard belongs at
skill/CLI level (P2-E), apply fn stays pure.

## P2-A.1 review findings + family-1 decision + curated-tool-advisor idea (2026-06-26)

**Verification (main agent, against faithful `decide` oracle):** the delivered family-1 is SAFE
(never broadens: DEFAULT `cmd:*` is a PREFIX fnmatch, e.g. `git diff:*` already matches
`git difftool`/`git diff-index`; the generated `^...\b` regex is a strict SUBSET), BUT it
**silently TIGHTENS**: the trailing `\b` drops `git difftool`/`git diffstat` from allow->deny,
undisclosed and not caught by the probes. Violates the "strict family-1 = verified-EQUIVALENT" contract.

**DECISION (Arnon): family-1 must be EQUIVALENCE-PRESERVING.** Fix dispatched to feature-coder:
(1) drop the trailing `\b` so the regex mirrors DEFAULT `:*` prefix semantics exactly; (2) harden
the gate to require **zero changed decisions** (reject on ANY `tightened` OR `broadened`, via
`replay.classify_change`) - this enforces true equivalence AND self-protects edge arg-forms
(no-colon exact patterns); (3) probe set must include prefix-extension near-misses; (4) replace the
weak/misleading "alembic = token-count" test+docstring with a test that actually exercises the
gate's reject path + a positive equivalence test (difftool/diffstat stay allowed). Behavior-CHANGING
consolidations belong to the later agent-judged family, not strict family-1.

**NEW DIRECTION (Arnon, worth pursuing - see assessment): curated well-known-tool advisor.**
Beyond literal-alternation, two things:
- **(a) More simple statically-analyzable families** - literal-alternation is just the first; harvest
  more verifiable families from real configs/GitHub (already aligned with "families not frozen").
- **(b) Curated knowledge base for a VERY SELECT FEW ubiquitous Bash tools** (git chief among them;
  ls/cat/head/wc/grep) whose read-only vs state-changing surface is stable + well-known. For these the
  maintenance tool can: never silently tighten them; proactively SUGGEST safe completions the user
  never configured (e.g. observe several read-only git subcommands allowed -> suggest the full
  read-only set); and suggest completing an INCOMPLETE deny set (e.g. some state-changing git commands
  denied -> suggest the rest: commit/push/branch/reset/rebase/...). NOTE alembic is NOT such a tool
  (project-specific, not universally known) - the curated set is deliberately tiny.

**CRITICAL CAVEAT (the load-bearing subtlety): "read-only" is a property of (tool + FLAG constraints),
NOT the tool alone.** Trapdoors most users miss:
- `find`: `-exec`/`-execdir`/`-ok`/`-okdir` (arbitrary exec), `-delete` (destructive),
  `-fprintf`/`-fprint`/`-fls` (write files). (Arnon's example.)
- `git`: `-c core.pager=...`/`--ext-diff`/`-O`/aliases (exec), `git config` (writes), `git clean -f`
  (deletes), `git checkout`/`restore`/`stash` (mutate), `git grep --open-files-in-pager`.
- `tar`/`zip`: `--to-command`, `-I`/`--use-compress-program` (exec).
- redirection (`> file`) is a SHELL write, seen by toolguard as a separate compound part, not the tool.
So the curated table must encode trapdoor FLAGS as first-class (whitelist read-only subcommands AND
constrain/deny trapdoor flags), never assert "read-only" naively.

**Placement / design (recommended):** keep this OUT of the core consolidation engine (Arnon's
constraint: don't make that code complex). Put the curated knowledge in a SEPARATE, versioned,
conservatively-reviewed deterministic data table under `toolguard/tools/` (like `danger.py`'s detector
table) = SINGLE SOURCE OF TRUTH consumed by BOTH the maintenance advisor (suggestions) AND skill #6
danger detection (an allow rule permitting `find ... -exec` or `git -c ...` is a FINDING). Suggestion
engine, human-in-the-loop, replay-gated. Direction-of-risk aligns with allow/deny asymmetry:
deny-completion = fail-safe/bold (the safer, high-value half); read-only allow-expansion = broadening,
must be conservative + trapdoor-aware + approved + replay-quantified. Ongoing-maintenance liability
mitigated by keeping the set TINY, suggestions never auto-applied, honest confidence, prefer
deny-direction when unsure. Likely its OWN ticket / a later P2 slice (knowledge-driven, not derivable
from the config). Shared knowledge base = good ROI that justifies the maintenance cost.

## Deep-tool-knowledge feeds the SECURITY AUDIT too (Arnon 2026-06-27)

The curated tool-knowledge base is a SHARED capability consumed by BOTH #3 (maintenance/suggest)
AND #6 (security audit/flag). Audit angle:
- A plain allow like `Bash(find:*)` / `Bash(find :*)` looks innocent but grants a trapdoor tool
  (find `-exec`/`-execdir`/`-ok`/`-okdir`/`-delete`/`-fprintf`/`-fprint`/`-fls`) -> must be flagged.
- A hand-authored guard like featherhill's `Bash([regex]\bfind\b(?!.*\s-(exec|execdir|delete)\b))`
  is better but INCOMPLETE (misses -fprintf/-fprint/-fls/-ok/-okdir) -> a real low/medium finding.

**Deterministic vs AI split for the audit (Arnon's distinction, endorsed):**
- DETERMINISTIC detector (new, additive to `danger.py`'s table): robustly handle the SIMPLE/known
  forms only - plain DEFAULT/`:*`/limited shapes (incl. the limited `[regex]` forms toolguard's OWN
  suggestion generator authors). Flag "allow grants a known-trapdoor tool with NO guard" (e.g.
  `find:*`). Do NOT attempt full semantic analysis of arbitrary hand-written regex/negative-lookahead.
- AI-DRIVEN pass: evaluates partial/complex guards (e.g. the incomplete `find` lookahead) and raises
  low/medium suspects. GROUND it by feeding the curated tool-knowledge table into
  `toolguard-audit --with-context` so the AI reasons from real trapdoor-flag knowledge instead of
  hallucinating. (Note: deterministic audit currently analyzes neither - this is new work.)

**Short-list selection = TRANSCRIPT-EVIDENCE-DRIVEN.** Pick the "deep knowledge" tools from what Claude
actually invokes (frequency-rank harvested transcripts - ties directly to P2-B transcript harvesting),
optionally enriched with a few ultra-common community tools from Claude's training knowledge. Arnon is
happy to START with only hard-evidence-from-his-transcripts tools.

**Trapdoor-tool candidates from training knowledge (enrichment; unit is (tool, FLAGS) not tool):**
exec/write/delete trapdoors hiding in "benign-looking" tools: `find` (above); `awk`/`gawk`
(system(), `print > file`); `sed` (`-i` writes, GNU `e` execs, `w file`); `xargs` (runs arbitrary cmd);
`tar` (`--to-command`, `-I`); `git` (`-c`,`--ext-diff`,aliases,config,clean,checkout/restore/stash);
pagers/editors `less`/`vim`/`man`/`view` (`!cmd`, LESSOPEN); command-runners `env`/`timeout`/`nice`/
`watch`/`nohup`/`xargs`; net tools `curl`/`wget`(`-o`/`-O` write, curl `-K`), `ssh`/`scp`/`rsync`(`-e`/
`--rsh` remote exec); interpreters `python`/`perl`/`ruby`/`node` `-c`/`-e`. EVEN "pure" text tools have
edge writes: `sort -o FILE` overwrites, `tee` writes. So "read-only" is ALWAYS per-flag.
Shell redirection (`> file`) is seen by toolguard as a separate compound part, not the tool.

**Placement reaffirmed:** one versioned deterministic data table under `toolguard/tools/` (single source
of truth) consumed by danger.py (#6 deterministic), the maintenance advisor (#3), and the audit
--with-context (#6 AI). Likely its own ticket; evidence (short-list) comes from P2-B transcripts.

## P2-A.1 STATUS: consolidation core DONE + equivalence fix LANDED (2026-06-28)

Family-1 (literal-alternation) + Family-2 (static-subsumption) consolidation engine built
(`toolguard/tools/consolidate.py`), library-only, replay/probe-gated. Equivalence-preserving fix
applied (no `\b`; gate hardened to no-changed-decision; prefix-extension probes; prefix-forms only).
Full suite **1037 OK**, ruff clean. NOT committed (TOO-15 dirty-by-design). See
[[TOO-15 P2-A.1 Consolidation Core Implementation Report]] addendum.
Next: P2-A.2 (comment-preserving apply via rule_sort + change-report; dirty-tree guard at skill level)
-> then P2-B transcripts, P2-C mining+hierarchy, P2-D families 3-4, P2-E SKILL+CLI. Curated
tool-knowledge advisor/audit-integration = separate later slice/ticket (transcript-evidence-driven).

## P2-A.2 STATUS: apply + change-report DONE (2026-06-28)

New `toolguard/tools/rule_apply.py` (library-only): `apply_proposals(proposals, *, dry_run=False)
-> ChangeReport` and `render_change_report(report, fmt)`. Groups proposals by file, removes
`removed_patterns` / adds `added_pattern` from the allow list, rewrites comment-preservingly.
- REUSE (no rebuild): `migrate_permissions.write_toml_config`/`write_json_config` for the write;
  stdlib `tomllib`/`json` to read RAW current perms (deliberately NOT a loaded Configuration --
  that may be takeover-filtered, which would drop blanket allows on write); `difflib.unified_diff`.
- dry_run computes the diff by rendering onto a TEMP COPY (real file untouched) -- the skill uses
  this to show the change before approval. Config drift (removed pattern absent) -> skipped+reported,
  not applied. path=None / unsupported list_type -> skipped+reported.
- `FileChange`/`ChangeReport` dataclasses; structured (golden-testable), ASCII report renderer.

**Prerequisite fix landed in core `rule_sort.parse_permissions_section_with_comments`:** it only
recognized DOUBLE-quoted rule lines, so SINGLE-quoted TOML literals (e.g. featherhill's
`'Bash([regex]\bfind\b(?!...))'`) were silently dropped/regenerated on a sort-reassemble cycle
(the "don't orphan rules/comments" hazard). Now parses single-quoted literals too and PRESERVES the
original line verbatim (keeps quoting + literal backslashes + comment association). Benefits migration
too. Regression test added in test_migration.TestCommentPreservation.

Tests: +10 `test_tools_rule_apply.py` (toml/json apply, dry-run+diff, single-quote+comment+other-rule
preservation, drift skip, no-path skip, multi-proposal-same-file, report render+invalid-fmt) +1
migration. **Full suite 1048 OK, ruff clean.** NOT committed (TOO-15 dirty-by-design).

P2-A COMPLETE (consolidation engine + apply + change-report). Open items for P2-A.2 noting:
- reassemble repositions a section-level comment that preceded `allow =` to inside the list (preserved,
  not lost) -- acceptable churn, user reviews diff.
- dirty-tree guard + user-approval flow are P2-E (skill), apply fn stays pure.
Next checkpoint: review/commit P2-A as a unit, then P2-B transcripts.
