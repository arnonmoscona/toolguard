---
title: TOO-15 coder task recall
type: note
permalink: toolguard/implementation/too-15-coder-task-recall
---

## Ticket
TOO-15, toolguard project, Python 3.14, stdlib unittest (NOT pytest).

## Environment
- Run tests: `uv run python -m unittest discover -s test -t .`
- This shell has CLAUDE_SETTINGS_PATH unset -- no env workaround needed
- NEVER `ruff format` (corrupts `except (A, B):` tuples on this project) -- use `uv run ruff check .` only
- `uv run python` only, never bare python
- No git commits -- leave tree dirty
- BDD Given/When/Then docstrings on every new/changed test
- No async/threading/local-imports
- Doc comments on changed functions
- Do NOT change docs/*.md (Arnon handles docs)
- Do NOT change no_match_fallback semantics (done in separate task)

## Two bugs to fix

### FIX A -- migration must only move GOVERNED tools (GitHub issue #1)
`toolguard.scripts.migrate_permissions` currently moves ALL permission patterns from
`settings.local.json` into `toolguard_hook.toml`, including tools toolguard does NOT
govern (e.g. `WebFetch(domain:...)`, `Skill(...)`). Those become inert after moving --
silent regression. `docs/config-sync.md` already says migration scans only
Bash/Read/Write/Edit.

- Root cause: `migrate_permissions.migrate` -> `get_native_permissions()` returns every
  pattern regardless of tool, and `find_divergent_patterns()` is not filtered by
  governed tools.
- Required: filter migration set to governed/supported tools only -- built-in
  Bash/Read/Write/Edit PLUS any tool in config's `governed_tools` /
  `additional_supported_tools`. Rules for ungoverned tools must be LEFT in
  settings.local.json untouched (not moved, not removed). Print clear note listing any
  ungoverned-tool patterns skipped.
- Find single best place to apply filter (likely where find_divergent_patterns / the
  migration set is assembled) so dry-run and apply agree. Reuse existing tool-name
  extraction (how patterns parsed into Tool(...)) -- do not hand-roll parsing.

### FIX B -- normalize redundant leading slashes (// -> /) in file-path patterns AND paths
Patterns copied from Claude Code's settings.local.json sometimes carry doubled leading
slash, e.g. `Read(//Users/arnon/...)`, `Read(//private/tmp/**)`. toolguard treats these
literally so they never match a real path -- during install even migrated "allow read
of toolguard source tree" rule denied reads of that tree.

- Required: normalize runs of consecutive slashes to single slash (`//a//b` -> `/a/b`)
  CONSISTENTLY on BOTH the file-path pattern and the path being matched, before glob
  matching, so `//`-patterns match corresponding real path. Do this in file-path
  matching/anchoring layer (toolguard/resolve.py `_anchor_file_pattern` /
  `_match_file_path_pattern`, and any path normalization in toolguard/path_utils.py).
  Apply UNIFORMLY to allow AND deny patterns and to input path so decisions stay
  consistent (`//`-deny must still deny). Do NOT change `**` globstar segment
  semantics -- only collapse duplicate slash chars. Preserve `~` expansion behavior.
  SECURITY-SENSITIVE: deny pattern must not stop denying.
- Consider whether migration should ALSO write normalized patterns; if cheap, normalize
  on migration write too, but load/match normalization is the primary fix.

## Process -- STRICT RED-GREEN WITH A CHECKPOINT
1. RED first. Add/adjust tests:
   (A) migration with mix of governed (Bash/Read) and ungoverned (WebFetch/Skill)
       patterns migrates ONLY governed ones, leaves rest in settings.local.json (both
       --dry-run listing and apply); skipped set is reported.
   (B) file-path matching: `Read(//Users/x/**)` (allow) matches `/Users/x/foo`; a
       `//`-deny still denies; collapsing does not break normal single-slash patterns,
       `**`, or `~`-anchored patterns; use trace's real examples (`//private/tmp/**`,
       `//Users/.../toolguard/**`).
   Run full suite, CONFIRM only touched/added tests fail (intended red).
2. STOP AT RED. Do NOT touch production code. Report red state to main agent via
   SendMessage: every test file/function added or changed with one-line note, exact
   failing set + reasons. WAIT for approval before GREEN (path matching is
   security-sensitive; Arnon reviews red tests, especially deny-still-denies cases).
3. GREEN after approval: change production until whole suite passes; don't edit tests
   during green except genuine mistake in own new test (call it out explicitly). Then
   `uv run ruff check .`.

## Handoff
Update basic-memory report (project 'toolguard', tag TOO-15) with path + short summary.
