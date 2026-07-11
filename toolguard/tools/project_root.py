"""
Repo-grain project-root resolution for the migration safety gate.

Hierarchy migration (promoting a rule from a project layer up to the user layer)
is only safe when we can name an unambiguous *project boundary*.  The canonical
boundary is a **project anchor** -- a version-control root (``.git``/``.hg``/
``.jj``) or an explicit Claude Code project marker (``.claude`` directory,
``CLAUDE.md`` file); both are language-agnostic and unambiguous, whereas a
build manifest (``pyproject.toml``, ``package.json``, ...) can sit in a
sub-package *below* the real repo root and give the wrong grain.  The migration
grain is therefore the **repository**, not the package.

This module is a thin re-export of the canonical implementation in
:mod:`toolguard.path_utils` (TOO-15).  The implementation lives there -- a
leaf module (stdlib only) -- rather than here, because :mod:`toolguard.hook`
(the live runtime hook) imports :mod:`toolguard.config`/
:mod:`toolguard.env_config` directly, and those two modules share this same
resolution primitive (in their "nearest marker of any kind wins" ``strict``
mode) for their own project-root discovery.  Keeping the shared primitive in
:mod:`toolguard.path_utils` means the runtime hook's import graph never has to
depend on :mod:`toolguard.tools`, which is deliberately segregated from the
runtime permission-evaluation path (see ``toolguard/tools/__init__.py``).

:func:`resolve_project_root` classifies the situation into a structured
:class:`ProjectRootResolution` and leaves the *decision* (proceed / ask /
refuse) to the caller.  The deterministic core never prompts: when the
boundary is unambiguous (an anchor root, or an explicit persisted override) it
resolves it; when only weaker markers exist it returns ``AMBIGUOUS`` with
candidate roots for a skill to disambiguate; when nothing is found it returns
``NONE`` so the gate can refuse.  This module always calls it in its
``strict=False`` (tiered, anchor-first) shape -- the migration-gate semantics.

Relationship to the two runtime ``find_project_root`` helpers (intentionally
distinct, NOT a fork -- both now call the same shared primitive in its
``strict=True`` shape):

* :func:`toolguard.config.find_project_root` -- *package*-grain, RAISES; finds the
  nearest strong-anchor/``pyproject.toml`` marker for **config-file discovery**
  (a package's ``.claude`` may legitimately live below the repo root).
* :func:`toolguard.env_config.find_project_root` -- same nearest-marker search,
  returns ``None`` instead of raising, for **.env loading**.
"""

from toolguard.path_utils import (
    CONFIG_ROOT_INDICATORS,
    DEFAULT_INDICATORS,
    ProjectRootResolution,
    RootCandidate,
    RootStatus,
    STRONG_PROJECT_ANCHORS,
    resolve_project_root,
)

__all__ = [
    "CONFIG_ROOT_INDICATORS",
    "DEFAULT_INDICATORS",
    "ProjectRootResolution",
    "RootCandidate",
    "RootStatus",
    "STRONG_PROJECT_ANCHORS",
    "resolve_project_root",
]
