---
title: TOO-45 R5cd implementation report
type: note
permalink: toolguard/too-45/too-45-r5cd-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Implemented TOO-45 R5c and R5d on branch `too-45`. R5's `--predicates` now reports `PASS`; `--layers` direction violations are down to the single deliberately-deferred `hook -> tools.decision` (R6's job). Suite: 2,368 OK (2,367 baseline + 1 new regression test). Corpus: no differences. `--guard`: PASS, 12 canaries. `ruff format`/`ruff check --no-cache`: clean.

## R5c -- `update_check` entry point/library split

Same shape as R5b (its report was the template). Moved everything importable out of `toolguard/update_check.py` into a new module `toolguard/install_update.py`: `InstallKind`, `InstallInfo`, `distribution_name`, `_read_direct_url_json`, `_file_url_to_path`, `_walk_up_to_git_root`, `is_git_worktree`, `local_repo_head`, `local_remote_head`, `detect_install`, `remote_head`, `run_upgrade`, `_check_git`, `_check_local`, `_check`, `installed_origin`, and the `EXIT_*` constants. `toolguard/update_check.py` is now a ~65-line thin CLI wrapper (`main()` only) around `install_update._check`.

### Why `foundation`, not `runtime`

Unlike R5b, this move was **not forced by a `--layers` violation** -- `tools.installer` (`tooling`) importing `update_check` (`runtime`) was already layer-legal (`tooling` may reach `runtime`); the scoping trace correctly flagged this as "real but layer-legal". The choice of layer for the new module was an independent architectural question, decided by import shape: the moved code imports only `toolguard._git` and `toolguard.constants` -- both `foundation` leaves -- exactly the same shape as its existing sibling `toolguard/install_provenance.py` (a related but distinct question: that module asks whether the CURRENTLY GOVERNING copy is a stale/shadowed checkout; `install_update` asks whether the INSTALLED distribution is behind the remote). Checked `install_provenance.py` first for a possible merge/reuse opportunity -- concluded they're siblings, not duplicates, matching R5b's own precedent of keeping "a different concern" as a separate module rather than folding it into a near neighbour. Added `install_update` to `.pyscn.toml`'s `foundation` layer's `packages` list; confirmed `--layers` completeness stays 100%.

### Files touched

- New: `toolguard/install_update.py` (function bodies byte-identical to the pre-move `update_check.py`, only docstrings/cross-references updated).
- `toolguard/update_check.py`: trimmed from 578 lines to a thin CLI (`main()`), docstring rewritten to point at `install_update`.
- `toolguard/tools/installer.py`: repointed `from toolguard.update_check import (...)` to `from toolguard.install_update import (...)`; fixed 2 docstring cross-references (`_binary_status`, `skills-status` help text) that named the old module path.
- `.pyscn.toml`: added `"install_update"` to the `foundation` layer's `packages` list.
- `test/unit/test_update_check.py`: renamed the module alias throughout to `install_update` for every class EXCEPT `TestMain` (which still exercises `update_check.sys`/`update_check._check`/`update_check.main` directly, since `main()` stays in the CLI module and `patch.object(update_check, "_check", ...)` still intercepts correctly -- `main()` resolves `_check` from its own module globals via the `from toolguard.install_update import _check` binding, same mechanism R5b used for `auto_migrate.migrate`). All 43 tests pass unchanged in substance.
- `test/unit/test_tools_installer.py`: one import line repointed (`InstallInfo`/`InstallKind`). The 127 `patch.object(installer_module, "detect_install"/"remote_head", ...)` call sites needed NO changes -- they patch attributes on `tools.installer`'s own namespace (where the names are bound via `from toolguard.install_update import (...)`), unaffected by which module supplies the value.
- `test/unit/test_git_helper.py`: this module cross-checks that `update_check.py` and `install_provenance.py` both delegate to the shared `toolguard._git.run_git` helper (TOO-19 M3 dedup guarantee). Repointed `update_check._DEFAULT_DIST_NAME` and `update_check.local_repo_head`/`update_check.run_git` assertions to `install_update`, since that's where the git-touching code and the constant now actually live; docstring updated.
- `docs/architecture.md`: left unchanged, matching R5b's own precedent -- the package-structure tree is a curated subset (it doesn't list `install_provenance.py` either), and the `update_check.py # toolguard-update-check entry point` line is still accurate (it never claimed to hold the logic).
- `technical-notes.md:1065`: fixed one precise now-false module-path claim ("`toolguard/update_check.py` (TOO-16), which compares...") to name both the CLI and the new logic module. Grepped the whole repo for `toolguard.update_check.` / `toolguard/update_check.py` afterward -- this was the only precise hit.
- `test/unit/test_architecture_fitness.py`: fixed a **pre-existing, R5b-introduced** staleness while I was in the same area -- `test_relabeling_pyscn_toml_layer_map_does_not_change_r5_verdict` builds a "maximally gamed" `.pyscn.toml` via three chained `str.replace()` calls against literal copies of the layer package-list strings. R5b's `permission_migration` addition to the `config` layer had already made the third `replace()` a silent no-op (old_string no longer matched), and my `install_update` addition to `foundation` made the second one a silent no-op too. `str.replace()` doesn't raise on no-match, and the test's own sanity check (`assertNotEqual(gamed_text, real_toml_text)`) only proves *at least one* of the three fired, not all three -- so the test was quietly exercising a weaker "gaming attempt" than it claimed, on both counts. Fixed both `old_string`s to match the current real `.pyscn.toml` content and updated the `new_string`s to preserve `permission_migration` while still appending `log_writer` (the intended config-layer gaming move). Verified the test still passes with the corrected, now-accurate strings.

## R5d -- `config_divergence -> error_log` layer violation

### What `config_divergence` actually needed `error_log` for, and the inversion

`check_and_warn_divergence` had exactly one call to `error_log.log_warning` (to write the structured `logs/toolguard-warning-*.md` entry) alongside its own direct `print(warning_message, file=sys.stderr)` (an independent, immediate user notice -- confirmed `error_log._log_entry` ALSO echoes to stderr internally, so these two prints were always redundant in content, not mechanism; I preserved both to avoid changing observable behaviour, since fixing that pre-existing duplication was out of scope for this task).

Argued from what each module is FOR: `config_divergence` (`config`-layer) detects drift between native and toolguard permissions -- a pure comparison concern. `error_log` (`runtime`-layer) owns the structured, per-stream Markdown audit log, a side-effecting concern the ideal picture assigns to `runtime`'s "record" role. The only real caller of `check_and_warn_divergence` is `toolguard/hook.py`, which is `runtime` and already legitimately imports `error_log` for three other log calls. So the fix is the "return the diagnostic to a caller that is allowed to log it" shape: `check_and_warn_divergence` now returns a new frozen dataclass, `DivergenceCheckResult(divergent_patterns, warning_message, corrective_steps)`, instead of calling `log_warning` itself; `hook.py`'s `_run_divergence_check` calls `error_log.log_warning` when `warning_message is not None`. Checked `error_log.py`'s other importers first (it's also imported by `hook.py` directly for 3 other calls, and by several tests) before concluding the fix belongs on the `config_divergence` side, not by moving `error_log` -- moving `error_log` would have been architecturally backwards (it's correctly `runtime`-layer; every one of its callers is `runtime` or `tooling`).

Used a frozen dataclass per CLAUDE.md's "prefer frozen dataclasses over tuples for any multi-value return that is not a strict pair" -- this is a 3-value return (patterns/message/steps), not a pair.

### Files touched

- `toolguard/config_divergence.py`: added `DivergenceCheckResult`; `check_and_warn_divergence`'s return type changed from `List[str]` to `DivergenceCheckResult`; removed `from toolguard.error_log import log_warning` and the `log_warning(...)` call; kept the direct stderr `print` and marker-file creation (both are filesystem/stdlib concerns, not `error_log` dependencies). Both early-return paths (marker exists today; no divergence found) now return `DivergenceCheckResult(divergent_patterns=[])`.
- `toolguard/hook.py`: `_run_divergence_check` now calls `log_warning(divergence.warning_message, divergence.corrective_steps, log_dir)` when `warning_message is not None`, then checks `divergence.divergent_patterns` for the auto-migrate branch (previously checked the bare list). Docstring rewritten to state the new division of responsibility.
- `test/unit/test_config_divergence.py`: 4 tests (`test_no_divergence`, `test_with_divergence`, `test_deduplication`, `test_takeover_mode_ignored_patterns`) updated to read `.divergent_patterns` instead of comparing the return value directly as a list; `test_no_divergence`/`test_with_divergence`/`test_deduplication` also gained assertions on `.warning_message`/`.corrective_steps` to pin the new contract. Given/When/Then docstrings updated to match.
- `test/unit/test_hard_deny.py`: one `patch("toolguard.hook.check_and_warn_divergence", return_value=[])` updated to `return_value=DivergenceCheckResult(divergent_patterns=[])` -- this mock's target function is genuinely reachable in this test (unlike the three in `test_logging_streams.py` below), so a bare `[]` would have hit `AttributeError: 'list' object has no attribute 'divergent_patterns'` in `hook.py`'s new consumption code. Added the one import line needed.
- `test/unit/test_logging_streams.py`: left the 3 pre-existing `patch("toolguard.hook.check_and_warn_divergence", return_value=[])` mocks untouched -- verified all three sit behind `hook_mod._divergence_check_done = True` set immediately before the call, so the guard clause returns before `check_and_warn_divergence` is ever invoked; confirmed by running the full suite, which stayed green. **Added one new test**, `TestDivergenceWarningLogging.test_divergence_check_writes_warning_log_via_hook`, following the exact isolation pattern of the neighbouring `TestM1SingleSourceWarning` class (`ConfigIsolationMixin`, `load_configuration(..., ignore_env_override=True)`). This is the regression test the task's own CLAUDE.md rule requires ("a fix without a regression test in the main suite is not finished") -- **no existing test exercised the real (unmocked) hand-off from `check_and_warn_divergence` to `hook.py`'s `log_warning` call**; every other test touching this path mocks `check_and_warn_divergence` entirely, so none of them would notice a regression where `hook.py` forgot to log the returned message. The new test drives `hook._run_divergence_check` directly against a real project fixture with a genuine divergent pattern and asserts a `toolguard-warning-*.md` file is written containing it.
- `test/unit/test_architecture_fitness.py`: updated the `TestSmokeAgainstRealTree.test_check_layers_runs_on_real_tree` docstring from "2 pre-existing DIRECTION violations" to "1 pre-existing DIRECTION violation (hook -> tools.decision)", crediting R5d for closing `config_divergence -> error_log` (same docstring R5b had already partially updated for its own third-violation removal).

## Doc-drift sweep

Grepped the whole repo for `check_and_warn_divergence` and `config_divergence` after the change. All other hits (`rule_entry.py`, `config.py`, `auto_migrate.py`, `permission_migration.py`, `test_auto_migrate.py`, `test_hierarchical.py`, `test_configuration.py`, `docs/architecture.md`) reference `get_native_permissions`/`get_toolguard_permissions`/`find_divergent_patterns`/`is_tool_wrapper` or the module's general existence -- none of them made a claim about `check_and_warn_divergence`'s return type or its logging behaviour, so none needed changes.

## Console-script smoke test (not mocked)

Ran the real installed `toolguard-update-check` console script (via `uv run --project /home/arnon/projects/toolguard toolguard-update-check`) against this actual checkout, no mocks:

```
$ uv run --project /home/arnon/projects/toolguard toolguard-update-check
toolguard update available: 11d1fd092 -> 532de02f8
Checkout: /home/arnon/projects/toolguard
Manual update steps (editable install -- git pull is sufficient):
  git -C /home/arnon/projects/toolguard pull
EXIT: 1
```

Also exercised `--quiet` (still prints when behind, per contract), `--upgrade` (correctly refuses to auto-run for a local/editable install and prints the manual-steps note instead -- no working-tree mutation), and `--help` (argparse help text, exit 0). This exercises the full path: `pyproject.toml [project.scripts]` entry-point resolution -> `update_check.main()` -> `install_update._check()` -> `detect_install()` (real `importlib.metadata` + real `git` subprocess calls) -> `_check_local()` -> `local_repo_head()`/`local_remote_head()` (real `git rev-parse`/`git ls-remote` against this actual checkout and its real `origin` remote).

Also smoke-tested the OTHER real importer, `tools.installer`'s `skills-status` subcommand (`_binary_status()`, which reuses `detect_install`/`remote_head`/`local_remote_head` from the new module):

```
$ uv run --project /home/arnon/projects/toolguard python -m toolguard.tools.installer skills-status --project-dir /home/arnon/projects/toolguard
binary install status:
  kind: local
  installed commit: 11d1fd092bb19b30d7a70fbd20eb06014611b7c6
  remote commit: 532de02f8e187f36cdc0e4a93c6a1c99031840ea
  update status: UPDATE AVAILABLE -- run: uv tool upgrade toolguard
...
```

Both real, unmocked runs confirm the split works end to end for both of the module's real (not test-only) consumers.

## Acceptance -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2368 tests in 29.875s
OK
```

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.35s. End-to-end: 61 cases in 3.39s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook
```

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (1):
  - hook (runtime) -> tools.decision (tooling) at line 697 [local import]
```
(Only the deliberately-deferred R6 item remains, as instructed -- untouched.)

```
$ uv run python tools/architecture_fitness.py --predicates
=== R5: PASS ===
  entry point modules (7, from pyproject.toml [project.scripts]): hook,
  scripts.migrate_permissions, session_start, tools.installer, tools.maintenance,
  tools.security_audit, update_check
  (out of scope -- toolguard/parser/ ...)
```

```
$ uv run ruff format . && uv run ruff check --no-cache .
150 files left unchanged
All checks passed!
```

## Files touched (summary)

New (1): `toolguard/install_update.py`

Modified, substantive (5): `toolguard/update_check.py`, `toolguard/tools/installer.py`, `toolguard/config_divergence.py`, `toolguard/hook.py`, `.pyscn.toml`

Modified, mechanical/doc-drift/test (8): `test/unit/test_update_check.py`, `test/unit/test_tools_installer.py`, `test/unit/test_git_helper.py`, `test/unit/test_architecture_fitness.py`, `test/unit/test_config_divergence.py`, `test/unit/test_hard_deny.py`, `test/unit/test_logging_streams.py`, `technical-notes.md`

14 files total (1 new + 13 modified), across two combined sub-steps (R5c+R5d) in a single delegated task -- above the usual single-task guideline in isolation, but this magnitude was explicitly pre-authorized: it matches R5b's own precedent (13 files for one sub-step) and the task prompt explicitly overrode the scoping trace's blast-radius deferral reasoning for R5c. No files deleted, no tests deleted, no files touched outside the repository. No git write operations were issued (`git status`/`diff` read-only only, plus one read of `git status --porcelain | wc -l` for the baseline).

## Reuse check (no reimplementation)

R5c is a pure relocation (function bodies byte-identical, only docstrings/cross-references updated) -- checked `install_provenance.py` first as a candidate for merging into, concluded it's a distinct concern (stale-checkout detection vs. remote-update detection) and kept them as siblings, consistent with R5b's own "different concern, separate module" precedent. R5d introduces one new type (`DivergenceCheckResult`), a small frozen dataclass with no logic to duplicate against stdlib/existing code.

## Backups / rollback

Original bytes of all 14 files this task touched (13 pre-existing + the not-yet-created `install_update.py`, whose rollback is simply deleting it) were copied to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r5cd-backups/` before any edit, with a sha256 manifest (`_MANIFEST.sha256`), verified intact at the end of the task (`sha256sum -c` reported all `OK`).

## Self-review

- Anti-pattern scan: no async/await, no threading, no new local imports (the one function-local import inside `hook.py` at line 697, `hook -> tools.decision`, is R5a's pre-existing sanctioned exception, untouched by this task). `DivergenceCheckResult` is a frozen dataclass, per the multi-value-return convention.
- `uv run python -m py_compile` on every touched production file: clean.
- `uv run ruff format .` / `uv run ruff check --no-cache .`: clean (one file reformatted by the format pass, `test_update_check.py`, pure whitespace).
- Diffed every touched file against its pre-edit backup individually (not just `git diff`, since the working tree carries ten other uncommitted TOO-45 stages) to confirm each edit was exactly the intended change.
- Requirements re-checked against the original prompt line by line before writing this report; every acceptance command above was actually run for this report, not recalled from memory.
- The nature of the R5c work matched R5b's shape exactly (mechanical entry-point/library split, patch-target updates, doc-drift sweep) -- no surprise requiring a stop-and-report, as the task's escape hatch anticipated.

## Elapsed time / cost estimate

Session ran roughly 17:58 to 18:20 local time (~22 minutes of tool-execution wall time observed via timestamps in the transcript; this undercounts think/generation time between tool calls).

Rough phase breakdown:
- Planning/reading (scoping trace, R5b report, source files for both sub-steps, layer-map/import analysis, deciding `install_update`'s target layer, tracing the `check_and_warn_divergence` return-type blast radius including the `_divergence_check_done` guard subtlety): the largest share.
- Implementation (writing `install_update.py`, trimming `update_check.py`, rewriting `test_update_check.py` in full, `config_divergence.py`'s dataclass + `hook.py`'s consumption, ~8 test-file edits, the pre-existing gamed-toml test-string fix, the new regression test): moderate.
- Verification (multiple full suite runs, corpus verify, guard/layers/predicates, ruff x2, two live console-script smoke tests, per-file backup diffs): the rest.

Estimated cost: Sonnet 5 at typical subagent token volumes for a task this size (several large file reads including a full 780-line source file rewritten as a ~700-line test file, one new ~380-line module, ~10 test-file edits, several multi-minute suite runs). Rough order of magnitude: low single-digit dollars total; not tracked precisely since this environment doesn't expose token counts directly to the agent.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 R5 scoping trace]]
- relates_to [[TOO-45 R5b implementation report]]
