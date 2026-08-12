"""
Detects whether the toolguard package currently governing this process might
be silently wrong: shadowed by an unintended source checkout, or an
installed distribution gone stale against a clean checkout.

Both failures are silent by default -- a stray ``PYTHONPATH=.`` once let a
source checkout of this repository SHADOW the installed package and govern
real permission decisions with uncommitted code for weeks before anyone
noticed. See technical-notes.md, "Shadowed-hook detection and install
hardening", for the full incident and the design choices it drove. This
module answers the two questions needed to make that condition
self-announcing instead of silent:

1. **Is the currently-imported toolguard package a source checkout, rather
   than an installed distribution?** :func:`source_checkout_root` /
   :func:`governing_package_root`.
2. **Does the ACTUALLY INSTALLED distribution's content differ from a clean
   working tree's content?** :func:`installed_distribution_root` /
   :func:`stale_install_report`.

A third predicate lives here too: :func:`pythonpath_shadow_entries` asks the
same "would a toolguard import be shadowed" question, but of the
*environment* rather than of what actually happened in this process, so it
can answer for a different, not-yet-launched invocation.

Nothing here runs on the per-tool-call hook path -- every function does real
filesystem or subprocess work, appropriate only for a once-per-session check.
"""

import hashlib
import importlib.metadata
import os

# subprocess is imported here for its own sake, not just for the type hint
# below -- test_install_provenance.py patches install_provenance.subprocess.run
# directly, which requires this module to hold its own reference to the
# module, even though the actual subprocess.run() call itself now lives in
# toolguard._git.run_git.
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
#: Named rather than written inline because this exact THREE-name,
#: parenthesis-free 3.14 form (``except A, B, C:``) is what silently
#: EXCLUDED this whole file from ``pyscn``'s analysis
#: (``test/unit/test_static_analysis_coverage.py`` guards against a repeat).
#: The bare TWO-name form (``except A, B:``) parses fine and is used
#: throughout this package, e.g. ``toolguard/_git.py`` -- only this clause's
#: third name trips the bug. Parenthesising does not survive either:
#: ``ruff format`` strips ``except (A, B, C):`` back to the bare form
#: whenever no name is bound to force the parens. Binding the tuple to a
#: name sidesteps both problems.
_PYPROJECT_READ_ERRORS = (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError)


def governing_package_root() -> Path:
    """
    Return the directory of the toolguard package that produced THIS import.

    Returns:
        The resolved, symlink-free ``toolguard/`` package directory --
        whichever copy (an installed distribution's site-packages, or a
        shadowing source checkout) is currently GOVERNING this process.
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
            process). Passing an explicit path lets a caller classify a
            DIFFERENT candidate package directory instead -- e.g. a Claude
            Code session's own ``toolguard/`` directory under its project
            root, ``project_root / "toolguard"`` (see
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
    package -- exactly the case this whole module exists to detect.

    Args:
        dist_name: The installed distribution name (default ``"toolguard"``).

    Returns:
        The installed ``toolguard/`` package directory, or ``None`` whenever it
        cannot be located -- most commonly a bare checkout that was never
        ``pip``/``uv tool install``-ed.
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
    never as "assume clean": never nag on uncertainty.

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
    Compute a stable SHA-256 digest over the ``.py`` files under *root*.

    Files are hashed in sorted RELATIVE-path order (not filesystem iteration
    order, and not affected by *root* itself differing between the two sides
    of a comparison) so the digest is deterministic and comparable across two
    different root directories with the same internal layout. Only byte
    content and relative path feed the digest -- mtimes/permissions never do.
    A file that raises ``OSError`` on read is silently SKIPPED rather than
    failing the whole digest -- one side of a comparison losing a file this
    way, and not the other, can flip the verdict with no error raised.

    Args:
        root: Directory to scan recursively for ``.py`` files to hash.

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
            uncommitted changes under ``toolguard/``), BOTH sides hash
            successfully, AND the two hashes differ. ``False`` for every
            other outcome: no checkout, no installed distribution, a dirty
            or undetermined tree, either side failing to hash (a missing
            directory or no ``.py`` files), or matching hashes. See
            :func:`stale_install_report` for why every non-``True`` outcome
            is deliberately silent rather than a warning.
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

    See :class:`StaleInstallReport` for exactly what ``is_stale`` means.
    Every non-``True`` outcome is silent by design: warning on an ordinary
    dev-loop dirty tree would be pure noise and train the reader to ignore
    it, and uncertainty must never be promoted into a claim -- never nag on
    uncertainty, never guess "stale".

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
    exists -- the ``PYTHONPATH=.`` footgun generalised to any directory. This
    is a PREDICTIVE check over the environment (would a fresh toolguard
    invocation be shadowed), independent of whether THIS process itself
    happens to be shadowed right now.

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
