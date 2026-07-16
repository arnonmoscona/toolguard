"""
Self-integrity hard-deny protection: stop ~/.toolguard from ever being deleted
by a Bash command, even one the installing agent decides to run on its own
initiative.

``~/.toolguard`` holds the install journal, config/settings backups, the
decision ledger, crash reports, and session-trace dumps -- the entire audit
trail this project relies on for a reliable, reversible install/uninstall.
docs/uninstall.md has repeatedly and explicitly said "do not delete
``~/.toolguard/``" across several real-install rounds (TOO-15), yet a real
install still deleted it wholesale: the agent decided, unprompted, that
`rm -rf ~/.toolguard` was part of "going further for a true clean slate,"
directly contradicting that documented policy. Prose warnings alone were not
enough to prevent this.

This module is the single source of truth for the ``[hard_deny]`` pattern(s)
that make this a TECHNICAL guarantee instead of a documentation request:
``[hard_deny]`` cannot be overridden by any level's normal allow, so even an
agent that has (mis)judged deleting ``~/.toolguard`` to be helpful is blocked
by toolguard's own enforcement -- independent of whether takeover is enabled,
independent of the session's own permission mode, and independent of the
agent's own judgment in the moment.

Design guard-rails:

- **Substring match, not exact-path match.** The pattern matches the literal
  substring ``.toolguard`` anywhere after ``rm``/``find ... -delete``, rather
  than trying to enumerate every way ``~``, ``$HOME``, or a resolved absolute
  path could be spelled in the command text (toolguard evaluates the RAW,
  pre-expansion command text, so ``~/.toolguard``, ``$HOME/.toolguard``, and
  ``/Users/x/.toolguard`` are three different literal strings that all need
  to match). This is deliberately broad -- no legitimate operation should
  ever need to ``rm`` anything under ``.toolguard`` via a bare shell command
  in the first place (every real ``toolguard-install``/uninstall action
  writes or removes files directly, in-process, never via a shell ``rm``).
- **Defense in depth, not a perfect guarantee.** Like the existing
  "Sensitive files" hard_deny set in :mod:`toolguard.tools.recommended_protections`,
  this is a strong mitigation against the observed failure mode, not a claim
  that every conceivable deletion path is covered.
- **Seeded unconditionally, early -- not gated on takeover.** Unlike the
  user's OWN secret-protection hard_deny set (an offered, consented choice
  tied to Phase 10.1), this protects toolguard's OWN operational integrity,
  not the user's files -- it is seeded in Phase 4 alongside self-permissions,
  regardless of whether the user ever enables takeover.
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
    """Return the declarative, canonical set of self-integrity ``[hard_deny]`` patterns."""
    return _SELF_INTEGRITY_HARD_DENY_PATTERNS
