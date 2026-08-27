---
title: 100-prereg
type: note
permalink: toolguard/too-45/reports/surprise/100-prereg
---

# Ticket 100 pre-registration - two orphaned module-private functions

Locked 2026-08-22, after dispatch, before any result seen. Informed estimate.

## Production files predicted
1. `toolguard/compound.py` -- delete `_resolve_leaf`
2. `toolguard/config.py` -- delete `_discover_rules_files`
3. `tools/architecture_fitness.py` -- new `--orphans` mode

**Predicted production count: 3.**

## Test files predicted
`test/unit/test_compound.py`, `test/unit/test_compound_resolve_seam.py` (~30 call sites repointed), possibly a test for the new check.

## Named uncertainties
- **U1**: repointing `_resolve_leaf`'s tests at `resolve_compound_permission_detailed` puts `_combine_strictest` in the path and gives the verdict real `matched_rule`/`provenance` instead of defaults. **I predict at least one test's expectations legitimately change**, and I have told the agent to report rather than paper over it. If ALL 30 repoint cleanly, that is mildly suspicious and worth a look.
- **U2**: whether `--orphans` reports zero after the change. If it reports more than zero, the original AST sweep missed something.
- **U3**: `architecture_fitness.py` is shared with the #104 agent. I predict a merge conflict in the argument parser.