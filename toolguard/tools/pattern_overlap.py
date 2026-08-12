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

    The split is on the FIRST ``:``, which is not always the ``cmd:args``
    separator: ``'curl http://ex.com/*'`` splits at the colon inside the URL,
    giving ``(['curl', 'http'], '//ex.com/*')``.
    :func:`toolguard.permissions.match_command` splits a DEFAULT pattern on the
    first ``:`` too, so making this one smarter alone would put the two out of
    step.

    Args:
        body: Wrapper-free DEFAULT pattern body (e.g. ``'git diff:*'``).

    Returns:
        ``(cmd_tokens, args_part)`` -- the command part split on whitespace, and
        the stripped args part, empty when ``body`` holds no ``:``.
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
        The command tokens (e.g. ``['uv', 'run', 'alembic']``), or ``None`` when
        *body* is not DEFAULT or its args part is anything other than ``*`` or
        ``**`` -- so ``'git commit:-m *'`` and a bare ``'ls'`` both give ``None``.
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
    Return whether one command-prefix token sequence is a prefix of the other.

    Prefix containment is SUFFICIENT for the patterns those tokens came from to
    match a command in common, but not necessary -- so ``False`` here is not
    evidence that they are disjoint.
    :func:`toolguard.permissions.match_command` glues the trailing ``*`` onto
    the last token with no separator, so ``git commit:*`` and
    ``git commit-tree:*`` both match ``git commit-tree abc`` while their token
    lists diverge at the second token.

    Args:
        a: First command-prefix token list.
        b: Second command-prefix token list.

    Returns:
        ``True`` when one list is a prefix of the other; an empty list is a
        prefix of anything.
    """
    n = min(len(a), len(b))
    return a[:n] == b[:n]
