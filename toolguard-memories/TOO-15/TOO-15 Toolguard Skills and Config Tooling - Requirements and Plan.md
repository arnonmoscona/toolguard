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

## P2-B STATUS: transcript harvesting DONE (2026-06-28)

New `toolguard/tools/transcript_harvest.py` (library-only). Parses Claude Code session
transcripts `~/.claude/projects/<encoded>/*.jsonl` into the SAME `log_harvest.LogEntry` shape,
so replay/redundancy/consolidate work unchanged (validated end-to-end: 200 harvested Bash cmds
ran straight through `replay_single` against the live config).
- `harvest_transcripts(dir, since, max_age_days)` mirrors `log_harvest.harvest` windowing (floor
  applied PER ENTRY by timestamp, since transcript files aren't per-day); `harvest_transcript_file(path)`;
  `transcript_dir_for_project(project_dir, claude_home=None)` encodes path `/`->`-`.
- REUSE: `subagent.parse_jsonl_lines` for JSONL; emits `log_harvest.LogEntry`.
- Walks assistant `tool_use` items for governed tools (Bash->input.command; Read/Write/Edit->
  input.file_path), joins each to its `tool_result` by id for status.
- RICHER STATUS than logs (the cold-start/auto-mode value): is_error False -> EXECUTED; is_error True
  + "doesn't want to proceed"/"rejected" -> **REFUSED** (the ASK->deny resolution = the rule-mining
  gold; reason text kept in rule_text); other is_error -> ERROR (permitted-but-failed); no result ->
  UNKNOWN. Timestamps ISO/UTC -> naive LOCAL (matches log convention). agent = subagent if isSidechain
  else main (coarse, best-effort). Malformed lines / missing dir handled gracefully.
- On the real toolguard transcript: 1336 governed uses (Bash 570/Read 316/Write 92/Edit 358);
  2 REFUSED were real `find` rejections with reason captured.

Tests: +15 `test_tools_transcript_harvest.py` (status derivation x4, tool extraction x3, timestamp/
agent/windowing x5, robustness/helpers x3). **Full suite 1063 OK, ruff clean.** NOT committed.

Note: harvesting only (corpus producer). The MINING (REFUSED/ASK -> suggested rules) + auto-mode
forensics is P2-C. Next: P2-C mining + hierarchy migration; then P2-D families 3-4; P2-E SKILL+CLI.

## P2-C.1 STATUS: rule mining core DONE (2026-06-28)

New `toolguard/tools/mining.py` (library-only) -- deterministic successor to the `denied-summary`
prototype. Does NOT generate patterns (that stays agent/skill + the future curated-tool advisor);
it AGGREGATES + CLASSIFIES + VERIFIES.
- `mine_rule_candidates(config, corpus, *, min_occurrences=1) -> MiningReport`: for each corpus entry,
  compares CURRENT `decide()` verdict vs OBSERVED status and classifies:
  `allow-candidate` (config asks/denies but it EXECUTED -- approval fatigue / blocked-but-used),
  `declined` (user REFUSED the prompt -- transcript signal), `denied`, `asked`; `consistent`
  (already-allowed+ran) omitted. Groups by (tool, command_key, signal): Bash key = executable token,
  file tools = parent dir. Sorted by occurrences desc.
- `evaluate_added_allow_rule(config, tool, pattern, target_provenance, corpus) -> AddRuleEffect`:
  replay-measures EXACTLY which corpus commands a proposed allow rule newly admits (the risk-note
  blast radius); reuses `with_layer_allow_replaced` + `replay`. tightened should be 0.
- `render_mining_report(report, fmt)` ASCII.
- ENGINE NOTE (learned): a bare `ask` rule with no allow yields `deny` ("no allow match"), and the
  compound-resolution path collapses ask; deterministic `ask` verdicts are awkward to construct
  synthetically (real corpus allow-candidates were all deny-origin). So the ask->allow-candidate
  mapping is unit-tested via `_classify` directly, not via decide().
- Real smoke (this repo's transcript, 30d, min_occ=3): 49 allow-candidates -- top `cd` x259,
  `echo` x62, Read/Edit of project dirs (all deny under the repo's minimal config but constantly run).

Tests: +12 `test_tools_mining.py` (classify mappings, deny-but-ran/declined/denied/consistent,
grouping by exec-token + parent-dir, sort, min_occurrences, evaluate_added_allow_rule, render+invalid).
**Full suite 1075 OK, ruff clean.** NOT committed.

P2-C remaining: P2-C.2 = hierarchy migration (move a rule up a level), replay-gated -- NOT yet built.
Then P2-D families 3-4 (agent-judged), P2-E SKILL+CLI.

## Dup/drift audit (2026-06-28, Arnon requested) + fixes

FIXED (reimplementation drift, logic-level):
1. `rule_apply._read_raw_permissions` re-rolled the `if toml: tomllib.load else json.load` branch ->
   now calls the canonical cached `config.load_config_file(path, file_format)` (whose own docstring
   says it is "the single internal config-file loader" replacing exactly those per-site branches).
   Dropped now-unused `json`/`tomllib` imports.
2. Wrapper BUILD `f"{tool}({body})"` was duplicated 3x (config_access.with_layer_allow_replaced,
   redundancy._config_without_allow, rule_apply._wrap). Added `config.wrap_tool_pattern(tool, body)` --
   the public inverse of the existing `config._strip_tool_wrapper` -- and routed all three through it
   (`_wrap` removed). Single source of truth for the wrapper shape.
Full suite 1075 OK, ruff clean after both.

REPORTED, lower severity (constant duplication, low drift risk -- left for a later cleanup pass, told
Arnon):
3. `{"Read","Write","Edit"}` set declared in 4 places: hook.FILE_PATH_TOOLS (canonical core) +
   log_harvest._FILE_TOOLS + transcript_harvest._FILE_TOOLS + mining._FILE_TOOLS. Recommend one shared
   constant; not fixed now (importing hook into the pure parsers adds coupling; needs a light shared home).
4. Status vocabulary ("EXECUTED"/"REFUSED") as constants in transcript_harvest but string literals in
   replay + mining. Recommend a shared STATUS_* home (log_harvest, next to LogEntry). Not fixed now.

ACCEPTABLE (not drift):
5. Three ASCII renderers (security_audit.render, rule_apply.render_change_report, mining.render_mining_report)
   share scaffolding but are independent formats; Arnon earlier chose independent renderers. OK.
6. transcript_harvest._index_tool_results vs subagent.find_tool_results -- both index tool_results by id
   but return different things (is_error+text vs entry index) for different purposes. OK.
7. config_access ask-unwrap (`perm[len(prefix):-1]` with startswith/endswith) vs config._strip_tool_wrapper:
   config_access also filters by the specific tool, so partly justified; minor, noted.

Verified clean (NO dup): the synthetic-config rebuild is a single primitive (with_layer_allow_replaced;
redundancy delegates); jsonl parsing reuses subagent.parse_jsonl_lines; sort reuses rule_sort; writers
reuse migrate_permissions.

## Dup/drift audit FOLLOW-UP: constants consolidated (2026-06-28)

Findings #3 (FILE_TOOLS set x4) and #4 (status literals) now FIXED via new leaf module
`toolguard/constants.py` (imports nothing from toolguard -> no coupling):
- `GOVERNED_TOOLS = frozenset({Bash,Read,Write,Edit})`, `FILE_TOOLS = frozenset({Read,Write,Edit})`
  (immutable, per Arnon's "shared immutable set"), `STATUS_EXECUTED/REFUSED/ERROR/UNKNOWN`.
- `hook.FILE_PATH_TOOLS` kept as an ALIAS of `FILE_TOOLS` (test_hook + decision.py import that name; len/in
  still work on a frozenset). `log_harvest`/`transcript_harvest`/`mining` use `FILE_TOOLS` directly;
  `transcript_harvest`/`mining`/`replay` use the `STATUS_*` constants instead of literals.
- Deliberately NOT touched: `error_log.py` "ERROR" (a log-LEVEL label, different semantic domain) and
  mining `SIGNAL_*` (not duplicated). BDD refactor: NO test changes; full suite 1075 OK, ruff clean.

## Curated-tool short-list: best-guess (2026-06-28) -- FINAL list TBD from fuller transcript mining

Arnon: take this as the working guess; before the curated-tool advisor is actually built we will
mine the transcripts more completely (frequency-rank) for the FINAL development short-list. Evidence
this session (toolguard repo transcript): Bash 570 uses; top mined groups `cd` x259, `echo` x62, plus
`grep`, the `git` family, and `find` (both REFUSED entries were find). That maps onto:

- **Tier 1 (broad read-only -> codify allow, kill approval fatigue):** `git` (the anchor: rich stable
  read-only vs state-changing subcommand split), `ls`/`cat`/`head`/`tail`/`wc` (trapdoor-free read
  baseline -- but `sort -o`/`tee` write, so still per-flag), `grep`/`rg`/`ag`, `cd`/`pwd`/`echo`
  (trivially safe but DOMINATE the corpus).
- **Tier 2 (trapdoor cases -- most valuable for the AUDIT side, NOT broad-allow):** `find`
  (-exec/-execdir/-ok/-delete/-fprintf), `sed` (-i writes, GNU `e` execs), `awk` (system(), print>file).
- **Tier 3 (common but project-specific / exec-heavy -> lean ask + deny-completion):** runner/installer
  family `uv`/`pip`/`npm`/`pnpm`/`yarn`/`pytest`/`make`, interpreters `python`/`node` (-c/-e),
  `curl`/`wget`.

Starting set recommendation = **Tier 1 + `find`**. HARD caveat: "read-only" is per-(tool, FLAG), never
per-tool; the table must encode trapdoor flags as first-class. Final selection = frequency rank from
Arnon's real transcripts (the harvester now produces this), not this guess. See the curated-tool-advisor
design above (separate ticket; feeds both #3 maintenance-suggest and #6 audit).

## P2-C.2 STATUS: hierarchy migration DONE (2026-06-28) -- P2-C COMPLETE

New `toolguard/tools/hierarchy.py` (library-only). specificity: 0 = most specific (project), higher =
broader (user); most-specific-wins (verified empirically on synthetic layers).
- `HierarchyMigration(tool, list_type, pattern, from_provenance, to_provenance, rationale)`;
  `migrate_config(config, migration)` composes TWO `with_layer_allow_replaced` calls (remove from
  source, add to target). allow-only this slice.
- `evaluate_migration(config, migration, corpus) -> MigrationEffect`: replays before/after;
  `decision_neutral` = no corpus decision changed (safe for the CURRENT context). The genuine
  promotion effect -- broadening to OTHER contexts the broader layer governs -- is outside any single
  corpus and surfaced as a `scope_note` (promotion/demotion/same-level). Replay-gate CAUGHT the key
  hazard in test: promoting an allow PAST an intermediate-layer deny tightens the verdict
  (decision_neutral False, tightened_count 1).
- `find_cross_layer_redundancies(config, tool) -> [CrossLayerRedundancy]`: a more-specific allow rule
  normalised-EQUAL to a broader-layer rule is redundant (broader already covers it -> drop the specific
  copy, decision-neutral). The cross-layer counterpart redundancy.py deferred. Conservative (equal only;
  cross-layer glob subsumption deferred). Reuses `redundancy._normalised_body`.
- REUSE (clean, no rebuild): with_layer_allow_replaced, replay, per_layer_rules, _normalised_body.

Tests: +7 `test_tools_hierarchy.py` (migrate relocates; neutral promotion; non-neutral-past-deny caught;
demotion scope-note; cross-layer redundancy flagged/unique-not-flagged/direction). **Full suite 1082 OK,
ruff clean.** NOT committed.

NOTE: hierarchy migration produces proposals + verification; the FILE apply (remove from file A, add to
file B) is not built -- it composes two rule_apply-style edits; generalize rule_apply or add a thin
apply when P2-E wires it.

P2 remaining: P2-D families 3-4 (agent-judged multi-option broadening) -- mostly SKILL guidance over the
existing replay/probe machinery; P2-E maintenance SKILL.md + CLI (the user-facing wiring, dirty-tree
guard, self-permissioning). Plus the curated-tool advisor (separate ticket, transcript-evidence-driven).

## Migration risk -> AI-audit refinement + DOCS requirement (Arnon 2026-06-29)

**DOCS requirement (note for user-facing docs / P2-E + docs pass):** hierarchy migration can have
security-relevant interactions the DETERMINISTIC tool CANNOT fully analyze -- across SECTIONS
(allow vs deny vs ask) and across LAYERS. replay only proves current-corpus decision-neutrality; it
cannot see developer INTENT or cross-context effects. Example: a broad `git:*` allow plus a deny on a
specific op the dev reserves for themselves (e.g. `git push`, NOT a read/write boundary). Splitting the
allow and the deny across different layers may or may not defeat that intent. The AI-driven security
audit (#6) CAN flag this -- ESPECIALLY when instructed to focus on rules for the SAME command/command
family across sections and layers -- and leave the final call to the developer.

**NEW WORK this phase (P2-C addition): feed proposed-but-unimplemented migrations to the AI audit.**
- Python: `hierarchy.migration_effect_to_dict(effect)` -> JSON-able dict (tool, list_type, pattern,
  from_locus/to_locus, from/to specificity, decision_neutral, broadened/tightened/changed counts,
  scope_note, rationale). Structured so it can be passed as context.
- `security_audit`: new optional `--migrations PATH` (JSON list of those dicts); when given with
  `--with-context`, embed under `context["proposed_migrations"]` -- the concrete "passing" mechanism so
  the AI pass sees the migration analysis alongside the rule hierarchy in ONE context blob.
- security-audit SKILL.md: new Pass-2 section "Evaluating proposed (unimplemented) migrations" --
  instruct the AI to evaluate each migration's risk IF ENACTED IN FULL: focus on same-command/family
  rules across allow/deny/ask AND across layers; flag allow-broadening-past-a-deny, orphaned/split deny
  that may defeat intent (the git-push example), and cross-context broadening the replay can't see;
  emit severity + confidence; the deterministic `decision_neutral`/replay is current-corpus ONLY, NOT a
  safety proof -- this is exactly where AI judgement adds value; leave the final decision to the developer.
- Tests: serializer round-trip + audit `--migrations` embedding into context.

## Coverage snapshot (2026-06-29, before P2-C commit)
Ran tools/coverage_stdlib.py. NOTE: stdlib `trace` flags multi-line signature CONTINUATION lines as
uncovered (false positives) -> raw % understated. Genuine new-module coverage is solid; most real gaps:
transcript_harvest (_extract_text list branch + timestamp None/invalid) and consolidate
(_static_prefix_of branches, suffix handling). Fold top-ups into a PRE-PUSH coverage pass.

## DONE: migration -> AI-audit refinement (2026-06-29)

Implemented the "feed proposed-but-unimplemented migrations to the AI audit" refinement:
- `hierarchy.migration_effect_to_dict(effect)` -> JSON-able dict (tool/list_type/pattern, from/to
  locus + specificity, decision_neutral, broadened/tightened/changed counts, scope_note, rationale).
- `security_audit` CLI: new `--migrations PATH` (loads a JSON list; argparse-errors on bad file);
  embeds under `context["proposed_migrations"]` (works with or without `--with-context`; context
  created if needed). Reads a plain user JSON via json.load (NOT a config file -> load_config_file
  doesn't apply; not drift). Smoke + tests green end-to-end.
- security-audit SKILL.md Pass 2: new "### Proposed migrations -- assess the risk of enacting them"
  subsection + documented `proposed_migrations` in the context JSON shape. Instructs the AI to assess
  each migration AS IF ENACTED IN FULL; decision_neutral is NOT a safety proof; focus on same-command/
  family rules across BOTH sections (allow/deny/ask) and layers; flag allow-broadened-past-a-deny
  (the git-push reserved-op example), orphaned/split guards, cross-context broadening; severity +
  confidence; developer decides.
- Tests: +1 hierarchy (serializer round-trip JSON-able) +2 security_audit (--migrations embeds;
  bad file -> SystemExit). Full suite 1085 OK, ruff clean. NOT committed.

This closes the migration-risk item. P2-C (mining + hierarchy + this refinement) fully done.

## Project-root definition + migration safety gate (design, Arnon + Claude 2026-06-29)

Drove out of the featherhill dry run (need a project-agnostic-vs-specific rule classifier). DESIGN
agreed (no code yet; for the migration skill #2/#3, agnostic detector, and setup skill):

**Project root = deterministic primitive.** Already exists: `config.find_project_root(start_dir)`
walks up for nearest `pyproject.toml` OR `.git` and RAISES if neither. Reconcile to ONE primitive;
do NOT fork a second definition.
- **`.git` (VCS root) is the canonical BOUNDARY/safety anchor** for migration (language-agnostic,
  unambiguous; `pyproject.toml` can sit in a sub-package below the git root -> wrong boundary).
- **Grain = REPO, not package** for migration-to-user-level (monorepo = one project; conservative).
  Package-grain (pyproject/.claude) is out of scope.
- **No project marker -> REFUSE to migrate** by default (safe), but frame as an overridable default
  with clear language, not an absolute. Precedence: `.git`/VCS >> build manifests >> CLAUDE.md >> pwd.

**Necessary but NOT sufficient (key caveat):** knowing the root does not classify a rule as agnostic.
Featherhill proof: `curl localhost:8001`, `uv run uvicorn flowers.app.main:app`, `lsof -i :8001`,
`canopy`, `./bin/*` are project-specific yet reference NO path inside the root. Classifier needs TWO
clauses: (a) no path inside the project root AND (b) no project-specific TOKEN (ports, app-module
names, sibling-project abs paths, project-named binaries). **Default to SPECIFIC/don't-promote when
unsure** (allow-direction asymmetry: wrong-promote = silent hole; wrong-keep = mild friction).

**Ask-when-in-doubt, layered (Arnon):** the elegant framing -- git root OR explicit user answer is the
CORRECTNESS anchor; a configurable, DEFAULTED, explicitly-NON-AUTHORITATIVE indicator list is only a
CONVENIENCE to propose candidates / reduce prompts, so the list never has to be complete. Flow:
try `.git` -> else PROPOSE candidates from markers ("found .git at X, pyproject at Y -- which is your
root?", show the signal) -> else ASK for a path -> else REFUSE. Non-interactive: ask degrades to refuse.
- **Two distinct config concepts:** (a) the INDICATORS (how to detect; user-editable, incomplete,
  defaulted, proposed at install) vs (b) a RESOLVED-ROOT OVERRIDE (this IS my root) PERSISTED after the
  user answers so we don't re-ask every run.
- Default indicators (small, starting point, NOT exhaustive): `.git`/`.hg`/`.jj`, `pyproject.toml`,
  `package.json`, `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle`, `CMakeLists.txt`.

**Clarity is a HARD principle (Arnon):** recommendation text is the product. Deterministic core emits
STRUCTURED facts; skill renders with CALIBRATED language that never overstates ("no decision change in
your history; cannot verify other projects" NOT "safe"). Same principle applies to the disambiguation
prompt (show the signal). Note: `find_project_root` currently treats pyproject/.git as EQUAL (OR) and
RAISES rather than returning None -- making it git-primary + graceful-None for the gate is a small
deliberate change when we build it (design choice, not a bug).

### P2-E.1 STATUS: LANDED (2026-06-30, inline) -- project-root resolver

PREMISE CORRECTION (found via code-review-graph callers_of): there are TWO existing finders, not one --
`config.find_project_root` (package-grain, RAISES; used by config DISCOVERY: discover_config_files,
_discover_levels, Configuration.project_root, log_writer, migrate_permissions) and
`env_config.find_project_root` (nearest .git/pyproject or None, for .env loading). BOTH are
nearest-marker finders; NEITHER is repo-grain/git-primary/structured. Mutating config.find_project_root
(as the old note implied) would have broken config discovery's package grain. So I did NOT touch either.

BUILT NEW pure primitive `toolguard/tools/project_root.py`: `resolve_project_root(start_dir, *,
override=None, indicators=DEFAULT_INDICATORS) -> ProjectRootResolution`. Status enum RESOLVED_OVERRIDE /
RESOLVED_VCS / AMBIGUOUS / NONE; `.safe_to_migrate` = VCS-or-override only. Order: override > nearest VCS
(repo boundary) > non-VCS build-marker candidates (AMBIGUOUS, for skill to ask) > NONE (refuse).
`indicators` (defaulted, non-authoritative) + `override` (persisted resolved-root) are PARAMETERS -- the
WHERE-persisted config schema is deferred to the skill/CLI wiring (keeps the primitive pure/testable).
Calibrated `reason` strings never say "safe". 6 BDD tests (test_tools_project_root.py). Suite 1095 OK,
ruff clean. The deterministic core never prompts; ask/refuse is the skill's job (per spec).

### P2-E.2 STATUS: LANDED (2026-06-30, inline) -- maintenance aggregator

NEW `toolguard/tools/maintenance.py` (mirrors security_audit.py shape): `ToolMaintenance` +
`MaintenanceReport` dataclasses; `run_maintenance(config, tools=None, corpus=None) -> MaintenanceReport`
COMPOSES (no reimpl) find_redundancy + propose_consolidations + propose_broadening_consolidations +
find_cross_layer_redundancies per tool, plus config-wide mine_rule_candidates; `render(report, fmt)`
SUMMARY view reusing mining.render_mining_report. 5 BDD tests. Suite 1100 OK, ruff clean. DEFERRED to
later P2-E sub-slices: CLI main(), verbose paste-ready per-file recommendation + 3 application modes,
#NOSECURITY, dirty-tree guard, self-permissioning, wiring resolve_project_root into the migration gate.

### FINDER CLEANUP: DONE (2026-06-30, Arnon asked to do it now). Extracted the shared bounded walk-up into
leaf module `toolguard/path_utils.py` (`iter_dirs_upward`, `find_nearest_marker` -- stdlib only, no
cycle risk). `config.find_project_root` (raises), `env_config.find_project_root` (None), and
`tools/project_root.py` (structured) now all DELEGATE to it, each keeping its own contract + grain. No
behavior change (suite 1095 OK, ruff clean; config-discovery + env_config finder tests green).

## Review of P2-C.2 + featherhill dry run (Arnon 2026-06-29): fixes done + DEFERRED requirements

**DONE NOW (in this slice's commit):**
- Simplified `hierarchy.find_cross_layer_redundancies` (was cognitive-complexity-borderline triple
  nest) -> coverage index `key -> [(specificity, provenance)]` + `_nearest_broader_cover` helper; one
  finding per redundant pattern citing the nearest broader cover. Tests green.
- security-audit SKILL.md: (a) sharpened the proposed-migrations section -- heading now "ONLY when
  context.proposed_migrations is present -- otherwise skip entirely", explicit "SKIP if absent", and
  "NEVER propose/invent migrations yourself; only risk-assess moves passed via --migrations". (b) NEW
  "### Remediations -- offer a concrete, usable fix" subsection: exhaustive-not-illustrative, simple>clever
  (anchor regexes, no giant regexes), remediation MAY span multiple rules AND sections, deny by file
  TOKEN not per-reader, prefer structurally-correct layer (file-tool deny for Read/Edit/Write but Bash
  readers still need a Bash deny), arbitrary-exec -> DELETE. + 4 few-shot examples (inline replacement /
  rule-combination across sections / delete / anchor-unanchored).

**DEFERRED to P2-E / an audit-enhancement slice (Arnon agreed all):**
- **Maintenance recommendation report** = the "just right" summary PLUS VERBATIM per-file config
  sections (use `rule_apply.apply_proposals(dry_run=True)` -- already yields exact per-file diff/new
  text). Three APPLICATION MODES the user picks: (i) user edits themselves from the recommendation
  (preferred -- they know their config), (ii) agent applies all in bulk, (iii) agent applies with
  case-by-case approval, GROUPED by interacting/very-similar rules (same command family; a rule + the
  deny it interacts with). Grouping comes from the migration-risk/interaction analysis.
- **Audit must REMEDIATE (structured + audience-aware):** evolve `RankedFinding.remediation` from a
  string into a STRUCTURED action (remove|replace|narrow|move + target + replacement rule(s)) so the
  maintenance skill can post-process without NLP. Audit needs a HUMAN vs SKILL audience mode (a
  `--for-skill`/agent flag or the maintenance skill telling it). OPEN QUESTION (Arnon on the fence):
  one report or two when invoked by the maintenance skill -- Arnon leans ONE (the human wants to read
  it too); likely resolution = ONE human-readable report PLUS structured remediation data the skill
  consumes (in JSON / sidecar), not two prose reports.
- **`#NOSECURITY` comment tag (bandit `# nosec` precedent):** (1) suppress = ACKNOWLEDGE not hide
  (Pass 1 still reports it, marked "acknowledged (#NOSECURITY: <reason>)", de-prioritized -- never
  silently drop, per toolguard transparency). (2) free-form reason scopes the exclusion (about .env,
  not unrelated issues) AND signals project-local -> a #NOSECURITY rule is therefore NOT a migration
  candidate (blessed HERE, not everywhere). (3) ENABLING Python work: `config_access.audit_context`
  must EXPOSE per-rule comments (leading + inline) -- `rule_sort` already parses them; the context
  currently throws them away. That comment-exposure is the prerequisite that unlocks the feature.

## >>> RESUME POINT (session end 2026-06-29) <<<

COMMITTED, not pushed. P2-A, P2-B, P2-C (mining + hierarchy + migration->AI-audit refinement) all
landed. Deterministic maintenance core is essentially complete:
config_access/decision/replay/log_harvest/transcript_harvest/redundancy/danger/takeover_audit/
sorters(+rule_sort)/consolidate/rule_apply/mining/hierarchy + security_audit (+ --migrations) +
constants. Full suite 1085 OK, ruff clean. Repo intentionally still "dirty"/dogfood per
[[too15-completion-gate]] (temp skill symlinks NOT yet removed; do at ticket close).

NEXT (pick up here):
- **P2-D** -- agent-judged families 3-4 (multi-option broadening); mostly SKILL guidance over existing
  replay/probe machinery, little new Python.
- **P2-E** -- maintenance SKILL.md + CLI. This is where the big DEFERRED items land (see the three
  "DEFERRED" blocks above): verbatim per-file recommendation sections via apply_proposals(dry_run);
  3 application modes (self-edit / bulk / case-by-case grouped by interaction); structured +
  audience-aware audit remediations (RankedFinding.remediation -> typed; human-vs-skill mode; ONE
  report + structured sidecar per Arnon's lean); #NOSECURITY (acknowledge-not-hide; scoped reason
  blocks migration; PREREQ = expose per-rule comments in audit_context); self-permissioning; dirty-tree
  guard; project-root resolution (git-primary, configurable indicators, ask-then-refuse -- see design
  block above); glob-defect docs.
- Pre-PUSH (per project CLAUDE.md): coverage top-ups (transcript_harvest/_extract_text + consolidate
  static-subsumption branches), version bump in pyproject.toml, release notes, glob-defect user docs.
- Curated-tool advisor = separate ticket (transcript-evidence-driven; short-list best-guess = Tier 1 +
  find, recorded above).

## P2-D design (2026-06-29) -- agent-judged broadening, "thin enumerator + evidence" (Arnon chose)

Seam decision (AskUserQuestion): add a SMALL deterministic enumerator that proposes broadenings and
attaches CONCRETE replay evidence; the JUDGMENT stays in the maintenance SKILL (P2-E). Not pure-SKILL,
not deferred. Matches the deterministic-core/agent-judgment seam.

NEW in `toolguard/tools/consolidate.py` (extend, do NOT fork the module):
- `BroadeningProposal` dataclass (distinct from strict `ConsolidationProposal`, so the strict
  equivalence contract stays pristine). Fields: kind ('lossy-alternation' | 'prefix-broadening'),
  tool, list_type, layer_provenance, removed_patterns: Tuple[str,...], added_pattern: str,
  rationale, plus STRUCTURED EVIDENCE: newly_admitted_commands: Tuple[str,...] (corpus commands that
  flip toward allow under B), collides_with_guard: Tuple[str,...] (the security-critical SUBSET whose
  decision_a was ask/deny and decision_b is allow -- the alembic-landmine surface), and
  probe_admitted_surface: Tuple[str,...] (near-miss probe commands the broader rule now admits but the
  originals did not).
- `propose_broadening_consolidations(config, tool, corpus) -> List[BroadeningProposal]`. corpus is
  REQUIRED here (evidence is the point; with no corpus, newly_admitted is probe-only).
- Family-3 enumeration = the LOSSY counterpart of `_find_literal_alternations`: same grouping
  (token-identical except one slot) BUT also propose the broader `cmd :*`-style merge (drop the varying
  slot entirely, e.g. `git diff:*`+`git status:*` -> `git :*`) AND keep alternations that the strict
  gate REJECTED because they broaden. Prefix-broadening: collapse a set of `git <sub>:*` to `git :*`
  when a common static prefix exists.
- Evidence extraction: build config_b via `with_layer_allow_replaced` (REUSE), `replay(corpus, A, B)`
  (REUSE), then newly_admitted = [d.entry.command for d in diff.broadened()]; collides_with_guard =
  the subset where d.decision_a.verdict in {ask,deny}. probe surface from a broader-near-miss generator.
- NO auto-reject for broadening (that's the whole point) -- but DO surface collides_with_guard
  prominently; the SKILL's rubric (P2-E) + security-audit lens decides. Strict families 1-2 unchanged.

REUSE MAP (anti-drift -- these EXIST, do not rebuild): `_split_default_body`, `_is_literal_token`,
`parse_pattern`(patterns), `per_layer_rules`/`with_layer_allow_replaced`(config_access),
`replay`+`ReplayDiff.broadened()`+`EntryDiff(entry,decision_a,decision_b,classification)`(replay),
`decide`(decision), `_build_alternation_regex` for the alternation case.

SUCCESS CRITERIA (BDD unittest, suite stays green): (1) git-family prefix-broadening emits a
BroadeningProposal with newly_admitted including a git subcommand NOT in the originals; (2) the alembic
case emits a proposal whose collides_with_guard names the alembic command that was ask->allow (surfaced,
NOT silently dropped); (3) a no-corpus call yields probe-only evidence (empty newly_admitted, non-empty
probe_admitted_surface); (4) strict `propose_consolidations` output UNCHANGED (no regression).

### P2-D STATUS: LANDED (2026-06-30, inline -- feature-coder hit monthly spend limit again)

Implemented in `toolguard/tools/consolidate.py`: `BroadeningProposal` dataclass +
`propose_broadening_consolidations(config, tool, corpus=None)` + helpers
`_find_prefix_broadenings`, `_overlapping_guard_rules`, `_default_prefix_tokens`,
`_prefixes_overlap`, `_broadening_probe_surface`. 4 BDD tests in test_tools_consolidate.py
(TestPrefixBroadening). Full suite 1089 OK, ruff clean. Strict family-1/2 path unchanged
(regression test green). Pre-push: top up coverage on defensive branches
(`_default_prefix_tokens` None path, dedup `seen`, `len(finals)<2` skip).

### P2-D SEMANTIC DISCOVERY (2026-06-30) -- collides reframed; new clarity requirement

Probed toolguard's REAL within-layer resolution while building P2-D:
- **Deny always wins** -- even a MORE-specific broadened allow loses to a broader deny in the same
  layer (`allow "uv run alembic :*"` vs `deny "uv run:*"` -> deny).
- **Ask collapses** -- a broad ask with no matching allow resolves to deny with provenance=None
  (compound ask-collapse). For ask to WIN (prov set) it must out-specific every matching allow, which a
  broadening (which only lowers allow specificity) can never achieve.
- => a within-layer broadening can essentially NEVER flip an explicitly-decided ask/deny command to
  allow in-context. So the verdict-based `collides_with_guard` would be a permanently-empty dead field.

DECISION (Arnon, option 1): replace `collides_with_guard` with **`overlaps_guard_rules`** -- the
same-layer ask/deny rule bodies whose command-space TEXTUALLY overlaps the broadened pattern (tested in
isolation, ignoring precedence; for DEFAULT patterns = one cmd-prefix is a prefix of the other). Honest
framing: "protected in-context today by resolution, but FRAGILE -- the protection is load-bearing and
evaporates under hierarchy migration (the featherhill .env-deny-left-behind class)." newly_admitted +
probe_admitted_surface unchanged. Criterion 2 reframed accordingly (overlaps_guard_rules names the
overlapping deny/ask body, not a punched-through command).

NEW REQUIREMENT (Arnon) -- **rule-interaction CLARITY analyzer** (its own slice, call it P2-F /
audit-enhancement; feeds BOTH security audit #6 and maintenance #3, shared analyzer like the
curated-tool table):
- toolguard's within-FILE resolution is complex enough that even an expert can't eyeball it (deny-
  always-wins, ask-collapse, specific-allow-beats-broad-ask-but-not-deny, most-specific-LAYER-wins).
  A "correct but inscrutable" consolidation/remediation is a latent bug. Clarity becomes a first-class
  audit dimension, not just security.
- Detect a FINITE CURATED CATALOG of confusing interactions (a lint rule set, NOT "confusing" in the
  abstract): deny silently shadows an overlapping allow; broad ask shadowed by specific allow (ask-
  collapse); same command across multiple sections same file; a rule whose effect depends on another
  layer. Each = detector + ONE canonical explanation + (where applicable) a canonical clearer form.
- Two output modes: **rewrite** to a clearer EQUIVALENT only when one provably exists (replay-equal);
  otherwise **explain + annotate** (inherent semantics cannot be rewritten away -- do not pretend).
- When a recommended result (incl. multi-rule/multi-section remediations) could be confusing, the
  explicit paste-ready proposal must carry GENERATED COMMENTS noting each rule's interaction (overrides
  X in another section / coupled to Y / overrides a broader-layer rule). Comments carry a stable marker
  (e.g. `# toolguard:`) so re-apply REPLACES (never accretes) them and never clobbers human comments --
  rides the existing comment-preserving apply machinery + couples with #NOSECURITY.
