---
title: latest-code-review-report
type: report
permalink: toolguard/too-15/latest-code-review-report
tags:
- TOO-15
- code-review
- P2
---

# Code Review Report -- TOO-15 P2 (S1-S4 loop)

Date: 2026-07-01. Scope (explicit file list): `edit_proposal.py`, `security_audit.py`,
`maintenance.py`, `config_access.py`, `danger.py`, `corpus.py`, `migration_gate.py`,
`working_tree.py`, `skills/toolguard-maintenance/SKILL.md`,
`skills/toolguard-security-audit/SKILL.md`.

Overall quality: **Good.** EditProposal / as-if-enacted audit pipeline is a sound design.
No critical security flaws introduced.

## Critical
None.

## Major
### M1 -- danger.py REGEX arbitrary-exec gap for node/ruby/perl -- **FIXED 2026-07-01**
`_is_arbitrary_exec` REGEX branch matched only literal `node `/`ruby `/`perl ` (trailing
space), so an anchored allow `[regex]^node:.*` produced NO finding, while the equivalent
DEFAULT pattern `node:*` was caught -- an asymmetric false-negative in our own security
detector (python was caught via bare `"python"`). Confirmed by reading
`_regex_body_matches_any` (literal substring check).
**Fix applied:** REGEX branch now uses bare interpreter tokens
(`python`/`node`/`ruby`/`perl`/`sh -c`/`bash -c`), symmetric with python; the redundant
`_regex_body_matches_any(...) or any(...)` double-check collapsed to one call (addresses
m2). `"exec"` deliberately EXCLUDED as a substring token (it appears in negative
lookaheads like `(?!.*exec)`; the DEFAULT branch checks it precisely). Regression tests
added: `test_regex_anchored_python_flagged`, `test_regex_anchored_node_ruby_perl_flagged`.
Suite 1155 green, ruff clean.

## Minor
- **m1 -- danger.py dead trailing-space entries in `_ARBITRARY_EXEC_PREFIXES`** --
  **FIXED** (removed `python `/`python3 `/`node `/`ruby `/`perl `; all covered by
  `_ARBITRARY_EXEC_BARE`; added explanatory comment).
- **m2 -- danger.py REGEX branch redundant double-check** -- **FIXED** as part of M1.
- **m3 -- corpus.py DRY** (OPEN, triage): `resolve_project_root(...)` root-resolution
  block copy-pasted in `resolve_logs_dir` (54-56) and `harvest_corpus` (94-95);
  `harvest_corpus` could call `resolve_logs_dir`.
- **m4 -- config_access/security_audit `AuditContext.takeover` duplicates
  `summary.takeover`** (OPEN, triage): both set from the same call; remove one or document.
- **m5 -- security_audit.py:309 tool-iteration inconsistency** (OPEN, triage): clarity
  findings iterate `sorted(GOVERNED_TOOLS)`, danger findings iterate
  `discover_tools(config)`; probably intentional -- add a comment.

## Suggestions (OPEN, triage)
- **S1 -- maintenance SKILL.md** uses `/tmp/tg-edits.json`; project convention prefers the
  scratchpad dir.
- **S2 -- edit_proposal `_provenance_from_dict`** `Path(data["path"])` raises `TypeError`
  on JSON null with no guard; CLI catches it but library callers of `rule_edit_from_dict`
  do not.
- **S3 -- working_tree.py:87** git porcelain v1 quotes paths with spaces; `dirty_paths`
  keeps the quotes verbatim (informational display only, not the safety decision).

## Disposition
M1 + m1 + m2 fixed and verified (regression tests, full suite 1155 OK, ruff clean).
m3-m5 and S1-S3 left for Arnon to triage (mostly cosmetic / defensive; none affect the
security decision).
