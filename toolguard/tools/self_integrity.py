"""
The canonical ``[hard_deny]`` patterns protecting ``~/.toolguard`` -- toolguard's
own state and audit trail -- from deletion by a Bash command.

These exist because the documented "do not delete ``~/.toolguard``" warning was
not enough: during a real install an agent decided, unprompted, that
``rm -rf ~/.toolguard`` was part of a clean slate. A ``[hard_deny]`` match is
not overridable by a normal allow at any level, so the protection does not
depend on the agent's judgement in the moment.

Deliberately a substring match on ``.toolguard`` rather than an enumeration of
paths: matching happens on the RAW, pre-expansion command text, so
``~/.toolguard``, ``$HOME/.toolguard`` and ``/home/x/.toolguard`` are three
different literal strings. Deliberately broad, too: nothing in toolguard removes
files through a shell ``rm``, so a false positive here costs nothing.

Defense in depth, not a guarantee -- e.g. ``sudo rm -rf ~/.toolguard`` and
``/bin/rm -rf ~/.toolguard`` match neither pattern.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class SelfIntegrityProtection:
    """
    One ``[hard_deny]`` pattern protecting toolguard's own state directory.

    Attributes:
        pattern: The full wrapped permission pattern (e.g.
            ``'Bash([regex]...)'``), ready to be appended verbatim to a
            ``[hard_deny]`` ``deny`` list.
        rationale: Short, human-readable reason the pattern is needed.
    """

    pattern: str
    rationale: str


_SELF_INTEGRITY_HARD_DENY_PATTERNS: Tuple[SelfIntegrityProtection, ...] = (
    SelfIntegrityProtection(
        pattern=r"Bash([regex]^rm\b.*\.toolguard)",
        rationale=(
            "Blocks any rm command (rm, rm -rf, rm -r, etc.) whose arguments "
            "reference .toolguard, regardless of whether it is spelled as "
            "~/.toolguard, $HOME/.toolguard, or a resolved absolute path -- "
            "the exact command that deleted a real install's state directory."
        ),
    ),
    SelfIntegrityProtection(
        pattern=r"Bash([regex]^find\b.*\.toolguard.*-delete)",
        rationale=(
            "Blocks the find ... -delete form of the same deletion, which rm "
            "alone does not catch."
        ),
    ),
)


def required_self_integrity_hard_deny_patterns() -> Tuple[SelfIntegrityProtection, ...]:
    """Return the canonical set of self-integrity ``[hard_deny]`` patterns."""
    return _SELF_INTEGRITY_HARD_DENY_PATTERNS
