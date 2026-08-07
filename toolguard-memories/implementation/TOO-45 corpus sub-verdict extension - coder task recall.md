---
title: TOO-45 corpus sub-verdict extension - coder task recall
type: note
permalink: toolguard/implementation/too-45-corpus-sub-verdict-extension-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

# Task

Close a gap in the TOO-45 golden verdict corpus (`test/verdict_corpus/`): it does not capture the compound sub-command breakdown (`RuntimeVerdict.sub_matches` / `overrides`), which is exactly the structural data whose loss was the ticket's headline defect (813/975 compound-allow decisions under-logged, 1,943 sub-commands with no audit entry — fixed in `hook.py::_log_allowed_command`, which now iterates `verdict.sub_matches` directly instead of regex-parsing reason prose). Nothing currently guards against a future regression reintroducing that loss.

Full instructions from the launching agent (verbatim intent, condensed): extend `decision_to_golden` in `test/verdict_corpus/fixture_loader.py` to capture, per `UnitVerdict` in `decision.sub_matches`: sub_command text, decision, matched_rule, provenance — plus `overrides` if present. Decide + document empty-vs-omitted representation for non-compound cases. Regenerate goldens, report how many cases carry a non-empty breakdown (investigate if surprisingly low). PROVE regression detection: deliberately break sub-verdict recording, run `--verify`, confirm FAIL naming affected cases, revert, confirm PASS again. Handle the e2e corpus (61 cases) consistently or explain explicitly why not / what's left unguarded. No production behaviour change. Full suite green (2,586 baseline). `tools/architecture_fitness.py --layers`/`--predicates` clean. Report to `toolguard-memories/TOO-45/reports/corpus-sub-verdict-extension.md` with the given frontmatter.

# Design decided

- Golden keys use RuntimeVerdict's own attribute names for consistency: `sub_matches` (list of dicts: `sub_command`, `decision`, `matched_rule`, `provenance` — sanitized/provenance_to_dict'd, deliberately NOT `reason`/`additional_context`/`fallback_kind` per the launcher's exact 4-field spec) and `overrides` (list of dicts: `identifier`, `winning_pattern`, `winning_provenance`, `overridden_pattern`, `overridden_provenance`).
- Always emit both keys as a list (never omitted), empty `[]` when there's nothing (file-path tool cases structurally never populate `sub_matches`/have 0 overrides in the vast majority of cases) — additive to the existing schema, byte-identical shape otherwise.
- Treat both new fields as a NEW HARD comparison tier (not the existing TRACKED tier), because the whole point is structural-loss detection, and existing TRACKED fields are for legitimate-reword tolerance. New `CompoundBreakdownMismatch` dataclass + `ComparisonResult.breakdown_mismatches`, included in `has_hard_failures`. This makes plain `--verify` (no `--strict-prose` needed) fail on a regression.
- e2e corpus: hook's real JSON output never carries `sub_matches`/`overrides` at all (only `permissionDecision`/`permissionDecisionReason`/`additionalContext`), so there is nothing to extend there without adding NEW instrumentation (decision-log-stream snapshotting, parallel to the existing `conflict` stream mechanism but for the main dated log). Decided NOT to add that (real scope growth, and the task gives an explicit escape hatch to document instead). Document explicitly: what's covered (decide()-level `sub_matches` construction correctness, via the in-process corpus) vs NOT covered (whether `hook.py::_log_allowed_command`'s write-loop over `verdict.sub_matches` correctly emits one entry per unit without skipping any — the literal historical seam). That gap is real and must be stated prominently in the report and README.
- Mutation test target: `toolguard/resolve.py::resolve_bash_permission_detailed`'s inner `_resolve_one` — temporarily skip appending to `sub_matches` on every second call (a counter), leaving the actual `decision`/`reason`/`additional_context` return values (and therefore top-level `verdict`) unaffected by construction, isolating the proof to the new sub_matches/overrides check (though `matched_rule`/`provenance` top-level TRACKED fields may also shift since `_deciding_sub_match` reads the now-shorter list — expected and will be reported, not hidden).

# Files expected to touch

- `test/verdict_corpus/fixture_loader.py` (decision_to_golden, new helpers, ComparisonResult, compare_goldens)
- `tools/corpus_build.py` (_print_comparison, docstring)
- `test/unit/test_verdict_corpus.py` (new test method)
- `test/verdict_corpus/README.md` (schema + rationale + e2e gap documentation)
- `test/verdict_corpus/goldens.jsonl` (regenerated, data only)
- Report at `toolguard-memories/TOO-45/reports/corpus-sub-verdict-extension.md`

No production code change planned except the TEMPORARY mutation-test edit to `toolguard/resolve.py`, which must be reverted before finishing, verified back to original via `git diff --stat` showing no changes to that file.