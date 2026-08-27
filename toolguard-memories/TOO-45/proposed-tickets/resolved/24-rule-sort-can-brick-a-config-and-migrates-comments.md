---
title: 'rule_sort: can render a config that no longer parses, and silently re-attributes
  comments'
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/24-rule-sort-can-brick-a-config-and-migrates-comments
---

**FIXED in `05f786d` (TOO-45 phase 2).** `rule_sort` no longer bricks a config and `annotate.py` re-attributes comments correctly — see `toolguard/rule_sort.py:104-130` — but note: the audit found this was implemented by escaping embedded newlines, the mechanism this ticket's own decision block explicitly rejected.

> **THE DECIDED FIX DOES NOT REACH A SECOND SURFACE. Measured 2026-08-14, RED test in the tree.**
>
> Your decision was to **normalise newlines to spaces in `normalize_entry`**. That closes the pattern path. It does **not** close the **comment renderer**: `annotate`'s notes are *generated prose* and never pass through `normalize_entry`.
>
> Measured by writing the file and parsing it back with `tomllib`: a newline in a note gives `TOMLDecodeError: Invalid value` — the break ends the `# toolguard:` comment and the remainder becomes a bare line inside the `allow = [` array. `\r\n` does the same and leaves a stray `\r`.
>
> **Everything else is inert, which narrows the fix usefully**: a note is a TOML **comment**, so `"`, `\`, `"""`, `]`, `,`, `#`, tab, `=`, `'`, non-ASCII and even a `'Bash(rm -rf /)'` lookalike all survive and parse. **Line breaks are the entire escaping surface.** Verified over 9 hostile notes x (tomllib parse + permission-list equality + a 4-command re-decide through `api.decide`), plus one real write-to-disk-and-reread.
>
> RED: `test_a_newline_in_a_note_keeps_the_section_parseable`. Proven falsifiable — a line-breaks-only collapse turns it green with zero collateral, while a whitespace-collapsing variant that also eats tabs breaks the tab case. **The minimal correct fix is line-breaks-only**, which is a useful narrowing of your decision.
>
> **Latent, not live** (queue AE4 confirmed) — and the reason is the next finding.
>
> ## A NEWLINE IN A PATTERN ALSO MAKES THE RULE INVISIBLE TO EVERY ANALYZER
>
> Measured: `per_layer_rules(config, "Bash")` returns the deny body as the literal **`'Bash(git\npush:*)'` — wrapper intact** — where the same pattern with a space returns `'git push:*'`.
>
> So a newline **silently defeats the `Tool(...)` unwrapping**, every downstream analyzer receives a body it cannot parse, and **the rule becomes invisible to `clarity`.** That is precisely what makes the comment-renderer defect unreachable today: **one defect is masking another, and fixing either alone will expose the other.**
>
> Likely cause: `entries_for_tool`'s unwrap regex missing `re.DOTALL`. Ticket 31 already lists that same function's `endswith(")")` check as a repo-wide zero-detection mechanism.
>
> **UPDATE 2026-08-12, test-repair campaign. The defect is confirmed and now has a RED test asserting the CORRECT behaviour — it will go green the moment the fix lands.**
>
> `test_rule_sort.test_newline_in_additional_context_keeps_the_section_parseable` currently fails with `TOMLDecodeError: Illegal character '\n'` over the section `reassemble_permissions_section` just wrote. **Nothing is pinned to the broken shape.**
>
> **SECOND CORRECTION, 2026-08-13 — my first correction was also wrong, and this one is measured by test ID.** I wrote that the 16 was "sourced entirely from `test_migration.py`". Diffing **test IDs** (not counts) against the concurrent-repair baseline: the 16 newly-detected tests are **1 in `test_migration.py`, 2 in `test_rule_sort.py`, and 13 in `test_tools_installer.py`.** The count reproduces; my attribution did not. The working queue's original MIG entry — "16 … including 1 here and 12 in `test_tools_installer`" — was right all along, and I overwrote a correct note with a wrong one.
>
> **Twice wrong on the same figure is the finding.** Both errors came from reading a count rather than the identities behind it. **A failure count attributes nothing; diff the test IDs.**
>
> **PRECONDITION CHECKED 2026-08-13, after Arnon asked "what newline in `additionalContext`? Those are not allowed in the first place."**
>
> **Correct as intent, not enforced anywhere.** Measured at all three layers that could refuse it:
>
> | stage | result |
> |---|---|
> | TOML syntax | **permits it** — `"a\n b"` as an escape, and `"""..."""` multi-line, both yield a real newline |
> | `normalize_entry` | **accepts it, `issues: ()`**, newline kept in metadata |
> | `load_configuration` | **`parse_failures: ()`, `validation_issues: 0`** |
>
> And it is not an exotic input: `additionalContext` exists to inject guidance text, so multi-line guidance is the natural thing to write. A user, an agent, or the maintenance skill can produce one without doing anything unusual.
>
> **So the framing changes.** This is not "a newline sneaks past validation" — **there is no validation, and the writer cannot represent what the reader accepts.** The config loads clean and the damage surfaces later, in a different component, as `seed-hard-deny` exiting 2.
>
> ## DECIDED BY ARNON 2026-08-13 — normalise, do not escape and do not reject
>
> **Intent: a newline is NOT allowed in `additionalContext`. That intent must be ENFORCED — in the runtime AND in the tests.** Today it is enforced in neither; it exists only as an unstated assumption.
>
> **Enforcement mechanism: replace any newline with a single space.**
>
> His reasoning, and it settles the three-way choice above:
>
> - **Not escaping.** Emitting `\n` escapes would make multi-line `additionalContext` a supported capability — a toolguard-specific extension to what the config format carries. He does not want that surface.
> - **Not rejecting.** Rejection discards the user's text and turns a cosmetic problem into a failed load. **Normalising preserves the text**; only the line break is lost.
> - **Replacing with a space** leaves the value valid TOML by construction, so no downstream writer can ever emit an unparseable section — which closes this ticket's original defect at the source rather than at each renderer.
>
> **Priority: low.** His words: *"Unlikely situation anyway."* Correctness of the fix matters more than urgency.
>
> ### Where to enforce it — my inference, not his instruction
>
> `normalize_entry` is the single normalize/merge chokepoint every permission entry passes through, so normalising there covers every writer at once and means `_escape_toml_string` can never see a newline. If it is done anywhere later, each renderer needs its own copy — the shape proposed ticket 52 already shows going wrong (two guards, fixing one hides nothing).
>
> ### Consequence for the RED tests already in the tree
>
> Both go green under this fix, which is the right outcome and worth checking explicitly when it lands:
>
> - `test_rule_sort.test_newline_in_additional_context_keeps_the_section_parseable` — the section stays parseable because the newline became a space.
> - `test_tools_installer.test_a_newline_in_an_existing_entrys_context_still_seeds_hard_deny` — seeding succeeds for the same reason.
>
> **A third test is owed and does not exist yet**: one pinning the normalisation itself — that a newline written into `additionalContext` is read back as a space. That is the "enforced in tests" half of his instruction, and without it the runtime enforcement is unguarded in exactly the way this campaign keeps finding.
>
> **SEVERITY ESCALATION 2026-08-13 — this defect can BLOCK SELF-PROTECTION FROM EVER BEING INSTALLED.**
>
> `installer._render_hard_deny_section` re-renders **every pre-existing `[hard_deny]` entry** through `render_toml_entry` → `_escape_toml_string`. Measured: with a newline in an existing structured entry's `additionalContext`, **`toolguard-install seed-hard-deny` and `seed-self-perms` both exit 2** (`invalid TOML -- Illegal character '\n'`), so **the canonical hard-deny rules and the self-integrity protections can never be seeded at all.**
>
> The write guard behaves correctly — the config is left untouched — so this is a clean failure rather than a corrupted file. But it means **an escaping bug gates the installation of the protections that stop toolguard deleting itself**, which links this ticket directly to proposed ticket 37's severity. Auto-memory records `~/.toolguard` being wiped four times during install testing.
>
> Also measured and **refuted**: the newline does *not* bite through `write_toml_config`'s permissions path — replay preserves the original source line. **The installer's exposure is the hard-deny renderer only.** RED test: `test_tools_installer.test_a_newline_in_an_existing_entrys_context_still_seeds_hard_deny`, verified green under the fix.
>
> **A CORRECTION TO MY OWN THIRD ATTEMPT AT THE 16.** Having twice got the attribution wrong, I then described `test_tools_installer.py` as "the suite's main defender of TOML escaping" because it held 13 of the 16. **Also wrong.** Measured by test ID: **all 13 are backslash-path detections and none is about escaping** — they fail because canonical self-integrity patterns contain `\b`, `\.`, `\$`. That module had **zero** targeted escaping coverage: removing quote escaping alone was detected by **0** of its tests, and applying this ticket's fix by **0**. A count told me a module was a defender; the identities showed the detections were incidental.
>
> **SCOPE CORRECTION — "bricks the config" is not true on every path.** Measured: a newline in `additionalContext` does **not** brick the config through `write_toml_config`. The write guard parses the candidate text first, refuses, and leaves the file absent or untouched. **The user-visible failure there is a migration that cannot complete — not a config clamped to `ask`.**
>
> The dangerous path is the **unguarded `rule_sort` writers**, which is where this ticket's severity actually lives. Worth saying precisely, because "bricks your config" and "a migration fails cleanly" call for different urgency.
>
> **The original claim about counts, kept for the record.** It says "removing all escaping gives 16 failures; applying the fix gives 0". The 16 is a **full-suite** number. Inside `rule_sort`'s own test module the figure was **0**, and the module was blind in *four* directions:
>
> | mutation of `_escape_toml_string` | failures in `test_rule_sort.py`, before repair |
> |---|---|
> | remove all escaping | **0** |
> | remove quote escaping only | **0** |
> | remove backslash escaping only | **0** |
> | **apply this ticket's fix** | **0** |
>
> After repair: the fix takes the module from 1 failure to 0, and the three away-from-correctness mutations give 3, 2 and 2. **Fixed and unfixed are now distinguishable in both directions** — which is the property this ticket asked for.
>
> **A second, near-miss finding.** §2's comment-migration fix would have to move comments *into* per-rule association. That association had **zero detection** (`drop_rule_comments` and `rule_comment_to_top` both survived). **The §2 fix could have shipped and silently broken ordinary comment travel**, with the suite green. Now covered by `test_comment_on_a_non_first_rule_travels_with_that_rule_after_reorder`.
>
> My own sweep note gave the wrong reason for not testing this — it said the mechanism was "already directly, intentionally pinned", which was true of top-anchor emission and false of the half a fix would touch.
>
> **Method reminder, earned a fourth time:** the round-trip class produced 5 failures under `always_fresh_render`, which reads as coverage. The tracebacks showed all five were byte-identity assertions on the *replay* path, and `rule_sort.py:652` — the from-scratch writer used by JSON→TOML migration — was never executed by any test in its own module. **A failure count alone marks a branch covered.**

# `rule_sort` can render a config that no longer parses, and silently re-attributes comments

Two defects in one module, found in the TOO-45 #07 sweep. The first is severe and has **zero test coverage**, confirmed by mutation.

## 1. A newline in `additionalContext` emits an unparseable config

`toolguard/rule_sort.py`'s `_escape_toml_string` escapes only `\\` and `"`. A literal newline passes through unescaped, so the emitted inline table spans multiple lines -- exactly the shape the module docstring exists to forbid.

Reachable from an ordinary JSON config:

```json
{"additionalContext": "line1\nline2"}
```

**Consequence, stated exactly:** a config that no longer parses clamps every governed decision to `ask` (an already-`deny` decision is exempt -- see the hedged form at `config.py:1526`). So **one enrichment string bricks the config into permanent prompting**, with the damage done by toolguard's own writer rather than by the user.

### Zero coverage, measured

Mutation testing in an out-of-tree copy: removing quote-escaping from `_escape_toml_string` produced **zero detections in `test_rule_sort.py`**. The only test anywhere that catches a broken escaper lives in `test_migration.py`, and it covers **quotes only** -- not the newline case, which is the one that bricks the file.

Confirmed from the other side too. `test_migration.py`'s `test_toml_escapes_special_chars` is the **only** test anywhere that reaches `_escape_toml_string` (via `write_toml_config` -> `generate_permissions_section` -> `render_toml_entry` -> `_render_toml_scalar`), and it exercises **the quote path only**. Nothing anywhere constructs a newline in `additionalContext`.

### The suite cannot see the bug OR its fix

The sharpest form of the measurement, run in an out-of-tree copy:

| mutation | result |
|---|---|
| remove **all** escaping from `_escape_toml_string` | 16 failures -- detected |
| **apply the fix** (also escape `\n`) | **0 failures** -- undetected |

So the escaper is not merely untested at the newline: **the suite is blind in both directions.** A correct implementation and a broken one are indistinguishable to all 2,733 tests. That means the fix ships with no regression safety unless a test lands with it, and it means nobody can tell from a green suite whether this has already been fixed and reverted.

Worth copying as a technique: **mutating toward the fix, not just away from correctness**, is what turned "probably untested" into a number.

### Fix direction

Escape the full TOML basic-string set, not two characters. `\n`, `\r`, `\t` and control characters all need it. Prefer a single escape table over incremental additions -- the incremental form is how it got here.

## 2. A leading comment silently re-attributes to a different rule after a sort

A comment reading *"NEVER remove: this is what blocks the force push"* does not travel with its rule. The first rule's leading block anchors to the top of the sub-list, so after a reorder it sits above whatever rule now comes first.

The failure is silent and the result still parses. A safety note ends up attached to a rule it does not describe, which is worse than losing it -- a reader trusts it.

### This is documented as intended, which is why it survived

`test_rule_sort.test_comment_before_first_rule_stays_anchored_to_top_after_reorder` accurately describes this behaviour and frames it as **"not a bug."** The sentence is *true* about what the code does and *wrong* about what it is for, so it passes every probe and stops the next reader from looking. That shape is the subject of **TOO-52**; this is its clearest instance.

The sweep deliberately left that Given/Then standing rather than rewriting it. **Do not treat it as a specification.**

### Fix direction

Anchor a leading comment block to the rule that follows it, and move both together. If that is genuinely undesirable, the alternative is to refuse to reorder a section containing anchored comments -- but a silent re-attribution is not an acceptable third option.

## Provenance

Both found in the `rule_sort.py` module sweep and the `test_rule_sort.py` test sweep, TOO-45 #07. Recorded in `reports/follow-up-queue.md` (sections `RS`, `RSO`).
