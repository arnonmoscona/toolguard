---
title: 89-scored
type: note
permalink: toolguard/too-45/reports/surprise/89-scored
---

# Ticket 89 scored - inert word-boundary regex in double-quoted TOML

Commit `52be738` (toolguard repo). **Note: this ticket's file set SPANS TWO REPOSITORIES** -- see below, it is the most interesting thing about the measurement.

## Production files - the headline metric

| | |
|---|---|
| predicted | `toolguard/config.py` (1), upside 2 |
| actual | `toolguard/config.py`, `toolguard/config_validation.py` (2) |
| **production recall** | **2/2 = 100%** -- the upside case landed |

I predicted "1, upside 2 if the `[regex]` body is compiled somewhere that also needs to know". The second file is `config_validation.py`, which is not quite the reason I gave -- it holds the *predicate*, parallel to the existing `find_hard_deny_entry_issues`, while `config.py` holds the *checker* that ticket 94 split out. **Right count, adjacent reason.** Scored as a hit on the metric and noted as a partial miss on mechanism.

## Uncertainties, resolved

- **U1** (narrow "raw control character in a `[regex]` body" vs something broader) -- **predicted narrow, correct.**
- **U2** (the audit skill must change too, and it is documentation not production) -- **correct, and it mattered more than expected**, see below.
- **U3** (whether any rule on this machine is already inert) -- **measured ZERO** across all four real config locations, read-only, before implementing.

**U3 deserves emphasis because it resolved the way that argues AGAINST urgency.** I flagged in advance that a live dead rule would be "a finding in its own right". There was none. So this is a guard against a trap nobody has yet stepped in -- which, per `.claude/rules/evidence-before-fixing.md`, still justifies the fix: the failure is silent by construction, the reachability is accidental rather than adversarial, and **our own published guidance manufactured the shape**. That last clause is what carries it, not the count.

## THE FINDING: the file set crosses a repository boundary, and the metric cannot see it

`.claude/` in this repo is a **symlink into `~/projects/dot_files`**. So the changes to `.claude/skills/toolguard-security-audit/SKILL.md` -- *the ticket's named root cause* -- and to `.claude/skills/toolguard-maintenance/passes/2-consolidate-and-group.md` are **invisible to `git status` in the toolguard repo** and are not in commit `52be738`.

Consequences for the series, both real:

1. **The touch-set metric silently under-counts any ticket whose work reaches `.claude/`.** Two files here. Nothing in the scoring procedure would have caught it; I found it only because the implementer said so explicitly. **Every earlier ticket that touched a rule or skill file has the same hole**, and the consolidated report should say so rather than quietly present the counts as complete.
2. **The fix is not committed and cannot be by me.** Arnon does all git write operations, and the standing exception covers commits on `too-45` in the toolguard repo only. `dot_files` also carries substantial unrelated dirty state, so a blanket commit there would sweep up work that has nothing to do with this ticket.

**This is the same class as the `no_match_fallback` blind spot recorded earlier**: an instrument that reports a clean, plausible number while a whole category of change is structurally invisible to it. It is worth adding to the consolidated report's methodology section as a named limitation of the touch-set measurement itself, not as a fact about ticket 89.

## Gate note

Full suite: 3987 tests, 3 failures, all pre-existing from concurrent uncommitted `multiline.py` work; identical before and after. Corpus verify fails for the same reason. **Attribution verified independently rather than accepted**: `Configuration.validation_issues()` has exactly one call site, `hook.py:93`, where it is consumed only to route log messages by severity -- it cannot reach a decision field. Empty-`$HOME` variant: same result. Full-suite verification still owed once 98 chunk 2 lands.