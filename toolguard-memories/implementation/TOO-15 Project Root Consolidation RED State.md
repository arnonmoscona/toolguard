---
title: TOO-15 Project Root Consolidation RED State
type: note
permalink: toolguard/implementation/too-15-project-root-consolidation-red-state
tags:
- TOO-15
- task-memory
- red-state
---

# TOO-15 project-root marker consolidation -- RED checkpoint (2026-07-11 08:29)

## Status: RED confirmed, STOPPED before touching production code, awaiting GREEN approval.

## Mid-task design change from coordinator (superseding the original two-algorithm brief)
Coordinator pushed for a deeper merge: ONE function (`resolve_project_root`, with a
`strict: bool = False` param) owns 100% of the walk-up logic for all three former
implementations. `strict=True` = flat "nearest marker of any kind wins" (config.py /
env_config.py's use case). `strict=False` = existing tiered anchor-first-then-ambiguous
algorithm (migration_gate.py / corpus.py's use case, unchanged default).

## Architectural deviation I made from the coordinator's literal instruction (flagged for review)
The coordinator's message named `toolguard/tools/project_root.py` as the default home for
the canonical function. I relocated the ENTIRE implementation (RootStatus, RootCandidate,
ProjectRootResolution, resolve_project_root, STRONG_PROJECT_ANCHORS, DEFAULT_INDICATORS)
into **`toolguard/path_utils.py`** instead, with `toolguard/tools/project_root.py`
reduced to a thin re-export shim. Reason: `toolguard/tools/__init__.py`'s own docstring
states the `toolguard.tools` sub-package is "intentionally segregated from the core hook
logic so that automation tooling concerns do not bleed into the runtime permission
evaluation path." `toolguard/hook.py` directly imports `toolguard.config` and
`toolguard.env_config` (confirmed via grep). If `config.py`/`env_config.py` called
`toolguard.tools.project_root.resolve_project_root`, the live hook's import graph would
newly depend on the tools/automation package -- a real, documented boundary violation.
`path_utils.py` is already the shared leaf module all three sites import from (stdlib
only), so it is the correct home to preserve both "one function" AND the segregation
boundary. The coordinator's message explicitly allowed relocation ("renamed if you think
a better home/name applies, but keep it in one place"), so I proceeded rather than
blocking, but flagging this clearly since it's a more significant structural choice than
a mere rename.

Consequence: `migration_gate.py` and `corpus.py` need ZERO code changes (they already
import `resolve_project_root`/`ProjectRootResolution` from `toolguard.tools.project_root`,
which continues to work via the re-export shim; neither references `RootStatus` /
`is_vcs` directly -- verified by grep and full read).

## Rename mapping (old -> new)
- `toolguard.tools.project_root.VCS_MARKERS` -> dropped as a separate name; replaced by
  `toolguard.path_utils.STRONG_PROJECT_ANCHORS = (".git", ".hg", ".jj", ".claude", "CLAUDE.md")`
  (used directly, no redundant alias, since there's now only one module).
- `RootCandidate.is_vcs` -> `RootCandidate.is_anchor`
- `RootStatus.RESOLVED_VCS` ("resolved_vcs") -> `RootStatus.RESOLVED_ANCHOR` ("resolved_anchor")
- `_nearest_vcs` -> `_nearest_anchor` (private helper, moves to path_utils.py)
- `_all_non_vcs_candidates` -> `_all_non_anchor_candidates` (private helper, moves to path_utils.py)
- New: `toolguard.path_utils.CONFIG_ROOT_INDICATORS = STRONG_PROJECT_ANCHORS + ("pyproject.toml",)`
  -- the single shared indicator tuple for config.py's and env_config.py's `strict=True`
  calls (eliminates the two hardcoded duplicate tuples).
- `toolguard.config.find_project_root` / `toolguard.env_config.find_project_root` become
  thin wrappers: `resolve_project_root(start, strict=True, indicators=CONFIG_ROOT_INDICATORS).root`,
  raising RuntimeError (config.py, same message shape) or returning None (env_config.py)
  on no match. External behavior unchanged except the new anchors.

## 9-file trace results (traced, not just grepped)
Only **test_env_config.py** exercises the real (unmocked) `find_project_root` walk (class
`TestFindProjectRoot`, lines ~21-105) -- confirmed safe (no stray `.claude`/`CLAUDE.md` at
`/`, `/tmp` on this machine; `test_stops_at_home_directory` already mocks `Path.home()` to
an isolated tmpdir). Added 4 new tests there (.claude alone, CLAUDE.md alone, .hg alone,
.jj alone).

All other 8 files (test_config.py, test_configuration.py, test_hard_deny.py,
test_hierarchical.py, test_migration.py, test_takeover_mode.py, test_toml_config.py,
test_tools_decision_ledger.py) mock `find_project_root` (or `resolve_project_root`)
directly at every call site (`patch("toolguard.config.find_project_root", ...)` etc.) --
confirmed via reading every usage, not just grep-counting. None of them call
`get_env_config`/exercise `env_config.find_project_root` for real either (grep returned
zero matches for `get_env_config`/`env_config\.` in those 8 files). **No fixture fixes
needed in any of the 8** -- the real walk-up algorithm is never exercised by them, so
adding new markers cannot change their outcomes. `test_config.py` also had a real gap: NO
test anywhere exercised `config.find_project_root`'s real (unmocked) marker walk before
this change -- added a new `TestFindProjectRoot` class there (7 tests: git, pyproject,
claude, claude.md, hg, jj, raises-when-nothing-found) mirroring env_config's existing
pattern.

## Test changes made (RED)
- `test/unit/test_config.py`: import `find_project_root`; new class `TestFindProjectRoot`
  (7 new tests).
- `test/unit/test_env_config.py`: 4 new tests in existing `TestFindProjectRoot` class
  (claude dir, CLAUDE.md file, .hg dir, .jj dir -- each alone).
- `test/unit/test_tools_project_root.py`: renamed `RootStatus.RESOLVED_VCS` ->
  `RESOLVED_ANCHOR` in 2 existing tests (`test_vcs_root_resolves`,
  `test_vcs_root_wins_over_nearer_pyproject`); added 3 new tests
  (`test_claude_directory_alone_resolves_as_anchor`,
  `test_claude_md_file_alone_resolves_as_anchor`,
  `test_nearest_anchor_wins_regardless_of_kind` -- .claude nearer than a farther .git wins).
- `test/unit/test_tools_migration_gate.py`: renamed helper `_resolved_vcs` ->
  `_resolved_anchor`, `RootStatus.RESOLVED_VCS` -> `RESOLVED_ANCHOR`, updated 2 BDD
  docstrings ("resolved VCS root" -> "resolved anchor root").

## RED run result (2026-07-11 08:29)
`uv run python -m unittest discover -s test -t .` -> exit 1.
`Ran 1391 tests in 0.627s` -- `FAILED (failures=4, errors=11)`.
Baseline was 1377 passing (all). 1391 = 1377 + 14 net-new test functions.
Failing set (15, exactly the touched/new tests expected to fail pre-implementation):
- test_config.py: test_finds_claude_directory_alone, test_finds_claude_md_file_alone,
  test_finds_hg_directory_alone, test_finds_jj_directory_alone (ERROR -- RuntimeError
  raised, markers not yet recognized). The other 3 new tests in this class (git,
  pyproject, raises-when-nothing-found) PASS already -- sanity check that the new test
  code itself is correct against unchanged behavior.
- test_env_config.py: test_finds_claude_directory_alone, test_finds_claude_md_file_alone,
  test_finds_hg_directory_alone, test_finds_jj_directory_alone (FAIL -- returns None
  instead of the expected dir).
- test_tools_project_root.py: test_claude_directory_alone_resolves_as_anchor,
  test_claude_md_file_alone_resolves_as_anchor, test_nearest_anchor_wins_regardless_of_kind,
  test_vcs_root_resolves, test_vcs_root_wins_over_nearer_pyproject (all ERROR --
  AttributeError, RootStatus.RESOLVED_ANCHOR does not exist yet).
- test_tools_migration_gate.py: test_resolved_root_and_clean_tree_is_safe,
  test_resolved_root_but_dirty_tree_is_blocked (ERROR -- AttributeError, same reason).

Math checks out: 1377 baseline - 4 (existing tests now failing post-rename) + 3 (new
tests already passing) = 1376 passing; 1391 - 1376 = 15 failing. Nothing outside the
touched set newly broke.

## Next step: GREEN (blocked on approval)
Implement in `path_utils.py` (new canonical home), `config.py`, `env_config.py`,
`tools/project_root.py` (shim). `migration_gate.py`/`corpus.py` need no changes.

## Update (coordinator-requested gap fix, 2026-07-11 ~08:35)

Coordinator reviewed diffs directly, APPROVED the path_utils.py relocation, the rename
mapping, and the 9-file trace conclusion. Flagged one real gap: no test proved the actual
semantic differentiator between `strict=True` and `strict=False` (a nearer weak marker
must win in strict mode; a farther anchor must win in tiered/default mode). Without it, a
buggy strict=True that just unwraps the tiered algorithm's `.root` would pass every test
written so far.

Added 2 tests to `test/unit/test_tools_project_root.py`:
- `test_strict_mode_nearest_marker_wins_over_tiered_default` -- farther `.git` + nearer
  `pyproject.toml`; asserts `resolve_project_root(pkg, strict=True).root == pkg` (nearer)
  AND `resolve_project_root(pkg).root == self.root` (farther, tiered default) in one test.
- `test_strict_mode_never_returns_ambiguous` -- only a weak marker (pyproject.toml), no
  anchor anywhere; asserts `strict=True` resolves directly to `RootStatus.RESOLVED_ANCHOR`
  (not `AMBIGUOUS`). Documented in the docstring that `RESOLVED_ANCHOR` is reused for
  "found via the flat marker list in strict mode" even when the found marker isn't
  technically an anchor-tier marker -- a deliberate, documented choice, not an oversight.

Full-suite re-run confirms RED for the right reason: both new tests fail with
`TypeError: resolve_project_root() got an unexpected keyword argument 'strict'` (the
`strict` param does not exist yet). `Ran 1393 tests` (1391 + 2) -- `FAILED (failures=4,
errors=13)` (11 -> 13, +2 for the new tests; nothing else changed). Proceeding straight to
GREEN per coordinator's instruction (no second stop-and-report needed for this addition).
