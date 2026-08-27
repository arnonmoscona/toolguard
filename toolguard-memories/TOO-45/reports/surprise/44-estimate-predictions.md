---
title: 44-estimate-predictions
tags:
- TOO-45
- estimate
permalink: toolguard/too-45/reports/surprise/44-estimate-predictions
---

# Blinded touch-set prediction -- proposed ticket 44 (ambient state read at point of use)

Prediction made from the ticket text and a path/line-count/docstring inventory only. No source file was read, nothing was grepped, no test was run.

## 1. Predicted touch set

### Production -- modified

| file | reason | confidence |
|---|---|---|
| `toolguard/path_utils.py` | named in ticket: gains the single `home()` accessor (and probably `cwd()`), plus the one place `Path.home()` raising is handled | high |
| `toolguard/error_reporter.py` | named in ticket: the validated template, extended into the stdin/stdout writer | high |
| `toolguard/env_config.py` | named in ticket: becomes the only door for `os.environ`, absorbing the 12 stray reads | high |
| `toolguard/hook.py` | the edge. Owns the stdin read and the stdout decision write (the 59 + 58 patches), and is where ambient values would be resolved once and passed down | high |
| `toolguard/config.py` | 2095 lines of home-anchored discovery (`~/.claude`, `~/.toolguard`); almost certainly the largest single holder of the 23 `Path.home()` calls | high |
| `toolguard/log_writer.py` | `resolve_log_dir` is home-anchored; already injection-shaped per the layer-map note, so it is the cheapest site to route through the accessor | high |
| `toolguard/session_start.py` | the second entry point, with the same stdin/stdout/home shape as `hook.py`; a fix that skips it leaves half the seam | high |
| `toolguard/once_per_store.py` | `_STORE_PATH` lives under the home directory -- the suite carries a dedicated `_real_once_per_home_guard`, which only exists because this module resolves home itself | medium |
| `toolguard/auto_migrate.py` | reads `~/.claude/settings.local.json`; the ticket cites it by name as the module whose mocks were inert | medium |
| `toolguard/error_log.py` | home-anchored log destinations sitting directly beneath `error_reporter`; changing the reporter's construction reaches it | medium |
| `toolguard/install_provenance.py` | inspects where the governing package was installed from -- home-relative install roots and environment variables | medium |
| `toolguard/install_update.py` | same family as `install_provenance`; git remote checks against a home-relative checkout | medium |
| `toolguard/tools/installer.py` | 2337 lines of install/uninstall path work; the heaviest tooling consumer of home and env | medium |
| `toolguard/config_divergence.py` | reads Claude's native settings files, which are home-anchored | low |
| `toolguard/subagent.py` | transcript lookup under `~/.claude/projects` | low |
| `toolguard/testing/sandbox.py` | fabricates throwaway homes and environments; a new accessor is exactly the thing a sandbox must be able to point elsewhere | low |
| `.pyscn.toml` | the declared layer map must place any newly added module, and the ticket explicitly argues about which layer a wrapper may live in | medium |

### Production -- added

| file | reason | confidence |
|---|---|---|
| `toolguard/testability.py` (**addition**) | the ticket reserves it by name as the destination for any wrapper that fails the "would you keep it if the suite vanished" test, and says to keep it in the design so nothing gets smuggled elsewhere | medium |

### Production -- deleted

None expected.

### Test -- modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_hook.py` | 3396 lines and the main holder of the `sys.stdin` / `sys.stdout` / `log_command` / `load_configuration` patches the ticket counts | high |
| `test/unit/test_error_reporter.py` | the wrapper being extended; new stream-writer behaviour lands here | high |
| `test/unit/test_env_config.py` | env access consolidating into this module changes what its tests assert | high |
| `test/unit/test_configuration.py` | 3977 lines over discovery; the likeliest home of a large share of the 18 `pathlib.Path.home` patches | high |
| `test/unit/test_auto_migrate.py` | the ticket names it as the file where every mock was inert; a real seam is the fix | high |
| `test/unit/test_config.py` | project-root and discovery tests keyed to home | medium |
| `test/unit/test_session_start.py` | second entry point's stdin/stdout and home patches | medium |
| `test/unit/test_hook_error_reporter.py` | asserts `main()` owns one reporter; extending the reporter to stdout changes that wiring | medium |
| `test/unit/test_log_writer.py` | log-dir resolution moving to the accessor | medium |
| `test/unit/test_hook_eval.py` | `--eval` mode is a second stdout consumer | medium |
| `test/unit/test_once_per_store.py` | store-path resolution moving to the accessor | medium |
| `test/unit/_config_isolation.py` | the shared isolation mixin is the natural place to swap stdlib patching for the new seam; 18 files depend on it | medium |
| `test/unit/test_architecture.py` | enforces the layer map; a new module or a new downward import trips it | medium |
| `test/unit/test_hierarchical.py` | home-anchored discovery across layers | low |
| `test/unit/test_sandbox.py` | follows any change to `testing/sandbox.py` | low |
| `test/unit/test_install_provenance.py` | follows the install-family changes | low |

### Test -- added

| file | reason | confidence |
|---|---|---|
| `test/unit/test_path_utils.py` (**addition**) | there is no `test_path_utils.py` in the inventory today, and the ticket's central new public surface (`home()`, and its raising path -- ticket 23's root cause) lands in that module | medium |
| `test/unit/test_testability.py` (**addition**) | only if `testability.py` is created non-empty | low |

### Test -- deleted

None expected.

## 2. Concentration set

Where the work actually lives, in order:

1. `toolguard/hook.py` -- the edge that must resolve ambient values once and hand them down; also the origin of the two largest patch blocks.
2. `toolguard/path_utils.py` -- the single home/cwd accessor, the cheapest and most-cited direction.
3. `toolguard/error_reporter.py` -- extended from stderr into a stdin/stdout writer.
4. `toolguard/config.py` -- the largest existing consumer of ambient home, and the module that decides whether direction 1 actually retires seams or just adds a ninth one.
5. `test/unit/test_hook.py` -- where the retired patches are actually deleted, and the file that proves the refactor worked.
6. `toolguard/env_config.py` -- the third wrapper, smallest of the three.

Everything else in the touch set is a call-site migration, not design work.

## 3. Expected counts

**Production**

| | count | plausible range |
|---|---|---|
| modified | 14 | 9-18 |
| added | 1 | 0-2 |
| deleted | 0 | 0-1 |

**Test**

| | count | plausible range |
|---|---|---|
| modified | 12 | 6-20 |
| added | 1 | 0-2 |
| deleted | 0 | 0-1 |

The listed table is slightly longer than the point estimate on purpose: the low-confidence rows are named because they are plausible, not because I expect all of them to land. `.pyscn.toml` is counted as production.
