---
title: TOO-45 ticket 99 - coder implementation report
type: note
permalink: toolguard/implementation/too-45-ticket-99-coder-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

# TOO-45 ticket 99 - contract module semantic seams: implementation report

Branch too-45. Not committed - dispatcher commits.

## Summary

Implemented plan items 1 and 3 (`PreToolUseResponse`, `PreToolUseEvent`) in
`toolguard/claude_code_contract.py`, wired both into their call sites, and added a
round-trip test file. **Declined plan item 4** (`SessionStartEvent`) with reasoning below,
per Arnon's pre-registered permission to refuse.

## Files changed

- `toolguard/claude_code_contract.py` (modified) - added `PreToolUseEvent` (frozen dataclass,
  `from_json_dict()`/`to_json_dict()`) and `PreToolUseResponse` (frozen dataclass,
  `to_json_dict()` owning the `hookSpecificOutput` nesting and the additionalContext-omission
  rule). Reordered the "Event names" constants block above `PreToolUseResponse` so
  `PRE_TOOL_USE_EVENT` is defined before its first use, rather than relying on Python's
  late name resolution across a forward reference. Added one sentence to the module docstring
  noting the two classes own translation for their two shapes.
- `toolguard/hook.py` (modified) - `create_hook_output()` now delegates to
  `PreToolUseResponse(...).to_json_dict()`; its docstring dropped the now-duplicated
  Args/Returns detail that lives on `PreToolUseResponse` itself. `_finalize_output()` was
  rewritten to merge the reporter's fault context into `verdict.additional_context` via
  `dataclasses.replace()` on the `RuntimeVerdict` *before* calling `create_hook_output()`,
  rather than mutating the already-built wire dict. This fully eliminated the module's need to
  reach into `hookSpecificOutput`/`additionalContext` directly, which the plan hadn't
  anticipated (it expected those two keys to stay) - it fell out naturally from working at the
  verdict level instead of the dict level. `parse_hook_input()` is unchanged (deliberately -
  plan item 2, out of scope).
- `toolguard/testing/sandbox.py` (modified) - `run_hook()` now builds a sandbox-default
  `PreToolUseEvent` and overlays the caller's payload dict on its `to_json_dict()` output,
  instead of hand-building the event dict with three `setdefault()` calls. See "Design decision
  worth flagging" below.
- `test/unit/test_claude_code_contract.py` (new) - 8 tests: 2 round-trip tests for
  `PreToolUseEvent` (full payload, and `permission_mode=None`), 1 for `to_json_dict()`'s exact
  flat shape, 1 for `from_json_dict()`'s lenient defaulting on an empty dict, and 4 for
  `PreToolUseResponse.to_json_dict()` covering the hookSpecificOutput nesting and all three
  additionalContext-omission cases (absent, explicit None, empty string) plus the
  non-empty-inclusion case. Pure dataclass construction, zero file I/O - no
  `ConfigIsolationMixin` needed per `test-config-isolation.md`'s own checklist ("If no [config
  discovery reached] ... no isolation needed. Stop.").

`toolguard/session_start.py` - untouched.

4 files touched (3 modified + 1 new), well under the scope-inflation guardrails.

## Declined: plan item 4 (SessionStartEvent)

Investigated before implementing, per the "evidence before fixing" project convention.
`session_start.py` has exactly one read site: `payload.get(CWD_KEY) or str(ambient.cwd())`.
Grepped the whole repo (source and tests) for any SessionStart-payload construction: none
exists anywhere via a shared type - every test builds the raw dict literal
`{"hook_event_name": "SessionStart", "cwd": ...}` directly. This is the opposite of
`PreToolUseEvent`'s situation, where `sandbox.py` constructs and `hook.py` parses the *same*
shape - the actual insight the ticket is built on (one class, both directions, so they cannot
drift apart). For SessionStart there is no second direction to keep in sync with: a
`SessionStartEvent` class here would wrap one field, have no round-trip partner anywhere in the
codebase, and prevent no drift that could occur. Declined. `CWD_KEY` import in
`session_start.py` is untouched.

## Design decision worth flagging: sandbox.py's run_hook() now defaults ALL 7 fields, not 3

Before, `run_hook()` used `event.setdefault()` for exactly `cwd`/`hook_event_name`/`session_id`,
leaving `tool_name`/`tool_input`/`transcript_path`/`permission_mode` entirely **absent** from
the outgoing JSON whenever the caller's payload omitted them. The `PreToolUseEvent`-based
rewrite (`{**default_event.to_json_dict(), **payload}`) makes all 7 fields present with
neutral defaults (`""`/`{}`/`None`) even when the payload omits them, because `to_json_dict()`
always emits the full shape (matching what real Claude Code actually sends).

Verified this changes no observable behavior in the current codebase: every real call site
(`test_sandbox.py`'s ~10 call sites, `fixture_loader.py`'s `build_hook_payload()`) always
supplies `tool_name` + `tool_input`, and every downstream read in `hook.py` is
`.get(key, default)` with the same effective default either way. Full test suite and
`corpus_build --verify` confirm no behavior change (see Gates below). Flagging this because it
is a genuine (if narrow) behavior difference in test-tooling semantics that the plan didn't
call out, in case a future caller of `run_hook()` ever relies on key-absence to probe
`parse_hook_input()`'s "missing required field" error path - it no longer can via `run_hook()`.

## Gates - actual numbers

- **Baseline** `uv run python -m unittest discover -s test -t .`: 3975 tests, 1 unexpected
  failure (`test_compound_resolve_seam.TestJudgeUnitInvariants.test_unknown_kind_unit_resolves_to_ask`)
  + 4 expected failures. Confirmed the 1 failure passes in isolation
  (`uv run python -m unittest test.unit.test_compound_resolve_seam...` -> OK) - transient,
  caused by the two other agents' concurrent edits to `compound.py`/`multiline.py`
  mid-full-suite-run, unrelated to this ticket.
- **After my changes**, first full run: 3983 tests (3975 + my 8 new), 3 unexpected failures, all
  in `test_verdict_corpus.py` (`test_no_sub_command_breakdown_changed`, `test_no_verdict_changed`,
  `test_tracked_fields_unchanged_or_acknowledged`) + 4 expected. Confirmed via grep that neither
  `test_verdict_corpus.py` nor `test_multiline_bash.py` (which had failed in an earlier
  intermediate run, 9 failures total, before settling) imports `claude_code_contract`, `hook`,
  or `sandbox` at all. A rerun of the full suite a few minutes later still showed the same 3
  failures in `test_verdict_corpus.py`, confirming these track the other agents' work landing on
  disk, not a regression from mine.
- `uv run python tools/corpus_build.py --verify`: FAILS, but every single reported difference is
  about heredoc sentinel naming (`__HEREDOC_TO_cat__` vs `__HEREDOC_TO_diff__`) and "heredoc
  sink could not be attributed" parse errors - exclusively `compound.py`/`multiline.py`
  territory. Zero diffs mention `hookSpecificOutput`, `permissionDecision`,
  `permissionDecisionReason`, `additionalContext`, or any field this ticket touches. My changes
  introduce no verdict/output differences; I could not get a clean `--verify` run because the
  files producing the (unrelated) diffs are being edited live by the other two agents, which I
  was explicitly told not to touch. This should be re-verified by whoever runs the gate after
  those agents finish.
- `uv run ruff check .` (repo-wide, read-only): **All checks passed!**
- `uv run ruff format` scoped to `toolguard/hook.py toolguard/claude_code_contract.py
  toolguard/testing/sandbox.py test/unit/test_claude_code_contract.py`: reformatted 2 of the 4
  (hook.py, the new test file); diffs reviewed, purely whitespace/wrapping, no semantic change.
  Did NOT run repo-wide `ruff format .` per the concurrency instruction.
- `uv run python tools/architecture_fitness.py --stdlib --ambient --layers`: all three PASS
  (78 modules mapped, no cross-layer violations; stdlib-only confirmed; every `os`/`Path`
  ambient read has an owner).

## Contract KEY-import metric (not counting the two new class imports)

| file | before | after |
|---|---|---|
| `toolguard/hook.py` | 12 | 6 |
| `toolguard/testing/sandbox.py` | 4 | 1 |
| `toolguard/session_start.py` | 1 | 1 (unchanged - item 4 declined) |
| **total** | **17** | **8** |

Net: 9 fewer key imports (53% reduction) across the three files, offset by 2 new class imports
(`PreToolUseResponse` in `hook.py`, `PreToolUseEvent` in `sandbox.py`).

## Self-review

- Anti-pattern scan: no `async`/`await`, no `threading`, no new function-level imports (grepped
  the diff directly). `ruff check .` clean (covers unused imports too).
- Requirements verified line-by-line against the task recall note (item 1 done, item 3/plan's
  sandbox item done, item 4/plan's session_start item explicitly declined with reasoning
  recorded before implementation began, all "explicitly out of scope" items left untouched -
  verified `parse_hook_input()`'s signature and body are byte-identical, `constants.py` was
  never opened, `tool_spec.py`/`installer.py`/`takeover_audit.py`/`command_extractor.py` were
  never opened).
- Concurrency: confirmed via `git status` at both start and end that I never touched
  `toolguard/compound.py` or `toolguard/parser/multiline.py`.

## Timing and estimated cost

- Phase 1 (read plan/rules/code, investigate sandbox/session_start semantics, fetch+verify
  hooks.md for permission_mode optionality, baseline test run): ~15:33-15:41, ~8 min.
- Phase 2 (implement both dataclasses, wire into hook.py/sandbox.py, write the round-trip test
  file): ~15:41-15:48, ~7 min.
- Phase 3 (gates: full suite x3, corpus_build --verify x2, ruff, architecture_fitness,
  diff review, anti-pattern scan): ~15:48-15:50, ~5 min (some overlap with phase 2's tail).
- Phase 4 (this report): ~2 min.
- Total wall time: ~22 min.
- Estimated cost: this was a Sonnet-tier feature-coder session with moderate tool use (reads,
  greps, several test runs, one web fetch); rough estimate $1.50-$2.50 total based on token
  volume (several large file reads, ~4000-line test-suite output parsed a few times).