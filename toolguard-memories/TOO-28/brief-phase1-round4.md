---
title: brief-phase1-round4
type: note
permalink: toolguard/too-28/brief-phase1-round4
---

# Brief: TOO-28 Phase 1 round 4 -- delete the unpacking aliases

## Task

Rounds 1-3 removed the loose parameters and made functions take one context object. Then, inside the bodies, they **re-created the unpacking they had just removed**:

```python
def _handle_command_tool(invocation: Invocation) -> RuntimeVerdict:
    tool_name = invocation.tool_name
    tool_input = invocation.tool_input
    env_config = invocation.env_config
    agent_info = invocation.agent_info
    permission_mode = invocation.permission_mode
    ...
```

**39 such lines across 4 files.** The signature got clean and the body kept doing the same work one level down.

Arnon, 2026-09-05: *"not sure why we need constructs like [these] - it just adds lots of lines without adding any clarity (there are quite a few of such instances). You can always choose a shorter name for the invocation variable in those cases (say, `inv`) if your goal is brevity at the use site."*

Round 2 justified the aliases as "used 7-15 times each, so inlining would be unreadable". **That justification is rejected**: if the use site is too wordy, the fix is a shorter parameter name, not N alias lines. Brevity is a naming problem, not a structural one.

**Your job: delete the pure aliases and read through the context object at each use site.** Behaviour-neutral. Nothing about any decision changes.

## Scope and widening

**In scope -- the 39 lines and their use sites:**

| file | count |
|---|---|
| `toolguard/hook.py` | 27 |
| `toolguard/permission_resolution.py` | 6 |
| `toolguard/resolve.py` | 3 |
| `toolguard/file_matching.py` | 3 |

**Only PURE aliases -- `x = <context>.x`.** These are NOT in scope and must stay:

- `takeover = invocation.config.takeover_mode()` (`hook.py:846`) -- a computed value, not an alias.
- `hook.py:677` `target = invocation.tool_input.get(key, "")` -- a lookup, not an alias.
- Any local whose name differs from the attribute, or that is reassigned later in the body. **If a local is reassigned, leave it and say so** -- collapsing it changes what the later code reads.

**The four `or {}` cases need a decision, not a blind edit.** `hook.py:81, 795, 847, 872` are `env_config = invocation.env_config or {}` -- an alias *plus* a None-default. Nothing anywhere distinguishes `None` from `{}` for this field. **Preferred fix: give `env_config` a non-None default in the dataclass** (`field(default_factory=lambda: MappingProxyType({}))`, the idiom already used in `rule_entry.py`), then the `or {}` disappears and the alias becomes pure. If you find a caller that genuinely relies on `None`, say so and keep the local instead.

**One real None check must survive**: `_run_startup_validation` does `config = invocation.config` then `if config is None: config = load_configuration(invocation.cwd)`. That is deliberate, documented behaviour with a test. Keep it working; the local may stay if removing it makes the branch worse.

**Renaming is permitted, not required.** `invocation` -> `inv` and `context` -> `ctx` are fine if you judge the use sites too wordy. **If you rename, rename consistently within each name's own scope** -- the concrete `Invocation` parameters and the Protocol-typed `context` parameters are deliberately different names because they are different types. Do not merge them.

**Is widening authorised? NO.** No new behaviour, no other cleanups. Fix cascade breakage only, as in rounds 2-3.

## Findings carried forward

1. **"Inlining would be unreadable at 7-15 use sites" -- REJECTED**, see Task. Shorter name, not aliases.
2. **`compound.py` is not "empty of functions taking config/tool_name/extended_syntax"** -- round 3's report said so and it is false: `check_compound_permission` takes `extended_syntax`. Its *conclusion* was right for a different reason -- it is a test-only helper (module comment at `compound.py:307`, all callers in `test_compound.py`), takes no `config` and no `tool_name`, and its callers hold no context object. **Nothing to do; recorded so it is not re-derived a third time.**
3. **`except ValueError, TypeError:` at `file_matching.py:113` -- ACCEPTED as correct.** PEP 758, and `pyproject.toml` declares `requires-python = ">=3.14"`. Verified pre-existing against tag `TOO-28-start-of-work`. Leave it.
4. **Rounds 1-3 verification -- ACCEPTED, independently re-run by me.** 4021 tests, ruff clean, three fitness checks, corpus 6401 in-process / 61 end-to-end no differences, all 8 entry points loading. That is your baseline.

## Steps and their completion artifacts

**TDD not required** -- behaviour-preserving. The suite and corpus are the specification. Tests should need **no** changes at all this round: nothing about any signature changes. **If a test needs touching, stop and say why** -- it means something moved that should not have.

| # | step | completion artifact |
|---|---|---|
| 1 | List the 39 candidate lines and classify each: pure alias / computed / reassigned / `or {}` | the classification, in the report |
| 2 | Decide the `env_config` default question | the decision and its reason |
| 3 | Delete the pure aliases, read through the context at use sites | suite green at baseline counts |
| 4 | Lint and format | `ruff check .` clean; `ruff format .` no reformatting needed |
| 5 | Architecture fitness | `--stdlib`, `--ambient`, `--layers` each exit 0 |
| 6 | Verdict-corpus equivalence | `OK: no differences`, `6401` / `61` |
| 7 | **Calibrate before believing step 6** | plant a decision-altering change, confirm `--verify` FAILS, revert, confirm it passes, confirm `git status --porcelain` clean for that file |
| 8 | Entry-point smoke test | all 8 `[project.scripts]` console scripts load |
| 9 | Sibling sweep | re-grep for `^\s*[a-z_]* = (invocation\|context\|inv\|ctx)\.` and report what remains and why |

**Baseline:** `Ran 4021 tests` / `OK (expected failures=4)`; `ruff check .` -> `All checks passed!`; corpus `OK: no differences` at `6401` / `61`. **A changed test count is a finding, not a pass.**

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **The count of 39** comes from one grep (`^\s*[a-z_]* = (invocation|context)\.`). It misses any alias written across two lines, assigned from a nested attribute, or using a different local name. **Re-measure and tell me the real number.**
- **That nothing distinguishes `None` from `{}` for `env_config`.** I checked the four `or {}` sites and nothing else. If a fifth reader branches on `is None`, my preferred fix is wrong.
- **That no local is reassigned after aliasing.** I did not check. If one is, collapsing it silently changes behaviour and the corpus may not catch it -- this is the highest-risk item in the round.
- **That removing the aliases actually reads better.** It is Arnon's judgement and mine, not a measurement. If a specific function comes out genuinely worse, **say which and why** rather than forcing it -- one concrete counter-example is more useful than compliance.

**Report anything you find wrong.** Every round so far has produced its most valuable output as a correction to my premises.