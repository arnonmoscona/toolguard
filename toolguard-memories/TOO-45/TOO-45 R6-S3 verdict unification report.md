---
title: TOO-45 R6-S3 verdict unification report
type: note
permalink: toolguard/too-45/too-45-r6-s3-verdict-unification-report
tags:
- task-memory
- TOO-45
---

# TOO-45 R6-S3: unify `Decision` into `RuntimeVerdict`

Implemented on branch `too-45`, working tree `/home/arnon/projects/toolguard`. S0 (instrument fix) and S1 (private-reach cleanup) were already done by prior coder passes before this session started -- confirmed by reading `toolguard-memories/TOO-45/TOO-45 R6-S0 instrument fix report.md` / `TOO-45 R6-S1 private reaches report.md` and by `git status` showing those files already modified. This report covers S3 only.

## What was done

`toolguard.tools.decision.Decision` (the TOOLING altitude) is deleted. `toolguard.tools.decision.decide()` now returns `toolguard.config_types.RuntimeVerdict` directly -- the object the resolver (`toolguard.resolve.resolve_bash_permission_detailed` / `resolve_file_path_permission_detailed`) already builds, not a re-render of it. `hook.py`'s `_verdict_from_decision` adapter is deleted entirely; `_resolve_event` now returns `decide(...)`'s result unmodified. This was possible -- ceasing to exist, as the task asked, not just shrinking -- because the resolver's `RuntimeVerdict` already carries every field `_verdict_from_decision` used to copy.

### The one real behavioural nuance, preserved deliberately

`Decision.tool` used to carry the CALLER's own tool name (so an MCP terminal tool routed through the Bash rule set would be reported under its own name), while `resolve_bash_permission_detailed`'s own `RuntimeVerdict.tool` is hardcoded to the literal string `'Bash'` (documented, since the resolver always evaluates command tools against the Bash rule set regardless of the true invoking tool). `_decide_bash` in the new `decision.py` preserves the old contract with one line: `dataclasses.replace(result, tool=tool)` when the caller's `tool` differs from the resolver's `'Bash'`. Verified empirically that no current call site anywhere in the codebase (production or test) ever passes a non-`'Bash'` tool into this path -- `grep` of every `decide(...)` call site confirms `tool` is always the literal `'Bash'` in practice -- so this is a no-op today, but it keeps the documented contract exact rather than silently narrowing it. `_decide_file_path` needed no such override: `resolve_file_path_permission_detailed` already sets `tool=tool_name` (the caller's own argument) verbatim, so `decide()` now calls it and returns its result inline with no wrapper at all.

The second known pre-existing difference -- `Decision` normalised an empty `sub_matches` to `None`, `RuntimeVerdict` keeps `[]` -- was NOT preserved, deliberately: `sub_matches` is explicitly excluded from every golden schema (`fixture_loader.decision_to_golden`'s own docstring says so), no test asserted `None`-vs-`[]`, and preserving it would have meant keeping exactly the kind of re-render adapter this stage exists to delete.

### A genuinely new capability, not a verdict change

Because `decide()` now returns the resolver's own object rather than a hand-picked subset of its fields, `decide()`'s return value now carries a real `overrides` (`List[Tuple[Optional[str], ConflictOverride]]`) where `Decision` always silently dropped it. This does NOT touch "no verdict may change" -- `overrides` was never part of the golden schema and no test observed it -- but it does make a comment in `tools/corpus_build.py` (about `ConflictOverride` being unobservable via `decide()`) go from true to false, so I corrected it (see Doc-drift below) rather than leave a stale claim standing.

## Files changed (23 total; all backed up before editing)

Production (11): `toolguard/tools/decision.py` (full rewrite -- `Decision` deleted, `decide()` returns `RuntimeVerdict`), `toolguard/hook.py` (`_verdict_from_decision` deleted, `_resolve_event` simplified), `toolguard/tools/replay.py` (`EntryDiff.decision_a/b` and `SingleDecision.decision` retyped to `RuntimeVerdict`; `.verdict` -> `.decision`), `toolguard/config_types.py` (docstring only), `toolguard/testing/sandbox.py`, `toolguard/tools/consolidate.py`, `toolguard/tools/mining.py`, `toolguard/tools/self_permission.py`, `toolguard/tools/uninstall_readiness.py`, `toolguard/tools/maintenance.py`, `tools/architecture_fitness.py` (docstrings only -- classifier logic untouched).

Belatedly added to the backup/edit set after I initially missed it (see Process note below): `tools/corpus_build.py` (one docstring correction, no code change).

Tests/corpus infra (12): `test/verdict_corpus/fixture_loader.py` (import + docstrings + `decision_to_golden`'s type hint and `.verdict` -> `.decision`; golden schema keys unchanged), `test/unit/test_architecture_fitness.py` (2 real-tree assertions + docstrings updated to the new reality), `test/unit/test_tools_decision.py` (full mechanical pass + 1 test deleted, see below), `test/unit/test_ask_resolution.py`, `test/unit/test_hook_eval.py`, `test/unit/test_resolve.py`, `test/unit/test_sandbox.py`, `test/unit/test_self_integrity.py`, `test/unit/test_symlink_hierarchy.py`, `test/unit/test_tools_consolidate.py`, `test/unit/test_tools_installer.py`, `test/unit/test_tools_replay.py` -- all purely `.verdict` -> `.decision` (each verified single-purpose before a bulk edit).

`toolguard.tools.decision_ledger.LedgerDecision` needed **zero changes** -- verified it has no relationship to `Decision`/`RuntimeVerdict` at all (its own `decision` field means "accept/reject/defer" on a maintenance-ledger entry; it doesn't import from `tools.decision`). Confirms the task's framing that it was never a verdict altitude.

## Test deleted (the hard rule's one exception)

`test/unit/test_tools_decision.py::test_positional_construction_of_decision_still_works` -- deleted. It pinned `Decision`'s own positional field order (`tool, target, verdict, reason, provenance, sub_matches`), specifically proving a PRIOR field addition (`additional_context`) had been appended last so it never broke a positional caller. `Decision` no longer exists, so there is nothing left to pin. Left an in-file comment explaining this and stating explicitly that no replacement was manufactured for `RuntimeVerdict` (its field order wasn't touched by this stage and had no equivalent test before or after). Net: 2402 baseline tests -> 2401, exactly one fewer, matching exactly one deletion.

No other existing test was modified in a way that weakens an assertion -- every other change is a mechanical `.verdict` -> `.decision` rename or a `Decision` -> `RuntimeVerdict` type-reference update, verified one file at a time before batch-editing, with the two real-tree architecture-fitness assertions rewritten to assert the new (stronger, not weaker) reality: TOOLING bucket empty, `UnitVerdict` nested in `RuntimeVerdict` only.

## Doc-drift swept

Beyond the files above: `tools/architecture_fitness.py` had ~5 docstring locations asserting present-tense facts about `Decision` that would become false the moment it was deleted (`_VERDICT_DECISION_FIELD_NAMES`'s rationale, `find_verdict_types`' "THREE genuine hits" claim, `_is_provenance_capable`'s example list, `classify_verdict_altitudes`' TOOLING-bucket bullet, its UNIT-nesting example) -- all updated to explain the historical reason `Decision` doesn't exist anymore rather than silently deleting the explanation. Grepped `docs/`, `README.md`, `AGENTS.md`, `llms.txt`, `technical-notes.md`, `CLAUDE.md` for `tools.decision.Decision` -- zero hits, no doc-site drift. Grepped the whole repo at the end for `Decision(` (construction), `import Decision`, and `.verdict` -- zero remaining hits outside historical basic-memory reports (correctly left as point-in-time snapshots) and my own new historical comments.

## Design check: separation of concerns / SRP, on call intent not just data shape

Explicitly asked for, run before declaring this done rather than after: **is there a genuine reason the analysis/replay path needs its own verdict representation, or was `Decision` only ever a copy that drifted?**

Verdict: it was a copy. Two tests, both negative for "genuine separate concern":

1. **Data shape.** 7 of `Decision`'s 8 fields were verbatim identical names on `RuntimeVerdict`; the 8th was a pure rename (`verdict`/`decision`). The two fields `RuntimeVerdict` had that `Decision` didn't (`overrides`, `fallback_warning`) weren't omitted because tooling structurally can't use them -- `tools/corpus_build.py`'s own comment shows tooling code WANTING to observe `ConflictOverride` and being unable to, purely because the adapter dropped it. That's evidence of an accidental limitation, not a designed boundary.
2. **Call intent.** Every call site asks the identical question -- "what would toolguard decide for this tool+target under this config?" -- whether the asker is the live hook, `--eval`, the replay harness, or `toolguard.testing.sandbox`. Contrast with the genuine LEVEL/UNIT/RUNTIME split, which really does carry different information at different pipeline stages (a `LevelMatch` has no provenance yet; a `UnitVerdict` is one leaf of many; only the full `RuntimeVerdict` is the final compound answer). TOOLING was never "one leaf" or "before provenance exists" -- it was the exact same final answer, fetched through a different call path, spelled with a different field name for tooling-ergonomics reasons that never rose to a genuine information difference.

The pre-unification shape was the textbook SRP violation: the "what does a verdict consist of" concern had TWO places that had to change in lockstep (edit `RuntimeVerdict`'s fields, remember to also edit `Decision`'s field mapping in two adapter functions) for one reason to change. That is exactly what the canary-automode-experiment measured directly: `_verdict_from_decision` had to learn about `auto_mode_override` for no reason intrinsic to that feature. Measured zero behavioural cost of unification corroborates the call-intent argument -- nothing about "how tooling uses the verdict" required a narrower shape.

I did not find a case for keeping `Decision` separate. If Arnon disagrees with this conclusion I'd want to hear the specific tooling-ergonomics argument for the `verdict`-vs-`decision` field-name choice, since that's the only thing that was ever genuinely different, and it's a naming preference, not an information difference.

## `hook.py`'s `_verdict_from_decision` -- ceased to exist, as required

Fully deleted, not merely shrunk. `_resolve_event` returns `decide(config, tool_name, target, extended_syntax)`'s result directly. Left a short historical comment at the deletion site rather than none, per the doc-drift discipline.

## `LedgerDecision` / `SingleDecision` -- left alone, as instructed

`decision_ledger.py`: zero changes, verified unrelated (see above).
`tools/replay.py`'s `SingleDecision`: the class itself, its own `decision` field NAME, and its role as a replay row pairing a verdict with an observed historical outcome are all untouched. Only its field's TYPE ANNOTATION changed (`Decision` -> `RuntimeVerdict`, since that's simply what the type now is) -- this is not letting the unification "leak into the file format": `SingleDecision`/`EntryDiff` are in-memory dataclasses, never serialized, so there is no persisted schema to protect here in the first place (unlike `LedgerDecision`, which genuinely is a persisted JSON schema and which I verified is untouched by anything in this stage).

## `tools/architecture_fitness.py`'s TOOLING altitude bucket

Now legitimately empty on the real tree, confirmed by direct execution (`af.classify_verdict_altitudes()['tooling'] == []`, `runtime == ['RuntimeVerdict']`, `unit == ['UnitVerdict']` nested only in `RuntimeVerdict.sub_matches`). Classifier logic (`_VERDICT_DECISION_FIELD_NAMES`, `_scan_decision_classes`, `classify_verdict_altitudes`, `R1_TOOLING_PACKAGES`) is **completely untouched** -- I edited only docstrings. The synthetic test `test_class_under_tooling_package_is_tooling_not_runtime` (a tempdir fixture, not the real tree) still passes unmodified and proves the rule still fires on a tooling-package verdict class if one is ever reintroduced -- this is the concrete evidence backing "did not weaken the classifier."

## Acceptance criteria -- real output

```
$ uv run python -m unittest discover -s test -t .
Ran 2401 tests in 35.235s
OK
```
(2402 baseline - 1 deliberate deletion, explained above.)

```
$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 9.07s. End-to-end: 61 cases in 3.36s.
OK: no differences.
```

```
$ uv run python tools/architecture_fitness.py --predicates
=== R1: PASS ===
=== R2: PASS ===
=== R3: PASS ===
=== R5: PASS ===
=== R6: PASS ===
```

```
$ uv run python tools/architecture_fitness.py --layers
=== --layers: completeness ===
All modules map to exactly one layer.

=== --layers: direction ===
VIOLATIONS (1):
  - hook (runtime) -> tools.decision (tooling) at line 667 [local import]
```
Exactly the expected S2-territory violation, unchanged in kind (only the line number moved, since code above it shrank).

```
$ uv run ruff format . && uv run ruff check --no-cache .
150 files left unchanged
All checks passed!
```
(Ruff format DID reformat `test/unit/test_sandbox.py` once, mid-session, wrapping 2 lines that got one character longer from `.verdict`->`.decision`; re-ran the full suite + corpus afterward to confirm still green.)

## `toolguard --eval` smoke test -- how

Built a throwaway project directory outside the repo (`/tmp/.../scratchpad/eval-smoke`, with a `.git` marker and a `.claude/toolguard_hook.toml` allowing `Bash(ls *)` and denying `Bash(rm -rf *)`), then piped a hook event through `python -m toolguard.hook --eval` with `PYTHONPATH` pointed at the working tree:

```
$ printf '{"tool_name":"Bash","tool_input":{"command":"ls -la"},"hook_event_name":"PreToolUse"}' | \
    PYTHONPATH=... python -m toolguard.hook --eval
{"hookSpecificOutput": {..., "permissionDecision": "allow", ...}}

$ printf '{"tool_name":"Bash","tool_input":{"command":"rm -rf /"},...}' | ... --eval
{"hookSpecificOutput": {..., "permissionDecision": "deny", ...}}
```

Also ran the SAME two events through the live (non-`--eval`) hook path for comparison -- identical verdicts. This exercises exactly the path `Decision` used to serve: `_resolve_event` -> `decide()` -> (now) `RuntimeVerdict` -> `create_hook_output()`. Scratch directory deleted afterward.

## Process note: one file initially missed, corrected before finishing

The task named `tools/corpus_build.py` as a known consumer to verify. I identified during planning that it needed only a docstring fix (no code path through `decide()`/`Decision`), drafted the fix, but did not actually apply it in my first edit pass -- caught this during the final repo-wide grep sweep, before writing this report. Backed it up (checksum recorded) and applied the fix late, then re-ran the full acceptance block afterward to confirm nothing regressed. Flagging this explicitly per the "no verdict may change" discipline: better to say "I found and fixed my own miss" than to let it go unmentioned.

## Scope-inflation flag

23 files touched, all non-trivially. This explicitly exceeds my own default guard (5 non-trivial existing-file edits / 10 total). I did not stop and ask, because this exact scope was pre-measured and pre-authorized by the task itself ("Measured cost: behavioural 0, mechanical 198... Treat 198 as a cost estimate, not an objection") and by the R6 reassessment's own blast-radius accounting. Flagging it here per my own operating instructions rather than silently proceeding past the guard.

## Backups

All 24 touched files (23 planned + the belated `tools/corpus_build.py`) were copied to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r6-s3-backups/` with a `SHA256SUMS.txt` manifest, all before their first edit (with the one documented exception above, backed up before its edit was applied, just later than planned). Diffed every backup against the current file at the end to confirm the touched-file list matches exactly what was intended -- no incidental edits outside the 24.

## Elapsed time / cost

I do not have a reliable wall-clock start timestamp for this session (the environment's date rolled over mid-session and I didn't capture a trustworthy anchor at launch), so I won't fabricate a precise figure. This was a long, single continuous session covering: reading four background reports in full, auditing every production and test consumer of `Decision`/`.verdict` across the repo (~24 files, ~250 mechanical sites), a full rewrite of `tools/decision.py`, careful hand-editing of `hook.py`/`replay.py`/`fixture_loader.py`/`config_types.py`/`architecture_fitness.py` (docstrings + one deleted test with justification), batch mechanical edits to 8 further test files, three full-suite test runs, two corpus verifications, an `--eval` smoke test, and a doc-drift sweep. Order of magnitude: a long session on a mid-tier model, most of the token cost in the initial reading/planning phase (four large background documents) and the file-by-file verification passes (many `grep`/`Read` calls to establish exact context before each edit, deliberately favoring precision over speed given the "no verdict may change" bar). I would not stand behind a dollar figure more precise than "likely comparable in order of magnitude to the other TOO-45 R6 report/coder passes described in the background documents I read (tens of dollars, not single digits)."