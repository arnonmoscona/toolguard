---
title: TOO-45 architecture_fitness.py coder task recall
type: note
permalink: toolguard/too-45/too-45-architecture-fitness.py-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Build `tools/architecture_fitness.py` on branch `too-45` (repo `/home/arnon/projects/toolguard`).
Repo-root `tools/`, NOT `toolguard/tools/`. Stdlib only. Dev-only instrument the TOO-45
refactoring loop runs every iteration (P2 in the execution plan).

Four modes, in priority order (if short on time, `--layers` and `--guard` matter most):

### 1. `--layers`
Parse `.pyscn.toml`'s `[architecture]` block (tomllib) as SSOT. Layer order
foundation < config < engine < runtime < tooling < support (already encoded as explicit
allow/deny rules in the toml -- use those directly, don't re-hardcode order).
- Completeness: every module under `toolguard/` matches exactly one layer via AST-based
  first-relative-path-segment matching (e.g. `toolguard/tools/decision.py` -> `tools` ->
  tooling). Exit non-zero naming any module matching zero or >1 layers.
  `toolguard/testing/sandbox.py` is a case pyscn itself cannot map -- our tool must map it
  correctly (support layer) and name it, demonstrating the value over pyscn's silent failure.
  `toolguard/__init__.py` (the root package file) is excluded from per-module mapping (it's
  the container, not a layer member).
- Direction: AST import graph (ast.walk, catches function-local imports too -- confirmed
  hook.py:622 has one: `from toolguard.tools.decision import decide` inside a function).
  Report every edge violating the source layer's `allow` list from the toml rules.
  Verified today's known violations:
  - `hook.py` (runtime) local-imports `tools.decision` (tooling) = violation. `tools/decision.py`
    top-level imports `from toolguard.hook import FILE_PATH_TOOLS` (runtime, allowed from
    tooling) -- so it's a one-directional violation, not a symmetric cycle at the layer level,
    though it IS a file-level import cycle (see R5).
  - `config_divergence.py` (config) imports `toolguard.error_log` (runtime) top-level = violation.
  - `auto_migrate.py` (config) local-imports `toolguard.scripts.migrate_permissions` (tooling,
    inside `if` branch) = violation.
  - Did NOT find `config_divergence -> scripts.migrate_permissions` as the spec's expected-list
    implied (only auto_migrate has that one) -- will report actual live findings and flag this
    discrepancy in the report rather than force a match.

### 2. `--predicates --json`
Emit COMPONENT diagnostics per predicate, not just a bool.

- **R3**: zero production sites parse structured data out of a reason string. AST scan for
  `.split`/`.startswith`/`.endswith` calls or `in` membership tests where the receiver/variable
  name contains "reason" (case-insensitive), across `toolguard/**/*.py` excluding test dirs.
  Confirmed baseline sites: `resolve.py:563` (`reason.startswith`), `hook.py:461` and
  `hook.py:978` (`reason.split`). Found a 4th raw match at `compound.py:232`
  (`marker in reason` inside `fallback_kind_for_reason`) -- this is the ALREADY-CONSOLIDATED
  canonical classifier (docstring: "made this function public" specifically to prevent ad hoc
  duplicate parsing elsewhere), so it is deliberately excluded via a small, documented
  allowlist constant, not silently dropped. This reproduces the spec's stated baseline of 3.
  Documented the reasoning inline and will call it out in the report as a judgment call to
  revisit when R3 actually lands.
- **R1**: verdict-ish classes (name matching Decision/Resolution/Verdict, case-insensitive) with
  file:line. `__iter__` shims found: `BashResolution` (resolve.py:149) and `FileResolution`
  (resolve.py:215). Callers: heuristic -- find producer functions (`return BashResolution(`
  etc.), then scan for tuple-unpack call sites (`a, b, c = producer(...)` or
  `for a, b, c in producer(...)`) across toolguard/**. Preliminary check found zero current
  production callers using tuple-unpack style (both hook.py and tools/decision.py use
  attribute access) -- if the scan confirms this, it's a real finding (dead compat shim) worth
  reporting explicitly.
- **R5**: no `runtime`/`scripts` layer module is a non-leaf (fan-in > 0 within the toolguard
  import graph) + import cycles via stdlib Tarjan SCC (~40 lines) on the full module graph.
- **R6**: no `tools/`/`scripts/` module (under `toolguard/tools/`, `toolguard/scripts/`) imports
  a private name (leading underscore, not dunder) from `config`, `permissions`, `compound`,
  `resolve` via AST ImportFrom.
- **R2**: parallel-array field groups on `ToolPatternLayer` (config_types.py:138) -- AST-detect
  dataclass fields, group by "X" / "X_entries" naming pairs (allow/allow_entries,
  deny/deny_entries, ask/ask_entries confirmed by reading the source).

Plus **enrichment footprint** (not a predicate): count + list of production files referencing
`additional_context`/`additionalContext`. Spec says 14 today -- verify live.

### 3. `--metrics`
git-log-based via subprocess (read-only git only, per global rules). Group commits by
`TOO-\d+` token in the FULL commit message (subject+body); untagged commits are singleton
groups ("logical change"). This dedup is what defeats commit-splitting gaming -- do not
shortcut to per-commit.

Zones: core (toolguard/*.py at root) / tools (toolguard/tools/**) / parser (toolguard/parser/**)
/ scripts (toolguard/scripts/**) / testing (toolguard/testing/**). Only files under toolguard/
count toward zone confinement / production-file-count metrics.

Emit: max co-change partners; 100%-coupled pairs (rarer file never seen without the other);
% of logical changes confined to one zone; p90 production files per logical change; scripts
appearing as co-change hubs; max module fan-in (reuse R5's import graph); longest dependency
chain (longest path on the Tarjan-condensed DAG); import cycle count.

**Critical framing (read P.3 in the decision log for evidence):** fan-in is measured but KNOWN
MISLEADING here -- `permissions`/`compound`/`resolve` have fan-in 2 (look like leaves) but
`compound.py` has never changed without both `config.py` and `permissions.py` (100% co-change).
MUST print fan-in and co-change adjacent, with a standing caveat string in the output that
fan-in must not be read as evidence R6 succeeded.

Every metric is an instrument, never a target -- state this in the module docstring.

### 4. `--guard`
`--since <ref>` (default HEAD). Compares ref against CURRENT STATE (working tree, including
uncommitted changes) via `git diff --name-status <ref>` + `git status --porcelain` for
untracked files -- NOT `git diff <ref> HEAD`, since the guard must catch uncommitted iteration
work. Fails on:
- file touched outside the repo, or under `logs/`, `.env`, `.claude.env`, permission-config
  files (`.claude/toolguard_hook.toml`, `.claude/settings*.json`). NOTE: git literally cannot
  see paths outside the repo -- document this limitation; guard checks what git can see, the
  file-tool deny rules (already applied, P4) are the primary defense for genuinely external
  writes.
- test file deleted, or total test count down. Chose STATIC AST counting of `test_*`
  functions/methods in `test/**/*.py` (current: read from disk; ref: `git show <ref>:path`,
  read-only) over `unittest discover`, because discover would require executing the ref's code
  in the current environment, which the guard must not assume works for an arbitrary ref.
  Documented this choice per the spec's "say which you chose and why".
- new entry in `pyproject.toml`'s `[project.dependencies]` (currently `[]` -- runtime stdlib
  only constraint). Compare via tomllib on `git show <ref>:pyproject.toml` vs current file.
- `ruff check .` or `ruff format --check .` failing, or `tools/check_doc_links.py` exiting
  non-zero.
Exit non-zero with a readable list of failures. No network, no non-installed tool.

## Output
Human-readable text by default; `--json` for machine consumption (predicates mode explicitly
needs `--json`; other modes should support `--json` too per "Both must carry the same facts").

## Testing
`test/unit/test_architecture_fitness.py`. Small synthetic fixture trees for graph/layer logic
(not pinned to today's live module set). A couple of smoke tests against the real tree that
just assert it runs without crashing and produces output.

## Conventions confirmed
- `uv run python`, never bare python. `unittest discover -s test -t .`.
- Stdlib only: `argparse`, `ast`, `tomllib`, `subprocess` (git), `pathlib`, `dataclasses`.
- CLI convention matches `tools/check_doc_links.py`: module docstring explains WHY, argparse,
  `def main(argv=None) -> int`, `sys.exit(main())`.
- `REPO_ROOT = Path(__file__).resolve().parents[1]` convention (from `tools/corpus_build.py`).
- No async/threading/local imports (module-level imports only in MY code -- note hook.py's own
  local import is a finding to REPORT, not something to fix; out of scope).
- Do not modify `test/verdict_corpus/` or `tools/corpus_build.py` (just landed, green).
- No git writes. Read-only git (log/diff/show/status) only.

## Scope guard
This is inherently one large new file + one new test file = 2 files, well within the 7-new-file
/ 10-total-file scope inflation guard. No existing files should need modification for this task
(no production toolguard/ code changes expected).

## When done
Write implementation report to basic-memory ticket-scoped `TOO-45/`, tagged `task-memory` +
`TOO-45`. Include live current values for every predicate/metric, test/ruff status, deviations
from spec (e.g. the config_divergence->scripts.migrate_permissions discrepancy above, the R3
compound.py:232 exclusion judgment call).
