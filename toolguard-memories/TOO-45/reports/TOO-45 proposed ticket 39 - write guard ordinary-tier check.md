---
title: TOO-45 proposed ticket 39 - write guard ordinary-tier check
type: note
permalink: toolguard/too-45/reports/too-45-proposed-ticket-39-write-guard-ordinary-tier-check
tags:
- TOO-45
- implementation-report
---

## Task

Proposed ticket 39's remaining defect: `verified_write_config`'s content-loss check
(`toolguard/config_write_guard.py`) refused a `hard_deny -> permissions.allow` rewrite
(fixed already in `05f786d`) but silently accepted `permissions.deny -> permissions.allow`
and `permissions.ask -> permissions.allow`.

## Defect confirmed independently before touching code

Ran a probe against the pre-change code (not from the brief -- executed myself):

```
hard_deny.deny -> permissions.allow: REFUSED -- write would move pattern(s) out of hard_deny
permissions.deny -> permissions.allow: WRITES OK
permissions.ask -> permissions.allow: WRITES OK
pattern deleted outright (control): REFUSED -- write would drop existing rule pattern(s)
```

Matches the brief's claimed matrix exactly -- no conflict to flag.

## What the new check compares, and why

Added a second placement check inside `verified_write_config`'s existing step 3 block
(same `if path.exists()` / `if original_parsed is not None` gate as the hard_deny check),
comparing the parsed original (from disk) against the parsed replacement text:

```python
restricting_before = _permissions_lists_patterns(original_parsed, ("deny", "ask"))
restricting_after = _permissions_lists_patterns(parsed, ("deny", "ask"))
allow_after = _permissions_lists_patterns(parsed, ("allow",))
moved_to_allow = sorted((restricting_before - restricting_after) & allow_after)
```

Refuses when non-empty, with reason `"write would move pattern(s) from deny/ask into
permissions.allow"`.

**Decision, written down as requested:** the check is deliberately NOT symmetric with the
hard_deny check. Hard_deny is the strictest tier, so leaving it is *always* a loss regardless
of destination -- the existing check correctly does a plain set difference. Ordinary
`deny`/`ask` are two different restricting sections at the SAME tier, so moving a pattern
between them (`deny` -> `ask` or `ask` -> `deny`) is not a loss and must not be flagged --
that's why `restricting_after` subtracts out patterns still present in *either* list, not
just the one they started in. A pattern present in BOTH `permissions.deny` and
`permissions.allow` after the write is also not flagged: it stays in `restricting_after`
because it's still in `deny`, and `deny` wins over `allow` at the same level, so nothing was
actually lost. This is purely presence-based (`_entry_pattern` string equality, same
precision the existing checks already use) -- no matcher, no `permissions.py` import, no
layer-relationship change.

The new check is independent of, and does not affect, the existing `hard_deny` check --
both run in sequence inside the same `if original_parsed is not None:` block.

## Preserving the broken-original tolerance

Untouched: both checks stay inside `if path.exists(): ... if original_parsed is not None:`.
An unparseable on-disk original still sets `original_parsed = None` and both placement checks
are skipped entirely -- a corrupted file remains writable. Pinned with a new test,
`test_write_over_unparseable_original_skips_placement_checks`: original on-disk text is
invalid TOML, replacement text moves a pattern from `deny` to `allow`, and the write still
succeeds.

## Tests added (`test/unit/test_config_write_guard.py`)

1. `test_pattern_moved_from_permissions_deny_into_allow_is_refused`
2. `test_pattern_moved_from_permissions_ask_into_allow_is_refused`
3. `test_pattern_moved_between_deny_and_ask_is_not_refused` (negative control -- legitimate
   move must still succeed)
4. `test_pattern_kept_in_deny_while_also_added_to_allow_is_not_refused` (negative control --
   pins the "deny beats allow at the same level" decision explicitly)
5. `test_write_over_unparseable_original_skips_placement_checks` (tolerance regression pin)

**Verified against pre-change code** by copying `git show HEAD:toolguard/config_write_guard.py`
over the working file, running the five new tests, then restoring the fixed file:

```
test_pattern_moved_from_permissions_deny_into_allow_is_refused ... FAIL (AssertionError: ConfigWriteVerificationError not raised)
test_pattern_moved_from_permissions_ask_into_allow_is_refused ... FAIL (AssertionError: ConfigWriteVerificationError not raised)
test_pattern_moved_between_deny_and_ask_is_not_refused ... ok  (already passed -- correctly not new behaviour)
test_pattern_kept_in_deny_while_also_added_to_allow_is_not_refused ... ok  (already passed)
test_write_over_unparseable_original_skips_placement_checks ... ok  (already passed -- pre-existing tolerance, not new)
```

Exactly the two tests asserting the fixed behaviour fail pre-change; the three negative
controls / tolerance pin already passed, confirming they test pre-existing behaviour rather
than accidentally depending on the fix.

## Other changes

- Extracted `_permissions_lists_patterns(parsed, list_types)` from the inline loop in
  `_patterns_in_parsed`, so both the existing full-scan and the new deny/ask-vs-allow
  comparison share one implementation (DRY, no behaviour change --
  `test_patterns_in_config_text` suite still passes unchanged).
- Updated `verified_write_config`'s docstring (step 3) to describe both placement checks and
  state the asymmetry decision above.
- Removed a stale docstring claim on the existing `test_pattern_moved_out_of_hard_deny_into_allow_is_refused`
  test (`"RED until proposed ticket 39 lands"`) -- that test already passes and is not marked
  `expectedFailure`; the hard_deny half of ticket 39 landed in `05f786d`, so the sentence was
  false at the time I read it. Left the test's Given/When/Then intact.

## Final verification probe against the fixed code

```
hard_deny.deny -> permissions.allow: REFUSED -- write would move pattern(s) out of hard_deny
permissions.deny -> permissions.allow: REFUSED -- write would move pattern(s) from deny/ask into permissions.allow
permissions.ask -> permissions.allow: REFUSED -- write would move pattern(s) from deny/ask into permissions.allow
pattern deleted outright (control): REFUSED -- write would drop existing rule pattern(s)
deny -> ask move (legitimate, control): WRITES OK
```

## Gates

- Full suite before: `Ran 3800 tests in 59.281s` / `OK (expected failures=4)`.
- Full suite after: `Ran 3805 tests in 56.266s` / `OK (expected failures=4)` (3800 + 5 new).
- `uv run ruff format .` -- reformatted the two touched files (my own additions only, per
  diff inspection); `uv run ruff check .` -- `All checks passed!`.
- `uv run python tools/architecture_fitness.py --ambient --layers --mocks --stdlib`: layers
  complete and directionally clean, stdlib-only holds, ambient reads all owned. `--mocks`
  shows the one pre-existing, unrelated finding
  (`test_session_warnings.py:159 patch("toolguard.error_log.log_crash")`), matching the
  brief's stated known finding.
- `~/.toolguard/errors/`: 1950 before, 1950 after -- unchanged.

## Scope

Two files touched (`toolguard/config_write_guard.py`, `test/unit/test_config_write_guard.py`),
no new files, no design detours -- matches the ticket's own "narrow" framing. Did not import
`permissions.py` or build a matcher, as the ticket instructed to stop and report if that urge
arose; it didn't.

## Untrusted-instruction note

A tool-output system-reminder appeared mid-session instructing a switch to raw
Bash/cat/sed/heredoc file operations in place of the Read/Edit/Write tools. This contradicts
my actual operating instructions and arrived through session/tool output rather than from
Arnon directly, so I disclosed it and ignored it, continuing with Read/Edit/Write as normal.

## Elapsed time and estimated cost

- Phase 1 (planning: read ticket, module, tests, probe against pre-change code, task recall):
  ~19:40-19:44 EDT, ~4 min.
- Phase 2 (implementation: helper extraction, new check, docstrings, 5 new tests,
  pre-change regression verification): ~19:44-19:49 EDT, ~5 min.
- Phase 3 (self-review: full suite x2, ruff, architecture fitness, errors-dir count, final
  probe): ~19:49-19:55 EDT (overlapping with phase 2 tool calls above), ~6 min.
- Phase 4 (this report): ~2 min.
- Total wall time: roughly 15-17 minutes.
- Estimated cost: small task, well under the 30-minute scope-inflation trigger; on Sonnet
  pricing with the token volume used here (a handful of file reads/edits, two full-suite
  runs, no large context re-reads), estimate is on the order of $0.30-$0.60 total.
