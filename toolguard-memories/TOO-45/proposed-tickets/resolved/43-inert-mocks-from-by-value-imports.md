---
title: Every mock in test_auto_migrate.py was inert, and the tests silently ran against
  the developer's real ~/.claude config
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/43-inert-mocks-from-by-value-imports
---

**FIXED in `05f786d` (TOO-45 phase 2).** The nine inert by-value-import mocks are gone from `test/unit/test_auto_migrate.py`; the ticket's own recommendation is self-retracted.

# Mocks that patch the defining module when the consumer imported by value

**Found 2026-08-13. Measured, not inferred: `mock.called == False` for all three patched functions.**

## The defect

`auto_migrate` imports `get_native_permissions`, `get_toolguard_permissions` and `find_divergent_patterns` **by value**:

```python
from toolguard.config_divergence import get_native_permissions, ...
```

All nine mocked tests patched `toolguard.config_divergence.*`. **`auto_migrate` holds its own references, so the real functions ran and the mocks were never consulted.** A fifth patch targeted `toolguard.config.discover_config_files`, which `load_configuration` never calls at all — it uses `_discover_levels`.

Only `patch("toolguard.auto_migrate.migrate")` ever took effect.

## Why it is worse than "the mocks did nothing"

The module has no `ConfigIsolationMixin`. With the mocks inert, `load_configuration` read **the developer's real `~/.claude` configuration**.

Measured at git HEAD: running the module under a `HOME` whose config contains `[permissions] allow = ["Bash(git status)"]` produces **9 failures**. The tests passed on this machine because of what happens to be in this machine's config.

So the module was:

- not testing what its names claimed,
- dependent on developer-machine state,
- and green throughout.

The repaired module now gives the same result under the real HOME, a hostile HOME, and an empty HOME.

## A FOURTH SHAPE, found 2026-08-13 — `wraps=` defeated by `return_value`

Measured on Python 3.14.5. Two tests in `test_git_helper.py` did:

```python
with patch("...run_git", wraps=_git.run_git) as spy:
    spy.return_value = None
```

**An explicit `return_value` defeats `wraps`.** The wrapped real function is never called — so the `wraps=` argument was **pure decoration that made the test read as an end-to-end check it was not.** A reader sees `wraps=` and believes the real code ran.

Both were replaced with a plain `patch.object(..., return_value=None)`, which at least says what it does.

**And the docstrings described the trap itself.** Both tests said *"When `toolguard._git.run_git` is patched to a spy"* while actually patching the **caller's** binding. The stated form would have been a **no-op**, because both callers import `run_git` by value — so the Gherkin documented the broken approach as if it were the working one.

## A FIFTH SHAPE, found 2026-08-13 — a constant captured into a DEFAULT ARGUMENT

```python
def parse_architecture_config(pyscn_toml_path: Path = PYSCN_TOML): ...
```

The default is evaluated **once, at import**, and every call site calls it with no arguments. So `patch.object(module, "PYSCN_TOML", ...)` is **provably inert** — falsified: under the patch the result is byte-identical to baseline, while passing the value explicitly flips the verdict.

**Distinct from the import-time-constant shape** (`decision_ledger.USER_LEDGER_PATH`): there the constant is *read* at import; here it is *captured into a signature*. Patching the constant cannot reach it either way, but the two need different fixes — redirect the constant vs. patch the function.

**It generalises within its module**: `TOOLGUARD_DIR` and `REPO_ROOT` are bound the same way across most of `architecture_fitness.py`, so **any future test patching those will be silently inert.**

It produced two cannot-fail tests, one asserting a result was *unchanged* under a patch that changed nothing.

## The five shapes, for the sweep

1. **Wrong target** — patching the defining module when the consumer imported by value.
2. **Target never reached** — the patch target is correct but the code never calls it.
3. **Guard/decorator wrapper** — the imported name is a wrapper, so mutating the raw function is inert twice over.
4. **`wraps=` defeated by `return_value`** — reads as end-to-end, executes nothing.

Shapes 1 and 3 are statically detectable. Shape 4 is too: `wraps=` and `return_value` on the same mock is always a contradiction and can be flagged by grep.

## THE REPO-WIDE SWEEP WAS RUN 2026-08-13. Both of this section's claims are wrong.

The sweep this section recommends was written as an AST pass and executed against the whole suite. **Its two load-bearing claims — "probably not unique" and "does not need judgement per site" — did not survive.**

**Measured, with the checker first validated against the known case** (it maps 290 by-value `(source, name)` pairs and does flag all three `test_auto_migrate` targets as they stood at HEAD, so a low count is a real negative and not a broken instrument):

| shape | sites repo-wide | verdict |
|---|---|---|
| **1 — patch the definer while a consumer imported by value** | **6**, five of them the same name (`toolguard.config.find_project_root`) | none is obviously inert: in each, the code under test is plausibly the *definer*, so the patch lands correctly. **The shape is close to absent outside the module that produced this ticket.** |
| **4 — `wraps=` with an explicit `return_value=`** | **0** | grep-able exactly as claimed, and already extinct — the two instances were the `test_git_helper` pair fixed here |
| **test's-own-holder** (the file imports the name by value *and* patches only the definer) | 38 co-occurrences | **noise.** Spot-checked `test_tools_security_audit.py:1194`: `main()` looks up `security_audit` as a module global, so the patch applies; the file's bare calls are in *different* tests, never under the patch. |

**"Does not need judgement per site" is false, and that is the durable lesson.** Deciding whether a patch is inert requires knowing *which scope calls the name* — the file-level co-occurrence a grep can see is not evidence either way. The check needs scope analysis, and even then the last word is whether the call under the patch reaches the patched binding, which is a question only execution answers.

**So the recommendation changes**: do not commission a repo-wide mechanical sweep. It has now been run and it found nothing actionable. **Falsifying each patch in the module being repaired — the campaign's existing per-module discipline — is what actually finds these**, and every instance of shapes 1, 3, 4 and 5 recorded in this ticket was found that way, not by grep.

## The original claim, retained for the record

**The check:** for every `patch("module.name")` in the suite, if the consuming module does `from module import name`, the patch is inert unless it targets `consumer.name`.

This is the test-side face of the by-value import trap the campaign already hit twice on the *mutation* side — where patching only the defining module silently produced false zero-detection readings. Same root cause, opposite consequence: there, a covered mechanism looked uncovered; here, an uncovered mechanism looked covered.

**Recommend a repo-wide sweep for the pattern.** It is grep-able and does not need judgement per site.

## What was found underneath, once the mocks were made real

- **Nothing in the module verified what auto-migration WROTE.** Every test stubbed `migrate()`; the module verified only that success was *reported*. There is now one end-to-end test that drives the real `migrate()` and asserts the pattern left `settings.local.json`, arrived in `toolguard_hook.toml`, and that both files were backed up first. It is also the module's first test to reach `config_write_guard.verified_write_config` — under which tickets 39 and 40 sit.
- **A red test**: `MigrationOutcome.SUCCEEDED` includes the "nothing to migrate" no-op, and `run_auto_migration` announces its own **pre-analysis** count. Measured with the real `migrate()`: a run that wrote nothing and a run that migrated one pattern produce **byte-identical stderr** (`Successfully migrated 1 pattern(s)`) and both return `True`. The user is told a count nothing produced. Fix is production-side — `migrate()` must return what it wrote.
- **Two claims in my own working notes were false**, both because the notes reasoned about a mock nobody had verified was reached.

## Related

The success notice is derived from data discarded before the write — the "prose is output, not a data structure" pattern, in the config-writing path. Same family as proposed ticket 38.