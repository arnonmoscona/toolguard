---
title: '[native] wildcard matching produces false negatives on end-anchored patterns'
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/17-native-wildcard-end-anchor-false-negative
---

> **UPDATE 2026-08-12, test-repair campaign.** This ticket's "why the tests did not catch it" section **understates the blindness by more than half**. It names one survivor (NATIVE rebound to GLOB) plus two absences. Measured in process: **14 of 30 mutations of `patterns.py` survived** — including NATIVE's start anchor and end anchor deleted outright, DEFAULT rebound to GLOB or NATIVE, REGEX rebound to NATIVE or DEFAULT, `re.search` → `re.match`, the `re.error` guard, and `parse_pattern`'s `extended_syntax=False` opt-out. **The REGEX branch had zero coverage in the matcher's own test file.** After repair: 0 of 30 survive.
>
> **The fix could previously have landed with zero test failures.** Applying this ticket's own fix option 1 (`fix_end_anchor`) produced no failure at all before the repair — the suite saw neither the bug nor its correction. It now fails a test, so the fix cannot land silently.
>
> **A proposed fix shape recorded in the working queue was insufficient.** `[native]cat */x` vs `cat a/b/x` separates NATIVE from GLOB but **not from DEFAULT**, because `fnmatch`'s `*` also crosses `/`. A repair built on it alone would have left `native_as_default` at zero detection. The `?`-as-literal case is what actually separates NATIVE from DEFAULT.
>
> **CLARIFICATION 2026-08-13, from Arnon's question "does native syntax even support an end-anchored rule like `*id_rsa`? I thought it only supports a trailing wildcard."**
>
> **It does support it, and the defect is not the anchor — it is that the search never backtracks.**
>
> - `patterns.py:132-135` implements the end anchor explicitly: *"No trailing `*` — the last segment must end at the command's end."*
> - `docs/permission-patterns.md` documents exactly that shape: **`Bash([native]* install)`** — leading wildcard, ends on a literal, no trailing `*`.
>
> Trace for `*id_rsa` against `cat id_rsa.pub id_rsa`: segments are `["", "id_rsa"]`; `find("id_rsa", 0)` returns **4** (inside `id_rsa.pub`); `pos` becomes 10; the end-anchor check sees `10 != len(command)` and returns False. **`id_rsa` does occur at the end — the matcher found the first occurrence, advanced past it, and never went back.**
>
> **So the fix is narrower than this ticket implies.** Not "add end-anchor support" but **anchor the final segment to the end of the command, or let the search backtrack.** Cheaper, and it does not touch the anchoring logic that already works.
>
> ### FIDELITY QUESTION SETTLED — checked against Claude Code's own documentation
>
> Arnon asked whether native even supports an end-anchored rule, recalling that it took only a trailing wildcard. **It does support it.** From Claude Code's permissions documentation, verbatim:
>
> > *"Bash permission rules support wildcard matching with `*`. **Wildcards can appear at any position in the command, including at the beginning, middle, or end**"*
> >
> > *"`Bash(* install)` matches any command ending with ` install`"*
>
> So `[native]` is **correct** to offer the shape, this ticket's premise holds, and the fix is **make the final segment anchor to the end / let the search backtrack** — not "stop accepting a shape native lacks."
>
> The defect itself is **still live and unfixed**: `match_command("cat id_rsa.pub id_rsa", ["[native]*id_rsa"])` → `(False, None)`. See the test-repair plan for the open decision on how a known-unfixed defect should be pinned.

# `[native]` wildcard matching produces false negatives on end-anchored patterns

**Severity: this can silently weaken a `deny` or `ask` rule.** Found during the TOO-45 #07 comment sweep, by executing a docstring claim rather than reading it.

## The defect

`toolguard/patterns.py`'s NATIVE branch splits the pattern on `*` and walks the literal segments with `str.find`, advancing a cursor. The final check is:

```python
if segments[-1] and not pattern.endswith("*") and pos != len(command):
    return False
```

`pos` holds where the **first** occurrence of the final literal segment ended. Requiring that to be end-of-string is wrong: the matcher needs the **last** occurrence, or a backtracking search. Leftmost-first is provably fine for the middle segments — the defect is entirely in the end anchor.

Minimal reproduction:

```
match_pattern(NATIVE, "a*a", "aXaYa")  -> False   # should be True
match_pattern(NATIVE, "*a",  "aa")     -> False   # should be True
```

## Characterisation

Brute-forced every pattern of length <= 4 over `{a, b, *}` against every command of length <= 5 over `{a, b}` — 7,623 pairs — against a reference implementation (`".*".join(re.escape(s) for s in pattern.split("*"))` under `re.fullmatch`, DOTALL):

- **416 mismatches, across 46 distinct patterns.**
- **Every mismatch is a false negative.** The matcher under-matches; it never over-matches.
- **Every mismatch pattern is end-anchored.** Zero mismatches among patterns ending in `*`, across every multi-wildcard shape in the sweep. A trailing `*` fully immunises a pattern.
- The most common failing shape is `*<literal>` — 280 of the 416 — not the two-literal `a*a` the minimal case suggests.

**The affected class, stated exactly:** every NATIVE wildcard pattern not ending in `*` whose final literal segment is **found before the end of the command, relative to the scan position** — the end-anchor check tests that occurrence rather than the last one.

Getting this wording right took two attempts, and the failed one is worth recording because it is the tempting one. *"…whose final literal also occurs earlier in the command"* is **necessary but not sufficient**: tested as a predicate over the brute-force corpus it under-fired 0 times but **over-fired on 204 pairs**. Counterexample: `NATIVE 'a*a'` vs `'aa'` matches **correctly**, even though `a` occurs earlier — that earlier occurrence was consumed by a preceding segment, so it was never in the final segment's search window. The condition is about the cursor, not the string.

A pattern with no `*` at all is also unaffected: `'abc'` vs `'abcabc'` returns `False` correctly, via the fast path.

## Why it matters

A false negative on an `allow` rule costs one unnecessary prompt. A false negative on a **`deny`** or **`ask`** rule means the rule does not fire on a command it was written to catch — a silent bypass, with nothing in the log to indicate the rule was even considered and rejected.

Plausible rules a user would actually write, all in the failing class:

```
NATIVE '*id_rsa'    vs 'cat id_rsa.pub id_rsa'            -> False (should match)
NATIVE '*.env'      vs 'cp .env.bak .env'                 -> False (should match)
NATIVE '*--force'   vs 'git push --force origin --force'  -> False (should match)
NATIVE '*rm'        vs 'rm foo && rm'                     -> False (should match)
NATIVE 'git * main' vs 'git push a main b main'           -> False (should match)
NATIVE '* install'  vs 'npm install pkg install'          -> False (should match)
```

**`docs/permission-patterns.md:115-118` advertises two of these shapes as worked examples** — `Bash([native]git * main)` and `Bash([native]* install)`. Both are end-anchored, so both are in the failing class.

Immune, for contrast:

```
NATIVE 'sudo *'   vs 'sudo rm -rf /'          -> True
NATIVE 'rm -rf *' vs 'rm -rf / rm -rf'        -> True
NATIVE '*secret*' vs 'echo secret secret'     -> True
```

## Fix options

1. **Anchor on the last occurrence.** For the final segment when the pattern does not end in `*`, use `command.endswith(segments[-1])` and check the cursor has not overrun, instead of comparing `find`'s result to the length.
2. **Translate to a regex once.** `".*".join(re.escape(s) for s in pattern.split("*"))` under `re.fullmatch` is the reference implementation the sweep tested against; it is correct on all 7,623 pairs and is arguably simpler than the cursor walk. Stdlib-only, so it costs no dependency.

Option 2 removes the whole class rather than patching one anchor. Option 1 is the smaller diff.

## Why the tests did not catch it

**`test_patterns.py` has 15 tests that cannot distinguish NATIVE from GLOB.** `TestNativePattern` (13) plus `TestPatternTypeComparison` (2). Measured: rebinding `match_pattern` so `PatternType.NATIVE` dispatches to the **GLOB** branch — deleting the entire hand-written no-backtracking segment scanner — leaves **all 15 passing**.

The two semantics do differ, and the input that separates them is this defect:

```
match_pattern(NATIVE, "*id_rsa", "cat id_rsa.pub id_rsa")  -> False
match_pattern(GLOB,   "*id_rsa", "cat id_rsa.pub id_rsa")  -> True
```

So the test file for the matcher never exercises the one behaviour that makes NATIVE a distinct pattern type. `test_glob_vs_native_wildcard_semantics` is the clearest case: its Then promises *"GLOB's `*` spans spaces … while NATIVE finds the segments in order"*, and its body is three `assertTrue`s that GLOB satisfies identically, with no `assertFalse` anywhere.

**Two lines fix the coverage**: one `assertFalse` on the pair above, one `assertTrue` on the GLOB counterpart. That pins the end-anchor, the type distinction, and this defect at once.

Also unpinned in that file: `match_pattern` is never called with `DEFAULT` at all, and GLOB `**` is never used outside a whole path component — so the `**`-degrades-to-`*` behaviour (`"/tmp/a**b"` vs `/tmp/a/x/b` → `False`) has no test either.

## Test obligation

Whichever fix: the brute-force differential above should become a test. It is cheap (7,623 pairs runs in well under a second) and it is the only thing that would have caught this. A handful of hand-written cases would not have — the failing shapes are not the ones a person thinks to write.

## Also worth deciding in the same ticket

- `match_pattern`'s **DEFAULT branch has no live caller**. `permissions.py:118` is guarded to REGEX/GLOB/NATIVE; `file_matching.py:101-102` remaps DEFAULT to GLOB before calling; no test passes DEFAULT either.
- `except ValueError, TypeError` in the GLOB branch is largely dead — `full_match`'s Python 3.14 body contains no `raise` on any path, and `None` cannot arrive via `parse_pattern`. The same catch is **duplicated** at `file_matching.py:113`, wrapping the call that already swallows both.
- Two non-`str` inputs escape the guard entirely, raising from `expand_tilde` *outside* the `try`: `match_pattern(GLOB, b'/a', '/a')` raises `TypeError`, `match_pattern(GLOB, 1, '/a')` raises `AttributeError`.

## Related, found in the same pass

`toolguard/permissions.py`: the GLOB and NATIVE branches bypass the DEFAULT newline guard, and *any* colon triggers the `cmd:args` split. Separate defect, same layer, probably the same ticket's neighbourhood.
---

## FIELD EXPOSURE MEASURED 2026-08-20 — 57,148 real decisions

Corpora: `~/projects/flowers/featherhill/logs` (49 daily logs, 4,722 decisions — **a real user project, the corpus that counts**), `toolguard/logs` (51 logs, 52,191 — dogfood, biased to this repo's own development), `instagram-downloader/logs` (7 logs, 235).

| shape this ticket needs | featherhill | toolguard | instagram | total |
|---|---|---|---|---|
| `[native]` rules of ANY shape | **0** | **0** | **0** | **0** |
| `[native]` end-anchored (the defect) | 0 | 0 | 0 | **0** |

**The `[native]` pattern type is not used at all — zero occurrences in 57,148 decisions.** This ticket is entirely about `[native]` matching, so its real-world exposure is not merely low, it is nil, and it cannot rise until somebody writes their first `[native]` rule.

**DEFER CANDIDATE — moved to the bottom of the queue and flagged for Arnon to re-decide.** The coordinator previously argued for fixing this on "silent and reachable by accident" grounds. That reasoning was sound about the *defect* and wrong about the *exposure*: a defect in an unused feature is reachable by nobody. This is the same misjudgement as the `sudo` case, caught by the same measurement Arnon asked for.

Counter-argument to weigh: the defect is a **false negative on a deny rule**, which is silent forever, so the first `[native]` deny rule anyone writes would fail quietly. The fix is also small and well-characterised (a 7,623-pair differential already exists). Cheap insurance against a feature that is documented and advertised in `docs/permission-patterns.md` with two worked examples — both of which are in the failing class.

### RE-MEASURED under Arnon's lens, 2026-08-20 — "no syntax qualifier and `[native]` are basically the same"

He is right, and it changes the denominator completely: the exposed population is not the zero `[native]`-prefixed rules but **every no-prefix rule**, of which there are **42,113** across the three corpora.

The exposed subset is still empty, for a better reason:

| | featherhill | toolguard | instagram | total |
|---|---|---|---|---|
| no-prefix (native-intent) rules | 3,651 | 38,434 | 28 | **42,113** |
| ends in `*` — **immune** | 3,649 | 38,409 | 28 | **42,086** |
| **END-ANCHORED — the defect class** | **0** | **0** | **0** | **0** |

(A first pass reported 38,390 end-anchored in the toolguard corpus. **That was a measurement error** — toolguard's newer log format appends a provenance suffix, `` `grep *  [project: .../toolguard_hook.toml]` ``, so the count was of rules ending in `]`. featherhill's older format carries no suffix, so featherhill-derived figures elsewhere are unaffected.)

**Why the immunity is structural rather than lucky.** The natural rule shape is a *prefix* rule — `grep:*`, `uv run python:*`, `~/projects/**` — and `:*` **is** the trailing wildcard. Claude Code's permission dialog writes prefix rules by construction when a user picks "Yes, and don't ask again". **So the mechanism that generates the overwhelming majority of rules emits the immune shape every time**, and an end-anchored rule can only arrive by somebody hand-writing a suffix match.

**The residual risk, stated precisely, because the corpora cannot speak to it.** The population that hand-writes end-anchored patterns is disproportionately people writing **deny** rules — `deny Bash(*id_rsa)` is this ticket's own example, and both worked examples in `docs/permission-patterns.md` (`Bash([native]git * main)`, `Bash([native]* install)`) are in the failing class. These corpora are almost entirely *allow* decisions, so a zero here is evidence about allow-rule authors and **silent about deny-rule authors**.

So: defer on **"nobody writes this shape"**, not on "this shape is safe" — and revisit the moment a deny rule not ending in `*` appears anywhere.
