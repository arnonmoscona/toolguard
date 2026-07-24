---
title: Code-review tooling cleanup - proposed changes (awaiting review)
type: note
permalink: toolguard/too-30/code-review-tooling-cleanup-proposed-changes-awaiting-review
tags:
- project
- tooling
- code-review
- implemented
---

## Status: IMPLEMENTED (2026-07-24)

All items below were approved and implemented in this pass. See
[[toolguard-memories/tooling/code-review-graph - install process for new projects]] for the follow-on install-process
proposal this work motivated.

## What was done

1. **`~/.claude/agents/code-reviewer.md`**:
   - `tools:` frontmatter fixed -- added `mcp__basic-memory__search_notes`,
     `read_note`, `write_note` (root cause of the basic-memory-unavailable bug found during
     TOO-30's own code review) plus a read-only `mcp__code-review-graph__*` subset.
     Explicit enumeration, no wildcards, per Arnon's instruction.
   - Removed the fake "context manager" JSON protocol blocks (Review Context Query, Progress
     Tracking) and the "Integration with other agents" section (referenced qa-expert,
     security-auditor, architect-reviewer, etc. -- none exist in this setup).
   - Replaced the fabricated "## MCP Tool Suite" section (listed git/eslint/sonarqube/semgrep
     as available when they weren't in the real tools list) with a pointer to
     `~/.claude/common-search.md` -- one shared source of truth instead of a second,
     independently-maintained list.
   - Reframed the hardcoded numeric checklist (coverage >80%, complexity <10, etc.) as
     defaults, explicitly overridable by a project's CLAUDE.md and an optional project-root
     `code-review.md`.
   - Left untouched (per round-1 decision): the generic topic-word-list middle section
     (Code quality assessment / Security review / Performance analysis / etc., lines ~29-260)
     -- flagged as condensable but never got explicit scope sign-off, so left as-is. Still
     open if Arnon wants to revisit.
2. **`~/.claude/skills/code-review/SKILL.md`**: bootstrap section gained two additions --
   reading an optional project-root `code-review.md` alongside CLAUDE.md, and a
   code-review-graph detection step that reads `~/.claude/code-review-graph-review.md`
   when the tool is present for that project.
3. **`~/.claude/common-search.md`**: new short third-lane section (structural graph search),
   pointing to the new dedicated file rather than inlining guidance -- kept deliberately
   brief so projects without the tool pay no context cost.
4. **New: `~/.claude/code-review-graph-search.md`** -- when code-review-graph beats
   ag/JetBrains MCP for general searching and when it doesn't, plus the edge-confidence
   caveat. Token/efficiency framing (appropriate for general search).
5. **New: `~/.claude/code-review-graph-review.md`** -- three-tier ranking of which
   capabilities matter most for CODE REVIEW specifically. Reframed per Arnon's explicit
   instruction: semantics/analytical-rigor framing, NOT token-savings framing (that
   framing lives only in the search-context file). Tier 1: `get_minimal_context_tool` first,
   `detect_changes_tool` (their own docs call it "the primary tool for code review"),
   `get_impact_radius_tool`/`get_affected_flows_tool`, `tests_for`/`callers_of` coverage
   verification, edge-confidence discipline. Tier 2: community clustering, architecture
   overview, hub/bridge centrality, surprising connections, suggested questions -- for
   substantial/cross-cutting changes. Tier 3: knowledge gaps, semantic search (for
   duplication checks), graph diff.
6. **Toolguard's own `CLAUDE.md`**: trimmed the code-review-graph section from ~118 lines to
   ~10. Removed everything now covered by the new global files (the generic pitch, "when to
   use graph tools first," the search-lane decision tree, the Key Tools table, the Workflow
   steps) -- confirmed this was installer-injected (`code-review-graph install`'s
   `--no-instructions`-suppressible behavior), not authored by Arnon. KEPT the two genuinely
   project-specific sections: "Project-specific caveats" (the `tests_for` unreliability bug
   and the semantic-search hybrid-mode/RRF-score quirk, both empirically discovered in this
   repo) and "Periodic maintenance" (the PostToolUse hook behavior and embed/postprocess
   refresh routine specific to toolguard's own hook configuration).

## Research finding: how to stop future installs from re-injecting this

`code-review-graph install --help` confirms: `--no-instructions` -- "Skip injecting graph
instructions into CLAUDE.md / AGENTS.md / etc." Also found `--no-skills` and `--no-hooks` for
completeness, though the install-process proposal recommends keeping skills/hooks enabled by
default and only suppressing instructions. Full recommended install command captured in the
follow-on proposal note.

## Verification not yet done

Have not yet re-run `/code-review` on a real scope to confirm the basic-memory fix and the
code-review-graph detection both work end-to-end post-fix. Worth doing before considering
this fully closed -- flagged for whenever Arnon wants to spot-check it.
