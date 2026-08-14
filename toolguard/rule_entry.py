"""
Structured allow/deny/ask rule entry: shape normalization and tool scoping.

Centralizes the parsing of a single permission entry -- plain string or the
structured ``{match = "...", ...}`` table form -- into one immutable
:class:`RuleEntry`, so callers no longer need to guess at
``isinstance(perm, str)``. :func:`normalize_entry` does shape normalization;
:func:`entries_for_tool` does the separate tool-scoping step.
:func:`normalize_entry` never silently drops an unusable element -- one that
cannot be normalized always comes back with an
:class:`~toolguard.issues.Issue` explaining why.

This module imports nothing from :mod:`toolguard` except
:mod:`toolguard.issues`, keeping it a leaf that both :mod:`toolguard.config`
and :mod:`toolguard.config_validation` can depend on without a circular
import (``config`` imports ``config_validation``, so neither could host this).

Structured entries are **single-line inline tables only**: TOML 1.0 requires an
inline table on one line, and toolguard's loader is stdlib :mod:`tomllib`. A
multi-line entry makes the whole file unparseable -- see
:func:`toolguard.config._multiline_structured_entry_diagnostic`.
"""

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from toolguard.issues import Issue

#: The table key holding a structured entry's permission pattern, e.g.
#: ``{match = "Bash(git *)", additionalContext = "..."}``. Not itself an
#: enrichment key -- see :data:`KNOWN_ENRICHMENT_KEYS`.
PATTERN_KEY = "match"

#: The enrichment key carrying text to inject into Claude's context when
#: this entry is the deciding match for a tool call.
ADDITIONAL_CONTEXT_KEY = "additionalContext"

#: Enrichment keys this toolguard version understands. ``match`` is the
#: pattern key (:data:`PATTERN_KEY`), not an enrichment key, and is
#: deliberately absent here. An unknown key is a WARNING, never an error --
#: a newer config read by an older toolguard must degrade, not break.
KNOWN_ENRICHMENT_KEYS = frozenset({ADDITIONAL_CONTEXT_KEY})

#: Structural matcher for a ``Tool(inner)`` permission wrapper: an
#: identifier followed by a parenthesised body. The greedy ``.*`` lets the
#: inner body itself contain parentheses (``Bash(foo(bar))`` ->
#: ``foo(bar)``), so no known-tool list is needed.
#:
#: Deliberately NOT ``re.DOTALL``. Used with ``fullmatch``, this is the only
#: check in this module that rejects a multi-line ``match`` value in a
#: structured entry -- a single-line TOML inline table can still carry an
#: embedded newline via a ``\n`` escape, so ``{match = "Bash(a)\nEvil(b)"}``
#: arrives here as one string containing a real newline. Without DOTALL it
#: correctly fails to match; with DOTALL the greedy ``.*`` spans the newline
#: to the LAST ``)``, accepting two concatenated wrappers as one.
_TOOL_WRAPPER_RE = re.compile(r"[A-Za-z0-9_]+\((.*)\)")

#: Sentinel for :attr:`RuleEntry.raw`'s "no raw value recorded" state. MUST
#: NOT be Python's ``None``: a genuine source element can itself BE
#: ``None`` (a JSON ``permissions.allow`` list can contain a literal
#: ``null`` -- TOML has no null, but ``toolguard_hook.json`` is a
#: first-class supported format), and that value must round-trip through
#: :meth:`RuleEntry.to_source` unchanged. Using ``None`` for both "unset"
#: and "a real value" would make the two indistinguishable there: a genuine
#: ``raw=None`` would render as the literal string ``"None"`` instead of
#: the value ``None``, silently corrupting the write.
_UNSET = object()


def _strip_tool_wrapper(pattern: str) -> str:
    """
    Remove a ``Tool(...)`` wrapper from a permission pattern, if present.

    Patterns are authored wrapped (``Bash(git *)``) but matched on the
    unwrapped inner pattern (``git *``).

    Args:
        pattern: A permission pattern, possibly wrapped in ``Tool(...)``.

    Returns:
        The unwrapped pattern, or *pattern* unchanged if it was not wrapped.
    """
    match = _TOOL_WRAPPER_RE.fullmatch(pattern)
    if match:
        return match.group(1)
    return pattern


def is_tool_wrapper(pattern: object) -> bool:
    """
    Report whether a permission pattern is a ``Tool(...)`` wrapper.

    Args:
        pattern: A candidate value; only a ``str`` can match.

    Returns:
        True if ``pattern`` is a string whose whole content is an
        ``identifier(...)`` tool wrapper.
    """
    return isinstance(pattern, str) and _TOOL_WRAPPER_RE.fullmatch(pattern) is not None


def strip_tool_wrapper(pattern: str) -> str:
    """Remove a ``Tool(...)`` wrapper from a bare pattern string -- the public
    entry point for a caller holding no :class:`RuleEntry`."""
    return _strip_tool_wrapper(pattern)


@dataclass(frozen=True)
class RuleEntry:
    """One allow/deny/ask entry, plain-string or structured form.

    Format-agnostic: the same type comes out of TOML, JSON, and
    synthesized-by-tooling entries, so every consumer sees one shape.
    """

    #: Wrapper-INTACT, exactly as written, e.g. ``"Bash([regex]^git .*)"``.
    #: Deliberately NOT stripped here: most consumers are tool-agnostic and
    #: need the wrapped form; a consumer that wants the bare inner pattern
    #: strips it itself via :attr:`stripped_pattern`.
    pattern: str

    #: Arbitrary key/value pairs from the entry's structured table (every
    #: key except :data:`PATTERN_KEY`), unconstrained in value type -- an
    #: unrecognized key's value is still recorded here for round-tripping,
    #: so this cannot be narrowed to primitives. Always built as
    #: ``MappingProxyType(...)`` so "frozen" is not a lie.
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    #: The exact source value this was parsed from (a ``str`` or a
    #: ``dict``), or :data:`_UNSET` when this entry was synthesized with
    #: nothing original to preserve. Lets an untouched entry re-emit
    #: byte-for-byte via :meth:`to_source` instead of being re-rendered.
    #: Test presence via :attr:`has_raw`, never ``raw is None`` -- see
    #: :data:`_UNSET`. compare=False: formatting is not identity.
    raw: object = field(default=_UNSET, compare=False, repr=False)

    #: True exactly when ``pattern`` is a SYNTHESIZED, non-matchable
    #: stand-in (``repr(raw)``), assigned by
    #: :func:`normalize_entries_preserving` for a raw element that could
    #: not be normalized into a real pattern (e.g. a structured entry
    #: missing its ``match`` key). Never ``True`` for an entry
    #: :func:`normalize_entry` built directly.
    #:
    #: A write-path caller building
    #: :func:`~toolguard.config_write_guard.verified_write_config`'s
    #: ``expected_patterns`` MUST exclude entries where this is ``True``
    #: (use :func:`real_patterns`, which already does): that guard checks
    #: "expected" patterns against the real text about to be written, which
    #: can never contain a synthesized ``repr()`` string, so passing one
    #: through as "expected" always looks like a dropped rule, wrongly
    #: refuses the write, and -- because ``expected_patterns`` is rebuilt
    #: from the file's own contents on every run -- keeps refusing every
    #: later write of that file until the malformed entry is fixed by hand.
    #:
    #: An explicit field rather than inferring "looks synthetic" from the
    #: pattern's string shape, which would be brittle and could itself
    #: misclassify a legitimate pattern.
    #:
    #: compare=False, repr=False: a write-path bookkeeping flag, not part
    #: of this entry's identity (mirrors :attr:`raw`).
    synthesized_pattern: bool = field(default=False, compare=False, repr=False)

    @property
    def stripped_pattern(self) -> str:
        """
        The tool-wrapper-stripped form of :attr:`pattern`.

        Returns:
            :attr:`pattern` with any ``Tool(...)`` wrapper removed.
        """
        return _strip_tool_wrapper(self.pattern)

    @property
    def additional_context(self) -> Optional[str]:
        """
        The text to inject into Claude's context when this entry decides, if any.

        The single accessor for ``additionalContext``, so no consumer reads
        ``metadata`` directly and every consumer applies the same rules:

        - A non-string value yields ``None``. It is reported as a validation
          error at parse time (see :func:`_additional_context_issues`) and
          must not reach the injection path, where it would render as
          ``"True"`` or ``"3"`` in the model's context.
        - A string that is empty or only whitespace yields ``None``, so a
          caller can test one value rather than distinguishing "absent" from
          "present but blank". Both mean "inject nothing".

        Returns:
            The context text, or ``None`` when this entry carries none usable.
        """
        value = self.metadata.get(ADDITIONAL_CONTEXT_KEY)
        if isinstance(value, str) and value.strip():
            return value
        return None

    @property
    def is_structured(self) -> bool:
        """Report whether this entry was parsed from a structured (dict) source."""
        return isinstance(self.raw, dict)

    @property
    def has_raw(self) -> bool:
        """
        Report whether this entry has an original source value to round-trip.

        True whenever ``raw`` was explicitly recorded, including a genuine
        ``raw=None``. Use this rather than ``raw is None``, which cannot tell
        a genuine null from unset -- see :data:`_UNSET`.
        """
        return self.raw is not _UNSET

    def identity(self) -> Tuple[str, str]:
        """
        Canonical hashable identity: ``(pattern, canonicalized metadata)``.

        There are deliberately three different comparison semantics in this
        type, used for different purposes -- do not try to unify them:

        - ``.pattern`` alone answers "is this the same RULE" (used for
          divergence/migration comparisons, and sorting). An entry with
          metadata on one side and none on the other is still the SAME rule,
          not a divergence.
        - ``identity()`` (this method) answers "is this literally the same
          entry, enrichment included" (used for exact-duplicate detection).
        - :func:`merge_entries` defines its own consolidation semantics on
          top of both: it groups by ``.pattern``, then uses ``identity()``
          as an internal fast path to collapse literal duplicates before
          applying its own bare-vs-structured and union/conflict rules.

        Returns:
            A ``(pattern, metadata_json)`` tuple, where ``metadata_json`` is
            ``metadata`` rendered via ``json.dumps(..., sort_keys=True)`` so
            that equal mappings always produce an equal, hashable key
            regardless of key insertion order.
        """
        return (
            self.pattern,
            json.dumps(dict(self.metadata), sort_keys=True, default=str),
        )

    def __hash__(self) -> int:
        """
        Hash consistent with :meth:`identity`, not with dataclass field equality.

        A ``MappingProxyType`` is not hashable, with or without keys, so a
        dataclass-generated ``__hash__`` over :attr:`metadata` would raise
        ``TypeError`` on every entry. Hashing the JSON-canonicalized
        identity sidesteps that.
        """
        return hash(self.identity())

    def to_source(self) -> object:
        """
        The value to write back into a config file (TOML table / JSON object).

        Returns ``raw`` verbatim whenever one was recorded -- the round-trip
        guarantee, and why ``raw`` needs the :data:`_UNSET` sentinel.
        Otherwise renders fresh: a bare string when there is no metadata, a
        ``{PATTERN_KEY: pattern, **metadata}`` table when there is.

        Returns:
            ``raw`` unchanged if recorded (even when that value is ``None``);
            otherwise a freshly rendered ``str`` or ``dict``.
        """
        if self.has_raw:
            return self.raw
        if not self.metadata:
            return self.pattern
        return {PATTERN_KEY: self.pattern, **dict(self.metadata)}


def _reject(
    level: str, message: str, corrective_steps: str
) -> Tuple[None, Tuple[Issue, ...]]:
    """Build :func:`normalize_entry`'s ``(None, (Issue,))`` rejection return."""
    return None, (
        Issue(level=level, message=message, corrective_steps=corrective_steps),
    )


def normalize_entry(
    raw: object, is_native: bool
) -> Tuple[Optional["RuleEntry"], Tuple[Issue, ...]]:
    """
    Normalize one allow/deny/ask config element into a :class:`RuleEntry`.

    Shape normalization ONLY -- tool-agnostic, and the returned ``pattern``
    (when present) keeps its ``Tool(...)`` wrapper intact; tool scoping is
    :func:`entries_for_tool`'s separate job. An unusable element is never
    silently dropped: it always comes back as ``(None, issues)`` with at
    least one issue explaining why.

    Behaviour:

    - A plain, non-empty ``str`` always normalizes to a bare
      ``RuleEntry(pattern=raw, metadata={}, raw=raw)`` with no issues, even
      if it is not ``Tool(...)``-wrapped -- :func:`entries_for_tool` simply
      filters such an entry out later, without an issue. Wrapper-shape
      validation is applied to STRUCTURED entries only: erroring on an
      unwrapped plain string would newly report configs that load without
      complaint today, while structured entries are new syntax with no
      already-written configs to protect.
    - A plain ``str`` containing a newline or carriage return normalizes to
      ``(None, issues)`` with an ``error``-level :class:`Issue`: the break
      defeats the ``Tool(...)`` wrapper strip (:data:`_TOOL_WRAPPER_RE` is
      not ``re.DOTALL``), so the entry can be accepted, scoped to a tool, and
      displayed as configured while matching no command -- silently inert,
      which is worse than a load error for a ``deny``.
    - An empty string is the other exception, normalizing to
      ``(None, issues)`` with a ``warning``-level :class:`Issue`:
      unambiguously a mistake (there is no pattern it could ever be), but
      ``warning`` rather than ``error`` because the point is to stop the
      SILENT drop, not to turn a loadable config into a failing one.
    - A ``dict`` with a valid (non-empty, wrapper-shaped, string)
      :data:`PATTERN_KEY` value normalizes to a :class:`RuleEntry` whose
      ``metadata`` holds every other key. A key outside
      :data:`KNOWN_ENRICHMENT_KEYS` does not block normalization but
      produces one ``warning`` :class:`Issue` each.
    - A ``dict`` missing :data:`PATTERN_KEY`, or whose value is not a
      non-empty, wrapper-shaped string, normalizes to ``(None, issues)``
      with an ``error`` :class:`Issue`.
    - A ``dict`` is entirely rejected when ``is_native`` is True: structured
      entries are a toolguard extension and are never interpreted from a
      native Claude ``settings.json`` layer. This normalizes to
      ``(None, issues)`` with a ``warning`` Issue -- a stray table in a
      native file is unusual, not an error in itself. A plain string under
      ``is_native=True`` is unaffected.
    - Anything else (``int``, ``None``, ``list``, ``bool``, ...) normalizes
      to ``(None, issues)`` with an ``error`` Issue.

    Args:
        raw: One element from a config's ``permissions.allow``/``ask``/
            ``deny`` list, of unknown/unvalidated shape.
        is_native: True when ``raw`` came from a native Claude settings
            layer (as opposed to a toolguard-owned config layer). Gates
            structured-entry recognition.

    Returns:
        A ``(entry, issues)`` pair. ``entry`` is ``None`` exactly when
        ``raw`` could not be normalized; ``issues`` is a (possibly empty)
        tuple of :class:`Issue`, always non-empty when ``entry`` is
        ``None``, and possibly non-empty (a warning) even when ``entry`` is
        not ``None``.
    """
    if isinstance(raw, str):
        if not raw:
            return _reject(
                level="warning",
                message="Permission entry is an empty string.",
                corrective_steps="Remove the empty entry or provide a "
                "valid 'Tool(pattern)' permission string.",
            )
        if "\n" in raw or "\r" in raw:
            return _reject(
                level="error",
                message=(
                    "Permission entry contains a newline, which defeats the "
                    f"'Tool(...)' wrapper strip and can never match a command: {raw!r}"
                ),
                corrective_steps="Remove the embedded newline; write one "
                "'Tool(pattern)' entry per list element.",
            )
        return RuleEntry(pattern=raw, metadata=MappingProxyType({}), raw=raw), ()

    if isinstance(raw, dict):
        if is_native:
            return _reject(
                level="warning",
                message=(
                    "Structured rule entries are ignored in native "
                    f"Claude settings files: {raw!r}"
                ),
                corrective_steps="Move structured entries "
                '(e.g. {match = "Bash(...)", ...}) to a toolguard '
                "config file (toolguard_hook.toml).",
            )

        if PATTERN_KEY not in raw:
            return _reject(
                level="error",
                message=(
                    f"Structured rule entry is missing required key "
                    f"'{PATTERN_KEY}': {raw!r}"
                ),
                corrective_steps=f"Add a '{PATTERN_KEY}' key holding the "
                "wrapped permission pattern, e.g. "
                f'{{{PATTERN_KEY} = "Bash(git *)"}}.',
            )

        pattern = raw[PATTERN_KEY]
        if not is_tool_wrapper(pattern):
            return _reject(
                level="error",
                message=(
                    f"Structured rule entry's '{PATTERN_KEY}' value is not a "
                    f"valid 'Tool(pattern)' permission string: {pattern!r}"
                ),
                corrective_steps=f"Set '{PATTERN_KEY}' to a wrapped "
                'permission pattern, e.g. "Bash(git *)".',
            )

        metadata = MappingProxyType({k: v for k, v in raw.items() if k != PATTERN_KEY})
        issues = tuple(
            Issue(
                level="warning",
                message=(
                    f"Unknown key '{key}' in structured rule entry for "
                    f"'{pattern}' -- ignored by this toolguard version."
                ),
                corrective_steps="Check for a typo, or upgrade toolguard if "
                "this key is from a newer config format.",
            )
            for key in metadata
            if key not in KNOWN_ENRICHMENT_KEYS
        )
        issues += _additional_context_issues(pattern, metadata)
        return RuleEntry(pattern=pattern, metadata=metadata, raw=raw), issues

    return _reject(
        level="error",
        message=(
            f"Permission entry has an unsupported type {type(raw).__name__!r}: {raw!r}"
        ),
        corrective_steps="Use either a 'Tool(pattern)' string or a "
        f'structured table like {{{PATTERN_KEY} = "Tool(pattern)"}}.',
    )


def _additional_context_issues(pattern: str, metadata: Mapping[str, object]) -> tuple:
    """
    Validate an ``additionalContext`` value, if the entry carries one.

    The value is injected into Claude's context as text, so anything that is
    not a string is a configuration mistake rather than something to coerce:
    silently stringifying ``true`` or ``3`` would put the literal word "True"
    or "3" into the model's context and look deliberate.

    Reported as an ``error``-level :class:`~toolguard.issues.Issue`, but
    DELIBERATELY does not reject the entry. The permission rule itself is
    still perfectly valid, and dropping it because its advisory text has the
    wrong type would turn a cosmetic mistake into a silently missing rule --
    exactly backwards for a ``deny``. The rule keeps working; only the
    enrichment is ignored (see :attr:`RuleEntry.additional_context`).

    Args:
        pattern: The entry's pattern, for the message.
        metadata: The entry's enrichment mapping.

    Returns:
        A tuple of zero or one Issue.
    """
    if ADDITIONAL_CONTEXT_KEY not in metadata:
        return ()
    value = metadata[ADDITIONAL_CONTEXT_KEY]
    if isinstance(value, str):
        return ()
    return (
        Issue(
            level="error",
            message=(
                f"'{ADDITIONAL_CONTEXT_KEY}' must be a string in the rule entry "
                f"for '{pattern}', got {type(value).__name__} ({value!r}) -- the "
                f"rule still applies, but no context will be injected."
            ),
            corrective_steps=(
                f'Quote the value, e.g. {{ {PATTERN_KEY} = "{pattern}", '
                f'{ADDITIONAL_CONTEXT_KEY} = "explanatory text" }}.'
            ),
        ),
    )


def entries_for_tool(
    entries: Tuple["RuleEntry", ...], tool_name: str
) -> Tuple["RuleEntry", ...]:
    """
    Filter normalized entries down to those scoped to ``tool_name``.

    Tool scoping ONLY -- the second half of the shape-normalization /
    tool-scoping split (see :func:`normalize_entry` for the first half).
    Keeps entries whose ``.pattern`` starts with ``f"{tool_name}("`` and
    ends with ``")"``. Does NOT strip the ``Tool(...)`` wrapper -- use
    :attr:`RuleEntry.stripped_pattern` for that.

    Args:
        entries: Already-normalized entries (e.g. from :func:`normalize_entry`).
        tool_name: Tool to scope to, e.g. ``"Bash"`` or ``"Read"``.

    Returns:
        The subset of ``entries`` whose pattern is wrapped for ``tool_name``,
        in their original relative order.
    """
    prefix = f"{tool_name}("
    return tuple(
        entry
        for entry in entries
        if entry.pattern.startswith(prefix) and entry.pattern.endswith(")")
    )


def normalize_entries_preserving(
    raw_list: object, is_native: bool
) -> Tuple["RuleEntry", ...]:
    """
    Normalize a raw allow/deny/ask list for a write-path caller, never dropping.

    A caller matching against rules can simply drop an element
    :func:`normalize_entry` could not parse -- an unusable entry cannot
    govern anything anyway. A caller about to WRITE the file back out
    cannot: dropping it would silently delete part of the user's config.

    A raw element that fails to normalize is instead wrapped as a
    :class:`RuleEntry` around the RAW value unchanged (so
    :meth:`RuleEntry.to_source` reproduces it verbatim), with a synthesized
    ``pattern`` of ``repr(raw)`` -- deliberately not a real ``Tool(...)``
    pattern, so it can never collide with a legitimately normalized entry,
    while still being a deterministic, sortable, hashable string for a
    caller that keys off ``.pattern``. Such an entry's
    ``.synthesized_pattern`` is ``True`` -- see that field's docstring for
    the write-path contract this creates.

    Args:
        raw_list: The raw ``permissions.allow``/``deny``/``ask`` value from a
            config layer or file. Tolerated even when not a ``list`` (treated
            as empty).
        is_native: Passed through to :func:`normalize_entry` (gates
            structured-entry recognition).

    Returns:
        One :class:`RuleEntry` per input element, in original order --
        always the same length as ``raw_list`` (when it is a ``list``).
    """
    if not isinstance(raw_list, list):
        return ()

    result = []
    for raw in raw_list:
        entry, _issues = normalize_entry(raw, is_native=is_native)
        if entry is None:
            entry = RuleEntry(
                pattern=repr(raw),
                metadata=MappingProxyType({}),
                raw=raw,
                synthesized_pattern=True,
            )
        result.append(entry)
    return tuple(result)


def real_patterns(entries: Sequence[Union[str, "RuleEntry"]]) -> List[str]:
    """
    Extract each entry's real, matchable pattern -- never a synthesized one.

    The single chokepoint every write-path caller MUST use to build
    :func:`~toolguard.config_write_guard.verified_write_config`'s
    ``expected_patterns`` out of entries that may include
    :func:`normalize_entries_preserving`'s synthesized fallback entries
    (``.synthesized_pattern`` True -- see that field's docstring for the
    permanent write-block that results otherwise). Such an entry is silently
    dropped here rather than contributing its ``repr(raw)`` stand-in. No real
    pattern is ever dropped, so the guard's own safety net -- refusing a
    write that would truly lose a rule -- is unaffected.

    Args:
        entries: A mix of pattern ``str`` (always kept) and
            :class:`RuleEntry` (kept unless ``synthesized_pattern`` is
            ``True``).

    Returns:
        The real pattern strings, in ``entries``' original order, with every
        synthesized-pattern entry omitted.
    """
    result: List[str] = []
    for entry in entries:
        if isinstance(entry, RuleEntry):
            if entry.synthesized_pattern:
                continue
            result.append(entry.pattern)
        else:
            result.append(entry)
    return result


@dataclass(frozen=True)
class MergeConflict:
    """
    A metadata contradiction found by :func:`merge_entries` between two or
    more structured entries that share the same ``.pattern``.

    A conflict is raised per contended metadata KEY, not per entry pair: if
    three entries share a pattern and two of them disagree on one key, that
    is a single :class:`MergeConflict` naming every entry carrying the key,
    so a caller sees the full picture in one record.

    Attributes:
        pattern: The ``.pattern`` the conflicting entries have in common.
        key: The metadata key whose value differs across entries.
        entries: Every entry in the DEDUPED pattern group that carries
            ``key``, in their original relative order -- exact duplicates
            are collapsed before the comparison, so three entries carrying
            ``key`` can produce a conflict naming two.
    """

    pattern: str
    key: str
    entries: Tuple["RuleEntry", ...]


@dataclass(frozen=True)
class MergeOutcome:
    """
    Result of :func:`merge_entries`: the consolidated entries plus any
    metadata conflicts found along the way.

    Attributes:
        entries: The merged result. One entry per pattern group, UNLESS that
            group hit a :class:`MergeConflict`, in which case every
            structured entry from that group is preserved separately instead
            of being collapsed (see :func:`merge_entries` case 3). Order is
            first-appearance order of pattern groups, and within a
            conflicted group, first-appearance order of that group's
            entries.
        conflicts: Structured conflict records, one per (pattern, key) pair
            with contradictory values across the entries sharing that
            pattern. Empty when no group had a contradiction.
    """

    entries: Tuple["RuleEntry", ...]
    conflicts: Tuple[MergeConflict, ...]


def merge_entries(entries: Sequence["RuleEntry"]) -> MergeOutcome:
    """
    Consolidate a sequence of :class:`RuleEntry` sharing the same pattern.

    This is the third, deliberately DIFFERENT comparison semantics on
    ``RuleEntry`` (see :meth:`RuleEntry.identity`'s docstring for how the
    three relate): entries are grouped by ``.pattern`` (comparison #1 --
    "same RULE"), and within each group:

    1. **Bare string vs. structured -> drop the bare string.** The structured
       entry is clearly the intended rule; the bare one adds nothing. This is
       a clean win, NOT a conflict and NOT reported. "Structured" throughout
       means "carries metadata" (``bool(entry.metadata)``), not
       :attr:`RuleEntry.is_structured`.
    2. **Multiple structured entries with COMPATIBLE metadata -> union
       merge.** "Compatible" means: for every key present in more than one
       entry, all its values are equal; remaining keys are disjoint. The
       result is a single entry whose metadata is the union of all key/value
       pairs (each key appearing once). No user interaction, no conflict
       reported.
    3. **Multiple structured entries with a CONTRADICTION (same key,
       different values) -> keep them separate AND alert.** No winner is
       picked, nothing is merged or silently dropped: every structured entry
       in that group is preserved as-is in the output, and one
       :class:`MergeConflict` is appended per contended key.

    Before any of the above, exact duplicates (identical ``.identity()`` --
    comparison #2, "literally the same entry, enrichment included") within a
    group are collapsed as an internal fast path, so a repeated bare or
    repeated identical-structured entry never inflates a group or produces a
    spurious "conflict" against itself.

    Entries with DIFFERENT patterns are independent groups and are never
    merged together, regardless of their metadata.

    Args:
        entries: The entries to consolidate, in their original order.

    Returns:
        A :class:`MergeOutcome` with the merged entries and any conflicts
        found. Both fields preserve first-appearance order of pattern groups
        and, within a group, first-appearance order of its entries. Empty
        input returns an empty outcome.
    """
    if not entries:
        return MergeOutcome(entries=(), conflicts=())

    # Group by ".pattern", preserving first-appearance order of both the
    # groups and the entries within each group.
    groups: Dict[str, List["RuleEntry"]] = {}
    group_order: List[str] = []
    for entry in entries:
        if entry.pattern not in groups:
            groups[entry.pattern] = []
            group_order.append(entry.pattern)
        groups[entry.pattern].append(entry)

    merged_entries: List["RuleEntry"] = []
    conflicts: List[MergeConflict] = []

    for pattern in group_order:
        group = groups[pattern]

        # Fast path: collapse literally identical entries, so a repeated bare
        # or repeated identical-structured entry doesn't inflate the group or
        # fabricate a conflict against itself.
        deduped: List["RuleEntry"] = []
        seen_identities = set()
        for entry in group:
            ident = entry.identity()
            if ident in seen_identities:
                continue
            seen_identities.add(ident)
            deduped.append(entry)

        # Metadata presence, not `is_structured` (which only reflects whether
        # `raw` is a dict): a case-2 union-merge result records no `raw` yet
        # carries real metadata, and must still count as structured if a
        # later pass merges it again.
        structured = [e for e in deduped if e.metadata]

        if not structured:
            # Only metadata-free entries (bare strings, or a structured
            # `{match: "..."}` entry with no other keys). Every such entry
            # has empty metadata, so identical .pattern => identical
            # identity() => the dedup pass above already collapsed this to
            # exactly one.
            merged_entries.append(deduped[0])
            continue

        if len(structured) == 1:
            # Case 1 (bare + one structured -> drop the bare): whether or
            # not a bare entry is also present in `deduped`, only the sole
            # structured entry is kept.
            merged_entries.append(structured[0])
            continue

        # Two or more structured entries share this pattern: any bare entry
        # is dropped the same way (case 1), and we decide between case 2
        # (union merge) and case 3 (conflict) by comparing every key that
        # appears in more than one structured entry.
        merged_metadata: Dict[str, object] = {}
        conflicting_keys: List[str] = []
        for entry in structured:
            for key, value in entry.metadata.items():
                if key not in merged_metadata:
                    merged_metadata[key] = value
                    continue
                if key in conflicting_keys:
                    continue
                if merged_metadata[key] != value:
                    conflicting_keys.append(key)

        if conflicting_keys:
            # Case 3: contradiction -- keep every structured entry separate,
            # alert once per contended key.
            for key in conflicting_keys:
                involved = tuple(e for e in structured if key in e.metadata)
                conflicts.append(
                    MergeConflict(pattern=pattern, key=key, entries=involved)
                )
            merged_entries.extend(structured)
            continue

        # Case 2: compatible -- union merge into a single synthesized entry.
        # `raw` deliberately stays at `_UNSET`: a union has no single original
        # source value, and `raw=None` would wrongly record one (see `_UNSET`).
        merged_entries.append(
            RuleEntry(
                pattern=pattern,
                metadata=MappingProxyType(merged_metadata),
            )
        )

    return MergeOutcome(entries=tuple(merged_entries), conflicts=tuple(conflicts))
