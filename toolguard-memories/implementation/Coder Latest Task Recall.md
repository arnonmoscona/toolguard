---
title: Coder Latest Task Recall
type: note
permalink: toolguard/toolguard-memories/implementation/coder-latest-task-recall
tags:
- task-memory
- claude_tooling
- tests-package
---


# Task: TOO-28 Phase 1 Round 4 -- delete unpacking aliases -- toolguard project

Brief: toolguard-memories/TOO-28/brief-phase1-round4.md (validated 5/5 slots present).

## Task
Rounds 1-3 collapsed loose parameters into one context object (Invocation), but function
bodies re-created the same unpacking as local aliases (`tool_name = invocation.tool_name`,
etc). 39 such lines claimed across 4 files (hook.py 27, permission_resolution.py 6,
resolve.py 3, file_matching.py 3) -- brief says this count is unverified, re-measure.
Arnon: "not sure why we need constructs like [these] - it just adds lots of lines without
adding any clarity... You can always choose a shorter name for the invocation variable in
those cases (say, inv) if your goal is brevity at the use site." Round 2's "used 7-15 times,
inlining unreadable" justification is REJECTED: brevity is a naming problem, not structural.

## In scope
Delete PURE aliases (`x = <context>.x`), inline through context object at use sites.
Renaming invocation->inv / context->ctx permitted per-scope, not required. Don't merge the
concrete Invocation-typed name with the Protocol-typed context name -- they're deliberately
different types.

## NOT in scope / must stay
- `takeover = invocation.config.takeover_mode()` (hook.py:846) -- computed, not alias.
- `hook.py:677` `target = invocation.tool_input.get(key, "")` -- lookup, not alias.
- Any local with different name than the attribute, or REASSIGNED later in body -- highest
  risk item, brief explicitly did NOT check this, must classify before editing any of them.
- `_run_startup_validation`'s `config = invocation.config; if config is None:
  config = load_configuration(invocation.cwd)` -- deliberate documented behavior with a test,
  keep working; local may stay if removing it makes the branch worse.

## env_config `or {}` cases (hook.py:81,795,847,872)
Preferred fix: give env_config dataclass field a non-None default
(`field(default_factory=lambda: MappingProxyType({}))`, idiom already in rule_entry.py),
removing `or {}` entirely so the alias becomes pure and gets deleted too. If a caller
genuinely relies on None, say so and keep the local instead.

## Compound.py finding carried forward (do not re-derive)
`check_compound_permission` DOES take extended_syntax (round 3's "empty of such functions"
claim was false), but its conclusion holds for a different reason: test-only helper (module
comment at compound.py:307, all callers in test_compound.py), takes no config/tool_name, no
context object in its callers. Nothing to do here.

## PEP 758 finding carried forward
`except ValueError, TypeError:` at file_matching.py:113 -- ACCEPTED correct, requires-python
>=3.14, verified pre-existing against tag TOO-28-start-of-work. Leave it.

## No widening authorized. Behavior-neutral only. TDD not required (no signature changes).
If a test needs touching -> STOP and explain why -- means something moved that shouldn't have.

## Steps (9) with completion artifacts
1. List candidate lines, classify each (pure/computed/reassigned/or{}) -- classification in
   report. Re-measure the "39" count; brief's grep misses multi-line aliases, nested-attribute
   assigns, and differently-named locals.
2. Decide the env_config default question -- decision + reason.
3. Delete pure aliases, inline at use sites -- suite green at baseline counts.
4. ruff check/format clean.
5. Architecture fitness --stdlib --ambient --layers exit 0.
6. Verdict-corpus equivalence: OK no differences, 6401/61.
7. Calibrate BEFORE believing step 6: plant a decision-altering change, confirm --verify
   FAILS, revert, confirm passes, confirm git status --porcelain clean for that file.
8. Entry-point smoke test: all 8 [project.scripts] console scripts load.
9. Sibling sweep: regrep `^\s*[a-z_]* = (invocation|context|inv|ctx)\.`, report what remains
   and why.

## Baseline (from round 3, independently reverified by Arnon)
Ran 4021 tests / OK (expected failures=4); ruff check -> All checks passed!;
corpus OK: no differences at 6401 / 61; 3 fitness checks pass; 8 entry points load.
A changed test count is a finding, not a pass.

## Constraints
- uv run python only, never bare python/python3 (denied by permission rules).
- unittest not pytest.
- Disclosure rule (INTENT/TOUCHES/INLINE BECAUSE + TG_INTENT=1/TG_ATTEST_READONLY=1) for any
  bash carrying authored logic. Required even when blocked or fails.
- No git write ops. Revert step 7's planted change by editing the file back, never
  git checkout.
- Don't touch test/verdict_corpus/ (frozen baseline).
- Comments short, explain why not what.

## Unverified brief claims -- must check, don't trust
- Count of 39 (grep missed multi-line, nested attr, different local names).
- "Nothing distinguishes None from {} for env_config" -- brief only checked the 4 or{} sites.
- "No local reassigned after aliasing" -- NOT CHECKED by brief author, highest risk item.
- "Removing aliases reads better" -- judgement call; flag any concrete counter-example.

## Success criteria
All 9 steps completed with artifacts. Suite green at baseline counts (or explained
deviation). Corpus equivalence proven AND calibrated. Sibling sweep reported. Report anything
found wrong in the brief's premises -- every round so far has produced its most valuable
output as a correction to the brief.
