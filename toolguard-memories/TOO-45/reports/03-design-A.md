---
title: 03-design-A
type: note
permalink: toolguard/too-45/reports/03-design-a
---

# TOO-45 — removing the `resolve` <-> `permission_resolution` runtime cycle (Design A)

## 0. Summary in one line

Do not move the loop, do not move the data, do not add a driver: **move the callee**. The injected callable stays, but its code relocates to modules strictly *below* `permission_resolution`, so nothing in `resolve.py` ever executes under `permission_resolution`'s stack frame again. The cycle dies; laziness, the test doubles, and all three Protocols survive untouched.

---

## 1. The shape I chose, and why

### The chosen shape: "move the callee, keep the injection"

The cycle is not caused by the injection. It is caused by *where the injected function's body lives*. Today `resolve.py` declares two `_decide_detailed` closures (lines 466 and 780) and hands them down to `resolve_permission_detailed`; that is what puts `resolve` frames above `permission_resolution` frames at runtime, and that is the whole of the cycle.

Look at what those two closures actually do:

- The Bash closure (`resolve.py:780`) is a **five-line argument-order adapter** over `permissions.decide_command_at_level_detailed`. Not one line of decision logic lives in `resolve.py`. The runtime edge `permission_resolution -> resolve` for the Bash path is a frame that immediately jumps back down to `permissions`. It is a cycle of pure adapter.
- The file-path closure (`resolve.py:466`) is the same adapter, over `_decide_file_path_at_level_detailed` — which *does* live in `resolve.py`, along with its four private helpers (`_anchor_file_pattern`, `_collapse_slashes`, `_match_file_path_pattern`, `_first_matching_file_pattern`). That cluster is the only real code in `resolve.py` that `permission_resolution` reaches.

So the cycle is: one adapter that adapts nothing, plus one self-contained matcher cluster that is sitting in the wrong module. It is *not* an architectural entanglement of decision policy — fact (4) already told us no policy has to move, and this is the mechanical reason why.

The fix, concretely: turn each adapter into a small callable object defined in the module that owns the matching, and relocate the file-path matcher cluster into a module of its own. `resolve.py` then *constructs* a matcher (a downward call) and *passes* it (a value, not its own code) into `permission_resolution`. Every runtime edge points down.

**Why this and not the others, in the measured facts:**

- **Matches as data — rejected on fact (3), but not on the cost you would expect.** I measured it and the naive cost argument is weaker than it looks (see §3): on Arnon's live config the hierarchy has **only 2 levels**, and for an *allow* verdict `_detect_override` already re-scans the lower levels, so eager evaluation would already be the status quo on the common path. The real objection is different and worse. Matching is not pure: `permissions.py` matching reaches `normalization`'s `exists()`/`is_symlink()`/`resolve()` (measured: L1's 148 patterns cost 253 µs, dominated by filesystem syscalls), and `patterns.py` runs user-supplied regex via `re.search` with no timeout. Today a pathological or expensive rule sitting at the *user* level is simply never executed whenever a project-level rule wins. Eager evaluation makes every rule in the whole hierarchy execute on every decision, per sub-command. That converts a bounded cost into an unbounded, user-controlled tail — and it is invisible to every test, because the corpus asserts verdict objects and the verdicts are identical. That is precisely the "wrong in production while every test passes" hazard the brief names, and it is a permanent architectural commitment: once `permission_resolution` is a fold over a list, laziness cannot be recovered without a second refactor.
- **Inverted iteration — rejected on facts (4) and (5).** Moving the level loop into `resolve.py` moves the cascade *order* — first-match-wins, and the `_detect_override` scan of less-specific levels — into the caller. Fact (4) says the value of this cycle over the `compound <-> resolve` one is that *no policy has to move*; inverted iteration voluntarily gives that away. And fact (5) says there are **two** call sites, so the loop lands in two places and must be kept in step by hand. This codebase already carries a documented scar from exactly that failure mode: `apply_parse_failure_floor` exists as a single shared function with a docstring that says "there must be exactly ONE implementation so the two call sites cannot drift". Inverted iteration re-creates the shape that function was written to prevent.
- **Decompose into three — rejected as over-delivery, on the observation above.** Its "pure per-level matcher" is exactly the relocation I am proposing. Its "pure decision fold" is `permission_resolution` as it stands today. Its "thin driver above both" is `resolve.py` as it stands today. Once the matcher moves out of `resolve.py`, the third module has no job left: it would be a new public seam, a new layer-map entry, and a new set of docstrings, added to describe a call chain that is already acyclic. If someone proposes it, ask them to name a function that would live in the driver and does not already live in `resolve.py`.

---

## 2. The new call topology

### New / moved code

**New module `toolguard/file_matching.py`** (engine layer). Contains, moved verbatim out of `resolve.py` and made public:

| now | becomes |
|---|---|
| `resolve._anchor_file_pattern` | `file_matching.anchor_file_pattern` |
| `resolve._collapse_slashes` | `file_matching._collapse_slashes` (stays private, single module) |
| `resolve._match_file_path_pattern` | `file_matching.match_file_path_pattern` |
| `resolve._first_matching_file_pattern` | `file_matching._first_matching_file_pattern` |
| `resolve._decide_file_path_at_level_detailed` | `file_matching.decide_file_path_at_level_detailed` |

Its imports: `config_types` (for `LevelMatch` and the new `PathAnchoring` Protocol), `normalization.expand_tilde`, `patterns`, and `permissions` (`is_universal_pattern`, `resolve_allow_ask`). It imports **nothing** from `resolve` or `permission_resolution`.

*Considered and rejected:* folding these into `permissions.py` next to their command-side twin. That would remove the allow/deny asymmetry three separate docstrings in this codebase currently apologise for — genuinely attractive — but `permissions.py` today has zero dependency on any configuration surface, and file-path anchoring needs `resolve_config_path`. I would rather not spend that property to save a file. Worth revisiting only if `permissions.py` ever acquires a config dependency for another reason.

**Two matcher types**, each a `@dataclass(frozen=True)` with `__call__`, each defined in the module that owns the matching:

```python
# toolguard/permissions.py
@dataclass(frozen=True)
class CommandLevelMatcher:
    """Match one sub-command against one hierarchy level's allow/deny/ask lists."""
    sub_command: str
    extended_syntax: bool

    def __call__(self, allow_patterns, deny_patterns, ask_patterns, /):
        return decide_command_at_level_detailed(
            self.sub_command, list(allow_patterns), list(deny_patterns),
            self.extended_syntax, ask_patterns=list(ask_patterns),
        )
```

```python
# toolguard/file_matching.py
@dataclass(frozen=True)
class FilePathLevelMatcher:
    """Match one file path against one hierarchy level's allow/deny/ask lists."""
    file_path: str
    config: PathAnchoring
    extended_syntax: bool

    def __call__(self, allow_patterns, deny_patterns, ask_patterns, /):
        return decide_file_path_at_level_detailed(
            self.file_path, list(allow_patterns), list(deny_patterns),
            self.config, self.extended_syntax, ask_patterns=list(ask_patterns),
        )
```

Frozen dataclasses rather than factory functions returning closures, deliberately: they satisfy the Protocol structurally just as a closure does, but they have a `repr`, they are comparable, they can be constructed in a test without a factory call, and — the load-bearing reason — a *class* is a thing the fitness predicate in §6 can see and reason about, where an anonymous closure with the same body would need special-casing.

### The two call sites

`resolve.py:493` becomes:

```python
resolved = resolve_permission_detailed(
    config, tool_name,
    FilePathLevelMatcher(file_path, config, extended_syntax),
    subject="Path",
)
```

`resolve.py:802` becomes:

```python
resolved = resolve_permission_detailed(
    config, "Bash", CommandLevelMatcher(sub_command, extended_syntax)
)
```

Both local `_decide_detailed` closures are deleted. Everything else in both functions is unchanged, including `_check_file_path_hard_deny` (it stays in `resolve.py` and imports `anchor_file_pattern`/`match_file_path_pattern` from `file_matching`) — hard deny runs *before* the orchestrator and was never part of the cycle.

### Resulting topology

```
hook / api  (runtime, api)
   |
   v
resolve                                   (engine)
   |-- constructs --> permissions.CommandLevelMatcher
   |-- constructs --> file_matching.FilePathLevelMatcher
   |-- calls ------> file_matching.{anchor,match}_file_path_pattern   (hard-deny path)
   |-- calls ------> compound.{decompose, judge_unit, _combine_strictest}
   |-- calls ------> permission_resolution.resolve_permission_detailed
                            |
                            |-- calls --> config_types.{provenance_for_pattern, entry_for_pattern}
                            |-- calls --> matcher(allow, deny, ask)
                                              |
                                              +--> permissions.decide_command_at_level_detailed
                                              +--> file_matching.decide_file_path_at_level_detailed
                                                        |
                                                        +--> permissions.{is_universal_pattern, resolve_allow_ask}
                                                        +--> patterns, normalization
```

Every arrow points down. `permission_resolution` still imports only `config_types` and the stdlib — its module docstring's central claim survives verbatim. `permissions` and `file_matching` still do not import `permission_resolution`. The static import graph is acyclic *and* the runtime call graph is acyclic, which is the thing that was untrue before and is the whole point.

The one docstring that must change materially is `config_types.py:830-857`, the block that opens "`permission_resolution` and `resolve` form a runtime cycle static analysis cannot see". It stops being true; replace it, do not soften it.

---

## 3. What happens to laziness

**Nothing. Zero change.** `_resolve_unclamped` still walks levels most-specific-first and still returns on the first match; `_detect_override` still scans only levels below the winner and still skips levels with an empty deny list. This shape is the only one of the four that leaves the short-circuit exactly as it is, and that is a substantial part of why I chose it.

Because the brief asks me not to hand-wave this, and because it is the number the *other* shapes live or die on, I measured it rather than reasoning about it. Read-only probes against the live config in this repo (`load_configuration`, `ignore_env_override=True`), 200 iterations each, warm:

| measurement | value |
|---|---|
| hierarchy levels for `Bash` | **2** (L0 project: 38 allow / 2 deny / 0 ask; L1 user: 71 / 53 / 24) |
| levels for `Read` / `Write` / `Edit` | 2 each, 10-13 patterns total |
| `permission_levels_with_provenance('Bash')` | 254 µs per call — rebuilt once per decision, not cached |
| L0 match (40 patterns) | 50 µs |
| L1 match (148 patterns) | 253 µs |
| full lazy cascade, one sub-command, `git status` | ~1030 µs |
| end-to-end hook process, `git status` | **100-140 ms** |

Four things follow, and they are worth writing down whatever shape is chosen:

1. **The hierarchy is shallow — 2 levels, not the 4-5 the "levels" language suggests.** The `~/.toolguard/rules/*.toml` files do *not* form a third level: `permission_levels_with_provenance` groups by `provenance.specificity` and they collapse into the same `user` level as `~/.claude/settings.json`. Any design argument that scales with "number of levels" is arguing about the constant 2.
2. **Eager evaluation would cost at most ~253 µs per sub-command here** — the L1 match that a level-0 deny or ask currently skips. Against a 100 ms process that is 0.25%, and even a five-leaf compound tops out around 1.3%. On *allow* verdicts the delta is roughly zero, because `_detect_override` already evaluates the lower level. **So the cost argument against "matches as data" is real but small, and I decline to rest the design on it.** The argument I do rest on is the tail: matching executes user-supplied `re.search` with no timeout and does per-pattern filesystem syscalls, so the worst case is set by the user's rules, not by these numbers, and the corpus cannot detect a change in it.
3. **If anyone does want to spend latency here, the level-structure rebuild is the better target.** 254 µs of the ~1030 µs cascade is `permission_levels_with_provenance` reconstructing the same tuples on every call — and in the Bash path that is *per sub-command*, so a 5-leaf compound pays it five times for an identical result. Caching it on `Configuration` is a bigger, safer win than anything in this refactor. Out of scope; file it.
4. **Does it need measuring before committing?** For *my* shape, no — it changes the work performed by exactly one frozen-dataclass construction per sub-command (sub-microsecond against ~1030 µs), and I would still re-run the numbers above as a before/after check rather than assert it. For the eager shapes, **yes, and not with these numbers** — a 2-level config with 188 patterns is the easy case. The measurement that would actually decide it is a config with a populated rules directory at a *distinct* specificity and at least one regex-heavy level, which is a supported shape this machine does not happen to have.

---

## 4. The test doubles (fact 6)

**They all survive, unchanged, and that is the single strongest practical argument for this shape.**

The injection point is not removed — only the identity of the production implementations changes. Every hand-built `decide_detailed` closure keeps working exactly as written:

- `test/unit/test_hierarchical.py:228` (plus its call sites at 252, 340, 364)
- `test/unit/test_configuration.py` — the `_decide` / `_decide_allow_git` / `_decide_deny_rm` family (~2936, 2979, 3315, 3397, 3410, 3663) and their ~15 call sites
- `test/unit/test_hard_deny.py:394`
- `test/unit/test_takeover_mode.py:299`
- `test/unit/test_logging_streams.py` (six call sites)
- `test/unit/test_permission_resolution.py` (two call sites)

None of these needs an edit for the cycle removal. The only test churn is mechanical and confined to the *moved* names: `test_hook.py:39` imports `_decide_file_path_at_level_detailed` from `toolguard.resolve`, and `test_hierarchical.py:522-566` imports `_anchor_file_pattern` from `toolguard.resolve` in four places. Those become imports from `toolguard.file_matching` under the new public names.

Why this matters beyond convenience: fact (7) says the corpus is a strong net *because it compares verdict objects*. That net is only as good as the assumption that the tests were not edited to match the new code. Under this shape the ~30 unit-test call sites that exercise the cascade are **byte-identical before and after**, so a green run is independent evidence. Under "matches as data" or "inverted iteration" the seam those tests bind to no longer exists, so the same commit rewrites the code and its tests, and the corpus becomes the *only* evidence rather than one of two.

One deliberate non-change: several of those doubles (`test_hard_deny.py`, `test_takeover_mode.py`) hand-roll an adapter that is now literally `CommandLevelMatcher`. Replacing them with the real class would delete duplicated adapter code and is worth doing — **as a separate follow-up commit after the corpus is green**, never in the same commit, for the reason in the previous paragraph.

---

## 5. The three Protocols

None of them were scaffolding for a discarded design. All three survive; one is renamed; one gains a base.

- **`ResolutionConfig` — survives unchanged.** Its four members (`permission_levels_with_provenance`, `has_any_rules`, `resolved_no_match_fallback`, `parse_failures`) are exactly what `permission_resolution` reads, and this refactor does not touch what it reads.
- **`ResolveConfig` — survives, one structural edit.** Declare it `class ResolveConfig(ResolutionConfig, PathAnchoring, Protocol)` and move its `resolve_config_path` member into the new base. No member is added or removed; `Configuration` still satisfies it structurally with no annotation.
- **`DecideDetailed` — survives, and should be renamed to `LevelMatcher`.** The Protocol itself is right: three positional-only pattern lists in, `Optional[LevelMatch]` out, positional-only for the documented pyright reason. What is wrong after the change is its *framing*. Its docstring, and `permission_resolution.py`'s module docstring at lines 37-40, both describe it as "the other half of this seam — the callable THIS module receives back from `resolve.py`". After the change it is not a callback into the caller; it is a matcher manufactured by a module below. Keep the type, rewrite the prose, rename it so no reader inherits the old mental model. Also correct the enumeration inside its docstring: the two implementations are no longer "closures declared inside `resolve.py`" but `permissions.CommandLevelMatcher` and `file_matching.FilePathLevelMatcher`.

**New: `PathAnchoring(Protocol)`** in `config_types`, one member, `resolve_config_path(self, raw_path: str) -> str`. It exists so `file_matching` can be typed without acquiring a dependency on the full configuration surface — the same argument that produced `ResolutionConfig`, applied one module further down. A one-member Protocol is worth its four lines here precisely because the alternative on offer is the bare untyped `config` parameter `_anchor_file_pattern` has today.

**Deletion test, offered as a review heuristic:** if a competing design deletes `DecideDetailed`, that design has deleted laziness with it. The Protocol exists because levels are matched *one at a time, on demand*. A shape that folds over precomputed matches does not need it — which is the tell, not the benefit.

---

## 6. Preventing the cycle from coming back

Fact (9) is right and it is the part of this work that outlives the refactor. Nothing today prevents this, and nothing would prevent someone reintroducing it next month by writing one convenient closure. A fitness predicate is warranted. I propose **two**, because the honest static check has a real blind spot and the honest dynamic check is slow.

### 6a. Static predicate — `find_callback_cycles`, in `tools/architecture_fitness.py`

Assertion, stated exactly:

> For every module `C` in the `toolguard` package, and every call in `C` whose callee resolves to a name imported from another in-scope `toolguard` module `M`: if any argument of that call is
> **(a)** a `Name` bound to a `def` / `async def` / `lambda` defined anywhere in `C`, or
> **(b)** a `functools.partial(f, ...)` whose first argument is such a name, or
> **(c)** an instantiation of a class defined in `C` that declares `__call__`,
> then report `C -> M -> C` as a runtime callback cycle.

Rationale for each clause: (a) is today's `resolve.py` at both call sites — it is what the predicate must catch to be worth writing. (b) is the obvious two-line evasion. **(c) is load-bearing precisely because of my own design**: I am introducing callable classes as the sanctioned pattern, so a reader who wants a matcher "close to where it's used" will reach for `class _Matcher` inside `resolve.py`, and without (c) the predicate would wave it through while reinstating the exact cycle.

It should reuse the existing machinery: `resolve_toolguard_import`, `R1_OUT_OF_SCOPE_PACKAGES` / `R5_OUT_OF_SCOPE_PACKAGES` for `parser/`, and `is_generated_file`. Note that it is *not* subsumed by the existing `find_import_cycles` (R5), which sees only import edges and by construction cannot see this class of cycle — that is the whole premise of the ticket.

Retroactive validation, which should be part of accepting it: the predicate must flag `resolve.py` before the change (2 findings) and the pre-`3bb21b7` `compound <-> resolve` cycle, and must be clean after.

Known blind spot, to be stated in the predicate's own docstring rather than discovered later: a local callable that is stashed in a dict, list, or attribute before being passed evades all three clauses. This is a heuristic that raises the cost of reintroduction, not a proof.

### 6b. Dynamic check — one test, the profile that found the bug

The cycle was found by profiling a real decision. Make that a test. Over a small sample of golden-corpus cases (10-20 is plenty; they all traverse the same call graph), install a `sys.setprofile` hook, record the `(caller_module, callee_module)` edges for `toolguard.*` frames only, and assert the resulting module-level call graph is a DAG.

This is stronger than 6a — it has no blind spot for indirection, and it would have caught both cycles — and it costs a fraction of a second because the sample is small and the tracer only records module pairs. Run it as an ordinary unit test. If it ever fails, its failure message should print the offending cycle as a path, not a boolean.

Use both: 6a as the always-on, fast, reviewable guard; 6b as the one that is actually true.

---

## 7. Risks, most dangerous first

1. **The moved file-path matcher gets the wrong `config`, silently re-anchoring every relative pattern.** `anchor_file_pattern` calls `config.resolve_config_path`; if the move mis-wires it (or a reviewer "simplifies" the new `PathAnchoring` parameter away and reaches for something else), every relative `Read`/`Write`/`Edit` pattern in the hierarchy re-anchors and file-path verdicts change wholesale. **Check:** the golden corpus, 6,025 `realistic` cases, comparing verdict objects — path anchoring is exactly what it is sensitive to. Reinforce it by requiring the review diff to show the move as a *rename* (`git diff -M --find-copies-harder`), not a rewrite: any hunk inside the moved bodies is a red flag on its own.
2. **`_match_file_path_pattern`'s `except ValueError, TypeError: return False` is load-bearing and easy to "clean up" in transit.** It is what stops a malformed user regex from crashing the hook — and a crashed hook fails *silently* in Claude Code (only exit code 2 blocks), so this failure mode is invisible. **Check:** confirm a unit test covers a malformed pattern before moving; add one if not. Also note for whoever does the move that ruff on this project rewrites `except (A, B):` to `except A, B:` — that is expected here and must not be "fixed" back.
3. **Renaming five privates to public leaks references.** The names appear in `test_hook.py`, `test_hierarchical.py`, `test_recommended_protections.py`, `test_architecture_fitness.py`, `config_types.py` docstrings, `resolve.py`'s own module docstring, and `hook.py`'s re-export contract ("`hook.py` re-exports every name that was previously importable from it"). **Check:** exhaustive grep for the five names across `toolguard/`, `test/`, `tools/`; then `find_private_imports` (R6) for anything cross-module that survives; then the full `unittest discover`.
4. **The new module is not registered in the layer map and degrades silently.** `.pyscn.toml`'s own comment says an unlisted module is silently unmapped and its dependencies stop being validated. **Check:** `uv run python tools/architecture_fitness.py --layers` completeness section reports UNMAPPED; add `file_matching` to the `engine` packages list in the same commit.
5. **A new static import cycle via `file_matching -> permissions`.** Harmless today, but it constrains `permissions.py` forever. **Check:** `find_import_cycles` (R5) already covers it; run `--cycles`.
6. **The renamed Protocol drags a docstring sweep wide enough to introduce a wrong claim.** This codebase's docstrings are long, cross-referential, and load-bearing; `DecideDetailed` is named in `config_types.py`, `permission_resolution.py`, `resolve.py`, `permissions.py`. A half-done rename leaves prose describing a cycle that no longer exists — which is worse than the cycle, because it teaches the next reader the wrong model. **Check:** grep for `DecideDetailed`, `decide_detailed`, and the literal phrase "runtime cycle" after the change; every surviving hit must be either the parameter name or a deliberate historical note.
7. **Per-sub-command dataclass construction is a latency regression.** It should be sub-microsecond against a ~1030 µs cascade, but assert rather than assume. **Check:** re-run the §3 probes before/after; the numbers to beat are ~1030 µs per cascade and 100-140 ms end-to-end.

---

## 8. Effort estimate

**Files touched: ~20-25. Hours: 6-8 with the fitness predicate, 3.5-5 without it.**

Breakdown:

| group | files | hours |
|---|---|---|
| `file_matching.py` (new), `permissions.py` (+`CommandLevelMatcher`), `resolve.py` (delete 2 closures + 5 moved functions, 2 call sites) | 3 | 1.5-2 |
| `config_types.py` — rename `DecideDetailed`, add `PathAnchoring`, rewrite the "runtime cycle static analysis cannot see" block and ~5 dependent passages | 1 | 1-1.5 |
| `.pyscn.toml` layer map | 1 | 0.1 |
| Test updates for moved names (`test_hook.py`, `test_hierarchical.py`, `test_recommended_protections.py`, `test_architecture_fitness.py`) — imports and docstrings only | 4 | 0.5 |
| Docstring cross-references naming the callback (`config.py`, `compound.py`, `hook.py`, `session_start.py`, `permissions.py`, `fixture_loader.py`, `corpus_build.py`) | 7 | 0.5-1 |
| `find_callback_cycles` + its tests + the dynamic DAG test, in this module's documentation style | 3 | 2-3 |
| Full test run, corpus run, `ruff`, fallout | — | 1 |

**Calibration against fact (8).** Commit `3bb21b7` touched 79 files and ±24k lines, but three things inflate it relative to this job, and I think it over-predicts by roughly 3-4x:

- it **bundled the Protocol typing work** with the removal; that work is already done and is what makes this design describable at all;
- it **had to move policy** — the ASK floor and `undecidable_fallback` handling out of `compound` — where fact (4) says nothing moves here;
- its line count is dominated by docstring rewrites in a codebase where a single function's docstring routinely runs 30-60 lines, so ±24k lines is not ±24k lines of behavior.

Scaling on the parts that transfer (docstring density, corpus verification, the same review bar) I predict ~20-25 files and roughly 1,500-2,500 changed lines, the large majority of them prose. The behavior-bearing edit is a **move plus two call sites** — that is the actual risk surface, and it is small.

On the ticket's unvalidated "3-6 hours by analogy": I think 3.5-5 h is right *for the cycle removal alone*, so the low end of that range is defensible. It does not cover the fitness predicate, which is ~40% of the total and is the deliverable with the longest half-life. I would rather see the predicate split into its own ticket and *actually done* than folded in and quietly dropped when the refactor turns out to be the easy part.

---

## Appendix: what I verified rather than assumed

- Read `permission_resolution.py` in full, and `resolve.py` lines 1-380 and 380-928.
- Confirmed fact (5): exactly two `resolve_permission_detailed` call sites in `resolve.py` (493, 802).
- Confirmed fact (6) and extended it: the injected doubles appear in **seven** test modules, not four — `test_hierarchical`, `test_configuration`, `test_hard_deny`, `test_takeover_mode`, `test_logging_streams`, `test_permission_resolution`, plus a fake in `test_hook.py:155`.
- Confirmed both `_decide_detailed` closures are pure argument-order adapters, and that only the file-path one reaches code that genuinely lives in `resolve.py`.
- Confirmed `_decide_file_path_at_level_detailed` and its four helpers form a closed cluster whose only outside needs are `normalization.expand_tilde`, `patterns`, `permissions.{is_universal_pattern, resolve_allow_ask}`, and `config.resolve_config_path` — i.e. the move is mechanically clean.
- Confirmed `permissions.py` already imports `config_types`, so hosting `CommandLevelMatcher` adds no import edge.
- Measured levels, per-level pattern counts, per-level match cost, cascade cost and end-to-end hook latency on the live config (probes in the session scratchpad; both were read-only and attested).
- Found nothing in the briefed facts that is wrong. Fact (3) is stated precisely right — laziness is a performance property, not a correctness one — and my §3 argument is deliberately *not* that it is a correctness property, but that its performance envelope is set by user-supplied regex and is therefore not bounded by the numbers I measured.