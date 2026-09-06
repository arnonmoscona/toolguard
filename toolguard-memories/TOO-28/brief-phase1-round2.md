---
title: brief-phase1-round2
type: note
permalink: toolguard/too-28/brief-phase1-round2
---

# Brief: TOO-28 Phase 1 round 2 -- thread Invocation all the way down

## Task

Round 1 stopped too early. It removed parameters only from functions taking **two or more** statics — a criterion from my round-1 brief that was wrong — so it migrated the two `hook.py` handlers and concluded the rest of the phase was empty. It is not.

**The real criterion: any parameter whose value is directly available from the `Invocation` is a fossil, whether there is one of them or five.** Arnon, 2026-09-05: *"you're still passing around material that is directly accessible from Invocation rather than passing the invocation object. For instance - `resolve_bash_permission_detailed()` in resolve.py still gets arguments that are directly accessible from Invocation."*

That function today is `(command, config, extended_syntax, hard_deny_deny, hard_deny_allow)`. Four of the five come straight off the invocation: `config` directly, `extended_syntax` from `env_config`, and both `hard_deny_*` from `config.hard_deny("Bash")` — which **both** call sites currently compute and pass identically.

**Your job: thread `Invocation` all the way down the decision path**, so a function that needs invocation context takes the context object rather than pieces of it.

**Decided by Arnon, 2026-09-05, after being shown the alternatives — do not re-open:** the engine takes `Invocation`. `api.decide` keeps its current public signature `(config, tool, target, extended_syntax=True)` and **constructs an `Invocation` internally** from what it has. I put the cost of that to him explicitly (synthetic `tool_input`, no real `cwd`/`agent_info`/`governed_tools`/`permission_mode`) and he chose it anyway over the two narrower options.

**Phase 1 remains behaviour-neutral.** Nothing may change a decision. `permission_mode` becomes *reachable*; nothing reads it to alter a verdict — that is Phase 2.

## Scope and widening

**In scope:**

- `toolguard/hook.py` — the six remaining fossil-signature helpers round 1 identified but did not migrate: `_log_allowed_command`, `_log_non_allow_decision`, `_log_config_discovery`, `_resolve_takeover_mode`, `_run_divergence_check`, `_run_startup_validation`. Four of these run **before** the `Invocation` is built in `main()`. **Reordering `main()` so they can take it is authorised** — but see the constraint below.
- `toolguard/resolve.py` — both `resolve_bash_permission_detailed` and `resolve_file_path_permission_detailed`.
- `toolguard/permission_resolution.py`, `toolguard/compound.py`, `toolguard/file_matching.py`, `toolguard/parser/*` — wherever a parameter is available on the `Invocation`.
- `toolguard/api.py` — construct the `Invocation` inside `decide`/`_decide_bash`. **Its public signature does not change.**
- `toolguard/invocation.py` — see the two refinements under Findings.

**Out of scope for NEW BEHAVIOUR, but IN scope for the refactor's own fallout.** Arnon, 2026-09-05: *"by the time you are done with the refactoring some of the 'out of scope' scripts may break because of function signature changes. They are out of scope for new behaviors. They are not out of scope for side effects of the refactoring."*

So: `tools/installer.py`, `tools/security_audit.py`, `tools/maintenance.py`, `tools/takeover_audit.py`, `session_start.py`, `update_check.py`, `permission_migration.py`, `tools/update_skills.py`, `tools/decision.py`, `testing/sandbox.py`, `tools/corpus_build.py` and every test module — **you MUST fix any of these that a signature change breaks.** Do not give them new behaviour, do not refactor them for their own sake, do not put an `Invocation` into an entry point that has no use for one. Fix exactly what the cascade forces, and list every file you touched this way in the report.

**A green suite is not proof you got this right.** `corpus_build.py` and `testing/sandbox.py` are exercised by the suite; the console-script entry points largely are not. **Import every one of the eight entry points and confirm it still loads**, and say so in the report.

**Is widening authorised? NO, except for the cascade above.** No new settings, no auto-mode behaviour, no reading `permission_mode` to change a verdict, no unrelated cleanups. Report what you notice; do not fix it.

## Findings carried forward

From round 1, each with a disposition:

1. **"2+ statics" criterion — REJECTED as wrong.** It was mine, and it is what produced the empty 1c/1d tranches. Superseded by the criterion in Task above.
2. **"Migrating would require unauthorized test rewrites" — REJECTED as a reason to defer.** Arnon's standing position: tests verify behaviour, not shape; *"it breaks N tests"* is not an objection. Change the call shape, never an assertion. If an assertion has to change to keep a test green, **stop and report** — that means behaviour moved.
3. **"Four helpers run before Invocation is built in main()" — ACCEPTED as a real finding, now in scope.** Reordering `main()` is authorised. **Constraint: the current order is load-bearing in at least one place** — `get_env_config()` runs before `load_configuration()` so the reporter has a log directory for warnings raised during config discovery. If your reordering changes *when* a warning or log line is emitted, that is a behaviour change: stop and report rather than absorbing it.
4. **Reference counts — FIXED.** Round 1 re-measured: `hook.py` 167 before / 153 after, `tools/installer.py` 42. My earlier figures omitted `config` and `agent_info`.
5. **Round 1's verification — ACCEPTED and independently re-run by me.** 4021 tests, ruff clean, three fitness checks, corpus 6401 in-process + 61 end-to-end with no differences, calibrated by a planted change. That is your baseline.
6. **Import ordering — FIXED by me** after round 1 (`invocation` sat between `error_log` and `error_reporter`).

**Two refinements to `Invocation` itself, both authorised:**

- **Fields a non-hook caller genuinely lacks should be `Optional` and `None`, not empty strings.** `api.decide` has no `cwd`, no `agent_info`, no `governed_tools`, no `permission_mode`. `None` says "not applicable here"; `""` is a lie that reads as data. Update the type hints and the docstring to say a non-hook evaluation context exists.
- **A factory classmethod is permitted** (e.g. `Invocation.for_evaluation(...)`) so `api.decide` and any test needing a synthetic one share a single construction site. **This does not relax "facts only, no behaviour"**: a constructor is not a decision. A method that resolves, caches, or decides anything is still forbidden.

## Steps and their completion artifacts

**TDD is NOT required and remains inappropriate** — this is behaviour-preserving. The existing suite and the verdict corpus are the specification; keeping them green *unchanged* is the proof. Where a test changes, it changes only in how it calls, never in what it asserts.

| # | step | completion artifact |
|---|---|---|
| 1 | Re-measure the fossils under the corrected criterion: every function in the in-scope modules taking any parameter available on the `Invocation` | the list, in the report, with a count |
| 2 | `invocation.py` refinements — Optional fields, factory, docstring | `test/unit/test_architecture.py`'s allow-list for it is still an empty `frozenset()` |
| 3 | `resolve.py` both resolvers take `Invocation` | suite green at the baseline counts |
| 4 | `api.py` constructs the `Invocation`; **public signature unchanged** | `grep` of `def decide` shows the same parameters as before |
| 5 | `hook.py` — the six helpers, plus any `main()` reordering | suite green; **and an explicit statement of whether log/warning emission order changed** |
| 6 | `permission_resolution.py`, `compound.py`, `file_matching.py`, `parser/*` | suite green |
| 7 | Fix the cascade in out-of-scope modules | every file listed in the report |
| 8 | Lint and format | `uv run ruff check .` clean; `uv run ruff format .` no reformatting needed |
| 9 | Architecture fitness | `--stdlib`, `--ambient`, `--layers` each exit 0; paste the last line of each. **`--layers` is the one to watch**: `invocation` is `foundation`, so any module may import it, but a *new* import edge in the wrong direction fails here |
| 10 | **Verdict-corpus equivalence** | `corpus_build.py --verify --strict-prose` -> `OK: no differences`, `6401` in-process, `61` end-to-end |
| 11 | **Calibrate the corpus before believing step 10** | plant a change you know alters a decision, confirm `--verify` FAILS, revert, confirm it passes, and confirm `git status --porcelain` is clean for the planted file. Paste all three |
| 12 | **Entry-point smoke test** | import each of the eight console-script modules named in `pyproject.toml` `[project.scripts]` and confirm each loads. Paste the result |
| 13 | Sibling sweep | see below |

**Baseline to match exactly:** `Ran 4021 tests` / `OK (expected failures=4)`; `ruff check .` -> `All checks passed!`; corpus `OK: no differences` at `6401` / `61`. **A changed test count is a finding, not a pass** — say which tests you changed and why.

**Sibling sweep (step 13).** After migrating, re-run your step-1 scan and report what remains: every function still taking a parameter available on an `Invocation` that is in hand at its call sites, with the reason it was left. "None remain" is a fine answer if true. Measured: 4 of 6 escaped-defect chains in this corpus were instance fixes where the class was already known — round 1 is itself an example.

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **That `extended_syntax` is always derivable from `env_config`.** I read one call site (`env_config.get("extended_syntax", True)`). If another path computes it differently, the `Invocation` may need it as its own field — decide, and say which you did and why.
- **That the six `hook.py` helpers are all genuinely migratable.** Round 1 gave two distinct reasons for deferring them and I have only checked the ordering one. If one resists for a reason neither of us has named, report it rather than forcing it.
- **That `compound.py`, `file_matching.py` and `parser/*` contain anything in scope.** Round 1 found `compound.py` and `parser/*` reference none of the statics. Under the corrected criterion they may still contain nothing. **An empty module is a finding about my scoping, not a failure of yours** — say so plainly instead of manufacturing work.
- **That `main()` can be reordered safely at all.** I know of one ordering constraint (finding 3). There may be others I have not found, and the corpus may not detect a change in *when* a log line is written, only in what the decision was.
- **That this stays behaviour-neutral.** That is the design claim, and step 11 is what tests it. If your planted change does **not** make the corpus fail, stop and report: the instrument is blind and step 10 means nothing.

**Report anything you find wrong, including in `toolguard-memories/TOO-28/TOO-28 implementation plan.md`.** Round 1's most valuable output was the correction that 1c/1d were empty and that my criterion was wrong. A correction to my premises is worth more than a clean run.