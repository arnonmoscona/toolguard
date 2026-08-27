---
title: Applying an edit drops the parse-failure safety floor, and the as-if-enacted
  audit then runs against a config that has lost it
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/70-applying-an-edit-drops-the-parse-failure-safety-floor
---

**PARTIALLY FIXED in `05f786d`.** The main defect, both parts, is fixed (`toolguard/tools/config_access.py:289`); still open: the caption-vs-enacted mismatch and unconditional double-wrapping, both still live in `toolguard/tools/edit_proposal.py`, untouched by phase 2.

# `with_layer_rules_replaced` silently drops `Configuration.parse_failures`

**Found 2026-08-13. RED test in the tree. The fix is one keyword argument and is proven.**

## The defect

`with_layer_rules_replaced` returns `Configuration(layers=..., start_dir=...)` and **omits the third field**, so `parse_failures` resets to `()`.

That field is not bookkeeping. A config with parse failures reports a validation issue like:

```
('error', '/broken.toml failed to parse and was skipped')
```

and that state **clamps every governed decision except an existing deny to `ask`** — the TOO-19 parse-failure floor. **Any edit erases the condition and the config comes back reporting no error at all.**

## Why it is more than a lost field

`security_audit --edits` calls `apply_edits(config, ...)` and then runs `security_audit(...)` **on the result**. So the as-if-enacted audit — the thing a user reads to decide whether to apply a change — runs against a config that has **lost its safety-floor condition**. The preview is cleaner than reality, in the one direction that matters.

This is ticket **47**'s shape (a constructor omission silently resetting a field) in a materially more consequential field.

## Fix, proven

Add `parse_failures=config.parse_failures`. **Mutating toward the fix turns the RED test green and breaks nothing else** — the strictly stronger statement, per ticket 31.

RED test: `TestWithLayerRulesReplaced.test_parse_failures_survive_the_rebuild`.

## Three more defects in the same module, all measured, all now held

### 1 — The description and the edits are unguarded against each other

`EditProposal.action` / `tool` / `rationale` are what a consumer **renders**; `edits` is what `apply_edits` **enacts**; nothing cross-checks them.

Measured: two proposals captioned `(narrow, Bash, "tighten Bash")` and `(remove, Write, "delete a Write rule")` over one identical edit tuple produce **byte-identical results** — a caption reading *"tighten Bash"* enacted a **`Read` broadening to `/**`**. The mutant that applies `proposal.tool` instead of `edit.tool` survived at HEAD with zero failures.

**This is ticket 57's defect one layer upstream.** There it was "the JSON list and the writer's list are different variables"; here it is `EditProposal.tool`/`action`/`rationale` versus `RuleEdit.tool`/`list_type`.

### 2 — A removal that misses still applies its addition

Queue row **AE2**, now executed: a `REPLACE` narrowing `git *` -> `git status:*` against a layer that no longer holds `git *` leaves **both** rules. **Half a narrowing is a broadening.** Pinned as characterization in the shape the queue prescribed; the design decision is open.

### 3 — Unconditional double-wrapping produces a silently inert rule

`wrap_tool_pattern` is unconditional, so a hand-authored `--edits` JSON carrying `"added_patterns": ["Bash(git:*)"]` yields `Bash(Bash(git:*))` — an inert rule, no error. Ticket 25's family, at the `--edits` boundary.

## The test module was at 16 mechanisms with zero detection

14 -> 32 tests; mutant survival **16/41 -> 0/48**; **zero** cannot-fail tests, so all sixteen were the *cannot-distinguish* category. Among them: edit order within a proposal, proposal list order, which tool an edit targets, JSON-safety of the serialized provenance path, the only-first-matching-layer rule, and — **deleting `new_content = dict(layer.content)` silently dropped a hard-deny rule with nothing failing.**

**Seven of the sixteen were killed by one fixture repair.** The serialization fixture held its type default or the fixture-common value in every field, so a mutant hardcoding any of them was invisible. Rebuilt so no field carries a default. **A fixture built from defaults is what lets hardcoding mutants through** — worth applying wherever a fixture looks tidy.

## And the read-only pass said this file was fine

`follow-up-queue.md:1499` records *"Nothing substantive… no false claim about behaviour anywhere, and its fixtures build exactly what its Givens describe"*, calling it *"the only file of the five whose comment volume was already proportionate."*

**The fixture claim is the instructive part: the fixtures did build what the Givens described — using every field's default value, which is exactly what let seven mutants through.** A statement can be true and still name the defect it is dismissing.

Third instance the same evening of a read-only queue verdict that mutation contradicted (`file_lock`: 3 comment findings vs 5 zero-detection mechanisms; `self_permission`: one redundancy nit vs 13 of 25).

---

## REMAINING SCOPE MEASURED 2026-08-20 — and the title understates it

The named safety-floor defect is fixed (`config_access.py:289`). Both remaining items live in `toolguard/tools/edit_proposal.py` (193 lines) and are **one defect with two symptoms**: the module carries **two parallel representations of the same change**, and nothing forces them to agree.

- **`RuleEdit`** (`:35`) — *"One atomic edit to a single `(tool, list_type)` list at a single layer."* This is **what gets applied**.
- **`EditProposal`** (`:58`) — bundles `RuleEdit`s under a `tool` / `action` / `rationale`. This is **what the user reads**.

The ticket's own measurement: two proposals captioned `(narrow, Bash, "tighten Bash")` and `(remove, Write, "delete a Write rule")` over one identical edit tuple produce **byte-identical results** — so a caption reading *"tighten Bash"* enacted a **`Read` broadening to `/**`**. The mutant applying `proposal.tool` instead of `edit.tool` **survived at HEAD with zero failures.**

### Why this outranks its title

The title is about a dropped safety floor, which is fixed. What is left is worse in a specific way: **what the user is shown is not what happens.** A user reads a caption to decide whether to apply a change, and the caption is a separate field from the change.

This is the campaign's founding defect — *"prose is output, not a data structure"* — in its most literal form. Not prose being parsed back, but **a human-readable description stored alongside the machine-readable operation, free to diverge.** The 813/975 under-logging incident is the same shape: a fact rendered for humans, the structured original discarded or ignored, and the two silently disagreeing.

### Fix direction — derive, do not duplicate

The caption should be **derived from the edits at render time**, not stored beside them. A proposal that reports `tool` should report the tools its `RuleEdit`s actually touch; an `action` should be computed from what the edits do. Then divergence is impossible rather than merely tested against.

If a stored caption is genuinely needed — for a rationale a human wrote, which cannot be derived — then **it must not name anything derivable.** A rationale saying *"localhost health checks are safe"* is fine; one saying *"tighten Bash"* is a duplicated fact.

### Note against ticket 57

Ticket 70's text says *"this is ticket 57's defect one layer upstream."* **57 turned out to need no production change** — its behaviour was already correct and only detection was missing. **That is not true here**: this code can genuinely diverge, and the surviving mutant proves nothing catches it. Do not let 57's disposition carry over.
