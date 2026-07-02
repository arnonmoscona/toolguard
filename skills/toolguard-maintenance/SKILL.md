---
name: toolguard-maintenance
description: >
  Curate the active toolguard permission configuration: find redundant,
  consolidatable, and confusing rules across the whole config hierarchy, then
  apply the safe, replay-verified consolidations with the user's consent. Use
  when asked to clean up, tidy, consolidate, simplify, de-duplicate, or maintain
  the toolguard / Claude Code permission rules, to shrink an over-grown allow
  list, or as a periodic config-curation checkpoint (e.g. before a push). Runs a
  deterministic analyzer, presents findings, and -- only on explicit go-ahead --
  applies consolidations behind a dry-run preview and a working-tree safety gate.
argument-hint: "[directory (default: current project)] [--corpus] [--apply]"
---

# Toolguard Maintenance

Keep the active toolguard permission configuration tidy and intelligible. This
skill orchestrates the tested `toolguard-maintain` analyzer/apply tool; it does
**not** re-implement any analysis or editing itself. It works in two stages:

1. **Report (always).** Run the deterministic analyzer to surface maintenance
   findings across the whole config hierarchy: redundant rules, consolidatable
   rule families, agent-judged broadenings, cross-layer redundancies, and
   confusing same-file rule interactions. High trust, mechanical, repeatable.
2. **Apply (opt-in, gated).** *After* presenting the report and getting an
   explicit go-ahead, apply the **strict, replay-verified consolidations** behind
   a dry-run preview and a safety pre-flight. Every other finding category is
   reported for the human to act on -- it is never auto-applied.

## Hard constraints

- **Reporting is read-only.** The report stage reads only local config files,
  makes no network calls, and costs no model tokens to run.
- **Applying needs explicit consent AND is gated.** Never write to a config file
  without (a) the user agreeing to apply, (b) showing them the dry-run diff
  first, and (c) the tool's own pre-flight passing (clean working tree, resolved
  project root). The tool refuses to write on a dirty tree; do not try to
  circumvent that.
- **Apply consolidations only.** Only the strict `literal-alternation`-style
  consolidation proposals are machine-appliable (they are replay-verified to
  preserve every decision). **Broadenings, redundancies, cross-layer findings,
  and clarity interactions are NEVER auto-applied** -- present them for human
  judgement. A broadening widens what is permitted; that is always the user's
  call.
- **Don't re-derive the analysis by hand.** Get findings from the tool's JSON
  contract; do not eyeball config files and invent findings.
- **ASCII only** in anything you render for the clipboard or a commit message.

## Picking the invocation

Run from the project whose configuration you want to curate (the analyzer
discovers the full hierarchy upward from that directory, exactly as the live hook
does). Pick the invocation by where you are -- the same rule as the audit skill:

- **Curating any normal project** -- use the installed console script (it runs
  inside toolguard's own environment, so the target project does not need
  toolguard on its Python path):
  ```bash
  toolguard-maintain --format json
  ```
- **Developing toolguard itself** -- if the current project IS the toolguard
  source repo (its `pyproject.toml` declares `name = "toolguard"` and
  `toolguard/tools/maintenance.py` exists), run the in-repo module so you
  exercise the **working branch**, not the installed release:
  ```bash
  uv run python -m toolguard.tools.maintenance --format json
  ```
- **If `toolguard-maintain` is not found** (and you are not in the toolguard
  repo) -- the global install is too old or partial (it predates this tool). Tell
  the user and suggest `uv tool upgrade toolguard`. Do **not** fall back to the
  `uv run python -m ...` form on an arbitrary project: that only works inside the
  toolguard source tree and fails confusingly elsewhere.

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

**Proactively (tools can run):** `toolguard.tools.self_permission.missing_self_permissions(config)`
reports which of the above are not yet permitted and the exact rule to add, so you
can offer them at install/first-run. **Self-healing (a call was denied):** you
cannot run anything under the denial -- tell the user the exact rule above to add
at their chosen scope, then retry. Every added rule stays explicit and auditable.

## Stage 1 -- Report

### Run it

Default run is **static and fast** (sub-second); it needs no corpus:

```bash
toolguard-maintain --format json
```

Options:

- `--dir DIR` -- curate a different project directory (default: current).
- `--format json|markdown|text` -- use **json** when you will interpret and
  re-present findings (it is the structured contract); `markdown`/`text` only
  when the user wants the raw report.
- `--tool TOOL` -- restrict to one governed tool (repeatable). Default: all
  governed tools (Bash, Read, Write, Edit).
- `--corpus` -- **opt-in.** Also harvest an evidence corpus (toolguard daily logs
  + Claude Code transcripts) so replay-backed and command-mining findings are
  populated. This parses every observed command and **can be slow on a large
  history** (tens of seconds), so bound it with `--max-age-days N`. Offer it when
  the user wants usage-evidence-driven findings (mining of frequently-asked
  commands, broadenings); warn that it takes a while. Example:
  `toolguard-maintain --corpus --max-age-days 30 --format json`.

### The JSON contract

```
{
  "total_findings": int,
  "has_any_findings": bool,
  "tools": [
    { "tool": "Bash", "total": int,
      "redundancies":   [ { "redundant_pattern", "provenance", "kind",
                            "list_type", "tool", "covered_by", "note" } ],
      "consolidations": [ { "kind", "tool", "list_type", "layer_provenance",
                            "removed_patterns", "added_pattern", "rationale",
                            "replay_summary" } ],   // the APPLIABLE proposals
      "broadenings":    [ { "kind", "tool", "list_type", "layer_provenance",
                            "removed_patterns", "added_pattern", "rationale",
                            "newly_admitted_commands", "overlaps_guard_rules",
                            "probe_admitted_surface" } ],
      "cross_layer_redundancies": [ { "tool", "pattern", "redundant_provenance",
                                      "covered_by_provenance", "note" } ],
      "interactions":   [ { "tool", "provenance", "kind", "allow_pattern",
                            "guard_section", "guard_pattern", "explanation" } ]
    } ],
  "mining": { "groups": [ { "tool", "command_key", "signal",
                            "distinct_commands", "occurrences",
                            "current_verdict", "observed_counts" } ] }
}
```

Every `provenance` is expanded to `{ level, source_type, file_format, path,
specificity, describe }` -- cite the `describe` string when you tell the user
*where* a rule lives.

### Present it

Group findings by category and explain each in the user's own config terms:

- **Consolidations** -- safe merges of a rule family into one clearer rule (e.g.
  three `git diff|status|log` allows into one anchored regex). Replay-verified to
  change no decision. These are what Stage 2 can apply.
- **Broadenings** -- a *wider* rule the evidence suggests; spell out exactly what
  new commands it would admit (`newly_admitted_commands`) and any guard rules it
  overlaps. **Human decision -- never auto-applied.**
- **Redundancies / cross-layer redundancies** -- rules already covered by another
  rule (same file, or a broader layer). Suggest removal; name both loci.
- **Clarity interactions** -- "correct but confusing" overlaps where toolguard's
  resolution (deny always wins; broad ask collapses to deny; else more-specific
  wins) makes the effective verdict non-obvious. Surface the tool's
  `explanation` verbatim -- the value is making the real behavior legible.
- **Mining groups** (only with `--corpus`) -- frequently-seen command families
  and how they currently resolve, as evidence for consolidation/broadening.

If `has_any_findings` is false, say the config is already tidy.

## Stage 2 -- Apply (opt-in, gated)

Only after presenting the report and the user agreeing to apply. **Applies the
strict consolidations only.**

### Always preview first (dry run)

```bash
toolguard-maintain --apply               # dry-run PREVIEW: shows the diffs, writes nothing
toolguard-maintain --apply --format json # same, as a structured change report
```

The preview prints a per-file change report **with the unified diff inlined**, so
you (and the user) see exactly what would change. The JSON change report shape:

```
{ "dry_run": bool, "total_applied": int, "total_skipped": int,
  "files_written": [path, ...],
  "files": [ { "path", "file_format",
               "applied": [ { "removed_patterns", "added_pattern", "rationale" } ],
               "skipped": [ { "removed_patterns", "reason" } ],
               "patterns_removed", "patterns_added", "diff", "written" } ],
  "edit_proposals": [ ... ],          // appliable consolidations (for --edits review)
  "withheld_nosecurity": [ { "tool", "list_type", "removed_patterns",
                             "added_pattern", "reason" } ] }   // see below
```

**`#NOSECURITY`-blessed rules are never auto-rewritten.** A consolidation that
would remove/merge a rule the user annotated with a `#NOSECURITY[: reason]` comment
is **withheld** from the apply path (and from the `edit_proposals` handed to the
audit review) -- that rule is intentionally-insecure *here* and is the user's to
change. Surface the `withheld_nosecurity` entries so the user knows a tidy-up was
deliberately skipped; do not try to route around it.

### Choose how to present the change to the user

Match the user's appetite -- these are presentation strategies over the same
dry-run preview, not different tools:

- **Self-edit (paste-ready).** Show the diff and the exact rule(s) to add/remove
  so the user can hand-edit. Best when they want full control or to tweak wording.
- **Bulk-apply.** Show the whole change report, then apply everything at once on
  confirmation. Best when the consolidations are obviously safe and uniform.
- **Case-by-case.** Walk the proposals (grouped by file / interacting rules),
  confirming each. Best when some merges touch rules the user cares about, or
  when clarity interactions overlap the same commands.

### Review the proposed changes with the security-audit skill (before writing)

**Always run this security review before `--write`.** A consolidation swaps a
family of rules for a new rule (and a fix may span sections/layers), so it must be
judged against the WHOLE config, not rule-by-rule. The audit does this
as-if-enacted:

1. Get the structured proposals from the dry-run preview: the JSON payload from
   `toolguard-maintain --apply --format json` carries an `edit_proposals` array
   (one `EditProposal` per consolidation).
2. Write that array to a temp file and hand it to the audit:
   ```bash
   toolguard-audit --edits /tmp/tg-edits.json --format json
   # dev checkout: uv run python -m toolguard.tools.security_audit --edits ... --format json
   ```
   The audit applies the edits in memory and reports on the AS-IF-ENACTED config;
   `context.proposed_edits.delta` lists findings `introduced` and `resolved`.
3. **Invoke the security-audit skill's judgement** on that result (its Pass-2
   "Proposed edits" section). Treat any `introduced` finding as a blocker to
   surface: a consolidation that resolves a MEDIUM but introduces a CRITICAL is a
   bad trade -- do not write it without the user's explicit, informed go-ahead.
4. Only proceed to `--write` when the review is clean or the user accepts the
   introduced risk with full knowledge of it.

The audit can also feed maintenance the OTHER direction: its own findings carry a
structured `remediation_proposal` (an `EditProposal`); you may ingest those as
proposed edits, preview them the same way, and (after the same review) apply them.

### Commit the change (only on explicit confirmation)

```bash
toolguard-maintain --apply --write
```

`--write` is the only flag that modifies files, and it runs the safety pre-flight
first. If the working tree is dirty or the project root cannot be resolved, it
**refuses and exits non-zero** (leaving config untouched) -- relay the blockers
and have the user commit/stash, then re-run. After a successful write the tree is
now dirty (the change is uncommitted); a second `--write` is correctly refused
until the user commits. Leave the git commit to the user.

## Stage 3 -- Annotate (opt-in, gated, comment-only)

Separately from applying consolidations, you can write **`# toolguard:` comments**
above rules with confusing interactions, so the real resolution is legible in the
config file itself. This changes NO rule -- it only adds/updates generated comment
lines.

```bash
toolguard-maintain --annotate                 # dry-run PREVIEW: unified diff, writes nothing
toolguard-maintain --annotate --format json   # same, structured (per-file diffs)
toolguard-maintain --annotate --write         # writes, gated by the same pre-flight as --apply
```

- **Idempotent + human-safe.** Re-running replaces the previous generation (no
  accreted duplicates) and removes a stale note when a rule is no longer confusing.
  Only `# toolguard:`-marked lines are ever touched; your own comments are
  preserved, as are rule order, blank lines, and empty sections (minimal diff).
- **Gated.** `--annotate --write` runs the working-tree / project-root pre-flight
  and refuses on blockers, exactly like `--apply --write`. `--annotate` and
  `--apply` are separate modes -- run them separately.
- **When to offer it.** After presenting clarity-interaction findings, offer to
  annotate so the config self-documents; always preview the diff and get consent
  before `--write`.

## Relationship to the security-audit skill

These are siblings with different jobs that form a loop: `toolguard-security-audit`
flags **risk** (read-only), this skill curates **clarity and redundancy** and
applies safe consolidations. They connect through the shared `EditProposal` model:

- **Maintenance -> audit (mandatory before writing):** hand your proposed edits to
  `toolguard-audit --edits` for the as-if-enacted review above.
- **Audit -> maintenance:** each audit finding carries a structured
  `remediation_proposal` (an `EditProposal`) you can ingest and apply through the
  same preview + review + write path.

Clarity interactions surface in both.

## When to use

- On demand: "clean up my toolguard rules", "consolidate these allow patterns",
  "my permission config has grown -- tidy it", "are any rules redundant or
  confusing?".
- As a periodic checkpoint -- a good pre-push curation step (the project's
  pre-push checklist explicitly suggests running maintenance).

## Notes

- The analyzer is offline for the report stage; only `--corpus` reads logs and
  transcripts, and only `--write` ever modifies a file.
- A clean report means no *known* maintenance patterns matched; it is not a proof
  the config is optimal.
- toolguard is a desktop tool that works in **local time**; corpus windows
  (`--max-age-days`) are relative to today's local date.
