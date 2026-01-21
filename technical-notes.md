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
