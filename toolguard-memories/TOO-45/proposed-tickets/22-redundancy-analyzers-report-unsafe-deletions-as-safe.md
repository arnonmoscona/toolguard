---
title: Redundancy analyzers report unsafe deletions as safe
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/22-redundancy-analyzers-report-unsafe-deletions-as-safe
---

**PARTIALLY FIXED in `05f786d`.** HR1, HR3, HR4, the zero-population family, and RD1 case-folding are fixed (all `toolguard/tools/hierarchy.py`); still open: HR2's note still claims a rule "can be dropped" (`hierarchy.py:400`), RD1 space-collapsing, and RD2 provenance (`toolguard/tools/redundancy.py:197`).

> **THE SAME DEFECT IS LIVE IN THE HIERARCHY ANALYZER, MEASURED 2026-08-14 — with 7 RED tests.** `find_cross_layer_redundancies` feeds the **maintenance skill's report directly** (`maintenance.py:193`), so these reach an operator as *"the more-specific copy is redundant and can be dropped"*:
>
> - **HR1, allow -> deny.** Project `allow git push:*`, intermediate `deny git push:*`, user `allow git push:*`. The finding names **user** as the cover; dropping the copy it calls redundant makes **mid** decide, and `git push` goes **`allow` -> `deny`**.
> - **RD1 cross-layer, allow -> ask — NEW, not previously in the queue.** `git status:*` is reported as covered by **`Git status:*`**; dropping it turns `allow` into `ask`. RD1's normalisation problem was known *within* a layer; this is it **across** layers.
> - **HR4**: `migration_effect_to_dict` emits `"list_type": "deny"` for a migration whose **allow** list is what `migrate_config` actually moved. Measured on a layer holding `whoami:*` in both lists: the deny list was untouched.
>
> **Also measured, and latent rather than live**: `migrate_config` **silently deletes a rule** when `to_provenance` matches no layer — the removal lands, the addition no-ops against `with_layer_rules_replaced`. No production constructor reaches it yet.
>
> **One deliberate non-pin, for this ticket's benefit**: the finding's note text ("*the more-specific copy is redundant and can be dropped*") was left unasserted, because HR2 says that sentence is itself wrong and must change — pinning its wording would fight the fix. The substance is carried by the RED test instead, which uses the note as its failure message.
>
> **INDEPENDENTLY REPRODUCED AGAINST LIVE CODE 2026-08-12** by the test-repair campaign. This ticket's claims hold; nothing in it needed correction.
>
> - **§3 (RD2) reproduced exactly.** Native `Bash(*)` (takeover-neutralised) + hook `Bash(*)`, `Bash(ls:*)`, takeover on, corpus `['git status']`: `_config_without_allow('*')` strips the **native** copy, and the finding is reported against `toolguard_hook`. **The live blanket allow is reported deletable on the strength of a replay that removed something already dead.**
> - **§5 reproduced.** `allow=['npm publish:*']` with corpus `['ls -la']` yields a corpus-redundant finding for `npm publish:*`. **A never-exercised rule is indistinguishable from a genuinely covered one** — the analyzer cannot tell "the corpus proves this is covered" from "the corpus never tried".
>
> **NEW, and it changes how the report should be read:** a corpus finding **names the covering rule as redundant too**. With `git status:*` and `git:*` and an all-`git status` corpus, *both* are reported. That is correct per the documented contract, but it means **acting on the report by deleting everything it lists removes the coverage entirely.** Now pinned by `test_corpus_redundant_rule_detected`.
>
> **Two mechanisms were deliberately left unpinned**, because a test either way would preempt this ticket's own undecided fix direction: RD1's normalisation policy (normalise like the matcher, or relabel findings as spelling duplicates) and RD2's layer attribution. Both are measured and reproduced above; neither is asserted.
>
> Module coverage went from 10/32 mutations surviving to 6/32, and every test is now killed by at least two mutations.
>
> **Candidate dead branch found:** `find_corpus_redundant_allows`' `if config_without is config: continue` guard appears unreachable — every pattern from `per_layer_rules` is locatable by `normalize_entry`. No config could be constructed that reaches it. Worth removing when RD-R1 rewrites the function.

# Redundancy analyzers report unsafe deletions as safe

Two engines find "redundant" rules: `hierarchy.find_cross_layer_redundancies` (across layers) and `redundancy.py` (within a layer, statically and against the corpus). **Both can name a rule whose removal changes decisions**, and both say so in prose or in the finding's own `note` string.

Found during the TOO-45 #07 sweep by executing the docstrings rather than reading them. Full reproductions in `reports/follow-up-queue.md`, rows `HR1`–`HR3` and `RD1`–`RD2`.

## 1. Cross-layer: an intermediate layer takes over (HR1)

`hierarchy.py` said, in three places, that a specific copy whose broader twin exists *"can be dropped with no change in behaviour"*. The scan reads **allow lists only**, so it never sees a deny in between:

```
project allow  git push:*
intermediate   deny  git push:*
user allow     git push:*

finding: ('git push:*', proj -> user)
before drop: allow   |   after drop: deny
```

Same result when the covering user layer itself holds both an allow and a deny. The docstrings are corrected; **the finding's `note` string still reads "the more-specific copy is redundant and can be dropped"** (HR2), so the code and its own documentation now disagree by design — strings were out of scope for the sweep.

`_nearest_broader_cover`'s *"the layer that would take over if the more-specific copy were dropped"* was the same error in a fourth place: in the probe above, the layer that takes over is the **intermediate** one, which is not what the function returns.

## 2. Within a layer: normalisation is coarser than matching (RD1)

`_normalised_body` case-folds and collapses runs of two-or-more spaces. **The matchers do neither.** So two rules can share a normalisation key and match disjoint command sets:

```
'Git *'          'git *'          same key   on 'git status':  left=False right=True
'a  b:*'         'a b:*'          same key   on 'a  b x':      left=True  right=False
'[regex]^Git '   '[regex]^git '   same key   on 'git status':  left=False right=True
'[glob]/Home/**' '[glob]/home/**' same key   on '/home/x':     left=False right=True

FLAGGED: git * | Duplicate of 'Git *': normalises to the same pattern
```

The docstring justified the folding with *"both patterns resolve identically in the toolguard matcher (the trailing whitespace in the command portion is ignored when `args` is `*`)"* — the wrong mechanism (`permissions.py:140-141` strips unconditionally, not only for `*`) and the wrong conclusion.

**`hierarchy.py` imports `_normalised_body` and inherits this**, while saying nothing about it.

## 3. Corpus strategy: the rule tested is not the rule reported (RD2)

The sharpest of the set. `find_corpus_redundant_allows` iterates takeover-**filtered** `per_layer_rules`, but `_config_without_allow` re-discovers the owning layer by searching **raw** `layer.content`. When two layers hold the same pattern and the first is neutralised by takeover, it strips the dead copy and leaves the live one:

```
native layer        Bash(*)                    <- neutralised by takeover
toolguard_hook      Bash(*), Bash(ls:*)        <- live
takeover: on

per_layer_rules: native allow=()   hook allow=('*','ls:*')
  loop reaches '*' at the HOOK layer
  _config_without_allow strips '*' from the NATIVE layer  -> no-op
  replay diff: empty
  FINDING pattern='*' attributed to toolguard_hook
```

The removal that was replayed is not the removal that is reported. The user is told the live blanket allow is redundant, on the strength of a replay that removed something already dead.

## 4. A blind spot both engines share (HR3)

A duplicate spanning two layers at the **same** specificity is found by neither: `hierarchy`'s cover test is a strict `spec > specificity`, and `redundancy` scans within a layer. Verified — both return `[]`.

This is not hypothetical. `config._discover_levels` places `toolguard_hook_rules` files at the **same** specificity as `~/.claude`, which is exactly the split the project documents and recommends.

## 5. What a zero corpus diff actually establishes

`find_corpus_redundant_allows` claimed *"every command that R would have matched is already covered by another rule"* — in the module docstring and in the function, and contradicted three lines below by the function's own `Note:`. A zero diff means **no corpus entry distinguished the two configs**; a corpus that never exercises R gives the identical result. Corrected in both places.

## Fix direction

1. **RD2 first** — it is a wrong answer, not an incomplete one, and the fix is small: `_config_without_allow` should take the `provenance` the caller already has instead of searching for the layer. That removes the loop, the hazard comment, and the defect together (`RD-R1`).
2. **Stop asserting deletability.** Both engines produce *candidates for review*. The `note` strings (HR2) and any remaining prose should say what was tested — "no corpus entry distinguished the two configs", "a broader copy exists at layer X" — never "can be dropped".
3. **Make cross-layer read deny/ask, not just allow** (HR1). A cover test that ignores intervening denies cannot answer the question it is asked.
4. **Decide on RD1**: either normalise the way the matcher matches (no case folding, no space collapsing), or keep the coarse key and label its findings explicitly as spelling duplicates that may not be behavioural ones.
5. **HR3 needs a decision, not a fix** — equal-specificity duplicates are structurally invisible to both engines, and that is the configuration the docs recommend.

## Relationship to the other tickets

Ticket 20 covers the **consolidation** engine, which is separate: consolidation rewrites rules and `--apply` enacts it, while these two only report. But 20's `RA1` — the approval diff carrying the writer's normalisation — reaches these findings too, since a user acting on a redundancy finding goes through the same apply path.

Tickets 17 and 18 (matcher under- and over-matching) are upstream of §2: any engine reasoning about whether two patterns cover the same commands inherits the matcher's defects.