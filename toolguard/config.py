"""
Configuration loading for toolguard.

Loads and parses permissions from Claude Code settings files with support for:
- Config file hierarchy (project -> user)
- Extended pattern syntax in toolguard_hook.json files
- Merging permissions from multiple sources

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
``discover_config_files``, and ``config_sync_settings_from_sources`` (used by
``auto_migrate``). That is transitional and tracked as a TOO-8 follow-up; everything else
internal is underscore-prefixed.
"""

import functools
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Dict, List, Mapping, Optional, Set, Tuple

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

# ``Issue`` moved to ``toolguard.issues`` (TOO-19 Phase 0a, increment 1) so
# that leaf modules can depend on it without importing this module, and is
# imported above and re-exported here so existing
# ``from toolguard.config import Issue`` call sites keep working unchanged.
#
# ``is_tool_wrapper`` and ``_strip_tool_wrapper`` similarly moved to
# ``toolguard.rule_entry`` (same increment), together with the
# ``_TOOL_WRAPPER_RE`` regex they both wrap: ``rule_entry.normalize_entry``
# needs the identical wrapper-shape check for structured entries, and
# ``rule_entry`` must stay a leaf module that this module depends on -- not
# the reverse -- so the regex and both predicates over it live there in
# exactly one place. ``_TOOL_WRAPPER_RE`` itself is not re-imported here
# since nothing in this module uses it directly any more (both former
# call sites moved along with the functions); only ``is_tool_wrapper`` is
# imported back and re-exported so the existing importer
# (``toolguard.config_divergence``) keeps working unchanged. TOO-45 R2a:
# this module's own code no longer calls ``_strip_tool_wrapper`` directly
# either -- every internal use now goes through
# :attr:`~toolguard.rule_entry.RuleEntry.stripped_pattern` -- so the
# ``is_tool_wrapper`` import here is a pure re-export as of that change
# (``as`` alias added to say so explicitly). TOO-45 R6-S1: the
# ``_strip_tool_wrapper`` re-export that used to sit alongside it was
# deleted -- it existed only so ``toolguard.tools.takeover_audit`` could
# reach a private name of a module it doesn't otherwise depend on; that
# caller now imports the new public ``toolguard.rule_entry.strip_tool_wrapper``
# directly instead, so nothing re-exports the private name any more.
#
# ``Provenance``, ``ConfigLayer``, ``ToolPatternLayer``,
# ``TakeoverEnabledConflict``, ``TakeoverConfig``, and ``ConflictOverride``
# similarly moved to ``toolguard.config_types`` (TOO-19 structural refactor):
# these are thin data types with no discovery/parsing logic, so they now live
# apart from ``Configuration`` and the machinery that builds and resolves
# them. Imported back and re-exported here (same ``import x as x`` idiom as
# above) so existing ``from toolguard.config import Provenance`` (etc.) call
# sites keep working unchanged.
#
# ``ResolvedDecision`` (the type formerly here) was collapsed into
# ``RuntimeVerdict`` by TOO-45 R1c, along with ``BashResolution``/
# ``FileResolution`` (formerly in ``toolguard.resolve``) -- see
# ``RuntimeVerdict``'s own docstring. Re-exported the same way.

# Default blanket ignored-allow patterns for takeover mode. These seed the
# union of ``ignored_allow_patterns`` so that, when takeover is enabled, the
# usual native blanket allows are suppressed even if no level lists them
# explicitly. Used by the ``Configuration.takeover_mode`` resolver.
_DEFAULT_IGNORED_ALLOW_PATTERNS: Tuple[str, ...] = (
    "Bash(*)",
    "Read(*)",
    "Write(*)",
    "Edit(*)",
    "mcp__jetbrains__execute_terminal_command(*)",
)
_DEFAULT_NO_MATCH_FALLBACK = "ask"
# The recognized ``no_match_fallback`` values (TOO-15; ``'allow'`` added
# TOO-19). Any other (typo/bad config) value is normalized to the default
# rather than propagated. Two spellings are ACCEPTED on input but never
# appear in this set -- both are normalized away before reaching it (see
# ``Configuration.resolved_no_match_fallback``'s ``alias_map``):
# the deprecated legacy value ``warn_deny`` normalizes to
# ``allow_with_warning``, and the deliberate long-form synonym
# ``allow_with_no_warnings`` normalizes to ``allow``. Unlike ``warn_deny``,
# ``allow_with_no_warnings`` is NOT deprecated -- it is a permanent alias that
# exists purely as a human reminder (see that setting's own comment below and
# ``resolved_no_match_fallback``'s docstring for why both spellings stay).
_VALID_NO_MATCH_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning", "allow"})

_DEFAULT_UNDECIDABLE_FALLBACK = "ask"
# The recognized `undecidable_fallback` values (TOO-19; `'allow'` added in the
# same allow/allow_with_no_warnings follow-up). This is a DIFFERENT setting
# from `no_match_fallback` above: `no_match_fallback` answers "I read this
# command and no rule covered it"; `undecidable_fallback` answers "I could
# not safely read this command at all" (foreign inline code / heredoc sinks,
# complex control structures, process substitution -- see
# `toolguard.compound`). It is a brand-new TOO-19 top-level key with NO
# legacy `[takeover_mode]` alias and NO deprecated `'warn_deny'` spelling --
# do not add either "for symmetry" with `no_match_fallback`; that history
# does not apply here. The `allow_with_no_warnings` synonym for `'allow'` IS
# honored here (see `resolved_undecidable_fallback`'s `alias_map`) -- that
# alias is not part of the `warn_deny` history the asymmetry above is about,
# it is a brand-new, deliberately symmetric spelling for both settings.
# See `Configuration.resolved_undecidable_fallback`.
_VALID_UNDECIDABLE_FALLBACKS = frozenset({"ask", "deny", "allow_with_warning", "allow"})

#: Canonical alias applied to BOTH ``no_match_fallback`` and
#: ``undecidable_fallback`` (TOO-19 allow/allow_with_no_warnings work):
#: ``'allow_with_no_warnings'`` is an exact synonym for ``'allow'`` -- allow
#: the command, emit NO warning anywhere. The long spelling exists purely as
#: a human reminder that this is a deliberate, reviewable choice; switching
#: back to the warned variant is a 3-character edit
#: (``allow_with_no_warnings`` -> ``allow_with_warning``). Unlike
#: ``warn_deny`` (below), this is not a deprecated spelling being phased out
#: -- both spellings are permanent and equally supported, so it is a plain
#: module-level constant rather than something scoped to one setting's
#: ``alias_map`` call.
_ALLOW_NO_WARNINGS_ALIAS = {"allow_with_no_warnings": "allow"}

#: The spellings a HUMAN may write for each ``*_fallback`` setting, used only
#: to build the "Accepted values:" part of the unrecognized-value warning
#: (TOO-19 m5; see :meth:`Configuration.unrecognized_fallback_settings`).
#: Deliberately NOT the same as ``_VALID_*_FALLBACKS``, which hold the
#: post-normalization CANONICAL set: a user who typed ``allow_with_no_warning``
#: needs to be shown ``allow_with_no_warnings``, and that spelling never
#: appears in the canonical set because the alias map replaces it first.
#: Equally deliberately EXCLUDES the deprecated ``warn_deny``: it still
#: resolves, so it never triggers this warning, but printing it here would be
#: advertising a spelling that is on its way out.
_ACCEPTED_FALLBACK_SPELLINGS = (
    "allow",
    "allow_with_no_warnings",
    "allow_with_warning",
    "ask",
    "deny",
)

# Documented defaults for the ``config_sync`` section. Single source of truth
# shared by the hierarchical ``Configuration.config_sync_settings`` resolver and
# the legacy ``config_sync_settings_from_sources`` path so the two never drift.
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
    path_str: str, file_format: str, mtime_ns: int, size: int
) -> dict:
    """
    Parse a single config file, memoized on (path, format, mtime, size).

    This is the cache layer behind :func:`load_config_file`. ``mtime_ns`` is part of
    the cache key so that rewriting a file (which changes its modification time)
    transparently invalidates the cached parse -- caching on path alone would return
    stale content. ``size`` is ALSO part of the key: two rewrites landing within the
    same mtime tick (fast successive writes, or a filesystem with coarse mtime
    resolution) would otherwise collide on an unchanged ``mtime_ns`` and serve a
    stale, wrong-sized parse -- a real risk for a read-modify-write caller (e.g. the
    installer seeding self-permissions, or ``migrate_permissions`` merging patterns)
    that could then silently drop rules that are genuinely on disk. ``path_str`` is a
    string (not :class:`Path`) so the key is hashable and stable.

    Args:
        path_str: Filesystem path to the config file, as a string.
        file_format: Either ``'toml'`` or ``'json'``.
        mtime_ns: The file's ``st_mtime_ns`` at the time of the call (cache key only).
        size: The file's ``st_size`` at the time of the call (cache key only).

    Returns:
        The parsed config dictionary.
    """
    return _parse_config_file(path_str, file_format)


def load_config_file(path: Path, file_format: str = "json") -> dict:
    """
    Load and parse a single config file, dispatching on format.

    This is the single internal config-file loader: it replaces the per-site
    ``if file_format == 'toml': tomllib.load(...) else: json.load(...)`` branches and
    memoizes parsing keyed on ``(path, st_mtime_ns, st_size)`` so that the same file
    discovered by multiple entry points in one invocation is parsed at most once,
    while a rewrite of the file is still picked up. ``st_size`` is included alongside
    ``st_mtime_ns`` because two rewrites landing within the same mtime tick would
    otherwise collide on the key and serve a stale parse.

    When the path cannot be ``stat``-ed (e.g. it does not exist), the cache is bypassed
    and the parse is attempted directly so that ``open``'s own ``FileNotFoundError``
    surfaces unchanged -- preserving the exact error boundary callers (and their tests)
    relied on before this consolidation. Nonexistent files are never worth caching.

    Tests that rewrite the SAME path within one process can reset the memo with
    ``_parse_config_file_cached.cache_clear()`` if ever needed (no current caller needs
    it because the mtime+size components of the key already invalidate rewritten
    files in practice).

    This loader RAISES on any failure (missing file, malformed content). Callers are
    responsible for their own error-handling policy (strict vs. lenient) by wrapping the
    call -- mirroring the differing semantics of the original call sites.

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
    except OSError:
        # Unstattable (typically missing): skip the cache and let open() raise.
        return _parse_config_file(str(path), file_format)
    return _parse_config_file_cached(
        str(path), file_format, stat_result.st_mtime_ns, stat_result.st_size
    )


def find_project_root(start_dir: Path = None) -> Path:
    """
    Find the project root by searching for a project anchor or pyproject.toml.

    Climbs up from start_dir (or current directory) until finding the nearest
    marker (a strong project anchor -- ``.git``/``.hg``/``.jj``/``.claude``/
    ``CLAUDE.md`` -- or ``pyproject.toml``), stopping at the home directory or
    filesystem root. This is a thin wrapper around the shared
    :func:`toolguard.path_utils.resolve_project_root` primitive in its
    ``strict=True`` ("nearest marker of any kind wins") shape (TOO-15).

    Args:
        start_dir: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to project root

    Raises:
        RuntimeError: If project root cannot be found
    """
    # Delegates rather than re-deriving. The identical body used to live here
    # AND be imported by toolguard.log_writer, which is what pinned the logging
    # module above the "config" layer -- see require_project_root's own note
    # (TOO-45). Kept as a public name here because callers and the test sandbox
    # both patch `toolguard.config.find_project_root` by that path.
    return require_project_root(start_dir)


def discover_config_files(start_dir: Path = None) -> List[Tuple[Path, str, str]]:
    """
    Discover all applicable config files in priority order.

    TOML files take precedence over JSON when both exist at the same level.

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

    # User level
    user_claude_dir = Path.home() / ".claude"
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
            # TOML file found - use it
            config_files.append((toml_path, source_type, "toml"))
            # NOTE: the "both .toml and .json exist" warning is intentionally NOT
            # emitted here. Detection/emission of the both-formats condition is
            # the SOLE responsibility of Configuration.validation_issues(), which
            # routes it to the warning log stream (TOO-8 Phase 4 single source of
            # truth). Printing it here too would double-surface the warning.
        elif json_exists:
            # JSON file found (or only JSON exists)
            config_files.append((json_path, source_type, "json"))

    return config_files


# Within-level candidates, highest-to-lowest priority. Each entry is
# (base_name, source_type, prefer_toml). Mirrors the ordering used by the legacy
# two-level discover_config_files so within-level behaviour (incl. TOML-over-JSON)
# is identical at every level of the hierarchy.
_LEVEL_CANDIDATES: Tuple[Tuple[str, str, bool], ...] = (
    ("toolguard_hook.local", "toolguard_hook", True),
    ("settings.local", "claude", False),
    ("toolguard_hook", "toolguard_hook", True),
    ("settings", "claude", False),
)

# Top-level sections a rules-directory file (see _rules_dirs()) is allowed to
# contain. Scalars/singletons (governed_tools, no_match_fallback,
# [takeover_mode], [config_sync], etc.) have no natural multi-file merge rule
# and remain the sole responsibility of the primary toolguard_hook.toml (TOO-30).
_RULES_FILE_ALLOWED_SECTIONS = frozenset({"permissions", "hard_deny"})


def _rules_dirs() -> Tuple[Path, Path]:
    """
    Resolve the two candidate user-level rules directories, in precedence order.

    Returns ``(xdg_dir, legacy_dir)``:

    - ``xdg_dir``: ``$XDG_CONFIG_HOME/toolguard/rules`` when ``XDG_CONFIG_HOME``
      is set in the environment to a non-empty string, per the XDG Base
      Directory Specification (an empty string is treated as unset, not as a
      literal empty-string base). Otherwise defaults to
      ``~/.config/toolguard/rules`` (TOO-30).
    - ``legacy_dir``: ``~/.toolguard/rules`` -- a separate, pre-existing
      directory (also used for backups/traces/stage/install-journal.md) that
      predates the XDG convention. A real, hand-authored ruleset placed here
      was found to be silently unenforced because only ``xdg_dir`` was ever
      scanned; both directories are now scanned (TOO-19).

    Both directories are optional and may not exist on disk; callers that need
    to scan them use :func:`_discover_rules_files` (single directory) or
    :func:`_discover_rules_files_multi` (both, in precedence order), which
    tolerate a missing or empty directory.

    When the SAME filename stem is present in both directories, ``xdg_dir``
    wins for the whole stem (both formats) -- mirroring the existing
    TOML-over-JSON precedence used within a single directory. See
    :func:`_merged_rules_by_stem` and :func:`_shadowed_rules_stems`. Both
    directories are otherwise equivalent: files from either merge into the
    same (least-specific, user) hierarchy level -- see :func:`_discover_levels`.

    Returns:
        ``(xdg_dir, legacy_dir)``, in precedence order (XDG first).
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        xdg_dir = Path(xdg_config_home) / "toolguard" / "rules"
    else:
        xdg_dir = Path.home() / ".config" / "toolguard" / "rules"
    legacy_dir = Path.home() / ".toolguard" / "rules"
    return (xdg_dir, legacy_dir)


def _group_rules_files_by_stem(rules_dir: Path) -> Dict[str, Dict[str, Path]]:
    """
    Flat scan of a rules directory, grouping ``*.toml``/``*.json`` files by stem.

    Shared building block behind :func:`_discover_rules_files` (which resolves
    each group down to a single TOML-over-JSON winner) and the duplicate-format
    detection in ``load_configuration()`` (which needs to know, while the
    directory still exists, whether a stem had BOTH formats present -- so that
    fact can be recorded on the resulting layer rather than re-checked against
    disk later, when the directory may no longer exist).

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

    TOML wins over JSON when both are present for a stem, mirroring the
    TOML-over-JSON precedence used elsewhere in the hierarchy. Results are
    sorted lexicographically by stem so merge order and log provenance are
    reproducible run-to-run. Shared by :func:`_discover_rules_files` (single
    directory) and :func:`_discover_rules_files_multi` (TOO-19, across the
    candidate directories from :func:`_rules_dirs`) so the winner-resolution
    rule lives in exactly one place.

    Args:
        by_stem: Mapping of stem to ``{'.toml': path, '.json': path}``, as
            returned by :func:`_group_rules_files_by_stem` or
            :func:`_merged_rules_by_stem`.

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
    scanning is intentionally flat for v1 (TOO-30). When both ``<stem>.toml``
    and ``<stem>.json`` exist for the same stem, only the TOML entry is
    returned (see :func:`_resolve_stem_formats`).

    Args:
        rules_dir: The directory to scan (typically one of the directories
            returned by :func:`_rules_dirs`).

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

    For each filename stem, the FIRST directory in ``rules_dirs`` (in the
    given precedence order) that contains that stem supplies its formats; the
    same stem in any later directory is entirely ignored for content purposes
    -- it is "shadowed" (see :func:`_shadowed_rules_stems`, which detects this
    so it can be surfaced as a warning rather than silently dropped, TOO-19).
    This mirrors :func:`_group_rules_files_by_stem`'s per-directory shape but
    resolves precedence ACROSS directories rather than within one.

    Args:
        rules_dirs: Candidate rules directories, most-preferred first (see
            :func:`_rules_dirs`).

    Returns:
        Mapping of stem to the winning directory's ``{'.toml': path, '.json':
        path}`` sub-mapping (same per-stem shape as
        :func:`_group_rules_files_by_stem`).
    """
    merged: Dict[str, Dict[str, Path]] = {}
    for rules_dir in rules_dirs:
        for stem, formats in _group_rules_files_by_stem(rules_dir).items():
            if stem not in merged:
                merged[stem] = formats
    return merged


def _discover_rules_files_multi(rules_dirs: Tuple[Path, ...]) -> List[Tuple[Path, str]]:
    """
    Flat, non-recursive scan across multiple rules directories (TOO-19).

    Applies :func:`_merged_rules_by_stem` for cross-directory,
    first-directory-wins stem precedence, then TOML-over-JSON WITHIN the
    winning directory for each stem via :func:`_resolve_stem_formats` --
    exactly as :func:`_discover_rules_files` does for a single directory.

    Args:
        rules_dirs: Candidate rules directories, most-preferred first (see
            :func:`_rules_dirs`).

    Returns:
        List of ``(path, format)`` pairs, sorted ascending by filename stem.
    """
    return _resolve_stem_formats(_merged_rules_by_stem(rules_dirs))


def _shadowed_rules_stems(rules_dirs: Tuple[Path, Path]) -> Dict[str, Path]:
    """
    Find filename stems present in BOTH of the two candidate rules directories.

    Intentionally two-directory-only (matching :func:`_rules_dirs`'s exact
    ``(xdg_dir, legacy_dir)`` return shape), not generalised to an arbitrary
    number of directories -- narrowing the contract here keeps "the second
    directory's file is shadowed" explicit rather than silently truncating a
    longer list if a third candidate directory were ever added (YAGNI; that
    would need this function revisited anyway).

    When the same stem exists in both directories, the second (``legacy_dir``)
    entry for that stem is entirely ignored for content purposes by
    :func:`_merged_rules_by_stem` -- this must not be silent, since it is
    exactly the "a real ruleset ends up in the wrong directory and is never
    enforced" failure mode TOO-19 exists to fix. EXCEPT when both
    directories' representative files resolve to the SAME real file (e.g. one
    directory symlinked into the other -- a natural migration/compatibility
    move, and in fact the exact stopgap workaround that motivated this
    ticket): nothing is actually being ignored in that case, so reporting it
    as shadowed would be a false positive that trains users to ignore the
    warning that matters. That stem is excluded.

    This identifies the remaining, genuinely-shadowed stems together with a
    representative shadowed path (TOML preferred over JSON within the
    shadowing directory, same rule as elsewhere) so :func:`load_configuration`
    can record it on the winning :class:`ConfigLayer` for
    :meth:`Configuration.validation_issues` to report as a warning.

    Args:
        rules_dirs: The two candidate rules directories, ``(xdg_dir,
            legacy_dir)`` as returned by :func:`_rules_dirs`.

    Returns:
        Mapping of stem to the shadowed (non-winning) representative path, for
        stems present in both directories as genuinely distinct real files.
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
    Discover config files within a single ``.claude`` directory.

    Applies the within-level priority ordering (``.local`` first, toolguard_hook
    before native settings) and TOML-over-JSON preference, exactly as the legacy
    two-level discovery did per level.

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
            # NOTE: the "both .toml and .json exist" warning is intentionally NOT
            # emitted here. It is detected and routed to the WARNING log stream by
            # Configuration.validation_issues() (TOO-8 Phase 4, M1 -- single source
            # of truth). Discovery stays side-effect-free.
        elif json_exists:
            found.append((json_path, source_type, "json"))
    return found


def _hierarchical_toggle(project_claude_dir: Optional[Path]) -> bool:
    """
    Read the ``hierarchical_configuration`` toggle from the project level only.

    Per the fixed-bootstrap rule, the toggle is read ONLY from the most-specific
    (project) ``toolguard_hook`` config so that ancestors cannot vote on whether
    ancestors are traversed. Defaults to ``True`` when unset or unreadable.

    This is a pre-pass over the SAME file(s) ``load_configuration()``'s main
    discovery loop parses again afterwards (a pre-existing, unrelated
    double-parse -- see the corrective-change history for this module). A
    parse failure here therefore does not need its own
    :attr:`Configuration.parse_failures` bookkeeping (TOO-19): if the
    project-level file this reads is genuinely broken, the SAME file is
    re-parsed and recorded by that later loop, so it still ends up on
    :attr:`Configuration.parse_failures` -- just via that call, not this one.

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
    located under ``~`` (preserving "user config always applies"). The walk never
    ascends above ``~``.

    Each level is assigned a ``specificity`` index: 0 = project (most specific),
    increasing with distance, and the user level last (least specific). When the
    ``hierarchical_configuration`` toggle (read from the project level only) is
    False, only the project and user levels are collected -- today's behaviour.

    After the primary ``.claude`` candidates, any files discovered across the
    two optional candidate rules directories (see :func:`_rules_dirs` /
    :func:`_discover_rules_files_multi`, TOO-30/TOO-19) are appended with
    ``source_type='toolguard_hook_rules'`` at the SAME (least-specific, user)
    specificity as ``~/.claude`` -- they merge into the user level rather than
    introducing a new hierarchy tier. Both candidate directories share this
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

        The level is emitted HERE, by the pass that actually found the file,
        rather than being re-derived downstream from the path's shape. An
        earlier implementation re-derived it via ``path.resolve()`` and asked
        whether the result lived under ``~/.claude``; that second derivation
        disagreed with this one whenever a ``.claude`` directory (or a file
        inside it) was a symlink into a store located under ``~/.claude``,
        silently promoting every project rule to the user level and changing
        precedence with no error (TOO-19, 2026-07-28). Deriving it once, from
        the discovery structure, makes the two answers the same answer.
    """
    home = Path.home()
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
    # unless it was already reached by the upward walk -- in which case it keeps
    # its natural, least-specific position at the tail).
    _add(user_claude_dir)

    # The user level is ALWAYS the last entry in level_dirs (appended last, and
    # if the upward walk reached it first it keeps its tail position), so this
    # index is the authoritative user tier. It is computed from level_dirs
    # rather than from the discovered results because a level whose directory
    # does not exist contributes no results at all -- taking the maximum over
    # the results would then promote the deepest EXISTING level to 'user'.
    user_specificity = len(level_dirs) - 1

    results: List[Tuple[Path, str, str, int, str]] = []
    for specificity, claude_dir in enumerate(level_dirs):
        if not claude_dir.exists():
            continue
        level = "user" if specificity == user_specificity else "project"
        for path, source_type, file_format in _discover_in_dir(claude_dir):
            results.append((path, source_type, file_format, specificity, level))

    # Optional candidate rules directories (TOO-30/TOO-19): flat *.toml/*.json
    # files that merge into the USER level (least-specific tier, index
    # len(level_dirs) - 1, which is stable even when ~/.claude itself has no
    # files). Appended after the primary ~/.claude candidates so those remain
    # the highest-priority user-level source when duplicate patterns exist.
    for path, file_format in _discover_rules_files_multi(_rules_dirs()):
        results.append(
            (path, "toolguard_hook_rules", file_format, user_specificity, "user")
        )

    return results


# ---------------------------------------------------------------------------
# Public configuration abstraction
# ---------------------------------------------------------------------------
#
# Everything below builds an immutable, file/format-agnostic view of the
# toolguard configuration on top of the internal sourcing/parsing helpers above.
# Clients should use load_configuration() and the Configuration methods rather
# than touching files, formats, or discovery order directly.


def wrap_tool_pattern(tool: str, body: str) -> str:
    """
    Wrap a pattern body in its ``Tool(...)`` envelope.

    The structural inverse of :func:`~toolguard.rule_entry._strip_tool_wrapper`: given a tool name and a
    wrapper-free body, produce the wrapped form as stored in config files (e.g.
    ``wrap_tool_pattern('Bash', 'git diff:*') -> 'Bash(git diff:*)'``).  This is
    the single source of truth for that construction so tooling never re-derives
    the ``f"{tool}({body})"`` idiom site by site.

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

    Phase 1 is behaviour-preserving: resolution is still union + global
    deny-first over two levels (project + user). The per-layer shape exists so
    a future resolver (Phase 2) can apply more-specific-wins without changing
    the public surface.

    Attributes:
        layers: Discovered config layers, most-specific first.
        start_dir: Directory discovery started from (for :attr:`project_root`).
        parse_failures: ``(path, message)`` pairs for every governed config
            file that EXISTED but failed to parse (TOO-19 fail-open security
            fix). Recorded at discovery time by :func:`load_configuration` --
            see :func:`_parse_source_recording_failures` -- for the sources
            that actually feed this Configuration (the main hierarchy-discovery
            loop and the ``CLAUDE_SETTINGS_PATH`` explicit branch). A file that
            simply does not exist is NOT recorded here (see that function's
            docstring for the "broken" vs "absent" distinction); a file that
            existed and either failed to parse or whose top level was not an
            object/table (same silent-information-loss failure mode) both
            count. Non-empty is a severe safety-floor condition: EVERY
            governed decision is clamped to ``'ask'`` by
            :func:`~toolguard.permission_resolution.resolve_permission_detailed`
            (see :func:`~toolguard.permission_resolution._apply_ask_floor`)
            until the file(s) are fixed, because a broken file may have
            silently dropped a deny/hard_deny rule with no other visible
            trace.
            :meth:`validation_issues` also reports one ``'error'`` Issue per
            entry, and ``toolguard-session-start`` surfaces it at the start of
            every session while it remains non-empty. Defaults to ``()`` so
            existing direct-construction call sites are unaffected.
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
        :func:`find_project_root` from :attr:`start_dir`. None is returned when
        no project marker (``pyproject.toml``/``.git``) is found up to ``~``.
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

        UNION across all toolguard_hook layers in the hierarchy (TOO-8 Phase 5):
        every level's ``governed_tools`` list is pooled, de-duplicated, and kept
        in first-occurrence (most-specific-first) order. Native Claude settings
        layers are ignored (``governed_tools`` is a toolguard extension).
        Defaults to :data:`~toolguard.tool_spec.DEFAULT_GOVERNED_TOOLS`
        (``('Bash', 'Read', 'Write', 'Edit')``) when no level configures any
        governed tool.

        Resolving over ``self.layers`` keeps governed-tools consistent with the
        hierarchical, more-specific-aware resolution used for permissions and
        takeover mode, and applies under ``CLAUDE_SETTINGS_PATH`` mode too (the
        explicit source becomes the only layer).
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
        Return the resolved takeover-mode configuration (TOO-8 Phase 5).

        Resolved hierarchically over ``self.layers`` (most-specific first),
        reading only ``toolguard_hook`` layers:

        - ``enabled`` is a SINGLE-OWNER policy with fail-safe-on-conflict. Only
          layers that EXPLICITLY set ``takeover_mode.enabled`` (key present)
          participate. If none set it, the result is ``False`` (default OFF). If
          one or more set it and they all AGREE, that shared value is used. If
          they DISAGREE (some true, some false), it is a misconfiguration: the
          result is forced to ``False`` (fail-safe OFF -- native Claude prompts
          stay active, nothing is silently bypassed) and a
          :class:`TakeoverEnabledConflict` is attached describing each disagreeing
          source with its provenance.
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

            # Record an EXPLICIT enabled setting (key present) with provenance.
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

        Implements the single-owner / fail-safe-on-conflict policy:

        - No level set it => ``(False, None)`` (default OFF).
        - One or more levels set it, all to the SAME value => ``(value, None)``.
        - Levels disagree (both ``True`` and ``False`` present) => CONFLICT:
          ``(False, TakeoverEnabledConflict(...))`` -- fail-safe OFF.

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

        The single shared walk behind both :meth:`hard_deny` (wrapper-stripped
        pattern tuples) and :meth:`hard_deny_entries` (the backing
        :class:`~toolguard.rule_entry.RuleEntry` objects) -- both public
        methods project from this one pooled result, so they cannot drift
        relative to each other (TOO-19 Phase 0a, increment 3).

        Reuses :meth:`_extract_tool_entries` (the same shape-normalization /
        tool-scoping chokepoint :meth:`permission_layers` uses) for each raw
        ``hard_deny.deny``/``allow`` list, so a structured (``{match=...,
        ...}``) entry here is parsed identically to one under
        ``[permissions]`` and is never silently dropped. Per-element issues
        (e.g. a malformed entry) are discarded here, exactly as
        :meth:`permission_layers` discards them -- this accessor has no
        issue-reporting channel in this increment.

        Native layers are skipped ENTIRELY before any entry is normalized:
        ``hard_deny`` is a toolguard extension with no native-Claude concept,
        mirroring the ``if layer.is_native: continue`` guard used elsewhere.
        Because of that guard, ``is_native`` passed to ``normalize_entry``
        (via ``_extract_tool_entries``) is always ``False`` here -- it is
        still threaded through the call, rather than hardcoded, so this call
        site reads consistently with every other ``_extract_tool_entries``
        caller.

        Pooling: entries are collected from ALL levels into one pool (union
        across the whole hierarchy), de-duplicated, order-preserving
        most-specific-first -- unlike the normal more-specific-wins cascade.
        The de-duplication key is ``entry.pattern`` (the wrapper-INTACT
        pattern string): the SAME rule from two layers is still one pooled
        entry even when only one occurrence carries enrichment metadata
        (e.g. ``additionalContext``). This mirrors :class:`RuleEntry`'s own
        ``.pattern``-only "same rule" comparison (see
        :meth:`~toolguard.rule_entry.RuleEntry.identity` for why that differs
        from full ``identity()`` equality or a future merge). Because
        ``entries_for_tool`` already scopes to one tool's wrapper prefix, two
        distinct wrapped patterns can never collide after stripping, so this
        is the identical de-dup behaviour as before, just keyed pre-strip.
        Insertion order follows ``self.layers`` (already most-specific
        first), so the FIRST (most-specific) occurrence of a pattern wins
        when two levels share it but differ in metadata.

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
        Unlike the normal more-specific-wins cascade, hard_deny is COLLECTED FROM
        ALL LEVELS INTO ONE POOL (union across the whole hierarchy, de-duplicated,
        order-preserving most-specific first). It is evaluated FIRST, before the
        cascade, and cannot be overridden by any level's normal allow.

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
        in the hook (reusing the Phase 2 anchoring), mirroring normal patterns.

        A structured (``{match = "...", ...}``) entry contributes its pattern
        here exactly like a plain string does (TOO-19 Phase 0a, increment 3
        fixed a prior bug where structured entries were silently dropped);
        its enrichment metadata is not exposed by this method -- use
        :meth:`hard_deny_entries` for that.

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

        Companion to :meth:`hard_deny`: same pooling/de-dup/order/native-skip
        behaviour (see :meth:`_pool_hard_deny_entries`, the single shared walk
        both methods project from), but returns the entries themselves rather
        than stripped pattern strings, so a structured entry's metadata
        (e.g. an ``additionalContext`` reinforcing why a command is hard-denied
        and what to use instead) is reachable. ``hard_deny(tool_name)`` is a
        pure projection of this same pool (each pattern is
        ``entry.stripped_pattern`` for the corresponding entry here) -- TOO-45
        R2c: no caller relies on positional alignment between the two methods'
        *return values* any more (the one that used to,
        ``resolve._hard_deny_additional_context``, now searches this method's
        result directly), so there is nothing left to keep in sync by hand.

        Not yet wired into any decision path -- this increment only makes the
        metadata reachable. A later TOO-19 phase uses it to surface
        enrichment (e.g. ``additionalContext``) at the moment a hard deny
        fires.

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

        The shared per-list worker behind :meth:`permission_layers`: runs every
        raw element through :func:`toolguard.rule_entry.normalize_entry` (shape
        normalization -- plain string or structured ``{match = ..., ...}``
        table), then keeps the ones that scope to ``tool_name`` via
        :func:`toolguard.rule_entry.entries_for_tool`.

        TOO-45 R2a: returns entries only -- callers that also want the
        wrapper-stripped pattern form read it off each entry's
        :attr:`~toolguard.rule_entry.RuleEntry.stripped_pattern` property
        instead of this method separately materialising a parallel
        ``patterns`` tuple, which used to be index-aligned with (and could
        drift from) the entries it was derived from.

        ``normalize_entry`` also returns issues (e.g. a malformed structured
        entry, or an unknown enrichment key); they are INTENTIONALLY discarded
        here -- ``permission_layers`` has no channel for them, and it is not
        this method's job to report them. They ARE surfaced, from a separate
        pass over the same entries, by
        :meth:`Configuration.validation_issues` (via
        :func:`toolguard.config_validation.validate_permissions`), which is
        where every content-level diagnostic is collected.
        Discarding the issue is not the same as discarding the entry: an
        element that normalizes successfully is never dropped here, which is
        the whole point of this increment -- a structured entry no longer
        silently vanishes from allow/deny/ask the way it used to.

        Args:
            raw_list: The raw ``permissions.allow``/``deny``/``ask`` value
                from one config layer. Tolerated even when not a list (treated
                as empty), matching the existing non-dict-``permissions``
                tolerance in :meth:`permission_layers`.
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
        structured (``{match = ..., ...}``) entries (TOO-19 Phase 0a, increment
        2) -- ``ToolPatternLayer``'s wrapper-stripped ``allow``/``deny``/``ask``
        pattern tuples are derived properties over these entries (TOO-45 R2),
        not separately populated. Takeover filtering is already applied: when
        takeover mode is enabled, blanket ignored allow patterns are removed
        from native ('claude') layers only, filtered directly on
        ``allow_entries``. Deny and ask entries are never filtered.

        Phase 1 callers flatten+union these (see :meth:`allow_deny_for`),
        preserving current behaviour. The per-layer shape supports a future
        more-specific-wins resolver without changing this API.

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
        the order the more-specific-wins resolver consumes.

        Returns, per hierarchy level (most-specific first), the collapsed
        ``(allow, deny)`` pattern tuples PLUS the contributing
        :class:`ToolPatternLayer` objects so a matched pattern can be mapped back
        to its exact source file/level via :attr:`ToolPatternLayer.provenance`.

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
        either side) is configured for ``tool_name`` at any level (TOO-15).

        Distinguishes a genuinely UNCONFIGURED tool (which should resolve to
        ``'ask'`` so a fresh install is not bricked) from a CONFIGURED tool whose
        rules simply do not match the current command/path (which is governed by
        :meth:`resolved_no_match_fallback`).

        Args:
            tool_name: Tool to check (e.g. ``'Bash'``, ``'Read'``, ``'Write'``,
                ``'Edit'``).

        Returns:
            ``True`` when at least one allow/deny/ask/hard_deny pattern exists
            for ``tool_name`` anywhere in the hierarchy.
        """
        for layer in self.permission_layers(tool_name):
            if layer.allow or layer.deny or layer.ask:
                return True
        hd_deny, hd_allow = self.hard_deny(tool_name)
        return bool(hd_deny or hd_allow)

    def _first_toplevel_str_setting(self, key: str) -> Optional[str]:
        """
        Return the first non-native layer's raw string value for a top-level
        ``toolguard_hook`` scalar setting key (TOO-19 code review m2).

        Shared layer-scan used by every "fallback"-shaped setting
        (:meth:`resolved_no_match_fallback`, :meth:`resolved_undecidable_fallback`,
        and the TOO-28 ``*_auto_mode`` settings that will reuse it): walks
        ``self.layers`` MOST-SPECIFIC first, skips native ``settings.json``
        layers (these settings are toolguard extensions, never native), and
        returns the first layer's value for ``key`` when it is present AND a
        ``str`` (a non-string value -- e.g. a stray table -- is treated as not
        set, same as absence).

        Args:
            key: The top-level ``toolguard_hook`` key to look up (e.g.
                ``'no_match_fallback'``, ``'undecidable_fallback'``).

        Returns:
            The first matching layer's raw string value, or ``None`` when no
            non-native layer sets it. Callers are responsible for any
            alias/legacy-spelling resolution and for validating against their
            own recognized value set -- this helper does neither.
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
        Resolve one "fallback"-shaped ``toolguard_hook`` setting (TOO-19 code
        review m2).

        Extracted so :meth:`resolved_no_match_fallback` and
        :meth:`resolved_undecidable_fallback` share ONE layer-scan +
        validation body instead of duplicating it verbatim, and so the two
        TOO-28 settings of the same shape (``no_match_fallback_auto_mode``,
        ``undecidable_fallback_auto_mode``) can reuse this method rather than
        requiring a THIRD/FOURTH copy or a re-done two-way de-duplication.
        The two behavioural differences between the existing settings are
        expressed as PARAMETERS, not special-cased in this shared body, so a
        setting with neither difference (like ``undecidable_fallback``, and
        presumably the TOO-28 settings) just omits them.

        Resolution order:

        1. :meth:`_first_toplevel_str_setting` -- most-specific non-native
           layer that sets the top-level key wins.
        2. If unset anywhere and *legacy_alias* is given, call it for a
           fallback raw value (e.g. the ``[takeover_mode]`` alias).
        3. If the resolved raw value is a key of *alias_map*, replace it with
           the mapped canonical spelling.
        4. Validate against *valid_values*; an unset OR unrecognized value
           (typo/bad config) resolves to *default* rather than propagating or
           raising.

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
                mechanism supplied the raw value. Covers BOTH kinds of
                alternate spelling this shared body needs to normalize: a
                truly deprecated legacy value being phased out (e.g.
                ``no_match_fallback``'s ``'warn_deny'`` -> ``'allow_with_warning'``)
                and a deliberate, PERMANENT synonym that is not deprecated at
                all (e.g. ``'allow_with_no_warnings'`` -> ``'allow'``, TOO-19
                -- the long spelling is a human reminder, not a spelling on
                its way out). ``None`` means this setting has no alternate
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
        Resolve the EFFECTIVE ``no_match_fallback`` setting (TOO-15).

        ``no_match_fallback`` is a top-level ``toolguard_hook`` key, checked
        across ALL non-native layers (most-specific first; the first layer that
        sets it wins). For backwards compatibility, the legacy alias nested
        under ``[takeover_mode].no_match_fallback`` (see :meth:`takeover_mode`)
        is honoured ONLY when NO layer sets the top-level key. When BOTH are set
        anywhere, the top-level key wins outright -- regardless of the relative
        specificity of the two settings. Applies in BOTH takeover and
        non-takeover modes (no longer gated on ``takeover_mode.enabled``).

        The deprecated legacy value ``'warn_deny'`` -- whether set via the
        top-level key or the ``[takeover_mode]`` alias -- is always normalized
        to the canonical ``'allow_with_warning'`` before being returned. The
        deliberate (non-deprecated) long-form synonym
        ``'allow_with_no_warnings'`` is likewise always normalized, to
        ``'allow'`` (TOO-19) -- see the module-level
        ``_ALLOW_NO_WARNINGS_ALIAS`` comment for why this spelling is kept
        permanently rather than deprecated like ``warn_deny``.

        Shares its layer-scan and validation with
        :meth:`resolved_undecidable_fallback` via
        :meth:`_resolve_fallback_setting` (TOO-19 code review m2); this
        method supplies the ``[takeover_mode]`` legacy alias and the
        ``warn_deny``/``allow_with_no_warnings`` alias map as parameters. Only
        the ``[takeover_mode]`` legacy alias and the ``warn_deny`` spelling
        are unique to this setting -- ``allow_with_no_warnings`` is honoured
        by :meth:`resolved_undecidable_fallback` too (TOO-19), so it is NOT
        part of the asymmetry the rest of this docstring describes.

        Returns:
            One of ``'ask'``, ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'``. The resolved value is validated against the
            recognized set; an unset OR unrecognized value (typo/bad config)
            resolves to the default ``'ask'`` and is never propagated as-is.
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
        Resolve the EFFECTIVE ``undecidable_fallback`` setting (TOO-19).

        ``undecidable_fallback`` answers a DIFFERENT question than
        ``no_match_fallback``: "I could not safely read this command at all"
        (foreign inline code / heredoc sinks, complex control structures,
        process substitution -- see :mod:`toolguard.compound`) rather than "I
        read the command and no rule matched it". It is resolved as a
        strictest-wins FLOOR against whatever the leaf/segment itself
        resolved to (or, for segments that were never checked against any
        rule at all, taken directly) -- see
        :func:`toolguard.compound.resolve_compound_permission` and
        :func:`toolguard.compound._resolve_leaf`.

        ``undecidable_fallback`` is a TOP-LEVEL ``toolguard_hook`` key ONLY,
        checked across ALL non-native layers (most-specific first; the first
        layer that sets it wins). Unlike :meth:`resolved_no_match_fallback`,
        this setting has NO legacy ``[takeover_mode]`` alias -- it is a
        brand-new TOO-19 setting with no prior spelling to stay
        backwards-compatible with -- and no field for it exists on
        :class:`~toolguard.config_types.TakeoverConfig`. Do NOT add either
        "for symmetry" with ``no_match_fallback``; that symmetry does not
        apply here, and there is deliberately no ``[takeover_mode]`` parsing
        for this key. There is also no deprecated ``'warn_deny'`` spelling to
        normalize (that alias exists only for ``no_match_fallback``'s
        history) -- keep that ONE asymmetry. Applies in BOTH takeover and
        non-takeover modes.

        The deliberate (non-deprecated) long-form synonym
        ``'allow_with_no_warnings'`` IS honoured here, normalized to
        ``'allow'`` (TOO-19) -- unlike ``warn_deny``, this is a brand-new
        spelling introduced for both settings at once, not part of
        ``no_match_fallback``'s legacy history, so it does not fall under the
        "no symmetry with no_match_fallback" rule above.

        This setting is NOT consulted by, and has NO effect on, the
        config-level parse-failure ASK floor
        (:func:`~toolguard.permission_resolution._apply_ask_floor`): a broken
        config file is never a policy question this (or any) setting can
        relax -- see that function's docstring for the rationale.

        Shares its layer-scan and validation with
        :meth:`resolved_no_match_fallback` via
        :meth:`_resolve_fallback_setting` (TOO-19 code review m2); unlike
        that method, this call supplies NO ``legacy_alias`` and its
        ``alias_map`` is JUST ``_ALLOW_NO_WARNINGS_ALIAS`` -- no
        ``warn_deny`` entry, per the asymmetry above.

        Returns:
            One of ``'ask'``, ``'deny'``, ``'allow_with_warning'``, or
            ``'allow'``. The resolved value is validated against the
            recognized set; an unset OR unrecognized value (typo/bad config)
            resolves to the default ``'ask'`` and is never propagated as-is.
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
        Find every layer that sets a ``*_fallback`` key to an unusable value (TOO-19 m5).

        Both :meth:`resolved_no_match_fallback` and
        :meth:`resolved_undecidable_fallback` fall back to ``'ask'`` when the
        configured value is not recognized. That resolution is correct and is
        NOT changed here -- ``'ask'`` is the safe direction. The problem this
        method exists to fix is that it used to happen with no diagnostic
        anywhere: ``no_match_fallback = "allow_with_no_warning"`` (singular)
        silently produced maximum-friction ``ask`` behaviour, which reads as a
        broken feature rather than a typo.

        Two kinds of unusable value are reported, because both are equally
        silent:

        - a string that is not a recognized spelling (after the alias map --
          ``warn_deny`` and ``allow_with_no_warnings`` are recognized and so
          never reported);
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

        This is the Phase 1 (behaviour-preserving) flattening of
        :meth:`permission_layers`: union across layers in discovery order with
        duplicates removed. Global deny-first matching is applied downstream by
        the matching code, not here.

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

        Resolution is MORE-SPECIFIC-WINS (TOO-8 Phase 5, decision #4): the value
        comes from the most-specific level that defines it -- project beats
        ancestor beats user. Layers are already ordered most-specific first, so
        the FIRST layer that defines the key wins and iteration stops. A bare
        ``name`` resolves a top-level key directly.

        This replaces the Phase-1 user-wins (last-occurrence) behaviour; it is a
        conscious, test-visible flip (see
        ``test/unit/test_configuration.py::...config_sync_conflict_is_project_wins``).

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

        # Iterate most-specific first; the FIRST layer that defines the key wins
        # (more-specific-wins). Stop as soon as a defining layer is found.
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

        Each value resolves more-specific-wins via :meth:`scalar` (TOO-8 Phase 5):
        the most-specific level that defines a key wins (project beats ancestor
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
        all toolguard_hook layers, de-duplicated and order-preserving. Used by
        divergence detection and migration tooling so those clients never open
        or parse config files themselves.

        TOO-19 Phase 0a increment 8 (W1 fix): every raw element is routed
        through :func:`toolguard.rule_entry.normalize_entries_preserving`
        rather than the old ``isinstance(perm, str)`` filter, which silently
        dropped any structured (``dict``) entry -- the root of the "structured
        entry deleted by the next auto-migration" defect (a divergence/merge
        client fed a config missing entries it never actually lost, causing
        migration to overwrite the file without them). An element that fails
        to normalize is still preserved (never dropped): this method's whole
        purpose is describing what should be WRITTEN back, so an unparseable
        element must round-trip too, not vanish.

        Values are kept wrapper-INTACT (unlike :meth:`permission_layers`,
        which strips): every consumer of this method (divergence, migration)
        is tool-agnostic and needs the wrapped form.

        Returns:
            Read-only mapping with keys 'allow', 'deny', 'ask', each a tuple of
            :class:`~toolguard.rule_entry.RuleEntry`.
        """
        result: Dict[str, List[RuleEntry]] = {"allow": [], "deny": [], "ask": []}
        # Tracks patterns already added per perm_type, for the de-dup check
        # below -- de-duplication keys on `.pattern` alone (comparison #1,
        # "is this the same RULE" -- see RuleEntry.identity()'s docstring),
        # matching the prior str-based de-dup exactly: an entry appearing
        # with metadata in one layer and bare in another is still the same
        # rule, and the FIRST occurrence across layers (most-specific first)
        # wins.
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

        Replaces the hand-rolled file walk in the hook's startup validation.
        Detects:

        - A governed config file that failed to parse entirely (TOO-19
          fail-open fix) -- reported FIRST, since it is the most severe class
          of issue: every decision is clamped to 'ask' while it persists.
        - Both a TOML and a JSON config file present at the same level/base.
        - A rules-directory filename stem shadowed across the two candidate
          rules directories (TOO-19).
        - A non-boolean ``takeover_mode.enabled``.
        - A rules-directory file (TOO-30) defining a top-level key outside
          ``[permissions]``/``[hard_deny]``.
        - Unsupported tools referenced in toolguard_hook permissions.
        - Tools referenced in permissions but absent from governed_tools.

        The config module only RETURNS issues; logging is the hook's job.

        Returns:
            Tuple of :class:`Issue`, in detection order (parse-failure issues
            first, then duplicate-file issues, then permission-validation
            issues).
        """
        issues: List[Issue] = []

        # 0) A governed config file failed to parse entirely (TOO-19). This is
        #    an 'error', not a 'warning': permission_resolution's ASK floor
        #    clamps EVERY decision to 'ask' while any entry remains (see
        #    Configuration.parse_failures's docstring), so a rule in this file
        #    -- possibly a deny or hard_deny -- may be silently unenforced.
        for path, message in self.parse_failures:
            issues.append(
                Issue(
                    level="error",
                    message=f"{path} failed to parse and was skipped: {message}",
                    corrective_steps=(
                        "Fix the file's syntax. Until it parses, EVERY toolguard "
                        "permission decision is clamped to 'ask' (see "
                        "toolguard.permission_resolution.resolve_permission_detailed) "
                        "so no rule -- including deny/hard_deny -- in this file is "
                        "silently lost."
                    ),
                )
            )

        # 1) Both a TOML and a JSON config file present for the same base in the
        #    same directory -> warn (the tool is using TOML). This is the SINGLE
        #    source of truth for the warning (TOO-8 Phase 4, M1): discovery itself
        #    is side-effect-free (it no longer prints) and the hook routes these
        #    Issues to the WARNING stream. A duplicate is recognised either by two
        #    discovered layers of differing format at the same base, OR -- since
        #    real discovery keeps only the TOML -- by both files existing on disk.
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
                # the on-disk check above (needed for rules-dir layers, TOO-30).
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
        #     rules directories (TOO-19): when the SAME stem exists in both the
        #     XDG rules directory and the legacy ~/.toolguard/rules directory,
        #     only the XDG entry becomes a layer (see _merged_rules_by_stem) --
        #     the losing file is entirely ignored. This must not be silent,
        #     since it is exactly the "a ruleset ends up in the wrong directory
        #     and is never enforced" failure mode TOO-19 exists to fix.
        #     Recorded on the winning layer at discovery time (see
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
        #     recognize (TOO-19 m5). Resolution silently falls back to 'ask',
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

        # 3) Rules-directory layers (TOO-30) may only define [permissions] and
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

        issues.extend(validate_permissions(merged_config))

        return tuple(issues)

    # -- provenance / introspection ---------------------------------------

    def describe_sources(self) -> Tuple[str, ...]:
        """Return human-readable descriptions of all discovered sources."""
        return tuple(layer.provenance.describe() for layer in self.layers)

    def describe_levels(self) -> Tuple[str, ...]:
        """
        Return concise ``level: path`` descriptions, one per discovered source.

        Used by the once-per-session discovery diagnostic in the resolution log
        (TOO-8 Phase 4, M2). Ordered most-specific first, mirroring layer order.

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
    worse than the generic message, so detection stays narrow and only
    upgrades the message when the specific cause is actually found.

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

    This is the side-effect-free core behind :func:`_parse_source` (kept for
    existing callers that only need the parsed dict, unchanged) and
    :func:`_parse_source_recording_failures` (TOO-19, which additionally needs
    the failure message to record on :attr:`Configuration.parse_failures`).
    Both wrap this function rather than duplicating the parse/except logic.

    A syntactically valid file whose top level is not an object/table (e.g. a
    bare JSON array) is treated the same as an unparseable file -- rather than
    propagating a raw ``AttributeError``/``TypeError`` out of
    ``load_configuration()`` and crashing the whole hook. This matters most
    for TOO-30's rules-directory files, which are more numerous and
    hand-authored than the single primary ``toolguard_hook.toml``, so a shape
    mistake in any one of them must not take down every command.

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
    throwaway accumulator (TOO-19 corrective change: this function is a
    strict subset of that one -- pyscn flagged the pair at 0.80 similarity.
    Both print the identical ``"Warning: Failed to load ..."`` diagnostic to
    stderr on failure and return the identical content; the only difference
    is that the other function ALSO records a genuine parse failure into a
    persistent ``parse_failures`` list. Passing a fresh list here that is
    immediately discarded reproduces "no recording" exactly, for BOTH the
    file-missing case (never recorded, on either function, since
    ``path.exists()`` is only checked before appending) and the file-broken
    case (recorded into the throwaway list, then discarded) -- so this
    delegation changes no observable behaviour). Does NOT change the
    fail-open behaviour itself -- the file is still skipped, with only a
    warning, same as before. (Whether fail-open is the right policy at all is
    a separate concern: see :func:`_parse_source_recording_failures`, used by
    :func:`load_configuration` for the sources that feed
    :attr:`Configuration.parse_failures` and the resulting ASK-floor clamp,
    TOO-19.) Callers that do not need the ASK-floor bookkeeping
    (``_hierarchical_toggle``, the legacy ``config_sync_settings_from_sources``)
    keep using this function unchanged.

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
    Parse *path*, printing the same warning :func:`_parse_source` would, and
    additionally recording a genuine ("broken", not merely absent) parse
    failure into *parse_failures* (TOO-19 fail-open security fix).

    Used only by :func:`load_configuration`'s call sites, i.e. the sources
    that actually feed the returned :class:`Configuration` (and therefore
    :func:`~toolguard.permission_resolution.resolve_permission_detailed`'s
    ASK-floor clamp): the main hierarchy-discovery loop and the
    ``CLAUDE_SETTINGS_PATH`` explicit-override branch. A file that simply
    does not exist on disk is NOT recorded -- it is not "broken"
    configuration, just absent -- even though the warning is still printed
    unchanged (the pre-existing
    diagnostic for a missing/misconfigured path). This matters only for the
    explicit branch: files reached via the hierarchy-discovery loop are
    always known to exist (discovery only yields paths it already found on
    disk), so ``path.exists()`` is trivially true there.

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


# NOTE (TOO-19, 2026-07-28): _level_for_path() lived here and re-derived a
# source's hierarchy level from its path shape, by resolving symlinks and
# testing containment under ~/.claude and the rules directories. It has been
# REMOVED, not fixed: _discover_levels() already knows each file's level -- it
# found the file by walking to that directory -- so the second derivation was
# redundant, and it disagreed with the first whenever a .claude directory or a
# file inside it was a symlink into a store under ~/.claude (project rules
# silently became user rules, changing precedence with no error). Do not
# reintroduce a path-shape-based level derivation; take the level from
# _discover_levels(). See test/unit/test_symlink_hierarchy.py.


def load_configuration(
    start_dir: Path = None, ignore_env_override: bool = False
) -> Configuration:
    """
    Load the toolguard configuration as an immutable :class:`Configuration`.

    This is the single public entry point. It performs all discovery and
    parsing internally and returns a file/format-agnostic view. When
    ``CLAUDE_SETTINGS_PATH`` is set, a single explicit source (plus any adjacent
    ``toolguard_hook`` file) is used, bypassing the hierarchy -- matching the
    legacy behaviour. The runtime hook relies on this single-file behaviour, so
    it is the default.

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to
            the current working directory.
        ignore_env_override: When True, ignore ``CLAUDE_SETTINGS_PATH`` and
            always discover the hierarchy rooted at the project. This exists for
            the migration/divergence tooling, whose write-target selection is
            already project-based; forcing the read path to be project-based too
            keeps that tooling internally consistent and unaffected by a stale
            ``CLAUDE_SETTINGS_PATH`` pointing at an unrelated project. The
            runtime hook never sets this.

    Returns:
        An immutable :class:`Configuration`. Note that command-permission
        resolution (Bash) and governed-tools/takeover resolution intentionally
        delegate to the legacy loaders so that ``CLAUDE_SETTINGS_PATH`` handling
        and stderr diagnostics remain byte-for-byte identical in Phase 1.
    """
    layers: List[ConfigLayer] = []
    # Accumulates (path, message) for every governed file that EXISTED but
    # failed to parse, across whichever branch below runs (TOO-19). Passed to
    # both Configuration(...) construction points so parse_failures is
    # populated regardless of which mode (explicit CLAUDE_SETTINGS_PATH vs.
    # hierarchy discovery) is active.
    parse_failures: List[Tuple[Path, str]] = []

    settings_path = (
        None if ignore_env_override else os.environ.get("CLAUDE_SETTINGS_PATH")
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

    # Lazily computed (at most once) if/when a rules-dir layer is encountered
    # below, while the candidate rules directories are known to exist (this
    # same discovery pass just scanned them) -- so the fields below can be
    # recorded once here rather than re-checked against the filesystem later
    # by validation_issues(), which must work even if the source directories
    # no longer exist by the time it runs (e.g. an isolated test's tempdir):
    #
    # - rules_duplicate_stems: filename stems that have BOTH a .toml and .json
    #   file WITHIN THE WINNING rules directory (TOO-19: computed via
    #   _merged_rules_by_stem, so a same-stem file in the OTHER, losing
    #   directory is never mistaken for a format duplicate -- that is
    #   shadowing, tracked separately below, per a different stem in a
    #   different format in each directory).
    # - rules_shadowed_stems: filename stems present in MORE THAN ONE
    #   candidate rules directory, mapping to a representative shadowed
    #   (losing) path (TOO-19).
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
            # Rules-directory files are restricted to [permissions]/[hard_deny]
            # (TOO-30). Any other top-level key is recorded for
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
# Internal helpers shared with divergence/migration tooling
# ---------------------------------------------------------------------------
#
# These keep all JSON/TOML parsing inside the config module while preserving the
# legacy (config_files) signatures that divergence/migration code and their tests
# rely on. Callers pass the discovered (path, source_type, format) triples; the
# parsing/format-branching lives here, not in those clients.


def config_sync_settings_from_sources(
    config_files: List[Tuple[Path, str, str]],
) -> Dict:
    """
    Resolve config_sync settings from toolguard_hook sources.

    Parses each toolguard_hook source and applies last-occurrence-wins
    resolution over discovery order, returning defaults for missing values.
    All file/format handling is internal to the config module.

    This is a legacy path used only by ``auto_migrate``'s own migration
    settings lookup (config_sync.auto_migrate/backup_dir/auto_sort_on_migrate)
    -- it does NOT build or feed a :class:`Configuration`, so a parse failure
    here is not recorded to :attr:`Configuration.parse_failures` and cannot
    trigger the TOO-19 ASK-floor clamp (which lives on ``Configuration``
    itself). A broken toolguard_hook file simply falls back to this
    function's own defaults, same as before this change; the file's actual
    permission rules going unenforced is still caught via the normal
    ``load_configuration()`` path that runs earlier in the same hook
    invocation (see ``hook.py``'s ``main``).

    Args:
        config_files: List of (path, source_type, format) triples as produced
            by :func:`discover_config_files`.

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
