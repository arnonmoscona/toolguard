# Permission Patterns

This guide covers toolguard's pattern types, how matching works for each, path
normalization, and compound-command handling. For where to put patterns (which file,
standard vs. extended), see [Configuration](configuration.md#step-3-configure-permission-patterns).

## Contents

Written for lookup rather than a start-to-finish read: jump to the section that answers the
question in front of you.

- [Pattern types](#pattern-types) -- command patterns vs. file-path patterns, at a glance
- [Command pattern examples](#command-pattern-examples)
  - [DEFAULT patterns (standard)](#default-patterns-standard)
  - [REGEX patterns](#regex-patterns)
  - [GLOB patterns](#glob-patterns)
  - [NATIVE patterns](#native-patterns)
- [File path patterns (Read, Write, Edit)](#file-path-patterns-read-write-edit)
- [Path normalization](#path-normalization)
- [Leading environment assignments](#leading-environment-assignments)
- [Compound and multi-line commands](#compound-and-multi-line-commands)
  - [The governing principle: when in doubt, ASK](#the-governing-principle-when-in-doubt-ask)
  - [Operators](#operators)
  - [Multi-line commands and scripts](#multi-line-commands-and-scripts)
  - [Command substitution and subshells](#command-substitution-and-subshells)
  - [Heredocs and the `__HEREDOC_TO_<sink>__` sentinel](#heredocs-and-the-__heredoc_to_sink__-sentinel)
  - [Inline interpreter code (`-c` / `-e` / `-r`)](#inline-interpreter-code--c---e---r)
  - [Control structures](#control-structures)
  - [Process substitution](#process-substitution)
  - [Limitations (summary)](#limitations-summary)

## Pattern types

Toolguard supports two categories of pattern matching.

**1. Command patterns** (for `Bash` and terminal tools)

| Pattern type | Prefix | Matching method | Use case |
|--------------|--------|-----------------|----------|
| DEFAULT | (none) | fnmatch prefix + path normalization | Standard Claude Code patterns |
| REGEX | `[regex]` | `re.search()` | Complex matching with regex |
| GLOB | `[glob]` | `PurePath.full_match()` | File path patterns with globstar |
| NATIVE | `[native]` | Word-level segment matching | Claude Code's own wildcard style |

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

The `:*` suffix enables prefix matching -- the command must start with the pattern before the colon, and that prefix must end on a token boundary. So `Bash(git log:*)` matches `git log` and `git log --oneline`, but not `git logfoo`. This mirrors Claude Code's own `Bash(git log *)`, which `:*` is equivalent to.

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

**`[native]` is defined by reference to Claude Code's own builtin rules, which change.** What it is supposed to mirror — quoted verbatim, with the date it was last verified and the known divergences — is in [native-pattern-reference.md](native-pattern-reference.md). **Check that file's date before relying on equivalence**, and update it there rather than restating the semantics here.

Use the `[native]` prefix (inside the tool wrapper) for Claude Code's wildcard syntax:

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
| Symlink resolution | A link is replaced by its target, including a dangling one; a symlinked ancestor directory is followed too, but only for an absolute path |
| Leading slashes | `//tmp` -> `/tmp` |
| Relative path args | `cat file.txt` -> `cat ./file.txt` |
| Relative path as command | `bin/script.sh` -> `./bin/script.sh` (only when the first token contains `/`; bare names like `ls`, `git` are left alone) |

**Effect on rules**: a single rule `Bash(./bin/script.sh:*)` covers both `./bin/script.sh`
and `bin/script.sh` invocations, and likewise `Bash(bin/script.sh:*)` covers both -- the
match is symmetric in either direction. You no longer need to list both `./bin/X` and
`bin/X` variants.

**A rule written with an absolute home path fires on the `~` spelling.** Every `Bash` rule
is matched against the command as written **and** with a leading `~` in each token
expanded, so `deny Bash(cat /Users/arnon/.ssh/id_rsa)` fires on `cat ~/.ssh/id_rsa`. That
direction holds for all four pattern types.

**The reverse direction is a DEFAULT accommodation, with one `[glob]` exception.** A
DEFAULT rule is matched against
two further spellings -- normalized, and normalized with symlinks resolved -- which is how
a rule written with `~` fires on the absolute spelling. `[regex]` and `[native]` rules get
no such spelling. `[glob]` gets it only when the whole pattern begins with `~`:
`[glob]~/bin/*` matches `/Users/arnon/bin/x`, but `[glob]cat ~/.ssh/*` does not match
`cat /Users/arnon/.ssh/id_rsa`. So write an extended-syntax rule about a home path with the
absolute path, or expect to write both spellings.

**Unlike the assignment asymmetry below, the tilde spelling is offered to `allow` too.**
Looking past `FOO=1` discards something real, so a granting rule must not do it. `~name`
resolves through the passwd database to that account's actual home directory -- the same
resolution a shell performs -- so `~/x` and `/Users/arnon/x`, or `~arnon/x` and
`/Users/arnon/x`, are two spellings of one file; there is nothing for a granting rule to be
protected from.

`~<name>` is expanded through the passwd database to that account's home directory,
whether or not it is the account this process runs as: a rule blind to it could be walked
past by spelling it that way. A name the database does not know, a `~` that does not start
a token, and a `~` inside a quote opened at the start of its token are all left as written.

**Normalization by pattern type**:

| Pattern type | Pattern normalization | Command normalization |
|--------------|----------------------|----------------------|
| DEFAULT | Command-name (`base_cmd`) canonicalized when it contains `/`; rest of pattern untouched | Full, plus per-token tilde expansion |
| GLOB | Leading `~` only -- so `[glob]~/bin/*` reaches an absolutely-spelled command, but `[glob]cat ~/bin/*` does not | Per-token tilde expansion |
| REGEX | None | Per-token tilde expansion |
| NATIVE | None | Per-token tilde expansion |

## Leading environment assignments

A command may set variables before the thing it runs: `FOO=1 rm -rf /tmp/x`. Matched literally, the leaf begins with `FOO=1`, not with `rm`, so `deny Bash(rm:*)` never fires. Toolguard therefore matches such a command **twice** -- as written, and with the assignment prefix removed -- but not symmetrically:

| List | What it is matched against |
|---|---|
| `deny`, `ask`, `hard_deny` | the command as written, **and** with the leading assignments removed |
| `allow`, and a `hard_deny` carve-out | the command as written; with the assignments removed **only** when every one of their names is listed in `assignments_looked_past_when_granting` |

**The asymmetry is the point.** Looking past an assignment when granting is how `LD_PRELOAD=/tmp/evil.so ls` would slip through `allow Bash(ls:*)`; `PATH`, `PYTHONPATH` and `LD_LIBRARY_PATH` are the same shape. So a restricting rule always sees the command underneath, and a granting rule only sees past names you have named.

Both spellings are matched by **every** pattern type -- DEFAULT, `[regex]`, `[glob]` and `[native]` alike. The command as written is always matched too, so a rule deliberately keyed on the prefix, like `deny Bash(TG_INTENT=1 rm:*)`, keeps working.

The prefix is identified by the bash grammar, so `FOO+=1`, quoted values and a substitution in the value (`FOO=$(id) rm`) are all recognised, and an assignment-looking token that is not leading (`echo FOO=1`) is not one. Configuring the granting side is covered in [configuration.md](configuration.md#assignments-looked-past-when-granting).

**Compared with Claude Code.** Native's documented behaviour has the same shape: a deny or ask rule matches past any leading assignment, and an allow rule matches past only "certain known-safe environment variables". What differs is the list -- native's is Claude Code's own and its members are not named in that documentation, whereas toolguard's is `assignments_looked_past_when_granting` and starts empty, so nothing is looked past when granting until you say so. This applies to the whole matching engine, not to `[native]` patterns specifically -- the quoted source is in [native-pattern-reference.md](native-pattern-reference.md#known-divergences-between-toolguard-and-the-above).

**Known limitation**: an array-element assignment (`arr[0]=$(id) rm -rf /tmp/x`) is not modelled by the grammar, so it still hides the command from a deny rule. Recorded deliberately rather than closed, because subscripts pull the grammar toward general bash.

## Compound and multi-line commands

Toolguard parses each Bash command with a formal grammar, splits it into its individual
sub-commands, and validates each one separately. The **strictest result wins**:

1. If ANY sub-command is denied -> the whole command is **denied**.
2. Otherwise if ANY sub-command requires "ask" -> the whole command **asks**.
3. Otherwise (all allowed) -> the whole command is **allowed**.

### The governing principle: when in doubt, ASK

Toolguard only auto-decides constructs it can decompose with confidence. Anything it cannot
safely break down -- a complex control structure, code in a non-bash interpreter, a construct
it does not model -- resolves to **ASK** (a prompt), never to a silent allow of an
undecomposed blob and never to a hard failure that would block a legitimate workflow. This is
the single most important thing to understand about how multi-line input is handled.

ASK is the **default**, not a hardcoded outcome: the `undecidable_fallback` config key
controls the floor level (`"ask"` default, `"deny"`, or `"allow_with_warning"`/`"allow"` --
the latter two remove this guarantee and are flagged by `toolguard-audit`). See
[Configuration: Undecidable fallback](configuration.md#undecidable-fallback) and
[Security: Loosening the undecidable fallback](security.md#loosening-the-undecidable-fallback).

### Operators

**Supported operators**: `&&`, `||`, `;`, `|`, `&`

| Operator | Name | Description |
|----------|------|-------------|
| `&&` | AND | Run second command only if first succeeds |
| `\|\|` | OR | Run second command only if first fails |
| `;` | Semicolon | Run commands sequentially |
| `\|` | Pipe | Connect stdout of first to stdin of second |
| `&` | Background | Run command in background |

```bash
git status && rm -rf /    # DENIED - rm -rf is blocked even though git status is allowed
ls -la | grep foo         # both stages must be allowed
sleep 10 &                # background command - sleep is validated
```

### Multi-line commands and scripts

Claude Code routinely issues multi-line Bash (several statements, or a whole script) in one
tool call. Toolguard decomposes these the same way it decomposes `;`-separated commands:

| Form | Handling |
|------|----------|
| Newline-separated statements | Each line is a separate statement (a newline acts like `;`). Every statement is validated. |
| Blank lines / leading-trailing padding | Ignored. |
| CRLF (`\r\n`) line endings | Normalized; handled identically to `\n`. |
| Trailing operator continuation (line ends with `&&`, `\|\|`, or `\|`) | Joined with the next line into ONE compound command. |
| Backslash line continuation (`\` then newline) | Joined into a single logical line before matching. |
| `#` comments | Stripped (a `#` only starts a comment at a word boundary, so `http://x#frag` is kept as an argument). |

```bash
# this whole block is validated statement-by-statement:
git status
echo "building" && make
rm -rf /            # <- this line alone causes the whole block to be DENIED
```

### Command substitution and subshells

Commands **inside** substitutions, subshells, and brace groups are extracted and validated:

| Construct | Example | Handling |
|-----------|---------|----------|
| Command substitution | `rm $(ls)` | inner `ls` validated (and the outer `rm`) |
| Backtick substitution | `` rm `ls` `` | inner `ls` validated |
| Subshells | `(cd /tmp && rm -rf *)` | inner `cd`, `rm -rf` validated |
| Brace groups | `{ cmd1; cmd2; }` | inner commands validated |

Nested substitutions are supported (e.g. `echo $(ls $(pwd))` validates `echo`, `ls`, and
`pwd`).

### Heredocs and the `__HEREDOC_TO_<sink>__` sentinel

A heredoc body (`cmd <<EOF ... EOF`) is **data fed to a command**, not shell to parse. Before
matching, toolguard removes the body and presents the heredoc-bearing command with an
all-letters sentinel argument, **`__HEREDOC_TO_<sink>__`**, where `<sink>` is the ultimate
consumer of the body (it follows the pipe). What happens next depends on that sink:

| Sink kind | Examples | Handling |
|-----------|----------|----------|
| **Non-executor** | `cat`, `tee`, `pbcopy` | The body is data. The bearer is matched normally, e.g. `cat __HEREDOC_TO_pbcopy__`. The body is never parsed as commands. |
| **Bash-family shell** | `bash`, `sh`, `dash`, `ksh`, `zsh` | The body IS bash; it is decomposed and each inner command is validated. |
| **Foreign interpreter / non-bash shell** | `python`, `node`, `perl`, `ruby`, `php`, `Rscript`, `uv`, `csh`, `fish` | The body is opaque code -> **ASK floor** (see below). |

The sentinel uses only `[A-Za-z0-9_]`, so it is easy to match in rules without escaping. The
bearer command keeps its other arguments, so a dangerous bearer is still caught
(`tee /etc/passwd <<EOF` -> `tee /etc/passwd __HEREDOC_TO_tee__`, still subject to a `tee` or
`Write` deny). Examples:

```
# allow heredocs only into known data sinks:
Bash([regex]__HEREDOC_TO_(cat|tee|pbcopy)__)

# match any heredoc at all (e.g. to deny or audit):
Bash([regex]__HEREDOC_TO_)
```

> **Safety:** never *allow* a heredoc whose sink is an executor (`bash`, `python`, ...). That
> would allow an arbitrary, unreviewed body to run -- a blanket-allow-class risk. Toolguard
> enforces an ASK floor on executor-sink heredocs (a plain `allow` cannot downgrade it; an
> explicit `deny` still applies). See [Security](security.md#multi-line-commands-and-the-ask-safe-guarantee).

### Inline interpreter code (`-c` / `-e` / `-r`)

Code passed inline to an interpreter is handled by the same executor rule as heredocs:

| Form | Handling |
|------|----------|
| `bash -c "<bash>"` (and `sh`/`dash`/`ksh`/`zsh -c`) | The inner string is bash -> decomposed and each command validated. |
| `python -c "..."`, `node -e "..."`, `perl -e`, `ruby -e`, `php -r`, `uv run python -c "..."` | Opaque foreign code -> **ASK floor** (a broad allow such as `uv run*` cannot downgrade it). |
| `python script.py`, `node app.js` (a named script, not inline code) | Matched normally -- only *inline* code gets the floor. |

### Control structures

| Construct | Handling |
|-----------|----------|
| Simple `if ... then ... fi`, `for/while ... do ... done` | Decomposed when non-nested, with no `else`/`elif`, a linear body, and a condition that is a plain command or a POSIX `[ ... ]` test. The condition and body commands are validated. |
| `case ... esac`; any `else`/`elif`; nested control structures; `[[ ... ]]` / `(( ... ))` conditions | Too complex to decompose safely -> **ASK**. |

A POSIX `[ ... ]` test is treated as a test, not a command (it needs no rule); any command
substitution inside it is still extracted and validated.

### Process substitution

Process substitution `<(...)` / `>(...)` is **not** decomposed today; a command using it
resolves to **ASK** (it is not silently allowed). Example: `diff <(sort a) <(sort b)` -> ASK.

### Limitations (summary)

These resolve to **ASK** rather than being auto-decided -- safe, but they will prompt:

- Complex / nested control structures, `case`, and `if/else`.
- Inline code in a non-bash interpreter (`python -c`, `node -e`, ...) and heredocs fed to one.
- Process substitution `<(...)` / `>(...)`.
- Any input the grammar cannot decompose.

For the strongest protection, still add explicit `deny` / [`[hard_deny]`](configuration.md#configuration-reference)
rules for destructive commands (e.g. `Bash([regex]rm\\s+-rf)`) so they hold regardless of how
a command is constructed -- see [Security: defense in depth](security.md#maintaining-your-toolguard-configuration).

Note that the design is intentionally simplified. It does not attempt to handle situations that would make toolguard code overly complex, hard to reason about, or error-prone. It also does not attempt to cover some situations that are plausible, but we have not seen convincing evidence that Claude Code actually uses them frequently enough. This is not a bash interpreter, nor is it a general security tool. Toolguard is focused on governing Claude Code behavior and making the configuration of the rules simple and easy to author and understand.
