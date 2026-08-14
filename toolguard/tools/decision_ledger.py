"""
Prior-decision ledger for the maintenance skill.

A decision taken during a maintenance dialogue that attaches to a *surviving* rule is
recorded on it, as an in-file ``# toolguard:`` annotation. A rejected proposal -- "do NOT
re-suggest merging this family", "do NOT re-suggest promoting these allows to the user
level" -- has **no surviving rule to hang on**, because the thing rejected does not exist
in the config. This module is the store for those, so a periodic run need not re-litigate
them.

Level-scoped like the config hierarchy: a **project** ledger at
``<project_root>/.claude/toolguard_decisions.json`` and a **user** ledger at
``~/.toolguard/decisions.json``. A decision is identified by ``(kind, family_id,
target)`` rather than by which file holds it, so the two can be searched as one
(``load_merged``).

Design rationale: technical-notes.md, "Prior-decision ledger".
"""

import json
from dataclasses import dataclass
from datetime import datetime
from importlib import metadata
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from toolguard.config import find_project_root

#: Schema tag written into every ledger file. ``load_ledger`` does not check it.
LEDGER_SCHEMA = "toolguard-decision-ledger/1"

#: Project-level ledger location, relative to the resolved project root.
PROJECT_LEDGER_RELPATH = Path(".claude") / "toolguard_decisions.json"

#: User-level ledger location -- toolguard's own namespace, deliberately not
#: ``~/.claude``.
USER_LEDGER_PATH = Path.home() / ".toolguard" / "decisions.json"

#: Recognised decision kinds. ``custom`` is the escape hatch for a meta-decision
#: that does not fit the enumerated shapes.
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

#: The recorded disposition. Only ``reject`` suppresses a suggestion (see
#: ``is_suppressed``); ``accept`` and ``defer`` are recorded but do not.
VALID_DECISIONS = frozenset({"reject", "accept", "defer"})

#: Which ledger file stores the decision.
VALID_LEVELS = frozenset({"project", "user"})


class LedgerError(Exception):
    """Raised when a ledger file is present but malformed or invalid.

    A missing ledger is normal and loads as empty. A corrupt one raises instead of
    loading as empty, since dropping settled decisions silently re-opens them.
    """


def decision_id(kind: str, family_id: str, target: str) -> str:
    """Return the stable, human-readable identity of a decision.

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
        recorded_at: Local ISO timestamp; ``""`` on an entry loaded from a file
            that omitted it.
        toolguard_version: Version that recorded it, or ``"unknown"``.
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
    """Return the installed distribution version, or ``"unknown"`` if not installed."""
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

    ``level`` is a property of the enclosing file, so :func:`ledger_to_dict` writes it
    once there rather than on every entry.
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
    """Serialise a whole ledger file for ``level``, in the order given."""
    return {
        "schema": LEDGER_SCHEMA,
        "level": level,
        "decisions": [decision_to_dict(d) for d in decisions],
    }


def project_ledger_path(project_dir: Path) -> Path:
    """Return the project-level ledger path for ``project_dir``.

    When no project root is found the ledger is anchored at ``project_dir`` itself,
    so a record still lands somewhere sensible.
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

    Each decision's ``level`` comes from WHICH FILE was read (``path`` matching
    :data:`USER_LEDGER_PATH` means ``user``, anything else means ``project``),
    never from the file's own ``level`` field -- that field is untrusted
    content and is ignored, so a project ledger cannot claim ``user`` and
    redirect a later write there.

    Args:
        path: The ledger file to read.

    Returns:
        The parsed decisions, or an empty tuple if the file does not exist.

    Raises:
        LedgerError: If the file exists but cannot be read, or is not a valid ledger.
    """
    if not path.exists():
        return ()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LedgerError(f"cannot read decision ledger {path}: {exc}") from exc
    if not isinstance(data, dict) or "decisions" not in data:
        raise LedgerError(f"decision ledger {path} is missing a 'decisions' array")
    level = "user" if Path(path) == Path(USER_LEDGER_PATH) else "project"
    entries = data["decisions"]
    if not isinstance(entries, list):
        raise LedgerError(f"decision ledger {path}: 'decisions' must be an array")
    return tuple(decision_from_dict(entry, level) for entry in entries)


def load_merged(project_dir: Path) -> Tuple[LedgerDecision, ...]:
    """Load the project and user ledgers for ``project_dir``, the project file first.

    Both files are optional; a missing one contributes nothing.
    """
    project = load_ledger(project_ledger_path(Path(project_dir)))
    user = load_ledger(USER_LEDGER_PATH)
    return project + user


def find_decision(
    decisions: Sequence[LedgerDecision], kind: str, family_id: str, target: str
) -> Optional[LedgerDecision]:
    """Return the decision matching ``(kind, family_id, target)``, if any.

    Matches on identity regardless of disposition; the caller inspects
    :attr:`LedgerDecision.decision` itself. Use :func:`is_suppressed` for the
    common "should I stay silent?" check.
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
    """Write ``decision`` into its level's ledger file, creating the file if needed.

    Idempotent by :attr:`LedgerDecision.id`: a same-id entry is replaced rather than
    duplicated, and the replacement is written last.

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
