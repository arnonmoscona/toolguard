---
title: local-tools MCP server planned migration to user level
type: note
permalink: toolguard/notes/local-tools-mcp-server-planned-migration-to-user-level
tags:
- project
- mcp
- local-tools
- FLO-145
---

# local-tools MCP server: planned migration to user level

Ticket: **FLO-145** (featherhill project)

The `mcp__local-tools__*` tools (including `checked_bash`) currently live in the
featherhill project as a project-scoped MCP server. FLO-145 tracks the refactoring
to make it a user-level MCP server.

Once that refactoring is done, it qualifies to be registered at the user level
(`~/.claude/` config), at which point it will be available to all projects — not just
featherhill.

**Impact on current agent files**: All `~/.claude/agents/*.md` files already reference
`mcp__local-tools__checked_bash` (Mac paths were fixed 2026-06-12). No changes needed
to the agent files when the migration happens — only the MCP server registration in
`~/.claude/settings.json` will need to be added.
