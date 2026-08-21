"""Unit tests for toolguard.claude_code_contract: the PreToolUse wire shapes."""

import unittest

from toolguard.claude_code_contract import (
    ADDITIONAL_CONTEXT_KEY,
    CWD_KEY,
    HOOK_EVENT_NAME_KEY,
    HOOK_SPECIFIC_OUTPUT_KEY,
    PERMISSION_MODE_KEY,
    SESSION_ID_KEY,
    TOOL_INPUT_KEY,
    TOOL_NAME_KEY,
    TRANSCRIPT_PATH_KEY,
    PreToolUseEvent,
    PreToolUseResponse,
)


class TestPreToolUseEventRoundTrip(unittest.TestCase):
    """The invariant this ticket buys: construct, serialise, parse, get the same event back."""

    def test_to_json_dict_then_from_json_dict_round_trips(self):
        """
        Given a fully-populated PreToolUseEvent
        When it is serialised with to_json_dict() and parsed back with from_json_dict()
        Then the reconstructed event equals the original
        """
        event = PreToolUseEvent(
            session_id="abc123",
            transcript_path="/path/to/transcript.jsonl",
            cwd="/current/working/dir",
            permission_mode="default",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "git status"},
        )

        round_tripped = PreToolUseEvent.from_json_dict(event.to_json_dict())

        self.assertEqual(event, round_tripped)

    def test_permission_mode_none_round_trips(self):
        """
        Given an event with permission_mode=None (a field not every event carries)
        When it round-trips through to_json_dict()/from_json_dict()
        Then permission_mode stays None, not coerced to a string
        """
        event = PreToolUseEvent(
            session_id="s",
            transcript_path="",
            cwd="/tmp",
            permission_mode=None,
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={},
        )

        round_tripped = PreToolUseEvent.from_json_dict(event.to_json_dict())

        self.assertEqual(event, round_tripped)
        self.assertIsNone(round_tripped.permission_mode)


class TestPreToolUseEventToJsonDict(unittest.TestCase):
    """to_json_dict()'s wire shape: flat, top-level, Claude Code's own key names."""

    def test_emits_the_documented_flat_keys(self):
        """
        Given a PreToolUseEvent
        When to_json_dict() renders it
        Then the result carries exactly Claude Code's documented top-level field names
        """
        event = PreToolUseEvent(
            session_id="s",
            transcript_path="t",
            cwd="/tmp",
            permission_mode="plan",
            hook_event_name="PreToolUse",
            tool_name="Bash",
            tool_input={"command": "ls"},
        )

        data = event.to_json_dict()

        self.assertEqual(
            data,
            {
                SESSION_ID_KEY: "s",
                TRANSCRIPT_PATH_KEY: "t",
                CWD_KEY: "/tmp",
                PERMISSION_MODE_KEY: "plan",
                HOOK_EVENT_NAME_KEY: "PreToolUse",
                TOOL_NAME_KEY: "Bash",
                TOOL_INPUT_KEY: {"command": "ls"},
            },
        )


class TestPreToolUseEventFromJsonDict(unittest.TestCase):
    """from_json_dict()'s lenient-parse behaviour: defaults, never raises on a missing key."""

    def test_missing_fields_default_rather_than_raise(self):
        """
        Given a raw dict missing every field
        When from_json_dict() parses it
        Then it returns an event with empty/None defaults instead of raising
        """
        event = PreToolUseEvent.from_json_dict({})

        self.assertEqual(event.session_id, "")
        self.assertEqual(event.transcript_path, "")
        self.assertEqual(event.cwd, "")
        self.assertIsNone(event.permission_mode)
        self.assertEqual(event.hook_event_name, "")
        self.assertEqual(event.tool_name, "")
        self.assertEqual(event.tool_input, {})


class TestPreToolUseResponseToJsonDict(unittest.TestCase):
    """to_json_dict()'s hookSpecificOutput nesting and the additionalContext omission rule."""

    def test_nests_decision_and_reason_under_hook_specific_output(self):
        """
        Given a response with a decision and a reason
        When to_json_dict() renders it
        Then both land nested inside hookSpecificOutput
        """
        response = PreToolUseResponse(
            decision="allow", reason="Command matches allow pattern"
        )

        data = response.to_json_dict()

        self.assertEqual(data[HOOK_SPECIFIC_OUTPUT_KEY]["permissionDecision"], "allow")
        self.assertEqual(
            data[HOOK_SPECIFIC_OUTPUT_KEY]["permissionDecisionReason"],
            "Command matches allow pattern",
        )

    def test_no_additional_context_omits_the_key_entirely(self):
        """
        Given a response built with no additional_context argument (defaults to None)
        When to_json_dict() renders it
        Then hookSpecificOutput has no additionalContext key at all
        """
        response = PreToolUseResponse(decision="allow", reason="ok")

        data = response.to_json_dict()

        self.assertNotIn(ADDITIONAL_CONTEXT_KEY, data[HOOK_SPECIFIC_OUTPUT_KEY])

    def test_empty_string_additional_context_omits_the_key_entirely(self):
        """
        Given a response with additional_context="" (empty string)
        When to_json_dict() renders it
        Then hookSpecificOutput has no additionalContext key -- omitted, not set to null
        """
        response = PreToolUseResponse(
            decision="allow", reason="ok", additional_context=""
        )

        data = response.to_json_dict()

        self.assertNotIn(ADDITIONAL_CONTEXT_KEY, data[HOOK_SPECIFIC_OUTPUT_KEY])

    def test_non_empty_additional_context_is_included(self):
        """
        Given a response with a non-empty additional_context
        When to_json_dict() renders it
        Then hookSpecificOutput carries additionalContext with that exact text
        """
        response = PreToolUseResponse(
            decision="allow",
            reason="ok",
            additional_context="prefer git status --short",
        )

        data = response.to_json_dict()

        self.assertEqual(
            data[HOOK_SPECIFIC_OUTPUT_KEY][ADDITIONAL_CONTEXT_KEY],
            "prefer git status --short",
        )


if __name__ == "__main__":
    unittest.main()
