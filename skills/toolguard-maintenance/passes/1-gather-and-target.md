# Pass 1 -- Gather and target

**Goal:** produce a populated *recommendation set* (schema:
`recommendation-set-schema.md`) in which every rule of every governed tool is
grouped into a command family, each proposed change is attached to its family with
evidence, and each change has been assigned a target level (with cross-level welds
blocked). No consolidation refinement and no narrative yet -- those are pass 2.

Read `../SKILL.md` first for the invocation rules, the JSON contracts, and the hard
constraints. This pass is entirely read-only.

## Step 1 -- gather evidence (three tool calls)

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

If a self-permission denial blocks a call, follow SKILL.md's Self-permissioning
section (suggest the exact rule, get consent, retry) -- do not work around it.

## Step 2 -- initialise the recommendation set

Create the JSON document per the schema. Fill `meta` (`project_dir`,
`generated_at` in local time, `toolguard_version`; set `trust_level` to a neutral
default). Leave `audit`, `corpus_validation`, `certification`, and `final_toml` null
-- later passes fill them.

**Determine `run_kind`** (see SKILL.md "First run vs periodic"). If the current
config already carries `# toolguard:` annotations, this project has been maintained
before -- lean `"periodic"`. If it plainly has not, or you cannot tell, ASK the user
and default to `"first"` when unsure (the safe default discusses more, never less).
While walking the config in Step 3, note which rules already carry a prior in-file
decision (`# toolguard:` or `#NOSECURITY: <reason>`): those are settled and a
periodic run must not re-litigate them.

## Step 3 -- group every rule into command families

From `context.tools[].layers`, walk **every** layer and **every** section
(`allow`/`deny`/`ask`; `hard_deny` where present), for every governed tool.

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
  layer) but still the user's call.
- **consolidations** (`edit_proposals`) -> for each, mark the removed members
  `status:"consolidate"` with `into` = the proposed `added_pattern`, sharing one
  rationale. Carry the `replay_summary` as evidence. **These are candidates the tool
  found by single-token literal alternation -- pass 2 re-judges them.**
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
and detect welds. **This pass, keep every change at its current level** (promotion
is being layered in later) -- but still do the analysis and record it, because it
gates consolidation in pass 2:

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
  - **ALLOW -> promote cautiously.** An allow at the user level *broadens* every project
    (cross-context broadening the corpus cannot see). Recommend only for clearly
    project-agnostic, benign allows (e.g. `git diff|status|log`), always with the
    caveat, and never for anything execution-broad.
  Record a `promotion` flag, the suggested `target_level`, and the reasoning. Do not
  enact the move; recommend it and let the user decide.
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
