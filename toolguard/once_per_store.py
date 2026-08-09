"""
Cross-project ``(project, kind, scope)`` claim store backing "once per
period" behaviour.

This is a private implementation detail (TOO-45 punch-list #01, conceptual
overhaul): the only caller is :mod:`toolguard.once_per`, which presents
``claim``/``scope``/``sqlite`` mechanics to nobody -- its named per-thing
objects (e.g. ``once_per.day("key", "description")``) take a project and a
message/action, nothing more. Production code outside this module and
:mod:`toolguard.once_per` must never import this module directly.

Storage is toolguard's OWN state, at ``~/.toolguard/once_per.db`` -- never
inside a project directory, matching :data:`toolguard.error_log`'s
``~/.toolguard/errors/`` and :data:`toolguard.tools.decision_ledger
.USER_LEDGER_PATH`'s ``~/.toolguard/decisions.json``. Because the store is
shared across every project, isolation lives in the KEY instead of the file
location: every claim is keyed on ``(project, kind, scope)``, where
``project`` is the resolved project-root path (as ``str``, so the row stays
readable when someone inspects the database by hand). ``project`` is
``None`` when no project root could be resolved.

Schema: one table ``claims(project, kind, scope, created_at, expires_at)``,
primary keyed on ``(project, kind, scope)``, with real timestamp columns --
expiry is a comparison, never a filename parse.

``scope`` is an OPAQUE, namespaced string, owned by :mod:`toolguard.once_per`.
Today only ``"day:YYYY-MM-DD"`` (see :func:`day_scope`); a future
session-scoped period adds a new scope prefix (e.g. ``"session:<id>"``),
never a new mechanism. ``kind`` distinguishes what is being throttled; also
owned by :mod:`toolguard.once_per` -- this module has no opinion on the
domain vocabulary.

Every write is fail-soft: a broken or unwritable store must never break a
permission decision, and :func:`claim` never raises. But "fail soft" is NOT
"always report success": :func:`claim` reports its outcome PER CALL via
:class:`ClaimResult` -- ``CLAIMED``, ``HELD_BY_SOMEONE_ELSE``, or
``UNGUARANTEED`` (with a ``reason``) -- so a caller whose action is unsafe to
repeat can tell "I hold the claim" apart from "the guarantee could not be
verified this time" instead of both collapsing into one ambiguous ``True``.
Only :func:`claim` may create ``~/.toolguard/`` or the database -- every
other function here is read-only or best-effort cleanup and must never
create storage that a caller with nothing to report would otherwise never
have touched.

The store path is resolved LAZILY (:func:`_resolve_store_path`), never at
import time: this module is on the hook's import path (via
:mod:`toolguard.once_per`), and a module-level ``Path.home()`` call would
make the whole hook fail to import -- silently, with no exit code 2 -- on a
container/CI shape with no ``HOME`` and no passwd entry.
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

#: Fail-soft storage errors every store-touching function catches. Named,
#: rather than an inline unparenthesized except-tuple: pyscn's parser
#: doesn't yet support Python 3.14's unparenthesized multi-exception except
#: clauses, and ruff's formatter strips the parens off one whenever it's
#: written inline, so a literal tuple here always ends up unparenthesized
#: again (see test_pyscn_reports_no_parse_failures).
_STORAGE_ERRORS = (OSError, sqlite3.Error) if sqlite3 is not None else (OSError,)

#: is_claimed additionally treats a malformed or non-string stored
#: timestamp as expired rather than raising -- see its docstring (TOO-45 D2).
_READ_ERRORS = _STORAGE_ERRORS + (ValueError, TypeError)

#: Test-patchable override for the store path (``patch.object(once_per_store,
#: "_STORE_PATH", ...)``). ``None`` means "use the default", resolved by
#: :func:`_resolve_store_path`. Never read directly outside this module;
#: :mod:`toolguard.testing.sandbox` and every store-touching function here
#: go through that resolver instead.
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

#: Legacy per-project claim db this module wrote directly under a project's
#: logs_dir before storage moved to ~/.toolguard/ (TOO-45 R2). Nothing writes
#: this anymore; reap() removes it on sight, like the marker-file prefixes
#: below.
_LEGACY_PROJECT_DB_FILENAME = ".toolguard-suppression.db"

#: This store's OWN previous filename, before the "suppression" language was
#: retired (TOO-45 punch-list #01). A sibling of the current store path;
#: reap() removes it on sight, disposable state like everything else here.
_LEGACY_STORE_FILENAME = "suppression.db"

#: Legacy per-kind marker-file prefixes this module's claim store replaces.
#: Nothing writes these anymore; reap() sweeps any that linger from before
#: the upgrade. This is the one place a filename glob is still correct --
#: these are someone else's (the old code's) format, not this module's.
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
    composing a degraded-mode notice. This module never asserts WHY on the
    caller's behalf beyond that phrase, and never repeats a specific storage
    technology's name outside this reason -- see the reason constants below.
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
    otherwise computes ``~/.toolguard/once_per.db`` FRESH on every call
    (never cached at module scope, and never memoised here either): this is
    what lets a store-touching call correctly pick up whatever ``$HOME`` is
    live for the current process, which is how :mod:`toolguard.testing
    .sandbox`'s child-process isolation (setting ``HOME`` in the subprocess
    environment) and every test's ``patch.object(once_per_store,
    "_STORE_PATH", ...)`` both keep working with the same mechanism.

    Returns ``None`` -- "store unavailable" -- if ``Path.home()`` cannot be
    resolved (e.g. no ``HOME`` and no passwd entry for the uid, an ordinary
    container/CI shape). Every caller in this module must treat ``None`` the
    same as any other storage error: fail soft, never raise.
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
    EXISTS`` alone: against a differently-shaped existing table (or a brand
    new file, whose version defaults to 0) that statement is a silent no-op,
    and every later statement raises into the fail-soft handlers --
    disabling throttling permanently and silently.

    Three cases, by comparing the stored version to ours:

    - Equal: heal only -- ``CREATE TABLE IF NOT EXISTS``, in case the table
      itself went missing while the version header survived (e.g. an
      external ``DROP TABLE``), then return.
    - Lower (a genuinely older store): drop and recreate. This is disposable
      claim state, never user data, so recreating on a shape change is
      correct and deliberately not a migration.
    - Higher (a NEWER build's store): raise rather than touch it. This
      process is not the one that owns that shape, so it stands down --
      degrading to unavailable for this claim -- instead of destroying data
      a newer, possibly still-running build depends on.

    Deliberately does NOT commit -- :func:`claim`, the only caller, runs
    this inside an explicit ``BEGIN IMMEDIATE`` transaction it manages
    itself, atomically with the insert it guards, and commits once both
    have run. A plain ``with conn:`` is NOT enough for this: PRAGMA and DDL
    statements (verified empirically against this project's Python/sqlite3)
    execute in sqlite3's own autocommit mode regardless of Python's `with
    conn:` wrapper, which only opens an implicit transaction before a DML
    statement -- so without the explicit BEGIN, this function's DROP+CREATE
    commits on its own, separately from the insert that follows it. That
    left a window where a second, concurrently-racing first-ever claim()
    could see the just-fixed schema, "fix" it again (a no-op DROP+CREATE,
    but still a fresh empty table), and wipe the first claim's row before
    its own insert landed -- reproduced via two real OS processes racing a
    brand-new store file
    (test_concurrent_claim_from_two_processes_only_one_wins) during
    development of this fix.
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
    time, there is no valid ``Connection`` type to annotate. Only
    :func:`claim` calls this -- it is the sole function allowed to create
    ``~/.toolguard/`` or the database file.

    Does NOT touch the schema -- :func:`claim` runs :func:`_ensure_schema`
    itself, inside its own transaction (see that function's docstring for
    why). Assigning the returned connection to the CALLER's own variable
    before anything schema- or write-related can raise is what keeps a
    later failure from leaking the connection: nothing here can raise after
    a connection is created, so there is nothing for this function itself
    to clean up.

    Raises ``OSError`` if the store path cannot be resolved at all (see
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
    Open the shared claim database read/write WITHOUT creating anything.

    Returns ``None`` when the store path can't be resolved, or the database
    file doesn't exist yet -- nothing has ever been claimed, so there is
    nothing to read or clean up. Opens with sqlite3's ``mode=rw`` URI option
    so a concurrent delete between the existence check and the connect can
    never create a fresh, table-less file in its place -- it raises
    ``sqlite3.Error`` instead, which every caller already catches.

    Built via ``Path.as_uri()`` rather than plain string interpolation:
    SQLite treats the first raw ``?`` in a URI path as the query delimiter,
    so a literal ``?`` in the path would silently truncate the filename
    there (and drop ``mode=rw``, reopening the exact hole it exists to
    close) and a literal ``%`` would be misread as a percent-escape --
    ``as_uri()`` percent-encodes both.

    Used by every function except :func:`claim`. See :func:`_connect` for
    why the return type is ``Any``.
    """
    path = _resolve_store_path()
    if path is None or not path.exists():
        return None
    return sqlite3.connect(f"{path.as_uri()}?mode=rw", uri=True, timeout=5.0)


def is_claimed(project: Optional[Path], kind: str, scope: str) -> bool:
    """
    Read-only check: is ``(project, kind, scope)`` currently claimed and still live?

    Never creates the database -- a missing one just means "not claimed".
    This is an optimisation only, letting a caller skip its analysis work on
    an already-warned day; the atomic :func:`claim` remains the correctness
    mechanism for the actual race. Fails soft to ``False`` (proceed) on any
    storage error, a ``None`` project, or a missing ``sqlite3``.

    Args:
        project: Resolved project-root path this claim is about, or None if
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
        # ValueError/TypeError: a malformed or non-string expires_at (hand
        # edit, or another toolguard build sharing this file with a
        # different schema) is treated as an expired claim, never raised --
        # this runs on every tool call via check_and_warn_divergence, and
        # nothing upstream catches it (TOO-45 D2).
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
    once-per-period guarantee could not itself be verified for THIS call:
    ``sqlite3`` is missing, *project* is ``None`` (no project root could be
    resolved), or a storage error occurred. This is deliberately NOT folded
    into "proceed" or "held" -- a caller whose action is unsafe to repeat
    (see :class:`toolguard.once_per.Repeat`) needs to be able to tell
    "I hold the claim" apart from "the guarantee could not be verified this
    time", which collapsing both into one boolean cannot express (TOO-45
    punch-list #01: this replaced an earlier design where ``project=None``
    silently returned the same value as a genuine claim, defeating a
    caller's fail-closed policy every single call).

    A single ``INSERT ... ON CONFLICT DO UPDATE ... WHERE`` closes the
    check-then-create race the old marker-file pattern had, as long as the
    store itself is healthy: two racing processes can't both win. Under
    contention that surfaces as a ``sqlite3.Error`` (e.g. a locked
    database), the fail-soft path below returns UNGUARANTEED regardless, so
    a caller with a safe-to-repeat policy may still proceed -- the guarantee
    holds only while the store is healthy.

    The caller decides WHEN to call this: to actually gate a race, it must
    be the last thing before the side effect being deduplicated, not called
    up front "just in case" -- see :func:`is_claimed` for a cheap read-only
    pre-check that doesn't hold anything.

    Never raises: every failure mode reports as UNGUARANTEED rather than
    propagating -- a broken or unavailable claim store must never block a
    permission decision.

    Args:
        project: Resolved project-root path this claim is about, or None if
            unresolved.
        kind: Caller-owned category being throttled (e.g. a module's own
            "takeover_warning" constant).
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
        # BEGIN IMMEDIATE, not `with conn:` -- PRAGMA and DDL statements
        # (inside _ensure_schema) run in sqlite3's own autocommit mode
        # regardless of Python's `with conn:` wrapper, which only opens an
        # implicit transaction before a DML statement. An explicit BEGIN
        # keeps schema repair and the insert in ONE real transaction, which
        # is what actually closes the race (verified empirically -- `with
        # conn:` alone did not, see _ensure_schema's docstring).
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

    For a caller whose claimed side effect itself failed (e.g. a migration
    that raised or returned a failure code), so "once per period" applies
    to successes only. Never creates storage; a claim that was never taken
    has nothing to release. Fails soft: storage errors, a ``None`` project,
    or a missing ``sqlite3`` are all swallowed.
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
    never a filename parse. The expiry sweep is GLOBAL, across every
    project: pure housekeeping on rows already past their TTL never
    reintroduces cross-project bleed, since it only ever removes claims no
    project could still be relying on.

    Also sweeps, unconditionally on sight: this store's own previous
    filename (``~/.toolguard/suppression.db``, a sibling of the current
    store path, from before TOO-45 punch-list #01 retired the "suppression"
    language), and, under *logs_dir*, the legacy per-kind marker files
    (``.toolguard-warned-*`` / ``.toolguard-migration-*`` /
    ``.toolguard-divergence-warned-*``) the original marker-file mechanism
    left behind, plus a stale ``.toolguard-suppression.db`` from this
    module's earlier, since-reversed per-project storage format. Nothing
    creates any of these anymore, so no date parsing or format detection is
    needed to decide whether one is old enough to remove.

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
