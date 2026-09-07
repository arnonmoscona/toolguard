---
title: TOO-28 Phase 4a - the interpreter lists finding
type: note
tags:
- task-memory
- TOO-28
- design
permalink: toolguard/too-28/phase-4a-interpreter-lists-finding
---

# Phase 4a: what each interpreter list is for, and one spec correction

Spec section 4.3 flagged *"several different lists in the same module, covering different sets"* as **a smell, no conclusion attached**, and said: look, establish what each was for, decide during design. This is that deliverable.

**Verdict: keep all of them. There is no duplication.** The finding of substance is not about the lists at all -- it is that the spec's reasoning *about* them, in section 6.1, rests on a false premise.

## There are six, not five

| list | location | the question it answers | shape |
|---|---|---|---|
| `BASH_FAMILY` | `command_extractor.py` | is this a shell whose inline code the PEG grammar CAN read? | frozenset |
| `FOREIGN_EXECUTORS` | `command_extractor.py` | is this an executor whose inline code it CANNOT read (so: ASK floor)? | frozenset |
| `_EXECUTOR_FLAGS` | `command_extractor.py` | for this executor, which flags mean inline code, take a value, or name a program file? | dict -> `_ExecutorFlags` |
| `COMMAND_WRAPPERS` | `command_extractor.py` | does this command run *another* command given as its arguments? | frozenset |
| `_ARBITRARY_EXEC_INTERPRETERS` | `tools/danger.py` | for the security audit: does this rule grant arbitrary execution? | tuple |
| `_ARBITRARY_EXEC_PREFIXES` / `_BARE` | `tools/danger.py` | the same question, for the two matching branches that need different shapes | tuples |

## Why they are not duplicates

**`BASH_FAMILY` and `FOREIGN_EXECUTORS` are complements, not copies.** One names executors toolguard can parse, the other executors it cannot. They are disjoint by construction and their union is "things that execute code we care about". Merging them would destroy the only distinction that matters here -- whether the ASK floor applies. Note `csh`, `tcsh` and `fish` sit in FOREIGN despite being shells: the grammar parses bash, not all shells.

**`_EXECUTOR_FLAGS` is a per-member detail table, not a parallel list.** Its keys are a subset of `FOREIGN_EXECUTORS`, and anything absent falls to `_DEFAULT_EXECUTOR_FLAGS`. That is a lookup with a default, which is the right shape; flattening it into the set would lose the per-interpreter flag data entirely.

**`COMMAND_WRAPPERS` answers an orthogonal question** -- "is the real executor further along the command line?" -- and shares no members conceptually. `sudo python -c ...` needs both lists to reach the right answer, which is the clearest demonstration they are different axes.

**`danger.py`'s lists serve a different consumer with a deliberately different membership.** They drive an audit heuristic, not runtime parsing, and the module's own comment records that the omissions are intentional: *"php, deno, bun, pwsh, python2, Rscript and the other shells are knowingly absent"*, and *"not derived from usage evidence"*. Its three variants exist because two matching branches need different shapes (leading prefixes versus bare substrings), which the comment also records.

**So the drift between `FOREIGN_EXECUTORS` and `_ARBITRARY_EXEC_INTERPRETERS` is intended, not accidental.** Adding an executor to the runtime list should NOT automatically add it to the audit list; the audit's membership follows evidence of rules people actually write. That is worth stating because a future reader will otherwise see two interpreter lists and try to unify them.

**Recommendation: no change.** Collapsing any pair would merge distinct questions -- the failure the spec warned about.

## RETRACTED -- what follows was wrong, and section 6.1 stands

**Arnon, 2026-09-07:** *"when there is no rule covering a specific unknown interpreter - then it does get covered by the fallback (yes, the fallback could be unsafe - but that's a configuration/human decision). If there is a rule - then it's not covered, and that's natural. How would toolguard even know that lua is an interpreter if it is not statically told it is?"*

Correct on every point. My error was reading section 6.1's *"it falls through to the fallback"* as meaning `undecidable_fallback` specifically, then building a false-premise claim on that reading. Section 6.1 says *"those fallbacks"*, plural, meaning the section 4.1 pair -- and an unknown interpreter **does** reach `no_match_fallback`, which section 4.1 now makes auto-mode-aware exactly as claimed.

The rest follows: a rule written for an interpreter toolguard has not been told about removes that command from fallback coverage, which is what a rule does. Detecting an unknown interpreter would require inferring intent from shape -- the heuristic this project deliberately refuses. **There is no watertight answer and none is available**; the options are the ones section 6.1 already names.

**What survives** is one documentation line, recorded for section 4.5: setting `undecidable_fallback` stricter than `no_match_fallback` expresses *"I distrust foreign inline code"*, and that protection reaches only the interpreters in `FOREIGN_EXECUTORS`. Worth saying once so nobody reads it as exhaustive.

The analysis below is kept because the measurements in it are real and the reasoning is a worked example of substituting a mechanism for an exposure -- twice, since the first version also invented the rule it measured against.

## SUPERSEDED: the claim that section 6.1's premise is false

Section 6.1 settles the unknown-interpreter question like this:

> **Not a gap for this ticket to close. It is the thing the fallbacks are for.** An interpreter toolguard does not recognise is something it can never directly handle, so it falls through to the fallback -- and making those fallbacks auto-mode-aware is exactly what section 4.1 does. The question dissolves into a capability the ticket already has.

**It does not fall through to the fallback.** An unrecognised interpreter is not classified undecidable at all, so `undecidable_fallback` never fires. The command is parsed as ordinary, matches whatever rules match it, and its inline code runs unexamined.

**Measured 2026-09-07**, live hook, one config with `no_match_fallback = "ask"`, `undecidable_fallback = "ask"` and `allow = ["Bash(lua *)", "Bash(python *)"]`:

```
python -c "import os; os.system(1)"   ->  ask     ASK floor applied (inline/heredoc foreign code)
lua -e "os.execute(1)"                ->  allow   Command matches allow pattern: lua *
```

### CORRECTED, same day, after Arnon asked "where do we have a lua rule?"

**Nowhere. That fixture was invented for the demonstration**, which makes the run above a demonstration of a mechanism, not a measurement of exposure -- the exact substitution `.claude/rules/evidence-before-fixing.md` exists to prevent.

Re-measured against this repository's REAL config, with no rule invented for `lua`:

```
lua -e "os.execute(1)"  ->  allow  "does not match any allow patterns; allowed with
                                    no warning by no_match_fallback=allow"
```

So the exposure path is **`no_match_fallback`, not a rule**. And following that honestly narrows the finding:

| configuration | `python -c` | `lua -e` | diverges? |
|---|---|---|---|
| toolguard defaults (`ask` / `ask`) | ask, via the floor | ask, via no-match | **no** |
| this repository today (`allow` / `allow`) | allow | allow | **no** |
| `no_match_fallback=allow`, `undecidable_fallback=ask` | **ask** | **allow** | **yes** |

**There is no divergence under the defaults, and none in this repository today.** It appears only when `no_match_fallback` is more permissive than `undecidable_fallback` -- the stance *"I trust unmatched commands, but not foreign inline code."*

**That stance is precisely what section 4.1's two independent settings were built to enable.** So the ticket's own feature is what creates the condition, which makes this more relevant to TOO-28 than the original framing, not less -- but the exposure is prospective rather than present, and should be described that way.

**The code already documented this and the spec contradicted it.** `FOREIGN_EXECUTORS`' own comment: *"KNOWN LIMITATION: the list is not exhaustive, and an interpreter missing from it (`lua`, `deno`, `bun`, `julia`) gets no ASK floor at all, so a broad allow rule would cover its inline code too."*

### What follows

1. **Section 4.1's auto-mode fallbacks do nothing for this case.** The fallback never fires, so making it mode-aware cannot help. Section 6.1's dismissal needs rewriting.
2. **Section 4.3's input-source constraint does not help either**, which is worth stating because it looks like it should. Deciding whether an executor's program came from a file requires that executor's flag table; for an unknown interpreter toolguard cannot tell `-e` from a filename, so the constraint has nothing to match on.
3. **So this is an accepted limitation with no mechanism behind it**, and the spec should say that rather than claiming a capability. The mitigations are the ones already implied by section 6.1's evidence principle: add an interpreter when evidence of use appears, and do not write broad allow rules for interpreters.
4. **Reachability, per `.claude/rules/evidence-before-fixing.md`:** toolguard governs Claude, not an adversary. This needs no deliberate evasion, though -- it fires whenever an agent uses an interpreter nobody has added yet and a rule happens to allow it. `deno` and `bun` in a JS project are the plausible cases, not a contrived one.

**Recommended spec amendment**: rewrite 6.1 to say the fallbacks do **not** cover unknown interpreters, that no mechanism does, and that the accepted answer is evidence-driven list extension. Keeping the current text would leave a documented capability that does not exist -- the failure mode this project measures most often.