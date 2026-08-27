---
title: Ticket 82 — native wrapper contract, FETCHED not recalled
type: note
tags: [task-memory, TOO-45, measurement, native-fidelity]
permalink: toolguard/too-45/measurements/82-native-contract
---

# Native Bash-rule preprocessing — verbatim, fetched 2026-08-21

**Source**: `https://code.claude.com/docs/en/permissions.md`, fetched **2026-08-21** in-session, per `.claude/rules/native-fidelity-claims.md`. Claims below are scoped to that date, not asserted as permanent.

## 1. The stripped-wrapper list — verbatim

> "Before matching Bash rules, Claude Code strips a fixed set of wrappers, so a rule like `Bash(npm test *)` also matches `timeout 30 npm test`. The stripped wrappers are `timeout`, `time`, `nice`, `nohup`, and `stdbuf`, plus the shell builtins `command` and `builtin`, and zsh's `noglob`. Each runs its argument as the actual command. Two related forms aren't stripped: the query form `command -v`, which looks up a command rather than running one, and zsh's `nocorrect`."

> "Bare `xargs` is also stripped, so `Bash(grep *)` matches `xargs grep pattern`. Stripping applies only when `xargs` has no flags: an invocation like `xargs -n1 grep pattern` is matched as an `xargs` command, so rules written for the inner command do not cover it."

**Stripped (9):** `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, and **bare** `xargs`.
**Explicitly NOT stripped:** `command -v`, `nocorrect`, `xargs` **with any flag**.
**Absent from the list, therefore not stripped:** `sudo`, `env` — which is why ticket 82's original premise was wrong and the rescope was correct.

## 2. Leading assignments — verbatim, and allow/deny are asymmetric

> "Claude Code also strips a leading assignment of certain known-safe environment variables, so `Bash(npm test *)` matches `NODE_ENV=test npm test`. An allow rule won't match past an assignment of any other variable. A deny or ask rule matches past any leading assignment, so `Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`."

This is ticket 77's subject and is already implemented. **Note the asymmetry is documented for leading assignments ONLY** — the wrapper example above is itself an *allow* rule, so do not import the asymmetry into wrapper stripping. That exact over-generalisation is one of the two failures that produced the native-fidelity rule.

## 3. NEW — a SECOND mechanism, not in ticket 82's scope as filed

> "Exec wrappers such as `watch`, `setsid`, `ionice`, and `flock` can't be auto-approved by a prefix rule like `Bash(watch *)`, so in Manual mode they always prompt. The same applies to `find` with `-exec` or `-delete`: a `Bash(find *)` rule doesn't cover these forms. To approve a specific invocation, write an exact-match rule for the full command string."

**This is the inverse of stripping and toolguard may implement neither.** Nine wrappers are stripped so rules see *through* them; four others (`watch`, `setsid`, `ionice`, `flock`) plus `find -exec` / `find -delete` are **barred from prefix auto-approval entirely**.

Two distinct fidelity gaps, and only the first is what ticket 82 was rescoped to. **Measure both before implementing**, and if the second is also absent, decide explicitly whether it belongs in 82 or in its own ticket rather than widening 82 silently.

**It also intersects proposed ticket 88**, which chose `find` as its worked example for "a rule needing exceptions". Native already treats `find -exec`/`-delete` specially — 88's design must be re-read against this quote rather than against my recollection of it.

## 4. Two incidental confirmations of already-shipped work

> "The `:*` form is only recognized at the end of a pattern. In a pattern like `Bash(git:* push)`, the colon is treated as a literal character and won't match git commands."

Confirms **ticket 18**'s fix (`c5e50a5`, *"a colon is only a wildcard at the end of a pattern"*) is faithful to native as documented on this date.

> "When `*` appears at the end with a space before it (like `Bash(ls *)`), it enforces a word boundary, requiring the prefix to be followed by a space or end-of-string. For example, `Bash(ls *)` matches `ls -la` but not `lsof`. In contrast, `Bash(ls*)` without a space matches both `ls -la` and `lsof` because there's no word boundary constraint."

The word-boundary rule, also ticket 18's territory. **Verify toolguard reproduces the `ls *` / `ls*` distinction** — it is a behaviour difference that a migrated rule would carry silently.

---

# MEASURED AGAINST toolguard, 2026-08-21

Probe config used `no_match_fallback = "ask"` so an unmatched rule is visible. **My first attempt used `allow_with_no_warnings` and every result came back `allow`** — the replay blind spot this campaign documented, reproduced by me in a fresh probe an hour after writing the rule about it.

## 1. Wrapper stripping — toolguard strips NONE of the nine

Allow rule `Bash(npm test *)`; every one of `timeout 30`, `time`, `nice`, `nohup`, `stdbuf -o0`, `command`, `builtin`, `noglob`, and bare `xargs` gives **`ask`** where native gives allow.

**Divergence is in the RESTRICTIVE direction** — extra prompts, never extra permission. Per the fidelity rule that is still a defect (*"a divergence that is 'safer' is still a defect"*), but it is friction, not exposure.

Correct on the not-stripped forms — `command -v`, `xargs -n1`, `sudo`, `env` all `ask` — though **correct by accident**: toolguard strips nothing, so it cannot over-strip.

**Field basis: zero.** Commands led by a stripped wrapper: featherhill **0**, instagram **0**, toolguard 29 (probe fixtures). Nobody writes `timeout 30 npm test` in these projects.

## 2. The exec-wrapper bar — unimplemented, and one case is PERMISSIVE

With `Bash(watch *)` and `Bash(find *)` allow rules present:

| command | toolguard | native |
|---|---|---|
| `watch ls` | **allow** | prompts — cannot be auto-approved by `Bash(watch *)` |
| `find . -delete` | **allow** | prompts — `Bash(find *)` does not cover `-delete` |
| `find . -name x` | allow | allow |

**This divergence runs the other way: toolguard grants what native withholds, and `find -delete` destroys files.** Exactly the shape the fidelity rule exists for — a migrated `Bash(find *)` means something more permissive here than where it was written.

## 3. Word boundary — FAITHFUL

`Bash(ls *)` matches `ls -la`, does **not** match `lsof`; `Bash(lsx*)` matches both. Confirms ticket 18's fix (`c5e50a5`) against native as documented today.

---

# EXPOSURE — and the featherhill count is CONTAMINATED

| | featherhill | toolguard | instagram |
|---|---|---|---|
| `Bash(find ...)` rules | 1 | 4 | 0 |
| `Bash(watch\|setsid\|ionice\|flock)` rules | **0** | 2 | 0 |
| `find -exec`/`-delete` commands | 9 | 39 | 0 |

**8 of featherhill's 9 are probes** — `-exec echo {}` three times, `-name 'nonexistent-CLAUDE.md' -delete` — from a toolguard investigation run with featherhill as cwd on 2026-05-11. One is genuine: `find flowers/test -name "*.py" -exec grep -l "class.*unittest.TestCase" {} \;`, which is **read-only**.

Every logged `find -exec`/`-delete` in featherhill matched rule **`*`** or nothing — **not** a `Bash(find *)`-shaped rule. So the combination that triggers the divergence has **zero occurrences**.

## Disposition — DEFER CANDIDATE, flagged for Arnon

**Do not fold either gap into ticket 82 unilaterally.**

- **Wrapper stripping (82 as rescoped)**: real fidelity gap, restrictive direction, zero field basis. Worth doing because `auto_migrate` imports native-authored rules — but it is friction-only, so it does not justify scope growth.
- **The exec-wrapper bar (NEW)**: permissive direction and a destructive command, which normally forces a fix. But it needs a `Bash(find *)`-style allow rule that **exists nowhere in any corpus**, and Claude does not write `find -delete` to evade a rule — the reachability filter applies.

Recommend: **implement 82's wrapper list; file the exec-wrapper bar as its own ticket** with this measurement attached, rather than widening 82. It also changes proposed ticket **88**, whose worked example is `find` — 88's design must be re-read against the fetched quote, not against recollection.

---

# IMPLEMENTATION SHAPE, measured 2026-08-21 — and the hazard it walks into

## The mechanism already exists

`command_spellings()` (`toolguard/parser/command_extractor.py:889`) produces a `CommandSpellings` — *"the further spellings of one leaf command each kind of pattern list may match"* — consumed by `toolguard.permissions`. Ticket 77 built it for leading assignments. **Wrapper stripping is the same question**: one more way the same command may be spelled.

So 82 extends an existing mechanism rather than adding one. That is the cheap and correct shape.

## THE HAZARD — widening this pair is the exact move that has bitten twice

`CommandSpellings`' own docstring:

> *restricting: ... A leading `NAME=value` assignment is looked past here **unconditionally**.*
> *granting: ... An assignment prefix is looked past only for names configured safe to look past, and **that asymmetry is the whole point of the pair**.*

**The pair exists because assignments are asymmetric.** `LD_PRELOAD=evil ls` is genuinely not `ls`, so a grant must not see past it while a restriction must.

**Wrapper stripping is NOT asymmetric.** Per the fetched doc (2026-08-21), native strips nine wrappers before matching, and its worked example is an **allow** rule — `Bash(npm test *)` matching `timeout 30 npm test`. Nothing in the page says deny behaves differently for wrappers. `timeout 30 rm -rf /` **is** `rm -rf /`; the wrapper runs its argument as the actual command, exactly as the doc says.

So the stripped-wrapper spelling belongs in **both** `restricting` and `granting`.

**That means the pair will carry two kinds of spelling with different symmetry rules**, and its docstring's claim that the asymmetry *"is the whole point"* stops being true.

**This is `one structure, two questions` — the failure recorded in auto-memory as having occurred twice in two tickets, once downgrading an unoverridable `hard_deny` to `ask` with a green suite.** Widening a shared structure for a new consumer silently changes the existing one.

**Required of the implementer**: state explicitly what each side of the pair means after the change, and verify the assignment behaviour is untouched — `TG_INTENT=1 LD_PRELOAD=x ls` must still not be granted by `allow Bash(ls:*)`. A green suite is not evidence here; ticket 77's tests were written before wrappers existed.

## The fidelity trap this ticket has ALREADY fallen into once

`.claude/rules/native-fidelity-claims.md` records that a prior investigation *"imported ticket 77's allow/deny asymmetry into a wrapper design note marked 'not to be re-derived'"* — and that the asymmetry is documented for **leading assignments only**.

**So the wrong answer here has already been written down once, in a note claiming it need not be rechecked.** Anyone implementing 82 must take the asymmetry question from the fetched doc, not from that note.

## Scope reminder

**Nine wrappers**: `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, `noglob`, and **bare** `xargs`. **Not stripped**: `command -v`, `nocorrect`, `xargs` with any flag, and — by absence — `sudo` and `env`.

The **exec-wrapper bar** (`watch`/`setsid`/`ionice`/`flock`, `find -exec`/`-delete`) is a **separate mechanism**, recommended as its own ticket, and is not part of this one.
