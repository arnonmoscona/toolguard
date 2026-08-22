# Toolguard Technical Notes

**Audience: primarily AI agents working on toolguard's own codebase, secondarily human
toolguard maintainers/developers digging into design rationale.** If you're a toolguard
*user* looking for how to configure or run it, you want the [docs/](docs/) guides instead --
start from [README.md](README.md#documentation). This file is deep design rationale: why a
decision was made, what alternatives were rejected and why, and low-level implementation
detail that doesn't belong in user-facing docs.

Sections are grouped by the ticket that did the work (`TOO-8`, `TOO-15`, `TOO-17`, ...),
most of which map to a specific subsystem -- use the table of contents below to jump straight
to a topic; you don't need the ticket history to use it, the ticket ID is just there for
anyone cross-referencing against the project's own tracker.

## Table of contents

- [Subagent Identification Workaround](#subagent-identification-workaround)
  - [The Problem](#the-problem)
  - [What Doesn't Work](#what-doesnt-work)
  - [The Solution: Transcript Parsing](#the-solution-transcript-parsing)
  - [Implementation Details](#implementation-details)
  - [Concurrency Considerations](#concurrency-considerations)
  - [Limitations](#limitations)
  - [Future Considerations](#future-considerations)
  - [Related Issues](#related-issues)
- [Hierarchical Configuration and Resolution (TOO-8 Phase 2)](#hierarchical-configuration-and-resolution-too-8-phase-2)
  - [Discovery hierarchy](#discovery-hierarchy)
  - [More-specific-wins permission resolution](#more-specific-wins-permission-resolution)
  - [Project-root-relative paths](#project-root-relative-paths)
  - [Hard-deny safety valve (TOO-8 Phase 3)](#hard-deny-safety-valve-too-8-phase-3)
  - [Rules directories: XDG and legacy paths, and shadowing](#rules-directories-xdg-and-legacy-paths-and-shadowing)
- [Logging streams, conflict logging, and provenance (TOO-8 Phase 4)](#logging-streams-conflict-logging-and-provenance-too-8-phase-4)
  - [Four separate log streams (one file per concern)](#four-separate-log-streams-one-file-per-concern)
  - [Conflict logging -- allow-over-deny overrides only](#conflict-logging----allow-over-deny-overrides-only)
  - [Provenance threaded into resolution reasons](#provenance-threaded-into-resolution-reasons)
  - [Change-detecting discovery diagnostic (M2, TOO-19)](#change-detecting-discovery-diagnostic-m2-too-19)
  - [Single source of truth for the both-formats warning (M1)](#single-source-of-truth-for-the-both-formats-warning-m1)
  - [Single source of truth for tool-wrapper stripping](#single-source-of-truth-for-tool-wrapper-stripping)
- [Non-permission cross-level resolution (TOO-8 Phase 5)](#non-permission-cross-level-resolution-too-8-phase-5)
  - [Scalars and `no_match_fallback` -- more-specific-wins](#scalars-and-no_match_fallback----more-specific-wins)
  - [`undecidable_fallback` vs `no_match_fallback` -- a deliberate asymmetry](#undecidable_fallback-vs-no_match_fallback----a-deliberate-asymmetry)
  - [`governed_tools` and takeover pattern lists -- UNION across all levels](#governed_tools-and-takeover-pattern-lists----union-across-all-levels)
  - [`takeover_mode.enabled` -- single-owner with fail-safe-on-conflict](#takeover_modeenabled----single-owner-with-fail-safe-on-conflict)
- [SessionStart conflict alerting (TOO-8 Phase 6)](#sessionstart-conflict-alerting-too-8-phase-6)
  - [Separate entry point](#separate-entry-point)
  - [Two detection sources](#two-detection-sources)
  - [Why dynamic conflicts come from the log](#why-dynamic-conflicts-come-from-the-log)
  - [Nag-every-session semantics](#nag-every-session-semantics)
  - [Stdout as session context](#stdout-as-session-context)
  - [Output format](#output-format)
  - [Resilience](#resilience)
- [Multi-line Bash decomposition (TOO-17)](#multi-line-bash-decomposition-too-17)
  - [The defect](#the-defect)
  - [Governing principle: when in doubt, ASK](#governing-principle-when-in-doubt-ask)
  - [Grammar-first, with a light AST -- no hand-rolled parsing](#grammar-first-with-a-light-ast----no-hand-rolled-parsing)
  - [`compound.py`'s shape: pure functions, no callbacks (TOO-45)](#compoundpys-shape-pure-functions-no-callbacks-too-45)
  - [How deep we go -- and why not deeper](#how-deep-we-go----and-why-not-deeper)
  - [Lexical pre-pass vs. grammar](#lexical-pre-pass-vs-grammar)
  - [Heredocs, the sink sentinel, and executor classification](#heredocs-the-sink-sentinel-and-executor-classification)
  - [Command substitution: validated, but no placeholder (yet)](#command-substitution-validated-but-no-placeholder-yet)
  - [Flagged defaults (resolved by TOO-19)](#flagged-defaults-resolved-by-too-19)
- [Maintenance and audit tooling (TOO-15 Phase 2)](#maintenance-and-audit-tooling-too-15-phase-2)
  - [Library-first, thin-skill seam](#library-first-thin-skill-seam)
  - [Corpus harvesting is opt-in, not automatic](#corpus-harvesting-is-opt-in-not-automatic)
  - [One report, two audiences -- `--format json` is the agent sidecar](#one-report-two-audiences------format-json-is-the-agent-sidecar)
  - [Structured remediation is a conservative, mechanical fix](#structured-remediation-is-a-conservative-mechanical-fix)
  - [The shared EditProposal model, and one edit primitive](#the-shared-editproposal-model-and-one-edit-primitive)
  - [As-if-enacted review: `--edits` vs `--migrations`](#as-if-enacted-review---edits-vs---migrations)
  - [Apply is preview-first and gated](#apply-is-preview-first-and-gated)
  - [Flagged gap (open) -- cross-project blast radius](#flagged-gap-open----cross-project-blast-radius)
  - [Multi-pass maintenance: SKILL.md orchestrator + `passes/` + a JSON state artifact](#multi-pass-maintenance-skillmd-orchestrator--passes--a-json-state-artifact)
  - [Certify-by-staging: author by AI, certify by tool](#certify-by-staging-author-by-ai-certify-by-tool)
  - [Corpus-replay candidate validation (`--replay-candidate`)](#corpus-replay-candidate-validation---replay-candidate)
  - [Prior-decision ledger (`decision_ledger.py`)](#prior-decision-ledger-decision_ledgerpy)
  - [Layer promotion certified by a live two-level HOME-staged audit](#layer-promotion-certified-by-a-live-two-level-home-staged-audit)
  - [CLI mode summary](#cli-mode-summary)
- [Isolated experiment sandbox (TOO-19)](#isolated-experiment-sandbox-too-19)
- [Shadowed-hook detection and install hardening (TOO-19)](#shadowed-hook-detection-and-install-hardening-too-19)
  - [Why the two footguns need different flags](#why-the-two-footguns-need-different-flags)
  - [`toolguard/install_provenance.py` -- placement rationale](#toolguardinstall_provenancepy----placement-rationale)
  - [The clean-tree predicate (stale-install detection)](#the-clean-tree-predicate-stale-install-detection)
  - [The SessionStart gate: only inside toolguard's own repo](#the-sessionstart-gate-only-inside-toolguards-own-repo)
  - [The audit predicate: `PYTHONPATH` content, not process provenance](#the-audit-predicate-pythonpath-content-not-process-provenance)
  - [Installer hardening, and its one real risk](#installer-hardening-and-its-one-real-risk)

## Subagent Identification Workaround

### The Problem

When a pre-tool-use hook runs, it needs to know whether the command is being executed by the main agent or by a subagent (like `feature-coder`). This is important for:
- Logging: Knowing which agent executed which command
- Future: Per-subagent permission configuration

### What Doesn't Work

**Approach 1: Using session_id or transcript_path**

The hook receives `session_id` and `transcript_path` from Claude Code. Initial investigation revealed that these values are **identical** for both main agent and subagents:

```
Main agent:     session=82c81e97-7657-4e8a-bde5-f0ebe4a9736a
Subagent:       session=82c81e97-7657-4e8a-bde5-f0ebe4a9736a  (same!)
```

This is by design in Claude Code's architecture. Subagents share the parent's session and write to the same transcript file. See [GitHub Issue #7881](https://github.com/anthropics/claude-code/issues/7881) for discussion.

**Approach 2: Echo self-announcement**

We tried having agents run an echo command to announce themselves:
```bash
echo "starting sub-agent: feature-coder"
```

This doesn't work because:
1. The echo runs through the hook itself, creating a chicken-and-egg problem
2. By the time we see it, we're already processing the announcement command

### The Solution: Transcript Parsing

Since main agent and subagents share the same transcript file, we can parse it to determine context.

**Key insight**: When a subagent is running, there will be an "open" Task tool_use entry in the transcript - one that has no corresponding tool_result yet.

**Transcript structure** (JSONL format):
```json
// Assistant calls Task tool
{"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "toolu_ABC", "name": "Task", "input": {"subagent_type": "feature-coder", "description": "..."}}]}}

// ... subagent executes commands ...

// When subagent completes, result appears
{"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "toolu_ABC", "content": "..."}]}}
```

**Algorithm** (`toolguard/subagent.py`):
1. Read the last 200 lines of the transcript file
2. Parse JSONL entries (skip malformed lines from concurrent writes)
3. Find all Task tool_use entries with their `tool_use_id` and `subagent_type`
4. Find all tool_result entries and map by `tool_use_id`
5. Work backwards through Task uses
6. The most recent Task without a result (or with result before the task entry) = current subagent

**Why this works**: Subagent execution is synchronous. While inside a subagent, no tool_result for that Task exists yet in the transcript.

### Implementation Details

**File**: `toolguard/subagent.py`

**Key functions**:
- `read_transcript_tail(path, max_lines=100)`: Efficiently reads last N lines
- `parse_jsonl_lines(lines)`: Parses JSONL, handles malformed lines gracefully
- `find_task_tool_uses(entries)`: Extracts Task calls with subagent_type
- `find_tool_results(entries)`: Maps tool_use_id to result index
- `identify_current_agent(transcript_path)`: Main entry point, returns context dict

**Return value**:
```python
{
    'agent_type': 'main' | 'subagent',
    'subagent_name': None | 'feature-coder' | etc.,
    'subagent_description': None | 'task description',
    'tool_use_id': None | 'toolu_ABC...'
}
```

**Edge cases handled**:
- Empty transcript: Returns main agent context
- Malformed JSONL lines: Skipped (can happen with concurrent writes)
- Content as string vs list: Some transcript formats vary; both handled
- No transcript_path provided: Returns main agent context

### Concurrency Considerations

**Multiple Claude Code instances**: Each Claude Code instance gets its own unique session_id and transcript file. The transcript_path is passed to the hook by the invoking instance, so concurrent instances are properly isolated:

```
Instance A: transcript = ~/.claude/projects/.../session-A-uuid.jsonl
  └─ Subagent A1: uses same transcript (session-A-uuid.jsonl)

Instance B: transcript = ~/.claude/projects/.../session-B-uuid.jsonl
  └─ Subagent B1: uses same transcript (session-B-uuid.jsonl)
```

Commands from Instance A (or its subagents) read only `session-A-uuid.jsonl`, while Instance B reads only `session-B-uuid.jsonl`. The transcript sharing problem is only *within* a single instance (main agent shares with its subagents). Across instances, isolation is maintained.

### Limitations

1. **Race condition window**: There's a tiny window where the transcript might not be fully flushed. Reading the last 200 lines provides buffer.

2. **Nested subagents**: If subagent A spawns subagent B, only the innermost (most recent open Task) is identified. This is the correct behavior for our use case.

3. **Performance**: Reading and parsing the transcript on every hook invocation has some overhead. For typical usage this is negligible (~1-5ms).

### Future Considerations

If Claude Code adds native subagent identification to the hook input (e.g., an `agent_context` field), this workaround can be removed. Until then, transcript parsing is a reliable solution.

### Related Issues

- GitHub Issue #7881: session_id shared between main and subagents
- GitHub Issue #10052: Feature request for native subagent identification in hooks

## Hierarchical Configuration and Resolution (TOO-8 Phase 2)

### Discovery hierarchy

Toolguard discovers configuration across a hierarchy of directories rather than
just the project and the user level. Starting from the project root (the nearest
ancestor with `pyproject.toml` or `.git`), it walks UP TO and INCLUDING the
user's home directory `~`, collecting configs from every ancestor that has a
`.claude/` subdirectory. The walk stops at `~` for a project located under
`~`, or at the filesystem root for a project that is not.

Within each `.claude/` directory the same within-level priority applies as
before: `toolguard_hook.local.{toml,json}`, `settings.local.json`,
`toolguard_hook.{toml,json}`, `settings.json` (TOML preferred over JSON, with a
warning when both exist).

Each level carries a **specificity** index: 0 = project (most specific),
increasing with distance up the tree; the user level `~/.claude` is always the
least specific. `~/.claude` is ALWAYS included as a level even when the project
is not located under `~`, preserving "user config always applies".

**Toggle:** `hierarchical_configuration` (a top-level key in a `toolguard_hook`
file) is read ONLY from the project-level config; it defaults to `true`. When
`false`, only the project and user levels are used (the pre-Phase-2 behaviour).
The fixed-bootstrap rule -- read the project level first to learn the toggle,
then decide traversal -- avoids the circularity of letting an ancestor vote on
whether ancestors are read.

`CLAUDE_SETTINGS_PATH` still forces single-file mode and bypasses the hierarchy.

### More-specific-wins permission resolution

Permission decisions use **more-specific-wins** instead of a flattened global
deny-first. Levels are evaluated MOST-SPECIFIC -> LEAST-SPECIFIC. Within a level,
deny-first applies (a deny match denies; otherwise an allow match allows). The
FIRST level that produces ANY match decides, and the cascade stops there. If no
level matches anything, the result is a fail-closed DENY.

This applies uniformly to:
- Bash command tools.
- Each sub-command of a compound Bash command, resolved independently through
  the full level cascade; the compound is allowed iff every sub-command is.
- File-path tools (Read/Write/Edit).

The level cascade is orchestrated by
`permission_resolution.resolve_command_permission`/`resolve_file_path_permission`
(TOO-45 D1a; fed by
`Configuration.permission_levels_with_provenance(tool)` through a narrow,
duck-typed query surface -- the engine module never imports `toolguard.config`
itself). Pattern
MATCHING stays in `permissions.py`/`compound.py` (and the file-path matcher in
`hook.py`); those provide a per-level
`decide(allow, deny) -> (decision, reason, matched_pattern) | None` callable.
A single-level config behaves identically to the old deny-first model, so there
is one resolution path with no legacy/dual code.

Compound commands on the live path are resolved by
`compound.resolve_compound_permission`: the hook splits the command into
sub-commands and passes each through the level cascade, combining the results
(any sub-command denied => whole command denied; else any "ask" => ask; else
allow). The older `compound.check_compound_permission` is **retained but OFF the
live path** -- it evaluates a compound command against a single flat
`(allow, deny)` pattern pair and predates the hierarchical resolver. It is kept
for its tests and for any caller that only needs flat allow/deny semantics; the
runtime hook no longer calls it.

### Project-root-relative paths

**Any relative path that appears anywhere in configuration resolves against the
PROJECT ROOT** -- regardless of which level/directory declared it. It is NOT
relative to the ancestor directory that holds the declaring file, and NOT
relative to the current working directory. This is enforced centrally by
`Configuration.resolve_config_path`.

It applies to:
- Scalar path settings such as `config_sync.backup_dir`.
- Relative file-path permission patterns for Read/Write/Edit (a pattern not
  starting with `/` or `~`, after any extended-syntax prefix such as
  `[glob]`/`[regex]` is removed). `[regex]` patterns are never path-joined.

Absolute paths and `~`-paths are unaffected; `~` still expands to the home
directory downstream. `[regex]`-prefixed patterns are also left untouched (a
regex is not a path). The config module knows the project root (via
`Configuration.project_root`), so it is the single anchor point for the rule.

Behaviour-change note: because relative file-path patterns are now rewritten to
`<project_root>/<body>`, a relative pattern such as `Read(src/**)` matches ONLY
paths inside the project root. A same-named path in an ancestor (e.g.
`<ancestor>/src/x.py`) no longer matches. Previously a relative pattern was
matched as authored. This is intentional under the more-specific-wins hierarchy
(a shared ancestor config should not silently grant access to unrelated sibling
trees) and is covered by a negative regression test in `test_hierarchical.py`.

### Rules directories: XDG and legacy paths, and shadowing

Beyond the `.claude/` hierarchy, toolguard also scans two flat, non-recursive
directories of `*.toml`/`*.json` rule files, both merging into the user (least
specific) level: `$XDG_CONFIG_HOME/toolguard/rules` (or `~/.config/toolguard/rules`
when `XDG_CONFIG_HOME` is unset) and the older `~/.toolguard/rules`, which predates
the XDG convention and is kept because a real, hand-authored ruleset placed there
was once found to be silently unenforced -- only the XDG directory was being
scanned. Both are now scanned, XDG first.

A rules-directory file may define only `[permissions]` and `[hard_deny]`; any
other top-level key is stripped and reported as a `validation_issues()` error
(scalar/singleton settings have no multi-file merge rule and stay the sole
responsibility of the primary `toolguard_hook.toml`).

When the same filename stem exists in both directories, the XDG copy wins and the
legacy copy is dropped entirely -- this must be loud, since it is exactly the
"ruleset lives in the wrong directory and is silently unenforced" failure mode
these directories exist to fix, so `validation_issues()` reports it as a warning.
The one exception: if both directories' entries resolve to the *same* real file
(e.g. one is a symlink into the other, a natural migration path), nothing is
actually being dropped, so no warning fires -- reporting it would just train users
to ignore the warning that matters.

### Hard-deny safety valve (TOO-8 Phase 3)

`[hard_deny]` is an **unoverridable** hard-deny mechanism: a (typically
less-specific) config can declare rules that NO more-specific config can
override. It is a toolguard extension read ONLY from `toolguard_hook` files
(TOML/JSON), never from native Claude `settings*.json` (Claude has no such
concept).

Shape (within a `toolguard_hook` file):

```toml
[hard_deny]
deny  = ["Bash(curl *)", "Read(**/.env)"]   # hard-denied (unoverridable)
allow = ["Bash(curl localhost*)"]            # carve-out EXCEPTION to the deny
```

Illustrating the shape only, not a recommended recipe: `allow` here is unoverridable too, so
it only suits a rule with a genuine no-exception carve-out. A rule you expect to except later
(curl-against-localhost is the running example) belongs at the ordinary deny/allow level
instead -- see [agent-guides.md](docs/agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception).

Semantics:

- **Pooled across ALL levels** into one union (not per-level inward
  propagation). `Configuration.hard_deny(tool)` returns the tool-scoped,
  de-duplicated `(deny, allow)` pools across every `toolguard_hook` layer.
- **Checked FIRST**, before the normal more-specific-wins cascade. A
  command/path that matches any hard-deny `deny` pattern AND does NOT match a
  hard-deny `allow` carve-out is **DENIED**, and that decision cannot be
  overridden by any level's normal allow. Otherwise resolution falls through to
  the Phase 2 cascade unchanged.
- `allow` is ONLY an exception to `deny` (e.g. hard-deny all `curl` EXCEPT
  `curl localhost`). It is NOT a forced/normal allow and does NOT affect the
  normal cascade.
- Patterns use the same extended syntax (`[regex]`/`[glob]`/`[native]`), tool
  wrappers, and matchers as normal permissions. Relative file-path hard-deny
  patterns anchor to the project root exactly like normal file-path patterns.

Applies uniformly to: Bash commands, EACH sub-command of a compound command
(the compound is hard-denied if any sub-command is), and file-path tools
(Read/Write/Edit, tool-scoped). Command matching uses
`permissions.check_hard_deny`; the file-path equivalent is
`file_matching.check_file_path_hard_deny`. There is no behaviour change when no
`[hard_deny]` is configured. Single resolution path (no dual/legacy code).

> Note (flagged for review): these exact `[hard_deny]` semantics -- the
> deny/allow carve-out shape and the all-levels pool -- were defined for Phase 3
> per decision #3 in the implementation plan and are pending Arnon's
> confirmation.

## Logging streams, conflict logging, and provenance (TOO-8 Phase 4)

### Four separate log streams (one file per concern)

Each logging concern writes to its OWN date-stamped file so the streams stay
separable:

| File                                  | Writer                         | Contents |
| ------------------------------------- | ------------------------------ | -------- |
| `logs/toolguard-YYYY-MM-DD.md`        | `log_writer.log_command`       | Resolution log (high volume): allowed/refused decisions, matched-rule provenance. Also `log_writer.log_discovery` (change-detecting discovery diagnostic, TOO-19) and `hard_deny` denials. |
| `logs/toolguard-error-YYYY-MM-DD.md`  | `error_log.log_error`          | REAL errors only. |
| `logs/toolguard-warning-YYYY-MM-DD.md`| `error_log.log_warning`        | Actionable warnings: both-`.toml`-and-`.json` present, unsupported/ungoverned tools. |
| `logs/toolguard-conflict-YYYY-MM-DD.md`| `error_log.log_conflict`      | Config conflicts, human/LLM-readable: allow-over-deny overrides and cross-level `takeover_mode.enabled` disagreements. |
| `logs/toolguard-discovery.log`        | `log_writer.log_discovery`     | Change-log backing the discovery diagnostic above: one PLAIN-TEXT line per project root per DISTINCT discovered level set (TOO-19 code review M3 -- not JSON). NOT date-partitioned, and never size-capped/rotated (see `log_writer._DISCOVERY_LOG_FILENAME`). |

`error_log._log_entry(level, stream, ...)` is the single shared writer; the
`stream` argument selects the `toolguard-<stream>-...` filename. All three share
the same Markdown entry format and echo a concise line to stderr.

The **takeover "active" notice** (`session_warnings.issue_takeover_warning`) is
informational, NOT actionable, so it is **no longer persisted to any log**: it is
a stderr echo on every invocation, never deduplicated, and (TOO-45 punch-list
#01, second pass) no longer touches the claim store at all -- periodic
housekeeping is internal to `toolguard.once_per.OncePer` and runs
opportunistically as a side effect of any OTHER throttled thing's successful
claim (e.g. `config_divergence.DIVERGENCE_WARNING`, `auto_migrate
.AUTO_MIGRATION`), backed by `toolguard.once_per_store`.

### Conflict logging -- allow-over-deny overrides only

A **conflict** is a MORE-specific level's `allow` overriding a LESS-specific
level's `deny` for the same command/path. The decision is unchanged
(more-specific-wins keeps the allow); a conflict entry is written to the conflict
log citing BOTH sides' provenance (winning allow's file/level + the overridden
deny's file/level) and the command. `hard_deny` denials are **not** conflicts --
they are recorded in the resolution log (with provenance), never the conflict log.

Detection lives in `permission_resolution.resolve_permission_cascade` /
`permission_resolution._detect_override`: when the winning decision is an `allow` at level
*k*, the LESS-specific levels are scanned for a `deny` match on the same command;
the first match becomes a `ConflictOverride`. The hook
(`_log_conflict_override` / `_format_conflict_message`) routes it to the conflict
stream.

### Provenance threaded into resolution reasons

`Configuration.permission_levels_with_provenance` is the provenance-carrying level
view (per level: `(allow, deny, ToolPatternLayer[])`). The detailed deciders
(`permissions.decide_command_at_level_detailed`,
`file_matching.decide_file_path_at_level_detailed`) report the matched pattern, which
`config_types.provenance_for_pattern` maps back to the owning
`ToolPatternLayer.provenance` for exact file/level precision. (TOO-45 R2d moved
this off `Configuration` -- it held no configuration state -- to live beside
`ToolPatternLayer` in `toolguard.config_types`; `permission_resolution.py`
imports and calls it directly.)
`resolve_permission_cascade` returns a `RuntimeVerdict`
(decision, reason, provenance, overrides, ...) -- TOO-45 R1c collapsed the former
`ResolvedDecision`/`BashResolution`/`FileResolution` into this one type, the single
runtime verdict every governed-tool resolution returns; see
`toolguard.config_types.RuntimeVerdict`'s own docstring. For **backward compatibility**,
provenance is appended to the reason as a bracketed suffix
(`_append_provenance` -> `Provenance.describe_brief`), e.g.
`Command matches allow pattern: git *  [project: /p/.claude/toolguard_hook.toml]`,
so existing `reason.split(': ', 1)` and "matches allow pattern: X" substring
consumers still work. Applied to Bash, each compound sub-command independently,
and Read/Write/Edit.

There is a single cascade implementation: the hook drives
`resolve_command_permission` / `resolve_file_path_permission_detailed` /
`hook.resolve_bash_permission_detailed`. (The earlier 2-tuple variants
`resolve_permission` / `resolve_file_path_permission` and their per-level helpers
`decide_command_at_level` / `make_command_level_decider` were removed once the
detailed path superseded them; no separate legacy cascade remains.)

### Change-detecting discovery diagnostic (M2, TOO-19)

`hook` calls `log_writer.log_discovery` on every invocation (fed by
`Configuration.describe_levels`), but toolguard is a fresh process per
`PreToolUse` call, so there is no in-process "once per session" to guard
with -- a prior module-level flag (`_discovery_diagnostic_done`) advertised
that guarantee and could never deliver it, since it reset to `False` on
every invocation. `log_discovery` is the guard instead: it keeps a small,
append-only, project-root-keyed change-log (`logs/toolguard-discovery.log`,
deliberately NOT date-partitioned -- see `log_writer._DISCOVERY_LOG_FILENAME`) and writes a
`discovered N config levels: <level: path>, ...` entry to the RESOLUTION
log, plus a discovery-log record, ONLY when the discovered levels differ
from the last recorded entry for this project root. On no change, it writes
nothing to either file. This replaces the discovery diagnostics that the
legacy `_load_permissions` printed to stderr.

**Plain text, not JSON (code review M3).** The discovery log was originally
JSONL: one JSON object per line. That was over-engineering for what the code
actually needs -- every record is one line, and the only thing ever read
back is the single most recent line matching this invocation's project
root, so JSON's structure and escaping bought nothing over a fixed-width
delimited line. Each record is now `<iso timestamp>\t<project_root>\t<levels
joined by the ASCII Unit Separator 0x1F>`. Tab and the Unit Separator are
both, for all practical purposes, impossible to encounter in a real
filesystem path or a `level: path` description string -- unlike a comma or a
colon, which both appear in those strings routinely -- so splitting on them
needs no escaping logic. `_parse_discovery_line` does the split; a line
missing either separator is treated as unparseable and skipped, the same
tolerance the old JSONL parser had for a torn write.

**No size cap on the file; a bounded read instead (code review M3).** The
original design capped how much of the file it would READ at 1 MB and
degraded to "no prior entry" past that -- which is the bug the review
caught: once a file crossed 1 MB, EVERY subsequent invocation saw "no prior
entry", appended, and made the file bigger, guaranteeing every invocation
after that would also append. Self-accelerating, and silent. The fix
removes the size cap entirely -- the file is never truncated or rotated, by
design -- and instead bounds only how much of it a single READ touches:
`_last_discovery_levels_for_root` seeks to `_DISCOVERY_TAIL_READ_BYTES`
(64 KiB) from the end and scans that tail's lines backwards for a match on
project root, discarding a possibly-partial first line when the read didn't
start at byte 0. Growing the file no longer changes the cost of a read (it
is always bounded by the tail size), and no longer changes correctness
either: the only way a read can miss the real last entry is if enough OTHER
projects' records (in a shared `TOOLGUARD_LOG_DIR`) have been appended after
it to push it outside the tail window, in which case the read degrades to
"no prior entry" -- costing one redundant log write for THIS invocation,
never an incorrect permission verdict. This is the same safety argument that
already justified tolerating a torn final line.

### Single source of truth for the both-formats warning (M1)

The "both `.toml` and `.json` exist" warning is detected ONLY in
`Configuration.validation_issues()` and routed by the hook to the WARNING stream.
Discovery (`_discover_in_dir`) is side-effect-free (no stderr print). The Issue
fires in real usage by checking on-disk presence of the sibling file (discovery
keeps only the TOML), and also when two differing-format layers share a base.

### Single source of truth for tool-wrapper stripping

Permission patterns are authored wrapped as `Tool(inner)` (e.g. `Bash(git *)`)
but matched on the unwrapped inner pattern. `rule_entry.strip_tool_wrapper` is the
single, purely STRUCTURAL strip (`re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)')`): it
needs no hand-maintained tool list and handles inner parentheses
(`Bash(foo(bar))` -> `foo(bar)`). Divergence detection recognises tool-scoped
native permissions via the shared `rule_entry.is_tool_wrapper` predicate, which uses
the same `_TOOL_WRAPPER_RE` -- there is no duplicated regex in
`config_divergence.py`. New governed tools require no change to any prefix list.

## Non-permission cross-level resolution (TOO-8 Phase 5)

Phase 5 resolves the *non-permission* settings across the hierarchy. Permission
and `[hard_deny]` resolution are unchanged.

### Scalars and `no_match_fallback` -- more-specific-wins

`Configuration.scalar(name, default)` resolves MORE-SPECIFIC-WINS: layers are
ordered most-specific first (project beats ancestor beats user), so the FIRST
toolguard_hook layer that defines the key wins and iteration stops. This flips
the Phase-1 user-wins (last-occurrence) behaviour. Native (`claude`) layers are
ignored -- these settings are toolguard extensions.

As a consequence, `Configuration.config_sync_settings()` (`auto_migrate`,
`backup_dir`, `auto_sort_on_migrate`) resolves more-specific-wins. The takeover
`no_match_fallback` likewise resolves more-specific-wins (first level that sets
it wins; default `deny`).

Single-level configs are unaffected: with one defining level, more-specific-wins
and the old behaviour coincide.

### `undecidable_fallback` vs `no_match_fallback` -- a deliberate asymmetry

`no_match_fallback` and `undecidable_fallback` answer different questions:
`no_match_fallback` is "I read this command and no rule covered it";
`undecidable_fallback` is "I could not safely read this command at all" (foreign
inline code, heredoc sinks, complex control structures, process substitution --
see `toolguard.compound`). It is applied as a strictest-wins floor by
`toolguard.compound._apply_undecidable_floor` against whatever the leaf/segment
itself resolved to. Both resolve the same way (top-level key, most-specific
layer wins, `'ask'`/`'deny'`/`'allow_with_warning'`/`'allow'`, unset or
unrecognized falls back to `'ask'`) via the shared
`Configuration._resolve_fallback_setting`.

They deliberately do NOT share every alias. `no_match_fallback` carries two
legacy spellings from before `undecidable_fallback` existed: a `[takeover_mode]`
nested alias, and the deprecated value `'warn_deny'` (normalizes to
`'allow_with_warning'`). `undecidable_fallback` is a brand-new top-level key with
neither -- it has no prior spelling to stay compatible with, and there is no
`[takeover_mode]` field for it on `TakeoverConfig`. Do not add either "for
symmetry"; that history does not apply to it. The one alias both settings DO
share is `'allow_with_no_warnings'` -> `'allow'` (see
`config._ALLOW_NO_WARNINGS_ALIAS`), because it was introduced for both at once
and is not part of `no_match_fallback`'s legacy history.

### `governed_tools` and takeover pattern lists -- UNION across all levels

`Configuration.governed_tools()` is a UNION across all toolguard_hook layers in
the hierarchy (de-duplicated, first-occurrence/most-specific-first order),
defaulting to `('Bash', 'Read', 'Write', 'Edit')`
(`toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS`) when nothing is configured. It now
resolves over the hierarchical `self.layers` (not the legacy 2-level
`_load_governed_tools`), so it is consistent with permission and takeover
resolution and applies under `CLAUDE_SETTINGS_PATH` mode (the explicit source is
the only layer).

The takeover pattern lists (`ignored_allow_patterns`,
`additional_ignored_patterns`) remain a UNION across all levels.
`ignored_allow_patterns` is seeded with the blanket defaults
(`Bash(*)`, `Read(*)`, `Write(*)`, `Edit(*)`,
`mcp__jetbrains__execute_terminal_command(*)`).

### `takeover_mode.enabled` -- single-owner with fail-safe-on-conflict

takeover_mode is a single-owner policy; cross-level disagreement on `enabled` is
a misconfiguration, not something to merge. `Configuration.takeover_mode()`
inspects which levels EXPLICITLY set `takeover_mode.enabled` (key present in that
layer's parsed content):

- 0 levels set it => default OFF (`False`).
- One or more set it, all to the SAME value => that value (no conflict).
- Levels disagree (some `true`, some `false`) => CONFLICT: `enabled` is forced to
  `False` (fail-safe OFF -- native Claude prompts stay active, nothing is
  silently bypassed), and a `TakeoverEnabledConflict` is attached to the
  `TakeoverConfig` recording each disagreeing source with its value and
  provenance.

This replaces the old OR-based `enabled` merge.

When the hook (`hook.main`) sees an enabled-conflict, it writes a once-per-session
entry to the **conflict log** (`error_log.log_conflict`, citing the disagreeing
levels' values + provenance and that fail-safe OFF was applied) and issues a
once-per-session takeover/config warning (the same session-marker mechanism as
the takeover "active" notice). Because `enabled` is already OFF, the downstream
path is the safe one. (Surfacing prior-session conflicts at session START is
handled by Phase 6.)

## SessionStart conflict alerting (TOO-8 Phase 6)

### Separate entry point

The SessionStart hook is exposed as a dedicated script entry point in
`pyproject.toml`:

```toml
toolguard-session-start = "toolguard.session_start:main"
```

This is **completely independent** of the PreToolUse `toolguard` hook and
runs under the `SessionStart` hook event, not `PreToolUse`. The two entry
points share configuration loading (`load_configuration`) but nothing else.

### Two detection sources

The hook detects conflicts from two complementary sources:

**1. Static conflicts (recomputed live)**

`config.takeover_mode().conflict` returns a `TakeoverEnabledConflict` when
levels disagree on `takeover_mode.enabled`. This is recomputed fresh every
session from the current configuration files, so it **self-clears** the
moment the configuration is corrected. No stale state is involved.

**2. Dynamic conflicts (from the conflict log)**

Allow-over-deny overrides (where a more-specific level's `allow` overrides a
less-specific level's `deny`) can only be detected at tool-use time -- when
an actual command is evaluated. These are recorded to
`logs/toolguard-conflict-YYYY-MM-DD.md` by `error_log.log_conflict`.

The SessionStart hook reads the most recent conflict log file that contains
at least one entry and reports its path and entry count. Entry counting is
simple: each entry starts with a Markdown heading of the form
`## YYYY-MM-DD HH:MM:SS - CONFLICT`, so counting such lines gives the count
without a full parse.

### Why dynamic conflicts come from the log

Dynamic conflicts require an actual command to evaluate, so they cannot be
recomputed statically from the configuration alone. The log is the only
durable record of overrides that occurred during previous sessions. This is
why the hook reports "conflict log X has N entries" rather than listing the
individual overrides.

### Nag-every-session semantics

There is **no deduplication marker** for the SessionStart alert. The hook
prints a summary every session while conflicts remain, stopping only when the
conflicts are genuinely resolved. This is intentional: persistent nagging
encourages resolution. This contrasts with the PreToolUse takeover notice,
which uses a once-per-day marker to avoid repetition.

### Stdout as session context

Claude Code injects SessionStart hook stdout directly into the session
context. This means the agent itself sees and can act on the conflict summary
immediately at the start of a session, without requiring the user to inspect
log files manually.

### Output format

When conflicts are detected, the hook prints a few lines to stdout and exits 0:

```
toolguard: configuration conflicts detected --
  - takeover_mode.enabled disagrees across levels; failed safe to OFF (...)
  - conflict log logs/toolguard-conflict-YYYY-MM-DD.md has N recorded entries
Review and resolve; see the conflict log for details.
```

When no conflicts are present, nothing is printed and the hook exits 0 silently.

### Resilience

The entire hook body is wrapped in a `try/except Exception` that degrades to a
one-line stderr message and exits 0. A SessionStart hook must **never** block
or break the session. Input is parsed leniently: missing `cwd` falls back to
`os.getcwd()`; missing or malformed stdin returns an empty payload.

## Multi-line Bash decomposition (TOO-17)

### The defect

The parser handled only a single logical line. A multi-line Bash command (newline-separated
statements, or a whole script in one tool call) was NOT split into sub-commands; combined with
DOTALL `fnmatch`, a command whose FIRST line matched an allowed prefix was allowed in full --
including dangerous later lines. A **fail-OPEN bypass** of the permission system. Real usage
hit it constantly: in a ~7,800-command corpus of historical logs/transcripts, **~29% of
commands in dev/analysis-heavy sessions were multi-line**, and ~94% of distinct multi-line
commands fell through to the fail-open whole-blob path.

### Governing principle: when in doubt, ASK

The fix is **fail-safe, not fail-open**. Toolguard auto-decides only what it can decompose
with confidence; anything else resolves to **ASK** -- never a silent allow of an undecomposed
blob, and never a hard deny that would break a legitimate workflow. This "hidden" ASK applies
even when no TOML pattern matches the construct.

**Update (TOO-19):** "resolves to ASK" above is the *default*, not a hardcoded outcome. The
top-level `undecidable_fallback` config key (`docs/configuration.md#undecidable-fallback`)
names the floor this governing principle resolves to -- `"ask"` (this default), `"deny"`
(stricter), or `"allow_with_warning"`/`"allow"` (both remove the floor entirely, the
deliberate opt-out, and both raise the SAME HIGH `toolguard-audit` finding -- `"allow"` is
strictly less safe since it logs no warning at all; `"allow_with_no_warnings"` is an
identical alias for `"allow"`, kept as a human reminder). See `compound.py`'s
`_UNDECIDABLE_FLOOR_DECISION` and `Configuration.resolved_undecidable_fallback` for the
resolution mechanics, which this whole section predates.

### Grammar-first, with a light AST -- no hand-rolled parsing

All STRUCTURAL parsing is done by the formal PEG grammar
(`toolguard/parser/bash_parser.peg`, regenerated to `bash_parser.py` with canopy). Bash
quoting/escaping/heredoc edge cases are exactly where ad-hoc regex/state-machine parsers go
wrong, so hand-rolled bash parsing is prohibited (an early attempt that did so was rejected).
The processing pipeline is layered for separation of concerns:

| Module | Responsibility |
|--------|----------------|
| `parser/multiline.py` | A narrow LEXICAL pre-pass only (see below). No structural parsing. |
| `parser/command_model.py` | Builds a small typed IR ("light AST") from the raw Canopy parse tree. The ONLY code that touches raw tree nodes. |
| `parser/command_extractor.py` | Walks the IR (not the raw tree) to produce leaves / undecidable segments. |
| `compound.py` | Resolves each leaf through the level cascade and combines strictest-wins (one combinator). `resolve_compound_permission` now feeds through `multiline.extract_structured` + the IR. |

Keeping raw-tree access isolated in one module is what makes the rest readable; the IR is the
"early simplification / noise removal" boundary.

### `compound.py`'s shape: pure functions, no callbacks (TOO-45)

`compound.py` was originally built around injected callbacks (`resolve_one`/`resolve_outer`/
`record_unit`) threaded through a `resolve.py`<->`compound.py` cycle: `compound.py` called back
into `resolve.py` to resolve a leaf, and `resolve.py` called back into `compound.py` to combine
results. That cycle made the ASK floor hard to test (it needed a fake resolver closure) and made
an audit-log entry's very existence depend on which callback a given leaf kind happened to
invoke -- an entry could go silently missing because a code path diverged, with no error anywhere.

The module is now three pure functions with no callback dependency: `decompose` splits a command
line into `CommandUnit`s (structure only -- decides nothing); `judge_unit` decides one unit given
the caller's own resolution of its `parts`, handed in as data via `part_verdicts` (owns the ASK
floor); `_combine_strictest` combines several already-judged units into the compound's own
verdict. `compound.py` never calls back into `resolve.py`; the production caller
(`resolve.resolve_bash_permission_detailed`) drives all three directly and builds its own
`sub_matches`/`overrides` by ordinary `append`/`extend`. `CommandUnit.audits_as_one` is decided at
construction time, in `_unit_for`, rather than re-derived from `kind` by a caller (see
`judge_unit`'s own `Raises` docstring for why a fifth kind must be decided explicitly, not
silently fall through).

`resolve_compound_permission_detailed` (and its thin wrapper `resolve_compound_permission`)
remain as a convenience driver over the same three functions, for callers -- `check_compound_permission`
and many existing tests -- with only a plain `resolve_one` 3-tuple closure and no
`UnitVerdict`-producing resolver of their own. Neither is on the production path.

An `'inline_code'` unit splits its own sub-commands (`extract_commands` over the leaf text, minus
the leaf's own text) across two `CommandUnit` fields, not one. `audit_parts` is the subset that is
itself foreign inline code -- itemised in `sub_matches` and, via `_combine_inline_code_reason`,
folded into the unit's own reason text when everything allows. `deny_check_parts` is every other
sub-command -- checked the same way but never itemised in `sub_matches` or folded into the reason
unless it actually decides. Both still feed the unit's other aggregate fields when merely allowed:
`fallback_kind`/`fallback_warning` and `additional_context` are each accumulated over the full set
`judge_unit` names `all_parts` (the stub, `audit_parts`, `deny_check_parts`), not just the subset
that appears in `sub_matches`/reason. In both `audit_parts` and `deny_check_parts`, only an `allow`
is observation-only (never `decision`/`matched_rule`/`provenance`); a `deny`
(ordinary or hard-deny) OR an `ask` still decides the unit outright, the same as it would for a
`'plain'` leaf's own sub-command, and that attribution flows through the unit's own verdict, never
through the raw audit-trail record: see `UnitVerdict.audit_only` and
`toolguard.resolve._deciding_sub_match`. Both cases are routed through `_pick_strictest`, the same
first-match-within-a-tier primitive `_combine_strictest` itself uses to combine a compound's
units -- not a bespoke, deny-only scan, which would silently downgrade an `ask` reaching no
branch at all to `allow`.

The two-field split exists because a straight widening of `audit_parts` to every sub-command --
needed to close a regression where re-classifying a leaf from `'plain'` to `'inline_code'` (TOO-45
proposed ticket 79's ASK-floor gap) silently dropped a hard-denied or denied inner substitution
from the decision entirely -- also changed what an unrelated, merely-allowed substitution (a
`$(mktemp -d)` alongside a `python -c` one, say) itemises and folds into the reason, which
`test/verdict_corpus/goldens.jsonl` pins for real harvested commands. Keeping that itemisation
scoped to `audit_parts` alone reproduces the historical output exactly for commands the corpus
already had pinned before this split existed. It does NOT for a leaf this fix newly floors: an
unrelated, merely-allowed `deny_check_parts` entry (e.g. `mktemp -d` alongside a `python -c` one)
is checked but never appears in `sub_matches` or the reason, a narrower-scoped recurrence of the
under-logging this project has hit before (see the global CLAUDE.md's "Prose is output, not a
data structure"). This is a disclosed, bounded trade-off, not an oversight: closing it means
recording every `deny_check_parts` verdict in `sub_matches` regardless of decision, which would
also change what `test_unrelated_substitution_is_not_itemised`
(`test/unit/test_resolve.py`) asserts.

That trade-off is scoped to itemisation and reason text only. `additional_context` is a
separate field: an allowed `deny_check_parts` entry's own context was silently dropped instead
of accumulated -- the same under-logging shape as the global CLAUDE.md's "Prose is output, not
a data structure", not a consequence of the itemisation trade-off above. It now accumulates via
`judge_unit`'s `all_parts`, the same as `fallback_kind`/`fallback_warning` already did, at no
cost to `test_unrelated_substitution_is_not_itemised`.

A related, separate trade-off: fixing `_combine_strictest`'s own fabrication guard so that a
fallback-decided `'inline_code'` unit is never mistaken for a genuine match one level up changes
the rendered `reason` text for TWO harvested corpus commands whose pinned `goldens.jsonl` entries
were already bracket-unbalanced -- `verdict`/`sub_matches` unchanged, confirmed by
`tools/corpus_build.py --verify`; only the TRACKED-tier prose differs. One of the two is now
balanced; the other survives unbalanced for a different, pre-existing reason -- a `'plain'`
unit's own summary is still re-parsed as prose one level up, tracked separately (proposed ticket
90, `toolguard-memories/TOO-45/proposed-tickets/`). `goldens.jsonl` was regenerated to match, the
corpus's own sanctioned remediation for a legitimate prose change.

### How deep we go -- and why not deeper

Bash is Turing-complete; statically reasoning about arbitrary scripts would mean rebuilding
~80% of bash plus semantic analysis. That is explicitly **out of scope**. We decompose only
the simple, common constructs observed in real usage and ASK on the rest:

- **Simple control structures** (non-nested `if`/`for`/`while`, no `else`/`elif`, linear body,
  condition = a command or a POSIX `[ ... ]` test) are decomposed and their inner commands
  validated. **Complex** ones (`else`/`elif`, nesting, `case`, `[[ ]]`/`(( ))`) -> ASK.
- **Process substitution** `<(...)`/`>(...)` -> ASK (it was also a pre-existing fail-open).
- Detection of these is done from the PARSE TREE, never a raw-text keyword scan -- comments,
  quoted strings, heredoc bodies, and `-c` arguments routinely contain `if`/`for`/`|`/etc. as
  non-structural text, so a lexical scan would mis-route huge numbers of benign commands.

### Lexical pre-pass vs. grammar

See [docs/multiline-parsing-flow.md](docs/multiline-parsing-flow.md) for a diagram of the
five-step pipeline this section describes.

A few things genuinely cannot (or should not) live in the PEG grammar and are done as a
deterministic, quote-aware lexical pre-pass in `multiline.py`: CRLF/CR -> LF; backslash-newline
continuation join; heredoc body extraction/removal; `#` comment stripping; whitespace
collapse. Everything else -- statement separation on newlines/`;`, operator continuation,
pipes, quoting, control structures -- is the grammar's job. The heredoc step is the notable
exception: a PEG cannot back-reference the captured heredoc delimiter, so the body is removed
lexically before parsing.

### Heredocs, the sink sentinel, and executor classification

A heredoc body is data for whatever consumes it, not shell to parse. `multiline.py` lifts the
body lexically behind an opaque placeholder; `command_extractor.py` then reads the parse tree
for which command owns the placeholder and replaces it with an all-letters sentinel
**`__HEREDOC_TO_<sink>__`**. The bearer's own class decides the sink first: a bearer that is
itself bash-family or foreign wins outright, even mid-pipeline (`python <<HD | bash` is
python's heredoc, not bash's). Only a non-executor bearer (`cat`, `tee`) falls through to the
pipeline's last stage, so `cat <<EOF | bash` still resolves to `bash`. See
[docs/heredoc-parsing-design.md](docs/heredoc-parsing-design.md) for why attribution comes off
the tree rather than a token scan. The bearer keeps its other arguments so a dangerous bearer
(`tee /etc/passwd <<EOF`) is still catchable. The sentinel is all `[A-Za-z0-9_]` deliberately,
so regex rules stay clean.

The sink's **executor class** then decides handling -- this is also why `-c`/`-e`/`-r` inline
code is treated the same way:

- **bash-family** (`bash`, `sh`, `dash`, `ksh`, `zsh`): the payload IS bash -> decompose and
  validate. We only attempt this for bash-family syntax because that is the only language our
  bash grammar can parse; trying to parse Python/Node/csh/fish would be unreliable, so those
  are punted (ASK) rather than guessed.
- **foreign** (non-bash shells + interpreters like `python`, `node`, `perl`, `ruby`, `php`,
  `Rscript`, `uv`, `uvx`): opaque code -> **ASK floor**. Recognition is **dynamic for
  versioned names**: `_is_foreign_executor` matches `python3.13`, `pypy3.11`, `node18`, etc.
  by prefix, so `FOREIGN_EXECUTORS` lists only canonical names and never needs updating for
  new releases (no year/version table to maintain). The list is NOT exhaustive, though -- an
  unrecognized interpreter (`lua`, `deno`, ...) is not floored (a documented YAGNI; the
  command is still validated and `deny` still works). The heredoc sink label is sanitized to
  `[A-Za-z0-9_]` when building the sentinel (`python3.13` -> `__HEREDOC_TO_python3_13__`) so
  the sentinel stays escape-free and the floor matcher still recognizes the versioned sink.
- **non-executor** (`cat`, `tee`, `pbcopy`, unknown): body is data -> the sentinel leaf is
  matched normally.

**ASK floor + no-blanket-allow invariant.** Because the heredoc/inline-code leaf keeps the
bearer (e.g. `cat __HEREDOC_TO_python__`), a broad receiver allow (`allow = cat:*`, or
`uv run*`) would otherwise match and re-open the fail-open. So a foreign-executor heredoc /
inline-code leaf has its verdict CLAMPED to at most ASK: a plain `allow` cannot downgrade it
(`deny` still applies). This makes "allow data-sink heredocs, ask executor heredocs"
authorable without cross-leaf context, while guaranteeing no fail-open. (TOO-19: "at most ASK"
is the `undecidable_fallback` default; `"allow_with_warning"`/`"allow"` remove this clamp
entirely -- see the governing-principle section above.)

### Command substitution: validated, but no placeholder (yet)

Inner commands of `$(...)`, `` `...` ``, subshells, and brace groups are extracted and
validated (including nested). We considered presenting the OUTER command with a
`__..._OUTPUT__` placeholder (like the heredoc sentinel) for cleaner rule authoring, but a
corpus scan showed command substitution is **< 1.5% of distinct commands** (and most of those
are false positives -- backticks inside strings/heredoc bodies -- or benign `$(date)`). Per
"don't over-engineer for rare constructs," the placeholder is deferred; current behavior
(inner validated, outer matched with the substitution text inline) is already safe.

### Flagged defaults (resolved by TOO-19)

- The foreign-executor **ASK floor** slightly constrains authoring (a plain `allow` cannot
  permit foreign inline/heredoc code -- by design, to prevent fail-open).
- Truly-unparseable input fails closed via the **`undecidable_fallback`** config key
  (default `"ask"`) -- NOT `no_match_fallback`, which answers a different question (a command
  that was read and understood but matched no rule). Both of the items above were originally
  hardcoded ASK; TOO-19 made the floor level itself configurable
  (`ask`/`deny`/`allow_with_warning`/`allow` -- `allow_with_no_warnings` is a deliberate,
  permanent alias for `allow`; unlike `no_match_fallback`, there is no `warn_deny` spelling
  here), closing this "open to revisit" note. See
  `docs/configuration.md#undecidable-fallback` for the setting and
  `docs/security.md#loosening-the-undecidable-fallback` for the security tradeoff of loosening
  it.

## Maintenance and audit tooling (TOO-15 Phase 2)

TOO-15 adds two operator-facing capabilities on top of the config hierarchy: a **security
audit** (`toolguard-audit`, read-only, flags risk) and **rule maintenance**
(`toolguard-maintain`, finds redundant/consolidatable/confusing rules and applies safe
consolidations). They are exposed both as console scripts and as agent **skills**
(`toolguard-security-audit`, `toolguard-maintenance`). The decisions below shaped how they
fit together; they are recorded here while the rationale is fresh.

### Library-first, thin-skill seam

All analysis and editing lives in the deterministic library (`toolguard/tools/`); the skills
only orchestrate the CLIs and add human/AI judgement. Corollary: the pure aggregators do no
IO. `run_maintenance` takes an already-harvested corpus as a parameter rather than reading
logs itself, and corpus harvesting lives in its own module (`tools/corpus.py`). This keeps
the analysis testable without a filesystem and keeps "which proposals to apply / is the tree
clean / did the user approve" firmly on the skill side.

### Corpus harvesting is opt-in, not automatic

Replay- and mining-backed findings need a corpus of observed commands (daily logs +
Claude transcripts, merged and time-bounded by `tools/corpus.py`). Harvesting is **opt-in**
(`toolguard-maintain --corpus`, bounded by `--max-age-days`), and static analysis is the fast
default. Reason: mining parses every observed command through the bash grammar, which on a
real history (measured: ~37s for a 2-day window over a 69 MB transcript store) is far too slow
to run by default. The daily-log dir is resolved from the project root's `logs/`; transcripts
from `~/.claude/projects/<encoded>/` via the same `/`<->`-` path encoding the harvester
already uses.

### One report, two audiences -- `--format json` is the agent sidecar

The audit and maintenance reports serve both a human and a driving skill. Rather than add a
separate `--for-skill`/`--audience` mode, the existing `--format json` **is** the agent
report: once a finding's remediation is structured (below), the JSON carries both the human
`remediation` string (unchanged, back-compatible) and a machine-actionable
`remediation_proposal`. Humans read the text; skills read the proposal. A distinct audience
flag was rejected as premature surface.

### Structured remediation is a conservative, mechanical fix

`RankedFinding.remediation` is a `Remediation(text, proposal)`: the human text is retained,
plus an optional `EditProposal` when the fix is mechanically expressible. The proposal is the
**conservative** action -- deleting a dangerous allow (always a tightening) or anchoring an
unanchored `[regex]` -- even where the human text suggests a more surgical narrowing. It is a
proposal to review as-if-enacted, never auto-applied. Danger detectors declare a
`remediation_kind` hint (`remove`/`anchor`); findings with no mechanical fix carry text only.

### The shared EditProposal model, and one edit primitive

A single representation (`tools/edit_proposal.py`: `EditProposal` = an intent label
`remove|replace|narrow|move` plus atomic `RuleEdit`s that may span **sections and layers**)
lets the two skills exchange proposed changes without parsing prose. Both directions reuse it:
the audit **emits** it (structured remediation), the audit **ingests** it (`--edits`), and the
maintenance skill converts its consolidations into it. Applying edits in memory
(`apply_edits`) is built on a section-generic `with_layer_rules_replaced`, generalized from the
former allow-only `with_layer_allow_replaced` (which now delegates -- one implementation). This
generalization mirrors the existing `migrate_config`, which already builds a modified config in
memory for the hierarchy-migration case.

### As-if-enacted review: `--edits` vs `--migrations`

Two ways to hand the audit a proposed change, deliberately different:

- **`--migrations`** embeds migration metadata under `context['proposed_migrations']` for the
  AI to reason about a hypothetical move. The config is NOT changed; the AI judges intent.
- **`--edits`** actually **applies** the proposals in memory and audits the resulting config,
  so the top-level findings reflect the proposed state (whole hierarchy, all sections), plus a
  finding delta (`introduced`/`resolved`). This is the maintenance->audit review path.

Reason `--edits` applies-then-audits rather than reasons-about: a consolidation (or an audit
remediation) can replace one rule with a SET of rules across sections, whose interaction only
shows up when the whole config is resolved as-if-enacted. `introduced` findings are the
headline risk; a change that resolves a MEDIUM but introduces a CRITICAL is a bad trade the
skill must surface.

### Apply is preview-first and gated

`toolguard-maintain --apply` is a **dry-run preview** (renders the per-file unified diffs,
writes nothing); only `--apply --write` mutates files, and only after `migration_preflight`
passes (clean working tree, resolved project root -- refuses on a dirty tree, exit 2, so a
change stays reviewable and revertible). Only strict, replay-verified consolidations
(null-or-tightening decision diff) are machine-appliable; broadenings and cross-layer/clarity
findings are reported for human judgement, never auto-applied.

### Flagged gap (open) -- cross-project blast radius

The `--edits` as-if-enacted review is **single-project**: it evaluates the current project's
hierarchy only. Edits to a SHARED layer (user `~/.claude`, enterprise) can affect OTHER
projects that inherit it, which this review does not yet surface -- a user-level refactor can
read "0 introduced" here while changing another project. Closing this (at minimum: detect a
shared-layer edit and WARN before `--write`; ideally: a filtered multi-project audit over the
user's projects discovered from `~/.claude/projects/` and `~/.claude.json`) is tracked as
remaining TOO-15 work. Until then, treat a clean single-project review of a user-level edit as
necessary but not sufficient.

### Multi-pass maintenance: SKILL.md orchestrator + `passes/` + a JSON state artifact

Maintenance is judgement-heavy refactoring, so the skill is a **conversation over evidence**,
not a one-shot report. `skills/toolguard-maintenance/SKILL.md` is only the orchestrator; the
real instructions live in `passes/*.md`, loaded one at a time (progressive disclosure -- doing
gather + level + consolidate + audit + present all at once invites mistakes):

1. `1-gather-and-target.md` -- run the analyzer + audit for evidence, group every rule into
   command families, target the level of each change (blocking cross-level welds), read the
   prior-decision ledger, capture non-permission settings.
2. `2-consolidate-and-group.md` -- treat the tool's consolidations as *candidates*, refine
   under level constraints, flag heterogeneous families, write per-family narratives.
3. `3-report-and-certify.md` (read-only) -- render the understanding view + cut/paste TOML,
   then certify with the tool (parse + as-if-enacted audit + corpus replay).
4. `4-discuss-and-apply.md` (the only write pass) -- case-by-case consent, then enact only
   what the user approved.

The passes do not re-derive each other's work: they read and annotate one **recommendation
set** JSON (`passes/recommendation-set-schema.md`) kept in the session scratchpad, never in
the repo. It is internal scratch -- the user sees the rendered understanding view and the
paste-ready TOML, never the JSON. The skill runs INLINE in the main conversation (not a forked
subagent) because pass 4 is an interactive per-item consent dialogue; the audit skill, being a
read-only report, may fork.

### Certify-by-staging: author by AI, certify by tool

Once consolidation involves judgement the final TOML cannot be purely tool-derived, so the
skill authors it and the tool certifies it: copy the project config into a temp dir, `git
init` it (the audit discovers config by walking up from a project-root marker -- a bare temp
dir loads nothing), overwrite the candidate TOML, and run `toolguard-audit --dir <tempdir>
--with-context`. This whole-config staging audit is the **authoritative** pre-write gate
(covers hand-authored changes `--edits` cannot represent). It has a silent-failure trap: a
mis-staged root makes the audit load nothing and report a bogus clean, so the pass verifies
`context.summary.sources` includes the staged file and the TOP-LEVEL `takeover_active` matches
before trusting the delta (`takeover_active` is top-level, NOT under `context.summary`).

### Corpus-replay candidate validation (`--replay-candidate`)

`toolguard-maintain --dir <project> --replay-candidate <staged>` replays the project's
observed corpus against the current config vs the assembled candidate and classifies each
observed command `unchanged` / `tightened` / `broadened`. It harvests its own corpus
independently of `--corpus`. It is **necessary, not sufficient**: it only covers observed
commands, an empty corpus is vacuous (not clean), a `broadened` is the red flag, and large
`tightened` counts are expected for deny-hardening. It never gates an apply on its own.

### The alembic landmine, stated correctly

The worked example behind the replay gate: a project layer allows `uv run alembic upgrade:*` and `uv run alembic current:*`, while a broader layer asks on `uv run alembic:*`. Consolidating the two project allows into `uv run alembic:*` moves the broad pattern into the *more specific* layer, which then decides for every alembic subcommand -- so `uv run alembic downgrade -1` goes from `ask` to `allow`. Replay catches it only if some alembic command was actually logged.

The layers are the whole point, and `replay.py`'s docstring stated it without them for a long time. With the allows and the ask in the **same** layer there is no landmine at all: ask beats allow within a layer, so the same consolidation *tightens* -- `upgrade head` goes `allow -> ask` and `downgrade -1` stays `ask` (measured 2026-08-12).

### Prior-decision ledger (`decision_ledger.py`)

A periodic run must not re-litigate settled questions. Two stores hold "prior decisions":
in-file annotations (`# toolguard:` / `#NOSECURITY`) for a decision attached to a surviving
rule, and the **sidecar ledger** for a meta-decision with no rule to hang on (a rejected merge
or promotion). The ledger is deliberately tool-owned and canonical (re-parsed mechanically
each run), not outsourced to a human-memory system. It is level-scoped like config: the
project ledger travels in the repo at `<root>/.claude/toolguard_decisions.json`; the user
ledger lives under toolguard's own namespace at `~/.toolguard/decisions.json` (NOT `~/.claude`
-- kept out of Claude Code's config dir).

A decision is identified by `(kind, family_id, target)`, independent of which level stores it,
so a suppression recorded at either level answers a re-raise. Only a `reject` disposition
suppresses (accept/defer do not). Recording is idempotent by id (same-id replaces in place). A
corrupt ledger raises `LedgerError` and is surfaced -- never silently emptied, since a dropped
decision would re-open a settled question. CLI: `--ledger-show [--format json]` (read, merges
both levels) and `--record-decision FILE --ledger-level {project,user}` (append; the whole
batch is validated before any entry is written, so a malformed member aborts atomically).

### Layer promotion certified by a live two-level HOME-staged audit

Promoting a rule to the user level is a cross-context broadening only the developer can
approve, so it is a first-class proposed **move** (`status:"promote"`), never auto-enacted
(there is no cross-level move writer -- it is a two-file hand-apply). Project-only staging
cannot certify it (the removed rule reads as gone), so pass 3 step 3c stages BOTH levels: the
project with the rule removed, and a temp `HOME/.claude/toolguard_hook.toml` with the rule
added (plus base setup if the user level does not exist yet). Because config discovery anchors
the user level on `Path.home()/".claude"`, redirecting `HOME` on the audit subprocess
(`HOME=<staged_home> toolguard-audit --dir <staged_project>`) stages the user level with no
tool change -- both `sources` then show, and the two-level verdict certifies the move. What no
audit can see (stated, not glossed): cross-context broadening of a promoted ALLOW across the
whole fleet, so a clean promotion audit is necessary, not sufficient.

### CLI mode summary

`toolguard-maintain` is read-only by default; the write modes each run `migration_preflight`
(clean tree + resolved root, else exit 2). Modes are mutually exclusive:

- default -- print findings (`--format markdown|text|json`); `--corpus [--max-age-days N]` adds
  replay/mining evidence.
- `--apply [--write]` -- dry-run preview of machine-appliable consolidations (`--write` enacts).
- `--annotate [--write]` -- write/refresh `# toolguard:` comments (comment-only, idempotent).
- `--replay-candidate <dir>` -- corpus-validate an assembled candidate (read-only).
- `--ledger-show` / `--record-decision FILE --ledger-level {project,user}` -- the ledger.

`toolguard-audit` is always read-only: `--with-context` (full hierarchy + summary), `--edits
<file>` (as-if-enacted delta; expects a bare `EditProposal` array), `--migrations`, `--strict`.
The `toolguard --eval` hook flag (read-only resolve, no migration/logging) backs the audit
skill's cross-project safety-floor probe.

User-facing usage of both skills is in [docs/skills.md](docs/skills.md).

## Isolated experiment sandbox (TOO-19)

`toolguard/testing/sandbox.py` answers behavioural questions -- "what would this config
decide for this command?" -- against a throwaway project instead of a live one. It exists
because the alternative was editing real configuration to test a theory, which is privilege
escalation (toolguard governs the agent, so the agent editing toolguard's config is the agent
editing its own permissions) and unrecoverable when the file is untracked. It happened twice
during TOO-19.

```python
with experiment(project_config='[permissions]\nallow = ["Bash(ls *)"]') as s:
    s.evaluate("Bash", "uv run python -c 'x'")   # -> ask, via the ASK floor
```

Isolation is structural rather than by discipline. `Path.home()` and
`config.find_project_root` are patched inward, the environment is cleared and rebuilt
(`CLAUDE_SETTINGS_PATH`, `TOOLGUARD_PROJECT_ROOT` and `CLAUDE_PROJECT_DIR` removed;
`XDG_CONFIG_HOME` pointed inside the sandbox rather than merely unset), and a tripwire raises
`SandboxEscapeError` on any write whose resolved path falls outside the sandbox root. The
tripwire is what makes this safe by construction instead of safe by inspection: an experiment
that *would* touch live config fails loudly rather than succeeding quietly.

`.evaluate()` delegates to `toolguard.api.decide`, the same side-effect-free
primitive behind the live hook and `--eval`, so a sandbox verdict matches the hook's by
construction. `.run_hook()` is the end-to-end form; it runs in a subprocess, so the in-process
tripwire cannot observe it and isolation there is by environment instead -- a weaker
guarantee, noted in its docstring.

There is a CLI for one-off questions, which is the point: the safe path has to be easier than
the unsafe one, or it gets bypassed under time pressure.

```bash
uv run python -m toolguard.testing.sandbox --config <file> --command "<command>"
```

Full flag list (see `toolguard/testing/sandbox.py::_build_argparser`):

- `--config FILE` -- PROJECT-level `toolguard_hook.toml` text to load into the sandbox.
- `--user-config FILE` -- USER-level `toolguard_hook.toml` text. Needed to reproduce a
  hierarchy/precedence question (project overriding, or failing to override, a user-level
  rule) -- omitting it means the experiment only has one level, so any cross-level question
  answers itself trivially.
- `--command COMMAND` (required) -- the Bash command, or the file path for a file-path tool,
  to evaluate.
- `--tool NAME` (default `Bash`) -- which tool to evaluate `--command` as. Without setting
  this, `Read`/`Write`/`Edit` cannot be evaluated at all -- the sandbox always checks against
  `Bash` unless told otherwise.
- `--hard-deny PATTERN` (repeatable) -- add one `[hard_deny]` pattern to the experiment; pass
  it more than once for several patterns.
- `--json` -- emit the verdict as JSON instead of human-readable text, for scripted use.

Anything worth running twice should become a unit test; the sandbox object is the same in
both places, so promotion is copy-paste. Not used by the hook, and not shipped as a user
feature -- development only. `ConfigIsolationMixin` was deliberately NOT consolidated into it
(the tripwire is a stricter contract that may expose latent isolation violations in the
existing suite; that discovery should be deliberate, not a side effect of a safety fix).

## Shadowed-hook detection and install hardening (TOO-19)

`PYTHONPATH=.` exported from a shell rc file made a source checkout of this repository SHADOW
the installed toolguard package for every process whose working directory happened to be that
checkout -- including the tool venv's own interpreter running the live PreToolUse hook. The
hook silently governed real permission decisions with uncommitted, mid-refactor code for weeks
before this was noticed. `toolguard/install_provenance.py` is the fix's detection layer;
`toolguard/session_start.py` and `toolguard/tools/environment_audit.py` are its consumers.
User-facing rationale:
[docs/security.md: The hook can be silently shadowed](docs/security.md#the-hook-can-be-silently-shadowed).

### Why the two footguns need different flags

Measured directly, not assumed:

- **Console-script invocation** (`toolguard` from `~/.local/bin/`): `PYTHONPATH` alone is the
  cause. Unsetting it fixes shadowing with no other change.
- **`-m` invocation** (`python -m toolguard.hook`): Python ALSO prepends the current working
  directory to `sys.path` for a `-m` invocation, so `-E` (ignore `PYTHONPATH`) alone is
  insufficient -- `-E -P` is required. Verified: `python -E -P -m toolguard.rule_entry` fails
  with "No module named" (the installed copy is governing, as intended, and this environment
  has none installed) while plain `-m` resolves the working tree instead. `toolguard/hook.py`
  already carries an `if __name__ == "__main__": main()` guard, so `-m toolguard.hook` is a
  valid, and the deliberately chosen, entry form for the hardened registration -- see
  [Installer hardening](#installer-hardening-and-its-one-real-risk) below for why the
  registered command uses `-m` at all rather than just hardening the console-script shim.

### `toolguard/install_provenance.py` -- placement rationale

A new, small, stdlib-only leaf module rather than a home in `toolguard/path_utils.py` or
`toolguard/tools/`, for two independent reasons:

- **Not `path_utils.py`.** That module's documented charter is project-root MARKER discovery
  (the shared "climb toward home" walk-up config/env loaders and the migration gate use) --
  a different question from "which toolguard package/distribution is this". Folding install
  provenance in would muddy an already-precisely-scoped leaf module for a concern its own
  callers (`toolguard.config`, `toolguard.env_config`) have no reason to import.
- **Not `toolguard/tools/`.** That package is documented as deliberately segregated from the
  runtime permission-evaluation path (`toolguard/tools/__init__.py`), so that automation
  tooling concerns never bleed into the hook's import graph. `toolguard/session_start.py` --
  the primary consumer here -- currently imports only `toolguard.config` at module level, and
  this change keeps it that way: `install_provenance` is a top-level `toolguard/*.py` leaf
  module, importable from both `session_start.py` (session-level, not `tools/`) and
  `toolguard/tools/environment_audit.py` (which, like every other analyser in `tools/`, freely
  imports top-level `toolguard.*` modules) without creating a new dependency in either
  direction.

`governing_package_root()` deliberately does NOT import the `toolguard` top-level package to ask
"where was I imported from" -- it uses `Path(__file__).resolve().parent` from INSIDE
`install_provenance.py` itself, which is exactly the currently-governing copy for whichever
process is running this code, with no risk of a second, separate import resolving differently.

### The clean-tree predicate (stale-install detection)

`stale_install_report()` answers "does the installed copy's content differ from this working
tree", but ONLY reports `is_stale=True` when the working tree is confirmed CLEAN under
`toolguard/` (`git status --porcelain -- toolguard` prints nothing) AND its content hash
differs from the installed copy's. Every other outcome -- dirty, undetermined (no git, not a
work tree, subprocess failure), or no installed distribution found at all -- reports
`is_stale=False`. This is deliberate, not an oversight: during active development the tree
differs from the installed copy constantly, so warning on a dirty tree would be pure noise and
train the reader to ignore the message; and uncertainty (git unavailable) must never be
silently promoted into a claim, so it resolves to silence rather than a guess. The content
comparison itself (`_hash_py_files`) hashes every `.py` file's relative path and byte content
in SORTED RELATIVE order (not filesystem iteration order, and not tied to either root's
absolute path), so two directories with the same internal layout hash identically regardless of
creation order or where they happen to live on disk.

This is intentionally a DIFFERENT comparison from the `toolguard-update-check` console script
(TOO-16; CLI in `toolguard/update_check.py`, detection/comparison logic in
`toolguard/install_update.py` since TOO-45 R5c), which compares a local checkout's git HEAD
against `git ls-remote origin HEAD` -- a git-history freshness question. `stale_install_report()` compares ACTUAL FILE CONTENT currently sitting in
site-packages against the checkout's current content, which is the only check that has any
signal for the specific scenario this was built for: a machine deliberately governed by a local,
unpushed build (`uv tool install /local/path toolguard`), where there IS no useful remote to
diff against. `installed_distribution_root()` locates that installed copy via
`importlib.metadata.distribution()`, which walks `sys.path` for the matching `*.dist-info`
directory the same way `pip`/`uv` left it -- succeeding even while the import itself is being
shadowed, since dist-info discovery and the actual import resolution are separate mechanisms.

### The SessionStart gate: only inside toolguard's own repo

Both `toolguard-session-start` checks are gated on the ACTIVE SESSION's project itself being a
toolguard source checkout (`config.project_root` has a sibling `pyproject.toml` naming
"toolguard" next to a real `toolguard/__init__.py`) -- not on whether the copy governing this
particular process happens to be a checkout. The reason: `PYTHONPATH=.` is a RELATIVE entry, so
it only actually shadows anything when the process's cwd -- which Claude Code sets to the
ACTIVE PROJECT for that session -- literally contains a `toolguard/` package, i.e. only in a
session working inside a toolguard checkout (or one improbably named the same). Gating on
`config.project_root` rather than blindly reporting `governing_package_root()`'s classification
means the check answers the question a developer working on toolguard itself actually has
("is MY checkout the one making decisions right now"), and stays silent for every other project
a user happens to open Claude Code in, where the question is meaningless. `ShadowStatus.
running_from_checkout` then additionally requires `governing_package_root()` to equal that SAME
checkout's `toolguard/` directory (not merely "some checkout somewhere") -- true live shadowing,
not just "you happen to be developing toolguard right now with a correctly installed hook".

### The audit predicate: `PYTHONPATH` content, not process provenance

`toolguard/tools/environment_audit.py`'s `audit_environment()` finding
(`pythonpath-shadows-hook`, HIGH) fires on a PURELY PREDICTIVE question -- does `PYTHONPATH`
contain an entry under which a `toolguard/` package exists -- read directly from the
environment, never from how the CURRENT process (`toolguard-audit` itself) was launched or
imported. This distinction is load-bearing: `toolguard-audit --dev` legitimately runs from this
source tree on purpose (see `CLAUDE.md`'s "Running toolguard's own skills against this repo"),
which says nothing about whether an ordinary `toolguard` PreToolUse hook invocation -- launched
separately by Claude Code, but sharing the same shell environment -- would ALSO be shadowed. A
predicate keyed to "how was I invoked" would be silent exactly when it needs to fire (an
Arnon-style `--dev` audit run with a genuinely shadowing `PYTHONPATH` still set) and would fire
on the harmless case (`--dev` with no `PYTHONPATH` shadowing risk at all). Reading the
environment directly avoids both failure modes. The finding follows the same
silent-in-the-normal-case shape as `takeover_audit.py`'s `loose-undecidable-fallback`: a
positive boolean predicate that is false for essentially every real environment, so it never
trains a reader to ignore audit output.

### Installer hardening, and its one real risk

`toolguard-install register-hooks` registers the PreToolUse hook as
`<tool venv python> -E -P -m toolguard.hook` (`_hardened_hook_command` in
`toolguard/tools/installer.py`) rather than the bare console-script path it used to write. The
interpreter path is derived from `--binary` by resolving ONE level of symlinks
(`Path(binary).resolve().parent`) -- for a `uv tool install`, `~/.local/bin/toolguard` is a
symlink whose target is the real script inside `.../uv/tools/toolguard/bin/`, and every such
`bin/` directory ships a `python3`/`python` SIBLING that is the correct interpreter for that
exact venv. The sibling's own path (not a further-resolved target) is what gets written, so it
survives a later `uv tool install --force`, which recreates the same venv directory in place
rather than moving it -- verified against the real machine layout during this ticket
(`~/.local/share/uv/tools/toolguard/bin/python3` is a stable symlink name across reinstalls,
even though what it points at, the shared managed interpreter, can itself change version).

**The one risk that matters: a hardened command bakes an ABSOLUTE interpreter path into
settings.json.** If that path is ever wrong -- and Claude Code's own hook contract makes this
concrete, not theoretical: only exit code 2 blocks a `PreToolUse` hook, and ANY OTHER outcome,
including the process failing to launch at all (`ENOENT` on a missing interpreter), is a
**non-blocking hook error** -- the tool call proceeds with NO toolguard decision whatsoever,
silently. That is strictly worse than the shadowing problem this hardening exists to close: a
shadowed hook still governs, just with the wrong code; a broken hardened path governs NOTHING
and produces no prompt telling you so. `_tool_venv_python()` therefore verifies the candidate
interpreter both EXISTS and is EXECUTABLE (`os.access(..., os.X_OK)`) before it is ever
returned, and `_hardened_hook_command()` falls back to the bare, unhardened, but WORKING
`--binary` path when no verified interpreter can be found -- an unhardened hook that runs is
always preferred over a hardened one that might not. `cmd_skills_status` (`skills-status`, the
installer's read-only status/verify path) additionally re-checks an EXISTING hardened
registration's recorded interpreter path against disk and reports `interpreter_missing=True`
if it no longer exists, so a later reinstall that relocates the venv is caught by a diagnostic
rather than discovered only when a tool call silently stops being governed.

SessionStart's own hook registration was deliberately left UNHARDENED in this pass (still the
bare `<binary>-session-start` form) -- the ticket's own line-pointer named only the PreToolUse
registration, and `toolguard-session-start`'s `main()` is wrapped in a broad
`except Exception` and always exits 0, so a shadowed or broken SessionStart process degrades to
"no session-start message this session" rather than a security-relevant silent failure. This is
a known, accepted asymmetry, not an oversight: if it ever needs closing, the same
`_hardened_hook_command` helper generalises directly to a `toolguard.session_start` module
form.

**A second, stronger reason surfaced by code review (TOO-19 s1, 2026-08-02): hardening
SessionStart would not just be an unnecessary asymmetry, it would actively break the shadow
detection this whole section exists for.** `_detect_shadow_status()` (`toolguard/session_start.py`)
compares `install_provenance.governing_package_root()` -- which `toolguard` package is ACTUALLY
governing the currently-running process -- against the active session's own source checkout, to
tell live shadowing (a `PYTHONPATH`-shadowed checkout governing decisions) apart from a properly
installed distribution. `-E -P` are exactly the flags that make Python ignore `PYTHONPATH` and
cwd when resolving imports (see "Why the two footguns need different flags" above) -- which is
precisely what makes the PreToolUse hardening correct THERE, but would make
`governing_package_root()` inside a hardened SessionStart process resolve the installed
distribution UNCONDITIONALLY, even from a session working inside a genuinely shadowing checkout.
Shadow/stale-install detection would go permanently and silently blind: not an error, not a
degraded message, just a feature that stopped noticing the exact condition it was built to catch,
with no test failing to say so. This makes UNHARDENED not a preference but an invariant:
`cmd_register_hooks` in `toolguard/tools/installer.py` carries a comment at the
`session_start_binary` assignment stating it, and
`test/unit/test_tools_installer.py::TestRegisterHooks::test_session_start_hook_is_never_hardened`
fails, with a message naming this reason, if that ever regresses.
