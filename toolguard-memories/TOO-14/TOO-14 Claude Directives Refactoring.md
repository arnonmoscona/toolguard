---
title: TOO-14 Claude Directives Refactoring
type: task-memory
permalink: toolguard/too-14/too-14-claude-directives-refactoring
tags:
- task-memory
- TOO-14
---

# TOO-14: Refactor Claude Code Directive Files

## Objective

Centralize common Claude Code directives in `~/.claude/` and slim down per-project
CLAUDE.md files to only project-specific content. Work scope: toolguard project only.
Featherhill is deferred to a separate ticket.

## Design decisions

- `~/.claude/CLAUDE.md`: global file, @ imports only `common-memory.md` (launch-critical)
- `~/.claude/common-memory.md`: @ imported; contains boot procedure (read Current Task Context at launch)
- `~/.claude/common-search.md`: markdown-linked (lazy load); only needed when searching
- `~/.claude/rules/python.md`: glob `paths: ["**/*.py"]`; applies globally to all projects
- `~/.claude/skills/code-review/SKILL.md`: `context: fork`, `agent: code-reviewer`; isolated subagent
- @ imports NOT supported in rules files (design constraint)
- Code review skill uses forked context: no conversation history bias, tokens don't pollute main context

## Draft file locations

All drafts in `toolguard/tmp/drafts/`:

```
tmp/drafts/
├── dot-claude/                          → ~/.claude/
│   ├── CLAUDE.md
│   ├── common-memory.md
│   ├── common-search.md
│   ├── rules/python.md
│   └── skills/code-review/SKILL.md
├── project/CLAUDE.md                    → toolguard/CLAUDE.md
└── bin/recall_main_agent_conversation   → ~/bin/ (user places manually; wraps featherhill script)
```

## Status: Session 2 complete -- drafts finalized, ready for manual deployment

### Session 1 (previous)
- Researched Claude Code CLAUDE.md hierarchy, @ imports, rules glob, skills/fork
- Created all draft files in `tmp/drafts/`

### Session 2 (this session)
- Ran equivalence review subagent (forked) vs current config
- Ran skills opportunity analysis subagent (forked) -- verdict: no new skills needed
- Fixed all gaps found in first review pass:
  - Added `pyscn` external analysis tool to SKILL.md
  - Added post-review main-agent workflow to global CLAUDE.md (open in IDE, verify freshness, do not read unless instructed)
  - Added "Bash for file ops" to `rules/python.md` post-scan checklist
  - Added git hooks informational note to `rules/python.md`
  - Restored `beyondgrep.com` docs URL in `common-search.md`
  - Restored two-condition IDE misconfiguration detection in `common-search.md`
  - Added `mcp__basic-memory__search` to tools list in `common-memory.md`
- Rewrote SKILL.md with bootstrap context section (read project CLAUDE.md + task memory), explicit file-list scope handling, ticket ID stripping, pyscn step, date stamp for freshness
- Ran second-pass equivalence review -- confirmed all 7 gaps resolved
- Fixed remaining issues from second pass:
  - Fixed misleading link text in global CLAUDE.md (`common-code-review.md` → `Code Review Skill`)
  - Added "do not read report unless instructed" directive to code review section
  - Restored "if the file exists" caveat on `technical-notes.md` reference in project CLAUDE.md
  - Restored "configuration drift" explanatory note in `common-search.md`

## Next steps

1. Arnon deploys manually (files from `tmp/drafts/` → final locations)
2. Post-deployment correctness review (next session)
3. Eventually: featherhill pass (separate ticket)