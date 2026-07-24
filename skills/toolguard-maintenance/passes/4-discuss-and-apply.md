# Pass 4 -- Discuss and apply (the WRITE pass)

**Goal:** present the certified proposal from pass 3, have a real case-by-case
conversation, and enact -- only on explicit consent -- exactly what the user approves.
This is the only pass that writes.

Read `../SKILL.md` (hard constraints, self-permissioning, first-run vs periodic) and
`recommendation-set-schema.md` first. Input: the certified, replay-validated
recommendation set from pass 3 (understanding view + cut/paste TOML + certification +
corpus validation).

> **Consent is the whole point of this pass.** No change is ever applied
> automatically, no matter how trivial or how cleanly it certified. Replay-verification
> and a clean audit are EVIDENCE, not consent. Bulk-apply exists only as an explicit
> user opt-in, never a default and never a label you attach on the user's behalf.

## Step 1 -- present and let the user drive

Present the pass-3 understanding view, the cut/paste section, and the certification
result (parse + audit + corpus replay, with the necessary-not-sufficient caveat).
Then hand control to the user. Default to a **case-by-case** walk:

- Go family by family, most-consequential first (the pass-3 order). For each family
  with changes or open questions, state the proposal and its evidence, then take the
  user's decision: **accept / reject / modify**. Record it on each member as
  `user_decision` and any `user_note`.
- **Answer their questions.** A heterogeneity question (the alembic `-x db=test`
  outlier), a broadening opportunity, a promotion opportunity, or a persisting
  ask/deny interaction is a real decision -- resolve it in dialogue, do not decide it
  for them.
- **If a decision changes the plan** (they want a different merge, reject a
  consolidation, accept a promotion), update the recommendation set AND **re-run pass
  3's certification + corpus replay** on the amended candidate before enacting. Never
  enact a variant that was not certified.
- **How much to raise depends on the run kind** (SKILL.md "First run vs periodic"). On
  a first run, walk everything. On a periodic run at a higher trust level, only open a
  discussion for NEW or CHANGED families and material audit findings; do not
  re-litigate a question already settled in a prior run (recorded in-file, or a member
  the pass-1 `settled` flag marked from a ledger `reject`). Never silently apply, even
  on the quietest periodic run.

- **Bulk-apply only if the user explicitly asks** ("just apply it all"). Offer it as
  an option, never assume it.
- **Self-edit is always available.** The certified cut/paste TOML lets the user
  hand-edit for full control or to tweak wording; prefer guiding a self-edit over
  applying more than they approved.

## Step 2 -- enact approved changes

Enact only what the user approved, by the narrowest mechanism that fits:

- **Tool-appliable consolidations** (the pass-1 `edit_proposals` subset the user
  accepted): enact with `toolguard-maintain --apply --write`, after showing a final
  `toolguard-maintain --apply` dry-run preview. Respect the write pre-flight (clean
  working tree, resolved project root); on refusal, relay the blockers and have the
  user commit/stash, then retry -- never circumvent the pre-flight. If the user
  accepted only a subset of a family, prefer guiding a self-edit from the certified
  TOML over applying more than they approved.
- **Changes the tool cannot mechanically apply** (level splits, hand-tuned rewrites,
  promotions): have the user paste the certified TOML, or apply via their chosen edit
  path. Do NOT invent a write mechanism the tool does not provide.
- **Promotions are a TWO-FILE hand-apply.** The tool has no cross-level move writer, so
  a `status:"promote"` change is never enacted by `--apply`. Present it as two paste
  actions from the pass-3 certified output: (1) REMOVE the rule from the project file,
  (2) ADD it to the user file (`~/.claude/toolguard_hook.toml`) -- creating that file
  with the full base setup (`[takeover_mode]`, `governed_tools`) if it does not yet
  exist. Repeat the incomplete-user-setup admonition: a promoted rule does nothing in
  projects that lack the toolguard hook, so promoting AND standing up the full
  user-level setup go together. For a promoted allow, restate the cross-context
  broadening caveat before the user commits. If the user declines the promotion, record
  it (Step 3) as a `reject-promotion` ledger entry so a periodic run stays quiet.
  **The promotion destination is always `~/.claude/toolguard_hook.toml` specifically --
  deliberately, not an oversight.** The optional `~/.config/toolguard/rules/` split-file
  directory (see `configuration.md#configuration-hierarchy`) is also part of the user
  level, but it is manually curated by the user and must NEVER be offered or chosen as
  a promotion destination on the agent's own initiative. If the user wants a promoted
  rule to land in one of those files instead, that must be their explicit instruction,
  not a suggestion this skill makes.
- **Inline clarity annotations:** after presenting clarity interactions, offer
  `toolguard-maintain --annotate` to write `# toolguard:` comments so the config
  self-documents (comment-only, same write pre-flight; show the `--annotate` preview
  first).
- **Leave the git commit to the user.** Never commit on their behalf.

## Step 3 -- record decisions for next time

Whatever the user decided -- accept, reject, or modify -- record it durably so a
future periodic run does not re-litigate it:

- Keep `user_decision` / `user_note` on every member of the recommendation set (the
  in-session record).
- Where a decision attaches to a **surviving rule**, prefer an **in-file annotation**
  on that rule (a `# toolguard:` note via `--annotate`, or a `#NOSECURITY: <reason>`
  where the user accepted a flagged risk): it is visible, versioned, and travels with
  the config. This is the first-choice prior-decision signal.
- A **META-decision with no rule to hang on** -- "don't ever suggest merging this
  family", "don't re-propose promoting these allows to the user level", "this rule is
  intentionally kept project-scoped" -- has nothing to annotate, so record it in the
  **sidecar decision ledger** with `toolguard-maintain --record-decision`. This is the
  store a periodic run reads (pass 1) to stay quiet on settled questions. Build a small
  JSON entry per rejected suggestion and record it at the level the decision belongs to:

  ```
  # one object, or a JSON list of them; then:
  toolguard-maintain --dir <project> --record-decision <file.json> --ledger-level project
  ```

  Each entry: `kind` (one of `reject-consolidation`, `reject-promotion`,
  `reject-broadening`, `reject-removal`, `intentional-scope`, `custom`), `family_id`
  (the recommendation-set family slug), `target` (the canonical thing rejected -- the
  proposed merge pattern, or `promote:user` for a promotion), optional `decision`
  (defaults to `reject`), and `rationale` (the user's own words, from `user_note`).
  Choose `--ledger-level user` only for a decision that should hold across every project
  (e.g. rejecting a universal-deny promotion); default `project` so it travels with the
  repo. Recording is idempotent -- re-recording the same `(kind, family_id, target)`
  updates in place, so a later run may safely re-affirm it.
- The `target` you record MUST match what pass 1 will query, so use the family's slug
  and the same canonical target string the report showed. If in doubt, run
  `toolguard-maintain --ledger-show` afterwards and confirm the entry reads back as the
  suggestion you intend to suppress.

## Output

Approved changes enacted (or handed off as certified paste-ready TOML); every decision
recorded (`user_decision` / `user_note`, plus in-file annotations where a rule carries
the decision) so periodic runs stay quiet. Nothing was applied that the user did not
explicitly approve, and the git commit is left to the user.
