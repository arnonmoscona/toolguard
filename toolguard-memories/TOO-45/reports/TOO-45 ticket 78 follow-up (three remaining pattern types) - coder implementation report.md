---
title: TOO-45 ticket 78 follow-up (three remaining pattern types) - coder implementation
  report
type: note
permalink: toolguard/too-45/reports/too-45-ticket-78-follow-up-three-remaining-pattern-types-coder-implementation-report
tags:
- task-memory
- TOO-45
---

# TOO-45 ticket 78 follow-up — the tilde spelling now reaches every pattern type and every rule kind

**Not committed.** No git write operation was run. Tree checked with `git status` before starting: HEAD `1dfda8e`, the predecessor's four files plus five others already modified. My own baseline run confirmed **3752, OK, 4 expected failures** and `~/.toolguard/errors/` = 1949.

## The fix

One production hunk, in `toolguard/permissions.py:178` — `match_command` now builds `spellings` as each of `command_str` and `also_spelled` **plus** its tilde-expanded form, deduplicated. `spellings` is what the `[regex]`/`[glob]`/`[native]` branch matches against and what the `**/<component>/**` branch reads, and it is the input `_command_variants` expands for the DEFAULT branch, so one accumulation reaches all four types.

Uniformity across rule kinds falls out of where it sits: `match_command` does not know whether it is matching a granting or restricting list — the caller chooses `restricting`/`granting` when it passes `also_spelled` — so adding the spelling here gives it to `allow`, `deny`, `ask`, `hard_deny` and hard-deny carve-outs on identical terms. That is Arnon's decision implemented, not re-litigated.

`_command_variants` keeps its own tilde entry. It is now redundant for `match_command` (its inputs arrive already expanded), but removing it would be a substitution, and it keeps that function's documented contract true in isolation. Cost is one extra `re.sub` per spelling, deduplicated away.

Before and after, through the real matcher:

```
                     DEFAULT  [glob]  [regex]  [native]
abs rule / ~ cmd  before  T       F       F        F
abs rule / ~ cmd  after   T       T       T        T
~ rule / abs cmd  before  T       F       F        F
~ rule / abs cmd  after   T       F       F        F      <- unchanged, see finding 3
```

## Is the brief's reasoning right? Yes, with one real exception

**The identity argument holds.** I checked it by execution rather than accepting it: `expand_tilde_in_command` was compared against real `bash` word expansion over 17 tilde forms. Identity holds for `~/x`, bare `~`, `~/a ~/b`, `HEAD~1`, `foo~/x`, `~//x`, `--file=~/x`, `~-`, `~1`.

**Three under-expansions, all safe** — no spelling is added, so nothing widens: `~root/x` (bash gives `/root/x`), `~+/x` (bash gives `$PWD/x`), and `"~/x"` / `'~/x'` where the quote starts the token.

**One over-expansion, and it is the exception the brief told me to look for.** A `~`-initial token lying inside a quote opened by an *earlier* token gets expanded, and bash would not: `echo 'a ~/b'` yields the spelling `echo 'a /home/arnon/b'`, which no shell would ever produce.

Measured on real traffic: **52 of the 446 leaf commands that gain a spelling (11.7%) gain an over-expanded one.** Every instance observed is a banner string — `echo "=== ~/.claude/CLAUDE.md for rtk mentions ==="` and its siblings.

**I did not suppress it, and here is the reasoning to check.** Suppressing it correctly requires knowing which bytes are quoted, which is word-level bash structure. `command_extractor` exposes leaf command *text*, not words, so the information is not available at this layer; deriving it in Python is exactly the hand-rolled tokenization `CLAUDE.md` prohibits, and the grammar route is a two-phase procedure well outside this brief. A crude "skip the expansion whenever the command contains a quote" would reintroduce the fail-open this ticket exists to close, for every quoted command — strictly worse. Direction of harm is fail-closed for `deny`/`ask`/`hard_deny`; fail-open for `allow` only where a rule author wrote an absolute home path *inside what is textually a quoted string*. **It is also pre-existing** — the predecessor introduced it for DEFAULT; my change extends its reach to the other three types. Recommend a follow-up ticket to expand tilde on grammar-produced words rather than `\S+` tokens.

## The `[glob]` diagnosis: confirmed, and worse than stated

Confirmed directly. `expand_tilde('cat ~/.ssh/id_rsa')` returns its argument **unchanged**, because the string starts with `cat`, not `~`.

Worth adding: `match_pattern`'s GLOB branch expands `~` on **both** sides, and on the Bash side **both** are inert for the same reason — a `[glob]` Bash *pattern* also starts with a command name. So the branch's tilde handling does nothing at all for commands; it is live only for file paths, where the subject really does begin with `~`. `match_pattern` itself is untouched: it is shared with `file_matching`, where `expand_tilde` on a real path is correct and per-token expansion would be wrong for a path containing a space.

## Blast radius

Corpus: **26,431 distinct commands** — every Bash command in all 64 date-stamped daily logs plus every Bash target in the verdict corpus — decomposing to **29,125 distinct leaves**. Taken **unsanitized**: `corpus_build`'s `sanitize_machine_paths` rewrites `/home/arnon` to `/home/tguser`, which would have erased the very thing being measured. Each command resolved through `toolguard.api.decide` against this repo's live configuration, on a pre-change and a post-change package tree, each run asserting which package directory it loaded.

| | before | after |
|---|---|---|
| commands compared | 26,431 | 26,431 |
| containing a `~` anywhere | 865 | 865 |
| leaves gaining a tilde-expanded spelling | 446 | 446 |
| verdict distribution | 26,238 allow / 183 deny / 10 ask | identical |
| **newly deny / newly allow / newly ask** | — | **0 / 0 / 0** |
| winning pattern changed, same verdict | — | **0** |
| `extract_structured()` digests differing | — | **0** |
| commands that raised | 0 | 0 |

### The corpus cannot see this change, and I did not report that as success

The predecessor's warning is confirmed and sharpened. Recounted from the live config: **190 live Bash rules; 7 name the absolute home path; all 7 are `allow`.** So this configuration can only be widened, never tightened, and the deny direction is unobservable in it.

**Granting-side exposure, measured below the cascade** so a rule that *would* fire is counted even where the cascade never reaches it — every live rule against all 29,125 leaves:

| rule kind | matching pairs before | after | delta |
|---|---|---|---|
| allow | 17,500 | 17,500 | **+0** |
| ask | 11 | 11 | +0 |
| deny | 54 | 54 | +0 |
| hard_deny | 23 | 23 | +0 |

Zero widening on real rules against real traffic.

### Deny-direction evidence, constructed deliberately

For each of the 446 leaves that gain a spelling, I synthesized a deny rule naming **that same command spelled absolutely**, in each pattern type, and asked whether the rule catches its own command:

| pattern type | caught before | caught after | **newly denied** |
|---|---|---|---|
| DEFAULT | 342 | 342 | +0 (the predecessor's fix) |
| `[glob]` | 44 | 404 | **+360** |
| `[regex]` | 0 | 445 | **+445** |
| `[native]` | 0 | 445 | **+445** |

That is the ticket's actual subject: **a deny rule of an extended type, naming a location by its absolute home path, previously missed the command that names that same location with `~` in every one of 445 real cases, and now catches it.** DEFAULT's ceiling of 342/446 and `[glob]`'s 404 are pre-existing limits of `fnmatch` and `PurePath.full_match` on strings carrying `[`, `?` and `*`, not anything this change introduced.

### Which commands newly match, in both directions

- **Newly matched, restricting side:** a `[regex]`, `[glob]` or `[native]` rule naming a location by an absolute path under home now matches a command naming it with a leading `~` in any token, including the command name (`~/bin/deploy`).
- **Newly matched, granting side:** the same, for `allow` and hard-deny carve-outs. `allow Bash([regex]^cat /home/arnon/)` now also covers `cat ~/anything`. Real, deliberate, and zero occurrences in this repo's configuration.
- **Newly matched, third branch:** `**/<component>/**` now reads the home path's own segments, so `cat ~/x` answers to `**/home/**`. This follows from the same identity argument — `~/x` *is* `/home/arnon/x`, so `home` genuinely is one of its segments — and it makes that branch consistent with the rest of DEFAULT, which already saw them. Pinned by a test and documented.
- **Still not matched:** `~user`, `~+`, a `~` inside a token (`HEAD~1`), a `~` quoted at the start of its token, and any location the rule did not already name.
- **Still not matched, and it is a gap:** the reverse direction under the extended types — see finding 3.

## Findings — four things stated somewhere that are not so

**1. The predecessor's report says `~ rule / abs cmd` is `True` for `[glob]`. On the command side it is `False`, before and after.** That measurement was taken on the **file-path** side, where the subject really does start with `~`, and does not carry over to commands. Consequence: this fix is **one-directional**. A `[regex]`/`[glob]`/`[native]` deny rule written *with* `~` is still evadable by writing the absolute path — DEFAULT covers that direction via `normalize_path_in_command`'s home collapse, and the extended types have no equivalent.

I deliberately did not close it, and this is not a bare "deferred": closing it means adding a *second* new spelling (an absolute→`~` per-token collapse) — a new normalization primitive and a second widening decision, neither authorized here. **Blast radius of leaving it, measured:** of 190 live Bash rules, **0 are extended-type rules spelled with `~`**, so nothing in this repo is currently evadable this way; the exposure is entirely prospective, against rules not yet written. Recommend a ticket.

**2. "3 of this repo's 7 home-spelled live rules are `[regex]`" — measured now: 2.** Five DEFAULT, two REGEX, seven total, all `allow`. The config is live and may have changed since their run, so this is a re-measurement, not necessarily an error at the time.

**3. New pre-existing production defect, verified, not fixed and not mine.** `parse_pattern` calls `.strip()` on the extracted body. For a REGEX pattern ending in an **escaped whitespace character** — exactly what `re.escape()` produces for any pattern ending in a space or newline — the strip removes the whitespace and leaves a **dangling backslash**, which `re.compile` rejects and `match_pattern` swallows as a non-match:

```
re.escape('ls ~/x \n')         -> 'ls\\ \\~/x\\ \\\n'
parse_pattern body after strip -> 'ls\\ \\~/x\\ \\'
re.compile(body)               -> re.error: bad escape (end of pattern) at position 10
match_pattern(...)             -> False
```

**A `[regex]` deny rule ending in escaped whitespace silently never fires.** This is a fail-open in the same family as the ticket, found because it is the single residual miss in the deny-direction table above (445 of 446). Recommend a ticket.

**4. `docs/permission-patterns.md`'s "Symlink resolution | Up to 3 iterations to prevent loops" was false, and I fixed it** — the predecessor flagged it and declined, saying a correct short replacement was not obvious. `normalize_path` calls `Path.resolve()` **once** (`toolguard/normalization.py:86-90`); there is no iteration count anywhere. The replacement states what the code does and matches the column's example form. Verified by reading the branch before writing the sentence.

**A false alarm I chased and want on the record**, because it nearly became a reported finding: `toolguard/normalization.py` contains `except OSError, RuntimeError:` with **no parentheses** — confirmed at byte level with ordinals, zero `chr(40)`. That is a Python 2 syntax error in every version before 3.14. It parses here because **PEP 758 landed in 3.14** and un-parenthesized `except` tuples are now legal (interpreter confirmed: `3.14.5`, form ACCEPTED). So the auto-memory note *"ruff strips except-tuple parens"* is **correct**, ruff is doing something valid, and there is nothing to fix. I verified before reporting rather than after.

## Duplication check

No new function. The change reuses `expand_tilde_in_command`, which the predecessor added and which is the only per-token tilde expander in the package; `patterns.expand_tilde` (whole-string, leading `~` only) and `path_utils.expanduser` (path-like → `Path`, delegates `~user` to pathlib) both remain distinct and were not merged, for the reasons in the predecessor's report. No new ambient read: `expand_tilde` already answers from `ambient.home()`, so `--ambient` sees nothing new and `PATH_AMBIENT_OWNERS` needs no entry.

## The non-throwing property

Preserved and confirmed on the new path. `expand_tilde` catches `(OSError, RuntimeError)`, which is exactly `ambient._UNRESOLVABLE`; `expand_tilde_in_command` adds only a `re.sub`. `test_an_unresolvable_home_does_not_raise_out_of_any_pattern_type` drives all four pattern types with `Path.home` raising and asserts a verdict rather than an exception.

## Tests added — 8, all in the main suite

`test/unit/test_permissions.py`, new `TestEveryPatternTypeCrossesTheTwoHomeSpellings`: every pattern type sees the `~` spelling; a deny rule reaches it through `check_permission`; **an allow rule reaches it on the same terms** (the assertion that pins Arnon's decision); a further spelling (`also_spelled`) is expanded too, so the assignment-prefix and tilde accommodations compose; a `**/<component>/**` pattern now answers to the home path's segments; `~root` is not expanded under any type; an unrelated file under home is not matched under any type; an unresolvable home does not raise out of any type.

**7 of the 8 fail against the pre-change `permissions.py`** — verified by swapping the backed-up file in and out in a single shell command. The eighth is the non-raising guard, correctly true in both states.

**No existing test was modified or deleted.** The only edit to an existing line anywhere under `test/` is `import re` added to the import block — an addition, no deletion. Nothing was written under `coder-test/`; the harnesses live in the scratchpad and nothing landed in the repo.

## Verification

| check | result |
|---|---|
| full suite, real `$HOME` | **3760, OK, 4 expected failures** (baseline 3752 + 8 added) |
| full suite, empty `$HOME` + `XDG_CONFIG_HOME` | **3760, OK, 4 expected failures** |
| newly red tests | **0** |
| `uv run ruff format .` | 179 files unchanged |
| `uv run ruff check .` | all checks passed |
| `architecture_fitness.py --ambient` | **exit 0** |
| `architecture_fitness.py --layers` | all modules map to one layer; no direction violations |
| `architecture_fitness.py --mocks` | **exactly 1 finding** |
| `corpus_build.py --verify` | 6401 in-process + 61 e2e, **no differences** |
| `check_doc_links.py` | all internal links resolve |
| `~/.toolguard/errors/` | **1949 before, 1949 after** |

## Files changed (4)

Production (1):
- `toolguard/permissions.py` — `match_command` accumulates the tilde-expanded spelling into `spellings`; docstring corrected (it said "the very prefix", which was ticket 77's assignment prefix and no longer covers the set); two-line inline note that GLOB's own expansion is inert on a command line, so nobody deletes this as redundant.

Tests (1): `test/unit/test_permissions.py` — one new class, 8 tests, plus `import re`.

Docs (2, doc-drift sweep):
- `docs/permission-patterns.md` — the "either spelling matches the other" paragraph said the extra spellings were "a DEFAULT accommodation" (now false); the pattern-type table said REGEX/NATIVE do no command normalization (now false) and that GLOB does "tilde expansion only" (true of the call, never of the effect). Rewrote the table rows to name what each type actually does, added the allow-vs-assignment-asymmetry rationale, and fixed the symlink row per finding 4.
- `docs/architecture-as-built.md` — "`[regex]`, `[glob]` and `[native]` bypass all of that and match the raw command" (now false), and the `**/<component>/**` bullet (now reads the expanded spelling too).

Repo-wide grep for the stale phrasings (`DEFAULT accommodation`, `bypass all of that`, `Tilde expansion only`, `four deduplicated spellings`, `match the raw command`) found no other site, including under `.claude/`, searched by explicit path since it is a symlink and gitignored.

## Rollback

Originals of all seven files I might have touched, with sha1s, at `<scratchpad>/t78b/backup/`; `sha1-before.txt` records the pre-change state. My production change is two hunks in one file and reverts cleanly from that copy. Both blast-radius trees, both run outputs, and all four harnesses are under `<scratchpad>/t78b/`.

## Time and cost

| phase | elapsed | est. cost |
|---|---|---|
| Planning: brief, predecessor's report, code survey, baseline suite, four-type matrix, bash identity comparison | ~26 min | ~$2.10 |
| Implementation: one production hunk, docstrings, 8 tests, fail-without-fix verification | ~20 min | ~$1.50 |
| Verification: two suite runs, five fitness/corpus gates, blast radius over 26,431 commands x 2 trees, deny-direction harness x 2 trees, over-expansion measurement | ~40 min | ~$3.20 |
| Doc sweep, the `except`-parens false alarm, reporting | ~14 min | ~$1.10 |
| **total** | **~100 min** | **~$7.90** |
