---
title: TOO-45 resolution seam Protocols - implementation report
type: note
permalink: toolguard/too-45/reports/resolution-seam-protocols-report
tags:
- task-memory
- TOO-45
- report
---

## Summary

Made the hidden shape-dependency between `toolguard/permission_resolution.py` and `toolguard/resolve.py` explicit and statically checkable, using `typing.Protocol` defined in `toolguard/config_types.py`, per the task spec. Two Protocols were added: `ResolutionConfig` (the exact four-member config surface `permission_resolution.py` reads) and `DecideDetailed` (the per-level decision callback, now a callback Protocol with named, positional-only parameters instead of `Callable[[object, object, object], ...]`). Both live in `config_types.py`, which both `permission_resolution.py` and `resolve.py` already import, so no new import edge was created and no cycle was introduced (verified before and after with `tools/architecture_fitness.py --layers`).

## Files changed (7, all in scope)

- `toolguard/config_types.py` -- added `ResolutionConfig` and `DecideDetailed` Protocols (+207 lines, all additive; nothing existing removed).
- `toolguard/permission_resolution.py` -- removed the old `DecideDetailed = Callable[[object, object, object], Optional[LevelMatch]]` alias and its module-level comment; imports `DecideDetailed`/`ResolutionConfig` from `config_types` instead; typed `config` as `ResolutionConfig` on `_resolve_unclamped` and `resolve_permission_detailed`; updated the module docstring and a few `:data:` cross-references to `:class:`.
- `toolguard/resolve.py` -- typed the two `_decide_detailed` closures (inside `resolve_file_path_permission_detailed` and `resolve_bash_permission_detailed`) with concrete `Sequence[str]` parameter types and `Optional[LevelMatch]` return, so they present a real, checkable signature to the Protocol-typed `decide_detailed` parameter. Added a short docstring to each explaining that the closure's TYPE (not its body) is what satisfies the contract.
- `toolguard/config.py` -- fixed a pre-existing stale return-type annotation on `Configuration.permission_levels_with_provenance` (declared a 3-tuple `(allow, deny, layers)` per level; the method actually returns/documents a 4-tuple `(allow, deny, ask, layers)`). Pure annotation fix, zero behavior change. This was NOT optional: without it, the real `Configuration` class does not structurally satisfy `ResolutionConfig` (see verification below), which would have made the whole exercise decorative for the one type that actually matters.
- `test/unit/test_configuration.py`, `test/unit/test_logging_streams.py`, `test/unit/test_permission_resolution.py` -- added type annotations (`Sequence[str]` params, `Optional[LevelMatch]` return) to seven existing test-helper `decide_detailed` closures that are passed to `resolve_permission_detailed`/`resolve_bash_permission_detailed` in tests. This was a **necessary consequence**, not scope creep: once `decide_detailed` is Protocol-typed, pyright stopped treating these previously-untyped (`Unknown`-parameter) closures as automatically compatible, and flagged 18 new errors across the three files. Adding the same type hints the production closures already needed made all 18 disappear with zero behavior change (pure annotations on existing, already-passing tests).

No other files were touched. Total: 4 production files + 3 test files, well within the scope-inflation guardrail.

## The real `DecideDetailed` signature, and what I found

The task pointed at three names from the existing module-level comment in `permission_resolution.py` (`resolve._decide_detailed`, `resolve._decide_file_path_at_level_detailed`, `resolve._check_file_path_hard_deny`) as candidates. Reading every call site directly (not trusting the comment) showed the comment conflated two different claims:

- **"Returns `LevelMatch`"** is true of FOUR functions: `permissions.decide_command_at_level_detailed`, `permissions.check_hard_deny`, `resolve._decide_file_path_at_level_detailed`, `resolve._check_file_path_hard_deny`.
- **"Is actually wired in as the `decide_detailed` callback"** is true of only TWO, and neither of the four functions above directly -- it's the two identically-shaped, locally-defined `_decide_detailed` closures inside `resolve_file_path_permission_detailed` (resolve.py) and `resolve_bash_permission_detailed` (resolve.py). Both closures adapt their own tool's differently-shaped decision function (`_decide_file_path_at_level_detailed` / `decide_command_at_level_detailed` respectively -- 5-6 params each, `config`/`extended_syntax` closed over) down to the shared 3-arg shape. `check_hard_deny` and `_check_file_path_hard_deny` are called DIRECTLY, before and outside the cascade this callback drives, against a pooled hard-deny pattern set with a completely different parameter shape (command/path + bare deny/allow pair, no `ask`, no per-level scoping) -- they are not `decide_detailed` implementations at all.

The real, single, shared signature actually satisfied is:

```python
(allow_patterns: Sequence[str], deny_patterns: Sequence[str], ask_patterns: Sequence[str], /) -> Optional[LevelMatch]
```

Modelled as a callback `Protocol` with `__call__` (per the task's own suggestion) rather than a bare `Callable[[...], ...]` alias, specifically so the three same-typed, order-dependent parameters could be named. The trailing `/` (positional-only) was not optional decoration -- see the pyright verification below for why it was required.

## Naming

- `DecideDetailed` -- kept, per the task's own note that it's fine as-is.
- `ResolutionConfig` -- new. Ties directly to the module it serves (`permission_resolution`), says its role ("the config surface resolution needs"), and avoids a `-Like`/`-Protocol` suffix. Considered and rejected: `PermissionSource` (vague, `config.py` already deals broadly with permissions), `ConfigForResolution` (restates rather than names a role).

## Docstrings

Every Protocol and every member (including the `parse_failures` property) has a docstring stating why it exists as a deliberate shape contract across a no-import runtime seam, per the task's requirement 5. `ResolutionConfig`'s docstring also explicitly notes why `resolve.py`'s own (wider) `config` surface is NOT typed against this Protocol -- it would be too narrow and would break those call sites.

## Pyright verification (the actual checking, not assumed)

Ran `pyright -p pyrightconfig.check.json` (the repo's on-demand strict-ish config; `typeCheckingMode: basic`) throughout, both scoped to the touched files and whole-project, before and after every change.

**Positive proof it checks the DecideDetailed contract on the real, live call path** (not a scratch file): temporarily changed the Bash-side `_decide_detailed` closure's `allow_patterns` parameter from `Sequence[str]` to `Sequence[int]` in `resolve.py`, ran pyright, and got exactly the expected error at the real call site:

```
resolve.py:753:64 - error: Argument of type "(allow_patterns: Sequence[int], ...) -> (LevelMatch | None)" cannot be assigned to parameter "decide_detailed" of type "DecideDetailed" in function "resolve_permission_detailed"
  Parameter 1: type "Sequence[str]" is incompatible with type "Sequence[int]" ...
```

Reverted immediately after confirming; re-ran pyright to confirm the file returned to its exact pre-breakage error count (2, both pre-existing and unrelated).

**Positive proof it checks the `ResolutionConfig` contract**, via a throwaway scratch file (since `resolve.py`'s own `config` parameters are deliberately untyped -- see below -- so the real production call path does NOT itself get checked against this Protocol): a class deliberately missing `has_any_rules` was rejected --

```
error: "MissingHasAnyRules" is incompatible with protocol "ResolutionConfig"
  "has_any_rules" is not present
```

-- and a class implementing all four members passed with zero errors. Both scratch files were deleted immediately after (never committed; `git status` confirms clean).

**Positive proof the real `Configuration` class satisfies `ResolutionConfig`** (the case that actually matters): before the `config.py` annotation fix, `Configuration` failed conformance for two independent reasons, both real and both fixed:
1. The stale 3-tuple return-type annotation (see Files changed above).
2. `parse_failures` declared as a plain attribute in the Protocol, but `Configuration` is `@dataclass(frozen=True)`, so pyright treats the field as read-only; a plain (read-write) Protocol attribute does not structurally match a read-only one. Fixed by declaring `ResolutionConfig.parse_failures` as a read-only `@property` instead -- documented inline as the reason, since it's a non-obvious pyright rule worth pinning.

After both fixes, `Configuration` satisfies `ResolutionConfig` with zero errors.

**An important negative/caveat, stated plainly per the task's instruction**: `resolve.py`'s own `config` parameters (in `resolve_file_path_permission_detailed`, `resolve_bash_permission_detailed`, etc.) remain untyped -- deliberately, since that module's own `config` surface is wider than `ResolutionConfig` and typing it against this narrower Protocol would be wrong, and typing it against the full `Configuration` class would create a new import edge into a module this task was explicitly told not to restructure. This means the REAL, live call from `resolve.py` into `resolve_permission_detailed` is NOT itself pyright-checked against `ResolutionConfig` today -- pyright treats the untyped `config` argument there as compatible with anything. The Protocol is real and does check (proven above, both via the scratch file and via the `DecideDetailed` live-call-site test), but its enforcement on the actual production call graph is currently only as strong as the caller's own typing, which for `config` (not for `decide_detailed`, which IS checked live) is a pre-existing gap this task did not create and was told not to close (closing it is exactly the "restructure the cycle" work explicitly out of scope). Flagging this rather than overclaiming: the shape is now documented and pyright-checkable, and one half of it (the callback) is actively checked on every real call; the other half (config) is checkable but not yet wired to a typed caller.

## Discarded/considered and rejected

- Typing `resolve.py`'s own `config` parameters against `ResolutionConfig`: would be structurally wrong (too narrow -- `resolve.py` also calls `resolve_config_path`, `resolved_undecidable_fallback`, `hard_deny`, `hard_deny_entries`, etc., none of which `ResolutionConfig` declares).
- Typing them against `Configuration` directly: would add a new import edge from `resolve.py` (engine layer) to `config.py` (config layer) purely for typing purposes -- explicitly not requested and adjacent to the "do not restructure the cycle" constraint.
- Tightening `apply_parse_failure_floor`/`_apply_ask_floor`/`_parse_failure_reason`'s existing `Tuple[Tuple[object, str], ...]` parameter types to `Tuple[Tuple[Path, str], ...]`: left alone, out of scope (not named in the task, and `Tuple` is covariant so the existing looser type already accepts `ResolutionConfig.parse_failures` with no error).

## No new tests added

Per the task's own guidance ("add tests only if they assert something real"): considered adding a unit test asserting a class missing a `ResolutionConfig` member fails at runtime -- rejected, because Protocols without `@runtime_checkable` cannot be `isinstance`-checked, and a runtime test would only re-state the Protocol's own shape (exactly the "noise" test the task warned against). The real assertion here is static (pyright), demonstrated and recorded above via the scratch-file verification rather than a permanent test. `runtime_checkable` was considered and rejected: it would add an `isinstance`-checkable behavior nobody in this codebase needs (the whole call path is compile-time/duck-typed, never runtime `isinstance`-gated), for a feature whose only cost-free benefit here would be enabling a test that duplicates what pyright already proves.

## Verification results

- `uv run python tools/architecture_fitness.py --layers`: clean before and after (no new module, no cross-layer direction violation; `config_types` was already a leaf both sides import).
- `uv run python tools/architecture_fitness.py --predicates`: R1/R2/R3/R5/R6 all PASS, both before and after, unchanged.
- `uv run python tools/corpus_build.py --verify`: OK, no differences. 6,401 in-process + 61 end-to-end cases, matching the ticket's expected counts exactly.
- `uv run python -m unittest discover -s test -t .`: 2,587 tests (one more than the ticket's stated 2,586 -- see the concurrency note below; not from this change). 2,586 pass; the 1 error is `test_logging_streams.TestDiscoveryDiagnostic.test_oversized_file_no_longer_degrades_to_permanent_append_mode`, independently re-run in isolation and confirmed as `OSError: [Errno 28] No space left on device` writing its padding fixture -- a genuine, live disk-space exhaustion on the shared `/tmp` tmpfs (confirmed shrinking in real time during this session, unrelated to any file this task touched). See the environment note below.
- `pyright -p pyrightconfig.check.json` on all 7 touched files: zero new errors introduced; two pre-existing errors incidentally FIXED (the `config.py` 3-tuple/4-tuple mismatch, and a cascading destructuring error it caused in `test_configuration.py`). File-scoped before/after counts: `permission_resolution.py` 0->0, `config_types.py` 0->0, `resolve.py` 2->2 (unrelated, pre-existing), `config.py` 10->9, `test_configuration.py` 9->8, `test_logging_streams.py` 11->11, `test_permission_resolution.py` 1->1. Total 33->31.
- `uv run ruff format` / `uv run ruff check` on all 7 files: clean.
- `uv run python -m py_compile` on all 7 files: clean.

## Environment note -- flagging for Arnon, not something I could or should fix unilaterally

Two things converged during this session that are worth knowing about, both external to this task's own correctness:

1. **`/tmp` (the shared tmpfs, 16G) was at or near 100% full for most of this session**, and was observed actively shrinking in real time (confirmed via two `df -h` calls 3 seconds apart). This caused one spurious test failure (disk-space exhaustion, not a code defect) and several Bash tool-output failures on my end (worked around by redirecting large command output to `~/toolguard-coder-scratch/` on the ext4 root filesystem instead of the default tmpfs scratchpad). I did not delete anything under `/tmp` -- it contains files from what looks like other/earlier sessions, not mine, and deleting shared scratch state without knowing who else depends on it seemed like the wrong call to make unilaterally.
2. **Another agent/session was concurrently modifying this same working tree during my run**: `test/unit/test_verdict_corpus.py`, `test/verdict_corpus/fixture_loader.py`, `test/verdict_corpus/README.md`, `test/verdict_corpus/goldens.jsonl`, `tools/corpus_build.py`, and a basic-memory report file all changed under me without any action from me -- confirmed via `git status`/`git diff --stat` showing exactly those 6 files plus my own intentional 7, and via a basic-memory task-recall note titled "TOO-45 corpus sub-verdict extension" that appeared during my session. I did not touch, revert, or interact with any of those files. This is worth knowing about regardless of my own task, since two agents editing one working tree without coordination is a real risk to both efforts.

Neither issue reflects a defect in this task's implementation; both are reported here because the task's own constraints ("full suite must stay green") could not be independently, cleanly re-verified with 100% certainty against a completely static baseline while this was happening. The isolated, disk-independent checks (pyright, architecture fitness, corpus verify, ruff, py_compile) are all clean and are not affected by either issue.

## Timing and estimated cost

- Phase 1 (planning, investigation, reading code/task): ~25 min.
- Phase 2 (implementation, including the pyright verification round-trips and the follow-on test-file fixes): ~70 min.
- Phase 3 (self-review, full verification suite, environment troubleshooting): ~25 min.
- Phase 4 (report writing, this note): ~10 min.
- Total elapsed: ~130 min (over the ticket's own 30-minute soft guideline, driven mainly by the pyright verification loop -- which found two real, unrelated pre-existing bugs -- and the disk-space/concurrency troubleshooting, not by scope growth in the implementation itself).
- Estimated cost: Sonnet 5, roughly 130 min of tool-call-heavy work with substantial file reads (several large docstring-heavy files read in full) -- rough estimate $3-5 in API terms for a session this length and tool-call volume.


## Follow-up: enforcing the boundary at `resolve.py`'s own `config` parameters

The coordinator reviewed the above and correctly identified that `ResolutionConfig` was checked and correct, but not actually *enforced* on the real production call path: `resolve.py`'s own `config` parameters (on `resolve_file_path_permission_detailed` and `resolve_bash_permission_detailed`) were still bare/untyped, so pyright performed no check where `resolve.py` calls into `resolve_permission_detailed`. `DecideDetailed` did not have this gap (its argument, the `_decide_detailed` closures, are fully typed at the point they're defined and passed).

### Fix: `ResolveConfig`, a Protocol that inherits `ResolutionConfig`

Added `ResolveConfig(ResolutionConfig, Protocol)` to `config_types.py`, adding exactly the members `resolve.py` itself reads from `config` (found by grepping every `config.` use in `resolve.py`, not guessed):

- `resolve_config_path(raw_path: str) -> str` -- file-path pattern anchoring (`_anchor_file_pattern`).
- `hard_deny(tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]` -- the file-path hard-deny pool (`_check_file_path_hard_deny`); the Bash side receives its pool as plain arguments from ITS OWN caller, not via `config.hard_deny()` inside `resolve.py`.
- `hard_deny_entries(tool_name: str) -> Tuple[Tuple[RuleEntry, ...], Tuple[RuleEntry, ...]]` -- hard-deny `additionalContext` lookup (`_hard_deny_additional_context`), used by both tool families.
- `resolved_undecidable_fallback() -> str` -- the undecidable-segment floor in `resolve_bash_permission_detailed`.

`parse_failures` (used directly at `resolve.py`'s own ask-floor re-application for undecidable segments) is already inherited from `ResolutionConfig`, not re-declared.

Inheriting rather than restating the original four means structural subtyping does the rest: a `ResolveConfig` is automatically valid wherever `ResolutionConfig` is expected, so `resolve_permission_detailed(config, ...)` called from inside a `ResolveConfig`-typed function is now checked for real.

Then typed `resolve_file_path_permission_detailed` and `resolve_bash_permission_detailed`'s `config` parameters as `ResolveConfig` (imported from `config_types`, so still zero new import edges -- both modules already import that module).

### Verification (same method, at the boundary that was missing it)

**Live-call-site breakage, exactly where the coordinator pointed**: temporarily changed `class ResolveConfig(ResolutionConfig, Protocol):` to `class ResolveConfig(Protocol):` (dropping the inheritance, keeping the same four extra members). Ran pyright on `resolve.py` and got errors at BOTH real call sites, not just the one named:

```
resolve.py:491:9 - error: Argument of type "ResolveConfig" cannot be assigned to parameter "config" of type "ResolutionConfig" in function "resolve_permission_detailed"
  "ResolveConfig" is incompatible with protocol "ResolutionConfig"
    "parse_failures" is not present
    "permission_levels_with_provenance" is not present
    "has_any_rules" is not present
    "resolved_no_match_fallback" is not present

resolve.py:766:48 - error: Argument of type "ResolveConfig" cannot be assigned to parameter "config" of type "ResolutionConfig" in function "resolve_permission_detailed"
  (same four members missing)

resolve.py:860:16 - error: Cannot access attribute "parse_failures" for class "ResolveConfig"
  Attribute "parse_failures" is unknown
```

Line 491 is the file-path resolver's call into `resolve_permission_detailed`; line 766 is the Bash resolver's (the exact line the coordinator cited, `:756`, before my own edits shifted it by 10 lines); line 860 is `resolve.py`'s own direct `config.parse_failures` read for the undecidable-segment ask floor -- a bonus confirmation that the check propagates through the whole function body, not just the one call argument. Reverted the inheritance immediately after confirming; pyright returned to exactly the same 2 pre-existing, unrelated errors (`ConflictOverride` list-invariance, untouched by any of this work).

**Real `Configuration` conformance**, via a throwaway scratch file (deleted immediately after, `git status` confirms clean): `Configuration` passed as `ResolveConfig` with zero errors; a deliberately incomplete class (missing only `resolved_undecidable_fallback`) was correctly rejected, naming exactly that one missing member.

### Fallout

None in production code. `hook.py`/`api.py` (the actual callers of `resolve_bash_permission_detailed`/`resolve_file_path_permission_detailed`, neither touched by this task) showed zero new errors -- their own `config` arguments are apparently untyped at those call sites too, so this is as far as static enforcement currently reaches without also touching those files, which was not requested and would be a larger, separate change. No test-helper fallout this round (the closures affected earlier were `decide_detailed`, not `config`, and no test constructs a bare object in place of a real `Configuration` for these two entry points).

### Final verification (this round)

- `uv run python tools/architecture_fitness.py --layers` / `--predicates`: clean, R1/R2/R3/R5/R6 PASS, unchanged.
- `uv run python tools/corpus_build.py --verify`: OK, no differences, 6,401 + 61 cases (same counts).
- `uv run python -m unittest discover -s test -t .`: 2,587 tests, OK (the disk-space and concurrency issues flagged in the first pass had both resolved by this point -- `/tmp` had 11G free on the final run, and the concurrent agent's corpus-extension work did not conflict).
- `pyright -p pyrightconfig.check.json` on all 7 touched files plus `hook.py`/`api.py`: zero new errors anywhere.
- `uv run ruff format` / `uv run ruff check` / `py_compile`: clean on all 7 files.

Total files touched remains 7 -- no new files added in this follow-up, only further edits to `config_types.py` and `resolve.py`.
