# Pass 2 -- Consolidate and group

**Goal:** turn the pass-1 recommendation set (raw candidates + level targeting) into
a *judged* proposal: refine or reject each consolidation under the level
constraints, surface heterogeneous families for discussion instead of merging them,
and write the per-family narrative that the report will show. Still read-only; no
config is touched.

Read `../SKILL.md` (hard constraints) and `recommendation-set-schema.md` first.
Input: the recommendation set from pass 1. Output: the same document with refined
`status`/`into` values, finalized `discussion` entries, and a `narrative` per family.

## Principle -- the tool's consolidations are candidates, not answers

The analyzer finds consolidations by **single-token literal alternation** only. That
is a candidate finder, not a design. Your job is judgement the tool cannot do:
respect levels, notice heterogeneity, and neither over- nor under-merge. Do **not**
try to make this deterministic or exhaustive -- reason case by case.

## Step 1 -- resolve blocked welds (split, do not enact)

For every consolidation flagged `cross-level-weld` in pass 1: **do not** keep the
tool's single merged rule. Split it along level lines into per-level candidates
(e.g. the `/tmp`, `/tmp/claude-code` members become one candidate destined for the
user level; the `flowers/`, `~/projects/flowers/` members another destined for the
project level). In this phase, since promotion is deferred, present the split as:
keep the project-level members merged (if homogeneous) and raise the user-level
members as a *promotion opportunity* discussion entry rather than enacting the move.
The point is: never emit a rule that welds levels together.

## Step 2 -- heterogeneity scan (flag, do not merge)

Within each family with a consolidation candidate, look for an **outlier in shape or
scope** among the members. Cues (not an exhaustive checklist -- use judgement):

- a member carrying a flag-with-value (`-x db=test`, `--profile prod`) while its
  siblings are plain subcommands;
- a member that reads as a **target/selector** -- a database, environment, host,
  account, or path -- when the others do not;
- a member noticeably narrower or broader in scope than the rest of the family.

When you find one:

- **Do not consolidate that member away.** Leave it `no-change` (or split it out of
  the merge) and record a `heterogeneity` flag.
- **Open a discussion entry** naming the outlier and asking the intent question in
  plain terms -- e.g. "these `uv run alembic` rules look uniform except
  `-x db=test`, which targets a specific database; do you want per-database rules,
  or is this just to reach a non-default database?" Ask; propose nothing.
- **Ceiling:** general programming judgement to *notice* the outlier is enough. Do
  NOT go research the domain tool (alembic, terraform, kubectl, ...) to resolve it
  yourself. The user supplies the intent.

### Confidence -- assert on ubiquitous tools, flag only the domain-specific

The "do not research" ceiling is about *obscure or domain-specific* behavior, NOT an
excuse to hedge on universal tooling. For ubiquitous, stable tools -- `git`, `.env`
files, `ssh`, core unix (`ls`/`cat`/`grep`/`find`), common package managers -- assert
their standard semantics **with confidence**: classify read-only vs mutating,
recommend the obvious hardening, and judge promotability without asking the user to
teach you what `git status` does. Reserve flag-and-ask for genuinely domain-specific
behavior (alembic's `-x`, terraform workspaces, a custom in-repo script).

Even on a well-known tool, still notice **non-standard usage**: `git flake8` /
`git isort` are not real git subcommands -- they are custom aliases (here, the user's
`~/bin` scripts). Assert the standard, and flag the deviation as its own small note.

## Step 3 -- refine the remaining (homogeneous, same-level) consolidations

For a family whose merge members are homogeneous and share one level:

- Confirm the tool's `added_pattern` actually covers exactly the removed members and
  nothing more; if the tool under-merged (left obvious same-shape siblings out) you
  may extend the merge -- but only when every member is the same shape and level,
  and only if it stays legible (anchored `^`, readable alternation; never a giant
  regex). When in doubt, keep the smaller, clearer merge.
- **Consolidating allows does not resolve an overlapping ask/deny.** If the merged
  members carve out of a broader `ask`/`deny`, the interaction persists (a
  more-specific allow still bypasses the ask; deny still wins). Keep the interaction
  as one discussion point; do not claim the merge "fixes" it.
- Keep `replay_summary` as the evidence line; it is decision-neutrality over the
  observed corpus, not a correctness proof -- say so if you cite it.

## Step 3a -- recommend known hardening confidently (secret files)

Some weaknesses are well-known enough to recommend a concrete fix, not merely flag.
The most common: secret-file reads guarded by **prefix-anchored per-tool** denies
(`Bash(cat .env:*)`, `Bash(head .env:*)`, ...). These are brittle -- they catch only
the CWD-relative spelling and only the enumerated readers; `head /abs/path/.env`,
`grep -r X ~/.ssh/`, `tail ../.env` slip straight through. Recommend the
tool-agnostic form (`.env`/`.ssh` conventions are universal -- assert this):

- **Bash layer (matches command text):** one `Bash([regex]\.env\b)` catches every
  reader that names a `.env`; `Bash([regex]\.ssh/)` for ssh keys. A path glob does
  NOT work on the Bash layer -- Bash rules match the command string, not a filesystem
  path, so use a regex here. Do NOT anchor the ssh regex with a leading slash
  (`/\.ssh/`) -- that misses the relative spelling `cat .ssh/id_rsa`; `\.ssh/` catches
  both relative and absolute. Give such a broad rule a **clarifying trailing comment**
  (e.g. `# applies to ANY command-line tool, not just cat/head/...`) so its reach is
  obvious in the file.
- **File tools (match paths):** `Read`/`Write`/`Edit` want a glob deny --
  `[glob]**/.env`, `[glob]**/.env.*`, `[glob]**/.ssh/**`. **Check all three tools are
  covered** -- a common gap is `Edit` missing a deny that `Read`/`Write` already have.

Present these as concrete deny rules the user can accept, spanning the sections/tools
they belong in. They compose with (never replace) any `#NOSECURITY` the user set.

**Deny consolidation is not like allow consolidation.** An allow merge must be
behavior-preserving (broadening an allow is dangerous -- that is what replay verifies). A
DENY merge may deliberately *tighten*: a superset deny is safe and usually better -- "when
in doubt, restrict". So denies get their own rule:

- When a **tool-agnostic** deny is warranted (as above), it subsumes the per-reader /
  per-path specific denies -- recommend adopting it and **deleting the specific ones as
  redundant** (do not keep both; that is the "redundant overlapping denies" smell).
- Where a tool-agnostic form does NOT apply, a consolidated **superset regex** deny is
  still a valid, safe consolidation of a deny family -- unlike an allow, it need not be
  exactly behavior-preserving, only not-looser. (Use groups `(a|b|c)` and escape dots,
  e.g. `(\.env|\.ssh)` -- `[a|b]` is a character class, not alternation.)
- Note any over-deny it introduces (e.g. `\.env\b` also denies `.env.example` templates)
  and whether that merely matches the config's existing posture (an existing
  `Read(**/.env.*)` deny) -- if so it is consistent, not a surprise.

**Complete a read/write split on a well-known tool (confident hardening).** When a family
shows the *read* operations allowed and the *mutating* ones simply absent (e.g. git:
`diff|log|status` allowed, nothing denied), use confident knowledge of that tool to
recommend making the intent explicit on the deny side -- an optional `deny` (or
`hard_deny` for the catastrophic: force-push, history rewrite, `reset --hard`, `clean
-f`). Fail-closed already blocks them today; the value is robustness if the allow side
later drifts broader. Present as optional hardening, not a required change.

## Step 4 -- write the per-family narrative

For each family, fill `narrative`: a short plain-English paragraph a human can read
without decoding patterns. Cover, in the family's own terms:

- what the family is and how many rules it has, across which sections;
- the current state and the proposed change (consolidate / remove / no-change), with
  a clear **before -> after**;
- **why it is safe, or what needs your decision** -- name any discussion question,
  broadening, heterogeneity outlier, promotion opportunity, or persisting
  interaction. Prefer honesty over reassurance: if the merge is decision-neutral but
  you are unsure it matches intent, say that.

Families that are entirely `no-change` get a one-line narrative ("N rules, no change
suggested") so the final report can still show them in context without noise.

## Output of this pass

The recommendation set with every consolidation either refined (homogeneous,
same-level, legible) or converted to a discussion/split, heterogeneity outliers
flagged and questioned, and a narrative on every family. Hand off to
`3-report-certify-and-apply.md`.
