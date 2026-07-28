"""
Command extraction module for bash compound commands.

This module provides functionality to extract individual commands
from compound bash command lines for security permission checking.

Uses the Canopy-generated PEG parser to walk the AST tree via the
Abstract Command Model (IR) defined in :mod:`toolguard.parser.command_model`.

ALL raw Canopy node access is isolated in :mod:`~toolguard.parser.command_model`
(:func:`~toolguard.parser.command_model.build_ir`).  This module operates
exclusively on the typed IR types.

TOO-17: Extended to handle multi-line programs.  The grammar now recognises:
  - Multiple statements separated by newlines / ``;``
  - Shell control structures (for/while/until/if/case) with both
    ``;``-delimited and newline-separated bodies
  - Process substitution ``<(...)`` / ``>(...)``
  - Trailing-operator line continuation (``&&`` / ``||`` / ``|`` + newline)

The structured extractor (``extract_structured_from_grammar``) returns a
list of :class:`LeafCommand` and :class:`UndecidableSegment` objects for
use by the compound resolution layer.  The legacy ``extract_commands``
function is preserved for backward compatibility.
"""

import logging
import re
from typing import List, Optional, Set, Union

from toolguard.parser import bash_parser
from toolguard.parser.command_model import (
    IRCompound,
    IRControlStructure,
    IRPipeline,
    IRProcSubst,
    IRSimpleCmd,
    IRSubshell,
    NodeKind,
    build_ir,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Structured result types (also imported from multiline.py for convenience)
# ---------------------------------------------------------------------------


class LeafCommand(object):
    """A fully-decomposed leaf command suitable for permission matching.

    Attributes:
        text: The command string (newline-free, whitespace-collapsed).
        ask_floor: When True the verdict for this leaf is clamped to at most
            ASK (an explicit deny still applies; a plain allow cannot downgrade
            to allow).  Used for foreign inline code and foreign heredoc sinks.
    """

    __slots__ = ("text", "ask_floor")

    def __init__(self, text: str, ask_floor: bool = False) -> None:
        """Initialise a LeafCommand.

        Args:
            text: The command string.
            ask_floor: Whether to clamp the verdict to ASK.
        """
        self.text = text
        self.ask_floor = ask_floor

    def __eq__(self, other: object) -> bool:
        """Return True if *other* is a LeafCommand with the same fields."""
        if isinstance(other, LeafCommand):
            return self.text == other.text and self.ask_floor == other.ask_floor
        return NotImplemented

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"LeafCommand(text={self.text!r}, ask_floor={self.ask_floor!r})"

    def __hash__(self) -> int:
        """Return a hash for use in sets."""
        return hash((self.text, self.ask_floor))

    # NamedTuple compatibility: support positional indexing.
    def __getitem__(self, index: int):
        """Support tuple-style indexing for backward compatibility."""
        return (self.text, self.ask_floor)[index]

    def __iter__(self):
        """Support tuple-style iteration for backward compatibility."""
        return iter((self.text, self.ask_floor))


class UndecidableSegment(object):
    """A segment that cannot be safely decomposed into individual commands.

    Resolves to ASK in the compound-resolution layer.

    Attributes:
        original: The original (pre-processed) text of the segment.
        reason: Human-readable description of why it is undecidable.
    """

    __slots__ = ("original", "reason")

    def __init__(self, original: str, reason: str) -> None:
        """Initialise an UndecidableSegment.

        Args:
            original: The original text.
            reason: Why decomposition is not possible.
        """
        self.original = original
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        """Return True if *other* is an UndecidableSegment with the same fields."""
        if isinstance(other, UndecidableSegment):
            return self.original == other.original and self.reason == other.reason
        return NotImplemented

    def __repr__(self) -> str:
        """Return a developer-friendly representation."""
        return f"UndecidableSegment(original={self.original!r}, reason={self.reason!r})"

    def __hash__(self) -> int:
        """Return a hash for use in sets."""
        return hash((self.original, self.reason))

    # NamedTuple compatibility: support positional indexing.
    def __getitem__(self, index: int):
        """Support tuple-style indexing for backward compatibility."""
        return (self.original, self.reason)[index]

    def __iter__(self):
        """Support tuple-style iteration for backward compatibility."""
        return iter((self.original, self.reason))


#: A single element of the structured extraction result.
ExtractionResult = Union[LeafCommand, UndecidableSegment]


# ---------------------------------------------------------------------------
# Executor classification (shared with multiline.py)
# ---------------------------------------------------------------------------

#: Shells whose payload (``-c`` arg or heredoc body) is bash-compatible and
#: can be decomposed by this pipeline.
BASH_FAMILY: frozenset = frozenset({"bash", "sh", "dash", "ksh", "zsh"})

#: Interpreters / non-bash shells whose inline code is foreign (not bash).
#: Any ``<foreign> -c/-e/-r "..."`` or heredoc/stdin into these triggers the
#: ASK floor (cannot be downgraded by a plain ``allow``).
#:
#: Only CANONICAL (un-versioned) names belong here. Do NOT enumerate version
#: suffixes such as ``python3.13`` / ``pypy3.11`` / ``node18``: those are matched
#: dynamically by :func:`_is_foreign_executor` via prefix, so this list never
#: needs updating for new interpreter releases (it is not year-dependent).
#:
#: KNOWN LIMITATION: this list is not exhaustive. An interpreter we do not
#: recognize (e.g. ``lua``, ``deno``, ``bun``, ``julia``) does NOT get the ASK
#: floor, so a broad ``allow`` for it would permit its inline code. The fail-safe
#: position holds (the command is still validated and an explicit ``deny`` works);
#: making this user-configurable is a deliberate YAGNI for now.
FOREIGN_EXECUTORS: frozenset = frozenset(
    {
        "python",
        "python3",
        "pypy",
        "pypy3",
        "node",
        "nodejs",
        "perl",
        "ruby",
        "php",
        "Rscript",
        "awk",
        "gawk",
        "csh",
        "tcsh",
        "fish",
    }
)

# Inline code flags per executor type.
_FOREIGN_INLINE_FLAGS = {
    "python": ["-c"],
    "python3": ["-c"],
    "node": ["-e"],
    "nodejs": ["-e"],
    "perl": ["-e"],
    "ruby": ["-e"],
    "php": ["-r"],
    "Rscript": ["-e"],
    "awk": ["-f"],
}

#: Matches a short-option token that carries (or is) an inline-code flag: an
#: optional bundle of up to two other short flags, one of the inline-code
#: letters ``c``/``e``/``r``, and an optional attached remainder (quoted or
#: bare code with no separating space, e.g. ``-cimport``, ``-c'code'``).
#: The ``{0,2}`` bound on the flag-bundle prefix is deliberate: it lets
#: combined short flags like ``-uc`` match while rejecting unrelated
#: word-like single-dash flags such as ``-name`` or ``-recurse`` (whose
#: prefix before a trailing c/e/r would be longer than 2 letters).
#:
#: TOO-19: this is the single shared definition. :mod:`toolguard.compound`
#: imports it from here (rather than each module keeping its own copy) so
#: the bundled/attached-flag matching logic used for ASK-floor *detection*
#: (this module) and for outer-command *extraction* (``compound.py``)
#: cannot drift apart.
INLINE_FLAG_TOKEN_RE: re.Pattern = re.compile(r"^-([a-zA-Z]{0,2})([cer])(.*)$")


def _basename(name: str) -> str:
    """Return the basename (no path) of a command name.

    Args:
        name: Command name, possibly with a path prefix.

    Returns:
        The basename of the command.
    """
    return name.split("/")[-1]


def _is_bash_family(name: str) -> bool:
    """Return True if *name* (basename) is a bash-family shell.

    Args:
        name: The bare command basename (no path, no arguments).

    Returns:
        True if the command is in the bash-family executor set.
    """
    return _basename(name) in BASH_FAMILY


def _is_foreign_executor(name: str) -> bool:
    """Return True if *name* (basename) is a known foreign executor.

    Handles version-suffixed names like ``python3.11``.

    Args:
        name: The bare command basename (no path, no arguments).

    Returns:
        True if the command is a known foreign interpreter / non-bash shell.
    """
    bn = _basename(name)
    if bn in FOREIGN_EXECUTORS:
        return True
    for prefix in ("python", "pypy", "node", "nodejs", "perl", "ruby", "php"):
        if bn.startswith(prefix) and (
            len(bn) == len(prefix) or not bn[len(prefix)].isalpha()
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Foreign inline code detection helpers
# ---------------------------------------------------------------------------


def _scan_for_inline_flag(remaining: List[str], inline_flags: List[str]) -> bool:
    """Scan tokens after a foreign executor for an inline-code flag.

    TOO-19: previously only ``remaining[0]`` (the single token immediately
    after the executor) was checked, which meant an intervening flag (e.g.
    ``python -u -c "..."``) or an attached/bundled flag (e.g. ``-cimport``,
    ``-uc``) silently bypassed the ASK-floor security control. This scans
    forward through any number of flag-shaped tokens, matching either an
    exact flag (e.g. ``-c``) or a bundled/attached form recognised by
    :data:`INLINE_FLAG_TOKEN_RE`.

    Scanning **stops at the first token that is not itself a flag** (does
    not start with ``-``): everything after such a token belongs to the
    script/module being invoked, not to the interpreter itself. This is what
    keeps ``python script.py -c foo`` and ``python -m mymod -c foo`` at
    ``False`` -- ``script.py`` / ``mymod`` are non-flag tokens that end the
    interpreter's own option list.

    KNOWN LIMITATION (see TOO-19 implementation report): a flag whose value
    is a SEPARATE non-flag token (e.g. Python's ``-X dev``) is
    indistinguishable, under this rule, from a script/module argument, so
    ``python -X dev -c "..."`` still scans as ``False``. Fixing that would
    require a per-executor table of which flags consume a following
    value-token without changing execution context -- judged out of scope
    here and reported as a residual gap rather than silently accepted.

    Args:
        remaining: Tokens following the foreign executor token.
        inline_flags: The exact flag strings (e.g. ``["-c"]``) that denote
            inline code for this executor.

    Returns:
        True if an inline-code flag was found before the first non-flag
        token (or end of input).
    """
    # Only single-letter flags (e.g. "-c") can appear in bundled/attached
    # form via INLINE_FLAG_TOKEN_RE (which only recognises c/e/r letters).
    inline_letters = {f[1:] for f in inline_flags if len(f) == 2 and f[0] == "-"}
    for tok in remaining:
        if tok in inline_flags:
            return True
        if not tok.startswith("-"):
            return False
        match = INLINE_FLAG_TOKEN_RE.match(tok)
        if match and match.group(2) in inline_letters:
            return True
        # Some other flag we don't specifically recognise (e.g. -u, -B, -O,
        # a long --flag) -- keep scanning, it doesn't end the option list.
    return False


def _detect_foreign_inline_code(cmd_text: str) -> bool:
    """Return True if cmd_text is a foreign executor with an inline code flag.

    Detects patterns like ``python3 -c "..."``, ``node -e "..."``,
    ``uv run python -c "..."``, and (TOO-19) forms with an intervening flag
    (``python -u -c "..."``) or a bundled/attached flag (``python -uc
    "..."``, ``python -cimport os``).

    Args:
        cmd_text: The command text to check.

    Returns:
        True if this is a foreign interpreter with an inline code flag.
    """
    tokens = cmd_text.split()
    if not tokens:
        return False
    for idx, tok in enumerate(tokens):
        bn = _basename(tok)
        if not _is_foreign_executor(bn):
            continue
        inline_flags = _FOREIGN_INLINE_FLAGS.get(bn, ["-c", "-e", "-r"])
        if _scan_for_inline_flag(tokens[idx + 1 :], inline_flags):
            return True
    return False


def _detect_bash_dash_c(cmd_text: str) -> Optional[str]:
    """Return the inner bash code if cmd_text is ``<bash-family> -c "<bash>"``.

    Args:
        cmd_text: The command text to check.

    Returns:
        The unquoted inner bash code, or None if this is not a bash -c pattern.
    """
    tokens = cmd_text.split(None, 2)
    if len(tokens) < 3:
        return None
    bn = _basename(tokens[0])
    if bn not in BASH_FAMILY:
        return None
    if tokens[1] != "-c":
        return None
    return _extract_quoted_string(tokens[2])


def _extract_quoted_string(text: str) -> Optional[str]:
    """Extract the content of a leading single- or double-quoted string.

    Args:
        text: Text starting (possibly after whitespace) with a quote.

    Returns:
        The unquoted content, or None if no clean quoted string was found.
    """
    text = text.strip()
    if not text:
        return None
    if text[0] == '"':
        i = 1
        content = []
        while i < len(text):
            ch = text[i]
            if ch == "\\" and i + 1 < len(text):
                next_ch = text[i + 1]
                if next_ch == '"':
                    content.append('"')
                    i += 2
                elif next_ch == "\n":
                    i += 2
                else:
                    content.append(ch)
                    content.append(next_ch)
                    i += 2
            elif ch == '"':
                return "".join(content)
            else:
                content.append(ch)
                i += 1
        return None
    elif text[0] == "'":
        end = text.find("'", 1)
        if end == -1:
            return None
        return text[1:end]
    return None


# ---------------------------------------------------------------------------
# Control structure helpers
#
# These helpers operate EXCLUSIVELY on IRControlStructure objects (Stage 2
# refactor: all raw Canopy node access has been moved into command_model.py).
# IRControlStructure now carries:
#   - Pre-computed complexity flags (has_else_or_elif, has_complex_condition,
#     body_has_nested_control).
#   - body_stmts_ir: pre-built List[IRCompound] for every body statement, so
#     this layer can iterate over IR without touching raw Canopy nodes.
#   - ctrl_condition_text: pre-extracted condition text (semicolons stripped).
# ---------------------------------------------------------------------------


def _is_posix_test(text: str) -> bool:
    """Return True if *text* is a POSIX ``[ ... ]`` test construct.

    These are test conditions, not commands to validate.

    Args:
        text: The condition text.

    Returns:
        True if the text is a POSIX [ ... ] test.
    """
    t = text.strip()
    return t.startswith("[") and t.endswith("]") and not t.startswith("[[")


def _extract_from_body_ir(
    body_stmts_ir: List[IRCompound],
) -> List[ExtractionResult]:
    """Extract structured results from a pre-built list of body-statement IR nodes.

    This replaces the old ``_extract_from_ctrl_body`` / ``_extract_from_ctrl_stmt``
    pair.  All raw Canopy walking has been moved to :func:`command_model._build_body_stmts_ir`;
    this function operates only on IR types.

    Args:
        body_stmts_ir: Pre-built :class:`IRCompound` list from
            :attr:`IRControlStructure.body_stmts_ir`.

    Returns:
        Ordered list of :class:`ExtractionResult` items from all body statements.
    """
    results: List[ExtractionResult] = []
    seen: Set[str] = set()
    for stmt_compound in body_stmts_ir:
        _structured_from_compound(stmt_compound, results, seen)
    return results


def _extract_from_do_loop_ir(ctrl: IRControlStructure) -> List[ExtractionResult]:
    """Extract structured results from a for/while/until :class:`IRControlStructure`.

    All complexity decisions use the pre-computed flags on *ctrl*; no raw
    Canopy node access is needed.

    Classification (SIMPLE vs COMPLEX):
      - A loop with no body statements (empty ``body_stmts_ir``) indicates
        an incomplete parse -- treat as undecidable.
      - A loop with a nested control structure in its body is COMPLEX.
      - A while/until loop with a complex condition is COMPLEX.
      - Otherwise SIMPLE: extract the inner commands from ``body_stmts_ir``.

    Args:
        ctrl: An :class:`IRControlStructure` for a for/while/until loop.

    Returns:
        List of ExtractionResult items.
    """
    # An empty body_stmts_ir with no do_clause means the loop did not parse fully.
    if not ctrl.body_stmts_ir and ctrl.do_clause is None:
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="loop parse incomplete (no do_clause found)",
            )
        ]

    if ctrl.body_has_nested_control:
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="loop with nested control structure cannot be statically decomposed",
            )
        ]

    if (
        ctrl.kind in (NodeKind.WHILE_LOOP, NodeKind.UNTIL_LOOP)
        and ctrl.has_complex_condition
    ):
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="loop condition uses [[ ]] or (( )) which cannot be statically decomposed",
            )
        ]

    return _extract_from_body_ir(ctrl.body_stmts_ir)


def _extract_from_if_stmt_ir(ctrl: IRControlStructure) -> List[ExtractionResult]:
    """Extract structured results from an if_stmt :class:`IRControlStructure`.

    All complexity decisions use the pre-computed flags on *ctrl*; no raw
    Canopy node access is needed.

    Classification (SIMPLE vs COMPLEX):
      - If the if statement has else/elif clauses -> COMPLEX -> ASK.
      - If the then-body has nested control structures -> COMPLEX -> ASK.
      - If the condition uses [[ ]] or (( )) -> COMPLEX -> ASK.
      - Otherwise SIMPLE: extract condition commands + body commands.

    Args:
        ctrl: An :class:`IRControlStructure` for an if statement.

    Returns:
        List of ExtractionResult items.
    """
    if ctrl.has_else_or_elif:
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="if statement with else/elif cannot be statically decomposed",
            )
        ]

    if ctrl.has_complex_condition:
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="if condition uses [[ ]] or (( )) which cannot be statically decomposed",
            )
        ]

    if ctrl.body_has_nested_control:
        return [
            UndecidableSegment(
                original=ctrl.node_text,
                reason="if body with nested control structure cannot be statically decomposed",
            )
        ]

    results: List[ExtractionResult] = []

    # Condition: may be a POSIX [ ... ] test (not a command) or a plain command.
    # ctrl_condition_text is pre-computed in the IR builder (semicolons stripped).
    cond_text = ctrl.ctrl_condition_text
    if cond_text and not _is_posix_test(cond_text):
        results.append(LeafCommand(text=cond_text, ask_floor=False))

    # Then-body commands: use the pre-built body_stmts_ir list.
    results.extend(_extract_from_body_ir(ctrl.body_stmts_ir))

    return results


# ---------------------------------------------------------------------------
# Structured extraction: IR -> List[ExtractionResult]
# ---------------------------------------------------------------------------


def _apply_leaf_policy(cmd_text: str, seen: Set[str]) -> List[ExtractionResult]:
    """Apply business policy to a leaf simple command text.

    Handles (in order):
    1. Deduplication via *seen*.
    2. ``bash -c "<inner>"`` recursion.
    3. Foreign inline code (ASK floor).
    4. Heredoc sentinel with foreign sink (ASK floor).
    5. Plain leaf (plain allow/deny).

    Args:
        cmd_text: The cleaned command text for the leaf node.
        seen: Set of already-seen texts (mutated by this function).

    Returns:
        A list with zero or one :class:`ExtractionResult` items.
    """
    if not cmd_text or cmd_text in seen:
        return []
    seen.add(cmd_text)

    # bash -c "..." -> decompose inner bash.
    inner_bash = _detect_bash_dash_c(cmd_text)
    if inner_bash is not None:
        from toolguard.parser.multiline import extract_structured  # noqa: PLC0415

        return extract_structured(inner_bash)

    # Foreign inline code -> ASK floor.
    if _detect_foreign_inline_code(cmd_text):
        return [LeafCommand(text=cmd_text, ask_floor=True)]

    # Heredoc sentinel with foreign sink -> ASK floor.
    if "__HEREDOC_TO_" in cmd_text:
        m = re.search(r"__HEREDOC_TO_(\w+)__", cmd_text)
        if m and _is_foreign_executor(m.group(1)):
            return [LeafCommand(text=cmd_text, ask_floor=True)]

    return [LeafCommand(text=cmd_text, ask_floor=False)]


def _structured_from_ir_element(
    element, results: List[ExtractionResult], seen: Set[str]
) -> None:
    """Extract structured results from a single IR pipeline element.

    Args:
        element: An IR pipeline element (IRSimpleCmd, IRSubshell, etc.).
        results: Accumulator for ExtractionResult items.
        seen: Set of already-seen command texts.
    """
    if isinstance(element, IRProcSubst):
        text = element.text
        if text and text not in seen:
            seen.add(text)
            results.append(
                UndecidableSegment(
                    original=text,
                    reason="process substitution <(...) or >(...) cannot be statically decomposed",
                )
            )
        return

    if isinstance(element, IRControlStructure):
        k = element.kind
        if k in (NodeKind.FOR_LOOP, NodeKind.WHILE_LOOP, NodeKind.UNTIL_LOOP):
            results.extend(_extract_from_do_loop_ir(element))
        elif k == NodeKind.IF_STMT:
            results.extend(_extract_from_if_stmt_ir(element))
        elif k == NodeKind.CASE_STMT:
            results.append(
                UndecidableSegment(
                    original=element.node_text,
                    reason="case statement cannot be statically decomposed",
                )
            )
        return

    if isinstance(element, IRSimpleCmd):
        if element.has_proc_subst:
            text = element.text
            if text and text not in seen:
                seen.add(text)
                results.append(
                    UndecidableSegment(
                        original=text,
                        reason="command contains process substitution <(...) or >(...)",
                    )
                )
            return
        results.extend(_apply_leaf_policy(element.text, seen))
        return

    if isinstance(element, IRSubshell):
        # Subshells/brace groups in structured extraction: recurse into inner.
        _structured_from_compound(element.inner, results, seen)
        return


def _structured_from_pipeline(
    pipeline: IRPipeline, results: List[ExtractionResult], seen: Set[str]
) -> None:
    """Extract structured results from an IR pipeline.

    Args:
        pipeline: An :class:`IRPipeline` to process.
        results: Accumulator for ExtractionResult items.
        seen: Set of already-seen command texts.
    """
    for element in pipeline.elements:
        _structured_from_ir_element(element, results, seen)


def _structured_from_compound(
    compound: IRCompound, results: List[ExtractionResult], seen: Set[str]
) -> None:
    """Extract structured results from an IR compound command.

    Args:
        compound: An :class:`IRCompound` to process.
        results: Accumulator for ExtractionResult items.
        seen: Set of already-seen command texts.
    """
    for pipeline in compound.pipelines:
        _structured_from_pipeline(pipeline, results, seen)


# ---------------------------------------------------------------------------
# Public API: structured extraction
# ---------------------------------------------------------------------------


def extract_structured_from_grammar(
    tree,
) -> List[ExtractionResult]:
    """Extract structured results by walking the grammar parse tree.

    Walks a ``program`` or ``compound_command`` parse tree and returns a
    list of :class:`LeafCommand` and :class:`UndecidableSegment` objects.

    This is the grammar-first structured extractor used by the compound
    resolution layer (via :func:`toolguard.parser.multiline.extract_structured`).

    All raw Canopy tree access is performed by :func:`~toolguard.parser.command_model.build_ir`;
    this function operates exclusively on the resulting IR.

    Args:
        tree: The canopy parse tree root node (program or compound_command).

    Returns:
        Ordered list of structured extraction results.
    """
    results: List[ExtractionResult] = []
    seen: Set[str] = set()
    ir = build_ir(tree)
    for statement in ir.statements:
        _structured_from_compound(statement, results, seen)
    return results


# ---------------------------------------------------------------------------
# Command text projection: IR -> List[str]
#
# This implements the semantics of the legacy _extract_from_tree, which
# includes both the wrapper text and the inner text for subshell/brace nodes.
# ---------------------------------------------------------------------------


def _collect_commands_from_element(
    element, commands: List[str], seen: Set[str]
) -> None:
    """Collect plain command strings from a single IR pipeline element.

    For subshell/brace nodes this emits:
    1. The wrapper text (e.g. ``(ls -la)``).
    2. The inner compound text (e.g. ``ls -la``) if different.
    3. Recurse into the inner compound for sub-commands.

    For simple commands it emits just the command text.

    Args:
        element: An IR pipeline element.
        commands: Accumulator list of command strings.
        seen: Set of already-seen command texts (deduplication).
    """

    def add(text: str) -> None:
        """Add *text* to *commands* if not empty and not already seen."""
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            commands.append(text)

    if isinstance(element, IRSimpleCmd):
        add(element.text)
        # Also collect any embedded command substitutions $(...)
        for subst_compound in element.cmd_substs:
            _collect_commands_from_compound(subst_compound, commands, seen)
        return

    if isinstance(element, IRSubshell):
        add(element.wrapper_text)
        add(element.inner_text)
        _collect_commands_from_compound(element.inner, commands, seen)
        return

    if isinstance(element, IRProcSubst):
        add(element.text)
        return

    if isinstance(element, IRControlStructure):
        # Control structures in extract_commands: emit text only.
        if element.node_text:
            add(element.node_text)
        return


def _collect_commands_from_pipeline(
    pipeline: IRPipeline, commands: List[str], seen: Set[str]
) -> None:
    """Collect plain command strings from an IR pipeline.

    Args:
        pipeline: An :class:`IRPipeline` to process.
        commands: Accumulator list of command strings.
        seen: Set of already-seen command texts.
    """
    for element in pipeline.elements:
        _collect_commands_from_element(element, commands, seen)


def _collect_commands_from_compound(
    compound: IRCompound, commands: List[str], seen: Set[str]
) -> None:
    """Collect plain command strings from an IR compound command.

    When *compound* has a ``raw_text`` (set for cmd_substitution inner
    compounds), that text is emitted first so that a compound like
    ``$(ps aux | grep python)`` contributes ``"ps aux | grep python"`` as
    well as the individual pipeline stages.

    Args:
        compound: An :class:`IRCompound` to process.
        commands: Accumulator list of command strings.
        seen: Set of already-seen command texts.
    """
    # Emit compound-level text for cmd_substitution inner nodes.
    if compound.raw_text:
        rt = compound.raw_text.strip()
        if rt and rt not in seen:
            seen.add(rt)
            commands.append(rt)
    for pipeline in compound.pipelines:
        _collect_commands_from_pipeline(pipeline, commands, seen)


# ---------------------------------------------------------------------------
# Public API: extract_commands and parse_command_line
# ---------------------------------------------------------------------------


def extract_commands(command_line: str) -> List[str]:
    """Extract individual commands from a compound bash command line.

    This function handles command lines with operators:
    - && (AND operator)
    - || (OR operator)
    - ; (semicolon separator)
    - | (pipe operator)

    It also extracts commands from nested constructs:
    - Command substitutions: $(...) and backticks
    - Subshells: (...)
    - Brace groups: { ...; }

    For subshell and brace-group pipeline elements the function emits both
    the wrapper text (e.g. ``(ls -la)``) and the inner command text, so that
    permission rules can match either form.

    The function uses the Canopy PEG parser to parse the command line and
    builds the Abstract Command Model (IR) via
    :mod:`toolguard.parser.command_model`.  All raw Canopy tree access is
    isolated there.

    NOTE: For multi-line commands use
    :func:`toolguard.parser.multiline.extract_structured` which runs the
    full pre-pass pipeline and then calls the grammar-based extractor.
    This function is preserved for backward compatibility with single-line
    commands.

    Args:
        command_line: The bash command line to parse.

    Returns:
        List of individual command strings.

    Examples:
        extract_commands('git status && rm -rf /')
        ['git status', 'rm -rf /']

        extract_commands('cat file | grep pattern')
        ['cat file', 'grep pattern']

        extract_commands('command1; command2; command3')
        ['command1', 'command2', 'command3']
    """
    if not command_line or not command_line.strip():
        return []

    try:
        tree = bash_parser.parse(command_line)
        ir = build_ir(tree)
        commands: List[str] = []
        seen: Set[str] = set()
        for statement in ir.statements:
            _collect_commands_from_compound(statement, commands, seen)
        return commands
    except bash_parser.ParseError as e:
        logger.warning("Parse failed for command: %s - %s", command_line[:100], e)
        return [command_line.strip()] if command_line.strip() else []
    except Exception as e:
        logger.error("Unexpected error parsing command: %s", e)
        return [command_line.strip()] if command_line.strip() else []


# Legacy compatibility - maintain old function names
def parse_command_line(command_line: str) -> List[str]:
    """Parse a bash command line and extract individual commands.

    This is a legacy compatibility function that wraps :func:`extract_commands`.
    New code should use :func:`extract_commands` directly.

    Args:
        command_line: The bash command line to parse.

    Returns:
        List of individual command strings.

    Example:
        parse_command_line('git status && rm -rf /')
        ['git status', 'rm -rf /']
        parse_command_line('cat file | grep pattern')
        ['cat file', 'grep pattern']
    """
    return extract_commands(command_line)
