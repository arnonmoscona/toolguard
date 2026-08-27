---
title: TOO-45 decisions pending Arnon
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/decisions-pending
---

# Decisions waiting on Arnon — TRIMMED 2026-08-25

**Everything that was already acted on has been removed.** The full 657-line version is `DECISIONS-PENDING-archive-2026-08-25.md`, unchanged, in this directory. What follows is only what still needs a decision from you.

**Where the removed material went** — checked, not assumed, before cutting:

| removed | disposition |
|---|---|
| COMMIT HAZARD (untracked `docs/` files + links) | **dead** — `git status` clean; all tracked |
| READ THIS SCREEN FIRST (2026-08-14), section E, phase-1 state | superseded by `TOO-45-punch-list-2026-08-20.md`, which says *"supersedes any earlier ordering"* |
| A1, A7 (tickets 17, 11) | **resolved** — both in `resolved/` |
| A4, A5, A9 (tickets 34, 32, 38) | carried by the 08-20 punch list (items 10, 7a); A9 already decided by you: *"no prose-parsing should be present in the code base"* |
| E1-E3 (`Bash(x:*)` boundary, 8 test edits, uninstall rules) | TAKEN and acted on |
| E4 (native normalises before matching) | **shipped** — `221eba9` *"Item 82 — toolguard strips the wrappers Claude Code strips"* |
| A13-A16, B, C, D | #09 doc work merged; A16 decided 2026-08-20 (ticket 85 filed); B/C/D dispositions taken |

**Still open but tracked elsewhere, not repeated here**: #102 (deferral), #107, the four `--undeclared-types` findings, `/documentation-review`, and the push. The work queue is the punch list; this file is only for things needing *your* call.

---
## `tools/check_doc_links.py` HAS A BLIND SPOT IN THIS PROJECT'S OWN VOCABULARY

I have been reporting *"check_doc_links passes"* as an invariant. **It passes over an unchecked subset.**

`LINK_RE` at `check_doc_links.py:42` uses `[^\]]+` for link text, which **cannot match a label containing `]`** — so any link written as `` [`[native]`](...) `` or `` [`[hard_deny]`](...) `` is **silently skipped**. Measured: **4 of 425 links skipped, and one of those four was genuinely broken.**

The vocabulary this project uses for pattern modes is exactly the vocabulary the checker cannot see. **A `.py` fix, so phase 2 and yours** — but until then the invariant is weaker than I have been saying.

## Two findings rescued from the section-C review-round audit, 2026-08-23 evening

Both surfaced by auditing the 29 blinded review rounds before deleting them (all 29 are untracked, so permanent). Both re-verified by me at HEAD `305caa3`, independently of the agent that found them.

### 1. Ordinary path spellings walk past a deny rule naming the same file

Against the rule `cat /home/arnon/.ssh/id_rsa`, with a positive and a negative control passing in the same run:

| spelling | matches deny? |
|---|---|
| `cat /home/arnon/.ssh/id_rsa` | True (control) |
| `cat ~/.ssh/id_rsa` | True |
| `cat ~/.ssh/../.ssh/id_rsa` | **False — evades** |
| `cat ~/./.ssh/id_rsa` | **False — evades** |
| `cat /home/arnon//.ssh/id_rsa` | **False — evades** |
| `cat /home/arnon/./.ssh/id_rsa` | **False — evades** (not in the original finding; found on re-verification) |
| `cat /home/arnon/.ssh/known_hosts` | False (control) |

**Exposure measured before proposing anything, per `.claude/rules/evidence-before-fixing.md` — and it splits the finding in two:**

| shape | featherhill (honest corpus) | toolguard (dogfood) | instagram |
|---|---|---|---|
| `//` double slash | **20 — every one accidental** | 27 | 1 |
| `../` or `./` through an absolute path | **0** | ~10, all relative navigation (`cd skills/x && readlink -f ../../docs`) or this campaign's own probes | 0 |

featherhill's 20 are Claude writing `tail //tmp/server-flo72-nav-test.log`, `mkdir //tmp/claude-code`, `grep //tmp/...` — **nobody typed those to evade anything; the agent doubled a slash by accident.** That is accidental reachability against a mechanism that fails silently, which by the rule's own test (*"zero occurrences plus accidental reachability plus silent failure is still a fix"*) is a fix.

**The `../` and `./` round-trips are the opposite case: zero occurrences anywhere, and they need deliberate spelling.** toolguard governs Claude, not an adversary. By the reachability filter these are a defer.

**Recommendation: file one ticket scoped to `//` collapsing, and record the `../`/`./` variants in it as measured-zero and deliberately deferred.** Filing needs your approval — not filed.

### 2. `pwd.getpwnam` is a route to the home directory that `--ambient` structurally cannot see

`toolguard/normalization.py:140` calls `pwd.getpwnam(name).pw_dir`; `grep -c pwd tools/architecture_fitness.py` returns **0**. There is no `PATH_AMBIENT_OWNERS` entry because the scan has no arm that would ever look.

This is the **fourth** instance of the pattern `.claude/rules/evidence-before-fixing.md` already names as the instrument's weak spot — *"`expanduser`, `resolve` and `absolute` each got through by not being on the list yet. The check was rigorous about what it had been told and blind to what nobody had declared."*

**The reachability filter does not apply here**, because nothing is broken in the product — the gap is in the instrument, and an instrument that reports a clean `--ambient` while a whole route goes unexamined is a false negative by construction. Cheap declarative fix: add a `pwd` arm to the scan plus an owner entry.

### 3. The decision vocabulary is a bare string literal, and its strictness order exists in three copies

Rescued from the section-B audit and **verified by me at HEAD `305caa3`** by reading all three sites.

Three identical mappings, three names, three modules:

| module | name | value |
|---|---|---|
| `toolguard/compound.py:55` | `_DECISION_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |
| `toolguard/tools/replay.py:35` | `_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |
| `toolguard/tools/mining.py:62` | `_VERDICT_STRICTNESS` | `{"allow": 0, "ask": 1, "deny": 2}` |

And the vocabulary underneath them is not named at all: `constants.py` defines only `STATUS_ASK = "ASK"` (uppercase, the log status). The lowercase decision words appear as bare literals — **207 occurrences of `"deny"` alone** in assignment or comparison position across the package. This is precisely the case the global CLAUDE.md rule names: *"decisions like `deny`/`ask`, kinds, statuses, format names"* are the offenders that matter most because they are repeated across modules and tests.

**Two reasons not to treat consolidation as mechanical, both from this project's own history:**

1. **`compound.py` documents its separation as deliberate** — *"Kept separate from `_combine_strictest`'s own ordering: that function combines several already-decided sub-commands with its own reason-building rules, while this floor clamps a single decision."* The three uses genuinely differ: a floor clamp, a verdict-change comparison, and a cluster headline.
2. **`project_one_structure_two_questions` records this exact shape going wrong twice in two tickets** — widening a shared structure for one consumer silently changed the other, once downgrading an unoverridable `hard_deny` to `ask` **with a green suite**.

**So the safe split is: name the vocabulary, leave the three orderings alone.** Extracting `ALLOW`/`ASK`/`DENY` as shared constants is pure win and cannot change behaviour. Merging the three dicts into one is the part that carries the risk, and the value is lower — they are three lines that happen to agree today, and the comments say two of them agree by coincidence of purpose rather than by shared meaning.

**Not filed** — needs your approval. Neither the follow-up queue nor any DURABLE file records it.

**Delete-list dependency**: the only two files recording this finding are `TOO-45/TOO-45 phase 2 tools-hierarchy tools-mining - coder report.md` (section B) and `TOO-45/TOO-45 phase 2 work unit 7 (tools-hierarchy, tools-mining) - coder task recall.md` (section A). **Both are on the delete list.** The finding is now captured here, so both may go.

### 4. `architecture_fitness.py --predicates` R3 reports PASS over a live prose re-parse, for two independent reasons

**Correction, same evening: the arm is `--predicates`, not `--contract`.** I wrote `--contract` first; that flag does not exist, and running it fails with `unrecognized arguments`. The real arm **passes**, which is the whole point — it prints, verbatim:

```
=== R3: PASS ===
  (excluded as sanctioned: compound.py::fallback_kind_for_reason)
```

It announces an exemption for a function that no longer exists, and calls the result a pass.

Surfaced by the implementation-habits extraction; **verified by me at HEAD `305caa3`.**

**Reason one — the exclusion list names a function that no longer exists.**

```
tools/architecture_fitness.py:1606
R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}
```

`grep -rn "def fallback_kind_for_reason" toolguard/` returns **0**. The function was removed; its sanction was not. A stale exemption is strictly worse than none, because it reads as a considered decision.

**Reason two — the detector is name-based, so a one-letter local defeats it. The blind spot is documented in the detector's own docstring** (`tools/architecture_fitness.py:1660-1664`): it returns *"every production site that extracts structured meaning from a `reason`-named string"*, via *"three shapes, all keyed on a Name/Attribute whose OWN name contains 'reason'."* A receiver named `r` contains no such substring, so it is invisible **by design, not by oversight** — the check was written to find one spelling of the antipattern and reports PASS for every other. At `compound.py:1119-1123` there is a live re-parse of a prose string the program itself produced:

```python
r = uv.reason
if " -> " in r:
    pattern_part = r.split(" -> ", 1)[-1]
```

The extracting agent tested this with a paired control — the identical parse with the receiver named `reason` instead of `r` — and the check **fired at 2 sites for `reason` and 0 for `r`**. I re-read the code and confirm the shape and the stale sanction; I did not re-run the paired control.

**Why this matters more than an ordinary lint gap.** This is the exact antipattern the project's own CLAUDE.md documents with a measurement: rendering a decision to a human-readable reason string, discarding the structured result, and later re-deriving facts by pattern-matching that prose. **Measured cost when it last happened: 813 of 975 compound-allow decisions (83%) under-logged, and 1,943 sub-commands reaching the audit trail with no record at all.** Nothing failed and nothing warned; the audit log looked complete.

So the position today is: **the codebase contains an instance of its most expensively-documented antipattern, and the instrument built to catch that antipattern reports PASS.** That is this campaign's signature failure — a mechanism that fails open and says nothing — occurring in the very check meant to prevent it.

**What is NOT established:** whether this particular site currently produces a wrong log entry. The shape is present; the consequence is unmeasured. That measurement should precede any fix, per `.claude/rules/evidence-before-fixing.md`.

**Suggested split, mirroring finding 3:** deleting the stale `R3_SANCTIONED_SITES` entry is pure win and cannot change behaviour. Making the detector receiver-name-independent is the real fix and will likely surface other sites — which is the point, but it should be a measured, scoped piece of work rather than a drive-by. **Not filed — needs your approval.**

---

## F. PRE-PUSH — GIT RULES AT USER LEVEL: ALLOW WORKTREES (decided, not yet applied) — Arnon, 2026-08-25

> *"I think that I made a mistake in my git rules. I should allow worktrees so that it is easier for you to run parallel agents on the same code base. Make a note that we should review the git rules we have at the user level to refine them based on the experience in TOO-45."*

**Measured current state, 2026-08-25 — worktrees are not prohibited anywhere, which sharpens the problem rather than dissolving it:**

| where | rule | level |
|---|---|---|
| `~/.toolguard/rules/git.rules.toml:182` | `git worktree list` | **allow** |
| `~/.toolguard/rules/git.rules.toml:268` | `worktree add\|move\|remove\|prune\|repair\|lock\|unlock` | **ask** |
| `.claude/toolguard_hook.toml:62` | `Bash(git worktree *)` | **allow** — in this project only |
| `~/.claude/CLAUDE.md`, git section | worktrees **not mentioned** — the list is commits, pushes, checkouts, merges, branches, stashes, resets | prose |

**So the change is an `ask` → `allow` move at user level, not a new permission.** And `ask` is the thing that actually blocks parallel agents: `12` B8 records two ~90-minute stalls from prompting commands in briefs, with the finding *"a subagent waiting on a permission prompt is indistinguishable from a stalled one"* — and it names `git worktree` explicitly as a known prompter (*"that will always prompt"*). **Under unattended operation an `ask` is not a prompt, it is a stall.** This project already worked around it locally, which is why the friction never surfaced here.

**Two further things for the same review, both found while checking the above:**

1. **The prose rule is ambiguous about worktrees.** It forbids *"checkouts, merges, branches"* and a `git worktree add` creates a branch-shaped checkout, so an agent can reasonably read the prose as forbidding it even where the permission rules allow it. **Prose and rules should agree explicitly**, in whichever direction is decided.
2. **Worktrees are directly supported by the tooling.** Both the `Agent` and `Workflow` tools take `isolation: "worktree"` to give each agent its own tree, which is the mechanism for parallel agents on one codebase without collisions. Allowing them unlocks a capability, not just a command.

**The wider ask, which is the actual item: review the user-level git rules against TOO-45 experience.** Not just worktrees — the whole `~/.toolguard/rules/git.rules.toml` set, asking of each rule whether its level still matches how the work is actually done now, and specifically which `ask` rules are really stalls under unattended operation. **Arnon's call, not mine — this is his global config and it governs every project on the machine.**
