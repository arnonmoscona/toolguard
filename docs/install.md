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

## Phase 0 -- Preflight

**0.1 Start the journal (and explain the directory).** Ensure `~/.toolguard/` exists and open
(create if absent) `~/.toolguard/install-journal.md`. If it already exists, read it first -- a
prior session may have done some steps; continue from where it left off rather than repeating.
Append a session header (date/time, "guided install started").

At the same time, create `~/.toolguard/README.txt` (if absent) so the directory is
self-explanatory to anyone who finds it later. It should state, in plain ASCII: what
`~/.toolguard/` is (toolguard's per-user state: the install journal, config/settings backups,
and the decision ledger); where toolguard was installed from (fill in the actual source --
e.g. `git+https://github.com/<owner>/toolguard` or a local path); and that **this directory is
intentionally NOT deleted on uninstall** -- it is kept for auditability and problem resolution,
holds nothing executable, and the user may delete it by hand at any time. Record its creation
in the journal -- there is nothing to reverse, since (like the rest of `~/.toolguard/`)
`README.txt` is deliberately left in place on uninstall.

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
- **`no_match_fallback` -- decided at Phase 10, not now.** When takeover is switched on it starts
  at the gentle `warn_deny` (unmatched commands are allowed but flagged, so nothing breaks while
  rules are still thin), and the user can tighten it to fail-closed `deny` once they are
  confident. Phase 10 walks this; there is nothing to set here.

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

---

## Phase 4 -- Write the base config, then register the hook (go-live LAST)

Use the exact hook JSON and `toolguard_hook.toml` shape from
[agent-guides.md](agent-guides.md#recipe-install-and-register-toolguard-from-scratch); do not
reinvent them. Put them at the scope chosen in Phase 1 (`~/.claude/` for user level, the
project's `.claude/` for a single project). **Order matters:** registering the hook is the
instant toolguard goes live and starts governing your own tool calls, so do it **last**, after
the config it will read is already on disk. Stage the file writes as one script (per the
atomic-groups principle) and apply it; register the hooks as a separate final step.

1. **Back up first.** Copy any file you are about to edit (`settings.json` /
   `settings.local.json`) to a timestamped backup under `~/.toolguard/backups/`, and journal the
   backup path (reverse: restore the backup).
2. **Write the config (group 1 -- while toolguard is still dormant).** Write `toolguard_hook.toml`
   with `governed_tools` (and `additional_supported_tools` for any custom MCP command tool) from
   Phase 2, and **takeover disabled** for now -- either omit the `[takeover_mode]` section or
   write `enabled = false`. Do NOT enable takeover here even if the user chose it: Phase 10 does
   that once rules exist (see Phase 2). Stage this (plus any other non-hook file writes) into one
   script under `~/.toolguard/stage/`, apply it once, and journal it (reverse: delete the file,
   or restore its prior version if one existed). Nothing is governing yet, so this cannot lock
   you out.
3. **Register the hooks LAST (go-live).** Only now edit `settings.json` / `settings.local.json`
   to add one PreToolUse matcher per governed tool + the SessionStart alert, pointing at the
   installed `toolguard` / `toolguard-session-start` entry points. This is the step that makes
   toolguard live -- and because the config from step 2 is already on disk (and takeover is off,
   so unmatched calls resolve to `ask`, never a hard deny), it will not lock the session out.
   Journal the exact edit (reverse: restore the backup, or remove the added hook block).

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
which are missing. Journal each rule added (reverse: remove that rule).

**10.2 Offer recommended secret protections (optional, with consent).** A fail-closed setup is a
good moment to add `[hard_deny]` protections for credentials (e.g. `Read(**/.env)`,
`Read(**/.ssh/**)`), per [security.md](security.md) and
[agent-guides.md](agent-guides.md#recipe-block-a-command-no-matter-what). Offer them; do not add
them silently.

**10.3 Enable takeover, starting gentle.** Edit `toolguard_hook.toml` to set
`[takeover_mode] enabled = true` with `no_match_fallback = "warn_deny"` -- unmatched commands are
allowed but flagged, so nothing breaks while the rule set is still thin. Explain that once they
are confident the rules cover their workflow, they (or a maintenance pass) can tighten it to
`no_match_fallback = "deny"` for a fully fail-closed posture. Back up the file first and journal
the change (reverse: restore the backup / set `enabled = false`).

**10.4 Re-validate under takeover.** Re-run `toolguard-audit --with-context --format json` and
confirm top-level `takeover_active` is now **true**, `sources` are as expected, and the
self-permission probes resolve as intended (audit allowed, maintain ask). Run the takeover audit
if available and address any findings (e.g. an uncovered blanket allow). Report the result.

---

## Wrap-up

Summarize what was done (scope, install method, whether takeover was enabled and at what
`no_match_fallback`, whether skills were installed, any migrations). Tell the user:

- Their setup is validated and active. If takeover was enabled, note it started at `warn_deny`
  (nothing blocked, unmatched commands flagged) and how to tighten it to `deny` later.
- The full record is in `~/.toolguard/install-journal.md`, and `~/.toolguard/README.txt`
  explains the directory. Both are kept indefinitely -- even after an uninstall.
- They can re-run any offered step (migration, audit, maintenance, or enabling takeover)
  whenever they like.
- **If they ever want to remove toolguard, they can point you at
  [docs/uninstall.md](uninstall.md) and you will roll everything back reliably from the
  journal** -- they will not have to reverse-engineer what was changed.

Then **offer the session-trace dump** (Phase T.1) -- useful even for a clean install. If
anything about toolguard itself misbehaved along the way, also offer to file an issue (Phase
T.2).

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

**T.1 Offer the trace dump.** Offer to write a focused, auditable markdown record of the session
to a file the user chooses (e.g. `~/toolguard-install-trace-<date>.md`). Build it **from the
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
- **Open a new issue only with the user's explicit go-ahead.** Title it by the symptom; body = a
  short summary + environment/versions + the trace dump (linked or pasted). Keep it ASCII. If
  `gh` is not authenticated, hand the user the prepared title+body to paste into the web "New
  issue" form rather than failing silently.

Never file an issue, or comment on one, without the user's consent.
