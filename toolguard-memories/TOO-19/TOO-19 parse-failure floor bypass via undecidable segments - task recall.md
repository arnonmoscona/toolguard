---
title: TOO-19 parse-failure floor bypass via undecidable segments - task recall
type: note
permalink: toolguard/too-19/too-19-parse-failure-floor-bypass-via-undecidable-segments-task-recall
tags:
- task-memory
- TOO-19
---

## Task

Security fix: with a broken config present AND `undecidable_fallback = "allow_with_warning"`,
commands that hit a grammar-level `UndecidableSegment` (process substitution, `case`, `while
read < file`, etc.) resolve to `allow` instead of `ask`, because `UndecidableSegment` handling
in `toolguard/compound.py::resolve_compound_permission` (~line 552-583) never calls
`resolve_one` / `Configuration.resolve_permission_detailed`, so the parse-failure ASK floor
(`Configuration._apply_parse_failure_ask_floor`) never runs for that segment.

## Root cause confirmed

- `toolguard/compound.py` lines 552-583: `isinstance(element, UndecidableSegment)` branch
  floors only against `undecidable_fallback`, never touches `config`.
- `toolguard/config.py::resolve_permission_detailed` (~1470-1512) is the only place the floor
  currently runs, called once per sub-command leaf via `_resolve_one` in
  `toolguard/resolve.py::resolve_bash_permission_detailed`.
- `resolve_file_path_permission_detailed` (resolve.py ~469-537) always calls
  `config.resolve_permission_detailed` -- confirmed NO equivalent bypass there. Its hard-deny
  early return is a `deny`, preserved unchanged by the floor by design.

## Required fix (from spec, do not deviate)

1. In `config.py`: extract core of `_apply_parse_failure_ask_floor` into new reusable method
   on `Configuration` taking a plain `(decision, reason)` pair, returning possibly-clamped
   pair. Same semantics: no parse failures -> unchanged; `decision == "deny"` -> unchanged;
   else -> `("ask", self._parse_failure_reason())`.
2. Refactor `_apply_parse_failure_ask_floor` to delegate to it (single implementation).
   Existing tests for it must pass unchanged.
3. Call new method in `resolve.py::resolve_bash_permission_detailed`, on final
   `(decision, reason)` from `resolve_compound_permission`, before building `BashResolution`.
   Idempotent re-application when already clamped -- must add test proving this.
4. Comment at call site explaining WHY floor applied twice (per-leaf + compound boundary).
5. Verify file-path path has no bypass (already confirmed above -- report this).

## Tests required (new file or add to test_resolve.py near TestUndecidableFallbackThreading)

- Broken config + allow_with_warning + `diff <(sort a) <(sort b)` -> ask, reason names file.
- Broken config + allow_with_warning + `case $x in a) b;; esac` -> ask (different UndecidableSegment
  construction site, multiline.py ~600).
- Broken config + undecidable_fallback=deny -> stays deny.
- No parse failure + allow_with_warning + undecidable command -> still allow (proves fix
  doesn't disable escape hatch).
- Idempotence: normal decomposable command under broken config -> exactly one clamped ask,
  unchanged reason.
- Name one test:
  `test_parse_failure_floor_covers_undecidable_segments_that_bypass_the_per_leaf_chokepoint`

Existing test `test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback`
(test_resolve.py ~963) is a FALSE-CONFIDENCE test -- it uses `python3 -c "..."` (an ask_floor
LEAF / foreign inline code case that already goes through `resolve_permission_detailed`), NOT
a true `UndecidableSegment` (grammar parse failure). That's exactly why the bug shipped despite
this test existing. Don't rely on it; write the new UndecidableSegment-specific tests.

## Mutation check required

Revert the new call in `resolve_bash_permission_detailed`, confirm new tests FAIL, restore,
report exact failure output.

## Config isolation

Tests likely build `Configuration` directly (hand-built layers, no file I/O) per existing
pattern in `TestUndecidableFallbackThreading` (`_make_config` helper) -- per
test-config-isolation.md checklist, if no discovery path is touched, no `ConfigIsolationMixin`
needed. Confirm this holds for whatever I write.

## Verification commands

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- baseline 1988 tests, must report OK.
- `uv run ruff check .` clean; `uv run ruff format` only touched files.
- Re-run sandbox repro from ticket, paste corrected output.

## Report location

basic-memory project `toolguard`, path
`TOO-19/TOO-19 parse-failure floor bypass via undecidable segments - fix report.md`,
tags `task-memory`, `TOO-19`.
