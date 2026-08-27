---
title: The --ambient check is module-granular for resolve(), because AST cannot prove
  a receiver absolute
tags:
- TOO-45
- proposed-ticket
- testing
permalink: toolguard/too-45/proposed-tickets/81-ast-cannot-prove-a-receiver-relative
---

# A new relative `resolve()` inside an already-owned module is invisible

**Found 2026-08-19 while building ticket 80's `--ambient` check, by the agent that built it. Re-measured 2026-08-19 against the finished check; two claims in the first draft were wrong and are corrected below.**

`Path("rel").resolve()` reads `os.getcwd()`; `Path("/abs").resolve()` does not — measured, one call versus zero. **Static analysis cannot tell which it is**, because the receiver's absoluteness is a runtime property.

## The mechanism, measured

Ownership is keyed **per module**, not per site: `PATH_AMBIENT_OWNERS` maps `(module, member) -> reason`. A single entry `("config", "resolve")` accounts for all six `resolve()` sites in `config.py`, and for any number added to it later. It is not an allowlist enumerating the sites.

The tree today: **22 `Path.resolve` reads across 10 modules, every one owned; zero `Path.absolute` reads anywhere.** (A textual `grep` finds 23 — the extra is `ambient.resolve()` in `hook.py`, toolguard's own facade function, correctly passed over as a module-alias read.) The 10 owner modules are `config`, `install_provenance`, `install_update`, `normalization`, `path_utils`, `permission_migration`, `session_start`, `testing.sandbox`, `tools.installer`, `tools.transcript_harvest`.

## Two gaps, not one

**Gap A — a `resolve()` in a module with no owner entry is reported but does not fail.** `resolve` is absent from `PATH_AMBIENT_FATAL_MEMBERS`, so such a site becomes an inventory line while `report.ok` stays `True` and `--ambient` exits 0. It is advisory, not enforced.

**Gap B — a new relative `resolve()` inside a module that already has an owner entry is not reported at all.** The `(module, member)` key already matches, so the site is skipped before any fatality question is asked. Nothing changes in the output.

The first draft of this ticket said "the check is closed against new *modules* and open against new *sites within them*." **That was wrong about the first half**: the check is *advisory* against new modules, not closed. It also said the checker "cannot make `resolve()` fatal without roughly nineteen false positives" — **also wrong now**, and it is what ticket 80 changed: every site acquired an owner, so promoting `resolve` to fatal today produces zero findings.

## What closes each

**Gap A is closable by adding `resolve` to `PATH_AMBIENT_FATAL_MEMBERS`** — a one-constant change, zero findings today, verified by simulation. **But read what it actually buys before spending it.** It closes the 68 scanned modules that have no resolve owner, and leaves the 10 that do wide open. Those 10 are precisely the path-handling modules — the ones where a new relative `resolve()` is realistically going to be written. The promotion is therefore a genuine tightening of the low-risk majority and no help at all on the high-risk minority, and it does not reduce this ticket.

**Gap B needs a runtime sentinel**: wrap `Path.resolve` and `Path.absolute` for the duration of the test suite and record any call whose receiver is relative. Runtime sees exactly what AST cannot — the receiver. This also catches the case no static rule of any granularity can reach: **an existing owned site whose receiver changes from absolute to relative**, where the file, the line and the module all stay the same.

**This project already has that shape and it already works.** `test/unit/_real_log_dir_guard.py` wraps toolguard's log-writing entry points, records any call resolving to the real repo `logs/` directory, and a companion test asserts the record is empty; `test/unit/__init__.py` also registers an `atexit` hook so the check does not depend on discovery order. That guard exists because a checklist alone failed three times to stop the same leak — the same argument applies here.

Deferred from ticket 80 only because installing it requires editing `test/unit/__init__.py`, which was outside that ticket's licence.

## Why this is worth doing rather than accepting

The route history on this one mechanism: `expanduser` escaped four blinded review rounds and was a **live isolation hole** returning the developer's real home under a patched `Path.home`; `resolve` escaped five; `absolute` escaped six and was found only by enumerating pathlib's surface rather than by review. Every one was invisible to the instrument used to clear the round before it.

**A sentinel is the first instrument in that sequence that observes the property directly rather than a proxy for it.** It is also the one that needs no enumeration, so it does not inherit the open-list weakness that let the first three through.

## One more thing the measurement turned up

**Nothing in the unit suite asserts that the real tree is ambient-clean.** The only test that runs the check over the real tree is `test_main_ambient_flag_smoke`, and it asserts `code in (0, 1)` — deliberately, as a smoke test. So `--ambient`'s verdict, fatal or not, has teeth only where someone runs the tool: the pre-push checklist. That is worth knowing before treating a fatality promotion as an enforcement change, and it applies to the `os`-import half of the checker too, which is otherwise the strong half.

---

## A cheaper partial fix for Gap A, measured 2026-08-19 and deferred

`TestAmbientRoutesOnTheRealTree` currently asserts `fatal_findings == []`. Asserting **`report.findings == []`** instead would close Gap A — a new *unowned* `resolve` site would fail the suite — and it **passes on the real tree today**, so the change is free of migration work.

The reason it was not taken on the spot: **it makes the suite stricter than the tool.** `--ambient` would exit 0 on a new unowned `resolve` (inventory findings are non-fatal) while the suite went red. Two verdicts disagreeing about the same tree is how both come to be distrusted, and the campaign has already spent a week on instruments whose verdict did not mean what it said.

**Two ways to take it, and the choice is the ticket's, not a wording call:**

- **Suite as the gate, tool as the report.** Keep `--ambient` advisory on `resolve` and let the suite be strict — defensible, since a report may inform while a gate must bite. **Then the failure message must say so explicitly**: that `--ambient` exits 0 for this case by design and the suite is stricter on purpose. Without that sentence, whoever trips it runs the tool, sees a pass, and concludes the suite is broken.
- **Make them agree** by promoting `resolve` to fatal. Measured separately: that closes the 68 low-risk modules and leaves the 10 path-handling ones open, because per-module ownership skips an owned site before fatality is asked — so it is a smaller win than it sounds and does not remove the need for the choice above.

Gap B — a new or mutated site *inside* an owner module — survives either way, and remains the runtime sentinel's job.
