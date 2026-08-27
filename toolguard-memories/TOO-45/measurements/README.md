---
title: Coordinator-only measurements — NOT visible to blinded estimators
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/measurements/readme
---

# Why this directory exists

**Measuring a ticket before briefing it is this campaign's highest-yield habit.** It closed ticket 57 with zero work, corrected ticket 20's diagnosis, and grounded 39, 64 and 70.

**Appending those measurements to the ticket files destroyed the blinding.** A blinded estimator is given exactly two things: the ticket, and a file inventory. Ticket 39's estimator predicted the scope correctly by **quoting the coordinator's own appendix back**, and ticket 20's purpose-built test of cause `I` was killed outright because the coordinator corrected the wrong diagnosis the experiment depended on.

**Contaminated by this route: 20, 39, 57, 64, 70.** Separately contaminated via the return channel: 05, 19.

## The rule from here

**Findings that come from the coordinator reading or executing code go in THIS directory, keyed by ticket number.** The ticket file keeps what was filed, plus status amendments recording what shipped. An estimator gets the ticket as filed plus the inventory — nothing written by the person who will brief the implementer.

**The implementer still gets the measurements**, quoted into its brief. Blinding is about the *estimator*, not about withholding evidence from the work.

## What still belongs in the ticket file

- `PARTIALLY FIXED in <sha>` status lines — those are facts about shipped code, not coordinator analysis.
- Arnon's dispositions and decisions.
- Anything a reader needs to understand what the ticket *is*.
