# Toolguard

A pre-tool-use hook for Claude Code that provides comprehensive permission checking for bash commands, file operations, and other tools. Supports multiple tool types, extended pattern syntax, and detailed logging.

## Motivation

Toolguard is a drop-in replacement for the native Claude code permissions system for Bash, Read, Write, and Edit tools. It is backwards compatible (as of January 2026), and has extended capabilities, and better coverage and safety. It also addresses some of the bugs that have existed for a while in the native system, which have not been fixed as of this writing.

### Goals of Toolguard

- **Unified configuration**: Single permission system for multiple tools (Bash, JetBrains terminal, etc.)
- **Compound command security**: Parse and validate each sub-command separately
- **Extended pattern types**: Support regex, glob with globstar, and Claude Code 2.10 native syntax
- **Path normalization**: Consistent, documented normalization of paths in commands and patterns
- **Better logging**: Comprehensive audit trail of all command decisions

---

## How-To Guide

### Configuration

Toolguard requires configuration in two places:
1. **Hook matchers** in Claude Code settings - tells Claude which tools trigger the hook
2. **Governed tools list** in toolguard config - tells toolguard which tools to actually check

Both must be configured for each tool you want to govern.

#### Step 1: Register Hook Matchers

Add hook matchers for each tool in `.claude/settings.local.json`. For example:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "mcp__jetbrains__execute_terminal_command",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "mcp__local-tools__checked_bash",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "/path/to/project/toolguard/hook.py" }
        ]
      }
    ]
  }
}
```

**Important**: Replace `/path/to/project/toolguard/hook.py` with the absolute path to your hook.py file.

#### Step 2: Configure Governed Tools

Create `.claude/toolguard_hook.toml` (preferred) or `.claude/toolguard_hook.json` with the list of tools to govern.

**TOML format** (recommended):

```toml
governed_tools = [
    "Bash",
    "mcp__jetbrains__execute_terminal_command",
    "Read",
    "Write",
    "Edit"
]
```

**JSON format**:

```json
{
  "governed_tools": [
    "Bash",
    "mcp__jetbrains__execute_terminal_command",
    "Read",
    "Write",
    "Edit"
  ]
}
```

**Note**: If both `.toml` and `.json` files exist, the TOML file takes precedence and a warning is logged.

##### Declaring Additional Supported Tools

Toolguard has a hardcoded list of known supported tools (Bash, Read, Write, Edit, and mcp__jetbrains__execute_terminal_command). If you have custom MCP tools that execute commands and want toolguard to govern them, add them to `additional_supported_tools`:

```toml
additional_supported_tools = [
    "mcp__custom__my_bash_tool",
    "mcp__other__command_runner"
]

governed_tools = [
    "Bash",
    "mcp__custom__my_bash_tool"
]
```

This tells toolguard:
1. These tools are valid and should not generate "unsupported tool" warnings
2. If they're also in `governed_tools`, their commands will be validated

**Why is this needed?** Toolguard validates your configuration at startup and warns about tools that appear in permissions but aren't recognized. Without `additional_supported_tools`, custom MCP tools would trigger warnings.

#### Recommended Tools to Govern

**Command Tools** (execute shell commands):

| Tool | Description | When to Include |
|------|-------------|-----------------|
| `Bash` | Native Claude Code bash tool | Always - this is the primary tool |
| `mcp__jetbrains__execute_terminal_command` | JetBrains IDE terminal | If using JetBrains MCP integration |

Also, check your MCP tool list. **Any tool that can execute bash commands should be included in the list**.

**File Path Tools** (read/write/edit files):

| Tool | Description | When to Include |
|------|-------------|-----------------|
| `Read` | Claude Code file read tool | If you want GLOB pattern control over file reading |
| `Write` | Claude Code file write tool | If you want GLOB pattern control over file writing |
| `Edit` | Claude Code file edit tool | If you want GLOB pattern control over file editing |

**Why govern file path tools?** Claude Code has a [known bug](https://github.com/anthropics/claude-code/issues/16170) where `**` globstar patterns work correctly for `Read` permissions but NOT for `Write` or `Edit`. Toolguard uses Python's `PurePath.full_match()` which correctly implements globstar semantics for all file operations. There are also bugs where the native permissions system sometimes prompts youfor permissions that are already granted in the configuration. This can stop a flow dead in its tracks while you're away from the terminal. Toolguard reclaims your time.

**Note on Subagents**: Subagents use the same tools as the main agent. If a subagent is configured to use a specific tool (e.g., an MCP bash tool), that tool must be in both the hook matchers AND the governed_tools list, or commands will bypass toolguard entirely.

#### Step 3: Configure Permission Patterns

Permission patterns can be configured in two places:

1. **`settings.local.json`** - Standard patterns that Claude Code understands natively
2. **`toolguard_hook.json`** - Extended syntax patterns (`[regex]`, `[glob]`, `[native]`)

**Why separate files?** If you ever need to disable the toolguard hook, patterns in `settings.local.json` will still work with Claude Code's native permission system. Extended syntax patterns in `toolguard_hook.json` are toolguard-specific and won't pollute the native configuration.

##### Standard Patterns (in settings.local.json)

Add permission patterns in the `permissions` section of your Claude settings:

**Command tool patterns** (for Bash and terminal tools):

```json
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",
      "Bash(git log:*)",
      "Bash(git diff:*)",
      "Bash(uv run pytest:*)",
      "Bash(ls -la:*)"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(sudo:*)"
    ]
  }
}
```

All command patterns use the `Bash(...)` prefix regardless of which tool is being governed. This provides a unified permission model across all command-executing tools.

**File path patterns** (for Read, Write, Edit tools):

```json
{
  "permissions": {
    "allow": [
      "Read(~/projects/**)",
      "Read(/tmp/**)",
      "Write(~/projects/myapp/**)",
      "Write(/tmp/**)",
      "Edit(~/projects/myapp/**)"
    ],
    "deny": [
      "Read(**/.env)",
      "Read(**/.env.*)",
      "Read(**/.ssh/**)",
      "Write(**/.env)",
      "Write(**/.ssh/**)"
    ]
  }
}
```

File path patterns use GLOB syntax with proper `**` globstar support. Each tool type (Read, Write, Edit) has its own patterns - a Read pattern does NOT grant Write or Edit access.

##### Extended Patterns (in toolguard_hook.toml or toolguard_hook.json)

For advanced pattern matching, add extended syntax patterns to `.claude/toolguard_hook.toml` (preferred) or `.claude/toolguard_hook.json`.

**TOML format** (recommended - supports comments):

```toml
governed_tools = ["Bash", "mcp__jetbrains__execute_terminal_command"]

[permissions]
# Extended syntax patterns - see Pattern Types section
allow = [
    "[regex]^git (log|diff|status|branch)",
    "[glob]~/projects/**/*.py",
    "[native]docker * --rm *"
]
deny = [
    "[regex]rm\\s+-rf\\s+/",
    "[glob]**/.env*"
]
ask = [
    "Bash(alembic:*)",
    "Bash(uv run alembic:*)"
]
```

**JSON format**:

```json
{
  "governed_tools": ["Bash", "mcp__jetbrains__execute_terminal_command"],
  "permissions": {
    "allow": [
      "[regex]^git (log|diff|status|branch)",
      "[glob]~/projects/**/*.py",
      "[native]docker * --rm *"
    ],
    "deny": [
      "[regex]rm\\s+-rf\\s+/",
      "[glob]**/.env*"
    ]
  }
}
```

Extended pattern types:
- `[regex]` - Regular expression matching with `re.search()`
- `[glob]` - True glob patterns with proper `**` globstar support
- `[native]` - Claude Code 2.10 word-level wildcard matching

See [Pattern Types](#pattern-types) for detailed syntax and examples.

#### Verifying Configuration

After configuration, restart Claude Code and check the logs:
- Commands should appear in `logs/toolguard-YYYY-MM-DD.md`
- If commands aren't logged, verify both hook matcher AND governed_tools include the tool

### Environment Variables

Toolguard can be configured via environment variables. These can be set in your shell, or in a `.env` file in your project root.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TOOLGUARD_LOGGING_ENABLED` | bool | `true` | Enable/disable command logging |
| `TOOLGUARD_LOG_DIR` | path | `{project}/logs` | Directory for log files |
| `TOOLGUARD_EXTENDED_SYNTAX` | bool | `true` | Enable `[regex]`, `[glob]`, `[native]` patterns |
| `TOOLGUARD_PROJECT_ROOT` | path | (auto-detect) | Explicit project root override |
| `TOOLGUARD_SOURCE_ROOT` | path | (empty) | Relative path from project root to source root |
| `TOOLGUARD_CREATE_LOG_DIR` | bool | `false` | Auto-create log directory if missing |

#### Boolean Values

Boolean environment variables accept (case-insensitive):
- **True**: `true`, `yes`, `1`
- **False**: `false`, `no`, `0`

#### Project Root Detection

If `TOOLGUARD_PROJECT_ROOT` is not set, toolguard searches upward from the current directory for:
1. `.git` directory
2. `pyproject.toml` file

The first directory containing either marker is used as the project root.

#### .env File

Toolguard loads environment variables from `.env` at `{project_root}/{source_root}/.env`. Environment variables set in the shell take precedence over `.env` file values.

Example `.env` file:
```bash
TOOLGUARD_LOGGING_ENABLED=true
TOOLGUARD_LOG_DIR=logs
TOOLGUARD_CREATE_LOG_DIR=true
```

#### Error Handling

**Missing log directory**: If the log directory doesn't exist:
- With `TOOLGUARD_CREATE_LOG_DIR=false` (default): Warning printed to stderr, logging disabled, commands still processed
- With `TOOLGUARD_CREATE_LOG_DIR=true`: Directory is created automatically

### Pattern Types

Toolguard supports two categories of pattern matching:

**1. Command Patterns** (for Bash and terminal tools)

| Pattern Type | Prefix | Matching Method | Use Case |
|--------------|--------|-----------------|----------|
| DEFAULT | (none) | fnmatch prefix + path normalization | Standard Claude Code patterns |
| REGEX | `[regex]` | `re.search()` | Complex matching with regex |
| GLOB | `[glob]` | `PurePath.full_match()` | File path patterns with globstar |
| NATIVE | `[native]` | Word-level segment matching | Claude Code 2.10 wildcard style |

**2. File Path Patterns** (for Read, Write, Edit tools)

File path tools use GLOB pattern matching exclusively via `PurePath.full_match()`. This provides proper globstar (`**`) support that Claude Code's native permissions lack for Write/Edit operations.

### Pattern Examples

#### DEFAULT Patterns (Standard)

The default pattern type uses fnmatch with colon syntax for prefix matching:

```
Bash(git status:*)       # git status with any arguments
Bash(cat ./*:*)          # cat files in current directory
Bash(uv run pytest:*)    # pytest with any arguments
Bash(git log:*)          # git log with any arguments
```

The `:*` suffix enables prefix matching - the command must start with the pattern before the colon.

#### REGEX Patterns

Use `[regex]` prefix for regular expression matching with `re.search()`:

```
[regex]^git (log|diff|status)    # git log, diff, or status at start
[regex]npm (install|run)         # npm install or run anywhere
[regex]^curl -s https?://        # curl with -s flag and http(s) URL
[regex]pytest.*-v                # pytest with -v flag anywhere
```

REGEX patterns match anywhere in the command unless anchored with `^` or `$`.

#### GLOB Patterns

Use `[glob]` prefix for true glob matching with proper globstar (`**`) support:

```
[glob]~/projects/**/*.py         # Any .py file under ~/projects (recursive)
[glob]/tmp/*.txt                 # .txt files directly in /tmp only
[glob]/tmp/**/*.txt              # .txt files anywhere under /tmp
[glob]~/projects/*/*.js          # .js files one level deep only
```

**Important**: GLOB patterns properly distinguish `*` from `**`:
- `*` matches any characters **except** path separator `/`
- `**` matches any characters **including** path separators (recursive)

#### NATIVE Patterns

Use `[native]` prefix for Claude Code 2.10 wildcard syntax:

```
[native]git * main               # git checkout main, git merge main, etc.
[native]* install                # npm install, pip install, cargo install
[native]npm *                    # Any npm command
[native]git * origin *           # git push origin main, git pull origin dev
[native]docker * --rm *          # docker run --rm, docker exec --rm, etc.
```

NATIVE patterns use word-level matching where `*` matches any sequence of characters. Segments must appear in order.

#### File Path Patterns (Read, Write, Edit)

File path patterns use GLOB syntax with proper `**` globstar support:

```
Read(~/projects/**)              # Any file under ~/projects (recursive)
Read(/tmp/**)                    # Any file under /tmp (recursive)
Read(/tmp/*)                     # Files directly in /tmp only (not recursive)
Write(~/projects/myapp/**)       # Write to any file in myapp project
Write(/tmp/**/*.log)             # Write to any .log file under /tmp
Edit(~/projects/**/src/*.py)     # Edit .py files in any src directory
```

**Key differences between `*` and `**`**:

| Pattern | Matches | Does NOT Match |
|---------|---------|----------------|
| `/tmp/*` | `/tmp/file.txt` | `/tmp/subdir/file.txt` |
| `/tmp/**` | `/tmp/file.txt`, `/tmp/subdir/file.txt`, `/tmp/a/b/c/d.txt` | `/var/tmp/file.txt` |
| `/tmp/**/*.txt` | `/tmp/file.txt`, `/tmp/subdir/file.txt` | `/tmp/file.log` |

**Deny patterns take precedence**:

```json
{
  "permissions": {
    "allow": ["Read(~/projects/**)"],
    "deny": ["Read(**/.env)", "Read(**/.env.*)"]
  }
}
```

With the above config, toolguard allows reading any file under `~/projects/` EXCEPT `.env` files anywhere in the path.

**Tilde expansion**: Both patterns and file paths support tilde (`~`) expansion. The pattern `Read(~/projects/**)` will match `/Users/username/projects/file.txt`.

### Path Normalization

Toolguard normalizes paths for consistent matching:

| Normalization | Example |
|---------------|---------|
| Tilde conversion | `/Users/arnon/projects` → `~/projects` |
| Symlink resolution | Up to 3 iterations to prevent loops |
| Leading slashes | `//tmp` → `/tmp` |
| Relative paths | `file.txt` → `./file.txt` |

**Normalization by pattern type**:

| Pattern Type | Pattern Normalization | Command Normalization |
|--------------|----------------------|----------------------|
| DEFAULT | Full | Full |
| GLOB | Tilde expansion only | Tilde expansion only |
| REGEX | None | None |
| NATIVE | None | None |

### Compound Commands

Toolguard properly handles compound commands with shell operators:

**Supported operators**: `&&`, `||`, `;`, `|`, `&`

| Operator | Name | Description |
|----------|------|-------------|
| `&&` | AND | Run second command only if first succeeds |
| `\|\|` | OR | Run second command only if first fails |
| `;` | Semicolon | Run commands sequentially |
| `\|` | Pipe | Connect stdout of first to stdin of second |
| `&` | Background | Run command in background |

**Behavior**:
1. Command is parsed and split into sub-commands
2. Each sub-command is validated separately
3. Strictest response wins:
   - If ANY sub-command is denied → whole command denied
   - Otherwise if ANY sub-command requires "ask" → whole command asks
   - Otherwise all allowed → whole command allowed

**Example**:
```bash
git status && rm -rf /    # DENIED - rm -rf is blocked even though git status is allowed
ls -la | grep foo         # Both parts must be allowed
sleep 10 &                # Background command - sleep is validated
```

#### Command Substitution Support

Toolguard extracts and validates commands inside substitutions:

| Construct | Example | Status |
|-----------|---------|--------|
| Command substitution | `$(rm -rf /)` | ✅ Inner command extracted and validated |
| Backtick substitution | `` `rm -rf /` `` | ✅ Inner command extracted and validated |
| Subshells | `(cd /tmp && rm -rf *)` | ✅ Inner commands extracted and validated |
| Brace groups | `{ cmd1; cmd2; }` | ✅ Inner commands extracted and validated |

**Nested constructs** are supported up to 5 levels deep:
```bash
echo $(cat $(find . -name '*.txt'))
# All three commands validated: echo, cat, find

(cd /tmp && rm -rf *)
# Both commands validated: cd, rm -rf (denied)
```

#### Current Limitations

The following bash constructs are **not currently parsed** - their inner commands are treated as opaque:

| Construct | Example | Status |
|-----------|---------|--------|
| Process substitution | `<(cmd)` or `>(cmd)` | ⚠️ Inner command not validated |
| Control structures | `if/for/while/case` | ⚠️ Body commands not validated |

**Note**: Analysis of historical command logs shows Claude Code rarely generates shell control structures at the start of commands. When `if/for/while` appear, they are typically inside Python one-liners or awk scripts where they are treated as string arguments rather than shell parsing constructs. This makes the risk of bypassing toolguard via control structures very low in practice.

**Mitigation**: Use deny patterns that match dangerous commands even when nested:
```json
{
  "deny": [
    "[regex]rm\\s+-rf",
    "[regex]rm\\s+.*-rf"
  ]
}
```

### Takeover Mode (Alpha)

**Takeover Mode** is an advanced configuration that allows Claude Code to receive blanket permissions while toolguard acts as the real security gatekeeper. This eliminates permission prompts during Claude Code operation while maintaining full security control.

#### What is Takeover Mode?

In takeover mode:
1. **Claude Code sees blanket allows** - No permission prompts interrupt workflow
2. **Toolguard enforces real permissions** - All commands/file operations are validated by toolguard's rules
3. **Best of both worlds** - Uninterrupted workflow with full security control

#### When to Use Takeover Mode

**Use takeover mode when:**
- You want Claude to work without permission interruptions
- You trust toolguard's permission system to enforce security
- You have well-defined allow/deny patterns in toolguard configuration
- You want consistent permission enforcement across all tools

**Don't use takeover mode when:**
- You're still configuring and testing permissions
- You prefer explicit Claude Code permission prompts as a second layer
- You're in a high-security environment requiring multi-layer validation

#### How It Works

Takeover mode operates by creating a split configuration:

1. **In `.claude/settings.local.json`**: Add blanket allow patterns that Claude Code sees:
   ```json
   {
     "permissions": {
       "allow": [
         "Bash(*)",
         "Read(*)",
         "Write(*)",
         "Edit(*)"
       ]
     }
   }
   ```

2. **In `.claude/toolguard_hook.toml`**: Define real permissions that toolguard enforces:
   ```toml
   [takeover_mode]
   enabled = true

   [permissions]
   allow = [
       "Bash(git status:*)",
       "Bash(git log:*)",
       "Read(~/projects/**)",
       "Write(~/projects/myapp/**)"
   ]
   deny = [
       "Bash(rm -rf:*)",
       "Read(**/.env)",
       "Write(**/.ssh/**)"
   ]
   ```

When `takeover_mode.enabled = true`, toolguard filters out blanket allow patterns (like `Bash(*)`) from its configuration to prevent them from bypassing the real permissions you've defined.

#### Configuration Options

```toml
[takeover_mode]
# Enable takeover mode (default: false)
enabled = false

# Patterns to ignore from settings.local.json (default list shown)
ignored_allow_patterns = [
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)"
]

# Add custom patterns to ignore list (beyond defaults)
additional_ignored_patterns = []

# What to do when no allow pattern matches (default: "deny")
# Options: "deny" or "ask"
no_match_fallback = "deny"
```

**Example with custom patterns**:
```toml
[takeover_mode]
enabled = true
additional_ignored_patterns = [
    "Bash(~/projects/**)",  # Ignore overly broad project access
]
no_match_fallback = "ask"  # Prompt instead of deny on no match
```

#### Security Warnings

**⚠️ CRITICAL**: If toolguard fails to run (e.g., Python error, missing dependencies), Claude Code will see only the blanket allow patterns and execute ANY command without restriction.

**To mitigate this risk**:
1. **Test thoroughly** before enabling takeover mode
2. **Monitor logs** regularly at `logs/toolguard-YYYY-MM-DD.md`
3. **Check error logs** at `logs/toolguard-error-YYYY-MM-DD.md`
4. **Start with `no_match_fallback = "ask"`** until you're confident in your patterns
5. **Use deny patterns** for critical resources (e.g., `**/.env`, `**/.ssh/**`)

**Verify toolguard is running**:
```bash
# Commands should appear in daily logs
tail -f logs/toolguard-$(date +%Y-%m-%d).md
```

If no logs appear after Claude Code executes commands, toolguard is NOT running and blanket allows are exposed.

#### Example Configuration

Complete takeover mode setup:

**`.claude/settings.local.json`** (blanket allows for Claude Code):
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/hook.py" }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/hook.py" }
        ]
      }
    ]
  },
  "permissions": {
    "allow": [
      "Bash(*)",
      "Read(*)",
      "Write(*)",
      "Edit(*)"
    ]
  }
}
```

**`.claude/toolguard_hook.toml`** (real permissions for toolguard):
```toml
governed_tools = ["Bash", "Read", "Write", "Edit"]

[takeover_mode]
enabled = true
no_match_fallback = "deny"

[permissions]
allow = [
    # Git operations
    "Bash(git status:*)",
    "Bash(git log:*)",
    "Bash(git diff:*)",
    "Bash(git branch:*)",

    # Testing
    "Bash(uv run pytest:*)",

    # File access
    "Read(~/projects/**)",
    "Write(~/projects/myapp/**)",
    "Edit(~/projects/myapp/**)"
]

deny = [
    # Dangerous commands
    "Bash(rm -rf:*)",
    "Bash(sudo:*)",
    "[regex]rm\\s+-rf\\s+/",

    # Sensitive files
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)"
]
```

### Configuration Sync & Migration

As you work with toolguard, permissions may accumulate in `settings.local.json` that would be better managed in `toolguard_hook.toml`. Toolguard provides tools to detect and migrate these permissions automatically.

#### What is Config Divergence?

**Config divergence** occurs when:
- Permissions exist in `settings.local.json` but not in `toolguard_hook.toml`
- You're managing permissions in two places, making maintenance harder
- Extended syntax patterns (`[regex]`, `[glob]`) can't be used because they're in the wrong file

#### Why It Matters

1. **Maintainability**: Single source of truth for permissions
2. **Extended features**: Use advanced patterns only available in `toolguard_hook.toml`
3. **Clarity**: Separation between Claude Code's view (blanket allows) and real permissions
4. **Takeover mode**: Essential for clean takeover mode configuration

#### Manual Migration

Toolguard includes a migration script to detect and migrate permissions:

**Dry run** (see what would change):
```bash
uv run python -m toolguard.scripts.migrate_permissions --dry-run
```

**Execute migration**:
```bash
uv run python -m toolguard.scripts.migrate_permissions
```

**What the migration does**:
1. Scans `settings.local.json` for Bash/Read/Write/Edit permissions
2. Identifies patterns not present in `toolguard_hook.toml`
3. Adds missing patterns to `toolguard_hook.toml`
4. Creates backup before making changes
5. Optionally sorts patterns for readability

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
✓ Migration complete
```

#### Auto-Migration

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
- You're actively developing permission patterns
- You want new patterns automatically moved to `toolguard_hook.toml`
- You trust the migration logic (test with dry-run first)

**When to disable auto-migration**:
- You prefer manual control over migrations
- You're in production with stable permissions
- You want to review changes before applying them

#### Backup Handling

**Backup location**: `logs/config-backups/` (configurable via `backup_dir`)

**Backup naming**: `toolguard_hook-YYYY-MM-DD-HHMMSS.toml`

**Example**:
```
logs/config-backups/
├── toolguard_hook-2026-02-05-140523.toml
├── toolguard_hook-2026-02-04-093012.toml
└── toolguard_hook-2026-02-03-151445.toml
```

**Restoring from backup**:
```bash
# Copy backup to main config
cp logs/config-backups/toolguard_hook-2026-02-05-140523.toml .claude/toolguard_hook.toml
```

**Backup retention**: Toolguard does not automatically delete old backups. Clean up manually as needed:
```bash
# Keep only last 10 backups
cd logs/config-backups
ls -t | tail -n +11 | xargs rm
```

#### Similarity Detection and Duplicate Removal

The migration script automatically identifies and handles redundant patterns using advanced similarity detection.

**Redundant Pattern Removal**:

The migration automatically removes patterns from `settings.local.json` that are:
1. **Exact duplicates** - Pattern exists identically in both files
2. **Subsets** - Pattern is covered by a broader rule in `toolguard_hook.toml`

**Example**:
```
Found 3 pattern(s) to migrate:
  ALLOW:
    - Bash(find:*)
    - Bash(uv run ruff format:*)  ← COVERED BY: Bash(uv run ruff:*)
    - Bash(~/bin/open_note_by_title.sh:*)

Found 2 redundant pattern(s) to remove (already in toolguard config):
  ALLOW:
    - Bash(uv run pytest:*)  (exact duplicate)
    - Bash(git push:*)  (covered by Bash(git:*))
```

**Superset Detection**:

For `:*)` patterns, the migration detects when a broader pattern covers a more specific one:
- `Bash(uv run ruff:*)` covers `Bash(uv run ruff format:*)`
- `Bash(git:*)` covers `Bash(git push:*)`, `Bash(git pull:*)`, etc.
- Only works with simple `:*)` postfix patterns (not extended syntax)
- Requires word boundary (space) to avoid false positives

**Similarity Ranking**:

The migration uses Python's `difflib` to rank similar patterns by similarity score:

```
Similar patterns (top 3 by similarity):
  'Bash(~/bin/open_note_by_title.sh:*)' similar to 'Bash(~/bin/open_note_by_title.sh :*)' (0.97)
  'Bash(uv run ruff format:*)' similar to 'Bash(uv run ruff:*)' (0.85) [SUPERSET]
```

**Configuration**:

Control similarity detection with the `max_similar_matches` setting:

```toml
[config_sync]
# Maximum similar patterns to show (default: 3)
max_similar_matches = 3
```

**Notes**:
- Extended syntax patterns (`[regex]`, `[glob]`, `[native]`) are skipped for superset detection
- If too many patterns share the same prefix, they won't be flagged as similar (not discriminating)
- Similarity uses a 0.7 cutoff threshold to balance precision and recall

### Session Warnings

Toolguard includes a session-based warning system to alert you about configuration issues without flooding your terminal.

#### How Warnings Work

**Warning frequency**:
- **Once per session** (default): Warning appears only once per Claude Code session
- **Once per day**: Warning appears once per calendar day

**Warning persistence**: Warnings are tracked using marker files in `/tmp/toolguard-warnings/`

**Example workflow**:
1. Configuration issue detected (e.g., ungoverned tool in permissions)
2. Warning printed to stderr and logged to `logs/toolguard-error-YYYY-MM-DD.md`
3. Marker file created at `/tmp/toolguard-warnings/<warning-hash>.marker`
4. Subsequent occurrences of same warning are suppressed until marker expires

#### Marker Files Location

**Directory**: `/tmp/toolguard-warnings/`

**Naming**: Each warning type gets a unique hash-based filename:
```
/tmp/toolguard-warnings/
├── a3f2e1d9c8b7a6f5.marker  # Ungoverned tool warning
├── b4e3d2c1f0e9d8c7.marker  # TOML/JSON conflict warning
└── c5d4e3f2a1b0c9d8.marker  # Unsupported tool warning
```

**Content**: Marker files contain the timestamp when the warning was first issued.

#### Marker Cleanup

**Automatic cleanup**: Marker files in `/tmp/` are typically cleared on system reboot

**Manual cleanup** (to see warnings again):
```bash
# Clear all toolguard warning markers
rm -rf /tmp/toolguard-warnings/

# Clear specific warning (find hash in logs/toolguard-error-YYYY-MM-DD.md)
rm /tmp/toolguard-warnings/a3f2e1d9c8b7a6f5.marker
```

**When to clear markers**:
- You've fixed a configuration issue and want to verify it's resolved
- You want to see all warnings again for debugging
- You're testing warning behavior

#### Warning Types

Common warnings that use the session warning system:

| Warning Type | Description |
|--------------|-------------|
| Ungoverned tools | Tools in permissions but not in `governed_tools` list |
| Unsupported tools | Tools not recognized by toolguard |
| TOML/JSON conflict | Both `.toml` and `.json` config files exist |
| Migration available | Patterns in `settings.local.json` can be migrated |

All warnings are logged to `logs/toolguard-error-YYYY-MM-DD.md` regardless of marker status.

### Configuration Reference

Complete TOML configuration structure with all available sections:

```toml
# ============================================================================
# TOOLGUARD CONFIGURATION REFERENCE
# ============================================================================

# List of tools that toolguard will govern (required)
governed_tools = [
    "Bash",
    "Read",
    "Write",
    "Edit",
    "mcp__jetbrains__execute_terminal_command"
]

# Additional custom tools to recognize as valid (optional)
additional_supported_tools = [
    "mcp__custom__my_bash_tool"
]

# ============================================================================
# TAKEOVER MODE - Claude sees blanket allows, toolguard enforces real rules
# ============================================================================
[takeover_mode]
# Enable takeover mode (default: false)
enabled = false

# Blanket patterns to ignore from settings.local.json (these are defaults)
ignored_allow_patterns = [
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)"
]

# Additional patterns to ignore (beyond defaults)
additional_ignored_patterns = []

# Fallback when no pattern matches: "deny" or "ask" (default: "deny")
no_match_fallback = "deny"

# ============================================================================
# CONFIG SYNC - Automatic migration from settings.local.json
# ============================================================================
[config_sync]
# Enable automatic migration on startup (default: false)
auto_migrate = false

# Directory for configuration backups (default: "logs/config-backups")
backup_dir = "logs/config-backups"

# Sort patterns after migration (default: true)
auto_sort_on_migrate = true

# ============================================================================
# PERMISSIONS - Define allow/deny/ask patterns
# ============================================================================
[permissions]
# Allowed patterns - commands/files that are permitted
allow = [
    # Standard patterns (Claude Code compatible)
    "Bash(git status:*)",
    "Bash(git log:*)",
    "Bash(uv run pytest:*)",
    "Read(~/projects/**)",
    "Write(~/projects/myapp/**)",

    # Extended syntax patterns (toolguard only)
    "[regex]^git (status|log|diff|branch)",
    "[glob]~/projects/**/*.py",
    "[native]docker * --rm *"
]

# Denied patterns - explicitly blocked (take precedence over allow)
deny = [
    # Dangerous commands
    "Bash(rm -rf:*)",
    "Bash(sudo:*)",
    "[regex]rm\\s+-rf\\s+/",

    # Sensitive files
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)"
]

# Ask patterns - require explicit user confirmation (optional)
ask = [
    "Bash(alembic:*)",
    "Bash(uv run alembic:*)",
    "Write(~/projects/production-db/**)"
]
```

**Configuration notes**:
- **Comments**: TOML format supports inline comments (not available in JSON)
- **Pattern order**: Patterns within each section (allow/deny/ask) are checked in order
- **Deny precedence**: Deny patterns always take precedence over allow patterns
- **Extended syntax**: Only supported in `toolguard_hook.toml`, not in `settings.local.json`

### Security Best Practices

#### Blanket Allow Risks

**⚠️ Never use blanket allows without toolguard protection**

```json
// DANGEROUS - DO NOT USE unless takeover mode is enabled
{
  "permissions": {
    "allow": ["Bash(*)", "Write(*)"]
  }
}
```

**Why this is dangerous**:
- Claude can execute ANY command or write ANY file
- No protection against mistakes or malicious suggestions
- Bypasses all security controls

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

2. **Takeover mode with toolguard** (blanket allows OK):
   ```toml
   # In settings.local.json: Bash(*), Write(*)
   # In toolguard_hook.toml:
   [takeover_mode]
   enabled = true

   [permissions]
   allow = ["Bash(git status:*)", "Write(~/projects/myapp/**)"]
   deny = ["Bash(rm -rf:*)", "Write(**/.env)"]
   ```

#### Backup Importance

**Always test changes with backups**:

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

   # Migration creates automatic backup, but manual backup doesn't hurt
   cp .claude/toolguard_hook.toml logs/manual-backup-$(date +%Y-%m-%d).toml
   ```

3. **Regular backups**:
   ```bash
   # Weekly backup script
   cp .claude/toolguard_hook.toml ~/backups/toolguard-$(date +%Y-%m-%d).toml
   ```

#### Testing with Dry-Run

**Always test migrations before executing**:

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

#### Monitoring and Verification

**Verify toolguard is working**:

1. **Check logs after commands**:
   ```bash
   tail -20 logs/toolguard-$(date +%Y-%m-%d).md
   ```
   You should see entries for every command Claude executes.

2. **Monitor error logs**:
   ```bash
   tail -f logs/toolguard-error-$(date +%Y-%m-%d).md
   ```
   Watch for warnings about configuration issues.

3. **Test with intentional violation**:
   ```bash
   # If "rm -rf /" is denied, this command should be blocked
   # Try it via Claude Code and verify it's logged as refused
   ```

**Red flags that toolguard is NOT working**:
- No entries in `logs/toolguard-YYYY-MM-DD.md` after Claude executes commands
- Commands execute that should be denied
- No warnings/errors in logs when you expect them

#### Recommended Deny Patterns

**Always include these in your deny list**:

```toml
[permissions]
deny = [
    # Destructive commands
    "Bash(rm -rf:*)",
    "[regex]rm\\s+-rf\\s+/",
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

---

## Technical Architecture

### Package Structure

```
toolguard/
├── __init__.py
├── hook.py              # Main hook entry point (reads stdin, writes stdout)
├── config.py            # Configuration loading and merging
├── config_validation.py # Validates tool permissions at startup
├── toml_config.py       # TOML configuration loader
├── error_log.py         # Warning/error logging to toolguard-error-*.md
├── permissions.py       # Permission checking logic
├── patterns.py          # Pattern type parsing and matching
├── normalization.py     # Path normalization functions
├── compound.py          # Compound command handling
├── log_writer.py        # Command logging to markdown files
├── parser/              # PEG-based bash command parser
│   ├── __init__.py
│   └── bash_parser.py   # Canopy-generated parser
└── test/
    └── unit/            # Comprehensive unit tests
        ├── test_compound.py
        ├── test_config.py
        ├── test_hook.py
        ├── test_logging.py
        ├── test_normalization.py
        ├── test_patterns.py
        ├── test_permissions.py
        └── test_toml_config.py
```

### Hook Flow

```
┌─────────────────┐
│  Claude Code    │
│  PreToolUse     │
└────────┬────────┘
         │ JSON via stdin
         ▼
┌─────────────────┐
│   hook.py       │
│  parse_input()  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Is tool in     │──No──► Allow (not governed)
│  governed list? │
└────────┬────────┘
         │ Yes
         ▼
┌─────────────────────────┐
│  Tool type?             │
└────────┬────────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌───────┐ ┌───────────┐
│ File  │ │ Command   │
│ Path  │ │ Tool      │
│ Tool  │ │(Bash,etc) │
└───┬───┘ └─────┬─────┘
    │           │
    ▼           ▼
┌─────────┐ ┌─────────────┐
│ GLOB    │ │ compound.py │
│ match   │ │ Parse cmd   │
│ via     │ │ into parts  │
│PurePath │ └──────┬──────┘
│.full_   │        │
│ match() │        ▼
└────┬────┘ ┌─────────────┐
     │      │permissions  │
     │      │.py Check    │
     │      │each subcmd  │
     │      └──────┬──────┘
     │             │
     └──────┬──────┘
            ▼
    ┌─────────────────┐
    │  logging.py     │
    │  Log decision   │
    └────────┬────────┘
             │ JSON via stdout
             ▼
    ┌─────────────────┐
    │  Claude Code    │
    │  Execute/Block  │
    └─────────────────┘
```

### Configuration Hierarchy

Toolguard follows Claude Code's configuration hierarchy:

1. **`CLAUDE_SETTINGS_PATH`** environment variable (if set, takes priority)
2. Otherwise, merges from multiple sources in order:
   - Project local: `.claude/toolguard_hook.local.toml` (or `.json`)
   - Project local: `.claude/settings.local.json`
   - Project: `.claude/toolguard_hook.toml` (or `.json`)
   - Project: `.claude/settings.json`
   - User local: `~/.claude/toolguard_hook.local.toml` (or `.json`)
   - User local: `~/.claude/settings.local.json`
   - User: `~/.claude/toolguard_hook.toml` (or `.json`)
   - User: `~/.claude/settings.json`

**TOML precedence**: When both `.toml` and `.json` files exist at the same level (e.g., both `toolguard_hook.toml` and `toolguard_hook.json`), the TOML file takes precedence and a warning is logged.

Extended patterns (`[regex]`, `[glob]`, `[native]`) are only supported in `toolguard_hook.toml` or `toolguard_hook.json` files to avoid polluting native Claude configuration.

### Pattern Matching Implementation

#### Command Tool Patterns

**DEFAULT** (`permissions.py`):
- Uses `fnmatch.fnmatch()` with colon syntax
- Applies full path normalization to both pattern and command
- Handles special path component patterns like `**/.env/**`

**REGEX** (`patterns.py`):
- Uses `re.search()` for flexible matching anywhere in command
- No normalization applied
- Invalid regex patterns treated as non-matching

**GLOB** (`patterns.py`):
- Uses `PurePath.full_match()` (Python 3.13+) for proper globstar
- `*` matches single path level, `**` matches recursively
- Tilde expansion applied to both pattern and command

**NATIVE** (`patterns.py`):
- Splits pattern by `*` into literal segments
- Finds segments in order within command
- Handles leading/trailing wildcards for anchoring

#### File Path Tool Patterns

**Read, Write, Edit** (`hook.py`):
- Uses `PurePath.full_match()` for GLOB matching
- Patterns extracted from settings via `load_file_path_patterns()`
- Pattern syntax: `ToolName(pattern)` e.g., `Read(/tmp/**)`
- Tilde expansion applied to both patterns and file paths
- Deny patterns checked first (take precedence)
- Each tool type has separate patterns (Read pattern ≠ Write permission)

### Logging

All decisions are logged to `logs/toolguard-YYYY-MM-DD.md` with:
- Timestamp
- Operation (command or file path with tool name)
- Decision (allow/deny)
- Matching pattern or reason for denial

Example log entries:
```markdown
## 2025-01-14

| Time | Command | Decision | Notes |
|------|---------|----------|-------|
| 10:15:23 | git status | executed | main |
| 10:15:45 | Read(/tmp/test.txt) | executed | main |
| 10:16:02 | Write(/etc/passwd) | refused | Path does not match any allow patterns |
```

### Error and Warning Logs

Configuration issues and validation warnings are logged to a separate file: `logs/toolguard-error-YYYY-MM-DD.md`

**What gets logged**:
- **WARNING**: Unsupported tools in permissions (tools not in known list or `additional_supported_tools`)
- **WARNING**: Ungoverned tools in permissions (tools in known list but not in `governed_tools`)
- **WARNING**: Both TOML and JSON config files exist at the same level
- **ERROR**: Critical configuration problems

**Example error log entry**:
```markdown
## 2026-01-20 10:30:45 - WARNING

**Message**: Tool "WebSearch" is not a known supported tool

**Corrective Steps**: If "WebSearch" is a valid tool that should be governed, add it to "additional_supported_tools" in your config. Otherwise, remove it from permissions or update the tool name.

---
```

**Note**: Warnings are also printed to stderr, so you'll see them in your terminal when the hook first runs.

---

## Requirements

- Python >= 3.14 (for `PurePath.full_match()` globstar support)
- Claude Code with PreToolUse hook support

## Testing

```bash
# Run all toolguard tests
uv run pytest toolguard/test/unit/ -v

# Run specific test file
uv run pytest toolguard/test/unit/test_patterns.py -v
```

Current test coverage: **375 tests** covering all pattern types, compound commands, command substitution extraction, subshell extraction, brace group extraction, file path permissions, configuration, TOML configuration, config validation, error logging, environment variables, security bypass attempts, parser robustness, and edge cases.
