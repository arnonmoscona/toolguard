"""
The auto-mode trace: one JSONL record per governed command/path whose
decision came from a fallback (no configured rule matched, or the ASK
floor's ``undecidable_fallback`` fired) while Claude Code's own
``permission_mode`` was ``'auto'``.

A purpose-built trace of what toolguard defers under auto mode, not a
patch over a deficiency.

**What this answers.** Which command/path SHAPES fall through toolguard's
own pattern coverage while the auto-mode classifier is active, so a human
can review them offline and decide whether new rules are worth writing.
**What it does not answer.** Whether the auto-mode classifier actually
allowed the call -- this is a ``PreToolUse``-only hook, so it sees what
toolguard itself deferred to its own fallback, never the classifier's own
verdict. That is a deliberate scope boundary, not a shortfall of this trace.

**This is a read-only side channel.** Nothing in the decision path reads
this trace, and a write failure here (see :func:`log_auto_mode_trace`)
never changes a verdict. It also does not mean auto-mode commands were
governed more loosely than any other mode's -- toolguard does not yet vary
its fallback behaviour by ``permission_mode`` at all (that is a later
phase); this trace only records where the SAME fallback outcome occurred
while auto mode was active, as a baseline for comparison once it does.

Deliberately in the "observability" architecture layer (config_types.py's
``RuntimeVerdict``/``UnitVerdict`` live one layer up, in "config"): the
caller extracts primitive fields from those into an
:class:`AutoModeTraceEntry` before calling :func:`log_auto_mode_trace`,
exactly as :mod:`toolguard.log_writer`'s ``LogRecord`` does for the main
resolution log.
"""

import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

#: WHY there was a fallback -- never WHAT the outcome was (that is
#: ``decision``, a separate field). Set structurally, at the point of
#: decision, on ``RuntimeVerdict.fallback_cause`` (see that class's own
#: docstring); the trace reads it rather than inferring it from anything
#: else. ``'unknown'`` means genuinely undeterminable -- most commonly the
#: ASK floor itself, or a compound where several allowed leaves would need
#: to agree on a cause and don't. Reporting a wrong cause would corrupt the
#: corpus permanently, since the information to correct it later was never
#: captured; ``'unknown'`` stays honest forever.
#:
#: This is a TRIAGE code: each value implies a different response to an
#: entry a human decides they don't like in retrospect.
#: - 'no_match': toolguard read the target fine; addressable by writing a rule.
#: - 'undecidable': toolguard could not read the target at all -- NO RULE
#:   CAN EVER COVER IT; needs the program-source constraint (spec 4.3) or
#:   auto-mode guidance instead. This is precisely the case where the right
#:   answer is NOT "make toolguard smarter so it can pattern this" -- spec
#:   section 2 names that as the design smell this field exists to let a
#:   reader rule out.
#: - 'parse_failure': toolguard could not read its OWN configuration; fix
#:   the config, not a rule.
#: - 'unknown': not determinable, so not triageable -- investigate the case
#:   rather than assuming either answer.
FALLBACK_CAUSE_NO_MATCH = "no_match"
FALLBACK_CAUSE_UNDECIDABLE = "undecidable"
FALLBACK_CAUSE_PARSE_FAILURE = "parse_failure"
FALLBACK_CAUSE_UNKNOWN = "unknown"


@dataclass(frozen=True)
class AutoModeTraceEntry:
    """
    One auto-mode trace record, built by the caller and passed to
    :func:`log_auto_mode_trace`.

    Attributes:
        tool_name: The governed tool, e.g. ``'Bash'``, ``'Read'``.
        target: The full, untruncated command (Bash) or bare file path
            (Read/Write/Edit) under evaluation -- never wrapped, summarised,
            or normalised, so later analysis can group entries by shape
            without stripping a rendered prefix first.
        decision: ``'allow'``, ``'ask'``, or ``'deny'`` -- the fallback's
            own emitted OUTCOME. Unrelated to ``fallback_cause``: that field
            is about why there was a fallback, never what it decided.
        fallback_cause: Why there was a fallback -- :data:`FALLBACK_CAUSE_UNDECIDABLE`,
            :data:`FALLBACK_CAUSE_PARSE_FAILURE`, :data:`FALLBACK_CAUSE_NO_MATCH`,
            or :data:`FALLBACK_CAUSE_UNKNOWN`.
        permission_mode: Recorded verbatim (always ``'auto'`` today, since
            that is the only mode that triggers a write -- kept as its own
            field rather than assumed, so the trace stays meaningful if the
            trigger ever widens).
        session_id: Claude Code's session identifier, or ``None``.
        cwd: The invocation's working directory, or ``None``.
        agent_info: The agent label, e.g. ``'main'``, or ``None``.
    """

    tool_name: str
    target: str
    decision: str
    fallback_cause: str
    permission_mode: Optional[str]
    session_id: Optional[str]
    cwd: Optional[str]
    agent_info: Optional[str]


def _entry_as_dict(entry: AutoModeTraceEntry) -> dict:
    """Render *entry* as a JSON-ready dict, primitives only, in on-disk key order."""
    return {
        "timestamp": datetime.now().isoformat(),
        "tool_name": entry.tool_name,
        "target": entry.target,
        "decision": entry.decision,
        "fallback_cause": entry.fallback_cause,
        "permission_mode": entry.permission_mode,
        "session_id": entry.session_id,
        "cwd": entry.cwd,
        "agent_info": entry.agent_info,
    }


def log_auto_mode_trace(entry: AutoModeTraceEntry, log_dir: Optional[Path]) -> None:
    """
    Append one auto-mode trace record, if *log_dir* is usable.

    Writes to ``<log_dir>/toolguard-automode-YYYY-MM-DD.jsonl``, one JSON
    object per line -- dated like the error/warning/conflict streams
    (:mod:`toolguard.error_log`), JSONL like :mod:`toolguard.log_writer`'s
    opt-in machine format, so this file needs no schema of its own to
    reconcile. Creates *log_dir* if it does not exist yet, matching
    :mod:`toolguard.error_log`'s sibling streams.

    Never raises: every failure (a *log_dir* that cannot be created, a
    write error) is caught and warned to stderr, exactly like every other
    toolguard log writer -- this is a read-only side channel, and a broken
    one must never change the verdict it is recording.

    Args:
        entry: The record to append.
        log_dir: Directory to write into, or ``None``/falsy (no-op --
            nothing configured to log into for this invocation).
    """
    if not log_dir:
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log_filename = f"toolguard-automode-{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        log_file = log_dir / log_filename
        rendered = json.dumps(_entry_as_dict(entry)) + "\n"
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(rendered)
    except Exception as e:
        print(f"Warning: Failed to write auto-mode trace: {e}", file=sys.stderr)
