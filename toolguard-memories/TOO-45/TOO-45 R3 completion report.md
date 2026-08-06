---
title: TOO-45 R3 completion report
type: note
permalink: toolguard/too-45/too-45-r3-completion-report
tags:
- task-memory
- TOO-45
---

## Step 1 finding, first (this is the part that matters)

`resolve.py:456`'s `if reason.startswith(_no_match_prefix):` was **not** recovering data that was otherwise unavailable, and it was **not corrupting anything** -- verified by execution across all 5 no-match-fallback branches (no-rules-configured, and the four `no_match_fallback` values: `deny`, `allow_with_warning`, `allow`, `ask`) on `resolve_file_path_permission_detailed`. Every branch produced the exact same reason text before and after the fix; `tools/corpus_build.py --verify` confirms byte-for-byte agreement across all 6,401 in-process + 61 e2e golden cases.

What the check WAS doing: `permission_resolution._resolve_unclamped`'s no-match-fallback branch hardcoded `"Command does not match any allow patterns..."` (Bash-phrased) for every caller. `resolve.py`'s file-path caller then parsed that prefix back out of the returned `reason` string purely to reword it to `"Path does not match any allow patterns..."` for file-path tools, preserving the fallback-specific suffix. This is real prose-parsing per R3's letter -- it reads a fixed substring out of a `reason`-named string to decide a rendering choice -- but the round trip was not lossy: it can't be, because the substituted prefix and the suffix it preserves are both literal, deterministic constants at the point they're generated.

The fix (below) closes the gap by giving the caller the correct vocabulary at the source, so there is no round trip to audit at all -- not just no round trip that today happens to be safe.

## Step 2: the fix

`toolguard/permission_resolution.py`:
- `_resolve_unclamped(config, tool_name, decide_detailed, subject: str = "Command")` -- new parameter, threaded into the four `"{subject} does not match any allow patterns..."` reason strings inside the no-match-fallback branch (the "no rules configured at all" branch already used the real `tool_name`, untouched).
- `resolve_permission_detailed(config, tool_name, decide_detailed, subject: str = "Command")` -- forwards to `_resolve_unclamped`. Additive, keyword-only-in-practice parameter with a default matching prior behaviour; every existing positional caller (2 production, ~20 test) is unaffected.

`toolguard/resolve.py`:
- `resolve_file_path_permission_detailed` now calls `resolve_permission_detailed(config, tool_name, _decide_detailed, subject="Path")` and uses `resolved.reason` directly -- the `_no_match_prefix`/`reason.startswith(...)` block is gone.
- `resolve_bash_permission_detailed`'s call site is untouched (default `subject="Command"` reproduces prior behaviour exactly).

Both docstrings updated to document the new parameter and why it exists (TOO-45 R3 cross-references included so a future reader lands on this reasoning, not just the diff).

### Acceptance -- actual output

```
$ uv run python -m unittest discover -s test -t .
Ran 2387 tests in 31.046s
OK

$ uv run python tools/corpus_build.py --verify
In-process: 6401 cases in 8.56s. End-to-end: 61 cases in 3.33s.
OK: no differences.

$ uv run python tools/architecture_fitness.py --guard
=== --guard: PASS === (no violations)
canaries: 12 evaluated against the live hook

$ uv run python tools/architecture_fitness.py --predicates   (R3 section)
=== R3: PASS ===
  (excluded as sanctioned: compound.py::fallback_kind_for_reason)

$ uv run ruff format . && uv run ruff check --no-cache .
150 files left unchanged
All checks passed!
```

R3 site count: **1 -> 0** (the `resolve.py` violation is gone; the ticket-sanctioned `compound.py::fallback_kind_for_reason` exclusion is the only remaining entry, and R3 now reads **PASS** instead of FAIL).

No behaviour changed: verified both by the corpus (`--verify`: no differences, 6,401 + 61 cases) and by a standalone execution probe over all 5 file-path no-match-fallback branches before the edit (see below) -- reason text was identical byte-for-byte in every branch both before and after.

## Step 3: assessment of the remaining sanctioned site, `compound.py::fallback_kind_for_reason`

**Not changed, per the task instruction.** Assessed by execution against two independent scenario batteries (11 distinct scenarios total, including an adversarial two-leaf, both-orders case designed to reproduce the shape of the earlier `_parse_compound_match_details` bug). Full detail below; short version: **the prose classification never disagreed with the structural ground truth in any scenario tried.** This is not a second instance of the R1e bug. It IS a real, avoidable indirection with an unused structural alternative sitting right next to it in one of its two call sites -- worth a note for a future ticket, not an emergency.

`fallback_kind_for_reason(decision, reason)` has exactly two production call sites left (both grep-verified):

**Call site 1 -- `compound.py:526`, inside the ordinary (non-ask-floor) sub-command aggregation loop.** `resolve_one(cmd)` is a plain `(decision, reason, additional_context)` 3-tuple contract (`toolguard/resolve.py:735`, `_resolve_one`). Tracing upstream: `_resolve_one`'s own closure `_decide` (`resolve.py:667`) **already computes `fallback_kind` structurally** -- `"warned"`/`"silent"`/`None`, from `resolved.matched_rule is None` and `resolved.fallback_warning`, never by parsing `reason` (the closure's own docstring says this explicitly) -- but `_resolve_one` discards it before returning to `compound.py`'s loop, which then re-derives the identical classification from `reason` text one function call later. Verified by execution (`no_match_fallback_allow_with_warning` case) that the two values agree; they are provably certain to agree by construction, since the reason text this loop reads is itself generated by the same `_resolve_unclamped` computation that produced the discarded structural value -- there is no independent path for them to diverge on.

Widening the contract to stop discarding the value is a real, measured cost, not a hypothetical one: `resolve_one`'s 3-tuple shape is hand-built by **20** test closures across `test_compound.py`, `test_hard_deny.py`, `test_hierarchical.py`, and `test_multiline_bash.py` (grep count, matches the docstring's own "~18" estimate closely enough to trust it). That is a genuine, non-trivial migration, which is presumably why this stayed grandfathered rather than getting the R1e treatment.

**Call site 2 -- `hook.py:438`, inside `_reason_suffix_or_placeholder`, called only from `_log_non_allow_decision`'s deny-side "Violated Rules" logging** (the allow side was already converted to a structural read in R1e -- see `_unit_matched_rule_for_log`, which reads `unit.fallback_kind` directly). This is where I looked hardest for a second instance of the earlier bug, because it is architecturally the same shape (final-verdict logging, reason-string classification). Finding: **a structural equivalent already exists and is unused.** `RuntimeVerdict.sub_matches` (populated by `resolve_bash_permission_detailed`, real production data, not a test artifact) plus the already-public `_deciding_sub_match(decision, sub_matches)` can identify the deciding leaf and read `.fallback_kind` directly -- no reason-text parsing needed. `resolve.py`'s own docstring for `_deciding_sub_match` (R1e-era, lines 533-537) already states this explicitly: *"hook.py's deny/ask logging (`_log_non_allow_decision`) still classifies reason via `compound.fallback_kind_for_reason` before choosing the placeholder -- that remains a RENDERING choice ... not a data-correctness workaround this function's callers still need."* My execution run corroborates that claim rather than contradicting it: single-leaf `undecidable_fallback=deny`, compound `ls && python -c ...` under the same setting, and -- the adversarial case -- a two-leaf compound with one genuine-rule deny and one escape-hatch deny, tried in **both** leaf orders, all agreed between prose and structural classification.

**Bottom line for step 3:** this sanction is not merely inherited without re-examination -- it was reasoned about once already (at R1e) and I re-verified that reasoning by execution rather than accepting it on citation. Site 1 has a real, measured cost (20 test closures) blocking removal; site 2 has essentially none (it's a read of already-public, already-populated data) and would be a small, low-risk follow-up if a future ticket wants to close the R3 exclusion list to zero -- but doing so is not urgent, since nothing is being lost or corrupted today at either site.

## Files changed

- `toolguard/permission_resolution.py` -- `subject` parameter added to `_resolve_unclamped` and `resolve_permission_detailed` (additive, default-preserving).
- `toolguard/resolve.py` -- `resolve_file_path_permission_detailed` passes `subject="Path"` and no longer parses its own output.
- `toolguard/compound.py` -- **not touched**, per the task instruction; assessed only.

Original bytes of all three files backed up to `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/r3-backups/` (with a `SHA256SUMS.orig` manifest) before any edit, per the task's hard rule.

## Investigation scripts (scratch, not committed)

Three read-only scripts in the scratchpad directory above exercised the resolver functions directly (no git, no file writes): `investigate_r3_resolve.py` (step 1, the 5 no-match-fallback branches), `investigate_r3_compound.py` and `investigate_r3_compound2.py` (step 3, the 11-scenario prose-vs-structural comparison, including the adversarial two-leaf/both-orders case). Not added to the main test suite -- they're one-off investigation instruments, not regression tests, and they don't pin any new behaviour that isn't already covered by the existing suite/corpus.

## Self-review

- Full suite: 2,387 OK (matches the documented baseline exactly).
- Corpus: no differences (6,401 in-process + 61 e2e).
- `--guard`: PASS, 12 canaries against the live hook.
- `--predicates`: R3 PASS (site count 1 -> 0; the sanctioned exclusion is the only remaining entry).
- `ruff format .` / `ruff check --no-cache .`: clean, repo-wide.
- Diffed against the pre-edit backups (not against `git diff`, since the working tree already carries 14 stages of uncommitted TOO-45 work): the actual delta is exactly the two hunks in `resolve.py` and the parameter/docstring additions in `permission_resolution.py` shown above; `compound.py` diff against its backup is empty.
- Doc-drift sweep: grepped the whole repo for `_no_match_prefix` (only hits are historical implementation-report memory files describing past state, and my own explanatory comment referencing the old code by name -- both correct as written) and for the reason-text substrings in `docs/architecture.md` / `docs/install.md` (both already describe both the "Command..." and "Path..." phrasings, unchanged by this fix, so no drift).

## Time / cost estimate

- Planning + reading context (CLAUDE.md, memory, architecture_fitness.py, permission_resolution.py, resolve.py): ~20 min.
- Step 1 investigation (execution probe, 5 branches): ~10 min.
- Step 2 implementation + acceptance run: ~15 min.
- Step 3 investigation (two execution probes, tracing `_deciding_sub_match`/`_resolve_leaf_detailed`/`_combine_strictest`): ~25 min.
- Report writing: ~10 min.
- Total: ~80 min. Rough token-cost estimate at Sonnet rates for a session this size: low single-digit dollars (well under $5).
