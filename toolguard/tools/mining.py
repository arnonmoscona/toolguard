"""
Rule mining: turn a harvested command corpus into actionable rule candidates.

The deterministic core behind the "what should become a rule?" maintenance
task.  It never invents or generalises a permission pattern.  It does two
things:

1. **Classify and group** (:func:`mine_rule_candidates`).  Each corpus entry's
   verdict under the CURRENT config is compared with the status the corpus
   recorded for it:

   - ``allow-candidate`` -- config says ``ask``/``deny``, corpus recorded
     ``EXECUTED`` (approval fatigue, or blocked-but-needed): a candidate to ADD
     to allow.
   - ``declined``        -- corpus recorded ``REFUSED``, whatever the config
     says.
   - ``denied``/``asked`` -- config says ``deny``/``ask`` and the corpus
     recorded neither ``EXECUTED`` nor ``REFUSED``.
   - ``consistent``      -- everything else: the config already allows it and
     the corpus recorded no refusal.  Dropped, never reported.

2. **Measure a proposal** (:func:`evaluate_added_allow_rule`).  Decision-replay
   against the config with the proposed allow rule added, naming the commands
   the rule newly admits -- of those the corpus happens to contain.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, List, Optional, Tuple

from toolguard.api import decide
from toolguard.config import Configuration, Provenance
from toolguard.constants import FILE_TOOLS, STATUS_EXECUTED, STATUS_REFUSED
from toolguard.parser.command_extractor import extract_commands
from toolguard.parser.multiline import LeafCommand, extract_structured
from toolguard.tools.config_access import with_layer_allow_replaced
from toolguard.tools.danger import assess_pattern_risk
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.replay import replay

SIGNAL_ALLOW_CANDIDATE = "allow-candidate"
SIGNAL_DECLINED = "declined"
SIGNAL_DENIED = "denied"
SIGNAL_ASKED = "asked"
#: Dropped by :func:`mine_rule_candidates`, so it never reaches a
#: :class:`CommandGroup` or the rendered report.
SIGNAL_CONSISTENT = "consistent"

#: Group display priority, applied only after the occurrence count -- lower
#: sorts first.
_SIGNAL_ORDER = {
    SIGNAL_ALLOW_CANDIDATE: 0,
    SIGNAL_DECLINED: 1,
    SIGNAL_DENIED: 2,
    SIGNAL_ASKED: 3,
}

#: Strictness order for a cluster's headline verdict -- higher wins, so a
#: single deny observed in a cluster is never summarised away by a majority
#: ask or allow.
_VERDICT_STRICTNESS: Dict[str, int] = {"allow": 0, "ask": 1, "deny": 2}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandGroup:
    """
    A cluster of corpus commands sharing a tool, command key, and signal.

    Attributes:
        tool: Tool name (``'Bash'``, ``'Read'``, ...).
        command_key: Coarse grouping key -- see :func:`_command_key`.
        signal: One of ``allow-candidate`` / ``declined`` / ``denied`` / ``asked``.
        distinct_commands: The distinct command strings in this cluster (sorted).
        occurrences: Total number of corpus entries in this cluster.
        current_verdict: The STRICTEST current-config verdict among the
            cluster (``deny`` > ``ask`` > ``allow``), so a single denied
            member is never summarised away by a majority ask or allow.
        observed_counts: Map of observed status -> count within the cluster.
    """

    tool: str
    command_key: str
    signal: str
    distinct_commands: Tuple[str, ...]
    occurrences: int
    current_verdict: str
    observed_counts: Dict[str, int]


@dataclass(frozen=True)
class MiningReport:
    """
    The result of mining a corpus against the current config.

    Attributes:
        groups: Command clusters, in the order :func:`mine_rule_candidates`
            sorted them.  ``consistent`` entries are not represented.
    """

    groups: Tuple[CommandGroup, ...]

    def by_signal(self, signal: str) -> List[CommandGroup]:
        """Return the clusters with the given signal."""
        return [g for g in self.groups if g.signal == signal]

    @property
    def allow_candidates(self) -> List[CommandGroup]:
        """Clusters the config would ``ask``/``deny`` that the corpus recorded as executed."""
        return self.by_signal(SIGNAL_ALLOW_CANDIDATE)

    @property
    def declined(self) -> List[CommandGroup]:
        """Clusters whose corpus entries recorded ``REFUSED``."""
        return self.by_signal(SIGNAL_DECLINED)


@dataclass(frozen=True)
class AddRuleEffect:
    """
    The replay-measured effect of adding an allow rule.

    Attributes:
        tool: Tool the rule applies to.
        pattern: The wrapper-free allow pattern body that was evaluated.
        target_locus: Human-readable description of the layer it was added to.
        newly_allowed: Distinct corpus commands that were ``ask``/``deny``
            before and ``allow`` after (sorted).
        broadened_count: Number of corpus entries that became looser, or
            ``None`` when the corpus was empty -- measuring zero entries is
            not the same claim as measuring some and finding no effect.
        tightened_count: Number of corpus entries that became stricter, under
            the same empty-corpus rule as ``broadened_count``.
        risk_flags: :func:`~toolguard.tools.danger.assess_pattern_risk`
            detector IDs the pattern itself trips, independent of the corpus
            -- so a tool-wide ``'*'`` proposal is distinguishable from a
            narrow one even when the corpus never exercises the difference.
    """

    tool: str
    pattern: str
    target_locus: str
    newly_allowed: Tuple[str, ...]
    broadened_count: Optional[int]
    tightened_count: Optional[int] = None
    risk_flags: Tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _command_key(tool: str, command: str) -> str:
    """
    Compute the coarse grouping key for a corpus entry.

    A file tool groups by its target's parent directory; every other tool --
    ``Bash`` and any MCP terminal tool alike -- groups by the leading token of
    the command's FIRST extracted leaf (:func:`~toolguard.parser.command_extractor.extract_commands`),
    e.g. ``git``. Routed through the grammar rather than a bare ``.split()`` so
    a leading disclosure comment or a compound prefix does not become the key.

    Args:
        tool: Tool name.
        command: The command string, or the file path for a file tool.

    Returns:
        A grouping key string.
    """
    if tool in FILE_TOOLS:
        parent = str(PurePosixPath(command).parent)
        return parent if parent and parent != "." else command
    extracted = extract_commands(command)
    stripped = extracted[0].strip() if extracted else command.strip()
    if not stripped:
        return stripped
    return stripped.split()[0]


def _command_has_a_real_leaf(command: str) -> bool:
    """
    True when *command* decomposes into at least one real leaf command a
    permission pattern could match.

    False for a blank command and for one the grammar cannot parse -- both
    resolve through a safety net rather than a rule, so "add a rule for this"
    has nothing behind it.
    """
    return any(isinstance(r, LeafCommand) for r in extract_structured(command))


def _deduplicated(corpus: List[LogEntry]) -> List[LogEntry]:
    """
    Drop a later entry repeating an earlier one's ``(timestamp, tool, command,
    status)`` -- the shape :func:`~toolguard.tools.corpus.harvest_corpus`
    produces when the daily log and the transcript both record the same real
    event, which must count once.
    """
    seen = set()
    deduped = []
    for entry in corpus:
        key = (entry.timestamp, entry.tool, entry.command, entry.status)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _classify(current_verdict: str, observed_status: str) -> str:
    """
    Classify one corpus entry's mining signal (see the module docstring).

    Args:
        current_verdict: The verdict the CURRENT config gives (``allow``/``ask``/``deny``).
        observed_status: The status the corpus recorded.  Only ``EXECUTED``
            and ``REFUSED`` are distinguished; every other value behaves the
            same way.

    Returns:
        One of the ``SIGNAL_*`` constants.
    """
    if observed_status == STATUS_REFUSED:
        return SIGNAL_DECLINED
    if current_verdict in ("ask", "deny") and observed_status == STATUS_EXECUTED:
        return SIGNAL_ALLOW_CANDIDATE
    if current_verdict == "deny":
        return SIGNAL_DENIED
    if current_verdict == "ask":
        return SIGNAL_ASKED
    return SIGNAL_CONSISTENT


# ---------------------------------------------------------------------------
# Mining
# ---------------------------------------------------------------------------


def mine_rule_candidates(
    config: Configuration,
    corpus: List[LogEntry],
    *,
    min_occurrences: int = 1,
) -> MiningReport:
    """
    Mine a corpus for rule candidates against the current config.

    Each entry is classified (see the module docstring), then grouped by
    ``(tool, command_key, signal)`` and summarised.  ``consistent`` entries are
    dropped before grouping, as is an ``allow-candidate`` whose command is a
    safety-net verdict rather than a real rule match (see
    :func:`_command_has_a_real_leaf`).  Two entries identical in
    ``(timestamp, tool, command, status)`` -- the same real event harvested
    twice, from the log and the transcript -- count once.

    Args:
        config: The current resolved configuration.
        corpus: Harvested command corpus.
        min_occurrences: Drop clusters holding fewer than this many corpus
            entries.  Counts entries, not distinct commands.

    Returns:
        A :class:`MiningReport` whose groups are sorted by occurrences (desc),
        then signal priority, then tool, then command key.
    """
    buckets: Dict[Tuple[str, str, str], Dict] = {}

    for entry in _deduplicated(corpus):
        verdict = decide(config, entry.tool, entry.command).decision
        signal = _classify(verdict, entry.status)
        if (
            signal == SIGNAL_ALLOW_CANDIDATE
            and entry.tool not in FILE_TOOLS
            and not _command_has_a_real_leaf(entry.command)
        ):
            signal = SIGNAL_CONSISTENT
        if signal == SIGNAL_CONSISTENT:
            continue

        key = (entry.tool, _command_key(entry.tool, entry.command), signal)
        bucket = buckets.get(key)
        if bucket is None:
            bucket = {
                "commands": set(),
                "occurrences": 0,
                "verdicts": Counter(),
                "observed": Counter(),
            }
            buckets[key] = bucket
        bucket["commands"].add(entry.command)
        bucket["occurrences"] += 1
        bucket["verdicts"][verdict] += 1
        bucket["observed"][entry.status] += 1

    groups: List[CommandGroup] = []
    for (tool, command_key, signal), bucket in buckets.items():
        if bucket["occurrences"] < min_occurrences:
            continue
        dominant_verdict = max(
            bucket["verdicts"], key=lambda v: _VERDICT_STRICTNESS.get(v, -1)
        )
        groups.append(
            CommandGroup(
                tool=tool,
                command_key=command_key,
                signal=signal,
                distinct_commands=tuple(sorted(bucket["commands"])),
                occurrences=bucket["occurrences"],
                current_verdict=dominant_verdict,
                observed_counts=dict(bucket["observed"]),
            )
        )

    groups.sort(
        key=lambda g: (
            -g.occurrences,
            _SIGNAL_ORDER.get(g.signal, 99),
            g.tool,
            g.command_key,
        )
    )
    return MiningReport(groups=tuple(groups))


# ---------------------------------------------------------------------------
# Candidate measurement (replay-backed)
# ---------------------------------------------------------------------------


def evaluate_added_allow_rule(
    config: Configuration,
    tool: str,
    pattern: str,
    target_provenance: Provenance,
    corpus: List[LogEntry],
) -> AddRuleEffect:
    """
    Measure, by decision-replay, the effect of adding an allow rule.

    Builds a synthetic config with ``pattern`` appended to ``tool``'s allow list
    at ``target_provenance`` and replays the corpus against (current vs proposed).
    Only commands the corpus contains are measured, so the result is a lower
    bound on what the rule admits, not its full reach -- ``risk_flags`` covers
    the pattern's own static reach, corpus or no corpus.

    Args:
        config: The current configuration.
        tool: The tool the rule applies to.
        pattern: The wrapper-free allow pattern body to add (e.g. ``git push:*``).
        target_provenance: The layer (provenance) to add the rule to.
        corpus: The command corpus to measure against.

    Returns:
        An :class:`AddRuleEffect` with the newly-allowed commands, change
        counts, and the pattern's static risk flags.
    """
    config_b = with_layer_allow_replaced(
        config, tool, target_provenance, set(), [pattern]
    )
    diff = replay(corpus, config, config_b)

    newly_allowed = sorted(
        {d.entry.command for d in diff.broadened() if d.decision_b.decision == "allow"}
    )

    return AddRuleEffect(
        tool=tool,
        pattern=pattern,
        target_locus=target_provenance.describe(),
        newly_allowed=tuple(newly_allowed),
        broadened_count=diff.broadened_count if corpus else None,
        tightened_count=diff.tightened_count if corpus else None,
        risk_flags=assess_pattern_risk(tool, pattern),
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_mining_report(report: MiningReport, fmt: str = "text") -> str:
    """
    Render a :class:`MiningReport` as human-readable text.

    Args:
        report: The report to render.
        fmt: ``'text'`` (default) or ``'markdown'``.

    Returns:
        A title, one line carrying all four signal counts, then one block per
        group in :attr:`MiningReport.groups` order -- which is by frequency
        first, so a common ``asked`` group can precede a rare
        ``allow-candidate`` one.

    Raises:
        ValueError: When ``fmt`` is not ``'text'`` or ``'markdown'``.
    """
    if fmt not in ("text", "markdown"):
        raise ValueError(f"unknown format {fmt!r} (expected 'text' or 'markdown')")

    md = fmt == "markdown"
    lines: List[str] = []
    title = "Toolguard Rule Mining Report"
    lines.append(f"# {title}" if md else title)
    if not md:
        lines.append("=" * len(title))
    lines.append("")

    counts = Counter(g.signal for g in report.groups)
    lines.append(
        "allow-candidate: {ac}  declined: {dc}  denied: {dn}  asked: {ak}".format(
            ac=counts.get(SIGNAL_ALLOW_CANDIDATE, 0),
            dc=counts.get(SIGNAL_DECLINED, 0),
            dn=counts.get(SIGNAL_DENIED, 0),
            ak=counts.get(SIGNAL_ASKED, 0),
        )
    )
    lines.append("")

    for group in report.groups:
        header = (
            f"[{group.signal}] {group.tool} '{group.command_key}' "
            f"x{group.occurrences} (now: {group.current_verdict})"
        )
        lines.append(f"## {header}" if md else header)
        for cmd in group.distinct_commands:
            lines.append(f"  - {cmd}")
        lines.append("")

    return "\n".join(lines)
