---
title: TOO-19 code review Majors M1-M3 - coder task recall
type: note
permalink: toolguard/too-19/too-19-code-review-majors-m1-m3-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task
Act on 3 Major findings from code review report `toolguard-memories/latest-code-review-report.md`
(2026-07-31), per Arnon's explicit per-finding direction. Repo: toolguard, branch too-19.

## M1 -- DOCUMENT ONLY
Add a new subsection to `docs/security.md` naming the `additionalContext` project-config
injection risk. No code/flag/config key. Must:
- Explain the channel (project-level `.claude/toolguard_hook.toml` discovered from project dir
  -> `additionalContext` free text injected into Claude's context).
- Verify + state proportionality: project-level `allow` CAN already override a `deny` from a
  less specific level under more-specific-wins (VERIFIED: config.py "specificity 0 = project
  (most specific)", normal resolution is more-specific-wins). `[hard_deny]` is POOLED across
  ALL levels and unoverridable (VERIFIED: config.py "hard_deny is COLLECTED FROM ... "), so a
  hard_deny survives a hostile project config; a plain `deny` does not. So a hostile project
  config already has a stronger lever (turn a deny into an allow) than context injection alone.
- Name the asymmetry: permission rules are visible to toolguard-audit/toolguard-maintain;
  additionalContext text is NOT surfaced by any audit tool (VERIFIED: grepped
  toolguard/tools/{security_audit,danger,clarity,redundancy,takeover_audit,config_access}.py
  for additional_context/additionalContext -- zero hits except an unrelated comment in
  config_access.py about comment-parsing quoting). So state the asymmetry is real as written
  in the finding.
- Note Claude Code's trust-on-first-open prompt as an existing control (not a guarantee).
- Single hyphens in headings. Add heading to docs/agent-map.md's security.md TOC list.

## M2 -- REAL BUG, fix at injection boundary
Budget (500 words, `compound._MAX_CONTEXT_WORDS`) currently applied only inside
`compound._accumulate_contexts`, called only from `_combine_strictest`'s all-allow branch.
Deny/ask Bash contexts (compound.py ~398/402), FileResolution (resolve.py ~531/536,
`resolve_file_path_permission_detailed`), and hard-deny Bash context (resolve.py ~618) are all
uncapped. A LONE over-budget entry (single paragraph alone > max_words) makes
`_accumulate_contexts` return `None` -- injects nothing, silently, no log trace.

**Boundary investigation (must verify, not assume):**
- hook.create_hook_output is called from hook.main() (bash + file paths) and
  hook._run_eval_mode() (--eval). BUT hook.main() calls `resolve_bash_permission_detailed` /
  `resolve_file_path_permission_detailed` DIRECTLY (resolve.py), NOT via decide().
  toolguard.tools.decision.decide() (used by --eval's `_resolve_event` AND by
  `testing/sandbox.py`'s `evaluate()`) ALSO calls the SAME two resolve.py functions.
  `testing/sandbox.py`'s CLI `main()` builds its OWN JSON payload straight from
  `decision.additional_context` -- it does NOT go through `create_hook_output` at all.
  CONCLUSION: `hook.create_hook_output` is NOT a boundary that covers sandbox. The TRUE single
  convergence point across main()/--eval/sandbox is inside `toolguard/resolve.py`:
  `resolve_bash_permission_detailed` and `resolve_file_path_permission_detailed` -- every path
  (main, decide(), sandbox) calls one of these two and only these two. Cap must be applied
  there, right before constructing the returned `BashResolution`/`FileResolution`.

**Design:**
- `compound._accumulate_contexts`: strip out budget enforcement entirely -- dedup + paragraph
  join only, no `max_words` param. Docstring updated.
- New public function `compound.cap_context_words(text, max_words=_MAX_CONTEXT_WORDS)` --
  applies the SAME greedy first-fit paragraph algorithm to a single already-final text (split
  on "\n\n"). If nothing fits whole (the lone-oversize case: first/only paragraph alone
  exceeds budget), truncate that first paragraph to `max_words` words at a word boundary and
  append a trailing marker paragraph, so an over-budget entry is NEVER silently dropped to
  None when the input was non-empty. Public (no underscore) since resolve.py, a different
  module, calls it -- API visibility rule: privatize by "should non-test code call it?".
- `resolve.py`: import `cap_context_words` from `toolguard.compound`; wrap the final
  `additional_context` value at all 3 return points (file-path hard-deny branch, file-path
  normal branch, bash single return) before constructing the dataclass.
- Because the log (`log_command`'s `additional_context` param -> `_preview_additional_context`)
  is fed straight from these same capped values, "the log must reflect what actually got
  injected" is automatically satisfied -- no separate signal needed.

**Tests required** (existing tests on `_accumulate_contexts(..., max_words=...)` must move/adapt
since the param is gone):
- test_compound.py: keep dedup/join tests on `_accumulate_contexts` (now unbounded); move the
  budget-specific tests (over-budget-dropped-whole, first-fit, exactly-at-budget,
  default-500-budget) to a new `TestCapContextWords` class testing `cap_context_words`
  directly, PLUS add a new lone-oversize test proving truncation-with-marker (not None).
- test_resolve.py: add lone-oversize test for a Bash allow rule (via
  `resolve_bash_permission_detailed`) and for a Read/Write/Edit rule (via
  `resolve_file_path_permission_detailed`), plus a case each proving deny and hard_deny
  contexts are now capped (previously uncapped).

**Docs to update for accuracy (doc-drift sweep):** `docs/configuration.md`'s
"additionalContext: injecting guidance..." section currently says the 500-word cap only
applies to the compound accumulation and that an over-budget paragraph is "dropped WHOLE" --
needs updating to say the cap applies uniformly to all governed tools and decisions, and that a
LONE over-budget entry is truncated with a marker rather than dropped.

## M3 -- REAL BUG + SIMPLIFY
`log_writer._last_discovery_levels_for_root`: delete the 1MB `_DISCOVERY_JSONL_MAX_READ_BYTES`
guard and its `None`-on-oversize path (self-accelerating noise bug: past the cap every
invocation appends). Replace JSONL with plain text, one line per entry, and read only a
BOUNDED TAIL (seek from end), scanning backwards for the most recent line matching this
project root -- never read the whole file.

**Format decision:** tab-separated 3 fields per line: `<iso-timestamp>\t<project_root>\t<levels
joined with \x1f (ASCII Unit Separator)>`. Tab and \x1f are both effectively impossible in a
real filesystem path or a "level: /path" description string, so splitting is unambiguous
without needing JSON escaping. Filename renamed `toolguard-discovery.jsonl` ->
`toolguard-discovery.log` (no longer JSON).

**Bounded tail:** pick a fixed tail size (e.g. last 64 KB) via `seek(0, SEEK_END)` then
`seek(max(0, size - TAIL_BYTES))`, read forward from there, split into lines, drop a possibly-
truncated first partial line, scan the REMAINING lines from the end for a match on
project_root. Falls back to "no prior record" if none found in that tail -- justified because
that costs one redundant log line, never a wrong verdict (same safety argument the ticket
gives for the corrupt-final-line tolerance already in the code).

**Files needing filename-string updates:** `test/unit/test_zz_real_log_dir_guard.py` (hardcoded
`"toolguard-discovery.jsonl"`), `test/unit/test_logging_streams.py`'s `TestDiscoveryDiagnostic`
class (`_jsonl_path` helper + all JSON-based assertions -- full rewrite to plain-text
assertions). `test/unit/_real_log_dir_guard.py` itself has no filename dependency (operates on
log_dir param generically) -- no change needed there.

**technical-notes.md** "Change-detecting discovery diagnostic (M2, TOO-19)" section describes
the JSONL design -- must update to describe plain-text + bounded-tail.

## Constraints
- unittest not pytest. BDD Given/When/Then docstrings. No function-level imports. Docstring on
  every function/class. `uv run python` always.
- Never edit outside repo. No git write ops. Never write to real `logs/` dir (guard is in place
  via test/unit/_real_log_dir_guard.py -- must not weaken it).
- Baseline: full suite 2012 tests OK before changes.

## Verification checklist (from task)
1. `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
   unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- must be OK.
2. `uv run ruff check .` and `uv run ruff format --check .` clean.
3. `uv run python tools/check_doc_links.py` exits 0.
4. Prove real repo logs/ untouched: count discovery entries in `logs/toolguard-<today>.md`
   before/after full run, report delta 0.
5. Mutation-check M3: construct a discovery log large enough that OLD code's 1MB cap would have
   tripped, confirm NEW code still finds the correct prior entry and does NOT append.
6. Demonstrate M2 end-to-end via `toolguard.testing.sandbox` with over-budget additionalContext
   on (a) Bash allow rule alone, (b) Read rule -- paste both outputs.

## Report location
basic-memory project `toolguard`, path `TOO-19/TOO-19 code review Majors M1-M3 - fix report.md`,
tags `task-memory` + `TOO-19`.
