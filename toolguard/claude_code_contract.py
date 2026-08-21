"""
Claude Code's PreToolUse/SessionStart hook wire protocol.

Every name in this module is Claude Code's own vocabulary, not toolguard's --
it mirrors an EXTERNAL, EVOLVING specification this project does not own or
control. A rename or addition on Claude Code's side changes this module's
*correctness*, not something toolguard gets to redesign. Treat each constant
as verified as of the date below, never as a permanent guarantee.

Doc: https://code.claude.com/docs/en/hooks.md
Sections: "Common input fields", "PreToolUse", "JSON output".
VERIFIED 2026-08-21.

Every bare occurrence of one of these field/event names elsewhere in the
package should import it from here instead of re-spelling the string. That
import is what makes "does this code touch Claude Code's external contract?"
a checkable fact rather than a grep for a dozen strings that goes stale
silently. :class:`PreToolUseEvent` and :class:`PreToolUseResponse` carry this
further for the two shapes that get parsed AND constructed elsewhere in the
package: a caller uses the class, not the individual keys.

Not in scope here: :mod:`toolguard.tool_spec`'s registry -- which tools
exist, whether each is governed by default, and which kind of matching
applies to it are toolguard's own decisions, built out of the field names
declared here.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

# --- PreToolUse / SessionStart input payload (stdin) ---
SESSION_ID_KEY = "session_id"
TRANSCRIPT_PATH_KEY = "transcript_path"
CWD_KEY = "cwd"
PERMISSION_MODE_KEY = "permission_mode"
HOOK_EVENT_NAME_KEY = "hook_event_name"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"


@dataclass(frozen=True)
class PreToolUseEvent:
    """
    A PreToolUse hook event as Claude Code sends it on stdin.

    Fetched 2026-08-21 from https://code.claude.com/docs/en/hooks.md's "Common
    Input Fields": every field here is listed there except ``permission_mode``,
    which that table says explicitly is not sent for every event ("Not all
    events receive this field").

    The one class both directions of this protocol use: :func:`from_json_dict`
    for a caller parsing what Claude Code sent, :func:`to_json_dict` for a
    caller constructing a synthetic event (e.g. a test sandbox driving the hook
    as a subprocess). One shape for both keeps them from drifting apart.
    """

    session_id: str
    transcript_path: str
    cwd: str
    permission_mode: Optional[str]
    hook_event_name: str
    tool_name: str
    tool_input: Dict[str, Any]

    @classmethod
    def from_json_dict(cls, data: Dict[str, Any]) -> "PreToolUseEvent":
        """Parse a raw stdin payload. Missing fields default rather than raise."""
        return cls(
            session_id=data.get(SESSION_ID_KEY, ""),
            transcript_path=data.get(TRANSCRIPT_PATH_KEY, ""),
            cwd=data.get(CWD_KEY, ""),
            permission_mode=data.get(PERMISSION_MODE_KEY),
            hook_event_name=data.get(HOOK_EVENT_NAME_KEY, ""),
            tool_name=data.get(TOOL_NAME_KEY, ""),
            tool_input=data.get(TOOL_INPUT_KEY, {}),
        )

    def to_json_dict(self) -> Dict[str, Any]:
        """Render as the wire's flat, top-level field shape."""
        return {
            SESSION_ID_KEY: self.session_id,
            TRANSCRIPT_PATH_KEY: self.transcript_path,
            CWD_KEY: self.cwd,
            PERMISSION_MODE_KEY: self.permission_mode,
            HOOK_EVENT_NAME_KEY: self.hook_event_name,
            TOOL_NAME_KEY: self.tool_name,
            TOOL_INPUT_KEY: self.tool_input,
        }


# --- Event names (values of hook_event_name / hookEventName, and the keys
# Claude Code's own settings.json hooks-registration schema uses) ---
PRE_TOOL_USE_EVENT = "PreToolUse"
SESSION_START_EVENT = "SessionStart"

# --- PreToolUse output (stdout) ---
HOOK_SPECIFIC_OUTPUT_KEY = "hookSpecificOutput"
#: The event-name field nested inside ``hookSpecificOutput`` -- distinct from
#: the input payload's :data:`HOOK_EVENT_NAME_KEY`, which is a sibling
#: top-level field spelled in snake_case.
HOOK_EVENT_NAME_RESPONSE_KEY = "hookEventName"
PERMISSION_DECISION_KEY = "permissionDecision"
PERMISSION_DECISION_REASON_KEY = "permissionDecisionReason"
#: Nested inside ``hookSpecificOutput`` for PreToolUse specifically -- the
#: shape this module's callers actually use. Claude Code's docs also
#: describe a top-level ``additionalContext`` sibling of ``hookSpecificOutput``
#: for other hook types; toolguard has no PreToolUse call site for that
#: shape, so it is not named here.
ADDITIONAL_CONTEXT_KEY = "additionalContext"


@dataclass(frozen=True)
class PreToolUseResponse:
    """
    The PreToolUse hook's JSON response: a permission decision for Claude Code.

    Owns the ``hookSpecificOutput`` nesting and the omission rule: ``to_json_dict``
    leaves ``additionalContext`` out entirely (not set to ``null``) when
    *additional_context* is empty, so a caller with nothing to add produces the
    same shape as a hook that never set the field at all.

    What this response carries is a caller decision (which of a resolved
    verdict's fields to surface here) -- the projection itself is policy, not
    part of this class.
    """

    decision: str
    reason: str
    additional_context: Optional[str] = None

    def to_json_dict(self) -> Dict[str, Any]:
        """Render as the ``hookSpecificOutput``-nested wire shape."""
        output: Dict[str, Any] = {
            HOOK_SPECIFIC_OUTPUT_KEY: {
                HOOK_EVENT_NAME_RESPONSE_KEY: PRE_TOOL_USE_EVENT,
                PERMISSION_DECISION_KEY: self.decision,
                PERMISSION_DECISION_REASON_KEY: self.reason,
            }
        }
        if self.additional_context:
            output[HOOK_SPECIFIC_OUTPUT_KEY][ADDITIONAL_CONTEXT_KEY] = (
                self.additional_context
            )
        return output


# --- Per-tool payload field names: the key inside tool_input holding a
# given tool's subject. Fetched 2026-08-21 from
# https://code.claude.com/docs/en/tools-reference.md: "Your PreToolUse hooks
# receive the tool's command string in `tool_input.command`, with the same
# fields as the Bash tool." Confirmed for file tools by
# https://code.claude.com/docs/en/hooks.md's MCP-hook example for a
# `Write|Edit` matcher: `"input": { "file_path": "${tool_input.file_path}" }`.
COMMAND_PAYLOAD_KEY = "command"
FILE_PATH_PAYLOAD_KEY = "file_path"

# --- Bash rule matching: wrappers stripped before matching ---
#: The wrappers Claude Code strips before matching a Bash rule, so a rule written for the
#: inner command also matches the wrapped form. Verbatim, fetched 2026-08-21 from
#: https://code.claude.com/docs/en/permissions.md: "The stripped wrappers are `timeout`,
#: `time`, `nice`, `nohup`, and `stdbuf`, plus the shell builtins `command` and `builtin`,
#: and zsh's `noglob`... Bare `xargs` is also stripped ... Stripping applies only when
#: `xargs` has no flags." `command -v` (a lookup, not an execution) is deliberately not
#: included; see :func:`toolguard.parser.command_extractor._strip_wrapper`. `sudo` and `env`
#: are not on native's list at all and are deliberately not covered here either.
STRIPPED_WRAPPERS: Tuple[str, ...] = (
    "timeout",
    "time",
    "nice",
    "nohup",
    "stdbuf",
    "command",
    "builtin",
    "noglob",
    "xargs",
)
