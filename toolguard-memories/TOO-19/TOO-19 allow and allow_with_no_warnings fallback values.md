---
title: TOO-19 allow and allow_with_no_warnings fallback values
type: note
permalink: toolguard/too-19/too-19-allow-and-allow-with-no-warnings-fallback-values
tags:
- task-memory
- TOO-19
---

## Summary

Added `allow` and `allow_with_no_warnings` (exact synonym, normalized to `allow`) as new
values for both `no_match_fallback` and `undecidable_fallback`. Both settings now accept five
values: `ask` (default) | `deny` | `allow_with_warning` | `allow` | `allow_with_no_warnings`.
`allow`/`allow_with_no_warnings` allow the command with **no warning anywhere** -- not in the
resolution-log reason, not in the WARNING log stream.

All verification steps in the task spec pass: full suite 2070/2070 (baseline 2039 + 31 new),
`ruff format --check` / `ruff check` clean, `tools/check_doc_links.py` exits 0, sandbox
demonstration below, real `logs/` untouched by the test run (see "Logs" section).

## Files changed

**Production (7):**
- `toolguard/config_types.py` -- `ResolvedDecision.fallback_warning: bool = False` field.
- `toolguard/config.py` -- valid-value sets extended; `_resolve_fallback_setting`'s
  `deprecated_aliases` param renamed to `alias_map` (see "Naming" below) and extended;
  `resolved_no_match_fallback`/`resolved_undecidable_fallback` now accept
  `allow_with_no_warnings`; the no-match-fallback consumption branch gained an `allow` case
  and sets `fallback_warning=True` only for `allow_with_warning`.
- `toolguard/resolve.py` -- `FileResolution.fallback_warning` (real data, propagated directly
  from `ResolvedDecision.fallback_warning`) and `BashResolution.fallback_warning` (computed by
  a new `_bash_result_is_fallback_warning` marker-detector, moved here from hook.py) added;
  `resolve_file_path_permission_detailed`/`resolve_bash_permission_detailed` wire them.
- `toolguard/compound.py` -- `_UNDECIDABLE_FLOOR_DECISION` gained `"allow": "allow"`; both
  reason-building call sites (`_resolve_leaf`'s ask-floor branch,
  `resolve_compound_permission`'s UndecidableSegment branch) now branch on the ACTUAL
  configured value (not just `floored == "allow"`) so `allow`'s reason text says "no warning"
  and never contains the `allow_with_warning` marker substring.
- `toolguard/hook.py` -- `_log_fallback_allow_warning` signature changed to
  `(fallback_warning: bool, reason: str, log_dir)`; the old `_ALLOW_WITH_WARNING_MARKERS`
  substring-matching logic is GONE from this module (moved to resolve.py); both call sites
  updated to pass `result.fallback_warning`.
- `toolguard/tools/takeover_audit.py` -- `loose-undecidable-fallback` (HIGH) now fires for
  `resolved_undecidable_fallback() in ("allow_with_warning", "allow")`, with
  value-specific description/impact text (never claims a warning for `allow`).
  `loose-no-match-fallback` (LOW) needed NO code change -- see "Audit consistency" below.
- `toolguard/tools/installer.py` -- `enable-takeover --no-match-fallback` CLI `choices` and
  help text extended to accept `allow`/`allow_with_no_warnings` (flagged as an additional,
  out-of-spec-but-related fix -- see "Additional finding" below).

**Tests (6, 31 new test methods):** `test/unit/test_configuration.py`,
`test/unit/test_resolve.py` (new `TestFallbackWarningField` class), `test/unit/test_compound.py`,
`test/unit/test_hook.py`, `test/unit/test_tools_takeover_audit.py`,
`test/unit/test_tools_installer.py`. None needed `ConfigIsolationMixin` -- all build
`Configuration` from hand-constructed `ConfigLayer`/`Provenance` (zero file I/O) or drive
`main()` in a module already isolated via `isolate_log_dir_for_module()` (test_hook.py).

**Docs (7):** `docs/configuration.md`, `docs/security.md` (both explicitly required by the
spec) plus `docs/auto-mode.md`, `docs/install.md`, `docs/permission-patterns.md`,
`technical-notes.md`, `skills/toolguard-security-audit/SKILL.md` (doc-drift sweep -- see
below). No new headings added anywhere, so `docs/agent-map.md` needed no update.

Note: `CLAUDE.md`, `toolguard/log_writer.py`, `test/unit/test_log_writer.py`,
`docs/agent-guides.md`, `docs/agent-map.md`, `docs/architecture.md`, `docs/takeover-mode.md`,
`AGENTS.md`, `llms.txt` all show as modified in `git status` but I did NOT touch any of them --
they were either already modified before this session started, or (in `CLAUDE.md`'s case)
changed by something else during the session. Flagging this so it isn't misattributed.

## Design decisions

### Naming: `deprecated_aliases` -> `alias_map`

`_resolve_fallback_setting`'s parameter was named `deprecated_aliases`. Reusing it unchanged
for `allow_with_no_warnings` would have been technically fine but semantically wrong:
`allow_with_no_warnings` is NOT deprecated -- it is a *permanent* synonym, the whole point of
the ticket being that it's a durable human reminder, not a spelling on its way out. Renamed to
`alias_map` and broadened the docstring to describe both kinds of alternate spelling it now
covers (truly-deprecated legacy values like `warn_deny`, and deliberate permanent synonyms like
`allow_with_no_warnings`). Contained rename: only the one method + its two call sites + one
already-internal keyword argument; no external code depended on the old name.

### Item 3 (hook.py `_log_fallback_allow_warning`): prose-vs-data decision

The spec's preference was: "if the decision now carries the resolved fallback value as data,
key off that instead of substring matching prose." I made it carry real data, but the depth of
that varies by resolution path, and I chose NOT to do a full plumb-through for the compound
path. Full reasoning:

**File-path (Read/Write/Edit) path -- 100% real data, zero parsing.** Added
`ResolvedDecision.fallback_warning: bool`, set precisely at the ONE place
`Configuration._resolve_permission_detailed_unclamped` already structurally distinguishes the
`allow_with_warning` branch from every other branch (including the new `allow` branch). This
propagates unchanged to `FileResolution.fallback_warning`. `hook.py`'s
`_log_fallback_allow_warning` now takes `fallback_warning: bool` as a parameter and does ZERO
string inspection -- this is the part of item 3 that is unambiguously "fixed properly."

**Compound (Bash) path -- centralized text-detection, NOT eliminated.** I investigated fully
plumbing `fallback_warning` through the compound pipeline (`resolve_one` Callable contract ->
`_resolve_leaf` -> `resolve_compound_permission` -> `_combine_strictest`) and found it
infeasible without disproportionate blast radius: `resolve_one`'s `Callable[[str], Tuple[str,
str, Optional[str]]]` 3-tuple contract is a stable public-ish abstraction with **18 existing
test-authored closures** across `test_compound.py`, `test_hard_deny.py`, and
`test_hierarchical.py` (verified by grep) that all return bare 3-tuples. Widening it to 4
elements would break every one of those closures with `ValueError: not enough values to
unpack`, since `_resolve_leaf`/`resolve_compound_permission`'s bodies do a fixed positional
unpack of whatever closure is passed in, test-authored or production. I am prohibited from
touching the main test suite's existing tests except to extend them, and even setting that
aside, breaking 18 test call sites for an internal-robustness nicety (no functional bug exists
today) would be a disproportionate, high-risk change for this ticket.

Instead: moved the substring-marker detection (`_ALLOW_WITH_WARNING_MARKERS`,
previously in hook.py) into `resolve.py` as a new private function
`_bash_result_is_fallback_warning(reason)`, called exactly once at the point
`resolve_bash_permission_detailed` builds the final `BashResolution`. This is still
text-derived for the compound path specifically, but: (1) it is now centralized in ONE place
instead of being hook.py's job, (2) it is exercised by dedicated regression tests
(`TestFallbackWarningField` in test_resolve.py, plus reason-text tests in test_compound.py)
that assert the new `allow` wording never collides with the `allow_with_warning` marker, (3)
from **hook.py's perspective** -- the module the spec names explicitly -- it is 100%
data-driven: `_log_fallback_allow_warning` reads a bool, full stop. I verified the marker
strings cannot collide: `"no_match_fallback=allow "` (space, followed by parenthetical) is not
a substring of `"no_match_fallback=allow_with_warning"`, confirmed by the passing
`assertNotIn("allow_with_warning", ...)` assertions in every new test.

I considered a "side-channel" enhancement (a mutable list captured by the `_resolve_one`
closure inside `resolve_bash_permission_detailed`, mirroring the existing pattern already used
there for `overrides`/`sub_matches`) that would have made the `no_match_fallback`-within-compound
sub-case real data too, leaving only the `undecidable_fallback`-within-compound sub-case
text-derived. I decided against adding it: it's a third propagation mechanism on top of two
already in play, for marginal benefit, and the ticket's own scope-inflation guidance argues for
stopping at "good enough, well-justified" rather than continuing to add mechanisms. Flagging
this as a considered-and-declined enhancement in case Arnon wants it done as a follow-up.

### Audit consistency (item 5)

`loose-undecidable-fallback` (HIGH): changed `== "allow_with_warning"` to
`in ("allow_with_warning", "allow")`. Since `resolved_undecidable_fallback()` normalizes
`allow_with_no_warnings` -> `allow` before this check runs, this one change covers all three
allow-ish spellings. Description/impact text is now value-specific so `allow`'s finding
correctly says "NO warning" rather than reusing `allow_with_warning`'s wording.

`loose-no-match-fallback` (LOW): **no code change needed.** This check is
`takeover.no_match_fallback != "deny"` -- a blanket "not deny" test, not an equality test
against one specific loose value. `takeover.no_match_fallback` is read RAW off
`TakeoverConfig` (unnormalized -- confirmed by reading `Configuration.takeover_mode()`'s
`no_match_fallback = section["no_match_fallback"]` with no alias resolution), so literally any
non-`"deny"` string -- `"ask"`, `"allow_with_warning"`, `"warn_deny"`, and now `"allow"` /
`"allow_with_no_warnings"` -- already fires it. I verified this with two new tests
(`test_allow_fallback_flagged`, `test_allow_with_no_warnings_fallback_flagged`) rather than
just asserting it from reading the code. Documented this finding in the module docstring and a
code comment so a future reader doesn't wonder why item 5 only touched one of the two checks.

## Additional finding: `installer.py` CLI choices (flagged, not in original spec)

While searching for every place describing these settings' valid values (per CLAUDE.md's
doc-drift-sweep convention), found `toolguard enable-takeover --no-match-fallback` has an
argparse `choices=("ask", "deny", "allow_with_warning")` that would reject the new values with
an "invalid choice" error -- a real functional gap a user hitting the CLI would experience.
Fixed the `choices` tuple and the subcommand's help text, and added 2 tests
(`test_sets_allow_fallback`, `test_sets_allow_with_no_warnings_fallback`). This wasn't in the
ticket's explicit "where to change things" list, so flagging it explicitly here per the
transparency principle rather than silently expanding scope.

## Doc-drift sweep findings

Beyond the two required docs, grepped the whole repo for `allow_with_warning` and found several
other live docs (not `logs/`, `tmp/`, `toolguard-memories/`, or `release-notes/`) with
now-incomplete EXHAUSTIVE value lists: `docs/permission-patterns.md` (the undecidable-fallback
floor summary), `technical-notes.md` (two spots -- the governing-principle update note and the
"Flagged defaults" section), and `skills/toolguard-security-audit/SKILL.md` (the JSON schema
comment for `context.takeover.no_match_fallback`). Fixed all four. Also updated
`docs/auto-mode.md` with an explicit warning against substituting `allow`/`allow_with_no_warnings`
for the page's `allow_with_warning` recommendation -- that page's entire safety argument is "the
warning gives you a reviewable trail," which `allow` silently defeats while looking like a
simpler version of the same setting; leaving this unsaid felt like the exact kind of "small,
individually reasonable" gap CLAUDE.md's own maintainer notes warn about. Also updated two spots
in `docs/install.md`'s Phase 10 guided-install runbook text for accuracy (both explicitly say
"the values are X/Y/Z" or "all three" -- now correctly scoped to "the values THIS FLOW
presents," noting `allow`/`allow_with_no_warnings` exist but are deliberately not offered in the
guided conversation).

`docs/agent-guides.md`, `README.md` had passing, non-exhaustive mentions of `allow_with_warning`
that remain accurate -- left unchanged.

## Sandbox demonstration

`no_match_fallback` (Bash allows only `git:*`; unmatched command `whoami`):

```
--- no_match_fallback=allow ---
verdict: allow
reason : Command does not match any allow patterns; allowed with no warning by no_match_fallback=allow (add an explicit rule to silence this)

--- no_match_fallback=allow_with_no_warnings ---
verdict: allow
reason : Command does not match any allow patterns; allowed with no warning by no_match_fallback=allow (add an explicit rule to silence this)

--- no_match_fallback=allow_with_warning ---
verdict: allow
reason : Command does not match any allow patterns; allowed with a warning by no_match_fallback=allow_with_warning (add an explicit rule to silence this)
```

`undecidable_fallback` (command `case $x in a) b;; esac`, grammar-undecidable):

```
--- undecidable_fallback=allow ---
verdict: allow
reason : Undecidable segment allowed with no warning by undecidable_fallback=allow (command did not parse; cannot safely decompose): case $x in a) b;; esac

--- undecidable_fallback=allow_with_no_warnings ---
verdict: allow
reason : Undecidable segment allowed with no warning by undecidable_fallback=allow (command did not parse; cannot safely decompose): case $x in a) b;; esac

--- undecidable_fallback=allow_with_warning ---
verdict: allow
reason : Undecidable segment allowed with a warning by undecidable_fallback=allow_with_warning (command did not parse; cannot safely decompose): case $x in a) b;; esac
```

`allow_with_no_warnings` resolves byte-for-byte identically to `allow` in both cases, confirming
the normalization. `allow_with_warning`'s reason is the only one claiming a warning.

## Test results

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .` -- **2070 tests, OK** (baseline 2039 + 31 new; 0 failures, 0
  errors). Ran this 5 times across the session as changes landed; always green.
- `uv run ruff format --check .` -- 134 files already formatted (clean).
- `uv run ruff check .` -- All checks passed.
- `uv run python tools/check_doc_links.py` -- All internal documentation links resolve, exit 0.
- `uv run ruff check --select F401` -- no unused imports.
- Manual scan of all changed production files for `async def`/`await`/`threading`/local
  imports -- none found.

## Logs (real logs/ directory)

The real `logs/toolguard-2026-08-02.md` line count went from 2993 (before the suite run) to
3049 (after) -- but this is NOT test leakage. `test/unit/_real_log_dir_guard.py` intercepts and
suppresses any write the test suite itself would make to the real log dir, and
`test_zz_real_log_dir_guard.py` (part of the 2070 passing tests) asserts that record is empty.
The +56 lines are from my OWN real Bash commands in this session (e.g. `cd`, `tail`) being
governed and logged by the actually-installed toolguard hook while I worked -- confirmed by
reading the tail of the file, which shows exactly those commands with today's timestamps. This
is normal, unavoidable, and unrelated to the test suite.

## Coverage against the spec's test list

- All five values parse/resolve for both settings: `test_configuration.py`
  (`TestResolvedNoMatchFallback`, `TestResolvedUndecidableFallback`).
- `allow_with_no_warnings` resolves identically to `allow`: same classes, plus
  `test_resolve.py::test_no_match_fallback_allow_with_no_warnings_alias_matches_allow` and
  sandbox demo above.
- Unrecognized value -> `ask`: pre-existing coverage, unaffected/still passing.
- `allow` allow verdict with NO warning-stream entry vs `allow_with_warning` WITH one:
  `test_hook.py::TestNoMatchFallbackThroughMain` (mocks `log_warning`, asserts called/not-called).
- Reason text for `allow` never claims a warning: asserted throughout (`assertIn("no warning",
  ...)`, `assertNotIn("allow_with_warning", ...)`).
- Undecidable floor treats `allow`/`allow_with_warning` identically:
  `test_compound.py::TestApplyUndecidableFloor` (new parametrized identity test) +
  `test_resolve.py`'s extended fallback-threading tests.
- Audit findings fire for all three allow-ish values, not ask/deny:
  `test_tools_takeover_audit.py` (existing `ask`/`deny` not-flagged tests + 4 new flagged tests).
- `warn_deny` still works for `no_match_fallback`, still rejected for `undecidable_fallback`:
  pre-existing coverage + new `test_warn_deny_is_not_honored_falls_back_to_ask`.

## Self-review

Ran `ruff format .` / `ruff check .` (clean), full suite after every meaningful change (5 runs,
always green), manual anti-pattern scan (no async/threading/local-imports introduced), unused
imports check (clean), and re-read every production diff for coherence before writing this
report.
