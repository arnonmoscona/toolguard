---
title: code-review-graph - install process for new projects
type: note
permalink: toolguard/tooling/code-review-graph-install-process-for-new-projects
tags:
- tooling
- code-review-graph
- process
---

## Scope note

General, cross-project process -- not toolguard-specific. Filed in toolguard's memory
because that's the active session context, same as the code-review tooling cleanup proposal
this builds on. Assumes the global guidance from that cleanup already exists:
`~/.claude/common-search.md` (third lane pointer), `~/.claude/code-review-graph-search.md`,
`~/.claude/code-review-graph-review.md`, `~/.claude/skills/code-review/SKILL.md` (bootstrap
detection step), `~/.claude/agents/code-reviewer.md` (tools frontmatter).

## Why a process is needed now (not just "run install")

Before this session, `code-review-graph install` was toolguard's only encounter with the
tool, and its default behavior injected a full generic-capability section directly into
toolguard's own `CLAUDE.md` -- the exact thing this session just spent effort trimming,
since that content is now redundant with the new global guidance files. Confirmed via
`code-review-graph install --help`: `--no-instructions` ("Skip injecting graph instructions
into CLAUDE.md / AGENTS.md / etc.") exists specifically to prevent this. Going forward, every
new install should use it by default -- the global bootstrap-time detection (SKILL.md /
common-search.md) now does that job once, for every project, instead of each project's
CLAUDE.md carrying its own copy that immediately starts drifting from the tool's actual
current version.

## Pre-install checklist

- [ ] **Confirm the project actually justifies it.** Per the tool's own FAQ ("When should I
  not use it?"): repos under a few hundred files get marginal value from the raw
  token-reduction numbers specifically (an agent can often already hold the relevant code in
  context, and the graph response can exceed a trivial diff's own size). This does NOT mean
  skip it for small repos outright -- the semantic/structural value (blast radius, risk
  scoring, community clustering, not missing a related test/caller) holds regardless of size,
  per the reasoning already captured in `code-review-graph-review.md`. But skip it for a
  repo you genuinely won't revisit, or one so small a direct read is trivially sufficient
  (a handful of files).
- [ ] **Decide platform scope.** Default to `--platform claude-code` unless the project is
  also worked in another supported tool (Cursor, Windsurf, etc.) -- avoids configuring
  integrations that will never be used.
- [ ] **Decide embeddings.** Default: local `sentence-transformers` only
  (`pip install "code-review-graph[embeddings]"`), consistent with this environment's
  established preference for local-only dev-tooling dependencies (no cloud/API-based
  providers -- OpenAI-compatible endpoints, Google Gemini, MiniMax -- until a concrete need
  justifies the added external dependency and data-egress surface). Skip embeddings
  entirely for a project too small for semantic search to add value over exact-name lookup.
- [ ] **Decide hooks.** Default: keep the PostToolUse auto-update hook enabled (structural
  graph self-maintains after every Edit/Write/Bash -- this is what kept toolguard's graph
  current with zero manual effort). No known reason to disable it.
- [ ] **Decide skills.** Default: keep bundled skills enabled (`build-graph`, `debug-issue`,
  `explore-codebase`, `refactor-safely`, `review-changes`, `review-delta`, `review-pr`) --
  but see the open investigation item below before relying on `review-changes` specifically
  in a new project, since toolguard's own copy didn't appear in this session's active skill
  list for an unexplained reason.

## Install command

```bash
code-review-graph install --platform claude-code --no-instructions
```

Add `-y` to skip the interactive confirmation prompt if running this as part of an
otherwise-automated setup. Do NOT add `--no-skills` or `--no-hooks` per the defaults above
unless a specific project has a reason to deviate (record the reason in that project's
`CLAUDE.md` if so).

## Post-install checklist (Claude can do all of this)

- [ ] Run `code-review-graph build` if `install` didn't already trigger a build (check
  `code-review-graph status` first -- zero nodes means it didn't run).
- [ ] Verify MCP wiring: run `/mcp` and confirm the `code-review-graph` server is connected
  with its tools listed.
- [ ] Confirm the project's `CLAUDE.md` (and `AGENTS.md` if present) was NOT modified by the
  install (`git diff` before committing anything) -- `--no-instructions` should have
  prevented this; treat any injected section as a bug in the flag if one appears anyway.
- [ ] If embeddings were enabled: run `code-review-graph embed`, then `code-review-graph
  postprocess` (communities + flows + FTS). Confirm via `list_graph_stats_tool` that
  `embeddings_count` roughly matches the function+class+test node count.
- [ ] Sanity-check `review-changes` (and any other bundled skill) actually appears in a
  fresh session's active skill list before relying on it -- **open investigation item**:
  toolguard has had this skill installed since an earlier session, but it did not appear in
  this session's skill listing for an unexplained reason. Resolve this on the NEXT project's
  install (or by investigating toolguard's own gap directly) before assuming the bundled
  skills work out of the box -- don't silently assume it's fine a second time.
- [ ] Add a minimal "MCP Tools: code-review-graph" section to the project's own `CLAUDE.md`
  -- NOT the generic capability writeup (that's now global), just:
  ```markdown
  ## MCP Tools: code-review-graph

  This project has `code-review-graph` installed. For general usage guidance, see
  `~/.claude/common-search.md`, `~/.claude/code-review-graph-search.md`, and
  `~/.claude/code-review-graph-review.md`. Project-specific deviations from that guidance,
  if any are discovered through use, go here.
  ```
  Leave the "Project-specific deviations" area genuinely empty until a real deviation is
  found through actual use -- don't pre-populate speculative caveats (toolguard's own
  `tests_for`-unreliable caveat, for example, was discovered empirically, not predicted in
  advance).
- [ ] If embeddings are enabled, note the periodic-maintenance routine in that same
  project-local section (mirroring toolguard's, adjusted for that project's own hook
  config) -- the enrichment layers (embeddings, communities, flows) do not auto-update the
  way the structural graph does, and this is easy to forget until search quality visibly
  degrades.

## Open question, not resolved here

Whether to standardize on running this checklist personally per-project as each project
comes up, versus writing a small wrapper script/slash-command that runs the install +
post-install checklist mechanically. Given the checklist is short and mostly one-time per
project, a manual pass (with Claude executing the post-install half) is probably sufficient
for now -- revisit if this becomes a recurring, higher-frequency task across many projects.
