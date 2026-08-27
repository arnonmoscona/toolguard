---
title: Four separate sites assume a parsed JSON document is a dict, and each fails
  differently
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/55-non-object-json-is-mishandled-at-four-separate-sites
---

**FIXED in `05f786d` (TOO-45 phase 2).** All four non-object-JSON sites are behaviourally fixed — see `toolguard/config_write_guard.py:125`, `toolguard/config_divergence.py:45`, `toolguard/session_start.py:65`, `toolguard/install_update.py:115` — though the single shared-boundary refactor the ticket proposed was declined.

# One assumption, four sites, four failure modes

**Consolidated 2026-08-13. Filed as one ticket because the fix is one decision, not four patches.**

Every site below assumes `json.loads(...)` returns a `dict`. **All four are measured, and each has a RED test except where noted.**

| # | site | what happens with a non-object document | red test |
|---|---|---|---|
| **40** | `config_write_guard.verify_config_text` | accepts `null`, `[]`, `3`, `"hello"` — so `verified_write_config(path, "null", "json")` **overwrites a real settings file and reports success**. The loader then rejects it, clamping every decision to `ask` | yes |
| **46** | `config_divergence` (`config.get(...)` outside the `try`) | `AttributeError` **on the live hook path** for a `settings.local.json` containing `[]` | yes |
| **50** | `session_start._parse_session_start_input` | returns the non-dict as-is, contradicting its own docstring; **stdout empty, `load_configuration` never called — the whole hook silently disabled** | yes |
| **NEW** | `install_update._read_direct_url_json` | annotated `Optional[dict]`, returns any JSON value; a `direct_url.json` whose top level is an array **crashes the update check** (`install_update.py:191`) | yes |

**Four sites, four different symptoms**: a bad write reported as success, a crash on the hot path, a silently disabled hook, and a crashed update check. That variety is the argument for fixing it once at the boundary rather than four times at the uses.

## The correct unit of work

**One guard where JSON enters the program**, not `isinstance` checks scattered at each consumer. Two of these four already *have* a type annotation promising a dict (`_read_direct_url_json` is `Optional[dict]`); the annotation is simply not enforced at the one place it could be.

Note the TOML side needs no equivalent: a TOML top level is **always** a table, so `_try_parse_source`'s "expected a top-level object/table" guard can never fire for TOML — measured, deleting it produces zero failures. **This whole obligation is JSON-only**, which makes the boundary narrower and the fix smaller.

## Why it kept being found separately

Each site was discovered by a different agent repairing a different module, and each looked like a local defect. **It only reads as one defect when the four are listed together** — which is an argument for the synthesis pass this campaign has repeatedly shown is where the real findings are.

## Related

Proposed ticket 42 is the same shape one level along: a rejection that is representable as `None` and then discarded. Both are about **the boundary not enforcing what the types already claim.**