---
title: brief-phase67
type: note
permalink: toolguard/too-28/brief-phase67
---

# Brief: TOO-28 Phases 6 + 7 -- documentation, then remove the scaffolding

Two phases, one brief and one commit, at Arnon's instruction (2026-09-07: *"you can do 6 and 7 together"*). They are independent: Phase 6 adds prose to `docs/`, Phase 7 removes and trims comments in `*.py`. Do 6 first, because Phase 7's rule -- *claims must still be true* -- applies to anything you write in 6 as well.

## Task

**Phase 6 (§4.5): write down what TOO-28 is FOR, not only what it configures.** The five phases that landed each documented their own setting, and that reference material is already in `docs/configuration.md`. What is missing is the frame those settings only make sense inside, plus three specific gaps listed below.

**The frame, from spec §2, and it is the whole point of the ticket:**

| | decides by | strong where | blind where |
|---|---|---|---|
| **toolguard** | exact pattern match | anything expressible as a rule; exact, testable, versioned, auditable | anything it cannot parse or pattern |
| **auto-mode guidance** | semantic judgement | undecomposable blobs, intent, novel shapes | exactness, repeatability, auditability |

> These are complementary halves with inverted strengths, **not two implementations of one control**. toolguard's blind spot is constitutive, not an unimplemented gap: compound commands it cannot decompose, heredocs, foreign inline code, a script whose contents it never sees. The ASK floor and `undecidable_fallback` exist precisely to announce it -- toolguard saying *"I cannot read this."*
>
> **Therefore TOO-28 is about the INTERFACE, not absorption.** Every setting it adds is a **handoff point**: a declaration of how much to trust the other half for a specific class of case. They are not "auto-mode variants of existing settings."
>
> **The design smell to avoid:** *"make toolguard smarter so it can handle X."* If X requires reading intent, the answer is auto-mode guidance, not a cleverer rule.

**Phase 7: remove the development scaffolding.** Arnon, 2026-09-05: *"when we're done developing, it needs to be cleaned up and only comments and docstrings with long term value, concise and claims verified must stay."*

## Scope and widening

### Phase 6 -- in scope

Prose under `docs/`, plus `README.md`/`llms.txt`/`AGENTS.md` if a pointer belongs there. **Seven items, enumerated:**

1. **The division of labour, written down**, with the blind spot stated plainly as *by design*. It is currently written **nowhere** in the docs (verified 2026-08-03, re-verified today: `grep -ri "division of labour" docs/` returns only the two forward-references phases 2 and 3 already wrote, both pointing at a section that does not exist). `docs/auto-mode.md` is the obvious home -- it is the page about the other half -- but choose and justify.
2. **The design smell named explicitly**: *"make toolguard smarter so it can handle X."* One sentence with the answer attached (the answer is auto-mode guidance, not a cleverer rule). Currently absent from `docs/`.
3. **The handoff framing.** Already written by Phase 2 (`docs/configuration.md:669`) and Phase 3. **VERIFY it, do not rewrite it** -- and make sure the new §2 material and it agree rather than saying the same thing twice in different words. If item 1 lands in `auto-mode.md`, `configuration.md:669` should point at it instead of re-explaining.
4. **A pointer early enough that someone orienting themselves meets it.** Today the frame would only be reachable by someone already reading a fallback setting's reference entry, which is backwards: it is the thing to read *first*. Decide where (`README.md`, `docs/quickstart.md`, `docs/agent-map.md` -- possibly all three) and say why.
5. **The takeover-mode inaccuracy under auto mode.** `docs/takeover-mode.md` rests on the premise *"native permits everything, toolguard is the only gate."* Auto mode drops broad native allow rules on entry, which is exactly the shape takeover mode installs -- so that premise does not hold there. The direction is safe (more actions reach the classifier, not fewer), but the documented model is inaccurate and should say so. **This is a claim about native behaviour: see the mandatory procedure below.**
6. **The auto-mode trace is completely undocumented** -- gap found 2026-09-07, in this brief, not by a previous phase. Phase 5 shipped `logs/toolguard-automode-<date>.jsonl` and nothing in `docs/` mentions it (`grep -rn "automode" docs/` -> no matches). A user cannot review a file they do not know exists. Document: what it records (a fallback-decided call while `permission_mode` is auto), the four `fallback_cause` values **as triage codes** -- each implies a different response, which is the field's whole purpose -- that it is a read-only side channel a write failure on which never changes a verdict, and **what it does not answer**: it is a `PreToolUse` hook, so it never sees the auto-mode classifier's own verdict. `toolguard/auto_mode_trace.py`'s module docstring has the material; it is the source, but read Phase 7 first, because part of it is stale.
7. **One line for `undecidable_fallback`**, the surviving finding from Phase 4a: setting it stricter than `no_match_fallback` expresses *"I distrust foreign inline code"*, and **that protection reaches only the interpreters in `FOREIGN_EXECUTORS`**. An interpreter not on that list (`lua`, `deno`, `bun`, `julia`) gets no ASK floor and reaches `no_match_fallback` instead. Worth saying once so nobody reads the setting as exhaustive. The code already documents this in `FOREIGN_EXECUTORS`' own comment; the docs do not.

### Phase 6 -- out of scope

- **`docs/install.md` and anything under `skills/`.** Arnon, 2026-09-05: *"we're not modifying the install flow or any of the bundled skills in this ticket."* That is **TOO-77**. The consequence is deliberate: these settings ship with no install-time explanation, so the docs must carry the explanation the install flow would have given. Write that explanation; do not touch the install flow.
- The security-audit skill. Also TOO-77.

### Phase 7 -- in scope

Comments and docstrings in `*.py` **added or edited by this ticket**. The precise diff is `git diff TOO-28-start-of-work..HEAD -- '*.py'` -- Arnon tagged the pre-work commit for exactly this. 46 files, 5459 insertions.

**7a -- delete pure scaffolding.** A comment whose entire content is "this is mid-refactor" has no reader now. **The plan's inventory is STALE and you must re-derive it**: it names `hook.py:1016, 1103, 1271, 1275`, and `grep -n "SCAFFOLD\|phase" toolguard/hook.py` returns nothing today -- later phases already rewrote them. Do not go looking for the four the plan names; find what is actually there.

**7b -- trim what survives to long-term value.** Three questions per comment, and the third is the one that pays:

1. **Does it have a reader after the work lands?** If it only makes sense to someone watching the refactor happen, delete it.
2. **Is it concise?** Per `~/.claude/rules/comments.md` (read it) -- assume anything written during this ticket is twice as long as it should be. Long rationale belongs in the ticket, not the code.
3. **Is its claim still TRUE?** **This is the highest-yield question in this brief, and there is a specific reason.** The phases landed **out of order** -- 1, 5, 2, 3, 4 -- so a comment written in Phase 5 was written before the Phase 2 feature existed. Anything phrased in the present or future tense about what toolguard "does not yet" do is a candidate.

   **One is already confirmed false**: `toolguard/auto_mode_trace.py:21` says *"toolguard does not yet vary its fallback behaviour by `permission_mode` at all (that is a later phase); this trace only records where the SAME fallback outcome occurred while auto mode was active, as a baseline for comparison once it does."* Phase 2 shipped `resolved_no_match_fallback_in_auto_mode` (`config_types.py:757`) and `resolved_undecidable_fallback_in_auto_mode` (`config_types.py:845`). The sentence was true when written and is false now. **Find the others by the same mechanism, do not assume this is the only one.**

Two specific dispositions the plan already decided, carried here so you do not re-decide them:

- `toolguard/invocation.py`'s module docstring is long rationale -- the in-process-corpus argument, the eight-console-scripts argument. **Keep the rule** ("explicit argument, not an ambient singleton") **and drop the argument for it**; the argument lives in the ticket.
- `test/unit/test_architecture.py:42` explains why the allow-list is empty. **That has lasting value** -- it is what stops someone importing `config` into it. Keep the substance, drop the ticket reference.

**Ticket references generally**: a `TOO-28` in a comment earns its place only when it points at rationale that genuinely cannot be inlined. There are ~30 in `*.py` today. Judge each; most should either become a plain statement of the rule or go.

**One bounded extra**, on the open-items list and unowned: `tools/architecture_fitness.py:1606`'s `R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}` names a function that no longer exists (`test/unit/test_compound_resolve_seam.py:410` calls it *"the now-deleted"*). **But it is not inert** -- `test/unit/test_architecture_fitness.py:1884` builds synthetic source to exercise that entry. So this is a judgement, not a deletion: if removing it changes what a test means, **STOP and report** rather than adjusting the test to fit.

### Phase 7 -- out of scope

- **`test/verdict_corpus/` fixtures.** Frozen goldens. Their command text is data, not comments, and editing them invalidates the corpus.
- Comments this ticket did not touch. The tag bounds the review; do not extend it into a general comment sweep.

### Is widening authorised?

**NO** for both phases, except: (a) fixing what your own changes break, and (b) a doc statement you find to be **factually false** while writing nearby prose -- correct it and report it separately, because a false doc sentence is a defect regardless of which ticket introduced it.

## Findings carried forward

1. **Phase 4a's finding is RETRACTED except for one line.** The unknown-interpreter "gap" was my error -- Arnon, 2026-09-07: *"How would toolguard even know that lua is an interpreter if it is not statically told it is?"* An unrecognised interpreter **does** reach `no_match_fallback`, which is what a fallback is for. Only item 7 above survives. **Do not document a gap here**; document the scope of what `undecidable_fallback` covers.
2. **Phase 0 is downgraded, not skipped.** Whether a hook `allow` skips the auto-mode *classifier* (as opposed to the prompt) is **still unsettled and only a test decides it**. It belongs to TOO-77, where the answer would be acted on. **Do not write a docs sentence that answers it either way** -- writing about a mechanism nobody has tested would be worse than leaving the gap visible. If the question is worth naming in the docs at all, name it as open.
3. **The handoff framing and the settings reference are already written** (Phases 2, 3, 4). Verify and cross-link; do not duplicate.
4. **Baseline, taken 2026-09-07 at `bd4f895`**: suite `Ran 4130 tests` / OK; `ruff check` clean; corpus `--verify --strict-prose` `OK: no differences` at 6401 in-process / 61 end-to-end; three `architecture_fitness.py` checks pass; 8 console entry points load.

## Steps and their completion artifacts

**TDD is NOT required here** -- Phase 6 adds no behaviour, and Phase 7 removes comments. Both are behaviour-neutral by construction, which makes the corpus the load-bearing check rather than new tests. **If you find yourself needing a new test, you have left the scope of this brief: stop and report.**

| # | step | completion artifact |
|---|---|---|
| 1 | **Fetch `https://code.claude.com/docs/en/permission-modes` and `permissions.md` in this session**, before writing item 5 | the verbatim quote about broad allow rules being dropped, with today's date, pasted in the report. **`.claude/rules/native-fidelity-claims.md` is mandatory here**: never restate native behaviour from memory or from this brief -- the quote below is second-hand and dated 2026-09-05. A blinded review cannot catch an error in this class, which is why it has bitten twice |
| 2 | Items 1-4: the frame, the design smell, the handoff verification, the pointer | the diff, plus where you put each and why |
| 3 | Item 5: the takeover-mode note, scoped to the fetch date | the diff, and the sentence stating the date rather than asserting permanent equivalence |
| 4 | Item 6: the auto-mode trace section | the diff. State explicitly which parts of `auto_mode_trace.py`'s docstring you did NOT copy because step 7 found them stale |
| 5 | Item 7: the `FOREIGN_EXECUTORS` scope line | the diff |
| 6 | **Every internal link resolves** -- anchors included | how you checked, and the count |
| 7 | 7a + 7b: the comment review over `git diff TOO-28-start-of-work..HEAD -- '*.py'` | **a table: file, what the comment claimed, disposition (deleted / trimmed / kept / REWRITTEN AS FALSE)**. The "false" row is the one Arnon will read first; report the count even if it is 1 |
| 8 | The `R3_SANCTIONED_SITES` judgement | the decision and its reason, or a STOP |
| 9 | Lint and format | `ruff check .` clean, `ruff format .` clean |
| 10 | Suite | green; state the count against the 4130 baseline |
| 11 | **Corpus equivalence** | `OK: no differences` at 6401/61 |
| 12 | **Calibrate before believing step 11** | plant a decision-altering change, confirm it FAILS, revert, confirm it passes, `git status` clean. **A null from an uncalibrated instrument is not evidence** -- this project has a measured case of exactly that |
| 13 | Three fitness checks + 8 entry points | exit 0 / all load |
| 14 | **Sibling sweep** | any doc that should carry the frame and does not, and any comment outside the diff made false by this ticket. "None, and here is how I looked" is a valid answer; a blank is not |

## This brief is unverified

**Do not take it on trust.** Specific claims of mine that may be wrong:

- **That the division of labour is written nowhere.** I grepped for `"division of labour"` and for `"smarter"`. It could be present in different words -- `docs/security.md` (644 lines) and `docs/architecture-as-built.md` (557) are the two I did not read. **Check before adding a third statement of something said twice already.**
- **That `auto_mode_trace.py:21` is the only confirmed-false comment.** I found it by grepping `"not yet"` and `"later phase"` across `toolguard/`. That catches one phrasing of one hazard. A comment can be falsified without containing either phrase -- and the out-of-order phase sequence means the hazard is systematic, not incidental.
- **That the plan's Phase 7a inventory is entirely stale.** I checked `hook.py` only. The other 45 files in the diff are unchecked.
- **That the takeover-mode premise is inaccurate under auto mode.** This rests on a quote fetched **2026-09-05**, relayed through the plan, which I have not re-fetched. Step 1 exists because of this. If the current doc says something different, **the doc wins and this brief is wrong** -- report it.
- **That item 6's framing matches what the code actually does.** I read the module docstring, not the writers of `fallback_cause`. Before documenting the four values, **find where each is set** -- a docstring enumerating code paths goes stale the moment a writer is added, and that exact shape has already misled this ticket once: I told a previous agent that a set `fallback_kind` proved the undecidable path fired, from a docstring, and it was false for the most common input.

**Report anything you find wrong.** Every phase of this ticket has produced its most valuable output as a correction to my premises, and the two most expensive corrections were both cases of me trusting prose over the code it described.
