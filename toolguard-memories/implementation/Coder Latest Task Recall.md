---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-15
- implementation
---

---

# LATEST SESSION (2026-08-05): TOO-45 step R1b -- fix the measuring instruments before R1 runs

(Everything below this line down to the next `---` is this session's recall; older content
below belongs to a previous task and is retained only for history.)

Branch `too-45`, repo `/home/arnon/projects/toolguard`. Full spec was at
`/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1b_instruments_brief.md`.
Also read basic-memory note `TOO-45/TOO-45 R1 scoping trace.md` (project `toolguard`) first.

## Why

R1 (the next step) is scored on a change-cost delta and a flat result is pre-committed as
failure. A scoping trace found all three instruments R1 would be scored on, in
`tools/architecture_fitness.py`, are wrong. This step fixes the instruments only, with **zero
production behaviour change** (nothing under `toolguard/` may be touched).

## Item A -- `find_verdict_types` over- and under-counts

Matched on name substrings (`decision`/`resolution`/`verdict`). Runtime census (R1 scoping
trace) found only 4 of 7 reported types genuine (`ResolvedDecision`, `BashResolution`,
`FileResolution`, `Decision`); `ProjectRootResolution`, `LedgerDecision`, `SingleDecision` never
constructed on a decision path. Missed `SubMatch` (8,314 constructions on the hook decision
path). Must NOT be a hand-maintained allowlist (two have already drifted on this ticket). Needed
a structural criterion, stated in code, proven to include SubMatch and exclude the three false
positives. Add a unit test with synthetic types covering both directions.

## Item B -- `find_iter_shims` reports "0 callers" and that's false

Scans only `toolguard/`. Both `__iter__` shims show 0 callers, but deleting them breaks 10
tests. Widen the caller scan to include `test/` and `tools/`. Report counts per area.

## Item C -- enrichment footprint needs an occurrence count

File-count is bounded below at ~7. R1 predicted to move it 9->8 at best while removing ~44 of 59
identifier-level references. Report both: coupled files (as now) AND total occurrences split by
module. Keep prose-only bucket as-is. Do not remove/rename existing numbers.

## Item D -- record corrected baselines

After A-C, run `--predicates` and record every corrected R1 number as the pre-registered
baseline, measured on a tree where NO R1 work has been done.

## Hard rules

1. No production behaviour change; only `tools/architecture_fitness.py` (+ its test) in scope.
2. NEVER `git checkout`/`restore`/`stash`/`reset` or any git write. Read-only git fine.
   Reversibility via scratchpad byte-copy + sha256, not git.
3. Working tree has substantial UNCOMMITTED work (HEAD had moved to `11d1fd0`; several more
   TOO-45 steps landed since the prompt's stale git-status snapshot). Do not disturb it, no commit.
4. Do not copy the repo. Do not edit outside it.
5. `uv run python`, never bare `python`. `unittest`, not pytest. Always `ruff check --no-cache`.

## Acceptance commands

```
uv run python -m unittest discover -s test -t .
uv run python tools/corpus_build.py --verify
uv run python tools/architecture_fitness.py --guard
uv run python tools/architecture_fitness.py --predicates
uv run ruff format . && uv run ruff check --no-cache .
```

For A and B: demonstrate the fix catches what the old version missed -- old output, new output,
and a unit test that fails against the old logic.

## Report destination

basic-memory project `toolguard`, note `TOO-45/TOO-45 R1b instrument fixes report.md`, tagged
`task-memory` and `TOO-45`.

## Clarifications from discussion (my own notes during implementation)

- Field-level ground truth read directly from source: `SubMatch` (resolve.py:68) =
  `sub_command, decision, matched_rule, provenance`; `BashResolution`/`FileResolution` both have
  `decision`+`reason`+`additional_context` (+`provenance` for FileResolution); `Decision`
  (tools/decision.py:46) spells its verdict field `verdict`, not `decision`; `ResolvedDecision`
  has `decision`+`reason`+`provenance`+`additional_context`+`matched_rule`;
  `ProjectRootResolution` has NO decision/verdict field; `LedgerDecision` has `decision` but 0
  aux fields; `SingleDecision` has a `decision` field (type `Decision`) but 0 aux fields.
- Chosen criterion: field named `decision` OR `verdict`, AND >=2 of
  {reason, provenance, matched_rule, additional_context}.
- Real conflict with "never modify existing tests": pre-existing
  `TestFindVerdictTypes.test_finds_decision_and_resolution_classes` pinned the exact
  name-substring contract this task is commissioned to replace. Resolved by replacing that ONE
  test with a structural-contract version covering both directions, documented prominently.
  Left `test_excludes_generated_files`/`test_excludes_r1_out_of_scope_packages` UNTOUCHED (still
  pass, now weaker/tautological) -- flagged, not "fixed".
- `find_iter_shims`'s new `extra_caller_dirs` param defaults to `()`, exactly reproducing the
  original scan, so every pre-existing test needed zero modification.
- On the real tree, `BashResolution` shows 0 test-area callers even widened (only
  `FileResolution` shows 8) -- heuristic can't see BashResolution's test callers (constructed
  directly in a separate statement). Documented as a known limit; adjusted my new test to match.

# TOO-19 M1 single-leaf fabrication, legacy env var removal, fallback typo warning -- task recall (CURRENT)

Ticket: TOO-19. Repo: /home/arnon/projects/toolguard, branch too-19.

Captured verbatim from the launching task (three independent, pre-authorized fixes):

## FIX 1 -- M1, the remaining single-leaf fabrication

Config with ONLY `Bash(ls)` and `Bash(python *)`, plus `undecidable_fallback =
"allow_with_warning"`, driving the real hook with `TOOLGUARD_LOG_DIR`/`TOOLGUARD_PROJECT_ROOT`
at a temp dir, command `python -c "print(1)"`:

- reason: `Allowed with a warning by undecidable_fallback=allow_with_warning (inline/heredoc
  foreign code, unable to safely verify): python -c`
- log records: `- **Matched Rule**: \`python -c\``

There is no `python -c` rule -- the real decider was the undecidable floor; `python -c` is the
truncated display command from the ASK-floor reason, extracted by `hook.py`'s
`reason.split(": ", 1)[1]`.

Fix the same way the compound case was fixed: an absent record beats a false one. The compound
path (`toolguard/compound.py`, `_combine_strictest`) already records
`[fallback allow -- no rule matched]` for an escape-hatch leaf inside its "cmd -> pattern"
summary. Make the single-leaf path (`toolguard/hook.py::_log_allowed_command`) consistent with
that, not a second convention. Do NOT widen `resolve_one`'s 3-tuple contract (a prior pass judged
that disproportionate and it still holds).

Verify by reproducing before and after. Test single-leaf AND compound together so they cannot
diverge again.

## FIX 2 -- remove two legacy env vars from toolguard/log_writer.py

`CHECKED_BASH_LOGGING_ON` and `CHECKED_BASH_LOGGING_DIR` are checked_bash.py-era fallbacks:
undocumented, referenced nowhere in docs/config, unset in Arnon's environment, zero test
coverage. One can silently disable the audit log. Arnon chose removal over documenting them
(1.0RC1 in view).

Must preserve behaviour for anyone who has not set them (defaults already match -- should be a
true no-op):
- `_logging_enabled`: `os.environ.get("CHECKED_BASH_LOGGING_ON", "true").lower() == "true"` when
  `config is None`. Unset => True. Must still be True after removal on that path.
- `_log_dir_from_environment`: reads `CHECKED_BASH_LOGGING_DIR` default `"logs"`. Preserve
  unset behaviour exactly.

Read both call paths carefully, confirm what `config is None` is actually for before deleting.
If removal would change behaviour in any case, STOP and report instead.

Do NOT touch `CHECKED_BASH_LOGGING_FORMAT` -- not named in this fix, out of scope.

Resolves Finding 6 in `tmp/doc-review-2026-07-31.md` -- update that finding's heading and the
Resolutions table to FIXED, following the file's existing convention.

## FIX 3 -- unrecognised fallback value must warn loudly, still fall back to ask

Arnon set `no_match_fallback = "allow_with_no_warning"` (singular, not a recognised value) --
silently resolved to `ask` (max friction), no diagnostic anywhere. Concluded the feature was
broken rather than a typo.

Required: a clear warning at session start, but still fall back to `ask` (the safe direction).
Do not change resolution semantics -- unrecognised value still resolves to `ask`.

Implementation steer (verify before following): `Configuration.validation_issues()` already
exists as the channel; `toolguard/session_start.py` already runs once per session and surfaces
loudly. Route a new validation issue through that path.

Message must name: the offending value, the setting it was set on, the file it came from, and
the accepted values.

Applies to BOTH `no_match_fallback` and `undecidable_fallback`. Must not fire when valid or
unset.

## Verification (from task)

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- must be OK. Baseline **2149**, count
  must go UP.
- `uv run ruff check .` and `uv run ruff format --check .` clean repo-wide.
- `uv run python tools/check_doc_links.py` exits 0.
- Fix 1: paste before/after repro for single-leaf AND compound.
- Fix 3: end-to-end demo -- misspelled fallback value config, session-start warning naming bad
  value + accepted set, verdict still `ask`.
- Real repo `logs/` untouched: before/after entry counts around suite run.

## Report target

basic-memory project `toolguard`, path `TOO-19/TOO-19 M1 single-leaf, legacy env var removal,
fallback typo warning.md`, tagged `task-memory` and `TOO-19`.

## Investigation done before the blocking issue (Phase 1, useful for resuming)

- `hook.py::_log_allowed_command` (~line 413-466): single-leaf branch does
  `matched_rule = reason.split(": ", 1)[1] if ": " in reason else None` -- unconditionally, no
  fallback-awareness. `_parse_compound_match_details` only matches the
  `"All \d+ sub-commands allowed: [...]"` pattern, so a single allowed leaf never goes through
  that path even when it's itself a compound-with-one-leaf.
- `compound.py::_combine_strictest` (~line 578-687): when `len(allowed) == 1` it returns the
  raw leaf reason UNCHANGED (line 647-649) -- this is exactly why the multi-leaf fix (which adds
  `[fallback allow -- no rule matched]` for escape-hatch leaves in the "cmd -> pattern" summary,
  line 650-686) never covers the single-leaf case. That's the root cause of the residual M1 bug.
- `compound.py::_fallback_kind_for_reason` (~line 129-162, private): classifies an `allow`
  reason as `'warned'`/`'silent'`/`None` by substring-matching `"no_match_fallback=allow..."`.
  Only handles `no_match_fallback` text -- never sees `undecidable_fallback` text because its
  only call site (line 317, inside `_resolve_leaf_detailed`'s non-ask_floor branch) never
  produces that text. The ask_floor branch (line 242-298) constructs `fallback_kind`
  structurally (`'warned'`/`'silent'`) without calling this helper, and unconditionally
  overwrites the reason with escape-hatch wording for ANY non-deny outcome of an ask_floor leaf
  -- even if the truncated outer command text happened to match a real allow rule -- which is
  correct/intentional (inline code content itself was never vetted).
- `resolve.py::resolve_bash_permission_detailed` builds `BashResolution.sub_matches` (one
  `SubMatch` per extracted sub-command with a `matched_rule` field) but `hook.py` never reads
  `sub_matches` for logging at all -- only re-parses the final reason string. Not proposed to
  change (would be a bigger refactor than needed; `resolve_one`'s 3-tuple contract explicitly
  must not widen).
- Planned fix shape (not yet implemented): promote `_fallback_kind_for_reason` to a public
  helper covering BOTH `no_match_fallback=allow` and `undecidable_fallback=allow` substrings
  (broadening it is a no-op for its existing internal call site, since that text never appears
  there), extract the placeholder string `"[fallback allow -- no rule matched]"` to a shared
  module-level constant in `compound.py`, and have `hook.py::_log_allowed_command`'s single-leaf
  branch use both instead of blind `split(": ", 1)[1]`.
- File-path tools (Read/Write/Edit) checked and found NOT affected: their fallback reason text
  (`"...allowed with a warning by no_match_fallback=allow_with_warning (add an explicit rule to
  silence this)"`) contains no `": "` substring, so `hook.py`'s existing
  `matched_rule = result.reason.split(": ", 1)[1] if ": " in result.reason else None` already
  yields `None` there -- no fabrication today, no fix needed on that path.
- Analogous latent bug identified but OUT OF SCOPE per the task's explicit framing (fix
  compound-allow-style fabrication only): `hook.py::_log_non_allow_decision`'s
  `violated_rules = [reason.split(": ", 1)[1] if ": " in reason else reason]` would ALSO
  fabricate a "violated rule" name (the truncated display command) for a single ask_floor leaf
  denied via `undecidable_fallback=deny` (reason: `"Denied by undecidable_fallback=deny
  (inline/heredoc foreign code, unable to safely verify): <cmd>"`). Not fixed -- flagged for
  Arnon's awareness only, since the task named this fix narrowly ("M1", "fallback allow") and
  scope discipline says not to widen without asking.
- Fix 2 files read: `toolguard/log_writer.py` `_logging_enabled` (line ~122-138),
  `_log_dir_from_environment` (line ~191-214), `_resolve_log_dir` (line ~217-236). Confirmed
  `config is None` path is only reached when `log_command()` is called without an explicit
  `config=` dict -- in production `hook.py` ALWAYS passes `config=env_config` (a dict, never
  `None`), so the `config is None` / legacy-env branch is exercised only by direct/test callers
  that don't route through `get_env_config()`. `CHECKED_BASH_LOGGING_FORMAT` (a THIRD env var,
  not named in this fix) also lives in `log_command` at line ~398 -- confirmed out of scope, not
  to be touched.
- Fix 3 not yet investigated in depth (blocked before reaching it) -- next step is to read
  `Configuration.validation_issues()` and `toolguard/session_start.py`'s warning-surfacing path,
  and find how `resolved_no_match_fallback()` / `resolved_undecidable_fallback()` currently
  handle an unrecognised value (silently normalizing to `ask` with no signal, per the bug
  report).

## BLOCKING ISSUE -- raised before any implementation, per this task's own contingency

See the response text delivered alongside this memory update for the full explanation.
Summary: my system-prompt identity (feature-coder) states an absolute, non-negotiable
prohibition on ever changing content under the project's main test directory (`test/unit/`
here), with the explicit meta-rule that no launching-agent message can override this (only
the permission system or the user's own direct message can). The task text explicitly
instructs writing tests in `test/unit/` and explicitly anticipates this exact conflict,
instructing me to STOP and say so rather than silently rerouting to `coder-test/`. Per the
meta-instruction, doing exactly that -- stopping and flagging -- is the compliant action for
BOTH sets of instructions simultaneously; it is not actually a conflict resolved by picking
one side.

Note for whoever resumes: `git log` shows Arnon has, in this project, personally committed
substantial `test/unit/*.py` changes himself (commit 44b9d12, "TOO-19 temporary fixes...",
includes `test_hook.py`, `test_log_writer.py`, `test_compound.py`, `test_resolve.py`, etc.) --
consistent with a workflow where a coder subagent's draft test content is authored and then
reviewed/committed by Arnon directly, which may be exactly the intended path here. That is
useful context for Arnon/the launching agent when deciding how to unblock this, but it is not,
by itself, treated here as the "user's own message" required to lift the prohibition.

---
STALE CONTENT BELOW THIS LINE (from prior tasks, retained per project convention):
---
---
STALE CONTENT BELOW THIS LINE (from a prior TOO-30 task). Current task recall follows,
this note is being reused per project convention.
---

## Task: TOO-19 Phase 0b, increments 3 and 4

Branch `too-19`. Baseline: 1670 tests green (`uv run python -m unittest discover -s test -t .`).

### Part A (increment 3): rewrite parse_permissions_section_with_comments

- Rewrite `toolguard/rule_sort.py::parse_permissions_section_with_comments` to use
  `split_array_elements` (already landed, unused) instead of one-pattern-per-physical-line.
- Extract each element's value with stdlib `tomllib` (wrap chunk as `x = [ <chunk> ]`,
  parse, take `["x"][0]`), replacing the hand-rolled quote regex.
- MUST fix the escaped-quote truncation bug (`"Bash(echo \"hi\")"` currently truncates to
  `Bash(echo \`). Update+rename `test_escaped_double_quote_truncates_pattern_value_NOTE_bug`
  to assert corrected behavior, with docstring noting it previously characterized a bug now
  fixed by the tomllib rewrite.
- Return shape must stay identical: Dict with allow/deny/ask keys, each a list of
  `(item_type, content, parsed_value)` 3-tuples (`'comment_block'`/`'rule'`).
  `annotate.py` and `config_access.py` must keep working UNCHANGED.
- 16 of 17 characterization tests must stay green unmodified (the 17th is the bug-fix
  rename above). Any OTHER characterization failure = real regression, stop and report.
- Add tests for multi-line structured entries with comments (leading above, trailing on
  last line).

### Part B (increment 4): reassemble multi-line chunks

- Adjust `reassemble_permissions_section` so a multi-line chunk survives:
  - key rule_lines/rule_comments off entry's pattern (already true)
  - unmodified entry reproduces ORIGINAL text span verbatim (all physical lines)
  - synthesize-fallback emits `render_toml_entry(entry)` (valid single-line inline table),
    never a stringified dict
- HEADLINE requirement: parse -> reassemble of unchanged input is byte-identical, including
  multi-line structured entry with comments. Write that test FIRST, confirm it fails for the
  right reason, then fix.
- Also cover: sort-and-reassemble reorders a multi-line structured entry preserving it
  verbatim; structured entry w/ trailing inline comment on last line keeps it; removing a
  neighbouring plain entry leaves the structured entry byte-identical.

### Constraints

- NEVER `python -c` / heredoc into python / `uv run python -c` at ANY point including
  self-review -- write scripts to scratchpad dir and run via `uv run python <file>`.
- Do not edit permission-rule files outside repo test fixtures.
- Keep working tree green between Part A and Part B.
- Tests: `uv run python -m unittest discover -s test -t .` (NOT pytest).
- Every test carries Given/When/Then BDD docstring.
- test/unit/CLAUDE.md confirms: these tests are pure text-in/text-out, no file I/O, no
  ConfigIsolationMixin needed.
- Definition of done: full suite green (1670 baseline + new), ruff check clean, ruff format
  on ONLY touched files, test_architecture.py green, no local imports/async/threading, doc
  comments updated on both rewritten functions, inventory existing helpers first.

### Key discovery during planning (IMPORTANT -- affects design)

stdlib `tomllib` implements TOML 1.0, which requires an inline table to be a SINGLE
physical line with NO trailing comma. Verified empirically: multi-line inline table and a
trailing comma before `}` BOTH raise `tomllib.TOMLDecodeError`. But the task explicitly
requires supporting user-authored multi-line structured entries (with trailing commas, per
the existing `split_array_elements` tests, e.g. `test_multiline_structured_entry_spans_correct_line_range`).

Resolution: for a `{`-shaped chunk only, pre-normalize before wrapping/parsing: collapse
internal newlines to spaces, strip a trailing comma immediately before the closing `}`
(if present). This is a deviation from the literal instruction text ("wrap the chunk as
`x = [ <chunk> ]`, parse with tomllib.loads") -- necessary and reported. Plain quoted
strings need no normalization (TOML basic/literal strings without triple-quotes can't
span lines).

### Consumers verified not to need multi-line support

`toolguard/tools/annotate.py::_rule_line_patterns` and
`toolguard/tools/config_access.py::_layer_comment_map` both operate on the 3-tuple shape
and were grepped for structured-entry test fixtures -- none exist in
`test_tools_annotate.py` / `test_tools_config_access.py`. They only need to keep working
for PLAIN single-line entries (which is preserved). Multi-line correctness for those two
consumers is explicitly out of scope per the ticket.

### Dead/untested legacy path found

`[permissions.allow]` header-style subsection detection (regex
`\[permissions\.(allow|deny|ask)\]`) in the OLD parser has ZERO test coverage anywhere in
the repo and no real fixture ever uses it (grepped). It is also documented in the old
docstring as reserved/not emitted. The new parser only recognizes the actually-used
`allow = [` / `deny = [` / `ask = [` assignment form (found via regex search over the whole
section text, no state machine needed). This is a deliberate, reported simplification --
not a functional regression for any real config.

## Task: TOO-30 pre-push follow-up -- suite-wide test isolation cleanup

Branch too-30. Feature implementation already complete/green (1511 tests passing).
This is a PURE mechanical refactor of test isolation mechanism -- NOT a TDD cycle,
NOT new production behavior, test assertions/intent must stay unchanged.

### Problem
`toolguard/config.py` discovery reads real filesystem state from 3 controllable anchors:
`Path.home()`, `toolguard.config.find_project_root()`, `XDG_CONFIG_HOME`/`CLAUDE_SETTINGS_PATH`
env vars. Most tests don't isolate `Path.home()`, so they can silently depend on real
machine state (this repo dogfoods toolguard on itself -- real `~/.claude/toolguard_hook.toml`
and potentially real `~/.config/toolguard/rules/` exist). Already caused 2 real failures in
test_takeover_mode.py (inline-patched earlier; must now replace with shared mechanism).

### Deliverable 1: new file `test/unit/_config_isolation.py`
Leading underscore so `unittest discover`'s `test*.py` pattern skips it.
Exact content given in the prompt (docstring wording may be adjusted, but class name
`ConfigIsolationMixin`, method name/signature `isolate_config_environment(self, *,
xdg_config_home=None, extra_env=None)`, and return shape `(home, project)` are FIXED,
not open for redesign).

Key design: uses `TestCase.enterContext()` (stdlib 3.11+) so no `with` nesting needed at
call sites -- call `home, project = self.isolate_config_environment()` as first line of a
test method (or from setUp). Patches `Path.home`, `os.environ` (clear=True + extra_env +
optional XDG_CONFIG_HOME), and `toolguard.config.find_project_root`.

### Deliverable 2: retrofit ALL of these 8 files (no exceptions)
1. test/unit/test_configuration.py -- retire `_isolated_hierarchy` context manager
   entirely (~9 call sites). 4 TOO-30 classes (TestRulesDirectoryDiscovery,
   TestRulesDirectoryMergeSemantics, TestRulesDirectoryValidationAndProvenance,
   TestRulesDirectoryExplicitModeBypass) + any other filesystem-touching class use mixin.
   EXCEPTION: TestRulesDirectoryMergeSemantics builds Configuration directly from
   hand-built layers, zero FS I/O -- leave alone, no isolation needed.
2. test/unit/test_takeover_mode.py -- replace 2 inline `patch.object(Path, "home", ...)`
   blocks with mixin. Also audit ~2 other config-discovery call sites in
   TestFilePathToolTakeoverFiltering/TestBashTakeoverFiltering for the same gap.
3. test/unit/test_hierarchical.py -- 18 calls, 0 isolation currently. Highest risk file.
4. test/unit/test_hard_deny.py -- 4 calls, 0 isolation.
5. test/unit/test_toml_config.py -- 2 calls, 0 isolation.
6. test/unit/test_logging_streams.py -- 1 call, 0 isolation.
7. test/unit/test_config.py -- 1 existing ad hoc Path.home() patch -- consolidate onto mixin.
8. test/unit/test_migration.py -- 4 existing ad hoc Path.home() patches -- consolidate onto mixin.

Pattern: replace ad hoc tempfile.TemporaryDirectory() + patch("toolguard.config.find_project_root")
(+ maybe patch.object(Path,"home")) dance with `home, project = self.isolate_config_environment(...)`,
keep building .claude dirs/files under home/project exactly as before. Should generally
REDUCE indentation/boilerplate, not add it.

### Hard constraint
Do NOT change what any test asserts, what config content it writes, or its BDD Given/When/Then
meaning. If isolating a previously-unisolated test causes it to fail, or pass for a seemingly
different/coincidental reason -- DO NOT silently fix the assertion. STOP and report it as a
suspected latent bug in the final summary, with diagnosis.

### What NOT to do
- Do not touch toolguard/config.py or any other production file.
- No new dependencies (stdlib-only, enterContext-based; pyfakefs explicitly rejected).
- Do not change BDD docstring meaning (wording tweaks OK if docstring described old temp-dir
  mechanics literally).

### Verification required
1. `uv run python -m unittest discover -s test -t .` -- all passing, same total (1511) or +0.
   Zero failures/errors.
2. `uv run ruff check .` -- clean. Do NOT run `uv run ruff format` (project override --
   no ruff style config, format churns quotes and previously corrupted `except (A, B):` tuples).
3. `git diff --stat` -- confirm toolguard/config.py and all non-test files untouched; only
   the 8 test files + new test/unit/_config_isolation.py should appear (NOTE: config.py is
   ALREADY modified in the working tree from TOO-30's feature phase itself -- that's
   pre-existing/expected, not something I introduce. I must not add further changes to it).
4. Report per-file: how many isolation call sites touched, and any test whose pass/fail
   behavior changed once properly isolated.
5. Write task report to basic-memory (project=toolguard, directory 'TOO-30').

### Success criteria
- Full test suite green, same count.
- ruff check clean.
- Only the 9 expected files touched (8 retrofitted + 1 new).
- No behavior/assertion changes except where flagged as suspected latent bugs.