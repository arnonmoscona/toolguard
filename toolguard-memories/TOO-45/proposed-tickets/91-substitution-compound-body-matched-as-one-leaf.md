---
title: A substitution's compound body is matched as one PEG leaf, not split per-part
tags: [TOO-45, proposed-ticket]
permalink: toolguard/too-45/proposed-tickets/91-substitution-compound-body-one-leaf
---

# Found in the ticket-79 round-3 review; filing recommended there, not done until round 4 asked again

Pre-existing, not introduced by ticket 79 -- confirmed present against base (`7d0646d`) too.
`extract_commands` emits a `$(...)` substitution's own body as a single command string when
that body is itself compound (e.g. `python -c "p"; ls`), and the whole string is then matched
against rules as one unit -- so `$(python -c "p"; ls)` is recorded as matched entirely by
`python -c *`, and `ls` never gets its own per-part rule check.

## Why it matters

Contradicts this project's own hard constraint (`CLAUDE.md`, "All bash parsing goes through the
PEG grammar -- never hand-rolled Python"): compound commands must be split into parts and
matched per-part, or the rules become brittle. A substitution body is exactly a compound
command, and it is not currently split before being checked.

## Where ticket 79 touches this, and where it doesn't

Ticket 79's `audit_parts`/`deny_check_parts` split (`_unit_for`/`judge_unit` in
`toolguard/compound.py`) now also routes an unsplit compound substitution into `audit_parts`
when it contains foreign inline code, which additionally duplicates the inner command in the
itemisation and inflates the "All N sub-commands allowed" count in the reason text. Ticket 79
did not introduce the underlying gap -- it is pre-existing and ticket 79's own fix merely flows
through it, unchanged.

## Fix direction

Recursively split a substitution's own body through the same PEG-based `extract_commands` path
used for the outer command line, rather than treating the body as one opaque string, before it
is checked against rules or classified into `audit_parts`/`deny_check_parts`.

## Status

Not investigated beyond the round-3 finding above -- no reproduction script, no measured
itemisation-inflation example. Worth a ticket, not a gate on ticket 79's own work.
