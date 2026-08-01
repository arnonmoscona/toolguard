"""
Thin configuration data types, separated from :mod:`toolguard.config`'s logic.

TOO-19 structural refactor. :mod:`toolguard.config` mixes these plain
``@dataclass(frozen=True)`` shapes with the much larger ``Configuration`` class
and all the discovery/parsing machinery that builds and resolves them. Moving
the types here lets type definitions live apart from implementation logic,
continuing the pattern already established for :class:`~toolguard.issues.Issue`
(in :mod:`toolguard.issues`) and :class:`~toolguard.rule_entry.RuleEntry` (in
:mod:`toolguard.rule_entry`).

This is a pure move: every class below is unchanged from its original home in
``config.py``, docstrings and comments intact. These types reference only each
other and :class:`~toolguard.rule_entry.RuleEntry`, so this module stays a leaf
that :mod:`toolguard.config` depends on -- not the reverse -- exactly like
``issues.py`` and ``rule_entry.py``. It must never import from
:mod:`toolguard.config`.

:mod:`toolguard.config` re-exports every class here, so existing
``from toolguard.config import Provenance`` (etc.) call sites are unaffected.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

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
        Return a compact ``level: path`` label for reason-string suffixes.

        Used to append matched-rule provenance to a decision reason as a
        bracketed suffix, e.g. ``[project: /home/me/proj/.claude/toolguard_hook.toml]``.
        Kept terse so it does not bloat the resolution log.
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
    Per-layer allow/deny patterns for a single tool, with provenance.

    This is the per-layer shape returned by ``Configuration.permission_layers``.
    Patterns are extracted (tool wrapper removed) and takeover filtering has
    already been applied. Phase 1 callers flatten + union these; a future
    per-layer resolver can consume the same shape without changes.

    Invariant (TOO-19 Phase 0a, increment 2): for each of the three
    allow/deny/ask pairs, ``X[i]`` is always the wrapper-stripped form of
    ``X_entries[i].pattern`` -- same order, same membership, index-for-index.
    Later increments (e.g. metadata lookup by winning pattern) rely on this
    invariant; do not populate one without the other, or in different orders.

    Attributes:
        provenance: Origin of the patterns in this layer.
        allow: Extracted allow patterns from this layer (order preserved).
        deny: Extracted deny patterns from this layer (order preserved).
        ask: Extracted ask patterns from this layer (order preserved).  A command
            matching an ask pattern resolves to an ``ask`` (prompt) verdict per the
            more-specific-wins model; defaults to empty for back-compatibility with
            constructors that predate ask-list resolution.
        allow_entries: The wrapper-INTACT :class:`~toolguard.rule_entry.RuleEntry`
            objects backing ``allow``, index-aligned with it (see invariant
            above). Defaults to ``()`` for back-compatibility with
            constructors that predate structured-entry support.
        deny_entries: As ``allow_entries``, for ``deny``.
        ask_entries: As ``allow_entries``, for ``ask``.
    """

    provenance: Provenance
    allow: Tuple[str, ...]
    deny: Tuple[str, ...]
    ask: Tuple[str, ...] = ()
    allow_entries: Tuple["RuleEntry", ...] = ()
    deny_entries: Tuple["RuleEntry", ...] = ()
    ask_entries: Tuple["RuleEntry", ...] = ()


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
class ResolvedDecision:
    """
    Rich result of a more-specific-wins resolution (TOO-8 Phase 4).

    Carries everything the hook needs to log a decision with provenance and to
    surface an allow-over-deny conflict, without the hook re-deriving any of it.

    Attributes:
        decision: 'allow' or 'deny'.
        reason: Human-readable reason, with provenance appended as a bracketed
            suffix when a rule matched (e.g.
            "Command matches allow pattern: git *  [project: .claude/...]").
        provenance: Provenance of the winning rule, or None for a fail-closed
            default deny (no rule matched at any level).
        override: A :class:`ConflictOverride` when the winning allow overrode a
            less-specific deny, otherwise None.
        additional_context: The winning rule's ``additionalContext`` enrichment
            text (TOO-19 Phase 1), or None when the winning entry did not carry
            one, no rule matched, or the ASK floor cleared the match (see
            :meth:`~toolguard.config.Configuration._apply_parse_failure_ask_floor`).
    """

    decision: str
    reason: str
    provenance: Optional["Provenance"]
    override: Optional[ConflictOverride] = None
    additional_context: Optional[str] = None
