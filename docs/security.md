# Security Best Practices

**Audience: anyone configuring toolguard -- human or agent -- who needs to know where the
sharp edges are.** This page covers the risks of blanket allows, the two guarantees toolguard
makes when it cannot fully understand its input (the ASK-safe guarantee for commands, and the
same posture applied to unparseable config files), how config writes are protected from
corruption, what to back up, how to verify toolguard is actually running, and a recommended
review cadence with a starting set of deny patterns. Read
[Blanket allow risks](#blanket-allow-risks) first if you read nothing else.

## Contents

Written for lookup rather than a start-to-finish read: jump to the section that answers the
question in front of you.

- [Blanket allow risks](#blanket-allow-risks) -- why a bare `Bash(*)`/`Write(*)` is dangerous,
  and the safe alternatives
- [A cloned project's config can inject text into Claude's context](#a-cloned-projects-config-can-inject-text-into-claudes-context) -- the `additionalContext` risk from an untrusted project
- [Multi-line commands and the ASK-safe guarantee](#multi-line-commands-and-the-ask-safe-guarantee) -- why undecomposable input never silently executes
- [Loosening the undecidable fallback](#loosening-the-undecidable-fallback) -- what
  `undecidable_fallback = "allow_with_warning"`/`"allow"` turns off and what still protects you
- [A broken config file also fails safe, not open](#a-broken-config-file-also-fails-safe-not-open) -- the parse-failure ASK floor
- [How toolguard protects its own writes](#how-toolguard-protects-its-own-writes) -- the
  guarantees behind every config write toolguard performs
- [Backup importance](#backup-importance)
- [Testing with dry-run](#testing-with-dry-run)
- [Verify toolguard is running](#verify-toolguard-is-running) -- red flags that it is not
- [The hook can be silently shadowed](#the-hook-can-be-silently-shadowed) -- `PYTHONPATH`
  making an unreviewed checkout govern instead of the installed release
- [Ongoing security review](#ongoing-security-review) -- what to check and how often
- [Maintaining your toolguard configuration](#maintaining-your-toolguard-configuration) -- keeping rules readable and trustworthy over time
- [Recommended deny patterns](#recommended-deny-patterns) -- a starting deny list

## Blanket allow risks

**Never use blanket allows without toolguard protection.**

```json
{
  "permissions": {
    "allow": ["Bash(*)", "Write(*)"]
  }
}
```

**Why this is dangerous**:

- Claude can execute ANY command or write ANY file.
- There is no protection against mistakes or malicious suggestions.
- It bypasses all security controls.

**Safe approaches**:

1. **Specific patterns only** (no takeover mode):

   ```json
   {
     "permissions": {
       "allow": [
         "Bash(git status:*)",
         "Write(~/projects/myapp/**)"
       ]
     }
   }
   ```

2. **Takeover mode with toolguard** (blanket allows OK -- see [Takeover Mode](takeover-mode.md)):

   ```toml
   # In settings.local.json: Bash(*), Write(*)
   # In toolguard_hook.toml:
   [takeover_mode]
   enabled = true

   [permissions]
   allow = ["Bash(git status:*)", "Write(~/projects/myapp/**)"]
   deny = ["Bash(rm -rf:*)", "Write(**/.env)"]
   ```

For rules that must hold no matter what any project config says, promote them to
[`[hard_deny]`](configuration.md#configuration-reference), which is pooled across all
hierarchy levels and cannot be overridden by a `[permissions]` allow at any level (it has
its own narrow `hard_deny.allow` carve-out list, which is a different mechanism -- see the
configuration reference linked above).

## A cloned project's config can inject text into Claude's context

A project-level `.claude/toolguard_hook.toml` (or `.json`) is discovered from the project
directory you open Claude Code in -- including a repository you cloned and did not author. A
structured rule entry in that file can carry
[`additionalContext`](configuration.md#additionalcontext-injecting-guidance-alongside-a-decision):
free text that toolguard injects straight into Claude's context, as
`hookSpecificOutput.additionalContext`, whenever that rule is the one that decides a matching
tool call. So a hostile project config is not just a set of permission rules -- it is also a
channel for arbitrary text the model is designed to treat as system-provided guidance, and you
may never have written or reviewed that text.

**In proportion: this is a lesser included risk, not a new class of exposure.** A project-level
config can already contribute `allow` patterns, and under more-specific-wins resolution the
project level is the MOST specific -- so a project-level `allow` already overrides a `deny`
declared at a less specific (e.g. user) level, for anything not pooled in
[`[hard_deny]`](configuration.md#configuration-reference) (`hard_deny` is collected across every
level and is the one thing a project config cannot override). In other words, a hostile project
config already has a strictly stronger lever available to it than context injection: it can turn
an inherited `deny` into a silent `allow` outright, before `additionalContext` even enters the
picture. Anyone who has trusted a cloned project with permission rules at all has already accepted
a bigger risk than this one.

**The asymmetry that is genuinely new is visibility, not severity.** Permission rules --
`allow`/`deny`/`ask`/`[hard_deny]` patterns -- are the object every audit tool in this project
reasons about: `toolguard-audit` and `toolguard-maintain` inspect them, flag risky patterns, and
report on them. `additionalContext`'s free text is not: no finding in `toolguard-audit`
enumerates, inspects, or reports on it today, so a rule carrying a large or manipulative
`additionalContext` string produces no signal in that tooling, even though it produces one every
time the rule matches at runtime. That gap is real and, as of this writing, nothing closes it --
reviewing a project's `toolguard_hook.toml` by hand (`grep -n additionalContext`) is the only way
to see what it says before trusting the project.

**No mitigation is planned before 1.0.** The real fix would be a user-level opt-out or review
gate for `additionalContext` from project-level config; it is deliberately not being built yet --
toolguard has very few users today, and adding a feature ahead of a demonstrated need is not
this project's priority. Claude Code's own "do you trust the files in this folder?" prompt on
first opening a project is the control that already exists here: answering yes accepts the
project's risks, including this one, alongside everything else a project's own settings and
`CLAUDE.md` can already do. Treat an unfamiliar cloned project the same way you would treat
running its code -- read its `toolguard_hook.toml` before you say yes.

## Multi-line commands and the ASK-safe guarantee

Claude Code frequently issues multi-line Bash, heredocs, and whole scripts in a single tool
call. Toolguard decomposes these and validates **each statement separately** (strictest-wins:
any denied statement denies the whole command). For the full mechanics see
[Permission Patterns: compound and multi-line commands](permission-patterns.md#compound-and-multi-line-commands).

The security guarantee is **fail-safe, not fail-open**: any construct toolguard cannot
decompose with confidence resolves to **ASK** (a prompt) -- it is never silently allowed as an
undecomposed blob. This covers complex/nested control structures, `case`, `if/else`, process
substitution `<(...)`, and code in non-bash interpreters. *(Historically, a multi-line command
whose first line matched an allowed prefix could slip later lines past the checks; that
fail-open bypass is closed.)*

This ASK behaviour is the `undecidable_fallback` **default**, not a hardcoded outcome --
see [Configuration: Undecidable fallback](configuration.md#undecidable-fallback) for the
setting itself, and [Loosening the undecidable fallback](#loosening-the-undecidable-fallback)
below for what changes if you set it to `allow_with_warning` or `allow`.

**Inline code and heredocs fed to an executor are a blanket-allow-class risk.** Code passed to
a shell or interpreter -- `python -c "..."`, `node -e "..."`, `bash <<EOF ... EOF`,
`cat <<EOF | bash` -- can do anything, and toolguard cannot read what it will do. Two rules
follow from this:

- **Bash-family payloads are decomposed and validated.** `bash -c "git status; rm -rf /"` and
  `cat <<EOF | bash` have their inner bash checked command-by-command.
- **Foreign-interpreter payloads get an ASK floor.** `python -c`, `node -e`, a heredoc piped to
  `python`, etc. always prompt by default -- and a broad `allow` (even `uv run*`) **cannot**
  downgrade that to a silent allow. An explicit `deny` still applies. Versioned interpreters
  (`python3.13`, `pypy3.11`, ...) are recognized automatically for the python, pypy, node,
  nodejs, perl, ruby and php families only -- a versioned `Rscript` or `awk` is not. This floor also drops any `additionalContext` the clamped rule would
  otherwise have injected, since the floor -- not the rule match -- decided the prompt; see
  [Configuration: additionalContext](configuration.md#additionalcontext-injecting-guidance-alongside-a-decision).
  This ASK floor's strictness is the `undecidable_fallback` setting's default; see
  [Loosening the undecidable fallback](#loosening-the-undecidable-fallback) below.

  *Caveat:* the floor applies to interpreters toolguard **recognizes** (the common Python /
  Node / Perl / Ruby / PHP / R / non-bash-shell families). An interpreter it does not know
  (e.g. `lua`, `deno`, `bun`, `julia`) is **not** floored, so a broad `allow` for it would
  permit its inline code. It is still validated as a command (an explicit `deny` works) -- but
  prefer not to broadly allow interpreters, recognized or not.

**Do not write an `allow` rule that permits an executor-sink heredoc or inline foreign code.**
Allowing `Bash([regex]__HEREDOC_TO_python__)` or `Bash(python3 -c:*)` re-creates exactly the
blanket-allow problem this section warns about -- you would be approving arbitrary, unreviewed
code. Leave them at ASK (or `deny`), and reserve `allow` for heredocs into data sinks
(`cat`, `tee`, `pbcopy`) and for named scripts you trust. See the
[heredoc sentinel patterns](permission-patterns.md#heredocs-and-the-__heredoc_to_sink__-sentinel)
for how to write these rules.

As always, **defense in depth**: add explicit `deny` / [`[hard_deny]`](configuration.md#configuration-reference)
rules for destructive commands (e.g. `Bash([regex]rm\\s+-rf)`) so they hold no matter how a
command is assembled.

## Loosening the undecidable fallback

Setting `undecidable_fallback` to `"allow_with_warning"`, `"allow"`, or its identical alias
`"allow_with_no_warnings"` is a **genuine loosening of a security control**, not a cosmetic
option -- see
[Configuration: Undecidable fallback](configuration.md#undecidable-fallback) for the setting's
full mechanics. This section covers what it turns off and, more importantly, what still
protects you when it is set.

**`"allow"` is not a safer or more cautious spelling than `"allow_with_warning"` -- it is
strictly less safe.** Both values have IDENTICAL effect on what gets allowed or denied; the
only difference is that `"allow"` records nothing at all, not even a warning. Do not read the
shorter, plainer-sounding name as the more conservative choice. The long alias
`"allow_with_no_warnings"` exists specifically to counter that impression: seeing it in a
config file is a deliberate nudge that this is worth reconsidering, and reverting to the
warned variant is a 3-character edit (`allow_with_no_warnings` -> `allow_with_warning`).

**What it turns off.** The two fail-safe-not-fail-open guarantees described above -- the ASK
floor on foreign inline code / heredoc sinks, and the "any construct toolguard cannot
decompose resolves to ASK" guarantee for `case`, nested control structures, and process
substitution -- both stop applying. Those commands execute with **no toolguard rule ever
evaluated against their contents**: toolguard cannot read what a `python -c "..."` payload or
an unparsed control structure will actually do, so this setting is trusting the command
outright rather than gating it.

**What still protects you.** Any of the three loosened values above only removes the *floor*
-- none of them touches anything else in the permission pipeline:

- **An explicit `deny` or `ask` rule still applies.** The floor can only ever raise an
  undecidable segment's decision, never lower one -- so a rule that already resolves the
  segment to `deny` or `ask` is unaffected. Only segments that would otherwise have floored
  from a silent `allow` are exposed.
- **[`[hard_deny]`](configuration.md#configuration-reference) still applies.** Hard-deny rules
  are pooled and checked before normal allow/deny resolution regardless of this setting.
- **[The parse-failure ASK floor still applies.](#a-broken-config-file-also-fails-safe-not-open)**
  A broken `toolguard_hook.toml`/`.json` clamps to ASK unconditionally -- this is the one
  fallback `undecidable_fallback` cannot loosen, by design.

**Residual risk, concretely.** With `"allow_with_warning"` set, a compromised or careless
Claude invocation can pass arbitrary code to `python -c`, `node -e`, a heredoc piped to an
interpreter, or an unparseable control-structure command, and toolguard will let it run (with
only a logged warning) unless a specific `deny`/`ask`/`[hard_deny]` rule happens to catch the
outer command. **With `"allow"`/`"allow_with_no_warnings"` set, the same thing happens with NOT
EVEN a logged warning** -- the only record of what ran is whatever Claude's own transcript
retains; toolguard's own logs show nothing distinguishing it from an ordinary explicit allow.
Since the whole point of these constructs is that toolguard cannot read their payload, writing
a rule to catch the *contents* is not generally possible -- you would be relying on catching
the outer invocation shape, which is exactly the blanket-allow risk
[above](#multi-line-commands-and-the-ask-safe-guarantee) warns against.

`toolguard-audit` raises a **HIGH** finding (`loose-undecidable-fallback`) whenever this
setting resolves to `allow_with_warning` OR `allow` (the latter includes the
`allow_with_no_warnings` alias, already normalized before the audit runs) -- `allow` triggers
the SAME severity, never a lower one, since it is the less-safe of the two. See
[Ongoing security review](#ongoing-security-review) below for how to run the audit routinely.
`undecidable_fallback = "deny"`, by contrast, raises no finding: it is strictly more
conservative than the `"ask"` default, not a loosening.

## A broken config file also fails safe, not open

A syntax error in any single `toolguard_hook.toml`/`.json` file (project, user, or a rules-directory
file) does not silently disable the rules it contains -- including `deny` and `[hard_deny]`. When
toolguard detects that a governed config file failed to parse, it clamps **every** permission
decision to **ASK** until the file is fixed: an explicit `deny`/`hard_deny` from elsewhere in the
hierarchy is never weakened, but anything that would otherwise have been a silent `allow` now
prompts instead. The permission prompt itself names the broken file and its parse error, and
`toolguard-session-start` repeats the same warning at the start of every session (Claude Code
injects that into the session context) until it is fixed. This mirrors the ASK-safe guarantee
above -- decompose-with-confidence-or-ASK -- applied at the config layer instead of the
command-parsing layer.

**The rules in the broken file itself are still gone.** The clamp protects you from a silent
`allow`; it does not resurrect the file's contents. If the unparseable file was the one
declaring a `[hard_deny]`, that hard deny is not enforced while the file is broken -- the
command it was blocking resolves to ASK instead of DENY.

> **It does not become a silent allow, including in [auto-mode](auto-mode.md).** An ASK
> returned by toolguard's `PreToolUse` hook is a real permission request, and Claude Code's
> unattended modes do not bypass it -- the command still stops and waits. So a `[hard_deny]`
> lost to a TOML syntax error degrades from "blocked outright" to "blocked pending an answer",
> not to "allowed". What you lose is the DENY; what you keep is the stop.
>
> In an unattended run that means the session **stalls** on the first affected command rather
> than proceeding without the rule -- the same dead end
> [auto-mode.md](auto-mode.md#why-no_match_fallback--ask-the-normal-default-doesnt-work-here)
> describes for `no_match_fallback = "ask"`. Inconvenient, and the right failure direction.
>
> Two habits keep it from costing you a run: declare `[hard_deny]` at the **user** level,
> where a broken project file cannot take it out, and treat `toolguard-session-start`'s
> broken-config warning as a stop-work item rather than noise -- especially before starting an
> unattended session. A one-line syntax error is the cheapest possible fix, right up until it
> costs you an overnight run.

**This behaviour is deliberately not tunable, and will stay that way.** Other fallbacks are
configurable because they answer a policy question -- what should happen to an action no rule
covers. A parse failure is not a policy question: toolguard does not know what its rules
*are*, so it has no basis for any verdict at all. There is nothing to trade off, so there is
no setting to loosen. Clean, parseable config is the precondition for trusting any of it.
Expect the friction to be loud and repeated until you fix the file -- that is the feature.

The most common way to produce this specific failure is a structured rule entry split across
several lines; see
[Structured rule entries, and the single line rule](configuration.md#structured-rule-entries-and-the-single-line-rule).

This floor also clears any `additionalContext` a matched rule would otherwise have injected
(unless the decision is an unaffected `deny`) -- see
[Configuration: additionalContext](configuration.md#additionalcontext-injecting-guidance-alongside-a-decision).

## How toolguard protects its own writes

Permission config is frequently not under version control, so a corrupting write is permanent,
unrecoverable loss. Config writes from the maintenance skill, the migration command and the
installer all go through a single guarded path that makes three promises. It is a convention,
not a barrier: nothing stops a future writer from bypassing it.

1. **It never writes a file that does not parse.** The final text is parsed before anything
   touches the disk. If it would not load, the write is refused and the original is left
   byte-for-byte unchanged.
2. **It refuses a write that would drop a rule** -- when the caller hands it the pre-write
   pattern set. Valid output can still be wrong output, so the guard re-parses the final text
   and refuses if a pattern has gone missing, even though the result would have parsed
   cleanly. The check is opt-in; `toolguard-install write-config` is the caller that skips it,
   because it writes a fresh file with no rules of its own.
3. **It cannot leave a half-written file.** Writes go to a sibling temporary file which is
   flushed, `fsync`ed, and then atomically renamed over the target, so a crash or a full disk
   mid-write leaves either the old file or the new one, never a truncated one.

A refusal is reported, not swallowed -- if you see one, the config on disk is intact and the
change was not applied. This protects toolguard's own tooling; it does not protect a file you
edit by hand, which is what the backups below are for.

## Backup importance

**Always test changes with backups.**

1. **Before enabling takeover mode**:

   ```bash
   # Backup your configs
   cp .claude/settings.local.json .claude/settings.local.json.backup
   cp .claude/toolguard_hook.toml .claude/toolguard_hook.toml.backup
   ```

2. **Before running migration**:

   ```bash
   # Dry run first
   toolguard-migrate --dry-run

   # Migration creates an automatic backup, but a manual backup doesn't hurt
   cp .claude/toolguard_hook.toml logs/manual-backup-$(date +%Y-%m-%d).toml
   ```

3. **Regular backups**:

   ```bash
   # Weekly backup
   cp .claude/toolguard_hook.toml ~/backups/toolguard-$(date +%Y-%m-%d).toml
   ```

## Testing with dry-run

**Always test migrations before executing.**

```bash
# Step 1: See what would change
toolguard-migrate --dry-run

# Step 2: Review output carefully
# - Are the patterns correct?
# - Any unexpected migrations?
# - Similar patterns that should be consolidated?

# Step 3: Execute only if dry-run looks good
toolguard-migrate

# Step 4: Verify the result
diff .claude/toolguard_hook.toml logs/config-backups/toolguard_hook-*.toml
```

## Verify toolguard is running

1. **Check logs after commands**:

   ```bash
   tail -20 logs/toolguard-$(date +%Y-%m-%d).md
   ```

   You should see entries for every *governed* tool call, provided logging is enabled.

2. **Monitor error and warning logs**:

   ```bash
   tail -f logs/toolguard-error-$(date +%Y-%m-%d).md
   tail -f logs/toolguard-warning-$(date +%Y-%m-%d).md
   ```

   Watch for warnings about configuration issues.

3. **Test with an intentional violation**: if `rm -rf /` is denied, ask Claude to run it and
   confirm it is logged as refused.

**Red flags that toolguard is NOT working**:

- No entries in `logs/toolguard-YYYY-MM-DD.md` after Claude executes commands.
- Commands execute that should be denied.
- No warnings/errors in logs when you expect them.

This matters most under [Takeover Mode](takeover-mode.md): if toolguard is silently not
running, the blanket allows are fully exposed.

## The hook can be silently shadowed

Toolguard *appearing* to run and toolguard's *own reviewed code* making the decision are not
the same guarantee. A stray `PYTHONPATH` entry -- most commonly `PYTHONPATH=.` left exported
from a shell rc file -- can make Python import a different `toolguard/` package than the one
actually installed, if that entry happens to contain its own `toolguard/` directory (a clone
of this repository is the obvious case, but any directory with a `toolguard/` subdirectory
qualifies). When that happens for the PreToolUse hook process, **every permission decision on
this machine is made by whatever code sits in that shadowing directory** -- possibly
uncommitted, mid-refactor, or simply never reviewed -- instead of the installed release. The
hook still runs, still returns a decision, and produces no error: this is a silent substitution
of *what* is deciding, not a failure you would notice from the logs described above. This was
found the hard way (TOO-19): a real install ran a shadowed, mid-refactor checkout as its live
permission hook for weeks before anyone noticed.

**Detection is automatic and gated to toolguard's own repository.** `toolguard-session-start`
checks, once per session, whether the active project IS a toolguard source checkout, and if so
whether the copy that produced that check is that same checkout rather than the installed
distribution -- if so, it prints a loud alert naming both the governing and the installed path.
A related, separate check catches a **stale install**: the installed copy's content differs
from a *clean* (no uncommitted changes) working tree, meaning you committed something and
forgot to reinstall. Both checks are silent everywhere else -- they answer a question that only
makes sense while you are developing toolguard itself. `toolguard-audit` carries a
complementary, always-on finding (`pythonpath-shadows-hook`, HIGH severity) that fires whenever
`PYTHONPATH` contains an entry that WOULD shadow the hook, independent of whether this
particular process happened to be shadowed -- silent, like every other finding in this project,
when the condition does not hold.

**The installer hardens the registration itself.** `toolguard-install register-hooks` registers
the PreToolUse hook as `<tool venv python> -E -P -m toolguard.hook` rather than the bare
console-script path, when it can verify the interpreter path first. `-E` makes the interpreter
ignore `PYTHONPATH` entirely; `-P` additionally stops it from prepending the current working
directory (or the script's own directory) to `sys.path` -- both are needed, because a plain
`-m` invocation would still pick up a `toolguard/` package sitting in the process's cwd even
with `PYTHONPATH` unset. Together they make the registered hook immune to both shadowing
vectors. `toolguard-install skills-status` reports an existing **unhardened** registration (an
older bare-binary form) so you can re-run `register-hooks` to switch to the hardened form; it
also flags a hardened registration whose recorded interpreter no longer exists on disk, which
is otherwise a silent failure -- see the note below.

**One risk this hardening deliberately manages, not eliminates: the hardened command bakes an
absolute interpreter path into your settings file.** If that exact path ever stops existing (an
unusual reinstall layout, a manually relocated venv), Claude Code cannot launch the hook at all
-- and a PreToolUse hook that fails to launch is, in Claude Code's own hook contract, a
**non-blocking error**: the tool call proceeds with **no toolguard decision whatsoever**,
silently. That would be strictly worse than the shadowing problem this hardening exists to
close. `register-hooks` therefore verifies the interpreter path exists and is executable
*before* writing it, and falls back to the older, unhardened-but-working bare-binary form when
it cannot -- an unhardened, working hook is always preferred over a hardened, broken one. Run
`toolguard-install skills-status` after any reinstall that might relocate the tool's venv, so a
newly-broken hardened path is caught by a diagnostic rather than by a silently ungoverned
session.

## Ongoing security review

Toolguard enforces your rules, but a permission system is only as good as the attention you
give it. Set a routine to review what it logged, what it warned about, what drifted, and
whether the rules still make sense.

**The fastest way to do this: ask Claude to run the [security-audit](skills.md#security-audit)
skill.** It runs a deterministic analyzer over your whole config hierarchy -- over-broad allows,
brittle secret-file protections, unanchored regexes, takeover-mode misconfiguration -- ranked
by severity, then optionally offers a deeper, judgement-based AI-assisted pass on top. It is
read-only and does exactly the "rules themselves" and "error & warning" review below in one
pass, with evidence instead of a raw log dump. The manual facilities in the table are still
there for scripting, spot-checking a specific log, or when you want the raw signal instead of
the skill's synthesis -- as in any security workflow, automation assists your review, it does
not replace your judgment.

| Review (suggested cadence) | What to look for | Where / supporting facility |
|----------------------------|------------------|-----------------------------|
| **Resolution log** -- after busy sessions / daily | Unexpected allows or refusals; which level and file authorized each command (the matched rule is logged with its `[level: path]` provenance) | `logs/toolguard-YYYY-MM-DD.md` -- see [logging](architecture-as-built.md#12-logging) |
| **Error & warning logs** -- regularly | Config errors (e.g. a non-boolean `takeover_mode.enabled`), ungoverned or unsupported tools, both-format (`.toml`+`.json`) conflicts | `logs/toolguard-error-*.md`, `logs/toolguard-warning-*.md`; also printed to stderr on every invocation until fixed (see [warning throttling](config-sync.md#warning-throttling)); the [security-audit skill](skills.md#security-audit) flags config errors too |
| **Conflicts & divergence** -- every session / periodically | Cross-level allow-over-deny overrides, `takeover_mode.enabled` disagreements, and rules that have drifted into native `settings.local.json` | `logs/toolguard-conflict-*.md` + the **SessionStart conflict-alert hook** (re-reports until resolved); drift via `toolguard-migrate --dry-run` -- see [Config Sync](config-sync.md) |
| **The rules themselves** -- periodically (e.g. monthly) | Over-broad or blanket allows, stale / duplicate / superseded rules, gaps in `[hard_deny]` coverage | The **[security-audit](skills.md#security-audit)** skill for risk findings; the **[maintenance](skills.md#maintenance)** skill for duplicate/consolidation/promotion proposals (family-grouped, certified before you approve anything); `toolguard-migrate --dry-run` for a lighter-weight duplicate/superset/similarity check; promote critical denies to [`[hard_deny]`](configuration.md#configuration-reference) |

A quick periodic pass, if you want the raw signal instead of running the skills:

```bash
# What ran / was refused today, with the rule + level that decided each
tail -n 50 logs/toolguard-$(date +%Y-%m-%d).md

# Config problems, conflicts, and drift
tail -n 50 logs/toolguard-error-$(date +%Y-%m-%d).md
tail -n 50 logs/toolguard-warning-$(date +%Y-%m-%d).md
tail -n 50 logs/toolguard-conflict-$(date +%Y-%m-%d).md

# Rules that drifted into native settings, plus redundant / over-broad rules
toolguard-migrate --dry-run
```

**What is automated vs. on you:**

- **Automatic** -- the SessionStart hook re-reports unresolved conflicts every session until
  you fix them; configuration problems are written to the error/warning logs and shown once
  per session on stderr; every decision is logged with its matched-rule provenance; conflicts
  are recorded to the conflict log; `auto_migrate` (if enabled) folds drift back on startup.
- **Assisted** -- the security-audit and maintenance skills do the analytical work of spotting
  risky, duplicate, or promotable rules and present it as an evidence-backed proposal.
- **On you** -- the final call on each finding: accept, narrow, remove, or promote to
  `[hard_deny]`. Neither skill applies anything without your explicit, per-item approval --
  no automation makes that judgment call for you.

More automation is planned over time to tighten this loop further; until then, a short
recurring review is the reliable safeguard.

## Maintaining your toolguard configuration

Over time your rules accumulate and drift. A little upkeep keeps the config readable,
reviewable, and trustworthy -- which is itself a security property: rules you cannot quickly
read are rules you cannot confidently audit.

- **Keep rules sorted.** Sorted allow/deny lists are far easier to scan, diff, and audit, and
  they make duplicates obvious. Set `auto_sort_on_migrate = true` so the migration tool sorts
  on every run (see [Config Sync](config-sync.md#auto-migration)), or sort by hand when you
  edit.
- **Consolidate similar rules into fewer regex/glob rules.** A long run of near-identical
  entries (`Bash(git status:*)`, `Bash(git log:*)`, `Bash(git diff:*)`, ...) is better
  expressed as one anchored pattern, e.g. `Bash([regex]^git (status|log|diff|branch)\b)`. Ask
  Claude to run the **[maintenance skill](skills.md#maintenance)** for this -- it groups rules
  into command families, proposes consolidations with a plain before/after, and certifies each
  proposal (parses, passes the audit, replays cleanly against your own history) before you
  approve anything. `toolguard-migrate --dry-run` also flags duplicates, supersets, and similar
  clusters as a lighter-weight check (see
  [Config Sync](config-sync.md#similarity-detection-and-duplicate-removal)).
  **Consolidate scope, not breadth:** replace several narrow rules with one rule that covers
  exactly the same commands -- do not collapse them into something broader (e.g. `Bash(git:*)`,
  which would also allow `git push` and `git reset --hard`). See
  [Permission Patterns](permission-patterns.md) for the syntax.
- **Manage divergence; do not fight it.** New allows will keep landing in native
  `settings.local.json` as you work -- that is unavoidable. Reconcile them into
  `toolguard_hook.toml` periodically with the migration tool rather than letting two sources
  drift (see [Config Sync](config-sync.md)).
- **Promote rules up the hierarchy; keep the project level clean.** Rules that apply
  everywhere -- general dev tooling, baseline safety denies, and especially `[hard_deny]` --
  belong at the **user level** (`~/.claude/toolguard_hook.toml`), not copied into every
  project. Keep each project's `.claude/toolguard_hook.toml` focused on what is genuinely
  project-specific. More-specific-wins still lets a project override a user-level rule when it
  truly needs to (see [the hierarchy](configuration.md#configuration-hierarchy)). A lean,
  project-focused config is easier to review and means fewer places to update a shared rule.
- **Let the security-audit skill review the rules, not just an ad hoc prompt.** Ask Claude to
  run the **[security-audit skill](skills.md#security-audit)** rather than freehand "review my
  config" -- it runs a deterministic analyzer first (over-broad allows, duplicates, risky
  patterns, missing safety denies, ranked by severity), then optionally a deeper judgement-based
  pass on top, so you get mechanical findings and AI judgement clearly separated instead of one
  undifferentiated opinion. Treat its output as informed advice, not an automatic fix: you make
  the final call, because the rules are **your** security policy. A finding you've deliberately
  accepted can be marked `#NOSECURITY: <reason>`, which labels the finding as accepted and sorts
  it last -- it is still listed and still counted, by design (see
  [Maintenance & Audit Skills](skills.md)).
- **Watch for stray rules from hasty permission answers.** A quick "Yes, and don't ask again"
  during a flow can add an allow that is broader than you intended (or that you would not have
  approved on reflection). These land in `settings.local.json` exactly like any other
  divergence, so when you run `toolguard-migrate --dry-run` (or the maintenance skill), scan the
  newly accumulated allows specifically and drop any you did not mean to grant before folding
  the rest in.
- **Comment your rules to record intent.** TOML supports comments -- use them to note *why* a
  rule exists (and when it was added), especially for `[regex]` patterns and `[hard_deny]`
  entries whose purpose is not obvious from the pattern alone. A rule whose reason has been
  forgotten tends to get either blindly kept or wrongly removed; a one-line comment prevents
  both and makes review faster.
- **Keep the config in version control and review the diffs.** Commit `toolguard_hook.toml`
  (and any ancestor-level configs) to git and review changes as diffs -- an over-broad or
  stray rule is far easier to catch in a diff than in a full file. Caveats: `settings.local.json`
  is typically git-ignored and machine-local, and you should never commit secrets or anything
  under `~/.claude` into a project repository.
- **Practice defense in depth -- do not rely on the absence of an allow.** Add explicit `deny`
  (or [`[hard_deny]`](configuration.md#configuration-reference)) rules for destructive
  operations even when you are allow-listing, so a future broad allow, a mistaken "always
  allow," or a parsing gap cannot silently expose them. See
  [Recommended deny patterns](#recommended-deny-patterns) for a starting set.
- **Use the `ask` tier for impactful-but-reversible operations.** Reserve `allow` for routine,
  safe commands and `deny`/`[hard_deny]` for the clearly dangerous; put the in-between
  (database migrations, `cp`/`mv`, network calls, package installs) in `ask` so you stay in the
  loop without blocking the workflow. The `ask` list is easy to overlook -- it is often the
  right home for a rule you are tempted to either fully allow or fully deny.

## Recommended deny patterns

**Always include these in your deny list**:

```toml
[permissions]
deny = [
    # Destructive commands
    "Bash(rm -rf:*)",
    "Bash([regex]rm\\s+-rf\\s+/)",
    "Bash(dd:*)",

    # Privilege escalation
    "Bash(sudo:*)",
    "Bash(su:*)",

    # Sensitive files -- within whatever project is active (see the anchoring note below)
    "Read(**/.env)",
    "Read(**/.env.*)",
    "Read(**/.aws/**)",
    "Read(**/.ssh/**)",
    "Write(**/.env)",
    "Write(**/.env.*)",
    "Write(**/.aws/**)",
    "Write(**/.ssh/**)",
    "Edit(**/.env)",
    "Edit(**/.env.*)",
    "Edit(**/.aws/**)",
    "Edit(**/.ssh/**)",

    # The same sensitive files, home-anchored -- protects them regardless of which
    # project is active (see the anchoring note below)
    "Read(~/.env)",
    "Read(~/.env.*)",
    "Read(~/.aws/**)",
    "Read(~/.ssh/**)",
    "Write(~/.env)",
    "Write(~/.env.*)",
    "Write(~/.aws/**)",
    "Write(~/.ssh/**)",
    "Edit(~/.env)",
    "Edit(~/.env.*)",
    "Edit(~/.aws/**)",
    "Edit(~/.ssh/**)",

    # System directories
    "Write(/etc/**)",
    "Write(/usr/**)",
    "Write(/bin/**)",
    "Write(/sbin/**)"
]
```

**Why both forms of the sensitive-file patterns are needed.** A relative pattern (`**/.ssh/**`,
not starting with `/` or `~`) is anchored to the *active project's root* before matching -- it
only protects a `.ssh`/`.env`/`.aws` path that lives **inside the current project's directory
tree**. It does **not** protect `~/.ssh/id_rsa` while you are working in some other project
elsewhere on disk. A home-anchored pattern (`~/.ssh/**`) is left unmodified and always resolves
to the real home directory, so it protects those paths **no matter which project is active**.
For real protection of your actual secrets -- not just a copy of them that happens to live inside
whatever repo you're in -- include both forms, especially at the user level where "whatever
project is active" varies session to session. (This was found the hard way: an install once
added only the relative patterns at user scope and `~/.ssh/id_rsa` was not denied until the
home-anchored patterns were added by hand.)

**Why `Write` and `Edit` are both listed for every family.** `Edit` modifies a file in place, so a `Write`-only deny still leaves `~/.ssh/authorized_keys` appendable and `~/.env.local` plantable. Covering both verbs across all four families does mean `.env.example` and its siblings are write-denied as well as read-denied; if you need one, add it to the narrow `hard_deny.allow` carve-out rather than trimming the deny list.

For the strongest protection, mirror the most critical of these into
[`[hard_deny]`](configuration.md#configuration-reference) at the user level so no project can
weaken them. `toolguard-install seed-hard-deny` (see the guided install runbook) adds exactly
this canonical set -- both forms -- to `[hard_deny]` for you.
