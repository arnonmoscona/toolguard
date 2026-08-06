"""
Toolguard install-provenance detection (TOO-19).

Stdlib-only leaf module: the only intra-package imports it has (TOO-19 code
review M3) are :mod:`toolguard.constants` and :mod:`toolguard._git`, which are
themselves stdlib-only leaves importing nothing from ``toolguard`` at all --
so this module still creates no dependency :mod:`toolguard.hook` (the
per-tool-call PreToolUse hook) would inherit, and is safe to use from
:mod:`toolguard.session_start` (a session-level entry point) and from
:mod:`toolguard.tools` audit code alike. **Nothing here is called from the hot
per-tool-call hook path** -- every function does real filesystem/subprocess
work, appropriate only for a once-per-session check.

Background: a stray ``PYTHONPATH=.`` exported from a shell rc file made a git
checkout of this repository SHADOW the installed toolguard package for every
process whose working directory happened to be that checkout -- including the
tool venv's own interpreter running the live PreToolUse hook. The hook
silently governed permissions using uncommitted, mid-refactor code for weeks
before this was noticed (TOO-19). This module answers the two questions
needed to make that condition self-announcing instead of silent:

1. **Is the currently-imported toolguard package a source checkout, rather
   than an installed distribution?** :func:`source_checkout_root` /
   :func:`governing_package_root`.
2. **Does the ACTUALLY INSTALLED distribution's content differ from a clean
   working tree's content?** :func:`installed_distribution_root` /
   :func:`stale_install_report`. "Installed" is located via
   :mod:`importlib.metadata`, which walks ``sys.path`` for the matching
   ``*.dist-info`` the same way ``pip``/``uv`` left it -- independent of
   whichever ``toolguard`` package actually satisfied a given import, so this
   still finds the real installed copy even while it is being shadowed.

A third, unrelated predicate lives here too because it shares the same
"would a toolguard import be shadowed" question, just asked of the
environment instead of this process's own state:
:func:`pythonpath_shadow_entries`, used by
:mod:`toolguard.tools.environment_audit` (the security-audit finding) and
NOT by the two checks above (which look at what actually happened, not what
the environment merely permits).
"""

import hashlib
import importlib.metadata
import os

# subprocess is imported for its own sake here, not just for run_git()'s
# benefit -- see _git_subtree_is_clean() below, whose module-attribute access
# (patch.object(install_provenance.subprocess, "run", ...) in
# test_install_provenance.py) requires this module to hold its own reference
# to the module, even though the actual subprocess.run() call itself now
# lives in toolguard._git.run_git.
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Tuple

from toolguard._git import run_git
from toolguard.constants import DIST_NAME as _DEFAULT_NAME

#: Failure modes of reading and parsing a candidate ``pyproject.toml``, all of
#: which mean the same thing here: this is not a source checkout we can
#: identify, so answer None rather than raising.
#:
#: Named rather than written inline as ``except A, B, C:`` because that bare
#: 3.14 form is not parseable by every tool that reads this package -- `pyscn`
#: silently EXCLUDED this whole file from its analysis because of it, so the
#: metrics covered 58 of 59 modules with only a warning to say so. Parenthesising
#: the clause does not survive: `ruff format` rewrites `except (A, B, C):` back
#: to the bare form whenever there is no `as` binding to force the parens (the
#: parenthesised clauses elsewhere in this package all bind `as e`, which is why
#: they persist). Binding the tuple to a name sidesteps the syntax entirely.
_PYPROJECT_READ_ERRORS = (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError)


def governing_package_root() -> Path:
    """
    Return the directory of the toolguard package that produced THIS import.

    Since this function is itself defined inside ``toolguard/install_provenance.py``,
    ``Path(__file__)`` already names wherever THAT import was actually
    satisfied from -- the currently GOVERNING copy for this process, whether
    that is an installed distribution's site-packages or a shadowing source
    checkout.

    Returns:
        The resolved, symlink-free ``toolguard/`` package directory.
    """
    return Path(__file__).resolve().parent


def source_checkout_root(
    package_root: Optional[Path] = None, *, expected_name: str = _DEFAULT_NAME
) -> Optional[Path]:
    """
    Return the checkout root when *package_root* sits inside a source checkout.

    A source checkout is recognised by a ``pyproject.toml`` SIBLING to the
    package directory (i.e. ``package_root.parent / "pyproject.toml"``)
    declaring ``[project].name == expected_name``, with *package_root* itself
    holding an ``__init__.py``. This is the tell an installed distribution
    never has: a ``pip``/``uv tool install`` copy ships ``toolguard/`` next to
    a ``toolguard-X.Y.Z.dist-info/`` directory, never a ``pyproject.toml``.

    Args:
        package_root: The package directory to classify (defaults to
            :func:`governing_package_root` -- i.e. the copy governing THIS
            process). Passing an explicit path lets a caller ask the same
            question about a DIFFERENT candidate directory, e.g. a Claude
            Code session's active project root (see
            :mod:`toolguard.session_start`).
        expected_name: The ``[project].name`` to require (default
            ``"toolguard"``), so an unrelated ``pyproject.toml`` one level up
            a nested layout never produces a false positive.

    Returns:
        The checkout root (``package_root.parent``), or ``None`` when
        *package_root* is not a source checkout of *expected_name*.
    """
    if package_root is None:
        package_root = governing_package_root()
    if not (package_root / "__init__.py").is_file():
        return None
    candidate = package_root.parent / "pyproject.toml"
    if not candidate.is_file():
        return None
    try:
        data = tomllib.loads(candidate.read_text(encoding="utf-8"))
    except _PYPROJECT_READ_ERRORS:
        return None
    if data.get("project", {}).get("name") != expected_name:
        return None
    return package_root.parent


def installed_distribution_root(dist_name: str = _DEFAULT_NAME) -> Optional[Path]:
    """
    Locate the ACTUALLY INSTALLED toolguard package directory, independent of
    what actually got imported.

    :func:`importlib.metadata.distribution` walks ``sys.path`` for a matching
    ``*.dist-info`` directory the same way ``pip``/``uv`` left it. This
    succeeds even when an earlier ``sys.path`` entry (e.g. an accidental
    ``PYTHONPATH=.``) shadows the real import with a different ``toolguard/``
    package (TOO-19) -- exactly the case this whole module exists to detect.

    Args:
        dist_name: The installed distribution name (default ``"toolguard"``).

    Returns:
        The installed ``toolguard/`` package directory, or ``None`` when no
        such distribution is installed at all (e.g. a bare checkout that was
        never ``pip``/``uv tool install``-ed), or its RECORD is missing the
        top-level ``__init__.py`` entry.
    """
    try:
        dist = importlib.metadata.distribution(dist_name)
    except importlib.metadata.PackageNotFoundError:
        return None
    try:
        located = dist.locate_file(f"{dist_name}/__init__.py")
    except Exception:
        return None
    located_path = Path(str(located))
    return located_path.parent if located_path.is_file() else None


def _git_subtree_is_clean(checkout_root: Path, subtree: str) -> Optional[bool]:
    """
    Return whether *subtree* has zero uncommitted changes in *checkout_root*.

    Runs ``git -C <checkout_root> status --porcelain -- <subtree>``. Returns
    ``None`` (genuinely unknown, never a guess) when git is unavailable, the
    directory is not a git work tree, or the process cannot be run for any
    reason -- callers MUST treat ``None`` the same as ``False`` (stay silent),
    never as "assume clean" (TOO-19: never nag on uncertainty).

    Args:
        checkout_root: The git work tree root to check.
        subtree: A path (relative to *checkout_root*) to scope the status
            check to.

    Returns:
        ``True`` when clean, ``False`` when dirty, ``None`` when undetermined.
    """
    result: Optional[subprocess.CompletedProcess[str]] = run_git(
        ["-C", str(checkout_root), "status", "--porcelain", "--", subtree]
    )
    if result is None or result.returncode != 0:
        return None
    return result.stdout.strip() == ""


def _hash_py_files(root: Path) -> Optional[str]:
    """
    Compute a stable SHA-256 digest over every ``.py`` file's content under *root*.

    Files are hashed in sorted RELATIVE-path order (not filesystem iteration
    order, and not affected by *root* itself differing between the two sides
    of a comparison) so the digest is deterministic and comparable across two
    different root directories with the same internal layout. Only byte
    content and relative path feed the digest -- mtimes/permissions never do.

    Args:
        root: Directory to hash every ``.py`` file under, recursively.

    Returns:
        The hex digest, or ``None`` when *root* does not exist or contains no
        ``.py`` files (an empty/degenerate root must never look like a
        "match" against a real package).
    """
    if not root.is_dir():
        return None
    paths = sorted(root.rglob("*.py"), key=lambda p: p.relative_to(root).as_posix())
    if not paths:
        return None
    digest = hashlib.sha256()
    for path in paths:
        try:
            content = path.read_bytes()
        except OSError:
            continue
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(content)
    return digest.hexdigest()


@dataclass(frozen=True)
class StaleInstallReport:
    """
    Result of comparing the installed toolguard distribution against a clean
    working tree.

    Attributes:
        is_stale: ``True`` ONLY when the working tree is confirmed CLEAN (no
            uncommitted changes under ``toolguard/``) AND its content hash
            differs from the installed distribution's. ``False`` for every
            other outcome (dirty tree, cleanliness undetermined, no checkout,
            no installed distribution, or matching hashes) -- see
            :func:`stale_install_report`'s "never nag on uncertainty" rule.
        checkout_root: The source checkout root that was compared, or
            ``None`` when no checkout was given/found.
        installed_root: The installed distribution's package root, or
            ``None`` when none was found.
    """

    is_stale: bool
    checkout_root: Optional[Path]
    installed_root: Optional[Path]


def stale_install_report(checkout_root: Optional[Path] = None) -> StaleInstallReport:
    """
    Detect a stale installed toolguard distribution relative to *checkout_root*.

    "Stale" means: the working tree is CLEAN under ``toolguard/`` (no
    uncommitted changes) AND its content hash differs from the installed
    distribution's. Every other outcome -- a dirty tree, cleanliness that
    could not be determined, or no installed distribution found -- reports
    ``is_stale=False`` by design: warning on an ordinary dev-loop dirty tree
    would be pure noise and train the reader to ignore it, and uncertainty
    must stay silent, never guess "stale" (TOO-19).

    Args:
        checkout_root: The source checkout to compare (defaults to
            :func:`source_checkout_root`'s result for the currently governing
            copy; when that is ``None`` -- not running from a checkout at all
            -- this returns ``is_stale=False`` immediately).

    Returns:
        A :class:`StaleInstallReport`.
    """
    if checkout_root is None:
        checkout_root = source_checkout_root()
    if checkout_root is None:
        return StaleInstallReport(False, None, None)

    installed_root = installed_distribution_root()
    if installed_root is None:
        return StaleInstallReport(False, checkout_root, None)

    clean = _git_subtree_is_clean(checkout_root, "toolguard")
    if clean is not True:  # False (dirty) or None (unknown) -> stay silent
        return StaleInstallReport(False, checkout_root, installed_root)

    working_hash = _hash_py_files(checkout_root / "toolguard")
    installed_hash = _hash_py_files(installed_root)
    if working_hash is None or installed_hash is None:
        return StaleInstallReport(False, checkout_root, installed_root)

    return StaleInstallReport(
        working_hash != installed_hash, checkout_root, installed_root
    )


def pythonpath_shadow_entries(
    env: Optional[Mapping[str, str]] = None,
) -> Tuple[str, ...]:
    """
    Return ``PYTHONPATH`` entries that would shadow an installed toolguard package.

    An entry shadows the install when ``<entry>/toolguard/__init__.py``
    exists -- exactly the TOO-19 ``PYTHONPATH=.`` footgun generalised to any
    directory. This is a PREDICTIVE check over the environment (would a fresh
    toolguard invocation be shadowed), independent of whether THIS process
    itself happens to be shadowed right now -- see
    :mod:`toolguard.tools.environment_audit`, whose finding is deliberately
    about the hook's resolution, not the auditing process's own (which may
    itself be a deliberate ``--dev`` run from this same checkout).

    Args:
        env: Environment mapping to read ``PYTHONPATH`` from (defaults to
            :data:`os.environ`). Exposed for testing without mutating the
            real environment.

    Returns:
        The subset of ``PYTHONPATH`` entries (original order, de-duplicated)
        that contain a ``toolguard/`` package -- empty when ``PYTHONPATH`` is
        unset, empty, or contains no such entry.
    """
    if env is None:
        env = os.environ
    raw = env.get("PYTHONPATH", "")
    if not raw:
        return ()
    found = []
    for entry in raw.split(os.pathsep):
        if not entry or entry in found:
            continue
        if (Path(entry) / "toolguard" / "__init__.py").is_file():
            found.append(entry)
    return tuple(found)
