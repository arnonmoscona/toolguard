---
title: Every MCP-terminal decision could lose its reason, matched rule and provenance
  - and hard-deny could stop applying to MCP terminals entirely - both undetected
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/65-mcp-terminal-decisions-could-lose-provenance-and-hard-deny-undetected
---

**FIXED in `05f786d` (TOO-45 phase 2).** Test blindness closed; production MCP-terminal provenance handling was never actually broken — see `test/unit/test_api.py:963`.

# `api.decide()` is the seam every consumer shares, and two of its mechanisms had no detector

**Found 2026-08-13. Not live defects — the code is correct. The finding is that either could break silently, on the one function both the hook and all tooling go through.**

## 1 — Ticket 31's prediction, reproduced exactly

> *"`api._decide_bash`'s tool override — it can null `reason`, `matched_rule` and `provenance` on every MCP-terminal decision with nothing failing."*

Measured. `dataclasses.replace(result, tool=tool)` → `dataclasses.replace(result, tool=tool, reason="", matched_rule=None, provenance=None)`: **0 newly-failing tests of 27.**

Every MCP-terminal decision could lose its explanation, its matched rule and its provenance — so the user sees no reason and the audit trail records no attribution — with a green suite.

Now held by asserting `dataclasses.replace(overridden, tool="Bash") == baseline`, where the baseline comes from `resolve_bash_permission_detailed` directly. **2 detectors.**

## 2 — Worse, and not previously predicted: hard-deny could stop applying to MCP terminals

`_decide_bash` looks the hard-deny pool up under the hardcoded string `"Bash"`. That single expression is **the only thing keeping MCP terminal tools inside the unoverridable-refusal pool.**

Mutating `config.hard_deny(tool)` **survived** — so **hard-deny could silently stop applying to every MCP terminal tool.** No test anywhere exercised an MCP-terminal tool through `decide()` against a Bash `hard_deny`. Now covered.

`hard_deny` is the mechanism documented as absolute. This is the third place in the campaign where its enforcement turned out to rest on something nothing was watching.

## A routing name that must not drift

`hook.py` routes on **`FILE_PATH_TOOLS`**; `api.py` routes on **`FILE_TOOLS`**. Both resolve to `tool_spec.FILE_KIND_TOOLS` today — **two names for one routing decision, across the seam whose entire purpose is that the two agree.**

## A test that passed *because of* a defect

The existing hard-deny carve-out test used `Bash(rm -rf /tmp:*)`, and **its expected outcome was reachable only through ticket 18's over-match** — the trailing `*` glues onto `/tmp` with no separator, so `rm -rf /tmpfoo` is exempted too.

Moved to a `[glob]` carve-out (correct, green, and survives ticket 18's fix), with the over-match added as a **RED** test: `test_hard_deny_carve_out_stops_at_the_path_boundary`.

**A green test whose correctness depends on a bug is a new shape** — it does not merely fail to detect the defect, it would *break* when the defect is fixed, and a phase-2 engineer would read that as the fix being wrong.

## Corrections

**To my own brief.** I told the agent that `resolve_file_path_permission_detailed` sets `matched_rule=None` **by design**, so shape 25's one-line remedy "does not work for file-path tools." **True only on the hard-deny branch.** The cascade branch passes `resolved.matched_rule` straight through — measured `'[glob]/home/*/project/.env'`. So the cheap remedy **does** work for file-path *cascade* denies; only hard-deny needs `check_file_path_hard_deny(...).matched_pattern`.

That is the second brief error of the same kind in two days: I took a true statement about one branch and stated it about the function.

**To the working queue.** Its fix shape at line 1949 says to assert `"Bash(rm -rf:*)"`. The measured value is `'rm -rf:*'` — **wrapper-stripped**. Following the queue verbatim would have produced a false failure.

## An inert mock, and a self-caught vacuous test

`_IsolatedEnvTestCase`, the base of six classes, was **inert**: with a hostile `CLAUDE_SETTINGS_PATH` live *and* the base neutered, **zero tests changed**. Nothing reachable from `decide()` reads that variable — `config.load_configuration` does, and `decide()` takes an already-built `Configuration`. Removed.

And worth recording as method: the agent's **own first rewrite** of `test_decide_does_not_write_to_log_files` **also could not fail**, because of test-order pollution — an earlier test created the probe file before the snapshot. It was caught **by running the falsification, not by reading the code.** The campaign's central rule, applied by an agent to its own work.

Module result: **5 of 12 mutants surviving → 0.**