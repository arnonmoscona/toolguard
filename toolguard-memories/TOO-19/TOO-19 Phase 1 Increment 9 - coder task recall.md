---
title: TOO-19 Phase 1 Increment 9 - coder task recall
type: note
permalink: toolguard/too-19/too-19-phase-1-increment-9-coder-task-recall
tags:
- task-memory
- TOO-19
- coder-latest-task-recall
---

## Task
TOO-19 Phase 1, increment 9: DOCUMENTATION ONLY. No production code changes. No git operations.

Repo: /home/arnon/projects/toolguard, branch too-19.

### What shipped (increments 1-8, 1949 tests green)
`additionalContext` is a REAL working feature:
- Structured rule entry: `{ match = "Bash(grep *)", additionalContext = "..." }`
- When that rule is the DECIDING match, text returned in hook JSON as
  `hookSpecificOutput.additionalContext`. Key OMITTED (not null) when nothing to inject.
- Works for allow, ask, deny, hard_deny (both Bash and file-path pools).
- Applies to all governed tools: Bash, Read, Write, Edit.
- toolguard config files ONLY - native Claude settings.json structured entry is
  rejected with warning, NOT interpreted.
- Value must be a string; non-string -> error-level validation issue but rule NOT dropped.
- Compound Bash: all-allow compound -> every allowed sub-command is decision-maker,
  contexts accumulate, one paragraph per contributing rule, blank line between, in
  match order. Dedup identical texts. Cap 500 words, greedy first-fit (paragraph that
  would exceed budget dropped WHOLE, never mid-sentence truncated; scan continues).
  Deny/ask compound: exactly one deciding leaf, its context passes alone, no accumulation.
- ASK-floor interaction: inline/heredoc-foreign-code ASK floor or config-parse-failure
  ASK floor clamps allow->ask => context DROPPED (floor decided, not the rule match).
  A deny detected on ASK-floor leaf DOES keep its context.
- Log (logs/toolguard-*.md) records it, capped 40-word preview + full word count.
- `toolguard --eval` and `python -m toolguard.testing.sandbox` report it.

### Deliverables
1. docs/configuration.md - correct "### Structured rule entries, and the single line rule"
   section (~line 349). Replace false "reserved for future release" paragraph. KEEP:
   toolguard's own tooling emits structured form; unrecognized key = validation warning,
   otherwise ignored. KEEP single-line-rule subsection + warning block UNCHANGED.
   Add worked example: realistic allow AND realistic deny with enrichment.
2. docs/configuration.md - new subsection covering: toolguard-config-only restriction;
   string-only values; deciding-match rule; compound accumulation+dedup+500-word cap;
   ASK-floor drop; works for allow/ask/deny/hard_deny across all governed tools.
   Add anchors to file's `## Contents` list at top.
3. README.md - concise section, one paragraph "what it's for" + ONE compelling example,
   link to docs/configuration.md for full behavior. Don't duplicate spec. Find right home
   near existing permission-syntax material.
4. Sweep other docs for staleness/cross-link: docs/architecture.md, docs/security.md,
   AGENTS.md, llms.txt, technical-notes.md. Look for: statements that additionalContext/
   enrichment keys are "reserved"/"not yet implemented"/"a no-op"/KNOWN_ENRICHMENT_KEYS
   empty - all now FALSE. Also docs/agent-map.md - summarizes every other doc, no other
   sync mechanism - update entries + TOC for every new heading.
5. Audience: no human reads docs end-to-end; agent-facing. Precise headings, short
   scannable sections, internal cross-links over narrative.
6. Style: plain ASCII. Single hyphens not `--` in HEADINGS (anchor slug issue, broken
   3x already). Body text may use `--`. Match direct second-person voice, state
   consequence not just rule.

### Verification required (all must pass before reporting)
- `uv run python tools/check_doc_links.py` must exit 0.
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -> still 1949 tests OK.
- Verify EVERY behavioral claim against actual code: toolguard/rule_entry.py,
  toolguard/compound.py::_accumulate_contexts, toolguard/hook.py::create_hook_output,
  toolguard/resolve.py. Do NOT just restate the summary - if discrepancy found, STOP
  and report rather than picking a version.

### Report
Write to basic-memory project `toolguard`, path
`TOO-19/TOO-19 Phase 1 increment 9 documentation report.md`, tags `task-memory`, `TOO-19`.
List every file changed, every anchor added, any discrepancy found, anything judged
out of scope.

### Constraints from CLAUDE.md
- Always `uv run python`, never bare python.
- No git write ops.
- Never edit outside repo.
- Bash disclosure rules apply if writing/running scratch scripts (INTENT/TOUCHES/
  INLINE BECAUSE comments + TG_INTENT/TG_ATTEST_READONLY env prefix) - but this task
  is doc-only so likely just uses standard tools (grep, doc link checker, unittest).
