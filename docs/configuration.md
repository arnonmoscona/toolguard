# Configuration

This is the full configuration reference. For the shortest working setup, start with the
[Quick Start](quickstart.md); for pattern syntax details see the
[Permission Patterns](permission-patterns.md).

Toolguard requires configuration in two places:

1. **Hook matchers** in Claude Code settings -- tells Claude which tools trigger the hook.
2. **Governed tools list** in toolguard config -- tells toolguard which tools to actually check.

Both must be configured for each tool you want to govern.

## Contents

Written for lookup rather than a start-to-finish read: jump to the section that answers the
question in front of you.

- [Step 1: Register hook matchers](#step-1-register-hook-matchers) -- which tools Claude Code
  sends to the hook at all
- [Step 2: Configure governed tools](#step-2-configure-governed-tools) -- which of those
  toolguard actually enforces
  - [Declaring additional supported tools](#declaring-additional-supported-tools)
  - [Recommended tools to govern](#recommended-tools-to-govern)
- [Step 3: Configure permission patterns](#step-3-configure-permission-patterns) -- the rules
  themselves
  - [Standard patterns (in settings.local.json)](#standard-patterns-in-settingslocaljson)
  - [Extended patterns (in toolguard_hook.toml or toolguard_hook.json)](#extended-patterns-in-toolguard_hooktoml-or-toolguard_hookjson) -- `[regex]`, `[glob]`, `[native]`
  - [Structured rule entries, and the single line rule](#structured-rule-entries-and-the-single-line-rule) -- the `{ match = "..." }` form, and the one-line requirement
  - [additionalContext: injecting guidance alongside a decision](#additionalcontext-injecting-guidance-alongside-a-decision) -- attaching explanatory text to a rule
- [No-match fallback](#no-match-fallback) -- what happens when nothing matches
- [Undecidable fallback](#undecidable-fallback) -- what happens when a command cannot be
  safely parsed at all
- [Assignments looked past when granting](#assignments-looked-past-when-granting) -- letting
  an allow rule see past a leading `VAR=value`
- [Verifying configuration](#verifying-configuration)
- [Environment variables](#environment-variables)
  - [Boolean values](#boolean-values)
  - [Project root detection](#project-root-detection)
  - [.env file](#env-file)
  - [Error handling](#error-handling)
- [Configuration hierarchy](#configuration-hierarchy) -- how project, ancestor, and user
  levels combine
- [Configuration reference](#configuration-reference) -- every section and key, annotated
- [Keeping toolguard up to date](#keeping-toolguard-up-to-date)

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

**Default: `Bash`, `Read`, `Write`, `Edit` are governed automatically.** If that is the set
you want, you can skip straight to [Step 3](#step-3-configure-permission-patterns) -- no
`governed_tools` key is required. You only need to set `governed_tools` explicitly to
**narrow** that default (e.g. Bash only) or to **add** a custom command tool such as
`mcp__jetbrains__execute_terminal_command`, which is never governed by default.

Remember that governance also requires the tool to be registered as a hook matcher in your
Claude Code settings (see [Step 1](#step-1-register-hook-matchers)) -- `governed_tools` and
the hook matchers are two independent switches, and both must be on for a given tool.

To set `governed_tools` explicitly, create `.claude/toolguard_hook.toml` (preferred) or
`.claude/toolguard_hook.json`:

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

# governed_tools defaults to Bash/Read/Write/Edit -- a custom tool is never
# governed by default, so list it explicitly alongside the built-ins you
# still want governed (this REPLACES the default, it doesn't extend it).
governed_tools = [
    "Bash", "Read", "Write", "Edit",
    "mcp__your_terminal_server__run_command"
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

#### Known limitation: only command tools and file-path tools can be governed

**Governing a tool whose subject is neither a shell command nor a file path does not work
today, and it fails closed rather than loudly.**

Toolguard reads the governed subject out of exactly two places: `file_path` for `Read`,
`Write` and `Edit`, and `command` for everything else. A tool whose payload uses any other
key -- `WebFetch` (`url`), a documentation-fetching MCP tool (`doc_id`), an API client
(`endpoint`) -- has no subject to find, so **every call is denied** with
`No command provided in tool input`, and the permission patterns you wrote for it are never
evaluated.

So a custom tool is safe to govern only when it takes its command under a `command` key.
Anything else should be left out of `governed_tools` and, if you need it restricted, denied
in your native Claude Code settings instead.

There is a second, subtler case worth knowing about even for command tools.
`mcp__jetbrains__execute_terminal_command` accepts an `executeInShell` flag which defaults to
**false**, meaning the string is run as a single process rather than through a shell. Toolguard
always parses that string as a shell command -- splitting on `&&`, `;` and `|`, and discarding
anything after a `#`. When the tool is running in process mode those characters are ordinary
arguments, so toolguard's view of the command and what actually runs can differ. Governing
that tool is still worthwhile; just do not rely on comment or compound handling being faithful
for it.

Both limitations are tracked and will be addressed together, since the fix is the same: letting
a tool describe where its subject lives and how that subject should be matched.

### Recommended tools to govern

`Bash`, `Read`, `Write`, and `Edit` are all governed by default -- the tables below explain
*why* each is worth governing, not a setting you need to make.

**Command tools** (execute shell commands):

| Tool | Description | When to include |
|------|-------------|-----------------|
| `Bash` | Native Claude Code bash tool | Always -- this is the primary tool (governed by default) |
| `mcp__jetbrains__execute_terminal_command` | JetBrains IDE terminal | If using JetBrains MCP integration (NOT governed by default -- see [Declaring additional supported tools](#declaring-additional-supported-tools)) |

Also check your MCP tool list. **Any tool that can execute bash commands should be
included.**

**File path tools** (read/write/edit files):

| Tool | Description | When to include |
|------|-------------|-----------------|
| `Read` | Claude Code file read tool | For GLOB pattern control over file reading (governed by default) |
| `Write` | Claude Code file write tool | For GLOB pattern control over file writing (governed by default) |
| `Edit` | Claude Code file edit tool | For GLOB pattern control over file editing (governed by default) |

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
- `[native]` -- Claude Code's own word-level wildcard matching

All three prefixes work for both command tools (`Bash(...)`,
`mcp__jetbrains__execute_terminal_command(...)`) and file-path tools (`Read(...)`,
`Write(...)`, `Edit(...)`). See [Permission Patterns](permission-patterns.md) for detailed syntax
and examples.

### Structured rule entries, and the single line rule

Anywhere a pattern string is accepted in a `toolguard_hook.toml` list, toolguard also accepts
a **structured entry**: an inline table carrying the pattern under a `match` key.

```toml
[permissions]
allow = [
    "Bash(git status:*)",             # plain pattern
    { match = "Bash(git log:*)" },    # structured entry, identical meaning
]
```

A bare `{ match = "..." }` entry means exactly the same thing as the equivalent plain string.
What a structured entry buys you is a second key, `additionalContext`: a string of guidance
text that toolguard injects into Claude's context when this entry is the rule that decides a
tool call. See
[additionalContext: injecting guidance alongside a decision](#additionalcontext-injecting-guidance-alongside-a-decision)
below for the full behaviour. The form is documented here regardless of whether you use
`additionalContext`, because **toolguard's own tooling can write it into your config** (the
maintenance skill and the migration command share a single serializer that emits it), so you
may meet a bare `{ match = "..." }` entry in a file you did not hand-edit. Any key other than
`match` and `additionalContext` is reported as a validation warning and otherwise ignored --
reserved for a future release.

A realistic allow and a realistic deny, each with enrichment:

```toml
[permissions]
allow = [
    { match = "Bash(git push:*)", additionalContext = "This repo requires a clean, hook-passing push. If a push is rejected, fix the underlying issue rather than reaching for --force or --no-verify." },
]
deny = [
    { match = "Bash([regex]rm\\s+-rf)", additionalContext = "Recursive force-delete is denied in this repo. Use 'git clean -fdx' for tracked-repo cleanup, or ask before removing untracked data." },
]
```

> **A structured entry MUST be written on ONE line.** TOML 1.0 forbids a multi-line inline
> table, so an entry split across lines does not merely fail on its own -- it makes the
> **entire file** unparseable, and every rule in it stops being enforced, including any
> `[hard_deny]` the file declares.

```toml
# WRONG -- breaks the whole file
allow = [
    {
        match = "Bash(git log:*)"
    }
]

# RIGHT
allow = [
    { match = "Bash(git log:*)" },
]
```

Toolguard detects this specific mistake and names the offending line rather than reporting a
generic TOML error:

```
structured rule entry starting at line 3 spans multiple physical lines, which is not valid
TOML 1.0 (an inline table must be written on a single line). Rewrite it as one line.
```

A file that fails to parse does not fail silently or fail open: every decision except an
already-`deny` one is clamped to `ask` until you fix it, and the broken file is named in the
output. Read
[Security: a broken config file also fails safe, not open](security.md#a-broken-config-file-also-fails-safe-not-open)
before relying on that clamp in an unattended session -- it behaves differently there.

### additionalContext: injecting guidance alongside a decision

`additionalContext` is a string on a structured rule entry that toolguard injects into
Claude's context -- as `hookSpecificOutput.additionalContext` in the hook's JSON output --
when that entry is the rule that decided a tool call. It works for `allow`, `ask`, `deny`,
and `[hard_deny]`, and across every governed tool (`Bash`, `Read`, `Write`, `Edit`, and any
custom command tool). A deny or hard_deny is often where it earns the most: "you can't do
this; do X instead" reaches Claude at the moment it needs the alternative, instead of Claude
discovering the constraint by trial and error.

- **toolguard config files only.** A structured entry carrying `additionalContext` inside a
  native Claude `settings.json`/`settings.local.json` layer is rejected with a validation
  warning and NOT interpreted -- neither the rule's pattern nor its context takes effect
  there. Structured entries are a toolguard extension, and this is deliberate, not an
  oversight.
- **The value must be a string.** A non-string value (a number, a bool, a table) produces an
  `error`-level validation issue, but the permission rule itself still applies -- only the
  enrichment is dropped. Toolguard refuses to coerce it: silently stringifying `true` or `3`
  would put the literal word "True" or "3" into Claude's context and look deliberate.
- **Only the deciding rule injects.** Deny-first, then more-specific-wins across levels
  decides which rule wins a tool call; only that rule's `additionalContext` is used. A rule
  that matched but did not decide the outcome contributes nothing, even if it also carries
  `additionalContext`.
- **Compound Bash commands accumulate, per contributing sub-command.** When every
  sub-command of a compound command is allowed, every allowed sub-command is a
  decision-maker (all of them had to allow for the compound to allow), so their
  `additionalContext` texts accumulate: one paragraph per contributing rule, separated by a
  blank line, in match order. Identical texts are deduplicated -- one rule matching three
  sub-commands says it once. A compound that is denied or asked has exactly one deciding
  sub-command, so its context passes through alone -- no accumulation.
- **The 500-word budget applies uniformly, to every decision and every governed tool.** The
  final text -- whether it is the compound-accumulated block above, a single deny/ask leaf's
  context, a Read/Write/Edit rule's context, or a `[hard_deny]` match's context -- is capped at
  500 words at the point it is about to be injected, filled greedily: a paragraph that would
  push the running total over budget is dropped WHOLE, never truncated mid-sentence, and
  scanning continues so a later, shorter paragraph can still fit. The one case that is never
  dropped entirely is a SINGLE paragraph that alone exceeds the budget: rather than
  disappearing, it is truncated to a 500-word prefix with a trailing
  `[toolguard: additionalContext truncated to 500 words ...]` marker, so a rule author's text
  is never silently reduced to nothing.
- **An ASK floor clamp drops it.** Two floors can clamp a decision to `ask` regardless of
  which rule matched: the Bash-only inline/heredoc-foreign-code floor (see
  [Permission Patterns: inline interpreter code](permission-patterns.md#inline-interpreter-code--c---e---r))
  and the config-parse-failure floor, which applies to every governed tool (see
  [Security: a broken config file also fails safe, not open](security.md#a-broken-config-file-also-fails-safe-not-open)).
  When either floor clamps an `allow` (or an `ask`) down to `ask`, the context is dropped --
  the floor decided the verdict, not the rule match, so injecting that rule's guidance would
  misrepresent why the prompt appeared. A `deny` is never clamped by either floor, so its
  context always survives.
- **The key is omitted, not `null`, when there is nothing to inject.** The hook's JSON output
  carries no `additionalContext` key at all unless there is real text to send, so any
  consumer that doesn't know about the field sees no change in shape.
- **The log keeps a short preview.** `logs/toolguard-*.md` records the accumulated text
  capped to a 40-word preview plus the full word count, so a large block doesn't overwhelm a
  human scanning the log for anomalies. The FULL text still reaches Claude via the hook's
  JSON output for that invocation.
- **Preview it before you rely on it.** `toolguard --eval` and
  `uv run python -m toolguard.testing.sandbox` both report the `additionalContext` a given
  command or path would trigger, so you can check the wording lands as intended without
  waiting for a live tool call.

## No-match fallback

`no_match_fallback` controls what happens when a **governed tool has rules, but a specific
command or path matches none of them.** (A governed tool with no rules at all always
resolves to `ask`, regardless of this setting.)

Set it as a **top-level** key in `toolguard_hook.toml` -- not nested inside `[takeover_mode]`
or any other section:

```toml
no_match_fallback = "ask"   # "ask" (default) | "deny" | "allow_with_warning" | "allow" | "allow_with_no_warnings"
```

Recognized values:

- `"ask"` -- prompt, the same as Claude Code's own default. **This is the default** if the
  key is unset anywhere in the hierarchy.
- `"deny"` -- fail-closed; block anything that doesn't match an explicit rule.
- `"allow_with_warning"` -- allow the command and log a warning (`"warn_deny"` is a
  deprecated alias for this value, still accepted). See
  [Auto-mode with toolguard](auto-mode.md) for the one case this is actually recommended
  for -- it is not a general recommendation.
- `"allow"` -- allow the command with **no warning anywhere** -- not in the resolution log
  reason, not in the WARNING log stream. Strictly less safe than `"allow_with_warning"`: this
  is the fully-silent variant.
- `"allow_with_no_warnings"` -- an exact synonym for `"allow"`, identical in every respect.
  It exists purely as a **human reminder**: seeing the long spelling in a config file is a
  prompt to reconsider it, and switching back to the warned variant is a 3-character edit
  (`allow_with_no_warnings` -> `allow_with_warning`). Prefer this spelling over `"allow"`
  when a person, not just an automated migration, is choosing to loosen the setting.

An unrecognized value (a typo, or anything outside the five above) is never propagated as
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

## Undecidable fallback

`undecidable_fallback` answers a **different question** from `no_match_fallback` above, and
that distinction is the whole reason both settings exist:

- `no_match_fallback`: "I read this command and understood it, but no rule covered it."
- `undecidable_fallback`: "I could not safely read this command at all."

`undecidable_fallback` governs Bash commands toolguard cannot safely decompose -- foreign
inline code and heredoc payloads (`python -c ...`, `<<EOF ... EOF`), process substitution,
`case` statements, and other control structures the PEG grammar does not decompose. In these
two situations toolguard has no rule to evaluate against the command's actual contents, so it
names a **floor level** instead of a normal decision.

Set it as a **top-level** key in `toolguard_hook.toml`:

```toml
undecidable_fallback = "ask"   # "ask" (default) | "deny" | "allow_with_warning" | "allow" | "allow_with_no_warnings"
```

Recognized values:

- `"ask"` -- prompt. **This is the default** if the key is unset anywhere in the hierarchy,
  or set to an unrecognized value.
- `"deny"` -- fail-closed; block anything toolguard could not safely parse.
- `"allow_with_warning"` -- allow the command and log a warning. Raises a **HIGH** finding
  (`loose-undecidable-fallback`) in `toolguard-audit` -- see
  [Security: Loosening the undecidable fallback](security.md#loosening-the-undecidable-fallback).
- `"allow"` -- allow the command with **no warning anywhere**. Strictly less safe than
  `"allow_with_warning"` (nothing is even logged), so it raises the SAME **HIGH**
  `loose-undecidable-fallback` finding -- never a lower severity, since the risk is greater,
  not smaller.
- `"allow_with_no_warnings"` -- an exact synonym for `"allow"`, normalized to it before
  resolution. Same human-reminder rationale as `no_match_fallback`'s identical alias above:
  the long spelling is a deliberate nudge to reconsider, and reverting to
  `"allow_with_warning"` is a 3-character edit.

There is no `"warn_deny"` alias for this setting (that alias exists only for the older
`no_match_fallback`, for backwards compatibility with its history). `"allow_with_no_warnings"`
IS honored for both settings -- it is a brand-new spelling introduced for both at once, not
part of `warn_deny`'s no_match_fallback-only history.

**Floor semantics, not a plain decision.** Unlike `no_match_fallback`, this setting does not
pick the outcome outright -- it names the *weakest* outcome the undecidable command is allowed
to resolve to, resolved **strictest-wins** (`deny` > `ask` > `allow`) against whatever the
segment's own leaf-level resolution already was:

| `undecidable_fallback` | Effect |
|---|---|
| `"deny"` | Always denies -- the strictest floor, nothing can weaken it. |
| `"ask"` (default) | Denies stay denied; anything that would otherwise resolve to allow is raised to ask. |
| `"allow_with_warning"` | No floor at all -- an explicit deny or ask still holds, but there is nothing left to raise an allow to. Allowed segments are logged with a warning. |
| `"allow"` / `"allow_with_no_warnings"` | Same floor behaviour as `"allow_with_warning"` -- identical strictness, zero effect on what gets allowed or denied. The only difference is that NO warning is logged for the resulting allow. |

An explicit `deny` or `ask` decision is **never weakened** by this setting at any value --
the floor can only make a result *stricter*, never looser. `allow_with_warning`, `allow`, and
`allow_with_no_warnings` are all the degenerate case where the floor equals "allow", so none of
them has any effect on what gets allowed or denied -- they differ only in whether the resulting
allow is logged with a warning.

**Parse-failure exemption.** A broken `toolguard_hook.toml`/`.json` file (invalid syntax,
unreadable) always clamps the whole compound decision to `ask`, regardless of
`undecidable_fallback` -- including for undecidable segments. A config toolguard could not
even load is not a policy question any setting, including this one, can relax.

**Top-level key only -- no `[takeover_mode]` alias.** Deliberately, unlike
`no_match_fallback`, there is no nested `[takeover_mode].undecidable_fallback` form and none
is planned; this is a brand-new setting with no prior spelling to preserve. Applies in
**both** takeover and non-takeover modes, resolved more-specific-wins across the
[configuration hierarchy](#configuration-hierarchy) the same way `no_match_fallback` is.

## Assignments looked past when granting

A command can set environment variables before the thing it runs -- `TG_INTENT=1 ls -la`. Matched literally, that leaf starts with `TG_INTENT=1`, not with `ls`, so `allow Bash(ls:*)` does not cover it and the command falls through to `ask`.

`assignments_looked_past_when_granting` lists the variable names an **allow** rule (and a `hard_deny` carve-out) may be matched past. A command whose leading assignments are all listed is matched a second time with them removed:

```toml
assignments_looked_past_when_granting = ["TG_INTENT", "TG_ATTEST_READONLY"]
```

**Empty by default**, and only names you list are ever looked past. That is the security of the setting: `LD_PRELOAD=/tmp/evil.so ls` must not be granted by `allow Bash(ls:*)`, and `PATH`, `PYTHONPATH` and `LD_LIBRARY_PATH` are the same shape. Put a name here only when setting that variable cannot change what the command does.

**Every name in the prefix must be listed**, or the grant sees the command as written. With only `TG_INTENT` listed, `TG_INTENT=1 LD_PRELOAD=x ls` is not granted by `allow Bash(ls:*)` -- one unlisted name withdraws the whole thing.

**Deny, ask and `hard_deny` rules ignore this setting**: they always see the command underneath the prefix, listed or not, so `FOO=1 rm -rf /tmp/x` is denied by `deny Bash(rm:*)` with nothing configured. The reasoning behind the asymmetry, and how it compares with Claude Code's own behaviour, is in [permission-patterns.md](permission-patterns.md#leading-environment-assignments).

**Pooled across the hierarchy**, like `governed_tools`: every level's list is unioned, so a name set once at the user level applies in every project and cannot be withdrawn by a more specific level. A value that is not a list, or an entry that is not a string, contributes nothing and is reported as a validation warning.

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

If `TOOLGUARD_PROJECT_ROOT` is not set, toolguard searches upward from the current directory
for any of six markers: a `.git`, `.hg` or `.jj` directory, a `.claude` directory, a
`CLAUDE.md` file, or a `pyproject.toml` file. The nearest directory containing any of them is
used as the project root -- so a stray `.claude/` or `CLAUDE.md` in a subdirectory will stop
the walk early.

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
[architecture-as-built.md](architecture-as-built.md#12-logging) for the provenance format.

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

# List of tools that toolguard will govern
# (optional -- defaults to Bash, Read, Write, Edit when no level sets it)
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

# Walk the full ancestor hierarchy (default: true). Set false to limit discovery
# to the project and user levels only. Read ONLY from the project-level config.
hierarchical_configuration = true

# What to do when a governed tool HAS rules but a command matches none (a tool with no
# rules at all always resolves to "ask"). A TOP-LEVEL key -- not nested inside
# [takeover_mode] -- applies in BOTH takeover and non-takeover modes. Options:
#   "ask" (prompt; DEFAULT), "deny" (fail-closed), "allow_with_warning" (allow + log a
#   warning; "warn_deny" is a deprecated alias for it), "allow" (allow, NO warning
#   anywhere; "allow_with_no_warnings" is an identical long-form alias, kept as a human
#   reminder). See "No-match fallback" above for the full explanation, including the
#   legacy [takeover_mode] alias.
no_match_fallback = "ask"

# What to do with a Bash command toolguard could NOT safely parse at all (foreign inline
# code / heredoc payloads, process substitution, undecomposable control structures) --
# a DIFFERENT question from no_match_fallback above. A TOP-LEVEL key ONLY -- no
# [takeover_mode] alias exists for this one. Names a strictest-wins FLOOR (deny > ask >
# allow) against the segment's own resolved decision, so an explicit deny/ask is never
# weakened. Options: "ask" (DEFAULT), "deny" (strictest), "allow_with_warning" (no floor
# at all -- raises a HIGH toolguard-audit finding), "allow" (same no-floor behaviour, but
# NO warning logged -- raises the SAME HIGH finding, not a lower one; "allow_with_no_warnings"
# is an identical long-form alias). See "Undecidable fallback" above for the full
# explanation, including the parse-failure exemption.
undecidable_fallback = "ask"

# Environment-variable names an ALLOW rule may be matched past when they appear as a
# leading assignment: with "TG_INTENT" listed, allow Bash(ls:*) also covers
# "TG_INTENT=1 ls -la". EMPTY BY DEFAULT, and every name in the prefix must be listed
# or the grant sees the command as written -- which is what keeps
# "LD_PRELOAD=/tmp/evil.so ls" outside an ls rule. Deny/ask/hard_deny ignore this and
# always see the command underneath. A toolguard extension, pooled across all levels
# like governed_tools. See "Assignments looked past when granting" above.
assignments_looked_past_when_granting = []

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

> **Upgrade note: the default `governed_tools` set grew.** Before this release, an unconfigured
> `governed_tools` defaulted to `Bash` only; it now defaults to `Bash`, `Read`, `Write`, `Edit`
> (see [Step 2: Configure governed tools](#step-2-configure-governed-tools)). If you never set
> `governed_tools` explicitly, upgrading toolguard means `Read`/`Write`/`Edit` are evaluated
> against your rules for the first time. If you never wrote file-path (`Read`/`Write`/`Edit`)
> permission patterns either, every such call now falls through to
> [`no_match_fallback`](#no-match-fallback) -- silent, a warning, or a deny, depending on that
> setting. If you want the old Bash-only behaviour, set `governed_tools = ["Bash"]` explicitly.

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
