---
title: The security audit's clarity checks iterate BUILTIN_TOOLS, so a governed MCP
  tool is never examined or mentioned
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/56-security-audit-clarity-checks-skip-every-non-builtin-governed-tool
---

# A governed tool the audit does not audit

**Found 2026-08-13. Two RED tests are in the tree. This is queue row SA1, now reproduced by execution.**

## The defect

A **governed, hooked MCP tool** carrying the *identical* allow/deny overlap that produces a `deny-shadows-allow` finding for `Bash` produces **no finding — and no mention anywhere in the report.**

`find_confusing_interactions` returns the finding correctly. The aggregator's clarity loop then iterates **`BUILTIN_TOOLS`**, so the tool is never passed to it.

A control test proves the overlap itself is detectable, so this is the loop bound and nothing else. **One-expression fix**: iterate `discover_tools(config)` or `config.governed_tools()`.

## Why it matters more than a missing finding

The user's own configuration says the tool is governed. **The audit silently narrows its scope to a hardcoded list and reports clean.** There is no "not checked" line, no warning, no mention of the tool at all — so a reader cannot tell the difference between "your MCP tool's rules are fine" and "your MCP tool was never looked at."

That is ticket 29's family — a verdict with no account of what was examined — arriving in the tool whose entire purpose is to tell the user their configuration is safe.

## Status in the tree

- `test_tools_security_audit.TestClarityScope.test_a_governed_non_builtin_tool_gets_clarity_coverage`
- `..._is_named_somewhere_in_the_report`

Both RED, both asserting correct behaviour.

## What the module could not see before this pass

The numbers are worth recording because this analyzer's whole output is a report a human reads:

- **0 of 14 finding-body mutations were detected** — pattern, locus, summary, impact, remediation, structured fix, and the source/tool header, in **both** output formats; plus the severity tally line, the text-mode severity headings, the group ordering, and the ASCII fold. **Now 14 of 14.**
- **Severity ordering**: `delete_sort` 0 → 3 failures, `reverse_sort` 0 → 1, `constant_key` 0 → 3.
- Overall: ~39 surviving mutations → **2**.

## Two fixture defects that caused the blindness, both instructive

1. **`_clean_config()` contained ZERO permission rules** (`discover_tools() == ()`). So **all 11 "no findings" tests certified an audit that had been handed nothing to examine.** The fixture reproduced, inside the test suite, the exact defect the campaign keeps finding in production: a clean result that is indistinguishable from an empty one. It now carries three real safe rules, a population assertion, and a positive control.

2. **Two `ConfigLayer`s were built with an identical `Provenance`.** That produced a phantom duplicate which made the mixed fixture three CRITICALs and the ordering assertion vacuous.

   **CORRECTION 2026-08-13 — I wrote "equal provenances merge". That is wrong, and the truth is worse.** They do not merge. **The last layer wins outright and is then reported for *every* layer sharing the key**, so the earlier layer's rules are **lost entirely**. Measured: layers `('first:*',)` and `('second:*',)` in → `[('second:*',), ('second:*',)]` out.
   
   So the shape has two halves and **I recorded only the harmless one.** The duplicate is cosmetic; the **silent loss of a whole layer's rules** is the dangerous half — and in a security audit, losing a layer means its dangerous rules are never examined while the report still looks complete.

   **Not reachable through real discovery**, measured rather than assumed: with the sharpest candidate layout (project root == `$HOME`, `.local.toml` + `.toml` + `settings.json` + both rules dirs) there are **5 layers and 0 duplicate `Provenance` pairs**, because `_discover_levels` de-dupes level dirs by resolved path and `path` is a `Provenance` field. The damage is confined to **hand-built configs — tests and tooling.** A RED test now pins the correct positional pairing, and mutating toward the fix (zip by index) turns it green.

The second is a new consequence of a trap already recorded: `Provenance` equality collapses fixtures. Previously it was seen **flattening** a hierarchy; here it **duplicates** findings. Worth carrying to the traps list in that stronger form.

## Correctly NOT claimed here

The agent declined to add detection for two adjacent defects, on ownership grounds, and was right to:

- **Ticket 52** (`[[permissions]]` holding `Bash(*)` yields no blanket-allow finding) — the loss happens upstream in `config.py`; detecting it here would repeat shape 27's ownership trap, where a mechanism is "owned" by a module structurally incapable of catching it.
- **Ticket 41 / DG5** (`Bash(sudo rm -rf ~/.toolguard)` as an allow rule produces no danger finding) — owned by `test_tools_danger.py`.

## Still live and unfixed, same module

**SA3**: `render()` folds output to ASCII, `_render_edit_banner` does **not**, and `main` prints both — so a non-ASCII pattern appears folded in one section and raw in the other: `- resolved destructive-cmd-allow (HIGH) rm -rf /café/☃`.