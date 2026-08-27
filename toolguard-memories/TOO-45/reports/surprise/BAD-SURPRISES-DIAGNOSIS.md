---
title: TOO-45 - why 03, 44 and 79 were the bad surprises
type: note
tags: [task-memory, TOO-45, measurement, architecture]
permalink: toolguard/too-45/reports/surprise/bad-surprises-diagnosis
---

# The three bad surprises, diagnosed

Source-only recall: **03 = 75.2%** (302 lines missed), **44 = 49.5%** (139), **79 = 13.8%** (370). Between them they carry **811 of the 958 missed production lines in the whole series (85%)**.

## The common mechanism, stated first

**All three tickets were accurate about the present and wrong about the future, in the same specific way: each proposed a fix confined to the modules where the symptom was observed. In all three the real fix created or relocated a home.**

An estimator reading "the extractor must descend" predicts extractor work. It is not being stupid; it is believing the ticket.

---

## Ticket 03 — the cycle was the symptom, not the disease

**Claims about the present — all TRUE.** The bidirectional runtime cycle exists; the call counts (4 and 3 in one real decision) are measured; the Protocols were added and do make the shape visible; no import graph shows it.

**Claims about the fix — both wrong.** The ticket names two candidate shapes: *"pass the level matches as data rather than as a callable"*, or *"invert the iteration so `resolve` drives and `permission_resolution` becomes a pure cascade."* **Both are rewirings of the two existing modules.** The actual fix extracted a third: `file_matching.py`, **278 lines, the single largest miss in the series.**

**Effort claim wrong too**: *"3-6 hours by analogy"*. Production alone came to 1,220 lines across 10 files.

### The architectural pattern

**A responsibility with no home, injected as a callable instead of extracted as a module.** `permission_resolution` needed per-level matching; `resolve` supplied it through an injected callable. The cycle was how a homeless responsibility manifested.

The ticket reasoned by analogy to the `compound` cycle — *"this cycle is a narrower case"* — and that analogy is what misled it. The compound removal worked by **moving policy**. This one needed **naming a thing that did not exist**. Those are different operations, and the ticket treated the second as a smaller instance of the first.

**Discovery during work: not the driver.** The scored file records a long tail of small prose-driven test touches, cause `E`. The surprise was structural and present from the start.

---

## Ticket 44 — the ticket contained the right answer, in its last section

**Claims about the present — all TRUE and unusually well measured.** 485 patches, 0 autospec, 18 of 79 files using the mixin, `Path.home()` 23 times across 10 files, ~157 patches purely for I/O, and the inert-mock instance in `test_auto_migrate.py` where green tests were reading the developer's real `~/.claude`.

**Zero alarms in the whole item.** Its scored file: *"Every surprise is estimator ignorance."* No hidden coupling, no latent defect, no prose coupling. **This was a clean execution that an inventory simply could not predict** — nothing in a path-and-docstring listing reveals which modules read `Path.home()`.

**But the prescription is internally inconsistent, and that is the finding.**

- Early, in the concrete tabulated sections: *"`path_utils.py` already calls it 4 times and is **the obvious owner**"*, and *"One accessor for `Path.home()`, **in `path_utils`**"*.
- Late, in the architectural discussion: it considers a dedicated `testability.py`, **rejects it on layer-map grounds** — *"a module named for testing at the bottom of the architecture, which is a stranger artifact than the one it labels"* — and concludes: *"it belongs in **its natural home**, with a docstring naming the **production** problem it solves. Testability is a consequence, not the justification."*

**That last paragraph is exactly what `ambient.py` is.** The ticket got the architecture right and then buried it 60 lines below a table that said something else.

### The architectural pattern

Same as 03: **a responsibility with no home** — here diffuse rather than injected, 10 read sites and no seam.

**But the transferable lesson is about ticket construction, not architecture: the ticket's best reasoning was in its last section and its most quotable prescription was in its first.** Anyone skimming for "what do I do" hits the table. The estimator did, and predicted `path_utils`/`testability.py`.

---

## Ticket 79 — accurate diagnosis, wrong localisation, and a genuinely coupled field

**Claims about the present — TRUE, and the reasoning is the best of the three.** The floor does not fire inside `$(...)`; the old behaviour really was accidental (a `str.split()` coincidence, with a table showing the discriminator); closing it is a new capability rather than a regression fix; and the corpus-blindness section is correct and important — a fixture with `undecidable_fallback = "allow_with_no_warnings"` cannot distinguish "the floor fired" from "the floor does not exist".

**One claim false, and it is load-bearing**: *"the extractor must descend into command substitutions the way it now descends into `if`/`while` conditions."* **The grammar already descended.** The consuming Python discarded the field — the third instance in this campaign of *"the grammar already knows, the Python throws it away."*

**More importantly, the fix's mass was never in the extractor.** `command_extractor.py` took 59 lines. `compound.py` + `resolve.py` took **357** — the second-largest miss in the series.

### The architectural pattern — and this one is a genuine defect

**`kind` is one field answering two questions.** Raising the floor reclassifies a leaf from `'plain'` to `'inline_code'` — and `kind` **also** drives audit decomposition. So a correct three-line floor fix collapsed the audit breakdown, and restoring it meant touching `sub_matches`, which verdict derivation also reads.

That is **"one structure, two questions"**, recorded in this project as having caused two prior defects — once silently downgrading an unoverridable `hard_deny` to `ask` with a green suite.

**The option never priced**: mark the leaf floored via a **separate flag**, leaving `kind` alone. The ticket did not consider it because the ticket was not about `kind` at all.

**Discovery during work: this is the only one of the three where it drove the surprise.** Eleven agent runs, four review rounds, and **three security weakenings** — each introduced by the fix for the previous one. Two tickets (90, 91) were filed from what the work exposed.

---

## Verdict

| | 03 | 44 | 79 |
|---|---|---|---|
| present-tense claims | all true | all true, well measured | all true |
| fix-shape claim | **2 of 2 wrong** | **inconsistent with itself** | **wrong localisation** |
| architectural pattern | responsibility with no home | responsibility with no home | one field, two questions |
| discovery drove it? | no | no | **yes** |
| avoidable by a better ticket? | partly | **yes** | no |

**Two of three are the same disease**, and it is the one an estimator cannot see: a responsibility that exists but has no module. It shows up as a cycle (03) or as diffusion (44), and it is cured by extraction — which is why *"does this change carve out a new module?"* recovers ~85% of the missing mass.

**44 was avoidable.** Its own last section had the answer; the ticket's structure hid it.

**79 was not.** No amount of ticket care predicts that `kind` is load-bearing in two subsystems — that is a property of the code, and the only instrument that could have surfaced it is the one the campaign kept re-learning: **ask what else reads this field before changing what it means.**
