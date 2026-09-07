---
title: brief-phase4bc
type: note
permalink: toolguard/too-28/brief-phase4bc
---

# Brief: TOO-28 Phase 4b+4c -- the input-source constraint

## Task

Spec section 4.3. **A rule must be able to say it applies only when the executable material comes from a file, or only when it does not.**

```toml
allow = [
    { match = "Bash([regex]^uv run python\\b)", input_source = "file" },
]
```

**The distinction is VISIBILITY and it is binary** -- *is a file* versus *is not a file*. Not an enumeration of heredoc, pipe, stdin, redirect, inline. Material in a file is invisible twice over: to the human at an ASK prompt, who cannot see inside it, and to toolguard, which cannot match against file contents. A redirect *from* a file counts as a file; the question is where the material is, not how it arrived.

**Scope is all known interpreters, not Bash only** -- `awk -f`, `python script.py`, and the equivalents for the shells and every other recognised executor.

**4b and 4c are briefed together deliberately.** The plan split them -- classify, then expose -- but a classifier with no consumer is dead code, and the interesting test ("does a rule actually constrain?") only exists once both halves are in. If the combined diff grows past what one review can carry, **stop and say so** and we will land the classifier alone.

## Scope and widening

**In scope:**

- **The classifier**, in `toolguard/parser/command_extractor.py`. Answer, for one extracted command: did its executable material come from a file? The existing `_ExecutorFlags` already carries most of what is needed -- `inline_letters`, `inline_long`, `value_letters`, `program_file_letters`, `bare_program` -- and **it may need no new fields at all**. Work out the resolution rule and state it. My reading, which you should check rather than adopt:
  - an inline flag matched -> **not a file** (the program is in the command text)
  - a `program_file_letters` flag matched -> **file**
  - `bare_program` and a positional present -> **not a file** (awk: the first positional is program TEXT)
  - otherwise a non-flag positional present -> **file** (`python script.py`)
  - no positional, or `-` -> **not a file** (stdin/REPL)
- **Coverage gaps to close**: `BASH_FAMILY` members have no `_EXECUTOR_FLAGS` entry at all and fall to `_DEFAULT_EXECUTOR_FLAGS`; `python`, `node`, `perl`, `ruby` and `Rscript` have no `program_file_letters` and no positional-file expression. Establish what each actually needs.
- **The rule-enrichment key**, following `auto_mode_behavior`'s pattern exactly (Phase 3): declared key constant, `RuleEntry` accessor, membership in `KNOWN_ENRICHMENT_KEYS`, config-time validation of an unrecognised value, and a declared value set.
  - **Name**: `input_source`, per the spec. **Values**: my suggestion is `"file"` and `"not_file"`; `"not_file"` is ugly and I am open to better, but avoid `"inline"` -- it is wrong for stdin, a pipe and a heredoc, which are all not-a-file without being inline. Propose an alternative if you have one, with the reason.
  - **Semantics: a guard on the rule, not a mapping.** Spec section 6.2 question 3: *"With a binary distinction there is nothing to list -- a rule states which of the two cases it requires."* A rule carrying `input_source` matches only when the command's material is that kind; otherwise the rule does not apply and resolution continues as if it had not matched.
- Documentation in `docs/`, alongside the Phase 2 and 3 additions. **Not** `install.md`, **not** the bundled skills -- TOO-77.

**Explicitly OUT of scope:**

- **Any grammar change.** This is token interpretation after the parse, not parsing. **If you find the grammar must change, STOP and report** -- `.claude/rules/bash-grammar.md` mandates a two-phase procedure (`.peg` plus canopy regeneration reviewed on its own, Python only afterwards) and that is a separate piece of work, not something to fold in.
- Unknown interpreters. Settled in Phase 4a: toolguard cannot know an executor it has not been told about, and no mechanism covers that. Do not add heuristics.
- Consolidating the six interpreter lists. Phase 4a's finding: they answer different questions, keep them all.

**Is widening authorised? NO**, except fixing what the change breaks.

## Findings carried forward

1. **The spec's "new work" claim is half wrong, and the plan records it.** Section 4.3 says *"the per-interpreter file-flag detection above is new work"*. `program_file_letters` and `bare_program` already exist and are populated for `awk` and `php`. What is missing is coverage and exposure, not mechanism.
2. **Phase 4a: keep all six interpreter lists.** `BASH_FAMILY`/`FOREIGN_EXECUTORS` are complements; `_EXECUTOR_FLAGS` is a per-member detail table with a default; `COMMAND_WRAPPERS` is orthogonal; `danger.py`'s three serve an audit heuristic whose narrower membership is deliberately independent.
3. **Phase 3 set the enrichment precedent.** `AUTO_MODE_BEHAVIOR_KEY`, `_VALID_AUTO_MODE_BEHAVIOR_VALUES` built from `DECISION_*`, `KNOWN_ENRICHMENT_KEYS`, validation mirroring `additionalContext`. Follow it rather than inventing a second shape.
4. **Baseline**: `Ran 4085 tests` / `OK (expected failures=4)`; ruff clean; corpus `OK: no differences` at `6401`/`61`; three fitness checks; 8 entry points.

## Steps and their completion artifacts

**TDD IS required** -- new behaviour. **Paste the RED runs.** No `RED:` markers in code.

| # | step | completion artifact |
|---|---|---|
| 1 | Establish and state the resolution rule, and whether any new `_ExecutorFlags` field is needed | the rule, in the report, with what you found wrong in mine |
| 2 | RED: classification across the interpreter families -- inline flag, program-file flag, positional file, `bare_program`, stdin | pasted failing output |
| 3 | RED: **the negative direction** -- a rule requiring `file` must NOT fire on inline code, and a rule requiring `not_file` must NOT fire on a file | pasted failing output. **A guard that always passes satisfies every positive case**; these are the tests that give step 2 meaning |
| 4 | RED: a rule with NO `input_source` behaves exactly as today, under every command shape | pasted failing output |
| 5 | GREEN: implement classifier and enrichment key | suite green; state the count |
| 6 | Config-time validation of an unrecognised value | the issue it reports |
| 7 | Composition with the four pattern types | a test each for DEFAULT, REGEX, GLOB and NATIVE carrying `input_source` -- section 4.3 chose enrichment over a fifth dialect precisely so it composes with all four |
| 8 | Interaction with `auto_mode_behavior` | one test with both keys on one rule. They are independent; prove it rather than assume it |
| 9 | Lint, format, three fitness checks | clean / exit 0 |
| 10 | **Corpus equivalence** | `OK: no differences` at `6401`/`61`, with no rule using the key |
| 11 | **Calibrate before believing step 10** | plant a decision-altering change, confirm FAIL, revert, confirm pass, `git status` clean |
| 12 | Entry points | all 8 load |
| 13 | **Live end-to-end** | drive the real hook with a rule carrying `input_source = "file"`; show `uv run python script.py` and `uv run python -c "..."` reaching different decisions. Paste both |
| 14 | Sibling sweep | any other consumer that should ask this question and does not |

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **The resolution rule in Scope is my reading of five field docstrings, not a traced implementation.** The `value_letters` interaction is where I would expect it to be wrong: a flag whose value is a separate token must be stepped over, and getting that wrong would misread the value as the positional program. Check it.
- **That no new `_ExecutorFlags` field is needed.** Plausible but unverified. If a field is needed, add it -- I would rather have the right structure than a clever derivation.
- **That `bare_program` means what I think.** I read it as "the first positional is program TEXT" (awk). If it means something else, my whole rule is wrong.
- **That a redirect from a file is detectable here at all.** Section 4.3 says it counts as a file. Redirects are a grammar-level construct and I have not checked whether extraction preserves them. **If it does not, say so** -- that is a real limit worth recording rather than approximating.
- **That "the rule does not apply" is the right semantics for a failed guard**, as opposed to the rule matching but the decision changing. I believe resolution should continue as though the rule had not matched, but check how a non-matching rule is currently treated so the behaviour is consistent with it.

**Report anything you find wrong.** Every phase so far produced its most valuable output as a correction to my premises -- twice this week from me substituting a mechanism for a measurement.