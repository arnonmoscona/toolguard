---
title: TOO-45 corpus strengthening - coder task recall
type: note
permalink: toolguard/too-45/too-45-corpus-strengthening-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task (verbatim intent, condensed)

Branch `too-45`, repo `/home/arnon/projects/toolguard`, clean at commit `d4123f4`. This is
corpus-strengthening work only -- **production code under `toolguard/` must not change** (mutations
during verification must be reverted; `git diff toolguard/` must be empty at the end).

An executed trace over the verdict corpus found `config.py`'s no-match fallback tail
(39/~118 executable lines of the next refactor step) is barely covered outside the dominant
`allow` branch. Need to strengthen `test/verdict_corpus/` so each of 7 points is exercised by
>= 25 distinct cases (except point 7 which just needs "real breadth", and the zero-hit defensive
lines which should be reached only if possible via the public surface -- otherwise documented as
unreachable, not faked):

1. `no_match_fallback = "ask"` -- >=25 distinct cases
2. `no_match_fallback = "allow_with_warning"` -- >=25 distinct cases, must include fallback-warning
   routing
3. `no_match_fallback = "deny"` -- >=25 distinct cases
4. unconfigured-tool branch (`not has_any_rules`) -- >=25 distinct cases, tool with NO rules at
   any level
5. parse-failure ASK floor firing -- >=25 distinct cases
6. `ask`-rule provenance across >1 hierarchy level, so `_provenance_for_pattern` /
   `_entry_for_pattern` take the `ask` branch -- >=25 distinct cases
7. `_detect_override` producing an actual override (more-specific allow overriding less-specific
   deny) -- currently 6/3308. Give real breadth: different tools, compound/single commands,
   different level distances.

Also: try to reach 3 zero-hit defensive lines via public surface only (config in, verdict out):
- `config.py` `_entry_for_pattern`: `if len(entries) != len(candidates): return None` (parallel
  array drift guard)
- `config.py` `_entry_for_pattern`: `return None` fallthrough when matched pattern in no layer
- `config.py` `_provenance_for_pattern`: same fallthrough
If unreachable without reaching into internals -- **say so, leave it, do not fabricate**.

### Acceptance criterion (the real gate)

For EACH of the 7 points: mutate the corresponding branch in `toolguard/`, run
`uv run python -m unittest test.unit.test_verdict_corpus`, confirm FAIL, revert, confirm green.
Verify `git diff` empty for `toolguard/` after each revert and at the end. Report actual counts
are NOT evidence by themselves -- the mutation-catch is the evidence.

### Constraints

- May add/extend fixtures under `test/verdict_corpus/configs/`, add cases, regenerate goldens via
  `tools/corpus_build.py`, add tests. Existing goldens for pre-existing cases must not change --
  run `tools/corpus_build.py --verify` before starting and confirm identical afterwards for
  pre-existing cases. If any pre-existing golden changes: STOP and report.
- Keep total corpus runtime sane (~8s baseline for in-process cases; ~10-11s with e2e). Report if
  approaching ~20s.
- Sanitize machine-specific paths (`/home/arnon` -> `/home/tguser`) -- corpus already does this via
  fixture_loader placeholders.
- `uv run python`, never bare python. unittest not pytest. Stdlib only. No async/threading/local
  imports. ruff format/check clean. No git write ops (commits are Arnon's).
- If scratch copy of repo needed, exclude `.git`/`.venv`, delete when done.

### Report

Write implementation report to basic-memory TOO-45/, tagged task-memory + TOO-45, including:
7 mutation results (fail-then-green pairs), new case count, new runtime, anything unreachable and
why.

## Context already gathered

- RESUME HERE memory says CP1 (this corpus + architecture_fitness.py) is already PASSED and
  committed (commit d5bdab3), R3 done (commit d4123f4 = "D4: one undecidable floor, not two").
  Current HEAD is d4123f4, tree clean except unrelated toolguard-memories/CLAUDE.md/uv.lock dirt
  from prior sessions -- NOT part of my task, leave alone.
- Existing corpus: cases.jsonl/goldens.jsonl = 5389 lines each (in-process), e2e_cases/goldens =
  30 lines each. 14 synthetic fixtures under configs/ (11 single-file TOML + realistic,
  parse_failure, hierarchy_conflict directory fixtures) plus real-traffic `realistic` (~5090
  cases dominate, all allow_with_no_warnings).
- Existing fixtures already named suggestively for several of my targets:
  fallback_ask.toml, fallback_allow_warning.toml, fallback_deny.toml, fallback_allow_silent.toml,
  undecidable_allow/ask/deny.toml, parse_failure/, hierarchy_conflict/. Need to check each one's
  current per-fixture case count (report said 15 each for fallback_*/undecidable_* originally,
  but numbers may have grown with R3 commit -- suite now 2321 vs 2189/2192).
- Tooling: `tools/corpus_build.py --extract/--generate/--verify`, shared `fixture_loader.py`.
- Baseline expectation before I touch anything: `tools/corpus_build.py --verify` clean,
  `uv run python -m unittest discover -s test -t .` green (last known count ~2321, need to
  re-verify), `tools/architecture_fitness.py --guard` PASS 12 canaries (not my concern unless it
  breaks).

## Plan (to be refined after reading config.py fallback/override code + corpus_build.py)

1. Read toolguard/config.py fallback dispatch, _detect_override, _entry_for_pattern,
   _provenance_for_pattern, hook.py's unconfigured-tool / parse-failure paths.
2. Read tools/corpus_build.py + fixture_loader.py + existing fixture TOMLs for the 7 target areas
   to understand current per-branch case counts precisely (not guess from the old report).
3. Establish per-branch baseline case counts (need a way to count e.g. how many cases currently
   hit no_match_fallback=ask etc -- likely by grep across configs + goldens, or by re-running the
   trace tool if available).
4. Design additions: extend existing fixtures (vary commands/paths) rather than always creating
   new ones, add new fixtures only where a genuinely new config shape is needed (e.g. override
   fixture needs allow-over-deny hierarchy at multiple level distances; ask-provenance needs
   multi-level ask rules).
5. Regenerate goldens, verify pre-existing cases unchanged, run full suite.
6. Do the 7 mutations one at a time (find exact line/branch in config.py per RESUME HERE + my own
   reading), confirm fail then revert then green, verify git diff toolguard/ empty each time.
7. Ruff format/check. Write report. No commits (Arnon does that).
