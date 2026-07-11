"""
toolguard-install: an AGENT-FACING installer helper for toolguard (TOO-15).

This console script exists to be driven by an AI coding agent following the guided
install runbook at ``docs/install.md`` in the toolguard repository. Each subcommand
performs one mechanical, journaled, reversible step -- writing the base config,
registering hooks, seeding toolguard's own self-permission rules, enabling takeover
mode, or appending a journal entry -- so the agent issues ONE approvable
``Bash(toolguard-install ...)`` command per step instead of several separate
Read/Write/Edit tool calls (each of which would otherwise trigger its own Claude Code
permission prompt). Because the file writes happen inside this process, they never hit
Claude's own permission layer at all.

It is NOT a general-purpose installer and is deliberately NOT meant for direct human
use -- see the top-level ``--help`` text for the full warning. Every subcommand's own
``--help`` states exactly which files it reads/writes/backs up, the journal entry it
appends (action + reverse), its preconditions, and what it refuses to do, so an agent
can decide whether a step does exactly what is wanted without running it first.

Design notes
------------
- Every mutating subcommand backs up any file it is about to replace/edit into
  ``~/.toolguard/backups/`` (reusing
  :func:`toolguard.scripts.migrate_permissions.create_backup`) and appends exactly one
  numbered, reversible entry to ``~/.toolguard/install-journal.md`` (see
  :func:`_append_journal_entry`), matching the format documented in
  ``docs/install.md`` ("The install journal").
- All file writes are atomic (write to a sibling ``.tmp`` file, then ``Path.replace``)
  so a failure never leaves a half-written config, settings file, or journal.
- TOML writing reuses
  :func:`toolguard.scripts.migrate_permissions.write_toml_config` (preserves
  everything outside the ``[permissions]`` section) and
  :func:`toolguard.rule_sort.find_section_boundaries` (generic TOML section locator,
  reused here for ``[takeover_mode]``) rather than hand-rolling a TOML parser/writer.
- The self-permission rules seeded by ``seed-self-perms`` are the single source of
  truth in :mod:`toolguard.tools.self_permission` -- never re-declared here.
"""

import argparse
import json
import sys
import tomllib
from datetime import datetime
from pathlib import Path
from re import MULTILINE, compile as re_compile
from typing import List, Optional, Sequence, Tuple

from toolguard.rule_sort import find_section_boundaries
from toolguard.scripts.migrate_permissions import create_backup, write_toml_config
from toolguard.tools.self_permission import required_self_permissions


class InstallerError(Exception):
    """
    Raised for an expected, user-facing installer failure (never a programming bug).

    :func:`main` catches this at the top level, prints ``error: <message>`` to
    stderr, and returns a non-zero exit code -- callers (an agent) are expected to
    read the message and either fix the invocation or fall back to a manual step.
    """


# Numbered journal entry header, e.g. "## [3] 2026-07-07 14:12 local -- ...".
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
    """Return ``~/.toolguard`` (toolguard's per-user state directory)."""
    return Path.home() / ".toolguard"


def _backups_dir() -> Path:
    """Return ``~/.toolguard/backups`` (where every mutating step backs up to)."""
    return _state_dir() / "backups"


def _journal_path() -> Path:
    """Return ``~/.toolguard/install-journal.md``."""
    return _state_dir() / "install-journal.md"


def _ensure_state() -> None:
    """
    Create ``~/.toolguard`` (with ``backups/`` and ``stage/``) and the journal if absent.

    The mutating config subcommands call this before journaling so they work even
    when run standalone (before ``init-state``); it never clobbers an existing journal
    or README. The bare ``journal`` subcommand deliberately does NOT call this -- it
    requires ``init-state`` to have run first.
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
            raise InstallerError(
                "--project-dir is required when --scope is 'project'"
            )
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
    project's own ``settings.local.json`` (matching ``docs/agent-guides.md``).
    """
    claude_dir = _claude_dir(scope, project_dir)
    if scope == "user":
        return claude_dir / "settings.json"
    return claude_dir / "settings.local.json"


def _atomic_write_text(path: Path, content: str) -> None:
    """
    Write *content* to *path* atomically (temp file + rename).

    Ensures *path*'s parent directory exists. Writing to a sibling ``.tmp`` file and
    then calling :meth:`Path.replace` guarantees a reader never observes a
    half-written file, and that a failure partway through never corrupts the
    original.
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

    Requires ``~/.toolguard`` to already exist (i.e. ``init-state`` has run) --
    refuses to silently create the state directory here, since that would skip the
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
        raise InstallerError(f"{_state_dir()} does not exist -- run 'init-state' first.")
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
    _atomic_write_text(config_path, content)

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
matcher per governed tool pointing at --binary, plus a SessionStart matcher
pointing at "<--binary>-session-start".

Hooks are MERGED into any existing PreToolUse/SessionStart entries -- other
hook types already present (PostToolUse, SessionEnd, ...) and any matcher
already registered are left untouched (re-running for a tool that already has
a matcher does not add a duplicate).

Backs up the pre-edit file into ~/.toolguard/backups/ before writing (skipped
only if the file did not exist yet). Journals one entry naming the file
edited and the matchers added; its reverse is "restore the backup" (or
"delete the file" if it was freshly created).
"""


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
    session_start_binary = f"{binary}-session-start"

    backup_path: Optional[Path] = None
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
            {"matcher": tool, "hooks": [{"type": "command", "command": binary}]}
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

    _atomic_write_text(settings_path, json.dumps(data, indent=2) + "\n")

    reverse = (
        f"restore backup {backup_path} over {settings_path}"
        if backup_path
        else f"delete {settings_path}"
    )
    index = _append_journal_entry(
        action=(
            f"registered hooks at {args.scope} scope: edited {settings_path} to add "
            f"PreToolUse matchers for {','.join(added_matchers) or '(none new)'} and "
            f"a SessionStart hook at {session_start_binary}, pointing at {binary}"
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
    return 0


# ---------------------------------------------------------------------------
# seed-self-perms
# ---------------------------------------------------------------------------

_SEED_SELF_PERMS_HELP = """\
Add the allow/ask rules toolguard's own skills need to keep working, at the
chosen scope's toolguard_hook.toml.

Adds, to the [permissions] section:
  - one rule per entry in toolguard.tools.self_permission.required_self_permissions()
    (the single source of truth -- currently Bash(toolguard-audit:*) => allow and
    Bash(toolguard-maintain:*) => ask)
  - Read/Write/Edit(~/.toolguard/**) => allow, so toolguard's own state directory
    (the journal and its backups) stays readable/writable

Consent for these specific rules is ASSUMED to already have been obtained by
the calling agent (per docs/install.md Phase 10.1) -- this subcommand does not
itself prompt for consent.

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
        InstallerError: If no ``toolguard_hook.toml`` exists yet at this scope.
    """
    _ensure_state()
    config_path = _config_path(args.scope, args.project_dir)
    if not config_path.exists():
        raise InstallerError(f"{config_path} does not exist -- run 'write-config' first.")

    # Read the raw TOML directly: we need the true, unfiltered [permissions]
    # section to detect which self-permission rules are already present.
    current = tomllib.loads(config_path.read_text())
    current_permissions = current.get("permissions", {})
    permissions = {
        "allow": list(current_permissions.get("allow", [])),
        "deny": list(current_permissions.get("deny", [])),
        "ask": list(current_permissions.get("ask", [])),
    }

    candidates: List[Tuple[str, str]] = [
        (f"Bash({p.pattern})", p.list_type) for p in required_self_permissions()
    ]
    candidates += [(f"{tool}(~/.toolguard/**)", "allow") for tool in ("Read", "Write", "Edit")]

    added: List[Tuple[str, str]] = []
    already_present: List[Tuple[str, str]] = []
    for pattern, list_type in candidates:
        if pattern in permissions[list_type]:
            already_present.append((pattern, list_type))
        else:
            permissions[list_type].append(pattern)
            added.append((pattern, list_type))

    print(f"seeded self-permissions: {config_path}")
    if not added:
        print("  already present, no changes needed:")
        for pattern, list_type in already_present:
            print(f"    {pattern} -> {list_type}")
        return 0

    backup_path = create_backup(config_path, _backups_dir())
    write_toml_config(config_path, permissions, auto_sort=True)

    index = _append_journal_entry(
        action=(
            f"seeded self-permission rules into {config_path}: "
            + "; ".join(f"{p} -> {t}" for p, t in added)
        ),
        reverse=f"restore backup {backup_path} over {config_path}",
        backup=str(backup_path),
    )

    for pattern, list_type in added:
        print(f"  added: {pattern} -> {list_type}")
    if already_present:
        print("  already present, unchanged:")
        for pattern, list_type in already_present:
            print(f"    {pattern} -> {list_type}")
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
when the tool HAS rules but none match; the default is the gentle
"allow_with_warning" (allow, but flagged) so nothing breaks while rules are
still thin -- "deny" (fail-closed) and "ask" are also accepted.

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
        "[takeover_mode]\n"
        "enabled = true\n"
        f'no_match_fallback = "{no_match_fallback}"\n'
    )


def _replace_or_append_toml_section(
    text: str, section_name: str, new_section_text: str
) -> str:
    """
    Replace an existing ``[section_name]`` section in *text*, or append it.

    Reuses :func:`toolguard.rule_sort.find_section_boundaries` (the same locator
    ``write_toml_config`` uses for ``[permissions]``) so this needs no bespoke TOML
    parsing.

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
        raise InstallerError(f"{config_path} does not exist -- run 'write-config' first.")

    original = config_path.read_text()
    backup_path = create_backup(config_path, _backups_dir())

    new_section = _render_takeover_section(args.no_match_fallback)
    new_text = _replace_or_append_toml_section(original, "takeover_mode", new_section)
    _atomic_write_text(config_path, new_text)

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
    index = _append_journal_entry(action=args.action, reverse=args.reverse, backup=args.backup)
    print(f"appended journal entry [{index}] to {_journal_path()}")
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
    """Build the ``toolguard-install`` argument parser and its six subcommands."""
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
        choices=("ask", "deny", "allow_with_warning"),
        default="allow_with_warning",
        help="what an unmatched command resolves to when the tool has rules but "
        "none match (default: allow_with_warning)",
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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    Entry point for the ``toolguard-install`` console script.

    Args:
        argv: Argument list (excluding the program name); defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code: ``0`` on success, ``2`` on an expected
        :class:`InstallerError` (refusal or unmet precondition).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except InstallerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
