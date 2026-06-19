# AGENTS.md

Guidance for AI agents that encounter this repository. There are two different jobs an agent
might have here -- pick the right entry point.

## Helping a user adopt or configure toolguard

If your job is to install toolguard for a user, register its hooks, or write/adjust
permission rules, **read [docs/agent-guides.md](docs/agent-guides.md) first**. It is the
terse, task-oriented version of the documentation (install, register hooks for every governed
tool, write rules, diagnose denials) and is usually enough on its own. Open the other guides
under [docs/](docs/) only when a task needs the detail; [llms.txt](llms.txt) is a map of all
the docs.

What toolguard is, in one line: a Claude Code PreToolUse hook that replaces the native
permission system for Bash/Read/Write/Edit with regex/glob/native pattern matching,
compound-command parsing, a hierarchical multi-level configuration model, an unoverridable
hard-deny safety valve, and detailed logging.

Key facts an agent should not get wrong:

- A tool is enforced only if it appears in **both** the Claude Code hook matchers
  (`.claude/settings.local.json`) **and** `governed_tools` (`.claude/toolguard_hook.toml`).
- Govern all the tools the user actually uses -- command tools (`Bash`,
  `mcp__jetbrains__execute_terminal_command`, custom MCP shell tools) and file-path tools
  (`Read`, `Write`, `Edit`) -- not just `Bash`.
- Custom MCP command tools must also be listed in `additional_supported_tools`.
- Standard patterns live in `settings.local.json`; extended patterns (`[regex]`/`[glob]`/
  `[native]`, prefix inside the tool wrapper) live in `toolguard_hook.toml`.
- `deny` beats `allow` within a level; the most-specific level wins across levels;
  `[hard_deny]` cannot be overridden by any allow.

## Modifying the toolguard codebase itself

If your job is to change toolguard's own code, read [CLAUDE.md](CLAUDE.md) -- it holds the
project's conventions: standard-library-only runtime, `unittest` (not pytest), the PEG-based
bash parser generated with `canopy`, BDD-style test docstrings, and more.
