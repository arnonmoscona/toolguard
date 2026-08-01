---
title: TOO-19 test log-dir isolation leak - fix report
type: note
permalink: toolguard/too-19/too-19-test-log-dir-isolation-leak-fix-report
---

tags: task-memory, TOO-19

## Summary

Fixed the test-isolation defect where the unit suite wrote real entries into
`logs/toolguard-<today>.md` and `logs/toolguard-discovery.jsonl`. Root cause:
`toolguard/env_config.py` has its own, separate `find_project_root()` (distinct
from `toolguard.config`'s), reading the real process `Path.cwd()` and not
patched by any existing test isolation. `toolguard.hook.main()` calls
`get_env_config()` unconditionally (before `load_configuration()`), so any test
driving `main()` without an explicit `TOOLGUARD_LOG_DIR` silently resolved the
real repo's `logs/` directory.

## Leaking tests found (all 3, confirmed exhaustively)

Method: ran each of the 61 `test/unit/test_*.py` modules individually with
`HOME`/`XDG_CONFIG_HOME` redirected to fresh temp dirs AND the working
directory pointed at a fresh, marker-free scratch temp dir (so
`env_config.find_project_root()`'s fallback -- which depends only on real
process cwd and cannot be overridden by any test's own `os.environ` clearing
-- can only ever resolve inside that scratch tree, never the real repo). This
required a second revision of the diagnostic script after the first revision
(which set `TOOLGUARD_LOG_DIR` via subprocess env while leaving cwd at the
real repo root) turned out to be unsafe: `ConfigIsolationMixin`'s
`isolate_config_environment()` calls `patch.dict(os.environ, env,
clear=True)`, which wipes ANY externally-set env var including my diagnostic's
override, causing the actually-affected test (`TestHardDenyThroughMain`) to
fall through to the real cwd-based resolution and silently miss my temp-dir
check entirely -- discovered only by re-checking the real log's discovery
count immediately after that run (1001 -> 1005) and realizing the "fixed"
diagnostic had itself leaked 4 entries into the real log. The corrected,
cwd-based method is immune to this because no test-level env clearing can
affect actual process cwd.

Confirmed leaking modules (all fixed):
- `test.unit.test_hook` -- 3 discovery writes (all `main()`-driving classes,
  none using `ConfigIsolationMixin`; they mock `load_configuration()` directly)
- `test.unit.test_hook_eval` -- 1 discovery write (`TestEvalMatchesLiveHookUnderFallback._run_live`,
  which drives `main()` WITHOUT `--eval` to compare verdicts against the
  read-only `--eval` path)
- `test.unit.test_hard_deny` -- 1 discovery write (`TestHardDenyThroughMain`,
  which DID already use `ConfigIsolationMixin` and still leaked, because the
  mixin's original scope covered only `toolguard.config`'s three anchors --
  `Path.home()`, `toolguard.config.find_project_root()`, `XDG_CONFIG_HOME` --
  and not `env_config`'s separate fourth one)

Total: 5 discovery entries per full-suite run (3+1+1), exactly matching the
originally reported measurement. Re-ran the full corrected diagnostic after
applying all fixes: 0/61 modules leak.

## Other log streams checked

- `log_command` -- always mocked (`patch("toolguard.hook.log_command")`) in
  every leaking test; never reached for real. Not a leak source today, but the
  structural guard (below) covers it defensively for the future, including its
  `config["log_dir"]` indirection (hook.py always passes `config=env_config`,
  never `log_dir=` directly, to `log_command`).
- `log_conflict` -- mocked wherever exercised in the leaking modules.
- `log_error` / `log_warning` -- not exercised unmocked by any leaking test;
  guarded defensively anyway (both take `log_dir` directly, called from
  `hook.py` and `config_divergence.py`).
- `log_crash` -- writes to `~/.toolguard/errors/` (HOME-relative, not the
  project `logs/` dir), so out of scope for "real project logs directory"
  specifically; not wrapped by this guard. HOME isolation for it is a
  pre-existing, separate concern already covered by `ConfigIsolationMixin`'s
  `Path.home()` patch where used.
- No conflict-log or crash-report files appeared in any of the 61 modules'
  isolated scratch log dirs.

## Fix: isolation at the right level

`test/unit/_config_isolation.py`:
- `ConfigIsolationMixin.isolate_config_environment()` now ALSO sets
  `TOOLGUARD_LOG_DIR` (to `tmp/logs`, not created on disk) inside the isolated
  env dict (via `setdefault`, so a caller's own `extra_env` can still
  override it), and exposes the path as `self.isolated_log_dir`. Return
  signature (`home, project`) unchanged -- 79 existing call sites all unpack
  exactly 2 values; adding a 3rd would have been a much larger, riskier diff
  for no real benefit since an instance attribute serves the same purpose.
  This alone fixed `TestHardDenyThroughMain` (test_hard_deny.py) with zero
  changes to that file.
- New `isolate_log_dir_for_module()`: a lighter, module-level (not
  per-TestCase) helper for test modules that never use
  `ConfigIsolationMixin` at all because they mock `load_configuration()`
  directly (test_hook.py, test_hook_eval.py). Retrofitting every individual
  test method in a ~2300-line file to call `isolate_config_environment()`
  would have been a much larger and more invasive diff than the leak
  warranted; a single `setUpModule()`/`tearDownModule()` pair using an
  additive (`clear=False`) `patch.dict` achieves the same effect with a
  ~25-line addition per file.

Retrofitted `test/unit/test_hook.py` and `test/unit/test_hook_eval.py` with
`setUpModule()`/`tearDownModule()` calling the new helper. `test_hard_deny.py`
needed no changes (already used the now-extended mixin).

`.claude/rules/test-config-isolation.md` updated: documents the fourth anchor
(`env_config`'s own project-root/log-dir resolution), the checklist item for
`isolate_config_environment()` now also covering `TOOLGUARD_LOG_DIR`, a new
checklist item for `isolate_log_dir_for_module()` (the mock-load_configuration
case), and a new "Structural guard against a silent regression" section
describing the guard below.

## Structural regression guard

New `test/unit/_real_log_dir_guard.py`, installed from `test/unit/__init__.py`
before any test module is imported (Python guarantees a package's
`__init__.py` runs before any of its submodules, for both `unittest discover`
and `python -m unittest test.unit.<module>`).

**Design considered and rejected**: a single test snapshotting the real
`logs/` directory's listing/mtimes before the suite and diffing after. Rejected
because a same-process `unittest` test can only observe state as of when IT
runs; `unittest discover`'s alphabetical-per-level ordering gives no guarantee
a "snapshot at start" test runs strictly first and a "diff at end" test runs
strictly last across all 61+ modules.

**Design chosen**: intercept the leak at its only possible source. Every
toolguard code path that can write to the real project `logs/` dir does so by
calling one of a fixed, small set of functions (`log_writer.log_command`,
`log_writer.log_discovery`, `error_log.log_conflict`, `error_log.log_error`,
`error_log.log_warning`) with a `log_dir` (or, for `log_command` specifically,
via `config["log_dir"]`). `install()` wraps each of these AT THEIR DEFINING
MODULE (not at each importer), so that `toolguard/hook.py`'s
`from toolguard.log_writer import log_command, log_discovery` (and similar for
`error_log`) binds directly to the guarded wrapper -- this only works because
`install()` runs before `toolguard.hook` is ever imported anywhere in the
process. The wrapper:
1. Detects when the resolved `log_dir` is the real repo's `logs/` dir or a
   path under it (`Path.resolve()` comparison, computed once from the guard
   module's own `__file__` location -- robust to cwd/invocation style).
2. When detected: does NOT call the real function at all (the write can never
   physically happen -- this is a genuine backstop, not just a detector), and
   records the offending call (function, resolved path, short call-stack
   excerpt) in a module-level registry.
3. Otherwise: calls straight through with no behavioural difference.

Surfaced two ways:
- `test_zz_real_log_dir_guard.py` (named to sort last, a convenience not a
  guarantee) asserts the registry is empty -- an ordinary, readable
  `unittest` FAILURE naming every offending call. Also contains a
  self-verification test (`TestRealLogDirGuardActuallyFires`) that calls
  `log_discovery` directly with the real `REAL_LOGS_DIR` and asserts (a) the
  event is recorded and (b) the real discovery JSONL file's
  existence/mtime is unchanged -- i.e. it proves the guard actually suppresses
  the write, not just detects it.
- `test/unit/__init__.py` also registers an `atexit` hook that re-checks the
  same registry once after the ENTIRE process's test run completes and
  force-exits nonzero with a stderr banner if anything leaked. This is what
  actually delivers "reliable regardless of discovery/test order" -- it does
  not depend on the dedicated test running last, or even being discovered at
  all (e.g. `python -m unittest test.unit.test_hard_deny` alone, with no other
  module in the run).

### Verification that the guard actually fires (required step)

Temporarily reverted the `ConfigIsolationMixin` fix (commented out the
`TOOLGUARD_LOG_DIR` line in `_config_isolation.py`) to reproduce the
`test_hard_deny.py` leak, then:

1. `uv run python -m unittest test.unit.test_hard_deny test.unit.test_zz_real_log_dir_guard -v`
   -> `test_zz_real_log_dir_guard`'s `test_no_real_log_dir_writes_were_attempted`
   FAILED with a full message naming `toolguard.log_writer.log_discovery`, the
   attempted `log_dir` (the real repo path), and the call stack down to
   `test_hard_deny.py:767` (`main()` -> `hook.py:659` -> the guard wrapper).
   Overall run: `FAILED (failures=1)`, exit code 1.
2. Discovered in the process that `sys.exit(1)` inside an `atexit` callback is
   silently caught by CPython 3.14.5 and reported as "Exception ignored in
   atexit callback" WITHOUT changing the process exit code -- verified by
   running `test.unit.test_hard_deny` ALONE (leak reintroduced, no dedicated
   guard test present): exit code was **0** despite the guard correctly
   detecting and suppressing the write and printing its banner to stderr. This
   would have made the atexit backstop look like it worked while silently not
   delivering the one property it exists for. Fixed by switching to
   `os._exit(1)` (with explicit `sys.stdout.flush()`/`sys.stderr.flush()`
   first, since `os._exit()` skips normal buffered-stream flushing).
   Re-verified: same reproduction (leak reintroduced, running ONLY
   `test.unit.test_hard_deny`, no guard test in the run) now exits **1**.
3. Restored the mixin fix (`env.setdefault("TOOLGUARD_LOG_DIR", ...)`),
   confirmed via `diff` against a pre-revert backup that the file matches the
   intended fixed state, and re-ran `test_hard_deny` + `test_hook` +
   `test_hook_eval` + `test_zz_real_log_dir_guard` together: all pass, 117
   tests, OK.

This is a documented, real bug found and fixed during this task (not merely a
hypothetical caveat): the `sys.exit`-in-`atexit` behavior on Python 3.14.5
does not raise a visible test failure, it just silently fails to change the
exit code, which is exactly the "guard that cannot fail" anti-pattern the task
warned against. Caught only because the verification step was actually
performed with a leak-only (no dedicated test) reproduction, not just the
combined run.

## Delta-0 proof (headline verification)

Read-only checks throughout (`grep -c '**Discovery**' logs/toolguard-2026-07-31.md`);
never edited/pruned anything under `logs/`.

- Baseline before any work: 1001.
- Accidental leak DURING diagnosis (documented above, from the first,
  incorrect revision of the diagnostic script + individual reproduction runs
  before the cwd-based method was adopted): 1001 -> 1005 (+4, matching
  test_hook's 3 + test_hook_eval's 1 -- test_hard_deny's leak in that phase
  went to the real dir too but via the corrected diagnostic which caught it
  without writing, since by then the cwd-based method was already in use for
  that specific check). This is real, human-visible data now sitting in
  Arnon's live log file; flagged here rather than silently left implicit.
- Final bracketed proof, with the complete fix in place:

  ```
  BEFORE: 1005
  <TMPH=$(mktemp -d); TMPX=$(mktemp -d)
   HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .>
  EXIT: 0
  Ran 2012 tests in 1.175s
  OK
  AFTER: 1005
  ```

  Delta: **0**.

## Verification checklist (all required items)

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"`
  -> **OK**, 2012 tests (2010 baseline + 2 new guard tests in
  `test_zz_real_log_dir_guard.py`).
- `uv run ruff check .` -> **All checks passed!**
- `uv run ruff format --check .` -> **134 files already formatted** (ran
  `ruff format .` once, which reformatted the 3 new/changed guard files to
  house style; re-checked clean afterward).
- Real-log delta-0 proof: see above.

## Files changed

- `test/unit/_config_isolation.py` -- extended `isolate_config_environment()`
  to isolate `TOOLGUARD_LOG_DIR`; added `isolate_log_dir_for_module()`.
- `test/unit/test_hook.py` -- added `setUpModule()`/`tearDownModule()` using
  the new module-level helper.
- `test/unit/test_hook_eval.py` -- same.
- `test/unit/__init__.py` -- installs the guard; registers the `atexit`
  backstop.
- `test/unit/_real_log_dir_guard.py` (new) -- the guard implementation.
- `test/unit/test_zz_real_log_dir_guard.py` (new) -- the dedicated regression
  test plus the guard's own self-verification test.
- `.claude/rules/test-config-isolation.md` (symlinked into `~/projects/dot_files`,
  not tracked by this repo's git) -- documents the fourth anchor, the extended
  checklist, and the new structural-guard section.

`test_hard_deny.py` required NO changes (already used the mixin, inherits the
fix automatically).

## Note on scope

Several other files in the working tree show as modified/untracked in `git
status` (e.g. `test_hard_deny.py`'s `additional_context` tuple-shape change,
various `toolguard/*.py` files, several other `TOO-19` memory notes) -- these
are pre-existing, uncommitted work from earlier in this branch, not part of
this task. Confirmed via `git diff` that none of my edits to `test_hard_deny.py`,
`test_hook.py`, or `test_hook_eval.py` touch anything beyond the log-dir
isolation additions described above; the rest of each file's diff predates
this session.
