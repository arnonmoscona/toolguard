"""
Configuration loading for toolguard.

Loads and parses permissions from Claude Code settings files with support for:
- A directory hierarchy of config sources (project and every ancestor up to
  ``~``, or to the filesystem root for a project outside ``~``, plus two
  candidate rules directories), not just project and user.
- Extended pattern syntax in ``toolguard_hook`` files (TOML preferred, JSON
  supported).
- Merging permissions from multiple sources.

Public abstraction
------------------
The public entry point is :func:`load_configuration`, which returns an immutable
:class:`Configuration`. All file discovery, JSON/TOML parsing, ``.claude/`` layout,
``.local`` handling, and ``CLAUDE_SETTINGS_PATH`` behaviour are internal to this module.
No code outside this module should open a config file, parse JSON/TOML, or branch on
file format/location. Clients ask the :class:`Configuration` semantic questions instead.

The lower-level loaders are internal implementation behind this abstraction; new clients
should always prefer :func:`load_configuration`. A few remain public only because
not-yet-migrated non-test callers still use them -- ``find_project_root``,
``discover_config_files``, ``load_config_file``, and
``config_sync_settings_from_sources`` (used by ``auto_migrate``). :func:`wrap_tool_pattern`
is also public, but by design -- it is a standalone helper unrelated to loading. Everything
else is underscore-prefixed.
"""

import functools
import hashlib
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Set, Tuple

from toolguard import ambient
from toolguard.config_types import ConfigLayer as ConfigLayer
from toolguard.config_types import ConflictOverride as ConflictOverride
from toolguard.config_types import Provenance as Provenance
from toolguard.config_types import RuntimeVerdict as RuntimeVerdict
from toolguard.config_types import TakeoverConfig as TakeoverConfig
from toolguard.config_types import TakeoverEnabledConflict as TakeoverEnabledConflict
from toolguard.config_types import ToolPatternLayer as ToolPatternLayer
from toolguard.config_types import (
    UnrecognizedFallbackSetting as UnrecognizedFallbackSetting,
)
from toolguard.config_validation import validate_permissions
from toolguard.error_reporter import report_warning
from toolguard.issues import Issue
from toolguard.path_utils import require_project_root
from toolguard.rule_entry import RuleEntry, entries_for_tool, normalize_entry
from toolguard.rule_entry import is_tool_wrapper as is_tool_wrapper
from toolguard.rule_entry import normalize_entries_preserving
from toolguard.tool_spec import DEFAULT_GOVERNED_TOOLS
from toolguard.toml_scan import find_multiline_structured_entry_line

#: Blanket allow patterns suppressed under takeover mode even when no level
#: lists them explicitly.
_DEFAULT_IGNORED_ALLOW_PATTERNS: Tuple[str, ...] = (
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)",
)
_DEFAULT_NO_MATCH_FALLBACK = "ask"
#: Recognized values for ``no_match_fallback`` after alias normalization --
#: ``warn_deny`` and ``allow_with_no_warnings`` are accepted spellings that
#: never appear here (see technical-notes.md for the asymmetry with
#: ``undecidable_fallback``).
_VALID_NO_MATCH_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning", "allow"})

_DEFAULT_UNDECIDABLE_FALLBACK = "ask"
#: Recognized values for ``undecidable_fallback`` after alias normalization.
_VALID_UNDECIDABLE_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning", "allow"})

#: Permanent synonym for ``'allow'`` on both ``*_fallback`` settings -- a
#: human reminder that silencing the warning was deliberate.
_ALLOW_NO_WARNINGS_ALIAS = {"allow_with_no_warnings": "allow"}

#: Human-facing spellings for the unrecognized-value warning's "Accepted
#: values:" text -- distinct from ``_VALID_*_FALLBACKS``, which hold the
#: post-alias canonical set. Deliberately excludes the deprecated
#: ``warn_deny``, which still resolves but should not be advertised.
_ACCEPTED_FALLBACK_SPELLINGS = (
    "allow",
    "allow_with_no_warnings",
    "allow_with_warning",
    "ask",
    "deny",
)

#: ``config_sync`` default values -- the more-specific-wins and
#: last-occurrence-wins resolvers differ on a conflict, not on these.
_CONFIG_SYNC_DEFAULTS: Dict[str, object] = {
    "auto_migrate": False,
    "backup_dir": "logs/config-backups",
    "auto_sort_on_migrate": True,
}


def _parse_config_file(path_str: str, file_format: str) -> dict:
    """
    Parse a single config file by format, with no caching.

    Args:
        path_str: Filesystem path to the config file, as a string.
        file_format: Either ``'toml'`` or ``'json'``.

    Returns:
        The parsed config dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        tomllib.TOMLDecodeError: If a TOML file is malformed.
        json.JSONDecodeError: If a JSON file is malformed.
    """
    if file_format == "toml":
        with open(path_str, "rb") as f:
            return tomllib.load(f)
    with open(path_str, "r") as f:
        return json.load(f)


@functools.lru_cache(maxsize=None)
def _parse_config_file_cached(
    path_str: str, file_format: str, mtime_ns: int, size: int, content_hash: str
) -> dict:
    """
    Parse a single config file, memoized on (path, format, mtime, size, content_hash).

    ``size`` is part of the key alongside ``mtime_ns`` because two rewrites
    within the same mtime tick would otherwise collide and serve a stale,
    wrong-sized parse. ``content_hash`` is needed on top of both: a
    same-length rewrite with its mtime restored (the shape a
    read-modify-write tool produces) changes neither, and coarse filesystem
    mtime resolution can leave even a genuine rewrite's mtime unchanged.

    Args:
        path_str: Filesystem path to the config file, as a string.
        file_format: Either ``'toml'`` or ``'json'``.
        mtime_ns: The file's ``st_mtime_ns`` at the time of the call (cache key only).
        size: The file's ``st_size`` at the time of the call (cache key only).
        content_hash: Digest of the file's bytes at the time of the call (cache key only).

    Returns:
        The parsed config dictionary.
    """
    return _parse_config_file(path_str, file_format)


def load_config_file(path: Path, file_format: str = "json") -> dict:
    """
    Load and parse a single config file, dispatching on format.

    Memoized on ``(path, st_mtime_ns, st_size, content_hash)``: repeat calls
    for the same unchanged file are cheap, and a rewrite is still picked up
    even when it lands on the same size and mtime. Raises on any parse
    failure rather than returning an error value.

    Args:
        path: Path to the config file.
        file_format: Either ``'toml'`` or ``'json'`` (defaults to ``'json'``).

    Returns:
        The parsed config dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
        tomllib.TOMLDecodeError: If a TOML file is malformed.
        json.JSONDecodeError: If a JSON file is malformed.
    """
    try:
        stat_result = path.stat()
        content_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return _parse_config_file(str(path), file_format)
    return _parse_config_file_cached(
        str(path),
        file_format,
        stat_result.st_mtime_ns,
        stat_result.st_size,
        content_hash,
    )


def find_project_root(start_dir: Path = None) -> Path:
    """
    Find the project root by searching for a project anchor or pyproject.toml.

    Climbs up from start_dir (or current directory) until finding the nearest
    marker (a strong project anchor -- ``.git``/``.hg``/``.jj``/``.claude``/
    ``CLAUDE.md`` -- or ``pyproject.toml``), stopping at the home directory or
    filesystem root.

    Args:
        start_dir: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to project root

    Raises:
        RuntimeError: If project root cannot be found
    """
    return require_project_root(start_dir)


def discover_config_files(start_dir: Path = None) -> List[Tuple[Path, str, str]]:
    """
    Discover all applicable config files in priority order.

    Legacy, two-level (project + user) discovery, superseded by
    :func:`_discover_levels`'s full ancestor-hierarchy walk; kept for callers
    that still use the flat two-level shape. For the ``toolguard_hook``
    sources, TOML takes precedence when both formats exist; native
    ``settings``/``settings.local`` sources are JSON-only.

    Returns config files in this order (highest to lowest priority):
    1. Project .claude/toolguard_hook.local.toml (or .json if no .toml)
    2. Project .claude/settings.local.json
    3. Project .claude/toolguard_hook.toml (or .json if no .toml)
    4. Project .claude/settings.json
    5. User ~/.claude/toolguard_hook.local.toml (or .json if no .toml)
    6. User ~/.claude/settings.local.json
    7. User ~/.claude/toolguard_hook.toml (or .json if no .toml)
    8. User ~/.claude/settings.json

    Args:
        start_dir: Directory to start searching for project root from. Defaults to cwd.

    Returns:
        List of (Path, source_type, format) tuples where:
        - source_type is 'claude' or 'toolguard_hook'
        - format is 'json' or 'toml'
    """
    config_files = []

    # Try to find project root
    try:
        project_root = find_project_root(start_dir)
        project_claude_dir = project_root / ".claude"
    except RuntimeError:
        # No project root found - skip project-level configs
        project_claude_dir = None

    # Define config file candidates in priority order with format preference
    # Each entry is (base_name, source_type, prefer_toml)
    candidates = []

    # Project level
    if project_claude_dir:
        candidates.extend(
            [
                (project_claude_dir, "toolguard_hook.local", "toolguard_hook", True),
                (project_claude_dir, "settings.local", "claude", False),
                (project_claude_dir, "toolguard_hook", "toolguard_hook", True),
                (project_claude_dir, "settings", "claude", False),
            ]
        )

    # User level -- skipped when it is the same directory as the project
    # level already added above (the project root is home), which would
    # otherwise duplicate every file found there.
    user_claude_dir = ambient.home() / ".claude"
    if (
        project_claude_dir is None
        or user_claude_dir.resolve() != project_claude_dir.resolve()
    ):
        candidates.extend(
            [
                (user_claude_dir, "toolguard_hook.local", "toolguard_hook", True),
                (user_claude_dir, "settings.local", "claude", False),
                (user_claude_dir, "toolguard_hook", "toolguard_hook", True),
                (user_claude_dir, "settings", "claude", False),
            ]
        )

    # Check for both TOML and JSON, with TOML taking precedence
    for directory, base_name, source_type, prefer_toml in candidates:
        toml_path = directory / f"{base_name}.toml"
        json_path = directory / f"{base_name}.json"

        toml_exists = toml_path.exists()
        json_exists = json_path.exists()

        if prefer_toml and toml_exists:
            config_files.append((toml_path, source_type, "toml"))
            # The "both .toml and .json exist" warning is deliberately not
            # emitted here -- Configuration.validation_issues() is the single
            # source of truth for it. Printing it here too would double it.
        elif json_exists:
            config_files.append((json_path, source_type, "json"))

    return config_files


#: Within-level candidates, highest-to-lowest priority: ``(base_name,
#: source_type, prefer_toml)``.
_LEVEL_CANDIDATES: Tuple[Tuple[str, str, bool], ...] = (
    ("toolguard_hook.local", "toolguard_hook", True),
    ("settings.local", "claude", False),
    ("toolguard_hook", "toolguard_hook", True),
    ("settings", "claude", False),
)

#: Top-level sections a rules-directory file may contain. Scalars/singletons
#: have no multi-file merge rule and stay in the primary toolguard_hook.toml.
_RULES_FILE_ALLOWED_SECTIONS = frozenset({"permissions", "hard_deny"})


def _rules_dirs() -> Tuple[Path, Path]:
    """
    Resolve the two candidate user-level rules directories, in precedence order.

    ``xdg_dir`` is ``$XDG_CONFIG_HOME/toolguard/rules`` (an empty
    ``XDG_CONFIG_HOME`` counts as unset) or else ``~/.config/toolguard/rules``.
    ``legacy_dir`` is ``~/.toolguard/rules``, which predates the XDG
    convention. Both are scanned, XDG first -- see technical-notes.md for why
    the legacy directory is still scanned and how a same-stem collision
    between the two is resolved.

    Neither directory need exist.

    Returns:
        ``(xdg_dir, legacy_dir)``, in precedence order (XDG first).
    """
    xdg_config_home = ambient.env_var("XDG_CONFIG_HOME")
    if xdg_config_home:
        xdg_dir = Path(xdg_config_home) / "toolguard" / "rules"
    else:
        xdg_dir = ambient.home() / ".config" / "toolguard" / "rules"
    legacy_dir = ambient.home() / ".toolguard" / "rules"
    return (xdg_dir, legacy_dir)


def _group_rules_files_by_stem(rules_dir: Path) -> Dict[str, Dict[str, Path]]:
    """
    Flat scan of a rules directory, grouping ``*.toml``/``*.json`` files by stem.

    Args:
        rules_dir: The directory to scan.

    Returns:
        Mapping of filename stem to a ``{'.toml': path, '.json': path}``
        sub-mapping of whichever suffixes are present for that stem. Empty
        when ``rules_dir`` is missing or not a directory.
    """
    if not rules_dir.is_dir():
        return {}
    by_stem: Dict[str, Dict[str, Path]] = {}
    for path in rules_dir.iterdir():
        if not path.is_file():
            continue
        if path.suffix in (".toml", ".json"):
            by_stem.setdefault(path.stem, {})[path.suffix] = path
    return by_stem


def _resolve_stem_formats(
    by_stem: Dict[str, Dict[str, Path]],
) -> List[Tuple[Path, str]]:
    """
    Resolve a stem-to-formats mapping to one winning ``(path, format)`` per stem.

    TOML wins over JSON when both are present for a stem. Results are sorted
    lexicographically by stem so merge order and log provenance are
    reproducible run-to-run.

    Args:
        by_stem: Mapping of stem to ``{'.toml': path, '.json': path}``.

    Returns:
        List of ``(path, format)`` pairs, ``format`` being ``'toml'`` or
        ``'json'``, sorted ascending by filename stem.
    """
    result: List[Tuple[Path, str]] = []
    for stem in sorted(by_stem):
        formats = by_stem[stem]
        if ".toml" in formats:
            result.append((formats[".toml"], "toml"))
        elif ".json" in formats:
            result.append((formats[".json"], "json"))
    return result


def _discover_rules_files(rules_dir: Path) -> List[Tuple[Path, str]]:
    """
    Flat, non-recursive scan of a rules directory for ``*.toml``/``*.json`` files.

    A missing or empty directory is a no-op (returns an empty list, never an
    error). Subdirectories and files with other extensions are ignored --
    scanning is intentionally flat. When both ``<stem>.toml``
    and ``<stem>.json`` exist for the same stem, only the TOML entry is
    returned (see :func:`_resolve_stem_formats`).

    Args:
        rules_dir: The directory to scan.

    Returns:
        List of ``(path, format)`` pairs, ``format`` being ``'toml'`` or
        ``'json'``, sorted ascending by filename stem.
    """
    return _resolve_stem_formats(_group_rules_files_by_stem(rules_dir))


def _merged_rules_by_stem(
    rules_dirs: Tuple[Path, ...],
) -> Dict[str, Dict[str, Path]]:
    """
    Merge rules-file stems across multiple directories, first-directory-wins.

    A later directory's same-stem entry is "shadowed" (see
    :func:`_shadowed_rules_stems`).

    Args:
        rules_dirs: Candidate rules directories, most-preferred first.

    Returns:
        Mapping of stem to the winning directory's ``{'.toml': path, '.json':
        path}`` sub-mapping.
    """
    merged: Dict[str, Dict[str, Path]] = {}
    for rules_dir in rules_dirs:
        for stem, formats in _group_rules_files_by_stem(rules_dir).items():
            if stem not in merged:
                merged[stem] = formats
    return merged


def _discover_rules_files_multi(rules_dirs: Tuple[Path, ...]) -> List[Tuple[Path, str]]:
    """
    Flat, non-recursive scan across multiple rules directories.

    Args:
        rules_dirs: Candidate rules directories, most-preferred first.

    Returns:
        List of ``(path, format)`` pairs, sorted ascending by filename stem.
    """
    return _resolve_stem_formats(_merged_rules_by_stem(rules_dirs))


def _shadowed_rules_stems(rules_dirs: Tuple[Path, Path]) -> Dict[str, Path]:
    """
    Find filename stems present in BOTH of the two candidate rules directories.

    Intentionally two-directory-only, matching :func:`_rules_dirs`'s exact
    ``(xdg_dir, legacy_dir)`` shape -- a same-stem collision here means the
    ``legacy_dir`` entry is dropped entirely by :func:`_merged_rules_by_stem`
    (see technical-notes.md for why this must be surfaced as a warning, and
    the one exception: both paths resolving to the same real file).

    Returns the shadowed stems with a representative shadowed path (TOML
    preferred over JSON, same rule as elsewhere) so :func:`load_configuration`
    can record it on the winning :class:`ConfigLayer` for
    :meth:`Configuration.validation_issues` to report.

    Args:
        rules_dirs: The two candidate rules directories, ``(xdg_dir,
            legacy_dir)`` as returned by :func:`_rules_dirs`.

    Returns:
        Mapping of stem to the shadowed (non-winning) representative path.
        Empty when no stem collides, or every collision is the same real file
        reached via two paths.
    """
    xdg_dir, legacy_dir = rules_dirs
    xdg_stems = _group_rules_files_by_stem(xdg_dir)
    legacy_stems = _group_rules_files_by_stem(legacy_dir)
    shadowed: Dict[str, Path] = {}
    for stem, legacy_formats in legacy_stems.items():
        xdg_formats = xdg_stems.get(stem)
        if xdg_formats is None:
            continue
        winning_path = xdg_formats.get(".toml") or xdg_formats.get(".json")
        shadowed_path = legacy_formats.get(".toml") or legacy_formats.get(".json")
        if winning_path.resolve() == shadowed_path.resolve():
            continue
        shadowed[stem] = shadowed_path
    return shadowed


def _discover_in_dir(claude_dir: Path) -> List[Tuple[Path, str, str]]:
    """
    Discover config files within a single ``.claude`` directory, in
    :data:`_LEVEL_CANDIDATES` priority order.

    Args:
        claude_dir: A ``.claude`` directory to scan.

    Returns:
        List of (path, source_type, format) triples for files that exist,
        highest-priority first.
    """
    found: List[Tuple[Path, str, str]] = []
    for base_name, source_type, prefer_toml in _LEVEL_CANDIDATES:
        toml_path = claude_dir / f"{base_name}.toml"
        json_path = claude_dir / f"{base_name}.json"
        toml_exists = toml_path.exists()
        json_exists = json_path.exists()

        if prefer_toml and toml_exists:
            found.append((toml_path, source_type, "toml"))
            # The "both .toml and .json exist" warning is deliberately not
            # emitted here -- Configuration.validation_issues() is the single
            # source of truth for it. Discovery stays side-effect-free.
        elif json_exists:
            found.append((json_path, source_type, "json"))
    return found


def _hierarchical_toggle(project_claude_dir: Optional[Path]) -> bool:
    """
    Read the ``hierarchical_configuration`` toggle from the project level only.

    Per the fixed-bootstrap rule, read ONLY from the most-specific (project)
    ``toolguard_hook`` config, so ancestors cannot vote on whether ancestors
    are traversed. Defaults to ``True`` when unset or unreadable.

    A parse failure here needs no :attr:`Configuration.parse_failures`
    bookkeeping: the same file is re-parsed and recorded by the real
    discovery pass afterwards.

    Args:
        project_claude_dir: The project's ``.claude`` directory, or None when no
            project root could be found.

    Returns:
        True to walk the full hierarchy, False to use only project + user levels.
    """
    if project_claude_dir is None:
        return True
    # Only toolguard_hook sources carry this toggle (not native settings).
    for path, source_type, file_format in _discover_in_dir(project_claude_dir):
        if source_type != "toolguard_hook":
            continue
        content = _parse_source(path, file_format)
        if content is None:
            continue
        if "hierarchical_configuration" in content:
            return bool(content["hierarchical_configuration"])
        # First (highest-priority) toolguard_hook source wins; stop after it so a
        # less-specific project-level file cannot override the toggle decision.
        break
    return True


def _discover_levels(start_dir: Path = None) -> List[Tuple[Path, str, str, int, str]]:
    """
    Discover config files across the directory hierarchy, most-specific first.

    Walks from the project root (see :func:`find_project_root`) UP TO and
    including the user's home directory, collecting config files from every
    ancestor that has a ``.claude`` subdirectory. The user-level ``~/.claude`` is
    ALWAYS included as the least-specific level, even when the project is not
    located under ``~`` (preserving "user config always applies"). The walk
    stops at ``~`` for a project located under ``~``, or at the filesystem
    root for a project that is not.

    Each level is assigned a ``specificity`` index: 0 = project (most specific),
    increasing with distance, and the user level last (least specific). When the
    ``hierarchical_configuration`` toggle (read from the project level only) is
    False, only the project and user levels are collected.

    After the primary ``.claude`` candidates, any files discovered across the
    two optional candidate rules directories are appended with
    ``source_type='toolguard_hook_rules'`` at the SAME (least-specific, user)
    specificity as ``~/.claude`` -- they merge into the user level rather than
    introducing a new hierarchy tier, and are ordered AFTER the primary
    ``~/.claude`` candidates so those stay the highest-priority user-level
    source on a duplicate pattern. Both candidate directories share this
    same specificity; when the same stem exists in both, the XDG directory's
    file wins and the other is dropped (see :func:`_merged_rules_by_stem`).

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to cwd.

    Returns:
        List of (path, source_type, format, specificity, level) tuples, ordered
        most-specific first then by within-level priority, with any
        rules-directory files appended last. ``level`` is ``'user'`` for the
        least-specific tier (``~/.claude`` plus the rules directories) and
        ``'project'`` otherwise.
    """
    home = ambient.home()
    user_claude_dir = home / ".claude"

    try:
        project_root = find_project_root(start_dir)
        project_claude_dir = project_root / ".claude"
    except RuntimeError:
        project_root = None
        project_claude_dir = None

    hierarchical = _hierarchical_toggle(project_claude_dir)

    # Build the ordered list of .claude directories (most specific first),
    # de-duplicated, with the user level always present and always last.
    level_dirs: List[Path] = []

    def _add(claude_dir: Path) -> None:
        resolved = claude_dir.resolve()
        for existing in level_dirs:
            if existing.resolve() == resolved:
                return
        level_dirs.append(claude_dir)

    if project_root is not None:
        if hierarchical:
            current = project_root
            while True:
                _add(current / ".claude")
                if current == home or current == current.parent:
                    break
                current = current.parent
        else:
            _add(project_root / ".claude")

    # User level always applies and is always least specific (appended last,
    # unless the upward walk already reached it, in which case it keeps its
    # natural tail position).
    _add(user_claude_dir)

    # Computed from level_dirs, not from the discovered results below: a level
    # whose directory does not exist contributes no results at all, so taking
    # the maximum over the results would promote the deepest EXISTING level to
    # 'user' instead of the true last entry.
    user_specificity = len(level_dirs) - 1

    results: List[Tuple[Path, str, str, int, str]] = []
    for specificity, claude_dir in enumerate(level_dirs):
        if not claude_dir.exists():
            continue
        # Emitted HERE, by the pass that actually found the file -- do not
        # re-derive it downstream from the path's shape (e.g. path.resolve()
        # plus a containment check against ~/.claude). That check silently
        # promotes a project rule to the user level, changing precedence with
        # no error, whenever a .claude directory (or a file inside it) is a
        # symlink into a store under ~/.claude.
        level = "user" if specificity == user_specificity else "project"
        for path, source_type, file_format in _discover_in_dir(claude_dir):
            results.append((path, source_type, file_format, specificity, level))

    # Rules-directory files, merged into the user level -- see this
    # function's docstring above.
    for path, file_format in _discover_rules_files_multi(_rules_dirs()):
        results.append(
            (path, "toolguard_hook_rules", file_format, user_specificity, "user")
        )

    return results


# ---------------------------------------------------------------------------
# Public configuration abstraction -- see the module docstring's "Public
# abstraction" section.
# ---------------------------------------------------------------------------


def wrap_tool_pattern(tool: str, body: str) -> str:
    """
    Wrap a pattern body in its ``Tool(...)`` envelope.

    The structural inverse of :func:`~toolguard.rule_entry._strip_tool_wrapper`: given a tool name and a
    wrapper-free body, produce the wrapped form as stored in config files (e.g.
    ``wrap_tool_pattern('Bash', 'git diff:*') -> 'Bash(git diff:*)'``).

    Args:
        tool: Tool name (e.g. ``'Bash'``).
        body: Wrapper-free pattern body (e.g. ``'git diff:*'``).

    Returns:
        The wrapped permission pattern string.
    """
    return f"{tool}({body})"


@dataclass(frozen=True)
class Configuration:
    """
    Immutable, file/format-agnostic view of the resolved toolguard config.

    Built by :func:`load_configuration`. Holds the discovered layers (most
    specific first) plus the start directory used for discovery. All semantic
    questions are answered by methods here; clients never touch files/formats.
    Permission resolution itself (more-specific-wins across levels) lives in
    :mod:`toolguard.permission_resolution`, fed by
    :meth:`permission_levels_with_provenance`; :meth:`allow_deny_for` remains
    as a flattened-union view for callers that don't need per-level detail.

    Attributes:
        layers: Discovered config layers, most-specific first.
        start_dir: Directory discovery started from (for :attr:`project_root`).
        parse_failures: ``(path, message)`` pairs for every governed config
            file that EXISTED but failed to parse -- a missing file is not
            recorded, only one that was found and was broken (unreadable, or
            its top level was not an object/table). Non-empty is a severe
            safety-floor condition: every governed decision EXCEPT an
            already-``'deny'`` one is clamped to ``'ask'`` by
            :func:`~toolguard.permission_resolution.resolve_permission_cascade`
            (see :func:`~toolguard.permission_resolution._apply_ask_floor`)
            until the file(s) are fixed, because a broken file may have
            silently dropped a deny/hard_deny rule with no other visible
            trace. :meth:`validation_issues` also reports one ``'error'``
            Issue per entry, and ``toolguard-session-start`` surfaces it at
            the start of every session while it remains non-empty.
    """

    layers: Tuple[ConfigLayer, ...]
    start_dir: Optional[Path] = None
    parse_failures: Tuple[Tuple[Path, str], ...] = ()

    # -- project root ------------------------------------------------------

    @property
    def project_root(self) -> Optional[Path]:
        """
        Return the resolved project root, or None when none can be found.

        The project root is the anchor for ALL relative paths declared anywhere
        in the configuration (see :meth:`resolve_config_path`). Resolved via
        :func:`find_project_root` from :attr:`start_dir`; None is returned
        when no project marker is found (see :func:`find_project_root` for
        the marker list).
        """
        try:
            return find_project_root(self.start_dir)
        except RuntimeError:
            return None

    def resolve_config_path(self, raw_path: str) -> str:
        """
        Resolve a path declared in configuration against the PROJECT ROOT.

        Any relative path appearing anywhere in configuration -- regardless of
        which level/directory declared it -- resolves against the project root,
        NOT against the ancestor directory that holds the declaring file and NOT
        against the current working directory. This is the single anchor point
        for that rule.

        Absolute paths and ``~``-paths are returned unchanged here (``~`` is
        expanded by downstream matching/normalisation, not by this method).

        Args:
            raw_path: A path string from configuration (e.g. a ``backup_dir`` or
                a relative file-path permission pattern, already stripped of any
                extended-syntax prefix and tool wrapper).

        Returns:
            For a relative path: ``<project_root>/<raw_path>`` as a string (or
            the original when no project root is known). Absolute and ``~`` paths
            are returned unchanged.
        """
        if not raw_path:
            return raw_path
        if raw_path.startswith("/") or raw_path.startswith("~"):
            return raw_path
        root = self.project_root
        if root is None:
            return raw_path
        return str(root / raw_path)

    # -- governed tools ----------------------------------------------------

    def governed_tools(self) -> Tuple[str, ...]:
        """
        Return the resolved list of governed tools.

        UNION across all toolguard_hook layers in the hierarchy:
        every level's ``governed_tools`` list is pooled, de-duplicated, and kept
        in first-occurrence (most-specific-first) order. Native Claude settings
        layers are ignored (``governed_tools`` is a toolguard extension).
        Defaults to :data:`~toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS`
        (``('Bash', 'Read', 'Write', 'Edit')``) when no level configures any
        governed tool.

        Under ``CLAUDE_SETTINGS_PATH``, only an adjacent ``toolguard_hook``
        file can contribute -- the explicit settings file itself is native
        (``is_native`` True) and is skipped like any other native layer.
        """
        seen: Dict[str, None] = {}
        for layer in self.layers:
            if layer.is_native:
                continue
            tools = layer.content.get("governed_tools", [])
            if not isinstance(tools, list):
                continue
            for tool in tools:
                if isinstance(tool, str):
                    seen.setdefault(tool, None)
        if not seen:
            return DEFAULT_GOVERNED_TOOLS
        return tuple(seen.keys())

    # -- takeover mode -----------------------------------------------------

    def takeover_mode(self) -> TakeoverConfig:
        """
        Return the resolved takeover-mode configuration.

        Resolved hierarchically over ``self.layers`` (most-specific first),
        reading only ``toolguard_hook`` layers:

        - ``enabled`` is a SINGLE-OWNER policy with fail-safe-on-conflict,
          resolved by :meth:`_resolve_takeover_enabled` (see there for the
          per-case outcome); a conflict fails safe to OFF (native Claude
          prompts stay active, nothing is silently bypassed).
        - ``ignored_allow_patterns`` and ``additional_ignored_patterns`` are a
          UNION across all levels (de-duplicated, order-preserving most-specific
          first). The blanket defaults seed ``ignored_allow_patterns``.
        - ``no_match_fallback`` resolves MORE-SPECIFIC-WINS (first level that sets
          it wins); defaults to ``'ask'``. The RAW value is returned unchanged
          here (including the deprecated ``'warn_deny'`` alias); normalization
          happens in :meth:`Configuration.resolved_no_match_fallback`.

        Returns:
            The resolved :class:`TakeoverConfig`.
        """
        ignored_allow: List[str] = list(_DEFAULT_IGNORED_ALLOW_PATTERNS)
        additional_ignored: List[str] = []
        no_match_fallback: Optional[str] = None
        explicit_enabled: List[Tuple[bool, Provenance]] = []

        for layer in self.layers:
            # takeover_mode is a toolguard extension; ignore native settings.
            if layer.is_native:
                continue
            section = layer.content.get("takeover_mode", {})
            if not isinstance(section, dict) or not section:
                continue

            # Record an EXPLICIT enabled setting with provenance.
            # ``enabled`` is a fail-safe SECURITY toggle, so a non-bool value is
            # NOT coerced (``bool('false')`` would be True): such a level does not
            # vote, and validation_issues() reports the malformed value.
            if "enabled" in section and isinstance(section["enabled"], bool):
                explicit_enabled.append((section["enabled"], layer.provenance))

            # Union pattern lists (most-specific first; de-dup preserves order).
            for pattern in section.get("ignored_allow_patterns", []):
                if pattern not in ignored_allow:
                    ignored_allow.append(pattern)
            for pattern in section.get("additional_ignored_patterns", []):
                if pattern not in additional_ignored:
                    additional_ignored.append(pattern)

            # no_match_fallback: more-specific-wins (first definition wins).
            if no_match_fallback is None and "no_match_fallback" in section:
                no_match_fallback = section["no_match_fallback"]

        enabled, conflict = self._resolve_takeover_enabled(explicit_enabled)

        return TakeoverConfig(
            enabled=enabled,
            ignored_allow_patterns=tuple(ignored_allow),
            additional_ignored_patterns=tuple(additional_ignored),
            no_match_fallback=no_match_fallback
            if no_match_fallback is not None
            else _DEFAULT_NO_MATCH_FALLBACK,
            conflict=conflict,
        )

    @staticmethod
    def _resolve_takeover_enabled(
        explicit: List[Tuple[bool, "Provenance"]],
    ) -> Tuple[bool, Optional["TakeoverEnabledConflict"]]:
        """
        Resolve ``takeover_mode.enabled`` from the explicit per-level settings.

        Single-owner / fail-safe-on-conflict: disagreement forces ``False``
        with a :class:`TakeoverEnabledConflict` recording every source.

        Args:
            explicit: ``(value, provenance)`` pairs for every layer that
                explicitly set ``enabled``, most-specific first.

        Returns:
            Tuple of ``(enabled, conflict_or_None)``.
        """
        if not explicit:
            return False, None
        values = {value for value, _prov in explicit}
        if len(values) == 1:
            return next(iter(values)), None
        # Disagreement => fail-safe OFF with a conflict record.
        return False, TakeoverEnabledConflict(sources=tuple(explicit))

    # -- permissions -------------------------------------------------------

    def _pool_hard_deny_entries(
        self, tool_name: str
    ) -> Tuple[Tuple[RuleEntry, ...], Tuple[RuleEntry, ...]]:
        """
        Pool wrapper-INTACT hard-deny (deny_entries, allow_entries) for a tool.

        Unlike the cascade, entries pool from ALL levels into a union,
        de-duplicated on ``entry.pattern``: the most-specific occurrence wins
        outright, so metadata (e.g. ``additionalContext``) on a less-specific
        duplicate is silently discarded. Wrapper-scoping means two distinct
        wrapped patterns never collide once stripped.

        Args:
            tool_name: Tool to extract hard-deny entries for (e.g. 'Bash',
                'Read', 'Write', 'Edit').

        Returns:
            A ``(deny_entries, allow_entries)`` pair of wrapper-INTACT
            :class:`RuleEntry` tuples, pooled across all toolguard_hook
            layers, de-duplicated on pattern, most-specific-first.
        """
        seen_deny: Dict[str, RuleEntry] = {}
        seen_allow: Dict[str, RuleEntry] = {}

        for layer in self.layers:
            # hard_deny is a toolguard extension; ignore native Claude settings.
            if layer.is_native:
                continue
            section = layer.content.get("hard_deny", {})
            if not isinstance(section, dict):
                continue

            deny_entries = self._extract_tool_entries(
                section.get("deny", []), tool_name, layer.is_native
            )
            for entry in deny_entries:
                seen_deny.setdefault(entry.pattern, entry)

            allow_entries = self._extract_tool_entries(
                section.get("allow", []), tool_name, layer.is_native
            )
            for entry in allow_entries:
                seen_allow.setdefault(entry.pattern, entry)

        return tuple(seen_deny.values()), tuple(seen_allow.values())

    def hard_deny(self, tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return the pooled hard-deny (deny, allow) patterns for a tool.

        ``[hard_deny]`` is a toolguard EXTENSION read ONLY from ``toolguard_hook``
        layers -- never from native Claude settings, which have no such concept.
        It is evaluated FIRST, before the normal cascade, and cannot be
        overridden by any level's normal allow. See :meth:`_pool_hard_deny_entries`
        for the pooling/de-dup/native-skip mechanics.

        Semantics of the returned lists:

        - ``deny``: a command/path matching any of these is hard-denied UNLESS it
          also matches an ``allow`` carve-out.
        - ``allow``: an EXCEPTION to ``deny`` only (e.g. hard-deny all ``curl``
          EXCEPT ``curl localhost``). It is NOT a forced/normal allow and does
          NOT affect the normal cascade.

        Patterns are returned in extracted form (the ``Tool(...)`` wrapper is
        stripped, exactly like :meth:`permission_layers`), tool-scoped to
        ``tool_name``, and carry the same extended syntax (``[regex]``/``[glob]``/
        ``[native]``) the normal matchers understand. Relative file-path patterns
        are NOT anchored here; anchoring to the project root happens at match time
        in the hook, mirroring normal patterns.

        A structured (``{match = "...", ...}``) entry contributes its pattern
        here exactly like a plain string does; its enrichment metadata is not
        exposed by this method -- use :meth:`hard_deny_entries` for that.

        Args:
            tool_name: Tool to extract hard-deny patterns for (e.g. 'Bash',
                'Read', 'Write', 'Edit').

        Returns:
            Tuple of (deny_patterns, allow_patterns) as immutable, de-duplicated
            tuples pooled across all toolguard_hook layers.
        """
        deny_entries, allow_entries = self._pool_hard_deny_entries(tool_name)
        return (
            tuple(entry.stripped_pattern for entry in deny_entries),
            tuple(entry.stripped_pattern for entry in allow_entries),
        )

    def hard_deny_entries(
        self, tool_name: str
    ) -> Tuple[Tuple[RuleEntry, ...], Tuple[RuleEntry, ...]]:
        """
        Return the pooled hard-deny (deny_entries, allow_entries) for a tool,
        as wrapper-INTACT :class:`RuleEntry` objects carrying enrichment
        metadata.

        Companion to :meth:`hard_deny`: same pooling/de-dup/native-skip
        behaviour, but returns the entries themselves rather than stripped
        pattern strings, so a structured entry's metadata (e.g. an
        ``additionalContext`` explaining why a command is hard-denied and
        what to use instead) is reachable.

        Args:
            tool_name: Tool to extract hard-deny entries for (e.g. 'Bash',
                'Read', 'Write', 'Edit').

        Returns:
            Tuple of (deny_entries, allow_entries): immutable, de-duplicated,
            wrapper-intact :class:`RuleEntry` tuples pooled across all
            toolguard_hook layers.
        """
        return self._pool_hard_deny_entries(tool_name)

    @staticmethod
    def _extract_tool_entries(
        raw_list: object, tool_name: str, is_native: bool
    ) -> Tuple[RuleEntry, ...]:
        """
        Normalize and scope one raw permissions list for a tool.

        Runs each raw element through
        :func:`toolguard.rule_entry.normalize_entry` (plain string or
        structured ``{match = ..., ...}`` table), then keeps entries that
        scope to ``tool_name``. An issue from a malformed entry (e.g. an
        unknown enrichment key) is discarded here -- surfaced separately by
        :meth:`Configuration.validation_issues` -- but a successfully
        normalized entry is never dropped for that reason.

        Args:
            raw_list: The raw ``permissions.allow``/``deny``/``ask`` or
                ``hard_deny.deny``/``allow`` value from one config layer.
                Tolerated even when not a list (treated as empty).
            tool_name: Tool to scope entries to (e.g. 'Bash', 'Read').
            is_native: True when this layer is a native Claude settings file --
                gates structured-entry recognition (a structured entry is a
                toolguard extension and is never interpreted from a native
                layer).

        Returns:
            The entries scoped to ``tool_name``, in source order.
        """
        if not isinstance(raw_list, list):
            raw_list = []

        normalized = []
        for perm in raw_list:
            entry, _issues = normalize_entry(perm, is_native=is_native)
            if entry is not None:
                normalized.append(entry)

        return entries_for_tool(tuple(normalized), tool_name)

    def permission_layers(self, tool_name: str) -> Tuple[ToolPatternLayer, ...]:
        """
        Return per-layer allow/deny patterns for a tool, most-specific first.

        Each layer carries provenance and the entries extracted for
        ``tool_name`` from that source, including entries contributed by
        structured (``{match = ..., ...}``) entries --
        ``ToolPatternLayer``'s wrapper-stripped ``allow``/``deny``/``ask``
        pattern tuples are derived properties over these entries, not
        separately populated. Takeover filtering is already applied: when
        takeover mode is enabled, blanket ignored allow patterns are removed
        from native ('claude') layers only. Deny and ask entries are never
        filtered.

        See :class:`Configuration`'s own docstring for how this feeds the
        more-specific-wins resolver vs. :meth:`allow_deny_for`'s flattened
        view.

        Args:
            tool_name: Tool to extract patterns for (e.g. 'Bash', 'Read').

        Returns:
            Tuple of :class:`ToolPatternLayer`, ordered most-specific first.
        """
        takeover = self.takeover_mode()
        ignored = (
            takeover.normalized_ignored_patterns() if takeover.enabled else frozenset()
        )

        result = []

        for layer in self.layers:
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                permissions = {}

            allow_entries = self._extract_tool_entries(
                permissions.get("allow", []), tool_name, layer.is_native
            )
            if takeover.enabled and layer.is_native:
                allow_entries = tuple(
                    entry
                    for entry in allow_entries
                    if entry.stripped_pattern not in ignored
                )

            deny_entries = self._extract_tool_entries(
                permissions.get("deny", []), tool_name, layer.is_native
            )
            ask_entries = self._extract_tool_entries(
                permissions.get("ask", []), tool_name, layer.is_native
            )

            result.append(
                ToolPatternLayer(
                    provenance=layer.provenance,
                    allow_entries=allow_entries,
                    deny_entries=deny_entries,
                    ask_entries=ask_entries,
                )
            )

        return tuple(result)

    def permission_levels_with_provenance(
        self, tool_name: str
    ) -> Tuple[
        Tuple[
            Tuple[str, ...],
            Tuple[str, ...],
            Tuple[str, ...],
            Tuple[ToolPatternLayer, ...],
        ],
        ...,
    ]:
        """
        Group per-layer patterns for a tool into per-LEVEL pairs, retaining
        each level's contributing layers.

        Layers sharing a specificity (e.g. a ``.local`` and a regular file in the
        same ``.claude`` directory) are collapsed into a single level, preserving
        within-level priority order. Levels are returned most-specific first --
        the order the more-specific-wins resolver consumes. The contributing
        :class:`ToolPatternLayer` objects are retained alongside the collapsed
        patterns so a matched pattern can be mapped back to its exact source
        file/level via :attr:`ToolPatternLayer.provenance`.

        Args:
            tool_name: Tool to resolve patterns for (e.g. 'Bash', 'Read').

        Returns:
            Tuple of (allow_patterns, deny_patterns, ask_patterns, layers) tuples,
            one per hierarchy level, ordered most-specific first.
        """
        grouped: Dict[
            int, Tuple[List[str], List[str], List[str], List[ToolPatternLayer]]
        ] = {}
        order: List[int] = []
        for layer in self.permission_layers(tool_name):
            spec = layer.provenance.specificity
            if spec not in grouped:
                grouped[spec] = ([], [], [], [])
                order.append(spec)
            allow_acc, deny_acc, ask_acc, layers_acc = grouped[spec]
            allow_acc.extend(layer.allow)
            deny_acc.extend(layer.deny)
            ask_acc.extend(layer.ask)
            layers_acc.append(layer)
        return tuple(
            (
                tuple(grouped[s][0]),
                tuple(grouped[s][1]),
                tuple(grouped[s][2]),
                tuple(grouped[s][3]),
            )
            for s in order
        )

    def has_any_rules(self, tool_name: str) -> bool:
        """
        Return whether ANY permission rule (allow, deny, ask, or hard_deny on
        either side) is configured for ``tool_name`` at any level.

        Distinguishes a genuinely UNCONFIGURED tool (which should resolve to
        ``'ask'`` so a fresh install is not bricked) from a CONFIGURED tool whose
        rules simply do not match the current command/path (which is governed by
        :meth:`resolved_no_match_fallback`). Reads the RAW, un-takeover-filtered
        rules -- unlike :meth:`permission_layers`, a native allow that takeover
        mode suppresses still counts as "configured" here, so a suppressed-away
        tool falls through to ``resolved_no_match_fallback`` instead of being
        misread as never configured at all.

        Args:
            tool_name: Tool to check (e.g. ``'Bash'``, ``'Read'``, ``'Write'``,
                ``'Edit'``).

        Returns:
            ``True`` when at least one allow/deny/ask/hard_deny pattern exists
            for ``tool_name`` anywhere in the hierarchy.
        """
        for layer in self.layers:
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                continue
            for perm_type in ("allow", "deny", "ask"):
                if self._extract_tool_entries(
                    permissions.get(perm_type, []), tool_name, layer.is_native
                ):
                    return True
        hd_deny, hd_allow = self.hard_deny(tool_name)
        return bool(hd_deny or hd_allow)

    def _first_toplevel_str_setting(self, key: str) -> Optional[str]:
        """
        Return the first non-native layer's raw string value for a top-level
        ``toolguard_hook`` scalar setting key.

        Most-specific layer wins; a non-string value (e.g. a stray table) is
        treated as not set, same as absence.

        Args:
            key: The top-level ``toolguard_hook`` key to look up.

        Returns:
            The first matching layer's raw string value, or ``None`` when
            unset. Does not resolve aliases or validate against a recognized
            set.
        """
        for layer in self.layers:
            if layer.is_native:
                continue
            if key in layer.content:
                value = layer.content[key]
                if isinstance(value, str):
                    return value
        return None

    def _resolve_fallback_setting(
        self,
        key: str,
        valid_values: frozenset,
        default: str,
        legacy_alias: Optional[Callable[[], Optional[str]]] = None,
        alias_map: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Resolve one "fallback"-shaped ``toolguard_hook`` setting.

        Args:
            key: The top-level ``toolguard_hook`` key (see
                :meth:`_first_toplevel_str_setting`).
            valid_values: The recognized value set for this setting.
            default: Value to use when unset or unrecognized.
            legacy_alias: Optional zero-arg callable returning a raw legacy
                value to fall back to when no layer sets *key*. ``None`` means
                this setting has no legacy alias.
            alias_map: Optional ``{spelling: canonical}`` mapping applied
                AFTER the legacy-alias fallback, regardless of which
                mechanism supplied the raw value -- covers both a deprecated
                spelling being phased out (e.g. ``no_match_fallback``'s
                ``'warn_deny'`` -> ``'allow_with_warning'``) and a permanent,
                non-deprecated synonym (``'allow_with_no_warnings'`` ->
                ``'allow'``). ``None`` means this setting has no alternate
                spelling to normalize.

        Returns:
            The resolved, validated setting value.
        """
        raw = self._first_toplevel_str_setting(key)
        if raw is None and legacy_alias is not None:
            raw = legacy_alias()
        if alias_map and raw in alias_map:
            raw = alias_map[raw]
        return raw if raw in valid_values else default

    def resolved_no_match_fallback(self) -> str:
        """
        Resolve the effective ``no_match_fallback`` setting -- the floor
        applied when a command was read but no rule covered it, unlike
        :meth:`resolved_undecidable_fallback`, which covers a command that
        could not be read at all.

        Top-level ``toolguard_hook`` key, most-specific layer wins, in both
        takeover and non-takeover modes. The legacy
        ``[takeover_mode].no_match_fallback`` alias is honoured only when no
        layer sets the top-level key; when both are set, the top-level key
        wins outright regardless of specificity. See technical-notes.md for
        why this setting carries the ``[takeover_mode]`` alias and the
        deprecated ``warn_deny`` spelling that
        :meth:`resolved_undecidable_fallback` does not.

        Returns:
            One of ``'ask'``, ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'``; unset or unrecognized resolves to ``'ask'``.
        """
        return self._resolve_fallback_setting(
            "no_match_fallback",
            _VALID_NO_MATCH_FALLBACKS,
            _DEFAULT_NO_MATCH_FALLBACK,
            legacy_alias=lambda: self.takeover_mode().no_match_fallback,
            alias_map={
                "warn_deny": "allow_with_warning",
                **_ALLOW_NO_WARNINGS_ALIAS,
            },
        )

    def resolved_undecidable_fallback(self) -> str:
        """
        Resolve the effective ``undecidable_fallback`` -- the floor applied
        when a command could not be read safely at all (foreign inline code,
        heredoc sinks, complex control structures), unlike
        :meth:`resolved_no_match_fallback`, which covers a command that *was*
        read and matched nothing. Applied by
        :func:`toolguard.compound._apply_undecidable_floor`.

        Top-level ``toolguard_hook`` key only, most-specific layer wins, in
        both takeover and non-takeover modes. Deliberately has no
        ``[takeover_mode]`` alias -- see technical-notes.md.

        Returns:
            One of ``'ask'``, ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'``; unset or unrecognized resolves to ``'ask'``.
        """
        return self._resolve_fallback_setting(
            "undecidable_fallback",
            _VALID_UNDECIDABLE_FALLBACKS,
            _DEFAULT_UNDECIDABLE_FALLBACK,
            alias_map=_ALLOW_NO_WARNINGS_ALIAS,
        )

    def unrecognized_fallback_settings(
        self,
    ) -> Tuple[UnrecognizedFallbackSetting, ...]:
        """
        Find every layer that sets a ``*_fallback`` key to an unusable value.

        Both :meth:`resolved_no_match_fallback` and
        :meth:`resolved_undecidable_fallback` fall back to ``'ask'`` when the
        configured value is not recognized -- the safe direction, and not
        changed here. Without this diagnostic that failure is silent:
        ``no_match_fallback = "allow_with_no_warning"`` (singular) would
        produce maximum-friction ``ask`` behaviour that reads as a broken
        feature rather than a typo.

        Two kinds of unusable value are reported, because both are equally
        silent:

        - a string that is not a recognized spelling after the alias map for
          THAT key -- ``allow_with_no_warnings`` is recognized for both keys,
          but ``warn_deny`` is recognized (and so never reported) only for
          ``no_match_fallback``; it IS reported for ``undecidable_fallback``,
          which has no such alias (see technical-notes.md);
        - a non-string value (a bool, a number, a table). These are treated as
          "not set" by :meth:`_first_toplevel_str_setting`, which is the same
          silent outcome.

        EVERY offending layer is reported, not just the winning one. A bad
        value at a less-specific level is inert today but is still a typo, and
        it becomes live the moment the more-specific level that masks it is
        removed.

        Scope: the TOP-LEVEL ``no_match_fallback`` / ``undecidable_fallback``
        keys. The deprecated ``[takeover_mode].no_match_fallback`` alias is not
        covered -- it is resolved through :class:`~toolguard.config_types.TakeoverConfig`,
        which does not retain per-layer provenance for that field, so it cannot
        name the file the way this warning must.

        Returns:
            Tuple of :class:`~toolguard.config_types.UnrecognizedFallbackSetting`,
            in layer order (most-specific first), ``no_match_fallback`` before
            ``undecidable_fallback`` within a layer.
        """
        valid_by_key = {
            "no_match_fallback": _VALID_NO_MATCH_FALLBACKS,
            "undecidable_fallback": _VALID_UNDECIDABLE_FALLBACKS,
        }
        alias_by_key = {
            "no_match_fallback": {
                "warn_deny": "allow_with_warning",
                **_ALLOW_NO_WARNINGS_ALIAS,
            },
            "undecidable_fallback": dict(_ALLOW_NO_WARNINGS_ALIAS),
        }
        found: List[UnrecognizedFallbackSetting] = []
        for layer in self.layers:
            if layer.is_native:
                continue
            for key, valid_values in valid_by_key.items():
                if key not in layer.content:
                    continue
                raw = layer.content[key]
                normalized = (
                    alias_by_key[key].get(raw, raw) if isinstance(raw, str) else raw
                )
                if isinstance(normalized, str) and normalized in valid_values:
                    continue
                found.append(
                    UnrecognizedFallbackSetting(
                        key=key,
                        value=str(raw),
                        provenance=layer.provenance,
                        accepted=_ACCEPTED_FALLBACK_SPELLINGS,
                    )
                )
        return tuple(found)

    def allow_deny_for(self, tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return flattened, de-duplicated (allow, deny) patterns for a tool.

        Flattens :meth:`permission_layers`: union across layers in discovery
        order with duplicates removed, for callers that don't need per-level
        (more-specific-wins) resolution. Global deny-first matching is applied
        downstream by the matching code, not here.

        Args:
            tool_name: Tool to resolve patterns for.

        Returns:
            Tuple of (allow_patterns, deny_patterns) as immutable tuples.
        """
        seen_allow: Dict[str, None] = {}
        seen_deny: Dict[str, None] = {}
        for layer in self.permission_layers(tool_name):
            for p in layer.allow:
                seen_allow.setdefault(p, None)
            for p in layer.deny:
                seen_deny.setdefault(p, None)
        return tuple(seen_allow.keys()), tuple(seen_deny.keys())

    # -- scalars -----------------------------------------------------------

    def scalar(self, name: str, default=None):
        """
        Resolve a top-level scalar setting from a named config section.

        Supports dotted names of the form ``'section.key'`` (e.g.
        ``'config_sync.backup_dir'``). Reads only from toolguard_hook layers.

        Resolution is MORE-SPECIFIC-WINS: the value comes from the
        most-specific level that defines it -- project beats ancestor beats
        user. Layers are already ordered most-specific first, so the FIRST
        layer that defines the key wins and iteration stops. A bare ``name``
        resolves a top-level key directly.

        Args:
            name: Scalar name, optionally ``'section.key'``.
            default: Value to return when the scalar is absent.

        Returns:
            The resolved value, or ``default`` if not found.
        """
        section: Optional[str]
        if "." in name:
            section, key = name.split(".", 1)
        else:
            section, key = None, name

        for layer in self.layers:
            if layer.is_native:
                continue
            content = layer.content
            if section is not None:
                sect = content.get(section, {})
                if isinstance(sect, dict) and key in sect:
                    return sect[key]
            else:
                if key in content:
                    return content[key]
        return default

    def config_sync_settings(self) -> Mapping:
        """
        Return resolved config_sync settings as a read-only mapping.

        Each value resolves more-specific-wins via :meth:`scalar`: the
        most-specific level that defines a key wins (project beats ancestor
        beats user). Missing keys fall back to the documented defaults.

        Returns:
            Read-only mapping with keys ``auto_migrate``, ``backup_dir``,
            ``auto_sort_on_migrate``.
        """
        return MappingProxyType(
            {
                key: self.scalar(f"config_sync.{key}", default)
                for key, default in _CONFIG_SYNC_DEFAULTS.items()
            }
        )

    # -- raw toolguard permissions (for divergence / migration) -----------

    def toolguard_permissions(self) -> Mapping:
        """
        Return raw (wrapper-intact) permissions from toolguard_hook layers.

        Aggregates allow/deny/ask entries (exact, with tool wrappers) across
        all toolguard_hook layers, de-duplicated and order-preserving.

        Every raw element is routed through
        :func:`toolguard.rule_entry.normalize_entries_preserving` rather than
        a plain ``isinstance(perm, str)`` filter, which would silently drop
        any structured (``dict``) entry -- and since this method's whole
        purpose is describing what should be WRITTEN back, a dropped entry
        here gets deleted by the next migration that overwrites the file. An
        element that fails to normalize is still preserved (never dropped).

        Values are kept wrapper-INTACT (unlike :meth:`permission_layers`,
        which strips), so the result is usable without a ``tool_name``.

        Returns:
            Read-only mapping with keys 'allow', 'deny', 'ask', each a tuple of
            :class:`~toolguard.rule_entry.RuleEntry`.
        """
        result: Dict[str, List[RuleEntry]] = {"allow": [], "deny": [], "ask": []}
        # De-dup keys on `.pattern` alone; first (most-specific) occurrence
        # wins -- see RuleEntry.identity().
        seen: Dict[str, Set[str]] = {"allow": set(), "deny": set(), "ask": set()}
        for layer in self.layers:
            if layer.is_native:
                continue
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                continue
            for perm_type in ("allow", "deny", "ask"):
                # is_native=False is always correct here: native layers were
                # already skipped above, so every element normalize_entries_preserving
                # sees belongs to a toolguard_hook layer.
                for entry in normalize_entries_preserving(
                    permissions.get(perm_type, []), is_native=False
                ):
                    if entry.pattern not in seen[perm_type]:
                        seen[perm_type].add(entry.pattern)
                        result[perm_type].append(entry)
        return MappingProxyType({k: tuple(v) for k, v in result.items()})

    # -- validation --------------------------------------------------------

    def validation_issues(self) -> Tuple[Issue, ...]:
        """
        Return structured content-level configuration issues.

        Detects:

        - A governed config file that failed to parse entirely -- reported
          FIRST, since it is the most severe class of issue: every decision
          is clamped to 'ask' while it persists.
        - Both a TOML and a JSON config file present at the same level/base.
        - A rules-directory filename stem shadowed across the two candidate
          rules directories.
        - A ``no_match_fallback``/``undecidable_fallback`` value toolguard
          does not recognize.
        - A non-boolean ``takeover_mode.enabled``.
        - A rules-directory file defining a top-level key outside
          ``[permissions]``/``[hard_deny]``.
        - Unsupported tools referenced in toolguard_hook permissions.
        - Tools referenced in permissions but absent from governed_tools.

        The config module only RETURNS issues; logging is the hook's job.

        Returns:
            Tuple of :class:`Issue`, in the detection order shown above --
            parse-failure issues first, permission-validation issues last.
        """
        issues: List[Issue] = []

        # 0) A governed config file failed to parse entirely. This is
        #    an 'error', not a 'warning': permission_resolution's ASK floor
        #    clamps every decision except an already-'deny' one to 'ask'
        #    while any entry remains (see Configuration.parse_failures's
        #    docstring), so a rule in this file -- possibly a deny or
        #    hard_deny -- may be silently unenforced.
        for path, message in self.parse_failures:
            issues.append(
                Issue(
                    level="error",
                    message=f"{path} failed to parse and was skipped: {message}",
                    corrective_steps=(
                        "Fix the file's syntax. Until it parses, EVERY toolguard "
                        "permission decision is clamped to 'ask' (see "
                        "toolguard.permission_resolution.resolve_permission_cascade) "
                        "so no rule -- including deny/hard_deny -- in this file is "
                        "silently lost."
                    ),
                )
            )

        # 1) Both a TOML and a JSON config file present for the same base in the
        #    same directory -> warn (the tool is using TOML). This is the single
        #    source of truth for the warning: discovery itself is side-effect-free
        #    and the hook routes these Issues to the WARNING stream. A duplicate
        #    is recognised either by two discovered layers of differing format at
        #    the same base, OR -- since real discovery keeps only the TOML -- by
        #    both files existing on disk.
        seen_formats: Dict[Tuple[str, str], set] = {}
        order: List[Tuple[str, str]] = []
        for layer in self.layers:
            path = layer.provenance.path
            base_name = path.stem
            parent = path.parent
            key = (str(parent), base_name)
            if key not in seen_formats:
                seen_formats[key] = set()
                order.append(key)
                # Augment with on-disk presence so the warning fires in real
                # usage (where discovery dropped the JSON sibling).
                for fmt, suffix in (("toml", ".toml"), ("json", ".json")):
                    if (parent / f"{base_name}{suffix}").exists():
                        seen_formats[key].add(fmt)
            if layer.duplicate_format:
                # Recorded at discovery time (see load_configuration); does not
                # depend on the source directory still existing on disk, unlike
                # the on-disk check above (needed for rules-dir layers).
                seen_formats[key].add("toml")
                seen_formats[key].add("json")
            seen_formats[key].add(layer.provenance.file_format)

        for parent_str, base_name in order:
            if len(seen_formats[(parent_str, base_name)]) > 1:
                issues.append(
                    Issue(
                        level="warning",
                        message=f"Both {base_name}.toml and {base_name}.json exist in {parent_str}",
                        corrective_steps=(
                            f"Remove one of the files to avoid confusion. TOML ({base_name}.toml) is being used."
                        ),
                    )
                )

        # 1b) A rules-directory filename stem shadowed across the two candidate
        #     rules directories -- see _shadowed_rules_stems for why this must
        #     warn. Recorded on the winning layer at discovery time (see
        #     load_configuration), same pattern as duplicate_format above.
        for layer in self.layers:
            if layer.shadowed_path is None:
                continue
            issues.append(
                Issue(
                    level="warning",
                    message=(
                        f"{layer.provenance.path} shadows {layer.shadowed_path}, "
                        "which is ignored (same filename stem present in both "
                        "candidate rules directories; the XDG rules directory "
                        "takes precedence)"
                    ),
                    corrective_steps=(
                        "Remove or rename one of the two files so the same "
                        "filename stem does not exist in both "
                        "~/.config/toolguard/rules (or $XDG_CONFIG_HOME/"
                        "toolguard/rules) and ~/.toolguard/rules -- the "
                        "ignored file's rules are not enforced."
                    ),
                )
            )

        # 1c) A *_fallback setting written with a value toolguard does not
        #     recognize. Resolution silently falls back to 'ask',
        #     which is the safe direction but is indistinguishable from a
        #     broken feature when nothing says so. A 'warning', not an 'error':
        #     the effective behaviour is the SAFE one, unlike the fail-open
        #     classes above. Also surfaced at session start (see
        #     toolguard/session_start.py) -- the log alone is not loud enough
        #     for something that presents as maximum friction with no cause.
        for bad in self.unrecognized_fallback_settings():
            issues.append(
                Issue(
                    level="warning",
                    message=bad.describe(),
                    corrective_steps=(
                        f"Set {bad.key} to one of: {', '.join(bad.accepted)}. "
                        f"Until then it resolves to 'ask', which prompts for "
                        f"everything the setting was meant to decide."
                    ),
                )
            )

        # 2) takeover_mode.enabled is a fail-safe security toggle: a non-bool
        #    value is not coerced (see takeover_mode); flag it as an error so the
        #    misconfiguration is visible rather than silently ignored.
        for layer in self.layers:
            if layer.is_native:
                continue
            section = layer.content.get("takeover_mode", {})
            if not isinstance(section, dict) or "enabled" not in section:
                continue
            if not isinstance(section["enabled"], bool):
                issues.append(
                    Issue(
                        level="error",
                        message=(
                            f"takeover_mode.enabled in {layer.provenance.describe()} is "
                            f"{type(section['enabled']).__name__}, not a boolean; it is ignored"
                        ),
                        corrective_steps=(
                            "Set takeover_mode.enabled to a boolean (true/false). "
                            "Non-boolean values are not coerced and the level does not "
                            "participate in resolving takeover mode."
                        ),
                    )
                )

        # 3) Rules-directory layers may only define [permissions] and
        #    [hard_deny]. Any other top-level key found in the raw file was
        #    stripped before the layer's content was built (load_configuration)
        #    and recorded on unexpected_keys -- surface it here as an error so
        #    the misconfiguration is visible (fail loud) rather than silently
        #    dropped. This does NOT block the layer's valid permissions/hard_deny
        #    content, which still resolves normally.
        for layer in self.layers:
            if not layer.unexpected_keys:
                continue
            keys_str = ", ".join(layer.unexpected_keys)
            issues.append(
                Issue(
                    level="error",
                    message=(
                        f"{layer.provenance.describe_brief()} defines unsupported "
                        f"top-level key(s) for a rules-directory file: {keys_str}"
                    ),
                    corrective_steps=(
                        "Rules-directory files (~/.config/toolguard/rules/*.toml "
                        "or *.json) may only contain [permissions] and "
                        "[hard_deny] sections. Move scalar/singleton settings "
                        "(governed_tools, no_match_fallback, [takeover_mode], "
                        "[config_sync], etc.) to the primary "
                        "~/.claude/toolguard_hook.toml."
                    ),
                )
            )

        # 4) Permission validation over the merged toolguard_hook content only.
        merged_config: Dict = {
            "governed_tools": [],
            "additional_supported_tools": [],
            "permissions": {"allow": [], "deny": [], "ask": []},
        }
        for layer in self.layers:
            if layer.is_native:
                continue
            content = layer.content
            for tool in content.get("governed_tools", []):
                if tool not in merged_config["governed_tools"]:
                    merged_config["governed_tools"].append(tool)
            for tool in content.get("additional_supported_tools", []):
                if tool not in merged_config["additional_supported_tools"]:
                    merged_config["additional_supported_tools"].append(tool)
            permissions = content.get("permissions", {})
            if isinstance(permissions, dict):
                for perm_type in ("allow", "deny", "ask"):
                    for perm in permissions.get(perm_type, []):
                        if perm not in merged_config["permissions"][perm_type]:
                            merged_config["permissions"][perm_type].append(perm)
            elif permissions:
                # e.g. [[permissions]] (array of tables) instead of
                # [permissions]: parses cleanly but every rule in the layer
                # is unmergeable, so record the loss instead of silently
                # dropping the layer's whole permissions section.
                issues.append(
                    Issue(
                        level="error",
                        message=(
                            f"{layer.provenance.describe_brief()} permissions "
                            f"section is not a table (found "
                            f"{type(permissions).__name__}); every rule in it "
                            f"was discarded"
                        ),
                        corrective_steps=(
                            'Write it as "[permissions]" with allow/deny/ask '
                            'arrays, not "[[permissions]]".'
                        ),
                    )
                )

        issues.extend(validate_permissions(merged_config))

        return tuple(issues)

    # -- provenance / introspection ---------------------------------------

    def describe_sources(self) -> Tuple[str, ...]:
        """Return human-readable descriptions of all discovered sources."""
        return tuple(layer.provenance.describe() for layer in self.layers)

    def describe_levels(self) -> Tuple[str, ...]:
        """
        Return concise ``level: path`` descriptions, one per discovered source.

        Ordered most-specific first, mirroring layer order.

        Returns:
            Tuple of ``"<level>: <path>"`` strings.
        """
        return tuple(layer.provenance.describe_brief() for layer in self.layers)


def _multiline_structured_entry_diagnostic(
    path: Path, error: tomllib.TOMLDecodeError
) -> str:
    """
    Build a diagnostic message for a TOML parse failure, naming the specific
    cause when it is identifiable.

    Currently detects exactly one cause, chosen because it is this project's
    single highest-impact TOML mistake: a structured permission entry
    (``{ match = "...", ... }``) written across multiple physical lines.
    TOML 1.0 forbids that (an inline table must sit on one physical line);
    ``tomllib``'s own error for it is a generic, unhelpful one (e.g.
    ``"Invalid initial character for a key part (at line N, column M)"``)
    that does not point a user at the actual mistake, let alone explain that
    it silently disabled every OTHER rule in the same file too.

    Detection re-reads *path* as text and scans it with
    :func:`toolguard.toml_scan.find_multiline_structured_entry_line`, which
    reuses this project's single existing permission-array scanner rather
    than a second TOML parser (see that function's docstring). If the file
    cannot be re-read, or no multi-line structured entry is found in it (the
    failure has some other cause -- a typo, a missing quote, anything else),
    this falls back to ``tomllib``'s own message UNCHANGED: a wrong guess
    here (misattributing an unrelated syntax error to this cause) would be
    worse than the generic message.

    Args:
        path: The file that failed to parse.
        error: The ``TOMLDecodeError`` raised while parsing it.

    Returns:
        An actionable message when the multi-line cause is detected,
        otherwise ``str(error)`` unchanged.
    """
    try:
        text = path.read_text()
    except OSError:
        return str(error)

    line = find_multiline_structured_entry_line(text)
    if line is None:
        return str(error)

    return (
        f"structured rule entry starting at line {line} spans multiple physical "
        "lines, which is not valid TOML 1.0 (an inline table must be written on "
        "a single line). Rewrite it as one line, e.g. "
        '\'{ match = "...", additionalContext = "..." }\'.'
    )


def _try_parse_source(
    path: Path, file_format: str
) -> Tuple[Optional[dict], Optional[str]]:
    """
    Attempt to parse a single config source file, without printing anything.

    A syntactically valid file whose top level is not an object/table (e.g. a
    bare JSON array) is treated the same as an unparseable file, rather than
    raising a raw ``AttributeError``/``TypeError`` -- a shape mistake in one
    rules-directory file must not crash discovery for every other file.

    A ``TOMLDecodeError`` gets an upgraded, actionable message when its cause
    is identifiable (currently: a multi-line structured entry -- see
    :func:`_multiline_structured_entry_diagnostic`); any other parse or read
    failure keeps the plain ``str(exception)`` message it always had.

    Args:
        path: Path to the config file.
        file_format: 'json' or 'toml'.

    Returns:
        ``(content, message)``. On success, ``(dict, None)``. On any failure
        (unreadable, malformed, or top level not an object/table),
        ``(None, message)`` where ``message`` is never empty.
    """
    try:
        content = load_config_file(path, file_format)
        if not isinstance(content, dict):
            raise TypeError(
                f"expected a top-level object/table, got {type(content).__name__}"
            )
        return content, None
    except tomllib.TOMLDecodeError as e:
        return None, _multiline_structured_entry_diagnostic(path, e)
    except Exception as e:  # noqa: BLE001 - tolerate any unreadable source
        return None, str(e)


def _parse_source(path: Path, file_format: str) -> Optional[dict]:
    """
    Parse a single config source file, returning its dict or None on failure.

    Delegates to :func:`_parse_source_recording_failures` with a fresh,
    throwaway accumulator: the failure is printed but never recorded onto
    :attr:`Configuration.parse_failures`, so it cannot trigger the ASK-floor
    clamp; the file is simply skipped, with only a warning.

    Args:
        path: Path to the config file.
        file_format: 'json' or 'toml'.

    Returns:
        Parsed dict, or None if the file cannot be read/parsed, or its
        top level is not an object/table.
    """
    return _parse_source_recording_failures(path, file_format, [])


def _parse_source_recording_failures(
    path: Path, file_format: str, parse_failures: List[Tuple[Path, str]]
) -> Optional[dict]:
    """
    Parse *path*, printing a warning on failure, and additionally recording a
    parse failure into *parse_failures* when the file existed but failed to
    parse.

    A missing file is never recorded here -- only one that was found and was
    broken, which is what feeds the ASK-floor clamp (see
    :attr:`Configuration.parse_failures`).

    Args:
        path: Path to parse.
        file_format: 'json' or 'toml'.
        parse_failures: Accumulator list to append ``(path, message)`` to on
            a genuine (file-exists) parse failure.

    Returns:
        Parsed dict, or None on any failure (missing or broken).
    """
    content, message = _try_parse_source(path, file_format)
    if message is not None:
        report_warning(
            f"Failed to load {path}: {message}",
            f"Fix or remove {path} so toolguard can read it.",
        )
        if path.exists():
            parse_failures.append((path, message))
    return content


def load_configuration(
    start_dir: Path = None, ignore_env_override: bool = False
) -> Configuration:
    """
    Load the toolguard configuration as an immutable :class:`Configuration`.

    This is the single public entry point. It performs all discovery and
    parsing internally and returns a file/format-agnostic view. When
    ``CLAUDE_SETTINGS_PATH`` is set, a single explicit source (plus any adjacent
    ``toolguard_hook`` file) is used, bypassing the hierarchy -- matching the
    legacy behaviour. The runtime hook relies on ``CLAUDE_SETTINGS_PATH``
    being honoured, so ``ignore_env_override`` defaults to ``False``.

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to
            the current working directory.
        ignore_env_override: When True, ignore ``CLAUDE_SETTINGS_PATH`` and
            always discover the hierarchy rooted at the project, so a stale
            ``CLAUDE_SETTINGS_PATH`` pointing at an unrelated project cannot
            affect the result.

    Returns:
        An immutable :class:`Configuration`.
    """
    layers: List[ConfigLayer] = []
    # Accumulates (path, message) for every governed file that EXISTED but
    # failed to parse, across whichever branch below runs. Passed to both
    # Configuration(...) construction points so parse_failures is populated
    # regardless of which mode (explicit CLAUDE_SETTINGS_PATH vs. hierarchy
    # discovery) is active.
    parse_failures: List[Tuple[Path, str]] = []

    settings_path = (
        None if ignore_env_override else ambient.env_var("CLAUDE_SETTINGS_PATH")
    )
    if settings_path:
        explicit = Path(settings_path)
        content = _parse_source_recording_failures(explicit, "json", parse_failures)
        if content is not None:
            layers.append(
                ConfigLayer(
                    provenance=Provenance("explicit", "claude", "json", explicit),
                    content=MappingProxyType(content),
                )
            )
        settings_dir = explicit.parent
        hook_toml = settings_dir / "toolguard_hook.toml"
        hook_json = settings_dir / "toolguard_hook.json"
        if hook_toml.exists():
            content = _parse_source_recording_failures(
                hook_toml, "toml", parse_failures
            )
            if content is not None:
                layers.append(
                    ConfigLayer(
                        provenance=Provenance(
                            "explicit", "toolguard_hook", "toml", hook_toml
                        ),
                        content=MappingProxyType(content),
                    )
                )
        elif hook_json.exists():
            content = _parse_source_recording_failures(
                hook_json, "json", parse_failures
            )
            if content is not None:
                layers.append(
                    ConfigLayer(
                        provenance=Provenance(
                            "explicit", "toolguard_hook", "json", hook_json
                        ),
                        content=MappingProxyType(content),
                    )
                )
        return Configuration(
            layers=tuple(layers),
            start_dir=start_dir,
            parse_failures=tuple(parse_failures),
        )

    # Computed lazily (at most once), here during discovery, so
    # validation_issues() never has to re-check a rules directory that may be
    # gone by the time it runs (e.g. an isolated test's tempdir).
    rules_duplicate_stems: Optional[frozenset] = None
    rules_shadowed_stems: Optional[Dict[str, Path]] = None

    for path, source_type, file_format, specificity, level in _discover_levels(
        start_dir
    ):
        content = _parse_source_recording_failures(path, file_format, parse_failures)
        if content is None:
            continue
        unexpected_keys: Tuple[str, ...] = ()
        duplicate_format = False
        shadowed_path: Optional[Path] = None
        if source_type == "toolguard_hook_rules":
            # Rules-directory files are restricted to [permissions]/[hard_deny].
            # Any other top-level key is recorded for
            # Configuration.validation_issues() to report as an error, and
            # stripped from the content the rest of the module sees -- so
            # governed_tools()/scalar()/takeover_mode()/etc. never observe it.
            unexpected_keys = tuple(
                key for key in content if key not in _RULES_FILE_ALLOWED_SECTIONS
            )
            content = {
                key: value
                for key, value in content.items()
                if key in _RULES_FILE_ALLOWED_SECTIONS
            }
            if rules_duplicate_stems is None:
                rules_duplicate_stems = frozenset(
                    stem
                    for stem, formats in _merged_rules_by_stem(_rules_dirs()).items()
                    if len(formats) > 1
                )
            if rules_shadowed_stems is None:
                rules_shadowed_stems = _shadowed_rules_stems(_rules_dirs())
            duplicate_format = path.stem in rules_duplicate_stems
            shadowed_path = rules_shadowed_stems.get(path.stem)
        layers.append(
            ConfigLayer(
                provenance=Provenance(
                    level, source_type, file_format, path, specificity
                ),
                content=MappingProxyType(content),
                unexpected_keys=unexpected_keys,
                duplicate_format=duplicate_format,
                shadowed_path=shadowed_path,
            )
        )

    return Configuration(
        layers=tuple(layers), start_dir=start_dir, parse_failures=tuple(parse_failures)
    )


# ---------------------------------------------------------------------------
# Legacy config_sync settings lookup
# ---------------------------------------------------------------------------


def config_sync_settings_from_sources(
    config_files: List[Tuple[Path, str, str]],
) -> Dict:
    """
    Resolve config_sync settings from toolguard_hook sources.

    Parses each toolguard_hook source and applies last-occurrence-wins
    resolution over discovery order, returning defaults for missing values.

    Legacy path: never builds or feeds a :class:`Configuration`, so a parse
    failure here cannot trigger the ASK-floor clamp -- it falls back to this
    function's own defaults. Real enforcement is still governed by the
    normal ``load_configuration()`` path.

    Args:
        config_files: List of (path, source_type, format) triples.

    Returns:
        Dict with keys 'auto_migrate', 'backup_dir', 'auto_sort_on_migrate'.
    """
    resolved: Dict = dict(_CONFIG_SYNC_DEFAULTS)
    for path, source_type, file_format in config_files:
        if source_type != "toolguard_hook":
            continue
        content = _parse_source(path, file_format)
        if content is None:
            continue
        config_sync = content.get("config_sync", {})
        if not isinstance(config_sync, dict) or not config_sync:
            continue
        for key in _CONFIG_SYNC_DEFAULTS:
            if key in config_sync:
                resolved[key] = config_sync[key]
    return resolved
