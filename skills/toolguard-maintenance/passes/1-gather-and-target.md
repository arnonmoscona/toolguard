# Pass 1 -- Gather and target

**Goal:** produce a populated *recommendation set* (schema:
`recommendation-set-schema.md`) in which every rule of every governed tool is
grouped into a command family, each proposed change is attached to its family with
evidence, and each change has been assigned a target level (with cross-level welds
blocked). No consolidation refinement and no narrative yet -- those are pass 2.

Read `../SKILL.md` first for the invocation rules, the JSON contracts, and the hard
constraints. This pass is entirely read-only.

## Step 1 -- gather evidence (four tool calls)

Pick the invocation form (installed console script vs in-repo module) per SKILL.md.
Run, capturing each to the session scratchpad:

1. **Findings** -- `toolguard-maintain --format json`
   (add `--corpus --max-age-days N` only if the user asked for usage-evidence-driven
   findings; warn it is slow).
2. **Full config + audit** -- `toolguard-audit --format json --with-context`.
   `context.tools[].layers` is your authoritative, wrapper-free view of **every**
   rule in **every** section across the whole hierarchy -- this is what you group.
3. **Candidate edits** -- `toolguard-maintain --apply --format json` (a dry-run;
   `files_written` must be `[]`). Its `edit_proposals` are the tool's machine-shaped
   consolidation candidates, and `withheld_nosecurity` lists rules a tidy-up
   deliberately skipped.
4. **Prior decisions** -- `toolguard-maintain --ledger-show --format json` (read-only).
   This merges the project ledger (`<root>/.claude/toolguard_decisions.json`) and the
   user ledger (`~/.toolguard/decisions.json`) into a flat list of settled
   meta-decisions the user made on a previous run. Each entry has `kind`, `family_id`,
   `target`, `decision`, and `rationale`. A `decision: "reject"` entry means "do not
   re-raise this" -- you will use it in Step 4 to keep a periodic run quiet. An empty
   list is normal on a first run. If the call reports a malformed ledger (exit 2), tell
   the user and proceed as if empty rather than guessing.

If a self-permission denial blocks a call, follow SKILL.md's Self-permissioning
section (suggest the exact rule, get consent, retry) -- do not work around it.

## Step 2 -- initialise the recommendation set

Create the JSON document per the schema. Fill `meta` (`project_dir`,
`generated_at` in local time, `toolguard_version`; set `trust_level` to a neutral
default). Leave `audit`, `corpus_validation`, `certification`, and `final_toml` null
-- later passes fill them.

**Determine `run_kind`** (see SKILL.md "First run vs periodic"). If the current
config already carries `# toolguard:` annotations, OR the prior-decision ledger
(Step 1 call 4) is non-empty, this project has been maintained before -- lean
`"periodic"`. If it plainly has not, or you cannot tell, ASK the user and default to
`"first"` when unsure (the safe default discusses more, never less). While walking the
config in Step 3, note which rules already carry a prior in-file decision
(`# toolguard:` or `#NOSECURITY: <reason>`): those are settled and a periodic run must
not re-litigate them.

**Load the prior-decision ledger into memory.** Keep the Step 1 call-4 list at hand as
the settled-meta-decision index, keyed by `(kind, family_id, target)`. It complements
the in-file annotations: annotations settle decisions attached to a surviving rule; the
ledger settles META-decisions with no rule to hang on (a rejected merge, a rejected
promotion). Step 4 consults it to suppress re-raising what the user already declined.

## Step 3 -- group every rule into command families

From `context.tools[].layers`, walk **every** layer and **every** section
(`allow`/`deny`/`ask`; `hard_deny` where present), for every governed tool.

> **`context.tools[]` is not the governed-tool list -- reconcile the two.** The
> authoritative set of governed tools is `context.summary.governed_tools`;
> `context.tools[]` does not match it in either direction. It can INCLUDE native-only
> tools that toolguard does not govern (`Skill`, `WebFetch`) -- skip those -- and it can
> OMIT a governed tool that carries rules (observed: an `mcp__local-tools__checked_bash`
> blanket deny lived only in the raw TOML, invisible to `context.tools[]`). So: take the
> governed set from `governed_tools`, and for any governed tool NOT represented in
> `context.tools[]`, read its `[permissions."<tool>"]` rules from the toolguard TOML
> directly (same as Step 6 does for non-permission tables). Otherwise the "union equals
> the full config" invariant below is quietly violated -- a governed deny goes unseen.

- A **family** is a set of rules that share a leading command signature -- the same
  head token(s) before the first variable part. Examples from a real config:
  `git` (`git diff`, `git status`, ...), `mkdir -p`, `uv run alembic`, `uv run
  python`, bare readers like `head`/`tail`/`cat`. Use judgement: `uv run alembic`
  is a more useful family than `uv`, because its members clearly co-vary.
- Create one family per signature. Add **every** rule as a `member` with its
  `pattern`, `section`, `locus` (the provenance `describe`), and its level (from
  provenance `level`). Default `status: "no-change"` -- a rule only gets a change
  status when a finding or your targeting gives it one.
- A rule that legitimately belongs to no family (a lone one-off) is still its own
  single-member family, so nothing is dropped from the final picture.

The invariant that makes the eventual report trustworthy: **after this step the
union of all family members equals the full config.** Unchanged rules are first-class.

## Step 4 -- overlay the findings onto members (evidence, not decisions)

Attach each finding to the member(s) it concerns and record its `source_finding_ids`
and `flags`. Do **not** yet decide anything -- you are annotating candidates.

- **redundancies** and **cross_layer_redundancies** -> mark the redundant member
  `status:"remove"` (candidate), noting in `rationale` what covers it. These are
  the safest class (exact/normalised duplicate, or already covered by a broader
  layer) but still the user's call. **Note the tooling asymmetry:** redundancy
  removals are NOT in the `--apply` `edit_proposals` (that dry-run carries only
  strict *consolidations* -- `collect_consolidations`). So a `remove` here is a
  candidate the user hand-applies from the certified TOML, not something
  `toolguard-maintain --apply --write` will enact. Do not expect to find it there.
- **consolidations** (`edit_proposals`) -> for each, mark the removed members
  `status:"consolidate"` with `into` = the proposed `added_pattern`, sharing one
  rationale. Carry the `replay_summary` as evidence. **These are candidates the tool
  found by single-token literal alternation -- pass 2 re-judges them.** They are the
  ONLY finding class present in `--apply` `edit_proposals`.
- **broadenings** -> do NOT set a change status. Add a `needs-discussion` flag and a
  `discussion` entry on the family: a broadening widens what is permitted and is
  always the user's decision. Record `newly_admitted_commands` /
  `overlaps_guard_rules` as the evidence to show.
- **interactions** (ask-overlaps-allow, deny-shadows-allow, ...) -> attach to the
  family as a single `discussion` entry, not per-member noise. If several
  interactions share an identical guard (e.g. one `ask uv run alembic:*` overlapping
  five allows), record them as **one** discussion point naming all the members, not
  five. Keep the tool's `explanation` as the seed text.
- **withheld_nosecurity** -> flag those members `nosecurity` and never propose
  changing them; they are surfaced for transparency only.
- **mining groups** (corpus runs) -> attach as evidence to the relevant family.
- **Settled meta-decisions -> pre-mark, do not drop.** For each candidate you overlay
  (a consolidation, a promotion, a broadening), form its `(kind, family_id, target)`
  key and look it up in the ledger loaded in Step 2. On a `decision: "reject"` match,
  pre-seed the member's `user_decision: "reject"` (with the ledger's `rationale` as
  `user_note`) and add a `settled` flag. Do NOT delete the member -- it stays in the
  family view so the final state is still reconstructable. The `settled` flag tells
  pass 4 to stay silent about it on a periodic run, while a first run or an explicit
  re-review may still revisit it. Never let the ledger auto-ENACT anything; it only
  suppresses re-RAISING a settled question.
- **Cross-cutting finding -> one owning family.** A finding that spans several
  families (a tool-agnostic deny that subsumes per-reader denies belonging to
  different families, an interaction naming members of more than one family, a
  broadening that fuses across signatures) is assigned to a SINGLE owning family --
  the one whose command signature it reads under most naturally (for a secret-read
  deny, the secret token like `.env`/`.ssh`, NOT each individual reader). Cross-
  reference the affected members from that owner. Never duplicate the finding into
  every family it touches (double-counting) nor let it fall between them (dropped).

## Step 5 -- target the level for each proposed change (and block welds)

For every member with a change status, decide the level its result should live at,
and detect welds. **Consolidations stay at their current level** -- a merge never
welds levels (that is the weld rule below). **Promotion is now a first-class proposed
MOVE**, not just an observation: a rule that belongs at a higher level gets
`status:"promote"` and a `target_level`, and is certified and applied as its own
change (see pass 3's promotion-staging and pass 4). A promotion is still NEVER
auto-enacted -- the tool has no cross-level move writer, so it is hand-applied from the
certified two-file TOML; but it IS a real proposal that flows through the rest of the
pipeline, not a passive note. Do the level analysis here because it both gates
consolidation (welds) AND drives the promotion proposals:

- **Cross-level weld (blocking).** If a consolidation's removed members do not all
  share one level, or its `added_pattern` fuses clearly project-specific tokens
  (repo paths, project dirs) with user/machine-generic ones (`/tmp`, `~/.cache`,
  generic subcommands), set the `cross-level-weld` flag on those members and mark
  the consolidation blocked. Pass 2 must split it, not enact it. (This is the
  `mkdir -p /tmp/... + flowers/...` welding case.)
- **Promotion -- a first-class recommendation, biased toward DENY.** Toolguard reads a
  user-level layer too, so rules that should apply everywhere belong there. RECOMMEND
  promotion (do not merely observe it), with an asymmetric bias:
  - **DENY -> promote eagerly.** A deny at the user level restricts *every* project --
    "when in doubt, restrict". Universal safety denies (`.env`/`.ssh` reads, `rm -rf`,
    secret paths under `~`) are almost always better at the user level. Recommend it
    unless the deny is genuinely project-specific policy.
  - **ALLOW -> promote cautiously, but DO survey them -- do not skip the allow side.**
    An allow at the user level *broadens* every project (cross-context broadening the
    corpus cannot see), so the bar is higher than for denies -- but "cautious" means
    *judge each one*, NOT *stay silent on all of them*. Walk **every** allow family and
    classify its promotability, the same as you do for denies:
    - **Benign, project-agnostic, read-only / utility allows are genuine candidates.**
      Ubiquitous dev-machine commands the user runs everywhere -- `echo`, `ls`, `du`,
      `date`, `sleep`, `ps`, `wc`, `sort`, `ag`/`ack`, `pbcopy`, `git diff|status|log`,
      and similar -- are clearly project-agnostic and low-risk. Surface these as
      promotion candidates (recommend, do not merely observe); do not leave them silent
      under a bare `no-change`.
    - **Reader allows are COUPLED to the secret denies -- flag it.** `grep`, `head`,
      `tail`, `cat`, `find` and friends can read secret files, so promoting THEIR allows
      is only safe alongside the `.env`/`.ssh` (and similar) denies at the same-or-higher
      precedence. Recommend promoting these readers only *together with* the guarding
      secret denies (deny out-ranks allow), and say so; never promote a reader allow to
      the user level while leaving the secret deny project-local.
    - **Never promote execution-broad allows** (`uv run python:*`, blanket interpreters,
      `curl` to arbitrary hosts) -- those broaden arbitrary execution everywhere.
    To avoid per-rule noise, you MAY group the clearly-benign utility allows into ONE
    promotion candidate ("these N read-only utility allows -> promote as a batch") rather
    than a separate entry each -- but the survey itself is not optional: a harmless allow
    left un-promotable-assessed is a missed recommendation, exactly the gap to avoid.
  Set `status:"promote"` and `target_level:"user"` on the member, add the `promotion`
  flag, and record the reasoning in `rationale`. The member's `pattern` is unchanged
  (a move, not a rewrite); the before->after is "project rule -> same rule at user
  level". Do not enact the move; it is certified in pass 3 and hand-applied in pass 4.
  A promotion the user declines is recorded in the ledger as `reject-promotion`
  (pass 4), so a periodic run does not re-raise it.
- **Incomplete-config guard -- attach to EVERY promotion recommendation.** A user-level
  toolguard *rule* only takes effect where toolguard actually runs. If the user level
  lacks the FULL toolguard setup -- the hook registered globally AND the base config
  (takeover / governed_tools) -- then projects with no toolguard config are governed by
  Claude-native rules alone, and the promoted rule silently does nothing there: a false
  sense of security, worst for a safety deny. From `config_settings`, check whether a
  complete user-level toolguard setup exists; if not, the promotion recommendation MUST
  carry a strong admonition -- promote the rule AND stand up the full user-level setup
  *together*, never rules without the setup. Do not drop the recommendation; pair it
  with the warning.

## Step 6 -- capture the top-level configuration settings (not permission rules)

The `[permissions]` rules do not stand alone: the toolguard config also carries top-level
options that shape how ALL those rules behave. Capture them into `config_settings` so pass
3 can surface them -- the maintenance analyzer never touches them, and silently cleaning
permissions while leaving these in an incoherent state is exactly the "unintended mess" to
avoid.

Source them structurally where possible: the audit `context` already exposes
`context.takeover` (enabled, `no_match_fallback`, `ignored_allow_patterns`, cross-level
`conflict`), `context.summary.governed_tools`, and `context.summary.sources` (the levels).
Note these live UNDER `context` -- the top-level `summary` key is null; use
`context.summary.*`. For settings the contract
does not expose (`[config_sync]` -- `auto_migrate`/`backup_dir`/`auto_sort_on_migrate` --
and `additional_supported_tools`), read the toolguard TOML's non-permission tables
directly. (This is reading declared key/values, not re-deriving permission-rule semantics
by hand -- that prohibition is about findings, not config metadata. That the contract does
not yet expose all of these is a known limitation / future tool enhancement.)

For each setting record an observation: `key`, `value`, `locus`/`level`, and classify:

- **`category`** -- `semantic` (changes how rules resolve: **`takeover_mode.enabled`**,
  `no_match_fallback`, the ignore-lists, `governed_tools`), `operational` (`backup_dir`,
  `auto_migrate`), or `preference` (`auto_sort_on_migrate`).
- **`cross_config`** -- true when it interacts with the Claude-native config or with other
  levels. **Takeover is the critical one**: it makes toolguard (not Claude) the gatekeeper
  and neutralizes native blanket allows, so a project WITHOUT it is governed differently --
  a cross-project coherence hazard entangled with the native `settings.local.json`.
- **`promotion_candidate`** -- toolguard's general configuration should TEND to
  centralize at the user level (less per-project setup to get right, fewer future
  contradictions/incompleteness). True for takeover posture, `no_match_fallback`,
  `governed_tools` (**including dev-tooling MCP tools** -- these are
  user-dev-tooling-specific, not truly project-specific; listing a tool a given project
  does not use is a harmless superset, so it does not block centralization), and
  `auto_sort`. Only genuinely project-relative settings stay project-level (`backup_dir`
  is a project-relative path).
- **`doc_link`** -- the relevant README/documentation section, so the user can read before
  changing a semantic setting. Never propose flipping takeover casually.

Detect and record cross-level `conflict` (from `takeover`) if present -- disagreement
about takeover across levels is a loud finding.

## Output of this pass

The recommendation set with: all families populated (unchanged members included),
change candidates marked with evidence and flags, cross-level welds blocked, and
level observations recorded. Hand off to `2-consolidate-and-group.md`. Do not
present anything to the user yet -- the family view is not ready until pass 2 has
refined the merges and written the narratives.
