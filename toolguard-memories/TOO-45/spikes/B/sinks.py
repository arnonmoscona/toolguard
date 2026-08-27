r"""Spike B: heredoc sink attribution via a small, line-scoped PEG grammar.

Companion to ``heredoc_line.peg`` / the canopy-generated ``heredoc_line.py``. The split of
responsibility is:

- **Grammar** (``heredoc_line.peg``): parses ONE physical line into commands, words,
  redirections (including ``<<``/``<<-``) and the operators connecting them. Never sees a
  heredoc body.
- **This module**: lifts heredoc bodies by line-oriented scanning (the terminator is
  context-sensitive -- captured on the bearer line, matched against later lines -- which a
  PEG cannot express without backreferences), and reads the sink from the small parse tree
  instead of re-deriving it with hand-rolled statement/pipe splitting.

Standard library only; no dependency on ``toolguard``.
"""

from __future__ import annotations

from typing import Iterator, List, NamedTuple, Optional

import heredoc_line


class _HeredocSpec(NamedTuple):
    sink: str
    delimiter: str
    strip_tabs: bool


def _delimiter_text(delimiter_node) -> str:
    """The heredoc delimiter word, with surrounding quotes (if any) removed."""
    raw = delimiter_node.text
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in ("'", '"'):
        return raw[1:-1]
    return raw


def _iter_pipeline_commands(pipeline_node) -> Iterator[object]:
    """Yield each command node of a parsed ``pipeline``, left to right."""
    yield pipeline_node.command
    for item in pipeline_node.elements[1]:
        yield item.command


def _iter_line_commands(line_node) -> Iterator[object]:
    """Yield each command node of a parsed ``line``, left to right across pipes and control ops."""
    yield from _iter_pipeline_commands(line_node.pipeline)
    for item in line_node.elements[2]:
        yield from _iter_pipeline_commands(item.pipeline)


def _command_heredocs(command_node) -> Iterator[object]:
    """Yield each heredoc redirection node attached to one command, in redirect order.

    A ``tail`` item is a heredoc when it carries both ``delimiter`` and ``strip`` -- the
    labels the grammar's ``heredoc`` rule alone produces; every other redirection or plain
    argument word lacks at least one of them.
    """
    for item in command_node.tail:
        target = item.elements[1]
        if hasattr(target, "delimiter") and hasattr(target, "strip"):
            yield target


def _line_heredoc_specs(line_text: str) -> Optional[List[_HeredocSpec]]:
    """Parse one physical line and list its heredocs, in redirect order.

    Returns ``None`` when the line does not parse at all -- treated the same as "no heredocs
    on this line" by the caller, which is the safe default (nothing gets misattributed).
    """
    try:
        tree = heredoc_line.parse(line_text)
    except heredoc_line.ParseError:
        return None

    specs = []
    for command_node in _iter_line_commands(tree):
        sink = command_node.head.text.strip().rsplit("/", 1)[-1]
        for hd in _command_heredocs(command_node):
            specs.append(
                _HeredocSpec(sink, _delimiter_text(hd.delimiter), hd.strip.text == "-")
            )
    return specs


def sinks(text: str) -> List[str]:
    """Return the sink command name for each heredoc in *text*, in source order.

    Each heredoc-bearing line is parsed by the small grammar to find which command owns its
    ``<<``; the body that follows is then skipped by plain line scanning, up to the matching
    terminator, without ever being parsed.
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    result: List[str] = []
    cursor = 0
    total = len(lines)
    while cursor < total:
        specs = _line_heredoc_specs(lines[cursor])
        if not specs:
            cursor += 1
            continue

        body_cursor = cursor + 1
        for spec in specs:
            while body_cursor < total:
                candidate = lines[body_cursor]
                check = candidate.lstrip("\t") if spec.strip_tabs else candidate
                body_cursor += 1
                if check == spec.delimiter:
                    break
            result.append(spec.sink)
        cursor = body_cursor

    return result
