---
title: 'DEFAULT multi-token prefix patterns over-match: Bash(git commit:*) matches
  git commit-tree'
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/18-default-multitoken-prefix-over-match
---

**PARTIALLY FIXED in `05f786d`.** A token-boundary matcher was added (`toolguard/permissions.py:81-93,203`) and the five seeded uninstall rules rewritten exact; still open: mid-pattern over-match (e.g. `git:* push`) and any-colon splitting (e.g. `curl http://ex.com/*`).

> **IT IS NO LONGER ABSTRACT: TOOLGUARD'S OWN SEEDED SELF-PERMISSIONS OVER-GRANT BECAUSE OF IT. Measured 2026-08-13, 2 RED tests / 20 subtests in `test_tools_uninstall_readiness.py`.**
>
> **All five** multi-token Bash entries in the uninstall-readiness table admit an extra unrelated path argument, and a suffix glued to their final token. The one that matters:
>
> ```
> Bash(rm -rf <skilldir>:*)   admits   rm -rf <skilldir> /etc/passwd
> ```
>
> These patterns are written **verbatim into the user's config** by `installer.cmd_seed_self_perms`. So the ticket's `git logfoo` example understates it: the same defect means **a rule toolguard seeds on its own behalf to remove one directory also permits removing an arbitrary second path.**
>
> Written **RED-asserting-correct**, deliberately against `follow-up-queue.md:1367`'s prescribed fix shape, which was a *characterisation* test. With a citable native-semantics spec (below), pinning the current behaviour would enshrine a divergence. The module's own docstring documents the over-grant and **no test anywhere asserted it** — verified by grep across `test/unit/`.
>
> **AUTHORITATIVE BASIS ADDED 2026-08-13 — this is a documented divergence from Claude Code, not just an over-match we noticed.**
>
> Two adjacent statements in Claude Code's own permissions documentation settle it:
>
> > *"The `:*` suffix is an equivalent way to write a trailing wildcard, so `Bash(ls:*)` matches the same commands as `Bash(ls *)`."*
> >
> > *"When `*` appears at the end with a space before it (like `Bash(ls *)`), it **enforces a word boundary**, requiring the prefix to be followed by a space or end-of-string. For example, `Bash(ls *)` matches `ls -la` but **not `lsof`**. In contrast, `Bash(ls*)` without a space matches both `ls -la` and `lsof` because there's no word boundary constraint."*
>
> So by native semantics `git log:*` ≡ `git log *`, **which enforces a word boundary and must not match `git logfoo`.** toolguard matching it is a divergence from the syntax it claims to mirror — which raises this from a judgement call about desirable behaviour to a **fidelity defect with a citable specification.**
>
> It also gives the fix a precise shape rather than an invented one: **a trailing `*` preceded by a space requires the next character to be a space or end-of-string; a trailing `*` with no space does not.** toolguard needs to distinguish those two cases, and `:*` normalises to the spaced form.
>
> **MEASURED 2026-08-13. All three claims now executed, and the result is worse than the ticket described.**
>
> | pattern | command | toolguard | native says |
> |---|---|---|---|
> | `git:* push` | `git checkout push` | **True** | **should NOT match** — the colon is literal |
> | `git:* push` | `git:* push` | **False** | **should match** — the colon is literal |
> | `git log:*` | `git logfoo` | **True** | **should NOT match** — word boundary |
> | `git log:*` | `git log --oneline` | True | should match ✓ |
> | `ls:*` | `lsof` | **False** | should NOT match ✓ |
> | `ls:*` | `ls -la` | True | should match ✓ |
>
> **Three distinct divergences, not one.**
>
> **1. Mid-pattern `:*` is treated as a wildcard, and it is MORE permissive than native.** `git:* push` matches `git checkout push` — so a user writing what they believe is a narrow rule gets one admitting every git subcommand before ` push`. This is the dangerous direction.
>
> **2. toolguard cannot express what native WOULD match.** `git:* push` does **not** match the literal string `git:* push`, which native accepts. So the divergence runs both ways: it matches what native rejects and rejects what native matches.
>
> **3. The word boundary is enforced INCONSISTENTLY — and this sharpens the whole ticket.** `ls:*` correctly refuses `lsof`. `git log:*` wrongly accepts `git logfoo`. **The boundary holds for a single-token prefix and fails for a multi-token one.**
>
> That is a much more precise statement of this ticket's subject than its title carries. It is not "`:*` ignores the word boundary" — the mechanism exists and works — it is that **the multi-token path takes a different route that skips it.** The fix is to make the multi-token case use the same boundary logic as the single-token case, which is narrower than reimplementing boundary handling.
>
> Probe kept at `scratchpad/colon_star_midpattern_probe.py`; re-run it after any fix, since it covers all three divergences and both correct cases in one table.
>
> ### NATIVE IS A MOVING TARGET — Arnon, 2026-08-13: "this is relatively new behavior for native"
>
> His recollection that native took only a trailing wildcard was **correct for an earlier version**. Claude Code has since added wildcards at any position, and the word-boundary rule.
>
> **That reframes the divergence.** It is probably not an original implementation error — it is **drift**, because the thing `[native]` mirrors changed underneath it. Which has a consequence beyond this ticket:
>
> **toolguard's fidelity to native cannot be established once.** `[native]` is defined by reference to an external, evolving specification, so any claim that it matches native is true only as of a date. A README sentence saying "mirrors Claude Code's native syntax" is a universally quantified claim about a moving target — the exact artifact type this campaign has spent three days finding unreliable.
>
> **Worth its own decision** (recorded here rather than filed separately, since it is the same investigation): does toolguard want a periodic fidelity check against the published native semantics — a small conformance corpus of pattern/command pairs, re-run when Claude Code updates — or does it accept drift and document `[native]` as "native as of version X"? Either is defensible. Silently claiming ongoing equivalence is not.

# DEFAULT multi-token prefix patterns over-match

**Severity: an allow rule grants commands its author did not name.** Found during the TOO-45 #07 comment sweep, by brute-forcing a docstring claim in `toolguard/tools/pattern_overlap.py` rather than reading it.

This is the first **over**-match found in this sweep. The `[native]` end-anchor defect (proposed ticket 17) is a false negative; this one is a false positive, and it runs on the pattern type most users actually write.

## The defect

`toolguard/permissions.py`, `match_command`:

- Line 158 checks that the runtime command's **base command** matches the pattern's base command on a token boundary.
- Line 163 then builds `full_cmd_pattern = bc + cmd_pattern[len(base_cmd):] + "*"` — gluing the trailing `*` onto whatever the pattern's last token was, with no separator and no boundary check.

So the boundary guard covers the **first** token only. Every later token is matched as a bare string prefix.

```
'git commit:*' vs 'git commit -m x'      -> True   (intended)
'git commit:*' vs 'git commit-tree abc'  -> True   (NOT intended)
'git commit:*' vs 'git commitfoo -x'     -> True   (NOT intended)
```

Single-token patterns are safe, because the first token *is* boundary-checked — that is the entire reason `'git:*'` is safe, since `'git*'` would otherwise match by `fnmatch` alone:

```
'git:*' vs 'github status'  -> False   (correct)
```

## Exact scope, confirmed by a second independent reproduction

**An N-token DEFAULT prefix pattern is unguarded on token N and guarded on tokens 1..N-1.**

```
'uv run alembic:*' vs 'uv run alembicfoo upgrade'  -> True   (3-token, over-match)
'a b c d:*'        vs 'a b c dx e'                 -> True   (4-token, over-match)
'uv run alembic:*' vs 'uv runx alembic upgrade'    -> False  (middle token IS space-guarded)
'uv run:**'        vs 'uv runx'                    -> True   (`**` normalises to `*`, same bug)
```

**The explicit-args branch is unaffected** — `'git commit:-m *'` vs `'git commit-tree -m x'` → `False`. It takes the `cmd_pattern + " " + args_pattern` path at line 167 and keeps the separator.

**It does not extend to Read/Write/Edit.** File paths go through `file_matching._match_file_path_pattern`, which promotes DEFAULT to GLOB and uses `PurePath.full_match` — no `cmd:args` split, no synthesized `*`:

```
'/home/x/docs'   vs '/home/x/docsfoo'       -> False
'/home/x/docs/*' vs '/home/x/docsfoo/a.md'  -> False
'/home/x/docs/*' vs '/home/x/docs/a/b.md'   -> False   (`*` does not cross `/`)
'/home/x/doc*'   vs '/home/x/docsfoo'       -> True    (the author's own `*`, not a synthesized one)
```

So the blast radius is exactly: **Bash (and other command-kind tools), DEFAULT pattern type, multi-token prefix with a `:*` or `:**` args part, last token only.**

## Why it matters

`DEFAULT` is the pattern type a user gets when they write no prefix at all — the common case, and the one the documentation leads with. The failure is asymmetric and bad in both directions:

- On an **allow** rule: `Bash(git commit:*)` silently grants `git commit-tree`, which writes objects directly into the object database. The author asked for one verb and got its whole prefix family.
- On a **deny** rule: the same shape over-blocks, which is merely annoying.

The over-grant is the one that matters. Nothing in the log distinguishes an intended match from an over-match — the matched-rule provenance names the rule the author wrote.

## This is already shipped, in toolguard's own seeded rules

`cmd_seed_self_perms` writes uninstall-readiness rules into the user's config at install time, before takeover. **Five** of them are multi-token prefixes, and every one over-grants in both shapes — swallowing a following argument, and matching a longer last token. Enumerated by token count from `required_uninstall_readiness_permissions()`'s own output and measured against the real matcher:

| tokens | seeded `allow` pattern | swallows an argument | matches a longer token |
|---|---|---|---|
| 4 | `uv tool uninstall toolguard:*` | yes | yes (`toolguard-other`) |
| 3 | `rm -rf .../skills/toolguard-security-audit:*` | yes (`… /home/USER/projects`) | yes (`…-BACKUP`) |
| 3 | `rm -rf .../skills/toolguard-maintenance:*` | yes | yes |
| 2 | `rm .../toolguard_hook.toml:*` | yes (`… /etc/passwd`) | yes (`….orig`) |
| 2 | `rm .../toolguard_hook.local.toml:*` | yes | yes |

Unaffected, and worth stating because it bounds the fix: the single-token `cd:*` (`cdx /tmp` → `False`), `toolguard-audit:*` (`toolguard-audit-evil --wipe` → `False`), and the two literal `Write`/`Edit` paths (`settings.json.bak`, `.jsonx` → `False`). Middle tokens are also guarded — `uv tool uninstall toolguard:*` vs `uv toolx uninstall toolguard` → `False`.

*(An earlier draft of this table said four, listing the security-audit pattern twice with two different witnesses and omitting `toolguard_hook.local.toml` and the maintenance skill dir. `follow-up-queue.md` row INS5 inherited the miscount; row UR5 records the correction.)*

`fnmatch`'s `*` crosses spaces, so `rm -rf <skilldir>*` swallows a **second argument**. The first row is the one that matters: an allow rule scoped to deleting one skill directory also permits deleting an arbitrary additional path in the same command.

**`uninstall_readiness.py`'s module docstring defends these rules with a claim the matcher refutes**: *"every pattern here is a literal, single-purpose command or exact file path — not a wildcard grant — so it can only do the one thing it is scoped to."* `_SEED_SELF_PERMS_HELP` inherits the same mis-description.

Single-token seeded rules are safe — `toolguard-audit-evil --wipe` does **not** match `toolguard-audit:*`, because the `startswith(bc + " ")` base gate catches it. The defect needs two or more tokens, and all four rows above have them.

**This raises the fix priority.** Until `match_command` is fixed, the seeded rule set should be reviewed for multi-token prefixes independently — they are in users' configs now.

## Evidence

Brute-forced 79,401 pattern pairs against 798 commands through the real `match_command`. The immediate finding was in `pattern_overlap.prefixes_overlap`, whose docstring claimed two prefix patterns share a command *exactly when* one token sequence is a prefix of the other:

```
claimed-overlap but no shared command: 0
shared command but claimed NO overlap: 315
    ['uv', 'run'] ['uv', 'runx']   witness: 'uv runx'
```

315 counterexamples in one direction, none in the other. Chasing why produced the `match_command` defect above — `prefixes_overlap` is correct about token sequences; `match_command` is not matching on token sequences.

## The fix is NOT localised — measured

Before scheduling this, know the blast radius. The over-match was applied-and-tested in a throwaway repo copy: **the fix breaks 20 tests, and not one of them is in `test_permissions.py` or `test_patterns.py`.**

**Two independent runs both got 20 failures and disagree on which files.** Re-measure before scheduling; do not trust either list below.

| run | reported breakdown |
|---|---|
| A | `test_tools_redundancy`, `test_tools_edit_proposal`, `test_tools_maintenance`, `test_hard_deny`, `test_verdict_corpus` |
| B | 1 `test_api`, 10 `test_tools_consolidate`, 9 `test_tools_maintenance` |

Run B additionally established that **`test_hard_deny` cannot be among them**: every pattern in `test_hard_deny.py` and `test_hierarchical.py` is colon-free, so `match_command` takes the whole-string `fnmatch` branch (`permissions.py:170-173`), while this defect lives entirely in the `":" in pattern_normalized` branch at `:163`. Both modules run 63 tests OK under the fix. Run A's `test_hard_deny` entry is a **name collision** with `test_api.TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command` — which is consistent with run B's single `test_api` failure.

**Located precisely by a third run (the `test_api.py` sweep).** The single `test_api` failure is `TestDecideSimpleBash.test_hard_deny_carve_out_exempts_command`, and its dependency on the defect is direct. The carve-out is `Bash(rm -rf /tmp:*)` against `rm -rf /tmp/foo`: `base_cmd` is `rm`, so the `matched_base` guard at `:158` checks only the `"rm "` prefix, and the pattern actually matched is `full_cmd_pattern = "rm -rf /tmp*"` — the `*` glued onto `/tmp` with no separator is the **sole** reason it matches. Boundary-guarded, the carve-out stops exempting and the verdict flips `allow` -> `deny`.

So **a hard-deny carve-out is reachable only through the over-match**, and carve-outs users have written the same way will stop exempting when this is fixed. The direction is safe — more denying, not less — but it is a visible behaviour change and belongs in the release note, not only in this ticket. (That run reported "22 above the floor" while its own breakdown sums to 20; the instruction to re-measure stands.)

The two runs most likely applied different repairs to the same defect (there is more than one way to restore the boundary), which is itself worth knowing: **the blast radius depends on which fix you choose.** What both agree on:

- **20 tests fail**, all of them **indirect** — nothing in `test_permissions.py` or `test_patterns.py` notices.
- **The consolidation/maintenance tier is where the breakage lands.** `_static_prefix_of`, `prefixes_overlap` and the golden corpus were all built against a matcher that behaves this way, so correcting it moves their answers.

Two consequences:

1. **This ticket cannot be done as a one-line matcher change.** It is a matcher fix plus a re-derivation of every consolidation/redundancy expectation and a corpus regeneration. Ticket 20 and ticket 22 are downstream of it and should probably be scheduled together rather than separately.
2. **The matcher's own tests do not notice.** `match_command("git logfoo", ["git log:*"])` returns `(True, 'git log:*')` today, and nothing in the two files that exist to test matching says a word about it. The 20 failures are all *indirect* — they detect the change through its effect on higher-level analysers, not through any assertion about matching.

Related coverage gaps measured in the same pass, all unpinned in `test_permissions.py`:

- **Ticket 17** — `[native]git * main` matches `git checkout main` but **not** `git checkout main --force`.
- **The GLOB/NATIVE newline-guard bypass** — on leaf `"git status\nrm -rf /"`: DEFAULT `git *` → `False`, `[glob]git*` → `True`, `[native]git *` → `True`. No multi-line fixture exists in the file.
- **The any-colon split** — `match_command("curl http://ex.com/x", ["curl http://ex.com/*"])` → `False`.
- The file's one false-positive test uses a **single-token** pattern, which *is* guarded (`bin/precommit_checks.shX` → `False`). The asymmetry lives on token N of an N>=2 pattern and is never constructed.

## A test docstring documents the over-match as intended behaviour

`test_tools_consolidate.test_consolidation_preserves_prefix_extension_commands` frames this defect as baseline semantics -- its Given/Then describe the over-match as the behaviour consolidation must preserve. Left standing deliberately (the sweep does not launder false prose), but **whoever fixes this must read that docstring as a description of the bug, not of the contract.** It is the most likely place for a fixer to conclude the current behaviour is intended.

## Fix direction

Apply the same boundary rule to the last token that line 158 applies to the first: the `*` should follow a separator, or the final token should be required to end at a token boundary in the command. Concretely, `bc + cmd_pattern[len(base_cmd):]` should be followed by a boundary-respecting wildcard rather than a bare `*`.

**Replay the verdict corpus before and after.** This changes what existing allow rules match, so some currently-allowed commands will start prompting. That is the correction, but it is a behaviour change users will notice, and the corpus is the only way to see its size in advance.

## Test obligation

The brute-force differential above should become a test — it is cheap, and it is what found this. Hand-written cases would not have: the failing shapes (`commit-tree`, `commitfoo`, `runx`) are not the ones a person thinks to write.

## Downstream, fix in the same ticket or immediately after

`pattern_overlap.prefixes_overlap` under-reports overlap (the 315 above). Both consumers — `consolidate.py:856` and `clarity.py:221,286` — use it in the **safe** direction, so today it is a completeness gap in an advisory analyzer and never a wrongly-granted permission. But it is derived from the same confusion, and if `match_command` is fixed to match on token sequences, `prefixes_overlap`'s "exactly when" becomes true and the docstring can go back to stating it.

## Comment defect noted alongside

`permissions.py:146-148`'s base-command-normalization paragraph reads as a description of how the whole command portion is matched, which is precisely what hides the fact that only the base command gets a boundary check. Worth rewriting when the code is fixed — the comment's shape is part of why this survived.

## Related

- Proposed ticket 17: `[native]` end-anchor false negatives. Same layer, opposite direction.
- `permissions.py`'s GLOB and NATIVE branches bypass the DEFAULT newline guard, and any colon triggers the `cmd:args` split.
---

## FIELD EXPOSURE MEASURED 2026-08-20 — 57,148 real decisions

Corpora: `~/projects/flowers/featherhill/logs` (49 daily logs, 4,722 decisions — **a real user project, the corpus that counts**), `toolguard/logs` (51 logs, 52,191 — dogfood, biased to this repo's own development), `instagram-downloader/logs` (7 logs, 235).

| shape this ticket needs | featherhill | toolguard | instagram | total |
|---|---|---|---|---|
| multi-token `:*` prefix rules | **748** | 1 | 3 | **752** |

**This is by far the largest real exposure of any queued ticket, and it is concentrated in the real user project rather than in dogfood.** 748 of featherhill's 3,675 matched rules — roughly one in five decisions — are the shape that over-grants.

**PROMOTE.** This was scheduled LAST on the grounds that its blast radius is heaviest (20 indirect test failures, corpus regeneration, tickets 20 and 22 downstream). That reasoning stands as a cost estimate and is exactly backwards as a priority: it is the only queued ticket with mass real-world exposure, it is an **over-grant** (rules admitting commands their author did not name), and its cost does not fall by waiting.
