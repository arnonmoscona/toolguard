---
title: brief-phase1-round3
type: note
permalink: toolguard/too-28/brief-phase1-round3
---

# Brief: TOO-28 Phase 1 round 3 -- thread Invocation through the engine layer

## Task

Round 2 threaded `Invocation` through `hook.py`, `resolve.py` and `api.py`, then stopped at the engine layer. It left `permission_resolution.py`, `compound.py`, `file_matching.py` and `parser/*` alone, arguing that those modules are deliberately typed against **Protocols** (`ResolutionConfig`, `ResolveConfig` in `config_types.py`) and that threading a concrete `Invocation` into them would trade a structural contract for a coupling and hurt isolated testability.

**Arnon rejected that argument on 2026-09-05, and he is right:**

> *"A Protocol expresses what something **must have**, not what something **might have**. So it can express 'I need something that gets me something of this shape'. Since Invocation just packages existing shape things into an object that allows you to access them, but generally does not change the shape of the things it contains, then the existing protocols can be refactored too so that they still serve the purposes they serve today and do not broaden their requirements. It's just how the way the desired class or 'shape' is described is what changes."*

The requirement does not broaden; it is stated one level out. Concretely:

```python
class ResolutionContext(Protocol):
    tool_name: str
    extended_syntax: bool
    @property
    def config(self) -> ResolutionConfig: ...
```

Isolated testability survives: a test builds a small object carrying those fields instead of a config double.

**Your job: finish the threading through the engine layer, refactoring the Protocols rather than discarding them.**

**Phase 1 remains behaviour-neutral.** Nothing may change a decision. `permission_mode` becomes reachable; nothing reads it to alter a verdict.

## Scope and widening

**In scope:**

- `toolguard/permission_resolution.py` -- `resolve_command_permission(config, tool_name, command, extended_syntax, *, spellings)` and its siblings. `config`, `tool_name` and `extended_syntax` are all on the `Invocation`.
- `toolguard/compound.py`, `toolguard/file_matching.py`, `toolguard/parser/*` -- wherever a parameter is available on the `Invocation`. Round 2 said several genuinely have them; re-measure rather than trusting either of us.
- `toolguard/config_types.py` -- **add the context Protocol(s)**. Refactor, do not replace: `ResolutionConfig` and `ResolveConfig` keep serving what they serve today, and the new Protocol is expressed in terms of them.
- `toolguard/resolve.py` -- two loose ends round 2 flagged: `_hard_deny_additional_context` (one of its two params is a genuine fossil; the other is sometimes a hardcoded `"Bash"` literal), and whether `_decide_bash` should share `decide`'s `Invocation` rather than building its own.

**Out of scope for NEW BEHAVIOUR, in scope for the refactor's own fallout** -- unchanged from round 2, and it matters more here because the engine layer has more callers. Every entry point, tool, and test module that a signature change breaks **must** be fixed. Do not give any of them new behaviour. List every file you touched this way.

**Is widening authorised? NO, except for that cascade.**

**Decided, do not re-open:**

- **`Invocation` stays in the `foundation` layer with an empty import allow-list.** It must not import `config_types` to type `config` properly. That would move it into the `config` layer, and `log_writer.py` is in **observability**, *below* config -- so an invocation stuck at config level could never be threaded there if a later phase needs it. **The consequence is accepted deliberately**: because `Invocation.config` is `Any`, a type checker will not catch an invocation whose config lacks the required methods. The Protocol still states the requirement for readers and for anything that does check; static enforcement at that one seam is traded for keeping the object reachable from every layer.
- **`api.decide`'s public signature does not change**, as in round 2.

## Findings carried forward

1. **"Protocols make this coupling wrong" -- REJECTED.** Arnon's argument above. The Protocol is refactored, not discarded.
2. **`extended_syntax` is NOT derivable from `env_config` -- ACCEPTED, already fixed in round 2.** `api.decide` receives it from its own caller; it is now its own `Invocation` field. This was a genuine bug caught: following my round-2 brief would have silently dropped an explicit `extended_syntax=False` from every tooling caller. **Do not undo it.**
3. **`main()` needs no reordering -- ACCEPTED.** Round 2 built a partial `Invocation` early and `dataclasses.replace()`-d it as later fields arrived, preserving call order and log emission timing exactly. Keep that approach.
4. **`_resolve_event` migrated -- ACCEPTED**, found by round 2's own sibling sweep and not named in its brief.
5. **Round 2's verification -- ACCEPTED and independently re-run by me**: 4021 tests, ruff clean, three fitness checks, corpus 6401 in-process / 61 end-to-end with no differences and calibrated, `api.decide` signature confirmed unchanged, and **all eight console entry points confirmed to load**. That is your baseline.
6. **Deferred siblings from round 2** -- `load_file_path_patterns`, `_command_target_key`, `_governed_tool_verdict`, `_resolve_reporter_log_dir`. Re-examine under the corrected criterion; each was deferred for a stated reason and some of those reasons may not survive this round's wider scope. Report your disposition for each by name.

## Steps and their completion artifacts

**TDD is NOT required and remains inappropriate** -- behaviour-preserving refactor. The suite and the verdict corpus are the specification. Where a test changes it changes only in how it calls, never in what it asserts. **If an assertion must change to stay green, stop and report** -- that means behaviour moved.

| # | step | completion artifact |
|---|---|---|
| 1 | Re-measure: every function in the in-scope modules taking any parameter available on an `Invocation` | the list, in the report, with a count |
| 2 | Add the context Protocol(s) to `config_types.py`, expressed in terms of the existing ones | the Protocol definition, quoted in the report |
| 3 | `permission_resolution.py` migrated | suite green at the baseline counts |
| 4 | `compound.py`, `file_matching.py`, `parser/*` migrated, or reported empty with evidence | suite green |
| 5 | `resolve.py` loose ends: `_hard_deny_additional_context` and the `_decide_bash` sharing question | a decision on each, with reasoning |
| 6 | Round 2's four deferred siblings re-examined | a disposition per function, by name |
| 7 | Fix the cascade in out-of-scope modules | every file listed |
| 8 | Lint and format | `ruff check .` clean; `ruff format .` no reformatting needed |
| 9 | Architecture fitness | `--stdlib`, `--ambient`, `--layers` each exit 0. **`--layers` is the one to watch**: `invocation` must still be `foundation` and its ratchet entry in `test/unit/test_architecture.py` must still be an empty `frozenset()` |
| 10 | Verdict-corpus equivalence | `OK: no differences`, `6401` in-process / `61` end-to-end |
| 11 | **Calibrate the corpus before believing step 10** | plant a change that alters a decision, confirm `--verify` FAILS, revert, confirm it passes, confirm `git status --porcelain` clean for that file. Paste all three |
| 12 | **Entry-point smoke test** | all eight `[project.scripts]` console scripts still load |
| 13 | Sibling sweep | what remains, and why |

**Baseline:** `Ran 4021 tests` / `OK (expected failures=4)`; `ruff check .` -> `All checks passed!`; corpus `OK: no differences` at `6401` / `61`. **A changed test count is a finding, not a pass.**

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **That the Protocol refactor is as cheap as Arnon and I think.** Neither of us has written it. If `ResolutionConfig` is consumed in a way that resists being wrapped -- passed onward to something that needs the bare config, or used where no `Invocation` exists -- that is a real finding, not an obstacle to route around. **Report it rather than forcing a shape that fights the code.**
- **That `compound.py`, `file_matching.py` and `parser/*` contain anything in scope.** Round 1 said they reference none of the statics; round 2 said several genuinely have Invocation-shaped parameters. **Those two statements disagree and I have not resolved which is right.** Measure, and say which was correct.
- **That every engine function has an `Invocation` in hand at its call sites.** Some are called from tests, and some may be called from paths where no invocation exists. Where one genuinely does not, say so by name -- do not fabricate an `Invocation` to satisfy a signature.
- **That keeping `Invocation` in `foundation` is right.** The reasoning is in Scope. If you find a concrete case where the `Any` typing lets a real error through that the old signature would have caught, that is worth more than the layering argument -- report it.

**Report anything you find wrong, including in `toolguard-memories/TOO-28/TOO-28 implementation plan.md`.** Both previous rounds produced their most valuable output as corrections to my premises: round 1 that my criterion was wrong, round 2 that my `extended_syntax` assumption was false and would have shipped a silent bug.