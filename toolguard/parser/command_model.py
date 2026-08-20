"""
Abstract Command Model (IR) for the bash command extractor.

A small typed Intermediate Representation that sits between the raw Canopy
parse tree and the business-policy extraction layer. :func:`build_ir` turns a
parse tree into an :class:`IRProgram`; :class:`NodeKind` and the IR node types
are the rest of the public surface.

**Design contract**: raw Canopy ``TreeNode*`` objects, ``hasattr`` probing and
the untyped ``elements`` lists are confined to this module. The contract is
per-module, not per-function: several private helpers here probe raw nodes,
not just :func:`build_ir`. :class:`IRControlStructure` does hand raw nodes
back out, but only as opaque handles.

The IR is intentionally shallow: it models only the constructs the extractor
cares about, not a full bash AST.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Node kind classification
# ---------------------------------------------------------------------------


class NodeKind(Enum):
    """Classification of a raw Canopy parse-tree node.

    Everything the IR builder needs to distinguish. Anything else is GENERIC,
    which the builder descends into rather than modelling.
    """

    # Most of these name a bash_parser.peg rule. The two that do not:
    # CONTROL_OP_PAIR is the anonymous `(control_op pipeline)` repetition
    # inside compound_command, and SUBSHELL_OR_BRACE covers subshell,
    # brace_group AND cmd_substitution -- see node_kind.
    PROGRAM = auto()
    FOR_LOOP = auto()
    WHILE_LOOP = auto()
    UNTIL_LOOP = auto()
    IF_STMT = auto()
    CASE_STMT = auto()
    PROC_SUBST = auto()
    SIMPLE_CMD = auto()
    SUBSHELL_OR_BRACE = auto()
    COMPOUND_CMD = auto()
    CONTROL_OP_PAIR = auto()
    PIPELINE = auto()
    GENERIC = auto()


def node_kind(node) -> NodeKind:
    """Classify a raw Canopy parse-tree *node* into a :class:`NodeKind`.

    Canopy names its generated node classes ``TreeNodeN``, so a node's type
    carries no meaning and the only identity it has is which grammar labels
    it exposes. The tests below are ordered, not independent: ``proc_subst``,
    ``subshell``, ``brace_group`` and both command-substitution forms all carry
    a ``compound_command`` label, so each later test means only "and none of
    the earlier ones matched".

    Args:
        node: A raw Canopy TreeNode (any subclass), or ``None``.

    Returns:
        The :class:`NodeKind` that best describes *node*; ``GENERIC`` for
        ``None`` and for anything that matches no test.
    """
    if node is None:
        return NodeKind.GENERIC

    if hasattr(node, "rest_stmts"):
        return NodeKind.PROGRAM

    if hasattr(node, "for_kw") and hasattr(node, "do_clause"):
        return NodeKind.FOR_LOOP
    if hasattr(node, "while_kw") and hasattr(node, "do_clause"):
        return NodeKind.WHILE_LOOP
    if hasattr(node, "until_kw") and hasattr(node, "do_clause"):
        return NodeKind.UNTIL_LOOP
    if hasattr(node, "if_kw") and hasattr(node, "then_clause"):
        return NodeKind.IF_STMT
    if hasattr(node, "case_kw") and hasattr(node, "esac_kw"):
        return NodeKind.CASE_STMT

    # Must precede SUBSHELL_OR_BRACE: <(...) also carries compound_command,
    # and only the leading "<("/">(" tells them apart.
    if (
        hasattr(node, "compound_command")
        and hasattr(node, "text")
        and node.text
        and node.text[0] in ("<", ">")
        and len(node.text) > 1
        and node.text[1] == "("
    ):
        return NodeKind.PROC_SUBST

    if hasattr(node, "command_name"):
        return NodeKind.SIMPLE_CMD

    # SUBSHELL_OR_BRACE is not a pure classification: a `$(...)`/backtick
    # substitution node carries compound_command too and lands here as well.
    # Position disambiguates them, so the caller must -- _build_pipeline_element
    # treats this kind as a subshell, _collect_cmd_substs as a substitution.
    if hasattr(node, "compound_command"):
        return NodeKind.SUBSHELL_OR_BRACE

    if hasattr(node, "control_op") and hasattr(node, "pipeline"):
        return NodeKind.CONTROL_OP_PAIR

    if hasattr(node, "pipeline") and not hasattr(node, "control_op"):
        return NodeKind.COMPOUND_CMD

    if hasattr(node, "pipeline_element"):
        return NodeKind.PIPELINE

    return NodeKind.GENERIC


# ---------------------------------------------------------------------------
# IR node types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IRAssignmentPrefix:
    """The ``NAME=value`` assignments a simple command runs its command word with.

    Attributes:
        names: Each assignment's variable name, in source order. The ``+`` of
            bash's ``NAME+=value`` is the operator, not part of the name.
        without_prefix: The command text from the executed word onward, cleaned
            the same way :attr:`IRSimpleCmd.text` is.
    """

    names: Tuple[str, ...]
    without_prefix: str


@dataclass
class IRSimpleCmd:
    """A leaf simple command from a pipeline_element node.

    Attributes:
        text: The command text, per :func:`_clean_simple_cmd_text`.
        has_proc_subst: True if any descendant is a process substitution
            (``<(...)`` or ``>(...)``), however deeply nested.
        cmd_substs: Ordered list of :class:`IRCompound` nodes for the
            ``$(...)`` and backtick substitutions in the command name and the
            argument list. Broken out because an inner ``$(rm -rf /)``
            argument is as dangerous as a top-level ``rm -rf /``, and *text*
            alone would only ever be matched as one string.
        assignment_prefix: The leading assignments, or None where there are
            none. Broken out because *text* names the assignment rather than
            the command under it, so a rule written against the command would
            not match.
    """

    text: str
    has_proc_subst: bool = False
    cmd_substs: List["IRCompound"] = field(default_factory=list)
    assignment_prefix: Optional[IRAssignmentPrefix] = None


@dataclass
class IRSubshell:
    """A subshell ``(...)`` or brace group ``{...}`` pipeline element.

    Attributes:
        wrapper_text: Full text of the pipeline element, e.g. ``(ls -la)``.
        inner_text: Text of the inner compound_command node, stripped and
            with one trailing ``;`` removed.
        inner: The :class:`IRCompound` built from the inner compound_command.
    """

    wrapper_text: str
    inner_text: str
    inner: "IRCompound"


@dataclass
class IRProcSubst:
    """A process substitution ``<(...)`` or ``>(...)`` node.

    The inner compound is not modelled: a process substitution is never
    decomposed, so there would be no reader for it.

    Attributes:
        text: Full text of the process substitution.
    """

    text: str


@dataclass
class IRControlStructure:
    """A control structure (for/while/until/if/case) node.

    Every flag and body statement is computed during the IR build, so the
    extraction layer decides SIMPLE-versus-COMPLEX from this dataclass alone.
    ``raw_node`` and the four fields after ``ctrl_condition_text`` are raw
    Canopy handles, not data: no consumer dereferences one, and only
    ``do_clause`` is looked at at all -- tested for ``None`` to tell a
    malformed loop from a loop with an empty body.

    A ``CASE_STMT`` carries only *kind*, *raw_node* and *node_text*; the
    build skips every other field for it, since a case statement is never
    decomposed.

    Attributes:
        kind: The :class:`NodeKind` of the control structure.
        raw_node: The original Canopy TreeNode.
        node_text: ``.text`` of the raw node, stripped.
        has_else_or_elif: ``IF_STMT`` only: elif/else clauses are present.
        has_complex_condition: The condition text contains ``[[`` or ``((``.
        body_has_nested_control: The body contains a nested control structure.
        body_stmts_ir: One :class:`IRCompound` per body statement -- the
            do_clause body for loops, the then-clause body for if.
        ctrl_condition_text: The condition node's text, stripped of a trailing
            ``;`` (if/while/until only). Empty string if absent.
        do_clause: The ``do_clause`` child node (loops only).
        ctrl_body: The ``ctrl_body`` reached through ``do_clause``.
        ctrl_condition: The ``ctrl_condition`` node -- consumers want
            ``ctrl_condition_text``.
        then_clause: The ``then_clause`` node -- consumers want
            ``body_stmts_ir``.
    """

    kind: NodeKind
    raw_node: object
    node_text: str = ""
    has_else_or_elif: bool = False
    has_complex_condition: bool = False
    body_has_nested_control: bool = False
    body_stmts_ir: List["IRCompound"] = field(default_factory=list)
    ctrl_condition_text: str = ""
    do_clause: object = None
    ctrl_body: object = None
    ctrl_condition: object = None
    then_clause: object = None


#: A single element of a pipeline.
IRPipelineElement = IRSimpleCmd | IRSubshell | IRProcSubst | IRControlStructure


@dataclass
class IRPipeline:
    """A pipeline: one or more elements joined by ``|``.

    Attributes:
        elements: Ordered list of pipeline elements.
    """

    elements: List[IRPipelineElement] = field(default_factory=list)


@dataclass
class IRCompound:
    """A compound: one or more pipelines joined by ``&&``, ``||``, or ``;``.

    Attributes:
        pipelines: Ordered list of pipelines.
        raw_text: Set only when building a command substitution's inner node,
            so the command-text projection can emit the compound's own text
            (``"ps aux | grep python"``) alongside its stages. ``None``
            everywhere else, which is what marks a compound as NOT a
            substitution.
    """

    pipelines: List[IRPipeline] = field(default_factory=list)
    raw_text: Optional[str] = None


@dataclass
class IRProgram:
    """The top-level program node: one or more statements.

    Attributes:
        statements: Ordered list of compound statements. A statement whose
            compound has no pipelines is dropped, so this can be shorter than
            the input's statement count -- and empty.
    """

    statements: List[IRCompound] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IR builder: the raw-Canopy side of the module
# ---------------------------------------------------------------------------


def _get_elements(node) -> list:
    return node.elements if hasattr(node, "elements") and node.elements else []


def _get_text(node) -> str:
    return node.text.strip() if hasattr(node, "text") and node.text else ""


def _clean_simple_cmd_text(text: str) -> str:
    """Strip trailing ``;``, ``&&`` and ``||`` from a command's text.

    A lone trailing ``&`` is left in place.
    """
    text = text.strip()
    while text.endswith(";") or text.endswith("&&") or text.endswith("||"):
        text = text.rstrip(";").rstrip("&").rstrip("|").strip()
    return text


def _assignment_prefix(node) -> Optional[IRAssignmentPrefix]:
    """Read a simple command's leading assignments off raw *node*, or None if it has none.

    Args:
        node: A raw Canopy simple_command TreeNode.

    Returns:
        An :class:`IRAssignmentPrefix`, or None when the grammar matched no
        ``assigned_command`` here.
    """
    cmd_name = getattr(node, "command_name", None)
    if cmd_name is None:
        return None
    prefix = getattr(cmd_name, "assignment_prefix", None)
    command_start = getattr(cmd_name, "command_start", None)
    if prefix is None or command_start is None:
        return None

    names = tuple(
        assignment.assignment_name.text for assignment in _get_elements(prefix)
    )
    # Offsets are into the whole input, so the executed part is found by
    # rebasing the command word's offset onto this node's own text.
    node_text = node.text if hasattr(node, "text") and node.text else ""
    without_prefix = node_text[command_start.offset - node.offset :]
    return IRAssignmentPrefix(
        names=names, without_prefix=_clean_simple_cmd_text(without_prefix)
    )


def _tree_has_proc_subst(node) -> bool:
    """Return True if any descendant of *node* is a process substitution."""
    if node is None:
        return False
    if node_kind(node) == NodeKind.PROC_SUBST:
        return True
    for child in _get_elements(node):
        if _tree_has_proc_subst(child):
            return True
    return False


def _if_has_else_or_elif(node) -> bool:
    """Return True if the if_stmt *node* has else or elif clauses.

    Searches two levels only: the if_stmt's own elements and their immediate
    children, which is where the grammar puts ``elif_clause``/``else_clause``.
    """
    for elem in _get_elements(node):
        if hasattr(elem, "elif_kw") or hasattr(elem, "else_kw"):
            return True
        for sub in _get_elements(elem):
            if hasattr(sub, "elif_kw") or hasattr(sub, "else_kw"):
                return True
    return False


def _body_has_nested_control(body_node) -> bool:
    """Return True if *body_node* contains a nested for/while/until/if/case, at any depth."""
    if body_node is None:
        return False
    for elem in _get_elements(body_node):
        k = node_kind(elem)
        if k in (
            NodeKind.FOR_LOOP,
            NodeKind.WHILE_LOOP,
            NodeKind.UNTIL_LOOP,
            NodeKind.IF_STMT,
            NodeKind.CASE_STMT,
        ):
            return True
        if _body_has_nested_control(elem):
            return True
    return False


def _has_complex_condition(condition_node) -> bool:
    """Return True if the condition node's text contains ``[[`` or ``((``.

    A substring test, not a parse: a condition merely *mentioning* either
    sequence -- inside a quoted argument, say -- also counts. That errs
    towards calling a condition complex, which costs an ASK.
    """
    if condition_node is None:
        return False
    text = condition_node.text if hasattr(condition_node, "text") else ""
    return "[[" in text or "((" in text


def _build_body_stmts_ir(body_node) -> "List[IRCompound]":
    """Build one :class:`IRCompound` per statement in a ``ctrl_body`` node.

    Canopy labels only the FIRST body statement (``.ctrl_stmt``); the rest
    live in an unnamed repetition at ``.elements[1]``, whose items each carry
    their own ``.ctrl_stmt``. That positional index is the fragile part --
    it tracks ``ctrl_body <- ctrl_stmt (ctrl_sep ctrl_stmt)*`` in the
    grammar, and reordering that rule silently drops every statement after
    the first.

    Args:
        body_node: A ``ctrl_body`` raw Canopy TreeNode, or ``None``.

    Returns:
        Ordered list of :class:`IRCompound` for every body statement,
        skipping any that built no pipelines. Empty if *body_node* is
        ``None``.
    """
    if body_node is None:
        return []

    stmts: List[IRCompound] = []

    first_stmt = getattr(body_node, "ctrl_stmt", None)
    if first_stmt is not None:
        comp = _build_compound(first_stmt)
        if comp.pipelines:
            stmts.append(comp)

    raw_elems = _get_elements(body_node)
    if len(raw_elems) > 1:
        rest_list = raw_elems[1]
        for item in _get_elements(rest_list):
            stmt = getattr(item, "ctrl_stmt", None)
            if stmt is not None:
                comp = _build_compound(stmt)
                if comp.pipelines:
                    stmts.append(comp)

    return stmts


def _build_control_structure(node, kind: NodeKind) -> "IRControlStructure":
    """Build an :class:`IRControlStructure` from a raw control node.

    Computes the complexity flags and the body statements up front, so the
    extraction layer never has to walk back into the raw tree. A ``CASE_STMT``
    gets neither -- see :class:`IRControlStructure`.

    Args:
        node: A raw Canopy control-structure TreeNode.
        kind: The :class:`NodeKind` of the node.

    Returns:
        The populated :class:`IRControlStructure`.
    """
    node_text = _get_text(node)
    do_clause = getattr(node, "do_clause", None)
    ctrl_body = getattr(do_clause, "ctrl_body", None) if do_clause is not None else None
    ctrl_condition = getattr(node, "ctrl_condition", None)
    then_clause = getattr(node, "then_clause", None)

    has_else_or_elif = False
    body_nested = False
    complex_cond = False
    body_stmts_ir: List[IRCompound] = []
    ctrl_condition_text = ""

    if kind == NodeKind.IF_STMT:
        has_else_or_elif = _if_has_else_or_elif(node)
        if then_clause is not None:
            then_body = getattr(then_clause, "ctrl_body", None)
            body_nested = _body_has_nested_control(then_body)
            body_stmts_ir = _build_body_stmts_ir(then_body)
        complex_cond = _has_complex_condition(ctrl_condition)
        if ctrl_condition is not None:
            ctrl_condition_text = _get_text(ctrl_condition).rstrip(";").strip()
    elif kind in (NodeKind.FOR_LOOP, NodeKind.WHILE_LOOP, NodeKind.UNTIL_LOOP):
        body_nested = _body_has_nested_control(ctrl_body)
        complex_cond = _has_complex_condition(ctrl_condition)
        body_stmts_ir = _build_body_stmts_ir(ctrl_body)
        if ctrl_condition is not None:
            ctrl_condition_text = _get_text(ctrl_condition).rstrip(";").strip()

    return IRControlStructure(
        kind=kind,
        raw_node=node,
        node_text=node_text,
        has_else_or_elif=has_else_or_elif,
        has_complex_condition=complex_cond,
        body_has_nested_control=body_nested,
        body_stmts_ir=body_stmts_ir,
        ctrl_condition_text=ctrl_condition_text,
        do_clause=do_clause,
        ctrl_body=ctrl_body,
        ctrl_condition=ctrl_condition,
        then_clause=then_clause,
    )


def _collect_cmd_substs(node, depth: int = 0) -> List["IRCompound"]:
    """Collect the ``$(...)`` and backtick substitutions in *node*'s subtree.

    Call this only from inside a simple_command. It reads a
    ``SUBSHELL_OR_BRACE`` node as a substitution, which is the right reading
    in that position and the wrong one at pipeline-element level, where
    :func:`_build_pipeline_element` reads the same kind as a subshell.

    Args:
        node: A raw Canopy TreeNode.
        depth: Substitution nesting depth, not tree depth. The ``> 5`` cutoff
            is inert -- the count restarts at 0 whenever the walk re-enters
            through :func:`_build_compound`, so 20 nested ``$( )`` layers are
            all collected.

    Returns:
        Ordered list of :class:`IRCompound` nodes, one per substitution found.
    """
    if node is None or depth > 5:
        return []

    results: List[IRCompound] = []
    k = node_kind(node)

    if k == NodeKind.SUBSHELL_OR_BRACE:
        inner_raw = node.compound_command
        inner_compound = _build_compound(inner_raw)
        inner_text = _get_text(inner_raw)
        if inner_text.endswith(";"):
            inner_text = inner_text[:-1].strip()
        inner_compound.raw_text = inner_text if inner_text else None
        results.append(inner_compound)
        results.extend(_collect_cmd_substs(inner_raw, depth + 1))
        return results

    for child in _get_elements(node):
        results.extend(_collect_cmd_substs(child, depth))

    return results


def _build_simple_cmd(node) -> IRSimpleCmd:
    """Build an :class:`IRSimpleCmd` from a raw simple_command *node*."""
    # simple_command <- command_name (proc_subst / redirection /
    # cmd_substitution / command_arg)* -- so elements[1] is the argument
    # repetition. Both halves can hold a substitution: `$(which python) -V`
    # puts one in the command name, `echo $(id)` in the arguments.
    elems = _get_elements(node)
    cmd_substs: List[IRCompound] = []
    cmd_name = getattr(node, "command_name", None)
    if cmd_name is not None:
        cmd_substs.extend(_collect_cmd_substs(cmd_name))
    if len(elems) > 1:
        for arg_item in _get_elements(elems[1]):
            cmd_substs.extend(_collect_cmd_substs(arg_item))
    return IRSimpleCmd(
        text=_clean_simple_cmd_text(_get_text(node)),
        has_proc_subst=_tree_has_proc_subst(node),
        cmd_substs=cmd_substs,
        assignment_prefix=_assignment_prefix(node),
    )


def _build_pipeline_element(node) -> Optional[IRPipelineElement]:
    """Build an IR node from a single pipeline_element raw node.

    Args:
        node: A raw Canopy pipeline_element TreeNode.

    Returns:
        The corresponding :class:`IRPipelineElement`, or ``None`` for a kind
        that has no pipeline-element form. A ``None`` is dropped silently by
        every caller, so the element simply disappears from the IR.
    """
    kind = node_kind(node)

    if kind == NodeKind.PROC_SUBST:
        return IRProcSubst(text=_get_text(node))

    if kind in (
        NodeKind.FOR_LOOP,
        NodeKind.WHILE_LOOP,
        NodeKind.UNTIL_LOOP,
        NodeKind.IF_STMT,
        NodeKind.CASE_STMT,
    ):
        return _build_control_structure(node, kind)

    if kind == NodeKind.SIMPLE_CMD:
        return _build_simple_cmd(node)

    if kind == NodeKind.SUBSHELL_OR_BRACE:
        wrapper_text = _get_text(node)
        inner_raw = node.compound_command
        inner_text_raw = _get_text(inner_raw)
        if inner_text_raw.endswith(";"):
            inner_text_raw = inner_text_raw[:-1].strip()
        inner_compound = _build_compound(inner_raw)
        return IRSubshell(
            wrapper_text=wrapper_text,
            inner_text=inner_text_raw,
            inner=inner_compound,
        )

    return None


def _build_pipeline(pipeline_node) -> IRPipeline:
    """Build an :class:`IRPipeline` from a raw pipeline TreeNode.

    Canopy labels only the first stage (``.pipeline_element``); the rest are
    reached by walking ``.elements`` for further ``pipeline_element`` labels.

    Args:
        pipeline_node: A raw pipeline TreeNode, or a single pipeline-element
            node -- callers pass both, so a node that is already an element
            is wrapped in a one-stage pipeline rather than rejected.

    Returns:
        An :class:`IRPipeline`; empty for ``None`` and for a node that yields
        no interpretable element.
    """
    pl = IRPipeline()
    if pipeline_node is None:
        return pl

    kind = node_kind(pipeline_node)

    if kind not in (
        NodeKind.PIPELINE,
        NodeKind.COMPOUND_CMD,
        NodeKind.CONTROL_OP_PAIR,
        NodeKind.GENERIC,
    ):
        elem = _build_pipeline_element(pipeline_node)
        if elem is not None:
            pl.elements.append(elem)
        return pl

    first_pe = getattr(pipeline_node, "pipeline_element", None)
    if first_pe is not None:
        elem = _build_pipeline_element(first_pe)
        if elem is not None:
            pl.elements.append(elem)

    def _collect_pipeline_elements(node) -> None:
        """Append the remaining pipe stages found under *node* to the enclosing pipeline.

        Does not descend into a simple command: its own subtree is already
        covered by the element built for it.
        """
        for child in _get_elements(node):
            if (
                hasattr(child, "pipeline_element")
                and child.pipeline_element is not None
            ):
                e = _build_pipeline_element(child.pipeline_element)
                if e is not None:
                    pl.elements.append(e)
            elif not hasattr(child, "command_name"):
                _collect_pipeline_elements(child)

    _collect_pipeline_elements(pipeline_node)
    return pl


def _build_compound(compound_node) -> IRCompound:
    """Build an :class:`IRCompound` from a raw compound_command TreeNode.

    Canopy labels only the first pipeline (``.pipeline``); the ``&&``/``||``/
    ``;``-separated remainder is reached by walking ``.elements`` for
    control-op-plus-pipeline pairs.

    Args:
        compound_node: A raw compound_command TreeNode -- or a control
            structure, a process substitution or a simple command, each of
            which is wrapped in a one-pipeline compound instead.

    Returns:
        An :class:`IRCompound`; empty for ``None``.
    """
    comp = IRCompound()
    if compound_node is None:
        return comp

    kind = node_kind(compound_node)

    if kind in (
        NodeKind.FOR_LOOP,
        NodeKind.WHILE_LOOP,
        NodeKind.UNTIL_LOOP,
        NodeKind.IF_STMT,
        NodeKind.CASE_STMT,
    ):
        ctrl_pl = IRPipeline(elements=[_build_control_structure(compound_node, kind)])
        comp.pipelines.append(ctrl_pl)
        return comp

    if kind == NodeKind.PROC_SUBST:
        ps_pl = IRPipeline(elements=[IRProcSubst(text=_get_text(compound_node))])
        comp.pipelines.append(ps_pl)
        return comp

    if kind == NodeKind.SIMPLE_CMD:
        comp.pipelines.append(IRPipeline(elements=[_build_simple_cmd(compound_node)]))
        return comp

    first_pipeline = getattr(compound_node, "pipeline", None)
    if first_pipeline is not None:
        pl = _build_pipeline(first_pipeline)
        if pl.elements:
            comp.pipelines.append(pl)

    def _collect_rest_pipelines(node) -> None:
        """Append the ``control_op``-separated pipelines under *node* to the compound.

        Descends only through GENERIC nodes -- the unlabelled repetition
        wrappers Canopy interposes. Anything it can name is either the pair
        it wants or already accounted for.
        """
        for child in _get_elements(node):
            ck = node_kind(child)
            if ck == NodeKind.CONTROL_OP_PAIR:
                pl = _build_pipeline(child.pipeline)
                if pl.elements:
                    comp.pipelines.append(pl)
            elif ck == NodeKind.GENERIC:
                _collect_rest_pipelines(child)

    _collect_rest_pipelines(compound_node)
    return comp


def build_ir(tree) -> IRProgram:
    """Build an :class:`IRProgram` from a raw Canopy parse tree.

    Accepts either a ``program`` node or a bare single-statement tree. On a
    ``program`` node the FIRST statement carries the grammar label
    ``compound_command``; only the remainder are reached through
    ``rest_stmts``. That naming is deliberate in ``bash_parser.peg`` -- do not
    "fix" it to ``statement`` without following it here.

    Args:
        tree: The root node returned by ``bash_parser.parse()``, or ``None``.

    Returns:
        An :class:`IRProgram`, one :class:`IRCompound` per top-level
        statement that produced any pipeline.
    """
    prog = IRProgram()
    if tree is None:
        return prog

    if node_kind(tree) == NodeKind.PROGRAM:
        first = getattr(tree, "compound_command", None)
        if first is not None:
            comp = _build_compound(first)
            if comp.pipelines:
                prog.statements.append(comp)

        rest = getattr(tree, "rest_stmts", None)
        if rest is not None and hasattr(rest, "elements"):
            for pair_node in rest.elements:
                stmt = getattr(pair_node, "statement", None)
                if stmt is not None:
                    comp = _build_compound(stmt)
                    if comp.pipelines:
                        prog.statements.append(comp)
    else:
        first = getattr(tree, "compound_command", tree)
        comp = _build_compound(first)
        if comp.pipelines:
            prog.statements.append(comp)

    return prog
