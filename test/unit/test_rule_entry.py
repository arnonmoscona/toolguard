"""
Unit tests for :mod:`toolguard.rule_entry` (TOO-19 Phase 0a, increment 1).

Pure unit tests: every :class:`~toolguard.rule_entry.RuleEntry` here is
built directly from hand-constructed values, with zero file I/O and no call
into ``toolguard.config``'s discovery path (``load_configuration()``,
``_discover_levels()``, ``find_project_root()``, ``discover_config_files()``,
or any function that calls one of those transitively). Per
``test/unit/CLAUDE.md``'s first checklist item, that means no
``ConfigIsolationMixin`` is needed for this file.

Run with:
    uv run python -m unittest discover -s test -t .
"""

import unittest
from types import MappingProxyType

import toolguard.rule_entry as rule_entry_module
from toolguard.issues import Issue
from toolguard.rule_entry import (
    KNOWN_ENRICHMENT_KEYS,
    PATTERN_KEY,
    MergeConflict,
    MergeOutcome,
    RuleEntry,
    entries_for_tool,
    is_tool_wrapper,
    merge_entries,
    normalize_entries_preserving,
    normalize_entry,
    real_patterns,
)


class TestNormalizeEntryPlainString(unittest.TestCase):
    """normalize_entry() behaviour for plain-string entries."""

    def test_plain_string_normalizes_with_no_issues(self):
        """
        Given a plain permission string
        When normalize_entry parses it (native or not doesn't matter here)
        Then it returns a RuleEntry with that pattern, empty metadata, raw
             set to the original string, and no issues
        """
        entry, issues = normalize_entry("Bash(git *)", is_native=False)

        self.assertEqual(entry, RuleEntry(pattern="Bash(git *)"))
        self.assertEqual(entry.raw, "Bash(git *)")
        self.assertEqual(dict(entry.metadata), {})
        self.assertEqual(issues, ())

    def test_plain_string_not_wrapper_shaped_still_normalizes(self):
        """
        Given a plain string that is NOT Tool(...)-wrapped (e.g. a bare word)
        When normalize_entry parses it
        Then it still normalizes with no issues -- wrapper-shape validation
             applies only to structured (dict) entries, never to plain
             strings, to avoid flooding existing configs with new errors for
             already-accepted shapes
        """
        entry, issues = normalize_entry("not-wrapped-at-all", is_native=False)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.pattern, "not-wrapped-at-all")
        self.assertEqual(issues, ())

    def test_plain_string_under_native_layer_is_unaffected(self):
        """
        Given a plain permission string
        When normalize_entry parses it with is_native=True
        Then it normalizes exactly as it would with is_native=False --
             native-layer gating only applies to structured (dict) entries
        """
        entry_native, issues_native = normalize_entry("Bash(git *)", is_native=True)
        entry_non_native, issues_non_native = normalize_entry(
            "Bash(git *)", is_native=False
        )

        self.assertEqual(entry_native, entry_non_native)
        self.assertEqual(issues_native, issues_non_native)

    def test_empty_string_is_rejected(self):
        """
        Given an empty string
        When normalize_entry parses it
        Then it returns (None, issues) with a WARNING (not error) Issue

        An empty string is the one non-wrapper-shaped plain string that is
        reported at all: it is unambiguously a mistake. It stays a warning
        rather than an error because today such an entry is silently filtered
        out by the tool-prefix scan, so an error would be a louder diagnostic
        than the current behaviour for config that loads clean.
        """
        entry, issues = normalize_entry("", is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertIsInstance(issues[0], Issue)
        self.assertEqual(issues[0].level, "warning")


class TestNormalizeEntryStructured(unittest.TestCase):
    """normalize_entry() behaviour for structured (dict) entries."""

    def test_dict_with_valid_match_normalizes(self):
        """
        Given a dict with a valid, wrapper-shaped 'match' value and no other keys
        When normalize_entry parses it under a non-native layer
        Then it returns a RuleEntry with pattern=match value, empty metadata,
             raw set to the original dict, and no issues
        """
        raw = {PATTERN_KEY: "Bash(git *)"}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.pattern, "Bash(git *)")
        self.assertEqual(dict(entry.metadata), {})
        self.assertIs(entry.raw, raw)
        self.assertTrue(entry.is_structured)
        self.assertEqual(issues, ())

    def test_dict_with_valid_match_and_known_enrichment_key(self):
        """
        Given a dict with a valid 'match' plus a key that IS in
             KNOWN_ENRICHMENT_KEYS
        When normalize_entry parses it
        Then the entry's metadata carries that key and no issue is raised
             for it

        Note: KNOWN_ENRICHMENT_KEYS is currently empty (Phase 1 has not
        landed "additionalContext" yet), so this test synthesizes a known
        key via monkeypatching the module constant for the duration of the
        test, to exercise the "known key -> no warning" branch independently
        of when a real enrichment key is added.
        """
        original = rule_entry_module.KNOWN_ENRICHMENT_KEYS
        rule_entry_module.KNOWN_ENRICHMENT_KEYS = frozenset({"additionalContext"})
        try:
            raw = {PATTERN_KEY: "Bash(git *)", "additionalContext": "why"}
            entry, issues = normalize_entry(raw, is_native=False)
        finally:
            rule_entry_module.KNOWN_ENRICHMENT_KEYS = original

        self.assertIsNotNone(entry)
        self.assertEqual(dict(entry.metadata), {"additionalContext": "why"})
        self.assertEqual(issues, ())

    def test_dict_with_unknown_key_returns_entry_and_warning(self):
        """
        Given a dict with a valid 'match' plus a key NOT in
             KNOWN_ENRICHMENT_KEYS
        When normalize_entry parses it
        Then it returns BOTH a usable RuleEntry (the unknown key does not
             block normalization) AND a warning Issue about that key --
             not one or the other
        """
        raw = {PATTERN_KEY: "Bash(git *)", "totallyMadeUpKey": "value"}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNotNone(entry, "unknown key must not block normalization")
        self.assertEqual(dict(entry.metadata), {"totallyMadeUpKey": "value"})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "warning")
        self.assertIn("totallyMadeUpKey", issues[0].message)

    def test_dict_missing_match_key_is_rejected(self):
        """
        Given a dict with no 'match' key at all
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        raw = {"additionalContext": "why"}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")
        self.assertIn(PATTERN_KEY, issues[0].message)

    def test_dict_with_non_string_match_is_rejected(self):
        """
        Given a dict whose 'match' value is not a string
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        raw = {PATTERN_KEY: 42}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_dict_with_empty_match_is_rejected(self):
        """
        Given a dict whose 'match' value is an empty string
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        raw = {PATTERN_KEY: ""}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_dict_with_non_wrapper_shaped_match_is_rejected(self):
        """
        Given a dict whose 'match' value is a non-empty string that is NOT
             Tool(...)-wrapped
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue -- unlike plain
             strings, structured entries ARE held to wrapper-shape validation
             since this is brand-new syntax with no back-compat surface
        """
        raw = {PATTERN_KEY: "not-wrapped-at-all"}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_dict_with_embedded_newline_in_match_is_rejected(self):
        """
        Given a dict whose 'match' value LOOKS wrapper-shaped end-to-end but
             contains an embedded newline splicing in what looks like a second
             tool-wrapper expression (e.g. "Bash(a)\\nEvil(b)")
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue -- the wrapper
             regex must not use DOTALL, or such a pattern would wrongly
             fullmatch (greedy .* consuming through the newline to the LAST
             closing paren), smuggling a second tool-wrapper expression past
             what is supposed to be strict, single-line structured-entry
             validation
        """
        raw = {PATTERN_KEY: "Bash(a)\nEvil(b)"}

        entry, issues = normalize_entry(raw, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_dict_under_native_layer_is_rejected_with_warning(self):
        """
        Given a valid, otherwise-normalizable dict entry
        When normalize_entry parses it with is_native=True
        Then it returns (None, issues) with a WARNING Issue (not an error) --
             structured entries are a toolguard extension and are never
             interpreted from a native Claude settings.json layer
        """
        raw = {PATTERN_KEY: "Bash(git *)"}

        entry, issues = normalize_entry(raw, is_native=True)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "warning")


class TestNormalizeEntryOtherTypes(unittest.TestCase):
    """normalize_entry() behaviour for entirely unsupported element types."""

    def test_int_is_rejected(self):
        """
        Given an int as a permission entry
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        entry, issues = normalize_entry(42, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_none_is_rejected(self):
        """
        Given None as a permission entry
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        entry, issues = normalize_entry(None, is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_list_is_rejected(self):
        """
        Given a list as a permission entry
        When normalize_entry parses it
        Then it returns (None, issues) with an error Issue
        """
        entry, issues = normalize_entry(["Bash(git *)"], is_native=False)

        self.assertIsNone(entry)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].level, "error")

    def test_no_silent_drop_every_rejection_carries_an_issue(self):
        """
        Given a variety of unusable inputs (empty string, bad dict, int, None, list)
        When each is normalized
        Then every single one returns at least one Issue -- the whole point
             of centralizing this parser is that nothing is EVER silently
             dropped, unlike the scattered isinstance(perm, str) checks this
             replaces
        """
        unusable_inputs = ["", {}, {"nope": "x"}, {PATTERN_KEY: 1}, 42, None, []]

        for raw in unusable_inputs:
            with self.subTest(raw=raw):
                entry, issues = normalize_entry(raw, is_native=False)
                self.assertIsNone(entry)
                self.assertGreaterEqual(len(issues), 1)


class TestIsToolWrapper(unittest.TestCase):
    """is_tool_wrapper() direct tests, incl. the TOO-19 embedded-newline fix."""

    def test_simple_wrapper_matches(self):
        """
        Given a plain Tool(pattern)-shaped string
        When is_tool_wrapper is called
        Then it returns True
        """
        self.assertTrue(is_tool_wrapper("Bash(git *)"))

    def test_nested_parens_in_body_still_match(self):
        """
        Given a wrapped pattern whose body itself contains parentheses
        When is_tool_wrapper is called
        Then it still returns True (greedy matching handles nesting without
             needing DOTALL)
        """
        self.assertTrue(is_tool_wrapper("Bash(foo(bar))"))

    def test_non_wrapped_string_does_not_match(self):
        """
        Given a string with no Tool(...) wrapper shape
        When is_tool_wrapper is called
        Then it returns False
        """
        self.assertFalse(is_tool_wrapper("not-wrapped-at-all"))

    def test_non_string_does_not_match(self):
        """
        Given a non-string value
        When is_tool_wrapper is called
        Then it returns False rather than raising
        """
        self.assertFalse(is_tool_wrapper(None))
        self.assertFalse(is_tool_wrapper(42))

    def test_embedded_newline_does_not_match(self):
        """
        Given a string that end-to-end looks wrapper-shaped but has an
             embedded newline splicing in what looks like a second
             tool-wrapper expression
        When is_tool_wrapper is called
        Then it returns False -- the wrapper regex is deliberately not
             DOTALL, so `.` never matches the embedded `\\n` and the greedy
             `.*` cannot span across it to reach the final `)`
        """
        self.assertFalse(is_tool_wrapper("Bash(a)\nEvil(b)"))


class TestEntriesForTool(unittest.TestCase):
    """entries_for_tool() tool-scoping behaviour."""

    def test_keeps_only_entries_matching_tool_wrapper(self):
        """
        Given a mix of RuleEntry objects for different tools
        When entries_for_tool filters for "Bash"
        Then only the Bash-wrapped entries are kept, wrapper intact
        """
        bash_entry, _ = normalize_entry("Bash(git *)", is_native=False)
        read_entry, _ = normalize_entry("Read(/etc/*)", is_native=False)
        entries = (bash_entry, read_entry)

        result = entries_for_tool(entries, "Bash")

        self.assertEqual(result, (bash_entry,))
        self.assertEqual(result[0].pattern, "Bash(git *)")

    def test_matches_exactly_startswith_and_endswith_semantics(self):
        """
        Given entries including a decoy that starts with the tool prefix but
             is not tool-wrapped for it (no closing paren immediately at the
             pattern's own end is not representable for a wrapped pattern,
             so this instead checks a same-prefix different-tool case)
        When entries_for_tool filters for "Bash"
        Then only entries whose pattern both starts with "Bash(" and ends
             with ")" are kept -- mirroring permission_layers()'s inline
             filter exactly (perm.startswith(prefix) and perm.endswith(")"))
        """
        bash_entry, _ = normalize_entry("Bash(git *)", is_native=False)
        bash_star_entry, _ = normalize_entry("BashOther(git *)", is_native=False)
        entries = (bash_entry, bash_star_entry)

        result = entries_for_tool(entries, "Bash")

        self.assertEqual(result, (bash_entry,))

    def test_empty_entries_returns_empty_tuple(self):
        """
        Given an empty entries tuple
        When entries_for_tool filters it
        Then it returns an empty tuple
        """
        self.assertEqual(entries_for_tool((), "Bash"), ())

    def test_does_not_strip_the_wrapper(self):
        """
        Given a Bash-scoped entry
        When entries_for_tool returns it
        Then the pattern is returned wrapper-intact -- stripping is the
             exclusive responsibility of permission_layers()'s own call site
        """
        entry, _ = normalize_entry("Bash(git *)", is_native=False)

        result = entries_for_tool((entry,), "Bash")

        self.assertEqual(result[0].pattern, "Bash(git *)")


class TestNormalizeEntriesPreserving(unittest.TestCase):
    """
    normalize_entries_preserving() behaviour: the write-path "never drop an
    element" contract (TOO-19 Phase 0a, increment 8).
    """

    def test_non_list_input_returns_empty_tuple(self):
        """
        Given a raw_list value that is not a list (None, a dict, an int, a
             plain string)
        When normalize_entries_preserving parses it
        Then it returns an empty tuple for every one of them -- the existing
             non-list tolerance elsewhere in this codebase, applied here too
        """
        non_list_inputs = [None, {"allow": []}, 42, "Bash(git *)"]

        for raw_list in non_list_inputs:
            with self.subTest(raw_list=raw_list):
                self.assertEqual(
                    normalize_entries_preserving(raw_list, is_native=False), ()
                )

    def test_unnormalizable_elements_are_preserved_not_dropped(self):
        """
        Given a list mixing a valid plain string, a valid structured entry,
             and several unnormalizable shapes (a malformed dict, an int,
             None, and a nested list)
        When normalize_entries_preserving parses it
        Then the output has EXACTLY one RuleEntry per input element (same
             length as the input) -- nothing is silently dropped, unlike
             normalize_entry()'s direct match-path callers -- and each
             unnormalizable element's RuleEntry carries the original raw
             value unchanged (by identity for the malformed dict and the
             nested list) with a synthesized repr()-based pattern
        """
        malformed_dict = {"nope": "x"}
        nested_list = ["Bash(nested *)"]
        raw_list = [
            "Bash(git *)",
            {PATTERN_KEY: "Bash(ls *)"},
            malformed_dict,
            42,
            None,
            nested_list,
        ]

        result = normalize_entries_preserving(raw_list, is_native=False)

        self.assertEqual(len(result), len(raw_list))
        for entry in result:
            self.assertIsInstance(entry, RuleEntry)

        # The three genuinely unnormalizable elements: preserved verbatim
        # via `raw`, with a repr()-based synthesized pattern that can never
        # collide with a real Tool(...) pattern.
        malformed_entry, int_entry, none_entry, nested_entry = (
            result[2],
            result[3],
            result[4],
            result[5],
        )
        self.assertIs(malformed_entry.raw, malformed_dict)
        self.assertEqual(malformed_entry.pattern, repr(malformed_dict))
        self.assertEqual(int_entry.raw, 42)
        self.assertEqual(int_entry.pattern, repr(42))
        self.assertIsNone(none_entry.raw)
        self.assertTrue(none_entry.has_raw)
        self.assertEqual(none_entry.pattern, repr(None))
        self.assertIs(nested_entry.raw, nested_list)
        self.assertEqual(nested_entry.pattern, repr(nested_list))

        # TOO-19 review-round-2 fix: every unnormalizable element's entry is
        # explicitly flagged synthesized_pattern=True (not inferred later
        # from the pattern's repr()-like string shape), and every VALID
        # entry (the plain string and the well-formed structured entry) is
        # NOT flagged.
        valid_string_entry, valid_structured_entry = result[0], result[1]
        self.assertFalse(valid_string_entry.synthesized_pattern)
        self.assertFalse(valid_structured_entry.synthesized_pattern)
        for entry in (malformed_entry, int_entry, none_entry, nested_entry):
            self.assertTrue(entry.synthesized_pattern)

    def test_all_elements_round_trip_through_to_source_faithfully(self):
        """
        Given the same mixed list as above (valid string, valid structured
             entry, malformed dict, int, None, nested list)
        When every resulting RuleEntry's to_source() is called
        Then each one reproduces its ORIGINAL raw_list element exactly,
             element-for-element in order -- including the None element,
             which must come back as None, not the string "None" --
             proving the write path never silently deletes or corrupts part
             of a user's config file
        """
        raw_list = [
            "Bash(git *)",
            {PATTERN_KEY: "Bash(ls *)"},
            {"nope": "x"},
            42,
            None,
            ["Bash(nested *)"],
        ]

        result = normalize_entries_preserving(raw_list, is_native=False)

        for original, entry in zip(raw_list, result):
            with self.subTest(original=original):
                self.assertEqual(entry.to_source(), original)


class TestRuleEntryTypeContract(unittest.TestCase):
    """
    Contract tests protecting RuleEntry's specific design decisions:
    the Mapping-valued (not flat-primitive) metadata field, the custom
    identity()/__hash__, compare=False on raw, and to_source()'s round-trip
    guarantee.
    """

    def test_identity_distinguishes_metadata_but_pattern_does_not(self):
        """
        Given two RuleEntry objects with the same pattern but different metadata
        When comparing .pattern vs .identity()
        Then .pattern treats them as the same rule, but .identity() treats
             them as different entries
        """
        entry_a = RuleEntry(pattern="Bash(git *)", metadata=MappingProxyType({}))
        entry_b = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"additionalContext": "why"}),
        )

        self.assertEqual(entry_a.pattern, entry_b.pattern)
        self.assertNotEqual(entry_a.identity(), entry_b.identity())

    def test_set_of_entries_works_with_list_valued_metadata(self):
        """
        Given a RuleEntry whose metadata holds a list value (e.g.
             applies_to = ["Bash", "Read"])
        When it is placed into a set() alongside another entry
        Then set() construction succeeds -- proving the flat-primitive
             constraint on metadata values is genuinely gone, not just
             documented as gone
        """
        entry_a = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"applies_to": ["Bash", "Read"]}),
        )
        entry_b = RuleEntry(pattern="Read(/etc/*)", metadata=MappingProxyType({}))

        result = {entry_a, entry_b}

        self.assertEqual(len(result), 2)

    def test_dataclass_generated_hash_would_fail_on_list_metadata(self):
        """
        Given the same list-valued-metadata RuleEntry as above
        When hash() is computed via a hypothetical dataclass-default
             __hash__ (i.e. hashing the raw field tuple directly, which is
             what @dataclass(frozen=True) without a custom __hash__ would do)
        Then that hypothetical hash raises TypeError -- proving RuleEntry's
             custom __hash__ (hashing identity() instead) is load-bearing,
             not incidental
        """
        entry = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"applies_to": ["Bash", "Read"]}),
        )

        # Simulate what the dataclass-generated __hash__ would do: hash the
        # tuple of comparable fields directly (pattern, metadata) -- 'raw'
        # is excluded there too since compare=False also excludes it from
        # the generated __hash__.
        with self.assertRaises(TypeError):
            hash((entry.pattern, entry.metadata))

        # But RuleEntry's own __hash__ succeeds.
        hash(entry)

    def test_to_source_returns_raw_verbatim_for_parsed_entry(self):
        """
        Given a RuleEntry produced by normalize_entry() from a structured dict
        When to_source() is called
        Then it returns the EXACT SAME object (identity, `is`) as the
             original raw dict, not a re-rendered equivalent
        """
        raw = {PATTERN_KEY: "Bash(git *)", "totallyMadeUpKey": "x"}
        entry, _ = normalize_entry(raw, is_native=False)

        self.assertIs(entry.to_source(), raw)

    def test_to_source_synthesizes_for_constructed_entry_with_metadata(self):
        """
        Given a RuleEntry constructed directly with no raw recorded (the
             default sentinel, has_raw is False) and with metadata
        When to_source() is called
        Then it synthesizes a dict of {PATTERN_KEY: pattern, **metadata}
             that round-trips to an equal dict (not the same object, since
             there was no original to preserve)
        """
        entry = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"additionalContext": "why"}),
        )

        result = entry.to_source()

        self.assertEqual(
            result, {PATTERN_KEY: "Bash(git *)", "additionalContext": "why"}
        )

    def test_to_source_synthesizes_bare_string_for_constructed_entry_without_metadata(
        self,
    ):
        """
        Given a RuleEntry constructed directly with no raw recorded (the
             default sentinel, has_raw is False) and no metadata
        When to_source() is called
        Then it returns the bare pattern string, not a single-key dict
        """
        entry = RuleEntry(pattern="Bash(git *)")

        self.assertEqual(entry.to_source(), "Bash(git *)")

    def test_has_raw_false_for_entry_with_no_raw_recorded(self):
        """
        Given a RuleEntry constructed with no `raw` argument at all
        When has_raw is checked
        Then it is False -- this entry has nothing original to preserve, so
             to_source() must render it fresh rather than round-trip it
        """
        entry = RuleEntry(pattern="Bash(git *)")

        self.assertFalse(entry.has_raw)

    def test_has_raw_true_when_raw_is_explicitly_none(self):
        """
        Given a RuleEntry constructed with `raw=None` EXPLICITLY (e.g. as
             produced by normalize_entries_preserving() for a parsed JSON
             `null` element)
        When has_raw is checked
        Then it is True -- a genuine `raw=None` is a recorded source value,
             distinct from "no raw was ever recorded" (the _UNSET default)
        """
        entry = RuleEntry(pattern=repr(None), metadata=MappingProxyType({}), raw=None)

        self.assertTrue(entry.has_raw)

    def test_to_source_round_trips_a_genuine_raw_none_value_faithfully(self):
        """
        Given a RuleEntry whose raw was explicitly recorded as None (e.g. a
             JSON config's allow/deny/ask list containing a literal `null`
             element, preserved by normalize_entries_preserving())
        When to_source() is called
        Then it returns None (the ORIGINAL value), never the string "None"
             -- regression guard for the raw=None / "no raw recorded"
             sentinel conflation bug (TOO-19 Phase 0a): before the _UNSET
             sentinel existed, `if self.raw is not None: return self.raw`
             fell through for this entry and to_source() re-rendered the
             bare pattern string instead, silently corrupting the config on
             write.
        """
        entry = RuleEntry(pattern=repr(None), metadata=MappingProxyType({}), raw=None)

        result = entry.to_source()

        self.assertIsNone(result)
        self.assertNotEqual(result, "None")

    def test_metadata_is_genuinely_immutable(self):
        """
        Given a RuleEntry's metadata (built as a MappingProxyType)
        When an attempt is made to mutate it
        Then it raises TypeError -- "frozen" is not a lie
        """
        entry = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"additionalContext": "why"}),
        )

        with self.assertRaises(TypeError):
            entry.metadata["additionalContext"] = "different"

    def test_entries_differing_only_in_raw_compare_equal(self):
        """
        Given two RuleEntry objects with the same pattern and metadata but
             different 'raw' values (e.g. differing source formatting)
        When compared for equality
        Then they compare EQUAL -- raw carries compare=False, so formatting
             differences are not identity differences
        """
        entry_a = RuleEntry(pattern="Bash(git *)", raw="Bash(git *)")
        entry_b = RuleEntry(pattern="Bash(git *)", raw={"match": "Bash(git *)"})

        self.assertEqual(entry_a, entry_b)

    def test_is_structured_reflects_raw_type(self):
        """
        Given a RuleEntry parsed from a plain string vs one parsed from a dict
        When is_structured is checked
        Then it is False for the string-sourced entry and True for the
             dict-sourced entry
        """
        string_entry, _ = normalize_entry("Bash(git *)", is_native=False)
        dict_entry, _ = normalize_entry({PATTERN_KEY: "Bash(git *)"}, is_native=False)

        self.assertFalse(string_entry.is_structured)
        self.assertTrue(dict_entry.is_structured)


class TestMergeEntries(unittest.TestCase):
    """
    merge_entries() consolidation semantics (TOO-19 Phase 0a, increment 6).

    Every RuleEntry here is hand-constructed with zero file I/O, so (per
    test/unit/CLAUDE.md's checklist) no ConfigIsolationMixin is needed.
    """

    def test_bare_and_structured_same_pattern_collapses_to_structured(self):
        """
        Given a bare-string entry and a structured entry sharing one pattern
        When merge_entries is called
        Then the bare entry is dropped, the structured entry survives alone,
             and no conflict is reported (a clean win, not a warning)
        """
        bare = RuleEntry(pattern="Bash(git push:*)", raw="Bash(git push:*)")
        structured = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
            raw={"match": "Bash(git push:*)", "additionalContext": "careful"},
        )

        outcome = merge_entries([bare, structured])

        self.assertEqual(outcome.entries, (structured,))
        self.assertEqual(outcome.conflicts, ())

    def test_structured_entries_disjoint_keys_union_merge(self):
        """
        Given two structured entries sharing a pattern with DISJOINT metadata
             keys
        When merge_entries is called
        Then they merge into a single entry whose metadata is the union of
             both, and no conflict is reported
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"autoMode": True}),
        )

        outcome = merge_entries([entry_a, entry_b])

        self.assertEqual(len(outcome.entries), 1)
        merged = outcome.entries[0]
        self.assertEqual(merged.pattern, "Bash(git push:*)")
        self.assertEqual(
            dict(merged.metadata),
            {"additionalContext": "careful", "autoMode": True},
        )
        self.assertEqual(outcome.conflicts, ())

    def test_structured_entries_identical_shared_value_union_merges_cleanly(self):
        """
        Given two structured entries sharing a pattern AND sharing one key
             with the IDENTICAL value (plus one disjoint key each)
        When merge_entries is called
        Then they merge into a single entry with the union of keys, the
             shared key appearing once, and no conflict is reported
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful", "onlyA": 1}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful", "onlyB": 2}),
        )

        outcome = merge_entries([entry_a, entry_b])

        self.assertEqual(len(outcome.entries), 1)
        merged = outcome.entries[0]
        self.assertEqual(
            dict(merged.metadata),
            {"additionalContext": "careful", "onlyA": 1, "onlyB": 2},
        )
        self.assertEqual(outcome.conflicts, ())

    def test_structured_entries_conflicting_value_stay_separate_and_reported(self):
        """
        Given two structured entries sharing a pattern AND sharing one key
             with DIFFERENT values
        When merge_entries is called
        Then neither is merged nor dropped -- BOTH survive separately, in
             their original order, and a MergeConflict naming the pattern and
             the contended key is reported
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "urgent"}),
        )

        outcome = merge_entries([entry_a, entry_b])

        self.assertEqual(outcome.entries, (entry_a, entry_b))
        self.assertEqual(len(outcome.conflicts), 1)
        conflict = outcome.conflicts[0]
        self.assertEqual(conflict.pattern, "Bash(git push:*)")
        self.assertEqual(conflict.key, "additionalContext")
        self.assertEqual(conflict.entries, (entry_a, entry_b))

    def test_third_entry_sharing_an_already_conflicting_key_is_skipped(self):
        """
        Given three structured entries sharing one pattern, all carrying the
             SAME metadata key with three pairwise-different values (so the
             SECOND entry already flags the key as conflicting against the
             first)
        When merge_entries is called
        Then the THIRD entry's value for that key hits the
             "key already in conflicting_keys" fast-skip (never re-compared
             against the first entry's value) -- yet the single reported
             MergeConflict still lists ALL THREE entries as carrying the
             key, and every entry survives separately with no exception or
             duplicate conflict record
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "first"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "second"}),
        )
        entry_c = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "third"}),
        )

        outcome = merge_entries([entry_a, entry_b, entry_c])

        self.assertEqual(outcome.entries, (entry_a, entry_b, entry_c))
        self.assertEqual(len(outcome.conflicts), 1)
        conflict = outcome.conflicts[0]
        self.assertEqual(conflict.key, "additionalContext")
        self.assertEqual(conflict.entries, (entry_a, entry_b, entry_c))

    def test_three_way_group_mixing_all_cases_resolves_correctly(self):
        """
        Given one group with a bare entry PLUS two structured entries that
             share a pattern, one key with an identical value (merges
             cleanly) and another key with contradictory values (conflicts)
        When merge_entries is called
        Then the bare entry is dropped (case 1), the two structured entries
             stay separate because of the contradiction (case 3), and a
             conflict is reported for the contended key -- proving the cases
             compose rather than interact badly
        """
        bare = RuleEntry(pattern="Bash(git push:*)", raw="Bash(git push:*)")
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType(
                {"sharedOk": "same", "additionalContext": "careful"}
            ),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType(
                {"sharedOk": "same", "additionalContext": "urgent"}
            ),
        )

        outcome = merge_entries([bare, entry_a, entry_b])

        self.assertEqual(outcome.entries, (entry_a, entry_b))
        self.assertEqual(len(outcome.conflicts), 1)
        self.assertEqual(outcome.conflicts[0].key, "additionalContext")

    def test_identical_structured_entries_dedupe_via_identity_fast_path(self):
        """
        Given two structured entries that are LITERALLY identical (same
             pattern, same metadata)
        When merge_entries is called
        Then they collapse to a single entry with no conflict -- the
             identity()-based fast path inside merge_entries, distinct from
             the union-merge path
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )

        outcome = merge_entries([entry_a, entry_b])

        self.assertEqual(len(outcome.entries), 1)
        self.assertEqual(outcome.conflicts, ())

    def test_different_patterns_are_never_merged_together(self):
        """
        Given two structured entries with DIFFERENT patterns
        When merge_entries is called
        Then both survive as independent, unmerged entries
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git status:*)",
            metadata=MappingProxyType({"additionalContext": "fine"}),
        )

        outcome = merge_entries([entry_a, entry_b])

        self.assertEqual(outcome.entries, (entry_a, entry_b))
        self.assertEqual(outcome.conflicts, ())

    def test_group_and_entry_order_is_first_appearance_order(self):
        """
        Given entries for two distinct patterns interleaved in appearance
             order (pattern B first, then pattern A, then pattern B again)
        When merge_entries is called
        Then the output groups preserve FIRST-appearance order (B's group
             before A's group), not sorted or reversed order
        """
        b1 = RuleEntry(pattern="Bash(git status:*)", raw="Bash(git status:*)")
        a1 = RuleEntry(pattern="Bash(git push:*)", raw="Bash(git push:*)")
        b2 = RuleEntry(
            pattern="Bash(git status:*)",
            metadata=MappingProxyType({"additionalContext": "fine"}),
        )

        outcome = merge_entries([b1, a1, b2])

        # b1+b2 collapse to b2 (structured wins over bare), a1 stays alone.
        self.assertEqual(outcome.entries, (b2, a1))

    def test_empty_input_returns_empty_outcome(self):
        """
        Given an empty sequence of entries
        When merge_entries is called
        Then it returns a MergeOutcome with empty entries and empty conflicts
        """
        outcome = merge_entries([])

        self.assertEqual(outcome, MergeOutcome(entries=(), conflicts=()))

    def test_merge_conflict_is_a_frozen_dataclass_with_pattern_key_entries(self):
        """
        Given a MergeConflict record produced by a real conflict
        When its fields are inspected
        Then it exposes pattern (str), key (str), and entries (tuple of the
             conflicting RuleEntry objects) -- and is itself immutable
        """
        entry_a = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
        )
        entry_b = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "urgent"}),
        )
        outcome = merge_entries([entry_a, entry_b])
        conflict = outcome.conflicts[0]

        self.assertIsInstance(conflict, MergeConflict)
        with self.assertRaises(Exception):
            conflict.key = "somethingElse"


class TestModuleConstants(unittest.TestCase):
    """Sanity checks on the module-level constants themselves."""

    def test_pattern_key_is_match(self):
        """
        Given the PATTERN_KEY constant
        When inspected
        Then it is the string "match", per the design ({match = "Bash(...)"})
        """
        self.assertEqual(PATTERN_KEY, "match")

    def test_known_enrichment_keys_starts_empty(self):
        """
        Given the KNOWN_ENRICHMENT_KEYS constant at this point in TOO-19
        When inspected
        Then it is an empty frozenset -- Phase 1 has not yet added
             "additionalContext" as a known key, and "match" (PATTERN_KEY)
             is never itself an enrichment key
        """
        self.assertEqual(KNOWN_ENRICHMENT_KEYS, frozenset())
        self.assertIsInstance(KNOWN_ENRICHMENT_KEYS, frozenset)


class TestRealPatterns(unittest.TestCase):
    """
    real_patterns() (TOO-19 review-round-2 fix): the chokepoint every
    write-path caller must use to build a config-write content-loss guard's
    ``expected_patterns`` argument, excluding synthesized-pattern entries.
    """

    def test_plain_strings_pass_through_unchanged(self):
        """
        Given a list of bare pattern strings (the legacy contract)
        When real_patterns() is called
        Then every string is kept, in order
        """
        entries = ["Bash(ls)", "Bash(git status)"]
        self.assertEqual(real_patterns(entries), entries)

    def test_normal_rule_entry_contributes_its_pattern(self):
        """
        Given a list containing a normally-normalized RuleEntry (not
             synthesized)
        When real_patterns() is called
        Then its .pattern is included
        """
        entry = RuleEntry(pattern="Bash(ls)", raw="Bash(ls)")
        self.assertEqual(real_patterns([entry]), ["Bash(ls)"])

    def test_synthesized_pattern_entry_is_excluded(self):
        """
        Given a list mixing a normal entry with a synthesized-pattern entry
             (as produced by normalize_entries_preserving() for a malformed
             element, e.g. a structured entry missing "match")
        When real_patterns() is called
        Then only the normal entry's pattern is returned -- the synthesized
             repr()-based pattern is dropped, since it can never appear in
             the actual text a write path produces (confirmed repro: passing
             it through wrongly refused every subsequent config write)
        """
        malformed = {"additionalContext": "oops"}
        entries = normalize_entries_preserving(["Bash(ls)", malformed], is_native=False)
        self.assertEqual(real_patterns(entries), ["Bash(ls)"])

    def test_mixed_str_and_rule_entry_list_both_handled(self):
        """
        Given a list mixing a bare pattern string and a RuleEntry
        When real_patterns() is called
        Then both contribute their pattern, in order
        """
        entries = ["Bash(ls)", RuleEntry(pattern="Bash(git *)", raw="Bash(git *)")]
        self.assertEqual(real_patterns(entries), ["Bash(ls)", "Bash(git *)"])

    def test_empty_input_returns_empty_list(self):
        """
        Given an empty entries list
        When real_patterns() is called
        Then it returns an empty list
        """
        self.assertEqual(real_patterns([]), [])


if __name__ == "__main__":
    unittest.main()
