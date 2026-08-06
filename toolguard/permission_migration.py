"""
Library implementation of toolguard's permission-migration workflow.

Merges permission patterns from Claude's ``settings.local.json`` into toolguard
configuration files (TOML or JSON): finds divergent/redundant patterns,
comment-preservingly rewrites the target config, and prunes the migrated
patterns out of ``settings.local.json``, with timestamped backups throughout.

TOO-45 R5b split this out of :mod:`toolguard.scripts.migrate_permissions`.
Before this split, that console-script module was simultaneously the
``toolguard-migrate`` CLI entry point AND the library three other modules
imported (:mod:`toolguard.auto_migrate`, :mod:`toolguard.tools.installer`,
:mod:`toolguard.tools.rule_apply`) -- an upward layer violation (a leaf-only
``scripts``/``tooling`` module being depended on for logic) that R5's
leafness predicate exists to catch. This module is the ``config``-layer home
for that logic: the only layer both ``auto_migrate`` (itself ``config``) and
``tools.*`` (``tooling``, which may reach down into ``config``) can legally
import from without a layering violation.
:mod:`toolguard.scripts.migrate_permissions` is now a thin CLI wrapper
(``parse_args`` / ``main``) around :func:`migrate` here.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from toolguard.config import (
    Configuration,
    discover_config_files,
    load_config_file,
    load_configuration,
)
from toolguard.config_divergence import (
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)
from toolguard.config_validation import extract_tool_name
from toolguard.config_write_guard import verified_write_config
from toolguard.rule_entry import (
    RuleEntry,
    normalize_entries_preserving,
    normalize_entry,
    real_patterns,
)
from toolguard.rule_sort import (
    RuleEntryOrStr,
    find_section_boundaries,
    parse_permissions_section_with_comments,
    reassemble_permissions_section,
    render_toml_entry,
    sort_patterns,
)


def create_backup(file_path: Path, backup_dir: Path) -> Path:
    """
    Create timestamped backup of a file.

    Backup filename format: basename.YYYY-MM-DD-HHMMSS.extension
    Example: settings.local.2026-02-05-143022.json

    Timestamps have second granularity, so two backups of the same file within the
    same wall-clock second would otherwise collide on an identical filename. To avoid
    silently overwriting (and thereby destroying) an earlier backup, a colliding
    candidate filename gets a monotonically increasing "-2", "-3", ... suffix appended
    until a filename that does not already exist is found. Example:
    settings.local.2026-02-05-143022.json,
    settings.local.2026-02-05-143022-2.json,
    settings.local.2026-02-05-143022-3.json, ...

    Args:
        file_path: Path to file to backup
        backup_dir: Directory where backup should be stored

    Returns:
        Path to created backup file

    Raises:
        OSError: If backup directory cannot be created or file cannot be copied
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Cannot backup non-existent file: {file_path}")

    # Create backup directory if needed
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")

    # Split filename into parts
    if file_path.suffix:
        # Has extension: name.ext -> name.TIMESTAMP.ext
        stem = file_path.stem
        suffix = file_path.suffix
        base_name = f"{stem}.{timestamp}"
    else:
        # No extension: name -> name.TIMESTAMP
        suffix = ""
        base_name = f"{file_path.name}.{timestamp}"

    # Disambiguate collisions (two backups landing in the same second) with a
    # monotonically increasing sequence number, so an earlier backup is never
    # silently overwritten.
    backup_path = backup_dir / f"{base_name}{suffix}"
    sequence = 2
    while backup_path.exists():
        backup_path = backup_dir / f"{base_name}-{sequence}{suffix}"
        sequence += 1

    # Copy file to backup location
    backup_path.write_bytes(file_path.read_bytes())

    return backup_path


def extract_pattern_key(pattern: str) -> Tuple[str, str]:
    """
    Extract tool name and command/path prefix for similarity comparison.

    Patterns are considered similar if they have the same tool and the same
    first "word" of the argument (up to space, colon, or wildcard).

    Examples:
        Bash(git push:*) -> ('Bash', 'git')
        Bash(git:*) -> ('Bash', 'git')
        Read(/tmp/*) -> ('Read', '/tmp/')
        Read(/tmp/foo/*) -> ('Read', '/tmp/')
        Write(*) -> ('Write', '*')

    Args:
        pattern: Permission pattern string like "Bash(git push:*)"

    Returns:
        Tuple of (tool_name, command_prefix)
    """
    # Extract tool name
    if "(" not in pattern:
        return (pattern, "")

    tool_name = pattern[: pattern.index("(")]
    arg_part = pattern[pattern.index("(") + 1 : pattern.rindex(")")]

    # Handle wildcard-only patterns
    if arg_part == "*":
        return (tool_name, "*")

    # For paths, extract up to first directory separator after root
    # Example: /tmp/foo/* -> /tmp/
    if arg_part.startswith("/"):
        # Find first / after root
        parts = arg_part.split("/")
        if len(parts) >= 3:  # ['', 'tmp', 'foo', ...]
            # Return up to and including second segment
            prefix = "/" + parts[1] + "/"
            return (tool_name, prefix)
        else:
            # Just root or one level: /tmp/* -> /tmp/
            return (tool_name, arg_part.split("*")[0] if "*" in arg_part else arg_part)

    # Extract first word/command component
    # Split on space or colon
    for delimiter in [" ", ":"]:
        if delimiter in arg_part:
            prefix = arg_part[: arg_part.index(delimiter)]
            return (tool_name, prefix)

    # No delimiter found - use arg up to wildcard or whole arg
    if "*" in arg_part:
        prefix = arg_part[: arg_part.index("*")]
        return (tool_name, prefix)

    return (tool_name, arg_part)


def is_superset(existing: str, new: str) -> bool:
    """
    Check if existing pattern is a superset of new pattern.

    Only handles simple :*) postfix patterns. Skips extended syntax.
    Example: Bash(uv run ruff:*) is superset of Bash(uv run ruff format:*)

    Args:
        existing: Existing pattern to check
        new: New pattern to check

    Returns:
        True if existing is a superset of new, False otherwise
    """
    # Skip extended syntax patterns
    if existing.startswith(("[regex]", "[glob]", "[native]")):
        return False
    if new.startswith(("[regex]", "[glob]", "[native]")):
        return False

    # Only handle :*) postfix patterns
    if not existing.endswith(":*)") or not new.endswith(":*)"):
        return False

    # Extract command part before :*)
    existing_cmd = existing[:-3]  # Remove ':*)'
    new_cmd = new[:-3]

    # existing is superset if its command is a prefix of new's command
    # and new's command is longer (to avoid matching identical patterns)
    # IMPORTANT: Check that the prefix ends with a word boundary (space or start of pattern)
    # to avoid false positives like 'ruff' matching 'ruffle'
    if new_cmd.startswith(existing_cmd) and len(new_cmd) > len(existing_cmd):
        # Check word boundary: next char after prefix should be space or colon
        next_char_idx = len(existing_cmd)
        if next_char_idx < len(new_cmd):
            next_char = new_cmd[next_char_idx]
            # Space indicates word boundary (e.g., "uv run ruff" -> "uv run ruff format")
            return next_char == " "
    return False


def find_redundant_patterns(
    native_perms: Dict[str, List[str]],
    toolguard_perms: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """
    Find patterns in native config that are redundant.

    A pattern is redundant if it:
    1. EXACTLY matches a pattern in toolguard config
    2. Is a SUBSET of a toolguard pattern (covered by broader rule)

    Args:
        native_perms: Permissions from settings.local.json
        toolguard_perms: Permissions from toolguard config

    Returns:
        Dictionary with same structure as permissions, containing redundant patterns
    """
    redundant = {"allow": [], "deny": [], "ask": []}

    for perm_type in ["allow", "deny", "ask"]:
        native_patterns = native_perms.get(perm_type, [])
        toolguard_patterns = toolguard_perms.get(perm_type, [])

        for native_pattern in native_patterns:
            # Check for exact duplicates
            if native_pattern in toolguard_patterns:
                redundant[perm_type].append(native_pattern)
                continue

            # Check if any toolguard pattern is a superset
            for toolguard_pattern in toolguard_patterns:
                if is_superset(toolguard_pattern, native_pattern):
                    redundant[perm_type].append(native_pattern)
                    break

    return redundant


def extract_meaningful_prefix(pattern: str) -> str:
    """
    Extract meaningful prefix from pattern for similarity comparison.

    A meaningful prefix is the content between Tool( and the first :, *, or ).
    Returns empty string for blanket patterns like Bash(*), Read(*).

    Examples:
        Bash(*) -> '' (no meaningful prefix)
        Read(*) -> '' (no meaningful prefix)
        Bash(uv run ruff format:*) -> 'uv run ruff format'
        Bash(find:*) -> 'find'
        Read(/tmp/*) -> '/tmp/'

    Args:
        pattern: Permission pattern string

    Returns:
        Meaningful prefix or empty string if none exists
    """
    if "(" not in pattern:
        return ""

    arg_part = pattern[pattern.index("(") + 1 : pattern.rindex(")")]

    # Blanket pattern - no meaningful prefix
    if arg_part == "*":
        return ""

    # For paths, meaningful prefix is path up to wildcard
    if arg_part.startswith("/"):
        if "*" in arg_part:
            prefix = arg_part[: arg_part.index("*")]
            # Ensure we have at least one directory component
            if prefix.count("/") >= 2:  # At least /dir/
                return prefix
            elif prefix and prefix != "/":
                return prefix
        return arg_part

    # Extract content before first :, *, or ) delimiter
    for delimiter in [":", "*", ")"]:
        if delimiter in arg_part:
            prefix = arg_part[: arg_part.index(delimiter)].strip()
            if prefix:  # Non-empty prefix
                return prefix

    # Use whole arg if no delimiters
    return arg_part.strip()


def detect_similar_patterns(
    new_pattern: str,
    existing_patterns: List[str],
    max_matches: int = 3,
) -> List[Tuple[str, float, bool]]:
    """
    Find existing patterns that are similar to the new pattern.

    Uses difflib for ranking by similarity score and detects superset relationships.
    Only flags patterns as similar if they have meaningful prefix matches.

    Args:
        new_pattern: Pattern being added
        existing_patterns: List of patterns already in config
        max_matches: Maximum number of similar patterns to return (default: 3)

    Returns:
        List of tuples: (pattern, similarity_score, is_superset)
        Sorted by similarity score (highest first), limited to max_matches
    """
    # Handle empty list
    if not existing_patterns:
        return []

    # Check if new pattern has meaningful prefix
    new_prefix = extract_meaningful_prefix(new_pattern)
    if not new_prefix:
        # Blanket pattern - skip similarity check entirely
        return []

    # Use difflib to find close matches with ranking
    # cutoff=0.7 balances between false positives and false negatives
    # n must be > 0, so use max(1, len(existing_patterns))
    close_matches = get_close_matches(
        new_pattern, existing_patterns, n=max(1, len(existing_patterns)), cutoff=0.7
    )

    # Calculate similarity scores and check for superset relationships
    # Only include patterns with meaningful prefix match
    results = []
    for match in close_matches:
        match_prefix = extract_meaningful_prefix(match)

        # Skip if existing pattern has no meaningful prefix
        if not match_prefix:
            continue

        # Check if prefixes have meaningful overlap
        # (at least one shares a common start with the other)
        has_prefix_match = (
            new_prefix.startswith(match_prefix)
            or match_prefix.startswith(new_prefix)
            or new_prefix in match_prefix
            or match_prefix in new_prefix
        )

        if not has_prefix_match:
            continue

        # Calculate similarity ratio
        ratio = SequenceMatcher(None, new_pattern, match).ratio()

        # Check if this is a superset relationship
        is_superset_match = is_superset(match, new_pattern)

        results.append((match, ratio, is_superset_match))

    # Sort by similarity score (highest first)
    results.sort(key=lambda x: x[1], reverse=True)

    # Limit to max_matches
    results = results[:max_matches]

    # Filter out if too many patterns share the same prefix
    # (indicates prefix isn't discriminating)
    if len(close_matches) > max_matches * 2:
        # Check if many patterns share the same tool and first word
        new_key = extract_pattern_key(new_pattern)
        prefix_count = sum(
            1 for p in existing_patterns if extract_pattern_key(p) == new_key
        )
        if prefix_count > max_matches * 2:
            # Too many with same prefix - not useful similarity
            return []

    return results


def generate_permissions_section(
    permissions: Dict[str, List[RuleEntryOrStr]], auto_sort: bool = True
) -> str:
    """
    Generate the [permissions] section content.

    Args:
        permissions: Dictionary with 'allow', 'deny', 'ask' keys, each a list
            of pattern ``str`` and/or :class:`~toolguard.rule_entry.RuleEntry`
            (TOO-19 Phase 0a increment 8: this is the from-scratch writer, used
            when there is no existing file/section to reuse original lines
            from, so every entry is rendered fresh via
            :func:`~toolguard.rule_sort.render_toml_entry`).
        auto_sort: Whether to sort patterns before writing

    Returns:
        String containing the complete [permissions] section
    """
    # Sort if requested
    if auto_sort:
        permissions = {
            key: sort_patterns(entries) for key, entries in permissions.items()
        }

    # Generate TOML content
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        entries = permissions.get(perm_type, [])
        if entries:
            lines.append(f"{perm_type} = [")
            for entry in entries:
                lines.append(f"  {render_toml_entry(entry)},")
            lines.append("]")
            lines.append("")

    return "\n".join(lines)


def _patterns_from_permissions(
    permissions: Dict[str, List[RuleEntryOrStr]],
) -> List[str]:
    """
    Extract every pattern string out of a permissions dict, plain or structured.

    Builds the ``expected_patterns`` argument passed to
    :func:`~toolguard.config_write_guard.verified_write_config`'s content-loss
    guard (TOO-19 corrective change, Change 2/4): every pattern this write is
    ASKED to write must still be present in the text the write path actually
    produces, or the write path itself silently lost a rule -- e.g. the
    ``rule_lines``/``rule_comments`` same-pattern-key collision bug in
    ``rule_sort.reassemble_permissions_section`` (TOO-19 Change 4).

    Delegates to :func:`~toolguard.rule_entry.real_patterns` (TOO-19 review
    fix) rather than extracting ``.pattern`` unconditionally: an entry from
    :func:`~toolguard.rule_entry.normalize_entries_preserving` may carry a
    SYNTHESIZED pattern (a raw element that failed to normalize, e.g. a
    structured entry missing its ``match`` key) that can never appear in the
    text this module actually writes, so including it here previously made
    the content-loss guard wrongly refuse every write once a config held one
    such malformed entry (confirmed repro).

    Args:
        permissions: Dict with ``'allow'``/``'deny'``/``'ask'`` keys, each a
            list of pattern ``str`` and/or ``RuleEntry``.

    Returns:
        Flat list of every REAL pattern string across all three lists (order
        and duplicates preserved -- the guard only cares about set
        membership), excluding any synthesized-pattern entry.
    """
    return [
        pattern
        for entries in permissions.values()
        for pattern in real_patterns(entries)
    ]


def write_toml_config(
    config_path: Path,
    permissions: Dict[str, List[RuleEntryOrStr]],
    auto_sort: bool = True,
) -> None:
    """
    Write permissions to TOML configuration file.

    Preserves all other sections, top-level keys, and comments in the file.
    Only replaces the [permissions] section content while maintaining comments.
    Every branch below writes via
    :func:`~toolguard.config_write_guard.verified_write_config`, never a raw
    ``Path.write_text`` -- the guard refuses to write text that fails to parse
    or that silently drops one of ``permissions``'s own patterns (TOO-19
    corrective change: a config file this project cannot parse back is a
    permanent, unrecoverable loss for a user whose config is not version
    controlled).

    Args:
        config_path: Path to TOML file to write
        permissions: Dictionary with 'allow', 'deny', 'ask' keys, each a list
            of pattern ``str`` and/or ``RuleEntry`` (TOO-19 Phase 0a increment 8)
        auto_sort: Whether to sort patterns before writing

    Raises:
        OSError: If file cannot be written
        ConfigWriteVerificationError: The text this function produced fails
            to parse, or would drop one of ``permissions``'s own patterns.
    """
    expected_patterns = _patterns_from_permissions(permissions)

    # Check if file exists
    if not config_path.exists():
        # Create new file with just permissions section (no comments to preserve)
        new_permissions_section = generate_permissions_section(permissions, auto_sort)
        verified_write_config(
            config_path,
            new_permissions_section + "\n",
            "toml",
            expected_patterns=expected_patterns,
        )
        return

    # Read existing file
    original_text = config_path.read_text()

    # Find [permissions] section boundaries
    start_pos, end_pos = find_section_boundaries(original_text, "permissions")

    if start_pos == -1:
        # No [permissions] section exists - append at end (no comments to preserve)
        new_permissions_section = generate_permissions_section(permissions, auto_sort)
        # Add blank line before if file doesn't end with newline
        if original_text and not original_text.endswith("\n"):
            new_content = original_text + "\n\n" + new_permissions_section + "\n"
        else:
            new_content = original_text + "\n" + new_permissions_section + "\n"
    else:
        # Extract existing [permissions] section
        existing_section_text = original_text[start_pos:end_pos]

        # Parse the existing section to preserve comments
        parsed_structure = parse_permissions_section_with_comments(
            existing_section_text
        )

        # Reassemble with new permissions, preserving comments
        new_permissions_section = reassemble_permissions_section(
            parsed_structure, permissions, auto_sort
        )

        # Replace existing [permissions] section
        before = original_text[:start_pos]
        after = original_text[end_pos:]

        # Ensure proper spacing
        new_content = before + new_permissions_section + "\n" + after

    verified_write_config(
        config_path, new_content, "toml", expected_patterns=expected_patterns
    )


def write_json_config(
    config_path: Path,
    permissions: Dict[str, List[RuleEntryOrStr]],
    auto_sort: bool = True,
) -> None:
    """
    Write permissions to JSON configuration file.

    Writes via :func:`~toolguard.config_write_guard.verified_write_config`,
    never a raw file write (TOO-19 corrective change) -- see
    :func:`write_toml_config`'s docstring for why.

    Args:
        config_path: Path to JSON file to write
        permissions: Dictionary with 'allow', 'deny', 'ask' keys, each a list
            of pattern ``str`` and/or ``RuleEntry`` (TOO-19 Phase 0a increment
            8). A ``RuleEntry`` is emitted via ``to_source()`` -- for JSON
            this is nearly free: ``to_source()`` returns the original ``dict``
            or ``str`` verbatim and ``json.dump`` handles either with no
            special casing.
        auto_sort: Whether to sort patterns before writing

    Raises:
        OSError: If file cannot be written
        ConfigWriteVerificationError: The text this function produced fails
            to parse, or would drop one of ``permissions``'s own patterns.
    """
    # Sort if requested
    if auto_sort:
        permissions = {
            key: sort_patterns(entries) for key, entries in permissions.items()
        }

    expected_patterns = _patterns_from_permissions(permissions)

    # Read existing config if it exists
    config = {}
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError, OSError:
            pass

    # Update permissions -- render each RuleEntry to its JSON-native source
    # (str or dict) at this single emission point; a bare str entry (legacy
    # contract) passes through unchanged.
    config["permissions"] = {
        key: [
            entry.to_source() if isinstance(entry, RuleEntry) else entry
            for entry in entries
        ]
        for key, entries in permissions.items()
    }

    new_text = json.dumps(config, indent=2) + "\n"
    verified_write_config(
        config_path, new_text, "json", expected_patterns=expected_patterns
    )


def update_settings_file(
    settings_path: Path,
    migrated_patterns: Dict[str, List[str]],
    redundant_patterns: Dict[str, List[str]] = None,
) -> None:
    """
    Remove migrated and redundant patterns from settings.local.json.

    Leaves permissions structure with empty lists for unmigrated patterns.
    Writes via :func:`~toolguard.config_write_guard.verified_write_config`
    (TOO-19 corrective change): ``settings.local.json`` is Claude's own native
    settings file, typically also outside version control, so a corrupting
    write here is the same unrecoverable-data-loss risk this guard exists to
    prevent. The content-loss check here confirms every pattern that was NOT
    migrated/redundant (and so should survive this edit) is still present.

    Args:
        settings_path: Path to settings.local.json
        migrated_patterns: Dict of patterns that were migrated (to remove)
        redundant_patterns: Dict of patterns that are redundant (to remove)

    Raises:
        OSError: If file cannot be read or written
        json.JSONDecodeError: If file contains invalid JSON
        ConfigWriteVerificationError: The text this function produced fails
            to parse, or would drop a pattern that was not being removed.
    """
    if redundant_patterns is None:
        redundant_patterns = {"allow": [], "deny": [], "ask": []}

    # Load current config
    with open(settings_path, "r") as f:
        config = json.load(f)

    permissions = config.get("permissions", {})

    # Remove migrated and redundant patterns
    for perm_type in ["allow", "deny", "ask"]:
        if perm_type in permissions:
            current = permissions[perm_type]
            migrated = set(migrated_patterns.get(perm_type, []))
            redundant = set(redundant_patterns.get(perm_type, []))
            to_remove = migrated | redundant
            # Keep only patterns that were not migrated or redundant
            permissions[perm_type] = [p for p in current if p not in to_remove]

    config["permissions"] = permissions

    expected_patterns = [
        pattern for values in permissions.values() for pattern in values
    ]
    new_text = json.dumps(config, indent=2) + "\n"
    verified_write_config(
        settings_path, new_text, "json", expected_patterns=expected_patterns
    )


@dataclass
class _MigrationSources:
    """
    Everything migrate() reads before it can compute or report anything.

    Pure load/discover phase: talks to disk (settings.local.json, the
    hierarchical toolguard configuration, and the raw list of discovered
    config files) but performs no comparison and prints nothing.
    """

    native_perms: Dict[str, List[str]]
    configuration: Configuration
    toolguard_perms: Dict[str, List[str]]
    config_files: List[Tuple[Path, str, str]]
    governed: set
    ignored_patterns: List[str]


def _load_migration_sources(
    project_root: Path, settings_path: Path
) -> _MigrationSources:
    """
    Load native permissions, the hierarchical toolguard configuration, and the
    discovered config file list -- everything migrate() needs before it can
    start comparing native vs. toolguard permissions.

    Args:
        project_root: Path to project root directory.
        settings_path: Path to the project's settings.local.json (assumed to
            exist -- migrate() checks this before calling here).

    Returns:
        A :class:`_MigrationSources` bundling every loaded/discovered value.
    """
    native_perms = get_native_permissions(settings_path)

    # Load configuration once and reuse for both permissions and takeover mode.
    # ignore_env_override=True: the migration tool selects its WRITE target via
    # project-based discovery (see discover_config_files below), so the READ path
    # must be project-based too. Honouring CLAUDE_SETTINGS_PATH here would analyse
    # an unrelated project's config while writing to this project's files.
    configuration = load_configuration(project_root, ignore_env_override=True)
    toolguard_perms = get_toolguard_permissions(configuration)

    # The migration target-file selection still needs the discovered file paths
    # (it writes to an existing toolguard_hook file or creates one).
    config_files = discover_config_files(project_root)

    # Build the list of ignored patterns from the hierarchical takeover config.
    # Only populated when takeover mode is enabled, preserving the prior behaviour
    # where ignored_patterns remained empty when takeover was off.
    takeover = configuration.takeover_mode()
    ignored_patterns = []
    if takeover.enabled:
        ignored_patterns = list(takeover.ignored_allow_patterns) + list(
            takeover.additional_ignored_patterns
        )

    governed = set(configuration.governed_tools())

    return _MigrationSources(
        native_perms=native_perms,
        configuration=configuration,
        toolguard_perms=toolguard_perms,
        config_files=config_files,
        governed=governed,
        ignored_patterns=ignored_patterns,
    )


def _find_skipped_ungoverned_patterns(
    native_perms: Dict[str, List[str]], governed: set
) -> List[str]:
    """
    Return native patterns for tools toolguard does not govern.

    A rule for a tool toolguard does not govern (e.g. WebFetch/Skill) must be
    left in settings.local.json -- moving it would leave it enforced by
    neither toolguard nor native Claude (issue #1).

    Args:
        native_perms: Native ``settings.local.json`` permissions dict.
        governed: The live set of tools toolguard's configuration governs.

    Returns:
        Sorted list of patterns intentionally left untouched.
    """
    return sorted(
        {
            pattern
            for perm_type in ("allow", "deny", "ask")
            for pattern in native_perms.get(perm_type, [])
            if extract_tool_name(pattern) not in governed
        }
    )


def _print_skipped_ungoverned(skipped_ungoverned: List[str]) -> None:
    """Print the "leaving these ungoverned-tool rules in place" notice, if any."""
    if not skipped_ungoverned:
        return
    print(
        f"Leaving {len(skipped_ungoverned)} rule(s) for ungoverned tools in "
        "settings.local.json (toolguard does not govern these; moving them would "
        "disable them):"
    )
    for pattern in skipped_ungoverned:
        print(f"  - {pattern}")


def _print_divergent_report(
    divergent: Dict[str, List[str]], toolguard_perms: Dict[str, List[str]]
) -> None:
    """Print the "found N pattern(s) to migrate" report, annotating superset coverage."""
    total_divergent = sum(len(patterns) for patterns in divergent.values())
    if total_divergent == 0:
        return
    print(f"Found {total_divergent} pattern(s) to migrate:")
    print()
    for perm_type in ["allow", "deny", "ask"]:
        patterns = divergent[perm_type]
        if not patterns:
            continue
        print(f"  {perm_type.upper()}:")
        for pattern in patterns:
            superset_match = None
            for existing in toolguard_perms.get(perm_type, []):
                if is_superset(existing, pattern):
                    superset_match = existing
                    break
            if superset_match:
                print(f"    - {pattern}  ← COVERED BY: {superset_match}")
            else:
                print(f"    - {pattern}")
        print()


def _print_redundant_report(redundant: Dict[str, List[str]]) -> None:
    """Print the "found N redundant pattern(s) to remove" report."""
    total_redundant = sum(len(patterns) for patterns in redundant.values())
    if total_redundant == 0:
        return
    print(
        f"Found {total_redundant} redundant pattern(s) to remove (already in toolguard config):"
    )
    print()
    for perm_type in ["allow", "deny", "ask"]:
        patterns = redundant[perm_type]
        if not patterns:
            continue
        print(f"  {perm_type.upper()}:")
        for pattern in patterns:
            print(f"    - {pattern}")
        print()


def _resolve_target_config_path(
    project_root: Path, config_files: List[Tuple[Path, str, str]]
) -> Tuple[Path, str]:
    """
    Pick the toolguard config file migrate() writes to, and announce the choice.

    The write target must always be project_root's OWN .claude directory --
    never an existing toolguard_hook file discovered at a different level
    (e.g. an ancestor project or the user's home ~/.claude). config_files
    mixes project- and user-level entries in one priority-ordered list (see
    discover_config_files), so scanning it unfiltered would silently widen
    migration scope from "this project" to "the user's global config" when
    the project has no toolguard_hook config of its own yet (TOO-15).

    Args:
        project_root: Path to project root directory.
        config_files: The discovered config file list from discover_config_files().

    Returns:
        ``(target_config_path, target_format)`` -- an existing project-level
        toolguard_hook file if one was found, otherwise a fresh
        ``project_root/.claude/toolguard_hook.toml`` path with format
        ``"toml"``.
    """
    project_claude_dir = project_root / ".claude"
    # discover_config_files() internally re-resolves the project root (see
    # find_project_root -> resolve_project_root), so entries it returns carry
    # a *resolved* directory even when the project_root passed into migrate()
    # here is not (e.g. through a symlinked tmp path). Compare resolved forms
    # so the scoping check is correct regardless of that discrepancy.
    resolved_project_claude_dir = project_claude_dir.resolve()

    # Check for an existing toolguard config file, restricted to project_root's
    # own .claude directory. Entries from any other directory (ancestor or
    # user-level) are ignored here -- discover_config_files() itself is left
    # untouched since it is relied on elsewhere for its intentional
    # multi-level (project + ancestor + user) priority behaviour.
    for file_path, source_type, file_format in config_files:
        if source_type != "toolguard_hook":
            continue
        if file_path.parent.resolve() != resolved_project_claude_dir:
            continue
        print(f"Will add patterns to: {file_path}")
        return file_path, file_format

    # If no toolguard config exists at the project level, create
    # project_root/.claude/toolguard_hook.toml -- never fall back to an
    # existing file at a different directory.
    target_config_path = project_claude_dir / "toolguard_hook.toml"
    print(f"No toolguard config found. Will create: {target_config_path}")
    return target_config_path, "toml"


def _print_similar_pattern_warnings(
    divergent: Dict[str, List[str]], toolguard_perms: Dict[str, List[str]]
) -> None:
    """Print near-duplicate warnings for every pattern about to be migrated."""
    print()
    print("Checking for similar patterns...")
    similar_found = False
    for perm_type in ["allow", "deny", "ask"]:
        existing_patterns = toolguard_perms.get(perm_type, [])
        for new_pattern in divergent[perm_type]:
            similar = detect_similar_patterns(
                new_pattern, existing_patterns, max_matches=3
            )
            if similar:
                if not similar_found:
                    print("Similar patterns (top 3 by similarity):")
                    similar_found = True
                for sim_pattern, score, is_superset_match in similar:
                    superset_note = " [SUPERSET]" if is_superset_match else ""
                    print(
                        f"  '{new_pattern}' similar to '{sim_pattern}' ({score:.2f}){superset_note}"
                    )

    if not similar_found:
        print("  No similar patterns found.")
    print()


def _print_dry_run_summary(
    settings_path: Path,
    backup_dir: Path,
    target_config_path: Path,
    total_divergent: int,
    total_redundant: int,
    auto_sort: bool,
) -> None:
    """Print the numbered "would perform these actions" preview for --dry-run."""
    print("DRY RUN: No changes will be made.")
    print()
    print("Would perform these actions:")
    print(f"  1. Create backup of {settings_path} in {backup_dir}")
    if target_config_path.exists():
        print(f"  2. Create backup of {target_config_path} in {backup_dir}")
        if total_divergent > 0:
            print(f"  3. Add {total_divergent} pattern(s) to {target_config_path}")
    else:
        if total_divergent > 0:
            print(f"  2. Create new config file {target_config_path}")
            print(f"  3. Add {total_divergent} pattern(s) to new config")
    total_to_remove = total_divergent + total_redundant
    if total_to_remove > 0:
        print(f"  4. Remove {total_to_remove} pattern(s) from {settings_path}")
        print(f"      ({total_divergent} migrated, {total_redundant} redundant)")
    if auto_sort:
        print("  5. Sort all patterns in target config")


def _build_merged_permissions(
    target_config_path: Path,
    target_format: str,
    divergent: Dict[str, List[str]],
    total_divergent: int,
) -> Dict[str, List[RuleEntry]]:
    """
    Merge the target config's existing permissions with the divergent patterns.

    Loads and normalizes the target config's existing [permissions] (if the
    file exists), then appends every not-yet-present divergent pattern.

    W1 fix (TOO-19 Phase 0a increment 8): every raw element is normalized into
    a RuleEntry via normalize_entries_preserving -- INCLUDING one that fails
    to normalize (preserved verbatim, never dropped). Previously this assigned
    the raw list straight through, so a structured (dict) entry either got
    silently deleted by reassemble_permissions_section (only patterns present
    in new_permissions survive) or crashed sort_patterns with "TypeError:
    unhashable type: 'dict'" -- both defects this increment fixes.

    Args:
        target_config_path: Path to the toolguard config being written to.
        target_format: ``"toml"`` or ``"json"``.
        divergent: Patterns to migrate, keyed by ``"allow"``/``"deny"``/``"ask"``.
        total_divergent: Sum of all divergent pattern counts (``0`` skips the
            "add divergent patterns" step entirely, leaving just the
            normalized existing permissions).

    Returns:
        Merged permissions dict, ready for :func:`write_toml_config` or
        :func:`write_json_config`.
    """
    merged_perms: Dict[str, List[RuleEntry]] = {"allow": [], "deny": [], "ask": []}
    if target_config_path.exists():
        existing_config = load_config_file(target_config_path, target_format)
        existing_perms = existing_config.get("permissions", {})
        for perm_type in ["allow", "deny", "ask"]:
            merged_perms[perm_type] = list(
                normalize_entries_preserving(
                    existing_perms.get(perm_type, []), is_native=False
                )
            )

    if total_divergent > 0:
        for perm_type in ["allow", "deny", "ask"]:
            existing_patterns = {entry.pattern for entry in merged_perms[perm_type]}
            for pattern in divergent[perm_type]:
                if pattern in existing_patterns:
                    continue
                # `pattern` is already a confirmed Tool(...)-wrapped string
                # (get_native_permissions() only keeps is_tool_wrapper
                # matches), so normalize_entry cannot return None here --
                # the fallback below is defensive, not expected to trigger.
                new_entry, _issues = normalize_entry(pattern, is_native=False)
                if new_entry is None:
                    new_entry = RuleEntry(pattern=pattern, raw=pattern)
                merged_perms[perm_type].append(new_entry)
                existing_patterns.add(pattern)

    return merged_perms


def _apply_migration(  # noqa: PLR0913 -- 9 args; pre-existing, not in TOO-45 scope
    settings_path: Path,
    target_config_path: Path,
    target_format: str,
    backup_dir: Path,
    divergent: Dict[str, List[str]],
    redundant: Dict[str, List[str]],
    total_divergent: int,
    total_redundant: int,
    auto_sort: bool,
) -> int:
    """
    Back up, write, and clean up: the actual (non-dry-run) migration write phase.

    Backs up settings.local.json and (if it exists) the target config, merges
    divergent patterns into the target config's permissions and writes it, and
    removes migrated/redundant patterns from settings.local.json. Any failure
    is caught and reported without letting an exception propagate out of the
    migration -- backups already made remain available for manual recovery.

    Args:
        settings_path: Path to settings.local.json.
        target_config_path: Path to the toolguard config being written to.
        target_format: ``"toml"`` or ``"json"``.
        backup_dir: Directory backups are written into.
        divergent: Patterns to migrate, keyed by ``"allow"``/``"deny"``/``"ask"``.
        redundant: Patterns to remove as already covered, same keying.
        total_divergent: Sum of all divergent pattern counts.
        total_redundant: Sum of all redundant pattern counts.
        auto_sort: Whether to sort patterns before writing the target config.

    Returns:
        ``0`` on success, ``1`` if any step raised.
    """
    print("Starting migration...")
    print()

    try:
        # 1. Backup settings.local.json
        print(f"Creating backup of {settings_path.name}...")
        settings_backup = create_backup(settings_path, backup_dir)
        print(f"  Backup created: {settings_backup}")

        # 2. Backup target config if it exists
        if target_config_path.exists():
            print(f"Creating backup of {target_config_path.name}...")
            config_backup = create_backup(target_config_path, backup_dir)
            print(f"  Backup created: {config_backup}")

        # 3. Merge divergent patterns into toolguard config
        print(f"Adding patterns to {target_config_path.name}...")
        merged_perms = _build_merged_permissions(
            target_config_path, target_format, divergent, total_divergent
        )

        if total_divergent > 0:
            # Ensure target directory exists
            target_config_path.parent.mkdir(parents=True, exist_ok=True)

            # Write to target config
            if target_format == "toml":
                write_toml_config(target_config_path, merged_perms, auto_sort)
            else:
                write_json_config(target_config_path, merged_perms, auto_sort)

            print(f"  Added {total_divergent} pattern(s)")

        # 4. Remove migrated and redundant patterns from settings.local.json
        total_to_remove = total_divergent + total_redundant
        if total_to_remove > 0:
            print(f"Removing patterns from {settings_path.name}...")
            update_settings_file(settings_path, divergent, redundant)
            print(
                f"  Removed {total_to_remove} pattern(s) ({total_divergent} migrated, {total_redundant} redundant)"
            )

        print()
        print("Migration completed successfully!")
        print()
        print("Backups created in:", backup_dir)

        return 0

    except Exception as e:
        print()
        print(f"ERROR: Migration failed: {e}", file=sys.stderr)
        print()
        print("Backups (if created) are available in:", backup_dir)
        print("You can manually restore from backups if needed.")
        return 1


def migrate(
    project_root: Path,
    dry_run: bool = False,
    auto_sort: bool = True,
    backup_dir: Optional[Path] = None,
) -> int:
    """
    Perform the migration of permissions from settings.local.json to toolguard config.

    Structured as four phases, each delegated to its own helper: load/discover
    sources (:func:`_load_migration_sources`), compute the divergent/redundant
    pattern sets and report them, resolve the write target
    (:func:`_resolve_target_config_path`), and -- unless this is a dry run --
    apply the migration (:func:`_apply_migration`). This function itself only
    sequences those phases and handles the early-exit "nothing to do" cases;
    it performs no file I/O of its own.

    This is the library entry point the ``toolguard-migrate`` console script
    (:func:`toolguard.scripts.migrate_permissions.main`) delegates to, and
    that :mod:`toolguard.auto_migrate` calls directly for unattended
    migration -- see this module's docstring for why the logic lives here
    rather than in the script module.

    Args:
        project_root: Path to project root directory
        dry_run: If True, preview changes without modifying files
        auto_sort: If True, sort patterns after migration
        backup_dir: Directory for backup files (default: project_root/logs/config-backups)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    if backup_dir is None:
        backup_dir = project_root / "logs" / "config-backups"

    settings_path = project_root / ".claude" / "settings.local.json"
    if not settings_path.exists():
        print(f"No settings.local.json found at {settings_path}")
        print("Nothing to migrate.")
        return 0

    sources = _load_migration_sources(project_root, settings_path)

    # Find divergent patterns (patterns in native but not in toolguard). Restrict to
    # the config's GOVERNED tools -- see _find_skipped_ungoverned_patterns's docstring
    # for why. Passing the live governed set means this tracks changes over time
    # (e.g. WebFetch becoming governed).
    divergent = find_divergent_patterns(
        sources.native_perms,
        sources.toolguard_perms,
        sources.ignored_patterns,
        governed_tools=sources.governed,
    )
    _print_skipped_ungoverned(
        _find_skipped_ungoverned_patterns(sources.native_perms, sources.governed)
    )

    # Find redundant patterns (exact duplicates or subsets)
    redundant = find_redundant_patterns(sources.native_perms, sources.toolguard_perms)

    total_divergent = sum(len(patterns) for patterns in divergent.values())
    total_redundant = sum(len(patterns) for patterns in redundant.values())

    if total_divergent == 0 and total_redundant == 0:
        print("No new patterns found to migrate.")
        print("All patterns in settings.local.json are already in toolguard config.")
        return 0

    _print_divergent_report(divergent, sources.toolguard_perms)
    _print_redundant_report(redundant)

    target_config_path, target_format = _resolve_target_config_path(
        project_root, sources.config_files
    )

    if total_divergent > 0:
        _print_similar_pattern_warnings(divergent, sources.toolguard_perms)

    if dry_run:
        _print_dry_run_summary(
            settings_path,
            backup_dir,
            target_config_path,
            total_divergent,
            total_redundant,
            auto_sort,
        )
        return 0

    return _apply_migration(
        settings_path,
        target_config_path,
        target_format,
        backup_dir,
        divergent,
        redundant,
        total_divergent,
        total_redundant,
        auto_sort,
    )
