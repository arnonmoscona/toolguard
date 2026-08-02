"""
Toolguard SessionStart Hook for Claude Code.

This hook runs at the start of every Claude Code session and surfaces any
configuration conflicts that are present so the agent (and user) become aware
of them immediately. Claude Code injects SessionStart stdout directly into the
session context, so printing a summary here makes it visible to the agent.

Two sources of conflict are checked:

1. **Static conflicts** (recomputed live): ``config.takeover_mode().conflict``
   detects a cross-level disagreement on ``takeover_mode.enabled`` in real time.
   The check self-clears when the configuration is fixed -- no stale state.

2. **Dynamic conflicts** (previously recorded): the conflict log file(s) in
   ``logs/toolguard-conflict-YYYY-MM-DD.md`` accumulate allow-over-deny overrides
   that can only be detected at tool-use time (when an actual command is evaluated).
   The most recent file with recorded entries is surfaced here.

The hook nags every session while conflicts remain. There is no deduplication
marker: persistent nagging is intentional to encourage resolution.

A THIRD, unrelated check runs alongside the two above (TOO-19): whether the
toolguard governing this machine is a shadowed source checkout, or a properly
installed copy that has drifted from its own checkout. See
:func:`_detect_shadow_status` and :mod:`toolguard.install_provenance` for the
detection primitives, and ``docs/security.md`` ("The hook can be silently
shadowed") for the full rationale. Both messages are gated on the ACTIVE
session's project being toolguard's own source repo -- meaningless for any
other project, so they stay silent there.

Input: JSON via stdin (SessionStart shape -- ``hook_event_name``, ``cwd``,
       ``session_id``; NO ``tool_name`` / ``tool_input`` fields).
Output: A short conflict summary on stdout when conflicts exist; nothing otherwise.
Exit code: Always 0 (a SessionStart hook must never block the session).
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from toolguard import install_provenance
from toolguard.config import Configuration, load_configuration


def _parse_session_start_input() -> dict:
    """
    Parse the SessionStart JSON payload from stdin.

    The SessionStart payload has ``hook_event_name``, ``session_id``, and ``cwd``
    but does NOT have ``tool_name`` or ``tool_input``. This parser is intentionally
    lenient: it falls back gracefully on missing or malformed input rather than
    raising, because a broken SessionStart hook must never block a session.

    Returns:
        Parsed JSON data as a dictionary, or an empty dict on failure.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _recent_conflict_logs(log_dir: Path) -> list:
    """
    Return existing ``toolguard-conflict-*.md`` files, most recent first.

    Sorts by filename descending; a lexicographic sort on the date suffix is
    correct because dates are in ``YYYY-MM-DD`` ISO format. Returns an empty list
    when ``log_dir`` does not exist or contains no conflict log files.

    Args:
        log_dir: Directory to search for conflict log files.

    Returns:
        List of conflict-log Paths, most recent first (possibly empty).
    """
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("toolguard-conflict-*.md"), reverse=True)


def _count_conflict_entries(log_file: Path) -> int:
    """
    Count the number of conflict entries recorded in a conflict log file.

    Each entry written by :func:`toolguard.error_log.log_conflict` begins with a
    Markdown heading of the form ``## YYYY-MM-DD HH:MM:SS - CONFLICT``. Counting
    lines that match this pattern gives the entry count without a full parse.

    Args:
        log_file: Path to a ``toolguard-conflict-*.md`` file.

    Returns:
        Number of entries found, or 0 if the file cannot be read.
    """
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            return sum(
                1 for line in f if line.startswith("## ") and "- CONFLICT" in line
            )
    except Exception:
        return 0


def _check_dynamic_conflicts(log_dir: Optional[Path]):
    """
    Check for previously recorded dynamic conflicts in the conflict log.

    Walks the conflict-log files in ``log_dir`` from most recent to least recent
    and returns a description of the FIRST one that has recorded entries. Walking
    (rather than only inspecting the single most-recent file) matters because an
    empty current-day log must not shadow an older log that still has unresolved
    conflicts -- the nag should persist until they are actually cleared.

    Args:
        log_dir: The directory to search for conflict log files, or None.

    Returns:
        Tuple of ``(relative_path_str, entry_count)`` describing the conflict log,
        or None when no recorded dynamic conflicts exist.
    """
    if log_dir is None:
        return None
    for log_file in _recent_conflict_logs(log_dir):
        count = _count_conflict_entries(log_file)
        if count == 0:
            continue
        # Express the path relative to the log dir's parent (the project root) for
        # a concise, human-readable display. Fall back to the absolute path when the
        # relationship cannot be established.
        try:
            display_path = log_file.relative_to(log_dir.parent)
        except ValueError:
            display_path = log_file
        return str(display_path), count
    return None


def _format_summary(
    static_conflict,
    dynamic_conflict,
    broken_files=(),
    shadow_status: Optional[ShadowStatus] = None,
) -> str:
    """
    Format a brief conflict/broken-config/shadow-status summary for stdout.

    Produces a short, human-readable summary for injection into the Claude
    Code session context, built from up to four independent sections:

    - A broken-config section (TOO-19) when *broken_files* is non-empty:
      names each broken file with its parse error and states that toolguard
      is falling back to ``ask`` for every tool call. This is unconditional
      -- it does not depend on either conflict argument.
    - The pre-existing conflict-detected section when *static_conflict* or
      *dynamic_conflict* is not None: a header line, one bullet per conflict
      source, and a closing action prompt -- byte-identical to this
      function's behaviour before *broken_files* was added.
    - A "running from a source tree" section (TOO-19) when
      *shadow_status* is given and ``shadow_status.running_from_checkout``
      is True: names both the governing and installed paths.
    - A "stale install" section (TOO-19) when *shadow_status* is given and
      ``shadow_status.stale`` is True: names both paths and the reinstall
      command. Independent of the section above -- either, neither, or both
      may fire.

    When every input is absent, the result is an empty string (callers only
    print when at least one is present).

    Args:
        static_conflict: A ``TakeoverEnabledConflict`` describing cross-level
            disagreement on ``takeover_mode.enabled``, or None.
        dynamic_conflict: A ``(path_str, count)`` tuple for the most recent
            conflict log file with recorded entries, or None.
        broken_files: ``(path, message)`` pairs for governed config files that
            failed to parse (:attr:`~toolguard.config.Configuration.parse_failures`,
            TOO-19). Defaults to ``()`` so existing 2-argument call sites are
            unaffected.
        shadow_status: A :class:`ShadowStatus` (see :func:`_detect_shadow_status`),
            or ``None`` so existing call sites are unaffected.

    Returns:
        A multi-line string suitable for printing to stdout, or "" when
        there is nothing to report.
    """
    sections = []

    if broken_files:
        broken_lines = [
            "toolguard: CONFIG BROKEN -- falling back to ASK for every tool "
            "call until fixed --"
        ]
        for path, message in broken_files:
            broken_lines.append(f"  - {path}: {message}")
        broken_lines.append(
            "  Rules in these file(s) -- including deny/hard_deny -- are NOT "
            "enforced. Fix them to restore normal permission handling."
        )
        sections.append("\n".join(broken_lines))

    if static_conflict is not None or dynamic_conflict is not None:
        conflict_lines = ["toolguard: configuration conflicts detected --"]

        if static_conflict is not None:
            # Build a compact provenance string: cite the first disagreeing
            # source so the human knows where to look, without flooding the
            # session context.
            provenance_parts = [
                f"{value} [{prov.describe_brief()}]"
                for value, prov in static_conflict.sources
            ]
            provenance_summary = "; ".join(provenance_parts)
            conflict_lines.append(
                f"  - takeover_mode.enabled disagrees across levels; "
                f"failed safe to OFF ({provenance_summary})"
            )

        if dynamic_conflict is not None:
            path_str, count = dynamic_conflict
            noun = "entry" if count == 1 else "entries"
            conflict_lines.append(
                f"  - conflict log {path_str} has {count} recorded {noun}"
            )

        conflict_lines.append("Review and resolve; see the conflict log for details.")
        sections.append("\n".join(conflict_lines))

    if shadow_status is not None and shadow_status.running_from_checkout:
        installed_desc = (
            str(shadow_status.installed_root)
            if shadow_status.installed_root is not None
            else "(no installed distribution found)"
        )
        sections.append(
            "toolguard: RUNNING FROM A SOURCE TREE, NOT THE INSTALLED "
            "DISTRIBUTION --\n"
            f"  governing:  {shadow_status.checkout_root / 'toolguard'}\n"
            f"  installed:  {installed_desc}\n"
            "  Every toolguard invocation sharing this environment is "
            "currently using UNREVIEWED code from this checkout instead of "
            "the installed release -- including the PreToolUse permission "
            "hook, which is making every allow/deny/ask decision from it. "
            "See docs/security.md ('The hook can be silently shadowed') for "
            "how this happens and how to fix it."
        )

    if shadow_status is not None and shadow_status.stale:
        sections.append(
            "toolguard: INSTALLED COPY IS STALE --\n"
            f"  checkout:   {shadow_status.checkout_root}\n"
            f"  installed:  {shadow_status.installed_root}\n"
            "  This checkout has changes that are not in the installed "
            "distribution. Reinstall: uv tool install --force "
            f"{shadow_status.checkout_root} toolguard\n"
            "  Installing from a local path snapshots the working tree AS "
            "IT IS NOW, including any uncommitted changes -- commit first. "
            "This install affects EVERY project toolguard governs on this "
            "machine, not just this one."
        )

    return "\n\n".join(sections)


def _detect_broken_config_files(config: Configuration):
    """
    Return every governed config file that failed to parse (TOO-19).

    A non-empty result means :meth:`~toolguard.config.Configuration.resolve_permission_detailed`
    is clamping EVERY toolguard decision to ``'ask'`` (see that method's
    docstring) until the file(s) are fixed -- the single most severe class of
    configuration problem, so it is surfaced unconditionally here, independent
    of (and in addition to) the existing static/dynamic conflict summary.

    Takes an already-loaded :class:`~toolguard.config.Configuration` (see
    :func:`_detect_conflicts`, called with the SAME instance by ``main()``)
    rather than loading its own -- ``main()`` calls ``load_configuration()``
    exactly once per session-start invocation and both checks derive from
    that one call (TOO-19 review fix: this used to make a second, redundant
    ``load_configuration()`` call purely to avoid widening
    :func:`_detect_conflicts`'s 2-tuple return shape).

    Args:
        config: An already-loaded ``Configuration``.

    Returns:
        ``config.parse_failures``, materialized via ``tuple(...)`` so it
        behaves identically for a real ``Configuration`` and for a test
        double that only implements iteration (see
        ``test_session_start.py``'s pre-existing ``MagicMock(spec=Configuration)``
        fixtures, which do not set ``parse_failures`` explicitly).
    """
    return tuple(config.parse_failures)


def _detect_conflicts(config: Configuration):
    """
    Detect both static and dynamic configuration conflicts.

    This is the core logic of the SessionStart hook. It is extracted from
    ``main()`` so it can be unit-tested independently without needing to mock
    stdin or sys.exit.

    Takes an already-loaded :class:`~toolguard.config.Configuration` --
    ``main()`` loads it once and passes the same instance to this function
    and to :func:`_detect_broken_config_files` (TOO-19 review fix: this
    function used to call ``load_configuration()`` itself, requiring a
    second, redundant call from ``_detect_broken_config_files`` rather than
    widening this function's return shape).

    Args:
        config: An already-loaded ``Configuration``.

    Returns:
        Tuple ``(static_conflict, dynamic_conflict)`` where either may be None
        when no conflict of that type exists.
    """
    # Determine log directory from project root (same logic as the PreToolUse hook).
    project_root = config.project_root
    log_dir = project_root / "logs" if project_root is not None else None

    # 1. Static conflict: cross-level disagreement on takeover_mode.enabled.
    takeover = config.takeover_mode()
    static_conflict = takeover.conflict  # TakeoverEnabledConflict or None

    # 2. Dynamic conflict: previously recorded entries in the conflict log.
    dynamic_conflict = _check_dynamic_conflicts(log_dir)

    return static_conflict, dynamic_conflict


@dataclass(frozen=True)
class ShadowStatus:
    """
    TOO-19 shadow/stale-install status for the CURRENT session.

    Gated on the active session's project being toolguard's own source
    checkout (see :func:`_detect_shadow_status`) -- meaningless, and always
    the all-empty/False values below, for every other project.

    Attributes:
        checkout_root: The active project's root, when it IS a toolguard
            source checkout (see
            :func:`~toolguard.install_provenance.source_checkout_root`);
            ``None`` when the gate failed (nothing else here is populated).
        running_from_checkout: ``True`` when the toolguard copy that produced
            THIS ``toolguard-session-start`` invocation is that SAME
            checkout -- genuine live shadowing, e.g. via ``PYTHONPATH`` --
            rather than a properly installed distribution.
        installed_root: The installed distribution's package root (via
            :func:`~toolguard.install_provenance.installed_distribution_root`),
            or ``None`` when none was found.
        stale: ``True`` only when :attr:`checkout_root` is confirmed clean
            (git) AND its content hash differs from :attr:`installed_root`'s
            -- see :func:`~toolguard.install_provenance.stale_install_report`.
    """

    checkout_root: Optional[Path]
    running_from_checkout: bool
    installed_root: Optional[Path]
    stale: bool


_EMPTY_SHADOW_STATUS = ShadowStatus(
    checkout_root=None, running_from_checkout=False, installed_root=None, stale=False
)


def _detect_shadow_status(config: Configuration) -> ShadowStatus:
    """
    Detect TOO-19 shadow/stale-install status for the current session.

    Gated on the active session's project (``config.project_root``) itself
    being a toolguard source checkout -- both checks are meaningless for any
    other project (a Claude Code session in an unrelated repo has no
    "working tree" for toolguard to compare against), so this returns
    :data:`_EMPTY_SHADOW_STATUS` immediately when that gate fails.

    Args:
        config: An already-loaded ``Configuration`` (reused from ``main()``,
            matching the pattern in :func:`_detect_conflicts` /
            :func:`_detect_broken_config_files`).

    Returns:
        A :class:`ShadowStatus`.
    """
    project_root = config.project_root
    if project_root is None:
        return _EMPTY_SHADOW_STATUS

    checkout_root = install_provenance.source_checkout_root(
        package_root=project_root / "toolguard"
    )
    if checkout_root is None:
        return _EMPTY_SHADOW_STATUS

    governing_root = install_provenance.governing_package_root()
    running_from_checkout = governing_root == (checkout_root / "toolguard").resolve()

    installed_root = install_provenance.installed_distribution_root()
    stale_report = install_provenance.stale_install_report(checkout_root)

    return ShadowStatus(
        checkout_root=checkout_root,
        running_from_checkout=running_from_checkout,
        installed_root=installed_root,
        stale=stale_report.is_stale,
    )


def _build_session_start_argparser() -> argparse.ArgumentParser:
    """
    Build the argument parser for the toolguard SessionStart hook.

    Returns:
        Configured :class:`~argparse.ArgumentParser` with a description explaining
        that this is a Claude Code SessionStart hook (not meant to be run directly).
    """
    return argparse.ArgumentParser(
        prog="toolguard-session-start",
        description=(
            "Audience: INTERNAL (Claude Code hook) -- run automatically, not a "
            "user-facing command.\n\n"
            "Claude Code SessionStart hook. "
            "Reads a JSON SessionStart event on stdin and prints a brief conflict "
            "summary to stdout when configuration conflicts exist. "
            "This is invoked automatically by Claude Code at the start of each session -- "
            "it is not intended to be run directly from a terminal."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )


def main() -> None:
    """
    Main entry point for the SessionStart hook.

    Reads the SessionStart JSON payload from stdin, checks for static and dynamic
    configuration conflicts, any governed config file that failed to parse
    (TOO-19), and -- when the active project is toolguard's own source repo --
    a shadowed/stale install (TOO-19, see :func:`_detect_shadow_status`), and
    prints a brief summary to stdout when any are found. Claude Code injects
    this stdout into the session context so the agent immediately learns of
    any unresolved conflicts, broken config, or install-provenance problem.
    Always exits 0 -- a SessionStart hook must never block or break a session.

    Exit codes:
        0: Always (including --help, isatty guard, and error cases).
    """
    parser = _build_session_start_argparser()
    # parse_known_args() is used instead of parse_args() so that the hook still
    # works correctly when invoked via the test runner (which places test names
    # in sys.argv). This hook accepts NO arguments -- it only reads stdin -- so
    # unknown args are silently discarded. --help still exits 0 via argparse.
    parser.parse_known_args()

    # Interactive guard: if a human runs 'toolguard-session-start' in a terminal
    # without piping a JSON event, do not block on stdin. Print a brief explanation
    # and exit. Claude always pipes JSON (not a TTY), so this guard is inert in real use.
    # Exit code 0: informational (Arnon: change to non-zero if preferred).
    if sys.stdin.isatty():
        print(
            "toolguard-session-start: this is a Claude Code SessionStart hook, "
            "not a standalone command.\n"
            "It reads a JSON SessionStart event on stdin and is invoked automatically "
            "by Claude Code at the start of each session.",
            file=sys.stderr,
        )
        sys.exit(0)

    try:
        payload = _parse_session_start_input()
        cwd = payload.get("cwd") or os.getcwd()

        # Loaded exactly once and passed to both checks below (TOO-19 review
        # fix -- see _detect_conflicts / _detect_broken_config_files
        # docstrings for why this used to be two separate load_configuration()
        # calls).
        config = load_configuration(cwd)
        static_conflict, dynamic_conflict = _detect_conflicts(config)
        broken_files = _detect_broken_config_files(config)
        shadow_status = _detect_shadow_status(config)

        if (
            static_conflict is not None
            or dynamic_conflict is not None
            or broken_files
            or shadow_status.running_from_checkout
            or shadow_status.stale
        ):
            print(
                _format_summary(
                    static_conflict, dynamic_conflict, broken_files, shadow_status
                )
            )

    except Exception as exc:  # noqa: BLE001 - SessionStart must never raise
        print(f"toolguard session-start: unexpected error ({exc})", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
