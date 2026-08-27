---
title: 18-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/18-estimate-predictions
---

# TOO-45 proposed-ticket 18 — touch-set prediction (BLINDED)

## Reasoning

I split the problem into three cost centres, because the ticket itself draws that line explicitly.

**1. The defect site.** The bug is pinned to one function in one module — `match_command` in
`toolguard/permissions.py`, specifically the `":" in pattern_normalized` branch around line 163,
where a trailing `*` gets glued onto the last token with no boundary check. The ticket's own "Fix
direction" section describes a same-module, same-function change: apply the boundary rule that
line 158 already applies to the first token, to the last token too. That keeps the core fix
extremely localised — one module, a handful of lines — even though line-count is a poor proxy for
importance here. The ticket also flags a specific comment (lines 146-148) as actively misleading
and "worth rewriting when the code is fixed," so I count that as part of the same file's diff
rather than a separate cost centre.

**2. The matcher's own test coverage.** The ticket is explicit that `test_permissions.py` and
`test_patterns.py` are "the two files that exist to test matching" and that neither currently
"says a word about" the over-match — that absence is presented as the coverage gap the fix must
close, with a "Test obligation" section calling for the brute-force differential to become a real
test. I weight `test_permissions.py` higher than `test_patterns.py` because the defect lives in
`permissions.py` and the worked examples (`git commit:*`, `git log:*`, `ls:*`) are exactly its
domain; `patterns.py` is described as covering GLOB/NATIVE-style matching, adjacent but not the
same code path.

**3. Downstream breakage in analyzer/consolidation code that doesn't live near the defect.** This
is the part the ticket spends the most space on, and it is the part I was told is scored
separately, so I reasoned about it as its own centre rather than folding it into "the fix touches
whatever it touches." The ticket reports two independent measurement runs that both found 20
failing tests, agree that none of them are in `test_permissions.py` or `test_patterns.py`, and
otherwise **disagree with each other** on the file breakdown. One data point is nailed down
precisely (a third, targeted run): `test_api.py::TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command`
fails because a hard-deny carve-out (`Bash(rm -rf /tmp:*)`) is only exempting because of the same
glued-`*` defect. Beyond that anchor point, I treated the two runs' file lists as competing
hypotheses to rank by corroboration rather than a single ground truth: files named in both runs
(the consolidation/maintenance tier) get higher confidence than files named in only one. I also
used the ticket's own structural argument — `_static_prefix_of`, `prefixes_overlap`, and "the
golden corpus" were "built against a matcher that behaves this way," and a named test
(`test_tools_consolidate.test_consolidation_preserves_prefix_extension_commands`) is called out by
name as encoding the bug as intended behaviour — as corroboration independent of either run's raw
file list.

I deliberately did **not** try to guess a production-code fix inside the consolidation/maintenance
modules themselves. The ticket frames all 20 downstream failures as *indirect* — detected through
effect on higher-level analyzers' output, not through any assertion in the matcher's own tests —
and explicitly says "the matcher's own tests do not notice." That reads to me as: the analyzers'
*logic* is likely unchanged, and it's their *test fixtures/expectations* (and possibly a
regenerated verdict corpus) that will need to move to match the now-correct matcher. So my
downstream predictions lean towards test files, with the production modules they exercise
(`consolidate.py`, `redundancy.py`, `maintenance.py`, `edit_proposal.py`) carrying much lower
confidence and appearing only if a golden expectation turns out to be baked into non-test code.

## Production — modified

| file | reason | confidence |
|---|---|---|
| `toolguard/permissions.py` | Defect site: `match_command`'s `:`-branch glues `*` onto the last token with no boundary check (ticket pinpoints line ~163); fix applies the same boundary rule used at line 158. Also the misleading comment at lines 146-148 the ticket calls out for rewriting. | high |
| `toolguard/tools/pattern_overlap.py` | Ticket says `prefixes_overlap`'s docstring ("exactly when...") is currently false and can "go back to stating it" once `match_command` matches on token sequences — explicitly framed as same-ticket-or-immediately-after. | low-medium |
| `toolguard/tools/uninstall_readiness.py` | Module docstring and `_SEED_SELF_PERMS_HELP` currently claim seeded patterns are "not a wildcard grant," which is false pre-fix — but becomes true once the matcher is fixed, so this text may need no edit at all. Listed for completeness, not because I expect it. | low |

## Production — added

None expected. The ticket's fix direction is a same-function correction, not a new mechanism or module.

## Test — modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_permissions.py` | Ticket's explicit "Test obligation": the brute-force differential (`git commit:*` vs `git commit-tree`, etc.) should become a test here — this is the matcher's primary test file and the ticket calls out its current silence on the bug by name. | high |
| `test/unit/test_patterns.py` | Named alongside test_permissions.py as one of "the two files that exist to test matching," also currently silent on the defect. | medium |
| `test/unit/test_tools_consolidate.py` | Named test `test_consolidation_preserves_prefix_extension_commands` is explicitly called out as encoding the over-match as intended behaviour in its Given/Then — ticket says whoever fixes this must not treat that docstring as a contract. Also the larger share (10) in one of the two disagreeing failure-count runs. | medium-high |
| `test/unit/test_tools_maintenance.py` | Named in both disagreeing runs (5 in run A, 9 in run B) — the only file with that cross-run agreement besides the test_api anchor. | medium-high |
| `test/unit/test_api.py` | Precisely located by a third, targeted run: `TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command` depends directly on the glued-`*` defect for its carve-out exemption. | high |
| `test/unit/test_tools_redundancy.py` | Named only in run A's breakdown; not corroborated by run B. | low-medium |
| `test/unit/test_tools_edit_proposal.py` | Named only in run A's breakdown; not corroborated by run B. | low-medium |
| `test/unit/test_verdict_corpus.py` | Named only in run A's breakdown, but the ticket separately states "Replay the verdict corpus before and after" and calls this file "a HARD tier that must never be [broken silently]" — plausible even without run B's corroboration. | low-medium |

## Test — added

None expected as new *files* — I expect the "Test obligation" differential to land inside the
existing `test_permissions.py` (and possibly `test_patterns.py`), not a new test module, since the
ticket frames it as filling a gap in files that already exist for this purpose.

## Deleted

None expected.

## Concentration set

`test/unit/test_permissions.py` and `toolguard/permissions.py` together, in that order. The fix
itself in `permissions.py` is described as a small, localised boundary-rule change (probably
under ~15 changed lines plus the comment rewrite), but the ticket asks for a comprehensive
differential test to be written from scratch covering the mid-pattern, any-colon, and
inconsistent-boundary cases plus the existing correct cases — that is likely to be the single
largest diff in the change, by line count. `test/unit/test_tools_consolidate.py` is a secondary
concentration point if the named docstring-as-bug test needs a real rewrite rather than a small
edit.

## Downstream prediction (SEPARATE — this is the part that matters)

The ticket is explicit that two independent measurements of the 20-test blast radius disagreed
with each other, and that this indirection (not the defect site) is where the real cost lives.
Ranking by cross-run corroboration and by explicit named evidence in the ticket text, independent
of either run's raw counts:

**Highest confidence (corroborated by a third, targeted run, not just the two disagreeing ones):**
- `test/unit/test_api.py` — exact test named: `TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command`.

**High confidence (named in both disagreeing runs, or named directly in ticket prose as encoding the bug):**
- `test/unit/test_tools_consolidate.py` — named test explicitly documents the over-match as intended.
- `test/unit/test_tools_maintenance.py` — appears in both run A and run B's breakdowns.

**Medium confidence (named in only one run, unconfirmed by the other):**
- `test/unit/test_tools_redundancy.py` — run A only.
- `test/unit/test_tools_edit_proposal.py` — run A only.
- `test/unit/test_verdict_corpus.py` — run A only, but independently plausible given the ticket's
  own instruction to replay the verdict corpus before/after and its description of a "corpus
  regeneration" as a necessary follow-on step.

**Predicted explicitly NOT touched, despite surface appearance:**
- `test/unit/test_hard_deny.py` — the ticket explicitly identifies run A's "test_hard_deny" entry
  as a **name collision** with `test_api.py`'s `test_hard_deny_carve_out_exempts_command`, and
  separately proves every pattern in `test_hard_deny.py` is colon-free, so it never reaches the
  buggy branch. I'm predicting this file is clean, which is the opposite of what a naive reading
  of run A's label would suggest.

**Uncertain / not predicted:** whether the fix requires production-code changes in
`toolguard/tools/consolidate.py`, `toolguard/tools/redundancy.py`, `toolguard/tools/maintenance.py`,
or `toolguard/tools/edit_proposal.py` themselves, versus only their tests' fixtures/expectations
moving. The ticket's framing ("the matcher's own tests do not notice... indirect... through effect
on higher-level analysers") reads to me as evidence the analyzer *logic* is unaffected and only
*expected outputs* shift, but I could not verify this without reading the modules, which was out
of scope for this estimate.