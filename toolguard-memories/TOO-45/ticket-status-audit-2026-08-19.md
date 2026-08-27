---
title: TOO-45 proposed tickets - status audit against the working tree
tags:
- TOO-45
- audit
permalink: toolguard/too-45/ticket-status-audit-2026-08-19
---

# TOO-45 proposed tickets - status audit, 2026-08-19

**Why this exists.** Every ticket in `proposed-tickets/` was written during phase 1 or earlier. Phase 2 (`05f786d`) then fixed a large amount of production code. The review that marked many tickets "fix" was therefore reading a list that predates the fixes. This file re-checks all 72 ticket files (numbered 11-79, including the 14/15 collisions) **against the code**, not against ticket text.

**Ground facts, verified independently:**

- `git diff 05f786d -- toolguard/ test/ tools/` is **empty**. The working tree's code is byte-identical to phase 2; only `docs/` and `toolguard-memories/` moved after it. So "current status" and "phase 2 status" are the same question.
- Suite reproduced locally: **3639 tests, OK, 4 expected failures** - matching phase 2's commit message exactly.
- The four deferred tests map onto tickets: `test_compound.py:1176` -> **#34**; `test_tools_security_audit.py:1905` and `:1923` -> **#56**; `test_tools_self_permission.py:145` -> install work moved to **TOO-36**.

**Counts: 31 ALREADY FIXED · 24 PARTIALLY FIXED · 16 NOT FIXED · 1 CANNOT DETERMINE.**

Where a ticket stated a measurable claim, it was re-measured. Several ticket bodies proved wrong; those are called out.

## ALREADY FIXED - the actionable part

These 31 no longer describe a live defect. Their own `Status:` lines are stale.

| # | Subject | Evidence | Note |
|---|---|---|---|
| 14-hook-error-paths-fail-open | Hook error paths fail open | `ee9aa94`; pinned `test/unit/test_hook_error_reporter.py:452` | Deny now on stdout with `additionalContext` |
| 15-migrate-has-no-cross-process-lock | migrate has no lock (superseded) | `caa83e7`; `toolguard/file_lock.py` | Superseded by the implementable 15 |
| 15-migrate-needs-its-own-cross-process-lock | migrate needs its own lock | `toolguard/file_lock.py:69-105`; `test/unit/test_file_lock.py` | flock/msvcrt, per-project lockfile |
| 15-once-per-period-cannot-express-must-not-run | once-per-period semantics | `toolguard/once_per.py`, `once_per_store.py` | Design ticket, self-declared closed |
| 23 | `log_crash` fail-open, hook emits no decision | `toolguard/error_log.py:145-148`; `test/unit/test_hook.py:3203` | Highest severity in the #07 sweep. `Path.home()` moved inside the try |
| 24 | rule_sort bricks a config / migrates comments | `toolguard/rule_sort.py:104-130`, `:558-570`; `toolguard/tools/annotate.py:31-37` | **Both parts fixed, but by the mechanism Arnon rejected - see Surprises** |
| 25 | A newline makes a deny rule inert | `toolguard/rule_entry.py:358-367` | Error-level Issue, entry rejected. Tests at `test_rule_entry.py:312,331` |
| 26 | session_start scans the wrong log dir | `toolguard/session_start.py:288-293`; `test_session_start.py:793` | Resolves via `env_config` |
| 27 | Config cache stale on equal-length rewrite | `toolguard/config.py:176-186`; `test_toml_config.py:294` | Key now includes a sha256 of the bytes |
| 28 | Audit severity ordering unpinned | `test_tools_danger.py:225,250,268`; `test_tools_security_audit.py:780` | Cosmetic residual: `f.tool` tiebreak still unobservable |
| 29 | run_guard reports ok with zero cases | `tools/architecture_fitness.py:3251-3260` | Empty canary set is now a mismatch, not a skip |
| 30 | pyscn parse guard misses tools/ and test/ | `test/unit/test_static_analysis_coverage.py:66,139` | Stronger than asked: AST scan over all tracked `.py`. **The "ruff reverts this" memory is stale** - the magic-trailing-comma form survives `ruff format` |
| 35 | Hard-deny tests tested themselves | `test/unit/test_hard_deny.py:340-345` (`bdb7c95`) | Tests now drive production's entry point. Residual: dead guard `permissions.py:247` |
| 41 | Leading token / absolute path escapes self-integrity | `toolguard/tools/self_integrity.py:46,57` (`05f786d`) | `^rm\b` -> `(^\|[\s/])rm\b`. 21-variant probe all deny |
| 43 | Inert mocks from by-value imports | `test/unit/test_auto_migrate.py` now has 1 `patch(` | Nine inert mocks gone; ticket self-retracts its recommendation |
| 46 | Non-object JSON crashes divergence check | `toolguard/config_divergence.py:45-46` | Verified end-to-end through the real hook |
| 48 | Dangling symlink evades a deny on its target | `toolguard/normalization.py:16-28,85-91` | Includes the "strictly worse sibling" |
| 49 | has_any_rules reads the filtered view | `toolguard/config.py:1185-1194` | Takeover no longer overrides a configured fallback |
| 50 | SessionStart can silently show nothing | `toolguard/session_start.py:392`, `:65` | Both defects |
| 51 | Multi-line commands unrecoverable in the audit log | `toolguard/log_writer.py:257,318`; `log_harvest.py:224,232` | Re-measured: historical loss rate 4.84% (ticket said 4.3%, understated). **Loss is now loud, not silent** |
| 54 | discover_config_files double-counts at home | `toolguard/config.py:269` | Pinned test present |
| 55 | Non-object JSON at four sites | `config_write_guard.py:125`, `config_divergence.py:45`, `session_start.py:65`, `install_update.py:115` | **All 4 behaviourally fixed; the single-boundary refactor was declined.** Close as "behaviour fixed, refactor declined" |
| 58 | apply_proposals rewrites then raises | `toolguard/tools/rule_apply.py:329-346` | Both defects; confirmed by live dry-run and real-run probe |
| 59 | per_layer_rules drops native ask | `toolguard/tools/config_access.py:118-123` | Plus the Provenance-collapse hazard |
| 60 | Auto-migration gate had zero detection | gate `toolguard/hook.py:908`; `test_hook_eval.py:784` | Was a coverage gap; gate was intact |
| 63 | Protection set covers Write but not Edit | `toolguard/tools/recommended_protections.py:40` | 24 patterns; probe denies all 11 named paths on Read/Write/Edit. **Doc-sync caveat - see Surprises** |
| 65 | MCP-terminal decisions lose provenance | `test/unit/test_api.py:963` | Test blindness closed; production was never broken |
| 67 | `if`/`while` defeats the foreign-code ASK floor | `toolguard/parser/command_extractor.py:513-527` | Verified: bare and `if`-wrapped both floor. No grammar change needed |
| 68 | File-path hard-deny discards its deciding pattern | `toolguard/resolve.py:105` | `matched_rule=hard.matched_pattern`; all 4 file-tool goldens now attributed |
| 69 | Self-permission table could grant `Bash(*)` | mutation probe: 4/36/76 failures, all DETECTED | Blindness closed. One decision still deferred to TOO-36 |
| 76 | Annotation written above every rule sharing line text | `toolguard/tools/annotate.py:103-121` | Index is allow-only, rationale documented inline |

## PARTIALLY FIXED - name the half

| # | Subject | Fixed | Still live |
|---|---|---|---|
| 11 | ASK floor scope on non-Bash tools | **The measurement, and the answer is benign**: floor applies to Bash and MCP terminal alike, by construction (`toolguard/api.py:68-72`). Test `test_ask_resolution.py:390`, added `bdb7c95`, passes | One doc sentence: `docs/configuration.md:507` still says "Bash-only" |
| 14-toolguard-error-reporter | Error reporter | Reporter built (`toolguard/error_reporter.py`); symptom 1 pinned | Takeover notice still writes straight to stderr, `session_warnings.py:27,33` |
| 16 | ToolSpec cannot describe a user-declared tool | Documentation `docs/configuration.md:186-212` | Code residual `hook.py:1130`; promoted to TOO-51 |
| 18 | DEFAULT multi-token prefix over-match | Token-boundary matcher `permissions.py:81-93,203`; 5 seeded uninstall rules rewritten exact | Mid-pattern `git:* push`; any-colon split `curl http://ex.com/*` |
| 19 | Compound splitter bypasses | P1 (`command_extractor.py:513-528`), P6-awk | P2-P5 all reproduce - `toolguard/parser/multiline.py` untouched by phase 2 |
| 20 | Consolidation safety claims are false | Section 5 only (side effect of #18) | Sections 1-4 reproduce; docstrings corrected over unchanged code. Sharpest: `consolidate.py:597` gates on `broadened_count` alone |
| 22 | Redundancy analyzers call unsafe deletions safe | HR1, HR3, HR4, zero-population family, RD1 case-folding (all `hierarchy.py`) | HR2 note still says "can be dropped" (`hierarchy.py:400`); RD1 space-collapsing; RD2 provenance (`redundancy.py:197`) |
| 31 | Suite blindness measured | Wave 1 committed (5 modules) | Tier 3 (~70 modules) not started. The ~65 figure is inflated per the ticket's own correction |
| 32 | Eight defects in committed punch-list code | **2 of 8**: item 8 (`COMMAND_TOOLS` gone, already stale when filed), item 7 partial | **6 of 8, including BOTH "fix before push" items** - see below |
| 33 | Code-level residue from the #07 sweep | Only section 2 (takeover string, `session_warnings.py:7-9`) | **Headline defect live** - see below. Plus sections 3-7 |
| 37 | Installer reports success seeding zero | `cmd_seed_self_perms` guarded, `installer.py:799-804` | `cmd_seed_hard_deny` unguarded, `:1675-1689` |
| 39 | Write-guard loss check is placement-blind | Hard-deny egress check `config_write_guard.py:336-352` | `deny`->`allow` and `ask`->`allow` still write successfully |
| 40 | verify_config_text is a parse check | `isinstance(parsed, dict)` at `config_write_guard.py:125-130` | Empty-string write succeeds; `expected_patterns` still iterates characters; 0644 -> 0600 |
| 52 | Wrong-typed `[[permissions]]` discarded silently | `[[permissions]]` shape at both sites (`config.py:1737`, `config_validation.py:75`) | **Bare-string `allow = "Bash(ls:*)"` still lost** - `config.py:1733` iterates the string's characters, so the new guard never sees it. 9 char-level warnings, no error |
| 53 | Auto-migration announces a count nothing produced | Symptom, `auto_migrate.py:145` | Root: `migrate()` still returns a countless `MigrationOutcome` |
| 57 | Maintenance --apply broadening / NOSECURITY | The one genuinely RED item (misspelled `--tool`), `maintenance.py:1296-1303` | Holes 1 and 2 got no production change - they were already correct, now only test-guarded |
| 61 | Takeover audit reads the legacy alias | **Defect 1, the dangerous one**: `takeover_audit.py:394` reads the resolved fallback | Defect 2 (conflict reported only alongside a blanket allow, `:329`); defect 3 (false impact string `:371`) |
| 62 | Log heading is a contract written twice | Blindness closed, `test_logging_streams.py:108` | Shared constant not extracted (`error_log.py:95` vs `session_start.py:91`) |
| 64 | Project ledger redirects a write into home | Defect 1, `decision_ledger.py:295` (level from path, not body) | Defect 2: `record_decision` still unlocked and non-atomic, `:340-366` |
| 66 | Architecture fitness passes over nothing | (a) empty-tree guard; (c) ruff/ticket-30 form | (b) a loosened map is still invisible in production - closed only by a test pin. Plus `[architecture].enabled` parsed by nothing |
| 70 | Applying an edit drops the parse-failure floor | Main defect both parts, `config_access.py:289` | Caption-vs-enacted and unconditional double-wrapping, both live in `edit_proposal.py` (untouched by phase 2) |
| 72 | Staleness check cries wolf / misses the PEG | (a) cries wolf; unreadable-file and shadow findings | (b) `_hash_py_files` still `rglob("*.py")`, so `bash_parser.peg` changes are invisible |
| 73 | Replay evidence strongest when emptiest | `replay.py:241-242`; `corpus.py:98-99,113-118` | `replay.py` got no examined-nothing guard; `ReplayDiff` still cannot separate decided from undecidable |
| 75 | mining hand-rolls bash parsing | (a) tokenization now via `extract_commands`, `mining.py:159-183` | (b) `TG_INTENT=1 ls -la` still buckets under key `TG_INTENT=1` - same root cause as #77 |

## NOT FIXED

| # | Subject | How established |
|---|---|---|
| 12 | Guard the audit write loop | No end-to-end log-file test exists; what exists is mocked at the write boundary |
| 13 | Anchor project root per session | No session-keyed store; root still recomputed per call, `env_config.py:155-162` |
| 17 | `[native]` end-anchor false negatives | Brute-forced 7,623 pairs / 416 mismatches / 0 false positives - identical to the ticket. Now **pinned as shipped behaviour** (`test_patterns.py:440`) and documented |
| 21 | Danger analyzer coverage gaps | All of sections 1-5 reproduce. `_is_blanket_allow` returns False for `*`, `**`, `[regex]^.*`. **Phase 2 made it worse**: new `assess_pattern_risk` (`danger.py:493`) feeds `mining` from the same broken predicates |
| 34 | Nested backtick substitution not descended | Deliberate: `@unittest.expectedFailure` at `test_compound.py:1175`. Measured: `rm -rf /` never becomes a matchable part in the backtick form |
| 38 | fallback_kind re-derived from prose | `compound.py:145,154` still prose-matching; `hook.py:484` still calls it for the deny side. **Nuance**: the allow side is already structural (`UnitVerdict.fallback_kind`, added `a3e3f27`, predates the ticket). The ticket's own CORRECTION retracts its central alarm |
| 42 | normalize_entry error channel discarded | **Re-counted: 8 sites, 7 discard - identical set to `bdb7c95`.** But the ticket's damage model is unsupported: every site guards, continues or substitutes. Weaker than filed |
| 44 | Ambient state read at point of use | No `testability.py`, no `path_utils.home()`. Re-measured: `patch(` now **553** (ticket said 485), `autospec` still **0**. Open decision, correctly sequenced as the first change after green |
| 45 | Detecting inert mocks | No fitness check; methodology, unimplemented |
| 47 | TakeoverConfig positional construction | `kw_only=False` at `config_types.py:287`; `TakeoverConfig(False,(),(),"deny")` still constructs |
| 56 | Clarity checks skip non-builtin governed tools | `security_audit.py:291` still iterates `BUILTIN_TOOLS`. Both tests `@unittest.expectedFailure` - deferred pending what "governed" means |
| 71 | Two warnings contradicting what happened | `config.py:1717` seeds `governed_tools: []`, so **every default config trips the spurious warning**; `config_validation.py:59` fallback is dead code |
| 74 | Item 10's conversion stopped at the hook | (a) `_handle_command_tool` (`hook.py:1093-1099`) takes no `tool_name` and hardcodes `"command"` at `:1130`. (b) empty registry ungoverns everything (`tool_spec.py:96` -> `config.py:794` -> `hook.py:688-693`) - **LATENT, not live**, since the real registry is non-empty |
| 77 | Leading env assignment evades a deny rule | **Probed live.** Under allow `Bash(*)` + deny `Bash(rm:*)`: `rm -rf /tmp/x` denies, but `FOO=1 rm -rf /tmp/x`, `timeout 5 rm ...` and `xargs rm ...` all **allow**. Second half confirmed: `TG_INTENT=1 ls -la` loses its allow rule and falls to ask |
| 78 | Absolute-spelled rule never matches tilde-spelled command | **Probed 2x2, confirmed, and it is Bash-specific.** Absolute rule + tilde command -> **ask** instead of deny; other three combinations deny. Cause: the command is normalized (`permissions.py:23`) while the rule pattern is not, and `normalize_path` collapses toward `~` but never expands it. **File-path tools are symmetric and safe** - all four combinations deny |
| 79 | Command substitution runs foreign code with no ASK floor | **Probed with a control.** Bare inline and `if`-wrapped both floor (ask); `echo $(python -c ...)`, `PKG=$(...)` and the backtick form all **allow**. Part (b) also live: `cases.jsonl` untouched since `11d1fd0`, and no inline-code case sits at an ask tier, so the corpus cannot observe a floor change |

## CANNOT DETERMINE

| # | Subject | What is needed |
|---|---|---|
| 36 | Disclosure comments not inert to the extractor | **Not reproducible at HEAD on the hook path**: every disclosure shape probed through `multiline.extract_structured` is inert, and `TG_INTENT=1`/`TG_ATTEST_READONLY=1` decompose identically to the bare form (pinned `test_multiline_bash.py:203`). But `multiline.py` is unchanged since `d0681c0`, so this was **not fixed by TOO-45** - the original report is either mis-attributed or from a shape not hit. Needs the original reproducer. **Adjacent live finding**: the legacy `extract_commands` does not strip a trailing comment, so `ls -la # uses \`grep\`` invents a `grep` leaf - harmless on the hook path, real for `mining` and analyzers |

## #32 - the eight, individually

Both items marked "fix before push" are **still open**. Verified directly: `DECLINED_UNAVAILABLE` has **0** occurrences in `toolguard/`; `error_reporter.py:56` still declares `log_fn_name`, dispatched via `getattr` at `:147`.

1. `migrate()` collapses four `LockUnavailable` reasons - **NOT FIXED**. `permission_migration.py:1250-1262`. **"fix before push"**
2. `_dispatch` `getattr` indirection - **NOT FIXED**. `error_reporter.py:56,147`. **"fix before push"**
3. Second copy of severity routing in `hook.py` - **NOT FIXED**. `hook.py:85-92`
4. `OncePer.run` executes a config-layer closure - **NOT FIXED**. `once_per.py:119-122`
5. `is_builtin` conflates "known" with "governed by default" - **NOT FIXED**. `tool_spec.py:29,91-98`
6. `TOOLS_BY_NAME` mutable public dict - **NOT FIXED**. `tool_spec.py:84`
7. Corpus payload-key blindness - **PARTIALLY FIXED**. Sixth hardcoded copy gone (`fixture_loader.py:638-640`); in-process replay still cannot see payload-key changes
8. `hook.COMMAND_TOOLS` - **ALREADY FIXED**. Zero occurrences; removed in `2113d02`, so this sub-item was already stale when the ticket was written

## #33 - is the defect still present?

**Yes.** The headline contradiction is live, and the two statements sit ten lines apart in one function:

- `config.py:1552-1556` (comment): *"clamps every decision **except an already-'deny' one** to 'ask'"* - correct
- `config.py:1563-1568` (user-facing `corrective_steps`): *"**EVERY** toolguard permission decision is clamped to 'ask' ... including deny/hard_deny"* - **false**
- `permission_resolution.py:125` settles it: `if not parse_failures or decision == "deny": return decision, reason`
- `docs/configuration.md:461` is correct

So the disagreement is three-way, and the only wrong statement is the one an operator actually reads.

Of #33's other items: section 2 is **fixed** (`session_warnings.py:7-9`, `hook.py:851`). Sections 3 (four dead-code items), 4 (four open questions, incl. GLOB/NATIVE bypassing the newline guard at `permissions.py:156-159`), 5 (duplicated error strings, `decision_ledger.py:176` and `:265`), 6 (stale analogy `permission_migration.py:93-95`) and 7 (refactor candidates) are all **not fixed**.

## Surprises worth your attention

1. **#24 was fixed by the mechanism you explicitly ruled out.** The ticket's decision block says *"Not escaping. Emitting `\n` escapes would make multi-line `additionalContext` a supported capability ... He does not want that surface"*, and mandates replacing a newline with a single space. `rule_sort.py:104-110` implements escaping, mapping `"\n": "\\n"`. Multi-line `additionalContext` now round-trips as a working feature, and `test_rule_sort.py:779` **pins** that behaviour - so implementing your decision now requires changing a green test. The fix follows the ticket body's older "Fix direction" section, which contradicts the later decision block.

2. **Phase 2 shipped a test that failed against its own tree.** `test_the_sixteen_patterns_appear_in_order_in_docs_security_md` requires the 24 canonical patterns to appear as a contiguous run in `docs/security.md`. Replaying the test's own parsing against `05f786d:docs/security.md` shows **8 of the 24 absent** and the assertion failing. It is green today only because of the **uncommitted** `docs/security.md` edit in the working tree. If `docs/` is committed separately or reverted, that test goes red - and phase 2's "3639 tests, OK" was not true at that commit.

3. **#21 is more severe after phase 2 than before it.** Nothing in `danger.py` was fixed, and phase 2 added `assess_pattern_risk` (`:493`) feeding `mining`'s `risk_flags` from the same broken predicates - so a proposed `[native]*` or `rm -r *` allow is now reported as carrying no risk.

4. **#78 is narrower than filed, and #79's boundary is instructive.** #78 is Bash-only; file-path tools are symmetric and safe. And `if`-wrapping (#67) is fixed while command substitution (#79) is not - the two were often discussed together, but only one closed.

5. **Several tickets are now "documented, not fixed."** #20, #21 section 6, #22 section 5, #33 section 4, #72 finding 4 and #73 finding 4 all had their docstrings corrected over unchanged code. This is honest, but it means a reader diffing those modules sees heavy edits on exactly the lines the ticket quotes and may conclude the defect was addressed.

6. **Two ticket bodies were themselves wrong.** #42's damage model is unsupported at all seven surviving sites, and #32 item 8 was already stale when written. #38's own CORRECTION retracts its central alarm. #31's ~65 figure is inflated per its own correction.

## Method note

Findings were produced by nine parallel audit blocks and cross-checked; the following were additionally verified by hand against the code: #11, #24, #25, #33, #41, #52, #63, #67, #68, #74, #75, #76, #78, #79, and #32 items 1, 2 and 8. Two probes of my own were initially wrong - a #79 fixture whose allow rule never loaded, caught only by adding a control - which is the same failure mode this audit exists to catch.
