---
title: TOO-19 Phase 1 increments 3 and 5 coder task recall
type: note
permalink: toolguard/implementation/too-19-phase-1-increments-3-and-5-coder-task-recall
---

## Task
Repo: /home/arnon/projects/toolguard, branch too-19. Ticket TOO-19, Phase 1 (additionalContext feature), increments 3 and 5 combined.
Plan note: basic-memory project toolguard, "TOO-19 Phase 1 Implementation Plan (additionalContext Feature)" - this prompt is authoritative where they differ.

Read /home/arnon/projects/toolguard/CLAUDE.md, ~/.claude/CLAUDE.md, ~/.claude/rules/python.md first.
Key: stdlib-only runtime; unittest NOT pytest; BDD Given/When/Then docstrings on every test; NO function-level imports; docstring on every function/class.

Combined deliberately: increment 3 alone would leave code half-threaded; one coherent change to one file (compound.py) plus resolve.py item 5.

## Already landed - do NOT redo, DO use
- Increment 1: toolguard/rule_entry.py has ADDITIONAL_CONTEXT_KEY, KNOWN_ENRICHMENT_KEYS, RuleEntry.additional_context property.
- Increment 2: ResolvedDecision (config_types.py) and FileResolution (resolve.py) each carry additional_context: Optional[str] = None; Configuration._entry_for_pattern exists in config.py; Configuration._resolve_permission_detailed_unclamped populates it; parse-failure ASK floor clears it.
- Increment 4: toolguard/compound.py::_accumulate_contexts(contexts, max_words=_MAX_CONTEXT_WORDS) -> Optional[str] already exists and fully tested (dedupes exact text, joins blank-line-separated paragraphs first-seen order, greedy FIRST-FIT 500-word budget dropping whole paragraphs, tolerates None entries, returns None when nothing survives). Call it - do not rewrite.

## Scope: Bash/compound path in toolguard/compound.py and toolguard/resolve.py
Do NOT touch hook.py or log_writer.py (increments 6-7) except fixing unpacks if broken.

1. Grow resolve_one's contract from Callable[[str], Tuple[str,str]] to 3-tuple (decision, reason, additional_context). Update type annotations/docstrings on _resolve_leaf, resolve_compound_permission, check_compound_permission.
   check_compound_permission builds resolve_one from toolguard.permissions.check_permission (2-tuple, NOT in scope to change - has many other callers). Adapt in closure (append None).

2. _resolve_leaf (~line 48): thread per-sub-command context into triples -> 4-tuples (decision, reason, cmd, additional_context); return (decision, reason, additional_context).
   - ASK-floor branch (leaf.ask_floor, ~line 80): on deny early-return, pass outer command's context through (deny IS deciding match). On clamped-to-ask path, pass None (floor determines verdict, not rule match) - consistent with _apply_parse_failure_ask_floor in increment 2. Follow unless concrete reason not to; justify in report either way.
   - empty-leaf "deny", "No valid commands found in leaf" path: None.

3. _combine_strictest (~line 250, currently List[Tuple[str,str,str]] -> Tuple[str,str]): takes 4-tuples, returns (decision, reason, additional_context).
   - deny branch: exactly one deciding leaf (denied[0]) - pass its context unchanged, no accumulation.
   - ask branch: same, asked[0]'s context.
   - all-allow branch: EVERY allowed leaf is decision-maker - pass full list of contexts (match order, None's included) through _accumulate_contexts. Applies to single-allowed-leaf case too.
   - final "deny", "No commands to evaluate" fallthrough: None.

4. resolve_compound_permission (~line 350): all_results list becomes 4-tuples; UndecidableSegment and unknown-element-type branch contribute None. Public return type becomes (decision, reason, additional_context).

5. toolguard/resolve.py::resolve_bash_permission_detailed: build resolve_one closure returning 3-tuple, sourcing context from ResolvedDecision.additional_context (already populated by increment 2), surface accumulated result on whatever result type. Read it - there's a BashResolution-style dataclass near FileResolution with backwards-compatible __iter__. If __iter__ exists for legacy tuple unpacking, do NOT add 4th yield (would silently break call sites) - add field, access by attribute, note in docstring.

6. Callers: grep every call site of resolve_compound_permission / check_compound_permission / _resolve_leaf and fix each. hook.py out of scope for wiring value onward, but if it unpacks one of these returns MUST fix unpack (accept 3rd element, ignore). Report exactly what touched in hook.py if anything.

## Tests - extend test/unit/test_compound.py (and resolve.py test file for item 5)
TestAccumulateContexts at end of test_compound.py covers helper already - do not duplicate.
Cover at minimum:
- single allowed leaf with enriched rule surfaces its context
- multi-leaf all-allow compound with 2+ distinct enriched rules -> accumulated paragraphs (assert actual joined text, not just non-None)
- SAME enriched rule matching two leaves of one compound dedupes to one paragraph
- deny in compound passes DENYING leaf's context, not accumulation of allowed ones (most likely to be got wrong)
- ask likewise
- all-allow compound where no rule enriched -> None
- ASK-floor branch behaves as decided in item 2, asserted explicitly both ways (deny-passthrough and clamp-to-ask)
- UndecidableSegment yields None
- existing 2-tuple-unpacking behaviour of any __iter__-bearing result type still works

## Verification before reporting
TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX" -- must report OK. Baseline 1909 tests passing. Empty-HOME form required.
uv run ruff check . clean; uv run ruff format ONLY on files touched.
Duplication/drift self-check before reporting: inventory whether anything added duplicates existing logic in compound.py, resolve.py, or permissions.py; report findings.

## Report
Write implementation report to basic-memory project toolguard, path "TOO-19/TOO-19 Phase 1 increments 3 and 5 implementation report.md", tagged task-memory and TOO-19. Include: ASK-floor decision + justification, every call site changed (esp hook.py), duplication self-check, anything judged out of scope. Do NOT commit to git.
