"""
Toolguard automation tooling sub-package.

This package provides deterministic Python helpers for the toolguard skills
and config tooling (TOO-15/TOO-11). It is intentionally segregated from the
core hook logic so that automation tooling concerns do not bleed into the
runtime permission evaluation path.

Modules
-------
config_access
    Thin facade over :class:`~toolguard.config.Configuration` for skills that
    need to inspect the config hierarchy without interacting with hook internals.
log_harvest
    Parse daily toolguard log files (``logs/toolguard-YYYY-MM-DD.md``) into a
    structured corpus of :class:`~toolguard.tools.log_harvest.LogEntry` records.
replay
    THE KEYSTONE: given a harvested corpus and two configurations (A=current,
    B=proposed), recompute each entry's decision under each config via
    :func:`~toolguard.api.decide` and produce a structured diff
    classifying each change as ``unchanged``, ``tightened``, or ``broadened``.
    The diff is the safety verifier the config-maintenance skill relies on.
redundancy
    Detect redundant permission rules: (1) static exact/normalised-equal
    duplicates within a tool's allow/deny/ask list; (2) corpus-backed
    subsumption -- a rule whose removal changes no decision in a harvested
    command corpus.
danger
    Ranked static risk findings over toolguard allow rules: arbitrary code
    execution, destructive commands, secrets exposure, unanchored regex allows,
    and blanket allows outside the takeover ignored set.  Takeover-mode-aware.
takeover_audit
    Verify takeover-mode invariants: hook registration, enabled-conflict +
    blanket allows, uncovered blanket allows, and loose no_match_fallback.
    A correctly-configured takeover setup yields no findings.
sorters
    Deterministic stable canonical sort of tool rule arrays (by pattern type
    then normalised body).  In-memory only; file rewriting is P2.
"""
