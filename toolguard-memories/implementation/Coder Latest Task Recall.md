---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-15
- implementation
---

## Task: TOO-30 pre-push follow-up -- suite-wide test isolation cleanup

Branch too-30. Feature implementation already complete/green (1511 tests passing).
This is a PURE mechanical refactor of test isolation mechanism -- NOT a TDD cycle,
NOT new production behavior, test assertions/intent must stay unchanged.

### Problem
`toolguard/config.py` discovery reads real filesystem state from 3 controllable anchors:
`Path.home()`, `toolguard.config.find_project_root()`, `XDG_CONFIG_HOME`/`CLAUDE_SETTINGS_PATH`
env vars. Most tests don't isolate `Path.home()`, so they can silently depend on real
machine state (this repo dogfoods toolguard on itself -- real `~/.claude/toolguard_hook.toml`
and potentially real `~/.config/toolguard/rules/` exist). Already caused 2 real failures in
test_takeover_mode.py (inline-patched earlier; must now replace with shared mechanism).

### Deliverable 1: new file `test/unit/_config_isolation.py`
Leading underscore so `unittest discover`'s `test*.py` pattern skips it.
Exact content given in the prompt (docstring wording may be adjusted, but class name
`ConfigIsolationMixin`, method name/signature `isolate_config_environment(self, *,
xdg_config_home=None, extra_env=None)`, and return shape `(home, project)` are FIXED,
not open for redesign).

Key design: uses `TestCase.enterContext()` (stdlib 3.11+) so no `with` nesting needed at
call sites -- call `home, project = self.isolate_config_environment()` as first line of a
test method (or from setUp). Patches `Path.home`, `os.environ` (clear=True + extra_env +
optional XDG_CONFIG_HOME), and `toolguard.config.find_project_root`.

### Deliverable 2: retrofit ALL of these 8 files (no exceptions)
1. test/unit/test_configuration.py -- retire `_isolated_hierarchy` context manager
   entirely (~9 call sites). 4 TOO-30 classes (TestRulesDirectoryDiscovery,
   TestRulesDirectoryMergeSemantics, TestRulesDirectoryValidationAndProvenance,
   TestRulesDirectoryExplicitModeBypass) + any other filesystem-touching class use mixin.
   EXCEPTION: TestRulesDirectoryMergeSemantics builds Configuration directly from
   hand-built layers, zero FS I/O -- leave alone, no isolation needed.
2. test/unit/test_takeover_mode.py -- replace 2 inline `patch.object(Path, "home", ...)`
   blocks with mixin. Also audit ~2 other config-discovery call sites in
   TestFilePathToolTakeoverFiltering/TestBashTakeoverFiltering for the same gap.
3. test/unit/test_hierarchical.py -- 18 calls, 0 isolation currently. Highest risk file.
4. test/unit/test_hard_deny.py -- 4 calls, 0 isolation.
5. test/unit/test_toml_config.py -- 2 calls, 0 isolation.
6. test/unit/test_logging_streams.py -- 1 call, 0 isolation.
7. test/unit/test_config.py -- 1 existing ad hoc Path.home() patch -- consolidate onto mixin.
8. test/unit/test_migration.py -- 4 existing ad hoc Path.home() patches -- consolidate onto mixin.

Pattern: replace ad hoc tempfile.TemporaryDirectory() + patch("toolguard.config.find_project_root")
(+ maybe patch.object(Path,"home")) dance with `home, project = self.isolate_config_environment(...)`,
keep building .claude dirs/files under home/project exactly as before. Should generally
REDUCE indentation/boilerplate, not add it.

### Hard constraint
Do NOT change what any test asserts, what config content it writes, or its BDD Given/When/Then
meaning. If isolating a previously-unisolated test causes it to fail, or pass for a seemingly
different/coincidental reason -- DO NOT silently fix the assertion. STOP and report it as a
suspected latent bug in the final summary, with diagnosis.

### What NOT to do
- Do not touch toolguard/config.py or any other production file.
- No new dependencies (stdlib-only, enterContext-based; pyfakefs explicitly rejected).
- Do not change BDD docstring meaning (wording tweaks OK if docstring described old temp-dir
  mechanics literally).

### Verification required
1. `uv run python -m unittest discover -s test -t .` -- all passing, same total (1511) or +0.
   Zero failures/errors.
2. `uv run ruff check .` -- clean. Do NOT run `uv run ruff format` (project override --
   no ruff style config, format churns quotes and previously corrupted `except (A, B):` tuples).
3. `git diff --stat` -- confirm toolguard/config.py and all non-test files untouched; only
   the 8 test files + new test/unit/_config_isolation.py should appear (NOTE: config.py is
   ALREADY modified in the working tree from TOO-30's feature phase itself -- that's
   pre-existing/expected, not something I introduce. I must not add further changes to it).
4. Report per-file: how many isolation call sites touched, and any test whose pass/fail
   behavior changed once properly isolated.
5. Write task report to basic-memory (project=toolguard, directory 'TOO-30').

### Success criteria
- Full test suite green, same count.
- ruff check clean.
- Only the 9 expected files touched (8 retrofitted + 1 new).
- No behavior/assertion changes except where flagged as suspected latent bugs.
