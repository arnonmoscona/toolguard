---
title: TOO-45 R2 scoping trace
type: note
permalink: toolguard/too-45/too-45-r2-scoping-trace
tags:
- task-memory
- TOO-45
---

# TOO-45 R2 scoping trace

Scouting run, 2026-08-05. MEASURE-AND-PROPOSE only — no R2 work was implemented. Every probe was reverted and the tree verified byte-identical (see "Restoration" at the end). Baseline re-verified by me at the start: suite **2,368 OK**, corpus **6,401 + 61 no differences**, `--guard` PASS 12/12, ruff clean, R2 FAIL with three pairs.

## 1. The instrument, checked before its output was used — IT CANNOT DISTINGUISH SUCCESS FROM FAILURE

`find_parallel_arrays` (tools/architecture_fitness.py:1577) does exactly one thing: it AST-parses `toolguard/**/*.py`, finds a `ClassDef` whose name is literally `ToolPatternLayer`, collects its `ast.AnnAssign` field names, and reports every `X` for which `X_entries` also exists. It never reads a docstring, never looks at a property, never looks at any other class, and never looks at how the fields are used.

I built nine synthetic modules, each carrying **the same index-alignment hazard** under a different spelling, and asked the detector about each. **DEMONSTRATED BY EXECUTION:**

| variant (all semantically identical hazards, except #8) | detector says |
|---|---|
| 0 CONTROL — today's shape | **FAIL (detected)** |
| 1 rename `_entries` -> `_rules` | PASS (invisible) |
| 2 dict-of-lists keyed by kind, two dicts | PASS (invisible) |
| 3 entries hidden behind `@property` | PASS (invisible) |
| 4 class renamed, shape byte-identical | PASS (invisible) |
| 5 arrays moved to a sibling class | PASS (invisible) |
| 6 prose-only invariant, unpaired field names | PASS (invisible) |
| 7 same fields assigned in `__init__` instead of annotated | PASS (invisible) |
| 8 **THE REAL FIX** — entries only, patterns derived | PASS (invisible) |

**The predicate fires on one spelling out of nine and cannot tell the real fix (#8) apart from seven pure gaming moves.** It is a spelling check on the string `"_entries"` inside a class whose name is hard-coded. It is not a hazard check.

Three further findings, all DEMONSTRATED BY EXECUTION:

- **The predicate under-scopes R2 by a whole second instance.** There is a second parallel-array pair with the same prose-defended invariant and the same drift guard: `Configuration.hard_deny(tool)` / `Configuration.hard_deny_entries(tool)`, consumed by index at `resolve.py:294` (`deny_entries[deny_patterns.index(matched_pattern)]`), with the invariant defended in prose at `config.py:1221-1224` and again at `resolve.py:268-272`. It is a *method* pair, not fields on `ToolPatternLayer`, so the detector is structurally blind to it. R2's own predicate would go PASS while this survives untouched.
- **Clause 3 of R2's stated predicate — "no prose-defended index-alignment invariant remains" — is entirely unrepresented in code.** Nothing in the tool reads prose. Variant 6 confirms it: an invariant stated only in a docstring is invisible.
- **Clause 2 — "stripped patterns are a derived property of `RuleEntry`" — is also unrepresented.** Variant 8 (the exact thing clause 2 asks for) and variant 1 (a rename that changes nothing) produce the identical reading. The predicate cannot tell you whether the derivation was done.

### What the instrument would need to become trustworthy

Not a better name-pattern. A different question. Concretely, four checks, in descending order of value:

1. **A positive check, not an absence check.** Assert that `RuleEntry` exposes a public wrapper-stripped-pattern accessor AND that every stripped-pattern collection in `toolguard/` is produced by mapping over entries — i.e. detect the *presence of the derivation*, not the absence of a suffix. Absence checks are what all seven gaming moves exploit.
2. **A use-site check for index-parallel access.** Flag any expression of the shape `A[B.index(x)]` or `zip(A, B)` where `A` and `B` are two separately-stored sequences reachable from the same object. That is the hazard itself, and it catches variants 1-7 and both instances (`config.py:1505`, `resolve.py:294`) without naming a class or a field. It is also the only check that would have found the `hard_deny` pair.
3. **A regression test that renames the fields and asserts the verdict does not move** — the exact device R1g used to close instrument defect #6. Without it, R2's PASS rests on a field name, which is precisely how R1f gamed R1.
4. **A prose check with teeth**: grep the class/method docstrings in scope for the index-invariant language (`index-for-index`, `index-aligned`, `same order, same membership`) and fail while any survives. Crude, but clause 3 is a prose clause and this is the only thing that can read prose.

Until at least (1) and (2) exist, **R2's predicate reading is not evidence about R2** and should not appear in an acceptance claim.

## 2. What the invariant protects, and whether the drift guard is a safety net

There are exactly **two** sites in the whole package that read a parallel array by index. DEMONSTRATED BY EXECUTION (grep over `toolguard/` for `.index(` — the other hits are all string slicing on `"("`):

- `config.py:1505` — `entries[candidates.index(pattern)]` in `Configuration.entry_for_pattern`, guarded by `if len(entries) != len(candidates): return None`.
- `resolve.py:294` — `deny_entries[deny_patterns.index(matched_pattern)]` in `_hard_deny_additional_context`, guarded by `if len(deny_entries) != len(deny_patterns) or ...`.

Both feed **only** `additionalContext`. Neither can change a verdict. That is stated in both docstrings and is consistent with everything below.

### The drift guard, measured under full corpus replay

I wrapped both sites with counting instrumentation and ran `corpus_build.py --verify` in-process (6,401 + 61 cases, "no differences"). **DEMONSTRATED BY EXECUTION:**

```
efp.calls                    3982      hd.calls                    14
efp.found                    3982      hd.found                    14
efp.DRIFT_GUARD_FIRED           0      hd.DRIFT_GUARD_FIRED         0
efp.DISAGREE                    0      hd.DISAGREE                  0
efp.not_found                   0      hd.not_found                 0
```

`DISAGREE` compares the index-derived entry against the entry a **direct search** over `_strip_tool_wrapper(entry.pattern) == pattern` returns. **In 3,996 real lookups the two never differed, and the drift guard never fired once.** The invariant buys nothing over a derived-property lookup on the live corpus.

### Would anything notice if the guards stopped?

I deleted both guards and ran the full suite. **DEMONSTRATED BY EXECUTION:** 2,368 ran, **2 failures**, both in `test_configuration.TestEntryForPatternDrift` — tests that synthesise a drifted `ToolPatternLayer` by hand for the sole purpose of firing the guard.

**The `resolve.py:294` length guard is pinned by ZERO tests.** Removing it produced no failure at all. That one is dead code with a comforting comment, in the literal sense: nothing in the suite and nothing in the corpus exercises it.

The `config.py:1503` guard is pinned by exactly the two synthetic tests that exist to pin it, and by nothing else. It is a real safety net only against a hazard the codebase creates for itself — and R2 deletes the hazard, which deletes the need for the net. Both tests become unconstructible after stage 2 (you cannot build a misaligned layer when there is only one array).

## 3. The replacement, argued

**`RuleEntry` can carry it, and the cost is zero.** `config_types.py` already does `from toolguard.rule_entry import RuleEntry, _strip_tool_wrapper` (config_types.py:40), and `rule_entry.py` imports nothing from `toolguard` except `issues`. So a `RuleEntry.stripped_pattern` property is available to `ToolPatternLayer` with no new import and no layering change. DEMONSTRATED BY EXECUTION — I built it and the suite ran.

**The pattern tuples are already a pure projection of the entries.** `_extract_tool_entries` (config.py:1295) literally computes `patterns = tuple(_strip_tool_wrapper(e.pattern) for e in scoped)` and returns both. `hard_deny` (config.py:1202-1206) does the same over `_pool_hard_deny_entries`. So R2 is not introducing a derivation — it is **deleting a materialised copy of one that already exists**. That is why it is cheap.

Recommended shape:

```python
class RuleEntry:
    @property
    def stripped_pattern(self) -> str: ...        # public; also retires the R6 finding
                                                  # tools.takeover_audit importing private
                                                  # _strip_tool_wrapper from config

class ToolPatternLayer:
    provenance: Provenance
    allow_entries / deny_entries / ask_entries: Tuple[RuleEntry, ...]
    allow / deny / ask -> derived properties over the entries
```

Keep `allow`/`deny`/`ask` as **read-only derived properties**, not deleted. Nine call sites in `config.py`, `tools/config_access.py` and the tooling read them and are genuinely pattern-shaped consumers; a property keeps them working and makes the "these are the same thing" claim executable instead of prose. The dataclass field disappears, so the drift **cannot be constructed** — which is the actual R2 goal, and is stronger than any guard.

### Three fields or one collection keyed by kind?

**Recommend one collection keyed by kind, but as a SECOND step, not folded into stage 2.** The evidence for it is real:

- `entry_for_pattern` and `provenance_for_pattern` each open with an identical 3-branch `if kind == "allow" / elif kind == "ask" / else` (config.py:1435-1440, 1484-1489), and `permission_resolution.py:214` sets `kind = decision` — the discriminator is already a runtime string. A `Mapping[str, Tuple[RuleEntry, ...]]` collapses both branches to `layer.entries[kind]`.
- The evidence against doing it in the same stage: variant 2 in the instrument table shows a dict-of-lists **carries the identical index hazard** if you keep a parallel dict of patterns. Doing the keying and the derivation together makes it impossible to tell by inspection which one bought the safety. Derive first (hazard gone), then key (duplication gone).

**Frozen dataclass over tuple, per the standing project preference:** `permission_levels_with_provenance` returns `Tuple[Tuple[allow, deny, ask, layers], ...]` and its single production consumer unpacks it positionally — `for index, (allow, deny, ask, layers) in enumerate(levels)` (permission_resolution.py:203). That is a 4-tuple, not a strict pair. Worse, **`allow`/`deny`/`ask` are fully derivable from `layers`** once the layer properties exist — config.py:1398-1416 builds them by concatenating exactly `layer.allow`/`.deny`/`.ask`. So this is a *fourth* materialised copy of the same information, and it is the last positional-coupling site on the resolution path. INFERRED BY READING the construction site; the derivability follows directly from the accumulate loop.

## 4. Blast radius, staged

All counts DEMONSTRATED BY EXECUTION, full suite, from a 2,368-test baseline. In every probe **all 2,368 tests still ran** — no module failed to import, so there is no hidden "never ran" population behind any of these numbers.

| stage | what it does | tests broken | mechanical vs behavioural |
|---|---|---:|---|
| **R2a** | `RuleEntry.stripped_pattern` property (pure addition) | **0** | n/a — additive |
| **R2b** | `ToolPatternLayer.allow/deny/ask` become derived properties; entries are the only storage; `permission_layers` takeover filter filters entries directly | **3** | **3 mechanical, 0 behavioural.** All three are `test_configuration.TestEntryForPatternDrift`, a 96-line class that exists only to construct a misaligned layer. Two become unconstructible and should be **deleted with the hazard**; the third (`test_aligned_layer_still_resolves_normally`) is a two-line constructor edit. |
| **R2c** | `resolve._hard_deny_additional_context` searches entries directly; delete its index lookup, its length guard, and the prose invariant on `hard_deny`/`hard_deny_entries` | **0** | zero cost, zero risk. Measured directly, suite 2,368 **OK**. |
| **R2d** | move `provenance_for_pattern` / `entry_for_pattern` off `Configuration` to sit beside `ToolPatternLayer` | **9** | **9 mechanical, 0 behavioural** — 2 `test_configuration`, 6 `test_hook`, 1 `test_logging_streams`. |
| **R2e** *(optional)* | `permission_levels_with_provenance` returns a frozen dataclass; drop the derivable `allow/deny/ask` members | not measured | 1 production consumer (permission_resolution.py:202); 9 references total incl. tests and docstrings |
| **R2f** *(optional)* | three kind fields -> one mapping keyed by kind | not measured | collapses two 3-branch dispatches |

**Recommended split: R2a + R2b + R2c as ONE stage, R2d as a second stage, R2e/R2f deferred to R6.**

Reasons. R2a is additive and meaningless alone. R2b is the whole point and costs 3 tests. R2c costs nothing and is the *other half of the same defect* — leaving it would let R2 report PASS with an identical hazard alive twelve lines away in `resolve.py`, which is exactly the R5d shape (a thing that "was never an R5 violation at all" but was the same defect). Total for the combined stage: **3 tests, all mechanical, two of which are deletions.**

R2d is separate because it is a *relocation*, not a representation change: it does not touch the arrays and its 9 breaks are all name-coupling. Keeping it separate keeps the R2b measurement clean. It is still clearly in scope — the D1a judge's finding **re-verified here by execution**: `Configuration.entry_for_pattern.__func__` raises `AttributeError: 'function' object has no attribute '__func__'`, i.e. it is a plain function reached through the class, holding no configuration state. There is a second, better argument for moving them that the judge did not have: **6 of R2d's 9 breaks are in `test_hook.py`, where a fake config object stubs `provenance_for_pattern`/`entry_for_pattern` purely because production reaches two stateless functions through a `config` instance** (test_hook.py:168-176). Moving them beside `ToolPatternLayer` deletes the reason those doubles exist.

**Note on the estimate discipline that has twice been wrong in the safe direction on this ticket.** I deliberately did NOT report the rename-proxy number for the `hard_deny` family: renaming `hard_deny` across `toolguard/` breaks **106 tests** (70 `test_resolve`, 19 `test_hard_deny`, 16 `test_hook`, 1 `test_configuration`) — and that number is **misleading**, because R2c does not rename anything. The real R2c change keeps the public name and breaks **zero**. 106 vs 0 is the sharpest illustration on this ticket yet that a rename-and-count proxy measures *name coupling*, not the cost of the work. Use it to find call sites; do not quote it as a blast radius unless the work actually renames.

## 5. Gaming moves, per stage, and the detector that would see each

| stage | cheapest way to satisfy the predicate without improving anything | detector that exposes it |
|---|---|---|
| R2a | add the property, use it nowhere | check that `_extract_tool_entries`/`permission_layers` no longer call `_strip_tool_wrapper` directly; count call sites of the private helper (should drop) |
| **R2b** | **rename `*_entries` to `*_rules`. Zero behaviour change, R2 goes PASS.** Demonstrated as variant 1 — and it needs no Python beyond a `sed`, the R5 "3-line config edit" move again | use-site check (2) above: any `A[B.index(x)]` / `zip(A,B)` over two stored sequences. Plus the rename-invariance regression test (3) |
| R2b (subtler) | keep both arrays, make one a `@property` over the other and leave the index lookup in place. Variant 3: detector blind, hazard technically gone but the invariant prose survives and the next editor re-materialises it | the prose check (4), plus assert `ToolPatternLayer.__dataclass_fields__` contains no stripped-pattern field |
| R2c | fix `config.py` only and leave `resolve.py:294`. **Today's predicate cannot see `resolve.py:294` at all, so this games R2 completely and silently** | the use-site check; it is class-agnostic, which is the whole reason to prefer it |
| R2d | move the functions to a new module that just re-exports from `config` | the anti-pass-through rule already in the plan's section 4; plus assert `config.py` no longer defines them |
| R2e/R2f | replace the 4-tuple with a `NamedTuple` (still positionally unpackable, still a tuple) | assert the returned type is a `@dataclass(frozen=True)` and is NOT iterable — the same shape R1a used to kill the `__iter__` shims |

## 6. Predicted acceptance numbers, and which to trust

Everything in this table was measured **with the R2b probe actually in place**, not predicted.

| number | prediction | trust |
|---|---|---|
| R2 predicate | **PASS** (measured) | **DO NOT USE AS EVIDENCE.** Section 1: it reads PASS for seven gaming moves too. Quote it as "scoped", never as "verified" |
| corpus `--verify` | **6,401 + 61, no differences** (measured under R2b) | **TRUSTWORTHY.** This is the real acceptance test: it compares verdict, reason, provenance and additionalContext end-to-end, and additionalContext is the only thing the index lookup feeds |
| `--guard` | **PASS, 12 canaries** (measured under R2b) | trustworthy but insensitive — 12 canaries against the live hook |
| suite | 2,368 -> **~2,366** (3 break; expect 2 deletions and 1 rewrite) | the count is bookkeeping, not evidence. What matters is *which* 3 |
| enrichment footprint | **72, unchanged** (measured under R2b) | **DO NOT LEAN ON IT.** Established unreliable across tuple->dataclass conversions, and confirmed again here: it did not move one identifier for a change that deletes three parallel arrays. It counts identifiers; deleting a field removes none |
| `config.py` LOC | 2,598 -> ~2,510 with R2d (the two staticmethods span config.py:1418-1506, 88 lines, docstring-heavy) | measured span; a size claim, not a quality claim |
| index-parallel access sites | **2 -> 0** | **This is the number to report.** It is the thing R2 exists to change, it is countable, and it is not gameable by renaming |
| prose index-invariant sites | **4 -> 0** (`config_types.py:161-165`, `config.py:1221-1224`, `config.py:1461-1470`, `resolve.py:268-272`) | matches clause 3 of the stated predicate; count them explicitly since no tool does |
| drift guards | **2 -> 0**, one of which was pinned by nothing | measured |

**The defensible R2 claim, if the work goes as measured, is: two index-parallel access sites to zero, four prose-defended invariant statements to zero, two drift guards deleted (one of them provably unexercised in 6,462 corpus cases and unpinned by any test), the misaligned state made unconstructible rather than guarded — with the corpus showing no verdict, reason, provenance or context differences.** None of that routes through the R2 predicate or the footprint metric.

## Restoration

Every probe file was byte-restored from `/tmp/.../scratchpad/r2-backups/` and verified with `sha256sum -c`. Final state, all re-verified after restoration:

- `sha256sum -c ORIGINAL.sha256` -> **OK** for `config.py`, `resolve.py`, `config_types.py`, `permissions.py`, `rule_entry.py`, `permission_resolution.py`, `hook.py`.
- `toolguard/tools/decision.py` and `toolguard/permission_resolution.py` were touched by a `sed` rename with no byte backup taken beforehand — **my mistake, caught immediately.** Both were restored by applying the exact inverse `sed` (the probe names `hard_deny_PROBE`, `prov_for_pat_MOVED`, `ent_for_pat_MOVED` were unique, so the rename was bijective); `permission_resolution.py` then verified OK against a sha taken after the reversal, and a repo-wide grep confirms **zero** probe markers survive. **Take the byte backup before the `sed`, not after.**
- `git status --porcelain`: **100 entries, the same modified set the session started with.** `toolguard/rule_entry.py` shows no diff (it was unmodified at start and is unmodified now).
- suite **2,368 OK**; corpus **no differences**; `--guard` 12 canaries; `ruff check --no-cache` **All checks passed**; R2 predicate back to **FAIL** with the same three pairs.

No git write of any kind was run.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- follows [[TOO-45 R5 scoping trace]]
- follows [[TOO-45 R1 scoping trace]]
- relates_to [[TOO-45 decision log]]
