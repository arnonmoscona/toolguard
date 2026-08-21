"""
Plain configuration data types, split out of :mod:`toolguard.config` so this module can
stay a leaf.

It imports only :mod:`toolguard.rule_entry`, and must never import :mod:`toolguard.config`
in return -- see :class:`RuntimeVerdict`, :class:`UnitVerdict`, and :class:`LevelMatch`'s
own docstrings for the specific circular imports this leaf avoids.
"""

from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import List, Mapping, Optional, Protocol, Tuple

from toolguard.rule_entry import RuleEntry, _strip_tool_wrapper


@dataclass(frozen=True)
class Provenance:
    """
    Display-only origin of a single configuration source.

    Carries enough for a human to tell where a layer's content came from, without exposing
    file/format decisions as control flow to clients.

    Attributes:
        level: Conceptual level label ('project', 'user', or 'explicit' for
            a CLAUDE_SETTINGS_PATH source).
        source_type: 'claude' (native settings), 'toolguard_hook', or
            'toolguard_hook_rules' (a rules-directory file).
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
        Return a compact ``level: path`` label, terse enough not to bloat a decision reason
        (e.g. ``[project: /home/me/proj/.claude/toolguard_hook.toml]``) or the audit log.
        """
        return f"{self.level}: {self.path}"


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
            :func:`~toolguard.config._rules_dirs`) and lost the cross-directory,
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
class ToolPatternLayer:
    """
    Per-layer allow/deny/ask entries for a single tool, with provenance.

    Takeover-mode filtering, if any, has already been applied -- to allow entries on native
    layers only. Deny and ask entries are never filtered.

    The wrapper-intact :class:`~toolguard.rule_entry.RuleEntry` tuples (``allow_entries``/
    ``deny_entries``/``ask_entries``) are the only storage; ``allow``/``deny``/``ask`` below
    are derived properties over them, not independently populated -- so the two can never
    drift out of alignment with each other.

    Attributes:
        provenance: Origin of the patterns in this layer.
        allow_entries: This layer's allow rules, wrapper-intact, in order.
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
    """Return *layer*'s entries for ``kind``; anything but ``'allow'``/``'ask'`` selects
    ``deny_entries``."""
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

    Companion to :func:`provenance_for_pattern` (same first-layer-wins search), kept as a
    separate function rather than folded into it: not every caller of
    ``provenance_for_pattern`` has a use for the entry, so a combined return type would hand
    those call sites an unused value.

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

    Both settings resolve such a value to the safe ``'ask'`` and keep going; without this
    record that happens with no diagnostic anywhere, so a one-character typo reads as
    maximum-friction behaviour rather than a typo (see
    :meth:`~toolguard.config.Configuration.unrecognized_fallback_settings`, which produces
    these).

    Attributes:
        key: The setting name -- ``'no_match_fallback'`` or
            ``'undecidable_fallback'``.
        value: The offending value EXACTLY as written in the file, rendered as
            a string (a non-string value, e.g. a bool or a table, is equally
            unusable and equally silent, so it is reported the same way).
        provenance: Origin of the layer that set it, so the warning can name
            the file to edit.
        accepted: The spellings to advertise in the warning -- the same set for both
            keys, and deliberately not the internal canonical set (see
            ``_ACCEPTED_FALLBACK_SPELLINGS``).
    """

    key: str
    value: str
    provenance: "Provenance"
    accepted: Tuple[str, ...]

    def describe(self) -> str:
        """
        Return a one-line description naming the bad value, the setting, the file, and the
        accepted spellings.
        """
        return (
            f"{self.key} = {self.value!r} in {self.provenance.describe_brief()} "
            f"is not a recognized value; falling back to 'ask'. "
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
        return frozenset(_strip_tool_wrapper(p) for p in combined)


@dataclass(frozen=True)
class ConflictOverride:
    """
    A more-specific ``allow`` overriding a less-specific ``deny``.

    Records BOTH sides of an allow-over-deny override so the conflict log can
    cite the winning allow and the overridden deny by provenance. The decision
    itself is unchanged (more-specific-wins keeps the allow); this is purely a
    record of the override for human/LLM review.

    The command/path that triggered the override is NOT stored here -- it travels
    alongside this record instead, as the other half of :attr:`RuntimeVerdict.overrides`'s
    ``(identifier, ConflictOverride)`` pair (see that attribute's own docstring for what
    *identifier* is per verdict kind).

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
class CommandSpellings:
    """
    The further spellings of one leaf command each kind of pattern list may match.

    Empty on both sides -- the default -- matches the command exactly as spelled, which
    is what a caller holding no parse of it should pass.

    Lives here because it is built by
    :func:`toolguard.parser.command_extractor.command_spellings` and consumed by
    :mod:`toolguard.permissions`, whose per-module import allow-list in
    ``test/unit/test_architecture.py`` excludes the parser.

    Each side pools TWO independent sources, built by
    :func:`~toolguard.parser.command_extractor.command_spellings`, that differ in
    whether they are gated:

    - A leading ``NAME=value`` assignment (ticket 77) IS gated: restricting sees past
      it unconditionally; granting only for names configured safe to look past. Making
      an unsafe assignment ungrantable is the reason this pair has two sides at all.
    - A stripped wrapper, e.g. ``timeout``/``nice``/bare ``xargs`` (ticket 82), is NOT
      gated: both sides see past one whenever found, because native strips wrappers
      before matching an ALLOW rule too (its own worked example is
      ``Bash(npm test *)`` matching ``timeout 30 npm test``).

    Attributes:
        restricting: What a deny, ask or hard_deny list may also match.
        granting: What an allow list, or a hard-deny carve-out, may also match.
    """

    restricting: Tuple[str, ...] = ()
    granting: Tuple[str, ...] = ()


@dataclass(frozen=True)
class LevelMatch:
    """
    A single hierarchy-level (or hard-deny-pool) pattern-match result.

    "No match" is represented by the caller returning ``None`` instead of constructing a
    ``LevelMatch``, never by an empty/placeholder ``matched_pattern``.

    A third, lower altitude than :class:`UnitVerdict` (one sub-command's outcome) and
    :class:`RuntimeVerdict` (the whole runtime verdict): the raw match at one hierarchy level
    or hard-deny pool, before any provenance lookup, ``additionalContext`` enrichment, or
    allow-over-deny override detection is attached. Deliberately not named with a "Verdict"
    suffix: a hierarchy-level match is not itself a governed-tool decision, only an input to
    one.

    Lives here rather than in :mod:`toolguard.resolve`: :mod:`toolguard.permissions` and
    :mod:`toolguard.file_matching` both construct it, and ``resolve.py`` imports FROM both of
    them, so either importing a type back out of ``resolve.py`` would be circular. This
    shared leaf lets all three import it.

    Attributes:
        decision: ``'allow'``, ``'ask'``, or ``'deny'`` -- this level's/
            pool's own decision, before any cascade-wide clamp (e.g. the
            parse-failure ASK floor, applied later by
            :func:`~toolguard.permission_resolution.resolve_permission_cascade`)
            is applied.
        reason: Human-readable reason for THIS level's/pool's own match,
            before provenance is appended as a bracketed suffix (that
            happens one layer up, in
            :func:`~toolguard.permission_resolution._resolve_unclamped`).
        matched_pattern: The winning (wrapper-free) pattern text. Always a
            genuine ``str`` when a ``LevelMatch`` is constructed at all.
    """

    decision: str
    reason: str
    matched_pattern: str


@dataclass(frozen=True)
class UnitVerdict:
    """
    Per-sub-command resolution record inside a compound Bash permission check.

    Deliberately not collapsed into :class:`RuntimeVerdict`: doing so would destroy the only
    structured, per-sub-command record of what a compound command did, forcing a consumer to
    re-derive it by re-parsing the combined reason string.

    Lives here rather than in :mod:`toolguard.resolve` (where it is also constructed):
    :mod:`toolguard.compound` constructs it too, and ``resolve.py`` imports FROM
    ``compound.py``, so ``compound.py`` importing a type back out of ``resolve.py`` would be
    circular. This shared leaf lets both import it.

    A caller can use ``sub_matches`` to identify which sub-command of a compound command
    produced the verdict (first deny => compound deny, first ask => compound ask, else
    allow) and to surface per-sub-command provenance.

    Attributes:
        sub_command: The sub-command's real, full source text. For an undecidable segment
            this is the segment's own text (it has no rule-matched parts at all). For an
            ask-floor leaf (foreign inline code / heredoc sink) this is NOT the
            outer-command stub :mod:`toolguard.compound` resolves internally to check for an
            explicit deny; see ``matched_rule`` below for why the stub's own match must not
            be attributed here.
        decision: ``'allow'``, ``'ask'``, or ``'deny'`` -- the leaf's final decision, after
            any ``undecidable_fallback`` floor has been applied. For an ask-floor leaf this
            can differ from what the stub itself resolved to; see ``fallback_kind``.
        matched_rule: The winning rule pattern (wrapper-free), or the hard-deny pattern when
            hard-denied. ``None`` when no rule matched, or when ``fallback_kind`` is not
            ``None``: a rule matching the ask-floor leaf's stub never verified the
            leaf's real, unread content, so it must never be recorded here as the reason the
            decision stands -- the escape hatch decided, not the rule.
        provenance: Origin of the layer whose rule matched, or ``None`` for a
            hard-deny (pooled across levels, no single provenance), a
            fail-closed default deny, or an escape-hatch outcome (same
            reasoning as ``matched_rule`` above).
        fallback_kind: ``'warned'``, ``'silent'``, ``'denied'``, or ``None`` -- structural
            counterpart of :func:`~toolguard.compound.fallback_kind_for_reason`, computed
            once here rather than re-derived by parsing ``reason`` downstream.
            ``'warned'``/``'silent'`` name the ``allow`` escape hatch (with/without a
            warning); ``'denied'`` names the ``undecidable_fallback=deny`` escape hatch.
            ``None`` whenever no allow/deny escape hatch produced this outcome -- including
            the ASK floor itself, which is not an allow or deny escape hatch.
        reason: Human-readable reason for THIS unit's own decision -- for an ask-floor leaf
            or an undecidable segment, it already names the escape hatch. Distinct from
            :attr:`RuntimeVerdict.reason`, which is the WHOLE compound's combined reason,
            not any one unit's.
        additional_context: This unit's own ``additionalContext`` enrichment, or ``None``
            when the floor (not a rule match) decided. Distinct from
            :attr:`RuntimeVerdict.additional_context`, the compound-wide accumulation
            across every contributing unit.
        audit_only: ``True`` for a raw record itemising one of an ``'inline_code'``
            unit's ``CommandUnit.audit_parts`` OR ``deny_check_parts`` (see
            :mod:`toolguard.compound`) -- present in ``RuntimeVerdict.sub_matches``
            for the audit trail (a ``deny_check_parts`` entry only when its own
            decision is ``'deny'`` or ``'ask'``, regardless of which entry actually
            decided the unit; an ``audit_parts`` entry always), but excluded from
            :func:`~toolguard.resolve._deciding_sub_match`'s search for the
            sub-command that decided the compound. When such an entry's own
            ``deny``/``ask`` genuinely decided its unit, that decision reaches
            ``matched_rule``/``provenance`` through the unit's own (non-audit-only)
            verdict instead -- never through this record directly. ``False`` for
            every other ``UnitVerdict``.
    """

    sub_command: str
    decision: str
    matched_rule: Optional[str]
    provenance: Optional["Provenance"]
    reason: str
    additional_context: Optional[str]
    fallback_kind: Optional[str] = None
    audit_only: bool = False


@dataclass(frozen=True)
class RuntimeVerdict:
    """
    The single runtime verdict type every governed-tool resolution returns.

    Used for the Bash cascade, the file-path cascade, and the internal cascade verdict each
    one folds over -- see the per-field notes below for what varies between those uses. A
    RUNTIME altitude, distinct from :class:`UnitVerdict` (the UNIT altitude nested inside it
    via ``sub_matches``).

    Why this lives in config_types.py, not resolve.py
    ---------------------------------------------------
    :mod:`toolguard.permission_resolution` constructs this type directly, as the internal
    cascade verdict, and its own docstring declares it never imports
    :mod:`toolguard.resolve` -- correctly, since ``resolve.py`` imports FROM
    ``permission_resolution``, so the reverse would be circular.
    :mod:`toolguard.config_types` is the shared leaf both modules can import -- and since
    :class:`Provenance` and :class:`ConflictOverride` are also defined here,
    ``provenance``/``overrides`` below can be typed precisely instead of falling back to
    ``Any``.

    ``tool``/``target``
    --------------------
    ``None`` until populated by one of :mod:`toolguard.resolve`'s two public entry points
    (:func:`~toolguard.resolve.resolve_bash_permission_detailed`,
    :func:`~toolguard.resolve.resolve_file_path_permission_detailed`), the only callers with
    an actual command/file_path string in scope; the internal cascade verdict leaves both
    ``None``. ``tool`` for a Bash/MCP-terminal resolution is always the literal string
    ``'Bash'``, matching :func:`~toolguard.resolve.resolve_bash_permission_detailed`'s
    convention of always evaluating against the Bash rule set regardless of the invoking
    tool's real name; a caller that needs the real name (e.g. an MCP terminal tool routed
    through the Bash rule set) restores it on the returned verdict afterwards.

    ``overrides``
    -------------
    A list of ``(identifier, ConflictOverride)`` pairs rather than a single optional one,
    because a compound Bash command can have one override per sub-command:

    - Bash compound: *identifier* is the overriding sub-command string, one entry per
      sub-command whose more-specific allow overrode a less-specific deny.
    - File path: *identifier* is the file path itself (== ``target``); 0 or 1 entries.
    - The internal cascade verdict: *identifier* is ``None`` -- no sub_command/target
      string is in scope at that layer (see ``tool``/``target`` above); the two public
      ``resolve.py`` entry points re-pair the bare override with the real identifier once
      they have one.

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
        overrides: See "``overrides``" above. Empty when the overall decision is
            not ``'allow'`` (only allow-over-deny overrides on an ALLOWED verdict
            are conflicts).
        sub_matches: One :class:`UnitVerdict` per audited unit, in order -- one per
            sub-command for an ordinary leaf, but one for the WHOLE leaf where a floor
            (not a sub-command's own rule match) decided it (see
            :attr:`~toolguard.compound.CommandUnit.audits_as_one`). Empty for a
            file-path verdict (file paths are never compound) and for the internal cascade
            verdict. Lets a caller identify the deciding sub-command and its
            provenance/matched-rule without re-running the resolver.
        additional_context: The accumulated ``additionalContext`` enrichment
            text, or ``None`` when no contributing rule carried one, no rule
            matched, or the ASK floor cleared the match. Word-capped via
            :func:`toolguard.compound.cap_context_words` regardless of
            whether the decision was allow, ask, or deny.
        fallback_warning: ``True`` when this 'allow' decision should be
            routed to the WARNING log stream -- only for an
            'allow' produced by the WARNED value of ``no_match_fallback`` or
            (for Bash) ``undecidable_fallback``. ``False`` for every other
            decision, including an explicit rule match and an 'allow'
            produced by a no-warning fallback value. Structurally-known
            data on the production path (never derived from *reason*
            there); :mod:`toolguard.compound`'s own test-only legacy
            driver still derives it from *reason* text.
        matched_rule: The deciding rule's pattern text (wrapper-free), or
            ``None`` when there is no single RULE to attribute -- a
            fail-closed default, a fallback/floor escape hatch (even when
            the escape-hatch leaf's own pre-floor decision happens to equal
            the final decision), or, for a compound Bash verdict, no single
            sub-command decided. Also deliberately ``None`` for a file-path
            hard-deny (unlike a Bash hard-deny, which does record its
            pattern here -- see :func:`~toolguard.resolve.resolve_file_path_permission_detailed`'s
            own comment for why). Not derived from *reason*, though
            ``hook.py``'s deny log entry still uses the reason-based
            :func:`~toolguard.compound.fallback_kind_for_reason` for its own
            rendering (the ask log entry uses the full ``reason`` text verbatim
            and never reaches that classifier).
        tool: See "``tool``/``target``" above.
        target: As ``tool``, the command string (Bash) or file path
            (file-path tools) under evaluation.
    """

    decision: str
    reason: str
    # Defaults to None so a synthetic guard-clause verdict (e.g. one built for an input that
    # never reached the resolver at all) can be constructed from just decision/reason --
    # every other "nothing to attribute" field below defaults away too.
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


# ---------------------------------------------------------------------------
# Configuration-surface Protocols for the permission_resolution / resolve /
# file_matching seam.
# ---------------------------------------------------------------------------
#
# permission_resolution.py is architecturally forbidden from importing
# toolguard.config, so config cannot be typed as Configuration at its entry
# points. These Protocols close that gap by stating, structurally, the exact
# subset of Configuration each caller's config parameter needs -- checked by
# pyright without adding an import edge to toolguard.config.


class ResolutionConfig(Protocol):
    """
    The minimal configuration surface :mod:`toolguard.permission_resolution` reads from
    ``config`` to run its decision cascade.

    Closes the gap left by :mod:`toolguard.permission_resolution` being architecturally
    forbidden from importing :mod:`toolguard.config`: any object handed in as ``config`` --
    in practice always a real :class:`~toolguard.config.Configuration`, but a test double
    needs only this surface -- must structurally supply exactly these five members.
    Restating the whole of ``Configuration`` here would defeat the purpose.

    :mod:`toolguard.resolve` needs a wider surface, so none of its ``config`` parameters
    are typed against this Protocol -- see :class:`ResolveConfig`.
    """

    @property
    def parse_failures(self) -> Tuple[Tuple[Path, str], ...]:
        """
        Every governed config file that failed to parse, as ``(path, message)`` pairs. Read
        directly by callers and passed to
        :func:`~toolguard.permission_resolution.apply_parse_failure_floor` to clamp a
        decision to ``'ask'`` whenever any governed file is broken -- a caller supplying a
        filtered or empty value here silently disables that floor for whatever it omits.

        A read-only ``@property``, not a plain attribute: the real implementer,
        :class:`~toolguard.config.Configuration`, is a frozen dataclass, and pyright treats
        a frozen dataclass field as read-only, so a plain writable attribute here would not
        structurally match it.
        """
        ...

    def permission_levels_with_provenance(
        self, tool_name: str
    ) -> Tuple[
        Tuple[
            Tuple[str, ...],
            Tuple[str, ...],
            Tuple[str, ...],
            Tuple["ToolPatternLayer", ...],
        ],
        ...,
    ]:
        """
        Return ``tool_name``'s ``(allow, deny, ask, layers)`` pattern tuples, one per
        hierarchy level, most-specific first.

        Drives the more-specific-wins cascade: each level's ``(allow, deny, ask)`` triple is
        matched by :func:`~toolguard.permissions.decide_command_at_level_detailed` or
        :func:`~toolguard.file_matching.decide_file_path_at_level_detailed`, and ``layers``
        is kept around so a winning pattern can be mapped back to its source
        :class:`Provenance` via :func:`provenance_for_pattern`/:func:`entry_for_pattern`.
        """
        ...

    def has_any_rules(self, tool_name: str) -> bool:
        """
        Return whether ``tool_name`` has any rule configured anywhere (allow, deny, ask, or
        hard_deny, at any level).

        Distinguishes a genuinely unconfigured tool (always resolves to ``'ask'``, so a
        fresh install is never bricked by a blanket deny) from a configured tool whose rules
        simply did not match the current command/path (governed by
        :meth:`resolved_no_match_fallback` instead).
        """
        ...

    def resolved_no_match_fallback(self) -> str:
        """
        Return the effective ``no_match_fallback`` policy: one of ``'ask'``, ``'deny'``,
        ``'allow_with_warning'``, or ``'allow'`` -- already alias-normalized and defaulted,
        never a raw/unrecognized config value.

        Consulted only in the no-match branch, once every hierarchy level has matched
        nothing.
        """
        ...

    def assignments_looked_past_when_granting(self) -> Tuple[str, ...]:
        """
        Return the assignment variable names an allow rule may be matched past --
        already de-duplicated and defaulted to empty, never a raw config value.

        Only a command carrying a leading ``NAME=value`` assignment can be affected
        by the list, so an empty result is the normal case rather than a gap.
        """
        ...


class ResolveConfig(ResolutionConfig, Protocol):
    """
    The configuration surface :mod:`toolguard.resolve` itself needs -- a strict superset of
    :class:`ResolutionConfig`.

    ``resolve.py`` reads four more members than :class:`ResolutionConfig` declares -- two
    directly (``hard_deny_entries``, ``resolved_undecidable_fallback``), two through the
    file-path helpers it forwards ``config`` into (``hard_deny``, ``resolve_config_path``).
    Inheriting rather than restating those four is deliberate: structural subtyping then
    makes a ``ResolveConfig`` valid wherever a
    ``ResolutionConfig`` is expected, so passing ``config`` down into
    :func:`~toolguard.permission_resolution.resolve_command_permission`/
    :func:`~toolguard.permission_resolution.resolve_file_path_permission` stays sound
    without a cast.
    """

    def resolve_config_path(self, raw_path: str) -> str:
        """
        Anchor a relative file-path pattern's body to the project root.

        A file-path-side concern only -- the Bash cascade never calls it.
        """
        ...

    def hard_deny(self, tool_name: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
        """
        Return the pooled ``(deny_patterns, allow_patterns)`` hard-deny pair for
        ``tool_name``, wrapper-stripped, unioned across every level.

        Checked FIRST, before the normal cascade, for the unoverridable hard-deny pool. The
        file-path path reads this pool from ``config`` directly; the Bash-side equivalent
        pool is instead fetched by the caller and passed to
        :func:`~toolguard.resolve.resolve_bash_permission_detailed` as a plain argument.
        """
        ...

    def hard_deny_entries(
        self, tool_name: str
    ) -> Tuple[Tuple["RuleEntry", ...], Tuple["RuleEntry", ...]]:
        """
        Return the pooled hard-deny ``(deny_entries, allow_entries)`` pair for ``tool_name``
        as wrapper-intact :class:`~toolguard.rule_entry.RuleEntry` objects (carrying
        ``additionalContext`` enrichment).

        Used to look up a matched hard-deny pattern's enrichment text, for both the Bash and
        file-path hard-deny paths.
        """
        ...

    def resolved_undecidable_fallback(self) -> str:
        """
        Return the effective ``undecidable_fallback`` policy: one of ``'ask'``, ``'deny'``,
        ``'allow_with_warning'``, or ``'allow'`` -- already alias-normalized and defaulted.

        Passed to :func:`~toolguard.compound.judge_unit` for every unit of a compound Bash
        command -- a Bash-compound-only concern, unused by the file-path cascade. It floors
        two cases: a grammar-level undecidable segment (no leaves, so it never reaches
        :func:`~toolguard.permission_resolution.resolve_command_permission` at all), and an
        ask-floor leaf (foreign inline code / heredoc sink), which does have a part and does
        reach that resolver, but is floored anyway once the explicit-deny check clears it.
        """
        ...


class PathAnchoring(Protocol):
    """
    The ``config`` member file_matching's matching functions need: project-root anchoring
    for a relative file-path pattern.

    Deliberately narrower than :class:`ResolveConfig`: file-matching's matching functions
    touch nothing else on ``config``, so this one-member Protocol documents that tight
    coupling instead of granting the wider surface ``resolve.py`` itself needs. (The module
    as a whole needs more -- :func:`~toolguard.file_matching.check_file_path_hard_deny` is
    typed :class:`ResolveConfig`, not this Protocol.)
    """

    def resolve_config_path(self, raw_path: str) -> str:
        """Anchor a relative file-path pattern's body to the project root."""
        ...


class FilePathResolutionConfig(ResolutionConfig, PathAnchoring, Protocol):
    """
    The configuration surface :func:`~toolguard.permission_resolution.resolve_file_path_permission`
    needs: the cascade surface (:class:`ResolutionConfig`) plus anchoring
    (:class:`PathAnchoring`) -- the file-path cascade forwards ``config`` one
    layer down into :func:`~toolguard.file_matching.decide_file_path_at_level_detailed`
    for project-root anchoring, which the Bash cascade never needs.
    """
