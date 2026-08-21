"""
An isolated, throwaway toolguard project for behavioural experiments.

Answering "what would toolguard decide for this command under this config?" by
editing live configuration is privilege escalation -- toolguard governs the
agent, so the agent editing toolguard's config is the agent editing its own
permissions -- and those files are typically not under version control, so a
mistake is unrecoverable. This module makes the safe path the easy path::

    with experiment(project_config='[permissions]\\nallow = ["Bash(ls *)"]') as s:
        print(s.evaluate("Bash", "ls -la").decision)      # 'allow'
        print(s.evaluate("Bash", "rm -rf /").decision)    # 'ask'

Isolation is STRUCTURAL, not by discipline
------------------------------------------
Three config-discovery anchors are redirected inward for the lifetime of the
context, and a tripwire catches whatever gets past them:

- ``Path.home()`` is patched to the sandbox's fake home. Both candidate rules
  directories derive from it -- but ``~/.config/toolguard/rules`` follows
  ``XDG_CONFIG_HOME`` whenever that is set, so that variable is pointed INSIDE
  the sandbox rather than merely unset.
- ``toolguard.config.find_project_root`` is patched to the sandbox project.
- The environment is CLEARED and rebuilt, so anything not rebuilt is absent
  rather than overridden (see :data:`SCRUBBED_ENV_VARS`).
- The tripwire raises :class:`SandboxEscapeError` on any in-process write
  resolving outside the sandbox root, so an experiment that *would* touch live
  configuration fails loudly instead of succeeding quietly.

Promotion rule
--------------
Anything worth running twice should become a unit test. The sandbox object is
the same in both places, so promotion is copy-paste.
"""

import argparse
import builtins
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, Mapping, Optional, Sequence
from unittest.mock import patch

from toolguard import config as toolguard_config
from toolguard.api import decide
from toolguard.claude_code_contract import (
    CWD_KEY,
    HOOK_EVENT_NAME_KEY,
    PRE_TOOL_USE_EVENT,
    SESSION_ID_KEY,
)

__all__ = [
    "SandboxEscapeError",
    "Sandbox",
    "experiment",
    "main",
]


class SandboxEscapeError(AssertionError):
    """
    Raised when sandboxed code attempts a filesystem write outside the sandbox.

    An :class:`AssertionError` subclass, so a broad ``except Exception`` in the
    code under test will swallow it.
    """


#: Environment variables a sandbox must not inherit. Declarative only: the
#: scrubbing is the wholesale environment clear in :func:`experiment`, which
#: does not read this tuple.
SCRUBBED_ENV_VARS = (
    "CLAUDE_SETTINGS_PATH",
    "TOOLGUARD_PROJECT_ROOT",
    "CLAUDE_PROJECT_DIR",
    "XDG_CONFIG_HOME",
)

#: The only real-environment variables carried into a sandbox.
_PRESERVED_ENV_VARS = ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")

_WRITE_MODE_CHARS = frozenset("wxa+")


def _is_benign_write(path_str: str) -> bool:
    """
    Return True for writes the tripwire deliberately ignores.

    Only bytecode caching: importing a module inside the context can write
    ``__pycache__`` entries next to the source, which would otherwise make the
    tripwire unusable.

    Args:
        path_str: The write target, as a string.

    Returns:
        True if this write should be permitted regardless of location.
    """
    return "__pycache__" in path_str or path_str.endswith((".pyc", ".pyo"))


class _Tripwire:
    """
    Patches the filesystem write surface so escapes raise instead of succeeding.

    The guarded surface is deliberately broad -- ``pathlib``, ``os``, ``shutil``
    and the two ``open`` bindings -- because a tripwire that covers only the
    obvious call is a tripwire that quietly fails on the one call that mattered.
    ``pathlib`` reaches ``io.open`` rather than ``builtins.open``, so both names
    are patched. Reads are never checked.

    In-process only: a SUBPROCESS's writes cannot be observed this way, which is
    why :meth:`Sandbox.run_hook` isolates by environment instead.
    """

    def __init__(self, root: Path):
        """
        Args:
            root: The sandbox root. Writes resolving outside it raise.
        """
        self._root = root.resolve()
        self._stack = contextlib.ExitStack()

    def _check(
        self, target: Any, operation: str, *, dir_fd: Optional[int] = None
    ) -> None:
        """
        Raise :class:`SandboxEscapeError` if ``target`` lies outside the sandbox.

        Args:
            target: The path being written to (any os.PathLike or str).
            operation: Name of the attempted operation, for the error message.
            dir_fd: When given and ``target`` is relative, the directory it is
                relative to -- e.g. Python 3.14's ``shutil.rmtree``, which descends
                via ``os.rmdir(name, dir_fd=...)``. That is relative to the open
                directory, not to cwd, so resolving a bare name against cwd here
                would compare a path the call never named.

        Raises:
            SandboxEscapeError: If the resolved target is outside the sandbox.
        """
        try:
            path_str = os.fspath(target)
        except TypeError:
            # Not a path at all (e.g. an already-open file descriptor). Nothing
            # to attribute a location to, so let it through rather than guess.
            return
        if not isinstance(path_str, str):
            path_str = path_str.decode("utf-8", "replace")
        if _is_benign_write(path_str):
            return
        if dir_fd is not None and not os.path.isabs(path_str):
            try:
                base = os.readlink(f"/proc/self/fd/{dir_fd}")
            except OSError:
                # No /proc (non-Linux) or the fd no longer resolves. A bare name
                # is meaningless without its directory, so fail closed rather
                # than fall back to a cwd-relative guess that could be wrong in
                # either direction.
                raise SandboxEscapeError(
                    f"Sandbox escape check: {operation} targeted {path_str!r} "
                    f"relative to dir_fd={dir_fd}, whose real directory could "
                    "not be resolved on this platform."
                )
            resolved = Path(base, path_str).resolve()
        else:
            try:
                resolved = Path(path_str).resolve()
            except OSError, ValueError:
                resolved = Path(os.path.abspath(path_str))
        if resolved == self._root or self._root in resolved.parents:
            return
        raise SandboxEscapeError(
            f"Sandbox escape: {operation} targeted {resolved}, which is outside "
            f"the sandbox root {self._root}. Experiments must never write to real "
            f"configuration; place the file inside the sandbox instead."
        )

    def _guarded_open(self, real_open):
        """Wrap an ``open``-like callable so write modes are location-checked."""

        def guarded(file, mode="r", *args, **kwargs):
            if _WRITE_MODE_CHARS & set(mode):
                self._check(file, f"open(mode={mode!r})")
            return real_open(file, mode, *args, **kwargs)

        return guarded

    def _guarded_unary(self, real_func, name: str):
        """
        Wrap a function whose FIRST positional argument is the write target.

        Forwards a ``dir_fd`` keyword to :meth:`_check` unexamined -- several of the
        wrapped functions (``os.rmdir``, ``os.unlink``, ``os.mkdir``, ...) accept one,
        and a relative target under it is not relative to cwd.
        """

        def guarded(target, *args, **kwargs):
            self._check(target, name, dir_fd=kwargs.get("dir_fd"))
            return real_func(target, *args, **kwargs)

        return guarded

    def _guarded_destination(self, real_func, name: str):
        """
        Wrap a function whose SECOND positional argument is the destination.

        For the copy/move/rename family, where the source may legitimately be
        outside the sandbox but the destination must not be.
        """

        def guarded(src, dst, *args, **kwargs):
            self._check(dst, name)
            return real_func(src, dst, *args, **kwargs)

        return guarded

    def __enter__(self) -> "_Tripwire":
        """Install every guard and return self."""
        self._stack.__enter__()

        for module, attr in (("builtins", "open"), ("io", "open")):
            real = getattr(builtins if module == "builtins" else io, attr)
            self._stack.enter_context(
                patch(f"{module}.{attr}", self._guarded_open(real))
            )

        unary_targets = [
            (os, "remove"),
            (os, "unlink"),
            (os, "rmdir"),
            (os, "mkdir"),
            (os, "makedirs"),
            (os, "truncate"),
            (shutil, "rmtree"),
        ]
        for module, attr in unary_targets:
            real = getattr(module, attr)
            name = f"{module.__name__}.{attr}"
            self._stack.enter_context(patch(name, self._guarded_unary(real, name)))

        destination_targets = [
            (os, "replace"),
            (os, "rename"),
            (shutil, "copy"),
            (shutil, "copy2"),
            (shutil, "copyfile"),
            (shutil, "move"),
        ]
        for module, attr in destination_targets:
            real = getattr(module, attr)
            name = f"{module.__name__}.{attr}"
            self._stack.enter_context(
                patch(name, self._guarded_destination(real, name))
            )

        path_targets = (
            "write_text",
            "write_bytes",
            "mkdir",
            "touch",
            "unlink",
            "rmdir",
            "chmod",
            "symlink_to",
        )
        for attr in path_targets:
            real = getattr(Path, attr)
            name = f"pathlib.Path.{attr}"

            def make(real_method, op_name):
                def guarded(inner_self, *args, **kwargs):
                    self._check(inner_self, op_name)
                    return real_method(inner_self, *args, **kwargs)

                return guarded

            self._stack.enter_context(patch.object(Path, attr, make(real, name)))

        return self

    def __exit__(self, *exc_info) -> None:
        """Remove every guard."""
        self._stack.__exit__(*exc_info)


class Sandbox:
    """
    An isolated fake project for evaluating toolguard configuration.

    Do not construct directly -- use :func:`experiment`, which manages setup,
    teardown and the tripwire.

    Attributes:
        root: The sandbox root directory (a temporary directory).
        home: The fake ``$HOME``; ``Path.home()`` resolves here.
        project: The fake project root, carrying a ``.git`` marker.
        log_dir: Where toolguard's logs land inside the sandbox.
    """

    def __init__(self, root: Path):
        """
        Args:
            root: A directory to build the sandbox layout inside.
        """
        self.root = root
        self.home = root / "home"
        self.project = root / "project"
        self.log_dir = root / "logs"
        for directory in (
            self.home / ".claude",
            self.home / ".toolguard" / "rules",
            self.home / ".config" / "toolguard" / "rules",
            self.project / ".claude",
            self.project / ".git",
            self.log_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    # -- paths ---------------------------------------------------------------

    @property
    def project_config_path(self) -> Path:
        """Path to the sandbox's project-level ``toolguard_hook.toml``."""
        return self.project / ".claude" / "toolguard_hook.toml"

    @property
    def user_config_path(self) -> Path:
        """Path to the sandbox's user-level ``toolguard_hook.toml``."""
        return self.home / ".claude" / "toolguard_hook.toml"

    @property
    def toolguard_rules_dir(self) -> Path:
        """The sandbox's ``~/.toolguard/rules`` directory."""
        return self.home / ".toolguard" / "rules"

    @property
    def xdg_rules_dir(self) -> Path:
        """The sandbox's ``~/.config/toolguard/rules`` directory."""
        return self.home / ".config" / "toolguard" / "rules"

    # -- config authoring ----------------------------------------------------

    def write_config(self, text: str, *, level: str = "project") -> Path:
        """
        Write a toolguard config file inside the sandbox.

        Args:
            text: Full TOML text of the config file.
            level: ``'project'`` or ``'user'``.

        Returns:
            The path written.

        Raises:
            ValueError: If ``level`` is not 'project' or 'user'.
        """
        path = self._config_path_for(level)
        path.write_text(text, encoding="utf-8")
        self._invalidate_config_cache()
        return path

    def config_text(self, *, level: str = "project") -> str:
        """
        Read back a config file from the sandbox.

        Args:
            level: ``'project'`` or ``'user'``.

        Returns:
            The file's text, or ``''`` when the file does not exist.
        """
        path = self._config_path_for(level)
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def write_rules_file(self, name: str, text: str, *, xdg: bool = False) -> Path:
        """
        Write a rules file into one of the two optional rules directories.

        Args:
            name: File name, e.g. ``'git.rules.toml'``.
            text: Full TOML text.
            xdg: When True write to ``~/.config/toolguard/rules``; otherwise
                ``~/.toolguard/rules``.

        Returns:
            The path written.
        """
        directory = self.xdg_rules_dir if xdg else self.toolguard_rules_dir
        path = directory / name
        path.write_text(text, encoding="utf-8")
        self._invalidate_config_cache()
        return path

    def _config_path_for(self, level: str) -> Path:
        """
        Map a level name to its config path.

        Raises:
            ValueError: If *level* is not ``'project'`` or ``'user'``.
        """
        if level == "project":
            return self.project_config_path
        if level == "user":
            return self.user_config_path
        raise ValueError(f"level must be 'project' or 'user', got {level!r}")

    @staticmethod
    def _invalidate_config_cache() -> None:
        """
        Drop toolguard's parsed-config cache.

        That cache is keyed on the file's mtime and size. Sandbox configs are
        rewritten rapidly within one process, so a rewrite landing in the same
        mtime tick at the same size would hit a stale entry and silently make
        an experiment evaluate the PREVIOUS config.
        """
        toolguard_config._parse_config_file_cached.cache_clear()

    # -- evaluation ----------------------------------------------------------

    def load_configuration(self):
        """
        Load the sandbox's :class:`~toolguard.config.Configuration`.

        Returns:
            The resolved Configuration for the sandbox project.
        """
        self._invalidate_config_cache()
        return toolguard_config.load_configuration(str(self.project))

    def evaluate(self, tool: str, target: str, *, extended_syntax: bool = True):
        """
        Resolve one permission decision through :func:`toolguard.api.decide`.

        ``decide`` is the resolver the live hook and ``--eval`` also use, but it
        sits BELOW the hook's own gates: it does not consult ``governed_tools``
        and does not pull the target out of a tool-input payload. Evaluating an
        ungoverned tool here therefore returns the rules' verdict, where the
        hook would allow the call untouched. Use :meth:`run_hook` when that
        difference matters.

        ``decide`` is side-effect-free and writes no log.

        Args:
            tool: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
            target: The command string (Bash) or file path (file tools).
            extended_syntax: Whether extended regex/glob prefixes are honoured.

        Returns:
            A :class:`~toolguard.config_types.RuntimeVerdict`.
        """
        return decide(self.load_configuration(), tool, target, extended_syntax)

    def run_hook(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Run the real hook end-to-end in a subprocess.

        Higher fidelity than :meth:`evaluate` -- it exercises stdin handling,
        the ``governed_tools`` gate, logging and JSON output -- at the cost of
        process startup.

        **Tripwire caveat:** the tripwire patches this process only, so it
        cannot observe the child's writes. Isolation here is by ENVIRONMENT
        alone: the child gets the sandbox's ``HOME``, ``XDG_CONFIG_HOME`` and
        log directory, and inherits nothing else. That is sound but a weaker
        guarantee, so prefer :meth:`evaluate` unless you need the full path.

        Args:
            payload: The hook event dict. ``cwd``, ``hook_event_name`` and
                ``session_id`` are defaulted when absent, so the common case is
                just ``tool_name`` and ``tool_input``.

        Returns:
            The hook's parsed JSON output -- or ``{'_raw_stdout': ...}`` when
            stdout was not JSON -- plus ``_stderr`` and ``_returncode``.
        """
        event = dict(payload)
        event.setdefault(CWD_KEY, str(self.project))
        event.setdefault(HOOK_EVENT_NAME_KEY, PRE_TOOL_USE_EVENT)
        event.setdefault(SESSION_ID_KEY, "sandbox")
        completed = subprocess.run(
            [sys.executable, "-m", "toolguard.hook"],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=self._subprocess_env(),
            cwd=str(self.project),
        )
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result = {"_raw_stdout": completed.stdout}
        result["_stderr"] = completed.stderr
        result["_returncode"] = completed.returncode
        return result

    def _subprocess_env(self) -> Dict[str, str]:
        """
        Build the environment for :meth:`run_hook`'s child process.

        Returns:
            A minimal environment with every config-discovery anchor pointed
            inward, plus a ``PYTHONPATH`` that makes the child import the same
            toolguard package this module was loaded from.
        """
        env = {key: os.environ[key] for key in _PRESERVED_ENV_VARS if key in os.environ}
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["XDG_CONFIG_HOME"] = str(self.home / ".config")
        env["TOOLGUARD_LOG_DIR"] = str(self.log_dir)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        return env

    def trace(self) -> list:
        """
        Return the sandbox's markdown log lines -- decision log and warning log.

        Only :meth:`run_hook` produces log output; :meth:`evaluate` is
        side-effect-free by design and contributes nothing here.

        Returns:
            Lines from every ``*.md`` file in the sandbox log directory, ordered
            by filename. The non-markdown discovery log is not included.
        """
        lines: list = []
        for log_file in sorted(self.log_dir.glob("*.md")):
            lines.extend(log_file.read_text(encoding="utf-8").splitlines())
        return lines


@contextlib.contextmanager
def experiment(
    *,
    project_config: Optional[str] = None,
    user_config: Optional[str] = None,
    hard_deny: Optional[Sequence[str]] = None,
    settings_json: Optional[Any] = None,
    rules_files: Optional[Mapping[str, str]] = None,
    xdg_rules_files: Optional[Mapping[str, str]] = None,
) -> Iterator[Sandbox]:
    """
    Create an isolated toolguard project for the duration of the block.

    Args:
        project_config: TOML text for the project ``toolguard_hook.toml``.
        user_config: TOML text for the user-level ``toolguard_hook.toml``.
        hard_deny: Patterns for a ``[hard_deny]`` section appended to the
            USER-level config.
        settings_json: Native Claude settings for the project. A mapping is
            serialised; a string is written verbatim (so malformed JSON can be
            exercised deliberately).
        rules_files: Name -> TOML text, written to ``~/.toolguard/rules``.
        xdg_rules_files: Name -> TOML text, written to
            ``~/.config/toolguard/rules``.

    Yields:
        A :class:`Sandbox` with the tripwire armed.
    """
    with tempfile.TemporaryDirectory(prefix="toolguard-sandbox-") as tmp:
        sandbox = Sandbox(Path(tmp))

        if project_config is not None:
            sandbox.project_config_path.write_text(project_config, encoding="utf-8")
        combined_user = user_config or ""
        if hard_deny:
            rendered = ",\n    ".join(json.dumps(pattern) for pattern in hard_deny)
            combined_user += f"\n\n[hard_deny]\ndeny = [\n    {rendered}\n]\n"
        if combined_user:
            sandbox.user_config_path.write_text(combined_user, encoding="utf-8")
        if settings_json is not None:
            text = (
                settings_json
                if isinstance(settings_json, str)
                else json.dumps(settings_json, indent=2)
            )
            (sandbox.project / ".claude" / "settings.json").write_text(
                text, encoding="utf-8"
            )
        for name, text in (rules_files or {}).items():
            (sandbox.toolguard_rules_dir / name).write_text(text, encoding="utf-8")
        for name, text in (xdg_rules_files or {}).items():
            (sandbox.xdg_rules_dir / name).write_text(text, encoding="utf-8")

        env = {key: os.environ[key] for key in _PRESERVED_ENV_VARS if key in os.environ}
        env["HOME"] = str(sandbox.home)
        env["XDG_CONFIG_HOME"] = str(sandbox.home / ".config")
        env["TOOLGUARD_LOG_DIR"] = str(sandbox.log_dir)

        Sandbox._invalidate_config_cache()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(Path, "home", return_value=sandbox.home))
            stack.enter_context(patch.dict(os.environ, env, clear=True))
            stack.enter_context(
                patch(
                    "toolguard.config.find_project_root", return_value=sandbox.project
                )
            )
            stack.enter_context(_Tripwire(sandbox.root))
            try:
                yield sandbox
            finally:
                Sandbox._invalidate_config_cache()


def _build_argparser() -> argparse.ArgumentParser:
    """Build the command-line parser for ad-hoc experiments."""
    parser = argparse.ArgumentParser(
        prog="python -m toolguard.testing.sandbox",
        description=(
            "Evaluate a command against a toolguard config in a fully isolated "
            "sandbox. Never reads or writes your real configuration."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="File containing the PROJECT-level toolguard_hook.toml text.",
    )
    parser.add_argument(
        "--user-config",
        metavar="FILE",
        help="File containing the USER-level toolguard_hook.toml text.",
    )
    parser.add_argument(
        "--command",
        required=True,
        help="The command (Bash) or file path (Read/Write/Edit) to evaluate.",
    )
    parser.add_argument(
        "--tool",
        default="Bash",
        help="Tool name to evaluate as (default: Bash).",
    )
    parser.add_argument(
        "--hard-deny",
        action="append",
        default=[],
        metavar="PATTERN",
        help="Add a [hard_deny] pattern. Repeatable.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the verdict as JSON instead of human-readable text.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """
    CLI entry point: evaluate one command in a throwaway sandbox.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        Process exit code (0 = the evaluation ran; the verdict is on stdout).
    """
    args = _build_argparser().parse_args(argv)
    project_config = (
        Path(args.config).read_text(encoding="utf-8") if args.config else None
    )
    user_config = (
        Path(args.user_config).read_text(encoding="utf-8") if args.user_config else None
    )

    with experiment(
        project_config=project_config,
        user_config=user_config,
        hard_deny=args.hard_deny or None,
    ) as sandbox:
        decision = sandbox.evaluate(args.tool, args.command)

    # additionalContext is a real hook output field: a preview tool that
    # silently omitted part of what the live hook emits is worse than no
    # preview. Omitted rather than null when there is none, matching the hook's
    # own output shape.
    if args.json:
        payload = {
            "tool": decision.tool,
            "target": decision.target,
            "verdict": decision.decision,
            "reason": decision.reason,
        }
        if decision.additional_context:
            payload["additionalContext"] = decision.additional_context
        print(json.dumps(payload, indent=2))
    else:
        print(f"verdict: {decision.decision}")
        print(f"reason : {decision.reason}")
        if decision.additional_context:
            print(f"context: {decision.additional_context}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
