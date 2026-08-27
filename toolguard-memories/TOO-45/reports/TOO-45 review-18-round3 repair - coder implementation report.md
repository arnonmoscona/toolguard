---
title: TOO-45 review-18-round3 repair - coder implementation report
type: note
permalink: toolguard/too-45/reports/too-45-review-18-round3-repair-coder-implementation-report
tags:
- task-memory
- TOO-45
- implementation-report
---

## Summary

Repaired all findings from `review-18-round3.md` (1 blocking, 9 non-blocking) on the
uncommitted ticket-18 work. `toolguard/permissions.py`'s matching logic was **not** touched
except a verified-equivalent dead-branch simplification (N8) plus a comment. Everything else
is documentation and tests, as briefed.

## N1 (elevated above blocking) -- the published curl recipe was unusable

Measured before fixing: the published `[hard_deny]` carve-out
`allow = ["Bash([regex]^curl\s+http://(localhost|127\.0\.0\.1)(:\d+)?(/\S*)?$)"]` denies
`curl -sS http://localhost:8080/health`, `curl -s http://localhost/x`, and
`curl -X POST http://localhost/api` -- any flag before the URL fails to match. Widening the
regex to admit flags (`^curl(\s+-\S+)*\s+http://...(\s+-\S+)*$`) was also measured: it exempts
`curl -L http://localhost/redirect-to-evil` (arbitrary redirect), reopening exactly the attack
the carve-out existed to close.

**Fix applied everywhere**: no pattern is both safe and usable here. Name each real invocation
exactly, one `Bash(...)` allow rule per command, e.g. `Bash(curl -sS http://localhost:8080/health)`.
Verified end-to-end via `toolguard.testing.sandbox.experiment()`: the exact command is allowed;
a different flag spelling, an extra flag, and a second URL are all still denied.

**Native quote used** (fetched `https://code.claude.com/docs/en/permissions.md`, **2026-08-20**,
"Wrappers" subsection):

> Development environment runners such as `direnv exec`, `devbox run`, `mise exec`, `npx`, and
> `docker exec` are not in the list. Because these tools execute their arguments as a command, a
> rule like `Bash(devbox run *)` matches whatever comes after `run`, including
> `devbox run rm -rf .`. To approve work inside an environment runner, write a specific rule that
> includes both the runner and the inner command, such as `Bash(devbox run npm test)`. Add one
> rule per inner command you want to allow.

A second, even closer sentence from the same page (the `find -exec` / exec-wrapper paragraph),
not quoted in the docs but informing the same fix: "To approve a specific invocation, write an
exact-match rule for the full command string."

**Rewritten in all three places**:
- `docs/configuration.md` -- the `[hard_deny]` example's `allow` list.
- `docs/agent-guides.md` -- same recipe; also added `"Bash(curl:*)"` to that recipe's own
  `deny` list (N9 -- previously it had no curl deny at all, so its carve-out was inert against
  its own example).
- `.claude/skills/toolguard-security-audit/SKILL.md` -- both the reasoning bullet (~line 301)
  and few-shot fix #5 (~line 391).

## B1 (blocking) -- row 19 misattribution, fixed

`docs/native-pattern-reference.md` row 19 said `agent-guides.md` published the paired
`deny Bash(curl:*)` / `allow Bash(curl http://localhost:*)` shape. Verified via
`git show HEAD:docs/agent-guides.md` (lines 182-190): its `[hard_deny]` example has **no**
curl deny entry, only the allow. Row 19 now attributes the allow line to both files and the
deny line to `configuration.md` alone, and states that `agent-guides.md`'s carve-out was inert
against its own deny both before and after the colon-recognition change (a separate,
pre-existing defect -- since fixed here via N9).

**N3** (stale pointer) fixed in the same edit: "(row 18's quote)" now reads "(the
single-`*`-spans-spaces quote above)", pointing at the verbatim quote at line 22, since this
round's diff removed that clause from row 18's own cell.

Also updated the "both recipes have been corrected" sentence to say what they were actually
corrected to (exact invocations), not the stale "single-URL-anchored `[regex]` form" claim --
the same stale claim also lived in `test_hard_deny.py`'s docstring and is fixed there too (see
N2 below). Grepped the whole repo for both strings; no other in-code occurrence.

## N8 -- `Bash(:*)` decision: document, not enforce

**Decision: document the behavior, do not add load-time validation this round.** A bare `Bash(:*)`
silently matches nothing (verified: `match_command("ls -la", [":*"])` -> `(False, None)`, no
raise). On a deny that's fail-open; on an allow it's a silently-inert rule. A real fix (reject
or warn at config-validation time) belongs in `toolguard/config_validation.py`, which already has
the right shape for it (`validate_permissions`, per-entry `Issue`s) -- but that's a new feature
with its own tests, outside this round's docs/tests-and-one-dead-branch scope, and risks scope
inflation on a repair round. Recommend a follow-up ticket if this matters enough to enforce.

Separately, verified by execution that the dead-branch simplification is safe: on the
`endswith(":*")` branch, `cmd_pattern` (`.strip()`ed) can only be `""` when `pattern_parts` is
empty, for every synthetic body tried plus a match-behavior differential against `HEAD`'s
`permissions.py`. Changed `base_cmd = pattern_parts[0] if pattern_parts else cmd_pattern` to
`else ""` with a one-line comment explaining why and noting the silent-no-match consequence.
Confirmed behavior-neutral by direct execution and by the full suite (3795/OK unchanged).

## N2 -- weak assertion strengthened

`test_colon_star_carveout_now_exempts_an_unrelated_second_url` previously asserted only
`assertIsNone(...)`, indistinguishable from "the deny never matched." Added the control: same
deny, no carve-out (`allow=[]`) -> `assertIsNotNone` for both commands, verified by execution
first. Docstring updated to describe the control.

## N5 -- non-differential cases, kept with a scoping note

Verified by execution (differential against a synthetic `HEAD`-paired module) that all 4
subtests of `test_colon_star_boundary_witness_shapes_a_person_would_not_write_by_hand` are
identical pre/post this round's diff. They pin real, pre-existing boundary behavior (not
duplicated elsewhere), so I kept them rather than deleting real coverage, and added one
sentence to the docstring making the non-differential scope explicit so the test count isn't
misread as coverage of this round's change.

## N7 -- ticket residue removed from test docstring

Removed the commit hash `05f786d` and the unverifiable "315 counterexamples" claim from
`test/unit/test_pattern_overlap.py`'s `TestPrefixesOverlapAgreesWithMatchCommand` docstring.
Grepped the whole repo (code and docs, not memory notes) for both strings -- no other
in-code occurrence.

## N4 -- SKILL.md wording precision

Rewrote the trailing-`*`/`:*` bullet (~SKILL.md:301) to: scope the "matches native's own
semantics" claim to the `:*` form specifically (a hand-written trailing ` *` diverges on a
bare no-argument command, per row 18); and fix "matches whatever is appended after it on the
same command line" -- verified `curl http://localhost/health` does **not** match
`Bash(curl http://localhost:*)` (the boundary requires a space or end-of-string), only a
space-separated continuation does.

## N6 -- live consequence, noted for the release note

`Bash(\obsidian search:context *)` in this machine's untracked
`.claude/toolguard_hook.toml` is a live allow rule that silently stops matching under the new
`:*`-recognized-only-at-end rule (`\obsidian search context foo` -> `False`). Not fixed here
(untracked, personal config, out of this ticket's file scope) -- flagged below for the release
note and for Arnon to fix directly (`Bash(\obsidian search context:*)`).

## Verification performed

- `uv run python -m unittest discover -s test -t .`: **3795 tests, OK, expected failures=4**,
  matching baseline, both before and after every substantive edit.
- `~/.toolguard/errors/`: **1950 before and after** the full suite run -- no new crash reports.
- `uv run ruff format .` / `uv run ruff check .`: clean.
- `uv run python tools/architecture_fitness.py --ambient/--layers/--mocks`: clean; the one
  `--mocks` finding (`test_session_warnings.py:159`) is pre-existing and untouched by this round.
- N1's recipe verified both as a fragment (`check_hard_deny`) and end-to-end through
  `toolguard.testing.sandbox.experiment()` (isolated home/env/project-root) -- the exact
  documented command is `allow`ed; a different flag spelling, an added `-o`, and a second URL
  are all still `deny`d.
- N8's dead-branch claim verified via a synthetic probe over 16 pattern bodies, and behavior
  verified identical to `HEAD` via a differential harness loading `HEAD:toolguard/permissions.py`
  as a synthetic submodule of the real `toolguard` package (unchanged siblings confirmed via
  `git diff --stat`).
- N5's non-differential claim verified the same way, case by case.
- B1's misattribution verified via `git show HEAD:docs/agent-guides.md`.
- N4's boundary claim verified by direct `match_command` execution.
- All edited TOML fragments (`configuration.md`, `agent-guides.md`) parsed with `tomllib` to
  confirm they are syntactically valid and contain exactly the claimed deny/allow entries.

## Brief vs. code

The brief's own caution ("trust the code over this brief") was checked: `git diff --stat
toolguard/permissions.py` shows 24 insertions / 30 deletions this round, confirming the brief's
own note that the matching logic **did** change substantively this round (not comments-only) --
consistent with review-18-round3's "Brief vs. code" section. I did not add to that diff except
the one verified-equivalent dead-branch line plus a comment.

## Files changed this round

- `docs/configuration.md` -- N1 recipe rewrite.
- `docs/agent-guides.md` -- N1 recipe rewrite + N9 (added missing curl deny).
- `docs/native-pattern-reference.md` -- B1 (row 19 attribution) + N3 (stale pointer) +
  updated "corrected to" claim.
- `.claude/skills/toolguard-security-audit/SKILL.md` (dot_files symlink, editable by standing
  grant) -- N1 (few-shot #5) + N4 (reasoning bullet wording).
- `toolguard/permissions.py` -- N8 dead-branch simplification (`else ""`) + explanatory comment.
  No matching-logic change.
- `test/unit/test_hard_deny.py` -- N2 (control assertion) + stale-claim fix in the same
  docstring.
- `test/unit/test_pattern_overlap.py` -- N7 (removed commit hash + unverifiable count).
- `test/unit/test_permissions.py` -- N5 (scoping note in docstring).

8 files touched, all within the brief's named scope. No new files created in the repo (scratch
probes lived only under the session scratchpad and were deleted before finishing).

## Not done / deferred

- N8's "reject or warn at load time" was decided against for this round (documented instead) --
  see rationale above. Candidate follow-up ticket if Arnon wants it enforced.
- N6's live `.claude/toolguard_hook.toml` fix was not applied (untracked personal config,
  outside this ticket's file scope) -- flagged for Arnon.

## Release-note draft (0.5.1, curl-carve-out section)

> **`hard_deny` / DEFAULT `:*` fidelity fix, and a doc correction that goes with it.**
> `Bash(cmd:*)` and mid-pattern `:` matching now follow Claude Code's own rule exactly: the
> `:*` shorthand is recognised only at a pattern's literal end, so `curl http://localhost:*`
> is a real boundary-checked prefix instead of splitting (and matching almost nothing) at the
> colon inside the URL. This is more permissive for that shape and more restrictive for
> ad-hoc `cmd:args`-style patterns (e.g. `git push:--force *` no longer matches
> `git push --force origin`) -- both directions match native as of 2026-08-20; see
> `docs/native-pattern-reference.md` rows 18-19.
>
> **If you have a `hard_deny.allow` curl carve-out written as
> `Bash(curl http://localhost:*)` or similar**, re-check it: a trailing `*`/`:*` spans
> arguments, so that shape now also exempts anything else on the same command line, including
> a second URL. We found no pattern-based fix that is both safe and usable (a flag-free anchor
> blocks ordinary flagged curl usage; a flag-tolerant one re-admits `-o`/`-L`), so our own docs
> now recommend naming each real invocation as an exact allow rule instead, one per command --
> the same approach Claude Code's own docs prescribe for environment runners like `devbox run`.
>
> **Known affected pattern on at least one dev machine**: `Bash(\obsidian search:context *)`
> silently stops matching under the new rule (a `:` followed by literal text, not a bare `*`,
> is no longer a `cmd:args` split). If you have a rule of that shape, rewrite it as
> `Bash(\obsidian search context:*)` or an equivalent whole-string pattern.

## Elapsed time / cost estimate

Rough phase breakdown (no precise start timestamp captured at session start):

- Planning (read review report, doc-drift greps, memory write): ~35-40 min.
- Implementation (all doc/test/permissions.py edits, native-doc fetch, TOML/sandbox
  verification probes): ~90 min, the largest share going to the N1 end-to-end sandbox
  verification (discovering and working around the `Sandbox()` vs `experiment()` API) and the
  N5/N8 differential-execution probes against a synthetic `HEAD` module.
- Self-review (full diff re-read, repeat suite runs, ruff, architecture_fitness, cleanup,
  report writing): ~35 min.

Total: roughly 2h10m wall clock. Estimated cost (Sonnet 5, mixed heavy tool use -- several
full-suite runs, one doc fetch, ~6 verification probes): **~$3-4**.
