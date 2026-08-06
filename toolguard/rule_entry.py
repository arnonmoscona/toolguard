"""
Structured allow/deny/ask rule entry: shape normalization and tool scoping.

TOO-19 Phase 0a, increment 1. Centralizes the parsing of a single permission
entry -- plain string or the new structured ``{match = "...", ...}`` table
form -- into one immutable :class:`RuleEntry` type, so every consumer stops
independently guessing at ``isinstance(perm, str)``.

:func:`normalize_entry` is the single chokepoint every consumer now goes
through -- :meth:`toolguard.config.Configuration.permission_layers`,
:meth:`~toolguard.config.Configuration.hard_deny`,
:meth:`~toolguard.config.Configuration.toolguard_permissions`,
:func:`toolguard.config_validation.validate_permissions`, and the write path
(``rule_sort`` / ``migrate_permissions`` / ``rule_apply``) -- replacing the
scattered ``isinstance(perm, str)`` checks that used to drop a non-string
entry silently, DENY lists included.

This module intentionally imports nothing from :mod:`toolguard` except
:mod:`toolguard.issues`, so it stays a leaf that :mod:`toolguard.config` and
:mod:`toolguard.config_validation` can both depend on without a circular
import (``config`` imports ``config_validation``, so neither could host this).
:mod:`test.unit.test_architecture` enforces that layering.

Structured entries are **single-line inline tables only**: TOML 1.0 requires an
inline table on one line, and toolguard's loader is stdlib :mod:`tomllib`. A
multi-line entry makes the whole file unparseable -- see
``toolguard.config._multiline_structured_entry_diagnostic``.
"""

import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Dict, List, Mapping, Optional, Sequence, Tuple, Union

from toolguard.issues import Issue

# The table key that carries the permission pattern in a structured entry,
# e.g. ``{match = "Bash(git *)", additionalContext = "..."}``. Not itself an
# enrichment key -- see KNOWN_ENRICHMENT_KEYS.
PATTERN_KEY = "match"

# The enrichment key carrying text to inject into Claude's context when the
# entry is the deciding match for a tool call (TOO-19 Phase 1).
ADDITIONAL_CONTEXT_KEY = "additionalContext"

# Enrichment keys this toolguard version understands. A later ticket adds an
# auto-mode flag. `match` is the pattern key (PATTERN_KEY), not an enrichment
# key, and is deliberately absent here.
# An unknown key is a WARNING, never an error -- a newer config read by an
# older toolguard must degrade, not break.
KNOWN_ENRICHMENT_KEYS = frozenset({ADDITIONAL_CONTEXT_KEY})

# Structural matcher for a ``Tool(inner)`` permission wrapper. An identifier
# made of word characters followed by a parenthesised body. Greedy ``.*``
# lets the inner body itself contain parentheses, e.g.
# ``Bash(foo(bar))`` -> ``foo(bar)``. This needs no known-tool list.
#
# Deliberately NOT ``re.DOTALL``: this is used with ``fullmatch`` to validate
# an ENTIRE pattern string is wrapper-shaped, and every wrapper-shaped
# pattern this project writes or accepts is single-line -- structured
# entries are single-line inline TOML tables (see module docstring), and a
# plain pattern string has no legitimate reason to contain an embedded
# newline either. With DOTALL, `.` also matches ``\n``, so e.g.
# ``"Bash(a)\nEvil(b)"`` would wrongly fullmatch (the greedy ``.*`` simply
# consumes through the embedded newline to the LAST ``)``) -- silently
# accepting what looks like two concatenated tool-wrapper expressions as one
# valid pattern, defeating the "strict, single tool wrapper" contract this
# regex exists to enforce. Without DOTALL, ``.`` never matches ``\n``, so
# such input correctly fails to fullmatch.
#
# Moved here, together with its two thin wrapper predicates below
# (``is_tool_wrapper``, ``_strip_tool_wrapper``), from ``toolguard.config``
# (TOO-19 Phase 0a, increment 1): ``normalize_entry`` needs the identical
# wrapper-shape check for a structured entry's ``match`` value, and this
# module must stay a leaf that ``config.py`` depends on -- not the reverse --
# so the regex and every predicate over it live here in exactly one place,
# and ``config.py`` imports and re-exports all three rather than any module
# keeping its own copy.
_TOOL_WRAPPER_RE = re.compile(r"[A-Za-z0-9_]+\((.*)\)")

# Sentinel for RuleEntry.raw's "no raw value recorded" state. MUST NOT be
# Python's `None`: a genuine source element can itself BE `None` (e.g. a
# JSON `permissions.allow` list containing a literal `null` -- TOML has no
# null, but toolguard_hook.json is a first-class supported format), and
# that value must round-trip through RuleEntry.to_source() unchanged rather
# than being treated as "nothing to re-emit, render fresh". Using `None` as
# both "unset" and "a real value" caused exactly that bug: to_source() fell
# through to rendering the STRING "None" for a `raw=None` entry instead of
# returning the value None, silently corrupting a user's config on write.
_UNSET = object()


def _strip_tool_wrapper(pattern: str) -> str:
    """
    Strip a ``Tool(...)`` wrapper from a permission pattern, if present.

    Permission patterns are authored wrapped as ``Tool(inner)`` (e.g.
    ``Bash(git *)``) but the loaders compare against the unwrapped inner pattern
    (``git *``). This is the single source of truth for that unwrapping. It is
    purely STRUCTURAL: any ``identifier(...)`` shape is stripped, so no
    hand-maintained tool list is needed and new tools require no change. The
    inner body may itself contain parentheses (``Bash(foo(bar))`` -> ``foo(bar)``).

    Returns the inner pattern when wrapped (e.g. ``'Bash(*)' -> '*'``); otherwise
    returns the pattern unchanged (already in extracted form).

    Args:
        pattern: A permission pattern, possibly wrapped in ``Tool(...)``.

    Returns:
        The pattern with any tool wrapper removed.
    """
    match = _TOOL_WRAPPER_RE.fullmatch(pattern)
    if match:
        return match.group(1)
    return pattern


def is_tool_wrapper(pattern: object) -> bool:
    """
    Report whether a permission pattern is a ``Tool(...)`` wrapper.

    Shares the single structural recogniser (``_TOOL_WRAPPER_RE``) with
    :func:`_strip_tool_wrapper`, so the wrapper shape lives in exactly one
    place. Used both by :func:`normalize_entry` (to validate a structured
    entry's ``match`` value) and by external clients (e.g.
    ``toolguard.config_divergence``) that need to recognise tool-scoped
    native permission strings without re-deriving the regex.

    Args:
        pattern: A candidate value; only a ``str`` can match.

    Returns:
        True if ``pattern`` is a string whose whole content is an
        ``identifier(...)`` tool wrapper.
    """
    return isinstance(pattern, str) and _TOOL_WRAPPER_RE.fullmatch(pattern) is not None


@dataclass(frozen=True)
class RuleEntry:
    """One allow/deny/ask entry, plain-string or structured form.

    Format-agnostic: the same type comes out of TOML, JSON, and
    synthesized-by-tooling entries, so every consumer sees one shape.
    """

    # Wrapper-INTACT, exactly as written: "Bash([regex]^git .*)".
    # Deliberately NOT stripped: permission_layers() is the ONLY consumer that
    # wants the wrapper-free body, and it strips at its own call site. Every
    # other consumer (toolguard_permissions, validate_permissions,
    # with_layer_rules_replaced, the whole rule_sort/write path) is
    # tool-agnostic and needs the wrapped form.
    pattern: str

    # Plain Mapping, NOT a tuple of flat primitives. Constraining every future
    # enrichment value to str/int/float/bool/None would permanently forbid the
    # first field that wants a list (applies_to = ["Bash", "Read"]) or a
    # sub-table, in a mechanism explicitly designed as a general extension
    # point. Hashability is recovered via identity() instead.
    # Always built as MappingProxyType(...) so "frozen" is not a lie.
    metadata: Mapping[str, object] = field(default_factory=lambda: MappingProxyType({}))

    # The exact source value this was parsed from (str, or the dict), OR
    # `_UNSET` when this entry was synthesized (constructed directly, or
    # produced by merge_entries()'s union-merge path) with no original
    # source to preserve. `_UNSET` -- NOT `None` -- is the "no raw" sentinel;
    # see its module-level docstring for why a genuine `raw=None` (a JSON
    # `null` element) must stay distinguishable from "unset". Test presence
    # via the `has_raw` property, not `raw is None`.
    # Lets the write path re-emit an UNTOUCHED entry verbatim instead of
    # re-rendering it -- this is what makes "maintenance tooling must not
    # destroy enrichment on unrelated edits" hold byte-for-byte.
    # compare=False: formatting is not identity.
    raw: object = field(default=_UNSET, compare=False, repr=False)

    # True exactly when `pattern` is a SYNTHESIZED, non-matchable stand-in
    # (``repr(raw)``) assigned by :func:`normalize_entries_preserving` for a
    # raw element that could not be normalized into a real permission
    # pattern -- e.g. a structured entry missing its ``match`` key, or a
    # JSON list element of an unsupported type (``42``, ``None``, ...). Never
    # set True for any entry constructed by :func:`normalize_entry` itself
    # (which only ever returns a real pattern, or `None`).
    #
    # This is the explicit marker a write-path caller MUST check before
    # feeding `.pattern` into `expected_patterns` for
    # :func:`~toolguard.config_write_guard.verified_write_config`'s
    # content-loss guard (TOO-19 review fix): that guard recomputes the set
    # of "present" patterns from the ACTUAL text it is about to write, using
    # only real pattern shapes (a plain string, or a structured entry's
    # `match` value) -- it can never reproduce a synthesized `repr()`
    # string. Passing a synthesized pattern as "expected" therefore always
    # looks like a dropped rule to the guard, refusing an otherwise-safe
    # write (confirmed repro: a single malformed structured entry blocked
    # every subsequent config write). Deliberately an explicit field rather
    # than re-deriving "looks synthetic" from the pattern's string shape at
    # each call site -- inferring it (e.g. "starts with a brace-like
    # `repr()` prefix") would be brittle and could itself misclassify a
    # legitimate pattern.
    #
    # compare=False, repr=False: purely a write-path bookkeeping flag, not
    # part of this entry's identity (mirrors `raw`).
    synthesized_pattern: bool = field(default=False, compare=False, repr=False)

    @property
    def stripped_pattern(self) -> str:
        """
        The wrapper-stripped form of :attr:`pattern` (see
        :func:`_strip_tool_wrapper`).

        TOO-45 R2a: the single accessor every consumer that wants the
        wrapper-free pattern now goes through, so a stripped-pattern
        collection (e.g. :class:`~toolguard.config_types.ToolPatternLayer`'s
        ``allow``/``deny``/``ask`` properties) is always a live projection
        over ``entries`` rather than a separately materialised, and
        therefore driftable, copy.

        Returns:
            ``pattern`` with any ``Tool(...)`` wrapper removed.
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

        True whenever `raw` was explicitly recorded -- including the edge
        case of a genuine `raw=None` (e.g. a parsed JSON `null` element) --
        and False only for a synthesized entry (constructed with no `raw`
        argument, or produced by merge_entries()'s union-merge path) that
        has nothing original to preserve. This is the sentinel-aware
        replacement for the naive (and buggy) `raw is None` check: use this,
        never `raw is None`, to decide "does this entry have a raw to
        re-emit".
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
        - :func:`merge_entries` (TOO-19 increment 6) defines its own
          consolidation semantics on top of both: it groups by ``.pattern``,
          then uses ``identity()`` as an internal fast path to collapse
          literal duplicates before applying its bare-vs-structured and
          union/conflict rules.

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

        ``set(entries)`` must work even when ``metadata`` holds a list value
        (e.g. ``applies_to = ["Bash", "Read"]``) -- the dataclass-generated
        ``__hash__`` would raise ``TypeError`` the moment ``metadata``
        (a ``Mapping``) or one of its values is unhashable. Hashing the
        JSON-canonicalized identity instead sidesteps that entirely.
        """
        return hash(self.identity())

    def to_source(self) -> object:
        """
        The value to write back into a config file (TOML table / JSON object).

        Returns ``raw`` verbatim for an unmodified entry -- the round-trip
        guarantee. This includes a genuine ``raw=None`` (e.g. a parsed JSON
        ``null`` element): it is returned as ``None``, not re-rendered, since
        it *was* recorded (``has_raw`` is True). Only truly synthesized/edited
        entries (``has_raw`` is False -- no ``raw`` was ever recorded) are
        re-rendered, as a bare string when there is no metadata or as a
        ``{PATTERN_KEY: pattern, **metadata}`` table otherwise.

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
    """
    Build one of :func:`normalize_entry`'s ``(None, (Issue,))`` rejection returns.

    Every branch of :func:`normalize_entry` that decides ``raw`` cannot be
    normalized returns this exact shape -- ``None`` paired with a single
    :class:`Issue` in a 1-tuple. Extracted once (TOO-19 review fix, pyscn
    clone flag) so those near-identical blocks read as "reject because ...",
    not several structurally-cloned literal tuples.

    Args:
        level: The Issue's severity (``"warning"`` or ``"error"``).
        message: The Issue's human-readable explanation.
        corrective_steps: The Issue's suggested fix.

    Returns:
        ``(None, (Issue(level=level, message=message,
        corrective_steps=corrective_steps),))``.
    """
    return None, (
        Issue(level=level, message=message, corrective_steps=corrective_steps),
    )


def normalize_entry(
    raw: object, is_native: bool
) -> Tuple[Optional["RuleEntry"], Tuple[Issue, ...]]:
    """
    Normalize one allow/deny/ask config element into a :class:`RuleEntry`.

    Shape normalization ONLY -- tool-agnostic and wrapper-intact (the
    returned ``pattern``, when present, is never stripped of its
    ``Tool(...)`` wrapper). This is the single chokepoint intended to replace
    every scattered ``isinstance(perm, str)`` check across the codebase.
    Unlike those checks, an unusable element is never silently dropped: it
    always comes back as ``(None, issues)`` with at least one issue
    explaining why.

    Behaviour:

    - A plain, non-empty ``str`` always normalizes to a bare
      ``RuleEntry(pattern=raw, metadata={}, raw=raw)`` with no issues, even
      if it is not ``Tool(...)``-wrapped. Wrapper-shape validation applies
      to STRUCTURED entries only: today, a plain string that isn't
      ``Tool(...)``-shaped is silently filtered out later by the
      tool-prefix scan in ``permission_layers()``, not reported as an
      error, and this function preserves that -- changing it would flood
      existing configs with brand-new errors for old, already-accepted
      config shapes. Structured entries are new syntax with no back-compat
      surface, so strict wrapper validation there is free.
    - An empty string is the ONE exception to the "plain strings are not
      wrapper-validated" rule above, and normalizes to ``(None, issues)``
      with a ``warning`` (not ``error``) :class:`Issue`. It is special-cased
      rather than folded into the general non-wrapper-shaped case because it
      is unambiguously a mistake -- there is no non-empty tool name an empty
      string could ever be missing -- whereas a merely unwrapped string
      (``"not-wrapped-at-all"``) might be a deliberately loose pattern this
      function has no basis to second-guess. ``warning`` (rather than
      ``error``) keeps this from being a louder-than-today diagnostic: an
      empty entry already loads silently today (``"".startswith("Bash(")``
      is False, so ``permission_layers()`` filters it out unnoticed), and
      this function's job is to stop SILENT drops, not to newly reject
      config that previously loaded without complaint.
    - A ``dict`` with a valid (non-empty, wrapper-shaped, string)
      :data:`PATTERN_KEY` value normalizes to a :class:`RuleEntry` whose
      ``metadata`` holds every other key. Keys outside
      :data:`KNOWN_ENRICHMENT_KEYS` do not block normalization but each
      produce a ``warning`` :class:`Issue` (typo protection / forward
      compatibility -- a newer config read by an older toolguard degrades,
      it does not break).
    - A ``dict`` missing :data:`PATTERN_KEY`, or whose value is not a
      non-empty, wrapper-shaped string, normalizes to ``(None, issues)``
      with an ``error`` :class:`Issue`. Unlike the plain-string case, this
      IS held to wrapper-shape validation, since a structured entry is new
      syntax with no back-compat surface (see above).
    - A ``dict`` is entirely rejected when ``is_native`` is True: structured
      entries are a toolguard extension and are never interpreted from a
      native Claude ``settings.json`` layer (mirrors the existing
      ``if layer.is_native: continue`` guards elsewhere in this codebase).
      This normalizes to ``(None, issues)`` with a ``warning`` Issue -- a
      native file with a stray table entry is unusual but not an error in
      itself. A plain string under ``is_native=True`` is unaffected and
      parses exactly as it would with ``is_native=False``.
    - Anything else (``int``, ``None``, ``list``, ``bool``, ...) normalizes
      to ``(None, issues)`` with an ``error`` Issue.

    Args:
        raw: One element from a config's ``permissions.allow`` /ask`` /
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
    exactly backwards for a `deny`. The rule keeps working; only the
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
    ends with ``")"``, mirroring EXACTLY the equivalent inline filter in
    ``Configuration.permission_layers()`` (``perm.startswith(prefix) and
    perm.endswith(")")``) so that wiring this function in there in a later
    increment is a pure refactor with no behaviour change.

    Does NOT strip the ``Tool(...)`` wrapper -- stripping happens only at
    ``permission_layers()``'s own call site, its sole consumer that wants
    the unwrapped form.

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
    Normalize a raw allow/deny/ask list for a WRITE-PATH caller, never dropping.

    :func:`normalize_entry`'s existing direct callers all sit on the MATCH
    path (``permission_layers``, ``hard_deny``, ``validate_permissions``,
    ``with_layer_rules_replaced``): each drops an element that fails to
    normalize, which is correct there -- an unusable entry cannot govern
    anything, so it is simply absent from the pool being matched against.

    A WRITE-PATH caller (TOO-19 Phase 0a increment 8: migration, ``rule_apply``,
    ``Configuration.toolguard_permissions``) is different: it opened a config
    file it is going to write back out, in whole or in part, so an element it
    cannot parse must still round-trip -- dropping it would silently delete
    part of the user's file. This is the single chokepoint for that
    "never lose an element" contract: a raw element that fails to normalize
    is wrapped as a :class:`RuleEntry` around the RAW value unchanged (so
    :meth:`RuleEntry.to_source` reproduces it verbatim), with a synthesized
    ``pattern`` of ``repr(raw)`` -- deliberately NOT a real ``Tool(...)``
    pattern, so it can never collide with (dedupe against, or be mistaken
    for) a legitimately normalized entry, while still being a deterministic,
    sortable, hashable string for callers that key off ``.pattern``. Such an
    entry's ``.synthesized_pattern`` is set ``True`` -- see that field's
    docstring for why a write-path caller building ``expected_patterns`` for
    :func:`~toolguard.config_write_guard.verified_write_config` MUST exclude
    these (TOO-19 review fix: a synthesized pattern can never appear in text
    the guard re-parses from disk, so passing one through wrongly looks like
    a dropped rule and refuses an otherwise-safe write).

    Args:
        raw_list: The raw ``permissions.allow``/``deny``/``ask`` value from a
            config layer or file. Tolerated even when not a ``list`` (treated
            as empty), matching the existing non-list tolerance elsewhere in
            this codebase.
        is_native: Passed through to :func:`normalize_entry` (gates
            structured-entry recognition).

    Returns:
        One :class:`RuleEntry` per input element, in original order --
        always the same length as ``raw_list`` (when it is a ``list``),
        unlike :func:`normalize_entry`'s direct match-path callers.
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
    Extract the real, matchable pattern from each entry -- for
    ``expected_patterns``, never a synthesized one.

    The single chokepoint every write-path caller MUST use to build
    :func:`~toolguard.config_write_guard.verified_write_config`'s
    ``expected_patterns`` argument out of a list of entries that may include
    output from :func:`normalize_entries_preserving` (TOO-19 review fix). That
    function's synthesized fallback entries (``.synthesized_pattern`` is
    ``True``, see that field's docstring) are silently DROPPED here rather
    than contributing their ``repr(raw)`` stand-in: the content-loss guard
    recomputes "present" patterns from the real text it is about to write,
    which can never contain a synthesized ``repr()`` string, so passing one
    through as "expected" always looks like a dropped rule and wrongly
    refuses an otherwise-safe write (confirmed repro: a single malformed
    structured entry blocked every subsequent config write). A genuinely
    droppable, real pattern is NEVER filtered here, so the guard's actual
    safety net -- refusing a write that would truly lose a rule -- is
    unaffected.

    Args:
        entries: A mix of pattern ``str`` (legacy contract; always kept) and
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
    is a single :class:`MergeConflict` naming all the entries that carry the
    key (not just the first disagreeing pair), so a caller sees the full
    picture in one record.

    Attributes:
        pattern: The shared ``.pattern`` (comparison #1 -- "same RULE") the
            conflicting entries have in common.
        key: The metadata key whose value differs across entries.
        entries: Every entry in the pattern group that carries ``key``, in
            their original relative order.
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
       a clean win, NOT a conflict and NOT reported. "Structured" here means
       "carries metadata" (``bool(entry.metadata)``), not
       ``entry.is_structured`` -- see the inline comment in the
       implementation for why that distinction matters for chained calls.
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

    # Group by ".pattern" (comparison #1 -- "is this the same RULE"),
    # preserving first-appearance order of both groups and entries within
    # each group.
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

        # Fast path: collapse entries that are literally identical
        # (comparison #2 -- "identity()", enrichment included), so a
        # repeated bare or repeated identical-structured entry doesn't
        # inflate the group or fabricate a conflict against itself.
        deduped: List["RuleEntry"] = []
        seen_identities = set()
        for entry in group:
            ident = entry.identity()
            if ident in seen_identities:
                continue
            seen_identities.add(ident)
            deduped.append(entry)

        # "Structured" here means "carries metadata" (`bool(entry.metadata)`),
        # NOT `entry.is_structured` (which reflects whether `raw` happens to
        # be a `dict`, purely a round-trip-source concern -- see
        # RuleEntry.to_source()). Using metadata presence instead is what
        # keeps this self-consistent across repeated merge_entries() passes:
        # a case-2 union-merge result is itself constructed with no `raw`
        # recorded (so `is_structured`/`has_raw` would be False) but carries
        # real metadata, and must still be treated as "structured" if merged
        # again later.
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
        # `raw` is deliberately left at its default (`_UNSET`, i.e.
        # `has_raw` is False): there is no single original source value for
        # a union of two or more entries, so nothing should be preserved
        # verbatim -- to_source() must re-render this one fresh. Passing
        # `raw=None` here would be wrong: it would record a genuine `None`
        # as the "original" source and to_source() would then round-trip
        # that `None` instead of rendering the merged metadata.
        merged_entries.append(
            RuleEntry(
                pattern=pattern,
                metadata=MappingProxyType(merged_metadata),
            )
        )

    return MergeOutcome(entries=tuple(merged_entries), conflicts=tuple(conflicts))
