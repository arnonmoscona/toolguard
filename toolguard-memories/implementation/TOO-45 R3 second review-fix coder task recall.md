---
title: TOO-45 R3 second review-fix coder task recall
type: note
permalink: toolguard/implementation/too-45-r3-second-review-fix-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Ticket / context

TOO-45, branch `too-45`, project toolguard. A BLINDED reviewer ran 29 mutations against R3's
FINAL state (after the earlier "R3 review-fix" pass already closed 6 findings from two
judges). 5 new findings, all defects introduced by R3 itself. Full task spec from the parent
agent, condensed below.

## Findings to fix

1. **Highest value -- production wiring pinned by nothing**: `grep -rn "_handle_command_tool\|
   _handle_file_path_tool" test/` returned zero hits. Every test drove `_log_allowed_command`/
   `_log_non_allow_decision` directly with hand-passed `matched_rule`. 6 mutations survive:
   argument swap at `hook.py:1146` (matched_rule/provenance), pass `None, None`, remove the
   allow-branch provenance suppression (`hook.py:598`), remove the deny-branch suppression
   (`hook.py:989`), file-path allow logs no provenance (`hook.py:1056-1057`), file-path deny
   passes no provenance (`hook.py:1068`). **Acceptance criterion**: apply the argument swap at
   `hook.py:1146` myself, confirm suite FAILS, revert, confirm green; same for removing the
   allow-branch suppression at `hook.py:598`. Report both results.
2. **Escape-hatch suppression reachable and unpinned**: `python -c "print(1)"` under
   `undecidable_fallback=allow_with_warning` yields raw `matched_rule='python *'` and a REAL
   provenance at source (verified). Add a test asserting the log records the placeholder for
   `matched_rule` and NO Provenance field. Same for the deny side (`python -c "print(1)" &&
   rm foo` under `undecidable_fallback=deny`).
3. **`BashResolution.matched_rule`'s docstring is FALSE**: claims `None` when there's no single
   decider -- false under the escape hatch when the leaf's pre-floor decision equals the final
   decision (the misleading real stub match survives). Safe only because `hook.py` re-applies
   the prose guard downstream. Fix the docstring on `matched_rule` AND `provenance`, and on
   `_deciding_sub_match` (resolve.py:616ish), which illustrates the mechanism only with the ASK
   floor (the one case where decision-inequality saves it) and wrongly generalises.
4. **Two false doc claims**: `log_harvest.py:25` and `docs/architecture.md:317` both say
   provenance "is never folded back into Matched Rule/Violated Rules text" -- false for every
   COMPOUND entry (matched_rule keeps the old bracketed `pattern  [prov]` format there, no
   separate Provenance field). Correct both.
5. **Two smaller**: (a) `log_writer.py:354` emits Provenance right after Matched Rule, which for
   a deny puts it ABOVE Violated Rules. Move it after Violated Rules; extend
   `test_provenance_ordering_in_markdown` to pin deny ordering too (currently pins only allow).
   (b) `hook.py:473`'s (`_parse_compound_match_details`) docstring says the reason string
   "remains the source of truth" but `compound.py:722` already builds `match_details` as a
   LIST before joining it into that string -- returning the list is a viable, undone
   conversion. Do NOT do the conversion (building the list still parses leaf reasons; removing
   that needs `resolve_one`'s contract widened -- R1 scope). Just make the docstring honest and
   trim the now-refuted claim.

## Out of scope

The compound-path list conversion itself. The `_reason_suffix_or_placeholder` /
`_matched_rule_for_single_command` collapse. Any signature narrowing. Anything in
`Configuration`.

## Invariants

After every meaningful edit: `uv run python -m unittest test.unit.test_verdict_corpus`. Any
`permissionDecision` change = revert. Before finishing: full suite, `architecture_fitness.py
--guard`, `corpus_build.py --verify`, `check_doc_links.py`, `ruff format . && ruff check .`.

## Conventions

`uv run python` never bare python; unittest not pytest; stdlib only; no async/threading/local
imports; may ADD/MODIFY tests whose pinned code changed (list each); no git write ops; nothing
under `logs/`, `.env`, permission config, or outside repo. Do NOT touch
`test/verdict_corpus/`, `tools/corpus_build.py`, `tools/architecture_fitness.py`.

## State at session start

`git status` showed `hook.py`, `resolve.py`, `log_writer.py`, `log_harvest.py`,
`docs/architecture.md`, `test_hook.py`, `test_log_writer.py`, `test_resolve.py`, `compound.py`,
`config.py`, `config_types.py` already modified from the PRIOR "R3 review-fix" session (which
closed a DIFFERENT set of 6 findings from two judges). Suite was 2314 tests green at that
session's end. My job was purely these 5 NEW findings.
