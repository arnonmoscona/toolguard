---
title: TOO-45 surprise factor - ticket 78 scored
type: note
tags: [task-memory, TOO-45, measurement]
permalink: toolguard/too-45/reports/surprise/78-scored
---

# Ticket 78 scored (absolute-spelled rule vs tilde-spelled command)

Actual from `git diff --numstat 1dfda8e..8867367`. **Primitives only.**

## Actual — production (3 files)

| file | +/- | predicted? | confidence |
|---|---|---|---|
| `toolguard/normalization.py` | 67/10 | yes | high |
| `toolguard/permissions.py` | 25/13 | yes | high |
| `toolguard/path_utils.py` | 2/2 | yes | medium |

**Production hits 3 of 3.** Zero production surprises.

Predicted-production not touched (5): `ambient.py` (medium), `file_matching.py` (low), `README.md` (medium), `compound.py` (low), `tools/architecture_fitness.py` (low).

## Actual — test (3 files)

| file | +/- | predicted? |
|---|---|---|
| `test/unit/test_normalization.py` | 223/6 | yes (high) |
| `test/unit/test_permissions.py` | 321/0 | yes (high) |
| `test/unit/test_ask_resolution.py` | 24/1 | **no — surprise** |

Predicted-test not touched (5): `test_hard_deny.py`, `test_path_utils.py`, `test_ambient.py`, `test_verdict_corpus.py`, `test_architecture.py`.

## Actual — docs (1 file)

| file | +/- | predicted? |
|---|---|---|
| `docs/permission-patterns.md` | 31/5 | **no — surprise** |

## Surprises: 2, both `E`, 0 alarms

- `docs/permission-patterns.md` — `E`. The estimator predicted **`README.md`** for the user-visible spelling contract. This project keeps pattern documentation in a dedicated file.
- `test/unit/test_ask_resolution.py` — `E`. Read/Write/Edit tilde coverage landed here rather than in a file-matching test.

## THREE findings, and two of them are now confirmed across multiple items

**1. Doc-file identity is systematically mispredicted, exactly like test-file identity.** Ticket 77's estimator also predicted `README.md` and `technical-notes.md` and the change went to `docs/agent-map.md`, `docs/configuration.md`, `docs/permission-patterns.md`, `docs/native-pattern-reference.md`. **Two for two.** An estimator reasons "user-visible behaviour -> README"; this project has a `docs/` tree with topic files. This is a property of the repository, not estimator error, and scoring it as `E` mislabels it — the same correction already recorded for test-file identity in `77-scored.md`. **Recommend the aggregate treat doc-file identity separately, or exclude doc files from recall entirely.**

**2. A predicted file was touched and then untouched — a category the protocol has no name for.** `toolguard/ambient.py` was predicted at medium confidence and shows **zero** net change. But it *was* modified during the work: `AmbientFacts.user` was added by one repair pass and removed by the next when the approach changed to a passwd lookup. The estimator was right about where the pressure would land; the net is zero because the design was replaced mid-flight.

This is neither `A` (absorbed by a seam — the architecture did not prevent it) nor `X` (descoped — the requirement was met, by other means). Call it **`T` (transient)**: predicted, actually touched, reverted before the commit. **It is only visible from the reflog and the agent reports, not from the diff** — so it cannot be recovered later for any already-scored item, and it is a reason to record intermediate state during a multi-pass ticket rather than only the final diff.

**3. `file_matching.py`: right reach, wrong file.** Predicted at low confidence and not touched — yet the fix *does* reach Read/Write/Edit, via the shared `expand_tilde` call rather than through that module. The estimator's reasoning ("a fix framed as fail-open will be swept across both matchers rather than left half-fixed") was **correct about the outcome and wrong about the mechanism**. Scoring by file counts this as a miss; scoring by claim it is a hit. Worth flagging for the aggregate as a limitation of file-granular scoring.

## Cost note, outside the protocol

78 took **five blinded review rounds and ~10 hours**. Rounds 2-5 pursued tilde positions with near-zero field occurrence (`name=~/...` occurs **once** in 57,000 commands; `~` after a redirect **zero** times in the real-user corpus), and round 4's fix introduced a measured loosening that round 5 caught. **The evidence gate existed by then but was being applied to whole tickets and not to findings within a ticket.** That is the process defect this item paid for.
