---
title: An annotation is written above every rule that shares its line text, so a deny
  gets a note claiming it shadows itself
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/76-an-annotation-is-written-above-every-rule-that-shares-its-line-text
---

**FIXED in `05f786d` (TOO-45 phase 2).** The annotation index is now allow-only, so a deny rule no longer gets a note claiming it shadows itself; the rationale is documented inline — see `toolguard/tools/annotate.py:103-121`.

# The annotator writes a factually false claim into the user's config

**Found 2026-08-14. One RED test in the tree, proven falsifiable by mutating toward the fix with zero collateral. Follow-up-queue row AE1, now measured end to end.**

## The defect

`_rule_first_line_patterns` builds **one dict keyed by the rule's physical source line**, across `allow`, `deny` and `ask` together.

So with `Bash(git:*)` in **both** the allow and the deny list — a configuration `clarity` itself reports as `deny-shadows-allow` — the allow's note is inserted above **both** lines. The deny then carries the text:

> `# toolguard: deny 'git:*' shadows part of this allow (deny wins)`

as a claim **about itself**. Confirmed end to end through `clarity_annotations` -> `annotate_section_text`, not inferred.

## The obvious fix does not work

Restricting the index loop to `("allow",)` **does not close it**, because the keying is by line *text*, not by list. **The fix must be positional.** (That restriction is also non-equivalent in a second way — it stops deny- and ask-keyed annotations landing at all — so it was deliberately left unpinned rather than enshrined: `clarity_annotations` only ever emits allow-section keys today, and pinning the restriction would freeze a capability no caller uses.)

## The test suite could not see the note text at all

**No test asserted that the note's text reached the file.** Every assertion was `assertIn(TOOLGUARD_MARKER, ...)` or `.count(TOOLGUARD_MARKER)` — so **a writer emitting a constant `# toolguard: note` above every annotated rule passed all 17 tests.** Nineteen tests detect that now.

Four more mechanisms were at outright zero detection, each for a fixture reason worth naming:

| mechanism | why it was invisible |
|---|---|
| the `file_format != "toml"` skip | never exercised |
| note de-duplication | the fixture used two **different** notes, so the duplicate case could not arise |
| the tail after the `[permissions]` section | the fixture put `[permissions]` **last**, so `old_text[end:]` was always empty |
| a newline injected into a generated note | no hostile-character fixture existed |

**Two tests fired against no mutant at all** (`test_no_permissions_section_is_a_noop`, `test_structured_entry_preserves_its_own_source_line_verbatim`). Survivors: **8 of 24 at HEAD -> 4 of 24**, with all four accounted for as proven-equivalent or deliberately-unpinned. 17 -> 35 tests.

## `annotate_config_file` has no signal for "annotated nothing"

`(old, old)` conflates **three** outcomes: no `[permissions]` section, no matching rule, and an empty note list. `maintenance._run_annotate` derives its entire report from `old != new`.

Ticket 29's family again. Each of the three is now covered by a test carrying **its own positive control in the same test**, so "nothing happened" is attributable to the missing rule rather than to a writer that never writes.

## Three equivalent mutants, proven by execution rather than by reading

- `_rule_first_line_patterns`: `content.split("\n", 1)[0]` -> `content` — 63/63 cases identical. The precondition is provable: `parse_permissions_section_with_comments` **raises** on a multi-line entry, so a rule's `content` is always one physical line and the split can never do anything.
- Same function: `if item_type == "rule"` -> `if True` — 63/63 identical, because comment blocks parse to `value is None` and the caller guards on `pattern is not None`.
- `annotate_config_file`'s `if start == -1: return old, old` guard made dead — 54/54 identical, since `find_section_boundaries` returns `(-1, -1)` and the resulting splice is `old[:-1] + "" + old[-1:] == old`.

## Related

The newline findings from the same measurement are folded into **ticket 24**, where the escaping decision already lives: the decided `normalize_entry` fix does not reach the comment renderer, and a newline in a *pattern* separately makes the rule invisible to every analyzer.

`_annotation_text`'s fallback `return finding.explanation` is the one branch that can emit multi-sentence text; `clarity`'s four `_explain*` helpers are newline-free **by accident of wording**, not by construction, and nothing in either module enforces it. A fifth `kind` closes that gap.
