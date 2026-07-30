# Technical Architecture

This guide describes toolguard's package layout, the request flow through the hook, how
pattern matching is implemented, and the logging streams. For the deeper design rationale
behind the hierarchy, resolution, hard-deny, and logging work, see
[technical-notes.md](../technical-notes.md).

## Package structure

```
toolguard/                      # Project root
|-- pyproject.toml              # Package metadata (hatchling build backend); defines the
|                               # toolguard / toolguard-session-start entry points
|-- toolguard/                  # Python package
|   |-- __init__.py
|   |-- hook.py                 # PreToolUse hook entry point (reads stdin, writes stdout)
|   |-- session_start.py        # SessionStart conflict-alert hook entry point
|   |-- update_check.py         # toolguard-update-check entry point
|   |-- config.py               # Configuration loading, hierarchy, and resolution
|   |-- config_types.py         # Frozen dataclasses for the resolved configuration
|   |-- rule_entry.py           # RuleEntry plus the single normalize/merge chokepoint
|   |-- issues.py               # The Issue type reported by validation
|   |-- config_validation.py    # Validates tool permissions at startup
|   |-- config_divergence.py    # Config divergence detection
|   |-- config_write_guard.py   # Guarded config writes (see "Writing configuration")
|   |-- toml_scan.py            # Pure TOML scanning primitives (stdlib-only leaf)
|   |-- rule_sort.py            # Rule ordering and TOML section reassembly
|   |-- auto_migrate.py         # Config auto-migration logic
|   |-- env_config.py           # Environment configuration (.env loading)
|   |-- constants.py            # Shared constants
|   |-- permissions.py          # Permission checking logic
|   |-- resolve.py              # Bash and file-path resolution with provenance
|   |-- patterns.py             # Pattern type parsing and matching
|   |-- normalization.py        # Path normalization functions
|   |-- path_utils.py           # Project-root resolution primitive
|   |-- compound.py             # Compound command handling
|   |-- error_log.py            # Error/warning/conflict log routing
|   |-- log_writer.py           # Command logging to markdown/JSONLines files
|   |-- session_warnings.py     # Session-level warning markers
|   |-- subagent.py             # Agent context identification (best-effort; see notes)
|   |-- tools/                  # Operator tooling: the security-audit and maintenance
|   |                           # commands and their analyzers (see docs/skills.md)
|   |-- testing/                # Isolated experiment sandbox for behavioural questions
|   |                           # (development only; not used by the hook)
|   |-- parser/                 # PEG-based bash command parser
|   |   |-- __init__.py
|   |   |-- bash_parser.peg     # Grammar definition
|   |   |-- bash_parser.py      # Canopy-generated parser
|   |   `-- command_extractor.py  # Command extraction from the parsed AST
|   `-- scripts/                # Utility scripts
|       `-- migrate_permissions.py
`-- test/                       # Tests (at project root, not inside the package)
    `-- unit/
        |-- test_auto_migrate.py
        |-- test_bash_parser.py
        |-- test_compound.py
        |-- test_config.py
        |-- test_config_divergence.py
        |-- test_configuration.py
        |-- test_env_config.py
        |-- test_hard_deny.py
        |-- test_hierarchical.py
        |-- test_hook.py
        |-- test_log_writer.py
        |-- test_logging_streams.py
        |-- test_migration.py
        |-- test_normalization.py
        |-- test_patterns.py
        |-- test_permissions.py
        |-- test_session_start.py
        |-- test_session_warnings.py
        |-- test_takeover_mode.py
        `-- test_toml_config.py
```

The bash parser is generated from a formal PEG grammar (`parser/bash_parser.peg`) using the
`canopy` parser generator. This is a deliberate design choice: compound commands are split
into parts by a real grammar rather than hand-rolled regular expressions. `canopy` is a
build-time dependency only -- the generated parser depends solely on the standard library.

## Hook flow

```
+-----------------+
|  Claude Code    |
|  PreToolUse     |
+--------+--------+
         | JSON via stdin
         v
+-----------------+
|  toolguard      |--> toolguard.hook:main
|  parse_input()  |
+--------+--------+
         |
         v
+-----------------+
|  Is tool in     |--No--> Allow (not governed)
|  governed list? |
+--------+--------+
         | Yes
         v
+-------------------------+
|  Tool type?             |
+--------+----------------+
         |
    +----+----+
    v         v
+-------+ +-----------+
| File  | | Command   |
| Path  | | Tool      |
| Tool  | |(Bash,etc) |
+---+---+ +-----+-----+
    |           |
    v           v
+---------+ +-------------+
| GLOB    | | compound.py |
| match   | | Parse cmd   |
| via     | | into parts  |
|PurePath | +------+------+
|.full_   |        |
| match() |        v
+----+----+ +-------------+
     |      | permissions |
     |      | .py check   |
     |      | each subcmd |
     |      +------+------+
     |             |
     +------+------+
            v
    +-----------------+
    |  log_writer.py  |
    |  Log decision   |
    +--------+--------+
             | JSON via stdout
             v
    +-----------------+
    |  Claude Code    |
    |  Execute/Block  |
    +-----------------+
```

Both the file-path and command paths first consult `[hard_deny]` (pooled across all
hierarchy levels); a hard-deny match short-circuits to a refusal that no allow can override.
Otherwise the decision comes from the more-specific-wins cascade across levels.

## Writing configuration

The hook itself never writes configuration -- it is a read-only path. Everything that does
write (the maintenance skill, `toolguard-migrate`, `toolguard-install`, and auto-migration)
funnels through `config_write_guard.py`, so there is exactly one place where config reaches
the disk. It parses the candidate text and refuses on failure, verifies that no pattern
present before the write has gone missing, and then writes atomically via a sibling temporary
file plus `fsync` and `os.replace`.

Two of those three checks exist because valid output is not the same as correct output: a
file can parse perfectly and still have lost a rule. The user-facing description of the
guarantees is in
[Security: how toolguard protects its own writes](security.md#how-toolguard-protects-its-own-writes).

Serialization has a single chokepoint too: `rule_sort.py::render_toml_entry` is the only
place a `RuleEntry` becomes TOML, shared by the section-reassembly writer and the
from-scratch migration writer. An entry that came from an existing file is re-emitted as its
original source line verbatim, so a rewrite preserves comments and formatting rather than
normalizing them away.

## Configuration hierarchy

Toolguard layers `.claude/` configs from the project root up to the home directory and
resolves conflicts by more-specific-level-wins. The user-facing summary lives in
[Configuration: hierarchy](configuration.md#configuration-hierarchy); the full resolution
algorithm, project-root-relative path anchoring, and the `CLAUDE_SETTINGS_PATH` single-file
override are documented in [technical-notes.md](../technical-notes.md).

## Pattern matching implementation

### Command tool patterns

**DEFAULT** (`permissions.py`):

- Uses `fnmatch.fnmatch()` with colon syntax.
- Applies full path normalization to the command (tilde, symlinks, leading slashes,
  relative-path canonicalization including the first token when it is a path).
- Canonicalizes the pattern's command-name portion (`base_cmd`) when it contains `/`, so
  `./bin/X:*` and `bin/X:*` match symmetrically.
- Handles special path-component patterns like `**/.env/**`.

**REGEX** (`patterns.py`):

- Uses `re.search()` for flexible matching anywhere in the command.
- No normalization applied.
- Invalid regex patterns are treated as non-matching.

**GLOB** (`patterns.py`):

- Uses `PurePath.full_match()` for proper globstar.
- `*` matches a single path level; `**` matches recursively.
- Tilde expansion applied to both pattern and command.

**NATIVE** (`patterns.py`):

- Splits the pattern by `*` into literal segments.
- Finds segments in order within the command.
- Handles leading/trailing wildcards for anchoring.

### Compound command resolution

Compound commands are resolved by `compound.resolve_compound_permission`, which is what the
live hook (`hook.py`) drives: it splits the command into sub-commands, resolves each one
through the more-specific-wins cascade, and combines the results (any sub-command denied =>
the whole command denied; otherwise any "ask" => ask; otherwise allow).

The older `compound.check_compound_permission` is **retained but off the live path**. It
evaluates a compound command against a single flat `(allow, deny)` pattern pair and predates
the hierarchical resolver; it is kept for its tests and for callers that only need flat
allow/deny semantics, but the runtime hook no longer uses it.

### File path tool patterns

**Read, Write, Edit** (`hook.py`):

- Default: `PurePath.full_match()` GLOB matching.
- Extended prefixes inside the tool wrapper are honored: `Write([regex]...)`,
  `Write([glob]...)`, `Write([native]...)`.
- Patterns are obtained from the `Configuration` abstraction (which strips the
  `ToolName(...)` wrapper); the inner pattern is then passed through `parse_pattern` +
  `match_pattern`.
- Pattern syntax: `ToolName(pattern)`, e.g. `Read(/tmp/**)`,
  `Write([regex]^/tmp/.*\.log$)`.
- Tilde expansion applied to both patterns and file paths (GLOB / DEFAULT only; REGEX and
  NATIVE match literally).
- Deny patterns are checked first (take precedence) within a level.
- Each tool type has separate patterns (a `Read` pattern is not a `Write` permission).

## Logging

Toolguard writes to four separate daily log streams, one file per concern:

| Stream | File | Contents |
|--------|------|----------|
| Resolution | `logs/toolguard-YYYY-MM-DD.md` | Every allow/deny decision (the high-volume audit trail) |
| Errors | `logs/toolguard-error-YYYY-MM-DD.md` | Configuration/runtime errors |
| Warnings | `logs/toolguard-warning-YYYY-MM-DD.md` | Non-fatal configuration warnings |
| Conflicts | `logs/toolguard-conflict-YYYY-MM-DD.md` | Cross-level conflicts (allow-over-deny overrides, takeover `enabled` disagreements) |

Each resolution entry records the timestamp, the operation (command or file path with tool
name), the decision (allow/deny), the **matched rule** (for allowed commands, including the
winning rule's provenance -- which level/file it came from), the violated rules (for denied
commands), and the best-effort agent identification.

For compound commands (e.g., `git status && git log`), each sub-command is logged as a
**separate entry** with its own matched rule.

Example resolution entries (markdown format):

```markdown
## 2026-01-14 10:15:23

- **Status**: EXECUTED
- **Command**: `git status`
- **Matched Rule**: `git *  [project: .claude/toolguard_hook.toml]`
- **Agent**: main

## 2026-01-14 10:15:45

- **Status**: EXECUTED
- **Command**: `gh pr view`
- **Matched Rule**: `gh pr view*  [user: ~/.config/toolguard/rules/gh.toml]`
- **Agent**: main

## 2026-01-14 10:16:02

- **Status**: REFUSED
- **Command**: `Write(/etc/passwd)`
- **Violated Rules**: `Path does not match any allow patterns`
- **Agent**: main
```

The second entry shows a rule sourced from the optional split-file
`~/.config/toolguard/rules/` directory (see
[configuration.md](configuration.md#configuration-hierarchy)): it names the specific file
that matched, distinct from -- but merged into the same user level as --
`~/.claude/toolguard_hook.toml`. (Paths above are abbreviated for readability, matching the
first entry's `.claude/toolguard_hook.toml` -- the actual provenance is always the full
absolute path, e.g. `/home/alice/.config/toolguard/rules/gh.toml`.)

Example (JSONLines format):

```json
{"timestamp": "2026-01-14T10:15:23", "status": "executed", "command": "git status", "violated_rules": [], "matched_rule": "git *", "extra_info": "main"}
```

### Error and warning logs

Configuration issues and validation warnings are routed by severity: errors to
`toolguard-error-*.md`, warnings to `toolguard-warning-*.md`.

**What gets logged**:

- **WARNING**: unsupported tools in permissions (not in the known list or
  `additional_supported_tools`).
- **WARNING**: ungoverned tools in permissions (in the known list but not in
  `governed_tools`).
- **WARNING**: both TOML and JSON config files exist at the same level.
- **ERROR**: critical configuration problems (e.g., a non-boolean `takeover_mode.enabled`).

**Example warning log entry**:

```markdown
## 2026-01-20 10:30:45 - WARNING

**Message**: Tool "WebSearch" is not a known supported tool

**Corrective Steps**: If "WebSearch" is a valid tool that should be governed, add it to
"additional_supported_tools" in your config. Otherwise, remove it from permissions or update
the tool name.

---
```

**Note**: Warnings are also printed to stderr, so you will see them in your terminal when
the hook first runs. Session-warning markers prevent the same warning from repeating every
invocation -- see [Config Sync: session warnings](config-sync.md#session-warnings).

### Conflict logging and SessionStart alerts

Cross-level conflicts (a more-specific allow overriding a less-specific deny, or
`takeover_mode.enabled` set to disagreeing values across levels) are written to the
dedicated conflict stream and surfaced again at the next session start by the
`toolguard-session-start` hook, which nags every session until the conflict is resolved. The
detection logic and rationale are documented in
[technical-notes.md](../technical-notes.md).
