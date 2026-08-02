---
title: TOO-19 allow and allow_with_no_warnings fallback values - coder task recall
type: note
permalink: toolguard/implementation/too-19-allow-and-allow-with-no-warnings-fallback-values-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task

Repo: /home/arnon/projects/toolguard (branch too-19). Ticket TOO-19.

Add `allow` and `allow_with_no_warnings` as fallback values for both `no_match_fallback` and
`undecidable_fallback`.

### Spec (verbatim in substance, from Arnon via orchestrator)

> both for `no_match_fallback` and for `undecidable_fallback` we should have an `allow` option
> that does not emit warnings, and an alias with identical meaning called
> `allow_with_no_warnings` (the longer variant serves as a human reminder that you may want to
> change it, and requires only a 3-character change to switch it to `allow_with_warning`).

Each of the two settings now accepts five values:
`ask` (default) | `deny` | `allow_with_warning` | `allow` | `allow_with_no_warnings`

`allow` and `allow_with_no_warnings` are **exact synonyms**: allow the command, emit **no**
warning anywhere. Normalise `allow_with_no_warnings` -> `allow` at resolution time, same way
existing deprecated `warn_deny` -> `allow_with_warning` normalisation works for
`no_match_fallback`. `undecidable_fallback` deliberately does NOT honour `warn_deny`; keep that
asymmetry.

### Where to change (find and verify before editing)

1. `toolguard/config.py` -- valid-value sets and shared resolver (extracted for review finding
   m2, shaped for TOO-28's two future `*_auto_mode` variants). Extend the resolver, don't
   special-case.
2. Reason strings. `allow_with_warning` -> "allowed with a warning by
   no_match_fallback=allow_with_warning". For `allow`, must NOT claim a warning was emitted.
   Accurate text naming the setting and value.
3. `toolguard/hook.py::_log_fallback_allow_warning` -- must NOT fire for `allow` /
   `allow_with_no_warnings`. Currently detects marker wording in reason string. Prefer fixing
   properly: key off resolved fallback value as data if the decision carries it, rather than
   substring matching prose. Report which approach taken and why.
4. `toolguard/compound.py::_apply_undecidable_floor` -- ranks deny > ask > allow. `allow` and
   `allow_with_warning` are the SAME strictness level; only warning differs. Both must behave
   identically for floor purposes.
5. Security audit: `loose-undecidable-fallback` (HIGH) currently fires for `allow_with_warning`.
   Must also fire for `allow` / `allow_with_no_warnings` (strictly less safe -- nothing
   recorded). Check whether analogous `loose-no-match-fallback` finding needs same treatment;
   keep consistent. Do not fire for `ask`/`deny`. Report findings.

### Tests (minimum coverage)

- All five values parse and resolve for BOTH settings.
- `allow_with_no_warnings` resolves identically to `allow`.
- Unrecognised value resolves to `ask`.
- `allow` produces allow verdict with NO warning-stream entry; `allow_with_warning` still
  produces one.
- Reason text for `allow` does not claim a warning.
- Undecidable floor treats `allow` and `allow_with_warning` identically.
- Audit findings fire for all three allow-ish values, not for ask/deny.
- `warn_deny` still works for `no_match_fallback`, still rejected for `undecidable_fallback`.

Tests touching config discovery MUST use `ConfigIsolationMixin` (see
`.claude/rules/test-config-isolation.md`).

### Docs

Update `docs/configuration.md` (both settings' value lists / tables) and `docs/security.md`
(loosening discussion). Explain WHY the long alias exists (deliberate human reminder -- the
whole point of having two spellings). Single hyphens in any NEW heading. Update
`docs/agent-map.md` for any new heading.

### Verification steps required

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- must be OK. Baseline **2039** tests
  (should increase with new tests, none should fail).
- `uv run ruff check .` and `uv run ruff format --check .` clean repo-wide.
- `uv run python tools/check_doc_links.py` exits 0.
- Demonstrate end-to-end with `toolguard.testing.sandbox` for both settings: show `allow`,
  `allow_with_no_warnings`, `allow_with_warning` side by side on an unmatched command and on an
  undecidable one (e.g. `case $x in a) b;; esac`). Paste the output in the report.
- Real `logs/` untouched: report before/after entry counts around suite run.

### Report

basic-memory project `toolguard`, path `TOO-19/TOO-19 allow and allow_with_no_warnings fallback
values.md`, tagged `task-memory` and `TOO-19`. Include: prose-vs-data decision for item 3, the
audit-consistency finding for item 5, and the sandbox demonstration.

## Constraints reiterated

- unittest NOT pytest. BDD Given/When/Then docstrings on every test.
- No function-level imports. Docstring on every function/class. stdlib-only runtime.
- Never run bare `python`/`python3` -- always `uv run python`.
- Never edit anything outside this repo. No git write operations.
- Never write to the repo's real `logs/` directory.
- PYTHONPATH=. shadowing hazard note from older docs is FIXED as of 2026-08-02; installed
  toolguard governs, no special precaution needed there.
- Announce-intent rule (CLAUDE.md) applies to any inline/heredoc/scratch-script bash I run.

## Success criteria

All test/verification items above pass; docs updated and consistent; audit findings behave per
spec; report written with the three required discussion sections.
