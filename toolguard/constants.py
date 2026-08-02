"""
Shared immutable constants for toolguard.

A single home for small vocabularies that were previously re-declared at multiple
call sites (the governed/file tool-name sets and the harvested-corpus status
strings).  Keeping them here -- in a leaf module that imports nothing from
toolguard -- lets both the core (``hook``) and the tooling layer
(``log_harvest``, ``transcript_harvest``, ``mining``, ``replay``) share one
definition without coupling to a heavyweight module.

TOO-19 code review M3: also the home for two constants ``update_check.py`` and
``install_provenance.py`` each declared verbatim (``_GIT_TIMEOUT_SECONDS`` and a
``toolguard`` distribution-name default) -- both modules are, like this one,
low-level stdlib-only leaves, so this is a layering-consistent home for their
shared values even though the values themselves are not vocabularies. The
duplicated git-subprocess boilerplate those two modules also shared is factored
into :func:`toolguard._git.run_git` instead, kept separate from this module
because it is procedural, not a constant.
"""

# Tools toolguard governs (intercepts permission decisions for).
GOVERNED_TOOLS = frozenset({"Bash", "Read", "Write", "Edit"})

# Governed tools whose target is a file PATH rather than a shell command line.
# (Bash is the complement: its "command" is a shell command line.)
FILE_TOOLS = frozenset({"Read", "Write", "Edit"})

# Observed-status vocabulary for a harvested corpus entry (``LogEntry.status``).
STATUS_EXECUTED = "EXECUTED"  # the tool ran without error
STATUS_REFUSED = "REFUSED"  # the user declined the permission prompt
STATUS_ERROR = "ERROR"  # permitted but the tool itself errored
STATUS_UNKNOWN = "UNKNOWN"  # no matching tool_result was found

# Network/process guard (TOO-19 code review M3) for every git subprocess call in
# update_check.py and install_provenance.py (via toolguard._git.run_git): never
# hang, never prompt for credentials.
GIT_TIMEOUT_SECONDS = 10

# Distribution/import/project name toolguard is published and installed under
# (TOO-19 code review M3) -- shared by update_check.py's importlib.metadata
# lookups and install_provenance.py's pyproject.toml [project].name check.
DIST_NAME = "toolguard"
