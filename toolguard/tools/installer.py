"""
``toolguard-install``: an AGENT-FACING installer helper for toolguard.

Driven by an AI coding agent working through the guided install runbook at
``docs/install.md``. Each subcommand is one mechanical step, so the agent issues ONE
approvable ``Bash(toolguard-install ...)`` command instead of several Read/Write/Edit
tool calls, each of which would trigger its own Claude Code permission prompt --
and because the writes happen inside this process, they never reach Claude's own
permission layer at all.

NOT a general-purpose installer, and deliberately not meant for direct human use.
Each subcommand's ``--help`` states what it touches, its preconditions, what it
refuses to do, and what it journals, so an agent can decide whether a step does what
is wanted without running it first.

Design notes
------------
- Changes are made recoverable two ways: the file being replaced is copied into
  ``~/.toolguard/backups/`` first, and a numbered entry naming the reverse action is
  appended to ``~/.toolguard/install-journal.md``. Which of the two a subcommand
  does, how many entries it appends, and when it does neither -- read-only,
  refused, or nothing to change -- is stated in that subcommand's own ``--help``.
- Config and settings writes go through
  :func:`~toolguard.config_write_guard.verified_write_config`, which parses the
  candidate text -- and, given the prior patterns, refuses a write that would drop
  one -- before writing it atomically.
- TOML editing reuses ``write_toml_config`` (preserves everything outside the
  ``[permissions]`` section) and ``find_section_boundaries`` rather than hand-rolling
  a TOML parser/writer.
"""

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from re import MULTILINE, compile as re_compile
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional, Sequence, Tuple

from toolguard.config import load_config_file
from toolguard.config_write_guard import (
    ConfigWriteVerificationError,
    patterns_in_config_text,
    verified_write_config,
)
from toolguard.permission_migration import create_backup, write_toml_config
from toolguard.rule_entry import RuleEntry, normalize_entries_preserving, real_patterns
from toolguard.rule_sort import (
    RuleEntryOrStr,
    find_section_boundaries,
    render_toml_entry,
)
from toolguard.tools.recommended_protections import required_hard_deny_patterns
from toolguard.tools.self_integrity import required_self_integrity_hard_deny_patterns
from toolguard.tools.self_permission import required_self_permissions
from toolguard.tools.uninstall_readiness import required_uninstall_readiness_permissions
from toolguard.install_update import (
    InstallKind,
    detect_install,
    local_remote_head,
    remote_head,
)
from toolguard.tool_spec import FILE_KIND_TOOLS


def _entry_pattern(entry: RuleEntryOrStr) -> str:
    """
    Return the wrapped pattern string (e.g. ``"Bash(git:*)"``) of a plain or
    structured entry.
    """
    return entry.pattern if isinstance(entry, RuleEntry) else entry


class InstallerError(Exception):
    """
    An expected, user-facing installer failure (never a programming bug).

    :func:`main` prints ``error: <message>`` to stderr and exits non-zero, so the
    calling agent can fix the invocation or fall back to a manual step.
    """


#: Numbered journal entry header, e.g. "## [3] 2026-07-07 14:12 local -- ...".
_JOURNAL_HEADER_RE = re_compile(
    r"^## \[(\d+)\] \d{4}-\d{2}-\d{2} \d{2}:\d{2} local -- ", MULTILINE
)

_JOURNAL_TITLE = (
    "# toolguard install journal\n"
    "\n"
    "This is an append-only, human- and agent-readable record of every change the\n"
    "toolguard installer made on this machine, so a later session can undo it\n"
    "precisely. Never delete or rewrite past entries; only append. Keep it forever.\n"
    "See docs/install.md in the toolguard repository for the full format and the\n"
    "uninstall procedure.\n"
)

_README_TEMPLATE = (
    "This is toolguard's per-user state directory.\n"
    "\n"
    "It holds:\n"
    "- install-journal.md -- an append-only record of every change the toolguard\n"
    "  installer made on this machine, with the exact command to reverse each one.\n"
    "- backups/ -- timestamped backups of any file the installer edited or\n"
    "  replaced, named after the original file (e.g.\n"
    "  settings.json.2026-07-07-141200).\n"
    "- stage/ -- staged file writes, applied together as one atomic group during a\n"
    "  guided install (see docs/install.md in the toolguard repository).\n"
    "- errors/ -- detailed crash reports if the hook ever hit an unexpected\n"
    "  exception (created on demand, not by init-state).\n"
    "- once_per.db -- once-per-day claim store for periodic notices\n"
    "  (created on demand, not by init-state).\n"
    "- traces/ -- session-trace dumps written by the guided install/uninstall\n"
    "  runbooks (see docs/install.md Phase T.1), created on demand, not by\n"
    "  init-state.\n"
    "\n"
    "Toolguard was installed from:\n"
    "    {source}\n"
    "\n"
    "This directory is intentionally NOT deleted on uninstall. It is kept for\n"
    "auditability and problem resolution, holds nothing executable, and you may\n"
    "delete it by hand at any time.\n"
)


# ---------------------------------------------------------------------------
# Small filesystem/state helpers
# ---------------------------------------------------------------------------


def _state_dir() -> Path:
    """Return toolguard's per-user state directory."""
    return Path.home() / ".toolguard"


def _backups_dir() -> Path:
    """Return the backups directory inside the state directory."""
    return _state_dir() / "backups"


def _journal_path() -> Path:
    """Return the install journal's path."""
    return _state_dir() / "install-journal.md"


def _ensure_state() -> None:
    """
    Create ``~/.toolguard`` (with ``backups/`` and ``stage/``) and the journal if absent.

    Exists so that a mutating subcommand works when run standalone, before
    ``init-state``; an existing journal is never clobbered. The bare ``journal``
    subcommand deliberately does NOT call this -- it requires ``init-state`` to
    have run first.
    """
    (_state_dir() / "stage").mkdir(parents=True, exist_ok=True)
    _backups_dir().mkdir(parents=True, exist_ok=True)
    journal_path = _journal_path()
    if not journal_path.exists():
        _atomic_write_text(journal_path, _JOURNAL_TITLE)


def _claude_dir(scope: str, project_dir: Optional[str]) -> Path:
    """
    Resolve the ``.claude`` directory for *scope*.

    Args:
        scope: Either ``'user'`` or ``'project'``.
        project_dir: Required (and only valid) when *scope* is ``'project'``.

    Returns:
        ``~/.claude`` for user scope, or ``<project_dir>/.claude`` for project scope.

    Raises:
        InstallerError: If *scope* and *project_dir* are inconsistent.
    """
    if scope == "project":
        if not project_dir:
            raise InstallerError("--project-dir is required when --scope is 'project'")
        return Path(project_dir) / ".claude"
    if project_dir:
        raise InstallerError("--project-dir is only valid with --scope project")
    return Path.home() / ".claude"


def _config_path(scope: str, project_dir: Optional[str]) -> Path:
    """Resolve the ``toolguard_hook.toml`` path for *scope*."""
    return _claude_dir(scope, project_dir) / "toolguard_hook.toml"


def _settings_path(scope: str, project_dir: Optional[str]) -> Path:
    """
    Resolve the Claude Code settings file to register hooks in for *scope*.

    User scope governs every project on the machine, so hooks go in the shared
    ``settings.json``. Project scope governs one repo, so hooks go in that
    project's own ``settings.local.json``.
    """
    claude_dir = _claude_dir(scope, project_dir)
    if scope == "user":
        return claude_dir / "settings.json"
    return claude_dir / "settings.local.json"


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Write *content* to *path* atomically (sibling temp file, then rename),
    creating *path*'s parent directory if needed.

    Do NOT use this for a rule-bearing config or settings file:
    :func:`~toolguard.config_write_guard.verified_write_config` does an
    equivalent atomic write, but parses the candidate text first and, given
    ``expected_patterns``, catches silently-dropped rules.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(content)
    tmp_path.replace(path)


def _split_csv(value: str) -> List[str]:
    """Split a comma-separated CLI value into a de-duplicated, order-preserving list."""
    if not value:
        return []
    result: List[str] = []
    for item in value.split(","):
        item = item.strip()
        if item and item not in result:
            result.append(item)
    return result


# ---------------------------------------------------------------------------
# The install journal
# ---------------------------------------------------------------------------


def _next_journal_index(existing_text: str) -> int:
    """Return the next monotonic journal entry index given the current journal text."""
    indices = [int(m.group(1)) for m in _JOURNAL_HEADER_RE.finditer(existing_text)]
    return (max(indices) + 1) if indices else 1


def _append_journal_entry(
    action: str, reverse: str, backup: Optional[str] = None
) -> int:
    """
    Append one numbered, reversible entry to ``~/.toolguard/install-journal.md``.

    Requires ``~/.toolguard`` to already exist: creating it here would skip the
    README/backups/stage scaffolding ``init-state`` is responsible for.

    Args:
        action: Human-readable description of what was done.
        reverse: The exact reverse action (what would undo *action*).
        backup: Path to a backup file made for this change, if any.

    Returns:
        The index of the newly appended entry.

    Raises:
        InstallerError: If ``~/.toolguard`` does not exist yet.
    """
    if not _state_dir().is_dir():
        raise InstallerError(
            f"{_state_dir()} does not exist -- run 'init-state' first."
        )
    journal_path = _journal_path()
    existing = journal_path.read_text() if journal_path.exists() else _JOURNAL_TITLE
    index = _next_journal_index(existing)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = (
        f"\n## [{index}] {timestamp} local -- {action}\n"
        f"- action: {action}\n"
        f"- backup: {backup if backup else 'none'}\n"
        f"- reverse: {reverse}\n"
    )
    _atomic_write_text(journal_path, existing + entry)
    return index


# ---------------------------------------------------------------------------
# init-state
# ---------------------------------------------------------------------------

_INIT_STATE_HELP = """\
Create ~/.toolguard (toolguard's per-user state directory) and its scaffolding.

Creates, if absent:
  ~/.toolguard/
  ~/.toolguard/backups/          (every later backup lands here)
  ~/.toolguard/stage/            (reserved for staged file-write groups)
  ~/.toolguard/README.txt        (explains the directory and the --source given)
  ~/.toolguard/install-journal.md (the append-only install journal)

Idempotent: running this again does NOT recreate or overwrite an existing
README.txt, and does NOT rewrite or clobber an existing install-journal.md --
it only appends a new session header recording that a session started.

This step does NOT append a numbered/reversible journal entry itself (there is
nothing to reverse: ~/.toolguard is deliberately never deleted by uninstall).
"""


def cmd_init_state(args: argparse.Namespace) -> int:
    """
    Handle the ``init-state`` subcommand: create ``~/.toolguard`` and its scaffolding.

    Args:
        args: Parsed CLI arguments; must have ``source``.

    Returns:
        ``0`` on success.
    """
    state_dir = _state_dir()
    backups_dir = _backups_dir()
    stage_dir = state_dir / "stage"
    state_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    stage_dir.mkdir(parents=True, exist_ok=True)

    readme_path = state_dir / "README.txt"
    readme_created = not readme_path.exists()
    if readme_created:
        _atomic_write_text(readme_path, _README_TEMPLATE.format(source=args.source))

    journal_path = _journal_path()
    journal_existed = journal_path.exists()
    existing = journal_path.read_text() if journal_existed else _JOURNAL_TITLE
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    session_header = (
        f"\n---\nSession started {timestamp} local -- guided install "
        f"(source: {args.source})\n"
    )
    _atomic_write_text(journal_path, existing + session_header)

    print(f"initialized state dir: {state_dir}")
    print(f"  backups: {backups_dir}")
    print(f"  stage: {stage_dir}")
    print(
        f"  README.txt: {'created' if readme_created else 'already present, left unchanged'}"
    )
    print(
        f"  journal: {journal_path} "
        f"({'created' if not journal_existed else 'session header appended'})"
    )
    return 0


# ---------------------------------------------------------------------------
# write-config
# ---------------------------------------------------------------------------

_WRITE_CONFIG_HELP = """\
Write the base toolguard_hook.toml for the chosen scope.

Writes:
  ~/.claude/toolguard_hook.toml               (--scope user)
  <project-dir>/.claude/toolguard_hook.toml   (--scope project)

with governed_tools (and additional_supported_tools, if given). The base
config ALWAYS keeps takeover mode disabled (no [takeover_mode] section is
written) -- use the separate enable-takeover subcommand for that, later, once
rules exist.

Preconditions and refusals:
  - Refuses to overwrite an existing toolguard_hook.toml unless --force is
    given; without --force it makes NO changes and reports the refusal.
  - With --force, the existing file is backed up into ~/.toolguard/backups/
    BEFORE being replaced.

Journals one entry naming the file written and, on --force, the backup path;
its reverse is either "delete the file" (fresh write) or "restore the backup"
(overwrite).
"""


def _render_config_toml(
    governed_tools: Sequence[str], additional_supported_tools: Sequence[str]
) -> str:
    """Render a fresh, minimal ``toolguard_hook.toml`` body (takeover disabled)."""
    lines = [
        "# toolguard_hook.toml -- written by toolguard-install",
        "# See docs/configuration.md in the toolguard repository for the full schema.",
        "",
    ]
    if additional_supported_tools:
        lines.append("additional_supported_tools = [")
        for tool in additional_supported_tools:
            lines.append(f'    "{tool}",')
        lines.append("]")
        lines.append("")
    lines.append("governed_tools = [")
    for tool in governed_tools:
        lines.append(f'    "{tool}",')
    lines.append("]")
    lines.append("")
    return "\n".join(lines)


def cmd_write_config(args: argparse.Namespace) -> int:
    """
    Handle the ``write-config`` subcommand: write the base ``toolguard_hook.toml``.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``,
            ``governed_tools``, ``additional_supported_tools``, ``force``.

    Returns:
        ``0`` on success, ``2`` if refused (existing file, no ``--force``).
    """
    _ensure_state()
    config_path = _config_path(args.scope, args.project_dir)
    governed_tools = _split_csv(args.governed_tools)
    additional = _split_csv(args.additional_supported_tools)

    backup_path: Optional[Path] = None
    if config_path.exists():
        if not args.force:
            print(
                f"refused: {config_path} already exists; no changes made "
                "(use --force to overwrite)"
            )
            return 2
        backup_path = create_backup(config_path, _backups_dir())

    content = _render_config_toml(governed_tools, additional)
    # No expected_patterns: this renders a fresh, minimal file with no
    # [permissions]/[hard_deny] rules at all, even on a --force overwrite, so
    # there is no pre-existing rule set the write is supposed to preserve.
    verified_write_config(config_path, content, "toml")

    reverse = (
        f"restore backup {backup_path} over {config_path}"
        if backup_path
        else f"delete {config_path}"
    )
    index = _append_journal_entry(
        action=(
            f"wrote base toolguard config at {args.scope} scope: {config_path} "
            f"(governed_tools={','.join(governed_tools)}; takeover disabled)"
        ),
        reverse=reverse,
        backup=str(backup_path) if backup_path else None,
    )

    print(f"wrote config: {config_path}")
    print(f"  governed_tools: {', '.join(governed_tools)}")
    print(
        f"  additional_supported_tools: {', '.join(additional) if additional else '(none)'}"
    )
    print("  takeover: disabled")
    if backup_path:
        print(f"  backup of previous file: {backup_path}")
    print(f"  journal: appended entry [{index}]")
    return 0


# ---------------------------------------------------------------------------
# register-hooks
# ---------------------------------------------------------------------------

_REGISTER_HOOKS_HELP = """\
Register toolguard's PreToolUse/SessionStart hooks, MERGING with any existing
hooks (never clobbering them).

Writes to ~/.claude/settings.json (user scope) or
<project-dir>/.claude/settings.local.json (project scope): one PreToolUse
matcher per governed tool, plus a SessionStart matcher pointing at
"<--binary>-session-start".

The PreToolUse matcher's command is HARDENED (TOO-19) when possible:
"<tool venv python> -E -P -m toolguard.hook" instead of the bare --binary
path. -E/-P make the interpreter ignore PYTHONPATH and cwd entirely when
resolving imports, so a stray PYTHONPATH=. (or any working-tree toolguard/
package) can never shadow the installed hook with unreviewed code -- see
docs/security.md ("The hook can be silently shadowed"). The interpreter path
is derived from --binary (its resolved location's sibling python3/python) and
is verified to exist and be executable BEFORE being written; if it cannot be
found, the bare --binary form is registered instead (unhardened, but working
-- a hook that fails to launch is a SILENT, non-blocking Claude Code hook
error that lets the tool call proceed with NO toolguard decision at all,
which is worse than the shadowing this hardens against, so an unverified path
is never written).

Hooks are MERGED into any existing PreToolUse/SessionStart entries -- other
hook types already present (PostToolUse, SessionEnd, ...) and any matcher
already registered are left untouched (re-running for a tool that already has
a matcher does not add a duplicate).

Backs up the pre-edit file into ~/.toolguard/backups/ before writing (skipped
only if the file did not exist yet). Journals one entry naming the file
edited and the matchers added; its reverse is "restore the backup" (or
"delete the file" if it was freshly created).
"""

#: The module the hardened PreToolUse hook command runs via ``-m``.
_HOOK_MODULE = "toolguard.hook"


def _tool_venv_python(binary: str) -> Optional[str]:
    """
    Resolve the tool venv's python interpreter next to *binary*.

    *binary* is the installed console-script path for the toolguard hook (a
    ``uv tool install`` shim, or a venv's ``bin/toolguard``).
    :meth:`Path.resolve` follows it to the script's real location, whose
    ``bin/`` directory holds the ``python3``/``python`` belonging to that venv.
    The sibling is returned by name, never further resolved: in a ``uv tool``
    venv ``bin/python3`` is itself a symlink to the base interpreter OUTSIDE
    the venv, which under ``-E -P`` cannot import toolguard at all.

    Never guesses: returns ``None`` rather than an interpreter path that might
    not run.

    Args:
        binary: Path to the installed toolguard console-script.

    Returns:
        The absolute path to the sibling interpreter, verified to exist and
        be executable, or ``None``.
    """
    try:
        bin_dir = Path(binary).resolve().parent
    except OSError:
        return None
    for name in ("python3", "python"):
        candidate = bin_dir / name
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def _hardened_hook_command(binary: str) -> Tuple[str, bool]:
    """
    Build the command to register for the toolguard PreToolUse hook.

    Prefers the hardened form ``<venv python> -E -P -m toolguard.hook`` (see
    docs/security.md, "The hook can be silently shadowed"), which cannot be
    shadowed by a ``PYTHONPATH`` or cwd-relative ``toolguard/`` package. Falls
    back to the bare *binary* path, UNHARDENED, when the venv python cannot be
    located. That fallback is deliberate: a hook that fails to launch is a
    NON-BLOCKING Claude Code error, so the tool call proceeds with no toolguard
    decision at all and nothing says so -- worse than the shadowing this
    hardens against. Hence an interpreter path is never written unverified.

    The interpreter path goes through :func:`shlex.quote` because Claude Code
    hands the registered string to a shell: an unquoted path with a space (a
    relocated venv, a macOS directory with a space) would split into several
    argv words and fail to launch, into that same silent fail-open. Verifying
    the interpreter exists does not cover this -- existence says nothing about
    how the written string re-parses.

    Args:
        binary: Path to the installed toolguard console-script.

    Returns:
        ``(command, hardened)`` -- the command string to register, and
        whether it is the hardened form.
    """
    python_path = _tool_venv_python(binary)
    if python_path is None:
        return binary, False
    return f"{shlex.quote(python_path)} -E -P -m {_HOOK_MODULE}", True


def cmd_register_hooks(args: argparse.Namespace) -> int:
    """
    Handle the ``register-hooks`` subcommand: merge PreToolUse/SessionStart hooks.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``,
            ``binary``, ``governed_tools``.

    Returns:
        ``0`` on success.

    Raises:
        InstallerError: If the target settings file exists but is not valid JSON.
    """
    _ensure_state()
    settings_path = _settings_path(args.scope, args.project_dir)
    governed_tools = _split_csv(args.governed_tools)
    binary = args.binary
    hook_command, hook_hardened = _hardened_hook_command(binary)
    # SessionStart is registered as the BARE "<binary>-session-start" form,
    # deliberately, and never through _hardened_hook_command(). Hardened, the
    # comparison session_start._detect_shadow_status() makes -- whichever copy of
    # toolguard produced THIS process, against the active project's source checkout
    # -- could only ever answer "the installed distribution", so live-shadow
    # detection would go permanently and silently blind: no error, and no other test
    # failing to say so. (The stale-install half does not go through
    # governing_package_root() and would survive.) See technical-notes.md,
    # "Shadowed-hook detection and install hardening (TOO-19)";
    # test_session_start_hook_is_never_hardened catches a regression here.
    session_start_binary = f"{binary}-session-start"

    backup_path: Optional[Path] = None
    original_text: Optional[str] = None
    if settings_path.exists():
        original_text = settings_path.read_text()
        try:
            data = json.loads(original_text) if original_text.strip() else {}
        except json.JSONDecodeError as exc:
            raise InstallerError(f"{settings_path} is not valid JSON: {exc}") from exc
        backup_path = create_backup(settings_path, _backups_dir())
    else:
        data = {}

    hooks = data.setdefault("hooks", {})
    pre_tool_use = hooks.setdefault("PreToolUse", [])
    existing_matchers = {
        entry.get("matcher") for entry in pre_tool_use if isinstance(entry, dict)
    }
    added_matchers: List[str] = []
    skipped_matchers: List[str] = []
    for tool in governed_tools:
        if tool in existing_matchers:
            skipped_matchers.append(tool)
            continue
        pre_tool_use.append(
            {"matcher": tool, "hooks": [{"type": "command", "command": hook_command}]}
        )
        added_matchers.append(tool)

    session_start = hooks.setdefault("SessionStart", [])
    session_start_commands = {
        h.get("command")
        for entry in session_start
        if isinstance(entry, dict)
        for h in entry.get("hooks", [])
    }
    session_start_added = session_start_binary not in session_start_commands
    if session_start_added:
        session_start.append(
            {"hooks": [{"type": "command", "command": session_start_binary}]}
        )

    # expected_patterns: settings.json can carry Claude's own native
    # `permissions.allow/deny/ask` alongside the hooks edited here, and this
    # rewrites the WHOLE file -- a merge bug would otherwise drop the user's
    # native rules with nothing to catch it. A brand-new or blank file has no
    # prior patterns, so it passes None rather than an empty set; blank text
    # would in any case raise out of patterns_in_config_text, an empty string
    # not being valid JSON.
    expected_patterns = (
        patterns_in_config_text(original_text, "json")
        if original_text is not None and original_text.strip()
        else None
    )
    verified_write_config(
        settings_path,
        json.dumps(data, indent=2) + "\n",
        "json",
        expected_patterns=expected_patterns,
    )

    reverse = (
        f"restore backup {backup_path} over {settings_path}"
        if backup_path
        else f"delete {settings_path}"
    )
    index = _append_journal_entry(
        action=(
            f"registered hooks at {args.scope} scope: edited {settings_path} to add "
            f"PreToolUse matchers for {','.join(added_matchers) or '(none new)'} and "
            f"a SessionStart hook at {session_start_binary}, pointing PreToolUse at "
            f"'{hook_command}' ({'hardened' if hook_hardened else 'UNHARDENED'})"
        ),
        reverse=reverse,
        backup=str(backup_path) if backup_path else None,
    )

    print(f"registered hooks: {settings_path}")
    print(
        f"  added PreToolUse matchers: "
        f"{', '.join(added_matchers) if added_matchers else '(none)'}"
    )
    if skipped_matchers:
        print(f"  already present, unchanged: {', '.join(skipped_matchers)}")
    if added_matchers:
        if hook_hardened:
            print(f"  PreToolUse command (hardened): {hook_command}")
        else:
            print(
                f"  PreToolUse command (UNHARDENED -- could not locate a venv "
                f"python next to {binary}): {hook_command}"
            )
    print(
        "  SessionStart hook: "
        + (
            f"added {session_start_binary}"
            if session_start_added
            else f"{session_start_binary} already present, unchanged"
        )
    )
    if backup_path:
        print(f"  backup of previous file: {backup_path}")
    print(f"  journal: appended entry [{index}]")
    print(
        "  reminder: still ahead per docs/install.md -- skills (5), validate (6), "
        "migration (7), security audit (8), maintenance (9), takeover (10) + "
        "wrap-up; the session-trace dump offer (Phase T.1) is MANDATORY before you "
        "end the conversation"
    )
    return 0


# ---------------------------------------------------------------------------
# seed-self-perms
# ---------------------------------------------------------------------------

#: Scoped to the one operation an agent needs here: prepending the uv tool bin
#: dir to ``PATH``. A
#: governed Bash call's shell state does not persist between invocations, so an
#: agent that runs toolguard's console scripts by bare name re-exports ``PATH``
#: before nearly every call; with ``no_match_fallback`` at its recommended
#: ``ask``, each one is a prompt. Deliberately not a general ``PATH`` rule --
#: ``export PATH="/malicious:$PATH"`` would make a later command resolve to a
#: planted binary. Anchored, with one optional quote character permitted at
#: each end.
_UV_BIN_PATH_PREPEND_ALLOW = r"Bash([regex]^export PATH=.?\$HOME/\.local/bin:\$PATH.?$)"


_SEED_SELF_PERMS_HELP = """\
Add the allow/ask rules toolguard's own skills -- and a later uninstall --
need to keep working, plus one self-integrity hard_deny protection, at the
chosen scope's toolguard_hook.toml.

Adds, to the [permissions] section:
  - one rule per entry in toolguard.tools.self_permission.required_self_permissions()
    (the single source of truth -- currently Bash(toolguard-audit:*) => allow and
    Bash(toolguard-maintain:*) => ask)
  - Read/Write/Edit(~/.toolguard/**) => allow, so toolguard's own state directory
    (the journal and its backups) stays readable/writable
  - Bash([regex]^export PATH=...$HOME/.local/bin...$PATH...$) => allow, a narrowly
    scoped rule covering ONLY prepending the uv tool bin dir to PATH (never an
    arbitrary PATH value), so the defensive `export PATH=...` an agent runs before
    nearly every toolguard console-script invocation stops prompting
  - one rule per entry in
    toolguard.tools.uninstall_readiness.required_uninstall_readiness_permissions()
    (the single source of truth -- ALL allow: cd navigation, restoring native
    settings, running uv tool uninstall, and removing toolguard's own config/
    skill files), so a LATER uninstall always completes -- seeded now, before
    takeover is ever enabled

Adds, to the [hard_deny] section's deny list:
  - one pattern per entry in
    toolguard.tools.self_integrity.required_self_integrity_hard_deny_patterns()
    (the single source of truth -- blocks any rm/find -delete command
    referencing ~/.toolguard), so ~/.toolguard can never be deleted by a Bash
    command, even one the agent decides to run unprompted -- unconditional on
    takeover choice, since this protects toolguard's own operational
    integrity, not the user's files

Consent for these specific rules is ASSUMED to already have been obtained by
the calling agent (per docs/install.md Phase 4, step 3) -- this subcommand
does not itself prompt for consent.

Precondition: toolguard_hook.toml must already exist at the chosen scope (run
write-config first) -- refuses otherwise, without creating a partial config.

Idempotent: a rule already present is left alone and reported as unchanged; if
nothing needs to change, no backup or journal entry is made and the summary
says so explicitly. Otherwise backs up the pre-edit config into
~/.toolguard/backups/ and journals one entry listing exactly what was added.
"""


def cmd_seed_self_perms(args: argparse.Namespace) -> int:
    """
    Handle the ``seed-self-perms`` subcommand: add toolguard's self-permission rules.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``.

    Returns:
        ``0`` on success (including the no-op case).

    Raises:
        InstallerError: If no ``toolguard_hook.toml`` exists yet at this
            scope, or if ``required_self_integrity_hard_deny_patterns()``
            returns no patterns -- seeding zero self-integrity protections
            must not be reported as a completed install.
    """
    _ensure_state()
    config_path = _config_path(args.scope, args.project_dir)
    if not config_path.exists():
        raise InstallerError(
            f"{config_path} does not exist -- run 'write-config' first."
        )

    self_integrity_patterns = required_self_integrity_hard_deny_patterns()
    if not self_integrity_patterns:
        raise InstallerError(
            "required_self_integrity_hard_deny_patterns() returned no patterns "
            "-- refusing to report a completed install that protects nothing."
        )

    # normalize_entries_preserving, not the raw tomllib values: a structured entry
    # parses as a plain dict, and a dict is unhashable, so the membership sets built
    # below would raise TypeError. is_native=False -- this is a toolguard config
    # file, never Claude's native settings.
    original_text = config_path.read_text()
    current = tomllib.loads(original_text)
    current_permissions = current.get("permissions", {})
    permissions: Dict[str, List[RuleEntryOrStr]] = {
        "allow": list(
            normalize_entries_preserving(
                current_permissions.get("allow", []), is_native=False
            )
        ),
        "deny": list(
            normalize_entries_preserving(
                current_permissions.get("deny", []), is_native=False
            )
        ),
        "ask": list(
            normalize_entries_preserving(
                current_permissions.get("ask", []), is_native=False
            )
        ),
    }

    candidates: List[Tuple[str, str]] = [
        (f"Bash({p.pattern})", p.list_type) for p in required_self_permissions()
    ]
    candidates += [
        (f"{tool}(~/.toolguard/**)", "allow") for tool in sorted(FILE_KIND_TOOLS)
    ]
    candidates.append((_UV_BIN_PATH_PREPEND_ALLOW, "allow"))

    claude_dir = _claude_dir(args.scope, args.project_dir)
    settings_path = _settings_path(args.scope, args.project_dir)
    candidates += [
        (f"{p.tool}({p.pattern})", p.list_type)
        for p in required_uninstall_readiness_permissions(claude_dir, settings_path)
    ]

    added: List[Tuple[str, str]] = []
    already_present: List[Tuple[str, str]] = []
    # Membership is by pattern: a bare str never compares equal to the RuleEntry
    # carrying the same pattern.
    existing_patterns_by_list = {
        list_type: {_entry_pattern(entry) for entry in permissions[list_type]}
        for list_type in ("allow", "deny", "ask")
    }
    for pattern, list_type in candidates:
        if pattern in existing_patterns_by_list[list_type]:
            already_present.append((pattern, list_type))
        else:
            permissions[list_type].append(pattern)
            existing_patterns_by_list[list_type].add(pattern)
            added.append((pattern, list_type))

    # Self-integrity hard_deny: stop ~/.toolguard from ever being deleted by a
    # Bash rm/find command. Seeded unconditionally here rather than behind the
    # optional secret-protection flow, because it protects toolguard's own
    # operational integrity rather than the user's files.
    #
    # [hard_deny] also accepts structured entries, so it is normalized like
    # `permissions` above and for the same reason.
    current_hard_deny = current.get("hard_deny", {})
    hard_deny_patterns: List[RuleEntryOrStr] = list(
        normalize_entries_preserving(current_hard_deny.get("deny", []), is_native=False)
    )
    hard_deny_allow_patterns: List[RuleEntryOrStr] = list(
        normalize_entries_preserving(
            current_hard_deny.get("allow", []), is_native=False
        )
    )
    hard_deny_added: List[str] = []
    hard_deny_already_present: List[str] = []
    existing_hard_deny_patterns = {
        _entry_pattern(entry) for entry in hard_deny_patterns
    }
    for protection in self_integrity_patterns:
        if protection.pattern in existing_hard_deny_patterns:
            hard_deny_already_present.append(protection.pattern)
        else:
            hard_deny_patterns.append(protection.pattern)
            existing_hard_deny_patterns.add(protection.pattern)
            hard_deny_added.append(protection.pattern)

    print(f"seeded self-permissions: {config_path}")
    if not added and not hard_deny_added:
        print("  already present, no changes needed:")
        for pattern, list_type in already_present:
            print(f"    {pattern} -> {list_type}")
        for pattern in hard_deny_already_present:
            print(f"    {pattern} -> hard_deny")
        return 0

    backup_path = create_backup(config_path, _backups_dir())
    if added:
        write_toml_config(config_path, permissions, auto_sort=True)
    if hard_deny_added:
        pre_write_text = config_path.read_text()
        new_hard_deny_section = _render_hard_deny_section(
            hard_deny_patterns, hard_deny_allow_patterns
        )
        updated_text = _replace_or_append_toml_section(
            pre_write_text, "hard_deny", new_hard_deny_section
        )
        # expected_patterns: everything in the file immediately before this
        # write, plus the full new hard_deny lists -- nothing the write should
        # preserve may go missing. Via real_patterns(), never a bare set() of
        # the entry lists, so a synthesized-pattern entry cannot look like a
        # dropped rule and refuse an otherwise-safe write.
        expected_patterns = (
            patterns_in_config_text(pre_write_text, "toml")
            | set(real_patterns(hard_deny_patterns))
            | set(real_patterns(hard_deny_allow_patterns))
        )
        verified_write_config(
            config_path,
            updated_text,
            "toml",
            expected_patterns=expected_patterns,
        )

    action_parts = [f"{p} -> {t}" for p, t in added]
    action_parts += [f"{p} -> hard_deny" for p in hard_deny_added]
    index = _append_journal_entry(
        action=(
            f"seeded self-permission rules into {config_path}: "
            + "; ".join(action_parts)
        ),
        reverse=f"restore backup {backup_path} over {config_path}",
        backup=str(backup_path),
    )

    for pattern, list_type in added:
        print(f"  added: {pattern} -> {list_type}")
    for pattern in hard_deny_added:
        print(f"  added: {pattern} -> hard_deny")
    if already_present or hard_deny_already_present:
        print("  already present, unchanged:")
        for pattern, list_type in already_present:
            print(f"    {pattern} -> {list_type}")
        for pattern in hard_deny_already_present:
            print(f"    {pattern} -> hard_deny")
    print(f"  backup of previous file: {backup_path}")
    print(f"  journal: appended entry [{index}]")
    return 0


# ---------------------------------------------------------------------------
# enable-takeover
# ---------------------------------------------------------------------------

_ENABLE_TAKEOVER_HELP = """\
Set [takeover_mode] enabled = true (with no_match_fallback) in an existing
toolguard_hook.toml.

Writes/replaces only the [takeover_mode] section of toolguard_hook.toml at
the chosen scope -- governed_tools and every other section are left
untouched. --no-match-fallback chooses what an unmatched command resolves to
when the tool HAS rules but none match; the default is "ask" (prompts,
matching Claude Code's own native behavior for anything unmatched). Also
accepted: "allow_with_warning" (allow, but flagged with a logged warning),
"allow" (allow, with NO warning logged -- also spelled "allow_with_no_warnings",
an identical, longer alias that exists as a human reminder this is a
deliberate loosening), and "deny" (fail-closed).

Precondition: toolguard_hook.toml must already exist at the chosen scope (run
write-config first) -- refuses otherwise.

Always backs up the pre-edit config into ~/.toolguard/backups/ first (this
step changes enforcement behavior, so a backup is made even though something
always changes), and journals one entry; its reverse is "restore the backup
(or set enabled = false)".
"""


def _render_takeover_section(no_match_fallback: str) -> str:
    """Render a ``[takeover_mode]`` section body with takeover enabled."""
    return (
        f'[takeover_mode]\nenabled = true\nno_match_fallback = "{no_match_fallback}"\n'
    )


def _replace_or_append_toml_section(
    text: str, section_name: str, new_section_text: str
) -> str:
    """
    Replace an existing ``[section_name]`` section in *text*, or append it.

    Args:
        text: Full TOML file content.
        section_name: Section name without brackets (e.g. ``'takeover_mode'``).
        new_section_text: The replacement section body (including its ``[header]``).

    Returns:
        The updated file content.
    """
    start_pos, end_pos = find_section_boundaries(text, section_name)
    if start_pos == -1:
        if not text:
            return new_section_text
        if text.endswith("\n"):
            return text + "\n" + new_section_text
        return text + "\n\n" + new_section_text
    before = text[:start_pos]
    after = text[end_pos:]
    return before + new_section_text + "\n" + after


def cmd_enable_takeover(args: argparse.Namespace) -> int:
    """
    Handle the ``enable-takeover`` subcommand: set ``[takeover_mode] enabled = true``.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``,
            ``no_match_fallback``.

    Returns:
        ``0`` on success.

    Raises:
        InstallerError: If no ``toolguard_hook.toml`` exists yet at this scope.
    """
    _ensure_state()
    config_path = _config_path(args.scope, args.project_dir)
    if not config_path.exists():
        raise InstallerError(
            f"{config_path} does not exist -- run 'write-config' first."
        )

    original = config_path.read_text()
    backup_path = create_backup(config_path, _backups_dir())

    new_section = _render_takeover_section(args.no_match_fallback)
    new_text = _replace_or_append_toml_section(original, "takeover_mode", new_section)
    # expected_patterns: this edit only touches [takeover_mode] -- every
    # permissions/hard_deny pattern already in the file must still be there.
    verified_write_config(
        config_path,
        new_text,
        "toml",
        expected_patterns=patterns_in_config_text(original, "toml"),
    )

    index = _append_journal_entry(
        action=(
            f"enabled takeover mode in {config_path}: enabled=true, "
            f"no_match_fallback={args.no_match_fallback}"
        ),
        reverse=f"restore backup {backup_path} over {config_path} (or set enabled = false)",
        backup=str(backup_path),
    )

    print(f"enabled takeover: {config_path}")
    print(f"  no_match_fallback: {args.no_match_fallback}")
    print(f"  backup of previous file: {backup_path}")
    print(f"  journal: appended entry [{index}]")
    print(
        "  reminder: BEFORE going further, confirm out loud that Phase 8 (security "
        "audit offer) and Phase 9 (maintenance offer) were ALREADY made earlier in "
        "this conversation -- this is the last checkpoint that reliably runs, and a "
        "real install skipped both silently despite the checklist. If either was not "
        "actually offered, go back and offer it now, THEN continue."
    )
    print(
        "  reminder: still ahead per docs/install.md -- 10.3 re-validate under "
        "takeover, then Wrap-up; the session-trace dump offer (Phase T.1) is "
        "MANDATORY before you end the conversation"
    )
    return 0


# ---------------------------------------------------------------------------
# journal
# ---------------------------------------------------------------------------

_JOURNAL_HELP = """\
Append one numbered, journaled entry to ~/.toolguard/install-journal.md.

Every mutating subcommand above already journals its own action automatically
-- use this subcommand directly only for a step this installer has no
dedicated subcommand for (e.g. a manual edit made in hand-off mode, or
recording a step done by the user themselves).

Requires ~/.toolguard to already exist (run init-state first); refuses
otherwise rather than creating a bare journal with no README/backups/stage
scaffolding.
"""


def cmd_journal(args: argparse.Namespace) -> int:
    """
    Handle the ``journal`` subcommand: append one entry to the install journal.

    Args:
        args: Parsed CLI arguments; must have ``action``, ``reverse``, ``backup``.

    Returns:
        ``0`` on success.
    """
    index = _append_journal_entry(
        action=args.action, reverse=args.reverse, backup=args.backup
    )
    print(f"appended journal entry [{index}] to {_journal_path()}")
    return 0


# ---------------------------------------------------------------------------
# discover-projects
# ---------------------------------------------------------------------------

_DISCOVER_PROJECTS_HELP = """\
Discover candidate projects for permission migration (docs/install.md Phase 7.1).
READ-ONLY: makes no backup and appends no journal entry.

Sources (never trusted blindly):
  - ~/.claude.json: its top-level "projects" object is keyed by the absolute path of
    every project Claude has worked in -- the primary/authoritative source.
  - ~/.claude/projects/: one directory per project, named by encoding the absolute
    path (the leading "/" and every "/" become "-"). This encoding is LOSSY (a real
    "-" in a path is indistinguishable from an encoded "/"), so a decoded candidate
    is only ever accepted if it verifiably exists on disk as a directory.

Filtered to candidates that: still exist as a directory, AND have a
.claude/settings.local.json that parses and contains at least one non-empty
permission list (allow/deny/ask). Directories that no longer exist, or have nothing
worth migrating, are left out.

Each surviving candidate is annotated with whether it already has a toolguard config
(toolguard_hook.toml or .json) and whether that config has
[takeover_mode] enabled = true, plus a rough count of permission patterns that would
be candidates for migration.

--format text (default) prints a human-readable list; --format json prints a JSON
array of objects with the fields: path, has_toolguard_config, takeover_enabled,
pattern_count. Output is sorted by path for determinism. Zero candidates prints a
plain statement rather than an empty table.

This is discovery only -- the actual migration (moving patterns into a toolguard
config) is a separate step: toolguard.scripts.migrate_permissions
(docs/install.md Phase 7.3).
"""


def _decode_transcript_dir_name(name: str) -> str:
    """
    Best-effort, LOSSY decode of a ``~/.claude/projects/`` directory name to a path.

    The encoding replaces the leading ``/`` and every ``/`` with ``-``, so reversing
    it is ambiguous whenever the original path itself contained a literal ``-``.
    Verify the decoded path exists as a directory before trusting it; this function
    does not.

    Args:
        name: A directory name found under ``~/.claude/projects/``.

    Returns:
        The best-effort decoded absolute path string.
    """
    return name.replace("-", "/")


def _load_claude_json_projects(claude_json_path: Path) -> List[str]:
    """
    Return the absolute project paths listed in ``~/.claude.json``'s ``projects`` key.

    A missing file, an :class:`OSError`, invalid JSON or an unexpected shape each
    yield an empty list.

    Args:
        claude_json_path: Path to ``~/.claude.json``.

    Returns:
        A list of absolute project path strings (possibly empty).
    """
    if not claude_json_path.exists():
        return []
    try:
        data = json.loads(claude_json_path.read_text())
    except json.JSONDecodeError, OSError:
        return []
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return []
    return [str(p) for p in projects.keys()]


def _load_transcript_dir_projects(transcripts_root: Path) -> List[str]:
    """
    Recover candidate project paths from ``~/.claude/projects/`` subdirectory names.

    Only decoded candidates that verifiably exist as a directory on disk are
    returned (see :func:`_decode_transcript_dir_name` for why the lossy encoding
    cannot be trusted blindly).

    Args:
        transcripts_root: Path to ``~/.claude/projects/``.

    Returns:
        A list of absolute project path strings (possibly empty).
    """
    if not transcripts_root.is_dir():
        return []
    candidates: List[str] = []
    for entry in transcripts_root.iterdir():
        if not entry.is_dir():
            continue
        decoded = _decode_transcript_dir_name(entry.name)
        if Path(decoded).is_dir():
            candidates.append(decoded)
    return candidates


def _count_permission_patterns(permissions: dict) -> int:
    """Return the total pattern count across the allow/deny/ask lists of *permissions*."""
    total = 0
    for list_type in ("allow", "deny", "ask"):
        value = permissions.get(list_type, [])
        if isinstance(value, list):
            total += len(value)
    return total


def _find_toolguard_config(claude_dir: Path) -> Optional[Tuple[Path, str]]:
    """Return ``(path, file_format)`` for an existing toolguard_hook.toml/json, else None."""
    toml_path = claude_dir / "toolguard_hook.toml"
    if toml_path.exists():
        return toml_path, "toml"
    json_path = claude_dir / "toolguard_hook.json"
    if json_path.exists():
        return json_path, "json"
    return None


def _discover_project_candidate(project_path_str: str) -> Optional[dict]:
    """
    Evaluate one candidate project path, returning its discovery record or ``None``.

    A candidate is dropped (returns ``None``) unless its directory still exists AND
    it has a ``.claude/settings.local.json`` that parses and has at least one
    non-empty permission list.

    Args:
        project_path_str: Absolute project path to evaluate.

    Returns:
        A dict with ``path``/``has_toolguard_config``/``takeover_enabled``/
        ``pattern_count`` keys, or ``None`` if the candidate does not qualify.
    """
    project_dir = Path(project_path_str)
    if not project_dir.is_dir():
        return None
    claude_dir = project_dir / ".claude"
    settings_path = claude_dir / "settings.local.json"
    if not settings_path.exists():
        return None
    try:
        settings_data = json.loads(settings_path.read_text())
    except json.JSONDecodeError, OSError:
        return None
    permissions = settings_data.get("permissions", {})
    if not isinstance(permissions, dict):
        return None
    pattern_count = _count_permission_patterns(permissions)
    if pattern_count == 0:
        return None

    takeover_enabled = False
    found_config = _find_toolguard_config(claude_dir)
    has_toolguard_config = found_config is not None
    if found_config is not None:
        config_path, file_format = found_config
        try:
            content = load_config_file(config_path, file_format)
        except OSError, ValueError:
            content = {}
        takeover_section = content.get("takeover_mode", {})
        if isinstance(takeover_section, dict):
            takeover_enabled = bool(takeover_section.get("enabled", False))

    return {
        "path": str(project_dir),
        "has_toolguard_config": has_toolguard_config,
        "takeover_enabled": takeover_enabled,
        "pattern_count": pattern_count,
    }


def cmd_discover_projects(args: argparse.Namespace) -> int:
    """
    Handle the ``discover-projects`` subcommand: list migration candidates. READ-ONLY.

    Args:
        args: Parsed CLI arguments; must have ``format``.

    Returns:
        ``0``. A candidate that does not qualify is dropped, not reported.
    """
    home = Path.home()
    seen: "dict[str, None]" = {}
    for project_path_str in _load_claude_json_projects(home / ".claude.json"):
        seen.setdefault(str(Path(project_path_str)), None)
    for project_path_str in _load_transcript_dir_projects(
        home / ".claude" / "projects"
    ):
        seen.setdefault(str(Path(project_path_str)), None)

    candidates = []
    for project_path_str in seen:
        record = _discover_project_candidate(project_path_str)
        if record is not None:
            candidates.append(record)
    candidates.sort(key=lambda entry: entry["path"])

    if args.format == "json":
        print(json.dumps(candidates, indent=2))
        return 0

    if not candidates:
        print("no candidate projects found (nothing to migrate).")
        return 0

    print(f"found {len(candidates)} candidate project(s):")
    for record in candidates:
        config_note = (
            "toolguard config present"
            if record["has_toolguard_config"]
            else "no toolguard config yet"
        )
        takeover_note = (
            " (takeover ENABLED -- its blanket allows are intentional, do not "
            "migrate them)"
            if record["takeover_enabled"]
            else ""
        )
        print(
            f"  {record['path']}  -- {config_note}{takeover_note}; "
            f"~{record['pattern_count']} pattern(s) candidate for migration"
        )
    return 0


# ---------------------------------------------------------------------------
# install-skills
# ---------------------------------------------------------------------------

_INSTALL_SKILLS_HELP = """\
Install toolguard's bundled skills (toolguard-security-audit, toolguard-maintenance)
into the chosen scope, in ONE step (docs/install.md Phase 5).

Writes:
  ~/.claude/skills/<skill-name>/                        (--scope user)
  <project-dir>/.claude/skills/<skill-name>/             (--scope project)

--source is either an existing local checkout directory (its
skills/<skill-name>/ subdirectories are copied directly) or a git remote URL
(shallow-cloned with 'git clone --depth 1' into a throwaway temp directory, then
copied from there; no new package dependency -- this shells out to whatever 'git'
is on PATH). Do NOT hand-roll this with a bespoke fetch/clone/copy sequence of your
own.

Accepts the SAME --source string that worked for 'uv tool install' in Phase 3,
including uv's own 'git+https://host/owner/repo@ref' form -- the 'git+' prefix is
stripped and a trailing '@ref' becomes 'git clone --branch ref', so branch pinning
is preserved. A plain 'https://host/owner/repo' URL (no branch control) also works.

Idempotent: a skill directory that already exists at the target is left untouched
and reported as "already installed, unchanged", UNLESS --force is given, in which
case the existing directory is backed up first (whole-tree copy into
~/.toolguard/backups/<skill-name>-<timestamp>/, mirroring the file-backup timestamp
format and its same-second collision '-2', '-3', ... suffixing) before being
replaced.

Journals one entry PER skill actually installed or replaced (never one bundled entry
for both); its reverse is "remove <target skill dir>" for a fresh install, or
"restore the backup over <target skill dir>" for a --force overwrite.

Refuses (raises an error, installs nothing) if --source is neither an existing local
path nor a working git remote.
"""

_BUNDLED_SKILL_NAMES: Tuple[str, ...] = (
    "toolguard-security-audit",
    "toolguard-maintenance",
)


def _backup_directory(source_dir: Path, backups_dir: Path, name_prefix: str) -> Path:
    """
    Copy *source_dir* whole-tree into ``~/.toolguard/backups/<name_prefix>-<timestamp>/``.

    Exists because ``create_backup`` handles single files only; the timestamp
    format and the ``-2``/``-3`` same-second collision suffixing match it.

    Args:
        source_dir: The directory to back up (must exist).
        backups_dir: ``~/.toolguard/backups``.
        name_prefix: A short label for the backed-up thing (e.g. a skill name).

    Returns:
        The path the directory was copied to.
    """
    backups_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    base_name = f"{name_prefix}-{timestamp}"
    backup_path = backups_dir / base_name
    sequence = 2
    while backup_path.exists():
        backup_path = backups_dir / f"{base_name}-{sequence}"
        sequence += 1
    shutil.copytree(source_dir, backup_path)
    return backup_path


def _parse_git_source(source: str) -> Tuple[str, Optional[str]]:
    """
    Parse a possibly uv-style VCS source into a plain ``git clone`` URL and an
    optional ref (branch/tag/commit).

    ``git+https`` is a pip/uv pseudo-scheme, not a git transport, so the
    ``git+https://host/owner/repo@ref`` string that ``uv tool install`` accepts
    is not a valid ``git clone`` argument. Stripping the prefix and splitting a
    trailing ``@ref`` lets the same ``--source`` value serve both, branch
    pinning included.

    A plain URL with no ``git+`` prefix comes back unchanged with no ref, so an
    ssh URL's ``user@host`` (``git@github.com:owner/repo``) is never mistaken
    for a ref split. Second guard, even under the prefix: an ``@`` splits only
    when the text after it contains no ``/``. That also declines to split a
    slash-bearing branch name such as ``release/1.2``, which is therefore not
    supported here.

    Args:
        source: The ``--source`` value as given (local path, plain git URL,
            or uv-style ``git+<scheme>://...[@ref]``).

    Returns:
        ``(clone_url, ref)`` -- ``ref`` is ``None`` when no ref was given.
    """
    if not source.startswith("git+"):
        return source, None
    url = source[len("git+") :]
    at_index = url.rfind("@")
    if at_index == -1 or "/" in url[at_index + 1 :]:
        return url, None
    return url[:at_index], url[at_index + 1 :]


@contextmanager
def _resolve_skills_source(source: str):
    """
    Yield a directory containing a ``skills/<skill-name>/`` layout for *source*.

    If *source* is an existing local directory, it is yielded directly (no copy, no
    cleanup). Otherwise *source* is treated as a git remote URL (accepting both a
    plain URL and uv's ``git+<scheme>://...[@ref]`` form, see
    :func:`_parse_git_source`) and shallow-cloned (``git clone --depth 1``,
    ``--branch <ref>`` when a ref was given) into a throwaway temporary directory
    that is yielded and then cleaned up when the context exits.

    Args:
        source: Either a local filesystem path or a git remote URL.

    Yields:
        A directory containing a ``skills/`` subdirectory to copy from.

    Raises:
        InstallerError: If *source* is a git URL and the clone fails.
    """
    local_path = Path(source)
    if local_path.is_dir():
        yield local_path
        return

    clone_url, ref = _parse_git_source(source)
    with TemporaryDirectory() as tmp_dir_name:
        dest = Path(tmp_dir_name)
        cmd = ["git", "clone", "--depth", "1"]
        if ref:
            cmd += ["--branch", ref]
        cmd += [clone_url, str(dest)]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise InstallerError(
                f"could not clone {source!r} (git exited {result.returncode}): "
                f"{result.stderr.strip()}"
            )
        yield dest


def cmd_install_skills(args: argparse.Namespace) -> int:
    """
    Handle the ``install-skills`` subcommand: install toolguard's bundled skills.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``, ``source``,
            ``force``.

    Returns:
        ``0`` on success (including the all-already-installed no-op case).

    Raises:
        InstallerError: If ``--source`` is neither an existing local path nor a
            working git remote, or lacks the expected ``skills/<name>`` layout.
    """
    _ensure_state()
    skills_dir = _claude_dir(args.scope, args.project_dir) / "skills"

    installed: List[str] = []
    unchanged: List[str] = []
    backups: List[Tuple[str, Path]] = []

    with _resolve_skills_source(args.source) as source_root:
        source_skills_dir = source_root / "skills"
        for skill_name in _BUNDLED_SKILL_NAMES:
            src = source_skills_dir / skill_name
            if not src.is_dir():
                raise InstallerError(
                    f"{args.source} has no skills/{skill_name} directory -- "
                    "nothing to install"
                )
            dst = skills_dir / skill_name
            if dst.exists():
                if not args.force:
                    unchanged.append(skill_name)
                    continue
                backup_path = _backup_directory(dst, _backups_dir(), skill_name)
                shutil.rmtree(dst)
                shutil.copytree(src, dst)
                backups.append((skill_name, backup_path))
                installed.append(skill_name)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src, dst)
                installed.append(skill_name)

    backup_by_skill = dict(backups)
    indices: List[int] = []
    for skill_name in installed:
        dst = skills_dir / skill_name
        backup_path = backup_by_skill.get(skill_name)
        reverse = (
            f"restore the backup at {backup_path} over {dst}"
            if backup_path
            else f"remove {dst}"
        )
        index = _append_journal_entry(
            action=(
                f"installed skill {skill_name} at {args.scope} scope from "
                f"{args.source}: {dst}"
            ),
            reverse=reverse,
            backup=str(backup_path) if backup_path else None,
        )
        indices.append(index)

    print(f"install-skills: {skills_dir}")
    if installed:
        print(f"  installed/replaced: {', '.join(installed)}")
    if unchanged:
        print(f"  already installed, unchanged: {', '.join(unchanged)}")
    for skill_name, backup_path in backups:
        print(f"  backup of previous {skill_name}: {backup_path}")
    if indices:
        print(f"  journal: appended entries {indices}")
    else:
        print("  journal: no changes to record")
    return 0


# ---------------------------------------------------------------------------
# seed-hard-deny
# ---------------------------------------------------------------------------

_SEED_HARD_DENY_HELP = """\
Add the canonical "Sensitive files" [hard_deny] protections to the chosen scope's
toolguard_hook.toml (docs/install.md Phase 10.1).

Adds, to the [hard_deny] section's deny list, exactly the patterns from
toolguard.tools.recommended_protections.required_hard_deny_patterns() -- the single
source of truth for this fixed, curated set (mirrors docs/security.md "Recommended
deny patterns" -> "Sensitive files": .env/.env.*/.aws/**/.ssh/** reads, writes and
edits).
This subcommand does NOT compose [hard_deny] TOML freehand and does not invent or
extend the set -- change recommended_protections.py (and docs/security.md) instead.

Any pre-existing [hard_deny] content (an 'allow' carve-out list, or unrelated 'deny'
entries) is preserved, not clobbered -- only the canonical patterns missing from
'deny' are appended.

Consent for these specific patterns is ASSUMED to already have been obtained by the
calling agent (per docs/install.md Phase 10.1: "Offer it; do not add it silently.")
-- this subcommand does not itself prompt for consent.

Precondition: toolguard_hook.toml must already exist at the chosen scope (run
write-config first) -- refuses otherwise, without creating a partial config.

Idempotent: a pattern already present is left alone; if nothing needs to change, no
backup or journal entry is made and the summary says so explicitly. Otherwise backs
up the pre-edit config into ~/.toolguard/backups/ and journals one entry listing
exactly what was added.
"""


def _render_hard_deny_section(
    deny_patterns: Sequence[RuleEntryOrStr], allow_patterns: Sequence[RuleEntryOrStr]
) -> str:
    """
    Render a ``[hard_deny]`` section body with the given deny/allow lists.

    Args:
        deny_patterns: The ``[hard_deny] deny`` entries, plain and/or
            structured.
        allow_patterns: The ``[hard_deny] allow`` entries, plain and/or
            structured.

    Returns:
        The full ``[hard_deny]`` section text, including its header.
    """
    lines = ["[hard_deny]"]
    if deny_patterns:
        lines.append("deny = [")
        for entry in deny_patterns:
            lines.append(f"    {render_toml_entry(entry)},")
        lines.append("]")
    if allow_patterns:
        lines.append("allow = [")
        for entry in allow_patterns:
            lines.append(f"    {render_toml_entry(entry)},")
        lines.append("]")
    return "\n".join(lines) + "\n"


def cmd_seed_hard_deny(args: argparse.Namespace) -> int:
    """
    Handle the ``seed-hard-deny`` subcommand: add the canonical [hard_deny] protections.

    Args:
        args: Parsed CLI arguments; must have ``scope``, ``project_dir``.

    Returns:
        ``0`` on success (including the no-op case).

    Raises:
        InstallerError: If no ``toolguard_hook.toml`` exists yet at this scope.
    """
    _ensure_state()
    config_path = _config_path(args.scope, args.project_dir)
    if not config_path.exists():
        raise InstallerError(
            f"{config_path} does not exist -- run 'write-config' first."
        )

    # Normalized, not raw: a structured entry parses as a plain dict, and a dict is
    # unhashable, so the membership set built below would raise TypeError.
    original = config_path.read_text()
    current = tomllib.loads(original)
    current_hard_deny = current.get("hard_deny", {})
    deny_patterns: List[RuleEntryOrStr] = list(
        normalize_entries_preserving(current_hard_deny.get("deny", []), is_native=False)
    )
    allow_patterns: List[RuleEntryOrStr] = list(
        normalize_entries_preserving(
            current_hard_deny.get("allow", []), is_native=False
        )
    )

    added: List[str] = []
    already_present: List[str] = []
    existing_deny_patterns = {_entry_pattern(entry) for entry in deny_patterns}
    for protection in required_hard_deny_patterns():
        if protection.pattern in existing_deny_patterns:
            already_present.append(protection.pattern)
        else:
            deny_patterns.append(protection.pattern)
            existing_deny_patterns.add(protection.pattern)
            added.append(protection.pattern)

    print(f"seeded hard-deny protections: {config_path}")
    if not added:
        print("  already present, no changes needed:")
        for pattern in already_present:
            print(f"    {pattern}")
        return 0

    backup_path = create_backup(config_path, _backups_dir())
    new_section = _render_hard_deny_section(deny_patterns, allow_patterns)
    new_text = _replace_or_append_toml_section(original, "hard_deny", new_section)
    # expected_patterns: everything in the file before this edit, plus the
    # full new deny/allow lists -- nothing may be silently dropped. Via
    # real_patterns() to exclude a synthesized pattern; see the matching
    # comment in cmd_seed_self_perms.
    expected_patterns = (
        patterns_in_config_text(original, "toml")
        | set(real_patterns(deny_patterns))
        | set(real_patterns(allow_patterns))
    )
    verified_write_config(
        config_path,
        new_text,
        "toml",
        expected_patterns=expected_patterns,
    )

    index = _append_journal_entry(
        action=(
            f"seeded hard-deny protections into {config_path}: " + "; ".join(added)
        ),
        reverse=f"restore backup {backup_path} over {config_path}",
        backup=str(backup_path),
    )

    for pattern in added:
        print(f"  added: {pattern}")
    if already_present:
        print("  already present, unchanged:")
        for pattern in already_present:
            print(f"    {pattern}")
    print(f"  backup of previous file: {backup_path}")
    print(f"  journal: appended entry [{index}]")
    return 0


# ---------------------------------------------------------------------------
# skills-status
# ---------------------------------------------------------------------------

_SKILLS_STATUS_HELP = """\
Report toolguard's own installation freshness (TOO-15 completion-gate check).
READ-ONLY: makes no backup and appends no journal entry.

Reports three things, side by side:
  - binary install status: the install kind (git/local/unknown), via
    toolguard.install_update.detect_install(), and whether a newer commit is
    available upstream. A network-unreachable or undeterminable remote is
    reported plainly as "unknown" -- this subcommand never hangs or fails
    just because the remote could not be reached.
  - bundled skill install status: for each name in _BUNDLED_SKILL_NAMES, at
    BOTH the user scope (~/.claude/skills/<name>) and the project scope
    (<project-dir>/.claude/skills/<name>), one of:
      missing   -- the path does not exist. This correctly covers a broken/
                   dangling symlink (Path.exists() reports False for one),
                   the footgun this check exists to catch.
      installed -- a directory (real, or a symlink resolving to a real
                   directory) containing a SKILL.md file.
      invalid   -- something exists at the path but is not a valid skill
                   directory (e.g. an empty directory, or a plain file) -- a
                   distinct, reportable state from missing.
  - PreToolUse hook registration status (TOO-19): for every toolguard
    PreToolUse command found in settings.json (user scope) and
    settings.local.json (project scope), whether it is the HARDENED
    "-E -P -m toolguard.hook" form register-hooks now writes, or an older
    UNHARDENED bare-binary registration (re-run register-hooks to switch),
    or -- for an already-hardened command -- whether its recorded
    interpreter path still exists on disk (a missing one is a SILENT,
    non-blocking hook failure at the next tool call; see register-hooks
    --help and docs/security.md).

--project-dir defaults to the current working directory, so running this
from inside the project you care about needs no flag.

--format text (default) prints a human-readable summary; --format json
prints a JSON object with "binary", "skills", and "hook_registrations" keys.

Exit code is always 0 -- this is a diagnostic, never a pass/fail gate. It
only raises an error for a genuine filesystem/permissions failure, never for
any of the missing/invalid/stale/unhardened states themselves (those are
normal, expected, reportable outcomes, not errors).
"""


def _classify_skill_dir(path: Path) -> str:
    """
    Classify a bundled-skill install path as ``'missing'``, ``'installed'``, or
    ``'invalid'``.

    Args:
        path: The candidate skill directory, e.g.
            ``~/.claude/skills/toolguard-maintenance``.

    Returns:
        ``'installed'`` when *path* is a directory containing ``SKILL.md``;
        ``'missing'`` when it does not exist -- which includes a dangling
        symlink, the footgun this check exists to catch, since
        :meth:`Path.exists` follows symlinks; ``'invalid'`` for anything else
        that exists there, such as an empty directory or a plain file.
    """
    if not path.exists():
        return "missing"
    if path.is_dir() and (path / "SKILL.md").is_file():
        return "installed"
    return "invalid"


def _binary_status() -> dict:
    """
    Summarize toolguard's own binary install freshness.

    Returns:
        A dict with ``kind`` (``'git'``/``'local'``/``'unknown'``),
        ``installed_commit``, ``remote_commit``, ``update_available``
        (``True``/``False``, or ``None`` when undeterminable), and ``note``
        (a human-readable explanation, set whenever the state is anything
        but a clean up-to-date/behind determination).
    """
    info = detect_install()

    if info.kind == InstallKind.GIT:
        remote = remote_head(info.url) if info.url else None
        if remote is None:
            return {
                "kind": "git",
                "installed_commit": info.installed_commit,
                "remote_commit": None,
                "update_available": None,
                "note": "could not reach the toolguard remote (offline, or git unavailable)",
            }
        return {
            "kind": "git",
            "installed_commit": info.installed_commit,
            "remote_commit": remote,
            "update_available": info.installed_commit != remote,
            "note": None,
        }

    if info.kind == InstallKind.LOCAL:
        if info.repo_path is None or info.installed_commit is None:
            return {
                "kind": "local",
                "installed_commit": info.installed_commit,
                "remote_commit": None,
                "update_available": None,
                "note": f"could not read HEAD from local checkout {info.repo_path}",
            }
        remote = local_remote_head(info.repo_path)
        if remote is None:
            return {
                "kind": "local",
                "installed_commit": info.installed_commit,
                "remote_commit": None,
                "update_available": None,
                "note": (
                    f"could not reach the toolguard remote from {info.repo_path} "
                    "(offline, or no 'origin' remote?)"
                ),
            }
        return {
            "kind": "local",
            "installed_commit": info.installed_commit,
            "remote_commit": remote,
            "update_available": info.installed_commit != remote,
            "note": None,
        }

    return {
        "kind": "unknown",
        "installed_commit": None,
        "remote_commit": None,
        "update_available": None,
        "note": "could not determine toolguard's install type",
    }


#: ``env`` options that themselves consume a following argument, so the
#: token after them is NOT the wrapped command (e.g. ``env -u PYTHONPATH
#: <python> ...``). Deliberately just the realistic subset -- see
#: :func:`_skip_env_wrapper`.
_ENV_OPTIONS_WITH_ARG = frozenset(
    {"-u", "--unset", "-C", "--chdir", "-S", "--split-string"}
)


def _skip_env_wrapper(tokens: List[str]) -> List[str]:
    """
    Skip a leading ``env`` wrapper -- and its own options/assignments -- in *tokens*.

    A hand-edited registration such as ``env -u PYTHONPATH <venv python> -E -P
    -m toolguard.hook`` has the wrapper, not the interpreter, as token 0.
    Without this, :func:`_interpreter_missing` calls a correctly hardened,
    working registration BROKEN -- a false alarm on exactly the shape the
    hardening recommends.

    Not a shell parser: it walks the realistic
    ``env [OPTION]... [NAME=VALUE]... [COMMAND ...]`` shape just far enough to
    reach the next token, which the caller treats as the interpreter whatever
    it is. Any other wrapper (``sudo``, a shell) is unrecognized.

    Args:
        tokens: The shlex-split (or naive-split, on unbalanced quotes)
            command tokens.

    Returns:
        *tokens* with a leading ``env`` and its own options/assignments
        removed, or *tokens* unchanged if it does not start with ``"env"``.
    """
    if not tokens or tokens[0] != "env":
        return tokens
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in _ENV_OPTIONS_WITH_ARG:
            index += 2
        elif token.startswith("-"):
            index += 1
        elif "=" in token:
            index += 1
        else:
            break
    return tokens[index:]


def _interpreter_missing(command: str) -> bool:
    """
    Determine whether a hardened hook *command*'s interpreter is missing.

    The interpreter is not always token 0 (see :func:`_skip_env_wrapper`), and
    an interpreter given as a bare name resolves on ``PATH`` rather than as an
    existing path -- hence :func:`shutil.which` alongside :meth:`Path.exists`.

    Deliberately biased toward under-reporting: a shape this cannot make sense
    of -- tokens exhausted after the ``env`` wrapper, say -- is reported as
    NOT missing. A missed warning costs little, whereas crying BROKEN over a
    correct registration teaches the reader to ignore the diagnostic.

    Args:
        command: The full hook command string as registered in settings.json.

    Returns:
        ``True`` only when an interpreter token was identified and it
        resolves neither via :meth:`Path.exists` nor :func:`shutil.which`.
    """
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()
    tokens = _skip_env_wrapper(tokens)
    if not tokens:
        return False
    interpreter = tokens[0]
    return not (Path(interpreter).exists() or shutil.which(interpreter))


def _hook_registration_findings(settings_path: Path) -> List[dict]:
    """
    Classify each toolguard PreToolUse hook command registered in *settings_path*.

    READ-ONLY. Returns one entry per PreToolUse hook whose command contains
    "toolguard" (case-insensitively), classified as hardened (containing
    ``-m toolguard.hook``) or not. A missing settings file, an
    :class:`OSError`, invalid JSON, or a file with no such hook yields an
    empty list.

    Args:
        settings_path: The ``settings.json``/``settings.local.json`` path to
            inspect.

    Returns:
        A list of dicts: ``{"matcher": str, "command": str, "hardened":
        bool, "interpreter_missing": bool}``. ``interpreter_missing`` is set
        only for a hardened command, and catches at report time an interpreter
        path that has stopped resolving -- which at hook-launch time would be a
        silent, non-blocking failure.
    """
    try:
        raw = settings_path.read_text()
        data = json.loads(raw) if raw.strip() else {}
    except OSError, json.JSONDecodeError:
        return []

    pre_tool_use = data.get("hooks", {}).get("PreToolUse", [])
    if not isinstance(pre_tool_use, list):
        return []

    findings: List[dict] = []
    for entry in pre_tool_use:
        if not isinstance(entry, dict):
            continue
        matcher = entry.get("matcher", "")
        for hook in entry.get("hooks", []):
            if not isinstance(hook, dict):
                continue
            command = hook.get("command", "")
            if not isinstance(command, str) or "toolguard" not in command.lower():
                continue
            hardened = f"-m {_HOOK_MODULE}" in command
            interpreter_missing = hardened and _interpreter_missing(command)
            findings.append(
                {
                    "matcher": matcher,
                    "command": command,
                    "hardened": hardened,
                    "interpreter_missing": interpreter_missing,
                }
            )
    return findings


def cmd_skills_status(args: argparse.Namespace) -> int:
    """
    Handle the ``skills-status`` subcommand: report install freshness. READ-ONLY.

    Args:
        args: Parsed CLI arguments; must have ``project_dir``, ``format``.

    Returns:
        ``0``. The exit code carries no findings -- this is a diagnostic, not a
        pass/fail gate.

    Raises:
        InstallerError: An :class:`OSError` prevented reading one of the checked
            paths. A missing or invalid skill, or an undeterminable binary
            status, is a reportable outcome, not an error.
    """
    project_dir = args.project_dir or str(Path.cwd())
    scoped_claude_dirs = (
        ("user", _claude_dir("user", None)),
        ("project", _claude_dir("project", project_dir)),
    )
    scoped_settings_paths = (
        ("user", _settings_path("user", None)),
        ("project", _settings_path("project", project_dir)),
    )

    try:
        skills = [
            {
                "skill": skill_name,
                "scope": scope,
                "path": str(claude_dir / "skills" / skill_name),
                "status": _classify_skill_dir(claude_dir / "skills" / skill_name),
            }
            for skill_name in _BUNDLED_SKILL_NAMES
            for scope, claude_dir in scoped_claude_dirs
        ]
        binary = _binary_status()
        hook_registrations = [
            {"scope": scope, **finding}
            for scope, settings_path in scoped_settings_paths
            for finding in _hook_registration_findings(settings_path)
        ]
    except OSError as exc:
        raise InstallerError(f"could not read installation state: {exc}") from exc

    if args.format == "json":
        print(
            json.dumps(
                {
                    "binary": binary,
                    "skills": skills,
                    "hook_registrations": hook_registrations,
                },
                indent=2,
            )
        )
        return 0

    print("binary install status:")
    print(f"  kind: {binary['kind']}")
    if binary["installed_commit"]:
        print(f"  installed commit: {binary['installed_commit']}")
    if binary["remote_commit"]:
        print(f"  remote commit: {binary['remote_commit']}")
    if binary["update_available"] is None:
        print(f"  update status: unknown ({binary['note']})")
    elif binary["update_available"]:
        print("  update status: UPDATE AVAILABLE -- run: uv tool upgrade toolguard")
    else:
        print("  update status: up to date")

    print(f"\nbundled skills (project dir: {project_dir}):")
    for skill_name in _BUNDLED_SKILL_NAMES:
        print(f"  {skill_name}:")
        for entry in skills:
            if entry["skill"] != skill_name:
                continue
            print(f"    {entry['scope']} ({entry['path']}): {entry['status']}")

    print("\nPreToolUse hook registration (TOO-19):")
    if not hook_registrations:
        print("  none found")
    for reg in hook_registrations:
        if reg["hardened"] and reg["interpreter_missing"]:
            status = "HARDENED but interpreter path NO LONGER EXISTS -- BROKEN"
        elif reg["hardened"]:
            status = "hardened"
        else:
            status = (
                "UNHARDENED -- re-run register-hooks to switch to the "
                "-E -P -m toolguard.hook form"
            )
        print(f"  {reg['scope']} matcher '{reg['matcher']}': {status}")
        print(f"    command: {reg['command']}")
    return 0


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

_TOP_LEVEL_DESCRIPTION = """\
toolguard-install: an AGENT-FACING installer helper for toolguard.

This tool exists to be driven by an AI coding agent following the guided install
runbook at docs/install.md in the toolguard repository. Each subcommand performs one
mechanical, journaled, reversible step (writing a config file, registering hooks,
seeding self-permissions, enabling takeover, or appending a journal entry) so the
agent issues ONE approvable command per step instead of several separate file edits.

This tool is not intended for direct human use. There is no interactive confirmation
and no undo beyond the install journal; the flags assume the calling agent already
worked through the consent/decision steps in docs/install.md. If you are a human
running this by hand: use it at your own risk, and read each subcommand's --help
(and docs/install.md) first.
"""


def _add_scope_args(parser: argparse.ArgumentParser) -> None:
    """Add the shared ``--scope``/``--project-dir`` options to a subparser."""
    parser.add_argument(
        "--scope",
        required=True,
        choices=("user", "project"),
        help="'user' (~/.claude, applies to every project) or 'project' "
        "(<project-dir>/.claude, applies to one repo)",
    )
    parser.add_argument(
        "--project-dir",
        default=None,
        help="project root; required when --scope is 'project', invalid otherwise",
    )


def _build_parser() -> argparse.ArgumentParser:
    """Build the ``toolguard-install`` argument parser and its subcommands."""
    parser = argparse.ArgumentParser(
        prog="toolguard-install",
        description=_TOP_LEVEL_DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p = subparsers.add_parser(
        "init-state",
        description=_INIT_STATE_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="create ~/.toolguard and its README/journal (idempotent)",
    )
    p.add_argument(
        "--source",
        required=True,
        help="where toolguard was installed from (recorded in README.txt)",
    )
    p.set_defaults(func=cmd_init_state)

    p = subparsers.add_parser(
        "write-config",
        description=_WRITE_CONFIG_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="write the base toolguard_hook.toml (takeover disabled)",
    )
    _add_scope_args(p)
    p.add_argument(
        "--governed-tools",
        required=True,
        help="comma-separated tool names, e.g. Bash,Read,Write,Edit",
    )
    p.add_argument(
        "--additional-supported-tools",
        default="",
        help="comma-separated custom MCP command tools (default: none)",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite an existing config (backs it up first)",
    )
    p.set_defaults(func=cmd_write_config)

    p = subparsers.add_parser(
        "register-hooks",
        description=_REGISTER_HOOKS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="merge PreToolUse/SessionStart hooks into settings.json/settings.local.json",
    )
    _add_scope_args(p)
    p.add_argument(
        "--binary", required=True, help="path to the installed toolguard hook binary"
    )
    p.add_argument(
        "--governed-tools",
        required=True,
        help="comma-separated tool names to add PreToolUse matchers for",
    )
    p.set_defaults(func=cmd_register_hooks)

    p = subparsers.add_parser(
        "seed-self-perms",
        description=_SEED_SELF_PERMS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="add toolguard's own self-permission rules to an existing config",
    )
    _add_scope_args(p)
    p.set_defaults(func=cmd_seed_self_perms)

    p = subparsers.add_parser(
        "enable-takeover",
        description=_ENABLE_TAKEOVER_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="set [takeover_mode] enabled = true in an existing config",
    )
    _add_scope_args(p)
    p.add_argument(
        "--no-match-fallback",
        choices=(
            "ask",
            "deny",
            "allow_with_warning",
            "allow",
            "allow_with_no_warnings",
        ),
        default="ask",
        help="what an unmatched command resolves to when the tool has rules but "
        "none match (default: ask)",
    )
    p.set_defaults(func=cmd_enable_takeover)

    p = subparsers.add_parser(
        "journal",
        description=_JOURNAL_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="append a numbered entry to ~/.toolguard/install-journal.md",
    )
    p.add_argument("--action", required=True, help="what was done")
    p.add_argument("--reverse", required=True, help="the exact reverse action")
    p.add_argument(
        "--backup",
        default=None,
        help="path to a backup file made for this change, if any",
    )
    p.set_defaults(func=cmd_journal)

    p = subparsers.add_parser(
        "discover-projects",
        description=_DISCOVER_PROJECTS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="list migration candidate projects (read-only)",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    p.set_defaults(func=cmd_discover_projects)

    p = subparsers.add_parser(
        "install-skills",
        description=_INSTALL_SKILLS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="install toolguard's bundled skills into the chosen scope",
    )
    _add_scope_args(p)
    p.add_argument(
        "--source",
        required=True,
        help="local checkout directory or git remote URL to install skills from",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="overwrite an already-installed skill (backs it up first)",
    )
    p.set_defaults(func=cmd_install_skills)

    p = subparsers.add_parser(
        "seed-hard-deny",
        description=_SEED_HARD_DENY_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="add the canonical [hard_deny] sensitive-file protections",
    )
    _add_scope_args(p)
    p.set_defaults(func=cmd_seed_hard_deny)

    p = subparsers.add_parser(
        "skills-status",
        description=_SKILLS_STATUS_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report toolguard binary/skills install freshness (read-only)",
    )
    p.add_argument(
        "--project-dir",
        default=None,
        help="project root to check for project-scope skills "
        "(default: current working directory)",
    )
    p.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="output format (default: text)",
    )
    p.set_defaults(func=cmd_skills_status)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Entry point for the ``toolguard-install`` console script.

    Args:
        argv: Argument list (excluding the program name); defaults to ``sys.argv[1:]``.

    Returns:
        The subcommand's own exit code -- ``0`` on success, ``2`` when it
        refuses -- or ``2`` for an :class:`InstallerError` (unmet
        precondition) or a
        :class:`~toolguard.config_write_guard.ConfigWriteVerificationError`
        (a config write refused as corrupt or pattern-dropping; the file on
        disk is untouched either way).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (InstallerError, ConfigWriteVerificationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
