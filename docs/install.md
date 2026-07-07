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

## Principles (follow these throughout)

- **Consent before every system-modifying action.** Installing a tool, editing
  `~/.claude/settings.json`, writing a config file, installing a package manager -- each one
  is proposed, explained briefly, and done only after the user agrees. Never batch silent
  changes.
- **Do it for them.** Prefer taking the action yourself (with consent) over telling the user
  to run commands, unless they ask to drive.
- **Right info, right time.** Explain a choice only when it is being made. Do not dump the
  whole design on them up front.
- **Stop anytime, resume anytime.** After each phase, the user may stop. The install journal
  (below) is the source of truth for what is done, so a later session can continue or roll
  back.
- **Journal everything, with its reverse.** Before/after every system-modifying step, append
  an entry to `~/.toolguard/install-journal.md` recording the action AND the exact command to
  undo it (see "The install journal"). This is what makes a clean, reliable uninstall possible
  later -- treat it as mandatory, not optional.
- **Local time, ASCII.** Timestamps in the user's local time; keep everything you write ASCII.

---

## Phase 0 -- Preflight

**0.1 Start the journal.** Ensure `~/.toolguard/` exists and open (create if absent)
`~/.toolguard/install-journal.md`. If it already exists, read it first -- a prior session may
have done some steps; continue from where it left off rather than repeating. Append a session
header (date/time, "guided install started").

**0.2 Detect the environment.** Note the OS/shell, whether Claude Code is present
(`~/.claude/` exists), whether `uv` is on PATH (`uv --version`), and whether `toolguard` is
already on PATH (`command -v toolguard`).

**0.3 Detect an existing toolguard install (edge cases).**

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

- **Takeover mode -- RECOMMENDED ON.** Explain: with takeover on, toolguard becomes the real
  gatekeeper -- it neutralizes broad "allow everything" rules that Claude Code may have saved,
  and falls closed (deny) when no rule matches, so nothing slips through unreviewed. Without
  it, toolguard only adds rules alongside Claude's own approvals. The one requirement is that
  the hook is actually registered (Phase 4 does this). The only cost is an occasional double
  prompt where a native allow overlaps. Recommend enabling it; record their choice.
- **`no_match_fallback` -- RECOMMENDED `deny`.** With takeover on, a command that matches no
  rule is denied (fail-closed). Recommend `deny`; `ask` is the softer alternative.
- **`governed_tools` -- govern what they use.** Recommend `Bash`, `Read`, `Write`, `Edit`,
  plus any command-running MCP tool they use (e.g. `mcp__jetbrains__execute_terminal_command`;
  a custom MCP shell tool also goes in `additional_supported_tools`). Ask which they use;
  default to the built-in four if unsure.

Keep the base config minimal and safe; the user can refine later with the maintenance skill.

---

## Phase 3 -- Install method

**Recommend `uv tool install`** -- it puts the `toolguard` entry points on PATH in an isolated
environment. Propose:

```bash
uv tool install /path/to/this/repo        # from the local checkout the user pointed you at
# or: uv tool install git+https://github.com/<owner>/toolguard
uv tool update-shell
```

Then journal it (reverse: `uv tool uninstall toolguard`).

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

---

## Phase 4 -- Register the hook and write the base config

Use the exact hook JSON and `toolguard_hook.toml` shape from
[agent-guides.md](agent-guides.md#recipe-install-and-register-toolguard-from-scratch); do not
reinvent them. Put them at the scope chosen in Phase 1 (`~/.claude/` for user level, the
project's `.claude/` for a single project).

1. **Back up first.** Copy any file you are about to edit (`settings.json` /
   `settings.local.json`) to a timestamped backup, and journal the backup path (reverse:
   restore the backup).
2. **Register hooks** -- one PreToolUse matcher per governed tool + the SessionStart alert,
   pointing at the installed `toolguard` / `toolguard-session-start` entry points. Journal the
   exact edit (reverse: restore the backup, or remove the added hook block).
3. **Write `toolguard_hook.toml`** with the Phase-2 choices (`[takeover_mode]`,
   `no_match_fallback`, `governed_tools`, `additional_supported_tools`). Journal it (reverse:
   delete the file, or restore its prior version if one existed).

---

## Phase 5 -- Skills (ask the user)

The maintenance and security-audit skills can either be installed persistently or just run
from this repo for the initial passes. **Ask the user which they want:**

- **Install persistently (user scope):** copy `skills/toolguard-security-audit/` and
  `skills/toolguard-maintenance/` into `~/.claude/skills/` so `/toolguard-security-audit` and
  `/toolguard-maintenance` work in every project from now on. Journal each (reverse: remove the
  installed skill directory). Use this if they expect to curate/audit toolguard regularly.
- **Run from the repo for now:** skip persistent install. The initial audit and maintenance
  below will run by following this repo's `skills/*/SKILL.md` files directly (you are already
  pointed at the repo). Persistent skill installation can be done later.

Record their choice; it decides how you invoke the audit/maintenance passes in Phases 8-9.

---

## Phase 6 -- Validate

Prove the install works before offering anything else:

- Run `toolguard --eval` on a representative event (read-only; it resolves a command without
  changing config or logging) and confirm it returns a decision.
- Run `toolguard-audit --with-context --format json` at the chosen scope; confirm it loads,
  `context.summary.sources` includes the config you just wrote, and top-level
  `takeover_active` matches the user's choice.
- Report the result plainly. If validation fails (no decision, wrong sources, unexpected
  `hook-not-registered`), diagnose it (usually a hook not registered or a path that did not
  expand) and offer to fix -- or, if the user prefers, to roll back what was done so far
  (Phase R).

---

## Phase 7 -- Offer an initial migration (optional)

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

### 7.2 Confirm the list with the user

Present the discovered candidates as a simple checklist (path, whether it already has toolguard,
roughly how many rules would move) and **ask the user to adjust it**: remove any they do not
want touched, and add any project the discovery missed (a brand-new repo Claude has not opened
yet will not appear). Migrate only the projects they confirm. This keeps the user in control and
never touches a project silently.

### 7.3 Migrate each confirmed project

For each project on the confirmed list, **dry-run first** so the user can review, then apply:

```bash
# from within the project (or point the migrator at its directory), review, then apply
uv run python -m toolguard.scripts.migrate_permissions --dry-run   # detects duplicates/supersets
uv run python -m toolguard.scripts.migrate_permissions             # applies; writes a timestamped backup
```

Apply creates a timestamped backup automatically. Journal each applied migration (reverse:
restore that backup). See [config-sync.md](config-sync.md) for the full behavior.

If they decline the whole step, note that migration can be done anytime later, the same way.

---

## Phase 8 -- Offer a security audit (optional)

Ask: "Want me to security-check your permissions now?" If yes, run the security-audit skill --
via `/toolguard-security-audit` if it was installed in Phase 5, otherwise by following this
repo's `skills/toolguard-security-audit/SKILL.md` directly. Present the findings and, for
anything risky, the suggested fixes. This is read-only.

---

## Phase 9 -- Offer an initial maintenance pass (optional)

Ask: "Want me to organize your new toolguard setup?" If yes, run the maintenance skill --
via `/toolguard-maintenance` if installed, otherwise by following
`skills/toolguard-maintenance/SKILL.md` directly. This is the first run, so it will walk the
whole config with them and apply only what they approve. See [skills.md](skills.md) for what to
expect.

---

## Wrap-up

Summarize what was done (scope, install method, takeover choice, whether skills were installed,
any migrations). Tell the user:

- Their setup is validated and active.
- The full record is in `~/.toolguard/install-journal.md`, kept indefinitely.
- They can re-run any offered step (migration, audit, maintenance) whenever they like.
- **If they ever want to remove toolguard, they can point you at
  [docs/uninstall.md](uninstall.md) and you will roll everything back reliably from the
  journal** -- they will not have to reverse-engineer what was changed.

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
- **Note provenance for shared things.** If you installed uv, or created `~/.toolguard`, mark
  it so uninstall knows it may remove it -- but always re-confirm at uninstall time, since the
  user may have come to rely on it.
- **Back up under `~/.toolguard/backups/`** so all restore points live in one place the journal
  can reference.

---

## Phase R -- Rollback during install (if the user changes their mind)

If the user wants to abandon the install partway through, do NOT improvise: read the journal
and undo the recorded steps in reverse order, each with consent and using the recorded reverse
action, exactly as [docs/uninstall.md](uninstall.md) describes. Then confirm toolguard no
longer governs (a `toolguard --eval` that no longer resolves, or the hooks gone from settings).
The journal makes this reliable even mid-flight.
