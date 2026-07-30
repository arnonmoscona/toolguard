# AGENTS.md

Guidance for AI agents that encounter this repository. There are two different jobs an agent
might have here -- pick the right entry point.

> **Fetching files from this repo over the web?** The default branch is `master` (not `main`).
> Do NOT guess the branch in raw URLs -- use the `HEAD` ref, which always resolves to the
> default branch regardless of its name:
> `https://raw.githubusercontent.com/<owner>/toolguard/HEAD/docs/install.md`. Better still,
> once you have run `uv tool install`, read the installed package source as ground truth rather
> than trusting a web summary (which can paraphrase JSON/TOML shapes incorrectly).
>
> **If a `WebFetch` of that raw URL hangs or is rejected**, do not keep retrying it blindly --
> ask the user to fetch it themselves (`curl -fsSL <raw-url> -o install.md` or `wget <raw-url>`,
> a plain download that does not depend on the fetch/summarizer path) and read the local file
> instead. This is a normal, expected fallback, not a sign anything is broken.

## Helping a user adopt or configure toolguard

If your job is a **full guided install for a user who does not have toolguard yet** -- they
pointed you at this repo and said "install toolguard" -- follow
**[docs/install.md](docs/install.md)**. It is a step-by-step runbook: scope and options
(including takeover mode), installing via `uv tool install` (setting up `uv` if needed),
registering the hook, validating, and offering an initial permission migration, security
audit, and maintenance pass -- doing the work for the user with consent at each step and
journaling every action to `~/.toolguard/install-journal.md` so it can be rolled back
reliably. To REMOVE toolguard later, follow [docs/uninstall.md](docs/uninstall.md).

If your job is narrower -- register hooks, write/adjust permission rules, or diagnose denials
on an existing setup -- **read [docs/agent-guides.md](docs/agent-guides.md)**. It is the terse,
task-oriented version of the documentation and is usually enough on its own. The two
operator skills (audit, maintenance) are described in [docs/skills.md](docs/skills.md). Open
the other guides under [docs/](docs/) only when a task needs the detail; [llms.txt](llms.txt)
is a file-level map of all the docs, and [docs/agent-map.md](docs/agent-map.md) goes one
level deeper -- every doc's headings, plus a question-and-pointer list for common lookups
("where does `no_match_fallback` go", "is it OK to delete `~/.toolguard`", etc.) -- reach for
it when you have a specific question rather than a task to execute.

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

> **A note on tooling.** This file, and toolguard's documentation generally, assume only a
> normal Linux or macOS environment plus toolguard itself. Nothing here requires an editor
> integration, an indexing service, a knowledge-graph server, or any other optional tool. If
> you have such tools available, use them by all means -- but their guidance belongs in your
> own configuration, not in this repository's documentation, where it would be advice a
> reader cannot follow.
