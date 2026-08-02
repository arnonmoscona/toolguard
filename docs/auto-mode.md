# Auto-mode with toolguard

**Auto-mode** here means Claude Code's own unattended modes -- `acceptEdits`,
`bypassPermissions`, or similar -- where Claude Code stops asking for permission on its own,
regardless of what your native `settings.json` allow/deny rules say. This page is about
running toolguard *underneath* that, not toolguard's own [Takeover Mode](takeover-mode.md)
(a related but different mechanism -- see [How this differs from Takeover Mode](#how-this-differs-from-takeover-mode)).

> Read this whole page before turning this on. It describes a real, named, supportable
> configuration -- but it trades away real protection for unattended operation, and you
> should make that trade with open eyes.

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

For a genuinely unattended auto-mode session, set:

```toml
[takeover_mode]
no_match_fallback = "allow_with_warning"
```

This lets anything unmatched proceed (so the session does not stall), but logs every one of
those decisions to `logs/toolguard-YYYY-MM-DD.md` with a warning marker -- giving you a full,
reviewable trail of everything that ran *without* an explicit rule behind it. Your explicit
`allow`/`deny` rules and your `hard_deny` floor are still fully enforced; only the *unmatched*
case is loosened.

**Do not substitute `no_match_fallback = "allow"` (or its `allow_with_no_warnings` alias)
here.** Those values exist for a genuinely different situation -- see
[Configuration: No-match fallback](configuration.md#no-match-fallback) -- and produce NO log
entry for the unmatched case at all. This whole recommendation's safety story is "everything
unmatched is logged so you can review it later"; `allow` quietly deletes that review trail
while looking like a simpler version of the same setting. Use `allow_with_warning`.

**This is deliberately not the general recommendation.** Outside of unattended auto-mode,
prefer the stricter `ask` default -- `allow_with_warning` is a named exception for this one
use case, not a setting to reach for generally.

**Say this plainly to yourself before enabling it:** `allow_with_warning` is strictly better
than naked auto-mode (real logging, a real `hard_deny` floor, real explicit `deny` rules that
still hold) -- but it is not a substitute for a well-built rule set. Anything that falls
through to the fallback executes *silently*, and you only find out by reading the logs
afterward. This is a **detective control for the unmatched case, not a preventive one.**

**`no_match_fallback` is not the only fallback that can hang an unattended run.**
`undecidable_fallback` -- a separate, top-level setting for commands toolguard cannot safely
parse at all (foreign inline code, heredocs, process substitution), rather than commands that
simply match no rule -- also defaults to `ask` and has the exact same dead-end problem in
auto-mode. Loosening `no_match_fallback` alone does not touch it. `toolguard-audit` raises a
HIGH finding if you loosen it to `allow_with_warning`, which is a signal to weigh the same
tradeoff deliberately rather than by default. See
[Configuration: Undecidable fallback](configuration.md#undecidable-fallback) and
[Security: Loosening the undecidable fallback](security.md#loosening-the-undecidable-fallback).

## Recommended checklist before you turn this on

1. **Build out explicit `allow`/`deny` rules first.** See
   [Permission Patterns](permission-patterns.md). The fewer commands fall through to the
   fallback, the less this tradeoff matters in practice.
2. **Seed `hard_deny` for your non-negotiables** -- secrets, toolguard's own state directory,
   anything that must never be silently allowed regardless of mode. See
   [Recommended deny patterns](security.md#recommended-deny-patterns). These hold even under
   `allow_with_warning`.
3. **Scope `no_match_fallback = "allow_with_warning"` narrowly** -- to the level/session where
   you actually run auto-mode, not as a blanket default across every project.
4. **Actually read the logs.** This configuration's whole safety story depends on you
   periodically reviewing `logs/toolguard-YYYY-MM-DD.md` for what ran unmatched, not just
   trusting that nothing bad happened.
5. If you stop running auto-mode, tighten `no_match_fallback` back to `ask` (or `deny` once
   your rules are exhaustive) -- there is no reason to keep the looser fallback once Claude
   Code is prompting natively again.

Toolguard's logs also record Claude Code's own `permission_mode` for every decision
(diagnostic only today -- it does not change enforcement), so you can audit exactly which
mode a given command ran under after the fact.

## How this differs from Takeover Mode

[Takeover Mode](takeover-mode.md) solves a different problem: it lets you give Claude Code
*blanket* native allows (so it never shows its own prompts) while toolguard silently
substitutes its own real rules underneath, stripping the blanket allows as it loads them.
Auto-mode, as used on this page, is about Claude Code's own `permission_mode` bypassing
prompts directly -- native settings are not necessarily blanket allows at all. The two can be
combined, but they address different layers: Takeover Mode replaces *what Claude Code sees*;
this page is about what happens when Claude Code *isn't asking in the first place*. Read
both before combining them.
