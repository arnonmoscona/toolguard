---
title: TOO-19 shadowing detection and install hardening - coder task recall
type: note
permalink: toolguard/too-19/too-19-shadowing-detection-and-install-hardening-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Ticket
TOO-19: close the "which toolguard is actually governing?" gap.

## Background (measured 2026-08-02)
`PYTHONPATH=.` was exported from `~/.zshrc_finalization`. Because the hook runs with cwd at
project root, the working tree SHADOWED the installed package: the tool venv's own interpreter
imported the working-tree `toolguard/__init__.py` instead of its own site-packages copy. Live
permission hook silently ran uncommitted, mid-refactor code for weeks. PYTHONPATH now removed
(fixed on this machine right now). Task: make the condition detectable and self-announcing so it
cannot silently return, here or for any other user.

Measured facts (re-verify if touched):
- Console-script invocation: PYTHONPATH alone was the cause; unsetting fixed it.
- `-m` invocation: cwd is ALSO prepended to sys.path, so `-E` alone insufficient; `-E -P` required.
  Verified: `python -E -P -m toolguard.rule_entry` fails "No module named" (installed copy
  governing) while plain `-m` resolves the working tree.
- `toolguard/hook.py` has `if __name__ == "__main__": main()` -> `-m toolguard.hook` valid.

## Work items (6)
1. Detection primitive (new, small, pure, stdlib only): is currently-imported toolguard the
   installed distribution or a source checkout? Suggested tell: pyproject.toml naming this
   project sitting beside the package root. Do NOT call on the per-tool-call hook path (hook.py
   PreToolUse) - session-level concern only.
2. Stale-install detection: installed copy's content differs from working tree. Locate installed
   dist independently of what got imported (importlib.metadata finds dist-info even when shadowed).
   Compare hash over packaged .py files. CRITICAL: only report when working tree is CLEAN (no
   uncommitted changes under toolguard/). Silent if cleanliness cannot be determined (no git/
   unavailable) - never nag on uncertainty.
3. Surface at SessionStart (toolguard/session_start.py, runs once/session, needs no dedup state -
   module-level global would NOT work, toolguard is per-tool-call process, mistake made once
   already). Two messages: (a) running from source tree - loud, name both governing + installed
   paths; (b) stale install - reminder to reinstall, name command, mention local-path install
   snapshots working tree incl uncommitted changes and affects every project on machine. ONLY in
   toolguard source repo; silent elsewhere.
4. Security-audit finding: silent in normal case (like loose-undecidable-fallback pattern). Fire
   when environment WOULD cause installed toolguard to be shadowed - e.g. PYTHONPATH contains an
   entry (such as '.') under which a toolguard/ package exists. Precise + silent for normal users.
   Note: toolguard-audit may itself run from source tree (--dev) - that's NOT the same as the
   hook being shadowed; finding must be about hook's resolution, not audit process's own.
5. Harden installer registration: toolguard/tools/installer.py:563 currently registers bare
   console-script path. Change to hardened form: `<tool-venv python> -E -P -m toolguard.hook`.
   Also: installer's status/verify path (cmd_skills_status) should report an EXISTING unhardened
   registration. Judge + report risk: hardened form bakes absolute interpreter path into settings -
   stable across `uv tool install --force`? What happens if ever wrong - fail loudly or silently
   not run (much worse)? MEASURED (web search): Claude Code hooks - only exit code 2 blocks; any
   other exit code (incl. launch failure/ENOENT) is a NON-BLOCKING hook error, and the tool call
   PROCEEDS. So a broken interpreter path = SILENT FAIL-OPEN (worse than shadowing this fixes).
   Design decision: only emit hardened form when the derived venv python sibling is verified to
   exist+executable at registration time; otherwise fall back to unhardened bare binary (working,
   not broken) with an explanation - never write an unverified absolute path.
6. Tests (every branch, esp silent-on-uncertainty paths) + docs (docs/security.md - why it
   matters, shadowed hook = unreviewed code deciding permissions; technical-notes.md - mechanism,
   -E -P reasoning, console-script vs -m difference).

## Verification required
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` - must be OK. Baseline **2070** tests.
- `uv run ruff check .` and `uv run ruff format --check .` clean repo-wide.
- `uv run python tools/check_doc_links.py` exits 0.
- Demonstrate detection actually works: construct shadowed condition in temp dir (PYTHONPATH to
  dir containing fake toolguard/ package), show detector firing; then show silent in normal case.
  Paste both.
- Real logs/ untouched: before/after entry counts around suite run.

## Report location
basic-memory project `toolguard`, path `TOO-19/TOO-19 shadowing detection and install
hardening.md`, tagged `task-memory` + `TOO-19`. Include: placement justification for item 1,
clean-tree predicate for item 2, audit predicate chosen for item 4, absolute-interpreter-path
risk assessment for item 5.

## Investigation notes (my own, coder)

### Existing related code (dup/drift check)
- `toolguard/update_check.py` (TOO-16) already has git-vs-remote-HEAD comparison for
  git/local/unknown install kinds (`detect_install()`, `InstallInfo`, `_check_git`,
  `_check_local`). This is DIFFERENT from item 2: update_check compares checkout git HEAD vs
  REMOTE origin HEAD (git history freshness). Item 2 needs: does the ACTUALLY INSTALLED
  site-packages content match the CURRENT clean working tree content right now (a snapshot
  mismatch, not a git-history question) - exactly Arnon's local-unpushed-branch scenario, which
  update_check.py cannot detect (no remote to compare against / branch not pushed). Will REUSE
  `distribution_name()`, `_read_direct_url_json()`, `_file_url_to_path()`, `_DEFAULT_DIST_NAME`
  helpers from update_check.py rather than reimplementing.
- `toolguard/path_utils.py` - stdlib-only leaf module, already hosts project-root-marker walk-up
  primitives (resolve_project_root et al). Scope is explicitly project-root discovery for
  config/migration. Considered adding item 1's detector there but decided against - different
  concern (install/distribution provenance, not path/marker walk-up), would muddy documented
  scope. Decision: NEW small leaf module `toolguard/install_provenance.py` (stdlib only) hosting
  item 1 + item 2 + the item 4 PYTHONPATH-shadow-risk predicate (shared between session_start.py
  and the new audit module).
- `toolguard/tools/__init__.py` docstring: tools/ deliberately segregated from runtime permission
  eval path. hook.py already has ONE documented, sanctioned local-import exception
  (`from toolguard.tools.decision import decide` inside `_resolve_event`, circular-import escape).
  session_start.py currently imports only `toolguard.config` at module level (no toolguard.tools
  dependency) - keep consistent: install_provenance.py must NOT import toolguard.tools, and
  session_start.py should import install_provenance (a top-level leaf module) not any
  toolguard.tools.* module directly, to keep hook.py's constraint intact by construction.
- Security audit aggregator pattern (security_audit.py): explicitly "NO detection logic of its
  own" - thin aggregator over danger.py / takeover_audit.py / clarity.py, normalizing each into
  RankedFinding (source="rule"/"takeover"/"clarity"). New finding source: create
  `toolguard/tools/environment_audit.py` (new small analyser module, same pattern as clarity.py),
  reuse `Severity` IntEnum from danger.py rather than defining a 4th severity enum. Add
  source="environment" branch to security_audit.py's aggregator.
- takeover_audit.py's `loose-undecidable-fallback`/`loose-no-match-fallback` findings are the
  precedent for "silent in normal case" - a positive boolean predicate that's false for ~100% of
  real configs.

### Installer hardening design (item 5)
- Verified on this machine: `~/.local/bin/toolguard` -> symlink -> `~/.local/share/uv/tools/
  toolguard/bin/toolguard` (real file, shebang `#!.../bin/python3`), and that bin/ dir has
  `python`, `python3`, `python3.14` siblings (python3.14 -> python -> shared uv-managed
  interpreter). `uv tool install --force` recreates this SAME target dir every time, so the
  SIBLING symlink path (not its fully-resolved target) is stable to bake into settings.json.
  `--binary` arg to `register-hooks` is REQUIRED, supplied by the calling agent (typically from
  `which toolguard` per docs/install.md), NOT a hardcoded default.
- Derivation: `Path(binary).resolve().parent` (one hop through the console-script symlink lands
  in the venv bin/ dir) + sibling `python3`/`python` (do NOT resolve further - keep the venv-local
  symlink name so it survives a --force reinstall). Verify exists() + X_OK before using;
  fall back to bare `binary` (old, unhardened, WORKING form) if not found - print why. Never
  write out an unverified absolute path.
- Web search confirmed (Claude Code hooks reference / GH issues): only exit code 2 blocks a
  PreToolUse hook; any other outcome incl. a launch failure (ENOENT on a stale absolute
  interpreter path) is a NON-BLOCKING hook error and Claude Code lets the tool call PROCEED. So a
  wrong hardened path = SILENT FAIL-OPEN, strictly worse than the shadowing problem being fixed.
  This drives the "verify before writing, fall back to working form" design above, and must be
  stated explicitly in the report's risk-assessment section.
- Scope decision: harden ONLY the PreToolUse (`toolguard.hook`) registration, per the ticket's
  literal line-563 pointer. SessionStart registration (`session_start_binary`) left as bare
  console-script - noted as a residual asymmetry in the report (low severity: session_start
  failures are informational-only, wrapped in broad exception handling, always exit 0).
- "status/verify path" = `cmd_skills_status` (no separate `verify` subcommand exists in this
  installer). Will add a check there reading both user + project settings.json/settings.local.json
  PreToolUse commands, classifying hardened vs unhardened toolguard registrations.

## Clarifications from discussion
(none yet - proceeding under auto-mode bias-to-action per system reminder; will ask if genuinely
blocked)
