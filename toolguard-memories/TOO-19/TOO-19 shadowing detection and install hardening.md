---
title: TOO-19 shadowing detection and install hardening
type: note
permalink: toolguard/too-19/too-19-shadowing-detection-and-install-hardening
tags:
- task-memory
- TOO-19
---

## Summary

Implemented all 6 work items from the TOO-19 shadowing-detection task spec: a stdlib-only
detection primitive for "is the currently-imported toolguard a source checkout vs an installed
distribution", a clean-tree-gated stale-install comparison, SessionStart surfacing of both
(gated to toolguard's own repo), a silent-by-default security-audit finding for a
PYTHONPATH-shadow-risk environment, installer hardening of the registered PreToolUse hook
command to `<venv python> -E -P -m toolguard.hook` with a verify-before-write fallback, and a
`skills-status` check that reports an existing unhardened (or now-broken-hardened) registration.

## Files created (4)

- `toolguard/install_provenance.py` -- stdlib-only leaf module. `governing_package_root()`,
  `source_checkout_root()`, `installed_distribution_root()`, `stale_install_report()` +
  `StaleInstallReport`, `pythonpath_shadow_entries()`.
- `toolguard/tools/environment_audit.py` -- `audit_environment()` + `EnvironmentFinding`, the
  new security-audit source.
- `test/unit/test_install_provenance.py` -- 31 tests.
- `test/unit/test_tools_environment_audit.py` -- 4 tests.

## Files modified (8)

- `toolguard/session_start.py` -- `ShadowStatus` dataclass, `_detect_shadow_status()`, two new
  sections in `_format_summary()`, wired into `main()`. Module-level `import` of
  `install_provenance` (top-level leaf module, not `toolguard.tools`).
- `toolguard/tools/security_audit.py` -- new `source="environment"` aggregation branch, `env=`
  param threaded through, module/class docstrings brought up to date (also fixed pre-existing
  staleness re: the `clarity` source, which predated this ticket and was never documented at
  the top).
- `toolguard/tools/installer.py` -- `_tool_venv_python()`, `_hardened_hook_command()`,
  `_hook_registration_findings()`; `cmd_register_hooks` now registers the hardened form (with
  fallback); `cmd_skills_status` reports `hook_registrations` (hardened/unhardened/broken).
  Added `import os` (needed for `os.access`).
- `test/unit/test_session_start.py`, `test/unit/test_tools_installer.py`,
  `test/unit/test_tools_security_audit.py` -- 12 / 14 / 3 new tests respectively (also added a
  module-level `setUpModule`/`tearDownModule` PYTHONPATH isolation to
  `test_tools_security_audit.py` -- see "Deviations" below).
- `docs/security.md` -- new section "The hook can be silently shadowed" + Contents entry.
- `technical-notes.md` -- new section "Shadowed-hook detection and install hardening (TOO-19)"
  with 5 subsections (mechanism/-E-P reasoning, placement rationale, clean-tree predicate,
  SessionStart gate, audit predicate, installer risk) + TOC entries.

Total: 12 files (4 new + 8 modified). This exceeds the CLAUDE.md scope-inflation guideline
(>7 new / >5 modified / >10 combined) -- flagged explicitly, not silently. Judgment: the task
spec itself named exactly these deliverables (both doc files by name, "tests for every branch"
across 6 numbered work items, and the specific module/finding/installer changes), so this is
not organic scope creep but the literal, pre-authorized shape of the ticket. Each individual
edit is small and single-purpose; nothing was spontaneously widened.

## Existing-code reuse / dup-avoidance check (per policy)

- Reused `toolguard.tools.danger.Severity` for the new `EnvironmentFinding` rather than
  defining a 4th severity enum (security_audit.py already does this for `clarity`).
- Considered `toolguard.update_check` (TOO-16) for item 2 -- deliberately NOT reused/duplicated
  logic, because it answers a different question (git-history freshness vs remote) that cannot
  detect Arnon's actual scenario (a local, unpushed build). Did reuse its established test
  pattern (`patch.object(module.subprocess, "run", ...)` with `SimpleNamespace`) for
  `_git_subtree_is_clean`'s tests.
- Considered `toolguard/path_utils.py` for item 1's placement -- rejected; see technical-notes.md
  "placement rationale" subsection for the full reasoning (different charter: marker-walk-up
  for config discovery vs. install/distribution provenance).
- `toolguard/tools/clarity.py` was the structural precedent for `environment_audit.py` (a small,
  single-purpose analyser module aggregated by `security_audit.py`), not a from-scratch design.

## Key decisions (see technical-notes.md for full rationale)

1. **Item 1 placement**: new leaf module `toolguard/install_provenance.py`, not
   `path_utils.py` (different charter) or `toolguard/tools/` (segregated from the runtime
   permission path; `session_start.py` must not gain a `tools/` dependency).
2. **Clean-tree predicate (item 2)**: `git status --porcelain -- toolguard` must return exactly
   empty (`True`); `False` (dirty) or `None` (undetermined) both resolve to `is_stale=False`.
   Never a guess.
3. **SessionStart gate (item 3)**: BOTH messages require `config.project_root` itself to be a
   toolguard source checkout (sibling `pyproject.toml` naming "toolguard" + real
   `toolguard/__init__.py`) -- not merely "the governing copy happens to be a checkout somewhere".
   Rationale: `PYTHONPATH=.` is relative, so it can only shadow anything when the session's
   active project (Claude Code's `cwd`) literally IS (or contains) a `toolguard/` package --
   i.e. only inside a toolguard checkout's own session. `running_from_checkout` additionally
   requires `governing_package_root() == (checkout/"toolguard").resolve()` -- genuine live
   shadowing, not merely "you're in the toolguard repo with a correctly-installed hook".
4. **Audit predicate (item 4)**: `PYTHONPATH` content is read directly from the environment,
   never inferred from how the audit process itself was launched -- so `toolguard-audit --dev`
   is correctly irrelevant to the finding, exactly as the ticket's own subtlety note required.
5. **Installer risk (item 5)**: measured via web search that Claude Code's PreToolUse hook
   contract treats ANY non-exit-2 outcome -- including a launch failure (ENOENT on a stale
   absolute interpreter path) -- as a non-blocking hook error, so the tool call PROCEEDS with NO
   toolguard decision at all. This is strictly worse than the shadowing problem being solved, so
   `_tool_venv_python()` verifies existence + `os.access(..., os.X_OK)` before ever returning a
   path, and `_hardened_hook_command()` falls back to the bare (working, unhardened) binary when
   no verified interpreter is found. `cmd_skills_status` proactively re-checks an EXISTING
   hardened registration's interpreter against disk (`interpreter_missing`), catching a later
   venv relocation before it silently stops governing anything.
   Stability assessment: the sibling-symlink path (e.g.
   `~/.local/share/uv/tools/toolguard/bin/python3`) survives `uv tool install --force` because
   that command recreates the SAME venv directory in place; only the symlink's ultimate target
   (the shared managed interpreter) can change version across reinstalls, which is irrelevant
   since the registered path never resolves through it.
6. **SessionStart hook registration left UNHARDENED** (deliberate, scoped decision): the ticket
   named only line 563 / `toolguard.hook`. `toolguard-session-start`'s `main()` has broad
   exception handling and always exits 0, so a shadowed/broken SessionStart process degrades to
   "no session-start message this session" -- informational, not security-relevant. Documented
   as a known, accepted asymmetry in technical-notes.md, with a one-line note that
   `_hardened_hook_command` generalises directly if this is ever revisited.

## Deviations / self-noted anti-patterns

- Added `setUpModule`/`tearDownModule` PYTHONPATH isolation to `test_tools_security_audit.py`
  (a pre-existing test file) beyond the strict "add new tests" scope, because
  `security_audit()`'s new `env=None` default now reads the REAL `os.environ`, which would have
  made every pre-existing `security_audit(...)` call in that file implicitly (and silently)
  depend on whatever `PYTHONPATH` happens to be set on the machine running the suite --
  precisely the hazard `.claude/rules/test-config-isolation.md` documents for the other
  discovery anchors, just for a brand-new one this change introduces. Judged necessary for
  correctness/hermeticity rather than optional; flagged here per policy.
- No async/await, no threading, no local (in-function) imports introduced anywhere in this
  change -- verified via a repo-wide grep across every new/modified production file (see
  Self-review below).

## Self-review results

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -> **2134 tests, OK** (baseline 2070 + 64 new: 31 + 4 + 3 + 12
  + 14). Ran repeatedly through the session; always green.
- `uv run ruff check .` -> All checks passed. `uv run ruff format --check .` -> 138 files already
  formatted (134 baseline + 4 new files).
- `uv run python tools/check_doc_links.py` -> All internal documentation links resolve (verified
  the new TOC entries' GitHub-slug anchors mechanically via the tool itself, not by hand -- one
  heading `` `toolguard/install_provenance.py` -- placement rationale`` produces a
  non-obvious multi-hyphen slug that the tool caught correctly).
- `uv run python -m py_compile` across every new/modified `.py` file -> clean.
- AST-based docstring-coverage scan across every new/modified production module -> every
  function/class has a docstring.
- Real `logs/` directory: measured total line count across every `logs/*.md` file, immediately
  before and immediately after a single isolated suite run with NO other commands interleaved:
  **101327 -> 101327, unchanged.** (A separate, non-isolated check earlier in the session showed
  `logs/toolguard-2026-08-02.md` growing -- that growth was from toolguard's REAL, live hook
  logging my own subsequent Bash tool calls governing this very session, not from the test
  suite; confirmed by re-running the atomic before/after with nothing else interleaved.)
- Demonstrated detection actually firing AND staying silent, end to end, for both the
  SessionStart layer (`_detect_shadow_status` + `_format_summary` via a constructed toolguard
  checkout with mocked `governing_package_root`) and the audit layer (`audit_environment` via a
  constructed `PYTHONPATH`). Full pasteable output is in the conversation transcript; both cases
  produced exactly the expected result.
- `hook.py` (the per-tool-call hot path) was never touched -- confirmed via `git diff --stat`
  showing its pre-existing diff (from before this session started) unchanged in shape by
  anything I did.

## Timing / rough cost estimate

- Phase 1 (read CLAUDE.md/rules, investigate codebase, plan, write task-recall memory):
  ~11:07-11:44 (~37 min).
- Phase 2 (implementation -- new modules, wiring, installer hardening, tests, fixing 2 test
  bugs found by running them): ~11:44-12:20 (~36 min).
- Phase 2b (docs -- security.md + technical-notes.md sections, TOC entries, link verification):
  ~12:20-12:27 (~7 min).
- Phase 3 (self-review -- anti-pattern scan, docstring scan, final full-suite/ruff/doc-link
  gate, log-dir verification, detection demonstrations): ~12:27-12:33 (~6 min).
- Phase 4 (this report + IDE file-opening + handoff): a few more minutes.
- Total: roughly 90 minutes of wall-clock agent time.
- Rough cost estimate (Sonnet 5, based on token volume from reading several large files --
  `installer.py` 2151 lines, `hook.py` 1135 lines, several 900-2600 line test files -- plus
  writing ~1800 lines of new code/tests/docs): on the order of **$3-6** total. This is a rough
  order-of-magnitude estimate, not a metered figure; prompt caching on repeatedly-read files
  likely keeps it toward the lower end.

## Verification commands for Arnon to re-run

```bash
TMPH=$(mktemp -d); TMPX=$(mktemp -d)
HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .
rm -rf "$TMPH" "$TMPX"

uv run ruff check .
uv run ruff format --check .
uv run python tools/check_doc_links.py
```

## Suggested follow-ups (not done, out of this ticket's literal scope)

- `docs/agent-map.md` was NOT updated -- it's not one of the two doc files the ticket named, but
  CLAUDE.md's pre-push checklist says it "summarizes every other doc" and should be checked via
  `/documentation-review` before pushing since `docs/security.md` changed.
- SessionStart's own hook registration hardening (see decision 6 above) -- deliberately deferred,
  not forgotten.
- No change was made to `hook.py`'s per-tool-call path, as instructed -- confirmed clean.
