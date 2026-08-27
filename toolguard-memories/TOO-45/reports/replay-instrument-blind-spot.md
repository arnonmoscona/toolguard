---
title: The corpus replay is structurally blind to not-matching -> matching
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/replay-instrument-blind-spot
---

# "Zero flips" has been over-trusted across this whole campaign

**Found 2026-08-20** by the ticket-18 blinded reviewer, and it reaches backwards.

## The defect in the instrument

The corpus replay compares the **decision** (`allow` / `deny` / `ask`) for each logged command before and after a change. **It cannot see a rule that goes from not-matching to matching, when the fallback already permits the command.**

This repository's `.claude/toolguard_hook.toml:4` sets:

```toml
no_match_fallback = "allow_with_no_warnings"      # TEMPORARY until TOO-28 is done
```

So a command that matched **no rule** was already `allow`, silently. After a change makes some rule match it, the decision is still `allow`. **No flip, no warning, nothing in the log.** The change is invisible to the instrument.

**Measured instance, not hypothetical.** This repo's own rule `Bash(\obsidian search:context *)` matched **nothing** at HEAD and matches **now**; the real command appears 5 times in `logs/`. The ticket-18 implementation reported *"zero flips across 53,112 logged decisions"* and concluded the change was safe. The correct reading is that **zero flips is evidence of neither safety nor inertness** — it is a null result over a transition the instrument cannot observe.

## What this invalidates, and how far back

Every "zero decision changes" claim made on this branch was measured under this config. Most consequentially:

- **Ticket 78**: *"26,530 real commands x 2 package trees, 0 newly-deny, 0 newly-allow, 0 newly-ask, 0 matched-rule changes"* — that one **did** compare matched rules, so it is sound.
- **Ticket 18 (this session)**: verdict-only. **Not sound as safety evidence.**

**The distinguishing question is whether the replay compared `matched_rule` as well as `decision`.** Where it did, the finding holds. Where it did not, "zero flips" means only that no command changed tier — a much weaker claim than it was reported as.

## The fix, and it is cheap

**Always compare `matched_rule` alongside `decision`.** A rule going from not-matching to matching shows up immediately as a `matched_rule` change from `None` to a pattern, regardless of what the fallback does. Ticket 78's harness already did this; it should be the standard rather than the exception.

**And note the second-order point about the config.** `allow_with_no_warnings` is marked TEMPORARY pending **TOO-28**. While it is set, this repo cannot observe *any* no-match event, in the logs or in a replay. That makes the dogfood corpus systematically weaker evidence than the featherhill corpus for anything involving rule coverage — a further reason to weight featherhill, beyond the dogfood-bias argument already recorded in `.claude/rules/evidence-before-fixing.md`.

## The general shape, which is this campaign's most repeated finding

An instrument reporting a clean result over a path it cannot see. The same shape as: checkers reporting PASS having examined nothing; `run_guard` returning `ok=True` with zero cases checked; the ASK floor the corpus could not observe; `--ambient` blind to `expanduser`, then `resolve`, then `absolute`.

**The rule this project keeps re-learning: before believing a null result, establish that the instrument can see a positive one.** For a replay, that means planting a change you know should show up and confirming it does.

---

## CORRECTED 2026-08-20 by Arnon — the fix is better than "compare matched_rule", and the blind spot is far narrower than feared

> *"since you do collect provenance - it should be easy for you to see whether the verdict was a fallback or not. And for the corpus estimation - you can assume the fallback is always ask even if in this repo it is temporarily an allow."*

**Both points hold, and the second is the real fix.**

**Re-score the corpus as if `no_match_fallback` were `ask`.** That converts the unobservable transition into a visible one: a command that matched no rule scores `ask`, and if a change makes some rule match it, the replay shows a genuine **`ask -> allow` flip**. This makes the *instrument* sensitive rather than merely adding a field to eyeball, and it models the **default** configuration instead of this repo's temporary one. Comparing `matched_rule` remains worth doing, but it is the weaker half.

**And provenance is already recorded**, so a fallback is distinguishable from a real match with no new plumbing — the log writes it in the matched-rule field as `[fallback allow -- no rule matched]`.

### Measured: the blind spot is a dogfood artifact only

| corpus | decisions | real rule match | fallback |
|---|---|---|---|
| **featherhill** | 3,675 | **100%** | **0** |
| toolguard | 51,918 | 81% | **9,848 (19%)** |
| instagram | 28 | 100% | 0 |

**featherhill — the corpus that counts — has zero fallback verdicts.** Every decision matched a real rule, so nothing there was ever masked, and any replay run against it was sound all along. The 19% is entirely toolguard's own logs, where `allow_with_no_warnings` has been swallowing no-match events.

**So the retrospective damage is smaller than the finding first suggested**: claims measured over featherhill stand as made. Claims measured over the *combined* corpus are diluted by toolguard's 19%, and a claim resting only on toolguard's logs is the one to distrust.

This is a third, independent reason to weight featherhill above dogfood — alongside rule-shape bias and command-shape task-specificity, both already in `.claude/rules/evidence-before-fixing.md`.
