---
title: Section C pre-deletion audit — the 29 blinded review rounds
type: note
tags:
- TOO-45
- DURABLE
permalink: toolguard/durable/section-c-audit
---

# Section C audit — 29 blinded review rounds, read file by file

**Verdict: 28 of the 29 are safe to delete. 1 must be rescued — `TOO-45/reports/review-78-round3.md`.** Two more (`review-78-round4.md`, `review-74-round1-repair.md`) are safe *only after* one line each is transcribed into an existing DURABLE document; the transcriptions are given verbatim below so no judgement is needed at deletion time.

All 29 were confirmed present and all 29 confirmed **untracked** by `git ls-files --error-unmatch` — so every deletion here is permanent, as the addendum states. Nothing in this audit was taken from `PROPOSED-DELETE-LIST.md` or the triage documents; every claim below was checked against the review files, the surviving corpus, or the live code at `9b4ff1d`.

## Method, so the null results can be judged

I read all 29 in full. For every finding that looked like it might still be open, I did three things: grepped the **post-deletion survivor set** (computed as `find toolguard-memories -name '*.md'` minus the 313 delete paths — 378 surviving files, reconciling exactly: 311 of the 313 are `.md`, the other two are `.txt`), grepped the repo's `docs/`, `technical-notes.md`, `toolguard/`, `TOO-45/proposed-tickets/` and `.claude/rules/`, and where the finding was behavioural I **re-measured it against HEAD**. Where I say something is represented elsewhere, the search term and the file that carries it are named.

The single most useful discovery about the corpus: `TOO-45/reports/` is **not** wholly on the delete list. `review-74-round1.md`, `review-78-round5.md`, `review-conclusions.md`, `follow-up-queue.md` and everything under `reports/surprise/` all survive, as does the whole of `TOO-45/proposed-tickets/` (81 tickets). That is why the section-C loss is much smaller than its size suggests: the round *before* and the round *after* usually survive, and the tickets the reviews caused were filed.

---

# RESCUE — 1 file

## `TOO-45/reports/review-78-round3.md` (18,418 bytes)

Two measured findings live only here. I re-measured both against HEAD today; **both are still true.**

### NB10 — four ordinary path spellings walk past a deny rule naming the same file

> **"NB10 — out of ticket, but it caps this fix's value.** The same deny is still walked past by three trivial neighbours of the spelling ticket 78 just closed: `allow cat ~/.ssh/../.ssh/id_rsa` / `allow cat ~/./.ssh/id_rsa` / `allow cat /home/arnon/.ssh/../.ssh/id_rsa` / `allow cat /home/arnon//.ssh/id_rsa` … Worth a ticket alongside 83; a rule author who reads 'the tilde spelling is now covered' will reasonably assume more coverage than exists."

**Where I checked:** grepped the 378 survivors plus `docs/`, `technical-notes.md` and all 81 files in `TOO-45/proposed-tickets/` for `\.\./\.ssh`, `//\.ssh`, `~/\./` and `traversal`. **Zero hits outside this file.** Tickets 78, 83, 87 and 90-92 each cover a different spelling problem; none covers `..`, `.` or `//`.

**Re-measured at HEAD** (`match_command` against the rule `cat /home/arnon/.ssh/id_rsa`):

```
True  | cat /home/arnon/.ssh/id_rsa
True  | cat ~/.ssh/id_rsa
False | cat ~/.ssh/../.ssh/id_rsa
False | cat ~/./.ssh/id_rsa
False | cat /home/arnon/.ssh/../.ssh/id_rsa
False | cat /home/arnon//.ssh/id_rsa
```

This is the class `.claude/rules/evidence-before-fixing.md` says **not** to defer: the failure is silent by construction (nobody reports a deny that did not fire), and it needs no deliberate evasion — `./` and doubled slashes are what path concatenation produces by accident. It is the reachability filter's *fix* side, not its *defer* side.

### NB6 — `pwd.getpwnam` is an ambient read that `--ambient` structurally cannot see

> **"NB6 — `_passwd_home` is a new ambient read that no existing guard can see.** The passwd database is machine state naming a home directory, but the lookup bypasses `toolguard.ambient` entirely. `tools/architecture_fitness.py --ambient` scans only `os` imports and `Path` ambient members … so `import pwd` / `pwd.getpwnam` is invisible to it and has no `PATH_AMBIENT_OWNERS` entry. `ConfigIsolationMixin` patches `Path.home` and clears `os.environ`, neither of which governs it. … a future test using a `~name` path under isolation will silently read the real machine's accounts with nothing to catch it. Suggest an owner entry plus a `pwd` arm in the fitness scan."

**Where I checked:** grepped survivors, `docs/`, `.claude/rules/` and all 81 tickets for `getpwnam` — the only surviving hit is `review-78-round5.md`, and there it appears solely as a test-patching detail ("Every new test patches `pwd.getpwnam` with a stub directory"), not as an instrument gap. Ticket 80 (`80-path-resolve-is-a-fifth-route-to-cwd.md`) names the *shape* — "a derived stdlib call that reads an ambient fact by a route the obvious patch target does not cover" — and tabulates exactly two instances (`expanduser`, closed; `resolve`, open). It does not name `pwd`.

**Re-measured at HEAD:** `toolguard/normalization.py:140` is `return pwd.getpwnam(name).pw_dir`. `grep -c pwd tools/architecture_fitness.py` returns **0** — no scan arm, no owner key, nothing. `PATH_AMBIENT_MEMBERS` is still `{"absolute", "cwd", "expanduser", "home", "resolve"}`.

This matters beyond one call site because it is the **fourth** instance of the pattern `.claude/rules/evidence-before-fixing.md` singles out as the weak spot of the whole instrument: *"`--ambient` enumeration … WEAK — and this is where three live defects escaped. `expanduser`, `resolve` and `absolute` each got through by not being on the list yet. The check was rigorous about what it had been told and blind to what nobody had declared."* Deleting this file deletes the only record of the fourth.

**Recommendation:** keep the file, and file one ticket per finding (drafts under "Anything still open" below). If Arnon prefers not to keep a whole review round, both findings must be transcribed into `intermediate/open-questions.md` **before** deletion — but the measured tables are what make them actionable, and they are 40 lines.

---

# SAFE — 26 files, each with where the content lives instead

Grouped by ticket, because the rounds supersede each other and the surviving evidence is usually the *ticket file* the round produced.

## Ticket 18 — 6 files

`review-18-round1.md`, `review-18-round2.md`, `review-18-round3.md`, `review-18-round4.md`, `review-18-round5.md`, `review-18-round6.md`

- The whole `curl` hard-deny-carve-out saga — four attempted recipes, the "1 of 8" and "1 of 16" usability measurements, the false universal *"no PATTERN carve-out is both safe and usable here"* asserted in four files — is captured in `TOO-45/proposed-tickets/88-deny-with-exception-recipe-needs-a-workable-example.md`, which reproduces the four-attempt table, the "two of those were approved by the coordinator on reasoning and refuted by measurement" finding, and the generalised rule. Checked by reading ticket 88; commit `715cdbd` says it was acted on.
- Round 6's B1 — `Bash([regex]\bcurl\b)` in a double-quoted TOML string parses **silently** to `\x08curl\x08` with `parse_failures: 0`, so certification cannot catch it — is `TOO-45/proposed-tickets/89-a-word-boundary-regex-in-double-quoted-toml-silently-goes-inert.md`. Also acted on in `715cdbd`.
- The `:*`-at-end matcher work, the widening/narrowing tables, and the hand-written `Bash(ls *)`-does-not-match-bare-`ls` divergence are in `docs/native-pattern-reference.md` rows 18 (twice) and 19 — verified present at lines 61-63 — and in `TOO-45/proposed-tickets/18-default-multitoken-prefix-over-match.md`, which carries the verbatim native quotes including the "space or end-of-string" sentence.
- Round 6 N5 (every published recipe emits a spurious `Tool "Bash" appears in permissions but is not in governed_tools list`) is `follow-up-queue.md` row **V1**, with an independent end-to-end verification and the `config_validation.py:59` root cause. Survives; checked by reading.
- Round 1 N1's replay blind spot (`no_match_fallback` masking match/no-match transitions) is the subject of a whole section of `.claude/rules/evidence-before-fixing.md` ("A corpus replay MUST compare `matched_rule`, not just the decision"), including the `\obsidian search:context *` example.
- Round 4's out-of-band instruction refusal is quoted **verbatim** at `03-out-of-band-instruction-records.md:97-101`; round 6's at `:105-109`.
- Every cost figure (47m/$5, 1h14m/$9-13, 14m/$4, 55m/$7, 35m/$6, 14m/$4-6) appears as rows B1-B6 of `02-campaign-cost-data.md`, token counts included.

## Ticket 39 — 3 files

`review-39-round1.md`, `review-39-round2.md`, `review-39-round3.md`

Every blocking finding is now **written into the shipped code**, which is the strongest possible survival. Read at HEAD:

- Round 3 B1 (a same-string move from `permissions.deny` into `hard_deny.allow` is undetected) — `_permissions_downgrade_violations`' docstring now reads *"Destination-agnostic on purpose: ending up in `permissions.allow`, in `hard_deny.allow` (a carve-out, not a restriction), or in an unrecognised sub-list toolguard's runtime does not read are all the same loss."* Fixed and documented.
- Round 3 B2 (`UnicodeDecodeError` escapes uncaught; a non-UTF-8 original is unrepairable) — `config_write_guard.py:492` now catches `UnicodeDecodeError`, and the step-3 skip enumeration says *"when its current on-disk content is not valid UTF-8 or fails to parse."*
- Round 2 B4 and its non-blocking siblings (broader-syntax carve-out, cross-file carve-out, per-file blindness) — all three are enumerated in `_hard_deny_egress_violations`' docstring: *"a `hard_deny.allow` carve-out that matches the denied pattern through broader rule syntax … is not detected, and neither is a carve-out added to a DIFFERENT config file, since `hard_deny` pools across every toolguard_hook layer at runtime but this comparison only ever sees one file."*
- Round 2's out-of-band **compliance** — the only agent in the campaign that complied — is `03-out-of-band-instruction-records.md:76` and again at `:375`, where it is called *"the single most useful thing this register establishes about the brief's power."*
- Costs: rows B7, B8 of `02`. Round 3 carries no cost line, and `02:204` correctly lists `review-39-round3` among the ten with none.

## Ticket 44 — 4 files

`review-44-redrift-guard.md`, `review-44-round4.md`, `review-44-round5.md`, `review-44-round6.md`

- Round 5's F1 (four `Path(...).expanduser()` sites bypassing the ambient binding, three of them inside `main()`) was closed inside the same ticket — round 6 measured *"there is not one `.expanduser()` call left anywhere in `toolguard/` outside `ambient.py`."*
- Round 6's blocking finding (`tools/decision_ledger.py:37`'s module-scope `USER_LEDGER_PATH = Path.home() / …`, which no binding can move) was closed by ticket 80: the constant is now `user_ledger_path()`, and `review-80-round1/2/3` reviewed that very change.
- The `test-config-isolation.md` checklist-drift findings (round 4 G.1, round 5 F3/F4, round 6 items 12-13) are **repaired in the live rule file** — read at `~/projects/dot_files/.../rules/test-config-isolation.md`: line 43 now says `ambient.cwd()` where F4 found `Path.cwd()`, and lines 98-105 carry the `patch("toolguard.ambient.` token with its own differentiated judgement bullet, which is what F3 asked for.
- The general "an instrument's stated guarantee outruns its mechanics" lesson survives in `01-claude-failure-modes-and-mitigations.md` and in `.claude/rules/evidence-before-fixing.md`'s instrument table.
- Costs: B9 (16m/$3.20), B10 (21m40s/$4). Rounds 6 and redrift-guard carry no cost line and are correctly listed in `02:204`.

## Ticket 74 — 2 files

`review-74-round1-repair.md`, `review-74-round2.md`

**Both are duplicated by `review-74-round1.md`, which is NOT on the delete list.** I verified this by reading it: its non-blocking list carries item 2 (*"The integrity condition is recorded nowhere. `main()`'s governed-verdict branch calls `_finalize_output` + `_emit_decision` + `sys.exit(0)` with no `log_command` and no reporter fault"*) — which is round 2's NB6 — plus item 5 (the asymmetric `["no file_path provided"]`), item 6 (the 98.3% clone pair, now `TOO-45/proposed-tickets/96-...`) and item 7 (`config_validation.py:59`'s hardcoded `["Bash"]`, also `follow-up-queue.md` V1).

The repair file's "all 9 `RED:` markers were stale" table is in auto-memory at `project_temporary_markers_expire_silently.md`, which opens *"Measured 2026-08-20: toolguard's test suite contained 9 `RED:` annotations. Every single one was stale … Not most. All nine."*

Out-of-band records: the repair file's refusal is `03:163`; round 2's is `03:121`, quoted as *"the only record that names a concrete harm rather than a rule violation."*

**One transcription owed before deleting `review-74-round1-repair.md`** — see the transcription block below.

## Ticket 77 — 3 files

`review-77-grammar-phase1.md`, `review-77-grammar-phase1-delta.md`, `review-77-round1.md`

- The delta review's M1 (`FOO+=1 rm -rf /` unrecognised, with a measured zero-corpus-impact one-token fix) **was taken.** `TOO-45/proposed-tickets/77-a-leading-env-assignment-evades-a-deny-rule.md:51` records it in the past tense — *"it is the same shape as the `FOO+=` gap that was closed in phase 1"* — and carries forward the residual `arr[0]=$(id) rm -rf /tmp/x` case with the reasoning for why it must be decided in the grammar and not in phase 2's Python. Ticket survives.
- Round 1's finding 8 (an unsourced claim that native strips assignments "for allow rules only") is the founding incident of `.claude/rules/native-fidelity-claims.md`, recorded there as "Ticket 77 (2026-08-19)" with the verbatim correction.
- Round 1's finding 1 (three files claiming `permissions` "sits below the parser in the layering", which `.pyscn.toml` does not say) is **fixed** — `grep -rn "below the parser\|may not import the parser" toolguard/` returns nothing at HEAD.
- The `sys.path[0]` instrument trap both grammar reviews recorded is auto-memory `project_isolation_instrument_provenance.md` and a full section of `.claude/rules/evidence-before-fixing.md`.
- Costs: B13 (33m/$5), B14 (42m/$7). `review-77-round1` carries no cost line, correctly listed in `02:204`.

## Ticket 78 — 3 of 5 files

`review-78-round1.md`, `review-78-round2.md`, `review-78-round4.md`

- Round 1's F1-F7 and round 2's B1/B2 (`~<name>` expanded via `getpass.getuser()` + `$HOME`, which a single env var inverts) were **superseded within the ticket**: round 3 measured the replacement (`pwd.getpwnam`) agreeing with `bash` term for term under `USER=root LOGNAME=root HOME=/tmp/fakehome`. `review-78-round5.md` survives and re-confirms it.
- Round 4's B1 (`echo hi >~/.ssh/authorized_keys` → **allow** while `> ~/…` → deny, on the one shape native singles out for approval) became `TOO-45/proposed-tickets/87-peg-grammar-does-not-parse-four-redirect-operators.md` and was fixed — round 5, which survives, reviews the fix and adds its own B1/B2 on the residue (`dd if=~/…`, and the ask→allow loosening on a `~` redirect target).
- Round 1's `~arnon` residue is superseded, and the general reachability point is in the global `CLAUDE.md` ("Claude does not prepend `env` to dodge a deny rule or spell a path `~arnon` to slip past `/home/arnon`").
- Round 2's N1 (isolation hole via `getpass` falling through to the passwd database under `ConfigIsolationMixin`) is recorded as the *`expanduser`* instance at `TOO-45/proposed-tickets/80-...:28`.
- Costs: B15 (13m16s/$4), B16 (2h/$9-12). Rounds 1 and 4 carry none, correctly listed in `02:204`.

**One transcription owed before deleting `review-78-round4.md`** — see below.

## Ticket 79 — 4 files

`review-79-round1.md`, `review-79-round2.md`, `review-79-round3.md`, `review-79-round4.md`

Every blocking finding was fixed and every deferred one was ticketed. Checked at HEAD:

- Round 4's blocking 1 (an allowed `deny_check_part`'s `additionalContext` silently dropped) is **fixed**: `compound.py:617` is `combined_context = _accumulate_contexts([v.additional_context for v in all_parts])`, and `all_parts` at `:483` is `(stub, *audit_part_verdicts, *deny_check_verdicts)`.
- Round 2's B2 (the outer summary re-parsing the inner summary's prose on `" -> "`) is `TOO-45/proposed-tickets/90-plain-unit-prose-still-re-parsed-by-combine-strictest.md`, with the bracket-balance table; the general lesson is a whole section of the global `CLAUDE.md` ("Prose is output, not a data structure") citing this ticket's 83% / 1,943-sub-command measurement.
- Round 3's non-blocking #1 and round 4's non-blocking #4 (a substitution's compound body matched as one PEG leaf) became `TOO-45/proposed-tickets/91-substitution-compound-body-matched-as-one-leaf.md`, and `intermediate/open-questions.md:146` carries its status as **open** with the correction about the truncated punch-list quote.
- The `audit_parts`/`deny_check_parts` structural point is `01-claude-failure-modes-and-mitigations.md` §5 and `intermediate/VERIFIED-open-questions.md` row 79 (ticket 106, decided not to do).
- Rounds 2 and 4's out-of-band refusals are `03:129` and `03:133`, the latter quoted as carrying *"the single most useful sentence in the corpus about why this shape matters at all."*
- Costs: B18 (1h25m/$15), B19 (2h05m/$11), B20 (1h59m/$9-13). Round 3 carries none, correctly listed in `02:204`.

## Ticket 80 — 3 files

`review-80-round1.md`, `review-80-round2.md`, `review-80-round3.md`

- Round 3's B1 (the `CLAUDE.md` pre-push line claiming exit 0 means no direct ambient read) is **fixed and visible in the live `CLAUDE.md`**, which now reads: *"Exit 0 does not mean nothing reads ambient state directly: owner entries exempt real reads, and an unowned `resolve()` is reported without failing. The suite asserts this too, so this is a second reading rather than the only one."* That is close to the round-3 reviewer's own suggested replacement.
- Round 2's U5 (`shutil.which` reading `PATH` outside `ambient` and undetected) is **stale**: `grep -rn shutil toolguard/` at HEAD shows no `which` call anywhere.
- The rest is prose findings on a tool that was subsequently rewritten; the enduring lesson — *a check is unambiguous exactly when it measures conformance to intent a human declared* — is the instrument table in `.claude/rules/evidence-before-fixing.md`, which is explicitly built from ticket 80's `--ambient`.
- Round 3's self-reported disclosure miss (`cat > … <<'PY'` with no `INTENT` block) is one of two in section C; the disclosure regime and its measured miss rate live in the global and project `CLAUDE.md` and in auto-memory `feedback_disclose_authored_shell.md`.
- Cost: B21 (26m/$4). Rounds 1 and 2 carry none, correctly listed in `02:204`.

---

# Transcriptions owed before deletion — 2 lines, verbatim

These are the only two facts in the 26 "safe" files that I could not find anywhere in the survivor set. Both are small enough that transcribing beats rescuing.

**Into `02-campaign-cost-data.md`, appended to row A85.** `review-74-round1-repair.md` carries a **phase-resolved** cost breakdown, which `02` records only as a `~50 min / ~$10-13` total. Phase-resolved figures are rare in this corpus (row A4 notes another case where only phases existed). Transcribe:

> A85 phase split, as reported: planning + reading the report + task memory ~10 min / ~$1.5-2; implementation (B1-B5, RED sweep, non-blocking fixes) ~25 min / ~$5-7; self-review (3 full suite runs, ruff, architecture_fitness, pyscn) ~10 min / ~$2-3, mostly tool wait; report writing ~5 min / ~$1.

**Into `intermediate/open-questions.md`, as a one-line note.** `review-78-round4.md` N7 is the only record of an uncached passwd lookup on the hook's hot path, and `_passwd_home` in `toolguard/normalization.py` still has no cache at HEAD (`grep -n "lru_cache\|cache" toolguard/normalization.py` returns nothing). Transcribe:

> `pwd.getpwnam` is uncached and runs once per `~name` token per spelling. Free against a local `/etc/passwd`; on an NSS/LDAP-backed host it is a network call inside a hook whose stated budget is tens of milliseconds, and the token count is attacker-influenced. (`review-78-round4.md` N7, 2026-08-20.)

---

# Anything still open that should be a ticket rather than a note

**Two, both from the rescued file, both re-measured at HEAD today.**

**Ticket draft A — a deny rule is walked past by `..`, `.` and `//` in the same path.** A rule naming `/home/arnon/.ssh/id_rsa` does not match `cat ~/.ssh/../.ssh/id_rsa`, `cat ~/./.ssh/id_rsa`, `cat /home/arnon/.ssh/../.ssh/id_rsa` or `cat /home/arnon//.ssh/id_rsa`. Pre-existing and orthogonal to ticket 78 — the absolute spelling behaves identically, so 78 neither caused nor worsened it. Reachable by accident, not only by evasion, which is what separates it from the `~arnon` class the project deliberately does not defend against. Sits naturally beside tickets 83 and 87. **Exposure not yet measured against the corpora** — that measurement should precede the fix, per `.claude/rules/evidence-before-fixing.md`, and the rule's own caveat applies: a false negative on a deny rule is silent forever, so a zero count would measure the observability of the bug rather than its absence.

**Ticket draft B — `pwd` is a route to the home fact that `--ambient` cannot see.** `toolguard/normalization.py:140` calls `pwd.getpwnam(name).pw_dir`. `tools/architecture_fitness.py` contains the string `pwd` zero times: no scan arm, no `OS_IMPORT_OWNERS`-style key, no `PATH_AMBIENT_OWNERS` entry, and `PATH_AMBIENT_MEMBERS` is still the five `pathlib` names. `ConfigIsolationMixin` governs neither. This is the fourth instance of the exact failure the `--ambient` row of the instrument table in `.claude/rules/evidence-before-fixing.md` is written about, and it is the strongest available argument that ticket 80's *"no reason to assume they are the last two"* was right. The fix is declarative and cheap: add `pwd` to what the scan looks for, and give `normalization` an owner entry stating why it reads it. **Note the asymmetry that makes this worth doing even though nothing is currently broken:** it is an *instrument* gap, so the reachability filter does not apply — the cost of leaving it is that the next unowned read of this kind also passes silently.

**One smaller item, offered as a note rather than a ticket.** `review-79-round2` non-blocking 2: among several denied substitutions, the compound attributes to the first match rather than preferring a `hard_deny` one, so a prompt can describe an unoverridable deny as though it were overridable. The reviewer explicitly said he would keep first-match and only prefer a hard-deny match when one is present. Decision unaffected; message only. I found no ticket for it and no surviving record, but it is a one-clause behaviour note, not a defect worth a file.

---

# UNCERTAIN — where I could not reach a confident call

**1. The fail-on-revert differential-test-strength dataset.** Nearly every one of the 29 rounds measured *how many of the new tests fail when production is reverted to base*, and reported it as a headline: 9 of 14 pass reverted (18-r1), 10 of 19 (18-r2), 20 of 24 differential (18-r3), 2 of 6 (39-r1), 4 of 7 (39-r2), 6 of 13 (39-r3), **1 of 3, not the briefed 3 of 3** (79-r1), 7 of 16 (79-r2), 8 of 18 (79-r3), 22 of 26 case rows (18-r6), 16 of 30 and 8 more (78-r3/r4). Grepping the survivors for `fail-on-revert`, `revert`, `shadow tree`, `prose share` and `churn` returns **nothing in `DURABLE/`**. `intermediate/practices-with-evidence.md` §1.2 covers mutation testing exhaustively, and fail-on-revert is arguably the same family aimed at a different target (the new tests rather than the old ones). **I cannot tell whether the counts themselves carry information beyond the practice.** What I can say is that they repeatedly caught briefs overstating a change's test coverage, which is a variant of the "tell every subagent the brief is unverified" finding (§1.3). If someone wants one sentence added to §1.2, the honest one is: *"Run the new tests against a reverted production tree and report the differential fraction; across 29 review rounds the briefed figure was wrong at least twice, once by 3× (79-r1)."*

**2. `review-44-round4` G.1's "silently inert mock" claim.** The finding says the pre-push checklist points at `patch("toolguard.config.Path.home"`, which *"if anyone wrote it, would be a silently inert mock — `config.py` no longer calls `Path.home()` at all."* Two halves check out at HEAD: `grep -c "Path.home()" toolguard/config.py` is **0**, and `test/unit/test_hierarchical.py:143` still writes exactly that patch, with the checklist (line 97 of the live rule file) still naming it. But **I believe the "inert" inference is wrong**: `mock.patch("toolguard.config.Path.home")` resolves `toolguard.config.Path` to the shared `pathlib.Path` class and patches its attribute globally, so it is equivalent to patching `pathlib.Path.home` and is not inert at all. Because the finding's premise looks incorrect to me and the residue is a stale grep target rather than a defect, I did not rescue on it — but I am not certain enough to call it a non-issue, and it is the one place where I am overriding a reviewer's conclusion.

**3. Whether the two rescued findings would survive an exposure measurement.** Neither has been counted against `featherhill/logs/`, `toolguard/logs/` or `instagram-downloader/logs/`. I did not run that count — it is the ticket's first step, not the audit's, and `.claude/rules/evidence-before-fixing.md` is explicit that the count must be taken *before* work begins and dated. I am confident the findings are **true and unrecorded**; I am not asserting they are **worth fixing**.

---

# Categories the brief asked about that came back empty

**Verbatim Arnon quotes: none.** These are blinded review reports with no user turn in them. `grep -n "Arnon"` across all 29 returns three hits, all third-person references to conventions ("not from Arnon", "If Arnon rules that…", "as Arnon"), none a quotation. This category carries no risk here.

**Out-of-band / injected-instruction incidents: all seven are already recorded verbatim.** `review-18-round4`, `review-18-round6`, `review-39-round2`, `review-74-round1-repair`, `review-74-round2`, `review-79-round2`, `review-79-round4` each appear in `03-out-of-band-instruction-records.md` with a dated heading, a line reference and the full quoted block — I read the entries at lines 76-141 and 163 and compared them against the source text. Nothing is paraphrased or truncated except where `03` itself marks the source as truncated.

**Cost figures: all present.** Every elapsed/dollar/token figure in the 29 reconciles to a row in `02-campaign-cost-data.md` (B1-B21 for the review rounds, A85 for the repair), and the nine section-C files with no cost line are exactly the ones `02:204` names. The one gap is the phase-resolved split noted in the transcription block above.

**Reviewer pushback and coordinator corrections: heavily represented, and this is the strongest thing in these files.** Almost every round has a "Where the brief conflicts with the code" section, and the corrections are substantive — the brief was wrong about a diffstat, a test count, a "comments-only" diff that changed three predicates, a "dead branch" that was reachable, a "silently fails to load" that fails loudly, a "3 of 3 differential" that was 1 of 3, and a "the working tree is otherwise clean" that was not. The *pattern* is captured in `01-claude-failure-modes-and-mitigations.md` §3 and `practices-with-evidence.md` §1.3, and in auto-memory `feedback_agent_reports_are_deltas_not_state.md`. The individual instances are not, and I judged them illustrative rather than load-bearing — the mitigation ("put *do not take my word for any of this* in every brief") is already established with its own evidence and does not need more instances to be believed.