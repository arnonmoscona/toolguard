"""
Abstract Command Model (IR) for the bash command extractor.

This module defines a small typed Intermediate Representation (IR) that sits
between the raw Canopy parse tree and the business-policy extraction layer in
``command_extractor.py``.

**Design contract**:
  - ALL code that touches raw Canopy ``TreeNode*`` objects, ``hasattr`` checks,
    or the ``elements`` lists lives here -- specifically in :func:`build_ir`.
  - The rest of the codebase operates only on the IR types defined in this
    module.

The IR is intentionally shallow: it models only the constructs the extractor
cares about, not a full bash AST.

Node kind dispatch is centralised in :func:`node_kind`, which collapses the
~12 ``_is_*`` predicates previously scattered across ``command_extractor.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Optional


# ---------------------------------------------------------------------------
# Node kind classification
# ---------------------------------------------------------------------------


class NodeKind(Enum):
    """Classification of a raw Canopy parse-tree node.

    This enum covers every node type the IR builder needs to distinguish.
    Nodes that don't match any specific pattern are classified as GENERIC
    and handled by recursive descent into their children.
    """

    PROGRAM = auto()  # top-level program node (has rest_stmts)
    FOR_LOOP = auto()  # for_loop (has for_kw + do_clause)
    WHILE_LOOP = auto()  # while_loop (has while_kw + do_clause)
    UNTIL_LOOP = auto()  # until_loop (has until_kw + do_clause)
    IF_STMT = auto()  # if_stmt (has if_kw + then_clause)
    CASE_STMT = auto()  # case_stmt (has case_kw + esac_kw)
    PROC_SUBST = auto()  # process substitution <(...) or >(...)
    SIMPLE_CMD = auto()  # pipeline_element with command_name
    SUBSHELL_OR_BRACE = (
        auto()
    )  # pipeline_element with compound_command (not proc_subst)
    COMPOUND_CMD = auto()  # compound_command node (has pipeline, no control_op)
    CONTROL_OP_PAIR = auto()  # control_op + pipeline pair
    PIPELINE = auto()  # pipeline node (has pipeline_element)
    GENERIC = auto()  # anything else -- walk children


def node_kind(node) -> NodeKind:
    """Classify a raw Canopy parse-tree *node* into a :class:`NodeKind`.

    This is the SINGLE point of ``hasattr`` / TreeNodeN dispatch.  All
    classification logic that previously lived in the ``_is_*`` predicates
    is consolidated here.

    Args:
        node: A raw Canopy TreeNode (any subclass).

    Returns:
        The :class:`NodeKind` that best describes *node*.
    """
    if node is None:
        return NodeKind.GENERIC

    # Program node: uniquely identified by rest_stmts label.
    if hasattr(node, "rest_stmts"):
        return NodeKind.PROGRAM

    # Control structures -- check before other hasattr tests.
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

    # Process substitution: compound_command AND text starts with <( or >(.
    if (
        hasattr(node, "compound_command")
        and hasattr(node, "text")
        and node.text
        and node.text[0] in ("<", ">")
        and len(node.text) > 1
        and node.text[1] == "("
    ):
        return NodeKind.PROC_SUBST

    # Simple command (pipeline_element leaf): has command_name.
    if hasattr(node, "command_name"):
        return NodeKind.SIMPLE_CMD

    # Subshell or brace group at pipeline_element level:
    # has compound_command but is NOT proc_subst.
    # NOTE: cmd_substitution nodes (TreeNode59) also have compound_command,
    # but they appear as children of a simple_command's element list, not
    # as the top-level pipeline_element.  Context determines interpretation;
    # the builder uses _build_pipeline_element (top-level) vs
    # _collect_cmd_substs (within arguments) to distinguish the two cases.
    if hasattr(node, "compound_command"):
        return NodeKind.SUBSHELL_OR_BRACE

    # Control-op + pipeline pair (e.g. "&& pipeline" from the rest-of-compound list).
    if hasattr(node, "control_op") and hasattr(node, "pipeline"):
        return NodeKind.CONTROL_OP_PAIR

    # Compound command: has pipeline but no control_op.
    if hasattr(node, "pipeline") and not hasattr(node, "control_op"):
        return NodeKind.COMPOUND_CMD

    # Pipeline: has pipeline_element.
    if hasattr(node, "pipeline_element"):
        return NodeKind.PIPELINE

    return NodeKind.GENERIC


# ---------------------------------------------------------------------------
# IR node types
# ---------------------------------------------------------------------------


@dataclass
class IRSimpleCmd:
    """A leaf simple command from a pipeline_element node.

    Attributes:
        text: The cleaned command text (stripped, trailing operators removed).
        has_proc_subst: True if the argument list contains any process
            substitution argument (``<(...)`` or ``>(...)``).
        cmd_substs: Ordered list of IRCompound nodes for any ``$(...)`` or
            backtick command substitutions found in the argument list.
            These must be extracted for security checking (an inner
            ``$(rm -rf /)`` argument is just as dangerous as a top-level
            ``rm -rf /`` command).
    """

    text: str
    has_proc_subst: bool = False
    cmd_substs: List["IRCompound"] = field(default_factory=list)


@dataclass
class IRSubshell:
    """A subshell ``(...)`` or brace group ``{...}`` pipeline element.

    Both wrappers contain an inner compound.  The *wrapper_text* includes
    the surrounding parens/braces; *inner_text* is the content without them
    (may equal the compound's text after stripping trailing ``;``).

    Attributes:
        wrapper_text: Full text of the pipeline element (e.g. ``(ls -la)``).
        inner_text: Text of the inner compound_command node, stripped and
            with trailing ``;`` removed.
        inner: The :class:`IRCompound` built from the inner compound_command.
    """

    wrapper_text: str
    inner_text: str
    inner: "IRCompound"


@dataclass
class IRProcSubst:
    """A process substitution ``<(...)`` or ``>(...)`` node.

    These cannot be statically decomposed and resolve to UndecidableSegment.

    Attributes:
        text: Full text of the process substitution.
    """

    text: str


@dataclass
class IRControlStructure:
    """A control structure (for/while/until/if/case) node.

    All complexity flags and the body statements are pre-computed here during
    the IR build phase so that the extraction layer in ``command_extractor.py``
    does NOT need to access raw Canopy nodes directly.

    Attributes:
        kind: The :class:`NodeKind` of the control structure.
        raw_node: The original Canopy TreeNode (kept for diagnostics / fallback;
            not accessed by the extraction layer after Stage 2 refactor).
        node_text: Pre-extracted ``.text`` of the raw node (stripped).
        has_else_or_elif: For ``IF_STMT``: True if elif/else clauses present.
        has_complex_condition: True if condition uses ``[[``/``((`` constructs.
        body_has_nested_control: True if body contains nested control structures.
        body_stmts_ir: Pre-built :class:`IRCompound` list for every statement in
            the body (do_clause body for loops, then-clause body for if).
            The extraction layer iterates this instead of walking raw Canopy nodes.
        ctrl_condition_text: Pre-extracted, semicolon-stripped text of the
            condition node (if/while/until only).  Empty string if absent.
        do_clause: Pre-fetched ``do_clause`` child node (for loops; raw node,
            retained for diagnostics but not used by extraction layer).
        ctrl_body: Pre-fetched ``ctrl_body`` from ``do_clause`` (raw node,
            retained for diagnostics but not used by extraction layer).
        ctrl_condition: Pre-fetched ``ctrl_condition`` node (raw node, retained
            for diagnostics; the extraction layer uses ``ctrl_condition_text``).
        then_clause: Pre-fetched ``then_clause`` node (raw node, retained for
            diagnostics; the extraction layer uses ``body_stmts_ir``).
    """

    kind: NodeKind
    raw_node: object  # raw Canopy node -- retained for diagnostics only
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


# A single element of a pipeline.
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
        raw_text: Optional raw command text from the parse tree node.  Set
            when building from a cmd_substitution inner node so that the
            command-text projection can emit the compound's text as well as
            the individual sub-commands (e.g. ``"ps aux | grep python"``
            alongside ``"ps aux"`` and ``"grep python"``).
    """

    pipelines: List[IRPipeline] = field(default_factory=list)
    raw_text: Optional[str] = None


@dataclass
class IRProgram:
    """The top-level program node: one or more statements.

    Attributes:
        statements: Ordered list of compound statements (one per statement
            in the input).
    """

    statements: List[IRCompound] = field(default_factory=list)


# ---------------------------------------------------------------------------
# IR builder: the SINGLE function allowed to touch raw Canopy nodes
# ---------------------------------------------------------------------------


def _get_elements(node) -> list:
    """Return the ``elements`` list of *node*, or empty list.

    This is the ONLY place we access the raw ``elements`` attribute.

    Args:
        node: A raw Canopy TreeNode.

    Returns:
        The ``elements`` list, or an empty list if absent / None.
    """
    return node.elements if hasattr(node, "elements") and node.elements else []


def _get_text(node) -> str:
    """Return the ``text`` attribute of *node*, stripped, or empty string.

    Args:
        node: A raw Canopy TreeNode.

    Returns:
        The stripped text, or empty string if absent.
    """
    return node.text.strip() if hasattr(node, "text") and node.text else ""


def _clean_simple_cmd_text(text: str) -> str:
    """Strip trailing control operators from a simple command text.

    These trailing operators (``;``, ``&&``, ``||``) are separator artefacts
    introduced by the grammar's ``trailing_semicolon`` rule and should not
    be included in the command text used for permission matching.

    Args:
        text: Raw text from a simple_command or compound_command node.

    Returns:
        The command text with trailing operators removed.
    """
    text = text.strip()
    while text.endswith(";") or text.endswith("&&") or text.endswith("||"):
        text = text.rstrip(";").rstrip("&").rstrip("|").strip()
    return text


def _tree_has_proc_subst(node) -> bool:
    """Return True if the subtree rooted at *node* contains a proc_subst node.

    Used to determine whether a simple_command argument list includes any
    process substitution (anywhere, even nested).

    Args:
        node: A raw Canopy TreeNode.

    Returns:
        True if any descendant node is a process substitution.
    """
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

    Args:
        node: An if_stmt TreeNode.

    Returns:
        True if the if statement has any elif or else clauses.
    """
    for elem in _get_elements(node):
        if hasattr(elem, "elif_kw") or hasattr(elem, "else_kw"):
            return True
        for sub in _get_elements(elem):
            if hasattr(sub, "elif_kw") or hasattr(sub, "else_kw"):
                return True
    return False


def _body_has_nested_control(body_node) -> bool:
    """Return True if *body_node* contains nested control structures.

    Args:
        body_node: A ctrl_body or ctrl_stmt TreeNode.

    Returns:
        True if the body contains any nested for/while/until/if/case.
    """
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
    """Return True if the condition node uses [[...]] or ((...)) constructs.

    Args:
        condition_node: The ctrl_condition TreeNode.

    Returns:
        True if the condition uses complex test constructs.
    """
    if condition_node is None:
        return False
    text = condition_node.text if hasattr(condition_node, "text") else ""
    return "[[" in text or "((" in text


def _build_body_stmts_ir(body_node) -> "List[IRCompound]":
    """Build :class:`IRCompound` objects for each statement in a ``ctrl_body`` node.

    A ``ctrl_body`` node (TreeNode32) contains:
      - ``.ctrl_stmt``: the first ctrl_stmt (named attribute).
      - ``.elements[1]``: an unnamed list of TreeNode33 items, each carrying
        a ``.ctrl_stmt`` attribute for additional body statements.

    Each ``ctrl_stmt`` is compiled to an :class:`IRCompound` via
    :func:`_build_compound`, which correctly handles both simple compound
    commands and nested control structures.

    This is the ONLY new place in this module that reads the raw
    ``ctrl_body.elements[1]`` unnamed-list structure; all raw Canopy
    walking is therefore contained within this module.

    Args:
        body_node: A ``ctrl_body`` raw Canopy TreeNode, or ``None``.

    Returns:
        Ordered list of :class:`IRCompound` for every body statement.
        Returns an empty list if *body_node* is ``None`` or empty.
    """
    if body_node is None:
        return []

    stmts: List[IRCompound] = []

    # First statement: accessible via the named attribute ``ctrl_stmt``.
    first_stmt = getattr(body_node, "ctrl_stmt", None)
    if first_stmt is not None:
        comp = _build_compound(first_stmt)
        if comp.pipelines:
            stmts.append(comp)

    # Remaining statements: body_node.elements[1] is an unnamed list of
    # TreeNode33 items, each with a ``.ctrl_stmt`` attribute.
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
    """Build a pre-populated :class:`IRControlStructure` from a raw control node.

    Pre-computes all complexity flags AND the body statements (as
    :class:`IRCompound` objects in ``body_stmts_ir``) so that the extraction
    layer does not need to access raw Canopy nodes at all.

    Args:
        node: A raw Canopy control-structure TreeNode.
        kind: The :class:`NodeKind` of the node.

    Returns:
        A fully-populated :class:`IRControlStructure`.
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
    """Collect all ``$(...)`` and backtick command substitutions from *node*'s subtree.

    This is called on the element list of a simple_command to find embedded
    command substitutions (nodes that have a ``compound_command`` child but
    are NOT proc_subst and NOT a pipeline_element-level subshell).

    The ``compound_command`` child is compiled to an :class:`IRCompound` and
    added to the result.  The search recurses into elements to find nested
    substitutions.

    A depth limit of 5 prevents unbounded recursion on pathological inputs.

    Args:
        node: A raw Canopy TreeNode (typically an element within a simple_command).
        depth: Current recursion depth (0 = top-level call).

    Returns:
        Ordered list of :class:`IRCompound` nodes for each cmd_substitution found.
    """
    if node is None or depth > 5:
        return []

    results: List[IRCompound] = []
    k = node_kind(node)

    # A node that has compound_command (and is NOT proc_subst) is a cmd_substitution.
    # Build its inner compound and recurse into it for nested substitutions.
    if k == NodeKind.SUBSHELL_OR_BRACE:
        inner_raw = node.compound_command
        inner_compound = _build_compound(inner_raw)
        # Capture the inner compound text so extract_commands can emit it
        # alongside the individual commands (e.g. "ps aux | grep python").
        inner_text = _get_text(inner_raw)
        if inner_text.endswith(";"):
            inner_text = inner_text[:-1].strip()
        inner_compound.raw_text = inner_text if inner_text else None
        results.append(inner_compound)
        # Recurse into the inner compound's raw node for deeply nested substitutions.
        results.extend(_collect_cmd_substs(inner_raw, depth + 1))
        return results

    # For other nodes: recurse into children.
    for child in _get_elements(node):
        results.extend(_collect_cmd_substs(child, depth))

    return results


def _build_pipeline_element(node) -> Optional[IRPipelineElement]:
    """Build an IR node from a single pipeline_element raw node.

    Args:
        node: A raw Canopy pipeline_element TreeNode.

    Returns:
        The appropriate :class:`IRPipelineElement`, or ``None`` if the node
        cannot be interpreted.
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
        text = _clean_simple_cmd_text(_get_text(node))
        has_ps = _tree_has_proc_subst(node)
        # Collect command substitutions from both command_name and argument elements.
        # elements[0] is command_name (may be cmd_sub_as_cmd); elements[1] is the args.
        elems = _get_elements(node)
        cmd_substs: List[IRCompound] = []
        # Check command_name for cmd_sub_as_cmd (e.g. $(ls) used as a command).
        cmd_name = getattr(node, "command_name", None)
        if cmd_name is not None:
            cmd_substs.extend(_collect_cmd_substs(cmd_name))
        # Check argument list for embedded substitutions.
        if len(elems) > 1:
            # elements[1] is the list of argument nodes (proc_subst / cmd_sub / arg).
            for arg_item in _get_elements(elems[1]):
                cmd_substs.extend(_collect_cmd_substs(arg_item))
        return IRSimpleCmd(text=text, has_proc_subst=has_ps, cmd_substs=cmd_substs)

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

    # Unexpected node type at pipeline element level -- fall through to None.
    return None


def _build_pipeline(pipeline_node) -> IRPipeline:
    """Build an :class:`IRPipeline` from a raw pipeline TreeNode.

    A pipeline node has:
    - ``.pipeline_element``: the first pipeline element (named attribute).
    - ``.elements``: a list that may contain TreeNode12 items with their own
      ``.pipeline_element`` attributes for the rest of the piped stages.

    Args:
        pipeline_node: A raw Canopy pipeline TreeNode.

    Returns:
        An :class:`IRPipeline` containing all pipeline elements.
    """
    pl = IRPipeline()
    if pipeline_node is None:
        return pl

    kind = node_kind(pipeline_node)

    # Direct pipeline element (e.g. within a proc_subst compound).
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

    # First element via named attribute.
    first_pe = getattr(pipeline_node, "pipeline_element", None)
    if first_pe is not None:
        elem = _build_pipeline_element(first_pe)
        if elem is not None:
            pl.elements.append(elem)

    # Rest of pipe stages: walk elements list looking for pipeline_element refs.
    def _collect_pipeline_elements(node) -> None:
        """Recursively collect additional pipeline elements from node's elements."""
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

    A compound_command node has:
    - ``.pipeline``: the first pipeline (named attribute).
    - ``.elements``: a list that may contain TreeNode4 items (control_op +
      pipeline pairs) for the rest of the && / || / ; separated pipelines.

    Also handles control structures appearing directly as a compound.

    Args:
        compound_node: A raw Canopy compound_command (or similar) TreeNode.

    Returns:
        An :class:`IRCompound` containing all pipelines.
    """
    comp = IRCompound()
    if compound_node is None:
        return comp

    kind = node_kind(compound_node)

    # Control structures at the compound level produce a single-element compound
    # wrapping an IRControlStructure so that the extractor can route them correctly.
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
        text = _clean_simple_cmd_text(_get_text(compound_node))
        has_ps = _tree_has_proc_subst(compound_node)
        elems = _get_elements(compound_node)
        cmd_substs: List[IRCompound] = []
        cmd_name = getattr(compound_node, "command_name", None)
        if cmd_name is not None:
            cmd_substs.extend(_collect_cmd_substs(cmd_name))
        if len(elems) > 1:
            for arg_item in _get_elements(elems[1]):
                cmd_substs.extend(_collect_cmd_substs(arg_item))
        sc_pl = IRPipeline(
            elements=[
                IRSimpleCmd(text=text, has_proc_subst=has_ps, cmd_substs=cmd_substs)
            ]
        )
        comp.pipelines.append(sc_pl)
        return comp

    # Standard compound_command: has .pipeline for first pipeline.
    first_pipeline = getattr(compound_node, "pipeline", None)
    if first_pipeline is not None:
        pl = _build_pipeline(first_pipeline)
        if pl.elements:
            comp.pipelines.append(pl)

    # Walk elements for additional (control_op + pipeline) pairs.
    def _collect_rest_pipelines(node) -> None:
        """Recursively collect control_op+pipeline pairs from node's elements."""
        for child in _get_elements(node):
            ck = node_kind(child)
            if ck == NodeKind.CONTROL_OP_PAIR:
                pl = _build_pipeline(child.pipeline)
                if pl.elements:
                    comp.pipelines.append(pl)
            elif ck == NodeKind.GENERIC:
                _collect_rest_pipelines(child)
            # Skip pipeline/simple_cmd/etc. that aren't control_op pairs.

    _collect_rest_pipelines(compound_node)
    return comp


def build_ir(tree) -> IRProgram:
    """Build an :class:`IRProgram` from a raw Canopy parse tree.

    This is the **single entry point** for all raw-tree access.  After this
    function returns, no code outside this module should touch raw Canopy
    nodes.

    Handles both:
    - A ``program`` node (TOO-17 grammar, has ``rest_stmts``).
    - A legacy single-statement tree (the first statement is accessible via
      ``compound_command``).

    Args:
        tree: The root Canopy parse tree node returned by ``bash_parser.parse()``.

    Returns:
        An :class:`IRProgram` whose ``statements`` list contains one
        :class:`IRCompound` per top-level statement.
    """
    prog = IRProgram()
    if tree is None:
        return prog

    if node_kind(tree) == NodeKind.PROGRAM:
        # Process first statement (grammar label: compound_command).
        first = getattr(tree, "compound_command", None)
        if first is not None:
            comp = _build_compound(first)
            if comp.pipelines:
                prog.statements.append(comp)

        # Process rest_stmts: each pair_node has a .statement attribute.
        rest = getattr(tree, "rest_stmts", None)
        if rest is not None and hasattr(rest, "elements"):
            for pair_node in rest.elements:
                stmt = getattr(pair_node, "statement", None)
                if stmt is not None:
                    comp = _build_compound(stmt)
                    if comp.pipelines:
                        prog.statements.append(comp)
    else:
        # Legacy single-statement: top node has compound_command.
        first = getattr(tree, "compound_command", tree)
        comp = _build_compound(first)
        if comp.pipelines:
            prog.statements.append(comp)

    return prog
