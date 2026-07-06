---
name: toolguard-maintenance
description: >
  Curate the active toolguard permission configuration through a guided,
  conversational review: find redundant, consolidatable, mis-levelled, and
  confusing rules across the whole config hierarchy, present them grouped by
  command family with a plain-English before/after, and -- only on explicit,
  per-item consent -- apply the changes the user approves. Use when asked to
  clean up, tidy, consolidate, simplify, de-duplicate, or maintain the toolguard
  / Claude Code permission rules, to shrink an over-grown allow list, or as a
  periodic config-curation checkpoint (e.g. before a push). Runs a deterministic
  analyzer for evidence, reasons about it in passes, and never applies anything
  automatically.
argument-hint: "[directory (default: current project)] [--corpus] [--dev (toolguard maintainers only)]"
---

# Toolguard Maintenance

Maintaining permission rules is judgement-heavy refactoring, not a mechanical
sort. The right consolidation, the right level for a rule, and whether a "confusing"
overlap is actually a bug all depend on *user intent* that the tool cannot infer.
So this skill is anchored on a conversation, not on code: the tested
`toolguard-maintain` analyzer produces **evidence**, and the skill turns that
evidence into a proposal you can understand and decide on, family by family.

**The model in one paragraph.** The analyzer produces evidence -- findings,
replay-verification, as-if-enacted audits. It never produces consent. Even a
strict, replay-verified, decision-neutral merge is only a *recommendation*: it may
belong at a different level, or be one you want left alone. This skill presents the
whole change set grouped by command family, discusses it with you, and enacts only
the pieces you explicitly approve. **Nothing is applied automatically, ever.**

## Hard constraints

- **No auto-apply, ever.** No change reaches a config file without an explicit,
  informed user choice for that specific change -- no matter how trivial or how
  well replay-verified.
- **Replay-verification is evidence, not consent.** "Decision-neutral over the
  corpus" proves the tool did not change an *observed* decision; it says nothing
  about intent, level, or contexts the corpus never exercised. **Bulk-apply is an
  explicit user opt-in ("just do it all"), never a default and never a label the
  skill assigns.**
- **Layer-targeting before consolidation.** Decide the right level for each rule
  *before* merging. Never merge rules that belong at different levels; if the tool
  proposes a merge that welds project-specific and user/machine-generic patterns
  into one rule, split it and flag it.
- **Heterogeneity is a discussion trigger, not a silent merge.** When a command
  family contains an outlier in shape or scope (a flag-with-value, a
  target/selector token, a member narrower or broader than its siblings), stop and
  ask -- do NOT consolidate it away, and do NOT go research an unfamiliar
  domain-specific tool to resolve it yourself. General programming judgement to
  *notice* the outlier is enough; the user supplies the intent. Conversely, **assert
  the standard semantics of ubiquitous, stable tools (git, .env, ssh, core unix) with
  confidence** -- the ceiling is for obscure/domain-specific behavior, not universal
  tooling.
- **Don't re-derive the analysis by hand.** Get findings and config from the tool's
  JSON contracts (below); do not eyeball config files and invent findings.
- **Read-only until consent; respect the write gate.** Only the tool's
  `--apply --write` / `--annotate --write` modify files, and only after the user
  approves. Both run a safety pre-flight (clean working tree, resolved project
  root) and refuse otherwise -- relay blockers, do not circumvent them.
- **ASCII only** in anything you render for the clipboard or a commit message.

## How this skill runs -- the passes

This skill executes as an ordered sequence of **passes**, each with its own
instruction file under `passes/`. Trying to gather, level, consolidate, audit, and
present all at once invites mistakes; each pass has a focused job. The passes share
one working document -- the **recommendation set** (schema:
`passes/recommendation-set-schema.md`), a JSON file kept in the session scratchpad
(never in the repo) that each pass reads and annotates.

Load and follow each pass file in order:

1. **`passes/1-gather-and-target.md`** -- run the analyzer + the security audit for
   evidence, build the recommendation set, group every rule into command families
   (across all sections), target the right level for each proposed change (blocking
   cross-level welds), and capture the top-level config settings (takeover mode,
   governed_tools, config_sync) as observations.
2. **`passes/2-consolidate-and-group.md`** -- treat the tool's consolidations as
   *candidates*, refine them at the judgement level under the level constraints,
   flag heterogeneous families for discussion, and write the per-family narrative.
3. **`passes/3-report-certify-and-apply.md`** -- render the understanding view, a
   detect-and-inform section on the non-permission config settings (takeover
   coherence, promotion-worthy posture), and a separate cut/paste TOML section;
   certify the assembled config with the tool (parse + as-if-enacted audit); then
   discuss and apply **case-by-case** on explicit consent.

> Phasing note (implementation in progress): the discussion loop, corpus-replay
> validation, first-run-vs-periodic trust levels, the prior-decision ledger, and
> user-level promotion are being layered in next. Until then, keep every proposed
> change at its current level and treat promotion opportunities as observations to
> raise, not moves to enact.

## Invocation

Run from the project whose configuration you want to curate (the analyzer
discovers the full hierarchy upward from that directory, exactly as the live hook
does).

**Default -- always use the installed console scripts.** Every command in this skill
and in its passes is written in console-script form (`toolguard-maintain`,
`toolguard-audit`). `uv tool install toolguard` puts these on the user's PATH and
they run inside toolguard's OWN virtualenv, so the target project needs nothing on
its Python path. Use them **verbatim**: do NOT prefix them with `uv run` and do NOT
rewrite them as `python -m ...`. Outside the toolguard source repo there is no `uv`
project to run and no importable `toolguard` package, so those forms just fail.

- **If `toolguard-maintain` is not found** (and you are not a toolguard maintainer --
  see Development mode) -- the global install is missing, too old, or partial. Tell
  the user and suggest `uv tool install toolguard` / `uv tool upgrade toolguard`. Do
  not improvise another invocation form.

Three names, reconciled: `toolguard-maintain` and `toolguard-audit` are the two
console scripts this skill drives; **`toolguard-security-audit` is a sibling *skill***
that wraps the audit analyzer -- it is never a shell command.

### Development mode (toolguard maintainers only -- the ONLY exception)

One situation, and only one, departs from the console-script default: maintaining the
toolguard project *itself* (working on its source tree, on the maintainer's machine).
There the installed release may lag the checkout, so you run the in-repo modules to
exercise the **working branch**. This never applies to a normal target project.

**Enter dev mode when EITHER holds:**

- the skill was invoked with the **`--dev`** argument -- authoritative; use this when
  developing/testing toolguard, as we are now; or
- the current project IS the toolguard source repo as a fallback (its
  `pyproject.toml` declares `name = "toolguard"` and `toolguard/tools/maintenance.py`
  exists), so it still works if `--dev` was forgotten.

In dev mode, apply this ONE mechanical substitution to every command in this skill
and its passes; nothing else changes:

| console script (default) | dev-mode form |
| --- | --- |
| `toolguard-maintain ...` | `uv run python -m toolguard.tools.maintenance ...` |
| `toolguard-audit ...`    | `uv run python -m toolguard.tools.security_audit ...` |

This table is the **sole** place the `uv run python -m ...` form is defined. The rest
of the skill body speaks only console scripts.

## Self-permissioning (running toolguard's tools under governance)

When toolguard governs the current project (especially in takeover mode), running
`toolguard-maintain` / `toolguard-audit` is itself a `Bash` command toolguard must
permit, or the skill's own call is denied (a chicken-and-egg bootstrap). Toolguard
**never self-grants** -- SUGGEST the rules, get explicit consent, and write them at
the **same scope the skill is installed** (user vs project). The concrete rules
(bake these in; the self-healing case below cannot run any tool to compute them):

- **`toolguard-audit`** -> add `Bash(toolguard-audit:*)` to **allow**. It is
  read-only, so a standing allow is fine.
- **`toolguard-maintain`** -> add `Bash(toolguard-maintain:*)` to **ask** (NOT
  allow). It can `--apply --write` config edits directly, so a blanket allow would
  let the model mutate the security config with no review. An `ask` rule prompts
  per invocation (a specific ask with no covering allow resolves to a prompt). Do
  **not** blanket-allow it.
- Hook entry points (`toolguard`, `toolguard-session-start`) are run by Claude
  Code's hook machinery, not as Bash calls -- they never need an allow rule.
- **Self-permission rules always name the console-script form**
  (`toolguard-audit:*`, `toolguard-maintain:*`) -- never the in-repo module
  dev-form. Even when you invoke the tools via `uv run python -m toolguard.tools.*`
  inside the toolguard source repo, do NOT bake a
  `Bash(uv run python -m toolguard.tools.*:*)` rule into config: that is
  dev-machine-specific cruft, and the dev repo's own `uv run python` allowance
  already covers the dev-form. The persisted self-permission rules are for the
  normal console-script invocation.

**Proactively (tools can run):** `toolguard.tools.self_permission.missing_self_permissions(config)`
reports which of the above are not yet permitted and the exact rule to add, so you
can offer them at install/first-run. **Self-healing (a call was denied):** you
cannot run anything under the denial -- tell the user the exact rule above to add
at their chosen scope, then retry. Every added rule stays explicit and auditable.

## Tool reference (commands and JSON contracts)

The passes call these; the shapes are collected here as the single source of truth.

### `toolguard-maintain` -- the analyzer

```bash
toolguard-maintain --format json          # findings (static, sub-second, no corpus)
```

Options: `--dir DIR` (curate another directory; default current), `--format
json|markdown|text` (**json** for anything you re-present), `--tool TOOL`
(restrict to one governed tool, repeatable; default all governed tools),
`--corpus` (opt-in: also harvest toolguard daily logs + Claude Code transcripts so
replay-backed and command-mining findings populate; can be slow -- bound with
`--max-age-days N`; offer when the user wants usage-evidence-driven findings).

Findings JSON contract:

```
{
  "total_findings": int, "has_any_findings": bool,
  "tools": [
    { "tool": "Bash", "total": int,
      "redundancies":   [ { "redundant_pattern", "provenance", "kind",
                            "list_type", "tool", "covered_by", "note" } ],
      "consolidations": [ { "kind", "tool", "list_type", "layer_provenance",
                            "removed_patterns", "added_pattern", "rationale",
                            "replay_summary" } ],   // CANDIDATE proposals -- evidence, not consent
      "broadenings":    [ { "kind", "tool", "list_type", "layer_provenance",
                            "removed_patterns", "added_pattern", "rationale",
                            "newly_admitted_commands", "overlaps_guard_rules",
                            "probe_admitted_surface" } ],
      "cross_layer_redundancies": [ { "tool", "pattern", "redundant_provenance",
                                      "covered_by_provenance", "note" } ],
      "interactions":   [ { "tool", "provenance", "kind", "allow_pattern",
                            "guard_section", "guard_pattern", "explanation" } ] } ],
  "mining": { "groups": [ { "tool", "command_key", "signal", "distinct_commands",
                            "occurrences", "current_verdict", "observed_counts" } ] }
}
```

Every `provenance` is expanded to `{ level, source_type, file_format, path,
specificity, describe }` -- `describe` tells the user *where* a rule lives, and
`level` is what layer-targeting reasons about.

### `toolguard-maintain --apply` -- the dry-run preview (CANDIDATE edits)

```bash
toolguard-maintain --apply --format json  # dry-run: edit_proposals + diffs, writes NOTHING
```

Change-report JSON: `{ "dry_run", "total_applied", "total_skipped",
"files_written", "files": [ { "path", "file_format", "applied":[{...}],
"skipped":[{...}], "diff", "written" } ], "edit_proposals": [ EditProposal, ... ],
"withheld_nosecurity": [ {...} ] }`. The `edit_proposals` array is what the audit's
`--edits` consumes. **This is a preview, not an application** -- `files_written` is
`[]` without `--write`.

**`#NOSECURITY`-blessed rules are never auto-rewritten.** A consolidation that
would touch a rule the user annotated `#NOSECURITY[: reason]` is **withheld** and
surfaced in `withheld_nosecurity`; treat it as the user's to change and never route
around it.

### `toolguard-audit --edits` -- as-if-enacted review (tool-appliable subset only)

```bash
toolguard-audit --edits <edits.json> --format json --with-context
```

Applies the edits in memory and reports on the AS-IF-ENACTED config;
`context.proposed_edits.delta` lists findings `introduced` and `resolved`, and
`context.tools[].layers` is the full rule hierarchy per tool (every section, with
`is_native` and per-rule `comments`). This is both the audit input and the richest
source of the *current* config for family grouping.

**Scope caveat:** `--edits` as-if-enacts ONLY the **tool-appliable subset** -- the
machine-shaped `edit_proposals` (the mechanical consolidations). It does NOT cover
hand-authored changes (level splits, deny hardening, rewrites) that live only in
your paste-ready TOML. So `--edits` gives the introduced/resolved **delta on the
consolidations**, but it is NOT the whole-config certification. The authoritative
pre-write gate is pass 3's `--dir <tempdir>` staging audit of the entire assembled
config (see pass 3, Step 3).

### `toolguard-maintain --apply --write` / `--annotate` -- the only writers

`--apply --write` enacts the approved consolidations; `--annotate [--write]`
writes/refreshes `# toolguard:` comments above confusing interactions (comment-only,
idempotent, touches only `# toolguard:` lines). Both run the working-tree /
project-root pre-flight and **refuse on a dirty tree or unresolved root** (exit
non-zero, config untouched) -- relay blockers, have the user commit/stash, re-run.
Leave the git commit to the user.

## Relationship to the security-audit skill

Siblings with different jobs that form a loop through the shared `EditProposal`
model: `toolguard-security-audit` flags **risk** (read-only); this skill curates
**clarity, redundancy, and level** and enacts approved changes.

- **Maintenance -> audit (mandatory before any write):** certify the full assembled
  config with the audit before anything is written. The AUTHORITATIVE gate is pass
  3's `--dir <tempdir>` staging audit of the whole paste-ready config -- it sees
  every hand-authored change (level splits, deny hardening), not just the mechanical
  ones. `toolguard-audit --edits` is the narrower **delta view over the
  tool-appliable subset** (the `edit_proposals`); use it for the introduced/resolved
  delta on the consolidations, never as the whole-config certification.
- **Audit -> maintenance:** each audit finding carries a structured
  `remediation_proposal` (an `EditProposal`) you can ingest and drive through the
  same propose -> discuss -> certify -> apply flow.

Clarity interactions surface in both.

## When to use

- On demand: "clean up my toolguard rules", "consolidate these allow patterns",
  "my permission config has grown -- tidy it", "are any rules redundant, confusing,
  or at the wrong level?".
- As a periodic checkpoint -- a good pre-push curation step (the project's pre-push
  checklist explicitly suggests running maintenance).

## Notes

- The analyzer is offline for gathering; only `--corpus` reads logs/transcripts,
  and only `--write` ever modifies a file.
- A clean report means no *known* maintenance patterns matched; it is not a proof
  the config is optimal.
- toolguard is a desktop tool that works in **local time**; corpus windows
  (`--max-age-days`) are relative to today's local date.
