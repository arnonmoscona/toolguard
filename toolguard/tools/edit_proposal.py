"""
General rule-edit proposal model and in-memory application.

An :class:`EditProposal` is one intent -- "narrow this allow", "move this rule" --
expressed as a list of atomic :class:`RuleEdit` operations that may span several
rules, several permission sections (allow / deny / ask) and several hierarchy
layers.  It is the shared form the security audit and the maintenance tooling
exchange proposals in, as data rather than prose.

The model is deliberately mechanical: :func:`apply_edits` composes the
section-generic
:func:`~toolguard.tools.config_access.with_layer_rules_replaced` primitive and
performs NO judgement.  Deciding whether an edit is safe or desirable lives
elsewhere.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from toolguard.config import Configuration, Provenance
from toolguard.tools.config_access import with_layer_rules_replaced

# The intent labels an EditProposal may carry, describing WHY the edit set exists.
# Advisory: this module never validates a proposal's action against the tuple, and
# the mechanics are entirely in the atomic RuleEdits.
ACTION_REMOVE = "remove"
ACTION_REPLACE = "replace"
ACTION_NARROW = "narrow"
ACTION_MOVE = "move"
ACTIONS = (ACTION_REMOVE, ACTION_REPLACE, ACTION_NARROW, ACTION_MOVE)


@dataclass(frozen=True)
class RuleEdit:
    """
    One atomic edit to a single ``(tool, list_type)`` list at a single layer.

    Attributes:
        tool: Tool the edited list belongs to (e.g. ``'Bash'``).
        list_type: Which permission list is edited: ``'allow'``, ``'deny'``, or
            ``'ask'``.
        provenance: The layer whose list is edited.  Matched by whole-``Provenance``
            equality, so an edit differing in any one field -- ``specificity``, or an
            unnormalized ``path`` -- matches no layer and is skipped.
        removed_patterns: Wrapper-free pattern bodies to remove from the list.
        added_patterns: Wrapper-free pattern bodies to append to the list.
    """

    tool: str
    list_type: str
    provenance: Provenance
    removed_patterns: Tuple[str, ...] = ()
    added_patterns: Tuple[str, ...] = ()


@dataclass(frozen=True)
class EditProposal:
    """
    A named, possibly section- and layer-spanning proposed configuration change.

    An :class:`EditProposal` bundles the atomic :class:`RuleEdit` operations that
    together realise one intent -- e.g. a ``replace`` that swaps a broad allow for
    a narrower allow PLUS a targeted deny (two sections), or a ``move`` that
    removes a rule from one layer and adds it to another.

    Attributes:
        action: One of :data:`ACTIONS` -- the intent label (advisory).
        tool: The primary tool the proposal concerns (the edits may still touch
            other tools, but this is the headline).
        rationale: Human-readable reason for the change.
        edits: The atomic edits that make up the proposal, applied in order.
        origin: Optional free-form tag identifying the producer, so a consumer can
            trace where the proposal came from.  Never interpreted here.
        verification: Producer-specific verification state, e.g. a
            :class:`~toolguard.tools.consolidate.SafetyResult` value string
            (``'safe'``, ``'unsafe'``, ``'unverified'``) for a consolidation.
            ``None`` when the producer has no such concept.
    """

    action: str
    tool: str
    rationale: str
    edits: Tuple[RuleEdit, ...]
    origin: str = ""
    verification: Optional[str] = None


def apply_edits(config: Configuration, proposals: List[EditProposal]) -> Configuration:
    """
    Return the configuration that results from enacting ``proposals`` in memory.

    Every :class:`RuleEdit` of every proposal is applied, in order, by composing
    :func:`~toolguard.tools.config_access.with_layer_rules_replaced`.  Nothing is
    written to disk; the result is a synthetic :class:`~toolguard.config.Configuration`
    suitable for as-if-enacted analysis.

    An edit can miss silently.  An unmatched ``provenance`` leaves the config
    untouched, and a ``removed_patterns`` entry that is no longer present is a no-op
    while the same edit's ``added_patterns`` still apply -- so a proposal built
    against an older config can be enacted in part, with nothing in the result
    saying so.

    Args:
        config: The original configuration.
        proposals: The edit proposals to enact, applied in list order.

    Returns:
        A new :class:`~toolguard.config.Configuration`, or ``config`` itself when no
        edit matched a layer.
    """
    result = config
    for proposal in proposals:
        for edit in proposal.edits:
            result = with_layer_rules_replaced(
                result,
                edit.tool,
                edit.provenance,
                edit.list_type,
                set(edit.removed_patterns),
                list(edit.added_patterns),
            )
    return result


# ---------------------------------------------------------------------------
# Serialization -- the JSON form in which proposals are exchanged.
# ---------------------------------------------------------------------------


def _provenance_to_dict(provenance: Provenance) -> Dict[str, Any]:
    """Serialize a :class:`~toolguard.config.Provenance` to a round-trippable dict."""
    return {
        "level": provenance.level,
        "source_type": provenance.source_type,
        "file_format": provenance.file_format,
        "path": str(provenance.path),
        "specificity": provenance.specificity,
    }


def _provenance_from_dict(data: Dict[str, Any]) -> Provenance:
    """Reconstruct a :class:`~toolguard.config.Provenance` from :func:`_provenance_to_dict`."""
    return Provenance(
        level=data["level"],
        source_type=data["source_type"],
        file_format=data["file_format"],
        path=Path(data["path"]),
        specificity=data["specificity"],
    )


def rule_edit_to_dict(edit: RuleEdit) -> Dict[str, Any]:
    """Serialize a :class:`RuleEdit` to a JSON-safe dict."""
    return {
        "tool": edit.tool,
        "list_type": edit.list_type,
        "provenance": _provenance_to_dict(edit.provenance),
        "removed_patterns": list(edit.removed_patterns),
        "added_patterns": list(edit.added_patterns),
    }


def rule_edit_from_dict(data: Dict[str, Any]) -> RuleEdit:
    """Reconstruct a :class:`RuleEdit` from :func:`rule_edit_to_dict`."""
    return RuleEdit(
        tool=data["tool"],
        list_type=data["list_type"],
        provenance=_provenance_from_dict(data["provenance"]),
        removed_patterns=tuple(data.get("removed_patterns", ())),
        added_patterns=tuple(data.get("added_patterns", ())),
    )


def edit_proposal_to_dict(proposal: EditProposal) -> Dict[str, Any]:
    """Serialize an :class:`EditProposal` to a JSON-safe dict."""
    return {
        "action": proposal.action,
        "tool": proposal.tool,
        "rationale": proposal.rationale,
        "origin": proposal.origin,
        "edits": [rule_edit_to_dict(edit) for edit in proposal.edits],
        "verification": proposal.verification,
    }


def edit_proposal_from_dict(data: Dict[str, Any]) -> EditProposal:
    """
    Reconstruct an :class:`EditProposal` from :func:`edit_proposal_to_dict`.

    ``action`` and ``tool`` are required; the other keys default to empty
    (``None`` for ``verification``).
    """
    return EditProposal(
        action=data["action"],
        tool=data["tool"],
        rationale=data.get("rationale", ""),
        edits=tuple(rule_edit_from_dict(e) for e in data.get("edits", ())),
        origin=data.get("origin", ""),
        verification=data.get("verification"),
    )
