---
title: TOO-45 D1a debts coder task recall
type: note
permalink: toolguard/too-45/too-45-d1a-debts-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Source

Full brief: `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/d1a_debts_brief.md` (copied in full below the plan). Branch `too-45`, repo `/home/arnon/projects/toolguard`. `toolguard/permission_resolution.py` is already staged (new file, D1a) -- do not unstage it. Everything else in the tree is unstaged D1a work already present; I must not commit.

## The ten items

A. Pin deny-under-broken-config: a deleted `or resolved.decision == "deny"` guard in `_apply_ask_floor` (permission_resolution.py:160) is caught by nothing. Write a test in the new test module asserting provenance + additional_context + matched_rule ALL survive a deny under parse_failures. Demonstrate fail/pass.
B. Add `toolguard.permission_resolution` to `test/unit/test_architecture.py`'s `LAYERS` tuple (allowed={"toolguard.config_types"}) so `test_leaf_modules_do_not_import_config` covers it. Demonstrate fail/pass by adding a forbidden import temporarily.
C. Strengthen `test/unit/test_architecture_fitness.py:1813 test_check_layers_runs_on_real_tree` to assert `report.unmapped == []`. Do NOT assert `report.ok` (3 pre-existing direction violations out of scope). Demonstrate fail/pass by removing permission_resolution from .pyscn.toml's engine layer packages list temporarily.
D. docs/architecture.md package inventory: fix stale `config.py` line, add `permission_resolution.py` entry. Check rest of doc for other D1a-falsified statements. technical-notes.md already fixed -- use as tone/wording reference.
E. Widen corpus tracked fields to observe `matched_rule` and the overridden deny's provenance. Plan: add `matched_rule` field to `Decision` (tools/decision.py), wire from `result.matched_rule` in both `_decide_bash`/`_decide_file_path`; add to `decision_to_golden` + `TRACKED_FIELDS` in fixture_loader.py. For overridden provenance: only observable via e2e conflict-log side effect (per fixture_loader's own docs) -- widen `generate_e2e_goldens_in_memory` to capture actual NEW conflict-log text (not just a header count) as a new `conflict_message` field, sanitized, tracked (like additionalContext text) only when both sides logged a conflict. Regenerate corpus after. `--verify` must show zero diff after regen; before regen it's expected to show diffs (per brief).
F. Add 2 sentences to `apply_parse_failure_floor`'s docstring: caller must pass real `parse_failures`, never `()` or a filtered subset. Do not change signature.
G. New file `test/unit/test_permission_resolution.py` hosting item A + B's new tests. Do not relocate existing ~28 cascade call sites elsewhere.
H. Cut permission_resolution.py docstrings: currently 202/370 lines (55%) per AST measurement -- verify and record before/after. Keep: HARD INVARIANT block, TOO-15 unconfigured-vs-no-match distinction, item-A comment. Cut restatement/Args/Returns duplication/history narration.
I. Fix module docstring's "six members" claim -- true only for this module's own duck-typed surface, not for a double driven through resolve.py (needs resolve_config_path + resolved_undecidable_fallback too). Say precisely which claim it is.
J. Fix `find_enrichment_footprint` in tools/architecture_fitness.py: tokenize-based, NAME tokens = real coupling, STRING/COMMENT tokens = prose-only. Report both counts separately, don't drop prose count. Add unit test with synthetic docstring-only file. Report corrected count for current tree, no tuning to hit a target.

## Hard operating rules

1. NEVER git checkout/restore/stash/reset or any git write -- denied by permission rule, hangs forever. Backups go to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/debts-backups/`, restore by copy-back + sha256sum verify. Read-only git fine.
2. Do not commit.
3. Do not copy the repo (previous incident filled disk). Work in place.
4. `uv run python`, unittest not pytest.
5. No local imports, no async, no threading.
6. Every test: Given/When/Then docstring, synced with behavior.
7. Don't edit outside the repo.

## Acceptance commands (paste real output)

```
uv run python -m unittest discover -s test -t .
uv run python tools/corpus_build.py --verify
uv run python tools/architecture_fitness.py --guard
uv run python tools/architecture_fitness.py --layers
uv run python tools/architecture_fitness.py --predicates
uv run ruff format . && uv run ruff check .
uv run python tools/check_doc_links.py   # if it exists
```
Items A, B, C need fail-then-pass demonstrations pasted verbatim.

## Report destination

basic-memory `toolguard`, `TOO-45/TOO-45 D1a debts implementation report.md`, tags `task-memory`, `TOO-45`. Must include: acceptance output verbatim, before/after docstring-line count (H), corrected footprint numbers (J), fail/pass demonstrations (A, B, C). No hard-wrapped paragraphs.

## Key file locations discovered during investigation

- `toolguard/permission_resolution.py` -- `_apply_ask_floor` L127-165, `apply_parse_failure_floor` L84-124, module docstring L1-25 ("six-member surface" claim at L20).
- `test/unit/test_configuration.py:3314` `TestParseFailureAskFloor` -- existing pattern for hand-built `Configuration(layers=(layer,), parse_failures=(...))` with zero file I/O, no ConfigIsolationMixin needed. Use as template for item A/G's new test module.
- `test/unit/test_architecture.py` `LAYERS` tuple L36-49.
- `.pyscn.toml` engine layer packages L173-175 -- already includes `permission_resolution` in the current unstaged working tree (D1a already fixed this; item C is about ratcheting the TEST, not the toml).
- `tools/architecture_fitness.py` `check_layers`/`LayerReport` L381-460ish; `find_enrichment_footprint` L1064-1077, `compute_predicates` L1085-1156, `render_predicates_text` L1159-1223.
- `test/unit/test_architecture_fitness.py:1805` `TestSmokeAgainstRealTree`, `:1813 test_check_layers_runs_on_real_tree`, `:1160 TestFindEnrichmentFootprint` (existing tests reference OLD List[str] return shape -- will need updating to match item J's new structured return, which is an explicitly authorized behavior change per the brief, not a weakening).
- `toolguard/tools/decision.py` `Decision` dataclass L45-87 (no matched_rule field yet), `_decide_bash` L141-208, `_decide_file_path` L211-252.
- `toolguard/resolve.py` `BashResolution.matched_rule` L166, `FileResolution.matched_rule` L238 -- already populated, just not threaded into `Decision`.
- `test/verdict_corpus/fixture_loader.py` `TRACKED_FIELDS` L660, `decision_to_golden` L339-368, `e2e_decision_to_golden` L508-571, `generate_e2e_goldens_in_memory` L574-621, `_count_stream_log_entries` L457-485 (presence-only; needs widening to capture actual new conflict-log text for item E's second field), `compare_e2e_goldens` L842-941.
- `toolguard/hook.py` `_format_conflict_message` L260-289 -- embeds `overridden_provenance.describe_brief()` in the conflict-log message text.
- `docs/architecture.md` package inventory L26-92, config.py line at L37.
- `test/verdict_corpus/README.md` schema docs at L51-53, 76-83, 199-201, 210-211 -- need matched_rule / conflict_message additions.
