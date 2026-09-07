"""
Shared immutable constants for toolguard.

A single home for small vocabularies otherwise re-declared at multiple call
sites -- built-in/file tool-name sets, harvested-corpus status strings, and a
couple of low-level values used by :mod:`toolguard._git` and its callers. A
leaf module that imports only other foundation modules, so any layer can use
these without coupling to something heavier.

The ``STATUS_*`` values are the common ones for a harvested corpus entry
(``LogEntry.status``); a status outside this set is preserved as-is. ``DECISION_*``,
``FALLBACK_*``, and ``FALLBACK_OUTCOME_*`` are a separate vocabulary -- permission
decisions, not corpus statuses -- deliberately not folded into ``STATUS_*`` even though
one spelling (``'ask'``) is shared by coincidence, not by meaning.
"""

from toolguard.claude_code_contract import COMMAND_PAYLOAD_KEY as _COMMAND_PAYLOAD_KEY
from toolguard.tool_spec import BUILTIN_TOOLS as _BUILTIN_TOOLS
from toolguard.tool_spec import FILE_KIND_TOOLS as _FILE_KIND_TOOLS

#: The first-party tools toolguard governs by default, by name. Whether
#: toolguard recognizes a tool at all is registry membership, not this set.
BUILTIN_TOOLS = _BUILTIN_TOOLS

#: Tools whose target is a file PATH rather than a shell command line.
FILE_TOOLS = _FILE_KIND_TOOLS

#: The tool ran without error.
STATUS_EXECUTED = "EXECUTED"
#: The call did not run: toolguard denied it, or transcript harvesting
#: inferred the user declined it.
STATUS_REFUSED = "REFUSED"
#: Toolguard's own hook prompted for the command (an 'ask' verdict), status
#: written by :mod:`toolguard.log_writer`.
STATUS_ASK = "ASK"
#: Permitted but the tool itself errored.
STATUS_ERROR = "ERROR"
#: No matching tool_result was found.
STATUS_UNKNOWN = "UNKNOWN"

#: A permission decision -- ``RuntimeVerdict.decision``/``UnitVerdict.decision`` and
#: everything that dispatches on one. Also the value a ``no_match_fallback``/
#: ``undecidable_fallback`` setting resolves to when it names one of these three
#: directly, rather than ``FALLBACK_ALLOW_WITH_WARNING``/its alias below.
DECISION_ALLOW = "allow"
DECISION_DENY = "deny"
DECISION_ASK = "ask"

#: The two ``no_match_fallback``/``undecidable_fallback`` values with no decision-value
#: equivalent -- allow, but only after logging a warning (or, for the alias, allow with
#: none at all). See :data:`DECISION_ALLOW` for the plain ``'allow'`` spelling.
FALLBACK_ALLOW_WITH_WARNING = "allow_with_warning"
FALLBACK_ALLOW_WITH_NO_WARNINGS = "allow_with_no_warnings"

#: ``UnitVerdict.fallback_outcome``/``RuntimeVerdict.fallback_outcome`` -- which escape
#: hatch, if any, decided an allow (or a denied undecidable segment): warned, silent, or
#: (the undecidable floor only) denied without ever evaluating a rule.
FALLBACK_OUTCOME_WARNED = "warned"
FALLBACK_OUTCOME_SILENT = "silent"
FALLBACK_OUTCOME_DENIED = "denied"

#: A rule's ``program_source`` guard (TOO-28 spec 4.3): whether a command's executable
#: material is visible on the command line, or hidden in a file toolguard cannot read.
#: Binary by design -- not an enumeration of heredoc/pipe/stdin/redirect/inline, all of
#: which are ``PROGRAM_SOURCE_NOT_FILE``.
PROGRAM_SOURCE_FILE = "file"
PROGRAM_SOURCE_NOT_FILE = "not_file"

#: Timeout, in seconds, for git subprocesses run through
#: :func:`toolguard._git.run_git` -- guards against a hang or an
#: interactive credential prompt.
GIT_TIMEOUT_SECONDS = 10

#: The distribution/import/project name toolguard is published and installed
#: under.
DIST_NAME = "toolguard"

#: Fallback ``tool_input`` key for a command tool with no registered
#: :class:`~toolguard.tool_spec.ToolSpec` (e.g. an unrecognized MCP tool
#: added via ``additional_supported_tools``) -- every registered command
#: tool's own ``payload_key`` is the same value too, so this only matters for
#: names outside the registry.
DEFAULT_COMMAND_PAYLOAD_KEY = _COMMAND_PAYLOAD_KEY
