---
title: Severity ordering in the audit reports is unpinned in every test that claims
  to pin it
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/28-audit-severity-ordering-is-unpinned-everywhere
---

**FIXED in `05f786d` (TOO-45 phase 2).** Severity ordering is now pinned by tests across the modules that claim it — see `test/unit/test_tools_danger.py:225,250,268` — with one cosmetic residual: the `f.tool` tiebreak is still unobservable.

> **UPDATE 2026-08-12, test-repair campaign — `tools/danger.py`'s ordering is now pinned, and this ticket's own framing needed a correction.**
>
> Measured before / after repair of `test_tools_danger.py`:
>
> | mutation | before | after |
> |---|---|---|
> | delete the sort | **0 failures** | 4 |
> | reverse the sort | 1 | 3 |
> | constant sort key | **0 failures** | 4 |
>
> **This ticket's table says "test that claims to pin it: none" for `tools/danger.py`. That is wrong, and the truth is worse.** `test_findings_sorted_critical_first` existed and its docstring claimed exactly that. It survived delete-sort and constant-key because its fixture listed the CRITICAL pattern first, so insertion order already satisfied it — and every assertion sat inside `if len(findings) >= 2:`. **An ordering test existed and was misleading, which is worse than absent**, so remedy line 3 ("add an ordering test at all") understates the work.
>
> It is also another instance of the cannot-fail / cannot-distinguish conflation flagged in ticket 31's UPDATE: this test *does* fail under reverse-sort. It was filed in the wrong category, in the section that documents the category.
>
> **The fix now requires a fixture written in ascending severity**, so insertion order cannot accidentally satisfy the assertion — that is the reusable part for the other two modules this ticket names.
>
> **Production finding: the `f.tool` component of the sort key does no work.** Dropping it produces zero failures even after repair, while dropping `f.pattern` produces one. `discover_tools` already returns names sorted and `_audit_tool` appends tool-by-tool into a stably-sorted list, so `f.tool` can never reorder anything. The docstring's "sorted by descending severity, then tool, then pattern" names a component that is unobservable through the public API.

# Severity ordering in the audit reports is unpinned in every test that claims to pin it

**This ticket exists only because three findings were read together.** Each was filed separately, by a different agent, on a different day, as "one weak test." Individually none of them justifies work. Together they say the audit tools' severity ordering has **no coverage anywhere**, and a reversed sort would ship silently.

## What is unpinned

| module | test that claims to pin it | why it cannot fail |
|---|---|---|
| `tools/takeover_audit.py` | `test_findings_sorted_critical_first` | the fixture yields **two CRITICALs** (`[4, 4]`), not the CRITICAL-and-HIGH its docstring claims -- `ignored_allow_patterns=[]` does not clear the hardcoded default-ignored seed in `Configuration.takeover_mode()`. A same-value comparison cannot verify cross-severity ordering |
| `tools/security_audit.py` | `test_sorted_severity_descending` | `_mixed_config()` yields **three CRITICALs**. `sorted(values, reverse=True) == values` holds for *any* order, including a reversed one |
| `tools/danger.py` | none | `findings.sort()` was already on the mutation tier's zero-detection list |

Both test cases were confirmed by mutation in an out-of-tree copy: flipping `security_audit`'s sort key direction produced **zero new failures across all 2,733 tests**.

## Why it matters

Severity ordering is the whole ergonomics of a security report. The user reads the top of the list and stops. A reversed or broken sort buries CRITICAL findings under LOW ones, and the report still looks complete, still lists everything, and passes every test that exists.

It is also the kind of thing a refactor breaks by accident -- a change of sort key, a switch from `sort()` to `sorted()`, a tuple reordering -- and there is nothing to catch it in three separate modules.

## The fix is small and the same in all three places

The fixtures need **mixed** severities. That is the entire defect: every fixture in this area happens to produce one severity level, so every ordering assertion is trivially satisfied.

1. `takeover_audit`: build a fixture that genuinely produces one CRITICAL and one HIGH. Note the trap that produced this -- passing `ignored_allow_patterns=[]` does *not* give you an empty ignore list, so a fixture written to be "clean" silently is not.
2. `security_audit`: give `_mixed_config()` findings at two or more severities, which is what its name already promises.
3. `danger`: add an ordering test at all.

Then assert the **positions**, not that a sorted list equals itself.

## The meta-point, which is the reason this is a ticket and not a queue row

Three agents found these across three files and three days. Each wrote "here is one weak test" and moved on. **None could see that the other two existed**, so none could see that a whole behaviour is uncovered across a whole subsystem.

That is the same failure this sweep found in `issue_takeover_warning` (two vacuous tests, filed separately, together meaning zero coverage) and in `touch_set_score.main` (two guards, each undetected alone because one test trips both). Same structure at three scales: within a function, within a behaviour, across a subsystem.

It is the argument for a synthesis pass being a **step** rather than something hoped for, and it is material for **TOO-52**.

## Provenance

`reports/follow-up-queue.md` sections `CTA` (takeover_audit), `SEC` (security_audit), and the mutation tier's undetected-mechanism list (danger). TOO-45 #07, 2026-08-11 to 08-12.
