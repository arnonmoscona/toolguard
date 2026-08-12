"""
Shared immutable constants for toolguard.

A single home for small vocabularies otherwise re-declared at multiple call
sites -- built-in/file tool-name sets, harvested-corpus status strings, and a
couple of low-level values used by :mod:`toolguard._git` and its callers. A
leaf module that imports only other foundation modules, so any layer can use
these without coupling to something heavier.

The ``STATUS_*`` values are the common ones for a harvested corpus entry
(``LogEntry.status``); a status outside this set is preserved as-is.
"""

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
#: Permitted but the tool itself errored.
STATUS_ERROR = "ERROR"
#: No matching tool_result was found.
STATUS_UNKNOWN = "UNKNOWN"

#: Timeout, in seconds, for git subprocesses run through
#: :func:`toolguard._git.run_git` -- guards against a hang or an
#: interactive credential prompt.
GIT_TIMEOUT_SECONDS = 10

#: The distribution/import/project name toolguard is published and installed
#: under.
DIST_NAME = "toolguard"
