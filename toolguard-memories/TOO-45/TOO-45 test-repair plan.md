---
title: TOO-45 test-repair plan
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/too-45-test-repair-plan
---

# Test-repair campaign

**Authorised by Arnon 2026-08-12**, as the long parallel task to run while he works through the open decisions on proposed fixes and the retro text. His framing: test modules are orthogonal so they parallelise like the docstring sweep, and the Gherkin-vs-implementation reconciliation is a **self-guard** that bounds each agent without cross-module context.

**Standing instruction from him: update the relevant proposed tickets as the work proceeds**, because he has not read 31-33 yet and will reach them late. A finding that lands only here repeats the exact failure this ticket already recorded twice.

## The decision I took, and why it deviates from "fix the broken tests"

Ticket 31 is explicit: *"Nobody should walk away from this ticket having fixed 65 tests."* The follow-up queue names **80 distinct test modules** — effectively the whole suite. Fixing all of it is neither useful nor affordable.

So: **triage per ticket 31's own recommendation**, permission path first. Arnon can widen it.

| tier | modules | why |
|---|---|---|
| **1 — permission path** | `test_compound.py`, `test_bash_parser.py`, `test_multiline_bash.py`, `test_permissions.py`, `test_patterns.py`, `test_hard_deny.py`, `test_ask_resolution.py`, `test_hierarchical.py` | ticket 31's named concentration; upstream of ticket 19's bypasses; failures here are silent and change real decisions |
| **2 — defects with a named coverage gap** | whatever tickets 17, 19, 22, 24, 28, 29 name | each already carries its own "why the tests did not catch it"; ticket 31 warns a fix landed next to unfalsifiable siblings will not survive the next refactor |
| **3 — the rest** | ~70 modules | mostly cosmetic per ticket 31. **Do not start.** Needs Arnon's decision, not agent time |

## THE THREE PHASES — Arnon, 2026-08-13

His sequencing, verbatim in substance:

1. **This campaign is strictly about fixing TESTS.** Some will end up failing once correct — that is the intended output, not a problem.
2. **Then make things green again by fixing the tested CODE** that the now-correct tests fail.
3. **Then handle, case by case, the proposed tickets he flags as in-scope.**
4. **Then add coverage where there is NO coverage at all** (added 2026-08-13). His scoping, and it is a deliberate limit: *"we won't bother here with adding coverage where some coverage already exists, because that would be too much work with debatable value."* So phase 4 is **absent tests only**, not thin ones.

### Phase 4 backlog — mechanisms with NO test at all, accumulating as found

| what | evidence | source |
|---|---|---|
| **Ticket 19 P1 — a `while`/`until` condition is never extracted** | the widest bypass in that ticket; **zero tests in `test_compound.py`**. It is not a bad pin, it is absent — so it will not announce itself in phase 2 either way | audit, 2026-08-13 |
| Ticket 19's three filed `multiline.py` bypasses | `heredoc_quote_parity_skip_off` still fails zero tests after repair. Needs new fixtures: `&&` before `<<`, two heredocs on one line, escaped `'` before `<<` | multiline agent |
| `_generate_positive_probes` / `_generate_extension_probes` | both can be emptied with zero failures, before and after repair; only `_generate_negative_probes` is detected | consolidate agent |
| REGEX branch of the matcher | had **zero** coverage in `test_patterns.py` before repair — now covered, listed here as the shape to look for elsewhere | patterns agent |
| Nine surviving mutations in `test_tools_consolidate.py` | `f1_accept_exact_bodies`, `f1_drop_dup_token_check`, `f1_drop_emitted_sets`, `f2_drop_equal_cmd_skip`, `f2_drop_args_filter`, `f2_drop_dedup_removals`, `regex_drop_suffix`, `broad_min_tokens_1`, `broad_min_finals_1` | consolidate agent |

**Add to this table whenever an agent reports a mechanism with no test, rather than leaving it in a report.**

### Still uncovered after the overnight bursts — the short list

Most agents closed their own gaps. These are the ones that survived, because they sit outside the repaired module's scope:

| mechanism | evidence |
|---|---|
| **`require_project_root` has no direct test anywhere** | there is **no `test_path_utils.py`**; `test_log_writer.py` patches it, which tests the caller. Its `RuntimeError` branch — whose message queue item 23 already flags as wrong — is unexercised |
| `build_validation_report` / `print_validation_report` in `touch_set_inventory` | reached only incidentally through `main()` |
| The three `undecidable_fallback=*` prose markers | unreachable from `_unit_from_tuple`; they belong to `hook.py`'s audit renderer, not the seam module |
| MCP-terminal tools in the golden corpus | **0 cases in both corpora**; adding them is a `corpus_build.py` change, not a test change |
| File-path **cascade** denies in the corpus | **0 cases** — all 4 file-tool denies are hard-denies |

**Phase 4 is "absent tests only", so a mechanism that is thinly covered does not belong here.** Each row above was measured as having *no* detector, not a weak one.

### Accumulated 2026-08-13 — still uncovered after their module's repair

Each was measured (mutation survived after repair), not inferred. Grouped by whether it is worth doing.

**Worth covering — a real mechanism nothing watches:**

| mechanism | evidence |
|---|---|
| **`_atomic_write_text` in `installer.py`** — called **174 times per module run**; replacing it with a plain `path.write_text` produces **0 failures** | ticket 40's atomicity blind spot in a *second, independent* writer |
| **`_binary_status`'s entire LOCAL install-kind branch** | `skills-status` is tested for GIT and UNKNOWN, never LOCAL — the kind this repo itself was installed as during part of TOO-19 |
| **`context.takeover.conflict`** in the security audit's `--with-context` | no fixture anywhere produces a takeover conflict |
| **`--max-age-days` reaching `harvest_corpus`** | **OWNER FOUND 2026-08-14**: it is not reachable from `replay`, which receives an already-harvested corpus. It lives at `toolguard/tools/corpus.py:52`, so it belongs to `test_tools_corpus.py` — dispatched with that as a named target |
| **`_split_csv`'s whitespace stripping** | no test passes `--governed-tools "Bash, Read"` |
| **Ticket 19's three filed `multiline.py` bypasses** | `heredoc_quote_parity_skip_off` still fails zero tests. Needs new fixtures: `&&` before `<<`, two heredocs on one line, escaped `'` before `<<` |
| **Ticket 19 P1 — a `while`/`until` condition is never extracted** | the widest bypass in that ticket; **zero tests**. Will not announce itself in phase 2 either way |

**Probably NOT worth covering — recorded so nobody re-derives them:**

| mechanism | why |
|---|---|
| `_generate_positive_probes` / `_generate_extension_probes` | both can be emptied with zero failures; only `_generate_negative_probes` is detected — but these are probe *generators*, and the gate they feed is now covered |
| `install_update.py:123-124` and `:220-221` | two defensive `except Exception:` blocks, not reachable through the public surface |
| `_walk_up_to_git_root` reaching `/` | a test for it would depend on whether `/.git` or `/tmp/.git` exists — machine-dependent by construction |
| `_render_ledger`'s `fmt` parameter | dead: markdown and text output are byte-identical (executed) |
| Nine surviving mutations in `test_tools_consolidate.py` | listed in that agent's report; low value individually |

**PROVEN EQUIVALENT — do NOT write tests for these.** Filing them as gaps would waste phase-4 effort on mutants that cannot be detected because they change nothing:

- `_read_direct_url_json`'s `if not raw: return None` — `except ValueError, TypeError` already absorbs `json.loads("")` and `json.loads(None)`; verified identical over eight inputs
- `_permission_patterns_in_text`'s `if start == -1: return []` — `find_section_boundaries` returns `(-1, -1)` when absent, so `text[-1:-1]` is `""` and the unguarded body yields `[]`
- `_withheld_to_dict(withheld) if withheld else []` — equivalent to the unconditional call
- `normalize_command`'s empty-string guard — `"".split()` → `[]` → `""` regardless
- `normalize_path`'s `range(3)` loop beyond iteration 1 — dead
- `danger()`'s `f.tool` sort component — `discover_tools` already returns sorted names and results are appended tool-by-tool, so it can never reorder anything

**This settles a question that was open.** Under this sequencing, **a red test asserting the CORRECT behaviour is the right instrument**: phase 2 turns it green by fixing the code. A characterization test pinning the buggy value would have to be *inverted* in phase 2 — extra work, and a step someone can forget, leaving the defect enshrined.

**Correction to my own earlier record**: I described ticket 17 as "two agents pinning it oppositely". Verified false by audit and grep — `test_patterns.py` carries one pin, `test_permissions.py` carries nothing. One agent acted, the other declined and said so in its report; **I read a non-action as a contradictory action** and propagated it into two files and two messages to Arnon. The lesson generalises past this instance: *an agent reporting that it chose not to do something is not evidence that something exists in the tree.* Check the tree.

He still reviews ticket 17 himself; this is evidence for that review, not a decision taken. But later waves should prefer **red-asserting-correct** over characterization where the two are genuinely equivalent, because it matches the plan.

It also means a growing red count is **progress**, not decay. The rule stands unchanged: never make a red test green by weakening it. Phase 2 makes it green by fixing the code.

## The rule that matters more than any fix

**Making a vacuous test real will surface genuine defects. That is the point, and it is also the danger.**

An agent told to "fix broken tests" will, under pressure, make a newly-failing test pass by weakening it — restoring the vacuity it was sent to remove, now with a plausible-looking assertion on top. That is strictly worse than leaving it alone, because the next reader sees a specific assertion and trusts it.

**Hard rules for every agent:**

1. **Never edit production code.** Not one line. If a test that now genuinely tests something fails, that is a **finding**, reported, not fixed.
2. **Never weaken an assertion to make it pass.** If the honest assertion fails, the test stays failing and the agent reports it. Arnon decides.
3. **Reconcile Gherkin against the body.** The Given/When/Then states intent and boundaries; the body either honours it or does not. Where they disagree, the Then is the claim and the body is the evidence. **Never rewrite a false Then to match a weak body** — that is the #07 rule, paid for there, and it applies verbatim here.
4. **A test that cannot fail is not fixed by adding an assertion.** Check the fixture can actually produce the negative case. Shapes 1, 4, 5 and 14 in ticket 31's catalogue are all "the fixture makes the outcome inevitable."
5. **Prove the fix.** For every repaired test: mutate the mechanism it names, confirm the test now fails, restore. A repaired test that still passes under mutation was not repaired. **Read the traceback** — ticket 31's method note: a mutation that produces failures is not necessarily detected.

## PROTOCOL DEFECT FOUND IN WAVE 1 — parallel mutation windows collide

**Reported by the `test_hard_deny.py` agent, unprompted, and it is correct.** During its mutation windows it twice saw *other* agents' live production mutations in `git diff` — `command_extractor.py` with the fail-open fallback rewritten, then `command_model.py`.

**The parallelisation premise was half wrong.** Arnon's framing — test modules are orthogonal, so they parallelise like the docstring sweep — holds for *editing test files*. It does **not** hold for **mutation testing**, because proving a repair requires temporarily modifying a **shared production file**. Two agents mutating at once can each observe the other's mutation, in their own module's run as well as in a full-suite run.

Consequences, in order of severity:

1. **Any full-suite number produced by a parallel agent is provisional.** The wave-1 agents' suite runs must not be trusted as coverage evidence.
2. A mutation proof can be **falsely positive** — a test "fails under mutation" because of someone else's mutation — or **falsely negative**, if a concurrent mutation happens to mask the effect.
3. Single-module runs bound but do not eliminate the exposure: two agents mutating the same shared file (e.g. both touching the parser) collide directly.

**The fix, found by the `test_bash_parser.py` agent without being asked: mutate IN PROCESS, never on disk.** It proved all 18 repairs plus 2 new tests by monkeypatching the generated parser inside the test run — delimiter character classes, node label wiring, `Parser.parse`'s raise — and **never wrote a production file at all**.

That is strictly better than the worktree isolation I was about to impose:

- **inherently collision-free** — nothing is shared, because nothing on disk changes
- **no setup cost**, where a worktree costs time and disk per agent
- **no restore step**, so the "agent forgot to restore a mutation" failure mode disappears entirely
- it cannot leave the repo dirty even if the agent crashes mid-proof

**Order of preference for wave 2 onward:**

1. **In-process monkeypatch.** Default. Works for anything reachable through an attribute, a module global, or a function object.
2. **Worktree isolation** (`isolation: "worktree"` on the Agent tool). Only where the mutation cannot be expressed in process — e.g. deleting a guard *inside* a function body, where the change is to code the monkeypatch cannot reach.
3. **In-tree mutate-and-restore.** Only when the coordinator is running it serially, with no agents live. Never in a parallel wave.

**Keep the wave-1 discovery visible, because it is the reusable part:** the collision was found by an agent reporting something it was not asked about, and the fix came from a *different* agent solving the problem incidentally. Neither was in the brief. Wave 2's brief now carries technique 1 explicitly, so it stops depending on luck.

**Wave 1's repairs are not thereby void** — both agents proved their repairs with single-module runs and read the tracebacks — but any wave-1 claim that rests on a *full-suite* count should be re-checked serially by the coordinator, with no agents running.

**Generalisable, worth carrying past this ticket:** *"the units are independent"* was true of the artifacts and false of the *method*. Before parallelising, ask what shared state the **verification** touches, not just what the edits touch.

## Per-agent brief shape

One agent per test module. Each gets: the module, the lettered sections of `reports/follow-up-queue.md` that name it, ticket 31's shape catalogue (27 shapes and growing — read its UPDATE sections, not just the original list), and the five hard rules above.

Each returns, as structured data, not prose:

- tests repaired, each with the mutation that now catches it
- tests left failing, each with the production defect it exposes
- tests found vacuous but **not** repairable without a production change
- Gherkin/body mismatches, and which side was wrong
- anything in the follow-up queue's account of this module that turned out to be **wrong** (the queue is my own working notes and carries my errors)

## OPEN DECISION FOR ARNON: how a KNOWN, UNFIXED defect should be pinned

Two wave-2 agents met the same live defect (ticket 17, NATIVE `*id_rsa` failing to match `cat id_rsa.pub id_rsa`) and resolved it **two different ways**. Both are defensible; the inconsistency is currently in the working tree.

- **`test_patterns.py`** pinned the shipped (wrong) value as a **characterization test**, with an inline comment naming it a false negative and a deny-rule bypass. Effect: ticket 17's own fix — which previously could have landed with **zero test failures** — now fails a test, so it cannot land silently.
- **`test_permissions.py`** refused to add the `assertFalse`, on the grounds that it enshrines a defect as expected behaviour, and asked for a decision instead.

**RESOLVED BY ARNON 2026-08-12: he will review ticket 17 manually, and the contradicting fixes are to be LEFT ALONE for now.**

So: **no standard is being imposed, and neither agent's choice is being reverted.** Both stay in the tree as they are, and the inconsistency is his to settle when he reads ticket 17.

Consequences for later waves:

- **Do not touch either pinning.** Not to harmonise them, not to relabel them, not to "improve" the characterization comment.
- **Do not adopt either as a precedent.** When a wave-3-or-later agent meets a known-unfixed defect, it **reports it** and pins nothing.
- The generalisable rule that survives regardless of his decision: **an agent must never silently assert a known-wrong value as expected behaviour.** Reporting is always safe; enshrining is not.

I withdrew a standard I had started to impose here. Worth noting why: the campaign's whole premise is that assertions state claims, and I was about to settle by fiat a question about *what a suite is allowed to claim about a known defect* — which is precisely the kind of decision that belongs to the person who owns the codebase, not to the process running through it.

## MEASURED BURN RATE — 12 agents, 2026-08-12

Every agent reported its own token count, so this is measured rather than estimated.

| quantity | measured |
|---|---|
| tokens per repair agent | **~161k** (range 142k–197k, n=12) |
| 12 agents | **1.93M** tokens |
| cost in the WEEKLY limit | **5 points** (94% → 99%) |
| cost in the SESSION limit | **~49 points** |

Derived: **1 weekly point ≈ 2.4 agents. One 5-hour session window holds ~24 agents.**

**The session limit binds, not the weekly one.** The whole weekly budget is ~240 agents-equivalent; even all of tier 3 (~70 modules) is ~29% of it. But at 2 concurrent agents averaging ~11 minutes, that is ~10 agents/hour, which exhausts a session window in **~2.5 hours**. That pause self-heals every 5 hours — an interruption, not a wall.

**Why this campaign costs more than #07's comment sweep, per Arnon's observation:** these agents run the test suite dozens of times to prove mutations in process. #07's agents mostly read and rewrote text. Same headcount, structurally different work. **Expect any mutation-based campaign to cost several times a read-and-edit campaign at equal agent count.**

## TRAPS THAT SILENTLY PRODUCE FALSE ZERO-DETECTION — put these in every later brief

Three now, all found by agents, all capable of making a covered mechanism look uncovered. **A false zero-detection reading is worse than no reading**, because it manufactures a finding that does not exist.

1. **By-value imports.** `permission_resolution` imports `decide_command_at_level_detailed` from `permissions`. Patching only the defining module silently no-ops. **Patch every module holding a reference**, and verify the mutation took effect before concluding anything.
2. **`Provenance` equality collapses fixtures — in TWO different directions.**
   - **Flattening**: `Provenance.specificity` defaults to 0, so a hand-built multi-level `Configuration` **collapses into a single level** unless specificity is set explicitly. One agent's two-level probe collapsed this way and reported a mutation as surviving when the fixture had quietly destroyed the hierarchy it was testing.
   - **Duplicating** (found 2026-08-13): two `ConfigLayer`s built with an **identical** `Provenance` **merge**, and the merged rules are attributed to **both** — so one dangerous rule was reported **twice**, inflating a CRITICAL count and making an ordering assertion vacuous.

   **Give every layer in a fixture a distinct `Provenance`, including its `path` and `specificity`, unless the test is specifically about merging.** The failure is silent in both directions and looks like a correct fixture.
3. **Masking guard pairs.** `apply_parse_failure_floor` and `_apply_ask_floor` both carry the already-deny exemption; `_apply_ask_floor`'s copy returns first, so the other is unreachable on the ordinary command path and can be deleted with tests green. **Mutating one guard at a time over-reports coverage** wherever a mechanism is implemented twice. Catalogue shape 19.
5. **THE MUTATION LANDED IN A DOCSTRING, NOT IN THE CODE.** Found 2026-08-13 and the subtlest one yet. A source-rewriting harness does `source.replace(old, new, 1)` — and if the token also appears in the function's **docstring above the code**, the first replacement edits *prose*. The mutant is then a no-op, the suite is green, and the reading is indistinguishable from genuine zero detection. It cost one agent a false survivor on `identity()`'s `sort_keys=True`.

   **Verify the replacement landed in code before trusting any result.** This is the "read the tracebacks" rule moved one step earlier: **read the mutant, not just the outcome.**

   **Refinement 2026-08-13 — the docstring is only the commonest case; the general fault is THE WRONG OCCURRENCE.** `replace(old, new, 1)` edits the *first* match, which may be a different branch of the same function. Measured twice in one module: a mutation intended for an `else` branch landed on the `project_root` branch, and one intended for a function's final return landed on its early return. Both were caught by **printing the mutant diff** and re-running as corrected variants. A sibling agent independently voided two of its own mutants the same way.

   **Print the diff of every mutant.** It is a few lines of harness and it has now caught four bad readings across three modules.

6. **REPEAT-RUN POLLUTION FROM MODULE-LEVEL STATE.** A multi-mutation harness runs the suite many times **in one process**. `OncePer._degraded_notice_sent` is per-instance and `AUTO_MIGRATION` is module-level, so `test_skips_migration_when_sqlite_unavailable` passes on run 1 and fails on run 2 — **under every mutation, including the null one.** A harness that does not reset such state sees a permanent "detection" that is pure artifact. Measured at HEAD: run 1 clean, run 2 fails. **Establish a null-mutation baseline across repeated runs before trusting any result.**

7. **`patch.dict(os.environ, ...)` WITHOUT `clear=True`.** The test then inherits the developer's environment. Measured in `test_env_config.py`: **8 of 13 hostile environment configurations failed at HEAD**, 10 distinct failures, purely from ambient `TOOLGUARD_*` variables. Worse, `TOOLGUARD_PROJECT_ROOT` made the code take an override branch, so **five `find_project_root` mocks stopped being called at all** — the "patch target the code never calls" shape, reachable from nothing more than the developer's shell.

8. **A bare `MagicMock` used where a path is expected reaches `open()` through `__index__` and opens FD 1 — closing stdout.** It corrupted one measurement run before being caught. Give any mock that might reach a filesystem call a concrete `return_value`.

9. **Compiling a mutant against a SNAPSHOT of the module dict instead of the live one.** The mutant then resolves its globals against frozen copies, so a second, unmutated implementation elsewhere is still reached and the probe reports "survived". This **silently defeats masking-pair probes specifically** — exactly the case where a false negative is most misleading. Cost one agent a false "survived" reading before it was caught. `exec(compile(src), live_module.__dict__)` — the live dict, never a copy.

10. **THE FIVE INERT-MOCK SHAPES.** A `patch(...)` that is never consulted looks identical to isolation that works. All five measured on this campaign:

    1. **Wrong target** — patching the defining module when the consumer imported by value (trap 1 above, seen from the test side).
    2. **Target never reached** — the target is right but the code never calls it. Trap 7 shows how ambient environment alone causes this.
    3. **Guard/decorator wrapper** — the imported name is a wrapper, so mutating the raw function is inert twice over.
    4. **`wraps=` defeated by an explicit `return_value=`** — the wrapped real function never runs, and the test *reads* as end-to-end. Now extinct in this repo.
    5. **A constant captured into a DEFAULT ARGUMENT at import** — `def f(p: Path = PYSCN_TOML)` with every call site passing nothing. `patch.object(mod, "PYSCN_TOML", ...)` is provably inert. **Distinct from the import-time-constant shape**: there the constant is *read* at import, here it is *captured into a signature*, and the two need different fixes.

    **Do not look for these by grep.** The sweep was written and run repo-wide on 2026-08-13 and found nothing actionable: shape 1 exists at 6 sites, none plainly inert; shape 4 at 0; and the 38 file-level "test's own holder" hits are noise, because inertness is a **scope** question a grep cannot answer. **Falsify each patch in the module you are repairing** — that is how all five were actually found.

11. **EXPLAIN AN UNEXPECTED DELTA BEFORE REPORTING IT — and never subtract one.** Both directions have now cost real accuracy:

    - A "4-failure environmental floor" was **subtracted across three mutation rounds** and turned out to be a genuine fixture defect (tests passing only because this repo happens to have a `logs/` directory).
    - Two apparent leaks this evening were **the dev machine itself**: the repo's `logs/` growing during a run was the live toolguard hook logging the agent's own Bash calls, and stray `.pyscn/reports/analyze_*.html` files were `pyscn analyze` running externally every ~45 seconds. One agent established this with a **22-second idle control plus per-test attribution across 189 tests** before declining to file a leak.

    A baseline you cannot explain is a finding, not a constant. Chase it in whichever direction it points.

    **Third source, found the same evening: sibling agents share the session scratchpad.** One agent's hostile-HOME fixture showed pre-existing files; their mtimes (16:26 and 18:16, against a 21:04 run) identified them as **another campaign agent's leftovers**. Re-running against `mktemp -d` was clean. **Use `mktemp -d` for any scratch HOME**, and check mtimes before attributing anything to the code under test.

12. **RESET PERSISTENT STATE BETWEEN MUTANTS — the artifact IS the mechanism's state.** Where the thing under test writes its state to a file, the **first mutant that lets a write through makes every later mutant look correct.**

    Measured 2026-08-13: `logs/toolguard-discovery.log` *is* `log_discovery`'s state. An agent's first sweep reported a "detects but does not suppress" mutant as zero-detection; with `logs/` restored to pristine before each run, **three** tests detect it. The whole sweep had to be re-run.

    The same applies to the suppression store, any cache, and any append-only log. **Establish a null-mutation baseline across repeated runs before trusting any number** — trap 6's repeat-run pollution, in the harness rather than the module.

13. **A FIXTURE TREE BUILT IN A BARE TEMP DIR IS NOT ISOLATED IF THE CODE WALKS UPWARD.** Measured 2026-08-13 in `test_tools_project_root`: fixtures were built under `TMPDIR`, i.e. **outside `$HOME`**, so `iter_dirs_upward` ran all the way to `/`. A `/tmp/pyproject.toml` left by any other process turns a `NONE` result into `AMBIGUOUS`; with `TMPDIR=$HOME/tmp` the dev machine's own `~/.claude` resolves as `RESOLVED_ANCHOR`.

    **Build the fixture inside a throwaway `HOME`** so the walk terminates inside the fixture. The follow-up queue had spotted the precondition and called it *"not a defect today"* — it was a latent one, and it is the same class as the campaign's other environment leaks.

    **The same warning applies harder to git fixtures**: a repo created inside another repo, or inside `/tmp` where a parent `.git` exists, does not behave as expected.

14. **MEASURE AT THE RIGHT TIER, OR A ZERO-SURVIVOR RESULT IS AN ARTIFACT.** When a module has more than one **declared source of truth** for the same value — a production table plus an expected-value table plus a doc block — a naive sweep mutates only the production copy, every mirror-comparison test dies, and the module reads as fully covered. It is not.

    Measured 2026-08-13 on `recommended_protections`, which declares three sources and whose own docstring asks a developer to update all of them **in one reviewed change**:

    | tier | what is mutated | result |
    |---|---|---|
    | **A** | the production value only | everything dies, on a test comparing against a literal copy |
    | **B** | + every declared mirror (expected tables, `docs/security.md`) | everything still dies — but on **shape** invariants and hardcoded expected-*name* arguments |
    | **C** | + drop the expected-name equality, keep only the behavioural assertion | **six weakenings survived** |

    **Tiers A and B only tell the developer "the value changed", which they already know** — they are doing the change. Only tier C asks *"does this still do what it exists to do?"*

    **REFINEMENT 2026-08-14, and it corrects the recipe above.** Tier A as stated — "mutate the production value only" — is **not a realistic state**. A real edit is re-imported *everywhere*, so leaving the **test module's own by-value imports** bound to the original makes `assertIs` mirror tests fire **spuriously**: a false *detection*, which is the opposite of the usual failure and reads as coverage.

    **Rebind every holder, the test module's included, and then measure behaviour.** And find the holders by an **identity scan over `sys.modules`**, not by grep — that is how one agent found ten production holders of `FILE_KIND_TOOLS`, including two names in `hook.py` for the same object. Grep finds imports; identity finds aliases.

    **But an identity scan sees only what is already IMPORTED, so every count it gives is a LOWER BOUND.** Two agents scanned the same constants hours apart and disagreed — `FILE_KIND_TOOLS` 10 vs **14**, `BUILTIN_TOOLS` 6 vs **8**, `KNOWN_TOOL_NAMES` 3 vs **6** — purely because different consumers were loaded. **Import the consumers you care about first, then scan**, and report the count as a floor rather than a total.

    What tier C found: six patterns naming a whole family (`.ssh/**`, `.aws/**`, Read and Write, both anchoring forms) were each pinned by exactly **one** witness file, so narrowing the family to that witness was invisible. A config narrowed that way passed every test while leaving `~/.ssh/id_ed25519`, `~/.ssh/config`, `~/.aws/config` and `~/.aws/sso/cache/*.json` — live SSO tokens — fully readable and writable.

    **Also worth copying: that agent noticed a mutant it killed for a fragile reason.** `.env.*` -> `.env.local` died only because one probe happened to use `.env.local` and another `.env.production` — an accidental cross-probe difference that anyone "tidying" the tables would remove. It made the difference explicit rather than banking the kill.

15. **A FIXTURE BUILT ENTIRELY FROM FIELD DEFAULTS IS WHAT LETS HARDCODING MUTANTS THROUGH.** If every field of a fixture holds its type default — or the same value the rest of the fixture uses — then a mutant that *hardcodes* that field is invisible, because the correct value and the hardcoded one coincide.

    Measured 2026-08-13 in `test_tools_edit_proposal`: **one fixture repair killed seven mutants at once** (`level`, `source_type`, `file_format`, `specificity`, the edit's `tool`, the proposal's `tool`, and `action`). Rebuild so **no field carries its default and no two fields share a value**, and pass non-`None` values for optional parameters — `start_dir=None` hid an eighth.

    **This is why a tidy-looking fixture is a warning sign.** The read-only queue pass over that file recorded *"its fixtures build exactly what its Givens describe"* — which was **true**, and was precisely the defect: the Givens described defaults.

16. **DO NOT BUILD A MUTATION WATCHDOG ON `TimeoutError`.** `TimeoutError` has been an **`OSError` subclass since 3.3**, so any code under test with a broad `except OSError` **swallows the alarm** and reinterprets it as its own domain error. Measured 2026-08-13 in `file_lock`: a SIGALRM watchdog raising `TimeoutError` was absorbed by `_try_acquire_posix`'s `except OSError` and read as "the lock is contended" — so **a deadlocking mutant reported as a clean survivor with zero failures.** The agent caught it only because an independent kernel probe said a blocking `flock` *must* deadlock while the sweep said otherwise; re-running with a `BaseException`-derived alarm flipped it to detected.

    **Derive any watchdog from `BaseException`.** This is not specific to `file_lock`: there are **40 `except OSError` sites across 19 production files**, including `once_per_store`, `_git`, `install_update`, `config`, `installer` and `config_access`.

    **Scope of the retrospective risk, stated precisely rather than alarmingly**: the hazard bites only where an agent *used* a watchdog, and a watchdog is only needed where a mutant can **block** — which in practice means `file_lock`, `once_per_store` and the subprocess-driving modules. And the corruption runs in one direction only: a swallowed alarm makes a **detected** mutant look like a **survivor**, so it *inflates* apparent coverage gaps rather than hiding them. **No filed ticket is at risk of being falsely severe because of it.** The cost is wasted work and a false "zero detection" claim, not a missed defect.

17. **VERIFY THE MUTANT IS LIVE — installing it is not the same as it taking effect.** Three harness bugs this evening produced *false SURVIVED* readings, and all three were caught by an **active check** rather than by review:

    - Restoring class identity after a re-exec silently undid **20 method-level mutants**, every one reported as surviving.
    - A `co_code`-only fingerprint missed string-literal mutants, because the test guard re-wraps the target with `functools.wraps`.
    - A decorator-stripping bug made three mutants read as *detected* with `TypeError: 'property' object is not callable`; after the fix, one **survived**. A count-only reading would have recorded a gate's verdict property as fully covered.

    **Assert, per mutant, that the live object differs from the original in the way you intended** — compare the source you compiled, not just the bytecode, and re-check after every restore step. Then read the tracebacks: a failure for the wrong reason is not detection.

    **A fourth, found 2026-08-14, and it is the nastiest**: an agent's `sys.modules` identity scan rebound **the harness's own `original` variable**, so the restore anchor *became the mutant*. It surfaced only as `AssertionError: mutant is not live` — **without the per-mutant liveness assertion it would have leaked mutants into every later round and read as universal detection.** **Exclude `__main__` from any identity scan.**

    **And when auditing writes: a name-only directory snapshot cannot see a REWRITE.** One agent's write-detection guard read NOT DETECTED until the snapshot included **size and mtime**.

    **A SNAPSHOT CANNOT ATTRIBUTE A WRITE, and on this machine the thing it keeps catching is US.** An agent's guard fired repeatedly under `~/.claude`; the culprit, measured, was **`~/.claude/projects/.../subagents/agent-*.jsonl` — the agent's own transcript, rewritten mid-run.** Pair the snapshot with an **attribution-based recorder** (wrap `builtins.open` / `io.open` / `os.open` / `remove` / `unlink` / `rmdir` / `mkdir` / `makedirs` / `rename` / `replace`, and self-test it by pointing the guarded roots at a fixture and exercising all four write routes), exclude the transcript tree from the snapshot with the reason recorded in the code, and keep repo `logs/` out of it — every concurrent toolguard-governed process appends there.

**Cost note**: digesting all of `~/.claude` is **3.9 s per snapshot** (22.5 k files, 301 MB) against 0.4 s for `~/.toolguard`. Scope the digests and say why in the code.

**And watch for shape 22 IN REVERSE in your own guard**: `assertTrue(_SNAPSHOT_BEFORE)` failed under an empty or non-existent `HOME` — which would have broken this repo's own pre-push *"run the suite against an empty `$HOME`"* step. Assert the snapshot **ran**, and accept zero files only when no anchor exists.

**CORRECTION 2026-08-14 — `(name, size, mtime_ns)` is ALSO insufficient on this machine, and I had been prescribing it.** An agent falsified its own snapshot by rewriting a 4-byte file with 4 *different* bytes: `mtime_ns` came back **byte-identical**, because WSL2 tmpfs uses the kernel's coarse timestamp and both writes land in the same tick. **Only a content hash saw it.** Snapshot `(name, size, sha256)`, and **prove the snapshot fires against all three of a planted file, a same-length in-place rewrite, and a deletion** before trusting a clean result. Assuming a self-check works is the same error the check exists to catch.

18. **PRE-IMPORT EVERY CONSUMER BEFORE THE FIRST REPLAY.** A whole ten-mutant battery came back wrong because `toolguard.api` was imported **lazily during the first replay** and permanently bound that run's mutant — so every subsequent mutant reported the first one's signature, and the readings were internally consistent and entirely false. The agent caught it by noticing identical signatures and re-ran with all consumers pre-imported. **Identical results across different mutants is the tell.**

18. **"ZERO FAILURES" IS NOT THE ONLY BAD SIGNAL — "THE SAME ONE FAILURE FOR EVERY MUTANT" IS WORSE, BECAUSE IT READS AS COVERAGE.**

    Measured 2026-08-14 in `test_tools_hierarchy`. My brief predicted the usual zero-detection result and **was wrong**: inverting precedence failed 1 test. But so did flattening every level, dropping the broadest layer, **and** dropping the most specific one — **all four with an identical failing-test set.** Eight further mutants all fired one *other* single test and nothing else. **Two over-loaded canaries were carrying the entire module.**

    A count of 1 looks like detection. It is not: four mutually contradictory mutations producing the same failure means the suite can tell *something changed* and nothing about *what*. This is trap 17's "identical results across different mutants is the tell" — present in the data and easy to read past, because the eye is looking for a zero.

    **The worst instance measured**: in `test_change_role_classifier`, **34 zero-detection mutants all shared one signature — the empty set** — while 23 of the module's 37 classification rules could be deleted with a green suite. Its follow-up-queue section opened *"mutation testing here found the detection rate good (3 of 5 mutations caught)"*: **a five-mutant sample generalised into a verdict**, on a module measured at **58% survival over 81 mutants**. That is the completeness failure mode's most dangerous variant — **the misleading part is the reassuring summary line, not a missed finding.**

    **Always diff the failing-test SETS across mutants, not just the counts.** And record `(test_id, failure_reason)` signatures rather than IDs alone: an agent found two mutants showing *newly-failing = 0* that were in fact detected, because the test was already RED and only the reason fingerprint distinguished them.

19. **A BADLY CHOSEN MUTANT READS EXACTLY LIKE ZERO DETECTION.** Found 2026-08-14. An agent's stub for `primary_role` returned `sorted(roles)[0]`, which **coincidentally agrees with the real precedence** on the tested input — `DECISION` sorts before `WRITE` — so it reported zero detection for a mechanism that is in fact covered. Re-run as `list(roles)[0]`, it failed the existing test immediately.

    **Confirm the mutant actually changes the output on your fixtures**, not merely that it compiled and is bound. A mutant that happens to agree with the original on every input you feed it is not a mutant; it is a slower way of running the original.

    **Seen again immediately, in the next module**: an agent's probe used a **symmetric** fixture (one bare name, one qualname) for a swap mutation, reported "no output change", and would have logged it as an **equivalent mutant** — while two tests do detect it. Fixed with an asymmetric fixture. **Symmetry in a fixture hides a swap**, the same way defaults hide hardcoding.

20. **`unittest` ROUTES `subTest` FAILURES THROUGH `addSubTest`, NOT `addFailure`.** Found 2026-08-14. A mutation harness that scores a suite by counting `addFailure` calls **under-reports every subtest-based detection**. Measured: one mutant read as **undetected** when the repaired test does catch it, purely because the detection arrived as a subtest.

    **Override `addSubTest` in any custom result class, or diff test IDs from the runner's own output instead of counting callbacks.**

    **Retrospective scope**: this under-reports detection, so it **inflates apparent gaps** rather than hiding defects — the same safe direction as the `TimeoutError` trap. But several modules this campaign used `subTest` heavily (`test_tools_uninstall_readiness` alone has 20), so a "zero detection" reading on a subtest-based suite is worth re-checking before it is quoted. If two different mutations fail the same set, you have one canary, not two detectors. That module's final mix was **0 cannot-fail and 8 cannot-distinguish** — the opposite of `test_hierarchical.py`, which was mostly vacuous.

## Coordinator brief errors, recorded because the pattern matters

- **I conflated two different "ask floors."** Wave 3's brief said ticket 11 concerned the TOO-19 parse-failure floor; ticket 11 is actually about the inline/heredoc foreign-code floor. Two mechanisms, one name, and I sent an agent after the wrong one. It caught the error itself and reported it rather than following the brief.
- This is now the second campaign in a row where **agents catch coordinator brief errors at a steady rate**. The #07 sweep logged fifteen-plus. The mechanism is the same one TOO-52 is built on: an agent verifying against the code beats a coordinator working from memory, including when the coordinator wrote the notes.

## Production observations accumulated from repair agents

Not test defects; found incidentally and worth their own dispositions:

- **`permissions.py:133`'s `.replace("**", "*")` is a semantic no-op.** `fnmatch` treats `**` and `*` identically, and the `**/x/**` case is handled and `continue`d before it. Its one live effect: the `"**"` entry of `args_pattern in ("*", "**", "")` at `:156` is unreachable except via three-or-more consecutive stars.
- **`test_permissions.py` tests only 4 of the 8 public names** in `toolguard/permissions.py`. `is_universal_pattern`, `resolve_allow_ask`, `decide_command_at_level_detailed` and `check_hard_deny` are never imported there.
- **`test_hierarchical.py`'s compound tests drive `compound.resolve_compound_permission`, whose own docstring says it is not on the production path.** That coverage pins a legacy alias.
- **Ticket 18 is live and unpinned**: `git log:*` matches `git logfoo`; `git commit:*` matches `git commit-tree abc`.

## Verification gate, run by me between waves

- full suite: `uv run python -m unittest discover -s test -t .` — the count must **rise or hold**, never fall silently
- `uv run ruff format --check .` and `uv run ruff check .`
- **no production file modified**: `git diff --name-only` must show `test/` paths only
- spot-mutate two repaired tests per wave myself, independently of the agent's claim

## Budget

**Superseded by Arnon 2026-08-12 ~17:55**: *"use a small fleet, regularly check remaining budget and stop when you hit 99%."* So the earlier "nothing dispatches before the reset" line is void — he raised the ceiling deliberately, knowing the weekly resets Aug 13 09:59 ET and that unspent budget at reset is simply lost.

Operating rule for the overnight run:

- **Check `~/bin/claude-usage` after EVERY wave**, before dispatching the next one. Never dispatch blind.
- **Hard stop at 99% weekly.** At the stop, do not start another wave; report and wait for the reset.
- **Small fleet: 3 concurrent agents.** Wave 1 was `test_compound.py`, `test_bash_parser.py`, `test_hard_deny.py` — the two named concentrations plus the unoverridable-refusal pool.
- **No polling cron.** Agent completions re-invoke automatically; a timer that wakes only to check on them burns budget for nothing, which is precisely what Arnon warned against.

## Ticket updates owed as this proceeds

- **31** — the triage decision, plus the actual repaired/left-failing counts. It currently asks for a decision; record that Arnon made one.
- **17, 19, 22, 24, 28, 29** — each names a coverage gap; record whether tier 2 closed it.
- **New tickets** for production defects surfaced by de-vacuuming a test. These are the campaign's real output and must not stay in this file.