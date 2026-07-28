"""
Prior-decision ledger for the maintenance skill (TOO-15 Phase C).

The maintenance skill is a dialogue: the user accepts, rejects, or modifies each
proposed rule change. Some of those decisions attach to a *surviving* rule and are
best recorded as an in-file ``# toolguard:`` annotation (see
:mod:`toolguard.tools.annotate`). But a decision such as "do NOT re-suggest merging
this family" or "do NOT re-suggest promoting these allows to the user level" has **no
surviving rule to hang on** -- the thing the user rejected does not exist in the
config. Without a durable record, every periodic maintenance run would re-litigate it.

This module is the canonical, tool-owned store for those meta-decisions. It is
deliberately NOT outsourced to an arbitrary human-memory system: the maintenance skill
re-parses it mechanically on every run to decide what is already settled, so it needs a
stable schema and a stable location.

Location mirrors the config hierarchy (decisions are level-scoped like the rules):

- **project** ledger travels with the repo at ``<project_root>/.claude/toolguard_decisions.json``
  (git-tracked, so a project's settled decisions follow the code);
- **user** ledger lives under toolguard's own namespace at ``~/.toolguard/decisions.json``.

A decision is *identified* by what it is about -- ``(kind, family_id, target)`` -- not
by where it is stored, so the same suppression recorded at either level answers a
"is this settled?" query. Writes replace an existing same-id entry in place (idempotent).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from toolguard.config import find_project_root

#: Schema tag written into every ledger file so a future format change is detectable.
LEDGER_SCHEMA = "toolguard-decision-ledger/1"

#: Project-level ledger location, relative to the resolved project root.
PROJECT_LEDGER_RELPATH = Path(".claude") / "toolguard_decisions.json"

#: User-level ledger location (toolguard's own namespace, not ``~/.claude``).
USER_LEDGER_PATH = Path.home() / ".toolguard" / "decisions.json"

#: Decision kinds the skill records. ``custom`` is the escape hatch for a
#: meta-decision that does not fit the enumerated shapes.
VALID_KINDS = frozenset(
    {
        "reject-consolidation",  # do not re-propose merging this family
        "reject-promotion",  # do not re-propose promoting to another level
        "reject-broadening",  # do not re-propose widening what is permitted
        "reject-removal",  # keep a rule the tool called redundant
        "intentional-scope",  # this rule is deliberately kept at its level
        "custom",
    }
)

#: The recorded disposition. ``reject`` is the one that suppresses a re-raise;
#: ``accept`` records that a change was taken; ``defer`` parks it for later.
VALID_DECISIONS = frozenset({"reject", "accept", "defer"})

#: Which ledger file stores the decision.
VALID_LEVELS = frozenset({"project", "user"})


class LedgerError(Exception):
    """Raised when a ledger file is present but malformed or invalid.

    A missing ledger is normal (returns empty); a *corrupt* one is surfaced rather
    than silently dropped, because silently losing settled decisions would cause the
    skill to re-litigate them -- the exact failure this module exists to prevent.
    """


def decision_id(kind: str, family_id: str, target: str) -> str:
    """Return the stable, human-readable identity of a decision.

    Identity is independent of which level stores the decision, so a suppression
    recorded at either level matches the same future suggestion.

    Args:
        kind: One of :data:`VALID_KINDS`.
        family_id: The command-family slug the decision is about.
        target: A canonical string describing what specifically was decided (e.g.
            the proposed consolidation pattern, or ``"promote:user"``).

    Returns:
        A ``kind::family_id::target`` slug used for matching and de-duplication.
    """
    return f"{kind}::{family_id}::{target}"


@dataclass(frozen=True)
class LedgerDecision:
    """A single settled maintenance decision.

    Attributes:
        kind: One of :data:`VALID_KINDS`.
        family_id: The command-family slug the decision concerns.
        target: Canonical description of the specific thing decided.
        decision: One of :data:`VALID_DECISIONS`.
        rationale: The user's own words for why (may be empty).
        recorded_at: Local ISO timestamp when the decision was recorded.
        toolguard_version: Version of toolguard that recorded it (provenance).
        level: Which ledger stores it -- one of :data:`VALID_LEVELS`.
    """

    kind: str
    family_id: str
    target: str
    decision: str
    rationale: str
    recorded_at: str
    toolguard_version: str
    level: str

    @property
    def id(self) -> str:
        """The stable :func:`decision_id` for this decision."""
        return decision_id(self.kind, self.family_id, self.target)


def _toolguard_version() -> str:
    """Return the installed toolguard version, or ``"unknown"`` if undeterminable."""
    try:
        return metadata.version("toolguard")
    except metadata.PackageNotFoundError:
        return "unknown"


def new_decision(
    kind: str,
    family_id: str,
    target: str,
    decision: str,
    rationale: str,
    level: str,
    *,
    recorded_at: Optional[str] = None,
    toolguard_version: Optional[str] = None,
) -> LedgerDecision:
    """Build a validated :class:`LedgerDecision`, stamping time and version.

    Args:
        kind: One of :data:`VALID_KINDS`.
        family_id: The command-family slug.
        target: Canonical description of what was decided.
        decision: One of :data:`VALID_DECISIONS`.
        rationale: The user's reasoning (may be empty).
        level: One of :data:`VALID_LEVELS`.
        recorded_at: Override the timestamp (defaults to local now, seconds).
        toolguard_version: Override the version (defaults to the installed one).

    Returns:
        A frozen, validated :class:`LedgerDecision`.

    Raises:
        LedgerError: If ``kind``, ``decision``, or ``level`` is not recognised.
    """
    _validate_enums(kind, decision, level)
    return LedgerDecision(
        kind=kind,
        family_id=family_id,
        target=target,
        decision=decision,
        rationale=rationale,
        recorded_at=recorded_at or datetime.now().isoformat(timespec="seconds"),
        toolguard_version=toolguard_version or _toolguard_version(),
        level=level,
    )


def _validate_enums(kind: str, decision: str, level: str) -> None:
    """Raise :class:`LedgerError` if any enum-valued field is unrecognised."""
    if kind not in VALID_KINDS:
        raise LedgerError(
            f"unknown decision kind {kind!r}; expected one of {sorted(VALID_KINDS)}"
        )
    if decision not in VALID_DECISIONS:
        raise LedgerError(
            f"unknown decision {decision!r}; expected one of {sorted(VALID_DECISIONS)}"
        )
    if level not in VALID_LEVELS:
        raise LedgerError(
            f"unknown level {level!r}; expected one of {sorted(VALID_LEVELS)}"
        )


def decision_to_dict(decision: LedgerDecision) -> dict:
    """Serialise a :class:`LedgerDecision` to a JSON-ready dict (no ``level``).

    The ``level`` is a property of the enclosing file, not of the entry, so it is
    written once at the file level (see :func:`ledger_to_dict`) rather than repeated
    on every decision.
    """
    return {
        "id": decision.id,
        "kind": decision.kind,
        "family_id": decision.family_id,
        "target": decision.target,
        "decision": decision.decision,
        "rationale": decision.rationale,
        "recorded_at": decision.recorded_at,
        "toolguard_version": decision.toolguard_version,
    }


def decision_from_dict(data: dict, level: str) -> LedgerDecision:
    """Deserialise one decision dict from a ledger file at ``level``.

    Args:
        data: The per-entry mapping (``id`` is derived, not trusted).
        level: The level of the enclosing ledger file.

    Returns:
        The parsed :class:`LedgerDecision`.

    Raises:
        LedgerError: If a required field is missing or an enum is unrecognised.
    """
    try:
        kind = data["kind"]
        family_id = data["family_id"]
        target = data["target"]
        decision = data["decision"]
    except (KeyError, TypeError) as exc:
        raise LedgerError(f"malformed ledger decision entry: {data!r}") from exc
    _validate_enums(kind, decision, level)
    return LedgerDecision(
        kind=kind,
        family_id=family_id,
        target=target,
        decision=decision,
        rationale=data.get("rationale", ""),
        recorded_at=data.get("recorded_at", ""),
        toolguard_version=data.get("toolguard_version", "unknown"),
        level=level,
    )


def ledger_to_dict(decisions: Sequence[LedgerDecision], level: str) -> dict:
    """Serialise a whole ledger file for ``level``.

    Args:
        decisions: The decisions to write (order preserved).
        level: The level the file represents.

    Returns:
        A mapping with the schema tag, level, and serialised decisions.
    """
    return {
        "schema": LEDGER_SCHEMA,
        "level": level,
        "decisions": [decision_to_dict(d) for d in decisions],
    }


def project_ledger_path(project_dir: Path) -> Path:
    """Return the project-level ledger path for ``project_dir``.

    Resolves the project root the same way config discovery does (nearest
    ``.git``/``pyproject.toml``); if no root is found the ledger is anchored at
    ``project_dir`` itself so a record still lands somewhere sensible.
    """
    start = Path(project_dir)
    try:
        root = find_project_root(start)
    except RuntimeError:
        root = start
    return root / PROJECT_LEDGER_RELPATH


def ledger_path_for_level(level: str, project_dir: Path) -> Path:
    """Return the ledger file path for ``level`` (``project`` or ``user``).

    Raises:
        LedgerError: If ``level`` is not one of :data:`VALID_LEVELS`.
    """
    if level == "user":
        return USER_LEDGER_PATH
    if level == "project":
        return project_ledger_path(project_dir)
    raise LedgerError(
        f"unknown level {level!r}; expected one of {sorted(VALID_LEVELS)}"
    )


def load_ledger(path: Path) -> Tuple[LedgerDecision, ...]:
    """Load decisions from a single ledger file.

    Args:
        path: The ledger file to read.

    Returns:
        The parsed decisions, or an empty tuple if the file does not exist.

    Raises:
        LedgerError: If the file exists but is not valid JSON or not a valid ledger.
    """
    if not path.exists():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read decision ledger {path}: {exc}") from exc
    if not isinstance(data, dict) or "decisions" not in data:
        raise LedgerError(f"decision ledger {path} is missing a 'decisions' array")
    level = data.get("level", "project")
    entries = data["decisions"]
    if not isinstance(entries, list):
        raise LedgerError(f"decision ledger {path}: 'decisions' must be an array")
    return tuple(decision_from_dict(entry, level) for entry in entries)


def load_merged(project_dir: Path) -> Tuple[LedgerDecision, ...]:
    """Load and concatenate the project and user ledgers for ``project_dir``.

    Project decisions come first, then user decisions. Both files are optional; a
    missing file contributes nothing.

    Args:
        project_dir: Directory to resolve the project ledger from.

    Returns:
        All decisions across both levels.
    """
    project = load_ledger(project_ledger_path(Path(project_dir)))
    user = load_ledger(USER_LEDGER_PATH)
    return project + user


def find_decision(
    decisions: Sequence[LedgerDecision], kind: str, family_id: str, target: str
) -> Optional[LedgerDecision]:
    """Return the decision matching ``(kind, family_id, target)``, if any.

    Matches on identity regardless of disposition; the caller inspects
    :attr:`LedgerDecision.decision` (use :func:`is_suppressed` for the common
    "should I stay silent?" check).
    """
    wanted = decision_id(kind, family_id, target)
    for decision in decisions:
        if decision.id == wanted:
            return decision
    return None


def is_suppressed(
    decisions: Sequence[LedgerDecision], kind: str, family_id: str, target: str
) -> bool:
    """Whether a settled ``reject`` suppresses re-raising this suggestion.

    Returns ``True`` only when a matching decision exists AND its disposition is
    ``reject``; an ``accept`` or ``defer`` does not silence a fresh suggestion.
    """
    match = find_decision(decisions, kind, family_id, target)
    return match is not None and match.decision == "reject"


def record_decision(project_dir: Path, decision: LedgerDecision) -> Path:
    """Append (or replace in place) ``decision`` in its level's ledger file.

    The write is idempotent by :attr:`LedgerDecision.id`: recording a decision whose
    id already exists replaces that entry rather than duplicating it. The parent
    directory is created if needed.

    Args:
        project_dir: Directory used to resolve a project-level ledger path.
        decision: The decision to persist (its ``level`` selects the file).

    Returns:
        The path of the ledger file written.

    Raises:
        LedgerError: If the target ledger exists but is malformed.
    """
    path = ledger_path_for_level(decision.level, Path(project_dir))
    existing: List[LedgerDecision] = [
        d for d in load_ledger(path) if d.id != decision.id
    ]
    existing.append(decision)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(ledger_to_dict(existing, decision.level), indent=2) + "\n",
        encoding="utf-8",
    )
    return path
