r"""
The lexical pre-pass in front of the bash PEG parser.

Normalises a raw, possibly multi-line command blob into text the grammar can
accept, then hands it over. Structural parsing is the grammar's job
(``bash_parser.peg``) -- statement splitting, pipe splitting,
control-structure recognition -- and hand-rolling any of it in this module is
out of bounds.

A heredoc's body is context-sensitive -- it lives on the lines AFTER its
bearer, which a PEG grammar cannot express -- so it has to be lifted out
lexically before the grammar ever sees the text (:func:`_lift_heredocs`).
The lift is blind to WHO RECEIVES it: it replaces each redirection with an
opaque placeholder and hands the placeholder-bearing lines, plus the lifted
bodies, to :mod:`toolguard.parser.command_extractor`, which reads which
``simple_command`` owns each placeholder off the parse tree and settles it
-- structural work, done where the module already interprets the tree.

What is left here is five lexical steps, applied in this order by
:func:`extract_structured`:

  1. CRLF / lone-CR -> LF.
  2. Backslash-continuation join -- ``\``+LF removed, except inside single
     quotes, where ``\`` is literal.
  3. Heredocs: find each ``<<``/``<<-`` and its body, and lift the body to a
     side table behind an opaque placeholder (:func:`_lift_heredocs`) --
     :mod:`~toolguard.parser.command_extractor` then resolves each
     placeholder and hands back the settled lines.
  4. Comment strip: ``#``-to-EOL at a word boundary, outside quotes.
  5. Whitespace: collapse horizontal runs, trim each line, drop blank lines.

The quote scanners across steps 2-4 do not agree; each documents its own
model. Step 5 ignores quoting altogether.

Design principle: **when in doubt, ASK**. A blob that cannot be safely
decomposed becomes an :class:`UndecidableSegment` rather than being passed
through whole.
"""

import logging
import re
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Re-export: the F401 suppression covers names imported purely so callers can
# take the result types from here, next to extract_structured.
from toolguard.parser.command_extractor import (  # noqa: E402, F401
    LeafCommand,
    UndecidableSegment,
    ExtractionResult,
    extract_structured_from_grammar,
)

# Used directly below, not merely re-exported: the lift here mints
# _LiftedHeredocs, and _process_heredocs hands it to command_extractor's
# sink attribution across the module boundary.
from toolguard.parser.command_extractor import (  # noqa: E402
    _LiftedHeredocs,
    _UnattributableHeredocError,
    _attribute_and_substitute,
)
from toolguard.parser import bash_parser  # noqa: E402


# ---------------------------------------------------------------------------
# Step 1: CRLF normalisation
# ---------------------------------------------------------------------------


def _normalize_line_endings(text: str) -> str:
    """Replace CRLF and lone CR with LF."""
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


# ---------------------------------------------------------------------------
# Step 2: Backslash-continuation join
# ---------------------------------------------------------------------------


def _join_backslash_continuations(text: str) -> str:
    r"""Join backslash-continuation lines into one logical line.

    A ``\`` immediately followed by a newline is a line-continuation in bash:
    both characters are removed and the two physical lines are concatenated
    with nothing between them, which is what keeps a token split across the
    continuation intact.

    Inside single quotes a ``\`` is literal, so it is left alone; inside
    double quotes it is still a continuation, so it is removed.

    KNOWN LIMITATION: the scan tracks single quotes with no notion of being
    inside double quotes, so an apostrophe in a double-quoted string flips it
    into "in single quotes". A continuation after ``echo "don't"`` is then
    left un-joined -- and its newline survives into the grammar -- until some
    later ``'`` happens to flip the state back.

    Args:
        text: LF-normalised command text.

    Returns:
        Text with ``\``+LF sequences removed where the scan considers itself
        outside single quotes.
    """
    result = []
    in_single = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_single:
            in_single = True
            result.append(ch)
            i += 1
        elif ch == "'" and in_single:
            in_single = False
            result.append(ch)
            i += 1
        elif ch == "\\" and not in_single and i + 1 < len(text) and text[i + 1] == "\n":
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Step 3: Heredoc handling
# ---------------------------------------------------------------------------

#: Matches one ``<<``/``<<-`` heredoc operator and its delimiter, with an
#: optional leading fd number. The span it reports covers the whole
#: redirection, which is what :func:`_process_heredocs` cuts out and replaces.
_HEREDOC_RE = re.compile(
    r"""
    (?P<fd>\d*)          # optional fd redirect number
    <<(?P<strip>-?)      # << or <<-
    \s*                  # optional whitespace before delimiter
    (?:
        '(?P<sq_delim>[^']+)'   |   # single-quoted delimiter
        "(?P<dq_delim>[^"]+)"   |   # double-quoted delimiter
        (?P<uq_delim>[A-Za-z_][A-Za-z0-9_]*)  # unquoted delimiter
    )
    """,
    re.VERBOSE,
)


def _unescaped_count(line: str, quote_char: str) -> int:
    """Count occurrences of *quote_char* in *line* not preceded by a ``\\``."""
    count = 0
    i = 0
    n = len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n:
            i += 2
            continue
        if line[i] == quote_char:
            count += 1
        i += 1
    return count


def _line_quote_states(line: str) -> List[bool]:
    """Per-character quote state for one line (True = inside ``'`` or ``"``).

    This function has no memory of any OTHER line, so it cannot tell a ``"``
    that opens a double-quoted string from one that closes a string opened on
    a previous physical line. Tracking double quotes is therefore trusted
    only when they are locally balanced (an even, unescaped count on this
    line) -- an apostrophe embedded in a double-quoted string that opens and
    closes on the SAME line, ``echo "it's"``, is then correctly left alone,
    while a line-leading ``"`` that really closes a multi-line string (seen
    on real traffic) does not wrongly poison the rest of the line. When
    double quotes are not trusted, a ``"`` is inert and only single-quote
    state is tracked -- escape-aware, so a ``\\'`` does not flip it either.
    """
    trust_double_quotes = _unescaped_count(line, '"') % 2 == 0

    states: List[bool] = []
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
        elif trust_double_quotes and ch == '"' and not in_single:
            in_double = not in_double
        i += 1
    return states


def _find_heredocs_in_line(line: str) -> List[dict]:
    """Find every heredoc redirection in a single logical line.

    A match starting inside a quoted region (:func:`_line_quote_states`) is
    skipped.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        One dict per heredoc, in left-to-right order, with keys ``start``,
        ``end`` (offsets spanning the whole redirection), ``delimiter`` and
        ``strip_tabs``.
    """
    quoted = _line_quote_states(line)
    specs = []
    for m in _HEREDOC_RE.finditer(line):
        delim = m.group("sq_delim") or m.group("dq_delim") or m.group("uq_delim")
        if delim is None:
            continue
        if quoted[m.start()]:
            continue
        strip_tabs = m.group("strip") == "-"
        specs.append(
            {
                "start": m.start(),
                "end": m.end(),
                "delimiter": delim,
                "strip_tabs": strip_tabs,
            }
        )
    return specs


#: Base spelling of the internal, sink-blind stand-in for one lifted heredoc
#: redirection. Never observable outside this module --
#: :mod:`~toolguard.parser.command_extractor` always resolves every one of
#: these before handing the settled lines back.
_PLACEHOLDER_BASE = "__HD"


def _placeholder_prefix(lines: List[str]) -> str:
    """A placeholder prefix that appears nowhere in *lines*, so input cannot forge one.

    A command may legitimately carry the placeholder's own spelling --
    ``echo __HD0__`` -- and a forged placeholder would otherwise be resolved
    against the body table, crashing on an index that was never minted or
    stealing a real heredoc's body.
    """
    joined = "\n".join(lines)
    prefix = _PLACEHOLDER_BASE
    while prefix in joined:
        prefix += "X"
    return prefix


def _placeholder(prefix: str, idx: int) -> str:
    return f"{prefix}{idx}__"


def _lift_heredocs(lines: List[str]) -> _LiftedHeredocs:
    """Replace each heredoc redirection with an opaque placeholder, blind to its sink.

    For each line, finds its heredoc specs (:func:`_find_heredocs_in_line`),
    reads each one's body off the following lines, and substitutes a
    placeholder word for the WHOLE redirection -- not just the body. Makes no
    decision about which command receives the heredoc; that is
    :mod:`~toolguard.parser.command_extractor`'s job, reading the placeholder
    back out of the returned lines.

    Multiple heredocs on one line share one forward-advancing line cursor, in
    left-to-right redirect order -- the order bash attaches them in. Each
    line's specs are substituted right-to-left so an earlier spec's recorded
    offset into the line stays valid while a later one is edited.

    Args:
        lines: Logical lines, already CRLF-normalised and backslash-joined.

    Returns:
        The line list with each heredoc redirection replaced by a
        placeholder, the raw body lines per placeholder in the placeholder's
        own left-to-right, top-to-bottom order, and the prefix those
        placeholders were minted with. Lines are otherwise untouched: no
        stripping, no splicing -- that is the next step's job.
    """
    prefix = _placeholder_prefix(lines)
    result_lines: List[str] = []
    bodies: List[List[str]] = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        specs = _find_heredocs_in_line(line)
        if not specs:
            result_lines.append(line)
            i += 1
            continue

        # Each spec is paired with its own body as soon as the body is read,
        # so the two never become independently-indexed sequences.
        paired: List[Tuple[dict, List[str]]] = []
        cursor = i + 1
        for spec in specs:
            delim = spec["delimiter"]
            strip_tabs = spec["strip_tabs"]

            body_lines: List[str] = []
            while cursor < n:
                body_line = lines[cursor]
                check_line = body_line.lstrip("\t") if strip_tabs else body_line
                if check_line == delim:
                    cursor += 1
                    break
                body_lines.append(body_line)
                cursor += 1
            # Running off the end without finding the terminator is not an
            # error here: the body is simply everything that was left.
            paired.append((spec, body_lines))

        base_idx = len(bodies)
        modified_line = line
        for offset in range(len(paired) - 1, -1, -1):
            spec, _ = paired[offset]
            modified_line = (
                modified_line[: spec["start"]]
                + _placeholder(prefix, base_idx + offset)
                + modified_line[spec["end"] :]
            )
        bodies.extend(body_lines for _, body_lines in paired)

        result_lines.append(modified_line)
        i = cursor

    return _LiftedHeredocs(lines=result_lines, bodies=bodies, prefix=prefix)


def _process_heredocs(lines: List[str]) -> List[str]:
    """Lift heredoc bodies, then hand off for sink attribution and settlement.

    :func:`_lift_heredocs` finds each heredoc lexically and lifts its body to
    a side table behind an opaque placeholder, deciding nothing about who
    receives it. :mod:`~toolguard.parser.command_extractor` then reads the
    lifted text's parse tree to classify each placeholder's sink and settle
    it -- see each function's own docstring for what it does and does not
    decide.

    Args:
        lines: Logical lines, already CRLF-normalised and backslash-joined.

    Returns:
        New list of logical lines with heredoc bodies removed or spliced in.

    Raises:
        _UnattributableHeredocError: a placeholder cannot be traced to any
            command -- the caller floors this to ASK rather than guessing.
    """
    return _attribute_and_substitute(_lift_heredocs(lines))


# ---------------------------------------------------------------------------
# Step 4: Comment stripping
# ---------------------------------------------------------------------------


def _strip_comments(text: str) -> str:
    """Remove ``#``-to-EOL comments at word boundaries, outside quotes.

    A ``#`` starts a comment only when preceded by whitespace or at the start
    of the string. A ``#`` mid-word -- a URL fragment, ``http://x#frag`` --
    is not a comment, and neither is one inside single or double quotes.

    Args:
        text: Text to strip comments from.

    Returns:
        Text with comment runs removed. Newlines are preserved, so line
        structure survives; the whitespace a comment left behind does not get
        trimmed here.
    """
    result = []
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            result.append(ch)
            i += 1
        elif ch == '"' and not in_single:
            in_double = not in_double
            result.append(ch)
            i += 1
        elif ch == "\\" and in_double:
            result.append(ch)
            if i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                i += 1
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or text[i - 1] in " \t\n":
                while i < len(text) and text[i] != "\n":
                    i += 1
                # The newline is left for the caller: it is a statement
                # separator, not part of the comment.
            else:
                result.append(ch)
                i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Step 5: Whitespace collapse
# ---------------------------------------------------------------------------


def _collapse_whitespace(text: str) -> str:
    """Collapse horizontal whitespace runs, trim each line, drop blank lines.

    Newlines survive: they are the statement separators the grammar splits on.

    No quote awareness at all -- unlike every other step here. ``echo 'a    b'``
    becomes ``echo 'a b'``, changing a string the command would have received
    verbatim. Accepted deliberately, on the grounds that it does not change
    approve/deny outcomes in practice.

    Args:
        text: Pre-processed command text.

    Returns:
        Text with horizontal whitespace collapsed and empty lines removed.
    """
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln.strip() for ln in text.split("\n")]
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------


def extract_structured(command_text: str) -> List[ExtractionResult]:
    """Pre-process a raw command blob and extract its structured results.

    The module's entry point: runs the five pre-pass steps in the module
    docstring, then hands the cleaned text to the grammar.

    Note what the caller receives on failure. A grammar ParseError -- or any
    other exception out of extraction -- yields a single
    :class:`UndecidableSegment` covering the whole CLEANED text, never the
    original, and never a bare passthrough of the input as a command. The
    caller's undecidable floor is then what decides the verdict.

    Args:
        command_text: Raw bash command text, possibly multi-line, CRLF, with
            heredocs and comments.

    Returns:
        Ordered list of structured extraction results; empty for blank input
        and for input that the pre-pass reduces to nothing.
    """
    if not command_text or not command_text.strip():
        return []

    text = _normalize_line_endings(command_text)
    text = _join_backslash_continuations(text)

    # Heredoc handling is the one step that needs whole lines rather than a
    # character stream: a heredoc's body lives on the lines AFTER its bearer.
    lines = text.split("\n")
    try:
        lines = _process_heredocs(lines)
    except _UnattributableHeredocError as e:
        logger.warning(
            "Heredoc sink attribution failed for command (after pre-pass): %s - %s",
            text[:100],
            e,
        )
        return [
            UndecidableSegment(
                original=text.strip(),
                reason=f"heredoc sink could not be attributed: {e}",
            )
        ]
    text = "\n".join(lines)

    text = _strip_comments(text)
    text = _collapse_whitespace(text)

    if not text.strip():
        return []

    try:
        tree = bash_parser.parse(text)
        return extract_structured_from_grammar(tree)
    except bash_parser.ParseError as e:
        logger.warning(
            "Grammar parse failed for command (after pre-pass): %s - %s",
            text[:100],
            e,
        )
        return [
            UndecidableSegment(
                original=text.strip(),
                reason="command did not parse; cannot safely decompose",
            )
        ]
    except Exception as e:
        logger.error("Unexpected error in grammar extraction: %s", e)
        return [
            UndecidableSegment(
                original=text.strip(),
                reason=f"unexpected extraction error: {e}",
            )
        ]
