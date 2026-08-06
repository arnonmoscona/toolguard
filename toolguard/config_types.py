"""
Thin configuration data types, separated from :mod:`toolguard.config`'s logic.

TOO-19 structural refactor. :mod:`toolguard.config` mixes these plain
``@dataclass(frozen=True)`` shapes with the much larger ``Configuration`` class
and all the discovery/parsing machinery that builds and resolves them. Moving
the types here lets type definitions live apart from implementation logic,
continuing the pattern already established for :class:`~toolguard.issues.Issue`
(in :mod:`toolguard.issues`) and :class:`~toolguard.rule_entry.RuleEntry` (in
:mod:`toolguard.rule_entry`).

Most classes below are unchanged from their original home in ``config.py``,
docstrings and comments intact. These types reference only each other and
:class:`~toolguard.rule_entry.RuleEntry`, so this module stays a leaf that
:mod:`toolguard.config` depends on -- not the reverse -- exactly like
``issues.py`` and ``rule_entry.py``. It must never import from
:mod:`toolguard.config`.

:mod:`toolguard.config` re-exports every class here, so existing
``from toolguard.config import Provenance`` (etc.) call sites are unaffected.

:class:`RuntimeVerdict` and :class:`UnitVerdict` are the exception to "pure
move": TOO-45 R1c collapsed ``ResolvedDecision`` (formerly here) with
``BashResolution``/``FileResolution`` (formerly in
:mod:`toolguard.resolve`) into :class:`RuntimeVerdict`, and moved
``SubMatch`` here (renamed :class:`UnitVerdict`) from
:mod:`toolguard.resolve` -- both live here rather than in ``resolve.py``
because :mod:`toolguard.permission_resolution` constructs the former
directly and cannot import ``resolve.py`` (circular: ``resolve.py`` imports
FROM ``permission_resolution``). :mod:`toolguard.resolve` re-exports both for
existing callers. See :class:`RuntimeVerdict`'s own docstring for the full
rationale.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import List, Mapping, Optional, Tuple

from toolguard.rule_entry import RuleEntry, _strip_tool_wrapper


@dataclass(frozen=True)
class Provenance:
    """
    Display-only origin of a single configuration source.

    Carries enough information to tell a human (or a future permission-mover)
    where a layer's content physically came from, without exposing file/format
    decisions as control flow to clients.

    Attributes:
        level: Conceptual level label ('project', 'user', or 'explicit' for
            a CLAUDE_SETTINGS_PATH single-file source).
        source_type: Either 'claude' (native settings) or 'toolguard_hook'.
        file_format: Either 'json' or 'toml'.
        path: Absolute path to the source file (display only).
        specificity: Hierarchy distance from the project root. 0 = most specific
            (project level); larger values are less specific; the user level is
            largest. Used by the more-specific-wins resolver. Sources at the same
            specificity belong to the same hierarchy level.
    """

    level: str
    source_type: str
    file_format: str
    path: Path
    specificity: int = 0

    def describe(self) -> str:
        """Return a short human-readable description of this source."""
        return f"{self.level}: {self.path} [{self.source_type}, {self.file_format}]"

    def describe_brief(self) -> str:
        """
        Return a compact ``level: path`` label.

        Two uses: appended to a decision *reason* as a bracketed suffix
        (e.g. ``[project: /home/me/proj/.claude/toolguard_hook.toml]``), and
        rendered as the audit log's standalone ``Provenance`` field (see
        ``hook._provenance_brief``). Kept terse so it does not bloat the
        resolution log.
        """
        return f"{self.level}: {self.path}"


@dataclass(frozen=True)
class ConfigLayer:
    """
    One discovered configuration source, with provenance and parsed content.

    Layers are produced most-specific first (project before user, ``.local``
    before regular). The parsed content is exposed as a read-only mapping so it
    cannot be mutated by clients. Pattern matching is intentionally NOT done
    here; layers carry typed pattern lists that matching code consumes.

    Attributes:
        provenance: Display-only origin of this layer.
        content: Read-only view of the parsed config dict for this source.
        unexpected_keys: Top-level keys present in the raw source file that are
            NOT permitted for this layer's source type and were stripped from
            ``content`` before it was built. Always empty for ``~/.claude``
            sources (which permit any toolguard_hook key). Non-empty only for
            ``toolguard_hook_rules`` (XDG rules-directory, TOO-30) layers, which
            are restricted to ``[permissions]``/``[hard_deny]``;
            :meth:`Configuration.validation_issues` reports these as errors.
            Defaults to ``()`` so existing direct-construction call sites are
            unaffected.
        duplicate_format: True when discovery found a same-stem sibling in the
            other format (TOML+JSON both present) that lost the TOML-over-JSON
            precedence and so does NOT get its own layer. Recorded at discovery
            time -- while the source directory is known to exist -- so
            :meth:`Configuration.validation_issues` can report the "both
            formats" warning without re-touching the filesystem later (relevant
            for ``toolguard_hook_rules`` layers, TOO-30). Computed WITHIN a
            single (the winning) rules directory only -- see ``shadowed_path``
            for the cross-directory case (TOO-19). Defaults to False.
        shadowed_path: Set to the representative path of a same-stem file that
            was found in one of the OTHER candidate rules directories (see
            :func:`_rules_dirs`) and lost the cross-directory,
            first-directory-wins precedence, so it does NOT get its own layer.
            Recorded at discovery time -- while the source directories are
            known to exist -- so :meth:`Configuration.validation_issues` can
            report the shadowing warning without re-touching the filesystem
            later. Only ever set on ``toolguard_hook_rules`` layers (TOO-19).
            Defaults to None (no cross-directory shadowing).
    """

    provenance: Provenance
    content: Mapping = field(default_factory=lambda: MappingProxyType({}))
    unexpected_keys: Tuple[str, ...] = ()
    duplicate_format: bool = False
    shadowed_path: Optional[Path] = None

    @property
    def source_type(self) -> str:
        """Convenience accessor for the source type ('claude'/'toolguard_hook')."""
        return self.provenance.source_type

    @property
    def is_native(self) -> bool:
        """True when this layer is a native Claude settings file."""
        return self.provenance.source_type == "claude"

    @property
    def specificity(self) -> int:
        """Hierarchy specificity of this layer (0 = most specific)."""
        return self.provenance.specificity


@dataclass(frozen=True)
class ToolPatternLayer:
    """
    Per-layer allow/deny/ask entries for a single tool, with provenance.

    This is the per-layer shape returned by ``Configuration.permission_layers``.
    Takeover filtering has already been applied. Phase 1 callers flatten +
    union the ``allow``/``deny``/``ask`` pattern views (below); a future
    per-layer resolver can consume the same shape without changes.

    TOO-45 R2: the wrapper-INTACT :class:`~toolguard.rule_entry.RuleEntry`
    tuples (``allow_entries``/``deny_entries``/``ask_entries``) are the ONLY
    storage. The wrapper-stripped pattern tuples (``allow``/``deny``/``ask``)
    are derived properties over them, not separately stored -- there is no
    longer a second, independently-populated collection that could drift out
    of alignment with the entries. Before this change the two were parallel
    dataclass fields with a hand-documented "same order, same membership,
    index-for-index" invariant; that invariant is gone because there is only
    one collection left to be misaligned with itself.

    Attributes:
        provenance: Origin of the patterns in this layer.
        allow_entries: The wrapper-INTACT :class:`~toolguard.rule_entry.RuleEntry`
            objects for this layer's allow rules (order preserved). Defaults
            to ``()`` for back-compatibility with constructors that predate
            structured-entry support.
        deny_entries: As ``allow_entries``, for ``deny``.
        ask_entries: As ``allow_entries``, for ``ask``. A command matching an
            ask pattern resolves to an ``ask`` (prompt) verdict per the
            more-specific-wins model.
    """

    provenance: Provenance
    allow_entries: Tuple["RuleEntry", ...] = ()
    deny_entries: Tuple["RuleEntry", ...] = ()
    ask_entries: Tuple["RuleEntry", ...] = ()

    @property
    def allow(self) -> Tuple[str, ...]:
        """Wrapper-stripped allow patterns, derived from ``allow_entries``."""
        return tuple(entry.stripped_pattern for entry in self.allow_entries)

    @property
    def deny(self) -> Tuple[str, ...]:
        """Wrapper-stripped deny patterns, derived from ``deny_entries``."""
        return tuple(entry.stripped_pattern for entry in self.deny_entries)

    @property
    def ask(self) -> Tuple[str, ...]:
        """Wrapper-stripped ask patterns, derived from ``ask_entries``."""
        return tuple(entry.stripped_pattern for entry in self.ask_entries)


def _entries_for_kind(layer: "ToolPatternLayer", kind: str) -> Tuple["RuleEntry", ...]:
    """
    Return *layer*'s entries for ``kind`` ('allow', 'ask', or anything else
    treated as 'deny') -- the single 3-branch dispatch shared by
    :func:`provenance_for_pattern` and :func:`entry_for_pattern`, so the two
    cannot disagree about which side of a layer a ``kind`` string selects.
    """
    if kind == "allow":
        return layer.allow_entries
    if kind == "ask":
        return layer.ask_entries
    return layer.deny_entries


def provenance_for_pattern(
    layers: Tuple[ToolPatternLayer, ...], pattern: str, kind: str
) -> Optional["Provenance"]:
    """
    Find the provenance of the layer that contributed a matched pattern.

    TOO-45 R2d: moved off ``Configuration`` (formerly
    ``Configuration.provenance_for_pattern``, a ``@staticmethod`` taking
    ``layers`` as a parameter) to live beside :class:`ToolPatternLayer`,
    whose entries this function searches -- it held no configuration state
    and its whole job is reading this type.

    Args:
        layers: The contributing layers for one level (most-specific first).
        pattern: The exact (wrapper-free) pattern string that matched.
        kind: 'allow', 'ask', or 'deny' -- which side of the layer to search.

    Returns:
        The provenance of the first layer whose ``kind`` entries contain a
        matching pattern, or None when not found (e.g. format drift).
    """
    for layer in layers:
        entries = _entries_for_kind(layer, kind)
        if any(entry.stripped_pattern == pattern for entry in entries):
            return layer.provenance
    return None


def entry_for_pattern(
    layers: Tuple[ToolPatternLayer, ...], pattern: str, kind: str
) -> Optional["RuleEntry"]:
    """
    Find the :class:`~toolguard.rule_entry.RuleEntry` behind a matched pattern.

    TOO-45 R2d: moved off ``Configuration`` for the same reason as
    :func:`provenance_for_pattern` (same file, same reasoning -- see that
    function's docstring).

    TOO-45 R2: searches ``entries`` directly by
    :attr:`~toolguard.rule_entry.RuleEntry.stripped_pattern` instead of
    locating ``pattern`` in a separately-stored stripped-pattern tuple and
    then reading the entry off a second, parallel tuple at the same index.
    Before this change a drifted pair of parallel lists could make that
    index lookup return the wrong entry (or, when guarded, silently return
    None); with only one collection to search, that failure mode no longer
    exists to guard against.

    Companion to :func:`provenance_for_pattern` (same first-layer-wins
    search), kept as a separate function rather than folded into it: the
    other caller of ``provenance_for_pattern``
    (:func:`~toolguard.permission_resolution._detect_override`, for the
    OVERRIDDEN deny) has no use for the entry, so merging the two would hand
    every call site an unused value. The two functions do re-walk the same
    (small, per-level) layer list, but that repeat scan is cheap relative to
    the readability cost of a combined return type.

    Args:
        layers: The contributing layers for one level (most-specific first).
        pattern: The exact (wrapper-free) pattern string that matched.
        kind: 'allow', 'ask', or 'deny' -- which side of the layer to search.

    Returns:
        The :class:`~toolguard.rule_entry.RuleEntry` behind the first layer
        whose ``kind`` entries contain a matching pattern, or None when not
        found (e.g. format drift).
    """
    for layer in layers:
        entries = _entries_for_kind(layer, kind)
        for entry in entries:
            if entry.stripped_pattern == pattern:
                return entry
    return None


@dataclass(frozen=True)
class TakeoverEnabledConflict:
    """
    A cross-level disagreement on ``takeover_mode.enabled`` (TOO-8 Phase 5).

    takeover_mode is a single-owner policy; different levels setting ``enabled``
    to DIFFERING values is a misconfiguration. When detected, the resolver
    fail-safes ``enabled`` to ``False`` (native Claude prompts stay active --
    nothing is silently bypassed) and carries this record so the hook can log a
    conflict entry and warn once per session.

    Attributes:
        sources: Tuple of ``(value, provenance)`` pairs, one per layer that
            EXPLICITLY set ``enabled``, in most-specific-first order. ``value`` is
            the boolean each layer set; ``provenance`` is that layer's origin.
    """

    sources: Tuple[Tuple[bool, "Provenance"], ...]

    def describe(self) -> str:
        """
        Return a human-readable summary citing each disagreeing source.

        Lists every level that set ``enabled`` with its value and provenance,
        most-specific first, for the conflict log entry.
        """
        parts = [f"{value} [{prov.describe_brief()}]" for value, prov in self.sources]
        return "takeover_mode.enabled set to conflicting values: " + "; ".join(parts)


@dataclass(frozen=True)
class UnrecognizedFallbackSetting:
    """
    A ``*_fallback`` setting written with a value toolguard does not recognize.

    TOO-19 m5. ``no_match_fallback`` and ``undecidable_fallback`` both resolve
    an unrecognized value to the safe default ``'ask'`` and keep going -- that
    part is deliberate and unchanged, because ``'ask'`` is the safe direction
    when a policy setting cannot be read. What was NOT acceptable is that it
    happened SILENTLY: a single-character typo (``allow_with_no_warnings``
    written as ``allow_with_no_warning``) produced maximum-friction behaviour
    with no diagnostic anywhere, which reads as "the feature is broken" rather
    than "you have a typo". This record carries everything a warning needs to
    say so, including the accepted spellings -- a warning that omits those is
    what turns a typo into a round trip.

    Attributes:
        key: The setting name -- ``'no_match_fallback'`` or
            ``'undecidable_fallback'``.
        value: The offending value EXACTLY as written in the file, rendered as
            a string (a non-string value, e.g. a bool or a table, is equally
            unusable and equally silent, so it is reported the same way).
        provenance: Origin of the layer that set it, so the warning can name
            the file to edit.
        accepted: The accepted spellings for *key*, sorted, INCLUDING the
            aliases that are normalized away before validation -- the user
            needs the spellings they may type, not the internal canonical set.
    """

    key: str
    value: str
    provenance: "Provenance"
    accepted: Tuple[str, ...]

    def describe(self) -> str:
        """
        Return a one-line human-readable description naming value, setting,
        file, and accepted spellings.
        """
        return (
            f"{self.key} = {self.value!r} in {self.provenance.describe_brief()} "
            f"is not a recognized value; falling back to 'ask'. "
            f"Accepted values: {', '.join(self.accepted)}"
        )


@dataclass(frozen=True)
class TakeoverConfig:
    """
    Resolved takeover-mode configuration (TOO-8 Phase 5).

    ``enabled`` is resolved as a SINGLE-OWNER policy with fail-safe-on-conflict:
    levels that explicitly set it must agree; if they disagree, ``enabled`` is
    forced to ``False`` and :attr:`conflict` records the disagreement. Pattern
    lists (``ignored_allow_patterns``/``additional_ignored_patterns``) remain a
    UNION across all levels, and ``no_match_fallback`` resolves
    more-specific-wins.

    Attributes:
        enabled: Whether takeover mode is active (fail-safe ``False`` on conflict).
        ignored_allow_patterns: Blanket allow patterns suppressed from native config.
        additional_ignored_patterns: Extra user-supplied ignored patterns.
        no_match_fallback: the RAW configured value (e.g. 'ask', 'deny',
            'allow_with_warning', or the deprecated legacy 'warn_deny' alias)
            -- not normalized at this layer; see
            :meth:`Configuration.resolved_no_match_fallback` for the
            normalized, alias-resolved value actually used to decide.
        conflict: A :class:`TakeoverEnabledConflict` when levels disagree on
            ``enabled``, otherwise None.
    """

    enabled: bool
    ignored_allow_patterns: Tuple[str, ...]
    additional_ignored_patterns: Tuple[str, ...]
    no_match_fallback: str
    conflict: Optional["TakeoverEnabledConflict"] = None

    def normalized_ignored_patterns(self) -> frozenset:
        """
        Return the set of ignored patterns in extracted (wrapper-free) form.

        Combines ``ignored_allow_patterns`` and ``additional_ignored_patterns``
        and strips any recognised tool wrapper so the values can be compared
        against extracted pattern lists.
        """
        combined = tuple(self.ignored_allow_patterns) + tuple(
            self.additional_ignored_patterns
        )
        return frozenset(_strip_tool_wrapper(p) for p in combined)


@dataclass(frozen=True)
class ConflictOverride:
    """
    A more-specific ``allow`` overriding a less-specific ``deny`` (Phase 4).

    Records BOTH sides of an allow-over-deny override so the conflict log can
    cite the winning allow and the overridden deny by provenance. The decision
    itself is unchanged (more-specific-wins keeps the allow); this is purely a
    record of the override for human/LLM review.

    The command/path that triggered the override is known by the caller (the
    hook), so it is NOT stored here; the hook composes the conflict-log message
    from this record plus the command it already holds.

    Attributes:
        winning_pattern: The more-specific ``allow`` pattern that won.
        winning_provenance: Provenance of the winning allow.
        overridden_pattern: The less-specific ``deny`` pattern that was overridden.
        overridden_provenance: Provenance of the overridden deny.
    """

    winning_pattern: str
    winning_provenance: Optional["Provenance"]
    overridden_pattern: str
    overridden_provenance: Optional["Provenance"]


@dataclass(frozen=True)
class LevelMatch:
    """
    A single hierarchy-level (or hard-deny-pool) pattern-match result.

    TOO-45 R1f: replaces the bare ``(decision, reason, matched_pattern)``
    tuple that :func:`~toolguard.permissions.check_hard_deny`,
    :func:`~toolguard.permissions.decide_command_at_level_detailed`,
    :func:`~toolguard.resolve._decide_file_path_at_level_detailed`, and
    :func:`~toolguard.resolve._check_file_path_hard_deny` used to return
    (or ``None`` when nothing at this level/pool matched -- every real
    caller wraps this type in ``Optional``, never constructs a
    ``LevelMatch`` for "no match").

    This is the ``decide_detailed`` callback contract
    :func:`~toolguard.permission_resolution.resolve_permission_detailed`
    consumes: ``decide_detailed(allow, deny, ask)`` must return a
    ``LevelMatch`` (or ``None``) so the matched pattern can be mapped back
    to its owning :class:`~toolguard.config.ToolPatternLayer`/provenance.

    A THIRD, lower altitude than :class:`UnitVerdict` (one sub-command's
    outcome) and :class:`RuntimeVerdict` (the whole runtime verdict): this
    is the raw match at ONE hierarchy level or hard-deny pool, before any
    provenance lookup, ``additionalContext`` enrichment, or allow-over-deny
    override detection is attached -- all of which
    :func:`~toolguard.permission_resolution._resolve_unclamped` does with
    the ``matched_pattern`` this type carries. Deliberately NOT named with
    a "Verdict" suffix (unlike ``UnitVerdict``/``RuntimeVerdict``): it isn't
    one -- a hierarchy-level match is not itself a governed-tool decision,
    only an input to one.

    ``tools/architecture_fitness.py`` reports this class under its own
    **LEVEL** altitude, excluded from R1's "exactly one runtime verdict
    type" gate but always visible with its reason. The test that decides
    this is whether the class can carry a :class:`Provenance` -- this one
    cannot, because none exists in scope until
    :func:`~toolguard.permission_resolution._resolve_unclamped` resolves it
    one layer up.

    TOO-45 R1g corrected an earlier version of this paragraph, which claimed
    the ``matched_pattern`` spelling was "the one deliberate naming choice
    that keeps it out of that count". That was true and was the problem: the
    class was invisible to the predicate rather than excluded by it, so R1's
    PASS rested on a field name. The classifier no longer inspects the
    winning-pattern field at all, and a test renames it to ``matched_rule``
    to prove the classification does not move.

    ``_check_file_path_hard_deny``'s use (TOO-45 R1f reconciliation)
    -------------------------------------------------------------------
    Before R1f, ``_check_file_path_hard_deny`` computed its own
    ``additionalContext`` lookup internally and returned
    ``(decision, reason, additional_context)`` -- a DIFFERENT shape from
    the other three functions' ``(decision, reason, matched_pattern)``,
    and the matched hard-deny pattern itself was discarded (a TOO-45 R3
    comment at the call site explained why closing that gap was out of
    R3's scope). R1f reconciles this onto ONE shared type instead of
    inventing a second: ``_check_file_path_hard_deny`` now returns its
    matched pattern in ``matched_pattern`` (mirroring
    :func:`~toolguard.permissions.check_hard_deny`'s Bash-side
    convention), and its caller
    (:func:`~toolguard.resolve.resolve_file_path_permission_detailed`)
    computes the ``additionalContext`` lookup itself from that pattern --
    exactly mirroring how the Bash side already does it in
    :func:`~toolguard.resolve.resolve_bash_permission_detailed`'s
    ``_decide`` closure. The final ``RuntimeVerdict.matched_rule`` for a
    file-path hard-deny STILL deliberately stays ``None`` (unchanged
    behaviour, unlike the Bash side, which does attribute it) -- R1f is a
    structural conversion only, not the R3 fix; see that call site's own
    comment for why the asymmetry is preserved rather than closed here.

    Lives in :mod:`toolguard.config_types`, not :mod:`toolguard.resolve` or
    :mod:`toolguard.permissions`, for the same reason
    :class:`RuntimeVerdict`/:class:`UnitVerdict` do:
    :mod:`toolguard.permission_resolution` consumes this type directly (via
    the ``decide_detailed`` callback's return value) and is architecturally
    forbidden from importing either module (see
    :mod:`toolguard.permission_resolution`'s own module docstring).
    :mod:`toolguard.permissions` and :mod:`toolguard.resolve` both
    re-export it for their own callers.

    Attributes:
        decision: ``'allow'``, ``'ask'``, or ``'deny'`` -- this level's/
            pool's own decision, before any cascade-wide clamp (e.g. the
            TOO-19 parse-failure ASK floor, applied later by
            :func:`~toolguard.permission_resolution.resolve_permission_detailed`)
            is applied.
        reason: Human-readable reason for THIS level's/pool's own match,
            before provenance is appended as a bracketed suffix (that
            happens one layer up, in
            :func:`~toolguard.permission_resolution._resolve_unclamped`).
        matched_pattern: The winning (wrapper-free) pattern text. Always a
            genuine ``str`` when a ``LevelMatch`` is constructed at all --
            "no match" is represented by the caller returning ``None``
            instead of a ``LevelMatch``, never by an empty/placeholder
            pattern here.
    """

    decision: str
    reason: str
    matched_pattern: str


@dataclass(frozen=True)
class UnitVerdict:
    """
    Per-sub-command resolution record inside a compound Bash permission check.

    TOO-45 R1c: renamed from ``SubMatch`` so its ALTITUDE is visible in its
    name -- this is the UNIT verdict, one decidable unit inside a compound,
    the phase-6 shape in the ideal picture (see the R1 scoping trace). It is
    deliberately NOT collapsed into :class:`RuntimeVerdict`: doing so would
    destroy the only structured record of what a compound command did,
    which is exactly what TOO-45 R1e needs to fix an audit-loss defect
    (813 of 975 compound-allow corpus cases writing fewer audit entries than
    sub-commands run, because the log reconstructs this information by
    re-parsing prose instead of reading it structurally).

    ``reason``/``additional_context`` merged in (TOO-45 R1e finishing pass)
    from a short-lived second type, ``compound.py``'s own ``LeafOutcome``,
    that an earlier pass of this same step introduced to carry a single
    leaf's/segment's ``(decision, reason, additional_context, fallback_kind)``
    outcome back to its caller. Both types described exactly ONE leaf --
    ``LeafOutcome``'s own docstring argued it had to stay separate from
    :class:`RuntimeVerdict` because ``fallback_kind`` (a tri-state tag for
    ONE leaf) is a different concept from ``RuntimeVerdict.fallback_warning``
    (an aggregate boolean over an entire compound); that argument is correct
    about ``RuntimeVerdict`` -- and says nothing about ``UnitVerdict``, which
    is ALSO per-leaf and is the type whose entire purpose is to be the unit
    altitude. Keeping them apart was exactly the kind of near-duplicate this
    ticket exists to remove: every ``LeafOutcome`` construction site in
    ``compound.py`` sits inside :func:`~toolguard.compound._resolve_leaf_detailed`,
    which already knows the leaf's real, full ``sub_command`` text at that
    point (it is the function's own ``leaf.text`` parameter), so there was
    never a construction site that genuinely lacked one to justify a
    ``sub_command``-less type.

    Lives here (not in :mod:`toolguard.resolve`, where it is actually
    constructed) for the same reason :class:`RuntimeVerdict` does -- see that
    class's docstring's "Why this lives in config_types.py" note. Re-exported
    by :mod:`toolguard.resolve` for existing callers.

    Callers (e.g. :func:`toolguard.tools.decision._decide_bash`) can use
    ``sub_matches`` to identify WHICH sub-command of a compound command produced
    the verdict (first deny => compound deny, first ask => compound ask, else
    allow) and to surface per-sub-command provenance to tooling.

    Attributes:
        sub_command: The individual sub-command string as extracted by the
            compound splitter.  For an ask-floor leaf (foreign inline code /
            heredoc sink, see ``compound.py::_resolve_leaf_detailed``) or an
            undecidable segment, this is the leaf's/segment's real, full
            source text -- NOT the truncated outer-command stub
            ``compound.py`` resolves internally to check for an explicit deny
            (TOO-45 R1e; see ``fallback_kind`` below for why the stub's own
            match must not be attributed here).
        decision: The decision for this sub-command: ``'allow'``, ``'ask'``, or
            ``'deny'`` -- always the leaf's TRUE FINAL decision, after any
            ``undecidable_fallback`` floor has been applied (TOO-45 R1e). For
            an ask-floor leaf this can differ from what the truncated stub
            itself resolved to; see ``fallback_kind``.
        matched_rule: The winning rule pattern string (wrapper-free, as stored in
            the layer) if one matched, or the hard-deny pattern string when the
            sub-command was hard-denied.  ``None`` when no rule matched (default
            fail-closed deny) OR when ``fallback_kind`` is not ``None`` (an
            escape-hatch outcome, TOO-45 R1e): a rule matching the
            ask-floor leaf's truncated stub never verified the leaf's real,
            unread content, so it must never be recorded here as the reason
            this leaf's decision stands -- the escape hatch decided, not the
            rule.
        provenance: Origin of the layer whose rule matched, or ``None`` for a
            hard-deny (pooled across levels, no single provenance), a
            fail-closed default deny, or an escape-hatch outcome (same
            reasoning as ``matched_rule`` above).
        fallback_kind: ``'warned'``, ``'silent'``, ``'denied'``, or ``None``
            (TOO-45 R1e) -- structural counterpart of
            :func:`~toolguard.compound.fallback_kind_for_reason`, computed
            once at the point this record is built instead of re-derived by
            re-parsing ``reason`` text downstream. ``'warned'``/``'silent'``
            name the ``no_match_fallback``/``undecidable_fallback`` allow
            escape hatch (with/without a warning); ``'denied'`` names the
            ``undecidable_fallback=deny`` escape hatch. ``None`` for a
            genuine rule match (including a genuine ``ask`` match that an
            ask-floor leaf's own stub happened to also decide) or a
            fail-closed default with no fallback setting in play (e.g. plain
            ``no_match_fallback=deny``, which is not an "escape hatch" in
            this sense -- see :func:`~toolguard.compound.fallback_kind_for_reason`'s
            own docstring). This is what lets a consumer (e.g.
            ``hook.py::_log_allowed_command``) substitute an honest
            placeholder for ``matched_rule`` without re-parsing ``reason``.
        reason: Human-readable reason for THIS unit's own decision (TOO-45
            R1e finishing pass; merged in from ``LeafOutcome``). For a leaf
            resolved through the normal (non-ask-floor) path this is the
            same reason text :func:`~toolguard.compound._combine_strictest`
            would build for it standing alone; for an ask-floor leaf or an
            undecidable segment it already names the escape hatch (see
            ``compound.py``'s branches). Distinct from
            :attr:`RuntimeVerdict.reason`, which is the WHOLE compound's
            combined reason, not any one unit's.
        additional_context: This unit's own ``additionalContext`` enrichment
            (TOO-19 Phase 1), or ``None``. ``None`` on the genuinely-floored
            path (the floor, not a rule match, decided -- see
            ``compound.py::_resolve_leaf_detailed``'s own docstring for why).
            Distinct from :attr:`RuntimeVerdict.additional_context`, which is
            the compound-wide accumulation across every contributing unit
            (:func:`~toolguard.compound._accumulate_contexts`), not any one
            unit's own value.
    """

    sub_command: str
    decision: str
    matched_rule: Optional[str]
    provenance: Optional["Provenance"]
    reason: str
    additional_context: Optional[str]
    fallback_kind: Optional[str] = None


@dataclass(frozen=True)
class RuntimeVerdict:
    """
    The single runtime verdict type every governed-tool resolution returns
    (TOO-45 R1c).

    Collapses THREE previously-separate types that all represented the same
    thing at slightly different points in the pipeline: ``ResolvedDecision``
    (the raw per-level/per-sub-command result, formerly defined here),
    ``BashResolution`` (the compound-aggregated Bash result), and
    ``FileResolution`` (the file-path result) -- all formerly in
    :mod:`toolguard.resolve`. The R1 scoping trace's runtime census showed
    they were never three different SHAPES, just three different SITES that
    each declared their own dataclass for the same decision/reason/
    provenance/matched_rule/additional_context/fallback_warning bundle.

    Named ``RuntimeVerdict`` (not just ``Verdict``) deliberately, to match
    the altitude language the R1 scoping trace uses and
    ``tools/architecture_fitness.py``'s predicate now enforces: this is the
    RUNTIME altitude, distinct from :class:`UnitVerdict` (the UNIT altitude
    nested inside it via ``sub_matches``) and
    :class:`~toolguard.tools.decision.Decision` (the TOOLING altitude,
    deferred to R6 -- see that class's own docstring). "Exactly one type
    represents a permission verdict end-to-end" was too blunt a predicate;
    "exactly one RUNTIME verdict type, with the other altitudes declared and
    justified" is what actually holds on this tree, and is what
    ``tools/architecture_fitness.py --predicates`` now reports.

    Why this lives in config_types.py, not resolve.py
    ---------------------------------------------------
    :mod:`toolguard.permission_resolution` constructs this type directly (it
    is the per-level/per-sub-command result, the old ``ResolvedDecision``'s
    role) and is architecturally forbidden from importing
    :mod:`toolguard.resolve` (see that module's own docstring: it imports
    FROM ``permission_resolution``, so the reverse would be circular).
    :mod:`toolguard.config_types` is the shared leaf both modules can import.
    A useful side effect: :class:`Provenance` and :class:`ConflictOverride`
    are ALSO defined in this module, so ``provenance``/``overrides`` below
    can be typed precisely instead of falling back to ``Any`` the way the old
    ``BashResolution``/``FileResolution`` had to, to dodge a circular import
    with :mod:`toolguard.config`.

    ``tool``/``target`` (TOO-45 R1c placeholder for R1d)
    -------------------------------------------------------
    Carried even though NOTHING consumes them yet -- ``toolguard.hook``'s
    ``log_command``/``create_hook_output`` call sites (R1d) still reconstruct
    this information by hand from the tool_name/command/file_path already in
    scope at the call site. Populating them here is what lets R1d stop doing
    that. Only :mod:`toolguard.resolve`'s two PUBLIC entry points
    (:func:`~toolguard.resolve.resolve_bash_permission_detailed`,
    :func:`~toolguard.resolve.resolve_file_path_permission_detailed`)
    populate them, since only they have the actual command/file_path string
    in scope; the internal per-level verdict built by
    :func:`~toolguard.permission_resolution.resolve_permission_detailed`
    leaves both ``None`` (it is never handed a target string at all -- its
    ``decide_detailed`` callback closes over it privately). ``tool`` for a
    Bash/MCP-terminal resolution is always the literal string ``'Bash'``,
    matching :func:`~toolguard.resolve.resolve_bash_permission_detailed`'s
    existing convention of always evaluating against the Bash rule set
    regardless of the actual invoking tool name (the hook does not thread
    the true MCP-terminal tool name down to the resolver).

    ``overrides`` (TOO-45 R1c reconciliation)
    --------------------------------------------
    The three collapsed types disagreed on shape: ``BashResolution`` carried
    a LIST of ``(sub_command, ConflictOverride)`` pairs (a compound can have
    one override per sub-command); ``FileResolution``/``ResolvedDecision``
    each carried a single ``Optional[ConflictOverride]`` (never compound).
    The list generalises, so this type always carries a list of
    ``(identifier, ConflictOverride)`` pairs:

    - Bash compound (:func:`~toolguard.resolve.resolve_bash_permission_detailed`):
      *identifier* is the deciding sub-command string, one entry per
      sub-command whose more-specific allow overrode a less-specific deny --
      unchanged from ``BashResolution.overrides``' old shape.
    - File path (:func:`~toolguard.resolve.resolve_file_path_permission_detailed`):
      *identifier* is the file path itself (== ``target``); 0 or 1 entries.
    - The internal per-level verdict
      (:func:`~toolguard.permission_resolution.resolve_permission_detailed`):
      *identifier* is ``None`` -- that layer has no sub_command/target string
      in scope (see the ``tool``/``target`` note above); the two public
      ``resolve.py`` entry points re-pair the bare override with the real
      identifier once they have one.

    Attributes:
        decision: ``'allow'``, ``'ask'``, or ``'deny'``.
        reason: Human-readable reason, with provenance appended as a bracketed
            suffix when a rule matched (e.g.
            "Command matches allow pattern: git *  [project: .claude/...]").
        provenance: Provenance of the winning rule (for a compound Bash
            verdict, the DECIDING sub-command's provenance -- see
            :func:`~toolguard.resolve._deciding_sub_match`), or ``None`` for a
            fail-closed default deny, a hard-deny match (pooled across
            levels, no single provenance), or when there is no single
            decider to attribute.
        overrides: See "``overrides`` (TOO-45 R1c reconciliation)" above.
            Empty when the overall decision is not ``'allow'`` (only
            allow-over-deny overrides on an ALLOWED verdict are conflicts).
        sub_matches: One :class:`UnitVerdict` per extracted Bash sub-command,
            in order. Empty for a file-path verdict (file paths are never
            compound) and for the internal per-level verdict. Allows callers
            to identify the deciding sub-command and its provenance/
            matched-rule without re-running the resolver.
        additional_context: The accumulated ``additionalContext`` enrichment
            text (TOO-19 Phase 1), or ``None`` when no contributing rule
            carried one, no rule matched, or the ASK floor cleared the match
            (see :func:`~toolguard.permission_resolution._apply_ask_floor`).
            Word-capped via :func:`toolguard.compound.cap_context_words`
            regardless of whether the decision was allow, ask, or deny.
        fallback_warning: ``True`` when this 'allow' decision should be
            routed to the WARNING log stream (TOO-19
            allow/allow_with_no_warnings work) -- ``True`` only for an
            'allow' produced by the WARNED value of ``no_match_fallback`` or
            (for Bash) ``undecidable_fallback``. ``False`` for every other
            decision, including an explicit rule match and an 'allow'
            produced by the newer no-warning fallback values. Real,
            structurally-known data, never derived from *reason* -- see
            :func:`toolguard.hook._log_fallback_allow_warning`.
        matched_rule: The deciding rule's pattern text (wrapper-free), or
            ``None`` when there is no single rule to attribute (fail-closed
            default, fallback, a floor that cleared the match, or -- for a
            compound Bash verdict -- no single sub-command decided). NOT
            derived from *reason*. TOO-45 R1e: for a compound Bash verdict
            produced by an ``undecidable_fallback`` escape-hatch leaf, this is
            now correctly ``None`` even when the escape-hatch leaf's own
            pre-floor decision happened to equal the final decision -- the
            leaf's recorded :class:`UnitVerdict` (see ``sub_matches``) is
            corrected to the leaf's TRUE final decision/attribution at the
            point it is built (:func:`~toolguard.compound._resolve_leaf_detailed`),
            not left holding the truncated stub's own, possibly-misleading
            match. Before R1e this field could carry that misleading match
            and callers had to re-classify *reason* themselves before
            logging it; that re-classification is no longer needed for this
            field, though ``hook.py`` still uses the reason-based
            :func:`~toolguard.compound.fallback_kind_for_reason` for the
            deny/ask log entry itself (a rendering choice, not a data-
            correctness one -- see :func:`~toolguard.resolve._deciding_sub_match`'s
            docstring for the full mechanism).
        tool: See "``tool``/``target`` (TOO-45 R1c placeholder for R1d)"
            above. ``None`` until populated by one of ``resolve.py``'s two
            public entry points.
        target: As ``tool``, the command string (Bash) or file path
            (file-path tools) under evaluation.
    """

    decision: str
    reason: str
    # TOO-45 R1d: defaulted to None (was required with no default) so a
    # synthetic guard-clause verdict -- e.g. hook.py's
    # RuntimeVerdict(decision="deny", reason="No command provided in tool
    # input") for an input that never reached the resolver at all -- can be
    # constructed with only decision/reason, the same way every other
    # "nothing to attribute" field on this class already defaults away.
    provenance: Optional["Provenance"] = None
    overrides: List[Tuple[Optional[str], "ConflictOverride"]] = field(
        default_factory=list
    )
    sub_matches: List["UnitVerdict"] = field(default_factory=list)
    additional_context: Optional[str] = None
    fallback_warning: bool = False
    matched_rule: Optional[str] = None
    tool: Optional[str] = None
    target: Optional[str] = None
