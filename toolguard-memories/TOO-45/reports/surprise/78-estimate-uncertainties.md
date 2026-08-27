---
title: 78-estimate-uncertainties
type: note
permalink: toolguard/too-45/reports/surprise/78-estimate-uncertainties
---

# Ticket 78 — named uncertainties

## What I would need to see to be more confident

1. **Where `_command_variants` actually lives.** I inferred `toolguard/permissions.py` from its docstring ("Command string matching and permission decisions for the command-kind tools") and from the ticket naming `match_command`. If the variant list is built in `toolguard/compound.py` or in `toolguard/resolve.py` instead, my highest-confidence production file is wrong and the concentration set shifts one module sideways.
2. **Whether a tilde-expansion primitive already exists.** `toolguard/path_utils.py`'s docstring is truncated at "expanding a", which I read as "expanding a `~`". If that helper is already there and already non-throwing, the production diff could be a *single* file — append one variant in `permissions.py` — and my production count of 4 is roughly double the truth.
3. **The post-ticket-80 ambient-access rule.** I do not know which modules the checker permits to read home directly, nor where the allowlist is stored (`.pyscn.toml`, `tools/architecture_fitness.py`, `test/unit/test_architecture.py`, or a dedicated data file). If `normalization.py` is *not* permitted, the expansion must be injected or routed through `path_utils`/`ambient`, which changes the shape of the fix and adds an architecture-test touch I only rated low.
4. **The corpus result.** The ticket makes adoption conditional on measuring the ~6,500-input corpus. If the fourth variant moves any verdict, the diff grows a fixture-data component I cannot see (the inventory lists only `.py`, so corpus fixture files are invisible to me) and the ticket may even be re-scoped rather than implemented. If it moves zero verdicts, as the trio did, the change is small and mechanical.
5. **Whether file-path tools share the defect.** The ticket is written entirely about `Bash` command matching. `toolguard/file_matching.py` may already expand `~` (glob is native for Read/Write/Edit), in which case naming it costs me precision for nothing.

## What I am most likely to be wrong about

- **The new test file.** This is my least-grounded medium. I inferred it from one precedent (`test_assignment_prefix.py`) and a genre match. The project may equally well fold the cases into `test_permissions.py` and `test_normalization.py`, in which case my only predicted addition is a miss and my test-added count should be 0.
- **`README.md`.** Documentation touches on this project are gated at push time (`/documentation-review`) rather than per-ticket, so a fix landing as a standalone commit may carry no doc change at all. This is a plausible false positive.
- **`toolguard/ambient.py`.** I predicted a non-throwing home accessor lands there because the ticket names the `RuntimeError` explicitly. But ticket 44 may have already made home optional as part of owning the fact — in which case ambient is read, not modified, and my medium is a miss.
- **Under-prediction of blast radius.** My known failure mode is stopping at the first working boundary. The realistic direction of surprise here is *more* touches than I named, not fewer: a variant-generation change sits under both the allow and the deny path, and widening what allow rules catch is a behaviour change that tests elsewhere (`test_hard_deny.py`, `test_hierarchical.py`, `test_symlink_hierarchy.py`, `test_resolve.py`, `test_verdict_corpus.py`) could each notice. I named two of those five and rated both low; if the fix ripples, I lose recall there first.
- **`toolguard/file_matching.py` and `toolguard/compound.py`** are the two low-confidence production names most likely to be false positives if the fix stays tightly scoped to `match_command`.