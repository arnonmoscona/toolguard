---
title: 'Code-level residue from the #07 sweep: defects found, deliberately not fixed,
  now needing a disposition'
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/33-code-level-residue-from-the-07-sweep
---

**PARTIALLY FIXED in `05f786d`.** Only section 2 is fixed (the takeover string, `toolguard/session_warnings.py:7-9`); still open: the headline contradiction between comment and user-facing text in `toolguard/config.py:1552-1568` is live, plus sections 3-7 (see the audit's #33 detail).

# Code-level residue from the #07 sweep

**#07 was comments-only by design** (Arnon, 2026-08-10): verifying a comment sweep is confusing enough without code changes mixed in, so a false or misleading **string** was recorded and left alone even when the comment beside it was being corrected. This ticket is the bill for that decision. Everything here needs its own change or an explicit "no".

Items already covered by their own tickets are **not** repeated: the matcher and extractor defects are 17-19, the analyzers are 20-22, the fail-opens are 23 and 29, and the suite-blindness measurements are 31.

## 1. Code and comments now actively disagree — the one to settle first

`toolguard/config.py`'s `validation_issues` builds an `Issue` whose `corrective_steps` text says *"EVERY toolguard permission decision is clamped to `'ask'`"*.

**False.** `permission_resolution.apply_parse_failure_floor` and `_apply_ask_floor` both return an already-`deny` verdict untouched (`if not parse_failures or decision == "deny"`), and that exemption is defended by the regression test `TestDenyUnderBrokenConfigKeepsProvenance`. The reassurance the text makes ("no rule including deny/hard_deny is silently lost") stays true; only the universal is wrong.

**It was corrected during the sweep and then reverted to keep #07 comments-only.** The two *comment* statements of the same claim were corrected and stay corrected. **So the code and its own documentation now contradict each other by design, and will until this lands.** That is not a stable state to leave a codebase in.

Same claim, one more place: `docs/configuration.md:460` carries the unhedged version. In scope for `/documentation-review`, not for this.

## 2. A user-facing string that contradicts its own call site

`session_warnings.issue_takeover_warning`'s message says *"Takeover mode is active. Claude's native permission prompts are bypassed."* But `hook._announce_takeover_state` also calls it on the **cross-level-conflict** branch, where `takeover.enabled` has just been fail-safed to `False` and native prompts are the ones still active.

The surrounding `hook.py` prose already says this correctly. **The string tells the user the opposite of what is happening**, in the one branch where the safety posture changed. Confirmed independently by two cold-review passes on 2026-08-11.

Fix needs either a second conflict-specific message, or a parameter distinguishing "enabled" from "fail-safed off after a conflict".

*(Related and already ticketed: this function's two tests are both unfalsifiable — see ticket 31.)*

## 3. Dead code / no production caller — four instances, verified by grep

| what | where | note |
|---|---|---|
| `_discover_rules_files` | `toolguard/config.py` | no production caller; only `test_configuration.py`. Its sibling `_discover_rules_files_multi` is the live one. Either dead code or a **missing call site** — worth deciding which before deleting |
| `get_command_breakdown` | `toolguard/compound.py` | no production caller in the repo, only a test |
| `LevelMatch` re-export | `toolguard/resolve.py` | explicit `as` re-export, never used as a type in the file, and nothing imports it *from* `resolve` |
| `match_pattern`'s `DEFAULT` branch | `toolguard/patterns.py` | no live caller: `match_command` handles DEFAULT itself, `file_matching` remaps DEFAULT to GLOB first, no test passes it |

`hook.COMMAND_TOOLS` is a fifth, tracked in ticket 32 item 8.

## 4. Open design questions the sweep surfaced but cannot answer

- **`hook.FILE_PATH_TOOLS = FILE_TOOLS`** — an alias whose only outside importer is `test_hook.py`, while `hook.py` itself uses the alias name at two call sites rather than the canonical `constants.FILE_TOOLS`. Keep as a permanent local name, or delete and repoint its three users?
- **`hook.py`'s interactive guard exits 0** when someone runs `toolguard` by hand in a terminal with no piped JSON. The code carried a note addressed to Arnon directly: *"Exit code 0: informational, not an error (Arnon: change to non-zero if preferred)."* Deleted as prose — a question to a named person is not documentation — but **it is unresolved**, and would otherwise have been lost with the comment.
- **GLOB and NATIVE bypass the DEFAULT newline guard.** REGEX's exemption is by design (its authors control `re.DOTALL`). Nothing establishes GLOB's or NATIVE's as intentional rather than an oversight in a guard whose entire purpose is closing a fail-open. Decide, or record the exemption explicitly.
- **Any `:` in a DEFAULT pattern triggers the `cmd:args` split**, so `curl http://ex.com/*` silently cannot match. A silent authoring trap for any pattern containing a URL. Require whitespace after the `:`, or document it in the README's pattern-syntax section.

## 5. Duplication the sweep had to describe twice

- **`decision_ledger.ledger_path_for_level`** re-implements the level check `_validate_enums` already performs, **down to a copy of its error string** — `f"unknown level {level!r}; expected one of {sorted(VALID_LEVELS)}"` appears at both `:176` and `:265`. Two messages that must stay identical with nothing keeping them so. Fix: reject through the existing validator.
- **`test_once_per_store.py:15` defines its own byte-identical `_IsolatedStoreMixin`** rather than importing the shared one in `_once_per_isolation.py`. The shared module's docstring claimed it was *"one copy, used by every test module that needs"* it — false, and verified by grep plus `git log -S` (the shared file was created fresh, never actually deduplicated). The false claim was removed; **the duplication remains**.

## 6. Stale cross-file analogy

`permission_migration.py:94-96`'s `_EXIT_CODES` comment describes itself as mirroring `error_reporter._ROUTING`'s *"one table to read, one place to change"* shape. That characterisation of `_ROUTING` was corrected during #07 — the table does **not** control stderr on a successful log write, since `error_log._log_entry` echoes unconditionally. `_EXIT_CODES`'s claim about itself stays true; only the analogy is stale. Drop it or reword to something both tables satisfy.

## 7. Two refactor candidates, both found because the comments clustered

`validation_issues` and `judge_unit`. The sweep's standing rule was that refactor candidates go to the queue and never into the code, so neither was touched. Both were spotted by the same signal — **a docstring that numbers what a function does should probably be that many functions.**

## Provenance

`reports/follow-up-queue.md`, the "Code-level defects found during #07 — flagged, deliberately NOT fixed there" table and rows `DL-R1`, `SML`, plus the #07 work queue's open-items and refactor-candidate sections. Promoted 2026-08-12 when Arnon asked what else had been left in the working queue.

Two rows from the original table are **already resolved** and are not repeated here: `_git.py`'s false import-depth claim (deleted wholesale during its own #07 pass) and `technical-notes.md`'s "three consumers" error (corrected by hand during the sweep).
