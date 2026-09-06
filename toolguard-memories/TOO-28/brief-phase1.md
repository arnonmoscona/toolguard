---
title: brief-phase1
type: note
permalink: toolguard/too-28/brief-phase1
---

# Brief: TOO-28 Phase 1 (tranches 1b, 1c, 1d) -- complete the invocation-context refactor

## Task

`toolguard/hook.py` loads several things once per run -- `env_config`, `config`, `governed_tools`, `hook_data`, `agent_info`, `permission_mode` -- then passes some of them down and drops others. Which subset a given function receives records when it was written, not what it needs. These are **fossil signatures**.

Phase 1a (already committed to the working tree, not to git) introduced `toolguard/invocation.py`: a frozen `Invocation` dataclass holding those statics, built once in `hook.py:main()` and passed as one explicit argument. It currently reaches only `_handle_file_path_tool` and `_handle_command_tool`, and only `permission_mode` has been migrated off their parameter lists.

**Your job: finish the migration.** Make `Invocation` the way the hook decision path receives these statics, and remove the now-redundant individual parameters.

**The requirement this serves** (do not implement it -- it is Phase 2, a later ticket phase): `permission_mode` must eventually be readable at the fallback resolvers and at the ASK-floor application point, so a later phase can make those auto-mode-aware. Phase 1 only makes it *reachable*. **Phase 1 changes no decision.**

**Behaviour-neutrality is the hard requirement of this whole phase.** Arnon, 2026-09-05: *"It does not change external behavior so while tests may have to change - replay behavior must remain identical with no change."*

## Scope and widening

**In scope -- the hook decision path only:**

- **1b** -- `toolguard/hook.py`. The largest tranche: 77 of ~133 references to the statics live here. Remove the redundant parameters from `_handle_file_path_tool` and `_handle_command_tool` (they still take `tool_name`, `tool_input`, `config`, `env_config`, `agent_info` alongside `invocation`), and from the private helpers below them where the value is available on the `Invocation`.
- **1c** -- `toolguard/config.py`, `toolguard/config_validation.py`, `toolguard/config_divergence.py`.
- **1d** -- `toolguard/resolve.py`, `toolguard/permission_resolution.py`, `toolguard/compound.py`, `toolguard/parser/*`, `toolguard/log_writer.py`.

**Explicitly OUT of scope -- do not touch:**

- `toolguard/tools/installer.py` (13 references), `toolguard/tools/security_audit.py`, `toolguard/tools/maintenance.py`, `toolguard/session_start.py`, `toolguard/update_check.py`, `toolguard/permission_migration.py`, `toolguard/tools/update_skills.py`. `pyproject.toml` declares **eight** console scripts; `toolguard.hook:main` is one, and these are separate entry points with their own lifecycles that `hook.py` imports none of. An object named for one hook invocation has no meaning inside `toolguard-install`. Arnon has separately ruled installer changes out of this ticket.
- `test/verdict_corpus/**` -- a frozen baseline. Changing it invalidates the goldens.
- Anything that changes a decision. No new settings, no auto-mode behaviour, no reading `permission_mode` to alter a verdict.

**Is widening authorised? NO.** Not to other entry points, not to adjacent cleanups, not to fixing unrelated fossil signatures you will certainly notice. This tranche is deliberately mechanical so that its review can be mechanical. If you find something that should change and is out of scope, **report it, do not do it.**

**One exception, and only this one:** if migrating a parameter forces a signature change in a helper not named above but genuinely inside the hook decision path, do it and say so in the report under judgements.

## Findings carried forward

Not a previous round of this task, but four decisions already made that you must not re-open, and one defect to fix:

1. **Explicit argument, never an ambient singleton or module global.** Rejected deliberately. `tools/corpus_build.py` drives 6401 decisions **inside one process**, so invocation state in a global would leak between cases in the very harness that proves the refactor changed nothing -- producing a clean, plausible, wrong result. This is not a style preference.
2. **`Invocation` holds facts and has no behaviour.** Do not add a method that decides anything, resolves anything, or caches anything. If you find yourself wanting one, report it instead.
3. **`Invocation.config` is typed `Any` on purpose.** `config` and `resolve` deliberately have **no import edge** between them -- they call each other through an injected callback, measured at 46,481 calls. `invocation.py` must keep importing nothing from `toolguard`; its architecture allow-list in `test/unit/test_architecture.py` is an empty `frozenset()` and must stay empty. **If you need to import `toolguard.config` into `invocation.py`, stop and report -- that is a blocking design question, not a detail.**
4. **The local aliases in 1a are scaffolding to be removed by you.** `hook.py` has `permission_mode = invocation.permission_mode` in both handlers, tagged `TOO-28-SCAFFOLD`. 1b should delete them and use `invocation.permission_mode` at the ~6 use sites, unless that makes a line unreadable -- your call, stated in the report.

**Defect to fix (mine, found after 1a landed):** `hook.py` around line 1272 carries `# TOO-28-SCAFFOLD: the sentence above stops being true in phase 1z.` **That claim is wrong.** Phase 1 is behaviour-neutral throughout, so the sentence it refers to -- *"it never affects the verdict itself"* -- stays true through all of Phase 1 and only becomes false in **Phase 2**, when auto-mode fallbacks first change a verdict. Correct the marker to say Phase 2.

## Steps and their completion artifacts

**TDD is NOT required here and would be inappropriate.** This is a behaviour-preserving refactor: there is no new behaviour to drive out with a failing test, and writing tests that assert the new signatures would be testing shape rather than behaviour. The existing 4021-test suite plus the verdict corpus *are* the specification, and keeping them green unchanged is the proof. Where a test must change, it must change **only** in how it calls the function -- never in what it asserts.

| # | step | completion artifact |
|---|---|---|
| 1 | Read `toolguard/invocation.py` and `hook.py`'s `main()` construction site; confirm this brief's claims (see the last slot) | a line in the report saying what you verified and anything you found wrong |
| 2 | **1b** -- migrate `hook.py`; delete the two `TOO-28-SCAFFOLD` aliases; fix the wrong Phase 1z marker | `uv run python -m unittest discover -s test -t .` passes with the same counts as the baseline below |
| 3 | **1c** -- migrate the three config modules | same suite green |
| 4 | **1d** -- migrate the decision path modules | same suite green |
| 5 | Lint and format | `uv run ruff check .` clean; `uv run ruff format .` reports no reformatting needed |
| 6 | Architecture fitness, all three | `uv run python tools/architecture_fitness.py --stdlib`, `--ambient`, `--layers` each exit 0; paste the last line of each |
| 7 | **Verdict-corpus equivalence -- the load-bearing one** | `uv run python tools/corpus_build.py --verify --strict-prose` prints `OK: no differences`. Paste the case counts |
| 8 | **Calibrate the corpus before believing step 7** | plant a change you know alters a decision, confirm `--verify` FAILS, then revert it and confirm it passes again. Paste both outcomes and confirm `git status --porcelain` is clean for the planted file |
| 9 | Sibling sweep | see below |

**Baseline to match exactly, measured 2026-09-05 on the current working tree:**

- `Ran 4021 tests` / `OK (expected failures=4)`
- `ruff check .` -> `All checks passed!`
- `--stdlib` -> `PASS`; `--layers` -> `All modules map to exactly one layer.` and `No cross-layer direction violations.`
- `corpus_build.py --verify --strict-prose` -> `OK: no differences`, `In-process: 6401 cases`, `End-to-end: 61 cases`

**A changed test count is a finding, not a pass.** If the number moves, say so and explain which tests you changed and why.

**Sibling sweep (step 9).** The fossil-signature pattern is the class; the four statics are the instances. After migrating, grep the in-scope modules for functions still taking two or more of `config`, `env_config`, `governed_tools`, `agent_info`, `permission_mode` as separate parameters where an `Invocation` is already in hand. **List every one you found and whether you migrated it.** Measured: 4 of 6 escaped-defect chains in this corpus were instance-fixes where the class was already known.

## This brief is unverified

**Do not take this brief on trust.** Specifically, these claims are mine and I may have them wrong:

- **The reference counts.** "77 of ~133 in `hook.py`", "13 in `tools/installer.py`" come from one grep of `env_config|governed_tools|hook_data` -- it does **not** count `config` or `agent_info`, so the real totals are higher and the proportions may differ. Re-measure before trusting the tranche sizing, and tell me the real numbers.
- **The tranche boundaries.** I grouped 1c and 1d by module name, not by call graph. If `compound.py` or `parser/*` turn out not to receive these statics at all, say so -- an empty tranche is a finding about my plan, not a failure of yours.
- **That `log_writer.py` belongs in 1d.** It takes `env_config` as `config=` in `log_command(...)`. That may be a different parameter with a colliding name rather than the same static. Check before migrating it.
- **That the aliases can simply be deleted.** I have not checked whether all ~6 `permission_mode` use sites in the handlers are inside functions that receive the `Invocation`.
- **That this is behaviour-neutral at all.** It is my design claim, and the corpus is what tests it -- which is why step 8 exists. If step 8's planted change does **not** make the corpus fail, stop and report: the instrument is blind and step 7's pass means nothing.

**Report anything you find wrong, including in the plan document** at `toolguard-memories/TOO-28/TOO-28 implementation plan.md`. A correction to my premises is worth more to me than a clean run.