---
title: 101-scored
type: note
permalink: toolguard/too-45/reports/surprise/101-scored
---

# Ticket 101 scored - grammar accepts a bare `{}`

Commit `03d922c`.

## Production files
| predicted | actual |
|---|---|
| `bash_parser.peg` | yes |
| `bash_parser.py` (canopy-regenerated) | yes |
| phase 2 Python — **predicted EMPTY** | **empty, as predicted** |

**2/2 = 100%.** The prediction that phase 2 would need no Python held: once the grammar accepts `{}` as a word token, the extractor needs nothing — `{}` is an ordinary argument.

## Test files
Predicted "whichever module owns grammar cases; possibly test_multiline_bash". Actual: **a new file I wrote myself**, `test/unit/test_deny_penetrates_constructs.py`, plus `test_verdict_corpus.py` (one population floor) and the goldens. **Missed entirely** — because the test that mattered was not a grammar test, it was a *security* test for a regression the ticket did not anticipate.

## Uncertainties
- **U1 HIT**: phase 2 empty.
- **U2 HIT**: predicted the gap was narrow. Measured — `%`, `@`, `^`, `!`, `=`, `:` all already parse standing alone. `{}` was the only one.
- **U3 — THE ALARM FIRED, AND IT WAS RIGHT TO.** I pre-registered: *"any diff on a command without `{}` means the grammar change was broader than intended — that is the high-value signal."* The first attempt was broader, and the signal that caught it was not the corpus but a direct construct-by-construct diff. Final state: 7 changed goldens, **all brace-bearing**, alarm clear.
- **U4 HIT**: canopy was installed and worked, though not on `PATH` — it lives in the npx cache and in another project's `node_modules`.

## Cause `N` - third instance, and the most serious

The first implementation **opened a deny bypass**: `{ rm -rf /tmp/zz; }` went deny -> allow. Caught before commit, by me, by measuring against the previous tree rather than trusting a clean corpus.

`N` has now fired three times in this campaign (98 chunk 1's placeholder forgery, 98 chunk 2's parse coupling, this). **All three were introduced by careful work, all three were caught pre-commit, and none was predictable from a touch-set estimate.** This one differs from the other two in severity: the earlier two failed closed, this one failed OPEN.

## The methodological result worth keeping

**A clean corpus is not evidence of no regression, for the third measured time.** The corpus contains no brace groups, so `--verify` would have passed while a deny rule silently stopped applying to a whole construct. The permanent answer is now in the tree: `test_deny_penetrates_constructs.py`, 17 constructs, one subTest each, plus a benign-command control so it cannot pass by denying everything.

## Two instrument errors of my own, both caught by contradiction

1. Keyed a golden comparison on `decision`/`command`; the fields are `verdict`/`target`. Reported a false **zero verdict changes**. Caught because it contradicted the population guard.
2. Checked brace-presence against **90-char truncated prefixes** and briefly believed 5 diffs were on brace-free commands. Caught because the one verdict change displayed without visible braces, which did not fit.

**Both were caught by a result that did not fit another result, not by care.** That is an argument for always having a second, independent number to contradict the first.