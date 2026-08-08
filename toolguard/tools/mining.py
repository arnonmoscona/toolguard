"""
Rule mining: turn a harvested command corpus into actionable rule candidates.

This is the deterministic core behind the "what should become a rule?" maintenance
task (the successor to the ad-hoc ``denied-summary`` prototype).  It does NOT
invent permission patterns -- pattern generation/generalisation is agent
judgement (and, later, the curated-tool advisor).  Instead it:

1. **Aggregates + classifies** every corpus command by comparing the CURRENT
   config's decision (via :func:`~toolguard.api.decide`) with the
   OBSERVED outcome from the corpus (logs + transcripts):

   - ``allow-candidate`` -- the config would ``ask``/``deny`` it but it was
     actually EXECUTED (approval fatigue, or blocked-but-needed): a candidate to
     ADD to allow.
   - ``declined``        -- the user REFUSED the permission prompt (transcript
     signal): they said no; surface it, do not suggest allowing it.
   - ``denied``/``asked`` -- the config blocks/prompts it and there is no
     positive observation: shown for review.

   Commands the config already allows and that ran fine are ``consistent`` and
   omitted from the report.

2. **Verifies** a proposed allow rule with decision-replay
   (:func:`evaluate_added_allow_rule`): it quantifies EXACTLY which corpus
   commands the rule would newly admit -- the perfect input for a risk note and
   the guard against an over-broad suggestion.

The allow/deny asymmetry applies: allow candidates are conservative (the user
must approve adding them, and replay quantifies the blast radius); declined/deny
signals bias toward fail-safe.
"""

from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Dict, List, Tuple

from toolguard.api import decide
from toolguard.config import Configuration, Provenance
from toolguard.constants import FILE_TOOLS, STATUS_EXECUTED, STATUS_REFUSED
from toolguard.tools.config_access import with_layer_allow_replaced
from toolguard.tools.log_harvest import LogEntry
from toolguard.tools.replay import replay

# Signal classifications (most actionable first).
SIGNAL_ALLOW_CANDIDATE = "allow-candidate"
SIGNAL_DECLINED = "declined"
SIGNAL_DENIED = "denied"
SIGNAL_ASKED = "asked"
SIGNAL_CONSISTENT = "consistent"  # omitted from the report

# Signal display priority (lower sorts first when occurrences tie).
_SIGNAL_ORDER = {
    SIGNAL_ALLOW_CANDIDATE: 0,
    SIGNAL_DECLINED: 1,
    SIGNAL_DENIED: 2,
    SIGNAL_ASKED: 3,
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandGroup:
    """
    A cluster of corpus commands sharing a tool, command key, and signal.

    Attributes:
        tool: Tool name (``'Bash'``, ``'Read'``, ...).
        command_key: Coarse grouping key (Bash: the executable token, e.g.
            ``'git'``; file tools: the parent directory).
        signal: One of ``allow-candidate`` / ``declined`` / ``denied`` / ``asked``.
        distinct_commands: The distinct command strings in this cluster (sorted).
        occurrences: Total number of corpus entries in this cluster.
        current_verdict: The most common current-config verdict among the cluster.
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
        groups: Command clusters, sorted by occurrences (desc) then signal
            priority then command_key.  Excludes ``consistent`` commands.
    """

    groups: Tuple[CommandGroup, ...]

    def by_signal(self, signal: str) -> List[CommandGroup]:
        """Return the clusters with the given signal."""
        return [g for g in self.groups if g.signal == signal]

    @property
    def allow_candidates(self) -> List[CommandGroup]:
        """Clusters the config blocks/prompts but were actually executed."""
        return self.by_signal(SIGNAL_ALLOW_CANDIDATE)

    @property
    def declined(self) -> List[CommandGroup]:
        """Clusters the user refused at the permission prompt."""
        return self.by_signal(SIGNAL_DECLINED)


@dataclass(frozen=True)
class AddRuleEffect:
    """
    The replay-measured effect of adding an allow rule.

    Attributes:
        tool: Tool the rule applies to.
        pattern: The wrapper-free allow pattern body that was evaluated.
        target_locus: Human-readable description of the layer it was added to.
        newly_allowed: Distinct corpus commands that move toward ``allow`` (were
            ``ask``/``deny`` before, ``allow`` after) -- exactly what the rule
            admits.
        broadened_count: Number of corpus entries that became looser.
        tightened_count: Number that became stricter (should be 0 for a pure
            allow addition; non-zero signals an interaction worth inspecting).
    """

    tool: str
    pattern: str
    target_locus: str
    newly_allowed: Tuple[str, ...]
    broadened_count: int
    tightened_count: int = 0


# ---------------------------------------------------------------------------
# Classification helpers
# ---------------------------------------------------------------------------


def _command_key(tool: str, command: str) -> str:
    """
    Compute the coarse grouping key for a command.

    Bash commands group by their leading executable token (e.g. ``git``); file
    tools group by their target's parent directory.

    Args:
        tool: Tool name.
        command: The command string (Bash) or file path (file tools).

    Returns:
        A grouping key string.
    """
    if tool in FILE_TOOLS:
        parent = str(PurePosixPath(command).parent)
        return parent if parent and parent != "." else command
    stripped = command.strip()
    if not stripped:
        return stripped
    return stripped.split()[0]


def _classify(current_verdict: str, observed_status: str) -> str:
    """
    Classify one corpus entry's mining signal.

    Args:
        current_verdict: The verdict the CURRENT config gives (``allow``/``ask``/``deny``).
        observed_status: The observed status from the corpus (``EXECUTED``/
            ``REFUSED``/``ERROR``/``UNKNOWN``/...).

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

    Each entry's current-config decision is compared with its observed outcome and
    classified (see module docstring).  Entries are grouped by
    ``(tool, command_key, signal)`` and summarised.  ``consistent`` commands
    (already allowed and executed) are omitted.

    Args:
        config: The current resolved configuration.
        corpus: Harvested command corpus (logs and/or transcripts).
        min_occurrences: Minimum cluster size to include (default 1).

    Returns:
        A :class:`MiningReport` whose groups are sorted by occurrences (desc),
        then signal priority, then command key.
    """
    # Accumulate per (tool, key, signal).
    buckets: Dict[Tuple[str, str, str], Dict] = {}

    for entry in corpus:
        verdict = decide(config, entry.tool, entry.command).decision
        signal = _classify(verdict, entry.status)
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
        dominant_verdict = bucket["verdicts"].most_common(1)[0][0]
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
# Candidate verification (replay-backed)
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
    The result reports EXACTLY which corpus commands the rule newly admits -- the
    blast radius a user needs to approve the suggestion responsibly.

    Args:
        config: The current configuration.
        tool: The tool the rule applies to.
        pattern: The wrapper-free allow pattern body to add (e.g. ``git push:*``).
        target_provenance: The layer (provenance) to add the rule to.
        corpus: The command corpus to measure against.

    Returns:
        An :class:`AddRuleEffect` with the newly-allowed commands and change counts.
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
        broadened_count=diff.broadened_count,
        tightened_count=diff.tightened_count,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_mining_report(report: MiningReport, fmt: str = "text") -> str:
    """
    Render a :class:`MiningReport` as a human-readable ASCII summary.

    Args:
        report: The report to render.
        fmt: ``'text'`` (default) or ``'markdown'``.

    Returns:
        An ASCII-only sorted summary, allow-candidates and declined commands
        first.

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
