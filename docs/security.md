# Security Best Practices

## Blanket allow risks

**Never use blanket allows without toolguard protection.**

```json
{
  "permissions": {
    "allow": ["Bash(*)", "Write(*)"]
  }
}
```

**Why this is dangerous**:

- Claude can execute ANY command or write ANY file.
- There is no protection against mistakes or malicious suggestions.
- It bypasses all security controls.

**Safe approaches**:

1. **Specific patterns only** (no takeover mode):

   ```json
   {
     "permissions": {
       "allow": [
         "Bash(git status:*)",
         "Write(~/projects/myapp/**)"
       ]
     }
   }
   ```

2. **Takeover mode with toolguard** (blanket allows OK -- see [Takeover Mode](takeover-mode.md)):

   ```toml
   # In settings.local.json: Bash(*), Write(*)
   # In toolguard_hook.toml:
   [takeover_mode]
   enabled = true

   [permissions]
   allow = ["Bash(git status:*)", "Write(~/projects/myapp/**)"]
   deny = ["Bash(rm -rf:*)", "Write(**/.env)"]
   ```

For rules that must hold no matter what any project config says, promote them to
[`[hard_deny]`](configuration.md#configuration-reference), which is pooled across all
hierarchy levels and cannot be overridden by an allow at any level.

## Backup importance

**Always test changes with backups.**

1. **Before enabling takeover mode**:

   ```bash
   # Backup your configs
   cp .claude/settings.local.json .claude/settings.local.json.backup
   cp .claude/toolguard_hook.toml .claude/toolguard_hook.toml.backup
   ```

2. **Before running migration**:

   ```bash
   # Dry run first
   uv run python -m toolguard.scripts.migrate_permissions --dry-run

   # Migration creates an automatic backup, but a manual backup doesn't hurt
   cp .claude/toolguard_hook.toml logs/manual-backup-$(date +%Y-%m-%d).toml
   ```

3. **Regular backups**:

   ```bash
   # Weekly backup
   cp .claude/toolguard_hook.toml ~/backups/toolguard-$(date +%Y-%m-%d).toml
   ```

## Testing with dry-run

**Always test migrations before executing.**

```bash
# Step 1: See what would change
uv run python -m toolguard.scripts.migrate_permissions --dry-run

# Step 2: Review output carefully
# - Are the patterns correct?
# - Any unexpected migrations?
# - Similar patterns that should be consolidated?

# Step 3: Execute only if dry-run looks good
uv run python -m toolguard.scripts.migrate_permissions

# Step 4: Verify the result
diff .claude/toolguard_hook.toml logs/config-backups/toolguard_hook-*.toml
```

## Verify toolguard is running

1. **Check logs after commands**:

   ```bash
   tail -20 logs/toolguard-$(date +%Y-%m-%d).md
   ```

   You should see entries for every command Claude executes.

2. **Monitor error and warning logs**:

   ```bash
   tail -f logs/toolguard-error-$(date +%Y-%m-%d).md
   tail -f logs/toolguard-warning-$(date +%Y-%m-%d).md
   ```

   Watch for warnings about configuration issues.

3. **Test with an intentional violation**: if `rm -rf /` is denied, ask Claude to run it and
   confirm it is logged as refused.

**Red flags that toolguard is NOT working**:

- No entries in `logs/toolguard-YYYY-MM-DD.md` after Claude executes commands.
- Commands execute that should be denied.
- No warnings/errors in logs when you expect them.

This matters most under [Takeover Mode](takeover-mode.md): if toolguard is silently not
running, the blanket allows are fully exposed.

## Ongoing security review

Toolguard enforces your rules, but a permission system is only as good as the attention you
give it. Set a routine to review what it logged, what it warned about, what drifted, and
whether the rules still make sense. The supporting automation (below) cuts the effort -- but,
as in any security workflow, it assists your review rather than replacing it.

| Review (suggested cadence) | What to look for | Where / supporting facility |
|----------------------------|------------------|-----------------------------|
| **Resolution log** -- after busy sessions / daily | Unexpected allows or refusals; which level and file authorized each command (the matched rule is logged with its `[level: path]` provenance) | `logs/toolguard-YYYY-MM-DD.md` (or `.jsonlines` for scripting) -- see [logging](architecture.md#logging) |
| **Error & warning logs** -- regularly | Config errors (e.g. a non-boolean `takeover_mode.enabled`), ungoverned or unsupported tools, both-format (`.toml`+`.json`) conflicts | `logs/toolguard-error-*.md`, `logs/toolguard-warning-*.md`; also surfaced once per session on stderr via [session warnings](config-sync.md#session-warnings) |
| **Conflicts & divergence** -- every session / periodically | Cross-level allow-over-deny overrides, `takeover_mode.enabled` disagreements, and rules that have drifted into native `settings.local.json` | `logs/toolguard-conflict-*.md` + the **SessionStart conflict-alert hook** (re-reports until resolved); drift via `migrate_permissions --dry-run` -- see [Config Sync](config-sync.md) |
| **The rules themselves** -- periodically (e.g. monthly) | Over-broad or blanket allows, stale / duplicate / superseded rules, gaps in `[hard_deny]` coverage | `migrate_permissions --dry-run` (duplicate / superset / similarity detection); `auto_sort_on_migrate` for readability; promote critical denies to [`[hard_deny]`](configuration.md#configuration-reference) |

A quick periodic pass:

```bash
# What ran / was refused today, with the rule + level that decided each
tail -n 50 logs/toolguard-$(date +%Y-%m-%d).md

# Config problems, conflicts, and drift
tail -n 50 logs/toolguard-error-$(date +%Y-%m-%d).md
tail -n 50 logs/toolguard-warning-$(date +%Y-%m-%d).md
tail -n 50 logs/toolguard-conflict-$(date +%Y-%m-%d).md

# Rules that drifted into native settings, plus redundant / over-broad rules
uv run python -m toolguard.scripts.migrate_permissions --dry-run
```

**What is automated vs. on you:**

- **Automatic** -- the SessionStart hook re-reports unresolved conflicts every session until
  you fix them; configuration problems are written to the error/warning logs and shown once
  per session on stderr; every decision is logged with its matched-rule provenance; conflicts
  are recorded to the conflict log; `auto_migrate` (if enabled) folds drift back on startup.
- **On you** -- actually reading those logs, running the dry-run review, and deciding whether
  each accumulated rule should stay, be narrowed, be removed, or be promoted to `[hard_deny]`.
  No automation makes those judgment calls for you.

More automation is planned over time to tighten this loop further; until then, a short
recurring review is the reliable safeguard.

## Maintaining your toolguard configuration

Over time your rules accumulate and drift. A little upkeep keeps the config readable,
reviewable, and trustworthy -- which is itself a security property: rules you cannot quickly
read are rules you cannot confidently audit.

- **Keep rules sorted.** Sorted allow/deny lists are far easier to scan, diff, and audit, and
  they make duplicates obvious. Set `auto_sort_on_migrate = true` so the migration tool sorts
  on every run (see [Config Sync](config-sync.md#auto-migration)), or sort by hand when you
  edit.
- **Consolidate similar rules into fewer regex/glob rules.** A long run of near-identical
  entries (`Bash(git status:*)`, `Bash(git log:*)`, `Bash(git diff:*)`, ...) is better
  expressed as one anchored pattern, e.g. `Bash([regex]^git (status|log|diff|branch)\b)`. The
  `migrate_permissions --dry-run` output flags duplicates, supersets, and similar clusters as
  consolidation candidates (see [Config Sync](config-sync.md#similarity-detection-and-duplicate-removal)).
  **Consolidate scope, not breadth:** replace several narrow rules with one rule that covers
  exactly the same commands -- do not collapse them into something broader (e.g. `Bash(git:*)`,
  which would also allow `git push` and `git reset --hard`). See
  [Permission Patterns](permission-patterns.md) for the syntax.
- **Manage divergence; do not fight it.** New allows will keep landing in native
  `settings.local.json` as you work -- that is unavoidable. Reconcile them into
  `toolguard_hook.toml` periodically with the migration tool rather than letting two sources
  drift (see [Config Sync](config-sync.md)).
- **Promote rules up the hierarchy; keep the project level clean.** Rules that apply
  everywhere -- general dev tooling, baseline safety denies, and especially `[hard_deny]` --
  belong at the **user level** (`~/.claude/toolguard_hook.toml`), not copied into every
  project. Keep each project's `.claude/toolguard_hook.toml` focused on what is genuinely
  project-specific. More-specific-wins still lets a project override a user-level rule when it
  truly needs to (see [the hierarchy](configuration.md#configuration-hierarchy)). A lean,
  project-focused config is easier to review and means fewer places to update a shared rule.
- **Let Claude help review the rules.** Claude is good at spotting over-broad allows,
  duplicates, risky patterns, and missing safety denies, and at proposing regex/glob
  consolidations. Ask it directly, e.g. *"Review `.claude/toolguard_hook.toml`: flag any
  over-broad or unnecessary allows, duplicates, and missing safety denies, and suggest
  consolidations -- do not edit, just report."* Treat its output as a second opinion: you make
  the final call, because the rules are **your** security policy.
- **Watch for stray rules from hasty permission answers.** A quick "Yes, and don't ask again"
  during a flow can add an allow that is broader than you intended (or that you would not have
  approved on reflection). These land in `settings.local.json` exactly like any other
  divergence, so when you run `migrate_permissions --dry-run`, scan the newly accumulated
  allows specifically and drop any you did not mean to grant before folding the rest in.
- **Comment your rules to record intent.** TOML supports comments -- use them to note *why* a
  rule exists (and when it was added), especially for `[regex]` patterns and `[hard_deny]`
  entries whose purpose is not obvious from the pattern alone. A rule whose reason has been
  forgotten tends to get either blindly kept or wrongly removed; a one-line comment prevents
  both and makes review faster.
- **Keep the config in version control and review the diffs.** Commit `toolguard_hook.toml`
  (and any ancestor-level configs) to git and review changes as diffs -- an over-broad or
  stray rule is far easier to catch in a diff than in a full file. Caveats: `settings.local.json`
  is typically git-ignored and machine-local, and you should never commit secrets or anything
  under `~/.claude` into a project repository.
- **Practice defense in depth -- do not rely on the absence of an allow.** Add explicit `deny`
  (or [`[hard_deny]`](configuration.md#configuration-reference)) rules for destructive
  operations even when you are allow-listing, so a future broad allow, a mistaken "always
  allow," or a parsing gap cannot silently expose them. See
  [Recommended deny patterns](#recommended-deny-patterns) for a starting set.
- **Use the `ask` tier for impactful-but-reversible operations.** Reserve `allow` for routine,
  safe commands and `deny`/`[hard_deny]` for the clearly dangerous; put the in-between
  (database migrations, `cp`/`mv`, network calls, package installs) in `ask` so you stay in the
  loop without blocking the workflow. The `ask` list is easy to overlook -- it is often the
  right home for a rule you are tempted to either fully allow or fully deny.

## Recommended deny patterns

**Always include these in your deny list**:

```toml
[permissions]
deny = [
    # Destructive commands
    "Bash(rm -rf:*)",
    "Bash([regex]rm\\s+-rf\\s+/)",
    "Bash(dd:*)",

    # Privilege escalation
    "Bash(sudo:*)",
    "Bash(su:*)",

    # Sensitive files
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.aws/**)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.aws/**)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)",

    # System directories
    "Write(/etc/**)",
    "Write(/usr/**)",
    "Write(/bin/**)",
    "Write(/sbin/**)"
]
```

For the strongest protection, mirror the most critical of these into
[`[hard_deny]`](configuration.md#configuration-reference) at the user level so no project can
weaken them.
