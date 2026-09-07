---
title: Coder Latest Implementation Report
type: note
permalink: toolguard/implementation/coder-latest-implementation-report
tags:
- task-memory
- TOO-28
- implementation-report
---

## TOO-28 Phases 6+7 -- Implementation Report

Brief: `toolguard-memories/TOO-28/brief-phase67.md`. Both phases done in one working-tree
change, uncommitted (git write ops are Arnon's). Tree left dirty as instructed.

### Phase 6 -- documentation (7 items, all done)

1. **Division of labour frame**: verified absent from docs/security.md and
   docs/architecture-as-built.md (grepped both fully) before writing. New section
   `## Division of labour: toolguard vs. auto-mode guidance` added to `docs/auto-mode.md`,
   before "The honest tradeoff" -- strong/blind table, "complementary halves not two
   implementations" framing, blind spot is constitutive.
2. Design smell ("make toolguard smarter so it can handle X") folded into the same new
   section as its closing paragraph.
3. Handoff framing at `docs/configuration.md:669` verified accurate (Phase 2/3 material) --
   its link retargeted from `auto-mode.md#how-this-differs-from-takeover-mode` (wrong
   anchor -- that section is about Auto-mode vs Takeover-mode mechanism, not the
   toolguard-vs-classifier frame) to the new
   `auto-mode.md#division-of-labour-toolguard-vs-auto-mode-guidance` anchor. No content
   duplicated.
4. Early pointer: new Q&A entry in `docs/agent-map.md`'s "Modes" section (agent
   orientation index); README.md's doc-table row for auto-mode.md extended one clause;
   quickstart.md's "Running unattended" paragraph extended one clause. agent-guides.md
   ("AI agents start here") already pointed to auto-mode.md -- confirmed via grep, no
   change needed there.
5. Takeover-mode inaccuracy: fetched `https://code.claude.com/docs/en/permission-modes`
   IN THIS SESSION (2026-09-07) per native-fidelity-claims.md. Verbatim quote captured
   (see below). Added a dated paragraph to `docs/takeover-mode.md`'s Security warnings,
   scoped to Bash only (did not extend the claim to Read/Write/Edit blanket allows,
   which the fetched doc does NOT list as dropped on auto-mode entry -- avoided
   overclaiming beyond what was verified).
6. Auto-mode trace: new section `## The auto-mode trace log` in `docs/auto-mode.md`,
   sourced from `toolguard/hook.py::_classify_fallback_cause`'s docstring (grounded in
   real writers: permission_resolution.py/compound.py set fallback_cause structurally)
   rather than `auto_mode_trace.py`'s own docstring, which I read FIRST per the brief's
   instruction and found partly stale (see Phase 7 below) -- did not copy the stale
   "does not yet vary fallback behaviour by permission_mode" framing into the docs.
7. FOREIGN_EXECUTORS scope: one paragraph added to `docs/configuration.md`'s
   "Undecidable fallback" section, lifted from the code comment at
   `toolguard/parser/command_extractor.py:162-164`, framed as scope (not a "gap" --
   Finding 1 in the brief retracted that framing).

**Native docs fetch (2026-09-07), verbatim quote used for item 5:**

> On entering auto mode, broad allow rules that grant arbitrary code execution are dropped:
> Blanket `Bash(*)` or `PowerShell(*)`, wildcarded interpreters like `Bash(python*)`,
> package-manager run commands, `Agent` allow rules, and `Monitor` allow rules... Narrow rules
> like `Bash(npm test)` stay in effect. Claude Code restores the dropped rules when you leave
> auto mode.
> -- https://code.claude.com/docs/en/permission-modes, "How the classifier evaluates actions"

Cross-check: `docs/security.md`'s existing claim "toolguard's ASK does not become a silent
allow, including in auto-mode... Claude Code's unattended modes do not bypass it" was
independently verified TRUE against the same fetch (permission-modes doc: "Claude Code
doesn't add the option to prompts forced by one of your ask rules or by a hook, because
auto mode still shows you those prompts"). No fix needed there -- confirming cross-check,
not a finding.

**Link verification (step 6)**: wrote a scratch checker
(`/tmp/.../scratchpad/check_doc_links.py`) implementing GitHub's anchor-slug algorithm,
resolving every `[text](file#anchor)` link against the target file's actual headings.
Ran against the 6 touched files: 351 links, all resolve. Ran against all of `docs/` +
README.md + AGENTS.md + llms.txt: 549 links, all resolve (no pre-existing breakage
either). Master TOC in `docs/agent-map.md` updated with the 2 new auto-mode.md headings.

### Phase 7 -- comment/docstring cleanup (`git diff TOO-28-start-of-work..HEAD -- '*.py'`)

**7a (scaffold deletion)**: re-derived from scratch per the brief's warning that the
plan's inventory was stale. Grepped the diff and current tree for SCAFFOLD, TODO, FIXME,
XXX, HACK, "not implemented", "eventually" -- zero hits. No pure-scaffolding comments
found to delete.

**7b (trim to long-term value)**: see the disposition table below. Summary:
- 45 `TOO-28` references found (grep, exact count matched diff-added count) -- all
  trimmed (ticket-reference parenthetical removed, substance kept). 0 false positives
  (every one was a pure ticket-ID tag on an otherwise-good sentence).
- 12 `spec 4.x`/`spec section N` internal-planning references found beyond the TOO-28
  set -- all trimmed the same way.
- 2 process-artifact references ("the brief's Finding 2", "brief's own unverified claim
  #5") -- trimmed, substance kept.
- 6 "round N (date)" ticket-history references in test_hook.py/permission_resolution.py
  -- trimmed; two of them wrapped genuinely valuable regression-story content (a
  documented past bug in the fallback_cause classifier), which was KEPT, only the
  ticket-round dating removed.
- **1 CONFIRMED FALSE comment, rewritten**: `toolguard/auto_mode_trace.py`'s module
  docstring said "toolguard does not yet vary its fallback behaviour by permission_mode
  at all (that is a later phase)" -- false since Phase 2 shipped
  `resolved_no_match_fallback_in_auto_mode`/`resolved_undecidable_fallback_in_auto_mode`.
  Rewritten to state the CURRENT truth: the trace's firing is not itself evidence of
  looser governance; that depends on whether the `_in_auto_mode` settings are actually
  configured to differ from base.
- Searched for OTHER false "not yet"/"later phase" claims beyond this one (brief's own
  flagged uncertainty) -- none found; the auto_mode_trace.py one was the only hit for
  "not yet"/"later phase"/"round N" combined with a factual (not just historical)
  claim.
- Two carried dispositions applied exactly as specified:
  - `toolguard/invocation.py` module docstring: kept the rule ("explicit argument, not
    an ambient singleton"), dropped the in-process-corpus elaboration and the
    eight-console-scripts enumeration (both replaced with one-line statements).
  - `test/unit/test_architecture.py:42`: kept the substance (why the allow-list is
    empty), dropped the `TOO-28:` prefix.
- Two duplicate-content pairs found and consolidated (not itemized in the brief, found
  during the sweep): `toolguard/config.py`'s `_FallbackSetting` class docstring and
  `unrecognized_fallback_settings()`'s method docstring said the same "single registry"
  fact twice, in different words; the method docstring now cross-references the class
  docstring instead of restating it. Same pattern in
  `toolguard/tools/takeover_audit.py` (module docstring vs. an inline comment above the
  Invariant 6/7 code) -- inline comment now cross-references the module docstring.

**Step 8 -- R3_SANCTIONED_SITES judgement**: `tools/architecture_fitness.py:1607`'s
`R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}` names a function
deleted in a PRIOR ticket (TOO-45 ticket 38, per `test_compound_resolve_seam.py:410`'s
"the now-deleted `fallback_kind_for_reason`") -- NOT this ticket's diff, so out of the
strict git-diff scope, but the brief named it as a bounded, authorized exception.
**Confirmed it is not inert**: `test_architecture_fitness.py:1884`'s
`test_sanctioned_site_is_excluded` builds synthetic source using that exact function
name to pin the sanctioned-sites EXCLUSION MECHANISM (not real compound.py coverage).
**Decision**: did NOT touch the tuple or the test (removing/renaming the tuple entry
would change what that test pins, and the brief explicitly said STOP rather than adjust
the test to fit). DID fix the now-false comment above the constant (it claimed the site
was "the structured contract other code calls into instead of parsing reason text
itself" and "the site R3 may eventually replace outright" -- both false today, since the
function is already gone). New comment states plainly: the exclusion is currently inert
against real code, kept only because the named test pins the mechanism against synthetic
source. This is the widening clause's explicit allowance (b): a false doc statement found
while working nearby, corrected and reported separately -- reported here.

### Comment disposition table (7a/7b) -- Arnon reads this section first

| File | What the comment claimed | Disposition |
|---|---|---|
| `toolguard/auto_mode_trace.py` (module docstring, ~line 21) | "toolguard does not yet vary its fallback behaviour by permission_mode at all (that is a later phase)" | **REWRITTEN AS FALSE** -- Phase 2 already shipped the `_in_auto_mode` resolvers. Rewritten to state current, accurate scope. |
| `tools/architecture_fitness.py:1601-1606` (R3_SANCTIONED_SITES comment) | "the structured contract other code calls into... the site R3 may eventually replace outright" | **REWRITTEN AS FALSE** -- the referenced function (`compound.fallback_kind_for_reason`) was already deleted in a prior ticket; nothing calls into it. Rewritten to state it is currently inert, kept only for a pinning test. Flagged separately per widening clause (b). |
| 45 sites across 17 files (`config_types.py`, `config.py`, `hook.py`, `invocation.py`, `permission_resolution.py`, `resolve.py`, `rule_entry.py`, `constants.py`, `session_start.py`, `parser/command_extractor.py`, `tools/takeover_audit.py`, and 6 test files) | `(TOO-28)` / `(TOO-28 spec 4.2)` / `(TOO-28 spec 4.3)` ticket-ID tags on otherwise-accurate sentences | **TRIMMED** -- ticket tag removed, substance kept verbatim. |
| 6 sites across `permission_resolution.py` and 2 test files | `(spec 4.x)` / `(spec section N)` tags without the literal string "TOO-28" | **TRIMMED** -- same treatment. |
| `test/unit/test_hook.py` (2 sites) | Regression-story docstrings dated "round 6 (2026-09-06)" explaining a fixed classifier bug | **TRIMMED** -- ticket-round dating removed, the regression-story substance (a real past bug, legitimate per the "specific incident" exception) kept. |
| `test/unit/test_hook.py:~3058` | "this is the exact ambiguity the brief's Finding 2 flagged" | **TRIMMED** -- process reference removed, substance kept. |
| `test/unit/test_resolve.py` (TestPerRuleAutoModeBehaviorInACompound) | "(brief's own unverified claim #5), not new production code" | **TRIMMED** -- process reference removed. |
| `toolguard/invocation.py` (module docstring) | Long in-process-corpus argument + eight-console-scripts enumeration | **TRIMMED** per carried disposition -- rule kept, argument dropped. |
| `test/unit/test_architecture.py:42` | `# TOO-28: invocation context. ...` | **TRIMMED** per carried disposition -- substance kept, ticket prefix dropped. |
| `toolguard/config.py` (`_FallbackSetting` docstring + `unrecognized_fallback_settings()` docstring) | Same "single registry both X and Y read" fact stated twice | **CONSOLIDATED** -- method docstring now cross-references the class docstring instead of restating. |
| `toolguard/tools/takeover_audit.py` (module docstring + inline comment above Invariant 6/7) | Same "no Invocation, reports what would resolve" fact stated twice | **CONSOLIDATED** -- inline comment now cross-references the module docstring. |
| Everything else in the 46-file, 5459-insertion diff | -- | **KEPT AS-IS** -- reviewed via full-diff greps for SCAFFOLD/TODO/FIXME/staleness markers (zero hits beyond the above) plus a manual read of `compound.py`'s full diff (the largest, most logic-dense file) -- no further issues found. |

**False-comment count: 2** (auto_mode_trace.py's module docstring; the
R3_SANCTIONED_SITES comment, which was outside the strict diff scope but explicitly
authorized as a bounded extra).

### Verification (all green, final state)

- Baseline (measured before any change, matches brief's recorded baseline exactly):
  suite `Ran 4130 tests` / OK (expected failures=4); `ruff check .` clean; corpus
  `--verify --strict-prose` `OK: no differences` at 6401/61; 3 fitness checks pass; 8
  entry points load.
- After all edits: suite `Ran 4130 tests` / OK (expected failures=4) -- unchanged count.
  `ruff check .` -- All checks passed. `ruff format .` -- 200 files unchanged.
- Corpus: `OK: no differences` at 6401 in-process / 61 end-to-end -- unchanged from
  baseline.
- **Calibration** (step 12): planted `_DEFAULT_NO_MATCH_FALLBACK = DECISION_ALLOW` in
  `toolguard/config.py` (was `DECISION_ASK`) -- corpus `--verify` correctly FAILED (2
  E2E hard mismatches + 2 tracked prose differences). Reverted the one-line change,
  confirmed `git diff toolguard/config.py` shows only the intentional Phase 7 comment
  edits (no calibration leftover), re-ran `--verify` -- `OK: no differences` again.
  Instrument proven sensitive before trusting the null result.
- 3 architecture fitness checks (`--stdlib`, `--ambient`, `--layers`): all exit 0,
  identical output to baseline.
- 8 console entry points (`toolguard.hook`, `.session_start`, `.update_check`,
  `.tools.security_audit`, `.tools.maintenance`, `.tools.installer`,
  `.scripts.migrate_permissions`, `.tools.update_skills`): all import cleanly.

### Sibling sweep (step 14)

- Checked whether any OTHER doc needed the division-of-labour frame or pointer:
  `docs/agent-guides.md` already points to auto-mode.md from its "Ground rules (read
  first)" section (the page AI agents are told to read first per README) -- no change
  needed, it now inherits the new frame automatically.
- Checked `docs/security.md`'s auto-mode-adjacent claim (ASK is a real prompt, not
  bypassed in auto-mode) against the same native-docs fetch -- confirmed still TRUE
  (permission-modes doc: hook/ask-rule-forced prompts still show in auto mode). Not a
  finding, a confirming cross-check.
- Grepped the whole codebase (not just the diff) for leftover `fallback_kind` (the
  renamed field, distinct from the deleted `fallback_kind_for_reason` function) --
  none found outside the already-handled R3/test references.
- Grepped for any pre-existing "additionalContext is the only enrichment key"-style
  claim that Phase 2/3's new `auto_mode_behavior`/`program_source` keys might have
  falsified -- none found.
- **Result: no additional doc or comment found that needed fixing beyond what's listed
  above.**

### Deviations from the brief

None. All 14 steps completed as specified. The R3_SANCTIONED_SITES comment fix is the
one item that went slightly beyond the strict "diff scope" boundary, but the brief
explicitly authorized it as a bounded, named exception, and it falls squarely under the
brief's own widening clause (b) for a found-false doc statement.

### Files changed (29 total, all uncommitted)

Docs (6): `README.md`, `docs/agent-map.md`, `docs/auto-mode.md`, `docs/configuration.md`,
`docs/quickstart.md`, `docs/takeover-mode.md`.

Production code (13): `toolguard/auto_mode_trace.py`, `config.py`, `config_types.py`,
`constants.py`, `hook.py`, `invocation.py`, `parser/command_extractor.py`,
`permission_resolution.py`, `resolve.py`, `rule_entry.py`, `session_start.py`,
`tools/takeover_audit.py`, `tools/architecture_fitness.py`.

Tests (8): `test/unit/test_architecture.py`, `test_classify_program_source.py`,
`test_configuration.py`, `test_hook.py`, `test_permission_resolution.py`,
`test_resolve.py`, `test_rule_entry.py`, `test_tools_takeover_audit.py`.

Memory (2, not part of the code change): task-recall note (this session's prepend),
`TOO-28 implementation plan.md` (pre-existing modification from an earlier session,
not touched by me this session -- shows as modified in git status from before I
started; left as-is).

Untracked: `toolguard-memories/TOO-28/brief-phase67.md` (the brief itself).

Net diff: 350 insertions, 136 deletions across the 27 code/doc files (excluding
memory notes).

### Time and cost (rough estimate)

- Phase 1 (planning, brief validation, native-docs fetch, baseline measurement): ~20 min.
- Phase 6 (documentation, 7 items + link verification): ~35 min.
- Phase 7 (comment sweep, 45+ TOO-28 refs, R3 judgement, disposition table): ~50 min.
- Phase 3 (verification: suite, corpus, calibration, fitness, entry points, sibling
  sweep): ~15 min.
- Total elapsed: ~2 hours. Estimated cost (Sonnet 5, moderate context use, several
  large file reads and two big web fetches): roughly $3-5 in API-equivalent terms.

## Post-review corrections (coordinator round 2, 2026-09-07)

Coordinator caught two defects in the Phase 6 work and requested fixes before the task is
reviewable. Both addressed; suite/ruff/corpus re-verified green afterward.

### 1. `docs/auto-mode.md` conflated "auto-mode" (generic, any unattended mode) with Claude
Code's specific `auto` permission-mode value

**Material fail-silent bug**: the opening definition named `acceptEdits`/`bypassPermissions`
as examples of "auto-mode", but toolguard's `*_in_auto_mode` settings compare
`permission_mode` by exact string equality against `"auto"` only
(`config_types.py:21` `AUTO_PERMISSION_MODE = "auto"`; checked at `hook.py:1100`,
`permission_resolution.py:479`/`490` -- all verified). A reader in `acceptEdits` or
`bypassPermissions` who followed the page's own recommendation
(`no_match_fallback_in_auto_mode = "allow_with_warning"`) would see it never fire; their
unattended run stalls on `ask` with nothing explaining why.

Re-fetched `https://code.claude.com/docs/en/permission-modes` (2026-09-07) and confirmed:
six distinct mode values (`default`, `acceptEdits`, `plan`, `auto`, `dontAsk`,
`bypassPermissions`), only `auto` has the classifier.

**Fixed**: `docs/auto-mode.md`'s opening now names `auto` specifically as one of six modes,
states the `_in_auto_mode` settings key on that exact value, and adds a dedicated paragraph
for `acceptEdits`/`dontAsk`/`bypassPermissions` telling the reader the BASE
`no_match_fallback`/`undecidable_fallback` settings govern there instead. The
Division-of-labour section's opening sentence was also tightened ("Once Claude Code enters
`auto` mode" rather than "Once Claude Code stops prompting on its own") since the classifier
only exists in `auto`. Also fixed the same conflation in `docs/agent-map.md`'s Modes Q&A
(rewrote the "auto-accept/bypass-permissions" question) and `README.md`'s doc-table row for
auto-mode.md (both were pre-existing, not introduced by me, but README's row was extended by
my own Phase-6 edit onto the same flawed premise).

**IMPORTANT OPEN QUESTION SURFACED WHILE FIXING THIS -- flagged, not resolved.** While
verifying what happens to toolguard's own `ask` decision under `acceptEdits`/`bypassPermissions`/
`dontAsk`, I got two fetches that contradict each other:
- `permission-modes.md` (fetched cleanly, consistent across two independent reads): under
  `dontAsk`, "Claude Code auto-denies every tool call that would otherwise prompt you...
  only actions matching your `permissions.allow` rules, read-only Bash commands, and calls
  approved by a PreToolUse hook" run -- implying an unapproved (`ask`) hook decision under
  `dontAsk` results in DENY.
- A second, anchor-targeted fetch of `docs/en/hooks#pretooluse-decision-control` returned a
  table claiming: *"In `bypassPermissions`, `acceptEdits`, or `dontAsk` modes, `"ask"` is
  ignored and the call proceeds as if the hook had made no decision."* This DIRECTLY
  CONTRADICTS the `dontAsk` behavior just confirmed from the primary page, and a follow-up
  fetch asking only for the page's own heading list showed NO "PreToolUse Decision Control"
  heading exists on `docs/en/hooks` at all -- strong evidence the second fetch's "verbatim
  quote" was fabricated/hallucinated by the summarizing model, not real page content.

  Given the contradiction and the missing heading, I did NOT trust the second fetch. I
  revised my own new doc language to stop asserting what Claude Code does with toolguard's
  `ask` under `acceptEdits`/`bypassPermissions` (removed a "stalls" claim I had written),
  keeping only what I could verify (the `_in_auto_mode` settings don't apply; `dontAsk`
  auto-denies an unapproved call) and added an explicit "not verified here" sentence in
  `docs/auto-mode.md`'s opening.

  **I did NOT touch `docs/security.md`'s pre-existing claim** ("Claude Code's unattended
  modes do not bypass [toolguard's ASK] -- the command still stops and waits") because I
  have no confirmed replacement fact, only an unresolved contradiction. That claim was
  already in the repo before this ticket; my earlier confirmation of it (recorded further up
  in this note) rested on a quote about `auto` mode's UI specifically
  (permission-modes.md:144, "doesn't add the option to prompts forced by... a hook, because
  auto mode still shows you those prompts"), which does not generalize to
  `acceptEdits`/`bypassPermissions`/`dontAsk` the way I originally assumed. **This is a
  genuine, unresolved, security-relevant open question** -- if toolguard's `ask` verdict is
  in fact ignored under `bypassPermissions`/`acceptEdits` (as the suspect second fetch
  claimed), that would mean toolguard's fallback protection is silently inert in exactly the
  modes people run for full automation, which is the project's most-measured failure class.
  It needs a dedicated, behavioral verification (a live hook test under each mode), not
  another doc fetch -- recommending a follow-up ticket rather than resolving it here.

### 2. `docs/takeover-mode.md`'s blockquote was reflowed, not verbatim

The five-bullet native-docs passage had been rendered as prose joined with commas/"and" and
an ellipsis. Per `.claude/rules/native-fidelity-claims.md` (both of this repo's prior
native-fidelity failures came from a quote trimmed or reflowed), rewrote it as the actual
lead-in sentence, five bullets, and closing sentence, matching the source structure exactly.
Also tightened the surrounding `bypassPermissions` sentence to match the verified fact
precisely ("allow rules have no effect" rather than my own paraphrase "not evaluated at
all"), and added the "deny rules block in every mode, including `bypassPermissions`"
qualifier the coordinator surfaced, since it's a real, relevant correction to the CRITICAL
warning's edge case.

### Re-verification after corrections

Doc-link checker: 353 internal links across the 6 touched files, all resolve (no anchors
broken by the edits). `ruff check .` / `ruff format --check .`: clean (no `.py` files
touched in this round). Suite: `Ran 4130 tests` / OK (expected failures=4) -- unchanged.
Corpus `--verify --strict-prose`: `OK: no differences` at 6401/61 -- unchanged. All match
the pre-correction state, as expected for a docs-only change.

## Post-review corrections round 3 (coordinator, 2026-09-07)

Coordinator independently re-fetched the hooks page and confirmed the second fetch from
round 2 was fabricated (no such table/section exists; real headings listed and match none of
it) -- confirming my decision to distrust it was correct. Coordinator then supplied verbatim,
dated (2026-09-07) quotes from `permissions.md`/`permission-modes.md` resolving the three
modes DIFFERENTLY from each other:

- **`auto`**: binds, explicit citation ("Claude Code doesn't add the option to prompts forced
  by one of your `ask` rules or by a hook, because auto mode still shows you those prompts").
- **`acceptEdits`**: prompting is not disabled in general -- only file edits + a named
  filesystem-command set auto-approve; "all other Bash commands except the built-in
  read-only set still prompt." A hook-forced `ask` almost certainly still holds. Should not
  be lumped with `bypassPermissions`.
- **`dontAsk`**: auto-denies rather than prompts when a hook has not explicitly approved
  (already had this right).
- **`bypassPermissions`**: the one genuinely in doubt. "Disables permission prompts and
  safety checks so tool calls execute immediately," and its one documented
  actions-no-mode-auto-approves exceptions list names a native `ask` RULE and a
  `PreToolUse` hook's `"allow"` explicitly -- but never a hook-forced prompt, despite the
  list clearly contemplating hooks. Well-evidenced that toolguard's ASK does NOT bind there;
  not proven, needs a live behavioural test (coordinator taking this to Arnon as a follow-up
  ticket).

**Fixed `docs/auto-mode.md`**: replaced the single "not verified for
`acceptEdits`/`bypassPermissions`" hedge with the four-way per-mode breakdown above, keeping
"not behaviourally verified" scoped to `bypassPermissions` only.

**Fixed `docs/security.md:260-275`** -- the real finding: this blockquote asserted "Claude
Code's unattended modes do not bypass [toolguard's ASK]" unqualified, inside the page's core
safety story for a broken-config parse failure (a `[hard_deny]` lost to a TOML syntax error
"degrades to blocked-pending-an-answer, not allowed"). Per the evidence above, that guarantee
is undocumented for `bypassPermissions` and the evidence runs the other way -- meaning, read
plainly, a `[hard_deny]` lost to a syntax error while running `bypassPermissions` could
degrade all the way to a SILENT ALLOW, in precisely the mode people run inside containers
because they are not watching. This is the fail-open-and-say-nothing shape the project's own
rules describe as its most-measured failure class, sitting in the paragraph that promised it
could not happen.

Rewrote the blockquote to: scope the strong "stops and waits" guarantee to `auto` (+
`acceptEdits`, which does not disable prompting) with its citation; state `dontAsk` denies
rather than stalls; state plainly for `bypassPermissions` that the guarantee is NOT
documented and the evidence runs against it, not behaviourally verified, with a pointer to
`auto-mode.md`'s fuller breakdown; kept the two existing habits (declare `[hard_deny]` at
user level; treat the broken-config warning as stop-work) since they are good advice under
either answer, and extended the second habit's framing to flag `bypassPermissions`
specifically. Did NOT swap one unqualified claim for a different unqualified one -- the
guarantee is stated as holding where documented (`auto`/`acceptEdits`), fail-closed-but-not-
a-stall for `dontAsk`, and in doubt for `bypassPermissions`.

### Re-verification after round-3 corrections

Doc-link checker: 402 internal links across the 7 touched files (added `security.md` to the
checked set), all resolve. `ruff check .`/`ruff format --check .`: clean (no `.py` files
touched). Suite: `Ran 4130 tests` / OK (expected failures=4) -- unchanged. Corpus
`--verify --strict-prose`: `OK: no differences` at 6401/61 -- unchanged.
