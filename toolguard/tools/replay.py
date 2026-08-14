"""
Decision-replay diff for toolguard config safety verification.

Given a harvested corpus of real commands and two configurations (A = current,
B = proposed), recompute each entry's permission decision under both and classify
every change by the *strictness order* ``deny > ask > allow``:

- ``unchanged``:  verdict_A == verdict_B.
- ``tightened``:  B is stricter (allow -> ask, allow -> deny, ask -> deny).
- ``broadened``:  B is looser (deny -> ask, deny -> allow, ask -> allow).

What a replay does and does not establish
-----------------------------------------
It evaluates the corpus and nothing else.  An empty ``broadened`` bucket means no
command IN THE CORPUS is newly permitted; it is not evidence that B is no broader
than A.  A widening that B introduces stays invisible here unless a command it
newly admits happens to be in the corpus.
"""

from dataclasses import dataclass, field
from typing import Dict, List

from toolguard.api import decide
from toolguard.config import Configuration
from toolguard.config_types import RuntimeVerdict
from toolguard.constants import STATUS_ASK, STATUS_EXECUTED, STATUS_REFUSED
from toolguard.tools.log_harvest import LogEntry


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

#: Strictness order for verdict comparison: higher = stricter.
_STRICTNESS: Dict[str, int] = {"allow": 0, "ask": 1, "deny": 2}


def classify_change(verdict_a: str, verdict_b: str) -> str:
    """
    Classify a verdict change from config A to config B.

    A verdict string outside :data:`_STRICTNESS` ranks as ``allow`` (0).  Since
    nothing ranks below 0, an unrecognised *verdict_a* can never yield
    ``'broadened'``.

    Args:
        verdict_a: Verdict under config A (``'allow'``, ``'ask'``, or ``'deny'``).
        verdict_b: Verdict under config B (``'allow'``, ``'ask'``, or ``'deny'``).

    Returns:
        One of ``'unchanged'``, ``'tightened'``, or ``'broadened'``.
    """
    sa = _STRICTNESS.get(verdict_a, 0)
    sb = _STRICTNESS.get(verdict_b, 0)
    if sa == sb:
        return "unchanged"
    if sb > sa:
        return "tightened"
    return "broadened"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntryDiff:
    """
    Per-entry result of a two-config decision replay.

    Attributes:
        entry: The original :class:`~toolguard.tools.log_harvest.LogEntry`.
        decision_a: Verdict under config A.
        decision_b: Verdict under config B.
        classification: ``'unchanged'``, ``'tightened'``, or ``'broadened'``.
    """

    entry: LogEntry
    decision_a: RuntimeVerdict
    decision_b: RuntimeVerdict
    classification: str


@dataclass
class ReplayDiff:
    """
    Structured result of replaying a corpus against two configurations.

    Attributes:
        diffs: Per-entry diff results, in corpus order.
        unchanged_count: Number of entries where the verdict did not change.
        tightened_count: Number of entries where B is stricter than A.
        broadened_count: Number of entries where B is looser than A.
    """

    diffs: List[EntryDiff] = field(default_factory=list)
    unchanged_count: int = 0
    tightened_count: int = 0
    broadened_count: int = 0

    @property
    def total_count(self) -> int:
        """Total number of entries evaluated."""
        return len(self.diffs)

    def broadened(self) -> List[EntryDiff]:
        """Return only the broadened entries."""
        return [d for d in self.diffs if d.classification == "broadened"]

    def tightened(self) -> List[EntryDiff]:
        """Return only the tightened entries."""
        return [d for d in self.diffs if d.classification == "tightened"]

    def unchanged(self) -> List[EntryDiff]:
        """Return only the unchanged entries."""
        return [d for d in self.diffs if d.classification == "unchanged"]


@dataclass(frozen=True)
class SingleDecision:
    """
    Per-entry result of a single-config decision replay.

    Attributes:
        entry: The original :class:`~toolguard.tools.log_harvest.LogEntry`.
        decision: The verdict under the single config.
        matches_observed: Whether the replayed verdict corroborates the status
            recorded in the log -- see :func:`_verdict_matches_status`, which
            decides it and lists what ``False`` does and does not mean.
    """

    entry: LogEntry
    decision: RuntimeVerdict
    matches_observed: bool


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def replay(
    corpus: List[LogEntry],
    config_a: Configuration,
    config_b: Configuration,
    extended_syntax: bool = True,
) -> ReplayDiff:
    """
    Replay a corpus against two configurations and return the decision diff.

    Args:
        corpus: List of :class:`~toolguard.tools.log_harvest.LogEntry` records
            to evaluate.
        config_a: The baseline configuration (e.g. current config).
        config_b: The proposed configuration (e.g. after a rule change).
        extended_syntax: Whether to honour ``[regex]``/``[glob]``/``[native]``
            prefixes.  Should match the setting used in production.

    Returns:
        A :class:`ReplayDiff` with per-entry results and summary counts, covering
        the corpus only -- see the module docstring for what that does not prove.
    """
    result = ReplayDiff()

    for entry in corpus:
        da = decide(config_a, entry.tool, entry.command, extended_syntax)
        db = decide(config_b, entry.tool, entry.command, extended_syntax)
        classification = classify_change(da.decision, db.decision)

        diff = EntryDiff(
            entry=entry,
            decision_a=da,
            decision_b=db,
            classification=classification,
        )
        result.diffs.append(diff)

        if classification == "unchanged":
            result.unchanged_count += 1
        elif classification == "tightened":
            result.tightened_count += 1
        else:
            result.broadened_count += 1

    return result


def replay_single(
    corpus: List[LogEntry],
    config: Configuration,
    extended_syntax: bool = True,
) -> List[SingleDecision]:
    """
    Replay a corpus against a single configuration.

    Args:
        corpus: List of :class:`~toolguard.tools.log_harvest.LogEntry` records.
        config: The configuration to evaluate against.
        extended_syntax: Whether to honour extended prefixes.

    Returns:
        List of :class:`SingleDecision` records, one per corpus entry, in
        corpus order.
    """
    results: List[SingleDecision] = []

    for entry in corpus:
        d = decide(config, entry.tool, entry.command, extended_syntax)
        matches = _verdict_matches_status(d.decision, entry.status)
        results.append(
            SingleDecision(entry=entry, decision=d, matches_observed=matches)
        )

    return results


def _verdict_matches_status(verdict: str, status: str) -> bool:
    """
    Check whether a replayed verdict is consistent with the observed log status.

    ``EXECUTED`` corroborates ``allow``; ``REFUSED`` corroborates ``deny`` or
    ``ask``; ``ASK`` -- toolguard's own hook prompting -- corroborates
    ``ask``.  The comparison is case-insensitive, and EVERY other status --
    ``ERROR``, ``UNKNOWN``, anything unrecognised -- returns ``False``.
    A ``False`` therefore reads as "not corroborated", never as "the config and
    the log disagree".

    Args:
        verdict: Replayed verdict (``'allow'``, ``'ask'``, or ``'deny'``).
        status: Status string from the log (e.g. ``'EXECUTED'``, ``'REFUSED'``).

    Returns:
        ``True`` when the verdict is consistent with the observed status.
    """
    status_upper = status.upper()
    if status_upper == STATUS_EXECUTED:
        return verdict == "allow"
    if status_upper == STATUS_REFUSED:
        return verdict in ("deny", "ask")
    if status_upper == STATUS_ASK:
        return verdict == "ask"
    return False
