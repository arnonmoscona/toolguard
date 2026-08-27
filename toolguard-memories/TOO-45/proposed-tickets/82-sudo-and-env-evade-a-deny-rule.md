---
title: sudo and env evade a deny rule, and they are not in the wrapper family that
  excuses it
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/82-sudo-and-env-evade-a-deny-rule
---

# `sudo rm -rf /tmp/x` does not match `deny Bash(rm:*)`

**Measured 2026-08-19** while doing ticket 77's phase-1 grammar work, by the agent doing it.

```
rule:     deny Bash(rm:*)
command:  sudo rm -rf /tmp/x   ->  EVADES
command:  env  rm -rf /tmp/x   ->  EVADES
```

Ticket 77 lists a "wrapper" family — `timeout`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, zsh `noglob` — as sharing its shape. **`sudo` and `env` are not in that list and are not the same thing.** Those wrappers adjust scheduling or buffering. `sudo` escalates privilege and `env` rewrites the environment, so of every prefix that can hide a command from its own deny rule, these two hide the versions that matter most.

A rule written `deny Bash(rm:*)` by someone protecting a machine does not fire on the privileged form of exactly that command.

## Why it is filed separately from 77

Ticket 77's scope is a leading `VAR=value` assignment, and its phase-1 grammar work introduced `assignment_prefix` + `command_word`. The agent that built it observed that **this is precisely the seam a `wrapper_prefix` would reuse** — so the fix is cheap once 77 lands, and doing it inside 77 would have widened a security change mid-flight.

Filing it separately also keeps the severity legible. 77 is about a marker convention costing an allow rule and a `FOO=1` prefix dodging a deny. **This is `sudo` dodging a deny**, which is a different sentence to read on a Monday.

## Design note, inherited from 77 and not to be re-derived

The same asymmetry applies and for the same reason:

- **deny / hard_deny / ask** — match the stripped spelling **as an additional variant alongside the raw one**, so a rule deliberately keyed on `sudo` keeps working.
- **allow** — do **not** strip. `sudo` in particular must never be looked past when granting; an `allow Bash(rm:*)` rule must not become an allow for `sudo rm`.

Note the allow side is not merely "stricter than native" here — it is the whole point. Stripping `sudo` for allow would convert every unprivileged allow rule into a privileged one.

**And 77's own lesson applies**: the stripped spelling must be visible to **every pattern type**, not only DEFAULT. `_command_variants` feeds DEFAULT matching alone, so a variant added there leaves `[regex]`, `[glob]` and `[native]` denies bypassable.

---

# DISPOSITION 2026-08-20 — THIS TICKET'S PREMISE IS WRONG. `sudo` and `env` are NOT defects.

**Arnon challenged the premise and was right.** *"You are talking specifically about the native syntax rule. That is simply how claude works, no? What does the claude documentation say about this? I would buy your argument only on compatibility grounds. Otherwise - those cases should be framed in a regex rule if you want safety. Check the docs."*

Checked. `https://code.claude.com/docs/en/permissions.md`, section **Wrappers**, verbatim:

> *"Before matching Bash rules, Claude Code strips a fixed set of wrappers, so a rule like `Bash(npm test *)` also matches `timeout 30 npm test`. **The stripped wrappers are `timeout`, `time`, `nice`, `nohup`, and `stdbuf`, plus the shell builtins `command` and `builtin`, and zsh's `noglob`.** Each runs its argument as the actual command. Two related forms aren't stripped: the query form `command -v` … and zsh's `nocorrect`."*
>
> *"Bare `xargs` is also stripped, so `Bash(grep *)` matches `xargs grep pattern`. Stripping applies only when `xargs` has no flags."*
>
> *"**This wrapper list is built in and is not configurable.** Development environment runners such as `direnv exec`, `devbox run`, `mise exec`, `npx`, and `docker exec` are not in the list. … To approve work inside an environment runner, **write a specific rule that includes both the runner and the inner command**."*

**`sudo` and `env` appear nowhere in the stripped list.** So `deny Bash(rm:*)` failing to match `sudo rm -rf x` or `env rm -rf x` is **native's own behaviour, faithfully reproduced** — not a bypass toolguard introduced. The documentation's own prescription for this class is exactly Arnon's: name the wrapper in the rule, or reach for `[regex]`.

## The real defect is the opposite one, and it is on the compatibility ground Arnon named

Measured 2026-08-20 against `deny Bash(rm:*)`:

| prefix | native | toolguard | |
|---|---|---|---|
| `timeout 30`, `time`, `nice -n 5`, `nohup`, `stdbuf -o0`, `command`, `builtin`, `noglob`, bare `xargs` | **strips → matches** | does not match | **9 divergences** |
| `sudo`, `env`, `command -v`, `nocorrect`, `npx`, `docker exec`, `watch`, `setsid`, `ionice`, `flock`, `xargs -n1` | does not strip | does not match | agrees (11) |

**toolguard strips no wrapper at all.** The eleven agreements are right by accident rather than by mechanism — there is no list, so nothing can be on the wrong side of it.

The divergence runs **both ways and is not primarily a safety issue**: a `deny` written `Bash(rm:*)` under-denies `timeout 30 rm -rf x`, and an `allow` written `Bash(npm test *)` under-allows `timeout 30 npm test`, costing a spurious prompt on the exact idiom the native docs use as their worked example.

## Two errors of mine that this correction retracts

1. **I proposed fixing the `env` case on safety grounds and Arnon initially accepted it.** That instruction should be reversed: `env` is faithful behaviour, and "fixing" it would be a deliberate divergence from native, adopted for safety. Defensible as a policy, but it is a policy decision, not a bug fix, and it was not presented as one.
2. **The "design note, inherited from 77 and not to be re-derived" above is WRONG for wrappers.** It says *never strip for allow*. That asymmetry is documented for **leading assignments** specifically (*"An allow rule won't match past an assignment of any other variable. A deny or ask rule matches past any leading assignment"*) — and does **not** extend to wrappers, whose documented example is itself an **allow** rule. Marking it "not to be re-derived" would have propagated the error straight into the implementation.

**Corrected scope**: implement native's wrapper list, closed and non-configurable as native has it, applied symmetrically to allow and deny — because that is what native does. `sudo` and `env` stay unstripped. 77's genuinely transferable lesson still holds: the stripped spelling must reach **every pattern type**, since `_command_variants` feeds DEFAULT alone.

## Second occurrence of the same review gap, within one day

The resume note records ticket 77's native-behaviour claim surviving two blinded reviews *"because reviewers check prose against this repository's code and nothing re-reads external sources."* **This is the same failure, one day later, in the same subject area** — and again it was Arnon's question, not a review or a metric, that caught it. A claim about an external, versioned specification cannot be validated against this repo at all. It needs the source fetched, quoted, and dated in the ticket.
