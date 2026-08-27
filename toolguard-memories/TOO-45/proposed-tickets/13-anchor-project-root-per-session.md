---
title: 13-anchor-project-root-per-session
type: note
permalink: toolguard/too-45/proposed-tickets/13-anchor-project-root-per-session
---

# Proposed: anchor the project root for the whole session, and settle relative-glob intent

**Status:** found 2026-08-08 while answering a question about hook parameters. **Arnon: needed before RC1**, not necessarily in TOO-45. Not trivial.

## The defect, measured

Claude Code passes the hook **no project identifier** — only `cwd`. Toolguard treats `cwd` as the starting point for an upward marker search, so the project root is recomputed **on every single tool call**.

`cwd` tracks the shell. Measured directly: planted a `pyproject.toml` in `tmp/cwdprobe/`, `cd`'d there, ran a trivial command — toolguard relocated the project root to that directory and wrote `tmp/cwdprobe/logs/`. A `cd` into any subdirectory holding a root marker moves toolguard's notion of the project mid-session.

Nested markers are ordinary: a vendored package, a subproject, a test fixture, a `frontend/` directory. Nothing about them looks dangerous.

## Two resolvers disagree about where the project is

From the nested root, `python3 --version` was **still denied**, with provenance naming the repo's own `.claude/toolguard_hook.toml`. So **rule discovery walked past the nested marker while project-root resolution did not.**

One session can therefore scatter its audit trail across several `logs/` directories while enforcing one consistent rule set. The audit trail is the thing this ticket's parent effort spent most of its work protecting.

## Why the harness cannot be trusted to contain this

Today the harness resets shell cwd when it leaves the project and preserves it within — so exposure is bounded to subdirectories. **That is undocumented, unversioned behaviour that can change between Claude Code releases.** A security boundary must not rest on it.

## Requirement

**Resolve the project root ONCE at session start and use it for the rest of the session.** `toolguard/session_start.py` already receives a `SessionStart` payload carrying `session_id` and `cwd`, before any `cd` can occur — the natural capture point.

Design questions:

- **Storage.** Toolguard is a fresh interpreter per tool call, so the anchor must be persisted, keyed by `session_id`. `session_id` is present on every `PreToolUse` payload and currently **read by nothing** — see [[01-once-per-session-warnings]], which needs the same machinery. These two should probably be designed together.
- **Absent anchor.** What happens on the first call of a session where `SessionStart` did not fire, or the store was cleaned? Falling back to today's per-call resolution reintroduces the defect silently; refusing to operate is a fail-closed choice with real friction. **This needs a stated policy, not a default.**
- **Reaping.** Session-keyed state accumulates. Same problem as ticket 01.
- **Legitimate monorepos.** A user genuinely working across sub-projects in one session may *want* the root to follow. If so, that must be opt-in and explicit, not an accident of `cd`.

## The semantics: DECIDED — every rule anchors to the current runtime project

**Arnon's position, adopted (2026-08-08): all rules, whatever their provenance, are anchored to the current runtime project.** Two reasons:

1. **Migration invariance.** A rule promoted from project level to a shared level because it is reusable must not change meaning. Moving it up widens *which projects it applies to*, never *what it means inside a project*.
2. **Mental model.** When a person writes a rule, the project is the frame they have in their head. Behaviour should match that picture.

**This is already what the code does, deliberately.** `Configuration.resolve_config_path` (`config.py:915`) calls itself "the single anchor point for that rule" and resolves a relative path against the project root "regardless of which level/directory declared it". So this ticket **records and documents an existing design decision**; it does not change semantics.

**A correction to an earlier claim in this ticket**: I asserted there was no syntax for "anywhere". That was wrong. Three tiers already exist and are syntactically distinct:

| pattern form | anchor |
|---|---|
| `**/.env` (relative) | current project root |
| `~/.ssh/**` | home directory, unchanged |
| `/etc/**` (absolute) | filesystem, unchanged |

So the "everywhere" intent **is** expressible today. The problem is discoverability, not expressiveness.

### The qualification worth deciding on

**The anchoring rule is most intuitive for `allow` and least intuitive for `deny`.**

- A user-level **allow** anchored to the project is *conservative* — it permits only within the project. Fails safe.
- A user-level **deny** anchored to the project is *permissive* — it protects only within the project. **Fails open relative to what the author probably intended.**

People promote a deny to a shared level because they want it **everywhere**, not because they want it **in every project separately**. Both readings preserve migration invariance; they differ exactly when a tool call touches a path outside any project.

This is not an argument against the decided semantics. It identifies where a user will most plausibly be wrong, which is what the audit should target.

**Open question**: does the same anchoring apply to `[hard_deny]` rules, which are pooled across levels and are the strongest statement a user can make? "Never, anywhere" is the natural reading of a hard deny; project-anchoring would weaken it. Needs checking and an explicit answer.

### Edge case needing a stated policy

`resolve_config_path` returns the pattern **unchanged when no project root is known**. So in a directory with no marker, every relative pattern silently becomes unanchored — a semantic change at precisely the moment least likely to be noticed. Decide whether that is intended, and say so.

## Documentation requirement

**Arnon's instruction: the agreed semantics must be documented in the same place that explains the layered configuration** — not in a separate note. A reader learning how levels compose must learn anchoring at the same time, because the two interact. The three-tier table above is the core of it.

## Implications for the security-audit skill

The audit should flag **probable intent mismatches**, not only syntax errors:

- a relative **deny** on a sensitive filename (`.env`, keys, credentials) declared at a shared level — likely meant as "everywhere", actually "this project only"
- any deny whose coverage would change if the project root moved
- relative patterns in a configuration where no project root can be resolved, since those silently stop being anchored

This is a new class of finding — *configured intent probably does not match configured effect* — and it is arguably worth more than the syntactic checks, because this failure is invisible by construction.

## Size

Not trivial. Three separable pieces: session anchoring (needs the `session_id` store), glob-intent semantics (a design decision with a migration story), and the audit findings (depends on the second). The first is shippable alone and removes the moving-target defect.

## Decision needed

Scope and sequencing. The anchoring piece alone closes the measured defect; the glob-semantics piece is the one that needs your judgement about what users mean, and it is the one that can break existing configs.