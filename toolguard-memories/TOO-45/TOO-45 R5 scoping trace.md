---
title: TOO-45 R5 scoping trace
type: note
permalink: toolguard/too-45/too-45-r5-scoping-trace
tags:
- task-memory
- TOO-45
---

# TOO-45 R5 scoping trace

Measured 2026-08-05 on branch `too-45` with nine stages of uncommitted work in the tree. Every probe was reversible: originals copied to `scratchpad/r5-backups/`, restored by copy-back, verified by `sha256sum`. No git write of any kind was issued. **Final state re-verified: `git status --porcelain` = 80 lines, identical to the 80 at start; suite 2,355 OK; `ruff check --no-cache` clean; `--guard` PASS 12/12.**

Every claim below is labelled **DEMONSTRATED BY EXECUTION** or **INFERRED BY READING**.

---

# 1. Instrument assessment — R5 must not be scored on this predicate as it stands

Nine defects. Two of them are disqualifying on their own.

## I-9 (disqualifying). R5 is unpassable: the cycle check has no out-of-scope filter

**DEMONSTRATED.** `find_import_cycles` returns every strongly connected component in the whole graph, with no scope filter. `parser.command_extractor <-> parser.multiline` lives entirely inside `toolguard/parser/`, which the execution plan puts explicitly out of scope ("Out of scope, unchanged ... `toolguard/parser/` including the generated parser"). R1 has `R1_OUT_OF_SCOPE_PACKAGES = ("parser",)` and prints an explicit `(out of scope -- ...)` line; R5 does not. `tools/architecture_fitness.py:679-682` states the omission is deliberate because "R5's cycle check and R6's private-import check both have their own, different reasons to look at (or past) parser/" — but no such reason is stated anywhere in the plan, the ideal picture, or the delta.

Consequence, demonstrated: after I applied the one-line fix that removes the `hook <-> tools.decision` cycle entirely, `--predicates` still reported **R5: FAIL** on the parser cycle alone. **No amount of in-scope work can turn R5 green.** A predicate that reports FAIL for every possible outcome of the step is not evidence about the step.

## I-3 (disqualifying). The predicate counts intra-layer fan-in, which the ideal picture *requires*

**DEMONSTRATED + INFERRED.** The ideal picture maps the layers as `runtime = ingest, record, externalise` ([[TOO-45 ideal picture]], "Mapping onto layers"). `hook` is the ingest; `log_writer` and `error_log` are the record; `session_warnings` is an externalise. So `hook -> log_writer` is the ideal picture working exactly as designed — and the predicate calls it a violation. Four of the nine flagged edges are `hook -> {error_log, log_writer, session_warnings, subagent}`, all intra-`runtime` (DEMONSTRATED: layer map from `.pyscn.toml`, edges from the graph).

The predicate as written therefore cannot be satisfied by *any* design consistent with the ideal picture, except by emptying the `runtime` layer down to entry points only — which is I-1's relabelling move. The plan's headline says "entry points and scripts are leaves"; the code says "no module in the layer named `runtime` has fan-in". Those are different questions, and the code is asking the wrong one.

## I-1. "Entry point" is a label in `.pyscn.toml` that the R5 implementer can edit, and nothing catches it

**DEMONSTRATED BY EXECUTION.** I edited three lines of `.pyscn.toml` — moved `error_log`, `session_warnings`, `subagent`, `update_check` into the `foundation` package list and `log_writer` into `config`, leaving `runtime = ["hook", "session_start"]`. **Zero Python changed.** Result: R5's non-leaf list went **7 -> 2**, `--layers` violations **3 -> 2**, and `test_architecture.py` + `test_architecture_fitness.py` ran **147 tests, OK**. Restored; sha256 `2555bf9d…eaca` matches the original byte for byte.

Nothing in the repo distinguishes that edit from real work. It is legitimate as far as every automated check is concerned, and it is refutable only by appeal to the ideal picture's prose. Note the uncomfortable part: five of those modules genuinely import nothing above `foundation` (DEMONSTRATED — `error_log`, `session_warnings`, `subagent` have **zero** toolguard imports; `update_check` imports only `_git` and `constants`; `log_writer` imports only `config.find_project_root`), so the relabelling is *defensible*, which is what makes it the dangerous move rather than an obvious cheat.

## I-2. The predicate's entry-point set is neither sound nor complete

**DEMONSTRATED.** `pyproject.toml [project.scripts]` declares 7 console scripts. The predicate judges 9 modules. Overlap is 4.

| Declared entry point | layer | fan-in | in predicate set? |
|---|---|---:|---|
| `hook` | runtime | 1 | yes |
| `session_start` | runtime | 0 | yes |
| `update_check` | runtime | 1 | yes |
| `scripts.migrate_permissions` | tooling | 3 | yes |
| `tools.installer` | tooling | 0 | **no** |
| `tools.maintenance` | tooling | 0 | **no** |
| `tools.security_audit` | tooling | 0 | **no** |

And judged-but-not-an-entry-point: `error_log` (fan-in 2), `log_writer` (1), `session_warnings` (1), `subagent` (2), and the `scripts` package `__init__` (0). None of these five has a `main()` (DEMONSTRATED by scanning their top-level defs). The three missed tooling entry points have fan-in 0 today, so there is no live false negative — but there is also no regression guard. The predicate never reads `pyproject.toml`.

## I-4. It cannot distinguish an annotation-only import from runtime coupling

**DEMONSTRATED** on a synthetic six-file package built and destroyed outside the repo, run through the real `build_import_graph`: an import under `if TYPE_CHECKING:` produced the edge `entry -> annotated_only`, indistinguishable from a real one. `build_import_graph` records `ImportEdge.is_local` and then discards it, and never looks at `TYPE_CHECKING` at all.

No live effect today: **DEMONSTRATED that zero of the flagged edges are TYPE_CHECKING-guarded** (a per-site AST probe over all of `toolguard/` reported `type_checking=False` for every one). But the answer to "does it distinguish annotation-only from real coupling" is **no**, and the direction of the error is the safe one only by luck — it over-reports, so a future annotation-only import would be scored as a violation whose removal is pure bookkeeping.

## I-5 / I-6 / I-7 / I-8. Four kinds of coupling it cannot see at all

All **DEMONSTRATED** on the same synthetic tree except I-7, which is demonstrated on the real one.

- **I-5 string-keyed dynamic import.** `importlib.import_module("toolguard.dynamic")` produced **no edge**. `hook` could keep calling `decide()` through `importlib` and R5 goes green with the coupling untouched.
- **I-6 callback injection.** `def d(callback)` produced **no edge**. Passing `decide` into `_resolve_event` as a parameter satisfies R5 with byte-identical runtime behaviour. This is the most dangerous one because it reads as good design. R1's own trace already found this exact blind spot: `resolve.py`'s callback re-enters `Configuration` 3,258 times per corpus run and no import graph shows it.
- **I-7 monkeypatching — and on two of the seven modules it is the *dominant* coupling.** `test/unit/_real_log_dir_guard.py:201-204` rebinds `log_writer.log_command`, `log_writer.log_discovery`, and `error_log.{log_conflict,log_error,log_warning}` by `setattr` on the module object, at `test/unit/__init__.py` import time, before any test module loads. DEMONSTRATED consequence: renaming that API, or moving either module, takes the suite to **`RAN=0`** — 2,355 tests never run, one collection error. The predicate scans only `toolguard/` and sees none of this.
- **I-8 `toolguard/__init__.py` is not a graph node.** DEMONSTRATED: `"" in build_import_graph()` is `False`; `build_import_graph` does `if rel == "": continue`, dropping the node *and its edges*. The file is import-free today (332 bytes, a version string), so this is latent — but one re-export line there launders any edge past R5, R6 and `--layers` alike.

## What the instrument must become before R5 is scored

1. **Apply an out-of-scope filter to the cycle check**, and *print* the exclusion the way R1 does. (Fixes I-9. Without this R5 cannot pass.)
2. **Replace "module is in the layer named `runtime`" with "module is named in `pyproject.toml [project.scripts]`"**, keeping `scripts/` package membership as a second, independent criterion. One change fixes I-1 (the label stops being the input), I-2 (soundness and completeness), and I-3 (intra-layer service edges stop being violations, because services are not entry points). The predicate then reads what the plan actually says: **no declared console-script module has fan-in > 0, and no `scripts/` module has fan-in > 0.**
3. **Add a companion detector for the gaming surface**, since items 5, 6 and 8 are all cheap and all invisible: flag `importlib.import_module` / `__import__` called with a string literal starting `toolguard.`, and make `toolguard/__init__.py` a real node. Callback injection (I-6) cannot be detected structurally — it must be an explicit judge question, phrased as *"did the dependency move, or only its spelling?"*
4. Leave the annotation-only gap (I-4) documented rather than fixed. It over-reports, it has zero live instances, and closing it would let a real import hide under a `TYPE_CHECKING` guard.

**One thing the instrument gets right, and it matters:** `--layers`' completeness check *does* catch a module that appears under a new name without a `.pyscn.toml` entry — every move probe produced a `test.unit.test_architecture` failure. So a mover cannot silently relabel; they must make the edit visibly. It is a visibility guarantee, not a prevention.

---

# 2. Recommended split

Ordered. R5a-0 is a prerequisite: R5 has no scoreable outcome until the instrument is fixed.

| Stage | What | Tests broken (DEMONSTRATED) | Real or bookkeeping |
|---|---|---:|---|
| **R5a-0** | Fix the predicate (items 1-3 above) | 0 production; new tests only | prerequisite — R5 is unscoreable without it |
| **R5a** | `tools/decision.py` imports `FILE_TOOLS` from `constants`, not `FILE_PATH_TOOLS` from `hook`; rewrite hook's stale `# noqa` justification | **0** | **real** — kills the cycle and hook's only fan-in |
| **R5b** | `scripts.migrate_permissions`: split the migration library out of the CLI leaf | **88** | **real** — a script is a library for 3 modules |
| **R5c** | `update_check`: split install-detection out of the CLI leaf | **180** | **real** — same shape, bigger |
| **R5d** | `config_divergence` stops writing warnings; returns them to its caller | **34** (seam) / 38 (whole-module move) | **real** — closes an upward layer violation |
| **R5e** | `subagent`: split the transcript-parsing library out | **1** | real but **UNPROTECTED** — see the warning below |
| *out of R5* | `hook -> {log_writer, error_log, session_warnings}` | 2,357 (whole suite) | **bookkeeping** — the ideal picture requires these |
| *deferred to R6* | move `decide()` to the `api` layer | **333** | real, and it is R6's stated job |

**Recommended R5 = R5a-0 + R5a + R5b + R5d.** That is 122 broken tests across three code stages, each independently revertible, and it closes both genuine upward layer violations plus the cycle.

**R5c (`update_check`, 180) is a judgement call.** Its only importer is `tools.installer`, a tooling module reaching down into a runtime entry point — layer-legal, so `--layers` never complains. It is real debt but it is the least entangled with anything else in this ticket, and 180 tests is more than R5a+R5b+R5d combined. Recommend deferring unless Arnon wants R5 to close the whole entry-point/library mixing pattern in one pass.

**R5e (`subagent`, 1 test) is the trap.** One broken test is not "cheap", it is "there is nothing here to catch a mistake": **DEMONSTRATED — there is no `test/unit/test_subagent.py`, and renaming all four of `subagent`'s public library functions across the package broke exactly zero tests (RAN=2355, OK).** The existing auto-memory note *Subagent ID broken — logging-only impact; don't chase subagent.py coverage* explains why. Either write the tests first or do not touch it in R5. Do not let the low number read as low risk; it is the opposite.

---

# 3. Blast-radius table (full)

Method, exactly as the R1 trace: word-boundary rename across `toolguard/**/*.py` **only** (never `test/`, never `tools/`), full `unittest discover` run, then restore from byte backup with sha256 verification. Damage = failures + errors + tests that never ran because a test module failed to import — the bare failure count understates it badly, as predicted. Baseline **2,355 OK**.

Module *moves* were probed separately and more faithfully: the `.py` file was physically renamed and only in-package dotted paths rewritten, leaving `test/` pointing at the old path — which is what a move actually does. Where both numbers exist, the move number is the one to trust; the word-rename number is contaminated wherever the module name is also a common identifier (`subagent` 684 vs move 1; `error_log` 798 vs move 2,357 — contaminated in *both* directions).

| Probe | Symbols / module | files touched | failures+errors | never ran | **damage** |
|---|---|---:|---:|---:|---:|
| A1 | `hook.FILE_PATH_TOOLS` | 2 | 2 | 91 | **93** |
| **A1'** | **the actual R5a edit (one import line + noqa comment)** | 2 | 0 | 0 | **0** |
| A2 | `decide` (word) | 18 | 9 | 324 | 333 |
| A-full | **move `tools.decision`** | 11 | 9 | 324 | **333** |
| B1 | `create_backup`, `write_toml_config`, `write_json_config` | 4 | 1 | 84 | 85 |
| B2 | `migrate_permissions` (word) | 10 | 10 | 196 | 206 |
| **B** | **move `scripts.migrate_permissions`** | 4 | 4 | 84 | **88** |
| B3 | `run_auto_migration` (the seam) | 2 | 7 | 23 | 30 |
| C1 | `InstallKind`,`InstallInfo`,`detect_install`,`remote_head`,`local_remote_head` | 3 | 2 | 170 | 172 |
| C2 | `update_check` (word) | 4 | 1 | 127 | 128 |
| **C** | **move `update_check`** | 1 | 4 | 176 | **180** |
| D1 | `subagent` library fns | 2 | 0 | 0 | **0** |
| D2 | `subagent` (word) | 3 | 54 | 630 | 684 |
| **D** | **move `subagent`** | 2 | 1 | 0 | **1** |
| E1 | `error_log` write API | 4 | 1 | 2,356 | **2,357** |
| E2 | `error_log` (word) | 3 | 57 | 741 | 798 |
| **E** | **move `error_log`** | 3 | 1 | 2,356 | **2,357** |
| E3 | `check_and_warn_divergence` (the seam) | 2 | 5 | 29 | **34** |
| F1 | `LogRecord`,`log_command`,`log_discovery` | 3 | 1 | 2,356 | **2,357** |
| **F** | **move `log_writer`** | 2 | 1 | 2,356 | **2,357** |
| G1 | `issue_takeover_warning` | 2 | 4 | 24 | 28 |
| **G** | **move `session_warnings`** | 1 | 3 | 24 | **27** |
| H | move `config_divergence` (control) | 5 | 9 | 29 | **38** |

The 2,357s are the I-7 monkeypatch: `test/unit/__init__.py` fails to import, so the suite reports `Ran 0 tests` with a single collection error. **A partial run gives no signal at all on those two modules** — anyone touching `log_writer` or `error_log` gets a binary all-or-nothing result and must fix `_real_log_dir_guard.py` in the same edit. That is a good reason to keep both out of R5.

---

# 4. Are the seven real violations?

| Flagged | Edge(s) | Verdict |
|---|---|---|
| `parser.multiline <-> parser.command_extractor` | intra-`parser` | **NOT a violation — out of scope, and the predicate is wrong to report it.** See I-9. |
| `hook` <- `tools.decision` | `FILE_PATH_TOOLS` | **REAL, and free.** See §5. |
| `scripts.migrate_permissions` <- `auto_migrate`, `tools.installer`, `tools.rule_apply` | `create_backup`, `write_toml_config`, `write_json_config`, `migrate` | **REAL.** A 1,263-line console-script module (`toolguard-migrate`) is the library home for the config write path. `auto_migrate` (config layer) reaches it by a function-local import at line 174 — an upward layer violation `--layers` reports. INFERRED: the writers belong beside `config_write_guard`. |
| `update_check` <- `tools.installer` | `InstallKind`, `detect_install`, `remote_head`, `local_remote_head` | **REAL but layer-legal.** A console-script module (`toolguard-update-check`) that also holds the install-provenance library. Same mixing defect as the previous row, no layer violation to force it. |
| `error_log` <- `config_divergence`, `hook` | `log_warning` etc. | **SPLIT.** `config_divergence -> error_log` is a genuine upward violation (config reaching into runtime) — real, fix by inversion. `hook -> error_log` is intra-runtime and is the ideal picture's "record" — **bookkeeping**. |
| `log_writer` <- `hook` | `LogRecord`, `log_command`, `log_discovery` | **BOOKKEEPING.** The entry point writes the audit log. That is what "runtime = record" means. Removing it would be motion, not improvement, and costs 2,357 tests. |
| `session_warnings` <- `hook` | `issue_takeover_warning` | **BOOKKEEPING.** Same: "externalise". |
| `subagent` <- `hook`, `tools.transcript_harvest` | `identify_current_agent`, `parse_jsonl_lines` | **REAL but small and untested.** `subagent` has no `main()` and is not an entry point — it is a transcript-parsing library mislabelled into `runtime`. Its `tools.transcript_harvest` importer is the tell. |

So of the nine reported items: **1 is out of scope, 3 are bookkeeping forced by a wrong predicate, 4 are real, 1 is real-but-deferred.**

---

# 5. The `hook <-> tools.decision` cycle: what moves, and which way

**Both directions must go, in different steps, for different reasons.**

## `tools.decision` must stop importing `hook` — now, and it is nearly free

**DEMONSTRATED.** `tools/decision.py:36` is `from toolguard.hook import FILE_PATH_TOOLS`. `hook.py:51` is `FILE_PATH_TOOLS = FILE_TOOLS` — a **bare alias** of `toolguard.constants.FILE_TOOLS`, a foundation-layer `frozenset({"Read","Write","Edit"})`. Three sibling tooling modules (`tools.transcript_harvest`, `tools.log_harvest`, `tools.mining`) already import `FILE_TOOLS` from `constants` directly. This edge is not a design decision; it is an alias that leaked.

The argument from purpose is decisive and does not need the layer map. `tools/decision.py`'s own docstring says it is the "**side-effect-free** decision primitive for toolguard tooling" whose point is that "all logging, stdin/stdout, and `sys.exit` live in `toolguard.hook.main`". A module whose entire reason to exist is that it does not touch the process entry point should not import from it. That it does so for three string literals makes the case unarguable.

**DEMONSTRATED cost: zero.** I applied it (`from toolguard.constants import FILE_TOOLS as FILE_PATH_TOOLS`) and the suite ran **2,355 OK**, R5's non-leaf list dropped to 6 with `hook` gone, and the `tools.decision <-> hook` cycle disappeared. Restored, both files sha256-verified.

## `hook` must stop importing `tools.decision` — but that is R6's move, not R5's

**DEMONSTRATED, and this reframes the whole edge:** `decide()` is **not on the live permission path**. I ran `toolguard.hook.main()` twice in a subprocess and checked `sys.modules`:

```
normal PreToolUse path : DECISION_IMPORTED=False
--eval path            : DECISION_IMPORTED=True
```

`hook.py`'s local import at line 687 sits inside `_resolve_event`, whose only caller is `_run_eval_mode()` — the `toolguard --eval` diagnostic. The main path resolves through `resolve.*` directly.

Argument from purpose: `hook`'s job is ingest / record / externalise. `tools.decision`'s job is to answer "what would toolguard decide about this?" with no side effects. `hook --eval` wants exactly that second thing, which is why it reaches for `decide()`. The resolution is **not** for `hook` to stop wanting it — the alternative is duplicating orchestration, which `tools/decision.py`'s docstring says it exists to avoid, and which would re-open the fidelity gap R1 just closed. The resolution is for `decide()` to live where both callers can legitimately reach it: the `api` layer, between `engine` and `runtime`, which the plan already specifies as R6's job and which the ideal picture already places there *precisely so that runtime consumes the same surface the tooling does*. Cost, DEMONSTRATED: **333**.

## What R5a should actually change in `hook.py`

The `# noqa: PLC0415` comment currently reads:

> Local import: toolguard.tools.decision imports FILE_PATH_TOOLS from this module, so importing decide() at module top-level would be a circular import. This documented cycle is the sanctioned exception to the no-local-imports rule.

The moment the back-edge goes, **that justification becomes false**, and a stale sanctioned-exception marker is worse than no marker — it is a lie that survives review because it looks like it was reviewed.

Do **not** simply hoist the import. INFERRED, and it must be measured before deciding: the hook is a per-tool-call process, so a module-level `from toolguard.tools.decision import decide` would load the tooling layer (and transitively `config`, `resolve`) on **every** governed tool call, to serve a path only `--eval` reaches. Keep it function-local, keep the `noqa`, and **rewrite the justification to the honest one**: deferred to keep the tooling layer off the hot path, pending R6 moving `decide()` to `api`. The result is one clean, machine-visible layer violation in `--layers` (`hook (runtime) -> tools.decision (tooling)`) sitting in the open waiting for R6, instead of a cycle hidden behind a comment that no longer describes reality. DEMONSTRATED: with the back-edge removed, `--layers` reports exactly that one violation and nothing else changes.

---

# 6. Gaming moves, named in advance

Per stage: how to satisfy the predicate without improving anything, and what the predicate would have to become to see it.

- **R5a (cycle).** *Game:* replace the module-level `from toolguard.hook import FILE_PATH_TOOLS` with `importlib.import_module("toolguard.hook").FILE_PATH_TOOLS`, or a function-local import inside `_decide_bash`. The first is invisible (**I-5, DEMONSTRATED**); the second is visible today (`is_local` edges are counted) but a reviewer may wave it through as "the sanctioned pattern". *Detector:* flag `importlib.import_module`/`__import__` with a `toolguard.*` string literal. *Honest test:* the fix must **delete** `hook.py:51`'s alias, not route around it — if `FILE_PATH_TOOLS` still exists in `hook.py` after R5a, the coupling was renamed, not removed.
- **R5a (hook side).** *Game:* pass `decide` into `_resolve_event` as a parameter from `_run_eval_mode`, or stash it in a registry dict. Edge gone, coupling identical. **I-6, DEMONSTRATED invisible.** *Detector:* none structurally — this must be an explicit judge question: *"is the dependency gone, or only its spelling?"*
- **R5b / R5c (script and entry-point splits).** *Game:* create `toolguard/scripts/_migrate_lib.py` (or `toolguard/update_check_lib.py`) that is a pure re-export of the same functions, and have the importers point at it. Predicate green, one more file, same coupling. This is the pass-through-facade move the plan already prohibits for R6 under a different name. *Detector:* the new module must have real content — apply the plan's own §4 test (*what to do* vs *how to do*, and would it change every time the underlying code changes). Mechanically: assert the extracted module contains function *definitions*, not only `import`/`from` statements.
- **R5b (auto_migrate).** *Game:* wrap the line-174 local import in `importlib`, killing the `--layers` violation without moving anything. **I-5.**
- **R5d (config_divergence).** *Game:* keep the write, but call it through a callback the caller injects. **I-6.** *Honest test:* after the change, `config_divergence` must have **no** path to a filesystem write, checked by execution, not by import.
- **Whole-step, cheapest of all.** *Game:* edit `.pyscn.toml`. **DEMONSTRATED: 3 lines, 0 Python, 7 non-leaves -> 2, 147 architecture tests still OK.** *Detector:* fix the predicate to read `pyproject.toml [project.scripts]` (recommendation 2). Until that lands, this move is available and undetectable, and it is the single most likely way R5 "passes" without work.
- **Latent, all stages.** *Game:* add a re-export to `toolguard/__init__.py`, which is not a graph node. **I-8, DEMONSTRATED.**

---

# 7. Predicted acceptance numbers, and which to trust

For **R5a-0 + R5a + R5b + R5d**.

**Trustworthy** (each demonstrated directly, or a direct sum of demonstrated numbers):

- Suite: **2,355 -> 2,355 + n**, all OK. R5a alone is demonstrated at exactly 2,355 OK.
- Tests requiring edits: **~122** (0 + 88 + 34). Cumulative, not additive across a shared file, so treat as an upper bound.
- `--layers` violations: **3 -> 0**. R5a removes nothing here (it removes the *cycle*, not the `hook -> tools.decision` violation, which R6 owns) — so more precisely **3 -> 1**, with the survivor being `hook (runtime) -> tools.decision (tooling)`, deliberately left visible. DEMONSTRATED at each step.
- Import cycles in scope: **1 -> 0**. DEMONSTRATED.
- R5 non-leaf count under the **corrected** predicate: **4 -> 1** (`hook`, `scripts.migrate_permissions`, `update_check`, `session_start`→ the first two fixed, `update_check` deferred, `session_start` already a leaf). Under the **current** predicate: 7 -> 4, still FAIL, which is I-9/I-3 and not a finding about the work.
- Corpus: **6,401 + 61, no differences.** `--guard` **PASS 12/12.** Both are behaviour-preservation checks and R5 is a pure structural step, so a change in either is a bug, not a result.
- `hook.py` shrinks by the alias and the three-line stale comment; `FILE_PATH_TOOLS` occurrences in `toolguard/` go **3 -> 0** (hook:51 def, hook:696, hook:1282) — a countable, gaming-resistant number, since the point of R5a is that the alias ceases to exist.

**Not trustworthy — do not lean on these:**

- **Enrichment footprint.** Established unreliable across tuple->dataclass conversions ([[TOO-45 decision log]], "The acceptance instrument failed"): it counts identifiers, so it cannot distinguish coupling removed from coupling made visible. R5 moves *imports*, not enrichment, so it should not move at all — and if it does, that is an artefact, not evidence.
- **Raw R5 predicate PASS/FAIL**, until recommendations 1 and 2 land. It reports FAIL for every reachable outcome.
- **`--layers` violation count as a proxy for improvement.** Two of the three violations are closed by moving code; the third would be closed just as well by an `importlib` call. The count is a floor, not a measure.
- **Broken-test counts as a difficulty proxy for `subagent` (1) or `log_writer`/`error_log` (2,357).** The first is low because nothing tests it; the second is high because of one monkeypatch in a test helper. Neither number is about the code.

---

# 8. Restoration record

Every mutation reversed and verified:

- `.pyscn.toml` — sha256 `2555bf9d714804e584254f8dc479dd370aef2c1f937be07dc2dcce24f627eaca`, matched after restore.
- `toolguard/tools/decision.py` — `98a0f52114cb7c91bab7f9e207c0e022fd7fce69b503684c97f52adeea8f06ef`, matched.
- `toolguard/hook.py` — `5488f9c6cb50b7f5601f4dabff1a2aa9c8f57c880c4a88c671fe40b564ce766c`, matched.
- 14 rename probes and 8 module-move probes: every touched file restored from backup, `sha256 verified: True` printed for each; the moved `.py` files renamed back and re-hashed. `git status --porcelain | grep -i r5probe` returns nothing.
- **`git status --porcelain` = 80 lines, identical to the 80 at start.** Suite **2,355 OK**. `ruff check --no-cache` **All checks passed**. `--guard` **PASS, 12 canaries**.
- No `git checkout`/`restore`/`stash`/`reset` or any other git write was issued at any point.

Probe scripts preserved (outside the repo) so any number can be re-run: `scratchpad/r5_edges.py`, `r5_instrument_probe.py`, `r5_entrypoints.py`, `r5_blast.py`, `r5_move.py`, `r5_hook_path.py`.

## Relations

- part_of [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 decision log]]
- relates_to [[TOO-45 R1 scoping trace]]
- relates_to [[TOO-45 delta - as-is against ideal]]
- relates_to [[TOO-45 ideal picture]]
