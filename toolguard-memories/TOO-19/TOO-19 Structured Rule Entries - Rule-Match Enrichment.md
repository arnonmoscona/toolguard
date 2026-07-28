---
title: TOO-19 Structured Rule Entries / Rule-Match Enrichment
type: note
permalink: toolguard/too-19/too-19-structured-rule-entries-rule-match-enrichment
tags:
- task-memory
- TOO-19
---

## Ticket (as filed)

Raw idea for discussion. Extend allow/deny/ask entries from bare pattern strings to an
optional structured form so a matching rule can inject `additionalContext` into Claude's
context via the PreToolUse hook response, reinforcing user guidance (e.g. "prefer `ag`
over `grep` in this codebase") that CLAUDE.md alone doesn't reliably enforce. Proposed
syntax sketch: `{rule="...", additionalContext="...", alwaysInject=true}` alongside plain
string entries in the same array. `alwaysInject` was proposed to control whether context
fires even when the rule wasn't the deciding match (compound commands can have several
matches). Also proposed for deny (offer a better option on refusal).

## Feasibility research (done this session)

- Verified against current Claude Code hooks docs (via claude-code-guide subagent, not
  assumed): `PreToolUse` hookSpecificOutput DOES support `additionalContext` today,
  fires regardless of the `permissionDecision` value (allow/ask/deny/defer). Capped at
  ~10,000 chars, truncated beyond that. This matters because the ticket's motivating case
  wants the nudge to fire on an ALLOW decision, where `permissionDecisionReason` is not
  something Claude sees (that's only surfaced on ask/deny) -- so `additionalContext` is
  the right mechanism, not a repurposed reason string. No redesign needed; premise holds.

## Critical-thinking findings (code-grounded, this session)

1. **Bigger change than it looks.** Every allow/deny/ask entry today is a bare `str`,
   baked into a `(decision, reason)` 2-tuple pipeline spanning `config.py` ->
   `permissions.py` -> `resolve.py` -> `compound.py` -> `hook.py`. Adding a structured
   entry + a context-accumulation channel touches all of these.
2. **Pre-existing silent-drop bug, independent of this ticket but activated by it.**
   `config.py` (`permission_layers`, hard-deny extraction) and `config_validation.py`
   filter every permission-list entry with `isinstance(perm, str)` and silently skip
   anything else -- zero validation warning today. Once a structured (non-string) form is
   legal, any typo/partial-rollout/version-mismatch scenario would make rules --
   including DENY rules -- silently vanish with no error surfaced anywhere.
3. **Compound-command accumulation is non-trivial.** `compound.py::_combine_strictest`
   currently picks ONE winning `(decision, reason)` (deny > ask > allow priority); for the
   all-allow case it already synthesizes a combined reason listing every leaf's matched
   pattern. Attaching context per rule requires this combinator to carry structured match
   info, not just formatted strings.
4. **File-path tools (Read/Write/Edit) already track the winning match's `Provenance`**
   via `FileResolution.provenance` in `resolve_file_path_permission_detailed` -- a decent
   existing hook point for "final decision maker" context. Bash's path
   (`resolve_bash_permission_detailed` + `compound.py`) does NOT carry this structured
   winning-match info yet, only formatted reason strings -- more plumbing needed there
   than on the file-path side.
5. **Native settings.json compatibility risk.** Toolguard's existing extended syntax
   (`[regex]`, `[glob]` prefixes) already only works in toolguard's own config files, not
   native Claude `settings.json`. Same constraint should apply to the structured-entry
   form to avoid corrupting/confusing Claude Code's own settings parsing.

## Decisions (Arnon, this session, 2026-07-24)

- **Silent-drop validation gap: bundle the fix into TOO-19** (not a separate ticket).
  Structured entries make an existing latent gap actively dangerous, so it belongs in
  scope here.
- **`alwaysInject` is DROPPED for this scope.** Not enough use case yet to justify the
  cross-layer/cross-leaf accumulation complexity and risk. Only the FINAL DECISION MAKER
  match's context fires -- no accumulation from non-deciding matches.
- **Plural-accumulation nuance RESOLVED (2026-07-24, follow-up):** for an all-allow
  COMPOUND command with multiple sub-commands each allowed by a DIFFERENT rule, each
  rule's `additionalContext` IS accumulated (each was genuinely the final decision maker
  for its own leaf -- this is plain multi-match accumulation, not the alwaysInject
  cross-layer/losing-match scenario, which stays dropped). Only the all-allow case can
  produce plural decisive matches; deny/ask always resolve to one strictest-wins leaf, so
  this accumulation path is allow-only.
  - **Formatting:** one paragraph per contributing rule's `additionalContext`.
  - **Cap:** 500 words total across all accumulated paragraphs (an internal toolguard
    cap, well inside the platform's own ~10,000-char `additionalContext` ceiling --
    chosen for readability, not to dodge truncation).
  - **Overflow policy:** if including a paragraph would push the total over 500 words,
    drop that paragraph WHOLE -- never truncate/chop a paragraph mid-sentence to fit.
    Which paragraph(s) get dropped when over budget (first-wins vs last-wins) is
    explicitly Arnon's-call-doesn't-matter ("It's a corner case") -- implementation may
    pick either, no need to special-case ordering.
- **Structured-entry syntax restricted to toolguard's own config files** (toolguard_hook
  .toml/json), never native Claude `settings.json`. Recommended option, accepted.
- **Scope across tools: "ideally all governed tools"** (Bash/Read/Write/Edit), with Bash
  as the tool Arnon actually cares about for this feature -- fall back to Bash-only if
  generalizing proves substantially more complex. My follow-up research: the PreToolUse
  hook's `additionalContext` support is uniform across tool_name, not Bash-specific, so
  there's no hook-level blocker to generalizing. The added cost is internal: toolguard
  already has two parallel resolution paths (`resolve_bash_permission_detailed` via
  `compound.py`, and `resolve_file_path_permission_detailed` for Read/Write/Edit) that
  would each need the structured-entry plumbing -- not a per-tool multiplication, just
  two paths instead of one. File-path path is closer to ready (already tracks winning
  `Provenance`); Bash path needs more work (compound.py currently only threads formatted
  strings, not structured match info).

## Additional notes from Arnon (mid-session, not yet reflected in a formal decision)

- **This "rule enrichment" mechanism will be reused by several other tickets** (e.g. the
  auto-mode per-rule flag noted in
  [[project_automode_aware_toolguard_ticket_draft]] sub-part 3, which explicitly said it
  would piggyback on TOO-19's structured-entry mechanism as a sibling field rather than a
  parallel one). Implication: design the schema as a general-purpose "structured rule
  entry" extension point, not an additionalContext-specific one-off -- future tickets add
  sibling fields to the same object shape.
- **Naming is open.** Arnon is considering `match` instead of `rule` as the pattern-key
  name in the structured entry (e.g. `{match="...", additionalContext="..."}`). Not
  decided -- flag as an open naming question when the ticket is refined further.

## Additional notes from Arnon (this session, follow-up round)

- **Maintenance and security-audit skills will be impacted.** Confirmed by grep, not
  hypothetical: `toolguard/tools/config_access.py::per_layer_rules()` (built on
  `config.py`'s `ToolPatternLayer`) is the shared chokepoint both skills read permission
  lists through. Downstream, at least these tool modules assume bare-string entries
  directly: `consolidate.py`, `clarity.py`, `redundancy.py`, `rule_apply.py`,
  `takeover_audit.py`, `installer.py`, `config_access.py` itself. `maintenance.py` pulls
  in the first four (consolidate/clarity/redundancy/rule_apply); `security_audit.py`
  pulls in `clarity.py` + `takeover_audit.py`. Without centralization, structured
  entries would either crash these tools or (worse, for security_audit) be silently
  skipped/under-analyzed.
- **Decision: do a centralizing refactor FIRST, as an initial phase before the
  additionalContext feature itself.** Rationale (Arnon): the widespread
  `isinstance(perm, str)` assumption scattered across ~9 call sites (see prior section)
  is exactly the kind of drift risk that should be addressed head-on with a single
  accessor, not patched N times. Mirrors this project's existing PEG-grammar-first
  phase-separation discipline (structural/schema change reviewed in isolation, then
  feature logic on top) -- same philosophy applied to the config-entry schema instead of
  the bash grammar.
  - Proposed shape (not yet detailed-designed): a normalized entry type living in/near
    `ToolPatternLayer` (`config.py`) and `LayerRules`/`per_layer_rules()`
    (`config_access.py`) -- the two existing chokepoints everything already reads
    through. Give it a `.pattern` (str) accessor so the ~9 read-only consumers found so
    far need little or no change. The write paths (`rule_apply.py`,
    `with_layer_rules_replaced`/`with_layer_allow_replaced` in `config_access.py`) are
    the ones that actually need new logic, to round-trip enrichment fields (e.g.
    `additionalContext`) instead of silently stripping them when maintenance tooling
    rewrites a rule list.
  - This refactor is now planned as **Phase 0 / prerequisite** of the eventual TOO-19
    implementation plan, done and reviewed before the additionalContext feature logic
    starts (consistent with the earlier decision to bundle the silent-drop validation
    fix into TOO-19 as well -- both are schema-hygiene prerequisites, not separate
    tickets).

## Additional decisions (2026-07-24, third round -- "any objections before planning")

New consumers found (beyond the ~7 tools/*.py already listed):
- **`toolguard/rule_sort.py`** (powers the `/sort-permissions` skill) does its OWN
  regex/line-based parsing of raw TOML text, entirely separate from `config.py`'s
  tomllib-based parse -- exists specifically because tomllib strips comments and this
  tool round-trips comment-preserving sort. Assumes one plain-string pattern per line
  today. Needs a real design decision (resolved below), not just Phase-0 plumbing.
- **`toolguard/log_writer.py::log_command`** already has a `matched_rule` audit field.

Decisions:
- **ask list gets the structured-entry syntax too** (all three of allow/deny/ask,
  uniform object shape, no special-casing).
- **log_writer.py WILL be extended** to record whether/what `additionalContext` was
  injected, alongside the existing `matched_rule` field -- for post-hoc debuggability
  ("why did Claude get this nudge").
- **Same-rule-matches-multiple-leaves dedup** (compound command matches the same
  enriched rule on 2+ sub-commands): dedupe by identical additionalContext text before
  accumulating paragraphs -- simple, no rule-identity tracking needed.
- **Consolidation/redundancy tooling requirement:** `consolidate.py`/`redundancy.py`
  must not silently merge two pattern-identical entries that differ in
  `additionalContext` (or one has it, one doesn't) without accounting for the context
  loss. Flows out of the Phase 0 refactor, stated explicitly as a requirement on it.
- **rule_sort.py / sort-permissions: RESOLVED, no PEG TOML parser, no single-line
  mandate.** Considered and rejected:
  - `tomlkit` (or similar comment-preserving TOML library) -- rejected per Arnon: zero
    runtime dependencies is a deliberate security property of this project (matches the
    project-wide stated policy in CLAUDE.md, not just the PreToolUse hot path), so no
    new third-party dependency for this.
  - A dedicated PEG grammar + canopy-generated TOML sub-parser (mirroring the Bash
    grammar pattern) -- considered, would work, but judged more engineering investment
    than justified for what's actually a bounded problem. Deferred/not needed given the
    hybrid approach below; could be revisited if the hybrid proves insufficient.
  - Mandating single-line inline-table formatting for structured entries (so the
    existing one-line-per-rule invariant needs no change) -- rejected by Arnon on
    readability grounds (long additionalContext text on one line is hard for a human to
    read/edit), even though `\n` escapes would have made it technically viable.
  - **Adopted hybrid approach:** (1) Relax the one-pattern-per-line invariant to
    "each new top-level array entry starts on a new line; multi-line spans are legal
    ONLY for structured `{...}` entries" (easy to validate, keeps plain-string rules
    exactly as readable/diffable as today). (2) Detect entry boundaries with a single
    linear scan tracking quote-state (inside `"..."`/`'...'`?) and brace-depth (inside
    `{...}`?), splitting only on top-level commas -- tool-name-agnostic (doesn't need to
    enumerate `Bash(`/`Read(`/etc., which would be brittle against
    `additional_supported_tools`), same complexity class as the existing parser, not a
    grammar. (3) For each chunk: comment/blank-line preservation stays exactly as it
    works today (text-span based, unaffected). For VALUE extraction (the sort key): if
    the chunk starts with `{`, wrap it (`x = [ <chunk> ]`) and parse with stdlib
    `tomllib.loads` to get the real parsed dict back correctly, instead of hand-rolled
    regex; plain-string chunks can use the same trick for consistency, incidentally
    fixing an existing fragility (today's double/single-quote escaping regex is already
    somewhat fragile per its own docstring caveats). No new grammar, no new dependency,
    no readability sacrifice.

## Status (HISTORICAL -- as of 2026-07-24)

> Superseded. For the real current status jump to **"Phase 0 COMPLETE (2026-07-26) --
> final state"** below: Phase 0 is implemented and green, Phase 1 is unblocked and not
> started. The two "still open" questions at the end of this section were both resolved --
> the naming is **`match`** (`PATTERN_KEY = "match"` in `rule_entry.py`), and the entry
> type shipped as the frozen `RuleEntry` dataclass. The multi-line design mentioned here
> was reversed; entries are single-line only.

Still at "raw idea for discussion" stage -- no implementation started, though the design
has converged substantially over three Q&A rounds this session. Emerging shape of the
plan:
- **Phase 0:** centralized structured-entry accessor refactor in `config.py`
  (`ToolPatternLayer`) + `config_access.py` (`LayerRules`/`per_layer_rules()`) -- fixes
  the silent-drop validation bug as a side effect, touches ~9 downstream consumers
  including maintenance/security-audit tooling (consolidate/clarity/redundancy/
  rule_apply/takeover_audit/installer), plus the `rule_sort.py` hybrid rewrite
  (multi-line-aware boundary scan + tomllib-per-chunk value extraction), plus
  `log_writer.py` audit-field extension.
- **Phase 1:** the `additionalContext` feature itself on top of the new schema --
  object-form entries in allow/deny/ask across toolguard-only config files, targeting
  all governed tools (Bash + Read/Write/Edit) if generalizing doesn't prove too costly,
  final-decision-maker-only injection (no alwaysInject), plural accumulation for
  all-allow compounds (paragraph-per-rule, 500-word cap, drop-whole-paragraph overflow,
  dedupe identical text across leaves).

Still open: `rule` vs `match` naming, and the precise field-level shape of the
centralized entry type/accessor API (not yet detailed-designed). Next step: implementation
plan.

## Implementation plan (2026-07-24)

Full Phase 0a/0b implementation plan (7 + 6 TDD increments) written to
[[TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing)]]. ~~Status:
DRAFT, awaiting Arnon's review -- not yet approved, no implementation started.~~
**Superseded: approved and fully implemented 2026-07-25/26.**

The rest of the implementation (the actual `additionalContext` feature) is planned
separately in [[TOO-19 Phase 1 Implementation Plan (additionalContext Feature)]], still
DRAFT (and carrying corrections -- see its own banner), now unblocked since Phase 0 has
landed. That plan also surfaced a gap in Phase
0a as drafted: it doesn't yet gate structured-entry parsing on `layer.is_native`, so the
toolguard-only restriction isn't actually enforced yet -- RESOLVED: folded into Phase 0a
(`normalize_entry` takes `is_native`), not left as a Phase 1 pre-step.

### Phase 0 plan revision 2 (2026-07-25)

Reviewed by Opus 5 against the actual code; all findings accepted by Arnon and folded into
the Phase 0 plan. Headline: the original draft analyzed the READ paths thoroughly and the
WRITE paths barely at all, hiding two confirmed defects.

- **W1 (high):** `Configuration.toolguard_permissions()` (`config.py:1644`) is a THIRD
  silent-drop site the draft missed. Chain ends in `reassemble_permissions_section`
  emitting only the patterns it was handed, so a structured entry is **deleted from the
  user's config file** by migration -- and `auto_migrate.py:198` runs that unattended.
- **W2 (medium):** `rule_apply` preserves dict entries into the write payload, which then
  reach `get_tool_priority` -> `tool_priorities.get(dict)` ->
  `TypeError: unhashable type: 'dict'`. The maintenance skill crashes on the first rule
  edit to a file holding a structured entry.
- Original increment 7 (`config_divergence.py`) was **misdiagnosed** -- it already uses the
  centralized accessor, no crash reachable; rescoped to a semantics regression guard.
- Fix shape for both: widen the write payload ONCE from `Dict[str, List[str]]` to
  `Dict[str, List[RuleEntry]]` and emit via `entry.to_source()` -- one uniform type, fewer
  branches than today's implicit str-or-dict ambiguity.

Other decisions taken at this review:
- **Flat-hashable-forever constraint DROPPED.** `metadata` stays a plain Mapping;
  hashability comes from an explicit `identity()` instead. Rationale: the original
  constraint bought a `set()` convenience at the price of permanently forbidding a
  list-valued or table-valued enrichment field in a mechanism explicitly designed as a
  general extension point for later tickets.
- **Parser split in two:** `normalize_entry(raw, is_native)` (shape only, tool-agnostic,
  wrapper-INTACT) + `entries_for_tool(entries, tool)` (scoping). `RuleEntry.pattern` is
  wrapper-intact; only `permission_layers()` strips, at its own call site.
- **"Same rule" deliberately means three different things** -- `.pattern` for
  sorting and for divergence/migration, `identity()` for exact-duplicate detection,
  `merge_entries()` for consolidation. Documented so nobody later "fixes" the apparent
  inconsistency.
- **Same-pattern merge rules specified by Arnon (2026-07-25),** superseding plain
  `identity()` dedup: (1) bare string vs structured -> DROP the bare string, the structured
  entry is the intended rule and the bare one adds nothing; (2) multiple structured entries
  whose metadata is compatible (overlapping keys agree, rest disjoint) -> trivial union
  merge, no duplicates, no user interaction; (3) contradiction (same key, different value)
  -> keep separate, alert the user, optionally annotate the file with a comment marking the
  confusion. Only case 3 needs attention, which is what stops this becoming an interactive
  burden in the maintenance skill. Also narrows the `rule_apply` guard to fire on case 3
  only, not on every metadata-carrying entry.
- **hard_deny enrichment is meaningful** (Arnon) -- a hard deny is exactly where an
  `additionalContext` earns its keep: restate the CLAUDE.md directive being violated and
  offer a concrete alternative.
- **JSON configs added to scope** but cheap: no comments to preserve, stdlib `json`
  round-trips the object form natively.
- **Review protocol:** inter-increment reviews by the main agent or an Opus subagent;
  Arnon reviews only between phases.
- **The rules-directory fix is increment 0** (first), and the XDG-wins precedence question
  is settled.
- **`ruff format` rule CORRECTED (2026-07-25).** Arnon challenged the "never run ruff
  format here" claim; verified empirically and the old rule was wrong on two of three
  counts -- no quote churn (codebase is already double-quoted), and
  `except (A, B):` -> `except A, B:` is valid under PEP 758 on this 3.14 project, not
  corruption. Real issue is only diff pollution: 56/117 files have drifted from ruff's
  defaults (line-wrapping at 88), so a repo-wide format would bury this ticket's diff.
  Rule for TOO-19: format TOUCHED FILES ONLY, `ruff check` clean, no repo-wide format.
  Adding `[tool.ruff] line-length = 88` + pinned ruff + one intentional format commit is a
  worthwhile SEPARATE task, out of scope here. Memory corrected in
  [[project_toolguard_dev_tooling]].

## Phase 0 COMPLETE (2026-07-26) -- final state

All Phase 0a increments (0-9) and Phase 0b increments (1-7) are landed.
**1691 tests green**, `ruff check` clean, architecture tests green.
Nothing committed -- all changes are in the working tree for review.

### The single-line decision (Arnon, 2026-07-26) -- supersedes the plan

The plan listed "mandating single-line structured entries" under REJECTED
alternatives, on readability grounds. **That framing was wrong**: it is not a style
preference but a TOML 1.0 format requirement. Inline tables must be on one line;
stdlib `tomllib` implements TOML 1.0; toolguard's loader uses `tomllib`.

Measured impact of a multi-line entry before the correction:

```
config WITH a multi-line structured entry:  layers=0, deny=[], hard_deny=[]
same file, entry on ONE line:               layers=1, deny=[...], hard_deny=[...]
```

One formatting choice silently disabled EVERY rule in the file, including
`hard_deny`, with only a stderr warning. Phase 0b had built multi-line chunk
support the loader could never read, while sort/annotate happily round-tripped it
-- making the format look supported while enforcement was dead.

Arnon's ruling: *"TOML conformance and not breaking the builtin toml library is a
hard requirement. If that means we have to do one line per rule then it's what it
is. I accept the limitation despite its readability issues. I'm not going to try
and work around that."*

Corrective change applied: `_flatten_inline_table` (the newline-collapsing
workaround) deleted; `tomllib` is now the sole arbiter of validity; a specific
diagnostic replaced the cryptic parse error:

> structured rule entry starting at line 8 spans multiple physical lines, which is
> not valid TOML 1.0 (an inline table must be written on a single line). Rewrite it
> as one line, e.g. '{ match = "...", additionalContext = "..." }'.

The chunk scanner (`split_array_elements`) was KEPT -- it is now a detection
mechanism, and it correctly handles commas/braces/`#` inside quoted strings, which
the old regex did not.

### Defects found and fixed that the plan did not anticipate

- **4th silent-drop site**: `config_validation.py:78` (plan listed three).
- **`config_access.with_layer_rules_replaced` CRASHED** on a structured entry
  (`dict in Set[str]` -> TypeError). The plan called it a "silent flatten" -- it was
  a hard crash across the whole maintenance/analysis surface.
- **`ConfigLayer` metadata dropped** on rebuild (`unexpected_keys`,
  `duplicate_format`, `shadowed_path`) -- pre-existing, fixed via `dataclasses.replace`.
- **`redundancy._config_without_allow` silently no-opped** on structured entries.
  My initial severity claim (that it would recommend DELETING a live rule) was WRONG
  -- a pre-existing `config_without is config` guard turns it into a skip. Real defect
  is a coverage gap: structured entries were never evaluated for corpus-redundancy.
- **`to_source()` sentinel bug**: a JSON `null` entry round-tripped as the STRING
  `"None"`. `raw is not None` conflated "no raw recorded" with "raw was literally
  None". Fixed with an `_UNSET` sentinel; a second instance of the same bug class was
  found and fixed in `rule_sort.py`.
- **`annotate.py` multi-line lookup always missed** (dict keyed by full content,
  looked up per physical line).
- **Escaped-quote truncation** in the old regex parser (`"Bash(echo \"hi\")"` parsed
  to `Bash(echo \`) -- fixed as a side effect of using real `tomllib`.

### Architectural changes beyond the plan

- **`RuleEntry` went into a NEW leaf module `toolguard/rule_entry.py`**, not
  `config.py` as planned -- `config.py` imports `config_validation`, so the planned
  placement would have forced a circular import at increment 4. `Issue` moved to
  `toolguard/issues.py`. Both re-exported from `config.py`, so all ~69 import sites
  are unchanged.
- **`toolguard/config_types.py`** (Arnon's request): the 7 thin frozen dataclasses
  moved out of `config.py` (2365 -> 2108 lines), separating type definitions from
  implementation logic. `Configuration` (1088 lines, 22 methods) deliberately stayed.
- **`test/unit/test_architecture.py`** (new): enforces the layering as a DAG, asserts
  re-exports are the SAME objects (a duplicate definition passes every behaviour test
  while `isinstance()` fails across module boundaries), and ratchets against new
  function-level imports. Its detectors were mutation-tested against 9 synthetic
  sources -- which caught a real bug in the detector itself.

### Verified independently (not taken from subagent reports)

Real `migrate()` round-trip preserves an enriched rule byte-identically, with
comments and post-sort position; structured entries survive in DENY lists; native
layers still reject structured entries; `#NOSECURITY` cannot be forged from a `#`
inside a quoted string (including inside `additionalContext`); a single-line
structured entry loads and enforces.

Coverage on touched modules: `issues.py`/`config_types.py` 100%, `rule_entry.py`
96.6%, `config.py` 96.5%, `rule_sort.py` 86.9% -> 92.3%.

### Open items for Arnon

1. **Completion gate**: the `~/.config/toolguard/rules/gh.rules.toml` symlink is now
   redundant -- verified `gh.rules.toml` is discovered natively from
   `~/.toolguard/rules/`. Safe to delete.
   **Bonus find**: `git.rules.toml` also lives there and was NEVER symlinked, so it
   was silently unenforced until increment 0 landed. It is now active -- worth
   reviewing that its rules are what you want enforced.
2. ~~**New ticket recommended -- fail-open on parse error.**~~ **DONE 2026-07-26**, at
   Arnon's direction rather than deferred: a TOML syntax error anywhere in a rules file
   used to skip the WHOLE file, silently disabling its `deny`/`hard_deny` with only a
   stderr warning. Now `Configuration.parse_failures` is populated and
   `resolve_permission_detailed` clamps every decision to `ask` (naming the broken
   files in user-visible output) until the config is fixed; `deny`/`hard_deny` are
   never weakened. SessionStart also alerts loudly. See
   [[TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report]]. No new
   ticket needed.
3. **`installer.py` latent issue** (flagged by a subagent, not fixed): raw `in`
   membership checks in `cmd_seed_self_perms` against lists that can contain
   structured entries. Same bug class as the ones fixed; non-security, self-healing.
4. **Separate task**: add `[tool.ruff] line-length = 88` + pin ruff + one intentional
   format commit. 56 of 117 files have drifted from ruff defaults; out of scope here
   because it would bury this ticket's diff.
5. **Phase 1** (`additionalContext` injection itself) is unblocked.
6. **DEFERRED BY ARNON (2026-07-28) -- ASK-floor residual gap for value-taking
   interpreter flags.** The bypass fix landed (see
   [[TOO-19 ASK-Floor Detection Bypass Fix]]): `_detect_foreign_inline_code` now scans
   forward through flag-shaped tokens instead of checking only `remaining[0]`, closing 11
   confirmed bypasses (`python -u -c`, `-B`, `-I`, `-O`, attached `-c'...'`/`-cimport`,
   bundled `-uc`, `perl/ruby -w -e`, `node --experimental-vm-modules -e`).

   **Still open:** any interpreter flag whose value is a SEPARATE token still ends the
   scan and bypasses the floor -- `python -W ignore -c`, `python -X dev -c`,
   `perl -I /path -e`, `ruby -I lib -e`, `node --require foo -e`. Structurally
   indistinguishable from `python -m mymod -c` (where `-c` really does belong to the
   module) without a per-executor table of value-taking flags.

   Arnon's decision: **do not build the table speculatively.** He will mine transcript
   evidence for which interpreters/flags actually occur in practice, then split the result
   between his own personal rules and toolguard builtin behaviour. Current fixes judged
   sufficient in the meantime.

   Related, also flagged and deliberately unchanged: `_FOREIGN_INLINE_FLAGS["awk"]` is
   `["-f"]`, which is awk's program-FILE flag; awk's actual inline program is the bare
   first argument (`awk '{print $1}'`) and is never detected. Wrong in both directions,
   but awk is common enough that changing it deserves its own decision.

7. **Safe-experimentation mechanism** -- design written to
   [[Safe Experimentation Mechanism - Design Proposal]], Arnon's verdict "good, but not
   good enough"; his annotated response pending. He has gated the Phase 0 commit on this.
