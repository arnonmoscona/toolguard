---
title: TOO-19 Phase 1 Implementation Plan (additionalContext Feature)
type: note
permalink: toolguard/too-19/too-19-phase-1-implementation-plan-additional-context-feature
tags:
- task-memory
- TOO-19
---

> **CORRECTIONS 2026-07-27 -- read before using this plan.** Phase 0 is now implemented,
> so the dependency below is satisfied, but the plan was written against the *planned*
> API and several names in it never existed:
>
> - **`_parse_permission_entry` does not exist.** It shipped as
>   `normalize_entry(perm, is_native=...)` in the new module `toolguard/rule_entry.py`
>   (alongside `entries_for_tool`, `merge_entries`, `RuleEntry`). Substitute throughout.
> - **`KNOWN_ENRICHMENT_KEYS` already exists** in `rule_entry.py` as an intentionally
>   empty `frozenset()` -- item 1 below ("extend the known-keys registry") is literally
>   just adding `"additionalContext"` to it plus the `str`-only value constraint.
> - **Structured entries are single-line only.** Anything in this plan implying a
>   multi-line `{...}` form is void; see the Phase 0 plan's status banner for why (TOML
>   1.0 / `tomllib` conformance is a hard requirement).
> - Test-file names below were already flagged UNCONFIRMED and remain so -- Phase 0 added
>   `test/unit/test_rule_entry.py`, `test_rule_sort.py`, and `test_architecture.py`, which
>   this plan predates.
>
> Otherwise the design (drop `alwaysInject`, decision-maker-only injection, toolguard
> configs only, 500-word cap dropping whole paragraphs) is unchanged and still Arnon's.

Status: DRAFT, awaiting Arnon's review. Depends entirely on
[[TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing)]] being implemented
and reviewed first -- this plan assumes `RuleEntry`, `_parse_permission_entry`, and the
`*_entries` fields on `ToolPatternLayer` already exist. See
[[TOO-19 Structured Rule Entries - Rule-Match Enrichment]] for the full requirements/
decisions history this implements. Several test-file names below are marked
UNCONFIRMED -- verify against the actual repo during implementation rather than trusting
this note blindly, per this session's own memory-hygiene practice.

---

# TOO-19 Phase 1: The `additionalContext` Feature

## Context

Phase 0 (separate plan/memory) makes the config-parsing layer safe for structured rule
entries but doesn't yet DO anything with them. Phase 1 is the actual feature: when a rule
carrying `additionalContext` is the deciding match for a tool call, that text is injected
into Claude's context via the `PreToolUse` hook's `additionalContext` output field
(confirmed this session to work regardless of the `allow`/`ask`/`deny` decision).

Locked-in decisions from this session (see the requirements memory for full history):
`alwaysInject` dropped (only the final decision-maker match injects); allow/deny/ask all
support structured entries uniformly; toolguard-config-files only, never native
`settings.json`; target all governed tools (Bash + Read/Write/Edit) if generalizing
doesn't prove too costly, Bash prioritized; all-allow compound commands accumulate
context as one paragraph per contributing rule, deduped by identical text, capped at 500
words total, dropping whole paragraphs (never truncating) on overflow; `log_writer.py`
gets a new field recording what was injected.

## Gap found while planning this phase: native-settings restriction -- RESOLVED, folded into Phase 0a

We decided structured entries should be toolguard-config-only, never interpreted from a
native Claude `settings.json` layer. Phase 0a's plan originally did NOT gate on
`layer.is_native` -- `_parse_permission_entry` would have happily parsed a dict-shaped
entry found in a native layer. **Folded into Phase 0a (2026-07-24, per Arnon's
instruction to apply the implied change before he reviews):** `_parse_permission_entry`
now takes the layer's `is_native` flag and rejects dict-shaped entries when True (warning
issue, plain strings unaffected), wired into both `permission_layers()` and `hard_deny()`.
See [[TOO-19 Phase 0 Implementation Plan (Rule Access + TOML Chunk Parsing)]]'s "Native-
layer gating" design subsection and TDD increments 1-2 for the concrete shape. Item 1
below (originally "add the native-layer rejection fix") is now just the known-keys
registry addition -- the gating itself is Phase 0a's responsibility, not Phase 1's.

## Design

### 1. Extend the known-keys registry

Add `"additionalContext"` to Phase 0a's known-keys set, constrained to `str` values only
(not just any flat-hashable primitive -- it's injected as text, so a bool/int value should
be a validation error, not silently stringified).

### 2. File-path tools (Read/Write/Edit) -- the more-ready path

`resolve.py::resolve_file_path_permission_detailed` returns a `FileResolution` (decision,
reason, override, provenance). Add an `additional_context: Optional[str]` field. Populate
it by looking up the winning pattern in the matching `*_entries` tuple (from Phase 0a) for
its kind/level, mirroring how `Configuration._provenance_for_pattern` already looks up
provenance by exact pattern-string match -- an analogous `_entry_for_pattern` helper (or
reuse the same lookup, extended to also return the `RuleEntry`). This requires
`Configuration.resolve_permission_detailed`'s `ResolvedDecision` (currently `decision,
reason, provenance, override`) to gain a 5th field carrying the winning entry's
`additionalContext`, threaded through from the per-level decider.

### 3. Bash tools -- the compound.py path (more work)

Today `resolve_one: Callable[[str], Tuple[str, str]]` threads a plain `(decision, reason)`
2-tuple through `compound.py`'s `_resolve_leaf` / `_combine_strictest`. This needs to grow
to carry a per-leaf `additional_context: Optional[str]` alongside decision and reason
(e.g. `(decision, reason, context)`, or a small named tuple/dataclass if that reads
cleaner). Consequences:
- `resolve_bash_permission_detailed` (`resolve.py`) and `Configuration.resolve_permission_detailed`
  populate the context the same way as increment 2, for the Bash matching path.
- `_combine_strictest`: for the deny/ask case (always exactly one strictest-wins leaf, per
  the earlier decision that only all-allow compounds can have plural decisive matches),
  the winning leaf's context passes through unchanged -- no accumulation logic needed
  there.
- For the all-allow case, route the collected per-leaf contexts through the new
  accumulation helper (next section) instead of just building the "cmd -> pattern"
  reason-string summary as today.
- `check_compound_permission`/`resolve_compound_permission`'s public return type grows
  from `(decision, reason)` to `(decision, reason, additional_context)` -- a signature
  change that ripples up to `hook.py`'s call sites.

### 4. Accumulation helper (new, pure function in `compound.py`)

```
_accumulate_contexts(contexts: List[str], max_words: int = 500) -> Optional[str]
```
- Dedupe by exact text equality, preserving first-seen order (handles the same rule
  matching multiple sub-commands in one compound).
- Join surviving contexts as separate paragraphs (blank line between).
- Greedy first-fit in original match order: running word count; a paragraph that would
  push the total over `max_words` is dropped WHOLE (never truncated mid-sentence). Order
  of which paragraph(s) get dropped when over budget doesn't matter (Arnon: "it's a
  corner case").
- Returns `None` when there are no contexts at all, so callers can omit the
  `additionalContext` key entirely rather than emit an empty string.

### 5. `hook.py` wiring

- `create_hook_output(decision, reason, additional_context=None)`: add
  `"additionalContext": additional_context` to the `hookSpecificOutput` dict only when
  non-empty.
- Update every call site (the Bash decision path ~line 741-775, the file-path decision
  path ~line 819-850, plus the other `create_hook_output(...)` call sites already
  identified this session) to pass the resolved context through where one exists; error
  paths keep passing `None`.

### 6. `log_writer.py` audit extension

Extend `log_command`'s signature with an `additional_context: Optional[str] = None`
param, written to the log entry alongside the existing `matched_rule` field, so a session
is debuggable after the fact ("why did Claude get this nudge"). Open detail to settle
during implementation, not a blocking design question: whether to log the full text or a
length-capped preview, to avoid unbounded log bloat from a 500-word paragraph block on
every matching invocation.

### 7. Documentation

README gets a new section for the `{match = "...", additionalContext = "..."}` syntax:
example, the toolguard-config-only restriction, and the compound-command accumulation
behavior (paragraph-per-rule, 500-word cap, drop-whole-paragraph overflow).

### Explicitly deferred, not in Phase 1's scope

- Authoring/synthesizing NEW structured entries via toolguard's own tooling (e.g.
  maintenance suggesting `additionalContext` for a confusing rule, or security-audit
  auto-proposing one) -- Phase 0b already deferred synthesizing brand-new structured TOML
  text to "Phase 1, if/when needed"; this plan does not build that either. A rule author
  hand-writes the TOML. Worth its own future ticket if wanted.
- Any special maintenance/security-audit SKILL-level surfacing of which rules carry
  `additionalContext` (beyond the safety guarantees Phase 0a already provides). Phase 1
  increment 8 below is a verification pass only, not a features pass.

## TDD increments (same discipline as Phase 0: one increment per feature-coder dispatch,
reviewed before the next; full suite green + ruff clean after each)

1. Known-keys registry: add `additionalContext` (str-only). (Native-layer rejection is now
   handled by Phase 0a, see the resolved gap note above -- no longer part of this
   increment.) Tests extend `test_configuration.py`/`test_toml_config.py` (per Phase 0a's
   routing).
2. File-path resolution: `ResolvedDecision`/`FileResolution` gain `additional_context`;
   `resolve_file_path_permission_detailed` populates it from the winning entry. Test file
   TBD-confirm (likely `test_configuration.py` alongside `resolve_permission_detailed`
   coverage, or a dedicated `resolve.py` test file -- UNCONFIRMED, verify at
   implementation time).
3. Bash/compound path: grow `resolve_one`'s return shape; thread context through
   `_resolve_leaf`; deny/ask single-winner passthrough. Tests extend `test_compound.py`.
4. `_accumulate_contexts` pure helper: dedup, 500-word cap, whole-paragraph-drop overflow,
   `None` for empty input. Standalone unit tests (new tests in `test_compound.py` or a
   small dedicated section there).
5. Wire increment 4 into `_combine_strictest`'s all-allow branch. Tests extend
   `test_compound.py`: multi-leaf all-allow compound with 2+ enriched rules produces the
   accumulated paragraphs; same rule matching 2 leaves dedupes to one paragraph; enough
   enriched matches to exceed 500 words drops whole paragraphs rather than truncating.
6. `hook.py` wiring: `create_hook_output` gains the param; call sites updated; JSON output
   includes `additionalContext` only when present. Test file TBD-confirm (hook.py's
   existing test suite -- UNCONFIRMED name, verify at implementation time).
7. `log_writer.py` extension. Test file TBD-confirm (UNCONFIRMED name, verify at
   implementation time).
8. Maintenance/security-audit verification pass (not a features pass): confirm both
   skills still run cleanly and report sensibly against a config containing enriched
   rules now that `additionalContext` is actually consumed, not just safely ignored.
9. README documentation.

## Verification

- `uv run python -m unittest discover -s test -t .` green after every increment.
- `uv run ruff format .` / `uv run ruff check .` clean.
- End-to-end manual check: a config with an enriched Bash allow rule for `grep`
  (`additionalContext` nudging toward `ag`); invoke the hook with a matching `grep`
  command; confirm the JSON output's `hookSpecificOutput.additionalContext` contains the
  expected text.
- Manual check: a compound command matching 2+ enriched allow rules produces multiple
  paragraphs, correctly deduped/capped.
- Manual check: a structured entry placed in a native `settings.json` layer is NOT
  interpreted as enriched (confirms the native-restriction gap fix from this plan).
