---
title: TOO-15 Coder Task Recall - discover-projects, install-skills, seed-hard-deny
  (RED phase)
type: note
permalink: toolguard/implementation/too-15-coder-task-recall-discover-projects-install-skills-seed-hard-deny-red-phase
tags:
- TOO-15
- task-memory
- coder-task-recall
---

## Ticket
TOO-15 (toolguard project). Continuing install-runbook noise reduction. Follow RED-then-checkpoint:
write tests FIRST, confirm ONLY new tests fail (baseline suite unaffected), STOP, report red state,
wait for explicit approval before writing production code.

## Background
`toolguard-install` (toolguard/tools/installer.py) is an agent-facing console script with
subcommands doing mechanical install steps in ONE Bash call each (init-state, write-config,
register-hooks, seed-self-perms, enable-takeover, journal), because file I/O happens inside the
process and never hits Claude Code's own permission layer -- only the initiating
`Bash(toolguard-install ...)` call does (pre-approved once in docs/install.md Phase 3).

A real install test found three more flows still agent-driven (multiple separate prompts) instead
of encapsulated. docs/install.md Phase 4 step 3, Phase 5, Phase 7.1, and Phase 10.1 were already
rewritten to reference the new subcommands by name -- authoritative behavioral spec.

## Three new subcommands to add (production phase, NOT yet)

### 1. discover-projects (Phase 7.1) -- READ-ONLY, no backup/journal
`toolguard-install discover-projects [--format text|json]`
- Primary source: `~/.claude.json` top-level `projects` dict keys (absolute paths).
- Supplement: `~/.claude/projects/<encoded>` dirs (leading `/` and every `/` -> `-`); decode is
  LOSSY -- only accept if decoded path exists as a directory on disk.
- Filter to: directory still exists AND has `.claude/settings.local.json` that parses and has
  >=1 non-empty permission list (allow/deny/ask).
- Annotate: has toolguard config (toolguard_hook.toml/json) + whether `[takeover_mode]
  enabled = true` there. Reuse `toolguard.config.load_config_file(path, file_format)` to parse
  (public helper) rather than hand-rolling TOML/JSON parsing. `_discover_in_dir`/
  `discover_config_files` in config.py are close but operate on the CURRENT project's `.claude`
  precedence chain -- not directly reusable for arbitrary candidate project dirs; check for a
  toolguard_hook.toml then .json directly instead.
- Output both `--format text` (default) and `--format json`; sort by path; zero-candidates ->
  plain message, not empty table.

### 2. install-skills (Phase 5) -- mutating, backs up + journals
`toolguard-install install-skills --scope <user|project> [--project-dir <path>] --source <repo-url-or-local-path> [--force]`
- Local path source -> `shutil.copytree` of `skills/toolguard-security-audit` and
  `skills/toolguard-maintenance` from `<source>/skills/...`.
- Git URL source -> `subprocess.run(["git", "clone", "--depth", "1", source, tmp_dir], ...)` into
  a `tempfile.TemporaryDirectory`; raise `InstallerError` with captured stderr on nonzero.
  No new PyPI dependency -- subprocess call to `git` on PATH only.
- Idempotent: existing target dir -> "already installed, unchanged", untouched, UNLESS --force
  (then back up whole dir tree into `~/.toolguard/backups/<skill-name>-<timestamp>/`, mirroring
  `create_backup`'s `%Y-%m-%d-%H%M%S` format + same-second collision `-2`, `-3`, ... suffix,
  implemented locally since `create_backup` only handles single files).
- Journal: one entry PER skill actually installed/changed, reverse = "remove <target>" or
  "restore backup at <path> over <target>".

### 3. seed-hard-deny (Phase 10.1) -- mutating, backs up + journals
`toolguard-install seed-hard-deny --scope <user|project> [--project-dir <path>]`
- Architecturally identical to `cmd_seed_self_perms` (ensure_state, require write-config done,
  tomllib.loads raw TOML for true `[hard_deny]` section, added-vs-already-present split,
  idempotent no-op, create_backup + write + journal otherwise).
- New module `toolguard/tools/recommended_protections.py` mirrors `self_permission.py`'s pattern
  (frozen dataclass + tuple + accessor fn) with EXACTLY this canonical list (verbatim from
  docs/security.md "Recommended deny patterns" -> "Sensitive files", confirmed matching):
  ```
  Read(**/.env)
  Read(**/.env.*)
  Read(**/.aws/**)
  Read(**/.ssh/**)
  Write(**/.env)
  Write(**/.aws/**)
  Write(**/.ssh/**)
  Edit(**/.env)
  ```
  Each entry carries a short rationale string.
- DESIGN NOTE (flagged per task instructions): `write_toml_config` / `reassemble_permissions_section`
  in rule_sort.py are hardcoded to section name `[permissions]` and keys allow/deny/ask -- NOT
  directly reusable for `[hard_deny]` (only deny/allow keys, different section name). Confirmed by
  reading rule_sort.py in full. Plan: mirror the EXISTING precedent already in installer.py for
  exactly this situation -- `cmd_enable_takeover` already handles a write_toml_config-unsupported
  section (`[takeover_mode]`) via a sibling render function (`_render_takeover_section`) + the
  already-generic `_replace_or_append_toml_section` (built on `find_section_boundaries`, itself
  generic on section_name). Same approach for hard_deny: read existing `[hard_deny]` via
  tomllib to merge deny list (preserving pre-existing allow carve-outs / unrelated deny entries),
  render fresh section text, replace-or-append via the existing generic helper. No new TOML engine,
  reuses `find_section_boundaries`. This is NOT the "materially different design" escape hatch --
  it's already anticipated as option B ("a sibling helper") in the task description.

## Also: README template addition
Add one `traces/` bullet line to `_README_TEMPLATE` in installer.py, same style as the recent
`errors/` bullet. Session-trace dumps (Phase T.1), created on demand by the AGENT directly (not by
any subcommand). Pure doc-text change, not a new subcommand, no test needed beyond maybe asserting
the existing init-state help/README tests aren't broken (they already assert substrings, should be
compatible since we're only adding an additional bullet).

## Tests to write (RED phase) -- exact plan
Mirror test/unit/test_tools_installer.py's `InstallerTestCase` fixtures (fake HOME via
`patch("pathlib.Path.home", ...)`, `run_cli`, `run_help`, `journal_indices`). For install-skills
git-URL path, mock `subprocess.run` via `patch.object(installer.subprocess, "run", ...)` mirroring
the pattern already used in test/unit/test_update_check.py (`patch.object(update_check.subprocess,
"run", ...)`).

New test classes in test/unit/test_tools_installer.py:
- TestDiscoverProjects: dedupe across both sources; lossy-decode only-if-exists inclusion;
  nonexistent dir excluded; empty/missing settings.local.json excluded; takeover-enabled flagged;
  zero-candidates plain message; --format json valid + expected fields; sorted by path.
- TestInstallSkills: local source copies both dirs + journals two entries; rerun without --force
  is no-op (no touch, no new journal entry); --force backs up old content first then replaces,
  journals; bad/network-failing git source (mocked subprocess) raises InstallerError.
- TestSeedHardDeny: full canonical list added in one call; idempotent rerun is exact no-op
  (mirrors cmd_seed_self_perms no-op shape); pre-existing hard_deny content (allow carve-out /
  unrelated deny) preserved; missing write-config precondition raises InstallerError.
- Extend TestSubcommandHelp / TestTopLevelHelp coverage for the 3 new subcommands' --help text
  (files/preconditions/refusals named), and top-level --help now lists 9 subcommands.

New file test/unit/test_recommended_protections.py (mirrors test_tools_self_permission.py shape):
proves the returned tuple has exactly the 8 canonical patterns, no more/no less, each with a
non-empty rationale.

## Workflow reminders
- Every new test function needs Given/When/Then BDD docstring (project CLAUDE.md hard requirement).
- Full suite: `uv run python -m unittest discover -s test -t .` -- confirm baseline (1405 passing)
  unaffected except new tests (which must fail for import/attribute reasons, not typos).
- Do NOT run `ruff format` on this project (corrupts `except (A, B):` tuples) -- `uv run ruff
  check .` only.
- Use `uv run python ...` always, never bare python.
- STOP after RED phase confirmation -- do not write toolguard/tools/installer.py changes,
  toolguard/tools/recommended_protections.py, or the README template change yet.
- Report file: /tmp/claude-1000/-home-arnon-projects-toolguard/f73a95d0-ceb7-4bb2-b0b7-f07da7d88163/scratchpad/feature-coder-helper-subcommands-report.md

## Policy note flagged to Arnon (self-review before proceeding)
My own feature-coder system prompt normally prohibits touching the project's main test
directory ("no changes there will ever be accepted... write your own tests under coder-test/**
instead"). This task explicitly and repeatedly instructs writing directly into
test/unit/test_tools_installer.py and a new test/unit/test_recommended_protections.py, per this
project's documented RED-then-checkpoint convention. Git status/log show this exact pattern
already used and committed multiple times for this same ticket (test_tools_installer.py already
modified, test_error_log.py already added, prior commits "TOO-15 improving the install process
further" / "... attempt #4/#5"), confirming this is Arnon's established, sanctioned convention for
this specific project -- not a generic override. Proceeding on that basis, but calling it out
explicitly in the handoff report rather than silently overriding my default restriction.
