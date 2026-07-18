# Agent Guides

Task-oriented, few-shot recipes for AI coding agents configuring toolguard on a user's
behalf. Each recipe states the goal, the decision rules, and a concrete before/after so the
edit can be applied directly. For full syntax see [Permission Patterns](permission-patterns.md) and
[Configuration](configuration.md).

## Ground rules (read first)

- A tool is only enforced if it appears in **both** the hook matchers
  (`.claude/settings.local.json`) **and** `governed_tools` (`.claude/toolguard_hook.toml`).
  If a user reports "my rule does nothing," check both before editing patterns.
- **Standard** patterns (`Bash(git log:*)`, `Read(/tmp/**)`) go in `settings.local.json`.
  **Extended** patterns (`[regex]`, `[glob]`, `[native]`) go in `toolguard_hook.toml`.
- Extended prefixes live **inside** the wrapper: `Bash([regex]...)`, never `[regex]Bash(...)`
  or a bare `[regex]...`.
- `deny` beats `allow` within a level; the most-specific level that matches decides across
  levels; `[hard_deny]` beats everything.
- Prefer the narrowest pattern that satisfies the request. Do not widen an existing rule to
  cover a new case if a second specific rule will do.

## Recipe: install and register toolguard from scratch

> For a **full guided install** -- scope/options conversation, installing via `uv`, validation,
> an optional first migration/audit/maintenance, and a journaled rollback -- follow
> [install.md](install.md). The steps below are the terse wiring reference it builds on; use
> them directly when you only need to register hooks and write the base config.

**Goal**: set up toolguard for a user who does not have it yet, governing all the tools that
matter (not just `Bash`).

**Steps**:

1. **Install** the entry points onto PATH:

   ```bash
   uv tool install /path/to/toolguard   # or: uv tool install git+https://github.com/<owner>/toolguard
   uv tool update-shell
   ```

   This yields `~/.local/bin/toolguard` (PreToolUse hook) and
   `~/.local/bin/toolguard-session-start` (SessionStart hook). Confirm the dir with
   `uv tool dir --bin`; if `~` is not expanded in hook commands, use the absolute path.
   Verify the hook runs by piping a sample event (it expects a JSON PreToolUse event on
   stdin, not a bare command) and checking for a JSON `permissionDecision`:
   `printf '{"tool_name":"Bash","tool_input":{"command":"ls -la"},"hook_event_name":"PreToolUse"}' | ~/.local/bin/toolguard`
   To keep a git install current, see
   [Keeping toolguard up to date](configuration.md#keeping-toolguard-up-to-date)
   (`uv tool upgrade toolguard`, or the `toolguard-update-check` helper).

2. **Register hooks** -- one PreToolUse matcher per governed tool, plus the SessionStart
   alert. Choose the scope first: for **one project** put the block in that project's
   `.claude/settings.local.json`; for **all projects** put the identical block in the user
   settings `~/.claude/settings.json` (the global hook command makes toolguard apply
   everywhere). Govern all supported tools the user actually uses: command tools (`Bash`,
   `mcp__jetbrains__execute_terminal_command`, and any other command-running MCP tool --
   named `mcp__<server>__<tool>`, e.g. a terminal MCP server in VS Code or Cursor; check
   `/mcp` for the real name) and file-path tools (`Read`, `Write`, `Edit`):

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

3. **Create `toolguard_hook.toml`** with `governed_tools` matching the hooks -- in the
   project (`.claude/toolguard_hook.toml`) for one project, or in `~/.claude/toolguard_hook.toml`
   as a global baseline for all projects (least-specific level; projects layer on top and win
   on conflicts). Custom MCP command tools must also go in `additional_supported_tools`
   (built-in tools do not):

   ```toml
   # Add any custom command-running MCP tool (mcp__<server>__<tool>) to BOTH lists.
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

4. **Add starter patterns** (see the recipes below) and **verify**: run a command, then
   confirm it appears in `logs/toolguard-YYYY-MM-DD.md`.

**Decision rules**:

- A tool is enforced only if it is in **both** the hook matchers and `governed_tools` --
  always set up both. Omit a tool from both if the user does not use it.
- Editable-install setups point the hooks at the entry points in the project's virtualenv
  instead -- `<checkout>/.venv/bin/toolguard` and `<checkout>/.venv/bin/toolguard-session-start`
  -- with matcher blocks for the other governed tools set up exactly as in the example above.
- For wiring details and the full supported-tool table, see
  [Configuration](configuration.md#step-1-register-hook-matchers).

## Recipe: allow a specific command

**Goal**: let Claude run a command family without prompts, without opening the door wider
than asked.

**Decision rule**: if the request is a fixed command prefix, use a DEFAULT `:*` pattern. If
it is "several related subcommands," use one `[regex]` alternation rather than a broad
prefix.

```jsonc
// Request: "let me run pytest and ruff"
// settings.local.json
{
  "permissions": {
    "allow": [
      "Bash(uv run pytest:*)",
      "Bash(uv run ruff:*)"
    ]
  }
}
```

```toml
# Request: "allow read-only git: status, log, diff, branch -- nothing that writes"
# toolguard_hook.toml -- one regex, anchored, no write subcommands
[permissions]
allow = ["Bash([regex]^git (status|log|diff|branch)\\b)"]
```

Avoid `Bash(git:*)` here -- it would also allow `git push`, `git reset --hard`, etc.

## Recipe: block a command no matter what

**Goal**: a rule that no project-level config can weaken.

**Decision rule**: a normal `deny` can be overridden by a more-specific `allow` at a deeper
level. If the user says "always," "never," "no exceptions," or it protects credentials/system
integrity, use `[hard_deny]` (in `toolguard_hook.toml` only), ideally at the **user** level.

```toml
# toolguard_hook.toml (user level: ~/.claude/)
[hard_deny]
deny = [
    "Bash([regex]\\brm\\s+-rf\\s+/)",
    "Bash(sudo:*)",
    "Read(**/.ssh/**)",
    "Read(**/.env)"
]
# Only if a narrow exception is explicitly requested:
allow = ["Bash(curl http://localhost:*)"]
```

Remember `hard_deny.allow` is a carve-out from `hard_deny.deny`, **not** a forced allow.

## Recipe: scope file access to a project

**Goal**: let Claude edit one project but not the rest of the filesystem, and never touch
secrets.

**Decision rule**: file-path tools default to GLOB. Use `**` for recursive, `*` for a single
level. Always pair an `allow` root with secret-protecting `deny` patterns.

```json
{
  "permissions": {
    "allow": [
      "Read(~/projects/myapp/**)",
      "Write(~/projects/myapp/**)",
      "Edit(~/projects/myapp/**)"
    ],
    "deny": [
      "Read(**/.env)",
      "Read(**/.env.*)",
      "Write(**/.env)",
      "Edit(**/.env)",
      "Read(**/.ssh/**)"
    ]
  }
}
```

A `Read` allow does not grant `Write` or `Edit` -- list each tool you intend to permit.

## Recipe: share rules across many projects

**Goal**: the user has the same rules copied into every project and wants one source.

**Decision rule**: move shared rules up to an ancestor `.claude/` directory (commonly
`~/.claude/`). Toolguard walks from the project root to `~` and applies more-specific-wins,
so a project can still override a shared default, and `[hard_deny]` at the top stays
unbreakable. Nothing else is needed -- discovery is automatic.

- Put org-wide guardrails in `~/.claude/toolguard_hook.toml` (`[hard_deny]` + baseline
  `deny`).
- Leave project-specific allows in each project's `.claude/`.
- To opt a project out of ancestor discovery entirely, set
  `hierarchical_configuration = false` in that project's `toolguard_hook.toml` (project +
  user levels only).

## Recipe: diagnose "my command was denied"

Work through this in order:

1. Was the tool governed? Confirm it is in both the hook matchers and `governed_tools`. If
   not, toolguard never saw it -- the denial came from native Claude.
2. Read the resolution log: `logs/toolguard-YYYY-MM-DD.md`. Each entry names the matched or
   violated rule and its provenance (`[level: file]`), so you can see exactly which level
   decided.
3. Check `logs/toolguard-conflict-YYYY-MM-DD.md`. A more-specific allow may have been
   overridden, or a `[hard_deny]` may have fired (hard-deny denials appear in the resolution
   log, not the conflict log).
4. For a compound command, find which **sub-command** failed -- each is logged separately,
   and one denied sub-command denies the whole line.
5. Fix at the right level: add a narrow `allow` at the project level to override an ancestor
   `deny`; but if a `[hard_deny]` matched, it cannot be overridden -- the rule itself must
   change.

## Recipe: clean up accumulated permissions

**Goal**: the user has many patterns piled up in `settings.local.json`.

**Expect this -- it is unavoidable.** Whenever Claude Code prompts and the user picks "Yes,
and don't ask again," Claude writes a new allow rule into its own `settings.local.json`. It
does not know about toolguard, so the rule diverges from `toolguard_hook.toml`. This recurs
throughout normal work and cannot be turned off, so treat divergence as routine maintenance,
not an error -- reconcile periodically.

**Decision rule**: never hand-move large lists. Use the migration script with a dry run
first; it also detects duplicates and supersets.

```bash
# Show what would move, with duplicate/superset detection -- review before applying
uv run python -m toolguard.scripts.migrate_permissions --dry-run

# Apply (creates a timestamped backup automatically)
uv run python -m toolguard.scripts.migrate_permissions
```

See [Config Sync & Migration](config-sync.md) for the full behavior, including
similarity ranking and backup handling.
