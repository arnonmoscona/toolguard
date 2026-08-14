"""
Generated ``# toolguard:`` comments that explain confusing rule interactions.

Renders the clarity analyzer's "correct but confusing" allow/guard findings as
leading comments above the allow rules they concern, so the real resolution is
legible in the config file itself.  Nothing here changes a rule or writes to
disk.

The ``# toolguard:`` prefix is the whole mechanism: a re-run drops every line
STARTING with it before re-inserting the current notes, so generations do not
accrete and a rule that no longer has a note comes back with none.  A
hand-written comment using that prefix is dropped too.  Every other line is carried
through unchanged, so rule order, blank lines, inline comments and formatting
survive byte for byte.
"""

from pathlib import Path
from typing import Dict, List, Tuple

from toolguard.config import Configuration
from toolguard.rule_sort import (
    find_section_boundaries,
    parse_permissions_section_with_comments,
    subsection_line_range,
)
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions

TOOLGUARD_MARKER = "# toolguard:"


def _one_line_note(note: str) -> str:
    """
    Collapse any line break in *note* to a single space.

    A note is rendered as one ``# toolguard:`` comment line; an embedded
    break would end the comment mid-array and leave the section unparseable.
    """
    return note.replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _annotation_text(finding: InteractionFinding) -> str:
    """
    One-line note for a clarity finding; an unrecognized *kind* falls back to the
    finding's own (longer) explanation.
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

    Grouped by the provenance of the allow rule each finding names, so a note lands
    in the layer file that finding came from.  Only the finding's allow pattern
    becomes a key; its overlapping guard pattern does not.  Non-``toml`` layers are
    skipped -- native
    ``json`` settings have nowhere to put a comment.

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


def _rule_first_line_patterns(section_text: str) -> Dict[str, str]:
    """
    Map each ALLOW rule's own FIRST physical line of source text to its full pattern.

    ``allow`` only -- :func:`clarity_annotations` documents that a note's key
    is always the finding's allow pattern, never a deny/ask one.  Scanning
    all three lists let an allow note also land above an identically
    spelled deny/ask line, misread as a claim about that rule instead.  A
    rule's ``content`` is one physical line today, so the split is a no-op.
    """
    parsed = parse_permissions_section_with_comments(section_text)
    line_to_pattern: Dict[str, str] = {}
    for item_type, content, value in parsed.get("allow", []):
        if item_type == "rule":
            first_line = content.split("\n", 1)[0]
            line_to_pattern[first_line] = value
    return line_to_pattern


def annotate_section_text(section_text: str, annotations: Dict[str, List[str]]) -> str:
    """
    Rewrite a ``[permissions]`` section's text with generated comments applied.

    Every line STARTING with ``# toolguard:`` is dropped first, then each rule's
    current notes are inserted above it at the rule's own indentation, one line per
    note.  Idempotent; every other line is emitted unchanged.

    Args:
        section_text: The full ``[permissions]`` section text.
        annotations: ``{ full_pattern -> [note, ...] }`` from :func:`clarity_annotations`.

    Returns:
        The rewritten section text.
    """
    line_to_pattern = _rule_first_line_patterns(section_text)
    allow_range = subsection_line_range(section_text, "allow")
    out: List[str] = []
    for index, line in enumerate(section_text.split("\n")):
        if line.strip().startswith(TOOLGUARD_MARKER):
            continue  # re-inserted below if still current
        # allow_range scopes the lookup to the allow array's own lines, so an
        # identically spelled deny/ask line is never mistaken for its match
        # (see _rule_first_line_patterns).
        in_allow = allow_range is not None and allow_range[0] <= index < allow_range[1]
        pattern = line_to_pattern.get(line) if in_allow else None
        if pattern is not None and pattern in annotations:
            indent = line[: len(line) - len(line.lstrip())]
            for note in annotations[pattern]:
                out.append(f"{indent}{TOOLGUARD_MARKER} {_one_line_note(note)}")
        out.append(line)
    return "\n".join(out)


def annotate_config_file(
    path: Path, annotations: Dict[str, List[str]]
) -> Tuple[str, str]:
    """
    Compute the annotated text for a config file (does NOT write to disk).

    Reads the file and rewrites only its ``[permissions]`` section.

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
