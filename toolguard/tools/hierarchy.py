"""
Hierarchy migration: move a rule up (or down) the config hierarchy, and detect
rules made redundant by an identical rule in a broader layer.

Toolguard resolves permissions across a hierarchy of layers ordered by
``Provenance.specificity`` (``0`` = most specific / project-level, higher =
broader / user-level), most-specific-wins.  Two hierarchy operations live here:

1. **Promotion / migration** -- move an allow rule from one layer to another
   (typically a more-specific project layer UP to a broader user layer, so it
   applies everywhere).  :func:`evaluate_migration` builds the migrated config
   and replays the corpus to confirm the move is DECISION-NEUTRAL for the current
   context; the genuine effect of a promotion -- broadening the rule to *other*
   contexts the broader layer governs -- is outside any single corpus and is
   surfaced as a scope note for the human to weigh.

   Not currently wired into any live auto-apply path: today's only user-facing
   promotion flow (the ``toolguard-maintenance`` skill, pass 4) hand-applies
   promotions as a two-file paste, always to ``~/.claude/toolguard_hook.toml``
   specifically. If/when this module's ``to_provenance`` is ever wired to an
   automated target-selection step, it MUST NEVER select a layer whose
   ``source_type`` is ``"toolguard_hook_rules"`` (the optional
   ``~/.config/toolguard/rules/`` split-file directory, TOO-30) as a promotion
   destination. That directory is manually curated by the user; moving a rule
   into one of its files must only ever happen on the user's explicit
   instruction, never as something toolguard decides on its own. The "broader
   user layer" a promotion targets means the primary
   ``~/.claude/toolguard_hook.toml`` (or an equivalent single, canonical
   user-level file the user has designated) -- not any arbitrary layer that
   happens to share the user specificity.

2. **Cross-layer redundancy** -- a rule in a more-specific layer that is
   normalised-equal to a rule already present in a broader layer is redundant:
   the broader copy already covers it, so the specific copy can be dropped with
   no change in behaviour.  This is the cross-layer counterpart of
   :mod:`toolguard.tools.redundancy` (which only handles intra-layer duplicates).

Scope: allow-list rules only in this slice (consistent with the rest of the
maintenance core).  Reuses ``with_layer_allow_replaced`` (the synthetic-config
primitive), ``replay`` (the gate), and ``redundancy._normalised_body`` (the
single normalisation helper) -- no reimplementation.
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
        list_type: Permission list (``'allow'`` in this slice).
        pattern: Wrapper-free pattern body to move (e.g. ``'git status:*'``).
        from_provenance: The layer the rule currently lives in.
        to_provenance: The layer to move it to. MUST NOT be a
            ``source_type == "toolguard_hook_rules"`` layer (the user-maintained
            ``~/.config/toolguard/rules/`` split-file directory) -- see the module
            docstring. Any code that constructs this value automatically must
            filter those out first.
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
        decision_neutral: ``True`` when no corpus decision changed -- the move is
            safe for the CURRENT context (its cross-context broadening is reported
            separately in ``scope_note``).
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
    A more-specific allow rule already covered by an identical broader-layer rule.

    Attributes:
        tool: Tool the rule applies to.
        pattern: The redundant (more-specific) pattern body.
        redundant_provenance: The more-specific layer holding the redundant copy.
        covered_by_provenance: The broader layer whose rule already covers it.
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

    Removes ``migration.pattern`` from ``from_provenance``'s allow list and adds
    it to ``to_provenance``'s, by composing two
    :func:`~toolguard.tools.config_access.with_layer_allow_replaced` calls.

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
    """
    Describe how a migration changes a rule's scope beyond the current corpus.

    Args:
        migration: The migration being described.

    Returns:
        A human-readable scope note.
    """
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

    This is the structured form passed to the AI-driven security audit (via
    ``toolguard-audit --migrations``) so it can evaluate the risk of a PROPOSED,
    not-yet-enacted migration -- the deterministic ``decision_neutral`` flag only
    proves current-corpus neutrality, never cross-section/cross-layer intent
    safety, which is exactly what the audit's judgement layer is for.

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
    Replay-measure the effect of a hierarchy migration on the current corpus.

    A safe promotion is DECISION-NEUTRAL here: the same commands resolve the same
    way whether the rule sits in the specific or the broader layer (both govern
    the current context).  A non-neutral result means a more-specific rule in
    between would change the outcome -- inspect before moving.

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
    "nearest" is the smallest such value -- the layer that would take over if the
    more-specific copy were dropped.

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
    Find more-specific allow rules already covered by a broader-layer rule.

    A rule in a more-specific layer (lower ``specificity``) whose body is
    normalised-equal to a rule in a broader layer (higher ``specificity``) is
    redundant: the broader copy already allows the same commands, so dropping the
    specific copy changes no decision.  Only normalised-EQUAL matches are claimed
    (conservative); cross-layer subsumption via globs is deferred.

    Args:
        config: The resolved configuration.
        tool: Tool name to check (e.g. ``'Bash'``).

    Returns:
        A list of :class:`CrossLayerRedundancy` findings.
    """
    layers = per_layer_rules(config, tool)

    # Index every allow rule by its normalised body -> where it appears
    # (specificity + provenance), then flag any rule that a strictly-broader
    # layer also holds.
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
