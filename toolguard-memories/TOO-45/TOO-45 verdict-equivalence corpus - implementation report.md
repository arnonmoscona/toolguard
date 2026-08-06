---
title: TOO-45 verdict-equivalence corpus - implementation report
type: note
permalink: toolguard/too-45/too-45-verdict-equivalence-corpus-implementation-report
tags:
- task-memory
- TOO-45
---

## Summary

Built the TOO-45 verdict-equivalence corpus per spec: `tools/corpus_build.py` (dev-only,
stdlib-only, `--extract`/`--generate`/`--verify`), `test/verdict_corpus/` (14 fixture configs,
`cases.jsonl`, `goldens.jsonl`, `README.md`, shared `fixture_loader.py`), and
`test/unit/test_verdict_corpus.py` (the two-tier replay test). Full suite: 2189 tests, 8.5s, OK.
Ruff format/check clean. No existing file modified (verified via `git status`).

## Files

New:
- `tools/corpus_build.py`
- `test/verdict_corpus/__init__.py`
- `test/verdict_corpus/fixture_loader.py` (shared by both the dev tool and the test -- single
  choke point for fixture loading, ephemeral-path sanitization, golden-record building, and
  `compare_goldens`, so the two can never drift)
- `test/verdict_corpus/README.md`
- `test/verdict_corpus/cases.jsonl` (5,290 lines), `goldens.jsonl` (5,290 lines)
- `test/verdict_corpus/configs/`: 11 single-file fixtures (`empty` has NO file -- special-cased
  to genuinely no config) + 3 directory fixtures (`realistic`, `parse_failure`,
  `hierarchy_conflict`), 20 TOML files total
- `test/unit/test_verdict_corpus.py`

This is a large file count by design -- the ticket itself specifies this exact layout. Flagging
per the scope-inflation guard rather than treating it as organic creep: it is spec-mandated, not
something I chose to expand.

## The three parser counts (important finding)

Measured live: 7,010 Discovery / ~10,000+ Command / ~17,000+ total -- growing every run.
**Root-caused, not a parser bug**: `logs/toolguard-2026-08-04.md` is actively appended to DURING
this very session (every Bash command I ran added a new Command entry). Proof: excluding just
that one file, the historical total is exactly 30 short of both the spec's `total` (16,906) and
`command` (9,896) targets, while `discovery_entries` matches 7,010 EXACTLY (discovery is
session-scoped, logged far less often, so it wasn't perturbed by ongoing single-session Command
growth). This is only possible if the drift is 100% additional Command entries from continued
usage, which is exactly what "the log keeps growing" predicts. `corpus_build.py` reports this
comparison on every `--extract` run (`check_log_counts`) rather than hard-failing, since an exact
match is now a moving target by construction (also caught and fixed along the way: an
initially-loose `toolguard-*.md` glob also matched `toolguard-warning-*.md`/`toolguard-error-*.md`,
which use an unrelated entry format -- fixed with `_DECISION_LOG_RE`, though empirically this
turned out NOT to be what caused the numeric drift, since those files' headers don't collide with
the entry-header regex at all).

Also found and fixed: the spec's literal "accumulate until backticks balance" (parity) algorithm
is WRONG on real data -- a genuine single-line entry
(`logs/toolguard-2026-07-24.md:157`, `grep -n "^#### \`"`) contains one unpaired literal backtick,
making total parity odd on a non-continued line. Replaced with: keep consuming lines until the
current line ENDS with a backtick (the log writer never escapes backticks and always closes the
field as the last character of its line, single- or multi-line) -- verified against the whole
corpus (10,000+ Command entries parsed with zero exceptions).

## Design decisions worth flagging

1. **Ephemeral-path sanitization is a second, independent sanitization pass** on top of the
   spec's machine-path one: every fixture is materialized in a fresh `toolguard.testing.sandbox`
   temp dir, so `reason` (embeds a bracketed provenance suffix) and `provenance.path` would
   otherwise contain a different random path every run. Replaced with `<FIXTURE_HOME>` /
   `<FIXTURE_PROJECT>` placeholders before serialization. **Verified byte-identical across two
   consecutive `--generate` runs on this machine** (diffed, zero differences).
2. **Test uses `toolguard.testing.sandbox.experiment()` (via `fixture_loader.py`), not
   `ConfigIsolationMixin`**, despite the spec's suggestion to reuse the mixin. Deliberate: the
   whole design point of `fixture_loader.py` is ONE shared path between the dev tool and the
   test so `compare_goldens` is comparing apples to apples; using two different
   isolation/loading mechanisms in the two callers would reintroduce exactly the drift risk the
   design is meant to eliminate. `sandbox.experiment()` isolates the same anchors
   `ConfigIsolationMixin` does (`Path.home()`, `find_project_root`, cleared env), plus a write
   tripwire it doesn't have.
3. **`compare_goldens` keys records by `(fixture, tool, target)`**, not by line position, so
   `cases.jsonl`/`goldens.jsonl` can be edited/reordered independently and the test still reports
   precisely what changed. Duplicate keys raise loudly (`ValueError`) rather than silently
   overwriting.
4. **A missing/stale golden is its own hard-failure category**, separate from a verdict change --
   catches "someone edited cases.jsonl without regenerating" as a data-integrity bug, not a false
   "verdict changed."
5. Real-traffic realistic fixture config content (project + user `toolguard_hook.toml`,
   `gh.rules.toml`, `git.rules.toml`) was captured ONCE by hand (sanitized) into
   `configs/realistic/`; `corpus_build.py` never reads live machine config, only these committed
   snapshots -- required for reproducibility on any checkout.

## Verification performed

- Full suite: `uv run python -m unittest discover -s test -t .` -- 2189 tests, 8.466s, OK
  (baseline before changes: 2186 tests, 1.4s, OK).
- `tools/corpus_build.py --generate` run twice, diffed: **byte-identical**.
- `tools/corpus_build.py --verify`: OK, ~7.4s.
- `test.unit.test_verdict_corpus` alone: 3 tests, ~7.3s (well under the ~20s target).
- **Mutation smoke test** (not the acceptance-gate mutation test Arnon runs separately, just a
  sanity check that the harness isn't a decoration): temporarily removed the `rm -rf /`
  hard-deny pattern from `configs/hard_deny.toml`, ran `--verify` and the unittest -- both
  correctly reported 2 verdict mismatches (`allow`/`ask` instead of `deny`) and the unittest
  failed with a clear message. Reverted; diffed clean; re-verified OK.
- `uv run ruff format .` / `uv run ruff check .` on all new files: clean.
- `uv run python tools/check_doc_links.py`: clean (README's links resolve).
- Scanned `cases.jsonl`/`goldens.jsonl` for secret-shaped strings (AWS/Slack/GitHub/OpenAI
  token shapes, PEM blocks, api-key/password/bearer patterns): clean. One benign hit
  (`grep -c ANTHROPIC_API_KEY` -- a variable NAME being grepped for, not a credential value).
- `git status`: only the new files listed above; no existing file touched; nothing under
  `logs/` written.
- No async/threading/local-imports found in any new file.

## Anything not done / deviations

- Did not attempt the acceptance-gate mutation test (seed many deliberate engine bugs and
  confirm the corpus catches every one) -- spec says Arnon runs that separately. Did one manual
  smoke-test mutation myself for basic confidence (see above).
- Per-fixture case counts: `empty`=15, `enrichment`=16, four `fallback_*`=15 each,
  three `undecidable_*`=15 each, `hard_deny`=17, `hierarchy_conflict`=15, `parse_failure`=15,
  `pattern_forms`=17, `realistic`=5,090. Total 5,290 cases.

## Time/cost (approximate)

- Phase 1 (planning/investigation, incl. reading config.py/resolve.py/sandbox.py/rule_entry.py,
  log-format survey): ~50 min, ~$3-4 est. (heavy tool-call volume, Sonnet 5 pricing).
- Phase 2 (implementation: fixture_loader.py, corpus_build.py incl. the two parser bugs found
  and fixed, 14 fixture TOMLs, test file, README): ~90 min, ~$6-8 est.
- Phase 3 (self-review: full suite runs, byte-identical check, mutation smoke test, secret scan,
  doc-link check): ~20 min, ~$1-2 est.
- Total elapsed: ~2h40m. Total estimated cost: ~$10-14.


## Follow-up: end-to-end corpus (closing the CP1 mutation-battery gap)

After the initial delivery, the coordinator ran the CP1 mutation battery (5 seeded changes)
against the in-process corpus: 4/5 caught (strictest-wins consolidation, the undecidable floor
collapsed at both sites, the parse-failure ASK floor disabled, enrichment dropped inside the
engine). One confirmed blind spot: disabling the `additionalContext` write at the hook OUTPUT
seam (`toolguard/hook.py::create_hook_output`, `if additional_context:` -> `if False:`) was
invisible to the in-process corpus, because `decide()` never reaches `create_hook_output` --
exactly the seam TOO-45's R1 step targets, and the same shape as a defect that shipped once
before (`--eval`/sandbox under-reporting a live output field).

### What was added

- **`test/verdict_corpus/e2e_cases.jsonl` / `e2e_goldens.jsonl`** (30 cases each) -- a small,
  hand-picked subset replayed through the REAL `toolguard` hook binary in a subprocess, via
  `toolguard.testing.sandbox.Sandbox.run_hook` (not `create_hook_output` called directly with
  fields off a `Decision` -- that would re-implement hook.py's own derivation inside the test and
  let a mutation in the derivation itself slip through, per the coordinator's explicit design
  constraint). Golds the FULL hook JSON response (`hookSpecificOutput.permissionDecision` /
  `permissionDecisionReason` / `additionalContext`), minus `run_hook`'s own `_stderr`/
  `_returncode` diagnostic keys.
- **`test/verdict_corpus/fixture_loader.py`** extended: `E2E_CASES_PATH`/`E2E_GOLDENS_PATH`,
  `_open_fixture_sandbox` (factored out of `load_fixture_configuration` so both it and the new
  `load_fixture_sandbox` share the identical write-then-isolate step), `load_fixture_sandbox`,
  `build_hook_payload` (dispatches `file_path` vs `command` via `toolguard.hook.FILE_PATH_TOOLS`,
  reused rather than redefined), `e2e_decision_to_golden`, `generate_e2e_goldens_in_memory`,
  `E2EHardMismatch`/`E2EComparisonResult`/`compare_e2e_goldens` -- a distinct two-tier split from
  the in-process one: HARD = `permissionDecision` value AND `additionalContext` key
  presence/absence; TRACKED = `permissionDecisionReason` text and `additionalContext` text (when
  present on both sides).
- **`tools/corpus_build.py`**: `E2E_CASES` (the 30 hand-picked triples, reusing existing fixtures
  -- no new configuration shapes), `build_e2e_cases`, all three CLI modes now drive both corpora,
  `_print_e2e_comparison`, per-corpus timing reported by `--generate`/`--verify`.
- **`test/unit/test_verdict_corpus.py`**: new `TestVerdictCorpusEndToEnd` class (deliberately
  separate from `TestVerdictCorpus`, own `setUpClass`, so either corpus runs and is diagnosed
  independently) with `test_no_stale_or_missing_e2e_goldens`, `test_no_hard_output_changed` (the
  hard invariant), `test_e2e_tracked_fields_unchanged_or_acknowledged`.

### Two real fixture bugs found and fixed while building this

1. **`hard_deny.toml` and `pattern_forms.toml` didn't declare `governed_tools`**, defaulting to
   `('Bash',)`. `decide()` (the in-process corpus's entry point) never consults `governed_tools`
   at all -- documented explicitly in its own docstring -- so this was invisible in the in-process
   corpus's Read/Write cases. But the real hook's `main()` DOES check it first and short-circuits
   ungoverned tools straight to `"allow"` / `"Not a governed tool"` before ever reaching
   `[hard_deny]` or the pattern rules. Both fixtures' end-to-end Read/Write cases were silently
   testing "is this tool governed" instead of what they were meant to (hard-deny / pattern-form
   matching for file paths). Fixed by adding `governed_tools = ["Bash", "Read", "Write", "Edit"]`
   to both -- a no-op for the in-process corpus's goldens (verified: re-running `--generate`
   changed nothing there), and the fix that made the end-to-end Read/Write cases meaningful.
2. **`hard_deny.toml`'s `Read(**/.env)` / `Read(**/.ssh/**)` patterns never matched any of this
   corpus's absolute-looking case targets** (e.g. `/home/tguser/.env`). A relative pattern (no
   leading `/` or `~`) is anchored to the fixture's own (ephemeral, per-run) sandbox project root
   via `Configuration._anchor_relative_path`; none of the portable, machine-independent absolute
   targets this corpus uses would ever fall under that sandbox-specific directory. Every such case
   -- in BOTH corpora, from the very first `--generate` run -- silently fell through to the
   `no_match_fallback` default (`ask`) instead of ever reaching `[hard_deny]` or the normal allow
   rule; this had been present since the initial delivery and was only caught while investigating
   the coordinator's e2e request. Fixed by switching those patterns (and the paired
   `[permissions] allow = ["Read(**)"]`) to the absolute `[glob]/**/...` form. Verified the fixed
   patterns now correctly hard-deny/allow as intended, in both corpora.

Also swapped one e2e case (`pattern_forms` file-tool slot) from an always-`ask` target to
`./docs/architecture.md`, which matches via the fixture's `[regex]` rule (regex patterns are
matched against the raw target text directly, unaffected by the anchoring rule above) -- giving
the end-to-end corpus a clean file-tool allow example alongside the existing ask (unmatched
`Write`) and deny (`hard_deny`'s now-fixed `Read('.env')`) cases.

### Verification performed (this follow-up)

- **Mutation check, exactly as requested**: applied `if additional_context:` -> `if False:` in
  `toolguard/hook.py::create_hook_output`. Ran `TestVerdictCorpusEndToEnd` --
  `test_no_hard_output_changed` FAILED with all 7 expected `additionalContext`-bearing cases
  reported as `additionalContext_presence: expected=True actual=False`
  (`enrichment` fixture's `ls -la`, `rm file.txt`, `sudo reboot`, `curl -X DELETE ...`,
  `ls -la && cat file.txt`, `cat a.txt && cat b.txt`, `pwd && ls -la`). Reverted the mutation;
  `git diff toolguard/hook.py` confirmed a byte-for-byte clean revert; full suite re-run green.
  **The gap the coordinator identified is closed.**
- Both corpora regenerated twice, diffed: **byte-identical** (in-process and end-to-end,
  independently).
- `tools/corpus_build.py --verify`: OK for both corpora.
- End-to-end golden scan: 30/30 cases meaningful -- 12 allow / 7 ask / 11 deny; enrichment present
  on 7 cases, absent on 2 (plain rule / unmatched fallback), including 3 multi-part accumulation
  cases; all 3 `undecidable_*` floors; the `parse_failure` ASK floor (allow-clamped-to-ask) and a
  `hard_deny` case showing deny is NOT clamped; 2 compound commands; 3 file-tool targets
  (allow/ask/deny).
- Full suite: 2192 tests (2189 + 3 new e2e test methods), **10.2-11.0s** (was 2189/8.5s before this
  follow-up; the whole module -- both classes -- runs in ~9.7-9.8s, of which the end-to-end class
  is ~1.5-2s for its 30 subprocess calls). Comfortably under the ~20s target.
- `uv run ruff format .` / `uv run ruff check .` on every touched file: clean.
- `uv run python tools/check_doc_links.py`: clean.
- `git status`: still only the three top-level new paths (`tools/corpus_build.py`,
  `test/verdict_corpus/`, `test/unit/test_verdict_corpus.py`); `toolguard/hook.py` confirmed
  unmodified in the final state.

### Design notes worth flagging

- `run_hook` is used rather than calling `create_hook_output` directly with fields taken off a
  `Decision`, per the coordinator's explicit constraint -- confirmed this matters in practice via
  the governed-tools discovery above: a `decide()`-only test would never have seen that gap either,
  since `decide()` and `create_hook_output` both sit downstream of the `governed_tools` check that
  only `hook.main()` performs.
- The two fixture bugs found here were latent in the ORIGINAL (pre-follow-up) in-process corpus
  too (the `.env`/`.ssh` anchoring one silently affected 5 in-process `hard_deny` Read goldens from
  the very first delivery) -- caught only because building the end-to-end corpus required
  actually reasoning through what each case was supposed to prove, rather than trusting that a
  generated golden matching *something* meant it was matching the *intended* thing.
