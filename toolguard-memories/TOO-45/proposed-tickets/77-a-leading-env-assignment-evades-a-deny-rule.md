---
title: A leading environment-variable assignment evades a deny rule, and costs a disclosed
  command its allow rule
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/77-a-leading-env-assignment-evades-a-deny-rule
---

# `FOO=1 rm -rf /tmp/x` is not seen as an `rm` command

**Found 2026-08-14, measured, not read.** Not covered by any test in the tree, so it is not one of the 137 phase-1 reds — it came out of a measurement I asked for while settling the `Bash(x:*)` boundary question.

Toolguard strips nothing before matching. A leading `VAR=value` assignment reaches the leaf command verbatim and is matched as part of the command text. Two consequences, in opposite directions:

| command | rule | today | should be |
|---|---|---|---|
| `FOO=1 rm -rf /tmp/x` | `deny Bash(rm:*)` | **evades the deny** | denied |
| `TG_INTENT=1 ls -la` | `allow Bash(ls:*)` | falls to `ask` | allowed |

**The deny row is a live bypass of a security tool by a one-token prefix.** Wrapper commands behave identically — `timeout`, `nice`, `nohup`, `stdbuf`, `command`, `builtin`, zsh `noglob` — and so does bare `xargs`.

## Native strips, and the asymmetry is the whole problem

Claude Code's documented behaviour, per `code.claude.com/docs/en/permissions.md`, applies three normalisations **before** prefix matching: wrapper stripping, bare `xargs` stripping, and **stripping of leading environment-variable assignments for allow rules only**.

So implementing native behaviour exactly — which is what a drop-in replacement is supposed to do — **fixes the allow row and leaves the deny bypass wide open.** That is the decision this ticket carries, and it is not a small one:

- **Match native exactly.** Drop-in fidelity preserved; `FOO=1 rm -rf /tmp/x` still evades a deny rule.
- **Strip for both lists.** Closes the bypass; diverges from native in the direction of being stricter. A deny that fires where native would not is a false positive, but a *safe* one.
- **Strip for allow, and treat a stripped prefix on a deny-list evaluation as undecidable** so it takes the ask floor. Closes the bypass without silently denying, at the cost of friction.

I have not picked. The first option is defensible only if the deny bypass is considered out of scope for a permission hook, which seems unlikely to be Arnon's view.

## It bites this project's own conventions directly

`CLAUDE.md` mandates `TG_INTENT=1 <command>` and `TG_ATTEST_READONLY=1 <command>` as the machine-checkable half of the disclosure rule. **Every command carrying one of those markers currently misses its own allow rule and falls to `ask`.** The rule designed to make agent behaviour visible is, today, also the rule that removes the agent's permissions — which is a strong incentive to skip it, and the disclosure rule already has a measured compliance problem.

Related but distinct: ticket 75 records that `mining._command_key` buckets `TG_INTENT=1 …` under the wrong token. Same marker, different subsystem — that one loses analysis, this one loses enforcement.

## Note on scope

Job 3 of the boundary follow-up incidentally immunises the two `hard_deny` self-integrity patterns against this, but that is a property of how those particular regexes are written, **not** of the matching engine. Every ordinary deny rule remains affected.
---

## Residual after phase 1, recorded because the argument that closed `+=` applies to it

`arr[0]=$(id) rm -rf /tmp/x` and `arr[0]+=$(id) rm -rf /tmp/x` **still hide `rm`**, so they still evade `deny Bash(rm:*)`. Array-element assignment is unmodelled; both grammar reviews saw it and left it.

That is defensible on frequency — zero corpus occurrences — but **it is the same shape as the `FOO+=` gap that was closed in phase 1**, and the reason `+=` was closed was not frequency. It was that a leftover gap of exactly this shape is what invites a hand-rolled check in the Python consumer, which is the failure `.claude/rules/bash-grammar.md` exists to prevent. Leaving it undocumented would mean the next person meets it with no record of the decision.

So: **decide it deliberately, in the grammar, or record here that it is accepted.** Do not close it in phase 2's Python.

---

## CORRECTION, 2026-08-20 — this ticket's native comparison was false, and so was the decision built on it

The body above says native strips leading assignments **"for allow rules only"**, and concludes that implementing native exactly "fixes the allow case and leaves the deny bypass wide open". Both are wrong. Fetched from `code.claude.com/docs/en/permissions.md` and quoted verbatim:

> Claude Code also strips a leading assignment of certain known-safe environment variables, so `Bash(npm test *)` matches `NODE_ENV=test npm test`. An allow rule won't match past an assignment of any other variable. **A deny or ask rule matches past any leading assignment, so `Bash(rm *)` in deny still matches `FOO=bar rm -rf tmp/`.**

**Native has no deny bypass.** The bypass existed only in toolguard. Native's policy is the same shape as the one built here — restricting rules match past the prefix, granting rules only for known-safe names — and the only real difference is **who owns the list**: native's is Claude Code's own and unnamed in its documentation, toolguard's is `assignments_looked_past_when_granting` and starts empty.

So the recorded decision that this design is *"deliberately stricter than native in both directions"* and that the divergence is *accepted as safer* is void. **There is no divergence in shape.** The implementation is unaffected and is in fact more native-compatible than claimed.

**Where the error came from, because the mechanism matters more than the fact.** It originated in an aside from a documentation-research subagent four weeks earlier: *"leading-env-var-assignment stripping for allow rules only"*. True as far as it went, and it omitted the sentence immediately following it in the source. That half-quote was relayed, repeated, written into a ticket, and used to justify a design decision — and it survived two blinded reviews, because every reviewer was checking prose against **this repository's** code and nobody re-read the external source. **A claim about a system outside the repo cannot be verified by reading the repo**, which is exactly the gap that let it live.
