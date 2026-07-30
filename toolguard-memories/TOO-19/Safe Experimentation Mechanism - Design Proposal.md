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

### Scope decision -- REVISED 2026-07-28 (supersedes the "personal instrument" call)

Arnon: *"the PostToolUse for tamper evidence hook should really be a documented, but
unwired feature of toolguard to start with. Therefore it should be configurable about what
is being tracked (directories, files)."*

So it becomes **a first-class toolguard feature that ships wired to nothing**:

| Ships | Does NOT ship |
| --- | --- |
| The module, fully unit tested | Any entry in anyone's `settings.json` |
| A console-script entry point | Any installer step that wires it |
| A `[tamper_evidence]` config section (absent = inert) | Any default-on behaviour |
| `docs/tamper-evidence.md`, linked from the doc graph | A migration that adds the section |

**Why this is better than the personal-instrument version**, and why the reversal is right:
a personal script has no tests, no docs, one user, and dies at the next machine rebuild --
yet it would still have carried all the design risk below (baseline lifecycle, de-listing,
snapshot secrecy). Shipping it unwired costs the same design work, adds test and doc cost
only, and buys correctness plus a second pair of eyes. The 1.0-scope worry is really about
*surface area users must understand*, and an absent config section has none.

**The honest cost**, so it is chosen with open eyes: an unwired feature is still a
maintenance obligation and still appears in the docs, the audit surface, and the config
schema. It is not free -- it is just much cheaper than it looks, because the expensive part
(getting the semantics right) is not optional either way.

### Module layout (respects the layering DAG enforced by `test_architecture.py`)

- **`toolguard/tamper_evidence.py`** -- pure leaf, **stdlib only, no toolguard imports**:
  hashing, the baseline manifest, snapshot write/prune, diff rendering. Every interesting
  decision lives here, so nearly all tests are plain function tests with a `tmp_path`.
- **`toolguard/tools/tamper_check.py`** -- the adapter: resolves the watchlist from
  `Configuration`, parses the PostToolUse stdin payload, emits output. Thin by design.
- **`toolguard-tamper-check`** console script -> `toolguard.tools.tamper_check:main`.

Deliberately **not** imported by `toolguard/hook.py`. The PreToolUse hot path stays
untouched; this runs as its own process on the PostToolUse event.

### Configuration

A new `[tamper_evidence]` table in `toolguard_hook.toml` (TOML only -- this is a toolguard
extension and has no native equivalent, so it must never be written into
`settings.json`; add it to the `config_sync` / `config_divergence` exclusions and to
`config_validation`'s known-section set, or it will be reported as an unknown key).

```toml
[tamper_evidence]
enabled = true

# What to watch. Absolute paths, ~ expansion, and globs. Two placeholders:
#   {project} -> the resolved project root
#   {home}    -> Path.home()
watch = [
    "{home}/.claude/settings.json",
    "{home}/.toolguard/**/*.toml",
    "{home}/.config/toolguard/rules/**",
    "{project}/.claude/toolguard_hook.toml",
    "{project}/.claude/settings*.json",
]

# Subtracted from the expanded watch set (editor scratch, backups, the snapshot dir).
ignore = ["**/*.bak", "**/*~"]

snapshot_dir = "{home}/.toolguard/tamper"   # default
max_file_bytes = 262144                      # refuse to snapshot larger; report size-only
max_versions   = 20                          # per watched file
max_age_days    = 90
report = "both"                              # "message" | "context" | "both" | "silent"
```

**Directories vs files**: a watch entry naming a directory is treated as `dir/**`. This is
what makes "track a directory" work without a separate key -- and it is the case that
matters most, because the `~/.toolguard` wipes were *deletions of a whole tree*.

**Merge semantics across the hierarchy -- security-monotonic, mirroring `hard_deny`:**

- `watch` and `ignore`: **union** across levels. A project level can ADD to what the user
  level watches; it can never shrink it. (An `ignore` union does technically let a project
  subtract -- so `ignore` is applied only to entries contributed *at or below* the level
  that declared it. Without that rule, "ignore = ["**"]" in a project config silently
  disables the user's watchlist, which is exactly the attack this feature exists to catch.)
- `enabled`: true if ANY level sets it true. A lower level cannot switch it off.
- The scalar knobs (`snapshot_dir`, retention, `report`): **most-specific wins**, consistent
  with the rest of the config system. These are not security-relevant.

**Default when `enabled = true` but `watch` is absent**: derive the watchlist from
`discover_config_files()` plus `_rules_dirs()` -- i.e. *every file toolguard already reads
to make decisions*, which is precisely the set whose tampering matters. This is the
ergonomic default and should be the documented recommendation; an explicit `watch` is for
widening (e.g. `~/.claude/agents/**`, `~/.claude/skills/**`) or for non-toolguard files.

### Lifecycle -- and a correction to draft 2

Draft 2 said *"on change, snapshot to `~/.toolguard/config-backups/`"*. **That is wrong for
recovery and must not be built as written.** PostToolUse runs *after* the write, so the
only thing available at detection time is the damaged content. Snapshotting on change
preserves the damage and loses the original.

Correct lifecycle:

1. **First sight of a watched file -> snapshot it immediately** (this is the baseline, and
   the thing you actually restore from), and record `path -> (sha256, size, mtime)` in
   `{snapshot_dir}/manifest.json`.
2. **Every subsequent run**: re-hash. Unchanged -> do nothing, no I/O beyond the hash.
3. **Changed** -> the *existing* snapshot is the pre-change content. Emit a diff of
   snapshot-vs-current, then snapshot the new content as the next baseline.
4. **Disappeared** -> report loudly and **keep the last snapshot**; do not re-baseline to
   "absent". This is the `~/.toolguard`-wipe case, and the snapshot is the only artifact
   that makes it recoverable.
5. **Newly appeared** -> report as new (a new rules file arriving unannounced is
   security-relevant), then baseline it.

Retention prunes by `max_versions` then `max_age_days`, but **never prunes a file's only
remaining snapshot** -- otherwise retention itself destroys the recovery artifact for a file
that has been quiet for 90 days, which describes most permission config.

### The de-listing hole (found while writing this up)

If the watchlist lives in `toolguard_hook.toml`, an agent that edits that file can remove a
path from `watch` -- or set `enabled = false` -- in the *same* write. PostToolUse then reads
the NEW config, computes the NEW watchlist, and correctly reports nothing.

Fix: **the effective watch set is the union of the current watchlist and the previous run's
watchlist**, which is already persisted in `manifest.json`. Any config file that ever
contributed a `[tamper_evidence]` section is itself permanently watched. De-listing then
shows up as a diff of the config file that did the de-listing -- the loudest possible
signal. Cheap, and it closes the obvious self-referential bypass. Needs an explicit unit
test with a BDD name that says so.

### Paired Pre/Post checks -- attribution (Arnon, 2026-07-28)

Arnon: *"it may be best implemented as two hooks: one PreToolUse that would capture
signatures before the tool use and one PostToolUse that would capture after. This would
make it more robust and would overcome some of the limits (not truly concurrent changes)."*

**Accepted.** It converts the vague "changed since last check" into three distinct,
separately actionable classifications:

| Where the hash changed | Classification | What it means |
| --- | --- | --- |
| `Pre(t)` -> `Post(t)` | **attributed** | THIS tool call changed the file. Sub-second window; a near-certain claim. |
| `Post(t-1)` -> `Pre(t)` | **external** | A human editor, `git checkout`, another session, or a crashed tool. |
| no `Pre(t)` record | **unattributed** | Fall back to draft-2 wording. |

The **external** class is not a consolation prize -- it is a signal the single-hook design
could not produce at all, and it is the one that would have caught the `~/.toolguard` wipes
attributed to the wrong actor. And **attributed** is what makes the report safe to word
strongly, which challenge 2 below said we could not do.

Note what this does **not** improve: **recovery is unchanged.** The snapshot store already
held the pre-change content in both designs. The entire gain is classification. Worth being
clear about, so the extra complexity is bought for the thing it actually delivers.

#### Correctness details that must be built, not discovered

1. **PostToolUse does not always run.** A toolguard `deny`, a user rejection at the prompt, a
   tool error, or a session kill all leave a `Pre` record with no `Post`. **Dangling pre-
   records are the normal case, not the exception** -- the state machine must treat them as
   ordinary and simply let the next `Pre` supersede them. A design that assumes pairing will
   misreport constantly.
2. **Correlation.** Prefer an id carried in both payloads if one exists; otherwise key on
   `session_id` + `tool_name` + a hash of `tool_input`. **Verify against current Claude Code
   docs** along with the output contract -- same open item.
3. **Concurrency across sessions.** Two Claude sessions interleave their records. Use
   **per-session state files** (`{snapshot_dir}/sessions/{session_id}.json`) rather than one
   mutable manifest, and atomic `os.replace` writes. Prune session files on age. The shared
   `manifest.json` stays the single baseline record and is only written on actual change.
4. **`Pre` runs on toolguard's own hot path** -- an extra process spawn (~50-80ms of
   interpreter startup) before every qualifying tool call. Do the cheap and obvious things:
   **stat-first (size+mtime), hash only on mismatch, never read content unless a hash
   differs**; the narrow `Edit|Write|Bash` matcher; and a **`pre_check = true|false`** knob so
   single-hook mode stays available. Default `true` when enabled. **Do not optimise beyond
   that** -- see the latency principle below.
5. **The `Pre` hook MUST NEVER BLOCK.** Arnon, unambiguous: *"this should never block, I
   think."* Not a posture, a hard requirement. Wrap `main()` in a blanket
   `except BaseException` -> error log -> `exit(0)`; never emit a decision-shaped JSON body on
   the pre phase at all, so there is no code path that *could* deny. Unit-test that an
   exception inside the core still exits 0 with empty stdout. A tamper-*evidence* feature
   that can deny a tool call has become a tamper-*prevention* feature by accident, which is
   precisely the design that was rejected in Part 2.

#### Latency principle (Arnon, 2026-07-28)

*"The overhead in execution is anyway an explicit user choice. You pay with latency for more
security (but not paying with friction -- as per 'more security, less friction')."*

**Latency is not friction.** Friction is being asked, interrupted, or blocked; latency is a
tax the user opted into by wiring the hook and choosing a broad watchlist. So the perf story
does not need to be clever -- it needs to be *honest and documented* (broad globs cost more,
here is roughly how much) rather than optimised. This meaningfully lowers the priority of
challenge 3 and rules out speculative optimisation work.

#### Deferred idea: external `b3sum` -- RECORDED, probably not worth pursuing

Arnon raised BLAKE3 via a `b3sum` binary for the directory case, with his own caveats
(provenance tracking of *how* each hash was computed, tool discovery, extra testing) and his
own conclusion: *"probably not worth pursuing for now."* Agreed, and there are two further
reasons it is likely the wrong optimisation:

1. **It would probably be SLOWER for the actual workload.** Per-file `subprocess` spawn is
   ~1-5ms; hashing a 4 KB TOML file in-process is microseconds. Shelling out per file is a
   straight loss. It could only win by hashing an entire tree in **one** spawn -- so if this
   is ever revisited, the design is "one `b3sum` invocation over the whole watch tree",
   not a drop-in hash swap. That is a different feature, not a tweak.
2. **The bottleneck is not hash throughput.** For the big-directory case the cost is
   thousands of `stat` calls, which BLAKE3 does not help with. And with stat-first, most runs
   never hash anything at all.
3. **If hash speed ever does matter, the answer is `hashlib.blake2b`** -- stdlib since 3.6,
   substantially faster than SHA-256 on large inputs, no discovery, no external binary, no
   provenance field, and it preserves the zero-runtime-dependency property that is a
   deliberate security posture in this project. An optional external hasher would put a
   third-party binary on toolguard's trust path, which is a poor trade for a feature whose
   whole job is integrity.

Recorded here rather than in the ticket so it is findable if the directory case ever gets
painful; not planned.

### Output contract

PostToolUse hooks can return JSON on stdout; the exact key set for surfacing text to the
user vs to the model must be **verified against current Claude Code docs before coding**, not
recalled -- this is the one part of the design I cannot ground from this repo. The `report`
knob exists precisely so the choice is configurable rather than baked in. Whatever the
mechanism, the diff must be unmistakable in a scrolling transcript (banner, path, verdict
count) and truncated to a bounded number of lines, with the snapshot path printed so the
full content is one command away.

**Failure posture: never block.** A tamper-evidence hook that errors must exit 0 and stay
silent about its own failure except in the toolguard error log. It is an observer; taking
down the user's session because a snapshot directory is unwritable would be a worse bug than
the one it watches for.

**Snapshot secrecy**: `settings.json` can contain tokens and environment values, so the
snapshot tree is created `0700` and files `0600`. Worth stating in the doc, since the
feature's effect is "quietly accumulate copies of your most sensitive local files".

### Testing plan (all offline, all `tmp_path`, no live config -- see Part 1's principle)

Core (`tamper_evidence.py`): first-sight baseline; unchanged is a no-op; change produces a
diff against the *pre-change* content; deletion reported without re-baselining; appearance
reported; retention prunes by count and by age but never the last copy; oversize file
reported by size without snapshotting; symlinked watch target resolves once and is not
double-reported (ties into Part 4); manifest survives a corrupt/absent file (rebuild, do not
crash); snapshot dir permissions.

Adapter (`tools/tamper_check.py`): watch-set union across levels; project `ignore` cannot
subtract a user-level entry; `enabled` cannot be switched off by a lower level; the
de-listing test above; directory entry expands to `dir/**`; absent section -> completely
inert (assert zero filesystem writes); malformed section -> inert plus an error-log line,
exit 0.

Pre/Post pairing: change between pre and post -> **attributed**, and the report says so;
change between the previous post and this pre -> **external**; a pre-record with no post
(denied/rejected/errored tool) is superseded by the next pre without any report; two
interleaved session ids do not corrupt each other's state; `pre_check = false` degrades
cleanly to single-hook behaviour; **an exception raised inside the core still exits 0 with
empty stdout** (the load-bearing test -- on `PreToolUse` a nonzero exit could block the
user's tool call).

### Documentation

New **`docs/tamper-evidence.md`**: what it is (evidence, not prevention), why it is
channel-independent, the config schema, the lifecycle, how to wire it, how to restore from a
snapshot, and an explicit "this is off by default and wires to nothing" statement. Linked
from:

- `docs/agent-map.md` -- **mandatory**; it summarises every doc and is the single most
  drift-prone file in the repo.
- `docs/security.md` -- as the detective control alongside the ASK floor and `hard_deny`
  (both preventive). The contrast is the clearest way to explain it.
- `docs/configuration.md` -- the `[tamper_evidence]` section, next to the other tables.
- `README.md` feature list and `llms.txt`.
- `docs/install.md` -- one line only, under optional extras: it is deliberately not part of
  the install flow.

### Wiring planned for THIS project

Unwired everywhere by default; wired here by hand, as the first real user:

1. `~/.claude/settings.json` gets **both** a `PreToolUse` and a `PostToolUse` matcher
   covering `Edit|Write|Bash` (not `*` -- `Read`, `Grep`, `Glob` and the MCP tools cannot
   change a file), running `toolguard-tamper-check --phase pre` / `--phase post`. The
   `PreToolUse` entry sits alongside toolguard's own permission hook; order does not matter,
   since tamper-check never blocks and a denied tool simply leaves a dangling pre-record.
2. `~/.claude/toolguard_hook.toml` gets `[tamper_evidence] enabled = true` and an explicit
   `watch` that adds `{home}/.claude/agents/**` and `{home}/.claude/skills/**` to the
   default set -- agents and skills are executable instructions to Claude, so tampering
   there is as consequential as tampering with rules, and this ticket already involved
   editing three agent/skill files.
3. This repo's `.claude/toolguard_hook.toml` adds `{project}/.claude/**` (it is untracked
   today -- see Part 4, which is the durable fix; this hook covers the window until then and
   any machine where that fix is not present).
4. After a week of living with it: decide whether the installer should *offer* to wire it.
   That decision is explicitly out of scope now.

### Challenges to this plan, stated plainly

1. **Detective controls only work if someone reads the output.** Under auto-mode -- the very
   condition that produced the incident -- Arnon is by definition not watching the
   transcript. The diff lands in a scrolling log nobody reads until after the damage. The
   snapshot still makes it *recoverable*, which is the larger half of the value, but the
   "loud diff" half is weaker than it sounds. This is a real argument that **Part 5
   (auto-mode `deny`) is the load-bearing control and this is the safety net**, not the
   reverse. Worth reflecting in how hard we work on the output formatting.
2. ~~**A PostToolUse hook cannot attribute a change.**~~ **Largely resolved** by the paired
   Pre/Post design above: changes now classify as attributed / external / unattributed.
   **Residual, accepted by Arnon:** a change made by a third party *during* the tool's own
   execution is indistinguishable from one the tool made. That window is sub-second and the
   misattribution is conservative (it over-blames the session rather than missing the
   change), so it is a documentation item, not a design problem. The report wording must
   still be honest per class -- "this tool call changed it" only for **attributed**.
3. ~~**It runs on every qualifying tool call, now twice.**~~ **Downgraded** by the latency
   principle above: the cost is an explicit user choice, and latency is not friction. Do the
   cheap mitigations (stat-first, narrow matcher, `pre_check` opt-out), **document** that
   broad globs cost more, and stop there. No speculative optimisation.
4. **Unwired features rot.** Nothing exercises the wiring path in CI, so the config schema
   and the docs drift from the code. The unit tests cover the module, not the integration.
   Partial mitigation: wiring it in this project (step 2 above) makes Arnon the canary.

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

**DONE 2026-07-28** -- `test/unit/test_symlink_hierarchy.py`, 8 tests. Results:

- `find_project_root` DOES anchor correctly on a symlinked `.claude`, returning the
  project directory rather than the symlink target.
- Level attribution is unchanged, and end-to-end verdicts through a symlinked `.claude`
  are byte-identical to the real-directory control.
- A symlinked rules FILE loads correctly (the TOO-19 near-miss did not regress).
- **FOOTGUN FOUND AND FIXED (same day).** `_level_for_path` re-derived a source's level
  from its path shape, resolving symlinks and testing containment under `~/.claude`. A
  store placed under `~/.claude` therefore silently reclassified every project rule as a
  USER rule, changing precedence with no error. Symlinking the CONTENTS instead of the
  directory hit the identical bug (attribution resolves the file, so it follows a file
  symlink too) -- so that apparent workaround cost version control for new files and
  bought nothing.

  **Fix:** `_discover_levels()` now emits the level itself, since it is the pass that
  actually found the file, and `_level_for_path()` is deleted (a comment at its former
  site warns against reintroducing path-shape derivation). The two derivations can no
  longer disagree because there is only one. Net negative LOC.

  Subtlety worth keeping: the user tier is `len(level_dirs) - 1`, NOT the maximum
  specificity among discovered results -- a level whose directory does not exist
  contributes nothing, so a max-over-results would promote the deepest existing level to
  `user`. Both the fix and this subtlety are mutation-tested (reintroducing either defect
  fails specific tests).

  Practical consequence: **the store's location no longer matters**, so there is no rule
  for future-you to remember and no doc caveat needed.

This is **complementary to, not a replacement for, the Part 2 hook**: VCS covers commits;
the hook covers the window between them, and any machine or user with no such repo.

---

## Part 5 -- MISSING FROM DRAFT 1: auto-mode is the primary lever

> **CORRECTION 2026-07-30 (Arnon).** The premise below was WRONG, and it propagated from here
> into the TOO-28 comment and into a draft of `docs/security.md` before being caught. **An ASK
> returned by a `PreToolUse` hook is NOT bypassed in auto mode** -- the command stops and waits.
> The 2026-07-25 "measurement" (`Status: ASK / ASK floor applied` followed by the command
> running) was misread: a logged ASK followed by execution is what an *approved* prompt looks
> like, and it is indistinguishable in the log from a bypass. The log records the verdict, not
> whether a human answered.
>
> This is consistent with what `docs/auto-mode.md` already said and this document did not
> reconcile with: `no_match_fallback = "ask"` is described there as "a dead end in an
> unattended run: there is no one there to answer, so an unmatched command just hangs." An
> ASK that hangs is an ASK that blocks.
>
> **What this changes:**
> - The 2026-07-25 incident is NOT explained by ask-bypass. The agent's `Edit` calls to the
>   live config went through because an explicit `Edit(./**)` allow matched them -- an allow
>   rule, not a missing block. That is a plainer and more actionable diagnosis.
> - **TOO-28's motivation changes DIRECTION, not just strength.** The old framing was "ask
>   interactively, deny in auto mode" -- add friction where nobody is watching. With the
>   corrected fact, Arnon's reframing (2026-07-30) is the more useful one: **ask interactively,
>   ALLOW in auto mode.** If you trust Claude Code's auto-mode classifier, toolguard's ASK is
>   redundant friction in an unattended run rather than protection -- the classifier is already
>   a second gate on that action, and toolguard's explicit `deny`/`hard_deny` still resolve
>   BEFORE it. Only the ASK tier relaxes. This also removes the stall problem above instead of
>   trading it for a hard failure.
> - The ASK floor is a real control in auto mode, not advisory telemetry.
>
> **Three caveats for TOO-28 -- ALL RESOLVED by Arnon 2026-07-30:**
>
> 1. **Does a hook `allow` bypass the classifier?** The whole rationale assumes the classifier
>    still judges an action toolguard allowed. If a `PreToolUse` `allow` makes Claude Code skip
>    the classifier, then ASK -> ALLOW removes BOTH gates and the reasoning inverts. Not
>    hypothetical: narrow native Bash allow rules DO bypass the classifier unless
>    `autoMode.classifyAllShell` is set, so "an allow can skip the classifier" is a real
>    mechanism in that system.
>    **RESOLVED: test it explicitly, manually, together.** Do NOT infer it from toolguard's
>    logs (the mistake corrected above) and do not settle it from documentation alone. This is
>    a prerequisite for TOO-28's design, not a detail to discover during it.
> 2. **The ASK floor is not a rule-derived ASK.** `compound.py`'s clamp fires when toolguard
>    *cannot safely decompose* the command (foreign inline code, heredocs into an interpreter)
>    -- a structural "I do not understand this input", not a policy choice about a known action.
>    **RESOLVED: it gets its OWN flag, separate from the no-match case.** Arnon has commented
>    on TOO-28 accordingly. Two distinct knobs, because they answer two distinct questions:
>    - `no_match_fallback_auto_mode` -- "no rule matched this action"
>    - `undecidable_fallback_auto_mode` -- "I could not decompose this command safely"
>
>    Keeping them separate matters: you might reasonably trust the classifier with an
>    unmatched-but-parseable command while still refusing to hand it something toolguard
>    itself could not read. Collapsing them into one flag would silently couple those.
> 3. **The parse-failure clamp is exempt, permanently.**
>    **RESOLVED (Arnon, verbatim):** *"parse failure must always be a noisy, naggy,
>    uncomfortable, heavy friction behavior. You MUST have clean TOML for any configuration to
>    be trusted at all."*
>
>    Treat this as an invariant rather than a default: **no auto-mode flag, present or future,
>    may downgrade a parse-failure ASK.** The reasoning is that a parse failure is not a
>    permission decision at all -- toolguard does not know what its rules are, so it has no
>    basis for any verdict, and the classifier cannot compensate for rules it never saw.
>    Anything that relaxes it produces the silent-allow scenario this document wrongly claimed
>    already existed, except real and by configuration. Any future flag touching fallback
>    behaviour needs a test asserting the parse-failure path is unaffected.
>
> Everything below is retained as written, for the record. Read it in light of this.

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

1. ~~**Arnon commits the current Phase 0 work**~~ -- DONE, `5dc4816`.
2. Implement tamper-evidence **as a shipped-but-unwired toolguard feature** (revised scope
   above): `tamper_evidence.py` core -> `tools/tamper_check.py` adapter -> console script ->
   unit tests -> `docs/tamper-evidence.md` + the five link sites -> hand-wire it in this
   project. Verify the PostToolUse output contract against current Claude Code docs before
   writing the adapter.
3. Implement `toolguard/testing/sandbox.py` + CLI + tripwire tests (incl. the two rules
   directories).
4. Add the project CLAUDE.md checklist.
5. Move `.claude/` to `dot_files` + symlink; add the symlink-resolution tests.
6. Auto-mode friction -> TOO-28 / TOO-38 (separate tickets, comment already prepared).
