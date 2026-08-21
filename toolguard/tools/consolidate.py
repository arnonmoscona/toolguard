"""
Consolidation proposals for toolguard permission rules.

Two families, each scoped to one tool's allow list within a single config layer:

1. **Literal-alternation.** A group of >= 2 DEFAULT ``cmd:*``/``cmd:**``
   patterns that are token-identical except one slot -- which varies over
   literal, wildcard-free values -- is collapsed into one ``[regex]`` rule.
   No-colon (exact) patterns are excluded.

2. **Static subsumption.** A pattern whose command text extends another's
   ``:*``/``:**`` prefix at a word (space) boundary is proposed for removal.
   Only a genuine ``:*``/``:**`` prefix on the wider rule covers the narrower
   one this way -- an EXACT (no-colon) wider pattern matches nothing but
   itself and is never treated as the covering rule -- and only a space
   boundary is one ``match_command`` honours; a ``/`` is not.

A family-1 candidate is emitted only when every probe -- and every corpus
entry, when a corpus is supplied -- yields the identical verdict before and
after.  Family 2 asks less: its two probes must be ``allow`` before and after,
and a corpus forbids both broadening and tightening.  Either way a failing
candidate is dropped silently.  With no corpus, neither gate can rule out a
tightening or broadening a real command would show; see
:class:`SafetyResult`.

Neither gate proves match-set equality by running match_command; each checks
only the commands it actually runs, or trusts a narrower structural argument
in family 2's case.  :func:`_check_family1_safe` and :func:`_static_prefix_of`
name the specific gaps that argument does and does not cover.

The module's other half, :func:`propose_broadening_consolidations`, is not part
of that scheme: it enumerates rewrites that DELIBERATELY admit more, gates
nothing, and attaches evidence for a human to judge.
"""

import re
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from toolguard.api import decide
from toolguard.config import Configuration, Provenance
from toolguard.patterns import PatternType, parse_pattern
from toolguard.tools.config_access import (
    LayerRules,
    per_layer_rules,
    with_layer_allow_replaced,
)
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.pattern_overlap import (
    default_prefix_tokens,
    prefixes_overlap,
    split_default_body,
)
from toolguard.tools.replay import replay


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------


class SafetyResult(Enum):
    """
    Outcome of a family-1/family-2 safety gate.

    ``UNVERIFIED`` is distinct from ``SAFE``: either no corpus was supplied at
    all, or the corpus had no entries for the tool being changed, so only
    synthetic probes ran -- the gate did not check a real command. A caller
    may still accept it (that is current policy, so a fresh install with no
    logs still gets consolidations), but it must branch on the value
    explicitly rather than treat it as an alias for ``SAFE``.
    """

    SAFE = "safe"
    UNSAFE = "unsafe"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class ConsolidationProposal:
    """
    One proposed change to a tool's allow list within one config layer.

    Attributes:
        kind: ``'literal-alternation'`` or ``'static-subsumption'``.
        tool: Tool name the proposal applies to (e.g. ``'Bash'``).
        list_type: Which permission list is modified.  Always ``'allow'``.
        layer_provenance: The :class:`~toolguard.config.Provenance` of the
            config layer holding the patterns being changed.
        removed_patterns: Wrapper-free pattern bodies being removed.
        added_pattern: Wrapper-free body of the replacement rule, or ``None``
            for a pure drop (every static-subsumption proposal).
        rationale: Human-readable explanation of why the change is claimed
            valid (which token varies, which rule subsumes which).
        replay_summary: Short evidence string summarising the probe/replay
            outcome (e.g. ``"10 probes unchanged; no corpus"``).
        verification: The :class:`SafetyResult` the gate returned alongside
            ``replay_summary``.  Defaults to ``UNVERIFIED`` so fixtures built
            without a real gate run still construct; every proposal the gates
            emit sets it explicitly.
    """

    kind: str
    tool: str
    list_type: str
    layer_provenance: Provenance
    removed_patterns: Tuple[str, ...]
    added_pattern: Optional[str]
    rationale: str
    replay_summary: str
    verification: SafetyResult = SafetyResult.UNVERIFIED


@dataclass(frozen=True)
class BroadeningProposal:
    """
    An *agent-judged* proposal to broaden a set of allow rules into one wider rule.

    A broadening DELIBERATELY admits more commands than the union of the rules
    it replaces, so it is never auto-applied: this layer only enumerates the
    candidate and attaches evidence for a human (or the maintenance skill) to
    judge.

    Attributes:
        kind: The broadening shape.  ``'prefix-broadening'`` collapses several
            ``<prefix> <sub>:*`` rules into a single ``<prefix> :*`` that admits
            any command starting with that prefix.
        tool: Tool name the proposal applies to (e.g. ``'Bash'``).
        list_type: Which permission list is modified.  Always ``'allow'`` here.
        layer_provenance: The :class:`~toolguard.config.Provenance` of the config
            layer holding the rules being broadened.
        removed_patterns: Wrapper-free bodies of the narrow rules being replaced.
        added_pattern: Wrapper-free body of the single broadened replacement rule.
        rationale: Human-readable explanation of what the broadening admits.
        newly_admitted_commands: Corpus commands for this tool whose verdict
            moves toward allow under the broadened config, from replay's
            ``broadened()`` entries.  Empty when no corpus was supplied.
        overlaps_guard_rules: Same-layer ask/deny rule bodies whose command-space
            overlaps the broadened pattern, each labelled ``"ask '<body>'"`` or
            ``"deny '<body>'"``.  The test is textual and ignores resolution
            precedence, so an entry is not by itself a punch-through: a same-layer
            deny still wins.  An ask guard may not -- allow-vs-ask ties break on
            literal-prefix length, so an ask BROADER than the broadened allow
            loses to it.  ``ask 'uv run:*'`` against a broadened
            ``uv run alembic :*`` is that case, and the ``uv run alembic``
            commands the ask used to gate become ``allow``.
        probe_admitted_surface: Synthetic near-miss commands the broadened rule
            admits and the originals did not -- breadth evidence that needs no
            corpus.
    """

    kind: str
    tool: str
    list_type: str
    layer_provenance: Provenance
    removed_patterns: Tuple[str, ...]
    added_pattern: str
    rationale: str
    newly_admitted_commands: Tuple[str, ...] = ()
    overlaps_guard_rules: Tuple[str, ...] = ()
    probe_admitted_surface: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Internal helpers -- pattern parsing
# ---------------------------------------------------------------------------


def _is_literal_token(token: str) -> bool:
    """Return True when *token* holds no fnmatch metacharacter (``*``, ``?``, ``[``, ``]``)."""
    return not any(c in token for c in ("*", "?", "[", "]"))


# ---------------------------------------------------------------------------
# Internal helpers -- regex construction
# ---------------------------------------------------------------------------


#: Closes a consolidated regex on a token boundary: the next character must be
#: whitespace or end-of-string, matching DEFAULT ``cmd:*`` prefix semantics.
_TOKEN_BOUNDARY_LOOKAHEAD = r"(?=\s|$)"


def _build_alternation_regex(
    prefix_tokens: List[str],
    varying_tokens: List[str],
    suffix_tokens: List[str],
) -> str:
    """
    Build the ``[regex]`` body for a literal-alternation group.

    Anchored with ``^`` and closed with a ``(?=\\s|$)`` lookahead, so the
    consolidated rule ends on a token boundary exactly as the DEFAULT ``cmd:*``
    patterns it replaces do -- ``git diff:*`` matches ``git diff --stat`` but
    not ``git difftool``. A trailing ``\\b`` would be too loose here: it holds
    before a ``-``, and so would admit ``git diff-index``.

    Args:
        prefix_tokens: Cmd tokens before the varying position (may be empty).
        varying_tokens: The distinct literal tokens at the varying position;
            sorted here, so the output does not depend on member order.
        suffix_tokens: Cmd tokens after the varying position (may be empty).

    Returns:
        A ``[regex]``-prefixed pattern body, e.g.
        ``'[regex]^git (diff|flake8|status)(?=\\s|$)'``.
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
    return f"[regex]^{cmd_regex}{_TOKEN_BOUNDARY_LOOKAHEAD}"


# ---------------------------------------------------------------------------
# Internal helpers -- static subsumption check
# ---------------------------------------------------------------------------


def _static_prefix_of(large_cmd: str, small_cmd: str) -> bool:
    """
    Return True when ``large_cmd`` is a structural prefix of ``small_cmd`` at
    the same word boundary :func:`~toolguard.permissions.match_command` uses
    for a DEFAULT ``:*`` prefix: equality, or ``small_cmd`` continuing after
    ``large_cmd`` with a space. A ``/`` is not a boundary here -- ``/usr/bin``
    does not structurally prefix ``/usr/bin/env``, matching
    ``/usr/bin:*``'s real match-set (it does not match ``/usr/bin/env``).

    This assumes ``large_cmd`` names a genuine ``large_cmd:*``/``:**``
    pattern -- the only shape this boundary rule actually covers
    ``small_cmd``'s match-set within. It says nothing about whether
    ``large_cmd`` was really written that way; the caller must not pass an
    EXACT (no-colon) pattern's command text here, since such a pattern
    matches only itself and this text-only comparison could not tell the
    difference. Given a genuine ``large_cmd:*`` on the caller's side, this is
    a real subset guarantee, not just a heuristic screen -- it does not run
    ``match_command`` to confirm it.

    Args:
        large_cmd: The command portion (before ``:``) of the larger pattern.
        small_cmd: The command portion of the potentially-subsumed pattern.

    Returns:
        True when ``large_cmd`` is a structural, word-boundary prefix of
        ``small_cmd``.
    """
    if small_cmd == large_cmd:
        return True
    if small_cmd.startswith(large_cmd + " "):
        return True
    if large_cmd.endswith(" ") and small_cmd.startswith(large_cmd):
        return True
    return False


# ---------------------------------------------------------------------------
# Internal helpers -- probe generation and safety check
# ---------------------------------------------------------------------------

#: Stand-in token for "a value no rule mentions", used to build near-miss
#: probes.
_PROBE_NEGATIVE_TOKEN = "__toolguard_probe_absent__"


def _generate_positive_probes(
    parsed_group: List[Tuple[List[str], str, int, List[str], List[str]]],
) -> List[str]:
    """
    Generate positive probe commands for a family-1 alternation group.

    Two per member: the bare command (cmd tokens joined, no args), and the same
    with a generic trailing ``--x``.

    Args:
        parsed_group: One ``(cmd_tokens, args, pos, prefix_tokens,
            suffix_tokens)`` tuple per group member.

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

    Puts :data:`_PROBE_NEGATIVE_TOKEN` in the varying slot, so neither the
    original patterns nor a faithful consolidated regex should match: a
    consolidated rule that matches anyway has widened the alternation.

    Args:
        prefix_tokens: Common prefix tokens before the alternation.
        varying_tokens: Unused; the probe deliberately avoids all of them.
        suffix_tokens: Common suffix tokens after the alternation.

    Returns:
        List of probe command strings.
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

    For each member, appends characters to the bare command with NO separating
    space (``git diff`` -> ``git diffx``, ``git difftool``).  A DEFAULT
    ``cmd:*`` pattern matches none of these -- its prefix must end on a token
    boundary -- so a consolidated regex without an equivalent boundary shows up
    here as a widening.

    Args:
        parsed_group: One ``(cmd_tokens, args, pos, prefix_tokens,
            suffix_tokens)`` tuple per group member.

    Returns:
        List of probe command strings.
    """
    probes: List[str] = []
    for cmd_tokens, _args, _pos, _prefix, _suffix in parsed_group:
        bare = " ".join(cmd_tokens)
        probes.append(bare + "x")
        probes.append(bare + "tool")
    return probes


def _corpus_verdict(
    corpus: Optional[List[LogEntry]],
    config_a: Configuration,
    config_b: Configuration,
    tool: str,
    probe_note: str,
    changed_word: str,
) -> Tuple[SafetyResult, str]:
    """
    Classify the corpus-replay half of a family-1/family-2 safety gate.

    Filters ``corpus`` to entries for ``tool`` before replaying and counting,
    so the reported entry count reflects commands that could actually
    exercise the change -- an entry for a different tool can never move its
    decision.  Distinguishes "no corpus was supplied" (``corpus`` is
    ``None``) from "a corpus was supplied but has none of this tool's
    commands" (filtered to empty): both are ``UNVERIFIED``, but only the
    empty case reuses :func:`~toolguard.tools.maintenance._render_replay`'s
    "vacuous, not a clean pass" wording for the analogous situation.

    Args:
        corpus: Harvested corpus, or ``None`` when ``--corpus`` was not passed.
        config_a: Configuration before the proposed change.
        config_b: Configuration after the proposed change.
        tool: Tool the change applies to; only matching corpus entries count.
        probe_note: Evidence prefix describing the probes that already
            passed, e.g. ``"4 probes unchanged"``.
        changed_word: Family-specific suffix reporting a clean replay, e.g.
            ``"0 changed"`` or ``"0 broadened, 0 tightened"``.

    Returns:
        ``(SafetyResult.SAFE, evidence)`` when a non-empty tool-filtered
        corpus replayed with no broadening or tightening,
        ``(SafetyResult.UNSAFE, evidence)`` when it changed a decision, or
        ``(SafetyResult.UNVERIFIED, evidence)`` when there was no
        tool-matching corpus to replay.
    """
    if corpus is None:
        return SafetyResult.UNVERIFIED, f"{probe_note}; no corpus"

    tool_corpus = [entry for entry in corpus if entry.tool == tool]
    if not tool_corpus:
        return SafetyResult.UNVERIFIED, (
            f"{probe_note}; corpus supplied but empty for {tool} -- "
            "vacuous, not a clean pass"
        )

    diff = replay(tool_corpus, config_a, config_b)
    if diff.broadened_count or diff.tightened_count:
        return SafetyResult.UNSAFE, (
            f"corpus replay changed decisions: {diff.broadened_count} broadened, "
            f"{diff.tightened_count} tightened"
        )
    evidence = f"{probe_note}; corpus replay {len(tool_corpus)} entries, {changed_word}"
    return SafetyResult.SAFE, evidence


def _check_family1_safe(  # noqa: PLR0913 -- 9 args
    config: Configuration,
    tool: str,
    provenance: Provenance,
    original_patterns: List[str],
    consolidated_body: str,
    prefix_tokens: List[str],
    varying_tokens: List[str],
    suffix_tokens: List[str],
    corpus: Optional[List[LogEntry]],
) -> Tuple[SafetyResult, str]:
    """
    Check whether replacing ``original_patterns`` with ``consolidated_body``
    changes any decision.  Both conditions are required for ``SAFE``:

    1. Every probe command has an IDENTICAL verdict under the original config
       and the consolidated config.  The probe set is the literal member
       commands (with and without a generic trailing arg), the prefix-extension
       near-misses of :func:`_generate_extension_probes`, and the absent-token
       near-misses of :func:`_generate_negative_probes`.
    2. When ``corpus`` is supplied, ``replay`` reports ZERO broadened AND ZERO
       tightened entries.  With no corpus this check cannot run at all, so the
       result is ``UNVERIFIED`` rather than ``SAFE``.

    Passing is evidence about the commands that were run, not a proof of
    match-set equality.  Two shapes are known to pass and still TIGHTEN:

    - **A wildcard in a NON-varying token.** Only the varying token is required
      to be wildcard-free, and :func:`_build_alternation_regex` escapes the
      rest, so ``git d*ff a:*`` + ``git d*ff b:*`` are accepted and
      ``git diff a`` stops being allowed.
    - **Path normalization.** DEFAULT matching tries a path-normalized form of
      the command as well as the raw one; a ``[regex]`` pattern only ever sees
      the raw one.  So ``cat ./x:*`` + ``cat ./y:*`` are accepted and ``cat x``
      stops being allowed.

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
        Tuple of ``(result, evidence_string)``.  ``result`` is ``UNSAFE`` when a
        probe or a corpus entry changed verdict, ``UNVERIFIED`` when every probe
        held but no corpus was supplied, and ``SAFE`` only when a corpus was
        also replayed clean.  ``evidence_string`` summarises what was checked.
    """
    config_b = with_layer_allow_replaced(
        config, tool, provenance, set(original_patterns), [consolidated_body]
    )

    parsed_group: List[Tuple[List[str], str, int, List[str], List[str]]] = []
    pos = len(prefix_tokens)
    for pat in original_patterns:
        ptype, body = parse_pattern(pat, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args = split_default_body(body)
        parsed_group.append((cmd_tokens, args, pos, prefix_tokens, suffix_tokens))

    probes = (
        _generate_positive_probes(parsed_group)
        + _generate_extension_probes(parsed_group)
        + _generate_negative_probes(prefix_tokens, varying_tokens, suffix_tokens)
    )

    changed = 0
    for cmd in probes:
        if decide(config, tool, cmd).decision != decide(config_b, tool, cmd).decision:
            changed += 1
    if changed:
        return (
            SafetyResult.UNSAFE,
            f"probe decision changes: {changed}/{len(probes)} (not equivalence-preserving)",
        )

    return _corpus_verdict(
        corpus, config, config_b, tool, f"{len(probes)} probes unchanged", "0 changed"
    )


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

    Groups DEFAULT ``cmd:*``/``cmd:**`` patterns that are token-identical except
    exactly ONE token slot, varying over literal, wildcard-free values.  Each
    group of >= 2 is a candidate, emitted only when :func:`_check_family1_safe`
    passes.

    Args:
        config: The full configuration (for probe decisions).
        tool: Tool name.
        allow_patterns: Wrapper-free allow patterns from the target layer.
        provenance: Layer provenance; identifies the layer to rewrite.
        corpus: Optional harvested corpus for the replay check.

    Returns:
        List of accepted :class:`ConsolidationProposal` records.
    """
    # Each entry: (raw_body, cmd_tokens, args_part)
    default_entries: List[Tuple[str, List[str], str]] = []
    for raw in allow_patterns:
        ptype, body = parse_pattern(raw, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args_part = split_default_body(body)
        if not cmd_tokens:
            continue
        # Prefix forms only.  A no-colon EXACT pattern cannot be folded into a
        # prefix regex without end-anchoring it, which the alternation does not do.
        if args_part != "*":
            continue
        default_entries.append((raw, cmd_tokens, args_part))

    if len(default_entries) < 2:
        return []

    # One key per (pattern, token position): that position is the varying slot
    # and every other position is fixed, so patterns sharing a key differ at
    # most in that slot.  A pattern therefore lands in as many groups as it has
    # literal tokens.
    groups: Dict[Tuple, List[Tuple[str, List[str], str, int]]] = defaultdict(list)

    for raw, cmd_tokens, args_part in default_entries:
        n = len(cmd_tokens)
        for pos in range(n):
            if not _is_literal_token(cmd_tokens[pos]):
                continue
            others = tuple((j, cmd_tokens[j]) for j in range(n) if j != pos)
            key = (args_part, n, pos, others)
            groups[key].append((raw, cmd_tokens, args_part, pos))

    proposals: List[ConsolidationProposal] = []
    # One proposal per set of patterns, even when that set could be read as
    # varying at more than one position.
    emitted_sets: Set[frozenset] = set()

    for (args_part, n, pos, others), members in groups.items():
        if len(members) < 2:
            continue

        raw_bodies = [m[0] for m in members]
        group_set = frozenset(raw_bodies)
        if group_set in emitted_sets:
            continue

        # Redundant -- the group key is only built for a literal token.
        varying_tokens = [m[1][pos] for m in members]
        if not all(_is_literal_token(t) for t in varying_tokens):
            continue
        if len(set(varying_tokens)) != len(varying_tokens):
            # Equal varying tokens mean equal bodies: duplicates, not an
            # alternation.
            continue

        # Every member agrees outside the varying slot, so any member's tokens
        # give the shared prefix and suffix.
        first_cmd_tokens = members[0][1]
        prefix_tokens = first_cmd_tokens[:pos]
        suffix_tokens = first_cmd_tokens[pos + 1 :]

        consolidated = _build_alternation_regex(
            prefix_tokens, varying_tokens, suffix_tokens
        )

        result, evidence = _check_family1_safe(
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
        if result is SafetyResult.UNSAFE:
            continue
        # UNVERIFIED (no corpus) is accepted on probe evidence alone, same as
        # SAFE -- refusing outright would break a fresh install with no logs.

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
                verification=result,
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
) -> Tuple[SafetyResult, str]:
    """
    Check whether removing ``small_body`` leaves its own commands allowed.

    Two probes derived from ``small_cmd`` must be ``allow`` both before AND
    after removal.  With a corpus, replay must also report no broadening AND
    no tightening.  With no corpus this replay check cannot run at all, so
    the result is ``UNVERIFIED`` rather than ``SAFE``.

    Args:
        config: The full original configuration.
        tool: Tool name.
        provenance: Layer provenance of the pattern being removed.
        small_body: Wrapper-free body of the pattern proposed for removal.
        small_cmd: Command portion of ``small_body`` (before the ``:``), used to
            build the probes.
        corpus: Optional corpus for the replay check.

    Returns:
        Tuple of ``(result, evidence_string)``.  ``result`` is ``UNSAFE`` when a
        probe or a corpus entry changed verdict, ``UNVERIFIED`` when both probes
        held but no corpus was supplied, and ``SAFE`` only when a corpus was
        also replayed clean.
    """
    config_b = with_layer_allow_replaced(config, tool, provenance, {small_body}, [])

    probes = [small_cmd, small_cmd + " --x"]
    pos_fail = 0
    for cmd in probes:
        va = decide(config, tool, cmd).decision
        vb = decide(config_b, tool, cmd).decision
        if va != "allow" or vb != "allow":
            pos_fail += 1

    if pos_fail:
        return SafetyResult.UNSAFE, f"positive probe failures: {pos_fail}/{len(probes)}"

    return _corpus_verdict(
        corpus,
        config,
        config_b,
        tool,
        f"{len(probes)} positive probes pass",
        "0 broadened, 0 tightened",
    )


def _find_static_subsumptions(
    config: Configuration,
    tool: str,
    allow_patterns: Tuple[str, ...],
    provenance: Provenance,
    corpus: Optional[List[LogEntry]],
) -> List[ConsolidationProposal]:
    """
    Find static subsumption elimination opportunities in ``allow_patterns``.

    Considers every ordered pair of DEFAULT patterns whose args part is ``*``
    or absent, and proposes dropping the second when the first is a genuine
    ``:*``/``:**`` prefix (an EXACT, no-colon pattern only ever matches
    itself and can never cover another pattern's extension, so it is never
    tried as the covering side), :func:`_static_prefix_of` holds on their
    command text, and :func:`_check_family2_safe` passes. Pairs whose command
    parts are equal are skipped, so an exact duplicate is never reported as a
    subsumption.

    Args:
        config: The full configuration (for probe decisions).
        tool: Tool name.
        allow_patterns: Wrapper-free allow patterns from the target layer.
        provenance: Layer provenance.
        corpus: Optional corpus for the replay guard.

    Returns:
        List of accepted :class:`ConsolidationProposal` records.
    """
    # Each entry: (raw_body, cmd_str, cmd_tokens, args_part)
    default_entries: List[Tuple[str, str, List[str], str]] = []
    for raw in allow_patterns:
        ptype, body = parse_pattern(raw, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args_part = split_default_body(body)
        if not cmd_tokens:
            continue
        # args_part == "" also covers a colon-bearing, non-trailing pattern like
        # "git commit:-m *" (split_default_body no longer splits on a mid-pattern
        # colon), whose cmd_tokens carry an fnmatch wildcard the "no args" cases
        # below don't expect. _static_prefix_of/_check_family2_safe are token-based
        # and still gate every proposal, so this hasn't produced a wrong one.
        if args_part not in ("*", ""):
            continue
        cmd_str = " ".join(cmd_tokens)
        default_entries.append((raw, cmd_str, cmd_tokens, args_part))

    proposals: List[ConsolidationProposal] = []
    proposed_removals: Set[str] = set()

    n = len(default_entries)
    for i in range(n):
        raw_large, large_cmd, _, large_args_part = default_entries[i]
        if large_args_part != "*":
            # EXACT (no ':*'/':**') -- matches only itself, so it can never
            # structurally cover another pattern's extension.
            continue
        for j in range(n):
            if i == j:
                continue
            raw_small, small_cmd, _, _ = default_entries[j]
            if large_cmd == small_cmd:
                continue
            # One removal proposal per pattern, however many rules cover it.
            if raw_small in proposed_removals:
                continue
            if not _static_prefix_of(large_cmd, small_cmd):
                continue

            result, evidence = _check_family2_safe(
                config, tool, provenance, raw_small, small_cmd, corpus
            )
            if result is SafetyResult.UNSAFE:
                continue
            # UNVERIFIED (no corpus) is accepted on probe evidence alone, same as
            # SAFE -- refusing outright would break a fresh install with no logs.

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
                        f"'{raw_small}' is a structural (word-boundary) text "
                        f"prefix match under '{raw_large}'; see replay_summary "
                        f"for what was actually verified"
                    ),
                    replay_summary=evidence,
                    verification=result,
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
    Return probe-checked consolidation proposals for ``tool``'s allow list.

    Scans every config layer's allow list for both families; a candidate that
    fails its probe check or the corpus replay is dropped without a trace.  What
    those checks do and do not establish is in :func:`_check_family1_safe` and
    :func:`_static_prefix_of`.

    Each proposal is evaluated against the ORIGINAL config on its own.  Two can
    name the same pattern -- a family-1 group and a family-2 drop covering the
    same rule -- and nothing here checks that applying more than one together
    still changes no decision.

    Args:
        config: The resolved :class:`~toolguard.config.Configuration`.
        tool: Tool name to inspect (e.g. ``'Bash'``).
        corpus: Optional harvested command corpus
            (:class:`~toolguard.tools.log_harvest.LogEntry` list) replayed as a
            second gate.  When ``None`` or empty, only the probes are applied.

    Returns:
        List of :class:`ConsolidationProposal` records, ordered by ``kind``,
        layer provenance, then removed patterns.
    """
    proposals: List[ConsolidationProposal] = []

    for layer in per_layer_rules(config, tool):
        allow = layer.allow  # wrapper-free tuple

        proposals.extend(
            _find_literal_alternations(config, tool, allow, layer.provenance, corpus)
        )
        proposals.extend(
            _find_static_subsumptions(config, tool, allow, layer.provenance, corpus)
        )

    proposals.sort(
        key=lambda p: (
            p.kind,
            p.layer_provenance.describe()
            if hasattr(p.layer_provenance, "describe")
            else str(p.layer_provenance),
            sorted(p.removed_patterns),
        )
    )
    return proposals


# ---------------------------------------------------------------------------
# Agent-judged broadening (families 3-4) -- enumerate + attach evidence
# ---------------------------------------------------------------------------


def _overlapping_guard_rules(
    broadened_prefix: Tuple[str, ...],
    ask_rules: Tuple[str, ...],
    deny_rules: Tuple[str, ...],
) -> Tuple[str, ...]:
    """
    Find same-layer ask/deny rules whose command-space overlaps a broadening.

    A TEXTUAL, precedence-ignorant overlap: it reports guards the broadened
    allow now also spans, whichever rule would win at decision time.  Only a
    DEFAULT ``cmd:*``/``cmd:**`` guard is comparable, so an ask/deny written as
    an extended-syntax pattern, with a real args part, or as an exact no-colon
    body is silently skipped.

    Args:
        broadened_prefix: Command-prefix tokens of the broadened allow rule.
        ask_rules: Wrapper-free ask bodies in the same layer.
        deny_rules: Wrapper-free deny bodies in the same layer.

    Returns:
        Sorted tuple of labelled guard bodies, e.g. ``("deny 'uv run:*'",)``.
    """
    prefix_list = list(broadened_prefix)
    overlaps: List[str] = []
    for section, rules in (("ask", ask_rules), ("deny", deny_rules)):
        for body in rules:
            gtokens = default_prefix_tokens(body)
            if gtokens is not None and prefixes_overlap(prefix_list, gtokens):
                overlaps.append(f"{section} '{body}'")
    return tuple(sorted(overlaps))


def _broadening_probe_surface(
    config_a: Configuration,
    config_b: Configuration,
    tool: str,
    prefix_joined: str,
) -> Tuple[str, ...]:
    """
    Synthesize near-miss probes the broadened rule admits but the originals do not.

    The probes put :data:`_PROBE_NEGATIVE_TOKEN` after the prefix, so no
    original narrow rule can name them.  A probe is kept only when it is
    ``allow`` under ``config_b`` and NOT ``allow`` under ``config_a``, so an
    unrelated broad allow already covering it does not create a false entry.

    Args:
        config_a: The baseline configuration.
        config_b: The broadened configuration.
        tool: Tool name to decide under.
        prefix_joined: The space-joined command prefix being broadened.

    Returns:
        Tuple of synthetic command strings the broadening newly admits.
    """
    probes = (
        f"{prefix_joined} {_PROBE_NEGATIVE_TOKEN}",
        f"{prefix_joined} {_PROBE_NEGATIVE_TOKEN} --flag value",
    )
    surface = [
        cmd
        for cmd in probes
        if decide(config_b, tool, cmd).decision == "allow"
        and decide(config_a, tool, cmd).decision != "allow"
    ]
    return tuple(surface)


def _find_prefix_broadenings(
    config: Configuration,
    tool: str,
    layer: LayerRules,
    corpus: Optional[List[LogEntry]],
) -> List[BroadeningProposal]:
    """
    Enumerate prefix-broadening candidates within one config layer.

    Groups DEFAULT ``<prefix> <sub>:*`` allow patterns that share an identical
    leading command prefix (all tokens but the last) and have a literal final
    token, and proposes collapsing each group of >= 2 distinct finals into a
    single ``<prefix> :*`` rule that admits ANY command under the prefix.  Each
    candidate carries the corpus commands it newly admits (when a corpus is
    supplied), the same layer's overlapping ask/deny guards, and a synthetic
    admitted surface.

    Args:
        config: The resolved configuration.
        tool: Tool name to inspect.
        layer: The :class:`~toolguard.tools.config_access.LayerRules` to inspect
            (its ``allow`` is broadened; its ``ask``/``deny`` are checked for
            overlap).
        corpus: Optional command corpus for replay evidence.

    Returns:
        List of :class:`BroadeningProposal` records, in no particular order.
    """
    provenance = layer.provenance

    # The >= 2 token requirement leaves a non-empty prefix, so single-token
    # commands (`ls:*` + `cat:*`) can never collapse into a bare ` :*` that
    # would allow everything.
    groups: Dict[Tuple[Tuple[str, ...], str], List[Tuple[str, str]]] = defaultdict(list)
    for raw in layer.allow:
        ptype, body = parse_pattern(raw, extended_syntax=True)
        if ptype != PatternType.DEFAULT:
            continue
        cmd_tokens, args_part = split_default_body(body)
        if args_part != "*":
            continue
        if len(cmd_tokens) < 2:
            continue
        last = cmd_tokens[-1]
        if not _is_literal_token(last):
            continue
        prefix = tuple(cmd_tokens[:-1])
        groups[(prefix, args_part)].append((raw, last))

    proposals: List[BroadeningProposal] = []
    seen: Set[Tuple[str, str]] = set()
    for (prefix, args_part), members in groups.items():
        finals = {last for _, last in members}
        if len(finals) < 2:
            continue

        removed = tuple(sorted(raw for raw, _ in members))
        prefix_joined = " ".join(prefix)
        added = f"{prefix_joined} :{args_part}"
        key = (added, "\x00".join(removed))
        if key in seen:
            continue
        seen.add(key)

        config_b = with_layer_allow_replaced(
            config, tool, provenance, set(removed), [added]
        )

        newly_admitted: Tuple[str, ...] = ()
        if corpus:
            newly_admitted = tuple(
                d.entry.command
                for d in replay(corpus, config, config_b).broadened()
                if d.entry.tool == tool
            )

        overlaps = _overlapping_guard_rules(prefix, layer.ask, layer.deny)
        probe_surface = _broadening_probe_surface(config, config_b, tool, prefix_joined)

        rationale = (
            f"Broaden {len(removed)} '{prefix_joined} <sub>:{args_part}' allow rules "
            f"into '{added}', admitting ANY command beginning with '{prefix_joined}' "
            f"(known subcommands {sorted(finals)} -> all)."
        )
        proposals.append(
            BroadeningProposal(
                kind="prefix-broadening",
                tool=tool,
                list_type="allow",
                layer_provenance=provenance,
                removed_patterns=removed,
                added_pattern=added,
                rationale=rationale,
                newly_admitted_commands=newly_admitted,
                overlaps_guard_rules=overlaps,
                probe_admitted_surface=probe_surface,
            )
        )
    return proposals


def propose_broadening_consolidations(
    config: Configuration,
    tool: str,
    corpus: Optional[List[LogEntry]] = None,
) -> List[BroadeningProposal]:
    """
    Enumerate AGENT-JUDGED broadening proposals for ``tool``'s allow list.

    Where :func:`propose_consolidations` only emits what its probes found
    unchanged, this deliberately surfaces consolidations that ADMIT MORE than
    the union of the rules they replace.  Nothing here is safe to auto-apply --
    each proposal carries the evidence a human or the maintenance skill needs to
    judge it; see :class:`BroadeningProposal`.

    Args:
        config: The resolved :class:`~toolguard.config.Configuration`.
        tool: Tool name to inspect (e.g. ``'Bash'``).
        corpus: Optional harvested command corpus.  It populates
            ``newly_admitted_commands`` and nothing else -- the guard overlaps
            and the synthetic admitted surface are computed either way.

    Returns:
        List of :class:`BroadeningProposal` records, ordered by ``kind``, layer
        provenance, then removed patterns.
    """
    proposals: List[BroadeningProposal] = []
    for layer in per_layer_rules(config, tool):
        proposals.extend(_find_prefix_broadenings(config, tool, layer, corpus))

    proposals.sort(
        key=lambda p: (
            p.kind,
            p.layer_provenance.describe()
            if hasattr(p.layer_provenance, "describe")
            else str(p.layer_provenance),
            sorted(p.removed_patterns),
        )
    )
    return proposals
