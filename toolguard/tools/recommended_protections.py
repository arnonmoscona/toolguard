"""
Recommended [hard_deny] protections: the curated "Sensitive files" pattern set.

A fail-closed (takeover) setup is a good moment to add ``[hard_deny]`` protections for
credentials: the ``[hard_deny]`` pool is checked before the normal cascade, so a
``[permissions]`` allow at any level does not override it.

Declarative only: nothing here writes. The write happens elsewhere, after explicit user
consent (docs/install.md Phase 10.1: "Offer it; do not add it silently.").
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


#: The canonical "Sensitive files" set, copied verbatim from docs/security.md's
#: "Recommended deny patterns" section: 12 relative (project-anchored) patterns followed
#: by their 12 home-anchored (``~/...``) siblings -- see that doc's "Why both forms of the
#: sensitive-file patterns are needed" for why both are here. Each of the four sensitive
#: families is covered for all three file tools: Write and Edit both modify a file, so
#: covering one and not the other leaves the protection a user was offered incomplete.
#: Composing this list freehand at install time is what the module exists to avoid, so
#: extending or trimming it is a reviewed change made here and in docs/security.md
#: together.
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
        pattern="Write(**/.env.*)",
        rationale=(
            "Prevents a command from silently planting or altering secrets under a "
            "variant name (e.g. .env.local) the exact-.env deny does not cover."
        ),
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
        pattern="Edit(**/.env.*)",
        rationale=(
            "Edit sibling of the .env variant write-deny: Edit modifies the file too, "
            "so leaving it uncovered reopens what that deny closes."
        ),
    ),
    RecommendedProtection(
        pattern="Edit(**/.aws/**)",
        rationale=(
            "Edit sibling of the AWS credentials write-deny: appending to a credentials "
            "file in place is a modification the write-deny alone does not stop."
        ),
    ),
    RecommendedProtection(
        pattern="Edit(**/.ssh/**)",
        rationale=(
            "Edit sibling of the SSH key write-deny: appending a key to authorized_keys "
            "in place is a modification the write-deny alone does not stop."
        ),
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
        pattern="Write(~/.env.*)",
        rationale=(
            "Home-anchored form of the .env variant write-deny above: prevents a "
            "command from planting ~/.env.local, ~/.env.production, etc. regardless "
            "of which project is active."
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
    RecommendedProtection(
        pattern="Edit(~/.env.*)",
        rationale=(
            "Home-anchored form of the .env variant edit-deny above: protects "
            "~/.env.local, ~/.env.production, etc. from in-place edits regardless "
            "of which project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Edit(~/.aws/**)",
        rationale=(
            "Home-anchored form of the AWS credentials edit-deny above: protects "
            "~/.aws/** from in-place edits regardless of which project is active."
        ),
    ),
    RecommendedProtection(
        pattern="Edit(~/.ssh/**)",
        rationale=(
            "Home-anchored form of the SSH key edit-deny above: protects "
            "~/.ssh/** -- ~/.ssh/authorized_keys above all -- from in-place edits "
            "regardless of which project is active."
        ),
    ),
)


def required_hard_deny_patterns() -> Tuple[RecommendedProtection, ...]:
    """Return the declarative, canonical set of recommended ``[hard_deny]`` patterns."""
    return _RECOMMENDED_HARD_DENY_PATTERNS
