---
title: TOO-45 surprise factor - ticket 85 chunk A scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/85-scored
---

# Ticket 85 chunk A scored — commit `d278d26`

Basis locked in `85-prereg.md` before the estimate existed: **chunk A's commit only**.

## Headline

| metric | value |
|---|---|
| **line-weighted recall (headline)** | **121 / 121 = 100%** |
| file recall | **7 / 7 = 100%** |
| precision (integrity guard only) | 7 / ~12 = 58% |
| **move-or-re-export call** | **CORRECT** |

**Second perfect touch set in the series** (after item 22), and the first where the character-of-fix question was *also* right.

## Per-file — every file predicted

| file | lines | confidence |
|---|---|---|
| `toolguard/claude_code_contract.py` (new) | 53 | high |
| `toolguard/hook.py` | 52 | high |
| `toolguard/tools/installer.py` | 7 | — |
| `toolguard/session_start.py` | 3 | — |
| `toolguard/tools/takeover_audit.py` | 3 | — |
| `.pyscn.toml` | 2 | **high** |
| `test/unit/test_architecture.py` | 1 | **high** |

**It predicted both ratchet files at high confidence**, with the right reasons — *"new leaf module needs a layer entry"* and *"a new foundation-layer leaf plausibly intersects an exhaustiveness check."* This is the class of miss that cost ticket 64 a falsified prediction (`--ambient`'s owners table), and it was learned here without being told.

## The character-of-fix question — CORRECT, with better reasoning than mine

> *"A re-export facade wouldn't produce that edge in any meaningful sense — if the old modules kept their literals and the new module merely re-exported values sourced from them, **the dependency would point the wrong way**."*

That is the sharper form of the argument. I framed move-versus-re-export as "does the caller change"; it framed it as **which direction the dependency points**, which is the property that actually makes the edge useful.

**And the distinction turned out to matter — one chunk later.** Chunk C left a consumer importing a moved constant from its old module, where it was still re-exported, and I had to repoint it. The estimator identified the exact failure mode of chunk C while estimating chunk A.

## FINDING 25 — a high-confidence false positive from an INFERRED convention

It predicted `test/unit/test_claude_code_contract.py` as a **new file at high confidence**, reasoning: *"this repo's convention (visible throughout the inventory) is one test file per production module, with no exceptions I could find."*

**Measured: 28 of 39 top-level modules have one; 11 do not** — `constants`, `config_types`, `issues`, `toml_scan`, `_git`, `file_matching`, and others. **They are all constant- or type-holding leaves, which is exactly what `claude_code_contract` is.** So the correct call was to create none, and the implementer matched the real convention.

**The inference was good and the premise was false.** *"No exceptions I could find"* is a claim about the estimator's search, stated as a claim about the repo — and the file inventory it reads makes absence hard to see, because a missing test file is not a row.

Worth carrying: **an estimator asserting a universal from an inventory is asserting the absence of rows, which is the one thing an inventory is bad evidence for.** Same shape as the campaign's own repeated finding that a zero count measures observability rather than absence.

## Contamination

None. Ticket 85's file carries no coordinator appendix; the return channel disclosed no prediction (a bare *"Both files are written"* preamble, same as item 22).
