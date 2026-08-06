---
title: TOO-45 verdict-equivalence corpus - coder task recall
type: note
permalink: toolguard/too-45/too-45-verdict-equivalence-corpus-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task

Build the verdict-equivalence corpus (TOO-45 P1): safety guard for the upcoming architecture
refactor. Full spec given verbatim in the launching prompt (branch `too-45`). Key points:

- `tools/corpus_build.py` (repo-root, dev-only, stdlib only): `--extract` / `--generate` /
  `--verify` modes.
- `test/verdict_corpus/`: `configs/<id>.toml` (+ subdirs where needed), `cases.jsonl`,
  `goldens.jsonl`, `README.md`.
- `test/unit/test_verdict_corpus.py`: replay test, two-tier (`verdict` hard-fails;
  `reason`/`additional_context`/`provenance` tracked, env-var-acknowledgeable).
- Entry point: `toolguard.tools.decision.decide(config, tool, target, extended_syntax=True)`.
- Load each fixture's `Configuration` ONCE, reuse across its cases (no `Sandbox.evaluate` per
  case -- that reloads).
- Real-traffic source: `logs/toolguard-*.md`, READ ONLY. Parser must reproduce exactly:
  7,010 Discovery entries (skip), 9,896 Command entries, 16,906 total.
- Sanitize `/home/arnon` -> `/home/tguser` and the real project root -> `/home/tguser/projects/toolguard`,
  consistently in both extracted commands and the `realistic` fixture's config content.
- 9 synthetic fixtures per the table in the prompt (fallback x4, undecidable x3, hard_deny,
  parse_failure, hierarchy_conflict, pattern_forms, enrichment) + `realistic` + `empty`.
- Target runtime < ~20s. `unittest`, not pytest. No new deps. `uv run ruff format .` /
  `check .` clean at the end. May only ADD test files, never modify existing ones.

## Investigation findings (before coding)

- `toolguard.tools.decision.decide` is pure delegation to `toolguard.resolve`; confirmed
  side-effect-free, matches hook exactly.
- `toolguard.testing.sandbox` (`experiment()` / `Sandbox`) already provides the 4-anchor
  isolation (`Path.home()`, `find_project_root`, env clear+rebuild, write tripwire). Decided to
  reuse it directly from `tools/corpus_build.py` for isolation (permitted per spec: "the sandbox
  module or direct environment/home redirection"). For the test, use `ConfigIsolationMixin`
  (project convention) -- but that mixin only isolates `toolguard.config` discovery + log dir,
  NOT the write tripwire; fine since the test never writes fixture files at runtime other than
  what the mixin already creates.
- `Configuration.project_root` is a LAZY property (`find_project_root(self.start_dir)` called at
  ACCESS time, not just at load time) -- but confirmed `resolve.py`'s bash/file-path resolvers
  never touch `config.project_root` at decide-time (only `hook.py`'s logging/migration paths do).
  So `decide()` does not need the isolation context to remain open after `load_configuration()`
  returns, in principle -- but I'm keeping the sandbox context open for the whole per-fixture
  case loop anyway, since it's cheap (just patches) and removes any doubt.
- Sandbox uses `tempfile.TemporaryDirectory()` -- RANDOM path per run. This would break
  "goldens byte-identical across two regenerations" via `Provenance.path` (an absolute Path) and
  via `reason` strings (which embed `Provenance.describe_brief()` as a bracketed suffix).
  DECISION: post-hoc sanitize `sandbox.home` / `sandbox.project` absolute-path prefixes out of
  both `reason` and serialized `provenance.path`, replacing with fixed placeholder tokens
  (`<FIXTURE_HOME>` / `<FIXTURE_PROJECT>`), applied identically by `corpus_build.py --generate`
  and by the test. This is on top of (not instead of) the machine-path sanitization required by
  the spec (which applies to the *committed* fixture config text and extracted commands, a
  different concern from the *ephemeral* sandbox path).
- Machine-path sanitization: `real_root` computed at runtime as the actual repo root
  (`Path(__file__).resolve().parents[1]` from `tools/corpus_build.py`); replace that literal
  prefix with `/home/tguser/projects/toolguard` FIRST, then regex `\b` on `/home/arnon` (word
  boundary after, so `/home/arnontoho` and `/home/arno` -- both real strings found in the logs,
  belonging to OTHER sandboxed/fake users -- are correctly left untouched). Verified via grep
  survey of all `logs/*.md` that no other real-machine absolute path spelling of the project
  root exists (only `/home/arnon/projects/toolguard`, tilde form `~/projects/toolguard`, and an
  unrelated dot_files path that happens to end in `.../projects/toolguard` -- NOT the toolguard
  repo, must NOT be rewritten).
- Config TOML schema confirmed from `.claude/toolguard_hook.toml` / `~/.claude/toolguard_hook.toml`
  / `~/.toolguard/rules/*.rules.toml`: `[permissions] allow=[...]/ask=[...]/deny=[...]`
  (each element a plain pattern string, or a structured
  `{ match = "...", additionalContext = "..." }` inline table -- MUST be on one physical TOML
  line, `toml_scan.py` specifically detects the multi-line mistake); `[hard_deny] deny=[...]`;
  top-level `no_match_fallback` / `undecidable_fallback` keys (canonical values:
  `ask`/`deny`/`allow_with_warning`/`allow`; `allow_with_no_warnings` is a permanent alias for
  `allow`; legacy `warn_deny` aliases to `allow_with_warning` for `no_match_fallback` only, not
  `undecidable_fallback`). Extended pattern prefixes `[regex]`/`[glob]`/`[native]` inside
  `Bash(...)`/`Read(...)`/etc.
- `parse_failure` fixture design: `Configuration.apply_parse_failure_floor` clamps any non-deny
  decision to `ask` (with a distinct reason via `_parse_failure_reason()`) whenever
  `Configuration.parse_failures` is non-empty, REGARDLESS of which layer failed to parse. Built
  as a two-file fixture: project-level config has a real ALLOW rule, user-level config is
  deliberately malformed TOML -- demonstrates the floor overriding what would otherwise be an
  allow, and includes a hard-deny case to show `deny` is NOT clamped.
- `realistic` fixture: sanitized snapshot of CURRENT live config stack, captured once as static
  committed files (project `.claude/toolguard_hook.toml` [107 lines], user
  `~/.claude/toolguard_hook.toml` [61 lines], `~/.toolguard/rules/gh.rules.toml` [~10KB],
  `~/.toolguard/rules/git.rules.toml` [~32KB, contains the TEMPORARY too-45 git-relaxation
  fences -- snapshotted as-is per "goldens pin current behaviour including current bugs/state"]).
  NOT re-read live at build time (would break reproducibility on another machine/checkout) --
  `--extract`/`--generate` only ever read the committed `configs/` files.

## Plan (approved via auto-mode; no blocking ambiguity found)

1. `test/verdict_corpus/__init__.py` (empty, makes it a package).
2. `test/verdict_corpus/fixture_loader.py`: shared code (fixture ids, config-file layout
   convention, `load_fixture` context manager wrapping `toolguard.testing.sandbox.experiment`,
   ephemeral-path sanitizer, golden-record builder, JSONL read/write helpers). Imported by both
   `tools/corpus_build.py` and `test/unit/test_verdict_corpus.py` to avoid drift.
3. `test/verdict_corpus/configs/`: one file or subdir per fixture id (11 fixtures total:
   `realistic`, `empty`, `fallback_ask`, `fallback_deny`, `fallback_allow_warning`,
   `fallback_allow_silent`, `undecidable_ask`, `undecidable_deny`, `undecidable_allow`,
   `hard_deny`, `parse_failure`, `hierarchy_conflict`, `pattern_forms`, `enrichment` -- that's
   14, correcting the count above).
4. `tools/corpus_build.py`: log parser (with the 3 verified counts as an assertion/report),
   sanitizer, synthetic case tables (as literal Python data), `--extract`/`--generate`/`--verify`.
5. `test/unit/test_verdict_corpus.py`: loads `cases.jsonl` + `goldens.jsonl`, replays via
   `fixture_loader`, hard-fails on verdict diffs, soft-fails (with `TOOLGUARD_CORPUS_ACCEPT_PROSE=1`
   escape hatch) on reason/context/provenance diffs.
6. `test/verdict_corpus/README.md`.

## Status

Plan complete, starting implementation.
