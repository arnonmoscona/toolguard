# Manual tests

Tests whose subject is **Claude Code itself**, not toolguard. They drive a real `claude -p` and cannot run in the unit suite, so they are run deliberately -- after a Claude Code upgrade that might change permission handling, or whenever a documentation claim depends on the answer.

Every claim these tests establish carries the Claude Code version it was measured against. A permission-behaviour claim is a claim with a date on it.

## `ask_binding_probe.sh` -- does a PreToolUse "ask" bind in every permission mode?

```bash
bash test/manual/ask_binding_probe.sh              # uses `toolguard` from PATH
bash test/manual/ask_binding_probe.sh ~/.local/bin/toolguard
```

**Why it exists.** toolguard's whole failure story rests on ASK being a real stop. `docs/security.md` tells you that a `[hard_deny]` lost to a TOML syntax error degrades to "blocked pending an answer", not to "allowed" -- and if an ASK were ignored in an unattended mode, that sentence would be false in exactly the mode people run inside containers, silently.

### Measured 2026-09-07, Claude Code 2.1.260, toolguard 0.5.1

| permission mode | toolguard rule | toolguard decided | command executed? |
|---|---|---|---|
| `default` | ask | ask | no |
| `bypassPermissions` | ask | ask | **no** |
| `bypassPermissions` | allow | allow | **yes** (control) |
| `acceptEdits` | ask | ask | no |
| `dontAsk` | ask | ask | no |

**A toolguard ASK binds in every mode, `bypassPermissions` included.**

### Read the control first

Case 3 is not decoration. An absent `probe_result.txt` proves an ASK bound only once something has proved the file *can* be produced under that mode. Without case 3, five absent files are equally consistent with "the harness never worked".

That is not hypothetical: the first version of this harness put the rules at the **top level** of `toolguard_hook.toml` instead of under `[permissions]`, where they are silently inert. Every case agreed, no rule had matched in any of them, and the output looked like a clean result. What caught it was printing what toolguard actually decided next to whether the command ran -- which is why the script emits that provenance from inside each measurement rather than from a separate check.

### What this does NOT establish

- Nothing about Claude Code's **auto-mode classifier**. This is a `PreToolUse` hook: it sees what toolguard decided, never the classifier's own verdict on the same call.
- Nothing about a hook `"allow"`. The documented critical-path circuit breaker means a hook allow is not universally honoured; this probe does not measure that.
- The `-p` (headless) path only. A call that would prompt is denied there rather than prompting. An interactive session prompts instead -- the same binding, a different surface.

### Prior claim this replaced

The documentation was briefly changed to hedge about `bypassPermissions`, on the reasoning that Claude Code's *actions no mode auto-approves* list names a native `ask` rule and a `PreToolUse` hook's `"allow"` but never a hook-forced prompt, while the mode itself "disables permission prompts and safety checks". That inference was **wrong**, and this test is what refuted it. An omission from a documentation list is not evidence about behaviour.
