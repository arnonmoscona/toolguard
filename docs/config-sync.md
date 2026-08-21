# Config Sync & Migration

As you work with toolguard, permissions may accumulate in `settings.local.json` that would
be better managed in `toolguard_hook.toml`. Toolguard provides tools to detect and migrate
these permissions, plus a session-warning system to surface configuration issues without
flooding your terminal.

## What is config divergence?

**Config divergence** occurs when:

- Permissions exist in `settings.local.json` but not in `toolguard_hook.toml`.
- You are managing permissions in two places, making maintenance harder.
- Extended syntax patterns (`[regex]`, `[glob]`) cannot be used because they are in the
  wrong file.

### Divergence is normal -- you cannot prevent it

Divergence is not a misuse of toolguard; it is a natural side effect of using Claude Code.
When Claude hits a command or file operation that resolves to **ask**, you respond with
"Yes, and don't ask again" (or similar), and Claude Code records a new allow rule in its own
`settings.local.json`. Claude Code knows nothing about toolguard, so that rule lands in the
native config rather than your `toolguard_hook.toml` -- and your two sources have drifted.

This happens during ordinary work, repeatedly, and there is **no way to switch it off**: it
is how Claude Code's permission prompts are designed to work. So the goal is not to prevent
divergence but to **manage** it -- periodically fold the accumulated native rules back into
`toolguard_hook.toml`. Toolguard provides tooling for exactly this (detection, dry-run
preview, and migration, described below), with more automation planned over time; you can
also reconcile by hand. Expect to do this occasionally for the life of the project.

Lean on the provided automation to ease this, but remember its purpose is your own security
and policy enforcement, not mere tidiness. As in any security workflow, review what changes
before you trust it: use the dry-run preview, check the backup diff, and watch the
[conflict and resolution logs](architecture-as-built.md#13-logging). That caution holds **even with
[auto-migration](#auto-migration) enabled** -- automation should speed the mechanical move,
never replace your judgment.

### Why it matters

1. **Maintainability**: a single source of truth for permissions.
2. **Extended features**: use advanced patterns only available in `toolguard_hook.toml`.
3. **Clarity**: separation between Claude Code's view (blanket allows) and the real
   permissions.
4. **Takeover mode**: essential for clean [takeover mode](takeover-mode.md) configuration.

## Manual migration

Toolguard includes a migration script to detect and migrate permissions, exposed as the
`toolguard-migrate` console script (installed alongside `toolguard`/`toolguard-audit`/etc. by
`uv tool install`).

**Dry run** (see what would change):

```bash
toolguard-migrate --dry-run
```

**Execute migration**:

```bash
toolguard-migrate
```

**Other flags**:

- `--no-sort` -- skip the auto-sort step (sorting is on by default; see
  [Auto-migration](#auto-migration)'s `auto_sort_on_migrate`, which controls the same
  behavior for automatic runs).
- `--backup-dir DIR` -- write the pre-migration backup somewhere other than the default
  `logs/config-backups/` (overrides `[config_sync] backup_dir` for this one run).

**If you have a local checkout instead of an installed package**, run it as a module from the
repo root: `uv run python -m toolguard.scripts.migrate_permissions --dry-run`. Note this only
works from *inside* a checkout that has toolguard's own source on its path -- after a normal
`uv tool install`, always use `toolguard-migrate` instead, from any project.

**What the migration does**:

1. Scans `settings.local.json` for `Bash`/`Read`/`Write`/`Edit` permissions.
2. Identifies patterns not present in `toolguard_hook.toml`.
3. Adds missing patterns to `toolguard_hook.toml`.
4. Creates a backup before making changes.
5. Optionally sorts patterns for readability.

**Example output**:

```
Found 12 patterns in settings.local.json
Found 8 patterns in toolguard_hook.toml
Identified 4 patterns to migrate:
  - Bash(git push:*)
  - Bash(git pull:*)
  - Read(~/projects/docs/**)
  - Write(/tmp/**)

Creating backup: logs/config-backups/toolguard_hook-2026-02-05-140523.toml
Migrating patterns...
Migration complete
```

## Auto-migration

Enable automatic migration to keep configurations in sync:

```toml
[config_sync]
# Enable automatic migration on hook startup
auto_migrate = false

# Directory for configuration backups
backup_dir = "logs/config-backups"

# Sort patterns alphabetically after migration
auto_sort_on_migrate = true
```

**When to enable auto-migration**:

- You are actively developing permission patterns.
- You want new patterns automatically moved to `toolguard_hook.toml`.
- You trust the migration logic (test with dry-run first).

**When to disable auto-migration**:

- You prefer manual control over migrations.
- You are in production with stable permissions.
- You want to review changes before applying them.

## Backup handling

**Backup location**: `logs/config-backups/` (configurable via `backup_dir`).

**Backup naming**: `toolguard_hook-YYYY-MM-DD-HHMMSS.toml`.

**Example**:

```
logs/config-backups/
|-- toolguard_hook-2026-02-05-140523.toml
|-- toolguard_hook-2026-02-04-093012.toml
`-- toolguard_hook-2026-02-03-151445.toml
```

**Restoring from backup**:

```bash
# Copy backup to main config
cp logs/config-backups/toolguard_hook-2026-02-05-140523.toml .claude/toolguard_hook.toml
```

**Backup retention**: Toolguard does not automatically delete old backups. Clean up manually
as needed:

```bash
# Keep only last 10 backups
cd logs/config-backups
ls -t | tail -n +11 | xargs rm
```

## Similarity detection and duplicate removal

The migration script automatically identifies and handles redundant patterns using
similarity detection.

**Redundant pattern removal**: the migration automatically removes patterns from
`settings.local.json` that are:

1. **Exact duplicates** -- the pattern exists identically in both files.
2. **Subsets** -- the pattern is covered by a broader rule in `toolguard_hook.toml`.

**Example**:

```
Found 3 pattern(s) to migrate:
  ALLOW:
    - Bash(find:*)
    - Bash(uv run ruff format:*)  <- COVERED BY: Bash(uv run ruff:*)
    - Bash(~/bin/open_note_by_title.sh:*)

Found 2 redundant pattern(s) to remove (already in toolguard config):
  ALLOW:
    - Bash(uv run pytest:*)  (exact duplicate)
    - Bash(git push:*)  (covered by Bash(git:*))
```

**Superset detection**: for `:*)` patterns, the migration detects when a broader pattern
covers a more specific one:

- `Bash(uv run ruff:*)` covers `Bash(uv run ruff format:*)`
- `Bash(git:*)` covers `Bash(git push:*)`, `Bash(git pull:*)`, etc.
- Only works with simple `:*)` postfix patterns (not extended syntax).
- Requires a word boundary (space) to avoid false positives.

**Similarity ranking**: the migration uses Python's `difflib` to rank similar patterns by
similarity score:

```
Similar patterns (top 3 by similarity):
  'Bash(~/bin/open_note_by_title.sh:*)' similar to 'Bash(~/bin/open_note_by_title.sh :*)' (0.97)
  'Bash(uv run ruff format:*)' similar to 'Bash(uv run ruff:*)' (0.85) [SUPERSET]
```

**Notes**:

- Extended syntax patterns (`[regex]`, `[glob]`, `[native]`) are skipped for superset
  detection.
- If too many patterns share the same prefix, they are not flagged as similar (not
  discriminating).
- Similarity uses a 0.7 cutoff threshold to balance precision and recall.
- Up to 3 similar matches are shown per pattern. This is currently a fixed constant, not a
  `toolguard_hook.toml` setting -- there is no `[config_sync]` key that controls it.

## Warning throttling

Configuration warnings go to stderr and to `logs/toolguard-warning-YYYY-MM-DD.md`. Most are not throttled: they are re-emitted on every hook invocation until you fix the config that causes them.

| Warning | Throttling |
|---------|------------|
| Ungoverned tools -- in permissions but not in `governed_tools` | none; every invocation |
| Unsupported tools -- not recognized by toolguard | none; every invocation |
| TOML/JSON conflict -- both `.toml` and `.json` at one level | none; every invocation |
| Takeover mode is active | none; every invocation, deliberately |
| Migration available -- patterns in `settings.local.json` have diverged | once per calendar day, per project |
| Automatic migration (`auto_migrate`) | once per calendar day, per project |

The two throttled items claim a slot in `~/.toolguard/once_per.db`. A calendar day is the only period available, and there is no per-session throttle: the hook is a fresh process for every tool call, so it has no session to scope one to.

All warnings are logged regardless of throttling. See
[Architecture, as built: logging](architecture-as-built.md#13-logging) for how the warning, error, and
conflict streams are separated.
