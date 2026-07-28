# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.
General guidelines that apply to all projects are in `~/.claude/CLAUDE.md`, which is
loaded automatically by Claude Code before this file.

## Project overview

The toolguard project is primarily a Claude Code hook for better management of permissions
than what is provided out of the box. It can be used in other ways as well. The main tools
it governs are `Bash`, `Read`, `Write`, `Edit` with the most attention devoted to `Bash`.
Toolguard provides extended syntax to support a richer expression of permission rules.
Specifically, it allows configuring permissions in the native Claude syntax (as a drop-in
replacement to the native configuration), but also supports regular expression command
matching and glob expression command matching (glob is natively supported for Read, Write,
and Edit -- but not for Bash).

The functionality of the tool is documented in detail in the project's [README](README.md).

## Architecture and design constraints

The tool is designed to have minimal runtime dependencies, so that execution only requires
the Python standard library. We add dependencies only when absolutely necessary.

For development we have one major dependency: the `canopy` parser generator. In order to
parse the bash commands Claude issues and match them against rules, one must break compound
commands into parts and evaluate each part separately -- otherwise the permission rules
become complex and brittle. Parsing with pure-Python regular expressions is crude,
error-prone, and extremely difficult to reason about and debug. Therefore **we avoid doing
any custom parsing of bash commands and instead rely on a formal PEG grammar for all
parsing**. From the formal grammar file (`toolguard/parser/bash_parser.peg`) we generate a
Python base parser using `canopy` (must be installed on the development system) and this
parser is used by `command_extractor.py` to break compound commands into parts. Note that
the grammar is not a full bash grammar -- it is only intended for the sole purpose of
breaking up compound commands from patterns often used by Claude Code. Canopy creates no
runtime dependencies as the generated Python code depends only on the standard library.

### Claude bad tendencies

Claude has a strong tendency to implement parsing using regex and pure python. Often when instructed to make grammar changes, even if explicitly told to use the PEG parser and canopy, it would still use convoluted python code instead.

The solution for this is to:
* Always use the feature-coder subagent for the implementation
* Require feature-coder to do the grammar changes first **only** in the PEG grammar file, validating by running canopy on it but without making any python file changes, which then gets reviewed before proceeding
* In a second phase, after reviewing the PEG changes, feature-coder is invoked to complete the python side of the change
* Even then it needs review because
  * It may still make new weird changes in the process - ones that should still belong in the PEG grammar
  * And it can create overly complex tree walking code, where it should really update the intermediate representation first (IR), and then end up with simpler, more readable processing code 

## Unit testing

Tests use the standard-library `unittest` framework (NOT pytest -- pytest is not
installed). Run the suite with:

```bash
uv run python -m unittest discover -s test -t .
```

**Every unit test function must carry a BDD/Gherkin-style description** (Given / When /
Then) in its docstring, stating the scenario under test and the expected outcome. This
makes the intent readable without reverse-engineering the assertions. Example:

```python
def test_more_specific_allow_overrides_parent_deny(self):
    """
    Given a parent level that denies a command and a project level that allows it
    When the command is evaluated under more-specific-wins resolution
    Then the project's allow wins and the command is permitted
    """
    ...
```

**Keep the BDD description and the test code in sync.** Whenever a test function is edited
so that what it does or expects changes, update its Given/When/Then to match in the same
edit. A stale BDD comment is worse than none -- treat it as part of the test, not optional
decoration.

### Coverage analysis (standard library only)

We avoid external coverage tools (`coverage.py`/`pytest-cov`). Use the stdlib `trace`
module via a small runner that executes the suite and writes annotated coverage:

```python
# tools/coverage_stdlib.py
import sys
import trace
import unittest

tracer = trace.Trace(
    count=True,
    trace=False,
    ignoredirs=[sys.prefix, sys.exec_prefix],  # skip the stdlib itself
)

def _run():
    suite = unittest.TestLoader().discover('test', top_level_dir='.')
    unittest.TextTestRunner(verbosity=1).run(suite)

tracer.runfunc(_run)
tracer.results().write_results(show_missing=True, summary=True, coverdir='cover')
```

Run it with:

```bash
uv run python tools/coverage_stdlib.py
```

This prints a per-module execution summary and writes annotated `cover/*.cover` files.
In those files, any source line prefixed with `>>>>>>` was never executed -- grep for it
to find gaps (e.g. `grep -rn '>>>>>>' cover/ | grep toolguard`). The `cover/` directory is
a build artifact -- add it to `.gitignore` (or write to a temp dir).

`ignoredirs=[sys.prefix, sys.exec_prefix]` keeps the stdlib out of the report, so only
`toolguard/` and test files appear. Note that `trace` provides line coverage only (no
branch coverage) and is slower than `coverage.py`; for finding untested lines in this
project that is sufficient.

## Announce intent before inline code and scratch scripts

Heredocs into an interpreter, `python -c` / `node -e` style inline code, and executing a
scratch script are the cases where what actually runs is least visible in the transcript --
and they are exactly the cases where the permission decision is hardest to make after the
fact.

**When this applies.** The test is not how long the command is -- it is whether the real
work lives in code the hook cannot see:

- **Announce**: heredocs into an interpreter; `python -c` / `node -e` / `perl -e` and
  friends; and **running a script written for the current action** (`uv run python
  tmp/probe.py`, `bash /tmp/fix.sh`, `node scratch.js`). These last ones are one-liners, but
  toolguard sees only a path -- the code itself never reaches the log or the prompt, which
  makes them the *most* important case, not an exception to it.
- **Do not announce**: ordinary one-liners whose full effect is visible in the command text
  (`grep`, `ls`, `git diff`, `uv run ruff check .`, `uv run python -m unittest ...`), and
  running a committed, reviewed script that is part of the project (`tools/coverage_stdlib.py`).
  The command already says what it does; a preamble adds noise without adding information.

When it applies, state your intent **as a Bash comment on the line(s) immediately before the
invocation**, so it travels with the command itself:

```bash
# INTENT: <what the code does, in plain language -- not a restatement of the code>
# TOUCHES: reads <paths>; writes <paths>  (say "writes nothing" when it writes nothing)
# INLINE BECAUSE: <why this is not a file you could have been asked to run>
uv run python - <<'PY'
...
PY
```

- [ ] **What** the code will do, in plain language (not a restatement of the code).
- [ ] **What it touches** -- which files or directories it reads, and which it writes.
- [ ] **Why** it is inline rather than a file you could have been asked to run.

**Use the comment form, not just prose in the terminal.** The comment is part of the
command text, so it reaches all three places that matter: the permission prompt (where
Arnon decides), the session transcript, and the toolguard log (`logs/toolguard-*.md`),
which otherwise records the command with no reasoning attached. A prose announcement in
the terminal reaches only the transcript. Add prose as well when the explanation needs more
room than a few comment lines, but never *instead* of the comment.

Verified 2026-07-28: a leading comment does not affect rule matching. `grep -c ... ` and
`# INTENT: ...` + `grep -c ...` both matched `Bash(grep *)` -- the PEG parser discards the
comment and matches the real leaf command -- and the log recorded the comment text.

This is not a request for permission and does not replace one. Arnon reads these when
deciding whether to keep or remove friction in the permission rules, so an accurate,
specific announcement is worth more than a short one.

If the honest answer to the third point is "no good reason", write the script to a file and
run `uv run python <file>` instead. That is a plain leaf command, it is allowed, it is
reviewable, and it matches this project's "no Bash for file operations" rule.

## Ticket tracking

Tickets for this project are prefixed by `TOO-`. Example: `TOO-123`.

To read a ticket:

```bash
~/projects/youtrack_api/get-issue.sh "TOO-123"
```

## Memory management

Use the basic-memory MCP server with `project='toolguard'` for all notes in this project.
See the global memory management guidelines (loaded via `~/.claude/common-memory.md`).

When creating memories in the context of a specific ticket, add the ticket ID as a tag
(e.g., `TOO-14`).

## Running toolguard's own skills in this repo: pass `--dev`

The `toolguard-maintenance` and `toolguard-security-audit` skills default to the
**installed console scripts** (`toolguard-maintain`, `toolguard-audit`) -- those are
what a normal `uv tool install toolguard` puts on PATH, and they run in toolguard's
own venv. That default is correct for every *other* project but wrong here: when we
work on THIS repo we want to exercise the working branch, not the installed release.

So whenever you run either skill against the toolguard project itself (development and
testing, as we usually do), invoke it with the **`--dev`** argument. That switches the
skill to the in-repo module form (`uv run python -m toolguard.tools.maintenance` /
`... .security_audit`). The skills also auto-detect the source repo as a fallback, but
prefer the explicit `--dev` -- it is unambiguous and does not depend on detection.

Never bake the `uv run python -m ...` form into a self-permission rule or into the
skill body; the dev-form lives only in each skill's "Development mode" section.

## Additional pre-push checklist items

* Check whether code changes in this change set require changes to the maintenance skill or the security audit skill
* Check whether changes in this change set require changes to install.md
* Do we need release notes?
* *After push* ask whether we should update the toolguard installation using `uv tool upgrade toolguard`

## Technical notes

Additional project-specific notes can be found in [technical-notes.md](technical-notes.md),
if the file exists.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

This project has `code-review-graph` installed. For general usage guidance (when it beats
`ag`/JetBrains MCP for searching, which capabilities matter most for code review and why),
see the global guidance: `~/.claude/common-search.md` (search lane selection),
`~/.claude/code-review-graph-search.md`, and `~/.claude/code-review-graph-review.md`. Do not
duplicate that guidance here -- only this project's own deviations from it are recorded
below.

### Project-specific caveats (verified 2026-06-29)

- **`tests_for` is unreliable on this repo.** The `TESTED_BY` heuristic misses
  class-based `unittest.TestCase` methods (which is how this project's tests are
  written -- not pytest), so `tests_for(fn)` returns false zeros. The underlying
  test->function `CALLS` edges DO exist, so to find a function's tests use
  `query_graph` pattern="callers_of" and filter to `is_test:true`.
- **Semantic search is true vector mode** -- embeddings are built (local
  `sentence-transformers`, ~2086 vectors) and communities are post-processed
  (igraph). `search_mode:"hybrid"` and the small (~0.015) scores are constant
  RRF fusion artifacts, NOT a sign of keyword-only fallback; ignore them. If a
  fresh `uv sync` ever wipes the venv, re-run `code-review-graph embed` +
  `postprocess` and restart the session to re-activate query-time embedding.

### Periodic maintenance (avoiding graph drift)

The **structural** graph (nodes/edges/calls/FTS) self-maintains: a `PostToolUse`
hook runs `code-review-graph update --skip-flows` after every Edit/Write/Bash, so
it stays current as code changes (and catches external changes -- git pull, IDE
edits -- on the first tool use of a session). The `SessionStart` hook only prints
`status`; it does not rebuild.

The **enrichment** layers do NOT auto-update and drift as the code evolves:

- **embeddings** -- new/renamed functions get no (or stale) vectors; semantic
  search silently degrades.
- **communities** -- only `postprocess` rebuilds them.
- **flows** -- the hook passes `--skip-flows`, so flows drift too.

Refresh them at checkpoints (end of a phase/slice, before relying on
`semantic_search`/`get_architecture_overview`, before an ultrareview):

```bash
uv run code-review-graph embed        # recompute vectors (local sentence-transformers)
uv run code-review-graph postprocess  # rebuild communities + flows + FTS (igraph)
```

**Suspect the embeddings are out of sync when:** `semantic_search` stops surfacing
recently-added functions, a concept query returns only older code, or you have just
landed a batch of new/renamed functions (a new module, a big refactor). Confirm via
`list_graph_stats` -- compare `embeddings_count` against the function+class+test node
count; a large shortfall means new nodes are unembedded. Fix: run `embed` (then a
session restart is only needed if the MCP **server process** itself must reload a
newly-installed embedding library; for a routine re-embed the running server picks up
the refreshed vectors from the DB). If structure itself looks stale (a function you
know exists is missing), force a full structural pass with
`uv run code-review-graph update` (or `build` for a from-scratch rebuild), then
`embed` + `postprocess`.

These commands are local, offline, and write only to the gitignored
`.code-review-graph/`.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. To check a function's test coverage, use `query_graph` pattern="callers_of"
   and keep `is_test:true` results (`tests_for` is unreliable here -- see caveats).
