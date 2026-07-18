---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-15
- task-memory
- implementation-report
---

## Task
TOO-15 completion-gate item: `toolguard-install skills-status` read-only diagnostic subcommand
(binary-install freshness + bundled-skill install state at user/project scope, robust to broken
symlinks and incomplete installs), plus wiring the toolguard-maintenance skill to offer (never
auto-apply) remediation using it.

## Files changed (3 total, all in scope)

1. **`toolguard/tools/installer.py`**
   - New import: `from toolguard.update_check import InstallKind, detect_install,
     local_remote_head, remote_head` (line ~60).
   - New section "skills-status" (~208 new lines) between `cmd_seed_hard_deny` and the "CLI
     wiring" section:
     - `_SKILLS_STATUS_HELP` -- argparse description constant, matches house style of every
       other subcommand's help text.
     - `_classify_skill_dir(path) -> str` -- returns `'missing'`/`'installed'`/`'invalid'`.
       `missing` relies on `Path.exists()` correctly returning `False` for a broken/dangling
       symlink (verified live, see tests below). `installed` requires `path.is_dir()` (follows
       symlinks) AND `(path / "SKILL.md").is_file()`. Anything else that exists is `invalid`.
     - `_binary_status() -> dict` -- wraps `detect_install()` + `remote_head()` /
       `local_remote_head()` (no git/network/comparison logic reimplemented, only these existing
       public functions called and their results compared). Returns
       `{kind, installed_commit, remote_commit, update_available, note}`; `update_available` is
       `None` (never a crash) when the kind is unknown or the remote is unreachable.
     - `cmd_skills_status(args) -> int` -- always returns 0; only raises `InstallerError` on a
       genuine `OSError` while reading state (wrapped in try/except around the classification +
       binary-status calls). `--project-dir` defaults to `str(Path.cwd())`. Text output mirrors
       `cmd_discover_projects`'s indented-summary house style; JSON output is
       `{"binary": {...}, "skills": [...]}`.
   - `_build_parser()`: new `skills-status` subparser with `--project-dir` (optional, default
     cwd) and `--format {text,json}` (default text), following the `discover-projects` precedent
     (no `_add_scope_args`, since this always checks both scopes).
   - No other logic was touched. `ruff format` (scoped to only this file + the test file, not
     repo-wide) reflowed a number of pre-existing lines it had not previously been run against
     (line-wrap changes, quote-style, and the already-accepted 3.14
     `except A, B:` unparenthesized-tuple form -- see project memory
     `project_ruff_strips_except_parens`, confirmed valid/intentional on this 3.14+ project, not
     a bug). No logic changed in any pre-existing line; confirmed by reading the full diff.

2. **`test/unit/test_tools_installer.py`**
   - New import: `os`, and `from toolguard.update_check import InstallInfo, InstallKind`.
   - New `TestSkillsStatus(InstallerTestCase)` class (12 tests) covering:
     - Fresh state: both skills missing at both scopes.
     - Both skills fully installed (real dirs + SKILL.md) at both scopes.
     - Symlink to a REAL valid skill dir elsewhere -> `installed` (dogfooding pattern).
     - **Broken/dangling symlink** (`os.symlink` to a nonexistent target) -> `missing`, no crash
       -- the specific footgun called out in the task.
     - Real directory with no `SKILL.md` -> `invalid`.
     - Binary status: GIT kind with update available, GIT kind with unreachable remote (reports
       `unknown`/`None`, never fails), UNKNOWN kind (reports plainly, exits 0).
     - `--project-dir` omitted -> defaults to `Path.cwd()` (mocked).
     - Read-only: no journal entry or backup is ever written.
     - `--format text` is non-JSON and mentions every skill name + binary kind.
     - `--format json` is valid JSON with `binary`/`skills` top-level keys and expected per-entry
       fields.
   - All `detect_install`/`remote_head` calls are mocked via `patch.object(installer_module, ...)`
     (a helper `_mock_git_up_to_date()` started via `addCleanup`, mirroring
     `test_update_check.py`'s mocking style) -- no real git/network calls. Confirmed this
     mattered: before mocking was added to 3 tests that initially omitted it, the class took 2.5s
     (real `git ls-remote` calls against this repo's own origin); after mocking, 0.017s.
   - Ruff format also reflowed some pre-existing unrelated lines in this file (multi-line call
     wraps collapsed to single lines) -- no logic changes.

3. **`skills/toolguard-maintenance/SKILL.md`**
   - New "## Pre-flight: install/skills freshness check" section, inserted right after "Hard
     constraints" and before "How this skill runs -- the passes" (a setup/diagnostic step, not
     part of the judgement-heavy curation passes).
   - Instructs running `toolguard-install skills-status --format json` first.
   - Extended the existing dev-mode substitution table (the skill's own documented "sole place"
     the `uv run python -m ...` form is defined) with a third row:
     `toolguard-install ...` -> `uv run python -m toolguard.tools.installer ...` -- rather than
     hardcoding a dev-form inline, per the task's explicit instruction not to bake that in outside
     the established convention.
   - Binary update available -> tell user, offer `uv tool upgrade toolguard`, never auto-run.
   - Missing/invalid skill(s) -> tell user which skill(s) at which scope(s), offer
     `toolguard-install install-skills`, explicit **per-item** scope choice (user vs project),
     with the tradeoff explained (audit/maintenance lean user-level; project-specific lean local).
   - Everything current -> brief acknowledgement, move on.

## Test count
Before: 1472 tests (baseline run, OK).
After: 1484 tests (12 new in `TestSkillsStatus`), OK.
Full suite: `uv run python -m unittest discover -s test -t .` -- green, 0.7-0.8s.

## Lint/format
`uv run ruff check toolguard/tools/installer.py test/unit/test_tools_installer.py` -- all checks
passed. `uv run ruff format` was run scoped to only these two files (not repo-wide) per the task
instructions; `py_compile` clean on both.

## Deviations from the original task spec
- None substantive. One micro-decision: extended the skill's existing dev-mode substitution table
  with a `toolguard-install` row instead of hardcoding an inline dev-form comment next to the new
  pre-flight command, to honor the skill's own stated invariant that the table is the "sole place"
  that form is defined.

## Known limitations
- `_binary_status()`'s genuine-error path (`InstallerError` on OSError) is not directly unit
  tested since `Path.exists()`/`is_dir()`/`is_file()` swallow `OSError` internally in this Python
  version, making it hard to trigger without deeper mocking; the try/except is defensive per the
  spec's explicit ask, not exercised by a dedicated test.
- Unrelated pre-existing uncommitted changes exist in the working tree (`README.md`,
  `docs/agent-guides.md`, `docs/configuration.md`, `docs/quickstart.md`, untracked
  `docs/auto-mode.md`) that predate this session and were not touched by this work -- flagged for
  awareness, not part of this diff.

## Self-review completed
- Anti-pattern scan: no async/await, no threading, no local imports, no new dependency, no Bash
  used for file edits (Edit/Write tools only).
- Ruff check clean, py_compile clean, full suite green.
- Live manual smoke test of `skills-status` (text and json) against the real repo confirmed
  correct output before writing the automated tests.
- Requirements re-verified against `implementation/TOO-15 coder task recall- skills-status
  subcommand.md`.

## Time/cost estimate (rough)
- Phase 1 (planning, reading installer.py/update_check.py/tests/SKILL.md): ~15 min, ~$0.40
- Phase 2 (implementation: installer.py + tests + iteration on mock-patching bugs): ~20 min, ~$0.55
- Phase 3 (self-review: ruff, full suite runs, diff review): ~5 min, ~$0.15
- Phase 4 (SKILL.md doc change + this report): ~5 min, ~$0.10
- Total: ~45 min, ~$1.20 (Sonnet, rough token-based estimate; not precise)
