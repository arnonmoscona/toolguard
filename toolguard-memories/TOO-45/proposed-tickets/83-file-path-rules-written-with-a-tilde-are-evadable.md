---
title: A [regex] or [native] file rule written with ~ does not match an absolute path
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/83-file-path-rules-written-with-a-tilde-are-evadable
---

# `deny Read([native]~/.ssh/*)` is evaded by an absolute path

**Measured 2026-08-20** while implementing ticket 78, by the agent implementing it — as a direct check of a claim in its brief rather than as a search.

Ticket 78 recorded that file-path tools were "symmetric and safe", so its scope was narrowed to Bash. **That is half true.** Safe in the direction ticket 78 was about, for all four pattern types. In the **reverse** direction, a `[regex]` or `[native]` file rule written with `~` does **not** match the absolute spelling of the same path.

```
rule:     deny Read([native]~/.ssh/*)
path:     /home/arnon/.ssh/id_rsa      ->  EVADES
```

Same shape as ticket 78 and the same consequence: a rule that names a file fails to fire on that file, spelled differently. Here it is the `~` spelling that is written and the absolute one that escapes, which is the opposite of ticket 78's Bash case and is why narrowing 78 to Bash left it standing.

## Why it is separate from 78

Ticket 78's fix accumulates a tilde-expanded spelling for **commands**. File-path matching is a different path through the matcher, and `[regex]` and `[native]` file rules are matched against the path text directly. Folding this into 78 would have widened a security change mid-flight across two subsystems.

## The design question this one carries, which 78 settled for commands

Ticket 78 established that tilde expansion is an **identity transformation** on a path — `~/x` and `/home/arnon/x` are the same file — which is why it applies uniformly to granting and restricting rules alike, unlike ticket 77's assignment stripping, where `LD_PRELOAD=evil ls` is genuinely not `ls`.

**That reasoning transfers here unchanged**, and it is the argument for making file-path matching symmetric in both directions rather than adding one more one-directional patch. The exceptions are the same and should be checked the same way: `~user` names somebody else's home and is not an identity, and a `~` that is not leading is not an expansion at all.

## Note on evidence

Ticket 78's own experience applies. This repository's rules cannot demonstrate the deny direction — every rule it has naming an absolute home path is an `allow` rule — so a clean corpus run over this config proves nothing about the case that matters. **Build the deny-direction evidence deliberately.**
---

## The command side has the same gap, measured 2026-08-20

Ticket 78's follow-up closed the absolute-rule-versus-tilde-command direction for all four pattern types. **The reverse remains open on commands too**: a `~`-spelled `[regex]`, `[glob]` or `[native]` **command** rule is not matched by the absolute spelling. DEFAULT is unaffected, before and after.

Measured exposure: **zero such rules exist today**, so it is prospective rather than live — which is why the implementer recommended recording it here instead of widening the matcher a second time in the same change. That was the right call; a security widening taken twice in one pass is one that nobody reviewed separately.

So this ticket now covers **both subsystems in the same direction**: a rule written with `~` failing to match the absolute spelling, on file paths and on commands alike. The identity argument from ticket 78 applies unchanged to both.

---

## FIELD EXPOSURE MEASURED 2026-08-20 — 57,148 real decisions

Corpora: `~/projects/flowers/featherhill/logs` (49 daily logs, 4,722 decisions — **a real user project, the corpus that counts**), `toolguard/logs` (51 logs, 52,191 — dogfood, biased to this repo's own development), `instagram-downloader/logs` (7 logs, 235).

| shape this ticket needs | featherhill | toolguard | instagram | total |
|---|---|---|---|---|
| tilde-spelled rules (any type) | 1,536 | 21 | 0 | 1,557 |
| extended-type rules (any spelling) | 24 | 3,117 | 0 | 3,141 |
| **BOTH extended-type AND tilde-spelled** | **0** | **0** | **0** | **0** |

Tilde-spelled rules are *extremely* common — 1,536 in featherhill alone, 42% of its matched rules, e.g. `~/projects/**` against `/Users/arnon/...`. **They work**, because they are DEFAULT/glob file rules and that path already matches. The defect needs a rule that is tilde-spelled **and** `[regex]`/`[native]`/`[glob]`, and **not one such rule exists in any corpus**.

**DEFER CANDIDATE — bottom of the queue, flagged for Arnon.** This confirms the ticket's own statement that exposure is prospective, and quantifies it: the two populations are large and disjoint.
