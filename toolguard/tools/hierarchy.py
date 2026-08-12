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

2. **Cross-layer redundancy** -- :func:`find_cross_layer_redundancies` reports a
   more-specific allow rule whose normalised body also appears in a broader
   layer.  Purely static: it reads allow lists and replays nothing.  Its findings
   are candidates for review, NOT verified-safe deletions -- see that function.
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
        decision_neutral: ``True`` when no corpus entry's verdict changed.  Not a
            safety verdict, even for the current context: a command the corpus
            never recorded can still flip.  Measured -- with a project ``git:*``
            allow and an intermediate ``git push:*`` deny, promoting ``git:*`` to
            an empty user layer over a corpus holding only ``git status`` is
            reported neutral while ``git push`` goes from ``allow`` to ``deny``.
        scope_note: Human-readable note about how the move changes the rule's
            scope beyond what the corpus can show (e.g. promotion to a broader
            layer applies the rule to other projects too).
    """

    migration: HierarchyMigration
    changed_count: int
    broadened_count: int
    tightened_count: int
    decision_neutral: bool
    scope_note: str


@dataclass(frozen=True)
class CrossLayerRedundancy:
    """
    A more-specific allow rule whose normalised body also appears in a broader layer.

    Attributes:
        tool: Tool the rule applies to.
        pattern: The more-specific pattern body.
        redundant_provenance: The more-specific layer holding it.
        covered_by_provenance: The nearest broader layer holding the same body.
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
    """
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
        decision_neutral=(changed == 0),
        scope_note=_scope_note(migration),
    )


# ---------------------------------------------------------------------------
# Cross-layer redundancy
# ---------------------------------------------------------------------------


def _nearest_broader_cover(
    coverage: Dict[Tuple[str, str], List[Tuple[int, Provenance]]],
    key: Tuple[str, str],
    specificity: int,
) -> Optional[Provenance]:
    """
    Return the nearest strictly-broader layer that also holds ``key``, or None.

    "Broader" means a higher ``specificity`` value (further from the project);
    "nearest" is the smallest such value.  The comparison is strict, so two
    layers sharing a specificity never cover each other.

    Args:
        coverage: Map of normalised key -> list of ``(specificity, provenance)``.
        key: The normalised pattern key to look up.
        specificity: The specificity of the more-specific occurrence.

    Returns:
        The covering :class:`Provenance`, or ``None`` when nothing broader holds it.
    """
    broader = [
        (spec, prov) for spec, prov in coverage.get(key, ()) if spec > specificity
    ]
    if not broader:
        return None
    return min(broader, key=lambda item: item[0])[1]


def find_cross_layer_redundancies(
    config: Configuration, tool: str
) -> List[CrossLayerRedundancy]:
    """
    Find more-specific allow rules whose normalised body a broader layer repeats.

    Only normalised-EQUAL bodies are matched; cross-layer subsumption via globs
    is not attempted.

    A finding is a candidate for review, not a verified-safe deletion.  The scan
    reads allow lists and nothing else, so it cannot see that dropping the
    specific copy hands the decision to a layer that denies or asks the same
    command.  Measured -- with a project ``git push:*`` allow, an intermediate
    ``git push:*`` deny and a user ``git push:*`` allow, this reports the project
    rule as covered by the user rule, and removing it turns ``git push`` from
    ``allow`` into ``deny``.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).

    Returns:
        A list of :class:`CrossLayerRedundancy` findings.
    """
    layers = per_layer_rules(config, tool)

    coverage: Dict[Tuple[str, str], List[Tuple[int, Provenance]]] = defaultdict(list)
    for lr in layers:
        for pattern in lr.allow:
            coverage[_normalised_body(pattern)].append(
                (lr.provenance.specificity, lr.provenance)
            )

    findings: List[CrossLayerRedundancy] = []
    for lr in layers:
        for pattern in lr.allow:
            cover = _nearest_broader_cover(
                coverage, _normalised_body(pattern), lr.provenance.specificity
            )
            if cover is not None:
                findings.append(
                    CrossLayerRedundancy(
                        tool=tool,
                        pattern=pattern,
                        redundant_provenance=lr.provenance,
                        covered_by_provenance=cover,
                        note=(
                            f"'{pattern}' at {lr.provenance.describe()} is also present "
                            f"at the broader {cover.describe()}; the more-specific copy "
                            f"is redundant and can be dropped."
                        ),
                    )
                )
    return findings
