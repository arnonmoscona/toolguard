---
title: Blind estimate (uncertainties) - item 15 migrate lock
type: note
permalink: toolguard/too-45/reports/surprise/15-estimate-uncertainties
tags:
- task-memory
- TOO-45
- measurement
---

## Named uncertainties

### 1. Does an exclusion primitive already exist in the package, making the "new wrapper module" premise wrong?

**Check:** `grep -rnE "flock|lockf|msvcrt|LOCK_EX|LOCK_NB|BEGIN IMMEDIATE|IMMEDIATE TRANSACTION" toolguard/ test/`

**Effect by mechanism:** if the claim store already holds an exclusive transaction or an OS lock, this stops being "add a primitive" and becomes "expose the one that exists to a second caller" — the production side collapses to two edits, no new module, no layer-map entry, no new isolation seam, and the whole test-side ripple disappears. If nothing matches, the wrapper is genuinely new and everything the convention attaches to a new home-writing module comes with it.

### 2. Is there a shared resolver for `~/.toolguard`, or does each writer derive it itself?

**Check:** `grep -rn "\.toolguard" toolguard/*.py toolguard/**/*.py` and `grep -rnE "Path\.home\(\)|expanduser" toolguard/`

**Effect by mechanism:** a single existing resolver means the lock calls it and inherits whatever test redirection already exists — nothing new is needed to keep tests off the real home. A second independent derivation means a second thing tests must redirect, which is precisely the situation the guard convention was invented for, and it adds both an isolation helper and a guard rather than reusing one.

### 3. What is `migrate()`'s current return shape — structured result, or bool/None?

**Check:** `grep -rn "def migrate" -A 30 toolguard/` for the return annotation, plus `grep -rn "migrate(" toolguard/ test/` for how callers consume it.

**Effect by mechanism:** if it already returns a structured result object, "declined, lock held" is a new variant on an existing type and callers barely move. If it returns a bare bool or None, the decline cannot be expressed without inventing a result type, which drags every caller and every caller's tests into the change — that is the difference between a two-file production change and a four-file one. This is also the CLAUDE.md prose-vs-structure trap: the decline must not be communicated only as a message string.

### 4. How does the error reporter get its context, and can a CLI process construct one?

**Check:** `grep -rn "def report_notice\|def report_warning\|def report_fault\|class .*Reporter" toolguard/error_reporter.py` and `grep -rn "error_reporter" toolguard/ | grep -v test`

**Effect by mechanism:** the ticket mandates the reporter rather than stderr. If the reporter needs hook-supplied session context, the CLI path needs new wiring to construct one, which pulls the script and its tests in. If it is a module-level function usable from any process, the reporting is one import and one call.

### 5. Which layer can the lock live in, given who must import it?

**Check:** read the layer stanzas in the layer map and run the layer-direction checker (`uv run python tools/architecture_fitness.py`), then `grep -rn "^from toolguard\|^import toolguard" ` on the migration module to see its current layer neighbours.

**Effect by mechanism:** if both a config-layer and a runtime-layer module end up importing the lock, it must sit at foundation; getting that wrong fails a fitness predicate rather than merely looking odd, and the correction is an extra config edit plus an assertion update. It also decides whether the lock may call the reporter at all, or must return a status upward for someone else to report — which changes where the failure-behaviour code lives.

### 6. Is there an existing pattern for spawning real concurrent processes in the test suite?

**Check:** `grep -rnE "subprocess\.(Popen|run)|multiprocessing|os\.fork" test/`

**Effect by mechanism:** the ticket explicitly rejects a single-process happy-path test, so real processes are required. An existing harness means the concurrency tests fold into a normal test module; no existing pattern means a shared helper (and probably a child-process entry script) is authored, adding files the estimate may have missed and slowing the suite in a way that gets noticed.

### 7. Does the test package auto-register isolation and guards, or does each test import them?

**Check:** read the top-level test package `__init__` for import side effects and any `setUpModule`/registration hooks.

**Effect by mechanism:** auto-registration means one package-level edit covers every test that would otherwise touch the real home; per-test imports mean no package edit but edits scattered across more test modules. Same total work, different file count — this is a pure precision risk for the estimate, not a design question.

### 8. Is `~/.toolguard`'s content inventoried anywhere that a new state file must be added to?

**Check:** `grep -rn "\.toolguard" docs/ README.md` and `grep -rn "\.toolguard" toolguard/tools/self_integrity.py toolguard/tools/uninstall_readiness.py`

**Effect by mechanism:** a new persistent file under the tool's own home tends to pull in whatever enumerates that directory — uninstall guidance, self-protection patterns, install docs. If those enumerate by directory glob, nothing changes; if they enumerate by filename, each list is another edit and the doc surface of this "narrow" item grows.

### 9. How is "a project" identified by the existing claim store, and will the lock agree with it?

**Check:** `grep -rn "project" toolguard/once_per_store.py | grep -iE "key|hash|root|normal"` and `grep -rn "def .*project_root" toolguard/`

**Effect by mechanism:** the requirement "per project, and two projects must not block each other" is only as good as the key. If a canonical project-key function exists it is reused and the requirement is nearly free. If not, a new keying rule is invented and there are now two notions of project identity in the same directory — a divergence that no test will catch unless one is written specifically for it, and the "different projects do not block" test would pass while still being wrong about symlinked or nested roots.

### 10. Does the codebase already have a platform-conditional import pattern to follow?

**Check:** `grep -rnE "sys\.platform|platform\.system\(\)|except ImportError" toolguard/`

**Effect by mechanism:** the Windows branch cannot be executed on this machine, so it will be exercised by patching. If there is an established pattern for platform gating, the wrapper follows it and its tests are cheap. If there is none, the branch is either untested (and the fitness/coverage checks will say so) or tested by an elaborate patching scaffold that is itself the most fragile new code in the change.

---

## What in the briefing looks misleading

- **The inventory omits the memories tree entirely.** Every other item in this series has produced implementation reports and task-recall notes under it, and those are real touched files. I excluded them because the briefing gave me no way to see the convention. If the scorer counts them, my numbers move for a reason the briefing structurally could not show — that is a measurement artefact, not an estimation error.

- **First-docstring-line-only actively hides capability.** `toolguard/once_per.py` is described as a facade for "throttling a warning or action to at most once per period". A facade for holding a claim over an action is one generalisation away from being exactly the mutual-exclusion primitive this ticket asks for, and the briefing cannot tell me whether it already is. If it is, uncertainty 1 fires and my central prediction of a new module is wrong.

- **Line counts say nothing about concurrency.** A 541-line sqlite-backed store is very likely to have transactional semantics already; the briefing presents it as merely large. Conversely a 1198-line migration module tells me nothing about whether the read-modify-write is one function or spread across five, which is the difference between a tidy `with` block and a restructuring.

- **The two existing helper files whose names imply the convention (`test/unit/_once_per_isolation.py`, 36 lines, and `test/unit/_real_once_per_home_guard.py`, 131 lines) are ambiguous about scope.** The docstring of the second says "the developer's real..." and is truncated exactly where it would tell me whether it guards all of `~/.toolguard` or only one store path. That single truncated line is the difference between adding a guard file and editing one.

- **The layer map excerpt does not match the layer order I was given in the task framing.** The comment block in the excerpt reads `foundation < config < engine < api < runtime < tooling < support`, with no `observability`, while the surrounding context states `foundation < observability < config < ...`. One of the two is stale. Since this item must decide where a new module sits and whether it may call the reporter, that discrepancy sits directly on the load-bearing decision — worth resolving before the module is placed rather than after the fitness check complains.

- **No test-runner or coverage configuration appears in the inventory** beyond `pyproject.toml`, so I cannot tell whether adding a module triggers a mechanical registration edit anywhere. I assumed auto-discovery; if there is a manual list, I am under-predicting by one file.
