r"""
The lexical pre-pass in front of the bash PEG parser.

Normalises a raw, possibly multi-line command blob into text the grammar can
accept, then hands it over. **Structural parsing is the grammar's job**
(``bash_parser.peg``) -- statement splitting, pipe splitting,
control-structure recognition -- and hand-rolling any of it in this module is
out of bounds.

The one deviation is heredoc handling. A heredoc's body is context-sensitive
-- it lives on the lines AFTER its bearer, which a PEG grammar cannot express
-- so it has to be lifted out lexically before the grammar ever sees the
text (:func:`_lift_heredocs`). But WHO RECEIVES a lifted heredoc is not
lexical: :func:`_attribute_and_substitute` answers it by parsing the lifted
text with the grammar and reading which ``simple_command`` owns the
placeholder, rather than modelling statement/pipe boundaries by hand.

What is left is five lexical steps, applied in this order by
:func:`extract_structured`:

  1. CRLF / lone-CR -> LF.
  2. Backslash-continuation join -- ``\``+LF removed, except inside single
     quotes, where ``\`` is literal.
  3. Heredocs: find each ``<<``/``<<-`` and its body, classify the sink by
     parsing the lifted text and reading which command owns the placeholder,
     then either splice the body back in as bash or replace the redirection
     with a ``__HEREDOC_TO_<sink>__`` sentinel and drop the body.
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
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Re-export: the F401 suppression covers names imported purely so callers can
# take the result types from here, next to extract_structured.
from toolguard.parser.command_extractor import (  # noqa: E402, F401
    LeafCommand,
    UndecidableSegment,
    ExtractionResult,
    extract_structured_from_grammar,
    _is_foreign_executor,
    _is_bash_family,
)
from toolguard.parser import bash_parser  # noqa: E402
from toolguard.parser.command_model import (  # noqa: E402
    IRPipelineElement,
    IRSimpleCmd,
    IRSubshell,
    build_ir,
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
#: :func:`_attribute_and_substitute` always resolves every one of these before
#: returning.
_PLACEHOLDER_BASE = "__HD"


@dataclass(frozen=True)
class _LiftedHeredocs:
    """What :func:`_lift_heredocs` hands to :func:`_attribute_and_substitute`."""

    lines: List[str]
    bodies: List[List[str]]
    prefix: str


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
    :func:`_attribute_and_substitute`'s job, reading the placeholder back out
    of the returned lines.

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


class _UnattributableHeredocError(Exception):
    """A lifted placeholder could not be traced to any command in the parse tree.

    Raised rather than guessed at -- see :func:`_record_placeholder_owners`.
    The caller floors this to the ASK-inducing :class:`UndecidableSegment`,
    the same as a genuine grammar :class:`~toolguard.parser.bash_parser.ParseError`.
    """


def _sink_tokens(element: IRSimpleCmd) -> List[str]:
    """The tokens a heredoc's sink is classified from: command word onward.

    Strips a leading assignment prefix (``NAME=value python ...``), which
    names a variable, not an executor.
    """
    text = (
        element.assignment_prefix.without_prefix
        if element.assignment_prefix
        else element.text
    )
    return text.split()


def _classify_sink(tokens: List[str]) -> Tuple[bool, bool, str]:
    """Classify a command's tokens as an interpreter, or not.

    Every token is checked, not just the first, so a wrapper like ``uv run
    python`` classifies as its inner interpreter and not as ``uv``.
    Bash-family wins over foreign wherever either appears.

    Args:
        tokens: A command's tokens (:func:`_sink_tokens`).

    Returns:
        ``(is_bash_family, is_foreign, sink_label)``. *sink_label* names the
        ``__HEREDOC_TO_<sink_label>__`` sentinel when the sink is not
        bash-family: the first bash-family token if any, else the first
        foreign one, else the first non-flag token, else ``'unknown'``.
    """
    first_bash: Optional[str] = None
    first_foreign: Optional[str] = None
    first_plain: Optional[str] = None
    for tok in tokens:
        bn = tok.split("/")[-1]
        if bn.startswith("-"):
            continue
        if first_plain is None:
            first_plain = bn
        if first_bash is None and _is_bash_family(bn):
            first_bash = bn
        if first_foreign is None and _is_foreign_executor(bn):
            first_foreign = bn

    if first_bash is not None:
        return True, False, first_bash
    if first_foreign is not None:
        return False, True, first_foreign
    return False, False, first_plain or "unknown"


def _resolve_sink(
    tokens: List[str], pipeline_elements: List[IRPipelineElement]
) -> Tuple[bool, str]:
    """Resolve a heredoc's effective sink from its bearer and its pipeline.

    A bearer that is itself bash-family or foreign consumes its own heredoc
    directly as code, and wins outright even mid-pipeline: ``python <<HD |
    bash`` belongs to python, not bash (the pipe only governs python's
    stdout). A bearer that is neither, like ``cat``, merely streams the body
    on unchanged, so the pipeline's LAST element -- whoever actually
    consumes that stream -- is the real sink: ``cat <<HD | bash`` decomposes
    the body as bash, ``cat <<HD | pbcopy`` sentinels it as data.

    Args:
        tokens: The bearer's own tokens (:func:`_sink_tokens`).
        pipeline_elements: The elements of the pipeline the bearer sits in.

    Returns:
        ``(is_bash_family, sink_label)``.
    """
    is_bash, is_foreign, label = _classify_sink(tokens)
    if is_bash or is_foreign:
        return is_bash, label

    last = pipeline_elements[-1] if pipeline_elements else None
    if isinstance(last, IRSimpleCmd):
        is_bash, _, label = _classify_sink(_sink_tokens(last))
    return is_bash, label


def _record_placeholder_owners(
    element: IRPipelineElement,
    pipeline_elements: List[IRPipelineElement],
    placeholder_re: re.Pattern,
    found: Dict[int, Tuple[List[str], List[IRPipelineElement]]],
) -> None:
    """Record *element*'s tokens and pipeline against every placeholder its text contains.

    Only :class:`IRSimpleCmd` and :class:`IRSubshell` are followed. A
    placeholder inside a control structure's body (``if true; then cat
    <<HD``) or a process substitution is deliberately left unrecorded, so it
    reaches :func:`_attribute_sinks`'s caller as undecidable instead of being
    guessed at.
    """
    if isinstance(element, IRSimpleCmd):
        tokens = _sink_tokens(element)
        for m in placeholder_re.finditer(element.text):
            found[int(m.group(1))] = (tokens, pipeline_elements)
        return
    if isinstance(element, IRSubshell):
        for pipeline in element.inner.pipelines:
            for inner_element in pipeline.elements:
                _record_placeholder_owners(
                    inner_element, pipeline.elements, placeholder_re, found
                )


def _record_placeholders_in_text(
    text: str,
    placeholder_re: re.Pattern,
    found: Dict[int, Tuple[List[str], List[IRPipelineElement]]],
) -> None:
    """Parse *text* and record every placeholder's owner into *found*.

    Raises:
        bash_parser.ParseError: *text* does not parse.
    """
    tree = bash_parser.parse(text)
    ir = build_ir(tree)
    for statement in ir.statements:
        for pipeline in statement.pipelines:
            for element in pipeline.elements:
                _record_placeholder_owners(
                    element, pipeline.elements, placeholder_re, found
                )


def _attribute_sinks(
    text: str, placeholder_re: re.Pattern, count: int
) -> List[Tuple[bool, str]]:
    """Classify every lifted heredoc's sink by parsing *text* and reading its tree.

    Whichever ``simple_command`` a placeholder's text lands in owns that
    heredoc, by construction of the grammar's own pipe, control-op and
    substitution rules -- not a Python model of any of them
    (:func:`_record_placeholder_owners`); :func:`_resolve_sink` then decides
    whether that bearer or its pipeline's last stage is the effective sink.

    Requiring the WHOLE text to parse is too strong a precondition -- one
    construct the grammar does not cover, anywhere in a multi-statement blob,
    would otherwise block attribution for every heredoc in it. So a
    whole-text parse failure falls back to parsing each line on its own
    (still only ``bash_parser.parse``, never a hand-rolled boundary check);
    this is sound because :func:`_lift_heredocs` already removed every
    heredoc's body and terminator before this function ever runs, so a
    bearer line is self-contained with respect to ITS OWN heredoc syntax. A
    line that still does not parse alone -- including one that is only a
    *fragment* of a real multi-line construct, like an ``if`` missing its
    ``fi`` -- contributes no owner, which is the correct outcome: unresolved,
    not guessed.

    Args:
        text: The lifted lines, joined by newline.
        placeholder_re: Matches one placeholder, capturing its index.
        count: Total number of placeholders (``len(bodies)``).

    Returns:
        One ``(is_bash_family, sink_label)`` per placeholder index, in order.

    Raises:
        _UnattributableHeredocError: a placeholder's owning command was not
            found, even line-by-line.
    """
    found: Dict[int, Tuple[List[str], List[IRPipelineElement]]] = {}
    try:
        _record_placeholders_in_text(text, placeholder_re, found)
    except bash_parser.ParseError:
        for line in text.split("\n"):
            try:
                _record_placeholders_in_text(line, placeholder_re, found)
            except bash_parser.ParseError:
                continue

    sinks: List[Tuple[bool, str]] = []
    for idx in range(count):
        owner = found.get(idx)
        if owner is None:
            raise _UnattributableHeredocError(
                f"heredoc placeholder {idx} is not owned by any command"
            )
        sinks.append(_resolve_sink(*owner))
    return sinks


def _attribute_and_substitute(lifted: _LiftedHeredocs) -> List[str]:
    """Classify each lifted heredoc's sink and settle its placeholder.

    The sink is read off the parse tree (:func:`_attribute_sinks`), then for
    each placeholder (right-to-left within a line, so an earlier one's offset
    stays valid while a later one is edited):

    - **bash-family sink** -- emit the body lines ahead of the bearer, so they
      go on to be split and matched as ordinary bash, and delete the
      placeholder from the bearer; or
    - **anything else** -- rewrite the placeholder into a
      ``__HEREDOC_TO_<sink>__`` word and discard the body unread. The bearer
      command and its other arguments survive either way.

    That sentinel is the only trace the discarded body leaves. Where the sink
    is a foreign executor, an ASK floor keyed on the sentinel stands in for
    reading it. Where it is anything else there is no floor and the body is
    simply gone: ``cat <<EOF > /etc/passwd`` becomes the leaf
    ``cat __HEREDOC_TO_cat__ > /etc/passwd`` with ``ask_floor`` unset.

    Args:
        lifted: The lines, per-placeholder bodies and placeholder prefix
            produced by :func:`_lift_heredocs`.

    Returns:
        New list of logical lines with heredoc bodies removed or spliced in.

    Raises:
        _UnattributableHeredocError: a placeholder cannot be traced to any
            command -- the caller floors this to ASK rather than guessing.
    """
    bodies = lifted.bodies
    if not bodies:
        return lifted.lines

    placeholder_re = re.compile(re.escape(lifted.prefix) + r"(\d+)__")
    sinks = _attribute_sinks("\n".join(lifted.lines), placeholder_re, len(bodies))

    result_lines: List[str] = []
    for line in lifted.lines:
        placeholders = list(placeholder_re.finditer(line))
        if not placeholders:
            result_lines.append(line)
            continue

        modified_line = line
        extra_lines: List[str] = []

        for m in reversed(placeholders):
            idx = int(m.group(1))
            is_bash, sink_label = sinks[idx]

            if is_bash:
                extra_lines = bodies[idx] + extra_lines
                modified_line = modified_line[: m.start()] + modified_line[m.end() :]
            else:
                # The sentinel has to survive as one grammar word and stay
                # matchable by the ASK floor's `__HEREDOC_TO_(\w+)__`, so the
                # substitute must itself be a word character. `python3.13`
                # becomes `python3_13`, which the foreign-executor prefix
                # test still recognises.
                sink_word = re.sub(r"[^A-Za-z0-9_]", "_", sink_label)
                sentinel = f"__HEREDOC_TO_{sink_word}__"
                modified_line = (
                    modified_line[: m.start()] + sentinel + modified_line[m.end() :]
                )

        result_lines.extend(extra_lines)
        stripped = modified_line.strip()
        if stripped:
            result_lines.append(stripped)

    return result_lines


def _process_heredocs(lines: List[str]) -> List[str]:
    """Remove heredoc bodies, splicing bash-family ones back in as source.

    Two steps: :func:`_lift_heredocs` finds each heredoc lexically and lifts
    its body to a side table behind an opaque placeholder, deciding nothing
    about who receives it; :func:`_attribute_and_substitute` then classifies
    each placeholder's sink and settles it. See each function's own docstring
    for what it does and does not decide.

    Args:
        lines: Logical lines, already CRLF-normalised and backslash-joined.

    Returns:
        New list of logical lines with heredoc bodies removed or spliced in.
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
