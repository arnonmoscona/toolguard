---
title: 85-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/85-estimate-predictions
---

# Ticket 85, chunk A — blinded touch-set prediction

Scope as instructed: creating `toolguard/claude_code_contract.py` and moving only the
**wire protocol** — hook payload field names, response field names, event names
(`tool_name`, `tool_input`, `hook_event_name`, `session_id`, `cwd`, `transcript_path`,
`hookSpecificOutput`, `hookEventName`, `permissionDecision`, `permissionDecisionReason`,
`additionalContext`, `PreToolUse`, `SessionStart`). Explicitly excluded from this estimate:
`STRIPPED_WRAPPERS` / matching-semantics constants, tool-registry material, and
documentation — the ticket names these as separate concerns, and the task brief assigns
them to later chunks.

## Reasoning

The ticket lists thirteen package modules that reference some part of the external
contract, but that list spans all three contract categories (wire protocol, stripped
wrappers, matching semantics), not just wire protocol. I had to guess, per module, which
category it plausibly touches, using only the one-line docstring in the inventory — I have
not read any of these files.

Modules I judge as wire-protocol-shaped (payload/response field names, event names):
`hook.py` (the PreToolUse entry point — the ticket's own worked example,
`create_hook_output`, lives here), `session_start.py` (a second hook entry point, for the
`SessionStart` event), `testing/sandbox.py` (constructs synthetic hook events for
experiments — a payload builder is exactly where field-name literals live),
`log_writer.py` (an audit trail over hook invocations, plausibly logging `tool_name`,
`tool_input`, `session_id`), `subagent.py` (identifies subagents, plausibly from
`transcript_path`), `tools/installer.py` and `tools/takeover_audit.py` (both plausibly
reference the `PreToolUse`/`SessionStart` event-name strings when writing or checking hook
registration in `settings.json`).

Modules I judge as NOT wire-protocol (matching semantics or native-config-schema instead,
so out of chunk A even though they're on the ticket's list of 13): `compound.py`,
`permission_resolution.py`, `auto_migrate.py`, `permission_migration.py`. `api.py` I put at
low confidence either way — it's the decision interface, which is nearer `RuntimeVerdict`
(a toolguard type) than to Claude's wire vocabulary, but I can't rule out a payload-field
reference from the docstring alone. `tools/environment_audit.py` I judge OUT (PYTHONPATH
shadowing, not hook I/O).

The ticket is explicit that "no bare contract literal survives anywhere else in the
package" is the goal — so I expect a MOVE (constants extracted, call sites rewritten to
import them), not a facade. See the dedicated section below.

Tests: the ticket explicitly defers the ~696 test-literal occurrences to a separate
decision ("do the package first"), so I predict most existing test files are UNCHANGED —
behavior is preserved, and test assertions check output values, not source-level literal
use. The two test changes I do expect come from structural completeness: a new module
needs its own test file (this repo's convention is one test file per module, no
exceptions I saw in the inventory), and `test_architecture.py` describes itself as testing
"module layering," which a new foundation-layer leaf module is likely to intersect.

## Production modified

| file | reason | confidence |
|---|---|---|
| `toolguard/hook.py` | Central wire-protocol module; builds `create_hook_output`, the ticket's own worked example. Stays in place but its literals become imports. | high |
| `toolguard/session_start.py` | Second hook entry point, owns the `SessionStart` event and its own `hookSpecificOutput`-shaped response. | high |
| `toolguard/testing/sandbox.py` | Builds synthetic hook payloads for experiments; payload field names are its raw material. | high |
| `toolguard/log_writer.py` | Audit trail over hook invocations; plausibly logs payload field values by name. | medium |
| `toolguard/subagent.py` | Subagent identification, plausibly keyed off `transcript_path`/`session_id`. | medium |
| `toolguard/tools/installer.py` | Agent-facing installer; plausibly writes the hook event name into `settings.json` hook registration. | medium |
| `toolguard/tools/takeover_audit.py` | Takeover invariant checker; plausibly checks hook registration event names. | low |
| `toolguard/api.py` | On the ticket's 13-module list, but its docstring reads as decision-interface, not wire-I/O — could be here for the response-field projection instead. | low |
| `.pyscn.toml` | New leaf module needs a layer entry (ticket says so explicitly) — I expect it added to `foundation`, alongside `constants`. | high |

## Production added

| file | reason | confidence |
|---|---|---|
| `toolguard/claude_code_contract.py` | The ticket's deliverable: the module itself, holding the wire-protocol constants (dated, with doc URL + anchor per entry). | high |

## Test modified

| file | reason | confidence |
|---|---|---|
| `test/unit/test_architecture.py` | Describes itself as testing module layering; a new foundation-layer leaf plausibly intersects an exhaustiveness check. | high |
| `test/unit/test_hook.py` | Huge central file for `hook.py`; behavior shouldn't change, but I can't rule out an import-shape or module-boundary assertion touching it. | low |
| `test/unit/test_session_start.py` | Same reasoning as `test_hook.py`, for the second entry point. | low |
| `test/unit/test_sandbox.py` | If `testing/sandbox.py`'s payload-building changes shape (not just literal source), this could need updates. | low |
| `test/unit/test_static_analysis_coverage.py` | Guards that pyscn can read the repo's source; a new module could need adding to an enumerated list. | low |

## Test added

| file | reason | confidence |
|---|---|---|
| `test/unit/test_claude_code_contract.py` | This repo's convention (visible throughout the inventory) is one test file per production module, with no exceptions I could find. | high |

## Files expected DELETED

None. This is a consolidation of scattered literals into a new module and an import
rewrite at call sites — not a module removal. No existing module loses its reason to
exist from chunk A alone.

## Concentration set

`toolguard/claude_code_contract.py` (new), `toolguard/hook.py`,
`toolguard/session_start.py`, `toolguard/testing/sandbox.py`,
`test/unit/test_claude_code_contract.py` (new). These five are where I'd expect the bulk
of the diff's substance to sit; everything else in the "modified" tables above is a
smaller, mechanical import-and-replace edit.

## Scope prediction

**IN chunk A**: the new `claude_code_contract.py` module populated with wire-protocol
constants only (payload fields, response fields, event names); the `.pyscn.toml` layer
entry for it; import-and-replace edits in the modules above that currently spell those
fields as bare literals; a new unit test file for the module; a likely edit to
`test_architecture.py` for layering completeness.

**OUT of chunk A** (explicitly, per the task brief): `STRIPPED_WRAPPERS` and the
not-stripped list; matching-semantics constants (word-boundary rule, `:*` equivalence,
assignment-stripping asymmety) — both of which I expect to touch `compound.py`,
`permission_resolution.py`, `auto_migrate.py`, `permission_migration.py` instead, in a
later chunk; tool-registry material (`tool_spec.py`); the `--contract` check in
`tools/architecture_fitness.py` (it needs the *whole* vocabulary populated to be
meaningful, not just the wire-protocol slice, so I don't expect it in chunk A even though
the ticket describes it as a natural consequence); the architecture-as-built.md section
and diagram; and the ~696 test-literal migration, which the ticket itself defers to a
separate decision.

## Move or re-export

**Prediction: a genuine MOVE, not a re-export facade.** The ticket's refinement is explicit
that "no bare contract literal survives anywhere else in the package" and that the import
edge itself ("references the contract... does not express it") is the deliverable being
optimized for. A re-export facade wouldn't produce that edge in any meaningful sense —
if the old modules kept their literals and the new module merely re-exported values
sourced from them, the dependency would point the wrong way (old modules would not import
the new one at all), and grepping the package for a bare contract string would still find
matches everywhere. That directly contradicts the ticket's stated goal.

So I predict every module I listed as "wire-protocol-shaped" above
(`hook.py`, `session_start.py`, `testing/sandbox.py`, `log_writer.py`, `subagent.py`,
`tools/installer.py`, `tools/takeover_audit.py`, possibly `api.py`) gets an added
`import toolguard.claude_code_contract` (or `from ... import NAME`) plus literal-to-name
replacements at each call site — not merely a new file with nothing else touched.

What a MOVE implies file-wise: all of the "Production modified" rows above are real edits
inside existing modules, each losing bare-string literals and gaining an import line, and
the new module is the sole remaining source of those literal values.

What a RE-EXPORT would instead have implied: only `claude_code_contract.py` appears as new
content, all "Production modified" rows above would collapse to zero or near-zero (the old
modules keep their existing literals untouched), and the new module's own content would be
built by importing *from* the old modules rather than the reverse — the shape
`toolguard/tools/project_root.py` already uses in this repo ("Re-export of the
project-root primitives implemented in :mod:`toolguard.path_utils`"), which is the pattern
this ticket is explicitly not choosing.

**Observable difference in the final diff**: a MOVE shows many small scattered edits (an
added import plus 1-3 line literal replacements) across 6-8 existing files, with the
package-wide count of bare contract literals dropping toward zero outside the new module.
A RE-EXPORT would show one new file and near-nothing else — no edits to `hook.py`,
`session_start.py`, etc. Given the ticket's explicit "no bare contract literal survives"
language, I predict the former, not the latter.