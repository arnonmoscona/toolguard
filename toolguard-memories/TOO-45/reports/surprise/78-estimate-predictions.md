---
title: 78-estimate-predictions
type: note
permalink: toolguard/too-45/reports/surprise/78-estimate-predictions
---

# Ticket 78 — blinded touch-set prediction

Estimator read only the ticket and the file inventory. No source was read, no grep, no tests, no history.

## 1. Predicted touch set

### Production

| File | Reason | Confidence |
|---|---|---|
| `toolguard/permissions.py` | Owns `match_command` and `_command_variants` (the ticket's named site); the fourth, tilde-expanded spelling is appended to the deduplicated variant list here | high |
| `toolguard/normalization.py` | Home is `normalize_path`'s module and the ticket frames the defect as "normalization runs in the collapsing direction only"; the inverse operation (expand `~` to absolute) is added as a sibling public function, non-throwing | high |
| `toolguard/path_utils.py` | Its own docstring already advertises "expanding a ..."; the low-level primitive either already exists here and is reused, or is added/hardened here, with `normalization` delegating rather than reimplementing | medium |
| `toolguard/ambient.py` | The ticket's explicit non-throwing requirement is about `Path.home()` raising `RuntimeError`; post-ticket-44 that fact is owned by `ambient`, so the safe/optional home accessor lands or is exercised here | medium |
| `toolguard/file_matching.py` | The same collapse-only asymmetry plausibly exists for `Read`/`Write`/`Edit` path rules; a security fix framed as fail-open is likely to be swept across both matchers rather than left half-fixed | low |
| `README.md` | The `~`-vs-absolute rule/command spelling contract is user-visible documented behaviour and the ticket calls the absolute spelling "the spelling most documentation examples use" | medium |
| `toolguard/compound.py` | Only if per-leaf matching builds its own candidate spellings instead of delegating to `permissions` | low |
| `tools/architecture_fitness.py` | Ticket 80's ambient-access checker carries the allowlist of modules permitted to read ambient state; a new home reader in `normalization` or `permissions` would need the list amended (or, more likely, the design avoids this by routing through `path_utils`) | low |

### Test

| File | Reason | Confidence |
|---|---|---|
| `test/unit/test_normalization.py` | Direct unit cover for the new expansion helper, including the non-throwing path when home cannot be determined | high |
| `test/unit/test_permissions.py` | The matcher-level assertion: an absolute-spelled rule fires on a `~`-spelled command, in both allow and deny directions | high |
| new `test/unit/test_tilde_spelling.py` (name uncertain — `test_tilde_expansion.py` / `test_home_spelling.py` equally likely) | Strong local precedent: `test_assignment_prefix.py` is a whole module named after one security asymmetry of exactly this shape ("a leading `NAME=value` must not hide the command from a deny rule") | medium |
| `test/unit/test_hard_deny.py` | The fail-open story is a deny-rule story, and `[hard_deny]` is the layer where an evaded sensitive-file pattern matters most | medium |
| `test/unit/test_path_utils.py` | Only 70 lines today; if the primitive lands or hardens there it gains the failure-mode cases | medium |
| `test/unit/test_ambient.py` | If `ambient` grows a non-throwing home accessor, its "home cannot be determined" case is asserted here | low |
| `test/unit/test_verdict_corpus.py` | The ticket mandates measuring corpus impact; if any verdict moves, the HARD-tier replay and its fixtures record it | low |
| `test/unit/test_architecture.py` | Only if the ambient-access allowlist moves | low |

I am deliberately **not** naming: `toolguard/api.py`, `toolguard/resolve.py`, `toolguard/permission_resolution.py`, `toolguard/hook.py`, `toolguard/patterns.py`, the parser package, or any module under `toolguard/tools/` beyond the one listed. The change is a variant-generation change below the resolver; nothing above it should need to know.

## 2. Concentration set

- `toolguard/permissions.py`
- `toolguard/normalization.py`
- `toolguard/path_utils.py`
- `test/unit/test_permissions.py`
- `test/unit/test_normalization.py`

That is where I expect the great majority of the diff. Everything else on the list is a spillover I expect to be one to five lines, or not to happen at all.

## 3. Expected counts

Point estimates, production and test scored separately.

### Production

| | Point estimate | Plausible range |
|---|---|---|
| modified | 4 | 2–6 |
| added | 0 | 0–1 |
| deleted | 0 | 0 |

The single most likely added production file would be a small dedicated home/tilde-spelling module, but the tree already has both `normalization.py` and `path_utils.py` sitting exactly there, so I predict no new production module. Of the 4 modified, I count `README.md` as one; if documentation is excluded from the production count, read this as 3.

### Test

| | Point estimate | Plausible range |
|---|---|---|
| modified | 3 | 2–5 |
| added | 1 | 0–1 |
| deleted | 0 | 0 |

If the new named test module does land, I expect `test/unit/test_permissions.py` to move less than predicted (the matcher-level cases go to the new file instead), so added=1 and modified=2 is a coherent joint outcome, as is added=0 and modified=4.