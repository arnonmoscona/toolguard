"""
The facts one ``PreToolUse`` evaluation knows about itself, carried as one value.

``hook.py`` loads several things once per run -- the resolved configuration, the
environment config, the governed-tool list, the parsed hook event, the agent label and
Claude Code's own permission mode -- and then passes some of them down and drops others.
This class names that set instead, so a new invocation-wide fact touches the load point
and the use points and nothing in between.

**An explicit argument, not an ambient singleton.** A module-level instance would leak
state across ``tools/corpus_build.py``'s in-process replay of many decisions in one
process -- a real scenario today, not a hypothetical one.

**Facts only.** Nothing here decides anything. The moment a method on this class makes a
decision, callers start depending on behaviour rather than on data, and which caller
depends on which behaviour stops being answerable.

**Scope is the hook's own invocation** -- toolguard's other console-script entry points
have their own lifecycles and do not import this module.
"""

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Invocation:
    """One decision's context -- a live ``PreToolUse`` evaluation, or a
    standalone one built by :meth:`for_evaluation`.

    Attributes:
        tool_name: The tool being evaluated, e.g. ``'Bash'``.
        tool_input: That tool's input payload. Verbatim from the hook event
            for a live invocation; a synthetic ``{key: target}`` mapping for
            one built via :meth:`for_evaluation`.
        config: The resolved :class:`~toolguard.configuration.config.Configuration`. Typed loosely
            because ``config`` and ``resolve`` deliberately have no import edge between
            them -- they call each other through an injected callback -- and this class
            must not become the thing that creates the first one. ``None`` only where a
            caller (e.g. :func:`~toolguard.hook._run_startup_validation`) treats that as
            "load one on demand".
        extended_syntax: Whether ``[regex]``/``[glob]``/``[native]`` prefixes are
            honoured. Not always derivable from ``env_config`` -- :func:`~toolguard.api.decide`
            receives it directly from its own caller -- so it is its own field rather
            than read out of ``env_config`` by whichever function needs it.
        cwd: The working directory the event reported, or ``None`` when there is no
            real one (:meth:`for_evaluation`).
        env_config: Environment-derived settings. Empty outside a live hook
            evaluation (:meth:`for_evaluation`) -- nothing reads ``None`` as a
            distinct state, so there is no defaulted-vs-absent distinction to
            preserve.
        governed_tools: The tools this configuration governs, or ``None`` outside a
            live hook evaluation.
        agent_info: The agent label used in the log, e.g. ``'main'``, or ``None``
            outside a live hook evaluation.
        permission_mode: Claude Code's own permission mode for this call, e.g.
            ``'default'`` or an auto mode, or ``None`` outside a live hook evaluation.
        session_id: Claude Code's session identifier for this call, or ``None``
            outside a live hook evaluation.

    Frozen because it is a record of what was loaded, not a place to accumulate state
    during a decision. A mutable one would reintroduce, inside a single process, exactly
    the cross-contamination the explicit-argument choice above avoids between processes.
    A field arriving later within one hook run (see ``hook.py``'s own construction site)
    is threaded via :func:`dataclasses.replace`, never by mutating in place.
    """

    tool_name: str
    tool_input: Mapping[str, Any]
    config: Any
    extended_syntax: bool = True
    cwd: Optional[str] = None
    env_config: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    governed_tools: Optional[Tuple[str, ...]] = None
    agent_info: Optional[str] = None
    permission_mode: Optional[str] = None
    session_id: Optional[str] = None

    @classmethod
    def for_evaluation(
        cls,
        config: Any,
        tool_name: str = "Bash",
        tool_input: Optional[Mapping[str, Any]] = None,
        extended_syntax: bool = True,
    ) -> "Invocation":
        """
        Build an ``Invocation`` for a standalone decision, with no real hook event.

        Used by :func:`~toolguard.api.decide` (which has a real ``config`` and
        ``extended_syntax`` but no real ``cwd``/``env_config``/``governed_tools``/
        ``agent_info``/``permission_mode`` to supply) and by anything else --
        tests included -- that needs a minimal ``Invocation`` without driving a
        full hook run. A constructor, not a decision: it resolves nothing and
        caches nothing.
        """
        return cls(
            tool_name=tool_name,
            tool_input=tool_input if tool_input is not None else {},
            config=config,
            extended_syntax=extended_syntax,
        )
