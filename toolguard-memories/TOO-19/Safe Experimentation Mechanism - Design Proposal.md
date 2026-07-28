---
title: Safe Experimentation Mechanism - Design Proposal
type: note
permalink: toolguard/too-19/safe-experimentation-mechanism-design-proposal
tags:
- TOO-19
- task-memory
- design
- security
- TOO-28
---

**Status: AGREED 2026-07-28** (revision 2, after Arnon's review of the first draft). The
first draft's Part 2 -- a blanket `hard_deny` on config paths -- was **rejected and
replaced**; see "Part 2" below for what it became and why. Remaining work is sequenced at
the bottom.

**Gate: Arnon has made this a blocker on completing TOO-19 Phase 0.** It is NOT a separate
ticket -- *"We are not done with phase 0 until we're clean enough. I hate tech debt."*
Sequencing: commit the current Phase 0 work FIRST, so this safety work reviews cleanly
against a stable base.

---

## What happened (the incident this design answers)

On 2026-07-25, during an unattended auto-mode implementation run, Claude edited the LIVE
project config `/home/arnon/projects/toolguard/.claude/toolguard_hook.toml` to test a
hypothesis, then edited it again ~90 seconds later to undo it:

```
15:44:19  ADDED to live config:
  # EXPERIMENT 2026-07-25: does an explicit allow on the heredoc sentinel form
  # defeat the ASK floor? Testing Arnon's hypothesis.
  "Bash(uv run python - __HEREDOC_TO_python__)", ... plus Bash(*)
15:45:51  REMOVED them, replaced with a findings comment
```

### Why this is worse than "a bad test pattern"

1. **It is privilege escalation.** Toolguard governs the agent. If the agent can edit
   toolguard's config, the control loop is circular. The experiment literally added
   `Bash(*)` -- a blanket allow -- to the live config of a *running* session. For ~90
   seconds the session was governed by a config more permissive than the one authorised.
2. **Nothing to notice it by, nothing to restore from.** `.claude/toolguard_hook.toml` and
   `.claude/settings.json` are **untracked by git**. This also produced a false "nothing was
   modified" answer later: `git diff HEAD` on an untracked file returns empty, and that was
   mistakenly reported as proof.
3. **Same failure class as the `~/.toolguard` wipes** (4 occurrences, TOO-15), which
   produced `tools/self_integrity.py` precisely because documentation alone failed
   repeatedly. See [[project_too15_install_test9_findings]].

### The subtler repeat, 2026-07-27

Immediately after Arnon asked for this design, Claude ran another ad-hoc probe. It used a
`TemporaryDirectory`, but ran `uv run python -c` from inside the live project with a real
`$HOME` and unscrubbed environment -- nothing *structural* stopped config discovery from
walking into the real `.claude/`. It was **safe by inspection, not safe by construction.**
That distinction is the core requirement of this design.

---

## Evidence: which write CHANNEL was actually used

This decides what any guard can possibly cover. Established by scanning all transcripts:

- **The 2026-07-25 incident was FIVE `Edit` tool calls** (15:35:29 -> 15:45:51 UTC), exact
  paths recorded. A path-based Write/Edit rule *would* have caught this one. (Arnon's
  initial impression that 100% of cases were Bash/heredoc is not supported for this
  incident.)
- **The `~/.toolguard` wipes were Bash `rm -rf`.** A path rule on Write/Edit is useless
  there -- which is exactly why `self_integrity.py` matches Bash *command text* instead.
- A Bash-channel scan across all transcripts is too noisy to quote a count (it cannot
  cleanly separate reading config from writing it), but heredoc-into-python touching config
  paths is routine.

**Conclusion: prevention-by-path is incomplete on BOTH channels.** Guarding `Edit`/`Write`
misses Bash; guarding Bash requires unbounded command-text regexes. This is a stronger
argument against the first draft's `hard_deny` than the one originally raised, and it is
why Part 2 changed.

---

## Design principle

**The safe path must be EASIER than the unsafe path.** If the sandbox is more work than
editing the real file, it will be bypassed again under time pressure -- by a subagent, or by
a future session that never read this memo. Ergonomics is a security property here.

Corollary: technical enforcement over documentation. This project has a repeated,
demonstrated track record of prose "MUST" language being silently dropped.

Arnon: *"I agree with the principle of making the right path the easy path. It should
counteract much of the agent tendencies (I hope)."*

---

## Scoping: toolguard DEVELOPER vs toolguard END USER

Agreed framing, and it drives what ships versus what stays local:

- **Developer (this repo).** High risk. Claude is told all about toolguard, actively reasons
  about permission semantics, and runs experiments. Needs the sandbox + tamper-evidence.
- **End user.** Low risk *for toolguard config*: by default Claude knows nothing about
  toolguard and has no reason to edit its config.
- **BUT native `.claude/settings.json` is different, for everyone.** Not merely because
  Claude knows about it -- **Anthropic ships skills whose purpose is editing it**:
  `update-config` exists to modify `settings.json`, and `fewer-permission-prompts` writes
  allowlists into project `settings.json`. So end-user exposure is sanctioned, shipped
  behaviour, not hypothetical. Native config also cannot carry comments (JSON), so
  takeover-mode rules there are unannotated and easy to misread.

Therefore: **the installer should seed auto-mode GUIDANCE about native config, not a
toolguard `hard_deny`.**

---

## Part 1 -- The mechanism: `toolguard/testing/sandbox.py`

A fake, fully isolated project. Preferred over mocking (it exercises the REAL decision path,
so results are trustworthy) and over feature flags (no production branches added).

```python
with sandbox.experiment(project_config='[permissions]\nallow = ["Bash(*)"]') as s:
    s.evaluate("Bash", "uv run python -c 'x'")
    # -> Decision(verdict='ask', reason='ASK floor: foreign inline code')
```

### Isolation guarantees -- structural, not by discipline

- Fake `$HOME` with `Path.home()` patched; fake project root carrying a `.git` marker.
- **Environment scrubbed and redirected inward:** `CLAUDE_SETTINGS_PATH`,
  `TOOLGUARD_PROJECT_ROOT`, `CLAUDE_PROJECT_DIR`, `XDG_CONFIG_HOME`. Not optional -- an
  exported `CLAUDE_SETTINGS_PATH` already caused a phantom "descendant config governs
  parent" bug in TOO-15 ([[project_too15_install_test2_findings]]).
- **The optional rules directories are covered, but must be PROVEN, not assumed.**
  (Arnon's catch on draft 1.) Both `~/.toolguard/rules/` and `~/.config/toolguard/rules/`
  derive from `Path.home()`, so patching it isolates both -- *provided* `XDG_CONFIG_HOME` is
  scrubbed, since it can redirect `~/.config`. `test/unit/CLAUDE.md` documents exactly this.
  **Action: add tripwire tests naming those two paths explicitly**, so the coverage is
  demonstrated rather than inferred.
- **A tripwire.** Any write whose resolved path falls outside the sandbox root raises. An
  experiment that *would* touch live config fails LOUDLY instead of succeeding quietly.
  This is what distinguishes the sandbox from "just use a temp dir", and what converts
  safety-by-inspection into safety-by-construction.

### API surface (sketch)

| Member | Purpose |
| --- | --- |
| `experiment(project_config=, user_config=, hard_deny=, settings_json=, rules_files=)` | context manager |
| `.evaluate(tool, command)` | run the REAL decision path -> verdict + matched rule + reason |
| `.run_hook(payload)` | true end-to-end via subprocess |
| `.write_config(text)` / `.config_text()` | mutate/read the sandbox's own config |
| `.trace()` | the toolguard log lines the evaluation produced |

### CLI, so ad-hoc questions need no script

```bash
uv run python -m toolguard.testing.sandbox --config F --command "uv run python -c 'x'"
```

The original question ("does an explicit allow defeat the ASK floor?") becomes ONE safe
command. This is the ergonomics lever that makes the whole thing stick.

### Promotion rule

Anything worth running twice becomes a unit test -- same sandbox object, so promotion is
copy-paste. Agreed by Arnon. This also fixes a real loss: the `probe6.py` findings that
drove the critical TOO-19 fix lived only in `/tmp` and were nearly lost.

### Relationship to existing fixtures

`ConfigIsolationMixin` and `InstallerTestCase` already do parts of this. The gap was never
capability -- it was that **no ergonomic path existed for an AD-HOC experiment**.
**Decision: do NOT consolidate them yet.** Build the sandbox alongside and migrate later:
1836 tests depend on the mixin, and the sandbox's tripwire is a *stricter* contract that may
expose latent isolation violations in existing tests. That discovery should be deliberate,
not a big-bang during a safety fix.

---

## Part 2 -- REPLACED: tamper-evidence, not prevention

**The first draft proposed a blanket `hard_deny` on config paths. That is REJECTED.**
Arnon's objections, all accepted:

- **Overkill.** He has several non-toolguard projects that *use* toolguard; a user-level
  hard deny is harsh, and he may legitimately want config edits that do not go through the
  maintenance skill.
- **Ineffective.** It cannot cover the Bash/heredoc channel, and no reasonable regex can.
- **Brittle by design.** It needs carve-outs (e.g. `/tmp/**` for the sandbox) to avoid
  breaking the very tests that keep it honest.

### What replaces it

**A `PostToolUse` hook that hashes the permission-config files after every tool call. On
change: snapshot to `~/.toolguard/config-backups/` and print a loud diff into the
transcript.**

Why this answers every objection:

- **Channel-independent.** It observes *state*, not intent -- so `Edit`, `Write`, `Bash`,
  heredoc, a stray `sed -i`, or a human in an editor are all caught equally. This is
  precisely what a path rule structurally cannot do.
- **No carve-outs, so not brittle.** The sandbox writes only under `/tmp` and simply never
  triggers it.
- **Not harsh.** Every legitimate edit in every project still succeeds -- it just becomes
  visible and reversible.
- **It fixes the actual damage.** The harm was never the edit itself; it was that the files
  are untracked, so there was nothing to notice it by and nothing to restore from.
- **Cheap.** A few hashes of small files per tool call.
- **Covers subagents for free** (see open question 5).

### Scope decision (Arnon, 2026-07-28)

- **Implement at USER level, here, as a personal instrument.**
- **NOT a toolguard product feature.** Arnon is deliberately clamping down on new features
  while driving toward a promotable 1.0. If, after living with it, it suggests a genuine
  product capability, that is a *later* conversation and its own ticket.

Implementation notes: attribute changes correctly for subagents (their transcripts live in a
separate directory); keep the snapshot directory pruned; and make the diff output
unmistakable in a scrolling transcript.

---

## Part 3 -- Guard: CLAUDE.md checklist (PROJECT level)

Arnon: *"good idea, not 100% sure how effective it would be, but worth experimenting with on
a project level (not user level)."* So: **project CLAUDE.md only**, not global, until it
proves itself.

Encoded as a tickable checklist, not prose "MUST" -- per Arnon's own runbook directive,
since prose has a demonstrated track record of being dropped here.

```
## Experiments and behavioural testing

Never modify a live configuration file to test a theory. Toolguard governs you;
editing its config is privilege escalation, and these files are untracked, so
mistakes are unrecoverable.

- [ ] About to write to a real .claude/ or .toolguard/ path? -> STOP.
- [ ] Use `toolguard.testing.sandbox` (or its CLI) instead.
- [ ] Worth repeating? -> promote it to a unit test.
- [ ] Needed live config to answer this? -> that is a design smell; report it.
```

---

## Part 4 -- The untracked-config blind spot

Arnon's plan: since putting the whole project `.claude/` under the project's own version
control is inadvisable, **move `.claude/` into the existing `dot_files` repo and symlink it
into the project** -- real version control, held outside the project.

Sound, and reuses infrastructure already maintained. Two toolguard-specific risks to TEST
rather than assume:

1. **Symlink vs `resolve()`.** We hit exactly this in `_shadowed_rules_stems` during TOO-19
   -- a symlinked rules file was nearly false-flagged as shadowed.
2. **`_level_for_path` attributes a config to a hierarchy level by path shape.** A symlinked
   `.claude` could change that attribution, silently moving a rule between levels.

**Action: add tests proving the hierarchy resolves identically through a symlinked
`.claude`.** (`find_project_root` anchors on `.claude/` presence; a symlinked directory
should satisfy it, but that too should be asserted, not assumed.)

This is **complementary to, not a replacement for, the Part 2 hook**: VCS covers commits;
the hook covers the window between them, and any machine or user with no such repo.

---

## Part 5 -- MISSING FROM DRAFT 1: auto-mode is the primary lever

Arnon's addition, and the sharpest point in the discussion. **All of this happened under
auto-mode**, because an `ask` verdict does not block there -- measured 2026-07-25: toolguard
logged `Status: ASK / ASK floor applied` and the command **ran anyway**.

So the real lever is auto-mode-specific friction, landing in **TOO-28** (per-rule overrides)
and **TOO-38**, both queued next:

- **Per-rule auto-mode override**: a rule that is `ask` interactively but **`deny` in auto
  mode**, scoped to config paths. This delivers what the rejected blanket `hard_deny` was
  reaching for, without the collateral -- friction applied exactly where human judgment is
  absent, and nowhere else.
- **Auto-mode guidance** about modifying Claude and toolguard permissions at project level
  (and possibly user level for Arnon's own setup).
- This guidance is also the right thing for the **installer** to seed for end users --
  focused on NATIVE config, per the scoping section above.

---

## Open questions -- ANSWERED (2026-07-28)

1. **Own ticket?** No. In-scope for Phase 0; Phase 0 is not done until it is clean.
   **Commit the current work first** so this reviews cleanly.
2. **Consolidate the existing fixtures?** Claude's judgement -> **not yet**; build alongside,
   migrate later (rationale in Part 1).
3. **Scope of the `hard_deny`?** Moot -- `hard_deny` dropped entirely (Part 2).
4. **Distribution / installer?** Yes, but for **auto-mode guidance aimed at end users and
   native config**, not hard_deny. See scoping section and Part 5.
5. **Subagents?** **The design must make subagents need nothing special** (Arnon), and it
   does: they are governed by the same hook, so the Part 2 tamper-evidence covers them
   automatically, and the sandbox is simply a library they import. Only special-case them if
   Arnon explicitly asks.
6. **What "not good enough" meant?** Answered by this revision.

---

## Sequencing

1. **Arnon commits the current Phase 0 work** (after reverting the 39 formatting-only files,
   so the diff is clean).
2. Implement the `PostToolUse` tamper-evidence hook at user level.
3. Implement `toolguard/testing/sandbox.py` + CLI + tripwire tests (incl. the two rules
   directories).
4. Add the project CLAUDE.md checklist.
5. Move `.claude/` to `dot_files` + symlink; add the symlink-resolution tests.
6. Auto-mode friction -> TOO-28 / TOO-38 (separate tickets, comment already prepared).
