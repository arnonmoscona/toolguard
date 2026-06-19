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
[conflict and resolution logs](architecture.md#logging). That caution holds **even with
[auto-migration](#auto-migration) enabled** -- automation should speed the mechanical move,
never replace your judgment.

### Why it matters

1. **Maintainability**: a single source of truth for permissions.
2. **Extended features**: use advanced patterns only available in `toolguard_hook.toml`.
3. **Clarity**: separation between Claude Code's view (blanket allows) and the real
   permissions.
4. **Takeover mode**: essential for clean [takeover mode](takeover-mode.md) configuration.

## Manual migration

Toolguard includes a migration script to detect and migrate permissions.

**Dry run** (see what would change):

```bash
uv run python -m toolguard.scripts.migrate_permissions --dry-run
```

**Execute migration**:

```bash
uv run python -m toolguard.scripts.migrate_permissions
```

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

**Configuration**: control similarity detection with the `max_similar_matches` setting:

```toml
[config_sync]
# Maximum similar patterns to show (default: 3)
max_similar_matches = 3
```

**Notes**:

- Extended syntax patterns (`[regex]`, `[glob]`, `[native]`) are skipped for superset
  detection.
- If too many patterns share the same prefix, they are not flagged as similar (not
  discriminating).
- Similarity uses a 0.7 cutoff threshold to balance precision and recall.

## Session warnings

Toolguard includes a session-based warning system to alert you about configuration issues
without flooding your terminal.

### How warnings work

**Warning frequency**:

- **Once per session** (default): the warning appears only once per Claude Code session.
- **Once per day**: the warning appears once per calendar day.

**Warning persistence**: warnings are tracked using marker files in
`/tmp/toolguard-warnings/`.

**Example workflow**:

1. A configuration issue is detected (e.g., an ungoverned tool in permissions).
2. A warning is printed to stderr and logged to `logs/toolguard-warning-YYYY-MM-DD.md`.
3. A marker file is created at `/tmp/toolguard-warnings/<warning-hash>.marker`.
4. Subsequent occurrences of the same warning are suppressed until the marker expires.

### Marker files location

**Directory**: `/tmp/toolguard-warnings/`.

**Naming**: each warning type gets a unique hash-based filename:

```
/tmp/toolguard-warnings/
|-- a3f2e1d9c8b7a6f5.marker  # Ungoverned tool warning
|-- b4e3d2c1f0e9d8c7.marker  # TOML/JSON conflict warning
`-- c5d4e3f2a1b0c9d8.marker  # Unsupported tool warning
```

**Content**: marker files contain the timestamp when the warning was first issued.

### Marker cleanup

**Automatic cleanup**: marker files in `/tmp/` are typically cleared on system reboot.

**Manual cleanup** (to see warnings again):

```bash
# Clear all toolguard warning markers
rm -rf /tmp/toolguard-warnings/

# Clear a specific warning (find the hash in logs/toolguard-warning-YYYY-MM-DD.md)
rm /tmp/toolguard-warnings/a3f2e1d9c8b7a6f5.marker
```

**When to clear markers**:

- You have fixed a configuration issue and want to verify it is resolved.
- You want to see all warnings again for debugging.
- You are testing warning behavior.

### Warning types

Common warnings that use the session warning system:

| Warning type | Description |
|--------------|-------------|
| Ungoverned tools | Tools in permissions but not in the `governed_tools` list |
| Unsupported tools | Tools not recognized by toolguard |
| TOML/JSON conflict | Both `.toml` and `.json` config files exist at one level |
| Migration available | Patterns in `settings.local.json` can be migrated |

All warnings are logged regardless of marker status. See
[Technical Architecture: logging](architecture.md#logging) for how the warning, error, and
conflict streams are separated.
