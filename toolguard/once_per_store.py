"""
Cross-project ``(project, kind, scope)`` claim store backing "once per
period" throttling.

This module is a private implementation layer: application code must not
import this module directly; throttle through :mod:`toolguard.once_per`.

Storage lives at ``~/.toolguard/once_per.db``, never inside a project
directory. Because the store is shared across every project, isolation is
by KEY rather than by file: every claim is keyed on ``(project, kind,
scope)``, where ``project`` is the project-root path as ``str`` (so a row
stays readable if someone inspects the database by hand).

Schema: one table ``claims(project, kind, scope, created_at, expires_at)``,
primary keyed on ``(project, kind, scope)``, with real timestamp columns --
expiry is a comparison, never a filename parse. ``scope`` and ``kind`` are
opaque strings this module does not validate or constrain; :func:`day_scope`
is only a convenience for building one particular ``scope`` shape
(``"day:YYYY-MM-DD"``), not a requirement.

Every write is fail-soft: a broken or unwritable store must never break a
permission decision. But "fail soft" is not "always report success":
:func:`claim` reports its outcome per call via :class:`ClaimResult` --
``CLAIMED``, ``HELD_BY_SOMEONE_ELSE``, or ``UNGUARANTEED`` (with a
``reason``) -- so a caller whose action is unsafe to repeat can tell "I
hold the claim" apart from "the guarantee could not be verified this time"
instead of both collapsing into one ambiguous ``True``. Only :func:`claim`
may create ``~/.toolguard/`` or the database -- every other function here
only reads or deletes, and must never create storage that a caller with
nothing to report would otherwise never have touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Optional

try:
    # pragma: no cover - stdlib built without the optional _sqlite3 extension
    import sqlite3
except ImportError:
    sqlite3 = None  # type: ignore[assignment]

#: Named so the except clauses read ``except <name>:`` -- an inline tuple
#: has its parens stripped by ruff, and the unparenthesized form fails
#: pyscn's parser (``test_pyscn_reports_no_parse_failures``).
_STORAGE_ERRORS = (OSError, sqlite3.Error) if sqlite3 is not None else (OSError,)

#: ``_STORAGE_ERRORS`` plus ``ValueError``/``TypeError`` -- see
#: :func:`is_claimed`'s except block for why.
_READ_ERRORS = _STORAGE_ERRORS + (ValueError, TypeError)

#: Test-patchable override for the store path
#: (``patch.object(once_per_store, "_STORE_PATH", ...)``). ``None`` means
#: "use the default" -- see :func:`_resolve_store_path`.
_STORE_PATH: Optional[Path] = None

#: Schema version, checked via ``PRAGMA user_version`` by :func:`_ensure_schema`.
#: Bump this whenever the ``claims`` table's shape changes.
_SCHEMA_VERSION = 1

#: Column list shared by both the healing (``IF NOT EXISTS``) and the
#: recreate paths in :func:`_ensure_schema`, so the two can never drift apart.
_CLAIMS_TABLE_COLUMNS = (
    "project TEXT NOT NULL, "
    "kind TEXT NOT NULL, "
    "scope TEXT NOT NULL, "
    "created_at TEXT NOT NULL, "
    "expires_at TEXT NOT NULL, "
    "PRIMARY KEY (project, kind, scope)"
)

#: Swept on sight by :func:`reap`, under a project's logs_dir; nothing in
#: this repository writes it.
_LEGACY_PROJECT_DB_FILENAME = ".toolguard-suppression.db"

#: In the same directory as the current store path. Swept on sight by
#: reap(); nothing in this repository writes it, disposable state like
#: everything else here.
_LEGACY_STORE_FILENAME = "suppression.db"

#: Legacy per-kind marker-file prefixes the claim store replaced. Nothing
#: writes these anymore; reap() sweeps any that linger. The one place a
#: filename glob is correct here -- these are the old marker-file format,
#: not this module's.
_LEGACY_MARKER_PREFIXES = (
    ".toolguard-warned-",
    ".toolguard-migration-",
    ".toolguard-divergence-warned-",
)

_DAY_SCOPE_PREFIX = "day:"


def day_scope(for_date: Optional[date] = None) -> str:
    """
    Build a per-calendar-day scope string: ``"day:YYYY-MM-DD"``.

    Local time (this is a desktop tool, not a server). Defaults to today.
    """
    return f"{_DAY_SCOPE_PREFIX}{(for_date or date.today()).isoformat()}"


class ClaimStatus(Enum):
    """Per-call outcome of :func:`claim`."""

    #: This call inserted a fresh row, or reclaimed one whose ttl had already
    #: elapsed -- the caller holds the claim and should proceed.
    CLAIMED = "claimed"

    #: Another, still-live claim already exists -- the caller should stay quiet.
    HELD_BY_SOMEONE_ELSE = "held_by_someone_else"

    #: The once-per-period guarantee could NOT be verified for this call
    #: (sqlite3 missing, no project root, or a storage error) -- see ``reason``.
    #: Distinct from ``HELD_BY_SOMEONE_ELSE``: that is a normal, expected
    #: outcome; this is a degraded one a caller may want to surface.
    UNGUARANTEED = "unguaranteed"


@dataclass(frozen=True)
class ClaimResult:
    """
    Outcome of a single :func:`claim` call.

    ``reason`` is populated only when ``status`` is
    :attr:`ClaimStatus.UNGUARANTEED` -- a short, caller-facing phrase for
    composing a degraded-mode notice.
    """

    status: ClaimStatus
    reason: Optional[str] = None


#: :class:`ClaimResult` reasons for :attr:`ClaimStatus.UNGUARANTEED`. Every
#: caller-facing degraded-mode notice is composed from exactly one of these.
_REASON_NO_SQLITE = "sqlite3 is unavailable"
_REASON_NO_PROJECT = "no project root could be resolved"
_REASON_STORAGE_ERROR = "a storage error occurred"


def _project_key(project: Optional[Path]) -> Optional[str]:
    """Normalise *project* to its stored key, or None when unresolved."""
    return None if project is None else str(project)


def _resolve_store_path() -> Optional[Path]:
    """
    Resolve the claim database path, lazily.

    Returns the test-patched :data:`_STORE_PATH` override when one is set,
    otherwise computes ``~/.toolguard/once_per.db`` fresh on every call --
    never cached at module scope -- so a store-touching call always picks
    up whatever ``$HOME`` is live for the current process. Also never
    resolved at import time: a module-level ``Path.home()`` call would make
    this module -- and anything that imports it -- fail to import on a
    container/CI shape with no ``HOME`` and no passwd entry.

    Returns ``None`` ("store unavailable") if ``Path.home()`` cannot be
    resolved (e.g. no ``HOME`` and no passwd entry for the uid, an ordinary
    container/CI shape). Every caller here must treat ``None`` like any
    other storage error: fail soft, never raise.
    """
    if _STORE_PATH is not None:
        return _STORE_PATH
    try:
        return Path.home() / ".toolguard" / "once_per.db"
    except RuntimeError:
        return None


def _ensure_schema(conn: Any) -> None:
    """
    Ensure *conn*'s ``claims`` table matches :data:`_SCHEMA_VERSION`.

    Checked via ``PRAGMA user_version`` rather than ``CREATE TABLE IF NOT
    EXISTS`` alone: against a differently-shaped existing table, that
    statement is a silent no-op, and every later statement raises into the
    fail-soft handlers -- disabling throttling permanently and silently.

    Three cases, by comparing the stored version to ours:

    - Equal: heal only -- ``CREATE TABLE IF NOT EXISTS``, in case the table
      itself went missing while the version header survived (e.g. an
      external ``DROP TABLE``), then return.
    - Lower: drop and recreate. By far the more common way here is a brand
      new file, whose version defaults to 0; more rarely, a genuinely older
      store. This is disposable claim state, never user data, so recreating
      on a shape change, or creating for the first time, is correct and
      deliberately not a migration.
    - Higher (a newer build's store): raise rather than touch it, standing
      down instead of destroying data a newer, possibly still-running build
      depends on.

    Deliberately does NOT commit -- :func:`claim` runs this inside an
    explicit ``BEGIN IMMEDIATE`` transaction it manages itself, atomically
    with the insert it guards, and commits once both have run. A plain
    ``with conn:`` is not enough: PRAGMA and DDL statements run in
    sqlite3's own autocommit mode regardless of that wrapper, which only
    opens an implicit transaction before a DML statement -- so without the
    explicit BEGIN, this function's DROP+CREATE
    would commit on its own, ahead of the insert, leaving a window where a
    second, concurrently-racing first-ever claim() could see the
    just-repaired schema, repeat the no-op DROP+CREATE -- but still a fresh
    empty table -- and wipe the first claim's row before its own insert
    landed.
    """
    current_version = conn.execute("PRAGMA user_version").fetchone()[0]
    if current_version > _SCHEMA_VERSION:
        raise sqlite3.OperationalError(
            f"claim store schema version {current_version} is newer "
            f"than this build's {_SCHEMA_VERSION}; standing down"
        )
    if current_version == _SCHEMA_VERSION:
        conn.execute(f"CREATE TABLE IF NOT EXISTS claims ({_CLAIMS_TABLE_COLUMNS})")
        return
    conn.execute("DROP TABLE IF EXISTS claims")
    conn.execute(f"CREATE TABLE claims ({_CLAIMS_TABLE_COLUMNS})")
    conn.execute(f"PRAGMA user_version = {_SCHEMA_VERSION}")


def _connect() -> Any:
    """
    Open the shared claim database, creating ``~/.toolguard/`` on demand.

    Return type is ``Any``: with ``sqlite3`` possibly ``None`` at import
    time, there is no valid ``Connection`` type to annotate.

    Does not touch the schema -- :func:`claim` runs :func:`_ensure_schema`
    itself, inside its own transaction. Nothing here can raise after the
    connection is created, so this function itself needs no ``try``/``finally``.

    Raises ``OSError`` if the store path cannot be resolved (see
    :func:`_resolve_store_path`) -- callers already catch ``OSError`` as
    part of their fail-soft handling.
    """
    path = _resolve_store_path()
    if path is None:
        raise OSError("claim store home directory could not be resolved")
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(path), timeout=5.0)


def _connect_existing() -> Any:
    """
    Open the shared claim database read/write without creating anything.

    Returns ``None`` when the store path can't be resolved, or the database
    file doesn't exist yet -- nothing has ever been claimed, so there is
    nothing to read or clean up. Opens with sqlite3's ``mode=rw`` URI option
    so a concurrent delete between the existence check and the connect
    raises ``sqlite3.Error`` (which every caller already catches) instead
    of creating a fresh, table-less file in its place.

    Built via ``Path.as_uri()`` rather than plain string interpolation:
    SQLite treats the first raw ``?`` in a URI path as the query delimiter,
    so a literal ``?`` would silently truncate the filename there (dropping
    ``mode=rw``, reopening the exact hole it exists to close), and a
    literal ``%`` would be misread as a percent-escape -- ``as_uri()``
    percent-encodes both.

    See :func:`_connect` for why the return type is ``Any``.
    """
    path = _resolve_store_path()
    if path is None or not path.exists():
        return None
    return sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=5.0)


def is_claimed(project: Optional[Path], kind: str, scope: str) -> bool:
    """
    Read-only check: is ``(project, kind, scope)`` currently claimed and still live?

    Never creates the database -- a missing one just means "not claimed".
    This is an optimisation only: it is not atomic, so :func:`claim` remains
    the correctness mechanism for the actual race. Fails soft to ``False``
    (proceed) on any storage error, a ``None`` project, or a missing
    ``sqlite3``.

    Args:
        project: The project-root path this claim is about, or None if
            unresolved (then always False -- nothing is ever stored for it).
        kind: Caller-owned category being throttled.
        scope: Opaque throttling window, e.g. :func:`day_scope`.
    """
    if sqlite3 is None or project is None:
        return False
    conn = None
    try:
        conn = _connect_existing()
        if conn is None:
            return False
        with conn:
            row = conn.execute(
                "SELECT expires_at FROM claims WHERE project = ? AND kind = ? AND scope = ?",
                (_project_key(project), kind, scope),
            ).fetchone()
        if row is None:
            return False
        return datetime.fromisoformat(row[0]) >= datetime.now()
    except _READ_ERRORS:
        # ValueError/TypeError: a malformed or non-string expires_at (a
        # hand edit, or a different schema sharing this file) is treated
        # as an expired claim rather than raised.
        return False
    finally:
        if conn is not None:
            conn.close()


def claim(
    project: Optional[Path], kind: str, scope: str, ttl: timedelta
) -> ClaimResult:
    """
    Atomically claim ``(project, kind, scope)`` for *ttl*, reporting the outcome per call.

    Returns :attr:`ClaimStatus.CLAIMED` when this call holds the claim -- it
    inserted a fresh row, or reclaimed one whose ``expires_at`` had already
    passed -- meaning the caller should proceed.

    Returns :attr:`ClaimStatus.HELD_BY_SOMEONE_ELSE` when another, still-live
    claim already exists -- a normal, expected outcome; the caller should
    stay quiet.

    Returns :attr:`ClaimStatus.UNGUARANTEED`, with a ``reason``, when the
    once-per-period guarantee could not itself be verified for this call:
    ``sqlite3`` is missing, *project* is ``None``, or a storage error
    occurred. Deliberately not folded into "proceed" or "held" -- a caller
    whose action is unsafe to repeat needs to tell "I hold the claim" apart
    from "the guarantee could not be verified this time", which one boolean
    cannot express.

    A single ``INSERT ... ON CONFLICT DO UPDATE ... WHERE`` avoids a
    separate check-then-create race: two racing processes can't both win,
    as long as the store itself is healthy. Ordinary contention just waits
    (``timeout=5.0`` on connect); only if that busy timeout is exceeded does
    it surface as a ``sqlite3.Error``, and the fail-soft path below returns
    UNGUARANTEED regardless -- the guarantee holds only while the store is
    healthy.

    The caller decides WHEN to call this: to actually gate a race, it must
    be the last thing before the side effect being deduplicated, not called
    up front "just in case" -- see :func:`is_claimed` for a cheap read-only
    pre-check that doesn't hold anything.

    Never raises: storage failures report as UNGUARANTEED rather than
    propagating.

    Args:
        project: The project-root path this claim is about, or None if
            unresolved.
        kind: Caller-owned category being throttled.
        scope: Opaque throttling window, e.g. ``day_scope()``.
        ttl: How long this claim remains valid before it may be reclaimed.
    """
    if sqlite3 is None:
        return ClaimResult(ClaimStatus.UNGUARANTEED, _REASON_NO_SQLITE)
    if project is None:
        return ClaimResult(ClaimStatus.UNGUARANTEED, _REASON_NO_PROJECT)
    now = datetime.now()
    expires_at = now + ttl
    conn = None
    try:
        conn = _connect()
        # BEGIN IMMEDIATE, not `with conn:` -- keeps _ensure_schema's repair
        # and this insert in one real transaction; see that function's
        # docstring for why `with conn:` alone is not enough.
        conn.execute("BEGIN IMMEDIATE")
        _ensure_schema(conn)
        cur = conn.execute(
            "INSERT INTO claims (project, kind, scope, created_at, expires_at) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(project, kind, scope) DO UPDATE SET "
            "created_at = excluded.created_at, "
            "expires_at = excluded.expires_at "
            "WHERE claims.expires_at < excluded.created_at",
            (
                _project_key(project),
                kind,
                scope,
                now.isoformat(),
                expires_at.isoformat(),
            ),
        )
        conn.commit()
        if cur.rowcount > 0:
            return ClaimResult(ClaimStatus.CLAIMED)
        return ClaimResult(ClaimStatus.HELD_BY_SOMEONE_ELSE)
    except _STORAGE_ERRORS:
        return ClaimResult(ClaimStatus.UNGUARANTEED, _REASON_STORAGE_ERROR)
    finally:
        if conn is not None:
            conn.close()


def release(project: Optional[Path], kind: str, scope: str) -> None:
    """
    Give up a claim early so a later attempt this period can retry.

    Never creates storage; a claim that was never taken has nothing to
    release. Fails soft: storage errors, a ``None`` project, or a missing
    ``sqlite3`` are all swallowed.
    """
    if sqlite3 is None or project is None:
        return
    conn = None
    try:
        conn = _connect_existing()
        if conn is None:
            return
        with conn:
            conn.execute(
                "DELETE FROM claims WHERE project = ? AND kind = ? AND scope = ?",
                (_project_key(project), kind, scope),
            )
    except _STORAGE_ERRORS:
        pass
    finally:
        if conn is not None:
            conn.close()


def reap(logs_dir: Path) -> None:
    """
    Delete expired claims, and sweep legacy per-project/per-kind artefacts.

    Expiry is a timestamp comparison against the stored ``expires_at`` --
    never a filename parse. The sweep is global, across every project: it
    only ever removes claims already past their TTL.

    Also sweeps, unconditionally on sight: :data:`_LEGACY_STORE_FILENAME`,
    and, under *logs_dir*, the legacy per-kind marker files
    (:data:`_LEGACY_MARKER_PREFIXES`) plus a stale
    :data:`_LEGACY_PROJECT_DB_FILENAME`. Nothing creates any of these
    anymore, so no date parsing or format detection is needed to decide
    whether one is old enough to remove.

    Never creates storage. Fails soft throughout.
    """
    if sqlite3 is not None:
        conn = None
        try:
            conn = _connect_existing()
            if conn is not None:
                with conn:
                    conn.execute(
                        "DELETE FROM claims WHERE expires_at < ?",
                        (datetime.now().isoformat(),),
                    )
        except _STORAGE_ERRORS:
            pass
        finally:
            if conn is not None:
                conn.close()

    store_path = _resolve_store_path()
    if store_path is not None:
        try:
            (store_path.parent / _LEGACY_STORE_FILENAME).unlink()
        except OSError:
            pass

    if not logs_dir.exists():
        return
    for prefix in _LEGACY_MARKER_PREFIXES:
        try:
            legacy_files = list(logs_dir.glob(f"{prefix}*"))
        except OSError:
            continue
        for marker_file in legacy_files:
            try:
                marker_file.unlink()
            except OSError:
                continue
    try:
        (logs_dir / _LEGACY_PROJECT_DB_FILENAME).unlink()
    except OSError:
        pass
