# Auto-mode with toolguard

**Auto-mode** here means Claude Code's own `auto` permission mode specifically -- one of six
mode values (`default`, `acceptEdits`, `plan`, `auto`, `dontAsk`, `bypassPermissions`; see
[Choose a permission mode](https://code.claude.com/docs/en/permission-modes)) and the only one
with a second model, the classifier, reviewing actions in place of a prompt. toolguard's
`*_in_auto_mode` settings key on that exact value (`permission_mode == "auto"`) and do nothing
under any other mode.

**Running `acceptEdits`, `dontAsk`, or `bypassPermissions` (`--dangerously-skip-permissions`)
instead?** None of those has a classifier, so the `_in_auto_mode` settings on this page have
nothing to hand off to and never fire there -- toolguard's own fallback decision is governed
by the BASE `no_match_fallback`/`undecidable_fallback` settings, exactly as in an interactive
session. Configure the base settings directly instead (see [Configuration: No-match
fallback](configuration.md#no-match-fallback) and [Undecidable
fallback](configuration.md#undecidable-fallback)) if you want the same review-with-a-warning
tradeoff this page recommends for `auto` mode.

**What does NOT change with the mode is whether toolguard's own `ask` stops the call. It
does, in every mode** -- measured against Claude Code 2.1.260 on 2026-09-07 by driving a real
session in each one, with a control confirming the same command ran under `bypassPermissions`
when the rule allowed it. `dontAsk` denies outright rather than waiting for an answer, which
is fail-closed by a different route; the rest stop and wait. So none of these modes is a way
to get past a toolguard `ask`, and the choice between them is about Claude Code's *own*
prompting, not about toolguard's authority. Re-run the check after a Claude Code upgrade:
[`test/manual/ask_binding_probe.sh`](../test/manual/README.md).

This page is about running toolguard *underneath* `auto` mode, not toolguard's own
[Takeover Mode](takeover-mode.md) (a related but different mechanism -- see [How this differs
from Takeover Mode](#how-this-differs-from-takeover-mode)).

> Read this whole page before turning this on. It describes a real, named, supportable
> configuration -- but it trades away real protection for unattended operation, and you
> should make that trade with open eyes.

## Division of labour: toolguard vs. auto-mode guidance

Once Claude Code enters `auto` mode, two different mechanisms can gate a call: toolguard's
rules, and Claude Code's own classifier (see
[Choose a permission mode](https://code.claude.com/docs/en/permission-modes)). Under the
OTHER modes that reduce or remove Claude Code's own prompting (`acceptEdits`, `dontAsk`,
`bypassPermissions`), there is no classifier at all, so toolguard's rules are the only side
of this table that is present -- see the top of this page for what to configure there
instead. They decide by different means, and each is strong exactly where the other is
blind:

| | Decides by | Strong where | Blind where |
|---|---|---|---|
| **toolguard** | Exact pattern match against configured rules | Anything expressible as a rule -- exact, testable, versioned, auditable | Anything it cannot parse or pattern: foreign inline code, heredocs, undecomposable control structures |
| **Auto-mode guidance** (the classifier) | Semantic judgement of the pending action | Undecomposable blobs, intent, novel shapes no rule was ever written for | Exactness, repeatability, auditability -- its calls are not versioned rules you can review offline |

**These are complementary halves with inverted strengths, not two implementations of one
control.** toolguard's blind spot is constitutive, not a missing feature: a compound command
it cannot decompose, a heredoc, foreign inline code, a script whose contents it never sees.
The [ASK floor](configuration.md#undecidable-fallback) and `undecidable_fallback` exist
precisely to *announce* that blind spot -- toolguard saying "I cannot read this," rather than
guessing.

Every `_in_auto_mode` setting on this page, and `auto_mode_behavior` on an individual rule
(see [Configuration: Per-rule auto-mode behavior](configuration.md#per-rule-auto-mode-behavior)),
is therefore a **handoff point**, not an "auto-mode variant" of a base setting: it declares how
much you trust the classifier for one specific class of case toolguard cannot decide on its
own. Setting one does not make toolguard smarter about auto mode.

**The design smell to watch for: "make toolguard smarter so it can handle this."** If what is
being asked for requires reading intent rather than matching a pattern, the answer is trusting
the classifier for that case -- not a cleverer rule. toolguard's exactness is the property
worth keeping; stretching it to cover judgement calls trades that away.

## The honest tradeoff

**Naked auto-mode (no toolguard at all): zero prompts, zero governance.** Whatever Claude
decides to run, executes -- unreviewed, unlogged, with nothing standing between the model's
decision and your system.

**Auto-mode with toolguard registered: still zero prompts, but real enforcement underneath.**
Toolguard's PreToolUse hook fires on every governed tool call regardless of Claude Code's own
`permission_mode` -- hook registration and Claude's native prompting are independent
mechanisms. So even while Claude Code itself stays silent, toolguard still:

- **Blocks** anything matching an explicit `deny` rule.
- **Blocks unconditionally** anything matching a [`hard_deny`](configuration.md#configuration-reference)
  rule -- no level, no auto-mode, no override can weaken this floor.
- **Allows** anything matching an explicit `allow` rule.
- Falls back to whatever `no_match_fallback` says for anything that matches *nothing*.

That last case is the crux of this page.

## Why `no_match_fallback = "ask"` (the normal default) doesn't work here

toolguard's own default fallback is `ask` -- a sensible default for interactive use, but it
is a dead end in an unattended run: there is no one there to answer, so an unmatched command
just hangs. `deny` avoids hanging but breaks any workflow you have not already fully
enumerated in your rules, which most real setups have not.

## The recommended configuration for this specific case

**Prefer the auto-mode handoff point over loosening the base setting.** `no_match_fallback_in_auto_mode` (see [Configuration: Fallback settings in auto mode](configuration.md#fallback-settings-in-auto-mode)) resolves in place of `no_match_fallback` only when Claude Code's own `permission_mode` is actually its auto mode -- so the SAME project stays strict (`ask`, or whatever you have set) the moment you go back to an interactive session, with nothing to remember to tighten back up:

```toml
no_match_fallback_in_auto_mode = "allow_with_warning"
```

This lets anything unmatched proceed (so the session does not stall) **only while `permission_mode` is auto**, and logs every one of those decisions to `logs/toolguard-YYYY-MM-DD.md` -- each carrying the command and `[fallback allow -- no rule matched]`, so you have a full, reviewable trail of everything that ran *without* an explicit rule behind it. Under auto mode every one of them is also appended to the [auto-mode trace](#the-auto-mode-trace-log) as a second, machine-readable record. Your explicit `allow`/`deny` rules and your `hard_deny` floor are still fully enforced; only the *unmatched* case, and only under auto mode, is loosened.

**`allow` (and its `allow_with_no_warnings` alias) is a defensible choice here, and the difference is smaller than it looks.** Measured 2026-09-07 against toolguard 0.7.0, driving the same unmatched command under auto mode with each value: the daily log entries are **identical** -- same `EXECUTED` status, same command, same `[fallback allow -- no rule matched]` -- and both write the auto-mode trace. **The review trail is the same either way.** What `allow_with_warning` adds is a warning on **stderr**, in the session, not a mark in the log.

So choose on whether anyone will see that warning. In a session a human is watching -- auto mode with someone at the keyboard -- it is a useful nudge to go write a rule, which is why it suits a **user-level** default that every project inherits. In a genuinely unattended run it is noise nobody reads. Neither value costs you the record.

**Older configs that instead loosen the base `no_match_fallback`/`[takeover_mode]` form directly still work** -- nothing here deprecates that -- but they loosen it for every `permission_mode`, not only the unattended one, which is a wider blast radius than this page has ever actually needed. Prefer the `_in_auto_mode` setting for new configurations.

**This is deliberately not the general recommendation.** Outside of unattended auto-mode,
prefer the stricter `ask` default -- `allow_with_warning` is a named exception for this one
use case, not a setting to reach for generally.

**Say this plainly to yourself before enabling it:** `allow_with_warning` is strictly better
than naked auto-mode (real logging, a real `hard_deny` floor, real explicit `deny` rules that
still hold) -- but it is not a substitute for a well-built rule set. Anything that falls
through to the fallback executes *silently*, and you only find out by reading the logs
afterward. This is a **detective control for the unmatched case, not a preventive one.**

**`no_match_fallback_in_auto_mode` is not the only fallback that can hang an unattended run.** `undecidable_fallback_in_auto_mode` -- the same handoff point for commands toolguard cannot safely parse at all (foreign inline code, heredocs, process substitution), rather than commands that simply match no rule -- has the exact same dead-end problem in auto-mode if left unset (it then defers to `undecidable_fallback`, which defaults to `ask`). Loosening `no_match_fallback_in_auto_mode` alone does not touch it. `toolguard-audit` raises a HIGH finding (`loose-undecidable-fallback-in-auto-mode`) whenever the auto-mode value is looser than the base one, whichever loose value you choose, which is a signal to weigh the same tradeoff deliberately rather than by default. Its no-match counterpart (`loose-no-match-fallback-in-auto-mode`) fires on the same condition at LOW. See [Configuration: Fallback settings in auto mode](configuration.md#fallback-settings-in-auto-mode) and [Security: Loosening the undecidable fallback](security.md#loosening-the-undecidable-fallback).

## Recommended checklist before you turn this on

1. **Build out explicit `allow`/`deny` rules first.** See
   [Permission Patterns](permission-patterns.md). The fewer commands fall through to the
   fallback, the less this tradeoff matters in practice.
2. **Seed `hard_deny` for your non-negotiables** -- secrets, toolguard's own state directory,
   anything that must never be silently allowed regardless of mode. See
   [Recommended deny patterns](security.md#recommended-deny-patterns). These hold even under
   `allow_with_warning`.
3. **Set `no_match_fallback_in_auto_mode = "allow_with_warning"` rather than the base
   setting** -- it only takes effect while `permission_mode` is actually auto, so the same
   project stays strict for every other session automatically.
4. **Actually read the logs.** This configuration's whole safety story depends on you
   periodically reviewing `logs/toolguard-YYYY-MM-DD.md` for what ran unmatched, not just
   trusting that nothing bad happened.
5. There is nothing to remember to tighten back up when you stop running auto-mode: the
   `_in_auto_mode` setting simply stops applying the moment `permission_mode` is no longer
   auto. (If you instead loosened the base `no_match_fallback`, tighten that back to `ask`,
   or `deny` once your rules are exhaustive -- there is no reason to keep it loose once Claude
   Code is prompting natively again.)

Toolguard's logs also record Claude Code's own `permission_mode` for every decision. As of the `_in_auto_mode` settings above, this is no longer purely diagnostic: when one of them is configured and the recorded mode is auto, it is also what decided the two fallback cases those settings cover. It remains diagnostic-only for everything else the log records, and you can audit exactly which mode a given command ran under after the fact.

## `auto_mode_behavior` and command prefixes

A rule carrying [`auto_mode_behavior`](configuration.md#per-rule-auto-mode-behavior) is matched under its **effective** group when `permission_mode` is auto -- that is the point of the key, and it is what makes an `ask` rule declaring `allow` compete with an allow's precedence rather than an ask's. One consequence is easy to miss: **the group also decides how command prefixes are handled, so a migrated rule can cover a slightly different set of commands in each mode.**

Prefix handling is per-group in Claude Code, and toolguard follows it (checked against [the permissions docs](https://code.claude.com/docs/en/permissions), 2026-09-08):

| | leading assignment (`FOO=bar cmd`) | wrappers (`timeout 30 cmd`) |
|---|---|---|
| `allow`, and `[hard_deny]`'s allow carve-out | matched past **only** for known-safe variables | matched past |
| `ask`, `deny`, `[hard_deny]`'s deny | matched past for **any** variable | matched past |

**The asymmetry is deliberate, not an oversight.** An allow rule should not match past `LD_PRELOAD=evil.so npm test`, because the assignment changes what actually runs and the visible command is no longer the whole story. A deny or ask rule matches past any assignment for the mirror-image reason: there you want to catch the command however it is dressed.

**Which migrations to watch: those with `allow` on exactly one side.** `ask -> allow`, `deny -> allow`, `allow -> ask` and `allow -> deny` all cross the line in the table above, so a command with a leading assignment can match in one mode and not the other. `ask -> deny` and `deny -> ask` are unaffected -- both groups treat prefixes identically.

**Nothing here fails open**, which is why this is a note rather than a warning. The groups that do *not* match past an arbitrary assignment are exactly the permission-**granting** ones, so a missed match withholds permission rather than conceding it. What you get instead is a rule that quietly stops covering what you expected: the command falls through to the fallback, and appears in the [auto-mode trace](#the-auto-mode-trace-log) under `fallback_cause: "no_match"` -- which reads as *"write a rule for this"* when the rule already exists.

**If a rule must cover a command with a leading assignment in both modes, write it as a regex.** A `[regex]` pattern is matched against the raw command text with no prefix handling at all, so it behaves identically whatever group the rule is matched under:

```toml
[permissions]
ask = [
    # native pattern: does not cover `PYTHONPATH=. uv run python x.py` under auto
    { match = "Bash(uv run python:*)", auto_mode_behavior = "allow" },

    # regex: covers it in both modes, because you decide what the prefix may be
    { match = "Bash([regex]^(?:[A-Za-z_][A-Za-z0-9_]*=\\S* )*uv run python\\b)", auto_mode_behavior = "allow" },
]
```

Writing the prefix into the pattern makes it explicit, which is the trade: you give up native's built-in judgement about which prefixes are safe, and take responsibility for it yourself. Prefer the native form unless a real command is falling through.

## The auto-mode trace log

Separately from the daily decision log above, every time a call resolves through a fallback
(`no_match_fallback`/`undecidable_fallback`, in either their base or `_in_auto_mode` form)
while `permission_mode` is auto, toolguard appends one record to
`logs/toolguard-automode-YYYY-MM-DD.jsonl`. It is a **read-only side channel**: nothing in the
decision path reads it, and a write failure here never changes a verdict.

Each record's `fallback_cause` is a **triage code** -- each value implies a different
response to a case you decide, in retrospect, you do not like:

- `"no_match"` -- toolguard read the command fine; no rule covered it. Addressable by writing
  a rule.
- `"undecidable"` -- toolguard could not read the target at all. No rule can ever cover this;
  the [program-source constraint](configuration.md#program-source-constraint) or an
  `_in_auto_mode` handoff setting are the deliberate ways to loosen it instead.
- `"parse_failure"` -- toolguard could not read its own configuration. Fix the config, not a
  rule.
- `"unknown"` -- not determinable from the information available (most often a compound
  command whose several allowed leaves disagree on a cause). Investigate the case rather than
  assuming either of the answers above.

**What this log does not answer.** It is written from a `PreToolUse` hook, so it records what
toolguard itself deferred to a fallback -- never whether Claude Code's own auto-mode
classifier subsequently allowed or blocked the call. Correlating the two means reading both
this log and Claude Code's own audit trail.

## How this differs from Takeover Mode

[Takeover Mode](takeover-mode.md) solves a different problem: it lets you give Claude Code
*blanket* native allows (so it never shows its own prompts) while toolguard silently
substitutes its own real rules underneath, stripping the blanket allows as it loads them.
Auto-mode, as used on this page, is about Claude Code's own `permission_mode` bypassing
prompts directly -- native settings are not necessarily blanket allows at all. The two can be
combined, but they address different layers: Takeover Mode replaces *what Claude Code sees*;
this page is about what happens when Claude Code *isn't asking in the first place*. Read
both before combining them.
