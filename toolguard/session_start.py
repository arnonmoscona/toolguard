"""
Toolguard SessionStart Hook for Claude Code.

Runs at the start of every Claude Code session and surfaces configuration
problems the agent and user should notice immediately. Claude Code injects
SessionStart stdout directly into the session context, so printing a
summary here makes it visible to the agent.

Checks performed, independent of each other:

1. **Static conflicts** (recomputed live): ``config.takeover_mode().conflict``
   detects a cross-level disagreement on ``takeover_mode.enabled``. Self-clears
   once the configuration is fixed -- no stale state.
2. **Dynamic conflicts** (previously recorded): the conflict log file(s) in
   ``logs/toolguard-conflict-YYYY-MM-DD.md`` accumulate conflict entries
   written by the PreToolUse hook -- allow-over-deny overrides, and also
   ``takeover_mode.enabled`` disagreements, which persist in the log after
   the configuration is fixed. The most recent file with recorded entries is
   surfaced.
3. Any governed config file that is broken -- unparseable, or parsed but
   with a wrong-shaped ``[permissions]``/``[hard_deny]`` list -- see
   :func:`_detect_broken_config_files`.
4. Any ``*_fallback`` setting written with an unrecognized value -- see
   :func:`_detect_unrecognized_fallbacks`.
5. Whether the toolguard governing this machine is a shadowed source
   checkout, or an installed copy that has drifted from its own checkout --
   see :func:`_detect_shadow_status`, and ``docs/security.md`` ("The hook can
   be silently shadowed") for the rationale. Meaningful only when the active
   session's project is toolguard's own source repo; silent otherwise.

None of the above is deduplicated: the hook nags every session while a
condition remains true, by design.

Input: JSON via stdin (SessionStart shape -- ``hook_event_name``, ``cwd``;
       NO ``tool_name`` / ``tool_input`` fields).
Output: A short summary on stdout when anything above is found; nothing otherwise.
Exit code: Always 0 (a SessionStart hook must never block the session).
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from toolguard import ambient, env_config, install_provenance
from toolguard.config import Configuration, load_configuration


def _parse_session_start_input() -> dict:
    """
    Parse the SessionStart JSON payload from stdin.

    Lenient by design: missing or malformed input yields an empty dict rather
    than an exception.
    """
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _recent_conflict_logs(log_dir: Path) -> list:
    """
    Return existing ``toolguard-conflict-*.md`` files, most recent first.

    Sorting by filename descending is correct because the date suffix is ISO
    ``YYYY-MM-DD``.
    """
    if not log_dir.exists():
        return []
    return sorted(log_dir.glob("toolguard-conflict-*.md"), reverse=True)


def _count_conflict_entries(log_file: Path) -> int:
    """
    Count the conflict entries recorded in a conflict log file.

    Each entry written by :func:`toolguard.error_log.log_conflict` begins with a
    Markdown heading of the form ``## YYYY-MM-DD HH:MM:SS - CONFLICT``. An
    unreadable file counts as zero.
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

    Walks the conflict-log files in *log_dir* from most recent to least recent
    and describes the FIRST one that has recorded entries. Walking, rather than
    inspecting only the single most-recent file, matters because an empty
    current-day log must not shadow an older log whose conflicts are still
    unresolved -- the nag should persist until they are actually cleared.

    Returns:
        ``(relative_path_str, entry_count)``, or None when no recorded dynamic
        conflicts exist.
    """
    if log_dir is None:
        return None
    for log_file in _recent_conflict_logs(log_dir):
        count = _count_conflict_entries(log_file)
        if count == 0:
            continue
        # log_dir's parent is the project root; show the path relative to it.
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
    unrecognized_fallbacks=(),
) -> str:
    """
    Format the session-start summary printed to stdout.

    Args:
        static_conflict: A ``TakeoverEnabledConflict`` describing cross-level
            disagreement on ``takeover_mode.enabled``, or None.
        dynamic_conflict: A ``(path_str, count)`` tuple for the most recent
            conflict log file with recorded entries, or None.
        broken_files: ``(path, message)`` pairs for governed config files
            that are broken (unparseable, or a wrong-shaped permissions
            list).
        shadow_status: A :class:`ShadowStatus`, or ``None``.
        unrecognized_fallbacks:
            :class:`~toolguard.config_types.UnrecognizedFallbackSetting` records.

    Returns:
        A multi-line string suitable for printing to stdout, or "" when there
        is nothing to report.
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

    if unrecognized_fallbacks:
        fallback_lines = [
            "toolguard: UNRECOGNIZED FALLBACK SETTING -- resolving to 'ask' "
            "(maximum prompting) --"
        ]
        for bad in unrecognized_fallbacks:
            fallback_lines.append(
                f"  - {bad.key} = {bad.value!r} in "
                f"{bad.provenance.describe_brief()} is not a recognized value"
            )
            fallback_lines.append(f"    accepted: {', '.join(bad.accepted)}")
        fallback_lines.append(
            "  This is almost always a typo. Until it is fixed the setting has "
            "no effect and every decision it was meant to make falls back to "
            "'ask' -- the safe direction, but the most friction."
        )
        sections.append("\n".join(fallback_lines))

    if static_conflict is not None or dynamic_conflict is not None:
        conflict_lines = ["toolguard: configuration conflicts detected --"]

        if static_conflict is not None:
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
    Return every governed config file that is broken -- unparseable, or
    parsed but with a wrong-shaped ``[permissions]``/``[hard_deny]`` list
    (see :attr:`~toolguard.config.Configuration.parse_failures`).

    A non-empty result means toolguard is clamping every decision to ``'ask'``
    -- except one already resolved to ``'deny'``, which is never weakened --
    until the file(s) are fixed.

    Returns:
        A tuple of ``(path, message)`` pairs, empty when every governed
        config file is sound.
    """
    return tuple(config.parse_failures)


def _detect_unrecognized_fallbacks(config: Configuration):
    """
    Return every ``*_fallback`` setting written with an unrecognized value.

    Surfaced here in addition to the resolution log because an unattended
    session stalls on prompts and nobody reads the log until after the round
    trip.

    Returns:
        A tuple of
        :class:`~toolguard.config_types.UnrecognizedFallbackSetting`, empty
        when every fallback setting is valid or unset.
    """
    return tuple(config.unrecognized_fallback_settings())


def _detect_conflicts(config: Configuration):
    """
    Detect both static and dynamic configuration conflicts.

    The dynamic-conflict scan reads the same log directory the PreToolUse
    hook writes to (:func:`~toolguard.env_config.get_env_config`, honouring
    ``TOOLGUARD_LOG_DIR``) rather than assuming ``project_root/logs`` --
    otherwise setting that variable silently disables the nag.

    Returns:
        ``(static_conflict, dynamic_conflict)``; either may be None when no
        conflict of that type exists.
    """
    project_root = config.project_root
    log_dir = (
        env_config.get_env_config(project_root)["log_dir"]
        if project_root is not None
        else None
    )

    takeover = config.takeover_mode()
    static_conflict = takeover.conflict  # TakeoverEnabledConflict or None

    dynamic_conflict = _check_dynamic_conflicts(log_dir)

    return static_conflict, dynamic_conflict


@dataclass(frozen=True)
class ShadowStatus:
    """
    Shadow/stale-install status for the current session.

    Every field carries its empty/False value unless the active session's
    project is toolguard's own source checkout (see
    :func:`_detect_shadow_status`).

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
    Detect shadow/stale-install status for the current session.

    Gated on the active project (``config.project_root``) being a toolguard
    source checkout: a session in an unrelated repo has no working tree to
    compare against, so this returns :data:`_EMPTY_SHADOW_STATUS` immediately
    when the gate fails. :func:`~toolguard.install_provenance.source_checkout_root`
    is passed the PACKAGE directory (``project_root / "toolguard"``), not the
    project root.
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
    """Build the argument parser for the toolguard SessionStart hook."""
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


def _run_checker(label: str, check: Callable[[], object], default: object) -> object:
    """
    Run one SessionStart detector, isolating its failure from the others.

    Args:
        label: Short name for the check, used in the stderr failure message.
        check: Zero-argument callable to run.
        default: Value to return if *check* raises.

    Returns:
        ``check()``'s result, or *default* on any exception (also reported
        to stderr, naming *label*).
    """
    try:
        return check()
    except Exception as exc:  # noqa: BLE001 - one checker must not block the rest
        print(f"toolguard session-start: {label} check failed ({exc})", file=sys.stderr)
        return default


def main() -> None:
    """
    Main entry point for the SessionStart hook.

    Reads the SessionStart JSON payload from stdin, runs the checks described
    in this module's docstring, and prints a summary to stdout when any of
    them fire. Each check is isolated: one raising does not withhold the
    others' findings.
    """
    parser = _build_session_start_argparser()
    # parse_known_args(), not parse_args(): this hook takes no arguments, and
    # the test runner's own args land in sys.argv, so unknown args must be
    # discarded rather than rejected.
    parser.parse_known_args()

    # Claude always pipes JSON (never a TTY), so this guard is inert in real
    # use -- it only stops a manual run from blocking on stdin.
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
        cwd = payload.get("cwd") or str(ambient.cwd())

        # Loaded once and shared by every _detect_* check below, so they see
        # a consistent snapshot.
        config = load_configuration(cwd)
        static_conflict, dynamic_conflict = _run_checker(
            "conflict", lambda: _detect_conflicts(config), (None, None)
        )
        broken_files = _run_checker(
            "broken-config", lambda: _detect_broken_config_files(config), ()
        )
        shadow_status = _run_checker(
            "shadow-status", lambda: _detect_shadow_status(config), _EMPTY_SHADOW_STATUS
        )
        unrecognized_fallbacks = _run_checker(
            "fallback", lambda: _detect_unrecognized_fallbacks(config), ()
        )

        if (
            static_conflict is not None
            or dynamic_conflict is not None
            or broken_files
            or shadow_status.running_from_checkout
            or shadow_status.stale
            or unrecognized_fallbacks
        ):
            print(
                _format_summary(
                    static_conflict,
                    dynamic_conflict,
                    broken_files,
                    shadow_status,
                    unrecognized_fallbacks,
                )
            )

    except Exception as exc:  # noqa: BLE001 - SessionStart must never raise
        print(f"toolguard session-start: unexpected error ({exc})", file=sys.stderr)

    sys.exit(0)


if __name__ == "__main__":
    main()
