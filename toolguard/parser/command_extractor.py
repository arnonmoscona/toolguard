"""
Split a bash command line into the leaf commands a permission rule can match.

Two extractors, both over the typed IR that
:mod:`toolguard.parser.command_model` builds from the Canopy PEG parse tree.
Nothing here reads a raw Canopy node's attributes.

- :func:`extract_structured_from_grammar` takes an already-parsed tree and
  returns :class:`LeafCommand` / :class:`UndecidableSegment` objects, so a
  segment that cannot be decomposed says so instead of vanishing.
- :func:`extract_commands` parses the string itself and returns plain command
  strings. It never reports an undecidable segment, and it runs no lexical
  pre-pass.

Business policy -- what counts as foreign inline code, what earns the ASK
floor -- lives here rather than in the grammar or the IR.
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
# Structured result types
# ---------------------------------------------------------------------------


class LeafCommand(object):
    """A decomposed leaf command, ready for permission matching.

    Also indexes and iterates as the 2-tuple ``(text, ask_floor)``.

    Attributes:
        text: The command string.
        ask_floor: Set for foreign inline code and for a heredoc bound for a
            foreign sink. Nothing here decomposes such a payload: an inline
            one stays whole in *text*, while a heredoc body is already gone by
            this point, leaving only a ``__HEREDOC_TO_<sink>__`` sentinel.
    """

    __slots__ = ("text", "ask_floor")

    def __init__(self, text: str, ask_floor: bool = False) -> None:
        self.text = text
        self.ask_floor = ask_floor

    def __eq__(self, other: object) -> bool:
        if isinstance(other, LeafCommand):
            return self.text == other.text and self.ask_floor == other.ask_floor
        return NotImplemented

    def __repr__(self) -> str:
        return f"LeafCommand(text={self.text!r}, ask_floor={self.ask_floor!r})"

    def __hash__(self) -> int:
        return hash((self.text, self.ask_floor))

    def __getitem__(self, index: int):
        return (self.text, self.ask_floor)[index]

    def __iter__(self):
        return iter((self.text, self.ask_floor))


class UndecidableSegment(object):
    """A segment the extractor refused to decompose into individual commands.

    Also indexes and iterates as the 2-tuple ``(original, reason)``.

    Attributes:
        original: The undecomposed segment text.
        reason: Human-readable description of why it is undecidable.
    """

    __slots__ = ("original", "reason")

    def __init__(self, original: str, reason: str) -> None:
        self.original = original
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        if isinstance(other, UndecidableSegment):
            return self.original == other.original and self.reason == other.reason
        return NotImplemented

    def __repr__(self) -> str:
        return f"UndecidableSegment(original={self.original!r}, reason={self.reason!r})"

    def __hash__(self) -> int:
        return hash((self.original, self.reason))

    def __getitem__(self, index: int):
        return (self.original, self.reason)[index]

    def __iter__(self):
        return iter((self.original, self.reason))


#: A single element of the structured extraction result.
ExtractionResult = Union[LeafCommand, UndecidableSegment]


# ---------------------------------------------------------------------------
# Executor classification
# ---------------------------------------------------------------------------

#: Shells whose payload (``-c`` arg or heredoc body) is bash-compatible, so
#: this pipeline decomposes it instead of flooring the leaf.
BASH_FAMILY: frozenset = frozenset({"bash", "sh", "dash", "ksh", "zsh"})

#: Interpreters and non-bash shells whose inline code this pipeline cannot
#: read. A flag from :data:`_FOREIGN_INLINE_FLAGS`, or a heredoc whose sink is
#: one of these, sets ``ask_floor`` on the leaf.
#:
#: A versioned name needs its own entry unless it belongs to one of the seven
#: families :func:`_is_foreign_executor` prefix-matches -- python, pypy, node,
#: nodejs, perl, ruby, php. ``python3.13`` is covered without an entry;
#: ``Rscript4.4`` and ``gawk5`` are not covered at all.
#:
#: KNOWN LIMITATION: the list is not exhaustive, and an interpreter missing
#: from it (``lua``, ``deno``, ``bun``, ``julia``) gets no ASK floor at all,
#: so a broad allow rule would cover its inline code too.
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

#: Flags that make :func:`_detect_foreign_inline_code` treat a leaf as foreign
#: inline code, keyed by executor basename. An executor absent from this table
#: falls back to ``-c``/``-e``/``-r``, which is what makes ``csh``/``tcsh``/
#: ``fish`` work without their own entry.
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

#: Matches a short-option token that carries, or is, an inline-code flag: an
#: optional bundle of up to two other short flags, one of the letters
#: ``c``/``e``/``r``, and an optional payload attached with no separating
#: space (``-uc``, ``-cimport``, ``-c'code'``).
#:
#: It is not specific to real inline-code flags: it rejects ``-name`` but
#: matches ``-recurse`` on an incidental ``r``. :func:`_scan_for_inline_flag`
#: narrows a match by also requiring the matched letter to be one the executor
#: in hand actually uses.
#:
#: Deliberately shared rather than re-derived: ASK-floor detection and
#: outer-command extraction must recognise the same flag forms.
INLINE_FLAG_TOKEN_RE: re.Pattern = re.compile(r"^-([a-zA-Z]{0,2})([cer])(.*)$")


def _basename(name: str) -> str:
    """Return the basename (no path) of a command name."""
    return name.split("/")[-1]


def _is_bash_family(name: str) -> bool:
    """Return True if *name* names a bash-family shell. Path prefixes are stripped."""
    return _basename(name) in BASH_FAMILY


def _is_foreign_executor(name: str) -> bool:
    """Return True if *name* names a known foreign executor.

    Path prefixes are stripped, and a version suffix on one of the interpreter
    families below is accepted (``python3.11``, ``node18``) -- the suffix must
    not start with a letter, so ``pythonic`` is not a match.
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
    """Scan the tokens after a foreign executor for an inline-code flag.

    Matches an exact flag (``-c``) or one of the bundled/attached forms
    :data:`INLINE_FLAG_TOKEN_RE` recognises (``-uc``, ``-cimport``), and
    stops at the first token that does not start with ``-``: everything past
    that belongs to the script or module being run, not to the interpreter.
    That is what keeps ``python script.py -c foo`` and ``python -m mymod -c
    foo`` at False.

    KNOWN LIMITATION: a flag whose value is a separate token is
    indistinguishable from a script argument under that rule, so
    ``python -X dev -c "..."`` also scans as False. Closing it needs a
    per-executor table of which flags consume the following token.

    Args:
        remaining: Tokens following the foreign executor token.
        inline_flags: The flag strings that denote inline code for this
            executor, e.g. ``["-c"]``.

    Returns:
        True if an inline-code flag was found before the first non-flag
        token (or end of input).
    """
    # Bundled/attached forms exist only for single-letter flags, and the
    # regex knows only c/e/r.
    inline_letters = {f[1:] for f in inline_flags if len(f) == 2 and f[0] == "-"}
    for tok in remaining:
        if tok in inline_flags:
            return True
        if not tok.startswith("-"):
            return False
        match = INLINE_FLAG_TOKEN_RE.match(tok)
        if match and match.group(2) in inline_letters:
            return True
        # Any other flag (-u, -B, --long) does not end the option list.
    return False


def _detect_foreign_inline_code(cmd_text: str) -> bool:
    """Return True if *cmd_text* runs a foreign executor with an inline-code flag.

    Covers ``python3 -c "..."``, ``node -e "..."``, a wrapped executor
    (``uv run python -c "..."``), an intervening flag (``python -u -c "..."``)
    and bundled/attached flags (``python -uc "..."``, ``python -cimport os``).

    Does NOT cover code that reaches an interpreter without a flag: stdin
    (``cat prog | python``) and awk's bare program argument
    (``awk '{...}' f``) both return False.

    Args:
        cmd_text: The command text to check.

    Returns:
        True if a foreign executor appears with one of the inline-code flags
        :data:`_FOREIGN_INLINE_FLAGS` gives it.
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
    """Return the inner bash code if *cmd_text* is ``<bash-family> -c "<bash>"``.

    Only that exact shape is recognised: ``-c`` must be the second token, and
    the code must be single- or double-quoted. ``bash -x -c '...'`` and
    ``bash -c $'...'`` both return None, and the leaf then stays undecomposed
    -- matched whole, with no ASK floor, since bash is not a foreign executor.

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
        The unquoted content, or None if *text* does not open with a plain
        ``'`` or ``"`` or the quote is never closed. A ``$'...'`` opener
        returns None -- the ``$`` is not a quote character here.
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
# The SIMPLE/COMPLEX split lives here; the flags it reads
# (has_else_or_elif, has_complex_condition, body_has_nested_control) and the
# body statements are pre-computed on IRControlStructure.
# ---------------------------------------------------------------------------


def _is_posix_test(text: str) -> bool:
    """Return True if *text* is a POSIX ``[ ... ]`` test, which is not a command to check.

    ``[[ ... ]]`` is excluded: it is handled as a complex condition elsewhere.
    """
    t = text.strip()
    return t.startswith("[") and t.endswith("]") and not t.startswith("[[")


def _extract_from_body_ir(
    body_stmts_ir: List[IRCompound],
) -> List[ExtractionResult]:
    """Extract structured results from a control structure's pre-built body statements.

    Deduplicates within the body only -- the ``seen`` set is local to this
    call, so ``for i in 1 2; do ls; done; ls`` yields two ``ls`` leaves.
    """
    results: List[ExtractionResult] = []
    seen: Set[str] = set()
    for stmt_compound in body_stmts_ir:
        _structured_from_compound(stmt_compound, results, seen)
    return results


def _extract_from_do_loop_ir(ctrl: IRControlStructure) -> List[ExtractionResult]:
    """Extract structured results from a for/while/until :class:`IRControlStructure`.

    Emits the commands of the loop BODY only, and only when the body has no
    nested control structure and (for while/until) the condition avoids
    ``[[ ]]``/``(( ))``.

    The loop's own condition contributes NOTHING, even when it is an ordinary
    command that bash will run -- unlike an if condition, which
    :func:`_extract_from_if_stmt_ir` does emit. So
    ``while rm -rf /tmp/x; do :; done`` decomposes to the single leaf ``:``
    and the ``rm`` is never matched against any rule.

    Returns:
        The body's results, or a single :class:`UndecidableSegment` naming
        which guard fired.
    """
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

    Emits the condition command AND the then-body commands, but only for a
    plain if: else/elif, a nested control structure in the body, or a
    ``[[ ]]``/``(( ))`` condition each make the whole statement undecidable.
    A POSIX ``[ ... ]`` condition is dropped rather than emitted -- it is a
    test, not a command.

    Returns:
        The condition and body results, or a single
        :class:`UndecidableSegment` naming which guard fired.
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

    cond_text = ctrl.ctrl_condition_text
    if cond_text and not _is_posix_test(cond_text):
        results.append(LeafCommand(text=cond_text, ask_floor=False))

    results.extend(_extract_from_body_ir(ctrl.body_stmts_ir))

    return results


# ---------------------------------------------------------------------------
# Structured extraction: IR -> List[ExtractionResult]
# ---------------------------------------------------------------------------


def _apply_leaf_policy(cmd_text: str, seen: Set[str]) -> List[ExtractionResult]:
    """Apply the module's leaf-level business policy to one leaf command's text.

    ``<bash-family> -c "<code>"`` recurses into the inner code and yields its
    leaves instead of itself; foreign inline code and a heredoc bound for a
    foreign sink get ``ask_floor``; anything else is a plain leaf. Text
    already in *seen* yields nothing, which is why a line's result can be
    shorter than its command count.

    Args:
        cmd_text: The cleaned command text for the leaf node.
        seen: Set of already-seen texts (mutated by this function).

    Returns:
        Zero or one :class:`ExtractionResult` items -- except on the
        ``bash -c`` recursion, which returns the inner code's whole result.
    """
    if not cmd_text or cmd_text in seen:
        return []
    seen.add(cmd_text)

    inner_bash = _detect_bash_dash_c(cmd_text)
    if inner_bash is not None:
        # Local import: multiline imports this module at module scope, so the
        # pre-pass entry point is only reachable from inside a function.
        from toolguard.parser.multiline import extract_structured  # noqa: PLC0415

        return extract_structured(inner_bash)

    if _detect_foreign_inline_code(cmd_text):
        return [LeafCommand(text=cmd_text, ask_floor=True)]

    if "__HEREDOC_TO_" in cmd_text:
        m = re.search(r"__HEREDOC_TO_(\w+)__", cmd_text)
        if m and _is_foreign_executor(m.group(1)):
            return [LeafCommand(text=cmd_text, ask_floor=True)]

    return [LeafCommand(text=cmd_text, ask_floor=False)]


def _structured_from_ir_element(
    element, results: List[ExtractionResult], seen: Set[str]
) -> None:
    """Append one IR pipeline element's structured results to *results*.

    An element type not handled below contributes nothing at all, rather
    than an undecidable segment.

    A simple command's ``cmd_substs`` are not walked here, so
    ``echo $(rm -rf /)`` produces one leaf carrying the whole text and no
    separate leaf for the substitution. The command-text projection below
    does walk them; the two extractors differ on this point.
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
        # Only the inner commands: the `(...)`/`{...}` wrapper text is not
        # itself a leaf here, unlike in the extract_commands projection.
        _structured_from_compound(element.inner, results, seen)
        return


def _structured_from_pipeline(
    pipeline: IRPipeline, results: List[ExtractionResult], seen: Set[str]
) -> None:
    for element in pipeline.elements:
        _structured_from_ir_element(element, results, seen)


def _structured_from_compound(
    compound: IRCompound, results: List[ExtractionResult], seen: Set[str]
) -> None:
    for pipeline in compound.pipelines:
        _structured_from_pipeline(pipeline, results, seen)


# ---------------------------------------------------------------------------
# Public API: structured extraction
# ---------------------------------------------------------------------------


def extract_structured_from_grammar(
    tree,
) -> List[ExtractionResult]:
    """Extract structured results from an already-parsed grammar tree.

    Args:
        tree: The canopy parse tree root node (program or compound_command).

    Returns:
        Ordered list of :class:`LeafCommand` and :class:`UndecidableSegment`
        objects. Text this saw before is dropped, so ``ls && ls`` yields one
        leaf.
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
# Wider than the structured extraction above: it emits a subshell's wrapper
# text as well as its contents, and it follows $(...) substitutions, so a
# permission rule can match either form.
# ---------------------------------------------------------------------------


def _collect_commands_from_element(
    element, commands: List[str], seen: Set[str]
) -> None:
    """Append one IR pipeline element's plain command strings to *commands*.

    A subshell or brace group emits its wrapper text (``(ls -la)``), its
    inner text (``ls -la``), and then the inner compound's own commands. A
    control structure emits its whole text and nothing from inside it.
    """

    def add(text: str) -> None:
        text = text.strip()
        if text and text not in seen:
            seen.add(text)
            commands.append(text)

    if isinstance(element, IRSimpleCmd):
        add(element.text)
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
        if element.node_text:
            add(element.node_text)
        return


def _collect_commands_from_pipeline(
    pipeline: IRPipeline, commands: List[str], seen: Set[str]
) -> None:
    for element in pipeline.elements:
        _collect_commands_from_element(element, commands, seen)


def _collect_commands_from_compound(
    compound: IRCompound, commands: List[str], seen: Set[str]
) -> None:
    """Append an IR compound's command strings to *commands*.

    A ``raw_text`` -- set only on a command substitution's inner compound --
    is emitted first, so ``$(ps aux | grep python)`` contributes
    ``"ps aux | grep python"`` as well as the individual pipeline stages.
    """
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

    Splits on ``&&``, ``||``, ``;`` and ``|``, and descends into command
    substitutions (``$(...)`` and backticks), subshells and brace groups.
    A control structure contributes only its own whole text -- nothing from
    inside it.

    NO LEXICAL PRE-PASS: heredocs, comments and line continuations are not
    handled, so a multi-line blob belongs in
    :func:`toolguard.parser.multiline.extract_structured` instead. Here a
    heredoc's body lines and its terminator word each come back as commands of
    their own.

    FAILS OPEN, unlike the structured extractor: when the grammar rejects
    *command_line*, or extraction raises anything else, the whole line comes
    back as one command string. Nothing in the return value distinguishes
    that from a genuine single-command line.

    Args:
        command_line: The bash command line to parse.

    Returns:
        List of individual command strings, deduplicated, in extraction
        order. Empty for blank input.

    Examples:
        extract_commands('git status && rm -rf /')
        ['git status', 'rm -rf /']

        extract_commands('cat file | grep pattern')
        ['cat file', 'grep pattern']

        extract_commands('(ls -la)')
        ['(ls -la)', 'ls -la']
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


def parse_command_line(command_line: str) -> List[str]:
    """Alias for :func:`extract_commands`, with no behaviour of its own."""
    return extract_commands(command_line)
