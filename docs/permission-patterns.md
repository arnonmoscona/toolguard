# Permission Patterns

This guide covers toolguard's pattern types, how matching works for each, path
normalization, and compound-command handling. For where to put patterns (which file,
standard vs. extended), see [Configuration](configuration.md#step-3-configure-permission-patterns).

## Pattern types

Toolguard supports two categories of pattern matching.

**1. Command patterns** (for `Bash` and terminal tools)

| Pattern type | Prefix | Matching method | Use case |
|--------------|--------|-----------------|----------|
| DEFAULT | (none) | fnmatch prefix + path normalization | Standard Claude Code patterns |
| REGEX | `[regex]` | `re.search()` | Complex matching with regex |
| GLOB | `[glob]` | `PurePath.full_match()` | File path patterns with globstar |
| NATIVE | `[native]` | Word-level segment matching | Claude Code 2.10 wildcard style |

**2. File path patterns** (for `Read`, `Write`, `Edit` tools)

File path tools use GLOB pattern matching by default via `PurePath.full_match()` -- this
provides proper globstar (`**`) support that Claude Code's native permissions lack for
`Write`/`Edit` operations. Extended prefixes (`[regex]`, `[glob]`, `[native]`) may also be
used inside the tool wrapper (e.g. `Write([regex]...)`) when stricter or alternate matching
is needed.

## Command pattern examples

### DEFAULT patterns (standard)

The default pattern type uses fnmatch with colon syntax for prefix matching:

```
Bash(git status:*)                # git status with any arguments
Bash(cat ./*:*)                   # cat files in current directory
Bash(uv run pytest:*)             # pytest with any arguments
Bash(git log:*)                   # git log with any arguments
Bash(./bin/precommit_checks.sh:*) # matches both `./bin/...` and `bin/...` invocations
```

The `:*` suffix enables prefix matching -- the command must start with the pattern before
the colon.

**Relative-path commands are canonicalized**: `bin/script.sh` and `./bin/script.sh` are
treated as equivalent on both sides of the match, so a single rule `Bash(./bin/script.sh:*)`
covers both forms. See [Path Normalization](#path-normalization) for details.

### REGEX patterns

Use the `[regex]` prefix (inside the tool wrapper) for regular expression matching with
`re.search()`:

```
Bash([regex]^git (log|diff|status))    # git log, diff, or status at start
Bash([regex]npm (install|run))         # npm install or run anywhere
Bash([regex]^curl -s https?://)        # curl with -s flag and http(s) URL
Bash([regex]pytest.*-v)                # pytest with -v flag anywhere
Write([regex]^/tmp/logs/.*\.log$)      # write to .log files under /tmp/logs
```

REGEX patterns match anywhere in the command (or path) unless anchored with `^` or `$`. No
path normalization is applied, so write absolute paths or explicit anchors when you need
them.

### GLOB patterns

Use the `[glob]` prefix (inside the tool wrapper) for true glob matching with proper
globstar (`**`) support:

```
Bash([glob]cat ~/projects/**/*.py)     # cat any .py file under ~/projects
Write([glob]/tmp/*.txt)                # write .txt files directly in /tmp only
Read([glob]/tmp/**/*.txt)              # read .txt files anywhere under /tmp
Read([glob]~/projects/*/*.js)          # .js files one level deep only
```

**Important**: GLOB patterns properly distinguish `*` from `**`:

- `*` matches any characters **except** the path separator `/`
- `**` matches any characters **including** path separators (recursive)

For file-path tools, the default (un-prefixed) form already uses glob semantics -- the
`[glob]` prefix is only needed when disambiguating from `[regex]`/`[native]` in a mixed list
or when `TOOLGUARD_EXTENDED_SYNTAX` is disabled.

### NATIVE patterns

Use the `[native]` prefix (inside the tool wrapper) for Claude Code 2.10 wildcard syntax:

```
Bash([native]git * main)               # git checkout main, git merge main, etc.
Bash([native]* install)                # npm install, pip install, cargo install
Bash([native]npm *)                    # Any npm command
Bash([native]git * origin *)           # git push origin main, git pull origin dev
Bash([native]docker * --rm *)          # docker run --rm, docker exec --rm, etc.
```

NATIVE patterns use word-level matching where `*` matches any sequence of characters.
Segments must appear in order.

## File path patterns (Read, Write, Edit)

File path patterns use GLOB syntax with proper `**` globstar support by default, and accept
extended-syntax prefixes inside the tool wrapper when you need regex or native semantics:

```
Read(~/projects/**)                                    # glob (default): any file under ~/projects
Read(/tmp/**)                                          # glob: any file under /tmp (recursive)
Read(/tmp/*)                                           # glob: files directly in /tmp only
Write(~/projects/myapp/**)                             # glob: write any file in myapp project
Write(/tmp/**/*.log)                                   # glob: write any .log file under /tmp
Edit(~/projects/**/src/*.py)                           # glob: .py files in any src directory
Write([regex]^/Users/[^/]+/\.claude/.*/memory/.*\.md$) # regex: tool-specific, no path normalization
Read([native]/Users/*/projects/*)                      # native: word-level wildcard matching
```

**Key differences between `*` and `**`**:

| Pattern | Matches | Does NOT match |
|---------|---------|----------------|
| `/tmp/*` | `/tmp/file.txt` | `/tmp/subdir/file.txt` |
| `/tmp/**` | `/tmp/file.txt`, `/tmp/subdir/file.txt`, `/tmp/a/b/c/d.txt` | `/var/tmp/file.txt` |
| `/tmp/**/*.txt` | `/tmp/file.txt`, `/tmp/subdir/file.txt` | `/tmp/file.log` |

**Deny patterns take precedence**:

```json
{
  "permissions": {
    "allow": ["Read(~/projects/**)"],
    "deny": ["Read(**/.env)", "Read(**/.env.*)"]
  }
}
```

With the above config, toolguard allows reading any file under `~/projects/` EXCEPT `.env`
files anywhere in the path.

**Tilde expansion**: Both patterns and file paths support tilde (`~`) expansion. The pattern
`Read(~/projects/**)` will match `/Users/username/projects/file.txt`.

## Path normalization

Toolguard normalizes paths in commands -- and the command-name portion of DEFAULT patterns
-- to a canonical form so that equivalent paths match:

| Normalization | Example |
|---------------|---------|
| Tilde conversion | `/Users/arnon/projects` -> `~/projects` |
| Symlink resolution | Up to 3 iterations to prevent loops |
| Leading slashes | `//tmp` -> `/tmp` |
| Relative path args | `cat file.txt` -> `cat ./file.txt` |
| Relative path as command | `bin/script.sh` -> `./bin/script.sh` (only when the first token contains `/`; bare names like `ls`, `git` are left alone) |

**Effect on rules**: a single rule `Bash(./bin/script.sh:*)` covers both `./bin/script.sh`
and `bin/script.sh` invocations, and likewise `Bash(bin/script.sh:*)` covers both -- the
match is symmetric in either direction. You no longer need to list both `./bin/X` and
`bin/X` variants.

**Normalization by pattern type**:

| Pattern type | Pattern normalization | Command normalization |
|--------------|----------------------|----------------------|
| DEFAULT | Command-name (`base_cmd`) canonicalized when it contains `/`; rest of pattern untouched | Full |
| GLOB | Tilde expansion only | Tilde expansion only |
| REGEX | None | None |
| NATIVE | None | None |

## Compound commands

Toolguard properly handles compound commands with shell operators.

**Supported operators**: `&&`, `||`, `;`, `|`, `&`

| Operator | Name | Description |
|----------|------|-------------|
| `&&` | AND | Run second command only if first succeeds |
| `\|\|` | OR | Run second command only if first fails |
| `;` | Semicolon | Run commands sequentially |
| `\|` | Pipe | Connect stdout of first to stdin of second |
| `&` | Background | Run command in background |

**Behavior**:

1. The command is parsed and split into sub-commands.
2. Each sub-command is validated separately.
3. The strictest response wins:
   - If ANY sub-command is denied -> the whole command is denied.
   - Otherwise if ANY sub-command requires "ask" -> the whole command asks.
   - Otherwise all allowed -> the whole command is allowed.

**Example**:

```bash
git status && rm -rf /    # DENIED - rm -rf is blocked even though git status is allowed
ls -la | grep foo         # Both parts must be allowed
sleep 10 &                # Background command - sleep is validated
```

### Command substitution support

Toolguard extracts and validates commands inside substitutions:

| Construct | Example | Status |
|-----------|---------|--------|
| Command substitution | `$(rm -rf /)` | Inner command extracted and validated |
| Backtick substitution | `` `rm -rf /` `` | Inner command extracted and validated |
| Subshells | `(cd /tmp && rm -rf *)` | Inner commands extracted and validated |
| Brace groups | `{ cmd1; cmd2; }` | Inner commands extracted and validated |

**Nested constructs** are supported up to 5 levels deep:

```bash
echo $(cat $(find . -name '*.txt'))
# All three commands validated: echo, cat, find

(cd /tmp && rm -rf *)
# Both commands validated: cd, rm -rf (denied)
```

### Current limitations

The following bash constructs are **not currently parsed** -- their inner commands are
treated as opaque:

| Construct | Example | Status |
|-----------|---------|--------|
| Process substitution | `<(cmd)` or `>(cmd)` | Inner command not validated |
| Control structures | `if/for/while/case` | Body commands not validated |

**Note**: Analysis of historical command logs shows Claude Code rarely generates shell
control structures at the start of commands. When `if/for/while` appear, they are typically
inside Python one-liners or awk scripts where they are treated as string arguments rather
than shell parsing constructs. This makes the risk of bypassing toolguard via control
structures very low in practice.

**Mitigation**: Use deny patterns that match dangerous commands even when nested. Remember
that extended-syntax prefixes must live inside the tool wrapper:

```json
{
  "deny": [
    "Bash([regex]rm\\s+-rf)",
    "Bash([regex]rm\\s+.*-rf)"
  ]
}
```
