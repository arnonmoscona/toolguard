---
title: TOO-45 decisions pending Arnon
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/decisions-pending-1
---

# Decisions waiting on Arnon

**Created 2026-08-12 at his instruction: accumulate decisions, report together.** Newest section at the bottom as the campaign continues. Anything marked TAKEN is a call I already made and acted on — listed so it can be overruled, not so it can be re-litigated.

---

## COMMIT HAZARD — READ BEFORE YOU STAGE ANYTHING

**Staging only the modified files ships broken links to everyone else.**

`docs/architecture-as-built.md`, `docs/native-pattern-reference.md` and **all of `docs/diagrams/`** are **untracked** — but **tracked** files already link to them: **6 files** point at `architecture-as-built`, **2** at `native-pattern-reference`, and `architecture-as-built` embeds **17 images** from `docs/diagrams/`. Meanwhile `docs/architecture.md` is **already staged as deleted**.

**All of it has to go in one commit.** And see A14: the delete-plus-untracked pair is a rename git will not follow unless you make it one.

---

## `tools/check_doc_links.py` HAS A BLIND SPOT IN THIS PROJECT'S OWN VOCABULARY

I have been reporting *"check_doc_links passes"* as an invariant. **It passes over an unchecked subset.**

`LINK_RE` at `check_doc_links.py:42` uses `[^\]]+` for link text, which **cannot match a label containing `]`** — so any link written as `` [`[native]`](...) `` or `` [`[hard_deny]`](...) `` is **silently skipped**. Measured: **4 of 425 links skipped, and one of those four was genuinely broken.**

The vocabulary this project uses for pattern modes is exactly the vocabulary the checker cannot see. **A `.py` fix, so phase 2 and yours** — but until then the invariant is weaker than I have been saying.

---

## READ THIS SCREEN FIRST — 2026-08-14, written for a part-time day

This file is 375 lines now. **You do not need to read it end to end to act.** Here is the whole state in one screen.

**PHASE 1 IS DONE.** 77 modules, **3,628 tests**, **137 intentional reds**, production untouched, `ruff format --check` and `ruff check` clean, gate run serially. **The 137 reds are the deliverable, not a problem** — each asserts correct behaviour and fails because production is wrong, so phase 2 has a definition of done. **A green suite would mean someone weakened a test.**

**A behavioural fact from the review worth knowing regardless of the document**: **a `[hard_deny]` section in a native `settings.json` is silently ignored** (`config.py:899-902` skips `layer.is_native`), so a hard deny written there does nothing while a native *normal* deny applies. Measured, not read. If that is intended, it is undocumented; if not, it is a gap in the direction that matters.

**#09 is done on its round-2 scope too**: `docs/architecture-as-built.md` at 515 lines, `docs/architecture.md` merged and deleted, **17 of 17 inventory diagrams**, zero orphans, link checker passing, and it has been through **two blinded reviews and three correction passes**.

**Two things about it need you, both small:**

- **ANSWERED 2026-08-14: `architecture-as-built.md` is the survivor.** A14's filename question is closed. Also confirmed: **nothing in the docs links into `tmp/`** — the `/tmp/` hits are all pattern examples in prose.
- **ANSWERED 2026-08-14: diagrams display at `width="50%"`, as HTML `<img>`.** All 17 converted; invariants re-verified (0 mermaid fences, 0 markdown embeds, 17 `<img>`, every path present, link checker passing). **`style` was rejected on evidence** — it renders correctly in local previews and is stripped by GitHub's sanitizer, so it would have failed only after a push. Two throwaway test files remain in `docs/` and are yours to delete: `diagram-path-test.md` and `diagram-sizing-test.md`.
- **The delete-plus-untracked-file pair looks like a rename that was never made one.** `docs/architecture.md` is staged as deleted while `docs/architecture-as-built.md` is untracked. Nothing points at the deleted file (`check_doc_links` passes), but git will record this as a delete plus an add and **the history will not follow**. If you want the lineage kept, that is a `git mv` decision at commit time — and it interacts with **A14's open question about which filename survives**.
- **I have been quoting "zero sentences over 40 words" and that figure is splitter-dependent.** Two agents measured the same file with their own splitters and disagreed: one found 2 over 40 and called them **artifacts** (backtick spans collapsing), the other found the same 2 and called them **real long bullet items**. Median sentence (12) and the paragraph distribution are stable across both. **The prose is genuinely much better than it was — the "zero" is not a solid number**, and I should not have repeated it as one.

**What actually needs YOU, in the order I would take them:**

| #     | decision                                                                                                             | why now                                                                                                                                                                        |
| ----- | -------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **1** | **A12** — should "governed" mean *builtin* or *describable*?                                                         | It changes what reaches the corpus, the replay and every analyzer. Everything downstream of it is guesswork until you answer                                                   |
| **2** | **A14** — the `#09` document's **filename**, and a **dangling reference we created** at `toolguard/log_writer.py:22` | The dangling ref is a one-word production edit I would not make without you. **The filename is my inconsistency to own** — my brief contradicted the plan's own recommendation |
| **3** | **A11** — `toolguard-install skills-status` is invoked by a skill and never self-permitted                           | Three options, all cheap. It falls to `no_match_fallback` under takeover today                                                                                                 |
| **4** | **A13** — take the ~20-line `--stdlib` check?                                                                        | **Nothing enforces the stdlib-only rule**, and the dev venv would mask a violation. A hard constraint with no enforcement                                                      |
| **5** | **A4** — ticket 34's fix direction (descend, or treat nesting as undecidable)                                        | A live bypass sits behind it                                                                                                                                                   |

**What I would fix first if you want a ranking rather than a decision** (all have RED tests): **67** (the disclosure ASK floor is lost inside `if`/`while`), **65** (hard-deny could stop applying to MCP terminals), **48** (a dangling symlink evades a deny), **52** (`[[permissions]]` discards a section silently), **69/74** (the self-permission tables could grant `Bash(*)`; the hook bypasses the tool registry), **75** (`mining` hand-rolls bash parsing, and **every command carrying your own mandated disclosure comment buckets under `#`**).

**Two of your earlier decisions turned out incomplete, measured rather than argued:**

- **Ticket 24's fix does not reach the comment renderer** — `annotate`'s notes are generated prose that never passes through `normalize_entry`. Useful narrowing: **line breaks are the entire escaping surface**, so the minimal correct fix is line-breaks-only.
- **Ticket 30's fix direction is reverted by your own toolchain** — `ruff format` rewrites `except (A, B, C):` straight back to the bare form. Two forms survive: a **magic trailing comma**, or a **named constant**.

**Reading budget.** 24 tickets are unread (53-76). Sections A8-A15 below are the new decisions; **section B** is production observations needing disposition, not decisions; **C** is what I decided on my own and you can overrule; **D** is housekeeping.

---

## A. Blocking nothing right now, but wanted before push

### A1. Ticket 17 — ONE pin, in one file *(he said he will review manually)*

**CORRECTION 2026-08-13, my error.** I described this twice as "two agents pinned it oppositely". **That is false.** Verified by audit and by repo-wide grep:

- **`test_patterns.py`** carries the single pin: `test_native_end_anchored_pattern_under_matches_unlike_glob_and_default` asserts `assertFalse(match_pattern(NATIVE, "*id_rsa", "cat id_rsa.pub id_rsa"))`, with an inline comment saying the False is a false negative and a deny-rule bypass, pinned so ticket 17's fix cannot land silently. **Green, pinning the defect.**
- **`test_permissions.py`** contains **nothing** about it — no `id_rsa`, no end-anchor, no ticket-17 assertion.

So one agent pinned it and the other **declined to act and said so**. I read a non-action as a contradictory action. There was never a contradiction in the tree.

**The decision still stands and is unchanged in substance:** that single pin is green while asserting a known bypass. Under the three-phase plan a red test would be the consistent instrument, but Arnon reserved this one, so it is untouched.

### A2. Tier 3 — ANSWERED BY YOU, and the "mostly cosmetic" prediction was wrong

You said continue, and I have. **Ticket 31's estimate that tier 3 would be mostly cosmetic has not held up.** Tier 3 produced tickets 58-67, including the highest-severity survivor of the whole campaign (65: hard-deny could stop applying to MCP terminals with a green suite) and the ASK-floor bypass (67). The marginal find rate has **not** dropped the way I predicted — it changed *kind*, from permission-path defects to instrument-tier defects, where the failure mode is "the tool that checks correctness reports OK having checked nothing".

**No decision needed unless you want it stopped.** ~29 modules remain; the dev instruments are last and lowest value.

### A3. The `~65` figure needs re-deriving before it is quoted again
My own counting error, caught independently by two agents: *cannot fail* (vacuous) and *cannot distinguish* (load-bearing but blind to what it claims) were counted as one number. Both categories are real and need different fixes. **Decision: whether re-deriving it is worth the agent time, or whether the catalogue of shapes is the durable artifact and the total never mattered.**

### A4. Ticket 34 — nested-backtick bypass, fix direction
`rm -rf /` inside nested backticks never becomes a matchable leaf, so a deny rule cannot fire. Two options: **descend** (govern the inner command, grammar work under the two-phase rule) or **treat the nesting as undecidable** and let the ask-floor take it (cheaper, arguably safer, connects to ticket 11). One deliberate red test currently sits in the tree for this.

### A5. Ticket 32's two "fix before push" items — still unfixed
Queued since 2026-08-10, confirmed still unfixed. They were marked fix-before-push by the architecture-judge back-test, not by me.

### A6. The "clamps EVERY decision" falsehood is in TWO production sites, and is now falsified by an executing test
`config.py`'s `corrective_steps` **and** `session_start._format_summary` both tell the user a broken config clamps *every* decision to `ask`. It does not — an already-`deny` decision is exempt. Previously this was known only by reading; a wave-3 test now pins the exemption directly, so the user-facing strings are contradicted by the suite. Strings are code and the #07 sweep deliberately did not touch them. It also appears in `docs/configuration.md:460` (section D).

### A7. Ticket 11 is a DIFFERENT mechanism than I thought — my error, corrected by an agent
I briefed wave 3 as though ticket 11 concerned the TOO-19 **parse-failure** floor. It does not: ticket 11 is about the **inline/heredoc foreign-code** ASK floor (`command_extractor._detect_foreign_inline_code` / `_apply_leaf_policy`). Two different mechanisms, both called "the ask floor". **Ticket 11's open measurement is untouched by this campaign and still needs doing.**

The agent pinned something useful anyway: the parse-failure floor **does** cover `Read`/`Write`/`Edit`, which `resolve_permission_cascade`'s docstring claimed and nothing tested.

---

## B. Production observations from repair agents — dispositions needed

- **`permissions.py:133`'s `.replace("**", "*")` is a semantic no-op.** Delete, or keep and document why. Its one live effect is making an `args_pattern` branch unreachable except via three-or-more consecutive stars.
- **A production dead-guard in `permissions.py`** (`if not deny_patterns:` early return) **cannot be pinned by any test**, because the code below returns the same answer. Delete the guard, or label its test a characterization. Ticket 35.
- **`test_hierarchical.py`'s compound tests drive a legacy alias** — `compound.resolve_compound_permission`, whose own docstring says it is not on the production path. Repoint, delete, or accept.
- **Ticket 18 is live and unpinned**: `git log:*` matches `git logfoo`; `git commit:*` matches `git commit-tree abc`.
- **LATENT DEFECT — `_classify_pipeline_sink` is stringly typed and its value space collides with its own class labels.** With `_is_bash_family` stubbed to `False`, `cat <<EOF | bash` **still** classifies as `"bash"`, because the fallback returns `tokens[0].split("/")[-1]` — the literal string `"bash"` — and the caller compares `sink_class == "bash"`. So bash-family detection *appears* covered for `bash` while being **silently dead for `sh`, `dash`, `zsh`**. This is the "literal strings with semantic meaning belong in constants" rule failing in production, not in a test. Needs its own ticket if you agree it is real.
- **`multiline._normalize_line_endings` is redundant.** The generated grammar's `line_ws_char <- [ \t\n\r]` splits CRLF and lone CR by itself; with the normaliser stubbed to identity, extraction is unchanged. No test in the module can detect its removal.
- **Two production masking pairs in `multiline.py`**: `_strip_comments` ↔ the PEG `comment` rule (the `.peg` itself calls its rule "mainly a safety net"), and `_collapse_whitespace` ↔ `line_ws`. Each half is individually undetectable; only deleting both fails a test.
- **Ticket 19's P7 confirmed and sharpened**: `case $x in a) echo hi;; esac` never reaches the `CASE_STMT` branch — killing the PEG `case_stmt` rule outright changes nothing. That branch is unreachable from a one-line `case`.
- **Ticket 19's three filed `multiline.py` bypasses remain unpinned by any test**, confirmed after repair (`heredoc_quote_parity_skip_off` still fails zero tests). Closing them is **new-fixture work, not repair work** — a separate decision from tier 2.
- **`danger()`'s sort key names a component that does nothing.** Dropping `f.tool` from the key produces zero failures even after repair; dropping `f.pattern` produces one. `discover_tools` already returns sorted names and results are appended tool-by-tool into a stably-sorted list. The docstring's "severity, then tool, then pattern" is one third fiction.
- **`config_access.per_layer_rules` keys a dict by `Provenance`.** Two layers with an equal `Provenance` **collapse**, and their findings are emitted twice. Not reachable in production (real layers differ by path) and there is no guard and no diagnostic. Found because a test fixture hit it.
- **A clean audit and an empty audit are the same value.** `danger()` on a config with zero layers returns `[]`, which renders as "no problems found". The return carries no count of what was examined, so "audited 40 allow rules, all safe" is indistinguishable from "audited nothing" — the same shape as ticket 29's `run_guard ok=True with zero cases checked`. Not fixable from the test side.
- **`danger.py:78` still claims `'remove'` is "always a safe tightening"** — the surviving copy of a claim already refuted for the redundancy analyzers.
- **`change_role_classifier.main()` returns exit 0 for a `--tree` that does not exist**, printing a complete report — *"files analyzed: 0"*, a full role breakdown of zeros, the whole `KNOWN_LIMITATIONS` block — indistinguishable from a genuine clean run. `--tree` is never validated. Ticket 29's family, in a measurement instrument. RED test in the tree; the fix (an `is_dir()` check returning 2) was proven to flip it green with zero collateral.
- **`change_role_classifier` inherits your ambient git config.** `_git_diff_entries` calls `subprocess.run` **with no env**, and `-M` is redundant under git's own `diff.renames=true` default — measured on git 2.53, the same diff reports `R100` without it. So an entire test class was certifying git's default rather than the tool's flag; the only case `-M` ever served was a user with `diff.renames=false`, and nothing tested it.
- **`CLOSURE_RULE_OWN_NAME` is provably dead** (`consider()` returns early for any name in the subject set, and the rule only fires for such names) — confirming queue CRC5 / `KNOWN_LIMITATIONS` N8. With it dead, **every `ClassDef` row collected by `_collect_whole_tree_facts` is inert.**
- **`toolguard/tools/sorters.py` is a pass-through with a test suite.** `stable_rule_key` is a one-line delegate; `sort_layer_rules` is three `sort_patterns` calls; **neither has a non-test caller** (identity scan plus grep). Confirms queue item TL3 — delete, or wire up. Its annotations are also narrower than its behaviour (`List[str]`/`str` vs the `RuleEntryOrStr` the callee handles), and a `RuleEntry` passes through correctly, so **the annotation is the bug** (TL4, decided by execution).
- **`[`-prefixed extended-syntax patterns cluster ahead of plain commands** inside each tool bucket, because `[` is 0x5B and the key is lowercased. Real, previously unstated, now pinned by an exact-order assertion.
- **`Configuration.permission_levels_with_provenance` orders levels by LAYER ORDER; `hierarchy.py` reasons entirely in SPECIFICITY VALUES.** They agree only because discovery happens to emit layers most-specific-first — **an invariant nothing asserts.** Latent, but it is the kind that breaks silently and changes which level wins.
- **`MigrationEffect` and its serialised payload carry no examined-entry count**, so `decision_neutral` is unfalsifiable from the audit record alone. Same shape as ticket 73's `harvest_corpus`.
- **`migration_gate` uses two different predicates over the same object**: `root.root is not None` decides whether to inspect the working tree (`:84`), `root.safe_to_migrate` decides safety (`:38`). They agree today **only because AMBIGUOUS and NONE always carry `root=None`** — an invariant nothing pins. If AMBIGUOUS ever gained a preferred root, the gate would run `git status` on a root it then refuses, and hand back a preflight carrying a working tree for a rejected root. Ticket 57's shape, latent.
- **`working_tree_status` on a SUBDIRECTORY reports the whole repo, with paths relative to the REPO ROOT.** So `migration_gate` can render dirty paths that do not resolve from the root it just named. Now pinned. Also: a **bare repository** reports `is_git_repo=False` — right verdict (no work tree to revert into), mildly misnamed field.
- **`dirty_paths` are git's DISPLAY strings, not paths.** Non-ASCII arrives C-quoted (`"caf\303\251.txt"`), untracked directories collapse to `newdir/`, renames read `old -> new`. The docstring said so and nothing tested it; now three tests do. Relevant if anything downstream ever treats them as paths.
- **An untracked file alone blocks `--apply`.** `working_tree_status` strips and discards porcelain's 2-char status code, so untracked, modified and staged are indistinguishable downstream. That may be the intended conservatism — but it is a policy nobody chose explicitly, and it is now pinned either way.
- **Good news, measured**: `working_tree_status` fails **CLOSED** on every failure mode — git absent, exit 128, timeout — and its `except` is genuinely narrow, so an unrelated exception propagates rather than being disguised as "git unavailable". Ticket 29's fail-open family does **not** apply. That narrowness was at zero detection and is the twin of ticket 31's `_git.run_git` finding.
- **`safe_to_migrate` is `True` for an override pointing at a path that does not exist.** The override is documented as "resolved but NOT checked for existence" — true of the *root*, but the consequence for the *safety predicate* is not stated. The gate reads `root.root is not None` and `root.safe_to_migrate`, and a nonexistent override satisfies both, after which it runs `git status` there. Cheap fix either side: have `RESOLVED_OVERRIDE` carry an `exists()` check, or have the gate stat the root first. Pinned as *documented* behaviour with the risk written into the Then, **not** flipped RED — the docstring says it is intentional.
- **Good news on the sibling worry**: `AMBIGUOUS`/`NONE` carrying `root=None` is **structural, not accidental** — hardcoded at each of the three return sites. So the gate's two-predicate agreement is safe today, and is now regression-guarded from the `project_root` side: giving `AMBIGUOUS` a preferred root fails `test_every_status_is_reachable_and_only_resolved_ones_carry_a_root`.
- **`require_project_root` has no direct test anywhere** — there is no `test_path_utils.py`, and `test_log_writer.py` patches it, which tests the caller. Its `RuntimeError` branch, whose message queue item 23 already flags as wrong, is unexercised.
- **`migration_gate` reports *"The resolved project root is not a git work tree"* for an absent `working_tree`** — a claim about something it never measured. Fail-closed direction is right; the wording is not. Its new test asserts the verdict and blocker count rather than the prose, so this can be fixed without touching the test.
- **`compound._resolve_leaf` has zero production callers** — only `test_compound.py` and `test_compound_resolve_seam.py`. The ask-floor fallback matrix's 12 cells drive it, so they exercise the real `judge_unit` / `_apply_undecidable_floor` but **not `resolve.py`'s driver loop.** Same shape as the `resolve_compound_permission` legacy alias two rows up, and the same three options: repoint, delete, or accept.
- **`file_lock._try_acquire_posix`'s `except OSError` swallows `TimeoutError`** (an `OSError` subclass since 3.3), reinterpreting a genuine hang as "the lock is contended". Harmless in production as far as measured — but it is a **measurement hazard**, and it cost one agent a false "clean survivor" reading on a deadlocking mutant. Worth a narrower `except` on its own merits.
- **`file_lock`'s outer `os.close(fd)` is unguarded** (queue item OP3): a close failure escapes as a bare `OSError`, defeating the module's "one exception type" contract — but only after the critical section has completed. Recorded, judged not worth pinning.
- **Shape 5 is live in production in `file_lock`**: `timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS` is a default argument bound at import, so any future test patching that constant is **silently inert**. Same shape as `architecture_fitness`'s `PYSCN_TOML`, and it will keep appearing — the way to exercise such a default is to **call without the argument**.
- **Ticket 38's downgrade holds, but its case is stronger than the downgrade suggests.** The shape-25 workaround — using `matched_rule is None` to tell a fail-closed verdict from a genuine match — gained **three more consumers** in the seam module. It works, and it works **by accident**: nothing declares that `None` means fail-closed. It stays accidental until the explicit kind field lands, and each new consumer raises the cost of landing it.

---

## A8. NEW AND SELF-REFERENTIAL — a disclosure comment can make toolguard reject the command it describes

**Ticket 36.** A `# INTENT:` block containing backticks and a `<<` token caused `"No valid commands found in command line"`. The command was fine; **the disclosure text broke extraction.**

`CLAUDE.md` states, in the section mandating disclosure: *"A leading comment does not affect rule matching -- the PEG parser discards it and matches the real leaf command."* That is false for at least some comment text, and it is load-bearing — it is why agents are told they can prepend disclosure blocks freely.

Two things make this worse than an ordinary parser bug:

- The disclosure rule demands comments on exactly the commands carrying heredocs and shell metacharacters, so **the text most likely to break extraction is the text the rule most often requires.**
- The failure is fail-closed with a message about the *command*, so the natural recovery is to drop the comment. **The failure mode trains agents out of disclosing.**

**Checkable tonight if you want it:** the logs would show rejected commands whose text contains a `# INTENT:` block.

### A9. Ticket 38 — the prose-parsing anti-pattern is still live, and it is a real refactor

`compound.fallback_kind_for_reason` classifies outcomes by substring-matching the reason text the program just rendered — the same shape TOO-45 already fixed once at the audit-trail level, where it cost **813 of 975 decisions under-logged**. The constant's own docstring admits the failure mode: *"reword either reason string without keeping that substring and this stops classifying it, silently."*

Two consequences beyond fragility: a plain `no_match_fallback=deny` is **indistinguishable from a genuine rule-match deny** in the audit trail, and the fail-closed deny is unclassified (shape 25).

**Decision needed: is this in scope before push, or its own ticket after?** It touches `RuntimeVerdict` and `resolve_one`'s 3-tuple, so it is a decided-type refactor, not a tidy-up. **Explicitly out of scope for the test-repair campaign**, which may not touch production code.

### A10. Ticket 37 — the installer reports success having seeded zero self-integrity rules
Same shape as ticket 29, in the install path. These are the rules that stop toolguard deleting itself, and auto-memory records `~/.toolguard` being wiped four times during TOO-15 testing. Connects to TOO-29.

---

### A11. NEW DECISION — `toolguard-install skills-status` is invoked by a skill but never self-permitted

Queue item UR2, now **measured rather than read**, with a RED test that derives its expectation by parsing fenced command-position invocations out of `skills/*/SKILL.md` against `pyproject.toml`'s `[project.scripts]` — so it stays correct as the skills change.

`toolguard-install skills-status --format json` is the **maintenance skill's pre-flight, before pass 1**. It has no entry in `_SELF_PERMISSIONS`, so it is never seeded and falls to `no_match_fallback` under takeover.

**Three options, and it is your call**: an `ask` entry, a narrow `toolguard-install skills-status:*` pattern, or accepting the prompt.

**Whichever you pick, note the coupling**: fixing the table also fails `test_only_audit_and_maintain_are_declared`, which must be updated in the same edit. The two tests disagreeing *is* the decision surfacing — that is what they are for, not a defect in either.

---

### A12. NEW DECISION — should "governed" mean *builtin*, or *describable*?

`transcript_harvest` gates on **`BUILTIN_TOOLS`** while resolving payload keys through **`TOOLS_BY_NAME`**. Measured consequence: a tool that is **registered, non-builtin, `ToolKind.COMMAND`, `payload_key="command"`** — `mcp__jetbrains__execute_terminal_command` is the live example — **is dropped from the harvest**, so it never reaches the corpus, the replay, or any analyzer.

An *unregistered* tool being dropped is correct. This is the other case, and the gate cannot tell them apart.

**The question is which set governs**: tools governed by default, or tools toolguard can describe. **The blast radius reaches `replay`, `redundancy` and `consolidate`**, which is why the agent pinned it green with a test naming all four discriminating facts rather than flipping it RED — it fires the moment the gate changes, whichever way you decide.

Related and already recorded: follow-up-queue rows 18 and LH1, and ticket 74's finding that `hook._resolve_event` hardcodes `"command"` while two other consumers honour the registry.

---

## A-NEW. Tickets filed 2026-08-13, ranked by what I would fix first

Every one has a RED test asserting correct behaviour unless noted, so phase 2 has a definition of done.

**Security / user-visible, fix first:**

| # | defect | why it ranks here |
|---|---|---|
| **48** | a **dangling symlink** evades a deny on its target; writing through it *creates* the target. **Plus a worse sibling**: `<dirlink>/f.txt` never resolves — no dangling link needed | a deny protecting a not-yet-existing file is the case that matters most, and it is the case that fails. Narrow fix confirmed; the parent-resolution half is a decision with real blast radius |
| **52** | `[[permissions]]` (a plausible typo) **discards the whole section silently** — no parse failure, no validation issue, `has_any_rules` False | rules vanish and toolguard reports the tool unconfigured. **Carries a phase-2 trap: two sites, and fixing one leaves the end-to-end loss invisible** |
| **41** | `sudo rm -rf ~/.toolguard` is **`ask`, not `deny`** | one-token bypass of self-integrity, in a module that exists because an agent ran that command unprompted |
| **49** | takeover makes `has_any_rules` False, so a user's explicit `no_match_fallback = "deny"` is **silently replaced by `ask`** | fires in the *canonical* takeover setup. **The related backwards warning string is pinned green by a test that will resist the fix** |
| **23** | hook emits **nothing on stdout** when crash logging fails | one-line fix, proven. Also the root cause of a test writing to your home directory |
| **51** | **4.3% of audit-log Command fields cannot be parsed back** (1,783 of 41,442, measured on your real logs) | the 813/975 defect downstream; hits heredocs hardest — the commands the disclosure rule exists for |
| **39** | a hard deny **moved into an allow** passes write verification | the guard catches deletion, not inversion, and inversion is worse |
| **40** | `verified_write_config(path, "null", "json")` **overwrites settings.json and reports success** | |
| **24** | a newline in a pattern emits an **unparseable config**, clamping everything to `ask` | |

**Correctness, lower urgency:** **46** (non-object JSON crashes the divergence check), **50** (SessionStart's four checks share one `try`, so one failure hides all four; plus non-object JSON disables the hook), **53** (auto-migration reports a count nothing produced), **54** (`discover_config_files` double-counts when the project root is home; blast radius nil today).

### Filed later on 2026-08-13 — the analyzer tier

| # | defect | why it matters |
|---|---|---|
| **57** | **maintenance `--apply` could enact a permission WIDENING** (`git :*`, admitting every git subcommand), and a **`#NOSECURITY`-blessed rule is withheld in the report but handed to the writer anyway** — the JSON list and the writer's list are different variables | both at **zero detection**. Report and action disagree, and the report is the reassuring one. **Third analyzer found with an unguarded safety gate**, after consolidate and redundancy |
| **56** | the security audit's clarity checks iterate `BUILTIN_TOOLS`, so a **governed MCP tool is never examined and never mentioned** | the audit silently narrows its scope and reports clean. One-expression fix |
| **55** | **four separate sites assume parsed JSON is a `dict`**, each failing differently — a bad write reported as success, a crash on the hot path, a silently disabled hook, a crashed update check | consolidated because the fix is **one guard at the boundary**, not four `isinstance` patches. Two of the four already carry an annotation promising a dict |

### Filed overnight 2026-08-13 (tickets 58-67) — you have NOT reviewed these

You said you had read through #52. Everything below is newer than that line.

**Security / user-visible:**

| # | defect | why it ranks here |
|---|---|---|
| **67** | `if python -c "import os"; then :; fi` -> **allow**. The inline/heredoc foreign-code **ASK floor is lost inside a control structure** — `command_extractor.py:482` builds the if-condition leaf directly, bypassing `_apply_leaf_policy`. Ticket 19's `while` bypass defeats it too | this is the floor the entire disclosure rule rests on — the reason `python -c` prompts under a blanket allow. Two shapes defeat it, and they are the shapes a command takes when it is conditional. **Also: six missed forms** (`python -uBIc`, `perl -E`, `node --eval`, `python -X dev -c`) and **one over-detection** (`grep python -c file` is floored and should not be) |
| **64** | a **project-level ledger path redirects a decision write into the user's home**, and `record_decision` is an **unlocked non-atomic read-modify-write** | item 15 gave `migrate()` an OS lock for the identical shape; this writer did not get one |
| **65** | `api._decide_bash`'s tool override could **null `reason`, `matched_rule` and `provenance` on every MCP-terminal decision** with 0 of 27 tests failing — and worse, **`config.hard_deny(tool)` could stop applying to MCP terminals entirely**, also undetected | ticket 31's prediction reproduced exactly, then exceeded. Hard-deny silently not applying to a whole tool class is the highest-severity survivor of the burst |
| **76** | **an annotation is written above every rule sharing its line text**, so with `Bash(git:*)` in both allow and deny the **deny carries a note claiming it shadows itself**. The obvious fix (restrict to the allow list) does **not** work — the keying is by line *text*; the fix must be positional | queue AE1, measured end to end. And **no test asserted the note's text reached the file** — a writer emitting a constant `# toolguard: note` above every rule passed all 17 tests |
| **75** | **`mining._command_key` hand-rolls bash tokenization** — against `CLAUDE.md`'s single hardest architectural rule — and **every disclosed command you mandate keys on `#`**, landing in one meaningless bucket. `TG_INTENT=1 uv run python x.py` keys on `TG_INTENT=1`. Also: a rule proposed from an **empty corpus is byte-identical** to one proposed from real data that admits nothing; a `deny` is **summarised away as `ask`** and the distribution discarded; and safety-net verdicts (empty / unparseable commands) are reported as **evidence to add a rule** | 7 REDs, each proven falsifiable by mutating toward its fix with zero collateral. **Both of the two disclosure forms your own rule mandates defeat the analyzer.** Nine of ten renderer mutants survived HEAD. `evaluate_added_allow_rule` has **no production caller**, so the widening half is latent and cheap to fix now |
| **74** | **item #10's conversion stopped at the hook**: `hook._resolve_event` and `_handle_command_tool` hardcode `"command"` and consult `payload_key()` only on the file-path branch, while `transcript_harvest` and `fixture_loader` honour the registry. And **an empty registry silently disables the hook, hard-deny included** — `rm -rf` allowed, nothing reports "governed nothing" | the contract exists, two consumers follow it, the component that actually governs does not. The vacuous test that should have caught the empty case was `for spec in _REGISTRY: assertTrue(...)`. Compounds ticket 65. **`Read.is_builtin: True -> False` — Read leaves the governed set while staying fully described — was ZERO failures at HEAD**: nothing checked that Read is *governed*, only that it is *listed* |
| **73** | the **corpus-replay safety evidence is strongest exactly when it is emptiest** — unparseable commands resolve to `ask` under *both* configs, so they count as `unchanged`, and `"corpus replay N entries, 0 broadened"` is the same string a genuinely corroborating run produces. Ticket 51 measured **4.3% of real Command fields unparseable**. Plus: `_verdict_matches_status` **cannot corroborate an ASK** (37,789 EXECUTED / 185 ASK / 96 REFUSED in your August logs), so any corroboration rate under-counts. **And one layer up: `harvest_corpus` returns a bare list, so five unrelated reasons to harvest nothing are byte-identical, and `--max-age-days=-1` is accepted unvalidated and silently empties it** | this is the gate on `consolidate` and `redundancy` rule merges. **Nine findings across two modules consolidated into ONE ticket** per your instruction — same evidence chain, same fix owner. 4 RED tests. The evidence string is also built from `len(corpus)` while the gate reads `broadened_count` (ticket 57's shape), and `replay_single` has **no production caller**, so the ASK defect is latent |
| **72** | the **staleness banner can cry wolf** — an unversioned checkout nested in an unrelated repo is reported clean by the ancestor repo's git, and the banner then announces uncommitted changes **about a tree git tracks nothing of**. And it **cannot see a change to `bash_parser.peg`**, because the digest is `.py`-only while the wheel ships the grammar | this is the boolean behind the banner that fires on your machine every session. Fix for the first verified by mutating toward it (both REDs green, zero collateral). **Same "never proven to run git in the directory it was given" blind spot found the same evening in `working_tree_status` and `migration_gate` — three modules, one shape.** Negative result also measured: no permanent false stale from wheel asymmetry |
| **71** | **two warnings that contradict what happened**: `Tool "Bash" appears in permissions but is not in governed_tools list` fires on the **default** config, and `Logging disabled` prints while logging works | neither changes a decision, but a hook with no UI has exactly two channels — the decision and stderr — and **the same stream carries `Warning: Failed to write to log file`, which ticket 23 established is the only trace a dropped log entry leaves anywhere.** The cost is that the channel stops being read. **Check against the `governed_tools` punch-list item**: `config.py:1690` seeds `[]` while `config_validation.py:59` defaults to `["Bash"]` — they disagree about what "unset" means, and one of them should go |
| **70** | **applying an edit drops `Configuration.parse_failures`**, erasing the condition that clamps every non-deny decision to `ask` — and `security_audit --edits` audits the *result*, so the as-if-enacted preview is cleaner than reality | one-keyword fix, proven (mutating toward it turns the RED green and breaks nothing). Ticket 47's constructor-omission shape in a far more consequential field. Same module: **a caption reading "tighten Bash" enacted a `Read` broadening to `/**`** — ticket 57's report-vs-action split one layer upstream — plus AE2 (a missed removal still applies its addition: half a narrowing is a broadening) and silent double-wrapping at the `--edits` boundary |
| **69** | the **self-permission table could grant `Bash(*)` with a green suite** — `pattern` is written verbatim into your config by the installer and **had no assertion anywhere**. Measured under the mutation: `rm -rf /` -> **`allow`**, `matched_rule='*'` | 0 of 5 widening mutants detected at HEAD, 5 of 5 after. And the installer's own tests **cannot** catch it: they build expectations by iterating the table under test, so they would seed `Bash(*)` and assert `Bash(*)` was seeded. **Fifth rule-generator in a row with an unguarded gate.** Ticket 57's report-vs-action split reproduces here too, 4 more mutants at zero detection |
| **68** | the file-path hard-deny **discards which pattern denied** (`matched_rule=None`), and **the comment defending that choice is wrong about the corpus it cites** | `matched_rule` is in the corpus's *tracked* tier, not the "no verdict may change" tier. Mutating toward the fix: **4 tracked diffs, zero hard failures** — four regenerable golden lines. **The comment, not the missing field, is what has been blocking the fix.** And the corpus cannot catch it either: the HARD tier that pins Bash attribution is **structurally blind to file paths**, which always carry `sub_matches == []` |
| **63** | the canonical protection set covers **Write but not Edit** | an `Edit` reaches a file a `Write` is denied on |
| **61** | takeover audit reads the **legacy alias** and **conditionally hides a conflict** | |
| **59** | per-layer rules **drops native `ask`**, so analyzers never see it | |
| **58** | `apply_proposals` **rewrites a file and then raises, losing the report** | the write happened; the record of it did not |

**The instrument tier — the tools that certify correctness:**

| # | defect | why it matters |
|---|---|---|
| **66** | **UPDATED AGAIN — ticket 30's fix direction is measurably WRONG and this ticket inherited it.** On ruff 0.15.14, `except (A, B, C):` is reformatted **straight back to the bare form**, so anyone applying ticket 30's fix has it **silently reverted by your own mandated `uv run ruff format .`**. Two forms measured to survive ruff *and* let pyscn parse: a parenthesised tuple with a **magic trailing comma** (exploded), or the tuple hoisted to a **named constant**. Also: the generated parser **HANGS pyscn past six minutes** (not "crashes"), and `.pyscn.toml` excludes `**/test_*.py`, so **no pyscn-based guard can ever cover the test suite** — the new guard is AST-based for that reason. Plus the *test-side* guard was worse than the tool | your auto-memory on ruff/except-parens is corrected too: harmless at **two** names, a real defect at **three or more** |: **loosening the layer map, deleting a row, emptying `LAYERS` entirely and inverting the layer order each failed ZERO tests**, and a live bypass exists — `from . import config` and `from .config import x` were **completely undetected**, while `permissions.py`'s imports read as **empty** to the extractor. `run_guard`, **`check_layers` and `compute_predicates` all report PASS over an empty tree**; the layer map is **gameable and `check_layers` cannot tell a loosened map from a fixed import by construction**; `pyscn analyze` prints *"Failed to parse file"* and then reports **Health Score 100/100**; only `api`'s allow-list was pinned by any test | consolidates 29 and 30 — one tool, one fix owner. This is the file the pre-push checklist trusts. **Ticket 30's enumeration was wrong in three ways and missed this file entirely** |
| **60** | the auto-migration gate had **zero detection across the whole suite** | |
| **62** | the log-entry heading is a **contract written twice as literals** | |

**Ticket 23 updated with three corrections**: the `~/.toolguard/errors/` leak is **now fixed** (0 deltas, directory stable at 1,628); a unit-level RED now exists at `error_log.py:142`; and reachability is narrower than the ticket implied — on Linux an unset `HOME` does **not** make `Path.home()` raise. **Five mechanisms in `error_log` had zero detection**, including the write-failure warning that is *the only trace a dropped log entry leaves anywhere*.

**Ticket 43 gained a fifth inert-mock shape** — a constant captured into a **default argument** at import (`parse_architecture_config(path: Path = PYSCN_TOML)`), which makes patching the constant provably inert. It generalises to `TOOLGUARD_DIR` and `REPO_ROOT` across most of `architecture_fitness.py`.

**First pinned-defect removal of the campaign**: `python -X dev -c` was recorded as a `KNOWN_LIMITATION` — the defect was pinned green as expected behaviour. Flipped to RED under hard rule 6.

### THE STDOUT CHANNEL: a test gap, NOT a production defect — bounded by measurement

`test_once_per` found that **`once_per` could have routed both the warning and the degraded notice to stdout** — the hook's JSON decision channel — with 17 of 17 tests green. Nothing in the module asserted the stream. Given ticket 23 established that a hook emitting nothing on stdout is an ungoverned tool call, a hook emitting *extra* on stdout is the same failure from the other side.

**So I checked whether the discipline actually holds repo-wide, and it does.** On the PreToolUse path, `print(json.dumps(output))` in `hook.py` is the only thing that reaches stdout; every warning site in `once_per`, `error_log`, `log_writer`, `error_reporter` and `session_warnings` passes `file=sys.stderr`. The remaining bare `print()` calls are in `permission_migration.py` and `install_update.py`, which are **console-script entry points** where stdout is the correct channel.

**Recording my own error, since it changes what the check is worth**: my first pass flagged three sites in `session_warnings.py` and `log_writer.py` as bare stdout prints. They are not — they are multi-line calls whose `file=sys.stderr` sits below the line the pattern matched. The finding is therefore **a test gap only**: the stream was never asserted, production has always been right, and it is now pinned in `once_per`.

**Worth asking in phase 2**: should anything assert this globally, rather than per module? It is one property, it is cheap to state, and its failure mode is silent.

### A QUALIFICATION ON THIS CAMPAIGN'S OWN ISOLATION CLAIMS — the real-log-dir guard is IN-PROCESS ONLY

Measured 2026-08-13: a parent with both guards installed spawned a `python -c` child in the shape `test/unit/_subprocess_harness.py` uses. **The child rewrote `logs/toolguard-discovery.log` while the parent's guard registry stayed at 0 events.** Children never import `test.unit`, so they are neither guarded nor backstopped. **17 test modules use `subprocess`; 4 use the harness**; `test_sandbox` alone spawns 21.

**What this does and does not undermine**: every agent's before/after **file-count and digest snapshots** are process-independent and still hold — and the full suite run in an out-of-tree copy left `logs/` **byte-identical**, so nothing exploits this today. What cannot be relied on is the *guard* as a promise about subprocess writes. **The guard is a backstop for in-process leaks, not a proof of isolation**, and I have been relaying its clean results without that qualifier.

Also: **`error_log.log_crash` writes to `~/.toolguard/errors/` and is covered by no guard at all** — each test isolates it ad hoc. That is the same shape as the TOO-19 leak this family exists for, on the exact directory ticket 23 concerns.

### THE FOLLOW-UP QUEUE SYSTEMATICALLY UNDER-REPORTS, and this changes how you should read it

Measured **six times in one evening**, not inferred. In every case the queue's read-only verdict was **accurate about what it examined** and silent about everything else:

| module | what the queue said | what mutation found |
|---|---|---|
| `edit_proposal` (`:1499`) | *"Nothing substantive… its fixtures build exactly what its Givens describe"* — called it the best of five | **16** zero-detection mechanisms |
| `self_permission` (`:1273`) | one redundant test | **13 of 25** mechanisms at zero detection |
| `migration_gate` (`:1297`) | *"nothing substantive… no stale claims, no vacuous assertions"* | **11 of 22** mutants surviving — 50% |
| `sandbox` | 2 defects (both correct) | **4 more** it never named, plus 16 pieces of API with no coverage at all |
| `file_lock` | 3 comment-level findings | **5** mechanisms at zero detection, 0 mechanism findings from the read |
| `recommended_protections` | — | 6 weakenings invisible except at the right measurement tier |

**The `edit_proposal` entry is the one to remember.** *"Its fixtures build exactly what its Givens describe"* was **true**, and was precisely the defect: the Givens described **defaults**, and a fixture built from defaults is what lets hardcoding mutants through. A statement can be correct and still name the problem it is dismissing.

**What this means practically**: the queue is reliable as a list of *things someone noticed* and unreliable as a statement of *what is wrong with a file*. A row saying "nothing substantive here" carries no information. **Do not use it to decide a module can be skipped** — that is the one inference it cannot support, and it is the inference its phrasing invites.

### Process/design findings that are not defects but change how work is done

- **Ticket 18 is no longer abstract — toolguard's own seeded rules over-grant because of it.** All **five** multi-token Bash entries in the uninstall-readiness table admit an extra unrelated path argument: **`Bash(rm -rf <skilldir>:*)` admits `rm -rf <skilldir> /etc/passwd`**, and those patterns go verbatim into your config. 2 RED tests / 20 subtests. The `git logfoo` framing understated it.
- **Ticket 18 gained an authoritative basis** — Claude Code's own docs specify the word-boundary rule (`Bash(ls *)` matches `ls -la`, not `lsof`), so toolguard matching `git logfoo` is a **documented divergence**, not a judgement call. And per your note, native's position-independent wildcards are **recent** — so this is drift, and **fidelity cannot be established once**. `docs/native-pattern-reference.md` now carries the quotes and the verification date.
- **Ticket 17's fix is narrower than the ticket implied** — the end anchor *is* supported; the bug is that the matcher takes the **first** occurrence of the final segment and never backtracks.
- **Ticket 24's decided fix is INCOMPLETE, measured 2026-08-14.** Normalising in `normalize_entry` closes the pattern path but **not the comment renderer** — `annotate`'s notes are generated prose that never passes through it. Useful narrowing from the same measurement: a note is a TOML **comment**, so quotes, backslashes, `"""`, `]`, `,`, tabs and non-ASCII are all **inert**; **line breaks are the entire escaping surface**, and the minimal correct fix is line-breaks-only (a whitespace-collapsing variant breaks the tab case). **And a newline in a *pattern* separately defeats the `Tool(...)` unwrapping**, so the rule becomes invisible to every analyzer — one defect masking another, and fixing either alone exposes the other.
- **Ticket 24 is decided** (normalise newlines to spaces, enforce in runtime *and* tests) and **escalated** — the same escaping bug makes `seed-hard-deny` and `seed-self-perms` exit 2, so **self-protection can never be seeded**.
- **Ticket 37 softened** — the two outputs are not byte-identical; the accurate claim is "a verdict with no count". A second instance exists in `cmd_seed_hard_deny`.
- **Ticket 38 downgraded** — the markers *are* pinned; a reword breaks 5 tests. My "silently" claim was inherited from a docstring rather than measured.
- **Ticket 42 corrected** — seven sites, not eight. `rule_entry.py:527` is the **model for the fix**, not an instance of the defect.

**Design / process, no red test:**

- **44** — ambient state read at point of use: **485 patches, 0 autospec, `pathlib.Path.home` patched 18 times.** The wrapper fix, validated against `error_reporter` as a working template. **You agreed this is the first code change after green, and it must land before phase 4.**
- **45** — detecting inert mocks; three mechanisms, and your `assert_called` idea scoped correctly after the white-box critique.
- **43** — inert mocks from by-value imports. **RECOMMENDATION WITHDRAWN, by measurement: the repo-wide sweep was written and run, and it found nothing actionable.** Shape 1 exists at 6 sites (5 the same name) and none is plainly inert; shape 4 is extinct; the 38 "test's own holder" hits are noise — the one inspected is correct by construction. **"Does not need judgement per site" is false** — inertness is a scope question, not a grep question. Five shapes now known; every one was found by falsifying patches *per module*, which is the discipline to keep. **No agent time needs spending here.**
- **47** — `TakeoverConfig`'s positional/default hazard; `kw_only` is necessary and not sufficient.
- **42** — `normalize_entry`'s error channel discarded at seven sites (corrected from eight).
- **38** — `fallback_kind` re-derived from prose. **Urgency downgraded**: the markers are pinned; my "silently" claim was inherited from a docstring, not measured.
- **31** — now also records: the **user level could stop being read repo-wide with a green suite**; that subtracting an "environmental floor" hid a real defect for three rounds; and a **fifth isolation anchor** missing from `test-config-isolation.md`.

---

## A15. #09 BLINDED REVIEW — 13 false claims, and one of them CORRECTS SOMETHING I TOLD YOU

The blinded pass verified every claim by execution: **~70 TRUE, 13 FALSE, 6 unverifiable.** A corrections pass is applying them.

**I owe you a correction.** I reported that the relative-import gap in the layer guard was closed. **Half of it is.** `architecture_fitness.resolve_toolguard_import` — the tool behind `--layers` — follows `from .config import x`, `from toolguard.config import x` and `import toolguard.config`, but **`from . import config` returns `''` and produces no violation**, and so does `from toolguard import config`. Only `test_architecture.py`'s own `_module_imports` sees all six forms. **The test side is fixed; the tool is still blind to the two forms this package actually uses most.**

**The finding with the widest consequences: `toolguard/tools/` SHIPS IN THE WHEEL.** `pyproject.toml:96-97` is `packages = ["toolguard"]`, so `toolguard/tools/` and `toolguard/scripts/` are **bound by the stdlib-only rule** — which is what the "all 77 modules" scan already assumes. The dev-only tree is the **top-level `tools/`**, and nothing in the document (or in my reports to you) distinguished the two. **If the core/tooling split is going to carry weight, that distinction has to be explicit.**

**The reviewer's closing observation is the durable part**, and it generalises past this document:

> *"The prose is measured; the tables and the summarising sentences are not. **Every falsehood I found is in a table cell, a diagram node, or a sentence that compresses a hedged paragraph into an absolute.**"*

Both directions were present: §5's list of *remaining* gaps is more pessimistic than the code (8 of 10 upward layer moves **are** caught — the real rule is "caught iff some module in a lower layer imports it"), while §5's list of *closed* gaps is more optimistic (F1 above).

**What it confirmed, which is the better news**: the parse-failure floor and its deny exemption are stated correctly in prose **and** in the diagram — the claim this project has got wrong in four places. The "pure resolver" trap is explicitly disarmed. The write chokepoint is correctly described as unenforced. `--guard`'s scope is accurate. And all three compound-resolution functions really do have zero production callers.

**Two numbers you may care about**: the doc's "38 modules, 15,100 lines" for the core runtime **silently excludes the 8,629-line parser** it claims to include — with `parser/`, tooling is 33% of the split, not 44%. And the cited "60 ms per invocation" measures the **installed 0.5.1 build**, which is not the code the document describes.

---

## A14. #09 — `docs/architecture.md` IS DELETED AND MERGED. Two things need you.

`docs/architecture-as-built.md` is now **475 lines / 4,943 words**, with 14 diagrams, all referenced, zero orphans, `check_doc_links.py` passing. **The merge is a ~16% net reduction in total prose** (655 lines across two files -> 475 in one) while *adding* four diagrams. Prose across the whole document: median sentence 12 words, **zero over 40**; median paragraph 22 words, **zero over 120**. Sections 5-7 went from a 24-word median sentence and three paragraphs over 120 words to 11 and zero.

**Six claims in the old `architecture.md` were false and are gone**, including two worth knowing: *"the hook itself never writes configuration — it is a read-only path"* (it does, via auto-migration reaching `verified_write_config`), and *"compound commands are resolved by `compound.resolve_compound_permission`, which is what the live hook drives"* — that function has **zero** production callers, as do `resolve_compound_permission_detailed` and `check_compound_permission`.

**1. WE CREATED ONE DANGLING REFERENCE AND I COULD NOT FIX IT.** `toolguard/log_writer.py:22` says *"(see ``docs/architecture.md``)"* and that file no longer exists. It is a one-word comment change, but it is **production code, which is phase 2 and yours to sequence** — so I have left it. `tools/corpus_build.py:622,723` use `"./docs/architecture.md"` as Read-pattern *fixture* paths; matching does not require the file to exist, so those are cosmetic.

**2. THE FILENAME IS MY INCONSISTENCY, NOT THE AGENT'S.** The #09 plan's own recommendation — written by me and shown to you — said *"merge into one `docs/architecture.md`"*, i.e. keep the older, more discoverable name. **My brief to the agent said the opposite**: merge into `architecture-as-built.md` and delete the other. It followed the brief and flagged the conflict. Reversing it is a `git mv` plus the same six repoints (`README.md`, `llms.txt`, `docs/agent-map.md`, `docs/config-sync.md` x2, `docs/security.md`, `docs/configuration.md`). **Your call which name survives.**

**A process note worth keeping**: two of those references (`docs/security.md:462`, `docs/configuration.md:781`) were found **only** by `check_doc_links.py`, not by the agent's grep. Run the link checker before deleting any doc, not after.

**Still open**: no diagram yet for the hard-deny pool or strictest-wins combination; and `docs/native-pattern-reference.md` is untracked, so nothing links it yet.

## A13. #09 IS MOVING AGAIN — four questions from pass 1, and one cheap fix worth taking

`docs/architecture-as-built.md` went **130 -> 271 lines** overnight. Four sections now lead it: the constraints the architecture answers, stdlib-only, the PEG grammar, and core-vs-tooling. Prose measured, not eyeballed: **median sentence 12 words, zero over 40, median paragraph 26 words, zero over 120.** Zero mermaid fences, zero dangling refs, and **`core-vs-tooling` is finally referenced**, so there are no orphan diagrams.

**The finding worth acting on: nothing enforces the stdlib-only rule.** An AST scan over all 77 runtime files confirms **0 foreign import roots today** — but no test, no `--guard` mode and no fitness check would catch `import numpy` in `toolguard/`, **and the dev venv would mask it** (`numpy` and `sentence_transformers` *are* importable there). The scan that proves it is ~20 lines and fits as an `architecture_fitness.py --stdlib` mode. **A hard constraint with no enforcement is the exact shape the "encoding rules as guidance" note warns about.**

**A caution about our own diagram process**: `core-vs-tooling.mmd` asserted *"fails open, never blocks."* **That is false** — the hook fails **closed**, and the fail-open it exists to prevent is exit-0-with-no-decision. That diagram had already been **built and inspected as an image**, and the inspection caught layout problems while missing a false claim inside it. *"Inspect every diagram as an image"* verifies legibility, not truth.

**Four questions:**

1. **Section numbering** — the constraints took 1-4 and pushed the originals to 5-8. Would you rather they were an unnumbered preamble? The merge pass renumbers again either way, so now is the cheap moment to say.
2. **Ticket-number citations in `docs/`** — the four tooling defects are described without numbers, with one pointer to `00-INDEX.md`. `docs/` is user-facing and linked from `llms.txt`; say if even that pointer is too internal.
3. **The `--stdlib` check** — take it, or leave the constraint on trust?
4. Still outstanding from the plan: an entry in `docs/agent-map.md` and a line in `llms.txt`. The merge pass is doing both.

---

## C. Decisions I TOOK — overrulable, already acted on

- **`docs/architecture.md` and `architecture-as-built.md` merge into one file.** Two documents with that boundary is a drift generator; the old file's best content is diagram material never drawn. Not yet executed — the rework does it.
- **The tooling section sits at the seam**, not deep into individual analyzers; depth stays in `docs/skills.md`. Given `tools/` is 44% of non-test Python, "at the seam" is a real limit and you may want more.
- **Diagrams ship as PNG, not SVG** — SVG rendered standalone but not embedded in your markdown renderers. Cost: **~1.1 MB of binary in `docs/`**, growing with the diagram set, and it churns on re-render. The lean alternative is raw ```` ```mermaid ```` fences, which GitHub renders natively but your local preview does not.
- **Test campaign triage: permission path first**, per ticket 31's own recommendation rather than a bulk sweep of 80 modules.
- **In-process mutation, never on disk** — after an agent caught that parallel agents were seeing each other's production mutations. Wave 1's full-suite numbers are provisional as a result; the repairs themselves were proven module-locally.

---

## D. Housekeeping, trivial

- **A doc-drift sweep fixed ~15 false claims across `security.md`, `configuration.md`, `config-sync.md`, `permission-patterns.md`, `agent-map.md` and `README.md`** — each verified against code before editing, several by driving real decisions. The ones worth knowing: *"It **never** silently drops a rule"* (the check is **opt-in**, default `None`, and `installer.py:437` skips it); *"`#NOSECURITY` so the audit stops re-flagging it"* (it still reports and labels — *"toolguard acknowledges, it does not hide"*); `governed_tools` marked **"(required)"** when it is optional, contradicting line 101 of the same file; project-root detection listing **2** markers when the code has **6**; and `README.md` claiming **724 tests** against a real 3,628. Four leftover *"Claude Code 2.10"* version pins were also removed — the same pass that deliberately removed that pin from the prose had left it in a table cell.
- **`docs/diagrams/config-hierarchy.mmd` said less-specific levels are "never consulted".** False — `resolve_command_permission` matches **every** level eagerly, and `_detect_override` scans the less-specific ones, which is what produces the conflict log the security doc tells users to review. Fixed and the PNG regenerated. **Third finding this week in a diagram node**, which is now a documented pattern rather than a coincidence.
- **`docs/config-sync.md#session-warnings` was NEVER TRUE, not stale** — a stronger verdict than I recorded. `/tmp/toolguard-warnings/`, the scheme it documents, appears **nowhere** in `toolguard/`, `tools/` or `test/`; the real code always used `logs_dir/.toolguard-<kind>-YYYY-MM-DD`, now `~/.toolguard/once_per.db`. Replaced with a true, shorter section (**net -60 lines**). The agent deliberately declined to add *"delete `~/.toolguard/once_per.db` to see it again"* — unverified advice pointing into the directory this repo has had wiped four times.
- **~~`docs/config-sync.md#session-warnings` is STALE~~** — it documents "once per session" and per-kind **marker files**, a mechanism the claim store replaced. Measured: `once_per` offers exactly **one** period, `day` (`once_per.py:190`); the marker files are **legacy and swept by `reap()`**; `session_warnings.py` is explicitly **not** throttled; and there is **no session-scoped throttle anywhere**. The architecture document carried the same falsehood and it is now corrected there. Worth a fix or a ticket — flagged rather than edited, because it is a third doc and the pass was scoped.
- **`.pyscn/reports/` holds 72 accumulated HTML files** (~8 MB and growing). `pyscn analyze` drops an unbounded ~112 KB report per run into `<cwd>/.pyscn/reports/`, and it is gitignored, so it accumulates invisibly — a static-analysis guard's own test runs were the main producer, now fixed to run from a throwaway cwd. Safe to delete the directory.
- **`docs/diagram-path-test.md`** is throwaway and can be deleted whenever.
- **Markdown cleanup under `toolguard-memories/`** before push — your call on what has long-term value.
- **None of tickets 17-35 are filed to YouTrack.** They exist only as files here.
- **`/documentation-review`** is triggered — `technical-notes.md` changed.
- **`docs/configuration.md:460`** carries the unhedged "clamps every decision to ask" overclaim.
- **`test/verdict_corpus/README.md:99` cites a verification mutation "inside `resolve.py::_resolve_one`". No such function exists** — the nested function there is `_decide`, and `_resolve_one` survives only as a local name in `test_hierarchical.py`. Its claimed 992 mismatches is also unreproducible at the current site (the equivalent mutation gives 191). Left for `/documentation-review` rather than fixed mid-campaign.

---

## E. State of the tree — PHASE 1 ESSENTIALLY COMPLETE

**PHASE 1 IS ESSENTIALLY COMPLETE. 76 test modules repaired. 2733 -> 3603 tests. 134 intentional reds. Production untouched; `ruff format --check` and `ruff check` clean; gate run serially with no agents live.**

**One module remains**: `test_touch_set_score.py`. `test_resolve.py` and `test_once_per_store.py` were measured clean earlier and are deliberately skipped. That is the whole of phase 1.

Added in the overnight burst: `test_api`, `test_command_extractor_inline_code`, `test_compound_resolve_seam`, `test_error_log`, `test_file_lock`, `test_install_provenance`, `test_once_per`, `test_sandbox`, `test_tools_edit_proposal`, `test_tools_migration_gate`, `test_tools_project_root`, `test_tools_self_permission`, `test_tools_uninstall_readiness`, `test_tools_working_tree`, `test_verdict_corpus`, `test_zz_real_log_dir_guard`, plus a narrow widening-guard follow-up on `test_recommended_protections`.

**Reds attributed by module, not counted**: the 20 in `test_tools_uninstall_readiness` are ticket 18's two methods across 20 subtests; every other module's count matches what its agent reported as `left_failing`.

`test_api`, `test_architecture_fitness`, `test_ask_resolution`, `test_auto_migrate`, `test_bash_parser`, `test_command_extractor_inline_code`, `test_compound`, `test_config`, `test_config_divergence`, `test_config_write_guard`, `test_configuration`, `test_env_config`, `test_error_log`, `test_error_reporter`, `test_git_helper`, `test_hard_deny`, `test_hierarchical`, `test_hook`, `test_hook_error_reporter`, `test_hook_eval`, `test_log_writer`, `test_logging_streams`, `test_migration`, `test_multiline_bash`, `test_normalization`, `test_patterns`, `test_permission_resolution`, `test_permissions`, `test_recommended_protections`, `test_rule_entry`, `test_rule_sort`, `test_self_integrity`, `test_session_start`, `test_session_warnings`, `test_symlink_hierarchy`, `test_takeover_mode`, `test_toml_config`, `test_tools_clarity`, `test_tools_config_access`, `test_tools_consolidate`, `test_tools_danger`, `test_tools_decision_ledger`, `test_tools_installer`, `test_tools_log_harvest`, `test_tools_maintenance`, `test_tools_redundancy`, `test_tools_rule_apply`, `test_tools_security_audit`, `test_tools_takeover_audit`, `test_update_check`.

**THE 79 FAILURES ARE THE INTENDED OUTPUT OF PHASE 1.** Each asserts the correct behaviour and fails because production is wrong. **A green suite means someone weakened a test, not that the code was fixed.** They are the definition of done for phase 2: fix the code, and they go green on their own.

**The 79 splits as 74 failures + 5 errors, and the 5 errors are not breakage.** Verified by name, not assumed: each errors rather than fails because the production defect *is* a crash, which is the correct shape for its ticket — `test_tools_rule_apply` (58), `test_update_check` and `test_config_divergence` (55, two of its four sites), `test_error_log` (23), `test_migration` (24).

Every red maps to a ticket in section A-NEW. The ones to look at first if you want to see the shape of it: `test_compound.test_nested_backticks` (34, a live bypass), `test_rule_sort.test_newline_in_additional_context_keeps_the_section_parseable` (24, config-bricking), and the three `test_hook` stdout reds (23, one-line fix proven).

**The campaign's central pattern, stated once**: *the mechanism a module is named for was usually its least-tested.* Hard-deny bypassed entirely -> 1 failure. The grammar's delimiter class destroyed -> 0 of 18. The hierarchy inverted -> 0 of 33. Takeover's ON/OFF pair -> 0 of 11. `run_git`'s subprocess call -> 0 of 10. `_check_family2_safe`, the gate on the only analyzer that writes -> 0 of 38. End-to-end tests were carrying the modules that owned the mechanism.

**Representative before/after, all measured in process:**

| module | mutations surviving before | after |
|---|---|---|
| `test_patterns` | 14 / 30 | **0 / 30** |
| `test_ask_resolution` | 9 / 19 zero-detection | **0** |
| `test_rule_sort` (escaping, all 4 directions) | **0 failures either way** | fix and bug now distinguishable |
| `test_tools_danger` (delete-sort / constant-key) | **0 / 0** | 4 / 4 |
| `test_hard_deny` (mechanism fully bypassed) | 1 failure, from the end-to-end test | 5, from the class that owns it |
| `test_bash_parser` (delimiter class destroyed) | **0 of 18** | 9 / 3 / 3 / 5 |
| `test_hierarchical` (hierarchy inverted) | **0 of 33** | pinned by 2 new tests |

**Tickets filed or updated tonight:** 34, 35, 36 new; 11 **answered and closed by measurement**; 17, 22, 24, 28, 31 updated with corrections.

**Nine errors found in my own working notes**, by agents told to treat them as unverified — including one flatly false "went through all 77 tests individually, none found", and two proposed fix shapes that would have produced broken tests.

`docs/architecture-as-built.md` and `docs/diagrams/` are new and untracked. **Nothing is committed. All git operations are his.**
---

# E. PHASE 2 — calls I made while you were away, 2026-08-14

You said "continue non-stop until green". These are the decisions that came up, all of them **reversible**, listed so you can overrule rather than so they can be re-argued.

## E1. TAKEN — the `Bash(x:*)` boundary fix stands, and it changes behaviour you will feel

`match_command` built its prefix as `bc + rest + "*"`, gluing the trailing wildcard onto the last token, so only the **base** command was boundary-guarded. `git log:*` matched `git logfoo`. That is now fixed: the prefix must end on a token boundary.

**I did not take this on the tests' say-so.** Two independent confirmations:

- The repo's **own measured divergence table** already carried it: `docs/native-pattern-reference.md` row 18 said native enforces a word boundary and `:*` is equivalent to ` *`, with toolguard's `git log:*` matching `git logfoo` recorded as the divergence. It is now marked resolved.
- **Anthropic's documentation**, fetched fresh, verbatim: *"The `:*` suffix is an equivalent way to write a trailing wildcard, so `Bash(ls:*)` matches the same commands as `Bash(ls *)`"*, and *"when `*` appears at the end with a space before it (like `Bash(ls *)`), it enforces a word boundary, requiring the prefix to be followed by a space or end-of-string. For example, `Bash(ls *)` matches `ls -la` but not `lsof`. In contrast, `Bash(ls*)` without a space matches both."*

**The blast radius, which is the part worth your attention.** The documented rule names exactly two terminators — a space or end-of-string — and **`/` is neither**. So path-prefix rules stop behaving like path prefixes:

- `mkdir -p /tmp/:*` no longer covers `mkdir -p /tmp/claude-code`
- `rm -rf /tmp:*` no longer covers `rm -rf /tmp/foo`
- `git diff:*` no longer covers `git difftool`
- a **hard-deny carve-out** written this way stops exempting, so its verdict moves `allow` -> `deny`

For an **allow** rule that direction is safe (more asks). For a **deny** rule it is the opposite — `deny /tmp:*` no longer denies `/tmp/foo` — so if you have deny rules written as path prefixes anywhere, they were relying on the bug and need rewriting as `[glob]` or with an explicit trailing separator. **That is the one consequence I would want you to check by hand.**

Honest caveat on the evidence: the docs' only worked boundary example is `ls -la` / `lsof`, a letter-vs-letter boundary. **They never test a `/` continuation.** The literal wording covers it; an on-point example does not exist. If you want certainty for the path case it needs behavioural testing against the real CLI, not another reading.

## E2. TAKEN — I authorised edits to 8 tests, which the phase-2 rules otherwise forbid

The fix turned 8 previously-green tests red, all in `test/unit/test_tools_consolidate.py` and all encoding the **pre-fix** semantics as contract. Proposed ticket 18 had named one of them in advance as exactly that. I gave one agent a **bounded licence naming the four locations and no others**, with the requirement that every changed line be shown before-and-after in its report.

`test_consolidation_preserves_prefix_extension_commands` is being rewritten to assert what it actually cares about — that consolidation does not **change** a verdict — rather than pinning the stale answer. `TestFamily2MkdirSubsumption` is being re-based on a fixture where subsumption is genuinely true, **not deleted**; if no such fixture exists that comes back as a finding.

**This is the rule I was most reluctant to bend**, and I am flagging it rather than burying it: once an agent may edit a test, "the test is the spec" stops being free. The licence was enumerated and audited for that reason.

## E3. TAKEN — Option A on the five seeded uninstall rules

10 reds in `test_tools_uninstall_readiness` are **not** a matcher bug, and my brief's hypothesis about them was wrong. `Bash(rm FILE:*)` is `Bash(rm FILE *)`, and a trailing `*` legitimately spans a second argument, so `rm FILE /etc/passwd` matching is native-correct. Refusing extra arguments would break `cd:*` matching `cd /tmp`.

The defect is in **the rules toolguard seeds to protect its own uninstall**, which are too loose. Option A drops `:*` from the five multi-token entries, making them exact-match: measured, all 8 real-flow probes stay `allow` with the correct `matched_rule` and all 10 dangerous witnesses become `ask`. **Cost: `rm -rf <dir> -f` and `rm -rf <dir>/` fall to `ask`.**

## E4. NEW FINDING, not fixed — native normalises commands BEFORE matching, and we may not

The documentation names three normalisations applied **before** prefix matching runs, which a drop-in replacement has to reproduce:

- **wrapper stripping** — `timeout`, `time`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, zsh `noglob`
- **leading environment-variable assignments stripped, for allow rules only**
- bare **`xargs`** stripping

**The middle one is pointed at us.** This project mandates `TG_INTENT=1 <command>` and `TG_ATTEST_READONLY=1 <command>` disclosure prefixes. Whether toolguard strips a leading assignment before matching decides whether **every disclosed command still matches its own rule** — and the allow-only asymmetry means a deny rule and an allow rule would treat the same prefix differently.

**MEASURED, and it is worse than I expected — filed as ticket 77, and it is the most serious thing found today.** Toolguard strips nothing. Two consequences in opposite directions:

- **`FOO=1 rm -rf /tmp/x` evades a `deny Bash(rm:*)` rule entirely.** A one-token prefix defeats a deny rule in a security tool.
- **`TG_INTENT=1 ls -la` misses `allow Bash(ls:*)` and falls to `ask`.** So this project's own mandated disclosure marker currently costs an agent its permissions — which is a standing incentive to skip a rule that already has a measured compliance problem.

Wrappers (`timeout`, `nohup`, `nice`, …) and bare `xargs` behave identically.

**The decision in ticket 77 is real and I did not pick.** Implementing native *exactly* — strip for allow only, as documented — **fixes the allow row and leaves the deny bypass open.** The alternatives are to strip for both lists (closes it, stricter than native) or to treat a stripped prefix on a deny evaluation as undecidable so it takes the ask floor (closes it without silently denying, at the cost of friction). Not fixed, no test covers it, and it is not one of the 137.

---

## A16 — DECIDED by Arnon 2026-08-20, NOT pending. External-contract module + weak drift detection. Recorded for the trail; ticket 85 filed.

He asked, on the ticket 82 correction: *"The list of stripped wrappers should be documented explicitly in the toolguard documentation and dated to the last date verified with a reference to the documentation page... We may want to make the wrapper list a tuple in an external contract related module. I don't think you have such a module today. Where do you track external contract related behavior like the payload structure, the response fields, etc.? Only in tests?"*

**Measured answer: only in tests, and there only by repetition.** Twelve Claude Code wire-protocol field names appear as bare string literals **45 times across 6 package modules and ~696 times across the test suite**. `additionalContext` alone: 7 package sites, 188 test sites. Nothing anywhere *states* the contract or when it was last checked — the tests encode it by repetition, so an upstream rename changes 696 lines while no single line ever said what the field was.

### Proposed: `toolguard/claude_code_contract.py`

Named for the owner of the facts, not for us. A leaf module, stdlib-only, importable from any layer like `constants.py`; needs a `.pyscn.toml` layer entry. Holds the three things that share one property — **we do not get to decide them**:

- `STRIPPED_WRAPPERS` and the explicitly-**not**-stripped list. Both are load-bearing: ticket 82's error was assuming membership of the second.
- The matching semantics toolguard mirrors: word-boundary rule, `:*` ≡ ` *`, colon-is-literal mid-pattern, known-safe assignment stripping and its allow/deny asymmetry.
- The hook wire protocol: payload and response field names.

Each entry carries the doc URL, the section anchor, and a `VERIFIED` date. Docs cite the module instead of restating it.

### How drift is detected — DECIDED: option (a), the weak one

- **(a) Dated constants plus a pre-push checklist line.** Weakest. His own CLAUDE.md predicts prose MUSTs get silently dropped, and this specific claim has now been wrong twice.
- **(b) Pin the Claude Code version** — `CONTRACT_VERIFIED_AGAINST = "2.1.231"` — and fail a test when the installed `claude --version` differs, with a message naming the page to re-read. Same shape as the Python-version test he proposed for the pathlib facade assumptions: pin the thing that changes underneath us, fail when it moves. **Cost, stated plainly: fires on every Claude Code upgrade, not only permission-affecting ones**, so most firings are "re-read, nothing changed, bump the constant."
- **(c) A session warning through the existing `session_warnings.py` / `once_per.py` machinery.** **Rejected by the coordinator without asking** — it would push a maintainer's revalidation chore into every *user's* runtime, and users of toolguard have no stake in whether our contract notes are current.

**Coordinator's recommendation: (b), accepting the noise**, because a calendar date detects nothing and the checklist has already failed twice. But (a) is defensible if he would rather not own a test that goes red for reasons unrelated to the code, and this is his call.

**DECISION, Arnon 2026-08-20**: *"A weak option is fine for now. At least we have a good way to periodically review."* -> **(a)**. Dated constants and a periodic review, no version-pinned test. (b) stays on the shelf if the weak form is seen to drift; the trigger for reconsidering it is evidence that a re-verification was skipped, not a schedule.

He also scoped the consolidation in the same breath: **all external-contract structures move to the new module, and stand-alone functions whose sole purpose is the external contract move with them; functions that merely reference contract structures while carrying toolguard-specific logic stay put.** Filed as **proposed ticket 85**, marked high priority and explicitly *part of TOO-45's original architectural-cleanup scope rather than an addition to it*.

---

## Two findings rescued from the section-C review-round audit, 2026-08-23 evening

Both surfaced by auditing the 29 blinded review rounds before deleting them (all 29 are untracked, so permanent). Both re-verified by me at HEAD `305caa3`, independently of the agent that found them.

### 1. Ordinary path spellings walk past a deny rule naming the same file

Against the rule `cat /home/arnon/.ssh/id_rsa`, with a positive and a negative control passing in the same run:

| spelling | matches deny? |
|---|---|
| `cat /home/arnon/.ssh/id_rsa` | True (control) |
| `cat ~/.ssh/id_rsa` | True |
| `cat ~/.ssh/../.ssh/id_rsa` | **False — evades** |
| `cat ~/./.ssh/id_rsa` | **False — evades** |
| `cat /home/arnon//.ssh/id_rsa` | **False — evades** |
| `cat /home/arnon/./.ssh/id_rsa` | **False — evades** (not in the original finding; found on re-verification) |
| `cat /home/arnon/.ssh/known_hosts` | False (control) |

**Exposure measured before proposing anything, per `.claude/rules/evidence-before-fixing.md` — and it splits the finding in two:**

| shape | featherhill (honest corpus) | toolguard (dogfood) | instagram |
|---|---|---|---|
| `//` double slash | **20 — every one accidental** | 27 | 1 |
| `../` or `./` through an absolute path | **0** | ~10, all relative navigation (`cd skills/x && readlink -f ../../docs`) or this campaign's own probes | 0 |

featherhill's 20 are Claude writing `tail //tmp/server-flo72-nav-test.log`, `mkdir //tmp/claude-code`, `grep //tmp/...` — **nobody typed those to evade anything; the agent doubled a slash by accident.** That is accidental reachability against a mechanism that fails silently, which by the rule's own test (*"zero occurrences plus accidental reachability plus silent failure is still a fix"*) is a fix.

**The `../` and `./` round-trips are the opposite case: zero occurrences anywhere, and they need deliberate spelling.** toolguard governs Claude, not an adversary. By the reachability filter these are a defer.

**Recommendation: file one ticket scoped to `//` collapsing, and record the `../`/`./` variants in it as measured-zero and deliberately deferred.** Filing needs your approval — not filed.

### 2. `pwd.getpwnam` is a route to the home directory that `--ambient` structurally cannot see

`toolguard/normalization.py:140` calls `pwd.getpwnam(name).pw_dir`; `grep -c pwd tools/architecture_fitness.py` returns **0**. There is no `PATH_AMBIENT_OWNERS` entry because the scan has no arm that would ever look.

This is the **fourth** instance of the pattern `.claude/rules/evidence-before-fixing.md` already names as the instrument's weak spot — *"`expanduser`, `resolve` and `absolute` each got through by not being on the list yet. The check was rigorous about what it had been told and blind to what nobody had declared."*

**The reachability filter does not apply here**, because nothing is broken in the product — the gap is in the instrument, and an instrument that reports a clean `--ambient` while a whole route goes unexamined is a false negative by construction. Cheap declarative fix: add a `pwd` arm to the scan plus an owner entry.

### 3. The decision vocabulary is a bare string literal, and its strictness order exists in three copies

Rescued from the section-B audit and **verified by me at HEAD `305caa3`** by reading all three sites.

Three identical mappings, three names, three modules:

| module | name | value |
|---|---|---|
| `toolguard/compound.py:55` | `_DECISION_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |
| `toolguard/tools/replay.py:35` | `_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |
| `toolguard/tools/mining.py:62` | `_VERDICT_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |

And the vocabulary underneath them is not named at all: `constants.py` defines only `STATUS_ASK = "ASK"` (uppercase, the log status). The lowercase decision words appear as bare literals — **207 occurrences of `"deny"` alone** in assignment or comparison position across the package. This is precisely the case the global CLAUDE.md rule names: *"decisions like `deny`/`ask`, kinds, statuses, format names"* are the offenders that matter most because they are repeated across modules and tests.

**Two reasons not to treat consolidation as mechanical, both from this project's own history:**

1. **`compound.py` documents its separation as deliberate** — *"Kept separate from `_combine_strictest`'s own ordering: that function combines several already-decided sub-commands with its own reason-building rules, while this floor clamps a single decision."* The three uses genuinely differ: a floor clamp, a verdict-change comparison, and a cluster headline.
2. **`project_one_structure_two_questions` records this exact shape going wrong twice in two tickets** — widening a shared structure for one consumer silently changed the other, once downgrading an unoverridable `hard_deny` to `ask` **with a green suite**.

**So the safe split is: name the vocabulary, leave the three orderings alone.** Extracting `ALLOW`/`ASK`/`DENY` as shared constants is pure win and cannot change behaviour. Merging the three dicts into one is the part that carries the risk, and the value is lower — they are three lines that happen to agree today, and the comments say two of them agree by coincidence of purpose rather than by shared meaning.

**Not filed** — needs your approval. Neither the follow-up queue nor any DURABLE file records it.

**Delete-list dependency**: the only two files recording this finding are `TOO-45/TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md` (section B) and `TOO-45/TOO-45 phase 2 work unit 7 (tools-hierarchy, tools-mining) - coder task recall.md` (section A). **Both are on the delete list.** The finding is now captured here, so both may go.

### 4. `architecture_fitness.py --predicates` R3 reports PASS over a live prose re-parse, for two independent reasons

**Correction, same evening: the arm is `--predicates`, not `--contract`.** I wrote `--contract` first; that flag does not exist, and running it fails with `unrecognized arguments`. The real arm **passes**, which is the whole point — it prints, verbatim:

```
=== R3: PASS ===
  (excluded as sanctioned: compound.py::fallback_kind_for_reason)
```

It announces an exemption for a function that no longer exists, and calls the result a pass.

Surfaced by the implementation-habits extraction; **verified by me at HEAD `305caa3`.**

**Reason one — the exclusion list names a function that no longer exists.**

```
tools/architecture_fitness.py:1606
R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}
```

`grep -rn "def fallback_kind_for_reason" toolguard/` returns **0**. The function was removed; its sanction was not. A stale exemption is strictly worse than none, because it reads as a considered decision.

**Reason two — the detector is name-based, so a one-letter local defeats it. The blind spot is documented in the detector's own docstring** (`tools/architecture_fitness.py:1660-1664`): it returns *"every production site that extracts structured meaning from a `reason`-named string"*, via *"three shapes, all keyed on a Name/Attribute whose OWN name contains 'reason'."* A receiver named `r` contains no such substring, so it is invisible **by design, not by oversight** — the check was written to find one spelling of the antipattern and reports PASS for every other. At `compound.py:1119-1123` there is a live re-parse of a prose string the program itself produced:

```python
r = uv.reason
if " -> " in r:
    pattern_part = r.split(" -> ", 1)[-1]
```

The extracting agent tested this with a paired control — the identical parse with the receiver named `reason` instead of `r` — and the check **fired at 2 sites for `reason` and 0 for `r`**. I re-read the code and confirm the shape and the stale sanction; I did not re-run the paired control.

**Why this matters more than an ordinary lint gap.** This is the exact antipattern the project's own CLAUDE.md documents with a measurement: rendering a decision to a human-readable reason string, discarding the structured result, and later re-deriving facts by pattern-matching that prose. **Measured cost when it last happened: 813 of 975 compound-allow decisions (83%) under-logged, and 1,943 sub-commands reaching the audit trail with no record at all.** Nothing failed and nothing warned; the audit log looked complete.

So the position today is: **the codebase contains an instance of its most expensively-documented antipattern, and the instrument built to catch that antipattern reports PASS.** That is this campaign's signature failure — a mechanism that fails open and says nothing — occurring in the very check meant to prevent it.

**What is NOT established:** whether this particular site currently produces a wrong log entry. The shape is present; the consequence is unmeasured. That measurement should precede any fix, per `.claude/rules/evidence-before-fixing.md`.

**Suggested split, mirroring finding 3:** deleting the stale `R3_SANCTIONED_SITES` entry is pure win and cannot change behaviour. Making the detector receiver-name-independent is the real fix and will likely surface other sites — which is the point, but it should be a measured, scoped piece of work rather than a drive-by. **Not filed — needs your approval.**

---

## F. PRE-PUSH — GIT RULES AT USER LEVEL: ALLOW WORKTREES (decided, not yet applied) — Arnon, 2026-08-25

> *"I think that I made a mistake in my git rules. I should allow worktrees so that it is easier for you to run parallel agents on the same code base. Make a note that we should review the git rules we have at the user level to refine them based on the experience in TOO-45."*

**Measured current state, 2026-08-25 — worktrees are not prohibited anywhere, which sharpens the problem rather than dissolving it:**

| where | rule | level |
|---|---|---|
| `~/.toolguard/rules/git.rules.toml:182` | `git worktree list` | **allow** |
| `~/.toolguard/rules/git.rules.toml:268` | `worktree add\|move\|remove\|prune\|repair\|lock\|unlock` | **ask** |
| `.claude/toolguard_hook.toml:62` | `Bash(git worktree *)` | **allow** — in this project only |
| `~/.claude/CLAUDE.md`, git section | worktrees **not mentioned** — the list is commits, pushes, checkouts, merges, branches, stashes, resets | prose |

**So the change is an `ask` → `allow` move at user level, not a new permission.** And `ask` is the thing that actually blocks parallel agents: `12` B8 records two ~90-minute stalls from prompting commands in briefs, with the finding *"a subagent waiting on a permission prompt is indistinguishable from a stalled one"* — and it names `git worktree` explicitly as a known prompter (*"that will always prompt"*). **Under unattended operation an `ask` is not a prompt, it is a stall.** This project already worked around it locally, which is why the friction never surfaced here.

**Two further things for the same review, both found while checking the above:**

1. **The prose rule is ambiguous about worktrees.** It forbids *"checkouts, merges, branches"* and a `git worktree add` creates a branch-shaped checkout, so an agent can reasonably read the prose as forbidding it even where the permission rules allow it. **Prose and rules should agree explicitly**, in whichever direction is decided.
2. **Worktrees are directly supported by the tooling.** Both the `Agent` and `Workflow` tools take `isolation: "worktree"` to give each agent its own tree, which is the mechanism for parallel agents on one codebase without collisions. Allowing them unlocks a capability, not just a command.

**The wider ask, which is the actual item: review the user-level git rules against TOO-45 experience.** Not just worktrees — the whole `~/.toolguard/rules/git.rules.toml` set, asking of each rule whether its level still matches how the work is actually done now, and specifically which `ask` rules are really stalls under unattended operation. **Arnon's call, not mine — this is his global config and it governs every project on the machine.**