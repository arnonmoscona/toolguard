---
title: TOO-45 change-role classifier - third adversarial report
type: note
permalink: toolguard/too-45/reports/classifier-adversarial-report-3
tags:
- task-memory
- TOO-45
- report
- adversarial
---

# TOO-45 change-role classifier — third adversarial report

Target: `tools/change_role_classifier.py`, closure rule v3 (`CLOSURE_RULE_RETURNS_TRACKED`, "a tracked symbol referenced anywhere within a return/yield value expression"). Read-only: no project file was modified, and `/tmp/toolguard-master-copy` / `/tmp/toolguard-branch-copy` were read in place and never written. All scratch fixtures have been deleted.

**Verdict up front: v3 substantially holds, and the two defects that killed v1 and v2 are genuinely gone — I could not reproduce either.** What remains is a third, smaller gate, on a different axis: a function joins the closure only if the tracked symbol appears in the *same expression* that is returned. Route the value through an intermediate binding first and the function does not join, and its call sites vanish. That gate costs 11 of 24 semantically identical implementations all four of their enforcement sites, and 5 of those 11 lose them with **every honesty bucket reading zero**. It is a real limitation and it is not fully disclosed, but unlike v1 and v2 it does not scale with factoring granularity, which is what the bias question was actually about. My recommendation is that the tool can be used, with the KNOWN LIMITATIONS text corrected on two specific false or over-broad claims listed at the end.

## Q1 — bias direction and style dependence

### Method

24 trees, each three files (`pkg/entry.py`, `pkg/policy.py`, `pkg/handlers.py`), each implementing the **identical** requirement: a rule entry carries `flag_x`; four enforcement sites honour it under auto mode. Only the factoring/expression style varies. `sites/4` counts occurrences the tool attributes inside `pkg/handlers.py` — i.e. how many of the four enforcement sites the report actually shows a human. Subject `flag_x`, default `--closure-hops 2` unless noted.

### Results, `--closure-hops 2`

| style | sites/4 | total prod occ | opaque hops | closure added | excluded-by-hop | primary roles |
|---|---|---|---|---|---|---|
| 01 inline | **4/4** | 5 | 0 | — | — | DECISION 4, WRITE 1 |
| 02 inline, branched | **4/4** | 5 | 0 | — | — | DECISION 4, WRITE 1 |
| 03 named predicate, `return A and entry.flag_x` | **4/4** | 7 | 0 | `auto_permits` | — | DECISION 5, WRITE 2 |
| 04 named predicate, early returns | **4/4** | 7 | 0 | `auto_permits` | — | CONDUIT 1, DECISION 4, WRITE 2 |
| 05 chain of two delegating functions | **4/4** | 9 | 0 | `_raw`, `auto_permits` | — | CONDUIT 1, DECISION 5, WRITE 3 |
| 06 chain of three delegating functions | 0/4 | 6 | 1 | `_raw`, `_mid` | **`auto_permits`** | CONDUIT 2, DECISION 1, WRITE 3 |
| 07 `@property` returning an expression | **4/4** | 7 | 0 | `is_flagged` | — | DECISION 5, WRITE 2 |
| 08 `@functools.cached_property` | **4/4** | 7 | 0 | `is_flagged` | — | DECISION 5, WRITE 2 |
| 09 method returning a dataclass field | **4/4** | 7 | 0 | `get_flag` | — | CONDUIT 1, DECISION 4, WRITE 2 |
| 10 generator that *filters* on the flag | 0/4 | 2 | **0** | — | — | DECISION 1, WRITE 1 |
| 11 generator that *yields* the flag | **4/4** | 7 | 1 | `flag_values` | — | CONDUIT 1, DECISION 4, WRITE 2 |
| 12 conditional return (`x if c else False`) | **4/4** | 7 | 0 | `auto_permits` | — | CONDUIT 1, DECISION 4, WRITE 2 |
| 13 intermediate local (`v = entry.flag_x; return v is True and ...`) | 0/4 | 2 | 1 | — | — | CONDUIT 1, WRITE 1 |
| 14 intermediate local via constant key + `.get()` | 0/4 | 3 | 1 | `FLAG_KEY` | — | CONDUIT 1, WRITE 2 |
| 15 intermediate local, branched not returned | 0/4 | 2 | 1 | — | — | CONDUIT 1, WRITE 1 |
| 16 intermediate local that shadows the subject spelling | 0/4 | 4 | 2 | — | — | CONDUIT 1, DECISION 1, WRITE 2 |
| 17 cached on `self` in `__init__`, property returns cache | 0/4 | 2 | **0** | — | — | WRITE 2 |
| 18 local bound by tuple unpacking | 0/4 | 2 | **0** | — | — | CONDUIT 1, WRITE 1 |
| 19 local bound by a walrus | 0/4 | 2 | **0** | — | — | DECISION 1, WRITE 1 |
| 20 local forwarded into a helper | 0/4 | 2 | 1 | — | — | CONDUIT 1, WRITE 1 |
| 21 module-level dict cache (`_CACHE["v"] = entry.flag_x`) | 0/4 | 2 | **0** | — | — | WRITE 2 |
| 22 local consumed by a nested closure | 0/4 | 2 | 1 | — | — | CONDUIT 1, WRITE 1 |
| 23 local assigned inside a loop | 0/4 | 2 | 1 | — | — | CONDUIT 1, WRITE 1 |
| 24 returns the flag inside a container it immediately indexes | **4/4** | 7 | 0 | `auto_permits` | — | CONDUIT 1, DECISION 4, WRITE 2 |

**11 of 24 recover all four sites; 13 recover none.** At `--closure-hops 4` style 06 recovers (4/4, 11 occurrences, closure `_raw`/`_mid`/`auto_permits`); nothing else changes, confirming that everything except 06 is a *shape* gate rather than a *depth* gate.

### What is genuinely fixed

**v2's punctuation gate is gone.** 03 vs 04 was v2's decisive counter-example — `return A and B and entry.subject and C` rejected while the byte-equivalent early-return form was accepted, moving a real tree 5 → 11. Under v3 the two are **identical on every axis that matters**: 4/4 sites, 7 occurrences, same closure member. `bool(...)`, `or default`, a conditional expression, a `.get()` call, a container subscript, `@property`, `@cached_property`, a `@staticmethod`-style plain method, and a value-yielding generator all now join. Of the 13 accessor shapes v2 rejected, I could not find one that v3 still rejects for punctuation reasons.

**v1's over-inclusion has not returned.** Across all 24 trees the closure never exceeded 3 names, and every member is a genuine carrier of the value (`auto_permits`, `is_flagged`, `_raw`, `FLAG_KEY`). No `main`-style consumer was pulled in. The "returns an unrelated value while merely consulting the symbol" exclusion still does its job — style 10 (the generator that reads the flag and yields the *entry*) is correctly not admitted as a carrier.

**Well-factored code is no longer penalised for being factored.** Every factored style that passes the gate recovers *more* than the inline baseline, not less: inline 5 occurrences, named predicate 7, two-level delegation 9, three-level delegation 11 at hop 4. Closure size no longer scales adversely with granularity — it scales *with* it, in the intended direction.

### The residual gate, and how big it is

The one thing that decides pass/fail in v3 is: **does the tracked symbol appear inside the returned expression itself, or does it pass through a binding on the way?** Every one of the 13 failures is an instance of the second.

The stylistic lever that survives is therefore 03 vs 13 — the same named predicate, one written as a single expression and one with a temp variable:

```python
# style 03 -- 7 occurrences, 4/4 sites, 0 opaque hops
def auto_permits(entry, mode):
    return mode == "auto" and entry.flag_x

# style 13 -- 2 occurrences, 0/4 sites, 1 opaque hop
def auto_permits(entry, mode):
    value = entry.flag_x
    return value is True and mode == "auto"
```

That is a swing of **-5 occurrences and -4 enforcement sites for one line of purely stylistic rewriting**, comparable in magnitude to v2's 11 → 5. The difference from v2 is twofold, and both differences matter:

1. **It is signalled, in 8 of the 13 failures.** Styles 13, 14, 15, 16, 20, 22, 23 raise opaque hops; style 06 is named in `excluded_by_hop_limit`. A reader who checks the honesty buckets sees *something*.
2. **The signal is under-sized.** One lost hop produces exactly one opaque-hop entry no matter how many call sites disappear behind it. Style 13 loses four enforcement sites and reports `opaque_hops.production = 1`. The magnitude of the loss is not recoverable from the signal.

**Five failures are completely silent** — `opaque_hops = 0`, `excluded_by_hop_limit = []`, `unclassified = 0`, `parse_failures = 0`:

- **10** generator filter. Arguably by design (the generator yields entries, not the flag), and the DECISION inside it *is* found — but the four consumer sites are not, with no signal.
- **17** value cached on `self` in `__init__`, returned bare by a property. Explicitly named in KNOWN LIMITATIONS as not covered by the closure — but the docs imply opaque hops are the fallback, and here there are none. Total DECISION count across the whole tree: **0**.
- **18** tuple-unpack binding, **19** walrus binding, **21** subscript/attribute cache target.

### The opaque-hop coverage claim — verified, and it is over-stated

The module docstring says closure cannot follow a value through a function-local variable and that the tool "COUNTS these crossings" instead. Tested on nine intermediate-binding shapes:

| binding form | opaque hop raised? |
|---|---|
| `value = entry.flag_x` (plain `Name` target) | yes (13, 15, 16, 20, 22, 23) |
| `value = entry.metadata.get(KEY)` | yes (14) |
| `value = ...` inside a loop | yes (23) |
| `value = ...` consumed by a nested closure | yes (22) |
| `value, extra = entry.flag_x, 1` (tuple target) | **no** (18) |
| `if (value := entry.flag_x) is None:` (walrus) | **no** (19) |
| `self._cache = entry.flag_x` (attribute target) | **no** (17) |
| `_CACHE["v"] = entry.flag_x` (subscript target) | **no** (21) |
| property caching in `__init__`, read later | **no** (17) |

The cause is mechanical and visible in `_find_opaque_hops_in_scope`: it only inspects `Assign`/`AnnAssign`/`AugAssign` whose target is a single plain `ast.Name`. Every other binding form is neither followed nor counted. This is the same class of defect as N2 in the second review — KNOWN LIMITATIONS asserting a coverage the counter does not have — recurring on four new binding forms. It is the one thing in this report I would call a documentation defect rather than a design trade-off, because the text tells a reader the loss is measured when for these shapes it is not.

### Q1 verdict

**v3 has a bias direction, and it is much weaker and differently-shaped than v1's or v2's.** It does not favour coarse-grained code as a function of factoring granularity — factored styles recover strictly more than the inline baseline, and delegation depth is only limited by an explicitly-reported hop limit. What it favours is code that reads and returns the value **in one expression**, over code that binds it to a name first. That is largely orthogonal to architectural quality, which is the improvement, but it is not entirely orthogonal: a defensive accessor that validates a raw value before returning it — `value = self.metadata.get(KEY); return value is True`, which is *exactly* the shape `RuleEntry.allow_in_auto_mode` uses on both TOO-45 validation trees — is precisely the shape that fails. Careful accessors are more likely to bind than careless ones. So the residual bias runs mildly against the more careful code, at a cost of up to 4/4 enforcement sites and −71% occurrences per affected accessor, signalled at magnitude 1 in 8 of 13 cases and not at all in 5.

Worth naming explicitly: **on the real trees this gate is masked by a coincidence.** `allow_in_auto_mode` is both the subject spelling and the property's own name, so its call sites are found through the seed name directly and never depend on closure growth. Point this tool at a subject whose constant, accessor and call sites do *not* share a spelling, and the intermediate-binding gate becomes load-bearing.

## Q2 — is the "symmetric expansion" argument sound?

**No. The inference is invalid, and I can demonstrate it on the actual validation trees.**

The argument is: the closure fix expanded recovered evidence 9 → 11 on both `/tmp/toolguard-master-copy` and `/tmp/toolguard-branch-copy`, and the two still report identical structure, so the agreement is credible rather than silent loss.

The formal objection is that the closure rule is a **pure function of each tree's source text**. Any blind spot it has in a region of code that the two trees *share* is symmetric by construction — symmetry there is a theorem about the input, not evidence about the rule. Two trees that implement the same feature from a common ancestor share almost all of the relevant code, so symmetry is the expected observation whether or not the rule is under-including.

That is not a hypothetical here. I checked what actually expanded. The 9 → 11 expansion added `_allow_in_auto_mode_issues` to the closure. That function lives in `toolguard/rule_entry.py`, which is present in **both** trees, and its body is character-for-character identical between them (verified by diff, ignoring comments and docstrings; the surrounding `allow_in_auto_mode` property region differs only in comment and docstring wording). **The symmetric expansion is the same source function being analysed twice.** It could not have come out asymmetric.

Both trees also report `opaque_hops.production = 5` — identical, because the five opaque hops are in shared code too. That number is the tool's own statement that there are five places a DECISION could be hiding, and it applies equally to both trees. Reading the equal reports as "the trees agree" while equal opaque-hop counts say "there are five places neither report can see" is reading the agreement past what it covers.

### Concrete counter-case, synthetic

Two trees, identical accessor (style 13's intermediate-local predicate), differing only in **1 vs 4 enforcement sites**:

| tree | enforcement sites in source | prod occurrences | roles | closure | opaque | excluded |
|---|---|---|---|---|---|---|
| A | 1 | 2 | CONDUIT 1, WRITE 1 | `flag_x` | 1 | — |
| B | **4** | 2 | CONDUIT 1, WRITE 1 | `flag_x` | 1 | — |

Identical reports, identical "expansion" behaviour, hiding a 4× difference in enforcement surface.

### Concrete counter-case, on the real tree

I copied `/tmp/toolguard-master-copy/toolguard` into scratch and changed the `allow_in_auto_mode` property body from `return value is True` to `return value is True and not self.pattern.startswith("Bash(rm")` — a genuine behavioural difference in the subject's own semantics (the auto-mode override no longer applies to `rm` rules). The original tree was read in place and not modified.

| tree | prod occurrences | roles | closure | opaque | excluded | string mentions |
|---|---|---|---|---|---|---|
| original | 11 | CONDUIT 6, DECISION 2, WRITE 3 | `ALLOW_IN_AUTO_MODE_KEY`, `_allow_in_auto_mode_issues`, `allow_in_auto_mode` | 5 | — | 1 |
| changed | **11** | **CONDUIT 6, DECISION 2, WRITE 3** | **identical** | **5** | — | 1 |

**Byte-identical reports across a real semantic change to the subject, located inside an opaque hop the tool already admits it cannot see.** So: two related trees can differ in what `allow_in_auto_mode` actually means and report identically, and their opaque-hop counts stay symmetric while doing it.

### Q2 verdict

Symmetric expansion across two closely-related trees is consistent with correctness but does not distinguish it from symmetric silent loss, because similar trees share the code containing the blind spot. The observed 9 → 11 on both trees is, specifically, the same identical function being counted twice. What the tool *does* legitimately support is the structural fact it was actually used for — the same value routed through the same two-function chain at two different module addresses — because that is read off the closure listing directly rather than inferred from an agreement.

## Q3 — the suite

**Refuted as stated, in the better direction.** `uv run python -m unittest discover -s test -t .` at the current working tree: **`Ran 2586 tests` … `OK`, exit code 0.** No failures, no errors. The reported 2565/2566 is stale — both the count and the single failure. Consistent with a concurrent agent having landed work on `tools/touch_set_*.py` / `test/unit/test_touch_set_*.py` between that run and this one (the count grew by 20). Nothing in the suite touches `tools/change_role_classifier.py` adversely, and its own tests pass.

## What I would change, in prose (no code was modified)

1. **Correct the opaque-hop coverage claim.** Both the module docstring and the `OpaqueHop`/KNOWN LIMITATIONS text should say the counter covers *simple single-`Name`-target assignments only*, and explicitly name the four binding forms it does not see: tuple/list unpacking, walrus (`NamedExpr`), attribute targets (`self._x = ...`), and subscript targets (`cache["k"] = ...`). This is the second review's N2 recurring on new forms; the honest fix is one sentence.
2. **Extend `_find_opaque_hops_in_scope` to those four forms** if any code is to be changed at all. It is a small, contained change to the target-shape test and it converts the five silent failures (10, 17, 18, 19, 21) down to one. That is the highest-value repair available and it does not touch the closure rule.
3. **Do not widen the closure rule again.** v3's exclusion of "reads the symbol on the way to an unrelated return" is the only thing standing between it and v1's 19-name explosion, and every widening so far has traded one bias for another. Under-inclusion with a correct signal is the acceptable outcome; the problem is the signal, not the rule.
4. **Note the magnitude gap.** One opaque hop can conceal an unbounded number of call sites. If a per-hop "call sites of the enclosing function" count is cheap, printing it next to each opaque hop would let a reader size the loss instead of guessing.
5. **Add a caveat to the two-tree comparison protocol**: equal reports on two related trees are evidence only over the region the tool can see, and the opaque-hop count is the size of the region it cannot. A tie with 5 opaque hops per side is not the same claim as a tie with 0.
