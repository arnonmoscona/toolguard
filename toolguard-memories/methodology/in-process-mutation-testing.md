---
title: In-process mutation testing - methodology
type: guide
tags:
- methodology
- testing
permalink: toolguard/methodology/in-process-mutation-testing
---

# In-process mutation testing

A method for measuring what a test suite can actually detect, developed and measured on the TOO-45 test-repair campaign (toolguard, Aug 2026). It is codebase-agnostic; toolguard appears below only as the worked example.

**Read this before running a mutation campaign, and again before trusting any number it produces.** Most of this file is about reading the measurement wrong, because that is where the time went.

## Why bother — the measured argument

One campaign, 77 test modules, 2,733 -> 3,628 tests, production code untouched throughout phase 1. The suite was green before and after. What the green suite could not see:

| mutation                                                            | tests that failed                    |
| ------------------------------------------------------------------- | ------------------------------------ |
| hard-deny bypassed entirely                                         | 1                                    |
| the parser grammar's delimiter character class destroyed            | 0 of 18                              |
| the config hierarchy inverted (and flattened, and each end dropped) | 0 of 33                              |
| the takeover ON/OFF pair                                            | 0 of 11                              |
| the installer's self-permission table widened to `Bash(*)`          | 0 of 5                               |
| the gate on writing a user's config without consent, removed        | 0 across all 5 modules that reach it |

Per-module survival rates before repair, measured: 47% (14 of 30), 55% (23 of 42), 58% (over 81 mutants). Near zero after repair in the same modules. The campaign filed roughly fifty production defect tickets, several security-shaped, from mutations alone.

**The pattern that generalised hardest: the mechanism a module is named for was usually its least-tested part.** A test file accumulates tests for the things that were easy to assert, and the headline mechanism is often the one only reachable through a wrapper, so nobody wrote a direct test for it.

**A read-only review is not a substitute.** On one module a careful reading pass reported "one minor redundancy"; mutation found 13 of 25 mechanisms at zero detection. On another, reading found nothing and mutation found five. Reading records that someone looked, not that nothing was there.

## The method

**Mutate the module under test in memory, run the suite, and diff the failing test IDs — never the counts.**

```python
src = inspect.getsource(target_fn)
mutated = src.replace(old, new, 1)          # then VERIFY where it landed - see below
ns = live_module.__dict__                   # the LIVE dict, never a copy
exec(compile(mutated, "<mutant>", "exec"), ns)
with patch.object(live_module, "target", ns["target"]):
    run_the_suite()
```

A production file is never written. That property is what makes it safe to run several agents concurrently, and it removes the "agent forgot to restore a mutation" failure mode entirely. Mutating on disk instead means concurrent runs observe each other's mutations — measured, in both the false-positive and false-negative directions, before this fix was found.

Order of preference: **in-process patch** by default; **worktree isolation** only where the mutation cannot be expressed in process (deleting a guard inside a body a patch cannot reach); **in-tree mutate-and-restore** only serially, with nothing else running.

## The distinction that matters more than any other

**Cannot fail** (vacuous) versus **cannot distinguish** (load-bearing, but blind to the thing it is named for). They are different defects, they need different fixes, and conflating them corrupts every count.

A vacuous assertion is inert. A non-distinguishing one actively certifies the wrong thing and *reads as thorough in review* — which is why human review does not catch it. Almost every finding on this campaign was the second kind. One module's final mix was 0 cannot-fail and 8 cannot-distinguish; another was mostly vacuous. The two do not correlate.

Examples of cannot-distinguish, all measured: thirteen tests named for one pattern type that fail under any stub of that branch but cannot tell that type from two others; a test asserting a final `deny` verdict where empty extraction also fails closed to `deny`, so the assertion cannot separate a rule match from total input loss; a test asserting a default parameter's *value* while the call site that consumes it can drop the argument entirely.

Two remedies that generalise: **assert the binding, not the value** (parse the source with `ast` and assert the name is imported from where it should be — interning defeats `assertIs` on identifier-shaped strings and small ints), and **assert the discriminating detail alongside the outcome** (assert the exact extraction next to the verdict, so the safety net becomes distinguishable from the mechanism).

## Reading the measurement

**Diff the failing-test SETS across mutants, not the counts.** "The same failing set for every mutant" is a *worse* signal than zero failures, because a non-zero count reads as coverage. Measured: inverting precedence, flattening every level, dropping the broadest layer and dropping the most specific one — four mutually contradictory mutations — all failed the identical single test. That is one over-loaded canary, not detection. The worst instance had 34 zero-detection mutants sharing one signature.

**Record `(test_id, failure_reason)`, not IDs alone.** Two mutants showing "newly failing = 0" were in fact detected: the test was already red, and only the reason fingerprint distinguished them.

**Read the tracebacks. A mutation that produces failures is not necessarily detected.** The campaign's highest-severity finding is one a naive failure count marks as covered — the failures came from an incidental stderr collision while the named mechanism stayed blind.

**Never generalise from a small sample.** One earlier note read "detection rate good (3 of 5 mutations caught)" for a module later measured at 58% survival over 81 mutants. The dangerous artifact there is the reassuring summary line, not a missed finding.

**Explain an unexpected baseline delta; never subtract it.** A "4-failure environmental floor" was subtracted across three rounds and turned out to be a real fixture defect (tests passing only because that machine's repo happened to have a `logs/` directory). "Floor" is a category that stops inquiry. A persistent baseline failure you cannot explain is a finding.

## Choosing mutants

**A badly chosen mutant is indistinguishable from zero detection.** A stub returning `sorted(roles)[0]` coincidentally agreed with the real precedence on every tested input and reported zero detection for a covered mechanism; `list(roles)[0]` failed an existing test immediately. **Confirm the mutant actually changes the output on your fixtures** — not merely that it compiled and is bound. A mutant that agrees with the original on every input you feed it is a slower way of running the original.

**Symmetry in a fixture hides a swap**, the same way defaults hide hardcoding. A probe for a swapped pair used a symmetric fixture, reported "no output change", and would have been logged as an equivalent mutant while two tests do detect it.

**Mutate toward the fix, not only away from correctness.** Applying the *fix* for a known defect and getting zero failures proves the suite sees neither the bug nor its correction — a strictly stronger statement than "untested". Measured: removing all escaping from a serializer gave 16 failures; adding the one missing escape gave 0.

**Mutate one guard at a time and you over-report coverage wherever a mechanism is implemented twice.** Two guards each carrying the same exemption mask each other: either alone is undetectable. Same for redundant emission routes — where a value reaches the output by 2^k paths, single-point mutants change nothing.

**When a value has more than one declared source of truth** (a production table, an expected-value table in the tests, a doc block), a naive sweep mutates only the production copy, every mirror-comparison test dies, and the module reads as fully covered. Rebind **every** holder, the test module's own imports included, then measure behaviour — and drop the expected-*name* equality so only the behavioural assertion remains. Measured: zero survivors at the naive tier, six weakenings surviving at the behavioural tier, each of which left live credentials readable.

**Record proven-equivalent mutants explicitly**, with the argument, so nobody re-derives them and nobody files them as coverage gaps.

## Harness correctness — the checklist

Every item here produced a false reading that cost real time.

- **`exec` against the live module dict, never a snapshot copy.** A mutant compiled against a frozen copy resolves its globals to the originals, so a second implementation elsewhere is still reached and the probe reports "survived". This defeats masking-pair probes specifically — the case where a false negative misleads most.
- **Patch every module holding a reference, not just the defining one.** By-value imports (`from mod import name`) make a single-module patch a silent no-op. This trap caught three separate people *who had already read the warning about it*; it is a checklist problem, not a knowledge problem. The mitigation that works is asserting the patch took effect.
- **Find holders by an identity scan over `sys.modules`, not by grep.** Grep finds imports; identity finds aliases (one scan found ten holders of a constant, including two names in one module for the same object). **Exclude `__main__`** — one scan rebound the harness's own `original` variable, making the restore anchor the mutant.
- **An identity scan sees only what is already imported, so every count is a lower bound.** Two scans of the same constants hours apart disagreed 10 vs 14, 6 vs 8, 3 vs 6, purely because different consumers were loaded.
- **Pre-import every consumer before the first replay.** A lazily imported module binds the *first* mutant permanently, and every later mutant then reports the first one's signature — internally consistent and entirely false. **Identical results across different mutants is the tell.**
- **Print the diff of every mutant.** `replace(old, new, 1)` edits the first match, which may be a docstring above the code, or a different branch of the same function. Both measured; the docstring case is the commonest and produces a perfect no-op mutant. A few lines of harness; it caught four bad readings across three modules.
- **Assert per mutant that the live object differs from the original in the way you intended** — compare the compiled source, not just bytecode (a `co_code` fingerprint misses string-literal mutants, and `functools.wraps` re-wrapping defeats naive comparison). Re-check after every restore step: one restore silently undid 20 method-level mutants, all reported as surviving.
- **Override `addSubTest` in any custom result class**, or diff test IDs from the runner's own output. `unittest` routes `subTest` failures through `addSubTest`, not `addFailure`, so a harness counting `addFailure` under-reports every subtest-based detection.
- **Establish a null-mutation baseline across repeated runs before trusting anything.** A multi-mutant harness runs the suite many times in one process, so module-level state and per-instance "once" flags make some tests fail on run 2 under *every* mutant including the null one — a permanent "detection" that is pure artifact.
- **Reset persistent state between mutants; the artifact often *is* the mechanism's state.** Where the code under test writes a log, a cache or a store, the first mutant that lets a write through makes every later mutant look correct. One sweep had to be entirely re-run after restoring the state directory to pristine before each round turned a "zero detection" into three detectors.
- **Derive any watchdog from `BaseException`.** `TimeoutError` has been an `OSError` subclass since 3.3, so code with a broad `except OSError` swallows the alarm and reinterprets it as its own domain error — a deadlocking mutant reported as a clean survivor with zero failures.
- **Write-detection snapshots need `(name, size, sha256)`.** `mtime_ns` is too coarse on some filesystems (WSL2 tmpfs) to see a same-length in-place rewrite. **Prove the snapshot fires against a planted file, a same-length rewrite, and a deletion** before trusting a clean result; assuming the self-check works is the error the check exists to catch.
- **A snapshot cannot attribute a write.** Pair it with a recorder wrapping the write routes (`open`, `os.open`, `remove`/`unlink`, `mkdir`/`makedirs`, `rename`/`replace`) and self-test the recorder against a fixture. On an agent-driven machine the thing a naive guard keeps catching is the agent's own transcript file. Scope digests deliberately and record why in the code — digesting a large home directory cost 3.9 s per snapshot against 0.4 s for a scoped one.

Several of these under-report detection rather than hiding defects — the subtest trap, the swallowed watchdog, the coincidental mutant. That direction inflates apparent gaps, so it wastes work rather than missing bugs. Say so when reporting scope; it is the difference between "re-check before quoting" and "a filed defect may be wrong".

## Fixture traps

**A fixture built entirely from field defaults is what lets hardcoding mutants through.** If every field holds its type default, or the same value as its neighbours, a mutant that *hardcodes* that field is invisible because the correct and hardcoded values coincide. Rebuild so no field carries its default and no two fields share a value, and pass non-`None` values for optional parameters. Measured: one fixture repair killed seven mutants at once. **A tidy-looking fixture is a warning sign** — a review pass had recorded approvingly that "its fixtures build exactly what its Givens describe", which was true and was precisely the defect.

**Equal value objects collapse fixtures, in both directions.** Frozen dataclasses that compare equal merge as dict keys: a hand-built multi-level structure silently flattens into one level, or two layers merge and their contents get attributed to both, doubling a count and making an ordering assertion vacuous. Give every element a distinct identity unless the test is specifically about merging.

**The five inert-mock shapes** — a `patch(...)` that is never consulted looks identical to isolation that works:

1. **Wrong target** — the consumer imported by value.
2. **Target never reached** — the target is right, the code never calls it. Ambient environment alone can cause this.
3. **Guard or decorator wrapper** — the imported name is a wrapper, so mutating the raw function is inert twice over.
4. **`wraps=` defeated by an explicit `return_value=`** — the wrapped real function never runs, and the test *reads* as end-to-end.
5. **A constant captured into a default argument at import** — `def f(p=CONST)` with every call site passing nothing makes `patch.object(mod, "CONST", ...)` provably inert. Distinct from the import-time-constant shape, and it needs a different fix.

**Do not look for these by grep.** A repo-wide grep sweep found nothing actionable, because inertness is a *scope* question. All five were found by falsifying each patch in the module being repaired. `autospec=True` catches a sixth class (stale call signatures) for the cost of a keyword and was used zero times in a 485-patch suite.

**A test that derives its expected value from the code under test cannot detect a change in that value.** It looks thorough — it iterates every entry — and it is structurally incapable of failing for the reason that matters. Two installer tests built their expectations by iterating the very table under test; both would have seeded a tool-wide grant and asserted that the grant was seeded.

## Environment isolation

**`patch.dict(os.environ, ...)` without `clear=True` inherits the developer's shell.** Measured: 8 of 13 hostile-environment configurations failed at HEAD from ambient variables alone, and one ambient variable made the code take an override branch, so five mocks stopped being called at all.

**A fixture tree in a bare temp dir is not isolated if the code walks upward.** Build it inside a throwaway `HOME` so the walk terminates inside the fixture; a stray marker file in `/tmp` left by any other process changes the result. **The warning applies harder to git fixtures** — a repo created inside another repo does not behave as expected.

**Use a fresh `mktemp -d` for any scratch directory, and check mtimes before attributing anything.** Concurrent agents share a session scratchpad; one "hostile HOME" fixture was polluted by a sibling agent's leftovers.

**Your own tooling writes into the tree.** Two apparent leaks were the dev machine itself: a repo log directory growing during a run was the live permission hook logging the agent's own commands, and stray report files were an analyzer running externally on a timer. One agent established this with a 22-second idle control plus per-test attribution across 189 tests before declining to file a leak. Do that before filing.

## Running it as a campaign

**One agent per test module, and tell each agent that the coordinator's notes are unverified and that reporting errors in them is part of the job.** Across two campaigns agents caught coordinator brief errors at a steady rate — roughly thirty corrections on this one, including the same figure wrong three times and several "none found" verdicts that had been reached by reading rather than measuring. **This is where a large share of the value came from.** An agent verifying against the code beats a coordinator working from memory, including when the coordinator wrote the notes.

**Findings must be recorded as failing tests, not as prose.** A red test asserting the *correct* behaviour is the right instrument: the later fix turns it green. A characterization test pinning the buggy value has to be inverted later — extra work, and a step someone can forget, leaving the defect enshrined. A growing red count is progress.

**Hard rules for every agent, in the measurement phase:**

1. **Never edit production code.** A newly-genuine test that fails is a *finding*, reported, not fixed.
2. **Never weaken an assertion to make it pass.** Restoring vacuity with a plausible assertion on top is strictly worse than leaving it alone, because the next reader trusts the specific assertion.
3. **Where a spec (Gherkin, docstring, test name) and the body disagree, the spec is the claim and the body is the evidence.** Never rewrite a false claim to match a weak body.
4. **A test that cannot fail is not fixed by adding an assertion** — check the fixture can produce the negative case at all.
5. **Prove every repair by mutation, and read the traceback.**
6. **Never silently assert a known-wrong value as expected behaviour.** Report it; the codebase owner decides whether a known defect gets pinned.

**Phase the campaign and do not blur the phases**: (1) fix the tests, accepting that some end up red; (2) fix the production code the now-correct tests fail; (3) work the filed tickets; (4) add coverage where there is *none*. Phase 4 being "absent tests only" is a deliberate limit — thinly-covered mechanisms are too much work for debatable value.

**Verification gate between waves, run serially with nothing else live**: full suite (count rises or holds), formatter and linter clean, `git diff --name-only` shows test paths only, and the coordinator independently spot-mutates two of each agent's claimed repairs.

**Cost.** Measured at ~161k tokens per repair agent (range 142k–197k, n=12). **Expect a mutation campaign to cost several times a read-and-edit campaign at equal agent count** — these agents run the suite dozens of times per module. On this setup the rolling session limit bound long before the weekly one; check budget between waves and never dispatch blind.

**Before parallelising anything, ask what shared state the *verification* touches, not just what the edits touch.** "The units are independent" was true of the artifacts and false of the method — which is the whole reason the in-process technique exists.