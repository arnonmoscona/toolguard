---
name: toolguard-security-audit
description: >
  Audit the active toolguard permission configuration for security risks and flag
  dangerous allow rules and takeover-mode misconfigurations across the whole
  config hierarchy. Use when asked to security-check, audit, or review the
  toolguard / Claude Code permission setup, to find risky or over-broad allow
  rules, to verify takeover mode is sound, or as a start-of-session safety check.
  Runs a deterministic analyzer first, then optionally offers a deeper,
  judgement-based AI-assisted assessment. Read-only: it reports findings and
  proposes fixes but never edits the config.
argument-hint: "[directory (default: current project)] [--format json|markdown|text] [--with-context] [--strict]"
---

# Toolguard Security Audit

Flag security risks in the active toolguard permission configuration. This skill
runs in two passes:

1. **Deterministic pass (always).** A tested Python analyzer (`toolguard-audit`)
   flags known risk patterns. High trust, mechanical, repeatable, zero model
   tokens. This is the authoritative layer.
2. **AI-assisted pass (opt-in).** *After* the deterministic pass, you offer the
   user a deeper, judgement-based assessment that you produce by reasoning about
   the config. Lower and variable trust; each finding carries a confidence level.
   Only run it if the user agrees.

Keep the two passes in **separate, clearly labeled report sections** so the user
can always tell mechanical certainty from model judgement.

## Hard constraints

- **Read-only.** This skill never edits, sorts, or migrates the configuration. It
  reports and proposes. Applying a fix is a separate, explicit user decision (and,
  for now, a manual edit). Do not modify any `toolguard_hook.toml`,
  `settings.json`, or `settings.local.json` as part of this skill.
- **Never mix the two passes.** Deterministic findings are owned by the tool: do
  not invent them, drop them, or re-rank them. Your own judgement-based findings go
  ONLY in the AI-assisted section, never presented as tool output.
- **Deterministic severity is final.** If you disagree with a tool severity, say so
  as commentary in the AI section; leave the deterministic ranking intact.
- **The AI pass is opt-in.** Do not run it without the user's go-ahead.

## Pass 1 -- Deterministic findings

### Run it

Run from the project whose configuration you want to audit (the analyzer discovers
the full hierarchy upward from that directory, exactly as the live hook does).

**Pick the invocation by where you are:**

- **Auditing any normal project** -- use the installed console script. It runs inside
  toolguard's own environment, so the audited project does **not** need toolguard on its
  Python path:
  ```bash
  toolguard-audit --format json
  ```
- **Developing toolguard itself** -- if the current project IS the toolguard source repo
  (its `pyproject.toml` declares `name = "toolguard"` and `toolguard/tools/security_audit.py`
  exists), run the in-repo module so you exercise the **working branch**, not the installed
  release:
  ```bash
  uv run python -m toolguard.tools.security_audit --format json
  ```
- **If `toolguard-audit` is not found** (and you are not in the toolguard repo) -- the
  install is too old or partial (it predates this tool). Tell the user and suggest
  `uv tool upgrade toolguard`. Do **not** fall back to the `uv run python -m ...` form on an
  arbitrary project: that only works inside the toolguard source tree, and will fail
  confusingly elsewhere (the target project has no toolguard to import).

> **Prerequisite under toolguard governance (self-permissioning).** When toolguard governs
> the current project (especially in takeover mode), running `toolguard-audit` is itself a
> `Bash` command toolguard must permit -- otherwise this skill's own call is denied. Toolguard
> never self-grants; the fix is an explicit, consented rule at the scope the skill is
> installed. The concrete rule (bake it in -- a denied call cannot run a tool to compute it):
> add **`Bash(toolguard-audit:*)` to allow** (read-only, so a standing allow is fine). If you
> hit a denial of `toolguard-audit`, tell the user that exact rule and retry once added. The
> mutating `toolguard-maintain` is handled by the maintenance skill and belongs in **ask**,
> not allow (see its Self-permissioning section). Hook entry points (`toolguard`,
> `toolguard-session-start`) run under the hook machinery and never need an allow rule.

Useful options:

- `--dir DIR` -- audit a different project directory (default: current directory).
- `--format json|markdown|text` -- use **json** when you are going to interpret and
  re-present the findings (it is the structured contract); use `markdown`/`text`
  only when the user just wants the raw report.
- `--strict` -- exit code becomes the highest severity (1=LOW .. 4=CRITICAL), 0 when
  clean. Useful for scripted/CI gating; not needed for interactive use.
- `--with-context` -- (json only) add the consolidated config `context` block used by
  Pass 2 below. Not needed for the deterministic pass itself.

Parse the JSON. Its shape:

```
{
  "takeover_active":   bool,
  "highest_severity":  int,            // 0 when no findings
  "counts":            { "CRITICAL": n, "HIGH": n, ... },  // only labels that occur
  "findings": [
    {
      "source":          "rule" | "takeover",  // rule = dangerous allow pattern;
                                               // takeover = takeover-mode invariant
      "finding_id":      str,    // e.g. "arbitrary-exec-allow", "hook-not-registered"
      "severity_label":  str,    // CRITICAL | HIGH | MEDIUM | LOW
      "severity_value":  int,    // 4=CRITICAL .. 1=LOW (numeric form of the label)
      "tool":            str?,   // governed tool, or null for config-wide findings
      "locus":           str?,   // which config level/source produced it
      "pattern":         str?,   // the flagged rule (rule findings only)
      "summary":         str,    // what is wrong
      "impact":          str,    // extra impact text (takeover findings)
      "remediation":     str,    // suggested fix (HUMAN text; may be more surgical
                                 // than the structured proposal below)
      "remediation_proposal": obj?,  // STRUCTURED, machine-appliable fix or null.
                                 // Present when the fix is mechanical (delete a
                                 // dangerous allow, anchor an unanchored regex).
                                 // Shape = an EditProposal:
                                 //   { action: remove|replace|narrow|move,
                                 //     tool, rationale, origin: "audit:<finding_id>",
                                 //     edits: [ { tool, list_type, provenance,
                                 //                removed_patterns, added_patterns } ] }
                                 // The maintenance skill ingests this directly (no
                                 // NLP) to build a reviewable edit; it is a
                                 // CONSERVATIVE tightening to review as-if-enacted,
                                 // never auto-applied. null => text-only judgement fix.
      "takeover_active": bool,   // whether takeover was ON when this finding fired
      "acknowledged":    bool,   // true when the flagged rule carries a #NOSECURITY
                                 // comment: the user has BLESSED this risk here.
                                 // Still reported (never hidden), but de-prioritized
                                 // (sorted after every un-acknowledged finding).
      "acknowledgement": str?    // the #NOSECURITY reason ("" for a bare tag), or null
    }, ...
  ]
}
```

### Acknowledged (`#NOSECURITY`) findings

A rule annotated with a `#NOSECURITY[: reason]` comment is **acknowledged, not
hidden**: it still appears in the report, flagged `acknowledged` with its reason,
and sorted last. Treat it as an intentional, project-local risk the user already
accepted -- do NOT re-raise it as a fresh headline or propose removing it. Do
still surface it (transparency), and if a #NOSECURITY rule genuinely became far
more dangerous than its reason covers, say so explicitly rather than silently
trusting the tag. When `context` is present, each layer's `comments[]` carries the
recovered `leading`/`inline` text and a `nosecurity_reason` per commented rule.

> **Structured remediation = the agent audience.** For a human, present the
> `remediation` text. For a driving skill (maintenance), `remediation_proposal` is
> the agent-oriented sidecar: a typed `EditProposal` the skill can enact via
> `edit_proposal.apply_edits` and re-audit as-if-enacted. There is no separate
> "agent mode" -- the same `--format json` serves both, humans reading the text
> and skills reading the proposal.

### Present it

**Use the canonical layout (this is also what Pass 2 must match).** Present the
deterministic findings in the renderer's own structure -- either show the
`toolguard-audit --format markdown` output as-is, or reproduce that exact shape:

```
# Toolguard Security Audit

**Takeover mode: ACTIVE**

CRITICAL: n  HIGH: n  MEDIUM: n  LOW: n

## CRITICAL

- **[finding_id]** source=rule  tool=Bash
  - pattern: `...`            (omit if null)
  - locus: ...                (omit if null)
  - summary: ...
  - impact: ...               (omit if empty)
  - remediation: ...
```

Do **not** invent your own heading style (no `### CRITICAL . takeover . ...`
constructions). Group `## SEVERITY` highest-first; within a severity keep rule and
takeover findings together. Add your interpretation/caveats as prose **below** the
finding block -- never by restructuring the items. Explain in the user's config terms,
but keep the layout above intact so Pass 1 and Pass 2 read as one report.

4. **Be honest about takeover context.** Some findings are CRITICAL *only because*
   takeover mode is active (a blanket allow outside takeover is a full governance
   bypass; the same rule is benign when toolguard is not the gatekeeper). Conversely,
   if takeover is active but the hook is not fully registered, the whole governance
   model is silently off -- surface that loudly.

5. **Propose, do not apply.** Offer each concrete remediation, but make the edit the
   user's call. The rule-maintenance tooling (sorting/consolidation/migration) is the
   right vehicle for applying fixes, not this audit skill.

If `highest_severity` is 0, say the deterministic pass found nothing -- then still
offer Pass 2 (the AI pass can surface risks the detectors do not cover).

## Pass 2 -- AI-assisted assessment (opt-in)

After presenting Pass 1, **offer** the user the deeper assessment. Make the
trade-off explicit, e.g.: "I can also do an AI-assisted assessment -- deeper and
able to catch semantic or combinational risks the deterministic detectors miss, but
it is judgement-based, not deterministic, may include false positives, and costs
model tokens. Want me to run it?" Proceed only if they agree.

### Inputs -- analyze the same consolidated material the deterministic pass did

Do **not** eyeball config files by hand or guess at the hierarchy -- get the exact
same consolidated material the deterministic analyzers used, from one call:

```bash
toolguard-audit --format json --with-context
# dev checkout: uv run python -m toolguard.tools.security_audit --format json --with-context
```

That JSON is the Pass-1 payload plus an additive top-level `context` block:

```
"context": {
  "summary": { "sources": [...],          // every discovered config file, specific-first
               "governed_tools": [...],    // tools toolguard actually governs
               "layer_count": int, ... },
  "takeover": {
    "enabled": bool,                       // the DETERMINISTIC takeover verdict -- trust it
    "no_match_fallback": "deny" | "warn_deny",
    "ignored_allow_patterns": [...],       // native blanket allows takeover suppresses
    "additional_ignored_patterns": [...],
    "conflict": str | null,                // cross-level takeover disagreement, if any
    "neutralized_allow_patterns": [...]    // THE IGNORE-LIST: allow bodies neutralized
                                           // by takeover -- do NOT flag these as risks
  },
  "tools": [                               // the FULL rule hierarchy, per tool
    { "tool": "Bash", "layers": [
        { "locus": str,                    // which config file/level
          "is_native": bool,               // true = Claude-native settings; false = toolguard
          "allow": [...], "deny": [...], "ask": [...],   // wrapper-free pattern bodies
          "comments": [                    // per-rule comments recovered from the file
            { "list_type": str, "pattern": str,          //   (toml layers only; #NOSECURITY
              "leading": str, "inline": str,             //   lives here). Empty for json layers
              "nosecurity_reason": str? } ] }            //   and uncommented rules.
    ]} ],
  "proposed_migrations": [...]             // OPTIONAL -- present only when the audit was run
                                           // with --migrations; see "Proposed migrations" below
  "proposed_edits": {                      // OPTIONAL -- present only with --edits. The
    "edits": [...],                        //   whole audit above is ALREADY as-if-enacted;
    "delta": { "introduced": [...],        //   see "Proposed edits" below.
               "resolved": [...] } }
}
```

Ground your analysis in this block:

- **Analyze the whole hierarchy AND both rule systems.** Every layer in `tools[].layers`
  is in scope -- walk all of them, most-specific first. Reason about *both* the
  toolguard rules (`is_native=false`) **and** the Claude-native permission rules
  (`is_native=true`); the native rules are collected here the same deterministic way,
  and a risk can live in either system or in how a more-specific layer overrides a
  broader one.
- **Consume the takeover verdict; never re-derive it.** `takeover.enabled` is the
  deterministic answer for whether toolguard is the real gatekeeper -- take it as given.
  When it is `true`, toolguard (not Claude) enforces permissions, so over-broad *native*
  allows are expected setup, not risks; the most dangerous failure is the hook not
  actually being registered (Pass 1 already checks that). When it is `false`, native
  allows are live and a blanket native allow is a real exposure.
- **Honor the ignore-list.** Treat every pattern in
  `takeover.neutralized_allow_patterns` as already-handled: do **not** raise findings
  about those native blanket allows -- the deterministic pass has determined takeover
  neutralizes them. Spend your judgement on what the detectors *cannot* see.

### What to analyze

Reason about the *actual* config (cite real patterns and loci -- no hypotheticals).
Look for what the deterministic detectors cannot, for example:

- **Combinational escapes** -- individually-benign allow rules that together enable
  a bypass (e.g. an allowed file write into a directory plus an allowed command that
  executes from it).
- **Over-broad matches** -- globs/regexes whose real-world match set is far wider or
  more dangerous than it looks; deny rules that are trivially side-stepped by an
  equivalent command spelling.
- **Less-obvious execution / exfiltration** -- allows that grant code execution or
  network egress via non-obvious binaries or subcommands (make, cmake, npm/yarn
  scripts, git hooks/aliases, package installers, `ssh`, `curl|sh`, etc.).
- **Missing hardening** -- deny patterns a hardened config *should* have given the
  governed tools and the takeover state, but does not.
- **Takeover reasoning** beyond the mechanical invariants the tool already checks.

Do **not** restate deterministic findings. You may cross-reference one via a
`relates-to` line. Anchor every finding to something concrete in the config.

### Remediations -- offer a concrete, usable fix

For every finding, propose a remediation the user can paste in, not just a
description of the problem:

- **Exhaustive, not illustrative.** Cover EVERY case you flagged. "here is a fix for
  `cat`, do the same for the others" is not acceptable -- spell them all out.
- **Simple over clever.** Prefer an anchored, readable rule a developer can edit over
  a maximally-precise one. Anchor regexes (`^`) and keep them legible; do NOT emit
  giant regexes.
- **A remediation may span multiple rules AND multiple sections.** It is often better
  to keep a broad allow and ADD targeted `deny` rules than to contort one allow. Deny
  the dangerous FILE/operation by token (one deny covers every reader) rather than
  enumerating tools.
- **Use the structurally-correct layer.** Read/Edit/Write of secret files is best
  denied at the file-tool layer (real path-glob semantics); but note Bash readers
  (`cat .env`) bypass that, so a Bash deny is still needed.
- **Arbitrary execution -> recommend DELETION** (or replacement by specific allows),
  never a rewrite that keeps the escape hatch.

Few-shot examples (style, not a fixed catalogue):

1. **Inline replacement** -- complete an incomplete guard:
   - finding: `Bash([regex]\bfind\b(?!.*\s-(exec|execdir|delete)\b))` misses the write
     trapdoors `-fprintf`/`-fprint`/`-fls`/`-ok`/`-okdir`.
   - fix (replace the one rule):
     `Bash([regex]\bfind\b(?!.*\s-(exec|execdir|ok|okdir|delete|fprintf|fprint|fls)\b))`

2. **Rule combination across sections** -- close a secret-read gap without narrowing
   normal use (KEEP the broad allows; ADD denies; deny by file token, not per reader):
   - finding: `.env`/`.ssh` reads slip through un-denied tools (`grep .env`, `tail ~/.ssh/id_rsa`).
   - fix (add these denies):
     `Bash([regex]\.env\b)`        -- any Bash command naming a .env file (all readers)
     `Bash([regex]/\.ssh/)`        -- any Bash command touching a .ssh path
     `Read([glob]**/.env)` `Read([glob]**/.ssh/**)`  -- the Read/Edit/Write tool path

3. **Delete outright** -- arbitrary execution:
   - finding: `Bash(uv run python:*)` is an arbitrary-exec escape hatch.
   - fix: REMOVE it. If specific scripts are needed, allow them explicitly, e.g.
     `Bash(uv run python ./bin/known_script.py)`.

4. **Anchor an unanchored allow:**
   - finding: `Bash([regex]rm /home/.../memory/.*)` is unanchored (`re.search`) -- it
     matches the substring anywhere in a command.
   - fix: `Bash([regex]^rm /home/.../memory/[^;&|]*$)`.

### Proposed edits (ONLY when `context.proposed_edits` is present -- otherwise skip entirely)

This block appears when the audit was invoked with `--edits` (typically the
maintenance skill handing you the concrete changes it wants to make -- e.g. its
consolidations, or your own `remediation_proposal`s it decided to apply). Unlike
`--migrations`, these edits were **actually applied in memory**, so the top-level
`findings` you already analysed reflect the **AS-IF-ENACTED** config (the whole
hierarchy, all sections). Your job is to judge whether enacting the edits is safe.

`context.proposed_edits` carries:

- `edits` -- the `EditProposal`s that were applied (each an `action`, `tool`,
  `rationale`, `origin`, and atomic `edits[]` with `list_type`/`provenance`/
  `removed_patterns`/`added_patterns`). An edit may span several sections
  (allow + deny) and layers.
- `delta` -- `introduced` and `resolved`: the findings that appear ONLY after the
  edits, and ONLY before them.

How to reason:

- **`delta.introduced` is the headline risk.** Any finding the edits CREATE is a
  reason to push back -- call each one out with its severity and say which edit
  caused it. A change that resolves one MEDIUM but introduces a CRITICAL is a bad
  trade; say so plainly.
- **`delta.resolved` is the benefit.** Acknowledge what the edits fix.
- **Look past the delta for cross-section / cross-layer interactions.** Replacing
  one rule with a set (e.g. narrow an allow AND add a deny) can change how a
  DIFFERENT rule for the same command family resolves, even when no finding id
  changed. Walk the as-if-enacted `tools[].layers` for the edited command family
  and confirm the effective verdict is what the edit intends (deny-wins;
  broad-ask-collapses; else more-specific-wins).
- **These findings are REAL for the proposed state, not hypothetical** -- be
  concrete, cite the actual patterns/loci in the as-if-enacted config.
- Give a clear bottom line: safe to enact, enact-with-changes (name them), or do
  not enact (why).

### Proposed migrations (ONLY when `context.proposed_migrations` is present -- otherwise skip entirely)

**If `proposed_migrations` is absent (the normal case for a plain permission
review), SKIP this whole section.** You NEVER propose or invent migrations yourself
-- you only risk-assess moves explicitly handed to you via `--migrations` (typically
when the maintenance skill invokes this audit). When the array IS present, assess the
risk of each migration **as if it were enacted in full**, and fold those findings
into this same AI section.

Each entry carries: `tool`, `list_type`, `pattern`, `from_locus`/`to_locus`,
`from_specificity`/`to_specificity` (lower = more specific), `decision_neutral`,
`broadened_count`/`tightened_count`, and a `scope_note`.

- **`decision_neutral` is NOT a safety proof.** It only means the move changed no
  decision over the harvested corpus of *this* context. It says nothing about
  developer intent or about contexts the corpus never exercised. A migration can be
  `decision_neutral: true` and still be risky -- this is exactly where your
  judgement is needed.
- **Focus on rules for the SAME command / command family across BOTH sections and
  layers.** A migration that relocates an allow (or deny) can change how it composes
  with a deny/ask/allow for a related command that stays put. Look especially for:
  - **Allow broadened past a deny.** Promoting a broad allow (e.g. `git:*`) up to a
    user layer while a more-specific deny the developer relies on (e.g. a reserved
    `git push`) stays at the project layer -- or vice versa -- may let the allow win
    in contexts where the deny no longer applies. This is NOT a read/write boundary;
    it is a deliberate carve-out that the split can silently defeat.
  - **Orphaned / split guards.** A deny and the allow it was carving an exception
    out of becoming separated across layers, so the pair no longer resolves as the
    author intended.
  - **Cross-context broadening.** A promotion applies the rule to every project the
    broader layer governs; the corpus cannot see those other projects. Flag the
    breadth the user is signing up for.
- **You cannot fully prove these; the developer decides.** Raise each as a finding
  with an honest severity and confidence, name the specific interacting rules and
  loci, state what intent the move *might* defeat, and explicitly leave the final
  call to the developer. Prefer flagging a plausible intent-defeating split even at
  `MEDIUM`/`LOW` confidence over staying silent.

### Severity and confidence

- **Severity**: CRITICAL / HIGH / MEDIUM / LOW -- same scale as Pass 1.
- **Confidence** (ordinal, your own honest calibration of whether this is a true
  risk *in this config*):
  - `HIGH` -- concrete and demonstrable; you can point to the exact mechanism.
  - `MEDIUM` -- plausible; depends on usage or context you cannot fully verify.
  - `LOW` -- speculative; worth a glance but easily a false positive.

Do not emit numeric confidence scores -- ordinal only (LLM numeric confidence is not
well-calibrated and implies false precision).

### Present it -- separate section, same style

Render the AI section in the **exact same layout** as the Pass-1 canonical format
above (same `# title`, the `CRITICAL: n  HIGH: n  MEDIUM: n  LOW: n` counts line, the
`## SEVERITY` groups, and the `- **[id]** source=...  tool=...` items with `  - field:`
sub-bullets). The ONLY differences from Pass 1 are: `source=ai`, an added
`confidence=` field on the item line, an optional `relates-to:` sub-bullet, and the
disclaimer header. If you showed Pass 1 in `text` format, use the text template instead
so both match. The two sections must look like one continuous report -- do not switch
heading styles or field formatting between them. Sort by **severity descending, then
confidence descending**, then by slug.

Markdown template:

```
# AI-Assisted Security Assessment

> Judgement-based, NOT deterministic. These are model-reasoned leads to verify,
> each with a confidence level -- they are not as authoritative as the
> deterministic findings above and may include false positives.

CRITICAL: n  HIGH: n  MEDIUM: n  LOW: n

## CRITICAL

- **[short-kebab-slug]** source=ai  confidence=HIGH  tool=Bash
  - pattern: `...`                 (if a specific rule is implicated)
  - locus: ...                     (config level/file, if known)
  - relates-to: arbitrary-exec-allow   (optional; a Pass-1 finding_id)
  - summary: ...
  - impact: ...                    (optional)
  - remediation: ...
```

Text template:

```
AI-Assisted Security Assessment
===============================

(Judgement-based, NOT deterministic -- verify before acting. May include false
positives. Confidence is ordinal.)

CRITICAL: n  HIGH: n  MEDIUM: n  LOW: n

[CRITICAL]
----------
  [short-kebab-slug]  source=ai  confidence=HIGH  tool=Bash
    pattern     : ...
    locus       : ...
    relates-to  : ...
    summary     : ...
    impact      : ...
    remediation : ...
```

Omit optional lines (`pattern`, `locus`, `relates-to`, `impact`) when they do not
apply, exactly as the deterministic renderer omits empty fields. If the AI pass
finds nothing, say so plainly under the section header rather than fabricating
filler.

## When to use

- On demand: "audit my toolguard security", "are any of my allow rules dangerous?",
  "is takeover mode set up safely?", "review my permission config for risks".
- As a start-of-session safety check when working in a security-sensitive repo or
  right after editing permission rules.

## Notes

- The deterministic analyzer is offline -- it reads only local config files, makes
  no network calls, and costs no model tokens to run.
- A clean deterministic report means no *known* risk patterns matched; it is not a
  proof of safety. That is exactly what the opt-in AI pass is for.
- The deterministic and AI passes have deliberately different trust levels. Keep them
  visually and verbally distinct so the user never confuses a mechanical certainty
  with a model hunch.
