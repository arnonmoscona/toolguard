"""
Pure TOML ``[permissions]`` section and array-element boundary scanning.

Leaf module (TOO-19 review fix, ITEM 8): every function here is a
structural, quote/brace-aware text scanner with NO dependency on
:class:`toolguard.rule_entry.RuleEntry` or any other toolguard type -- it
locates section/array/element BOUNDARIES in raw TOML text, nothing more.
Extracted out of :mod:`toolguard.rule_sort` (which re-imports and
re-exports every public name here for backward compatibility, since several
tooling modules and tests already import them from ``toolguard.rule_sort``)
specifically so that :mod:`toolguard.config` -- the hook HOT PATH, loaded on
every single tool-use evaluation -- can import
:func:`find_multiline_structured_entry_line` directly from here instead of
transitively pulling in all of ``rule_sort.py`` (a ~1300-line tooling module
whose own imports include :mod:`toolguard.rule_entry`) just for that one
diagnostic function.

Depends only on the Python standard library (``re``, ``dataclasses``,
``typing``), like :mod:`toolguard.config_write_guard` -- see
``test.unit.test_architecture``'s ``LAYERS`` for the enforced layering.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# TOML section boundary location
# ---------------------------------------------------------------------------

#: Matches any TOML section header as a WHOLE line: optional leading/trailing
#: horizontal whitespace around ``[name]``, optionally followed by a trailing
#: ``#`` comment, nothing else on the line. Used to find the boundary where
#: the NEXT section begins (see :func:`find_section_boundaries`). Deliberately
#: line-anchored (``re.MULTILINE``) rather than a bare ``"\n["`` scan: a
#: bracketed value on a continuation line inside a multi-line array (e.g. a
#: nested-array metadata value) almost never forms a whole line by itself once
#: its own trailing comma/content is accounted for, so this stays a safe
#: heuristic for this project's TOML shape without needing a full TOML
#: tokenizer. The trailing ``(?:#.*)?`` (TOO-19 review fix) is what lets a
#: header line carry an inline comment, e.g. ``[permissions] # my perms`` --
#: without it, that common, valid TOML shape was wrongly treated as "no
#: section header on this line", regressing to the ``(-1, -1)``
#: "section not found" case (confirmed repro).
_ANY_SECTION_HEADER_RE = re.compile(r"(?m)^[ \t]*\[[^\]]+\][ \t]*(?:#.*)?$")


def _section_header_re(section_name: str) -> re.Pattern:
    """
    Compile a regex matching *section_name*'s TOML header as a whole line.

    Requires the ENTIRE line (ignoring only leading/trailing horizontal
    whitespace, and an optional trailing ``#`` comment -- see
    :data:`_ANY_SECTION_HEADER_RE`'s docstring for why that matters) to
    consist of ``[section_name]`` and nothing else. This is what keeps
    :func:`find_section_boundaries` from matching ``[section_name]`` when it
    merely appears as a SUBSTRING elsewhere in the file -- inside a quoted
    string value (e.g. an ``additionalContext`` mentioning ``"see
    [permissions] docs"``) or inside another section's ``#`` comment -- which
    a plain ``str.find`` cannot distinguish (TOO-19 correctness fix: the old
    substring scan could locate a false header inside quoted text and then
    splice a rewritten section into the MIDDLE of that string, producing
    unparseable TOML). A quoted-string occurrence like the example above is
    NOT a whole line by itself (it sits inside a longer ``additionalContext =
    "..."`` line), so it still correctly fails to match here even with the
    trailing-comment allowance.

    Args:
        section_name: Section name without brackets, e.g. ``'permissions'``.

    Returns:
        Compiled pattern matching only a genuine header line for this section.
    """
    return re.compile(rf"(?m)^[ \t]*\[{re.escape(section_name)}\][ \t]*(?:#.*)?$")


def find_section_boundaries(text: str, section_name: str) -> Tuple[int, int]:
    """
    Find start and end character positions of a TOML section in *text*.

    Both the section's own header and the NEXT section's header (the end
    boundary) are located as whole LINES (via :func:`_section_header_re` and
    :data:`_ANY_SECTION_HEADER_RE` respectively), not as a bare substring/
    character scan -- see :func:`_section_header_re`'s docstring for why that
    distinction matters (TOO-19 correctness fix).

    Args:
        text: Full TOML file content.
        section_name: Section name without brackets (e.g. ``'permissions'``).

    Returns:
        ``(start_pos, end_pos)`` where *start_pos* is the index of the
        ``[section_name]`` header line and *end_pos* is the index of the next
        section header line, or the end of the string when no further section
        header follows.  Returns ``(-1, -1)`` when the section is not found.
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
    Find the index of the ``]`` closing the array whose ``[`` is at ``open_pos``.

    Quote- and depth-aware, mirroring :func:`split_array_elements`'s own
    scanning rules (so the two functions agree on what counts as "inside a
    string"/"inside a comment"): a ``#`` outside a quote starts a line comment
    that runs to the next newline; ``"`` opens a TOML basic string (with
    backslash-escape awareness); ``'`` opens a TOML literal string (no
    escaping); nested ``[``/``{`` increase a combined depth counter and their
    closing counterparts decrease it, so a nested array/table value (e.g.
    ``applies_to = ["Bash", "Read"]`` inside a structured entry) never gets
    mistaken for the enclosing array's own close.

    Args:
        text: The full text to scan (typically an entire ``[permissions]``
            section).
        open_pos: Index of the ``[`` whose match is sought.

    Returns:
        Index of the matching ``]``, or ``len(text)`` if the input is
        malformed (no matching close found).
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
    Find one ``<perm_type> = [`` assignment's position within a section.

    This is the only subsection form real configs use -- the legacy
    ``[permissions.allow]`` header form (which never actually enclosed a
    valid array, has zero test coverage anywhere in this project, and is
    documented in this module's history as reserved/not emitted) is
    intentionally no longer recognized.

    Args:
        section_text: The full ``[permissions]`` section text.
        perm_type: ``'allow'``, ``'deny'``, or ``'ask'``.

    Returns:
        ``(match_start, open_pos, close_pos)`` -- the index where the
        ``<perm_type> = [`` line itself begins, the index of its own ``[``,
        and the index of the matching ``]`` (via :func:`_find_array_close`)
        -- or ``None`` if this subsection is absent from ``section_text``.
    """
    match = re.search(rf"(?m)^[ \t]*{perm_type}\s*=\s*\[", section_text)
    if not match:
        return None
    open_pos = match.end() - 1
    close_pos = _find_array_close(section_text, open_pos)
    return match.start(), open_pos, close_pos


# ---------------------------------------------------------------------------
# Top-level array-element boundary scanning (TOO-19 Phase 0b increment 2)
# ---------------------------------------------------------------------------
#
# A shared, tool-name-agnostic scanner that locates each top-level element of
# a TOML array via a single linear pass over the raw text between its "[" and
# "]" delimiters. Wired into production by TOO-19 Phase 0b increment 3's
# rewrite of toolguard.rule_sort.parse_permissions_section_with_comments (see
# that module's _parse_array_body), which feeds each element's .text to tomllib
# for value extraction. annotate.py and config_access.py consume that rewrite
# transparently -- they were not themselves changed (see
# parse_permissions_section_with_comments's docstring).
#
# This scanner's own multi-line-span awareness (an ArrayElement's start_line
# can differ from its end_line) is a DETECTION mechanism, not a support one,
# as of TOO-19's corrective change: _toml_value_of_chunk now rejects a
# multi-line structured entry as invalid TOML instead of accepting it, so a
# 'rule' item's content is always single-line by the time it reaches a
# caller. The span-tracking stays because find_multiline_structured_entry_line
# uses it to point a user at the exact offending entry when tomllib has
# already rejected the whole file.
#
# It deliberately does NOT enumerate tool names (Bash(/Read(/etc.) -- that
# would be brittle against `additional_supported_tools`, which lets users
# govern arbitrary tools. Splitting is purely structural: quote-state and
# brace-depth tracking, nothing about what a pattern string looks like.


@dataclass(frozen=True)
class ArrayElement:
    """
    One top-level element of a TOML array, as located by :func:`split_array_elements`.

    An "element" here is the array VALUE itself -- a quoted string
    (``"Bash(ls *)"``) or an inline/multi-line table (``{ match = "...", ... }``)
    -- deliberately excluding any full-line comment(s) that precede it and any
    trailing inline comment/whitespace that follows it up to its delimiting
    comma. Those are captured separately in ``leading``/``trailing`` so two
    different future consumers can each get exactly what they need without
    re-scanning:

    * ``annotate.py`` wants to insert a new leading comment line immediately
      above the element's OWN first line (``start_line``), i.e. BELOW any
      pre-existing leading comment block, which lives in ``leading`` instead
      -- not above the whole segment. This mirrors the current single-line
      parser's behaviour, where a generated ``# toolguard:`` comment is
      inserted directly above the rule's own line, never above a pre-existing
      human comment.
    * ``config_access.py`` wants a trailing inline ``#`` comment that sits on
      the element's OWN last line (``end_line``), which -- for a multi-line
      structured entry -- is not the same as the element's first line. That
      text lives in ``trailing`` (its portion before the first ``\\n``, if
      any).

    Every field describes a slice of the ORIGINAL text passed to
    :func:`split_array_elements` (not a copy re-based at zero), so several
    elements from the same call remain directly comparable/orderable.

    Reconstruction guarantee: for a single element,
    ``leading + text + trailing == original_text[segment_start:segment_end]``.
    Concatenating ``leading + text + trailing`` for every returned element, in
    order, and then appending ``original_text[elements[-1].segment_end:]``
    (any trailing comment-only remainder after the last element, before the
    array's closing ``]``, if the source had one) reconstructs
    ``original_text`` byte-for-byte. See :func:`split_array_elements` for why
    that remainder is not folded into an element itself.
    """

    #: The element's own value text, e.g. ``'"Bash(ls *)"'`` or
    #: ``'{ match = "Bash(x)" }'`` (possibly spanning multiple lines).
    text: str

    #: Raw text preceding ``text`` within this element's segment: blank lines,
    #: full-line ``#`` comments, and indentation since the previous top-level
    #: comma (or the start of the scanned input, for the first element).
    leading: str

    #: Raw text following ``text``: same-line trailing content (an inline
    #: ``# comment``, if any) plus the delimiting comma (if the source had
    #: one) plus anything up to the next element's ``leading`` (or, for the
    #: last element, up to wherever scanning stopped looking for a comma).
    trailing: str

    #: 0-based character offset of ``text``'s first character within the
    #: original input.
    start_pos: int

    #: 0-based character offset one past ``text``'s last character (exclusive)
    #: within the original input -- ``original_text[start_pos:end_pos] == text``.
    end_pos: int

    #: 1-based line number (within the original input) of ``text``'s first
    #: character.
    start_line: int

    #: 1-based line number (within the original input) of ``text``'s last
    #: character. Equal to ``start_line`` for a single-line element; greater
    #: for a multi-line structured entry.
    end_line: int

    #: 0-based character offset where this element's whole segment
    #: (``leading + text + trailing``) begins within the original input.
    segment_start: int

    #: 0-based character offset one past this element's whole segment
    #: (exclusive) -- also where the NEXT element's ``segment_start`` begins,
    #: for every element but the last.
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
    """
    Build one :class:`ArrayElement` from positions collected by :func:`split_array_elements`.

    A small helper so the two places that finalize an element (on a top-level
    comma, and at end-of-input) share exactly one construction path.

    Args:
        text: The full original input text being scanned.
        segment_start: Offset where this element's segment begins.
        value_start: Offset where the element's own value text begins.
        value_start_line: 1-based line number of ``value_start``.
        value_end: Offset one past the element's own value text (exclusive).
        value_end_line: 1-based line number of the value's last character.
        segment_end: Offset one past this element's whole segment (exclusive).

    Returns:
        The constructed :class:`ArrayElement`.
    """
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
    """
    Mutable state threaded through :func:`split_array_elements`'s single
    linear scan, one character at a time (see that function's docstring for
    the state machine this represents: quote/comment tracking, brace depth,
    and the position of the current segment's value, if found yet).

    A dedicated (mutable) object rather than a handful of loop-local
    variables purely so :func:`_scan_array_char` can advance the scan by one
    character without :func:`split_array_elements` itself needing to know
    the shape of that state -- the two functions are otherwise a single
    scan, just split across a call boundary.
    """

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
    #: Current nesting depth of top-level ``{...}`` tables.
    brace_depth: int = 0
    #: Current 1-based line number.
    line: int = 1


def _scan_array_char(text: str, i: int, ch: str, state: _ArrayScanState) -> None:
    """
    Advance *state* by exactly one character of :func:`split_array_elements`'s scan.

    A direct, unreordered extraction of that function's single linear pass:
    the branches below are tried in exactly the priority order its docstring
    describes (newline bookkeeping first, then comment/quote absorption, then
    quote/brace open+close, then the top-level comma that finalizes a
    segment into an :class:`ArrayElement`). This function's own docstring
    intentionally does not repeat that rationale -- see
    :func:`split_array_elements` for it.

    Args:
        text: The full original input text being scanned (needed only to
            build the finalized :class:`ArrayElement` on a top-level comma).
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
        # TOML literal (single-quoted) strings have no escape mechanism --
        # a "'" always ends the string, a "\\" is just a literal backslash.
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
        # A stray top-level comma with no value found yet in this segment
        # (malformed input) is absorbed into the still-open segment
        # rather than raising or emitting a broken element.
        return


def split_array_elements(text: str) -> Tuple[ArrayElement, ...]:
    """
    Locate top-level array-element boundaries in *text* via a single linear pass.

    *text* is the raw content BETWEEN a TOML array's ``[`` and ``]`` delimiters
    (the caller slices that out, e.g. via a subsection match on
    ``allow = [`` ... ``]``). The scan tracks quote state (``"..."`` TOML basic
    strings, with backslash-escape awareness, and ``'...'`` TOML literal
    strings, which have no escape mechanism) and brace depth (``{...}``,
    including nested tables), splitting only on a comma that appears at
    top level (depth 0, outside any quote or comment). A ``#`` outside a quote
    starts a line comment that runs to the next newline; commas, braces, and
    ``#`` characters INSIDE a quoted string are never treated as structural.

    Only ONE value is recognized per segment (a TOML array element is always a
    single value): the first ``"``, ``'``, or top-level ``{`` encountered in a
    segment marks ``text``'s start; its matching close (the closing quote, or
    the matching outer ``}`` for a table, however many lines away) marks
    ``text``'s end. Everything before that within the segment is ``leading``;
    everything after it, up to and including the delimiting comma (if any),
    is ``trailing``.

    A segment that contains no value at all (pure whitespace/comments) is not
    turned into an element -- this covers both a fully empty array (returns
    ``()``) and a comment-only remainder AFTER the last real element's comma,
    before the closing ``]`` (that remainder is simply not represented by any
    element; a caller can recover it, if needed, as
    ``text[elements[-1].segment_end:]`` -- constructing it into a
    "phantom" value-less element was considered and rejected as needless
    complexity for something no known consumer needs).

    This function is a pure boundary scanner: it does not know what a valid
    TOML value looks like beyond "quoted string" or "braced table", does not
    validate the array is well-formed, and does not raise on malformed input
    (e.g. an extra top-level ``{`` inside a segment that already found its
    value) -- it makes a best-effort, non-crashing scan, since a later
    increment's ``tomllib``-based per-element value extraction is where real
    TOML validity is actually enforced.

    Known limitation: the quote tracking recognizes single-``"``/``'`` basic
    and literal strings only -- it has no triple-quote (``\"\"\"``/``'''``)
    state, so a TOML multi-line string is mis-split wherever it contains a
    ``,``, ``{``, ``}``, or ``#`` that an ordinary quoted string would have
    protected (out of contract; not a supported input shape).

    The scan itself is delegated, one character at a time, to
    :func:`_scan_array_char`, which mutates a shared :class:`_ArrayScanState`
    -- this function's own body is just that loop plus finalizing whatever
    segment is still open at end-of-input (a segment's value has no closing
    comma when it is the array's last element).

    Args:
        text: Raw text between a TOML array's ``[`` and ``]`` (exclusive of
            the brackets themselves).

    Returns:
        A tuple of :class:`ArrayElement`, one per top-level array element
        found, in source order. Empty when *text* contains no value at all.
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
# Multi-line structured entry diagnostic (TOO-19 corrective change)
# ---------------------------------------------------------------------------


def find_multiline_structured_entry_line(text: str) -> Optional[int]:
    """
    Return the 1-based line number of the first multi-line structured entry
    found in a whole TOML file's *text*, or ``None`` if there is none.

    Used ONLY to turn a raw ``tomllib.TOMLDecodeError`` (already raised
    elsewhere, e.g. by :func:`toolguard.config._parse_source`'s direct
    ``tomllib.load`` call, or by
    :func:`toolguard.rule_sort.parse_permissions_section_with_comments`) into
    an actionable diagnostic naming the offending line -- a multi-line
    structured entry is this project's single highest-impact TOML mistake,
    since it silently disables every rule in the file. This function does
    not itself validate TOML and is not a second parser: it locates each
    ``allow``/``deny``/``ask`` array inside *text*'s ``[permissions]``
    section (:func:`find_section_boundaries`, :func:`_locate_subsection`) and
    scans each one's interior with :func:`split_array_elements` -- the SAME
    structural scanner
    :func:`toolguard.rule_sort.parse_permissions_section_with_comments` uses,
    kept quote/brace-aware and non-crashing on malformed input specifically
    so it remains usable here, on text ``tomllib`` has already rejected.

    Deliberately narrow: it reports a line only when it finds this ONE
    specific, unambiguous shape (an element starting with ``{`` whose
    ``ArrayElement.start_line`` differs from its ``end_line``). Any other
    TOML error -- a typo, a missing quote, a wrong-shaped table -- is out of
    scope and correctly yields ``None``, so a caller building a diagnostic
    message can fall back to the generic one instead of guessing wrong.

    Args:
        text: Full raw text of a TOML config file. Need not be valid TOML;
            the scan is best-effort, mirroring :func:`split_array_elements`'s
            own tolerance of malformed input.

    Returns:
        1-based line number (within *text*) of the first offending entry's
        opening ``{``, or ``None`` if *text* has no ``[permissions]`` section
        or no multi-line structured entry was found in it.
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
