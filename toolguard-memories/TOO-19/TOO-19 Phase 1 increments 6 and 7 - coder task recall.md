---
title: TOO-19 Phase 1 increments 6 and 7 - coder task recall
type: note
permalink: toolguard/too-19/too-19-phase-1-increments-6-and-7-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task

TOO-19 Phase 1 ("additionalContext" feature), increments 6 and 7 combined, plus one
addition (the `decision.py` shared primitive) the plan note missed.

Already landed (increments 1-5), do NOT redo:
- `toolguard/rule_entry.py`: `ADDITIONAL_CONTEXT_KEY`, `KNOWN_ENRICHMENT_KEYS`,
  `RuleEntry.additional_context`.
- `config_types.py` `ResolvedDecision.additional_context`; `resolve.py`
  `FileResolution.additional_context`; `config.py` `Configuration._entry_for_pattern`.
- `compound.py::_accumulate_contexts` (dedupe / paragraphs / 500-word first-fit budget,
  `_MAX_CONTEXT_WORDS = 500`).
- `resolve_one` is a 3-tuple through `compound.py`; `BashResolution.additional_context`
  (`resolve.py`); `resolve.py::_hard_deny_additional_context` shared hard-deny lookup for
  BOTH file-path and Bash hard-deny paths.

The value already arrives on `FileResolution.additional_context` and
`BashResolution.additional_context`. This task carries it the LAST TWO HOPS: into the
hook's JSON output, and into the log.

## Scope

### 1. toolguard/tools/decision.py (NOT in plan note -- do first)
`Decision` dataclass (~line 45-78) gets `additional_context: Optional[str] = None` as the
LAST field (backwards compatible for positional construction). `_decide_bash` (~132) and
`_decide_file_path` (~201) populate it from `result.additional_context`.

### 2. toolguard/hook.py::create_hook_output (~line 169)
Signature -> `create_hook_output(decision, reason, additional_context=None)`. Add
`"additionalContext": additional_context` inside `hookSpecificOutput`, ONLY when a
non-empty string -- absent key (not `null`) otherwise. Keep default so all ~12 existing
call sites stay valid without changes except the two decision paths.

### 3. Call sites (grepped, hook.py):
- L169 def create_hook_output
- L512 --eval path: `create_hook_output(decision, reason)` (in `_run_eval_mode`)
- L514/517/520 error paths in `_run_eval_mode` -- no context
- L684 not-a-governed-tool -- no context
- L708 no file_path provided -- no context
- L775 FILE-PATH DECISION PATH -- pass `file_result.additional_context`
- L782 no command provided -- no context
- L850 BASH DECISION PATH -- pass `bash_result.additional_context`
- L866/876/884 error paths (JSONDecodeError/ValueError/Exception) -- no context

`_resolve_event` (actual name, NOT `_resolve_hook_event` as the plan note guessed;
~line 433-483) currently returns `(decision, reason)`, used only by `_run_eval_mode`.
Decision: WIDEN to `(decision, reason, additional_context)` since `--eval` exists to
preview what the hook would do and silently omitting a real output field defeats that.
Update its docstring and `_run_eval_mode`.

### 4. toolguard/log_writer.py -- increment 7
Extend `log_command` with `additional_context: Optional[str] = None`, written to the log
entry (both markdown and jsonlines formats) alongside `matched_rule`.

Arnon's steer: CAP the logged text (preview + ellipsis + full word count) rather than the
full up-to-500-word block, because logs are scanned by a human. Existing convention in the
codebase: `compound.py::_truncate_for_display` (char-based, `_MAX_DISPLAY_COMMAND_LEN =
120`, appends `" ...[truncated]"`) -- but that's private to compound.py and char-based, not
word-based. Will write a small dedicated preview helper in log_writer.py matching Arnon's
"preview + ellipsis + full word count" spec, not reusing the private compound helper.

Wire at `log_command(...)` call sites in hook.py that correspond to a REAL decision (allow
/ ask / refused, both file-path and Bash paths). Error paths pass nothing.

## Tests to add (test/unit/, exact files TBD by grep, expect test_hook.py /
test_hook_eval.py / test_log_writer.py)
- create_hook_output OMITS additionalContext key when None/empty (assert `not in`, not
  `is None`)
- includes key inside hookSpecificOutput when given
- end-to-end hook invocation, Bash, enriched allow rule -> text in emitted JSON
- same for a file-path tool
- error path (no command provided) -> no additionalContext
- Decision.additional_context populated by decide() for both branches
- log entry carries it (+ capping behaviour)
- existing positional Decision construction still works

Tests touching config discovery MUST use ConfigIsolationMixin (test-config-isolation.md).
BUT: existing hook tests patch `toolguard.hook.load_configuration` directly with either a
hand-rolled `_FakeConfig` or (for real-Configuration end-to-end tests, e.g.
`TestNoMatchFallbackThroughMain`) a real `Configuration` built from `ConfigLayer`/
`Provenance` objects with zero file I/O -- per the isolation rule's own checklist, that
needs NO isolation mixin (no real filesystem discovery is reached). Follow that existing
pattern for the new end-to-end tests rather than introducing ConfigIsolationMixin where it
isn't needed.

## Verification
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"`
  must report OK. Baseline: 1925 tests passing before this change.
- `uv run ruff check .` clean; `uv run ruff format` ONLY on touched files (5 pre-existing
  unformatted repo files must NOT be reformatted).
- Duplication/drift self-check before reporting.
- Do NOT commit anything to git.

## Report destination
basic-memory project `toolguard`, path
`TOO-19/TOO-19 Phase 1 increments 6 and 7 implementation report.md`, tags `task-memory`,
`TOO-19`.
