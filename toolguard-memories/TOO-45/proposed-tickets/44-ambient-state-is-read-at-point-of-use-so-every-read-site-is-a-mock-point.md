---
title: Ambient state is read at point of use, so every read site becomes an independent
  mock point
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/44-ambient-state-is-read-at-point-of-use-so-every-read-site-is-a-mock-point
---

# 485 patches, zero autospec, and one root cause

**Written 2026-08-13 in answer to Arnon's question: does the code's structure make mocking harder and more error-prone than it needs to be?**

**Yes.** Measured across the package and the suite.

## The measurements

| | count |
|---|---|
| `patch(` occurrences in `test/` | **485** across 33 files |
| uses of `autospec` anywhere | **0** |
| test files using `ConfigIsolationMixin` | 18 of 79 |
| `Path.home()` calls in production | **23**, across **10 files** |
| `os.environ` reads in production | 19, across 8 files |
| `Path.cwd()` / `os.getcwd` | 6 |

The most-patched targets say the rest:

| target | patches |
|---|---|
| `sys.stdin` | 59 |
| `sys.stdout` | 58 |
| `toolguard.hook.log_command` | 56 |
| `toolguard.hook.load_configuration` | 35 |
| `sys.stderr` | 29 |
| **`pathlib.Path.home`** | **18** |
| `builtins.print` | 11 |

## The diagnosis

**Ambient state is read at the point of use, deep in the call graph, instead of being resolved once at the edge and passed down.** Every read site becomes a seam a test must know about individually.

Three consequences, each visible in the numbers:

1. **`Path.home()` is called in ten different files, so there is no single seam to control.** The suite's response is to patch **`pathlib.Path.home` itself — the standard library — 18 times. That is the tell: when tests patch stdlib, the codebase has not offered them anything better. `path_utils.py` already calls it 4 times and is the obvious owner; nothing routes through it.

2. **~157 patches exist purely to control I/O** (`sys.stdin`, `sys.stdout`, `sys.stderr`, `builtins.print`). The hook does I/O inline rather than through an injected writer. **TOO-45 item #04 already solved exactly this shape once** by introducing `error_reporter` and routing stderr through it — the precedent exists, it just was not extended to stdin/stdout.

3. **By-value imports make the correct patch target non-obvious**, and getting it wrong fails *silently and permissively*. Proposed ticket 43 is the measured instance: every mock in `test_auto_migrate.py` was inert, the tests read the developer's real `~/.claude`, and they were green.

## Why this is a design problem and not a testing problem

A mock is a seam. **The number of mocks a suite needs is a measurement of how many implicit dependencies the code has** — 485 is that measurement. Reducing it is not a test-quality exercise; it is removing hidden inputs.

The relevant standing preference already covers it: threading state repeatedly is a design signal, and the answer is an invocation-scoped object holding facts and nothing else. Here that object is obvious — **home, cwd, environment and project root, resolved once per hook invocation** and passed down. toolguard is one process per tool call, so there is exactly one correct value for each, for the whole process lifetime.

## Fix directions, cheapest first

1. **One accessor for `Path.home()`**, in `path_utils`, that everything calls. Turns 10 seams into 1 and makes patching `pathlib.Path.home` unnecessary.
2. **Extend the `error_reporter` treatment to stdin/stdout.** Would retire the largest single block of patches.
3. **An invocation-scoped context object** carrying the resolved ambient values. The largest change and the one that removes the category rather than shrinking it.

## The shape of the fix, per Arnon 2026-08-13

**A thin wrapper around each frequently-mocked thing, so tests mock at the wrapper's use point instead of at every use point.** That is the general form of the three directions above, and it is what makes the problem tractable: the wrapper does not need to be clever, it needs to be *the only door*.

The three candidates in descending patch count:

| wrapper | retires |
|---|---|
| stdin/stdout writer, extending the existing `error_reporter` pattern | ~157 patches |
| a single `home()` accessor in `path_utils` | 18 `pathlib.Path.home` patches, 10 seams |
| environment access through `env_config` only | 12 of 19 reads |

`error_reporter` (item #04) already proves the pattern works in this codebase.

## THE TEMPLATE IS VALIDATED — measured 2026-08-13

`error_reporter` was checked against the standard this ticket proposes, and it holds:

- **zero ambient reads** — no `Path.home()`, no `os.environ`, no `Path.cwd()`. Its only external dependency is a `log_dir` **handed to it**.
- **one `patch()` in 24 tests**, against 18 `pathlib.Path.home` patches elsewhere in the suite.
- **completely indifferent to `HOME`**: 24/24 green under normal env, empty `HOME` + empty `XDG_CONFIG_HOME`, `HOME=/nonexistent`, and a foreign cwd — with no `ConfigIsolationMixin` and no `Path.home` patch.

That is the whole thesis of this ticket, demonstrated in a module that already exists.

### Four conditions a stdin/stdout writer must meet to inherit it

1. **Injected, not resolved.** The writer must be *handed* its streams at construction, the way `Reporter` is handed `log_dir`. **The moment it reads `sys.stdout` at point of use it becomes another of the 157 patch points rather than the thing that retires them.**
2. **One door, and the door must be observable.** A writer that leaves `print()` reachable beside it buys nothing.
3. **An ambient registry needs an identity handle.** `active()` is the one blind spot in `error_reporter`, and the reason generalises: a registry whose severities share a destination **cannot be tested through its output at all** — only through instance identity (shape 4). A stdout writer grows the same problem the instant it gains an ambient `active()`. Design the seam with it, or keep the stream explicitly threaded.
4. **The failure path must announce itself.** `_dispatch` already prints when its own log write raises — and nothing asserted it. A writer whose fallback is silent is ticket 29's "reports success having written nothing" family.

## Where the wrappers should LIVE — Arnon proposed a dedicated `testability.py`

His reasoning: a wrapper existing to help mocking is an oddball against "no runtime code aware of testing", but sits in a grey zone — it does not change behaviour under test, so its test-awareness is **passive, not acting**. That classification is right.

**Two objections to the dedicated module as the default destination:**

1. **The layer map forbids the obvious location.** `toolguard/testing/` is the `support` layer, declared *"May reach anywhere; nothing may depend on it."* A `testability.py` that production imports inverts that rule. It would have to live in `foundation` — a module named for testing at the bottom of the architecture, which is a stranger artifact than the one it labels.

2. **Most of these wrappers are not test-only, and that is what makes them worth building.**
   - a `home()` accessor gives one place to resolve the home directory **and one place to handle it raising** — which is ticket 23's root cause, since `Path.home()` raising is exactly what makes the hook emit nothing
   - an I/O writer is what `error_reporter` already is, introduced by item #04 for routing and suppression
   - environment access through `env_config` is the intended design already; the 12 stray reads are drift

   Filing those under `testability.py` **mislabels them** and invites a later reader to delete them as scaffolding.

**Proposed criterion instead of a blanket destination — would you keep this wrapper if the test suite vanished tomorrow?**

- **Yes** → it belongs in its natural home, with a docstring naming the *production* problem it solves. Testability is a consequence, not the justification.
- **No** → `testability.py`, honestly labelled, exactly as Arnon describes.

**Keep the module in the design as the named destination for whatever fails that test** — expected to be small, possibly empty. Without it, the temptation is to smuggle a test-only wrapper into a real module and say nothing.

## SEQUENCING — this should be the FIRST code change after the suite is green

Arnon's question: is this the first fix involving code changes, once the reds are resolved? **Yes, with one ordering constraint.**

**Not before phase 2.** The 18 red tests are live user-facing defects — a permission bypass, a config-bricking write, a hook that emits nothing, a hard deny that can be inverted, `settings.json` overwritable with `null`, a `sudo` escape from self-integrity. Those outrank an internal quality problem. And doing a refactor that touches many tests *while* reds are outstanding destroys the signal: you could not tell whether a red went green because the defect was fixed or because the refactor changed what the test exercises.

**But before phase 4**, and this is the load-bearing part. Phase 4 adds coverage where there is none — **every new test written against the current structure is a new mock point that the refactor will then have to migrate.** Writing them first means doing that work twice, and the second pass is the one where a mistake is silent.

So: **phase 1 (tests) → phase 2 (green) → THIS → phase 3 remainder → phase 4 (new coverage).**

## What NOT to do

Do not add mock-verification boilerplate as the primary answer (see the companion note on that question). It is worth doing, but it is a detector for a defect the structure keeps producing — and detectors do not reduce the 485.