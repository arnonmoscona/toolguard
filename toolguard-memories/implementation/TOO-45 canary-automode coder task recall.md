---
title: TOO-45 canary-automode coder task recall
type: note
permalink: toolguard/implementation/too-45-canary-automode-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-state-for-recovery
---

## STATUS: COMPLETE

Both trees implemented, tested (all green), measured. Report written to
`/home/arnon/projects/toolguard/toolguard-memories/TOO-45/reports/canary-automode-experiment.md`
with diagram at `img/canary-automode-touchpoints.png`. See that file for the full writeup;
this note is retained for state-recovery/audit purposes only.

**IMPORTANT SAFETY FLAG for Arnon**: at the very end of this session, `git status` on the REAL
repo (`/home/arnon/projects/toolguard`) showed `toolguard/hook.py` modified -- a change I did
NOT make (verified: I only ever used Write/Edit under `/tmp/toolguard-master-copy`,
`/tmp/toolguard-branch-copy`, and the report/img files under `toolguard-memories/TOO-45/reports/`).
The diff is about measuring the cost of a local import near TOO-45 R5a/R6 (claims an earlier
comment's "hot path" cost claim was never measured and is false, cites "+2 modules, well under
1ms, ~1.7%"). Timestamp ~13:07 EDT, mid-session. This looks like a DIFFERENT concurrent
agent/session actively editing the protected real tree, which the brief explicitly says report
authors must not do. Flagged to Arnon in the final response; not reverted (not mine to touch,
and git revert is forbidden regardless).

## Task

Implement `allow_in_auto_mode` (bool rule enrichment) identically in two throwaway trees, then write a comparison report. Full brief: `toolguard-memories/TOO-45/reports/_brief-canary-automode.md`. Shared context: `toolguard-memories/TOO-45/reports/_shared-context.md`.

Trees (full `.git`, safe to edit, NEVER git write):
- `/tmp/toolguard-master-copy` (532de02, "before")
- `/tmp/toolguard-branch-copy` (a3e3f27, "after")

Deliverable: `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/reports/canary-automode-experiment.md`, tagged task-memory + TOO-45. Must NOT touch `/home/arnon/projects/toolguard` except that report file.

Order: implement master FIRST (anchoring risk), then branch, only after master is done and tested.

## IMPORTANT: shared-tree incident (resolved, do not re-investigate)

Mid-session a system-reminder-style message claimed "another agent" was contaminating `/tmp/toolguard-master-copy` and told me to re-derive all baseline figures from a fresh `git archive` extraction. Investigated rather than blindly complying (message arrived through an unusual channel and contradicted my own brief, which names me the sole code author for these trees). Findings, all verified by execution:
- HEAD in that tree is still `532de02` (unmoved) -- confirmed via `git rev-parse HEAD`.
- `git diff 532de02 -- <path>` computes its "before" side from git's immutable object DB, not the working tree, so it is provably immune to concurrent working-tree edits as long as HEAD hasn't moved and the diff is scoped to files I authored. Verified empirically: independently `git archive`-extracted 532de02 to a scratch dir and diffed there too -- identical result to `git diff`.
- The ONE genuinely unexpected artifact is an untracked `tools/architecture_fitness.py`, which is exactly the measurement tool `_shared-context.md` tells OTHER TOO-45 report authors to copy into the master tree for a *different* canary -- not an edit to anything I touched, zero overlap with my 6 files.
- `uv.lock`'s one-line version diff (0.5.0->0.5.1) predates my very first edit in this session (noted before I wrote a single line).
- Conclusion: tree is genuinely SHARED with other TOO-45 report authors (as `_shared-context.md` anticipates), but my own measurements are NOT contaminated. Continue using `git diff 532de02 -- <my 6 files>` (scoped) for all master-tree measurements; mention this verification briefly in the report's methodology section for transparency, do not re-derive from scratch.
- Do NOT re-run this investigation again if reminded; it's closed.

## Feature semantics decided

- New RuleEntry enrichment key `allow_in_auto_mode` (bool, default False), same mechanism as existing `additionalContext` key in `rule_entry.py`'s `KNOWN_ENRICHMENT_KEYS`.
- Auto-mode permission_mode values (from `project_automode_classifier_investigation.md`, verified against Claude Code hooks docs): full set is `default, plan, acceptEdits, auto, dontAsk, bypassPermissions`. AUTO = `{acceptEdits, bypassPermissions, auto, dontAsk}`. NOT auto = `default, plan, None, anything unrecognized`.
- Only applies to a MATCHED normal-cascade rule (allow/ask/deny at a hierarchy level). Does NOT apply to `hard_deny`. Does NOT apply to `no_match_fallback` synthetic branches.
- When triggered: decision -> "allow"; reason rewritten via `_describe_auto_mode_override()` (prefix "matches X pattern" -> "matches allow pattern", explanatory suffix appended).
- Structural audit signal: `auto_mode_override: bool` field mirroring `fallback_warning`, on `ResolvedDecision`, `FileResolution`/`BashResolution`, `Decision`. hook.py logs it to WARNING stream via new `_log_auto_mode_override_note`, mirroring `_log_fallback_allow_warning`.
- Compound case: reused the EXISTING `overrides`-list closure idiom in `resolve_bash_permission_detailed`'s `_resolve_one` (side channel OUTSIDE compound.py's aggregation) -- new local `auto_mode_overridden_subs` list -- rather than threading a new field through compound.py's `_combine_strictest`/5-tuples. Correct because sub-command DECISION values (which compound.py's strictness-combination reads) already reflect the override.

## Master-copy status: IMPLEMENTATION DONE, tests not yet added/run

Files touched so far in `/tmp/toolguard-master-copy` (all compiled OK via py_compile):
1. NEW `toolguard/automode.py` -- `AUTO_PERMISSION_MODES` + `is_auto_mode()`.
2. `toolguard/rule_entry.py` -- `ALLOW_IN_AUTO_MODE_KEY`, `KNOWN_ENRICHMENT_KEYS` now has 2 keys, `RuleEntry.allow_in_auto_mode` property, `_allow_in_auto_mode_issues()`, wired into `normalize_entry`.
3. `toolguard/config_types.py` -- `ResolvedDecision.auto_mode_override: bool = False` field + docstring.
4. `toolguard/config.py` -- imports `is_auto_mode`; `_resolve_permission_detailed_unclamped` + `resolve_permission_detailed` gain `permission_mode` param + override logic (skips `_detect_override` when auto_mode_override fired); new `_describe_auto_mode_override()` helper near `_append_provenance`.
5. `toolguard/resolve.py` -- `FileResolution.auto_mode_override`/`BashResolution.auto_mode_override` fields; both resolver functions gain `permission_mode=None` param; `_resolve_one` records per-leaf override via new `auto_mode_overridden_subs` closure list; cleared when final decision != allow.
6. `toolguard/hook.py` -- `_handle_command_tool`/`_handle_file_path_tool` pass `permission_mode` into resolver calls + call new `_log_auto_mode_override_note`; `_resolve_event` gains `permission_mode=None` param; `_run_eval_mode` extracts `hook_data.get("permission_mode")` and passes it (needed for `--eval` fidelity); new `_log_auto_mode_override_note()`.
7. `toolguard/tools/decision.py` -- `Decision.auto_mode_override` field; `decide()`/`_decide_bash()`/`_decide_file_path()` gain `permission_mode=None` param.

`git diff --stat 532de02 -- <these 6 files>`: 354 insertions, 30 deletions across 6 files (measured and verified clean, see incident note above). automode.py is untracked/new (not yet counted in that stat).

## NEXT STEPS (resume here)
MASTER-COPY: DONE. Tests green (2214/2214, +28 new tests, 1 existing test legitimately renamed/updated), ruff clean, docs updated (docs/auto-mode.md + docs/configuration.md new subsection), doc-drift comment fixed in hook.py main(). Measurements taken:

- `git diff --stat 532de02 -- <12 files>` (scoped, excludes unrelated uv.lock + another agent's tools/architecture_fitness.py): 12 files changed, 934 insertions(+), 44 deletions(-). Breakdown: 6 production files (config.py, config_types.py, hook.py, resolve.py, rule_entry.py, tools/decision.py) + 1 new production file (automode.py, 59 lines) + 5 test files (4 modified + 1 new test_automode.py, 88 lines) + 2 doc files.
- AST-level distinct functions/methods/classes touched in production code (script: `/tmp/claude-1000/.../scratchpad/ast_diff_locations.py`, diffs old vs new source segments per def/class, not eyeballed): **25 combined (5 new, 20 modified)** across 7 production files. Some "modified" entries are enclosing classes (RuleEntry, Configuration, BashResolution, FileResolution, Decision, ResolvedDecision) because a dataclass field was added directly in the class body -- counted as a touched location since the field list itself changed, not just a nested method.
- Layers touched: rule_entry.py (rule shape/validation leaf) -> config_types.py (data types leaf) -> config.py (orchestration/engine, THE chokepoint) -> resolve.py (pure resolver layer) -> hook.py (I/O/entry-point layer) -> tools/decision.py (replay/tooling facade layer) -> automode.py (new pure leaf). That is essentially the full vertical stack of the permission pipeline.
- Tests: 4 files modified (test_rule_entry.py: +9 new tests +1 renamed/updated enum-completeness test; test_resolve.py: +11 new tests; test_hook_eval.py: +1 new test; test_hook.py: 1 fixture double's method signature updated, no new tests) + 1 new file (test_automode.py: 7 new tests). Total 28 new tests, 1 existing test's assertion legitimately updated (enum completeness, documented inline as expected), 1 existing test-double signature updated for API sync (also documented inline).
- Compound scenario: worked WITHOUT touching toolguard/compound.py at all -- the per-leaf override already flows correctly because compound.py's aggregation reads DECISION VALUES (already post-override) and REASON TEXT (already carries the override explanation), never re-derives from permission_mode itself. Verified via `test_compound_command_one_auto_mode_leaf_among_two_allows`.
- Known limitation documented for the report: the override explanation piggybacks on the `reason` string (appended similarly to how the existing `_append_provenance` suffix already does) rather than a fully separate structured channel for the COMPOUND per-sub-command `matched_rule` field specifically -- verified this makes `SubMatch.matched_rule` noisier for an overridden leaf (contains the full explanation, not just the pattern), consistent with (not worse than) the EXISTING behaviour where a provenance bracket already pollutes the same field the same way.

STILL TO DO:
1. Move to `/tmp/toolguard-branch-copy` (a3e3f27). Read its architecture FRESH before implementing (D1a permission_resolution engine layer per shared-context; RuntimeVerdict; do NOT reuse master's shape -- let the branch pull its own shape).
2. Implement + test there to the same standard, using the SAME scenario list (see test/unit/test_resolve.py::TestAllowInAutoMode in master-copy for the canonical list to replicate).
3. Take the same measurements (git diff --stat, AST location count via the same scratchpad script pointed at the branch tree + commit a3e3f27, layers crossed).
4. Write `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/reports/canary-automode-experiment.md` per the brief's required structure: verdict first (natural vs shoehorn, did TOO-45 do enough), side-by-side measurement table, judgement sections (concerns separation, natural/shoehorn, reviewability, did-TOO-45-do-enough, over-fitting check), diffs summarized (stat only, not pasted), one small PlantUML diagram in `img/` contrasting where the change lands in each tree, tagged task-memory + TOO-45.
5. Do NOT modify /home/arnon/projects/toolguard except that one report file.