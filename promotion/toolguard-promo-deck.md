# toolguard

**Claude permissions, done right.**

Claude Code's native permissions mix deterministic rules combined with an opaque auto-mode classifier. toolguard replaces both with one engine — consistent, and capable of rules native can't even express.

[Install in one message](#try-it-in-one-message) · [github.com/arnonmoscona/toolguard](https://github.com/arnonmoscona/toolguard)

<details>
<summary><strong>😩 The native system doesn't consistently do what it says</strong></summary>

- Re-prompts for permissions already granted — can stall an unattended session
- `**` globstar is broken for `Write`/`Edit`
- Compound commands (`&&`, heredocs, subshells) get only partial support — not real parsing
- No idea why something was allowed *or denied* — just a session transcript nobody reads, no dedicated decision log

</details>

<details>
<summary><strong>✅ toolguard fixes all of it</strong></summary>

| | Native | toolguard |
|---|---|---|
| Compound commands | partial support | more complete support — can't parse everything (no magic) |
| Globstar on Write/Edit | broken | works |
| Pattern types | prefix matching only | prefix (Claude-compatible) + regex + true glob |
| Config hierarchy | hierarchical, no hard floor — opaque to debug | hierarchical + `[hard_deny]` floor, full provenance |
| Decision log | none — search the transcript | dedicated log, every decision |
| Rule maintenance | manual, usually skipped | automated audit + consolidation skills |

</details>

<details>
<summary><strong>🔌 It's Claude-Code-native, not another tool to learn</strong></summary>

- **Same syntax at the core** — `Bash(git log:*)` still works exactly like today
- **Extended syntax** (regex, true glob) when prefix matching runs out of road
- **Install by asking Claude**: *"install toolguard from `github.com/arnonmoscona/toolguard` using docs/install.md"* — agent-driven, journaled, reversible
- **Ships as a hook + skills** — `toolguard-security-audit` and `toolguard-maintenance` run themselves, with per-item consent

```bash
# uv tool install alone won't wire the hooks for you — tell Claude instead:
# "install toolguard from https://github.com/arnonmoscona/toolguard using docs/install.md in the repo."
```

</details>

<details>
<summary><strong>🔒 The real risk: nobody maintains their rule set</strong></summary>

**Friction is why people skip permissions entirely.** That's why `--dangerously-skip-permissions` and auto-mode are so common — maintaining a rule set is a chore nobody has time for.

- toolguard reads the docs no human will — **generates, audits, and carefully migrates** your existing rules (flagging the bad ones)
- It handles nuance native prefix-matching structurally cannot, even for complex, common CLIs (see the gh CLI example below)
- Two skills do the upkeep for you — `toolguard-security-audit`, `toolguard-maintenance` — and CLAUDE.md can remind you they exist

</details>

<details>
<summary><strong>📎 For the curious: gh CLI, quantified</strong></summary>

- **61 toolguard rules vs. 197 native rules** — 33 toolguard allow lines ≈ 91 equivalent native rules; 28 toolguard deny lines ≈ 106 equivalent native rules
- Native permissions only do prefix matching — anchored at the start of the command, nothing else
- **State your security stance in one sentence — Claude turns it into a full enforced rule set**, for gh, aws, terraform, kubectl, or anything else you run. toolguard is the *only* practical way to do this.
- See the full generated rule set: [`docs/gh-cli-rules-example.toml`](https://github.com/arnonmoscona/toolguard/blob/master/docs/gh-cli-rules-example.toml)

</details>

<details>
<summary><strong>📎 What native literally cannot express</strong></summary>

Deny any `gh api` call that mutates state — wherever the flag appears:

```
Bash([regex]^(?:\S*/)?gh\s+api\s.*(-X\s|--method(\s|=)))
```

A prefix rule catches `gh api -X:*` but not the equally common `gh api repos/x/y -X DELETE` — the flag can appear anywhere. There's no finite number of native rules that covers it. Native is left with two bad options: allow `gh api:*` wholesale, or deny it wholesale and lose the safe GET case entirely.

**You don't need to write this by hand** — Claude generates it, and the maintenance skill keeps it current. Same story for docker, kubectl, helm, terraform, ansible, vault — **toolguard is the only solution that would work.**

</details>

<details>
<summary><strong>❓ FAQ</strong></summary>

- **Do I have to rewrite all my rules?** No — they're migrated for you.
- **Do I lose auto-mode?** No. It gets better — and better yet soon.
- **What if I change my mind?** Claude rolls back cleanly from the install log. Complex rules get the best native approximation possible — native just can't express everything toolguard can.
- **How do I do X?** Ask Claude — it reads the docs for you. Better yet, it'll just do it for you.
- **What about my privacy?** toolguard is 100% local, zero runtime dependencies, zero network connections.

</details>

<details open>
<summary><strong>🚀 Try it in one message</strong></summary>

> "Install toolguard from `https://github.com/arnonmoscona/toolguard` using `docs/install.md` in the repo."

Claude interviews you about your preferences, then handles install, hook wiring, validation, and rollback if you change your mind.

**[github.com/arnonmoscona/toolguard](https://github.com/arnonmoscona/toolguard)**

</details>
