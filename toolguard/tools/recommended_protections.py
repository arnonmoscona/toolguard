"""
Recommended [hard_deny] protections: the curated "Sensitive files" pattern set.

A fail-closed (takeover) setup is a good moment to add ``[hard_deny]`` protections for
credentials -- ``[hard_deny]`` cannot be overridden by any level, so it is the strongest
guarantee toolguard offers. Freehand ``[hard_deny]`` patterns are exactly the kind of
thing an agent can get subtly wrong (a near-miss on this happened during a real
install), and a mistake there is hard to walk back unnoticed.

This module is the SINGLE SOURCE OF TRUTH for the canonical "Sensitive files" set
documented in docs/security.md ("Recommended deny patterns" -> "Sensitive files"),
copied here verbatim. ``toolguard-install seed-hard-deny`` (see
:mod:`toolguard.tools.installer`) reads this list and writes exactly these patterns --
it never composes ``[hard_deny]`` TOML by hand.

Design guard-rails (mirrors :mod:`toolguard.tools.self_permission`):

- **Declarative only, no I/O.** This module does not write anything; the write is
  always performed elsewhere, after explicit user consent (docs/install.md Phase 10.1:
  "Offer it; do not add it silently.").
- **Fixed set, not user-editable here.** Extending or trimming this list is a
  deliberate, reviewed change to this module (and to docs/security.md, which must stay
  in sync) -- never an ad hoc addition by an agent at install time.
"""

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class RecommendedProtection:
    """
    One canonical ``[hard_deny]`` pattern from docs/security.md's "Sensitive files" set.

    Attributes:
        pattern: The full wrapped permission pattern (e.g. ``'Read(**/.env)'``), ready
            to be appended verbatim to a ``[hard_deny]`` ``deny`` list.
        rationale: Short, human-readable reason the pattern is recommended.
    """

    pattern: str
    rationale: str


# The canonical "Sensitive files" set, copied verbatim from docs/security.md's
# "Recommended deny patterns" section: the 8 original relative (project-anchored)
# patterns followed by their 8 home-anchored (~/...) siblings -- see that doc's "Why
# both forms of the sensitive-file patterns are needed" for the rationale. Keep this
# list and that doc in sync; do not extend or trim it here without updating
# docs/security.md to match.
_RECOMMENDED_HARD_DENY_PATTERNS: Tuple[RecommendedProtection, ...] = (
    RecommendedProtection(
        pattern="Read(**/.env)",
        rationale="Environment files commonly hold API keys and secrets.",
    ),
    RecommendedProtection(
        pattern="Read(**/.env.*)",
        rationale=(
            "Environment file variants (e.g. .env.local, .env.production) commonly "
            "hold API keys and secrets."
        ),
    ),
    RecommendedProtection(
        pattern="Read(**/.aws/**)",
        rationale="AWS credential files grant cloud account access if leaked.",
    ),
    RecommendedProtection(
        pattern="Read(**/.ssh/**)",
        rationale="SSH keys grant direct access to other systems if leaked.",
    ),
    RecommendedProtection(
        pattern="Write(**/.env)",
        rationale="Prevents a command from silently planting or altering secrets.",
    ),
    RecommendedProtection(
        pattern="Write(**/.aws/**)",
        rationale="Prevents a command from silently altering AWS credentials.",
    ),
    RecommendedProtection(
        pattern="Write(**/.ssh/**)",
        rationale="Prevents a command from silently altering SSH keys.",
    ),
    RecommendedProtection(
        pattern="Edit(**/.env)",
        rationale="Prevents a command from silently editing secrets in place.",
    ),
    RecommendedProtection(
        pattern="Read(~/.env)",
        rationale=(
            "Home-anchored form of the .env read-deny above: relative patterns are "
            "anchored to the active project root, so they only protect a copy of "
            "the secret inside the current project. This form protects ~/.env "
            "regardless of which project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Read(~/.env.*)",
        rationale=(
            "Home-anchored form of the .env variant read-deny above: protects "
            "~/.env.local, ~/.env.production, etc. regardless of which project is "
            "active."
        ),
    ),
    RecommendedProtection(
        pattern="Read(~/.aws/**)",
        rationale=(
            "Home-anchored form of the AWS credentials read-deny above: protects "
            "~/.aws/** regardless of which project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Read(~/.ssh/**)",
        rationale=(
            "Home-anchored form of the SSH key read-deny above: protects "
            "~/.ssh/** regardless of which project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Write(~/.env)",
        rationale=(
            "Home-anchored form of the .env write-deny above: prevents a command "
            "from silently planting or altering ~/.env regardless of which "
            "project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Write(~/.aws/**)",
        rationale=(
            "Home-anchored form of the AWS credentials write-deny above: prevents "
            "a command from silently altering ~/.aws/** regardless of which "
            "project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Write(~/.ssh/**)",
        rationale=(
            "Home-anchored form of the SSH key write-deny above: prevents a "
            "command from silently altering ~/.ssh/** regardless of which "
            "project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Edit(~/.env)",
        rationale=(
            "Home-anchored form of the .env edit-deny above: prevents a command "
            "from silently editing ~/.env in place regardless of which project is "
            "active."
        ),
    ),
)


def required_hard_deny_patterns() -> Tuple[RecommendedProtection, ...]:
    """Return the declarative, canonical set of recommended ``[hard_deny]`` patterns."""
    return _RECOMMENDED_HARD_DENY_PATTERNS
