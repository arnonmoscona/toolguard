# Toolguard

A pre-tool-use hook for Claude Code that provides comprehensive permission checking for
bash commands, file operations, and other tools. It supports multiple tool types, extended
pattern syntax, a hierarchical (multi-level) configuration model, and detailed logging.

Toolguard is a drop-in replacement for the native Claude Code permissions system for
`Bash`, `Read`, `Write`, and `Edit`. It is backwards compatible (as of January 2026), adds
extended capabilities, and works around several long-standing bugs in the native system.

## Documentation

> **AI agents start here:** read **[docs/agent-guides.md](docs/agent-guides.md)** first. It
> is the terse, task-oriented version of everything below (install, register hooks, write
> rules, diagnose denials) and is usually enough on its own. Only open the other guides when
> a task needs the detail -- they are verbose and human-oriented.

New to toolguard? Start with the quick-start, then dip into the topic guides as needed.

| Guide | What it covers |
|-------|----------------|
| [Quick Start](docs/quickstart.md) | The shortest path to a working setup: register the hook, govern `Bash`, add a few patterns, verify. |
| [Configuration](docs/configuration.md) | Full configuration reference: hook matchers, governed tools, permission patterns, environment variables, the hierarchy/resolution model, and the annotated config template. |
| [Permission Patterns](docs/permission-patterns.md) | Pattern types (DEFAULT/REGEX/GLOB/NATIVE), file-path patterns, path normalization, and compound-command handling. |
| [Takeover Mode](docs/takeover-mode.md) | The "blanket-allow + toolguard-enforces" mode, its risks, and a complete example. |
| [Config Sync & Migration](docs/config-sync.md) | Detecting config divergence, migrating patterns into `toolguard_hook.toml`, backups, and session warnings. |
| [Security Best Practices](docs/security.md) | Blanket-allow risks, recommended deny patterns, backups, and verifying toolguard is actually running. |
| [Agent Guides](docs/agent-guides.md) | Task-oriented, few-shot recipes aimed at AI coding agents configuring toolguard. |
| [Technical Architecture](docs/architecture.md) | Package structure, hook flow, pattern-matching implementation, and logging streams. |

Developer-facing internals (subagent identification, the TOO-8 hierarchy/resolution design,
logging streams, hard-deny semantics) live in [technical-notes.md](technical-notes.md).

## Motivation

The native Claude Code permission system is adequate for simple cases but limited: it has
no regex matching, broken globstar (`**`) support for `Write`/`Edit`, no parsing of
compound commands, and recurring bugs where it re-prompts for permissions that are already
granted -- which can stall an unattended session. Toolguard addresses these gaps.

### Goals of Toolguard

- **Unified configuration**: a single permission system across multiple tools (`Bash`,
  JetBrains terminal, custom MCP command tools, etc.).
- **Compound command security**: parse and validate each sub-command separately.
- **Extended pattern types**: regex, glob with globstar, and Claude Code 2.10 native syntax.
- **Hierarchical configuration**: share rules from an ancestor `.claude/` directory instead
  of copying them into every project, with more-specific-level-wins resolution and an
  unoverridable `[hard_deny]` safety valve.
- **Path normalization**: consistent, documented normalization of paths in commands and
  patterns.
- **Better logging**: a comprehensive audit trail of every command decision, split across
  dedicated log streams.

## Requirements

- Python >= 3.14 (for `PurePath.full_match()` globstar support)
- [uv](https://docs.astral.sh/uv/) (recommended) or pip for package management
- Claude Code with PreToolUse hook support

## Installation

Making toolguard work takes three steps. The [Quick Start](docs/quickstart.md) has the full
detail (commands, settings blocks, per-project vs. global setup) -- this is just the map:

1. **Base installation** -- install the package so its hook entry points (`toolguard`,
   `toolguard-session-start`) exist on your PATH. See
   [Quick Start: Install](docs/quickstart.md#0-install-toolguard).
2. **Hook configuration** -- register the PreToolUse permission hook (required) and the
   SessionStart conflict-alert hook (recommended) in your Claude Code settings, either for a
   single project or globally for all projects. See
   [Quick Start: Register the hooks](docs/quickstart.md#1-register-the-hooks).
3. **Governed-tools config** -- create a `toolguard_hook.toml` declaring which tools
   toolguard checks. See
   [Quick Start: Declare the governed tools](docs/quickstart.md#2-declare-the-governed-tools).

Installing the package alone does nothing -- toolguard only acts once the hooks are
registered (step 2) and the tools are governed (step 3).

## Testing

```bash
cd /path/to/toolguard

# Run the whole suite (standard-library unittest, NOT pytest)
uv run python -m unittest discover -s test -t .

# Run a single test module
uv run python -m unittest discover -s test/unit -p "test_patterns.py" -v
```

The suite (683 tests as of this writing) covers all pattern types, compound commands,
command/subshell/brace-group extraction, file-path permissions, hierarchical resolution,
hard-deny, configuration loading (TOML + JSON), config validation and divergence,
auto-migration, the four logging streams, conflict logging, session warnings,
takeover mode, SessionStart conflict alerting, security-bypass attempts, parser
robustness, and edge cases.
