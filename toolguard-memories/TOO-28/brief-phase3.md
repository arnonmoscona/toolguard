---
title: brief-phase3
type: note
permalink: toolguard/too-28/brief-phase3
---

# Brief: TOO-28 Phase 3 -- per-rule auto-mode decision

## Task

Spec section 4.2. **An individual rule must be able to declare that its decision differs when the permission mode is auto.**

Both directions are wanted, on one field:

- **Widening** (`ask` -> `allow` in auto mode) -- the primary case. Intent-disclosure and read-only attestation: today an attested, undecidable-but-declared operation costs a prompt in every mode.
- **Narrowing** (`ask` -> `deny` in auto mode) -- friction exactly where human judgement is absent.

**This rides on the existing rule-enrichment mechanism**, not a new pattern dialect: `{ match = "Bash(...)", additionalContext = "...", in_auto_mode = "allow" }`. `RuleEntry.metadata` already carries structured keys and `permission_resolution` already looks the winning entry up.

**Key name: `in_auto_mode`.** Consistent with the settings shipped in Phase 2 (`no_match_fallback_in_auto_mode`), and it reads correctly at the use site: *in auto mode, allow*.

**Do NOT call this an "override" anywhere in code.** `RuntimeVerdict.overrides` and `permission_resolution._detect_override` already mean allow-over-deny **conflict detection**. Reusing the word would create precisely the vocabulary split the previous commit removed. Call it the rule's auto-mode decision.

**Behaviour-neutral when no rule carries the key**, which the corpus must prove.

## Scope and widening

**In scope:**

- **`rule_entry.py`**: parse and validate `in_auto_mode` on a structured entry. Values are decisions -- use the `DECISION_*` constants from `constants.py`, not literals. An unrecognised value must be a **config-time issue**, not a silent ignore; follow how `additionalContext` reports its own problems (`_additional_context_issues`).
- **`permission_resolution.py`**, at the seam that already exists. Around line 252 the winning entry is fetched:

  ```python
  kind = decision
  prov = provenance_for_pattern(layers, matched_pattern, kind)
  winning_entry = entry_for_pattern(layers, matched_pattern, kind)
  ```

  **The ordering here is a trap.** `kind = decision` maps the decision to *the list the matched pattern lives in*, so provenance and enrichment resolve against the right rule. **Apply the auto-mode decision AFTER that lookup**, never before -- applying it first would send `provenance_for_pattern`/`entry_for_pattern` looking in the wrong list and silently lose provenance and `additionalContext`.
- **`context.permission_mode`** is already available here from Phase 2. Gate on `AUTO_PERMISSION_MODE`.
- Documentation in `docs/` -- the configuration reference, alongside the Phase 2 settings. **Not** `install.md`, **not** the bundled skills; those are TOO-77.

**Explicitly OUT of scope:**

- **Converting this repo's own disclosure-nudge rule.** Spec 4.2 names it as the live use case, but that is a change to `.claude/toolguard_hook.toml`, which would move real decisions and require regenerating the verdict corpus. Build the capability; do not use it here. **Flag it as a follow-up.**
- The two fallback settings (Phase 2, done) and anything in Phase 4.
- Any change to how `hard_deny` resolves -- see Findings 1.

**Is widening authorised? NO**, except fixing what the change breaks.

## Findings carried forward

1. **`hard_deny` needs NO decision-logic change, and this is verified, not assumed.** `check_hard_deny` is called from `resolve.py:243`, *before* any matching, and `permission_resolution`'s own docstring states it: *"`hard_deny` denials are handled by the caller BEFORE any matching happens and never reach this function at all."* So the cascade -- where the auto-mode decision lives -- structurally cannot see a hard-denied command, and spec 4.2's constraint (*"an auto-mode override on an `allow` entry must never carve an exception out of a `[hard_deny]`"*) already holds.
2. **An `in_auto_mode` key inside `[hard_deny]` is IGNORED and DOCUMENTED. No validator rule.** Arnon, 2026-09-05: *"Hard-deny should be trivial to understand with as little subtlety as feasible. It is intended for absolute denial as the name suggests. If you start adding modifiers it stops being 'hard'."* I had proposed rejecting it as a config error; he overruled that, and he is right -- ignoring it fails **closed** and visibly (the command is denied anyway, and the author notices). Document the fact where a reader will meet it.
3. **A `deny` rule carrying `in_auto_mode = "allow"` must be REFUSED as a config error**, pending Arnon's decision. That combination means "deny normally, permit when no human is watching", which is backwards from every other safety default in this project. Spec 4.2's two examples both start from `ask`, and its stated constraint concerns `allow` entries -- it does not contemplate weakening a `deny`. **Refusing is the reversible choice**; permitting it silently is not. Report it so Arnon can lift the restriction deliberately.
4. **Phase 2 shipped `DECISION_*`, `AUTO_PERMISSION_MODE` and `_FALLBACK_SETTINGS`.** Use them; do not introduce parallel literals.
5. **Baseline**: `Ran 4064 tests` / `OK (expected failures=4)`; ruff clean; corpus `OK: no differences` at `6401`/`61`; three fitness checks; 8 entry points.

## Steps and their completion artifacts

**TDD IS required** -- this adds behaviour. **Paste the RED runs.** No `RED:` markers in code.

| # | step | completion artifact |
|---|---|---|
| 1 | RED: an `ask` rule with `in_auto_mode = "allow"` allows under auto, and still asks under `default` | pasted failing output |
| 2 | RED: an `ask` rule with `in_auto_mode = "deny"` denies under auto (the narrowing direction) | pasted failing output |
| 3 | RED: **a rule WITHOUT the key behaves identically under every mode** | pasted failing output. This is what makes the corpus result mean something |
| 4 | RED: provenance and `additionalContext` still resolve correctly on a rule whose decision was changed | pasted failing output. This is the ordering trap above; a test that only checks the decision would pass with provenance silently lost |
| 5 | GREEN: implement | suite green; state the new count |
| 6 | **hard_deny regression guards** | a hard-denied command stays denied with `in_auto_mode = "allow"` present on a matching allow rule, AND on a `hard_deny.allow` carve-out. These assert an invariant that currently holds structurally -- exactly the kind a later refactor breaks silently |
| 7 | **The section 8 invariant** | a rule with `in_auto_mode = "allow"` must still be clamped to ask under a parse failure. The floor sits above rule matching and must not be escapable by a per-rule declaration. Add it to the enumerating test from Phase 2 if that is the natural home |
| 8 | Config-time validation | an unrecognised `in_auto_mode` value, and a `deny` rule carrying `in_auto_mode = "allow"`, both surface as issues rather than silently doing something |
| 9 | Lint, format, three fitness checks | each clean / exit 0 |
| 10 | **Corpus equivalence** | `OK: no differences` at `6401`/`61`, with no rule in this repo's config carrying the key |
| 11 | **Calibrate before believing step 10** | plant a decision-altering change, confirm `--verify` FAILS, revert, confirm it passes, `git status --porcelain` clean |
| 12 | Entry points | all 8 load |
| 13 | **Live end-to-end** | drive the real hook with a rule carrying `in_auto_mode`, under `permission_mode: "auto"` and `"default"`, and paste both decisions. Only the live path proves the mode reaches the rule |
| 14 | Sibling sweep | anywhere else a rule's metadata should be consulted and is not |

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **That `permission_resolution.py:252` is the only place a matched rule's decision is finalised.** I read one site. The file-path path and the compound path may finalise elsewhere, in which case the auto-mode decision must be applied at each -- or better, at a single shared point. **If you find more than one, say so before scattering the logic**; a decision applied in two places will drift.
- **That `kind = decision` is the only ordering hazard.** It is the one I found by reading. There may be others.
- **That `RuleEntry.metadata` validation is the right home** for rejecting a bad value. If validation happens elsewhere for `additionalContext`, follow that instead and tell me.
- **That refusing `deny` + `in_auto_mode = "allow"` is implementable cleanly** at config time. If the rule's list membership is not known where metadata is validated, say so -- that is a real structural finding, not a reason to skip the check.
- **That the compound path needs nothing.** A compound's leaves each resolve through the cascade, so a per-leaf rule with the key should work -- but I have not traced it, and the interaction with `_combine_strictest` is unexamined.

**Report anything you find wrong.** Every phase so far produced its most valuable output as a correction to my premises.