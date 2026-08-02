# Takeover Mode

**Takeover Mode** is an advanced configuration that lets Claude Code receive blanket
permissions while toolguard acts as the real security gatekeeper. This eliminates permission
prompts during Claude Code operation while keeping full security control in toolguard's
hands.

> Read the [Security Warnings](#security-warnings) before enabling takeover mode, and never
> enable it before you have tested your real permission set.

## What is takeover mode?

In takeover mode:

1. **Claude Code sees blanket allows** -- no permission prompts interrupt the workflow.
2. **Toolguard enforces real permissions** -- all commands/file operations are validated by
   toolguard's rules.
3. **Best of both worlds** -- uninterrupted workflow with full security control.

## When to use takeover mode

**Use takeover mode when:**

- You want Claude to work without permission interruptions.
- You trust toolguard's permission system to enforce security.
- You have well-defined allow/deny patterns in toolguard configuration.
- You want consistent permission enforcement across all tools.

**Don't use takeover mode when:**

- You are still configuring and testing permissions.
- You prefer explicit Claude Code permission prompts as a second layer.
- You are in a high-security environment requiring multi-layer validation.

## How it works

Takeover mode operates by creating a split configuration:

1. **In `.claude/settings.local.json`**: add blanket allow patterns that Claude Code sees:

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

2. **In `.claude/toolguard_hook.toml`**: define the real permissions toolguard enforces:

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

When `takeover_mode.enabled = true`, toolguard strips the blanket allow patterns (like
`Bash(*)`) out of your **native** Claude settings (`settings.json` / `settings.local.json`)
as it loads them, so those blanket allows cannot bypass the real permissions you defined in
`toolguard_hook.toml`. Which patterns get stripped is controlled by `ignored_allow_patterns`
-- see [Ignored allow patterns](#ignored-allow-patterns) below.

### Conflict handling across the hierarchy

Takeover mode is a single-owner setting (typically declared at the user level). The
`enabled` flag is **not** merged per level. Toolguard recomputes it live from all levels:

- No level sets it -> takeover is OFF.
- All levels that set it agree -> that value is used.
- Levels disagree -> toolguard **fails safe to OFF** (native Claude prompts stay active,
  nothing is silently bypassed) and records a high-visibility conflict (dedicated conflict
  log + SessionStart alert).
- A non-boolean `enabled` value does not vote and is reported as a configuration error.

This is deliberate: silently keeping takeover ON against a project's more cautious OFF would
weaken security, and denying everything would brick a session over a benign override. See
[technical-notes.md](../technical-notes.md) for the full rationale.

## Configuration options

```toml
[takeover_mode]
# Enable takeover mode (default: false)
enabled = false

# Blanket allow patterns stripped from NATIVE settings while takeover is on.
# The five values below are the BUILT-IN DEFAULTS -- they are applied
# automatically, so you normally do not list this key at all. Anything you do
# put here is ADDED to the defaults (you cannot remove a default).
ignored_allow_patterns = [
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)"
]

# Extra blanket allows to strip, ON TOP OF the defaults above. This is the
# normal place to add your own (no need to re-list the defaults).
additional_ignored_patterns = []
```

**`no_match_fallback`** (what happens when a governed tool has rules but a command matches
none of them) is a **top-level** `toolguard_hook.toml` key, not part of `[takeover_mode]` --
and it applies whether or not takeover mode is on. A nested `[takeover_mode].no_match_fallback`
form is still accepted as a legacy alias, but new configs should set it at the top level:

```toml
no_match_fallback = "deny"   # strict fail-closed posture, e.g. for a takeover setup

[takeover_mode]
enabled = true
```

See [Configuration: No-match fallback](configuration.md#no-match-fallback) for the full
explanation (all three values, resolution order, and the legacy-alias precedence rule).

`no_match_fallback` has a sibling setting, `undecidable_fallback`, that answers a different
question -- "this command could not be safely parsed at all" (foreign inline code, heredocs,
process substitution) rather than "no rule covered this command." It applies whether or not
takeover mode is on, has no `[takeover_mode]` alias, and defaults to `"ask"`. See
[Configuration: Undecidable fallback](configuration.md#undecidable-fallback).

**Example with custom patterns**:

```toml
no_match_fallback = "ask"  # prompt instead of deny on no match

[takeover_mode]
enabled = true
additional_ignored_patterns = [
    "Bash(~/projects/**)",  # Ignore overly broad project access
]
```

### Ignored allow patterns

This is the heart of takeover mode: the list of blanket allow patterns that toolguard
suppresses so they cannot quietly grant Claude everything. The exact behavior:

- **Built-in defaults (always applied).** When takeover is enabled, toolguard always ignores
  these five blanket allows, even if you configure nothing:

  ```
  Bash(*)
  Read(*)
  Write(*)
  Edit(*)
  mcp__jetbrains__execute_terminal_command(*)
  ```

- **Two keys, both additive.** `ignored_allow_patterns` is pre-seeded with those defaults;
  `additional_ignored_patterns` starts empty. Whatever you put in *either* key is **added**
  to the defaults (unioned, de-duplicated) -- there is no way to *remove* a default. Prefer
  `additional_ignored_patterns` for your own entries so you do not have to re-list the
  defaults. Both keys are also unioned across every level of the
  [config hierarchy](configuration.md#configuration-hierarchy).
- **Native settings only.** Ignoring strips matching patterns out of your *native* Claude
  config (`settings.json` / `settings.local.json`) as it is read. The same pattern written in
  a `toolguard_hook.toml`/`.json` file is **not** stripped -- that is your real rule set.
- **Allow only, exact match.** Only `allow` entries are affected (never `deny`), and matching
  is **exact** after the tool wrapper is removed: `Bash(*)` suppresses exactly the `Bash(*)`
  allow, not narrower allows like `Bash(git *)`.
- **Only while enabled.** Nothing is ignored unless `takeover_mode.enabled` is true; with
  takeover off, your native allow patterns are honored normally.

In short: you rarely need to touch `ignored_allow_patterns`. Reach for
`additional_ignored_patterns` only when you keep an *extra* broad allow in your native
settings (e.g. `Bash(~/projects/**)`) that you want toolguard to disregard so your
`toolguard_hook.toml` rules stay authoritative.

## Security warnings

**CRITICAL**: If toolguard fails to run (e.g., a Python error or missing dependency), Claude
Code sees only the blanket allow patterns and will execute ANY command without restriction.

**To mitigate this risk**:

1. **Test thoroughly** before enabling takeover mode.
2. **Monitor logs** regularly at `logs/toolguard-YYYY-MM-DD.md`.
3. **Check error logs** at `logs/toolguard-error-YYYY-MM-DD.md`.
4. **Start with `no_match_fallback = "ask"`** until you are confident in your patterns.
5. **Use deny patterns** for critical resources (e.g., `**/.env`, `**/.ssh/**`), and
   consider promoting the most important ones to
   [`[hard_deny]`](configuration.md#configuration-reference) so no level can weaken them.

**Verify toolguard is running**:

```bash
# Commands should appear in daily logs
tail -f logs/toolguard-$(date +%Y-%m-%d).md
```

If no logs appear after Claude Code executes commands, toolguard is NOT running and the
blanket allows are exposed.

## Example configuration

A complete takeover mode setup:

**`.claude/settings.local.json`** (blanket allows for Claude Code):

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
no_match_fallback = "deny"

[takeover_mode]
enabled = true

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
    "Bash([regex]rm\\s+-rf\\s+/)",

    # Sensitive files
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)"
]
```
