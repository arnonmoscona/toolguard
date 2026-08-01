---
title: TOO-19 undecidable_fallback - audit finding and docs task recall
type: note
permalink: toolguard/too-19/too-19-undecidable-fallback-audit-finding-and-docs-task-recall
tags:
- task-memory
- TOO-19
---

## Task

Final piece of TOO-19 undecidable_fallback requirement: security-audit finding + documentation.
Repo: /home/arnon/projects/toolguard, branch too-19.

## Context: already landed (recap from prompt, verify against code)

- New top-level key in `toolguard_hook.toml` (NOT under `[takeover_mode]`, no legacy alias).
  Values: `ask` (default), `deny`, `allow_with_warning`. No `warn_deny` alias. Unset/unrecognized -> `ask`.
  Ignored in native `settings.json`. More-specific-wins across levels. Applies in takeover and non-takeover.
- Answers different question from `no_match_fallback`: "couldn't safely read this command at all"
  vs "read it, no rule covered it".
- Governs two Bash-only situations: ASK floor on foreign inline code/heredoc sinks
  (`compound.py::_resolve_leaf`, `leaf.ask_floor` branch), and `UndecidableSegment`
  (process substitution, case, control structures - `parser/multiline.py`).
- Names a FLOOR LEVEL, resolved strictest-wins (deny > ask > allow) against leaf's own resolution.
  `allow_with_warning` = no floor at all.
- Config-parse-failure ASK floor is exempt and overrides it - `resolve.py::resolve_bash_permission_detailed`
  re-applies `Configuration.apply_parse_failure_floor` at compound boundary.

## Task 1: security-audit finding (toolguard/tools/danger.py)

- Add finding: severity HIGH, id `loose-undecidable-fallback`, raised when undecidable_fallback
  resolves to allow_with_warning.
- Model after `loose-no-match-fallback` (severity LOW, source=takeover) - find where produced,
  follow structure (locus/tool/remediation, how findings reach markdown + JSON).
- Impact text: explain why HIGH not LOW - no_match_fallback=ask just means unmatched prompts
  (toolguard still parsed/understood). undecidable_fallback=allow_with_warning means executing
  commands toolguard COULD NOT PARSE AT ALL (foreign inline code, heredoc payloads, process
  substitution) with no rule ever evaluated. Cite compound.py's "when in doubt, ASK" principle.
- Remediation: set to ask (default) or deny.
- deny value: NO finding (strictly more conservative than default; state reasoning in report).
- Tests: extend file covering existing takeover-invariant findings (find - likely
  test_tools_danger.py or test_tools_security_audit.py). Cover: fires for allow_with_warning;
  not for ask/deny/unset; severity HIGH; appears in markdown + JSON.

## Task 2: documentation

- docs/configuration.md: new section beside "## No-match fallback". Lead with distinction
  between the two questions. Cover: three values, floor semantics w/ strictest-wins table,
  two situations governed, parse-failure exemption, top-level-key-only no [takeover_mode]
  alias, allow_with_warning raises HIGH audit finding. Add anchors to Contents list.
- docs/security.md: allow_with_warning is genuine loosening. What it turns off / what remains
  (explicit deny/ask rules, [hard_deny], parse-failure floor still apply). Concrete residual risk.
- docs/configuration.md reference section: add key if "Configuration reference" listing exists.
- docs/agent-map.md: update entries + TOC for every heading added (no other sync mechanism).
- Sweep README.md, AGENTS.md, llms.txt, technical-notes.md for staleness - esp anything saying
  undecidable/ASK-floor behaviour is fixed/hardcoded/not configurable.

### Style
- Plain ASCII. Single hyphens (not --) in HEADINGS only (anchor slugs don't collapse hyphen runs).
  Body text may use --.
- No human reads end to end - precise headings, short scannable sections, cross-links.

## Verification (all required)

- `uv run python tools/check_doc_links.py` - MUST exit 0.
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` - must report OK. Baseline 1993.
- `uv run ruff check .` clean; `uv run ruff format` only on touched files (5 pre-existing repo
  files unformatted, leave them).
- Demonstrate finding end-to-end: throwaway config in temp dir, undecidable_fallback =
  "allow_with_warning", run `uv run python -m toolguard.tools.security_audit --dir <tempdir>`.
  Paste output in report. Do NOT run against real repo config or --dir .

## Report

basic-memory project toolguard, path `TOO-19/TOO-19 undecidable_fallback - audit finding and docs report.md`,
tags task-memory + TOO-19. Include: deny-warrants-no-finding reasoning, end-to-end audit output,
every file/anchor changed, any stale doc found beyond listed sweep.

## Notes on repo state at start

Working tree has some pre-existing staged/modified files unrelated to this task (test_rule_entry.py,
various memory .md files added/deleted, rule_entry.py modified, __pycache__ untracked). Not touching
those unless directly relevant.
