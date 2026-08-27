---
title: 'The suite''s measured blindness: ~65 assertions that cannot fail and ~50 mechanisms
  with zero detection'
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/31-suite-blindness-measured
---

**PARTIALLY FIXED in `05f786d`.** Wave 1 was committed (5 modules); still open: Tier 3 (~70 modules) has not started, and the ticket's own correction says its original ~65-assertion figure was inflated.

# The suite's measured blindness

**This is the largest quantitative output of TOO-45 #07, and it is a decision, not a work order.** Nobody should walk away from this ticket having fixed 65 tests. The point is to choose which subset matters and what rule stops the rest from accumulating again.

Two measurements, made by different methods on the same suite:

| measurement | method | result |
|---|---|---|
| tests whose assertions **cannot fail** | read the test, then run the fixture or mutate the mechanism it names | **~65 across ~78 files** |
| mechanisms with **zero test detection** | delete the mechanism in an out-of-tree copy, run all 2,733 tests, subtract the 2-error environmental floor | **~50** |

They are complementary halves of one fact. A mechanism is often undetected *because* the test that names it cannot fail -- that is exactly the pattern behind proposed tickets 17, 19 and 22, each of which carries its own "why the tests did not catch it" section.

**The suite is green and stays green. Neither number is visible from a passing run**, which is the entire problem: 2,733 passing tests is the same signal whether these exist or not.

## Part 1 -- assertions that cannot fail

Nineteen distinct shapes, catalogued as they were found. **This catalogue is the durable artifact of the sweep** and is worth keeping independently of whether any test is fixed:

1. Absence asserted against a fixture that cannot produce the presence.
2. A mock on a path the code never takes.
3. `assertIs` defeated by interning (`"toolguard"` is identifier-shaped; `10` is small-int cached).
4. The asserted value is what **every** alternative also produces.
5. The subject is stripped upstream before reaching the code under test.
6. Equal frozen-dataclass fixtures collapse into one dict key.
7. The failure case makes the module fail to **import** -- errors on collection, never fails.
8. `assertEqual(x, x)`, or both sides computing the same thing.
9. `assertIsNotNone(x)` where the function raises rather than returning `None`.
10. `hasattr(node, "label")` where the label came from the rule that produced the node.
11. `assertIn(literal, node.text)` where `node.text` **is** the input literal.
12. The Then names a mechanism the assertions never check; the outcome is what a tie-break produces anyway.
13. `assertRaises(Exception)`, which a typo'd attribute also satisfies.
14. The fixture's own setup provides an alternative route to the outcome, so the named subject is irrelevant.
15. A "control" test that never takes the comparison its name promises.
16. A dead assertion that can only fail after the line above it already failed.
17. A decoy row expired-on-write, so "was it deleted?" and "is it expired?" are indistinguishable.
18. Two tests differing by one flag, same expected verdict, neither observing the flag.
19. Two mechanisms that mask each other -- each undetected when deleted *alone*, because the one test that exercises them trips **both**.

Three more, found late and worth folding in:

20. **An assertion satisfied by a fail-open safety net rather than by correct behaviour.** The largest single cluster: `test_compound.py` has **12 of 223** in this shape, because `extract_commands` returns `[original.strip()]` on any parse error, so `assertGreater(len(result), 0)` cannot distinguish correct extraction from the fallback.
21. **Every real assertion nested inside `if <collection>:`** with no else and no non-empty check -- and in one case the code path *always* produced an empty collection, so the block never ran.
22. **A guard or checker that passes with an empty input set** (proposed ticket 29 is an instance).

Shapes 14-22 are not "vacuous" in the naive sense -- they assert something real about the **wrong subject**, which is why they read as thorough in review and why a human reviewer does not catch them.

## Part 2 -- mechanisms with zero detection

Measured across many rounds; the largest single run was **42 mutations with 23 survivors, a 55% survival rate.** A representative sample of what survives:

- `api._decide_bash`'s tool override -- it can null `reason`, `matched_rule` and `provenance` on **every MCP-terminal decision** with nothing failing
- `entries_for_tool`'s `endswith(")")` check
- `config_divergence.check_and_warn_divergence`'s once-per-day pre-check
- `danger()`'s entire `findings.sort()` (part of proposed ticket 28)
- `_is_blanket_allow`'s GLOB branch
- the NATIVE pattern type rebound to GLOB -- confirmed independently from two different test files (proposed ticket 17)
- `iter_dirs_upward`'s home stop; `.env`'s whole-line `#` skip
- `run_git`'s `timeout` **and** `GIT_TERMINAL_PROMPT=0` -- the exact pair `install_update.py` credited with *"no git subprocess here can hang"*

## Two method notes that change how the numbers should be read

**A mutation that produces failures is not necessarily detected.** Three separate batches found mutations that broke tests for an *incidental* reason while the named mechanism stayed uncovered -- including proposed ticket 23, the sweep's highest-severity finding, which a naive failure count marks as covered. **Any re-measurement must read the tracebacks.** The ~50 figure is therefore a floor, not a ceiling.

**Mutate toward the fix, not only away from correctness.** Applying the *fix* for a filed defect and getting zero failures proves the suite sees neither the bug nor its correction. Done for `_escape_toml_string` (proposed ticket 24): removing all escaping gives 16 failures, adding the missing `\n` escape gives **0**. That is a strictly stronger statement than "untested."

## What this ticket is actually asking for

Not 65 test fixes. A decision on three things:

1. **Triage.** The subset that matters is small and identifiable: assertions in the **permission path** (matcher, extractor, resolution) and in anything whose failure is silent. `test_compound.py`'s 12 and the parser's 13-of-18 are the concentration; both are upstream of proposed ticket 19's bypasses. Most of the rest are cosmetic and can stay.
2. **A rule that stops the accumulation.** The shapes are mechanical enough to check. Candidates: a review checklist item; a periodic mutation round on the permission path only; or the claim-falsification skill in **TOO-52**, which is the same technique pointed at a different artifact.
3. **Whether these get fixed alongside their defects or separately.** Tickets 17, 19, 22, 24, 28 and 29 each already name their own coverage gap. Fixing a defect without its test obligation lands the fix next to unfalsifiable siblings and it will not survive the next refactor -- ticket 19 says so explicitly.

## Scope note, stated plainly

This ticket does **not** claim the suite is bad. 2,733 tests catch a great deal, and several files came back with **zero** findings after mutation -- `test_resolve.py` and `test_once_per_store.py` both had every probe detected. The finding is narrower and more useful: **where the suite is blind, it is blind silently, and the blindness clusters in exactly the layers where toolguard's defects were found.**

## UPDATE 2026-08-12 — Arnon decided: fix them, permission path first

He directed the repair campaign rather than leaving this as an open decision. Triage per this ticket's own part 1: permission path first, tier 3 (~70 modules) not started. Plan and hard rules: `TOO-45 test-repair plan.md`. **Two of the three wave-1 modules are done and both produced findings this ticket did not predict.**

### Corrections to this ticket's own numbers, measured during repair

- **`test_compound.py`'s fail-open cluster is 16, not 12.** Five more in `assertIn(original, result)` form, where the original is present *only because the whole line failed open*. All five verified by execution.
- **`test_very_deep_nesting` does not belong in that cluster** — it parses successfully (11 elements) rather than failing open. It is shape 12, not 20. The working queue's list of 12 was internally inconsistent with its own evidence.
- **Shape numbering has drifted** between `reports/follow-up-queue.md` and this promoted catalogue. The queue cites "shape 3" for the fail-open shape; here shape 3 is `assertIs` defeated by interning, and fail-open is **20**. Anything citing a shape number by memory is suspect; cite this file.
- **One queue entry is simply false.** It lists `test_returns_none_when_no_deny_patterns` as an assertion that cannot fail with "confirmed zero detection". Inverting the guard so an empty pool denies **does** fail it. The queue conflated *redundant implementation* with *vacuous assertion* — two different findings needing two different fixes.

### The single worst measurement of wave 1

**`test_bash_parser.py`'s 18 tests survived the destruction of the grammar's delimiter class.** Removing space, `|`, `&` or `;` — i.e. destroying command/argument splitting or operator recognition outright — left **all 18 green**. The repaired module fails 9, 3, 3 and 5 tests respectively under those same four mutations.

The count here was also understated: **14 of 18 cannot fail, not 13.** `test_nested_subshell` is listed among the survivors in both the queue and ticket 19, but its `hasattr` can only be false when `parse` raises — an error, never a failure. Measured against `git HEAD`: ten mutations produced failures in only **four** tests.

### THE ~65 FIGURE IS INFLATED, and the cause is a systematic conflation

**Found independently by two agents, in two unrelated modules.** This is the most important correction to this ticket, and it is a correction to *my* counting method, not to the underlying findings.

Two different defects were counted as one:

- **An assertion that cannot fail** — no implementation change makes it fail. Genuinely vacuous.
- **An assertion that cannot DISTINGUISH** — it fails under some mutations but not the one that matters. Real, load-bearing, and still blind to the specific thing its name promises.

Instances confirmed:

- `test_returns_none_when_no_deny_patterns` was listed as "confirmed zero detection". Inverting the guard **does** fail it. It is a redundant *implementation*, not a vacuous *assertion*.
- All 13 `TestNativePattern` tests were counted as cannot-fail. Measured: **11 of 13 fail** when the NATIVE branch is stubbed always-True, and all 13 fail when stubbed always-False. Only 2 are strictly one-directional. The accurate finding — which the queue's own body text states correctly — is that they cannot **distinguish** NATIVE from GLOB or DEFAULT.

**So "~65 assertions that cannot fail" overstates the vacuous category and understates the more interesting one.** The distinguish-failures are arguably the worse defect: a vacuous assertion is inert, while a non-distinguishing one actively certifies the wrong thing and reads as thorough in review.

**Do not re-report the ~65 figure without re-deriving it against this distinction.** Both categories are real; they need different fixes and should never have shared a number.

### Method warning: monkeypatch measurements can report FALSE zero-detection

Discovered while repairing `test_hierarchical.py`. `permission_resolution` imports `decide_command_at_level_detailed` **by value**, so patching `toolguard.permissions` alone silently no-ops — the mutant is never reached and the probe reports zero detection for a mechanism that is in fact covered.

**Any in-process mutation must patch every module holding a reference to the object, not just its defining module.** The first `allow_first_within_level` run reported a false zero before this was caught.

This does **not** affect this ticket's original ~50 figure, which was measured by deleting mechanisms in an out-of-tree file copy — a technique immune to by-value import binding. It does affect anything measured by monkeypatch since.

### Second-worst measurement of the campaign

**`test_patterns.py`: 14 of 30 mutations survived before repair, 0 after.** The matcher's own test file had **zero coverage of the REGEX branch** — not mentioned anywhere in the queue or in ticket 17. Also surviving: NATIVE's start anchor and end anchor deleted outright, DEFAULT rebound to GLOB or NATIVE, REGEX rebound to NATIVE or DEFAULT, `re.search` → `re.match`, the `re.error` guard, and `parse_pattern`'s `extended_syntax=False` opt-out.

**Ticket 17's fix could previously have landed with zero test failures.** It now fails a test, which is the "mutate toward the fix" property this ticket asks for.

### Shape 25 — the fail-CLOSED mirror of shape 20, and it may be the most widespread of all

Found in `test_multiline_bash.py`, where it silently covered **12 tests**. Shape 20 was "an assertion satisfied by a fail-open safety net". This is the same defect wearing the opposite sign, and it is **undocumented in the code**:

- **empty extraction fails CLOSED to `deny`** — `"No valid commands found in command line"` (`compound.py`)
- **any `UndecidableSegment` floors to `ask`**

Therefore:

- `assertEqual(decision, "deny")` **cannot distinguish** a deny-rule match from total extraction loss.
- `assertEqual(decision, "ask")` **cannot distinguish** the named mechanism from a parse failure.

**Why this one deserves attention beyond its module:** shape 20 needed a specific function (`extract_commands`) and a specific assertion form (`assertGreater(len, 0)`). Shape 25 needs neither. **Any test anywhere that asserts a final verdict of `deny` or `ask` is a candidate**, because the safety nets sit at the end of the decision path and every test's assertion passes through them. The fix is the same as shape 20's: assert the exact extraction alongside the verdict, so the safety net becomes distinguishable.

This shape is a strong argument for the TOO-52 skill: it is mechanically checkable (find verdict assertions with no accompanying extraction assertion) and it is invisible to review, because asserting `deny` on a dangerous command reads as exactly right.

**A ONE-LINE REMEDY EXISTS for the Bash case, found 2026-08-13.** `RuntimeVerdict.matched_rule` carries the wrapper-free rule on a genuine match (e.g. `[regex]^rm\b.*\.toolguard`) but is **`None`** on the fail-closed empty-extraction deny. So the two are distinguishable at the cost of one assertion:

```python
self.assertIn(verdict.matched_rule, expected_rule_bodies)
```

Measured on `test_self_integrity.py`: under `decompose -> []`, HEAD produced 3 failures — **none of them in the hard-deny tests the file exists for**. A failure count of 3 reads as "the module noticed"; the tracebacks showed the opposite. After adding the `matched_rule` assertion, all 8 deny assertions detect it.

**Any module asserting a `deny` verdict against a Bash rule can adopt this immediately.** It is the cheapest high-yield fix the campaign has produced.

### Two REPO-WIDE zero-detection mechanisms, measured against the full suite (2026-08-13)

Measured properly — the whole 2,820-test suite run under each mutation, with the concurrent-edit baseline subtracted:

- **`entries_for_tool`'s `endswith(")")` check** — zero detection anywhere in the repo at HEAD. **This ticket predicted it; it is now measured.** Now detected by exactly one test.
- **`_first_toplevel_str_setting`'s `isinstance(value, str)` guard** — zero detection anywhere. **Not previously in this ticket.** Removing it makes `resolved_no_match_fallback()` raise `TypeError` on an unhashable configured value. Now detected by one test.

Both are single-test-detected now, which is thin but is the difference between one and zero.

**Method note for anyone re-measuring this week:** the full-suite baseline currently carries **19 intentional failures** from modules under concurrent repair. Any repo-wide mutation count must subtract it, or every mutation looks detected.

### THE USER LEVEL COULD STOP BEING READ, REPO-WIDE, WITH A GREEN SUITE

Measured 2026-08-13 and the widest single blind spot the campaign has found.

Mutating `discover_config_files` so the `~/.claude` candidates block becomes a **no-op**:

- `test_config.py` at HEAD: **18/18 green — zero detection**
- extended across every module that reaches it (`test_migration`, `test_toml_config`, 136 tests), **patching both holders** — `config` *and* `permission_migration`, which imports it by value: **failures identical to baseline. Zero detection repo-wide.**

**A user's entire `~/.claude` could stop being read and nothing would fail.** Now detected by 3 tests.

Also closed in the same pass, all previously at zero: TOML-vs-JSON precedence in both directions, the `source_type`/`format` tuple fields, project-outranks-user ordering, existence filtering, `iter_dirs_upward`'s home stop (which this ticket had listed as repo-wide zero-detection — **confirmed**), nearest-marker-wins, and the `config`/`env_config` `find_project_root` relationship.

### Shape 27 — asserting a DEFAULT VALUE is not asserting the default is USED

Found 2026-08-13, and it had actively misdirected the working queue.

`test_git_helper.py` asserts `run_git.__kwdefaults__["timeout"] is GIT_TIMEOUT_SECONDS` — that the default **exists and has the right value**. It never asserts the parameter reaches `subprocess.run`.

So deleting `timeout=timeout` from the actual call **survives that test**. Measured: it survived the whole suite. The same held for `GIT_TERMINAL_PROMPT=0` and `capture_output=True`.

**The queue had routed this mechanism to `test_git_helper.py` as its owner** — "cross-file: the owner is `test_git_helper.py`, not this batch" — and that file cannot detect it. A plausible-looking ownership claim sent the finding to a module that was structurally incapable of catching it.

**Generalises:** any assertion about a signature, a constant, a default, or an annotation describes the *declaration*, not the *behaviour*. `Optional[dict]` on `_read_direct_url_json` is the same shape — the annotation promises a dict and nothing enforces it (proposed ticket 55).

This closes ticket 31's own prediction: `run_git`'s `timeout` **and** `GIT_TERMINAL_PROMPT=0` were both at zero detection, together backing `install_update.py`'s universally quantified claim that *"no git subprocess here can hang."* **The claim was unguarded.** Now **3 + 4 detectors for the timeout** (`test_git_helper` and `test_update_check` respectively) and **3 for `GIT_TERMINAL_PROMPT`** — corrected from "2", which was my own miscount.

**The remedy for shape 27, which generalises:** assert the **binding**, not the value. `test_git_helper.py` now parses `_git.py` with `ast` and asserts the name is *imported from* `toolguard.constants`. This matters because the values are interned — `"toolguard"` is identifier-shaped and `10` is small-int cached, so a module that re-declares the literal locally still satisfies `assertIs`. Proven: a synthetic module re-declaring both passes every `assertIs` and fails the AST check.

**Four more mechanisms were at zero detection repo-wide**, all now held: `run_git` prepending `"git"` to argv; `run_git` honouring an **explicitly passed** timeout (every caller uses the default, so hardcoding it survived everywhere); the **narrowness** of `except OSError, subprocess.SubprocessError` (widening it to `BaseException` — swallowing every bug as "git unavailable" — survived everywhere); and `install_provenance._git_subtree_is_clean` being bounded by a timeout at all.

### METHOD REFINEMENT: a probe against a TEST module must patch the TEST module

The by-value trap has a second face that caught an agent **who had already read the warning about the first**.

Probing whether `test_patterns.py` detects `parse_pattern`'s `extended_syntax` opt-out, the agent patched only the defining module and read **zero detection**. False — `test_patterns.py` imports the function **by value**, so the real one ran. With the test module's holder patched too, it fails 1 test.

**The rule is not "patch production holders"; it is "patch every holder, including the test module's own imports."** Cross-module coverage probes are the case where this bites, because the test module is easy to forget — it is the thing being measured, not the thing being mutated.

### SUBTRACTING AN "ENVIRONMENTAL FLOOR" CAN HIDE THE DEFECT THAT IS THE FLOOR

Measured 2026-08-13, and it invalidates a habit this ticket's own method relies on.

The working queue recorded, at three separate places (lines 1612, 1663, 1718), a *"4-failure environmental floor"* / *"environment artifact"* for `test_hook_error_reporter.TestOrdinaryInvocationStderr`, and **subtracted it from three separate mutation rounds.**

**It was not an artifact. It was a real fixture defect.** Those tests passed only because the developer's repo happens to have a `logs/` directory: `main()` resolves a coarse log dir (`require_project_root()/logs`) *before* `env_config` exists, and warns to stderr when it is missing. In an rsync copy without `logs/`, both tests failed.

**So the finding was seen three times and dismissed three times, because "floor" is a category that stops inquiry.** The correct move on a persistent baseline failure is to explain it, not to subtract it — and "it fails in a copy of the repo but not the original" is a description of a machine-state dependence, which is exactly what this campaign is finding everywhere else.

Anything in this ticket derived by subtracting a floor should be re-checked against that possibility. The original 2-error floor (`test_architecture_fitness.TestSmokeAgainstRealTree`, which needs a real git repo) is a genuine environmental requirement — but it earned that status by being explained, not by being persistent.

### A fifth isolation anchor, missing from the rules

`.claude/rules/test-config-isolation.md` names four anchors. `isolate_log_dir_for_module` covers only the **config-derived** log dir, not the **coarse pre-`env_config`** one that `main()` resolves first. **Any module driving `main()` end-to-end silently depends on the real repository having a `logs/` directory.** That is the fifth anchor and it should be added to the rule.

### Method indictment of parts of the working queue

`reports/follow-up-queue.md:3664` concluded, for its own file, *"assertions that cannot fail: none found as a defect in the test file itself"* — reached by **reading method bodies**. Reading found nothing in that module. Mutation found **five** zero-detection mechanisms in it.

**Read-only verdicts of "none found" in that queue are not measurements and must not be quoted as such.** They record that someone looked, not that nothing was there. This is the same failure the campaign keeps re-learning: execute the claim, do not read it.

### Shape 26 — a `zip()` over input and output hides a length mismatch

Found in `test_rule_entry.py`. A round-trip test iterating `zip(raw_list, result)` **cannot see a dropped element**: `zip` stops at the shorter sequence, every surviving pair still matches, and the assertion passes. A mutation making `normalize_entries_preserving` silently drop unnormalizable elements produced zero failures.

One-line fix: `assertEqual(len(result), len(raw_list))` before the loop.

Mechanically checkable, and worth adding to the TOO-52 skill's list: **any `zip` of an input collection against an output collection wants a length assertion first.** The working queue noticed this instance in passing and recorded it as an aside rather than a defect or a shape.

### New shapes, promoted from wave 1

23. **A test helper that re-implements the logic under test.** Converts an entire class into a tautology — the tests exercise the fixture's copy, not production. Ten tests, zero detection, in the file named for the mechanism. See proposed ticket 35; this is the campaign's most severe finding so far and shape 19's cousin at class scale.
24. **Redundant emission routes mask single-point mutations.** `_collect_cmd_substs` flattens every nesting level into the top-level command, so level *k* is reachable by ~2^k routes; four separate single-point mutations changed nothing. **Any future mutation round that counts single-point survivors over-reports coverage here** — a method warning, not just a test defect.

### Method correction that outranks both

**Parallel mutation testing is not safely parallel.** Agents proving repairs mutate *shared production files*, so concurrent agents observe each other. Full-suite numbers from parallel agents are provisional. Detail and the worktree-isolation fix in the plan file. This ticket's own ~50 figure was measured serially and is unaffected.

## Provenance

TOO-45 #07, 2026-08-11 to 08-12, across ~78 test files. Detail in `reports/follow-up-queue.md` (~60 lettered sections) and in the #07 work queue's shape catalogue. Promoted to a ticket 2026-08-12 after Arnon asked whether one existed -- it did not, which is the second time in this ticket that the largest findings had been left in a working queue rather than on his decision surface.
