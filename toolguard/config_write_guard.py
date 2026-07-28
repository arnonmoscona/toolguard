"""
Self-protection guard for every toolguard config-file write.

TOO-19 corrective change: toolguard's own configuration files (``toolguard_hook.toml`` /
``toolguard_hook.json``, and anything else this project's tooling rewrites) are typically
NOT under version control on a developer's machine. A write that produces text which fails
to parse -- whether from a real bug in the writer, a not-yet-anticipated input shape, or a
regression of a bug class like TOO-19's own ``find_section_boundaries`` defect -- is a
PERMANENT, unrecoverable data loss for that user: the very next hook invocation reads a
broken file and (by this project's own documented fail-open policy) silently disables every
rule in it, with no un-corrupted copy left anywhere.

This module is the single, final gate every config-file write must pass through before
touching disk: parse the text first (:func:`verify_config_text`), optionally confirm no
existing rule pattern is about to be silently dropped (:func:`verified_write_config`'s
``expected_patterns`` check), and only then write -- atomically, so a crash mid-write can
never leave a half-written, truncated file on disk either.

Leaf module by design: this file imports ONLY the Python standard library (``tomllib``,
``json``, ``os``, ``tempfile``, ``pathlib``, ``typing``) and nothing else from
``toolguard`` -- not ``toolguard.config``, not ``toolguard.rule_sort``, not
``toolguard.rule_entry``. That is what lets every writer (``toolguard.scripts.
migrate_permissions``, ``toolguard.tools.maintenance``, and any future one) depend on this
module without risking a circular import, and it is enforced by
``test.unit.test_architecture``. A structured permission entry's pattern key ("match") is
therefore a small literal constant duplicated here rather than imported from
``toolguard.rule_entry.PATTERN_KEY`` -- see :func:`_entry_pattern`.
"""

import json
import os
import tempfile
import tomllib
from pathlib import Path
from typing import Iterable, Optional, Union

#: The table key carrying a structured entry's permission pattern, e.g.
#: ``{ match = "Bash(git *)", additionalContext = "..." }``. Deliberately a
#: literal duplicate of ``toolguard.rule_entry.PATTERN_KEY`` -- this module
#: must stay a true dependency-free leaf (see module docstring), so it cannot
#: import that constant, and the value ("match") is part of this project's
#: on-disk config format, not an implementation detail likely to drift.
_PATTERN_KEY = "match"

#: The two top-level tables this guard scans for existing rule patterns.
#: ``permissions`` carries ``allow``/``deny``/``ask``; ``hard_deny`` carries
#: ``deny``/``allow`` (checked generically -- see :func:`_patterns_in_parsed`).
_PERMISSIONS_LIST_TYPES = ("allow", "deny", "ask")


class ConfigWriteVerificationError(Exception):
    """
    Raised when text about to be written to a config file fails verification.

    The original file on disk is always left untouched when this is raised --
    every check this module performs happens BEFORE any write is attempted
    (see :func:`verified_write_config`).

    Attributes:
        path: The config file path the write was refused for (``None`` when
            raised by :func:`verify_config_text` directly, which has no path
            context of its own).
        reason: Short machine-stable category of the failure, e.g.
            ``"invalid TOML"`` or ``"write would drop existing rule
            pattern(s)"``.
        message: The underlying parser's error message, or the list of
            missing patterns, giving the actionable detail.
    """

    def __init__(
        self, path: Optional[Union[str, Path]], reason: str, message: str
    ) -> None:
        """
        Build the exception and its human-readable message.

        Args:
            path: The config file path involved, or ``None`` if unknown at
                the point of raising.
            reason: Short category of the failure.
            message: Detailed explanation (parser error text, or missing
                pattern list).
        """
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
    Parse *text* and raise if it does not parse as valid TOML/JSON.

    Pure syntax check -- does no I/O and does not know or care what the
    parsed content actually contains (see :func:`verified_write_config` for
    the separate content-loss check). This is the minimum bar every write
    must clear: a config file this project cannot even parse back is the
    single highest-impact failure mode this module exists to prevent (see
    module docstring).

    Args:
        text: The candidate config file text.
        file_format: ``'toml'`` or ``'json'``.
        path: Optional path to attach to the raised error for a more useful
            message, when the caller has one (:func:`verified_write_config`
            always supplies it; a caller invoking this function directly may
            not have one yet).

    Raises:
        ConfigWriteVerificationError: ``text`` fails to parse as
            ``file_format``.
    """
    try:
        _parse(text, file_format)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as e:
        raise ConfigWriteVerificationError(
            path=path,
            reason=f"invalid {file_format.upper()}",
            message=str(e),
        ) from e


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

    Writes to a temporary file created in *path*'s own parent directory (same
    filesystem, required for :func:`os.replace` to be atomic), flushes and
    calls :func:`os.fsync` before renaming, so a crash mid-write can never
    leave a truncated *path* on disk -- *path* either keeps its old complete
    content or gets the new complete content, never a partial write. The
    temporary file is removed if any step fails. *path*'s parent directory is
    created first if it does not exist yet, matching every writer this guard
    replaces (e.g. a first-ever ``write-config`` into a not-yet-existing
    ``.claude/`` directory).

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

    Public counterpart of the internal ``expected_patterns`` bookkeeping
    :func:`verified_write_config` does for its own callers: a caller that
    needs to compute ``expected_patterns`` from an *existing* on-disk file
    (rather than from the in-memory data structure it is about to write) --
    e.g. before an edit that only touches an unrelated section and must not
    let the pre-existing ``permissions``/``hard_deny`` patterns silently
    vanish -- can read that file's current text and pass it here to get the
    set to pass through unchanged.

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

    Three steps, in order, ANY of which can refuse the write (leaving *path*
    completely untouched on disk):

    1. :func:`verify_config_text` -- *text* must parse as *file_format*.
    2. If *expected_patterns* is not ``None``: every pattern in it must still
       be present somewhere in *text*'s parsed ``permissions``/``hard_deny``
       structure (see :func:`_patterns_in_parsed`). A missing pattern means
       this write would silently DELETE a rule -- refused, distinct from (and
       checked after) the pure syntax check in step 1.
    3. Atomic write via :func:`_atomic_write`.

    Args:
        path: Destination config file path.
        text: The full new file content to write.
        file_format: ``'toml'`` or ``'json'``.
        expected_patterns: When given, every pattern in this iterable must
            appear in *text* after parsing, or the write is refused. Pass
            ``None`` (the default) to skip this content-loss check entirely
            -- appropriate only when the caller has no meaningful "existing
            patterns" set to compare against (e.g. writing a brand-new file).

    Raises:
        ConfigWriteVerificationError: *text* fails to parse, or would drop
            one or more *expected_patterns*.
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

    _atomic_write(path, text)
