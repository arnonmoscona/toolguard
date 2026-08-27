---
title: Consolidate every external-contract structure into one module, and move the functions
  that exist only to serve it
tags:
- TOO-45
- proposed-ticket
- architecture
permalink: toolguard/too-45/proposed-tickets/85-consolidate-the-external-contract-into-one-module
---

# The contract toolguard does not own is recorded nowhere, 741 times

**Filed 2026-08-20 at Arnon's instruction.** *"Make a ticket to consolidate all structures related to external contract into this new module and all stand-alone functions whose sole purpose is dealing with the external contract(s) should move there too. Functions that mix references to external contract structures but have toolguard-specific logic should not be moved. This ticket is a fairly high priority as it is really part of the original scope of TOO-45 (architectural cleanup)."*

## The measurement

Twelve Claude Code wire-protocol field names, counted as bare string literals:

| | sites | modules |
|---|---|---|
| package | **45** | **6** |
| tests | **~696** | — |

`additionalContext` alone is 7 package sites and 188 test sites. Thirteen package modules reference some part of the contract: `api`, `auto_migrate`, `compound`, `hook`, `log_writer`, `permission_migration`, `permission_resolution`, `session_start`, `subagent`, `testing.sandbox`, `tools.environment_audit`, `tools.installer`, `tools.takeover_audit`.

**Nothing anywhere states the contract.** The ~696 test occurrences *encode* it by repetition, which is not the same thing: an upstream rename changes 696 lines, and no single line ever said what the field was, who owns it, or when it was last verified against the source. This is the project's own "literal strings with semantic meaning belong in constants" rule, applied to the one category of string toolguard does not get to define.

**Why it is urgent rather than tidy.** A claim about native's behaviour cannot be validated against this repository — see `.claude/rules/native-fidelity-claims.md`. Two false claims shipped in one day for exactly that reason. Consolidation does not fix that by itself, but it creates the single place a periodic re-verification can be *performed against*, which is the whole mitigation Arnon accepted.

## The module

`toolguard/claude_code_contract.py` — named for the **owner of the facts**, not for us. Leaf module, stdlib-only, importable from any layer like `constants.py`; needs a `.pyscn.toml` layer entry.

Every entry carries the **doc URL, the section anchor, and a `VERIFIED` date.** Documentation cites the module rather than restating it, so there is one place to update and one place to review.

Contents:

- **Wire protocol** — payload field names (`tool_name`, `tool_input`, `hook_event_name`, `session_id`, `cwd`, `transcript_path`) and response field names (`hookSpecificOutput`, `hookEventName`, `permissionDecision`, `permissionDecisionReason`, `additionalContext`), plus event names (`PreToolUse`, `SessionStart`).
- **`STRIPPED_WRAPPERS`** and, equally load-bearing, the explicitly **not**-stripped list. Ticket 82's error was an assumption about membership of the second, so it is not optional commentary — it is half the contract.
- **Matching semantics toolguard mirrors** — word-boundary rule, `:*` ≡ ` *`, colon-is-literal mid-pattern, known-safe assignment stripping and its allow/deny asymmetry.

**Drift detection is the weak option, chosen deliberately** (Arnon, 2026-08-20: *"A weak option is fine for now. At least we have a good way to periodically review."*): dated constants plus a periodic re-verification, no version-pinned test. The stronger option — pin `claude --version` and fail on change — is recorded in `DECISIONS-PENDING.md` A15 and remains available if the weak one is seen to drift.

## THE BOUNDARY RULE — this is the whole difficulty of the ticket

Arnon's rule, and it must be applied per function rather than per module:

- **A stand-alone function whose SOLE purpose is dealing with the external contract MOVES.**
- **A function that references external-contract structures but carries toolguard-specific logic STAYS.**

### The worked example, because it is the case that will be got wrong

`hook.create_hook_output` builds the wire response. Every key it writes is Claude Code's. But it takes a `RuntimeVerdict` — a toolguard type — and *projects* it: it consumes `decision`, `reason` and `additional_context`, and deliberately ignores `provenance`, `matched_rule`, `sub_matches`, `overrides`, `fallback_warning`, `tool` and `target` because those drive the audit log instead.

**That projection is a toolguard decision, not Claude Code's.** Which fields of our verdict reach the wire is our policy. So `create_hook_output` **stays**, and imports its key names from the contract module.

`hook._finalize_output` stays for a plainer reason: it merges accumulated reporter faults into `additionalContext`, which is entirely toolguard behaviour.

**The test to apply**: could this function be written by someone who had read Claude Code's documentation and knew nothing about toolguard? If yes, it moves. If it encodes a choice toolguard made, it stays and imports the names.

**Expect few functions to move and many to change imports.** That is the correct outcome, not a disappointing one — a small module of facts plus wide adoption of its names beats a large module that has absorbed logic to look substantial. **Resist the pull to move `create_hook_output` merely because it would make the new module feel load-bearing.**

## Scope boundary worth stating

The ~696 test literals are the larger count, and migrating them is a much bigger diff than the package's 45. **Do the package first and decide about tests separately** — a test that spells the field literally is arguably *pinning* the contract rather than duplicating it, and there is a real argument for leaving at least the wire-level tests spelled out so a rename fails loudly. That argument should be made explicitly rather than settled by momentum in either direction.

## Verification obligation

This is a pure refactor: **no behaviour may change.** The evidence that it did not:

- the full suite green before and after, with `~/.toolguard/errors/` file count unchanged (it is a test-isolation leak detector);
- `corpus_build --verify` showing no differences;
- a before/after replay over the real command corpus showing zero decision, matched-rule and digest differences — the same instrument ticket 78 used.

`--layers` must stay clean, which is the check that the new leaf module has not acquired an upward dependency.

## Priority

**High, and part of TOO-45's original architectural-cleanup scope** rather than an addition to it. Suggested sequencing: let **ticket 82 create the module** with the wrapper list alone — a single real consumer validates the module's shape — and let this ticket move everything else in immediately after. That avoids blocking a security fix behind a wide refactor, and avoids designing the module in the abstract.

---

## REFINEMENT, Arnon 2026-08-20 — the import edge is a deliverable, not a side effect

> *"All claude code keys should be actually in that new module - so the whole function would end up directly **referencing** the contract but not **expressing** it. Just that dependency alone is useful for static analysis and review purposes."*

This sharpens the boundary rule into something mechanical. **Every Claude Code key becomes a named constant in `claude_code_contract`, and no bare contract literal survives anywhere else in the package.** `create_hook_output` then still stays put — but it changes character: it *references* the contract instead of *expressing* it.

**The `import claude_code_contract` edge becomes the answer to "what depends on the external contract?"** — enumerable by AST, exactly, in one query. Today that question can only be asked as a grep for twelve strings, which is a list that goes stale silently and that nobody thinks to re-derive when a thirteenth field appears.

This is the same argument that justified the ambient facade in tickets 44 and 80, and it earned its keep there: consolidating ambient reads behind one module is what made `expanduser`, `resolve` and `absolute` findable at all, after each had escaped four, five and six review rounds respectively by being invisible to the instrument used to clear the round before it.

### Consequence: a `--contract` check belongs in `tools/architecture_fitness.py`

Once the vocabulary lives in one place, **a bare contract literal outside that module is statically detectable**, and the tool already has the shape for it — `--ambient` and `--mocks` are the precedent. Scope it the way `--ambient` scopes `pathlib`: a closed list.

**And say plainly what such a check cannot do.** It can find *known* contract strings that escaped the module. It cannot find a field Claude Code added upstream that we have never heard of — no static rule can, because the vocabulary is the thing being checked. That gap is covered only by the periodic re-read of the documentation, which is the whole of the drift mitigation Arnon accepted. **A green `--contract` must not be reported as "the contract is current"**; it means "no known key leaked out of the module," which is a different and much smaller claim. This project has repeatedly been misled by exactly that substitution — an instrument's silence read as coverage of something it never examined.

`pathlib` was tractable for `--ambient` because it is a closed list that changes only with a Python release. The wire protocol is closed in the same sense and changes only with a Claude Code release — so the analogy holds, including its limit: correctness is asserted **as of a version**, never permanently.

### Review benefit, stated separately because it is not the same as the analysis benefit

Reviewing "does this change touch the external contract?" becomes reading an import list rather than knowing which twelve strings to grep for. That matters here specifically: a blinded reviewer **cannot** validate a contract claim against this repository, so the most a review can do is *notice that a claim is being made* and demand a fetched citation. The import edge is what makes that noticing reliable rather than dependent on the reviewer already knowing the vocabulary.

---

## THE ARCHITECTURE DOCUMENT MUST CARRY THIS DECISION (Arnon 2026-08-20)

> *"Like nearly all architectural concerns - it's a balancing act that uses a lot of judgement as well as 'personal architectural taste'. That's one of the reasons that it is harder for AI agents to reason about code architecture - it is mostly 'mushy', not well-measurable, and full of human experience based decisions that are not clearly self evident in the code artifacts that emerge. That is also why non-trivial systems need to articulate much of the architecture decisions in an accompanying document with illustrative diagrams."*

**In scope for this ticket**: a new section in `docs/architecture-as-built.md`, with a diagram in `docs/diagrams/` following the existing `.mmd` + `.png` convention (`external-contract.mmd`). It sits naturally after **§4 "Two halves: the core runtime and the operator tooling"** and before **§5 "The layer model"**, since it introduces a leaf both halves depend on — but place it where it reads best.

### Write the part that is NOT re-derivable from the code

**The diagram and the prose do different jobs, and both are required.**

*(An earlier draft of this section said a structural diagram was "nearly worthless here, because a reader can get that from the import graph." Arnon corrected it, and the correction is the more useful statement of what to build.)*

**The diagram's job is to express intent, not to document what there is.** It must be very close to the truth, but it is **not meant to be complete** — it is selective by design, so leaving things out is the technique, not a defect. Its value is human comprehension bandwidth: code and analysis tools handle arbitrarily large graphs, and a person cannot hold one in their head. A small, focused diagram is the **entry point** to the decision, not an illustration bolted onto finished prose.

**The prose's job is what no artifact records**: which alternatives were live, what each would have cost, and what future the decision bets on. That is the "human experience based decisions not self evident in the code artifacts" Arnon names, and it is the part that decays if unwritten.

**On drift.** Diagrams do drift, but a *good* architecture is stable until something in the world collides forcefully with its assumptions about the future — so the drift is bounded, and the fear of it is not a reason to skip the diagram. Worth noticing the corollary: because the diagram encodes the bet, **a diagram that has genuinely gone wrong is a signal that the bet was called**, not merely that someone forgot to update a picture. Treat that as information about the architecture rather than as a documentation chore.

So the section must carry:

- **Why a separate module rather than `constants.py`.** These facts differ in kind: we do not own them, they can change without any commit to this repository, and their correctness is asserted *as of a date* rather than permanently. Nothing else in `constants.py` has that property.
- **Why `create_hook_output` stayed out of it** — the worked boundary case, stated as a decision with its reasoning, because it is the one a future reader is most likely to try to reverse. Naive SRP argues for moving it; the argument against is that projecting our verdict onto their wire is *our* policy, spelled in their vocabulary.
- **What the import edge buys**, and what it does not: `--contract` finds known keys that escaped the module; it cannot find a field Claude Code added that we have never heard of. A green check is not "the contract is current."
- **Why drift detection is deliberately weak** — dated constants and a periodic review, not a version-pinned test — and what evidence would justify strengthening it.

### The general point is worth recording once, not per ticket

This project has direct evidence for Arnon's claim, and it is unusually clean. `tools/architecture_fitness.py` was built to measure architectural health; his own assessment is that his impressions still catch almost all architectural issues, and the campaign record agrees — **every architectural error in TOO-45 was caught by a question from Arnon, never by a metric.** The tools' value has been to trigger a focused human look at a suspect area, including when their specific finding was wrong.

That is not an argument against the tools. It is an argument about **what the document is for**: the metric sees the artifact, and an architectural decision is a bet about which future changes will be cheap. The artifact records the choice; only prose can record the alternatives and the bet. Which is why the sections that matter most in `architecture-as-built.md` are the ones explaining what was *rejected* — §2 (standard library only) and §3 (all parsing through the PEG grammar) both earn their length that way, and §3 exists specifically because the rule was repeatedly violated when it lived only in code.
