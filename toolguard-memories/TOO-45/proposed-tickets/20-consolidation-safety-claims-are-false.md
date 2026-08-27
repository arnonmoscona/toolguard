---
title: Consolidation can escalate ask to allow and silently drop allows; its safety
  claims are false
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/20-consolidation-safety-claims-are-false
---

**PARTIALLY FIXED in `05f786d`.** Only section 5 is closed, as a side effect of #18's matcher fix; still open: sections 1-4 all reproduce, and `toolguard/tools/consolidate.py:597` still gates on `broadened_count` alone — the ticket's docstrings were corrected over otherwise-unchanged code.

> **UPDATE 2026-08-13, test-repair campaign. §1–§4 all reproduce exactly against live code — nothing in the substance needed correcting. Three things are new, and one of them outranks the ticket's own findings.**
>
> ### The safety gate on the only analyzer that WRITES had zero test detection
>
> **`_check_family2_safe` could be stubbed to always pass, have its corpus check dropped, or check only the before-verdict — each producing 0 failures across all 38 tests.** This is the gate standing between a static-subsumption proposal and `--apply` changing the user's permission config. Family 1's corpus gate was equally undetected: `broadened_count` and `tightened_count` were each silently deletable. Both are now partly covered by two new tests.
>
> ### Family 2's corpus gate may check the one thing that cannot happen
>
> Its `broadened_count > 0` condition **looks unreachable**: removing an allow rule cannot move a replayed decision *toward* allow. A direct probe gave `broadened: 0, tightened: 0`. If that holds, the gate tests for broadening — which is impossible here — and **skips tightening, which is exactly what §3 demonstrates does happen.** Sharper than §2 as written.
>
> ### Mutate toward the fix: this ticket's own §3 fix is invisible to the suite
>
> Applying §3's proposed fix (exclude no-colon EXACT bodies from family 2's args filter) produces **0 failures**. The suite sees neither the defect nor its correction — so the fix could land, or silently regress later, with nothing noticing.
>
> ### Two staleness corrections to this ticket and its queue section
>
> - **§1's production complaint is stale.** It quotes `BroadeningProposal.overlaps_guard_rules` claiming *"resolution PROTECTS these in-context… verdict-based punch-through is unreachable here."* The shipped docstring now says the **opposite** and names the punch-through case explicitly. **The false claim had migrated into the *test* docstring**, which is where it was found — production was corrected and its copy in the tests was not. A doc-drift mechanism worth naming on its own.
> - **`follow-up-queue.md:514` no longer resolves.** It cites two strings at `test_tools_consolidate.py:523` and `:405` that the #07 doc sweep (commit `7460ffb`) removed; the line numbers through that section are all stale.
>
> ### Measured escalation, recorded not pinned
>
> Broadening to `uv run alembic :*` takes `uv run alembic downgrade base` and `uv run alembic destroy` from **ask → allow**. No assertion was added, because pinning it would encode the escalation as expected.
>
> Module went 38 → 40 tests. Nine mutations still survive unrepaired and are listed in the campaign notes.

# Consolidation's safety claims are false

**These are the only findings `--apply` enacts.** `toolguard-maintain --apply --write` writes consolidations into the user's config; the neighbouring engines (redundancy, cross-layer) only report. So this is the one analyzer whose output changes permissions automatically, and its stated safety properties do not hold.

Found during the TOO-45 #07 sweep by executing the docstrings in `toolguard/tools/consolidate.py` rather than reading them. Twelve false claims in one module; the four below have teeth.

## 1. Consolidation can escalate `ask` to `allow` (privilege escalation)

`BroadeningProposal.overlaps_guard_rules` documents itself as:

> resolution PROTECTS these in-context … this is NOT a punch-through … Verdict-based punch-through is unreachable here.

False on the module's **own worked example**, which is also its own unit test's config:

```
added='uv run alembic :*'   overlaps=("ask 'uv run:*'",)
  'uv run alembic downgrade base':  before=ask   after=allow   PUNCH-THROUGH
  'uv run alembic destroy':         before=ask   after=allow   PUNCH-THROUGH
```

Allow-vs-ask ties break on `_literal_prefix_specificity` (`permissions.py:276`), and the strings reaching `resolve_allow_ask` are wrapper-free: **16 for `'uv run alembic :*'` vs 7 for `'uv run:*'`**. So the new, more-specific allow beats the broader existing ask. This is a real precedence contest, not a fallback artefact — before the change no allow matches and the ask wins by matching; after, both match and the allow wins. The protection holds only when the ask is *more* specific than the proposed allow — verified: `ask 'uv run alembic downgrade:*'` correctly stays `ask`.

The field exists to warn about exactly this, and its docstring says it cannot happen.

## 2. Consolidation can silently REMOVE an existing allow (tightening)

Two accepted proposals, both reporting every probe unchanged:

```
removed=('cat ./x:*', 'cat ./y:*')   added='[regex]^cat (\./x|\./y)'
  evidence: '10 probes unchanged; no corpus'
  'cat x':  before=allow  after=ask   CHANGED
```
The DEFAULT pattern also matches the *path-normalized* command; the generated `[regex]` does not.

```
removed=('git d*ff a:*', 'git d*ff b:*')   added='[regex]^git d\*ff (a|b)'
  'git diff a':  before=allow  after=ask   CHANGED
```
Only the **varying** token is checked for wildcards, so a wildcard in a fixed token is escaped into a literal.

The docstring claims *"the no-changed-decision gate additionally guarantees it never tightens"* and describes the result as **"EQUIVALENCE-PRESERVING"**. Neither holds.

**Family 2 is weaker still, and this is the sharpest single fact in the ticket.** `_check_family2_safe` (`consolidate.py:582-596`) runs exactly **two** probes (`small_cmd` and `small_cmd + " --x"`), and its corpus gate is `if diff.broadened_count > 0: return False` — **`tightened_count` is never checked at all.** So a family-2 removal can tighten observed decisions, on a real corpus, and still be emitted. That is not an edge case the probes happen to miss; it is a gate that does not look.

### A note on where "equivalence-preserving" came from

`consolidate.py:397` uses the phrase **only in a failure message**: `f"probe decision changes: {changed}/{len(probes)} (not equivalence-preserving)"`. Failing the gate proves non-equivalence; passing it proves nothing about the match set. During this sweep an editor read the term off that line and wrote it into `maintenance.py` in three places as a positive property — the implication inverted on the way. Worth knowing when fixing: the phrase is load-bearing in exactly one direction, and the codebase already contains a reader who got it backwards.

## 3. "Structurally proven safe" is false — the probe is the only guard

Family-2 (static subsumption) proposals are documented as *"structurally proven safe before the probe is run"*. `_static_prefix_of` returns `True` for pairs `match_command` does not actually subsume:

```
_static_prefix_of('uv run', 'uv run python') = True
match_command('uv run python', ['uv run'])   = False
```

With a third rule covering the probes, a proposal is emitted whose own rationale **string** asserts the false property: *"…is statically subsumed by 'uv run': every command matched by the former is also matched by the latter"*.

**And this reaches a genuine tightening through the public API.** Allow list `['uv run', 'uv run python:*', '[regex]^uv run python( --x)?$']`:
```
static-subsumption | removed = ('uv run python:*',) | 2 positive probes pass; no corpus
  'uv run python'            before=allow  after=allow
  'uv run python --x'        before=allow  after=allow
  'uv run python -m pytest'  before=allow  after=ask    CHANGED
```

**A corpus does not save it.** With a corpus containing that exact command, the proposal is *still emitted*, because family 2 rejects only on `broadened_count`:
```
static-subsumption | removed = ('uv run python:*',)
  evidence: 2 positive probes pass; corpus replay 1 entries, 0 broadened
  'uv run python -m pytest'  before = allow  after = ask
```
So family 2 tightens **even with a corpus**, and its evidence string says "0 broadened" while doing it. This is why "give it the corpus" (fix 2 below) is necessary but **not sufficient** for family 2.

## 4. `_static_prefix_of` is unsound on a `/` boundary, and a test pins the unsoundness

```
claims_subset=True   witness: '/usr/bin/env python'
  matched by small '/usr/bin/env:*':  True
  matched by large '/usr/bin:*':      False
```

`match_command` gates on a space after the first token, so a `/` inside the base token is not a subsumption boundary. **`test_path_boundary_prefix_subsumes` asserts this exact case as correct** — the test will have to change with the code.

## 5. Family 1's stated mechanism is wrong (lower severity)

*"By construction the generated regex is a subset-or-equal of the union … so it can never broaden."* False for a single-token group:

```
generated: '[regex]^(cat|ls)'
  'lsof -i':  regex=True  union=False   BROADENS
  'lstat':    regex=True  union=False   BROADENS
```

The gate *does* reject it (4 of 10 probes change) — but by probing, not by construction. The claim attributed the safety to the wrong mechanism, which matters because someone optimising away "redundant" probes would read it as licence.

## The compounding factor

`run_maintenance` calls `propose_consolidations(config, tool)` **without the corpus**, while giving the corpus to the two neighbouring engines. So the one category of finding that `--apply` writes into a config is also the one that is never replay-verified against real decisions — it is guarded only by synthetic probes, and §1–§4 show the probes miss escalations, tightenings, and unsound subsumption.

## The approval surface shows more than what was approved

Found later in the sweep, in `rule_apply.py`, and it compounds everything above: **a dry run's `diff` carries the writer's normalisation, not just the proposals' edits.**

Executed — unsorted TOML plus a proposal set where every proposal drifts:

```
total_applied = 0
diff shows:  Bash(aaa:*) re-sorted above Bash(zzz:*)
             the file's `deny = []` and `ask = []` lines DELETED
```

Nothing was applied, and the diff is still non-empty. The deletions are `rule_sort.reassemble_permissions_section`'s `if not entries: continue`, which discards an empty sub-list and any comments attached to it.

Only `written` is gated on `applied`, so a pure-drift batch changes nothing on disk. But **once one proposal applies, the unrequested normalisation is written with it** — and the diff is what the maintenance skill shows the user for approval. The user approves a consolidation and also gets a re-sort and two deleted lines they were never asked about.

Recorded as `RA1` in `reports/follow-up-queue.md`.

## Fix direction

1. **Verdict-aware safety, not decision-count-aware.** The gate compares probe verdicts before/after but treats "no probe changed" as proof. It needs to reason about the *rule set*: a new allow that is more literal-specific than an existing ask will win, regardless of what the probes happened to cover.
2. **Give `propose_consolidations` the corpus**, like its neighbours. Cheapest single change, and it would have caught §1 and §2 on any real corpus containing those commands.
3. **Fix `_static_prefix_of`'s boundary rule** to match `match_command`'s actual gate, and update `test_path_boundary_prefix_subsumes`.
4. **Never emit a proposal whose rationale string asserts a property the code did not check** (§3). Prose is output — carry the structured evidence and render it at the edge.

## Interaction with proposed ticket 18

Ticket 18 (`match_command` over-matches multi-token DEFAULT prefixes) is upstream of all of this: `_static_prefix_of` is trying to model a matcher that is itself wrong. **Fix 18 first**, then re-derive these — several may change shape, and §4's witness in particular depends on the current gate.

## Recorded in full

`reports/follow-up-queue.md`, rows C1–C7 with reproductions, plus C-R1/C-R2 refactoring candidates. C4 is the false rationale **string**, left unedited under the comments-only rule and deliberately now contradicting the corrected docstring above it. Three overclaiming docstrings in `test_tools_consolidate.py` are flagged there too.
---

## MEASURED 2026-08-20 — the gate has a hole the amendment does not name

Read at `toolguard/tools/consolidate.py:594-605` (`_check_family2_safe`):

```python
if corpus:
    diff = replay(corpus, config, config_b)
    if diff.broadened_count > 0:
        return False, f"corpus replay: {diff.broadened_count} broadened"
    evidence = f"... corpus replay {len(corpus)} entries, 0 broadened"
else:
    evidence = f"{len(probes)} positive probes pass; no corpus"
return True, evidence
```

**With no corpus, there is no broadening check at all, and the function returns `True`.** The consolidation is approved on positive probes alone.

**`broadened_count` itself is not the defect.** `replay.py:10` defines broadened as *"B is looser (deny -> ask, deny -> allow, ask -> allow)"* — so `ask -> allow` **is** counted, and the gate does catch the ticket's headline escalation **when a corpus is supplied.** The amendment's phrase *"gates on `broadened_count` alone"* is therefore not quite the defect: the classification is right, the **coverage** is not.

### This is the campaign's signature shape, in the safety gate itself

*Safe-when-unverifiable.* The evidence string is scrupulously honest — it literally says `no corpus` — but the boolean the caller branches on is `True`. Anyone reading the return value gets "safe"; only someone reading the prose gets "unchecked". **That is exactly the prose-versus-structured-data failure this project's own rule was written about**: the fact is in the sentence and not in the value.

Same family as ticket 73 (*"the corpus-replay safety evidence is strongest exactly when it is emptiest"*), and as `run_guard` reporting `ok=True` over zero cases.

### Fix direction — decide, do not patch

Three defensible answers, and the ticket should state which and why:

1. **Refuse without a corpus.** No evidence, no consolidation. Safest; may make the tool unusable on a fresh install with no logs.
2. **Return a third state** — `safe` / `unsafe` / `unverified` — so the caller cannot collapse "checked and clean" into "not checked". Best fit for the project's own rule about carrying structure rather than prose.
3. **Keep returning `True` but require the caller to surface "no corpus"** prominently to the user before applying.

**Whichever is chosen, the boolean must stop meaning two different things.** Also check `_check_family1_safe` (`:324`) for the same branch — this was read in one function only.
