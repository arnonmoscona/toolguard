---
title: "Maintenance --apply could enact a permission-widening, and hands a #NOSECURITY-withheld rule to the writer anyway"
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/57-maintenance-apply-could-enact-a-broadening-and-ignores-nosecurity-withholding
---

**PARTIALLY FIXED in `05f786d`.** The one genuinely red item, a misspelled `--tool` flag, is fixed (`toolguard/tools/maintenance.py:1296-1303`); the other two holes needed no production change, since they were already correct and are now only test-guarded.

# Two write-path holes, both undetected until measured

**Found 2026-08-13. Both were at zero detection at HEAD. Neither is a red test — both are now covered, so this ticket records what was unguarded and asks whether the production behaviour needs hardening beyond the tests.**

## Hole 1 — `--apply` could enact a permission WIDENING

`collect_consolidations` is supposed to return **strict** consolidations only. Mutant `collect-includes-broadenings`, making it return broadenings as well, **survived at HEAD with zero failures.**

The consequence is concrete, not hypothetical. The `git diff` / `git log` / `git status` fixture yields both:

- a strict consolidation — `[regex]^git (diff|log|status)`
- **a prefix-broadening to `git :*`** — which admits *every* git subcommand

**`--apply` would have enacted the widening**, and no test would have failed. Now killed by three tests.

## Hole 2 — a `#NOSECURITY`-blessed rule is withheld in the report and rewritten on disk

Mutant `apply-ignores-withholding` **survived at HEAD**. The withholding is reported correctly in the JSON — and **the writer receives the blessed rule anyway**, because the JSON `edit_proposals` list is built from a *separate variable* from the one handed to `apply_proposals`.

So a user who explicitly marked a rule "do not touch" gets a report saying it was left alone, and a config where it was changed. **The report and the action disagree, and the report is the reassuring one.**

Now killed by a test asserting **both** directions — untagged proposals are handed over, tagged ones are not.

## Why both were invisible

The module verified that `--apply` **reported** proposals (`assertTrue(payload["edit_proposals"])`, `assertTrue(all(p.kind for p in proposals))`) and that `apply_proposals` was called with the right `dry_run` flag. **Nothing verified what was proposed, or what was handed to the writer.**

That is the same shape as `test_auto_migrate.py` — verifying that success was reported rather than what was done — and it is the third analyzer this campaign has found with an unguarded safety gate, after consolidate's `_check_family2_safe` (stubbable to always pass, 0 failures across 38 tests) and redundancy's unsafe-deletion reporting (ticket 22).

Mutant survival for the module: **21 of 43 → 2 of 49**, and both survivors are proven **equivalent** mutants, not gaps.

## A separate defect, left RED

**A misspelled tool name is indistinguishable from a clean run.** `--tool Bahs` **exits 0** and prints `No maintenance findings.` — byte-identical to a real clean run. Measured the same for `tools=[]` (nothing inspected at all).

Queue row **M8**, ticket 29's family. RED test: `test_a_misspelled_tool_name_is_distinguishable_from_a_clean_run`, written **mechanism-agnostically** — it passes under an argparse rejection, a non-zero exit, or a differing message, so it does not preempt the fix.

Two adjacent instances are pinned rather than red: `--apply --write` with everything withheld prints `APPLIED changes to disk.` above a report saying `0 file(s) written`; and a vacuous replay (empty corpus) differed from a clean one only in wording, with only the vacuous half asserted.

## A NEW machine-state trap, worth carrying beyond this ticket

**`decision_ledger.USER_LEDGER_PATH` is a module constant built from `Path.home()` at IMPORT time**, so patching `Path.home` cannot move it. With one decoy entry in `~/.toolguard/decisions.json`, **2 of 4 ledger tests fail**; under a hostile HOME, 3 do. They passed only because this developer happens to have no such file.

**Any constant derived from ambient state at import time is immune to the standard isolation patches** — this is proposed ticket 44's argument arriving in a form the existing mixins cannot reach. Fixed here by redirecting the constant in `setUp`.

## Correctly NOT filed as gaps

Two mutants survive and were proven **equivalent**, not undetected:

- `_permission_patterns_in_text`'s `if start == -1: return []` is dead — `find_section_boundaries` returns `(-1, -1)` when the section is absent, so `text[-1:-1]` is `""` and the unguarded body yields `[]` for every input tested.
- `_withheld_to_dict(withheld) if withheld else []` is equivalent to the unconditional call.

**Do not "fix" either with a test.**

## Inherited, not fixed here

Maintenance's annotation write inherits **ticket 39**'s placement-blindness: `expected_patterns` is a flat set of strings, so an annotation that *moved* a rule between `allow` and `deny` would still verify. That is `config_write_guard`'s contract to change, not this module's.
---

## DISPOSITION 2026-08-20 — no production work is owed; this is a decision, not a defect

Re-read against its own amendment while scheduling. **The queue had this at ~1h of implementation. It is 0h plus one decision.**

- The single genuinely red item — a misspelled `--tool` flag — **is fixed** (`maintenance.py:1296-1303`).
- The other two holes **needed no production change**: the behaviour was already correct. What was missing was *detection*, and both are now test-guarded.

So the ticket's own question is the only thing left: *"asks whether the production behaviour needs hardening beyond the tests."*

### Recommendation: no. Close it.

The code does the right thing. The risk the ticket identified is that a **future** change could silently break it — the mutant `collect-includes-broadenings` survived at HEAD with zero failures, which is a coverage finding, not a behaviour finding. **A test is the correct instrument for that risk**, and one now exists. Hardening production code that is already correct, to guard against a regression a test already catches, adds a second mechanism where one suffices.

Worth stating because the opposite instinct is strong on a security-adjacent path: *"add a runtime check as well"* feels safer and is not free — it is another branch to keep true, another claim to keep accurate, and this campaign has spent a day on exactly that kind of accumulated claim.

**For Arnon**: overrule if you want belt-and-braces on the `--apply` write path specifically. Otherwise this closes with the phase-2 test work already committed.

### Why it was queued as work

The punch list carried it at ~1h because the entry was derived from the ticket **title** rather than its amendment. Same error class as ticket 18, where the body described an already-fixed defect and cost eleven hours. **Third instance of cause `I` on this campaign.**
