---
title: latest-code-review-report
type: report
tags:
- code-review
- TOO-45
permalink: latest-code-review-report
---

# Code review — 2026-08-09

**Scope:** `toolguard/hook.py`, `test/unit/test_hook.py`, `test/unit/test_hook_error_reporter.py` (TOO-45 punch-list #04). Reviewed against `HEAD`; `toolguard/error_reporter.py` and `.pyscn.toml` were read as context because the change's correctness depends on them.

**Verification run:** `uv run python -m unittest test.unit.test_hook test.unit.test_hook_error_reporter test.unit.test_error_reporter` — 109 tests, all pass. `ruff check` and `ruff format --check` clean on all four files.

## Summary

This is a good, well-motivated change: it closes a genuine fail-open (the three `except` handlers in `main()` printed their deny JSON to **stderr** and exited 0, which Claude Code reads as "no opinion" and falls through to native permission handling), funnels every decision through one emission point, and the tests assert the stdout/stderr split rather than the message text. Two things stop it from being complete. The exit-2 belt-and-braces path in `_emit_decision` does not work on a real pipe — measured, not inferred — and `_run_eval_mode`, twenty lines above in the same file, still contains three verbatim copies of the exact defect that was just removed from `main()`. There is also a latent structural loss in the nested-invocation design that will silently drop faults as soon as a second `report_fault` call site exists.

---

## Critical

None. No security vulnerability, injection path, or credential handling issue was introduced. The change moves the fail-safe posture in the right direction.

---

## Major

### M1. `_emit_decision` never flushes, so the documented exit-2 guarantee does not hold on a real pipe

**`/home/arnon/projects/toolguard/toolguard/hook.py:249-253`**

```python
try:
    print(json.dumps(output))
except Exception as e:
    print(f"toolguard: failed to emit decision: {e}", file=sys.stderr)
    sys.exit(2)
```

When Claude Code runs the hook, stdout is a **pipe**, so `sys.stdout` is block-buffered. `print()` copies into the buffer and returns; the actual `write(2)` happens at flush or at interpreter shutdown — *after* `_emit_decision` has returned and the `try/except` is long gone.

Measured on this machine with a closing reader (scratchpad probe, real pipe):

```
PRINT_RETURNED_WITHOUT_RAISING
FLUSH_RAISED: BrokenPipeError: [Errno 32] Broken pipe
Exception ignored while flushing sys.stdout: BrokenPipeError
exit=120
```

So the real behaviour on a stdout write failure is **exit 120 with no JSON on stdout** — and Claude Code treats any exit code other than 0 and 2 as a *non-blocking* error, i.e. the tool call proceeds. That is the same fail-open class this item exists to close, just relocated to the last-resort path.

The module docstring and `main()`'s docstring both assert the stronger guarantee ("Exit 2 fires only if writing that JSON to stdout itself fails"), so the documentation is currently wrong as well.

The unit test passes because `_BrokenStdout.write` raises — which is what a `StringIO`-shaped double does and precisely what a buffered pipe does not.

**Fix:** flush inside the `try`, and cover the buffered case.

```python
try:
    print(json.dumps(output))
    sys.stdout.flush()
except Exception as e:
    ...
```

Add a test double that raises on `flush()` (not `write()`), asserting exit 2. Keep the existing `write`-raising test; both shapes are worth pinning.

### M2. `_run_eval_mode` still emits its deny JSON on stderr — the same fail-open, in the same file

**`/home/arnon/projects/toolguard/toolguard/hook.py:765-783`**

All three `except` clauses do `print(json.dumps(output), file=sys.stderr)` while the success path at line 764 prints to stdout. Consumers parse stdout, so on any internal error they get an **empty stdout and exit 0** — indistinguishable from "produced nothing", not "denied".

This matters more than an ordinary preview-tool bug: `.claude/skills/toolguard-security-audit/SKILL.md` uses `toolguard --eval` as its ASK-floor probe across projects. A configuration that makes the probe crash yields no verdict rather than a deny, in the tool whose job is to detect exactly that class of hole.

The docstring now also states a falsehood: *"Errors are reported as a `deny` decision on stderr, matching the live hook's fail-safe contract"* — after this change the live hook's contract is stdout.

**Fix:** route these through `_emit_decision` too (the fault buffer is not wanted here, so `create_hook_output` + `_emit_decision`, not `_finalize_output`), and update the docstring. If `--eval` deliberately wants a distinguishable failure exit code, say so explicitly rather than relying on stream choice.

### M3. Nested invocations discard the inner buffer — accumulated faults are lost across the boundary

**`/home/arnon/projects/toolguard/toolguard/hook.py:1266-1271`** (the nesting) and `toolguard/error_reporter.py:137-147` (the drain).

`drain_claude_context()` reads only `_current`, and `invocation()`'s `finally` restores `_current = previous`, throwing the inner `_InvocationState` and its `claude_messages` away. Two losses follow directly from the nesting this change introduces:

* A fault reported **inside** the inner invocation (config loading, startup validation, resolution) followed by an exception is lost: the exception unwinds past the inner `with`, and the handler's `_finalize_output` drains the **outer** buffer, which never received it.
* A fault reported in the **outer** scope before the inner opens (i.e. during `get_env_config()`) is lost on the **success** path, because the drain there happens inside the inner invocation.

Latent today only because the sole `report_fault` call site is `_report_crash_fault`, which runs in the outer scope. It will start losing data the first time anything between `get_env_config()` and the decision reports a fault — which is the stated purpose of the module. This is the "do not flatten or discard as you go" failure mode from the global conventions, and neither existing test covers the crossing.

**Fix (in `error_reporter.invocation`):** on exit, splice any undrained `claude_messages` into the parent state before restoring, so nesting composes:

```python
finally:
    if previous is not None and _current is not None:
        previous.claude_messages.extend(_current.claude_messages)
    _current = previous
```

Add a test: report a fault inside the inner invocation, raise, assert it appears in the crash response's `additionalContext` alongside the handler's own fault.

---

## Minor

### m1. Six near-identical `except` blocks

`main()`'s three handlers (hook.py:1293-1348) differ only in the reason string, the `caught_as` label, and the `JSONDecodeError` case's extra `raw_stdin`. `_run_eval_mode`'s three are the same again. Collapse to one helper:

```python
def _deny_after_crash(exc, reason, caught_as, extra_context=None) -> None:
    context = _build_crash_context(...)  # caller supplies locals()
    if extra_context:
        context.update(extra_context)
    log_crash(exc, context, caught_as=caught_as)
    _report_crash_fault(reason)
    _emit_decision(_finalize_output(RuntimeVerdict(decision="deny", reason=reason)))
```

Note `_build_crash_context(locals())` has to be evaluated at the catch site, so pass the dict in.

### m2. `main()` is now ~190 lines at five levels of nesting

`with` → `try` → `with` → `if` → call args. The whole decision body moved two indent levels right, which is most of the diff's churn and makes the next diff on this function harder to read. Extract the inner block as `_decide_and_emit(env_config) -> None`, leaving `main()` as: parse args → guards → outer invocation → try/except. That also makes m1's helper natural.

### m3. `invocation(config=...)` takes an *env* config, and the call site reads as if it takes the `Configuration`

`hook.py:1271` reads `error_reporter_invocation(config=env_config)` while a `Configuration` object named `config` is in scope a few lines below. Rename the parameter to `env_config` in `error_reporter.invocation`; the docstring already has to spell out that it means "a `get_env_config()` dict".

### m4. Stale module docstring in `error_reporter.py`

Lines 10-12 still say *"`report_fault` has no production call site yet ... the Claude-facing buffer is exercised only by tests"*. `hook._report_crash_fault` is now that call site.

### m5. `_warn_if_settings_path_override` now writes to the warning log on every tool call

Previously stderr-only; via `report_warning` it now also hits `error_log.log_warning` on every invocation where `CLAUDE_SETTINGS_PATH` is set — a persistently-exported variable, so that is one log line per tool call indefinitely. `once_per` exists in this branch; consider whether this belongs on it, or confirm the per-call repetition is deliberate (it is a live-reminder warning, so it may be).

### m6. The outer invocation resolves a log directory on the hot path, possibly a different one

`invocation(config=None)` calls `resolve_log_dir(None, None)` → `_log_dir_from_environment()` → `require_project_root()`, on every invocation, before `env_config` exists. Two consequences: a small filesystem walk added to the hot path before any decision work, and the outer and inner invocations can resolve **different** directories, splitting one invocation's log entries across two. Harmless with today's defaults, worth a sentence in the docstring so it is a decision rather than an accident.

### m7. `_emit_decision`'s stderr fallback is itself unguarded

If stdout is broken, stderr often is too (same terminal/pipe teardown). `print(..., file=sys.stderr)` raising there propagates out of `_emit_decision`, out of the handler, and the process exits 1 — non-blocking, i.e. fail-open again. Wrap the fallback in a bare `try/except Exception: pass` before `sys.exit(2)`; the exit code is the part that matters.

### m8. `_run_main` swallows `SystemExit` without checking the code

**`test/unit/test_hook_error_reporter.py:67-70`** — every test in the module would still pass if `main()` started exiting 2. Capture the exception and assert `code == 0`. `test_hook.py`'s equivalents already do this.

### m9. `_run_main`'s `patches` list only ever holds zero or one element

**`test/unit/test_hook_error_reporter.py:56-73`** — a list, a loop to start, a `try/finally` loop to stop, for one optional patch. `with contextlib.ExitStack()` or a plain conditional `with` reads better and is harder to get wrong.

### m10. Missing test for the M3 crossing

The module tests "fault in inner, success" and "fault in outer, crash" but not "fault in inner, crash" — the one that currently loses data.

---

## Suggestions

### s1. Fault text now flows into `additionalContext`, which the model reads

`_report_crash_fault` embeds `str(e)` into text delivered to Claude. Today's exception messages are toolguard-authored and safe (`JSONDecodeError` does not echo the document; the `ValueError` names come from a fixed list). But the general `except Exception` will happily forward whatever a deeper component put in its message, and tool input is the most likely source. For a permission hook, that is a small new prompt-injection surface. Consider truncating fault text and prefixing it with a fixed, unmistakable frame (e.g. `[toolguard internal fault] ...`) so injected prose cannot pass as instruction.

### s2. `_CRASH_CORRECTIVE_STEPS` hard-codes a path that `log_crash` also hard-codes

Both name `~/.toolguard/errors/`. If that ever moves, one of them will be missed. `error_log` should expose the directory (or a `crash_reports_hint()`), and hook.py should use it.

---

## Architectural drift pass

Run because a ticket ID was supplied. These are observations about the trend, not defects in this change.

**Blast radius vs. conceptual size — healthy.** One concept ("all reports go through one module") landed in six production files plus one new module. That looks wide, but it is a *consolidation*: `.pyscn.toml`'s own comment records the config layer dropping from 16 hand-rolled stderr writes to zero, and I verified that — `grep "file=sys.stderr"` across `config.py`, `env_config.py`, `auto_migrate.py`, `config_divergence.py` now returns nothing. The remaining four in `hook.py` are M2's three plus the one legitimate `_emit_decision` fallback.

**New file has a declared architectural home — good, and worth saying.** `error_reporter` was added to the `observability` layer in `.pyscn.toml` with the rationale updated in the same edit. This is the drift check that most often silently fails (an unlisted module stops being validated and the compliance score stays plausible), and it was done correctly here.

**`hook.py` is the repository's co-change hub, and this change deepens it.** Over the last 200 commits touching `toolguard/`: `hook.py`↔`config.py` co-changed 16 times, and `hook.py` has 8+ distinct co-change partners — more than any other module. It is now 1394 lines, with `main()` at ~190 of them, and this change gives it two further responsibilities: error-reporter invocation lifecycle and decision-emission policy. Each individual addition is reasonable, which is exactly why this accumulates. Worth considering a small `decision_emit` module owning `create_hook_output` / `_finalize_output` / `_emit_decision` and the invocation nesting, leaving `hook.py` to orchestrate. Not urgent; noted so the trend is visible.

**Test cost trend — in line.** ~391 added test lines against ~195 net added production lines (~2:1). The tests assert behaviour (which stream carried the decision, what reached `additionalContext`) rather than pinning message text, so this is not representation-pinning.

**Boundary crossings — none.** The change stays inside `toolguard/` and `test/unit/`.

---

## Tooling notes

* `pyscn` was **not** run: the requested scope is one production file, well below the "substantial part of the codebase" bar, and the skill says to ask first. Worth running before push given `.pyscn.toml` itself changed.
* `code-review-graph` (`find_large_functions`) returned **stale line numbers** — `main` at 1142-1295 when it is actually at 1205-~1394, i.e. the index predates this uncommitted change. Function names and relative sizes were still usable, and it did surface that `main` is the largest function in the file, which a linear read would have taken longer to establish. Verdict: mildly useful, but `wc -l` plus a `grep` for `^def` gave the same answer with current data. LSP would not have answered "what is the biggest function here" in one call, so this is inside the graph's remaining exclusive ground — just at the low-value end of it. No refresh was run before this call (row-one tool, no refresh required per the reference; staleness here is the incremental-update hook not having seen the working-tree edits).