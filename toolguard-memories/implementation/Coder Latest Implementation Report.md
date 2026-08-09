---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-45
- coder-latest-implementation-report
---

# TOO-45 punch-list #10 -- ToolSpec -- implementation report

Branch `too-45`. Not committed -- Arnon does all git write operations.

## Summary

Added `toolguard/tool_spec.py` (foundation layer): a `ToolKind` enum, a frozen `ToolSpec`
dataclass (name, kind, payload_key, governed_by_default), a 5-entry static registry, and
derived views (`known_tool_names`, `governed_by_default`, `file_kind_tools`, `payload_key`).
`constants.GOVERNED_TOOLS`/`FILE_TOOLS` and `config_validation.KNOWN_SUPPORTED_TOOLS` now
derive from it under their existing names, so every existing importer (`api`, `tools/danger`,
`tools/mining`, `tools/log_harvest`, `tools/security_audit`, `tools/maintenance`,
`tools/transcript_harvest`, `hook`) keeps working unchanged. The three literal payload-key
reads the spec named (`hook.py` x2, `tools/transcript_harvest.py` x1) now resolve the key from
the registry instead of hardcoding `"file_path"`. `tools/installer.py:900`'s hardcoded
`("Read", "Write", "Edit")` tuple now derives from `file_kind_tools()`.

## Files changed

- `toolguard/tool_spec.py` (new) -- the registry.
- `test/unit/test_tool_spec.py` (new) -- pinning tests + payload-key resolution tests.
- `toolguard/constants.py` -- `GOVERNED_TOOLS`/`FILE_TOOLS` now derived.
- `toolguard/config_validation.py` -- `KNOWN_SUPPORTED_TOOLS` now derived.
- `toolguard/hook.py` -- `COMMAND_TOOLS` deleted (see below); two payload-key literals derived.
- `toolguard/tools/installer.py` -- the fifth copy (`installer.py:900`) derived.
- `toolguard/tools/transcript_harvest.py` -- payload-key literal derived.
- `test/verdict_corpus/fixture_loader.py` -- payload-key literal derived (see "look-alike vs
  oracle" below); also fixed a stale docstring reference to the deleted `decision.py`.
- `tools/architecture_fitness.py` -- comment only: fixed a stale cross-reference to
  `hook.FILE_PATH_TOOLS` (renamed at the source of this ticket) and stated *why* the constant
  stays independent, so the next reader doesn't "fix" the duplication away.
- `.pyscn.toml` -- added `tool_spec` to the foundation layer's package list.

## 1. Did the existing membership tests agree on normalisation?

**Case and the scoped `Tool(pattern)` form: yes, cleanly.** No site lowercases or otherwise
normalizes a tool name before comparing it against any of the three live sets; the one place
that strips a `Tool(pattern)` scope (`config_validation.extract_tool_name`) already runs before
every comparison against `KNOWN_SUPPORTED_TOOLS`/`governed_tools`, consistently. Confirmed with
`grep -n '\.lower()\|\.upper()'` near every tool-name comparison site -- none found outside
`danger.py`'s unrelated command-body lowercasing.

**But membership itself did not agree, on one tool.** `hook.COMMAND_TOOLS` included
`mcp__local-tools__checked_bash`; `config_validation.KNOWN_SUPPORTED_TOOLS` deliberately did
not, per an explicit comment on `test_toml_config.py:611` dating to the original repo migration
(`f0d49c9`, months before TOO-45): "`mcp__local-tools__checked_bash` is user-specific and
configured via `additional_supported_tools` in TOML, not hardcoded here." A third site,
`config.py:98`'s `_DEFAULT_IGNORED_ALLOW_PATTERNS`, independently corroborated the 5-tool
pattern (agreeing with `KNOWN_SUPPORTED_TOOLS`, not `COMMAND_TOOLS`). This was reported and
held before any derivation. The coordinator's resolution, verified independently before
applying: `hook.COMMAND_TOOLS` had exactly one occurrence in the whole tree -- its own
definition -- and `mcp__local-tools__checked_bash` appeared in production nowhere else. It was
dead code whose sixth member happened to be excluded everywhere else on purpose. **Deleted
`COMMAND_TOOLS` rather than deriving it.** The registry ended up holding exactly the 5 names
`KNOWN_SUPPORTED_TOOLS` already had, so no fifth `ToolSpec` field was needed and every
derivation is behaviour-identical to today, confirmed by the golden verdict corpus staying
byte-identical (`test_no_verdict_changed`, `test_no_sub_command_breakdown_changed`, both e2e
golden tests) and the full suite passing throughout (including a run against an isolated empty
`$HOME`/`XDG_CONFIG_HOME`).

## 2. How many lines would adding `NotebookEdit` now take?

**About 10 lines across exactly 2 files**, both new files added by this change:

- `toolguard/tool_spec.py`: one new `ToolSpec(...)` entry in `_REGISTRY` (~7 lines,
  ruff-formatted the same way as the existing 5).
- `test/unit/test_tool_spec.py`: the pinning tests are deliberately literal, so
  `test_known_tool_names_matches_prior_literal_set` (and `test_file_kind_tools_matches_prior_literal_set`
  if `NotebookEdit` is file-kind) need their expected sets updated (+1 line each) -- this is the
  pinning test doing its job, not friction.

No production call site changes: `constants.py`, `config_validation.py`, `hook.py`,
`tools/installer.py`, `tools/transcript_harvest.py` all read the registry, not a literal.
(Governing it by default, or exposing it without `additional_supported_tools`, remains a
separate, deliberately out-of-scope decision -- `governed_by_default=False` for a new entry
does not change `governed_tools()`'s resolution.) Note Claude Code's real payload key for
`NotebookEdit` is `notebook_path`, not `file_path` -- worth flagging for whoever eventually
does this, since `ToolKind.FILE` alone doesn't determine the key value, the registry entry does.

## 3. Further copies found, not listed in the spec

Two, both flagged and resolved with the coordinator before touching them:

- `test/verdict_corpus/fixture_loader.py:679` -- a fourth `"file_path" if tool in
  FILE_PATH_TOOLS else "command"` branch, in test scaffolding. **Derived** (now calls
  `tool_spec.payload_key`), because scaffolding that builds a payload but validates nothing has
  no independent detection value -- if production's key changed and this didn't, the corpus
  would silently replay the wrong payload and still pass. Also fixed a stale docstring
  reference to `decision.py`, deleted by an earlier TOO-45 item (`dbdd797`).
- `toolguard/config.py:98` `_DEFAULT_IGNORED_ALLOW_PATTERNS` -- textually derivable
  (`f"{name}(*)"` for each of today's 5 `KNOWN_SUPPORTED_TOOLS` names, same order), but **left
  alone**, per the coordinator: deriving it would couple takeover-mode's ignored-allow-pattern
  seed to registry membership, so adding a tool to the registry would silently change which
  native allow patterns takeover mode ignores -- a behaviour change hiding inside a
  deduplication. The two lists agreeing today is a coincidence of the current tool set, not a
  shared definition -- a **look-alike**, not a copy. Recorded here for the follow-up list with
  this reasoning attached, so it isn't "fixed" by someone re-deriving it later.

## 4. Duplication self-check

No tool-name membership set is defined twice. Final grep sweep (`GOVERNED_TOOLS`, `FILE_TOOLS`,
`KNOWN_SUPPORTED_TOOLS`, `COMMAND_TOOLS`, `_CANARY_FILE_TOOLS`, `_DEFAULT_IGNORED_ALLOW_PATTERNS`,
every `"file_path"` literal) confirms exactly one definition site per name, `COMMAND_TOOLS`
gone entirely, and `hook.FILE_PATH_TOOLS` remains the sole pre-existing alias
(`FILE_PATH_TOOLS = FILE_TOOLS`, already documented as such before this change).

## The corrected copy count, and the durable inventory

The ticket's premise was "four independent membership sets." Measured: **three live, one
dead** (`hook.COMMAND_TOOLS` had zero readers anywhere in the tree). This is the second
punch-list item in this series whose central evidence didn't survive measurement -- punch-list
#04 claimed 16 hand-rolled stderr writes where there were 8.

Final classification of every site touched or considered, by *purpose* (per the coordinator's
framing: derive scaffolding, duplicate oracles, and say which one a copy is):

| Site | Classification | Disposition |
|---|---|---|
| `constants.GOVERNED_TOOLS` | one concept, duplicated | now derived |
| `constants.FILE_TOOLS` | one concept, duplicated | now derived |
| `config_validation.KNOWN_SUPPORTED_TOOLS` | one concept, duplicated | now derived |
| `hook.COMMAND_TOOLS` | dead code (not a real fourth set) | deleted |
| `hook.py`:2 payload-key literals | one concept, duplicated | now derived |
| `tools/transcript_harvest.py`:1 payload-key literal | one concept, duplicated | now derived |
| `tools/installer.py:900` file-tools tuple | one concept, duplicated (5th copy) | now derived |
| `test/verdict_corpus/fixture_loader.py:679` | scaffolding (no independent detection value) | now derived |
| `tools/architecture_fitness.py:_CANARY_FILE_TOOLS` | independent oracle (drift detector) | **left duplicated**, comment now says why |
| `toolguard/config.py:_DEFAULT_IGNORED_ALLOW_PATTERNS` | look-alike (same values today, different concept -- takeover-mode semantics, not tool structure) | **left alone**, reasoning recorded here for follow-up |

## Verification

- Full suite: 2721 tests (2710 + 11 new), OK -- run twice more after the two post-review edits,
  including once against an isolated empty `$HOME`/`XDG_CONFIG_HOME`.
- Golden verdict corpus: byte-identical (`test_no_stale_or_missing_goldens`,
  `test_no_sub_command_breakdown_changed`, `test_no_verdict_changed`,
  `test_tracked_fields_unchanged_or_acknowledged`, and all e2e-golden equivalents), re-run after
  the `fixture_loader.py` edit too.
- `uv run python tools/architecture_fitness.py --layers`: clean (completeness + direction).
- `uv run ruff format .` / `uv run ruff check .`: clean, whole repo.

## Self-review

- Anti-pattern scan: no async/await, no threading, no local (in-function) imports introduced;
  all new imports are module-level. No unused imports (ruff check confirms).
- Every new/changed function carries a short docstring; no ticket narrative left in code
  comments (references to "TOO-45 punch-list #10" only where they mark *why a name lives here*,
  matching the style of neighbouring pre-existing comments in `constants.py`).
- `test/unit/test_tool_spec.py` follows this repo's Given/When/Then docstring convention.

## Out of scope, confirmed untouched

- `NotebookEdit` -- not added (see #2 above for the cost estimate).
- `governed_tools()`'s resolution, `additional_supported_tools`' semantics, and every default:
  unchanged.
- No behaviour change anywhere: golden corpus proves it for the runtime decision path;
  `test_tool_spec.py`'s pinning tests prove it for the three derived sets themselves.

## Timing (approximate -- no wall-clock instrumentation at task start)

- Phase 1 (planning, spec/ticket read, code investigation, first stop-and-report on the
  `COMMAND_TOOLS`/`KNOWN_SUPPORTED_TOOLS` disagreement): roughly 20-25 minutes.
- Coordinator round-trip + second investigation (the `_CANARY_FILE_TOOLS` independence
  question): roughly 10 minutes.
- Phase 2 (implementation, all files): roughly 15-20 minutes.
- Phase 3 (verification bar, twice; self-review; this report): roughly 10-15 minutes.
- Total: roughly 60-70 minutes of wall clock. Cost estimate at Sonnet pricing for this token
  volume (several long tool-output reads, two multi-file edit passes, one large test run
  captured to a scratch file): on the order of $1.50-$2.50 total; not separately itemized per
  phase since no per-call token accounting was captured during the run.


---

# Fix pass -- code review follow-up (M1, M2, minors, test gap)

Same branch, still uncommitted. This section covers the fix pass requested against
`toolguard-memories/latest-code-review-report.md`'s two Majors and six Minors.

## What changed, by finding

**M1 -- `governed_by_default()` named a set that wasn't a default.** Renamed throughout:
`ToolSpec.governed_by_default` field -> `ToolSpec.is_builtin`; the derived view (folded into
M2's frozenset conversion) -> `tool_spec.BUILTIN_TOOLS`. Both docstrings now say explicitly
what the flag is (built-in knowledge) and what it is NOT (the effective governed set --
`Configuration.governed_tools()`, defaulting to `('Bash',)`, never reads this registry).

**Checked whether `constants.GOVERNED_TOOLS` should follow the rename -- it does, no live
bug found.** Read all four real importers before deciding:

- `security_audit.py:353` -- `for tool in sorted(GOVERNED_TOOLS): find_confusing_interactions(...)`
- `maintenance.py:184,715` -- `sorted(GOVERNED_TOOLS)` as the default tool list for maintenance
  scans and clarity annotations
- `transcript_harvest.py:281` -- `if tool not in GOVERNED_TOOLS: continue` filtering transcript
  tool_use items

Every one iterates "every tool toolguard knows how to analyze/harvest", never "the current
project's configured governed set" -- confirmed by reading each call site's surrounding logic,
not just the review's assertion. **No live bug**: nothing downstream needed the effective
governed set and got the builtin set instead. Since the exact same false-default-implication
risk M1 flagged applies one layer up (a future author could as easily wire
`governed_tools()`'s fallback to `constants.GOVERNED_TOOLS` as to the old `tool_spec` name),
renamed it too: `constants.BUILTIN_TOOLS`, updating the 4 production import sites
(`maintenance.py`, `security_audit.py`, `transcript_harvest.py`) + `test_tool_spec.py`. Grepped
`README.md`, `docs/`, and `toolguard/api.py` first -- zero hits, so this isn't part of the
documented public surface and carries no external-compat risk.

**M2 -- one registry, two view semantics.** `tool_spec.py`'s three derived views are now
module-level frozensets computed once (`KNOWN_TOOL_NAMES`, `BUILTIN_TOOLS`, `FILE_KIND_TOOLS`),
not zero-arg functions. `payload_key()` is the only remaining function (it takes an argument,
so it's a lookup, not a view). `constants.py` now re-exports the SAME frozenset objects
(`BUILTIN_TOOLS = _BUILTIN_TOOLS`, imported under a private alias to avoid self-assignment) --
pinned with `assertIs`, not just `assertEqual`, in `test_tool_spec.py`, so a future change back
to independent construction fails loudly. `installer.py` was the one live-call site (M2's other
half); it now reads the module-level `FILE_KIND_TOOLS` constant directly instead of calling a
function per invocation. `tool_spec.py`'s module docstring dropped the "every derived view
picks it up automatically" dynamism claim -- it now describes what the module actually does:
a static registry, its structural facts, and which pieces stay configurable and don't derive
from it.

**Minors, all done:**

- `constants.py` docstring: "imports nothing from toolguard" -> "imports only other
  foundation modules" (it imports `tool_spec`).
- `tool_spec.py` module docstring no longer claims `Configuration.governed_tools()` consumes
  the registry -- it doesn't; only `config_validation.KNOWN_SUPPORTED_TOOLS` does. Rewritten
  to say so plainly.
- Half-converted dispatch fixed at both sites exactly as the review's snippet proposed:
  `fixture_loader.py:680` and `transcript_harvest.py:226` now do
  `spec = TOOLS_BY_NAME.get(tool); key = spec.payload_key if spec else "command"` --
  the `else` is now genuinely an unknown-tool fallback, not a second definition of the command
  key. (`transcript_harvest.py` needed `TOOLS_BY_NAME` imported in place of `payload_key`;
  `FILE_TOOLS` import dropped, no longer needed there.)
- `hook.py:734` and `:1107` (now `:734`/`:1108` after a 5-line net change) interpolate the
  resolved key: `reason=f"No {key} provided in tool input"`. For the registry's current
  contents this renders identically to before (`payload_key` still resolves file-kind tools to
  `"file_path"`), so `test_hook_eval.py:166`'s existing `assertIn("No file_path provided", ...)`
  needed no edit -- confirmed by running it unchanged. Added new tests (see below) that swap in
  a different key so the interpolation itself is actually exercised, not just coincidentally
  correct.
- `test_tool_spec.py`'s `assertRaises(Exception)` -> `assertRaises(dataclasses.FrozenInstanceError)`.
- `TOOLS_BY_NAME` now has a duplicate-name guard: built via `_index_by_name()`, which raises
  `ValueError` on a repeated `name` instead of the dict comprehension silently keeping only the
  last entry. Tested directly (construct two `ToolSpec`s named `"Bash"`, assert the raise) and
  indirectly (`len(TOOLS_BY_NAME) == len(_REGISTRY)` against the real registry).

**Explicitly not done (not in the fix-pass prompt's itemized list, so left alone to avoid
scope creep):** m6 (the private `_tool_payload_key` import alias in `hook.py`), s1 (collapsing
the `FILE_PATH_TOOLS` -> `FILE_TOOLS` -> `FILE_KIND_TOOLS` alias chain), s4 (typing style,
`typing.FrozenSet`/`Mapping` -- though note `tool_spec.py` was already rewritten with builtin
generics as a side effect of the M2 change, since the frozensets needed types anyway; the
one remaining `typing` import was dropped entirely, so s4 is now accidentally moot).

## Closing the test gap (item 4)

Added, beyond the fixes above:

- `TestRegistryIntegrity` in `test_tool_spec.py`: the count-match test, a non-empty-payload-key
  test over every real registry entry, and the duplicate-name-raises test.
- `test_constants_module_constants_are_the_same_frozensets`: `assertIs` (not `assertEqual`) on
  both `constants.BUILTIN_TOOLS`/`FILE_TOOLS` against their `tool_spec` originals -- this is
  the test that would have caught M2 if it had existed before.
- **Seam-pinning tests in each real consumer's existing test file**, all using
  `unittest.mock.patch.dict("toolguard.tool_spec.TOOLS_BY_NAME", {...})` to inject a `ToolSpec`
  for `"Read"` with a payload key of `"target_path"` instead of `"file_path"`, then asserting
  the consumer genuinely resolves through the registry rather than a hardcoded literal:
  - `test_hook_eval.py` -- `TestResolveEventPayloadKeySeam` (2 tests) against `_resolve_event`.
  - `test_hook.py` -- 2 new tests in `TestHandleFilePathToolAuditWiring` against
    `_handle_file_path_tool` (also exercises `@patch("toolguard.hook.log_command")` so no real
    logging happens).
  - `test_tools_transcript_harvest.py` -- 1 new test in `TestToolExtraction` against
    `_command_for_tool` directly.
  - `test_verdict_corpus.py` -- new `TestBuildHookPayloadPayloadKeySeam` class (2 tests) against
    `fixture_loader.build_hook_payload`, including the unregistered-tool fallback-to-`"command"`
    case.

  This is deliberately the technique the review's own m5 suggested ("swap in a file-kind tool
  with a different payload key and drive `hook._resolve_event`,
  `transcript_harvest._command_for_tool` and `fixture_loader.build_hook_payload`"), adapted for
  the fact the registry is now intentionally static (M2): rather than making production code
  swappable, the tests inject via `mock.patch.dict` on the shared `TOOLS_BY_NAME` dict object,
  which every consumer references by import, so one patch point exercises the real dispatch
  path in each of the four call sites without touching production code's snapshot semantics.

Net new tests: 10 (test_tool_spec.py +3, test_hook_eval.py +2, test_hook.py +2,
test_tools_transcript_harvest.py +1, test_verdict_corpus.py +2).

## Verification

- Baseline confirmed green before starting: 2721 tests, OK.
- Full suite after all fixes: **2731 tests, OK** (2721 + 10 new).
- Golden verdict corpus re-run standalone: all 9 tests in `test_verdict_corpus.py` pass,
  byte-identical (`test_no_verdict_changed`, `test_no_sub_command_breakdown_changed`, both
  e2e-golden equivalents included).
- `uv run python tools/architecture_fitness.py --layers`: clean (completeness + direction).
- `uv run ruff format .`: 1 file reformatted (a line-collapse in `test_hook_eval.py`, cosmetic).
- `uv run ruff check .`: all checks passed, whole repo.
- Grepped the whole tree for `GOVERNED_TOOLS`, `governed_by_default`, `file_kind_tools`,
  `known_tool_names` after the rename: zero stragglers in production code; only historical
  references remain in memory/report files (expected) and in `test_tool_spec.py`'s own prose
  ("equals the prior GOVERNED_TOOLS", describing what's being pinned, not a live symbol).
- Grepped for any further hand-written `("Read","Write","Edit")`-shaped tool tuples: found
  only `rule_sort.py`'s `tool_priorities` dict (a sort-order assignment, a different concept,
  not membership -- correctly out of scope) and test-file literal config content (input data,
  not derived-set duplication).

## Self-review

- Anti-pattern scan: no async/await, no threading, no local (in-function) imports introduced.
- No unused imports (ruff check confirms; `FILE_TOOLS`/`payload_key` imports were dropped from
  `transcript_harvest.py` and `fixture_loader.py` where the m3 fix made them unnecessary).
- Doc-drift sweep: fixed the docstrings immediately adjacent to every renamed symbol
  (`transcript_harvest.py`'s "governed tools" -> "known (builtin) tools" in two docstrings that
  would otherwise have gone stale from the `BUILTIN_TOOLS` rename in the same function bodies).
- Every new test carries a Given/When/Then docstring per `.claude/rules/testing.md`.

## Timing and cost (fix pass only, approximate)

No wall-clock instrumentation was captured at task start for this fix pass either (same gap
as the original implementation pass) -- the phase headers shown during the run used
uninstrumented estimates; the one real timestamp taken mid-session (`date`) read 16:12 local,
well past what the estimates implied, so the phase-by-phase numbers below are ordinal (planning
happened first, then implementation, then review) rather than reliable durations.

- Planning (read review + spec + every affected source file, decided the GOVERNED_TOOLS rename
  question): the largest share of the work -- this fix pass required reading ~15 files before
  the first edit, more than the edits themselves.
- Implementation (8 production files + 5 test files): a single continuous pass, no
  false starts or reverts.
- Self-review/verification: three full-suite runs (baseline, post-production-fix,
  post-test-additions) plus targeted single-file runs after each test-file edit.
- Rough cost estimate at Sonnet pricing for this token volume (multiple full-file reads,
  three full-suite log captures, one multi-file grep sweep): on the order of $1.50-$2.50,
  comparable to the original implementation pass; not separately itemized per phase for the
  same reason as before -- no per-call token accounting was captured during the run.


---

# TOO-45 -- default governed tools: Bash-only -> Bash/Read/Write/Edit -- implementation report

Branch `too-45`. Not committed -- Arnon does all git write operations. Task recall:
`toolguard/TOO-45/TOO-45 governed_tools default change - coder task recall`.

## Summary

`Configuration.governed_tools()` (`toolguard/config.py`) now falls back to
`toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS` (`('Bash', 'Read', 'Write', 'Edit')`, registry
order) instead of the literal `("Bash",)` when no level in the hierarchy configures
`governed_tools`. `tool_spec.ToolSpec.is_builtin`'s docstring corrected (it now IS the
governance default, not "NOT the effective governed set"). Sourced from the punch-list #10
registry as instructed, not a fifth hand-written literal.

## Files changed

- `toolguard/tool_spec.py` -- new `DEFAULT_GOVERNED_TOOLS: tuple[str, ...]` constant (registry
  order, not the unordered `BUILTIN_TOOLS` frozenset); module docstring and `is_builtin` field
  docstring corrected.
- `toolguard/config.py` -- `governed_tools()` returns `DEFAULT_GOVERNED_TOOLS`; docstring
  updated.
- `toolguard/constants.py` -- fixed a stale comment on `BUILTIN_TOOLS` claiming the effective
  default "is not derived from this registry" (it now is, via `config.py`).
- `test/unit/test_configuration.py` -- updated four assertions in
  `TestGovernedAndTakeoverDelegation` and `TestRulesDirectoryMergeSemantics` that pinned the
  OLD default literal; see "Test changes" below for why this is pinning-value maintenance, not
  weakening.
- `test/unit/test_tool_spec.py` -- new `TestDefaultGovernedTools` class: pins
  `DEFAULT_GOVERNED_TOOLS == ('Bash', 'Read', 'Write', 'Edit')` and that its content matches
  `BUILTIN_TOOLS` (the task's explicit "test pinning the new default" ask).
- `test/verdict_corpus/README.md`, `configs/hard_deny.toml`, `configs/pattern_forms.toml`,
  `configs/override_breadth/project/.claude/toolguard_hook.toml` -- fixed stale comments citing
  the old default literal to justify their explicit `governed_tools` setting; reworded to
  "independent of whatever the default happens to be" (still correct, no longer stale). README
  also corrected a fixture count (three fixtures declare it explicitly, not two --
  `override_breadth` was missing from that sentence, unrelated to this change but caught while
  editing the same paragraph).
- `docs/configuration.md` -- Step 2 rewritten to state the new default up front and that no
  config entry is needed for it; "Recommended tools to govern" tables annotated
  "(governed by default)" / "(NOT governed by default)"; the `additional_supported_tools`
  illustration snippet now shows the *correct* pattern for adding a custom command tool
  (extending the default set explicitly, since setting `governed_tools` replaces rather than
  extends the default) instead of a `governed_tools = ["Bash"]` placeholder that no longer
  demonstrated anything useful; added an "Upgrade note" callout ahead of "Keeping toolguard up
  to date" describing the upgrade consequence for a project that never configured
  `governed_tools` (see "Upgrade-consequence documentation" below).
- `docs/install.md` -- Phase 2's `governed_tools` guidance rewritten: the built-in four no
  longer needs an explicit recommendation-to-set, only the "ask about MCP command tools" half
  survives as an actionable step.
- `AGENTS.md` -- "Key facts an agent should not get wrong" section updated: states the new
  default explicitly and corrects "govern... not just Bash" (now backwards -- Read/Write/Edit
  are already governed; only non-built-in command tools need an explicit entry).
- `technical-notes.md` -- fixed the `governed_tools()`-UNION section's stale `('Bash',)`
  default literal.

## Golden verdict corpus: verified, zero goldens changed

`toolguard.api.decide()` (the in-process corpus's entry point, `cases.jsonl`/`goldens.jsonl`,
~6400 cases) never consults `governed_tools()` at all -- confirmed in its own docstring
("The governed-tools list is NOT checked here"). Only the end-to-end corpus
(`e2e_cases.jsonl`/`e2e_goldens.jsonl`, replaying through the real hook subprocess, 61 cases)
enforces it.

Ran `uv run python tools/corpus_build.py --verify --strict-prose` (in memory, writes nothing)
after the code change: **"OK: no differences"** across both corpora, hard AND tracked fields.
Traced why: every e2e case exercising `Read`/`Write`/`Edit` already lives under a fixture that
sets `governed_tools` explicitly (`hard_deny`, `pattern_forms`, `override_breadth`) -- this was
deliberately done when those fixtures were authored, specifically so their file-tool cases stay
governed independent of the ambient default (their own comments said so, citing the OLD
default -- now corrected, see above). No fixture pairs a `Read`/`Write`/`Edit` e2e case with a
fixture that leaves `governed_tools` unset. Net effect: this is a genuine no-op for the corpus,
not a gap in verification -- no goldens file was regenerated or touched.

**Correction to the task brief's estimate**: the brief said "19 of 24 corpus configs do not set
`governed_tools`" and expected some e2e cases to move. The actual fixture count is 16 (not 24 --
possibly counting something else, e.g. distinct config *files* rather than fixtures, since
several fixtures are multi-file), and empirically zero e2e cases move, for the structural reason
above. Flagging this as a correction, not a shortfall in verification -- I ran `--verify
--strict-prose` (which fails on ANY tracked-field difference, not just hard ones) and it passed
clean.

## Test changes -- why this is pinning maintenance, not weakening

Four existing assertions literally pinned the production default value under test
(`config.governed_tools()`'s no-configuration fallback), which the ticket's whole point is to
change:

- `test_governed_tools_default_when_unconfigured`, `test_governed_tools_tolerates_non_list_value`,
  `test_governed_tools_ignores_native_layers`: asserted `("Bash",)`; the default itself is the
  literal thing under test, so these were updated to the new default value with matching
  Given/When/Then docstring edits.
- `test_rules_dir_scalars_have_zero_effect_end_to_end`: this one needed more than a literal swap.
  It proves a rules-directory file's scalar settings (including a "sneaky"
  `governed_tools = ["Write"]`) have zero effect on resolution. Since `"Write"` is now already
  part of the default, that value could no longer distinguish "leaked through" from "is just the
  default" -- the assertion would have passed even if the filtering bug it guards against were
  reintroduced. Changed the sneaky value to `mcp__jetbrains__execute_terminal_command` (never
  in the default) so the test still proves what its docstring claims, and added a sentence to
  the docstring explaining why that specific tool was chosen.

No test was weakened -- each change either updates a pinned literal to match a legitimately
changed production default, or (the fourth case) strengthens the fixture so it keeps proving
what it always claimed to prove given the new default.

## Upgrade-consequence documentation

Placed a callout in `docs/configuration.md` (the "Upgrade note" ahead of "Keeping toolguard up
to date" -- the section a user reads specifically when upgrading) explaining: an existing
project that never set `governed_tools` and never wrote file-path permission patterns will,
after upgrading, have `Read`/`Write`/`Edit` evaluated against its rules for the first time and
fall through to `no_match_fallback` (silent / warning / deny depending on that project's
setting), with the one-line fix (`governed_tools = ["Bash"]`) to restore the old behaviour.

**Did not create a version-numbered `release-notes/*.md` file.** `pyproject.toml` is at 0.5.1,
which predates this punch-list, and no release-notes file exists yet for whatever version ships
the full TOO-45 overhaul -- creating an orphan release note for an unreleased, unnumbered version
mid-ticket would be premature relative to this project's own cadence (version bump + release
notes happen at the ticket's actual pre-push wrap-up, per global CLAUDE.md, not per punch-list
item). Flagging explicitly: **this upgrade note is release-notes-worthy content** and should be
pulled into whatever `release-notes/0.x.y.md` file gets written when TOO-45 ships.

## Config validation's `governed_tools` fallback -- investigated, left alone, flagged

`config_validation.py`'s "ungoverned tool" advisory-warning check has its own
`config.get("governed_tools", ["Bash"])` fallback (a comment says "defaults to ['Bash']").
Investigated whether this needed updating too: it does not, because it is dead code on the real
call path. `Configuration.validation_issues()` builds its own `merged_config` dict with
`"governed_tools": []` always present (even when unconfigured, per its own merge loop) before
calling `validate_permissions(merged_config)`, so the `.get(..., ["Bash"])` default in
`config_validation.py` never actually fires there -- the key is always present, just sometimes
empty. This is a separate, pre-existing mechanism from `Configuration.governed_tools()` (it
reads raw layer content directly, not the resolved effective default), unrelated to this
change, and left untouched to avoid scope creep on an unrelated latent quirk. Flagging it here
rather than silently ignoring it.

## Verification

- Baseline (before any change): 2731 tests, OK.
- Full suite after all changes: **2733 tests, OK** (2731 + 2 new in `TestDefaultGovernedTools`).
- Golden verdict corpus: `tools/corpus_build.py --verify --strict-prose` -- "OK: no differences"
  (both corpora, hard and tracked fields), run twice (once right after the code change, once
  again after all doc edits).
- `uv run python tools/architecture_fitness.py --layers`: clean (completeness + direction) --
  confirms `config` legally importing the new `tool_spec` constant (both in `foundation`,
  `config` already allowed to import `foundation`).
- `uv run ruff format --check .` / `uv run ruff check .`: clean, whole repo.

## Self-review

- Anti-pattern scan: no async/await, no threading, no local (in-function) imports introduced.
  One new module-level import (`toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS` in `config.py`),
  alphabetically placed with the existing `toolguard.*` imports.
- No unused imports (ruff check confirms).
- Doc-drift sweep: grepped the whole repo (`docs/`, `README.md`, `AGENTS.md`, `llms.txt`,
  `technical-notes.md`, `test/verdict_corpus/`) for the old default literal
  (`('Bash',)` / `["Bash"]` "when unset" phrasing) after the code change; every hit that made a
  default-value CLAIM was corrected. Hits that were just illustrative config content (e.g.
  `test_toml_config.py`'s `governed_tools = ["Bash"]` fixture, deliberately narrowing) or an
  unrelated concept (a `--tool NAME` CLI flag default, `tools/maintenance.py`'s `tools=['Bash']`
  test parameter) were left alone -- confirmed by reading each site's context, not just the grep
  hit.
- Every new/changed test carries a Given/When/Then docstring per `.claude/rules/testing.md`.

## Unrelated finding, flagged for Arnon -- NOT fixed (out of scope, needs a decision)

**Five multi-file verdict-corpus fixtures' `.claude/toolguard_hook.toml` files are gitignored
and therefore never committed**, discovered while investigating why `--verify` showed zero diffs
(wanted to confirm the comparison was meaningful). `.gitignore:7` is a bare `.claude` pattern,
written for the top-level project `.claude/` symlink -- but a bare gitignore pattern (no leading
or embedded `/`) matches the basename at ANY depth, so it also swallows
`test/verdict_corpus/configs/{realistic,ask_provenance,override_breadth,hierarchy_conflict,
parse_failure}/{home,project}/.claude/toolguard_hook.toml` -- 10 files, confirmed absent from
`git ls-tree -r HEAD` (present only in this and presumably every other contributor's local
working tree, invisible to `git status` because they're ignored rather than merely untracked).
This corpus's own README calls itself "the load-bearing safety guard for the TOO-45
permission-engine architecture refactor" -- a fresh clone of this repo is currently missing 10 of
its fixture files entirely. Did not fix: touches `.gitignore` (needs a decision on the right
fix -- narrow the pattern, add negations, or restructure the fixture layout) and requires `git
add`-ing files git currently ignores, both outside this punch-list's scope and outside a
coder subagent's authority (git write operations are Arnon's). Worth its own quick ticket.

## Timing and cost (approximate)

- Phase 1 (task capture, code investigation -- `tool_spec.py`/`config.py`/`api.py`/
  `config_validation.py` reading, verdict-corpus README + fixture reading, baseline suite run):
  ~20 minutes.
- Phase 2 (implementation -- code change, 4 test fixes, 1 new test class, corpus comment fixes,
  documentation sweep across 6 files): ~30 minutes (includes a brief plan-mode interruption
  mid-session with no content change, handled per the harness's own instructions).
- Phase 3 (verification -- 4 full suite runs, 2 corpus `--verify` runs, architecture fitness,
  ruff, the gitignore investigation): ~15 minutes.
- Phase 4 (this report, task recall cross-check): ~5 minutes.
- Total: ~70 minutes wall clock. Rough cost estimate at Sonnet pricing for this token volume
  (several full-file reads, four full-suite log captures, one multi-file grep sweep, one corpus
  investigation with a large parser-noise stdout): on the order of $1.50-$2.50; not separately
  metered per phase.
