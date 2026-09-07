---
title: brief-phase2
type: note
permalink: toolguard/too-28/brief-phase2
---

# Brief: TOO-28 Phase 2 -- two independent auto-mode fallbacks

## Task

Spec section 4.1. **toolguard must be able to resolve a different fallback when the permission mode is auto, for two settings that are configured independently:**

- **no-match** -- "no rule matched this action"
- **undecidable** -- "I could not decompose this command safely"

**They must be independently configurable.** A single flag would silently couple two different decisions: you might reasonably trust the classifier with an unmatched-but-parseable command while still refusing to hand it something toolguard itself could not read.

**Why it is wanted.** In an unattended run an ASK that nobody answers stalls the session. Where the user trusts Claude Code's auto-mode classifier, toolguard's ASK in these two cases is redundant friction rather than protection. **Only the ASK tier relaxes** -- `deny` and `hard_deny` still resolve first and are untouched.

**These are handoff points, not "auto-mode variants of existing settings"** (spec section 2). Each one is a declaration of how much to trust the other half of the division of labour for a specific class of case. Frame them that way in docstrings and docs.

**This phase changes behaviour** -- but only when the new settings are explicitly configured. Unset, everything resolves exactly as today.

## Scope and widening

**In scope:**

- **Two new top-level `toolguard_hook` keys**: `no_match_fallback_in_auto_mode` and `undecidable_fallback_in_auto_mode`. Same value vocabularies, alias maps and level-resolution behaviour as their base settings. `Configuration._resolve_fallback_setting(key, valid_values, default, ...)` already takes the key as a parameter, so this should be a call per setting rather than new machinery.
  - **Top-level keys, NOT a new `[auto_mode]` table.** `resolved_no_match_fallback`'s own docstring records that the `[takeover_mode].no_match_fallback` table form is a **legacy alias**, honoured only when no layer sets the top-level key. The config surface is moving away from tables; a new one would move against it.
  - **Unset means "use the base setting".** Not "ask", not a separate default. This is what keeps the change inert until someone opts in, and it is what makes the corpus check below meaningful.
- **`permission_mode` must reach the fallback resolvers.** Phase 1 put it on `Invocation`, but the engine's Protocol -- `ResolutionContext` in `config_types.py` -- carries only `tool_name`, `extended_syntax` and `config`. The resolvers are called from `permission_resolution.py`, which sees the context, not the invocation. **Add `permission_mode` to that Protocol** (and to `ResolveContext`/`FilePathResolutionContext` as their inheritance requires). `Invocation` already has the field, so it satisfies the wider Protocol unchanged.
- **`tools/takeover_audit.py`** reads both resolvers today and would otherwise report a stale picture. It has no invocation, so it reports the non-auto resolution -- make that explicit rather than accidental, and say so in its output if that is cheap.
- Documentation of the two settings in `docs/` -- the configuration reference. **Not** `install.md`, **not** the bundled skills; those are TOO-77.

**Explicitly OUT of scope:**

- The per-rule auto-mode override (spec 4.2) -- that is Phase 3.
- Any change to `deny`, `hard_deny`, or the parse-failure floor.
- Reading `permission_mode` for anything other than these two settings.
- A setting to enable or disable the auto-mode trace from Phase 5.

**Is widening authorised? NO**, except fixing what the change breaks.

## Findings carried forward

1. **Phase 1 did not finish the job it was named for.** It made `permission_mode` reachable in `hook.py` and stopped at the engine boundary; the Protocol does not carry it. Closing that is part of this phase, not a surprise.
2. **`fallback_outcome` (formerly `fallback_kind`) is an OUTCOME, `fallback_cause` is a CAUSE.** Both now exist on `UnitVerdict`/`RuntimeVerdict`. Do not conflate them, and do not read either as a proxy for which fallback setting fired -- that mistake produced a false label in Phase 5 and cost three rounds.
3. **Uncommitted in the tree**: Phase 5 is committed; the `fallback_kind` -> `fallback_outcome` rename is done but uncommitted and ships in **this** commit with your work. Build on it; do not revert it.
4. **Baseline**: `Ran 4043 tests` / `OK (expected failures=4)`; `ruff check .` -> `All checks passed!`; corpus `OK: no differences` at `6401` / `61`; three fitness checks pass; 8 entry points load.

## Steps and their completion artifacts

**TDD IS required** -- this adds behaviour. **Paste the RED runs**; do not leave `RED:` markers in code (9 of 9 went stale in this project).

| # | step | completion artifact |
|---|---|---|
| 1 | Add `permission_mode` to `ResolutionContext` and its descendants; confirm `Invocation` satisfies them unchanged | suite green at baseline count |
| 2 | RED: with `no_match_fallback_in_auto_mode = "allow"` and mode `auto`, an unmatched command allows; under mode `default` it still asks | pasted failing output |
| 3 | RED: the two settings are **independent** -- setting one does not change the other's behaviour, in both directions | pasted failing output. This is the requirement's core; a single coupled flag would pass a test that only checks one |
| 4 | RED: **unset means unchanged** -- with neither new key set, every decision is identical to today under every mode | pasted failing output |
| 5 | GREEN: implement | suite green; state the new count |
| 6 | **The section 8 invariant** | a test asserting the parse-failure ASK floor is unaffected by either new setting, **in every combination**, under auto and non-auto. **Write it so the NEXT fallback-ish setting also fails it** -- enumerate the settings rather than hard-coding these two. Spec section 8 requires this of any future flag touching fallback behaviour, and an enumerating test is the only form that holds |
| 7 | `takeover_audit` reports the resolved values without a stale picture | its output, pasted |
| 8 | Lint and format | `ruff check .` clean; `ruff format .` no reformatting needed |
| 9 | Architecture fitness | `--stdlib`, `--ambient`, `--layers` each exit 0 |
| 10 | **Corpus equivalence** | `OK: no differences`, `6401` / `61`. **This must hold with the new settings UNSET**, which is the proof that the change is inert by default |
| 11 | **Calibrate before believing step 10** | plant a decision-altering change, confirm `--verify` FAILS, revert, confirm it passes, `git status --porcelain` clean for that file |
| 12 | Entry-point smoke test | all 8 console scripts load |
| 13 | **Live end-to-end check** | drive the real hook with a synthetic `PreToolUse` event, `permission_mode: "auto"`, an unmatched command, and the new setting configured -- show the decision differs from the same event under `permission_mode: "default"`. **Paste both.** A unit test cannot show the mode actually arriving from the hook payload |
| 14 | Sibling sweep | any other place that resolves a fallback and would need the same treatment |

## This brief is unverified

**Do not take this brief on trust.** Claims of mine that may be wrong:

- **That `_resolve_fallback_setting` handles the new keys with no changes.** I read its signature, not its body. If level resolution or the alias machinery assumes something about the base keys, say so.
- **That "unset means use the base setting" is cleanly expressible.** It needs to distinguish "not set at any level" from "set to something unrecognised", which the existing resolver may or may not separate -- it collapses unrecognised values to the default. **If it cannot distinguish them, that is a real finding**: an unrecognised auto value would silently become the base setting rather than warning, which is the wrong failure direction for a security setting.
- **That adding `permission_mode` to `ResolutionContext` is behaviour-neutral by itself.** It should be, but `Invocation` gives it a default of `None` and the Protocol may need to allow that.
- **That `takeover_audit` only needs a non-auto reading.** I have not read it closely. If it should report both, say so.
- **That the two settings are genuinely independent in the code**, not just in the config. If they share a resolution path that couples them, that is the thing this phase exists to prevent.

**Report anything you find wrong.** Every previous round produced its most valuable output as a correction to my premises -- including one where my own "17 occurrences" count turned out to be grep text in fixture commands rather than real references.