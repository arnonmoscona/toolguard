"""
Permission migration script for toolguard.

Migrates permission patterns from Claude's settings.local.json to toolguard
configuration files (TOML or JSON). Creates timestamped backups and provides
dry-run mode for safe preview of changes.
"""

import argparse
import json
import sys
from datetime import datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Dict, List, Tuple

from toolguard.config import (
    discover_config_files,
    find_project_root,
    load_config_file,
    load_configuration,
)
from toolguard.config_divergence import (
    find_divergent_patterns,
    get_native_permissions,
    get_toolguard_permissions,
)


def parse_args() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Migrate permissions from settings.local.json to toolguard config",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes without making them
  uv run python -m toolguard.scripts.migrate_permissions --dry-run

  # Migrate with default settings
  uv run python -m toolguard.scripts.migrate_permissions

  # Migrate without auto-sorting
  uv run python -m toolguard.scripts.migrate_permissions --no-sort

  # Use custom backup directory
  uv run python -m toolguard.scripts.migrate_permissions --backup-dir /tmp/backups
        """,
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Preview changes without modifying files"
    )

    parser.add_argument(
        "--no-sort",
        action="store_true",
        help="Do not sort patterns after migration (default: auto-sort)",
    )

    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Directory for backup files (default: logs/config-backups/)",
    )

    return parser.parse_args()


def create_backup(file_path: Path, backup_dir: Path) -> Path:
    """
    Create timestamped backup of a file.

    Backup filename format: basename.YYYY-MM-DD-HHMMSS.extension
    Example: settings.local.2026-02-05-143022.json

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
        backup_name = f"{stem}.{timestamp}{suffix}"
    else:
        # No extension: name -> name.TIMESTAMP
        backup_name = f"{file_path.name}.{timestamp}"

    backup_path = backup_dir / backup_name

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


def get_tool_priority(pattern: str) -> Tuple[int, str]:
    """
    Get sorting priority for a pattern.

    Tool priority: Bash (0), Read (1), Write (2), Edit (3), others (4).
    Secondary sort: case-insensitive alphabetical by full pattern.

    Args:
        pattern: Permission pattern string

    Returns:
        Tuple of (priority, lowercase_pattern) for sorting
    """
    tool_priorities = {"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}

    # Extract tool name
    tool_name = pattern.split("(")[0] if "(" in pattern else pattern
    priority = tool_priorities.get(tool_name, 4)

    return (priority, pattern.lower())


def sort_patterns(patterns: List[str]) -> List[str]:
    """
    Sort patterns by tool priority and alphabetically.

    Sorting order:
    1. Bash patterns first
    2. Read patterns
    3. Write patterns
    4. Edit patterns
    5. Other tools alphabetically
    6. Within each tool: case-insensitive alphabetical

    Args:
        patterns: List of permission patterns

    Returns:
        Sorted list of patterns
    """
    return sorted(patterns, key=get_tool_priority)


def find_section_boundaries(text: str, section_name: str) -> Tuple[int, int]:
    """
    Find start and end positions of a TOML section in text.

    Args:
        text: Full TOML file content
        section_name: Section name (e.g., 'permissions')

    Returns:
        Tuple of (start_pos, end_pos) where:
        - start_pos: Position of the '[section_name]' line
        - end_pos: Position of next section header or EOF
        Returns (-1, -1) if section not found
    """
    section_header = f"[{section_name}]"
    start_pos = text.find(section_header)

    if start_pos == -1:
        return (-1, -1)

    # Find the end of this section (next section header or EOF)
    # Look for next line starting with '['
    end_pos = len(text)
    search_from = start_pos + len(section_header)

    for i in range(search_from, len(text)):
        if text[i] == "\n":
            # Check if next line starts with '['
            if i + 1 < len(text) and text[i + 1] == "[":
                end_pos = i + 1  # End just before next section
                break

    return (start_pos, end_pos)


def parse_permissions_section_with_comments(section_text: str) -> Dict:
    """
    Parse [permissions] section preserving comments and their associations.

    Returns a structure that maps each permission type to a list of items,
    where each item can be a comment block, rule line, or subsection header.

    Args:
        section_text: Text of the [permissions] section

    Returns:
        Dict with structure:
        {
            'allow': [(type, content, parsed_value), ...],
            'deny': [(type, content, parsed_value), ...],
            'ask': [(type, content, parsed_value), ...]
        }
        where type is 'comment_block', 'rule', or 'header'
    """
    import re

    result = {"allow": [], "deny": [], "ask": []}
    lines = section_text.split("\n")

    current_subsection = None
    comment_buffer = []

    for line in lines:
        stripped = line.strip()

        # Skip [permissions] header itself
        if stripped == "[permissions]":
            continue

        # Detect subsection headers like [permissions.allow]
        subsection_match = re.match(r"\[permissions\.(allow|deny|ask)\]", stripped)
        if subsection_match:
            current_subsection = subsection_match.group(1)
            # Flush any pending comments as top-of-section
            if comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # Detect simple subsection assignments like "allow = ["
        assign_match = re.match(r"(allow|deny|ask)\s*=\s*\[", stripped)
        if assign_match:
            current_subsection = assign_match.group(1)
            # Flush any pending comments as top-of-section
            if comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # Check if this is a comment line
        if stripped.startswith("#"):
            comment_buffer.append(line)
            continue

        # Keep blank lines in comment buffer (they're part of comment blocks)
        if stripped == "":
            if current_subsection and comment_buffer:
                comment_buffer.append(line)
            continue

        # Handle closing bracket - flush any pending comments as bottom-of-section
        if stripped == "]":
            if current_subsection and comment_buffer:
                result[current_subsection].append(
                    ("comment_block", "\n".join(comment_buffer), None)
                )
                comment_buffer = []
            continue

        # This is a rule line (contains a quoted pattern)
        if current_subsection and '"' in stripped:
            # Extract the pattern value
            pattern_match = re.search(r'"([^"]*)"', stripped)
            if pattern_match:
                pattern_value = pattern_match.group(1)
                # Unescape the pattern
                pattern_value = pattern_value.replace('\\"', '"').replace("\\\\", "\\")

                # Attach any pending comments to this rule
                if comment_buffer:
                    result[current_subsection].append(
                        ("comment_block", "\n".join(comment_buffer), None)
                    )
                    comment_buffer = []

                # Add the rule with its original line text (preserves inline comments)
                result[current_subsection].append(("rule", line, pattern_value))
                continue

    # Flush any remaining comments as bottom-of-section
    if current_subsection and comment_buffer:
        result[current_subsection].append(
            ("comment_block", "\n".join(comment_buffer), None)
        )

    return result


def reassemble_permissions_section(
    parsed_structure: Dict,
    new_permissions: Dict[str, List[str]],
    auto_sort: bool = True,
) -> str:
    """
    Reassemble [permissions] section with comments preserved and rules sorted.

    Args:
        parsed_structure: Structure from parse_permissions_section_with_comments
        new_permissions: New permission values to use
        auto_sort: Whether to sort the rules

    Returns:
        Complete [permissions] section text with comments preserved
    """
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        patterns = new_permissions.get(perm_type, [])
        if not patterns:
            continue

        # Get the parsed items for this subsection
        parsed_items = parsed_structure.get(perm_type, [])

        # Extract comments and their associations
        top_comments = []
        bottom_comments = []
        rule_comments = {}  # Maps pattern value to its preceding comment block
        rule_lines = {}  # Maps pattern value to its original line text (with inline comments)

        current_comment_block = None
        seen_first_rule = False

        for item_type, content, value in parsed_items:
            if item_type == "comment_block":
                if not seen_first_rule:
                    # Comments before first rule go to top
                    top_comments.append(content)
                else:
                    # Comments after a rule might belong to next rule or bottom
                    current_comment_block = content
            elif item_type == "rule":
                seen_first_rule = True
                # Save original line text (preserves inline comments)
                rule_lines[value] = content
                if current_comment_block:
                    # Associate this comment with this rule
                    rule_comments[value] = current_comment_block
                    current_comment_block = None

        # Any remaining comment block goes to bottom
        if current_comment_block:
            bottom_comments.append(current_comment_block)

        # Sort patterns if requested
        sorted_patterns = sort_patterns(patterns) if auto_sort else patterns

        # Reassemble the subsection
        lines.append(f"{perm_type} = [")

        # Add top comments
        for comment_block in top_comments:
            lines.append(comment_block)

        # Add rules with their comments
        for pattern in sorted_patterns:
            # Add comment block if this pattern had one
            if pattern in rule_comments:
                lines.append(rule_comments[pattern])

            # Use original line if available (preserves inline comments), otherwise generate new
            if pattern in rule_lines:
                lines.append(rule_lines[pattern])
            else:
                # New pattern - generate line
                escaped = pattern.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'  "{escaped}",')

        # Add bottom comments
        for comment_block in bottom_comments:
            lines.append(comment_block)

        lines.append("]")
        lines.append("")

    return "\n".join(lines)


def generate_permissions_section(
    permissions: Dict[str, List[str]], auto_sort: bool = True
) -> str:
    """
    Generate the [permissions] section content.

    Args:
        permissions: Dictionary with 'allow', 'deny', 'ask' keys
        auto_sort: Whether to sort patterns before writing

    Returns:
        String containing the complete [permissions] section
    """
    # Sort if requested
    if auto_sort:
        permissions = {
            key: sort_patterns(patterns) for key, patterns in permissions.items()
        }

    # Generate TOML content
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        patterns = permissions.get(perm_type, [])
        if patterns:
            lines.append(f"{perm_type} = [")
            for pattern in patterns:
                # Escape quotes in pattern
                escaped = pattern.replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'  "{escaped}",')
            lines.append("]")
            lines.append("")

    return "\n".join(lines)


def write_toml_config(
    config_path: Path,
    permissions: Dict[str, List[str]],
    auto_sort: bool = True,
) -> None:
    """
    Write permissions to TOML configuration file.

    Preserves all other sections, top-level keys, and comments in the file.
    Only replaces the [permissions] section content while maintaining comments.

    Args:
        config_path: Path to TOML file to write
        permissions: Dictionary with 'allow', 'deny', 'ask' keys
        auto_sort: Whether to sort patterns before writing

    Raises:
        OSError: If file cannot be written
    """
    # Check if file exists
    if not config_path.exists():
        # Create new file with just permissions section (no comments to preserve)
        new_permissions_section = generate_permissions_section(permissions, auto_sort)
        config_path.write_text(new_permissions_section + "\n")
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

    config_path.write_text(new_content)


def write_json_config(
    config_path: Path,
    permissions: Dict[str, List[str]],
    auto_sort: bool = True,
) -> None:
    """
    Write permissions to JSON configuration file.

    Args:
        config_path: Path to JSON file to write
        permissions: Dictionary with 'allow', 'deny', 'ask' keys
        auto_sort: Whether to sort patterns before writing

    Raises:
        OSError: If file cannot be written
    """
    # Sort if requested
    if auto_sort:
        permissions = {
            key: sort_patterns(patterns) for key, patterns in permissions.items()
        }

    # Read existing config if it exists
    config = {}
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except json.JSONDecodeError, OSError:
            pass

    # Update permissions
    config["permissions"] = permissions

    # Write config
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def update_settings_file(
    settings_path: Path,
    migrated_patterns: Dict[str, List[str]],
    redundant_patterns: Dict[str, List[str]] = None,
) -> None:
    """
    Remove migrated and redundant patterns from settings.local.json.

    Leaves permissions structure with empty lists for unmigrated patterns.

    Args:
        settings_path: Path to settings.local.json
        migrated_patterns: Dict of patterns that were migrated (to remove)
        redundant_patterns: Dict of patterns that are redundant (to remove)

    Raises:
        OSError: If file cannot be read or written
        json.JSONDecodeError: If file contains invalid JSON
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

    # Write updated config
    with open(settings_path, "w") as f:
        json.dump(config, f, indent=2)
        f.write("\n")


def migrate(
    project_root: Path,
    dry_run: bool = False,
    auto_sort: bool = True,
    backup_dir: Path = None,
) -> int:
    """
    Perform the migration of permissions from settings.local.json to toolguard config.

    Args:
        project_root: Path to project root directory
        dry_run: If True, preview changes without modifying files
        auto_sort: If True, sort patterns after migration
        backup_dir: Directory for backup files (default: project_root/logs/config-backups)

    Returns:
        Exit code (0 for success, 1 for error)
    """
    # Set default backup directory
    if backup_dir is None:
        backup_dir = project_root / "logs" / "config-backups"

    # Load settings.local.json permissions
    settings_path = project_root / ".claude" / "settings.local.json"
    if not settings_path.exists():
        print(f"No settings.local.json found at {settings_path}")
        print("Nothing to migrate.")
        return 0

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

    # Find divergent patterns (patterns in native but not in toolguard)
    divergent = find_divergent_patterns(native_perms, toolguard_perms, ignored_patterns)

    # Find redundant patterns (exact duplicates or subsets)
    redundant = find_redundant_patterns(native_perms, toolguard_perms)

    # Check if there's anything to migrate or clean up
    total_divergent = sum(len(patterns) for patterns in divergent.values())
    total_redundant = sum(len(patterns) for patterns in redundant.values())

    if total_divergent == 0 and total_redundant == 0:
        print("No new patterns found to migrate.")
        print("All patterns in settings.local.json are already in toolguard config.")
        return 0

    # Report what will be migrated
    if total_divergent > 0:
        print(f"Found {total_divergent} pattern(s) to migrate:")
        print()
        for perm_type in ["allow", "deny", "ask"]:
            patterns = divergent[perm_type]
            if patterns:
                print(f"  {perm_type.upper()}:")
                for pattern in patterns:
                    # Check if covered by a superset
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

    # Report redundant patterns
    if total_redundant > 0:
        print(
            f"Found {total_redundant} redundant pattern(s) to remove (already in toolguard config):"
        )
        print()
        for perm_type in ["allow", "deny", "ask"]:
            patterns = redundant[perm_type]
            if patterns:
                print(f"  {perm_type.upper()}:")
                for pattern in patterns:
                    print(f"    - {pattern}")
                print()

    # Find target config file (prefer TOML, create if none exists)
    target_config_path = None
    target_format = None

    # Check for existing toolguard config files
    for file_path, source_type, file_format in config_files:
        if source_type == "toolguard_hook":
            target_config_path = file_path
            target_format = file_format
            break

    # If no toolguard config exists, create .claude/toolguard_hook.toml
    if target_config_path is None:
        target_config_path = project_root / ".claude" / "toolguard_hook.toml"
        target_format = "toml"
        print(f"No toolguard config found. Will create: {target_config_path}")
    else:
        print(f"Will add patterns to: {target_config_path}")

    # Check for similar patterns (only for patterns being migrated)
    if total_divergent > 0:
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

    if dry_run:
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
        return 0

    # Perform migration
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

        # Load existing toolguard config permissions (full structure)
        merged_perms = {"allow": [], "deny": [], "ask": []}
        if target_config_path.exists():
            existing_config = load_config_file(target_config_path, target_format)

            existing_perms = existing_config.get("permissions", {})
            for perm_type in ["allow", "deny", "ask"]:
                merged_perms[perm_type] = existing_perms.get(perm_type, [])

        # Add divergent patterns (if any)
        if total_divergent > 0:
            for perm_type in ["allow", "deny", "ask"]:
                for pattern in divergent[perm_type]:
                    if pattern not in merged_perms[perm_type]:
                        merged_perms[perm_type].append(pattern)

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


def main() -> int:
    """
    Main entry point for the migration script.

    Returns:
        Exit code (0 for success, 1 for error)
    """
    args = parse_args()

    try:
        project_root = find_project_root()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1

    return migrate(
        project_root=project_root,
        dry_run=args.dry_run,
        auto_sort=not args.no_sort,
        backup_dir=args.backup_dir,
    )


if __name__ == "__main__":
    sys.exit(main())
