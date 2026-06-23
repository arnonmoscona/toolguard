"""
Compound command permission checking for toolguard.

This module provides permission checking for compound bash commands,
validating each sub-command and returning the strictest permission decision.

TOO-17: resolve_compound_permission now uses the multi-line pre-processor
(:mod:`toolguard.parser.multiline`) to correctly handle multi-line commands,
heredocs, inline code, and control structures.  The governing principle is
**"when in doubt, ASK"**: any segment that cannot be safely decomposed
resolves to ASK rather than a silent allow of an undecomposed blob.
"""

import logging
from typing import Callable, List, Tuple

from toolguard.parser.command_extractor import extract_commands
from toolguard.parser.multiline import (
    LeafCommand,
    UndecidableSegment,
    extract_structured,
)
from toolguard.permissions import check_permission

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_leaf(
    leaf: LeafCommand, resolve_one: Callable[[str], Tuple[str, str]]
) -> Tuple[str, str]:
    """Resolve a single leaf command through the grammar splitter then resolve_one.

    The leaf may still be a compound single-line command (``git status && echo x``).
    We run it through the existing PEG grammar to split it further, then apply
    ``resolve_one`` to each sub-command.

    The ASK floor from the leaf's ``ask_floor`` flag is applied AFTER the normal
    resolution: if ``ask_floor`` is True, any ``allow`` verdict is clamped to
    ``ask`` (explicit ``deny`` is preserved).

    Special case for ASK-floor leaves (foreign inline code / foreign heredoc sinks):
    these often contain embedded newlines or other content that confuses the PEG
    grammar and the newline guard in ``match_command``.  For these leaves we
    resolve the outer command only (first token + flag up to the inline-code arg)
    to check for explicit denies; allows are clamped to ASK by the floor.

    Args:
        leaf: A :class:`~toolguard.parser.multiline.LeafCommand` to resolve.
        resolve_one: Callable mapping a single command string to
            ``(decision, reason)``.

    Returns:
        ``(decision, reason)`` for the leaf, with ASK floor applied.
    """
    # For ASK-floor leaves (foreign inline code, foreign heredoc sinks),
    # we need to check for explicit denies but clamp allows to ASK.
    # The leaf text may contain embedded newlines (multiline -c arg) that
    # would confuse the PEG grammar and the newline guard.  Resolve only
    # the outer command stub (without the inline payload) for deny checking.
    if leaf.ask_floor:
        outer_cmd = _extract_outer_command(leaf.text)
        decision, reason = resolve_one(outer_cmd)
        if decision == "deny":
            return "deny", reason
        # allow or ask -> clamp to ask
        return "ask", f"ASK floor applied (inline/heredoc foreign code): {outer_cmd}"

    # Use the PEG grammar to further split the leaf into sub-commands
    sub_commands = extract_commands(leaf.text)
    if not sub_commands:
        # Empty leaf -- treat as no-op; should not normally happen
        logger.debug("Empty leaf command after grammar extraction: %r", leaf.text)
        return "deny", "No valid commands found in leaf"

    # Resolve each sub-command and build (decision, reason, cmd) triples.
    # For deny/ask, pre-format the reason with the sub-command context so that
    # _combine_strictest can pass the formatted message through unchanged.
    # For allow, pass the raw reason through so _combine_strictest can build
    # the "cmd -> pattern" summary for the all-allowed case.
    triples: List[Tuple[str, str, str]] = []
    for cmd in sub_commands:
        decision, reason = resolve_one(cmd)
        if decision == "deny":
            formatted = (
                f"Compound command contains denied sub-command: {cmd} ({reason})"
            )
        elif decision == "ask":
            formatted = (
                f"Compound command contains sub-command requiring approval:"
                f" {cmd} ({reason})"
            )
        else:
            # allow: pass raw reason through for "cmd -> pattern" formatting
            formatted = reason
        triples.append((decision, formatted, cmd))

    # Route through the ONE strictest-wins combinator.
    return _combine_strictest(triples)


def _extract_outer_command(leaf_text: str) -> str:
    """Extract the outer command from a leaf that may contain inline code.

    For ``<executor> -c "<code>"`` leaves, returns just the executor + flag
    without the code (e.g., ``uv run python -c``).  For heredoc sentinel
    leaves, returns the command up to and including the sentinel.

    This is used to check for explicit deny patterns on the outer command
    without being confused by embedded newlines in the inline code.

    Args:
        leaf_text: The leaf command text (may contain embedded newlines).

    Returns:
        The outer command stub (no embedded newlines), suitable for
        ``match_command``.
    """
    # Remove everything after and including the first quote that comes
    # after a flag like -c/-e/-r.  Walk the tokens to find the inline flag.
    tokens = leaf_text.split()
    result_tokens = []
    for idx, tok in enumerate(tokens):
        result_tokens.append(tok)
        # If this token is an inline flag, stop here (don't include the code arg)
        if tok in ("-c", "-e", "-r") and idx + 1 < len(tokens):
            break
        # If this token contains or IS the heredoc sentinel, include it and stop
        if "__HEREDOC_TO_" in tok:
            break
    return " ".join(result_tokens)


def _combine_strictest(results: List[Tuple[str, str, str]]) -> Tuple[str, str]:
    """Combine a list of (decision, reason, leaf_text) tuples with strictest-wins.

    Priority: deny > ask > allow.

    For the all-allowed case with multiple leaves, the combined reason uses the
    ``"cmd -> pattern"`` format (e.g. ``"git status -> git *"``), matching the
    expected log output and test format.

    Args:
        results: List of ``(decision, reason, leaf_text)`` triples where
            ``leaf_text`` is the original command text for the element.

    Returns:
        The single strictest ``(decision, reason)`` tuple.
    """
    denied = [(d, r, t) for d, r, t in results if d == "deny"]
    asked = [(d, r, t) for d, r, t in results if d == "ask"]
    allowed = [(d, r, t) for d, r, t in results if d == "allow"]

    if denied:
        _d, r, _t = denied[0]
        return "deny", r
    if asked:
        _d, r, _t = asked[0]
        return "ask", r
    if allowed:
        if len(allowed) == 1:
            _d, r, _t = allowed[0]
            return "allow", r
        # Multiple allowed leaves: build "cmd -> pattern" summary.
        match_details = []
        for _d, r, leaf_text in allowed:
            # Extract the pattern from the leaf reason.  The leaf reason may be
            # in one of two forms:
            #   "Command matches allow pattern: <pat>"  (from check_permission)
            #   "cmd -> <pat>"  (already formatted by _resolve_leaf)
            if " -> " in r:
                # Already in "cmd -> pattern" format: use as-is or reformat.
                # If leaf_text is the cmd part, use that for clarity.
                pattern_part = r.split(" -> ", 1)[-1]
                cmd_part = (
                    leaf_text.strip().rstrip(";").strip() or r.split(" -> ", 1)[0]
                )
                match_details.append(f"{cmd_part} -> {pattern_part}")
            elif ": " in r:
                pattern_part = r.split(": ", 1)[1]
                cmd_part = leaf_text.strip().rstrip(";").strip() or "?"
                match_details.append(f"{cmd_part} -> {pattern_part}")
            else:
                match_details.append(r)
        return (
            "allow",
            f"All {len(allowed)} sub-commands allowed: [{', '.join(match_details)}]",
        )
    return "deny", "No commands to evaluate"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_compound_permission(
    command: str,
    allow_patterns: List[str],
    deny_patterns: List[str],
    ask_patterns: List[str] = None,
    extended_syntax: bool = True,
) -> Tuple[str, str]:
    """Check permissions for a compound bash command.

    Extracts individual commands from a compound command line and checks each
    against the permission patterns.  Returns the strictest permission decision:

    - If ANY command is denied -> deny the entire command.
    - Else if ANY command requires ask -> ask for the entire command.
    - Else if ALL commands are allowed -> allow the entire command.

    Delegates to :func:`resolve_compound_permission` with a simple
    ``check_permission`` closure.

    Args:
        command: The bash command line (may be compound or multi-line).
        allow_patterns: Patterns that allow commands.
        deny_patterns: Patterns that deny commands.
        ask_patterns: Reserved for future use.
        extended_syntax: If False, skip ``[regex]``/``[glob]``/``[native]``
            prefix parsing.

    Returns:
        ``(decision, reason)`` where *decision* is ``'allow'``, ``'deny'``,
        or ``'ask'``.
    """
    return resolve_compound_permission(
        command,
        lambda c: check_permission(c, allow_patterns, deny_patterns, extended_syntax),
    )


def resolve_compound_permission(
    command: str,
    resolve_one: Callable[[str], Tuple[str, str]],
) -> Tuple[str, str]:
    """Resolve a compound command where each sub-command cascades independently.

    Each extracted sub-command is resolved through ``resolve_one`` -- typically
    a closure over
    :meth:`toolguard.config.Configuration.resolve_permission_detailed`, so every
    sub-command independently runs the full more-specific-wins level cascade.
    The compound is allowed iff ALL sub-commands resolve to allow; otherwise the
    strictest outcome wins (any deny -> deny, then any ask -> ask).

    TOO-17: Multi-line input is fully pre-processed via
    :func:`toolguard.parser.multiline.extract_structured` before the per-leaf
    grammar step.  Undecidable segments (complex control structures, process
    substitution, foreign inline code without an explicit deny) resolve to ASK
    rather than failing open.

    Args:
        command: The bash command line (may be compound or multi-line).
        resolve_one: Callable mapping a single sub-command string to its
            resolved ``(decision, reason)`` (cascaded across config levels).

    Returns:
        ``(decision, reason)``. For an all-allowed compound the reason lists
        per-sub-command matched rules, matching the legacy format the hook logs.
    """
    structured = extract_structured(command)

    if not structured:
        return "deny", "No valid commands found in command line"

    # Resolve each element and collect results.
    # Each entry is (decision, reason, leaf_text) where leaf_text is the
    # original element text (used to build combined "cmd -> pattern" reason).
    all_results: List[Tuple[str, str, str]] = []

    for element in structured:
        if isinstance(element, UndecidableSegment):
            # Cannot safely decompose -> ASK
            logger.debug(
                "Undecidable segment (-> ask): %r reason=%s",
                element.original[:80],
                element.reason,
            )
            all_results.append(
                (
                    "ask",
                    f"Undecidable segment ({element.reason}): {element.original[:80]}",
                    element.original,
                )
            )
        elif isinstance(element, LeafCommand):
            d, r = _resolve_leaf(element, resolve_one)
            all_results.append((d, r, element.text))
        else:
            # Should not happen
            logger.warning("Unknown extraction result type: %r", type(element))
            all_results.append(("ask", "Unknown extraction result; cannot verify", ""))

    return _combine_strictest(all_results)


def get_command_breakdown(command: str) -> List[str]:
    """Get a breakdown of individual commands from a compound command.

    Utility for debugging and logging.  Returns only the textual leaf commands
    (undecidable segments are represented by their ``original`` text).

    Args:
        command: The bash command line to break down.

    Returns:
        List of individual command strings.
    """
    structured = extract_structured(command)
    result = []
    for element in structured:
        if isinstance(element, LeafCommand):
            # Further split by PEG grammar
            result.extend(extract_commands(element.text))
        elif isinstance(element, UndecidableSegment):
            result.append(element.original)
    return result
