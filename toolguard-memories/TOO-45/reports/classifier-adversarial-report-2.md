---
title: TOO-45 change-role classifier - second adversarial report
type: note
permalink: toolguard/too-45/reports/classifier-adversarial-report-2
tags:
- task-memory
- TOO-45
- report
- adversarial
---

# TOO-45 change-role classifier — second adversarial report

Target: `tools/change_role_classifier.py` (read-only; not modified, not its test file). Second pass, after the six structural fixes that followed the first adversarial review. Scratch fixtures lived under the session scratchpad and have been removed.

**Verdict up front: the six fixes hold, and the hypothesis you asked me to test is CONFIRMED. The bias did not disappear; it changed mechanism and, in the case that matters most, it now runs against well-factored code more sharply and more silently than the old rule ran against it in the other direction.** The closure is no longer gated on how finely the tree is factored — it is gated on the *internal expression style of one function body*, which is worse, because that is not a property anyone would think to control for when comparing two trees.

## Part 2 — what the fix introduced (lead finding)

### The decisive experiment, synthetic

The same requirement — "a rule entry may carry `allow_in_auto_mode`; honour it at four enforcement sites" — written four ways. All four are semantically identical. "Enforcement sites found" counts how many of the four handler call sites the tool attributes to the subject at all.

| tree | what it is | occurrences | DECISION | enforcement sites found |
|---|---|---|---|---|
| **U** | unfactored: `if mode == "auto" and entry.allow_in_auto_mode:` copy-pasted at all 4 sites | 5 | **4** | **4 / 4** |
| **F** | well-factored: constant key + `@property` (`value = self.metadata.get(KEY); return value is True`) + named predicate `def auto_mode_permits(entry, mode): return mode == "auto" and entry.allow_in_auto_mode`, called from all 4 sites | 5 | **1** | **0 / 4** |
| **F2** | same factoring, property is `return self._allow_in_auto_mode` | 3 | 1 | **0 / 4** |
| **F3** | **byte-for-byte identical to F except the predicate body is written `if mode != "auto": return False` / `return entry.allow_in_auto_mode`** | 11 | **4** | **5 / 5** |

F vs U is the finding: the factored tree loses all four enforcement sites, and reports one DECISION where the unfactored tree reports four. F vs F3 is the finding that makes it dangerous: **a three-line stylistic rewrite of one predicate body, with no architectural change whatsoever, moves the report from 5 occurrences / 1 DECISION / 0 sites to 11 occurrences / 4 DECISION / 5 sites.** `return A and B` is invisible to `CLOSURE_RULE_RETURNS_TRACKED`; `if not A: return False` / `return B` satisfies it.

None of this is signalled. In tree F: `parse_failures` 0, `unclassified_occurrences` 0, `excluded_by_hop_limit` **empty**, `removed_files` 0. In tree F2 the opaque-hop count is 0 as well — **four enforcement sites lost with every honesty bucket reading zero**. And `--closure-hops 6` changes nothing (tracked set stays at 2 names): this is a *shape* gate, not a *depth* gate, so the excluded-by-hop-limit probe — the tool's designated mechanism for "a chain that was cut off is named, never silently absent" — is structurally incapable of ever reporting it.

### The same experiment on the real validation tree

`/tmp/toolguard-master-copy` (154 files, subject `allow_in_auto_mode`), refactored two ways in scratch copies. Both variants extract the auto-mode override from `config.py` into a named predicate in a new `permission_policy.py` module — the *identical* refactoring, the kind TOO-45 is trying to reward. The only difference between the two variants is the predicate's body style, shown in full below.

| variant | production occurrences | closure members | what the tool sees |
|---|---|---|---|
| baseline, unrefactored | 9 — `CONDUIT 5, DECISION 2, WRITE 2` | 2 | — |
| extracted predicate, `return A and B and flag and C` | **9 — `CONDUIT 5, DECISION 2, WRITE 2`** | 2 | **the refactor is completely invisible; identical to baseline** |
| extracted predicate, early-return ending `return winning_entry.allow_in_auto_mode` | **11 — `CONDUIT 6, DECISION 2, WRITE 3`** | 3 (`_auto_mode_override_applies` joins) | new module and call site both credited |

```python
# variant A -- predicate INVISIBLE to the tool
def _auto_mode_override_applies(decision, winning_entry, permission_mode) -> bool:
    return (
        decision != "allow"
        and winning_entry is not None
        and winning_entry.allow_in_auto_mode
        and is_auto_mode(permission_mode)
    )

# variant B -- same function, same semantics, +2 production occurrences and +1 closure member
def _auto_mode_override_applies(decision, winning_entry, permission_mode) -> bool:
    if decision == "allow" or winning_entry is None:
        return False
    if not is_auto_mode(permission_mode):
        return False
    return winning_entry.allow_in_auto_mode
```

So on the actual tree this instrument will be pointed at: a real architectural change (policy pulled out of `config.py` into its own module behind a named predicate) can produce a report *numerically identical to not having done it*, and the difference between "invisible" and "+22% production occurrences" is which of two idiomatic ways the author wrote a four-clause boolean.

### Which accessor shapes survive the gate

19 accessor shapes, each with call sites, one tree, subject `flag_x`. Six join the closure; thirteen do not. Every shape you listed in the brief is in the rejected column.

| joins the closure (6) | does NOT join (13) |
|---|---|
| `return flag_x` | `return bool(flag_x)` |
| `return (flag_x)` | `return flag_x or False` |
| `@property → return self.flag_x` | `return flag_x is True` |
| `@functools.cached_property → return self.flag_x` | `return flag_x if flag_x is not None else False` |
| `@staticmethod → return flag_x` | `return (flag_x, 1)` |
| `@classmethod → return flag_x` | `return {"v": flag_x}` |
| | `return cast(bool, flag_x)` |
| | `return flag_x.strip()` |
| | `v = flag_x; return v` |
| | `v = meta.get(flag_x); return v` |
| | `return acc_bare()` (delegating wrapper) |
| | `@property → return self._flag_x` (private backing attribute) |
| | `return self.metadata.get(flag_x)` |

`cached_property`, `staticmethod` and `classmethod` are fine — decorators are not the problem. The private-backing-attribute property (`return self._flag_x`) is the most common real accessor in Python and it is rejected, because the returned attribute name is `_flag_x` and only `flag_x` is tracked. Note the asymmetry that produces: `return self.flag_x` is admitted, `return self._flag_x` is not, so whether a class uses a private backing field decides whether its entire call-site population is counted.

### The documented mitigation for this does not exist

`KNOWN_LIMITATIONS` entry 12 says, of `return self.metadata.get(THE_KEY)`: *"an accessor that reaches the value through one extra step … is NOT tracked as an accessor even though a human would call it one — **see the OPAQUE HOP count for exactly this shape**, measured separately rather than folded into closure growth."*

Measured directly, one file, two methods:

```python
class A:
    def one_liner(self):
        return self.metadata.get(THE_KEY)      # -> 0 opaque hops

    def two_liner(self):
        value = self.metadata.get(THE_KEY)
        return value is True                    # -> 1 opaque hop
```

Result: **1 opaque hop total, and it is the two-liner.** `_find_opaque_hops_in_scope` only ever inspects `Assign`/`AnnAssign`/`AugAssign` statements; a `Return` whose value is an expression containing a tracked symbol is not an opaque hop and is not anything else either. So the sentence in the tool's own limitations list points at a measurement that never fires for the shape it names. This is the load-bearing honesty claim for the Part 2 gap, and it is false as written.

### Suggested fixes (prose only)

Three options, in increasing cost. (1) Cheapest and probably right: keep `CLOSURE_RULE_RETURNS_TRACKED` for growth, but add a separate, non-growing **"consults-tracked-and-returns"** report — every function whose return expression syntactically contains a tracked symbol but does not bare-return it — listed by name and location, next to the opaque hops, framed as "these functions may be accessors this closure did not follow; their call sites are NOT counted." That restores the honesty bucket without reintroducing F3's inflation, and it would have made both F and variant-A visible. (2) Widen the rule to "every `return` in the function has the tracked symbol in its value expression AND the function's return annotation/name suggests an accessor" — cheap but guessy. (3) Broaden the rule to any `return <expr containing tracked>` where the function's *only* statement is that return — catches `return bool(x)`, `return self._x.strip()`, `return x or default`, `return self.metadata.get(KEY)`, and the ternary, without admitting multi-statement consumers; this is the one I would try first if growth must widen. In all cases, **make `_find_opaque_hops_in_scope` also walk `Return.value`**, or correct entry 12's text.

## Part 1 — do the six fixes hold

| # | fix | verdict |
|---|---|---|
| 1 | decisions through a call/attribute no longer pure CONDUIT | **HOLDS, with one gap** |
| 2 | closure inflation via `reads-tracked` | **HOLDS** |
| 3 | diff-mode statement-span line filtering | **HOLDS, over-corrected** |
| 4 | git `-M` rename detection | **HOLDS (verified by reading + the project's own tests, not independently)** |
| 5 | test/production boundary | **HOLDS, with a new over-trigger** |
| 6 | filesystem / encoding crashes | **HOLDS** |

**1 — HOLDS.** All seven previously-broken shapes now carry dual `DECISION`+`CONDUIT`: `if bool(subject):`, `if len(subject) > 0:`, `if subject.enabled:`, `if subject.is_ready():`, `if isinstance(subject, str):`, `if items.get(subject):`, `if (found := subject) is not None:`, plus `while subject.ready:`. `if data[subject]:` remains CONDUIT (documented). The gap is new — see N5.

**2 — HOLDS.** Subject `command` on the real `toolguard/` package: closure is now the seed alone, 82 occurrences, all 82 genuinely `command`. The previous run reported 142 with 58% precision. The narrow rule correctly rejects the consumer/validator/resolver shapes (`def consumer(meta): if meta.get(SUBJ_KEY): …`, `def validator(meta): v = reader(meta); return bool(v)`, `def main(meta): return consumer(meta)`).

**3 — HOLDS.** Both of the previous report's silent-loss cases now report. Subject moved from a call argument into a multi-line branch test: found, `DECISION`. A `DECISION`'s comparand edited on a different physical line of the same statement: found, `DECISION`.

**4 — verified indirectly.** `git init` is denied by a permission rule on this machine, so I could not construct an independent throwaway repo. I read `_git_diff_entries`/`run_git_diff` and the two regression tests (`TestGitRenameDetection`), which are genuine end-to-end tests over a real temp repo asserting zero occurrences for a byte-identical `git mv` and a preserved decision for rename-plus-edit. The code path is correct: `--name-status -M`, three-field `R` lines parsed to `old_path`/`new_path`, pre-image fetched from `old_path`. I did not independently confirm behaviour when git declines to detect a rename (a move plus >50% rewrite is reported `A`+`D`, so the new path gets `allowed_lines=None` and the whole file counts) — that residue is inherent to `-M`, not a defect in the fix, but it means the F5 inflation still applies to heavily-rewritten moves.

**5 — HOLDS.** `spec/spec_thing.py` → TEST, `src/conftest.py` → TEST, `--tree` pointed at `tests/` forces test context, full file lists printed. `pkg/test_helpers.py` still TEST (documented as undecidable by filename). New over-trigger: N7.

**6 — HOLDS.** Broken symlink, `chmod 000`, directory named `weird.py` all land in `parse_failures` with the exception type named; exit 0; the run completes. Latin-1 with a PEP 263 cookie now parses and classifies correctly (`WRITE` + `DECISION`), as does a UTF-8 BOM file.

## New defects, ranked

**N1 — CRITICAL, silent. Closure growth is gated on one function body's expression style.** Part 2 above. Direction: under-counts factored code; the repair moved the bias, it did not remove it. Occurrence finding — one of the two outputs the tool now stands behind — is exact *for the tracked name set it chose*, and the choice of that set is the unstable part. Not visible in any honesty bucket, and structurally invisible to `excluded_by_hop_limit`.

**N2 — HIGH, silent, and a false statement in the tool's own limitations list.** `return <expr containing tracked>` produces no opaque hop. `KNOWN_LIMITATIONS[11]` explicitly directs the reader to the opaque-hop count for exactly the `return self.metadata.get(THE_KEY)` shape. It never fires there. Fix: walk `Return.value` in `_find_opaque_hops_in_scope`, or correct the text.

**N3 — HIGH. The F5 whole-file-on-move inflation was fixed only in `--repo` mode; `--old/--new` still has it in full.** Measured: `pkg/a.py` → `pkg2/a.py`, byte-identical content, two-tree mode reports **4 occurrences including a phantom `DECISION` and a phantom `WRITE`**, and names `pkg/a.py` in `removed_files`. `run_two_tree_diff` has no rename/move detection at all — a file whose relative path changed is "newly added", so `allowed_lines=None` and every line counts. For an architecture-overhaul comparison, where moving files *is* the change, this inflates by exactly the amount of code that moved, and it inflates only the tree that did the moving. The `removed_files` list is the only trace, and it does not say the counts were affected. Fix: match old/new files by content hash (or by basename plus a difflib similarity threshold) before falling back to "new file", exactly as `-M` does for git mode.

**N4 — MEDIUM-HIGH, silent. Symlinked directories are not traversed, and vanish from every list.** A `*.py` file reachable only through a symlinked package directory is not analyzed, not counted, and appears in neither `production_files`, `test_files`, nor `parse_failures` — `files_analyzed` simply does not include it. Cause: `Path.rglob` defaults to `recurse_symlinks=False` on Python 3.13+, and this project runs 3.14.5. The first adversarial report recorded "symlinked package directories are traversed" as surviving behaviour; that is no longer true. Both real validation trees contain a symlinked `.claude` directory (no `*.py` under it today, so no live impact) — but a tree assembled with a symlinked source dir would silently lose it whole. Fix: `rglob("*.py", recurse_symlinks=True)` with a visited-inode set to stop cycles, or `os.walk(followlinks=True)`; either way name what was skipped.

**N5 — MEDIUM. The `keyword.value` half of the fix-1 walk-through is dead code.** `if f(key=subject):` scores **CONDUIT**, not `DECISION`+`CONDUIT`. `_governing_role` returns `(_CONTINUE, CONDUIT)` for `keyword.value`, the walk moves to the `keyword` node, and the `keyword`'s parent is `Call` with field `"keywords"` — for which there is **no rule**, since the `Call` case matches only `("args", "func")`. The walk terminates with an "unhandled construct `Call` (field='keywords')" note. Two consequences: the fix's stated coverage of keyword arguments does not exist, and the note is emitted only into `occurrences[].notes` in `--json` — `print_text_report` prints notes only for `UNCLASSIFIED` occurrences, and this one is not UNCLASSIFIED because a hop role was accumulated. **A reader of the text report sees nothing.** Fix: add `"keywords"` to the `ast.Call()` case, and print the "reached unhandled construct … role kept" notes in the text report as their own honesty section — they are exactly the "a rule is missing here" signal the tool was built to surface.

**N6 — MEDIUM. The fix-3 statement-span expansion over-corrects for declarations.** `_enclosing_statement_span` returns the *smallest enclosing `ast.stmt`*, which for an `ast.arg` or a `def`/`class` name **is the entire function or class**. Measured: changing `c = 3` to `c = 4` on line 4 of a function whose parameter is named `subject` reports the parameter at line 1 as a changed occurrence (`CEREMONY`); changing `y = 2` to `y = 9` inside `class subject:` reports the class name as a changed occurrence (`WRITE`). So in both diff modes, any edit anywhere inside a function or class whose name or parameter matches the subject books its declaration as touched. This is the mirror image of the defect that was fixed, and it inflates `CEREMONY`/`WRITE` in proportion to how large the enclosing bodies are. Fix: for `arg`/`def-name`/`class-name` occurrences, test the declaration's own line span (`def` line through the end of the signature), not the body.

**N7 — MEDIUM, silent-ish. `_root_forces_test_context` inspects the root's full ABSOLUTE path, including directories outside the tree.** Measured: a tree at `…/spec/candidateA/` containing only `pkg/prod.py` reports **production files: 0, production occurrences: 0, test occurrences: 1**. The check is `any(part in TEST_DIR_NAMES for part in root.resolve().parts)`, so any ancestor directory anywhere on the machine named `test`/`tests`/`spec`/`specs` silently reclassifies an entire candidate tree as test code. If the two trees under comparison are checked out under differently-named parents — and they are throwaway copies, so their parent directories are arbitrary — one tree's production bucket can go to zero while the other's does not, and the production comparison becomes meaningless in exactly the way F6 warned about, now from the fix rather than the bug. The printed file lists do make it visible to a careful reader. Fix: only inspect path components at or below a supplied project boundary, or require an explicit `--force-test-context` / `--test-path` flag rather than inferring from the absolute path.

**N8 — LOW. `CLOSURE_RULE_OWN_NAME` is unreachable.** The rule fires only when `d.name in subject_set`, and `consider()` returns early for any `name in subject_set`. It can never admit anything. Harmless (the seed already covers it), but the docstring and the `--help`-adjacent prose advertise it as one of three growth rules, and it will never appear in a closure listing. Delete it or fix the guard.

**N9 — LOW, but no longer as narrow as the deferral claims. `BoolOp` is still an unconditional terminal DECISION.** Confirmed: `value = entry.subject or "default"` labels `DECISION`. `KNOWN_LIMITATIONS[15]` argues this is "no longer load-bearing" because the ratio was retired — but the brief now names *per-location role annotation* as a claimed-trustworthy output, which puts it back on the hook. Measured lever: appending ` and True` — a no-op — to `flag = entry.subject` flips the report from `{'CONDUIT': 1}` to `{'DECISION': 1}`. Worth knowing for the real comparison: on the unrefactored `master-copy`, **one of the two production DECISIONs is produced by this rule** — `config.py:1787`'s `and winning_entry.allow_in_auto_mode` sits inside a `BoolOp` being *assigned* to `auto_mode_override`, and is scored DECISION without the walk ever confirming the result is branch-tested (it is, one line later, but the tool does not check). Mitigating: in the one-token case above an opaque hop *was* recorded, so that particular loss is honest.

**N10 — LOW, confirmed as documented but now compounding. Closure rebinding.** `KEY = "subject"` followed by `KEY = "something_completely_unrelated"` still leaves `KEY` tracked; 4 phantom occurrences for code that never references the subject. New wrinkle: the narrow `returns-tracked` rule now propagates the error one hop further — `def use(d): … return KEY` joins the closure off the *rebound* constant, so the phantom set grows rather than staying put. Documented as deferred; the compounding is not.

**N11 — LOW. A `.py` file reachable through two paths is still parsed and counted twice** (file-level symlink). Unchanged from F9.

## What I tried and could not break

- **The base identity match.** No substring, prefix, or suffix leakage in any of the fixtures; `flag_x` never matched `flag_x_2` or `_flag_x`; the `command` run on the real package reproduced the previous oracle's exact 82.
- **The crash surface.** Broken symlink, permission-denied, directory-named-`*.py`, latin-1 with a cookie, UTF-8 BOM — all handled, all named, exit 0.
- **The statement-span line filter**, in the direction it was fixed for. I could not construct a diff-mode case where a genuinely edited subject occurrence went unreported.
- **Decorator forms.** `staticmethod`, `classmethod` and `functools.cached_property` do not confuse closure growth; the rejections in the table above are all about the return *expression*, not the decorator.
- **`git init` was denied**, so git-diff mode was verified by reading plus the project's own tests rather than by independent fixture. That is the one Part 1 item I did not attack directly, and I am flagging it rather than implying I did.

## Bottom line

The repair is real: five of six fixes hold cleanly under direct attack, and the sixth (git rename) reads correct and is genuinely tested. The occurrence finder's identity matching is still exact. What the repair introduced is a new form of the same bias, in the opposite direction and with less signal than before: closure growth is now decided by one function body's expression style, the excluded-by-hop-limit bucket cannot report it by construction, and the opaque-hop count that the tool's own documentation offers as the compensating measurement does not fire on the shape it names.

**Can this instrument compare two codebases today? For occurrence finding and role annotation on a single tree, yes, with the seed-subject caveat. For comparing two trees, not yet — but the gap is narrow and nameable rather than fundamental.** Concretely: N1 plus N2 mean a tree that factors its policy behind accessors reports systematically fewer occurrences than one that inlines the same policy, with no bucket recording the loss; N3 means `--old/--new` is not usable for a move-heavy comparison at all; N7 means the two trees' production buckets can differ for reasons that have nothing to do with the trees. Fix N2 first — it is a handful of lines in `_find_opaque_hops_in_scope` and it converts N1 from a silent loss into a measured one, which is the difference between "cannot be trusted" and "can be trusted with a stated correction". Then N3 and N7, both of which are contained. N1 itself may not need solving if the loss is honestly reported, because the real trees' current output is a clean null result and the question is whether that null is real or manufactured — a "functions that consult but do not return the tracked symbol" listing would answer that directly.

One observation worth recording separately: on the two real validation trees the tool now reports **identical** numbers — production 9 (`CONDUIT 5, DECISION 2, WRITE 2`), test 17, 4 production opaque hops, closure `{ALLOW_IN_AUTO_MODE_KEY, allow_in_auto_mode}` — where the pre-fix version reported 16 vs 17 production and 50 vs 56 test occurrences. The closure fix removed every measured difference between the two trees. That is the expected consequence of a correct narrowing if the differences were artefacts, and it is also exactly what N1 predicts if they were not. The two hypotheses are not distinguishable from the tool's current output, which is itself the argument for adding the consults-but-does-not-return listing before this instrument is used to decide anything.
