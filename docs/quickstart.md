# Quick Start

You don't need to become a toolguard expert, and you don't need to do the setup yourself.
Toolguard ships an automated, guided install, a security auditor, a config-tidying skill,
and a migration tool -- Claude can drive all of them for you, explaining each decision as it
goes. This page covers the one thing you're still likely to do by hand: writing your own
permission rules.

## Get toolguard running

**Recommended -- let Claude install it for you.** Tell Claude, in this repo or any project
you want governed:

> Install toolguard from `<this repo's URL>` using `docs/install.md` from the `master`
> branch.

Claude will walk you through a short conversation: what to govern, which scope (one project
or every project), whether to enable [Takeover Mode](takeover-mode.md), and whether to
install the [audit and maintenance skills](skills.md). Every change is journaled and
reversible -- see [Uninstalling](#uninstalling) below.

**Manual / scripted install.** If you'd rather do it yourself (no AI agent involved, or
you're scripting a reproducible setup), the exact `uv tool install` commands, hook JSON, and
`toolguard_hook.toml` are laid out step by step in
[Agent Guides: install and register toolguard from scratch](agent-guides.md#recipe-install-and-register-toolguard-from-scratch).
Package options (uv tool vs. editable install) and the update-check tooling are covered
there and in [Configuration](configuration.md).

## Write your own permission rules

This is the part quickstart is really for -- everything else, an agent can do for you, but
*what you want allowed or denied* is your call to make.

Standard patterns go in `settings.local.json` so they still work even with the hook
disabled:

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
governed (Bash, a JetBrains terminal, any custom MCP command tool) -- one unified permission
model. Deny always takes precedence over allow, and a tool is only checked if it is in
**both** the hook matchers and `governed_tools` (both handled for you by the guided install).

That's enough to start. Toolguard also supports three extended pattern "dialects" (used in
`toolguard_hook.toml`, not `settings.local.json`) for cases plain prefix matching can't
express -- one minimal example of each:

```
Bash([regex]^git (log|diff|status))    # regex: any of these three git subcommands, anchored
Bash([glob]cat ~/projects/**/*.py)     # glob: true recursive ** (not just a prefix wildcard)
Bash([native]git * origin *)           # native: word-level wildcard, e.g. git push origin main
```

The same three dialects work inside `Read(...)`/`Write(...)`/`Edit(...)` too, not just
`Bash(...)` -- file paths default to glob matching already, but `[regex]` and `[native]` are
available there as well when you need them, e.g. `Write([regex]^/tmp/.*\.log$)`. Full syntax,
matching rules, and more file-path examples are in [Permission Patterns](permission-patterns.md).

### You don't have to become an expert to use any of this

You do not need to read all of toolguard's documentation, and you do not need to learn its
pattern dialects by hand -- Claude has already read them. You can:

- **Ask Claude questions** -- "what does `[native]` matching do", "why didn't my rule
  match" -- and get an answer grounded in the real docs, not a guess.
- **Describe the security stance you want, in plain English, and have Claude write the
  rules.** "Let me run any read-only git and gh command, but nothing that pushes,
  force-pushes, or changes repo settings" is enough -- Claude can turn that into a correct,
  properly anchored rule set without you touching regex or glob syntax yourself.

[`docs/gh-cli-rules-example.toml`](gh-cli-rules-example.toml) is a real worked example of
exactly this: a full, carefully-reasoned rule set governing the `gh` CLI (61 rules, generated
from `gh`'s own manual against a stated disposition -- read-only allowed, anything that
modifies GitHub-side state denied, with a couple of explicit exceptions). Point Claude at a
tool's own docs and ask for the same treatment.

**This solves a real, common problem.** Plenty of tools people run every day -- the AWS CLI,
`kubectl`, the Terraform CLI, and many more -- are enormously powerful and carry real risk in
careless or compromised hands, with dozens of subcommands and flags that each deserve a
different trust level. Hand-writing a good rule set for a tool like that is impractical, and
doing it with Claude Code's *native* permission system alone is not just impractical but
genuinely impossible -- native patterns are prefix-only, with no way to express "any of these
subcommands, but never with this flag" or similar shape-aware distinctions. Toolguard's
regex/glob/native dialects can express that; Claude, working from toolguard's own
documentation and a tool's own docs, can generate it correctly from a plain-English security
stance. That combination gets you real, meaningful protection on tools that would otherwise
be all-or-nothing.

Two more skills round this out, and both are conversational -- you describe what you want,
Claude does the mechanical work:

- **[Maintenance](skills.md#maintenance) streamlines your rule set as it grows.** Every
  "yes, and don't ask again" adds a rule; over time you end up with duplicates, near-
  duplicates, and rules that could be one broader rule instead. Ask Claude to run it and it
  proposes consolidations family-by-family (all your `git` rules together, and so on) --
  nothing is merged or removed without your explicit, per-item approval.
- **[Security audit](skills.md#security-audit) checks that your rules stay safe.** Beyond
  its deterministic checks (over-broad allows, unanchored regexes, takeover-mode
  misconfiguration), you can hand it a stance in plain English -- "make sure nothing here
  lets Claude force-push, and every secret-file path is denied" -- and have it assess your
  actual configuration against that, not just generic rules of thumb.

## Keep settings.local.json and toolguard_hook.toml in sync

Rule drift is normal, not a mistake: every time Claude Code prompts and you answer "yes,
and don't ask again," it writes a new allow rule into its own `settings.local.json` --
Claude Code has no idea `toolguard_hook.toml` exists. Left alone, your permissions end up
split across two files.

`toolguard-migrate` folds those native rules back into `toolguard_hook.toml` (dry-run first
to preview, then apply -- it backs up before writing and removes exact/subset duplicates
from `settings.local.json` as it goes). To have this happen automatically instead of running
it by hand, set in `toolguard_hook.toml`:

```toml
[config_sync]
auto_migrate = true   # fold settings.local.json rules in on every hook startup
```

Off by default -- turn it on once you trust your rule set (dry-run first), and keep it off
if you would rather review each migration before it lands. See
[Config Sync & Migration](config-sync.md) for the full detail, including backup handling and
similarity/duplicate detection.

## Verify it runs

There is no need to restart Claude Code as once the hook is setup it goes live immediately.
The agent guided install would have verified already that the installation was successful and 
that toolguard is functioning. If you want to make sure yourself, run a command, then check the logs:

```bash
tail -f logs/toolguard-$(date +%Y-%m-%d).md
```

Every command Claude executes should appear there. If nothing is logged after Claude runs
commands, toolguard is not running -- see
[Security Best Practices](security.md#verify-toolguard-is-running) before relying on it,
especially before enabling [Takeover Mode](takeover-mode.md).

## Running unattended (Claude Code auto-mode)

If you also run Claude Code itself in an auto-accept / bypass-permissions mode, see
[Auto-mode with toolguard](auto-mode.md) -- toolguard is still worth registering in that
setup, but the honest tradeoffs are different enough to deserve their own page.

## Uninstalling

**Tell Claude to follow [`docs/uninstall.md`](uninstall.md)** -- the guided, journal-driven
rollback owns the whole teardown (config, hooks, skills, package) end to end. No separate
manual steps to remember here.
