"""
THE KEYSTONE: decision-replay diff for toolguard config safety verification.

Given a harvested corpus of real commands (from :mod:`toolguard.tools.log_harvest`)
and two configurations (A = current, B = proposed), this module recomputes each
entry's permission decision under both configs via
:func:`~toolguard.tools.decision.decide` and produces a structured
:class:`ReplayDiff` classifying every change.

Classification
--------------
Each entry is classified by the *strictness order* ``deny > ask > allow``:

- ``unchanged``:  verdict_A == verdict_B.
- ``tightened``:  B is STRICTER than A (allow -> ask, allow -> deny, ask -> deny).
  Tightening is SAFE from a security perspective (fewer things are permitted).
- ``broadened``:  B is LOOSER than A (deny -> ask, deny -> allow, ask -> allow).
  Broadening is the direction to WATCH: it permits something previously blocked.

Safety note
-----------
The alembic landmine (mentioned in the design doc) is an example of an unexpected
broadening: ``uv run alembic <sub>:*`` rules in ``allow`` coexist with
``uv run alembic:*`` in ``ask``; a naive consolidation of the allow rules into
``uv run alembic:*`` would silently turn the ``ask`` into ``allow`` for ALL
alembic commands, including dangerous ones.  Replay catches this because the
alembic commands recorded in the log would change from ``ask``->``allow`` in the
diff and appear in the ``broadened`` bucket.

Single-config mode
------------------
When only one configuration is provided, :func:`replay_single` returns per-entry
decisions without a diff (useful for redundancy analysis and other single-config
inspections).
"""

from dataclasses import dataclass, field
from typing import Dict, List

from toolguard.config import Configuration
from toolguard.config_types import RuntimeVerdict
from toolguard.constants import STATUS_EXECUTED, STATUS_REFUSED
from toolguard.tools.decision import decide
from toolguard.tools.log_harvest import LogEntry


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

# Strictness order: higher = stricter (fewer things allowed)
_STRICTNESS: Dict[str, int] = {"allow": 0, "ask": 1, "deny": 2}


def classify_change(verdict_a: str, verdict_b: str) -> str:
    """
    Classify a verdict change from config A to config B.

    Uses the strictness ordering ``allow (0) < ask (1) < deny (2)``.
    Unknown verdict strings are treated as having strictness 0 (least strict)
    so they do not silently mask a broadening.

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

    The ``diffs`` list contains one :class:`EntryDiff` per corpus entry.
    The counts give a quick summary without iterating.

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
        """Return only the broadened entries (B is looser than A)."""
        return [d for d in self.diffs if d.classification == "broadened"]

    def tightened(self) -> List[EntryDiff]:
        """Return only the tightened entries (B is stricter than A)."""
        return [d for d in self.diffs if d.classification == "tightened"]

    def unchanged(self) -> List[EntryDiff]:
        """Return only the unchanged entries (verdict same under A and B)."""
        return [d for d in self.diffs if d.classification == "unchanged"]


@dataclass(frozen=True)
class SingleDecision:
    """
    Per-entry result of a single-config decision replay.

    Attributes:
        entry: The original :class:`~toolguard.tools.log_harvest.LogEntry`.
        decision: The verdict under the single config.
        matches_observed: Whether the replayed verdict matches the status
            recorded in the log (``True`` when the log says ``EXECUTED`` and
            the replay yields ``allow``, or the log says ``REFUSED`` and replay
            yields ``deny`` or ``ask``).
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

    For each entry in ``corpus``, :func:`~toolguard.tools.decision.decide` is
    called under both ``config_a`` and ``config_b``, the verdicts are compared,
    and the entry is classified as ``unchanged``, ``tightened``, or
    ``broadened``.

    This is the core safety primitive: a proposed config change is safe (from a
    security perspective) when the diff contains no ``broadened`` entries; or,
    when broadening is intentional, the caller can inspect exactly which commands
    are newly admitted.

    Args:
        corpus: List of :class:`~toolguard.tools.log_harvest.LogEntry` records
            to evaluate.  Typically produced by
            :func:`~toolguard.tools.log_harvest.harvest`.
        config_a: The baseline configuration (e.g. current config).
        config_b: The proposed configuration (e.g. after a rule change).
        extended_syntax: Whether to honour ``[regex]``/``[glob]``/``[native]``
            prefixes.  Should match the setting used in production.

    Returns:
        A :class:`ReplayDiff` with per-entry results and summary counts.
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

    Useful for single-config analysis such as redundancy checking (does removing
    a rule change any corpus decision?) or log-consistency checking (does the
    replay agree with what was actually observed?).

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

    ``EXECUTED`` corresponds to ``allow``; ``REFUSED`` corresponds to ``deny``
    or ``ask`` (the hook returns ask to Claude as a permission request, but a
    refusal in the log means the user declined or the hook denied it).  Unknown
    status values return ``False``.

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
    return False
