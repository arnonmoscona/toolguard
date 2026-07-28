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