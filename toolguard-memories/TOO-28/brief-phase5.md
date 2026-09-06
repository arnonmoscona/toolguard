---
title: brief-phase5
type: note
permalink: toolguard/too-28/brief-phase5
---

# Brief: TOO-28 Phase 5 -- the auto-mode gap log

## Task

Spec section 4.4. **When no toolguard rule matched and the permission mode is auto, record what happened in a dedicated log.**

**Why it exists.** Spec section 2 frames toolguard and Claude Code's auto-mode guidance as complementary halves with inverted strengths: toolguard is exact and auditable but blind to anything it cannot pattern; the classifier reads intent but is neither repeatable nor auditable. **The guidance half currently has no feedback loop.** This log is that loop -- it makes visible which commands fall through toolguard entirely, so patterns worth expressing as rules can be found and the guidance improved.

**This does not make toolguard judge meaning.** The analysis is offline, out-of-band and human-directed. Nothing in the decision path reads this log, and nothing written to it affects any verdict. toolguard records what it deferred; it does not evaluate it.

**This is NEW behaviour**, unlike Phase 1. Decisions must still be unchanged -- the corpus must report no differences -- but there is genuinely new output, so TDD applies.

## Scope and widening

**In scope:**

- A **separate log file**, not the decision log. `logs/toolguard-<date>.md` continues unchanged. Precedent for sibling logs exists: `toolguard-error-<date>.md`, `toolguard-warning-<date>.md`, `toolguard-discovery.jsonl`.
- **JSONL, one object per line.** This corpus is for machine analysis. **Carry the structured decision through to the writer -- do not render a sentence and re-parse it.** TOO-45 measured 83% of compound-allow decisions under-logged for exactly that mistake, and this log's whole value is that the data stays analysable.
- **Trigger: no toolguard rule matched AND `permission_mode == "auto"`.** "No rule matched" means the decision came from the fallback, not from a matched pattern.
- **Fields**: enough for offline analysis without re-reading transcripts. At least timestamp, session id, tool name, the governed subject, the fallback decision emitted, which fallback produced it (no-match vs undecidable), the permission mode string, cwd, agent info. Add what you judge useful; **primitives only, never a derived figure or a rendered sentence.**
- **Register the new writer in `test/unit/_real_log_dir_guard.py`'s `install()`.** Its wrapped set is `log_command`, `log_discovery`, `log_conflict`, `log_error`, `log_warning`. A new log-writing function not added there writes into the REAL repo `logs/` during the suite -- this bit before (TOO-19), which is why the guard exists.

**Explicitly OUT of scope:**

- **No `PostToolUse` hook.** See Findings 1 -- a known limitation, deliberately accepted.
- **No install-flow or bundled-skill changes.** Those are TOO-77.
- **No new configuration setting** to enable or disable this. If you want one, report it.
- **Nothing reads the log.** No analysis tooling, no report generator, no rule suggestion.
- The auto-mode fallback settings (spec 4.1) and per-rule override (4.2) are Phases 2 and 3.

**Is widening authorised? NO**, except fixing what the change breaks.

## Findings carried forward

1. **The stated purpose and what a PreToolUse hook can see do not fully meet -- KNOWN LIMITATION, accepted for this phase.** Section 4.4 wants analysis of *"what the auto-mode classifier actually allows"*. toolguard registers only for `PreToolUse` (verified in `~/.claude/settings.json`, 2026-09-06), so it sees what it **deferred** and never the classifier's verdict. The outcome half needs a `PostToolUse` registration, which is an install-flow change, and Arnon moved those to **TOO-77**. **Record this in the module docstring** so users of the log know what it does and does not answer. The deferral half still serves the primary purpose: finding which shapes fall through, so rules can be written for them.
2. **`plan` mode may also use the classifier -- OPEN, do not decide silently.** `permission-modes` doc, fetched 2026-09-05: plan mode allows *"Reads, plus classifier-approved commands when auto mode is available"*. So classifier-approved commands can occur under `plan`. **The spec says auto; implement auto.** Record the mode string in every entry regardless, and **flag in your report** what evidence you found. Widening the trigger is Arnon's call.
3. **The mode values are `default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`** -- from that fetched doc, not memory. `default` is Manual mode's config value. Do not invent a mode string; verify rather than recall (`.claude/rules/native-fidelity-claims.md`).
4. **Phase 1 is complete and committed.** `Invocation` reaches the decision path carrying `permission_mode`, so the mode is available where the fallback is applied -- that is what Phase 1 was for. Baseline: `Ran 4021 tests` / `OK (expected failures=4)`, ruff clean, three fitness checks, corpus `OK: no differences` at `6401` / `61`, all 8 entry points load.

## Steps and their completion artifacts

**TDD IS required here**, unlike Phase 1: this phase adds behaviour, so there is something to drive out, and the existing suite cannot specify output that does not exist yet.

**Per-behaviour artifact: paste the RED run.** Show the test failing for the right reason before the implementation exists, then passing after. **Do not write a `RED:` marker in the code** -- this project measured 9 of 9 such markers going stale.

| # | step | completion artifact |
|---|---|---|
| 1 | Locate where "no rule matched" is decidable with the `Invocation` in hand | the call site, named in the report |
| 2 | RED: an entry is written for an unmatched command under `auto` | pasted failing output |
| 3 | RED: **nothing** is written when a rule DID match, and when the mode is not `auto` | pasted failing output. **The negative cases are what make the positive test mean anything** |
| 4 | RED: a write failure does not change the verdict | pasted failing output |
| 5 | GREEN: implement; register in `_real_log_dir_guard.install()` | suite green, count stated |
| 6 | Lint and format | `ruff check .` clean; `ruff format .` no reformatting needed |
| 7 | Architecture fitness | `--stdlib`, `--ambient`, `--layers` each exit 0 |
| 8 | **Corpus equivalence -- decisions must not move** | `OK: no differences`, `6401` / `61` |
| 9 | **Calibrate before believing step 8** | plant a decision-altering change, confirm `--verify` FAILS, revert, confirm it passes, confirm `git status --porcelain` clean for that file |
| 10 | Entry-point smoke test | all 8 `[project.scripts]` console scripts load |
| 11 | Confirm no real log leak | `test_zz_real_log_dir_guard` passes |

**A changed test count is expected this round** (new tests), unlike Phase 1 -- state the new number and what was added.

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **That "no rule matched" is cleanly detectable at one place.** I have not traced it. The fallback path sets provenance to none and the decision log writes `[fallback allow -- no rule matched]`, but whether one point holds both that fact and the `Invocation` is unverified. **If it is not clean, say so -- do not scatter the trigger across several sites**, which would be the "prose is output" failure in a different costume.
- **That a compound command has one answer here.** A compound may have some leaves matched and some not. Whether that is one entry, several, or one with per-leaf detail is a real design question I have not settled. Decide, and say why.
- **That JSONL in the existing log directory is right.** It follows `toolguard-discovery.jsonl`, but I have not checked whether that file's rotation, naming and write path are a good model or an accident.
- **That `permission_mode == "auto"` is the whole test.** See Finding 2. Also unverified: whether Claude Code ever sends a mode string this project has not seen. **An unknown mode must not crash the hook** -- a defensive default matters more than a clever one.
- **That nothing in the decision path will end up reading this log.** It must not. If the implementation makes that tempting, report it as a design smell.

**Report anything you find wrong.** Every round of Phase 1 produced its most valuable output as a correction to my premises.