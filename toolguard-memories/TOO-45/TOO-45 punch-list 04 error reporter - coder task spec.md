---
title: TOO-45 punch-list 04 error reporter - coder task spec
type: note
permalink: toolguard/too-45/too-45-punch-list-04-error-reporter-coder-task-spec
tags:
- task-memory
- TOO-45
---

# TOO-45 punch-list #04 — a toolguard error reporter, and the config-layer stderr writes moved onto it

Ticket: `toolguard-memories/TOO-45/proposed-tickets/04-error-reporter-and-config-layer-stderr.md`. Read it first — it carries Arnon's requirement verbatim, and the requirement is the design.

## Correction to the ticket's evidence, measured 2026-08-09

The ticket says **16** hand-rolled stderr writes across four config-layer modules. **There are 8.** Punch-list #01 removed the rest as a side effect when it rewrote `auto_migrate` and `config_divergence` onto the once-per-day facade. Counted by AST (`print(..., file=sys.stderr)` and `sys.stderr.write(...)` call nodes, not grep over text):

| module | writes today | ticket claimed |
|---|---|---|
| `toolguard/config.py` | 1 (line 2290) | 3 |
| `toolguard/env_config.py` | 2 (83, 130) | 2 |
| `toolguard/auto_migrate.py` | 4 (152, 163, 166, 168) | 6 |
| `toolguard/config_divergence.py` | 1 (line 55) | 5 |
| **total** | **8** | 16 |

For context, the whole package has 40, the largest concentrations being `hook.py` 9, `install_update.py` 6, `error_log.py` 5, `log_writer.py` 4. **Only the four config-layer modules are in scope.** The others are named so you know the boundary is deliberate, not an oversight.

## What to build

### 1. `toolguard/error_reporter.py` — new module, `observability` layer

Declare it in `.pyscn.toml`'s `observability` packages list alongside `log_writer`, `error_log`, `session_warnings`, `once_per`. The layer completeness check fails if you forget, which is the intended safety net.

**The caller's entire contract is severity and what happened.** Three named functions, because the function name *is* the severity and that reads as intent:

- `report_notice(message)` — routine, expected under normal operation. The takeover-mode notice is the archetype.
- `report_warning(message, corrective_steps)` — something is wrong; toolguard still works.
- `report_fault(message, corrective_steps)` — toolguard itself is broken.

A caller passes **nothing else**. No stream, no log directory, no audience, no "should this repeat". If a call site currently computes any of those, that computation moves into the reporter or disappears.

### 2. The routing table, owned by the reporter and stated in one place

One module-level mapping from severity to destinations. It must be a single readable table, not `if` branches scattered through the module — the whole point of the encapsulation is that Arnon can change policy by reading and editing one thing.

Today's policy, chosen to keep this item a refactor and not a behaviour change:

| severity | stderr | warning log | error log | reaches Claude |
|---|---|---|---|---|
| notice | yes | no | no | no |
| warning | yes | yes | no | no |
| fault | yes | no | yes | yes |

**`notice` keeping stderr is deliberate and temporary.** Arnon's requirement says nothing should be on stderr under normal conditions, and the takeover notice violates that on every tool call. Changing where the user sees it is a user-visible behaviour change he has explicitly reserved. So the current behaviour is preserved and the table is the one line he edits when he decides. Say that in the table's doc comment, briefly.

### 3. The reporter resolves its own destinations

`error_log.log_warning` / `log_error` take a `log_dir` argument. Callers must not supply one. The reporter resolves the log directory itself — `log_writer` is in the same layer, so its resolution logic is importable; reuse it rather than duplicating the rules. If the log directory cannot be resolved, the reporter still writes stderr and does not raise.

**Nothing the reporter does may raise into a caller.** A config-layer module reporting a problem must never be given a second problem. Wrap the log-writing side in a guard that degrades to stderr.

### 4. Reaching Claude, invocation-scoped

`verdict.additional_context` already becomes `additionalContext` inside `hookSpecificOutput` (see `hook.py` ~178-200). That is the existing channel and the reporter should use it: a `fault` accumulates into a buffer that `hook.py` drains and appends to the outgoing decision's additional context.

**The buffer must be invocation-scoped, not a module global.** toolguard is one process per tool call, so a module global is safe in production and leaks in the in-process replay harness and across tests — this has bitten this project before. Install the reporter's per-invocation state through a context manager used at the process entry points, with a safe default when none is installed (stderr only, no logs, no buffer). The context manager also gives tests and the replay harness a clean reset for free.

**Stop and report if this pulls in more than the hook's output assembly.** Wiring the drain should be roughly one place in `hook.py`. If it turns out to require threading a reporter through the resolution path or changing the verdict type, do not do it — leave `drain()` implemented and tested but unwired, and say so in your report. That is a scope boundary, not a failure.

### 5. Move the 8 call sites

Replace each with the matching `report_*` call. Judge severity per site from what the message actually is — a failed config load that toolguard recovers from is a warning; a failure that means toolguard cannot do its job is a fault. `auto_migrate`'s four are progress/outcome messages about a migration, which is closer to notice/warning than fault; use your judgement and state your reasoning per site in the report.

## Explicitly NOT in scope

- **`hook.py`'s three error handlers that print the deny JSON to stderr and exit 0.** That is a real fail-open and it gets its own item and its own tests. Do not fix it here, and do not route it through the reporter here.
- The other 32 stderr writes in the package.
- Changing where the takeover notice appears.
- **`Issue.level` is a bare `str` carrying `'warning'` / `'error'`** (`toolguard/issues.py`). That is the standing "literal strings with semantic meaning belong in constants" rule, and the reporter's severity type is its natural home — but converting it reaches `config.py`, `config_validation.py` and `rule_entry.py`. **Leave it. Note it in your report as a follow-up** so it gets a ticket instead of silently riding along.

## Constraints

- **Stdlib only** at runtime. No new dependencies.
- Tests are `unittest` under `test/`, run with `uv run python -m unittest discover -s test -t .`. Not pytest.
- `uv run ruff format .` and `uv run ruff check .` before you report.
- Doc comments say what a thing is, what it takes, what it returns, and any non-obvious constraint — **1-5 lines**. No ticket narrative in code; a bare `TOO-45` pointer is fine, the story is not.
- Any string the code **branches on** is a constant, named at module scope.
- No new module-level mutable state without the invocation-scoped treatment described above.

## Verification — assert the destination, never merely that something happened

This is the part most likely to be done wrong, because the weak version passes while the routing is broken.

- **Per severity, assert where it landed** — stderr captured *and* the log file's content checked *and* the Claude buffer inspected. "A warning was produced" is exactly the assertion that stays green through wrong routing.
- A test that an ordinary invocation puts nothing on stderr **except** what the table classifies as a notice — so the premise the ticket disputes becomes machine-checked rather than prose.
- A test that a failure inside the reporter's own log-writing path still produces stderr output and does not raise.
- A test that the invocation-scoped buffer does not leak between two successive invocations in one process.
- The golden verdict corpus is **structurally blind here** — it compares verdict objects, so it guards what a decision *is* and never where anything *goes*. A green corpus is not evidence about this item. Keep it green, but do not cite it as verification.
- The existing suite must stay green: 2646 tests, plus `uv run python tools/architecture_fitness.py --layers`.

## Report

Write your implementation report to basic-memory as usual. Include:

1. Per call site, the severity you chose and why.
2. Whether the Claude wiring landed or hit the scope boundary in §4.
3. Anything you found that the spec got wrong — the ticket was already wrong by a factor of two about its own central evidence, so treat the spec as fallible and say so when it is.
4. A duplication self-check: before reporting, inventory what already exists in `error_log`, `log_writer`, `session_warnings` and `once_per`, and confirm the reporter is not a fourth copy of something. If it overlaps one of them, say where.
