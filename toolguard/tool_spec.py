"""
Static description of a tool toolguard knows how to govern.

``foundation`` layer -- consumed by config (``config_validation``,
``config.governed_tools``), api, runtime (``hook``), and tooling
(``installer``, ``transcript_harvest``). The registry is static: it
describes structural facts (kind, payload key, whether the tool is built
into toolguard's own knowledge) about each tool. ``additional_supported_tools``
stays configurable and is not derived from here.
``config_validation.KNOWN_SUPPORTED_TOOLS`` consumes this registry
(TOO-45 punch-list #10); ``Configuration.governed_tools()`` consumes
``DEFAULT_GOVERNED_TOOLS`` for its no-configuration fallback.
"""

from dataclasses import dataclass
from enum import Enum


class ToolKind(Enum):
    """Whether a tool's subject is a shell command line or a file path."""

    COMMAND = "command"
    FILE = "file"


@dataclass(frozen=True)
class ToolSpec:
    """One governable tool: its name, kind, payload key, and built-in status."""

    name: str
    kind: ToolKind
    payload_key: str
    #: True for tools toolguard ships built-in knowledge of. This IS the
    #: default governed set (see :data:`DEFAULT_GOVERNED_TOOLS`) --
    #: ``Configuration.governed_tools()`` falls back to it only when no
    #: level in the hierarchy configures ``governed_tools`` explicitly.
    is_builtin: bool


# The registry. Adding a tool is one entry here; every derived view below
# picks it up automatically.
_REGISTRY: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="Bash",
        kind=ToolKind.COMMAND,
        payload_key="command",
        is_builtin=True,
    ),
    ToolSpec(
        name="Read",
        kind=ToolKind.FILE,
        payload_key="file_path",
        is_builtin=True,
    ),
    ToolSpec(
        name="Write",
        kind=ToolKind.FILE,
        payload_key="file_path",
        is_builtin=True,
    ),
    ToolSpec(
        name="Edit",
        kind=ToolKind.FILE,
        payload_key="file_path",
        is_builtin=True,
    ),
    ToolSpec(
        name="mcp__jetbrains__execute_terminal_command",
        kind=ToolKind.COMMAND,
        payload_key="command",
        is_builtin=False,
    ),
)


def _index_by_name(registry: tuple[ToolSpec, ...]) -> dict[str, ToolSpec]:
    """
    Index *registry* by name.

    Raises:
        ValueError: two entries share a ``name`` -- a duplicated registry
            entry must fail loudly at import, not collapse silently.
    """
    by_name: dict[str, ToolSpec] = {}
    for spec in registry:
        if spec.name in by_name:
            raise ValueError(f"Duplicate tool name in registry: {spec.name!r}")
        by_name[spec.name] = spec
    return by_name


#: Every registered tool, by name.
TOOLS_BY_NAME: dict[str, ToolSpec] = _index_by_name(_REGISTRY)

#: Every tool name with a registered :class:`ToolSpec`.
KNOWN_TOOL_NAMES: frozenset[str] = frozenset(TOOLS_BY_NAME)

#: Tool names toolguard ships built-in knowledge of -- see
#: :attr:`ToolSpec.is_builtin`. Unordered; for the ordered default governed
#: set, use :data:`DEFAULT_GOVERNED_TOOLS`.
BUILTIN_TOOLS: frozenset[str] = frozenset(
    tool.name for tool in _REGISTRY if tool.is_builtin
)

#: Built-in tool names in registry order -- the default
#: ``Configuration.governed_tools()`` resolves to when no level in the
#: hierarchy configures ``governed_tools`` explicitly.
DEFAULT_GOVERNED_TOOLS: tuple[str, ...] = tuple(
    tool.name for tool in _REGISTRY if tool.is_builtin
)

#: Tool names whose subject is a file path rather than a command line.
FILE_KIND_TOOLS: frozenset[str] = frozenset(
    tool.name for tool in _REGISTRY if tool.kind is ToolKind.FILE
)


def payload_key(tool_name: str) -> str:
    """
    Return the ``tool_input`` key holding *tool_name*'s subject.

    Raises:
        KeyError: *tool_name* has no registered :class:`ToolSpec`.
    """
    return TOOLS_BY_NAME[tool_name].payload_key
