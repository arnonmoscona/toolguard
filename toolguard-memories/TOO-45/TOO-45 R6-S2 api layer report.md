---
title: TOO-45 R6-S2 api layer report
type: note
permalink: toolguard/too-45/too-45-r6-s2-api-layer-report
tags:
- task-memory
- TOO-45
---

# TOO-45 R6-S2: give the engine a public `api` layer

Implemented on branch `too-45`, working tree `/home/arnon/projects/toolguard`. This is the final stage of the R6 replacement plan. S0 (instrument fix), S1 (private-reach cleanup) and S3 (verdict unification, `Decision` -> `RuntimeVerdict`) were already done and green before this session started (2401 tests, corpus 6401+61 no differences, R1/R2/R3/R5/R6 PASS) -- confirmed by reading the S3 report and by the baseline run below. This report covers S2 only.

## What was done

Moved `decide()` (and its private helper `_decide_bash()`) out of `toolguard/tools/decision.py` (the `tooling` layer) into a new module `toolguard/api.py`, in a new declared `.pyscn.toml` layer `api` sited directly above `engine`:

```
foundation < config < engine < api < runtime < tooling < support
```

`toolguard/tools/decision.py` becomes a one-line backward-compatible re-export: `from toolguard.api import decide  # noqa: F401`, with a docstring explaining the history and pointing at `toolguard.api` for the real implementation. `toolguard/hook.py`'s `_resolve_event` (the `--eval`-only caller) now imports `decide` from `toolguard.api` at MODULE level -- the function-local import, its `noqa: PLC0415` marker, and the two-paragraph comment justifying why it stayed local (and correcting two false claims about it) are all deleted, per the task's explicit instruction that this comment "should disappear along with the local import."

This clears the one remaining layer violation:

```
Before: hook (runtime) -> tools.decision (tooling) at line 667 [local import]
After:  No cross-layer direction violations.
```

## Design: is `api` a genuine interface, or a relocation dressed up as one?

Asked explicitly, before declaring this done, per the task's instruction to check call intent and SRP, not just the predicate.

**Public surface: exactly one function, `decide()`.** I considered and rejected making `api.py` a broader facade (the S4 idea the R6 reassessment already rejected on separate grounds -- 74% of the tooling+runtime crossing surface is config-layer, not engine-layer, and a 43-name facade over `Configuration`/`rule_sort`/etc. would be "a list of what 21 modules import," not a designed interface). `api.py`'s surface is deliberately narrow: it fronts the one verb every actual consumer -- the live hook's `--eval` path and every tooling call site -- asks for: "what would toolguard decide for this tool+target under this config?" That is the same call-intent argument the S3 report made for unifying `Decision` into `RuntimeVerdict`, applied one level up: there is one question, asked from two layers, and now there is one place that answers it.

**Would I defend `_decide_bash` as a member too?** It's private (leading underscore), not part of the public surface, and stays that way -- it exists only because `resolve_bash_permission_detailed` hardcodes `tool='Bash'` and one documented edge case (a caller-supplied tool name that differs) needs the override restored. `decide()` is the only name external code should ever import, and the two test files that reach `_decide_bash` directly (`test_api.py`, mirroring the prior `test_tools_decision.py` non-pattern) do so because "should non-test code call it?" is the project's own established privacy criterion (test importing privates is fine, per the auto-memory rule I checked against), and `_decide_bash`'s override contract is exactly the kind of thing worth pinning directly rather than only through `decide()`'s black box.

**Was I tempted to build the wrong shim?** Yes, briefly, and the reassessment's own E2 probe already blocked it: making `api.py` a thin re-export pointing back at `tools/decision.py` (the WRONG direction) was measured to fail the layer check outright -- the violation just relocates to `api.py`'s own import line. That is not what I built. What I built is the other direction: `api.py` owns the real ~170-line implementation (moved verbatim from `tools/decision.py`, docstrings adjusted for its new layer identity); `tools/decision.py` is the one-line forward. That direction is legal under the declared rules (`tooling` is allowed to import `api` downward) and is what the reassessment's E2b probe demonstrated.

## Did runtime end up calling anything but the api for its decision?

No, and this is the specific thing R6's stated extension asked me to check. `hook.py`'s LIVE (non-`--eval`) path -- `_handle_command_tool`/`_handle_file_path_tool`, driven by `main()` -- never called `decide()` at all, before or after this stage: it calls `resolve_bash_permission_detailed`/`resolve_file_path_permission_detailed` directly from `toolguard.resolve` (the `engine` layer, which `runtime` is allowed to import from without going through `api`). That was confirmed true before this stage (S3 report, DEMONSTRATED BY EXECUTION) and re-verified below. The ONLY place `hook.py` calls `decide()` is `_resolve_event`, used exclusively by `_run_eval_mode()` (`--eval`), and it now imports that name from `toolguard.api` directly -- not from `toolguard.tools.decision` -- so there is no case where hook.py reaches `decide()` through any path other than the api layer.

**Did tooling end up calling anything but the api?** Here I made a deliberate, bounded choice and want to be explicit about it rather than let it pass silently. I did NOT rewrite the ~15 existing production/test call sites (`self_permission.py`, `uninstall_readiness.py`, `replay.py`, `mining.py`, `consolidate.py`, `testing/sandbox.py`, the verdict-corpus fixture loader, and 8 test modules) to import `from toolguard.api import decide` directly. They still say `from toolguard.tools.decision import decide`, which now resolves to the exact same function object as `toolguard.api.decide` (pinned by a new identity test, see below) via the one-line re-export. So tooling calls the api's `decide()` -- literally the same object, not a divergent copy -- but does so through an alias rather than the api's own name.

I chose this over a full rename sweep for three reasons, and I think Arnon should have the choice to override it:

1. **It's what the reassessment's S2 blast-radius estimate measured and pre-authorized**: "layer violations 1 -> 0; 3 failing tests, all fitness-tool altitude assertions; 0 behavioural failures; corpus no differences" -- that number was produced by the same design (api owns `decide()`, `tools/decision.py` becomes the re-export), not by a full rename. A rename sweep across ~16 files (5 more production files than S3 already touched, plus corpus/test infra) was not what was measured, and going there unilaterally would have exceeded both the pre-authorized scope and my own scope-inflation guard for a change I hadn't sized.
2. **It is architecturally sound, not merely convenient.** The layer checker validates by import EDGE. `tools/decision.py` (tooling) importing from `toolguard.api` (api) is a legal downward edge in its own right -- it is not "tooling secretly bypassing the api," it's tooling's own internal module correctly sitting one layer below the interface it forwards. Nothing about R6's predicate, or the layer rules, requires every external caller to spell the api layer's name literally; it requires no caller to reach INTO a higher layer than it's allowed to, which is satisfied.
3. **I found no genuine drift risk it would leave behind**, because there is no second definition to drift FROM -- there is exactly one `decide()`, defined once, in `api.py`. The risk R6's extension is actually guarding against ("an interface used only by tooling drifts from what the engine really does, because its primary consumer bypasses it") is a risk of TWO implementations, not two import spellings of one. That risk doesn't exist here: I verified `toolguard.tools.decision.decide is toolguard.api.decide` (same object) and `decide.__module__ == "toolguard.api"` (genuinely defined there, not re-implemented) with direct identity tests, mirroring the exact guard pattern `test_architecture.py`'s `TestReExportIdentity` already uses for `config.py`'s re-exports of `config_types` -- the project's own established defense against silent duplicate-definition.

If Arnon wants the ~16-file rename swept too (so every call site literally says `toolguard.api.decide`), it is a cheap, low-risk mechanical follow-up now that the real move is done and verified -- nothing found here argues against it, only that it wasn't what this stage's measured/authorized scope covered.

## Files changed (7 modified, all backed up before editing; 2 new)

**Production (5 modified, 1 new):**
- `toolguard/api.py` (**new**, 171 lines) -- `decide()`/`_decide_bash()` moved here verbatim from `tools/decision.py`, docstrings rewritten to describe the module's own identity, its reason for existing, and why its surface is exactly one function (the S4-rejection argument, repeated here for local context).
- `toolguard/tools/decision.py` (rewritten, 155 -> 33 lines) -- now a backward-compatible re-export with a history docstring.
- `toolguard/hook.py` -- `from toolguard.api import decide` added at module level; the function-local import + its justification/correction comment deleted; 4 docstring references to `toolguard.tools.decision.decide()` updated to `toolguard.api.decide()`.
- `toolguard/config_types.py` -- one docstring cross-reference (`_decide_bash`'s new home).
- `toolguard/resolve.py` -- see "Also in this stage" below (the accepted docstring defect).
- `.pyscn.toml` -- new `[[architecture.layers]] name = "api"` entry (`packages = ["api"]`); new `[[architecture.rules]] from = "api"` (`allow = ["api", "engine", "config", "foundation"]`); `runtime`/`tooling`/`support`'s `allow` lists extended to include `"api"`; `engine`'s `deny` comment extended to include `"api"` (decorative only -- confirmed by reading `parse_architecture_config`/`check_layers` that `deny` is never actually parsed by this project's checker, only `allow` gates the direction check; kept for human readability, matching every other layer's existing convention).

**Test (2 modified, 1 new):**
- `test/unit/test_architecture.py` -- updated the one stale comment describing the now-removed `hook -> tools.decision` local import + `PLC0415` marker as a still-current fact; it's now phrased in the past tense with the R6-S2 resolution.
- `test/unit/test_architecture_fitness.py` -- `test_check_layers_runs_on_real_tree`'s docstring and assertions updated: it previously documented "1 pre-existing DIRECTION violation... deliberately left open for R6" and deliberately did NOT assert `report.ok`; now it asserts `report.ok is True` (ratcheted, since the violation is genuinely gone) alongside the existing completeness assertion. Two new tests added to `TestSmokeAgainstRealTree`, both requested explicitly by the task's pyscn caveat:
  - `test_api_layer_is_seen_and_populated_in_real_tree_layer_map` -- pins that `toolguard/api.py` maps to layer `"api"` specifically in the real tree's `module_layer`, not unmapped, not multiply-mapped. This is the direct check against "a module that maps to no layer stops being validated" -- completeness alone (`report.unmapped == []`) doesn't prove the NEW layer specifically was reached; this does.
  - `test_api_layer_rule_allows_only_engine_and_below` -- pins the real `.pyscn.toml`'s declared `api` rule as `{"api", "engine", "config", "foundation"}` exactly, explicitly asserting `"runtime"`/`"tooling"`/`"support"` are absent. This pins the DIRECTION of the rule itself, not just "today's tree happens to have zero violations" -- a future accidental widening of the rule (e.g. adding `"runtime"` to `api`'s allow list) fails this test even before any real import would trip `--layers`.
- `test/unit/test_api.py` (**new**, 130 lines) -- `TestApiReExportIdentity` (2 tests: same-object identity between `toolguard.tools.decision.decide` and `toolguard.api.decide`; `decide.__module__ == "toolguard.api"`), `TestApiDecideSmoke` (1 test, minimal behavioural smoke case -- full behavioural coverage of `decide()` already lives in `test_tools_decision.py` and reaches the same object through the re-export, so it is not duplicated here), `TestDecideBashToolOverride` (1 test pinning `_decide_bash`'s documented tool-name-override contract directly).

Net new tests: 2401 -> 2407 (+6: 4 in `test_api.py`, 2 in `test_architecture_fitness.py`). No existing test was weakened; the one existing assertion that changed (`test_check_layers_runs_on_real_tree`) was STRENGTHENED (un-asserted `report.ok` -> asserted `True`), not relaxed, and only because the underlying fact it was declining to assert is now genuinely true. No test deleted this stage.

## Also in this stage: the accepted `resolve.py` docstring defect

`toolguard/resolve.py:2` claimed *"Pure, side-effect-free permission resolver layer"*. Confirmed false by reading `normalization.py:47-50,81` (`exists()`, `is_symlink()`, `resolve()` -- all live filesystem reads inside `normalize_path`/`normalize_path_in_command`) and tracing the call path into `permissions.py:145` (`command_variants = [command_str, normalize_path_in_command(command_str)]`, inside the pattern-matching function every resolver in `resolve.py` calls into). Corrected the docstring's opening claim and the "Pure (no logging...)" bullet to state the narrower, still-true claim without the word "pure": no logging, no stdin/stdout, no `sys.exit`. Line 7's narrower claim survives verbatim in substance. Explicitly noted in the new docstring text that the check-to-use race in that disk read is a known, deliberately deprioritised issue and is NOT mitigated or chased here, per the task's instruction. Also updated this docstring's "both callers" paragraph to name `toolguard.api` (with `toolguard.tools.decision` noted as its now-back-compat alias) instead of the stale `toolguard.tools.decision` reference, since that paragraph is literally about the two callers this stage's move concerns.

## Doc-drift swept

Grepped the whole repo (excluding `toolguard-memories/`, which is intentionally historical) for `hook -> tools.decision`, `1 pre-existing DIRECTION`, and `deliberately left open for` -- the only hits were the two comments already fixed above (test_architecture.py, test_architecture_fitness.py). Grepped for remaining `noqa: PLC0415` markers: only the two pre-existing, unrelated parser-cycle escapes remain (`command_extractor.py`, `multiline.py`); hook.py's is gone, confirming the local import was fully removed rather than merely commented differently. Checked `toolguard/tools/__init__.py`'s prose description of the `decision` module ("side-effect-free evaluation primitive... replay a single command/path through the exact same matching logic the hook uses") -- left unchanged because it remains literally true (the module still is that, one hop away via the re-export); rewriting every prose mention across the repo that remains true was judged out of this stage's authorized scope (see the "tooling call sites" discussion above). Checked `technical-notes.md:965` (`.evaluate()` delegates to `toolguard.tools.decision.decide`) for the same reason -- also still true, left unchanged. Confirmed `pyproject.toml`'s wheel packaging (`packages = ["toolguard"]`) already covers the new `api.py` file with no config change needed.

## Acceptance criteria -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2407 tests in 32.730s
OK
```
(2401 baseline + 6 new: 4 in test_api.py, 2 in test_architecture_fitness.py.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.11s. End-to-end: 61 cases in 3.41s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --predicates
=== R1: PASS ===
=== R2: PASS ===
=== R3: PASS ===
=== R5: PASS ===
=== R6: PASS ===
```

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
No cross-layer direction violations.
```
(Exactly the reassessment's predicted E2b shape: 1 -> 0 violations. Unlike the reassessment's own probe, which predicted "3 failing tests, all fitness-tool altitude assertions" as the mechanical cost, THIS implementation produced ZERO test failures -- see "Why fewer failures than predicted" below.)

```
$ uv run ruff format . && uv run ruff check --no-cache .
152 files left unchanged
All checks passed!
```

## Why fewer failures than predicted -- and DEMONSTRATED, not assumed

The reassessment's E2b probe predicted 3 failing tests, all fitness-tool altitude assertions, when moving `decide()` to `api.py`. My implementation produced 0 failures on the first full-suite run after the move (verified: ran the suite once immediately after completing the `hook.py`/`tools/decision.py`/`.pyscn.toml` edits, before touching any test file -- see the "after_move_test.log" checkpoint, 2401 tests, OK). The likely reason: the reassessment's probe was run against a design where `tools/decision.py` stopped existing as a module with meaningful content in a way that disturbed `tools/architecture_fitness.py`'s real-tree module scan (its own appendix doesn't specify the exact shim shape it used for E2b beyond "genuinely owns decide(); tools/decision.py becomes the re-export," which is the same shape I built). Since `RuntimeVerdict`/`UnitVerdict` (the classes the altitude classifier scans for) live in `config_types.py`, untouched by this move, and `tools/decision.py` still exists with the same package membership (`tools`), nothing about the classifier's real-tree scan changed. I did not chase this discrepancy further since it resolved in the SAFER direction (fewer breaks, not more) and the acceptance criteria the task specifies were all met; I'm flagging the mismatch rather than silently taking credit for a better number than what was forecast.

## Smoke-tested both entry paths end to end

**`toolguard --eval`** (uses the api layer's `decide()`): built a throwaway project dir (`.claude/toolguard_hook.toml` allowing `Bash(ls *)`, denying `Bash(rm -rf *)`) outside the repo, piped both an allow-case and a deny-case hook event through `PYTHONPATH=<repo> uv run python -m toolguard.hook --eval` from inside that directory. Both verdicts came back correct (`allow`, `deny` with the expected reasons).

**Live hook** (does NOT go through `decide()`/`api.py` at all -- confirmed, see below): ran the identical two events through `python -m toolguard.hook` (no `--eval`) from the same directory. Identical verdicts to `--eval`, confirming no drift between the two paths.

**In-process `sys.modules` check** (the same technique the S3 report used, re-run after this stage's move): drove `hook.main()` in-process, once with `--eval` and once without, and inspected `sys.modules` afterward in each case. Result: `toolguard.api` is now resident in BOTH cases (`api_loaded=True` for live and eval alike) -- expected and correct, since the import is now module-level and `api` is a layer `runtime` is always allowed to have resident. `toolguard.tools.*` is loaded in NEITHER case (`tools_mods=[]` for both) -- this is actually a small IMPROVEMENT over the pre-S2 state the S3 report measured, where `--eval` used to load `toolguard.tools` and `toolguard.tools.decision` (because `decide` lived there); now `hook.py` reaches `decide` straight from `toolguard.api` without ever touching the `tools` package, on either path. The live path's separate confirmation -- that `_handle_command_tool`/`_handle_file_path_tool` call `resolve_bash_permission_detailed`/`resolve_file_path_permission_detailed` directly, never `decide()` -- was re-verified by reading the current source (grep for `decide(` call sites in `hook.py`: exactly one, inside `_resolve_event`), not merely re-asserted from the S3 report.

## Scope-inflation flag

7 modified files + 2 new files = 9 total, all non-trivial in the "touched with intent" sense but small individually (`config_types.py`: 1-line docstring edit; `test_architecture.py`: 1 comment block). This is within my own default guard (5 non-trivial existing-file edits / 10 total) and well within the pre-authorized S2 blast radius from the reassessment. No stop-and-ask was triggered.

## Backups

All 7 edited files were copied to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r6-s2-backups/` with a `SHA256SUMS.txt` manifest, all before their first edit. Diffed every backup against the current file at the end to confirm the touched-file list and content matches exactly what was intended, and to produce the "true delta" line counts quoted above (as opposed to `git diff`, which shows cumulative uncommitted changes from S0/S1/S3 too, on files those stages already touched).

## Elapsed time / cost

Session start ~16:00 local (first tool call after the sub-agent identification echo), report written ~17:05 local: roughly 65 minutes total, single continuous session.

- **Phase 1 (reading + planning)**: ~25 min. Reading `_shared-context.md`, `r6-reassessment.md` (the full ~240-line analysis document) and the S3 report in full; tracing `hook.py`'s live-vs-eval call paths, `.pyscn.toml`'s current layer/rule structure, and every production+test consumer of `tools.decision`/`decide` via targeted greps, before writing any code. Most of the token cost in this session was here, consistent with the pattern the S3 report also noted.
- **Phase 2 (implementation)**: ~25 min. Backups, `api.py` (new), `tools/decision.py` (rewrite), `hook.py` (import hoist + 3 docstring fixes), `.pyscn.toml` (new layer + rule updates), `config_types.py`/`resolve.py` (docstring fixes), 2 new pinning tests + 1 new test file, with a full-suite run after each major edit rather than batching them (per the project's own "run tests after every meaningful change" convention) -- 4 full suite runs total during this phase.
- **Phase 3 (self-review + acceptance)**: ~10 min. Final consolidated acceptance block, backup-diff review, doc-drift grep sweep, the in-process `sys.modules` smoke probe.
- **Phase 4 (report + IDE)**: ~5 min.

Order of magnitude: comparable to or somewhat cheaper than the S3 session (which the S3 report estimated at "tens of dollars, not single digits") -- this stage touched roughly a third as many files and needed no mechanical multi-file rename sweep, which was the bulk of S3's token cost. I would not stand behind a more precise dollar figure than "same order of magnitude as S3, likely on the lower end of it."