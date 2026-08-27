"""Spike C: lift heredocs blind, parse with the real grammar, ask the tree for the sink.

Two steps, cleanly separated:

1. :func:`lift_heredocs` finds each heredoc redirection with only line-oriented
   scanning plus enough quote awareness to know a ``<<`` is not sitting inside
   a quoted string, then replaces the WHOLE redirection (not just the body)
   with an opaque placeholder word. It makes no decision about who owns the
   heredoc -- that question is not asked here at all.
2. :func:`sinks` parses the cleaned text with the project's own PEG grammar
   (``toolguard.parser.bash_parser``) and IR builder (``command_model.build_ir``,
   also unmodified repo code) and looks for each placeholder inside the IR's
   ``IRSimpleCmd.text``. Whichever simple command's text contains a
   placeholder is that heredoc's sink -- read off the tree, not computed.

Only the two stages above are new logic. Everything that decides "where does
a statement end" or "what does a command word look like" is the grammar's,
not this file's.
"""

from __future__ import annotations

import re
import sys

# Not a runtime dependency of toolguard -- this is a throwaway spike script
# reaching into the real project tree for its (unmodified) grammar and IR
# modules, which are not installed as a package from this scratchpad.
_REPO_ROOT = "/home/arnon/projects/toolguard"
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from toolguard.parser import bash_parser  # noqa: E402
from toolguard.parser.command_model import (  # noqa: E402
    IRCompound,
    IRPipeline,
    IRSimpleCmd,
    IRSubshell,
    build_ir,
)

# ---------------------------------------------------------------------------
# Step 1: blind lift. The only place in this file that knows what a quote is.
# ---------------------------------------------------------------------------

#: One heredoc redirection: optional fd digits, ``<<``/``<<-``, then a
#: quoted or unquoted delimiter. Deliberately ignorant of anything else on
#: the line -- it does not need to know what a statement or a pipe is.
_HEREDOC_RE = re.compile(
    r"""
    (?P<fd>\d*)
    <<(?P<strip>-?)
    [ \t]*
    (?:
        '(?P<sq>[^']+)'
      | "(?P<dq>[^"]+)"
      | (?P<uq>[A-Za-z_][A-Za-z0-9_]*)
    )
    """,
    re.VERBOSE,
)

_PLACEHOLDER_RE = re.compile(r"__HD(\d+)__")


def _placeholder(idx: int) -> str:
    return f"__HD{idx}__"


def _quoted_positions(line: str) -> list[bool]:
    """Per-character quote state (True = inside ``'`` or ``"``), one line only.

    A ``\\`` escapes the next character everywhere except inside single
    quotes, matching bash -- so an escaped apostrophe does not flip
    unrelated ``<<`` occurrences into "quoted" the way a naive parity count
    would.
    """
    states: list[bool] = []
    in_single = False
    in_double = False
    i = 0
    n = len(line)
    while i < n:
        cur = in_single or in_double
        states.append(cur)
        ch = line[i]
        if ch == "\\" and not in_single and i + 1 < n:
            states.append(cur)
            i += 2
            continue
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return states


def _find_heredoc_specs(line: str) -> list[dict]:
    """Every unquoted heredoc redirection on *line*, left to right.

    This is the whole of what step 1 needs to know about the line's
    structure: where an unquoted ``<<`` is. It does not look at ``&&``,
    ``|``, ``;`` or ``$(...)`` at all -- those are the grammar's job in
    step 2.
    """
    quoted = _quoted_positions(line)
    specs = []
    for m in _HEREDOC_RE.finditer(line):
        if quoted[m.start()]:
            continue
        delim = m.group("sq") or m.group("dq") or m.group("uq")
        specs.append(
            {
                "start": m.start(),
                "end": m.end(),
                "delimiter": delim,
                "strip_tabs": m.group("strip") == "-",
            }
        )
    return specs


def lift_heredocs(text: str) -> tuple[str, list[str]]:
    """Replace each heredoc's redirection with an opaque placeholder word.

    Reads each heredoc body off the lines that follow its bearer line (the
    one piece of context-sensitivity a PEG grammar cannot express) and
    removes it, but decides NOTHING about which command the heredoc belongs
    to. The placeholder is a plain word with no sink information encoded in
    it -- ``__HD0__``, not ``__HEREDOC_TO_python__``.

    Args:
        text: Raw, possibly multi-line command text.

    Returns:
        ``(cleaned_text, bodies)`` -- text safe to hand to
        ``bash_parser.parse``, and each heredoc's body, indexed by the
        number in its placeholder.
    """
    lines = text.split("\n")
    out_lines: list[str] = []
    bodies: list[str] = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        specs = _find_heredoc_specs(line)
        if not specs:
            out_lines.append(line)
            i += 1
            continue

        # Bodies are read in left-to-right redirect order off one shared
        # cursor, matching the order bash itself attaches them.
        cursor = i + 1
        paired: list[tuple[dict, list[str]]] = []
        for spec in specs:
            body_lines: list[str] = []
            while cursor < n:
                check = (
                    lines[cursor].lstrip("\t") if spec["strip_tabs"] else lines[cursor]
                )
                if check == spec["delimiter"]:
                    cursor += 1
                    break
                body_lines.append(lines[cursor])
                cursor += 1
            paired.append((spec, body_lines))

        # Placeholder indices are assigned left-to-right; the line is edited
        # right-to-left so each earlier span's recorded offset stays valid.
        base_idx = len(bodies)
        modified = line
        for offset in range(len(paired) - 1, -1, -1):
            spec, _ = paired[offset]
            modified = (
                modified[: spec["start"]]
                + _placeholder(base_idx + offset)
                + modified[spec["end"] :]
            )
        bodies.extend("\n".join(body_lines) for _, body_lines in paired)

        out_lines.append(modified)
        i = cursor

    return "\n".join(out_lines), bodies


# ---------------------------------------------------------------------------
# Step 2: ask the tree. No knowledge of quotes or statement boundaries here
# at all -- the grammar already decided both.
# ---------------------------------------------------------------------------


def _sink_name(element: IRSimpleCmd) -> str:
    """The basename of the word *element* actually executes."""
    text = (
        element.assignment_prefix.without_prefix
        if element.assignment_prefix
        else element.text
    )
    tokens = text.split()
    return tokens[0].split("/")[-1] if tokens else ""


def _walk_element(element, found: dict[int, str]) -> None:
    """Record the sink for every placeholder found in *element*'s text.

    Only ``IRSimpleCmd`` and ``IRSubshell`` are followed: a heredoc inside a
    for/while/if body or a ``$(...)``/backtick substitution is out of scope
    for this spike -- see the README.
    """
    if isinstance(element, IRSimpleCmd):
        name = _sink_name(element)
        for m in _PLACEHOLDER_RE.finditer(element.text):
            found[int(m.group(1))] = name
        return
    if isinstance(element, IRSubshell):
        _walk_compound(element.inner, found)


def _walk_pipeline(pipeline: IRPipeline, found: dict[int, str]) -> None:
    for element in pipeline.elements:
        _walk_element(element, found)


def _walk_compound(compound: IRCompound, found: dict[int, str]) -> None:
    for pipeline in compound.pipelines:
        _walk_pipeline(pipeline, found)


def sinks(text: str) -> list[str]:
    """The sink command name for each heredoc in *text*, in source order.

    Args:
        text: Raw, possibly multi-line bash command text.

    Returns:
        One sink name per heredoc, ordered by the heredoc's own position in
        the source (``bash <<A <<B`` yields two entries, ``A`` first).
    """
    cleaned, bodies = lift_heredocs(text)
    tree = bash_parser.parse(cleaned)
    ir = build_ir(tree)

    found: dict[int, str] = {}
    for statement in ir.statements:
        _walk_compound(statement, found)

    return [found.get(i, "<unresolved>") for i in range(len(bodies))]
