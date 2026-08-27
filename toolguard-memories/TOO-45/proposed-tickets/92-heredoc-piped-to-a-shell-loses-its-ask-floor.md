---
title: A foreign heredoc whose OUTPUT is piped to a shell loses its ASK floor
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/92-heredoc-piped-to-a-shell-loses-its-ask-floor
---

# `python <<HD | bash` runs foreign code with no ASK floor

**Found 2026-08-21** during the review of ticket 19's P2/P3 fix. **Pre-existing — measured identical before and after that change** (PYTHONPATH-isolated comparison with module provenance printed inside the measuring run), so it is not a regression and was correctly kept out of that ticket's scope.

Using `HD` as the heredoc delimiter throughout, so this file can be pasted into a shell without the examples terminating it:

```
python <<HD | bash        ->  allow
import os
HD

python <<HD               ->  ask      (control: the floor works)
import os
HD
```

`sh` in place of `bash` behaves the same.

## Cause

`_classify_pipeline_sink` (`toolguard/parser/multiline.py`) takes the **last** `|`-separated segment as the heredoc's sink. Here that segment is `bash`, so the heredoc is classified bash-family and its body is spliced back in as **shell source**, reaching the matcher as ordinary shell leaves with no floor.

**In real bash the heredoc belongs to `python`.** A pipe governs the command's *stdout*; the heredoc is its *stdin*. So the classification is not merely conservative — it is wrong about which process receives the body.

## Why it is a different defect from ticket 19's P2

P2 was about **statement** separators (`&&`, `||`, `;`, `&`) letting an earlier command capture a later heredoc's sink, and is fixed by scoping to the heredoc's own statement. This one lives entirely **inside a single statement**, and inside the pipe chain that scoping deliberately preserves. Ticket 19's P2 wording — *"segments on `|` alone"* — names this cause, but every example it gives is separator-based, so the fix does not reach it.

## Measured exposure

**Zero occurrences** of `<interpreter> <<HEREDOC ... | <shell>` in the three log corpora.

**Assess it against the reachability filter rather than the count.** `cmd <<HD | bash` is a real idiom — generate a script, pipe it to a shell — so it arises by ordinary intent, not by evasion. And the failure is **silent by construction**: no floor, no warning, nothing distinguishing it from an ordinary allow. Per `.claude/rules/evidence-before-fixing.md`, *zero occurrences plus accidental reachability plus silent failure is still a fix*.

**Caveat on that zero, recorded deliberately**: the same rule now documents that counts under ~50 must be read by printing the lines, and that probe traffic from toolguard's own investigations contaminates **every** corpus, featherhill included. This count came from a regex over raw logs and has not been line-inspected. Treat it as *"no evidence found"*, not as *"does not occur"*.

## Fix direction, and the question it forces

A heredoc's sink is the command it is **attached to**, decided by redirect position, not by pipeline position. So classify the sink from **the pipe segment containing the `<<` operator** rather than from the last segment of the chain.

That is ticket 19's P2 fix one level down — scope to the construct that owns the heredoc — which suggests the two should share one notion of *"the command this redirect belongs to"* instead of each carrying its own. This project has now paid three times for one concept with several hand-written enumerations; this is the same shape before it becomes the fourth.

**Check the genuine data-flow case before implementing.** `cat x | python <<HD` must still classify as `python`. There the heredoc is already in the last segment, so segment-of-the-`<<` gives the same answer — but verify it on a matrix, not by reasoning.

## Related

- Ticket **19** — P2/P3, the statement-scoping fix this was found beside.
- Ticket **90** — the surviving prose re-parse for `'plain'` units.
- Ticket **91** — a substitution body still matched as one leaf.
- If ticket 19's repair round declines the wider guard: `python $(a | b) <<HD` is floorless for the same family of reason, because `_split_on_unquoted_pipe` splits on a `|` inside `$(...)`.

---

# CLOSED 2026-08-23 — RE-MEASURED, fixed

Flagged during the memory-extraction pass as *"recorded as fixed by ticket 98's spikes, never re-measured"*. Re-measured against HEAD, provenance printed by the measuring run:

| command | floored leaves |
|---|---|
| `python <<HD \| bash` + body | `('python __HEREDOC_TO_python__', True)` |
| `python <<HD` alone (control) | `('python __HEREDOC_TO_python__', True)` |

**The piped form is now identical to the unpiped control.** Fixed by ticket 98 chunk 2, which moved heredoc sink attribution onto the parse tree: a bash-family or foreign bearer wins outright even mid-pipeline, so the interpreter receiving the body decides. Before that fix this command produced NO sentinel at all and leaked the body line into the leaf list as a bare command.

Closed on evidence, not on the earlier assumption.
