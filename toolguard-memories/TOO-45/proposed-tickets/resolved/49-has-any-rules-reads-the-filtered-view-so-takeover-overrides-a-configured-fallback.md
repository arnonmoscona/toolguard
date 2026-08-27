---
title: has_any_rules reads the takeover-filtered view, so takeover silently overrides
  a user's configured deny fallback
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/49-has-any-rules-reads-the-filtered-view-so-takeover-overrides-a-configured-fallback
---

**FIXED in `05f786d` (TOO-45 phase 2).** `has_any_rules` now reads the unfiltered view, so takeover no longer overrides a configured fallback — see `toolguard/config.py:1185-1194`.

# A configured fail-closed setting is replaced by `ask`

**Found 2026-08-13. A RED test is in the tree. This fires in the CANONICAL takeover setup, not an exotic one.**

## The defect

`Configuration.has_any_rules()` iterates `permission_layers()` — the **takeover-filtered** view.

In the ordinary takeover configuration:

- native `permissions.allow = ["Bash(*)"]`
- a hook file with takeover **on** and no Bash rules of its own yet
- `no_match_fallback = "deny"` — the user has explicitly chosen fail-closed

takeover strips the only Bash allow, so `has_any_rules("Bash")` returns `False`, and the hardcoded `'ask'` for an *unconfigured tool* **silently overrides the user's explicit setting**.

Measured:

| takeover | `has_any_rules` | verdict |
|---|---|---|
| `True` | `False` | **`ask`** — "No Bash permission rules configured at any level" |
| `False` | `True` | `allow` |

## Why this is a defect rather than a judgement call about defaults

`has_any_rules`' **own docstring** says it distinguishes a *genuinely unconfigured* tool from a *configured* one whose rules do not happen to match. **This configuration is configured** — the user wrote `no_match_fallback = "deny"` and enabled takeover deliberately. The filtered view makes a configured system look unconfigured, and the safety net then outranks the setting it was meant to back up.

The user-visible effect is the wrong direction: someone who asked for fail-closed gets a prompt instead.

## The product decision Arnon owns

Does the unconfigured-tool safety net win, or does an explicitly configured fallback? The red test asserts **what the config says**. If the answer is "the safety net wins", the fix is to say so in the reason string and in the docs — not to leave the two silently disagreeing.

## Status in the tree

`test_takeover_mode.test_configured_deny_fallback_survives_suppression_of_every_rule` is deliberately RED, failing `'ask' != 'deny'`.

## Related finding: the takeover warning says the opposite of what happened

`session_warnings.issue_takeover_warning` emits *"Takeover mode is active. Claude's native permission prompts are bypassed."* — and `hook._announce_takeover_state` emits it on the **conflict** branch, where `enabled` has just **fail-safed to `False`** and native prompts are precisely what is still active.

So on the one path where the user most needs an accurate message, the message states the opposite. Confirmed still live (it is a standing queue item). Out of scope for a test module; needs a production fix.

**IMPORTANT FOR WHOEVER FIXES IT — the wrong string is PINNED by a test.** `test/unit/test_session_warnings.py:56-61` (`test_notice_message_content`) asserts `"native permission prompts are bypassed"`. **Correcting the message will turn that test red, and the correct response is to update the test, not to revert the fix.** Emitted from `hook.py:826`, in `_announce_takeover_state`'s conflict branch, where `takeover.enabled` has already fail-safed to `False`.

This is the failure mode the campaign has been guarding against, arriving from the other direction: a green test pinning a wrong user-facing string, which will actively resist the fix.

### MEASURED 2026-08-13 — it is worse than "the message is wrong". The program contradicts itself in one breath.

Driving `hook._announce_takeover_state` on the conflict branch, stderr receives, **two lines apart, on the same stream**:

```
[CONFLICT] ... Fail-safe applied: takeover mode is treated as DISABLED (OFF), so Claude
native permission prompts stay active and nothing is silently bypassed.
...
[TOOLGUARD WARNING] Takeover mode is active. Claude's native permission prompts are bypassed.
```

**Two directly contradictory propositions, both asserted.** This is an outright error, not a wording preference — no phrasing makes both true.

### The existing test was reframed, not inverted — and that was the right call

The string is **correct on the enabled branch**. Inverting the assertion would have been wrong. The defect is **one unconditional message serving two opposite states.** So:

- `test_notice_text_is_accurate_only_for_the_ENABLED_state` keeps all four phrase assertions (nothing weakened) but its name and docstring now say this is the only text the function can emit and that it is true **only** when `enabled is True`. That un-enshrines the value without losing the pin.
- New RED `test_conflict_branch_must_not_claim_the_bypass_happened` asserts the conflict branch emits neither claim, **while asserting `"Fail-safe applied"` IS present** — so the test proves it actually reached that branch rather than passing on an unrelated path.

### Two fix candidates, both proven against the RED test with zero collateral

- **CANDIDATE_A** — drop the call at `hook.py:826` on the conflict branch. One-line deletion, **but it costs the user the "your permission config is broken" warning entirely.**
- **CANDIDATE_B** — a `fail_safed_off` parameter selecting a conflict-specific message, passed by the hook. **Recommended**: keeps the warning and makes it accurate.

Both were mutated toward in process and both turn the RED test green with no other test affected.

### While that function is being touched anyway

`session_warnings.py:14`'s `to_stdout` parameter gates a write to **stderr**. The docstring already flags the misnomer; rename it in the same change.

### The most consequential thing the module could not see

At HEAD, a mutant copying the notice to **stdout as well** survived. **stdout is the hook's JSON response channel**, so a stray copy there corrupts the permission decision itself. **Nothing anywhere asserted stdout silence.** Now covered.

## Why the test suite could not see any of this

**The class named for the takeover switch was blind to the switch.** The pair explicitly named `..._suppressed_when_takeover_enabled` / `..._not_suppressed_when_takeover_disabled` failed under **0 of 11** mutations, because the fixture's hook deny (`Bash(rm *)`) matched the command directly — so the native allow never decided anything and flipping takeover could not change the answer.

After repair: 3 tests fail under `filter_regardless_of_enabled`, 5 under `enabled_forced_on`, 5 under `enabled_forced_off`. **Mutation survival went from 5 of 11 undetected to 0 of 15.**

Four mechanisms had **zero** coverage anywhere and now have some: `additional_ignored_patterns` actually reaching the permission path; cross-level `enabled` disagreement discovered from real files; a non-bool `enabled` not being coerced (`bool("true")` would enable the highest-consequence switch in the product); and takeover never filtering deny entries.