---
title: latest-code-review-report
type: report
tags:
- code-review
- TOO-45
permalink: latest-code-review-report
---

# Code review report -- 2026-08-09 (20:36-20:52)

**Ticket**: TOO-45 (punch-list #03 -- extract `file_matching`, remove the `permission_resolution <-> resolve` runtime cycle)
**Scope reviewed** (8 files, as requested):

- `/home/arnon/projects/toolguard/toolguard/permission_resolution.py` (heavily rewritten, +299/-…)
- `/home/arnon/projects/toolguard/toolguard/resolve.py` (928 -> 714 lines, two closures deleted)
- `/home/arnon/projects/toolguard/toolguard/file_matching.py` (new, 280 lines, untracked)
- `/home/arnon/projects/toolguard/toolguard/config_types.py` (`DecideDetailed` deleted; `PathAnchoring` + `FilePathResolutionConfig` added)
- `/home/arnon/projects/toolguard/toolguard/permissions.py` (1 docstring line)
- `/home/arnon/projects/toolguard/test/unit/test_configuration.py`
- `/home/arnon/projects/toolguard/test/unit/test_hierarchical.py`
- `/home/arnon/projects/toolguard/test/unit/test_permission_resolution.py`

## Summary

This is a good refactor, and the central claim holds under independent measurement: the injected `decide_detailed` callable is genuinely gone, not relocated, and the runtime call graph across the decision path is acyclic. Behaviour is preserved (2733 tests OK, golden verdict corpus unchanged), the new module has a declared architectural home, and the change is a net deletion of 184 production lines with no compensating test bloat. Everything I found is documentation drift, naming/visibility inconsistency, or duplication that the change introduced without marking as deliberate -- no correctness, security, or performance defects.

## What I measured (including the clean results)

**Runtime call topology.** The change adds/removes injected callables, so I measured rather than inferred. A `sys.setprofile` probe recorded caller-module -> callee-module edges across five real decisions driven through `toolguard.api.decide()` (compound Bash, file path, file-path hard-deny, ask match, deny match), then ran DFS cycle detection:

- 14 toolguard modules, 25 module-pair edges on the decision path
- **No runtime cycle.**
- `permission_resolution -> resolve`: **absent** (this is the whole point of the change, and it is real)
- `file_matching -> resolve`, `permissions -> resolve`, `file_matching -> permission_resolution`: all absent
- Observed shape matches the intent: `resolve -> permission_resolution -> {permissions, file_matching}`, plus `resolve -> file_matching` for the pre-cascade hard-deny check.

**Residual invisible edge, acyclic.** `permission_resolution -> config` and `file_matching -> config` DO exist at runtime -- they call `Configuration`'s methods through the Protocol-typed `config` parameter. There is no import edge, so no static tool sees them; this is the same invisibility class as the callable that was removed. It is currently harmless (the graph is acyclic and `config` never calls back into the engine), but the seam was **narrowed, not eliminated**, and a future method added to `Configuration` that reaches back into the engine would recreate an invisible cycle with nothing positioned to notice. Worth knowing when reading `permission_resolution.py`'s docstring claim of decoupling from `config` -- true for imports, not for runtime.

**Eager-matching cost.** The implementation report carries a `+0.58%` figure inherited from the design docs and explicitly says it was not re-measured. I re-measured it: replayed the committed 6401-case verdict corpus with both per-level matchers wrapped, comparing the new eager cascade against a reconstruction of the old lazy one (visit until first match; then, only for an `allow` winner, scan the tail skipping levels with no deny patterns).

- matcher invocations, new eager: **17,799**; old lazy: **17,680** -> **+0.67%**
- 119 of 9,070 cascades did extra work; largest single-decision delta was **1** extra matcher call

The claim holds. One caveat the number hides: the worst case scales with hierarchy depth when a **deny** wins at the most-specific level (old cost 1 matcher call, new cost L). Corpus fixtures top out at ~2 levels, so a deep real-world hierarchy would show a larger -- still trivial -- delta. No action needed.

**Suite / lint.** `uv run python -m unittest discover -s test -t .` -> Ran 2733 tests, OK (matches the stated baseline exactly). `uv run ruff check .` -> All checks passed. `uv run ruff format --check .` -> 173 files already formatted.

**pyscn** (`uvx pyscn analyze --json --skip-deps .`, report `analyze_20260809_204301.json`): 11 in-scope functions, all cyclomatic complexity <= 8 except the pre-existing `permissions.match_command` (cx=18, cognitive=67), which this change did not touch. `resolve.resolve_bash_permission_detailed` has cognitive complexity 25 but the change **reduced** it (one closure deleted). Direction of travel is good. Clone findings are folded into the Suggestions below.

## Critical

None.

## Major

**MAJ-1. `technical-notes.md` names a function that no longer exists, in 4 places.**
`/home/arnon/projects/toolguard/technical-notes.md` lines 244, 373, 391, 404 reference `permission_resolution.resolve_permission_detailed`, deleted by this change. Lines 328 and 385 reference `hook._check_file_path_hard_deny` / `hook._decide_file_path_at_level_detailed`, which were already stale (wrong module) and are now doubly stale (wrong module *and* wrong name -- they are `file_matching.check_file_path_hard_deny` / `decide_file_path_at_level_detailed`).

The implementation report deliberately deferred this to punch-list #07 and I can see the reasoning, but it is worth raising to Major because CLAUDE.md instructs agents to read `technical-notes.md` on demand for design rationale, and 73KB of design prose naming non-existent API actively misleads. The pre-push checklist's `/documentation-review` gate should not be allowed to be the only thing that catches it.
*Fix*: update the 6 references, or add a dated "names below are pre-punch-list-#03" banner to the affected sections until #07 lands.

**MAJ-2. 16 test docstrings in `test_configuration.py` name a function the test does not call.**
`/home/arnon/projects/toolguard/test/unit/test_configuration.py`, lines 2848, 2916, 2968, 3308, 3312, 3448, 3473, 3497, 3520, 3541, 3587, 3711, 3722, 3733, 3744, 3755, 3766. Each says `When resolve_command_permission('Bash', ...) ...`, but every one of those tests calls the new test-local `_resolve_via_cascade` (line ~41), which calls `resolve_permission_cascade` -- the pure fold -- and never touches `resolve_command_permission`, whose entire job (building the level list with the **real** matcher) these tests deliberately avoid.

This is a mechanical-rename error introduced by this change: the old name `resolve_permission_detailed` was accurate, and it was replaced with the wrong successor. In a project that uses Given/When/Then docstrings as the specification, a "When" clause naming the wrong unit under test is worse than no clause. It also obscures MIN-3 below.
*Fix*: `resolve_permission_cascade` in all 16, and correspondingly rename `test_resolve_command_permission_reason_cites_rules_dir_file_path` (line 3308) to `..._resolve_permission_cascade_...`.

## Minor

**MIN-1. Two module docstrings directly contradict each other about re-exporting.**
`/home/arnon/projects/toolguard/toolguard/file_matching.py:24` says: *"``resolve.py`` re-exports every name below for its own existing importers."*
`/home/arnon/projects/toolguard/toolguard/resolve.py:107-112` says: *"Only `check_file_path_hard_deny` is imported here ... this one deliberately does not re-export them."*
`resolve.py` is correct; the `file_matching.py` sentence is stage-1 text that stage 2 invalidated when it renamed the helpers public and repointed the test imports.
*Fix*: delete the sentence at `file_matching.py:24`.

**MIN-2. Two functions were made public on a rationale that measurement contradicts.**
`/home/arnon/projects/toolguard/toolguard/file_matching.py:9-18` justifies the public names thus: *"`anchor_file_pattern`, `match_file_path_pattern`, `decide_file_path_at_level_detailed`, and `check_file_path_hard_deny` are public ... both cross a module boundary, so neither can stay private."* Measured across `toolguard/`, `test/`, `tools/`:

- `decide_file_path_at_level_detailed` -- crosses (imported by `permission_resolution`). Correct.
- `check_file_path_hard_deny` -- crosses (imported by `resolve`). Correct.
- `match_file_path_pattern` -- **zero** callers outside `file_matching.py`, production or test.
- `anchor_file_pattern` -- **zero production** callers outside `file_matching.py`; 4 test imports in `test_hierarchical.py`.

Per this project's own API-visibility criterion (privatize by "should non-test code call it?"; tests importing privates is fine), both should stay `_`-prefixed.
*Fix*: either re-privatize the two (updating the 4 test imports), or -- if the intent is that `file_matching` presents a coherent public matching API -- keep them public and rewrite the rationale, which is currently a false statement of fact.

**MIN-3. 26 cascade tests no longer exercise production's level-list construction.**
`_resolve_via_cascade` (`test_configuration.py:~41`) reimplements the comprehension that pairs `config.permission_levels_with_provenance(tool)` output into `LevelOutcome` values. Previously those tests called the production function `resolve_permission_detailed(config, tool, decide)` with only the *matcher* faked, so production's own level iteration and match/layers pairing were under test. Now that step is a test-local copy.

Risk is low -- the pairing is still covered by the real-matcher tests in `test_hierarchical.py`, `test_permission_resolution.py`, `test_logging_streams.py`, `test_hard_deny.py`, `test_takeover_mode.py` -- so this is an observation, not a demand. But it is a genuine coverage relocation that the implementation report does not mention, and it is the kind of thing that is invisible later.
*Fix (optional)*: none required; if you want the old property back, have `_resolve_via_cascade` call `resolve_command_permission` with a monkeypatched matcher instead of rebuilding the list.

**MIN-4. `check_file_path_hard_deny` is typed far wider than it uses, two functions below the change that fixed exactly that.**
`/home/arnon/projects/toolguard/toolguard/file_matching.py:210-212` types `config` as `ResolveConfig` (8 members) while touching only `hard_deny` and `resolve_config_path`. The change introduces `PathAnchoring` precisely to state "the narrowest statement of what those functions actually touch" for its neighbours, then does not apply the principle here. `file_matching.py`'s own docstring rationale for this ("it needs both anchoring and `hard_deny`") describes a 2-member surface, not `ResolveConfig`.
*Fix*: `class HardDenyPool(PathAnchoring, Protocol)` adding only `hard_deny`, in `config_types.py` beside the others.

## Suggestions

**SUG-1. Make `resolve_permission_cascade`'s parameters keyword-only, or bundle them.**
`/home/arnon/projects/toolguard/toolguard/permission_resolution.py:349-356` takes five positionals after `levels`, of which **three are plain strings** (`tool_name`, `no_match_fallback`, `subject`). Transposing any two is a silent behaviour change that no type checker catches. Both production call sites pass 5 positionally.
Either make everything after `levels` keyword-only (`*,`), or -- closer to this project's stated preference for an invocation-scoped facts object over repeated threading -- pass one frozen dataclass carrying the four config-derived facts (`tool_name`, `parse_failures`, `has_any_rules`, `no_match_fallback`), which both entry points read from `config` and re-thread today.

**SUG-2. The two new entry points are 0.85-similar and nothing marks that as deliberate.**
pyscn flags `permission_resolution.py:400-436 <-> 439-479` as a type-2 clone at 0.850 similarity -- `resolve_command_permission` vs `resolve_file_path_permission`. They differ only in which matcher is called (and its extra `config` argument) and `subject="Path"`. This duplication was **introduced by this change**. Either extract a shared `_resolve(levels, matcher, subject)` taking a bound matcher, or add a one-line comment saying the duplication is preferred over a higher-order parameter (which would be defensible here, given the whole point was removing an injected callable -- but say so, otherwise the next reader will "fix" it by reintroducing one).

**SUG-3. Replace `_resolve_unclamped`'s four-branch fallback chain with a lookup.**
`permission_resolution.py:311-346` is four `if fallback == "...":` branches each constructing a near-identical `RuntimeVerdict` (pyscn flags 312-322 <-> 323-332 at 0.79). A dict keyed on the fallback value -> `(decision, reason_template, fallback_warning)` collapses it and makes adding a fifth policy a data change rather than a code change.

**SUG-4. Decision strings are branched on with no named constants.**
`permission_resolution.py` has 15 sites constructing or branching on bare `"deny"` / `"allow"` / `"ask"` / `"allow_with_warning"`; `constants.py` defines no decision constants. The global CLAUDE.md names `"deny"`/`"ask"` decisions as the highest-value case for this rule. This is pre-existing and project-wide, and this change merely perpetuated it -- so it belongs in its own ticket, not here. Flagging it because the change moved and rewrote several of those sites, which was the natural moment.

**SUG-5. The two per-level matchers are the same algorithm twice.**
`permissions.decide_command_at_level_detailed` and `file_matching.decide_file_path_at_level_detailed` share the identical skeleton (deny-first loop, non-blanket ask filter, `resolve_allow_ask`, build `LevelMatch`), differing in the match primitive, path anchoring, and the noun in the reason string. Pre-existing, but the change makes it more visible: they are now siblings consumed by one fold. Low priority -- the anchoring difference is real and a shared skeleton would need a `match_one(pattern, subject)` callable, which cuts against this ticket's direction.

**SUG-6. Cross-reference density has a measurable rename tax.**
This change edited 6 production files for **docstrings only**, because those modules name other modules' functions in `:func:` cross-references. That same mechanism produced MAJ-1 (the references in `technical-notes.md` that were not updated because nothing links them to the rename). Consider referencing the *module* rather than the function in cross-module prose, where the function name is not itself the point.

## Architectural drift pass

Run because the change touches 9 production files and carries a ticket ID. These are indicators for judgement, not thresholds.

1. **Blast radius vs conceptual size -- healthy.** One concept landed in 9 production files, but only **4 carry code** (`permission_resolution`, `resolve`, `file_matching`, `config_types`); the other 5 are docstring-only. The code footprint matches the idea's size. The doc-only tail is SUG-6.

2. **Logical coupling -- one real signal.** Over the last 400 commits touching `toolguard/`: `config_types.py` changed in **8** commits, and **all 8** also touched an engine module (`resolve` / `permission_resolution` / `permissions` / `compound` / `file_matching`). A 100%-coupled pair is two files behaving as one module. This change adds to it: `PathAnchoring` and `FilePathResolutionConfig` landed in `config_types.py` purely because `file_matching` and `permission_resolution` needed them.

   This is not a defect -- it is the deliberate price of "put the contract in a shared leaf so no import edge is needed", and the alternative (importing `config`) is worse. But it is worth naming, because the *concepts* have drifted across a layer boundary: `PathAnchoring` describes what an **engine** module needs, and it now lives in the **config** layer. `engine -> config` is a legal downward edge, so no checker complains, and the compliance score stays clean while the coupling grows. If this keeps accreting, an engine-layer contracts module (`toolguard/engine_contracts.py`, registered under `engine` in `.pyscn.toml`) would hold these Protocols with no cycle and no cross-layer concept leak. Not urgent; worth a ticket before the next batch of Protocols.

3. **New file has a declared home -- clean.** `file_matching` is registered in `.pyscn.toml` under the `engine` layer (line 212). No unassigned file, which is the failure mode that usually goes unnoticed.

4. **Boundary crossings -- benign.** The change spans `toolguard/` and `tools/` (`architecture_fitness.py`, one docstring line). One crossing, doc-only.

5. **Test cost trend -- good.** This change: **+120/-199** test lines against **+376/-560** production lines (ratio 0.32). The project's standing ratio over the last 40 commits is roughly **3.25** test insertions per production insertion. Coming in ten times below the norm is the right answer for a behaviour-preserving refactor: no representation-pinning tests were added, and the golden corpus carried the verification instead. Positive signal.

## Tool observation (code-review-graph trial)

Phase: **refactoring**. `semantic_search_nodes` returned `/home/arnon/projects/toolguard/toolguard/resolve.py::_decide_detailed` at lines 780-800 -- a function **deleted in the working tree**. Verified absent by grep. Had I taken it at face value it would have been a false "dead closure left behind" finding.

Two honest caveats. First, **I did not run `embed` + `postprocess` before the search**, so per the trial protocol this entry should be read as inconclusive rather than negative. Second, the stale node came from the *nodes* table, which the reference documents as auto-updating on every Edit/Write/Bash -- so refreshing embeddings might not have helped anyway. The search did usefully surface the test-local `_decide` stubs across five test files in one call. But the specific question I was asking ("is `_decide_detailed` gone?") is a one-call `LSP` question that pyright would have answered correctly, which is the standard the trial now applies.

## Verification commands used

```
uv run python -m unittest discover -s test -t .        # Ran 2733 tests, OK
uv run ruff check .                                     # All checks passed
uv run ruff format --check .                            # 173 files already formatted
uvx pyscn analyze --json --skip-deps .                  # grade B; in-scope cx all <= 8 bar pre-existing match_command
```

Plus two throwaway measurement scripts (deleted with the scratchpad): a `sys.setprofile` runtime-call-graph probe with DFS cycle detection, and a corpus replay counting eager vs lazy matcher invocations.

## Review metrics

- **Elapsed**: 16 minutes (20:36 -> 20:52)
- **Estimated cost**: ~$3.10 (Opus 5; heavy file reads, one 6401-case corpus replay, one full test-suite run)
- **Files reviewed**: 8 in scope; ~12 more read for context (`api.py`, `patterns.py`, `constants.py`, `.pyscn.toml`, `technical-notes.md`, corpus harness, sandbox harness)
- **Issues by severity**: Critical 0, Major 2, Minor 4, Suggestions 6, plus 5 architectural-drift observations (4 healthy, 1 worth a ticket)
