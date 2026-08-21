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
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set, Union

from toolguard.config_types import CommandSpellings
from toolguard.parser import bash_parser
from toolguard.parser.command_model import (
    IRAssignmentPrefix,
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
#: read. Inline code per :data:`_EXECUTOR_FLAGS`, or a heredoc whose sink is
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


@dataclass(frozen=True)
class _ExecutorFlags:
    """How one foreign executor spells "the program is on the command line".

    Attributes:
        inline_letters: Short-flag letters introducing inline code. Recognised
            bundled and with the code attached (``-uc``, ``-cimport os``).
        inline_long: Long flags introducing inline code, matched with or
            without an ``=value`` payload (``--eval``, ``--eval=code``).
        value_letters: Short flags whose value may be a SEPARATE token, so the
            scan must step over that token rather than stop at it. A letter
            listed here wrongly hides any inline flag behind it, so add one
            only when the separate-token form is real.
        program_file_letters: Short flags naming a program FILE -- the opposite
            of inline code. Seeing one settles the question for
            *bare_program* executors.
        bare_program: The first non-flag argument is the program itself, as in
            ``awk '{print $1}' file``.
    """

    inline_letters: frozenset = frozenset()
    inline_long: frozenset = frozenset()
    value_letters: frozenset = frozenset()
    program_file_letters: frozenset = frozenset()
    bare_program: bool = False


_PYTHON_FLAGS = _ExecutorFlags(
    inline_letters=frozenset("c"), value_letters=frozenset("XW")
)
_NODE_FLAGS = _ExecutorFlags(
    inline_letters=frozenset("ep"),
    inline_long=frozenset({"--eval", "--print"}),
    value_letters=frozenset("r"),
)
_PERL_FLAGS = _ExecutorFlags(
    inline_letters=frozenset("eE"), value_letters=frozenset("I")
)
_RUBY_FLAGS = _ExecutorFlags(
    inline_letters=frozenset("e"), value_letters=frozenset("IEC")
)
_PHP_FLAGS = _ExecutorFlags(
    inline_letters=frozenset("rRBE"),
    value_letters=frozenset("d"),
    program_file_letters=frozenset("F"),
)
_RSCRIPT_FLAGS = _ExecutorFlags(inline_letters=frozenset("e"))
_AWK_FLAGS = _ExecutorFlags(
    value_letters=frozenset("vF"),
    program_file_letters=frozenset("f"),
    bare_program=True,
)

#: Fallback for a foreign executor with no entry of its own -- ``csh``,
#: ``tcsh``, ``fish`` and anything added to :data:`FOREIGN_EXECUTORS` without a
#: spec. Deliberately broad: a missing letter is a missing ASK floor.
_DEFAULT_EXECUTOR_FLAGS = _ExecutorFlags(inline_letters=frozenset("cer"))

#: Per-executor flag specs, keyed by basename. Looked up by exact basename
#: first, then by the interpreter family :func:`_is_foreign_executor`
#: prefix-matches, so ``python3.13`` and ``pypy3`` reach the python spec.
_EXECUTOR_FLAGS = {
    "python": _PYTHON_FLAGS,
    "pypy": _PYTHON_FLAGS,
    "node": _NODE_FLAGS,
    "nodejs": _NODE_FLAGS,
    "perl": _PERL_FLAGS,
    "ruby": _RUBY_FLAGS,
    "php": _PHP_FLAGS,
    "Rscript": _RSCRIPT_FLAGS,
    "awk": _AWK_FLAGS,
    "gawk": _AWK_FLAGS,
}

#: Commands that run another command given as their arguments, so a foreign
#: executor after one of these is still executed. Without this list every token
#: would have to be tried as an executor, which flags ``grep python -c file``.
#:
#: KNOWN LIMITATION: a wrapper missing from the list hides the executor behind
#: it, and one leaf's inline code then gets no ASK floor.
COMMAND_WRAPPERS: frozenset = frozenset(
    {
        "command",
        "doas",
        "env",
        "exec",
        "nice",
        "nohup",
        "npx",
        "pipenv",
        "poetry",
        "stdbuf",
        "sudo",
        "time",
        "timeout",
        "uv",
        "uvx",
        "watch",
        "xargs",
    }
)

#: Matches a ``NAME=value`` assignment prefix, which precedes the command word
#: rather than being it (``TG_ATTEST_READONLY=1 python -c ...``).
_ASSIGNMENT_TOKEN_RE: re.Pattern = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

#: Matches a short-option token that carries, or is, an inline-code flag: an
#: optional bundle of other short flags, one of the letters ``c``/``e``/``r``,
#: and an optional payload attached with no separating space (``-uc``,
#: ``-cimport``, ``-c'code'``). The bundle is lazy so the first matching
#: letter wins, which is what keeps ``-cimport`` split as ``-c`` + ``import``.
#:
#: It is not specific to real inline-code flags: it matches ``-name`` on the
#: trailing ``e``. Used only to find where the flag ends so the payload can be
#: dropped from the outer-command stub, never to decide the ASK floor.
INLINE_FLAG_TOKEN_RE: re.Pattern = re.compile(r"^-([a-zA-Z]*?)([cer])(.*)$")


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


def _flags_for(name: str) -> _ExecutorFlags:
    """Return the :class:`_ExecutorFlags` for executor *name*.

    Tries the exact basename, then the interpreter family it belongs to, then
    :data:`_DEFAULT_EXECUTOR_FLAGS`.
    """
    bn = _basename(name)
    spec = _EXECUTOR_FLAGS.get(bn)
    if spec is not None:
        return spec
    for family, family_spec in _EXECUTOR_FLAGS.items():
        if bn.startswith(family) and not bn[len(family) :][:1].isalpha():
            return family_spec
    return _DEFAULT_EXECUTOR_FLAGS


def _executor_index(tokens: List[str]) -> Optional[int]:
    """Return the index of the foreign executor *tokens* actually runs, or None.

    Only the command word counts, plus a command word reached through
    ``NAME=value`` assignments and :data:`COMMAND_WRAPPERS` -- so
    ``timeout 5 python -c`` and ``env X=1 python -c`` are found while
    ``grep python -c file``, where the interpreter is merely an argument, is
    not. Everything after a wrapper is searched, since a wrapper's own
    arguments cannot be told from the command it wraps.
    """
    after_wrapper = False
    for idx, tok in enumerate(tokens):
        bn = _basename(tok)
        if _is_foreign_executor(bn):
            return idx
        if after_wrapper:
            continue
        if bn in COMMAND_WRAPPERS:
            after_wrapper = True
            continue
        if not _ASSIGNMENT_TOKEN_RE.match(tok):
            return None
    return None


def _scan_for_inline_code(remaining: List[str], spec: _ExecutorFlags) -> bool:
    """Scan the tokens after a foreign executor for inline code.

    Walks the option list, stepping over a flag whose value is a separate
    token, and stops at the first token that is neither -- everything past
    that belongs to the script or module being run, not to the interpreter.
    That is what keeps ``python script.py -c foo`` and ``python -m mymod -c
    foo`` at False.

    Args:
        remaining: Tokens following the foreign executor token.
        spec: The executor's flag spec.

    Returns:
        True if the executor was given inline code.
    """
    program_from_file = False
    idx = 0
    while idx < len(remaining):
        tok = remaining[idx]
        if not tok.startswith("-") or tok == "-":
            return spec.bare_program and not program_from_file
        if tok.startswith("--"):
            if tok.split("=", 1)[0] in spec.inline_long:
                return True
            idx += 1
            continue
        consumed_next = False
        for pos, letter in enumerate(tok[1:], start=1):
            if letter in spec.inline_letters:
                return True
            takes_value = letter in spec.value_letters
            if letter in spec.program_file_letters:
                program_from_file = True
                takes_value = True
            if takes_value:
                # The value ends the bundle: it is the rest of this token, or
                # the whole of the next one.
                consumed_next = pos + 1 == len(tok)
                break
        idx += 2 if consumed_next else 1
    return False


def _detect_foreign_inline_code(cmd_text: str) -> bool:
    """Return True if *cmd_text* hands a foreign executor a program to run.

    Covers an inline-code flag in every spelling the executor accepts --
    short, bundled, attached, long and long-with-``=`` -- plus awk's bare
    program argument, a wrapped executor (``uv run python -c "..."``) and an
    assignment prefix (``X=1 python -c "..."``).

    Does NOT cover code reaching an interpreter on stdin (``cat prog |
    python``), or an interpreter behind a wrapper not in
    :data:`COMMAND_WRAPPERS`.

    Args:
        cmd_text: The command text to check.

    Returns:
        True if a foreign executor is run with inline code.
    """
    tokens = cmd_text.split()
    idx = _executor_index(tokens)
    if idx is None:
        return False
    return _scan_for_inline_code(tokens[idx + 1 :], _flags_for(tokens[idx]))


def _detect_bash_dash_c(cmd_text: str) -> Optional[str]:
    """Return the inner bash code if *cmd_text* is ``<bash-family> -c "<bash>"``.

    Only that exact shape is recognised, optionally behind ``NAME=value``
    assignments: ``-c`` must directly follow the shell, and the code must be
    single- or double-quoted. ``bash -x -c '...'`` and ``bash -c $'...'`` both
    return None, and the leaf then stays undecomposed -- matched whole, with
    no ASK floor, since bash is not a foreign executor.

    Args:
        cmd_text: The command text to check.

    Returns:
        The unquoted inner bash code, or None if this is not a bash -c pattern.
    """
    lead = 0
    for tok in cmd_text.split():
        if not _ASSIGNMENT_TOKEN_RE.match(tok):
            break
        lead += 1
    tokens = cmd_text.split(None, lead + 2)
    if len(tokens) < lead + 3:
        return None
    if _basename(tokens[lead]) not in BASH_FAMILY:
        return None
    if tokens[lead + 1] != "-c":
        return None
    return _extract_quoted_string(tokens[lead + 2])


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


def _condition_results(ctrl: IRControlStructure) -> List[ExtractionResult]:
    """Extract structured results from a control structure's condition.

    The condition of an if/while/until is a command bash runs, so it goes
    through the same leaf policy as any other command and can carry the ASK
    floor. A POSIX ``[ ... ]`` condition is dropped instead -- it is a test,
    not a command. Empty for a for loop, which has no condition.
    """
    cond_text = ctrl.ctrl_condition_text
    if not cond_text or _is_posix_test(cond_text):
        return []
    # Own dedup scope, so a command appearing in both the condition and the
    # body is emitted for each -- bash runs it in both places.
    return _apply_leaf_policy(cond_text, set())


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

    Emits a while/until loop's condition command, then the commands of the
    loop BODY, and only when the body has no nested control structure and the
    condition avoids ``[[ ]]``/``(( ))``. A for loop's header names a variable
    and a word list, not a command, so it contributes nothing.

    Returns:
        The condition and body results, or a single
        :class:`UndecidableSegment` naming which guard fired.
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

    return _condition_results(ctrl) + _extract_from_body_ir(ctrl.body_stmts_ir)


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

    return _condition_results(ctrl) + _extract_from_body_ir(ctrl.body_stmts_ir)


# ---------------------------------------------------------------------------
# Structured extraction: IR -> List[ExtractionResult]
# ---------------------------------------------------------------------------


def _substitution_carries_ask_floor(cmd_substs: Sequence["IRCompound"]) -> bool:
    """Return True if any command inside *cmd_substs* would itself carry ``ask_floor``.

    Probes each substitution's compound through the same structured walk
    used for a whole command line (:func:`_structured_from_compound`), on a
    throwaway result list and a throwaway ``seen`` set so this check can
    never suppress a leaf the real walk still needs to emit. Nesting is
    covered because that walk recurses into a nested ``cmd_substs`` the same
    way.

    Args:
        cmd_substs: A simple command's :attr:`IRSimpleCmd.cmd_substs`.

    Returns:
        True if a foreign executor with inline code is reachable inside any
        of *cmd_substs*, at any depth.
    """
    for subst_compound in cmd_substs:
        probe: List[ExtractionResult] = []
        _structured_from_compound(subst_compound, probe, set())
        if any(isinstance(r, LeafCommand) and r.ask_floor for r in probe):
            return True
    return False


def _apply_leaf_policy(
    cmd_text: str, seen: Set[str], cmd_substs: Sequence["IRCompound"] = ()
) -> List[ExtractionResult]:
    """Apply the module's leaf-level business policy to one leaf command's text.

    ``<bash-family> -c "<code>"`` recurses into the inner code and yields its
    leaves instead of itself; foreign inline code -- directly on the leaf or
    inside one of its *cmd_substs* -- and a heredoc bound for a foreign sink
    get ``ask_floor``; anything else is a plain leaf. Text already in *seen*
    yields nothing, which is why a line's result can be shorter than its
    command count.

    Args:
        cmd_text: The cleaned command text for the leaf node.
        seen: Set of already-seen texts (mutated by this function).
        cmd_substs: The leaf's ``$(...)``/backtick substitutions, if it is an
            :class:`IRSimpleCmd`. Callers with no IR to hand -- a control
            structure's condition text, and the ``bash -c`` recursion below --
            pass none, so a substitution inside a condition is not yet
            covered by this check.

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

    if _detect_foreign_inline_code(cmd_text) or _substitution_carries_ask_floor(
        cmd_substs
    ):
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

    A simple command's ``cmd_substs`` are not emitted as their own leaves --
    ``echo $(rm -rf /)`` still produces one leaf carrying the whole text, so
    this stays in step with :func:`~toolguard.compound.decompose`, which
    already gets the substitution's own sub-commands from
    :func:`extract_commands`. What ``cmd_substs`` change here is whether that
    one leaf carries ``ask_floor`` -- see :func:`_apply_leaf_policy`.
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
        results.extend(_apply_leaf_policy(element.text, seen, element.cmd_substs))
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


def command_spellings(
    command_text: str, looked_past_when_granting: Sequence[str] = ()
) -> CommandSpellings:
    """How *command_text* may be spelled for permission matching.

    A granting list gets the stripped spelling only when EVERY leading
    assignment's name is in *looked_past_when_granting*: one unlisted name in the
    prefix and the grant sees the raw command only, so ``TG_INTENT=1 LD_PRELOAD=x
    ls`` is not granted by ``allow Bash(ls:*)``.

    Args:
        command_text: One leaf command, as handed to permission matching.
        looked_past_when_granting: Assignment variable names a granting list may
            be matched past.

    Returns:
        A :class:`~toolguard.config_types.CommandSpellings`. Both fields are empty
        when *command_text* carries no leading assignment, which leaves matching
        exactly as it was.
    """
    prefix = leading_assignments(command_text)
    if prefix is None or prefix.without_prefix == command_text:
        return CommandSpellings()
    granted = all(name in looked_past_when_granting for name in prefix.names)
    return CommandSpellings(
        restricting=(prefix.without_prefix,),
        granting=(prefix.without_prefix,) if granted else (),
    )


def leading_assignments(command_text: str) -> Optional[IRAssignmentPrefix]:
    """The leading ``NAME=value`` assignments *command_text* runs its command with.

    Recognised by the grammar, so ``FOO+=1``, a quoted value and a substitution
    in the value are all covered, and an assignment-looking token that is not
    leading (``echo FOO=1``) is not one.

    Args:
        command_text: One leaf command, as handed to permission matching.

    Returns:
        An :class:`~toolguard.parser.command_model.IRAssignmentPrefix`, or None
        when *command_text* has no leading assignment, does not parse, or is
        more than a single simple command -- a caller reading this to decide
        what a rule may match must not be handed a guess.
    """
    if not command_text or not command_text.strip():
        return None

    try:
        ir = build_ir(bash_parser.parse(command_text))
    except Exception:
        return None

    if len(ir.statements) != 1 or len(ir.statements[0].pipelines) != 1:
        return None
    elements = ir.statements[0].pipelines[0].elements
    if len(elements) != 1 or not isinstance(elements[0], IRSimpleCmd):
        return None
    return elements[0].assignment_prefix


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
