---
title: TOO-45 change-role classifier - adversarial report
type: note
permalink: toolguard/too-45/reports/classifier-adversarial-report
tags:
- task-memory
- TOO-45
- report
- adversarial
---

# TOO-45 change-role classifier — adversarial report

Target: `tools/change_role_classifier.py` (read-only; not modified). 54 attack cases across 8 families, all executed against the real tool via its CLI. Scratch fixtures lived under the session scratchpad and have been removed.

**Verdict up front: the instrument cannot be trusted to compare two codebases.** Three independent defects each on their own invert or destroy the headline conduit-to-decision comparison, and the worst one is not an edge case — it is the tool's behaviour on the exact refactoring the TOO-45 experiment is trying to reward.

## Ranked findings

### F1 — FATAL. Decisions expressed through a call or an attribute are scored CONDUIT. The instrument systematically scores the better architecture worse.

`_governing_role` returns a **terminal** `CONDUIT` for `ast.Call` (fields `args`/`func`) and for `ast.Attribute` (field `value`). It stops walking there, so it never sees the `If`/`While`/`Compare` above. Every decision that routes the subject through one layer of indirection is booked as transport.

Measured on a single synthetic module, subject `subject`:

| source | correct role | tool |
|---|---|---|
| `if subject:` | DECISION | DECISION |
| `if subject == 3:` | DECISION | DECISION |
| `if bool(subject):` | DECISION | **CONDUIT** |
| `if len(subject) > 0:` | DECISION | **CONDUIT** |
| `if subject.enabled:` | DECISION | **CONDUIT** |
| `if subject.is_ready():` | DECISION | **CONDUIT** |
| `if isinstance(subject, str):` | DECISION | **CONDUIT** |
| `if items.get(subject):` | DECISION | **CONDUIT** |
| `if (found := subject) is not None:` | DECISION | **CONDUIT** |

Six of sixteen decisions misrouted, none flagged unclassified. The error runs in both directions at once — it removes from the DECISION denominator *and* adds to the CONDUIT numerator — so a single misclassification moves the headline ratio twice as far as it should. Reported ratio for that file was 0.80; the truthful value is 0.13.

The consequence is not academic. Two trees implementing the *same* requirement — a boolean `allow_in_auto_mode` honoured at four call sites:

- **Tree A**, the requirement copy-pasted inline at all four sites (`if mode == "auto" and entry.allow_in_auto_mode:` × 4): reported **`0.00 (0 CONDUIT / 4 DECISION)` — a perfect score.**
- **Tree B**, the requirement factored into one `auto_mode_permits(entry, mode)` predicate called from all four sites: reported **`undefined (0 DECISION locations; 5 CONDUIT)` — the worst reading the tool can produce.**

Tree B is the better architecture by any reading, and the instrument rates it as pure conduit with zero logic. The mechanism is twofold: the predicate's four call sites are `Call.func` → CONDUIT, and the predicate's own body ends in `return entry.allow_in_auto_mode`, which is `Return.value` → CONDUIT. A predicate function that *returns* its decision can never register a DECISION anywhere in the tree.

This is the single most important finding, because "did the refactoring pay off" and "does this codebase encapsulate its decisions behind named predicates" are close to the same question, and the instrument answers it backwards.

Suggested fix (not implemented): make `Call` args/func and `Attribute.value` `_TRANSPARENT` rather than terminal, so the walk continues to the governing `If`/`Compare`/`BoolOp`, and emit a dual role (`CONDUIT` for the hop plus `DECISION` for the governing construct) rather than choosing one. Separately, treat `return <tracked>` inside a function whose result is itself branched on as a decision — or, more cheaply, stop reporting a single ratio and report DECISION-reach (how many distinct call sites a decision governs) alongside it.

### F2 — FATAL. The headline ratio is trivially gameable by a `sed`.

Three purely mechanical, architecture-neutral transformations, each measured:

| transformation | before | after |
|---|---|---|
| append ` or None` to every subject use (6 transport sites) | `undefined (0 DECISION / 6 CONDUIT)` | **`0.00 (0 CONDUIT / 6 DECISION)`** |
| wrap `if entry.subject:` in `bool(...)` (3 sites) | `0.00 (0 CONDUIT / 3 DECISION)` | **`undefined (0 DECISION; 3 CONDUIT)`** |
| insert one `assert entry.subject is not None` | `undefined (0 DECISION / 4 CONDUIT)` | `4.00 (4 CONDUIT / 1 DECISION)` |

The first row is the killer: `sed -i 's/entry\.subject)/entry.subject or None)/g'` moves a tree from the worst possible headline to the best possible headline while changing nothing a reviewer would call architecture. `X or None` puts the subject in `BoolOp.values`, which is an unconditional DECISION. The second row is the same lever pulled the other way. This is precisely the defect class that killed an earlier instrument on this ticket ("a `sed` could satisfy it"), and here it does not merely satisfy a gate — it produces the top score.

Suggested fix: `BoolOp` should not be an unconditional DECISION; distinguish a boolean operation that *is* a branch test (walk up: is the `BoolOp` reached from an `If`/`While`/`IfExp`/`Assert` test?) from one whose result is assigned or passed, which is defaulting, i.e. transport. And no headline ratio should be published without an accompanying "how sensitive is this number to N-line edits" figure.

### F3 — FATAL for cross-tree comparison. Closure growth via `reads-tracked` inflates the numerator, by an amount that depends on how finely the tree is factored.

`_closure_growth_candidates`' `reads-tracked` rule admits **any function whose body mentions a tracked name**, and then at the next hop any function that mentions *that function*. Once a name is in the closure, `_analyze_tree` counts every occurrence of that bare name anywhere in the tree, with no scope, import or type check.

Measured on the real `toolguard/` package, subject `command`, default `--closure-hops 2`:

- closure grew to **19 names**, including `main`, `replay`, `run_maintenance`, `evaluate_migration`, `find_corpus_redundant_allows`;
- **142 occurrences reported, of which only 82 (58%) are the actual subject**;
- the 60 closure-member occurrences break down as CONDUIT/WRITE/CEREMONY and contribute **zero DECISION**;
- headline moves from a truthful 11.2 (56/5) to the reported **16.80 (84/5)** — a 50% inflation from symbols that are not the subject.

Subject `mode` on the same tree admits `_guarded_open` at hop 1 and then **`__enter__`** at hop 2 — a dunder, so every context manager in the tree is now an occurrence of `mode`. Half that subject's reported occurrences (4 of 8) are not the subject.

The inflation is not a constant offset. Closure size is a direct function of how many small functions the code is decomposed into — the exact variable the TOO-45 experiment is measuring. A finely-factored tree grows a large closure and collects a large CONDUIT surcharge; a coarsely-factored one does not. The two trees' numbers are therefore not on a common scale, and the direction of the bias again disfavours the better-factored tree.

Suggested fix: closure members admitted by `reads-tracked` should be tracked as *definitions to inspect*, not as *names to match tree-wide*; or at minimum, occurrences attributed to closure members should be reported in a separate bucket and excluded from the headline ratio, with the seed-subject ratio as the published number. The per-name breakdown the tool already has internally would make this cheap.

### F4 — SILENT LOSS. In diff modes, a real requirement edit at a subject site can report zero occurrences, zero unclassified, zero failures.

Changed-line restriction is applied against `node.lineno`. For a multi-line statement, the subject's node line is often not one of the lines difflib marks changed, even when the statement's meaning changed completely.

Case 1 — the subject's role changed from transport to branch:

```python
# old                    # new
def f(entry, sink):      def f(entry, sink):
    sink(                    if (
        entry.subject,           entry.subject,
    )                        ):
                                 return 1
```

`entry.subject` moved from a call argument into a branch test. Reported: `prod={}`, ratio `undefined (0 DECISION; 0 CONDUIT)`, `unclassified=0`, `parse_failures=0`, `removed_files=[]`. The tool states that this change touched the subject in **zero places**.

Case 2 — a DECISION's comparand was edited:

```python
    if (
        entry.subject
        == "old_value"     ->   == "new_value"
    ):
```

Same result: nothing reported anywhere, in any bucket. A requirement edit at a real decision site is invisible.

This is the house-style defect the brief warned about — under-count, failure direction toward "nothing to see", no honesty bucket. It matters most because `--old/--new` and `--repo` are the modes you would reach for when comparing before/after of one tree.

Suggested fix: expand each occurrence's line test to the full line span of its **enclosing statement** (`ast` gives `lineno`/`end_lineno` on every stmt), not the node's own line; a subject occurrence should count if any line of the statement it belongs to changed. Cheap, and strictly more correct.

### F5 — SILENT INFLATION. In git mode a pure `git mv` injects the entire file.

`run_git_diff` calls `_git_show(repo, base, path)`; for a renamed file the new path does not exist at base, so `old_source is None` and `allowed_lines` is set to `None`, meaning **every line of the file counts as changed**. Measured on a throwaway repo: `git mv a.py b.py` with byte-identical content reported `{'DECISION': 1, 'WRITE': 1}` where the correct answer is nothing. A rename-heavy refactor — which is what "architecture overhaul" tends to mean — will import whole files' worth of occurrences into the diff-mode counts as if newly written.

(A pure delete was handled correctly: `removed_files=['a.py']`, no counts. A no-op commit reported nothing. Those two behave.)

Suggested fix: use `git diff --name-status -M` and resolve the rename's old path, so the pre-image is fetched from the correct name.

### F6 — Test/production boundary is wrong in both directions.

`is_test_path` is a pure path rule. Measured on a six-file fixture:

| path | reality | tool |
|---|---|---|
| `pkg/test_helpers.py` | production helper | **TEST** |
| `spec/spec_thing.py` | tests | **PRODUCTION** |
| `src/conftest.py` | shared test fixtures | **PRODUCTION** |
| `pkg/testing/fixtures.py` | shipped test-support code | PRODUCTION (arguably right) |
| `tests/test_real.py` | tests | TEST |
| `pkg/real.py` | production | PRODUCTION |

Also: pointing `--tree` at a `test/` subdirectory strips the `test` path component from the relative paths, so the rule then depends entirely on filenames — a `test/unit/helpers.py` would be booked as production.

Severity is conditional but can be total: if the two candidate trees use different test-directory conventions (`test/` vs `spec/`), one tree's entire suite lands in the production bucket and the production ratio comparison is meaningless. Worth checking explicitly before any comparison run.

Suggested fix: report the actual file lists behind each bucket in the text output (currently only counts and a rule sentence are printed), so a misfiled tree is visible at a glance; and allow an explicit `--test-path` glob override.

### F7 — Closure abuse: over-attribution to names that no longer, or never did, mean the subject.

- **Rebinding is not noticed.** `KEY = 'subject'` followed by `KEY = 'something_completely_unrelated'` leaves `KEY` tracked; every `KEY` read in the tree is credited to the subject. Reported 2 CONDUIT + 4 WRITE + 1 CEREMONY for code that references the subject nowhere.
- **Same-named attribute in unrelated code is credited.** With `MODE = 'subject'` in `pkg/a.py`, an entirely unrelated `class Unrelated: MODE = '...'` with `if self.MODE == 'x':` in `pkg/b.py` produced a **phantom DECISION** attributed to the subject. Any subject whose string value is bound to a short, common constant name pollutes the whole tree.
- **Aliased imports are not followed inward.** `from pkg.a import real_thing as subject` tracks `subject` but never `real_thing`, so the defining module's own uses are invisible.

Correctly handled, and worth crediting: a docstring-only mention of a tracked symbol does **not** admit the function to the closure.

### F8 — Crashes on file-system and encoding conditions that occur in real trees.

`run_single_tree`/`run_two_tree_diff` call `Path.read_text` with no exception handling, and `_try_parse` catches only `SyntaxError`. Uncaught, with a traceback and a non-zero exit:

- a **broken symlink** named `*.py` → `FileNotFoundError`;
- a file with mode `000` → `PermissionError`;
- a **directory** named `weird.py` → `IsADirectoryError`;
- a **latin-1 file with a PEP 263 coding cookie** → `UnicodeEncodeError` from `compile()` (the `errors="surrogateescape"` read produces lone surrogates that `ast.parse` cannot re-encode).

These are loud, not silent, so they are lower severity than F1–F5 — but they mean the tool cannot be pointed at an arbitrary tree, and the latin-1 case is *valid Python* that the tool cannot process at all.

### F9 — Lower-severity role and robustness issues, all confirmed

- `a = subject or "default"` — a defaulting conduit — is scored **DECISION** (same `BoolOp` rule as F2). Over-counts the denominator.
- The walrus dual-role logic only fires when the subject is the walrus *target*. The far commoner `if (x := subject) is not None:` scores plain CONDUIT and the decision is lost (folded into F1).
- A **UTF-8 BOM** file is valid Python but is reported as a parse failure (`invalid non-printable character U+FEFF`). Loss is named, so honest, but it is a false failure.
- A `.py` file reachable through **two paths** (a file symlink) is parsed and counted **twice**.
- An expression nested more than `MAX_WALK_DEPTH` (60) levels degrades to UNCLASSIFIED: an 81-term `BinOp` chain inside an `if` test yielded 59 DECISION + 22 UNCLASSIFIED. Named, and UNCLASSIFIED is excluded from the ratio — so deep expressions quietly shrink the denominator.
- `obj[subject:]` (slice bound) and a bare `subject` expression statement land in UNCLASSIFIED. Correctly named, but both are excluded from the ratio.
- `HANDLERS[subject] = h_a` (a registry write) is scored CONDUIT, not WRITE.

## What survived the attack, and deserves saying

- **The base match is exactly right.** An independent `ast` oracle counted every exact-identity occurrence of five subjects (`mode`, `command`, `rule`, `path`, `value` — 394 occurrences) across the real `toolguard/` package and matched the tool's seed-subject counts **exactly, on all five**. No substring matching, no discovery loss, no over-match. The "never match on name substrings" claim in the docstring is true and verified.
- Symlinked package **directories** are traversed. Star imports, `__init__.py` re-exports, `if TYPE_CHECKING:` imports, empty files, JSON content in a `.py` file, `.pyi` stubs and NUL-byte files are all handled without loss or crash (the NUL-byte file appears correctly in `parse_failures`).
- The honesty machinery it does have is real: `parse_failures`, `removed_files`, `closure.parse_failures`, `excluded_by_hop_limit` and `unclassified_occurrences` all populate correctly when the corresponding condition is triggered. The problem is not that the buckets lie — it is that F1, F3, F4 and F5 route past all of them.
- `KNOWN_LIMITATIONS` is unusually honest and several entries were confirmed verbatim by these attacks (notably the "decision expressed by choosing between two call sites" entry, and the stale-alias entry). F1 is arguably a *sharper* form of a limitation already documented — but the documentation frames it as an edge, and the measurement above shows it is the common case.

## Bottom line for the TOO-45 comparison

Do not run the two candidate trees through this tool and compare the printed ratios. F1 alone makes the number anti-correlated with the property being measured, F3 puts the two trees on different scales, and F2 means the number would not survive an honest reviewer asking "what would a `sed` do to this". If a number is needed now, the safest available reading is: seed-subject occurrences only (F3 removed), single-tree mode only (F4/F5 removed), with the per-occurrence list read by hand to re-score the call-and-attribute decisions (F1) — which is to say, the tool is currently useful as an *occurrence finder*, where it is provably exact, and not as a *role scorer*.
