---
title: TOO-14 Claude Directives Refactoring
type: task-memory
permalink: toolguard/too-14/too-14-claude-directives-refactoring
tags:
- task-memory
- TOO-14
---

# TOO-14: Refactor Claude Code Directive Files

## Status: COMPLETE (toolguard scope)

## Objective

Centralize common Claude Code directives in `~/.claude/` and slim down per-project
CLAUDE.md files to only project-specific content. Work scope: toolguard project only.
Featherhill is deferred to a separate ticket.

## Deployed file layout

`~/.claude/` is a symlink to `~/projects/dot_files/wsl/.claude/` (version-controlled
dotfiles repo). All global config changes are automatically tracked there.

```
~/.claude/                               (symlink -> dot_files/wsl/.claude/)
├── CLAUDE.md                            global user directives (@ imports common-memory.md)
├── common-memory.md                     @ imported, launch-critical (boot procedure)
├── common-search.md                     markdown-linked (lazy load, loaded when needed)
├── rules/python.md                      glob paths:**/*.py, auto-loads for .py files
└── skills/code-review/SKILL.md         context:fork, agent:code-reviewer

toolguard/CLAUDE.md                      slimmed project-specific file
~/bin/recall_main_agent_conversation     wrapper script -> featherhill script
```

## Design decisions

- `common-memory.md` is `@` imported (launch-critical: contains boot procedure)
- `common-search.md` is markdown-linked (lazy load: only needed when searching)
- `rules/python.md` with glob applies globally to all projects, zero per-project setup
- Code review skill uses `context: fork`: isolated subagent, no conversation history
  bias, tokens don't pollute main context. Main agent opens report in IDE but does NOT
  read it unless explicitly instructed.
- `@` imports are NOT supported in rules files (design constraint confirmed by research)
- `~/bin/recall_main_agent_conversation` is a temporary wrapper; will be replaced when
  a proper uv-managed Python setup exists in ~/bin

## Remaining housekeeping

- Delete orphaned files: `toolguard/claude.code.review.md` and `toolguard/claude.search.md`
  (no longer linked from any config, harmless but dead weight)

## Deferred

- Featherhill project pass: separate ticket