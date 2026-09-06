---
title: coder-latest-task-recall
type: note
permalink: toolguard/implementation/coder-latest-task-recall
tags:
- task-memory
- instagram-downloader
---

---
tags: [task-memory, TOO-28, coder-recall]
---

# TOO-28 Phase 1 round 3 -- thread Invocation through the engine layer (Protocol refactor)

Brief: `toolguard-memories/TOO-28/brief-phase1-round3.md` (validated: all 5 slots present).

## Task

Round 2 threaded `Invocation` through `hook.py`, `resolve.py`, `api.py`, then stopped at the
engine layer (`permission_resolution.py`, `compound.py`, `file_matching.py`, `parser/*`),
arguing Protocol-typed config surfaces make threading a concrete `Invocation` wrong there.
Arnon rejected this 2026-09-05: a Protocol expresses a shape requirement one level out, and the
existing Protocols (`ResolutionConfig`, `ResolveConfig`, `FilePathResolutionConfig` in
`config_types.py`) can be refactored into "context" Protocols (`tool_name`, `extended_syntax`,
`config: <SomeConfigProtocol>`) without broadening what they require. Job: finish the
threading by refactoring the Protocols, not discarding them.

Phase 1 stays behaviour-neutral. `permission_mode` becomes reachable; nothing reads it to alter
a verdict.

## Scope

- `permission_resolution.py`: `resolve_command_permission`, `resolve_file_path_permission` --
  all three of config/tool_name/extended_syntax are on Invocation.
- `compound.py`, `file_matching.py`, `parser/*` -- re-measure (round 1 said empty, round 2 said
  file_matching.py has genuine candidates; brief says the two disagree, resolve which is right).
- `config_types.py` -- add the context Protocol(s), expressed in terms of existing Config
  Protocols.
- `resolve.py` loose ends: `_hard_deny_additional_context`'s two params, and whether
  `_decide_bash` should share `decide`'s Invocation.
- Cascade fixups in any broken caller/test authorized as fallout, not new behaviour.
- Decided, do not re-open: `Invocation` stays in `foundation` with an empty import allow-list
  (never imports `config_types`); `api.decide`'s public signature unchanged.

## Baseline (round 2, independently re-confirmed by me before starting)

4021 tests / OK (expected failures=4); ruff clean; three fitness checks pass; corpus 6401
in-process / 61 end-to-end, OK: no differences, calibrated; all 8 console entry points load.

---

## TOO-28 Phase 1 ROUND 2 (this session) -- thread Invocation all the way down

Brief: `toolguard-memories/TOO-28/brief-phase1-round2.md` (validated, 5/5 slots). Everything
below this line, down to "--- (round 1 recall follows, superseded where it conflicts) ---",
is the current task. Round 1's recall further down is historical context only.

### Corrected criterion (supersedes round 1's "2+ statics")
Any parameter whose value is directly available from `Invocation` is a fossil, whether there
is one of them or five. Not just multi-static functions.

### Decided by Arnon, do not re-open
- Engine (resolve.py etc.) takes `Invocation`.
- `api.decide` keeps its PUBLIC signature `(config, tool, target, extended_syntax=True)` and
  constructs an `Invocation` internally (synthetic tool_input, no real cwd/agent_info/
  governed_tools/permission_mode).
- Phase 1 stays behaviour-neutral. permission_mode becomes reachable, nothing reads it to
  alter a verdict (that's Phase 2).

### In scope
- `toolguard/hook.py` -- 6 remaining helpers: `_log_allowed_command`, `_log_non_allow_decision`,
  `_log_config_discovery`, `_resolve_takeover_mode`, `_run_divergence_check`,
  `_run_startup_validation`. Reordering `main()` authorised BUT: `get_env_config()` before
  `load_configuration()` is load-bearing (reporter needs log dir for warnings during config
  discovery) -- if reordering changes WHEN a warning/log line emits, STOP and report.
- `toolguard/resolve.py` -- both `resolve_bash_permission_detailed` and
  `resolve_file_path_permission_detailed`.
- `toolguard/permission_resolution.py`, `toolguard/compound.py`, `toolguard/file_matching.py`,
  `toolguard/parser/*` -- wherever a param is available on Invocation.
- `toolguard/api.py` -- construct Invocation inside decide/_decide_bash. Public signature of
  `decide` unchanged (verify via grep).
- `toolguard/invocation.py` refinements:
  - Fields a non-hook caller lacks (cwd, agent_info, governed_tools, permission_mode) become
    `Optional`/`None`, not `""`. Update type hints + docstring.
  - Add factory classmethod (e.g. `Invocation.for_evaluation(...)`) shared by api.decide and
    tests needing synthetic Invocation. Facts only -- no decision logic in the factory.

### Out of scope for NEW BEHAVIOR but IN scope for refactor fallout
Fix any breakage the signature cascade causes in: tools/installer.py, tools/security_audit.py,
tools/maintenance.py, tools/takeover_audit.py, session_start.py, update_check.py,
permission_migration.py, tools/update_skills.py, tools/decision.py, testing/sandbox.py,
tools/corpus_build.py, every test module. No new behavior, no refactor-for-its-own-sake, no
Invocation injected where not needed. List every file touched this way.

Widening NOT authorised beyond the cascade. No new settings, no auto-mode behavior, no reading
permission_mode to change verdict, no unrelated cleanups -- report, don't fix.

### Steps (13) and completion artifacts -- see brief for full table
1. Re-measure fossils under corrected criterion -- list + count in report.
2. invocation.py refinements -- test_architecture.py allow-list for it stays empty frozenset().
3. resolve.py both resolvers take Invocation -- suite green at baseline counts.
4. api.py constructs Invocation; decide's public signature unchanged -- grep proof.
5. hook.py six helpers + main() reordering -- suite green; explicit statement on log/warning
   emission order.
6. permission_resolution.py, compound.py, file_matching.py, parser/* -- suite green.
7. Fix cascade in out-of-scope modules -- list every file.
8. Lint/format clean.
9. Architecture fitness --stdlib/--ambient/--layers exit 0 each; paste last line of each.
10. Verdict-corpus equivalence: corpus_build.py --verify --strict-prose -> OK: no differences,
    6401 in-process / 61 end-to-end.
11. CALIBRATE FIRST: plant a decision-altering change, confirm --verify FAILS, revert, confirm
    passes, confirm git status --porcelain clean for planted file. Paste all three outputs.
12. ENTRY-POINT SMOKE TEST: import each of the 8 console-script modules from pyproject.toml
    [project.scripts] and confirm each loads. Paste result.
13. Sibling sweep: re-run step-1 scan post-migration, report what remains + why left.

Baseline to match EXACTLY: `Ran 4021 tests` / `OK (expected failures=4)`; ruff check ->
`All checks passed!`; corpus `OK: no differences` at 6401/61. Changed test count = a finding,
not a pass -- say which tests changed and why.

### Round 1 already done (in working tree, build on it)
- hook.py: `_handle_file_path_tool`, `_handle_command_tool` migrated to take `invocation:
  Invocation` (5 statics -> 1). TOO-28-SCAFFOLD aliases deleted. main()'s two call sites updated.
  9 test call sites in test_hook.py updated (construct Invocation via `_invocation()` helper).
- invocation.py: frozen dataclass, 8 fields (tool_name, tool_input, cwd, config, env_config,
  governed_tools, agent_info, permission_mode), imports nothing from toolguard, foundation layer.
- Baseline suite: Ran 4021 tests / OK (expected failures=4). Corpus: 6401 in-process / 61 e2e,
  OK: no differences. Calibrated via config.py _DEFAULT_NO_MATCH_FALLBACK plant/revert (proven
  sensitive).
- Round 1's 6 helpers NOT migrated (now MY job): see hook.py list above.
- Round 1 found compound.py/parser/* reference NO statics at all (may still be empty under
  corrected criterion -- verify, don't assume).

### Conventions
- Given/When/Then docstrings on test functions, kept in sync with edits.
- Comments: short, why not what. ~/.claude/rules/comments.md and python.md apply.
- Do not touch test/verdict_corpus/ (frozen baseline).
- uv run python always, never bare python/python3 (denied by permission rules).
- No git write ops. Step 11 revert = edit file back, never git checkout.
- Disclosure rule: any authored Bash logic needs INTENT/TOUCHES/INLINE BECAUSE comment +
  TG_INTENT=1 (or TG_ATTEST_READONLY=1 if all read-only) prefix on the leaf.

### This brief is unverified -- brief's own flagged uncertainties
- Whether extended_syntax is always derivable from env_config (checked one call site only).
- Whether all 6 hook.py helpers are genuinely migratable (round 1 checked only ordering reason).
- Whether compound.py/file_matching.py/parser/* contain anything in scope (may be empty --
  fine, say so, don't manufacture work).
- Whether main() can be reordered safely at all beyond the one known constraint.
- Whether this stays behaviour-neutral -- step 11 tests this.

Report anything wrong, including in `toolguard-memories/TOO-28/TOO-28 implementation plan.md`.

--- (round 1 recall follows, superseded where it conflicts) ---

## Ticket / context

No YouTrack ticket. Project: /home/arnon/projects/instagram-downloader.
Brief file: /tmp/claude-1000/-home-arnon-projects-instagram-downloader/cb73a65e-4b61-44d5-9ffe-49aacd793eab/scratchpad/brief-grid-navigation-fix.md
Brief validated OK (5/5 slots).

## Task

`process_collection()` in `collection_processor.py` stops after ~16-20 posts in a saved
collection that holds 83+. Root cause diagnosed in brief: exact-match click selector
`a[href='/p/{post_id}/']` never matches real grid hrefs (`/{author}/p/{post_id}/`), so the
loop always falls through to `page.goto(post_url)` — a direct navigation with no way back
to the grid. Subsequent scrolling/harvesting then runs against the post page, not the
collection grid.

## Scope

In scope: collection_processor.py (download_post, _close_popup_if_open, process_collection
scroll/termination loop), models.py (only if PostInfo needs more fields), tests/, a
throwaway probe in tmp_work/.

Out of scope (do not touch): auth.py, navigation.py, browser.py, config.py, tui_app.py,
tui_reporter.py, status.py, metadata_log.py, download_log.jsonl format, anything under
~/OneDrive/Pictures/WFDownloader-replacement/ (report only), .env/.claude.env.

Widening authorized only within collection_processor.py and tests/, per step 1's verdict.

## Steps (in order, per brief)

1. MEASURE FIRST (gates 2/3): probe in tmp_work/ - does clicking a post's real href open a
   modal or navigate away? Does Escape from a modal restore grid scroll/DOM/pathname?
   Artifact: probe file + before/after numbers + one-line verdict.
2. Fix selector at collection_processor.py:542 to use post.href. TDD required: failing
   test against old exact-match selector, passing against new one.
3. Make leaving the grid recoverable. Design depends on step 1 verdict. Invariant:
   process_collection is on the collection grid at top of every scroll iteration.
4. Restore prototype settling times (tmp_work/test_full_scroll_v2.py used uniform(6,8) on
   no-spinner path + uniform(3,5) end of each iteration; production only does
   human_delay(3,5) with no end-of-loop delay).
5. Run uv run pytest, uv run ruff format ., uv run ruff check . — paste output.
6. Verify against live "August 2026" collection in DRY_RUN mode; confirm discovered count
   exceeds 83 and keeps climbing to natural end.
7. Sibling sweep: check other hardcoded selectors (_CAROUSEL_NEXT_BTN :157,
   _CAROUSEL_SLIDE_COUNT_JS, _EXTRACT_POSTS_JS, [role="dialog"] assumption) against reality.

TDD required only for step 2 (pure, testable without browser). Not required for 3/4/6
(Playwright-integration, real verification is the live run in step 6).

## Findings carried forward (dispositions already decided by brief author)

1. Exact-match selector never matches -> FIX (primary bug), use post.href.
2. goto fallback is unrecoverable -> FIX (grid must be restored or loop must tolerate
   leaving it).
3. _close_popup_if_open is a no-op with no dialog -> FIX together with #2.
4. Settling time ~half prototype's -> FIX.
5. One download_log.jsonl record has a 39-char post_id (should be 11) -> REPORT ONLY, do
   not touch WFDownloader-replacement files.
6. reporter.discovered() DOM-snapshot first arg caps at 42 under virtual scrolling ->
   REJECTED, leave alone, informational only.
7. Spinner detection/scroll mechanics are sound (measured: +1661px, +12 posts/scroll, 83
   unique after 6 scrolls, still climbing with post-opening removed) -> NO CHANGE.
8. convert_image_to_png cannot derail flow (utils.py:109-115 catches everything) ->
   REJECTED as cause, no change.

## Brief's measured vs inferred claims (attack the inferred ones)

Measured: grid href shape, 0/8 exact-match, scroll growth numbers, DOM caps at 42,
download_log.jsonl 52 records stats.

Inferred / NOT verified — my job to check:
- Clicking real href opens a modal vs navigates away (step 1 exists for this).
- Escape from modal restores grid scroll position / loaded posts (Instagram pushes
  /p/{id}/ into history on modal open; popstate may reset virtualized list).
- Extra 5-8 posts/run come from post-page recommendations (inferred from 39-char post_id).
- True size of August 2026 collection unknown — 83 was still climbing; don't treat 83 as
  the hard target, just "keeps climbing past 83 to a natural end".

Also: current working tree has uncommitted mods to browser.py, config.py, pyproject.toml
etc. — line numbers in brief may drift; re-resolve against current file.

## Constraints

uv run python always. Comments short, why not what. String literals branched on -> named
constants. Do not commit (Arnon does git writes). No async/threading/local imports without
approval. Live IG session already valid in browser_data/ — probes using project's own
BrowserManager + navigation.py should just work; examples in tmp_work/.