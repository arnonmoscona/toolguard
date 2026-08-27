---
title: The "deny with a legitimate exception" recipe needs a workable example, and a rule for when it applies
tags: [TOO-45, proposed-ticket, documentation]
permalink: toolguard/too-45/proposed-tickets/88-deny-with-exception-recipe
---

# Split out of ticket 18. The matcher fix shipped in `c5e50a5`; this did not.

The docs carry a recipe for *"deny a command generally, permit one safe use."* Its worked example used `curl`, and **four attempts to write that example all failed**, each in a different direction:

| attempt | outcome |
|---|---|
| `Bash(curl http://localhost:*)` as a `hard_deny` carve-out | exempts `curl http://localhost http://evil.example/steal` -- a trailing `*` spans arguments |
| anchored `[regex]`, no flags admitted | blocks every practical invocation |
| exact invocations, one rule per command | permits **1 of 8** realistic variants |
| bounded flag set `(-[sSv]+)*` | permits **1 of 16** -- dies on `--silent`, `-X POST`, `-H`, quoted URLs, `https://`, IPv6 `[::1]` |

**Two of those were approved by the coordinator on reasoning and refuted by measurement.** Both "verifications" were circular: the permitted-case list was derived from the pattern's own alphabet, so it could not have failed.

## The diagnosis: `curl` has no seam

`curl`'s dangerous capabilities are expressed in the **same syntax** as its safe ones -- `-o` writes a file, `-L` redirects anywhere, a second bare URL exfiltrates. A pattern loose enough for real usage admits those; a pattern tight enough to exclude them excludes ordinary use. **This is a property of curl's CLI, not of toolguard.**

## The rule worth publishing, which is the real deliverable

**A deny-with-exception recipe works when either the SAFE set or the DANGEROUS set is closed and enumerable. When neither is, use `ask`.**

| tool | which set is enumerable | verdict |
|---|---|---|
| **`find`** | the **dangerous** set: `-exec`, `-execdir`, `-ok`, `-okdir`, `-delete`, `-fprintf`, `-fprint`, `-fls` | **one negative lookahead. Use this as the example.** |
| `git` | the **safe** set: read-only verbs | works, but `~/.toolguard/rules/git.rules.toml` is **402 lines** because of global-flag prefixes -- unusable for teaching |
| `curl` | neither | **`ask`** |

That gives a reader a test they can apply to their own tools, which a worked example alone never did.

## Scope

1. **Replace the `curl` example with `find`** in `docs/configuration.md`, `docs/agent-guides.md`, and `.claude/skills/toolguard-security-audit/SKILL.md`. Measured working:

   ```
   Bash([regex]^find\b(?!.*\s-(exec|execdir|ok|okdir|delete|fprintf|fprint|fls)\b))
   ```

   5/5 ordinary invocations permitted (`-name`, `-type`, `-mtime`, `-maxdepth`, `-size`, `-print`, `-ls`); 5/5 dangerous excluded.

2. **State the enumerability rule** once, plainly, next to the recipe.

3. **Say that `curl` should be `ask`** -- Arnon, 2026-08-20: *"curl should generally be an ask anyway, especially since claude can use its builtin WebFetch for almost any need that curl would be legitimate for."* **TOO-23** tracks the broader question; meanwhile WebFetch is governed Claude-side and is ungoverned by toolguard.

4. Keep the caveat that survives: an exact-invocation allow is defeated by a port, a flag order, a quote or a spelling. At the **ordinary** level that is an acceptable tradeoff because the user can add more allows; inside `hard_deny` it is not, because nothing can override it.

## Verification obligation

**Write the permitted list from realistic usage BEFORE looking at any pattern.** Cases derived from the artifact under test are not a test -- that failure produced two of the four wrong versions. Verify through `toolguard.testing.sandbox` with both `evaluate()` and `run_hook()`, and report warning counts rather than filtering them.
