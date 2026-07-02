"""
Generated ``# toolguard:`` comments that explain confusing rule interactions.

The clarity analyzer (:mod:`toolguard.tools.clarity`) detects "correct but
confusing" allow/guard overlaps.  This module turns those findings into short
leading comments written above the affected rules, so the real resolution is
legible in the config file itself.

Design guarantees:

- **Stable marker.**  Every generated line begins with ``# toolguard:`` so a
  re-run REPLACES the previous generation instead of accreting duplicates, and so
  a rule that is no longer confusing has its stale generated comment removed.
- **Never clobbers human comments.**  Only ``# toolguard:``-marked lines are ever
  removed; any other comment line is preserved verbatim.
- **Minimal diff.**  The writer is line-based: rule order, empty sections, blank
  lines, inline comments and formatting are left byte-for-byte unchanged except
  for the generated comment lines themselves.

This module only computes and writes comments; it never changes a rule.
"""

from pathlib import Path
from typing import Dict, List, Tuple

from toolguard.config import Configuration
from toolguard.rule_sort import (
    find_section_boundaries,
    parse_permissions_section_with_comments,
)
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions

TOOLGUARD_MARKER = "# toolguard:"


def _annotation_text(finding: InteractionFinding) -> str:
    """
    Build the concise one-line note for a single clarity finding.

    Kept short (the full explanation lives in the audit/maintenance report); the
    comment is a legibility nudge in the file, not the whole analysis.
    """
    if finding.kind == "deny-shadows-allow":
        return f"deny '{finding.guard_pattern}' shadows part of this allow (deny wins)"
    if finding.kind == "ask-overlaps-allow":
        return (
            f"ask '{finding.guard_pattern}' overlaps this allow "
            "(more-specific rule wins)"
        )
    if finding.kind == "multi-section-interaction":
        return (
            f"also governed by {finding.guard_section} '{finding.guard_pattern}'; "
            "effective verdict is non-obvious"
        )
    if finding.kind == "cross-layer-dependent":
        return (
            f"interacts with {finding.guard_section} '{finding.guard_pattern}' in "
            "another layer; verdict spans files"
        )
    return finding.explanation


def clarity_annotations(
    config: Configuration, tool: str
) -> Dict[Path, Dict[str, List[str]]]:
    """
    Map each config FILE to the generated comments its confusing allow rules need.

    Grouped by the allow rule's own source file (its provenance), so a rule is only
    annotated in the file where it is actually confusing -- an identical pattern in
    another layer is left alone.  Only ``toml`` layers are annotated (native ``json``
    settings carry no comments).

    Args:
        config: The resolved configuration to analyze.
        tool: Tool whose rules to annotate (e.g. ``'Bash'``).

    Returns:
        ``{ path -> { full_pattern -> [note, ...] } }`` where *full_pattern* is the
        FULL ``Tool(body)`` form as it appears in the file, and notes are
        de-duplicated and sorted for a stable diff.
    """
    by_file: Dict[Path, Dict[str, List[str]]] = {}
    for finding in find_confusing_interactions(config, tool):
        if finding.provenance.file_format != "toml":
            continue
        path = Path(finding.provenance.path)
        full_pattern = f"{finding.tool}({finding.allow_pattern})"
        notes = by_file.setdefault(path, {}).setdefault(full_pattern, [])
        note = _annotation_text(finding)
        if note not in notes:
            notes.append(note)
    return {
        path: {pattern: sorted(notes) for pattern, notes in patterns.items()}
        for path, patterns in by_file.items()
    }


def _rule_line_patterns(section_text: str) -> Dict[str, str]:
    """Map each rule's original line text to its full pattern, via the comment parser."""
    parsed = parse_permissions_section_with_comments(section_text)
    line_to_pattern: Dict[str, str] = {}
    for perm_type in ("allow", "deny", "ask"):
        for item_type, content, value in parsed.get(perm_type, []):
            if item_type == "rule":
                line_to_pattern[content] = value
    return line_to_pattern


def annotate_section_text(section_text: str, annotations: Dict[str, List[str]]) -> str:
    """
    Rewrite a ``[permissions]`` section's text with generated comments applied.

    Idempotent and minimal-diff: every existing ``# toolguard:`` line is dropped,
    then the current annotations are re-inserted immediately above their rule at
    the rule's indentation.  All other lines (rules, human comments, blanks,
    section brackets) are preserved exactly.

    Args:
        section_text: The full ``[permissions]`` section text.
        annotations: ``{ full_pattern -> [note, ...] }`` from :func:`clarity_annotations`.

    Returns:
        The rewritten section text.
    """
    line_to_pattern = _rule_line_patterns(section_text)
    out: List[str] = []
    for line in section_text.split("\n"):
        if line.strip().startswith(TOOLGUARD_MARKER):
            continue  # drop stale generated comments (re-inserted below if still relevant)
        pattern = line_to_pattern.get(line)
        if pattern is not None and pattern in annotations:
            indent = line[: len(line) - len(line.lstrip())]
            for note in annotations[pattern]:
                out.append(f"{indent}{TOOLGUARD_MARKER} {note}")
        out.append(line)
    return "\n".join(out)


def annotate_config_file(
    path: Path, annotations: Dict[str, List[str]]
) -> Tuple[str, str]:
    """
    Compute the annotated text for a config file (does NOT write to disk).

    Reads the file, rewrites only its ``[permissions]`` section, and returns the
    before/after text so the caller can diff, preview, or write it under the same
    safety gate used for other config edits.

    Args:
        path: The config file to annotate.
        annotations: ``{ full_pattern -> [note, ...] }`` from :func:`clarity_annotations`.

    Returns:
        ``(old_text, new_text)``.  ``new_text == old_text`` when the file has no
        ``[permissions]`` section or nothing changed.
    """
    old_text = Path(path).read_text(encoding="utf-8")
    start, end = find_section_boundaries(old_text, "permissions")
    if start == -1:
        return old_text, old_text
    new_section = annotate_section_text(old_text[start:end], annotations)
    new_text = old_text[:start] + new_section + old_text[end:]
    return old_text, new_text
