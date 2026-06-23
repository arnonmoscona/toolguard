# Quick Start

This is the shortest path to a working toolguard setup: install it, register its hooks,
tell toolguard which tools to govern, add a handful of permission patterns, and verify it
runs. For the full reference see [Configuration](configuration.md).

A working setup needs **three** things, all required:

1. **The package installed** so its entry points exist.
2. **Hooks registered** in Claude Code settings -- so Claude actually calls toolguard.
3. **A governed tools list** in toolguard's own config -- so toolguard knows what to check.

## 0. Install toolguard

**Recommended -- install as a uv tool.** This puts toolguard's two entry points on your PATH
so Claude Code can call them directly, with no wrapper script:

```bash
uv tool install /path/to/toolguard        # or: uv tool install git+https://github.com/<owner>/toolguard
uv tool update-shell                       # ensure the tool bin dir is on PATH
```

This gives you two executables in uv's tool bin directory (`~/.local/bin` by default --
confirm with `uv tool dir --bin`):

- `~/.local/bin/toolguard` -- the PreToolUse permission hook (**required**).
- `~/.local/bin/toolguard-session-start` -- the SessionStart conflict-alert hook
  (**recommended**): at the start of each session it reports any unresolved configuration
  conflicts (cross-level allow-over-deny overrides, or disagreeing `takeover_mode.enabled`
  values) so they do not go unnoticed. It nags every session until the conflict is fixed.

**Verify the install.** The hook reads a JSON PreToolUse event on stdin (not a bare command),
writes its decision to stdout, and sends any warnings to stderr. Pipe a sample event through
it -- you should get a JSON `permissionDecision` back (which value depends on your config; any
decision means the hook is installed and running):

```bash
printf '{"tool_name":"Bash","tool_input":{"command":"ls -la"},"hook_event_name":"PreToolUse"}' \
  | ~/.local/bin/toolguard
```

(Feeding a bare command such as `echo ls | toolguard` is *not* a valid test -- it is not a
hook event, so toolguard fail-closes with a `deny` and a JSON-parse reason.)

Upgrade later with `uv tool upgrade toolguard` -- see
[Keeping toolguard up to date](#keeping-toolguard-up-to-date) below.

**Alternative -- editable install (for development).** To hack on toolguard itself, install
it editable instead:

```bash
cd /path/to/toolguard
uv pip install -e .
```

With this style the same entry points are installed into the project's virtualenv instead of
`~/.local/bin` -- you point the hooks at `<checkout>/.venv/bin/toolguard` and
`<checkout>/.venv/bin/toolguard-session-start`. The
[editable-install variant](#alternative-editable-install) in step 1 shows how.

## Keeping toolguard up to date

When you install from git (`git+https://...`), uv pins the exact commit it resolved. uv cannot
do a *version*-tracking upgrade from a git source -- it follows the branch HEAD -- so toolguard
ships a small `toolguard-update-check` command that compares your installed commit against the
remote HEAD. (Once toolguard is published to a package index this becomes a plain version check
and `uv tool upgrade` handles it natively.) Pick whichever of the three options below suits you.

**1. Manual (simplest).** Upgrade whenever you like -- plain `uv tool upgrade` re-resolves the
remote HEAD and rebuilds if it moved:

```bash
uv tool upgrade toolguard
```

To peek first without upgrading, run `toolguard-update-check` (exit code `0` = up to date,
`1` = update available, `2` = could not determine, e.g. offline or not a git install).

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

**3. Auto-update (opt-in).** Same once-a-day throttle, but it *installs* the update when one is
found:

```bash
toolguard_auto_update() {
  local stamp="$HOME/.cache/toolguard/update-check.stamp"
  mkdir -p "$(dirname "$stamp")"
  if [ -z "$(find "$stamp" -mtime -1 2>/dev/null)" ]; then
    touch "$stamp"
    toolguard-update-check --upgrade   # upgrades only if behind
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

## 1. Register the hooks

Register a PreToolUse matcher for **every tool you want toolguard to govern**, plus the one
recommended `SessionStart` hook. For a useful setup, govern all the tools toolguard
supports, not just `Bash` -- otherwise file reads/writes and your other command tools slip
through ungoverned. The supported tools are:

- **Command tools**: `Bash`, `mcp__jetbrains__execute_terminal_command` (JetBrains
  terminal), and any other MCP tool that runs shell commands. These are named
  `mcp__<server>__<tool>` and vary by editor/server -- for example a terminal/command MCP
  server added in VS Code or Cursor. Run `/mcp` in Claude Code to see the exact names you
  have.
- **File-path tools**: `Read`, `Write`, `Edit`.

Each PreToolUse block points its `command` at the same `~/.local/bin/toolguard`; the
`SessionStart` block takes no matcher and runs once per session:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash",
        "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard" } ] },
      { "matcher": "mcp__jetbrains__execute_terminal_command",
        "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard" } ] },
      { "matcher": "Read",
        "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard" } ] },
      { "matcher": "Write",
        "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard" } ] },
      { "matcher": "Edit",
        "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard" } ] }
    ],
    "SessionStart": [
      { "hooks": [ { "type": "command", "command": "~/.local/bin/toolguard-session-start" } ] }
    ]
  }
}
```

Drop the matcher blocks for any tool you do not use (e.g. omit
`mcp__jetbrains__execute_terminal_command` if you do not use the JetBrains MCP), and add one
for any other command-running MCP tool you do use. Whatever tools you keep here must also
appear in `governed_tools` (next step) -- a tool is checked only when it is in **both**
places.

> **Path note:** if your environment does not expand `~` in hook commands, use the absolute
> path instead (e.g. `/home/you/.local/bin/toolguard`). Run `uv tool dir --bin` to find the
> exact directory.

### One project, or all projects

The `hooks` block above can live in either of two places -- the JSON is identical:

- **One project**: put it in that project's `.claude/settings.local.json` (local, not shared)
  or `.claude/settings.json` (shared/committed). Toolguard runs only in that project.
- **All projects (global)**: put it in your user settings, `~/.claude/settings.json`. Because
  the hook command (`~/.local/bin/toolguard`) is global, *every* Claude Code project then
  gets toolguard automatically -- no per-project hook setup needed.

Global hook registration pairs well with a user-level governed-tools config (step 2): put a
baseline `~/.claude/toolguard_hook.toml` in place and toolguard works in every project out of
the box, while individual projects can still add or override rules.

### Alternative: editable install

If you installed toolguard editable (`uv pip install -e .`) rather than as a uv tool, the
`toolguard` and `toolguard-session-start` entry points are installed into the project's
virtualenv. Point the hooks there instead of `~/.local/bin`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/.venv/bin/toolguard" }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          { "type": "command", "command": "/path/to/toolguard/.venv/bin/toolguard-session-start" }
        ]
      }
    ]
  }
}
```

Register matchers for the other governed tools exactly as in the main example above -- only
the `command` path differs.

## 2. Declare the governed tools

Create a `toolguard_hook.toml` (TOML is preferred over JSON because it allows comments). Put
it at the level that matches your hook setup from step 1:

- **One project**: `.claude/toolguard_hook.toml` in the project root.
- **All projects (global)**: `~/.claude/toolguard_hook.toml`. This is toolguard's least-
  specific configuration level, so it acts as a baseline for every project; a project's own
  `.claude/toolguard_hook.toml` is layered on top and wins on conflicts (more-specific-wins).
  See [Configuration: hierarchy](configuration.md#configuration-hierarchy).

List every tool you registered a hook for:

```toml
# Custom MCP command tools (e.g. a terminal/command MCP server you added in VS Code
# or Cursor, named mcp__<server>__<tool>) must be declared here so toolguard
# recognizes them -- otherwise they trigger "unsupported tool" warnings. Built-in
# tools (Bash, Read, Write, Edit, mcp__jetbrains__execute_terminal_command) do NOT
# need this. Uncomment and edit the line below if you have such a tool.
additional_supported_tools = [
    # "mcp__your_terminal_server__run_command",
]

governed_tools = [
    "Bash",
    "mcp__jetbrains__execute_terminal_command",
    # "mcp__your_terminal_server__run_command",
    "Read",
    "Write",
    "Edit"
]
```

A tool is only checked if it appears in **both** the hook matchers and `governed_tools`.

**`additional_supported_tools`** is needed only for custom tools toolguard does not know
about out of the box. Toolguard ships with a known list (`Bash`, `Read`, `Write`, `Edit`,
`mcp__jetbrains__execute_terminal_command`); any other tool you put in `governed_tools` (or
in permission patterns) should also be listed in `additional_supported_tools`, or toolguard
will warn that it is an unsupported tool. Declaring a tool here ("recognition") is separate
from actually governing it -- see
[Configuration: recognition vs. governance](configuration.md#declaring-additional-supported-tools)
for the full distinction.

## 3. Add a few permission patterns

Standard patterns go in `settings.local.json` so they still work if you ever disable the
hook:

```json
{
  "permissions": {
    "allow": [
      "Bash(git status:*)",
      "Bash(git log:*)",
      "Bash(uv run pytest:*)"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(sudo:*)"
    ]
  }
}
```

All command patterns use the `Bash(...)` wrapper regardless of which command tool is being
governed -- this gives one unified permission model across `Bash`, the JetBrains terminal,
and any custom MCP command tools. Deny always takes precedence over allow.

That is enough to start. When you want regex/glob/native matching, file-path control for
`Read`/`Write`/`Edit`, or shared rules across projects, read on:

- [Permission Patterns](permission-patterns.md) -- the extended pattern types and how matching works.
- [Configuration](configuration.md) -- governed tools, environment variables, the
  multi-level config hierarchy, and the full annotated config template.

## 4. Verify it runs

Restart Claude Code, run a command, then check the logs:

- Every command Claude executes should appear in `logs/toolguard-YYYY-MM-DD.md`.
- If commands are missing, confirm the tool is in **both** the hook matchers and
  `governed_tools`.

```bash
tail -f logs/toolguard-$(date +%Y-%m-%d).md
```

If nothing is logged after Claude runs commands, toolguard is not running -- see
[Security Best Practices](security.md#verify-toolguard-is-running) before relying on it,
especially before enabling [Takeover Mode](takeover-mode.md).
