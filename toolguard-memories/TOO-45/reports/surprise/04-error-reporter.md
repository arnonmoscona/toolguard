---
title: Surprise factor - item 04 (error reporter, config-layer stderr)
type: note
permalink: toolguard/too-45/reports/surprise/04-error-reporter
tags:
- task-memory
- TOO-45
- measurement
---

# Item 04 — a toolguard error reporter, and the config-layer stderr writes moved onto it

Protocol: [[surprise-factor-protocol]]. Estimate pre-registered in [[04-estimate-predictions]] (sealed, opened only after green) and [[04-estimate-uncertainties]] (read before implementing, per the protocol change made after item 01). **Blinding held on both sides.**

First item run under the two-file split, and the split is the headline.

## Actual touch set — 14 files

| group | files |
|---|---|
| production, added | `error_reporter.py` |
| production, modified | `hook.py`, `config.py`, `env_config.py`, `auto_migrate.py`, `config_divergence.py`, `log_writer.py` |
| config | `.pyscn.toml` |
| tests, added | `test_error_reporter.py`, `test_hook_error_reporter.py` |
| tests, modified | `test_configuration.py`, `test_env_config.py`, `test_auto_migrate.py`, `test_config_divergence.py` |

Verified: 2,680 tests OK, golden corpus unchanged, `--layers` clean, ruff clean, and all 8 config-layer stderr writes gone (AST-counted, same instrument used to find them).

## Scoring

`|P| = 21`, `|A| = 14`, **hits = 11**, surprises = 3, overshoots = 10.

| | raw | production only | test only |
|---|---|---|---|
| **recall** (`hits/|A|`) | **79%** | **88%** (7/8) | 67% (4/6) |
| precision (`hits/|P|`) | 52% | 58% (7/12) | 44% (4/9) |
| surprise ratio `|A|/|P|` | 0.67 | | |

**Leak discount.** The ticket names `config.py`, `env_config.py`, `auto_migrate.py`, `config_divergence.py` by path and mentions `hook.py`. Excluding those five, the honest set is 9 files and **recall on unnamed files is 67%** (6/9). That is the number to compare across items.

### FINDING 1 (Q1) — the ratio now ranks three items almost exactly backwards

| item | surprise ratio | recall | ratio rank | recall rank |
|---|---|---|---|---|
| 05 | 0.90 | 46% | 1st | 3rd |
| 04 | **0.67** | **79%** | 2nd | **1st** |
| 01 | 0.54 | 60% | 3rd | 2nd |

Three items, and the two measures are inversely ordered. The mechanism is now unambiguous: `|A|/|P|` rewards an estimator that names few files and punishes one that names many, independent of whether it named the *right* ones. Item 04 has the best recall in the series and the middling ratio; item 05 has the worst recall and the best ratio.

**This is a Q1 result, not a Q2 result.** It says the current headline statistic is miscalibrated — which is a tuning problem with a stable sign, and therefore the easy kind. `n = 3`.

### FINDING 2 (Q2) — the uncertainties half corrected the ticket's central fact before any code was written

This is the strongest structural result the experiment has produced.

Uncertainty #2 asked *"how many hand-rolled stderr writes are there really, and are any outside the four modules the ticket names?"* and supplied the grep. Following it, then measuring properly by AST, showed **8 writes, not the 16 the ticket asserts** — item #01 had already removed the rest as a side effect. The ticket's headline evidence had decayed by half and nobody had noticed.

The other three that paid off:

- **#1** *"does a usable reporting seam already exist?"* → surfaced that `error_log` writes but does not locate, and `log_writer` locates. That split is the reason for this item's only production surprise.
- **#3** *"does 'visible to Claude' mean the hook's JSON output, and is it a return value rather than a side effect?"* → correctly identified this as a **threading** problem, not a routing one. It turned out to be the hardest part of the item and the source of two of its three real defects.
- **#8** *"is there an enforcement mechanism, or should one be added?"* → answered no, and the item shipped without one. That is a live gap, recorded below.

**The estimator, seeing only filenames and one docstring line each, asked better questions about this change than the ticket did.** For the second item running, section 4 outperformed sections 1-3.

### FINDING 3 (Q2) — overshoots need causes too, and most of this item's are mine

The protocol assigns a cause to every *surprise* and none to any *overshoot*. That is a structural gap, and item 04 makes it obvious: of 10 overshoots, **5 are things the ticket raised and I cut** — `session_warnings.py` and its test (classifying the takeover notice), `architecture_fitness.py` and its test (a predicate banning hand-rolled stderr), `docs/architecture.md` / `technical-notes.md`. The estimator predicted them because the ticket invited them. Scoring them as estimator error is simply wrong.

**Proposed new category, for overshoots only: `X` — scoped out.** The ticket invited it, the implementer declined it. Not estimator error; a record of a scope decision, and the running `X` count across items is itself a useful signal about how much of each ticket actually gets built.

With `X` separated, this item's precision reads 11 hits / 16 in-scope predictions = **69%**, against the raw 52%.

### Cause assignment — surprises

| file | cause | note |
|---|---|---|
| `log_writer.py` | **E** | The reporter needs the log directory; `error_log`'s functions take one as an argument and `log_writer` owns resolving it, so `_resolve_log_dir` became public. The estimator predicted `error_log.py` for exactly this mechanism and picked the wrong one of the two modules. A case could be made for `C` — a module named for writing command logs owning the resolution another module depends on is genuinely non-obvious structure — but the honest call is that no docstring-only briefing could distinguish them, and `C` is the cause that flatters me. Recorded as `E` with the argument for `C` written down rather than suppressed. |
| `test_hook_error_reporter.py` | **E** | Right mechanism, wrong shape: the estimator predicted growing `test_hook.py`; a new file was written instead rather than adding to a 3,146-line module. |
| `test_configuration.py` | **E** | A naming trap. `config.py`'s tests live in `test_configuration.py` (3,982 lines), not `test_config.py` (307 lines). Both exist, both docstrings are plausible, and nothing in the briefing separates them. |

| cause | count |
|---|---|
| **E** — estimator ignorance | 3 |
| **C** / **P** / **D** / **S** / **R** | 0 |

**Abandon gate: does not fire.** The trigger is three *consecutive* all-`E` items. Item 05 was dominated by `P`, item 01 carried `R`; only item 04 is all-`E`. The counter restarts here.

## Complexity ratings

- **Blind judge: `high`.** Its reasoning: almost nothing in the change can be checked in isolation — verifying any converted call site means holding `error_reporter`, `error_log`, `log_writer.resolve_log_dir` and the hook's invocation scoping together at once. It also named four contract changes and found a real defect (see below).
- **Arnon: `low`.** *"Very easy to review. A bunch of trivial changes. All meaningful code changes in one module."*

**Maximum disagreement on a three-point scale, on the first item where both ratings exist.** Arnon's diagnosis — *"something is wrong with the way the blind upfront judgement is guided... not the method, but the judgement"* — is recorded in [[surprise-factor-protocol]] along with five corrections to the judge's brief. In short: the anchors led with "changes a contract or an invariant", which measures how **consequential** a change is, not how **expensive to read** it is, and the judge answered the question it was asked. Item 15 is the first test of the corrected brief.

Note the judge was not merely wrong: it found a real defect nobody else did (the handlers running outside the reporter's scope). **Useful reviewer, miscalibrated rater** — which is why the fix is to the rating brief and not to the practice of running it.

## What the two blind reviewers caught that 2,673 tests did not

Three real defects, all confirmed independently before acting on them:

1. **Faults were discarded on exactly the paths where faults occur.** `hook.py` opened the reporter's invocation *inside* the `try`, so all three `except` handlers ran after the context manager had torn it down, and they called `create_hook_output` rather than `_finalize_output`.
2. **`env_config`'s two converted sites could never reach any log**, because `get_env_config()` runs before the invocation was installed and is itself what calls them.
3. **The routing table did not own the decision it advertised.** `error_log._log_entry` echoes to stderr unconditionally, so flipping the table's `stderr` column silenced nothing. Renamed `stderr_fallback`. This is the same defect shape as item 01's `available()`: a field reporting a policy while the real behaviour lives elsewhere.

Plus a prose defect the change introduced: `log_writer._log_dir_from_environment`'s docstring claimed production never reaches it. This change made production reach it. Fixed by correcting the claim rather than inventing a mechanism — reading `TOOLGUARD_LOG_DIR` directly there would miss a `.env`-supplied override and give one setting two resolutions.

**Pattern now at three for three: blind reviewers find defects that the full suite, ruff, pyright, the layer checker and the golden corpus all miss.** The corpus is structurally blind here by construction — it compares verdict objects, so it guards what a decision *is* and never where anything *goes*.

## Known gap shipped deliberately

`report_fault` has **no production call site.** The Claude-facing buffer is exercised only by tests. This is a consequence of the scope boundary — the only genuine faults live in `hook.py`'s error handlers, which belong to the fail-open item — not a bug. Documented in the module docstring rather than papered over with invented call sites.

Also not built: any enforcement stopping a new hand-rolled `stderr` write from appearing. The ticket's stated failure mode is *"left alone they read as the convention"*, and this project's own history says prose does not prevent that. A fitness predicate is the durable answer and is worth its own ticket.

## Modified co-change `n/(n-1)`

`n = 14`, `n/(n-1) = 1.077`. Series so far: 05 `1.04` (n=26), 01 `1.07` (n=15), 04 `1.077` (n=14). The measure is `1 + 1/(n-1)` and therefore carries exactly the information already in `n`, inverted. **Three items in, the recommendation is to drop it** — it has never disagreed with the file count and cannot, by construction.
