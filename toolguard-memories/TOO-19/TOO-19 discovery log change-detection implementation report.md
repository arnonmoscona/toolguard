---
title: TOO-19 discovery log change-detection implementation report
type: note
permalink: toolguard/too-19/too-19-discovery-log-change-detection-implementation-report
tags:
- task-memory
- TOO-19
---

## Summary

Fixed the config-discovery diagnostic log noise in `toolguard/hook.py` /
`toolguard/log_writer.py`. The old `_discovery_diagnostic_done` module-level
global could never guard anything, since toolguard is a fresh process on every
`PreToolUse` invocation -- the flag reset to `False` every time, so every hook
call logged a Discovery entry (measured: 940/2051 real log entries on
2026-07-31, 868 byte-identical).

Replaced it with a change-detecting mechanism: `log_discovery()` now compares
the currently discovered config levels against the most recent recorded entry
for this project root, and writes to either log ONLY when they differ (or
there is no prior entry for this root).

## Files changed

- `toolguard/log_writer.py` -- new `_last_discovery_levels_for_root()` helper;
  rewrote `log_discovery()` to accept a `project_root` argument and do
  change-detection via a new JSONL log; also moved a stray local `import json`
  (inside `log_command`'s jsonlines branch) to the top-level import, since I
  was touching the file anyway and it violated the project's no-local-imports
  rule.
- `toolguard/hook.py` -- deleted the `_discovery_diagnostic_done` global and
  its guard; the call site now calls `log_discovery()` unconditionally on
  every invocation, passing `env_config["project_root"]`.
- `test/unit/test_logging_streams.py` -- rewrote `TestDiscoveryDiagnostic`
  (was one test with the old 2-arg signature) into 7 tests covering the new
  behaviour; updated the module docstring's summary line.
- `technical-notes.md` -- updated the "Once-per-session discovery diagnostic
  (M2)" section (and its TOC entry) to describe the new change-detecting
  mechanism, and added a row for the new JSONL file to the log-streams table.
  This was flagged by CLAUDE.md's doc-drift-sweep requirement -- the old
  section literally documented the guard I just deleted.
- `coder-test/too19_discovery_demo.py`, `coder-test/too19_discovery_change_demo.py`
  -- new throwaway demo scripts (not part of the formal suite), kept as a
  record of the end-to-end verification below.

## Design implemented (matches the spec)

1. New file `<log_dir>/toolguard-discovery.jsonl`, append-only JSONL, one
   object per line, NOT date-partitioned. The reasoning (a dated file would
   re-log every morning, reproducing the noise) is in `log_writer.py`'s module
   docstring on the `_DISCOVERY_JSONL_FILENAME` constant.
2. The JSONL log IS the state -- no separate marker file.
3. Keyed by project root (`env_config["project_root"]`, stringified). Compares
   against the most recent JSONL entry whose `project_root` field matches,
   scanning backward so entries from other projects sharing a
   `TOOLGUARD_LOG_DIR` don't cause flapping.
4. On change (or no prior entry for this root): appends the JSONL record AND
   writes the `**Discovery**` entry to the main dated log, in that order. On
   no change: writes nothing to either file.
5. Main-log entry format is byte-identical to before:
   `- **Discovery**: discovered {count} config levels: {joined}` under
   `## {timestamp}`. Verified `log_harvest.py`'s existing 18 tests still pass
   unchanged (it depends on this shape to skip Discovery sections).
6. `_discovery_diagnostic_done` and its guard deleted from `hook.py`.
   `log_discovery`'s docstring rewritten to explain the actual mechanism
   instead of the false "caller owns the once-per-session guard" claim.
7. JSONL schema chosen:
   ```json
   {"timestamp": "<ISO 8601>", "project_root": "<str>", "level_count": <int>, "levels": ["<level: path>", ...]}
   ```
   No separate signature field -- comparison is `previous_levels == levels`
   (direct list equality) against the derived `levels` list; per the spec's
   preference for one source of truth, nothing is hashed/summarized.

### Constraints honored

- **Latency**: `_last_discovery_levels_for_root()` reads the JSONL file once
  per invocation (`Path.read_text()`), guarded by
  `_DISCOVERY_JSONL_MAX_READ_BYTES = 1_000_000` (1 MB) -- oversized or missing
  files degrade to "no prior entry" rather than raising or doing a partial
  read.
- **Never fails the hook**: the whole `log_discovery()` body is wrapped in the
  existing `try/except Exception` + stderr-warning pattern already used
  elsewhere in `log_writer.py`.
- **No locking for the race**: documented in a comment on `log_discovery()`
  -- two hooks racing can both append a JSONL line; harmless duplicate,
  correctly de-duplicated on the next read since both lines carry the same
  `levels`. I did add one small piece of defensive handling beyond the
  no-locking decision: before appending, the code checks whether the file's
  last byte is a newline, and prefixes one if not. This isn't locking (still
  no coordination between racing writers) -- it's specifically to keep a torn
  final line from a *previous* crash from silently corrupting the *next*
  legitimate append into one unparseable line. Found this via my own test
  (`test_corrupt_final_line_is_tolerated_as_no_prior_entry`), which failed
  without it.
- **Malformed/truncated final line**: tolerated. The backward scan in
  `_last_discovery_levels_for_root()` skips any line that fails `json.loads`
  and keeps scanning further back for a matching `project_root` -- so a torn
  final line degrades to "no prior entry for the affected read", not a crash,
  and doesn't hide earlier valid entries for *other* project roots sharing the
  log dir.

## Tests added (`test/unit/test_logging_streams.py::TestDiscoveryDiagnostic`, 7 tests)

- `test_first_call_writes_both_files`
- `test_unchanged_second_call_writes_nothing` -- byte-identical assertion on
  both files (the core fix)
- `test_different_levels_writes_both_again`
- `test_reverting_to_a_previously_seen_value_still_logs` -- A -> B -> A logs a
  third time (comparison is against the LAST entry, not full history)
- `test_two_project_roots_sharing_a_log_dir_do_not_flap` -- A, B, A, B logs
  each time; a same-root repeat does not
- `test_corrupt_final_line_is_tolerated_as_no_prior_entry`
- `test_main_log_entry_format_unchanged` -- exact string assertion, plus
  confirms Discovery still doesn't leak into warning/conflict streams

None of these tests reach `toolguard.config`'s discovery path (they call
`log_discovery()` directly with hand-supplied `log_dir`/`project_root`, no
file-system config discovery) -- per `.claude/rules/test-config-isolation.md`,
no `ConfigIsolationMixin` isolation was needed, and I confirmed this by
re-reading that rule before writing the tests.

Existing `test/unit/test_tools_log_harvest.py` (18 tests, including
`test_discovery_entries_are_skipped`) re-run unchanged and pass -- confirms
`log_harvest.py` still correctly skips Discovery sections.

## Verification

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"`
  -- baseline (before any change) **2004 tests, OK**. After: **2010 tests, OK**
  (6 new tests net; I wrote 7 new tests and replaced the 1 old one).
- `uv run ruff check .` -- All checks passed.
- `uv run ruff format --check .` -- all files formatted (had to reformat the
  two new `coder-test/` demo scripts once; committed formatted).

### End-to-end demonstration (coder-test/too19_discovery_demo.py)

Using `toolguard.testing.sandbox.experiment()` + `Sandbox.run_hook()` (real
hook subprocess, isolated `HOME`/`TOOLGUARD_LOG_DIR` inside a temp sandbox --
never touches the real repo's `logs/`):

```
Invocations: 5
Discovery entries in main resolution log: 1
Discovery JSONL change-log lines: 1
PASS: unchanged config across 5 hook invocations logged Discovery exactly once.
```

**Before/after for "N vs 1"**: I did not re-run the literal pre-fix code (that
would have required a git write operation -- stash/checkout -- which is
outside my authority; see Security section of my instructions). Instead the
"before" is established two ways: (a) the real-world measurement already
quoted in the ticket (940/2051 entries, 868 duplicate, on the *actual* old
code running this exact repo for weeks); (b) analytically from the source --
`_discovery_diagnostic_done` was a plain module global and toolguard forks a
fresh process per `PreToolUse` call, so under the old code the entry count is
provably always exactly N for N invocations, with no possible dedup, for any
N and any config. I judged re-running old code via git stash to fabricate a
literal "N" data point not worth risking a discouraged write operation for a
result that's already provable and already measured in production.

I also wrote a second demo (`coder-test/too19_discovery_change_demo.py`)
confirming the mechanism isn't just "silence everything after call 1" -- it
genuinely reacts to a real config change (adding a user-level config file
mid-run produces a second Discovery entry):

```
After 2 identical-config invocations: 1 Discovery entries
After adding a user-level config: 2 Discovery entries
PASS: discovery log reacts to genuine config changes, not just always-1.
```

### Real logs/ confirmation

Real-logs entry counts, read-only, before and after my work:

- Before: `toolguard-2026-07-31.md` had **966** `Discovery` occurrences (read
  at task start).
- After: **998** `Discovery` occurrences, plus a new
  `logs/toolguard-discovery.jsonl` (19 lines) that didn't exist before.

**This growth is real but NOT from my own test code or demo scripts** -- both
demo scripts and every test I wrote write exclusively into
`tempfile.TemporaryDirectory()` / sandbox-owned temp paths; I grepped the
diffs to confirm this. The growth has two sources, both outside my control:

1. **Live dogfooding of my own session.** This repo's toolguard hook governs
   *my own* Bash tool calls in this very session (per CLAUDE.md: "the global
   `uv tool install` toolguard governs this repo"). Every `grep`, `uv run
   ruff`, `uv run python -m unittest ...` I ran as the acting agent is itself
   a real `PreToolUse` invocation against the real repo with real config,
   which appends a real Discovery entry when the (real, 8-level) config
   changed relative to the last entry for `/home/arnon/projects/toolguard`.
   Since I only ran ONE genuine config change scenario against my own repo
   (none, actually -- the real project config didn't change), this should in
   principle have logged only once under the fix... but see point 2.
2. **Pre-existing test-suite behavior, unrelated to my patch.** Grepping
   confirmed the small-level-count JSONL/log entries interleaved with the
   real-repo ones (`/tmp/tmpXXXX/project`, `/p/toolguard_hook.toml`,
   `/fake/0/toolguard_hook.toml`, `(none)`) come from **pre-existing** tests I
   did not write or modify: `test/unit/test_hook.py`,
   `test/unit/test_takeover_mode.py`, `test/unit/test_configuration.py`.
   These invoke hook/config logic in ways that resolve `find_project_root()`
   from the real `cwd` (the repo itself, since `uv run python -m unittest`
   runs with `cwd=/home/arnon/projects/toolguard`) even when `$HOME` is
   overridden, so `get_env_config()`'s default `log_dir` falls back to the
   REAL `logs/` directory for those specific test cases. This is a latent gap
   in test isolation that already existed before I started (present in files
   I'm not permitted to modify) -- **out of scope for TOO-19**, flagging it
   here per the CLAUDE.md instruction to say so rather than silently work
   around it. Running the full suite at all (mandated by my own verification
   steps, and something any contributor running `unittest discover` would also
   do) triggers this regardless of my change.

I did not hand-edit, truncate, or revert any existing real log file, and did
not disable this dogfooding governance to hide the effect -- I considered
that circumventing an existing safeguard and out of bounds per my own
instructions.

## Anti-pattern scan

- No `async`/`await` introduced.
- No `threading` introduced.
- No new local (function-level) imports -- and I removed one pre-existing one
  (`import json` inside `log_command`'s jsonlines branch, now top-level).
- No unused imports (ruff clean).
- Docstrings on every new function.

## Scope note

`git diff toolguard/hook.py` and `git diff toolguard/log_writer.py` show a
much larger diff than my own edits (the ~600 pre-existing changes for a prior
TOO-19 Phase 1 "additionalContext" feature were already sitting uncommitted in
the working tree at session start, even though the git-status snapshot given
to me at conversation start didn't list either file as modified). I verified
with `git diff ... | grep '^@@'` that my edits are exactly two hunks per file
(the global-removal + call-site rewrite in `hook.py`; the
`_last_discovery_levels_for_root` addition + `log_discovery` rewrite + the
stray-import fix in `log_writer.py`) and touched nothing else. I did not
revert or otherwise interact with the pre-existing uncommitted work.

## Out of scope / judged not to fix

- The pre-existing test-isolation gap described above
  (`test_hook.py`/`test_takeover_mode.py`/`test_configuration.py` writing into
  real `logs/` when `find_project_root()` resolves the real cwd). Worth a
  follow-up ticket; not touched here since I'm not permitted to edit test
  files beyond what this task specifically asked for, and it's unrelated to
  the discovery-diagnostic bug.
- `_validation_done` / `_divergence_check_done` in `hook.py` have the exact
  same "module global can never guard a per-process hook" shape as the bug
  just fixed. Not touched -- out of scope for this ticket, which was scoped
  specifically to the discovery diagnostic. Worth flagging for a follow-up if
  the same log-noise pattern shows up for validation/divergence entries.

## Timing / cost estimate

- Phase 1 (planning: read rules, hook.py/log_writer.py/config.py, task
  recall): ~7 min, ~$0.35
- Phase 2 (implementation: log_writer.py rewrite, hook.py edit, test rewrite,
  torn-line fix, doc updates): ~13 min, ~$0.65
- Phase 3 (self-review: test runs, ruff, diff-scope verification, real-logs
  investigation): ~8 min, ~$0.40
- Phase 4 (handoff: this report): ~3 min, ~$0.15
- **Total: ~31 min, ~$1.55** (Sonnet 5, rough token-based estimate)
