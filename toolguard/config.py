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
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Tuple

from toolguard.config_validation import validate_permissions

# Structural matcher for a ``Tool(inner)`` permission wrapper. An identifier made
# of word characters followed by a parenthesised body. ``.*`` (greedy, DOTALL via
# the trailing ``\)``) lets the inner body itself contain parentheses, e.g.
# ``Bash(foo(bar))`` -> ``foo(bar)``. This needs no known-tool list.
_TOOL_WRAPPER_RE = re.compile(r"[A-Za-z0-9_]+\((.*)\)", re.DOTALL)

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
_DEFAULT_NO_MATCH_FALLBACK = "deny"

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
def _parse_config_file_cached(path_str: str, file_format: str, mtime_ns: int) -> dict:
    """
    Parse a single config file, memoized on (path, format, mtime).

    This is the cache layer behind :func:`load_config_file`. ``mtime_ns`` is part of
    the cache key so that rewriting a file (which changes its modification time)
    transparently invalidates the cached parse -- caching on path alone would return
    stale content. ``path_str`` is a string (not :class:`Path`) so the key is hashable
    and stable.

    Args:
        path_str: Filesystem path to the config file, as a string.
        file_format: Either ``'toml'`` or ``'json'``.
        mtime_ns: The file's ``st_mtime_ns`` at the time of the call (cache key only).

    Returns:
        The parsed config dictionary.
    """
    return _parse_config_file(path_str, file_format)


def load_config_file(path: Path, file_format: str = "json") -> dict:
    """
    Load and parse a single config file, dispatching on format.

    This is the single internal config-file loader: it replaces the per-site
    ``if file_format == 'toml': tomllib.load(...) else: json.load(...)`` branches and
    memoizes parsing keyed on ``(path, st_mtime_ns)`` so that the same file discovered
    by multiple entry points in one invocation is parsed at most once, while a rewrite
    of the file is still picked up (the mtime changes).

    When the path cannot be ``stat``-ed (e.g. it does not exist), the cache is bypassed
    and the parse is attempted directly so that ``open``'s own ``FileNotFoundError``
    surfaces unchanged -- preserving the exact error boundary callers (and their tests)
    relied on before this consolidation. Nonexistent files are never worth caching.

    Tests that rewrite the SAME path within one process can reset the memo with
    ``_parse_config_file_cached.cache_clear()`` if ever needed (no current caller needs
    it because the mtime component of the key already invalidates rewritten files).

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
        mtime_ns = path.stat().st_mtime_ns
    except OSError:
        # Unstattable (typically missing): skip the cache and let open() raise.
        return _parse_config_file(str(path), file_format)
    return _parse_config_file_cached(str(path), file_format, mtime_ns)


def find_project_root(start_dir: Path = None) -> Path:
    """
    Find the project root by searching for pyproject.toml or .git directory.

    Climbs up from start_dir (or current directory) until finding a marker file/directory,
    stopping at home directory or filesystem root.

    Args:
        start_dir: Directory to start searching from. Defaults to current working directory.

    Returns:
        Path to project root

    Raises:
        RuntimeError: If project root cannot be found
    """
    current = Path(start_dir) if start_dir else Path.cwd()
    home = Path.home()

    while True:
        # Check for project markers
        if (current / "pyproject.toml").exists() or (current / ".git").exists():
            return current

        # Stop if we reach home or root
        if current == home or current == current.parent:
            raise RuntimeError(
                "Project root not found. Searched for pyproject.toml or .git directory "
                f"from {Path.cwd()} up to {current}. Something is badly wrong."
            )

        current = current.parent


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


def _discover_levels(start_dir: Path = None) -> List[Tuple[Path, str, str, int]]:
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

    Args:
        start_dir: Directory to start project-root discovery from. Defaults to cwd.

    Returns:
        List of (path, source_type, format, specificity) tuples, ordered
        most-specific first then by within-level priority.
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

    results: List[Tuple[Path, str, str, int]] = []
    for specificity, claude_dir in enumerate(level_dirs):
        if not claude_dir.exists():
            continue
        for path, source_type, file_format in _discover_in_dir(claude_dir):
            results.append((path, source_type, file_format, specificity))
    return results


# ---------------------------------------------------------------------------
# Public configuration abstraction
# ---------------------------------------------------------------------------
#
# Everything below builds an immutable, file/format-agnostic view of the
# toolguard configuration on top of the internal sourcing/parsing helpers above.
# Clients should use load_configuration() and the Configuration methods rather
# than touching files, formats, or discovery order directly.


def _strip_tool_wrapper(pattern: str) -> str:
    """
    Strip a ``Tool(...)`` wrapper from a permission pattern, if present.

    Permission patterns are authored wrapped as ``Tool(inner)`` (e.g.
    ``Bash(git *)``) but the loaders compare against the unwrapped inner pattern
    (``git *``). This is the single source of truth for that unwrapping. It is
    purely STRUCTURAL: any ``identifier(...)`` shape is stripped, so no
    hand-maintained tool list is needed and new tools require no change. The
    inner body may itself contain parentheses (``Bash(foo(bar))`` -> ``foo(bar)``).

    Returns the inner pattern when wrapped (e.g. ``'Bash(*)' -> '*'``); otherwise
    returns the pattern unchanged (already in extracted form).

    Args:
        pattern: A permission pattern, possibly wrapped in ``Tool(...)``.

    Returns:
        The pattern with any tool wrapper removed.
    """
    match = _TOOL_WRAPPER_RE.fullmatch(pattern)
    if match:
        return match.group(1)
    return pattern


def is_tool_wrapper(pattern: str) -> bool:
    """
    Report whether a permission pattern is a ``Tool(...)`` wrapper.

    Shares the single structural recogniser (``_TOOL_WRAPPER_RE``) with
    :func:`_strip_tool_wrapper`, so the wrapper shape lives in exactly one place.
    Used by clients (e.g. ``config_divergence``) that need to recognise
    tool-scoped native permission strings without re-deriving the regex.

    Args:
        pattern: A candidate permission string.

    Returns:
        True if the whole string is an ``identifier(...)`` tool wrapper.
    """
    return isinstance(pattern, str) and _TOOL_WRAPPER_RE.fullmatch(pattern) is not None


def wrap_tool_pattern(tool: str, body: str) -> str:
    """
    Wrap a pattern body in its ``Tool(...)`` envelope.

    The structural inverse of :func:`_strip_tool_wrapper`: given a tool name and a
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


def _append_provenance(reason: str, provenance) -> str:
    """
    Append matched-rule provenance to a reason as a bracketed suffix.

    Keeps backward compatibility with existing reason consumers: the suffix is
    appended AFTER the original reason so ``reason.split(': ', 1)`` and
    "matches allow pattern: X" substring assertions still hold. Two spaces
    separate the original reason from the suffix, e.g.::

        Command matches allow pattern: git *  [project: /p/.claude/toolguard_hook.toml]

    When ``provenance`` is None (no rule matched / mapping unavailable), the
    reason is returned unchanged.

    Args:
        reason: The base reason string from the matcher.
        provenance: A :class:`Provenance`, or None.

    Returns:
        The reason with a ``  [<level: path>]`` suffix, or unchanged.
    """
    if provenance is None:
        return reason
    return f"{reason}  [{provenance.describe_brief()}]"


@dataclass(frozen=True)
class Provenance:
    """
    Display-only origin of a single configuration source.

    Carries enough information to tell a human (or a future permission-mover)
    where a layer's content physically came from, without exposing file/format
    decisions as control flow to clients.

    Attributes:
        level: Conceptual level label ('project', 'user', or 'explicit' for
            a CLAUDE_SETTINGS_PATH single-file source).
        source_type: Either 'claude' (native settings) or 'toolguard_hook'.
        file_format: Either 'json' or 'toml'.
        path: Absolute path to the source file (display only).
        specificity: Hierarchy distance from the project root. 0 = most specific
            (project level); larger values are less specific; the user level is
            largest. Used by the more-specific-wins resolver. Sources at the same
            specificity belong to the same hierarchy level.
    """

    level: str
    source_type: str
    file_format: str
    path: Path
    specificity: int = 0

    def describe(self) -> str:
        """Return a short human-readable description of this source."""
        return f"{self.level}: {self.path} [{self.source_type}, {self.file_format}]"

    def describe_brief(self) -> str:
        """
        Return a compact ``level: path`` label for reason-string suffixes.

        Used to append matched-rule provenance to a decision reason as a
        bracketed suffix, e.g. ``[project: /home/me/proj/.claude/toolguard_hook.toml]``.
        Kept terse so it does not bloat the resolution log.
        """
        return f"{self.level}: {self.path}"


@dataclass(frozen=True)
class ConfigLayer:
    """
    One discovered configuration source, with provenance and parsed content.

    Layers are produced most-specific first (project before user, ``.local``
    before regular). The parsed content is exposed as a read-only mapping so it
    cannot be mutated by clients. Pattern matching is intentionally NOT done
    here; layers carry typed pattern lists that matching code consumes.

    Attributes:
        provenance: Display-only origin of this layer.
        content: Read-only view of the parsed config dict for this source.
    """

    provenance: Provenance
    content: Mapping = field(default_factory=lambda: MappingProxyType({}))

    @property
    def source_type(self) -> str:
        """Convenience accessor for the source type ('claude'/'toolguard_hook')."""
        return self.provenance.source_type

    @property
    def is_native(self) -> bool:
        """True when this layer is a native Claude settings file."""
        return self.provenance.source_type == "claude"

    @property
    def specificity(self) -> int:
        """Hierarchy specificity of this layer (0 = most specific)."""
        return self.provenance.specificity


@dataclass(frozen=True)
class ToolPatternLayer:
    """
    Per-layer allow/deny patterns for a single tool, with provenance.

    This is the per-layer shape returned by ``Configuration.permission_layers``.
    Patterns are extracted (tool wrapper removed) and takeover filtering has
    already been applied. Phase 1 callers flatten + union these; a future
    per-layer resolver can consume the same shape without changes.

    Attributes:
        provenance: Origin of the patterns in this layer.
        allow: Extracted allow patterns from this layer (order preserved).
        deny: Extracted deny patterns from this layer (order preserved).
    """

    provenance: Provenance
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]


@dataclass(frozen=True)
class TakeoverEnabledConflict:
    """
    A cross-level disagreement on ``takeover_mode.enabled`` (TOO-8 Phase 5).

    takeover_mode is a single-owner policy; different levels setting ``enabled``
    to DIFFERING values is a misconfiguration. When detected, the resolver
    fail-safes ``enabled`` to ``False`` (native Claude prompts stay active --
    nothing is silently bypassed) and carries this record so the hook can log a
    conflict entry and warn once per session.

    Attributes:
        sources: Tuple of ``(value, provenance)`` pairs, one per layer that
            EXPLICITLY set ``enabled``, in most-specific-first order. ``value`` is
            the boolean each layer set; ``provenance`` is that layer's origin.
    """

    sources: Tuple[Tuple[bool, "Provenance"], ...]

    def describe(self) -> str:
        """
        Return a human-readable summary citing each disagreeing source.

        Lists every level that set ``enabled`` with its value and provenance,
        most-specific first, for the conflict log entry.
        """
        parts = [f"{value} [{prov.describe_brief()}]" for value, prov in self.sources]
        return "takeover_mode.enabled set to conflicting values: " + "; ".join(parts)


@dataclass(frozen=True)
class TakeoverConfig:
    """
    Resolved takeover-mode configuration (TOO-8 Phase 5).

    ``enabled`` is resolved as a SINGLE-OWNER policy with fail-safe-on-conflict:
    levels that explicitly set it must agree; if they disagree, ``enabled`` is
    forced to ``False`` and :attr:`conflict` records the disagreement. Pattern
    lists (``ignored_allow_patterns``/``additional_ignored_patterns``) remain a
    UNION across all levels, and ``no_match_fallback`` resolves
    more-specific-wins.

    Attributes:
        enabled: Whether takeover mode is active (fail-safe ``False`` on conflict).
        ignored_allow_patterns: Blanket allow patterns suppressed from native config.
        additional_ignored_patterns: Extra user-supplied ignored patterns.
        no_match_fallback: 'deny' or 'warn_deny'.
        conflict: A :class:`TakeoverEnabledConflict` when levels disagree on
            ``enabled``, otherwise None.
    """

    enabled: bool
    ignored_allow_patterns: Tuple[str, ...]
    additional_ignored_patterns: Tuple[str, ...]
    no_match_fallback: str
    conflict: Optional["TakeoverEnabledConflict"] = None

    def normalized_ignored_patterns(self) -> frozenset:
        """
        Return the set of ignored patterns in extracted (wrapper-free) form.

        Combines ``ignored_allow_patterns`` and ``additional_ignored_patterns``
        and strips any recognised tool wrapper so the values can be compared
        against extracted pattern lists.
        """
        combined = tuple(self.ignored_allow_patterns) + tuple(
            self.additional_ignored_patterns
        )
        return frozenset(_strip_tool_wrapper(p) for p in combined)


@dataclass(frozen=True)
class Issue:
    """
    A structured, content-level configuration issue (display/log only).

    Replaces the hand-rolled validation walk in the hook. The config module
    detects issues and returns them; the hook decides whether/where to log.
    The config module performs NO logging side effects.

    Attributes:
        level: Severity label ('warning' or 'error').
        message: Human-readable description of the issue.
        corrective_steps: Suggested remediation.
    """

    level: str
    message: str
    corrective_steps: str


@dataclass(frozen=True)
class ConflictOverride:
    """
    A more-specific ``allow`` overriding a less-specific ``deny`` (Phase 4).

    Records BOTH sides of an allow-over-deny override so the conflict log can
    cite the winning allow and the overridden deny by provenance. The decision
    itself is unchanged (more-specific-wins keeps the allow); this is purely a
    record of the override for human/LLM review.

    The command/path that triggered the override is known by the caller (the
    hook), so it is NOT stored here; the hook composes the conflict-log message
    from this record plus the command it already holds.

    Attributes:
        winning_pattern: The more-specific ``allow`` pattern that won.
        winning_provenance: Provenance of the winning allow.
        overridden_pattern: The less-specific ``deny`` pattern that was overridden.
        overridden_provenance: Provenance of the overridden deny.
    """

    winning_pattern: str
    winning_provenance: Optional["Provenance"]
    overridden_pattern: str
    overridden_provenance: Optional["Provenance"]


@dataclass(frozen=True)
class ResolvedDecision:
    """
    Rich result of a more-specific-wins resolution (TOO-8 Phase 4).

    Carries everything the hook needs to log a decision with provenance and to
    surface an allow-over-deny conflict, without the hook re-deriving any of it.

    Attributes:
        decision: 'allow' or 'deny'.
        reason: Human-readable reason, with provenance appended as a bracketed
            suffix when a rule matched (e.g.
            "Command matches allow pattern: git *  [project: .claude/...]").
        provenance: Provenance of the winning rule, or None for a fail-closed
            default deny (no rule matched at any level).
        override: A :class:`ConflictOverride` when the winning allow overrode a
            less-specific deny, otherwise None.
    """

    decision: str
    reason: str
    provenance: Optional["Provenance"]
    override: Optional[ConflictOverride] = None


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
    """

    layers: Tuple[ConfigLayer, ...]
    start_dir: Optional[Path] = None

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
        Defaults to ``('Bash',)`` when no level configures any governed tool.

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
            return ("Bash",)
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
          it wins); defaults to ``'deny'``.

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

        Args:
            tool_name: Tool to extract hard-deny patterns for (e.g. 'Bash',
                'Read', 'Write', 'Edit').

        Returns:
            Tuple of (deny_patterns, allow_patterns) as immutable, de-duplicated
            tuples pooled across all toolguard_hook layers.
        """
        prefix = f"{tool_name}("
        seen_deny: Dict[str, None] = {}
        seen_allow: Dict[str, None] = {}

        for layer in self.layers:
            # hard_deny is a toolguard extension; ignore native Claude settings.
            if layer.is_native:
                continue
            section = layer.content.get("hard_deny", {})
            if not isinstance(section, dict):
                continue
            for perm in section.get("deny", []):
                if (
                    isinstance(perm, str)
                    and perm.startswith(prefix)
                    and perm.endswith(")")
                ):
                    seen_deny.setdefault(perm[len(prefix) : -1], None)
            for perm in section.get("allow", []):
                if (
                    isinstance(perm, str)
                    and perm.startswith(prefix)
                    and perm.endswith(")")
                ):
                    seen_allow.setdefault(perm[len(prefix) : -1], None)

        return tuple(seen_deny.keys()), tuple(seen_allow.keys())

    def permission_layers(self, tool_name: str) -> Tuple[ToolPatternLayer, ...]:
        """
        Return per-layer allow/deny patterns for a tool, most-specific first.

        Each layer carries provenance and the extracted (wrapper-free) patterns
        for ``tool_name`` from that source. Takeover filtering is already
        applied: when takeover mode is enabled, blanket ignored allow patterns
        are removed from native ('claude') layers only. Deny patterns are never
        filtered.

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

        prefix = f"{tool_name}("
        result = []

        for layer in self.layers:
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                permissions = {}

            allow = []
            for perm in permissions.get("allow", []):
                if (
                    isinstance(perm, str)
                    and perm.startswith(prefix)
                    and perm.endswith(")")
                ):
                    pattern = perm[len(prefix) : -1]
                    if takeover.enabled and layer.is_native and pattern in ignored:
                        continue
                    allow.append(pattern)

            deny = []
            for perm in permissions.get("deny", []):
                if (
                    isinstance(perm, str)
                    and perm.startswith(prefix)
                    and perm.endswith(")")
                ):
                    deny.append(perm[len(prefix) : -1])

            result.append(
                ToolPatternLayer(
                    provenance=layer.provenance, allow=tuple(allow), deny=tuple(deny)
                )
            )

        return tuple(result)

    def permission_levels_with_provenance(
        self, tool_name: str
    ) -> Tuple[
        Tuple[Tuple[str, ...], Tuple[str, ...], Tuple[ToolPatternLayer, ...]], ...
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
            Tuple of (allow_patterns, deny_patterns, layers) triples, one per
            hierarchy level, ordered most-specific first.
        """
        grouped: Dict[int, Tuple[List[str], List[str], List[ToolPatternLayer]]] = {}
        order: List[int] = []
        for layer in self.permission_layers(tool_name):
            spec = layer.provenance.specificity
            if spec not in grouped:
                grouped[spec] = ([], [], [])
                order.append(spec)
            allow_acc, deny_acc, layers_acc = grouped[spec]
            allow_acc.extend(layer.allow)
            deny_acc.extend(layer.deny)
            layers_acc.append(layer)
        return tuple(
            (tuple(grouped[s][0]), tuple(grouped[s][1]), tuple(grouped[s][2]))
            for s in order
        )

    @staticmethod
    def _provenance_for_pattern(
        layers: Tuple[ToolPatternLayer, ...], pattern: str, kind: str
    ) -> Optional["Provenance"]:
        """
        Find the provenance of the layer that contributed a matched pattern.

        Args:
            layers: The contributing layers for one level (most-specific first).
            pattern: The exact (wrapper-free) pattern string that matched.
            kind: 'allow' or 'deny' -- which side of the layer to search.

        Returns:
            The provenance of the first layer whose ``kind`` list contains the
            pattern, or None when not found (e.g. format drift).
        """
        for layer in layers:
            candidates = layer.allow if kind == "allow" else layer.deny
            if pattern in candidates:
                return layer.provenance
        return None

    def resolve_permission_detailed(
        self, tool_name: str, decide_detailed
    ) -> ResolvedDecision:
        """
        Resolve a decision with provenance and allow-over-deny conflict detection.

        Drives a most-specific-wins cascade over the hierarchy levels (evaluated
        MOST-SPECIFIC -> LEAST-SPECIFIC, first level that matches anything wins;
        no match at any level => fail-closed deny). ``decide_detailed`` must
        return ``(decision, reason, matched_pattern)``
        (or None) so the matched rule can be mapped to its source provenance. The
        returned :class:`ResolvedDecision` carries the winning rule's provenance
        (with provenance appended to the reason as a bracketed suffix) and, when
        the winning decision is an ``allow`` that overrides a ``deny`` in a
        LESS-specific level, a :class:`ConflictOverride` describing both sides.

        Conflict detection (Phase 4): only allow-over-deny overrides are
        conflicts. ``hard_deny`` denials are handled by the caller BEFORE this
        runs and are NOT conflicts.

        Args:
            tool_name: Tool whose levels to evaluate.
            decide_detailed: Callable
                ``(allow, deny) -> (decision, reason, matched_pattern) | None``.

        Returns:
            A :class:`ResolvedDecision`.
        """
        levels = self.permission_levels_with_provenance(tool_name)
        for index, (allow, deny, layers) in enumerate(levels):
            result = decide_detailed(allow, deny)
            if result is None:
                continue
            decision, reason, matched_pattern = result
            kind = "allow" if decision == "allow" else "deny"
            prov = self._provenance_for_pattern(layers, matched_pattern, kind)
            reason_with_prov = _append_provenance(reason, prov)

            override = None
            if decision == "allow":
                override = self._detect_override(
                    levels, index, matched_pattern, prov, decide_detailed
                )
            return ResolvedDecision(decision, reason_with_prov, prov, override)

        return ResolvedDecision(
            "deny", "Command does not match any allow patterns", None, None
        )

    @staticmethod
    def _detect_override(
        levels, winning_index, winning_pattern, winning_prov, decide_detailed
    ):
        """
        Scan LESS-specific levels for a deny overridden by the winning allow.

        Args:
            levels: All levels (most-specific first) as returned by
                :meth:`permission_levels_with_provenance`.
            winning_index: Index of the level whose allow won.
            winning_pattern: The winning allow pattern.
            winning_prov: Provenance of the winning allow.
            decide_detailed: The same per-level decider (used to test less-specific
                levels for a deny match on the same command).

        Returns:
            A :class:`ConflictOverride` for the first less-specific deny match, or
            None when no less-specific level denies the command.
        """
        for allow, deny, layers in levels[winning_index + 1 :]:
            if not deny:
                continue
            result = decide_detailed(allow, deny)
            # We only care about a DENY at this less-specific level. ``decide``
            # is deny-first, so a deny here surfaces as decision == 'deny'.
            if result is not None and result[0] == "deny":
                _decision, _reason, overridden_pattern = result
                overridden_prov = Configuration._provenance_for_pattern(
                    layers, overridden_pattern, "deny"
                )
                return ConflictOverride(
                    winning_pattern=winning_pattern,
                    winning_provenance=winning_prov,
                    overridden_pattern=overridden_pattern,
                    overridden_provenance=overridden_prov,
                )
        return None

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

        Aggregates allow/deny/ask permission strings (exact, with tool
        wrappers) across all toolguard_hook layers, de-duplicated and
        order-preserving. Used by divergence detection and migration tooling so
        those clients never open or parse config files themselves.

        Returns:
            Read-only mapping with keys 'allow', 'deny', 'ask', each a tuple of
            permission strings.
        """
        result = {"allow": [], "deny": [], "ask": []}
        for layer in self.layers:
            if layer.is_native:
                continue
            permissions = layer.content.get("permissions", {})
            if not isinstance(permissions, dict):
                continue
            for perm_type in ("allow", "deny", "ask"):
                for perm in permissions.get(perm_type, []):
                    if isinstance(perm, str) and perm not in result[perm_type]:
                        result[perm_type].append(perm)
        return MappingProxyType({k: tuple(v) for k, v in result.items()})

    # -- validation --------------------------------------------------------

    def validation_issues(self) -> Tuple[Issue, ...]:
        """
        Return structured content-level configuration issues.

        Replaces the hand-rolled file walk in the hook's startup validation.
        Detects:

        - Both a TOML and a JSON config file present at the same level/base.
        - Unsupported tools referenced in toolguard_hook permissions.
        - Tools referenced in permissions but absent from governed_tools.

        The config module only RETURNS issues; logging is the hook's job.

        Returns:
            Tuple of :class:`Issue`, in detection order (duplicate-file issues
            first, then permission-validation issues).
        """
        issues: List[Issue] = []

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

        # 3) Permission validation over the merged toolguard_hook content only.
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

        for warning in validate_permissions(merged_config):
            issues.append(
                Issue(
                    level=warning.get("level", "warning"),
                    message=warning["message"],
                    corrective_steps=warning["corrective_steps"],
                )
            )

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


def _parse_source(path: Path, file_format: str) -> Optional[dict]:
    """
    Parse a single config source file, returning its dict or None on failure.

    Args:
        path: Path to the config file.
        file_format: 'json' or 'toml'.

    Returns:
        Parsed dict, or None if the file cannot be read/parsed.
    """
    try:
        return load_config_file(path, file_format)
    except Exception as e:  # noqa: BLE001 - tolerate any unreadable source
        print(f"Warning: Failed to load {path}: {e}", file=sys.stderr)
        return None


def _level_for_path(path: Path) -> str:
    """
    Determine the conceptual level label for a discovered source path.

    Args:
        path: Path to the source file.

    Returns:
        'user' if the path is under the user's ~/.claude directory, otherwise
        'project'.
    """
    user_claude = Path.home() / ".claude"
    try:
        path.resolve().relative_to(user_claude.resolve())
        return "user"
    except ValueError:
        return "project"


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

    settings_path = (
        None if ignore_env_override else os.environ.get("CLAUDE_SETTINGS_PATH")
    )
    if settings_path:
        explicit = Path(settings_path)
        content = _parse_source(explicit, "json")
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
            content = _parse_source(hook_toml, "toml")
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
            content = _parse_source(hook_json, "json")
            if content is not None:
                layers.append(
                    ConfigLayer(
                        provenance=Provenance(
                            "explicit", "toolguard_hook", "json", hook_json
                        ),
                        content=MappingProxyType(content),
                    )
                )
        return Configuration(layers=tuple(layers), start_dir=start_dir)

    for path, source_type, file_format, specificity in _discover_levels(start_dir):
        content = _parse_source(path, file_format)
        if content is None:
            continue
        level = _level_for_path(path)
        layers.append(
            ConfigLayer(
                provenance=Provenance(
                    level, source_type, file_format, path, specificity
                ),
                content=MappingProxyType(content),
            )
        )

    return Configuration(layers=tuple(layers), start_dir=start_dir)


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
