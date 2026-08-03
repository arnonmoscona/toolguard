---
title: TOO-19 deny-side rule fabrication fix - coder task recall
type: note
permalink: toolguard/too-19/too-19-deny-side-rule-fabrication-fix-coder-task-recall
tags:
- task-memory
- TOO-19
---

## Task

Repo: /home/arnon/projects/toolguard, branch too-19. One focused fix (feature-coder delegation).

**Defect**: `toolguard/hook.py::_log_non_allow_decision` recovers the violated rule for a deny
via a blind `reason.split(": ", 1)[1]`. When the decision came from the undecidable floor
(`undecidable_fallback = "deny"`) rather than a matched rule, the right-hand side is the
truncated *display command*, not a rule -- the audit log records a rule that exists nowhere in
config. This is the deny-side counterpart of the allow-side fabrication bug fixed earlier
today (TOO-19 m5), which introduced `fallback_kind_for_reason` (public, `compound.py`) and
`FALLBACK_ALLOW_PLACEHOLDER`.

**Repro shape**: config with ONLY `Bash(ls)` and `Bash(python *)` allow, `undecidable_fallback
= "deny"`, command `python -c "print(1)"`. Expect `- **Violated Rules**: \`python -c\`` with no
such rule configured.

## Required fix

- "An absent record beats a false one" -- same principle as allow side, not a second
  convention.
- `fallback_kind_for_reason` as written keys on allow markers and returns None for any
  non-allow decision -- must extend it (or add a deny counterpart) to also classify a deny
  produced by `undecidable_fallback=deny`. Ticket instructs: pick ONE mechanism, justify.
- Check whether ask-side has the same defect; fix in same pass if so, else say why not.
- Do NOT widen `resolve_one`'s 3-tuple contract (prior judgement holds, ~18 test closures
  depend on it).

## My analysis before coding (read source first)

- `_log_non_allow_decision` (hook.py ~818-865): `ask` branch passes `reason` whole as `note`
  (no split) -- NOT fabrication-prone; ask side unaffected, no fix needed there.
- `deny` branch: `violated_rules = [reason.split(": ", 1)[1] if ": " in reason else reason]` --
  this is the ONLY blind-split site for deny. Confirmed via `_combine_strictest`
  (compound.py ~663-716): the deny branch always forwards the FIRST denied leaf's raw reason
  verbatim (no reformatting/summary-building step like the multi-allow "cmd -> pattern"
  summary that needed its OWN fix on the allow side) -- so unlike allow, deny needs only ONE
  fix site (hook.py), not two (hook.py + compound.py's `_combine_strictest`).
- Two deny reason shapes carry the marker `"undecidable_fallback=deny"` and both end in
  `": <display>"`:
  1. `_resolve_leaf_detailed`'s ask-floor branch (compound.py ~302-309):
     `"Denied by undecidable_fallback=deny (inline/heredoc foreign code, unable to safely
     verify): {display_cmd}"`
  2. `resolve_compound_permission_detailed`'s UndecidableSegment branch (compound.py ~868-872):
     `f"Undecidable segment denied by undecidable_fallback=deny ({element.reason}): {display}"`
  Single substring marker `"undecidable_fallback=deny"` catches both.
- `no_match_fallback=deny`'s reason (`config.py` ~1774-1776, `"Command does not match any
  allow patterns"`) has NO colon at all -- already safe (falls to the `else: reason` branch),
  no marker needed for it.
- File-path tools (Read/Write/Edit) have no `undecidable_fallback` concept (no bash grammar) --
  their deny reasons are either a genuine rule match (real colon+pattern) or the no-colon
  no-match default. Not affected; not in scope.

## Plan

1. `compound.py`: add `FALLBACK_DENY_PLACEHOLDER` constant next to `FALLBACK_ALLOW_PLACEHOLDER`.
   Extend `_FALLBACK_REASON_MARKERS` with `("undecidable_fallback=deny", "denied")`. Broaden
   `fallback_kind_for_reason`'s decision gate from `!= "allow"` to `not in ("allow", "deny")`
   so it classifies both sides through the SAME marker table -- ONE mechanism. Verified this
   doesn't change behavior at existing call sites (compound.py sub-command loop line ~348,
   hook.py's `_matched_rule_for_single_command`) since `resolve_one()` never produces
   `undecidable_fallback=deny` text (only compound.py itself constructs it) and no allow-side
   marker text can appear in a deny reason or vice versa.
2. `hook.py`: add a shared private helper (e.g. `_reason_suffix_or_placeholder(decision,
   reason, placeholder)`) wrapping `fallback_kind_for_reason` + the colon-split, used by BOTH
   `_matched_rule_for_single_command` (allow, existing) and the new deny-side extraction in
   `_log_non_allow_decision` -- keeps ONE extraction mechanism at the hook.py layer too, not
   two copies of the same split-guard logic. Import `FALLBACK_DENY_PLACEHOLDER`.
   Preserve exact prior behavior for the "no colon at all" case: deny falls back to the FULL
   reason (not None) -- helper returns None in that case, caller substitutes `reason`.

## Tests to add (test/unit/, new tests only, no existing test touched)

Mirror `TestAuditLogMatchedRuleNeverFabricated` in `test_resolve.py` (allow-side m5 tests) --
same hand-constructed-Configuration style (no ConfigIsolationMixin needed, zero file I/O).
Cover:
- Single-leaf ask-floor deny under `undecidable_fallback=deny` -> placeholder, not `python -c`.
- UndecidableSegment deny under `undecidable_fallback=deny` (if easy to construct) -> placeholder.
- A genuine deny (real deny pattern match) still records its real pattern (regression guard).
- ask-side: confirm (documentation-style test or explicit check) that ask still logs full
  reason text as note, unaffected.

## Verification checklist (from spec)

- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python -m
  unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -- baseline 2169, must go UP.
- `uv run ruff check .` and `uv run ruff format --check .` clean repo-wide.
- `uv run python tools/check_doc_links.py` exits 0.
- Before/after repro pasted in report.
- Real repo `logs/` untouched -- bracket suite run with entry counts.

## Report destination

basic-memory project `toolguard`, path `TOO-19/TOO-19 deny-side rule fabrication fix.md`,
tagged `task-memory` and `TOO-19`.
