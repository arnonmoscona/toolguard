---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-28
- implementation-report
---

# TOO-28 Phase 5 -- Implementation Report

(Content below the horizontal rule near the end of this file is STALE, from the prior
Phase 1 Round 4 report -- left in place because this note's permalink resists a clean
`write_note` overwrite; ignore everything after "## STALE CONTENT BELOW".)

Brief: `toolguard/TOO-28/brief-phase1-round4` (validated 5/5 slots).

Brief: `toolguard-memories/TOO-28/brief-phase5.md` (validated 5/5 slots present).

## Summary

Implemented the TOO-28 spec 4.4 auto-mode gap log: a new, read-only JSONL side channel
(`logs/toolguard-gap-YYYY-MM-DD.jsonl`) that records one entry per governed Bash/file-path
decision where **no toolguard rule matched** (the fallback decided) **and** Claude Code's
own `permission_mode` was `'auto'`. Nothing in the decision path reads this log, and a
write failure in it can never change a verdict (defended at two independent layers).

New module `toolguard/gap_log.py` (writer + `GapLogEntry` dataclass), two small additions
to `toolguard/hook.py` (a shared trigger/classification helper called from both
`_handle_command_tool` and `_handle_file_path_tool`), a new `Invocation.session_id` field
(mirrors Phase 1's `permission_mode` addition), registration in the test suite's real-logs
guard, an owner-table entry for a false-positive `--ambient` finding, and 11 new tests (5
in a new `test/unit/test_gap_log.py`, 6 in a new `TestAutoModeGapLog` class in
`test/unit/test_hook.py`). TDD followed throughout -- see the RED/GREEN evidence below.
Self-review is complete: full suite green (4032 tests, up from the 4021 baseline + 11 new),
ruff clean, all 3 architecture-fitness checks pass, corpus equivalence proven and
calibrated, all 8 console entry points load.

## Step 1 -- where "no rule matched" is decidable with the Invocation in hand

`toolguard/hook.py::_handle_command_tool` and `_handle_file_path_tool`, immediately after
each computes its `result: RuntimeVerdict` (via `resolve_bash_permission_detailed` /
`resolve_file_path_permission_detailed`) and before `return result`. Both functions
already hold a fully-populated `Invocation` (including `permission_mode`, confirmed
reachable there since Phase 1) at exactly that point -- no new plumbing needed to reach
it. One shared private helper, `_maybe_log_auto_mode_gap(result, subject, invocation)`,
is called from both sites, so the trigger logic exists in exactly one place rather than
being duplicated or scattered.

**The brief's own uncertainty here ("I have not traced it") is resolved: yes, one clean
place.** No compound-command special-casing was needed at the call-site level; the
per-leaf nuance (below) lives entirely inside the trigger function itself.

## Step 2 -- RED: an entry is written for an unmatched command under auto (pasted)

*(Reproduced by temporarily removing the hook.py wiring -- the gap_log import, the
`AUTO_PERMISSION_MODE` constant, `_fallback_decided`, `_classify_fallback_source`,
`_maybe_log_auto_mode_gap`, and both call sites -- then restoring it byte-for-byte
afterward via a saved `git diff`, confirmed identical with `diff` before re-running.)*

```
$ TG_ATTEST_READONLY=1 uv run python -m unittest test.unit.test_hook.TestAutoModeGapLog -v
...
AttributeError: <module 'toolguard.hook' from '.../toolguard/hook.py'> does not have the attribute 'log_gap'
...
ERROR: test_unmatched_command_under_auto_mode_writes_a_gap_entry (test.unit.test_hook.TestAutoModeGapLog.test_unmatched_command_under_auto_mode_writes_a_gap_entry)
Given a real Configuration allowing only 'git *' (no_match_fallback ...
AttributeError: <module 'toolguard.hook' ...> does not have the attribute 'log_gap'

----------------------------------------------------------------------
Ran 4 tests in 0.003s

FAILED (errors=4)
```

All 4 tests in the class failed for the right reason (the wiring did not exist yet), not
for an unrelated reason.

## Step 3 -- RED: nothing written when a rule matched, and when mode is not auto (pasted)

Same RED run as step 2 covers this: `test_matched_rule_under_auto_mode_writes_nothing` and
`test_unmatched_command_outside_auto_mode_writes_nothing` are two of the four tests in that
same failing run above (both errored with the identical `AttributeError`, since the mock
target `toolguard.hook.log_gap` didn't exist yet). These are the negative cases the brief
called the ones that "give step 2 meaning" -- without them, a logger that fires on *every*
decision would also make the positive test pass.

## Step 4 -- RED: a write failure does not change the verdict (pasted)

`test_gap_log_write_failure_does_not_change_the_returned_verdict` is the fourth test in
the same RED run above (same `AttributeError`, same root cause -- the wiring, including
its own try/except safety net, did not exist yet).

## Step 5 -- GREEN: implement; register in the guard

After restoring the wiring (verified byte-identical to the pre-revert diff via `diff`):

```
$ TG_ATTEST_READONLY=1 uv run python -m unittest test.unit.test_hook.TestAutoModeGapLog test.unit.test_gap_log -v
...
Ran 9 tests in 0.004s

OK
```

Two more tests were added afterward (see "Judgements I acted on" below) to cover the
compound-command ambiguity Finding 2 flagged, bringing the class to 6 tests / 11 new tests
total. Registered `gap_log.log_gap` in `test/unit/_real_log_dir_guard.py::install()`
(alongside `log_command`/`log_discovery`/`log_conflict`/`log_error`/`log_warning`), using
the existing `_guard_simple_log_dir_arg` wrapper -- no new guard shape needed.

**Full suite**: `Ran 4032 tests in 59.7s` / `OK (expected failures=4)` -- 4021 baseline +
11 new (5 in test_gap_log.py, 6 in TestAutoModeGapLog). A changed test count is expected
this round (new tests), per the brief.

## Step 6 -- Lint and format

`uv run ruff check .` -- `All checks passed!`
`uv run ruff format --check .` -- `199 files already formatted` (after formatting one
file, `test/unit/test_hook.py`, whose line I added was one character over the wrap width;
also fixed one PRE-EXISTING format issue in `toolguard/invocation.py` -- a stray blank
line inside `for_evaluation()`, present at HEAD before this session touched anything,
incidental cleanup since the file was already being edited for `session_id`).

## Step 7 -- Architecture fitness

```
$ uv run python tools/architecture_fitness.py --stdlib
=== --stdlib: PASS ===

$ uv run python tools/architecture_fitness.py --ambient
=== --ambient: PASS -- every os import and Path ambient-member read this scan saw has an owner ===

$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness (81 modules examined) ===
All modules map to exactly one layer.
=== --layers: direction ===
No cross-layer direction violations.
```

`--ambient` did NOT pass on the first run -- see "Non-blocking findings" below for the
real false positive found and fixed here (a new `PATH_AMBIENT_OWNERS` entry, not a code
change).

## Step 8 -- Corpus equivalence

```
$ TG_ATTEST_READONLY=1 uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 11.45s. End-to-end: 61 cases in 3.99s.
OK: no differences.
```

Exact match to the brief's stated baseline (`6401` / `61`).

## Step 9 -- Calibrate before believing step 8

Planted a decision-altering one-line change in
`toolguard/permission_resolution.py::_resolve_unclamped`'s `fallback == "ask"` branch
(`decision="ask"` -> `decision="allow"`, with an inline comment marking it as the probe):

```
$ TG_ATTEST_READONLY=1 uv run python tools/corpus_build.py --verify
...
3 E2E HARD MISMATCH(ES) -- STOP AND INVESTIGATE, do not regenerate:
  [enrichment] Bash('echo hi').permissionDecision: expected='ask' actual='allow'
  [fallback_ask] Bash('echo hello').permissionDecision: expected='ask' actual='allow'
  [pattern_forms] Write('./scratch/output.txt').permissionDecision: expected='ask' actual='allow'
...
FAIL: hard verdict/output/data-integrity differences found.
```

Exit code 1 -- the instrument is sensitive. Reverted the line by editing it back (never
`git checkout`); confirmed with `git diff -- toolguard/permission_resolution.py` and
`git status --porcelain -- toolguard/permission_resolution.py` that both are EMPTY (byte-
identical to HEAD). Reran `--verify`: `OK: no differences` again, same `6401` / `61`
counts.

## Step 10 -- Entry-point smoke test

All 8 `[project.scripts]` modules import cleanly:
`toolguard.hook`, `.session_start`, `.update_check`, `.tools.security_audit`,
`.tools.maintenance`, `.tools.installer`, `.scripts.migrate_permissions`,
`.tools.update_skills` -- `OK` for each.

## Step 11 -- Confirm no real log leak

`test_zz_real_log_dir_guard` passes as part of the full suite (`OK (expected failures=4)`,
no failures reported for that module). Isolated single-file runs of that test module can
show an UNRELATED, pre-existing failure
(`test_every_sanctioned_relative_receiver_site_fired`) because one of ITS sanctioned sites
(`transcript_harvest.transcript_dir_for_project`) is only exercised by other test modules
-- confirmed this is order-dependent and not caused by this change by re-running the FULL
suite, which passes.

## Design decisions (the brief's flagged unknowns, resolved)

1. **"No rule matched" IS cleanly detectable at one place** (Step 1) -- but the
   *definition* of "no rule matched" needed care for a compound Bash command. Trigger
   function `_fallback_decided(result)`: for a Bash verdict, inspects
   `result.sub_matches` and fires if ANY non-audit-only unit has `matched_rule is None`.
   This is deliberately NOT the same as `result.matched_rule is None` at the top level --
   that field is also `None` when several sub-commands each matched a DIFFERENT real
   rule and there was simply no single decider to attribute (see
   `resolve.py::_deciding_sub_match`'s own docstring). Two new tests
   (`test_compound_with_one_matched_and_one_unmatched_leaf_writes_a_gap_entry` /
   `test_compound_with_every_leaf_genuinely_matched_writes_nothing`) pin exactly this
   distinction. File-path verdicts are never compound, so `result.matched_rule is None`
   is used directly there.
2. **A compound command is ONE gap-log entry, not several.** Chose invocation-granularity
   (matching the "governed subject" = the full raw command, same as the decision log)
   over per-leaf entries. Reasoning: this log's whole purpose is a human deciding whether
   a SHAPE is worth a new rule, and the full command text in one entry is enough for that
   -- adding per-leaf entries would double the log's complexity for a corpus nobody
   currently reads (brief: "Nothing reads the log"). Flagged as a judgement call, not
   settled by the brief.
3. **JSONL in the existing log directory, dated like the error/warning/conflict
   streams** -- NOT modeled on `toolguard-discovery.jsonl`, which does not exist (see
   Non-blocking findings). Modeled on `toolguard-error-YYYY-MM-DD.md` etc. for naming/
   rotation, and on `log_writer.py`'s own (currently unused in production)
   `LOG_FORMAT_JSONLINES` rendering for content shape.
4. **`permission_mode == "auto"` is the whole test, per the coordinator's mid-task
   clarification** -- `plan` mode is explicitly excluded (closed, not left open) since
   Claude Code's own plan mode is meant to be read-only. An unrecognised mode string
   cannot crash the hook by construction: the check is a plain string equality against
   `"auto"`, so any other value (including one this project has never seen) simply
   doesn't match and the log stays silent -- no special-casing needed.
5. **Nothing in the decision path reads this log** -- true by construction; `gap_log.py`
   has no readers anywhere in the tree, and it sits in the "observability" architecture
   layer, which nothing above "config" is even permitted to read FROM (see the layer
   rules in `.pyscn.toml`). No design smell found here to report.

## Judgements I acted on that the brief did not specify

- **Which fallback classification is honestly derivable, and where the honesty limit
  is.** `_classify_fallback_source(result)`: only the deny-side undecidable escape hatch
  is structurally unambiguous at the RuntimeVerdict altitude
  (`result.fallback_kind == "denied"`) -- confirmed by tracing `_combine_strictest` in
  `compound.py`, which shows `RuntimeVerdict.fallback_kind` is NEVER populated with
  `'warned'`/`'silent'` (only `UnitVerdict.fallback_kind` is, one level down). An
  ask-floor outcome and an allow-side escape hatch both collapse to the identical shape
  as a plain `no_match_fallback` outcome at every altitude reachable without new
  plumbing -- distinguishing them would need the deciding `CommandUnit.kind`
  (`'plain'` vs `'inline_code'`/`'undecidable'`), which `UnitVerdict` does not carry, and
  which the ONLY other route to (matching against the rendered `reason` string, e.g.
  `"Undecidable segment..."`) is exactly the "prose is output, not a data structure"
  anti-pattern this project has already been burned by once (TOO-45). Reported everything
  else as `'no_match'` rather than adding new fields to `UnitVerdict`/`CommandUnit` (would
  touch the "engine" layer for a read-only side feature explicitly out of the decision
  path -- judged not worth the risk) or guessing. Documented as a known, honest
  approximation in the code, not hidden.
- **Added `Invocation.session_id`** (not requested by name in the brief, but "session id"
  is in the brief's required field list, and `Invocation` is documented as exactly the
  right place for a new invocation-wide fact -- Phase 1 added `permission_mode` the same
  way). Threaded at the point `hook_data` is first available in `main()` (before the
  later `governed_tools`/`agent_info`/`permission_mode` replace(), since `session_id`
  needs nothing else computed first).
- **Defense in depth on the write path.** `gap_log.log_gap` already swallows every
  internal failure (mirrors `log_writer.log_command`'s "never fail the hook" contract).
  Added a SECOND try/except around the call site in `_maybe_log_auto_mode_gap` itself, so
  step 4's guarantee holds even against a bug in `log_gap` itself, not just an ordinary
  I/O failure inside it -- and made this independently testable (mocked `log_gap` to
  raise directly, bypassing its own internal handling).
- **`--ambient` false positive fixed via the owner table, not by touching gap_log.py's
  design.** See Non-blocking findings.
- **Incidental format fix** in `toolguard/invocation.py` (pre-existing stray blank line
  in `for_evaluation()`, unrelated to this ticket) -- fixed since the file was already
  being edited for `session_id`, rather than leaving a known `ruff format` violation
  sitting next to my own new code in the same file.

## Sibling sweep

Grepped the whole `toolguard/` package for any OTHER place that resolves a Bash/file-path
verdict outside `_handle_command_tool`/`_handle_file_path_tool` (`resolve_bash_permission_
detailed`, `resolve_file_path_permission_detailed`, `decide(` call sites) to confirm no
second call site needed the same wiring. Findings:
- `hook.py::_resolve_event` (the `--eval`/replay path) calls `decide()` directly, never
  `_handle_command_tool`/`_handle_file_path_tool` -- correctly excluded, since `--eval`'s
  own docstring says "resolve one piped event... without logging" and this must not
  become a second, undocumented logging path for that mode.
- `tools/corpus_build.py`'s ~6401 in-process cases call the resolver functions directly,
  bypassing `hook.py` entirely -- confirmed via grep (no `_handle_command_tool`/
  `_handle_file_path_tool`/`hook.main` references there), so they can never reach the new
  gap-log call sites, which is why step 8/9 needed no special handling for the bulk of
  the corpus. Its ~61 end-to-end cases run the REAL `toolguard` subprocess with
  `TOOLGUARD_LOG_DIR` pointed at an isolated sandbox directory (`toolguard/testing/
  sandbox.py`), so even on the rare case a fixture sets `permission_mode='auto'`, any
  resulting gap-log write is sandboxed, not a leak into the real repo.
- No other `toolguard/tools/*.py` script drives `hook.main()`'s live path at all (they
  call the config/resolution layer directly for audit/migration purposes), so no further
  call sites needed the wiring.

## Non-blocking findings for the next round

- **The brief's premise that JSONL precedent is `toolguard-discovery.jsonl` is factually
  wrong.** No such file exists anywhere in the tree. The real discovery log is
  `toolguard-discovery.log` (note: `.log`, not `.jsonl`), and its content is plain
  tab/unit-separator-delimited TEXT, not JSON at all (`log_writer.py`'s own module
  docstring and `_DISCOVERY_FIELD_SEP`/`_DISCOVERY_LEVELS_SEP` constants confirm this).
  Grepped for `jsonl`/`JSONL` across `toolguard/*.py` to confirm no other candidate
  exists. Used the error/warning/conflict dated-file convention plus `log_writer.py`'s
  real (if currently production-unused) `LOG_FORMAT_JSONLINES` rendering instead, which
  is a closer match to what the brief actually wanted (JSONL, dated, in the log
  directory) than the file it cited.
- **`--ambient` architecture-fitness false positive, found and fixed.** The scanner
  flags any bare `.cwd` ATTRIBUTE NAME (AST-level, no type-awareness) as a possible
  `Path.cwd()`/ambient read, regardless of the receiver's actual type. `GapLogEntry.cwd`
  (a plain `str` dataclass field, set from `Invocation.cwd`) tripped this. This is the
  exact same class of false positive the project already solved once, for `hook.cwd`
  (`PATH_AMBIENT_OWNERS[("hook", "cwd")]`, justified as "PreToolUseEvent.cwd, a wire
  field... not Path.cwd()"). Added a matching entry,
  `PATH_AMBIENT_OWNERS[("gap_log", "cwd")]`, with the equivalent justification, rather
  than renaming the field (which would have made `GapLogEntry.cwd` inconsistent with
  `Invocation.cwd`'s own naming) or silently ignoring the check.
- **JetBrains IDE**: files were opened via `mcp__jetbrains__open_file_in_editor` for
  review; no issues encountered.
- **Coverage tooling** (`tools/coverage_stdlib.py`) was not run -- not one of the brief's
  11 mandated steps, and the new code is fully exercised by the 11 new unit tests (both
  positive and negative branches of every new function). Available on request.

## Timing and estimated cost

- Reading brief, spec, plan, and tracing the resolver internals (`resolve.py`,
  `compound.py`, `config_types.py`, `permission_resolution.py`) to answer the brief's
  unverified claims: ~35 min, ~$0.65
- Architecture-layer check (`.pyscn.toml`) before writing `gap_log.py`, which changed the
  module design (writer/dataclass split) before any code was written: ~5 min, ~$0.10
- Implementation (`gap_log.py`, `hook.py` wiring, `invocation.py`, guard registration,
  `.pyscn.toml`): ~20 min, ~$0.35
- TDD cycle: writing tests, reverting/restoring hook.py for genuine RED evidence,
  re-running for GREEN, adding the two compound-command tests: ~25 min, ~$0.45
- Debugging the `--ambient` false positive and fixing it via the owner table: ~10 min,
  ~$0.20
- Full verification pass (suite, ruff, 3 fitness checks, corpus, calibration probe,
  entry points, guard test): ~15 min, ~$0.25
- basic-memory write-up (including working around a permalink-overwrite quirk in the
  MCP server -- see below): ~15 min, ~$0.25
- Report writing: ~10 min, ~$0.15
- **Total: ~135 min, ~$2.40** (Claude Sonnet 5, rough token-based estimate)

## Addendum -- coordinator round-trip correction + retraction (2026-09-06)

Coordinator verified end-to-end (live hook run, `permission_mode: auto`, unmatched
command wrote a well-formed entry with every briefed field) and sent back one correction
and one retraction. Both addressed; full verification set re-run.

**1. CORRECTION, applied.** `_classify_fallback_source` was reporting `FALLBACK_SOURCE_NO_MATCH`
as a default for every case it could not prove -- correctly identified as a guess, not a
fact: a wrong label corrupts the corpus permanently since the information to fix it later
was never captured, whereas an honest `unknown` stays accurate forever. Added
`FALLBACK_SOURCE_UNKNOWN` to `gap_log.py`. `_classify_fallback_source` now returns
`FALLBACK_SOURCE_UNDECIDABLE` only for the one provable case
(`fallback_kind == "denied"`) and `FALLBACK_SOURCE_UNKNOWN` for everything else.
`FALLBACK_SOURCE_NO_MATCH` stays defined (reserved for a future classifier that CAN prove
it, e.g. if `CommandUnit.kind` is ever plumbed through) but is not emitted by anything
today -- documented as such in both the module-level docstring and the classifier's own.

Added 5 new tests: `TestClassifyFallbackSource` (4 tests, direct against hand-built
`RuntimeVerdict`s -- denied->undecidable, and ask/allow/deny with no fallback_kind all ->
unknown, never no_match) plus one new end-to-end wiring test,
`test_undecidable_deny_under_auto_mode_writes_undecidable_source` (real Configuration,
`undecidable_fallback='deny'`, a foreign-inline-code command, confirms the wiring
surfaces `undecidable` correctly, not just the direct unit test). Updated the one
existing test that asserted `no_match` to assert `unknown` instead, with its docstring
corrected to explain why.

**2. RETRACTION, applied.** My non-blocking finding claimed `toolguard-discovery.jsonl`
"does not exist" -- wrong; it exists (a stale Jul 31 artifact, confirmed by the
coordinator both before writing the brief and again just now). The substantive point
survives: the LIVE discovery log is `toolguard-discovery.log` (plain text, dated Sep 2),
so the `.jsonl` file is stale and a weak precedent, not a nonexistent one. Restated below
and in this note's own finding.

**Verification re-run in full** (per the coordinator's request):
- Suite: `Ran 4037 tests in 59.1s` / `OK (expected failures=4)` -- 4032 (prior round) + 5
  new.
- `uv run ruff check .` -- `All checks passed!`; `uv run ruff format --check .` -- `199
  files already formatted`.
- `--stdlib` / `--ambient` / `--layers` -- all PASS, all exit 0 (no ambient-owner changes
  needed this round; the correction touched no `Path`/`os` surface).
- Corpus: `OK: no differences`, `6401` / `61`.
- Calibration re-run: planted the SAME `permission_resolution.py` probe used last round
  (`decision="ask"` -> `decision="allow"` in the `no_match_fallback=ask` branch),
  `--verify` FAILED (3 hard mismatches, exit 1), reverted, `git status --porcelain` and
  `git diff` both empty for that file, `--verify` passed again (`6401`/`61`).
- All 8 console-script entry points import cleanly.
- `test_zz_real_log_dir_guard` passes within the full suite run (no failures reported for
  that module).

**Non-blocking finding, corrected**: ~~"The brief's premise that JSONL precedent is
`toolguard-discovery.jsonl` is factually wrong -- that file doesn't exist"~~ is WRONG as
stated. `logs/toolguard-discovery.jsonl` exists (a stale Jul 31 artifact). The accurate
finding: the file is stale and is NOT the live discovery log (`toolguard-discovery.log`,
plain text, dated Sep 2), so it is a weak precedent for this ticket's JSONL choice, not a
nonexistent one. The dated error/warning/conflict convention plus `log_writer.py`'s real
`LOG_FORMAT_JSONLINES` rendering remain the better-justified choice either way.

## Addendum 2 -- coordinator round-trip, "no_match" is provable for file paths (2026-09-06)

Coordinator verified round 1's correction (`fallback_kind == "denied"` genuinely proves
`undecidable`) and a live hook run confirms `unknown` for a plain unmatched Bash command.
But flagged that round 1 over-corrected: for a **file-path** tool specifically, `no_match`
IS provable, not just a guess, and a field where every row says `unknown` is as useless as
not recording it.

**Investigated as directed, not taken on trust.** Traced `resolve_file_path_permission` ->
`resolve_permission_cascade` -> `_apply_ask_floor` in `permission_resolution.py`. Two facts
combine to make this provable:

1. File paths genuinely have no `undecidable_fallback` concept
   (`resolve.py::resolve_file_path_permission_detailed`'s own comment, confirmed by
   reading the code, not just quoting the comment).
2. The ONE other mechanism that can also clear a file-path verdict's `matched_rule` to
   `None` -- the parse-failure ASK floor (`_apply_ask_floor`) -- REBUILDS the verdict
   (wiping `matched_rule` even off a **genuine rule match**) only when
   `Configuration.parse_failures` is non-empty; it is a complete no-op when
   `parse_failures` is empty (`if not parse_failures or resolved.decision == "deny": return
   resolved`, unchanged).

So: a fallback-decided file-path verdict with an EMPTY `invocation.config.parse_failures`
has no other explanation than `_resolve_unclamped`'s own no-match branch -- provably
`no_match`. With a NON-empty `parse_failures`, the floor cannot be ruled out (it can even
overwrite an already-`ask` no-match verdict's own reason text), so it stays `unknown`,
exactly as the coordinator's decision tree specified.

**Applied**: `_classify_fallback_source(result, invocation)` (now takes `invocation` too)
emits `FALLBACK_SOURCE_NO_MATCH` when `invocation.tool_name in FILE_PATH_TOOLS and not
invocation.config.parse_failures`; `FALLBACK_SOURCE_UNDECIDABLE` for the proven deny-side
case; `FALLBACK_SOURCE_UNKNOWN` for everything else (all Bash cases beyond the denied one,
and file-path with non-empty `parse_failures`). `no_match` is no longer a dead constant.

**5 new tests**: 2 direct (`TestClassifyFallbackSource`: file-path + empty parse_failures
-> no_match; file-path + non-empty parse_failures -> unknown) plus 1 end-to-end
(`test_unmatched_file_path_under_auto_mode_writes_no_match_source`, a real Read
Configuration, unmatched path, confirms the wiring surfaces `no_match`, not just the unit
test), and 2 renamed/clarified existing Bash tests (now explicit that the file-path
exclusion does not apply to Bash).

**Verification re-run in full**: `Ran 4040 tests` / `OK (expected failures=4)` (4037 +
3 new this round); `ruff check .` -- all checks passed; `ruff format --check .` -- 199
files already formatted; `--stdlib`/`--ambient`/`--layers` all PASS; corpus `OK: no
differences`, `6401`/`61`; calibration re-run (same `permission_resolution.py` probe,
`--verify` FAILED, reverted, `git status --porcelain`/`git diff` both empty, `--verify`
passed again); all 8 entry points import cleanly; `test_zz_real_log_dir_guard` passes
within the full suite.

## Addendum 3 -- naming correction, pure rename plus one data-quality fix (2026-09-06)

Arnon's review of the actual log output: "gap" is the wrong frame -- it is a
purpose-built trace of what toolguard defers under auto mode, not a patch over a
deficiency. Three changes, no behaviour moves:

1. **Renamed throughout**: `toolguard/gap_log.py` -> `toolguard/auto_mode_trace.py`;
   `GapLogEntry` -> `AutoModeTraceEntry`; `log_gap` -> `log_auto_mode_trace`;
   `hook.py::_maybe_log_auto_mode_gap` -> `_maybe_trace_auto_mode`; the on-disk filename
   `toolguard-gap-<date>.jsonl` -> `toolguard-automode-<date>.jsonl`. `FALLBACK_SOURCE_*`
   kept as-is (already approved). Updated every docstring/comment describing this
   feature, the test module (`test_gap_log.py` -> `test_auto_mode_trace.py`, classes and
   methods renamed), the `_real_log_dir_guard.install()` registration, the
   `.pyscn.toml` "observability" layer entry, and the `tools/architecture_fitness.py`
   ambient-owner entry.

   **Swept the whole tree afterward** (`grep -rni gap toolguard/ test/ tools/
   .pyscn.toml`): every remaining hit is pre-existing, unrelated English usage (coverage
   gaps, config-shape gaps, a "negation gap" in gitignore handling, frozen
   `test/verdict_corpus/` fixtures) -- none describes this feature. One specifically
   checked and left alone: `test_hook.py:1538`'s "the undecidable_fallback half of the
   same no_match_fallback gap" is a pre-existing, unrelated docstring about fallback
   documentation coverage, not this log.

2. **`subject` -> `target`** on `AutoModeTraceEntry` and the `_maybe_trace_auto_mode`
   parameter -- toolguard already has this word (`api.decide`'s parameter,
   `RuntimeVerdict.target`, an identical docstring), so a second word for the same
   concept was unjustified duplication.

3. **Data-quality fix**: a `Read`/`Write`/`Edit` row now records the BARE file path,
   not the decision log's rendered `Tool(path)` wrapper -- the wrapper duplicated the
   `tool_name` field beside it and forced any consumer grouping by path to strip a
   prefix first. Fixed at the call site in `_handle_file_path_tool` (passes `file_path`
   directly instead of `log_target`); Bash was already bare. Updated/renamed the
   end-to-end test to pin `entry.target == "/other/path.txt"` (not
   `"Read(/other/path.txt)")`.

**Verification re-run in full**: `Ran 4040 tests` / `OK (expected failures=4)` (same
count as the prior round -- pure rename, no test added or removed); `ruff check .` --
all checks passed; `ruff format --check .` -- 199 files already formatted; `--stdlib`/
`--ambient`/`--layers` all PASS; corpus `OK: no differences`, `6401`/`61`; calibration
re-run (same `permission_resolution.py` probe, `--verify` FAILED, reverted, `git status
--porcelain`/`git diff` both empty, `--verify` passed again); all 8 entry points import
cleanly; `test_zz_real_log_dir_guard` passes within the full suite.

## Addendum 4 -- fallback_cause: allow-side undecidable, parse_failure, and the rename (2026-09-06)

Two coordinator rounds, addressed together since the second (the field rename) landed
mid-implementation of the first.

**Round A -- the allow-side undecidable bug.** My prior claim that only the deny-side escape
hatch is provable was WRONG. `RuntimeVerdict.fallback_kind` only ever carries the deny side
(confirmed: its own docstring calls it "the deny-side counterpart of UnitVerdict.fallback_kind"),
but `UnitVerdict.fallback_kind` -- available on every entry of `RuntimeVerdict.sub_matches`,
already read for the per-leaf no-match check -- carries the allow side too ('warned'/'silent').
No `CommandUnit.kind` lookup was ever needed. **Verified empirically, not trusted from the
coordinator's reading**: traced `_judge_inline_code_unit` in compound.py, then ran
`node -e "console.log(1)"` against this repo's own real config
(`undecidable_fallback = "allow_with_no_warnings"`) -- confirmed `sub_matches[0].fallback_kind
== 'silent'` and the classifier now returns `undecidable`. Also verified the default ask-floor
case still correctly returns `unknown` (fallback_kind stays None there), and that an `audit_only`
sub_matches entry's own 'warned' (from an unrelated substitution's ordinary
no_match_fallback=allow_with_warning) does NOT get misread as the escape hatch -- excluded via
the same `audit_only` filter `_fallback_decided` already uses.

**Round A also added a third, determinable cause: `parse_failure`.** The configuration's own
`parse_failures` being non-empty combined with a non-'deny' decision is UNCONDITIONAL proof --
`permission_resolution.apply_parse_failure_floor`'s own hard invariant floors every non-deny
leaf/path to 'ask' regardless of what it would otherwise have resolved to, wiping `matched_rule`
the same way a genuine fallback would. **Verified empirically**: planted a non-empty
`parse_failures` on (a) a plain unmatched Bash command, (b) a `node -e` foreign-inline-code
command under `undecidable_fallback=allow`, (c) a genuine Bash deny rule match, (d) an unmatched
file path -- (a), (b), (d) all collapsed to identical shape (`decision='ask'`, `matched_rule=None`,
`fallback_kind=None`), confirming the floor masks whatever the undecidable escape hatch would
otherwise have shown; (c) was UNAFFECTED (deny bypasses the floor entirely), confirming a plain
Bash `no_match_fallback=deny` correctly stays `unknown` regardless of `parse_failures`.

**Found and fixed a real bug while implementing this**: the new unconditional `invocation.
config.parse_failures` read would have crashed (`AttributeError`) on the several existing tests
that build a minimal `Invocation` with `config=None`. Guarded with `invocation.config.
parse_failures if invocation.config is not None else ()` -- the live call site always has a real
`Configuration` by this point, so this only protects test-only synthetic invocations.

**Round B -- naming.** Arnon: *"fallback_source is about WHY there was a fallback. It has
nothing to do with the final outcome."* Renamed `fallback_source` -> `fallback_cause`
throughout (field, JSON key, `FALLBACK_SOURCE_*` -> `FALLBACK_CAUSE_*`,
`_classify_fallback_source` -> `_classify_fallback_cause`), and reframed
`_undecidable_escape_hatch_fired`'s check from an enumerated `in ('warned','silent','denied')`
to a plain `is not None` -- matching the "collapse outcome flavours into one cause" instruction
exactly, since those three values ARE `UnitVerdict.fallback_kind`'s only non-None values.
`UnitVerdict`/`RuntimeVerdict.fallback_kind` themselves were explicitly OUT of scope (a separate
future commit, to avoid touching the 17 `fallback_kind` occurrences in the frozen
`test/verdict_corpus/goldens.jsonl`) -- not touched.

Added the triage-mapping paragraph to the `FALLBACK_CAUSE_*` docstring per Arnon's stated use
(each value implies a different response: `no_match` -> write a rule; `undecidable` -> no rule
ever can, needs a feature or auto-mode guidance instead -- explicitly the case spec section 2
names as the design smell to avoid; `parse_failure` -> fix the config; `unknown` -> investigate,
not triageable).

**New/changed tests** (test_hook.py): `test_allow_side_escape_hatch_in_sub_matches_is_undecidable`,
`test_audit_only_escape_hatch_shaped_entry_is_not_undecidable`,
`test_bash_fallback_with_parse_failures_is_parse_failure`,
`test_deny_decision_with_parse_failures_bypasses_the_floor_stays_unknown` (all new, direct
classifier tests); `test_undecidable_allow_under_auto_mode_writes_undecidable_cause` and
`test_broken_config_under_auto_mode_writes_parse_failure_cause` (new end-to-end tests, real
Configuration, driven through `_handle_command_tool`); renamed
`test_file_path_tool_fallback_with_parse_failures_is_unknown` ->
`..._is_parse_failure` with its assertion corrected to the new, more precise cause. 6 net new
tests this round (4046 total, up from 4040).

**Live sample regenerated** per the coordinator's request: piped a real `PreToolUse` event
(`node -e "console.log(1)"`, `permission_mode: "auto"`) into `uv run python -m toolguard.hook`
from the repo root, against this repo's REAL config. Resulting row, left in place at
`logs/toolguard-automode-2026-09-06.jsonl` for review:

```json
{"timestamp": "2026-09-06T14:00:45.448416", "tool_name": "Bash", "target": "node -e \"console.log(1)\"", "decision": "allow", "fallback_cause": "undecidable", "permission_mode": "auto", "session_id": "live-sample-too28", "cwd": "/home/arnon/projects/toolguard", "agent_info": "main"}
```

**Verification re-run in full**: `Ran 4046 tests` / `OK (expected failures=4)` (4040 + 6 new);
`ruff check .` -- all checks passed; `ruff format --check .` -- 199 files already formatted;
`--stdlib`/`--ambient`/`--layers` all PASS; corpus `OK: no differences`, `6401`/`61`; calibration
re-run (same `permission_resolution.py` probe, `--verify` FAILED, reverted, `git status
--porcelain`/`git diff` both empty, `--verify` passed again); all 8 entry points import cleanly;
`test_zz_real_log_dir_guard` passes within the full suite.

## Addendum 5 -- revert the allow-side undecidable detection: it emitted a false label (2026-09-06)

**The coordinator's round-4 instruction (Addendum 4, "Round A") was wrong, and I implemented it
without independently re-deriving the claim from first principles -- I verified the ONE case
it predicted (`node -e`) but never checked the negative case (a plain unmatched command) against
the new code path.** A live sample the coordinator regenerated caught it: under this repo's own
`no_match_fallback = "allow_with_no_warnings"`, a plain, perfectly readable, unmatched command
(`some-unmatched-command-xyz --flag`) was being labelled `undecidable` -- the one cause that
tells a reader "no rule can ever address this", when writing a rule is exactly the fix. It
inverted the triage the field exists for.

**Root cause**: `resolve.py:276-278`'s plain `no_match_fallback` allow path
(`fallback_kind = "warned" if resolved.fallback_warning else "silent"`) sets the IDENTICAL
values `compound.py`'s undecidable escape hatch sets. `UnitVerdict.fallback_kind is not None`
means "some allow-side fallback decided this leaf" -- covering BOTH causes -- and cannot
separate them. My round-4 verification tested only the positive case the coordinator predicted
(`node -e` under `undecidable_fallback=allow`) and never drove the SAME predicate against an
ordinary unmatched command, which is exactly the gap that let this ship.

**Reverted** `_undecidable_escape_hatch_fired` to the one provable case:
`RuntimeVerdict.fallback_kind == "denied"`. Dropped the `sub_matches` scan entirely. The real
finding is now recorded in the function's own docstring: the undecidable-vs-no-match
distinction is NOT derivable from `fallback_kind` on the allow side, because the fact that a
unit was undecidable (`CommandUnit.kind` in `compound.py`) is discarded before it ever reaches
`UnitVerdict` -- `fallback_kind` there is an OUTCOME flavour ("allowed with/without a warning"),
shared by the plain no-match path and the escape hatch alike, never a CAUSE marker. This is
named explicitly as the reason `FALLBACK_CAUSE_UNKNOWN` exists for the allow-side/ask-floor
cases, so a future reader does not repeat the mistake by reading `fallback_kind` as a cause.

**Everything else from round 4 kept**: `fallback_cause` naming, the `parse_failure` cause, the
file-path `no_match` case, the triage docstring -- all still correct and unaffected by this
revert (they never touched the allow-side sub_matches scan).

**Tests**: removed 2 tests that pinned the now-reverted (wrong) behavior
(`test_allow_side_escape_hatch_in_sub_matches_is_undecidable`,
`test_audit_only_escape_hatch_shaped_entry_is_not_undecidable`); replaced with
`test_sub_matches_entry_shaped_like_the_escape_hatch_is_not_undecidable` (direct classifier
test, asserting `unknown` for the exact ambiguous shape) and
`test_plain_unmatched_command_under_auto_mode_never_writes_undecidable_cause` (end-to-end,
`no_match_fallback=allow_with_no_warnings`, the precise scenario that broke live -- asserts
both `assertNotEqual(..., UNDECIDABLE)` and `assertEqual(..., UNKNOWN)`). Updated
`test_undecidable_allow_under_auto_mode_writes_unknown_cause` (renamed from
`..._writes_undecidable_cause`) to assert the corrected `unknown` outcome. Net test count
unchanged this round (4046 -> 4046: -2 removed, +2 added).

**Live samples regenerated and pasted, all three requested cases**, via a real `PreToolUse`
event piped into `uv run python -m toolguard.hook` from the repo root, against this repo's
REAL config. Removed the stale (wrong) sample from the prior round first. Resulting rows, left
in place at `logs/toolguard-automode-2026-09-06.jsonl`:

```json
{"timestamp": "2026-09-06T14:10:41.577474", "tool_name": "Bash", "target": "node -e \"console.log(1)\"", "decision": "allow", "fallback_cause": "unknown", "permission_mode": "auto", "session_id": "live-sample-too28-r2", "cwd": "/home/arnon/projects/toolguard", "agent_info": "main"}
{"timestamp": "2026-09-06T14:10:41.678770", "tool_name": "Bash", "target": "some-unmatched-command-xyz --flag", "decision": "allow", "fallback_cause": "unknown", "permission_mode": "auto", "session_id": "live-sample-too28-r2", "cwd": "/home/arnon/projects/toolguard", "agent_info": "main"}
{"timestamp": "2026-09-06T14:10:41.761517", "tool_name": "Read", "target": "/tmp/some-unmatched-path-xyz.txt", "decision": "allow", "fallback_cause": "no_match", "permission_mode": "auto", "session_id": "live-sample-too28-r2", "cwd": "/home/arnon/projects/toolguard", "agent_info": "main"}
```

`node -e` (genuinely undecidable) and the plain unmatched command now BOTH correctly read
`unknown` -- honest, since this repo's config makes them genuinely indistinguishable -- instead
of the plain command being wrongly labelled `undecidable`. The unmatched `Read` still correctly
reads `no_match`.

**Verification re-run in full**: `Ran 4046 tests` / `OK (expected failures=4)`; `ruff check .`
-- all checks passed; `ruff format --check .` -- 199 files already formatted; `--stdlib`/
`--ambient`/`--layers` all PASS; corpus `OK: no differences`, `6401`/`61`; calibration re-run
(same `permission_resolution.py` probe, `--verify` FAILED, reverted, `git status --porcelain`/
`git diff` both empty, `--verify` passed again); all 8 entry points import cleanly;
`test_zz_real_log_dir_guard` passes within the full suite.

## Addendum 6 -- carry the cause structurally instead of inferring it (2026-09-06)

Arnon: *"make sure that the cause IS preserved and makes its way upwards so it does NOT get
lost"* -- and this project's own rule: *"Accumulate structured results... you cannot recover
what you discarded."* The prior two rounds were both re-deriving a cause downstream from a
field (`fallback_kind`) that structurally cannot carry it; this round carries the cause itself,
set once, where it is actually known.

**Traced before writing code, per the coordinator's "do not take this on trust" instruction.**
Confirmed empirically (see live samples below) at each of the three points cause is genuinely
known and was being discarded:

- `permission_resolution.py::_resolve_unclamped`'s no-match branches (5 of them) know
  structurally "no rule matched", independent of what `no_match_fallback` then decided
  (allow/ask/deny) -- the coordinator's trap #1 exactly: outcome-gating the OLD
  `fallback_kind` computation (`decision == "allow" and matched_rule is None`) was too narrow.
- `compound.py`'s undecidable branches (`_judge_undecidable_unit`, all of
  `_judge_inline_code_unit`'s floor-fired branches) know "the leaf could not be read",
  independent of outcome too.
- Where a branch does NOT decide (an explicit rule fired ahead of the floor, in
  `_judge_inline_code_unit`), the cause is PROPAGATED from the deciding sub-verdict rather than
  guessed -- `None` if that was a genuine rule match, `'no_match'` if IT was itself a no-match
  outcome.

**Added `UnitVerdict.fallback_cause`/`RuntimeVerdict.fallback_cause`** (`config_types.py`),
values `'no_match'` / `'undecidable'` / `None`. **`fallback_kind` untouched**, as instructed --
still under that name, still doing what it always did.

**Aggregation to `RuntimeVerdict`** follows the EXACT existing pattern `fallback_kind` already
uses in `_combine_strictest` (deny: single first-decider; ask: single first-decider; allow:
single-allowed-unit propagates, MULTIPLE allowed units do not -- matching how `matched_rule`/
`provenance` already treat that exact ambiguity). **This resolves item 3 honestly**: the
"genuinely ambiguous, mixed causes" case is a real, narrow one -- a compound where two or more
LEAVES ALL ALLOW via DIFFERENT causes (e.g. one leaf a genuine rule match, another a plain
no-match) has no single cause to report, and `RuntimeVerdict.fallback_cause` correctly stays
`None` there, same as the pre-existing `matched_rule`/`provenance` ambiguity for that exact
shape. New end-to-end test pins this
(`test_compound_with_mixed_causes_across_allowed_leaves_writes_unknown_cause`) -- this IS now
the "genuinely untagged -> unknown" case the coordinator wanted preserved, not the (wrong)
prior round's "everything except deny is unknown".

**hook.py's classifier simplified drastically**: deleted `_undecidable_escape_hatch_fired`
entirely; `_classify_fallback_cause` now just checks `parse_failures` first (unchanged,
independent, config-based -- correctly takes precedence since the floor can overwrite a
carried cause) then reads `result.fallback_cause` directly. No more scanning, no more
inferring, no more `FILE_PATH_TOOLS` branching for `no_match` (file paths get it via the SAME
`_resolve_unclamped` no-match branch Bash uses).

**The frozen goldens, verified BEFORE writing any code, not assumed**: read
`fixture_loader.py::unit_verdict_to_dict`/`decision_to_golden` and confirmed both are
hand-written dicts explicitly whitelisting 4/9 fields respectively -- neither dumps the
dataclass generically, so the new field structurally cannot leak in. Corpus confirmed
`OK: no differences` afterward, as predicted rather than hoped.

**Docstring corrections** (separate coordinator instruction, addressed in the same round --
Arnon: *"a confidently-worded wrong docstring is worse than no docstring, because it stops the
reader going to the code"*):
- `UnitVerdict.fallback_kind`: REWRITTEN. Deleted the writer enumeration ("'warned'/'silent'
  name the allow escape hatch...") that had gone stale the moment `resolve.py`'s plain
  no-match path started setting the same values, and that omission is exactly what produced
  the false `undecidable` label two rounds ago. Now states the invariant (an outcome flavour)
  and the crucial negative explicitly (does NOT identify which fallback fired), pointing at
  `fallback_cause`.
- `RuntimeVerdict.fallback_kind`: left unchanged, per instruction -- re-verified against the
  same test (every claim checked against the actual writers) and found accurate.
- `_combine_strictest`'s own docstring: trimmed the `Args`/`Returns` sections that enumerated
  per-field mechanics now stated once, generically, for both `fallback_kind` and
  `fallback_cause` together.
- `auto_mode_trace.py`'s `FALLBACK_CAUSE_*` comment: the "which mechanism sets which value"
  paragraph was REWRITTEN -- the old version described the round-5 sub_matches-scanning
  mechanism (already reverted) and had gone stale/wrong in the same shape as the
  `fallback_kind` docstring. Replaced with a one-line pointer to `RuntimeVerdict.
  fallback_cause` as the source of truth; kept the triage-response paragraph (a claim about
  values, not about writers, so it was never affected).
No claim was found worth deleting outright rather than rewriting -- each one, once corrected,
was still worth stating.

**Tests**: rewrote `TestClassifyFallbackCause` from scratch (9 tests -> 5) to match the now
much simpler classifier -- direct tests read `fallback_cause`/`parse_failures` precedence
only, no more hand-built `sub_matches` shapes (that mechanism is gone). Fixed 3 end-to-end
tests whose expected values were STALE UNKNOWNs that are now correctly `no_match`/
`undecidable`. Added the mixed-causes compound test above. Net: 4046 -> 4043 (-4 direct, +1
end-to-end).

**Live samples regenerated exactly as requested, all three cases, pasted below** (stale
samples from the reverted round removed first):

```json
{"target": "node -e \"console.log(1)\"", "decision": "allow", "fallback_cause": "undecidable", ...}
{"target": "some-unmatched-command-xyz --flag", "decision": "allow", "fallback_cause": "no_match", ...}
{"tool_name": "Read", "target": "/tmp/some-unmatched-path-xyz.txt", "decision": "allow", "fallback_cause": "no_match", ...}
```

`node -e` now correctly and PROVABLY reads `undecidable` (structurally set, not inferred), and
the plain unmatched command now correctly reads `no_match` -- the two are FINALLY
distinguished in the common single-leaf case, which is most of what this feature exists for.

**Verification re-run in full**: `Ran 4043 tests` / `OK (expected failures=4)`; `ruff check .`
-- all checks passed; `ruff format --check .` -- 199 files already formatted; `--stdlib`/
`--ambient`/`--layers` all PASS; corpus `OK: no differences`, `6401`/`61` (confirming the
goldens verification above); calibration re-run (same `permission_resolution.py` probe,
`--verify` FAILED, reverted, `git diff` on that file shows only the legitimate `fallback_cause`
additions, `--verify` passed again); all 8 entry points import cleanly; `test_zz_real_log_dir_
guard` passes within the full suite.

**Footprint note**: this round touched 4 production files beyond `hook.py`/`auto_mode_trace.py`
(`config_types.py`, `permission_resolution.py`, `resolve.py`, `compound.py`) -- the core
resolver, explicitly out of scope in earlier rounds of this same phase. Flagging per the
scope-inflation guidance: this was coordinator-directed, incrementally, with an explicit
"if genuinely ambiguous, report rather than guess" escape valve I used once (the mixed-causes
case). Worth a look at whether this phase's file count should have been budgeted differently
from the outset, not a request to undo anything now.

## STALE CONTENT BELOW (prior Phase 1 Round 4 report -- ignore)

---

## Summary

Deleted the unpacking aliases rounds 1-3 re-created inside function bodies after
collapsing signatures to take one `Invocation`/context object. Read through
`invocation.x` / `context.x` at every use site instead. Behavior-neutral: no signature
changes, no test changes.

## Step 1: candidate classification (re-measured, not trusted from the brief)

Re-ran the brief's grep (`^\s*[a-z_]+ = (invocation|context)\.`) and cross-checked with
an AST scan that also catches multi-line assignments and nested-attribute chains the
line-based grep would miss. Both methods agreed exactly: **37 pure aliases** (not the
brief's claimed 39 -- see correction below), classified as:

- **35 deletable pure aliases** across the 4 files (single attribute, target name ==
  attribute name, used inside their function).
- **1 reassigned local, kept**: `config = invocation.config` in
  `_run_startup_validation` (hook.py), immediately followed by
  `if config is None: config = load_configuration(invocation.cwd)`. This is the
  documented `test_validation_loads_config_when_none` behavior. **Kept exactly as-is.**
- **1 `or {}` default alias**, resolved via the dataclass-default fix (see Step 2)
  rather than left in place: `env_config = invocation.env_config or {}` in the same
  function -- this one wasn't in the brief's list of 4 "or {}" sites (see correction
  below) but is the same shape and got the same fix.

**Correction to the brief's count**: the brief said 39 across
hook.py(27)/permission_resolution.py(6)/resolve.py(3)/file_matching.py(3), citing
`hook.py:846` (`takeover = invocation.config.takeover_mode()`) and `hook.py:677`
(`target = invocation.tool_input.get(key, "")`) as the two out-of-scope exceptions
inside that 39. My independent count of the SAME shape (`x = invocation.x` /
`x = context.x`, single attribute, name matches) is **37**, not 39 -- the brief's grep
was looser than its own stated shape and swept in those two out-of-scope lines as part
of its "39", then separately excluded them by name. Net effect on scope is nil (both
methods agree on the identical set of lines to actually delete), but the count itself
should read 37, and among those 37 there were actually **4 `or {}` sites**, not the "4"
the brief already knew about at 3 different locations -- the brief listed
`hook.py:81, 795, 847, 872`, which IS 4 sites and IS complete; my earlier draft of this
report miscounted a 5th before rechecking. Confirmed final: exactly 4 `or {}` sites,
all in hook.py, all listed correctly in the brief.

**Reassignment check (the brief's stated highest-risk item, which the brief author had
not checked)**: wrote an AST-based checker that, for each of the 37 candidates, finds
its enclosing function and scans the WHOLE function body for any other assignment to
the same local name. Result: **exactly one reassigned candidate**
(`_run_startup_validation`'s `config`), matching the deliberate documented case the
brief called out by name. No other candidate is reassigned. This was checked
mechanically, not by inspection, given the brief's explicit warning that it hadn't been
checked and might not be caught by the corpus.

## Step 2: env_config `or {}` decision

**Took the brief's preferred fix**: gave `Invocation.env_config` a non-`None` default
(`field(default_factory=lambda: MappingProxyType({}))`, the idiom already used in
`rule_entry.py`), and updated its docstring to say so. Verified before applying:

- Grepped every `.env_config` reader and every `Invocation(...)` construction site
  (production and test) -- **no caller anywhere passes `env_config=None` explicitly**,
  and no code anywhere checks `invocation.env_config is None` as a distinct state from
  `{}`. The docstring's prior claim ("`None` when there is no real environment being
  evaluated") described an distinction nothing actually reads.
- `Invocation.for_evaluation()` (used by `api.decide()` and ~130 test call sites) never
  passes `env_config`, so it already picks up the new default -- previously `None`, now
  `{}`. None of its callers reach any of the four functions whose `or {}` I removed
  (`_run_startup_validation`, `_log_config_discovery`, `_resolve_takeover_mode`,
  `_run_divergence_check`), so this is safe.
- All 4 `or {}` sites in hook.py (lines 81, 795, 847, 872 at the brief's numbering)
  removed; each alias then became pure and was deleted along with the others.

## Step 3: deletions and inlining

All 35 pure aliases (plus the 4 `or {}` cases, now pure) deleted, inlined at use sites
via `invocation.x` / `context.x`. Also deleted the two explanatory comments in
`_handle_file_path_tool` and `_handle_command_tool` ("Local names, not `invocation.` at
each of the ~40/~30 use sites below") -- these were the literal round-2 justification
text the brief rejects, left behind as dead commentary once the aliases they explained
were gone.

Use-site counts after inlining, worst case: `_resolve_event`'s `invocation.tool_name`
(5 uses) and `resolve_bash_permission_detailed`'s `invocation.config` (4 uses, one
inside a nested closure). Judged both still readable at that count; did not rename
`invocation`/`context` to `inv`/`ctx` anywhere, since no single function's readability
genuinely suffered enough to justify a asymmetric rename (brief permits but does not
require renaming, and a rename in one function while ~15 others keep the full name
would itself be an inconsistency the brief warns against).

**One caught-by-tests bug during editing, worth flagging explicitly**: on the first
pass I missed a second bare `tool_name` reference in `resolve.py`'s
`resolve_file_path_permission_detailed` (line 133, in the non-hard-deny return path --
the hard-deny path at line 112 was fixed, the fallthrough path was not). The full
`unittest` run caught it immediately (3+ `NameError` failures). Followed up with an
AST-based scope checker across all 4 edited files, scanning every function for a bare
`Name(Load)` reference to any deleted alias name not bound in that function's own or
enclosing scope -- confirms zero remaining leftover references anywhere in the 4 files,
not just in the paths the test suite happens to exercise.

## No widening

No signature changes, no behavior changes, no functions touched outside the 4 named
files. Nothing renamed except local variable deletions/inlining described above.

## Judgements made that the brief did not specify

1. Did not rename any `invocation`/`context` parameter to `inv`/`ctx` -- judged none of
   the touched functions wordy enough to need it (max 5 uses of one attribute in one
   function). Flagging per the brief's own request for "one concrete counter-example"
   the other way: none found.
2. Deleted the two "Local names, not `invocation.`..." comments as dead commentary once
   their aliases were gone, rather than leaving them as historical notes -- they
   directly restated the round-2 rationale the brief rejects, so keeping them would
   have left a comment arguing against the code beneath it.
3. Corrected the brief's stated count from 39 to 37 (see Step 1) -- the two "excluded by
   name" lines (`hook.py:677` target lookup, `hook.py:846` takeover computed value) were
   swept into the brief's raw grep count and then separately carved back out; the actual
   deletable-candidate count under the brief's own stated definition ("`x = <context>.x`")
   is 37, and the scope (which lines to touch) is identical either way.

## Sibling sweep (step 9)

`grep -rnE '^\s*[a-z_]+ = (invocation|context|inv|ctx)\.' toolguard/` across the WHOLE
package (not just the 4 files) after all edits. Remaining hits, all correctly excluded:

- `permission_resolution.py:394,439` -- `levels = context.config.method(...)`: computed
  (method call), not a pure alias.
- `resolve.py:245` -- `looked_past = invocation.config.method()`: computed.
- `hook.py:77` -- the accepted reassigned `config` in `_run_startup_validation`.
- `hook.py:81,790,864,1088` -- `log_dir`/`disco_log_dir`/`conflict_log_dir` =
  `invocation.env_config.get("log_dir")`: differently-named lookups, not aliases.
- `hook.py:671,999,1067` -- `target`/`file_path`/`command` =
  `invocation.tool_input.get(key, "")`: differently-named lookups (the brief's own
  named exception at 677, plus two of the same shape).
- `hook.py:840` -- the accepted computed `takeover = invocation.config.takeover_mode()`.
- `hook.py:867` -- `project_root = invocation.config.project_root`: nested attribute,
  differently named.
- `hook.py:877` -- `config_sync = invocation.config.config_sync_settings()`: computed.
- `security_audit.py:759` -- `tc = ctx.takeover`: unrelated `ctx` (local var from
  `audit_context(config)`, not this ticket's `Invocation`/`ResolutionContext`/
  `FilePathResolutionContext`/`ResolveContext` types), differently named, and
  `security_audit.py` is out of scope for this round anyway.

Also confirmed via grep that every function parameter typed as `Invocation`,
`ResolutionContext`, `FilePathResolutionContext`, or `ResolveContext` anywhere in the
package lives in one of the 4 target files -- nothing was missed outside the brief's
stated scope.

## Verification (all 9 steps + calibration)

- **Baseline reconfirmed before touching anything**: `Ran 4021 tests` / `OK (expected
  failures=4)` -- exact match to the brief's stated baseline.
- **After all edits**: `Ran 4021 tests` / `OK (expected failures=4)` -- identical count,
  no test file touched (confirmed via `git status --porcelain`: the same test files
  modified at session start are the only ones modified now; none by me).
- `uv run ruff check .` -- `All checks passed!`
- `uv run ruff format --diff .` -- one file (`file_matching.py`) needed reformatting
  after my edit (line-wrap on a call I split across two lines); applied `ruff format .`,
  reran diff -- `197 files already formatted`.
- `tools/architecture_fitness.py --stdlib` -- PASS.
- `tools/architecture_fitness.py --ambient` -- exit 0 (heuristic notes only, no new
  ambient reads introduced -- I added no `os`/`pathlib` usage).
- `tools/architecture_fitness.py --layers` -- "All modules map to exactly one layer."
  / "No cross-layer direction violations."
- `tools/corpus_build.py --verify --strict-prose` -- `OK: no differences`. `In-process:
  6401 cases`. `End-to-end: 61 cases`. Exact match to baseline.
- **Calibration (step 7)**: planted a decision-altering change in
  `_governed_tool_verdict` (`if tool_name not in governed_tools:` -> `if True:`, forcing
  every tool to be treated as ungoverned/allow). Reran `--verify`: **FAIL**, exit code
  1, with concrete expected-vs-actual diffs shown (e.g. a `git status` allow rule match
  replaced by "Not a governed tool"). Reverted by editing the line back (never
  `git checkout`). Reran `--verify`: **OK: no differences**, exit 0, same case counts.
  Confirmed `git status --porcelain -- toolguard/hook.py` shows only the legitimate
  round-4 diff, no residue from the probe (checked the exact line text matches
  pre-plant).
- **Entry-point smoke test (step 8)**: imported all 8 `[project.scripts]` modules
  (`toolguard.hook`, `.session_start`, `.update_check`, `.tools.security_audit`,
  `.tools.maintenance`, `.tools.installer`, `.scripts.migrate_permissions`,
  `.tools.update_skills`) and asserted each has a `main` attribute -- all 8 OK. Also ran
  a live smoke test of the actual hook (`toolguard.hook --eval` with a sample
  `PreToolUse` event) under `PYTHONPATH=.` to confirm the working tree (not an installed
  copy) executes end-to-end without error.

## Files changed

- `toolguard/hook.py` -- deleted aliases in `_run_startup_validation`,
  `_log_allowed_command`, `_resolve_event`, `_log_config_discovery`,
  `_resolve_takeover_mode`, `_run_divergence_check`, `_log_non_allow_decision`,
  `_handle_file_path_tool`, `_handle_command_tool`. No signature changes this round
  (all signature changes visible in `git diff` predate round 4, from rounds 1-3).
- `toolguard/resolve.py` -- deleted aliases in `resolve_file_path_permission_detailed`
  and `resolve_bash_permission_detailed`; fixed the missed `tool_name` reference caught
  by the test suite.
- `toolguard/permission_resolution.py` -- deleted aliases in `resolve_command_permission`
  and `resolve_file_path_permission`.
- `toolguard/file_matching.py` -- deleted aliases in `check_file_path_hard_deny`.
- `toolguard/invocation.py` -- `env_config` field default changed from `None` to
  `field(default_factory=lambda: MappingProxyType({}))`; docstring updated to match
  (this file predates round 4 as a new untracked file from round 1a; only this one
  field/docstring edit is round 4's).

No test file touched. No file outside these 5 touched.

## Timing and estimated cost

- Planning/brief validation/task-memory capture: ~5 min, ~$0.05
- Classification (grep + AST scans, reassignment check): ~15 min, ~$0.30
- env_config decision + verification of callers: ~10 min, ~$0.20
- Editing (5 files): ~25 min, ~$0.45
- Debugging the missed `tool_name` reference + AST unbound-scan: ~10 min, ~$0.20
- Verification (tests, lint, fitness, corpus, calibration, entry points, sibling
  sweep): ~20 min, ~$0.35
- Report writing: ~10 min, ~$0.15
- **Total: ~95 min, ~$1.70** (Claude Sonnet 5, rough token-based estimate)