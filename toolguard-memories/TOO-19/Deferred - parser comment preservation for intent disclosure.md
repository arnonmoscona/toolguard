---
title: Deferred - parser comment preservation for intent disclosure
type: note
permalink: toolguard/too-19/deferred-parser-comment-preservation-for-intent-disclosure
tags:
- TOO-19
- intent-disclosure
- parser
- deferred
- evidence-needed
---

## Status: DEFERRED pending evidence. Do not build.

Idea worth keeping, not worth acting on yet. Arnon's position (2026-07-31): the failure mode it
would fix is a real possibility but is **not backed by evidence**, and no evidence can exist yet
because the new announce-intent guidance has not been deployed anywhere.

## The idea

Today the PEG parser **discards comments** before rule matching. That is why the intent-disclosure
mechanism needs env-var prefixes (`TG_INTENT=1`, `TG_ATTEST_READONLY=1`) as its machine-checkable
half -- a rule cannot match on a `# INTENT:` comment block, verified 2026-07-29 in the sandbox.

The change would be: instead of discarding comments, the parser either preserves them or emits
them as their own node in the IR, so wrapper code can pass them to the decision path. That would
let the disclosure block itself be the signal, with no env-var prefix at all, and would make the
comment text available for `additionalContext` or logging.

## Why it is deferred

The argument for it rests on a **hypothesis I stated and Arnon correctly flagged as unevidenced**:
that agents will write the comment block, omit the env-var prefix, get denied a second time with
no visible reason, and be unable to see why. Plausible -- but nobody has observed it. The rate
could be near zero if the guidance names the prefix clearly enough.

The attestation flag is sufficient for short-term experimentation. Deciding on a parser change
before knowing the miss rate would be building for an imagined problem.

## Preconditions before gathering evidence

Both required, in order:

1. **TOO-19 finished** -- the deny rules need per-rule `additionalContext`, or the denial teaches
   nothing and the evidence is about a broken mechanism rather than the real one.
2. **TOO-19 published** -- installed and running, not just merged.

Only then do the enforcement rules go into a live config and start producing data. Patience.

## What to measure, once running

The question is narrow: **how often does an agent produce the comment block but omit the env-var
prefix?**

- Denials of the three intent-disclosure rules, split by whether the command carried an
  `# INTENT:` block. Comment-present + marker-absent is the signal case.
- **Repeat** denials on the same command within a turn -- an agent that added the comment,
  re-issued, and was denied again is the exact failure the parser change would prevent.
- Whether it self-corrects on the next attempt (a one-off is cheap; a loop is not).

`tmp/audit_disclosures.py` already parses toolguard logs and detects disclosure blocks, so it is
most of the harness. It classifies commands by qualifying shape and checks for `# INTENT:`; it
would need the denial-outcome split added. See [[intent-disclosure-phrasing-experiment-winning-wording-and-results]]
for the log-parsing gotcha (ASK entries carry no "Matched Rule" line, which silently hid every
heredoc on the first run).

## Decision rule

If comment-without-marker is rare, or agents self-correct on the next attempt, keep the env-var
prefix -- it is cheap and already works. If it is common or produces retry loops, the parser
change is justified and this becomes a real ticket.

## Security note to carry into that design

A comment that influences decisions is an attack surface: the comment is authored by the same
agent the rule governs. The env-var prefix has this property today too, so preserving comments is
not a regression -- but it is the reason this is a **disclosure** mechanism and not an
**authorization** one. Nothing here should ever be able to turn a deny into an allow; it exists to
put information in front of Arnon before he decides. Keep that boundary explicit if the design is
revisited.
