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
silently.

Not in scope here: the tool-registry/payload-key material in
:mod:`toolguard.tool_spec`, and the ``STRIPPED_WRAPPERS`` matching-semantics
list in :mod:`toolguard.parser.command_extractor` -- both are Claude Code
facts too, moved in a later pass.
"""

# --- PreToolUse / SessionStart input payload (stdin) ---
SESSION_ID_KEY = "session_id"
TRANSCRIPT_PATH_KEY = "transcript_path"
CWD_KEY = "cwd"
PERMISSION_MODE_KEY = "permission_mode"
HOOK_EVENT_NAME_KEY = "hook_event_name"
TOOL_NAME_KEY = "tool_name"
TOOL_INPUT_KEY = "tool_input"

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

# --- Event names (values of hook_event_name / hookEventName, and the keys
# Claude Code's own settings.json hooks-registration schema uses) ---
PRE_TOOL_USE_EVENT = "PreToolUse"
SESSION_START_EVENT = "SessionStart"
