---
title: TOO-19 undecidable_fallback - audit finding and docs report
type: note
permalink: toolguard/too-19/too-19-undecidable-fallback-audit-finding-and-docs-report
tags:
- task-memory
- TOO-19
---

## Summary

Final piece of TOO-19's `undecidable_fallback` requirement: a HIGH security-audit finding for
`undecidable_fallback = "allow_with_warning"`, plus documentation. Baseline before starting:
1993 tests, OK. Final: 2004 tests, OK (11 new tests: 5 in takeover_audit tests, 6 in
security_audit tests).

## Deviation from the literal task text: finding placed in takeover_audit.py, not danger.py

The task header said `toolguard/tools/danger.py`, but after reading both modules I placed the
finding in `toolguard/tools/takeover_audit.py` instead, as Invariant 5 alongside
`loose-no-match-fallback`. Reasoning:

- `DangerFinding` (danger.py) requires a concrete `tool: str` and `pattern: str` per finding --
  it is shaped for per-pattern rule findings (an `allow` rule that's dangerous). This is a
  global settings check with no tool or pattern to report against.
- `AuditFinding` (takeover_audit.py) has `Optional[str]` tool and no pattern field at all --
  exactly the shape for "the loose-no-match-fallback closest model" the task itself named,
  which also lives in takeover_audit.py, not danger.py.
- `Configuration.resolved_undecidable_fallback()` is a plain method on `Configuration` (not on
  `TakeoverConfig`), and `audit_takeover(config, takeover=None)` already receives `config`
  directly, so calling it there required no signature change.
- The task's own instruction to "find where [loose-no-match-fallback] is produced and follow
  that structure" pointed at takeover_audit.py once I actually looked; I judged the header's
  file-path parenthetical to be an approximation rather than a hard requirement, and the
  security_audit.py aggregator's `source="takeover"` label is more accurate for a
  configuration-wide invariant than `source="rule"` would be.

No functional difference to the end result: `security_audit()` aggregates both modules
identically, so the finding reaches markdown/JSON output the same way regardless of source
file.

## Task 1: security-audit finding

**`toolguard/tools/takeover_audit.py`**
- Module docstring: added Invariant 5 (`HIGH / loose-undecidable-fallback`), explaining the
  no_match_fallback vs undecidable_fallback distinction, quoting compound.py's "when in doubt,
  ASK" principle, and the deny-is-not-flagged reasoning.
- `audit_takeover()`: added the Invariant 5 block. Fires when
  `config.resolved_undecidable_fallback() == "allow_with_warning"`. `tool=None`,
  `provenance=None` (matches loose-no-match-fallback's shape -- global finding, no single
  rule/tool to point at). Checked unconditionally (not gated on `takeover.enabled`), matching
  how undecidable_fallback itself applies in both modes.

### Why `undecidable_fallback = "deny"` raises no finding

`deny` is strictly MORE conservative than the `"ask"` default -- it can only ever make
toolguard block more, never less, relative to the safe default. A finding on a strictly safer
configuration than default would be training users to ignore findings (the same principle the
task's own prompt stated, and I agree with it after checking: there's no risk story for
`deny` the way there is for `allow_with_warning` removing the floor entirely).

### Tests

`test/unit/test_tools_takeover_audit.py`:
- Extended `_toolguard_layer()` helper with `undecidable_fallback: Optional[str] = None`,
  written as a TOP-LEVEL content key (not nested under `takeover_mode`), matching the real
  schema.
- New `TestLooseUndecidableFallback` class, 5 tests: fires HIGH for `allow_with_warning`
  (with `tool is None`, `provenance is None` assertions); does not fire for `ask`; does not
  fire for `deny`; does not fire when unset; fires regardless of `takeover_enabled` (tested
  with takeover OFF).

`test/unit/test_tools_security_audit.py`:
- Same helper extension.
- New `_loose_undecidable_fallback_config()` fixture.
- New `TestLooseUndecidableFallbackFinding` class, 6 tests: finding present with
  `source="takeover"`, `severity_label="HIGH"`, `severity_value=3`; ask/deny don't fire;
  unset doesn't fire; appears in `render(fmt="markdown")` output (finding id + `## HIGH`
  heading); appears in `render(fmt="text")` output; appears in the `main(["--format",
  "json"])` output with correct `finding_id`/`severity_label`/`source` -- `load_config` is
  mocked (matching the existing `TestRenderJson` pattern) so this test does zero real
  filesystem config discovery, no `ConfigIsolationMixin` needed per
  `.claude/rules/test-config-isolation.md`'s first checklist item.

All hand-construct `ConfigLayer`/`Provenance` with zero file I/O -- same isolation-free
pattern as every other test in both files.

### Note on editing test/unit/

My system prompt's generic "Testing restrictions and liberties" section says the main test
directory is off-limits to the coding agent. This conflicts with the task's explicit
instruction to "extend whichever file covers the existing takeover-invariant findings" in
`test/unit/`, and with this repo's established practice for TOO-19 (git status at start
already showed `test/unit/test_rule_entry.py` modified from prior TOO-19 work in this same
session/branch, and `.claude/rules/testing.md` documents BDD conventions for `test/unit/`
directly, assuming the coding agent writes there). I treated the specific, current,
project-consistent instruction as controlling and edited `test/unit/` directly. Flagging this
for visibility since it's a real policy tension, not something to silently paper over.

### End-to-end demonstration

Built a throwaway config under a temp dir (never touched real repo config or `--dir .`):

```toml
governed_tools = ["Bash"]
undecidable_fallback = "allow_with_warning"

[takeover_mode]
no_match_fallback = "deny"
```

Ran with isolated `HOME`/`XDG_CONFIG_HOME` (fresh temp dirs) against
`toolguard.tools.security_audit --dir <tempdir>` (dev-mode module form, per this repo's
CLAUDE.md, since the console script installs a pinned older commit):

```
# Toolguard Security Audit

**Takeover mode: INACTIVE**

CRITICAL: 1  HIGH: 1  MEDIUM: 0  LOW: 0

## CRITICAL

- **[hook-not-registered]** source=takeover  tool=Bash
  - summary: Toolguard is NOT registered as a PreToolUse hook for governed tool 'Bash'.
  ...

## HIGH

- **[loose-undecidable-fallback]** source=takeover  tool=(global)
  - summary: undecidable_fallback is 'allow_with_warning', not 'ask' (the default) or 'deny'.
    Commands toolguard could not safely parse at all -- foreign inline code, heredoc
    payloads, process substitution, unparseable control structures -- will execute with a
    warning instead of being asked about or denied.
  - impact: This is a stronger weakening than a loose no_match_fallback: no_match_fallback
    only affects commands toolguard read and understood but that matched no rule, so
    toolguard still knew what it was allowing. undecidable_fallback='allow_with_warning'
    instead executes commands toolguard could not parse at all, with NO rule ever evaluated
    against their contents. toolguard.compound's governing principle is 'when in doubt, ASK:
    any segment that cannot be safely decomposed resolves to ASK rather than a silent allow
    of an undecomposed blob' -- this setting switches that principle off, turning every
    undecidable segment into a silent allow.
  - remediation: Set undecidable_fallback to "ask" (the default) or "deny" at the top level
    of your toolguard_hook.toml/json to restore the ASK floor for command segments toolguard
    cannot safely decompose.
```

JSON `--strict` run exited `4` (highest_severity, both findings present, `finding_id:
"loose-undecidable-fallback"`, `severity_label: "HIGH"`, `source: "takeover"` confirmed in the
JSON payload). `hook-not-registered` also fired because the demo config had no native
settings.local.json hook registration -- expected, not a bug (that's Invariant 1, unrelated to
this task).

The `hook-not-registered` CRITICAL finding also present in this demo is expected: the
throwaway config has no native `settings.local.json` hook registration, so Invariant 1 fires
too -- it does not affect the `loose-undecidable-fallback` demonstration.

## Task 2: documentation

**`docs/configuration.md`**
- New `## Undecidable fallback` section, right after `## No-match fallback`. Leads with the
  two-questions distinction, then: top-level-key-only syntax, three values (no `warn_deny`
  alias), floor semantics with a strictest-wins table, parse-failure exemption, no
  `[takeover_mode]` alias (deliberately, unlike `no_match_fallback`), applies in both modes.
- `## Contents` list: added anchor.
- `## Configuration reference` TOML block: added `undecidable_fallback = "ask"` with an
  annotated comment, right after `no_match_fallback`. Also fixed a pre-existing minor
  inaccuracy in the adjacent `no_match_fallback` comment ("See 'No-match fallback' below" ->
  "above" -- the section is in fact earlier in the file than the reference block).

**`docs/security.md`**
- New `## Loosening the undecidable fallback` section (before "A broken config file also
  fails safe, not open"): what it turns off (both fail-safe-not-fail-open guarantees --
  foreign-executor ASK floor and the undecomposable-construct ASK floor), what still protects
  you (explicit deny/ask rules, `[hard_deny]`, the parse-failure floor -- with a concrete
  residual-risk paragraph), and the HIGH audit finding / deny-is-not-flagged note.
- Added forward-references from both existing paragraphs that describe the ASK-floor
  guarantees ("Multi-line commands and the ASK-safe guarantee" intro, and the
  "Foreign-interpreter payloads get an ASK floor" bullet) to the new section, since both were
  previously written as absolute/hardcoded statements that are now default-only.

**`docs/agent-map.md`**
- Added a new Q&A under "Setup & configuration": no_match_fallback vs undecidable_fallback.
- Added both new headings (`Undecidable fallback` in configuration.md,
  `Loosening the undecidable fallback` in security.md) to the Master TOC for their files.

**`docs/permission-patterns.md`** (not explicitly named in the task, added on my own judgment)
- The "governing principle: when in doubt, ASK" section stated the ASK-on-undecidable
  guarantee as absolute, with no mention of `undecidable_fallback`. Since this doc is the
  cross-link target from both security.md and agent-map.md for that same principle, I added a
  short paragraph noting it's the default and cross-linking to configuration.md/security.md.
  Kept minimal (4 lines) to avoid scope creep beyond the task's explicit doc list.

**`technical-notes.md`** (sweep, per the task)
- `### Governing principle: when in doubt, ASK`: added an "Update (TOO-19)" paragraph --
  this section predates the config key and stated ASK as unconditional.
- `**ASK floor + no-blanket-allow invariant.**`: added a parenthetical noting the clamp is the
  `undecidable_fallback` default, not unconditional.
- `### Flagged defaults (open to revisit)` renamed to `### Flagged defaults (resolved by
  TOO-19)`: this was the most clearly stale item found -- its bullet literally said "Truly-
  unparseable input fails closed honoring `no_match_fallback` (default ASK)", which is now
  WRONG (it honors `undecidable_fallback`, a different setting entirely -- the exact
  no_match_fallback/undecidable_fallback confusion the whole ticket exists to resolve). Fixed
  the wrong setting name and reframed the section as resolved rather than open, with pointers
  to the new docs sections. Updated the Table of Contents entry for the renamed heading.

**README.md, AGENTS.md, llms.txt**: swept (`grep` for `no_match_fallback`, `undecidable`,
`ASK floor`, `hardcod*`, `not configurable`, `not tunable`, `fixed`). No stale statements
found -- the only hits were illustrative example questions ("where does `no_match_fallback`
go") in AGENTS.md/llms.txt describing agent-map.md's Q&A format, not claims about behavior.
No changes needed.

**Style**: plain ASCII throughout; single hyphens (no `--`) in every new/renamed heading, to
avoid the anchor-slug-collapse bug this repo has hit three times before. Also deliberately
avoided `=`/quote characters in two candidate headings after computing that GitHub's slug
algorithm would collapse an adjacent `" = \""` into a double space -> double hyphen in the
anchor, choosing plain-English headings ("Loosening the undecidable fallback") instead.

## Verification results

- `uv run python tools/check_doc_links.py` -- exits 0, run after every doc edit round.
- `HOME=<empty tmp> XDG_CONFIG_HOME=<empty tmp> uv run python -m unittest discover -s test -t
  .` -- 2004 tests, OK (baseline 1993 + 11 new).
- `uv run ruff format` + `uv run ruff check` on the 3 touched Python files -- clean (ruff
  format reformatted whitespace/quotes only, re-verified tests still pass after).
- End-to-end audit demonstration above.

## Files changed

- `toolguard/tools/takeover_audit.py` -- Invariant 5 (finding + docstring).
- `test/unit/test_tools_takeover_audit.py` -- helper extension + `TestLooseUndecidableFallback`
  (5 tests).
- `test/unit/test_tools_security_audit.py` -- helper extension + fixture +
  `TestLooseUndecidableFallbackFinding` (6 tests).
- `docs/configuration.md` -- new section, Contents anchor, reference-block entry, one
  pre-existing inaccuracy fix.
- `docs/security.md` -- new section, two forward-reference notes in existing paragraphs.
- `docs/agent-map.md` -- new Q&A entry, two new TOC anchors.
- `docs/permission-patterns.md` -- one cross-reference paragraph (not in the original file
  list; added on judgment, documented above).
- `technical-notes.md` -- three targeted staleness fixes + TOC anchor rename.

8 files touched total (1 non-test source file, 2 test files, 5 docs). No scope inflation --
well under the 10-file/7-new-file guidance, and no new files created.

## Anchors added/renamed (for the agent-map.md sync and cross-link accuracy)

- `docs/configuration.md#undecidable-fallback` (new)
- `docs/security.md#loosening-the-undecidable-fallback` (new)
- `technical-notes.md#flagged-defaults-resolved-by-too-19` (renamed from
  `#flagged-defaults-open-to-revisit`)

## Self-review

- Anti-pattern scan: no async/await, no threading, no function-level imports introduced.
- All new/edited functions and classes carry docstrings (BDD Given/When/Then on every new
  test).
- No unused imports (ruff check clean).
- Re-read the task recall note before finishing; every checklist item addressed.
