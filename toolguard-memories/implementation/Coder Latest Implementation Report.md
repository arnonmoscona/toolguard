---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- TOO-15
- task-memory
- implementation-report
---

# LATEST SESSION (2026-08-07): TOO-45 compound/resolve cycle removal

(Everything below this line down to the next `---` is this session's report; older content below belongs to previous tasks and is retained only for history.)

## Summary

Implemented TOO-45 Plan B (compound/resolve cycle removal) with all 5 judgment refinements (R1-R5), in 7 verified steps. Abandon gate NOT taken. Full detail, including "what turned out wrong" and the dynamic cycle-verification trace, is in the ticket-scoped report: `toolguard-memories/TOO-45/reports/compound-cycle-implementation.md` (permalink `toolguard/too-45/reports/compound-cycle-implementation`).

## Files changed

- `toolguard/compound.py` -- added `CommandUnit` (with `audits_as_one: bool`, judgment R1), `decompose`, `judge_unit` (absorbs old `_resolve_leaf_detailed` + the `UndecidableSegment` branch, no callbacks), `_unit_from_tuple`. `_combine_strictest` now takes `List[UnitVerdict]`. `_resolve_leaf_detailed` deleted. `resolve_outer`/`record_unit` parameters and their type aliases deleted from the legacy driver.
- `toolguard/resolve.py` -- `resolve_bash_permission_detailed` now drives `compound.decompose`/`judge_unit`/`_combine_strictest` directly; `_decide` returns a strict `(UnitVerdict, Optional[ConflictOverride])` pair; `_resolve_one`/`_resolve_outer`/`_record_unit` deleted.
- `toolguard/hook.py`, `toolguard/config_types.py` -- docstring-only fixes (stale references to the deleted mechanism).
- `test/unit/test_compound_resolve_seam.py` -- new, 17 tests: sub_matches characterization (Plan B step 0, the corpus does NOT track this field), the 12-cell ask-floor fallback matrix (judgment R3), the stub-override-never-leaks test (judgment R3), `_unit_from_tuple`'s own test + judge_unit's two new raise conditions (judgment R5).

## Verification

Cycle gone: verified both structurally (`judge_unit` takes zero `Callable` params; `resolve.py` no longer imports `resolve_compound_permission_detailed`) and dynamically (`sys.settrace` trace across 3 real decisions: 0 calls from `toolguard.compound` back into `toolguard.resolve`).

Full gate: 2604 unit tests OK; corpus `--verify` OK, no differences (6401 in-process + 61 end-to-end); architecture fitness `--layers` 100% complete / 0 violations; `--predicates` R1/R2/R3/R5/R6 all PASS; `ruff check .` clean. No golden regenerated, no pre-existing test modified.

## Note on concurrent work

`toolguard/config.py` and `toolguard/permission_resolution.py` show modified in git status but from a concurrent coder-subagent session (mtimes 10:16-10:22, before my edits started at 10:44) -- not my work, flagged in the ticket report, not touched by me. That other session's own report may be the one this note previously had at the top before this prepend (the note appears to be shared/stacked across sessions, not one-writer-per-run; overwrite was attempted first and rejected by the tool as an existing-note conflict).

## Self-review

Ruff format + check clean on all touched files. No async/await, no threading, no local imports introduced. py_compile clean. All 5 judgment refinements (R1-R5) implemented and each has dedicated test coverage.

---
## UPDATE: adversarial-review response addressed (same session)

`touch_set_score.py` no longer computes any score/rate/ratio (Monte Carlo proof that both the
count and the rate are granularity-biased -- see `touch-set-adversarial-report.md`). It is now a
pure set comparator producing auditable lists. Twelve D-series defects fixed: D6 (duplicate JSON
keys, fatal via `object_pairs_hook`), D7 (resolved by the D9 redesign), D8 (NFKC/whitespace/
backslash normalisation), D5 (validator widened to class/module-level assignment targets, hard
gate downgraded to advisory with nearest-match suggestions), D4 (abstention gets its own
`kind_abstained` list, never folded into mismatches), D9 (two-judge format replaced with two
separate ordinary actuals files, reconciled by the tool, with a new `location_set_disagreements`
bucket), D10 (empty-after-normalisation location rejected), D11 (safe file reads, symlink dedup),
D12 (best-effort stdlib-only gitignore support, explicitly NO subprocess -- preserves the
blindness guarantee an audit hook verified). D3/D2 documented in KNOWN_LIMITATIONS per explicit
instruction, no code needed.

Test suites rewritten: 42 tests in `test_touch_set_score.py` (includes a structural guard against
ever reintroducing a "rate" field), 47 in `test_touch_set_inventory.py`. Full project suite: 2586
tests, clean. Report updated with an honest account of the retraction. Same four files throughout
-- no fifth module.

## UPDATE: second course correction addressed (same session)

Three changes requested and implemented, all within the original four files: (1) surprise/miss are now primary COUNT+LIST, rates demoted to a secondary tier with per-rate warnings, kind_mismatch_rate stays primary since its denominator does not scale with factoring granularity; (2) new `--validate-predictions` mode on `touch_set_inventory.py` checks a predictions file against a tree's FULL location set (any nesting/visibility) at authoring time, keeping `touch_set_score.py` completely tree-agnostic; (3) actuals now support two independent judges (`kind_1`/`kind_2`), with disagreement counted/listed explicitly and excluded from `kind_mismatches`, never silently reconciled.

New tests: 12 added to `test_touch_set_inventory.py` (27 total), 8 added to `test_touch_set_score.py` (36 total). Full suite: 2547 tests, clean. Also fixed two pre-existing local imports found during this pass (moved to module level, per project convention) -- present since the tool's first version, not introduced by either course correction.

Naive-vs-real hazard demonstration re-verified against the final tool: same 6/7 result holds.

Full detail in the report update section at `toolguard/too-45/reports/touch-set-harness-report`.

---

# LATEST SESSION (2026-08-06): TOO-45 M2 expected-touch-set harness

(Everything below this line down to the next `---` is this session's report; older content
below belongs to a previous task and is retained only for history.)

## Summary

Built `tools/touch_set_inventory.py` (blind-predictor structural inventory, one tree only, never
a diff) and `tools/touch_set_score.py` (scorer for the M2 "expected touch set" measure). Mid-task,
the coordinator withdrew the original directive to derive ACTUAL kinds mechanically from
`tools/change_role_classifier.py` after an adversarial review found its role labels
anti-correlated with code quality. Redesigned `touch_set_score.py` into a pure comparator between
two hand/judge-authored files (predictions + actuals, symmetric shape), with zero dependency on
any tree, diff, subprocess, or AST classifier. Also dropped `touch_set_inventory.py`'s incidental
reuse of two helpers from the classifier module, reimplementing them locally.

## Files created

- `tools/touch_set_inventory.py`
- `tools/touch_set_score.py`
- `test/unit/test_touch_set_inventory.py` (15 tests)
- `test/unit/test_touch_set_score.py` (28 tests, doubles as the committed hazard suite)

No existing files modified.

## Key decisions

See the full report at basic-memory `toolguard/too-45/reports/touch-set-harness-report` (also
`toolguard-memories/TOO-45/reports/touch-set-harness-report.md` in-repo) for: predictions/actuals
file format, every location-matching decision and its rationale, the 7-scenario hazard suite
(6/7 fail-then-pass against a deliberately naive, never-committed comparator; the 7th, "H4 plain",
is a documented case where naive coincidentally succeeds), and the three-part adversarial exposure
review the coordinator requested (sed-vulnerability, silent-loss, factoring-scale-sensitivity).

## Deviations from the original plan

The single largest deviation is the mid-task redesign described above -- not something I chose,
but a course correction from the coordinator that I implemented in full, including rewriting both
tools' dependency surface and both test suites. The original spec's "predicted location does not
exist in the tree at all" hazard case genuinely lost its distinguishing capability in the
redesign (no tree access remains to check existence against) -- collapsed into an honest
`ordinary_misses` bucket with the loss stated as KNOWN LIMITATION #1 in the tool's own output,
not silently absorbed.

## Known limitations / follow-up

Documented exhaustively in the tool's own `KNOWN_LIMITATIONS` output and the full report. The one
NOT mitigated: location granularity (file + function/class) still scales with how finely a tree
factors its logic, which can shift miss/surprise-rate denominators between two trees for reasons
unrelated to prediction quality. This is a documentation-level ask (grain `actuals.json`
consistently across trees), not something the tool can enforce.

## Self-review results

`uv run ruff format` / `uv run ruff check` clean on all four files. No async/threading/local
imports. `git status` confirms only the four intended files were created. All 43 new tests pass
reliably in isolation, run repeatedly. The full project suite showed transient failures during
this session traced to a DIFFERENT, concurrently-active agent modifying
`tools/change_role_classifier.py` (untracked, very recent mtime) in the same working tree --
confirmed via repeated isolated/held-out reruns, not a regression from this work. One disclosed
process anti-pattern: a single early sanity-check command used an undisclosed `python -c` pipe
before I re-grounded in the project's intent-disclosure convention; every subsequent script
execution used the proper disclosure block.

## Time/cost estimate

~50 minutes elapsed end to end (see the full report's "Time and cost" section for the phase
breakdown). Estimated cost: Sonnet 5, moderate session with a full mid-task redesign; rough order
of magnitude USD 3-6, not precisely measured.
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