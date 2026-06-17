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

The level cascade is orchestrated by `Configuration.resolve_permission` (fed by
`Configuration.permission_levels(tool)`). Pattern MATCHING stays in
`permissions.py`/`compound.py` (and the file-path matcher in `hook.py`); those
provide a per-level `decide(allow, deny) -> (decision, reason) | None` callable.
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

### Single source of truth for tool-wrapper stripping

Permission patterns are authored wrapped as `Tool(inner)` (e.g. `Bash(git *)`)
but matched on the unwrapped inner pattern. `config._strip_tool_wrapper` is the
single, purely STRUCTURAL strip (`re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)')`): it
needs no hand-maintained tool list and handles inner parentheses
(`Bash(foo(bar))` -> `foo(bar)`). Divergence detection recognises tool-scoped
native permissions via the shared `config.is_tool_wrapper` predicate, which uses
the same `_TOOL_WRAPPER_RE` -- there is no duplicated regex in
`config_divergence.py`. New governed tools require no change to any prefix list.
