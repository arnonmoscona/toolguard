"""
Hierarchy operations on a config: move a rule between layers, and find rules a
broader layer already duplicates.  Allow-list rules only.

Layers are ordered by ``Provenance.specificity`` (``0`` = most specific,
project-level) and resolve most-specific-wins.

1. **Migration** -- :func:`migrate_config` relocates an allow rule between
   layers, typically promoting one from a project layer UP to the user layer so
   it applies everywhere.  :func:`evaluate_migration` replays a corpus across the
   before/after pair.  The point of a promotion -- the rule now applying in every
   OTHER context the destination layer governs -- lies outside any corpus, so it
   is described in prose in ``MigrationEffect.scope_note`` for a human to weigh.

2. **Cross-layer redundancy** -- :func:`find_cross_layer_redundancies` reports an
   allow rule whose normalised body also appears in a layer that would decide in
   its place once dropped -- a broader layer, or the earlier occurrence of a
   same-specificity duplicate.  Purely static: it reads allow, deny and ask
   lists and replays nothing.  Its findings are candidates for review, NOT
   verified-safe deletions -- see that function.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from toolguard.config import Configuration, Provenance
from toolguard.tools.config_access import per_layer_rules, with_layer_allow_replaced
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.redundancy import _normalised_body
from toolguard.tools.replay import replay


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchyMigration:
    """
    A proposal to move an allow rule from one config layer to another.

    Attributes:
        tool: Tool the rule applies to (e.g. ``'Bash'``).
        list_type: Permission list the rule belongs to.  Recorded but not acted
            on -- :func:`migrate_config` edits the allow list whatever this says.
        pattern: Wrapper-free pattern body to move (e.g. ``'git status:*'``).
        from_provenance: The layer the rule currently lives in.
        to_provenance: The layer to move it to.  Any automated target selection
            must exclude ``source_type == "toolguard_hook_rules"`` layers: those
            sit at the SAME specificity as ``~/.claude``, so a plain "pick a
            broader layer" step can land in the user's hand-curated
            rules-directory files, which toolguard must never write to unasked.
        rationale: Human-readable reason for the move.
    """

    tool: str
    list_type: str
    pattern: str
    from_provenance: Provenance
    to_provenance: Provenance
    rationale: str


@dataclass(frozen=True)
class MigrationEffect:
    """
    The replay-measured effect of a :class:`HierarchyMigration`.

    Attributes:
        migration: The migration that was evaluated.
        changed_count: Corpus entries whose verdict changed (broadened + tightened).
        broadened_count: Entries that became looser.
        tightened_count: Entries that became stricter.
        decision_neutral: ``True`` when no corpus entry's verdict changed,
            ``None`` when the corpus was empty -- neutrality is not a
            meaningful claim about zero examined entries, so an empty corpus
            must not read the same as a replayed-and-unchanged one.  Not a
            safety verdict even when ``True``, and even for the current
            context: a command the corpus never recorded can still flip.
            Measured -- with a project ``git:*`` allow and an intermediate
            ``git push:*`` deny, promoting ``git:*`` to an empty user layer
            over a corpus holding only ``git status`` is reported neutral
            while ``git push`` goes from ``allow`` to ``deny``.
        scope_note: Human-readable note about how the move changes the rule's
            scope beyond what the corpus can show (e.g. promotion to a broader
            layer applies the rule to other projects too).
    """

    migration: HierarchyMigration
    changed_count: int
    broadened_count: int
    tightened_count: int
    decision_neutral: Optional[bool]
    scope_note: str


@dataclass(frozen=True)
class CrossLayerRedundancy:
    """
    An allow rule whose normalised body also appears in a layer that would
    decide in its place once this copy is dropped.

    Attributes:
        tool: Tool the rule applies to.
        pattern: The redundant copy's pattern body.
        redundant_provenance: The layer holding the redundant copy.
        covered_by_provenance: The layer that would take over: a broader one,
            or the earlier occurrence of a same-specificity duplicate.
        note: Human-readable explanation.
    """

    tool: str
    pattern: str
    redundant_provenance: Provenance
    covered_by_provenance: Provenance
    note: str


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


def migrate_config(
    config: Configuration, migration: HierarchyMigration
) -> Configuration:
    """
    Build a synthetic config with the rule moved between layers.

    Removes ``migration.pattern`` from ``from_provenance``'s allow list and
    appends it to ``to_provenance``'s.  Nothing on disk is touched.

    Args:
        config: The original configuration.
        migration: The migration to apply.

    Returns:
        A new :class:`Configuration` with the rule relocated.

    Raises:
        ValueError: When ``migration.list_type`` is not ``'allow'`` -- this
            module moves allow-list rules only, and silently editing the
            allow list for a migration that CLAIMS to move a different list
            would misdescribe the change.  Also raised when
            ``migration.to_provenance`` matches no layer in ``config``:
            without this check the removal from ``from_provenance`` still
            lands while the addition silently no-ops, losing the rule.
    """
    if migration.list_type != "allow":
        raise ValueError(
            f"migrate_config only moves allow-list rules, got "
            f"list_type={migration.list_type!r}"
        )
    target_present = any(
        lr.provenance == migration.to_provenance
        for lr in per_layer_rules(config, migration.tool)
    )
    if not target_present:
        raise ValueError(
            f"migration target {migration.to_provenance.describe()!r} "
            f"matches no layer in the config"
        )
    removed = with_layer_allow_replaced(
        config, migration.tool, migration.from_provenance, {migration.pattern}, []
    )
    return with_layer_allow_replaced(
        removed, migration.tool, migration.to_provenance, set(), [migration.pattern]
    )


def _scope_note(migration: HierarchyMigration) -> str:
    """Describe how a migration changes a rule's scope, beyond what a corpus can show."""
    from_locus = migration.from_provenance.describe()
    to_locus = migration.to_provenance.describe()
    from_spec = migration.from_provenance.specificity
    to_spec = migration.to_provenance.specificity

    if to_spec > from_spec:
        return (
            f"Promotion: moving up from {from_locus} to the broader {to_locus}. "
            f"The rule will then apply in EVERY context {to_locus} governs "
            f"(other projects/directories), which a single corpus cannot verify."
        )
    if to_spec < from_spec:
        return (
            f"Demotion: moving down from {from_locus} to the narrower {to_locus}. "
            f"The rule will stop applying in contexts outside {to_locus}."
        )
    return f"Same-level move from {from_locus} to {to_locus} (no scope change)."


def migration_effect_to_dict(effect: MigrationEffect) -> Dict[str, object]:
    """
    Serialise a :class:`MigrationEffect` into a JSON-able dict.

    The form ``toolguard-audit --migrations`` ingests, so a judgement layer can
    weigh a proposed, not-yet-enacted move: ``decision_neutral`` is corpus
    evidence, never a statement about intent.  See technical-notes.md,
    "As-if-enacted review: ``--edits`` vs ``--migrations``".

    Args:
        effect: The evaluated migration effect.

    Returns:
        A dict with the migration's identity (tool, list_type, pattern, from/to
        locus and specificity), the replay-measured counts, the neutrality flag,
        the scope note, and the rationale.
    """
    migration = effect.migration
    return {
        "tool": migration.tool,
        "list_type": migration.list_type,
        "pattern": migration.pattern,
        "from_locus": migration.from_provenance.describe(),
        "to_locus": migration.to_provenance.describe(),
        "from_specificity": migration.from_provenance.specificity,
        "to_specificity": migration.to_provenance.specificity,
        "rationale": migration.rationale,
        "decision_neutral": effect.decision_neutral,
        "changed_count": effect.changed_count,
        "broadened_count": effect.broadened_count,
        "tightened_count": effect.tightened_count,
        "scope_note": effect.scope_note,
    }


def evaluate_migration(
    config: Configuration,
    migration: HierarchyMigration,
    corpus: List[LogEntry],
) -> MigrationEffect:
    """
    Replay-measure the effect of a hierarchy migration on a corpus.

    A non-neutral result means at least one recorded command resolves differently
    after the move -- inspect before moving.  A neutral one is weaker evidence
    than it looks: see :class:`MigrationEffect`'s ``decision_neutral``.

    Args:
        config: The current configuration.
        migration: The migration to evaluate.
        corpus: The command corpus to measure against.

    Returns:
        A :class:`MigrationEffect` with change counts, a neutrality flag, and a
        scope note.
    """
    config_b = migrate_config(config, migration)
    diff = replay(corpus, config, config_b)
    changed = diff.broadened_count + diff.tightened_count
    return MigrationEffect(
        migration=migration,
        changed_count=changed,
        broadened_count=diff.broadened_count,
        tightened_count=diff.tightened_count,
        decision_neutral=(changed == 0) if corpus else None,
        scope_note=_scope_note(migration),
    )


# ---------------------------------------------------------------------------
# Cross-layer redundancy
# ---------------------------------------------------------------------------


#: A layer's position in the ordered layer list, used to break ties between
#: two layers sharing a specificity -- discovery lists same-tier layers in
#: resolution order, so an earlier position wins and a later duplicate is dead.
_Order = Tuple[int, int]


def _nearest_broader_cover(
    coverage: Dict[Tuple[str, str], List[Tuple[_Order, Provenance]]],
    key: Tuple[str, str],
    order: _Order,
) -> Optional[Tuple[_Order, Provenance]]:
    """
    Return the nearest layer that would decide instead of ``order`` if its own
    copy were dropped, or None.

    A layer covers when it resolves LATER than ``order``: a strictly broader
    specificity, or the same specificity at a later position (same-tier layers
    are checked in list order, so an earlier occurrence decides and a later
    one is dead weight -- "covers" here means "the earlier one covers the
    later, dead, duplicate"). "Nearest" is the smallest such order.

    Args:
        coverage: Map of normalised key -> list of ``(order, provenance)``.
        key: The normalised pattern key to look up.
        order: The ``(specificity, position)`` of the occurrence being checked.

    Returns:
        The covering ``(order, Provenance)``, or ``None`` when nothing covers it.
    """
    later = [item for item in coverage.get(key, ()) if item[0] > order]
    if not later:
        return None
    return min(later, key=lambda item: item[0])


def _intervening_deny_or_ask(
    blocking: Dict[Tuple[str, str], List[int]],
    key: Tuple[str, str],
    redundant_specificity: int,
    cover_specificity: int,
) -> bool:
    """
    True when a deny or ask rule sharing ``key``'s normalised body sits at a
    specificity strictly between the redundant occurrence and its cover.

    Only meaningful across specificities: a same-specificity tie (see
    :func:`_nearest_broader_cover`) has nothing "between" it.  When true,
    dropping the redundant copy would hand the decision to that deny/ask
    layer instead of to the reported cover, changing the outcome.

    Args:
        blocking: Map of normalised key -> specificities holding a deny/ask
            rule with that body.
        key: The normalised pattern key to check.
        redundant_specificity: Specificity of the occurrence considered redundant.
        cover_specificity: Specificity of its reported cover.
    """
    if cover_specificity <= redundant_specificity:
        return False
    return any(
        redundant_specificity < spec < cover_specificity
        for spec in blocking.get(key, ())
    )


def find_cross_layer_redundancies(
    config: Configuration, tool: str
) -> List[CrossLayerRedundancy]:
    """
    Find allow rules whose normalised body a layer that would decide in their
    place also holds.

    Two shapes are reported: a more-specific allow rule a broader layer
    repeats, and a same-specificity duplicate's later occurrence (discovery
    places same-tier layers in resolution order; the earlier one decides).
    Only normalised-EQUAL bodies are matched; cross-layer subsumption via
    globs is not attempted.

    A finding is a candidate for review, not a verified-safe deletion. The
    body match is exact-normalised, not the real matcher, and only a deny/ask
    of the SAME normalised body is checked for interference -- an intervening
    rule that matches the same real commands through a different pattern
    shape is invisible here.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).

    Returns:
        A list of :class:`CrossLayerRedundancy` findings.

    Raises:
        ValueError: When ``config`` has no layers at all -- there is nothing
            to scan, which must not read the same as a genuine clean scan.
    """
    layers = per_layer_rules(config, tool)
    if not layers:
        raise ValueError(f"cannot scan {tool!r}: config has no layers")

    coverage: Dict[Tuple[str, str], List[Tuple[_Order, Provenance]]] = defaultdict(list)
    blocking: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for position, lr in enumerate(layers):
        for pattern in lr.allow:
            key = _normalised_body(pattern, fold_case=False)
            coverage[key].append(((lr.provenance.specificity, position), lr.provenance))
        for pattern in (*lr.deny, *lr.ask):
            key = _normalised_body(pattern, fold_case=False)
            blocking[key].append(lr.provenance.specificity)

    findings: List[CrossLayerRedundancy] = []
    for position, lr in enumerate(layers):
        for pattern in lr.allow:
            key = _normalised_body(pattern, fold_case=False)
            cover = _nearest_broader_cover(
                coverage, key, (lr.provenance.specificity, position)
            )
            if cover is None:
                continue
            (cover_specificity, _cover_position), cover_prov = cover
            if _intervening_deny_or_ask(
                blocking, key, lr.provenance.specificity, cover_specificity
            ):
                continue
            findings.append(
                CrossLayerRedundancy(
                    tool=tool,
                    pattern=pattern,
                    redundant_provenance=lr.provenance,
                    covered_by_provenance=cover_prov,
                    note=(
                        f"'{pattern}' at {lr.provenance.describe()} is also present "
                        f"at {cover_prov.describe()}, which would decide in its "
                        f"place if this copy were removed. No deny/ask rule with "
                        f"the same normalised body sits between them, but that is "
                        f"not a full safety check -- review before removing."
                    ),
                )
            )
    return findings
