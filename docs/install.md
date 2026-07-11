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

- [ ] **Phase 0** preflight (READ-ONLY -- no writes yet): detect environment; **check
      `CLAUDE_SETTINGS_PATH`**; detect any existing install
- [ ] Set expectations (unconventional + slower, but adaptable / user-in-control / self-rescuing /
      safe+rollbackable / auto-reports issues) and **get a go-ahead**
- [ ] **Phase 1** scope (user vs project)
- [ ] **Phase 2** options (governed_tools; takeover decided now, enabled late)
- [ ] **Phase 3** install the package (`uv tool install`) -- puts `toolguard-install` on PATH --
      then `toolguard-install init-state` (creates `~/.toolguard/` + journal) and journal the install
- [ ] Pre-approve `Bash(toolguard-install:*)` once to cut prompt noise (see the helper section)
- [ ] **Phase 4** write the base config (`write-config`), then **register hooks LAST**
      (`register-hooks` = go-live)
- [ ] **Phase 5** skills (ask)
- [ ] **Phase 6** validate
- [ ] **Phase 7** migration (optional) -- this is the "**move** your rules" step; be takeover-aware;
      confirm the project list and where rules land
- [ ] **Phase 8** security audit (optional) -- **never remove a flagged rule without consent**
- [ ] **Phase 9** maintenance pass (optional) -- this is the separate "**review / clean up**" step
- [ ] **Phase 10** enable takeover (only if chosen) -- seed self-permissions (`seed-self-perms`);
      then `enable-takeover` starting gentle; describe the posture in plain language; do not push `deny`
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

- **`governed_tools` -- govern what they use.** Recommend `Bash`, `Read`, `Write`, `Edit`,
  plus any command-running MCP tool they use (e.g. `mcp__jetbrains__execute_terminal_command`;
  a custom MCP shell tool also goes in `additional_supported_tools`). Ask which they use;
  default to the built-in four if unsure.
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
  takeover is switched on (Phase 10) it starts at the gentle `allow_with_warning` (unmatched
  commands are allowed but flagged, so nothing breaks while rules are still thin), and the user
  can tighten it to fail-closed `deny` once confident. The values are `ask` (prompt) /
  `allow_with_warning` (allow + warn) / `deny` (fail-closed). Phase 10 walks this; nothing to set
  here.

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
2. **Journal the package install** (the helper cannot journal its own installation):
   `toolguard-install journal --action "installed toolguard via uv tool install (vX.Y.Z)" --reverse "uv tool uninstall toolguard"`
   -- and if you installed `uv`, journal that separately with its reverse.
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

If the helper does not fit (an unusual settings layout, a manager other than `uv`, hand-off mode),
fall back to editing the files by hand using the exact hook JSON / `toolguard_hook.toml` shape from
[agent-guides.md](agent-guides.md#recipe-install-and-register-toolguard-from-scratch) -- back up
first and record it with `toolguard-install journal --action ... --reverse ...`.

---

## Phase 5 -- Skills (ask the user)

The maintenance and security-audit skills can either be installed persistently or just run
from this repo for the initial passes. **Ask the user which they want:**

- **Install persistently (user scope):** copy `skills/toolguard-security-audit/` and
  `skills/toolguard-maintenance/` into `~/.claude/skills/` so `/toolguard-security-audit` and
  `/toolguard-maintenance` work in every project from now on. Journal each (reverse: remove the
  installed skill directory). Use this if they expect to curate/audit toolguard regularly.
  - **Do NOT hand-roll a bespoke fetch script for this** (a past attempt wrote an ad-hoc shell
    loop that created a malformed directory). If you installed from a local checkout, copy the
    two skill directories directly. If you installed from the repo URL (no checkout), fetch the
    skill files cleanly from the repo at the installed commit (raw files, exact paths) into the
    target directory -- one straightforward copy per file, no clever shell. (A standard
    `toolguard-install-skills` helper is planned to remove this step entirely.)
- **Run from the repo for now:** skip persistent install. The initial audit and maintenance
  below will run by following this repo's `skills/*/SKILL.md` files directly (you are already
  pointed at the repo). Persistent skill installation can be done later.

Record their choice; it decides how you invoke the audit/maintenance passes in Phases 8-9.

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

### 7.1 Discover candidate projects

Build the list from the two places Claude Code records where it has been used, then reconcile:

- **Authoritative: `~/.claude.json`.** Its top-level `projects` object is keyed by the
  **absolute path** of every project Claude has worked in. Read the keys directly, e.g.
  `jq -r '.projects | keys[]' ~/.claude.json`. Treat these as the primary list.
- **Supplementary: `~/.claude/projects/`.** This holds one transcript directory per project,
  named by encoding the absolute path (the leading `/` and every `/` become `-`, so
  `/home/me/app` -> `-home-me-app`). Use it only to catch a project the JSON missed. **Decoding
  is lossy** -- a real `-` in a path is indistinguishable from an encoded `/` -- so never trust
  a decoded path blindly; only accept one that exists on disk.

Then reconcile into a clean candidate list:

- **Keep only directories that still exist** (a recorded project may have been moved/deleted).
- **Keep only projects worth migrating:** those with a `.claude/settings.local.json` that
  actually contains permission rules. Skip ones with nothing to migrate.
- **Flag, do not skip, projects that already have a `toolguard_hook.toml`** -- migrating again
  is usually a no-op but the user should know which are already set up.
- **Recognize takeover-configured projects -- do NOT misread their blanket allows.** A project
  that already runs toolguard in **takeover mode** deliberately keeps broad `Bash(*)` / `Read(*)`
  / `Write(*)` / `Edit(*)` allows in its `settings.local.json` **on purpose**: those are the
  native blanket allows that the project's own `takeover_mode.ignored_allow_patterns` neutralizes,
  and its real rules live in its `toolguard_hook.toml`. These blanket allows are **not** stray
  standalone permissions to migrate -- presenting them that way to the user is wrong and alarming.
  Before analyzing a candidate's `settings.local.json`, check whether it has a `toolguard_hook.toml`
  with `[takeover_mode] enabled = true`; if so, say plainly that it is an existing takeover setup
  whose blanket allows are intentional, and leave them alone. (The migration tool is already
  takeover-aware and ignores them; your *conversational analysis* must be too.)

### 7.2 Confirm the list with the user

Present the discovered candidates as a simple checklist (path, whether it already has toolguard,
roughly how many rules would move) and **ask the user to adjust it**: remove any they do not
want touched, and add any project the discovery missed (a brand-new repo Claude has not opened
yet will not appear). Migrate only the projects they confirm. This keeps the user in control and
never touches a project silently.

### 7.3 Cut the noise for this batch, then migrate each confirmed project

**Checkpoint: a new permission group just became known -- ask for it once, not per project.**
Once the list is confirmed (7.2), you know exactly which projects you are about to run the
migrator against. Rather than letting each project's dry-run and apply calls prompt separately,
propose one allow rule that covers the whole confirmed batch up front, e.g.
`Bash(uv run python -m toolguard.scripts.migrate_permissions:*)` (or scoped further per the
user's preference). Journal it like any other rule (reverse: remove it; uninstall removes it).
This is the same "pre-approve once, cut the noise" principle as the `toolguard-install` allow
rule in Phase 3 -- just applied at the checkpoint where migration's own permission needs become
known, rather than guessed at the start of the install.

For each project on the confirmed list, **dry-run first** so the user can review, then apply:

```bash
# from within the project (or point the migrator at its directory), review, then apply
uv run python -m toolguard.scripts.migrate_permissions --dry-run   # detects duplicates/supersets
uv run python -m toolguard.scripts.migrate_permissions             # applies; writes a timestamped backup
```

Apply creates a timestamped backup automatically. Journal each applied migration (reverse:
restore that backup). See [config-sync.md](config-sync.md) for the full behavior.

**Confirm where the rules will land -- do not let project-root detection decide silently.**
toolguard finds a project root by walking up for a `.git`/`pyproject.toml` marker. A directory
without such a marker (a bare `~/projects` holding many repos is a common case) is NOT treated as
a project, so its migrated rules cascade to the **user level** (`~/.claude/toolguard_hook.toml`)
instead of a project `.claude/`. That may not be what the user expects -- user-level rules apply
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

---

## Phase 8 -- Offer a security audit (optional)

Ask: "Want me to security-check your permissions now?" If yes, run the security-audit skill --
via `/toolguard-security-audit` if it was installed in Phase 5, otherwise by following this
repo's `skills/toolguard-security-audit/SKILL.md` directly. The audit itself is read-only:
present the findings and, for anything risky, the suggested fix.

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

Ask: "Want me to organize your new toolguard setup?" If yes, run the maintenance skill --
via `/toolguard-maintenance` if installed, otherwise by following
`skills/toolguard-maintenance/SKILL.md` directly. This is the first run, so it will walk the
whole config with them and apply only what they approve. See [skills.md](skills.md) for what to
expect.

---

## Phase 10 -- Enable takeover (only if the user chose it in Phase 2)

If the user did NOT choose takeover, skip this phase; leave a note that they can enable it later
(a maintenance pass, or by re-running this phase). If they DID, this is where you switch
toolguard from add-on mode to the real gatekeeper -- now that rules exist, so it does not lock
itself (or the user) out.

**10.1 Seed the permissions toolguard itself needs (ask first, then seed).** Under takeover with
a fail-closed fallback, toolguard governs its OWN skills' commands and its own state directory.
If those are not permitted, the audit/maintenance skills' calls get denied and `~/.toolguard/`
becomes unreadable -- the exact self-inflicted lockout to avoid. These are not invented user
allow-rules; they are the minimum for toolguard's own tooling to keep working, so **propose them
explicitly, explain each, and add them only with consent**, at the chosen scope:

- `Bash(toolguard-audit:*)` -> **allow** (read-only; the audit skill runs it).
- `Bash(toolguard-maintain:*)` -> **ask** (it can write config; per-invocation consent, never a
  blanket allow, so the model cannot silently mutate the security config).
- Read/Write/Edit access to `~/.toolguard/**` (the install journal and the decision ledger live
  there).

These come from toolguard's single source of truth for self-permissions
(`toolguard.tools.self_permission`); if a skill is installed you can also let it compute exactly
which are missing. Once the user consents, add them in one command:
`toolguard-install seed-self-perms --scope <user|project> [--project-dir <path>]` -- it reads that
same source of truth, adds exactly those rules (idempotently -- a second run is a no-op), backs up
the config first, and journals the change with its reverse.

**10.2 Offer recommended secret protections (optional, with consent).** A fail-closed setup is a
good moment to add `[hard_deny]` protections for credentials (e.g. `Read(**/.env)`,
`Read(**/.ssh/**)`), per [security.md](security.md) and
[agent-guides.md](agent-guides.md#recipe-block-a-command-no-matter-what). Offer them; do not add
them silently.

**10.3 Enable takeover, starting gentle.** Turn it on in one command:
`toolguard-install enable-takeover --scope <user|project> [--project-dir <path>] --no-match-fallback allow_with_warning`
(this backs up the config and journals with its reverse). Describe the result to the user in
**plain language, not config tokens** -- e.g. "right now, a command that matches none of your rules
is *allowed but logged with a warning*, so nothing breaks while your rule set is still thin."

Tightening to `deny` is a **preference, not a requirement** -- present it that way. Explain: with
`deny`, an unmatched command is *blocked* (fully fail-closed), which is **stricter than Claude
Code's own default** (Claude *prompts* -- "ask" -- on anything it has no rule for). A fail-closed
setup is the safest but can feel restrictive day to day. So recommend `deny` only if they
specifically want maximum strictness and are comfortable with the extra friction; otherwise
leaving it at allowed-but-warned (or moving to prompt-on-unmatched) is perfectly reasonable. It is
their call about how tight they want to be.

**10.4 Re-validate under takeover.** Re-run `toolguard-audit --with-context --format json` and
confirm top-level `takeover_active` is now **true**, `sources` are as expected, and the
self-permission probes resolve as intended (audit allowed, maintain ask). Run the takeover audit
if available and address any findings (e.g. an uncovered blanket allow). Report the result.

---

## Wrap-up

Summarize what was done (scope, install method, whether takeover was enabled and at what
`no_match_fallback`, whether skills were installed, any migrations). Tell the user:

- Their setup is validated and active. If takeover was enabled, describe the current posture in
  **plain language** -- e.g. "a command that matches none of your rules is currently allowed but
  logged with a warning" -- not the raw `allow_with_warning` token. If they might tighten it
  later, frame `deny` as an optional preference (stricter than Claude's own prompt-on-unmatched
  default), per Phase 10.3 -- do not push it.
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
to a file the user chooses (e.g. `~/toolguard-install-trace-<datetime>.md`). Build it **from the
session transcript, not your working memory**; fill obvious gaps from working memory only where
the transcript clearly missed something, and label such notes `[inferred]`. Include: the
environment and toolguard version/commit; the ordered timeline of user messages and every tool
call with its result (allows / denies / warnings, verbatim strings); the exact reproduction of
any problem; a clear separation of "the agent did X" vs "toolguard did Y" (so agent mistakes are
not misread as toolguard bugs); and the final state. This is the same record that makes a good
bug report.

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
