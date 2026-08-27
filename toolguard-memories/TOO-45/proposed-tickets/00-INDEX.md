---
title: TOO-45 proposed tickets — index, numbering collisions, and true status
tags:
- TOO-45
- index
permalink: toolguard/too-45/proposed-tickets/00-index
---

# TOO-45 proposed tickets — index and true status

Built 2026-08-12 because the numbering collided three times and, more seriously, **several `**Status:**` lines are stale in the misleading direction** — they say "deferred, awaiting your call" for work that is committed. Status is read at exactly the moment someone decides what to do next, so a stale one is worse than none.

**Every status line inside an individual ticket predates this file. Where they disagree, this file wins** — it is reconciled against `git log --grep=TOO-45`.

## Done — committed, regardless of what the ticket file says

| ticket | commit | the ticket's own status line | true |
|---|---|---|---|
| `01-once-per-session-warnings` | `e3da420` Item 01 | *"deferred from TOO-45, needs a design decision"* | **STALE — DONE** |
| `03-permission-resolution-resolve-cycle` | `19299d9` Item 03 | *"deferred from TOO-45"* | **STALE — DONE** |
| `04-error-reporter-and-config-layer-stderr` | `ee9aa94` Item 04 | "ACCEPTED, in scope" | **DONE** |
| `05-remove-tools-decision-shim` | `dbdd797` Item 05 | *"deferred, awaiting your call"* | **STALE — DONE** |
| `10-tool-as-a-described-thing` | `2113d02` Item 10 | *"deferred from TOO-45"* | **STALE — DONE** |
| `resolved/14-hook-error-paths-fail-open` | `ee9aa94` + the #04 addendum | *"needs Arnon's decision on when, not whether"* | **STALE — DONE**, moved to `resolved/` 2026-08-19 (fail-open fixed, hook's 9 stderr sites routed) |
| `resolved/15-migrate-needs-its-own-cross-process-lock` | `caa83e7` Item 15 | "ACCEPTED for TOO-45" | **DONE**, moved to `resolved/` 2026-08-19 |

## The three numbering collisions, resolved

**`04` — a pair, and it is already documented.** `04-error-reporter-and-config-layer-stderr.md` supersedes `04-config-layer-stderr-consolidation.md` and merges proposed #04 into the core of proposed #14 (Arnon, 2026-08-09). `14-toolguard-error-reporter.md` was deliberately **retained** for its measurements and for the parts left out of the merge. Nothing to decide.

**`14` — a pair.** `14-toolguard-error-reporter` folded into `04` above; `14-hook-error-paths-fail-open` was closed by the #04 addendum and moved to `resolved/`. **Correction, 2026-08-19 audit:** `14-toolguard-error-reporter` is only partially done — the reporter is built, but the takeover notice still writes straight to stderr (`toolguard/session_warnings.py:27,33`); see its status line.

**`15` — a group of three, and it is one chain, not three tickets.** Read in this order:

1. `15-migrate-has-no-cross-process-lock` — **the discovery**, 2026-08-08, out of #01's adversarial review. Its diagnosis was later **narrowed**: it blamed `claim()` failing open under a persistently broken store, and the implementable ticket found the sharper truth — `auto_migrate` is already serialised by #01's daily claim, and the genuinely unguarded caller is the CLI path `toolguard/scripts/migrate_permissions.py`. Superseded on the analysis; keep for the history.
2. `15-once-per-period-cannot-express-must-not-run` — **the reasoning**. Folded into #01's redesign; marked SUPERSEDED-ACCEPTED in its own text.
3. `15-migrate-needs-its-own-cross-process-lock` — **the implementable ticket, and the canonical one.** Committed as `caa83e7`.

**All three moved to `resolved/` 2026-08-19** — the 2026-08-19 status audit confirms `caa83e7` (`toolguard/file_lock.py:69-105`) closes the gap for all three.

**No number is duplicated among 17-27.** The collisions are confined to the 04/14/15 era, when ticket numbers and punch-list item numbers were being assigned from the same visual namespace.

## Open — genuinely awaiting a decision

| ticket | note |
|---|---|
| `02-pattern-string-join-key` | deferred, needs a design decision |
| `06-measurement-tools-keep-or-remove` | deferred at Arnon's request, for discussion before push |
| `07-doc-comment-cleanup-sweep` | **IN PROGRESS** — `toolguard/` and `tools/` complete; `test/` tier ~70 of 88 files |
| `08-literal-strings-to-constants` | deferred; global guidance carries the rule, this is the sweep of existing code |
| `09-architecture-document` | pending, punch-list #09 |
| `11-ask-floor-scope-non-bash-tools` | **security-relevant; settle by measurement.** Its own text recommends running the measurement before push regardless of what else is deferred — cheap, and the only open pre-#17 item with a plausible security consequence. **[PARTIALLY FIXED 2026-08-19 — the measurement is done and benign, one doc sentence still wrong, see ticket]** |
| `12-guard-the-audit-write-loop` | deferred |
| `13-anchor-project-root-per-session` | **Arnon: needed before RC1**, not necessarily in TOO-45. Not trivial |
| `16-toolspec-cannot-describe-a-user-declared-tool` | found by Arnon at the manual review of #10. **#10 made this look solved without solving it**. **[PARTIALLY FIXED 2026-08-19 — documented, code residual promoted to TOO-51, see ticket]** |

## Open — found by the #07 sweep, none filed to YouTrack

All eleven were found by *executing* a claim rather than reading it. 17-22 came from the `toolguard/` and `tools/` tiers; 23-27 were promoted out of the work queue on 2026-08-12 after Arnon noticed they had never been written up.

| ticket | layer | failure |
|---|---|---|
| 17 | matcher | `[native]` under-matches — deny rules that do not fire |
| 18 | matcher | DEFAULT multi-token over-matches — **live in five seeded self-permission rules**. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 19 | extractor | commands reach the shell without ever being rule-matched (3 bypasses). **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 20 | analyzer | consolidation escalates `ask` -> `allow`; `--apply` writes it. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 21 | analyzer | danger detector: 4 of 6 categories dead, 6 blanket-allow forms invisible |
| 22 | analyzer | redundancy engines report unsafe deletions as safe. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 23 | hook | **`log_crash` fail-open — the hook can exit with no decision on stdout.** Highest severity in the sweep. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 24 | writer | `rule_sort` can render a config that no longer parses (bricks it to permanent `ask`); and comments silently re-attribute after a sort. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 25 | config | a newline makes a **deny** rule inert — accepted, displayed as configured, matching nothing. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 26 | diagnostics | `TOOLGUARD_LOG_DIR` silently disables the conflict nag forever. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 27 | config | cache returns stale data after an equal-length, same-mtime rewrite. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 28 | audit tools | **severity ordering is unpinned in every test that claims to pin it** — three modules, mutation-confirmed. The first finding in this sweep that exists *only* as a synthesis across files. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 29 | dev instrument | `run_guard` reports `ok=True` with **zero cases checked** when `GUARD_CANARIES` is empty — a guard whose no-op state is indistinguishable from success. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 30 | dev instrument | the pyscn parse-failure guard covers only `toolguard/`; three unguarded three-name `except` clauses sit outside it, one of them in the sweep's own verification tool. Low severity. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 31 | test suite | **the sweep's largest quantitative finding** — ~65 assertions that cannot fail (22-shape catalogue) and ~50 mechanisms with zero detection. A decision about triage and a stopping rule, **not** a work order to fix 65 tests. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 32 | committed code | **eight defects in already-reviewed punch-list code**, from the architecture-judge back-test. **Two marked "fix before push"** and queued since 2026-08-10. **[PARTIALLY FIXED 2026-08-19 — both "fix before push" items still open, see ticket]** |
| 33 | mixed | the code-level residue #07 deliberately did not fix. Includes **code and comments actively contradicting each other** in `config.py`, and a user-facing string that tells the user the opposite of what happened. **[PARTIALLY FIXED 2026-08-19 — the headline contradiction is still live, see ticket]** |

### How 31-33 came to exist

All three were promoted on 2026-08-12 after Arnon asked whether the sweep's biggest findings had tickets. They did not — they were in `reports/follow-up-queue.md` and the #07 work queue, which are **my** working notes, not his decision surface. Ticket 32 had been sitting there since 08-10 **with two items marked "fix before push."**

This is the second time in this ticket that the largest findings were left in a working queue. The standing rule now at the top of the #07 work queue: **a product defect recorded only in the queue is a defect that will never be actioned — promote it the same day, incomplete if necessary.**

**Scheduling note**: 20 and 22 are downstream of 18 — fixing the matcher moves their answers, so they want scheduling together rather than separately.

## 34-76 — filed after this index was built, 2026-08-12 to 08-14

**This index was 43 tickets stale, which is the defect it exists to prevent.** Navigation only — **`DECISIONS-PENDING.md` is the authority** on ranking and on what needs Arnon. **He has read through #52; 53-76 are unread.**

**Every ticket from 34 on has at least one RED test asserting correct behaviour**, so phase 2 has a definition of done and none of them can be closed by argument alone.

| # | one line |
|---|---|
| 34 | nested backtick substitution is never descended into, so an inner command is never rule-matched |
| 35 | the hard-deny test class re-implemented production's ordering, so it detected nothing. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 36 | **a disclosure comment can make toolguard reject the command it describes** |
| 37 | the installer reports "already present, no changes needed" having seeded zero. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 38 | `fallback_kind` re-derived by substring-matching the program's own prose |
| 39 | the write guard's content-loss check is placement-blind — a hard deny moved into an allow passes. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 40 | `verify_config_text` accepts any JSON, so a verified write can overwrite `settings.json`. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 41 | a leading token or absolute path escapes the self-integrity hard-deny (`sudo rm -rf ~/.toolguard` is `ask`). **[FIXED 2026-08-19, moved to `resolved/`]** |
| 42 | `normalize_entry` returns `(None, error)` and **seven** call sites discard the error |
| 43 | inert mocks from by-value imports — five shapes; **the repo-wide sweep was run and found nothing actionable**. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 44 | ambient state read at point of use — 485 patches, 0 autospec. **The wrapper refactor, first code change after green** |
| 45 | detecting inert mocks — three mechanisms |
| 46 | a `settings.local.json` holding a JSON array crashes the divergence check. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 47 | `TakeoverConfig`'s 4th positional is `no_match_fallback`, so the stock construction misassigns |
| 48 | **a dangling symlink evades a deny written against its target, and writing through it creates the target**. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 49 | takeover silently replaces a configured `deny` fallback with `ask`. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 50 | two ways SessionStart shows the user nothing at all. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 51 | **4.3% of audit-log Command fields cannot be parsed back**; heredocs hit hardest. **[FIXED 2026-08-19, moved to `resolved/` — re-measured loss rate is 4.84%, and loss is now loud rather than silent]** |
| 52 | **a wrong-typed `[[permissions]]` section is discarded silently** — no parse failure, no warning. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 53 | auto-migration reports "Successfully migrated 1 pattern(s)" for a run that wrote nothing. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 54 | `discover_config_files` double-counts when the project root is home. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 55 | four sites assume parsed JSON is a `dict`; one guard at the boundary fixes all four. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 56 | the security audit iterates `BUILTIN_TOOLS`, so a governed MCP tool is never examined |
| 57 | **maintenance `--apply` could enact a widening, and hands a `#NOSECURITY`-withheld rule to the writer anyway**. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 58 | `apply_proposals` rewrites a file then raises, losing the report. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 59 | `per_layer_rules` drops every native `ask`, so no analyzer sees one. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 60 | the auto-migration gate had zero detection across the whole suite. **[FIXED 2026-08-19, moved to `resolved/` — the gate was already intact; it was a test coverage gap]** |
| 61 | the takeover audit stays silent on a loose fallback and cries wolf elsewhere. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 62 | the log-entry heading is a writer/reader contract written twice as literals. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 63 | the canonical protection set denies **Write** but not **Edit** of your SSH and AWS credentials. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 64 | a project ledger claiming `level=user` redirects the next write into your home; `record_decision` is unlocked. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 65 | **every MCP-terminal decision could lose reason, matched rule and provenance — and hard-deny could stop applying**. **[FIXED 2026-08-19, moved to `resolved/` — was test blindness, production was never broken]** |
| 66 | the architecture fitness tool passes over an empty tree and cannot see a loosened map; **ticket 30's fix is reverted by `ruff format`**. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 67 | **wrapping foreign inline code in `if` or `while` defeats the ASK floor entirely**. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 68 | the file-path hard-deny discards its deciding pattern, on a false premise about the corpus. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 69 | **the self-permission and uninstall tables could grant `Bash(*)` with a green suite**. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 70 | applying an edit drops the parse-failure safety floor; the as-if-enacted audit is cleaner than reality. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 71 | two warnings that contradict what happened — a spurious `governed_tools` complaint on the default config |
| 72 | the staleness banner can cry wolf, and cannot see a change to `bash_parser.peg`. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 73 | **the corpus-replay safety evidence is strongest exactly when it is emptiest**. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 74 | item 10's conversion stopped at the hook; an empty registry silently disables hard-deny |
| 75 | **`mining` hand-rolls bash tokenization, and every command carrying a mandated disclosure comment buckets under `#`**. **[PARTIALLY FIXED 2026-08-19 — see ticket]** |
| 76 | an annotation is written above every rule sharing its line text, so a deny gets a note claiming it shadows itself. **[FIXED 2026-08-19, moved to `resolved/`]** |
| 77 | **`FOO=1 rm -rf /tmp/x` evades a `deny Bash(rm:*)` rule** — nothing is stripped before matching, and the same gap costs every `TG_INTENT=1` disclosed command its allow rule |
| 78 | **an absolute-spelled deny rule never fires on a `~`-spelled command** — `normalize_path` collapses toward `~` but never expands it, so matching is asymmetric. Pre-existing at HEAD |
| 79 | `$(python -c ...)` runs foreign code with no ASK floor — **and the verdict corpus is structurally blind to floor changes**, so "no verdict changed" is not the evidence it reads as |
| 80 | **`Path("rel").resolve()` is a fifth route to cwd**, invisible to a `Path.cwd` patch — same shape as the `expanduser` hole ticket 44 closed, which was reaching the developer's REAL home under a patched `Path.home` |
| 81 | the `--ambient` check is **module-granular for `resolve()`** — AST cannot prove a receiver absolute, so a new relative `resolve()` in an already-listed module is invisible. A runtime sentinel, in the shape of `_real_log_dir_guard`, is what closes it |
| 82 | **`sudo rm -rf /tmp/x` evades `deny Bash(rm:*)`**, and so does `env` — not the same family as the scheduling wrappers, and the allow side must never strip them |
| 83 | **`deny Read([native]~/.ssh/*)` is evaded by the absolute spelling** — ticket 78's mirror image on the file-path side, which is why narrowing 78 to Bash left it standing |
| 84 | **a `[regex]` deny rule ending in escaped whitespace silently never fires** — `.strip()` leaves a dangling backslash, `re.error` is swallowed as a non-match |

**Numbering note**: 34-76 are sequential with no collisions — the three collisions this file documents are all in 01-33.

## Keep this file current, or delete it

An index that goes stale is the defect it was written to fix. When a ticket is committed, update the row here in the same pass.
