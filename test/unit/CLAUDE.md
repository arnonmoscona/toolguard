# CLAUDE.md (test/unit/)

Supplements the project root `CLAUDE.md`. Applies to everything under `test/unit/`.

## Why this file exists

This repo dogfoods toolguard on itself: a real `~/.claude/toolguard_hook.toml` (and,
since TOO-30, potentially a real `~/.config/toolguard/rules/`) genuinely exists on any
machine that develops toolguard. `toolguard/config.py`'s discovery machinery reads real
filesystem state from exactly three controllable anchors -- `Path.home()`,
`toolguard.config.find_project_root()`, and the `XDG_CONFIG_HOME`/`CLAUDE_SETTINGS_PATH`
environment variables. A test that doesn't redirect all three it touches can silently
depend on -- or be broken by -- whatever real config happens to exist on the machine
running the suite. This already caused 2 real, confirmed test failures (`test_takeover_mode.py`,
found 2026-07-23) before the shared isolation facility below existed. See
basic-memory (project='toolguard'): "TOO-30 pre-push follow-up: suite-wide test
isolation cleanup" for the full investigation and "TOO-30 Test Isolation Cleanup -
Implementation Report" for the retrofit.

## Writing or editing a test in this directory: work through this checklist

- [ ] **Does this test call anything that reaches `toolguard.config`'s discovery path**
  (`load_configuration()`, `_discover_levels()`, `find_project_root()`,
  `discover_config_files()`, or a production function that calls one of those
  transitively, e.g. `migrate()`, `load_file_path_patterns()`)? If NO -- e.g. the test
  builds a `Configuration` directly from hand-constructed `ConfigLayer`/`Provenance`
  objects with zero file I/O -- no isolation is needed. Stop here.
- [ ] If YES: does the test's `TestCase` class mix in `ConfigIsolationMixin` (import
  from `test.unit._config_isolation`)? If not, add it:
  `class TestFoo(ConfigIsolationMixin, unittest.TestCase):`
- [ ] Call `home, project = self.isolate_config_environment(...)` as the first line of
  the test (or once from `setUp` if every test in the class needs the same shape). Do
  NOT hand-roll a new `tempfile.TemporaryDirectory()` + `patch("toolguard.config.find_project_root", ...)`
  + `patch.object(Path, "home", ...)` combination -- that is exactly the ad hoc,
  inconsistent pattern this facility replaced.
- [ ] Pass `xdg_config_home=` / `extra_env=` if the test needs to control those.
- [ ] **Exception case**: if the test needs `project` genuinely NESTED several
  directories under `home` (testing the ancestor walk itself), or a marker positioned
  ABOVE home, the mixin's fixed sibling layout (`tmp/home`, `tmp/project`) cannot
  represent that -- hand-roll `tempfile.TemporaryDirectory()` +
  `patch("toolguard.config.find_project_root", ...)` + `patch.object(Path, "home", ...)`
  as before, but **add a one-line comment saying so** (e.g. `# mixin can't represent a
  nested home/project layout -- hand-rolled`). A silent exception is indistinguishable
  from a missed retrofit; do not leave one silent. See `test/unit/test_hierarchical.py`
  for the existing precedent (1 such exception, commented) -- and check whether
  `isolate_config_environment()`'s `project_under_home=` parameter (nests project several
  directories under home, for tests exercising the ancestor walk itself) already covers your
  case before assuming a hand-rolled exception is needed at all.
- [ ] Never patch `Path.home` or `find_project_root` via any mechanism other than
  `ConfigIsolationMixin` or the commented hand-rolled exception above (no new ad hoc
  variants).

## Before pushing: audit for new isolation gaps

Production code can grow new ways to touch the real filesystem that
`ConfigIsolationMixin` doesn't yet cover. Before a push that touched `toolguard/config.py`
or any test in this directory since the last push:

- [ ] Diff `toolguard/config.py` (and anything it delegates discovery to) against the
  last push: did it add a new environment variable, a new fixed real-filesystem path
  (like `~/.claude` or the XDG rules directory), or a new function that reads
  `Path.home()` / walks the filesystem independently of `find_project_root`? If so,
  `ConfigIsolationMixin.isolate_config_environment()` in `test/unit/_config_isolation.py`
  needs a new parameter or a new patched anchor to cover it.
- [ ] Grep this directory for `Path.home()`, `patch.object(Path, "home"`,
  `patch("toolguard.config.find_project_root"`, `patch("toolguard.config.Path.home"`,
  and `XDG_CONFIG_HOME` outside of `_config_isolation.py` itself and the commented
  hand-rolled exceptions. Any new, uncommented hit is either a missed retrofit or a new
  ad hoc pattern that should be folded into the shared mixin instead.
- [ ] Run the full suite (`uv run python -m unittest discover -s test -t .`) with a
  throwaway change to your real `~/.claude/toolguard_hook.toml` (e.g. temporarily
  setting `takeover_mode.enabled = true` if it isn't already) to sanity-check nothing
  newly depends on real machine state. Revert the throwaway change after.
