---
title: The takeover audit stays silent on an effectively loose fallback, cries wolf
  on a hardened one, and hides a cross-level conflict unless a blanket allow happens
  to exist
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/61-takeover-audit-reads-the-legacy-alias-and-conditionally-hides-a-conflict
---

**PARTIALLY FIXED in `05f786d`.** Defect 1, the dangerous one, is fixed — `toolguard/takeover_audit.py:394` now reads the resolved fallback; still open: defect 2, a conflict reported only alongside a blanket allow (`:329`), and defect 3, a false impact string (`:371`).

# The audit is wrong in both directions, and its conflict report is conditional

**Found 2026-08-13. Two RED tests in the tree. This is queue row TK2, executed.**

## Defect 1 — invariant 4 reads the legacy alias, not the effective value

`audit_takeover`'s invariant 4 reads `takeover.no_match_fallback` — the **legacy alias** — instead of `config.resolved_no_match_fallback()`. Both directions are wrong:

| config | effective fallback | audit says |
|---|---|---|
| top-level `"allow"` + section `"deny"` | **`allow`** — loose | **silent** |
| top-level `"deny"`, no section | **`deny`** — hardened | **LOW finding**, and its description prints `'ask'` |

**A false negative on the loose case and a false positive on the hardened one**, from one expression.

**Mutating toward the fix** (`config.resolved_no_match_fallback() != "deny"`) turns exactly the two RED tests green with **zero collateral** in the module. Before the repair, that same fix produced **zero failures** — the module saw neither the bug nor its correction.

## Defect 2 — a cross-level `enabled` conflict is only reported when a blanket allow happens to exist

`takeover_mode()` builds the conflict and `hook._log_takeover_enabled_conflict` records it — but **`audit_takeover` surfaces it only when native blanket allows are present.**

**A configuration with a genuine cross-level disagreement about `takeover_mode.enabled` and no blanket allow gets a completely clean audit.** The conflict is detected, logged, and then withheld from the one report a user runs to check whether takeover is configured safely.

Not pinned as RED — whether the audit *should* report a conflict independent of blanket allows is a product decision, not an obvious defect. But the current behaviour is almost certainly not what a reader of "clean audit" would assume.

## Defect 3 — TK1: an impact string that is false in every reachable config

`uncovered-blanket-allow`'s impact text says the allow *"remains live in the permission evaluation."* Measured: `permission_layers` returns `allow=()` for it — **it is stripped at runtime**, so the sentence is false wherever the finding can appear. Decide TK1's (a)/(b) before touching either side.

## What the module could not see

- **12 defensive type guards in the hooks/permissions walks had zero detection.** Removing any of them makes the auditor **raise** on a hand-edited `settings.json` (`"hooks": "yes"`, `"permissions": []`, a dict inside `allow`). **A crashed audit is a report that never happened** — the most complete form of ticket 29's shape. Closed by 9 malformed-input shapes × 2 tests. Three of them initially failed to detect their own guard because a **neighbouring guard masked it**; fixed by using non-iterables.
- **Ticket 29's shape confirmed a ninth time**: emptying `governed_set` — the audit examines zero tools — left the clean-report tests green.
- **The ON/OFF pair explicitly named for the switch varied three things at once** — `enabled`, `ignored_allow_patterns`, and the native allow list — so no observed difference was attributable to the switch. Ticket 47's second hazard, in a third module. Now both draw from one builder that varies `enabled` alone.
- `test_findings_sorted_critical_first` had a **false Given** ("both CRITICAL and HIGH findings") over a fixture producing `[4, 4]`, so `4 >= 4` could never distinguish ascending from descending.

Mutation: **7 of 26 survivors → 0 of 30** behaviour mutants, plus 12 of 13 guard mutants now detected and the 13th proven equivalent.

## A correction to my own brief, recorded because the mistake is instructive

**I told the agent ticket 59 (`per_layer_rules` drops native `ask`) lands on this module. It does not** — `takeover_audit.py` imports no `config_access` and never reads `permissions.ask`.

Worse, **the working queue's own note said "not applicable" and my brief contradicted it.** I generalised a fresh, vivid finding across a boundary I had not checked, and overrode a correct note to do it. That is the same failure this campaign keeps documenting in the other direction — and the agent caught it by reading the code rather than the brief.