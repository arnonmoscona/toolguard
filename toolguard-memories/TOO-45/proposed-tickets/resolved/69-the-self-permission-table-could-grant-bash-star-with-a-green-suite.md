---
title: The self-permission table could grant Bash(*) with a green suite, and the module
  that writes it is a tautology
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/69-the-self-permission-table-could-grant-bash-star-with-a-green-suite
---

**FIXED in `05f786d` (TOO-45 phase 2).** A mutation probe (4/36/76 seeded failures, all detected) confirms the self-permission table can no longer grant `Bash(*)` undetected; one decision is still deferred to TOO-36.

# The one dangerous field in the table had no assertion anywhere

**Found 2026-08-13. Measured through the real engine, not inferred. Five RED-turned-green guards now in the tree, plus one intended RED.**

## The defect

`_SELF_PERMISSIONS[*].pattern` is written **verbatim** into the user's config by `installer.cmd_seed_self_perms` (`installer.py:822`, as `(f"Bash({p.pattern})", p.list_type)`).

**No test in `test_tools_self_permission.py` asserted the `pattern` field at all.**

So the field that becomes a permission rule in the user's config was unguarded. Measured with `pattern` mutated to `"*"`:

```
rm -rf /   ->   allow      (matched_rule='*')
```

A **tool-wide Bash grant**, seeded by toolguard's own installer, with the suite green.

**Five widening/narrowing mutants, 0 of 5 detected at HEAD; 5 of 5 after repair.** The others: `pattern=""` (grants nothing — the rule is silently useless), `"rm -rf:*"`, `maintain -> "*"`, and `"toolguard:*"`, which is interestingly a **narrowing** rather than a widening — DEFAULT prefix matching is token-guarded, so it stops permitting `toolguard-audit` and starts permitting the bare hook binary.

## Why the installer's own tests could not catch it either

`test_tools_installer.py:1200,1310` builds its expectations by **iterating `required_self_permissions()`** — the very table under test. **It is a tautology with respect to widening: it would seed `Bash(*)` and assert that `Bash(*)` was seeded.**

This is the shape worth naming beyond this ticket: *a test that derives its expected value from the code under test cannot detect a change in that value.* It looks like thorough coverage — it iterates every entry — and it is structurally incapable of failing for the reason that matters.

The widening assertion now lives in `test_tools_self_permission.py`, driving `toolguard.api.decide` against a must-not-admit witness set.

## Ticket 57's shape is reproducible here, also at zero detection

One value, **three independent reads**: `_status_for` interpolates `permission.pattern` into the displayed recommendation, `_self_permission_to_dict` emits it separately, and the installer reads the field directly.

Four mutants, **0 failures each** at HEAD:

| mutant | effect |
|---|---|
| D1 | the recommendation names `command` instead of `pattern` |
| D2 | the dict emits `"*"` |
| D3 | the dict emits `list_type="allow"` for the **mutating** tool |
| D4 | the dict drops the key entirely |

All four now detected, by `assertEqual(payload["permission"], dataclasses.asdict(status.permission))` plus `assertIn(f"Bash({pattern})", recommendation)`.

## Two structural observations that make this recur

- **`_status_for` branches on `risk`, never on `list_type`.** The two can silently disagree — and `list_type` is what the installer writes, while `risk` is what the recommendation is computed from. Only one literal check coupled them.
- **`_SELF_PERMISSIONS` is read directly by `evaluate_self_permissions`, not through `required_self_permissions()`.** A caller patching the accessor gets a report that disagrees with the evaluation. Not exploitable today; it is ticket 57's two-variable defect one refactor away.

## CONFIRMED IN THE SIBLING TOO, the same evening

`uninstall_readiness.py` has the identical defect. Mutating the `uninstall the package` entry's `pattern` to `"*"` survived its whole module at HEAD; measured through the real engine, `rm -rf /` -> **`allow`**, `matched_rule='*'`. Written verbatim into the user's config by the same writer (`installer.py:833`), and `test_tools_installer.py:1225` is the same tautology as its twin.

**Mutation score there: 5 of 22 surviving at HEAD -> 1 of 23 after repair, and that one is proven equivalent** (the serializer emitting a literal `"allow"` for `list_type`, proven by exhausting the table — `{p.list_type for p in table} == {"allow"}` — and confirmed non-vacuous by a second mutant emitting `"ask"`, which 8 subtests kill).

Both ticket-57-shaped mutants survived there as well: the recommendation naming `permission.probe` instead of `permission.pattern`, and naming the **ASK** list while `list_type` says allow.

**Fix both tables in one change.** `_status_for` is duplicated across the two modules with **divergent risk-awareness**, and UR-R1's proposal to merge them would make the `list_type` blindness reachable — so the merge and the guard want thinking about together.

## The fifth generator in a row

`self_permission.py` and `uninstall_readiness.py` are the same module twice, and `recommended_protections.py` is a degenerate third. **All three generate rules.** All three now have guards — but the third turned out to be a **different story, and my assumption that the tautology was systemic was wrong.**

**`recommended_protections` never had this defect.** Every single-field weakening was killed, and its installer-side test (`test_tools_installer._EXPECTED_HARD_DENY_PATTERNS`) owns an **independent 16-entry literal** rather than iterating the table under test — so it is genuinely pinned, not the tautology that made `test_tools_installer` useless for the two siblings above.

What it lacked was the **protections-direction analogue**: not "grants too much" but **"denies too little"**. Six patterns naming a whole family (`.ssh/**`, `.aws/**`, Read and Write, both anchoring forms) were each pinned by exactly **one** witness file, so narrowing the family to that witness was invisible. Before the fix, a config narrowed that way passed every test while leaving `~/.ssh/id_ed25519`, `~/.ssh/config`, `~/.aws/config` and `~/.aws/sso/cache/*.json` — **live SSO tokens** — fully readable and writable. Closed by a 10-witness test, each differing from the existing probe in **both filename and directory depth**, proven non-vacuous by 8 distinct mutants.

**That hole was only visible at tier C** — see the tier note in `TOO-45 test-repair plan.md`. A naive sweep reported zero survivors here, and the zero was an artifact of the module having three declared sources of truth.

**One minor production observation**: `RecommendedProtection.rationale` is consumed by nothing — not by `installer.py`, which reads only `.pattern`, nor by any doc or skill. A documented display field with no display path; only a test asserts it is non-empty.

Preceded by unguarded safety gates in **consolidate**, **redundancy**, **maintenance** (ticket 57) and **architecture_fitness** (ticket 66).

## Related — an open decision, not a defect

`test_every_console_script_a_skill_invokes_is_declared` is **intentionally RED**:

```
{'toolguard-install': ['skills/toolguard-maintenance/SKILL.md:72']} != {}
```

`toolguard-install skills-status --format json` is the maintenance skill's **pre-flight, before pass 1**, has no entry in `_SELF_PERMISSIONS`, is never seeded, and falls to `no_match_fallback` under takeover. Queue item UR2, now falsifiable — the test derives its expectation by parsing fenced command-position invocations out of `skills/*/SKILL.md` against `pyproject.toml`'s `[project.scripts]`, so it stays correct as skills change.

**Fixing the table will also fail `test_only_audit_and_maintain_are_declared`**, which must be updated in the same edit. The two tests disagreeing *is* the open decision: an `ask` entry, a narrow `toolguard-install skills-status:*` pattern, or accepting the prompt. **Arnon's call.**

## And a note on how it was found

`follow-up-queue.md:1273` reviewed this file **by reading** and reported one minor redundancy. Mutation found **13 of 25 mechanisms at zero detection**, including the entire `pattern` field. Second instance the same evening — the read-only pass over `file_lock` recorded three comment findings and zero mechanism findings while mutation found five. **A queue entry being right is not the same as it being complete.**
