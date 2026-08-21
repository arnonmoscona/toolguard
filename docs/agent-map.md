# Agent Map

**Audience: agents (AI coding assistants configuring or using toolguard).** Human-readable,
but written for fast lookup, not for reading start to end -- if you're a human wanting a
guided tour, start with [README.md](../README.md) or [quickstart.md](quickstart.md)
instead.

**What this is:** two things in one page --

1. A [master table of contents](#master-table-of-contents) across every doc in this project
   (headings only, no content), so you can jump straight to the file+section that has what
   you need instead of reading multiple files to find it.
2. A [questions and pointers](#questions-and-pointers) list of real, recurring questions
   (drawn from this project's own install-test history and documentation audits -- not
   hypothetical), each with a one-line answer and a pointer to the section that has the full
   detail. The answer here is deliberately terse; follow the link for anything you need to
   act on, don't treat the one-liner as authoritative on its own.

**Drift warning -- read this before trusting an anchor here.** This file is a map, not a
source of truth. If anything here disagrees with the actual document it points to, the real
document wins -- treat the disagreement as a sign this map is stale and needs a refresh
(see the `documentation-review` command / `CLAUDE.md`'s pre-push checklist), not as a reason
to doubt the real doc. The master TOC section was generated mechanically from the current
`##`/`###` headings (a Python script walks each file, skips code-fenced example headings,
and computes GitHub's anchor-slug algorithm) -- regenerate it the same way rather than
hand-editing it when docs change. The questions-and-pointers section is hand-curated and has
no such regeneration path; that's an explicit tradeoff (see `tmp/too15-doc-audience-audit.md`
Finding 6 for the reasoning) -- keep it short and pointer-shaped, and prefer fixing/adding an
entry over letting it silently go stale.

---

## Questions and pointers

**Setup & configuration**

- **Q: Is `no_match_fallback` set inside `[takeover_mode]` or at the top level of
  `toolguard_hook.toml`?**
  A: Top level. The nested `[takeover_mode].no_match_fallback` form still works but is a
  legacy alias, only used when no level sets the top-level key. See
  [configuration.md#no-match-fallback](configuration.md#no-match-fallback).
- **Q: What's the difference between `no_match_fallback` and `undecidable_fallback`?**
  A: `no_match_fallback` is about commands toolguard read and understood but that matched no
  rule; `undecidable_fallback` is about commands toolguard could not safely parse at all
  (foreign inline code, heredocs, process substitution). Both default to `"ask"`, but only
  `undecidable_fallback` has no `[takeover_mode]` alias and raises a HIGH audit finding when
  set to `"allow_with_warning"`. See
  [configuration.md#undecidable-fallback](configuration.md#undecidable-fallback).
- **Q: Why isn't my rule being enforced even though I added it?**
  A: A tool is governed only if it's in **both** the hook matcher (native settings) **and**
  `governed_tools` (`toolguard_hook.toml`, which defaults to `Bash`/`Read`/`Write`/`Edit`
  when unset) -- check both. See
  [agent-guides.md#ground-rules-read-first](agent-guides.md#ground-rules-read-first).
- **Q: What is `CLAUDE_SETTINGS_PATH` and why does it matter?**
  A: An env var that forces single-file mode, bypassing the whole config hierarchy -- a real
  footgun if set and forgotten (it has caused confusing "why isn't my hierarchy working"
  reports before). See
  [configuration.md#environment-variables](configuration.md#environment-variables) and
  [install.md's Phase 0.4 check](install.md#phase-0----preflight).
- **Q: How do I keep the toolguard binary itself up to date?**
  A: `toolguard-update-check` (or the throttled shell-alert / auto-update snippets). See
  [configuration.md#keeping-toolguard-up-to-date](configuration.md#keeping-toolguard-up-to-date).
- **Q: Can I split my user-level rules into multiple files instead of one big
  `toolguard_hook.toml`?**
  A: Yes -- drop any number of `*.toml`/`*.json` files into
  `~/.config/toolguard/rules/` (or `$XDG_CONFIG_HOME/toolguard/rules/`). Each merges into the
  same user level automatically; flat/non-recursive, `[permissions]`/`[hard_deny]` only. See
  [configuration.md#configuration-hierarchy](configuration.md#configuration-hierarchy).
- **Q: What are `toolguard-install`'s subcommands, and what does each do?**
  A: It's self-documenting and agent-facing -- run `toolguard-install --help` and
  `toolguard-install <subcommand> --help` rather than relying on a doc summary; the guided
  runbook that sequences them is [install.md](install.md).

**Rules & patterns**

- **Q: Do the `[regex]`/`[glob]`/`[native]` dialects work on `Read`/`Write`/`Edit`, or only
  `Bash`?**
  A: All three work on file-path tools too, not just command tools. See
  [permission-patterns.md#file-path-patterns-read-write-edit](permission-patterns.md#file-path-patterns-read-write-edit).
- **Q: Does `[native]` actually match what Claude Code's own permission rules do?**
  A: It is *meant* to, but Claude Code's rules change and ours can drift. What it mirrors is
  quoted verbatim, with the date last verified and the known divergences, in
  [native-pattern-reference.md](native-pattern-reference.md). **Check that date before
  relying on equivalence.**
- **Q: How do I write a deny rule that nothing (no more-specific level, no explicit allow)
  can override?**
  A: `[hard_deny]`, ideally at the user level -- but only for a rule with NO legitimate
  exception. See
  [agent-guides.md#recipe-block-a-command-no-matter-what](agent-guides.md#recipe-block-a-command-no-matter-what).
- **Q: How do I deny a command by default but permit one specific real invocation of it?**
  A: An ordinary `deny` at a shared level plus a more-specific `allow` at a deeper one --
  `[hard_deny]` refuses this case on purpose, since it means no exceptions. See
  [agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception](agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception).
- **Q: How do I share the same rules across many projects without copying them into each
  one?**
  A: Put them in an ancestor `.claude/` (commonly `~/.claude/`) -- discovery walks up
  automatically, more-specific-wins. See
  [agent-guides.md#recipe-share-rules-across-many-projects](agent-guides.md#recipe-share-rules-across-many-projects).
- **Q: How do I diagnose why a specific command was denied (or unexpectedly allowed)?**
  A: Work through the resolution log, then the conflict log, in order. See
  [agent-guides.md#recipe-diagnose-my-command-was-denied](agent-guides.md#recipe-diagnose-my-command-was-denied).
- **Q: How does toolguard handle heredocs, multi-line commands, and compound commands
  (`&&`, `;`, `|`, subshells)?**
  A: Decomposed into sub-commands and validated separately; anything it can't safely
  decompose takes the `undecidable_fallback` floor, which defaults to ASK but can be
  loosened. See
  [permission-patterns.md#compound-and-multi-line-commands](permission-patterns.md#compound-and-multi-line-commands).
- **Q: Does `FOO=1 rm -rf /tmp/x` match a rule written for `rm`, and does `TG_INTENT=1 ls`
  still match `allow Bash(ls:*)`?**
  A: Deny, ask and `hard_deny` always see the command underneath a leading `VAR=value`, so
  the first is denied. An allow rule does not, unless every variable in the prefix is listed
  in `assignments_looked_past_when_granting` -- so the second falls to `ask` until you
  configure it. The asymmetry is what stops `LD_PRELOAD=x ls` inheriting an `ls` allow, and
  it diverges from Claude Code in both directions. See
  [permission-patterns.md#leading-environment-assignments](permission-patterns.md#leading-environment-assignments)
  and
  [configuration.md#assignments-looked-past-when-granting](configuration.md#assignments-looked-past-when-granting).
- **Q: Can a rule explain itself to Claude -- e.g. tell it why a command was denied, or what
  to do instead?**
  A: Yes -- add `additionalContext` to a structured rule entry (toolguard config files only;
  a plain string or a native-settings entry cannot carry it). It's injected only when that
  rule is the one that decided the call. See
  [configuration.md#additionalcontext-injecting-guidance-alongside-a-decision](configuration.md#additionalcontext-injecting-guidance-alongside-a-decision).

**Modes**

- **Q: What's the difference between Takeover Mode and Auto-mode?**
  A: Takeover Mode is toolguard's own mechanism (blanket native allows + toolguard enforcing
  the real rules underneath). Auto-mode is about Claude Code's *own* permission_mode
  bypassing its native prompts -- a different layer, can be combined but solves a different
  problem. See
  [auto-mode.md#how-this-differs-from-takeover-mode](auto-mode.md#how-this-differs-from-takeover-mode).
- **Q: Can I run Claude Code in an auto-accept/bypass-permissions mode safely with
  toolguard?**
  A: Yes, toolguard's hook still enforces underneath -- but read the honest tradeoff on
  `no_match_fallback = "allow_with_warning"` first, it's a narrow recommendation for this
  case only. See [auto-mode.md](auto-mode.md).
- **Q: What happens to Claude Code's own `Bash(*)`-style blanket allows once Takeover Mode
  is enabled?**
  A: Stripped from native settings as they're loaded, so they can't bypass the real
  toolguard rules. See
  [takeover-mode.md#ignored-allow-patterns](takeover-mode.md#ignored-allow-patterns).

**Maintenance & audit**

- **Q: How do I run a security audit, or clean up/consolidate accumulated rules?**
  A: The `toolguard-security-audit` and `toolguard-maintenance` skills -- ask Claude in
  natural language, don't hand-author this yourself. See
  [skills.md](skills.md).
- **Q: What's the difference between "migration" and "maintenance"?**
  A: Migration reconciles drift between `settings.local.json` and `toolguard_hook.toml`
  (mechanical, one concern). Maintenance is the broader pass -- duplicates, over-broad
  allows, mis-levelled rules, promotion -- and uses migration as one input among several.
  See [config-sync.md](config-sync.md) vs [skills.md#maintenance](skills.md#maintenance).
- **Q: Is there a `max_similar_matches` (or similar) setting to tune duplicate detection?**
  A: No -- that's a fixed constant (3 matches shown, 0.7 similarity cutoff), not a
  `toolguard_hook.toml` key. See
  [config-sync.md#similarity-detection-and-duplicate-removal](config-sync.md#similarity-detection-and-duplicate-removal).
- **Q: What CLI flags does `toolguard-migrate` accept?**
  A: `--dry-run`, `--no-sort`, `--backup-dir DIR`, beyond the no-argument default apply. See
  [config-sync.md#manual-migration](config-sync.md#manual-migration).

**Install & uninstall safety**

- **Q: Is it ever OK to delete `~/.toolguard/` as part of routine uninstall or a "clean
  slate" request?**
  A: **No.** This has been a real, repeated failure mode (an agent over-interpreting "clean
  slate" or "reset my memory" as license to wipe it) -- never delete it unless the user
  names that exact directory and explicitly says to delete it. See
  [uninstall.md#step-3----leave-toolguard-in-place-do-not-delete-it](uninstall.md#step-3----leave-toolguard-in-place-do-not-delete-it).
- **Q: Does toolguard's self-protection against `rm -rf ~/.toolguard` survive an uninstall?**
  A: No -- the protection lives inside `toolguard_hook.toml`, which uninstall removes, so it
  stops applying at that point. This is a known, accepted gap (native, survives-uninstall
  protection is a separate future ticket), not yet fixed. Treat "can never be deleted" language
  in `install.md`'s Phase 4 as true only while the config is still live, not as an
  unconditional guarantee.
- **Q: How do I uninstall toolguard completely and safely?**
  A: Follow the journal in reverse, most-recent action first; never guess which backup file
  to restore. See [uninstall.md](uninstall.md).

---

## Master table of contents

Every `##`/`###` heading in every doc, generated mechanically (see the drift warning above).

**`README.md`** (project root)
- [Why Toolguard?](../README.md#why-toolguard)
- [Explaining decisions to Claude](../README.md#explaining-decisions-to-claude)
- [Documentation](../README.md#documentation)
- [Motivation](../README.md#motivation)
  - [Goals of Toolguard](../README.md#goals-of-toolguard)
- [Requirements](../README.md#requirements)
- [Installation](../README.md#installation)
- [Testing](../README.md#testing)

**`docs/agent-guides.md`**
- [Ground rules (read first)](agent-guides.md#ground-rules-read-first)
- [Recipe: install and register toolguard from scratch](agent-guides.md#recipe-install-and-register-toolguard-from-scratch)
- [Recipe: allow a specific command](agent-guides.md#recipe-allow-a-specific-command)
- [Recipe: block a command no matter what](agent-guides.md#recipe-block-a-command-no-matter-what)
- [Recipe: deny a command with a legitimate exception](agent-guides.md#recipe-deny-a-command-with-a-legitimate-exception)
- [Recipe: scope file access to a project](agent-guides.md#recipe-scope-file-access-to-a-project)
- [Recipe: share rules across many projects](agent-guides.md#recipe-share-rules-across-many-projects)
- [Recipe: diagnose "my command was denied"](agent-guides.md#recipe-diagnose-my-command-was-denied)
- [Recipe: clean up accumulated permissions](agent-guides.md#recipe-clean-up-accumulated-permissions)

**`docs/architecture-as-built.md`** (replaced `docs/architecture.md`, which was merged into it)
- [1. What toolguard has to do, and what it may not](architecture-as-built.md#1-what-toolguard-has-to-do-and-what-it-may-not)
  - [One process per tool call](architecture-as-built.md#one-process-per-tool-call)
- [2. Standard library only](architecture-as-built.md#2-standard-library-only)
- [3. All bash parsing goes through the PEG grammar](architecture-as-built.md#3-all-bash-parsing-goes-through-the-peg-grammar)
  - [Why](architecture-as-built.md#why)
  - [The written rule exists because this has regressed](architecture-as-built.md#the-written-rule-exists-because-this-has-regressed)
- [4. Two halves: the core runtime and the operator tooling](architecture-as-built.md#4-two-halves-the-core-runtime-and-the-operator-tooling)
  - [Why the split matters more than the line count suggests](architecture-as-built.md#why-the-split-matters-more-than-the-line-count-suggests)
- [5. What Claude Code owns lives in one leaf](architecture-as-built.md#5-what-claude-code-owns-lives-in-one-leaf)
  - [The rule, and the case built to test it](architecture-as-built.md#the-rule-and-the-case-built-to-test-it)
  - [What the import edge buys, and what it does not](architecture-as-built.md#what-the-import-edge-buys-and-what-it-does-not)
  - [Why drift detection stays weak on purpose](architecture-as-built.md#why-drift-detection-stays-weak-on-purpose)
- [6. The layer model](architecture-as-built.md#6-the-layer-model)
  - [Which module sits where](architecture-as-built.md#which-module-sits-where)
  - [Why `observability` sits below `config`](architecture-as-built.md#why-observability-sits-below-config)
  - [Why `api` exists](architecture-as-built.md#why-api-exists)
  - [What is checked, and what is not](architecture-as-built.md#what-is-checked-and-what-is-not)
- [7. The verdict altitudes: `LevelMatch`, `UnitVerdict`, `RuntimeVerdict`](architecture-as-built.md#7-the-verdict-altitudes-levelmatch-unitverdict-runtimeverdict)
- [8. The decision path, end to end](architecture-as-built.md#8-the-decision-path-end-to-end)
  - [A compound Bash command: what runs around the cascade](architecture-as-built.md#a-compound-bash-command-what-runs-around-the-cascade)
  - [Four public entry points that are not on this path](architecture-as-built.md#four-public-entry-points-that-are-not-on-this-path)
- [9. The runtime dependency no import graph shows](architecture-as-built.md#9-the-runtime-dependency-no-import-graph-shows)
- [10. The configuration hierarchy](architecture-as-built.md#10-the-configuration-hierarchy)
- [11. Pattern matching](architecture-as-built.md#11-pattern-matching)
- [12. Writing configuration](architecture-as-built.md#12-writing-configuration)
- [13. Logging](architecture-as-built.md#13-logging)
- [Sources](architecture-as-built.md#sources)

**`docs/auto-mode.md`**
- [The honest tradeoff](auto-mode.md#the-honest-tradeoff)
- [Why `no_match_fallback = "ask"` (the normal default) doesn't work here](auto-mode.md#why-no_match_fallback--ask-the-normal-default-doesnt-work-here)
- [The recommended configuration for this specific case](auto-mode.md#the-recommended-configuration-for-this-specific-case)
- [Recommended checklist before you turn this on](auto-mode.md#recommended-checklist-before-you-turn-this-on)
- [How this differs from Takeover Mode](auto-mode.md#how-this-differs-from-takeover-mode)

**`docs/config-sync.md`**
- [What is config divergence?](config-sync.md#what-is-config-divergence)
  - [Divergence is normal -- you cannot prevent it](config-sync.md#divergence-is-normal----you-cannot-prevent-it)
  - [Why it matters](config-sync.md#why-it-matters)
- [Manual migration](config-sync.md#manual-migration)
- [Auto-migration](config-sync.md#auto-migration)
- [Backup handling](config-sync.md#backup-handling)
- [Similarity detection and duplicate removal](config-sync.md#similarity-detection-and-duplicate-removal)
- [Warning throttling](config-sync.md#warning-throttling)

**`docs/configuration.md`**
- [Contents](configuration.md#contents)
- [Step 1: Register hook matchers](configuration.md#step-1-register-hook-matchers)
- [Step 2: Configure governed tools](configuration.md#step-2-configure-governed-tools)
  - [Declaring additional supported tools](configuration.md#declaring-additional-supported-tools)
  - [Recommended tools to govern](configuration.md#recommended-tools-to-govern)
- [Step 3: Configure permission patterns](configuration.md#step-3-configure-permission-patterns)
  - [Standard patterns (in settings.local.json)](configuration.md#standard-patterns-in-settingslocaljson)
  - [Extended patterns (in toolguard_hook.toml or toolguard_hook.json)](configuration.md#extended-patterns-in-toolguard_hooktoml-or-toolguard_hookjson)
  - [Structured rule entries, and the single line rule](configuration.md#structured-rule-entries-and-the-single-line-rule)
  - [additionalContext: injecting guidance alongside a decision](configuration.md#additionalcontext-injecting-guidance-alongside-a-decision)
- [No-match fallback](configuration.md#no-match-fallback)
- [Undecidable fallback](configuration.md#undecidable-fallback)
- [Assignments looked past when granting](configuration.md#assignments-looked-past-when-granting)
- [Verifying configuration](configuration.md#verifying-configuration)
- [Environment variables](configuration.md#environment-variables)
  - [Boolean values](configuration.md#boolean-values)
  - [Project root detection](configuration.md#project-root-detection)
  - [.env file](configuration.md#env-file)
  - [Error handling](configuration.md#error-handling)
- [Configuration hierarchy](configuration.md#configuration-hierarchy)
- [Configuration reference](configuration.md#configuration-reference)
- [Keeping toolguard up to date](configuration.md#keeping-toolguard-up-to-date)

**`docs/heredoc-parsing-design.md`**
- [What is forced](heredoc-parsing-design.md#what-is-forced)
- [Why this needed rework](heredoc-parsing-design.md#why-this-needed-rework)
- [Rejected alternatives](heredoc-parsing-design.md#rejected-alternatives)
- [Reader's guide](heredoc-parsing-design.md#readers-guide)

**`docs/install.md`**
  - [Set expectations up front (say this before you start)](install.md#set-expectations-up-front-say-this-before-you-start)
- [Phase map](install.md#phase-map)
- [Principles (follow these throughout)](install.md#principles-follow-these-throughout)
- [Install checklist (work through it; do not skip a box)](install.md#install-checklist-work-through-it-do-not-skip-a-box)
- [Phase 0 -- Preflight](install.md#phase-0----preflight)
- [Phase 1 -- Scope](install.md#phase-1----scope)
- [Phase 2 -- Options (recommend, then take their decision)](install.md#phase-2----options-recommend-then-take-their-decision)
- [Phase 3 -- Install method](install.md#phase-3----install-method)
- [The `toolguard-install` helper (use it to cut prompt noise)](install.md#the-toolguard-install-helper-use-it-to-cut-prompt-noise)
- [Phase 4 -- Write the base config, then register the hook (go-live LAST)](install.md#phase-4----write-the-base-config-then-register-the-hook-go-live-last)
- [Phase 5 -- Skills (ask the user)](install.md#phase-5----skills-ask-the-user)
- [Phase 6 -- Validate](install.md#phase-6----validate)
- [Phase 7 -- Offer an initial migration (optional)](install.md#phase-7----offer-an-initial-migration-optional)
  - [7.1 Discover candidate projects](install.md#71-discover-candidate-projects)
  - [7.2 Confirm the list with the user](install.md#72-confirm-the-list-with-the-user)
  - [7.3 Cut the noise for this batch, then migrate each confirmed project](install.md#73-cut-the-noise-for-this-batch-then-migrate-each-confirmed-project)
- [Phase 8 -- Offer a security audit (optional)](install.md#phase-8----offer-a-security-audit-optional)
- [Phase 9 -- Offer an initial maintenance pass (optional)](install.md#phase-9----offer-an-initial-maintenance-pass-optional)
- [Phase 10 -- Enable takeover (only if the user chose it in Phase 2)](install.md#phase-10----enable-takeover-only-if-the-user-chose-it-in-phase-2)
- [Wrap-up](install.md#wrap-up)
- [The install journal (`~/.toolguard/install-journal.md`)](install.md#the-install-journal-toolguardinstall-journalmd)
- [Phase R -- Rollback during install (if the user changes their mind)](install.md#phase-r----rollback-during-install-if-the-user-changes-their-mind)
- [Phase T -- Trace dump and issue reporting (offer this)](install.md#phase-t----trace-dump-and-issue-reporting-offer-this)

**`docs/native-pattern-reference.md`**
- [Quoted verbatim from Claude Code's documentation](native-pattern-reference.md#quoted-verbatim-from-claude-codes-documentation)
- [Known divergences between toolguard and the above](native-pattern-reference.md#known-divergences-between-toolguard-and-the-above)
- [What this file is not](native-pattern-reference.md#what-this-file-is-not)

**`docs/permission-patterns.md`**
- [Contents](permission-patterns.md#contents)
- [Pattern types](permission-patterns.md#pattern-types)
- [Command pattern examples](permission-patterns.md#command-pattern-examples)
  - [DEFAULT patterns (standard)](permission-patterns.md#default-patterns-standard)
  - [REGEX patterns](permission-patterns.md#regex-patterns)
  - [GLOB patterns](permission-patterns.md#glob-patterns)
  - [NATIVE patterns](permission-patterns.md#native-patterns)
- [File path patterns (Read, Write, Edit)](permission-patterns.md#file-path-patterns-read-write-edit)
- [Path normalization](permission-patterns.md#path-normalization)
- [Leading environment assignments](permission-patterns.md#leading-environment-assignments)
- [Compound and multi-line commands](permission-patterns.md#compound-and-multi-line-commands)
  - [The governing principle: when in doubt, ASK](permission-patterns.md#the-governing-principle-when-in-doubt-ask)
  - [Operators](permission-patterns.md#operators)
  - [Multi-line commands and scripts](permission-patterns.md#multi-line-commands-and-scripts)
  - [Command substitution and subshells](permission-patterns.md#command-substitution-and-subshells)
  - [Heredocs and the `__HEREDOC_TO_<sink>__` sentinel](permission-patterns.md#heredocs-and-the-__heredoc_to_sink__-sentinel)
  - [Inline interpreter code (`-c` / `-e` / `-r`)](permission-patterns.md#inline-interpreter-code--c---e---r)
  - [Control structures](permission-patterns.md#control-structures)
  - [Process substitution](permission-patterns.md#process-substitution)
  - [Limitations (summary)](permission-patterns.md#limitations-summary)

**`docs/quickstart.md`**
- [Get toolguard running](quickstart.md#get-toolguard-running)
- [Verify it runs](quickstart.md#verify-it-runs)
- [Write your own permission rules](quickstart.md#write-your-own-permission-rules)
  - [You don't have to become an expert to use any of this](quickstart.md#you-dont-have-to-become-an-expert-to-use-any-of-this)
- [Keep settings.local.json and toolguard_hook.toml in sync](quickstart.md#keep-settingslocaljson-and-toolguard_hooktoml-in-sync)
- [Running unattended (Claude Code auto-mode)](quickstart.md#running-unattended-claude-code-auto-mode)
- [Uninstalling](quickstart.md#uninstalling)

**`docs/security.md`**
- [Contents](security.md#contents)
- [Blanket allow risks](security.md#blanket-allow-risks)
- [A cloned project's config can inject text into Claude's context](security.md#a-cloned-projects-config-can-inject-text-into-claudes-context)
- [Multi-line commands and the ASK-safe guarantee](security.md#multi-line-commands-and-the-ask-safe-guarantee)
- [Loosening the undecidable fallback](security.md#loosening-the-undecidable-fallback)
- [A broken config file also fails safe, not open](security.md#a-broken-config-file-also-fails-safe-not-open)
- [How toolguard protects its own writes](security.md#how-toolguard-protects-its-own-writes)
- [Backup importance](security.md#backup-importance)
- [Testing with dry-run](security.md#testing-with-dry-run)
- [Verify toolguard is running](security.md#verify-toolguard-is-running)
- [The hook can be silently shadowed](security.md#the-hook-can-be-silently-shadowed)
- [Ongoing security review](security.md#ongoing-security-review)
- [Maintaining your toolguard configuration](security.md#maintaining-your-toolguard-configuration)
- [Recommended deny patterns](security.md#recommended-deny-patterns)

**`docs/skills.md`**
- [Security audit](skills.md#security-audit)
- [Maintenance](skills.md#maintenance)
  - [What a run looks like](skills.md#what-a-run-looks-like)
  - [Promotion: moving a rule to the "user" level](skills.md#promotion-moving-a-rule-to-the-user-level)
  - [First run vs periodic](skills.md#first-run-vs-periodic)
  - [`#NOSECURITY`: accepting a risk on purpose](skills.md#nosecurity-accepting-a-risk-on-purpose)
  - [Command-line form](skills.md#command-line-form)
- [Running the skills against toolguard's own repo](skills.md#running-the-skills-against-toolguards-own-repo)
- [See also](skills.md#see-also)

**`docs/takeover-mode.md`**
- [What is takeover mode?](takeover-mode.md#what-is-takeover-mode)
- [When to use takeover mode](takeover-mode.md#when-to-use-takeover-mode)
- [How it works](takeover-mode.md#how-it-works)
  - [Conflict handling across the hierarchy](takeover-mode.md#conflict-handling-across-the-hierarchy)
- [Configuration options](takeover-mode.md#configuration-options)
  - [Ignored allow patterns](takeover-mode.md#ignored-allow-patterns)
- [Security warnings](takeover-mode.md#security-warnings)
- [Example configuration](takeover-mode.md#example-configuration)

**`docs/uninstall.md`**
- [Principles](uninstall.md#principles)
- [Step 1 -- Read the journal](uninstall.md#step-1----read-the-journal)
- [Step 2 -- Replay the reverses, in reverse order](uninstall.md#step-2----replay-the-reverses-in-reverse-order)
- [Step 3 -- Leave `~/.toolguard/` in place (do NOT delete it)](uninstall.md#step-3----leave-toolguard-in-place-do-not-delete-it)
- [Step 3b -- Keep the logs (do NOT delete them by default)](uninstall.md#step-3b----keep-the-logs-do-not-delete-them-by-default)
- [Step 4 -- Verify](uninstall.md#step-4----verify)
- [Step 5 -- Offer a trace dump, and an issue report if toolguard misbehaved](uninstall.md#step-5----offer-a-trace-dump-and-an-issue-report-if-toolguard-misbehaved)
- [Fallback -- no journal available](uninstall.md#fallback----no-journal-available)

**`skills/toolguard-security-audit/SKILL.md`**
- [Hard constraints](../skills/toolguard-security-audit/SKILL.md#hard-constraints)
- [Pass 1 -- Deterministic findings](../skills/toolguard-security-audit/SKILL.md#pass-1----deterministic-findings)
- [Pass 2 -- AI-assisted assessment (opt-in)](../skills/toolguard-security-audit/SKILL.md#pass-2----ai-assisted-assessment-opt-in)
- [Pass 3 -- Safety floor and cross-project sweep](../skills/toolguard-security-audit/SKILL.md#pass-3----safety-floor-and-cross-project-sweep)
- [When to use](../skills/toolguard-security-audit/SKILL.md#when-to-use)
- [Notes](../skills/toolguard-security-audit/SKILL.md#notes)

**`skills/toolguard-maintenance/SKILL.md`**
- [Hard constraints](../skills/toolguard-maintenance/SKILL.md#hard-constraints)
- [Pre-flight: install/skills freshness check](../skills/toolguard-maintenance/SKILL.md#pre-flight-installskills-freshness-check)
- [How this skill runs -- the passes](../skills/toolguard-maintenance/SKILL.md#how-this-skill-runs----the-passes)
- [First run vs periodic (trust level)](../skills/toolguard-maintenance/SKILL.md#first-run-vs-periodic-trust-level)
- [Invocation](../skills/toolguard-maintenance/SKILL.md#invocation)
- [Self-permissioning (running toolguard's tools under governance)](../skills/toolguard-maintenance/SKILL.md#self-permissioning-running-toolguards-tools-under-governance)
- [Tool reference (commands and JSON contracts)](../skills/toolguard-maintenance/SKILL.md#tool-reference-commands-and-json-contracts)
- [Relationship to the security-audit skill](../skills/toolguard-maintenance/SKILL.md#relationship-to-the-security-audit-skill)
- [When to use](../skills/toolguard-maintenance/SKILL.md#when-to-use)
- [Notes](../skills/toolguard-maintenance/SKILL.md#notes)
**`technical-notes.md`** (project root) -- has its own full table of contents at the top of
the file (57 subsections across 7 ticket-grouped topics: subagent identification,
hierarchical config/resolution, logging streams, non-permission resolution, SessionStart
conflict alerting, multi-line Bash decomposition, maintenance/audit tooling). Not
re-duplicated here -- see [technical-notes.md](../technical-notes.md#table-of-contents)
directly.

**`skills/toolguard-maintenance/passes/*.md`** -- the maintenance skill's own internal
per-pass instructions (`1-gather-and-target.md`, `2-consolidate-and-group.md`,
`3-report-and-certify.md`, `4-discuss-and-apply.md`, `recommendation-set-schema.md`). Not
enumerated here -- these are read by the skill itself during a run, not typically looked up
standalone; open them directly if you need the exact per-pass mechanics.
