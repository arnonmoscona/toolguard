"""The one quote-aware scanner every pre-pass consumer in this spike reads.

:func:`scan` walks *text* once, left to right, and produces a flat list of
:class:`Span` objects: contiguous runs that share the same quote state and
the same ``$(...)``/backtick nesting depth. Every consumer downstream
(continuation-join, comment-strip, heredoc-finding, statement/pipe
segmentation) reads spans instead of re-deriving quote or nesting state on
its own -- this file is the single place that decides what a quote is.

State model: bash quoting has three persistent contexts -- SINGLE, DOUBLE,
and PLAIN (top level) -- plus one instantaneous label, ESCAPED, for the one
character immediately following an escaping backslash. A backslash escapes
the next character in PLAIN or DOUBLE context; inside SINGLE it is literal.
An escaped character never toggles the surrounding context (an escaped quote
does not open or close a string).

``depth`` counts unquoted ``$(...)``/backtick nesting. It only advances while
context is PLAIN: a ``$(`` written inside a double-quoted string still starts
a real substitution in bash, but nothing this pre-pass does needs to see past
a quote to find a statement or pipe boundary, so depth is simply held
constant through SINGLE/DOUBLE spans and resumes on return to PLAIN. This
matches the pre-existing behaviour of the module being replaced.
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple


class State(Enum):
    PLAIN = "plain"
    SINGLE = "single"
    DOUBLE = "double"
    ESCAPED = "escaped"


@dataclass(frozen=True)
class Span:
    """A maximal run of *text* sharing one (state, depth) pair."""

    start: int
    end: int  # exclusive
    text: str
    state: State
    depth: int  # $(...)/backtick nesting depth; 0 = top level
    line: int  # 0-based physical line number of `start`


def _char_states(text: str) -> List[Tuple[State, int]]:
    """One ``(State, depth)`` pair per character of *text*, left to right."""
    out: List[Tuple[State, int]] = []
    context = State.PLAIN
    depth = 0
    subst_stack: List[str] = []  # 'P' for an open $(, 'B' for an open backtick
    i = 0
    n = len(text)

    while i < n:
        ch = text[i]

        if context == State.SINGLE:
            out.append((State.SINGLE, depth))
            if ch == "'":
                context = State.PLAIN
            i += 1
            continue

        if ch == "\\" and context in (State.PLAIN, State.DOUBLE):
            out.append((context, depth))
            i += 1
            if i < n:
                out.append((State.ESCAPED, depth))
                i += 1
            continue

        if context == State.DOUBLE:
            out.append((State.DOUBLE, depth))
            if ch == '"':
                context = State.PLAIN
            i += 1
            continue

        # context is PLAIN, and ch is not an escaping backslash.
        if ch == "'":
            context = State.SINGLE
            out.append((State.SINGLE, depth))
            i += 1
        elif ch == '"':
            context = State.DOUBLE
            out.append((State.DOUBLE, depth))
            i += 1
        elif ch == "$" and i + 1 < n and text[i + 1] == "(":
            subst_stack.append("P")
            depth = len(subst_stack)
            out.append((State.PLAIN, depth))
            i += 1
        elif ch == ")" and subst_stack and subst_stack[-1] == "P":
            out.append((State.PLAIN, depth))
            subst_stack.pop()
            depth = len(subst_stack)
            i += 1
        elif ch == "`":
            if subst_stack and subst_stack[-1] == "B":
                out.append((State.PLAIN, depth))
                subst_stack.pop()
                depth = len(subst_stack)
            else:
                subst_stack.append("B")
                depth = len(subst_stack)
                out.append((State.PLAIN, depth))
            i += 1
        else:
            out.append((State.PLAIN, depth))
            i += 1

    return out


def _line_numbers(text: str) -> List[int]:
    """0-based physical line number for every character of *text*."""
    lines = [0] * len(text)
    line = 0
    for i, ch in enumerate(text):
        lines[i] = line
        if ch == "\n":
            line += 1
    return lines


def scan(text: str) -> List[Span]:
    """Scan *text* once into quote/escape/depth-annotated spans."""
    if not text:
        return []

    char_states = _char_states(text)
    lines = _line_numbers(text)
    spans: List[Span] = []
    span_start = 0
    cur_state, cur_depth = char_states[0]

    for i in range(1, len(text)):
        state, depth = char_states[i]
        if (state, depth) != (cur_state, cur_depth):
            spans.append(
                Span(
                    span_start,
                    i,
                    text[span_start:i],
                    cur_state,
                    cur_depth,
                    lines[span_start],
                )
            )
            span_start = i
            cur_state, cur_depth = state, depth

    spans.append(
        Span(
            span_start,
            len(text),
            text[span_start:],
            cur_state,
            cur_depth,
            lines[span_start],
        )
    )
    return spans


def expand(spans: List[Span]) -> List[Tuple[State, int]]:
    """Flatten spans back to one (state, depth) pair per character.

    Pure re-derivation from spans :func:`scan` already computed -- no new
    quote logic, just O(1) per-position lookup for consumers that scan for a
    specific character (a control operator, a pipe, a ``#``) rather than
    walking span by span.
    """
    out: List[Tuple[State, int]] = []
    for span in spans:
        out.extend([(span.state, span.depth)] * (span.end - span.start))
    return out
