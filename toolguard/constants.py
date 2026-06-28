"""
Shared immutable constants for toolguard.

A single home for small vocabularies that were previously re-declared at multiple
call sites (the governed/file tool-name sets and the harvested-corpus status
strings).  Keeping them here -- in a leaf module that imports nothing from
toolguard -- lets both the core (``hook``) and the tooling layer
(``log_harvest``, ``transcript_harvest``, ``mining``, ``replay``) share one
definition without coupling to a heavyweight module.
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
