---
title: TOO-45 R1e finishing pass coder task recall
type: note
permalink: toolguard/too-45/too-45-r1e-finishing-pass-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Finish TOO-45 step R1e in /home/arnon/projects/toolguard on branch too-45. Full brief was at
`/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1e_finish_brief.md`
(captured in full below).

A previous agent did most of R1e and was killed mid-verification (85 min with no filesystem write).
Its work is in the tree and largely GOOD: audit-trail fix landed, compound.py's six bare verdict
tuples converted, corpus confirms verdicts and hook output unchanged. DO NOT restart from scratch,
DO NOT revert its work.

### What's already done and verified working (per brief)
- `_log_allowed_command` reads `verdict.sub_matches` (one `UnitVerdict` per sub-command) instead of
  regex-parsing reason prose. `_parse_compound_match_details` and `_COMPOUND_MATCH_PATTERN` gone.
- R3's prose-parse sites dropped 2 -> 1 (hook.py one retired).
- compound.py's six bare verdict-tuple returns converted: bare tuples 10 -> 4.
- Corpus reports verdicts and hook output UNCHANGED.
- Three tuple-unpacking call sites in test/unit/test_compound.py (TestAskFloorReasonTruncation)
  already fixed by the orchestrator (Claude Code main agent) -- do not redo.
- Suite state at handoff: 2,349 with 4 failures, 0 errors.

### Defect 1 (most important): 5 corpus cases regress matched_rule/provenance to None
All involve a compound with an undecidable segment or ask-floor leaf:
- [realistic] Bash("grep -n 'ls && python -c' .../test_resolve.py").provenance -> None
- [realistic] Bash("grep -n 'ls && python -c' .../test_resolve.py").matched_rule -> None (was 'grep *')
- [undecidable_allow] Bash('diff <(cat a) <(cat b) && ls -la').provenance -> None
- [undecidable_allow] Bash('diff <(cat a) <(cat b) && ls -la').matched_rule -> None (was 'ls *')
- [undecidable_allow] Bash('ls -la | diff - <(pwd)').matched_rule -> None (was 'ls *')

Root cause per brief: sub_matches does not hold what the prose used to recover for ask-floor
leaves. Must close the gap so engine records matched_rule/provenance for these leaves, not
reconstruct in the logger. Must prove via corpus --verify: zero None-regressions AND verdicts
still unchanged. If truly impossible for some case, state precisely which/why with execution
evidence -- don't assume/acknowledge away.

### Defect 2: LeafOutcome vs UnitVerdict duplication
`--predicates` reports 2 runtime verdict types: RuntimeVerdict and new LeafOutcome (compound.py:267).
Gate requires exactly 1. LeafOutcome carries (decision, reason, additional_context, fallback_kind).
UnitVerdict carries (sub_command, decision, matched_rule, provenance). Both describe one leaf --
duplication R1 exists to remove. Merge into UnitVerdict (natural home, right name); give it
LeafOutcome's fields. Where a construction site has no sub_command yet, make that explicit rather
than inventing a parallel type. Read LeafOutcome's docstring first -- its argument is sound about
RuntimeVerdict (fallback_kind is per-leaf tri-state vs RuntimeVerdict.fallback_warning aggregate
boolean) but beside the point about UnitVerdict (also per-leaf). If genuinely can't merge after
real effort, stop and report the argument+evidence rather than shipping two.

### Defect 3: three stale real-tree pins in tests need updating to post-R1e reality (not weakened
to vacuity):
- TestClassifyVerdictAltitudes.test_real_tree_has_exactly_one_runtime_verdict_type
- TestComputePredicates.test_r1_gate_fails_on_the_real_tree_because_of_bare_verdict_tuples
- TestFindBareVerdictTuples.test_real_tree_flags_all_six_compound_functions (should still pin the
  4 remaining bare tuples in permissions.py/resolve.py, not be deleted)
Update Given/When/Then docstrings in same edit.

### Prove it, don't assert it
Re-run the measurement that found 813/975 (83%) compound allow cases under-logging and 1,943
sub-commands with no audit entry -- report new numbers, zero expected, explain if not zero. Also
confirm no logged matched_rule carries stray trailing ']' (79 instances before fix).

### Acceptance commands (must paste real output)
```
uv run python -m unittest discover -s test -t .           # expect OK
uv run python tools/corpus_build.py --verify              # verdicts unchanged AND zero None-regressions
uv run python tools/architecture_fitness.py --guard       # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates  # runtime verdict types back to 1; bare tuples 4
uv run ruff format . && uv run ruff check --no-cache .
```
Report enrichment footprint before/after (currently 9 coupled files / 53 occurrences).

### Hard rules
1. NEVER git checkout/restore/stash/reset or any git write -- denied by rule, hangs. Read-only git
   fine. Backup original bytes to
   `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1e-finish-backups/`,
   restore by copy + sha256sum verify.
2. Report progress in transcript as you go, avoid long silent stretches.
3. Tree has substantial UNCOMMITTED work spanning seven prior stages. Do not disturb, do not commit.
4. Do not copy the repository. Do not edit anything outside it.
5. All bash parsing through PEG grammar -- never hand-roll parsing of command text.
6. uv run python never bare python. unittest not pytest. Always ruff check --no-cache.
7. No local imports, no async, no threading. Docstrings terse.

### Report location
basic-memory project toolguard, note `TOO-45/TOO-45 R1e finishing pass report.md`, tagged
task-memory + TOO-45. Lead with the five restored records and under-logging before/after. No
hard-wrapped paragraphs.

## Clarifications from discussion
(none yet -- proceeding per brief, auto-mode active, bias toward proceeding without stopping to ask)
