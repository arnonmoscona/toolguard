"""
Canonical sorting and comment-preserving section machinery for toolguard rules.

This module contains the single authoritative implementation of permission-rule
sorting and TOML ``[permissions]`` section parsing/reassembly.  Both the
migration script and the tools layer import from here so that there is exactly
ONE sort order in the codebase.

Sorting order
-------------
1. Tool priority: Bash (0), Read (1), Write (2), Edit (3), all others (4).
2. Within each tool bucket: case-insensitive alphabetical on the FULL pattern
   string (e.g. ``Bash(git:*)`` sorts before ``Bash(uv run:*)``).

All functions are pure (no side-effects, no I/O) and depend only on the Python
standard library, :mod:`toolguard.rule_entry` (a leaf module), and
:mod:`toolguard.toml_scan` (also a leaf module: the pure TOML section/array
boundary scanners this module builds its comment-preserving parser on top of,
moved out -- TOO-19 review fix -- so that :mod:`toolguard.config`'s hot path
can use :func:`toolguard.toml_scan.find_multiline_structured_entry_line`
without importing this whole tooling module. Every public name moved there is
re-imported and re-exported below for backward compatibility).

Structured entries are single-line, always (TOO-19 corrective change)
------------------------------------------------------------------------
A structured permission entry (``{ match = "...", additionalContext = "..." }``)
MUST be written on exactly one physical line. This is not a style preference:
TOML 1.0 (stdlib :mod:`tomllib`'s spec version, and the only parser this
project's runtime config loader uses) forbids an inline table from spanning
multiple physical lines. A file authored with a multi-line structured entry
fails to parse, and -- because the config loader fails open on a parse error
-- silently disables EVERY rule in that file, including ``deny``/``hard_deny``.
This module previously worked around that by pre-normalizing a multi-line
chunk to one line before handing it to ``tomllib`` (see git history around
``_toml_value_of_chunk``/the now-removed ``_flatten_inline_table``), which let
this module's own tooling (migration, annotation, config-access reporting)
round-trip a shape the runtime loader could never actually read -- making the
format look supported when enforcement was silently dead. Do not reintroduce
that workaround. See :func:`toolguard.toml_scan.find_multiline_structured_entry_line`
for the diagnostic offered instead: pointing a user at the exact offending
line so they can fix the formatting, not silently tolerating it.

Element shape (TOO-19 Phase 0a increment 8)
--------------------------------------------
Every function here that handles a permission "pattern" accepts EITHER a bare
``str`` (the historical contract, still fully supported -- this module has
long-standing direct callers/tests that pass plain pattern strings) or a
:class:`~toolguard.rule_entry.RuleEntry` (the write path's uniform payload
type: migration and ``rule_apply`` feed ``RuleEntry`` lists straight through
here end-to-end, so a structured entry's metadata is never re-derived or
re-guessed). This is what fixes the confirmed "TypeError: unhashable type:
'dict'" defect: a RAW, un-normalized ``dict`` used to reach
:func:`get_tool_priority` whenever write-path code fed a config file's raw
permissions list straight into :func:`sort_patterns`; every write-path caller
now normalizes first (see :func:`toolguard.rule_entry.normalize_entries_preserving`),
so the only two shapes any function in this module ever sees are ``str`` and
``RuleEntry`` -- both handled, in exactly one place each
(:func:`get_tool_priority`, :func:`_pattern_of`, :func:`render_toml_entry`),
never re-checked ad hoc elsewhere in this module.
"""

import re
import tomllib
from typing import Dict, List, Optional, Tuple, Union

from toolguard.rule_entry import PATTERN_KEY, RuleEntry

# Re-imported (and re-exported -- see each name's own re-export comment below)
# from toolguard.toml_scan, the pure TOML section/array boundary scanning leaf
# module these were moved into (TOO-19 review fix, ITEM 8): this module's own
# _locate_subsection/split_array_elements calls, several tooling modules'
# `from toolguard.rule_sort import find_section_boundaries`, and
# test_rule_sort.py's direct imports of ArrayElement/find_section_boundaries/
# find_multiline_structured_entry_line/split_array_elements all keep working
# unchanged. toolguard.config imports find_multiline_structured_entry_line
# directly from toolguard.toml_scan instead (see that module's docstring).
from toolguard.toml_scan import (  # noqa: F401 -- re-exported for backward compat
    ArrayElement,
    _locate_subsection,
    find_multiline_structured_entry_line,
    find_section_boundaries,
    split_array_elements,
)

#: A permission entry as this module accepts it: either a bare pattern string
#: (legacy contract) or a normalized :class:`RuleEntry` (write-path contract).
RuleEntryOrStr = Union[str, RuleEntry]


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------


def get_tool_priority(entry: RuleEntryOrStr) -> Tuple[int, str]:
    """
    Return a sort key for a permission entry.

    The key is a ``(priority, lowercase_pattern)`` tuple where priority is:

    * 0 -- Bash
    * 1 -- Read
    * 2 -- Write
    * 3 -- Edit
    * 4 -- any other tool

    The secondary key (``lowercase_pattern``) is the full pattern string
    lowercased, giving case-insensitive alphabetical ordering within each tool
    bucket. Sorting is by ``.pattern`` alone (comparison #1, "same RULE" --
    see :meth:`RuleEntry.identity`'s docstring) -- a structured entry's
    metadata never affects ordering.

    Args:
        entry: A permission pattern string such as ``Bash(git:*)`` or
            ``Read(/tmp/*)`` (may include an extended-syntax prefix like
            ``[regex]``), OR a :class:`RuleEntry` whose ``.pattern`` is used.

    Returns:
        Tuple ``(priority, lowercase_pattern)`` for use as a sort key.
    """
    pattern = entry.pattern if isinstance(entry, RuleEntry) else entry
    tool_priorities = {"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}

    # Extract tool name (text before the first '(' or the whole string).
    tool_name = pattern.split("(")[0] if "(" in pattern else pattern
    priority = tool_priorities.get(tool_name, 4)

    return (priority, pattern.lower())


def sort_patterns(patterns: List[RuleEntryOrStr]) -> List[RuleEntryOrStr]:
    """
    Return a new sorted list of permission entries in canonical order.

    Entries are sorted by tool priority (Bash first, then Read, Write, Edit,
    then others) and then alphabetically by the full pattern string
    (case-insensitive).  The input list is never mutated, and elements are
    never rebuilt -- each is returned exactly as given (a ``str`` stays a
    ``str``; a ``RuleEntry`` stays that same ``RuleEntry`` object, metadata
    and all).  The sort is stable: entries that compare equal under the key
    retain their original relative order. A list may freely mix ``str`` and
    ``RuleEntry`` elements; :func:`get_tool_priority` resolves each
    independently.

    Args:
        patterns: A list of permission patterns in their full wrapped form
            (e.g. ``['Read(/tmp/*)', 'Bash(git:*)']``), or ``RuleEntry``
            objects, or a mix of both.

    Returns:
        A new list containing the same entries in canonical order.
    """
    return sorted(patterns, key=get_tool_priority)


def _pattern_of(entry: RuleEntryOrStr) -> str:
    """
    Return the wrapped pattern string for a permission entry, either shape.

    The single place :func:`reassemble_permissions_section` extracts
    ``.pattern`` from either a bare ``str`` or a :class:`RuleEntry`, mirroring
    :func:`get_tool_priority`'s identical resolution (kept as two functions,
    not one, since their return types differ: a sort key vs. a bare pattern).

    Args:
        entry: A pattern ``str`` or a :class:`RuleEntry`.

    Returns:
        The wrapped pattern string.
    """
    return entry.pattern if isinstance(entry, RuleEntry) else entry


# ---------------------------------------------------------------------------
# TOML rendering of a single rule entry
# ---------------------------------------------------------------------------


def _escape_toml_string(value: str) -> str:
    """
    Escape a string for use inside a double-quoted TOML basic string.

    The single source of this escaping -- previously duplicated inline at
    each pattern-emission call site in this module and in
    ``permission_migration.generate_permissions_section``.

    Args:
        value: The raw string to escape.

    Returns:
        ``value`` with backslashes and double quotes escaped.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _render_toml_key(key: str) -> str:
    """
    Render a TOML table key: bare when safe, quoted otherwise.

    Args:
        key: A metadata key, e.g. ``"additionalContext"``.

    Returns:
        The key as TOML source: unquoted when it is a valid bare key
        (``[A-Za-z0-9_-]+``), otherwise a quoted basic string.
    """
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return f'"{_escape_toml_string(key)}"'


def _render_toml_scalar(value: object) -> str:
    """
    Render one metadata value as TOML source.

    Supports every value shape :class:`RuleEntry.metadata` is documented to
    allow (str, bool, int, float, and list/dict of those -- see that
    docstring for why metadata stays a plain ``Mapping`` rather than a
    flat-primitive-only shape). Anything else falls back to its ``str()``
    form, quoted -- this keeps a single writer that can never raise on a
    synthesized/edited entry's metadata, rather than growing a special case
    per new enrichment-value type.

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
    Render a dict as a single-line TOML inline table.

    E.g. ``{"match": "Bash(*)", "additionalContext": "x"}`` renders as
    ``{ match = "Bash(*)", additionalContext = "x" }``. Always single-line:
    TOML 1.0 forbids an inline table from spanning multiple physical lines,
    and this project never authors one that does (TOO-19 corrective change --
    see this module's top-of-file docstring).

    Args:
        table: The dict to render (typically a :meth:`RuleEntry.to_source`
            result).

    Returns:
        TOML inline-table source, valid to embed as one list item.
    """
    body = ", ".join(
        f"{_render_toml_key(k)} = {_render_toml_scalar(v)}" for k, v in table.items()
    )
    return "{ " + body + " }"


def render_toml_entry(entry: RuleEntryOrStr) -> str:
    """
    Render one permission entry's TOML source for a single list item.

    Used ONLY for an entry with no original source line to reuse verbatim (a
    brand-new entry, or one whose ``.pattern`` has no match in a file's
    parsed structure) -- an entry with an original line always reuses that
    line unchanged instead (the byte-identical round-trip guarantee lives in
    the caller, not here). Returns quoted-string TOML for a plain pattern and
    a single-line inline table for a structured entry, WITHOUT the caller's
    list indentation or trailing comma.

    This is the ONE point where a :class:`RuleEntry` is actually emitted as
    TOML (``entry.to_source()``), shared by both
    :func:`reassemble_permissions_section`'s synthesize-fallback and
    ``permission_migration.generate_permissions_section`` (the from-scratch
    writer), so there is exactly one TOML serialization of a structured entry
    in the codebase.

    Delegates to :func:`_render_toml_scalar` for the actual rendering (TOO-19
    review fix): ``entry.to_source()`` is documented to be able to return ANY
    JSON value verbatim (a JSON config's ``permissions.allow`` may hold an
    ``int``, ``bool``, ``None``, or ``list`` element -- see
    :func:`~toolguard.rule_entry.normalize_entries_preserving`, which
    deliberately preserves such an element rather than dropping it), and
    ``_render_toml_scalar`` is this module's one TOTAL renderer that already
    handles every one of those shapes (plus ``dict``, via
    :func:`_render_toml_inline_table`). Previously this function only handled
    ``dict`` explicitly and fell through to string-escaping for everything
    else, raising ``AttributeError`` on a non-``str``, non-``dict`` source
    (confirmed repro: ``render_toml_entry`` on an entry whose ``to_source()``
    is ``42``, ``None``, or ``True``).

    Args:
        entry: The entry to render -- a bare pattern ``str`` or a
            :class:`RuleEntry`.

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
    and parses it with stdlib :mod:`tomllib`, UNMODIFIED -- the single point
    where a permission entry's literal syntax (a quoted string, or a
    structured ``{...}`` table) becomes a real value, and stdlib
    :mod:`tomllib` is the sole arbiter of whether that syntax is valid (TOO-19
    corrective change: this module previously pre-normalized a multi-line
    ``{...}`` chunk into one line before handing it to ``tomllib`` -- see this
    module's git history for ``_flatten_inline_table`` -- which let a
    multi-line structured entry round-trip through this module's own tooling
    even though TOML 1.0 (and every other consumer of these files, including
    the runtime config loader) has never accepted one. That silently made a
    security-critical formatting mistake look supported. It is not: a
    structured rule entry MUST be written on a single physical line, full
    stop -- see this module's top-of-file docstring). A ``text`` that spans
    multiple physical lines (an invalid multi-line inline table) now raises
    ``tomllib.TOMLDecodeError`` here, same as it always has for stdlib
    ``tomllib`` itself; this function does not catch it -- the caller
    decides whether to propagate or degrade (see
    :func:`parse_permissions_section_with_comments`'s docstring for why
    propagating, not silently dropping the entry, is the deliberate choice).

    This also replaced the old hand-rolled quote regex (``r'"([^"]*)"'``),
    which silently truncated at an escaped quote (``"Bash(echo \\"hi\\")"``
    parsed to ``Bash(echo \\``) -- TOO-19 Phase 0b increment 3 fixed that as a
    side effect of using a real TOML parser, which understands
    backslash-escaping natively. A plain quoted string never needed any
    normalization: TOML basic/literal strings (without the triple-quote
    syntax this project never emits or expects) cannot span multiple physical
    lines to begin with.

    Args:
        text: One array element's own source text, as found by
            :func:`split_array_elements` -- a quoted string (always
            single-line) or a ``{...}`` table (single-line to parse
            successfully; :func:`split_array_elements` may still hand this a
            multi-line one, which is the malformed case this function now
            surfaces instead of silently accepting).

    Returns:
        The parsed value: a ``str`` for a quoted pattern, or a ``dict`` for a
        structured entry.

    Raises:
        tomllib.TOMLDecodeError: ``text`` is not valid single-line TOML --
            most notably, a structured entry written across multiple
            physical lines.
    """
    parsed = tomllib.loads(f"x = [ {text} ]")
    return parsed["x"][0]


def _flush_comment_lines(lines: List[str]) -> Optional[str]:
    """
    Join a run of raw text lines into one comment_block's content, or ``None``.

    Mirrors the pre-rewrite line-by-line parser's accumulation rule exactly:
    every ``#`` comment line is kept; a blank line is kept ONLY once the
    buffer already holds something (i.e. it falls BETWEEN two collected
    lines) -- a leading or freestanding blank run with no comment adjacent
    contributes nothing to the block. ``lines`` is expected to contain only
    comment/blank lines (the only content :func:`_parse_array_body` and
    :func:`parse_permissions_section_with_comments` ever route here); anything
    else is silently ignored rather than raised on, matching the old parser's
    tolerance of malformed input.

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
    Marker ``str`` subclass identifying a SYNTHESIZED, non-matchable rule
    pattern (TOO-19 review fix).

    Returned by :func:`_rule_pattern_of_value` in place of a real pattern
    when a parsed array element has no legitimate pattern to key by (e.g. a
    structured entry missing its ``match`` key) -- mirrors
    :class:`~toolguard.rule_entry.RuleEntry`'s own
    ``synthesized_pattern`` marker for the same class of malformed input,
    kept as a separate mechanism here because this module's "rule" items
    carry a bare pattern *string*, not a :class:`RuleEntry`.

    Behaves exactly like ``str`` everywhere (equality, hashing, dict keys,
    ``_split_tool_pattern`` string ops, ...), so every existing consumer of a
    ``'rule'`` item's ``parsed_value`` -- ``rule_lines``/``rule_comments``
    keying in :func:`reassemble_permissions_section`,
    ``toolguard.tools.annotate``, ``toolguard.tools.config_access`` -- keeps
    working completely unchanged. :func:`is_synthetic_pattern` is the one
    place that distinguishes it: e.g.
    ``toolguard.tools.maintenance._permission_patterns_in_text`` must never
    feed this value into the config-write content-loss guard as an
    ``expected_patterns`` entry, since the guard recomputes "present"
    patterns from the ACTUAL text being written and can never reproduce a
    synthesized ``repr()`` string -- passing one through would wrongly look
    like a dropped rule and refuse an otherwise-safe write.
    """


def is_synthetic_pattern(value: object) -> bool:
    """
    Report whether *value* is a :class:`SyntheticPattern` (a synthesized,
    non-matchable stand-in produced by :func:`_rule_pattern_of_value` for a
    malformed rule entry), rather than a real permission pattern.

    Args:
        value: Typically a ``'rule'`` item's ``parsed_value`` from
            :func:`parse_permissions_section_with_comments`.

    Returns:
        ``True`` iff *value* is a :class:`SyntheticPattern`.
    """
    return isinstance(value, SyntheticPattern)


def _rule_pattern_of_value(value: object) -> str:
    """
    Extract the permission-pattern string from one parsed array-element value.

    A plain string value IS its own pattern. A structured (``dict``) value's
    pattern lives under :data:`toolguard.rule_entry.PATTERN_KEY` (``"match"``)
    -- mirrors :class:`~toolguard.rule_entry.RuleEntry` so a structured
    entry's parsed_value is directly usable everywhere a bare pattern string
    is expected (e.g. as a ``rule_lines``/``rule_comments`` key in
    :func:`reassemble_permissions_section`). A dict missing the key (malformed
    input -- full validation is :func:`~toolguard.rule_entry.normalize_entry`'s
    job, not this comment-preserving parser's) falls back to a
    :class:`SyntheticPattern` wrapping ``repr(value)`` (TOO-19 review fix: was
    a bare ``str`` before, indistinguishable from a real pattern -- see
    :func:`is_synthetic_pattern`) so parsing never raises here, while still
    letting a write-path caller recognise and exclude it from
    ``expected_patterns``.

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

    Splits the array's interior (the text strictly between ``open_pos`` and
    ``close_pos``, i.e. between its ``[`` and matching ``]``) into elements via
    :func:`split_array_elements`. Each element's own leading comment lines
    become a preceding ``comment_block`` item; its value (extracted via
    :func:`_toml_value_of_chunk`, which raises ``tomllib.TOMLDecodeError`` --
    propagated, not caught here -- for a malformed element, most notably a
    structured entry spanning more than one physical line) and reconstructed
    original source span (own indentation, value text, and same-line trailing
    comma/comment) become a ``rule`` item.

    An element's SAME-LINE trailing content (its own delimiting comma and/or
    an inline ``#`` comment before the next newline) is folded into its own
    ``rule`` content rather than the next element's leading comment_block --
    this is what keeps ``"Bash(ls:*)",  # note`` attached to its own rule
    instead of becoming a leading comment for whatever rule follows. Content
    on a LATER line still belongs to the *next* element's leading comment
    block (or, after the last element, to a trailing bottom comment_block).
    A comment appearing BEFORE this array's own ``[`` (outside it, e.g. right
    under the ``[permissions]`` header) is NOT this function's concern -- see
    :func:`parse_permissions_section_with_comments`, which handles that as an
    inter-subsection gap.

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
    """
    body = section_text[open_pos + 1 : close_pos]
    elements = split_array_elements(body)
    items: List[Tuple[str, str, Optional[str]]] = []

    if not elements:
        # No value at all -- still surface a comment-only body (e.g. a
        # not-yet-populated list with just an explanatory comment) as a
        # single trailing comment_block, matching the old parser's "flush
        # whatever's pending when the closing bracket is hit" behaviour.
        bottom = _trailing_comment_source_lines(body)
        comment_text = _flush_comment_lines(bottom)
        if comment_text is not None:
            items.append(("comment_block", comment_text, None))
        return items

    # pending_prefix carries raw text (comments/blanks/indentation) that has
    # not yet been assigned to a comment_block or a rule's own leading
    # whitespace. It starts as the very first element's leading text, and
    # after each element is processed becomes whatever text follows that
    # element's delimiting comma (or trailing content) up to -- but not
    # including -- the next element's own indentation line.
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

    TOML permits the array's syntactically LAST element to omit its
    delimiting comma. :func:`_parse_array_body` reuses that element's
    original source span verbatim (the round-trip guarantee documented on
    :func:`reassemble_permissions_section`) -- but sorting is free to move
    that same element out of last position, at which point a reused span with
    no comma produces invalid TOML at the next parse (confirmed repro, TOO-19
    review fix M5: ``allow = ["Bash(zz)", "Bash(aa)"]`` with no comma on
    ``"Bash(aa)"`` -- the source's last element -- becomes
    ``tomllib.TOMLDecodeError: Unclosed array`` once sorting moves ``aa``
    before ``zz``). A trailing comma on the array's actual last element is
    always legal TOML, so normalizing every reused span to end in one is
    unconditionally safe and keeps every span's shape uniform.

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

    Shared by every place that hands a whole SPAN of comment/blank text (as
    opposed to one element's own single leading-comment span, which
    :func:`_parse_array_body` peels apart itself) to
    :func:`_flush_comment_lines`: the trailing text after the last element in
    an array body, a comment-only (no-value) array body, and the
    inter-subsection gap text in :func:`parse_permissions_section_with_comments`.
    In every one of these, ``source`` ends with exactly one ``\\n`` when it
    has any content at all (the line terminator of the last real content
    line, immediately before wherever the NEXT known token starts -- an
    array's closing ``]``, or the next subsection's own ``allow``/``deny``/
    ``ask =`` line) -- ``str.split("\\n")`` turns that into a final empty
    string that does not correspond to an actual blank LINE in the file,
    unlike a genuine blank line (TWO trailing newlines), which must still be
    kept. This drops exactly one such artifact, never more.

    Args:
        source: Raw comment/blank text with no more array elements in it.

    Returns:
        The candidate lines, with any single trailing empty-string artifact
        removed.
    """
    lines = source.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    return lines


def parse_permissions_section_with_comments(section_text: str) -> Dict:
    """
    Parse a ``[permissions]`` section, preserving comments and their associations.

    Each permission sub-list (allow / deny / ask) is represented as an ordered
    list of typed items so that comments can be round-tripped through a
    sort-and-reassemble cycle without loss.

    Item types:

    * ``'comment_block'`` -- one or more consecutive comment/blank lines.
    * ``'rule'``          -- one permission entry, plain or structured. Its
      ``content`` is the entry's own original source span (own indentation
      through its same-line trailing comma/comment) -- always a SINGLE
      physical line: a structured ``{...}`` entry is valid TOML only when
      written on one line (TOML 1.0 forbids an inline table from spanning
      multiple physical lines), and this function raises rather than
      returning one that doesn't (see "Raises" below).

    A *comment_block* that immediately precedes a *rule* is considered to
    "belong to" that rule and travels with it when rules are re-sorted.
    Comment blocks that appear before the first rule or after the last rule are
    anchored to the top or bottom of the sub-section respectively.

    TOO-19 Phase 0b increment 3 rewrote this on top of two building blocks
    instead of a one-pattern-per-physical-line regex scan: each subsection's
    array interior is split into elements by :func:`split_array_elements`
    (quote/brace-depth-aware, so a value's own commas/braces/``#`` never
    cause a spurious split), and each element's value is then extracted by
    stdlib :func:`tomllib.loads` via :func:`_toml_value_of_chunk` instead of a
    hand-rolled quote regex. That fixed a real truncation bug the old regex
    had with an escaped quote inside a double-quoted pattern. A later TOO-19
    corrective change removed this rewrite's original ADDITIONAL behaviour of
    accepting a multi-line structured entry (via a pre-normalization step
    that collapsed it to one line before handing it to ``tomllib``): TOML 1.0
    never actually allowed that shape, so pre-normalizing it made this
    module's own tooling (migration, annotation, config-access reporting)
    silently more permissive than the runtime config loader, which always
    rejected it -- exactly the kind of "looks supported but isn't" gap that
    hides a security-relevant formatting mistake. :func:`split_array_elements`
    still recognizes a multi-line ``{...}`` span structurally (needed to
    build an actionable diagnostic pointing at the offending entry -- see
    :func:`find_multiline_structured_entry_line`); this function just no
    longer accepts one as valid content.

    A comment sitting OUTSIDE a subsection's own array brackets -- between the
    ``[permissions]`` header and the first ``allow``/``deny``/``ask =`` line,
    or between one subsection's closing ``]`` and the next subsection's own
    ``=`` line -- is attached as a leading ``comment_block`` to whichever
    subsection follows it (never to the one before), matching the old
    line-by-line parser's single-global-buffer behaviour. Subsections are
    processed in the order they actually appear in ``section_text`` (not the
    fixed ``allow``/``deny``/``ask`` enumeration order) so this gap
    attribution is correct regardless of how a file orders its subsections.

    Args:
        section_text: The full text of the ``[permissions]`` section, including
            its ``[permissions]`` header line.

    Any text remaining AFTER the last subsection's closing ``]`` -- e.g. a
    comment explaining a following ``[hard_deny]`` section -- is captured
    too (TOO-19 review fix M1: this trailing text used to be silently
    dropped on write-back, which is exactly the kind of comment loss that
    can erase the human-readable rationale for a security rule). It is
    returned under the extra top-level ``'trailing_comment'`` key rather
    than folded into one of the three subsection lists, so it survives a
    round trip through :func:`reassemble_permissions_section` without being
    mistaken for content belonging to ``allow``/``deny``/``ask``. Every
    existing caller only ever reads ``result.get(perm_type, [])`` for
    ``perm_type in ("allow", "deny", "ask")``, so this extra key is
    invisible to them.

    Returns:
        ``Dict`` with keys ``'allow'``, ``'deny'``, ``'ask'``, and
        ``'trailing_comment'``.  Each of the first three values is a list of
        ``(item_type, content, parsed_value)`` tuples, where *parsed_value*
        is the extracted pattern string for ``'rule'`` items and ``None``
        for ``'comment_block'`` items. ``'trailing_comment'`` is the raw
        text (verbatim, embedded newlines and all) that followed the last
        subsection's ``]``, or ``None`` if there was none (or it held only
        blank lines).

    Raises:
        tomllib.TOMLDecodeError: An array element fails to parse as valid
            TOML -- most notably, a structured entry written across more
            than one physical line. Deliberately NOT caught here: a
            malformed entry must fail loudly, not vanish silently from the
            parsed structure (the exact defect class TOO-19 exists to
            remove). Callers that want a softer degrade-on-failure policy
            (e.g. a best-effort reporting tool) catch this at their own call
            site instead -- see e.g. ``toolguard.tools.config_access``'s
            ``_layer_comment_map``.
    """
    located = []
    for perm_type in ("allow", "deny", "ask"):
        location = _locate_subsection(section_text, perm_type)
        if location is not None:
            match_start, open_pos, close_pos = location
            located.append((match_start, perm_type, open_pos, close_pos))
    located.sort(key=lambda entry: entry[0])

    result = {"allow": [], "deny": [], "ask": []}
    prev_end = 0
    for match_start, perm_type, open_pos, close_pos in located:
        gap_text = section_text[prev_end:match_start]
        gap_comment = _flush_comment_lines(_trailing_comment_source_lines(gap_text))

        items: List[Tuple[str, str, Optional[str]]] = []
        if gap_comment is not None:
            items.append(("comment_block", gap_comment, None))
        items.extend(_parse_array_body(section_text, open_pos, close_pos))

        result[perm_type] = items
        prev_end = close_pos + 1

    # Text after the LAST subsection's ']' (TOO-19 review fix M1). Deliberately
    # NOT using _trailing_comment_source_lines here: that helper drops one
    # trailing empty-string split artifact on the assumption a FOLLOWING known
    # token (the next subsection's own "allow"/"deny"/"ask =" line) will supply
    # the missing final newline back on reassembly. There is no such follow-up
    # token after the last subsection, so that drop would silently eat the
    # final newline of this trailing text. Splitting directly and handing every
    # part to _flush_comment_lines (which already drops leading blank lines
    # while its buffer is empty) reproduces the original text byte-for-byte on
    # reassembly instead.
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

    Round-trip guarantee: an entry whose ``.pattern`` matches a pattern found
    in ``parsed_structure`` reuses that entry's ORIGINAL source span verbatim
    (``rule_lines``/``rule_comments``, keyed by ``(pattern, occurrence_index)``
    -- see "Duplicate-pattern keying" below, not by pattern alone) -- one
    physical line, for either a plain pattern or a structured entry (see
    :func:`parse_permissions_section_with_comments`: a ``'rule'`` item's
    content is always single-line since that function raises rather than
    accepting a multi-line one). This is what makes an untouched entry
    byte-identical after a sort-and-reassemble cycle, including a structured
    entry's own formatting and enrichment, without this function ever
    re-rendering it (TOO-19 Phase 0b increment 4's headline round-trip
    guarantee). Only an entry with no matching original source (new, or
    added by this write) is rendered fresh, via :func:`render_toml_entry`
    (also always single-line -- see its docstring).

    Duplicate-pattern keying (TOO-19 Change 4 fix): when the original file
    has MORE THAN ONE entry sharing a pattern but differing in metadata (e.g.
    two structured entries with different ``additionalContext`` --
    deliberately preserved side-by-side by :func:`~toolguard.rule_entry.merge_entries`'s
    case-3 contradiction handling so a human can resolve them), a naive
    ``pattern -> line`` map can only keep ONE of them, silently destroying the
    other's enrichment on the next write. This function instead keys both
    ``rule_lines``/``rule_comments`` AND each ``new_permissions`` entry by
    ``(pattern, occurrence_index)``, where ``occurrence_index`` is the entry's
    0-based position among same-pattern entries, counted separately on each
    side (parse order for the former, ``new_permissions``'s own given order --
    BEFORE sorting -- for the latter). This relies on same-pattern duplicates
    appearing in the same RELATIVE order on both sides, which holds for every
    known caller: :func:`~toolguard.rule_entry.merge_entries` explicitly
    documents preserving "first-appearance order... within a group", and no
    other caller reorders same-pattern duplicates independently. A full
    ``RuleEntry.identity()``-based match (pattern PLUS metadata) was
    considered but rejected: :func:`parse_permissions_section_with_comments`
    only ever surfaces a rule's bare pattern as ``parsed_value`` (see that
    function's docstring), not its parsed metadata, and widening that return
    shape would ripple into every other consumer
    (:mod:`toolguard.tools.annotate`, :mod:`toolguard.tools.config_access`)
    that relies on ``parsed_value`` being a bare pattern string.

    Args:
        parsed_structure: Structure returned by
            :func:`parse_permissions_section_with_comments`.
        new_permissions: New permission values to use, as a dict with keys
            ``'allow'``, ``'deny'``, ``'ask'``, each a list of pattern
            ``str`` and/or :class:`~toolguard.rule_entry.RuleEntry` (a
            structured entry MUST be a ``RuleEntry`` -- a bare ``dict`` is
            never accepted here, keeping this function's own element
            handling to exactly two shapes).
        auto_sort: When ``True`` (the default), patterns are sorted using
            :func:`sort_patterns` before reassembly.

    Returns:
        Complete ``[permissions]`` section text, including the header line, with
        comments preserved and rules ordered.
    """
    lines = ["[permissions]"]

    for perm_type in ["allow", "deny", "ask"]:
        entries = new_permissions.get(perm_type, [])
        if not entries:
            continue

        parsed_items = parsed_structure.get(perm_type, [])

        # Classify parsed items into top/bottom comment anchors and per-rule
        # comment associations. Keyed by (pattern, occurrence_index), NOT
        # pattern alone (TOO-19 Change 4 fix -- see this function's own
        # "Duplicate-pattern keying" docstring section): two ORIGINAL rule
        # items sharing a pattern get distinct keys, counted in PARSE order.
        top_comments = []
        bottom_comments = []
        rule_comments: Dict[Tuple[str, int], str] = {}
        rule_lines: Dict[Tuple[str, int], str] = {}

        current_comment_block = None
        seen_first_rule = False
        parsed_occurrence_count: Dict[str, int] = {}

        for item_type, content, value in parsed_items:
            if item_type == "comment_block":
                if not seen_first_rule:
                    top_comments.append(content)
                else:
                    current_comment_block = content
            elif item_type == "rule":
                seen_first_rule = True
                occurrence = parsed_occurrence_count.get(value, 0)
                parsed_occurrence_count[value] = occurrence + 1
                key = (value, occurrence)
                rule_lines[key] = content
                if current_comment_block:
                    rule_comments[key] = current_comment_block
                    current_comment_block = None

        # Any trailing comment block belongs to the bottom.
        if current_comment_block:
            bottom_comments.append(current_comment_block)

        # Assign each entry its own (pattern, occurrence_index) key in
        # `entries`'s GIVEN (pre-sort) order -- matching the parse-order
        # counting above -- THEN sort, keeping each entry paired with its
        # precomputed key rather than re-deriving it post-sort.
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

        for comment_block in top_comments:
            lines.append(comment_block)

        for entry, key in keyed_entries:
            # Preceding comment block travels with the rule.
            if key in rule_comments:
                lines.append(rule_comments[key])

            # Use original line (preserves inline comments AND enrichment
            # formatting -- the round-trip guarantee) ONLY for an entry that
            # is itself a verbatim round-trip of file content (a bare str, or
            # a RuleEntry whose `.has_raw` is True -- see
            # RuleEntry.to_source()'s "has_raw" contract; NOT `.raw is None`,
            # since a RuleEntry can legitimately have `raw=None` recorded --
            # e.g. a JSON config's `null` element -- and that must still
            # count as having a raw to preserve). Render fresh
            # (`render_toml_entry`) whenever no original line exists for this
            # entry's key, OR the entry is a SYNTHESIZED RuleEntry (`has_raw`
            # is False, e.g. `merge_entries`'s case-2 union-merge result,
            # TOO-19 Phase 0a increment 9): now that `rule_lines` is keyed by
            # (pattern, occurrence_index) rather than pattern alone (TOO-19
            # Change 4), a synthesized entry (which represents a MERGE of
            # what may have been several original occurrences) still has no
            # single original occurrence of its own to reuse, so it is always
            # rendered fresh rather than replaying one arbitrary original's
            # leftover text.
            is_synthesized = isinstance(entry, RuleEntry) and not entry.has_raw
            if key in rule_lines and not is_synthesized:
                lines.append(rule_lines[key])
            else:
                lines.append(f"  {render_toml_entry(entry)},")

        for comment_block in bottom_comments:
            lines.append(comment_block)

        lines.append("]")
        lines.append("")

    # Text that followed the LAST subsection's ']' in the original file (TOO-19
    # review fix M1), e.g. a comment explaining a following [hard_deny] section.
    # Only emitted when non-empty, so a file with nothing trailing keeps ending
    # in the canonical "]\n" produced by the loop above -- no spurious blank
    # output. See parse_permissions_section_with_comments's docstring for why
    # this string alone (appended as-is, no extra separator added here) already
    # reproduces the original spacing byte-for-byte.
    trailing_comment = parsed_structure.get("trailing_comment")
    if trailing_comment:
        lines.append(trailing_comment)

    return "\n".join(lines)
