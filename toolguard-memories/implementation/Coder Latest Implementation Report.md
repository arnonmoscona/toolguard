---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-28
- implementation-report
---


# TOO-28 Phase 4b+4c: the input-source constraint

Brief: `toolguard-memories/TOO-28/brief-phase4bc.md`, validated `all 5 slots present and filled`.

## Step 1: the resolution rule, and what was wrong in the coordinator's version

**Implemented rule** (`_input_source_for_executor` in `command_extractor.py`), walking tokens after the executor:

1. A token starting with `<` (not `<<`, which is a heredoc marker already lifted upstream) -> **file**. Checked FIRST, ahead of everything else.
2. A token not starting with `-` (or exactly `-`) -> the bare-positional case: **not_file** if `spec.bare_program` (awk: the positional IS the program), else **file** (`python script.py`). `-` alone -> **not_file** (stdin).
3. A long flag (`--eval`, `--eval=x`) in `inline_long` -> **not_file**.
4. A bundled short-flag token: an `inline_letters` hit -> **not_file**; a `program_file_letters`/`value_letters` hit steps over its value (shared with `_scan_for_inline_code` via the new `_classify_flag_token` helper) and, for `program_file_letters`, returns **file** immediately.
5. No positional reached at all -> **not_file** (REPL/stdin).

**Two things were wrong in the coordinator's reading, both found by tracing, not assumed:**

- **The bash-family coverage gap was real and would have shipped a live bug.** Falling to `_DEFAULT_EXECUTOR_FLAGS` (`inline_letters="cer"`) would classify `bash -e script.sh` as inline, because `-e` is bash's real exit-on-error flag, not an inline-code flag. Fixed with a dedicated `_BASH_FAMILY_FLAGS = _ExecutorFlags(inline_letters=frozenset("c"))`.
- **The redirect case needed explicit priority over `bare_program`, not just "detection."** `awk < script.awk` would otherwise hit the bare-positional branch and, since `<` doesn't start with `-`, be misread by awk's `bare_program` rule as inline program text. The redirect check runs first.

Everything else in the coordinator's reading (inline flag -> not_file, `program_file_letters` -> file, `bare_program`+positional -> not_file, otherwise positional -> file, no positional/`-` -> not_file) was confirmed correct.

## The five unverified claims -- all checked

1. **`value_letters` interaction** -- real, and correctly handled. `python -X foo script.py` classifies as `file` (steps over `foo`); `python -X foo -c "..."` classifies as `not_file` (still finds `-c` after stepping over `-X`'s value). Both are pinned as tests (`test_python_value_letters_flag_is_stepped_over_before_the_positional`, and the not_file mirror).
2. **No new `_ExecutorFlags` field needed for python/node/perl/ruby/Rscript** -- confirmed. Their existing `bare_program=False` default already triggers the correct "reached a positional -> file" branch with zero changes to those five spec objects. The only new spec is `_BASH_FAMILY_FLAGS`, and that's a coverage gap (bash-family had NO entry before), not new field plumbing.
3. **`bare_program` means "the first positional is program TEXT"** -- confirmed correct via `_AWK_FLAGS`/`_scan_for_inline_code` tracing.
4. **Redirect-from-a-file IS detectable at this layer** -- confirmed empirically: `extract_commands()` preserves `<`/redirect syntax verbatim in leaf text. No grammar change needed; this is pure post-parse token interpretation, as scoped.
5. **"Rule does not apply, continue as though unmatched" is the right semantics, and is consistent with existing behaviour** -- confirmed. The existing no-match branch is `if result is None: continue`; the guard failure is implemented as the same `continue`, at level granularity (see Judgements below).

## What was implemented

- `toolguard/constants.py`: `INPUT_SOURCE_FILE = "file"`, `INPUT_SOURCE_NOT_FILE = "not_file"`.
- `toolguard/parser/command_extractor.py`:
  - `_BASH_FAMILY_FLAGS`, and five new `_EXECUTOR_FLAGS` entries (bash/sh/dash/ksh/zsh).
  - `_executor_index` gained `include_bash_family: bool = False` (default preserves `_detect_foreign_inline_code`'s existing behaviour exactly).
  - `_classify_flag_token` extracted from `_scan_for_inline_code`'s inner loop (proven behaviour-identical by full-suite green at the same 4085-test baseline before any new tests were added).
  - New `_input_source_for_executor` and public `classify_input_source(cmd_text: str) -> str`.
- `toolguard/rule_entry.py`: `INPUT_SOURCE_KEY`, `_VALID_INPUT_SOURCE_VALUES`, `RuleEntry.input_source` property, `_input_source_issues` validator, wired into `normalize_entry` and `KNOWN_ENRICHMENT_KEYS` -- exact mirror of `auto_mode_behavior`'s Phase 3 shape.
- `toolguard/resolve.py`: `_decide` now computes `classify_input_source(sub_command)` and passes it as `resolve_command_permission(..., input_source=...)`.
- `toolguard/permission_resolution.py`: `command_input_source` threaded through `_resolve_unclamped` -> `resolve_permission_cascade` -> `resolve_command_permission` (NOT `resolve_file_path_permission`). Guard applied right after `winning_entry` is resolved: a mismatch `continue`s the outer level loop.
- Docs: `docs/configuration.md` new "## Input-source constraint" section (after "Per-rule auto-mode behavior", matching Phase 2/3 placement) plus ToC entry; `docs/agent-map.md` Q&A entry and index entry. `install.md` and bundled skills untouched (TOO-77).

## Judgements I acted on that the brief did not specify

**Level-granularity guard failure, not full per-pattern retry.** `permissions.py`'s `match_command`/`decide_command_at_level_detailed` operate on plain `List[str]` pattern text with no `RuleEntry` association -- there is no cheap way to say "skip this one pattern, try the next in the same list" without restructuring those matching primitives, which is a materially bigger change than this phase authorizes. Implemented instead: a failed guard treats the WHOLE LEVEL as unmatched, falling through the cascade to the next, less-specific level -- structurally identical to the existing `if result is None: continue` branch. Documented in both the code (`_resolve_unclamped`'s docstring) and here. This is the brief's own claim 5, resolved by choosing the option consistent with existing behaviour over one that would need new machinery.

**`input_source` scoped to Bash/MCP-terminal resolution only; `resolve_file_path_permission` never receives it.** A rule mistakenly carrying `input_source` on a file-path list is therefore inert rather than an error -- consistent with how `auto_mode_behavior` is inert on `[hard_deny]`.

## Completion artifacts, per mandated step

| # | artifact |
|---|---|
| 2 | RED: `test.unit.test_classify_input_source` written first as a full suite (18 tests); temporarily stubbed `classify_input_source` to always return `not_file` -> **11 of 18 failed** (all 11 `file`-direction cases; all 7 `not_file`-direction cases passed) -- pasted below |
| 3 | Same run IS the negative-direction proof: the 7 passing `not_file` cases under the always-`not_file` stub show the stub is not a trivial "always pass" -- the guard tests in `test_permission_resolution.py` separately prove this at the rule layer (see below) |
| 4 | `test_rule_without_input_source_is_unaffected` (in `TestInputSourceGuard`) resolves the same rule under both `'file'` and `'not_file'` classifications and asserts identical `'allow'` both times |
| 5 | GREEN: full suite `Ran 4119 tests` / `OK (expected failures=4)` (baseline 4085 + 18 classifier + 7 rule_entry + 9 permission_resolution = 4119, exact) |
| 6 | `test_unrecognized_value_reports_an_error_but_keeps_the_rule` (both `test_rule_entry.py` and mirrored validation path) -- error Issue, rule still normalizes, `entry.input_source` is `None` |
| 7 | `test_input_source_composes_with_a_{default,regex,glob,native}_pattern`, four tests, all green |
| 8 | `test_input_source_and_auto_mode_behavior_act_independently` -- one ask rule carrying both keys; `file` command widens to `allow` (auto_mode_behavior fires), `not_file` command's guard fails first so auto_mode_behavior is never consulted and the level falls through to `ask` |
| 9 | `ruff format --check .` -> `200 files already formatted`; `ruff check .` -> `All checks passed!`; `--stdlib`/`--ambient`/`--layers` all PASS, exit 0 |
| 10 | `tools/corpus_build.py --verify --strict-prose` -> `OK: no differences` at `6401`/`61` |
| 11 | Calibration: removed the `winning_entry.input_source is not None` guard clause (leaving only `!=`, so `None != "file"/"not_file"` fires on every Bash match) -> corpus **FAILED hard**, many verdict/reason differences pasted below; reverted; re-ran -> `OK: no differences` again; `git status --porcelain` on all 5 touched production files showed no probe residue |
| 12 | All 8 entry-point modules imported cleanly |
| 13 | Live end-to-end, real `toolguard.hook:main`, scratch config with `{ match = "Bash([regex]^uv run python\\b)", input_source = "file" }`: `uv run python script.py` -> `"permissionDecision": "allow"`; `uv run python -c "print(1)"` -> `"permissionDecision": "ask"` (rule did not apply, fell to `no_match_fallback=ask`). Both pasted below |
| 14 | Sibling sweep below |

### RED output (step 2/3, classifier)

```
FAIL: test_awk_program_file_flag_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_awk_redirected_from_a_file_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_bash_dash_e_is_a_file_not_inline ... AssertionError: 'not_file' != 'file'
FAIL: test_bash_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_node_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_perl_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_php_program_file_flag_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_python_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_python_value_letters_flag_is_stepped_over_before_the_positional ... AssertionError: 'not_file' != 'file'
FAIL: test_rscript_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
FAIL: test_ruby_positional_script_is_a_file ... AssertionError: 'not_file' != 'file'
----------------------------------------------------------------------
Ran 18 tests in 0.002s
FAILED (failures=11)
```

### RED output (step 3, guard negative direction, `permission_resolution.py`)

Guard clause temporarily removed entirely from `_resolve_unclamped`:

```
FAIL: test_file_required_rule_does_not_fire_on_inline_code ... AssertionError: 'allow' != 'ask'
FAIL: test_input_source_and_auto_mode_behavior_act_independently ... AssertionError: 'allow' != 'ask'
FAIL: test_not_file_required_rule_does_not_fire_on_a_file ... AssertionError: 'allow' != 'ask'
----------------------------------------------------------------------
Ran 9 tests in 0.002s
FAILED (failures=3)
```

(The composition/positive tests in the same class stayed green under the missing guard -- exactly the "a guard that always passes satisfies every positive case" failure mode the brief named, confirming these 3 are the tests that give the others meaning.)

### Calibration FAIL excerpt (step 11)

```
[pattern_forms] Bash('git push origin main').permissionDecisionReason:
    expected: 'Compound command contains denied sub-command: ... deny pattern: [regex]^git\s+push\b ...'
    actual  : 'Compound command contains sub-command requiring approval: ... (no_match_fallback=ask)'
[pattern_forms] Bash('git status').permissionDecisionReason:
    expected: 'Command matches allow pattern: git status ...'
    actual  : '... requiring approval: git status (no_match_fallback=ask)'
[realistic] Bash('gh status') / Bash('git status'): similar -- every previously-matched Bash rule in the corpus stopped matching.
FAIL: hard verdict/output/data-integrity differences found.
```

### Live end-to-end (step 13)

```
$ echo '{...,"tool_input":{"command":"uv run python script.py"},...}' | uv run python -m toolguard.hook
{"hookSpecificOutput": {"permissionDecision": "allow", "permissionDecisionReason": "Command matches allow pattern: [regex]^uv run python\\b  [project: .../toolguard_hook.toml]"}}

$ echo '{...,"tool_input":{"command":"uv run python -c \"print(1)\""},...}' | uv run python -m toolguard.hook
{"hookSpecificOutput": {"permissionDecision": "ask", "permissionDecisionReason": "Command does not match any allow patterns; awaiting a decision (no_match_fallback=ask)"}}
```

## Sibling sweep

- **`resolve_file_path_permission` (Read/Write/Edit)** -- deliberately excluded per brief scope; `input_source` is inert there by construction (parameter defaults `None`, `winning_entry.input_source` is also always `None` for any real file-path rule, so the guard never fires either way for that path).
- **`[hard_deny]`** -- `Configuration.hard_deny()` never exposes entry metadata at all, so `input_source` on a hard_deny entry is inert, identically to `auto_mode_behavior`'s Phase 3 precedent. Not a new gap; consistent with existing design.
- **MCP-terminal tool resolution** -- already covered. `resolve.py`'s `_decide` closure is shared by both native Bash sub-commands and MCP terminal-tool commands (per its own docstring: "regardless of the invoking tool's own name"), and `resolve_command_permission` has exactly one production call site, inside `_decide`. No separate path needed a wire-up.
- **No other consumer found.** `grep`-level check of `resolve_command_permission(` call sites confirmed a single production caller.

## Baseline vs. final

Baseline (start of phase): `Ran 4085 tests` / OK; corpus 6401/61 OK; 3 fitness checks; 8 entry points.
Final: `Ran 4119 tests` / OK (expected failures=4); ruff clean; corpus 6401/61 OK, calibrated; 3 fitness checks PASS; 8 entry points load; `test.unit.test_architecture` 27/27.

## Self-review

- Anti-pattern scan: no async/await, no threading, no local imports introduced.
- No grammar changes -- confirmed throughout; this was pure post-parse token interpretation, exactly as scoped. Never hit a point requiring `.peg`/canopy changes.
- Existing-test modification: one canary test (`test_known_enrichment_keys_holds_...`) in `test_rule_entry.py` asserted `KNOWN_ENRICHMENT_KEYS`'s exact membership and had to be updated to include the new key -- explicitly authorized by the brief ("membership in KNOWN_ENRICHMENT_KEYS," following the Phase 3 precedent, whose own addition is what put `auto_mode_behavior` in that same test's docstring). No other existing test was touched; no test was weakened.
- `docs/agent-map.md`/`docs/configuration.md` updated in the same edit as the code they describe, per the doc-drift sweep habit.

## Time / cost estimate (this phase's continuation only -- prior phases already reported separately)

Rough breakdown for this session's portion (investigation was completed and reported before this continuation began per the prior summary):

- Implementation (classifier, rule_entry, resolve.py, permission_resolution.py wiring): ~20 min
- TDD (writing tests, RED/GREEN cycles for classifier and guard): ~15 min
- Verification (lint, fitness checks, corpus + calibration, entry points, live e2e): ~15 min
- Documentation + sibling sweep + report: ~10 min

Total this continuation: roughly 60 minutes of tool-call time. Estimated cost at Sonnet rates for a session of this token volume: low single-digit USD (a few dollars), consistent with prior phases in this same ticket.


## Correction round: two defects found by the coordinator's review (2026-09-07)

**Both accepted and fixed.** The coordinator measured live against the shipped code; I had not tested the file-path case at all, and my report's "silently inert" claim was wrong -- it was an untested assumption, exactly the kind this project's rules warn against.

### 1. `input_source` on a file-path rule broke matching -- allow went dark, deny failed open

**Root cause, traced (not assumed):** `_resolve_unclamped`'s guard ran unconditionally: `winning_entry.input_source != command_input_source`. `resolve_file_path_permission` never threads a classification, so `command_input_source` stays `None` there -- and `"file" != None` is `True`, so ANY rule declaring `input_source` on a Read/Write/Edit pattern had its level treated as unmatched, regardless of the pattern itself. An allow rule stopped matching (silent narrowing); a deny rule stopped matching too (fail-open -- the more serious direction).

**Fix, two layers:**
- `_resolve_unclamped`'s guard now also requires `command_input_source is not None` -- a resolution that never classified anything (every file-path call) makes the guard a structural no-op, not a mismatch.
- `RuleEntry.input_source` (the single accessor) now ALSO returns `None` when the pattern's tool is in `FILE_TOOLS`, independent of the resolver-side fix -- defense in depth, and it is what makes the config-time rejection below actually correspond to what the rule does.
- New config-time validation (`_input_source_issues`): `input_source` on a `Read(...)`/`Write(...)`/`Edit(...)` pattern is now an `error`-level Issue naming the key and the tool, rejecting the whole key outright rather than accepting it silently-and-inert -- matching the "loud config issue, never a quiet change" instruction.

**RED/GREEN evidence**, `test.unit.test_permission_resolution.TestInputSourceGuardNeverAppliesToFilePathResolution` and `test.unit.test_rule_entry.TestInputSource.{test_input_source_on_a_read_rule_is_rejected,test_input_source_is_rejected_on_every_file_path_tool}`:
- RED (resolver bug, before the `is not None` fix): allow test `AssertionError: 'ask' != 'allow'`; deny test `AssertionError: 'ask' != 'deny'` (in-process default `no_match_fallback` differs from the coordinator's live scratch config, which showed `allow` -- same underlying defect either way: the deny simply never fires).
- RED (validation, before the FILE_TOOLS check): `AssertionError: 'file' is not None` x4 (Read/Write/Edit x2 test methods).
- GREEN after both fixes: `Ran 92 tests` (test_rule_entry.py) / `Ran 37 tests` (test_permission_resolution.py), both OK.

**Live end-to-end, both directions, real hook, post-fix:**
```
allow = [ { match = "Read(<target>/**)", input_source = "file" } ]
  [ERROR] 'input_source' has no effect ... 'Read' is a file-path tool ...
  Read <target>/f.txt -> permissionDecision: allow  (rule still matches correctly)

deny = [ { match = "Read(<target>/f.txt)", input_source = "file" } ]
  [ERROR] 'input_source' has no effect ...
  Read <target>/f.txt -> permissionDecision: deny  (rule still fires correctly)
```
Both the loud diagnostic and the correct underlying decision are present in both directions.

Corpus/fitness/entry-points re-run clean after the fix (`Ran 4124 tests` / OK; ruff clean; 3 fitness PASS; corpus `OK: no differences` at 6401/61; 8 entry points). Corpus-level calibration was not repeated for this specific narrowing condition -- no corpus config declares `input_source` on a file-path rule, so a corpus probe would show nothing regardless of correctness; the two dedicated RED/GREEN unit-test cycles above are the calibration evidence for this fix.

### 2. Level-granularity guard can suppress a sibling deny in the same list -- CONFIRMED, pinned, not fixed (as instructed)

Traced `match_command`: it returns the FIRST matching pattern in list order and never examines the rest. So `deny = [{match="Bash(python *)", input_source="file"}, "Bash(python -c *)"]` resolving `python -c "x"` under `not_file`: `match_command` returns the first pattern (the guarded one) as the level's match; its guard fails; `continue` discards the WHOLE level; the second, unguarded, also-matching pattern is never reached, because `match_command` already returned before ever considering it.

Pinned with `test.unit.test_permission_resolution.TestInputSourceGuardWithinLevelPrecedence.test_a_failing_guard_on_the_first_matching_deny_suppresses_a_sibling_deny` -- asserts the ACTUAL (undesired but documented) behavior: the command falls through to `no_match_fallback` ('ask') instead of being denied. This test PASSED on first run against the unmodified code, confirming the coordinator's reading was correct and needed no resolution-layer change.

Per instruction, **no restructuring of `permissions.py`**. The guard's comment in `_resolve_unclamped` now states plainly: *"including a sibling pattern in the SAME list that would also have matched: match_command returns only the first matching pattern and never tries the rest."* `docs/configuration.md`'s Input-source constraint section gained the same warning, with the practical mitigation (order the unguarded/broader rule first).

### Final state after the correction round

`Ran 4124 tests` / `OK (expected failures=4)`; `ruff format --check .` -> `200 files already formatted`; `ruff check .` -> `All checks passed!`; `--stdlib`/`--ambient`/`--layers` all PASS; `test.unit.test_architecture` 27/27; corpus `tools/corpus_build.py --verify --strict-prose` -> `OK: no differences` at 6401/61; 8 entry points import cleanly; live end-to-end re-confirmed for both the original Bash scenario and both new file-path scenarios (allow and deny).

Files touched this round (subset of the phase's file list, no new files beyond the earlier `test/unit/test_classify_input_source.py`): `toolguard/permission_resolution.py`, `toolguard/rule_entry.py`, `test/unit/test_permission_resolution.py`, `test/unit/test_rule_entry.py`, `docs/configuration.md`, `docs/agent-map.md`.


## Escalation round 2: match semantics rewritten -- pre-match filtering/bucketing replaces post-match guard/rewrite (2026-09-07)

**Accepted in full, including the mid-round extension applying the same defect class to `auto_mode_behavior`.** Both keys share one root cause: treating a guard/behavior as something applied AFTER a plain-pattern match conflates "the pattern text matched" with "the rule matched" -- they are the same thing only when a rule carries no enrichment that can move or veto it. Arnon, 2026-09-07: *"a rule match should be considered on the whole rule, not just the pattern match."*

### The redesign

**Filtering and effective-grouping now happen BEFORE `decide_command_at_level_detailed`/`decide_file_path_at_level_detailed` are even called**, per level, in a new `_level_pattern_buckets()` (`permission_resolution.py`):

- An entry whose `input_source` guard fails for the command's classification (or whose classification is unavailable, e.g. file-path resolution) is dropped -- never offered to the matcher, so it cannot win, and therefore cannot suppress a sibling pattern in the same list. Pattern ORDER stops mattering.
- Under `permission_mode=auto`, an entry declaring `auto_mode_behavior` is bucketed by that EFFECTIVE decision rather than the list it is actually written in (its ACTUAL/real group) -- so deny-first precedence and more-specific-wins now apply to what a rule genuinely DOES, not to which list happened to hold it.

The post-match `continue`-on-guard-failure and the post-match auto-mode decision REWRITE are both **deleted** from `_resolve_unclamped`. `permission_mode`/`command_input_source` are no longer parameters of `_resolve_unclamped`/`resolve_permission_cascade` at all -- dead once filtering/bucketing moved upstream.

### Provenance: decision and group are no longer the same thing

Arnon, 2026-09-07: *"we just need to be careful about provenance... the provenance of the rule is still in the actual group it resides in."* `LevelMatch` gained a new field, `matched_entry_kind: Optional[str] = None` -- the rule's ACTUAL list, set only by `resolve_command_permission`/`resolve_file_path_permission` (the only code that knows which entry produced a given matched pattern, via the bucketing index), left `None` by `permissions.py`/`file_matching.py`'s own unmodified constructors (so **`permissions.py` was never touched**, per the standing scope constraint) and by any hand-built `LevelMatch` in existing tests.

`_matched_rule_lookup`/`_detect_override` now key `provenance_for_pattern`/`entry_for_pattern` off a new `_real_group(result)` helper (`matched_entry_kind` if set, else `decision` -- backward compatible with every hand-built `LevelMatch` in `test_configuration.py`'s cascade tests). **Self-discovered and fixed**: `_detect_override`'s own less-specific-level lookup had the identical ordering-trap bug (hardcoded `DECISION_DENY` as the search kind), not explicitly asked for but fixed in the same pass and pinned with a new test (`test_override_provenance_names_the_overridden_rules_real_list_when_it_too_migrated`).

The reason text: since bucketing means the base match genuinely happens in the EFFECTIVE group, `decide_command_at_level_detailed`'s own reason ("matches allow/deny/ask pattern: ...") is now correct BY CONSTRUCTION and needed no rewrite. `_resolve_unclamped` appends Phase 3's original suffix (`-- auto_mode_behavior='X' applied (permission_mode=auto)`) exactly when `matched_entry_kind != decision`, so a reader sees both the rule that matched and that a migration happened. Live-verified: `"Command matches allow pattern: rm -rf *  [...] -- auto_mode_behavior='allow' applied (permission_mode=auto)"` -- coherent, never contradictory.

### The exact reported bug, fixed and reproduced live, both directions

```toml
no_match_fallback = "allow"
[permissions]
deny = [
    { match = "Bash(mycmd *)", auto_mode_behavior = "allow" },
    "Bash(mycmd --dangerous*)",
]
```
`mycmd --dangerous now`:
- `permission_mode=default` -> `deny`, reason names `mycmd *` (real deny, migration inert outside auto mode)
- `permission_mode=auto` -> **now `deny`** (previously `allow`), reason names `mycmd --dangerous*` -- the migrated rule moved out of the deny bucket, so the unguarded sibling deny wins deny-first precedence, exactly as intended.

And the `input_source` case from round 1, re-verified unaffected by this rewrite: `deny = [{match="Bash(python *)", input_source="not_file"}, "Bash(python /tmp/danger.py)"]` resolving `python /tmp/danger.py` (classified `file`) -> **`deny` in BOTH pattern orderings** (previously `allow`/fell through to a less-specific level in the guarded-first ordering). Pinned in `TestInputSourceGuardIsOrderIndependent`, which replaces the round-1 class that had pinned the bug as a documented limitation.

### A genuine, unrelated test-fixture gap surfaced and fixed

`test_hook.py`'s `_fake_config` stand-in `Configuration` returned bare pattern-string tuples with `layers=()` (never built real `ToolPatternLayer`/`RuleEntry` objects) -- the OLD code path worked fine with this shape since it matched directly against the flat string tuples; the new entry-based bucketing needs real entries and silently saw nothing there, failing 7 previously-unrelated `test_hook.py` tests (ordinary allow patterns with no enrichment keys at all resolving to `ask` instead of `allow`). Fixed by having the fixture build a genuine `ToolPatternLayer` with plain `RuleEntry(pattern=p)` objects (no metadata, so `.input_source`/`.auto_mode_behavior` are both `None` and every existing test's behavior is unchanged) instead of an empty-layers tuple. This is a fixture/helper adaptation required by the authorized refactor, not a weakening of any assertion.

### Tests added/changed this round

- `TestInputSourceGuardIsOrderIndependent` (replaces the round-1 "pinned limitation" class): both pattern orderings deny for the exact reported case; the guarded pattern still wins when its own condition IS met.
- `TestPerRuleAutoModeBehavior`: `test_allow_migrated_to_deny_wins_deny_first_precedence_over_a_matching_ask` (the exact reported scenario, unit-level), `test_provenance_and_additional_context_survive_narrowing_to_deny` (mirror of the existing deny-widened-to-allow test), `test_reason_names_the_actual_rule_and_states_the_behavior_applied`, `test_override_provenance_names_the_overridden_rules_real_list_when_it_too_migrated` (self-discovered `_detect_override` fix).
- `test_hook.py`: fixture fix only, no test assertions changed.

RED confirmed for the whole `TestPerRuleAutoModeBehavior` class (10/11 failed) by temporarily disabling `_effective_kind`'s migration; RED confirmed separately for the override-provenance test by reverting `_detect_override`'s lookup to hardcoded `DECISION_DENY`. Both reverts restored cleanly (`git status --porcelain` clean of probe residue).

### Final verification, this round

`Ran 4129 tests` / `OK (expected failures=4)`; `ruff format --check .` -> `200 files already formatted`; `ruff check .` -> `All checks passed!`; `test.unit.test_architecture` 27/27; 3 fitness checks PASS; corpus `tools/corpus_build.py --verify --strict-prose` -> `OK: no differences` at 6401/61, calibrated by forcing the allow bucket permanently empty in `_level_pattern_buckets` (hard corpus FAIL across nearly every allow-matched case), reverted, re-confirmed passing, `git status --porcelain` clean; 8 entry points import cleanly; live end-to-end re-verified for both `input_source` (Bash and the Read allow/deny file-path cases from round 1) and `auto_mode_behavior` (the exact reported scenario, both permission modes, plus the annotated-reason case).

### Documentation corrected

`docs/configuration.md`'s Input-source section previously (this round's OWN round-1 correction) documented the suppression as a real limitation with "order the unguarded rule first" advice -- removed per instruction, replaced with the correct semantics (a rule whose guard fails did not match, order-independent). Its auto-mode-behavior section gained a new paragraph on precedence-by-effective-group. `docs/agent-map.md`'s matching Q&A entry updated the same way.


## Final correction: reason text names the real group, not the effective one (2026-09-07)

**Accepted.** The wording choice flagged as ambiguous in round 2 was resolved the other way: the BASE clause must name the rule's REAL list ("matches ask pattern"), and the suffix states the effective decision separately -- not the reverse. Arnon: *"the provenance of the rule is still in the actual group it resides in"* -- the sentence a human reads must say so too, not just the `Provenance` object.

### Root cause and fix

`permissions.py`/`file_matching.py` (both untouched, per scope) build the base reason as the literal `f"Command/Path matches {decision} pattern: {pattern}"`, where `decision` is the EFFECTIVE group -- correct as far as those modules know, since that genuinely is the bucket the pattern matched from after TOO-28's pre-match bucketing. New `_reason_naming_real_group()` in `permission_resolution.py` renames that one known literal clause to the REAL group (`_real_group(result)`) whenever it differs, applied before `_append_provenance`. Deliberately a single, exact, known-literal `str.replace(..., count=1)` rather than general parsing -- the literal template was read directly from both source files, not guessed, and the alternative (reconstructing the whole message from scratch) would duplicate the two format strings this module doesn't own.

### Verified: only the prose was wrong, not the data

Explicit check, per instruction: `matched_rule`, `provenance.path`, `provenance.level`, and `decision` on the `RuntimeVerdict` were already correct before this fix (confirmed by a direct probe showing identical values pre- and post-fix) -- `_matched_rule_lookup`'s round-2 fix (keying off `_real_group`) already made the structured `Provenance` object right. `LogRecord` (`log_writer.py`) carries no free-text `reason` field at all, only `matched_rule` (pattern text, group-word-free) and other structured fields -- confirmed by grep, no other prose-composition site exists.

### Tests

Renamed/split the round-2 reason test into two, one per direction, each asserting BOTH that the correct group's word is present and the WRONG one is absent (`assertNotIn`): `test_reason_names_the_rules_real_list_not_its_effective_one` (deny rule widened to allow -- reason says "matches deny pattern") and `test_reason_names_the_real_list_in_the_narrowing_direction_too` (allow rule narrowed to deny -- reason says "matches allow pattern"). RED confirmed by temporarily reverting to `result.reason` unrewritten (both tests failed, reproducing the exact reported wording:` "Command matches allow pattern: rm -rf *  [...] -- auto_mode_behavior='allow' applied"` for a rule actually in the deny list); reverted, GREEN confirmed.

Live end-to-end, both directions, real hook: ask-list rule widened to allow under auto -> `"Command matches ask pattern: some-guarded-cmd*  [...] -- auto_mode_behavior='allow' applied (permission_mode=auto)"`; allow-list rule narrowed to deny under auto -> `"...Command matches allow pattern: mycmd *  [...] -- auto_mode_behavior='deny' applied (permission_mode=auto))"`. Both base clauses name the rule's real list; both suffixes separately state what moved it.

### Final verification, this round

`Ran 4130 tests` / `OK (expected failures=4)`; `ruff format .` -> `200 files left unchanged`; `ruff check .` -> `All checks passed!`; 3 fitness checks PASS; corpus `OK: no differences` at 6401/61 (no corpus rule carries `auto_mode_behavior`, so this prose-only fix is invisible to a decision-diff corpus check by construction -- the RED/GREEN unit-test cycle is the correct instrument here, and is what was used); 8 entry points import cleanly.

**Phase complete.** All three rounds (initial implementation, the two file-path/precedence bugs, and this wording correction) are in a single coherent final state.


## Final rename: `input_source` -> `program_source` (2026-09-07)

**Pure rename, no behavior change**, per Arnon's decision: `input_source` was ambiguous (`python script.py < data.txt` has an obvious "input source" that is not the program) and `program_source` reuses the module's own established vocabulary (`_ExecutorFlags.program_file_letters`/`bare_program`).

### Scope

Mechanical three-pass rename (`INPUT_SOURCE`->`PROGRAM_SOURCE`, `input_source`->`program_source`, `InputSource`->`ProgramSource`) across all 11 files that had any occurrence: `toolguard/constants.py`, `toolguard/rule_entry.py`, `toolguard/permission_resolution.py`, `toolguard/parser/command_extractor.py`, `toolguard/resolve.py`, `test/unit/test_hook.py`, `test/unit/test_permission_resolution.py`, `test/unit/test_rule_entry.py`, `test/unit/test_classify_input_source.py` (renamed to `test_classify_program_source.py`), `docs/configuration.md`, `docs/agent-map.md`. The renamed test file's own class/method names, module docstring, and every `Given/When/Then` docstring changed too, since a stale test description is worse than none.

**Also caught and fixed, found by a follow-up hyphenated-prose grep the underscore-based sed couldn't reach**: `toolguard/auto_mode_trace.py`'s comment ("needs the input-source constraint" -- a file not in the original 11, found by searching "input-source"/"input source" separately from the underscore form), the renamed test file's own opening docstring line ("Tests for the input-source classifier"), `rule_entry.py`'s error message text ("input-source guard will be ignored"), and both `docs/configuration.md`'s/`docs/agent-map.md`'s markdown heading (`## Input-source constraint` -> `## Program-source constraint`) and every anchor link pointing at it. `grep -rni "input.source"` repo-wide (excluding `.git` and memory notes) now returns nothing.

**Also fixed while here**: `RuleEntry.program_source`'s docstring still described ROUND 1's removed mechanism (`resolve_permission_cascade`'s `command_input_source is not None` check as "a second, independent line of defense") -- stale since escalation round 2 deleted that check entirely. Corrected to describe the actual current mechanism: the accessor is what `_level_pattern_buckets`'s pre-match filtering reads.

### Verification

`Ran 4130 tests` / `OK (expected failures=4)` -- identical count to before the rename, confirming no behavior moved. `ruff format .` -> 3 files reformatted (cosmetic re-wrap from longer identifiers only), `ruff format --check .` clean on re-run; `ruff check .` -> `All checks passed!`. 3 fitness checks PASS. Corpus `OK: no differences` at 6401/61 (no re-calibration needed for a pure rename with no corpus config using the key -- the round-2 broad calibration already proved the underlying mechanism is corpus-visible; this round changed no logic). 8 entry points import cleanly. Live end-to-end re-run with the renamed key: `uv run python script.py` under `{ match = "...", program_source = "file" }` -> `allow`; `uv run python -c "..."` -> `ask`; and the file-path rejection message now reads `'program_source' has no effect in the rule entry for 'Read(...)' -- 'Read' is a file-path tool, and 'program_source' only classifies commands.`

### A mistake I made and did not fix myself

While renaming the test file I used `git mv` (not `mv`) out of habit -- this **staged** the file (`git status` now shows `AM test/unit/test_classify_program_source.py` instead of untracked `??`). This is a git write operation I should not have performed. I did **not** run any further git command to correct it, per policy (hand over the command line rather than compound the mistake with another write). **Remedy, for Arnon to run if desired**: `git restore --staged test/unit/test_classify_program_source.py` (or `git reset HEAD -- test/unit/test_classify_program_source.py`) returns it to untracked, matching every other new file from this phase.
