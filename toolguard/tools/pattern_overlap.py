"""
DEFAULT-pattern command-prefix overlap helpers.

These are shared between the consolidation engine (which uses them for broadening
guard-overlap evidence) and the clarity analyzer (which uses them for same-file
rule-interaction detection), so the overlap semantics live in exactly one place.
Only DEFAULT ``cmd:*``/``cmd:**`` prefix patterns are analysed; ``[regex]``/
``[glob]``/``[native]`` patterns are out of scope here (their command-space is
not prefix-comparable).
"""

from typing import List, Optional, Tuple

from toolguard.patterns import PatternType, parse_pattern


def split_default_body(body: str) -> Tuple[List[str], str]:
    """
    Split a DEFAULT pattern body into ``(cmd_tokens, args_part)``.

    Splits on the FIRST ``:`` in ``body``.  The left side is stripped and
    tokenised on whitespace; the right side is stripped and returned as-is.
    If no ``:`` is present, ``args_part`` is the empty string.

    Args:
        body: Wrapper-free DEFAULT pattern body (e.g. ``'git diff:*'``).

    Returns:
        Tuple of ``(cmd_tokens, args_part)`` where ``cmd_tokens`` is a list of
        whitespace-split tokens from the command portion and ``args_part`` is
        the args portion (e.g. ``'*'``).
    """
    if ":" in body:
        colon_idx = body.index(":")
        cmd_part = body[:colon_idx].strip()
        args_part = body[colon_idx + 1 :].strip()
    else:
        cmd_part = body.strip()
        args_part = ""
    return cmd_part.split(), args_part


def default_prefix_tokens(body: str) -> Optional[List[str]]:
    """
    Return the command-prefix tokens of a DEFAULT ``cmd:*``/``cmd:**`` pattern.

    Args:
        body: A wrapper-free pattern body.

    Returns:
        The command tokens (e.g. ``['uv', 'run', 'alembic']``) when ``body`` is a
        DEFAULT prefix pattern with a ``*``/``**`` argument tail, else ``None``
        (non-DEFAULT patterns are not analysed for overlap here).
    """
    ptype, inner = parse_pattern(body, extended_syntax=True)
    if ptype != PatternType.DEFAULT:
        return None
    cmd_tokens, args_part = split_default_body(inner)
    if not cmd_tokens or args_part not in ("*", "**"):
        return None
    return cmd_tokens


def prefixes_overlap(a: List[str], b: List[str]) -> bool:
    """
    Return whether two DEFAULT command prefixes share a command.

    Two prefix patterns match a common command exactly when one token sequence is
    a prefix of the other (e.g. ``['uv','run']`` and ``['uv','run','alembic']``
    both match ``uv run alembic ...``).

    Args:
        a: First command-prefix token list.
        b: Second command-prefix token list.

    Returns:
        ``True`` when their command-spaces intersect.
    """
    n = min(len(a), len(b))
    return a[:n] == b[:n]
