"""
The machine state toolguard reads: home directory, current directory, process
environment.

Nothing here reads the machine at import.

An entry point may bind one :class:`AmbientFacts` for the whole invocation via
:func:`active`; unbound, each accessor reads live. A binding governs reads that
come through this module, not reads the rest of the package makes directly.
"""

import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Generator, Mapping, Optional, Union


_UNRESOLVABLE = (OSError, RuntimeError)


@dataclass(frozen=True)
class AmbientFacts:
    """
    The machine state one invocation sees.

    Attributes:
        home: Home directory, or ``None`` where none could be resolved.
        cwd: Current directory, or ``None`` where none could be resolved.
        env: Snapshot of the process environment.
    """

    home: Optional[Path]
    cwd: Optional[Path]
    env: Mapping[str, str]


def resolve() -> AmbientFacts:
    """
    Read the machine now and return what it says.

    An unresolvable home or cwd is recorded as ``None`` rather than raising, and
    the accessors below then fall back to a live call, so the error surfaces at
    a caller that actually needs the value rather than at the entry point.
    """
    try:
        home = Path.home()
    except _UNRESOLVABLE:
        home = None
    try:
        cwd = Path.cwd()
    except _UNRESOLVABLE:
        cwd = None
    return AmbientFacts(home=home, cwd=cwd, env=MappingProxyType(dict(os.environ)))


#: The facts bound by :func:`active`; None outside any binding.
_active: Optional[AmbientFacts] = None


@contextmanager
def active(facts: AmbientFacts) -> Generator[None]:
    """
    Bind *facts* for the duration of the block. The accessors below report them,
    except that a ``None`` home or cwd falls through to a live call.

    Restores the previous binding on exit, including on an exception, so
    nothing carries into the next invocation in the same process. Call it once
    near a process entry point, not deep in resolution logic.
    """
    global _active
    previous = _active
    _active = facts
    try:
        yield
    finally:
        _active = previous


def home() -> Path:
    """The bound home directory, or a live lookup where that is unbound or None."""
    if _active is not None and _active.home is not None:
        return _active.home
    return Path.home()


def cwd() -> Path:
    """The bound current directory, or a live lookup where that is unbound or None."""
    if _active is not None and _active.cwd is not None:
        return _active.cwd
    return Path.cwd()


def env() -> Mapping[str, str]:
    """The bound environment snapshot, or a snapshot of the live one when unbound."""
    if _active is not None:
        return _active.env
    return MappingProxyType(dict(os.environ))


def env_var(name: str, default: Optional[str] = None) -> Optional[str]:
    """
    The value of environment variable *name*, or *default* where it is unset.
    Answers from :func:`env`, so an override there governs this too.
    """
    return env().get(name, default)


def expanduser(path: Union[str, Path]) -> Path:
    """
    *path* with a leading ``~`` replaced by :func:`home`, so an override there
    governs it. A ``~user`` form names somebody else's home and is left to
    :meth:`pathlib.Path.expanduser`.
    """
    expanded = Path(path)
    parts = expanded.parts
    if parts and parts[0] == "~":
        return home().joinpath(*parts[1:])
    return expanded.expanduser()
