# TOO-45 verdict-equivalence corpus

## What this is, and why it exists

This is the load-bearing safety guard for the TOO-45 permission-engine architecture
refactor. **There are two corpora, covering two different seams:**

- The **in-process corpus** (`cases.jsonl` / `goldens.jsonl`, ~5,000 cases) replays
  `(config, tool, target)` cases through `toolguard.tools.decision.decide` -- the
  single side-effect-free entry point that backs both the live hook and `--eval`.
- The **end-to-end corpus** (`e2e_cases.jsonl` / `e2e_goldens.jsonl`, ~30 cases)
  replays a small, deliberately chosen subset through the REAL `toolguard` hook
  binary, in a subprocess, via `toolguard.testing.sandbox.Sandbox.run_hook`.

The end-to-end corpus exists because `decide()` stops at the decision itself and
is blind to `toolguard.hook.create_hook_output` -- the seam that turns a decision
into the actual JSON Claude Code receives. That gap was not hypothetical: during
TOO-45's CP1 mutation battery, disabling the `additionalContext` write at that
exact seam (`if additional_context:` -> `if False:` in `create_hook_output`) was
caught by nothing in the in-process corpus, because `create_hook_output` is
downstream of everything `decide()` touches. The end-to-end corpus was added
specifically to close that hole, confirmed by seeding the same mutation and
verifying `TestVerdictCorpusEndToEnd.test_no_hard_output_changed` fails (see the
TOO-45 implementation report in basic-memory for the exact run).

Everything else in TOO-45 (the interface layering, the config load/query split,
the rest of the refactor steps) is only defensible because these corpora exist to
catch a verdict -- or an output field -- that quietly changed along the way.

**Goldens pin CURRENT behaviour, including any current bugs.** They are not a
specification of what toolguard *should* do -- they are a snapshot of what it
*does* do, right now, at the commit the corpus was generated from. That is
deliberate: verdict equivalence means *before vs after the refactor*, not
*matches some ideal*.

## The two-tier comparison -- read this before touching a failing test

`test/unit/test_verdict_corpus.py` treats two kinds of difference completely
differently, in BOTH corpora (the exact fields differ; the principle doesn't):

- **HARD invariant. ANY change is a test failure, full stop, and is NEVER "fixed"
  by regenerating a goldens file.** For the in-process corpus this is `verdict`
  AND the compound sub-command breakdown (`sub_matches`/`overrides` -- see
  "Sub-command breakdown" below). For the end-to-end corpus this is
  `permissionDecision`, the PRESENCE/ABSENCE of the `additionalContext` key in
  the hook's JSON output, and the PRESENCE/ABSENCE of a conflict-log entry
  (`conflict_logged`) -- whether each of those exists at all is hard; their
  TEXT (`additionalContext`, `conflict_message`) is tracked -- see below.
  **If `test_no_verdict_changed`, `test_no_sub_command_breakdown_changed`, or
  `test_no_hard_output_changed` fails, STOP and investigate a real behaviour
  change in the engine.** If you believe the change is a deliberate, reviewed
  bug fix (not a refactor artifact), see "Updating goldens after a deliberate
  fix" below -- that is the only legitimate path, and it goes through review,
  not through a test quietly turning green again.
- **TRACKED, not frozen.** For the in-process corpus: `reason`,
  `additional_context`, `provenance`, `matched_rule`. For the end-to-end corpus:
  `permissionDecisionReason`'s text, `additionalContext`'s text when present
  on both sides, and `conflict_message`'s text when both sides logged a
  conflict. A refactor step may legitimately reword a reason string, move
  code between modules (changing a provenance path's incidental detail), or
  restructure how context is composed, without changing what the hook actually
  decides or outputs. A single-tier golden would either block that legitimate
  work or hide a real regression inside a "just a reword" diff -- both are
  expensive here, so this is reported separately: it fails by default (so
  nothing is silently ignored), but has one explicit acknowledgement path:
  `TOOLGUARD_CORPUS_ACCEPT_PROSE=1` for a one-off run, or regenerating the
  goldens file after reviewing the diff once the change is confirmed
  intentional.

## Sub-command breakdown (`sub_matches`/`overrides`) -- what it guards, and what it doesn't

The in-process golden schema also pins `RuntimeVerdict.sub_matches` (one entry
per extracted Bash sub-command, in order -- `sub_command`/`decision`/
`matched_rule`/`provenance`, deliberately narrower than the full
`UnitVerdict`; see `fixture_loader.py::unit_verdict_to_dict`'s docstring) and
`RuntimeVerdict.overrides` (one entry per allow-over-deny override, in order
-- `identifier`/`winning_pattern`/`winning_provenance`/`overridden_pattern`/
`overridden_provenance`; see `override_to_dict`). Both keys are ALWAYS present
as a list, empty (never omitted) when a verdict genuinely has none -- every
file-path verdict for `sub_matches` (file paths are never compound), the
common case for `overrides` -- so a regression that drops a genuinely
non-empty breakdown down to `[]` is a visible list-shrank diff, not a key that
quietly stops appearing. Unlike `provenance`/`matched_rule` at the top level,
these are HARD, not TRACKED (see the two-tier comparison above): the entire
point of this extension is to catch STRUCTURAL loss -- a dropped, reordered,
or garbled entry -- and none of the four captured fields is prose a
legitimate refactor has a reason to reword.

**Why this exists**: this is precisely the structural data whose silent loss
was TOO-45's headline audit-trail defect -- `hook.py`'s audit-log writer used
to reconstruct which sub-commands of an allowed compound ran by regex-parsing
the combined `reason` string, silently dropping 813 of 975 compound-allow
corpus cases' audit entries (1,943 sub-commands with no log record at all).
`_log_allowed_command` now reads `verdict.sub_matches` structurally instead
(TOO-45 R1e), but nothing pinned that fix against a future regression
reintroducing the loss until this extension. Verified to actually catch a
regression: a controlled mutation dropping every second recorded
`UnitVerdict` inside `resolve.py::resolve_bash_permission_detailed`'s
`_resolve_one` made `tools/corpus_build.py --verify` fail with 992 named
sub-command-breakdown mismatches (each showing the exact dropped sub-command);
reverting the mutation restored a clean `--verify`. See the TOO-45
implementation report for the exact run.

**What this does NOT guard** (a real, residual gap -- deliberately not closed
by this extension): whether `hook.py::_log_allowed_command`'s own write loop
over `verdict.sub_matches` correctly emits ONE audit-log entry per unit
without skipping any. That is the literal seam the historical defect lived
in, one step downstream of what `decide()` returns. The in-process corpus
calls `decide()` directly and never reaches `_log_allowed_command` at all
(same reason the end-to-end corpus exists for `additionalContext` -- see
above), and the end-to-end corpus's golden captures only the hook's real JSON
*response*, which never carries `sub_matches`/`overrides` in any form -- the
only observable trace of what actually got written to the audit log is the
log file itself, which this corpus does not currently snapshot for the main
decision-log stream (only for the `conflict` stream, via
`conflict_logged`/`conflict_message`). Closing this residual gap would mean
extending the end-to-end corpus to snapshot `toolguard-YYYY-MM-DD.md`
before/after each `run_hook` call, parallel to the existing
`conflict`-stream mechanism -- deliberately out of scope here (see the TOO-45
implementation report for why: it is new instrumentation, not an additive
schema widening, and the launching task gave an explicit option to document
the gap instead of closing it).

## Layout

```
test/verdict_corpus/
  configs/
    <fixture_id>.toml          single project-level config (most fixtures)
    <fixture_id>/               multi-file fixtures (a second hierarchy level
      project/.claude/toolguard_hook.toml    and/or a rules-dir file):
      home/.claude/toolguard_hook.toml       realistic, parse_failure,
      home/.toolguard/rules/*.rules.toml     hierarchy_conflict
  cases.jsonl         one JSON object per line: {"fixture", "tool", "target"}
  goldens.jsonl       one JSON object per line: {"fixture", "tool", "target",
                      "verdict", "reason", "additional_context", "provenance",
                      "matched_rule", "sub_matches", "overrides"} -- the last
                      two are the TOO-45 sub-verdict extension (see
                      "Sub-command breakdown" below); each is a list, always
                      present, empty when there is nothing to record
  e2e_cases.jsonl     same shape as cases.jsonl -- a small, hand-picked subset
  e2e_goldens.jsonl   one JSON object per line: {"fixture", "tool", "target",
                      "response"}, where "response" is the full hook JSON output
                      (hookSpecificOutput.permissionDecision/
                      permissionDecisionReason/additionalContext), minus the two
                      run_hook-only diagnostic keys (_stderr, _returncode), PLUS
                      "conflict_logged"/"conflict_message" when (and only when)
                      this case caused a new conflict-log entry
  README.md       this file
```

The SAME `configs/` fixtures back both corpora -- the end-to-end corpus does not
define its own configuration shapes, it replays a subset of `(fixture, tool,
target)` triples through a different execution path.

`fixture == "empty"` has no `configs/empty.toml` file at all -- that fixture is
genuinely "no configuration exists", which a real absence represents more
honestly than an almost-empty placeholder file would (see
`test/verdict_corpus/fixture_loader.py::load_fixture_files`).

`test/verdict_corpus/fixture_loader.py` is shared code, used by BOTH
`tools/corpus_build.py` and `test/unit/test_verdict_corpus.py`, so the two can
never disagree about how a fixture becomes a `Configuration` (or a `Sandbox`, for
the end-to-end corpus) or how a `Decision` (or a real hook JSON response) becomes
a golden record.

## Fixtures

| fixture | pins |
|---|---|
| `realistic` | Sanitized snapshot of the live config stack (project + user `toolguard_hook.toml`, plus `~/.toolguard/rules/*.rules.toml`), captured once as static committed files. Cases: every distinct `(tool, target)` pair extracted from `logs/toolguard-*.md` real traffic. |
| `empty` | No configuration at all. |
| `fallback_ask` / `fallback_deny` / `fallback_allow_warning` / `fallback_allow_silent` | Each `no_match_fallback` value (the last one uses the `allow_with_no_warnings` alias spelling deliberately, to exercise alias resolution). All four share the same 15 hand-written cases, so replaying one case across all four fixtures shows how the SAME command's outcome changes per setting. |
| `undecidable_ask` / `undecidable_deny` / `undecidable_allow` | Each `undecidable_fallback` value, exercised with commands the parser genuinely cannot decompose (process substitution). |
| `hard_deny` | `[hard_deny]` entries for both Bash and file paths, including a `hard_deny.allow` carve-out (an exception to a hard-deny pattern, not a normal allow). |
| `parse_failure` | A valid project-level config paired with a deliberately malformed user-level TOML file, to exercise `permission_resolution.apply_parse_failure_floor` clamping a would-be allow down to `ask` -- while a `hard_deny` case shows `deny` is never weakened by the floor. |
| `hierarchy_conflict` | Project-allow vs user-deny AND the reverse, for two different patterns, PLUS a rules-dir file that agrees with the project level for both -- a genuine three-way conflict for more-specific-wins resolution. |
| `pattern_forms` | Native syntax, the explicit `[native]` spelling, `[regex]`, and `[glob]` prefixes, for both Bash and file-path tools. |
| `enrichment` | `additionalContext` on allow, ask, deny, and hard_deny entries (the `{ match = "...", additionalContext = "..." }` structured form), including the multi-part accumulation case for a compound command whose allowed sub-commands each carry their own context. |

Two fixtures (`hard_deny`, `pattern_forms`) declare `governed_tools` explicitly
(the default, when unset, is `('Bash',)`) so their `Read`/`Write` cases are
actually governed at the end-to-end layer -- `decide()` (the in-process corpus's
entry point) never consults `governed_tools` at all, so this only matters for
`e2e_cases.jsonl`. Their `[hard_deny]`/`[permissions]` `Read`/`Write` patterns
also use the absolute `[glob]/**/...` form rather than a bare relative one: a
relative pattern is anchored to the (ephemeral, per-run) sandbox project root,
which none of this corpus's portable, absolute-looking case targets would ever
fall under -- discovered by generating goldens with the relative form first and
finding every such case fell through to the `no_match_fallback` default instead
of ever reaching the pattern it was meant to exercise.

## End-to-end case selection

`E2E_CASES` in `tools/corpus_build.py` is hand-picked (not sampled) to span the
hook's OUTPUT surface, reusing existing fixtures rather than adding new
configuration shapes: allow / ask / deny, `additionalContext` present and
absent, multi-part `additionalContext` accumulation, the `parse_failure` ASK
floor, all three `undecidable_*` floors, `hard_deny` (including a file-tool
target), a compound command, and file-tool targets across allow/ask/deny.
Kept small (~30 cases) because subprocess startup dominates its cost -- adding
volume here buys little the in-process corpus doesn't already cover, at real
runtime cost.

## Real-traffic extraction: verified counts

`logs/toolguard-*.md` (excluding `toolguard-warning-*.md` / `toolguard-error-*.md`,
which use an unrelated entry format) is a live, append-only log. The TOO-45 spec
that commissioned this corpus verified an exact snapshot of 7,010 Discovery
entries (skipped -- no `Command` field), 9,896 Command entries, and 16,906 total,
at a specific point in time. `tools/corpus_build.py --extract` reports the SAME
three counts on every run and compares them to that snapshot, but logs/ keeps
growing (including from ordinary day-to-day toolguard usage, and from this
tool's own development), so a HIGHER total than the snapshot on a later run is
expected, not a bug. If `discovery_entries` specifically ever stops matching
7,010, that is the one signal worth treating as suspicious -- config discovery
is logged at most once per session, so it grows far more slowly than Command
entries; a discovery-count mismatch would point at a real parser bug rather than
ordinary log growth.

## Sanitization

Two independent sanitization passes exist, for two different problems:

1. **Machine-path sanitization** (`corpus_build.py`'s `sanitize_machine_paths`):
   applied to every extracted real-traffic command AND (once, by hand, when the
   `realistic` fixture's config files were captured) to that fixture's config
   text, consistently, so pattern matching still lines up on both sides. Rewrites
   the real repo root to `/home/tguser/projects/toolguard` and any other
   `/home/arnon` occurrence to `/home/tguser` (word-boundary safe -- it does NOT
   touch other, already-fake usernames like `/home/arnontoho` that appear in the
   logs from unrelated sandboxed experiments).
2. **Ephemeral sandbox-path sanitization** (`fixture_loader.py`'s
   `_sanitize_ephemeral`): every fixture is materialized in a fresh
   `toolguard.testing.sandbox` temporary directory before its `Configuration` is
   loaded, so `reason` strings and `provenance.path` would otherwise embed a
   different random path on every single run -- making even one machine's two
   consecutive regenerations fail to match. This replaces the sandbox's own
   `home`/`project` absolute paths with fixed placeholders (`<FIXTURE_HOME>` /
   `<FIXTURE_PROJECT>`) before a golden record is built. This is unrelated to (1)
   and applies to every fixture, not just `realistic`.

Both together mean `tools/corpus_build.py --generate` is required to be, and was
verified to be, byte-identical across two consecutive runs on the same machine.

## Commands

Every mode below drives BOTH corpora (see `tools/corpus_build.py`'s own module
docstring for the exact per-corpus behaviour of each mode).

```bash
# Rebuild cases.jsonl (from logs/ + synthetic fixtures) AND e2e_cases.jsonl
# (from the hand-picked E2E_CASES table).
uv run python tools/corpus_build.py --extract

# Regenerate goldens.jsonl (via decide()) AND e2e_goldens.jsonl (via the real
# hook subprocess, one per case).
uv run python tools/corpus_build.py --generate

# Regenerate BOTH corpora IN MEMORY and diff against their committed goldens.
# Writes nothing. Exits non-zero on any hard difference or data-integrity problem.
uv run python tools/corpus_build.py --verify

# Also fail --verify (exit 1) on tracked-field (reason/context/provenance,
# or the end-to-end corpus's equivalents) differences, not just hard ones.
uv run python tools/corpus_build.py --verify --strict-prose

# Run both replay-test classes as part of the normal suite.
uv run python -m unittest test.unit.test_verdict_corpus -v

# Run only the end-to-end class (useful when only it needs re-checking --
# it is far cheaper to iterate on than the full in-process corpus).
uv run python -m unittest test.unit.test_verdict_corpus.TestVerdictCorpusEndToEnd -v

# Acknowledge reviewed reason/context/provenance (or end-to-end equivalent)
# differences for one run, without regenerating any goldens file.
TOOLGUARD_CORPUS_ACCEPT_PROSE=1 uv run python -m unittest test.unit.test_verdict_corpus
```

## Updating goldens after a deliberate fix

If a step in the refactor is discovered to fix a genuine bug (not just move code
around), the resulting verdict change is expected and the goldens must be
updated deliberately:

1. Confirm with the architect judge / a human reviewer that the verdict (or
   end-to-end output) change is the intended, reviewed effect of a specific fix
   -- not a side effect of something else.
2. Run `uv run python tools/corpus_build.py --generate` to refresh both
   `goldens.jsonl` and `e2e_goldens.jsonl`.
3. Include the diff of whichever goldens file(s) changed in the same commit/PR
   as the fix, so the change is reviewed alongside its cause, not as an
   unexplained data file update.
4. Note the change (what changed, for which case, and why) in the TOO-45
   decision log.

Never take this path to make a RED `test_no_verdict_changed` or
`test_no_hard_output_changed` go green without having gone through steps 1-4
first. That defeats the entire purpose of this corpus.

## Adding cases

New in-process synthetic cases go in `tools/corpus_build.py`'s `SYNTHETIC_CASES`
table (and, if they need a new configuration shape, a new/updated file under
`configs/`), then `--extract` followed by `--generate`. Real-traffic cases are
never added by hand -- re-run `--extract` to pick up new log entries.

New end-to-end cases go in `tools/corpus_build.py`'s `E2E_CASES` list --
prefer reusing an existing fixture over adding a new configuration shape (see
"End-to-end case selection" above), and keep the total small; subprocess
startup, not case count, is the cost that matters here.
