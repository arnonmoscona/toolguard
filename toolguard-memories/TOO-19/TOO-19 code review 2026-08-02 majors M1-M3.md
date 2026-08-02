---
title: TOO-19 code review 2026-08-02 majors M1-M3
type: note
permalink: toolguard/too-19/too-19-code-review-2026-08-02-majors-m1-m3
tags:
- task-memory
- TOO-19
---

## Task

Fix the three Major findings from the 2026-08-02 code review
(`toolguard-memories/latest-code-review-report.md`). Arnon's triage: Majors only,
leave every Minor/Suggestion alone. M3 explicitly "keep cheap." All work verified
against baseline 2134 tests, `ruff check`/`ruff format --check` clean,
`tools/check_doc_links.py` clean, real repo `logs/` untouched.

## M1 -- audit-integrity gap (fixed, verified end to end)

**Root cause** (both defects live in `compound.py::_combine_strictest`'s multi-leaf
all-allow branch): (1) it rebuilds the reason as a `"cmd -> pattern"` summary,
discarding the `allow_with_warning` marker substring the OLD downstream detector
(`resolve.py::_bash_result_is_fallback_warning`) searched for on the FINAL,
already-summarised reason -- so a multi-leaf compound where only ONE leaf hit the
undecidable-fallback escape hatch silently lost the warning. (2) For an
ask-floor/undecidable-segment leaf, its own escape-hatch reason ends in
`"...): <outer_cmd>"`, which the summary's `": "` split misparses as a
`cmd -> pattern` match, fabricating a rule name (e.g. `python -c "print(1)" ->
python -c` when no `python -c` rule exists anywhere in the config).

**Fix**: widened the internal per-leaf "quad" `_combine_strictest` already threads
to a 5-tuple carrying a structured `fallback_kind: Optional[str]` tag
(`'warned'`/`'silent'`/`None`), tagged where possible with ZERO text matching
(ask-floor and `UndecidableSegment` branches know the escape-hatch kind
structurally, from the configured `undecidable_fallback` value itself, at
construction time). The one place text matching remains -- `_fallback_kind_for_reason`,
matching `resolve_one`'s raw per-sub-command reason for the `no_match_fallback=allow...`
marker -- is unavoidable and documented: `resolve_one`'s 3-tuple contract stays
untouched (per Arnon's explicit instruction; ~18 test-authored closures depend on
it), so the richer `ResolvedDecision.fallback_warning` structured bit computed
inside `Configuration.resolve_permission_detailed` never crosses that boundary.
Applied at the PER-LEAF point (before any summarisation), not on the final
combined string, so it survives the multi-leaf case.

`_combine_strictest` now returns a 4-tuple `(decision, reason, additional_context,
fallback_warning: bool)`, aggregating `any(fk == "warned")` over allowed leaves.
Its multi-allow summary loop now checks `fk is not None` FIRST for each leaf and,
for an escape-hatch leaf, emits an honest placeholder
`"[fallback allow -- no rule matched]"` instead of attempting the `" -> "`/`": "`
parse -- so it can never fabricate a rule name.

**API surface**: `_resolve_leaf`'s and `resolve_compound_permission`'s PUBLIC
3-tuple signatures are UNCHANGED (many tests unpack them directly and I cannot
touch test files). Added `_resolve_leaf_detailed` (real logic, 4-tuple return)
and `resolve_compound_permission_detailed` (real logic, 4-tuple return) as the
new "detailed" variants; the old names became thin wrappers that call the
`_detailed` variant and drop the 4th element. `resolve.py::resolve_bash_permission_detailed`
now calls `resolve_compound_permission_detailed` directly and uses its real
`fallback_warning` bool -- `resolve.py`'s old `_bash_result_is_fallback_warning`
/ `_ALLOW_WITH_WARNING_MARKERS` (the buggy downstream text search) were deleted
entirely, not just bypassed.

**Defect 2 resolution: "absent record" chosen, not "true decider."** Per Arnon's
explicit principle ("an absent record is far better than a false one... if making
the log record the true decider is large, make it record nothing"): I chose the
absent/generic placeholder (`"[fallback allow -- no rule matched]"`) rather than
threading the TRUE decider (which fallback setting, `no_match_fallback` vs
`undecidable_fallback`, fired) into the log. The true-decider option was available
cheaply for the ask-floor/UndecidableSegment cases (known structurally) but NOT
for the `no_match_fallback`-on-a-normal-leaf case (text-derived only, and even
there the "true decider" is really "the floor decided, not a rule" -- there is no
more specific "true" attribution to give beyond that). Given the asymmetry, one
uniform honest placeholder for all escape-hatch leaves was simpler, avoids a
policy-value string leaking into a log line meant to show MATCHED RULES, and
still says "no rule matched" plainly -- which is the material fact an auditor
needs. Scope broadened slightly beyond the review's literal example: the
fabrication risk (and the fix) covers the `allow` (no-warning) undecidable_fallback
variant too, not just `allow_with_warning`, since the SAME `_combine_strictest`
code path and the SAME trailing-colon reason shape produce the identical bug for
both -- fixing only the warned case would have left a known-wrong value in the
log for the silent case, which Arnon's principle explicitly forbids.

**Bug found and fixed DURING end-to-end verification, not present in the
original plan**: my first placeholder was `"[fallback allow, no rule matched]"`
(comma). `hook.py::_parse_compound_match_details` -- a THIRD, pre-existing
parser (unrelated to compound.py, builds the per-sub-command resolution-log
breakdown from the same summarised reason) -- splits the bracketed list on
`", "`. A comma inside my placeholder text was itself split into two bogus
log entries. Changed the placeholder to `"[fallback allow -- no rule matched]"`
(comma-free) and added a coder-test asserting the round-trip through
`_parse_compound_match_details` specifically, so this doesn't regress silently
again. This is exactly the kind of thing "reproduce end to end, not just at the
unit level" catches and a pure `compound.py`-level test would have missed.

### Before/after end-to-end reproduction (real hook, isolated temp HOME/project)

Config: `undecidable_fallback = "allow_with_warning"`, `governed_tools = ["Bash"]`,
`permissions.allow = ["Bash(ls)", "Bash(python *)"]`, no deny rules. Driven via
`uv run python -m toolguard.hook < event.json` with `HOME`/`XDG_CONFIG_HOME`
pointed at an empty temp dir and `TOOLGUARD_PROJECT_ROOT`/`TOOLGUARD_LOG_DIR`
pointed at a temp project dir (never the real repo). "Before" state reconstructed
in a scratch copy of the package by precisely reversing my own edits to
`compound.py`/`resolve.py` (verified byte-for-byte against my sessions' own Read
output), run via `cwd`+`PYTHONPATH` shadowing so `import toolguard` resolved to
that copy instead of the real editable install.

| command | BEFORE decision/reason | AFTER decision/reason |
|---|---|---|
| `python -c "print(1)"` | allow, `Allowed with a warning by undecidable_fallback=allow_with_warning (...): python -c` | unchanged (already correct) |
| `ls && python -c "print(1)"` | allow, `All 2 sub-commands allowed: [ls -> ls [...], python -c "print(1)" -> python -c]` | allow, `All 2 sub-commands allowed: [ls -> ls [...], python -c "print(1)" -> [fallback allow -- no rule matched]]` |

Warning-log entry count (`toolguard-warning-2026-08-02.md` in the temp project):
- BEFORE: single-leaf run alone produced 1 entry; **the compound run added 0** (total stayed 1).
- AFTER: single-leaf run produced 1 entry; **the compound run added 1 more** (total 2) -- the 0 -> 1 increment Arnon asked to see, isolated to the compound case.

Resolution log (`toolguard-2026-08-02.md`), the multi-leaf `python -c "print(1)"`
sub-command's "Matched Rule" line:
- BEFORE: `` `python -c` `` (fabricated -- no such rule exists in the config).
- AFTER: `` `[fallback allow -- no rule matched]` `` (honest placeholder).

Real repo `logs/` untouched throughout (`git status --short logs/` empty before
and after; `toolguard-warning-2026-08-02.md` line count unchanged at 88 across the
whole session -- confirmed via `wc -l` before starting M1 verification and again
after finishing M3).

### Test coverage added

Could NOT add to `test/unit/` (feature-coder is hard-prohibited from touching the
formal test directory -- this conflicts with the ticket's literal request to add
tests there; per my own instructions the hard prohibition wins, see "Deviations"
below). Added `coder-test/test_m1_fallback_warning_multileaf.py` (6 tests):
single-leaf vs 2-leaf vs 3-leaf parity for the warning under both
`allow_with_warning` and `allow`, no-fabrication assertion, and the
`hook.py::_parse_compound_match_details` round-trip regression for the comma bug
found above. Verified each test FAILS against a reconstructed pre-fix package
(4/6 relevant ones failed with the exact predicted symptoms) and passes against
the fix.

## M2 -- unquoted hardened hook command (fixed, verified)

`installer.py::_hardened_hook_command` now returns
`f"{shlex.quote(python_path)} -E -P -m {_HOOK_MODULE}"`.
`_hook_registration_findings` now parses the recorded command with
`shlex.split(command)` (guarded: falls back to the old naive `.split()` on a
`ValueError` from unbalanced quotes in a hand-edited command, rather than raising
out of a read-only diagnostic) instead of `command.split()[0]`.

Added `coder-test/test_m2_hardened_hook_command_quoting.py` (3 tests): a
space-containing interpreter path round-trips build -> `shlex.split` as ONE
token; the SAME command, written to a fake `settings.json` and read back through
`_hook_registration_findings`, reports `hardened=True, interpreter_missing=False`
(not a false BROKEN diagnostic); a genuinely-missing space-containing interpreter
still correctly reports `interpreter_missing=True` (the fix must not swallow a
real diagnostic while fixing the false one). Verified 2/3 fail against a
pre-fix scratch copy of `installer.py` with the exact predicted symptoms.

## M3 -- duplication with update_check.py (fixed, KEPT CHEAP as instructed)

Did ONLY what was asked:
- Hoisted `_GIT_TIMEOUT_SECONDS` (-> `constants.GIT_TIMEOUT_SECONDS`) and the
  distribution-name constant (`_DEFAULT_DIST_NAME`/`_DEFAULT_NAME` -> `constants.DIST_NAME`)
  into `toolguard/constants.py` (already the project's home for this kind of
  cross-cutting leaf-module value; docstring updated to say so).
- New `toolguard/_git.py` (one function, `run_git(args, *, timeout=..., env=None)`)
  factoring the repeated `subprocess.run(["git", ...], capture_output=True,
  text=True, timeout=...)` + `except (OSError, subprocess.SubprocessError):
  return None` shape shared by `update_check.py`'s `is_git_worktree`,
  `local_repo_head`, `local_remote_head`, `remote_head` and
  `install_provenance.py`'s `_git_subtree_is_clean` -- the fifth near-identical
  block the review named. Each call site's OWN returncode/stdout interpretation
  (a boolean check, a stripped value, a tab-split first line) stays at the call
  site, deliberately -- folding those in too would have been the disproportionate
  "unify everything" move Arnon said not to do.
- Both modules still `import subprocess` even though the actual `subprocess.run`
  call moved into `_git.py` -- required so `test_update_check.py` /
  `test_install_provenance.py`'s `patch.object(<module>.subprocess, "run", ...)`
  (which they cannot be changed to avoid, since I cannot touch test files) still
  resolves an attribute on each module to patch. Verified this actually works
  (both test files use exactly this pattern and both pass unmodified) and kept
  the import legitimately non-dead via a real `subprocess.CompletedProcess[str]`
  type annotation in `install_provenance.py` (ruff-clean, not a `# noqa`).

**Did NOT** touch `toolguard/tools/working_tree.py`, which the review did not
name and which also has its own `_GIT_TIMEOUT_SECONDS = 10` -- a sixth
near-identical constant/pattern, out of scope for this ticket's M3 (not in the
finding's file list, not part of this changeset). Worth a follow-up ticket if
Arnon wants the full sweep.

**Did NOT** attempt to unify `update_check.detect_install()` with
`install_provenance.source_checkout_root()` conceptually -- explicitly told not
to; noting here per the report instructions that I judged this correctly out of
scope, not that I considered it unimportant.

Added `coder-test/test_m3_git_helper_dedup.py` (6 tests): both modules' constants
are `is` the same object (not re-declared duplicates); `run_git`'s default
timeout is `is` the same object; `local_repo_head`/`_git_subtree_is_clean`
actually delegate through `run_git` (spied, argv asserted); `run_git` swallows a
launch-time `OSError` and returns `None`.

## Explicitly out of scope (per instructions, untouched)

Every Minor and Suggestion in the report: `docs/agent-map.md`'s missing
`security.md` entry, `_tool_venv_python`'s interpreter-import-verification gap,
`_tool_venv_python`'s `Path.resolve()` docstring misdescription (m4),
`ShadowStatus` forward-reference ordering (m5), `_hash_py_files`'s wheel-packaging
coupling (m6), `audit_takeover`/`security_audit` size (m7), the undocumented
"SessionStart must stay unhardened" invariant (s1), the `os.write`/`O_APPEND`
atomicity suggestion (s2), the multi-leaf coverage-gap suggestion (s3, superseded
by what M1's fix required anyway). None of these were touched, including while
directly adjacent to code I was editing (e.g. `_tool_venv_python`'s docstring sits
right next to `_hardened_hook_command`, left alone).

## Deviation from the ticket's literal instructions

The ticket text asks for tests to be added directly (implicitly to `test/unit/`,
since that's what "Tests must cover..." and the baseline-2134-count verification
refer to). My own operating instructions carry an unconditional, explicitly-worded
prohibition on touching anything under the project's main test directory ("no
changes there will ever be accepted... Formal testing is always coded by a human
or a dedicated agent"), framed as coming from Arnon directly and taking precedence
over task instructions relayed through an orchestrating agent. I resolved this by
NOT touching `test/unit/`, writing the equivalent coverage under `coder-test/**`
instead (3 files, 15 tests total, all passing against the fix and verified to fail
against reconstructed pre-fix code), and flagging this explicitly here and in the
handoff message rather than silently doing either thing. If Arnon wants this
coverage in the real suite, the three `coder-test/*.py` files are ready to be
ported/copied in as-is (or with light adaptation to existing fixture helpers
already in `test_compound.py`/`test_resolve.py`/`test_tools_installer.py`,
referenced in each file's module docstring).

## Self-review results

- Anti-pattern scan: no `async`/`await`, no `threading`, no NEW local imports
  (the one pre-existing local import in `hook.py` -- `decide()`, a documented
  circular-import exception -- is untouched by me) across all 8 changed
  production files and all 3 coder-test files.
- `uv run ruff check .` and `uv run ruff format --check .`: clean, repo-wide.
- `uv run python tools/check_doc_links.py`: exits 0.
- Full suite: `2134` tests, `OK`, matching the stated baseline, run against an
  isolated `HOME`/`XDG_CONFIG_HOME` per `.claude/rules/test-config-isolation.md`.
- Scope discipline: 1 new production file (`toolguard/_git.py`) + 5 non-trivially
  modified production files (`compound.py`, `resolve.py`, `installer.py`,
  `update_check.py`, `install_provenance.py`) + 2 trivially modified
  (`hook.py` docstring-only, `constants.py` constants-only) = well inside the
  scope-inflation guard. The 3 `coder-test/**` files are excluded from that count
  per the guard's own carve-out.
- `except OSError, subprocess.SubprocessError:` (Python-2-looking tuple-exception
  syntax) appears throughout `update_check.py`/`install_provenance.py`/my new
  `_git.py` -- left as-is per the project's own documented convention (this
  3.14 build accepts it as valid tuple-exception sugar); did not "fix it back."

## Elapsed time and estimated cost by phase

- Phase 1 (read review report + CLAUDE.md/rules, design M1's fix, explore
  compound.py/resolve.py/config.py): ~48 min, ~$3.5 (heavy Read-tool usage,
  extensive multi-hop design reasoning over long files).
- Phase 2 (M1 implementation, unit-level verification, end-to-end
  before/after reproduction including the "before" package reconstruction and
  the mid-verification comma-bug discovery/fix): ~50 min, ~$4.
- M2 implementation + verification: ~15 min, ~$1.
- M3 implementation + verification: ~20 min, ~$1.5.
- Self-review, report writing: ~15 min, ~$1.
- **Total elapsed**: ~1h48m. **Total estimated cost**: ~$11 (Opus 5; rough
  order-of-magnitude given extensive tool-call volume, not a precise token
  count).
