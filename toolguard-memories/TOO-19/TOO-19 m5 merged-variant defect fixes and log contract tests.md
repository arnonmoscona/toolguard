---
title: TOO-19 m5 merged-variant defect fixes and log contract tests
type: note
permalink: toolguard/too-19/too-19-m5-merged-variant-defect-fixes-and-log-contract-tests
tags:
- task-memory
- TOO-19
---

## Task

TOO-19 finding m5 (complexity reduction) residual work. The `hook.py`/`log_writer.py`
complexity refactor itself was already done and merged (Y's `hook.py` + X's
`log_writer.py`, per `/tmp/m5exp/competitive-review.md`) before this session started, with
the working tree carrying it uncommitted. My job: fix findings #12, #13, #20 against
`toolguard/log_writer.py`, and add two pinning tests the review flagged as missing.

## Changes made

### 1. Finding #12 -- pure renderers (`toolguard/log_writer.py`)

Replaced `_write_markdown_entry(f, record, timestamp) -> None` and
`_write_jsonlines_entry(f, record) -> None` (which wrote directly to an open `TextIO`) with:

- `_render_markdown_entry(record, timestamp) -> str` -- builds a list of line strings via
  the same explicit `if record.x:` checks as before (kept X's explicit style per the
  review's own recommended fix, not Y's `getattr` table -- avoids finding #9's silent-typo
  hazard), then `"".join(...)`.
- `_build_jsonlines_entry(record) -> dict` -- unchanged logic, just returns the dict instead
  of writing it.

`log_command`'s write site now renders first, then does a single `open(...).write(rendered)`:

```python
if logging_format == "jsonlines":
    rendered = json.dumps(_build_jsonlines_entry(record)) + "\n\n"
else:
    rendered = _render_markdown_entry(record, timestamp)

with open(log_file, "a", encoding="utf-8") as f:
    f.write(rendered)
```

This delivers both properties the review named: a single `f.write()` narrows the
interleaving window between two concurrent hook processes, and a mid-render exception now
leaves no half-written record (rendering happens entirely before the file is opened).
Removed the now-unused `TextIO` import.

### 2. Finding #13 -- timestamp asymmetry documented

Both `_build_jsonlines_entry` and `_render_markdown_entry` docstrings now explicitly state
the asymmetry is deliberate (jsonlines calls `datetime.now()` itself for an independent ISO
field; markdown takes the pre-formatted string `log_command` already computed) and point at
each other, with an explicit "do not clean this up" instruction and a note about the
`side_effect`-list-dependent call sequence.

### 3. Finding #20 -- `_log_dir_from_environment` exception docs

Added a `Raises: RuntimeError` section documenting that it's propagated from
`find_project_root` and that `log_command` catches it specifically as fatal.

### 4. Two missing tests

**`test/unit/test_log_writer.py`**, new class `TestLogFormatGoldenFile` (4 tests): exact
byte-for-byte content assertions for markdown and jsonlines, each with every optional field
populated and with none. `datetime.now()` patched to a single fixed value (class-wide) so
output is fully deterministic. jsonlines test also asserts exact key insertion order via
`list(entry.keys())`. This is the first test in the file asserting full exact content rather
than substrings/pairwise ordering.

**`test/unit/test_hook.py`**, new method `test_crash_context_carries_tool_name_tool_input_cwd`
on the existing `TestHookCrashCapture` class: forces `resolve_bash_permission_detailed` to
raise after `tool_name`/`tool_input`/`cwd` are assigned in `main()`, patches
`toolguard.hook.log_crash`, and asserts the crash-context dict passed to it has all three
keys with values matching the hook input exactly. No existing test checked this directly
(existing tests only grep crash-report file text for exception type/message).

Both files already used patterns compatible with the isolation rules: `test_log_writer.py`'s
tests pass `log_dir=` explicitly (never reach `toolguard.config` discovery, no isolation
needed); `test_hook.py` already has module-level `TOOLGUARD_LOG_DIR` isolation via
`setUpModule`/`isolate_log_dir_for_module()` (TOO-19, fourth anchor) which the new test
inherits for free.

Deviation note: the feature-coder role's default policy is "never touch the main test
directory, only `coder-test/**`". This task's explicit instructions named
`test/unit/test_log_writer.py` / `test/unit/test_hook.py` as the intended homes and gave
concrete pinning-test requirements, so I followed the task instructions over the generic
default -- these are new pinning tests (never weakening or deleting existing assertions),
consistent with normal ticket work in this repo.

## Self-check against findings #15-18 (must-preserve properties)

- **#15 (frozen dataclass, no mutable-default hazard):** `_LogRecord` untouched --
  `field(default_factory=list)` for `violated_rules`, frozen, unchanged by this session.
  Confirmed by inspection; my diff touches nothing above the two renderer functions.
- **#16 (`sys.exit(1)` escapes `except Exception` as `SystemExit`):** untouched --
  `_require_existing_log_dir`'s `sys.exit(1)` and the `try`/`except RuntimeError`/`except
  Exception` structure in `log_command` are unchanged; I only replaced the body of the
  `with open(...)` block's write call.
- **#17 (`datetime.now()` call sequence: log_filename, then timestamp, then jsonlines
  isoformat, in that order):** Verified with an ad hoc script
  (`/tmp/.../scratchpad/verify_datetime_sequence.py`) patching `datetime.now` with a 3-item
  `side_effect` list: call count is exactly 3, the filename uses call #1, the jsonlines entry
  uses call #3. The third call now happens just *before* `open()` instead of textually
  inside the `with` block, but the call *order* relative to the other two `datetime.now()`
  calls is unchanged -- `open()` itself never calls `datetime.now()`, so moving the render
  step earlier doesn't reorder anything a `side_effect` list could observe.
- **#18 (field/key ordering, falsy-omission):** Verified via the new golden tests --
  markdown order Status/Command/Matched Rule/Violated Rules/Permission Mode/Note/Context/Agent,
  jsonlines key order timestamp/status/command/violated_rules/matched_rule/note/extra_info/
  permission_mode/additional_context, both exactly as documented in the review, both formats
  tested with all-optional-populated and none-populated cases.

## Byte-identity evidence (purity refactor, finding #12)

Ad hoc script `/tmp/claude-1000/.../scratchpad/byte_identity_check.py`: reimplemented the
pre-refactor `_write_markdown_entry`/`_write_jsonlines_entry` verbatim against an
`io.StringIO()` buffer, ran both old and new code over 3 cases (bare fields, some optional
fields, all optional fields including one long enough to exercise
`_preview_additional_context`'s truncation path), and compared output strings plus JSON key
order. Result: **all 3 cases byte-identical** for both formats, key order identical.

## Verification results

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -- **Ran 2039 tests, OK** (baseline 2034 + 5 new: 4 golden
  + 1 crash-context). `test_zz_real_log_dir_guard` (part of the 2039) passed, confirming no
  test wrote into the real `logs/` directory.
- `uv run ruff check .` and `uv run ruff format --check .` -- both clean, repo-wide.
- `pyscn analyze --json toolguard/hook.py toolguard/log_writer.py`:
  - `main` (hook.py): **cyclomatic 9**, cognitive 9, risk low -- matches the review's
    predicted 9/9/2, well under the target of 10, no regression (I made no hook.py edits
    this session besides the new test in test_hook.py).
  - `log_command` (log_writer.py): **cyclomatic 6**, cognitive 8, risk low -- matches the
    review's predicted 6/9/3, well under 10.
  - New `_render_markdown_entry`: cyclomatic 7, low risk (no explosion from the refactor).
- Real `logs/` directory: `toolguard-2026-08-01.md` entry count (`## ` headers) went from
  676 -> 745 and line count 5598 -> 6161 across this session's several `uv run python -m
  unittest ...` and `pyscn` invocations. This growth is from toolguard's live hook logging
  *my own Bash tool calls* during this session (this repo dogfoods toolguard on itself, per
  the repo hazard note) -- NOT from the test suite, which the passing
  `test_zz_real_log_dir_guard` + its `atexit` re-check independently confirm wrote nothing
  real. No test-induced leakage occurred.

## Files changed

- `toolguard/log_writer.py` -- pure renderers, docstring additions (findings #12, #13, #20).
- `test/unit/test_log_writer.py` -- new `TestLogFormatGoldenFile` class (4 tests), plus
  `import tempfile` added to top-level imports (new tests use it directly instead of
  repeating the file's existing per-test local-import style).
- `test/unit/test_hook.py` -- one new test method on `TestHookCrashCapture`.

Ad hoc verification scripts (not shipped, scratchpad only):
- `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/byte_identity_check.py`
- `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/verify_datetime_sequence.py`

## Scope check

2 files modified (`toolguard/log_writer.py`, plus 2 test files) -- well under the
scope-inflation thresholds. No new files in the package itself. No async/threading/local
imports introduced in `toolguard/`. Elapsed roughly 40-45 minutes total.
