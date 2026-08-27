---
title: The canonical protection set denies writing your SSH and AWS credentials but
  not editing them
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/63-the-canonical-protection-set-covers-write-but-not-edit
---

**FIXED in `05f786d` (TOO-45 phase 2).** The canonical protection set now covers Edit as well as Write; a probe confirms all 11 named credential paths deny on Read/Write/Edit — see `toolguard/tools/recommended_protections.py:40`, with a documentation-sync caveat noted in the audit's Surprises section.

# `Edit` slips past the recommended hard-deny set

**Found 2026-08-13. Two RED tests in the tree, three subtests. Both gaps measured through the real engine, not inferred from the pattern list.**

## Gap 1 — `Edit` is denied only for `.env`

The canonical set hard-denies **`Write`** of `~/.ssh/authorized_keys` and `~/.aws/credentials`. It covers **`Edit`** only for `.env`.

So **appending a key to `~/.ssh/authorized_keys` via `Edit` passes the hard-deny pool.** The file the set exists to protect is protected against one tool and not the other.

## Gap 2 — `.env` variants are read-protected but not write-protected

**Reads** of `.env.*` are denied. **Writes** are denied only for the exact name `.env` — so **`Write ~/.env.local` passes.**

The entry's own rationale says it *"prevents a command from silently planting or altering secrets."* Planting a secret in `.env.local` is exactly that, and it is allowed.

## Fix

Patterns added to `recommended_protections.py`, `_EXPECTED_PATTERNS` and `docs/security.md` **in one reviewed change** — the three are meant to be a single source of truth and are now tested as one. A design call rather than an obvious repair, and easily reverted.

**Deliberately NOT pinned as characterization.** Recording "`Edit ~/.ssh/**` is not denied" as expected behaviour would enshrine an undesirable value. RED instead.

## The set had ZERO behavioural coverage

**Nothing anywhere executed these 16 patterns.** Every assertion was structural — the tests could confirm the table *lists* `Read(~/.ssh/**)` and could not confirm it *denies* `~/.ssh/id_rsa`. A list of strings that nothing runs is a list of strings.

Now each of the 16 has at least one probe driving `toolguard.api.decide` through the real engine and naming it as the **deciding** pattern, plus negative controls (`Write <project>/README.md` must still be allowed).

Also newly covered: **table ↔ `docs/security.md` agreement.** The module docstring, `seed-hard-deny`'s help text and the security doc all claim a single source of truth, and **nothing checked it.** The new test parses the doc's TOML block and requires the 16 patterns as one contiguous ordered run.

## A limitation worth knowing before applying shape 25's remedy elsewhere

**A file-path hard-deny discards which pattern denied.** `resolve_file_path_permission_detailed` sets `matched_rule=None` **by design**, for golden-corpus stability — so the deciding pattern survives only inside the prose `reason`.

That means **shape 25's one-line remedy (`assertIn(verdict.matched_rule, ...)`) does not work for file tools.** These tests call `check_file_path_hard_deny(...).matched_pattern` instead, which is the structured value.

It is also the "prose is output, not a data structure" pattern again: the fact exists, is discarded at the boundary, and survives only as text. Worth a ticket of its own if the golden corpus can be re-baselined.

## Two smaller findings

- **Ticket 37's second instance confirmed by reading**: `installer.py:1665-1682`'s `cmd_seed_hard_deny` prints `"already present, no changes needed:"` followed by **nothing** on an empty table. **The pinning test is the only thing standing between an empty table and that output** — the table still has no population guarantee.
- **Doc-vs-tool drift**: `docs/security.md`'s recommended block also lists four `Write(/etc/**)`-class system-directory patterns that `seed-hard-deny` does **not** seed, while the doc says it "adds exactly this canonical set."

## A correction to my own brief

I told the agent to check whether a test *iterates the list to check the list*. **It does not** — `_EXPECTED_PATTERNS`, an independent module-level 16-tuple, already existed at HEAD and every table mutant was caught by it. The suspicion was reasonable (it was true in `test_tools_installer.py`) but wrong here, and the agent said so rather than manufacturing a finding to match the brief.