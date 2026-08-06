---
title: TOO-45 follow-up queue
type: note
permalink: toolguard/too-45/reports/follow-up-queue
tags:
- task-memory
- TOO-45
- report
---

# TOO-45 follow-up queue

What comes after the R6 replacement stages are committed. Split into **change challenges** (measuring instruments, implemented in throwaway copies and discarded) and **real defects** (candidates for actual tickets).

## Change challenges — run after the R6 stages are committed

These are **experiments, not deliverables.** Each is implemented in throwaway copies of pre-TOO-45 master and the post-R6 branch, measured, judged, and thrown away. Nothing lands in the repo.

**The discipline that makes them worth anything:** the throwaway implementations must be written *as if they were the real ticket* — same care, same tests, same handling of awkward cases. The moment an implementer takes a shortcut because "it's only an experiment", it will take that shortcut in whichever tree makes shortcuts easier, which is exactly the signal being measured.

Full detail per challenge in [[change-challenges]], produced by an agent deliberately kept blind to this ticket's analysis.

| order | challenge | axis | why |
|---|---|---|---|
| 1 | **CC-1** per-session budgets / rate limits | decision-relevant state; session identifier becomes load-bearing for policy | subsumes the session-layer scenario Arnon sketched |
| 2 | **CC-4** govern a tool with structured arguments | domain-model extensibility, dispatch fan-out | attacks the decision path from the opposite end to CC-1 |
| 3 | **CC-2** expiring / windowed rules | time-dependence, clock seams, rule identity vs pattern string | **run immediately after CC-1 as a controlled contrast** — they share the time axis but differ on cross-process state, so the delta isolates "cannot express time" from "cannot express state". Running either alone confounds them. |
| — | **semver pattern type** | duplicated vocabulary | **calibration control.** Everyone predicts it is trivial. The prefix tuple is hand-copied across ~7 sites in 4 modules with no single source of truth, and a missed site fails *silently* into `fnmatch`. Its real cost calibrates how much to trust intuition on the rest. |

Lower-ranked: CC-5 (resident long-lived process), CC-3 (rewrite tool input, not just judge it), CC-8 (decision derivation + counterfactual), CC-6 (remote org-managed policy), CC-7 (multi-user host safety).

**Flagged as likely uninformative** by the designer, recorded so nobody re-proposes them: a new `no_match_fallback` value, another governed command tool, a fifth log stream, enabling JSONLines, and anything measured by renaming.

**CC-3 carries a caveat:** it may not discriminate if the parsing IR is lossy in both a good and a bad version by design. Settle that first with a one-hour round-trip property test — decompose then reassemble every corpus command — before committing to the full challenge.

### The session-layer framing (Arnon's, worth carrying into CC-1)

A session-scoped override is naturally **an additional configuration layer** alongside the existing hierarchy, not a bolted-on policy source. That reframes the challenge into a sharper question: **is the layer abstraction open for extension, or welded to filesystem discovery?**

Measured beforehand, as a prediction to score: `Configuration` holds `layers: Tuple[ConfigLayer, ...]` and tests already hand-construct layers with zero file I/O, so injection is possible *at the type level*. But `load_configuration()` is "the single public entry point" and "performs all discovery and parsing internally" — discovery and construction are fused, with no supported production path to inject. The vocabulary is file-shaped throughout (`ConfigLayer` is "one **discovered** configuration source"; `Provenance` requires `file_format` ∈ {json, toml} and `source_type` ∈ {claude, toolguard_hook}). And `Provenance` is documented as **"display-only… without exposing file/format decisions as control flow"** — a session layer carrying an expiry makes provenance-shaped metadata control-relevant, **falsifying a stated invariant** rather than merely extending a type.

**Prediction on record:** this half will barely discriminate between the trees, because the layer model is essentially unchanged between them — D1a moved orchestration out of `Configuration` but left it as the layer holder, and the load-vs-query split was the plan's "candidate step", identified and never done. The *consuming* half (precedence in the cascade, provenance on the verdict, explaining the override in the audit trail) should discriminate, because the branch has one chokepoint and a structured verdict. If that split holds, one experiment isolates what was fixed from what was not.

## Real defects found, ranked — ACCEPTED BY ARNON 2026-08-06

**Status: accepted for fixing.** Sequencing: after R6's S3 and S2 land, because `hook.py` is contested until then (S3 removes `_verdict_from_decision` from it, S2 moves `decide()` out) and defect 3 lives there. Two agents editing the real tree concurrently is the shape that produced today's contaminated-baseline incident — not worth the risk to save twenty minutes.

**Open question for Arnon: which ticket?** These are pre-existing defects that TOO-45 did not cause and were found only because a blind reviewer went looking at the product. My recommendation is a separate ticket for defects 1-4, since mixing unrelated bug fixes into an architecture-overhaul commit is exactly what makes a refactor hard to review or revert. Defect 5 is a one-line docstring correction of a false claim and can ride along with the R6 stages, consistent with the several other false-comment corrections this ticket has already made.


All found by the blind challenge designer, then verified independently by me. **None of these were surfaced by the seven directed report agents** — a methodological result in itself: every prior agent read this ticket's analysis and inherited its frame; the blind one looked at the product instead.

**1. `log_writer` can `sys.exit(1)` (lines 198, 476) — the audit path can take down enforcement.** Claude Code treats only exit code 2 as blocking, so a full disk or a permissions error on the log directory means the hook exits non-blocking and **the tool call proceeds unjudged**. A fail-open with no timing component. Highest-ranked of these.

**2. The join key between matching and rule entries is the pattern string itself, and it is known non-unique** — `merge_entries` already exists to handle same-pattern entries with contradictory metadata. R2 removed the index-parallel arrays but left the string join.

**3. "Once per session" has been wanted three times and never implemented.** Three copy-pasted date-marker files plus three `hook.py` module globals whose own docstrings concede they cannot work in a per-call process. Worth noting this is the exact trap already recorded in long-term memory, sitting in the codebase in triplicate, and missed by every directed pass.

**4. Documentation defect:** `docs/config-sync.md` documents markers in `/tmp/toolguard-warnings/`; the code writes `<log_dir>/.toolguard-warned-*`.

**5. `resolve.py:2` claims "Pure, side-effect-free permission resolver layer"** while matching reads live disk state (`normalization.py:47-50, 81` — `exists()`, `is_symlink()`, `resolve()` — reached from `permissions.py:146` and `:194`). The narrower line-7 claim ("no logging, no stdin/stdout, no `sys.exit`") remains true.

**6. `session_id` is read by nothing on the decision path**, while `permission_mode` *is* read and is documented three times as "diagnosis only, never affects the verdict". A clean observational/decisional split that CC-1 deliberately breaks — useful context, not a defect.

## Deprioritised deliberately

**The check-to-use race in path matching.** Real, but Arnon's call (2026-08-06) is not to complicate the design for it: sub-second hook execution on a single-user machine makes a file changing underneath the check unlikely, and the system takes the strictest result across several layers, so something *could* slip but has more than one chance to be caught. Recorded as noted-and-deprioritised, not open. **Do not rat-hole on it.**

**Worth keeping from that finding, because it is not about races:** a verdict is not purely a function of config and input, since matching reads live disk state. The golden corpus implicitly assumes determinism and nobody has checked that assumption. Cheap to test; it concerns the verification infrastructure rather than the product.
