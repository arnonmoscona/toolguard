"""
Self-protection gate for every toolguard config-file write.

``toolguard_hook.toml``/``.json`` and the native Claude settings files are usually not
tracked anywhere else on a developer's machine, so a write that produces text this project
cannot parse back leaves that file broken with no way back: toolguard skips it and clamps
every governed decision, other than an already-``deny`` one, to ``ask`` until it is fixed.

This module is the only place a toolguard config write is allowed to happen: parse the
candidate text first (:func:`verify_config_text`), optionally confirm no existing rule
pattern is about to be silently dropped (:func:`verified_write_config`'s
``expected_patterns`` check), and only then write -- atomically, so a crash mid-write can
never leave a half-written file on disk either.

Leaf module by design: imports only the Python standard library and nothing else from
``toolguard``, so every writer can depend on this module without risking a circular import
-- see ``test.unit.test_architecture``'s ``LAYERS`` for the enforced layering. A structured
entry's pattern key ("match") is therefore a small literal constant duplicated here rather
than imported from :data:`toolguard.rule_entry.PATTERN_KEY`.
"""

import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Iterable, Optional, Union

#: Structured entry's pattern key, e.g. ``{ match = "Bash(git *)", ... }``.
_PATTERN_KEY = "match"

#: The ``permissions`` table's three sub-lists scanned for existing rule
#: patterns (see :func:`_patterns_in_parsed`).
_PERMISSIONS_LIST_TYPES = ("allow", "deny", "ask")

#: ``permissions`` sub-lists that restrict a command, vs. ``allow`` /
#: ``hard_deny.allow``, which loosen it -- both tables use the literal key
#: ``"allow"`` for their sole loosening list (see
#: :func:`verified_write_config` step 3).
_RESTRICTING_LIST_TYPES = ("deny", "ask")
_ALLOW_LIST_TYPES = ("allow",)

#: The only ``hard_deny`` sub-list the runtime treats as restricting --
#: ``Configuration._pool_hard_deny_entries`` reads exactly ``deny`` and
#: ``allow`` and nothing else. Used, unlike :data:`_RESTRICTING_LIST_TYPES`
#: above, as an explicit include-list rather than a generic by-key scan, so
#: an unrecognised or renamed sub-list is read as having left ``hard_deny``
#: rather than as still protecting anything (see :func:`_hard_deny_patterns`).
_HARD_DENY_RESTRICTING_LIST_TYPES = ("deny",)


class ConfigWriteVerificationError(Exception):
    """
    Raised when text about to be written to a config file fails verification.

    The original file on disk is always left untouched when this is raised --
    every check this module performs happens BEFORE any write is attempted
    (see :func:`verified_write_config`).

    Attributes:
        path: The config file path the write was refused for, or ``None``
            when the caller invoked :func:`verify_config_text` directly
            without supplying one.
        reason: Short machine-stable category of the failure, e.g.
            ``"invalid TOML"`` or ``"write would drop existing rule
            pattern(s)"``.
        message: The underlying parser's error message, or the list of
            missing patterns, giving the actionable detail.
    """

    def __init__(
        self, path: Optional[Union[str, Path]], reason: str, message: str
    ) -> None:
        self.path = path
        self.reason = reason
        self.message = message
        location = f" for {path}" if path is not None else ""
        super().__init__(f"refusing to write config{location}: {reason} -- {message}")


def _parse(text: str, file_format: str) -> object:
    """
    Parse *text* as either TOML or JSON, letting the underlying parser's
    exception propagate to the caller.

    Args:
        text: Raw config file text to parse.
        file_format: ``'toml'`` or ``'json'``.

    Returns:
        The parsed value (normally a ``dict`` for a well-formed config file,
        but this function does not itself enforce that shape).

    Raises:
        tomllib.TOMLDecodeError: ``file_format`` is ``'toml'`` and ``text`` is
            not valid TOML.
        json.JSONDecodeError: ``file_format`` is ``'json'`` and ``text`` is
            not valid JSON.
        ValueError: ``file_format`` is neither ``'toml'`` nor ``'json'``.
    """
    if file_format == "toml":
        return tomllib.loads(text)
    if file_format == "json":
        return json.loads(text)
    raise ValueError(f"unknown file_format {file_format!r} (expected 'toml' or 'json')")


def verify_config_text(
    text: str, file_format: str, path: Optional[Union[str, Path]] = None
) -> None:
    """
    Parse *text* and raise if it does not parse as a TOML/JSON top-level
    object/table.

    Pure syntax and shape check -- no I/O, and it does not look at what the
    parsed content contains (:func:`verified_write_config` adds the separate
    content-loss check on top of this).

    Args:
        text: The candidate config file text.
        file_format: ``'toml'`` or ``'json'``.
        path: Optional path to attach to the raised error for a more useful
            message.

    Raises:
        ConfigWriteVerificationError: ``text`` fails to parse as
            ``file_format``, or parses to something other than a top-level
            object/table (e.g. a bare JSON array, string or number -- TOML
            has no such shape).
        ValueError: ``file_format`` is neither ``'toml'`` nor ``'json'``.
    """
    try:
        parsed = _parse(text, file_format)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        raise ConfigWriteVerificationError(
            path=path,
            reason=f"invalid {file_format.upper()}",
            message=str(e),
        ) from e
    if not isinstance(parsed, dict):
        raise ConfigWriteVerificationError(
            path=path,
            reason="not a top-level object/table",
            message=f"parsed to {type(parsed).__name__}, expected an object/table",
        )


def _entry_pattern(entry: object) -> Optional[str]:
    """
    Extract a permission entry's pattern string, plain or structured.

    Args:
        entry: One element of a ``permissions``/``hard_deny`` list, as parsed
            from TOML/JSON -- normally a ``str`` (plain pattern) or a ``dict``
            (structured entry, pattern under :data:`_PATTERN_KEY`).

    Returns:
        The pattern string, or ``None`` when ``entry`` is neither shape, or a
        structured entry has no (string) pattern key.
    """
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        match = entry.get(_PATTERN_KEY)
        if isinstance(match, str):
            return match
    return None


def _collect_patterns(entries: Iterable[object]) -> set:
    """Extract every pattern string from an iterable of permission-list entries."""
    patterns: set = set()
    for entry in entries:
        pattern = _entry_pattern(entry)
        if pattern is not None:
            patterns.add(pattern)
    return patterns


def _table_lists_patterns(parsed: object, table: str, list_types: Iterable[str]) -> set:
    """
    Collect rule patterns from specific sub-lists of one top-level table.

    Args:
        parsed: The parsed config structure (normally a ``dict``; any other
            top-level shape, or a missing/malformed *table*, simply yields
            an empty set).
        table: Top-level table name, e.g. ``"permissions"`` or ``"hard_deny"``.
        list_types: Which of *table*'s sub-lists to scan, e.g. ``("deny", "ask")``.
            A sub-list whose value is not a list (missing, ``null``, or a
            malformed scalar/string) contributes nothing rather than raising.

    Returns:
        Set of every pattern string found across those lists.
    """
    if not isinstance(parsed, dict):
        return set()

    section = parsed.get(table)
    if not isinstance(section, dict):
        return set()

    patterns: set = set()
    for list_type in list_types:
        value = section.get(list_type)
        if isinstance(value, list):
            patterns |= _collect_patterns(value)
    return patterns


def _patterns_in_parsed(parsed: object) -> set:
    """
    Collect every rule pattern present in a parsed config structure.

    Scans ``permissions.allow``/``permissions.deny``/``permissions.ask`` and
    every list-valued entry under ``hard_deny`` (checked generically by key,
    not hardcoded to ``deny``/``allow``, so a future ``hard_deny`` list is
    covered without a change here). Accepts both plain-string entries and
    structured ``{match = ...}`` entries (see :func:`_entry_pattern`).

    Args:
        parsed: The parsed config structure (normally a ``dict``; any other
            top-level shape simply yields an empty set).

    Returns:
        Set of every pattern string found.
    """
    return _table_lists_patterns(
        parsed, "permissions", _PERMISSIONS_LIST_TYPES
    ) | _hard_deny_patterns(parsed)


def _hard_deny_patterns(parsed: object, *, exclude: Iterable[str] = ()) -> set:
    """
    Collect rule patterns present under a parsed config's ``hard_deny``
    table, in isolation from ``permissions`` (see :func:`_patterns_in_parsed`
    for the combined set).

    Scans every list-valued entry generically by key rather than an
    explicit include-list, so an unrecognised or renamed sub-list still
    counts as PRESENT here, never silently dropped -- fail-closed for "does
    this config still LOOK like it is protecting this pattern". See
    :func:`_hard_deny_egress_violations` for why that reading is too
    permissive for a runtime-effect check on its own.

    Args:
        parsed: The parsed config structure (normally a ``dict``; any other
            top-level shape simply yields an empty set).
        exclude: Sub-list keys to skip, e.g. the ``allow`` carve-out.

    Returns:
        Set of every pattern string found under ``hard_deny``, minus any
        sub-list named in *exclude*.
    """
    if not isinstance(parsed, dict):
        return set()

    hard_deny = parsed.get("hard_deny")
    if not isinstance(hard_deny, dict):
        return set()

    patterns: set = set()
    for key, value in hard_deny.items():
        if key in exclude or not isinstance(value, list):
            continue
        patterns |= _collect_patterns(value)
    return patterns


def _atomic_write(path: Path, text: str) -> None:
    """
    Write *text* to *path* atomically: sibling temp file, fsync, then rename.

    Writes to a temporary file in *path*'s own parent directory (same
    filesystem -- :func:`os.replace` fails across devices), flushes and
    calls :func:`os.fsync` before renaming, so a crash mid-write leaves
    *path* holding either its old complete content or the new complete
    content, never a partial write. The temporary file is removed if any
    step fails. *path*'s parent directory is created first if it does not
    already exist.

    Args:
        path: Destination file path.
        text: Text to write.

    Raises:
        OSError: The temp file could not be created, written, or renamed.
    """
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        dir=directory, prefix=f".{path.name}.", suffix=".tmp"
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def patterns_in_config_text(text: str, file_format: str) -> set:
    """
    Parse *text* and return every rule pattern it contains.

    Lets a caller compute ``expected_patterns`` (see
    :func:`verified_write_config`) from an EXISTING on-disk file's text,
    rather than from the in-memory data it is about to write -- e.g. before
    an edit that only touches one section and must not let patterns
    elsewhere in the file silently vanish.

    Args:
        text: Config file text to parse (normally freshly read from disk).
        file_format: ``'toml'`` or ``'json'``.

    Returns:
        Set of every rule pattern found under ``permissions``/``hard_deny``
        (see :func:`_patterns_in_parsed`); empty if *text* parses to a
        non-``dict`` value or has neither table.

    Raises:
        tomllib.TOMLDecodeError: ``file_format`` is ``'toml'`` and ``text``
            is not valid TOML.
        json.JSONDecodeError: ``file_format`` is ``'json'`` and ``text`` is
            not valid JSON.
        ValueError: ``file_format`` is neither ``'toml'`` nor ``'json'``.
    """
    return _patterns_in_parsed(_parse(text, file_format))


def _hard_deny_egress_violations(
    original_parsed: object, parsed: object, expected: set
) -> list:
    """
    Patterns effectively hard-denied in *original_parsed* that would no
    longer be effectively hard-denied in *parsed*, restricted to *expected*
    -- the same patterns step 2's content-loss check is enforcing, so a
    pattern the caller never asked this write to preserve (e.g. one this
    write intentionally migrates out to a different file) is not flagged
    just because it no longer appears here.

    "Effectively denied" is judged asymmetrically on purpose: the BEFORE
    snapshot scans every ``hard_deny`` sub-list generically by key
    (fail-closed -- an unrecognised or renamed list still counts as
    protecting), while the AFTER snapshot only counts
    :data:`_HARD_DENY_RESTRICTING_LIST_TYPES` (``deny``), matching what
    ``Configuration._pool_hard_deny_entries`` actually reads at runtime. A
    pattern moved to an unrecognised sub-list therefore reads as having
    left ``hard_deny`` rather than as still protected.

    Both snapshots compare PATTERN STRINGS, not match-time effect: a
    ``hard_deny.allow`` carve-out that matches the denied pattern through
    broader rule syntax rather than an identical string -- e.g. denying
    ``Bash(curl http://evil:*)`` then carving out ``Bash(curl:*)`` -- is not
    detected, and neither is a carve-out added to a DIFFERENT config file,
    since ``hard_deny`` pools across every toolguard_hook layer at runtime
    but this comparison only ever sees one file. Catching either needs the
    matcher, which this function deliberately does not invoke.

    Returns:
        Sorted list of pattern strings that would lose hard_deny protection.
    """
    before = (
        _hard_deny_patterns(original_parsed, exclude=_ALLOW_LIST_TYPES)
        - _table_lists_patterns(original_parsed, "hard_deny", _ALLOW_LIST_TYPES)
    ) & expected
    after = _table_lists_patterns(
        parsed, "hard_deny", _HARD_DENY_RESTRICTING_LIST_TYPES
    ) - _table_lists_patterns(parsed, "hard_deny", _ALLOW_LIST_TYPES)
    return sorted(before - after)


def _permissions_downgrade_violations(
    original_parsed: object, parsed: object, expected: set
) -> list:
    """
    Patterns that leave ``permissions.deny``/``permissions.ask`` and end up
    restricted NOWHERE -- neither still in ``permissions.deny``/``ask`` nor
    picked up by ``hard_deny.deny``. Destination-agnostic on purpose: ending
    up in ``permissions.allow``, in ``hard_deny.allow`` (a carve-out, not a
    restriction), or in an unrecognised sub-list toolguard's runtime does
    not read are all the same loss. Restricted to *expected* for the same
    reason as :func:`_hard_deny_egress_violations`.

    A pattern kept in ``deny``/``ask`` while also added to ``allow`` is
    fine (deny/ask still wins at the same level); moving from ``deny`` to
    ``ask`` or back is fine too, and so is picking up a ``hard_deny.deny``
    entry -- unlike a ``hard_deny.allow`` carve-out, ``ask`` and
    ``hard_deny.deny`` are both still enforced, so neither move is the loss
    this function exists to catch.

    Same string-only ceiling as :func:`_hard_deny_egress_violations`: a
    pattern staying in ``permissions.ask`` while a DIFFERENT, more specific
    pattern is added to ``permissions.allow`` (e.g. ``ask`` keeps
    ``Bash(git push:*)`` while ``allow`` gains ``Bash(git push origin:*)``)
    is the same class of gap and is not detected here either.

    Returns:
        Sorted list of pattern strings no longer restricted anywhere.
    """
    restricting_before = (
        _table_lists_patterns(original_parsed, "permissions", _RESTRICTING_LIST_TYPES)
        & expected
    )
    still_restricting_after = _table_lists_patterns(
        parsed, "permissions", _RESTRICTING_LIST_TYPES
    ) | _table_lists_patterns(parsed, "hard_deny", _HARD_DENY_RESTRICTING_LIST_TYPES)
    return sorted(restricting_before - still_restricting_after)


def verified_write_config(
    path: Union[str, Path],
    text: str,
    file_format: str,
    *,
    expected_patterns: Optional[Iterable[str]] = None,
) -> None:
    """
    Verify *text*, then atomically write it to *path*. Refuses on any failure.

    Steps, in order, leaving *path* untouched on disk if any of them fails:

    1. :func:`verify_config_text` -- *text* must parse as *file_format*.
    2. If *expected_patterns* is not ``None``: every pattern in it must still
       be present in *text*'s parsed ``permissions``/``hard_deny`` structure
       (see :func:`_patterns_in_parsed`). A missing pattern means this write
       would silently DELETE a rule -- refused.
    3. Same gate, placement-aware: a pattern string being present somewhere
       satisfies step 2 even when it moved to a strictly weaker place, so
       two more specific losses are refused on top of it, by comparing
       *path*'s CURRENT on-disk content against *text* --
       :func:`_hard_deny_egress_violations` and
       :func:`_permissions_downgrade_violations`. Both are scoped to
       *expected_patterns* itself, so a pattern the caller never asked this
       write to keep (e.g. one migrated out to a different file, and so
       already absent from *expected_patterns*) is not flagged just because
       step 3 can only see *path*. Both are also STRING comparisons, not
       match-time ones -- see their docstrings for the gap that leaves
       open, deliberately left unfixed.

       Skipped entirely when *expected_patterns* is ``None`` (the caller has
       chosen not to compare against an existing rule set at all -- e.g.
       ``tools/installer.py``'s ``cmd_write_config``, which always writes a
       fresh, rule-free file even on ``--force``, backed up separately
       before the overwrite), when *path* does not yet exist, or when its
       current on-disk content is not valid UTF-8 or fails to parse -- in
       these cases there is nothing to compare against, and a broken
       original must stay writable.
    4. Atomic write via :func:`_atomic_write`.

    Args:
        path: Destination config file path.
        text: The full new file content to write.
        file_format: ``'toml'`` or ``'json'``.
        expected_patterns: When given, every pattern in this iterable must
            appear in *text* after parsing, or the write is refused. Pass
            ``None`` (the default) to skip this content-loss check --
            appropriate when the caller has no meaningful "existing
            patterns" to compare against (e.g. writing a brand-new file).

    Raises:
        ConfigWriteVerificationError: *text* fails to parse, would drop one
            or more *expected_patterns*, would remove a pattern's effective
            ``hard_deny`` protection, or would move a pattern out of
            ``permissions.deny``/``permissions.ask`` without leaving it
            restricted anywhere.
        ValueError: ``file_format`` is neither ``'toml'`` nor ``'json'``.
        OSError: The atomic write itself fails (disk full, permissions, ...).
    """
    path = Path(path)
    verify_config_text(text, file_format, path=path)

    if expected_patterns is not None:
        expected_set = set(expected_patterns)
        parsed = _parse(text, file_format)
        present = _patterns_in_parsed(parsed)
        missing = sorted(expected_set - present)
        if missing:
            raise ConfigWriteVerificationError(
                path=path,
                reason="write would drop existing rule pattern(s)",
                message=f"missing pattern(s): {', '.join(missing)}",
            )

        if path.exists():
            try:
                original_parsed = _parse(path.read_text(encoding="utf-8"), file_format)
            except (
                UnicodeDecodeError,
                tomllib.TOMLDecodeError,
                json.JSONDecodeError,
                OSError,
            ):
                original_parsed = None
            if original_parsed is not None:
                moved_from_hard_deny = _hard_deny_egress_violations(
                    original_parsed, parsed, expected_set
                )
                if moved_from_hard_deny:
                    raise ConfigWriteVerificationError(
                        path=path,
                        reason="write would move pattern(s) out of hard_deny",
                        message=(
                            f"no longer in hard_deny: {', '.join(moved_from_hard_deny)}"
                        ),
                    )

                lost_restriction = _permissions_downgrade_violations(
                    original_parsed, parsed, expected_set
                )
                if lost_restriction:
                    raise ConfigWriteVerificationError(
                        path=path,
                        reason=(
                            "write would move pattern(s) out of "
                            "permissions.deny/ask without leaving them "
                            "restricted anywhere"
                        ),
                        message=(
                            f"no longer restricted: {', '.join(lost_restriction)}"
                        ),
                    )

    _atomic_write(path, text)
