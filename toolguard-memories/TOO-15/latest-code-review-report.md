---
title: latest-code-review-report
type: report
permalink: toolguard/too-15/latest-code-review-report
tags:
- TOO-15
- code-review
---

# Code Review Report -- TOO-15 (no-match / no-rules permission semantics)

Date: 2026-07-08

## Scope

`changed` scope, resolved via `git diff HEAD --name-only` at review time:

- `toolguard/config.py`, `toolguard/hook.py`, `toolguard/resolve.py` (production)
- `test/unit/test_configuration.py`, `test/unit/test_hook.py`, `test/unit/test_resolve.py`,
  `test/unit/test_tools_self_permission.py` (tests)
- `AGENTS.md`, `README.md`, `docs/install.md`, `docs/uninstall.md` (docs -- unrelated to the
  no-match semantics change; a separate install/uninstall-runbook hardening pass)
- `toolguard-memories/implementation/Coder Latest Task Recall.md` (subagent notes, out of
  scope for code review)

Excluded (present in repo working tree as of the last conversation snapshot but already
committed by the time of this review, per fresh `git status`): the `skills/toolguard-maintenance/*`
pass files and `toolguard/tools/maintenance.py` / `test/unit/test_tools_maintenance.py`.

Four `toolguard-memories/TOO-15/*.md` files show as `AD` (added in index, deleted in working
tree) -- net no content change for review purposes, but flagged below as an observation.

## Summary

This is a well-scoped, well-tested semantics change: an entirely unconfigured governed tool
now resolves to `ask` instead of a fail-closed `deny` (fixing the "fresh install bricked"
bug), and `no_match_fallback = warn_deny` now actually allows with a warning instead of
merely rewording a deny (fixing a real functional bug where the reword never changed the
decision). The implementation correctly centralizes both cases in
`Configuration.resolve_permission_detailed`, removing duplicated early-exit logic from
`hook.py` so `hook.py` and `toolguard.tools.decision.decide()` cannot drift apart -- confirmed
by dedicated anti-drift tests. All 1308 unit tests pass, `ruff check` is clean, and the two
new methods (`has_any_rules`, `resolved_no_match_fallback`) are low-complexity (pyscn:
complexity 6 and 5, "low" risk). No critical or security issues found.

## Findings

### Critical
None.

### Major
None. (`main()` in `hook.py` remains at pyscn cognitive-complexity 55 / "high risk" -- but
this is pre-existing debt this change actually shrinks slightly (net -20 lines), not a
regression introduced here. Worth a mention at the next pre-push `pyscn` review per
CLAUDE.md's checklist, not a blocker for this change.)

### Minor

1. **`toolguard/hook.py:400-401`** -- `_resolve_event`'s docstring is now stale. It says:
   "No logging, divergence checks, auto-migration, or takeover reason-rewriting happen here
   (the takeover `no_match_fallback` rewrite is cosmetic -- it changes a deny *reason* string
   but never the decision)." That rewrite block was *removed from `main()` entirely* by this
   change (it was the exact bug being fixed), so the comparison this docstring draws no longer
   exists on either side. Update the docstring to stop referencing removed behavior.

2. **`toolguard/log_writer.py:33-34`** -- `log_command`'s docstring says `status` is "Either
   'executed' or 'refused'", but `hook.py`'s new `elif decision == "ask":` branches (both the
   file-path and Bash blocks) now pass `status="ask"`. Functionally harmless (status is an
   unconstrained string used only for display), but the docstring should be updated to list
   `'ask'` too.

3. **`toolguard/hook.py`** (both new `ask` branches, e.g. line ~674-681 and ~743-750) --
   `log_command(..., "ask", [reason], ...)` passes the ask reason through the `violated_rules`
   parameter. In the markdown log this renders as `**Violated Rules**: <reason>` for an
   outcome that was never a rule violation -- just a "needs confirmation" verdict. Cosmetic,
   but a reader of `logs/toolguard-*.md` could reasonably be confused. Consider a distinct
   field/label for the `ask` case in a follow-up (not blocking; `log_command`'s signature has
   no better field today).

4. **`docs/install.md` Phase 0.1** -- "Journal creating it (reverse: the user may delete it
   manually; uninstall does not)." reads as a sentence fragment / doesn't parse cleanly.
   Minor wording cleanup.

5. Four `toolguard-memories/TOO-15/*.md` files (design doc, implementation plan, P2 dry-run
   notes, a parking-lot idea) are staged for add but deleted in the working tree (`AD` in git
   status). Not a code issue, but worth confirming this is an intentional cleanup/consolidation
   before it is committed, since `git status` currently shows them as a pending deletion of
   previously-staged content.

### Suggestions

- `Configuration.resolved_no_match_fallback()` accepts and returns whatever string a layer
  sets for `no_match_fallback` without validating it against `{'deny', 'warn_deny'}` (this was
  already true of the legacy `takeover_mode().no_match_fallback` path, so not a regression).
  A typo'd value (e.g. `"warndeny"`) silently falls through to the same behavior as `'deny'`
  with no warning. Consider adding a `validation_issues()` check for unrecognized
  `no_match_fallback` values while touching this area again in the future.
- The doc changes in `AGENTS.md`/`README.md`/`docs/install.md`/`docs/uninstall.md` (guided
  install/uninstall runbook hardening: sandbox-preflight detection, phased takeover
  enablement starting at `warn_deny`, keeping `~/.toolguard/` on uninstall) are unrelated to
  the no-match semantics change but are internally consistent with it and with each other;
  no issues found on read-through. They were not run through any automated check (they are
  prose/runbook, not code).

## Verification performed

- Read full diffs of all changed production and test files.
- Ran `uv run python -m unittest discover -s test -t .`: **1308 tests, OK**.
- Ran `uv run ruff check` on all changed Python files: **all checks passed**.
- Ran `uvx pyscn analyze --json --skip-deps` on the three changed production files: overall
  health C/62, but the two new methods score low-complexity; the one high-risk function
  touched (`hook.main`) had complexity reduced, not increased, by this diff. The duplication
  finding pyscn reports (`_parse_config_file` family) is pre-existing and unrelated to this
  diff.
- Cross-checked `toolguard/tools/decision.py` against the implementation report's claim that
  it needed zero changes: confirmed via `git diff` (no changes to that file).

## Review metadata

- Files reviewed (code): 3 production + 4 test files, fully read/diffed.
- Files reviewed (docs/notes): 4 doc files diffed, 1 memory file diff-stat only (out of scope).
- Issues found: 0 critical, 0 major (new), 5 minor, 2 suggestions.
