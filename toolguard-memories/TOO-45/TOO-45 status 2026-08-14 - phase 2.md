---
title: TOO-45 status 2026-08-14 - phase 2
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/too-45-status-2026-08-14-phase-2
---

# Where TOO-45 stands, 2026-08-14

**Written for you to pick up without reading the scrollback.** You reviewed proposed tickets through #52 and said you would resume there; **there are now 27 unread, #53 to #79.**

## FINAL STATE — phase 2 is done to the limit of what I can decide

**3,639 tests. 4 failures. 0 errors.** `ruff format --check` and `ruff check` both clean.

**All four remaining reds are the ones waiting on you** — nothing else is left:

| test | blocked on |
|---|---|
| `test_compound::test_nested_backticks` | **A4** — descend into nested backticks, or treat the nesting as undecidable |
| `test_tools_security_audit::TestClarityScope` ×2 | **A12** — does "governed" mean *builtin* or *describable* |
| `test_tools_self_permission::test_every_console_script_a_skill_invokes_is_declared` | **A11** — `toolguard-install skills-status` self-permission |

**Verified before writing this**: no test file lost assertions relative to `bdb7c95` (checked per file), test count rose 3,628 -> 3,639, and **nothing is committed** — `bdb7c95` is still HEAD. 44 production files changed, 14 test files changed, every test change under a licence enumerated below.

## The one-paragraph version

Phase 1 is committed at **`bdb7c95`** — 77 test modules repaired, 3,628 tests, 137 deliberate reds. You then said "continue non-stop until green", so **phase 2 ran all day**: the 137 reds were triaged into ten production defects and fixed by eleven agent runs. **Nothing is committed beyond `bdb7c95`** — all git operations are still yours. `git diff --name-only -- toolguard/ tools/` is now **deliberately non-empty**; that invariant belonged to phase 1 and phase 2 is the phase that breaks it on purpose.

## What phase 2 actually changed

The 137 reds were not 137 bugs. They were **ten**, each visible from several angles:

| # | reds | the defect |
|---|---|---|
| 1 | 24 | `Bash(x:*)` matched across token boundaries — `Bash(git log:*)` matched `git logfoo` |
| 2 | 15 | valid JSON that is not an object (`[1,2,3]`, a bare string, `null`) handed straight to `.get()` |
| 3 | 11 | `rule_sort._escape_toml_string` escaped only `\` and `"`, so **one newline in a rule's context bricked the config file** |
| 4 | 6 | the audit log could not read back a command containing a newline or a `#` heading, and lost it silently |
| 5 | 10 | the inline foreign-code ASK floor: `awk` undetected, and **the floor lost entirely inside an `if`/`while` condition** |
| 6 | 12 | **the hook's own crash handler could crash**, so no deny reached stdout |
| 7 | 14 | `mining` hand-rolled bash tokenization; `hierarchy` could not tell an empty scan from a clean one |
| 8 | 12 | the maintenance analyzers — including a **takeover audit that could be exactly backwards** |
| 9 | 16 | dev instruments reporting PASS having examined zero modules |
| 10 | 12 | config silently discarding a `[[permissions]]` section; user-facing messages claiming things that did not happen |

### The three I would want you to look at first

**The hook's last-resort deny never ran.** `error_log.log_crash` built `errors_dir = Path.home() / ".toolguard" / "errors"` **above** its own `try`. An unresolvable home therefore threw straight out of `hook.main()`'s broad except clause, so `_emit_decision` never ran and stdout was empty. Claude Code treats **only exit code 2** as blocking — so on that path toolguard was not "denying", it was **absent**, with no permission check at all and no error anywhere. The fix is moving one line inside the existing `try`.

**The ASK floor was lost inside an `if`/`while` condition.** `while rm -rf /tmp/x; do :; done` yielded a leaf of `':'`, so the real command never became matchable and no rule could fire on it. It now denies. I briefed this expecting a PEG grammar change; **there wasn't one to make.** The grammar already parsed the condition and populated `ctrl_condition_text` for all three forms — the consuming Python never read the field, and its docstring said that was intended.

**The takeover audit could invert its own verdict.** Invariant 4 read the raw `[takeover_mode].no_match_fallback` instead of `config.resolved_no_match_fallback()`, so it could call a loose top-level override "hardened" and a hardened key "loose".

## Tickets filed today — 77, 78, 79. All security-shaped, none covered by any test.

- **77 — `FOO=1 rm -rf /tmp/x` evades a `deny Bash(rm:*)` rule.** Toolguard strips nothing before matching. Native strips wrappers (`timeout`, `nohup`, …), bare `xargs`, and leading env assignments **for allow rules only** — so implementing native *exactly* fixes the allow case and **leaves the deny bypass open**. That is the decision in the ticket and I did not pick. The same gap means every `TG_INTENT=1` disclosed command currently misses its own allow rule: the rule that makes agent behaviour visible is also the rule that removes the agent's permissions.
- **78 — an absolute-spelled deny rule never fires on a `~`-spelled command.** `normalize_path` collapses toward `~` but never expands it, so matching is asymmetric. **Pre-existing at HEAD**, measured against a `git archive` copy. Anyone who writes deny rules with absolute paths — the more natural spelling — has rules an agent evades by typing `~`.
- **79 — `$(python -c "...")` runs foreign code with no ASK floor**, *and* the verdict corpus is structurally blind to floor changes. `realistic` sets `undecidable_fallback = "allow_with_no_warnings"`, so an `inline_code` unit resolves to `allow, matched_rule: None` — identical to having no floor. `test_no_verdict_changed` passing across ~2,500 commands therefore cannot distinguish "the floor fired" from "the floor never existed". Third instance of that family after 29, 68 and 73. **I quoted that green as safety evidence earlier in the day; it wasn't.**

## What needs YOU

Section **E** of `DECISIONS-PENDING.md` is new and holds the calls I made today, all reversible. In the order I would take them:

1. **E1 — the boundary fix's blast radius.** `Bash(x:*)` now requires a token boundary, confirmed against Anthropic's documentation *and* against the repo's own measured divergence table. But the documented rule names exactly two terminators — a space or end-of-string — and **`/` is neither**. So `rm -rf /tmp:*` no longer covers `/tmp/foo`. On an **allow** rule that is the safe direction; on a **deny** rule it is a fail-open. **If you have deny rules written as path prefixes, they were relying on the bug.** That is the one thing I would check by hand.
2. **A12** — still unanswered, still gating 2 reds and every analyzer downstream.
3. **77's fix direction** — see above; the obvious answer does not work.
4. **E2** — I authorised edits to 13 test locations under bounded, enumerated licences (details below). Overrule any of them.
5. **A11, A13, A4** — unchanged from yesterday.

## The rule I bent, stated plainly

Phase 2's hard rule was **agents never edit `test/`**. Tests are the spec; a green suite obtained by editing a test is a campaign failure. That rule held for every agent. **I overrode it myself, five times, each time naming the exact locations in the brief and requiring before-and-after in the report:**

- 8 tests in `test_tools_consolidate.py` encoding the **pre-fix** `Bash(x:*)` semantics as contract. Ticket 18 had named one of them in advance as exactly that.
- 2 expected-value data pins in `test_tools_maintenance.py`.
- 2 stale "RED until…" docstrings that had become false.
- 2 count pins in `test_recommended_protections.py`.
- 1 regeneration of `test/verdict_corpus/goldens.jsonl` — **only after all seven deltas were individually adjudicated by A/B measurement** against a tree differing solely in `command_extractor.py`. Bulk regeneration was explicitly forbidden: that is how a corpus stops being evidence and becomes a screenshot.

I also fixed two bare 3-name `except` clauses under `test/` myself, and re-ran `ruff format` to confirm the magic trailing comma survived — that is the fix this project has measured reverting itself.

**Tests were ADDED too**, closing gaps the fixes exposed: `TestMatchCommandTokenBoundary` and `TestMatchCommandUnderASymlinkedHomeDirectory` in `test_permissions.py`, and three leading-assignment tests in `test_multiline_bash.py`. The first of those matters — **`match_command` had no test at its own level at all**; every guard on the most security-critical function we touched reached it only through `decide()`.

## Friction you will actually feel

- **13 `awk` invocations with inline programs are now ASK** where they were allow. Measured over all 7,706 leaves in `cases.jsonl`. (An earlier report said six; that was corrected. `python -uBIc`, `perl -E`, `node --eval` are real detector improvements but appear in **zero** real commands, so quoting them as friction overstated the cost.)
- `awk -f prog.awk` went **ask → allow**, correctly — the old table listed `-f`, a program *file* flag, as inline code.
- `rm -rf <dir> -f` falls to `ask` under the tightened uninstall rules.
- `.env.example` becomes write-denied as well as read-denied, as a consequence of closing the `Edit`/`Write` gap in recommended protections.

## Where my briefs were wrong

Same rate as the whole campaign, and worth keeping because it is where a lot of the value came from — every agent is told the notes are unverified and to report errors in them.

- The 20 uninstall reds were **not** a matcher bug. `Bash(rm FILE:*)` ≡ `Bash(rm FILE *)`, and a trailing `*` legitimately spans a second argument; refusing extra args would break `cd:*` matching `cd /tmp`. The defect was in the **seeded rules**.
- No PEG grammar change was needed for `if`/`while` conditions.
- "Emit the deny first, logging is best-effort" would have **broken** the error reporter — the crash fault must reach `additionalContext` before output is finalised.
- Option A's cost was overstated: `rm -rf <dir>/` was already `ask` before it.
- The `~`-vs-absolute inverse never matched, even at HEAD — it is ticket 78, not a regression.
- I said "no test edit is needed" for Option A; one pin had to change.

## Still open

- **4 reds are blocked on your decisions**: `test_compound::test_nested_backticks` (A4), `test_tools_security_audit` ×2 (A12), `test_tools_self_permission` ×1 (A11).
- **Phases 3 and 4 have not started.** Phase 3 is the tickets you flag as in scope; phase 4 is coverage where there is none. Phase 4's largest known gap is still `require_project_root`, which has no direct test anywhere and no `test_path_utils.py` exists.
- Noticed and not fixed: a verdict-strictness dict **triplicated across three modules**; `AddRuleEffect` has no production caller at all.
- Two throwaway files still in `docs/` for you to delete: `diagram-path-test.md`, `diagram-sizing-test.md`.