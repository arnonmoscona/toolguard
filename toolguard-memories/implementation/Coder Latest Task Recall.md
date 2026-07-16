---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-15
- implementation
---

> **NOTE: The content below this line, up to the "--- ARCHIVED (stale, prior task) ---" marker,
> is the CURRENT ACTIVE task recall. Everything after that marker is a STALE recall from a
> previous, unrelated TOO-15 sub-task (project-root marker consolidation) and should be
> ignored for the current work.**

# Coder Latest Task Recall (TOO-15: migrate() target-level bug, RED phase only)

Started: 2026-07-16 14:41 EDT

## Ticket / context
TOO-15 install-runbook hardening. Real-machine repro (2026-07-16): running
`toolguard-migrate --dry-run` inside the toolguard repo's own checkout (which has
`.git` + `pyproject.toml`, so `find_project_root()` correctly resolves it as a
project root) proposed writing to `~/.claude/toolguard_hook.toml` instead of
creating `<project_root>/.claude/toolguard_hook.toml`.

## The bug
`toolguard/scripts/migrate_permissions.py`, function `migrate()`, around
line 743-762 (search "Find target config file (prefer TOML, create if none exists)"):

```python
target_config_path = None
target_format = None

for file_path, source_type, file_format in config_files:
    if source_type == "toolguard_hook":
        target_config_path = file_path
        target_format = file_format
        break

if target_config_path is None:
    target_config_path = project_root / ".claude" / "toolguard_hook.toml"
    target_format = "toml"
    print(f"No toolguard config found. Will create: {target_config_path}")
else:
    ...
```

`config_files` = `discover_config_files(project_root)` (toolguard/config.py) which
mixes PROJECT-level and USER-level entries in ONE priority-ordered list (project
toolguard_hook.local/settings.local/toolguard_hook/settings, THEN same 4 at user
level `~/.claude/`), only including files that exist on disk.

Bug: loop scans the WHOLE list (project + user) for first existing
`source_type == "toolguard_hook"` file. If project_root has no toolguard_hook
config of its own but `~/.claude/toolguard_hook.toml` exists (e.g. user-scope
install), the loop silently picks the USER file as migration target -> project's
rules get added to the GLOBAL user config instead of creating a project-level one.

## Correct behavior
Migration should ALWAYS target project_root's own `.claude` dir:
- If `project_root/.claude` already has an existing toolguard_hook config
  (`.local.toml`/`.local.json` preferred over `toolguard_hook.toml`/`.json`, TOML
  over JSON at same base name - same precedence discover_config_files already
  encodes for one level) -> migrate into THAT file.
- If not -> CREATE `project_root/.claude/toolguard_hook.toml`. Never fall through
  to an existing file at a DIFFERENT directory (ancestor or home), even if
  discover_config_files returned one.
- When project_root itself resolves to Path.home() (find_project_root() fallback,
  e.g. no project markers above cwd), project_root/.claude IS ~/.claude, so
  existing/create logic naturally does the right thing - no special-casing needed.

Fix (NOT to be done in this RED phase): restrict the "search for existing
toolguard_hook file" loop in migrate() to ONLY config_files entries whose
containing directory is `project_root / ".claude"`. Do NOT change
discover_config_files() itself (config.py) - used elsewhere intentionally for
multi-level priority (read/merge for evaluation).

## Scope: RED PHASE ONLY
- Write/extend tests in test/unit/test_migration.py pinning down correct behavior.
- Do NOT touch toolguard/scripts/migrate_permissions.py or toolguard/config.py.
- Confirm: full suite green except new bug-exposing test(s), which must fail with
  an assertion mismatch (wrong path chosen), not an exception.

## Scenarios required (class TestMigrationTargetLevel or similar)
1. project has own existing toolguard_hook.toml AND different user-level one also
   exists -> migrate targets PROJECT's own file. (Guard - likely already passes.)
2. project has NO toolguard_hook config of its own, but user-level
   ~/.claude/toolguard_hook.toml exists -> migrate should CREATE
   project_root/.claude/toolguard_hook.toml, NOT target user file.
   **THIS IS THE BUG - must FAIL against current code.**
3. project_root resolves to home dir itself (find_project_root fallback), user-level
   toolguard_hook.toml exists there -> migrate targets that existing file (project
   == user collapses correctly). Guard - likely already passes.
4. Neither project nor user toolguard_hook config exists anywhere -> migrate
   creates project_root/.claude/toolguard_hook.toml. Guard - likely already passes.

## Fixture guidance
- Reuse existing end-to-end migrate() invocation pattern already in
  test/unit/test_migration.py (large file, 1600+ lines) - look at
  TestBackupCreation and any existing migrate()-level integration tests first.
- migrate() signature per migrate_permissions.py::main(): (project_root, dry_run,
  auto_sort, backup_dir).
- Need to patch Path.home() to point at a separate temp "home" dir distinct from
  project_root temp dir - check how test_migration.py / test_config.py already
  mock/patch home directory resolution.

## Success criteria
- Full suite run: `uv run python -m unittest discover -s test -t .`
- All pre-existing tests pass.
- Only new bug-exposing test (scenario 2) fails, with clear assertion diff showing
  wrong target path chosen (not an exception).
- Report back which tests are new/failed/why, wait for explicit approval before
  GREEN phase.

--- ARCHIVED (stale, prior task) ---

# Coder Latest Task Recall (TOO-15: project-root marker consolidation)

Started: 2026-07-11 08:19

## Ticket
TOO-15. Project-root marker consolidation in toolguard.

## Environment / conventions
- Python 3.14, stdlib `unittest` (NOT pytest). Run: `uv run python -m unittest discover -s test -t .`
- NEVER `ruff format` (corrupts `except (A, B):` on this project -- known regression). Use `uv run ruff check .` only.
- `uv run python` only, never bare python.
- No git commits -- leave tree dirty. (Tree already has unrelated uncommitted WIP on config.py caching (mtime+size), installer.py, docs, pyproject.toml -- NOT part of this task, do not touch/revert.)
- BDD Given/When/Then docstrings on every new/changed test.
- No async/threading/local-imports. Doc comments on changed functions.

## Background (already investigated by requester -- use as given, do not re-derive)
Three "find project root" implementations:
1. `toolguard/config.py::find_project_root` -- markers `("pyproject.toml", ".git")`, RAISES RuntimeError if none found. Used by LIVE HOOK to find `<root>/.claude/toolguard_hook.toml`.
2. `toolguard/env_config.py::find_project_root` -- markers `(".git", "pyproject.toml")`, returns `Optional[Path]` (None if not found). Used for `.env`/log-dir resolution.
3. `toolguard/tools/project_root.py::resolve_project_root` -- MIGRATION SAFETY GATE (used by `migration_gate.py`, `corpus.py`). Structured result (RootStatus.RESOLVED_VCS / AMBIGUOUS / NONE / RESOLVED_OVERRIDE). Walks ALL THE WAY UP for a VCS marker (.git/.hg/.jj) FIRST across the whole climb; only if none anywhere does it fall back to build-manifest candidates (pyproject.toml, package.json, etc) as AMBIGUOUS requiring caller to ask user. DELIBERATELY different from #1/#2's "nearest marker of any kind wins" walk. PRESERVE this distinction, do not merge away.

#1 and #2 are near-identical trivial wrappers around `toolguard.path_utils.find_nearest_marker` with own hardcoded marker tuples -- TRUE unjustified duplication, consolidate.

RootStatus.RESOLVED_VCS / is_vcs in project_root.py consumed only internally by migration_gate.py, corpus.py, test_tools_project_root.py, test_tools_migration_gate.py -- confirmed via grep no skill-markdown/JSON-contract string reliance on literal "vcs"/"resolved_vcs" -- renaming is safe, internal-only.

## Required changes

### 1. Add `.claude` (dir) and `CLAUDE.md` (file) as project-root markers, everywhere
Maintainer's decision: `.claude/` dir or `CLAUDE.md` file is unambiguous evidence of project root, SAME trust tier as VCS marker (.git/.hg/.jj) -- not a weaker "ask first" candidate.

### 2. Consolidate TRUE duplication (config.py + env_config.py)
- Add ONE canonical "strong project anchor" marker tuple in `toolguard/path_utils.py` (shared leaf module both already import from):
  `STRONG_PROJECT_ANCHORS = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")`
  (adding .hg/.jj to config.py/env_config.py too for consistency with project_root.py -- natural low-risk extension, do it)
- `config.py::find_project_root` and `env_config.py::find_project_root` should each call `find_nearest_marker(start, STRONG_PROJECT_ANCHORS + ("pyproject.toml",))` (or small shared private helper if preferred, but eliminate duplicated hardcoded tuples) -- keep EXTERNAL behavior unchanged otherwise: #1 still RAISES RuntimeError with existing message shape when nothing found; #2 still returns None. Do not change any caller of either function.

### 3. project_root.py: add new anchor markers, rename inaccurate "VCS" naming (internal-only, verified safe)
- Extend strong-anchor tier to include .claude/CLAUDE.md alongside .git/.hg/.jj -- reuse SAME STRONG_PROJECT_ANCHORS constant from path_utils.py (do not re-declare separate list).
- Rename: `VCS_MARKERS` -> `ANCHOR_MARKERS` (or clearer name -- must not imply "version control only"), `RootCandidate.is_vcs` -> `is_anchor`, `RootStatus.RESOLVED_VCS` -> `RootStatus.RESOLVED_ANCHOR` (enum VALUE string can change too, e.g. "resolved_anchor" -- verified nothing external depends on literal string). Update reason/docstring text saying "version-control root" to accurate text (e.g. "project anchor (version control or a Claude Code project marker)"). Update module top docstring rationale to reflect .claude/CLAUDE.md now first-class anchors, not just build-manifest-tier.
- `DEFAULT_INDICATORS` keeps pyproject.toml/package.json/etc in WEAKER (ambiguous, ask-first) tier -- unchanged tier, now composed as `ANCHOR_MARKERS + (weaker build-manifest tuple, unchanged contents)`.
- Update two call sites (migration_gate.py, corpus.py) and both existing test files (test_tools_project_root.py, test_tools_migration_gate.py) for the rename.

## Process -- STRICT RED-GREEN WITH A CHECKPOINT

1. RED first. Before touching production code:
   - Update existing tests asserting OLD names/behavior (RootStatus.RESOLVED_VCS, is_vcs, old marker tuples) to new ones.
   - Add NEW tests: `.claude` alone (no .git) sufficient for config.py's find_project_root (does not raise) and env_config.py's (returns dir, not None); same for bare CLAUDE.md file; project_root.py's resolve_project_root resolves .claude-only and CLAUDE.md-only dirs as RESOLVED_ANCHOR (not AMBIGUOUS), SAME priority as .git (nearest anchor across whole tier wins, matching existing `_nearest_vcs` behavior, just renamed); .hg/.jj alone now also sufficient for config.py/env_config.py.
   - TRACE (not just grep) existing tests that hardcode OLD default marker sets or would be affected by ADDING new markers -- prior RED pass on this ticket missed 20 tests by grep-only auditing, do not repeat. Specifically check: test_config.py, test_configuration.py, test_env_config.py, test_hard_deny.py, test_hierarchical.py, test_migration.py, test_takeover_mode.py, test_toml_config.py, test_tools_decision_ledger.py (found via grep referencing find_project_root directly/indirectly) -- read each usage, confirm whether adding .claude/CLAUDE.md/.hg/.jj as markers could change outcome (e.g. fixture dir with stray .claude it did NOT intend as root marker, or relies on find_project_root raising/returning None in a dir that would now resolve). Fix such fixtures (e.g. isolated tmpdir with no incidental .claude) rather than just changing assertion, UNLESS the test's actual intent was already about marker detection.
   - Run full suite; confirm failing set is EXACTLY touched/added tests, nothing else newly broken, no test silently passing for wrong reason.
2. STOP AT RED. Do NOT touch production code yet. Report red state to requester (SendMessage to 'main'): every test file/function added or changed with one-line note, exact failing set + reasons, specifically flag anything found in the 9-file trace needing a fixture fix (not just assertion change). WAIT for approval before GREEN.
3. GREEN after approval: implement in path_utils.py, config.py, env_config.py, project_root.py, migration_gate.py, corpus.py until whole suite passes. Don't edit tests during green except genuine mistake in own new test (call out explicitly). Run FULL suite + `uv run ruff check .`.

## Deliverable
When done (green): basic-memory report (project 'toolguard', tag TOO-15) with final shared-constant design, rename mapping (old->new, every symbol), which of 9 traced test files needed fixture fix vs assertion update and why, final test counts. Give path + short summary. Do NOT touch docs/*.md or any other module.

## Baseline
Full suite before starting: 1377 tests, OK (2026-07-11 08:19).


## RED phase result (2026-07-16, completed)

Added `TestMigrationTargetLevel` class (4 new tests) to
`test/unit/test_migration.py`, appended before the `if __name__ == "__main__"`
block, right after `TestMigrationWithRedundantPatterns`. No production code
touched (`toolguard/scripts/migrate_permissions.py`, `toolguard/config.py`
untouched).

Tests added (all patch `pathlib.Path.home` to an isolated temp dir, distinct
from `project_root`, to avoid leaking the real dev machine's `~/.claude`):

1. `test_migration_targets_project_own_existing_config_not_user_level` - PASSES
   (guard). Project has own toolguard_hook.toml + different user-level one exists
   -> migrate targets project's own file, user file untouched.
2. `test_migration_creates_project_config_instead_of_using_user_level` -
   **FAILS against current code (the bug)**. Project has no toolguard_hook of its
   own; user-level `~/.claude/toolguard_hook.toml` exists -> current code writes
   into the user file instead of creating
   `project_root/.claude/toolguard_hook.toml`. Failure:
   `AssertionError: False is not true : migrate() must create a project-level
   toolguard_hook.toml rather than silently writing into the user-level config`
   -- clean assertion mismatch, not an exception.
3. `test_migration_project_root_equal_to_home_targets_the_shared_config` - PASSES
   (guard). project_root == home dir (single shared .claude) -> targets that file.
4. `test_migration_creates_project_config_when_neither_level_has_one` - PASSES
   (guard). Neither level has a config -> creates project-level file.

Full suite verification (baseline vs with new tests, via file-copy compare, NOT
git stash -- git write ops are prohibited for the agent):
- Baseline (original test_migration.py, restored via `git show HEAD:...` copy,
  no git write commands used): 1431 tests, OK.
- With new tests: 1435 tests, 1 failure (exactly test #2 above), rest pass.

`uv run ruff check test/unit/test_migration.py` and
`uv run python -m py_compile test/unit/test_migration.py` both clean. No
async/threading/local-import anti-patterns introduced.

Only file changed by this task: `test/unit/test_migration.py` (+193 lines, pure
addition). Other dirty files in the tree (AGENTS.md, docs/*, pyproject.toml,
uv.lock, docs/gh-cli-rules-example.toml) were already modified before this task
started (per session's initial git status) and were not touched.

STATUS: RED phase complete. Awaiting explicit approval before GREEN phase
(implementing the fix in migrate_permissions.py, scoping the existing-file
search loop to only `config_files` entries whose containing directory is
`project_root / ".claude"`).
