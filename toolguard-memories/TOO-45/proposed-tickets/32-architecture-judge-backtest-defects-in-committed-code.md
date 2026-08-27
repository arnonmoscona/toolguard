---
title: Eight defects in committed, already-reviewed punch-list code (architecture-judge
  back-test)
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/32-architecture-judge-backtest-defects-in-committed-code
---

**PARTIALLY FIXED in `05f786d`.** 2 of 8 items are closed — item 8 (`COMMAND_TOOLS`, already gone before the ticket was filed) and item 7 partially; still open: 6 of 8, including both items marked "fix before push" (see the audit's #32 detail table).

# Eight defects in committed, already-reviewed punch-list code

**Two are marked "fix before push" and have been sitting in a working queue since 2026-08-10.** Found by the architecture-judge back-test, not by the #07 sweep; evidence and verification in `reports/architecture-judge-backtest.md`. Disposition below is a recommendation -- the call is Arnon's.

What makes this set different from the #07 tickets: **every item is in code that was already written, reviewed and committed** as part of this ticket's own punch-list. The back-test was run to see what a judge would find in work believed finished.

| # | defect | where | recommendation |
|---|---|---|---|
| 1 | `migrate()` collapses four `LockUnavailable` reasons into one `DECLINED_LOCKED`; `auto_migrate` then announces *"another migration is already running"* for all four **and consumes the day's claim**, silently disabling auto-migration until tomorrow. The comment defending the consumed claim is true only of the timeout branch. | `permission_migration.py:1250`, `auto_migrate.py:174` | **fix before push.** A user-visible false statement plus a silent disable. Add `DECLINED_UNAVAILABLE`, or carry the reason on the outcome. |
| 2 | `_dispatch` does `getattr(error_log, rule.log_fn_name)`, so `log_warning`/`log_error` have **zero static callers** from the reporter — invisible to pyright's `incomingCalls` and to `callers_of`. Test-patching mechanics driving a production indirection. | `error_reporter.py` `_ROUTING` / `_dispatch` | **fix before push.** Directly contradicts the standing principle that what static analysis cannot see, a reader cannot either. Bind the callable and patch the reporter in tests instead. |
| 3 | `hook.py` constructs the Reporter and still keeps four hand-rolled `log_error`/`log_warning` calls; `hook.py:96-100` is a **second copy** of the severity routing table. | `hook.py:98,100,431,944` | small and mechanical. |
| 4 | `OncePer.run` executes a config-layer closure handed to it by `auto_migrate`, so an observability module runs config code at runtime **with no import edge**. `--layers` reports clean. Same class as the cycle #03 removed. | `once_per.py`, `auto_migrate.py` | **decide.** Benign in form (the callee is opaque to the facade) but it weakens what a clean `--layers` means. Argue it or remove it — the standard applied to #03. |
| 5 | `is_builtin` means both *"toolguard ships knowledge of this"* and *"govern by default"*; `test_tool_spec.py:82` pins `DEFAULT_GOVERNED_TOOLS == BUILTIN_TOOLS`, so **the first understood-but-not-governed tool fails a test**. | `tool_spec.py` | **fold into TOO-51.** It is the mechanism that makes TOO-51 harder the longer it waits. |
| 6 | `TOOLS_BY_NAME` is a live mutable public dict while `BUILTIN_TOOLS`/`FILE_KIND_TOOLS`/`KNOWN_TOOL_NAMES` are import-time snapshots. Tests patch the dict, **exercising a state production cannot reach.** | `tool_spec.py`, `test_hook.py`, `test_hook_eval.py`, `test_verdict_corpus.py` | fix with 5. Read-only mapping plus one accessor. |
| 7 | The golden verdict corpus **cannot see payload-key changes**: the in-process corpus replays with the target already extracted, and the e2e path goes through a **sixth** hardcoded copy of the tool→key map. | `fixture_loader.py:679` | verification-infrastructure item. Pairs with the determinism gap below. |
| 8 | `hook.COMMAND_TOOLS` has **zero readers anywhere** and is a mutable `set` among frozensets. | `hook.py:58` | **delete.** Trivial. |

## The near-miss worth remembering

The #10 spec instructed pointing `tools/architecture_fitness.py`'s canary at the new registry **and deleting the comment explaining why it was deliberately independent.** Probe and probed would then share a source, making a wrong payload key invisible.

**It was never carried out — the coder silently declined, and nothing in review caught it.** So the safeguard held by luck rather than by process. That is the same failure mode as everything in this ticket: work that looked finished.

## Two verification-infrastructure gaps recorded alongside

Both concern how we check, not what ships:

1. **A verdict is not purely a function of config and input.** Matching reads live disk state (`normalization.py:47-50, 81` — `exists()`, `is_symlink()`, `resolve()`, reached from `permissions.py:146` and `:194`). **The golden corpus implicitly assumes determinism and nobody has checked that assumption.** Cheap to test.
2. **`resolve.py:2` claims "Pure, side-effect-free permission resolver layer"** while the above is true. The narrower line-7 claim (*"no logging, no stdin/stdout, no `sys.exit`"*) remains accurate.

With item 7 above, **the corpus's known blind spots now number four.**

## Explicitly deprioritised — do not reopen

**The check-to-use race in path matching.** Arnon's call, 2026-08-06: do not complicate the design for it. Sub-second hook execution on a single-user machine makes a file changing under the check unlikely, and the strictest result is taken across several layers, so something *could* slip but has more than one chance to be caught. **Noted and deprioritised, not open. Do not rat-hole on it.**

## Provenance

`reports/architecture-judge-backtest.md` and `reports/follow-up-queue.md` lines 60-86. Promoted to a ticket 2026-08-12 when Arnon asked what else had been left in the working queue — this had been there since 08-10, including the two "fix before push" items.
