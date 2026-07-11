---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-15
- implementation
---

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