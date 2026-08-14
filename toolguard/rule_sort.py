"""
Canonical rule sorting and comment-preserving ``[permissions]`` machinery.

Defines toolguard's canonical permission-rule sort order, plus a
parse/reassemble pair that rewrites a TOML ``[permissions]`` section without
losing the comments attached to its rules.

Sort order: tool priority first -- Bash (0), Read (1), Write (2), Edit (3),
anything else (4) -- then case-insensitive alphabetical on the full pattern
string, so ``Bash(git:*)`` precedes ``Bash(uv run:*)``.

Every function here is pure: no I/O and no global state.

A permission entry is accepted in either of two shapes, a bare pattern ``str``
or a :class:`~toolguard.rule_entry.RuleEntry`; a raw ``dict`` is never
accepted, so a caller holding un-normalized config data normalizes it first
(:func:`~toolguard.rule_entry.normalize_entries_preserving`).
:data:`RuleEntryOrStr` names that union.

Structured entries are single-line, always
------------------------------------------
A structured entry (``{ match = "...", additionalContext = "..." }``) must be
written on exactly one physical line. TOML 1.0 -- the version stdlib
:mod:`tomllib` implements -- forbids an inline table from spanning physical
lines, so a file containing one fails to parse as a whole. This module
therefore treats a multi-line entry as invalid input rather than normalizing
it to one line first: accepting a shape ``tomllib`` rejects would make this
module's tooling round-trip files nothing else in the project can read.
"""

import re
import tomllib
from typing import Dict, List, Optional, Tuple, Union

from toolguard.rule_entry import PATTERN_KEY, RuleEntry
from toolguard.toml_scan import (  # noqa: F401 -- re-exported
    ArrayElement,
    _locate_subsection,
    find_multiline_structured_entry_line,
    find_section_boundaries,
    split_array_elements,
)

#: A permission entry as this module accepts it: a bare pattern string or a
#: normalized :class:`RuleEntry`.
RuleEntryOrStr = Union[str, RuleEntry]


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def get_tool_priority(entry: RuleEntryOrStr) -> Tuple[int, str]:
    """
    Return the canonical sort key for a permission entry.

    Args:
        entry: A wrapped permission pattern such as ``Bash(git:*)`` or
            ``Read(/tmp/*)``, or a :class:`RuleEntry`, whose ``.pattern`` is
            used -- a structured entry's metadata never affects ordering.

    Returns:
        ``(tool_priority, lowercased_pattern)``.
    """
    pattern = entry.pattern if isinstance(entry, RuleEntry) else entry
    tool_priorities = {"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}

    tool_name = pattern.split("(")[0] if "(" in pattern else pattern
    priority = tool_priorities.get(tool_name, 4)

    return (priority, pattern.lower())


def sort_patterns(patterns: List[RuleEntryOrStr]) -> List[RuleEntryOrStr]:
    """
    Return a new list of permission entries in canonical order.

    The input list is not mutated and no element is rebuilt -- each comes back
    as the same object it went in as. The sort is stable, so entries with
    equal keys keep their relative order.

    Args:
        patterns: Permission entries in their full wrapped form (e.g.
            ``['Read(/tmp/*)', 'Bash(git:*)']``), as :class:`RuleEntry`
            objects, or a mix.
    """
    return sorted(patterns, key=get_tool_priority)


def _pattern_of(entry: RuleEntryOrStr) -> str:
    """Return the wrapped pattern string for a permission entry of either shape."""
    return entry.pattern if isinstance(entry, RuleEntry) else entry


# ---------------------------------------------------------------------------
# TOML rendering of a single rule entry
# ---------------------------------------------------------------------------


#: Named single-character TOML basic-string escapes. Every other character
#: needing escaping (a control character outside this table) falls back to
#: a ``\\uXXXX`` escape in :func:`_escape_toml_string`.
_TOML_NAMED_ESCAPES = {
    "\\": "\\\\",
    '"': '\\"',
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\f": "\\f",
    "\r": "\\r",
}


def _escape_toml_string(value: str) -> str:
    """
    Escape a string for a double-quoted TOML basic string.

    Covers the full basic-string escaping surface, not just backslash and
    double quote: a literal control character (newline included) is illegal
    unescaped in a TOML basic string and would otherwise split the rendered
    value across physical lines, corrupting the file.
    """
    return "".join(
        _TOML_NAMED_ESCAPES.get(
            char,
            f"\\u{ord(char):04x}" if ord(char) < 0x20 or ord(char) == 0x7F else char,
        )
        for char in value
    )


def _render_toml_key(key: str) -> str:
    """Render a TOML table key: bare when safe, quoted otherwise."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return f'"{_escape_toml_string(key)}"'


def _render_toml_scalar(value: object) -> str:
    """
    Render one metadata value as TOML source.

    Strings, bools, ints, floats, lists/tuples and dicts get their natural
    TOML form; anything else is stringified and quoted rather than raising.
    That fallback has a consequence worth knowing: TOML has no null, so a
    Python ``None`` (reachable from a JSON config's ``null`` list element)
    renders as the *string* ``"None"``.

    Args:
        value: One metadata value.

    Returns:
        TOML source for ``value``.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return f'"{_escape_toml_string(value)}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(_render_toml_scalar(v) for v in value) + "]"
    if isinstance(value, dict):
        return _render_toml_inline_table(value)
    return f'"{_escape_toml_string(str(value))}"'


def _render_toml_inline_table(table: Dict[str, object]) -> str:
    """
    Render a dict as a TOML inline table.

    ``{"match": "Bash(*)", "additionalContext": "x"}`` renders as
    ``{ match = "Bash(*)", additionalContext = "x" }``. A value containing a
    literal newline is escaped, not split -- the rendered inline table stays
    on one physical line, as the module docstring requires.

    Args:
        table: The dict to render.

    Returns:
        The inline-table source text.
    """
    body = ", ".join(
        f"{_render_toml_key(k)} = {_render_toml_scalar(v)}" for k, v in table.items()
    )
    return "{ " + body + " }"


def render_toml_entry(entry: RuleEntryOrStr) -> str:
    """
    Render one permission entry as the TOML source of a single list item.

    For a caller with no original source line to reuse -- a brand-new entry,
    or a whole section written from scratch. Emits a quoted string for a
    plain pattern and an inline table for a structured entry, WITHOUT the
    caller's list indentation or trailing comma.

    Args:
        entry: A bare pattern ``str``, or a :class:`RuleEntry` rendered from
            its :meth:`~toolguard.rule_entry.RuleEntry.to_source` -- which
            can be any JSON value, not only a string or a table, hence the
            delegation to :func:`_render_toml_scalar`.

    Returns:
        TOML source for one list item (a quoted string, an inline table, or
        another TOML scalar/array -- see :func:`_render_toml_scalar`).
    """
    source = entry.to_source() if isinstance(entry, RuleEntry) else entry
    return _render_toml_scalar(source)


# ---------------------------------------------------------------------------
# TOML [permissions] section parsing and reassembly
# ---------------------------------------------------------------------------


def _toml_value_of_chunk(text: str) -> object:
    """
    Parse one array element's raw TOML source text into its Python value.

    Wraps ``text`` as a single-element array assignment (``x = [ <text> ]``)
    and hands it to stdlib :mod:`tomllib` UNMODIFIED, so ``tomllib`` alone
    decides whether the element's syntax is valid. A multi-line structured
    entry therefore raises here rather than being flattened to one line first
    -- see the module docstring for why flattening it was a mistake.

    Args:
        text: One array element's own source text.

    Returns:
        The parsed value -- typically a ``str`` or a ``dict``, but whatever
        ``tomllib`` yields.

    Raises:
        tomllib.TOMLDecodeError: ``text`` is not valid single-line TOML --
            most notably, a structured entry written across multiple
            physical lines. Deliberately not caught: the caller chooses
            whether to propagate or degrade.
    """
    parsed = tomllib.loads(f"x = [ {text} ]")
    return parsed["x"][0]


def _flush_comment_lines(lines: List[str]) -> Optional[str]:
    """
    Join a run of raw text lines into one comment_block's content, or ``None``.

    A ``#`` line is always kept. A blank line is kept only once the buffer
    already holds a comment, so a run of blanks BEFORE the first comment is
    dropped while one after it is not. Any other line is ignored, so
    malformed input cannot crash the parse.

    Args:
        lines: Candidate raw lines (no trailing ``\\n`` on each), in order.

    Returns:
        The joined comment_block content, or ``None`` if nothing qualified.
    """
    buffer: List[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            buffer.append(line)
        elif stripped == "" and buffer:
            buffer.append(line)
    return "\n".join(buffer) if buffer else None


class SyntheticPattern(str):
    """
    Stand-in pattern for a parsed array element that has no usable pattern --
    e.g. a structured entry missing its ``match`` key.

    Being a plain ``str`` subclass it works as a ``'rule'`` item's
    ``parsed_value`` everywhere a real pattern does;
    :func:`is_synthetic_pattern` is what tells the two apart.
    """


def is_synthetic_pattern(value: object) -> bool:
    """
    Report whether *value* is a :class:`SyntheticPattern` rather than a real
    permission pattern.
    """
    return isinstance(value, SyntheticPattern)


def _rule_pattern_of_value(value: object) -> str:
    """
    Extract the permission-pattern string from one parsed array-element value.

    A plain string value IS its own pattern; a structured (``dict``) value's
    lives under :data:`toolguard.rule_entry.PATTERN_KEY` (``"match"``), so
    either shape yields something usable wherever a bare pattern string is
    expected. Anything else is malformed input -- validating it is
    :func:`~toolguard.rule_entry.normalize_entry`'s job, not this
    comment-preserving parser's -- and yields a :class:`SyntheticPattern`
    over ``repr(value)`` so that parsing never raises here.

    Args:
        value: One element's value, as returned by :func:`_toml_value_of_chunk`.

    Returns:
        The pattern string to key this rule by -- a :class:`SyntheticPattern`
        for malformed input, otherwise a plain ``str``.
    """
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get(PATTERN_KEY), str):
        return value[PATTERN_KEY]
    return SyntheticPattern(repr(value))


def _parse_array_body(
    section_text: str, open_pos: int, close_pos: int
) -> List[Tuple[str, str, Optional[str]]]:
    """
    Parse the interior of one already-located ``allow``/``deny``/``ask`` array.

    Each element's own leading comment lines become a preceding
    ``comment_block`` item; the element itself becomes a ``rule`` item
    carrying its reconstructed original source span (own indentation, value
    text, same-line trailing comma/comment).

    An element's SAME-LINE trailing content -- its delimiting comma and any
    inline ``#`` comment before the next newline -- is folded into its own
    ``rule`` content, which is what keeps ``"Bash(ls:*)",  # note`` attached
    to its own rule rather than becoming a leading comment for whichever rule
    follows. Content on a LATER line belongs to the next element's leading
    comment block, or to a trailing one after the last element.

    Args:
        section_text: The full ``[permissions]`` section text (only the
            ``open_pos``/``close_pos`` slice of it is read).
        open_pos: Index of this array's own ``[``, as returned by
            :func:`_locate_subsection`.
        close_pos: Index of this array's matching ``]``.

    Returns:
        A list of ``(item_type, content, parsed_value)`` tuples in source
        order, exactly as :func:`parse_permissions_section_with_comments`
        documents for one subsection.

    Raises:
        tomllib.TOMLDecodeError: An element is not valid single-line TOML
            (see :func:`_toml_value_of_chunk`). Deliberately not caught here.
    """
    body = section_text[open_pos + 1 : close_pos]
    elements = split_array_elements(body)
    items: List[Tuple[str, str, Optional[str]]] = []

    if not elements:
        # No value at all -- still surface a comment-only body (e.g. a
        # not-yet-populated list holding just an explanatory comment) rather
        # than returning nothing and losing the comment on write-back.
        bottom = _trailing_comment_source_lines(body)
        comment_text = _flush_comment_lines(bottom)
        if comment_text is not None:
            items.append(("comment_block", comment_text, None))
        return items

    # pending_prefix holds raw text (comments, blanks, indentation) not yet
    # assigned to a comment_block or to a rule's own leading whitespace: the
    # first element's leading text, then, after each element, whatever
    # follows it up to the next element's own indentation.
    pending_prefix = elements[0].leading
    last_index = len(elements) - 1
    final_leftover = body[elements[-1].segment_end :]

    for index, element in enumerate(elements):
        if "\n" in pending_prefix:
            comment_source, own_indent = pending_prefix.rsplit("\n", 1)
        else:
            comment_source, own_indent = "", pending_prefix

        comment_text = _flush_comment_lines(comment_source.split("\n"))
        if comment_text is not None:
            items.append(("comment_block", comment_text, None))

        value = _toml_value_of_chunk(element.text)
        pattern = _rule_pattern_of_value(value)

        next_leading = (
            elements[index + 1].leading if index < last_index else final_leftover
        )
        combined = element.trailing + next_leading
        if "\n" in combined:
            same_line_tail, pending_prefix = combined.split("\n", 1)
        else:
            same_line_tail, pending_prefix = combined, ""

        same_line_tail = _ensure_trailing_comma(same_line_tail)

        content = own_indent + element.text + same_line_tail
        items.append(("rule", content, pattern))

    bottom_comment = _flush_comment_lines(
        _trailing_comment_source_lines(pending_prefix)
    )
    if bottom_comment is not None:
        items.append(("comment_block", bottom_comment, None))

    return items


def _ensure_trailing_comma(same_line_tail: str) -> str:
    """
    Ensure the same-line text following an array element's own value carries
    a delimiting comma, inserting one when the ORIGINAL source omitted it.

    TOML permits the array's syntactically LAST element to omit its comma,
    and :func:`_parse_array_body` reuses each element's original source span
    -- so once sorting moves that element out of last position, the reused
    span would produce invalid TOML:
    ``allow = ["Bash(zz)", "Bash(aa)"]`` with no comma after ``"Bash(aa)"``
    becomes ``TOMLDecodeError: Unclosed array`` as soon as ``aa`` sorts
    first. A trailing comma on the real last element is always legal, so
    normalizing every reused span to carry one is unconditionally safe.

    The check ignores anything after a ``#``: an inline comment may itself
    contain a literal comma (e.g. ``# note, cont'd``), which must never be
    mistaken for the element's own delimiter.

    Args:
        same_line_tail: The raw text on the SAME line as an array element's
            own value, up to (but excluding) the next newline -- e.g. ``""``,
            ``" # note"``, or ``",  # note"``.

    Returns:
        *same_line_tail* unchanged if it already contains a real
        (non-comment) comma, otherwise with one inserted at its very start.
    """
    comment_start = same_line_tail.find("#")
    code_part = (
        same_line_tail if comment_start == -1 else same_line_tail[:comment_start]
    )
    if "," in code_part:
        return same_line_tail
    return "," + same_line_tail


def _trailing_comment_source_lines(source: str) -> List[str]:
    """
    Split a comment/blank text span into candidate lines for
    :func:`_flush_comment_lines`, dropping the one spurious empty token a
    trailing ``\\n`` produces.

    That final empty string is the last content line's own terminator, not an
    actual blank LINE in the file. A genuine blank line ends the span with TWO
    newlines and must survive, so exactly one such artifact is dropped, never
    more.
    """
    lines = source.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def subsection_line_range(
    section_text: str, perm_type: str
) -> Optional[Tuple[int, int]]:
    """
    0-indexed, end-exclusive line-number range spanned by one
    ``<perm_type> = [ ... ]`` array's interior, within
    ``section_text.split("\\n")``.

    Lets a caller tell which physical line a given piece of ``section_text``
    belongs to WITHOUT re-parsing it -- e.g. distinguishing an ``allow``
    line from a ``deny`` line that happens to share the exact same text.

    Args:
        section_text: The full ``[permissions]`` section text.
        perm_type: ``'allow'``, ``'deny'``, or ``'ask'``.

    Returns:
        ``(start_line, end_line)``, or ``None`` when the subsection is absent.
    """
    location = _locate_subsection(section_text, perm_type)
    if location is None:
        return None
    _, open_pos, close_pos = location
    start_line = section_text.count("\n", 0, open_pos)
    end_line = section_text.count("\n", 0, close_pos) + 1
    return start_line, end_line


def parse_permissions_section_with_comments(section_text: str) -> Dict:
    """
    Parse a ``[permissions]`` section, preserving comments and their associations.

    Each permission sub-list (allow / deny / ask) is represented as an ordered
    list of typed items, so that comments survive a sort-and-reassemble cycle.

    Item types:

    * ``'comment_block'`` -- one or more consecutive comment/blank lines.
    * ``'rule'``          -- one permission entry, plain or structured. Its
      ``content`` is the entry's own original source span (own indentation
      through its same-line trailing comma/comment), always a SINGLE physical
      line, since this function raises rather than returning a multi-line
      structured entry (see "Raises" below and the module docstring).

    A *comment_block* that immediately precedes a *rule*, INSIDE the
    subsection's own array brackets, belongs to that rule and travels with
    it when rules are re-sorted, including a block preceding the very first
    rule. A block after the last rule -- or one with no rule following it at
    all -- is anchored to the bottom.

    A comment sitting OUTSIDE a subsection's own array brackets -- between the
    ``[permissions]`` header and the first ``allow``/``deny``/``ask =`` line,
    or between one subsection's closing ``]`` and the next subsection's own
    ``=`` line -- describes that subsection as a whole, not any one rule
    inside it. It is kept out of that subsection's item list, in
    ``'leading_comments'``, and reassembly always emits it right after the
    ``<perm_type> = [`` line regardless of how rules are re-sorted.
    Subsections are matched to whichever gap precedes them in the order they
    actually appear in ``section_text``, not in fixed
    ``allow``/``deny``/``ask`` order, so that attribution is right whatever
    order a file uses.

    Args:
        section_text: The full text of the ``[permissions]`` section, including
            its ``[permissions]`` header line.

    Returns:
        ``Dict`` with keys ``'allow'``, ``'deny'``, ``'ask'``, always
        ``'trailing_comment'``, and ``'leading_comments'`` when at least one
        subsection had one. Each of the first three values is a list of
        ``(item_type, content, parsed_value)`` tuples, where *parsed_value*
        is the extracted pattern string for ``'rule'`` items and ``None``
        for ``'comment_block'`` items. ``'leading_comments'``, when present,
        maps a subsection name to the comment text that preceded its own
        array brackets. ``'trailing_comment'`` is the comment text that follows the
        subsections -- e.g. one introducing a following ``[hard_deny]``
        section -- with leading blank lines dropped, or ``None`` when there
        is none. Both are kept out of the three per-subsection lists so
        neither can be mistaken for a rule's own comment or be dropped on
        write-back.

    Raises:
        tomllib.TOMLDecodeError: An array element fails to parse as valid
            TOML -- most notably, a structured entry written across more
            than one physical line. Deliberately NOT caught here: a
            malformed entry must fail loudly rather than vanish silently
            from the parsed structure. A caller wanting a best-effort read
            catches it at its own call site.
    """
    located = []
    for perm_type in ("allow", "deny", "ask"):
        location = _locate_subsection(section_text, perm_type)
        if location is not None:
            match_start, open_pos, close_pos = location
            located.append((match_start, perm_type, open_pos, close_pos))
    located.sort(key=lambda entry: entry[0])

    result = {"allow": [], "deny": [], "ask": []}
    leading_comments: Dict[str, str] = {}
    prev_end = 0
    for match_start, perm_type, open_pos, close_pos in located:
        gap_text = section_text[prev_end:match_start]
        gap_comment = _flush_comment_lines(_trailing_comment_source_lines(gap_text))
        if gap_comment is not None:
            leading_comments[perm_type] = gap_comment

        result[perm_type] = _parse_array_body(section_text, open_pos, close_pos)
        prev_end = close_pos + 1

    if leading_comments:
        result["leading_comments"] = leading_comments

    # Text after the LAST subsection's ']'. Deliberately NOT going through
    # _trailing_comment_source_lines: nothing follows this span to supply the
    # final newline back on reassembly, so dropping that split artifact would
    # eat the trailing text's own last newline. Splitting directly is enough
    # -- _flush_comment_lines already drops the leading blank lines.
    result["trailing_comment"] = _flush_comment_lines(
        section_text[prev_end:].split("\n")
    )

    return result


def reassemble_permissions_section(
    parsed_structure: Dict,
    new_permissions: Dict[str, List[RuleEntryOrStr]],
    auto_sort: bool = True,
) -> str:
    """
    Rebuild a ``[permissions]`` section with comments preserved and rules sorted.

    Uses the parsed structure produced by
    :func:`parse_permissions_section_with_comments` to re-associate comments
    with their rules (comments that preceded a rule travel with it when rules
    are re-ordered by the sort).

    Round-trip guarantee: an entry matched against ``parsed_structure`` is
    re-emitted as that entry's ORIGINAL source text, with only a delimiting
    comma added where the source omitted one (:func:`_ensure_trailing_comma`)
    -- so an untouched rule keeps its own spacing and enrichment, with nothing
    re-rendered. An entry with no original line to reuse -- new, or
    synthesized rather than read from the file -- is rendered fresh instead,
    via :func:`render_toml_entry`.

    Duplicate-pattern keying: a file may legitimately hold several entries
    sharing a pattern but differing in metadata --
    :func:`~toolguard.rule_entry.merge_entries` deliberately preserves such a
    contradiction side by side for a human to resolve. A naive
    ``pattern -> line`` map keeps only one of them and silently destroys the
    other's enrichment on the next write, so original lines and comments are
    keyed by ``(pattern, occurrence_index)`` instead, with ``occurrence_index``
    counted separately on each side: parse order for the file, and
    ``new_permissions``'s own given order -- BEFORE sorting -- for the new
    entries. That assumes same-pattern duplicates appear in the same RELATIVE
    order on both sides. Keying on pattern PLUS metadata is not available
    here: :func:`parse_permissions_section_with_comments` surfaces only a
    rule's bare pattern.

    Args:
        parsed_structure: Structure returned by
            :func:`parse_permissions_section_with_comments`.
        new_permissions: New permission values to use, as a dict with keys
            ``'allow'``, ``'deny'``, ``'ask'``, each a list of pattern
            ``str`` and/or :class:`~toolguard.rule_entry.RuleEntry`. A
            structured entry MUST be a ``RuleEntry``; a bare ``dict`` is
            never accepted.
        auto_sort: When ``True`` (the default), patterns are sorted using
            :func:`sort_patterns` before reassembly.

    Returns:
        Complete ``[permissions]`` section text, including the header line,
        with comments preserved and rules ordered. A sub-list that
        ``new_permissions`` leaves empty or omits is dropped entirely, and so
        are the comments that belonged to it.
    """
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        entries = new_permissions.get(perm_type, [])
        if not entries:
            continue

        parsed_items = parsed_structure.get(perm_type, [])

        # Classify parsed items into bottom comment anchors and per-rule
        # comment associations, keyed by (pattern, occurrence_index) counted
        # in PARSE order -- see "Duplicate-pattern keying" above.
        bottom_comments = []
        rule_comments: Dict[Tuple[str, int], str] = {}
        rule_lines: Dict[Tuple[str, int], str] = {}

        current_comment_block = None
        parsed_occurrence_count: Dict[str, int] = {}

        for item_type, content, value in parsed_items:
            if item_type == "comment_block":
                current_comment_block = content
            elif item_type == "rule":
                occurrence = parsed_occurrence_count.get(value, 0)
                parsed_occurrence_count[value] = occurrence + 1
                key = (value, occurrence)
                rule_lines[key] = content
                if current_comment_block:
                    rule_comments[key] = current_comment_block
                    current_comment_block = None

        # A comment block with no rule after it (including one preceding an
        # otherwise rule-free list) belongs to the bottom.
        if current_comment_block:
            bottom_comments.append(current_comment_block)

        # Key each entry in `entries`'s GIVEN (pre-sort) order, matching the
        # parse-order counting above, THEN sort the pairs -- the key cannot be
        # re-derived after sorting.
        entry_occurrence_count: Dict[str, int] = {}
        keyed_entries: List[Tuple[RuleEntryOrStr, Tuple[str, int]]] = []
        for entry in entries:
            pattern = _pattern_of(entry)
            occurrence = entry_occurrence_count.get(pattern, 0)
            entry_occurrence_count[pattern] = occurrence + 1
            keyed_entries.append((entry, (pattern, occurrence)))

        if auto_sort:
            keyed_entries = sorted(
                keyed_entries, key=lambda pair: get_tool_priority(pair[0])
            )

        lines.append(f"{perm_type} = [")

        leading_comment = parsed_structure.get("leading_comments", {}).get(perm_type)
        if leading_comment:
            lines.append(leading_comment)

        for entry, key in keyed_entries:
            if key in rule_comments:
                lines.append(rule_comments[key])

            # Test `has_raw`, not `raw is None` (see `rule_entry._UNSET`). A
            # synthesized entry was never read from the file, so it has no
            # occurrence to replay.
            is_synthesized = isinstance(entry, RuleEntry) and not entry.has_raw
            if key in rule_lines and not is_synthesized:
                lines.append(rule_lines[key])
            else:
                lines.append(f"  {render_toml_entry(entry)},")

        for comment_block in bottom_comments:
            lines.append(comment_block)

        lines.append("]")
        lines.append("")

    # Text that followed the LAST subsection's ']', e.g. a comment introducing
    # a following [hard_deny] section. Appended after the blank line each
    # emitted sub-list ends with, so a comment that sat directly under the
    # last `]` gains one.
    trailing_comment = parsed_structure.get("trailing_comment")
    if trailing_comment:
        lines.append(trailing_comment)

    return "\n".join(lines)
