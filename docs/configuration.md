# Configuration

This is the full configuration reference. For the shortest working setup, start with the
[Quick Start](quickstart.md); for pattern syntax details see the
[Permission Patterns](permission-patterns.md).

Toolguard requires configuration in two places:

1. **Hook matchers** in Claude Code settings -- tells Claude which tools trigger the hook.
2. **Governed tools list** in toolguard config -- tells toolguard which tools to actually check.

Both must be configured for each tool you want to govern.

## Step 1: Register hook matchers

Add hook matchers for each tool in `.claude/settings.local.json`. For example:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "~/.local/bin/toolguard" }
        ]
      },
      {
        "matcher": "mcp__jetbrains__execute_terminal_command",
        "hooks": [
          { "type": "command", "command": "~/.local/bin/toolguard" }
        ]
      },
      {
        "matcher": "Read",
        "hooks": [
          { "type": "command", "command": "~/.local/bin/toolguard" }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          { "type": "command", "command": "~/.local/bin/toolguard" }
        ]
      },
      {
        "matcher": "Edit",
        "hooks": [
          { "type": "command", "command": "~/.local/bin/toolguard" }
        ]
      }
    ]
  }
}
```

**Important**: The `command` shown here is the `toolguard` entry point installed by
`uv tool install` (`~/.local/bin/toolguard` by default -- confirm with `uv tool dir --bin`).
If your environment does not expand `~` in hook commands, use the absolute path. Also add a
`SessionStart` hook pointing at `~/.local/bin/toolguard-session-start` (the conflict-alert
hook). For an editable install the same entry points live in the project's virtualenv
(`<checkout>/.venv/bin/toolguard` and `<checkout>/.venv/bin/toolguard-session-start`). See
[Agent Guides: install and register toolguard from scratch](agent-guides.md#recipe-install-and-register-toolguard-from-scratch)
for both styles and the [README installation notes](../README.md#installation).

## Step 2: Configure governed tools

Create `.claude/toolguard_hook.toml` (preferred) or `.claude/toolguard_hook.json` with the
list of tools to govern.

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

**Note**: If both `.toml` and `.json` files exist at the same level, the TOML file takes
precedence and a warning is logged.

### Declaring additional supported tools

Toolguard has a hardcoded list of known supported tools (`Bash`, `Read`, `Write`, `Edit`,
and `mcp__jetbrains__execute_terminal_command`). If you have custom MCP tools that execute
commands and want toolguard to govern them, add them to `additional_supported_tools`:

```toml
# Custom command tools follow the mcp__<server>__<tool> naming -- run /mcp in
# Claude Code to find the exact name. Declaring a tool here only makes toolguard
# RECOGNIZE it; governing it is a separate step (governed_tools, below).
additional_supported_tools = [
    "mcp__your_terminal_server__run_command"
]

# Minimal, for illustration -- in a real config list every tool you govern.
governed_tools = [
    "Bash"
]
```

**Recognition vs. governance** -- these are two separate things, and it helps to keep them
apart:

- **Recognition** means toolguard treats a tool name as valid. The built-in tools (`Bash`,
  `Read`, `Write`, `Edit`, `mcp__jetbrains__execute_terminal_command`) are recognized
  automatically; a custom MCP tool is recognized only once you list it in
  `additional_supported_tools`.
- **Governance** means toolguard actually checks that tool's calls. A tool is governed only
  when it is **both** registered as a hook matcher (in your Claude Code settings) **and**
  listed in `governed_tools` (see [Recommended tools to govern](#recommended-tools-to-govern)).

Recognition alone does **not** govern a tool -- it only makes the name valid. Always pair the
two: a custom tool you put in `governed_tools` should also be in `additional_supported_tools`.
If you govern a custom tool without recognizing it, toolguard still enforces it, but its
permission patterns raise an "unsupported tool" warning at startup -- so recognition is what
keeps a governed custom tool's configuration clean.

**Why the warning?** At startup toolguard validates your configuration and warns about any
tool that appears in your permission patterns but is not recognized. Listing a custom MCP
tool in `additional_supported_tools` silences that warning; the built-in tools are recognized
automatically and never need it.

### Recommended tools to govern

**Command tools** (execute shell commands):

| Tool | Description | When to include |
|------|-------------|-----------------|
| `Bash` | Native Claude Code bash tool | Always -- this is the primary tool |
| `mcp__jetbrains__execute_terminal_command` | JetBrains IDE terminal | If using JetBrains MCP integration |

Also check your MCP tool list. **Any tool that can execute bash commands should be
included.**

**File path tools** (read/write/edit files):

| Tool | Description | When to include |
|------|-------------|-----------------|
| `Read` | Claude Code file read tool | For GLOB pattern control over file reading |
| `Write` | Claude Code file write tool | For GLOB pattern control over file writing |
| `Edit` | Claude Code file edit tool | For GLOB pattern control over file editing |

**Why govern file path tools?** Claude Code has a
[known bug](https://github.com/anthropics/claude-code/issues/16170) where `**` globstar
patterns work for `Read` permissions but NOT for `Write` or `Edit`. Toolguard uses Python's
`PurePath.full_match()`, which implements globstar correctly for all file operations. The
native system also sometimes re-prompts for permissions already granted, stalling an
unattended session; toolguard reclaims that time.

**Note on subagents**: Subagents use the same tools as the main agent. If a subagent uses a
specific tool (e.g., an MCP bash tool), that tool must be in both the hook matchers AND
`governed_tools`, or its commands bypass toolguard entirely.

> **Known limitation -- subagent identification is currently broken (until further notice).**
> Toolguard attempts to attribute each command to the issuing agent (main vs. a specific
> subagent) for **logging** purposes by parsing the Claude Code transcript. This was always a
> best-effort workaround (Claude Code exposes no reliable way to identify subagent identity),
> and recent Claude Code versions changed the transcript format and broke it. The impact is
> **logging only** -- the agent attribution shown in logs may be wrong or absent. It does
> **not** affect permission decisions: allow/deny/hard_deny resolution never depends on
> subagent identity. This will be revisited in a future release.

## Step 3: Configure permission patterns

Permission patterns can be configured in two places:

1. **`settings.local.json`** -- standard patterns that Claude Code understands natively.
2. **`toolguard_hook.toml` / `toolguard_hook.json`** -- extended syntax patterns
   (`[regex]`, `[glob]`, `[native]`).

**Why separate files?** If you ever need to disable the toolguard hook, patterns in
`settings.local.json` still work with Claude Code's native permission system. Extended
syntax patterns are toolguard-specific and would pollute the native configuration.

**Multi-line commands, heredocs, and control structures** are decomposed and validated
statement-by-statement, and constructs that cannot be safely decomposed resolve to *ask*
(never a silent allow). This also introduces the `__HEREDOC_TO_<sink>__` matchable sentinel
for heredocs. See
[Permission Patterns: compound and multi-line commands](permission-patterns.md#compound-and-multi-line-commands)
before writing rules that involve heredocs, `bash -c`, or `python -c`-style inline code.

### Standard patterns (in settings.local.json)

Add permission patterns in the `permissions` section of your Claude settings.

**Command tool patterns** (for `Bash` and terminal tools):

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

All command patterns use the `Bash(...)` prefix regardless of which tool is being governed.
This provides a unified permission model across all command-executing tools.

**File path patterns** (for `Read`, `Write`, `Edit` tools):

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

File path patterns use GLOB syntax with proper `**` globstar support. Each tool type
(`Read`, `Write`, `Edit`) has its own patterns -- a `Read` pattern does NOT grant `Write`
or `Edit` access.

### Extended patterns (in toolguard_hook.toml or toolguard_hook.json)

For advanced pattern matching, add extended syntax patterns to
`.claude/toolguard_hook.toml` (preferred) or `.claude/toolguard_hook.json`.

**Important:** Extended-syntax prefixes (`[regex]`, `[glob]`, `[native]`) must appear
**inside** the tool wrapper, e.g. `Bash([regex]...)`, `Write([glob]...)`, `Read([regex]...)`.
Bare patterns without a tool wrapper (e.g. `"[regex]^git.*"`) are ignored by the config
loader -- every permission rule must identify which tool it governs.

**TOML format** (recommended -- supports comments):

```toml
governed_tools = ["Bash", "mcp__jetbrains__execute_terminal_command", "Write", "Read"]

[permissions]
# Extended syntax patterns -- prefix lives inside the tool wrapper
allow = [
    "Bash([regex]^git (log|diff|status|branch))",
    "Bash([glob]~/projects/**/*.py)",
    "Bash([native]docker * --rm *)",
    "Write([regex]^/Users/[^/]+/\\.claude/projects/.*/memory/.*\\.md$)",
    "Read([glob]~/projects/**)"
]
deny = [
    "Bash([regex]rm\\s+-rf\\s+/)",
    "Write([glob]**/.env*)"
]
ask = [
    "Bash(alembic:*)",
    "Bash(uv run alembic:*)"
]
```

**JSON format**:

```json
{
  "governed_tools": ["Bash", "mcp__jetbrains__execute_terminal_command", "Write", "Read"],
  "permissions": {
    "allow": [
      "Bash([regex]^git (log|diff|status|branch))",
      "Bash([glob]~/projects/**/*.py)",
      "Bash([native]docker * --rm *)",
      "Write([regex]^/Users/[^/]+/\\.claude/projects/.*/memory/.*\\.md$)",
      "Read([glob]~/projects/**)"
    ],
    "deny": [
      "Bash([regex]rm\\s+-rf\\s+/)",
      "Write([glob]**/.env*)"
    ]
  }
}
```

Extended pattern types:

- `[regex]` -- regular expression matching with `re.search()`
- `[glob]` -- true glob patterns with proper `**` globstar support
- `[native]` -- Claude Code 2.10 word-level wildcard matching

All three prefixes work for both command tools (`Bash(...)`,
`mcp__jetbrains__execute_terminal_command(...)`) and file-path tools (`Read(...)`,
`Write(...)`, `Edit(...)`). See [Permission Patterns](permission-patterns.md) for detailed syntax
and examples.

## No-match fallback

`no_match_fallback` controls what happens when a **governed tool has rules, but a specific
command or path matches none of them.** (A governed tool with no rules at all always
resolves to `ask`, regardless of this setting.)

Set it as a **top-level** key in `toolguard_hook.toml` -- not nested inside `[takeover_mode]`
or any other section:

```toml
no_match_fallback = "ask"   # "ask" (default) | "deny" | "allow_with_warning"
```

Recognized values:

- `"ask"` -- prompt, the same as Claude Code's own default. **This is the default** if the
  key is unset anywhere in the hierarchy.
- `"deny"` -- fail-closed; block anything that doesn't match an explicit rule.
- `"allow_with_warning"` -- allow the command but log a warning (`"warn_deny"` is a
  deprecated alias for this value, still accepted). See
  [Auto-mode with toolguard](auto-mode.md) for the one case this is actually recommended
  for -- it is not a general recommendation.

An unrecognized value (a typo, or anything outside the three above) is never propagated as
configuration -- it silently resolves to the default `"ask"` rather than breaking config
loading.

**Resolution**: more-specific-wins across the
[configuration hierarchy](#configuration-hierarchy) -- the first level (most specific) that
sets the top-level key wins. This applies in **both** takeover and non-takeover modes; it is
not gated on `takeover_mode.enabled`.

**Legacy alias**: `[takeover_mode].no_match_fallback` (nested inside the takeover-mode
section) is an older form of the same setting, still accepted for backwards compatibility.
It is honored **only when no level sets the top-level key anywhere**. If both the top-level
key and the nested alias are set at any level, **the top-level key wins outright**,
regardless of which one is more specific. Write new configs with the top-level key.

*(Current caveat: `toolguard-install enable-takeover` -- the subcommand the guided install
runbook uses to enable takeover mode -- currently writes the nested `[takeover_mode]` form,
not the preferred top-level key. It still works correctly via the legacy-alias path
described above; this is noted here for accuracy, not as something you need to work around.)*

## Verifying configuration

After configuration, restart Claude Code and check the logs:

- Commands should appear in `logs/toolguard-YYYY-MM-DD.md`.
- If commands are not logged, verify both the hook matcher AND `governed_tools` include the
  tool.

## Environment variables

Toolguard can be configured via environment variables. These can be set in your shell, or
in a `.env` file in your project root.

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TOOLGUARD_LOGGING_ENABLED` | bool | `true` | Enable/disable command logging |
| `TOOLGUARD_LOG_DIR` | path | `{project}/logs` | Directory for log files |
| `TOOLGUARD_EXTENDED_SYNTAX` | bool | `true` | Enable `[regex]`, `[glob]`, `[native]` patterns |
| `TOOLGUARD_PROJECT_ROOT` | path | (auto-detect) | Explicit project root override |
| `TOOLGUARD_SOURCE_ROOT` | path | (empty) | Relative path from project root to source root |
| `TOOLGUARD_CREATE_LOG_DIR` | bool | `false` | Auto-create log directory if missing |
| `CLAUDE_SETTINGS_PATH` | path | (unset) | Forces single-file mode against the named settings file, bypassing the config hierarchy (see [the hierarchy section](#configuration-hierarchy)) |
| `XDG_CONFIG_HOME` | path | `~/.config` | Base directory for the optional split rules directory -- see [Split user-level rules directory](#configuration-hierarchy) below |

### Boolean values

Boolean environment variables accept (case-insensitive):

- **True**: `true`, `yes`, `1`
- **False**: `false`, `no`, `0`

### Project root detection

If `TOOLGUARD_PROJECT_ROOT` is not set, toolguard searches upward from the current
directory for:

1. a `.git` directory
2. a `pyproject.toml` file

The first directory containing either marker is used as the project root.

### .env file

Toolguard loads environment variables from `.env` at `{project_root}/{source_root}/.env`.
Environment variables set in the shell take precedence over `.env` file values.

Example `.env` file:

```bash
TOOLGUARD_LOGGING_ENABLED=true
TOOLGUARD_LOG_DIR=logs
TOOLGUARD_CREATE_LOG_DIR=true
```

### Error handling

**Missing log directory**: If the log directory does not exist:

- With `TOOLGUARD_CREATE_LOG_DIR=false` (default): warning printed to stderr, logging
  disabled, commands still processed.
- With `TOOLGUARD_CREATE_LOG_DIR=true`: directory is created automatically.

## Configuration hierarchy

Toolguard discovers configuration across a directory hierarchy: it walks from the project
root up to your home directory, collecting `.claude/` configs at each level. The
`~/.claude/` (user) level is always included as the least-specific level.

Conflicts resolve by **more-specific level wins**: the project level overrides an ancestor
directory, which overrides the user level. Within a single level, `deny` takes precedence
over `allow`, and the first level (most specific) that produces any match decides -- pattern
precision does not cross levels. Set `hierarchical_configuration = false` in the project's
`toolguard_hook.toml` to limit discovery to the project and user levels only. (The toggle is
read only from the project-level config; an ancestor cannot vote on whether ancestors are
read.)

Within each level, sources are consulted highest-priority first:

- `.claude/toolguard_hook.local.toml` (or `.json`)
- `.claude/settings.local.json`
- `.claude/toolguard_hook.toml` (or `.json`)
- `.claude/settings.json`

Relative paths in configuration (for example a relative `backup_dir` or a relative
`Read`/`Write`/`Edit` path pattern) always resolve against the **project root**, regardless
of which level declared them. Absolute and `~` paths are unaffected, and `[regex]` patterns
are never rewritten.

**TOML precedence**: When both `.toml` and `.json` files exist at the same level (e.g., both
`toolguard_hook.toml` and `toolguard_hook.json`), the TOML file takes precedence and a
warning is logged.

**Split user-level rules directory**: In addition to the fixed `~/.claude/` files above,
toolguard also scans `$XDG_CONFIG_HOME/toolguard/rules/` (defaulting to
`~/.config/toolguard/rules/` when `XDG_CONFIG_HOME` is unset or empty) for any number of
`*.toml`/`*.json` files. This directory is entirely optional -- if it doesn't exist, or
exists but is empty, discovery is a no-op. It exists so a large, self-contained concern
(e.g. \~60 rules for the `gh` CLI) can live in its own file instead of being mixed into one
big `toolguard_hook.toml`.

- The scan is **flat and non-recursive**: subdirectories and files with other extensions are
  ignored.
- Every file found merges into the **user level** (the least-specific tier) -- it does not
  introduce a new hierarchy tier of its own. Normal more-specific-wins / deny-wins-within-a-
  level resolution applies across the combined user-level rule set exactly as it does today.
- Files are consulted in **lexicographic order by filename stem**, appended after the four
  primary `~/.claude` candidates, so merge order and log provenance are reproducible run to
  run.
- The same **TOML-over-JSON precedence** applies per stem within the directory (e.g. `gh.toml`
  and `gh.json` both present -> only `gh.toml` is used, with the same "both formats" warning
  emitted for the single-file case).
- Each file may only contain `[permissions]` and `[hard_deny]` sections -- not
  scalar/singleton settings such as `governed_tools`, `no_match_fallback`,
  `hierarchical_configuration`, `[takeover_mode]`, or `[config_sync]`. There's no natural way
  to merge those across an arbitrary number of files, so they remain the sole responsibility
  of the primary `~/.claude/toolguard_hook.toml`. An unexpected top-level key in a
  rules-directory file is reported as an error-level configuration issue (naming the specific
  file and key) but does NOT block the file's valid `[permissions]`/`[hard_deny]` content from
  loading.
- `[regex]`/`[glob]`/`[native]` extended patterns work identically inside rules-directory
  files, since they use the same `toolguard_hook.toml`/`.json` schema.

**Worked example**: [`docs/gh-cli-rules-example.toml`](gh-cli-rules-example.toml) is a
self-contained, \~60-rule `[permissions]` block covering the `gh` CLI. Rather than pasting it
into the main `toolguard_hook.toml`, drop it in as its own file:

```bash
mkdir -p ~/.config/toolguard/rules
cp docs/gh-cli-rules-example.toml ~/.config/toolguard/rules/gh.toml
```

It is then discovered automatically as a user-level source, and a matched rule from it is
logged with its own provenance, e.g. `[user: ~/.config/toolguard/rules/gh.toml]` -- see
[architecture.md](architecture.md#logging) for the provenance format.

**Single-file override**: Setting the `CLAUDE_SETTINGS_PATH` environment variable forces
toolguard to read only that one settings file and bypass the hierarchy entirely -- including
the rules directory, which is never scanned in this mode. The migration/divergence tooling
deliberately ignores this override so it stays project-scoped.

Extended patterns (`[regex]`, `[glob]`, `[native]`) are only supported in
`toolguard_hook.toml` or `toolguard_hook.json` files, to avoid polluting native Claude
configuration. For the deeper resolution algorithm and rationale, see
[technical-notes.md](../technical-notes.md).

## Configuration reference

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

# Limit discovery to project + user levels only (default: true = full hierarchy).
# Read ONLY from the project-level config.
hierarchical_configuration = true

# What to do when a governed tool HAS rules but a command matches none (a tool with no
# rules at all always resolves to "ask"). A TOP-LEVEL key -- not nested inside
# [takeover_mode] -- applies in BOTH takeover and non-takeover modes. Options:
#   "ask" (prompt; DEFAULT), "deny" (fail-closed), "allow_with_warning" (allow + log a
#   warning; "warn_deny" is a deprecated alias for it). See "No-match fallback" below
#   for the full explanation, including the legacy [takeover_mode] alias.
no_match_fallback = "ask"

# ============================================================================
# TAKEOVER MODE - Claude sees blanket allows, toolguard enforces real rules
# ============================================================================
[takeover_mode]
# Enable takeover mode (default: false)
enabled = false

# Blanket allow patterns stripped from NATIVE settings (settings.json /
# settings.local.json) when takeover is on, so they cannot bypass your real
# rules. The five below are the BUILT-IN DEFAULTS, applied automatically -- you
# normally omit this key. Entries here are ADDED to the defaults (you cannot
# remove a default). See docs/takeover-mode.md "Ignored allow patterns".
ignored_allow_patterns = [
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)"
]

# Extra blanket allows to strip, on top of the defaults above (normal place for
# your own additions; no need to re-list the defaults).
additional_ignored_patterns = []

# LEGACY ALIAS for the top-level no_match_fallback key above -- only honored when
# no level sets the top-level key anywhere. Prefer the top-level key in new
# configs. See "No-match fallback" below.
# no_match_fallback = "deny"

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

    # Extended syntax patterns (toolguard only) - prefix lives inside the tool wrapper
    "Bash([regex]^git (status|log|diff|branch))",
    "Bash([glob]cat ~/projects/**/*.py)",
    "Bash([native]docker * --rm *)",
    "Write([regex]^/Users/[^/]+/\\.claude/.*/memory/.*\\.md$)"
]

# Denied patterns - explicitly blocked (take precedence over allow)
deny = [
    # Dangerous commands
    "Bash(rm -rf:*)",
    "Bash(sudo:*)",
    "Bash([regex]rm\\s+-rf\\s+/)",

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

# ============================================================================
# HARD DENY - Unoverridable denials no more-specific config can override
# ============================================================================
# A toolguard extension (toolguard_hook files only; ignored in native
# settings.json). Pooled across ALL hierarchy levels and checked BEFORE normal
# allow/deny resolution. Use it for rules that must always hold -- typically
# declared at the user level so no project can weaken them.
[hard_deny]
# deny: if a command/path matches one of these (and no `allow` carve-out below),
# it is DENIED, and that decision cannot be overridden by an allow at any level.
deny = [
    "Bash([regex]rm\\s+-rf\\s+/)",
    "Bash(curl:*)",
    "Read(**/.ssh/**)"
]
# allow: carve-out EXCEPTIONS to hard_deny.deny (NOT forced allows). A command
# matching one of these is exempted from the hard deny above; everything else
# still falls through to normal resolution.
allow = [
    "Bash(curl http://localhost:*)",
    "Bash(curl http://127.0.0.1:*)"
]
```

**Configuration notes**:

- **Comments**: TOML format supports inline comments (not available in JSON).
- **Pattern order**: Patterns within each section (allow/deny/ask) are checked in order.
- **Deny precedence**: Deny patterns always take precedence over allow patterns within a
  level.
- **Extended syntax**: Only supported in `toolguard_hook.toml` / `toolguard_hook.json`, not
  in `settings.local.json`.
- **Hard deny**: `[hard_deny]` rules are evaluated before everything else and **cannot** be
  overridden by an `allow` at any level (including a more-specific one); its `allow` list is
  only a carve-out exception to its own `deny`, not a forced allow. `[hard_deny]` is a
  toolguard extension (read from `toolguard_hook` files only) and is pooled across all levels
  of the configuration hierarchy.

## Keeping toolguard up to date

Toolguard ships a `toolguard-update-check` command that works for both install kinds:

- **Git install** (`uv tool install git+https://...`): uv pins the exact commit it resolved. uv
  cannot do a *version*-tracking upgrade from a git source, so the checker compares your installed
  commit against the remote HEAD. With `--upgrade` it runs `uv tool upgrade` automatically.
- **Local/editable install** (`uv tool install /path/to/toolguard` or `uv pip install -e .`):
  the checker compares your checkout's `HEAD` against the remote `origin HEAD`. Remediation is
  manual (it prints the `git pull` command and, for non-editable installs, the reinstall step);
  `--upgrade` prints the same manual steps without running anything (to avoid mutating your
  working tree).
- **Unknown**: if neither kind can be determined (no `direct_url.json` and no discoverable git
  repo), the checker exits with code 2 and a message explaining the situation.

Exit codes: `0` = up to date, `1` = update available, `2` = could not determine (offline, or
install kind is unknown).

(Once toolguard is published to a package index this whole commit-comparison becomes a plain
version check and `uv tool upgrade` handles it natively; `toolguard-update-check` can then be
retired.)

Pick whichever of the three options below suits you.

**1. Manual (simplest).**

For a git install, upgrade whenever you like:

```bash
uv tool upgrade toolguard
```

For a local/editable install, pull in your checkout (and reinstall if not editable):

```bash
git -C /path/to/toolguard pull
# non-editable only (uv tool install /path):
uv tool install --force /path/to/toolguard
```

To check first without upgrading, run `toolguard-update-check`. For a git install it reports
whether you are behind; for a local install it reports and prints the manual steps.

**2. Throttled startup alert (recommended).** Add this to `~/.zshrc` (or `~/.bashrc`) to be
*told* when an update exists -- at most once a day, network-free the rest of the time, and it
never upgrades on its own:

```bash
toolguard_update_alert() {
  local stamp="$HOME/.cache/toolguard/update-check.stamp"
  mkdir -p "$(dirname "$stamp")"
  # only check once per 24h
  if [ -z "$(find "$stamp" -mtime -1 2>/dev/null)" ]; then
    touch "$stamp"
    toolguard-update-check --quiet   # prints only when an update is available
  fi
}
toolguard_update_alert
```

For a **local install**, when `toolguard-update-check --quiet` prints (meaning you are behind),
it also prints the manual `git pull` / reinstall steps. No action is taken automatically.

**3. Auto-update (opt-in, git install only).** Same once-a-day throttle, but it *installs* the
update when one is found. This only auto-runs for a **git install**; for a local install it
prints the manual steps instead (never auto-mutates your working tree):

```bash
toolguard_auto_update() {
  local stamp="$HOME/.cache/toolguard/update-check.stamp"
  mkdir -p "$(dirname "$stamp")"
  if [ -z "$(find "$stamp" -mtime -1 2>/dev/null)" ]; then
    touch "$stamp"
    toolguard-update-check --upgrade   # auto-upgrades git installs; prints steps for local
  fi
}
toolguard_auto_update
```

> **Security caveat for auto-update.** This pulls and runs whatever is at the remote HEAD into
> your global permission hook, with no human review at pull time. That is fine if *you* are the
> sole author and gatekeeper of the repository you track (you reviewed it when you pushed).
> It is riskier if you track a repository you do not control -- a malicious or broken push
> would silently become your active permission authority. When in doubt, use option 2 (alert)
> and upgrade by hand.
