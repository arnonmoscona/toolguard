---
title: TOO-45 architecture_fitness.py implementation report
type: note
permalink: toolguard/too-45/too-45-architecture-fitness.py-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Built `tools/architecture_fitness.py` (repo-root, dev-only, stdlib-only) and
`test/unit/test_architecture_fitness.py` (74 tests). All four modes implemented:
`--layers`, `--predicates --json`, `--metrics`, `--guard`. Full suite: 2266 tests, OK
(baseline was 2192; +74 all new, none modified). `ruff format --check .` and `ruff check .`
clean across the whole repo. `tools/check_doc_links.py` clean. The tool's own `--guard`
passes when dogfooded against this session's changes.

Files:
- `/home/arnon/projects/toolguard/tools/architecture_fitness.py` (new, ~1180 logical lines
  after formatting -- `wc -l` reports 1543 including blank/docstring lines)
- `/home/arnon/projects/toolguard/test/unit/test_architecture_fitness.py` (new, 74 tests)

No existing files were modified.

## Live numbers on the real codebase TODAY (CP1 evidence)

### `--layers`

Completeness: **all modules map to exactly one layer** (including
`toolguard/testing/sandbox.py`, which the plan flags as unmappable by pyscn itself --
under this tool's first-relative-path-segment matching it maps cleanly to `support`,
demonstrating the value over pyscn's silent failure).

Direction violations (3), matching the plan's expected list except one discrepancy noted below:
- `auto_migrate` (config) -> `scripts.migrate_permissions` (tooling) at line 172, local import
- `config_divergence` (config) -> `error_log` (runtime) at line 16
- `hook` (runtime) -> `tools.decision` (tooling) at line 622, local import

**Discrepancy from the plan's expected-violations list:** the plan lists
"`config_divergence`/`auto_migrate` -> `scripts.migrate_permissions`" as a pair. Only
`auto_migrate` actually imports `scripts.migrate_permissions`; `config_divergence` does not
(verified by direct grep before writing the detector, and confirmed by the tool's own scan).
Not a bug in the tool -- a minor inaccuracy in the plan's summary phrasing.

### `--predicates`

**R1** (one verdict type): FAIL. 7 verdict-ish classes found (`ResolvedDecision`,
`ProjectRootResolution`, `BashResolution`, `FileResolution`, `Decision`, `LedgerDecision`,
`SingleDecision`). 5 classes define `__iter__` tuple-compat shims: `TreeNode`,
`LeafCommand`, `UndecidableSegment` (all in `parser/`, previously undocumented as
"verdict-ish" -- worth the architect judge's attention, since these are parser AST nodes with
`__iter__`, not resolution results, so R1's class-name heuristic over-catches slightly here),
plus the two known ones, `BashResolution` and `FileResolution` (both in `resolve.py`).
**Finding: all 5 shims currently have ZERO tuple-unpacking callers** in production code (the
heuristic producer/caller scan found none) -- every current caller of
`resolve_bash_permission_detailed`/`resolve_file_path_permission_detailed` already uses
attribute access. If that holds up under closer review, the `__iter__` compat shims may be
dead code today, which would make R1 cheaper than the plan assumes.

**R2** (no parallel arrays on `ToolPatternLayer`): FAIL, 3 groups: `allow`/`allow_entries`,
`deny`/`deny_entries`, `ask`/`ask_entries` -- exactly matching the class's own documented
invariant.

**R3** (no reason-string parsing): FAIL, **5 sites, not the plan's baseline of 3**:
`hook.py:461`, `hook.py:978`, `resolve.py:563` (the 3 the plan names), plus **two new sites
this AST scan found that the plan's grep-based count missed: `resolve.py:692` and
`resolve.py:699`**, inside `_resolve_one()`, extracting `matched_rule` from a variable named
`reason_body` via `"  [" in reason_body` and `reason_body.startswith(marker)`. These do the
same category of ad hoc string-parsing as the 3 known sites. They were missed by a literal
`reason\.` / `\breason\b` grep (used both in the plan and in my own initial manual check)
because the variable is named `reason_body`, not `reason` -- `\breason\b` doesn't match inside
`reason_body` (no word boundary after `_`), and `reason.` requires a literal dot. This AST
scan matches on substring containment (`"reason" in name.lower()`), so it catches this case;
**this is a genuine, previously-undocumented finding, not a tool bug** -- verified by reading
the source directly. `compound.py:232`'s `fallback_kind_for_reason` (the already-consolidated
canonical classifier) is excluded via a documented allowlist constant
(`R3_SANCTIONED_SITES`), which reproduces the plan's "Today: 3" for the 3 sites it names,
before the 2 new ones are added.

**R5** (runtime/scripts leaves, no cycles): FAIL. Two import cycles found:
- `tools.decision <-> hook` (the known one)
- **`parser.multiline <-> parser.command_extractor`, previously undocumented.** Verified real
  (not a scanner artifact): both sides carry `# noqa: E402/F401` and `# noqa: PLC0415`
  suppressions, i.e. the codebase already silently tolerates this cycle via lint-suppression
  rather than fixing it. Worth flagging to the architect judge -- it's inside the `engine`
  layer (both `parser.*`), so it's invisible to the layer-direction check (same layer, always
  allowed) and would stay invisible to any check that only looks at layer boundaries.

Non-leaf runtime/scripts modules: **broader than the plan's known list.** The plan names only
`hook` and (implicitly) `scripts.migrate_permissions`. A strict reading of the predicate text
("no runtime/scripts module is a non-leaf") also flags `error_log`, `log_writer`,
`session_warnings`, `subagent`, `update_check` -- every one of these has fan-in from `hook.py`
itself (its normal internal collaborators) or from `tools/` callers. **This is a genuine
interpretation ambiguity I'm flagging rather than silently resolving:** is R5 about the ENTIRE
`runtime` layer having zero internal fan-in (very strict -- would forbid `hook.py` from
importing its own helper modules), or specifically about **entry points**
(`hook`, `session_start`, `update_check`, `security_audit`, `maintenance`, `installer`,
`scripts.migrate_permissions` -- i.e. the `[project.scripts]` console-script targets in
`pyproject.toml`) not being importable as libraries? Under the narrower "entry points" reading,
`update_check` is still a real, interesting hit (it's a declared console-script entry point AND
imported by `tools/installer.py`), but `log_writer`/`session_warnings`/`subagent`/`error_log`
would not be. I implemented the literal, broader reading (per the module docstring's own
"component diagnostics, not a bare boolean" directive -- report facts, let the judge interpret)
and documented this explicitly in the code and here; the architect judge should settle which
reading R5 actually means before using this as a step-closing signal.

**R6** (no private imports from config/permissions/compound/resolve): FAIL, 1 site:
`tools/takeover_audit.py:87` imports `_strip_tool_wrapper` from `config`.

**Enrichment footprint** (tracked diagnostic, not a predicate): **14 files**, exactly matching
the plan's stated baseline: `compound`, `config`, `config_types`, `config_write_guard`, `hook`,
`log_writer`, `resolve`, `rule_entry`, `rule_sort`, `testing.sandbox`, `toml_scan`,
`tools.config_access`, `tools.decision`, `tools.installer`.

### `--metrics`

27 logical changes total (grouped by `TOO-nn` ticket token across 70 raw commits), 10 touching
production `toolguard/*.py`. Max co-change partners: `config.py` (69). 71 pairs meet the
100%-coupling bar (rarer file touched >= 3 times, never without its partner) -- text output
caps at top 30 by co-change count, full list available via `--json`. Confirms the decision
log's central finding: `compound.py <-> config.py` and `compound.py <-> permissions.py` are
both 4/4 (100% coupled, though at a lower absolute count than the decision log's raw 6/6 --
methodology difference: my grouping dedupes by ticket, the decision log's number was likely
per-matching-commit; both are internally consistent, just not directly comparable numbers).
`hook.py <-> permissions.py` is the single highest raw pair at 6/6.

% logical changes confined to one zone: 40.0. p90 production files per logical change: 45.0
(driven by the large TOO-19 commits touching dozens of files). `scripts/migrate_permissions.py`
is the top scripts co-change hub (69 partners) -- consistent with the plan's S1 hypothesis that
it parses more than a shallow transport script should.

Max module fan-in (import-graph, this tool's own AST-based count): `config`, **25**. The
decision log's grep-based count on 2026-08-04 was 28 -- different methodology (raw
`from toolguard...` import statement occurrences vs. distinct importing modules in an AST
graph), not a contradiction; noted so the two numbers aren't compared directly by mistake.
Import cycle count: 2 (both listed above). Longest dependency chain: 12 hops,
`tools.maintenance -> tools.hierarchy -> tools.redundancy -> tools.replay ->
{hook,tools.decision} -> auto_migrate -> scripts.migrate_permissions -> config_divergence ->
config -> config_validation -> rule_entry -> issues` (the cycle collapses to one combined node
as designed).

Fan-in/co-change caveat is printed in every `--metrics` run, adjacent to the fan-in figure, per
the spec's explicit requirement.

**Deviation from spec:** added a `MIN_COUPLING_OBSERVATIONS = 3` threshold (documented, with
rationale) to the 100%-coupling pair list. Without it, the list was 1463 pairs on first smoke
test -- with only 10 production-touching logical changes so far, any two files that happened to
land in the same big commit trivially look "100% coupled" on a single coincidence. The threshold
requires the rarer file to have been touched at least 3 times (matching the decision log's own
bar of 6 observations as "real evidence"). This is a judgment call, not in the original spec;
flagging it explicitly as requested.

### `--guard`

Passes cleanly against `HEAD` on both a clean state and dogfooded against this session's actual
changes (2 new files). Verified via a synthetic-repo integration test suite (not by touching real
guarded paths) that it correctly fails on: an untracked file under `logs/`, a test file deleted,
total test count decreasing, and a new `pyproject.toml` dependency.

**Design choices, as instructed to document:**
- **Test counting: static AST counting of `test_*` functions/methods**, not `unittest
  discover`. Chosen because `discover` would need to import and execute the *ref's* code
  inside the *current* environment/dependencies, which the guard must not assume works for an
  arbitrary historical ref (a ref from before a dependency was added, or with an import-time
  syntax the current interpreter handles differently). Ref-side counts are read via `git show
  <ref>:path` (read-only, no checkout); current-side counts read the working tree directly (so
  uncommitted changes are seen).
- **Comparison base is the CURRENT STATE (working tree + staged + untracked) vs. `--since`**,
  via `git diff --name-only <ref>` (which diffs a ref against the working tree, not just
  `HEAD`) plus `git ls-files --others --exclude-standard` for untracked files -- not `git diff
  <ref> HEAD`. This is deliberate: the guard runs mid-iteration, before a commit exists, and
  must catch in-progress work.
- **Known, honest limitation, stated in the module docstring and here:** a file touched
  literally outside the repository directory is invisible to every git command this guard
  runs -- git cannot see paths outside its own working tree at all. The guard's outside-repo
  check only catches the degenerate case of a path that resolves outside the repo root via git
  machinery (e.g. a symlink oddity); it is NOT a general defense against writes to
  `~/.claude/*` or similar. The primary defense for that is the `Write`/`Edit` deny rules
  already applied in `.claude/toolguard_hook.toml` (P4, done per the decision log) -- the guard
  is the deterministic backstop for what git *can* see, not a replacement for those rules.
- Dependency check is scoped to `[project].dependencies` only (currently `[]`), not
  `[dependency-groups].dev` -- matches "runtime is standard-library only"; dev tooling deps are
  out of scope for this check.

## Bugs found and fixed during self-review

1. `extract_toolguard_imports` originally hardcoded `relative_module_path(py_file)` with the
   default `TOOLGUARD_DIR` regardless of what tree was being scanned -- broke every synthetic
   test that used a temp directory. Fixed by threading a `package_root` parameter through
   `extract_toolguard_imports`, `check_layers`, and `build_import_graph`.
2. `find_reason_parsing_sites` double-counted a site when one line trips both AST patterns
   (e.g. `reason.split(...) if ": " in reason else None` matches both the `.split()` call and
   the `in reason` check) -- deduped by `(module, line)`.
3. `find_iter_shims`'s producer-detection had a dead `... or True` condition (functionally
   harmless because filtering happened downstream, but misleading and would confuse a future
   reader) -- rewrote as an explicit two-pass algorithm (collect all `__iter__`-bearing classes
   first, across every file, before looking for producers/callers, since a producer can live in
   a different module than its class).
4. `--metrics`' 100%-coupled-pairs list produced 1463 pairs on first run -- added the
   documented `MIN_COUPLING_OBSERVATIONS` threshold and capped text rendering to the top 30
   (full list still in `--json`).
5. One real local-import anti-pattern violation in my own first draft: `import re` inside
   `_ticket_token`. Moved to module level with a compiled `_TICKET_TOKEN_RE` constant. Noting
   this per the global CLAUDE.md instruction to record anti-pattern violations even when
   self-caught and fixed.
6. Added `tools/check_doc_links.py` conventions matched (`REPO_ROOT = Path(__file__).resolve()
   .parents[1]`, `argparse`, `def main(argv=None) -> int`, `sys.exit(main())`).

## What I could not fully verify / left as an open question

- **R5's scope ambiguity** (entire `runtime` layer vs. just entry points) -- documented above
  and in the code; deliberately did not silently narrow it, per the instruction to emit
  component-level facts rather than pre-judged pass/fail.
- **R1's shim caller-detection is a heuristic**, not true call-graph tracing (this AST-only
  tool has no type inference): it links a tuple-unpack call site to a shim class via "some
  function in the tree returns `ClassName(...)` and its name matches the unpacked call's callee
  name". This is exact for this codebase's actual shape (`result = resolve_bash_permission_
  detailed(...)` style) but could theoretically under- or over-match in a codebase with more
  indirection. Documented in the function's own docstring.
- Did not add a P2-mentioned "test asserting no module under toolguard/ imports from repo-root
  tools/" as a NEW production-code check inside `architecture_fitness.py` itself (it isn't one
  of the four requested modes) -- instead added it as
  `TestShippedCodeDoesNotImportDevTools.test_no_toolguard_module_imports_repo_root_tools` in the
  test file, since the plan explicitly asked for "a test", not a fifth CLI mode. Currently
  passes (no toolguard module imports bare `tools`).

## Existing-code reuse check

Checked for prior art before implementing: no existing Tarjan/SCC, import-graph, or
architecture-layer-checking code exists anywhere in `toolguard/` or `tools/` (the closest thing,
pyscn, is an external dev dependency already known to be inadequate -- that inadequacy is this
tool's whole reason for existing, per the ticket). `tools/corpus_build.py` and
`tools/check_doc_links.py` were read for CLI/style conventions and followed, not duplicated.
Nothing in the stdlib provides layer-aware import-graph analysis; `ast`/`tomllib`/`subprocess`
(all stdlib) were sufficient.

## Self-review results

- `uv run python -m py_compile` on both files: clean.
- `uv run ruff format .` / `uv run ruff check .`: clean, whole repo (146 files formatted, no
  changes needed beyond the 2 new files during development).
- `uv run python tools/check_doc_links.py`: clean.
- `uv run python -m unittest discover -s test -t .`: **2266 tests, OK** (baseline before this
  work: 2192; net +74, all new, zero existing tests modified).
- Anti-pattern scan: no `async`/`await`, no `threading`, one local-import violation found and
  fixed (see bug #5 above). No new files beyond the 2 (well within the 7-new-file scope guard).
- Dogfooded `--guard` against this session's own diff: PASS.

## Time and cost (estimated)

Exact wall-clock start time wasn't captured at session start; times below are reconstructed from
timestamps taken during the session and are therefore approximate, not precise:

| phase | approx elapsed | approx cost (Sonnet 5 pricing, rough token estimate) |
|---|---|---|
| Phase 1: planning, reading plan/decision-log/CLAUDE.md, verifying baseline sites | ~20 min | ~$0.60 |
| Phase 2: implementation (module + iterative smoke-testing + refactor for testability) | ~60 min | ~$2.20 |
| Phase 2/3: test file authoring + debugging (2 real bugs found via tests) | ~35 min | ~$1.30 |
| Phase 3: self-review (anti-pattern scan, docstring audit, full-suite runs, dogfooding) | ~15 min | ~$0.50 |
| Phase 4: this report | ~10 min | ~$0.35 |
| **Total** | **~2h20m** | **~$5.0** |

## Relations

- relates_to [[TOO-45 architecture overhaul execution plan]]
- relates_to [[TOO-45 decision log]]

## Addendum: guard canary check (coordinator-requested, post-initial-delivery)

### Correction to the original report

The original report described `parser.multiline <-> parser.command_extractor` as "previously
undocumented". **That's wrong and is retracted.** The TOO-45 ticket lists exactly two import
cycles, and that is one of them -- the tool finding it is a correct confirmation of a known
cycle, not a new discovery. No code change was needed for this; it's a correction to the report
text only. (The R3 `resolve.py:692/699` finding and the R5 non-leaf-scope ambiguity, both
elsewhere in the original report, stand as originally written -- only the cycle-novelty claim
was wrong.)

### Addition: `--guard` now asserts the guard rules are actually loaded

**Why:** `.claude/toolguard_hook.toml` is a symlink into an external, deliberately-uncommitted
dotfiles change, and `~/.toolguard/rules/git.rules.toml` lives outside any repository. Neither
is protected by version control here. Because `no_match_fallback = "allow_with_no_warnings"`,
losing either file's `<TEMPORARY>` deny fences fails OPEN and SILENT -- nothing else would
notice. The diff-based guard checks (file-touch, test-count, dependency) all answer "did the
diff do something forbidden"; none of them ask the logically prior question, "are the forbidding
rules even still loaded in the live hook, right now."

**What was built:**
- `GUARD_CANARIES`: one module-level constant, 12 fixed `(tool, target, expected-verdict)`
  cases -- 7 Bash git-command cases (5 deny, 2 allow) exercising
  `~/.toolguard/rules/git.rules.toml`'s fences, and 5 file-tool cases (3 deny, 2 allow)
  exercising `.claude/toolguard_hook.toml`'s fence. The 2 Bash allows and 2 file-tool allows are
  deliberate, per the coordinator's instruction: a canary set that only checks denies would pass
  happily even if the rules over-reached and started denying ordinary work.
- Each case is evaluated through the **live, installed toolguard binary** via
  `toolguard --eval` (read-only mode; documented in `toolguard/hook.py`'s `_run_eval_mode`),
  never by reading the rules files and inferring what they'd do -- the whole point is to ask the
  thing that's actually authoritative.
- Binary resolution: `~/.local/bin/toolguard` first, falling back to `shutil.which("toolguard")`
  on PATH. When neither resolves, the check reports **SKIPPED with a clear reason** (surfaced as
  a `GuardReport.warning`, never silently) and does **not** fail the guard -- a missing binary is
  an environment problem, not evidence the rules were lost.
- A mismatch is reported as a failure naming the tool, target, expected verdict, and actual
  verdict. `GUARD_CANARIES` carries an extensive module-level comment (per the coordinator's
  instruction) stating it must be updated whenever the `<TEMPORARY>` fences change, and that a
  mismatch means EITHER the guards were lost OR the rules were deliberately changed and the
  constant is stale -- the tool cannot tell which; that's the operator's call.
- New standalone mode: `--guard-canaries-only` -- runs *only* the canary check, skipping the
  diff/test-count/dependency/lint checks (none of which are meaningful without a diff base).
  Wired into `main()`'s "at least one mode required" check and JSON payload alongside `--guard`.
- `run_guard()` gained `only_canaries`, `run_canaries`, and `canary_binary` parameters --
  the last two exist purely so the tool's own test suite can inject a stub binary and disable
  the real canary check, per the explicit instruction not to make unit tests depend on the real
  installed binary or real permission config.

### Canary results on this machine, right now (2026-08-04)

All 12 canaries pass against the live installed hook (`~/.local/bin/toolguard`, via
`uv tool install`):

| tool | target | expected | actual |
|---|---|---|---|
| Bash | `git clean -fdx` | deny | deny |
| Bash | `git stash` | deny | deny |
| Bash | `git commit --amend` | deny | deny |
| Bash | `git rm -r toolguard/tools` | deny | deny |
| Bash | `git bisect start` | deny | deny |
| Bash | `git commit -m x` | allow | allow |
| Bash | `git stash list` | allow | allow |
| Write | `<repo>/logs/probe.md` | deny | deny |
| Edit | `<repo>/.claude/toolguard_hook.toml` | deny | deny |
| Write | `/home/arnon/.claude/settings.json` | deny | deny |
| Write | `<repo>/toolguard/compound.py` | allow | allow |
| Read | `<repo>/logs/probe.md` | allow | allow |

Verified twice: once by hand via direct `printf ... | toolguard --eval` invocations before
writing any code (to confirm the expected table was still accurate), and once via
`--guard-canaries-only --json` after implementation, both agreeing exactly.

### Added runtime

`--guard-canaries-only` alone: **~1.2s** (12 real subprocess invocations of the installed
binary, ~100ms each). Full `--guard --no-lint` (diff/test-count/dependency checks + canaries):
**~2.0s**, up from an unmeasured-but-clearly-sub-second diff-only baseline (the diff checks
alone are a handful of `git` subprocess calls plus AST parsing of the test tree). Full `--guard`
with lint (`ruff check`, `ruff format --check`, `check_doc_links.py`) plus canaries: **~2.4s**.
All well within "cheap, fast, no network."

### Tests added (13, using a stubbed hook binary throughout)

New `TestGuardCanaries` class (9 tests) plus 4 more spread across the existing structure:
- `_write_stub_hook_binary()` test helper: writes a small, self-contained, executable Python
  script (shebang line built from `sys.executable`) that mimics `toolguard --eval`'s I/O
  contract, so canary-logic tests **never** touch the real installed binary or this machine's
  permission config.
- Covers: all-pass against a matching stub; a mismatch reported with target/expected/actual;
  unparseable stub output reported as a "canary error" (not a silent pass); the skip path when
  `resolve_toolguard_binary()` finds nothing (patched, not simulated by hiding the real binary);
  `resolve_toolguard_binary()`'s local-bin-first / PATH-fallback / none-found branches (`Path.home`
  and `shutil.which` both patched); `--guard-canaries-only` skipping the diff-based checks
  entirely on a synthetic repo that would otherwise fail them; full `--guard` mode carrying a
  canary mismatch alongside a clean diff; `render_guard_text` surfacing the canary count and
  warnings.
- Also fixed the **5 pre-existing `TestGuardIntegration` tests** (written earlier in this same
  task, not pre-existing repo tests) to pass `run_canaries=False` -- without that they would have
  started silently depending on the real installed binary the moment `run_canaries` defaulted to
  `True`, exactly the dependency the coordinator flagged.
- Two smoke tests against the real repo/real binary (consistent with the file's existing smoke-test
  allowance): `test_guard_canaries_only_runs_on_real_repo` and
  `test_main_guard_canaries_only_flag_smoke` -- both assert shape/non-crash only, never a specific
  verdict, since those will legitimately change when the `<TEMPORARY>` fences are removed.

### Status after this addition

- `uv run python -m unittest discover -s test -t .`: **2279 tests, OK** (was 2266 before this
  addition; +13 new, zero modified beyond the 5 `run_canaries=False` additions noted above, all
  within the file I authored this task).
- `uv run ruff format --check .` / `uv run ruff check .`: clean, whole repo.
- `uv run python tools/check_doc_links.py`: clean.
- Anti-pattern scan: no new `async`/`threading`/local-import issues.
- Dogfooded `--guard --since HEAD` (full mode, including the real canary check against the real
  binary) against this session's actual diff: **PASS**, all 12 canaries evaluated and matched.

## Addendum 2: three predicate-proxy defects fixed (coordinator-requested)

All three fixes are to `tools/architecture_fitness.py` only. No `toolguard/` production code,
`test/verdict_corpus/`, or `tools/corpus_build.py` touched.

### Fix 1 -- generated code excluded from predicates/metrics, never silently

Added `is_generated_file()` (banner-scan over the first 10 lines for `"generated from"`,
`"do not edit"`, `"@generated"`, `"autogenerated"`, case-insensitive -- content-detected, not a
hardcoded filename, per the explicit instruction that a hardcoded path silently stops protecting
a second generated file). `iter_source_files()` wraps `iter_python_files()` and drops generated
files; every style/debt detector (R1/R2/R3/R6) and `build_import_graph()` (shared by R5 and every
`--metrics` figure) now use it instead of the raw iterator. `--layers` is deliberately
**unchanged** -- it still validates the real import graph including generated files, since their
imports are still real architecture.

Exclusions are never silent: `list_generated_files()` (dotted paths, for `--predicates`) and
`generated_repo_paths()` (repo-relative POSIX paths, for `--metrics`, matching git's own path
spelling) are both reported explicitly in the output under a new `generated_files_excluded` key,
rendered as its own section in both `--predicates` and `--metrics` text output.

**Found on this repo today: exactly 1 generated file** -- `toolguard/parser/bash_parser.py`
(confirmed: its first line is literally `# This file was generated from bash_parser.peg`).

### Fix 2 -- R1 scope now excludes `toolguard/parser/` explicitly

Added `R1_OUT_OF_SCOPE_PACKAGES = ("parser",)` (R1-specific -- explicitly NOT applied to R5's
cycle check, which still needs to see `parser.multiline <-> parser.command_extractor`, or to R6,
which never looked at `parser/` anyway) with a comment citing the execution plan's "Out of
scope, unchanged: ... toolguard/parser/". Both `find_verdict_types()` and `find_iter_shims()`
skip modules under it. `r1_out_of_scope_modules()` reports every module in the excluded package
(including the generated one, for full transparency even though it's independently excluded by
fix 1 too) under R1's own `out_of_scope_excluded` key, with a reason string, rendered in the
text output.

### Fix 3 -- R3 detector widened; found the false negative the coordinator described, STILL LIVE

Widened `_REASON_STRING_METHODS` to add `rsplit`, `partition`, `rpartition`, `rindex`, `index`,
`find` (receiver-based, same as before). Added a new branch, `_REASON_REGEX_METHODS = {"match",
"search", "fullmatch"}`, checked against every **argument** of the call (not the receiver) --
this is the structural fix, since a compiled pattern's own `.match(reason)` or a module-level
`re.match(pattern, reason)` both put the reason-bearing operand in the argument list, which the
original receiver-only check could never see. The "assigned to a local first" case
(`reason_body = resolved.reason`) was already handled by the existing substring-name matching
(`"reason" in name.lower()`) and is now covered by a regression test
(`test_catches_a_reassigned_reason_local`) verifying the fix stays true after any future
refactor of this detector. A documented, honest limitation is stated in the function's own
docstring: this is name-based, not data-flow analysis, so a value split out of a reason string
into an unrelated-named local (e.g. a bare loop variable `part`) is not traced further past that
rename.

**Result: NOT the expected "0 new sites".** The widened detector found `hook.py:522`, inside
`_parse_compound_match_details()`, still live in the current working tree:

```
m = _COMPOUND_MATCH_PATTERN.match(reason)
```

This is exactly the code the coordinator's message described as "(since removed)" -- but
`grep -n "_parse_compound_match_details\|_COMPOUND_MATCH_PATTERN" toolguard/hook.py` on this
working tree right now shows the function still defined (`hook.py:476`), the module-level
pattern still defined (`hook.py:473`), and the function still actively called
(`hook.py:573: compound_details = _parse_compound_match_details(reason)`). `git status` shows
`toolguard/hook.py` as currently modified-but-uncommitted (159 insertions / 84 deletions against
HEAD), so this may be a working-tree/timing discrepancy with whatever removal the coordinator
had in mind, rather than a tool bug -- **per instruction, this is reported as found, not fixed**;
`toolguard/` production code was not touched. The only other R3 site is `resolve.py:588`
(`reason.startswith(_no_match_prefix)`), which matches the ticket-sanctioned "Command" -> "Path"
reword the coordinator said would remain. Both of the previously-found `resolve.py`
`reason_body`-based sites (line ~692/699 in the earlier report) and both `hook.py`
`reason.split` sites (461/978) are confirmed GONE from the current tree -- consistent with "R3's
conversion is complete" being true except for this one live exception.

### Correction from the previous addendum, applied

Removed the "previously undocumented" claim about the `parser.multiline <->
parser.command_extractor` cycle -- it's one of the ticket's two documented cycles; the tool
finding it is a correct confirmation. No code change was needed.

### Verification run (as requested)

```
$ uv run python tools/architecture_fitness.py --predicates
```
- Generated files excluded (1): `parser.bash_parser`.
- **R1: `__iter__` shims = 2** (`BashResolution`, `FileResolution`); out-of-scope excluded:
  `parser`, `parser.bash_parser`, `parser.command_extractor`, `parser.command_model`,
  `parser.multiline`.
- R3: 2 sites -- `hook.py:522` (new finding, see above) and `resolve.py:588` (sanctioned
  reword); `compound.py::fallback_kind_for_reason` still excluded as sanctioned.
- R2/R5/R6: unchanged from the previous report (R5 still shows both cycles; the R5
  broader-than-plan scope ambiguity flagged in the original report stands, unaddressed by this
  round -- it wasn't in scope for this fix).

```
$ uv run python tools/architecture_fitness.py --layers
```
Unchanged behaviour (3 direction violations, as before; generated file still classified into
its layer, as designed) -- exit 1.

```
$ uv run python tools/architecture_fitness.py --guard
```
PASS, 12/12 canaries matched -- exit 0, ~1.4s.

```
$ uv run python -m unittest discover -s test -t .
```
**2300 tests, OK** (was 2279 before this round; +21 new: 5 for generated-file detection itself,
2 for R1 out-of-scope exclusion + `r1_out_of_scope_modules`, 6 for the widened R3 detector, 4 for
generated-file exclusion spread across the other R-detector test classes, 1 for
`production_files`' new `excluded` parameter, 1 for `compute_metrics` excluding a generated file
end-to-end, 2 extending existing key-presence smoke assertions -- see below).

`uv run ruff format --check .` / `uv run ruff check .`: clean, whole repo (146 files). `uv run
python tools/check_doc_links.py`: clean. No new `async`/`threading`/local-import issues.
Dogfooded `--guard --since HEAD` against this round's own diff: PASS.

### Existing tests changed (as required, listed per instruction)

Two existing test methods were extended (assertions added, nothing removed or weakened) because
the change they cover directly requires it:
- `TestComputePredicates.test_assembles_all_predicate_keys` -- added
  `"generated_files_excluded"` to the expected-keys tuple and an assertion that R1's dict carries
  `"out_of_scope_excluded"`.
- `TestSmokeAgainstRealTree.test_compute_metrics_runs_on_real_repo` -- added
  `"generated_files_excluded"` to the expected-keys tuple and an assertion that the real
  `toolguard/parser/bash_parser.py` is named in it (a fact stable across refactor steps, unlike
  a predicate count, so it doesn't fight the file's own "don't pin to today's numbers"
  philosophy).

No other existing test was modified; all 108 pre-existing assertions in this file still pass
unchanged.
