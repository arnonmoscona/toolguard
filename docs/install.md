# Installing toolguard with an AI agent (guided)

**Audience: an AI agent (Claude) that a user has pointed at this repository and asked to
"install toolguard".** This is a runbook you follow *on the user's behalf*. The user is
assumed to be new to toolguard: do the work for them, ask the right question at the right
moment, explain just enough to make each decision, and never require them to understand
toolguard's internals.

This is a guided conversation, not a script. Everything it orchestrates already exists --
the `uv tool install` entry points, the hook wiring (see
[agent-guides.md](agent-guides.md#recipe-install-and-register-toolguard-from-scratch) for the
exact JSON/TOML), `migrate_permissions`, and the audit/maintenance skills. Your job is to
sequence them, get consent, and keep a rollback record.

**You do NOT need to clone this repository.** `uv` installs toolguard straight from the repo URL
(Phase 3). Read the docs you need as raw files or from the installed package; do not `git clone`
unless the user explicitly wants a source checkout.

## Phase map

Work the phases in order. This map is for re-entry -- resuming after an interruption, or
answering "what does Phase 8 do again" without re-reading the file.

| Phase | What happens | Reversible? |
| --- | --- | --- |
| [0 -- Preflight](#phase-0----preflight) | Environment checks before any change | n/a, no changes yet |
| [1 -- Scope](#phase-1----scope) | Which projects, user level or project level | n/a |
| [2 -- Options](#phase-2----options-recommend-then-take-their-decision) | Takeover mode and other decisions | n/a |
| [3 -- Install method](#phase-3----install-method) | `uv tool install` | yes, uninstall |
| [4 -- Base config, then hook](#phase-4----write-the-base-config-then-register-the-hook-go-live-last) | Config first, go-live LAST | yes, journaled |
| [5 -- Skills](#phase-5----skills-ask-the-user) | Install the audit/maintenance skills | yes, journaled |
| [6 -- Validate](#phase-6----validate) | Confirm enforcement actually works | n/a |
| [7 -- Migration](#phase-7----offer-an-initial-migration-optional) | Fold native rules in (optional) | yes, backups |
| [8 -- Security audit](#phase-8----offer-a-security-audit-optional) | Optional review pass | n/a, read-only |
| [9 -- Maintenance](#phase-9----offer-an-initial-maintenance-pass-optional) | Optional cleanup pass | yes, per-item consent |
| [10 -- Takeover](#phase-10----enable-takeover-only-if-the-user-chose-it-in-phase-2) | Only if chosen in Phase 2 | yes, journaled |
| [Wrap-up](#wrap-up) | Hand back, summarize | n/a |

Supporting sections, not part of the sequence:

- [Principles (follow these throughout)](#principles-follow-these-throughout) -- read before Phase 0
- [Install checklist](#install-checklist-work-through-it-do-not-skip-a-box) -- the box-ticking version of the phases
- [The `toolguard-install` helper](#the-toolguard-install-helper-use-it-to-cut-prompt-noise) -- subcommands that cut prompt noise
- [The install journal](#the-install-journal-toolguardinstall-journalmd) -- what to record, and why rollback depends on it
- [Phase R -- Rollback during install](#phase-r----rollback-during-install-if-the-user-changes-their-mind) -- if the user changes their mind
- [Phase T -- Trace dump and issue reporting](#phase-t----trace-dump-and-issue-reporting-offer-this) -- when something went wrong

### Set expectations up front (say this before you start)

Before the first system change, tell the user plainly what they are signing up for -- this is a
deliberately unconventional way to install software, and they should choose it knowingly:

- **It is slower** than a normal installer -- it is a step-by-step conversation, not a one-shot
  command.
- **But it is worth it because:** it adapts to *their* environment rather than assuming one; it
  keeps them **fully in control** in the agent environment they already use, deciding every
  important step; it can **work its way out of tough situations** and rescue itself when it hits
  a corner; it is **very safe and transparent** -- every change is journaled, and even a partial
  install rolls back cleanly, leaving logs and debug traces behind for diagnosis; and it can
  **auto-report installation problems as GitHub issues** so bugs get fixed.

Get a "yes, go ahead" before proceeding.

## Principles (follow these throughout)

- **Consent before every system-modifying action.** Installing a tool, editing
  `~/.claude/settings.json`, writing a config file, installing a package manager -- each one
  is proposed, explained briefly, and done only after the user agrees. Never batch silent
  changes.
- **Do it for them.** Prefer taking the action yourself (with consent) over telling the user
  to run commands, unless they ask to drive.
- **Important decisions are the user's -- never decide-and-go.** When a choice actually matters
  -- what counts as the project root, which rules to migrate, removing a rule an audit flagged,
  enabling takeover, tightening the fallback -- **surface it and let the user decide**, even when
  you have a confident default. Do NOT silently auto-classify, auto-remove, or auto-tighten. A
  confident recommendation is welcome; acting on it without asking is not. This is slower on
  purpose; keeping the user in control is the whole point.
- **Right info, right time.** Explain a choice only when it is being made. Do not dump the
  whole design on them up front.
- **Stop anytime, resume anytime.** After each phase, the user may stop. The install journal
  (below) is the source of truth for what is done, so a later session can continue or roll
  back.
- **Journal everything, with its reverse.** Before/after every system-modifying step, append
  an entry to `~/.toolguard/install-journal.md` recording the action AND the exact command to
  undo it (see "The install journal"). This is what makes a clean, reliable uninstall possible
  later -- treat it as mandatory, not optional.
- **Apply changes in atomic groups, not trickle-by-trickle.** Half-applied intermediate states
  are where installs break -- above all the instant hooks go live and toolguard starts governing
  the very tools you are using. So where a phase makes several related changes, **stage them
  together and apply the group as a single unit**: write the whole group into one short shell
  script under `~/.toolguard/stage/` (e.g. `stage/02-config.sh`), show it to the user, then run
  it once. Order the groups so the go-live step (registering the hooks) is **last**, after
  everything toolguard will need is already on disk. Each applied group is still journaled with
  its reverse. This makes each step atomic from the running agent's perspective and minimizes
  fragile in-between states.
- **Local time, ASCII.** Timestamps in the user's local time; keep everything you write ASCII.

---

## Install checklist (work through it; do not skip a box)

Keep this list in front of you and tick each item as you finish it. Steps marked **(MUST)** have
been forgotten in real installs -- do not end the session without them. The phases below expand
each item.

**Re-check this list out loud after every phase, not just at the start.** In real installs,
phases have been silently skipped -- Phase 8/9's offers went unmade, the trace dump was never
raised until the user asked for it directly. Silently completing "enough" and stopping is the
failure mode: after each phase, briefly state which boxes are now checked and which remain,
including the **(MUST)** ones, before moving on or ending the conversation.

**A narrower mid-flight request from the user does not erase the rest of the checklist.** If the
user says something like "now migrate this project" or "roll back and give me a dump," treat it
as scoping *that* request, not as permission to skip the MUST items still open (trace dump,
`~/.toolguard/` retention, offering audit/maintenance if not yet declined). Re-orient against
this checklist before ending the session, even when the conversation's shape suggests something
narrower was asked for.

- [ ] **Phase 0** preflight (READ-ONLY -- no writes yet): detect environment; **check
      `CLAUDE_SETTINGS_PATH`**; detect any existing install
- [ ] Set expectations (unconventional + slower, but adaptable / user-in-control / self-rescuing /
      safe+rollbackable / auto-reports issues) and **get a go-ahead**
- [ ] **Phase 1** scope (user vs project)
- [ ] **Phase 2** options (governed_tools; takeover decided now, enabled late)
- [ ] **Phase 3** install the package (`uv tool install`) -- puts `toolguard-install` on PATH --
      then `toolguard-install init-state` (creates `~/.toolguard/` + journal) and journal the install
- [ ] Pre-approve `Bash(toolguard-install:*)` once to cut prompt noise (see the helper section)
- [ ] **Phase 4** write the base config (`write-config`), **register hooks** (`register-hooks` =
      go-live), then immediately **seed self-permissions** (`seed-self-perms`) -- unconditional on
      takeover choice; toolguard-audit/toolguard-maintain get invoked from Phase 6 onward; this
      same step also seeds the uninstall-readiness rules so a later uninstall never hard-blocks
- [ ] **Phase 5** skills (ask) -- persistent install uses `install-skills`, not an ad hoc clone/copy
- [ ] **Phase 6** validate
- [ ] **Phase 7** migration (optional) -- this is the "**move** your rules" step; discover
      candidates with `discover-projects`; be takeover-aware; confirm the project list and where
      rules land; defer any project outside the confirmed batch to Phase 9, don't extend Phase 7
      ad hoc
- [ ] **Phase 8** security audit (optional) -- **never remove a flagged rule without consent**
- [ ] **Phase 9** maintenance pass (optional) -- this is the separate "**review / clean up**" step
- [ ] **Phase 10** enable takeover (only if chosen) -- offer secret protections
      (`seed-hard-deny`, never hand-composed); then `enable-takeover`, recommending `ask` as the
      starting fallback (not `allow_with_warning`); describe the posture in plain language; present
      `deny` as an option, don't push it; remind the user that new rules should go into toolguard's
      own config from now on (10.4)
- [ ] **Wrap-up** summary
- [ ] **(MUST)** Offer the **session-trace dump** (Phase T.1) -- even on a clean install; do not end
      the conversation without having offered it
- [ ] **(MUST, if any toolguard problem occurred)** Offer to file/append a **GitHub issue** with the
      trace (Phase T.2)

---

## Phase 0 -- Preflight

**0.1 Preflight is READ-ONLY; the state directory is created after the package install.** Do not
write anything during Phase 0 -- it only inspects. You will create `~/.toolguard/` (its journal,
`README.txt`, and `backups/`+`stage/` directories) in one step right after installing the package
in Phase 3, with `toolguard-install init-state --source <where-you-installed-from>` (see "The
`toolguard-install` helper" below). That one command writes the journal and a README explaining
that `~/.toolguard/` holds toolguard's per-user state (the install journal and config/settings
backups), where toolguard was installed from, and that it is **intentionally NOT deleted on
uninstall**.

If `~/.toolguard/install-journal.md` **already exists** from a prior session, read it first and
continue from where it left off rather than repeating steps (running `init-state` again is safe --
it never clobbers an existing journal or README, it just appends a new session header).

**0.2 Detect the environment.** Note the OS/shell, whether Claude Code is present
(`~/.claude/` exists), whether `uv` is on PATH (`uv --version`), and whether `toolguard` is
already on PATH (`command -v toolguard`).

**0.3 Confirm you can actually perform the install (permission/sandbox preflight).** This
runbook writes files under `~/.claude/` and `~/.toolguard/`, runs the installed `toolguard`
binary, and may install a package -- all OUTSIDE the current project. If your own environment
is sandboxed or permission-restricted (a common cause of failure: writes/commands come back
"does not match any allow patterns" or "Path does not match any allow patterns", even for
`pwd`/`cat`), you cannot complete these steps silently. Detect this EARLY with one harmless
probe (e.g. try to stat `~/.claude/settings.json` or run `command -v uv`). If actions outside
the project are being blocked:

- **Explain it to the user plainly** -- their agent is running in a restricted mode, so it
  cannot edit `~/.claude` or run the installer on their behalf.
- **Offer the two ways forward:** (a) they re-run you in a mode that permits these actions
  (e.g. grant the specific paths/commands, or an accept-edits/appropriate permission mode),
  then you continue; or (b) you proceed in **hand-off mode** -- for each system-modifying step
  you give them the exact command to run themselves with the `!` prefix, then you verify the
  result and journal it. Do NOT silently fall back to shell heredocs to dodge a block that was
  intentional.
- Whichever they pick, keep journaling; a blocked step that the user runs manually is still
  journaled (with its reverse) so uninstall stays reliable.

**0.4 Check for a `CLAUDE_SETTINGS_PATH` override (important footgun).** Run
`echo "$CLAUDE_SETTINGS_PATH"`. If it is set, STOP and explain it before going further: this
environment variable puts toolguard in **single-file mode** -- it makes *every* toolguard
decision, in *every* directory, read that one settings file plus its adjacent
`toolguard_hook.toml`, **bypassing the entire configuration hierarchy** (including the
`~/.claude` config you are about to write). It is honored deliberately (handy for testing a
specific config), but as a *persistently exported* shell variable it is a footgun: if it points
at another project's config -- especially one with `takeover_mode` + `no_match_fallback = "deny"`
-- that project's fail-closed rules govern this whole machine, and the install can lock itself
out of `~/.claude`. This is a real failure we have seen. Show the user the value and ask plainly:
**"Is this intentional?"**

- **Not intended (the common case -- a stale export in a shell profile):** have them
  remove/comment the export in their shell startup (`~/.zshrc`, `~/.zshenv`, `~/.bashrc`, ...)
  AND `unset CLAUDE_SETTINGS_PATH` in the current shell, then continue. A user-level install
  cannot work correctly while it points at another project. (Note: a hook already registered in
  the *current* Claude Code session picked up the old environment; the variable is only fully
  cleared for a fresh session -- for in-session probes, invoke the hook with
  `env -u CLAUDE_SETTINGS_PATH`.)
- **Intended:** explain that the hierarchy stays bypassed, so the user-level install will not
  take effect until it is unset; let them decide whether to proceed anyway, unset it, or stop.

**0.5 Detect an existing toolguard install (edge cases).**

- **Already fully installed at the user level** (a `~/.claude/toolguard_hook.toml` plus the
  hook registered in `~/.claude/settings.json`): tell the user toolguard is already set up.
  Do NOT reinstall. Offer instead to run a security audit or a maintenance pass (Phases 8-9),
  or to add project-level rules. Stop the install flow.
- **Existing project wiring, non-standard** (a project has a `toolguard_hook.toml` and/or hook
  matchers, but there is no proper user-level setup): **warn and explain, do not
  auto-reconcile.** Tell the user plainly: "This project is already partly wired to toolguard,
  but not in the recommended way. I can (a) leave it as-is and set up a clean user-level
  install alongside it, (b) run the security-audit and maintenance flow against that project
  so it recommends how to bring it to the standard setup [this reuses Phases 8-9 -- it does
  not rewrite anything without your approval], or (c) stop here so you can handle it manually."
  Take their choice. Reconciling automatically is out of scope for this guide; the
  audit/maintenance flow is the supported bridge.
- **Nothing found:** proceed as a fresh install.

---

## Phase 1 -- Scope

Ask where toolguard should apply, and explain the difference in one breath:

- **User level (recommended for most):** toolguard governs *every* project on this machine.
  Config and hooks live in `~/.claude`. Best if they want protection everywhere.
- **Single project only:** toolguard governs just one repo. Config and hooks live in that
  project's `.claude/`. Best for trying it out or a shared machine.

Record the chosen scope; it determines where every later file goes. (You can always add
project-level rules later on top of a user-level base.)

---

## Phase 2 -- Options (recommend, then take their decision)

Present the few settings that shape behavior. Recommend the safe default, explain the "why"
briefly, and use their answer.

- **`governed_tools` -- govern what they use.** `Bash`, `Read`, `Write`, `Edit` are toolguard's
  own default when `governed_tools` is left unset, so no config entry is needed for that set.
  Ask whether they use any command-running MCP tool (e.g.
  `mcp__jetbrains__execute_terminal_command`; a custom MCP shell tool also goes in
  `additional_supported_tools`) -- only then does `governed_tools` need writing explicitly, and
  it must list the built-in four alongside the MCP tool (setting it replaces the default, it
  doesn't extend it). If unsure, leave it unset.
- **Takeover mode -- RECOMMENDED ON, but ENABLED LATE.** Take their decision now, but explain
  that if they choose it, you will switch it on near the *end* of the install, not now. With
  takeover on, toolguard becomes the real gatekeeper: it neutralizes broad "allow everything"
  rules Claude Code may have saved, and falls closed when no rule matches, so nothing slips
  through unreviewed. Without it (add-on mode), toolguard enforces the deny rules it has and,
  for anything with no matching rule, falls back to a normal permission prompt (`ask`) -- just
  like Claude's default -- so nothing is blocked outright and nothing is silently allowed.
  Recommend enabling it, and record their choice. **Why late:** turning takeover on with a
  fail-closed `deny` fallback while the machine has **no rules yet** would deny everything and
  lock the session out. So toolguard installs first in add-on mode; once
  rules are in place -- imported from their existing config (Phase 7) or reviewed in the
  maintenance pass (Phase 9) -- **Phase 10 enables takeover** as they chose. We never seed an
  allow-list we invented to paper over the gap; we install safe, add rules with the user, then
  tighten.
- **`no_match_fallback` -- decided at Phase 10, not now.** With takeover off, an unmatched
  command prompts (`ask`) by default -- nothing is blocked, matching Claude's own behavior. When
  takeover is switched on (Phase 10), **recommend keeping that same `ask` behavior** as the
  starting point -- it is both the safer of the two non-`deny` options (it never silently executes
  an unmatched command) and the one the user is already used to, so nothing about their day-to-day
  experience needs to feel different just because takeover is now the real gatekeeper. The user can
  tighten it to fail-closed `deny` once confident, or loosen it to `allow_with_warning` if they
  find prompting too disruptive and knowingly accept the tradeoff -- but that is a choice to
  present, not the one to steer them toward. The values THIS FLOW presents are `ask` (prompt;
  **recommended**) / `allow_with_warning` (allow + warn; available, not encouraged) / `deny`
  (fail-closed; optional for maximum strictness). `allow` and its `allow_with_no_warnings`
  alias also exist (TOO-19: allow with NO warning logged) but are deliberately NOT offered in
  this guided conversation -- they are strictly less safe than `allow_with_warning` with no
  install-time upside, so presenting them here would only add a worse option to steer someone
  away from. A user who wants one can still set it by hand later; see
  [Configuration: No-match fallback](configuration.md#no-match-fallback). Phase 10 walks this;
  nothing to set here.
  `undecidable_fallback` is a separate setting (for commands toolguard cannot safely parse at
  all, e.g. foreign inline code or heredocs, rather than commands that simply match no rule) --
  leave it at its `ask` default; there is no install-time decision for it. See
  [Configuration: Undecidable fallback](configuration.md#undecidable-fallback).

So Phase 4 writes the base config with takeover **disabled** regardless of their choice; Phase 10
enables it (with the self-permissions it needs) if they chose takeover. Keep the base config
minimal and safe; the user refines it later with migration and the maintenance skill.

---

## Phase 3 -- Install method

**Recommend `uv tool install`** -- it puts the `toolguard` entry points on PATH in an isolated
environment. You do NOT need a local checkout: `uv` installs straight from GitHub. Propose the
remote form first:

```bash
# Preferred: install directly from the repo URL -- no clone needed
uv tool install --from git+https://github.com/<owner>/toolguard toolguard
# If the user pointed you at a local checkout instead:
uv tool install /path/to/this/repo
uv tool update-shell
```

Then journal it (reverse: `uv tool uninstall toolguard`). Record the exact source you used in
the journal and in `~/.toolguard/README.txt` (Phase 0.1).

> **Do not trust a web-fetched summary of this repo for exact syntax.** If you are reading this
> runbook (or `agent-guides.md`) via a fetch/summarizer rather than the raw files, the hook JSON
> shape and config field values can come back paraphrased or wrong (observed: an invented
> `no_match_fallback = "ask"`, and a mis-shaped hook block). After installing, treat the
> **installed package source** as ground truth -- read the real schema from the installed
> `toolguard/` (e.g. under `uv tool dir`/site-packages) or fetch the RAW file, and verify the
> hook/TOML shapes against it before writing anything.

- **If `uv` is absent:** offer to install it (the official installer) with consent, and
  journal that separately (reverse: remove `~/.local/bin/uv`/`uvx` and `~/.local/share/uv`, or
  the platform's documented uninstall). Note in the journal that uv was installed BY this
  process, so uninstall may remove it -- but confirm with the user at uninstall time, since
  they may have started using uv for other things.
- **Alternative managers:** if the user prefers, `pipx install`, `pip install --user`, or a
  dedicated venv are all fine -- use their choice and journal the matching uninstall.
- **User-dictated method:** if the user has particular requirements (a specific prefix, a
  managed environment, an air-gapped mirror), let them tell you exactly how; follow it and
  journal the reverse they describe.

Confirm the entry point exists (`command -v toolguard`, or `uv tool dir --bin`). Note the
absolute path if `~` is not expanded in hook commands.

**Now that the package is on PATH, initialize state and cut the prompt noise -- before any config
changes:**

1. **Create the state directory + journal in one command:**
   `toolguard-install init-state --source "<the exact source you installed from>"`. This makes
   `~/.toolguard/` with its journal, `README.txt`, `backups/`, and `stage/`. From here on the
   mechanical steps are each a single `toolguard-install` subcommand that journals itself -- read
   each subcommand's `--help` first and fall back to a manual edit if it does not fit (see the
   helper section).
   **`init-state` itself has no reverse and needs no journal entry -- do not invent one.**
   `~/.toolguard/` is permanent: uninstall never deletes it (see
   [uninstall.md](uninstall.md#step-3----leave-toolguard-in-place-do-not-delete-it)). A real
   mistake to avoid: an agent once bundled `init-state` into a hand-written journal note and
   invented a reverse of "remove `~/.toolguard/`" for it -- then a later uninstall dutifully
   followed that bad entry and deleted the whole audit trail. If you ever journal `init-state` as
   part of a bundled manual note, its reverse is "(none -- `~/.toolguard/` is kept forever)",
   never a deletion.
2. **Journal the package install** (the helper cannot journal its own installation):
   `toolguard-install journal --action "installed toolguard via uv tool install (vX.Y.Z)" --reverse "uv tool uninstall toolguard"`
   -- and if you installed `uv`, journal that separately with its reverse. **Always record this
   through the `journal` subcommand (one call per distinct action), never by hand-editing
   `install-journal.md`.** A hand edit is an `Edit` tool call the Phase 3 pre-approval below does
   not cover (it only pre-approves `Bash(toolguard-install:*)`), so it re-introduces the very
   per-edit prompts this helper exists to cut -- and it produces an ad hoc entry instead of a
   properly numbered one. If several small actions belong together (e.g. the package install plus
   `uv tool update-shell`), call `journal` once per action rather than merging them into one
   free-form entry.
3. **Pre-approve the helper once, to stop the per-edit prompts:** propose adding
   `Bash(toolguard-install:*)` to the native allow list so the remaining `toolguard-install ...`
   calls run without prompting. Journal it (reverse: remove that allow rule; uninstall removes it).

---

## The `toolguard-install` helper (use it to cut prompt noise)

Once the package is installed (Phase 3), a **`toolguard-install`** console script is on PATH. It
exists to do the mechanical, deterministic install steps -- create `~/.toolguard`, write
`toolguard_hook.toml`, register the hooks, seed self-permissions, enable takeover, and journal --
as **single commands**, so you do not make many separate Read/Write/Edit tool calls (each of
which prompts the user). Because the script does its file writes *inside its own process*, those
edits never reach Claude Code's permission layer at all; **only the `Bash(toolguard-install ...)`
call does.** It is an agent-facing tool (its top-level `--help` says as much) -- not for direct
human use.

How to use it well:

- **Cut the noise once.** Early on, propose adding the single allow rule `Bash(toolguard-install:*)`
  (and re-grant narrow patterns at later checkpoints -- e.g. specific project paths after Phase 7
  discovery). Journal it; uninstall removes it. After that one approval, the mechanical steps run
  quietly.
- **Read the subcommand `--help` BEFORE you run it.** Each subcommand's `--help` is written for
  *you*: it states exactly which files it reads / writes / backs up, the journal entry it will
  append (its action and the reverse), its preconditions, and what it **refuses** or does **not**
  do. Confirm it will do **exactly** what this phase needs. **If it does not fit, fall back to the
  conversational/manual steps for that phase** -- the script is an accelerator, not a straitjacket.
  Treat each `--help` as the authoritative spec for that step (this doc describes intent; the help
  describes the exact behavior of the installed version).
- **Trust its output over your assumptions.** Every run prints exactly what it did -- the files it
  wrote and backed up (with paths) and the journal index it added -- and says plainly when it did
  **not** do something (e.g. "refused: config already exists; no changes made"). Read that summary
  and update your understanding of the state from it, rather than assuming the command did what you
  intended.

Where a phase below says "write the config", "register the hooks", "seed self-permissions", or
"enable takeover", prefer the matching `toolguard-install` subcommand (after checking its `--help`),
and fall back to the manual edit only when the helper does not fit.

---

## Phase 4 -- Write the base config, then register the hook (go-live LAST)

Do these with the `toolguard-install` helper -- it backs up and journals each step for you. Read
each subcommand's `--help` first and fall back to a hand edit only if it does not fit. Use the
scope chosen in Phase 1 (`--scope user`, or `--scope project --project-dir <path>`). **Order
matters:** registering the hook is the instant toolguard goes live and starts governing your own
tool calls, so do it **last**, after the config it will read is already on disk.

1. **Write the base config (while toolguard is still dormant):**
   `toolguard-install write-config --scope <user|project> [--project-dir <path>] --governed-tools Bash,Read,Write,Edit [--additional-supported-tools <mcp tool>]`.
   This writes `toolguard_hook.toml` with takeover **disabled** (Phase 10 enables it later once
   rules exist), refuses to overwrite an existing config without `--force` (backing it up first),
   and journals the write with its reverse. Nothing is governing yet, so this cannot lock you out.
2. **Register the hooks LAST (go-live):**
   `toolguard-install register-hooks --scope <user|project> [--project-dir <path>] --binary <path-to-toolguard> --governed-tools Bash,Read,Write,Edit`.
   This backs up the settings file, MERGES one PreToolUse matcher per governed tool + the
   SessionStart alert into it (never clobbering existing hooks, skipping any already present), and
   journals it. This is the step that makes toolguard live -- and because the config from step 1 is
   already on disk (and, with takeover off, an unmatched call resolves to `ask`, never a hard
   deny), it will not lock the session out.
3. **Seed toolguard's own self-permissions immediately -- do this now, regardless of whether the
   user chose takeover in Phase 2.** As soon as the hook is live (step 2), EVERY governed Bash
   call goes through toolguard, including toolguard's own tooling: `toolguard-audit` runs in
   Phase 6 (validate) and Phase 8 (audit offer), `toolguard-maintain` runs in Phase 9
   (maintenance offer) -- all of which happen before Phase 10. Deferring this seeding to Phase 10
   (as earlier versions of this runbook did) meant every one of those calls prompted
   individually, with nothing yet permitting them; a real install measured this as materially
   noisier than necessary. Seed now instead:

   - `Bash(toolguard-audit:*)` -> **allow** (read-only; the audit skill runs it).
   - `Bash(toolguard-maintain:*)` -> **ask** (it can write config; per-invocation consent, never
     a blanket allow, so the model cannot silently mutate the security config).
   - Read/Write/Edit access to `~/.toolguard/**` (the install journal and the decision ledger
     live there).
   - **Uninstall-readiness rules**, so a LATER uninstall never hits a hard block: `Bash(cd:*)` ->
     **allow** (harmless navigation -- `cd` cannot execute code, and toolguard's parser already
     checks any command substitution embedded in its argument on its own merits); plus **allow**
     rules for restoring the native settings file (`Write`/`Edit` on its exact path), running
     `uv tool uninstall toolguard`, and removing toolguard's own config and skill files. A real
     install hit exactly this: with takeover active and none of these rules yet in place, the
     agent's own teardown tool calls were hard-blocked, forcing an out-of-band hand-off instead of
     a prompt. Seeding these now -- before takeover is ever enabled -- guarantees uninstall always
     completes, regardless of the `no_match_fallback` chosen later in Phase 10. **These are `allow`,
     not `ask`** -- a deliberate exception to the "mutating tool -> ask" principle above, because an
     `ask` verdict was observed NOT reliably reaching a prompt during a real install (root cause
     still under investigation), so `ask` alone cannot actually guarantee uninstall completes.
     `allow` is immune to that failure mode, and every pattern here is a literal, single-purpose
     command or exact file path (not a wildcard) -- by the time any of them would fire, the user has
     already given explicit consent by starting the uninstall conversation in the first place.
   - **A self-integrity `[hard_deny]` protection**, so `~/.toolguard/` itself can never be deleted
     by a Bash `rm`/`find -delete` command -- not gated behind takeover, not even overridable by an
     explicit allow rule (that is the whole point of `[hard_deny]`). A real install had its
     `~/.toolguard/` wiped when the installing agent decided, unprompted, to "go further for a true
     clean slate" during uninstall and ran `rm -rf ~/.toolguard` -- directly contradicting
     [uninstall.md](uninstall.md#step-3----leave-toolguard-in-place-do-not-delete-it)'s explicit,
     repeated "do not delete `~/.toolguard/`" policy. Prose warnings alone did not prevent this;
     this pattern makes it a technical guarantee instead. It only blocks deletion -- reading,
     writing, or editing files under `~/.toolguard/` (the journal, backups, traces) is unaffected.

   These come from toolguard's single source of truth for self-permissions
   (`toolguard.tools.self_permission`, `toolguard.tools.uninstall_readiness`, and
   `toolguard.tools.self_integrity`); if a skill is installed you can also let it compute exactly
   which are missing. **Propose them explicitly, explain each, and add them only with consent** --
   they are not invented user allow-rules, just the minimum for toolguard's own tooling (and its
   own later removal) to keep working. Once the
   user consents, add them all in one command:
   `toolguard-install seed-self-perms --scope <user|project> [--project-dir <path>]` -- it reads
   all three sources of truth, adds exactly those rules (idempotently -- a second run is a no-op),
   backs up the config first, and journals the change with its reverse.

If the helper does not fit (an unusual settings layout, a manager other than `uv`, hand-off mode),
fall back to editing the files by hand using the exact hook JSON / `toolguard_hook.toml` shape from
[agent-guides.md](agent-guides.md#recipe-install-and-register-toolguard-from-scratch) -- back up
first and record it with `toolguard-install journal --action ... --reverse ...`.

---

## Phase 5 -- Skills (ask the user)

The maintenance and security-audit skills can either be installed persistently or just run
from this repo for the initial passes. **Ask the user which they want:**

- **Install persistently (user scope):**
  `toolguard-install install-skills --scope <user|project> [--project-dir <path>] --source <repo-url-or-local-checkout>`.
  This fetches (or copies, if `--source` is a local checkout) `skills/toolguard-security-audit/`
  and `skills/toolguard-maintenance/` and installs them into `~/.claude/skills/` (or the
  project's) in one step, so `/toolguard-security-audit` and `/toolguard-maintenance` work from
  now on. It is idempotent (an already-installed skill is reported unchanged, use `--force` to
  reinstall) and journals what it did with its reverse. **Do NOT hand-roll this with a bespoke
  fetch/clone/copy sequence of your own** -- an ad hoc shell loop has previously created a
  malformed skill directory, and doing the fetch/copy as several separate Read/Write/Bash calls
  is exactly the per-step prompt noise this helper exists to avoid. Use this if the user expects
  to curate/audit toolguard regularly.
- **Run from the repo for now:** skip persistent install. The initial audit and maintenance
  below will run by following this repo's `skills/*/SKILL.md` files directly (you are already
  pointed at the repo). Persistent skill installation can be done later.

Record their choice; it decides how you invoke the audit/maintenance passes in Phases 8-9.

**Keeping them current afterwards.** `uv tool upgrade toolguard` replaces the package and leaves
installed skills untouched, so a skill fix ships without reaching anybody who already has the old
copy. After any upgrade, run:

```bash
toolguard-update-skills
```

It force-refreshes the user-scope skills from the copy shipped inside the installation just
upgraded -- no network, no `--source` to get right, and no way for the skills to be a different
version from the binary. Each replaced skill is backed up into `~/.toolguard/backups/` and
journalled first. `--list` shows what would be written without writing it. Use
`install-skills` for the first install or for project scope; use this for every refresh after.

---

## Phase 6 -- Validate

Prove the install works before offering anything else:

- Run `toolguard --eval` on a representative event (read-only; it resolves a command without
  changing config or logging) and confirm it returns a decision.
- Run `toolguard-audit --with-context --format json` at the chosen scope; confirm it loads and
  `context.summary.sources` includes the config you just wrote. At this point top-level
  `takeover_active` should be **false** -- takeover is not enabled until Phase 10. (If the user
  chose takeover, note that it is intentionally still off and will be switched on at the end.)
- Report the result plainly. If validation fails (no decision, wrong sources, unexpected
  `hook-not-registered`), diagnose it (usually a hook not registered or a path that did not
  expand) and offer to fix -- or, if the user prefers, to roll back what was done so far
  (Phase R).

---

## Phase 7 -- Offer an initial migration (optional)

**Say plainly what "migration" is, and how it differs from the later "maintenance pass"** -- a new
user cannot consent to something they cannot name. In one breath: *"Migration just **moves** the
permission rules you already approved in Claude Code (in `settings.local.json`) into toolguard's
own config, so toolguard enforces them -- it does not change or judge them. Later, a separate
**maintenance pass** (Phase 9) is where we **review, clean up, and consolidate** those rules. Right
now I'm only offering the move."* Use those words ("move" vs "review/clean up") consistently so the
user always knows which one you are doing.

Ask: "Do you want me to move your existing Claude Code permissions into toolguard now?" Many
users have accumulated allow rules in `settings.local.json`. If yes, do NOT ask them to name
projects from memory -- **discover the candidates, then confirm the list with them.**

**Also ask the scope explicitly: every known project, or just the one you're in right now?**
Do not silently narrow this yourself. If the user is mid-conversation in a specific project and
says something like "migrate this," confirm whether that means *only* this project or whether
they also want the fleet-wide discovery below -- a real install once migrated only the current
project without ever running 7.1/7.2, leaving every other known project un-migrated and never
mentioned. If they want just the current project, skip 7.1/7.2 and go straight to 7.3 for it;
otherwise run the full discovery.

### 7.1 Discover candidate projects

Run `toolguard-install discover-projects` (add `--format json` if you want to parse it rather
than read it). This is read-only -- no backup, no journal entry -- and replaces what used to be
several separate `jq`/`cat`/`ls` calls (each its own prompt) with the one already-pre-approved
`Bash(toolguard-install:*)` call from Phase 3. It builds the candidate list the same way this
runbook always specified, so you can trust its output without re-deriving it by hand:

- **Authoritative: `~/.claude.json`.** Its top-level `projects` object is keyed by the
  **absolute path** of every project Claude has worked in -- the primary list.
- **Supplementary: `~/.claude/projects/`.** One transcript directory per project, named by
  encoding the absolute path (leading `/` and every `/` become `-`). Only used to catch a project
  the JSON missed, and only trusted if the decoded path actually exists on disk (the encoding is
  lossy -- a real `-` in a path is indistinguishable from an encoded `/`).
- **Filtered to existing directories with something worth migrating:** a `.claude/settings.local.json`
  that actually contains permission rules. Directories that no longer exist, or have nothing to
  migrate, are left out.
- **Each candidate is annotated, not silently skipped:** whether it already has a
  `toolguard_hook.toml`, and whether that config has `[takeover_mode] enabled = true`.

**Recognize takeover-configured projects in what it reports -- do NOT misread their blanket
allows.** A project already running toolguard in **takeover mode** deliberately keeps broad
`Bash(*)` / `Read(*)` / `Write(*)` / `Edit(*)` allows in its `settings.local.json` **on purpose**:
those are the native blanket allows that the project's own `takeover_mode.ignored_allow_patterns`
neutralizes, and its real rules live in its `toolguard_hook.toml`. These blanket allows are
**not** stray standalone permissions to migrate -- presenting them that way to the user is wrong
and alarming. The discovery output already flags which candidates are takeover-configured; for
those, say plainly that it is an existing takeover setup whose blanket allows are intentional,
and leave them alone. (The migration tool is already takeover-aware and ignores them; your
*conversational analysis* must be too.)

### 7.2 Confirm the list with the user

Present the discovered candidates as a simple checklist (path, whether it already has toolguard,
roughly how many rules would move) and **ask the user to adjust it**: remove any they do not
want touched, and add any project the discovery missed (a brand-new repo Claude has not opened
yet will not appear). Migrate only the projects they confirm. This keeps the user in control and
never touches a project silently.

**If the user asks mid-flow to migrate a project that is NOT on the confirmed 7.2 list, prefer
deferring it to the Phase 9 maintenance pass over extending Phase 7 ad hoc.** Handling it inline
here is not wrong, exactly, but Phase 7 is meant to be one bounded pass over a known, confirmed
batch -- a one-off addition discovered mid-conversation is precisely what the maintenance pass
(Phase 9), or a later standalone run of this same Phase 7, is for. Recommend that instead of
silently just doing it; let the user decide.

### 7.3 Cut the noise for this batch, then migrate each confirmed project

**Checkpoint: a new permission group just became known -- ask for it once, not per project.**
Once the list is confirmed (7.2), you know exactly which projects you are about to run the
migrator against. Rather than letting each project's dry-run and apply calls prompt separately,
propose one allow rule that covers the whole confirmed batch up front, e.g.
`Bash(toolguard-migrate:*)` (or scoped further per the user's preference). Journal it like any
other rule (reverse: remove it; uninstall removes it). This is the same "pre-approve once, cut
the noise" principle as the `toolguard-install` allow rule in Phase 3 -- just applied at the
checkpoint where migration's own permission needs become known, rather than guessed at the start
of the install.

For each project on the confirmed list, **dry-run first** so the user can review, then apply:

```bash
# from within the project (or point the migrator at its directory), review, then apply
toolguard-migrate --dry-run   # detects duplicates/supersets
toolguard-migrate             # applies; writes a timestamped backup
```

**Use the `toolguard-migrate` console script, not `uv run python -m
toolguard.scripts.migrate_permissions`.** After a `uv tool install`, `toolguard-migrate` is on
PATH via the same isolated environment as `toolguard-install` and the other console scripts, so
it works from inside ANY project. `uv run python -m ...` instead runs inside *that other
project's own* ephemeral environment, which has no idea toolguard exists -- it only happens to
work if you are standing inside the toolguard checkout itself. Two real installs independently
hit this exact confusion before `toolguard-migrate` existed; do not reintroduce it.

Apply creates a timestamped backup automatically. Journal each applied migration (reverse:
restore that backup). See [config-sync.md](config-sync.md) for the full behavior.

**Confirm where the rules will land -- do not let project-root detection decide silently.**
`toolguard-migrate` always targets the resolved project's own `.claude` directory -- creating a
project-level `toolguard_hook.toml` there if one does not exist yet, never an existing file at a
different level (e.g. an ancestor project's or the user's `~/.claude`), even if one already
exists elsewhere. The one case where this legitimately lands at **user level** is when
`toolguard` itself finds no project marker (`.git`/`pyproject.toml`/`.claude/CLAUDE.md`) above the
target directory -- a bare `~/projects` holding many repos is a common case -- so project-root
resolution falls back to the home directory itself, and "the project's own `.claude`" and
"`~/.claude`" are the same place. That may not be what the user expects -- user-level rules apply
everywhere. Before applying, tell the user which level each project's rules will migrate to, and
if a directory was classified as "not a project," say so and let them confirm or point you at the
real root. This is an important decision (see Principles); don't auto-classify and proceed.

**Only governed tools migrate.** Migration moves rules for the governed/built-in tools
(`Bash`/`Read`/`Write`/`Edit` and any `additional_supported_tools`). Rules for ungoverned tools
(e.g. `WebFetch`, `Skill`) are left in `settings.local.json` untouched -- moving them would make
them inert (toolguard does not govern them and native Claude no longer sees them). If you see a
dry-run proposing to move ungoverned-tool rules, that is a bug -- do not apply it; leave those
rules where they are.

If they decline the whole step, note that migration can be done anytime later, the same way.

**Avoid `cd`-ing into the toolguard source checkout, or into ANY directory with its own,
unrelated toolguard governance, and be aware `cd` changes persist across Bash calls.** If you ever
run a command from inside a local toolguard checkout (`git clone`d for inspection, not the normal
`uv tool install` path), the Bash tool's working directory stays there for every subsequent call
in the session -- and running an installed console script (`toolguard-audit`, `toolguard-migrate`,
...) from inside that checkout can shadow the `uv tool install`-managed package with the
checkout's own `toolguard/` directory, producing a confusing `ModuleNotFoundError: No module named
'toolguard.tools'` that has nothing to do with the install itself. **A second, separate risk of
the same `cd`:** if that directory (or ANY directory you `cd` into) happens to have its own,
unrelated, more specific project-level `toolguard_hook.toml` -- e.g. a user's separate real
development checkout of a project they already govern with toolguard -- that config silently wins
over the install/uninstall session's own config the moment cwd shifts there, since project-level
is always more specific than user-level. A command that behaves correctly at the user level can
then be denied (or otherwise resolve differently) for reasons that have nothing to do with the
install you are working on. Prefer `(cd <dir> && command)` in a subshell, or pass an absolute path
to the console script's own `--dir`/similar flag, over a bare `cd` that leaves the shell's working
directory changed for later calls -- and if a command behaves unexpectedly right after a `cd`,
check whether you have wandered into a directory with its own separate governance before assuming
a toolguard defect.

**Plain `cd` navigation itself is pre-permitted by default from Phase 4 onward** (part of the
uninstall-readiness rules seeded in Phase 4, step 3) -- `cd` cannot execute code on its own, and
toolguard's parser independently extracts and checks any command substitution embedded in its
argument (e.g. `cd $(...)`), so this does not weaken enforcement. If a bare `cd` is still denied
despite that, do not assume a toolguard bug -- it is more likely one of the two things above
(shadowing by an unrelated governance layer, or an install predating the uninstall-readiness
seeding); check `toolguard-audit`'s self-permission section and the actual `logs/toolguard-*.md`
entry for that command (its recorded status -- `executed`/`ask`/`refused` -- is authoritative,
never guess from a paraphrased transcript) before concluding anything.

---

## Phase 8 -- Offer a security audit (optional)

Ask: "Want me to security-check your permissions now?" If yes, **don't limit this to wherever you
happen to be sitting.** Offer the same discovered candidate list Phase 7 used (re-run
`toolguard-install discover-projects` if Phase 7 was skipped or declined) alongside the
current/user scope, and let the user pick which to audit -- **default to "all," not just the
current one.** Two categories are easy to miss if you only think about the project you installed
into:

- **A project that already has its own toolguard config** (e.g. one already running takeover
  mode, like a project Phase 7.1 flagged as takeover-configured) benefits from an audit of *its*
  config just as much as the one you just installed into -- it was never audited just because it
  wasn't part of THIS install.
- **A project with no toolguard config yet but with `settings.local.json` permission rules**
  can still surface native rule-danger findings (e.g. an `arbitrary-exec-allow`) -- toolguard-audit
  checks native settings independently of whether toolguard governs that project at all.

For each confirmed target, run `toolguard-audit --dir <path> --with-context --format json` (or
via `/toolguard-security-audit` if installed, pointed at that directory) -- read-only, never
edits config -- and present its findings separately, labeled by project.

**Do NOT act on a finding without explicit approval -- above all, never silently remove a rule
the audit flagged.** A CRITICAL finding (e.g. an `arbitrary-exec-allow` rule that a migration
pulled in) is exactly the kind of thing to *show the user and let them decide*, not to quietly
delete. For each fix you propose: name the rule, explain why the audit flagged it and what
removing/changing it does, and apply it only after the user says yes. Removing a rule the user
approved earlier -- even a dangerous-looking one -- is an important decision that belongs to
them (see Principles). If a migrated rule is clearly one-off session noise, still *ask* before
dropping it.

---

## Phase 9 -- Offer an initial maintenance pass (optional)

Ask: "Want me to organize your new toolguard setup?" If yes, **offer the same discovered project
list as Phase 8, not just the current scope** -- a project running its own toolguard config
benefits from a maintenance pass over *its* rules too, exactly as with the audit. `toolguard-maintain`
is read-only by default (it only edits config when `--apply --write` is given), so running it in
report mode across several confirmed projects needs no extra per-project consent beyond the
initial "yes, run maintenance" -- only an actual apply step does. For each confirmed target, run
`toolguard-maintain --dir <path> --format markdown` (or via `/toolguard-maintenance` if
installed, pointed at that directory) and walk the findings with them, applying only what they
approve. See [skills.md](skills.md) for what to expect.

---

## Phase 10 -- Enable takeover (only if the user chose it in Phase 2)

If the user did NOT choose takeover, skip this phase; leave a note that they can enable it later
(a maintenance pass, or by re-running this phase). If they DID, this is where you switch
toolguard from add-on mode to the real gatekeeper -- now that rules exist, so it does not lock
itself (or the user) out.

(Self-permissions -- `Bash(toolguard-audit:*)`, `Bash(toolguard-maintain:*)`, and
`~/.toolguard/**` access -- were already seeded in Phase 4, step 3, right after go-live. If for
some reason they were skipped there, do them now before proceeding: same command,
`toolguard-install seed-self-perms --scope <user|project> [--project-dir <path>]`.)

**10.1 Offer recommended secret protections (optional, with consent).** A fail-closed setup is a
good moment to add `[hard_deny]` protections for credentials. **Do not compose this TOML by
hand** -- freehand `[hard_deny]` patterns are exactly the kind of thing an agent can get subtly
wrong (a near-miss on this happened during a real install), and `[hard_deny]` cannot be
overridden by any level, so a mistake here is hard to walk back unnoticed. Use the fixed, curated
set instead: `toolguard-install seed-hard-deny --scope <user|project> [--project-dir <path>]` --
it reads the same canonical secret-file pattern list documented in [security.md](security.md)
("Recommended deny patterns" -> "Sensitive files": `.env`/`.env.*`/`.aws/**`/`.ssh/**` reads,
writes and edits), adds exactly those to `[hard_deny]` idempotently, backs up the config first, and
journals the change with its reverse. **Offer it; do not add it silently.**

**10.2 Enable takeover, defaulting to `ask` on anything unmatched.** Turn it on in one command:
`toolguard-install enable-takeover --scope <user|project> [--project-dir <path>] --no-match-fallback ask`
(this backs up the config and journals with its reverse). Describe the result to the user in
**plain language, not config tokens** -- e.g. "right now, a command that matches none of your
rules will prompt you for approval, same as Claude's own normal behavior -- nothing runs without
you seeing it first, and nothing about your day-to-day experience changes just because takeover
is on."

**Present all three fallback values, but recommend `ask` -- do not default the conversation
toward `allow_with_warning`.** All three are legitimate choices and the user should hear about
each, but they are not equally worth recommending:

- **`ask` (recommended).** Prompts on anything unmatched, exactly like Claude Code's own native
  behavior. It is the safer of the two non-`deny` options -- it never lets an unrecognized command
  run without a human seeing it -- and it asks nothing new of the user, since it is the behavior
  they already know. Suggest this as the default unless they have a specific reason to want
  something else.
- **`allow_with_warning`.** An available option, not a recommendation. Unmatched commands execute
  *silently* (only a log entry records it) -- looser than `ask` in a real, not just theoretical,
  way. Offer it for someone who finds prompting too disruptive and knowingly accepts that
  tradeoff; do not steer them toward it as the easy/default choice.
- **`deny`.** A **preference, not a requirement**, for someone who specifically wants maximum
  strictness. With `deny`, an unmatched command is *blocked* (fully fail-closed) -- **stricter
  than Claude Code's own default** -- and can feel restrictive day to day. Recommend it only if
  they say they want maximum strictness and are comfortable with the extra friction.

It is their call how tight they want to be -- your job is to make sure they understand the
tradeoff between the three, not to push them toward whichever feels quietest in the moment.
(`allow` and its `allow_with_no_warnings` alias also exist and resolve to the CLI's
`--no-match-fallback` choices, but are deliberately not part of this three-option
conversation -- see 10.2's config note above for why.)

**10.3 Re-validate under takeover.** Re-run `toolguard-audit --with-context --format json` and
confirm top-level `takeover_active` is now **true**, `sources` are as expected, and the
self-permission probes resolve as intended (audit allowed, maintain ask). Run the takeover audit
if available and address any findings (e.g. an uncovered blanket allow). Report the result.

**10.4 Recommend where future rules should go.** Now that takeover is active, tell the user: from
here on, new permission rules should go into toolguard's own config (`toolguard_hook.toml` /
`.local.toml`), not hand-added to Claude's native `settings.json` / `settings.local.json`. Be
precise about *why*, since both technically still work -- toolguard reads native settings.json as
one of its config sources regardless of takeover, so a rule added there is still honored. The
reason to prefer toolguard's own file going forward is **consistency and maintainability**: one
place to look, and toolguard's regex/glob/native pattern extensions are only available there.
Frame this as a recommendation, not a restriction -- do not tell them native edits are unsafe or
will stop working, because they will not.

---

## Wrap-up

Summarize what was done (scope, install method, whether takeover was enabled and at what
`no_match_fallback`, whether skills were installed, any migrations). Tell the user:

- Their setup is validated and active. If takeover was enabled, describe the current posture in
  **plain language** -- e.g. "a command that matches none of your rules currently prompts you,
  same as Claude's own normal behavior" (or, if they chose `allow_with_warning` instead of the
  recommended `ask`, "...is currently allowed but logged with a warning") -- not the raw config
  token. If they might tighten it later, frame `deny` as an optional preference (stricter than
  Claude's own prompt-on-unmatched default), per Phase 10.2 -- do not push it.
- If takeover was enabled, remind them (per Phase 10.4): new rules from now on should go into
  toolguard's own config, not hand-added to Claude's native settings -- both still work, but one
  place is easier to keep consistent.
- The full record is in `~/.toolguard/install-journal.md`, and `~/.toolguard/README.txt`
  explains the directory. Both are kept indefinitely -- even after an uninstall.
- They can re-run any offered step (migration, audit, maintenance, or enabling takeover)
  whenever they like.
- **If they ever want to remove toolguard, they can point you at
  [docs/uninstall.md](uninstall.md) and you will roll everything back reliably from the
  journal** -- they will not have to reverse-engineer what was changed.

**MANDATORY final step -- do not skip it.** Before you consider the install (or a rollback)
finished, you MUST **offer the session-trace dump** (Phase T.1) -- it is useful even for a clean
install and essential when anything went wrong. This has been missed repeatedly; treat "offered
the trace dump" as part of the definition of done, and if any toolguard problem surfaced during
the session, also offer to file an issue (Phase T.2). Do not end the conversation without having
made the offer.

---

## The install journal (`~/.toolguard/install-journal.md`)

A durable, append-only, human- and agent-readable record of every change this process made, so
a future agent can undo it precisely. **Never delete or rewrite past entries; only append.**
Keep it forever.

Write one entry per system-modifying action, most-recent last, each with a monotonically
increasing order index:

```
## [3] 2026-07-07 14:12 local -- register user-level hooks
- scope: user (~/.claude)
- action: edited ~/.claude/settings.json to add PreToolUse matchers for Bash/Read/Write/Edit
  and a SessionStart alert, pointing at ~/.local/bin/toolguard
- backup: ~/.toolguard/backups/settings.json.2026-07-07T141200
- reverse: restore the backup above over ~/.claude/settings.json (removes exactly these hooks)
- reverse-order: undo AFTER any skills/config added later, BEFORE uninstalling the tool
```

Guidelines:

- **Record the reverse as a concrete action**, not "remove the hooks" in the abstract -- name
  the backup to restore or the exact file to delete.
- **Capture ordering.** Uninstall replays reverses in REVERSE order (last thing done is undone
  first): skills -> config files -> hook registration -> the toolguard tool -> uv (only if this
  process installed it, and only with fresh confirmation).
- **Note provenance for shared things.** If you installed uv (a separate tool the user may come
  to rely on), mark it so uninstall knows it *may* offer to remove it -- but always re-confirm at
  uninstall time. Note that `~/.toolguard/` itself is NOT part of teardown: uninstall leaves its
  (non-executable) contents in place for auditability; see [uninstall.md](uninstall.md).
- **Back up under `~/.toolguard/backups/`** so all restore points live in one place the journal
  can reference -- and so they survive an uninstall along with the journal.

---

## Phase R -- Rollback during install (if the user changes their mind)

If the user wants to abandon the install partway through, do NOT improvise: read the journal
and undo the recorded steps in reverse order, each with consent and using the recorded reverse
action, exactly as [docs/uninstall.md](uninstall.md) describes. Then confirm toolguard no
longer governs (a `toolguard --eval` that no longer resolves, or the hooks gone from settings).
The journal makes this reliable even mid-flight. When you are done, offer the trace dump and, if
toolguard itself misbehaved, the issue report -- see Phase T.

---

## Phase T -- Trace dump and issue reporting (offer this)

**Offer a session-trace dump at the end** -- always after a rollback or any toolguard
misbehavior, and it is reasonable to offer it after a clean install too. Users often need an
auditable record of what happened, to reproduce a problem or to send to the toolguard author.
**If ANY toolguard problem surfaced during the install, proactively offer the dump at the very
end -- do not wait for the user to ask.** (A real miss: an install hit bugs, finished, and never
offered the dump; the user had to request it.)

**T.1 Offer the trace dump.** Offer to write a focused, auditable markdown record of the session
to a file the user chooses -- **default to `~/.toolguard/traces/toolguard-install-trace-<datetime>.md`**
(create `traces/` if absent) rather than dropping it directly in `$HOME`; it belongs alongside the
journal, backups, and `errors/` as one of the auditable records this directory holds, and keeping
it there is what lets a later uninstall (Step 5) find and quote it automatically. Honor a
different location if the user asks for one. Build it **from the session transcript, not your
working memory**; fill obvious gaps from working memory only where
the transcript clearly missed something, and label such notes `[inferred]`. Include: the
environment and toolguard version/commit; the ordered timeline of user messages and every tool
call with its result (allows / denies / warnings, verbatim strings); the exact reproduction of
any problem; a clear separation of "the agent did X" vs "toolguard did Y" (so agent mistakes are
not misread as toolguard bugs); and the final state. This is the same record that makes a good
bug report.

**List every individual permission/consent prompt separately, not just as a phase summary.** If
the session felt noisy (more confirmation dialogs than expected), a phase-level summary ("Phase 4
ran") hides exactly the detail needed to diagnose it. Include a short ordered list of each
distinct prompt/consent moment (native Claude permission dialog, `AskUserQuestion`, or a toolguard
`ask` verdict) with the exact command/action it was for -- so a later reviewer can tell which ones
were deliberate checkpoints (by design) versus avoidable repeats of something already covered by
an earlier allow rule.

**Always check `~/.toolguard/errors/` and fold in anything there, verbatim.** Any unexpected
exception in the hook (a parse failure, a config load error, anything the hook itself did not
expect) gets a detailed crash report written there -- full traceback and the exact input that
triggered it -- independent of whether you noticed a problem in the conversation. If a symptom
this session was vague (e.g. something that just looked like "a parse error" with no exact text
captured), this directory is the authoritative record; quote its contents in full rather than
paraphrasing from memory, and say so explicitly if the directory is empty (that itself is useful
signal -- it means the trouble was not an unhandled exception in the hook).

**T.2 If toolguard ITSELF appears to have a bug, offer to file an issue.** Whenever the trouble
looks like a defect in toolguard rather than the environment or your own mistake -- and
**especially if the user chose to roll the install back** -- offer to open a GitHub issue **on
the user's behalf** at <https://github.com/arnonmoscona/toolguard/issues>, attaching the summary
and the T.1 trace dump. Before opening anything:

- **Search existing issues first.** Query the repo's issues (open, and recently closed) for the
  same symptom -- `gh issue list` / `gh search issues` if `gh` is available, otherwise the
  GitHub search UI/API. **Show the user any that look related.**
- **Let the user judge:** are any of these the same problem (then add a comment with your trace,
  or just point them at it), or is this genuinely new?
- **`gh` vs the browser -- offer the choice, don't just install `gh`.** If `gh` is not present,
  do NOT silently install it: tell the user you can either install `gh` (a general-purpose tool
  they may want anyway) **or** they can open the issue in their browser -- let them pick. If `gh`
  is present but unauthenticated, or the user prefers the browser, hand them the prepared
  title + body to paste into the web "New issue" form rather than failing silently.
- **Open a new issue only with the user's explicit go-ahead.** Title it by the symptom; body = a
  short summary + environment/versions. Keep it ASCII.
- **Always attach the T.1 trace dump to the issue.** `gh` cannot attach a file, so paste the
  trace dump's contents into the issue body or a follow-up comment (or upload it as a gist and
  link it) -- an issue without the trace is much harder to act on.
- **Attach the dump to every issue this session touched.** If you opened issues *earlier* in the
  session (before the dump existed), go back and add the dump to them as a comment now. If you
  open issues *after* writing the dump, attach it at creation. The trace should be on all of them.

Never file an issue, or comment on one, without the user's consent.
