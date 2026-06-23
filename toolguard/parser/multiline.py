"""
Multi-line bash command pre-processing for TOO-17.

This module implements the NARROW LEXICAL PRE-PASS that normalises multi-line
bash command blobs before they are handed to the PEG parser.  It DOES NOT do
any structural parsing itself -- statement splitting, pipe splitting, and
control-structure recognition all happen in the PEG grammar
(``bash_parser.peg``) and are walked by ``command_extractor.py``.

The pre-pass handles ONLY the following steps, in order:
  1. CRLF / lone-CR -> LF.
  2. Backslash-continuation join (``\\``+LF -> empty, EXCEPT inside single
     quotes where ``\\`` is literal).
  3. Heredoc handling: detect each ``<<``/``<<-`` + delimiter; locate the body
     up to the terminator; classify the *ultimate sink* (bash-family / foreign /
     non-executor) and take the appropriate action per the design decision.
  4. Comment strip: ``#``-to-EOL at a word boundary (preceded by whitespace or
     line-start), outside quotes.
  5. Whitespace: collapse runs to a single space; trim per-statement line.

After these steps the cleaned text is handed to the PEG grammar (via
:func:`command_extractor.extract_structured_from_grammar`) for structural
parsing and structured result extraction.

Design principle: **when in doubt, ASK**.  Everything that cannot be safely
decomposed into individual simple commands resolves to an undecidable segment
rather than silently allowing an undecomposed blob.

Runtime: **standard library only** (no canopy / no external packages).
"""

import logging
import re
from typing import List

logger = logging.getLogger(__name__)

# Re-export structured result types from command_extractor so that callers
# can import them from either module (keeping backward compat with compound.py).
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
    """Replace CRLF and lone CR with LF.

    Args:
        text: Raw command text.

    Returns:
        Text with all line endings normalised to LF.
    """
    text = text.replace("\r\n", "\n")
    text = text.replace("\r", "\n")
    return text


# ---------------------------------------------------------------------------
# Step 2: Backslash-continuation join
# ---------------------------------------------------------------------------


def _join_backslash_continuations(text: str) -> str:
    r"""Join backslash-continuation lines into one logical line.

    A ``\`` immediately followed by a newline is a line-continuation in bash:
    the ``\`` and the newline are both removed, effectively concatenating the
    two physical lines (no space inserted, per bash semantics and Arnon's
    decision -- "empty join keeps tokens correct").

    Inside *single quotes* a ``\`` is literal and MUST NOT be consumed.
    Inside *double quotes* a ``\`` followed by a newline IS a continuation
    (remove it), matching bash behaviour.

    Args:
        text: LF-normalised command text.

    Returns:
        Text with ``\``+LF sequences removed (where appropriate).
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
            # Remove the backslash and the newline -- join continuation
            i += 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


# ---------------------------------------------------------------------------
# Step 3: Heredoc handling
# ---------------------------------------------------------------------------

# Regex to detect a heredoc operator on a line.
# Captures: optional fd number, <</-; optional spacing; delimiter.
# The delimiter may be single-quoted, double-quoted, or bare word.
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
    """Find all heredoc specifications in a single logical line.

    Returns a list of dicts with keys: start, end, delimiter, strip_tabs.
    start/end are character offsets within *line* of the ``<<DELIM`` token
    (including the fd number if present).

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        List of heredoc spec dicts found in the line.
    """
    specs = []
    for m in _HEREDOC_RE.finditer(line):
        delim = m.group("sq_delim") or m.group("dq_delim") or m.group("uq_delim")
        if delim is None:
            continue
        strip_tabs = m.group("strip") == "-"
        # Quick quote-context check: count unescaped single quotes before this
        # position to see if we are inside single quotes.
        before = line[: m.start()]
        if before.count("'") % 2 == 1:
            # Inside single quotes -- skip
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
    """Classify the *effective executor* of the last stage in the pipeline.

    Returns a string identifying the executor class:
    - ``'bash'``: the effective executor is a bash-family shell.
    - ``'foreign'``: the effective executor is a known foreign interpreter.
    - ``<sink_basename>``: for non-executor/unknown receivers (used in the
      heredoc sentinel ``__HEREDOC_TO_<sink>__``).

    The *effective executor* may differ from the first token when a runner
    like ``uv run <interp>`` is used: we scan all tokens of the last pipeline
    stage to find any known bash-family or foreign executor.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        ``'bash'``, ``'foreign'``, or the bare basename of the sink command.
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

    # Check each token for known executor types.
    # Bash-family takes priority over foreign (conservative).
    has_foreign = False
    for tok in tokens:
        basename = tok.split("/")[-1]
        # Skip flag-like tokens
        if basename.startswith("-"):
            continue
        if _is_bash_family(basename):
            return "bash"
        if _is_foreign_executor(basename):
            has_foreign = True

    if has_foreign:
        return "foreign"

    # No known executor -- use the first token's basename as the sink label
    return tokens[0].split("/")[-1]


def _extract_pipeline_sink(line: str) -> str:
    """Return the basename of the *effective executor* of the pipeline on *line*.

    For the heredoc sentinel ``__HEREDOC_TO_<sink>__``, we want the name that
    reflects the actual interpreter/program receiving the heredoc body.

    When a known executor (bash-family or foreign) is found in the last pipeline
    stage (e.g. ``uv run python``, ``cat <<EOF | bash``), we return THAT
    executor's basename.  This ensures the sentinel (and the ASK floor check in
    ``command_extractor.py``) uses the right name.

    Args:
        line: A single-line (no embedded newlines) command text.

    Returns:
        Basename of the effective executor, or the first token's basename if
        no known executor is found.
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

    # Prefer known executors (bash-family first, then foreign)
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

    # No known executor: use first non-flag token's basename
    for tok in tokens:
        bn = tok.split("/")[-1]
        if not bn.startswith("-"):
            return bn
    return "unknown"


def _split_on_unquoted_pipe(text: str) -> List[str]:
    """Split *text* on unquoted ``|`` characters (not ``||``).

    Quote-aware: single and double quotes protect their content.  Escapes
    inside double quotes are honoured.  ``||`` is NOT a pipe.

    Args:
        text: Text to split on unquoted pipes.

    Returns:
        List of text segments.
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
            # Consume escape and next char
            current.append(ch)
            if i + 1 < len(text):
                current.append(text[i + 1])
                i += 2
            else:
                i += 1
        elif ch == "|" and not in_single and not in_double:
            if i + 1 < len(text) and text[i + 1] == "|":
                # || operator -- not a pipe
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
    """Process heredocs in a list of logical lines.

    For each line that contains a ``<<DELIM`` heredoc operator:
    - Locate the body lines up to (and including) the terminator.
    - Classify the ultimate sink (bash-family / foreign / non-executor).
    - Replace the ``<<DELIM`` redirection with a sentinel
      ``__HEREDOC_TO_<sink>__`` for non-bash-family sinks, preserving the
      bearer command and its other args.
    - For bash-family sinks: extract the body lines and PREPEND them as new
      logical lines (so they get further pre-processing and then statement
      splitting like normal bash).
    - For foreign sinks: emit the bearer + sentinel; the ASK floor is applied
      later during resolution.
    - For non-executor sinks: emit the bearer + sentinel; normal matching.

    Args:
        lines: List of (pre-processed) logical lines (already
            CRLF-normalised and backslash-joined).

    Returns:
        New list of logical lines with heredoc bodies removed / replaced.
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

        # Process each heredoc spec in reverse order so that offsets stay valid
        # as we replace text within the line.
        modified_line = line
        extra_lines: List[str] = []  # bash-family body lines to prepend

        for spec in reversed(specs):
            delim = spec["delimiter"]
            strip_tabs = spec["strip_tabs"]

            # Find the body lines: scan forward from i+1 for the terminator.
            body_lines = []
            j = i + 1
            while j < len(lines):
                body_line = lines[j]
                # For <<- strip leading tabs from each body line and terminator
                check_line = body_line.lstrip("\t") if strip_tabs else body_line
                if check_line == delim:
                    j += 1  # consume the terminator line
                    break
                body_lines.append(body_line)
                j += 1
            # After the loop, lines[i+1:j] were the body + terminator; mark
            # them consumed by advancing i to j at the end.

            # Determine the effective executor class and sink label.
            # Use _classify_pipeline_sink to detect bash-family / foreign, which
            # handles wrappers like "uv run python" (effective executor = python).
            # Use _extract_pipeline_sink for the sentinel label (first token basename).
            sink_class = _classify_pipeline_sink(modified_line)
            # Sanitize the sink label to word-chars only: the sentinel must stay
            # all [A-Za-z0-9_] (so regex rules need no escaping) AND the ASK-floor
            # matcher in command_extractor uses ``__HEREDOC_TO_(\w+)__`` -- a dotted
            # version like ``python3.13`` must become ``python3_13`` so it still
            # matches and is still recognized as a foreign executor by prefix.
            sink_label = re.sub(
                r"[^A-Za-z0-9_]", "_", _extract_pipeline_sink(modified_line)
            )

            if sink_class == "bash":
                # Decompose the body as bash: prepend body lines
                extra_lines = body_lines + extra_lines
                # Remove the <<DELIM token from the line entirely
                modified_line = (
                    modified_line[: spec["start"]] + modified_line[spec["end"] :]
                )
            else:
                # Replace <<DELIM with sentinel; body is discarded.
                # For foreign executors the ASK floor is applied in the
                # command_extractor layer when it sees __HEREDOC_TO_<foreign>__.
                sentinel = f"__HEREDOC_TO_{sink_label}__"
                modified_line = (
                    modified_line[: spec["start"]]
                    + sentinel
                    + modified_line[spec["end"] :]
                )
            # Update i to skip the consumed body lines
            i = j

        # Emit: first any bash-family body lines, then the modified bearer line
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
    of the string (i.e. at a "word boundary" in the shell sense).  A ``#``
    embedded mid-word (e.g. in a URL ``http://x#frag``) is NOT a comment.

    Operates outside single and double quotes.

    Args:
        text: Text to strip comments from.

    Returns:
        Text with ``#``-to-EOL comment sequences removed.
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
            # Escape in double quotes: consume next char literally
            result.append(ch)
            if i + 1 < len(text):
                result.append(text[i + 1])
                i += 2
            else:
                i += 1
        elif ch == "#" and not in_single and not in_double:
            # Check word boundary: preceding char must be whitespace, or we
            # are at the start of the string.
            if i == 0 or text[i - 1] in " \t\n":
                # Skip to end of line
                while i < len(text) and text[i] != "\n":
                    i += 1
                # Keep the newline itself
            else:
                # Mid-word # -- not a comment
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
    """Collapse runs of spaces/tabs to a single space; trim per-line.

    This operates on the full pre-processed text; newlines (statement
    separators) are preserved.  The over-normalisation inside quoted strings
    is intentional and acceptable per Arnon's decision (it does not change
    approve/deny semantics in practice).

    Args:
        text: Pre-processed command text.

    Returns:
        Text with runs of horizontal whitespace collapsed.
    """
    # Collapse horizontal whitespace runs (not newlines)
    text = re.sub(r"[ \t]+", " ", text)
    # Strip leading/trailing whitespace per line
    lines = [ln.strip() for ln in text.split("\n")]
    # Remove blank lines introduced by stripping
    lines = [ln for ln in lines if ln]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main public entry point
# ---------------------------------------------------------------------------


def extract_structured(command_text: str) -> List[ExtractionResult]:
    """Pre-process and extract structured results from a (multi-line) command.

    This is the main entry point for TOO-17.  It runs the narrow lexical
    pre-pass on *command_text* and then delegates ALL structural parsing to
    the PEG grammar (via :func:`~toolguard.parser.command_extractor.extract_structured_from_grammar`).

    The pre-pass performs ONLY:
      1. CRLF / lone-CR -> LF.
      2. Backslash-continuation join.
      3. Heredoc body extraction/removal.
      4. Comment stripping.
      5. Whitespace collapse/trim.

    After the pre-pass the cleaned text is parsed by the PEG grammar (which
    handles statement splitting, pipe splitting, control-structure recognition,
    and quoted string spanning).  The tree-walker in ``command_extractor.py``
    then emits structured results.

    Design principle: **"when in doubt, ASK."**  Any segment that cannot be
    safely decomposed resolves to an :class:`UndecidableSegment` (ASK) rather
    than silently allowing an undecomposed blob.

    Args:
        command_text: Raw bash command text (possibly multi-line, CRLF, etc.).

    Returns:
        Ordered list of structured extraction results.
    """
    if not command_text or not command_text.strip():
        return []

    # Step 1: Normalise line endings
    text = _normalize_line_endings(command_text)

    # Step 2: Join backslash continuations
    text = _join_backslash_continuations(text)

    # Step 3: Heredoc handling (operates line-by-line)
    lines = text.split("\n")
    lines = _process_heredocs(lines)
    text = "\n".join(lines)

    # Step 4: Strip comments
    text = _strip_comments(text)

    # Step 5: Collapse whitespace (preserves newlines as separators)
    text = _collapse_whitespace(text)

    if not text.strip():
        return []

    # Steps 6+: Delegate to grammar-based structured extraction.
    # Parse the cleaned text with the PEG grammar and walk the tree.
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
        # Parse failure: cannot safely decompose -> ASK.
        # This is the fail-SAFE replacement for the old fail-OPEN
        # `return [command_line.strip()]` fallback.
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
