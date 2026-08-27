---
title: TOO-45 ticket 104 - dicts are undeclared types - coder implementation report
type: note
permalink: toolguard/toolguard-memories/too-45/too-45-ticket-104-dicts-are-undeclared-types-coder-implementation-report
tags:
- task-memory
- TOO-45
- ticket-104
- implementation-report
---

## Summary

Implemented both parts of ticket 104 (proposed-tickets/104-dicts-are-undeclared-types.md),
approved by Arnon.

## Part 1 -- toolguard/hook.py: parse_hook_input() returns PreToolUseEvent

`parse_hook_input()` now returns `toolguard.claude_code_contract.PreToolUseEvent` instead of
`Dict[str, Any]`. Required-field validation (`tool_name`, `tool_input`, `hook_event_name`
present) stays in hook.py as before -- policy, not contract -- then constructs the event via
`PreToolUseEvent.from_json_dict(data)`. No validation was added to the dataclass itself.

Every caller updated to attribute access:
- `_run_eval_mode()`: `hook_data.tool_name` / `.tool_input` / `.cwd`
- `main()`: same three, plus `hook_data.permission_mode` (was `.get(PERMISSION_MODE_KEY)`)
- `_agent_info_for()`: signature simplified from `(hook_data: Dict[str, Any])` to
  `(transcript_path: str)` -- it only ever read `transcript_path`, so this drops its
  dependency on the whole event/dict entirely rather than threading a dataclass through for
  one field. Call site: `_agent_info_for(hook_data.transcript_path)`.

**Contract KEY imports in hook.py: 6 before this ticket's own change -> 4 after**
(`CWD_KEY`, `HOOK_EVENT_NAME_KEY`, `TOOL_INPUT_KEY`, `TOOL_NAME_KEY` remain -- all four are
still legitimately used: the first three for `parse_hook_input`'s required-field check on the
raw JSON dict before dataclass construction, `CWD_KEY` also (with `TOOL_NAME_KEY`/`TOOL_INPUT_KEY`)
inside `_build_crash_context`, which reads Python `locals()` -- a different, pre-existing,
out-of-scope use unrelated to `hook_data`'s type. `PERMISSION_MODE_KEY` and `TRANSCRIPT_PATH_KEY`
are now unused and removed). Matches the ticket's historical figures (12 before ticket 99, 6
after ticket 99, now 4 after this ticket).

**No caller needed `.to_json_dict()` to paper over a mismatch** -- every site fit the dataclass
cleanly. The one behavioural subtlety checked and confirmed harmless: `PreToolUseEvent.cwd`
defaults to `""` (not `None`) when the field is absent, whereas the old code used
`hook_data.get(CWD_KEY, None)`. Traced every downstream consumer
(`toolguard.path_utils.require_project_root`, `toolguard.env_config.find_project_root`) -- both
use `if start_dir else ambient.cwd()`, so `""` and `None` are equivalent (falsy). No `or None`
conversion needed.

### An unexpected fallout: --ambient false positive

`hook_data.cwd` (a dataclass field read) collided with `tools/architecture_fitness.py`'s
`--ambient` scan, which flags ANY `.cwd`/`.resolve`/`.home`/etc attribute name anywhere
(module + attribute-name granularity, not receiver-type-aware) as a possible
`pathlib.Path.cwd()` ambient read. Fixed via the tool's own documented remediation: added
`("hook", "cwd"): "PreToolUseEvent.cwd, a wire field parsed from stdin JSON -- not
Path.cwd()"` to `PATH_AMBIENT_OWNERS` in `tools/architecture_fitness.py`. This is a per-module
(not per-site) exemption -- the tool's own known, documented limitation, same tradeoff as
every other entry in that dict.

## Part 2 -- tools/architecture_fitness.py: --undeclared-types

Added as a self-contained section (`_is_serializer_name`, `UNDECLARED_TYPES_OPEN_ENDED_EXEMPTIONS`,
`UndeclaredTypeFinding`, `UndeclaredTypesReport`, `_is_public_function_name`,
`_is_bare_dict_annotation`, `_own_return_statements`, `_returns_dict_literal`,
`_iter_functions_with_class`, `_collect_called_names`, `check_undeclared_types`,
`render_undeclared_types_text`), inserted right after the concurrent #100 agent's `--orphans`
section, following the same insertion style.

**Declaration checked (strong half, per evidence-before-fixing.md):** the return annotation
itself. Flags a public (no leading underscore, no dunder) function or method annotated
exactly `-> Dict[str, Any]` / `-> dict` / `-> Dict` (bare, unparameterised), or with no return
annotation at all that returns a dict literal (`return {...}`) somewhere in its own body
(nested defs excluded). A narrower annotation like `Dict[str, int]` is deliberately left
alone -- only the "completely undeclared value type" shape is flagged.

**"Crosses a module boundary" (heuristic half, labelled as such in the docstring and in
render output):** a name/attribute call-site scan with no import resolution -- true if the
function's bare name is called anywhere (as `name(...)` or `.name(...)`) in ANY toolguard
file other than the one that defines it. Can over-report (unrelated function, same name) and
under-report (a call reached only via an untraced alias). Only the annotation/literal half is
exact; this half is explicitly documented as a heuristic, not a verdict.

**Two exemptions, built in up front as the ticket specified:**
1. `_is_serializer_name(name)`: `..._to_dict` suffix or `to_...dict` prefix+suffix pattern --
   covers every existing `to_json_dict`/`*_to_dict` wire-format serialiser in the codebase (12
   hit this on the real tree: `to_json_dict` x3, `to_dict` x1 plus `report_to_dict`,
   `change_report_to_dict`, `replay_diff_to_dict`, `rule_edit_to_dict`,
   `edit_proposal_to_dict`, `migration_effect_to_dict`, `self_permission_status_to_dict`,
   `decision_to_dict`). Caught and fixed a bug in my own first draft here: a regex using
   `re.match` with an unanchored `_to_dict$` alternative never matched anything but the
   literal string `"_to_dict"`, because `match()` anchors at position 0 -- silently exempted 0
   of the 12 real serialisers until caught by comparing the actual `--undeclared-types` output
   against expectation. Rewrote as a plain `str.endswith`/`startswith` check, which is also
   clearer.
2. `UNDECLARED_TYPES_OPEN_ENDED_EXEMPTIONS`: an explicit, empty allowlist
   (`"module:qualname"` strings) for a genuinely open-ended mapping (e.g. a parsed TOML
   table). Left empty -- no real function in the current tree needed it (checked for TOML-table
   parsers specifically; none matched the Dict[str, Any]/dict shape). Mechanism is in place
   and tested (`test_open_ended_allowlist_exempts_an_explicit_entry`) for when one is found.

**Report-only, never fails the build** (exit code untouched by this mode), per the ticket.

### Current count on the real tree, 2026-08-22 (report this, per ticket instruction)

```
=== --undeclared-types: 4 finding(s) (report-only -- does not fail the build) ===
examined 353 public function(s)/method(s); 12 exempt by serialiser-name convention,
0 exempt via explicit allowlist, 3 return an undeclared dict but are never called
outside their own module
  - config:164 load_config_file (annotated)
  - config:2222 config_sync_settings_from_sources (annotated)
  - rule_sort:488 parse_permissions_section_with_comments (annotated)
  - subagent:141 identify_current_agent (annotated)
```

Manually verified each of the 4 is a genuine cross-module call (grepped real call sites), not
a name-collision false positive:
- `load_config_file` (`-> dict`, config.py) -- called from `tools/installer.py`,
  `tools/rule_apply.py`, `permission_migration.py`.
- `config_sync_settings_from_sources` -- called from `auto_migrate.py`.
- `parse_permissions_section_with_comments` (`-> Dict`, rule_sort.py) -- called from
  `tools/config_access.py`, `tools/annotate.py`, `tools/maintenance.py`,
  `permission_migration.py`.
- `identify_current_agent` (`-> Dict[str, Any]`, subagent.py) -- called from
  `hook.py`'s `_agent_info_for`.

**Per the ticket's instruction: I did NOT fix these 4.** That is a separate decision for Arnon
-- flagging only, per "If the count is large, do NOT go fix them all."

`parse_hook_input` itself no longer appears in the findings (confirmed by a dedicated
regression test, `TestUndeclaredTypesOnTheRealTree.test_parse_hook_input_no_longer_appears`),
tying Part 1 and Part 2 together.

### Known limitation not engineered around (scope discipline)

`Optional[Dict[str, Any]]` return annotations are not recognised (only bare
`Dict[str, Any]`/`dict`/`Dict`). Checked: the two functions in the repo with that exact shape
(`_resolve_reporter_log_dir`, `_provenance_to_dict`) are both private, so this costs zero real
findings today. Left unhandled rather than adding recursion for a case with no current
instance -- can be added later if a public function needs it.

## The log_dir / extended_syntax literal-string sweep -- explicitly NOT done, per instruction

Re-measured, unchanged from the ticket's own count: `"log_dir"` literal -- 10 sites;
`"extended_syntax"` literal -- 4 sites (both `grep -rn` over `toolguard/`). Per Arnon's
instruction, did not touch either. My own read, for the record (not acted on):
- `"log_dir"`: this one reads as the SAME under-modelling pattern as `parse_hook_input` --
  it is a key repeatedly pulled out of `env_config: Dict[str, Any]` (itself returned by
  `toolguard.env_config.get_env_config()`, also `-> Dict[str, any]`). A dedicated
  `EnvConfig` dataclass, mirroring what this ticket just did for `PreToolUseEvent`, would be
  the natural next instance of the same fix -- but `get_env_config()`'s callers and blast
  radius were not surveyed (out of scope this ticket).
- `"extended_syntax"`: reads more like a standalone repeated key name than a
  crossing-a-dict-boundary symptom in the 4 sites I saw in passing -- each reads it off
  `env_config` too (same root cause as `log_dir` above), so it is really the SAME
  `EnvConfig`-shaped fix, not an independent literal to name as a constant.

Both are symptoms of the same one undeclared type (`get_env_config()`'s `Dict[str, Any]`), not
two separate constants-cleanup items -- consistent with Arnon's framing that a literals sweep
would be treating the symptom again. Left as a candidate for a *separate* ticket, not touched
here.

## Evidence-before-fixing.md applicability

This ticket is a pure internal type-modelling/tooling refactor -- no Bash/deny/allow matching
logic touched, zero permission-decision impact. The log-corpus procedure in
`.claude/rules/evidence-before-fixing.md` is designed for permission-relevant defects
(measuring how often a bypass shape fires in real traffic); it does not meaningfully apply to
a structural refactor with no decision-path change. Did not run a corpus count for this
reason -- flagging the reasoning explicitly rather than silently skipping the rule.

## Concurrency notes (three other agents were running against the same repo)

`tools/architecture_fitness.py` was being actively edited by the #100 agent (`--orphans`)
throughout this session -- confirmed live via two "file modified on disk since you last read
it" warnings during editing. Re-read the file before each subsequent edit rather than trusting
stale context. Final touches to shared scaffolding, all additive (no restructuring):
- Module docstring: added an `--undeclared-types` bullet next to the existing `--orphans` one,
  and a usage-example line.
- `from dataclasses import dataclass, field` -> added `asdict` (needed for JSON payload
  rendering).
- `PATH_AMBIENT_OWNERS`: added one entry (`("hook", "cwd")`) -- required by my OWN hook.py
  change, not by `--undeclared-types` itself.
- `main()`'s argparse block: one `add_argument("--undeclared-types", ...)`, inserted after the
  `--orphans` entry the other agent added.
- The `not any([...])` mode-required list and its error message: appended `args.undeclared_types`
  / `--undeclared-types`, alongside the `--orphans` entries already there.
- Dispatch block: one `if args.undeclared_types:` block, inserted after the other agent's
  `if args.orphans:` block.

No restructuring of the argument parser was needed -- both new modes fit the existing
one-flag-per-mode pattern additively. Ran `ruff format` on this shared file (in scope, since I
touched it) -- it also reformatted a couple of lines in the #100 agent's own code (their
`(SyntaxError, OSError)` except-tuple line-wrap and a dict-literal comprehension); this is
expected, deterministic, and idempotent, so no functional risk, but flagging it since it
touches code I did not author.

Did not touch `toolguard/compound.py`, `toolguard/config.py`,
`toolguard/parser/command_extractor.py`, or `toolguard/parser/multiline.py`, per instruction.
Did not run repo-wide `ruff format` -- only on the 4 files I changed.

## Files changed (4, all modifications, 0 new files)

- `toolguard/hook.py` (53 lines changed)
- `tools/architecture_fitness.py` (383 lines changed -- includes the #100 agent's concurrent
  `--orphans` work already present when I read/edited it)
- `test/unit/test_hook.py` (33 lines changed: updated `TestHookInputParsing` for attribute
  access, added `test_parse_returns_a_pretooluseevent_with_every_field_populated`)
- `test/unit/test_architecture_fitness.py` (184 lines added: `TestUndeclaredTypesCheck`, 7
  synthetic-fixture tests; `TestUndeclaredTypesOnTheRealTree`, 2 real-tree smoke/regression
  tests)

Well within scope-inflation guardrails (0 new files vs the 7-file caution line; 4 modified
files vs the 5-file caution line for non-trivial changes; combined 4 vs the 10-file line).

## Gates -- actual numbers

- `uv run python -m unittest discover -s test -t .`: **4000 tests, OK (expected failures=4)**
  (baseline was 3990 OK/expected failures=4; +10 from my new tests: 1 in test_hook.py, 9 in
  test_architecture_fitness.py).
- Empty-`$HOME`/`$XDG_CONFIG_HOME` variant: **4000 tests, OK (expected failures=4)**, matching.
- `uv run python tools/corpus_build.py --verify`: **"OK: no differences"** (6401 in-process +
  61 end-to-end cases) -- confirms Part 1 is behaviour-preserving.
- `uv run ruff check .` on the 4 changed files: all pass. `ruff format --check` on the 4
  changed files: already formatted (ran `ruff format` once mid-session on
  `tools/architecture_fitness.py` after the fix above; the other 3 files needed no
  reformatting).
- `uv run python tools/architecture_fitness.py --stdlib --ambient --layers --undeclared-types`:
  **exit 0**. `--layers`: all 78 modules mapped, no direction violations. `--stdlib`: PASS.
  `--ambient`: PASS (0 unowned reads) after the `PATH_AMBIENT_OWNERS` fix above.
  `--undeclared-types`: 4 findings, report-only (never affects exit code).

## Self-review

- Anti-pattern scan: no async/await, no threading, no new local imports introduced.
- Doc comments: short, on-thing-not-on-change, per the global comment-length rules. No ticket
  references left in docstrings (the `# TOO-45 #104` marker is a code-comment SECTION HEADER
  in `architecture_fitness.py`, matching the existing `# TOO-45 #100` convention the other
  agent already used for `--orphans` in the same file -- not a docstring).
- Requirements re-verified against the task recall note before writing this report: both parts
  done, both exemption categories built in, count reported, the 4 findings NOT fixed, the
  literals sweep NOT done, `.claude/compound.py`/`config.py`/parser files untouched, no
  repo-wide format, no commit/push.
- Existing-code check before implementing: confirmed via grep that `PreToolUseEvent` already
  existed (ticket 99) and `testing/sandbox.py` already used it for the inverse direction --
  reused it directly rather than reimplementing. For `--undeclared-types`, reused the existing
  `iter_source_files`/`relative_module_path` file-discovery helpers rather than re-walking the
  tree by hand.

## Timing (approximate -- first-call timestamp not captured precisely)

- Phase 1 (planning, reading rules/ticket/blast-radius survey): ~15 min
- Phase 2 (implementation, both parts + the ambient false-positive fix + the serializer-regex
  bug fix): ~25 min
- Phase 3 (tests, gates, self-review): ~10 min
- Total: roughly 50 minutes. Rough cost estimate (Sonnet 5, this session's token volume):
  low single-digit dollars -- no large file dumps, no long-running subprocess loops beyond the
  test suite itself (~60s x 3 runs + corpus verify ~16s).
