---
title: 74-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/74-estimate-uncertainties
---

# TOO-45 Item 74 — uncertainties

## Most unsure about

- **Where `governed_tools()` and `_REGISTRY` actually live.** The ticket's phrasing ("With
  `_REGISTRY = ()`, `governed_tools()` returns empty") reads to me as `tool_spec.py` internals by
  naming convention and by that module's declared role, but I have no direct confirmation. If
  `governed_tools()` is instead a `hook.py`-local function that merely *reads* `tool_spec`'s
  data, then my `tool_spec.py` prediction is wrong and the whole empty-registry fix stays inside
  `hook.py`.
- **Where hard-deny evaluation is centralized.** I don't know whether `hook.py` calls a
  `config.hard_deny(...)`/`permission_resolution` function that already handles hard-deny
  correctly (in which case the bug is purely "the hook skips calling it for out-of-registry
  tools," a `hook.py`-only fix), or whether hard-deny logic itself needs to change. I hedged this
  as a low-confidence line rather than dropping it, but it's the least-grounded row in my table.
- **Whether the "characterization" tests the ticket describes are already committed** (as part of
  the investigative work that produced this ticket) or are themselves part of the fix's own diff.
  If they're already in the tree, my test-file predictions are actually predicting *modifications
  to already-passing characterization docstrings/assertions* rather than net-new test code — same
  files, different nature of change, which doesn't affect the touch-set prediction but would
  affect a line-count estimate if one were asked for.
- **Whether `error_reporter.py` needs a change at all.** "Nothing reports 'governed nothing'"
  could be satisfied by a single new call to an already-generic reporter API from within
  `hook.py`, with zero changes to `error_reporter.py` itself. I kept it as a low-confidence row
  rather than dropping it because the module's report surface is unconfirmed from the two files
  I was allowed to read.

## Would drop first if told I over-predicted

In order: `toolguard/config.py`, `toolguard/permission_resolution.py`, `toolguard/error_reporter.py`,
then `test/unit/test_tool_spec.py`. All four are single-line, low-confidence hedges against
boundaries I couldn't see. `toolguard/tool_spec.py` and `test/unit/test_hard_deny.py` I'd drop
next if pressed further, but I hold those with more conviction (naming-convention inference for
the former; declared test-module scope for the latter). `toolguard/hook.py` and
`test/unit/test_hook.py` I would not drop — both findings are stated as living inside
`_resolve_event`, and the RED test is named as belonging to the hook test module.

## Declaration

**Files read (exactly two, as instructed):**

1. `/home/arnon/projects/toolguard/toolguard-memories/TOO-45/proposed-tickets/74-item-10s-conversion-stopped-at-the-hook-and-an-empty-registry-disables-hard-deny.md`
2. `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/briefing-74.md`

No other file, source module, test, report, or git history was opened. I ran one `Bash` command,
`mkdir -p .../reports/surprise`, which only creates a directory and reads nothing.

**Unsolicited project context that reached me and that I used:**

- The full contents of `~/.claude/CLAUDE.md` and the project's `/home/arnon/projects/toolguard/CLAUDE.md`
  were present in my system prompt before I did anything. I drew on the "Literal strings with
  semantic meaning belong in constants" and "Tests verify behavior, not shape" conventions when
  reasoning about *how* a fix would likely be shaped (e.g. expecting dispatch literals to become
  named constants, expecting behavioural rather than shape-only test assertions), and on the
  declared architecture layer list already embedded in the briefing file itself (not separately
  read).
- The auto-memory index (`MEMORY.md`) was present and named several toolguard-specific facts I
  did not otherwise verify, notably: `[[project_no_match_fallback_and_undecidable_ticket]]` on
  hardcoded-ask-floor behaviour, and `[[project_subagent_id_broken]]`. I did not use these in the
  prediction — they're about unrelated subsystems (no-match fallback, subagent logging) and I
  didn't let them influence the hook/registry touch-set guess.
- Git status in the environment block, listing modified/untracked files (several `test/unit/*.py`
  files as `M`, plus a large `toolguard-memories/TOO-45/...` untracked tree). I noticed this but
  deliberately did not use it to infer the touch set — those modifications belong to other,
  already-in-flight punch-list items (07 doc comments, etc.), not to this ticket, and treating a
  stale working-tree snapshot as signal for an unmade change would have been exactly the kind of
  leak this exercise is designed to catch. I did not open any of those files.
- Recent commit subject lines were visible in the environment block (Items 07, 03, 10, 15, 04). I
  recognized "Item 10" as the punch-list item this ticket's title refers to, which shaped my
  reading of "the conversion" as an already-completed piece of prior work rather than something
  I needed to guess at — but I did not open commit `2113d02` or any diff to see what it touched.
- The two system-reminder date-change notices and the "Auto Mode Active" reminder were present;
  neither influenced the prediction content. The auto-mode reminder's suggestion to prefer Bash
  for file edits was not followed for the two output files, since the task explicitly restricts
  file access to reading the two named inputs and writing the two named outputs — I used the
  `Write` tool directly rather than shelling out, and read nothing further via Bash.