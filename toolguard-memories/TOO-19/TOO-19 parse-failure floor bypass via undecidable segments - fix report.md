---
title: TOO-19 parse-failure floor bypass via undecidable segments - fix report
type: note
permalink: toolguard/too-19/too-19-parse-failure-floor-bypass-via-undecidable-segments-fix-report
tags:
- task-memory
- TOO-19
---

## Summary

Fixed the fail-open security bug: a broken (unparseable) config file combined with
`undecidable_fallback = "allow_with_warning"` allowed commands that hit a grammar-level
`UndecidableSegment` (process substitution, `case`, `while read < file`, etc.) to resolve to
`allow`, because that code path never reaches `Configuration.resolve_permission_detailed` and
so never saw the parse-failure ASK floor.

## Root cause (confirmed)

`toolguard/compound.py::resolve_compound_permission` handles `UndecidableSegment` elements
(~line 552-583) by flooring directly against `undecidable_fallback`, without ever calling
`resolve_one` (i.e. `Configuration.resolve_permission_detailed`). The parse-failure ASK floor
(`Configuration._apply_parse_failure_ask_floor`) lived only inside
`resolve_permission_detailed`, so it never ran for these segments.

## Fix

1. **`toolguard/config.py`**: extracted the clamp's core logic into a new public method
   `Configuration.apply_parse_failure_floor(decision, reason) -> (decision, reason)`. Same
   semantics as before: no parse failures -> unchanged; `decision == "deny"` -> unchanged;
   otherwise -> `("ask", self._parse_failure_reason())`.
2. `_apply_parse_failure_ask_floor` now delegates the value computation to
   `apply_parse_failure_floor` (kept its own guard clause so the short-circuit for "no parse
   failures / already deny" behaves identically to before -- see "one wrinkle" below).
3. **`toolguard/resolve.py::resolve_bash_permission_detailed`**: added
   `decision, reason = config.apply_parse_failure_floor(decision, reason)` immediately after
   `resolve_compound_permission` returns, before building `BashResolution`. A comment at the
   call site explains why the floor is applied twice (per-leaf inside `_resolve_one`, and here
   at the compound boundary) and warns against "simplifying" it away.
4. **`toolguard/test/unit/test_hook.py`**: the hook's `_FakeConfig` test double needed a new
   `apply_parse_failure_floor` pass-through method (mirrors its existing
   `resolved_undecidable_fallback` fake) since `resolve_bash_permission_detailed` now calls it
   unconditionally.

### One wrinkle caught by the test suite, not by me

My first draft of `_apply_parse_failure_ask_floor` used a "did the decision string change"
shortcut to decide whether to return the original `resolved` object unchanged. That is WRONG:
when the pre-clamp decision was already `'ask'` (e.g. the no-match-fallback default `'ask'`,
which carries a different reason than the floor's), the shortcut incorrectly treated it as
"unchanged" and skipped rewriting the reason. `test_ask_reason_rewritten_to_name_broken_file`
(pre-existing, untouched) caught this immediately. Fixed by keeping the original guard
(`not self.parse_failures or resolved.decision == "deny"`) as the single source of truth for
whether to rewrite, and delegating only the *value* computation to the new method.

## File-path path bypass check (required by ticket)

Confirmed no equivalent bypass. `resolve_file_path_permission_detailed`
(`toolguard/resolve.py`, ~469-537) has exactly two exits:
- A hard-deny early return -- always `'deny'`, which the floor preserves unchanged by design.
- `config.resolve_permission_detailed(tool_name, _decide_detailed)` -- always routes through
  the per-leaf chokepoint and therefore the floor.

There is no bash-grammar concept (`UndecidableSegment`, compound decomposition) on the
file-path path at all, so there is no analogous class of bypass to close there.

## No other bypass of the per-sub-command chokepoint noticed

Reviewed `toolguard/compound.py` end to end while tracing this bug. The only two things that
produce a verdict without going through `resolve_one` are: (a) the ask_floor LEAF case (foreign
inline code / heredoc sinks) via `_resolve_leaf`, which floors against `undecidable_fallback`
only -- but its OUTER command's resolution still goes through `resolve_one` per the existing
test `test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback`, so it was
never actually unfloored; and (b) `UndecidableSegment`, the bug just fixed. No other
verdict-producing branch bypasses `resolve_one`.

## Tests added (`test/unit/test_resolve.py`, new class
`TestParseFailureFloorCoversUndecidableSegments`)

- `test_parse_failure_floor_covers_undecidable_segments_that_bypass_the_per_leaf_chokepoint`
  -- process substitution + broken config + allow_with_warning -> ask, reason names file.
- `test_grammar_parse_failure_undecidable_segment_also_floored` -- `case $x in a) b;; esac`
  (the OTHER `UndecidableSegment` construction site: genuine grammar parse failure in
  `toolguard/parser/multiline.py`, distinct from the process-substitution detection site) ->
  ask.
- `test_broken_config_undecidable_segment_stays_deny_under_deny_fallback` --
  `undecidable_fallback='deny'` + broken config -> stays deny.
- `test_no_parse_failure_allow_with_warning_undecidable_segment_still_allows` -- no parse
  failure + allow_with_warning -> still allow (escape hatch not disabled outright).
- `test_normal_decomposable_command_under_broken_config_clamped_exactly_once` -- idempotence:
  a normal leaf command under a broken config yields exactly one clamped ask with one copy of
  the broken-file path in the reason (proves double-application doesn't corrupt or duplicate).

Also identified and flagged (not duplicated) the existing FALSE-CONFIDENCE test
`TestUndecidableFallbackThreading.test_broken_config_still_asks_despite_allow_with_warning_undecidable_fallback`
in `test_resolve.py`, which uses `python3 -c "..."` (an ask_floor LEAF, already covered) rather
than a true `UndecidableSegment` -- documented in the new class's docstring so a future reader
understands why this class exists alongside it.

## Mutation check (required)

Temporarily commented out the new `decision, reason = config.apply_parse_failure_floor(...)`
line in `resolve.py`, ran the new test class in isolation:

```
FAIL: test_grammar_parse_failure_undecidable_segment_also_floored
AssertionError: 'allow' != 'ask'
FAIL: test_parse_failure_floor_covers_undecidable_segments_that_bypass_the_per_leaf_chokepoint
AssertionError: 'allow' != 'ask'
Ran 5 tests in 0.002s
FAILED (failures=2)
```

The two tests targeting the actual bug failed as expected; the other three (deny-preserved,
no-parse-failure-still-allows, idempotence) correctly still passed since they don't exercise
the reverted line. Restored the line; full suite green again.

## Verification

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- **1993 tests, OK** (1988 baseline + 5 new).
- `uv run ruff check .` on touched files: clean. `uv run ruff format` applied (only reformatted
  the new method signature to one line; no semantic changes).
- Sandbox repro, corrected output:

```
$ uv run python -m toolguard.testing.sandbox --config <broken.toml> --user-config <allow_with_warning> --command 'diff <(sort a) <(sort b)' --json
{
  "verdict": "ask",
  "reason": "toolguard config is BROKEN -- falling back to ask for every tool call.\nUnparseable file(s):\n  .../.claude/toolguard_hook.toml: Expected '=' after a key in a key/value pair (at line 1, column 6)\nRules in these files are NOT being enforced. Fix the file(s) to restore normal permission handling."
}
```

Same corrected result for `case $x in a) b;; esac` and `while read l; do echo $l; done < f`.

With the SAME `allow_with_warning` config but NO broken file, `diff <(sort a) <(sort b)`
still correctly resolves to `allow` -- confirming the escape hatch itself is untouched, only
the broken-config bypass is closed.

## Files changed

- `toolguard/config.py` -- new `Configuration.apply_parse_failure_floor`, refactored
  `_apply_parse_failure_ask_floor` to delegate.
- `toolguard/resolve.py` -- new call in `resolve_bash_permission_detailed` + explanatory
  comment.
- `test/unit/test_hook.py` -- `_FakeConfig.apply_parse_failure_floor` pass-through added.
- `test/unit/test_resolve.py` -- new `TestParseFailureFloorCoversUndecidableSegments` class,
  5 tests.

## Self-review notes

- No async/await, no threading, no function-level imports introduced.
- Docstrings on both new/changed methods and the new test class/methods (BDD Given/When/Then).
- Followed the ticket's exact prescribed design (single delegated implementation, call at the
  compound boundary, comment explaining the double application) -- no scope deviation.
- Total footprint: 2 source files, 2 test files changed. Well within scope-inflation limits.
