# Maintenance & Audit Skills

Toolguard ships two Claude Code **skills** that help you keep your permission
configuration safe and tidy without hand-editing TOML:

- **`toolguard-security-audit`** -- a read-only safety check that flags risky rules
  and takeover-mode problems.
- **`toolguard-maintenance`** -- a guided, conversational clean-up that finds
  redundant, mergeable, mis-levelled, and confusing rules and -- only with your
  per-item approval -- applies the ones you accept.

Both are also available as plain command-line tools (`toolguard-audit`,
`toolguard-maintain`) if you want the raw analysis without the conversation.

> **Nothing is ever changed without your explicit say-so.** The audit skill never
> writes at all. The maintenance skill writes only the specific changes you approve,
> one at a time, and only when your working tree is clean so every change stays
> reviewable and revertible.

---

## Security audit

**What it does.** Runs a deterministic analyzer over your whole config hierarchy and
reports security risks -- over-broad allow rules (e.g. an allow that permits arbitrary
code execution), brittle secret-file protections, unanchored regexes, and
takeover-mode misconfigurations -- ranked by severity. It can then offer a deeper,
judgement-based AI assessment on top of the mechanical findings. It is **read-only**:
it reports findings and proposes fixes but never edits anything.

**When to use it.** As a start-of-session safety check, before a push, after you (or
Claude) have piled up new permissions, or any time you want to know "is my toolguard
setup actually safe?"

**How to run it.** Ask Claude in natural language -- "audit my toolguard permissions",
"security-check the config", "is takeover mode set up safely?" Claude invokes the
skill, runs the analyzer, and walks you through the findings.

**What you get.** A ranked list of findings, each with where the rule lives, why it is
risky, and a concrete suggested fix. A finding you have deliberately accepted can be
marked with a `#NOSECURITY: <reason>` comment on the rule (see below); the audit then
shows it as *acknowledged* and de-prioritizes it instead of nagging.

**Command-line form.** `toolguard-audit` (add `--with-context` for the full rule
hierarchy, `--format json` for machine output, `--strict` to fail on findings).

---

## Maintenance

Permission lists grow. Every time Claude Code prompts and you pick "Yes, and don't ask
again," it writes a new allow rule -- so rules accumulate, drift from your
`toolguard_hook.toml`, duplicate each other, and develop confusing overlaps. The
maintenance skill curates all of that.

It is deliberately a **conversation, not a one-click cleanup**, because the right merge,
the right level for a rule, and whether a "confusing" overlap is actually a bug all
depend on what *you* intended -- which the tool cannot infer.

### What a run looks like

1. **Gather & analyze.** The skill runs the analyzer and a security audit for evidence,
   then groups every rule -- across `allow`/`ask`/`deny` -- into **command families**
   (all your `git` rules together, all your `mkdir` rules, and so on).
2. **Understand.** It presents an *understanding view*: each family with its rules
   marked `no-change` / `edit` / `consolidate` / `remove` / `new` / `promote`, a plain
   before-and-after, and a short paragraph explaining what it is proposing and why.
   Unchanged rules are shown too, so you can see the whole final picture, not just a
   diff. It also flags open questions (an odd rule that does not fit its family, a rule
   that would *broaden* what is allowed, a promotion opportunity) for you to decide.
3. **Certify.** Before you touch anything, it assembles the resulting config and runs it
   back through the tool -- it must parse, pass the security audit with no new findings,
   and not change the verdict on commands you have actually run.
4. **Decide & apply.** It walks the proposal with you family by family -- accept, reject,
   or modify each -- and enacts only what you approve. You can also say "just apply it
   all" if you want to, but that is always your explicit choice, never the default.

### Promotion: moving a rule to the "user" level

Toolguard reads a user-level layer (`~/.claude`) that applies to *every* project, not
just the current one. The skill will suggest **promoting** rules that belong everywhere:

- **Safety denies** (secret-file reads like `.env`/`.ssh`, `rm -rf`) are promoted
  eagerly -- a deny at the user level protects all your projects.
- **Benign, project-agnostic allows** (`echo`, `ls`, `git diff|status|log`, and similar
  read-only utilities) are offered as user-level candidates too, so you set them up
  once instead of per project.
- **Risky allows** -- anything that can run arbitrary code, or a reader that could read
  secrets unless the guarding deny travels with it -- are *not* promoted, or only
  alongside their guard.

A promotion is never applied automatically: the skill shows you both files (the rule
removed from the project, added to the user level) for you to paste. **Important:**
user-level rules only take effect where toolguard is actually installed, so if you have
no user-level toolguard setup yet, promote the rule *and* stand up that setup together --
a safety deny that never runs is worse than none, because it looks like protection.

### First run vs periodic

Your first maintenance run on a project is large -- everything is a fresh decision. Later
runs (e.g. before each push) should be quiet: mostly no-ops with a few new rules. To
avoid re-asking questions you already settled, the skill records your decisions and reads
them back next time:

- Decisions attached to a rule you kept are written as `# toolguard:` comments (or a
  `#NOSECURITY: <reason>` where you accepted a flagged risk) -- visible, versioned, and
  travelling with the config.
- Decisions with no rule to attach to (e.g. "don't ever suggest merging this family",
  "don't promote these") are recorded in a small **decision ledger** -- a project one in
  `.claude/toolguard_decisions.json` and a user one in `~/.toolguard/decisions.json`. A
  periodic run reads it and stays quiet about anything you already declined.

### `#NOSECURITY`: accepting a risk on purpose

Sometimes a rule the audit flags is one you genuinely want (a single-user dev machine
allowing `uv run python`, say). Add a trailing `#NOSECURITY: <reason>` comment to the
rule. The audit then treats it as acknowledged, and maintenance will never rewrite or
"clean up" that rule out from under you. Use it deliberately for arbitrary-code-execution
allows -- it is a standing exception the tooling cannot vet for you.

### Command-line form

`toolguard-maintain` prints findings by default (read-only). Its write modes
(`--apply --write` to enact approved consolidations, `--annotate --write` to add the
`# toolguard:` comments) refuse to run on a dirty working tree, so a change always stays
reviewable. Most people never need the CLI directly -- the skill drives it for you.

---

## Running the skills against toolguard's own repo

If you are developing toolguard itself, the skills default to the installed console
scripts, which is correct for every *other* project. To exercise your working branch
instead, invoke a skill with `--dev` (it switches to the in-repo module form). This is
for toolguard maintainers only; see each skill's SKILL.md "Development mode" section.

## See also

- [Security Best Practices](security.md) -- the risks the audit looks for.
- [Config Sync & Migration](config-sync.md) -- reconciling `settings.local.json` drift.
- [Permission Patterns](permission-patterns.md) -- the rule syntax the skills produce.
- Internal CLI/pass/contract details for developers and agents live in
  [technical-notes.md](../technical-notes.md) ("Maintenance and audit tooling").
