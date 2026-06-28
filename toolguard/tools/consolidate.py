"""
Config consolidation proposals for toolguard permission rules.

Two complementary consolidation families are provided:

1. **Family 1 -- Literal-alternation consolidation.**
   Within a tool's allow list and a single config layer, groups of >= 2
   DEFAULT ``:*``/``**`` (prefix) patterns that are token-identical except
   exactly ONE token slot (which varies over literal, wildcard-free values) are
   collapsed into a single ``[regex]`` rule.  The regex is anchored with ``^``
   and mirrors DEFAULT ``cmd:*`` PREFIX semantics exactly (no trailing word
   boundary), so it is EQUIVALENCE-PRESERVING rather than silently tightening.
   Strict acceptance requires that the consolidation changes NO decision: every
   probe -- and, when a corpus is supplied, every corpus entry -- must have an
   identical verdict before and after.

2. **Family 2 -- Static subsumption elimination.**
   Within a tool's allow list and a single config layer, a DEFAULT pattern
   whose static match-set is a provable SUBSET of another pattern in the same
   list is proposed for removal.  Only DEFAULT ``:*`` patterns are considered
   and the proof is purely structural (word/path-boundary prefix analysis),
   making this corpus-independent.  When a corpus is supplied, replay provides
   a secondary guard.

Accepted proposals carry probe-verified, replay-confirmed evidence; any
candidate that cannot be proven safe is SILENTLY excluded from the returned
list (not flagged as a soft finding -- that is deferred to a later slice).

Safety note (equivalence + the alembic landmine)
------------------------------------------------
Strict family-1 is accepted only when it changes NO decision -- neither
broadening NOR tightening.  This is what prevents the alembic landmine: a
consolidation that silently widened an ``ask``/``deny`` command to ``allow`` (or
quietly narrowed a previously-allowed command) would change at least one probe
or corpus decision and is rejected before emission.  By construction the
generated regex is a subset-or-equal of the union of the original DEFAULT prefix
patterns, so it can never broaden; the no-changed-decision gate additionally
guarantees it never tightens.  See :func:`_check_family1_safe`.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from toolguard.config import Configuration, Provenance
from toolguard.patterns import PatternType, parse_pattern
from toolguard.tools.config_access import per_layer_rules, with_layer_allow_replaced
from toolguard.tools.decision import decide
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.replay import replay


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConsolidationProposal:
    """
    A verified proposal to consolidate or remove one or more permission rules.

    Each instance represents a single, probe-verified, replay-confirmed change
    to a tool's allow list within one config layer.  The proposal is GENERAL
    enough to represent a future remediation EDIT (remove + replace), not only
    consolidation.

    Attributes:
        kind: ``'literal-alternation'`` or ``'static-subsumption'``.
        tool: Tool name the proposal applies to (e.g. ``'Bash'``).
        list_type: Which permission list is being modified.  Always ``'allow'``
            in this slice.
        layer_provenance: The :class:`~toolguard.config.Provenance` identifying
            the config layer that contains the patterns being changed.
        removed_patterns: Wrapper-free pattern bodies being removed.
        added_pattern: Wrapper-free body of the replacement rule, or ``None``
            for pure-drop proposals (static-subsumption where the larger rule
            already covers everything).
        rationale: Human-readable explanation of WHY the consolidation is
            valid (e.g. which token varies, which rule subsumes which).
        replay_summary: Short evidence string summarising the probe/replay
            outcome (e.g. "N positive probes pass; corpus replay: 0 broadened").
    """

    kind: str
    tool: str
    list_type: str
    layer_provenance: Provenance
    removed_patterns: Tuple[str, ...]
    added_pattern: Optional[str]
    rationale: str
    replay_summary: str


# ---------------------------------------------------------------------------
# Internal helpers -- pattern parsing
# ---------------------------------------------------------------------------


def _is_literal_token(token: str) -> bool:
    """
    Return True when ``token`` contains no fnmatch wildcard characters.

    Wildcard characters (``*``, ``?``, ``[``, ``]``) make a token non-literal
    and unsuitable for direct inclusion in a regex alternation group.  All
    other characters are considered safe for literal matching.

    Args:
        token: A single whitespace-free token from a DEFAULT pattern body.

    Returns:
        True when the token is free of ``*``, ``?``, ``[``, and ``]``.
    """
    return not any(c in token for c in ("*", "?", "[", "]"))


def _split_default_body(body: str) -> Tuple[List[str], str]:
    """
    Split a DEFAULT pattern body into ``(cmd_tokens, args_part)``.

    Splits on the FIRST ``:`` in ``body``.  The left side is stripped and
    tokenised on whitespace; the right side is stripped and returned as-is.
    If no ``:`` is present, ``args_part`` is the empty string.

    Args:
        body: Wrapper-free DEFAULT pattern body (e.g. ``'git diff:*'``).

    Returns:
        Tuple of ``(cmd_tokens, args_part)`` where ``cmd_tokens`` is a list of
        whitespace-split tokens from the command portion and ``args_part`` is
        the args portion (e.g. ``'*'``).
    """
    if ":" in body:
        colon_idx = body.index(":")
        cmd_part = body[:colon_idx].strip()
        args_part = body[colon_idx + 1 :].strip()
    else:
        cmd_part = body.strip()
        args_part = ""
    return cmd_part.split(), args_part


# ---------------------------------------------------------------------------
# Internal helpers -- regex construction
# ---------------------------------------------------------------------------


def _build_alternation_regex(
    prefix_tokens: List[str],
    varying_tokens: List[str],
    suffix_tokens: List[str],
) -> str:
    """
    Build a ``[regex]``-prefixed consolidated pattern for a literal-alternation group.

    The resulting pattern is anchored with ``^`` and has NO trailing word
    boundary, so it mirrors DEFAULT ``cmd:*`` PREFIX semantics exactly (e.g.
    ``^git (diff|status)`` matches ``git diff``, ``git diff --stat`` AND
    ``git difftool`` -- the same set as the original ``git diff:*``).  Adding a
    ``\\b`` here would silently TIGHTEN (drop ``git difftool``), which strict
    family-1 must not do.  All tokens are escaped with :func:`re.escape` before
    insertion.

    Args:
        prefix_tokens: Cmd tokens before the varying position (may be empty).
        varying_tokens: The distinct literal tokens at the varying position,
            sorted for determinism.
        suffix_tokens: Cmd tokens after the varying position (may be empty).

    Returns:
        A ``[regex]``-prefixed pattern body ready for insertion into the allow
        list (e.g. ``'[regex]^git (diff|flake8|status)'``).
    """
    escaped_prefix = " ".join(re.escape(t) for t in prefix_tokens)
    escaped_suffix = " ".join(re.escape(t) for t in suffix_tokens)
    alternation = "(" + "|".join(re.escape(t) for t in sorted(varying_tokens)) + ")"

    parts: List[str] = []
    if escaped_prefix:
        parts.append(escaped_prefix)
    parts.append(alternation)
    if escaped_suffix:
        parts.append(escaped_suffix)

    cmd_regex = " ".join(parts)
    return f"[regex]^{cmd_regex}"


# ---------------------------------------------------------------------------
# Internal helpers -- static subsumption check
# ---------------------------------------------------------------------------


def _static_prefix_of(large_cmd: str, small_cmd: str) -> bool:
    """
    Return True when ``large_cmd`` is a provable structural prefix of ``small_cmd``.

    The check is conservative: we only claim subsumption when ``large_cmd`` is
    a word-level or path-level prefix of ``small_cmd``.  Specifically:

    - Equality: ``small_cmd == large_cmd``.
    - Space-separated word prefix: ``small_cmd.startswith(large_cmd + " ")``.
    - Path-separator prefix: ``small_cmd.startswith(large_cmd + "/")``.
    - Trailing-separator in large: when ``large_cmd`` already ends with ``/``
      or `` ``, a character-level prefix check is used.

    The trailing-separator case handles patterns like ``mkdir -p /tmp/:*`` (large)
    vs ``mkdir -p /tmp/claude-code:*`` (small): ``large_cmd = "mkdir -p /tmp/"``
    ends with ``/``, so ``small_cmd.startswith("mkdir -p /tmp/")`` is enough
    proof.

    Args:
        large_cmd: The command portion (before ``:``) of the larger pattern.
        small_cmd: The command portion of the potentially-subsumed pattern.

    Returns:
        True when ``small_cmd:*`` match-set is structurally proven to be
        a subset of ``large_cmd:*``'s match-set.
    """
    if small_cmd == large_cmd:
        return True
    # Word-level or path-level boundary
    for sep in (" ", "/"):
        if small_cmd.startswith(large_cmd + sep):
            return True
    # large_cmd already ends with a separator (e.g. "mkdir -p /tmp/")
    if large_cmd.endswith(("/", " ")) and small_cmd.startswith(large_cmd):
        return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers -- probe generation and safety check
# ---------------------------------------------------------------------------

# Synthetic probe token that is unlikely to appear in any real pattern.
_PROBE_NEGATIVE_TOKEN = "__toolguard_probe_absent__"


def _generate_positive_probes(
    parsed_group: List[Tuple[List[str], str, int, List[str], List[str]]],
) -> List[str]:
    """
    Generate positive probe commands for a family-1 alternation group.

    For each member of the group, synthesises two probe commands:
    - The bare command (cmd tokens joined, without args).
    - The command with a generic trailing argument ``--x``.

    These probes must be ``allow`` under both the original and consolidated
    configs to confirm the consolidation does not tighten anything.

    Args:
        parsed_group: List of ``(cmd_tokens, args, pos, prefix_tokens, suffix_tokens)``
            tuples for each group member.

    Returns:
        List of probe command strings.
    """
    probes: List[str] = []
    for cmd_tokens, _args, _pos, _prefix, _suffix in parsed_group:
        bare = " ".join(cmd_tokens)
        probes.append(bare)
        probes.append(bare + " --x")
    return probes


def _generate_negative_probes(
    prefix_tokens: List[str],
    varying_tokens: List[str],
    suffix_tokens: List[str],
) -> List[str]:
    """
    Generate negative probe commands for a family-1 alternation group.

    Uses a synthetic token guaranteed not to be in ``varying_tokens`` to
    construct a near-miss command.  A near-miss should NOT be allowed by
    either the original patterns or the consolidated regex; if the consolidated
    regex matches it (but the originals did not), broadening is detected.

    Args:
        prefix_tokens: Common prefix tokens before the alternation.
        varying_tokens: The actual varying tokens in the group.
        suffix_tokens: Common suffix tokens after the alternation.

    Returns:
        List of probe command strings (near-miss commands).
    """
    token = _PROBE_NEGATIVE_TOKEN
    cmd_parts = prefix_tokens + [token] + suffix_tokens
    bare = " ".join(cmd_parts)
    return [bare, bare + " --x"]


def _generate_extension_probes(
    parsed_group: List[Tuple[List[str], str, int, List[str], List[str]]],
) -> List[str]:
    """
    Generate prefix-extension near-miss probes for a family-1 group.

    For each group member, appends literal characters to the bare command with
    NO separating space (e.g. ``git diff`` -> ``git diffx`` and
    ``git difftool``).  Under DEFAULT ``cmd:*`` PREFIX semantics these share the
    member's verdict, so an equivalence-preserving consolidated rule must agree
    on them.  They are the probes that expose BOTH silent tightening (a too-strict
    word boundary that would drop ``git difftool``) and exact-vs-prefix widening
    (a no-colon exact pattern consolidated into an over-broad prefix regex).

    Args:
        parsed_group: List of ``(cmd_tokens, args, pos, prefix_tokens, suffix_tokens)``
            tuples for each group member.

    Returns:
        List of probe command strings.
    """
    probes: List[str] = []
    for cmd_tokens, _args, _pos, _prefix, _suffix in parsed_group:
        bare = " ".join(cmd_tokens)
        probes.append(bare + "x")
        probes.append(bare + "tool")
    return probes


def _check_family1_safe(
    config: Configuration,
    tool: str,
    provenance: Provenance,
    original_patterns: List[str],
    consolidated_body: str,
    prefix_tokens: List[str],
    varying_tokens: List[str],
    suffix_tokens: List[str],
    corpus: Optional[List[LogEntry]],
) -> Tuple[bool, str]:
    """
    Verify that replacing ``original_patterns`` with ``consolidated_body`` is
    EQUIVALENCE-PRESERVING (changes no decision).

    Strict family-1 acceptance requires that the consolidation neither broadens
    NOR tightens any decision:

    1. Every probe command has an IDENTICAL verdict under the original config and
       the consolidated config.  The probe set is: the literal member commands
       (with and without a generic trailing arg), prefix-extension near-misses
       (member command plus trailing characters with no separating space, e.g.
       ``git diff`` -> ``git difftool``), and a synthetic absent-token near-miss.
       The extension probes are what expose a too-strict boundary (silent
       tightening) or an exact-vs-prefix widening.
    2. When ``corpus`` is supplied, ``replay`` reports ZERO broadened AND ZERO
       tightened entries.

    Args:
        config: Original configuration.
        tool: Tool name.
        provenance: Layer provenance for the target layer.
        original_patterns: Wrapper-free bodies of the patterns being replaced.
        consolidated_body: Wrapper-free body of the proposed consolidated rule.
        prefix_tokens: Common prefix tokens before the varying position.
        varying_tokens: The varying tokens (one per group member).
        suffix_tokens: Common suffix tokens after the varying position.
        corpus: Optional harvested command corpus for historical replay check.

    Returns:
        Tuple of ``(passed, evidence_string)``.  ``passed`` is True ONLY when no
        probe and no corpus entry changes verdict; ``evidence_string`` summarises
        what was checked.
    """
    # Build config B: remove originals, add consolidated rule.
    config_b = with_layer_allow_replaced(
        config, tool, provenance, set(original_patterns), [consolidated_body]
    )

    # Parse parsed_group from original_patterns for probe generation.
    parsed_group: List[Tuple[List[str], str, int, List[str], List[str]]] = []
    pos = len(prefix_tokens)
    for pat in original_patterns:
        ptype, body = parse_pattern(pat, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args = _split_default_body(body)
        parsed_group.append((cmd_tokens, args, pos, prefix_tokens, suffix_tokens))

    # Full probe set: positive members, prefix-extension near-misses, and the
    # synthetic absent-token negative probe.  Strict family-1 requires that the
    # verdict is UNCHANGED for every one of them.
    probes = (
        _generate_positive_probes(parsed_group)
        + _generate_extension_probes(parsed_group)
        + _generate_negative_probes(prefix_tokens, varying_tokens, suffix_tokens)
    )

    changed = 0
    for cmd in probes:
        if decide(config, tool, cmd).verdict != decide(config_b, tool, cmd).verdict:
            changed += 1
    if changed:
        return False, f"probe decision changes: {changed}/{len(probes)} (not equivalence-preserving)"

    # --- Corpus replay: require zero changed decisions (no broaden, no tighten) ---
    if corpus:
        diff = replay(corpus, config, config_b)
        if diff.broadened_count or diff.tightened_count:
            return False, (
                f"corpus replay changed decisions: {diff.broadened_count} broadened, "
                f"{diff.tightened_count} tightened"
            )
        evidence = (
            f"{len(probes)} probes unchanged; "
            f"corpus replay {len(corpus)} entries, 0 changed"
        )
    else:
        evidence = f"{len(probes)} probes unchanged; no corpus"

    return True, evidence


# ---------------------------------------------------------------------------
# Family 1: Literal-alternation consolidation
# ---------------------------------------------------------------------------


def _find_literal_alternations(
    config: Configuration,
    tool: str,
    allow_patterns: Tuple[str, ...],
    provenance: Provenance,
    corpus: Optional[List[LogEntry]],
) -> List[ConsolidationProposal]:
    """
    Find literal-alternation consolidation opportunities in ``allow_patterns``.

    Groups DEFAULT ``:*`` patterns that are token-identical except exactly ONE
    token slot (varying over literal, wildcard-free values).  Each group of
    >= 2 such patterns is a candidate; the candidate is emitted as a proposal
    only when the strict probe-equivalence and optional corpus-replay checks
    pass.

    Args:
        config: The full configuration (for probe decisions).
        tool: Tool name.
        allow_patterns: Wrapper-free allow patterns from the target layer.
        provenance: Layer provenance (used to build config_b via Step-0 primitive).
        corpus: Optional harvested corpus for secondary replay check.

    Returns:
        List of accepted :class:`ConsolidationProposal` records.
    """
    # --- Parse all DEFAULT :* patterns ---
    # Each entry: (raw_body, cmd_tokens, args_part)
    default_entries: List[Tuple[str, List[str], str]] = []
    for raw in allow_patterns:
        ptype, body = parse_pattern(raw, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args_part = _split_default_body(body)
        if not cmd_tokens:
            continue
        # Only consolidate DEFAULT prefix forms (cmd:* / cmd:**).  No-colon EXACT
        # patterns are excluded: a plain prefix regex cannot preserve their exact
        # match semantics without end-anchoring (deferred to a later slice).
        if args_part not in ("*", "**"):
            continue
        default_entries.append((raw, cmd_tokens, args_part))

    if len(default_entries) < 2:
        return []

    # --- Group by template: (args, n_tokens, pos, other_tokens_tuple) ---
    # For each pattern and each token position, create a template key where
    # that position is the "varying slot" and all others are fixed.
    groups: Dict[Tuple, List[Tuple[str, List[str], str, int]]] = defaultdict(list)

    for raw, cmd_tokens, args_part in default_entries:
        n = len(cmd_tokens)
        for pos in range(n):
            # Include only if this token is literal (no fnmatch wildcards)
            if not _is_literal_token(cmd_tokens[pos]):
                continue
            # Template key: all positions except ``pos`` are fixed.
            others = tuple((j, cmd_tokens[j]) for j in range(n) if j != pos)
            key = (args_part, n, pos, others)
            groups[key].append((raw, cmd_tokens, args_part, pos))

    # --- Evaluate each group ---
    proposals: List[ConsolidationProposal] = []
    # Track which frozensets of raw patterns we've already emitted to avoid
    # duplicate proposals from multiple valid positions in the same pattern set.
    emitted_sets: Set[frozenset] = set()

    for (args_part, n, pos, others), members in groups.items():
        if len(members) < 2:
            continue

        raw_bodies = [m[0] for m in members]
        group_set = frozenset(raw_bodies)
        if group_set in emitted_sets:
            continue

        # All varying tokens must be literal (already guaranteed by group-key
        # construction, but double-check for robustness).
        varying_tokens = [m[1][pos] for m in members]
        if not all(_is_literal_token(t) for t in varying_tokens):
            continue
        if len(set(varying_tokens)) != len(varying_tokens):
            # Duplicate varying tokens -> exact duplicates, handled by redundancy.
            continue

        # Reconstruct prefix/suffix from the first member's cmd_tokens.
        first_cmd_tokens = members[0][1]
        prefix_tokens = first_cmd_tokens[:pos]
        suffix_tokens = first_cmd_tokens[pos + 1 :]

        # Build the consolidated [regex] pattern.
        consolidated = _build_alternation_regex(prefix_tokens, varying_tokens, suffix_tokens)

        # Safety check: probes + optional corpus replay.
        safe, evidence = _check_family1_safe(
            config,
            tool,
            provenance,
            raw_bodies,
            consolidated,
            prefix_tokens,
            varying_tokens,
            suffix_tokens,
            corpus,
        )
        if not safe:
            continue

        emitted_sets.add(group_set)
        proposals.append(
            ConsolidationProposal(
                kind="literal-alternation",
                tool=tool,
                list_type="allow",
                layer_provenance=provenance,
                removed_patterns=tuple(sorted(raw_bodies)),
                added_pattern=consolidated,
                rationale=(
                    f"Consolidated {len(raw_bodies)} patterns alternating at token "
                    f"position {pos}: {sorted(varying_tokens)}"
                ),
                replay_summary=evidence,
            )
        )

    return proposals


# ---------------------------------------------------------------------------
# Family 2: Static subsumption elimination
# ---------------------------------------------------------------------------


def _check_family2_safe(
    config: Configuration,
    tool: str,
    provenance: Provenance,
    small_body: str,
    small_cmd: str,
    corpus: Optional[List[LogEntry]],
) -> Tuple[bool, str]:
    """
    Verify that removing the subsumed pattern ``small_body`` is safe.

    Checks that positive probe commands (derived from ``small_cmd``) remain
    ``allow`` after removal, and runs an optional corpus replay.

    Args:
        config: The full original configuration.
        tool: Tool name.
        provenance: Layer provenance of the pattern being removed.
        small_body: Wrapper-free body of the pattern being proposed for removal.
        small_cmd: Command portion of ``small_body`` (before the ``:``) for
            generating positive probes.
        corpus: Optional corpus for secondary replay check.

    Returns:
        Tuple of ``(passed, evidence_string)``.
    """
    config_b = with_layer_allow_replaced(
        config, tool, provenance, {small_body}, []
    )

    # Positive probes: commands that match the small pattern and should
    # remain allowed after removal (by virtue of the larger pattern covering them).
    probes = [small_cmd, small_cmd + " --x"]
    pos_fail = 0
    for cmd in probes:
        va = decide(config, tool, cmd).verdict
        vb = decide(config_b, tool, cmd).verdict
        if va != "allow" or vb != "allow":
            pos_fail += 1

    if pos_fail:
        return False, f"positive probe failures: {pos_fail}/{len(probes)}"

    if corpus:
        diff = replay(corpus, config, config_b)
        if diff.broadened_count > 0:
            return False, f"corpus replay: {diff.broadened_count} broadened"
        evidence = (
            f"{len(probes)} positive probes pass; "
            f"corpus replay {len(corpus)} entries, 0 broadened"
        )
    else:
        evidence = f"{len(probes)} positive probes pass; no corpus"

    return True, evidence


def _find_static_subsumptions(
    config: Configuration,
    tool: str,
    allow_patterns: Tuple[str, ...],
    provenance: Provenance,
    corpus: Optional[List[LogEntry]],
) -> List[ConsolidationProposal]:
    """
    Find static subsumption elimination opportunities in ``allow_patterns``.

    For each pair of DEFAULT ``:*`` patterns in the list, checks whether one
    pattern's match-set is a STRICT structural subset of the other (using
    :func:`_static_prefix_of`).  Only conservative prefix-based proofs are
    claimed; ambiguous cases are silently skipped.

    Identical patterns (handled by redundancy detection) are excluded.

    Args:
        config: The full configuration (for probe decisions).
        tool: Tool name.
        allow_patterns: Wrapper-free allow patterns from the target layer.
        provenance: Layer provenance.
        corpus: Optional corpus for secondary replay guard.

    Returns:
        List of accepted :class:`ConsolidationProposal` records.
    """
    # Parse all DEFAULT :* patterns into (body, cmd_tokens, args_part)
    default_entries: List[Tuple[str, str, List[str], str]] = []
    for raw in allow_patterns:
        ptype, body = parse_pattern(raw, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args_part = _split_default_body(body)
        if not cmd_tokens:
            continue
        if args_part not in ("*", "**", ""):
            continue
        cmd_str = " ".join(cmd_tokens)
        default_entries.append((raw, cmd_str, cmd_tokens, args_part))

    proposals: List[ConsolidationProposal] = []
    proposed_removals: Set[str] = set()

    n = len(default_entries)
    for i in range(n):
        raw_large, large_cmd, _, _ = default_entries[i]
        for j in range(n):
            if i == j:
                continue
            raw_small, small_cmd, _, _ = default_entries[j]
            # Skip equal patterns (handled by redundancy.py).
            if large_cmd == small_cmd:
                continue
            # Skip already-proposed removals to avoid duplicate proposals.
            if raw_small in proposed_removals:
                continue
            # Structural proof: small_cmd is a proper prefix-subset of large_cmd.
            if not _static_prefix_of(large_cmd, small_cmd):
                continue

            # Safety check: removing small_body must not change any decision.
            safe, evidence = _check_family2_safe(
                config, tool, provenance, raw_small, small_cmd, corpus
            )
            if not safe:
                continue

            proposed_removals.add(raw_small)
            proposals.append(
                ConsolidationProposal(
                    kind="static-subsumption",
                    tool=tool,
                    list_type="allow",
                    layer_provenance=provenance,
                    removed_patterns=(raw_small,),
                    added_pattern=None,
                    rationale=(
                        f"'{raw_small}' is statically subsumed by '{raw_large}': "
                        f"every command matched by the former is also matched by the latter"
                    ),
                    replay_summary=evidence,
                )
            )

    return proposals


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def propose_consolidations(
    config: Configuration,
    tool: str,
    corpus: Optional[List[LogEntry]] = None,
) -> List[ConsolidationProposal]:
    """
    Return probe-verified consolidation proposals for ``tool``'s allow list.

    Scans each config layer's allow list for Family 1 (literal-alternation) and
    Family 2 (static-subsumption) opportunities.  Only STRICTLY accepted
    proposals are returned -- any candidate that fails the self-contained probe
    check or the optional corpus replay is silently excluded.

    The returned list is in a deterministic, stable order (sorted by
    ``kind``, ``layer_provenance``, and ``removed_patterns``).

    Safety properties
    -----------------
    - Family-1 proposals are EQUIVALENCE-PRESERVING: accepted only when no probe
      and no corpus decision changes (neither broadened nor tightened).  The
      generated regex is anchored with ``^`` and mirrors DEFAULT ``cmd:*`` prefix
      semantics (no trailing boundary), so by construction it is a
      subset-or-equal of the original union and the gate proves it never tightens.
    - Family-2 proposals are structurally proven safe before the probe is run.
    - The replay guard (when ``corpus`` is supplied) provides an additional
      catch for any edge-case decision change on real traffic.

    Alembic landmine avoidance
    --------------------------
    The landmine is a consolidation that silently widens an ``ask``/``deny``
    command to ``allow`` (e.g. collapsing several ``uv run alembic <sub>:*``
    allows into a bare ``uv run alembic:*`` that bypasses an ``ask`` guard).
    Strict family-1 cannot produce it: the no-changed-decision gate
    (:func:`_check_family1_safe`) rejects any candidate whose probe or corpus
    decisions differ before and after.  (Separately, patterns with different
    token counts never form a group at all, since grouping fixes all but one
    token slot -- but that is incidental structure, not the safety mechanism.)

    Args:
        config: The resolved :class:`~toolguard.config.Configuration`.
        tool: Tool name to inspect (e.g. ``'Bash'``).
        corpus: Optional harvested command corpus
            (:class:`~toolguard.tools.log_harvest.LogEntry` list) used as a
            secondary replay safety gate.  When ``None`` or empty, only the
            self-contained probe check is applied.

    Returns:
        Deterministically ordered list of :class:`ConsolidationProposal`
        records, all of which have passed probe-equivalence and (when a corpus
        is given) corpus-replay verification.
    """
    proposals: List[ConsolidationProposal] = []

    for layer in per_layer_rules(config, tool):
        allow = layer.allow  # wrapper-free tuple

        # Family 1: literal alternation
        proposals.extend(
            _find_literal_alternations(config, tool, allow, layer.provenance, corpus)
        )
        # Family 2: static subsumption
        proposals.extend(
            _find_static_subsumptions(config, tool, allow, layer.provenance, corpus)
        )

    # Stable, deterministic sort.
    proposals.sort(
        key=lambda p: (
            p.kind,
            p.layer_provenance.describe() if hasattr(p.layer_provenance, "describe") else str(p.layer_provenance),
            sorted(p.removed_patterns),
        )
    )
    return proposals
