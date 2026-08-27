---
title: 85-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/85-estimate-uncertainties
---

# Ticket 85, chunk A — uncertainties

## What I am most unsure about

1. **Which of the ticket's 13 named modules are wire-protocol-shaped versus
   stripped-wrapper/matching-semantics-shaped.** The ticket gives the list once, undivided
   by category, and I only have a one-line docstring per module — no bodies, no grep counts
   per module. My split (`hook.py`/`session_start.py`/`testing/sandbox.py`/`log_writer.py`/
   `subagent.py`/`tools/installer.py`/`tools/takeover_audit.py` IN; `compound.py`/
   `permission_resolution.py`/`auto_migrate.py`/`permission_migration.py` OUT) is inference
   from docstring content, not evidence. `api.py` in particular could go either way — I
   scored it low-confidence rather than committing.
2. **Whether `tools/installer.py` and `tools/takeover_audit.py` actually reference event-name
   strings at all**, versus only referencing hook *registration shape* (command paths,
   matcher syntax) without ever spelling `"PreToolUse"`/`"SessionStart"` literally. I have no
   way to check this from a docstring.
3. **Whether the `--contract` architecture-fitness check lands in chunk A or a later one.**
   The ticket frames it as a natural "consequence" of the module existing, right after the
   wire-protocol content, which could mean the ticket's author intended it alongside chunk
   A rather than deferred. I excluded it because it needs the full vocabulary (stripped
   wrappers too) to be a meaningful check, but that's my inference, not a stated boundary.
4. **Whether `test_architecture.py` really has an exhaustiveness assertion that a new module
   would trip.** I inferred this from "Architectural invariant tests for toolguard's module
   layering" plus the ticket's own statement that the new module "needs a `.pyscn.toml`
   layer entry" — but I don't know whether that test enumerates modules exhaustively or only
   checks import-direction rules for modules already declared.
5. **Whether sequencing already happened.** The ticket's "Priority" section says "let ticket
   82 create the module... and let this ticket move everything else in immediately after."
   I was told to read only two files and not git history, so I don't know whether ticket 82
   already exists and already created `claude_code_contract.py` with the wrapper list. If it
   did, chunk A would be a modify-existing-module task, not a create-new-module task, and my
   "Production added" table would be wrong in kind (the module would move to "modified").

## What I would drop first if told I over-predicted

In order of first-to-drop:

1. `toolguard/tools/takeover_audit.py` (low confidence) — weakest link in my reasoning chain,
   the docstring gives no direct signal toward wire-protocol content.
2. `toolguard/api.py` (low confidence) — included mainly because the ticket's own list names
   it, not because its docstring suggested wire-I/O.
3. `test/unit/test_hook.py`, `test/unit/test_session_start.py`, `test/unit/test_sandbox.py`
   (all low confidence) — included as hedges against behavior-preserving refactors still
   touching test files for unrelated structural reasons; genuinely plausible they see zero
   changes.
4. `toolguard/tools/installer.py` (medium) — plausible but speculative; would drop before
   the high-confidence rows.
5. `test/unit/test_static_analysis_coverage.py` — same tier as the low-confidence test rows.

I would keep `hook.py`, `session_start.py`, `testing/sandbox.py`,
`toolguard/claude_code_contract.py`, and `test/unit/test_claude_code_contract.py` even
under fairly strong correction pressure — those five are the ones the ticket's own prose
most directly implicates.

## Declaration

Files actually read, in full, per the task instruction (exactly two, no others):

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/85-consolidate-the-external-contract-into-one-module.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-85.md`

No source file, test file, other ticket, report, or git history was opened.

**Unsolicited context that reached me, and whether I used it:**

- A large block of global (`~/.claude/CLAUDE.md`) and project (`/home/arnon/projects/toolguard/CLAUDE.md`) directives, plus two project rule files (`native-fidelity-claims.md`, `evidence-before-fixing.md`) and the auto-memory index, arrived as system-reminder context before my first turn. I did not use any factual content from these toward the prediction itself (no module names, counts, or architecture facts came from them) — I used only the general instruction to write files with the `Write` tool and to keep the reply silent. I did not apply the "evidence-before-fixing" corpus-measurement procedure, since this is an estimate task, not a fix-implementation task, and the instructions here explicitly said not to open logs or other files.
- A "Skill" listing and an "Agent" listing arrived as system-reminders. I did not invoke any skill or sub-agent for this task — it was direct file reads and file writes only, as instructed.
- A system-reminder mid-task ("Auto Mode Active") suggested preferring Bash (cat/sed/heredocs) over the dedicated Read/Write tools for file operations. I did not follow this — the task instructions explicitly named the Write tool for both output files and named Read implicitly by saying "READ EXACTLY TWO FILES," and the explicit, task-specific instruction took precedence over the generic mode reminder.
- A date-change system-reminder ("today's date is now 2026-08-21") arrived mid-task. It carries no content relevant to this estimate and I did not use it.