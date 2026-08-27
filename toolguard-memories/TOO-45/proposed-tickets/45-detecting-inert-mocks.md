---
title: Detecting inert mocks - three mechanisms, and which of them catches what
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/45-detecting-inert-mocks
---

# Guarding against mocks that do nothing

**Written 2026-08-13 in answer to Arnon's second question: should every module that mocks carry a test verifying the mock actually works?**

**Yes — and the sharper version is cheaper and catches more.** But note first that there are *two distinct failure modes*, and no single mechanism catches both.

| failure mode | measured instance |
|---|---|
| **Wrong target** — patching the defining module when the consumer imported the name by value | `test_auto_migrate.py`: `patch("toolguard.config_divergence.find_divergent_patterns")` while `auto_migrate` holds its own reference. `mock.called == False`. |
| **Target never reached** — the patch target is correct, but the code never calls it | same module: `patch("toolguard.config.discover_config_files")`, which `load_configuration` never calls; it uses `_discover_levels`. |

## Mechanism 1 — a static check (catches wrong target, misses unreached)

For every `patch("mod.name")` in the suite, if the consuming module does `from mod import name`, the patch is inert unless it targets `consumer.name`. **This is decidable by reading the source; no test execution needed.**

`tools/architecture_fitness.py` is the natural home — it already owns repo-wide invariants of exactly this kind, and the check would cover all 33 patching files at once and could not be forgotten when a new module is added.

**Cannot catch** the unreached-target case: the patch target was perfectly correct there.

## Mechanism 2 — assert the mock was called (catches both, per test)

**This is Arnon's idea in its strongest form, and it is better than a separate canary test.** Rather than one test per module verifying "mocking works", make it a convention that **every patch is asserted to have been consulted**:

```python
mock_divergent.assert_called()          # or assert_called_once_with(...)
```

with an explicit annotation where a mock is deliberately expected *not* to fire.

Why this beats a separate canary test: a canary verifies that *a* mock in the module works. It does not verify that *this test's* mock worked. Mocks drift per test — a patch target that was right when written goes stale when production changes an import, and only the tests using that particular target break. A canary elsewhere in the file stays green.

It also documents intent: "this test depends on this call happening" is worth stating regardless.

**Cost:** one line per patch, and it does have to be remembered — which is the weakness a static check does not share.

### CORRECTION, Arnon 2026-08-13: this is white-box, and that limits where it applies

`assert_called()` requires the test to **know a priori that the mock must fire**. That is a white-box claim about the implementation, and it is **not universally true of mocks**.

Where it holds: **config isolation.** Almost every test knows the config will be read — that is why the test is isolating it in the first place. The assertion states something the test already depends on, so it costs nothing in coupling.

Where it does not: a mock standing in for a path that may or may not be taken — an error handler, a fallback, a cache miss, an optional notification. Asserting `called` there **converts an incidental dependency into a specified one**, and the test starts failing when a legitimate refactor stops taking that path. That is a worse defect than the one being guarded against, because it is a false alarm on correct code.

**So the convention must be scoped, not universal:** assert `called` where the call is part of what the test is asserting anyway — isolation seams above all — and leave it off where the call is incidental. A blanket rule would manufacture brittleness.

This also weakens mechanism 2 relative to mechanism 1: the static check makes no claim about what *should* happen at runtime, so it has no white-box cost at all.

## Mechanism 3 — `autospec=True` (free, currently used zero times)

**Measured: 485 patches in the suite, `autospec` used 0 times.**

`autospec` builds the mock from the real object's signature, so a call with the wrong arity or keyword fails instead of silently returning a `Mock`. It does **not** catch either failure mode above — a wrong-target autospec mock is still inert — but it is close to free and it catches a third class the campaign has also seen: production signature changes that leave a mock happily accepting the old call.

## Recommendation

- **Mechanism 1 as a fitness check** — highest coverage per unit of effort, cannot be forgotten, and this repo already has the machinery.
- **Mechanism 2 as a convention** — the only one that catches an unreached target, and the only one that is per-test rather than per-module.
- **Mechanism 3 by default** on new patches, since it costs a keyword argument.

## The caveat worth stating plainly

All three are **detectors for a defect the structure keeps producing.** Proposed ticket 44 measures the structural cause: ambient state read at point of use, 485 patches, `pathlib.Path.home` patched 18 times because the codebase offers no seam of its own.

Detectors are worth having — the campaign found the inert mocks by accident, and an accident is not a process. But **the number of mocks a suite needs is a measurement of how many implicit dependencies the code has.** Guarding the mocks does not reduce that number; it just stops it hurting silently.