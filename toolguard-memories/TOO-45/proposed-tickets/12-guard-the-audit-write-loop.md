---
title: 12-guard-the-audit-write-loop
type: note
permalink: toolguard/too-45/proposed-tickets/12-guard-the-audit-write-loop
---

# Proposed: guard hook.py's audit write loop

**Status:** deferred from TOO-45. Closes the residual half of this ticket's headline defect.

## Problem

TOO-45's headline finding was that `hook.py` reconstructed the compound breakdown by regex over reason prose, leaving **813 of 975 compound-allow decisions (83%) under-logged and 1,943 sub-commands with no audit record**.

The corpus was extended during this ticket to record `sub_matches` and `overrides` as a hard comparison tier — proven to detect loss by dropping every second recorded `UnitVerdict`, which failed `--verify` naming 992 cases.

**That guards `decide()`'s construction of the breakdown. It does not guard `hook.py::_log_allowed_command` actually writing it.** The end-to-end corpus records the hook's JSON *response to Claude Code*, and the breakdown goes to the log **file**, which nothing asserts on.

So the defect's original location — the hook writing what it was given — remains unguarded by anything standing.

## Why it is not urgent but should not be forgotten

The current implementation is correct, verified by a one-off measurement during this ticket. Nothing is broken today. The risk is a future refactor of the logging path regressing it silently, with a green corpus and 2,600 green tests.

That is precisely the situation that produced the original defect.

## Proposed

An end-to-end test that drives a compound command through the hook and **asserts on log file content**: one entry per sub-command, in extraction order, each carrying its own matched rule and provenance.

Note the existing test infrastructure already guards against writing into the **real** repo `logs/` directory (`test/unit/_real_log_dir_guard.py`), so this must use an isolated log dir via the established mixin.

## Size

Small — one test module. The infrastructure exists.

## Decision needed

Now or later? Recommend **now**, on the grounds that it is small and that leaving this ticket's headline fix unguarded while celebrating it is an unattractive combination.