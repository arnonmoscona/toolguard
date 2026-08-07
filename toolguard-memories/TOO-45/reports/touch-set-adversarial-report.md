---
title: TOO-45 expected-touch-set harness - adversarial report
type: note
permalink: toolguard/too-45/reports/touch-set-adversarial-report
tags:
- task-memory
- TOO-45
- report
- adversarial
---

# TOO-45 expected-touch-set harness — adversarial report

Targets: `tools/touch_set_score.py`, `tools/touch_set_inventory.py` (read-only; neither modified, nor their tests). Roughly 80 executed cases across a granularity experiment, a Monte-Carlo sweep, and six attack families, all driven through the real CLIs or the real scoring functions. Fixtures lived under the session scratchpad and have been removed.

**Verdict up front: the instrument cannot currently be trusted to compare two codebases, and the specific reason is that the mitigation applied to the granularity problem does not work.** The demotion of rates in favour of counts did not remove the bias; it reversed its sign. Count and rate now disagree about which tree is better at every realistic prediction quality, and both are wrong in different regimes. Separately, the primary surprise count can be moved by a factor of three with a one-line regex on the actuals file, and driven to exactly zero by prediction volume alone.

The blindness guarantee — the one claim held as non-negotiable — **survived**, and survived a hard test rather than a reading.

## Part 1 — the decisive experiment

**Hypothesis: counts do not escape granularity bias, they only soften it. CONFIRMED, and it is worse than "soften".**

### 1A — same requirement, same per-location prediction quality, two decompositions

One requirement ("honour a per-rule `allow_in_auto_mode` boolean"), expressed as five conceptual work items, laid out COARSE (3 actual locations) and FINE (6 actual locations). Prediction quality is defined operationally as **per-location recall** — the fraction of that tree's own actual locations the predictor named — which is the only definition of "equally good predictor" that does not itself assume a granularity. Scored through the real CLI.

| prediction quality | COARSE surprises | COARSE misses | COARSE surprise_rate | FINE surprises | FINE misses | FINE surprise_rate |
|---|---|---|---|---|---|---|
| perfect (recall 1.00) | 0 | 0 | 0.000 | 0 | 0 | 0.000 |
| good (recall 0.67) | **1** | 1 | 0.333 | **2** | 2 | 0.333 |
| poor (recall 0.33) | **2** | 2 | 0.667 | **4** | 4 | 0.667 |

The count doubles with the decomposition. The demoted rate is identical to three decimal places. **The number the tool promoted to primary is the granularity-sensitive one, and the number it demoted with a printed warning is the granularity-invariant one.**

### 1D — the same result across the parameter space (Monte Carlo, 3000 draws per cell)

Pure-noise model: no architecture leak at all, predictor names each location independently with probability `p`. Cell is `mean surprise COUNT / mean surprise RATE`.

| recall p | n=1 | n=2 | n=4 | n=6 | n=8 | n=12 |
|---|---|---|---|---|---|---|
| 1.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 | 0.00 / 0.00 |
| 0.90 | 0.10 / 0.10 | 0.19 / 0.10 | 0.39 / 0.10 | 0.60 / 0.10 | 0.80 / 0.10 | 1.23 / 0.10 |
| 0.80 | 0.20 / 0.20 | 0.39 / 0.19 | 0.79 / 0.20 | 1.20 / 0.20 | 1.57 / 0.20 | 2.43 / 0.20 |
| 0.60 | 0.39 / 0.39 | 0.79 / 0.39 | 1.56 / 0.39 | 2.40 / 0.40 | 3.18 / 0.40 | 4.75 / 0.40 |
| 0.40 | 0.59 / 0.59 | 1.21 / 0.60 | 2.42 / 0.60 | 3.60 / 0.60 | 4.76 / 0.60 | 7.16 / 0.60 |

`E[surprises] = n × (1 − p)`, exactly, across the whole grid. Miss count behaves identically (`E[misses] = n × (1 − p)` with miss rate flat). The conversion factor a reader needs: **at a plausible per-location recall of 0.8, every extra actual location a tree has costs it 0.2 surprises before any architecture difference exists.** A tree with four more locations than its rival starts 0.8 surprises behind — the same order of magnitude as a single genuine architecture leak, which is the entire signal M2 is looking for.

`kind_mismatch_rate` **is** granularity-invariant, as claimed: with a true kind-error rate of 0.300 it read 0.273–0.308 across every combination of `n` in {1,2,4,6,8,12} and `p` in {0.6, 0.8, 1.0}. That claim in the docstring is correct. It measures the predictor's kind accuracy, not the architecture, and it is separately broken — see D4.

### 1G — head to head, identical architecture fact

Two trees, each with **exactly one** genuine architecture leak (a location no reading of the requirement would predict). COARSE has 3 actual locations, FINE has 8. The predictor is equally good on both. Any verdict other than "tie" is instrument bias. 20 000 paired draws per row.

| recall p | E[surp] COARSE | E[surp] FINE | count says | E[rate] COARSE | E[rate] FINE | rate says | P(count picks COARSE) |
|---|---|---|---|---|---|---|---|
| 1.00 | 1.00 | 1.00 | tie | 0.333 | 0.125 | FINE | 0.0% (ties 100%) |
| 0.90 | 1.20 | 1.70 | COARSE | 0.399 | 0.212 | FINE | 45.1% |
| 0.80 | 1.40 | 2.40 | COARSE | 0.466 | 0.300 | FINE | 64.7% |
| 0.70 | 1.60 | 3.11 | COARSE | 0.533 | 0.388 | FINE | 76.2% |
| 0.60 | 1.79 | 3.81 | COARSE | 0.598 | 0.477 | FINE | 84.8% |
| 0.50 | 1.99 | 4.49 | COARSE | 0.665 | 0.561 | FINE | 90.9% |

**The two published numbers give opposite verdicts at every prediction quality below perfect.** The count is unbiased only when prediction is perfect (`p = 1.00`, where it correctly ties); the rate is unbiased only when there is no prediction noise at all — and at `p = 1.00` the rate is the one that is wrong, calling FINE better 0.333 to 0.125 when the trees leak identically. Neither number is safe in the regime any real run will land in.

Restated as a decomposition: `surprises = leaks + n(1−p)`. The **count** carries the noise term, which scales with `n`. The **rate** is `leaks/n + (1−p)`, which divides the *signal* by `n`. Counting removes the denominator but not the dependence on granularity, because granularity was never only in the denominator — it is in the number of independent chances to be surprised. This is the same trap the protocol document diagnosed for M1 and believed it had escaped by switching from rates to counts; the escape does not hold.

### Is there a common unit at all?

**Not a per-location one, and I think this is a finding about the approach rather than about the tool.** Any per-location measure — count or rate — treats the locations of one requirement as independent trials, and they are not: a tree that splits one decision across four functions has not created four independent opportunities for an architecture leak, it has created one decision with four addresses. Counting them as four is exactly the "abstraction looks like sprawl" error.

The unit that *is* invariant is the **conceptual work item** — "carry the flag on the record", "make the decision honour it", "thread the mode to the decision point" — which is fixed by the requirement and identical across trees by construction. Under that unit both decompositions in 1A score one leaked concept, tie, correctly. The tool cannot see it: it has no notion of concept, and the harness report's own mitigation ("ask whoever authors `actuals.json` to grain locations at a consistent CONCEPTUAL level") is not verifiable, not enforceable, and — see D2 — is precisely the lever that moves the headline number by 3×.

My recommendation, which is a change to the protocol and not a patch to the tool: **stop publishing a surprise count and publish the surprise LIST**, with the predictor's own reading of the requirement beside it, and adjudicate each entry as "a careful reader would/would not have expected this". That is a holistic judgement over a small, fully enumerated set — five to fifteen items per canary — and it is defensible in a way the number is not. If a number is wanted anyway, it should be **distinct leaked concepts**, assigned by mapping each surprise onto the requirement's work items *before* the trees are unblinded, with the mapping recorded. That is the only quantity in this design that does not move when a tree refactors.

## Confirmed defects, ranked by whether they could change a two-codebase conclusion

### D1 — FATAL. The granularity mitigation is inverted. (Part 1 above)

Counts are `E = n(1−p)`; rates are granularity-flat under noise and signal-diluting under leaks. Count and rate disagree at every `p < 1`. The tool prints the biased number as PRIMARY with no caveat and the invariant one as SECONDARY with a warning telling the reader not to use it.

Suggested fix: print neither as a headline. Print the surprise list, `location_counts`, and — if a scalar is required — a concept-level count supplied by the same authoring step that writes `actuals.json`, with the concept mapping as a required field on every entry.

### D2 — FATAL. A one-line regex on the actuals file moves the primary count 3×, and nothing validates actuals.

Same underlying change, same predictor knowledge, both files re-grained from function level to file level by `sed 's/::.*//'`:

| graining | surprises | misses | matched |
|---|---|---|---|
| function-level (as designed) | **3** | 0 | 3 |
| file-level (one regex, both files) | **1** | 0 | 2 |
| actuals file-level, predictions function-level | **3** | **3** | **0** |

The third row is the accident case rather than the attack case: a judge who grains coarser than the predictor produces total mismatch, `kind_mismatch_rate` undefined, and no bucket anywhere saying "these two files are not graining at the same level". `location_counts` is printed and a careful reader could infer it, but nothing states it.

This is the direct analogue of the classifier's F2, and it lands on the number promoted to primary *because* it was believed immune. Note the asymmetry that makes it dangerous rather than merely fragile: **the actuals file is the one file in this design that nothing validates at all.** `--validate-predictions` exists for predictions; there is no `--validate-actuals`, and the scorer reads no tree.

Suggested fix: require every entry on both files to carry a `concept` field drawn from a requirement-supplied vocabulary, and refuse to score when the two files' graining differs (compare the distribution of qualnamed vs bare-path locations, and the concept-to-location fan-out, and fail loudly).

### D3 — FATAL. Nothing constrains prediction volume; surprises go to zero on demand.

`surprises = |actuals \ predictions|` is monotonically non-increasing in the prediction set, and no code path bounds, weights, or flags the prediction count. Measured: an honest 4-location prediction against a 6-location actual gives **2 surprises**; the identical predictor padded to 16 real locations in the same modules gives **0 surprises, 10 misses**. Zero surprises reads as "no architecture leak".

The ceiling is not theoretical. `--validate-predictions` accepts **every** function, class, method and private helper at any nesting depth: on this repo that is **4869 distinct locations**, all of which pass validation with exit 0. A predictions file naming all of them guarantees `surprises == 0` against any actuals file whatsoever, while passing the only gate in the workflow.

The abuse does not need to be that crude. Because predictions are authored per tree, from that tree's own inventory, a difference in prediction *budget* between trees — even an unintentional one, e.g. the predictor being more thorough on the tree it read second — moves the surprise counts directly and in opposite directions.

Suggested fix: fix the prediction budget before authoring (e.g. "name at most 1.5× the irreducible footprint you predicted"), record it, and have the scorer refuse to score, or loudly flag, when `predicted_unique / actual_unique` exceeds a stated threshold. At minimum print that ratio next to `location_counts` rather than leaving the reader to divide.

### D4 — FATAL for the one primary rate. A judge's abstention is scored as the predictor being wrong.

An actuals entry with `kind` omitted or `null` gets `KIND_UNKNOWN`, which then compares unequal to every predicted kind, so **every correctly-located prediction on an abstained location is counted as a kind mismatch**, and the location stays in the rate's denominator.

| case | matched | matched_with_known_kind | kind_mismatches | kind_mismatch_rate |
|---|---|---|---|---|
| single judge abstains on 1 of 1 matched location | 1 | **1** | **1** | **1.000 (1/1)** |
| single judge abstains on 3 of 4 matched locations | 4 | **4** | **3** | **0.750 (3/4)** — truth is 0/1 |
| dual judge, BOTH abstain on 1 of 2 | 2 | **2** | **1** | **0.500 (1/2)** |
| dual judge, entry has no kind fields at all | 2 | **2** | **1** | **0.500 (1/2)** |

The field name `matched_with_known_kind` is false: it subtracts judge *disagreements* only, never unknowns. `actual_locations_kind_unknown` is printed separately, so the information is on the page — but the rate the reader is told is PRIMARY and undemoted is wrong by exactly the abstention count, in the direction of "the predictor was wrong". A judge who abstains more on the harder-to-read tree hands that tree a worse kind-mismatch rate for reading difficulty alone, which is close to the opposite of what the measure is for.

The committed test suite never places a `kind_unknown` actual on a *matched* location — only on a surprise — so this is untested, not intentional.

Suggested fix: exclude `KIND_UNKNOWN` actuals from both the numerator and the denominator of `kind_mismatch_rate` (make `matched_with_known_kind` mean what it says), and report `matched_with_unknown_kind` as its own bucket alongside disagreements.

### D5 — HIGH, and directional. The validator rejects real locations, manufacturing surprises at the requirement's data-carrying location.

`--validate-predictions` builds its location set from `FunctionDef`/`AsyncFunctionDef`/`ClassDef` only. Anything else that a diff judge would legitimately name is reported as *"invalid (NOT found in tree — likely a guessed name)"*, exit 1, gating the predictor into deleting it. Measured on real fixtures:

| predicted location | reality | validator |
|---|---|---|
| `pkg/real.py::Outer.Inner.method` | nested class method | valid |
| `pkg/real.py::_private_helper` | private helper | valid |
| `pkg/deep.py::a.b.c.d.e` | 5-deep nested def | valid |
| `pkg/real.py::only_in_a_comment` | comment only | **invalid (correct)** |
| `pkg/real.py::string_only_name` | string literal only | **invalid (correct)** |
| `pkg/real.py::DataLike.field_one` | **dataclass-style field** | **INVALID (wrong)** |
| `pkg/real.py::lambda_assigned` | module-level lambda | **INVALID (wrong)** |
| `pkg/real.py::gen_a` | name generated at runtime | **INVALID (wrong)** |

On the real repo, `toolguard/rule_entry.py::RuleEntry.pattern` — an actual field of an actual frozen dataclass — is reported invalid. So is `toolguard/config.py::RuleEntry.allow_in_auto_mode`, which is **the scorer's own module-docstring example location**. The tool's canonical worked example fails its own gate.

Why this is directional rather than merely annoying: the `record` kind lands on data-carrying declarations more than on functions, and "add a boolean to the rule record" is the shape of several of the twelve micro-requirements. A predictor gated out of naming the field, paired with a judge who is not gated at all and will name it, produces a **guaranteed manufactured surprise at the single most predictable location in the change** — and it fires on whichever tree carries the requirement in a typed record rather than in a function, which is not a property either tree should be scored on.

Suggested fix: include `AnnAssign`/`Assign` targets at class and module level in the validation location set (they are cheap to collect from the same walk), and downgrade "not found" from a hard exit-1 gate to a warning that names the nearest real locations, since the validator's false-negative cost is now demonstrably higher than its false-positive cost.

### D6 — SILENT LOSS. Duplicate JSON keys are resolved by `json.loads` last-wins, with no warning anywhere.

`json.loads` silently keeps the last occurrence of a repeated key. Neither loader checks for it (`object_pairs_hook` is not used), so:

- `{"location": "pkg/a.py::f", "location": "pkg/z.py::gone", "kind": "decide"}` scores as `pkg/z.py::gone` only. The real location the judge wrote **vanishes with no bucket**, and the result is a phantom **surprise** (`pkg/z.py::gone`) *and* a phantom **miss** (`pkg/a.py::f`) — both headline counts corrupted from one entry, zero warnings.
- `{"location": "...", "kind": "decide", "kind": "transport"}` scores `transport`, `kind_mismatches=1`, `kind_mismatch_rate 1.000`. A judge's first verdict is discarded silently.
- `{"kind_1": "decide", "kind_1": "transport", "kind_2": "transport"}` — a real judge disagreement — is silently reconciled into agreement: `kind_disagreements=0`. This directly violates the module docstring's *"this tool never averages, reconciles, or silently picks one"*.

This is the house-style defect the brief names: a real input vanishes into no explicit bucket, and the failure direction is toward a confident number.

Suggested fix: load with `object_pairs_hook` and make a repeated key a fatal schema error on both files. Three lines.

### D7 — SILENT LOSS. A duplicated actuals location silently reconciles a real judge disagreement, and the text report never shows the second verdict.

Two entries for the same location, the first with judges agreeing and the second with judges disagreeing: `_dedupe` keeps the first, so `kind_disagreements = 0` and `kind_mismatch_rate = 0.000 (0/1)`. The disagreement is present in the file and does not appear in the disagreement bucket.

The `ambiguous_actuals` bucket does list the location, and the JSON output carries `kind_2` — but `print_text_report` renders it as `kinds given = [decide, decide]`, joining only `e["kind"]` (judge 1). **A reader of the text report sees no trace of judge 2's conflicting verdict at all.** The stated guarantee that disagreement is never silently reconciled holds only for non-duplicated locations.

Suggested fix: compute `kind_disagreements` over *all* entries, not deduplicated ones, and render both judges in the ambiguous-actuals text block.

### D8 — HIGH for a hand-authored file. Cosmetic location variance costs one surprise AND one miss each.

Every one of these produced `surprises=1, misses=1, matched=0` — two headline units of damage from one character, on a measure whose real signal is of size one to three:

| predictions | actuals | outcome |
|---|---|---|
| `pkg/A.py::f` | `pkg/a.py::f` | phantom surprise + phantom miss |
| `pkg/a.py::Outer. inner` | `pkg/a.py::Outer.inner` | phantom surprise + phantom miss |
| `pkg/a.py::café` (NFC) | `pkg/a.py::café` (NFD) | phantom surprise + phantom miss |
| `pkg\a.py::f` | `pkg/a.py::f` | phantom surprise + phantom miss |

`normalize_location` strips only the ends of the qualname and normalises only the path half's leading `./` and `/`. The unicode case is the worrying one because it is invisible on screen and CPython NFKC-normalises identifiers anyway, so the two strings genuinely denote the same function. These are not silent — both buckets list them — but "not silent" is weak comfort when the primary output is a count of order 2 and the files are hand-typed by two different agents.

Suggested fix: `unicodedata.normalize("NFKC", ...)` on the qualname, collapse internal whitespace around `.`, and normalise `\` to `/` in the path half. Case should be left alone (Python is case-sensitive) but a near-miss warning — "no exact match, but a location differing only in case exists on the other side" — would catch the rest cheaply.

### D9 — STRUCTURAL. The two-judge machinery cannot express disagreement about the primary output.

`kind_1`/`kind_2` live inside a single shared entry, so the file structurally assumes both judges listed the same location set. There is no way to say "judge 1 did not consider this location changed at all" as distinct from "judge 1 abstained on its kind" — the closest expression, an entry carrying only `kind_2`, is scored as an abstention-disagreement. Which means **the surprise count and the miss count, the two primary outputs, have no second-judge check of any kind.** Only the kind axis is double-judged, and that is the axis the harness report itself calls secondary in importance to the surprise list.

Suggested fix: two separate actuals files, one per judge, reconciled by the tool — with location-set disagreement reported as its own bucket, exactly as kind disagreement is now.

### D10 — LOW. A location of `"/"` or `"./"` passes the non-empty guard and normalises to the empty string.

`"location": "/"` in predictions and `"location": "./"` in actuals both become `""` and **match each other**, scoring `matched=1`. `"   "` is correctly rejected; `"/"` is not. The `--validate-predictions` path shows the same string as `- ''` in its invalid list. Harmless in practice, but it is a hole in the one validation rule the loader has for its key field.

Suggested fix: apply the non-empty check *after* normalisation.

### D11 — LOW (loud, not silent). Filesystem and encoding crashes, inherited from the same family as the classifier's F8.

Both `run_inventory` and `all_locations_for_validation` call `Path.read_text` unguarded and catch only `SyntaxError` from `ast.parse`. Uncaught traceback, exit 1, in **both** the inventory and validate modes:

- broken symlink named `*.py` → `FileNotFoundError`
- directory named `weird.py` → `IsADirectoryError`
- latin-1 file with a PEP 263 coding cookie (**valid Python**) → `UnicodeEncodeError` from the surrogateescape read
- file with mode `000` → `PermissionError`

Handled correctly: UTF-8 BOM and NUL-byte files land in `parse_failures` and are named. One quiet one: a module reachable through a **file symlink** is inventoried twice (`pkg/ok.py` and `pkg/alias.py`, both with `ok`), inflating `modules_found` and the location set.

### D12 — MEDIUM for protocol hygiene. The inventory shows the blind predictor the project's gitignored scratch directory.

`EXCLUDED_DIR_NAMES` is a fixed denylist with no `tmp`, `scratch`, `site-packages`, `.tox`, `env`, or `.eggs`, no `--exclude` flag, and no gitignore awareness. On this repo the inventory a predictor would be handed contains **11 modules from `tmp/`** — which is in `.gitignore` and is where agents on this ticket park scratch work — including one named `tmp/auto-mode/scan_auto_mode.py`. For the auto-mode canary that filename alone is a hint about the requirement's subject matter, and it is the sort of file a canary implementer or a previous analysis run could plausibly leave behind. Nothing about the change leaks *today*, but the channel is open and unguarded.

Suggested fix: add `--include` (restrict to the package under test) and honour `.gitignore`, or at minimum require an explicit path list rather than a whole repo root.

## What survived, and deserves saying

- **The blindness guarantee is real, and I tested it rather than read it.** Running `run_inventory` on the real repo under a `sys.addaudithook`: **170 files opened, 0 outside the tree, 0 under `.git`, 0 subprocess/socket/exec events.** The emitted schema is `{path, is_test, line_count, docstring_first_line, public_symbols}` and nothing else. There is no diff mode, no second-tree mode, no VCS read, and no code path that could acquire one. A blind predictor cannot learn anything about the change from the inventory's *content*; the residual exposure (D12) is about what a repo happens to contain, not about the tool reaching for it. Caveat worth recording: the tool has no provenance field, so nothing in its output would reveal that a *post*-implementation tree had been inventoried by mistake. That is a workflow risk, not a tool defect, but it is unrecoverable after the fact.
- **Schema validation is genuinely strict where it is strict at all.** Rejected fatally, with a clear message: top-level object instead of array, non-object entries, malformed JSON, `null`/integer/whitespace-only `location`, integer or unknown or trailing-whitespace `kind`, the reserved literal `"kind_unknown"` on either file, `kind_1`/`kind_2` in a predictions file, mixed single/dual entries in one actuals file, UTF-8 BOM on the JSON. No partial scoring of a broken file was observed anywhere.
- The `KIND_UNKNOWN`/`KIND_DISAGREEMENT` collision assertions do what they claim.
- The plain duplicate case behaves as documented: `predictions_raw` vs `predicted_unique` and the `ambiguous_*` buckets let a reader see how many entries were collapsed. Ten copies of one location report `raw=10, unique=1, ambiguous=1`.
- Scale is fine: 20 000-entry files score correctly and fast.
- Deeply nested qualnames, nested class methods, private helpers and decorated functions all validate correctly; comment-only and string-literal-only names are correctly rejected.
- `kind_mismatch_rate` is granularity-invariant exactly as claimed (0.273–0.308 against a true 0.300 across 18 granularity/quality cells). Its problem is D4, not granularity.
- `KNOWN_LIMITATIONS` #2 is honest about the underlying sensitivity. The error is not concealment — it is that the mitigation chosen ("report counts, demote rates") is the wrong way round, and #2 asserts the opposite: *"surprise and miss are reported as COUNTS and LISTS (primary output, immune to this bias)"*. That sentence is false, and Part 1A is a two-line counterexample.

## Bottom line for the TOO-45 comparison

Do not compare surprise counts between the two candidate trees. Under the tool's own model a difference of four actual locations is worth ~0.8 phantom surprises at plausible prediction quality, which is the size of the effect being looked for; a one-line re-graining of the actuals file is worth 3×; and prediction volume can zero the number outright with the validator's blessing.

What M2 is still good for, and it is not nothing: **the surprise LIST**. Enumerating "here are the places that changed which nobody predicted, with the predictor's reasoning beside each" is genuinely the sharpest question in the whole suite, and the machinery that produces that list is sound once D5–D8 are fixed. Read it, argue each entry, map each to a conceptual work item, and report the number of leaked *concepts* with the mapping shown. That is a judged result with a visible audit trail, which is what this measure always was — the counting step is what dressed it up as mechanical.

Fix order if the tool is kept: D6 (three lines, `object_pairs_hook`), D4 (one expression), D7 (one expression), D8 (a normalisation pass), D5 (extend the validator's walk), then D2/D3 as protocol changes with tool support. D1 is not fixable inside this tool.
