"""
Boundary scanning of raw TOML text: ``[permissions]`` section spans and
array-element spans.

Quote- and brace-aware text scanning, nothing more -- it locates spans, never
parses a value or validates TOML, and it does not raise on malformed input.

Deliberately imports nothing from toolguard, so a hot-path caller can take one
function from here without pulling in the rule machinery.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# TOML section boundary location
# ---------------------------------------------------------------------------

#: A TOML section header occupying a WHOLE line -- ``[name]`` with only
#: horizontal whitespace and an optional trailing ``#`` comment around it.
#: Used to find where the NEXT section begins.
#:
#: Line-anchored rather than a bare ``"\n["`` scan, so a bracket in the middle
#: of a value line is not taken for a header. It remains a heuristic, not a
#: TOML tokenizer: a nested array alone on its own line with no trailing comma
#: (``["Bash", "Read"]``) does match, and would be read as a section header.
_ANY_SECTION_HEADER_RE = re.compile(r"(?m)^[ \t]*\[[^\]]+\][ \t]*(?:#.*)?$")


def _section_header_re(section_name: str) -> re.Pattern:
    """
    Compile a whole-line matcher for one section's header -- the line shape
    :data:`_ANY_SECTION_HEADER_RE` describes, narrowed to *section_name*.

    Args:
        section_name: Section name without brackets, e.g. ``'permissions'``.

    Returns:
        Compiled pattern matching a header line for this section.
    """
    return re.compile(rf"(?m)^[ \t]*\[{re.escape(section_name)}\][ \t]*(?:#.*)?$")


def find_section_boundaries(text: str, section_name: str) -> Tuple[int, int]:
    """
    Find the character span of a TOML section in *text*.

    Args:
        text: Full TOML file content.
        section_name: Section name without brackets (e.g. ``'permissions'``).

    Returns:
        ``(start_pos, end_pos)`` -- the index of the ``[section_name]`` header
        line, and the index of the next section header line or ``len(text)``
        when no further header follows. ``(-1, -1)`` when the section is not
        found.
    """
    match = _section_header_re(section_name).search(text)
    if match is None:
        return (-1, -1)

    start_pos = match.start()
    next_header = _ANY_SECTION_HEADER_RE.search(text, match.end())
    end_pos = next_header.start() if next_header is not None else len(text)

    return (start_pos, end_pos)


def _find_array_close(text: str, open_pos: int) -> int:
    """
    Find the ``]`` closing the array whose ``[`` is at *open_pos*.

    Quote-, comment- and depth-aware, so a ``]`` inside a string or comment,
    or the close of a nested ``[``/``{`` value, never ends the array early.

    Args:
        text: The text to scan, typically an entire ``[permissions]`` section.
        open_pos: Index of the ``[`` whose match is sought.

    Returns:
        Index of the matching ``]``, or ``len(text)`` when there is none --
        malformed input is not an error here.
    """
    depth = 1
    in_dquote = False
    in_squote = False
    in_comment = False
    escape_next = False
    i = open_pos + 1
    n = len(text)

    while i < n:
        ch = text[i]

        if ch == "\n":
            in_comment = False
            escape_next = False
            i += 1
            continue

        if in_comment:
            i += 1
            continue

        if in_dquote:
            if escape_next:
                escape_next = False
            elif ch == "\\":
                escape_next = True
            elif ch == '"':
                in_dquote = False
            i += 1
            continue

        if in_squote:
            if ch == "'":
                in_squote = False
            i += 1
            continue

        if ch == "#":
            in_comment = True
        elif ch == '"':
            in_dquote = True
        elif ch == "'":
            in_squote = True
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
            if depth == 0:
                return i

        i += 1

    return n


def _locate_subsection(
    section_text: str, perm_type: str
) -> Optional[Tuple[int, int, int]]:
    """
    Locate a ``<perm_type> = [`` assignment within a section.

    Args:
        section_text: The full ``[permissions]`` section text.
        perm_type: ``'allow'``, ``'deny'``, or ``'ask'``.

    Returns:
        ``(match_start, open_pos, close_pos)`` -- where the assignment's own
        line begins, the index of its ``[``, and the index of the matching
        ``]`` -- or ``None`` when the subsection is absent.
    """
    match = re.search(rf"(?m)^[ \t]*{perm_type}\s*=\s*\[", section_text)
    if not match:
        return None
    open_pos = match.end() - 1
    close_pos = _find_array_close(section_text, open_pos)
    return match.start(), open_pos, close_pos


# ---------------------------------------------------------------------------
# Top-level array-element boundary scanning
# ---------------------------------------------------------------------------
#
# Splitting is purely structural -- quote state and brace depth, nothing about
# what a pattern string looks like. Deliberately no tool-name enumeration
# ("Bash(", "Read(", ...): additional_supported_tools lets users govern
# arbitrary tools, so any such list would be wrong the moment one is added.
#
# An element may span several lines (start_line != end_line). That span is a
# DETECTION affordance, not support for the shape: a multi-line structured
# entry is invalid TOML, and the span is what lets
# find_multiline_structured_entry_line name the offending entry.


@dataclass(frozen=True)
class ArrayElement:
    """
    One top-level element of a TOML array, as located by :func:`split_array_elements`.

    An "element" is the array VALUE alone -- a quoted string
    (``"Bash(ls *)"``) or an inline/multi-line table
    (``{ match = "...", ... }``). Surrounding comments and whitespace are kept
    separately in ``leading`` and ``trailing``, so a caller can rewrite a
    value without disturbing them.

    All offsets and line numbers are relative to the text passed to
    :func:`split_array_elements` -- the array interior, not the file.

    Reconstruction guarantee: ``leading + text + trailing ==
    original_text[segment_start:segment_end]`` for each element; concatenating
    those in order and appending ``original_text[elements[-1].segment_end:]``
    reproduces ``original_text`` byte-for-byte.
    """

    #: The element's own value text, e.g. ``'"Bash(ls *)"'`` or
    #: ``'{ match = "Bash(x)" }'`` (possibly spanning multiple lines).
    text: str

    #: Raw text between the previous top-level comma (or the start of the
    #: scanned input) and ``text``: blank lines, full-line ``#`` comments,
    #: indentation -- and any inline comment that followed that comma.
    leading: str

    #: Raw text from the end of ``text`` up to and including the delimiting
    #: comma, or to wherever scanning stopped for the last element. An inline
    #: ``#`` comment written AFTER the comma -- the usual placement -- lands
    #: in the NEXT element's ``leading``, not here.
    trailing: str

    #: Offset of ``text``'s first character in the original input.
    start_pos: int

    #: Offset one past ``text``'s last character --
    #: ``original_text[start_pos:end_pos] == text``.
    end_pos: int

    #: 1-based line number of ``text``'s first character.
    start_line: int

    #: 1-based line number of ``text``'s last character. Greater than
    #: ``start_line`` for a multi-line element.
    end_line: int

    #: Offset where this element's whole segment (``leading + text +
    #: trailing``) begins.
    segment_start: int

    #: Offset one past this element's whole segment -- also the next element's
    #: ``segment_start``, for every element but the last.
    segment_end: int


def _build_array_element(
    text: str,
    segment_start: int,
    value_start: int,
    value_start_line: int,
    value_end: int,
    value_end_line: int,
    segment_end: int,
) -> ArrayElement:
    """Assemble one :class:`ArrayElement` from offsets collected by the scan."""
    return ArrayElement(
        text=text[value_start:value_end],
        leading=text[segment_start:value_start],
        trailing=text[value_end:segment_end],
        start_pos=value_start,
        end_pos=value_end,
        start_line=value_start_line,
        end_line=value_end_line,
        segment_start=segment_start,
        segment_end=segment_end,
    )


@dataclass
class _ArrayScanState:
    """Mutable state threaded through :func:`split_array_elements`'s scan."""

    #: Finalized elements found so far, in source order.
    elements: List[ArrayElement] = field(default_factory=list)
    #: Offset where the CURRENT (still-open) segment began.
    segment_start: int = 0
    #: Offset/line where the current segment's value began, once found.
    value_start: Optional[int] = None
    value_start_line: Optional[int] = None
    #: Offset (exclusive)/line where the current segment's value ended.
    value_end: Optional[int] = None
    value_end_line: Optional[int] = None
    #: Whether the scan is currently inside a ``"..."`` / ``'...'`` string.
    in_dquote: bool = False
    in_squote: bool = False
    #: Whether the scan is currently inside a ``#`` line comment.
    in_comment: bool = False
    #: Whether the previous character inside a double-quoted string was an
    #: unconsumed ``\\`` (so the current character is escaped, not structural).
    escape_next: bool = False
    #: Current ``{...}`` nesting depth. ``[``/``]`` are not tracked, so a
    #: comma inside a bare nested array does split.
    brace_depth: int = 0
    #: Current 1-based line number.
    line: int = 1


def _scan_array_char(text: str, i: int, ch: str, state: _ArrayScanState) -> None:
    """
    Advance *state* by exactly one character of :func:`split_array_elements`'s scan.

    Args:
        text: The input being scanned, needed only to build the finalized
            :class:`ArrayElement` on a top-level comma.
        i: ``ch``'s offset within *text*.
        ch: The character itself (``text[i]``).
        state: Scan state, mutated in place.
    """
    if ch == "\n":
        state.line += 1
        state.in_comment = False
        state.escape_next = False
        return

    if state.in_comment:
        return

    if state.in_dquote:
        if state.escape_next:
            state.escape_next = False
        elif ch == "\\":
            state.escape_next = True
        elif ch == '"':
            state.in_dquote = False
            if state.brace_depth == 0:
                state.value_end, state.value_end_line = i + 1, state.line
        return

    if state.in_squote:
        # No escape handling: a TOML literal string ends at the first "'",
        # and a "\" inside one is just a backslash.
        if ch == "'":
            state.in_squote = False
            if state.brace_depth == 0:
                state.value_end, state.value_end_line = i + 1, state.line
        return

    if ch == "#":
        state.in_comment = True
        return

    if ch == '"':
        state.in_dquote = True
        if state.value_start is None:
            state.value_start, state.value_start_line = i, state.line
        return

    if ch == "'":
        state.in_squote = True
        if state.value_start is None:
            state.value_start, state.value_start_line = i, state.line
        return

    if ch == "{":
        if state.brace_depth == 0 and state.value_start is None:
            state.value_start, state.value_start_line = i, state.line
        state.brace_depth += 1
        return

    if ch == "}":
        if state.brace_depth > 0:
            state.brace_depth -= 1
            if state.brace_depth == 0:
                state.value_end, state.value_end_line = i + 1, state.line
        return

    if ch == "," and state.brace_depth == 0:
        if state.value_start is not None and state.value_end is not None:
            state.elements.append(
                _build_array_element(
                    text,
                    state.segment_start,
                    state.value_start,
                    state.value_start_line,
                    state.value_end,
                    state.value_end_line,
                    i + 1,
                )
            )
            state.segment_start = i + 1
            state.value_start = state.value_end = None
            state.value_start_line = state.value_end_line = None
        # A stray comma with no value yet in this segment (malformed input) is
        # absorbed into the still-open segment rather than emitting a broken
        # element.
        return


def split_array_elements(text: str) -> Tuple[ArrayElement, ...]:
    """
    Locate top-level array-element boundaries in *text* via a single linear pass.

    *text* is the raw content BETWEEN a TOML array's ``[`` and ``]``; the
    caller slices that out. The scan tracks quote state (``"..."`` basic
    strings, with backslash escapes; ``'...'`` literal strings, without) and
    ``{...}`` depth, and splits only on a comma at depth 0 outside any quote
    or comment. A ``#`` outside a quote starts a line comment running to the
    next newline; commas, braces and ``#`` inside a quoted string are never
    structural.

    One value per segment: the first ``"``, ``'`` or top-level ``{`` starts
    ``text``; the last quote/brace close at depth 0 in the segment ends it,
    however many lines away. Everything before ``text`` in the segment is
    ``leading``, everything after it up to and including the delimiting comma
    is ``trailing``.

    A segment with no value at all produces no element -- which covers an
    empty array (returns ``()``) and a comment-only remainder after the last
    element's comma. A caller that wants that remainder reads
    ``text[elements[-1].segment_end:]``.

    Never raises on malformed input -- this locates boundaries, it does not
    validate TOML.

    Known limitation: there is no triple-quote (``\"\"\"``/``'''``) state, so a
    TOML multi-line string is out of contract and may be mis-split.

    Args:
        text: Raw text between a TOML array's ``[`` and ``]``, exclusive of
            the brackets themselves.

    Returns:
        A tuple of :class:`ArrayElement` in source order, one per top-level
        element. Empty when *text* contains no value at all.
    """
    state = _ArrayScanState()

    for i, ch in enumerate(text):
        _scan_array_char(text, i, ch, state)

    if state.value_start is not None and state.value_end is not None:
        state.elements.append(
            _build_array_element(
                text,
                state.segment_start,
                state.value_start,
                state.value_start_line,
                state.value_end,
                state.value_end_line,
                len(text),
            )
        )

    return tuple(state.elements)


# ---------------------------------------------------------------------------
# Multi-line structured entry diagnostic
# ---------------------------------------------------------------------------


def find_multiline_structured_entry_line(text: str) -> Optional[int]:
    """
    Report a line carrying a multi-line structured permission entry, if any.

    A structured entry (``{ match = "...", ... }``) spread across several
    physical lines is not valid TOML 1.0, and it is this project's
    highest-impact config mistake: the whole file then fails to parse, so none
    of its rules load. ``tomllib``'s own message for it is a generic
    key-syntax complaint that does not identify the mistake.

    Not a second TOML parser, and no validation of its own: it locates the
    ``allow``/``deny``/``ask`` arrays inside *text*'s ``[permissions]``
    section and hands each interior to :func:`split_array_elements`, whose
    tolerance of malformed input is what makes it usable here -- on text
    ``tomllib`` has already rejected.

    Deliberately narrow. It reports a line only for the one unambiguous shape
    (an element starting with ``{`` that begins and ends on different lines).
    Any other TOML error -- a typo, a missing quote, a wrong-shaped table --
    yields ``None``, so a caller falls back to the generic message rather
    than misattributing the failure.

    Args:
        text: Full raw text of a TOML config file. Need not be valid TOML.

    Returns:
        1-based line number of an offending entry's opening ``{``, else
        ``None`` -- including when *text* has no ``[permissions]`` section.
        The arrays are searched ``allow``, ``deny``, ``ask``, so with more
        than one offender this is not necessarily the earliest line.
    """
    section_start, section_end = find_section_boundaries(text, "permissions")
    if section_start == -1:
        return None
    section_text = text[section_start:section_end]

    for perm_type in ("allow", "deny", "ask"):
        location = _locate_subsection(section_text, perm_type)
        if location is None:
            continue
        _, open_pos, close_pos = location
        body = section_text[open_pos + 1 : close_pos]
        for element in split_array_elements(body):
            if element.text.startswith("{") and element.start_line != element.end_line:
                absolute_pos = section_start + open_pos + 1 + element.start_pos
                return text.count("\n", 0, absolute_pos) + 1

    return None
