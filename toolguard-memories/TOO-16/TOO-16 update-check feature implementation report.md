---
title: TOO-16 update-check feature implementation report
type: note
permalink: toolguard/too-16/too-16-update-check-feature-implementation-report
tags:
- TOO-16
- implementation-report
---

# TOO-16 update-check feature implementation report

Built by the main agent inline (feature-coder spawns failed twice with 529 Overloaded;
proceeded directly). 2026-06-23. Nothing committed -- Arnon does git.

## What was built

### New module `toolguard/update_check.py` + entry point
- pyproject `[project.scripts]` gained `toolguard-update-check = "toolguard.update_check:main"`.
- Compares the installed git commit (PEP-610 `direct_url.json` `vcs_info.commit_id`, read via
  `importlib.metadata`) against remote HEAD (`git ls-remote <url> HEAD`, `GIT_TERMINAL_PROMPT=0`,
  10s timeout, offline-safe -- never hangs/raises). Source URL is read from `direct_url.json`
  too (works for forks; no hardcoded URL).
- Public/testable functions: `distribution_name()`, `installed_origin() -> (url, commit)|None`,
  `remote_head(url) -> sha|None`, `run_upgrade(dist_name) -> int`; `_check(quiet, do_upgrade)`
  holds the logic; `main()` does argparse + `sys.exit`.
- **Exit-code contract:** 0 = up to date, 1 = update available, 2 = could not determine
  (not a git install -> editable/registry, OR remote unreachable/offline, OR git/uv missing).
- Flags: `--upgrade` (runs `uv tool upgrade <dist>` only when behind), `--quiet` (silent when
  up to date; still prints when behind or unknown -- for shell-startup use).
- Prints the upgrade command using the DISTRIBUTION NAME from metadata, so it stays correct
  after a future PyPI rename.

### Docs
- `docs/quickstart.md`: new `## Keeping toolguard up to date` section (between Step 0 and Step 1)
  with a 3-option menu: (1) manual `uv tool upgrade toolguard` [+ `toolguard-update-check` to
  peek]; (2) throttled once-a-day STARTUP ALERT shell snippet (stamp file under `~/.cache/
  toolguard/`, alert only, calls `--quiet`); (3) opt-in AUTO-UPDATE snippet (same throttle,
  calls `--upgrade`) with a SECURITY CAVEAT (pulls/runs remote HEAD into the global hook with no
  pull-time review; fine if you are sole author/gatekeeper, risky otherwise -> recommend option 2).
  Throttling lives in the shell snippets; the tool stays stateless. Also de-staled the "Upgrade
  later" line (plain `uv tool upgrade` is verified reliable; dropped the `--force` lead).
- `docs/agent-guides.md`: one-line pointer to the new section from the install step.

### Tests -- `test/unit/test_update_check.py` (21 tests, all green)
- installed_origin: git install -> tuple; no vcs_info -> None; read_text None -> None; metadata
  PackageNotFoundError -> None.
- remote_head: parses sha; nonzero exit -> None; OSError -> None; empty output -> None.
- _check: up-to-date(0); --quiet suppresses up-to-date stdout; update-available(1) prints command;
  --quiet still prints when behind; command uses distribution name; not-a-git-install(2);
  remote-unreachable(2); --upgrade runs run_upgrade only when behind; not when up to date.
- run_upgrade: returns subprocess code; uv-missing -> EXIT_UNKNOWN.
- main: exits with _check's code; passes quiet/do_upgrade flags through.

## Verification
- Full suite: 725 -> **746** (+21), green WITH ruff clean.
- Real CLI smoke in the editable dev venv -> "not a git install" exit 2 (correct graceful path).
- git-install E2E (exit 0/1 against a real remote) is verifiable once this is pushed + the global
  tool upgraded -- the global `toolguard-update-check` does not exist until then (chicken-and-egg).

## Gotcha discovered (saved to auto-memory)
`ruff format` on this 3.14 project STRIPS parens: `except (A, B):` -> `except A, B:`. Valid on
3.14 (PEG parser; semantically a tuple, catches both -- verified) and ruff's house style here.
Do NOT re-add the parens; ruff re-strips them. See auto-memory `project_ruff_strips_except_parens`.

## For Arnon to review
- Exit-code semantics (0/1/2) and the `--quiet`/`--upgrade` behavior.
- The auto-update shell snippet + its security caveat wording.
- Whether to bump version again (currently 0.3.0, already pushed) and add release notes
  (per the new CLAUDE.md pre-push checklist).
