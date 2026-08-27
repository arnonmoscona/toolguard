---
title: TOO-45 phase 2 tools-hierarchy tools-mining - coder report
type: note
permalink: toolguard/too-45/too-45-phase-2-tools-hierarchy-tools-mining-coder-report
tags:
- task-memory
- TOO-45
---

## Outcome table

| Test | Outcome | Defect (one sentence) | Fix location |
|---|---|---|---|
| `test_a_disclosure_comment_does_not_split_a_command_from_its_own_group` | GREEN | `_command_key` hand-rolled `.split()` instead of routing through the PEG grammar, so any command carrying the project's own mandated disclosure comment keyed on `#`. | `toolguard/tools/mining.py:159` (`_command_key`) |
| `test_a_command_that_does_not_parse_is_not_offered_as_a_rule_to_add` | GREEN | An unparseable command floored to `ask` by the undecidable net was still classified `allow-candidate`, since `matched_rule is None` for both a safety net and an ordinary no-rule-matched fallback and can't tell them apart. | `toolguard/tools/mining.py:186,277-282` (`_command_has_a_real_leaf` gate) |
| `test_an_empty_command_is_not_offered_as_a_rule_to_add` | GREEN | Same defect, empty-command shape (fail-closed extraction net). | same fix |
| `test_a_currently_denied_command_is_not_summarised_away_as_ask` | GREEN | Cluster verdict picked `Counter.most_common(1)`, so a minority `deny` inside a majority-`ask`/`allow` cluster was discarded. | `toolguard/tools/mining.py:62,305-307` (`_VERDICT_STRICTNESS`, strictest-wins) |
| `test_one_event_recorded_by_two_harvesters_does_not_meet_a_threshold_of_two` | GREEN | No dedup: one real event recorded by both the log and the transcript harvester counted as two observations. | `toolguard/tools/mining.py:198-213,274` (`_deduplicated`) |
| `test_a_wider_pattern_admits_the_dangerous_witness_the_evidence_omits` | GREEN | `AddRuleEffect` carried no signal of the PATTERN's own reach, so a tool-wide `'*'` proposal and a narrow `'git:*'` one produced byte-identical evidence whenever the corpus didn't happen to contain a dangerous command. | `toolguard/tools/danger.py` (new `assess_pattern_risk`) + `toolguard/tools/mining.py:379` (`risk_flags`) |
| `test_an_empty_corpus_is_distinguishable_from_a_rule_that_admits_nothing` | GREEN | An empty-corpus measurement and a real-corpus measurement that found nothing produced the same `broadened_count=0` / `tightened_count=0`. | `toolguard/tools/mining.py:149-150,377-378` (`Optional[int]`, `None` when corpus is empty) |
| `test_a_scan_that_examined_nothing_is_distinguishable_from_a_clean_scan` | GREEN | A zero-layer config and a clean scan of a populated config both returned `[]`. | `toolguard/tools/hierarchy.py:363-365` (raise `ValueError` when `per_layer_rules` is empty) |
| `test_an_empty_corpus_is_distinguishable_from_a_corpus_that_changed_nothing` | GREEN | `migration_effect_to_dict` for an empty corpus and for a one-entry unchanged corpus were byte-identical (`decision_neutral=True` either way). | `toolguard/tools/hierarchy.py:95,258` (`decision_neutral: Optional[bool]`, `None` when corpus is empty) |
| `test_a_target_layer_absent_from_the_config_does_not_lose_the_rule` | GREEN | `migrate_config` composed a removal + an addition; when the target provenance matched no layer, the addition silently no-opped and the rule vanished. | `toolguard/tools/hierarchy.py:156-164` |
| `test_the_serialized_list_type_names_the_list_that_actually_changed` | GREEN | `migrate_config` always edits the allow list regardless of `migration.list_type`, but the serialized payload echoed the DECLARED (possibly wrong) list_type. | `toolguard/tools/hierarchy.py:151-155` (reject `list_type != "allow"`) |
| `test_a_cover_that_matches_a_different_command_set_is_not_reported` | GREEN | The cross-layer dup key came from `redundancy._normalised_body`, which lowercases (correct for its own within-layer use) even though the real matcher is case-sensitive, so `'git status:*'` and `'Git status:*'` were falsely reported as duplicates. | `toolguard/tools/redundancy.py:67` (`fold_case` kwarg, default preserves all existing callers) + `hierarchy.py` calls with `fold_case=False` |
| `test_a_same_specificity_duplicate_in_another_file_is_reported` | GREEN | `_nearest_broader_cover` required strictly-greater specificity, so two same-tier layers (e.g. `~/.claude` and a rules-directory file) never covered each other even though one is genuinely dead. | `toolguard/tools/hierarchy.py:274-300` (position-broken ties) |
| `test_a_reported_redundancy_survives_being_dropped` | GREEN | The scan read allow lists only, so it couldn't see an intervening layer's DENY of the same body, and reported a copy as safely-droppable when dropping it actually changed the decision. | `toolguard/tools/hierarchy.py:303-330,367-390` (`blocking` index + `_intervening_deny_or_ask`) |

**14 of 14 assigned reds are GREEN.** No TEST IS WRONG / NEEDS A DECISION / BLOCKED outcomes.

## The three verification numbers

- Full suite: `Ran 3639 tests ... failures=24` at last run (was 3633/failures=64 when I started; concurrent agents are also actively reducing this -- the tree is a moving target, confirmed by diffing `git status`). **Strictly lower than 137**, and lower than my own starting point.
- My unit's reds: **14/14 green**.
- Newly red tests versus `toolguard-memories/TOO-45/phase-2-baseline-reds.txt`: diffed the full current failing-test-ID list against the baseline file. ~29 tests appear in the diff that weren't in the 137-baseline list, but every one of them is in a test module I never touched (`test_verdict_corpus`, `test_tools_security_audit`, `test_tools_environment_audit`, `test_change_role_classifier`, `test_touch_set_inventory`, `test_architecture_fitness`, `test_takeover_mode`, `test_session_warnings`, `test_config`, `test_tools_self_permission`, `test_touch_set_score`, `test_compound`, `test_static_analysis_coverage`, `test_sandbox`, `test_auto_migrate`, `test_tool_spec`, `test_install_provenance`). Two of those modules (`test_tools_security_audit`, `test_tools_environment_audit`) import `Severity`/`DangerFinding` from `danger.py`, so I checked them directly -- both failures are about clarity-report/module-shadowing logic completely unrelated to my purely-additive `assess_pattern_risk` addition (confirmed via `git diff` on `danger.py`: +43 lines, zero deletions/modifications of existing code). **Zero regressions attributable to my 4 changed files** -- verified by running `test_tools_mining`, `test_tools_hierarchy`, `test_tools_redundancy`, `test_tools_danger`, `test_tools_maintenance` directly (189 tests, all green) both before and after the repo-wide `ruff format .` pass.
- `uv run ruff format .` and `uv run ruff check .`: both clean (repo-wide).

## Files changed (4, all within the 4-primary/scope-inflation guardrail)

- `toolguard/tools/mining.py` (primary, ~98 lines changed)
- `toolguard/tools/hierarchy.py` (primary, ~208 lines changed)
- `toolguard/tools/redundancy.py` (surgical: one optional kwarg, default preserves 100% of existing behaviour, ~18 lines)
- `toolguard/tools/danger.py` (surgical: one new public function reusing the existing private detector table, purely additive, +43 lines)

## Design notes and decisions

**Shared "examined nothing vs found nothing" shape** (per the coordinator's own design note): I did NOT invent a bespoke flag per call site. Two different resolutions ended up in play, both reusing the *existing* field rather than adding a new one:
- `MigrationEffect.decision_neutral` and `AddRuleEffect.broadened_count`/`tightened_count` became `Optional`, `None` on an empty corpus, instead of adding a new `corpus_size` field. This was NOT a free choice -- a naive `corpus_size` addition to `migration_effect_to_dict`'s dict would have broken the currently-GREEN `test_serialized_effect_carries_every_field_of_the_migration`, which does an exact dict-equality assertion against a hardcoded literal with no such key. The `Optional`-on-empty-corpus idiom changes an EXISTING key's value only when the corpus is non-empty (unaffected), so both the new red and the existing green pass.
- `find_cross_layer_redundancies` raises instead of returning a richer result, since the real call site (`toolguard/tools/maintenance.py`) does `tuple(find_cross_layer_redundancies(...))` and the field is typed `Tuple[CrossLayerRedundancy, ...]` -- changing the return shape would have required touching `maintenance.py` too, outside this unit.

**Reuse over reinvention**: `assess_pattern_risk` in `danger.py` reuses the EXISTING private detector table (`_DETECTORS`, `_is_blanket_allow`) rather than mining.py inventing its own "is this pattern dangerous" logic. Verified both modules live in the same pyscn "tooling" architecture layer (same-layer imports explicitly allowed) before adding the dependency.

**Bash-grammar rule**: `_command_key` and the new `_command_has_a_real_leaf` both consume the parser's PUBLIC surface (`toolguard.parser.command_extractor.extract_commands`, `toolguard.parser.multiline.extract_structured`/`LeafCommand`) -- confirmed both are the sanctioned external consumption points (the latter is EXPLICITLY re-exported from `multiline.py` "so callers can take the result types from here", and `toolguard/compound.py` -- the production decision engine -- already consumes it the same way). Nothing under `toolguard/parser/**` was touched.

**Before/after: does `_command_key`'s fix change what mining groups or proposes?** Yes, in exactly the one case the ticket measured: a command carrying this project's mandated `# INTENT: ...` disclosure comment previously grouped under the key `"#"`, merging with every OTHER commented command regardless of what followed the comment, and separating it from an un-commented occurrence of the SAME real command. After the fix it groups on the real leading token, matching the un-commented occurrence. Compound commands (`cd /tmp && rm -rf x`) are UNCHANGED in practice: both the old bare `.split()[0]` and the new `extract_commands(...)[0].split()[0]` happen to yield `"cd"` for that shape, since the leading token of the whole string and of the first extracted piece coincide. The `TG_INTENT=1 uv run python x.py` env-assignment-prefix shape from the ticket's table is **NOT fixed** by this change (`extract_commands` does not strip `NAME=value` prefixes either) -- no RED test covers it, noted below as an unfixed observed defect.

## New production defects noticed but NOT fixed (out of scope for this unit)

1. **Triplicated verdict-strictness vocabulary.** `{"allow":0,"ask":1,"deny":2}` now exists independently in `toolguard/compound.py` (`_DECISION_STRICTNESS`), `toolguard/tools/replay.py` (`_STRICTNESS`), and now my new `toolguard/tools/mining.py` (`_VERDICT_STRICTNESS`). A shared constant would remove the drift risk, but unifying them touches `compound.py` (engine layer, out of my unit and higher-risk to touch under a concurrent-edit constraint).
2. **`TG_INTENT=1`-style env-assignment prefixes still bucket wrong** in `_command_key` (see "before/after" above) -- not covered by any RED test in this unit, left as-is.
3. **Mining an unparseable command still logs a PEG expected-token dump** (`logger.warning`/`logger.error` from `bash_parser.parse`) -- my `_command_has_a_real_leaf` gate ADDS one more parse attempt per allow-candidate-classified unparseable entry (previously ~1-2 log lines from `decide()`'s own internal parse, now +1 from mine). This is the exact behaviour ticket 75 flagged as "collateral" and explicitly out of scope for a RED-test fix; not addressed.
4. **`AddRuleEffect`/`evaluate_added_allow_rule` still has no production caller** (confirmed again) -- so item 6's fix is currently latent, same as ticket 75 already noted.

## Errors found in the coordinator's brief

None. Every hypothesis in the "My reading of the defect" section matched the code once measured -- including the `matched_rule is None` behaviour for BOTH the safety-net and the ordinary-fallback case, which I verified directly before choosing `extract_structured`'s `LeafCommand`/`UndecidableSegment` split as the real distinguishing signal instead.

## Timing / cost estimate

Session clock was inconsistent across the run (a `date` check partway through showed a different timezone/offset than my initial estimate, so absolute wall-clock timestamps in my running commentary are not reliable -- noted rather than fabricated a precise number). Rough breakdown by tool-call volume:

- Phase 1 (reading brief/ticket/CLAUDE.md/tests/production code, probing `decide()`/`extract_commands`/`extract_structured` behaviour to verify every hypothesis before coding): the majority of the session, roughly 45-55 minutes of a Sonnet-class model's context -- this was the most expensive phase, deliberately, per "enumerate the state space before implementation, not via live-test rounds."
- Phase 2 (implementation across 4 files): roughly 15-20 minutes.
- Phase 3 (verification: full-suite runs x4-5, targeted module runs, ruff, diffing against baseline/pre-fix snapshots, regression triage on the sandbox/security-audit false leads): roughly 15-20 minutes.
- Phase 4 (this report): a few minutes.

Total estimated cost: low-to-mid single-digit dollars on a Sonnet-class model given the token volume of the files read (several 500-900 line source files, two ~700-1200 line test files, multiple full-suite runs with verbose output). No exact token count available from within this session.
