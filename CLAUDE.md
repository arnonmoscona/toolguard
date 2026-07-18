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

## pre-push checks

When we're about to wrap up a ticket, and it seems that I am ready to push a set of changes to github, check the following and remind me:

* Have we verified that out code coverage is good enough?
* Did we do necessary documentation updates (you would know, as you participate)
* Should I bump the version in `pyproject.toml`
* Do we need any release notes?
* Run `pyscn analyze toolguard` to find issues, read the report, and discuss what to fix, what to defer, and what to ignore
* Consider running the toolguard maintenance skill to keep the toolguard configuration constantly curated. A push is a good checkpoint for this.
* If any doc under `docs/`, README.md, AGENTS.md, or llms.txt changed since the last push, run `/documentation-review` (`.claude/commands/documentation-review.md`). This is the main defense against documentation drift -- `docs/agent-map.md` in particular summarizes every other doc and has no other mechanism keeping it in sync, so it is the single most likely thing to go stale silently. Don't skip this just because a change looks small; several of this project's own past doc bugs were introduced by small, individually-reasonable edits.

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

## Technical notes

Additional project-specific notes can be found in [technical-notes.md](technical-notes.md),
if the file exists.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph.** For structural and
symbol-shaped questions it is often the best first stop -- faster, cheaper
(fewer tokens), and it gives structural context (callers, dependents, impact,
architecture) that file scanning cannot. It does **not** replace the global
search guidance in `~/.claude/common-search.md`; it is a third lane alongside
`ag`/`ack` and the JetBrains MCP. Reach for any of those three before defaulting
to Grep/Glob/Read -- see "How this fits the global search directives" below for
the division of labor.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of
- **Finding a function's tests**: `query_graph` pattern="callers_of" and keep the
  `is_test:true` results -- **NOT** `tests_for` (see caveats below)
- **Architecture questions**: `get_architecture_overview` + `list_communities`

When the graph doesn't fit, choose the next lane by the rules below -- not
automatically Grep.

### How this fits the global search directives (don't bury them)

The global guidance in `~/.claude/common-search.md` still governs. This graph is a
**third lane**, not a replacement. Decision order for this repo:

- **Text-anchored** (string literal, comment, log message, config value, TODO, or any
  gitignored / just-created file): **`ag`/`ack`** -- the graph indexes structure, not
  arbitrary text, and `ag` sees the live filesystem (immune to graph drift and
  IDE-index lag).
- **Symbol / relationship / architecture-anchored**: prefer a semantic tool over grep,
  choosing by need --
  - **code-review-graph** for token-cheap breadth: exploration, `get_impact_radius`,
    `detect_changes` / review context, `get_architecture_overview` / communities. Its
    wins are token cost and structural reach.
  - **JetBrains MCP** (`search_symbol`, `analyze_calls`, `get_symbol_info`) for
    live-accurate precision on a specific symbol: aliases, overloads, just-edited code,
    or whenever the graph's enrichment may be **stale** (see the drift note below).
  - Tiebreak: graph first to map the territory cheaply; JetBrains MCP to confirm or
    disambiguate an exact symbol, or when the graph looks stale.
- **Grep/Glob**: genuinely last resort -- only when none of the above fits. (Noted
  because the default reflex is to reach for grep first; resist it.)

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
