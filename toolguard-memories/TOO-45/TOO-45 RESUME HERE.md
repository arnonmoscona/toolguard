---
title: TOO-45 RESUME HERE
type: note
permalink: toolguard/too-45/too-45-resume-here
tags:
- task-memory
- TOO-45
- resume
---

# TOO-45 RESUME HERE

Rewritten at each stop. **Read this first**, then [[TOO-45 decision log]] (the long-form record) and [[TOO-45 architecture overhaul execution plan]]. Written 2026-08-05, end of the first full working day on this ticket.

## FIRST, ON A COLD RESTART

**Remind Arnon that this session must be put back into auto-mode.** A restart drops it, it is easy to forget, and unattended progress is the whole execution model here. Say it before anything else. Then re-create an anti-stall reminder if the session will run unattended — cron jobs are session-only and do not survive a restart.

## State: the approved scope is COMPLETE and UNCOMMITTED

```
R1: PASS   R2: PASS   R3: PASS   R5: PASS   R6: FAIL (its own ticket, agreed with Arnon)
suite 2,387 OK      corpus 6,401 in-process + 61 e2e, no differences
--guard PASS 12/12  ruff clean (--no-cache)    doc links resolve
--layers completeness 100%, 1 direction violation: hook -> tools.decision (R6-deferred, deliberate)
```

**~58 modified/added files are uncommitted, spanning fifteen completed stages.** Committed baseline is still `11d1fd0`.

```bash
git add -A && git commit -m "TOO-45: verdict unification, audit-trail fix, leaf entry points, one rule representation"
```

**This is the biggest outstanding risk and it is my process failure.** I offered a commit command after D1a and never re-offered one at each subsequent green checkpoint. It already cost real time: when R1e half-failed there was no clean rollback point, because reverting it alone would have taken D1a through R1d with it. **Commit at every verified-green checkpoint.**

## Verify after any restart

```bash
uv run python -m unittest discover -s test -t .            # 2387 OK
uv run python tools/corpus_build.py --verify               # no differences
uv run python tools/architecture_fitness.py --guard        # PASS, 12 canaries
uv run python tools/architecture_fitness.py --predicates   # R1/R2/R3/R5 PASS, R6 FAIL
uv run ruff check --no-cache .                             # NOTE: --no-cache always
echo '{"session_id":"t","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"'$PWD'"}' | PYTHONPATH=. uv run python -m toolguard.hook
```

## What was done

| step | result |
|---|---|
| **R3** | zero production sites parse structured data out of reason prose |
| **D4** | one undecidable floor, not two — proven by a mutation that flipped MISSED -> CAUGHT |
| **D1a** | decision orchestration out of `Configuration` into `permission_resolution` (engine layer, imports only `config_types`) |
| **R1** | one runtime verdict type (`RuntimeVerdict`); `UnitVerdict`/`Decision`/`LevelMatch` are declared altitudes; 2 `__iter__` shims and 13 bare verdict tuples gone; `log_command` 12 params -> 4 |
| **R5** | entry points are leaves; `permission_migration` and `install_update` split out of their console scripts; `hook <-> tools.decision` cycle gone |
| **R2** | index-parallel access 3 -> 0; prose invariant statements 4 -> 0; both drift guards deleted; misaligned `ToolPatternLayer` state now **unconstructible** |

**The single most important outcome is not a predicate.** The compound audit trail was **83% lossy** — 813 of 975 compound-allow cases under-logged, 1,943 sub-commands executed with no audit record — because `hook.py` recovered the breakdown by regex over reason prose and silently dropped every segment without `" -> "`. It is now **0 of 978**. Fixing it exposed a second, independent bug: `resolve._deciding_sub_match` and `tools.decision._decide_bash` both attributed provenance with heuristics that only worked *because* escape-hatch leaves were missing.

## NEXT

1. **Commit.** See above.
2. **Pre-push checklist** (global CLAUDE.md + project additions): coverage (`uv run python tools/coverage_stdlib.py`), documentation updates, version bump in `pyproject.toml`, release notes, `pyscn analyze` on the main package, and the two project-specific questions — do the changes require updates to the **maintenance skill** or the **security-audit skill**, and to `install.md`? Anything under `docs/`, `README.md`, `AGENTS.md` or `llms.txt` that changed needs `/documentation-review`.
3. **The audit-log format changed** (R3 added a `Provenance` field, narrowed `Matched Rule`; R1e added per-sub-command entries and provenance). Arnon's standing call: log it as an additional step after the main refactor, plus the maintenance-skill question and release notes.
4. **R6 is its own ticket.** Its groundwork is done: the engine's config surface is provably all-public, and `hook -> tools.decision` is the one remaining layer violation, deliberately parked with a comment explaining that it stays a *local* import because the hook is a per-process-per-call binary and hoisting it would load the tooling layer on the hot path.
5. **Carry into R6's brief:** `decide()` belongs in an `api` layer both callers can reach. Demonstrated by execution that `decide()` is **not on the live path** — `toolguard.tools.decision` reaches `sys.modules` only under `--eval`.
6. **Deferred, evidence recorded:** `compound.py::fallback_kind_for_reason` remains R3's one sanctioned exclusion. Both its call sites were assessed by execution and prose/structural classification always agree; site 1's real fix is blocked by 20 test closures hand-built against the narrow 3-tuple `resolve_one` contract. Re-earned on evidence, not grandfathered.

## Ruff configuration is now in force

Four rules on top of the stock defaults: **PLC0415** (no function-level imports), **TID251** (bans `threading`/`asyncio`/`multiprocessing`/`concurrent.futures`), **PLR0913** (`max-args = 8`), **RUF100** (unused noqa, making every suppression self-cleaning). `select` is pinned explicitly — `preview = true` is scoped to `[tool.ruff.lint]` because setting it at `[tool.ruff]` turns on the preview **formatter** and reformats 55 files. Full analysis and the rejected list: [[TOO-45 ruff configuration proposal]].

---

## Operating rules that have already cost time

- **Git: `add` and `commit` only, on branch `too-45`.** Everything else denied by rule. **NEVER tell a subagent to revert with `git checkout`/`restore`/`stash`** — one hung on an ASK prompt for 85 minutes and had to be killed with the tree failing. Tell them: back up original bytes to a scratch file, copy back, verify with `sha256sum`. **And make them populate the backup directory BEFORE editing** — two agents created it and skipped the snapshots.
- **Watch for silent agent stalls.** Check file mtimes rather than waiting on a notification. The 85-minute stall was found that way; its last transcript line showed it mid-verification.
- **`uv run ruff check .` can report clean FROM CACHE against a tree that has an error.** Always `--no-cache` when the result is evidence.
- **Subagent repo copies must exclude `.git`/`.venv` and be deleted after.** Accumulated copies filled the temp filesystem; every Bash command then returned **empty** rather than erroring.
- **Mutation runs: state the target.** A mutation "MISSED" against the corpus may be fully pinned by unit tests. Harness at `scratchpad/mutation_gate.py` prints its target.
- Both permission files are **denied to the agent** — Arnon edits them. Telegram chat_id **8205417538**.

## The method, as it actually works

- **Scope every step with an executed trace before implementing.** Used on D1, R1, R5 and R2; it changed the plan every time, and twice it deleted more work than it created.
- **Fix the measuring instrument BEFORE the step it scores**, as its own isolated task so no refactor can tune its own metric.
- **Two judges with deliberately different questions** — architect: *what does this contain?*; blinded: *what would notice if it were wrong?* Neither lens sees the other's findings.
- **Mutate what you just built.** Acceptance is "make it wrong on purpose and confirm something fails", never "did I add assertions".
- **Record a prediction before a step**, then score it honestly. I lost several; the losses were the most informative results.

## Standing failures of mine, with today's evidence

1. **Claims derived from a representation rather than from execution.** Every correction all day came from something that ran.
2. **I fix instances, not classes.**
3. **A turn that ends with intentions ends.** Unattended stretches need a pending agent or a scheduled wakeup.
4. **NEW — I trusted instruments without checking they could express the outcome.** *Seven* instrument defects in one day: name-substring matching; a caller scan confined to one directory; a gate on half a predicate's own definition; a scan that could only see classes; a footprint metric blind to positional coupling; a field deliberately named to dodge a detector; and a class-name-hardcoded scan a `sed` could defeat. Every one reported success or failure it had not earned. **Six of seven were caught only by running something.**
5. **NEW — rename-and-count measures NAME COUPLING, not work.** Renaming `hard_deny` breaks 106 tests; the actual R2c change to the same code breaks 0. R5b's "88" and R5c's "180" both resolved to zero net suite change. **Report mechanical versus behavioural separately, or do not report the number.**
