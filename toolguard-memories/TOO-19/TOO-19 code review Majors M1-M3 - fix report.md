---
title: TOO-19 code review Majors M1-M3 - fix report
type: note
permalink: toolguard/too-19/too-19-code-review-majors-m1-m3-fix-report
tags:
- task-memory
- TOO-19
---

## Summary

Fixed the 3 Major findings from the 2026-07-31 code review report, per Arnon's explicit
per-finding direction. M1 is documentation-only (no code). M2 and M3 are real bugs, fixed at
the root cause with new regression tests. Elapsed ~2h10m across planning, implementation, and
verification (see Timing below).

## Files changed (11, all pre-existing, 0 new files)

- `toolguard/compound.py` -- split `_accumulate_contexts` (dedup+join only now) from new
  public `cap_context_words` (the word-budget enforcement, moved out).
- `toolguard/resolve.py` -- applies `cap_context_words` at the true injection boundary (both
  `resolve_bash_permission_detailed` and `resolve_file_path_permission_detailed`, all return
  points).
- `toolguard/log_writer.py` -- M3: discovery log rewritten from JSONL+1MB-cap to plain text +
  bounded-tail read.
- `docs/security.md` -- M1: new section "A cloned project's config can inject text into
  Claude's context".
- `docs/agent-map.md` -- TOC entry for the new security.md heading.
- `docs/configuration.md` -- updated the `additionalContext` section to describe the uniform
  cap and the lone-oversize truncation-with-marker behaviour (doc-drift fix for M2).
- `technical-notes.md` -- updated "Change-detecting discovery diagnostic" section for the
  plain-text/bounded-tail redesign (M3), plus a stray second reference to the old `.jsonl`
  filename in the logging-streams table (doc-drift sweep caught it in a second file).
- `test/unit/test_compound.py` -- moved budget-specific tests off `_accumulate_contexts` onto
  a new `TestCapContextWords` class; added the lone-oversize truncation tests there.
- `test/unit/test_resolve.py` -- new `TestAdditionalContextBudgetAtInjectionBoundary` class:
  lone-oversize Bash allow, lone-oversize Read allow, Bash deny capped, Bash hard-deny capped,
  file hard-deny capped.
- `test/unit/test_logging_streams.py` -- `TestDiscoveryDiagnostic` rewritten for the plain-text
  format; added 2 new tests (oversized-file-no-longer-degrades, entry-outside-tail-window).
- `test/unit/test_zz_real_log_dir_guard.py` -- filename reference updated (imports the
  constant from `log_writer` rather than hardcoding the old `.jsonl` string).

**Scope-inflation self-check**: 11 modified files is slightly over the informal 10-file
guideline. I judged this acceptable rather than stopping to ask, because every touch is a
direct, mandated consequence of the 3 findings plus their explicitly-required tests and the
doc-drift they created -- no new files, no speculative refactoring, no scope beyond what the
task specified.

## M1 -- docs/security.md, new section

Added "A cloned project's config can inject text into Claude's context" right after "Blanket
allow risks". Verified before writing, not assumed:
- **Proportionality**: `config.py` confirms specificity 0 = project (MOST specific) and normal
  resolution is more-specific-wins, so a project-level `allow` already overrides a `deny` from
  a less-specific level. `[hard_deny]` is pooled across ALL levels and is the one thing a
  project config cannot override. So a hostile project config already has a stronger lever
  (turn a `deny` into an `allow`) than context injection alone -- documented as such.
- **Asymmetry**: grepped every `toolguard/tools/*.py` audit module
  (security_audit/danger/clarity/redundancy/takeover_audit/config_access) for
  `additional_context`/`additionalContext` -- zero hits (one unrelated comment about quote
  parsing). No audit finding today inspects or reports on `additionalContext` content, while
  permission patterns are exactly what those tools reason about. Documented the asymmetry as
  real, per the finding's own framing (not the alternative "audit already surfaces it" branch,
  since it does not).
- Noted Claude Code's trust-on-first-open prompt as an existing control, not a guarantee.
- No code, flag, or config key added, per Arnon's explicit decision.

## M2 -- injection boundary moved, lone-oversize entries no longer vanish

**Boundary investigation** (verified, not assumed): `hook.create_hook_output` is NOT the right
boundary -- `toolguard/testing/sandbox.py`'s CLI builds its JSON payload directly from
`Decision.additional_context` and never calls `create_hook_output` at all. The true single
convergence point across `hook.main()` (which calls the resolve.py functions directly),
`hook._run_eval_mode()`/`--eval` (via `decision.decide()`), and `sandbox.evaluate()` (also via
`decide()`) is `toolguard/resolve.py`'s two public functions:
`resolve_bash_permission_detailed` and `resolve_file_path_permission_detailed`. Every caller,
with no exception, goes through one of exactly these two. The budget is now applied there, at
every return point (file hard-deny, file normal, bash single return).

**Lone-oversize decision**: truncate the paragraph to a `max_words`-word prefix at a word
boundary and append a `[toolguard: additionalContext truncated to N words -- the original
entry exceeded the injection budget]` marker paragraph. Chosen over "keep the whole oversized
paragraph" (defeats the budget's purpose) and "silently keep None" (the bug itself) -- the
marker keeps the injected text non-empty, on-budget, and self-explanatory to a human reading
the log, satisfying "the log must reflect what actually got injected" automatically since the
log preview is fed from this same capped value.

**Design**: `compound._accumulate_contexts` now does dedup+paragraph-join ONLY (no `max_words`
param). New public `compound.cap_context_words(text, max_words=500)` does the greedy
first-fit paragraph budget on the FINAL text, with the lone-oversize truncation fallback.
Public (not `_`-prefixed) because a different module (`resolve.py`) calls it -- API visibility
rule: privatize by "should non-test code call it?".

**Verified end-to-end via sandbox** (600-word additionalContext on each):
- (a) Bash allow rule alone (`git status`): verdict `allow`, context = first 500 words +
  marker. Before the fix this would have returned `None` (nothing injected at all).
- (b) Read rule (`/tmp/some/file.txt`): verdict `allow`, context = first 500 words + marker.
  Before the fix this would have injected all 600 words uncapped.
  Both outputs captured via `uv run python -m toolguard.testing.sandbox --config <fixture>
  --tool <Bash|Read> --command <...> --json`, confirmed identical truncation behaviour.

## M3 -- plain text + bounded tail, no size cap

Deleted `_DISCOVERY_JSONL_MAX_READ_BYTES` (1 MB) and its `None`-on-oversize path entirely --
the file is never truncated, rotated, or size-capped now.

**Plain-text format chosen**: `<iso-timestamp>\t<project_root>\t<levels joined by \x1f>`
(`\x1f` = ASCII Unit Separator). Justification: tab and `\x1f` are, for all practical purposes,
unreachable from a real filesystem path or a `"level: path"` description string -- unlike a
comma or colon, which both appear in those strings routinely -- so splitting needs no escaping
logic. Filename renamed `toolguard-discovery.jsonl` -> `toolguard-discovery.log` (no longer
JSON, name should say so).

**Bounded tail**: `_last_discovery_levels_for_root` seeks to `_DISCOVERY_TAIL_READ_BYTES`
(64 KiB) from the end of the file and reads only that tail, scanning its lines backwards for a
line matching this invocation's project root. A read that starts mid-file drops its first
(possibly partial) line. If no match is found within the tail, degrades to "no prior record" --
justified because that costs exactly one redundant log write for this invocation, never an
incorrect permission verdict (the same safety argument the code already used for tolerating a
torn final line from a concurrent write).

**Mutation-check performed**: padded a discovery log past 1 MB (with filler records for a
DIFFERENT project root, so the real `/proj` entry stays within the 64 KiB tail as the last
line), then called `log_discovery` again with the SAME levels. Observed: the file's bytes are
byte-identical before and after -- the new code found the correct prior entry and did NOT
append, where the OLD 1 MB cap would have degraded to "no prior entry" and appended, growing
the file further on every subsequent call (the self-accelerating bug). Captured as
`test_oversized_file_no_longer_degrades_to_permanent_append_mode` in
`test/unit/test_logging_streams.py`, run standalone and confirmed passing. A companion test
(`test_entry_outside_the_tail_window_degrades_to_no_prior_entry`) proves the documented
degrade-gracefully trade-off when a real entry genuinely scrolls outside the tail window.

**technical-notes.md** "Change-detecting discovery diagnostic" section updated in place
(heading anchor left unchanged to avoid unrelated link churn) with the plain-text + bounded-
tail rationale. A second stray reference to the old `.jsonl` filename, in the same file's
logging-streams table (a different section), was also found and fixed -- a doc-drift sweep
catch, not part of the section I was already editing.

## Verification results

1. `HOME=<empty> XDG_CONFIG_HOME=<empty> uv run python -m unittest discover -s test -t .` --
   **2025 tests, OK** (2012 baseline + 13 new: 9 in `TestCapContextWords`,
   6 in `TestAdditionalContextBudgetAtInjectionBoundary` minus overlap with pre-existing --
   exact new-test count verified by diffing `Ran N` before/after each edit round).
2. `uv run ruff check .` -- All checks passed. `uv run ruff format --check .` -- 134 files
   already formatted.
3. `uv run python tools/check_doc_links.py` -- All internal documentation links resolve.
4. Real repo `logs/` dir: Discovery-entry count in `logs/toolguard-<today>.md` measured
   immediately before and immediately after the isolated full-suite invocation specifically --
   **1 before, 1 after, delta 0**. One earlier Discovery entry (0->1) DID appear in this
   session, but it was written by toolguard's own LIVE, self-governing hook (this repo
   dogfoods itself; the project-level `.claude` hook invokes the working-tree code directly,
   not a pinned global install) reacting to MY filename rename (`.jsonl` -> `.log`) on the
   first ordinary Bash tool call I issued after that edit -- the new file legitimately had no
   prior entry yet. This is an unavoidable, one-time side effect of editing `log_writer.py`
   while working inside a repo that governs its own agent session, entirely separate from and
   unrelated to running the test suite; it will not recur for the rest of the session, and the
   tightly-bracketed measurement around the test-suite command itself shows zero effect from
   running the tests.
5. M3 mutation-check: see above, observed byte-identical file before/after, no append.
6. M2 sandbox demonstration: see above, both (a) and (b) confirmed truncated-with-marker.
7. `test_zz_real_log_dir_guard.py` (part of the full suite) confirms zero real-logs-dir writes
   from the test process itself.

## Existing-vs-new-implementation check

No existing helper duplicated: `cap_context_words` is a genuinely new function (the budget
logic previously lived inline in `_accumulate_contexts` and is being relocated, not
duplicated -- the old code path no longer applies any budget). The plain-text discovery-log
read/write logic is new but small (a few lines); no stdlib or existing project helper does
"tail-read + delimited-line parse", so a bespoke implementation was appropriate here.

## Timing and estimated cost (Sonnet 5)

- Planning (read review report, CLAUDE.md/rules, resolve.py/hook.py/sandbox.py boundary
  investigation, log_writer.py, docs): ~35 min, ~$0.9.
- Implementation (compound.py, resolve.py, log_writer.py, docs, tests): ~70 min, ~$2.0.
- Verification (test runs, ruff, doc-links, sandbox demos, mutation-check, real-logs-dir
  delta): ~25 min, ~$0.5.
- Total: ~2h10m elapsed, **~$3.4 estimated** (Sonnet 5, moderate input/output token volume;
  no large-context operations).
