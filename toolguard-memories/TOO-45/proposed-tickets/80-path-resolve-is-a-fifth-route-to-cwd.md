---
title: Path.resolve() on a relative path is a fifth route to cwd, invisible to a Path.cwd
  patch
tags:
- TOO-45
- proposed-ticket
- testing
permalink: toolguard/too-45/proposed-tickets/80-path-resolve-is-a-fifth-route-to-cwd
---

# `Path("x").resolve()` reads `os.getcwd()` and no isolation guard sees it

**MUST FIX (Arnon, 2026-08-19).** Scheduled immediately after ticket 44, whose `expanduser` fix is the working precedent.

**Found 2026-08-19 while closing ticket 44's `expanduser` gap. Measured both directions; 17 sites.**

`Path.resolve()` on a **relative** path consults `os.getcwd()` internally. A test that patches `Path.cwd` does not affect it, so a module that resolves a relative path reaches the real process working directory while appearing isolated.

This is the same shape as the `expanduser` hole ticket 44 closed, one fact over: **a derived stdlib call that reads an ambient fact by a route the obvious patch target does not cover.** There are now two confirmed instances of that shape and no reason to assume they are the last two.

| fact | obvious patch target | the route that escapes it |
|---|---|---|
| home | `Path.home` | `Path(...).expanduser()` — reads `$HOME`, then the passwd entry. **Closed by ticket 44.** |
| cwd | `Path.cwd` | `Path("rel").resolve()` — reads `os.getcwd()`. **Open.** |

## Why the `expanduser` instance is the argument for taking this one

That one was not merely an inaccurate comment. `ConfigIsolationMixin` clears `os.environ` without a `HOME` key, so a `~` path fell past the cleared environment to the **passwd entry** and returned the developer's real home under a patched `Path.home`. Tests believed they were isolated and were not. It survived four review rounds because the instrument used to prove "zero bypasses" watched `Path.home`, `Path.cwd` and `os.getcwd` — and `expanduser` uses none of them.

The cwd instance has the same property: **an instrument that watches `Path.cwd` cannot see it.**

## Scope

17 call sites. Whether they all matter depends on which run relative paths in a context where cwd is not already pinned — that is the measurement this ticket needs first, not a blanket migration. `ambient.cwd()` exists and a derived accessor (`ambient.resolve()`, matching `ambient.expanduser()`) is the obvious shape if migration is warranted.

## The generalisable part, which outlives this ticket

**When consolidating reads of an ambient fact, enumerate the stdlib calls that read it *indirectly*, not just the ones that name it.** A search for `Path.cwd` and `os.getcwd` is not a search for "reads the working directory". The route table above is the durable artifact; extend it rather than rediscover it.
---

## Design settled with Arnon, 2026-08-19 — the fix is a checker, not just a migration

### `ambient` stays a facts module, and does not become a facade

Arnon caught the drift one instance early: `ambient.expanduser()` is a *path operation* that happens to need a fact, not a fact. Left alone it invites `ambient.resolve()`, then `ambient.absolute()`, and the module becomes a shadow `os.path` where every stdlib call acquires a twin and each twin is a fresh place to diverge from what it mimics.

**The line: `ambient` answers what a fact *is*; it never performs an operation.** `home()`, `cwd()`, `env()` are facts; `env_var()` is a lookup *in* a fact and stays. `expanduser()` moves to `path_utils`, which already owns the home-boundary logic it must agree with. **This ticket does NOT add `ambient.resolve()`** — relative paths get resolved against `ambient.cwd()` explicitly at the sites that need it, which is clearer anyway, since "resolve against *which* directory" is the real question.

### Enforce it with a deny-by-default AST check, not a route table

The reason `expanduser` survived four blinded reviews and `resolve` survived five is that both were caught — when caught at all — by enumerating known-bad routes. **An enumerate-the-bad-list rule cannot catch the route nobody thought of.** Two escapes is the argument for closing it.

**Two rule shapes, both AST, both deny-by-default:**

- **`os` — closed at the import level.** Outside the facade, `os` is used for genuine file operations (`os.replace`, `os.fsync`), which is a short nameable whitelist. Banning the import makes `os.environ`, `os.getcwd`, `os.getenv`, `os.path.expanduser` and `getpwuid` *unreachable* rather than undetected, including routes not yet enumerated. Rides on the import graph `--layers` already walks.
- **`pathlib` — closed over an enumerated API.** `Path` cannot be banned; it is a legitimate type everywhere. But its surface is finite, so the list is exhaustive rather than reactive.

**Measured 2026-08-19 against the running stdlib: 70 members, of which exactly 5 read ambient state.**

| bucket | count | members |
|---|---|---|
| `PurePath` | 24 | pure string logic |
| filesystem operations | 41 | `stat`, `open`, `glob`, `mkdir`, … — **a different concern**, not ambient |
| **ambient-reading** | **5** | `home`, `cwd`, `expanduser`, `resolve`, `absolute` |

**`Path.absolute()` was found by this enumeration** — it prepends `os.getcwd()`, is invisible to a `Path.cwd` patch, and appears in neither this ticket's original body nor the repair agent's route table nor six review rounds. Add it to scope.

Note what the split also settles: **filesystem access is not an ambient fact.** Those 41 members may deserve their own seam one day; folding them into `ambient` is the facade drift above.

### The list is version-dependent, so the checker maintains it

Arnon: *"the answer can only change with new versions of python."* So **do not hardcode the five.** The check enumerates `dir(Path)` at runtime and compares against a stored classification; **a member in neither bucket is a failure**, reported as *"pathlib gained `X`; classify it as ambient-reading or not"*. A Python upgrade then cannot silently widen the hole. Same discipline as this campaign's zero-input rule, applied to version drift.

### What this does to the ticket's cost

The checker enumerates the affected sites, so "measure which of the 17 matter" stops being a manual survey — and it catches the seventh route before it bites rather than after. Build the check as part of this ticket; it is what makes the migration verifiable rather than hopeful.

### A version pin, because enumeration cannot see a behaviour change

Arnon, 2026-08-19: *"you can have a unit test that checks the python version and would fail if it changes — reminding us to revalidate the stdlib mocking-facilitating facade assumptions. Then we change that unit test only after looking for any relevant changes in the standard library."*

**This is not redundant with the runtime enumeration; it covers what enumeration structurally cannot.** Enumerating `dir(Path)` detects a member **added or removed**. It cannot detect an **existing member changing behaviour** — if a future release made `Path.glob()` consult the working directory, the member set would be byte-identical and the check would pass clean. The only instrument that can see that is a person reading the release notes, and the only way to make a person look is to fail.

So: **an automated check for the dimension a machine can see, and a deliberate gate for the one it cannot.**

Mechanics:

- Pin `sys.version_info[:2]`, **not** the patch level. Patch releases rarely change semantics, and a gate that fires on noise gets suppressed — which is the failure mode that matters more than the one it guards.
- **The failure message must say what to revalidate**, not merely that the version moved: name the five classified members, point at the classification, and say that the check is updated only *after* reading the release notes for changes to how they resolve. A gate whose message is "version changed" teaches the reader to bump the constant.
- Updating the pin is the last step of that review, never the first.
