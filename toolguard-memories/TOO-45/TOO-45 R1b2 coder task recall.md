---
title: TOO-45 R1b2 coder task recall
type: note
permalink: toolguard/too-45/too-45-r1b2-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

R1b2: instrument-only. Extend `tools/architecture_fitness.py` so R1's predicate also detects bare verdict-tuple returns (functions under `toolguard/` returning a tuple literal or annotated `Tuple[...]`/`tuple[...]` of 3+ elements that looks like a verdict), and fold that into R1's pass gate (pass only when exactly one runtime verdict type, zero `__iter__` shims, AND zero bare verdict-tuple returns).

Brief at `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r1b2_brief.md`.

## Hard constraints
- No production changes: tools/ and test/ only, nothing under toolguard/.
- Do NOT hand-maintain a list of function names. Must use a structural signal, stated in code.
- Must not flag strict pairs or non-verdict 3-tuples (path/message, ok/value, coordinates, spans).
- Must flag the 6 in compound.py, and as many of the 16 (from R1 scoping trace) as the criterion honestly reaches.
- If fewer than 16 caught, say so honestly with a miss list -- do not stretch the rule.
- Group output by module, function name + line, like existing predicate output.
- Unit tests with synthetic source, both directions: verdict 3-tuple caught; strict pair + non-verdict 3-tuple not flagged.
- NEVER git checkout/restore/stash/reset. Read-only git only. Back up to scratchpad/r1b2-backups/ with sha256 verify if any production file must be touched (shouldn't be needed here since instrument-only).
- Don't disturb uncommitted tree. Don't commit. Don't copy repo. Don't edit outside repo.
- uv run python always. unittest not pytest. ruff check --no-cache.

## Candidate signals from brief (evaluate both)
1. Annotated return type is tuple of 3+ elements, >=1 decision-like type, name/annotation mentions decision/verdict/reason.
2. Return literal 3+ wide tuple whose first element is, across ALL return statements in the function, consistently one of "allow"/"deny"/"ask" string literals. (Brief says this is the stronger signal, likely catches compound.py.)

## Acceptance commands
```
uv run python -m unittest discover -s test -t .
uv run python tools/corpus_build.py --verify
uv run python tools/architecture_fitness.py --guard      # expect PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates # R1 should now FAIL with tuple list
uv run ruff format . && uv run ruff check --no-cache .
```

## Report target
basic-memory project toolguard, note `TOO-45/TOO-45 R1b2 tuple predicate report.md`, tagged task-memory + TOO-45. Lead with new R1 baseline + flagged list, then criterion chosen/rejected. No hard-wrapped paragraphs.

## Status
Started planning phase.


## Status: DONE

Implementation complete. Detector `find_bare_verdict_tuples` added to `tools/architecture_fitness.py`, wired into R1's gate and rendering. 13 hits found on the real tree (all 6 compound.py, all 3 hook.py, plus 2 permissions.py, 2 resolve.py). R1 now FAILs as expected. Full suite 2349 OK, corpus verify clean, guard PASS (12 canaries), ruff clean. No production code under toolguard/ touched. Full report: `TOO-45/TOO-45 R1b2 tuple predicate report.md`.
