---
title: TOO-45 R5b coder task recall
type: note
permalink: toolguard/too-45/too-45-r5b-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task as given

Implement TOO-45 step R5b on branch `too-45` in `/home/arnon/projects/toolguard`.

R5's predicate: entry points and scripts are leaves; no `runtime` or `scripts` module is
imported by anything else. R5a-0 (predicate fix) and R5a (hook<->tools.decision cycle) were
already done and green before this task started (suite 2,367 OK, corpus no differences, guard
12/12). `--predicates` reported exactly two real R5 violations going in:

- `scripts.migrate_permissions` (scripts_package) imported by: `auto_migrate`,
  `tools.installer`, `tools.rule_apply`
- `update_check` (entry_point) imported by: `tools.installer`

Task: fix the FIRST one only. `update_check` is explicitly deferred (measured ~180 affected
tests) -- do not touch it.

`toolguard/scripts/migrate_permissions.py` is the `toolguard-migrate` console script AND a
library three other modules import. Split it: move the importable logic into a proper module
at the right layer, leave the console-script entry point as a thin `main()` that calls it,
repoint `auto_migrate`, `tools.installer`, `tools.rule_apply` at the library.

Constraint from the ticket: new module's home must be a layer the three importers can legally
reach -- `auto_migrate` is in `config`, `tools.*` is in `tooling`. Must add the new module to
`.pyscn.toml`'s layer map and confirm `--layers` completeness stays 100%.

`auto_migrate.py:172` had `# noqa: PLC0415` local import of
`toolguard.scripts.migrate_permissions`, marked "comes off when R5 breaks it" -- if the split
removes the cycle, this becomes a normal module-level import and the marker must go (RUF100
would fail on a marker whose reason is gone).

Blast radius measured at ~88 affected tests (cost estimate, not an objection). Rewrite call
sites freely, keep behaviour each test checks, update Given/When/Then docstrings in the same
edit, state explicitly any test deleted and why.

## Acceptance commands (all must show real output)

```
uv run python -m unittest discover -s test -t .           # expect OK
uv run python tools/corpus_build.py --verify              # expect: NO DIFFERENCES
uv run python tools/architecture_fitness.py --guard       # expect: PASS, 12 canaries
uv run python tools/architecture_fitness.py --layers      # completeness 100%
uv run python tools/architecture_fitness.py --predicates  # scripts.migrate_permissions gone from R5
uv run ruff format . && uv run ruff check --no-cache .
```

Plus a real end-to-end smoke test of the console script (not mocked).

## Hard rules

- No git write ops ever (checkout/restore/stash/reset -- these HANG waiting for a human).
  Read-only git fine.
- Back up original bytes to
  `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r5b-backups/`
  BEFORE editing, verified populated.
- Report progress, avoid long silent stretches.
- Tree holds substantial uncommitted work across ten completed TOO-45 stages -- don't disturb
  it, don't commit, don't copy the repo.
- `uv run python`, never bare `python`. `unittest`, not `pytest`. Always
  `ruff check --no-cache`.
- No local imports, no async, no threading. Prefer frozen dataclasses over tuples for
  multi-value returns that aren't a strict pair.
- Don't edit anything outside the repo.

## Required reading before starting

Basic-memory note `TOO-45/TOO-45 R5 scoping trace.md` in project `toolguard` -- has the
executed measurements for R5, including the blast-radius table and the recommendation that the
new module belongs "beside `config_write_guard`" (i.e. in the `config` layer).

## Report destination

`TOO-45/TOO-45 R5b implementation report.md` in basic-memory project `toolguard`, tagged
`task-memory` and `TOO-45`.
