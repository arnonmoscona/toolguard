"""
Static registry of the tools toolguard knows how to govern.

A user's ``additional_supported_tools`` config setting extends the
recognized-tool set without changing anything here.
"""

from dataclasses import dataclass
from enum import Enum


class ToolKind(Enum):
    """Whether a tool's subject is a shell command line or a file path."""

    COMMAND = "command"
    FILE = "file"


@dataclass(frozen=True)
class ToolSpec:
    """A statically registered governable tool."""

    name: str
    kind: ToolKind
    payload_key: str
    #: True for the first-party tools toolguard governs by default. Whether
    #: toolguard recognizes a tool at all is registry membership
    #: (:data:`KNOWN_TOOL_NAMES`), not this flag.
    is_builtin: bool


# The registry. Adding a tool is one entry here.
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

#: Built-in tool names, unordered; :data:`DEFAULT_GOVERNED_TOOLS` is the
#: same names in registry order.
BUILTIN_TOOLS: frozenset[str] = frozenset(
    tool.name for tool in _REGISTRY if tool.is_builtin
)

#: Built-in tool names, in registry order.
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
