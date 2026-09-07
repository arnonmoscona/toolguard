---
title: coder-latest-task-recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- instagram-downloader
---

---
tags: [task-memory, TOO-28]
---

# TOO-28 Phases 6+7 -- coder task recall (CURRENT; everything below down to the next '---'
divider that starts an older '## TOO-28 Phase' section is STALE from earlier sessions --
write_note overwrite does not take effect for this permalink, known basic-memory quirk, so
prepend is used)

## Ticket: TOO-28, Phases 6 + 7

Brief: `toolguard-memories/TOO-28/brief-phase67.md` (validated: all 5 slots present and filled).

Both phases in one commit, at Arnon's instruction. Do 6 first (its claims-must-be-true rule
applies to what Phase 6 writes too). No git write ops -- leave tree dirty, describe it.

### Phase 6 -- documentation only, no behaviour change

Seven items, all in `docs/` (+ possibly README.md/llms.txt/AGENTS.md pointers). Out of scope:
`docs/install.md`, anything under `skills/` (that's TOO-77).

1. Division of labour (toolguard=exact pattern match, strong/blind table; auto-mode=semantic
   judgement, inverted strengths). Complementary halves, NOT two implementations of one control.
   toolguard's blind spot is constitutive by design (ASK floor / undecidable_fallback announce
   it). Verify not written already: check docs/security.md (644 lines) and
   docs/architecture-as-built.md (557 lines) which brief author did not read.
2. Design smell named explicitly: "make toolguard smarter so it can handle X" -> wrong, answer
   is auto-mode guidance not a cleverer rule.
3. Handoff framing already written (docs/configuration.md:669, Phase 3) -- VERIFY, don't
   rewrite; cross-link rather than duplicate.
4. Early pointer somewhere orientation-first (README.md / docs/quickstart.md /
   docs/agent-map.md -- decide which, say why).
5. Takeover-mode inaccuracy under auto mode: docs/takeover-mode.md assumes "native permits
   everything, toolguard is only gate" -- false under auto mode since auto mode drops broad
   native allow rules on entry. MUST fetch code.claude.com/docs/en/permission-modes and
   permissions.md in-session before writing this (native-fidelity-claims.md rule). Direction is
   safe (more actions reach classifier not fewer) but doc is inaccurate.
6. Auto-mode trace completely undocumented: `logs/toolguard-automode-<date>.jsonl` (Phase 5).
   Document: what it records, 4 fallback_cause values AS TRIAGE CODES, that it's a read-only
   side channel (write failure never changes verdict), what it does NOT answer (PreToolUse hook,
   never sees auto-mode classifier's own verdict). Source: toolguard/auto_mode_trace.py
   docstring -- but READ PHASE 7 FIRST, part of it is stale (confirmed false: line 21, "does
   not yet vary fallback behaviour by permission_mode" -- Phase 2 shipped
   resolved_no_match_fallback_in_auto_mode and resolved_undecidable_fallback_in_auto_mode).
7. One line for undecidable_fallback: protection reaches only interpreters in
   FOREIGN_EXECUTORS; an interpreter not on that list (lua, deno, bun, julia) gets no ASK floor,
   reaches no_match_fallback instead. Code already documents this in FOREIGN_EXECUTORS' own
   comment; docs don't.

### Phase 7 -- comment/docstring cleanup in *.py

Scope: `git diff TOO-28-start-of-work..HEAD -- '*.py'` (46 files, 5459 insertions). NOT
test/verdict_corpus/ fixtures (frozen goldens). NOT comments outside the diff (general sweep is
widening).

7a: delete pure scaffolding comments (mid-refactor notes with no reader now). Plan's inventory
(hook.py:1016,1103,1271,1275) is STALE -- grep confirmed empty already. Re-derive, don't trust
plan.

7b: trim survivors on 3 questions: (1) has a reader after work lands? (2) concise per
~/.claude/rules/comments.md? (3) is claim still TRUE? -- HIGHEST YIELD, because phases landed
out of order (1,5,2,3,4), so Phase 5 comments may predate Phase 2 features. Confirmed false:
auto_mode_trace.py:21 (see above). Find others via same mechanism (not just grep "not yet"/
"later phase" -- that's incomplete).

Two carried dispositions (don't re-decide):
- invocation.py module docstring: keep the RULE ("explicit argument, not ambient singleton"),
  drop the ARGUMENT (in-process-corpus, eight-console-scripts) -- belongs in ticket not code.
- test/unit/test_architecture.py:42: keep substance (why allow-list is empty / stops importing
  config into it), drop ticket reference.

~30 TOO-28 references in *.py -- judge each; most become plain rule statement or go.

Bounded extra: tools/architecture_fitness.py:1606 R3_SANCTIONED_SITES references
("compound.py", "fallback_kind_for_reason") which no longer exists per
test/unit/test_compound_resolve_seam.py:410 ("the now-deleted"). NOT inert:
test/unit/test_architecture_fitness.py:1884 builds synthetic source to exercise that entry.
Judgement call -- if removing changes what a test means, STOP and report, don't adjust test.

### Widening: NOT authorised except (a) fixing own breakage, (b) correcting a doc statement
found factually false while writing nearby prose (report separately).

### Findings carried forward
1. Phase 4a's "unknown interpreter gap" finding RETRACTED except item 7. Unrecognised
   interpreter DOES reach no_match_fallback correctly -- that's what fallback is for. Don't
   document a gap; document scope of what undecidable_fallback covers.
2. Phase 0 status (does hook allow skip auto-mode classifier) UNSETTLED -- belongs to TOO-77.
   Do NOT write a docs sentence answering it either way; if named at all, name as open.
3. Handoff framing + settings reference already written (Phases 2,3,4) -- verify + cross-link,
   don't duplicate.
4. Baseline taken 2026-09-07 at bd4f895: suite "Ran 4130 tests" / OK; ruff check clean; corpus
   --verify --strict-prose "OK: no differences" at 6401 in-process / 61 end-to-end; 3
   architecture_fitness.py checks pass; 8 console entry points load.

### Native docs fetched 2026-09-07 (this session)

From https://code.claude.com/docs/en/permission-modes, "How the classifier evaluates actions"
accordion:

> On entering auto mode, broad allow rules that grant arbitrary code execution are dropped:
> * Blanket `Bash(*)` or `PowerShell(*)`
> * Wildcarded interpreters like `Bash(python*)`
> * Package-manager run commands
> * `Agent` allow rules
> * `Monitor` allow rules, because Claude Code runs Monitor commands through the shell
>
> Narrow rules like `Bash(npm test)` stay in effect. Claude Code restores the dropped rules
> when you leave auto mode.

Confirms brief's item 5 premise and "direction is safe" claim.

### TDD note
TDD NOT required -- both phases behaviour-neutral by construction. Corpus is the load-bearing
check. If a new test seems needed -> stop and report, out of scope.

### Constraints
uv run python, unittest not pytest, stdlib-only runtime, PEG grammar unchanged. Disclosure
rule for authored Bash. No git write ops. Read ~/.claude/rules/comments.md before writing/
trimming any comment. .claude/rules/native-fidelity-claims.md mandatory for item 5.

---

---
tags: [task-memory, TOO-28]
---

# TOO-28 Phase 2 -- two independent auto-mode fallbacks (CURRENT; everything below down to
the next '---' divider that starts an older '## TOO-28 Phase 5' or similar section is STALE
from earlier sessions -- this note's write_note overwrite does not take effect for this
permalink, a known basic-memory quirk, so prepend is used instead)

Brief: `toolguard-memories/TOO-28/brief-phase2.md` (validated, 5/5 slots). Plan reference:
`toolguard-memories/TOO-28/TOO-28 implementation plan.md`.

## Task

Two new top-level `toolguard_hook` keys, `no_match_fallback_in_auto_mode` and
`undecidable_fallback_in_auto_mode`, independently configurable, same value vocabulary
(`ask`/`deny`/`allow_with_warning`/`allow`, plus the `allow_with_no_warnings` alias) as their
base settings. When Claude Code's `permission_mode == "auto"`, the resolver consults the
`_in_auto_mode` variant instead of the base one; unset means "defer to the base setting"
(NOT a fixed default like `'ask'`) so the change is inert until someone opts in. `deny`,
`hard_deny`, and the TOO-19 parse-failure ASK floor are untouched.

Uncommitted `fallback_kind` -> `fallback_outcome` rename (9 files) stays in the tree; ships in
the same commit as this phase, per Arnon. Baseline: 4043 tests / OK (expected failures=4);
`ruff check .` clean; verified again at session start before touching anything.

## In scope

- `ResolutionContext`/`ResolveContext`/`FilePathResolutionContext` (`config_types.py`) gain
  `permission_mode: Optional[str]`. `Invocation` already has the field (Phase 1), so it
  satisfies the widened Protocol unchanged.
- `Configuration.resolved_no_match_fallback_in_auto_mode()` /
  `resolved_undecidable_fallback_in_auto_mode()` -- new methods, each one call to the existing
  `_resolve_fallback_setting(key, valid_values, default, alias_map=...)` with `default` set to
  the BASE resolved value (`self.resolved_no_match_fallback()` / `resolved_undecidable_fallback()`),
  computed dynamically, not a literal. This reuses `_resolve_fallback_setting` with NO changes
  to its body -- confirmed by reading it (see Findings below).
- `ResolutionConfig`/`ResolveConfig` Protocols (`config_types.py`) gain the two new resolver
  methods so `context.config.resolved_no_match_fallback_in_auto_mode()` etc. type-check.
- `permission_resolution.py`: `resolve_command_permission`/`resolve_file_path_permission`
  branch on `context.permission_mode == AUTO_PERMISSION_MODE` to pick base vs auto resolver
  for `no_match_fallback`. Factor the branch into one small helper shared by both functions.
- `resolve.py`: `resolve_bash_permission_detailed`'s `judge_unit(...)` call (line ~353)
  branches the same way on `invocation.permission_mode` for `undecidable_fallback`.
- A new shared constant `AUTO_PERMISSION_MODE = "auto"` -- MUST live in `config_types.py`
  (config layer), not `hook.py` (runtime layer): `permission_resolution.py`/`resolve.py` are
  engine layer and cannot import runtime. `hook.py` already has its own local
  `AUTO_PERMISSION_MODE = "auto"` (used by the Phase 5 trace gate) -- change it to import the
  same constant from `config_types.py` rather than leaving two literals that can drift (CLAUDE.md:
  literal strings with semantic meaning belong in constants).
- `tools/takeover_audit.py`: two new findings mirroring invariant 4/5 but reading the
  `_in_auto_mode` resolvers, firing ONLY when `resolved_..._in_auto_mode() != resolved_...()`
  (i.e. explicitly configured to something other than deferring to base) AND the auto value is
  loose by the same predicate as the existing invariant. This catches the real gap (base=deny,
  auto=allow, currently invisible) without duplicate-firing when unset (auto defers to base by
  construction, so equality means "nothing new to say").
- `docs/` (configuration reference) documents the two new settings, framed as handoff points
  per spec section 2, not "auto-mode variants". NOT `install.md`, NOT skills (TOO-77).
- Step 6: an ENUMERATING test asserting the parse-failure ASK floor is unaffected by either
  new setting in every combination, under auto and non-auto -- written to also catch a FUTURE
  fallback-ish setting, not hard-coded to just these two.

## Out of scope

Per-rule auto-mode override (spec 4.2, Phase 3). Any change to `deny`/`hard_deny`/the floor
itself. Reading `permission_mode` for anything but these two settings. A Phase-5 trace on/off
switch.

## Key investigation findings (from reading the code this session, before writing anything)

1. **`_resolve_fallback_setting`'s body needs NO changes.** Read in full:
   `raw = self._first_toplevel_str_setting(key); if raw is None and legacy_alias: raw =
   legacy_alias(); if alias_map and raw in alias_map: raw = alias_map[raw]; return raw if raw
   in valid_values else default`. Passing a dynamically-computed `default` (the base resolved
   value) rather than a literal works exactly as needed with zero modification.

2. **"Unset" and "unrecognized" DO collapse to the same `default` inside `_resolve_fallback_setting`
   -- confirmed, and it is the documented, deliberate "safe direction" for the two EXISTING
   settings** (unset/unrecognized `no_match_fallback` -> `'ask'`, the strictest). This is
   NOT a gap for the base settings: `Configuration.unrecognized_fallback_settings()` is a
   SEPARATE diagnostic (not the resolver) that already scans every layer and reports a
   `warning` Issue (via `_unrecognized_fallback_setting_issues`, surfaced at session start and
   in config validation) for exactly "set to something unusable" -- distinguishing it from
   "unset" is already solved, just not inside the resolver itself.
   **For the two NEW settings this needs a genuinely different design**, because their default
   isn't a fixed literal, it's "defer to base" -- so I'm extending `unrecognized_fallback_settings()`
   (and its `valid_by_key`/`alias_by_key` dicts) to also cover the two new keys, reusing the exact
   same per-layer scan. Its `describe()` method currently hardcodes "falling back to 'ask'" in
   `UnrecognizedFallbackSetting` (`config_types.py`) -- WRONG for the new keys (they fall back to
   the base setting's resolved value, which may not be 'ask'). Needs a message that names what it
   actually falls back to, parametrized per key rather than hardcoded.
   **This is the finding the brief most wanted checked, and the answer is: the base settings were
   never actually ambiguous (the diagnostic already disambiguates them) -- the new settings need the
   diagnostic extended AND its message corrected, which is a real, if minor, pre-existing inaccuracy
   surfaced by adding keys with a different fallback target.**

3. `apply_parse_failure_floor`/`_apply_ask_floor` are structurally already immune: neither
   function takes a fallback-setting parameter at all, so nothing about *which* no_match/
   undecidable resolver is consulted upstream can reach them. The floor is applied twice
   (once per-sub-command inside `resolve_permission_cascade`, once again at the compound
   boundary in `resolve.py:400`). Step 6's test should still exist (this is a hard invariant
   worth pinning, not something to skip because it's already structurally true), enumerating
   over both new settings' full value sets x both modes x parse-failure-present.

4. Layer map confirmed via `.pyscn.toml`: `invocation` is `foundation`; `config`/`config_types`
   are `config`; `permission_resolution`/`resolve`/`compound`/`permissions`/`file_matching`/
   `parser` are `engine`; `hook`/`session_start`/`subagent` are `runtime`. `permission_resolution.py`
   deliberately imports neither `config` nor `invocation` (docstring states this explicitly) --
   only `config_types`. `resolve.py` already imports `Invocation` directly. `compound.py` takes
   `undecidable_fallback` as an already-resolved plain string parameter and has no config/mode
   awareness at all -- correct, no change needed there; the mode branch happens in `resolve.py`
   before calling `judge_unit`.

5. `tools/takeover_audit.py::audit_takeover(config)` takes only a `Configuration`, no
   `Invocation`/`permission_mode` -- confirmed, matches the brief. Existing Invariant 4
   (`loose-no-match-fallback`, LOW) and Invariant 5 (`loose-undecidable-fallback`, HIGH) read
   `config.resolved_no_match_fallback()`/`resolved_undecidable_fallback()` and fire when not
   `'deny'` / when loose, respectively. Adding two new findings alongside them, same file,
   same pattern.

6. Call sites needing the mode branch (exhaustive, from grep): `permission_resolution.py:421`
   (`resolve_command_permission`), `permission_resolution.py:466` (`resolve_file_path_permission`),
   `resolve.py:353` (`judge_unit`'s `undecidable_fallback` arg). No other call site of either
   base resolver exists outside `config.py`, `takeover_audit.py`, and tests.

## Process notes

- TDD required (this adds behaviour). Paste RED runs, no `RED:` markers left in code.
- Corpus equivalence (step 10/11) must hold with the new settings UNSET -- proof of inertness.
  Calibrate the instrument first (plant a change, confirm `--verify` fails, revert, confirm
  clean diff and passing verify) before trusting a "no differences" result.
- Live end-to-end (step 13): drive the real `toolguard.hook:main` via piped synthetic
  `PreToolUse` JSON, from the repo root, under both `permission_mode: "auto"` (with the new
  setting configured, unmatched command) and `permission_mode: "default"` -- paste both.
- Final report: five headings at column 0, no preamble. Files opened in JetBrains via
  `projectPath="//wsl.localhost/Ubuntu-26.04/home/arnon/projects/toolguard"`.

---

---
tags: [task-memory, TOO-28]
---

# TOO-28 Phase 5 -- coder task recall (this session; content below down to the next '---'
divider that starts a new '## TOO-28' or '## Ticket' section is STALE, from an earlier
session, and is being replaced piecemeal since this note's write_note overwrite is not
taking effect for this permalink -- see basic-memory quirk noted in the implementation
report)

## Brief
`/home/arnon/projects/toolguard/toolguard-memories/TOO-28/brief-phase5.md` -- validated
(5/5 slots) before starting.

## Task
Spec section 4.4: when no toolguard rule matched AND `permission_mode == "auto"`, record
what happened in a dedicated JSONL log (`logs/toolguard-gap-YYYY-MM-DD.jsonl`). Read-only
side channel -- nothing in the decision path reads it, a write failure must never change a
verdict. Phase 1 (already committed) made `Invocation.permission_mode` reachable at the
decision path; this phase is the first consumer of it.

## Scope
In scope: new log writer + trigger + classification, registered in
`test/unit/_real_log_dir_guard.py`. Out of scope: PostToolUse hook, install-flow/skill
changes (TOO-77), new config setting, anything that READS the log, Phases 2/3 (auto-mode
fallback config, per-rule override).

## Coordinator mid-task clarification (2026-09-06)
- Finding 2 (whether `plan` mode should also trigger) is CLOSED: auto only, do not widen,
  do not report as open. Plan mode is meant to be read-only by Claude Code's own design.
- Finding 1 (PostToolUse/classifier-verdict limitation) de-prioritised: state as a scope
  boundary in the docstring, not as a shortfall.
- Field selection: the governed subject must be the FULL, untruncated command/path text --
  "prose is output" rule applied to this log's primary field. Same subject text and tool
  naming as the existing decision log, so the two corpora can be correlated/compared.
- Do NOT log non-auto entries (the decision log already carries permission_mode on every
  entry, so that comparison is already possible).
- Must NOT claim in the docstring that auto-mode commands were governed more permissively
  -- Phase 2 (auto-mode fallback config) hasn't landed, so today the SAME fallback applies
  regardless of mode. This log is a pre-relaxation baseline.

## Key design decisions made (all documented in code + implementation report)
1. Call site: `toolguard/hook.py::_handle_command_tool` / `_handle_file_path_tool`, right
   after `result: RuntimeVerdict` is computed -- both already have `invocation` in hand.
   One shared helper `_maybe_log_auto_mode_gap`, not scattered.
2. Trigger (`_fallback_decided`): for Bash (possibly compound), check `result.sub_matches`
   -- fires if ANY non-audit-only unit has `matched_rule is None`. This correctly
   distinguishes "some/all leaves fell to a fallback" from "no single decider because
   multiple leaves each matched a DIFFERENT real rule" (RuntimeVerdict.matched_rule is
   None in BOTH cases at the top level -- brief's Finding 2 flagged this ambiguity
   explicitly). For file-path verdicts (never compound), `result.matched_rule is None`
   directly.
3. Classification (`_classify_fallback_source`): only the deny-side undecidable escape
   hatch is structurally unambiguous (`RuntimeVerdict.fallback_kind == "denied"`). Ask-floor
   and allow-side escape hatches collapse to the same shape as a plain no_match_fallback
   outcome at every altitude available without touching resolve.py/compound.py (which
   would need CommandUnit.kind, not carried on UnitVerdict) -- reported as "no_match" by
   default. Documented as a known, honest limitation, not silently guessed.
4. `gap_log.py` lives in the "observability" architecture layer (same as log_writer.py/
   error_log.py), so it must NOT import config_types.py (RuntimeVerdict/UnitVerdict) --
   confirmed via .pyscn.toml's layer rules before writing code. hook.py (runtime layer)
   extracts primitives into a GapLogEntry dataclass, exactly like LogRecord.
5. Added `Invocation.session_id` (mirrors Phase 1's `permission_mode` addition) -- an
   invocation-wide fact, threaded via the initial Invocation() construction in main()
   (available immediately from hook_data, unlike governed_tools/agent_info/permission_mode
   which need a later replace()).
6. Defense in depth: `_maybe_log_auto_mode_gap` wraps its own call to log_gap in try/except
   too (log_gap already swallows internally) -- makes "a write failure does not change the
   verdict" independently testable and true even against a bug in log_gap itself.

## Findings / corrections to the brief
- The brief's premise that JSONL precedent is `toolguard-discovery.jsonl` is WRONG -- no
  such file exists; the real discovery log is `toolguard-discovery.log`, plain
  tab-separated text, not JSON at all. Followed the error/warning/conflict DATED-file
  convention instead, with JSONL content per log_writer.py's actual (currently-unused)
  LOG_FORMAT_JSONLINES rendering.
- `--ambient` fitness check false-positived on `GapLogEntry.cwd`/`entry.cwd` (bare
  attribute-name match, no type-awareness) -- same class of false positive already solved
  for `hook.cwd` (PreToolUseEvent.cwd). Added a matching PATH_AMBIENT_OWNERS entry in
  tools/architecture_fitness.py with the same style of justification.

## Baseline (measured before any change)
4021 tests / OK (expected failures=4); ruff check clean; ruff format flagged ONE
pre-existing issue in invocation.py (stray blank line, unrelated to Phase 5, fixed
incidentally since the file was already being touched); all 3 fitness checks exit 0;
corpus `OK: no differences` at 6401/61; all 8 entry points import cleanly.

---

(Everything below this line is STALE content from an earlier session's recall, left in
place only because this permalink resists a clean overwrite; ignore it.)

# TOO-28 Phase 1 round 3 -- thread Invocation through the engine layer (Protocol refactor)

Brief: `toolguard-memories/TOO-28/brief-phase1-round3.md` (validated: all 5 slots present).

## Task

Round 2 threaded `Invocation` through `hook.py`, `resolve.py`, `api.py`, then stopped at the
engine layer (`permission_resolution.py`, `compound.py`, `file_matching.py`, `parser/*`),
arguing Protocol-typed config surfaces make threading a concrete `Invocation` wrong there.
Arnon rejected this 2026-09-05: a Protocol expresses a shape requirement one level out, and the
existing Protocols (`ResolutionConfig`, `ResolveConfig`, `FilePathResolutionConfig` in
`config_types.py`) can be refactored into "context" Protocols (`tool_name`, `extended_syntax`,
`config: <SomeConfigProtocol>`) without broadening what they require. Job: finish the
threading by refactoring the Protocols, not discarding them.

Phase 1 stays behaviour-neutral. `permission_mode` becomes reachable; nothing reads it to alter
a verdict.

## Scope

- `permission_resolution.py`: `resolve_command_permission`, `resolve_file_path_permission` --
  all three of config/tool_name/extended_syntax are on Invocation.
- `compound.py`, `file_matching.py`, `parser/*` -- re-measure (round 1 said empty, round 2 said
  file_matching.py has genuine candidates; brief says the two disagree, resolve which is right).
- `config_types.py` -- add the context Protocol(s), expressed in terms of existing Config
  Protocols.
- `resolve.py` loose ends: `_hard_deny_additional_context`'s two params, and whether
  `_decide_bash` should share `decide`'s Invocation.
- Cascade fixups in any broken caller/test authorized as fallout, not new behaviour.
- Decided, do not re-open: `Invocation` stays in `foundation` with an empty import allow-list
  (never imports `config_types`); `api.decide`'s public signature unchanged.

## Baseline (round 2, independently re-confirmed by me before starting)

4021 tests / OK (expected failures=4); ruff clean; three fitness checks pass; corpus 6401
in-process / 61 end-to-end, OK: no differences, calibrated; all 8 console entry points load.

---

## TOO-28 Phase 1 ROUND 2 (this session) -- thread Invocation all the way down

Brief: `toolguard-memories/TOO-28/brief-phase1-round2.md` (validated, 5/5 slots). Everything
below this line, down to "--- (round 1 recall follows, superseded where it conflicts) ---",
is the current task. Round 1's recall further down is historical context only.

### Corrected criterion (supersedes round 1's "2+ statics")
Any parameter whose value is directly available from `Invocation` is a fossil, whether there
is one of them or five. Not just multi-static functions.

### Decided by Arnon, do not re-open
- Engine (resolve.py etc.) takes `Invocation`.
- `api.decide` keeps its PUBLIC signature `(config, tool, target, extended_syntax=True)` and
  constructs an `Invocation` internally (synthetic tool_input, no real cwd/agent_info/
  governed_tools/permission_mode).
- Phase 1 stays behaviour-neutral. permission_mode becomes reachable, nothing reads it to
  alter a verdict (that's Phase 2).

### In scope
- `toolguard/hook.py` -- 6 remaining helpers: `_log_allowed_command`, `_log_non_allow_decision`,
  `_log_config_discovery`, `_resolve_takeover_mode`, `_run_divergence_check`,
  `_run_startup_validation`. Reordering `main()` authorised BUT: `get_env_config()` before
  `load_configuration()` is load-bearing (reporter needs log dir for warnings during config
  discovery) -- if reordering changes WHEN a warning/log line emits, STOP and report.
- `toolguard/resolve.py` -- both `resolve_bash_permission_detailed` and
  `resolve_file_path_permission_detailed`.
- `toolguard/permission_resolution.py`, `toolguard/compound.py`, `toolguard/file_matching.py`,
  `toolguard/parser/*` -- wherever a param is available on Invocation.
- `toolguard/api.py` -- construct Invocation inside decide/_decide_bash. Public signature of
  `decide` unchanged (verify via grep).
- `toolguard/invocation.py` refinements:
  - Fields a non-hook caller lacks (cwd, agent_info, governed_tools, permission_mode) become
    `Optional`/`None`, not `""`. Update type hints + docstring.
  - Add factory classmethod (e.g. `Invocation.for_evaluation(...)`) shared by api.decide and
    tests needing synthetic Invocation. Facts only -- no decision logic in the factory.

### Out of scope for NEW BEHAVIOR but IN scope for refactor fallout
Fix any breakage the signature cascade causes in: tools/installer.py, tools/security_audit.py,
tools/maintenance.py, tools/takeover_audit.py, session_start.py, update_check.py,
permission_migration.py, tools/update_skills.py, tools/decision.py, testing/sandbox.py,
tools/corpus_build.py, every test module. No new behavior, no refactor-for-its-own-sake, no
Invocation injected where not needed. List every file touched this way.

Widening NOT authorised beyond the cascade. No new settings, no auto-mode behavior, no reading
permission_mode to change verdict, no unrelated cleanups -- report, don't fix.

### Steps (13) and completion artifacts -- see brief for full table
1. Re-measure fossils under corrected criterion -- list + count in report.
2. invocation.py refinements -- test_architecture.py allow-list for it stays empty frozenset().
3. resolve.py both resolvers take Invocation -- suite green at baseline counts.
4. api.py constructs Invocation; decide's public signature unchanged -- grep proof.
5. hook.py six helpers + main() reordering -- suite green; explicit statement on log/warning
   emission order.
6. permission_resolution.py, compound.py, file_matching.py, parser/* -- suite green.
7. Fix cascade in out-of-scope modules -- list every file.
8. Lint/format clean.
9. Architecture fitness --stdlib/--ambient/--layers exit 0 each; paste last line of each.
10. Verdict-corpus equivalence: corpus_build.py --verify --strict-prose -> OK: no differences,
    6401 in-process / 61 end-to-end.
11. CALIBRATE FIRST: plant a decision-altering change, confirm --verify FAILS, revert, confirm
    passes, confirm git status --porcelain clean for planted file. Paste all three outputs.
12. ENTRY-POINT SMOKE TEST: import each of the 8 console-script modules from pyproject.toml
    [project.scripts] and confirm each loads. Paste result.
13. Sibling sweep: re-run step-1 scan post-migration, report what remains + why left.

Baseline to match EXACTLY: `Ran 4021 tests` / `OK (expected failures=4)`; ruff check ->
`All checks passed!`; corpus `OK: no differences` at 6401/61. Changed test count = a finding,
not a pass -- say which tests changed and why.

### Round 1 already done (in working tree, build on it)
- hook.py: `_handle_file_path_tool`, `_handle_command_tool` migrated to take `invocation:
  Invocation` (5 statics -> 1). TOO-28-SCAFFOLD aliases deleted. main()'s two call sites updated.
  9 test call sites in test_hook.py updated (construct Invocation via `_invocation()` helper).
- invocation.py: frozen dataclass, 8 fields (tool_name, tool_input, cwd, config, env_config,
  governed_tools, agent_info, permission_mode), imports nothing from toolguard, foundation layer.
- Baseline suite: Ran 4021 tests / OK (expected failures=4). Corpus: 6401 in-process / 61 e2e,
  OK: no differences. Calibrated via config.py _DEFAULT_NO_MATCH_FALLBACK plant/revert (proven
  sensitive).
- Round 1's 6 helpers NOT migrated (now MY job): see hook.py list above.
- Round 1 found compound.py/parser/* reference NO statics at all (may still be empty under
  corrected criterion -- verify, don't assume).

### Conventions
- Given/When/Then docstrings on test functions, kept in sync with edits.
- Comments: short, why not what. ~/.claude/rules/comments.md and python.md apply.
- Do not touch test/verdict_corpus/ (frozen baseline).
- uv run python always, never bare python/python3 (denied by permission rules).
- No git write ops. Step 11 revert = edit file back, never git checkout.
- Disclosure rule: any authored Bash logic needs INTENT/TOUCHES/INLINE BECAUSE comment +
  TG_INTENT=1 (or TG_ATTEST_READONLY=1 if all read-only) prefix on the leaf.

### This brief is unverified -- brief's own flagged uncertainties
- Whether extended_syntax is always derivable from env_config (checked one call site only).
- Whether all 6 hook.py helpers are genuinely migratable (round 1 checked only ordering reason).
- Whether compound.py/file_matching.py/parser/* contain anything in scope (may be empty --
  fine, say so, don't manufacture work).
- Whether main() can be reordered safely at all beyond the one known constraint.
- Whether this stays behaviour-neutral -- step 11 tests this.

Report anything wrong, including in `toolguard-memories/TOO-28/TOO-28 implementation plan.md`.

--- (round 1 recall follows, superseded where it conflicts) ---

## Ticket / context

No YouTrack ticket. Project: /home/arnon/projects/instagram-downloader.
Brief file: /tmp/claude-1000/-home-arnon-projects-instagram-downloader/cb73a65e-4b61-44d5-9ffe-49aacd793eab/scratchpad/brief-grid-navigation-fix.md
Brief validated OK (5/5 slots).

## Task

`process_collection()` in `collection_processor.py` stops after ~16-20 posts in a saved
collection that holds 83+. Root cause diagnosed in brief: exact-match click selector
`a[href='/p/{post_id}/']` never matches real grid hrefs (`/{author}/p/{post_id}/`), so the
loop always falls through to `page.goto(post_url)` — a direct navigation with no way back
to the grid. Subsequent scrolling/harvesting then runs against the post page, not the
collection grid.

## Scope

In scope: collection_processor.py (download_post, _close_popup_if_open, process_collection
scroll/termination loop), models.py (only if PostInfo needs more fields), tests/, a
throwaway probe in tmp_work/.

Out of scope (do not touch): auth.py, navigation.py, browser.py, config.py, tui_app.py,
tui_reporter.py, status.py, metadata_log.py, download_log.jsonl format, anything under
~/OneDrive/Pictures/WFDownloader-replacement/ (report only), .env/.claude.env.

Widening authorized only within collection_processor.py and tests/, per step 1's verdict.

## Steps (in order, per brief)

1. MEASURE FIRST (gates 2/3): probe in tmp_work/ - does clicking a post's real href open a
   modal or navigate away? Does Escape from a modal restore grid scroll/DOM/pathname?
   Artifact: probe file + before/after numbers + one-line verdict.
2. Fix selector at collection_processor.py:542 to use post.href. TDD required: failing
   test against old exact-match selector, passing against new one.
3. Make leaving the grid recoverable. Design depends on step 1 verdict. Invariant:
   process_collection is on the collection grid at top of every scroll iteration.
4. Restore prototype settling times (tmp_work/test_full_scroll_v2.py used uniform(6,8) on
   no-spinner path + uniform(3,5) end of each iteration; production only does
   human_delay(3,5) with no end-of-loop delay).
5. Run uv run pytest, uv run ruff format ., uv run ruff check . — paste output.
6. Verify against live "August 2026" collection in DRY_RUN mode; confirm discovered count
   exceeds 83 and keeps climbing to natural end.
7. Sibling sweep: check other hardcoded selectors (_CAROUSEL_NEXT_BTN :157,
   _CAROUSEL_SLIDE_COUNT_JS, _EXTRACT_POSTS_JS, [role="dialog"] assumption) against reality.

TDD required only for step 2 (pure, testable without browser). Not required for 3/4/6
(Playwright-integration, real verification is the live run in step 6).

## Findings carried forward (dispositions already decided by brief author)

1. Exact-match selector never matches -> FIX (primary bug), use post.href.
2. goto fallback is unrecoverable -> FIX (grid must be restored or loop must tolerate
   leaving it).
3. _close_popup_if_open is a no-op with no dialog -> FIX together with #2.
4. Settling time ~half prototype's -> FIX.
5. One download_log.jsonl record has a 39-char post_id (should be 11) -> REPORT ONLY, do
   not touch WFDownloader-replacement files.
6. reporter.discovered() DOM-snapshot first arg caps at 42 under virtual scrolling ->
   REJECTED, leave alone, informational only.
7. Spinner detection/scroll mechanics are sound (measured: +1661px, +12 posts/scroll, 83
   unique after 6 scrolls, still climbing with post-opening removed) -> NO CHANGE.
8. convert_image_to_png cannot derail flow (utils.py:109-115 catches everything) ->
   REJECTED as cause, no change.

## Brief's measured vs inferred claims (attack the inferred ones)

Measured: grid href shape, 0/8 exact-match, scroll growth numbers, DOM caps at 42,
download_log.jsonl 52 records stats.

Inferred / NOT verified — my job to check:
- Clicking real href opens a modal vs navigates away (step 1 exists for this).
- Escape from modal restores grid scroll position / loaded posts (Instagram pushes
  /p/{id}/ into history on modal open; popstate may reset virtualized list).
- Extra 5-8 posts/run come from post-page recommendations (inferred from 39-char post_id).
- True size of August 2026 collection unknown — 83 was still climbing; don't treat 83 as
  the hard target, just "keeps climbing past 83 to a natural end".

Also: current working tree has uncommitted mods to browser.py, config.py, pyproject.toml
etc. — line numbers in brief may drift; re-resolve against current file.

## Constraints

uv run python always. Comments short, why not what. String literals branched on -> named
constants. Do not commit (Arnon does git writes). No async/threading/local imports without
approval. Live IG session already valid in browser_data/ — probes using project's own
BrowserManager + navigation.py should just work; examples in tmp_work/.