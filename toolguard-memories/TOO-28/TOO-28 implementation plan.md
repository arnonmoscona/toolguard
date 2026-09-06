---
title: TOO-28 implementation plan
type: note
tags:
- task-memory
- TOO-28
- plan
permalink: toolguard/too-28/too-28-implementation-plan
---

# TOO-28 — implementation plan

**Status: DRAFT FOR REVIEW.** Written 2026-09-04 against `TOO-28 specification.md` (214 lines, signed off the same day). The spec settles *what and why*; this settles *how*, and nothing here may quietly change scope — where I think the spec is wrong, it is flagged in §7 rather than silently corrected.

**The raw touch-set estimate was sealed before this document existed** and has not been read by anyone. This plan is therefore uncontaminated by it, and it is the document the **informed** estimate will be taken against.

---

## 1. What the code already provides — four findings that shape the phasing

I read the relevant seams before planning. Three of these make the work smaller than the spec assumes and one makes a phase mostly investigation.

### 1.1 `permission_mode` is already parsed and threaded — but only to the log

It arrives on every `PreToolUse` call as §3 says, and `hook.py` already carries it through several call layers (`hook.py:458, 909, 991, 1064`) into `log_writer.LogRecord.permission_mode` (`log_writer.py:87, 237, 330`).

**It never reaches the decision.** The fallback resolvers (`config.py:1293 resolved_no_match_fallback`, `config.py:1324 resolved_undecidable_fallback`) take no mode argument, and their callers — `resolve.py:338`, `permission_resolution.py:409, 451`, `tools/takeover_audit.py:395, 426` — have no mode to pass.

So Phase 1 is **not** "plumb a new input from the hook payload". It is "make an already-present fact reach a different set of call sites".

**And that reframes the phase entirely — Arnon, 2026-09-05.** `permission_mode` is not one more parameter; it is invocation context, like `env_config`, `config`, `governed_tools` and `hook_data`, all of which `hook.py` already loads once and then passes selectively into `_handle_file_path_tool` and `_handle_command_tool`, which pass some of them further down and drop others. **Those signatures are fossils**: carrying the statics was never designed, so each one accreted where it was first needed.

Threading `permission_mode` through that same set would add a fifth fossil. The fix is to name the thing that already exists — one invocation-scoped object holding the statics — and Phase 1 becomes that refactor. **This is the last change that costs this many touch points**; afterwards a new invocation-wide fact touches the load point and the use points and nothing in between. Structurally the same move as the enrichment mechanism: one general carrier, so new meanings become new keys rather than new plumbing.

**Ambient singleton or explicit argument? Explicit, and this is not a style preference.** The tempting version is a module-level singleton that any function can reach, on the assumption that each hook evaluation is its own process. **That assumption is false today, not in some future.** `tools/corpus_build.py` drives a *fast in-process corpus* — thousands of decisions inside one process — and that harness is the instrument used to prove "zero decision flips" on every risky change. A singleton carrying invocation state would leak between cases there and produce a clean, plausible, wrong replay result **with nothing reporting it**. That is this project's signature failure mode, aimed squarely at the tool used to detect it.

So: construct the object once in `hook.py`, pass it as one argument. Signatures still get simpler (five statics collapse to one), tests still mock trivially, functions stay pure, and the replay harness stays honest by construction rather than by remembering to reset a global.

### 1.2 The rule-enrichment carrier exists, and both new fields fit it

`RuleEntry` already carries `metadata: Mapping[str, object]` (`rule_entry.py:131`), populated from the structured rule form `{ match = "Bash(*)", additionalContext = "x" }` (`rule_sort.py:173`). That is TOO-19's mechanism, and §10's scoping question — *does it already provide what is needed* — answers **yes**.

Both §4.2's `auto_mode` override and §4.3's input-source constraint are additional keys on an existing structured form. Neither needs a fifth pattern dialect, which is what §4.3 decided on other grounds; the code agrees with the decision.

### 1.3 §4.3's "new work" is already half-built

The spec says *"the per-interpreter file-flag detection above is new work."* **Partly false.** `_ExecutorFlags` (`command_extractor.py:~205`) already has:

```python
inline_letters, inline_long, value_letters, program_file_letters, bare_program
```

`program_file_letters` is exactly "this flag says the program is in a file" — populated today for `awk -f` and `php -F`. `bare_program` covers `awk '{...}' file`. The binary distinction §4.3 asks for is therefore **largely derivable from data that already exists**: an inline flag present means not-a-file; a `program_file_letters` flag or a bare positional program means file.

What is genuinely missing is **coverage, not mechanism**: `python script.py`, `node script.js`, `perl s.pl`, `ruby s.rb`, `Rscript s.R` and the `BASH_FAMILY` shells all take their program as a *positional* argument with no entry saying so. That is a table extension plus a resolution rule, not a new subsystem.

This is the single biggest sizing correction in the plan, and it moves Phase 4 from "new detection layer" to "complete an existing table and expose what it computes".

### 1.4 No grammar change is expected — but the two-phase rule stands by

File-vs-inline is decided by **interpreting tokens after the parse** (`command_extractor.py`), not by the PEG grammar, which produces the tree that extraction walks. So `.claude/rules/bash-grammar.md`'s mandatory two-phase procedure should not be triggered.

**This is a prediction, not a licence.** If design finds the grammar must change, Phase 4b splits: `.peg` plus canopy regeneration reviewed on its own, Python only afterwards. Nobody may implement grammar behaviour in Python because the plan said a change was unlikely.

### 1.5 The lists §4.3 calls a smell

Five, and my preliminary read is that they answer **different questions** and are not duplicates:

| list | location | question it answers |
|---|---|---|
| `BASH_FAMILY` | `command_extractor.py:150` | is this a shell whose `-c` takes a script? |
| `FOREIGN_EXECUTORS` | `command_extractor.py:164` | is this a non-shell interpreter whose inline code we cannot read? |
| `_EXECUTOR_FLAGS` | `command_extractor.py:246` | for this interpreter, which flags mean inline / value / program-file? |
| `COMMAND_WRAPPERS` | `command_extractor.py:265` | does this command run another command given as its arguments? |
| `_ARBITRARY_EXEC_INTERPRETERS` | `tools/danger.py:205` | is this dangerous arbitrary execution, for the audit tool? |

§4.3 says *look, establish what each was for, decide then* and warns that collapsing a deliberate distinction is worse than leaving them. **My recommendation is to leave all five**, with the finding written down so the question is not reopened a third time. Phase 4a produces that finding; it is the deliverable, not a refactor.

---

## 2. Phase plan

Each phase is one reviewable commit unless marked otherwise. Target size is **under ~300 changed lines including tests**; where a phase looks likely to exceed that, it is already split below.

### Phase 0 — DOWNGRADED 2026-09-05. No longer blocking; folds into Phase 6.

**The blocking question is answered, and not by this phase.** Spec §9 made the design contingent on whether a hook `allow` bypasses the classifier. Three independent lines now settle what actually matters:

1. **Documented**: a hook-forced prompt still shows in auto mode — *"auto mode still shows you those prompts"*. A toolguard `ask` binds.
2. **Documented**: *"a matching deny rule blocks the call"* regardless of the hook. A toolguard `deny` binds.
3. **Field-proven, in this repository**: `no_match_fallback = "allow_with_no_warnings"` was set as a `<TEMPORARY>` measure *because* toolguard ASKs were stalling unattended auto-mode runs. That is direct evidence that the ASK binds in auto mode — the whole reason the fallback exists.

Arnon, 2026-09-05: *"Auto-mode will not be able to execute anything that toolguard specifies as an ask or deny. That's already proven — that's exactly why we ended up having the temporary fallbacks the way they are."*

**What is left is not a design question but a documentation-accuracy one**: whether a hook `allow` skips the *classifier* changes what a user is opting into when they relax an ASK in auto mode. It does not change what gets built.

**And with the install flow now out of scope (Phase 6), it has no home in this ticket at all.** It belongs to the follow-up that touches the install flow and the security-audit skill, because that is where the answer would be acted on. **Recorded there as an open question rather than answered here** — writing a docs sentence about a mechanism nobody has tested would be worse than leaving the gap visible.

**Recommend amending spec §9** to lift "blocking prerequisite" status, with the three lines above as the reason.

The original phase text is kept below, because the reasoning is the record of how it was settled.

### Phase 0 (original) — settle the blocking prerequisite (§9). **Superseded.**

**Docs fetched 2026-09-05** from `https://code.claude.com/docs/en/permissions.md` and `https://code.claude.com/docs/en/permission-modes`, per the project's native-fidelity rule. The result **does not match the recollection on file**, so this phase gets more important rather than less.

**The documented order, quoted verbatim** from *how the classifier evaluates actions*:

> 1. Actions matching your allow, ask, or deny rules resolve immediately. [...]
> 2. Read-only actions and file edits in your working directory are auto-approved [...]
> 3. **Everything else goes to the classifier.**
> 4. If the classifier blocks, Claude receives the reason and tries an alternative.

So **rules resolve first and only the unresolved reaches the classifier** — the opposite of "the classifier runs before the hook and the hook is only invoked iff the classifier already allowed". That recollection was offered as `AFAIK` with an explicit invitation to re-check, and re-checking says it is inverted.

**Where hooks sit is not stated directly, but the doc groups them with allow rules in three separate places:**

> `rm` and `rmdir` removals targeting a critical path, **which no allow rule or `PreToolUse` hook `"allow"` approves**

> Claude Code never lets a `permissions.allow` rule **or a `PreToolUse` hook that returns `"allow"`** approve an `rm` or `rmdir` command that targets a critical path, even in modes that skip other prompts.

> [in `dontAsk`] Claude runs only actions matching your `permissions.allow` rules, read-only Bash commands, **and calls approved by a `PreToolUse` hook**.

Every mention treats a hook `allow` as a resolution mechanism of the same class as an allow rule, subject to the same circuit breaker. **The strong reading is that a hook `allow` resolves the action and the classifier never sees it** — which is exactly §9's feared case, now the documented default rather than the surprising one.

**One thing the recollection got right, and it is confirmed:**

> Claude Code doesn't add the option to prompts forced by one of your `ask` rules or by a hook, because **auto mode still shows you those prompts**

So a toolguard ASK is genuinely enforced in auto mode. Spec §7's retraction stands.

**`autoMode.classifyAllShell` appears in neither page.** §9 cites it as the mitigation; it is either renamed, removed, or was never on these pages. The current documented mechanism with the same purpose is different — see §9 of this plan.

**What the manual test must now settle**, since the docs establish the ordering but not the hook's exact position:

1. Does a toolguard `allow` cause the classifier to be skipped? Design: a command shape auto mode reliably refuses, harmless if it runs (observable is "did it execute", no side effect either way). Run with no toolguard rule, then with a toolguard `allow`. If it executes only in the second case, the hook allow skipped the classifier.
2. Does the hook run at all when the classifier would deny? Observable via toolguard's own log: an entry means the hook saw it.

Both are automated where possible and manual where not — per Arnon 2026-09-05, tests are always mandated, automated **and** manual.

**Blocks**: Phases 2 and 3. **Does not block**: Phases 1, 4, 5.

**Outcome if a hook allow does bypass** — now the expected outcome, not the contingency: relaxing ASK to `allow` in auto mode removes the *only* remaining gate for that command, because the classifier will not see it either. §4.1 and §4.2 remain buildable, but their **justification changes from "the classifier is a second gate" to "the user is asserting this needs no gate"**, and the install flow's wording must say that plainly. That is a scope conversation, not something to absorb.

### Phase 1 — the invocation-context refactor (§1.1). **Behaviour-neutral. Several commits.**

Not "thread `permission_mode`" but "give the statics a home, then put the mode in it". One object, constructed once in `hook.py`, holding `env_config`, `config`, `governed_tools`, `hook_data` and `permission_mode`; passed as a single explicit argument, **not** an ambient singleton — see §1.1 for why the in-process corpus makes that a correctness question rather than a taste one.

**Facts only, no behaviour.** The object holds what was loaded; it does not decide anything. The moment a method on it makes a decision, it stops being context and becomes a god object, and the next person cannot tell which of its callers depend on which of its behaviours.

**Respect the `config`/`resolve` seam.** Those two modules have zero import edges between them and call each other through an injected callback — 46,481 calls, measured. The context object must not become the thing that quietly creates the first import between them; hold `config` behind the same protocol/callback shape the seam already uses.

**Commit tranches, because one mechanical sweep is unreviewable:**

**Scope: the hook's invocation, not every module that loads config — measured 2026-09-05.** References to the four statics fall as: `hook.py` **77**, `tools/installer.py` 13, `config.py` 11, `config_validation.py` 8, `config_divergence.py` 5, then a thin tail of 1–3 each.

> **CORRECTED 2026-09-05.** Those counts grep only `env_config|governed_tools|hook_data` — they omit `config` and `agent_info` entirely, so they undercount by roughly half. Re-measured including all five: `hook.py` **167** before the migration and **153** after; `tools/installer.py` **42**. The proportions, and therefore the scope decision, are unchanged; the numbers were wrong. Recorded rather than quietly edited, because a count taken one link up the chain is this project's named first failure shape.

`pyproject.toml` declares **eight** console scripts. `toolguard.hook:main` is one of them; `installer`, `security_audit`, `maintenance`, `session_start`, `update_check`, `migrate_permissions` and `update_skills` are separate entry points with their own lifecycles, and `hook.py` imports none of them.

**So they are out.** An object named for one hook invocation has no meaning inside `toolguard-install`; putting them on it would be the god-object drift warned about above, arriving on day one. The refactor covers the hook decision path and stops there.

That also **removes a scope collision rather than excusing one**: Arnon ruled installer changes out of TOO-28, and `tools/installer.py` is the second-largest holder of these parameters. It is excluded on principle, not by exception.

**Commit tranches:**

- **1a** — define the context type, construct it in `hook.py`, pass it to `_handle_file_path_tool` and `_handle_command_tool` *alongside* the existing arguments. Nothing else changes. Small, and it makes the shape reviewable before anything depends on it.
- **1b** — `hook.py` itself, removing the now-redundant parameters. The largest tranche by far and the one to review hardest; 58% of all references live here.
- **1c** — `config.py`, `config_validation.py`, `config_divergence.py`.
- **1d** — the decision path proper: `resolve`, `permission_resolution`, `compound`, `parser/*`, `log_writer`.
- ~~**1z** — add `permission_mode` to the context.~~ **Already done in 1a**, which used it as the demonstration field. Struck 2026-09-05.

Non-hook entry points are untouched in every tranche.

### OUTCOME, 2026-09-05: 1b landed, 1c and 1d were EMPTY, and that changes Phase 2

**1b** reduced both handlers from six parameters to one (`_handle_file_path_tool(invocation)`), deleted the 1a aliases, and updated 9 test call sites — shape only, no assertion touched. Verified independently: 4021 tests, ruff clean, all three fitness checks, and the verdict corpus at 6401 in-process + 61 end-to-end with no differences, on a corpus calibrated by a planted `_DEFAULT_NO_MATCH_FALLBACK` change that made it fail and was then fully reverted.

**1c and 1d turned out to contain no work at all.** An AST scan of every module named in them found **zero** functions taking two or more of the statics as separate parameters: `compound.py` and `parser/*` reference none of them, and `resolve.py`, `permission_resolution.py` and `log_writer.py` each take at most one per function. There was no redundant parameter to remove.

**So Phase 1 did NOT deliver §3's goal, and the plan was wrong to expect it to.** `Invocation` is imported by `hook.py` and nothing else; `permission_mode` still does not reach the fallback resolvers or `_apply_ask_floor`. The plan conflated two different jobs under one phase:

- **removing fossil parameters** — mechanical, behaviour-neutral, reviewable in bulk. That was Phase 1, and it is done.
- **threading the mode down to the resolvers** — *adding* a parameter and a new import to modules that have neither, driven by a requirement that does not exist yet.

Those have opposite risk profiles, and doing the second one now would be building plumbing before knowing where the water goes: several of the target functions are called standalone from `test_resolve.py`, `test_logging_streams.py` and `test_hook_eval.py` with no `Invocation` in existence, so migrating them means rewriting tests to serve a requirement Phase 2 has not yet stated. **The deferral is the better call and the plan is amended to it.**

**Phase 2 therefore inherits the threading**, and one architectural finding with it: `_log_config_discovery`, `_resolve_takeover_mode`, `_run_divergence_check` and `_run_startup_validation` all run in `main()` **before** the `Invocation` is built. If Phase 2 wants them mode-aware, `main()` needs reordering — which is a design question to settle in Phase 2's planning, not to discover mid-implementation.

Six functions in `hook.py` remain genuine fossil-signature siblings by shape — the four above plus `_log_allowed_command` and `_log_non_allow_decision` — each blocked either by that ordering or by standalone test call sites. Recorded rather than fixed.

**Every tranche is behaviour-neutral and must prove it.** Corpus replay, re-scored as if `no_match_fallback` were `ask` — this repo sets `allow_with_no_warnings`, which makes an unmatched command an invisible allow and hides exactly the transitions a refactor could introduce. **Plant a change you know should appear and confirm the instrument shows it** before believing any null; a symmetric null from an uncalibrated instrument has already been used in this project to override a correct finding.

**Scope question for Arnon (§7.4)**: this is a behaviour-neutral refactor with a large blast radius and no dependency on TOO-28's semantics. It may deserve its own ticket.

### Phase 2 — two independent auto-mode fallbacks (§4.1)

Two settings, deliberately not one flag. Naming to be agreed in review; the spec's requirement is independence, not spelling.

Includes: config parsing and validation, level resolution consistent with the existing more-specific-wins rule, and `tools/takeover_audit.py` reporting the resolved values (it reads both resolvers today and would otherwise report a stale picture).

**§8 invariant, non-negotiable**: a test asserting the **parse-failure ASK is unaffected** by either new setting, in every combination. §8 requires this of *any* future flag touching fallback behaviour, so the test should be written to make the next such flag fail loudly rather than to cover only these two.

### Phase 3 — per-rule auto-mode override (§4.2)

One field, both directions (`ask`→`allow` widening, `ask`→`deny` narrowing), on the structured rule form via `RuleEntry.metadata`.

**On hard_deny — Arnon is right, and I checked. No decision-logic change.** `check_hard_deny` is called from `resolve.py:243`, *before* any matching happens, and `permission_resolution.py` states it explicitly: *"`hard_deny` denials are handled by the caller BEFORE any matching happens and never reach this function at all."* The cascade — where a per-rule auto-mode override would live — structurally cannot see a hard-denied command, so no override inside it can escape hard_deny. That is the property he asked for, and it already holds.

**And no validation change either — decided 2026-09-05.** I had proposed rejecting an `auto_mode` key inside `[hard_deny]` as a config error, on the grounds that silently ignoring it echoes the `config_write_guard` fail-open. **That analogy was wrong and I withdraw it**: the `config_write_guard` case fails *open* and invisibly — hard_deny silently stops protecting. Ignoring a mode key on a hard-deny entry fails *closed* and visibly: the command is denied anyway, and the author notices because the thing they tried to permit did not run. Same "silently ignored" shape, opposite safety direction, and only the direction matters.

Arnon's reason is the better one and it is about the concept, not the mechanism:

> *"Hard-deny should be trivial to understand with as little subtlety as feasible. It is intended for absolute denial as the name suggests. If you start adding modifiers it stops being 'hard'."*

**So: the key is ignored inside `[hard_deny]`, and that is documented.** No validator rule, no resolver change, no special case — the whole value of hard_deny is that there is nothing to reason about.

**Tests regardless** (tests are always mandated): a regression guard asserting a hard-denied command stays denied with an auto-mode override present on a matching allow, and on a `hard_deny.allow` carve-out. These assert an invariant that currently holds by structure — which is precisely the kind that a later refactor silently breaks.

**Live use**: the 2026-08-28 disclosure-nudge rule becomes an `ask` with an auto-mode override. Convert it in this phase and note it in release notes, since it changes this repo's own behaviour.

### Phase 4 — input-source constraint (§4.3). **Three commits.**

**4a — the list finding. Documentation, no behaviour change.** Establish and write down what each of the five lists in §1.5 is for. Recommend keep-or-merge with reasons. This is a deliverable in its own right because the question has now been raised twice and will be raised again.

**4b — complete the classification.** Extend `_ExecutorFlags` coverage so "the program is in a file" is answerable for every interpreter in `FOREIGN_EXECUTORS` and `BASH_FAMILY`, including positional-program cases. Resolution rule: an inline flag means not-a-file; a program-file flag or a bare positional program means file; a redirect *from* a file counts as a file, per §4.3.

Tests must cover the **negative** direction too — a rule that requires "is a file" must not fire on inline code, and vice versa. A rule that matches everything passes any list of positive cases.

**4c — expose it to rule authors.** The enrichment field, its validation, and its interaction with all four existing pattern types (it must compose with DEFAULT/REGEX/GLOB/NATIVE unchanged, which is why §4.3 chose enrichment over a fifth dialect).

### Phase 5 — the auto-mode gap log (§4.4). Depends only on Phase 1.

A **separate** log, not the decision log. Records the case "no rule matched **and** mode is auto": what was deferred, and what the mode was. Offline analysis only; nothing in the decision path reads it.

**Design note**: this is the one place where the "prose is output, not a data structure" rule bites hardest. Carry the structured decision through to the writer; do not render a sentence and re-parse it. TOO-45 measured 83% of compound-allow decisions under-logged for exactly that reason.

**Sequencing opinion — see §3.** This is the phase that produces evidence, and the project's own principle (§6.1) is that features follow evidence. There is a case for running it immediately after Phase 1.

### Phase 6 — documentation only (§4.5). **Scope cut 2026-09-05: no install flow, no bundled skills.**

Arnon, 2026-09-05: *"we're not modifying the install flow or any of the bundled skills in this ticket. If we need changes to the security audit — it will be in a different ticket."*

So §4.1's tail — *"Install, security-audit and possibly maintenance flows must become aware of the new configuration, and the install flow should explain it and seek the user's decision"* — is **out of this ticket**. In scope here is `docs/` prose and nothing under `skills/` or the install path.

- The division of labour from §2 written down, stating plainly that toolguard's blind spot is **by design** — currently written nowhere, verified 2026-08-03.
- The new settings framed as **handoff points**, never as "auto-mode variants".
- The design smell named explicitly: *"make toolguard smarter so it can handle X"*.
- A pointer early enough that someone orienting themselves meets it.
- The takeover-mode note from §9: under auto mode, broad native allow rules are dropped, so "native permits everything" does not describe auto mode.
- Then `/documentation-review`, per the project's pre-push checklist, because `docs/agent-map.md` summarises every other doc and has no other mechanism keeping it current.

**Two consequences of the cut, both recorded rather than absorbed:**

1. **The settings ship without an install-time explanation.** A user meets them in the docs or not at all until the follow-up lands. That is a deliberate, temporary gap, and the docs written here should carry the explanation the install flow would have given — which is cheap, since it has to be written anyway.
2. **The pre-push checklist asks two questions this ticket must now answer "yes, deferred" to**: *does this require updates to the maintenance or security-audit skill*, and *does it require updates to `install.md`*. Answering "no" would be false. **A deferred obligation recorded nowhere is this project's most-measured failure**, so the follow-up ticket should be filed when this plan is approved, not when the phase is reached.

### Phase 7 — remove the scaffolding (added 2026-09-05, Arnon)

> *"when we're done developing, it needs to be cleaned up and only comments and docstrings with long term value, concise and claims verified must stay."*

Development leaves notes-to-self in the code. They are useful while the work is in flight and worthless afterwards, and this project has measured what happens when they are left: **all 9 `RED:` markers were stale, and one propagated into a brief and misdirected an implementer.**

**Two distinct jobs, not one:**

**7a — delete pure scaffolding.** Comments whose entire content is "this is mid-refactor". They have no reader after the refactor. Current inventory, 2026-09-05:

| location | what it says |
|---|---|
| `hook.py:1016` | phase-1a note: other statics still arrive as parameters |
| `hook.py:1103` | *"see the note in _handle_file_path_tool"* — also a cross-reference, which drifts |
| `hook.py:1271` | *"TOO-28 changes that in a later phase; until then this comment is still accurate"* — **self-dating, and false the moment 1z lands** |
| `hook.py:1275` | phase-1a note on the construction site |

**7b — trim what survives to long-term value.** Not everything with a ticket number is scaffolding:

- `invocation.py`'s module docstring is long rationale — the in-process-corpus argument, the eight-console-scripts argument. **Per the project's own comment rules that belongs in the ticket, not the code**; the docstring keeps the rule ("explicit argument, not an ambient singleton") and drops the argument for it.
- `test_architecture.py:42` explains why the allow-list is empty. **That has lasting value** — it is what stops someone importing `config` into it. Keep the substance, drop the ticket reference.
- `hook.py:1271`'s underlying comment ("permission_mode is recorded for diagnosis, it never affects the verdict") is **made false by 1z** and must be rewritten then, not deleted now.

**7c — the frozen corpus is NOT in scope.** `test/verdict_corpus/` fixtures carry `# TEMPORARY until TOO-28 is done` on the two fallback settings. Those are a captured baseline; editing them would invalidate the goldens. Flag them at the `<TEMPORARY>` fence decision instead, and decide there whether the corpus is re-extracted.

### The mechanism, because a cleanup phase is exactly the kind of prose that gets dropped

Prose saying "remember to clean up" has a measured failure rate here. Three instruments, and they catch different things:

1. **One uniform token on every scaffolding comment: `TOO-28-SCAFFOLD`.** Today's markers were worded four different ways and no single grep found them. A token makes the inventory a command rather than a memory. Retrofitted 2026-09-05; currently `hook.py:1016, 1103, 1272`.
2. **A test asserting `toolguard/` contains none of it**, carrying `@unittest.expectedFailure` while scaffolding exists. When Phase 7 removes the last marker the test *unexpectedly succeeds*, which unittest reports as a failing run, forcing the decorator off. **The check clears itself.**
3. **The baseline tag — `TOO-28-start-of-work`, at `25022a6` (Arnon, 2026-09-05).** This is the one that catches what the other two cannot.

**Why the tag matters more than the token.** The token only finds scaffolding somebody *remembered to mark*. Phase 7b's real problem is the opposite: comments edited or added in passing, by an author who did not think of them as temporary. Those carry no marker by definition, so no grep can enumerate them — but a diff can.

```bash
git diff TOO-28-start-of-work..HEAD --stat -- '*.py'          # which files at all
git diff TOO-28-start-of-work..HEAD -- '*.py' | grep -E '^\+\s*#'   # every comment line added
git diff TOO-28-start-of-work..HEAD -- '*.py'                  # read the docstring hunks
```

Every added or changed comment gets one question, from the project's own rules: **will this still be worth reading in a year, to someone who never saw the ticket?** Then the narrower ones — does it explain what the code plainly says; does it document what static analysis already finds; is the claim in it still true.

**The tag has a second job, and it is the more important one.** It is the scoring baseline for the touch-set experiment: the actual changed-file set for both sealed estimates is `git diff --name-only TOO-28-start-of-work..HEAD`. The tag, the raw estimate's `tree.commit` and the informed estimate's `tree.commit` are the same commit, so the baseline is exact rather than reconstructed. **Recorded here because a tag nobody wrote down is a tag nobody finds** — and this repository has already lost the pre-seal bytes of the spec for want of a commit.

---

## 3. Ordering, and the one choice I would put to you

Dependencies: **Phase 1 gates everything, and is now the only gate** — Phase 0 was downgraded on 2026-09-05 and blocks nothing.

**Order: 1 → 5 → 2 → 3 → 4a → 4b → 4c → 6 → 7.**

Phase 7 is last by necessity: it removes scaffolding, and scaffolding is load-bearing until the phase that needed it has landed.

The non-obvious move is **5 before 2 and 3**. Reasons:

- It starts producing evidence about what the auto-mode classifier actually permits, which is the input §4.1 and §4.2 are ultimately tuned against. Building the tuning knobs before the instrument that tells you where to set them is the wrong order.
- It is independent of Phase 0's answer, so it makes progress while the prerequisite is unresolved.
- §4.4 is the feedback loop for the half of §2 that has none. Everything else in this ticket is a knob.

**The argument against**, which is real: it delays the capability that motivated the ticket — the unattended-run stall — by two phases. If relieving that stall is the near-term goal, run 2 and 3 first and take 5 later.

**This is a judgement about what the ticket is for, so it is yours.**

---

## 4. Where the informed estimate goes, and what this item can and cannot measure

Between agreement on this plan and the start of Phase 1. Stage `informed`, `blinded: false`, `saw` including `plan`. Taken against **this document**, not the spec. Do not start Phase 1 before it is sealed.

### This item will not measure predictive value, and that is now known in advance

Arnon, 2026-09-05:

> *"the refactor would make the surprise factor pretty much useless and an analytical result — it would make every file change trivially. So using this as a verification of the surprise factor here is not going to add knowledge. It would validate that the process of the surprise factor plugin enforcement works though."*

Correct, and it follows from the refactor's nature rather than from anything about the estimator: once "every module that takes those five statics" is the touch set, the informed prediction is a derivation, not a forecast. A near-perfect score here would be an artefact of the question, not evidence about the instrument.

**So this item's value is process validation** — the sandbox, the seal, the clean-scope gate, the record schema, the ordering discipline — and it should be reported that way rather than as a data point about accuracy. Pooling it with items where prediction was genuinely uncertain would inflate the aggregate.

### The consequence that needs recording, or the item becomes actively misleading

**The raw estimate was sealed on 2026-09-04 against a spec that contained no refactor.** The refactor entered on 2026-09-05, during planning. So the raw estimate will show a large under-prediction whose cause is **a requirement that moved after sealing**, not an estimator that failed.

Left unlabelled, that is the worst possible outcome for this experiment: a huge apparent miss, landing straight in the bad-surprise tail, triggering a review that finds nothing wrong — the exact false positive that would discredit the tail as a signal.

**The schema already anticipated this**, which is a small vindication of recording primitives rather than conclusions:

- `SCOPE_CHANGES = ("up", "down", "unchanged", "killed")` — this item is **`up`**.
- Surprise cause **`R`**: *"requirement added or changed after the estimate was sealed — a moving target"*, deliberately kept distinct from `S` (scope creep) because *"S is a discipline signal and R is a scope-change signal that should agree with the outcome's `scope_change_during_planning`"*.

So: every file the refactor touches that the raw estimate missed is cause `R`, and `scope_change_during_planning: "up"`. Both are already required fields. **Nothing needs to be built and nothing needs to be excluded** — the item is recorded honestly and the analysis decides later what to pool.

That is worth noting as its own small finding: this is the first live case of the moving-target scenario, and the primitives handled it without a schema change.

---

## 5. Review checkpoints

Every phase ends with: full suite green, `ruff check` and `ruff format`, and the three architecture-fitness runs (`--stdlib`, `--ambient`, `--layers`). Then the what-vs-how question the checklist says no tool can answer — *is this about what to do or how to do it, and is it stable under maintenance?*

Additionally:

- **Phase 1**: corpus replay, re-scored as if `no_match_fallback` were `ask`, with a planted change proving the instrument is sensitive. A null result from an uncalibrated instrument is not evidence.
- **Phases 2, 3**: `code-reviewer` subagent before commit, since both change decision semantics.
- **Phase 4b**: the negative-direction tests above are the review's first question.
- **Before push**: coverage, version bump, release notes, `pyscn analyze`, and the `<TEMPORARY>` fence in `.claude/toolguard_hook.toml` — the TOO-45 guards it holds are due a keep-or-drop decision, and the fence goes either way.

---

## 6. Risks

| risk | why it matters | handling |
|---|---|---|
| Phase 0 inverts the rationale | §4.1/§4.2 would remove two gates rather than one | it is Phase 0 precisely so this is found before code exists |
| Mode-awareness spreads through the code as a parameter | six signatures grow an argument and the seam blurs | the Phase 1 context object; `--layers` plus the what-vs-how question at the Phase 1 review |
| The context object is made ambient "because each hook run is its own process" | false today: `tools/corpus_build.py` runs thousands of decisions in one process, so state would leak into the very harness used to prove no behaviour changed — silently | explicit argument, decided in §1.1; no module-level instance exists to reach for |
| The Phase 1 refactor lands as one unreviewable sweep | a mechanical diff across the package is where a behaviour change hides best | tranches 1a..1z, each behaviour-neutral, each replay-verified against a calibrated instrument |
| The context object grows behaviour | it becomes a god object and callers' dependencies become untraceable | facts only, asserted at review; a method that decides anything is the signal |
| A future flag quietly relaxes parse-failure | genuine silent-allow, invisible forever | §8 test written to catch the *next* flag, not only these two |
| Consolidating the five lists breaks a deliberate distinction | §4.3 warns of exactly this | 4a is a finding; any merge is a separate decision with the finding in hand |
| The separate log re-derives structure from prose | measured 83% under-logging in TOO-45 | structured result carried to the writer; asserted by test |
| Scope creep from TOO-40 / TOO-19 | both are adjacent and inviting | TOO-40 is out by §6.2; TOO-19's carrier is used as-is, not extended |

---

## 7. Where I think the spec is wrong, or should be amended

Flagged rather than acted on.

1. **§4.3, "the per-interpreter file-flag detection above is new work"** — partly false. `program_file_letters` and `bare_program` exist and are populated for `awk` and `php`. The work is completing coverage and exposing the result, not building detection. **Recommend amending the spec** so the informed estimate is taken against an accurate statement.
2. **§4.3's list smell** — my preliminary read (§1.5) is that all five lists answer different questions. Recorded here as a prior, not a conclusion; 4a is still the phase that decides.
3. **§9 cites `autoMode.classifyAllShell`, which appears in neither current doc page** (fetched 2026-09-05). Renamed, removed, or never there. The current mechanism serving the same purpose is the auto-mode allow-rule dropping described in §9 of this plan. **Recommend amending the spec**, and treating this as a worked example of why `[native]` fidelity is a claim with a date on it.

5. **§9's "blocking prerequisite" status should be lifted.** Settled 2026-09-05 by documentation plus this repository's own `<TEMPORARY>` fallback, which exists because toolguard ASKs stalled unattended auto-mode runs. Nothing in the design is contingent any more. **Recommend amending the spec** so the informed estimate is taken against a plan with no phantom gate in it.

6. **§4.1's tail is out of scope — decided 2026-09-05.** *"Install, security-audit and possibly maintenance flows must become aware of the new configuration, and the install flow should explain it and seek the user's decision rather than choosing for them"* moves to a follow-up ticket. **Recommend amending the spec**, because this one is a *requirement* being deferred rather than a wrong statement being fixed, and an unamended spec would leave the ticket permanently unfinishable against its own text.
4. **The invocation-context refactor stays in TOO-28 — decided 2026-09-05.** Not its own ticket: many touch points, but *"very simple in logic"*, no external behaviour change. It gets its own review and its own commit, and **replay behaviour must be identical with no change** — tests may change, decisions may not.

---

## 8. Not in this plan, deliberately

Anything §5 cut (the classifier), TOO-40, TOO-18, and any extension of TOO-19's enrichment mechanism beyond adding keys to it. If a phase starts to need one of these, that is a scope conversation, not an implementation detail.

---

## 9. CLOSED 2026-09-05 — not a defect. One claim corrected, one documentation item carried into Phase 6.

**Closed by Arnon, 2026-09-05**: *"Toolguard works the way we want it to work. The hook spec read does not change it. We intentionally make sure that there is no real competition in practice by using takeover mode combined with auto-migration."*

The net effect of auto mode dropping broad native allows is that fewer actions resolve at the native step and more reach the classifier — **more scrutiny, never less** — while toolguard's own `ask` and `deny` bind either way. No security gap, no ticket to file. What remains is one sentence of documentation (below), carried into Phase 6.

The analysis is retained because the corrected claim about hook semantics is load-bearing for how takeover mode is described.

**Arnon's position, and it settles the main question:** Claude Code's auto mode is unaware of toolguard, and that is deliberate. The toolguard config is authoritative regardless of what auto mode does, for both tightening and broadening. Takeover mode deliberately configures Claude Code as a broad allow for everything precisely so toolguard is the gate.

That disposes of my §9 alarm as originally written. What follows is what survives it.

### The one claim the docs contradict

> *"As far as I understand the behavior of a preToolUse hook is that it can only tighten."*

**Not as stated.** From `permissions.md`, fetched 2026-09-05:

> PreToolUse hooks run before the permission prompt [...] The hook output can deny the tool call, force a prompt, or **skip the prompt to let the call proceed**.

Skipping a prompt that would otherwise happen is broadening. The `dontAsk` description says the same from another angle: in a mode that auto-denies everything that would prompt, *"Claude runs only actions matching your `permissions.allow` rules, read-only Bash commands, **and calls approved by a `PreToolUse` hook**."* A hook allow causes execution there.

**But the broadening is bounded, and this is the half the intuition got right:**

> **Hook decisions don't bypass permission rules.** Claude Code evaluates deny and ask rules regardless of what a PreToolUse hook returns: a matching deny rule blocks the call, and a matching ask rule still prompts even when the hook returned `"allow"` or `"ask"`.

So a hook allow cannot override a native deny or a native ask. It can only skip a *prompt*. The practical consequence — you cannot get an allow out of "auto-mode denies, toolguard allows" — holds; the mechanism is not "hooks only tighten".

**Why the precise version matters**: takeover mode's whole design rests on where a hook allow can and cannot reach. "Only tightens" would mean a broad toolguard allow is harmless by construction. It is not harmless by construction; it is bounded by native deny/ask rules, which is a different guarantee and one that depends on the native config actually carrying them.

### The wrinkle that does survive, and it is about takeover mode

Auto mode drops broad native allow rules on entry:

> On entering auto mode, broad allow rules that grant arbitrary code execution are dropped: Blanket `Bash(*)` or `PowerShell(*)`; Wildcarded interpreters like `Bash(python*)`; Package-manager run commands; `Agent` allow rules; `Monitor` allow rules [...] Narrow rules like `Bash(npm test)` stay in effect.

**Takeover mode's deliberate broad native allow is exactly the shape that gets dropped.** So in auto mode, the native config toolguard assumes is wide open may not be — which means the premise "native permits everything, toolguard is the only gate" does not hold there. The direction is safe (more actions reach the classifier, not fewer), but toolguard's documented model of takeover mode would be inaccurate under auto mode, and §4.5's documentation is the natural place to say so.

**Still unsettled, and only a test decides it**: whether a hook `allow` skips the auto-mode *classifier*, not just the prompt. The docs say hooks run "before the permission prompt", and in auto mode the classifier reviews actions "instead of you" — so skip-the-prompt plausibly means skip-the-classifier, but that is inference from two sentences on different pages. It stays in Phase 0.

### Superseded — the original finding, kept for the record

While fetching the docs for Phase 0 I hit something adjacent and, I think, more consequential than the question I went looking for. Quoted verbatim, `permission-modes`, fetched 2026-09-05:

> On entering auto mode, broad allow rules that grant arbitrary code execution are dropped:
> * Blanket `Bash(*)` or `PowerShell(*)`
> * Wildcarded interpreters like `Bash(python*)`
> * Package-manager run commands
> * `Agent` allow rules
> * `Monitor` allow rules [...]
>
> Narrow rules like `Bash(npm test)` stay in effect. Claude Code restores the dropped rules when you leave auto mode.

**Claude Code deliberately disarms broad native allow rules in auto mode**, precisely so they cannot approve arbitrary execution without the classifier seeing it. That is a designed safety behaviour with a named threat model.

**toolguard's allows are hook decisions, not native rules, so nothing drops them.** A broad toolguard allow keeps approving in auto mode, and — per the ordering in Phase 0 — a hook `allow` appears to resolve the action without the classifier. The net effect is that **governing a project with toolguard may quietly re-open the exact hole auto mode closes**, and the more faithfully toolguard mirrors native allow syntax, the more likely a user has written such a rule.

Three reasons this belongs on the record now rather than later:

- It is a **direction the spec does not consider at all**. §4.1 and §4.2 are about *relaxing* toolguard in auto mode; this says toolguard may already be too permissive there, before any relaxation ships.
- It bears directly on the project's own fidelity principle: `auto_migrate` imports rules Claude Code authored, written against semantics where broad allows get dropped in auto mode. Imported into toolguard, they do not. **A divergence that is silently more permissive is the defect shape the fidelity rule exists to catch.**
- It is exactly the sort of thing the §4.4 data-collection log would surface — another argument for the ordering in §3.

**Recommendation**: verify it in Phase 0 (the test design already covers the mechanism), then file it separately rather than absorbing it. It is not what TOO-28 is about, and folding a second security question into this ticket would make both harder to review.

**Confidence, stated honestly**: the "rules resolve first" ordering and the allow-rule dropping are quoted; the claim that a *hook* allow behaves like an allow rule for classifier-skipping is a **strong inference from three groupings in the doc, not a quoted statement**. It needs the manual test before anyone acts on it.
