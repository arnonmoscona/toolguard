---
title: TOO-45 R3 second review-fix implementation report
type: note
permalink: toolguard/implementation/too-45-r3-second-review-fix-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

## Summary

Fixed all 5 findings from the blinded 29-mutation reviewer's report against R3's final state
(a session distinct from, and after, the earlier "R3 review-fix" pass that closed 6 findings
from two judges). Full suite green throughout (2321 tests at completion, up from 2314 at
session start -- +7: 6 new handler-wiring tests plus 1 new deny-ordering test). Verdict corpus
green (6/6, zero accepted prose differences), `architecture_fitness.py --guard` PASS (12/12
canaries), `corpus_build.py --verify` OK (0 differences, in-process 5389 cases + e2e 30 cases),
`check_doc_links.py` OK, ruff format/check clean.

Note: `git diff --stat` on the touched files includes the PRIOR session's already-uncommitted
work (nothing was committed between sessions) -- the numbers below describe only what I changed
this session.

## Item 1 -- production wiring pinned by nothing (the acceptance criterion)

Added two new test classes to `test/unit/test_hook.py`, both mocking only
`toolguard.hook.log_command` and driving the real handler functions with a real
`Configuration`/`ConfigLayer`/`Provenance`, so the whole resolve -> handler -> `_log_*_decision`
-> `log_command` chain executes for real:

- `TestHandleCommandToolAuditWiring` (drives `_handle_command_tool`): plain allow (`ls` ->
  `Bash(ls)`), plain deny (`rm -rf /tmp/x` -> `Bash(rm -rf *)`), escape-hatch allow
  (`python -c "print(1)"` under `undecidable_fallback=allow_with_warning`), escape-hatch deny
  (`python -c "print(1)" && rm foo` under `undecidable_fallback=deny`, second leaf genuinely
  denied by `Bash(rm *)` -- see item 2 for why this exact shape was needed).
- `TestHandleFilePathToolAuditWiring` (drives `_handle_file_path_tool`): file-path allow
  (`Read(/tmp/x/**)`), file-path deny (`Read(/secrets/**)`).

All assert EXACT `matched_rule`/`provenance` (or `violated_rules`/`provenance`) values, not
merely that logging happened.

**Acceptance criterion, both results:**

1. Applied the argument swap at `hook.py`'s `_log_allowed_command` call site in
   `_handle_command_tool` (swapped `result.matched_rule` and
   `_provenance_brief(result.provenance)`). Full suite: **1 failure**
   (`TestHandleCommandToolAuditWiring.test_plain_allow_logs_the_exact_matched_rule_and_provenance`).
   Reverted (`diff` against pre-mutation backup: identical). Suite back to 2321 OK.
2. Removed the allow-branch provenance suppression guard (`single_provenance = provenance if
   single_matched_rule == matched_rule else None` -> `single_provenance = provenance`). Full
   suite: **1 failure**
   (`TestHandleCommandToolAuditWiring.test_escape_hatch_allow_logs_placeholder_and_no_provenance`).
   Reverted (diff identical to pre-mutation backup). Suite back to 2321 OK.

Both mutations are now caught. Did not separately mutate `hook.py:989` (deny-branch
suppression) or the file-path lines per the acceptance criterion's explicit scope (only the two
listed), but the new `test_escape_hatch_deny_logs_placeholder_and_no_provenance` and the two
file-path tests exercise those code paths with real (non-degenerate) values, so they would
catch the equivalent mutations too -- not independently re-verified by hand, since only the two
above were asked for.

## Item 2 -- escape-hatch suppression reachable and unpinned

Probed `resolve_bash_permission_detailed()` directly (read-only) before writing assertions:

- `python -c "print(1)"` under `allow_with_warning`: `matched_rule='python *'`,
  `provenance='project: /p/toolguard_hook.toml'` (both REAL, at the raw `BashResolution`
  level) -- confirms the leaf's pre-floor decision ('allow', from the genuine `python *` stub
  match) equals the final decision, so `_deciding_sub_match` cannot separate them structurally.
- `python -c "print(1)" && rm foo` under `deny` with `deny=["Bash(rm *)"]`: compound decision
  `'deny'`, reason names the ESCAPE HATCH (python leaf, picked first by strictest-wins), but
  `matched_rule='rm *'`/provenance are the OTHER leaf's real deny match (`_deciding_sub_match`
  picks whichever `SubMatch` agrees with the final decision -- here that's `rm foo`, not the
  escape-hatch leaf). This is why the single-leaf deny case alone (already covered by an
  existing test, `TestAuditLogViolatedRuleNeverFabricated`) wouldn't have exercised the
  hook.py:989 guard: for a lone escape-hatch leaf, `BashResolution.matched_rule` is ALREADY
  `None` at the raw field, so nothing to leak. The two-leaf shape with a genuine second deny
  rule was necessary to get a REAL, non-None provenance flowing into the suppression point.

Both scenarios pinned in `TestHandleCommandToolAuditWiring` (see item 1): matched_rule is the
placeholder, `provenance` kwarg is `None` in both cases.

## Item 3 -- false docstring invariant

`resolve.py::BashResolution.matched_rule`/`provenance` Attributes entries: added the
escape-hatch caveat (pre-floor decision can equal final decision, in which case the field holds
the real-but-misleading stub match; correctness depends on `hook.py`'s reason-based guard, which
any new consumer must replicate).

`resolve.py::_deciding_sub_match`'s docstring: added a paragraph after the existing (correct,
kept) decision-inequality example, explicitly naming it as "the case where inequality saves
this function" and stating that it does NOT generalise to the decision-equality case (single-leaf
`allow_with_warning`/`allow`), where the function returns the real, misleading `SubMatch` and
relies on the same downstream `hook.py` guard.

## Item 4 -- false documentation claims

`toolguard/tools/log_harvest.py`'s module docstring and `docs/architecture.md` (both the
pre-example paragraph and the post-example paragraph) corrected to state: single-leaf entries
get a separate Provenance field; compound per-sub-command entries do NOT -- their provenance
(when available) stays folded into Matched Rule in the pre-R3 bracketed format
(`git *  [project: /path]`), because per-sub-command provenance was never threaded through
`_log_allowed_command`'s compound branch.

## Item 5 -- two smaller

(a) `log_writer.py::_render_markdown_entry`: moved the `Provenance` line to render AFTER
`Violated Rules` instead of between `Matched Rule` and `Violated Rules`, so a deny's Provenance
no longer sits above the field it describes (allow ordering is unaffected -- `Violated Rules`
never renders for an allow). Added `test_provenance_ordering_in_markdown_for_deny` as a sibling
test to the existing allow-only `test_provenance_ordering_in_markdown` (kept the existing test
unmodified -- one BDD scenario per test method, per the testing convention, rather than
cramming both into one). Pins Violated Rules < Provenance < Agent for a deny.

(b) `hook.py::_parse_compound_match_details`'s docstring: replaced the closing "remains the
source of truth" claim (which implicitly denied any viable alternative) with an honest
statement that `compound.py:722`'s `_combine_strictest` already builds the same determination
as a `match_details` list before joining it into the reason string this function splits back
apart, that consuming the list directly is a viable follow-up NOT done here, and why (still
parses leaf reasons at `compound.py:738-747`, so it moves rather than removes the parse; fully
removing it needs `resolve_one`'s 3-tuple contract widened, out of scope -- R1). Kept the
ask-floor-leaf negative-result bullets unchanged (per instruction) since they document a real,
distinct mechanism, not the overstated claim.

## Files changed this session

Production: `toolguard/hook.py` (1 docstring), `toolguard/resolve.py` (2 docstrings),
`toolguard/log_writer.py` (1 field-order fix + 1 comment), `toolguard/tools/log_harvest.py` (1
doc correction). Docs: `docs/architecture.md` (2 paragraphs). Tests:
`test/unit/test_hook.py` (2 new imports lines, 2 new test classes / 6 new tests),
`test/unit/test_log_writer.py` (1 new test method).

No existing test's BEHAVIOR was modified -- `test_provenance_ordering_in_markdown` (allow) is
untouched; a new sibling test covers the deny ordering.

## Corpus / prose

Zero `TOOLGUARD_CORPUS_ACCEPT_PROSE` uses needed -- `corpus_build.py --verify` reported zero
differences throughout, checked after every meaningful edit.

## Self-review / anti-pattern scan

Grepped all touched files for `async def`, `threading`, and function-local imports: none
introduced (the one local import in `hook.py` at `_resolve_event` is the pre-existing,
documented circular-import exception, untouched by me). `uv run ruff format .` and
`uv run ruff check .` both clean. Full suite 2321/2321 OK. No git write operations performed
(mutations were applied via file backup/restore with `cp`, not committed, and diffed against
the backup to confirm exact reversion).

## Scope check

7 non-trivial files touched (4 production, 1 doc, 2 test), 0 new files created -- well within
the scope-inflation guard.

## Elapsed time / cost (rough estimate)

- Phase 1 (reading resume/prior-session notes, all 5 findings' cited source locations, tracing
  the escape-hatch mechanism through resolve.py/compound.py/hook.py, one read-only probe
  script): ~19:55 -> ~20:12, ~17 min. Est. cost: ~$0.9 (heavy reading across 5 files plus a
  probe).
- Phase 2/3 interleaved (all docstring/doc/ordering fixes, the 6 new tests, mutation testing
  with revert-and-verify x2, full invariant suite x6): ~20:12 -> ~20:31, ~19 min. Est. cost:
  ~$1.0 (many edits and test runs, moderate re-reads for verification).
- Phase 4 (this report, memory writes, IDE opens): ~20:31 -> ~20:35, ~4 min. Est. cost: ~$0.2.
- **Total elapsed**: ~40 min. **Total estimated cost**: ~$2.1 (Sonnet 5 pricing, rough
  token-count based estimate).
