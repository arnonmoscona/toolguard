---
title: TOO-45 R3 review-fix coder task recall
type: note
permalink: toolguard/implementation/too-45-r3-review-fix-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Ticket / context

TOO-45, branch `too-45`, project toolguard. R3 ("decisions carry structured data; prose is
rendered, never parsed") was independently reviewed by two judges. Not closing until specific
findings below are fixed. Full task spec came from the parent agent, verbatim below (condensed).

## Findings to fix (from two judges' review)

1. **Highest priority -- mutation test escape**: `matched_rule=matched_pattern` mutated to
   `matched_rule=reason_with_prov` in `config.py` passed all 2300 tests; only `None` failed 2.
   Existing assertions (`assertIn`, `assertIsNotNone`) were loose by construction. Fix: add exact
   equality assertions for plain allow, deny, Bash hard-deny, file-path allow, and the
   escape-hatch `None` case. **Acceptance criterion**: apply the mutation, confirm suite FAILS,
   revert, confirm green, report results.
2. **Provenance regression**: matched_rule/violated_rules used to carry a bracketed provenance
   suffix (e.g. `ls:*  [project: /path]`); R3 correctly stopped doing that, but provenance was
   never given a replacement field, so it's now silently LOST from the audit log. Fix: add a
   `provenance` field to `BashResolution` (FileResolution already had one), thread through
   `log_command` as its own field, never folded back into matched_rule/violated_rules text.
   Update `log_harvest.py` docstring examples. Add tests pinning provenance appears for allow,
   deny, hard-deny (hard-deny has none, by design -- pin the null case too).
3. **Weakened test**: `test_hook.py::test_simple_command_logs_matched_rule` passed
   `matched_rule="git *"` in and asserted the same value out -- tautological. Fix: drive from a
   real `Configuration` + `resolve_bash_permission_detailed()` resolution instead.
4. **False docstring invariant**: `resolve.py::_deciding_sub_match_rule`'s docstring claimed it
   mirrors `_combine_strictest` "EXACTLY" and "can never diverge" -- false for
   `ls && python -c "print(1)"` under `undecidable_fallback=deny` (both leaves' SubMatch says
   'allow', final decision is 'deny', function correctly returns None but the invariant claim
   was wrong). Fix and verify no other overclaim survives.
5. **Docstring policy** (Arnon's standing rule, verbatim in the task): comments terse, negative
   results/edge cases documented, no autobiography duplicating history the reader can't
   re-derive from code. Explicit CUT targets: `config_types.py`'s `matched_rule` Attributes entry
   (9 lines -> ~1 load-bearing line), a multi-line resolve.py comment justifying a one-line
   statement below it, `hook.py`'s `_reason_suffix_or_placeholder` docstring (narrated a
   deletion). KEEP `_parse_compound_match_details`'s docstring (records a negative result) and
   the hard-deny asymmetry comment. Also fix stale `resolve.py:128` reference to a function
   (`_bash_result_is_fallback_warning`) that no longer exists.
6. **Lower priority, only if 1-5 solid**: collapse `_reason_suffix_or_placeholder` +
   `_matched_rule_for_single_command` into one correctly-named function (deferred -- explicitly
   optional). Add `matched_rule` to `BashResolution`/`FileResolution`'s `Attributes:` blocks
   (done, cheap, low-risk).

## Invariants (non-negotiable, run after every meaningful edit)

```
uv run python -m unittest test.unit.test_verdict_corpus
```
`permissionDecision` change = revert. Before finishing: full suite, `architecture_fitness.py
--guard`/`--predicates`, `corpus_build.py --verify`, `ruff format . && ruff check .`.

## Conventions

`uv run python` never bare python; unittest not pytest; stdlib only; no async/threading/
function-local imports; may ADD/MODIFY tests whose pinned code changed (list each); no git write
ops; nothing under `logs/`, `.env`, permission config, or outside repo. Do NOT touch
`test/verdict_corpus/`, `tools/corpus_build.py`, `tools/architecture_fitness.py`.

## State at session start

`git status` showed config.py/config_types.py already modified from a PRIOR coder session (R3
steps 1-2 done: `matched_rule` field added to `ResolvedDecision`, populated in config.py). Steps
3-5 from the resume note (`BashResolution`/`FileResolution.matched_rule`, populate at 3
construction sites, convert 4 parse sites) were ALSO already done by the time I started reading
(test_hook.py/test_resolve.py showed as modified too) -- so my actual job was purely the review
fixes above, not the original R3 implementation.
