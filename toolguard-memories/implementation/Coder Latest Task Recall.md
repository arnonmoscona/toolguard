---
title: Coder Latest Task Recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

## Ticket

TOO-45 punch-list #01, second review pass. Repo `/home/arnon/projects/toolguard`, branch
`too-45`. Tree was 2648 tests green at start. Previous `once_per_day` redesign reviewed for
conceptual alignment, came back `partially` -- direction right, mechanics redistributed
rather than removed. This pass finishes it. 10 numbered items in the review.

## The 10 items (verbatim intent)

1. **Real defect**: `once_per_store.claim`'s `project=None` branch returned `True`
   (proceed) identically to a genuine successful claim, so `run(..., on_unavailable=SKIP)`
   silently ran the guarded action on every call when no project root resolved --
   defeating the fail-closed contract. Root cause: `available()` answered a *global
   technology* question when the facade needed a *per-call guarantee* question. Fix:
   `claim()` reports a per-call outcome (`CLAIMED` / `HELD_BY_SOMEONE_ELSE` /
   `UNGUARANTEED(reason)`); delete `available()` from the facade's decision path; the
   facade stops naming a specific storage technology in its degraded notice, using the
   store's own reason text instead. Add a regression test for the `project=None` +
   fail-closed path specifically.
2. **`sweep()` de-duplication**: three call sites each remembered to call housekeeping
   under different conditions. Fix: `OncePer` triggers housekeeping internally after a
   successful claim, throttled under its own shared key. The word `sweep` disappears from
   client code entirely.
3. **`logs_dir` threading**: remove it from `check_and_warn_divergence` and
   `run_auto_migration` signatures; resolve wherever the sweep needs it internally
   (transitional convention: `project / "logs"`), marked as expiring in a release or two.
4. **One named object per throttled thing**: `DIVERGENCE_WARNING = once_per.day("divergence_warning",
   "the configuration divergence warning")`, then `.done()`/`.warn()`/`.run()` on it --
   replacing a bare `_KEY` constant plus a duplicated description string at each call site.
5. **Module shape**: move the facade out of `session_warnings.py` into a new
   `toolguard/once_per.py`, exposing `day` (and later `session`). `session_warnings.py`
   keeps only `issue_takeover_warning` (explicitly not throttled). Diverges from Arnon's
   literal illustrative suggestion (`once_per_day` living in `session_warnings`) --
   flagged as a reversible rename in the report.
6. **Finish the "suppression" rename**: docstrings, the on-disk filename
   (`suppression.db` -> `once_per.db`), `self_integrity.py`, `docs/uninstall.md`, and the
   `import ... as suppression` aliases in test files. No migration needed (disposable
   state); add the old filename to what `reap()` sweeps.
7. **`OnUnavailable.PROCEED`/`SKIP` renamed** to reflect the CALLER's domain knowledge
   (repeat-safety), not the mechanism's action: `SAFE_TO_REPEAT` / `UNSAFE_TO_REPEAT`.
8. **`_degraded_notices_sent`** module global -> instance attribute on `OncePer`
   (avoids cross-period collisions on a shared key).
9. **`scope: Callable[[], str]`** bakes in wall-clock-only periods. Give the scope
   function a `context` parameter now (unused today, `None` always) so a future
   session-scoped period can thread the real session id through without a later
   signature break. Explicitly: do NOT implement `once_per_session`.
10. **Test-side duplication**: four byte-identical `_IsolatedStoreMixin` copies (three
    with a function-local import) -> one shared helper module, no function-local
    imports, no private reach-in where item 8 makes it unnecessary.

## Keep -- do not redo

All correctness fixes from the previous six passes stand with their regression tests:
atomic claim + two-process race test, lazy home resolution, nothing raising into a
caller, reads creating nothing, `PRAGMA user_version` + stand-down on a higher version,
`Path.as_uri()`, the real-store isolation guard, fail-closed migrate policy.

## Constraints

Stdlib only. unittest, BDD Given/When/Then docstrings. No git write ops (rm/mv only).
Doc comments short, no ticket narrative in code. Do NOT touch
`tools/architecture_fitness.py`, the architecture test files, `hook.py`'s stderr
handlers, or `toolguard-memories/`.

## Verify commands required

```
uv run python -m unittest discover -s test -t .
uv run python tools/architecture_fitness.py --layers
uv run ruff format . && uv run ruff check .
uv run pyright toolguard/
```

Golden corpus runs in the suite; STOP if it reports differences. Re-run the probe at
`/tmp/claude-1000/.../scratchpad/probe_claim_leak.py`, updating only imports/names, never
assertions/scenario. Confirm a full suite run creates no store under `~/.toolguard/`.

## Note on process

Investigation before writing this recall took a long time (deep design work was needed
before any code could be written safely, given the scope), so this note was written
retroactively partway through implementation rather than strictly first -- flagging
honestly per protocol. No requirements were lost; the ticket was read in full before any
edits, and this note captures it faithfully.
