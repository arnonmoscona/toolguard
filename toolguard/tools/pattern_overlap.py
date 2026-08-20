"""
Command-prefix overlap tests for DEFAULT ``cmd:*``/``cmd:**`` patterns.

``[regex]``/``[glob]``/``[native]`` patterns are out of scope -- their
command-space is not prefix-comparable -- and :func:`default_prefix_tokens`
returns ``None`` for them.
"""

from typing import List, Optional, Tuple

from toolguard.patterns import PatternType, parse_pattern


def split_default_body(body: str) -> Tuple[List[str], str]:
    """
    Split a DEFAULT pattern body into ``(cmd_tokens, args_part)``.

    The ``:*``/``:**`` shorthand is recognised only when it is the pattern's literal
    end, matching :func:`toolguard.permissions.match_command` and Claude Code's own
    ``:*`` rule: a ``:`` anywhere else -- e.g. inside a URL like
    ``'curl http://ex.com/*'`` -- is a literal character, not a separator. Only that
    trailing ``**``/``*`` is normalized.

    Args:
        body: Wrapper-free DEFAULT pattern body (e.g. ``'git diff:*'``).

    Returns:
        ``(cmd_tokens, args_part)`` -- the command part split on whitespace, and
        ``args_part`` either ``'*'`` or empty (no trailing ``:*``/``:**``).
    """
    if body.endswith(":**"):
        cmd_part = body[: -len(":**")].strip()
        args_part = "*"
    elif body.endswith(":*"):
        cmd_part = body[: -len(":*")].strip()
        args_part = "*"
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
        The command tokens (e.g. ``['uv', 'run', 'alembic']``), or ``None`` when
        *body* is not DEFAULT or does not end in ``:*``/``:**`` -- so a bare ``'ls'``
        gives ``None``.
    """
    ptype, inner = parse_pattern(body, extended_syntax=True)
    if ptype != PatternType.DEFAULT:
        return None
    cmd_tokens, args_part = split_default_body(inner)
    if not cmd_tokens or args_part != "*":
        return None
    return cmd_tokens


def prefixes_overlap(a: List[str], b: List[str]) -> bool:
    """
    Return whether one command-prefix token sequence is a prefix of the other.

    Prefix containment is SUFFICIENT for the patterns those tokens came from to
    match a command in common. It is necessary only for wildcard-free tokens: a
    token carrying an fnmatch wildcard can still match across diverging lists
    (``git c*:*`` and ``git commit:*`` share ``git commit``), so ``False`` is
    not by itself evidence that two patterns are disjoint.

    Args:
        a: First command-prefix token list.
        b: Second command-prefix token list.

    Returns:
        ``True`` when one list is a prefix of the other; an empty list is a
        prefix of anything.
    """
    n = min(len(a), len(b))
    return a[:n] == b[:n]
