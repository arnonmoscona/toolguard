"""
Configuration structure types.

What is left of the old ``config_types`` after TOO-78 moved the decision
vocabulary down to :mod:`toolguard.decision_model.vocabulary`: these four describe
how configuration is SHAPED, and nothing below the configuration layer uses
them. The split is what lets ``engine`` and ``parser`` depend on the model
without gaining an edge into this package.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Optional, Tuple

from toolguard.decision_model.vocabulary import Provenance
from toolguard.decision_model.rule_entry import strip_tool_wrapper


@dataclass(frozen=True)
class ConfigLayer:
    """
    One discovered configuration source, with provenance and parsed content.

    Layers are produced most-specific first (project before user, ``.local``
    before regular). The parsed content is exposed as a read-only mapping so it
    cannot be mutated by clients. Pattern matching is intentionally NOT done
    here; ``content`` is the raw parsed dict, not yet the typed pattern lists
    :class:`ToolPatternLayer` carries.

    Attributes:
        provenance: Display-only origin of this layer.
        content: Read-only view of the parsed config dict for this source.
        unexpected_keys: Top-level keys present in the raw source file that are
            not permitted for this layer's source type and were stripped from
            ``content`` before it was built. Always empty for ``~/.claude``
            sources (which permit any toolguard_hook key). Non-empty only for a
            rules-directory layer, which is restricted to
            ``[permissions]``/``[hard_deny]``; :meth:`Configuration.validation_issues`
            reports these as errors.
        duplicate_format: True when discovery found a same-stem sibling in the
            other format (TOML+JSON both present) that lost the TOML-over-JSON
            precedence and so does NOT get its own layer. Recorded at discovery
            time -- while the source directory is known to exist -- so
            :meth:`Configuration.validation_issues` can report the "both
            formats" warning without re-touching the filesystem later. Computed
            WITHIN a single (the winning) rules directory only -- see
            ``shadowed_path`` for the cross-directory case.
        shadowed_path: Set to the representative path of a same-stem file that
            was found in one of the OTHER candidate rules directories (see
            :func:`~toolguard.configuration.config._rules_dirs`) and lost the cross-directory,
            first-directory-wins precedence, so it does NOT get its own layer.
            Recorded at discovery time, for the same reason as
            ``duplicate_format`` above. Only ever set on a rules-directory layer.
    """

    provenance: Provenance
    content: Mapping = field(default_factory=lambda: MappingProxyType({}))
    unexpected_keys: Tuple[str, ...] = ()
    duplicate_format: bool = False
    shadowed_path: Optional[Path] = None

    @property
    def source_type(self) -> str:
        """Convenience accessor for :attr:`Provenance.source_type`."""
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
class TakeoverEnabledConflict:
    """
    A cross-level disagreement on ``takeover_mode.enabled``.

    takeover_mode is a single-owner policy; different levels setting ``enabled``
    to DIFFERING values is a misconfiguration. When detected, the resolver
    fail-safes ``enabled`` to ``False`` (native Claude prompts stay active --
    nothing is silently bypassed) and carries this record so the hook can log a
    conflict entry and surface a warning.

    Attributes:
        sources: Tuple of ``(value, provenance)`` pairs, one per layer that
            EXPLICITLY set ``enabled``, in most-specific-first order. ``value`` is
            the boolean each layer set; ``provenance`` is that layer's origin.
    """

    sources: Tuple[Tuple[bool, "Provenance"], ...]

    def describe(self) -> str:
        """Return a one-line summary citing every disagreeing source, most-specific first."""
        parts = [f"{value} [{prov.describe_brief()}]" for value, prov in self.sources]
        return "takeover_mode.enabled set to conflicting values: " + "; ".join(parts)


@dataclass(frozen=True)
class UnrecognizedFallbackSetting:
    """
    A ``*_fallback`` setting written with an unrecognized value.

    Every such setting resolves such a value to its own safe fallback and keeps going;
    without this record that happens with no diagnostic anywhere, so a one-character typo
    reads as unexpected behaviour rather than a typo (see
    :meth:`~toolguard.configuration.config.Configuration.unrecognized_fallback_settings`, which produces
    these).

    Attributes:
        key: The setting name -- ``'no_match_fallback'``, ``'undecidable_fallback'``, or
            one of their ``'*_in_auto_mode'`` counterparts.
        value: The offending value EXACTLY as written in the file, rendered as
            a string (a non-string value, e.g. a bool or a table, is equally
            unusable and equally silent, so it is reported the same way).
        provenance: Origin of the layer that set it, so the warning can name
            the file to edit.
        accepted: The spellings to advertise in the warning -- the same set for every
            key, and deliberately not the internal canonical set (see
            ``_ACCEPTED_FALLBACK_SPELLINGS``).
        falls_back_to: What the setting resolves to instead, described in prose --
            ``"'ask'"`` for the two base settings, ``"the non-auto-mode setting"`` for
            their ``'*_in_auto_mode'`` counterparts, which have no fixed default of
            their own.
    """

    key: str
    value: str
    provenance: "Provenance"
    accepted: Tuple[str, ...]
    falls_back_to: str = "'ask'"

    def describe(self) -> str:
        """
        Return a one-line description naming the bad value, the setting, the file, and the
        accepted spellings.
        """
        return (
            f"{self.key} = {self.value!r} in {self.provenance.describe_brief()} "
            f"is not a recognized value; falling back to {self.falls_back_to}. "
            f"Accepted values: {', '.join(self.accepted)}"
        )


@dataclass(frozen=True)
class TakeoverConfig:
    """
    Resolved takeover-mode configuration.

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
            'allow_with_warning', 'allow', or the deprecated legacy 'warn_deny' alias)
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
        return frozenset(strip_tool_wrapper(p) for p in combined)
