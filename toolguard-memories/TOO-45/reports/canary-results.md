---
title: TOO-45 canary results
type: note
permalink: toolguard/too-45/reports/canary-results
tags:
- task-memory
- TOO-45
- canary
- report
---

# Canary results — four requirements, both trees

Four small requirements, each implemented independently in pre-TOO-45 master (`532de02`) and post-R6 branch (`708a720`) by separate agents that saw one tree only and were never told what was being measured. Predictions were registered before any implementation ran: [[mr07-preregistration]], [[boundary-canaries-preregistration]].

## Results

| canary | probes | outcome |
|---|---|---|
| **MR-07** project-root marker | duplication of a primitive | **null** — one-line functional change in both, identical file sets |
| **MR-10** NotebookEdit as a governed tool | is a tool a described thing or scattered membership tests | **null** — same sites, same fix shape, same defect found in both |
| **MR-12** compound part N of M | is the sub-result collection modelled or reconstructed | **branch wins clearly** |
| **MR-08** `TOOLGUARD_LOG_FORMAT` | is env config one object; how many log write sites | **master looks easier and is WRONG** |

## MR-12 — the clean win, and why it is not circular

| | master | branch |
|---|---|---|
| production/doc files | 5 | 3 |
| test files | 4 | 2 |
| layers threaded | 4 (`compound`→`resolve`→`hook`→`log_writer`) | 2 (`hook`→`log_writer`) |
| signature changes | return tuple widened, 2 fields added to `BashResolution` | none |
| source of the total | `len(structured)` + an extra O(n) rescan | `len(verdict.sub_matches)` |
| self-rated difficulty | fiddly | straightforward |

**The mechanism is the finding, not the counts.** In master, the obvious source of the total is a **trap**: `sub_matches` silently omits `UndecidableSegment` entries, so a compound containing process substitution would undercount. Master's implementer caught it only by investigating, and rerouted through four layers. In the branch, `sub_matches` is correct — TOO-45 R1e made `compound.py` record a `UnitVerdict` for **every** leaf and segment, including escape-hatch ones that never call `resolve_one` (`resolve.py:552-560`).

So the branch was easier **because the obvious path had been made the correct path.** That is what "absorbs change well" means stated mechanically rather than aesthetically.

**And it clears the home-ground objection registered against it in advance.** R1e's repair was about *decision correctness* — attributing a compound's deny to the right leaf. MR-12 needs a *count*. Different consumer, different purpose, same repair: the benefit generalised from what the fix was for to something nobody had in mind when making it. That is precisely the property the neutral-ground canaries were supposed to test and structurally could not.

## MR-08 — the reversal that inverts on inspection

Master: 3 production/doc files, self-rated **straightforward**, `hook.py` untouched. Branch: 6 files, self-rated **fiddly**, forced to relocate two constants into `constants.py`.

Master's implementation added `env_config.py:12  from toolguard.log_writer import normalize_log_format` — a **config → runtime upward dependency**. `.pyscn.toml:178` places `env_config` in `config`; `:194` places `log_writer` in `runtime`; the order is `foundation < config < engine < api < runtime`. Master has that layering intent recorded and **no reachable check**, so nothing objected. The branch's implementer discovered the constraint by running `tools/architecture_fitness.py --layers` before wiring anything, and paid three extra files to route the shared constants down into `foundation`.

**So "straightforward" was straightforwardly wrong.** The two branch wins arrive by different mechanisms — MR-12 makes the correct path obvious, MR-08 makes the incorrect path impossible.

## What MR-08 actually exposed: `log_writer` was in the wrong layer (FIXED)

Arnon's reading of the MR-08 result, on general principles and before looking at the code: logging and configuration are both **cross-cutting concerns**, so both belong low and importable from almost anywhere; and an apparent dependency of logging on configuration can be satisfied by **injection** rather than by import. He asked whether the branch had mis-organised this. It had.

Verified:

- `log_writer.py` imported **exactly one** thing from toolguard — `from toolguard.config import find_project_root` — and that is a thin wrapper over `path_utils.resolve_project_root`, already in `foundation`.
- Configuration reached `log_writer` by **injection already**: `_logging_enabled(config)`, `_log_dir_from_config(config)`, `_resolve_log_dir(log_dir, config)` all take a plain dict parameter. Arnon's distinction was exactly right; the import was the only thing making it look otherwise.
- `error_log.py` and `session_warnings.py` import **nothing** from toolguard. `update_check.py` imports only foundation. All three already satisfied the map's own definition of a foundation leaf.
- The `runtime` layer's own comment named the error: *"Entry points and side-effecting session/logging concerns."* Two unrelated criteria in one layer. `hook`/`session_start` belong high because they **orchestrate**; the other four were there because they have **side effects**, which is orthogonal to dependency direction.
- **The measured cost: 16 hand-rolled `stderr` writes across four config-layer modules** — `config` 3, `env_config` 2, `auto_migrate` 6, `config_divergence` 5 — because config-layer code could not legally reach a logging or warning module. Engine has zero, which fits. The layering was not being obeyed there; it was being routed around.

**The uncomfortable part.** R6-S2 reported zero layer violations and that was reported as a clean result. It was clean because **the map encoded the wrong boundary** — a map that matches the code always shows zero violations, whether or not the code is well-layered. Those 16 bypasses are invisible to the checker by construction. Our own fitness tooling could not have found this; a change-canary did, and only because someone tried to make config-layer code reach a logging concern.

**The fix, applied:**

1. `require_project_root()` added to `path_utils` (foundation), holding the body that was in `config.find_project_root`; `config.find_project_root` now delegates to it, so the logic is not duplicated (this codebase's recurring sin) and the public name and sandbox patch path survive.
2. `log_writer` imports `path_utils.require_project_root` — **zero config-layer imports remain**.
3. New **`observability`** layer between `foundation` and `config`, holding `log_writer`, `error_log`, `session_warnings`, `update_check`. `runtime` keeps only the orchestrators: `hook`, `session_start`, `subagent`.
4. Every `[[architecture.rules]]` entry updated. The load-bearing line is `config` gaining `observability` in its allow-list — which is what makes those 16 stderr bypasses unnecessary.

Verified: **2,586 tests OK**, ruff clean, layer completeness 100%, no direction violations, R1/R2/R3/R5/R6 all PASS. One test changed — `test_api_layer_rule_allows_only_engine_and_below`, whose exact-set assertion had to grow by `observability`; its negative assertions, which carry the real intent, are untouched.

**Not done, deliberately**: consolidating the 16 stderr writes onto the real warning path. That is larger, it is a behaviour change to what users see, and it belongs in its own ticket now that the layering permits it.

## The methodological result: self-rated difficulty can invert

Subjective difficulty was pre-registered as the weakest evidence in the set. MR-08 shows it can be worse than weak — **actively inverted**. The implementer who introduced a layering violation rated the work easier than the one who avoided it, and rated it easier *because* nothing stopped them. Any future use of this measure has to treat a low difficulty rating as unexplained until the correctness question is settled separately.

## What every canary produced regardless of the comparison

Four for four, each implementer surfaced a **pre-existing product defect while not looking for one**:

- **MR-07** — `DEFAULT_INDICATORS` contains `package.json`, `CONFIG_ROOT_INDICATORS` does not. Tooling and runtime disagree about what a project is.
- **MR-10** — two hardcoded copies of the file-tools list in `tools/danger.py` (lines 305, 366), wired to no shared constant. **Both** implementers found them, and **neither by following code** — only by grepping literal tuples.
- **MR-08** — `log_writer.py` disagrees with itself about the default format (line 449 vs 465), latent today and live the moment the format becomes selectable; and `tools/log_harvest.py` matches the resolution log by `.md` filename only, so the retained JSONLines renderer cannot be enabled without silently emptying corpus harvest, mining and replay.
- **MR-12** — `docs/architecture.md` still documents master's folded-provenance behaviour as current; the `sub_matches`/`UndecidableSegment` gap in master.

All of it now on [[pre-push-punch-list]].

**This is the strongest general result of the whole exercise, and it was not what the experiment set out to measure**: implementing a plausible small requirement is a better defect-detector than reviewing the code. Every defect above sat in code that had already been read by seven directed report agents, one blind reviewer, `pyscn`, `ruff`, and 2,586 passing tests.

## Prediction scoring

| canary | predicted | actual | verdict |
|---|---|---|---|
| MR-12 | branch wins clearly, biggest discriminator | correct | **right**, but the mechanism was wrong — I expected prose-parsing to bite; the real bite was a silent undercount in a collection that *looks* usable |
| MR-10 | near-null | null | **right** |
| MR-08 | small-to-moderate branch edge | master easier, and wrong | **wrong** |
| MR-07 | null | null | **right** |

Three of four directionally right, one wrong, and the one I was most confident about was right for the wrong reason. My ranking (MR-12 > MR-08 > MR-10) held at the top and inverted at the bottom.

**Calibration conclusion**: my intuitions about where this codebase is weak are worth something and are not worth trusting unverified — which is the same conclusion the instrument work reached by a different route.

## Honest limits

- **n = 4.** No claim of significance.
- **Two of four are nulls**, and one win came from ground the refactor targeted, though for an unanticipated consumer.
- **Implementer variance is uncontrolled.** Different agents, different thoroughness — MR-10's master implementer ran manual end-to-end smoke tests, its branch implementer did not.
- **The MR-08 doc confound**: `docs/architecture.md` already names `TOOLGUARD_LOG_FORMAT` as the planned selector, making that requirement unusually easy for anyone reading docs first. Symmetric across trees, so it dampens rather than biases.
- **No mechanical measure was used for any of this.** Every finding above came from implementer prose and from my own verification against the live repo. The four instruments built earlier contributed nothing to these conclusions.
