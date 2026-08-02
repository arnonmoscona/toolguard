---
title: latest-code-review-report
type: note
permalink: latest-code-review-report
tags:
- code-review
- TOO-19
---

# Code Review Report -- 2026-08-02

**Scope:** `changed` (`git diff HEAD` + untracked new files), ticket TOO-19 -- the
`allow` / `allow_with_no_warnings` fallback values, the shadow/stale-install detection
(`install_provenance.py`, `tools/environment_audit.py`, `session_start.py`), the hardened
PreToolUse hook registration, and the `hook.py` / `log_writer.py` decomposition.
**Reviewer:** code-reviewer subagent
**Elapsed:** ~57 minutes | **Files reviewed:** 12 source + 11 test + 13 docs/skills (36)
**Suite:** 2134 tests, all green. `uv run ruff check .` clean.

---

## Summary

This is high-quality, unusually well-documented work. The `allow`/`allow_with_no_warnings`
addition is threaded correctly through every layer, the marker-safety design (new reason
texts deliberately worded so they cannot contain the old `allow_with_warning` marker) is
sound and regression-tested, and moving the text-based detector out of `hook.py` into
`resolve.py` -- replacing it with a structured `fallback_warning` boolean on the file-path
path -- is exactly the right direction. The shadow-detection feature is honest about its own
limits, the "never nag on uncertainty" rule is implemented consistently, and the `hook.py`
`main()` decomposition is behaviour-preserving on close reading.

Two things need attention before push. First, an audit-integrity gap that this change set
makes newly load-bearing: for a **multi-leaf all-allow compound**, the `allow_with_warning`
marker is destroyed by `_combine_strictest`'s reason summarisation, so the documented promise
("allow the command and log a warning") silently fails, and the log actively **misattributes**
the allow to a pattern that never matched. Second, `docs/agent-map.md` is missing the brand-new
`security.md` section added in this very change set -- the exact drift CLAUDE.md warns about.

---

## Critical

None. No security vulnerability, injection path, or credential handling issue found. The git
subprocess uses a list argv with no shell, all new inputs are read-only, and the new
fallback values fail safe (they cannot weaken an explicit deny/ask -- verified against
`_apply_undecidable_floor`'s table and its tests).

---

## Major

### M1. `allow_with_warning` silently loses its warning on multi-leaf all-allow compounds

**Files:** `/home/arnon/projects/toolguard/toolguard/compound.py` (`_combine_strictest`,
lines 512-542) and `/home/arnon/projects/toolguard/toolguard/resolve.py`
(`_bash_result_is_fallback_warning`, line 626).

Empirically confirmed with `check_compound_permission` + `_bash_result_is_fallback_warning`:

| command | final reason | warning logged? |
|---|---|---|
| `python -c "print(1)"` | `Allowed with a warning by undecidable_fallback=allow_with_warning (...): python -c` | **True** |
| `ls && python -c "print(1)"` | `All 2 sub-commands allowed: [ls -> ls, python -c "print(1)" -> python -c]` | **False** |

Two distinct problems, both in the second row:

1. **The WARNING stream never fires.** `_combine_strictest`'s multi-allow branch rebuilds the
   reason as a `cmd -> pattern` summary via `r.split(": ", 1)[1]`, which discards the marker
   substring. `_bash_result_is_fallback_warning` then returns `False`.
   `docs/configuration.md` promises `allow_with_warning` will "allow the command and log a
   warning"; for any compound with two or more allowed leaves it does not. The same applies to
   `no_match_fallback=allow_with_warning` reasons reaching the same branch.
2. **The audit trail actively misreports.** The right-hand side of `python -c "print(1)" ->
   python -c` is the *truncated display command*, not a pattern. A reader of
   `logs/toolguard-*.md` sees what looks like a rule match where in fact the undecidable
   escape hatch fired and **no rule was ever evaluated against the payload**. For a security
   tool this is worse than the missing warning.

This is pre-existing (the old hook-level detector ran on the same combined string), but it is
in scope: this change set is precisely about who is responsible for that promise, and it moved
and re-documented the detector as sound. Existing coverage misses it because
`test_bash_undecidable_allow_with_warning_reaches_warning_log_stream`
(`/home/arnon/projects/toolguard/test/unit/test_hook.py:1538`) uses a **single-leaf** command.

**Recommended fix:** stop deriving `fallback_warning` from text on the Bash path. The plan
memo's own reason for not doing this ("`resolve_one` is a 3-tuple relied on by many fixtures")
does not apply here -- the flag belongs on the *quad* `_combine_strictest` already carries
internally, not on `resolve_one`. Concretely: have `_resolve_leaf` and the undecidable-segment
branch of `resolve_compound_permission` tag their results, propagate `any(...)` across the
allowed leaves in `_combine_strictest`, and return it alongside `additional_context`.
Separately, the multi-allow summary should not run the `": "` split on an escape-hatch reason
at all -- either pass those through verbatim or label them (`<cmd> -> [undecidable escape
hatch]`). Add a regression test with a two-leaf compound for both fallback settings.

### M2. Hardened hook command is written unquoted -- a path with a space fails open

**File:** `/home/arnon/projects/toolguard/toolguard/tools/installer.py`,
`_hardened_hook_command` (returns `f"{python_path} -E -P -m {_HOOK_MODULE}"`).

`docs/security.md` states the design rule plainly: a PreToolUse hook that fails to launch is a
non-blocking Claude Code error, so "the tool call proceeds with no toolguard decision
whatsoever" -- "strictly worse than the shadowing problem this hardening exists to close".
`register-hooks` therefore verifies the interpreter exists and is executable before writing
it. But it then writes the path **unquoted** into a string Claude Code hands to a shell. Any
interpreter path containing a space (a relocated venv, a macOS path under a directory with a
space) produces a command that passes the existence check and still cannot launch -- exactly
the fail-open the surrounding prose says must never be written.

**Recommended fix:** `shlex.quote(python_path)` in `_hardened_hook_command`. Then update
`_hook_registration_findings`'s `command.split()[0]` to `shlex.split(command)[0]` (guarded),
or it will report a correctly-quoted path as `interpreter_missing` -- a false "BROKEN"
diagnostic. Add a test with a space-containing interpreter path.

### M3. `install_provenance.py` duplicates `update_check.py`'s git/dist-name scaffolding

**Files:** `/home/arnon/projects/toolguard/toolguard/install_provenance.py` vs
`/home/arnon/projects/toolguard/toolguard/update_check.py`.

Verbatim duplication: `_GIT_TIMEOUT_SECONDS = 10` (update_check.py:55, install_provenance.py:53)
and the distribution-name constant (`_DEFAULT_DIST_NAME` / `_DEFAULT_NAME`, both `"toolguard"`).
`_git_subtree_is_clean` is the fifth near-identical
`subprocess.run(["git", ...], capture_output=True, text=True, timeout=_GIT_TIMEOUT_SECONDS)`
plus returncode-check plus `.strip()` block across the two modules
(`is_git_worktree`, `local_repo_head`, `local_remote_head`, `remote_head` are the others).

Conceptually the two modules also overlap: `update_check.detect_install()` already answers
"was this toolguard installed from a checkout, and where" via `direct_url.json` plus a
`__file__` walk-up, while `install_provenance.source_checkout_root()` answers a near-identical
question via a sibling `pyproject.toml`. `skills-status` now reports **both** views side by
side (`binary` from `detect_install`, `hook_registrations` from the new module), so a user can
be shown two independently-derived and potentially contradictory pictures of the same install.

The stated reason for the isolation ("imports nothing from `toolguard` itself, so it creates
no dependency `toolguard.hook` would inherit") does not hold up: `update_check.py` is also
stdlib-only, and `install_provenance` is already imported by `session_start` and
`tools/environment_audit`, both of which pull in far heavier modules.

**Recommended fix:** extract a small stdlib-only `toolguard/_git.py` (or reuse
`update_check`'s helpers directly) exposing `run_git(repo, *args) -> Optional[str]` and one
shared distribution-name constant; have both modules import it. Then decide explicitly whether
`detect_install` and `source_checkout_root` should remain two answers to one question -- if
they stay, say in both docstrings why, and make `skills-status` note that the two blocks are
derived differently.

---

## Minor

### m1. `docs/agent-map.md` is missing the new `security.md` section

**File:** `/home/arnon/projects/toolguard/docs/agent-map.md`.

The file states it lists "Every `##`/`###` heading in every doc, generated mechanically". A
mechanical slug-comparison across all of `docs/*.md` found exactly one genuine miss:
`## The hook can be silently shadowed` (`docs/security.md:391`) -- the section this very change
set adds. (Four other reported misses are `##` lines inside fenced log samples in
`architecture.md`/`install.md`; two more were slugification artefacts of the checker.) CLAUDE.md
calls this file "the most likely thing to go stale silently"; it did.

**Recommended fix:** add the entry under the `docs/security.md` block; consider committing the
slug-comparison as a small check that `/documentation-review` runs.

### m2. `_tool_venv_python` never verifies the interpreter can import `toolguard.hook`

**File:** `/home/arnon/projects/toolguard/toolguard/tools/installer.py`, `_tool_venv_python`.

The guard is "a `python3`/`python` sibling exists and is executable". That is not the same as
"this interpreter can run `-m toolguard.hook`". If `binary` is a real script rather than a
symlink and its `bin/` also holds an unrelated `python3`, the hardened command names an
interpreter with no toolguard, which fails to launch -- the fail-open M2 describes. On this
machine the layout is benign (`~/.local/bin/toolguard` is a symlink into the uv tool venv, and
`~/.local/bin` holds only `python3.14`), so likelihood is low, but the check is a one-liner:
either require `bin_dir.parent / "pyvenv.cfg"` to exist, or run
`<candidate> -E -P -c "import toolguard.hook"` once at install time and fall back on non-zero.

### m3. `_hook_registration_findings` false-flags a wrapped command as BROKEN

**File:** `/home/arnon/projects/toolguard/toolguard/tools/installer.py`,
`_hook_registration_findings`: `interpreter = command.split()[0]`.

A hand-edited registration such as `env FOO=1 /path/python -E -P -m toolguard.hook` yields
`interpreter = "env"`, `Path("env").exists()` is `False`, and the tool prints "HARDENED but
interpreter path NO LONGER EXISTS -- BROKEN" for a working hook. Guard on the token being
absolute (`Path(tok).is_absolute()`) before treating a missing path as broken.

### m4. `_tool_venv_python`'s docstring misdescribes `Path.resolve()`

Same file. "Resolving *one* level of symlinks (`Path.resolve()`)" -- `resolve()` resolves the
**entire** symlink chain. The behaviour is still what is wanted here; only the sentence is
wrong, and it is the kind of sentence a future reader would act on.

### m5. `ShadowStatus` is forward-referenced in a signature defined ~190 lines earlier

**File:** `/home/arnon/projects/toolguard/toolguard/session_start.py`. `_format_summary`
(line ~147) annotates `shadow_status: Optional[ShadowStatus]`, but `ShadowStatus` is not
defined until line ~340. This only works because PEP 649 deferred annotations are the default
on this project's Python 3.14 floor -- correct, but load-bearing on a language default that
nothing in the file mentions. Move the dataclass above `_format_summary`.

### m6. The `_hash_py_files` staleness check is coupled to wheel packaging

**File:** `/home/arnon/projects/toolguard/toolguard/install_provenance.py`.

`stale_install_report` compares every `.py` under the checkout's `toolguard/` against every
`.py` in the installed package root. Today this is sound -- `pyproject.toml` has
`[tool.hatch.build.targets.wheel] packages = ["toolguard"]` and `.gitignore` excludes no `.py`
under `toolguard/` (verified). But the moment a `.py` is added under `toolguard/` that the
wheel excludes (a build exclude, or a gitignored generated file), the hashes diverge
permanently while `git status` stays clean, producing a **permanent, unfixable stale nag** --
the failure mode the module's own "never nag on uncertainty" rule exists to prevent.
Worth a comment naming the coupling, and a test that would fail if a wheel exclude for
`toolguard/**/*.py` is ever introduced.

### m7. `audit_takeover` and `security_audit` grew past reasonable size

`audit_takeover` (`/home/arnon/projects/toolguard/toolguard/tools/takeover_audit.py:288`) is
now **293 lines**; invariant 5 gained a ~30-line inline if/else building two long prose
variants. `security_audit`
(`/home/arnon/projects/toolguard/toolguard/tools/security_audit.py:268`) is **162 lines** and
grew another 21-line normalisation block. Both are straight-line, low-branching code, so the
risk is readability rather than defects.

**Suggested refactor:** in `audit_takeover`, give each invariant its own
`_check_invariant_N(config, takeover) -> Optional[AuditFinding]` and drive them from a list;
replace invariant 5's if/else with a `dict[str, tuple[str, str]]` lookup keyed on the resolved
value, which is the pattern that scales when the third loose value arrives. In
`security_audit`, the four per-source blocks are the same shape -- a
`_rank(source, finding, takeover)` adapter per analyser, iterated over a tuple of
`(source, iterable, adapter)`, would collapse most of it.

---

## Suggestions

### s1. Document *why* the SessionStart hook is deliberately left unhardened

`cmd_register_hooks` hardens the PreToolUse command but registers SessionStart as the bare
`<binary>-session-start`. That is **correct and necessary**: `_detect_shadow_status` compares
`governing_package_root()` against the checkout, so an `-E -P` SessionStart hook could never
be shadowed and `running_from_checkout` would be permanently `False` -- the detector would
silently die. Nothing in the code or `docs/security.md` says this, so a future "harden every
hook for consistency" change would disable the feature with no test failing. One sentence in
`_hardened_hook_command`'s docstring and one in security.md, plus a test asserting the
SessionStart registration is *not* hardened.

### s2. The `log_writer` render-then-write claim is honest but could be made true

The new comment says rendering first "narrows the interleaving window". Correct as written. If
you want the stronger guarantee, `os.write(fd, rendered.encode())` on an `O_APPEND` fd is
atomic under `PIPE_BUF`; today's `f.write()` on a buffered text stream can still split a large
entry (a long heredoc command plus a multi-line parse-failure reason can exceed 8 KiB).

### s3. Coverage gap worth closing alongside M1

There is no test for a **multi-leaf** compound under either `allow_with_warning` setting. Add
one per setting, asserting both the WARNING stream and the reason text. Mutation-test them
(neutralise the fix, confirm failure) per this ticket's own practice.

### s4. Things confirmed good, worth keeping

- The marker-safety design (new `allow` reason texts worded so they can never contain
  `...=allow_with_warning`) is correct and has explicit regression tests in `test_resolve.py`.
- `_apply_parse_failure_ask_floor` correctly drops `fallback_warning` when it clamps to `ask`.
- The `hook.py` `main()` decomposition preserves behaviour exactly, including the two
  module-global once-guards and the empty-`file_path` / empty-`command` deny paths.
- `_bash_result_is_fallback_warning` is now additionally gated on `decision == "allow"`, which
  is a strict improvement over the old hook-level check.
- `stale_install_report`'s `if clean is not True` (rather than `if not clean`) correctly
  collapses "dirty" and "undetermined" into silence.
- `pythonpath_shadow_entries` de-duplicates while preserving order, and `audit_environment`
  is silent in the normal case -- consistent with the project's stated anti-alert-fatigue rule.

---

## Tooling notes

**code-review-graph** (refresh done: `embed` + `postprocess` re-run before use; 81 new nodes
embedded, 75 communities). Two invocations. `find_large_functions` earned its keep -- it
surfaced `audit_takeover` at 293 lines and `security_audit` at 162 immediately, ranked, which
is a question neither `LSP` nor `ag` answers in one call (m7). `semantic_search_nodes`
("detect shadowed installation PYTHONPATH provenance hash comparison") did **not** find the
`update_check.py` duplication that M3 rests on -- it returned mostly `Provenance` test
fixtures, matching on the word "provenance" rather than the concept. It did surface
`update_check.detect_install` at rank 4, which was the thread I pulled, so: a partial win, and
the miss was arguably the query's fault (the overlapping concept is "where did this install
come from", not the words I used). Phase: **refactoring / hardening**, which is the phase the
graph's exclusive ground is supposed to cluster in.

**pyscn** not run -- the skill requires asking first and this is a subagent context. Prior
baseline was health 80/B with Arnon's instruction to handle findings case-by-case.

---

## Cost / effort

- Elapsed: ~57 minutes
- Files reviewed: 36 (12 source incl. 2 new untracked modules, 11 test, 13 docs/skills)
- Findings: 0 Critical, 3 Major, 7 Minor, 4 Suggestions
- Estimated cost: ~$4-6 (Opus 5, roughly 180k input with cache reuse, ~30k output)
