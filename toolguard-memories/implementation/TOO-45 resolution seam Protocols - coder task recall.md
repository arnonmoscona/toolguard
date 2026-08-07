---
title: TOO-45 resolution seam Protocols - coder task recall
type: note
permalink: toolguard/implementation/too-45-resolution-seam-protocols-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-recall
---

# Task

Make the hidden shape-dependency between `toolguard/permission_resolution.py` and `toolguard/resolve.py` explicit and statically checkable, using `typing.Protocol`, defined in `toolguard/config_types.py` (both modules already import it -- no new import edge, no cycle).

## Requirements (verbatim intent)

1. Define Protocols in `toolguard/config_types.py`. Verify no new import edge/cycle via `uv run python tools/architecture_fitness.py --layers` before and after.
2. A Protocol for the config shape `permission_resolution.py` actually uses -- minimal, real surface only (not a restatement of the whole `Configuration` class). Per the module docstring the 4-member surface is: `permission_levels_with_provenance(tool_name)`, `has_any_rules(tool_name)`, `resolved_no_match_fallback()`, `parse_failures` (attribute).
3. Replace `DecideDetailed`'s `Callable[[object, object, object], Optional[LevelMatch]]` with real parameter types, determined from actual call sites (not just the docstring's four named functions -- verify which of those four are ACTUALLY wired as the `decide_detailed` callback vs called directly with a different shape). If they don't share one signature, model honestly -- Protocol with `__call__` if params have meaning worth naming.
4. Name for intent, tersely. `DecideDetailed` is fine as-is. Config protocol name should say its ROLE, not restate its type. Avoid `-Like` suffix if a meaningful name exists.
5. Docstring on every Protocol/method explaining WHY it exists (deliberate shape contract across a runtime seam with no import).

## Constraints

- Behaviour must not change. Golden corpus: `uv run python tools/corpus_build.py --verify` (6,401 in-process + 61 e2e).
- Full suite green: `uv run python -m unittest discover -s test -t .` (2,586 tests currently).
- `uv run python tools/architecture_fitness.py --layers` and `--predicates` clean (R1/R2/R3/R5/R6 PASS).
- Do NOT restructure the cycle itself (separate future work).
- Tests: add only if they assert something real (not shape restatement).
- Verify pyright ACTUALLY checks the Protocol -- deliberately break a call site, observe the error, revert. Report exactly what happened. If pyright doesn't check it as expected, say so plainly.

## Report location

`toolguard-memories/TOO-45/reports/resolution-seam-protocols-report.md`, frontmatter:
```
---
title: TOO-45 resolution seam Protocols - implementation report
type: note
permalink: toolguard/too-45/reports/resolution-seam-protocols-report
tags:
- task-memory
- TOO-45
- report
---
```
Never hard-wrap paragraphs in that report.

## Investigation findings (before coding)

- `permission_resolution.py` module docstring already names the 4-member config surface exactly as above -- that's authoritative for the Protocol's minimal surface.
- Config's `permission_levels_with_provenance` (config.py:1368) has a PRE-EXISTING stale return-type annotation: declares a 3-tuple `(allow, deny, layers)` per level but actually returns/documents a 4-tuple `(allow, deny, ask, layers)`. Pyright ALREADY flags this today (baseline `pyright -p pyrightconfig.check.json`, 12 errors total, includes this one at config.py:1408, reportReturnType "expected 3 but received 4"). This is a real pre-existing bug, independent of this task, but it DIRECTLY blocks Protocol conformance: if the new Protocol declares the (correct) 4-tuple, `Configuration` won't structurally satisfy it while its own declared return type is the wrong 3-tuple. Plan: fix ONLY this one type annotation (config.py:1368-1372) to state the true 4-tuple shape -- pure annotation fix, zero runtime/behavior change, and it removes one of the 12 pre-existing pyright errors rather than adding one. Will call this out explicitly to Arnon as an in-scope-adjacent fix, not scope creep, since it's required for the Protocol to be meaningfully checkable against the real Configuration class.
- `resolved_no_match_fallback` also has a pre-existing pyright error (declares `-> str`, body has a `str | None` return path) -- but this does NOT block Protocol conformance because Protocol structural checks compare DECLARED signatures, and the declared return is already `str`. Leaving this alone (unrelated, not required for our fix).
- The `DecideDetailed` callback: actual wiring is via TWO closures, both locally named `_decide_detailed`, one in `resolve_file_path_permission_detailed` (resolve.py:456-464) and one in the Bash sub-command resolver (resolve.py:722-729). BOTH have identical real signature: `(allow_patterns: Sequence[str], deny_patterns: Sequence[str], ask_patterns: Sequence[str]) -> Optional[LevelMatch]` (called as `decide_detailed(allow, deny, ask)` from permission_resolution.py, where allow/deny/ask are `Tuple[str, ...]` from `config.permission_levels_with_provenance`).
- `_decide_file_path_at_level_detailed` and `_check_file_path_hard_deny` (also named in the existing `DecideDetailed` comment, alongside `permissions.decide_command_at_level_detailed`/`permissions.check_hard_deny`) do NOT share this signature and are NOT passed as the `decide_detailed` callback at all -- `_check_file_path_hard_deny`/`check_hard_deny` are called DIRECTLY, outside/before the cascade, with a completely different parameter shape (command/file_path + deny/allow patterns, no `ask`). `_decide_file_path_at_level_detailed`/`decide_command_at_level_detailed` are called FROM INSIDE the two `_decide_detailed` closures, which adapt their differently-shaped params into the shared 3-arg contract. The existing module-level comment conflates "returns LevelMatch" (true of all 4) with "satisfies the decide_detailed callback contract" (true of only the 2 closures) -- plan to correct this in the new docstring.
- No existing Protocol usage precedent in the codebase to match style against -- checked, none found yet (will grep before writing).