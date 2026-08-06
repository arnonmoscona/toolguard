"""
Backward-compatible re-export of :func:`toolguard.api.decide`.

History (TOO-45 R6-S2)
-----------------------
Until this stage, :func:`decide` was DEFINED here, in the ``tooling`` layer.
The live hook's ``--eval`` path needed the same function, but ``runtime ->
tooling`` is an upward import under this project's declared layering, so
``hook.py`` carried a function-local import that could never be hoisted to
module level without also violating the layer rule (TOO-45 R6 reassessment,
section 4, DEMONSTRATED BY EXECUTION: hoisting moves the violation, it does
not remove it). The fix was to move :func:`decide` itself to ``toolguard.api``
-- the new layer this project declared directly above ``engine``, which both
``runtime`` and ``tooling`` are allowed to import from.

This module now forwards the identical function object unchanged, so the
existing production and test call sites written as ``from
toolguard.tools.decision import decide`` (roughly fifteen of them at the time
of this move: :mod:`toolguard.tools.self_permission`,
:mod:`toolguard.tools.uninstall_readiness`, :mod:`toolguard.tools.replay`,
:mod:`toolguard.tools.mining`, :mod:`toolguard.tools.consolidate`,
:mod:`toolguard.testing.sandbox`, the verdict-corpus fixture loader, and
several unit test modules) keep working without a mechanical rename sweep
that this stage's measured scope did not call for. See :mod:`toolguard.api`
for the real implementation, its full docstring (including the "Fidelity
guarantee" this module inherited unchanged), and the design rationale for
why the ``api`` layer's public surface is exactly this one function.

History before TOO-45 R6-S3
-----------------------------
Before R6-S3, :func:`decide` returned a separate ``Decision`` dataclass (the
TOOLING altitude in the R1 scoping trace's altitude picture) that re-rendered
:class:`~toolguard.config_types.RuntimeVerdict` field-by-field. ``Decision``
is gone; :func:`decide` (now in :mod:`toolguard.api`) returns
:class:`~toolguard.config_types.RuntimeVerdict` directly.
"""

from toolguard.api import decide  # noqa: F401 re-exported for backward compatibility
