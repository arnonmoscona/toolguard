---
title: TOO-19 Fail-Open Config Parse Failure ASK-Floor Implementation Report
type: note
permalink: toolguard/too-19/too-19-fail-open-config-parse-failure-ask-floor-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Closed the fail-open hole where a broken (unparseable) `toolguard_hook.toml`/
`.json` file silently dropped every rule it contained -- including `deny`
and `[hard_deny]` -- with only an easy-to-miss stderr warning. Implemented
exactly Arnon's decision: when any governed config file fails to parse,
every permission decision is clamped to `ask` (never `allow`, never a
silent no-op) until it is fixed, with a `permissionDecisionReason` naming
the broken file(s) and their parse errors. An explicit `deny`/`hard_deny`
is never weakened. Full suite green: 1691 baseline -> 1713 (+22 new tests,
zero existing tests modified).

## Chokepoint chosen: `Configuration.resolve_permission_detailed`

Traced both governed-tool families to their single shared call site:

- File-path tools (Read/Write/Edit): `resolve.resolve_file_path_permission_detailed`
  -> `config.resolve_permission_detailed(tool_name, _decide_detailed)`.
- Bash/MCP-terminal tools: `resolve.resolve_bash_permission_detailed`, PER
  SUB-COMMAND (so a compound command's clamp propagates naturally through
  the existing strictest-wins combinator in `compound.py` with zero changes
  there) -> `config.resolve_permission_detailed("Bash", _decide_detailed)`.

Both the live hook (`hook.main`) and the read-only `--eval`/replay path
(`toolguard.tools.decision.decide` -> the same two `resolve.py` functions)
funnel through these, so `Configuration.resolve_permission_detailed` is the
one place that sees every governed tool's decision, for both live and
`--eval` execution, without touching the Bash-specific compound pipeline
(`compound.py`'s own `ask_floor`/`LeafCommand` machinery is untouched, per
the brief's explicit instruction not to reuse it). `hard_deny` matches are
checked and returned by the CALLER before this method is ever invoked, so
they are naturally unaffected -- no special-casing needed for "never weaken
hard_deny," it falls out of the architecture.

Implementation: the original method body was extracted unchanged into a new
private `_resolve_permission_detailed_unclamped`; the public
`resolve_permission_detailed` now calls it and pipes the result through a
new `_apply_parse_failure_ask_floor`, which mirrors `compound.py`'s existing
ASK floor (`_resolve_leaf`, lines ~65-71) exactly: `deny` -> unchanged;
`allow`/`ask` -> `ask` with a new reason from `_parse_failure_reason()` (also
overwrites an already-`ask` reason with the floor message, matching that
same precedent, tested explicitly).

## "Top level is not a table" case: counts as broken

Verified against `_parse_source`'s actual `None`-return paths (now
`_try_parse_source`): a `TOMLDecodeError`/generic exception AND the
"top level is not a table" `TypeError` both flow through the SAME generic
`except Exception` branch inside the main hierarchy-discovery loop (where
the path is guaranteed to exist, since `_discover_levels` only yields paths
it found on disk). No special-casing was needed -- it is automatically
included in `parse_failures` for exactly the reason Arnon suspected: same
silent information-loss failure mode as a syntax error. Covered by
`test_top_level_not_a_table_is_a_parse_failure` in
`test/unit/test_configuration.py`.

## Scope of "broken" vs "absent" -- how it's enforced

New `_parse_source_recording_failures(path, file_format, parse_failures)`
wraps the new side-effect-free `_try_parse_source` (which both the
unchanged `_parse_source`, kept for callers that don't need the bookkeeping,
and this new function delegate to). It prints the SAME warning
`_parse_source` always did, but only appends `(path, message)` to
`parse_failures` when `path.exists()` -- so a `CLAUDE_SETTINGS_PATH` pointing
at a genuinely missing file (the one call site without a pre-existing
`.exists()` guard) still warns exactly as before but is NOT treated as
"broken." Within the main hierarchy-discovery loop and the two
already-`.exists()`-guarded `hook_toml`/`hook_json` branches, this check is
trivially true (discovery never yields nonexistent paths), so it's a no-op
there.

## `_parse_source` call sites -- what feeds `Configuration` and what doesn't

Per the brief's request to report on all 6 call sites:

- **Feed `load_configuration`'s returned `Configuration` (switched to
  `_parse_source_recording_failures`, now propagate to `parse_failures`):**
  the main hierarchy-discovery loop (~line 2110→2204 post-edit), and all
  three `CLAUDE_SETTINGS_PATH` explicit-mode branches (explicit settings
  file, adjacent `toolguard_hook.toml`, adjacent `toolguard_hook.json`).
- **`_hierarchical_toggle`** (reads the project-level `hierarchical_configuration`
  toggle): still calls the unchanged `_parse_source`. Does NOT need its own
  `parse_failures` entry -- it is a pre-existing (documented, unrelated)
  duplicate parse of the SAME first-priority project-level file the main
  discovery loop parses again afterwards; if that file is genuinely broken,
  the main loop's parse of it is what actually gets recorded. Confirmed via
  the real double-stderr-warning observed in end-to-end verification
  (pre-existing quirk, not something this change introduced or needed to
  fix -- also called out in the prior "TOO-19 Corrective Change" report).
- **`config_sync_settings_from_sources`**: still calls the unchanged
  `_parse_source`. This is a legacy path (`auto_migrate`'s own migration
  settings lookup) that does NOT build or feed a `Configuration` at all --
  documented this explicitly in its own docstring. A broken file here just
  falls back to that function's own defaults, same as before; the file's
  actual permission rules going unenforced is still caught by the normal
  `load_configuration()` path that runs earlier in the same hook
  invocation.

## `--eval` parity

Free consequence of the chokepoint choice -- no separate code path exists.
Verified by a new test (`test_eval_reflects_parse_failure_ask_floor` in
`test_hook_eval.py`) and by driving the REAL `toolguard --eval` console
entry point as a subprocess against a real broken-file fixture (see
Verification section) -- both show `ask` with the naming reason.

## SessionStart loud alert (`toolguard/session_start.py`)

Added `_detect_broken_config_files(cwd)` -- a NEW, separate function that
calls `load_configuration(cwd)` a second time and returns
`tuple(config.parse_failures)`. Deliberately did NOT widen
`_detect_conflicts`'s existing 2-tuple return (`static_conflict,
dynamic_conflict`): `test_session_start.py` has ~10 existing tests that
unpack it as a 2-tuple, and per the brief's "no existing test may need
modification" instruction I kept that function's contract byte-identical.
The extra `load_configuration()` call is a minor, session-start-only
(once-per-session) cost, not a per-tool-call one.

`_format_summary(static_conflict, dynamic_conflict, broken_files=())` gained
a new optional trailing parameter (default preserves every existing call
site and, verified by a new test, produces byte-identical output to before
when omitted). The broken-file section is unconditional -- independent of
the conflict sections -- and states the file, its parse error, and that
toolguard is falling back to ASK.

`main()` now also calls `_detect_broken_config_files` and includes it in
the print-trigger condition, still always exits 0 (the broken-file lookup
sits inside the same `try/except Exception` block; a failure there is
caught the same way an existing `load_configuration` failure already was).

### A subtle test-compatibility finding (worth flagging)

`test_session_start.py`'s `TestMain`/`TestDetectConflicts` build
`MagicMock(spec=Configuration)` WITHOUT setting `parse_failures` explicitly
(pre-existing fixtures, ~10 call sites). I empirically verified
(`probe_mock_spec.py`, scratchpad) that on such an unconfigured mock,
`bool(mock.parse_failures)` is `True` (MagicMock's default `__bool__`) but
`len(...)` is `0` and iterating yields nothing (MagicMock's default
`__iter__`/`__len__`). Writing the check as `if config.parse_failures:`
(direct truthiness) would have silently broken `test_no_stdout_when_no_conflicts`
and its siblings. Using `tuple(config.parse_failures)` (iteration-based)
instead is correct for BOTH a real `Configuration` and these pre-existing
mocks, and I verified `test_no_stdout_when_no_conflicts` still passes
unmodified. Added a dedicated regression test
(`test_no_stdout_when_no_conflicts_or_broken_files_default_mock`) explaining
this in its docstring so it doesn't get silently "fixed" back to truthiness
later.

## `Configuration.parse_failures` and `validation_issues()`

New frozen-dataclass field `parse_failures: Tuple[Tuple[Path, str], ...] = ()`
on `Configuration`, documented in the class docstring's new "Attributes"
section (matching `ConfigLayer`'s existing per-field-in-docstring style).
Default-only addition -- confirmed every existing `Configuration(...)`
construction site in the codebase uses keyword args only (grepped), so
nothing needed updating.

`validation_issues()` now prepends one `Issue(level="error", ...)` per
`parse_failures` entry, ahead of the existing checks (most severe first),
with corrective steps pointing at the ASK-floor consequence. This already
flows through `hook.py`'s existing once-per-session `_run_startup_validation`
-> `log_error(...)` routing with zero changes needed there.

## Testing (TDD, red first)

All new tests carry Given/When/Then docstrings. Confirmed red-for-the-right-reason
(`AttributeError`/`TypeError: unexpected keyword argument 'parse_failures'`)
before implementing.

- `test/unit/test_configuration.py` (+11 tests, 3 new classes):
  `TestParseFailureAskFloor` (allow->ask with reason; ask-reason rewritten;
  explicit deny NOT weakened; valid config completely unaffected -- the
  primary regression guard), `TestParseFailuresPropagation` (end-to-end via
  `ConfigIsolationMixin`: broken rules-dir file recorded alongside a valid
  layer whose rules still work; valid config has empty `parse_failures`;
  top-level-not-a-table counts; `CLAUDE_SETTINGS_PATH` missing file does
  NOT count; `CLAUDE_SETTINGS_PATH` broken file DOES propagate),
  `TestValidationIssuesParseFailures` (error Issue per broken file; none
  when empty).
- `test/unit/test_hard_deny.py` (+2 tests in `TestHardDenyCommand`):
  hard_deny stays `deny` under a broken config (never weakened); a
  non-hard-denied command IS clamped to `ask` by the same broken config
  (the actual security fix, demonstrated at the hard_deny-aware resolution
  layer, not just the bare `Configuration` method).
- `test/unit/test_hook_eval.py` (+1 test): `--eval` reflects the clamp.
- `test/unit/test_session_start.py` (+8 tests): `_format_summary`'s new
  parameter (4 tests, including a byte-identical-output regression guard),
  `_detect_broken_config_files` (2 tests), `main()`'s alert + exit-0 (1
  test) + the MagicMock-compatibility regression guard (1 test).

Every new test class that reaches `load_configuration()`
(`TestParseFailuresPropagation`) mixes in `ConfigIsolationMixin` per
`test/unit/CLAUDE.md`'s checklist; the others hand-build `Configuration`/
`ConfigLayer` directly (zero file I/O), which the checklist says needs no
isolation.

## Self-review results

- Full suite: `uv run python -m unittest discover -s test -t .` -> 1713
  tests, OK (1691 + 22 new; zero existing tests modified -- verified via
  `git diff` showing 0 deletion lines in every touched test file except
  diff headers).
- `test/unit/test_architecture.py`: 7/7 green (no new local imports, no
  layering violation -- `Configuration` stays in `config.py`, nothing moved
  to/from `config_types.py`/`issues.py`/`rule_entry.py`).
- `uv run ruff check` on all 6 touched Python files: clean.
- `uv run ruff format` on ONLY the touched files: 3 files reformatted
  (pure whitespace/parenthesization, e.g. multi-`with`-statement
  parenthesization in pre-existing `test_hook_eval.py` code -- confirmed
  semantically identical by whitespace-stripped diff comparison and by the
  full suite staying green after formatting).
- Anti-pattern scan: no `async`/`await`, no `threading`/`Thread` in any
  touched file.
- Duplication/reuse check: reused `_multiline_structured_entry_diagnostic`
  unchanged (as instructed); reused the existing `ConfigIsolationMixin`,
  `ConfigLayer`/`Provenance` test-construction patterns already established
  in `test_configuration.py`/`test_hard_deny.py` rather than inventing new
  ones; mirrored `compound.py`'s ASK-floor semantics explicitly rather than
  re-deriving them.
- Doc-drift sweep: reused `docs/security.md`'s existing "fail-safe, not
  fail-open" narrative with a new short section
  ("A broken config file also fails safe, not open"); updated
  `_parse_source`'s own docstring (now a thin wrapper) and added
  cross-referencing notes to `_hierarchical_toggle` and
  `config_sync_settings_from_sources` explaining why they do NOT need
  `parse_failures` bookkeeping, so no stale "out of scope" claims remain
  now that the fail-open *consequence* (not the file-skip mechanism itself)
  has changed. Grepped for other stale references to the old fail-open
  framing; none found outside what was updated.

## End-to-end verification output

Scratchpad script `verify_ask_floor_e2e.py` (isolated temp home/project
pairs, patches `Path.home`/`find_project_root` directly, mirroring
`ConfigIsolationMixin`'s own approach):

```
=== BROKEN config: 'git status' (normally allow) ===
decision: ask
reason: Compound command contains sub-command requiring approval: git status (toolguard config is BROKEN -- falling back to ask for every tool call.
Unparseable file(s):
  /tmp/.../project/.claude/toolguard_hook.local.toml: Invalid value (at end of document)
Rules in these files are NOT being enforced. Fix the file(s) to restore normal permission handling.)
parse_failures: ((PosixPath('/tmp/.../toolguard_hook.local.toml'), 'Invalid value (at end of document)'),)

=== BROKEN config: 'rm -rf /' (explicit deny) ===
decision: deny
reason: Compound command contains denied sub-command: rm -rf / (Command matches deny pattern: rm -rf *  [project: /tmp/.../toolguard_hook.toml])

=== VALID config: 'git status' ===
decision: allow
reason: Command matches allow pattern: git *  [project: /tmp/.../toolguard_hook.toml]
parse_failures: ()

RESULT: PASS
```

Additionally drove the REAL `toolguard`/`toolguard-session-start` console
entry points as subprocesses (`uv run python -m toolguard.hook [--eval]`,
`uv run python -m toolguard.session_start`) against a real broken-file
fixture on disk:

- `--eval` against the broken project: `permissionDecision: "ask"`, reason
  names the file -- identical shape to the live (non-`--eval`) hook.
- Valid config (broken sibling removed): `permissionDecision: "allow"`.
- `toolguard-session-start` against the broken project: prints the
  `CONFIG BROKEN -- falling back to ASK ...` alert naming the file, exits 0.
- Live (non-`--eval`) hook against the broken project: `validation_issues()`
  correctly wrote a real `## ... - ERROR` entry to
  `logs/toolguard-error-*.md` with the exact message/corrective-steps text
  designed above.

(Noted, not a defect: the broken file's warning prints 2x per
`load_configuration()` call due to the PRE-EXISTING `_hierarchical_toggle`
double-parse quirk documented in the prior "TOO-19 Corrective Change"
report; `session_start.main()`'s two separate `load_configuration()` calls
[`_detect_conflicts` + `_detect_broken_config_files`] therefore print it 4x
there. Out of scope for this change; flagging for visibility only.)

## Deviations / things worth flagging

1. `session_start.main()` now calls `load_configuration(cwd)` twice
   (once inside `_detect_conflicts`, once inside the new
   `_detect_broken_config_files`) rather than widening `_detect_conflicts`'s
   return shape, specifically to avoid touching its existing ~10-test
   contract. SessionStart runs once per session, so the extra discovery
   walk is a one-time cost, not a per-tool-call one.
2. Added two small doc/comment-only clarifications beyond the literal
   4-item "Required changes" list: a cross-referencing note on
   `_hierarchical_toggle` and `config_sync_settings_from_sources`
   explaining why they don't need `parse_failures` bookkeeping (directly
   answering the brief's "report what you find about the others"), and a
   new short section in `docs/security.md` extending the existing
   "fail-safe, not fail-open" narrative to this change. Both are
   documentation-only, no behavior change.
3. Nothing in the brief was found to be contradicted by the implementation.

## Time / cost (rough)

- Phase 1 (planning, requirements capture incl. reading prior "TOO-19
  Corrective Change" memory, codebase exploration of the chokepoint
  candidates, MagicMock probing): ~19 min, ~$0.60-0.75 (heavy tool use --
  many reads/greps across config.py/resolve.py/hook.py/session_start.py,
  one probe script).
- Phase 2 (TDD implementation across config.py/session_start.py + 4 test
  files, including one self-found test-helper bug (missing `Bash(...)`
  wrapper) fixed mid-flight): ~13 min, ~$0.55-0.70 (many targeted edits,
  several full-suite runs, real subprocess verification).
- Phase 3 (self-review: ruff, anti-pattern scan, doc-drift sweep,
  end-to-end scratchpad + subprocess verification): ~6 min, ~$0.25-0.30.
- Phase 4 (this report + IDE opens): ~3 min, ~$0.10-0.15.
- **Total: ~41 minutes wall time, roughly $1.50-1.90 estimated token cost**
  (Sonnet 5 pricing, rough order-of-magnitude for a tool-heavy security-fix
  session).
