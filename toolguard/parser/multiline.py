r"""
The lexical pre-pass in front of the bash PEG parser.

Normalises a raw, possibly multi-line command blob into text the grammar can
accept, then hands it over. **Structural parsing is the grammar's job**
(``bash_parser.peg``) -- statement splitting, pipe splitting,
control-structure recognition -- and hand-rolling any of it in this module is
out of bounds.

The one deviation is heredoc sink classification, which has to run before the
grammar ever sees the text: :func:`_split_on_unquoted_pipe` segments the
bearer line on ``|`` in Python, and the two sink readers tokenize that segment
themselves. That ``|``-only model is why an earlier ``&&`` can steal a later
heredoc's sink.

What is left is five lexical steps, applied in this order by
:func:`extract_structured`:

  1. CRLF / lone-CR -> LF.
  2. Backslash-continuation join -- ``\``+LF removed, except inside single
     quotes, where ``\`` is literal.
  3. Heredocs: find each ``<<``/``<<-`` and its body, classify the sink, and
     either splice the body back in as bash or replace the redirection with a
     ``__HEREDOC_TO_<sink>__`` sentinel and drop the body.
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
from typing import List

logger = logging.getLogger(__name__)

# Part re-export, part use: the F401 suppression covers the names imported
# purely so callers can take the result types from here, next to
# extract_structured.
from toolguard.parser.command_extractor import (  # noqa: E402, F401
    BASH_FAMILY,
    FOREIGN_EXECUTORS,
    LeafCommand,
    UndecidableSegment,
    ExtractionResult,
    extract_structured_from_grammar,
    _is_foreign_executor,
    _is_bash_family,
)


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


def _find_heredocs_in_line(line: str) -> List[dict]:
    """Find every heredoc redirection in a single logical line.

    A match preceded by an odd number of ``'`` characters is skipped as
    quoted. That parity count does not exclude ESCAPED quotes, so a ``\\'``
    earlier on the line flips the parity and hides every heredoc after it:
    ``echo it\\'s && cat <<EOF`` returns no specs at all, and the body lines
    then reach the grammar as ordinary statements with the terminator word
    among them.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        One dict per heredoc, in left-to-right order, with keys ``start``,
        ``end`` (offsets spanning the whole redirection), ``delimiter`` and
        ``strip_tabs``.
    """
    specs = []
    for m in _HEREDOC_RE.finditer(line):
        delim = m.group("sq_delim") or m.group("dq_delim") or m.group("uq_delim")
        if delim is None:
            continue
        strip_tabs = m.group("strip") == "-"
        before = line[: m.start()]
        if before.count("'") % 2 == 1:
            continue
        specs.append(
            {
                "start": m.start(),
                "end": m.end(),
                "delimiter": delim,
                "strip_tabs": strip_tabs,
            }
        )
    return specs


def _classify_pipeline_sink(line: str) -> str:
    """Classify what will receive a heredoc body written on *line*.

    Looks at the last ``|``-separated segment, and at every one of its tokens
    rather than just the first, so a wrapper like ``uv run python`` classifies
    as its inner interpreter and not as ``uv``. Bash-family wins over foreign
    when both appear, which decides in favour of decomposing the body.

    Two consequences worth knowing:

    - The segmentation is by ``|`` alone. ``&&``, ``||`` and ``;`` do not end
      a segment, so an executor named anywhere earlier in the line is taken
      as the sink: ``bash -c "true" && python <<EOF`` classifies as ``bash``,
      and the Python body is spliced in as bash source with no ASK floor.
    - A segment of nothing but flags falls through to ``tokens[0]``, which
      returns the flag itself -- ``'-x'``.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        ``'bash'``, ``'foreign'``, or the first token's basename for anything
        else; ``'unknown'`` when there is no token at all.
    """
    segments = _split_on_unquoted_pipe(line)
    if not segments:
        return "unknown"
    last = segments[-1].strip()
    if not last:
        return "unknown"

    tokens = last.split()
    if not tokens:
        return "unknown"

    has_foreign = False
    for tok in tokens:
        basename = tok.split("/")[-1]
        if basename.startswith("-"):
            continue
        if _is_bash_family(basename):
            return "bash"
        if _is_foreign_executor(basename):
            has_foreign = True

    if has_foreign:
        return "foreign"

    return tokens[0].split("/")[-1]


def _extract_pipeline_sink(line: str) -> str:
    """Name the sink for the ``__HEREDOC_TO_<sink>__`` sentinel.

    Same segmentation and same wrapper handling as
    :func:`_classify_pipeline_sink`, but it returns the executor's own
    basename rather than a class -- ``python3.13``, not ``foreign``. The
    sentinel has to carry a name a foreign-executor test can still recognise.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        The basename of the first bash-family token, else of the first
        foreign one, else of the first non-flag token; ``'unknown'`` when
        there is none -- including for a segment that is nothing but flags,
        where :func:`_classify_pipeline_sink` instead returns the flag.
    """
    segments = _split_on_unquoted_pipe(line)
    if not segments:
        return "unknown"
    last = segments[-1].strip()
    if not last:
        return "unknown"
    tokens = last.split()
    if not tokens:
        return "unknown"

    first_bash = None
    first_foreign = None
    for tok in tokens:
        bn = tok.split("/")[-1]
        if bn.startswith("-"):
            continue
        if first_bash is None and _is_bash_family(bn):
            first_bash = bn
        if first_foreign is None and _is_foreign_executor(bn):
            first_foreign = bn

    if first_bash is not None:
        return first_bash
    if first_foreign is not None:
        return first_foreign

    for tok in tokens:
        bn = tok.split("/")[-1]
        if not bn.startswith("-"):
            return bn
    return "unknown"


def _split_on_unquoted_pipe(text: str) -> List[str]:
    """Split *text* on unquoted ``|`` characters, treating ``||`` as one operator.

    Single and double quotes protect their content, and a ``\\`` escapes the
    next character everywhere except inside single quotes -- a stricter and
    more correct quote model than :func:`_find_heredocs_in_line`'s parity
    count.

    Args:
        text: Text to split on unquoted pipes.

    Returns:
        The segments, with their quoting and spacing intact; empty list for
        empty input.
    """
    segments = []
    current = []
    in_single = False
    in_double = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "'" and not in_double:
            in_single = not in_single
            current.append(ch)
            i += 1
        elif ch == '"' and not in_single:
            in_double = not in_double
            current.append(ch)
            i += 1
        elif ch == "\\" and (in_double or (not in_single and not in_double)):
            current.append(ch)
            if i + 1 < len(text):
                current.append(text[i + 1])
                i += 2
            else:
                i += 1
        elif ch == "|" and not in_single and not in_double:
            if i + 1 < len(text) and text[i + 1] == "|":
                current.append(ch)
                current.append(text[i + 1])
                i += 2
            else:
                segments.append("".join(current))
                current = []
                i += 1
        else:
            current.append(ch)
            i += 1
    if current or segments:
        segments.append("".join(current))
    return segments


def _process_heredocs(lines: List[str]) -> List[str]:
    """Remove heredoc bodies, splicing bash-family ones back in as source.

    For each line carrying a ``<<DELIM``: find the body up to its terminator,
    classify the sink, then either

    - **bash-family sink** -- emit the body lines ahead of the bearer, so they
      go on to be split and matched as ordinary bash, and delete the ``<<DELIM``
      from the bearer; or
    - **anything else** -- replace the ``<<DELIM`` with a
      ``__HEREDOC_TO_<sink>__`` word and discard the body unread. The bearer
      command and its other arguments survive either way.

    That sentinel is the only trace the discarded body leaves. Where the sink
    is a foreign executor, an ASK floor keyed on the sentinel stands in for
    reading it. Where it is anything else there is no floor and the body is
    simply gone: ``cat <<EOF > /etc/passwd`` becomes the leaf
    ``cat __HEREDOC_TO_cat__ > /etc/passwd`` with ``ask_floor`` unset.

    ONE HEREDOC PER LINE IS THE SUPPORTED CASE, and the second one is worth
    the paragraph because it fails quietly. The specs are walked right-to-left
    so the replacement offsets stay valid, but each terminator scan starts
    where the previous one stopped -- so the rightmost delimiter claims the
    leftmost body. ``bash <<A <<B`` over bodies ``echo from-A`` / ``echo
    from-B`` yields ``['echo from-A', 'A', 'echo from-B', 'bash']``: the
    terminator word ``A`` becomes a command of its own.

    Args:
        lines: Logical lines, already CRLF-normalised and backslash-joined.

    Returns:
        New list of logical lines with heredoc bodies removed or spliced in.
    """
    result_lines: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        specs = _find_heredocs_in_line(line)
        if not specs:
            result_lines.append(line)
            i += 1
            continue

        modified_line = line
        extra_lines: List[str] = []

        for spec in reversed(specs):
            delim = spec["delimiter"]
            strip_tabs = spec["strip_tabs"]

            body_lines = []
            j = i + 1
            while j < len(lines):
                body_line = lines[j]
                check_line = body_line.lstrip("\t") if strip_tabs else body_line
                if check_line == delim:
                    j += 1
                    break
                body_lines.append(body_line)
                j += 1
            # Running off the end without finding the terminator is not an
            # error here: the body is simply everything that was left.

            sink_class = _classify_pipeline_sink(modified_line)
            # The sentinel has to survive as one grammar word and stay
            # matchable by the ASK floor's `__HEREDOC_TO_(\w+)__`, so the
            # substitute must itself be a word character. `python3.13` becomes
            # `python3_13`, which the foreign-executor prefix test still
            # recognises.
            sink_label = re.sub(
                r"[^A-Za-z0-9_]", "_", _extract_pipeline_sink(modified_line)
            )

            if sink_class == "bash":
                extra_lines = body_lines + extra_lines
                modified_line = (
                    modified_line[: spec["start"]] + modified_line[spec["end"] :]
                )
            else:
                sentinel = f"__HEREDOC_TO_{sink_label}__"
                modified_line = (
                    modified_line[: spec["start"]]
                    + sentinel
                    + modified_line[spec["end"] :]
                )
            i = j

        result_lines.extend(extra_lines)
        stripped = modified_line.strip()
        if stripped:
            result_lines.append(stripped)

    return result_lines


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
    lines = _process_heredocs(lines)
    text = "\n".join(lines)

    text = _strip_comments(text)
    text = _collapse_whitespace(text)

    if not text.strip():
        return []

    try:
        from toolguard.parser import bash_parser  # noqa: PLC0415

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
