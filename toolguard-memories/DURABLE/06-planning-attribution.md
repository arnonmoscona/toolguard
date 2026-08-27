---
title: Planning attribution — which review rounds were caused by insufficient planning
type: note
permalink: toolguard/durable/06-planning-attribution
tags:
- TOO-45
- process
- durable
---

# 06 — Planning attribution: which review rounds were preventable by analysis

**The question**: of the blinded review rounds in `TOO-45/reports/`, which were needed because of insufficient planning, and which because of something only discoverable by running the code?

## SCOPE — this is NOT about feature planning — Arnon, 2026-08-25

**Arnon, 2026-08-25:**

> *"Feature planning is distinct from nearly all planning that was done here — even if it were to be done in an agentic loop."*

**This is the sharpest limit on this document and it applies to every number in it.** The eight tickets whose rounds were read — **18, 39, 44, 74, 77, 78, 79, 80** — are without exception *repair* work: fixing a defect, refactoring a mechanism, or rewriting prose about existing behaviour. **Not one is new-feature development.** So what is measured here is **repair-brief planning**: how well an agent specified a change to code that already existed and whose desired behaviour was already decided.

Feature planning answers questions this corpus never asks — what should this do, who is it for, what is in and out of scope, how will we know it worked, what does it foreclose. **None of those can be "insufficient" in the way measured here**, because the tier-1 bar used throughout this document is *"the information existed in the repository before implementation and nobody read it."* That bar is meaningful only when the answer is already written down somewhere. In feature work it usually is not written down anywhere, because it has not been decided yet.

**So do not carry these percentages across.** In particular the headline split — *"planning would have removed most of the prose rounds and almost none of the behaviour rounds"* — is a statement about **refactor** planning. The prose rounds were preventable because the truth was already in the repo; that condition is exactly what feature work lacks. Whether an agentic loop can do feature planning well is **unmeasured here**, in either direction, and this document is not evidence for or against it.

**The one thing that probably does transfer** is the mechanism in *"repair briefs drop the previous round's non-blocking findings"* below — that is a property of how briefs are written and handed off, not of what kind of work they describe. Treat even that as a hypothesis outside repair work.

**This document is written in three tiers and the tiers are not interchangeable.** Tier 1 (CONFIRMED) meets a full evidence bar: a verbatim finding, a named cheap preventive step, and independently checked evidence that the information existed before implementation. Tier 2 (JUDGED) is a reasoned opinion over incomplete evidence, and every entry states the gap, the confidence, and what would change my mind. Tier 3 (UNCLEAR) is the residue. **A tier-2 entry is an opinion; do not quote it as a measurement.**

---

## Headline

| | count |
|---|---|
| Review-round files read in full | **30** (tickets 18, 39, 44, 74, 77, 78, 79, 80) |
| Gate-level findings examined (blocking findings + the 2 medium findings on the two PASS grammar reviews) | **82** |
| **CONFIRMED planning-preventable** | **20** (24%) |
| **JUDGED planning-preventable, with stated confidence** | **24** (29%) |
| **EXECUTION-ONLY — rejected as planning-preventable** | **32** (39%) |
| **UNCLEAR** | **6** (7%) |
| Rounds whose **entire** blocking set is CONFIRMED planning-preventable — i.e. the round would not have failed without them | **4 of 30** |
| Rounds whose blocking set is *majority* planning-preventable across tiers 1+2 | **11 of 30** |

**The rejected count is the load-bearing half of this table.** Thirty-nine percent of the gate findings in this campaign could not have been found by any amount of reading — they were found by differential execution against `HEAD`, by running real `bash`, by building rejected grammar variants and measuring them, or by driving the real hook subprocess. Several of those were security defects that fail silently. Nothing in a planning phase reaches them.

**A structural split runs through the whole data set and it is the most useful thing here.** The findings sort almost cleanly by *what kind of review the round was*:

| round type | tickets | dominant finding class |
|---|---|---|
| **Prose reviews** (comments, docstrings, message strings) | 44 r4–r6, 77 r1, 80 r1–r3 | **planning-preventable** — internal contradictions, claims refuted by a file in the same repo, project rules already written down |
| **Behaviour / logic reviews** | 18 r1–r2, 39 r2–r3, 78 r2/r4/r5, 79 r1–r4 | **execution-only** — measured differentials, shell oracles, config-shape interactions |
| **Grammar reviews** | 77 phase 1 + delta | **execution-only** — both PASSed; every finding came from generating and measuring rejected variants |

So the honest answer to the user's hypothesis is not one number. It is: **planning would have removed most of the prose rounds and almost none of the behaviour rounds.** Details and the cost arithmetic are in the verdict section.

### What "examined" means here

I read all 30 surviving round files end to end and classified every blocking finding in each. Only the 20 tier-1 cases were then independently re-verified by me against the repository (`git show`, `grep`, reading the cited file at the cited line). The tier-2 and tier-3 classifications rest on the review text alone.

Two known limits on this data set, both inherited from `05-campaign-statistics.md`: **ticket 44's rounds 1–3, ticket 78's round 1 headline count, and ticket 80's rounds 1–2 headline counts have no surviving files**, so the population is the rounds that survive, not the rounds that happened; and cost figures are agent self-reports with no meter behind them.

---

## Tier 1 — CONFIRMED planning-preventable

Ordered strongest first. Each carries the verbatim finding, the preventive step, and the evidence the information pre-existed.

### C1. Ticket 77, prose round 1 — three code comments assert an architectural prohibition that the layer map contradicts

**Verbatim finding** (`review-77-round1.md`, blocking finding 1):

> Measured against `.pyscn.toml`: `parser` is listed in the **same** layer as `permissions` and `permission_resolution` (`engine`, line 212), and the rule block `from = "engine"` allows `["engine", "config", "observability", "foundation"]`. Engine-to-engine imports are legal and machine-checked as legal.

The three sentences it refutes: `permissions.py:18` *"…which is what keeps this module **below the parser in the layering**."*; `permission_resolution.py:384` *"this module **sits below the parser in the layering**"*; `config_types.py:369` *"consumed by `toolguard.permissions`, **which may not import the parser package**."*

**What would have caught it**: opening `.pyscn.toml` and reading the `engine` layer's `packages` list — the single machine-readable declaration of the constraint being asserted.

**Evidence it was knowable beforehand — verified by me, not taken from the review**: `git show 19299d9:.pyscn.toml` line 212 reads `packages = ["permissions", "compound", "resolve", "parser", "permission_resolution", "file_matching"]`, and commit `19299d9` is dated **2026-08-10**, ten days before this round. Both modules have been in the same layer for the whole campaign.

**Why this one is the strongest case in the set**: the review names the cost precisely — *"in a repo whose architecture document exists specifically to separate what is machine-checked from what is convention, telling a reader that pyscn enforces this is the expensive kind of wrong."*

---

### C2. Ticket 80, prose round 1 — the tool's own front-door docstring says "five modes" fourteen lines above "Six modes"

**Verbatim finding** (`review-80-round1.md`, B1):

> The section heading below was updated to `Six modes` and the summary line was not. Six is the correct count (`--layers`, `--predicates`, `--metrics`, `--mocks`, `--ambient`, `--guard`). The module's first sentence is false.

**What would have caught it**: reading the module docstring of the file being edited, top to bottom, once. The two statements are fourteen lines apart in one file, both inside the diff's own blast radius.

**Evidence it was knowable beforehand**: the change *is* the addition of the sixth mode. The correct count was established by the change itself, and the contradicting line was in the same docstring the change edited.

---

### C3. Ticket 80, prose round 2 — a test's stated justification cites a pre-push checklist that does not exist

**Verbatim finding** (`review-80-round2.md`, B2), on `test_architecture.py:722`:

> False. Repo-wide grep for `--ambient` (excluding `toolguard-memories/`) returns hits only in `tools/architecture_fitness.py` and the two test files. `CLAUDE.md`'s pre-push section names coverage, docs, a version bump, release notes, the maintenance skill, `/documentation-review` and `pyscn` -- not `architecture_fitness.py`.

**What would have caught it**: `grep -rn -- '--ambient'` before writing "whose exit code is what the pre-push checklist reads".

**Evidence it was knowable beforehand**: `CLAUDE.md` predates the change and did not name the mode. The review notes the Given is *"load-bearing here: it is the entire stated justification for a second test that would otherwise duplicate the first"* — so this is not a decorative sentence.

*(Round 3 then found the mirror image: the fix added the sentence to `CLAUDE.md`, where round 3's B1 measured three counterexamples to it. See J8.)*

---

### C4. Ticket 74, round 1 — a new docstring states the opposite of what `tool_spec.py`'s own module docstring says

**Verbatim finding** (`review-74-round1.md`, B2):

> `additional_supported_tools` feeds only `all_supported_tools` at `config_validation.py:67`, used for validation warnings. It never reaches `governed_tools()`. The claim also contradicts `tool_spec.py:4` ("extends the recognized-tool set") and `config_validation.py:10` ("recognized by adding it to `additional_supported_tools`").

**What would have caught it**: reading the module docstring of the registry the new sentence describes.

**Evidence it was knowable beforehand — verified by me**: `toolguard/tool_spec.py` lines 4–5 currently read *"A user's ``additional_supported_tools`` config setting extends the **recognized-tool** set without changing anything here."* The round-1 scope was `hook.py`, `test_hook.py`, `test_tool_spec.py` — `tool_spec.py` itself was **not in the diff**, so that correct sentence was sitting untouched in the tree while the wrong one was being written.

---

### C5. Ticket 74, round 2 — three fresh change-history paragraphs shipped in the same commit as a sweep deleting nine of them

**Verbatim finding** (`review-74-round2.md`, BL-1):

> All three are **true** — I verified each by execution (see below) — so this is not the round-1 falsity class. It is a standard violation: the comment standard's `test/` section says a test docstring "keeps its Given/When/Then and **that is all it keeps**", and its Cut list names "change history in any form".

**What would have caught it**: applying the change set's *own* stated standard to the change set's own new prose.

**Evidence it was knowable beforehand — verified by me**: `TOO-45/TOO-45 comment standard.md:103` reads verbatim *"A test docstring keeps its Given/When/Then and **that is all it keeps**; every other comment in a test file is deleted outright."* The commit under review (change set B) was a sweep removing nine such markers under that exact rule.

**Cost of the round it caused**: `review-74-round2` — ~1h05m, ~$9–12, 11 files (Table B, `02-campaign-cost-data.md`). It reported **one** blocking finding, and it is this one. This round exists because of a rule the same commit was enforcing elsewhere.

---

### C6. Ticket 44, prose rounds 4 and 5 — the operative checklist in the file being edited was not updated with the prose eight lines above it

**Verbatim finding** (`review-44-round4.md`, G.1):

> This is the finding with real cost. The section's prose was correctly updated for ticket 44; the operative checklist eight lines below it was not, so the part an agent actually ticks through is the stale part.

Round 5 then measured the consequence (`review-44-round5.md`, F3):

> **Ran it verbatim.** Three hits outside the exemptions, *all three introduced by this change*: `test_error_log.py:211`, `test_hook_error_reporter.py:102`, `test_hook_error_reporter.py:290`. […] So an agent ticking this checklist on the next push is told that the change's deliberate, doc-endorsed idiom is "a missed retrofit ... to fold into the mixin".

**What would have caught it**: running the checklist that lives in the file you just edited, before you stop editing it.

**Evidence it was knowable beforehand**: `.claude/rules/test-config-isolation.md` contained the checklist before the change; the change edited the prose paragraph immediately above it. Round 6 then found a *third* generation of the same defect (`review-44-round6.md`, findings 12 and 13: *"As written, the two consecutive bullets give opposite instructions for an uncommented `ambient.` hit"*), and named the pattern outright: *"which is the exact failure mode this file has already produced twice."*

---

### C7. Ticket 44, prose round 5 — a stale mechanism claim about a file the change had just rewritten

**Verbatim finding** (`review-44-round5.md`, F4):

> Verified by grep: **`env_config.py` contains no `Path.cwd()`.** It calls `ambient.cwd()` (line 29), and reads its env vars via `ambient.env_var()`. The substitution pass updated the config.py bullet […] and wrote the new paragraph, and left this one asserting the pre-change mechanism -- in a change whose entire subject is that substitution.

**What would have caught it**: `grep -n 'Path.cwd' toolguard/env_config.py`, in the same pass that performed the substitution.

**Evidence it was knowable beforehand**: the substitution *is* the change. Every site it touched was enumerable from the diff.

---

### C8. Ticket 44, prose round 6 — "One read point per fact" refuted by two shipped call sites the repo's own tests already document

**Verbatim finding** (`review-44-round6.md`, finding 1):

> `USER_LEDGER_PATH = Path.home() / ".toolguard" / "decisions.json"` is a module-scope read of home in the shipped package -- a second read point for the home fact that no binding and no patch can move (the repo's own `test_tools_decision_ledger.py:37` and `test_tools_maintenance.py:1604` already document that).

**What would have caught it**: `grep -rn 'Path.home()' toolguard/` before writing a claim about how many read points there are.

**Evidence it was knowable beforehand**: the review names two existing tests that documented the second read point. Both predate the change.

---

### C9. Ticket 18, round 3 — the reference doc misattributes a published recipe to a file that never carried it

**Verbatim finding** (`review-18-round3.md`, B1):

> `agent-guides.md` never published that shape. Its `[hard_deny]` block at `HEAD:docs/agent-guides.md:182-190` is: […] There is no `curl` deny.

**What would have caught it**: `git show HEAD:docs/agent-guides.md` and reading the block being cited — the review's own method, and one command.

**Evidence it was knowable beforehand**: the file is in the repository at `HEAD`; the claim was written about it without reading it.

**Cost of the round it caused**: `review-18-round3` was ~14 minutes / ~$4, and this was its **only** blocking finding. A whole gate round, and a repair pass, for a citation nobody checked.

---

### C10. Ticket 18, round 4 — the replacement recipe was validated against one ordinary use and three attacks

**Verbatim finding** (`review-18-round4.md`, B2):

> The direction is fail-closed, so this is not a hole. It is a guidance defect, and it is the mirror image of the reason the previous recipe was rejected: that one was checked against nine attacks and zero ordinary uses; this one is safe against every attack and fails almost every ordinary use.

Measured: **14 of 15 ordinary variants of the same intent are HARD-DENIED**.

**What would have caught it**: writing a must-permit list of realistic invocations *before* choosing the replacement, and scoring against it — the step round 5 later performed and recorded (*"I wrote the must-permit list from realistic local-dev curl usage before reading the regex"*).

**Evidence it was knowable beforehand — verified against the intervening documents**: `review-18-round3.md` N1, written before the repair, already stated it in terms the repair had in hand: *"Flags-before-URL is the dominant curl spelling, so the 'narrow exception' a user asks for will not work."* The repair report (`TOO-45 review-18-round3 repair - coder implementation report.md`) confirms it read N1 and then verified the replacement as *"the exact command is allowed; a different flag spelling, an extra flag, and a second URL are all still denied"* — one permit, three denies.

**Honest caveat on a tempting piece of evidence**: the auto-memory rule `feedback_test_what_a_rule_permits.md` states exactly this lesson, but its mtime is `2026-08-20 17:23`, **after** this repair (`16:02`) and after round 4's review (`16:15`). It was written *from* this incident and was not available to prevent it. The pre-existing evidence is the round-3 review text, which is sufficient on its own.

---

### C11. Ticket 18, round 5 — a new test's docstring describes a recipe the same diff replaced

**Verbatim finding** (`review-18-round5.md`, Blocking 3):

> False, and contradicted by the diff it ships in. Both `configuration.md` and `agent-guides.md` were corrected to the **bounded-flag-set `[regex]` carve-out**; the exact-invocation form is explicitly the *rejected* alternative in those same files.

**What would have caught it**: reading the two doc files in the same diff before writing a docstring that points at them.

**Evidence it was knowable beforehand**: both files are in the same change set.

---

### C12. Ticket 18, round 6 — the agent-facing doc omits a disclosure its sibling doc, edited in the same change, states correctly

**Verbatim finding** (`review-18-round6.md`, B2):

> **`docs/configuration.md` states the limit plainly and passes**: *"The `Bash(...)` DEFAULT wrapper with no wildcard matches only that literal command line."* That sentence is exactly right and is the whole disclosure. **`docs/agent-guides.md` carries no equivalent sentence.**

Measured: **1 of 16** realistic health-check invocations allowed.

**What would have caught it**: diffing the two documents' claims against each other — they are edited in the same commit and `docs/agent-map.md` routes the reader to the one missing the sentence.

**Evidence it was knowable beforehand**: the correct sentence exists in the same change set, in the sibling file.

---

### C13. Ticket 77 grammar delta — a one-token fix the previous review had pre-authorised on a condition that then fired

**Verbatim finding** (`review-77-grammar-phase1-delta.md`, M1):

> This is the same residual-bypass class as M1 in the previous review, whose own L2 said it was worth a ticket line "unless M1 is being fixed anyway -- in which case `assignment_name ("+=" / "=")` is a one-token addition". M1 *was* fixed here; the attached condition fired and was not taken.

**What would have caught it**: re-reading the prior review's findings list when scoping the repair, and checking which conditional recommendations the repair's own scope activated.

**Evidence it was knowable beforehand**: `review-77-grammar-phase1.md` L2, written before this round, states the condition and the exact fix. The delta review then measured the fix at **0 differences over 28,770 corpus commands**, so the cost of taking it was nil.

---

### C14. Ticket 39, round 2 — a docstring's fail-closed claim refuted by one grep of `config.py`

**Verbatim finding** (`review-39-round2.md`, B1):

> The runtime does the exact opposite. `Configuration._pool_hard_deny_entries` reads `section.get("deny", [])` and `section.get("allow", [])` and nothing else. Generic-by-key is fail-closed applied to the *before* snapshot and fail-**open** applied to the *after* snapshot — and the check applies it to both.

**What would have caught it**: reading `_pool_hard_deny_entries` — the runtime function whose behaviour the new docstring asserts.

**Evidence it was knowable beforehand**: `config.py:960`/`:966` are pre-existing and untouched by the diff. The review flags it against the campaign's own standard: *"Under the project's own comment standard this is rule 0 (a claim reaching outside its own file, which is where the false ones live)."*

---

### C15–C20. Remaining CONFIRMED cases, compactly

| # | round | verbatim core of the finding | preventive step | pre-existing evidence |
|---|---|---|---|---|
| C15 | 78 r3 B1 | *"That is not an incidental behaviour — it is asserted by `test_a_tilde_spelled_rule_still_fires_on_the_absolute_spelling`, added by this same diff, roughly 650 lines away."* | read the test you added before writing the comment that contradicts it | the test and `docs/architecture-as-built.md:437`'s correct qualifier ("the one route **among the three**") both in hand |
| C16 | 78 r3 B3 | *"`_involves_a_symlink` deliberately does not examine a relative path's ancestors; its own docstring says so."* | read the docstring of the function whose behaviour the doc row describes | pre-existing function docstring, untouched by the diff |
| C17 | 79 r3 B1 | *"that test is **added** by this diff -- it appears as `+    def test_unrelated_substitution_is_not_itemised(self):`"* — while `technical-notes.md` called it *"an existing, pinned test this round of work did not have authorization to touch"* | read your own diff before writing permanent documentation about it | the diff |
| C18 | 80 r1 B3 | *"Bumping `AMBIENT_PYTHON_PIN` **is** how the gate is satisfied -- it is the only use of the constant other than the message text"* | count the constant's references before claiming the gate "cannot" be satisfied by bumping it | the constant, in the file being edited |
| C19 | 80 r1 B7 | *"`USER_LEDGER_PATH` became `user_ledger_path()` in this change. `.claude/rules/testing.md`: 'Keep the description and the code in sync in the same edit.'"* | grep the old symbol name after a rename | the rule file, and the rename is the change |
| C20 | 80 r2 B1 | *"The change's own test `test_an_owner_entry_exempts_one_member_not_the_whole_module` asserts the opposite of what this sentence implies, and the mode's section in the module docstring states the pair-keying correctly."* | read the test and the docstring in the same file | both written by the same change |

---

## Tier 2 — JUDGED

Reasoned opinions over incomplete evidence. Each states what I have, the gap, the opinion, a confidence, and the single piece of evidence that would change my mind.

### J1. Ticket 39 round 1 B1 — `hard_deny.deny -> hard_deny.allow` still writes

**Evidence I have**: the review quotes `docs/configuration.md:986` (*"allow: carve-out EXCEPTIONS to hard_deny.deny"*) and states that `_hard_deny_patterns` *"pools **every** list-valued entry under `hard_deny` into one set, so `deny` and `allow` are indistinguishable to the egress check"*, with `_hard_deny_patterns` untouched by the diff. Both facts were readable before implementation.

**The gap**: the review established the *consequence* by sandboxed execution (`rm -rf /` going from deny to allow). I cannot show that the implementer would have made the leap from "the pooling function pools both sub-lists" to "therefore the strongest tier is placement-blind" without running it.

**Opinion**: planning-preventable. The ticket's entire subject is placement, `hard_deny` has exactly two sub-lists, and the function that ignores the distinction was in the file being modified.

**Confidence**: moderate-to-high.

**What would change my mind**: evidence that `docs/configuration.md`'s carve-out semantics were ambiguous or contradicted elsewhere at that date — the review's finding depends on `hard_deny.allow` negating rather than adding.

### J2. Ticket 18 round 4 B1 — "No PATTERN carve-out is both safe and usable here", asserted in four files

**Evidence I have**: the review's own diagnosis — *"The supporting argument is a false dichotomy. It considers exactly two regexes […] It never considers a **bounded flag set**"* — and its explicit link to a written project rule: *"This is the same shape the global CLAUDE.md warns about under compression: 'only', 'every', 'never' appear where the original was hedged."* The repair report confirms exactly two regexes were measured.

**The gap**: producing the counterexample regex required construction and measurement. The *rule* (do not universally quantify) was available; the *counterexample* was not free.

**Opinion**: planning-preventable as a hedging failure, not as a discovery failure. The cheap step is not "find the working regex" — it is "do not write a universal negative into four files, one of them an agent-facing skill, on the strength of two samples."

**Confidence**: moderate.

**What would change my mind**: a demonstration that scoping the claim honestly ("neither of the two shapes we tried works") would still have failed the gate.

### J3. Ticket 78 round 3 B2 — the `expand_tilde_in_command` entry added to `_command_variants` is a no-op

**Evidence I have**: *"`_command_variants` has exactly one caller, `match_command`, which by then has already closed `spellings` under `expand_tilde_in_command`"* — a one-caller function whose single caller is in the same file. Round 2 had already reported it as non-blocking N2 (*"the variant set `match_command` builds is byte-identical with and without the line"*), so it was in writing before round 3.

**The gap**: the *idempotence* argument that makes it dead needs a moment's reasoning, and round 2 established it by measurement.

**Opinion**: planning-preventable at round 3 (it was a written finding carried forward and not acted on); borderline at round 2.

**Confidence**: high for round 3, low for round 2.

**What would change my mind**: evidence that round 2's N2 was excluded from the round-3 repair brief on an explicit decision rather than by omission.

### J4. Ticket 79 round 2 B2 — the outer summary is built by re-parsing the inner summary's prose

**Evidence I have**: the review names the governing rule by title — *"This is the global CLAUDE.md's 'prose is output, not a data structure' rule, and the fix is the one that section prescribes"* — and that rule is not generic advice: it was written **from this project**, citing TOO-45's own 813-of-975 under-logging measurement.

**The gap**: the specific manifestation (a count saying 2 with three entries listed and an unbalanced bracket) was found by execution.

**Opinion**: planning-preventable in the sense that matters — the design decision to render a reason string and later split it on `" -> "` was made against an explicit, project-authored prohibition on exactly that.

**Confidence**: moderate-to-high.

**What would change my mind**: evidence that the re-parse was pre-existing rather than introduced or relied upon by this change. (Round 3 says the prose re-parse in `_combine_strictest` **is** pre-existing — which is a real pull toward "inherited defect", and is why this is not tier 1.)

### J5. Ticket 79 round 1 B5 — the new tests do not discriminate the change

**Evidence I have**: *"**1 of 3, not 3 of 3** (the brief's claim #4 is false)"*, and *"The only test that changes colour is the one asserting that `mktemp -d` must be **absent** -- it fails pre-fix because pre-fix correctly included it. That test encodes B1's loss as the desired behaviour."*

**The gap**: fail-on-revert is a cheap, mechanical, and by this point standard step in this campaign — but it is a *verification* step, not a planning step.

**Opinion**: this sits on the boundary and I judge it planning-adjacent: it is a checklist item that existed, was claimed as done in the brief, and was not done.

**Confidence**: moderate.

**What would change my mind**: nothing about the finding; only a re-definition of "planning" that excludes pre-submission self-checks.

### J6. Ticket 78 round 5 B1 — `dd if=~/.ssh/id_rsa` walks past the deny rule

**Evidence I have**: the review's own reasoning — *"This is the identical failure mode to `>~/.ssh/x`, which round B1 fixed *because* it walked past an absolute deny rule. The reason `>~` was closed and `if=~` was not is not a principled one; both are positions where the shell expands."*

**The gap**: which positions bash tilde-expands is documented in the bash manual, so it is knowable by reading — but knowing to enumerate them is exactly the insight round 4 supplied.

**Opinion**: **not** preventable before round 4; **clearly** preventable at the round-4 repair, where the right move was to enumerate every shell-expanding position once rather than patch the one that was found.

**Confidence**: high for the second half, high for the first.

**What would change my mind**: evidence that the round-4 repair brief did ask for the full enumeration and it was refused on scope.

### J7. Ticket 80 round 3 B2 — "`resolve` has one in most modules that handle paths"

**Evidence I have**: *"Measured: 22 `resolve` sites across **10** modules; **43** of the package's 78 `.py` files reference `Path` at all. 10 of 43 is 23%, not 'most'."* The same sentence was reported **non-blocking in round 1** (*"Measured: 10 of 78 modules"*) and again in round 2 (M5), before becoming blocking in round 3.

**The gap**: whether the count was ever in the repair brief.

**Opinion**: preventable, and preventable twice over — the campaign's own rule (*a category or count claim must be verifiable by running the code, or say less*) applies, and two prior rounds had already printed the number.

**Confidence**: high.

**What would change my mind**: the repair briefs for rounds 2 and 3 showing the item was explicitly deferred.

### J8. Ticket 80 round 3 B1 — the false universal escaped from the tool into `CLAUDE.md`

**Evidence I have**: *"Rounds 1 and 2 swept the tool's own paragraphs; this sentence is the paraphrase that escaped into `CLAUDE.md`."* Round 1's F1/B2 had already established that `render_ambient_text`'s *"PASS -- every read of machine state has an owner"* is false, and round 3 notes it is *"the universal the CLAUDE.md sentence in B1 was almost certainly derived from."*

**The gap**: nobody knew the sentence had been copied into `CLAUDE.md` — a grep for the claim's wording would have found it; a grep for `--ambient` had already been run in round 2 for a *different* purpose and did not cover `CLAUDE.md`'s prose.

**Opinion**: preventable by one broader grep — "where else does this claim appear?" — which is the campaign's own auto-memory lesson *"Ask what a change made FALSE"*.

**Confidence**: moderate.

**What would change my mind**: evidence that the `CLAUDE.md` line was added *after* rounds 1–2, in which case it is a new defect rather than an escaped one.

### J9–J24, compactly

| # | round | shape | opinion | confidence |
|---|---|---|---|---|
| J9 | 18 r1 B2 | `split_default_body` normalises before the shape check; *"`match_command` deliberately handles `**/<component>/**` **before** normalising — its own docstring says so"* | preventable by reading the docstring of the function being mirrored | moderate |
| J10 | 39 r1 B2 | *"When a pattern *leaves* `deny` for `ask`, there is no `deny` entry left to win anything"* — pure reasoning over one's own sentence | preventable | moderate-high |
| J11 | 39 r1 B3 | *"The check is `(restricting_before - restricting_after) & allow_after`. It reads `allow_after`"* — the docstring denies the line above it | preventable by reading one expression | high |
| J12 | 39 r2 B3 | skip-list docstring omits the `expected_patterns is not None` gate the code sits inside | preventable by reading the enclosing `if` | moderate-high |
| J13 | 39 r2 B4 | *"'Both ways' is a closed enumeration of an open set"* | preventable as a hedging failure | moderate |
| J14 | 44 r4 1.1 | `--eval` returns above the binding; *"`hook.py`'s own comment gets this exactly right by saying 'every reader **below**'"* | preventable by reading the two returns above the `with` | moderate-high |
| J15 | 44 r5 F1 | *"four lines read home directly through `Path(...).expanduser()`"* — refutes "every reader below agrees" | preventable by grepping `expanduser`; but round 4's own grep omitted the term, so the omission was not obvious | moderate |
| J16 | 74 r1 B1 | a `RED:` annotation on a green test, describing a defect that does not exist; *"this exact sentence is what produced the previous brief's false 'there is already a RED test' claim"* | preventable — running the named test is one command, and the campaign's own memory documents stale markers | high |
| J17 | 74 r1 B4 | the rewrite *"asserts fewer facts about the verdict"* than the original — droppable by `git show` of the original test | preventable | moderate-high |
| J18 | 74 r1 B5 | *"There are now three (…), and two of them are no longer below"* — a count in a docstring the change invalidated | preventable by counting | high |
| J19 | 77 r1 finding 2 | the validation message tells the operator *"contains **str, not a string**"* for the most likely input | preventable by reading the message-construction branch against its own trigger | moderate |
| J20 | 78 r1 F4/F6/F7 | code docstring drifted from the doc that states the same fact correctly; test class docstring claims a symmetry all six of its tests avoid | preventable by comparing the two copies / reading the class | moderate-high |
| J21 | 78 r5 B2 | `~`-targeted redirect moves ask→allow, *"on precisely the shape upstream gates by design"* | preventable — `.claude/rules/native-fidelity-claims.md` mandates fetching the native page before any claim in this area | moderate |
| J22 | 79 r2 B3 / r3 B3 | `audit_only`'s documented contract is not the predicate the code uses (`v.decision in ("deny","ask")`) | preventable by reading the one line | moderate-high |
| J23 | 79 r4 B1 | the fourth omission of the same family; *"The implementer's sweep asked 'what else consumes `deny_check_verdicts` or `fallback_kind`?' […] That question cannot find a fourth omission"* | preventable by the analysis the review names — enumerate what a `'plain'` part contributes — but that reframing is genuinely non-obvious | low-to-moderate |
| J24 | 44 redrift B1 | *"the material it points at is the **third** paragraph"* — an ordinal cross-reference wrong on the day it was written | preventable by counting paragraphs | high |

---

## Tier 3 — UNCLEAR

Six findings where I can form no defensible opinion, listed so the residue is visible rather than silently absorbed: `18 r2 B2` (no test pins the widening direction — depends entirely on whether the widening was known at authoring time, which only round 2 established); `39 r3 B1` (same-string move into `hard_deny.allow` — the three-function interaction is derivable but genuinely subtle); `44 redrift B2` (an assertion message stating one of two possible causes); `78 r1 F1`/`F2` (the `[glob]` "inert" claim — the review shows the *conclusion* is right for the wrong reason, and I cannot judge whether the right reason was reachable without executing `match_pattern`); `79 r2 B4` (a `technical-notes.md` overclaim whose falsity depends on a population that did not exist before the change).

---

## The pattern that costs the most: repair briefs drop the previous round's non-blocking findings

This is not one of the classification buckets, and it is the most consequential thing in the data.

**Four consecutive rounds of ticket 18 measured the same axis — whether the published `curl` hard-deny carve-out permits ordinary use — and got a worse or equally bad answer each time**, because each repair addressed the direction the last round complained about and lost the other:

| round | finding | measured usability |
|---|---|---|
| r3 N1 (non-blocking) | *"the published recipe is too narrow to be usable"* | flags-before-URL denied |
| r4 B2 (blocking) | *"safe against every attack and fails almost every ordinary use"* | **1 of 15** ordinary variants exempt |
| r5 B1 (blocking) | *"the safety claim is fine and the usability claim is not"* | **11 of 22** permitted |
| r6 B2 (blocking) | *"the agent-facing `curl` recipe never says the allow permits exactly one string"* | **1 of 16** realistic invocations allowed |

Rounds 4, 5 and 6 cost, by the campaign's own Table B, roughly **$17–19 and about 1h45m of reviewer time**, plus three repair passes. Ticket 18 ran **6 rounds** with a round curve of 2→2→1→3→3→2 — the campaign's own analysis notes it *"opened with the fewest findings of any ticket and never converged; rounds 4 and 5 each found more than round 1."*

The same shape appears three more times: 80's "most modules" claim (non-blocking r1 → non-blocking r2 → **blocking** r3); 78's dead `_command_variants` line (non-blocking r2 N2 → **blocking** r3 B2); 77's `+=` grammar gap (conditional recommendation in the phase-1 review → condition fires → not taken → re-raised in the delta review, where the fix measured at **0 corpus differences**).

**The preventive step is a planning step and it is nearly free**: when scoping a repair, carry forward the previous round's *non-blocking* findings and explicitly mark each as fixed, deferred-with-a-reason, or rejected. Every one of the four escalations above was pre-stated in writing by the round before.

---

## Counter-cases — rounds that planning could not have prevented

These bound the claim, and they are the reason the answer is not "plan harder".

### CC1. Ticket 77, grammar phase 1 — the rejected design was measured, not argued

The review **built** the two designs the author had rejected and ran the corpus through each:

> `variantA vs pre-change:  differing=280  {'parse': 88, 'extract_commands': 274, 'structured': 94}` […] 274 commands lose nested decomposition exactly as the author predicted […] It is also understated: variantA additionally turns 88 commands into parse failures.

And for the second:

> **307 real commands become parse failures** -- every bare assignment […] The greedy `?` consumes the assignment, `command_word` then fails at end-of-input, and PEG does not retry the optional with zero matches.

No reading of a PEG grammar produces "274 nested decompositions and an 88-command ASK-floor cliff". This is the purest execution-only finding in the corpus, and note that the round **PASSed** — the measurement's value was confirming two design choices, not catching a defect.

### CC2. Ticket 78 round 2 — a fail-open that only a differential against a real shell exposes

> | `$LOGNAME=root`, `$HOME` untouched | `/root` | `/home/arnon` |
>
> With `$LOGNAME=root`, an allow rule `cat /home/arnon/*` **allows** `cat ~root/.ssh/id_rsa` — a command that actually reads `/root/.ssh/id_rsa`.

The defect is that `getpass.getuser()` reads `LOGNAME`/`USER` before the passwd database while `Path.home()` reads `$HOME`, and nothing checks they agree. The review had to read the CPython source *and* run `bash -c 'printf %s ~name'` under manipulated environments to establish it. A design review reads "expand `~name` when it matches our own username" and nods.

### CC3. Ticket 79 round 1 — a security downgrade produced by a data-flow consequence nobody modelled

> `rm -rf /tmp/x` is **not merely un-itemised -- it is gone**: not judged, not recorded, and its `hard_deny` match no longer decides.
>
> ```
>   echo $(python -c "import os") $(rm -rf /tmp/x)
>      PRE-FIX : deny   rule='rm:*'   subs=[outer:allow, 'python -c ...':ask, 'rm -rf /tmp/x':deny]
>      POST-FIX: ask    rule=None     subs=[outer:ask,   'python -c ...':ask]
> ```

An unoverridable `hard_deny` became a promptable `ask`, as a side effect of reclassifying a leaf's `kind`. This was found by a `HEAD`-vs-working-tree differential and could not have been found by reading the ticket, the brief or the diff. It is also the counter-case that matters most, because the failure was **silent**: the suite was green and the corpus replay showed nothing.

### CC4. Ticket 18 round 2 — the widening direction, and where it landed

> Measured old-vs-new over a 38 × 39 pattern/command grid […]: **8 matches lost, 10 matches gained.** […] Three commands flip from hard-denied to exempt, one of them exfiltrating to an external host through a carve-out whose name says "localhost".

The change was framed — by the ticket, the brief and the doc — as a one-way narrowing. It widens, and the widening reaches a published `hard_deny` recipe. Only a grid differential over both directions finds that.

### CC5. Ticket 39 round 2 — a config shape nobody would think to model

> ```
> hard_deny.allow = 5      BEFORE  WROTE OK
> hard_deny.allow = 5      AFTER   UNCAUGHT TypeError: 'int' object is not iterable
> ```
> […] a user who hand-typed `allow = 5` cannot repair the file through any toolguard writer -- the precise "a corrupted file must not become unfixable" hazard the ticket flagged, arrived at through a different door.

The ticket *named* the hazard. The instance arrived through a type the plan had no reason to enumerate, and it was found by differentially running 169 config shapes.

---

## Verdict

**What the evidence supports:**

1. **A quarter of the gate findings in this campaign (20 of 82) were preventable by a step that costs under a minute** — a grep, opening one named file, counting a constant's references, reading the sibling document in the same commit, or re-reading the previous round's findings list. That is a real, checkable number and it is not small.

2. **The preventable findings cluster hard in prose reviews and in documentation.** Tickets 44, 77 (prose round), and 80 are dominated by them; ticket 80's rounds 1–3 alone account for 6 of the 20 CONFIRMED cases. If the hypothesis is *"planning makes documentation and comment work cheaper and more accurate"*, the evidence is strong.

3. **Four rounds of thirty would not have failed at all** but for CONFIRMED planning-preventable findings (18 r3, 74 r2, 44 r6, 80 r2), and a further seven had majority-preventable blocking sets. At the campaign's own per-round costs (~$4–13 and 14 min–2h each, `02-campaign-cost-data.md` Table B), those four rounds plus their repair passes are on the order of **$25–40 and several hours**, before counting the coordinator's time.

4. **The single largest recoverable cost is not planning-before-implementation at all. It is planning-between-rounds** — repair briefs that carry only the blocking findings forward. Four documented escalations (18's curl recipe, 80's "most modules", 78's dead variant, 77's `+=`) each burned at least one extra round on something the previous round had already written down. This is the cheapest fix identified in this document and it is not in any project rule today.

**What the evidence does NOT support:**

1. **It does not support "planning would have made the campaign cheap."** 39% of gate findings — including every finding that mattered for security — were execution-only. The three most serious defects found anywhere in these thirty rounds (79 r1's hard_deny→ask downgrade, 78 r2's `~name` fail-open, 18 r2's hard_deny carve-out widening) were all found by differential measurement, and all three were **silent**: green suites, clean replays, no warnings. Arnon's own `review-conclusions.md` reaches the same place from the other direction — *"high-coverage unit testing is necessary but mainly guards against regressions […] Randomized perturbation by blinded agents does the opposite"*.

2. **It does not support extrapolating a rate.** The round files that survive are not the rounds that happened: ticket 44's rounds 1–3, ticket 78's round 1 headline, and ticket 80's rounds 1–2 headlines are missing, and rounds are known to have run without producing a file at all. The 24% is a rate over surviving evidence.

3. **It does not settle causation for the JUDGED tier.** Twenty-four findings are ones where I can defend an opinion and cannot demonstrate a fact. Read them as opinions.

**The synthesis I would offer, stated as opinion**: this campaign's data supports a narrower and more useful claim than the hypothesis as posed. Planning is strongly cost-reducing for *claims* — anything the change asserts about the rest of the system, about a rule, about a count, about another file. It is close to worthless for *behaviour under composition*, which is where this project's genuine defects live and where blinded execution earned its keep repeatedly. The campaign's own practice already reflects half of this: it ran prose reviews and behaviour reviews as separate rounds with separate briefs. What it did not do is *staff them differently* — the prose rounds were run by the same expensive blinded-Opus reviewers as the behaviour rounds, when a large share of what they found was reachable by grep.
