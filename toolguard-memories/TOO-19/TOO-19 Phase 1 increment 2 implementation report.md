---
title: TOO-19 Phase 1 increment 2 implementation report
type: note
permalink: toolguard/too-19/too-19-phase-1-increment-2-implementation-report
tags:
- task-memory
- TOO-19
---

## Summary

Threaded `additional_context` through the FILE-PATH resolution path (increment 2 of TOO-19
Phase 1). `compound.py`, `hook.py`, and `log_writer.py` were untouched, per scope.

## Files changed

- `toolguard/config_types.py`: `ResolvedDecision` gains `additional_context: Optional[str] = None`
  (last field, keeps existing positional construction sites working). Docstring updated.
- `toolguard/config.py`:
  - New `Configuration._entry_for_pattern(layers, pattern, kind) -> Optional[RuleEntry]`,
    a companion to `_provenance_for_pattern` (same first-layer-wins walk).
  - `_resolve_permission_detailed_unclamped`: looks up the winning entry via
    `_entry_for_pattern` and reads its `.additional_context` property onto the returned
    `ResolvedDecision`. No-match / no-rules fallback branches were left as-is (they omit the
    5th positional arg, which defaults to `None`).
  - `_apply_parse_failure_ask_floor`: the clamped `ResolvedDecision` now explicitly passes
    `additional_context=None` (previously implicit via the 4-arg call; now explicit as a 5th
    positional `None`) alongside `provenance`/`override`, with the docstring updated to say so.
- `toolguard/resolve.py`:
  - `FileResolution` gains `additional_context: Optional[str] = None`. **Not** added to
    `__iter__` -- documented explicitly in the field's own docstring and covered by a test
    that unpacks the 3-tuple form.
  - `_check_file_path_hard_deny` now returns a 3-tuple `(decision, reason,
    additional_context)` instead of a 2-tuple: it looks up the matched deny pattern's entry
    via `config.hard_deny_entries(tool_name)`, index-aligned with `config.hard_deny(tool_name)`.
    Verified via grep that the only caller was `resolve_file_path_permission_detailed` itself
    (the docstring-listed `hook.py` reference is a `# noqa: F401` re-export, not a call site),
    so the signature change is safe.
  - `resolve_file_path_permission_detailed` passes `additional_context` through on both the
    hard-deny early return and the normal cascade return.

## Wrapper-intact-vs-stripped decision and evidence

`_entry_for_pattern` matches `pattern` against the WRAPPER-STRIPPED `layer.allow`/`deny`/`ask`
tuples (mirroring `_provenance_for_pattern`), then reads the corresponding `RuleEntry` off
`allow_entries`/`deny_entries`/`ask_entries` **by index**, never by comparing against
`entry.pattern` (which is wrapper-INTACT).

Evidence this is the correct form: `matched_pattern` is produced by the `decide_detailed`
callable, whose `allow`/`deny`/`ask` arguments trace back through
`permission_levels_with_provenance` -> `permission_layers` -> `layer.allow` (built by
`_extract_tool_entries`, which explicitly strips the tool wrapper). So `matched_pattern` is
always wrapper-free at the point `_entry_for_pattern` is called. The `ToolPatternLayer`
docstring's own invariant ("for each of the three allow/deny/ask pairs, X[i] is always the
wrapper-stripped form of X_entries[i].pattern -- same order, same membership, index-for-index")
is exactly the mechanism `_entry_for_pattern` relies on. I added a defensive
`len(entries) == len(candidates)` guard before indexing, to fail safe (return `None`) rather
than raise for any legacy-constructed `ToolPatternLayer` that predates structured-entry support
(where `*_entries` defaults to `()` while `allow`/`deny`/`ask` may be non-empty).

## `_provenance_for_pattern` extension vs. separate method

Chose a **separate** `_entry_for_pattern` rather than extending `_provenance_for_pattern` to
return both provenance and entry. `_provenance_for_pattern` has two call sites:
`_resolve_permission_detailed_unclamped` (needs the entry) and `_detect_override` (only needs
provenance, for the OVERRIDDEN deny in a conflict record -- `ConflictOverride` has no
`additional_context` field and this increment doesn't add one). Combining the two would give
`_detect_override` an unused second return value. The two methods do re-walk the same small
per-level layer list, but that repeat scan is cheap and the separation reads cleaner; documented
this trade-off in `_entry_for_pattern`'s own docstring.

## Hard-deny finding

`_check_file_path_hard_deny` did NOT previously surface which pattern matched to any consumer
beyond building the reason string as a local variable (`matched_deny`). Extending it to also
look up the entry and return `additional_context` was a small, contained change (about a dozen
lines, using the existing `Configuration.hard_deny_entries` accessor which was already built in
increment 0a/3 specifically for this purpose but "not yet wired into any decision path"). This
was well within the "if bigger than the rest of the increment combined, stop" guardrail -- it
was the smallest of the seven numbered items.

## Duplication / drift self-check

- Compared `_entry_for_pattern` against `_provenance_for_pattern` (structurally identical
  walk, different return type -- addressed above) and `Configuration._detect_override` (uses
  `_provenance_for_pattern`, not a candidate for reuse here since it needs provenance only).
  No existing helper already did "find the RuleEntry for a matched pattern" -- confirmed by
  grepping `config.py` for `_entries` and `additional_context` before adding anything.
  `permissions.py` contains only pure pattern-matching helpers (`decide_command_at_level_detailed`,
  `resolve_allow_ask`, etc.) with no RuleEntry-awareness at all -- nothing to reuse or duplicate
  there.
- The hard-deny index-alignment lookup in `_check_file_path_hard_deny`
  (`deny_entries[deny_patterns.index(matched_deny)]`) mirrors the pattern already used and
  tested in `test_hard_deny.py::TestHardDenyStructuredEntries::
  test_hard_deny_and_hard_deny_entries_are_index_aligned` -- not a new invention, just the same
  index-alignment contract applied at the point of use instead of only in a test.

## Tests added

- `test/unit/test_configuration.py`:
  - `TestAdditionalContextResolution` (new class): structured allow/deny/ask entries surface
    `additional_context` on `ResolvedDecision`; plain-string rule yields `None`; structured
    entry with no `additionalContext` key yields `None`; no-match fallback yields `None`.
  - `TestParseFailureAskFloor.test_additional_context_cleared_by_ask_floor` (new test in the
    existing class): the ASK floor clears `additional_context` to `None` even when the winning
    (would-be) match carried one.
- `test/unit/test_resolve.py`:
  - `TestFilePathAdditionalContext` (new class): structured allow/deny/ask entries surface
    `additional_context` on `FileResolution` for Read/Write/Edit respectively; plain-string
    rule yields `None`; hard-deny match carries `additional_context`; explicit 3-tuple
    unpacking regression test (`decision, reason, override = result`).

13 new tests, all passing. Full suite: 1898 tests (1885 baseline + 13), run against an empty
`$HOME`/`$XDG_CONFIG_HOME` per the project's isolation convention -- OK.

## Verification

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -- OK, 1898 tests.
- `uv run ruff check .` -- all checks passed.
- `uv run ruff format` run ONLY on the 5 touched files (`toolguard/config.py`,
  `toolguard/config_types.py`, `toolguard/resolve.py`, `test/unit/test_configuration.py`,
  `test/unit/test_resolve.py`) -- 3 needed reformatting (long lines), 2 were already clean.
  Did not touch any other pre-existing unformatted file in the repo.
- `uv run python -m py_compile` on all 5 touched files -- OK.

## Out of scope / not done (correctly, per the prompt)

- `toolguard/compound.py`, `toolguard/hook.py`, `toolguard/log_writer.py` -- untouched, these
  are increments 3-7.
- `ConflictOverride` was not given an `additional_context` field -- not requested, and
  `_detect_override`'s only consumer (the overridden deny) has no spec requirement for it in
  this increment.
- Did not add `additional_context` to `BashResolution` or `SubMatch` -- Bash resolution is
  out of scope for increment 2 (file-path only).

## Anti-pattern check

No async/await, no threading, no local (function-level) imports introduced. All new/changed
functions and classes carry docstrings.

## Not committed

No git commits made, per instructions.
