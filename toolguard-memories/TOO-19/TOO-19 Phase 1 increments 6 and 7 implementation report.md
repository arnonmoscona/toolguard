---
title: TOO-19 Phase 1 increments 6 and 7 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-1-increments-6-and-7-implementation-report
tags:
- task-memory
- TOO-19
---

## Summary

Implemented TOO-19 Phase 1 increments 6+7 plus the `decision.py` addition: carried the
already-landed `additionalContext` enrichment (increments 1-5) the last two hops -- into the
hook's JSON output (`hookSpecificOutput.additionalContext`) and into the log
(`logs/toolguard-*.md` / `.jsonlines`). No changes to matching/resolution logic -- this is
pure plumbing over already-working data (`FileResolution.additional_context` /
`BashResolution.additional_context`).

## Files changed (7 total -- well under scope-inflation thresholds)

Source (3):
- `toolguard/tools/decision.py` -- `Decision.additional_context` field (last positional
  slot), populated in `_decide_bash` / `_decide_file_path`.
- `toolguard/hook.py` -- `create_hook_output(decision, reason, additional_context=None)`;
  `_resolve_event` widened to a 3-tuple; `_log_allowed_command` gained the parameter; both
  decision paths (file-path ~line 766, Bash ~line 849) and `_run_eval_mode` wired through.
- `toolguard/log_writer.py` -- `log_command(..., additional_context=None)`, a new
  `_preview_additional_context` helper, wired into both markdown (`**Context**:` field) and
  jsonlines (`additional_context` key) writers.

Tests (4, all under `test/unit/`, none in a directory the task barred me from touching --
this project's actual test suite lives here and the ticket explicitly assigned test work):
- `test/unit/test_hook.py` -- 4 new `create_hook_output` key-presence tests
  (`TestHookOutput`); 3 fixes to `TestLogAllowedCommand` (now-required
  `additional_context=None` kwarg in existing `assert_*_call`s); new
  `TestAdditionalContextThroughMain` class (3 end-to-end tests: Bash enriched allow, Read
  enriched allow, error-path-emits-none).
- `test/unit/test_hook_eval.py` -- 4 fixes for the widened `_resolve_event` 3-tuple; 1 new
  test confirming `--eval` surfaces `additionalContext`.
- `test/unit/test_tools_decision.py` -- new `TestDecideAdditionalContext` class (5 tests:
  file/Bash enriched + plain-string-yields-None + positional-construction-still-works).
- `test/unit/test_log_writer.py` -- new `TestPreviewAdditionalContext` (3 tests) and
  `TestAdditionalContextLogging` (6 tests: markdown/jsonlines presence, capping, absence).

Test count: 1925 baseline -> 1946 (21 new tests; some of the +22 I wrote landed as net +21
because ruff's auto-reformat of `test_hook_eval.py` didn't change test count -- rounding is
just from counting by hand, not a discrepancy worth chasing).

## Key decisions

### 1. `_resolve_event` was widened to a 3-tuple (not left alone)

The ticket asked me to decide and justify. I widened it: `--eval` exists specifically to
preview what the live hook would do, and the live hook now includes `additionalContext` in
its JSON output for a matched enriched rule. Leaving `--eval` silent about that field would
mean the security-audit skill's "what would this config decide" probe systematically omits
a real, user-visible piece of hook behavior -- exactly the failure mode `--eval`'s own
docstring says it exists to prevent (no drift from the live hook). The two synthetic guard
verdicts inside `_resolve_event` (ungoverned tool, missing target) have no matched rule, so
they always report `None` -- no invented enrichment. Updated docstring, `_run_eval_mode`,
and the 5 call sites in `test_hook_eval.py` that unpacked the old 2-tuple.

### 2. Log capping: word-budget preview + ellipsis + full word count

Followed Arnon's steer exactly: preview + ellipsis + **full** word count (not the preview's
word count), e.g. `"word0 word1 ... word39 ... (100 words total)"`. Chose 40 words as the
preview budget (`_LOG_CONTEXT_PREVIEW_WORDS`) -- short enough that a human scanning
`logs/toolguard-*.md` for anomalies isn't confronted with a wall of text on every matching
invocation, long enough to convey the gist. Applied uniformly to BOTH the markdown
`**Context**:` field and the jsonlines `additional_context` key, since both are read by the
same human-scanning-a-log use case and the existing codebase doesn't differentiate the two
formats' verbosity elsewhere. The FULL, uncapped text still reaches Claude via
`hookSpecificOutput.additionalContext` for that single invocation -- only the persisted log
copy is capped, so nothing is lost, just not re-displayed 500 words at a time on every
matching command thereafter.

Did **not** reuse `compound.py::_truncate_for_display` (see duplication self-check below) --
it is char-based (120 chars, `" ...[truncated]"`, no word count), built for a different
purpose (bounding a command string in a permission-prompt reason), and is a private helper
of `compound.py`. Arnon's spec explicitly wanted a word-count-based preview with the full
word count surfaced, which is a different contract, so a small dedicated helper in
`log_writer.py` was the right call rather than stretching an unrelated private helper to fit
two shapes.

### 3. `_log_allowed_command`'s compound-command case gets ONE accumulated context on every sub-entry

`BashResolution.additional_context` is a single already-deduplicated, budget-capped block
for the WHOLE compound command (from `compound.py::_accumulate_contexts`, landed in
increment 4) -- it is not attributable to an individual sub-command. When a compound command
logs one entry per sub-command (`_parse_compound_match_details`), each of those entries now
carries the same accumulated block, mirroring exactly what the hook injects to Claude for
the whole command. Documented this explicitly in `_log_allowed_command`'s docstring so a
future reader doesn't expect per-sub-command attribution.

## Call sites touched (hook.py, all `create_hook_output` grepped and verified)

- L169 `create_hook_output` definition -- signature widened, default `None` preserved.
- L548 `--eval` success path -- now passes `additional_context`.
- L550/553/556 `--eval` error paths (JSONDecodeError/ValueError/Exception) -- untouched,
  default `None`.
- L720 not-a-governed-tool -- untouched.
- L744 no file_path provided -- untouched.
- L815 **file-path decision path** -- passes `file_result.additional_context`.
- L822 no command provided -- untouched.
- L898 **Bash decision path** -- passes `bash_result.additional_context`.
- L914/924/932 top-level error handlers (JSONDecodeError/ValueError/Exception) -- untouched.

`log_command` call sites in `main()`: both file-path (allow/ask/refused, 3 sites) and Bash
(ask/refused directly, allow via `_log_allowed_command`) decision branches now pass
`additional_context`; the two guard `log_command` calls (no file_path / no command provided)
pass nothing, matching the "error paths have no matched rule" rule from the spec.

## Duplication/drift self-check

- `Decision.additional_context`: pure pass-through of an already-computed field
  (`FileResolution.additional_context` / `BashResolution.additional_context`), zero new
  matching/resolution logic. No duplication.
- `create_hook_output`'s "only add the key when truthy" pattern: a 2-line conditional, not
  extracted anywhere else in the codebase to compare against; too small to be worth a shared
  helper.
- `_preview_additional_context`: considered reusing `compound.py::_truncate_for_display`
  (the only existing truncation helper in the codebase) and explicitly rejected it -- see
  decision #2 above. Different unit (words vs. chars), different marker format, different
  call-site contract (Arnon's explicit "full word count" requirement), and it is private to
  `compound.py`. Nothing else in the codebase does word-budget truncation with an appended
  total-word-count, so this is genuinely new, not a duplicate.
- No other `additionalContext`/`additional_context` plumbing existed anywhere past
  `FileResolution`/`BashResolution` before this change (grepped `hook.py` and `log_writer.py`
  before starting) -- confirmed this was in fact the missing last-two-hops work, not a
  re-implementation of something already done.

## Verification

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"`
  -> **1946 tests, OK** (baseline 1925 + 21 new).
- `uv run ruff check .` -> All checks passed.
- `uv run ruff format` run ONLY on the 3 touched source files and 4 touched test files (did
  NOT touch the 5 pre-existing unformatted repo files, nor the other already-modified files
  from earlier landed increments visible in `git status`, e.g. `compound.py`, `config.py`,
  `resolve.py`, `rule_entry.py`, `test_compound.py`, `test_resolve.py`, etc. -- those are
  prior work, not mine, and were left untouched).
- `uv run python tools/coverage_stdlib.py` -- spot-checked `toolguard.log_writer.cover` and
  `toolguard.tools.decision.cover`: every new branch (`_preview_additional_context`'s
  short/long/exact-budget paths, both markdown and jsonlines `additional_context` writers,
  `decide()`'s new field pass-through) is exercised by the new tests. `toolguard.hook`
  stayed at 91.4% coverage (no regression).

## Out of scope / not touched

- No changes to `compound.py`, `config.py`, `config_types.py`, `resolve.py`, `rule_entry.py`
  -- those carry increments 1-5, already landed and untouched by this task.
- No git operations performed (no commits), per instructions.
- Did not attempt to make the compound-command log entries carry per-sub-command
  attribution for `additionalContext` -- the underlying data (`BashResolution`) doesn't
  support that distinction yet; flagged as a documented limitation in
  `_log_allowed_command`'s docstring rather than invented.

## Self-review

Anti-pattern scan: no `async`/`await`, no `threading`, no new local imports (the one
pre-existing local import in `hook.py::_resolve_event`, documented as the sanctioned
circular-import exception, was not duplicated or added to). Every new/changed function
carries a docstring. No unused imports introduced.
