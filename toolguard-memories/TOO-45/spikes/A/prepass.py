"""Pre-pass steps as consumers of :mod:`lexer`'s shared span stream.

Four steps, each a consumer rather than an independent quote scanner:

- :func:`join_continuations` -- backslash-newline join.
- :func:`strip_comments` -- ``#``-to-EOL comment removal.
- heredoc body lift -- :func:`_heredoc_positions` and its helpers.
- sink classification -- :func:`_classify_sink` and its helpers.

Only sink classification stays hand-written Python by design (see the spike
README); the other three are here for completeness, since they read the same
lexer output rather than inventing their own.

Statement/pipe segmentation stay simple hand-rolled scans rather than the PEG
grammar deliberately, for the same reason the module being replaced does:
this all runs *before* the grammar ever sees the text, to lift heredoc bodies
whose terminator is a context-sensitive backreference no PEG grammar (and no
canopy-generated parser) can express.
"""

import re
from typing import List, Tuple

from lexer import State, expand, scan


# ---------------------------------------------------------------------------
# Consumer 1: backslash-continuation join
# ---------------------------------------------------------------------------


def join_continuations(text: str) -> str:
    """Join backslash-continuation lines into one logical line.

    Reads :func:`lexer.scan`'s ESCAPED label: whenever the escaped character
    is a newline, both it and the backslash that escaped it (always the last
    character already emitted, by construction of the scanner) are dropped.
    """
    out: List[str] = []
    for span in scan(text):
        if span.state == State.ESCAPED and span.text == "\n":
            if out and out[-1].endswith("\\"):
                out[-1] = out[-1][:-1]
            continue
        out.append(span.text)
    return "".join(out)


# ---------------------------------------------------------------------------
# Consumer 2: comment stripping
# ---------------------------------------------------------------------------


def strip_comments(text: str) -> str:
    """Remove ``#``-to-EOL comments at word boundaries, outside quotes.

    A ``#`` starts a comment only in a PLAIN span (unquoted, unescaped) and
    only when preceded by whitespace or the start of the text -- a ``#``
    inside a word, or inside a quote, is not a comment.
    """
    states = expand(scan(text))
    out: List[str] = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if (
            states[i][0] == State.PLAIN
            and ch == "#"
            and (i == 0 or text[i - 1] in " \t\n")
        ):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


# ---------------------------------------------------------------------------
# Shared: statement and pipe segmentation
# ---------------------------------------------------------------------------

#: Mirrors bash_parser.peg's control_op alternation in membership and order --
#: `&&`/`||` must be checked before their own single-character prefix.
_CONTROL_OP_TABLE: Tuple[Tuple[str, int], ...] = (
    ("&&", 2),
    ("||", 2),
    (";", 1),
    ("&", 1),
)


def _match_control_op(text: str, i: int) -> int | None:
    for token, width in _CONTROL_OP_TABLE:
        if text.startswith(token, i):
            return width
    return None


def _statement_bounds_containing(line: str, pos: int) -> Tuple[int, int]:
    """The ``control_op``-delimited statement in *line* spanning offset *pos*.

    A boundary only counts in a PLAIN span at depth 0 -- inside a quote or an
    unquoted ``$(...)``/backtick substitution, `;`/`&`/`&&`/`||` are part of
    the substitution's own command, not a split point for this one.
    """
    flat = expand(scan(line))
    start = 0
    i = 0
    n = len(line)
    while i < n:
        state, depth = flat[i]
        if state == State.PLAIN and depth == 0:
            width = _match_control_op(line, i)
            if width is not None:
                if pos < i:
                    return start, i
                i += width
                start = i
                continue
        i += 1
    return start, n


def _pipe_segment_containing(text: str, pos: int) -> str:
    """The unquoted-`|`-delimited segment of *text* spanning offset *pos*.

    Same depth/quote rule as :func:`_statement_bounds_containing`; `||` is
    the control operator, not a pipe, and is skipped as one unit.
    """
    flat = expand(scan(text))
    start = 0
    i = 0
    n = len(text)
    while i < n:
        state, depth = flat[i]
        if state == State.PLAIN and depth == 0 and text[i] == "|":
            if i + 1 < n and text[i + 1] == "|":
                i += 2
                continue
            if pos < i:
                return text[start:i]
            i += 1
            start = i
            continue
        i += 1
    return text[start:n]


# ---------------------------------------------------------------------------
# Consumer 3: heredoc finding
# ---------------------------------------------------------------------------

#: Matches one `<<`/`<<-` heredoc operator and its delimiter, with an
#: optional leading fd number. Format-parsing only -- quote validity of the
#: match position is checked separately, against the shared scan, not by
#: this regex.
_HEREDOC_RE = re.compile(
    r"""
    (?P<fd>\d*)
    <<(?P<strip>-?)
    \s*
    (?:
        '(?P<sq_delim>[^']+)'   |
        "(?P<dq_delim>[^"]+)"   |
        (?P<uq_delim>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)


def _find_heredocs_in_line(line: str, states: List[Tuple[State, int]]) -> List[dict]:
    """Every heredoc redirection in one physical *line*.

    A candidate match is accepted only when the shared scan reports its `<<`
    as PLAIN -- replacing the quote-parity heuristic this consumer used to
    have of its own, which an embedded (non-escaped) apostrophe inside a
    double-quoted string could throw off.
    """
    specs = []
    for m in _HEREDOC_RE.finditer(line):
        delim = m.group("sq_delim") or m.group("dq_delim") or m.group("uq_delim")
        if delim is None:
            continue
        if states[m.start()][0] != State.PLAIN:
            continue
        specs.append(
            {
                "start": m.start(),
                "delimiter": delim,
                "strip_tabs": m.group("strip") == "-",
            }
        )
    return specs


def _heredoc_positions(text: str) -> List[Tuple[str, int]]:
    """Every heredoc in *text*, in source order, as (bearer_line, offset).

    Bodies are located and their line range skipped -- using the same PLAIN
    check that finds the redirect -- but not returned: sink classification
    needs only where the heredoc sits in its bearer line, not its body text.
    """
    lines = text.split("\n")
    offsets = []
    pos = 0
    for line in lines:
        offsets.append(pos)
        pos += len(line) + 1
    states = expand(scan(text))

    result: List[Tuple[str, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        line_states = states[offsets[i] : offsets[i] + len(line)]
        specs = _find_heredocs_in_line(line, line_states)
        if not specs:
            i += 1
            continue

        cursor = i + 1
        for spec in specs:
            delim = spec["delimiter"]
            strip_tabs = spec["strip_tabs"]
            while cursor < n:
                candidate = lines[cursor].lstrip("\t") if strip_tabs else lines[cursor]
                cursor += 1
                if candidate == delim:
                    break

        for spec in specs:
            result.append((line, spec["start"]))
        i = cursor

    return result


# ---------------------------------------------------------------------------
# Consumer 4: sink classification (stays hand-written Python)
# ---------------------------------------------------------------------------


def _classify_sink(segment: str) -> str:
    """The basename of the first non-flag token in a pipe segment."""
    for tok in segment.strip().split():
        basename = tok.split("/")[-1]
        if not basename.startswith("-"):
            return basename
    return "unknown"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def sinks(text: str) -> List[str]:
    """The sink command name for each heredoc in *text*, in source order."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = join_continuations(text)

    result: List[str] = []
    for line, pos in _heredoc_positions(text):
        stmt_start, stmt_end = _statement_bounds_containing(line, pos)
        statement = line[stmt_start:stmt_end]
        segment = _pipe_segment_containing(statement, pos - stmt_start)
        result.append(_classify_sink(segment))
    return result
