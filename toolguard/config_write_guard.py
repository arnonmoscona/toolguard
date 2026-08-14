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
    patterns: set = set()
    if not isinstance(parsed, dict):
        return patterns

    permissions = parsed.get("permissions")
    if isinstance(permissions, dict):
        for list_type in _PERMISSIONS_LIST_TYPES:
            for entry in permissions.get(list_type) or []:
                pattern = _entry_pattern(entry)
                if pattern is not None:
                    patterns.add(pattern)

    return patterns | _hard_deny_patterns(parsed)


def _hard_deny_patterns(parsed: object) -> set:
    """
    Collect every rule pattern present under a parsed config's ``hard_deny``
    table, in isolation from ``permissions`` (see :func:`_patterns_in_parsed`
    for the combined set).

    Args:
        parsed: The parsed config structure (normally a ``dict``; any other
            top-level shape simply yields an empty set).

    Returns:
        Set of every pattern string found under ``hard_deny``.
    """
    patterns: set = set()
    if not isinstance(parsed, dict):
        return patterns

    hard_deny = parsed.get("hard_deny")
    if isinstance(hard_deny, dict):
        for value in hard_deny.values():
            if not isinstance(value, list):
                continue
            for entry in value:
                pattern = _entry_pattern(entry)
                if pattern is not None:
                    patterns.add(pattern)

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
    3. Same gate: any pattern *path*'s CURRENT on-disk ``hard_deny`` holds
       must still be under ``hard_deny`` in *text* -- moving a pattern into
       ``permissions.allow`` passes step 2 (the pattern string is still
       present somewhere) but is refused here, since a hard deny turned into
       an allow is a loss even though nothing looks missing.
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
        ConfigWriteVerificationError: *text* fails to parse, or would drop
            one or more *expected_patterns*.
        ValueError: ``file_format`` is neither ``'toml'`` nor ``'json'``.
        OSError: The atomic write itself fails (disk full, permissions, ...).
    """
    path = Path(path)
    verify_config_text(text, file_format, path=path)

    if expected_patterns is not None:
        parsed = _parse(text, file_format)
        present = _patterns_in_parsed(parsed)
        missing = sorted({p for p in expected_patterns if p not in present})
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
                tomllib.TOMLDecodeError,
                json.JSONDecodeError,
                OSError,
            ):
                original_parsed = None
            if original_parsed is not None:
                moved = sorted(
                    _hard_deny_patterns(original_parsed) - _hard_deny_patterns(parsed)
                )
                if moved:
                    raise ConfigWriteVerificationError(
                        path=path,
                        reason="write would move pattern(s) out of hard_deny",
                        message=f"no longer in hard_deny: {', '.join(moved)}",
                    )

    _atomic_write(path, text)
