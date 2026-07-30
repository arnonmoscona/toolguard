"""
An isolated, throwaway toolguard project for behavioural experiments.

Why this exists
---------------
Answering "what would toolguard decide for this command under this config?" used
to be done by editing live configuration and watching what happened. That is
privilege escalation (toolguard governs the agent, so the agent editing
toolguard's config is the agent editing its own permissions), and because these
files are typically not under version control, a mistake is unrecoverable. It
happened twice in TOO-19; see the task memory
``Safe Experimentation Mechanism - Design Proposal``.

This module makes the safe path the easy path::

    with experiment(project_config='[permissions]\\nallow = ["Bash(ls *)"]') as s:
        print(s.evaluate("Bash", "ls -la").verdict)      # 'allow'
        print(s.evaluate("Bash", "rm -rf /").verdict)    # 'deny' or 'ask'

Isolation is STRUCTURAL, not by discipline
------------------------------------------
Four anchors decide what configuration toolguard sees, and all four are
redirected inward for the lifetime of the context:

- ``Path.home()`` is patched to the sandbox's fake home. Both candidate rules
  directories (``~/.toolguard/rules`` and ``~/.config/toolguard/rules``) derive
  from it, so both are isolated by this single patch -- but see
  ``XDG_CONFIG_HOME`` below, which can redirect the second one back out.
- ``toolguard.config.find_project_root`` is patched to the sandbox project.
- The environment is CLEARED and rebuilt. ``CLAUDE_SETTINGS_PATH``,
  ``TOOLGUARD_PROJECT_ROOT`` and ``CLAUDE_PROJECT_DIR`` are removed (an exported
  ``CLAUDE_SETTINGS_PATH`` already caused a phantom "descendant config governs
  parent" bug in TOO-15), and ``XDG_CONFIG_HOME`` is pointed INSIDE the sandbox
  rather than merely unset.
- A **tripwire** raises :class:`SandboxEscapeError` on any filesystem write whose
  resolved path falls outside the sandbox root. An experiment that *would* touch
  live configuration fails loudly instead of succeeding quietly. This is what
  makes the sandbox safe by construction rather than safe by inspection.

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
from toolguard.tools.decision import decide

__all__ = [
    "SandboxEscapeError",
    "Sandbox",
    "experiment",
    "main",
]


class SandboxEscapeError(AssertionError):
    """
    Raised when sandboxed code attempts a filesystem write outside the sandbox.

    Deliberately an :class:`AssertionError` subclass: an escape is a failed
    safety invariant, not an ordinary runtime error, and it should never be
    swallowed by a broad ``except Exception`` in code under test.
    """


#: Environment variables that must never leak INTO a sandbox. Each one can
#: redirect toolguard's config discovery back out at the real filesystem.
SCRUBBED_ENV_VARS = (
    "CLAUDE_SETTINGS_PATH",
    "TOOLGUARD_PROJECT_ROOT",
    "CLAUDE_PROJECT_DIR",
    "XDG_CONFIG_HOME",
)

#: Variables preserved from the real environment because clearing them breaks
#: subprocess execution itself rather than affecting config discovery.
_PRESERVED_ENV_VARS = ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT")

_WRITE_MODE_CHARS = frozenset("wxa+")


def _is_benign_write(path_str: str) -> bool:
    """
    Return True for writes the tripwire deliberately ignores.

    Only bytecode caching qualifies: importing a module inside the context can
    write ``__pycache__`` entries next to the source, which is unrelated to
    configuration and would otherwise make the tripwire unusable.

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
    ``pathlib.Path.write_text`` reaches ``io.open`` rather than
    ``builtins.open``, so both names are patched.

    In-process only. Writes performed by a SUBPROCESS cannot be observed this
    way; :meth:`Sandbox.run_hook` isolates those by environment instead (see its
    docstring).
    """

    def __init__(self, root: Path):
        """
        Args:
            root: The sandbox root. Writes resolving outside it raise.
        """
        self._root = root.resolve()
        self._stack = contextlib.ExitStack()

    def _check(self, target: Any, operation: str) -> None:
        """
        Raise :class:`SandboxEscapeError` if ``target`` lies outside the sandbox.

        Args:
            target: The path being written to (any os.PathLike or str).
            operation: Name of the attempted operation, for the error message.

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
        try:
            resolved = Path(path_str).resolve()
        except (OSError, ValueError):
            resolved = Path(os.path.abspath(path_str))
        if resolved == self._root or self._root in resolved.parents:
            return
        raise SandboxEscapeError(
            f"Sandbox escape: {operation} targeted {resolved}, which is outside "
            f"the sandbox root {self._root}. Experiments must never write to real "
            f"configuration; place the file inside the sandbox instead."
        )

    def _guarded_open(self, real_open):
        """
        Wrap an ``open``-like callable so write modes are location-checked.

        Args:
            real_open: The original callable (``builtins.open`` or ``io.open``).

        Returns:
            A callable with the same signature that checks write-mode calls.
        """

        def guarded(file, mode="r", *args, **kwargs):
            if _WRITE_MODE_CHARS & set(mode):
                self._check(file, f"open(mode={mode!r})")
            return real_open(file, mode, *args, **kwargs)

        return guarded

    def _guarded_unary(self, real_func, name: str):
        """
        Wrap a function whose FIRST positional argument is the write target.

        Args:
            real_func: The original callable.
            name: Operation name used in the escape message.

        Returns:
            A callable that checks its first argument, then delegates.
        """

        def guarded(target, *args, **kwargs):
            self._check(target, name)
            return real_func(target, *args, **kwargs)

        return guarded

    def _guarded_destination(self, real_func, name: str):
        """
        Wrap a function whose SECOND positional argument is the destination.

        Covers ``os.replace``/``os.rename`` and the ``shutil`` copy/move family,
        where the source may legitimately be outside the sandbox (reading is
        always allowed) but the destination must not be.

        Args:
            real_func: The original callable.
            name: Operation name used in the escape message.

        Returns:
            A callable that checks its destination argument, then delegates.
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

        path_targets = ("write_text", "write_bytes", "mkdir", "touch", "unlink",
                        "rmdir", "chmod", "symlink_to")
        for attr in path_targets:
            real = getattr(Path, attr)
            name = f"pathlib.Path.{attr}"

            def make(real_method, op_name):
                def guarded(inner_self, *args, **kwargs):
                    self._check(inner_self, op_name)
                    return real_method(inner_self, *args, **kwargs)

                return guarded

            self._stack.enter_context(
                patch.object(Path, attr, make(real, name))
            )

        return self

    def __exit__(self, *exc_info) -> None:
        """Remove every guard."""
        self._stack.__exit__(*exc_info)


class Sandbox:
    """
    A fully isolated fake project for evaluating toolguard configuration.

    Do not construct directly -- use :func:`experiment`, which manages setup and
    teardown.

    Attributes:
        root: The sandbox root directory (a temporary directory).
        home: The fake ``$HOME``; ``Path.home()`` resolves here.
        project: The fake project root, carrying a ``.git`` marker.
        log_dir: Where toolguard writes decision logs inside the sandbox.
    """

    def __init__(self, root: Path):
        """
        Args:
            root: An existing empty directory to build the sandbox inside.
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

        Args:
            level: ``'project'`` or ``'user'``.

        Returns:
            The corresponding path.

        Raises:
            ValueError: If the level is unknown.
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

        ``toolguard.config._parse_config_file_cached`` is an unbounded
        ``lru_cache`` keyed by path and mtime. Sandbox files are written and
        rewritten rapidly inside one process, so a stale entry would silently
        make an experiment evaluate the PREVIOUS config -- the single most
        misleading failure this module could have.
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
        Resolve one permission decision through the REAL decision path.

        Delegates to :func:`toolguard.tools.decision.decide`, the same
        side-effect-free primitive that backs the live hook and ``--eval``, so a
        verdict here matches the hook's by construction rather than by
        re-implementation.

        Because ``decide`` is side-effect-free it writes no log; use
        :meth:`run_hook` when the log output itself is what you need.

        Args:
            tool: ``'Bash'``, ``'Read'``, ``'Write'``, or ``'Edit'``.
            target: The command string (Bash) or file path (file tools).
            extended_syntax: Whether extended regex/glob prefixes are honoured.

        Returns:
            A :class:`toolguard.tools.decision.Decision`.
        """
        return decide(self.load_configuration(), tool, target, extended_syntax)

    def run_hook(self, payload: Mapping[str, Any]) -> Dict[str, Any]:
        """
        Run the real hook binary end-to-end in a subprocess.

        Higher fidelity than :meth:`evaluate` (it exercises argument parsing,
        stdin handling, logging and JSON output), at the cost of process startup.

        **Tripwire caveat, stated plainly:** the tripwire patches this process
        only, so it cannot observe a subprocess's writes. Isolation here is by
        ENVIRONMENT instead -- the child receives the sandbox's ``HOME``,
        ``XDG_CONFIG_HOME`` and log directory, and the scrubbed variables are
        absent -- which is sound but a genuinely weaker guarantee. Prefer
        :meth:`evaluate` unless you specifically need end-to-end behaviour.

        Args:
            payload: The hook event dict. ``cwd`` defaults to the sandbox
                project and ``hook_event_name`` to ``'PreToolUse'`` when not
                supplied, so callers can pass just ``tool_name`` and
                ``tool_input`` for the common case.

        Returns:
            The hook's parsed JSON output, plus ``_stderr`` and ``_returncode``
            keys for diagnosis.
        """
        event = dict(payload)
        event.setdefault("cwd", str(self.project))
        event.setdefault("hook_event_name", "PreToolUse")
        event.setdefault("session_id", "sandbox")
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
            A minimal environment pointing every discovery anchor inward.
        """
        env = {
            key: os.environ[key]
            for key in _PRESERVED_ENV_VARS
            if key in os.environ
        }
        env["HOME"] = str(self.home)
        env["USERPROFILE"] = str(self.home)
        env["XDG_CONFIG_HOME"] = str(self.home / ".config")
        env["TOOLGUARD_LOG_DIR"] = str(self.log_dir)
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
        return env

    def trace(self) -> list:
        """
        Return the toolguard decision-log lines produced inside the sandbox.

        Only :meth:`run_hook` produces log output; :meth:`evaluate` is
        side-effect-free by design and contributes nothing here.

        Returns:
            All log lines from the sandbox log directory, in file order.
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
    Create a fully isolated toolguard project for the duration of the block.

    Args:
        project_config: TOML text for the project ``toolguard_hook.toml``.
        user_config: TOML text for the user-level ``toolguard_hook.toml``.
        hard_deny: Patterns for a ``[hard_deny]`` section appended to the
            USER-level config, matching how hard denies are normally declared
            (at the user level, so no project can weaken them).
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

        env = {
            key: os.environ[key]
            for key in _PRESERVED_ENV_VARS
            if key in os.environ
        }
        env["HOME"] = str(sandbox.home)
        env["XDG_CONFIG_HOME"] = str(sandbox.home / ".config")
        env["TOOLGUARD_LOG_DIR"] = str(sandbox.log_dir)

        Sandbox._invalidate_config_cache()
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(Path, "home", return_value=sandbox.home))
            stack.enter_context(patch.dict(os.environ, env, clear=True))
            stack.enter_context(
                patch("toolguard.config.find_project_root", return_value=sandbox.project)
            )
            stack.enter_context(_Tripwire(sandbox.root))
            try:
                yield sandbox
            finally:
                Sandbox._invalidate_config_cache()


def _build_argparser() -> argparse.ArgumentParser:
    """
    Build the command-line parser for ad-hoc experiments.

    Returns:
        The configured parser.
    """
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
    project_config = Path(args.config).read_text(encoding="utf-8") if args.config else None
    user_config = (
        Path(args.user_config).read_text(encoding="utf-8") if args.user_config else None
    )

    with experiment(
        project_config=project_config,
        user_config=user_config,
        hard_deny=args.hard_deny or None,
    ) as sandbox:
        decision = sandbox.evaluate(args.tool, args.command)

    if args.json:
        print(
            json.dumps(
                {
                    "tool": decision.tool,
                    "target": decision.target,
                    "verdict": decision.verdict,
                    "reason": decision.reason,
                },
                indent=2,
            )
        )
    else:
        print(f"verdict: {decision.verdict}")
        print(f"reason : {decision.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
