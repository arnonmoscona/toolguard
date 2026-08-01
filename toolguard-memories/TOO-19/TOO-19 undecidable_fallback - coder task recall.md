---
title: TOO-19 undecidable_fallback - coder task recall
type: note
permalink: toolguard/too-19/too-19-undecidable-fallback-coder-task-recall
---

## Task
New late-added requirement (Arnon added after Phase 1 landed): a configurable `undecidable_fallback`, mirroring the existing `no_match_fallback`.

Repo: /home/arnon/projects/toolguard, branch too-19. Ticket TOO-19.

## Motivating rationale
`no_match_fallback` answers "I read this command and no rule covered it."
`undecidable_fallback` answers "I could not safely read this command at all."
Independent controls. TOO-28 will add auto-mode variants of both; this is the base pair.

## Scope: CONFIG LAYER + THREADING only
Follow-up task adds security-audit finding and docs. Do NOT write docs or touch `toolguard/tools/danger.py`.

### 1. toolguard/config.py - the setting
Mirror `no_match_fallback` (study `_VALID_NO_MATCH_FALLBACKS` ~line 92-98, `resolved_no_match_fallback` ~line 1675, `takeover_mode()` parse ~line 995) with DELIBERATE differences:
- `_VALID_UNDECIDABLE_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning"})`, `_DEFAULT_UNDECIDABLE_FALLBACK = "ask"`.
- TOP-LEVEL KEY ONLY. No legacy `[takeover_mode]` alias, no field on TakeoverConfig. Docstring must say so explicitly so nobody "restores symmetry" later.
- No `warn_deny` alias (that's only for no_match_fallback's history).
- Add `Configuration.resolved_undecidable_fallback()`: more-specific-wins across non-native layers, ignore native settings entirely, unset/unrecognized -> "ask", never propagated as-is.
- Applies in both takeover and non-takeover modes.

### 2. Floor semantics
`undecidable_fallback` is a FLOOR LEVEL, resolved STRICTEST-WINS against leaf's resolved verdict. Strictness: deny > ask > allow.

| leaf | fallback=ask | fallback=deny | fallback=allow_with_warning |
|---|---|---|---|
| deny | deny | deny | deny |
| ask | ask | deny | ask |
| allow | ask | deny | allow + warning reason |

Floor can only make verdict STRICTER than allow; never weakens explicit deny/ask. allow_with_warning = "no floor at all" escape hatch. Implement as one small well-named tested pure helper, not inline conditionals.

### 3. Exactly two call sites, both in toolguard/compound.py
- `_resolve_leaf`'s `leaf.ask_floor` branch (~line 94): foreign inline code/heredoc sinks. Currently hardcodes clamp to "ask".
- `resolve_compound_permission`'s `UndecidableSegment` branch (~line 400+): control structures, process substitution. Currently hardcodes "ask". NEVER resolved against any rule - no underlying decision, takes fallback value directly (no strictest-wins needed).

compound.py is config-free (takes resolve_one callable) - thread value as explicit param `undecidable_fallback: str = "ask"` on `_resolve_leaf`, `resolve_compound_permission`, `check_compound_permission`. Default "ask" keeps existing callers/tests valid.

`toolguard/resolve.py::resolve_bash_permission_detailed` sources it from `config.resolved_undecidable_fallback()`, passes down.

Non-ask outcome reason string must say why (undecidable_fallback, not a rule). Keep existing reason format for default ask case (no churn to existing tests).

### 4. HARD INVARIANT - parse-failure floor exempt, PERMANENTLY
`config.py::_apply_parse_failure_ask_floor` must be COMPLETELY UNAFFECTED by this setting. Arnon: "parse failure must always be a noisy, naggy, uncomfortable, heavy friction behavior. Clean TOML required for any configuration to be trusted." Parse failure = toolguard doesn't know what its rules ARE, no basis for any verdict.

Explicit test: undecidable_fallback = "allow_with_warning" AND broken config file present -> decision still clamped to ask. Name test unmistakably. Comment at exemption site explaining why no flag may ever relax it.

## Tests (test/unit/, find right files, verify don't guess - likely test_configuration.py, test_compound.py, test_resolve.py)
- three valid values parse/resolve; unrecognized/unset -> ask
- native layer value ignored
- more-specific-wins across levels
- full strictest-wins matrix (every cell, 3x3=9 or so)
- heredoc/inline-code leaf under each of 3 settings, end to end
- UndecidableSegment (for loop or process substitution) under each of 3 settings
- parse-failure exemption
- no_match_fallback and undecidable_fallback are INDEPENDENT - set one deny, other allow_with_warning, assert each governs only its own case

Tests touching config discovery MUST use ConfigIsolationMixin per .claude/rules/test-config-isolation.md.

## Verification before reporting
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` must report OK. Baseline 1949 tests passing. Empty-HOME form required.
- `uv run ruff check .` clean; `uv run ruff format` ONLY on touched files (5 pre-existing unformatted files - don't touch).
- Sandbox sanity check under each setting: `uv run python -m toolguard.testing.sandbox --config <file> --command "python -c 'import os'"`. Report observations.
- Duplication/drift self-check: does floor helper duplicate `compound.py::_combine_strictest` (already ranks deny>ask>allow)? Consider reuse vs coupling concerns. Report reasoning.

## Report
Write to basic-memory project `toolguard`, path `TOO-19/TOO-19 undecidable_fallback - config and threading implementation report.md`, tagged task-memory and TOO-19. Include: floor-helper design + _combine_strictest reuse decision, sandbox observations, every call site touched, anything judged out of scope.

## Constraints from CLAUDE.md
- stdlib-only runtime
- unittest not pytest
- BDD Given/When/Then docstrings on every test
- NO function-level imports (hook.py has ONE sanctioned documented circular-import exception)
- docstring on every function/class
- Never bare python/python3 - always uv run python
- Never edit file outside repo
- Do not commit or run write git operations
