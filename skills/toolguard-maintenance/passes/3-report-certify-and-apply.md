# Pass 3 -- Report, certify, and apply

**Goal:** present the proposal so the user can understand and decide it, prove the
proposed config is sound with the tool, and enact -- case by case, on explicit
consent -- only what the user approves. This is the pass that finally talks to the
user and (only then) may write.

Read `../SKILL.md` (hard constraints, tool reference, self-permissioning) and
`recommendation-set-schema.md` first. Input: the fully-annotated recommendation set
from pass 2.

## Step 1 -- render the understanding view (for comprehension, not paste)

Group by **command family**. For each family, in this order:

- A one-line header: family label, tool, rule count, and a status summary
  (e.g. "uv run alembic -- Bash -- 6 rules: 2 consolidate, 1 needs discussion, 3 no-change").
- The **members table/list across all sections**, each marked
  `[no-change] | [edit] | [consolidate] | [remove] | [new] | [promote?]`, showing the
  pattern and its section, and for changes a **before -> after**. **Show unchanged
  rules too** -- the reader must be able to reconstruct the family's final state.
- The **narrative** paragraph from pass 2.
- Any **discussion questions** for this family, called out clearly (broadening
  opportunity, heterogeneity outlier, promotion opportunity, persisting
  ask/deny interaction). These are the decisions you are asking the user to make.

Sort families with the most-consequential first (families with changes or open
questions before all-`no-change` families). Keep the tool's `explanation` text for
interactions rather than re-deriving resolution semantics. ASCII only.

Do not bury a section/deny/hard_deny change inside an allow discussion -- if a change
spans sections, show each section's line under the same family.

## Step 1b -- render the configuration-settings section (detect and inform)

After the families, add a distinct **"Configuration settings (not permission rules)"**
section from `config_settings`. These are not changed by this run; the goal is to make
sure a permission cleanup does not leave the *semantics* in an unintended, incoherent
state. For each observation, state the setting, its level, and what it means -- and:

- **Lead with `takeover_mode`, framed accurately: it is RESTRICTIVE, not broadening.**
  Takeover makes toolguard (not Claude) the gatekeeper for governed tools, neutralizes
  the *blanket* native allows (`Bash(*)` etc.), and applies a fail-closed default. Its
  point is convenience and centralization -- one permission system instead of two. A
  broad native allow does NOT broaden toolguard; it only broadens Claude's own
  auto-approval, which the hook overrides. **Do not alarm the user about takeover being
  on.** The real failure conditions are narrow -- check and flag only these:
  1. **Hook not registered** -- `enabled = true` is inert unless the PreToolUse hook is
     actually wired into Claude's settings. Flag on + hook missing = the illusion of
     governance while native rules decide. Surface loudly if present.
  2. **Ungoverned broad native allow** -- a broad native allow on a tool that no toolguard
     layer governs (not in `governed_tools`, or no toolguard at that level) runs under
     Claude alone. (Takeover neutralizes only *blanket* native allows; a *specific* native
     allow is still honored as a toolguard layer, so native config can still broaden
     toolguard via non-blanket allows.)
  Otherwise, overlapping governance is at most a double-prompt annoyance. Link the docs;
  do not tell the user to flip a semantic setting casually.
- **Incomplete user-level toolguard config -- alert strongly if present.** If there ARE
  toolguard rules at the user level but NOT the full user-level setup (hook registered
  globally + base config), those rules apply only in projects that already run toolguard
  and silently do nothing in toolguard-less projects -- a dangerous false sense of
  security, worst for safety denies. Flag this loudly, and tie it to every promotion
  recommendation (never recommend user-level rules without the full setup).
- Note `promotion_candidate` settings as opportunities (with the cross-context caveat),
  and say which are project-bound and why (`backup_dir`, MCP-specific tools).
- If a cross-level takeover `conflict` was detected, surface it loudly -- it means the
  governance model may be silently off.

- **Lean toward user-level centralization for general config.** Present `governed_tools`
  (including dev-tooling MCP tools), the takeover posture, and `no_match_fallback` as
  things that usually belong at the user level -- centralizing toolguard's general config
  means the user does not re-hook toolguard per project and reduces future
  incompleteness/contradiction. A tool listed but unused in some project is a harmless
  superset, so "project-specific" is not a reason to keep it project-level. Only
  project-relative settings (`backup_dir`) stay project-level.

Make **no concrete auto-change** to these; detect, inform, and link. This is the safeguard
against "cleaned the rules, broke the semantics".

## Step 2 -- render the cut/paste section (exact, paste-ready TOML)

Separate, clearly-labelled section. For each file that would change, emit the
**resulting** TOML -- the section (or whole file if clearer) as it should read
*after* the approved changes, in the tool's final sort order, so the user can paste
it verbatim. This TOML is **authored by you** (the pass 2 merges include judgement
the tool did not make), which is exactly why Step 3 certifies it.

- **One block per affected file**, headed with the file's path -- and that includes
  files at OTHER levels. If a promotion moves a rule to the user layer, render BOTH
  the project file (rule removed) and the user file (rule added). If the target level
  has no toolguard config yet (e.g. the user layer only holds Claude-native settings),
  show the `toolguard_hook.toml` that would be **created** there -- and because rules
  alone at that level are inert without the full setup, the block must ALSO show the
  base config it needs (`[takeover_mode]`, `governed_tools`) plus a plain note that the
  hook must be registered globally, and the strong admonition: do NOT add user-level
  rules without this full setup (a promoted safety deny that never runs is worse than
  none -- it looks protected).
- **Every section present.** Emit `allow`, `deny`, `ask` (and `hard_deny` if used) in
  each block, even when a section is untouched -- an unchanged section gets a
  `# no proposed changes in this section` marker so the user can see it was considered,
  not forgotten. Never show only the section that changed.
- Each section is a **drop-in replacement**: include its surrounding unchanged rules,
  not just the delta, so the user can paste the whole block.
- Preserve `#NOSECURITY` and other user comments verbatim; never rewrite a
  `withheld_nosecurity` rule.
- **Annotate interacting rules inline.** Where a rule's real effect depends on another
  (a more-specific allow that bypasses an `ask`, a broad deny that supersedes specific
  ones, a deny that shadows an allow), add a short trailing `#` comment on the rule --
  e.g. `# more-specific override of ask "Bash(alembic:*)"` or `# broad secret-read deny;
  supersedes the per-reader denies` -- so the resulting file self-documents its
  non-obvious resolutions (same spirit as `--annotate`).
- **Show the recommended END-STATE, folded in -- never contradict yourself.** The block
  is the config *as recommended*, with confident recommendations (redundancy removals,
  deny consolidation/hardening) already applied so the result is actually clean. Do NOT
  leave rules you have called redundant sitting in the block under a `# no proposed
  changes` marker while a separate section says to remove them -- that self-contradiction
  is exactly what a reader will (rightly) call out. Reserve `# no proposed changes` for
  sections that genuinely have none. Only *true* decisions (an unresolved arbitrary-exec
  choice, promotions) stay un-applied -- mark those inline (`# DECISION: see ...`) or in
  clearly-labelled alternative blocks, not as clutter in the main block.

## Step 3 -- certify the assembled TOML with the tool (author by AI, certify by tool)

Never let the user paste un-certified AI-authored TOML. Prove it with the tool:

1. Copy the project's config tree to a temp dir (scratchpad), then overwrite the
   candidate file(s) with your Step-2 TOML. **The temp dir MUST be a recognized
   project root**, or the audit will not discover the staged config at all: it
   discovers config by walking up from a project root (a `.git` dir or equivalent
   marker), so a bare temp dir loads NOTHING. Make it a root (e.g. `git init` the
   temp dir) before auditing.
2. Run `toolguard-audit --dir <tempdir> --format json --with-context` against the
   staged copy.
   - **VERIFY the audit actually loaded your staged config before trusting any
     result.** Check that `context.summary.sources` includes your staged file and
     that `takeover_active` matches the real project (usually `true`). If takeover
     flips to `false`, `sources` shows only user-level JSON, or you see a spurious
     `hook-not-registered` finding, the staging FAILED to load -- the "clean" result
     is false. Do not report it; fix the staging (project root) and re-run. This
     failure is silent and produces a config that looks like it resolved everything.
   - If it **fails to load/parse**, the TOML is wrong -- fix it and repeat; never
     hand the user TOML that does not parse.
   - Compare its findings to the current config's audit (the `audit.before` you
     already have): any **introduced** finding is a blocker to surface, exactly as
     the `--edits` review would flag. A change that resolves a MEDIUM but introduces
     a CRITICAL is a bad trade -- say so.
3. Record the result in the recommendation set `certification`
   (`parses`, `audit_clean`, `notes`). Corpus-replay validation is a later phase;
   for now note it as not-yet-run rather than claiming it.

State the certification outcome to the user with the report: "the proposed config
parses and the security audit is clean / introduces the following ...".

## Step 3a -- let the audit REVISE the proposal, not just gate it

Certification is not only a pass/fail gate -- the audit's judgement should feed back
into the recommendation. For any audit finding that lands on a rule inside a family
you are already presenting (or a prominent CRITICAL/HIGH anywhere in the proposed
config), do not settle for a passive "note the risk"; turn it into a **concrete
alternative** the user can accept:

- Ingest the finding's structured `remediation_proposal` (an `EditProposal`) when the
  audit provides one, and fold it into that family's proposal.
- When it does not, propose the fix yourself, exhaustively and specifically -- but
  **verify your proposed fix against the audit; do not assume it works.** Worked
  example (a real, instructive failure): the audit flags `Bash(uv run python:*)` as
  arbitrary-exec CRITICAL. The tempting move is to scope it to the script directory,
  e.g. `Bash([regex]^uv run python (\./)?\.?bin/)`. Re-certify it and you find the
  audit **still** flags it CRITICAL -- running any Python file is arbitrary code
  execution, so no rewrite of a `uv run python` allow clears the finding (the detector
  flags exact-file script allows too). The honest post-audit recommendation is
  therefore twofold: (a) the tighter `bin/`-scoped rule is still worth it as *hygiene*
  (it limits which scripts run), but present it as hygiene, not a CRITICAL fix; and
  (b) the finding itself cannot be rewritten away -- it is a genuine
  **user decision**: accept the arbitrary-exec risk with an explicit
  `#NOSECURITY: <reason>` (owned and visible), or drop `uv run python` from `allow`
  entirely and invoke scripts another way. Escalate it as a decision; never report a
  tightened rule as though it resolved the finding.
- **When you recommend `#NOSECURITY` on a code-execution allow, warn sternly and
  unambiguously.** State plainly that it permits **ungoverned arbitrary code
  execution**: any command reaching that rule can run anything (read/exfiltrate
  secrets, delete files, reach the network), and **toolguard's current facilities
  cannot analyze what such a script actually does** -- the annotation is a blanket,
  standing exception, not a vetted one. It is a legitimate choice on a single-user dev
  machine, but the user must accept it with eyes open. Do not soft-pedal it; do not
  bury it in a list. (Future pluggable script-classifiers may narrow this, but never
  fully reliably -- do not imply the tooling will catch a bad script.)
- A revision changes the proposal, so **re-certify** the amended config (back to Step
  3). Bound this: one revise + re-audit; if it still is not clean, surface the
  trade-off and let the user decide rather than looping.

The point: a finding that touches what you are already editing must reshape the
recommendation, not sit beside it as a caveat.

## Step 4 -- discuss and apply, case by case, on explicit consent

Present the understanding view + cut/paste section + certification. Then **let the
user drive**:

- Default to **case-by-case**: walk the families with changes or questions, take the
  user's decision (accept / reject / modify), and record it in each member's
  `user_decision` / `user_note`. Answer their questions; if a heterogeneity or
  broadening question changes the plan, update the proposal and re-certify.
- **Bulk-apply only if the user explicitly asks for it** ("just apply it all"). It is
  never the default and never something you label "safe" on their behalf.
- **Self-edit** is always offered: the cut/paste TOML lets the user hand-edit if they
  want full control or to tweak wording.

### Enacting approved changes

- For approved **tool-appliable consolidations** (the pass-1 `edit_proposals`
  subset the user accepted), enact with `toolguard-maintain --apply --write` after a
  final `--apply` dry-run preview shown to the user. Respect the write pre-flight
  (clean tree, resolved root); on refusal relay the blockers and have the user
  commit/stash, then retry. If the user accepted only a subset, prefer guiding a
  self-edit from the certified TOML over applying more than they approved.
- For approved changes the tool cannot mechanically apply (level splits, hand-tuned
  rewrites): have the user paste the certified TOML, or apply via their chosen edit
  path. Do not invent a write mechanism the tool does not provide.
- After presenting clarity interactions, offer `toolguard-maintain --annotate` to
  write `# toolguard:` comments so the config self-documents (comment-only, same
  write gate; preview first).
- **Leave the git commit to the user.**

## Output

Approved changes enacted (or handed off as certified paste-ready TOML); the
recommendation set records every decision (`user_decision`/`user_note`) for the
future prior-decision ledger. Nothing was applied that the user did not explicitly
approve.
