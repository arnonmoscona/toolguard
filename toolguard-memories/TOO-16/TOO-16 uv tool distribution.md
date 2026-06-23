---
title: TOO-16 uv tool distribution
type: note
permalink: toolguard/too-16/too-16-uv-tool-distribution
tags:
- task-memory
- TOO-16
---

# TOO-16 uv tool distribution

## Ticket
Let uv users run toolguard without adding it as a (dev) dependency: install it as a
`uv tool` and point the Claude Code hook at the installed entry point. Ticket checklist
(5 steps): (1) `[project.scripts]` entry in pyproject; (2) doc how to install as uv tool +
validate it works (`echo ls | ~/.local/bin/toolguard`); (3) change hook example from
`run_hook.sh` to `~/.local/bin/toolguard`; (4) note for non-uv users (source + venv + bare
python); (5) delete `run_hook.sh`. Note: needs the pyproject entry pushed before it can be
fully tested.

Read via `~/projects/youtrack_api/get-issue.sh "TOO-16"` (no comments on the ticket).

## State as of 2026-06-23 (this session)

Most of the doc work was pulled forward into TOO-8 Phase 7. Mapped to reality:
- Step 1 (pyproject `[project.scripts]`): DONE + committed + pushed. Entries:
  `toolguard = "toolguard.hook:main"`, `toolguard-session-start = "toolguard.session_start:main"`.
- Step 3 (hook example uses `~/.local/bin/toolguard`): DONE across quickstart/configuration/
  agent-guides/takeover-mode.
- Step 4 (non-uv editable note): DONE (quickstart "editable install" alternative).
- Step 2 (validate command): WAS MISSING; the ticket's literal `echo ls | toolguard` is WRONG
  for the current hook (see spot test). FIXED this session.
- Step 5 (delete run_hook.sh): DONE this session.

### Spot test (real `uv tool install`, 2026-06-23) -- VERIFIED
`uv tool install git+https://github.com/arnonmoscona/toolguard` (repo is PUBLIC, anon https
clone works; default-branch HEAD only -- pushed commits, not local-only). Installed
`toolguard==0.2.0`, two executables. Confirmed:
- bin dir = `~/.local/bin` (matches docs); symlinks into `~/.local/share/uv/tools/toolguard/bin/`.
- Hook reads a JSON PreToolUse event on STDIN; decision JSON -> STDOUT; warnings -> STDERR.
- `ls -la` event -> allow; `rm -rf /` event -> deny (compound detection + rule provenance work).
- The ticket's `echo ls | toolguard` -> deny with "Failed to parse hook input: Invalid JSON"
  (fail-closed, safe, but MISLEADING as a smoke test). Correct validation command:
  `printf '{"tool_name":"Bash","tool_input":{"command":"ls -la"},"hook_event_name":"PreToolUse"}' | ~/.local/bin/toolguard`
  -> a JSON `permissionDecision`.
- Observation (not a TOO-16 issue): `CLAUDE_SETTINGS_PATH` is set in Arnon's env pointing at
  `flowers/featherhill/.claude`, so the smoke test used that config (explains featherhill
  warnings even from /tmp).

### Changes made this session (UNCOMMITTED; Arnon does git)
- `docs/quickstart.md`: added "Verify the install" block with the correct JSON-payload command
  + an explicit warning that bare `echo ls | toolguard` is not a valid test.
- `docs/agent-guides.md`: added the same verify command to the install step of the setup recipe.
- `docs/architecture.md`: removed the `run_hook.sh` legacy line from the package-structure
  listing; replaced with a pyproject entry-points comment.
- Deleted `run_hook.sh` (filesystem rm; git shows `D run_hook.sh`, unstaged). Zero references
  remain anywhere outside memories.

## Remaining / open
- Arnon to stage+commit: the doc edits + `run_hook.sh` deletion (his git domain).
- Future (NOT now, Arnon's call): switch the documented install from default-branch HEAD to a
  tagged release once a first release is cut. For now intentionally target HEAD, no tags.
- Consider `uv tool uninstall toolguard` if the global install was only for testing (Arnon
  installed it this session; may be intentional to keep).

## Related
[[TOO-8 Hierarchical Configuration Implementation Plan]] (Phase 7 did most TOO-16 docs).
Distribution-model decisions also in the auto-memory `project_distribution_model.md`.

## Distribution model decision (2026-06-23)

- **Now: GitHub-only, git-based install.** Stay on `git+https://github.com/arnonmoscona/toolguard`.
  Because uv cannot do version-tracking upgrades from a git source (it follows a branch HEAD or
  a pinned ref; it will not "find the latest tag and upgrade"), version-based NATIVE
  `uv tool upgrade` is NOT available while git-based. So updates remain commit-based and any
  "is there an update?" check must be custom.
- **Update tooling to build now (git-based):** a small `toolguard-update-check` entry point
  (compare installed commit from PEP-610 `direct_url.json` `vcs_info.commit_id` vs
  `git ls-remote ...HEAD`; print the upgrade command; optional `--upgrade` to self-update),
  plus a docs MENU of options (manual / throttled once-a-day alert / auto-update). Arnon's
  personal pick = AUTO-UPDATE, implemented as: cheap throttled check first, run the upgrade
  only on drift (not a blind reinstall every shell). Reliable upgrade command TBD by the
  push-test: plain `uv tool upgrade` may be cache-bound; `uv tool upgrade <name> --reinstall`
  (or `uv tool install --force git+...`) is the fallback.
- **Future (~RC1): publish to PyPI.** The dist name `toolguard` is TAKEN on PyPI (squatted after
  the project started). So publishing requires renaming the DISTRIBUTION (e.g. `claude-toolguard`);
  the import package and the `toolguard`/`toolguard-session-start` entry points stay unchanged.
  Do the rename + doc update ATOMICALLY at publish time -- NOT now (renaming now breaks the
  current global install and every `uv tool upgrade toolguard` reference for zero benefit).
  Once on an index, native `uv tool upgrade` handles versions and the custom update-checker
  becomes redundant (can be retired). => This is a separate FUTURE ticket (release process +
  PyPI publish + dist rename), distinct from TOO-16's git-install scope.
- Version bump to 0.3.0 (from 0.2.0) was a manual bump by Arnon to make the push-test's version
  change visible; it does NOT drive uv's git-based upgrade decision (cosmetic confirmation only).

## Push-test result (2026-06-23) -- upgrade command SETTLED

Empirically verified against a real version bump (pushed commit e3e2698, 0.2.0 -> 0.3.0):
- **Plain `uv tool upgrade toolguard` IS sufficient** for a git-HEAD install -- it re-resolves
  the remote ref, rebuilds when the commit moved, and updated 0.2.0 -> 0.3.0 with NO
  `--reinstall`. The earlier "Nothing to upgrade" was a genuine up-to-date result, not a cache
  false-negative. So docs lead with plain `uv tool upgrade toolguard`; `--reinstall` /
  `install --force` are fallbacks only.
- Check logic confirmed: installed commit from `direct_url.json vcs_info.commit_id` vs
  `git ls-remote ...HEAD`; flips correctly and back to up-to-date after upgrade.
- Hook still returns valid decisions post-upgrade; upgrade is idempotent.
- NOTE for the shipped entry point: read the installed commit via `importlib.metadata`
  (the package can introspect its own `direct_url.json`) rather than a filesystem glob.

## Follow-up requirements (2026-06-23, Arnon) -- update-check v2 + interactive guard

Version bumped to 0.3.1 (Arnon).

1. **update_check must support BOTH install kinds, not just git.** Current `installed_origin`
   only handles `vcs_info` (a `git+https` uv-tool install). A `uv tool install /local/path`
   and an editable `uv pip install -e .` record `dir_info` (a `file://` checkout path), no
   `vcs_info`, so the checker punts (exit 2) -- which makes the quickstart "Keeping toolguard
   up to date" section MISLEADING (it offers the local-path install). Fix: detect kind =
   git (vcs_info) / local (dir_info file:// path, or discovered by walking up from the module's
   own `__file__` to a `.git`) / unknown (punt, exit 2). For local: compare the checkout's
   `git rev-parse HEAD` vs `git ls-remote origin HEAD`; remediation is manual (`git pull`, plus
   `uv tool install --force <repo>` / `uv tool upgrade <dist> --reinstall` for a non-editable
   local install; editable picks up source live). `--upgrade` must NOT auto-mutate a working
   tree -- print manual steps for local installs; only auto-run `uv tool upgrade` for the git kind.
2. **Interactive-run guard on the hooks.** `toolguard` (hook.main) and `toolguard-session-start`
   (session_start.main) should detect `sys.stdin.isatty()` and, instead of blocking on stdin,
   print a short explanation that they are Claude Code hooks meant to be invoked by Claude with
   a JSON event on stdin -- then exit. Safe: Claude always pipes JSON (not a TTY), so the hook
   path is unaffected.
3. Update the quickstart "Keeping toolguard up to date" section to be accurate for both kinds.

4. **`--help` on all three console scripts.** `toolguard-update-check` already has argparse
   (free `--help`). Add `--help`/`-h` to `toolguard` (hook.main) and `toolguard-session-start`
   (session_start.main) -- describe that they are Claude Code hooks. Adding argparse to the
   hooks must not break normal invocation (Claude calls them with NO args + piped JSON).
