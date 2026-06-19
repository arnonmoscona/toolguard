# Toolguard Technical Notes

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
`.claude/` subdirectory. The walk never ascends above `~`.

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

The level cascade is orchestrated by `Configuration.resolve_permission_detailed`
(fed by `Configuration.permission_levels_with_provenance(tool)`). Pattern
MATCHING stays in `permissions.py`/`compound.py` (and the file-path matcher in
`hook.py`); those provide a per-level
`decide(allow, deny) -> (decision, reason, matched_pattern) | None` callable.
A single-level config behaves identically to the old deny-first model, so there
is one resolution path with no legacy/dual code.

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
`hook._check_file_path_hard_deny`. There is no behaviour change when no
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
| `logs/toolguard-YYYY-MM-DD.md`        | `log_writer.log_command`       | Resolution log (high volume): allowed/refused decisions, matched-rule provenance. Also `log_writer.log_discovery` (once-per-session discovery diagnostic) and `hard_deny` denials. |
| `logs/toolguard-error-YYYY-MM-DD.md`  | `error_log.log_error`          | REAL errors only. |
| `logs/toolguard-warning-YYYY-MM-DD.md`| `error_log.log_warning`        | Actionable warnings: both-`.toml`-and-`.json` present, unsupported/ungoverned tools. |
| `logs/toolguard-conflict-YYYY-MM-DD.md`| `error_log.log_conflict`      | Config conflicts (allow-over-deny overrides), human/LLM-readable, ON by default. |

`error_log._log_entry(level, stream, ...)` is the single shared writer; the
`stream` argument selects the `toolguard-<stream>-...` filename. All three share
the same Markdown entry format and echo a concise line to stderr.

The **takeover "active" notice** (`session_warnings.issue_takeover_warning`) is
informational, NOT actionable, so it is **no longer persisted to any log**: it is
stderr + a once-per-session marker file only.

### Conflict logging -- allow-over-deny overrides only

A **conflict** is a MORE-specific level's `allow` overriding a LESS-specific
level's `deny` for the same command/path. The decision is unchanged
(more-specific-wins keeps the allow); a conflict entry is written to the conflict
log citing BOTH sides' provenance (winning allow's file/level + the overridden
deny's file/level) and the command. `hard_deny` denials are **not** conflicts --
they are recorded in the resolution log (with provenance), never the conflict log.

Detection lives in `Configuration.resolve_permission_detailed` /
`Configuration._detect_override`: when the winning decision is an `allow` at level
*k*, the LESS-specific levels are scanned for a `deny` match on the same command;
the first match becomes a `ConflictOverride`. The hook
(`_log_conflict_override` / `_format_conflict_message`) routes it to the conflict
stream.

### Provenance threaded into resolution reasons

`Configuration.permission_levels_with_provenance` is the provenance-carrying level
view (per level: `(allow, deny, ToolPatternLayer[])`). The detailed deciders
(`permissions.decide_command_at_level_detailed`,
`hook._decide_file_path_at_level_detailed`) report the matched pattern, which
`Configuration._provenance_for_pattern` maps back to the owning
`ToolPatternLayer.provenance` for exact file/level precision.
`resolve_permission_detailed` returns a `ResolvedDecision`
(decision, reason, provenance, optional override). For **backward compatibility**,
provenance is appended to the reason as a bracketed suffix
(`_append_provenance` -> `Provenance.describe_brief`), e.g.
`Command matches allow pattern: git *  [project: /p/.claude/toolguard_hook.toml]`,
so existing `reason.split(': ', 1)` and "matches allow pattern: X" substring
consumers still work. Applied to Bash, each compound sub-command independently,
and Read/Write/Edit.

There is a single cascade implementation: the hook drives
`resolve_permission_detailed` / `resolve_file_path_permission_detailed` /
`hook.resolve_bash_permission_detailed`. (The earlier 2-tuple variants
`resolve_permission` / `resolve_file_path_permission` and their per-level helpers
`decide_command_at_level` / `make_command_level_decider` were removed once the
detailed path superseded them; no separate legacy cascade remains.)

### Once-per-session discovery diagnostic (M2)

`hook` emits, once per session (guarded by `_discovery_diagnostic_done`), a
`discovered N config levels: <level: path>, ...` entry to the RESOLUTION log via
`log_writer.log_discovery` (fed by `Configuration.describe_levels`). This replaces
the discovery diagnostics that the legacy `_load_permissions` printed to stderr.

### Single source of truth for the both-formats warning (M1)

The "both `.toml` and `.json` exist" warning is detected ONLY in
`Configuration.validation_issues()` and routed by the hook to the WARNING stream.
Discovery (`_discover_in_dir`) is side-effect-free (no stderr print). The Issue
fires in real usage by checking on-disk presence of the sibling file (discovery
keeps only the TOML), and also when two differing-format layers share a base.

### Single source of truth for tool-wrapper stripping

Permission patterns are authored wrapped as `Tool(inner)` (e.g. `Bash(git *)`)
but matched on the unwrapped inner pattern. `config._strip_tool_wrapper` is the
single, purely STRUCTURAL strip (`re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)')`): it
needs no hand-maintained tool list and handles inner parentheses
(`Bash(foo(bar))` -> `foo(bar)`). Divergence detection recognises tool-scoped
native permissions via the shared `config.is_tool_wrapper` predicate, which uses
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

### `governed_tools` and takeover pattern lists -- UNION across all levels

`Configuration.governed_tools()` is a UNION across all toolguard_hook layers in
the hierarchy (de-duplicated, first-occurrence/most-specific-first order),
defaulting to `('Bash',)` when nothing is configured. It now resolves over the
hierarchical `self.layers` (not the legacy 2-level `_load_governed_tools`), so it
is consistent with permission and takeover resolution and applies under
`CLAUDE_SETTINGS_PATH` mode (the explicit source is the only layer).

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
