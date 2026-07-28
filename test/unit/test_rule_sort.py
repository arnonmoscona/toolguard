"""
Unit tests for toolguard.rule_sort's comment-preserving TOML section machinery.

Three groups of tests live here:

* **Characterization tests** (TOO-19 Phase 0b increment 1, extended by
  increments 3 and 4, corrected by a later TOO-19 corrective change) for
  ``parse_permissions_section_with_comments`` and
  ``reassemble_permissions_section``, and dedicated tests for
  ``find_section_boundaries``. Most of these lock down parser behaviour that
  predates and survives the increment-3 rewrite; a few characterize the
  REWRITTEN parser directly (the escaped-quote test, renamed from
  ``..._NOTE_bug`` once increment 3's tomllib-based rewrite fixed the
  truncation bug it used to document) and the increment-4 reassembly
  round-trip guarantees. A structured entry is single-line ONLY (TOML 1.0's
  own requirement -- see ``rule_sort.py``'s top-of-file docstring): the tests
  that used to characterize multi-line SUPPORT were replaced by one asserting
  ``tomllib.TOMLDecodeError`` is raised instead, and the round-trip/reorder/
  neighbour-removal tests were converted to single-line structured entries
  (the underlying behaviour they exercise -- verbatim reuse, sort ordering,
  comment recovery -- still matters; only the multi-line SHAPE was invalid).
  Do not "fix" a still-characterized behaviour here casually; if it looks
  wrong, that is either already-reported or worth reporting separately, not
  silently changed. This module previously had no direct tests, only
  indirect coverage via ``test_tools_annotate.py`` and
  ``test_tools_config_access.py`` (both still pass, also converted to
  single-line structured entries).

* **Direct tests** (TOO-19 Phase 0b increment 2) for the
  ``split_array_elements`` top-level array-element boundary scanner, wired
  into production by the increment-3 rewrite of
  ``parse_permissions_section_with_comments`` (see that function's own
  docstring in ``rule_sort.py``). This scanner keeps its multi-line-SPAN
  awareness even though a multi-line structured entry is no longer valid
  content: it is what lets ``find_multiline_structured_entry_line`` point a
  user at the exact offending line once ``tomllib`` has already rejected the
  file (detection, not support -- see that function's own tests below).

* **Direct tests** for ``find_multiline_structured_entry_line``, the
  diagnostic-building scanner used by ``toolguard.config``'s
  ``_parse_source`` to upgrade a raw ``TOMLDecodeError`` into an actionable
  message.

All tests here are pure text-in/text-out: no file I/O, no config discovery, so
per ``test/unit/CLAUDE.md``'s isolation checklist, ``ConfigIsolationMixin`` is
not needed (none of the functions under test reach ``toolguard.config``'s
discovery path).
"""

import tomllib
import unittest
from types import MappingProxyType

from toolguard.rule_entry import RuleEntry
from toolguard.rule_sort import (
    ArrayElement,
    find_multiline_structured_entry_line,
    find_section_boundaries,
    is_synthetic_pattern,
    parse_permissions_section_with_comments,
    reassemble_permissions_section,
    render_toml_entry,
    split_array_elements,
)


# =============================================================================
# Part 1 (increment 1): characterization tests for the existing parser
# =============================================================================


class TestFindSectionBoundaries(unittest.TestCase):
    """Characterization tests for find_section_boundaries()."""

    def test_finds_permissions_section_in_realistic_multi_section_file(self):
        """
        Given a TOML file with a [general] section, a [permissions] section
            containing an allow list, and a trailing [other] section
        When find_section_boundaries() is called for "permissions"
        Then the returned span starts at the "[permissions]" header and ends
            right before the "[other]" header, including the blank line
            separating the two sections
        """
        text = (
            "[general]\n"
            "foo = 1\n"
            "\n"
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls:*)",\n'
            "]\n"
            "\n"
            "[other]\n"
            "bar = 2\n"
        )
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(
            text[start:end],
            '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n\n',
        )

    def test_returns_minus_one_pair_when_section_absent(self):
        """
        Given a TOML file with no [permissions] section
        When find_section_boundaries() is called for "permissions"
        Then it returns (-1, -1)
        """
        text = "[general]\nfoo = 1\n"
        self.assertEqual(find_section_boundaries(text, "permissions"), (-1, -1))

    def test_section_at_end_of_file_extends_to_string_end(self):
        """
        Given a TOML file where [permissions] is the LAST section (no section follows)
        When find_section_boundaries() is called
        Then the span extends all the way to the end of the text
        """
        text = "[general]\nfoo = 1\n\n[permissions]\nallow = [\n]\n"
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(end, len(text))
        self.assertEqual(text[start:end], "[permissions]\nallow = [\n]\n")

    def test_ignores_section_name_appearing_inside_quoted_string_in_earlier_section(
        self,
    ):
        """
        Given an EARLIER [hard_deny] section whose structured entry's
            additionalContext string literally CONTAINS the substring
            "[permissions]" (e.g. "see [permissions] docs"), followed by a
            real [permissions] section
        When find_section_boundaries() is called for "permissions"
        Then it locates the REAL [permissions] header line, not the substring
            occurrence inside the quoted string -- TOO-19 critical fix: the
            old str.find()-based scan matched the substring first and then
            spliced a rewritten section into the middle of that string,
            producing unparseable TOML (see toolguard/rule_sort.py's
            find_section_boundaries docstring)
        """
        text = (
            "[hard_deny]\n"
            "deny = [\n"
            '  { match = "Bash(rm -rf /)", additionalContext = "see [permissions] docs" },\n'
            "]\n"
            "\n"
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls *)",\n'
            "]\n"
        )
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(text[start : start + len("[permissions]")], "[permissions]")
        self.assertEqual(
            text[start:end],
            '[permissions]\nallow = [\n  "Bash(ls *)",\n]\n',
        )

    def test_ignores_section_name_appearing_inside_a_comment(self):
        """
        Given a full-line "#" comment that mentions "[permissions]" as plain
            text, appearing BEFORE the real [permissions] section
        When find_section_boundaries() is called for "permissions"
        Then it locates the real header line, not the comment text
        """
        text = (
            "# see the [permissions] section below for details\n"
            "[general]\n"
            "foo = 1\n"
            "\n"
            "[permissions]\n"
            "allow = [\n"
            "]\n"
        )
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(text[start : start + len("[permissions]")], "[permissions]")
        self.assertEqual(text[start:end], "[permissions]\nallow = [\n]\n")

    def test_section_header_with_leading_whitespace_is_recognized(self):
        """
        Given a [permissions] header line with leading horizontal whitespace
            (indentation) before the bracket
        When find_section_boundaries() is called for "permissions"
        Then the indented header line is still recognized as the section start
        """
        text = '[general]\nfoo = 1\n\n  [permissions]\nallow = [\n  "Bash(ls:*)",\n]\n'
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(
            text[start:end], '  [permissions]\nallow = [\n  "Bash(ls:*)",\n]\n'
        )

    def test_end_boundary_not_confused_by_bracket_inside_multiline_array_value(self):
        """
        Given a [permissions] section containing a metadata value that is
            itself a nested array-of-arrays (a continuation line beginning
            with "[" that is NOT a genuine section header), followed by a
            real trailing [other] section
        When find_section_boundaries() is called for "permissions"
        Then the end boundary is the real [other] header line, not the
            bracketed continuation line inside the array value -- TOO-19 fix:
            the old scan treated ANY newline-then-"[" as a section boundary
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  { match = "Bash(x)", matrix = [\n'
            "    [1, 2],\n"
            "  ] },\n"
            "]\n"
            "\n"
            "[other]\n"
            "bar = 2\n"
        )
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(text[end:], "[other]\nbar = 2\n")

    def test_header_with_trailing_comment_is_recognized(self):
        """
        Given a [permissions] header line followed by a trailing "#" comment
            on the SAME line (e.g. "[permissions] # my perms")
        When find_section_boundaries() is called for "permissions"
        Then the header is still recognized and the section span is found --
            TOO-19 review-round-2 regression fix: a previous fix tightened
            the header match to a whole-line anchored regex with no comment
            allowance, which broke this common, valid TOML shape (confirmed
            repro: it returned (-1, -1))
        """
        text = '[permissions] # my perms\nallow = [\n  "Bash(ls *)",\n]\n'
        start, end = find_section_boundaries(text, "permissions")
        self.assertNotEqual((start, end), (-1, -1))
        self.assertEqual(text[start:end], text)

    def test_header_with_trailing_comment_and_odd_spacing_is_recognized(self):
        """
        Given a [permissions] header line with irregular internal/trailing
            whitespace around a trailing "#" comment
            (e.g. "  [permissions]   #   spaced out")
        When find_section_boundaries() is called for "permissions"
        Then the header is still recognized despite the odd spacing
        """
        text = "  [permissions]   #   spaced out\nallow = [\n]\n"
        start, end = find_section_boundaries(text, "permissions")
        self.assertNotEqual((start, end), (-1, -1))
        self.assertEqual(text[start:end], text)

    def test_header_with_comment_containing_a_bracket_is_recognized(self):
        """
        Given a [permissions] header line whose trailing comment itself
            contains a "]" character (e.g. "# see [other] section")
        When find_section_boundaries() is called for "permissions"
        Then the header is still recognized -- the comment's own "]" must
            not confuse the header match
        """
        text = "[permissions] # see [other] section\nallow = [\n]\n"
        start, end = find_section_boundaries(text, "permissions")
        self.assertNotEqual((start, end), (-1, -1))
        self.assertEqual(text[start:end], text)

    def test_quoted_string_false_positive_still_not_matched_with_trailing_comment_allowance(
        self,
    ):
        """
        Given the SAME "[permissions]"-inside-a-quoted-string shape as
            test_ignores_section_name_appearing_inside_quoted_string_in_earlier_section,
            re-verified after the trailing-comment allowance was added
        When find_section_boundaries() is called for "permissions"
        Then it still locates only the REAL [permissions] header, never the
            substring occurrence inside the quoted additionalContext value --
            regression guard: the trailing-comment allowance must not
            reintroduce the original substring-match bug
        """
        text = (
            "[hard_deny]\n"
            "deny = [\n"
            '  { match = "Bash(rm -rf /)", additionalContext = "see [permissions] docs" },\n'
            "]\n"
            "\n"
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls *)",\n'
            "]\n"
        )
        start, end = find_section_boundaries(text, "permissions")
        self.assertEqual(text[start : start + len("[permissions]")], "[permissions]")
        self.assertEqual(
            text[start:end],
            '[permissions]\nallow = [\n  "Bash(ls *)",\n]\n',
        )


class TestParsePermissionsSectionWithComments(unittest.TestCase):
    """
    Characterization tests for parse_permissions_section_with_comments().

    Most of these predate the TOO-19 Phase 0b increment 3 tomllib-based
    rewrite and still hold unmodified against it. ``test_single_line_structured_entry_*``
    exercises the rewrite's capability directly: a structured ``{...}`` entry
    parsing as one logical ``rule`` item -- something the old
    one-pattern-per-physical-line scan could never do.
    ``test_multiline_structured_entry_raises_tomldecodeerror`` characterizes
    the complementary, deliberate NON-capability: a structured entry spanning
    more than one physical line is invalid TOML 1.0 and this parser must fail
    loudly on it, not accept or silently drop it (TOO-19 corrective change).
    """

    def test_plain_double_quoted_entry_parsed_as_rule(self):
        """
        Given an [permissions] allow list containing one double-quoted entry
        When parse_permissions_section_with_comments() is called
        Then the entry is returned as a single ('rule', <line>, <pattern>) item
        """
        text = '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(result["allow"], [("rule", '  "Bash(ls:*)",', "Bash(ls:*)")])
        self.assertEqual(result["deny"], [])
        self.assertEqual(result["ask"], [])

    def test_plain_single_quoted_entry_parsed_verbatim_no_unescaping(self):
        """
        Given an allow list containing one single-quoted (TOML literal string)
            entry with a backslash inside it, as used for regex patterns
        When parse_permissions_section_with_comments() is called
        Then the pattern value is the literal content verbatim (single-quoted
            TOML strings have no escape mechanism, so the backslash is kept
            as-is, not interpreted)
        """
        text = "[permissions]\nallow = [\n  'Bash([regex]\\bfind\\b)',\n]\n"
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [("rule", "  'Bash([regex]\\bfind\\b)',", "Bash([regex]\\bfind\\b)")],
        )

    def test_full_line_comment_above_entry_attached_as_preceding_comment_block(self):
        """
        Given an allow list with a full-line "#" comment immediately above an entry
        When parse_permissions_section_with_comments() is called
        Then the comment appears as a ('comment_block', ...) item immediately
            preceding the ('rule', ...) item for that entry
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # explains the rule below\n"
            '  "Bash(ls:*)",\n'
            "]\n"
        )
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [
                ("comment_block", "  # explains the rule below", None),
                ("rule", '  "Bash(ls:*)",', "Bash(ls:*)"),
            ],
        )

    def test_trailing_inline_comment_kept_inside_rule_line_content(self):
        """
        Given an entry with a trailing "# ..." comment on the same physical line
        When parse_permissions_section_with_comments() is called
        Then the rule item's content is the FULL original line, inline comment
            included (the parser does not split the inline comment out of
            "content" -- callers that need it separately, e.g. config_access.py,
            extract it themselves from this same line text)
        """
        text = '[permissions]\nallow = [\n  "Bash(ls:*)",  # only read-only\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [("rule", '  "Bash(ls:*)",  # only read-only', "Bash(ls:*)")],
        )

    def test_freestanding_blank_line_with_no_adjacent_comment_is_dropped(self):
        """
        Given a blank line between two entries that is NOT part of any comment
            block (no comment immediately before or after it accumulating it
            into a buffer)
        When parse_permissions_section_with_comments() is called
        Then the blank line is silently absent from the parsed structure --
            characterizes current behaviour; NOTE this means a plain blank-line
            separator between two rules (with no comment) does not survive a
            parse/reassemble round trip. Not necessarily a bug (it may be
            considered acceptable reformatting), but worth flagging as a real
            current limitation ahead of the rewrite.
        """
        text = '[permissions]\nallow = [\n  "Bash(a:*)",\n\n  "Bash(b:*)",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [
                ("rule", '  "Bash(a:*)",', "Bash(a:*)"),
                ("rule", '  "Bash(b:*)",', "Bash(b:*)"),
            ],
        )

    def test_blank_line_inside_active_comment_buffer_is_preserved(self):
        """
        Given a blank line sandwiched BETWEEN two comment lines immediately
            preceding an entry (i.e. the blank line falls inside an
            already-open comment buffer)
        When parse_permissions_section_with_comments() is called
        Then the blank line is kept as part of that comment_block's content
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # first comment line\n"
            "\n"
            "  # second comment line\n"
            '  "Bash(a:*)",\n'
            "]\n"
        )
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [
                (
                    "comment_block",
                    "  # first comment line\n\n  # second comment line",
                    None,
                ),
                ("rule", '  "Bash(a:*)",', "Bash(a:*)"),
            ],
        )

    def test_indentation_variations_preserved_verbatim_in_rule_content(self):
        """
        Given entries indented with different amounts of leading whitespace
        When parse_permissions_section_with_comments() is called
        Then each rule's "content" retains its own original indentation exactly
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '    "Bash(a:*)",\n'
            '  "Bash(b:*)",\n'
            '"Bash(c:*)",\n'
            "]\n"
        )
        result = parse_permissions_section_with_comments(text)
        contents = [item[1] for item in result["allow"]]
        self.assertEqual(
            contents,
            ['    "Bash(a:*)",', '  "Bash(b:*)",', '"Bash(c:*)",'],
        )

    def test_empty_list_returns_empty_lists_for_all_subsections(self):
        """
        Given a [permissions] section whose allow/deny/ask lists are all empty
        When parse_permissions_section_with_comments() is called
        Then all three keys map to empty lists
        """
        text = "[permissions]\nallow = [\n]\ndeny = [\n]\nask = [\n]\n"
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result,
            {"allow": [], "deny": [], "ask": [], "trailing_comment": None},
        )

    def test_single_entry_list_parsed_correctly(self):
        """
        Given an allow list with exactly one entry
        When parse_permissions_section_with_comments() is called
        Then that single entry is the only item in "allow"
        """
        text = '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(len(result["allow"]), 1)
        self.assertEqual(result["allow"][0][2], "Bash(ls:*)")

    def test_escaped_double_quote_no_longer_truncates_pattern_value(self):
        """
        Given a double-quoted entry containing an escaped quote (\\") in its body
        When parse_permissions_section_with_comments() is called
        Then the parsed pattern value is the FULL unescaped string, continuing
            past the escaped quote to the real closing quote -- this used to be
            a real bug (the old hand-rolled regex r'"([^"]*)"' had no concept of
            backslash-escaping and treated the escaped quote's own '"' as the
            string terminator, truncating to 'Bash(echo \\'). TOO-19 Phase 0b
            increment 3's rewrite onto per-chunk stdlib tomllib parsing fixes
            this as a side effect: tomllib understands TOML string escaping
            natively, so there is no longer a hand-rolled quote regex to have
            this bug in the first place.
        """
        text = '[permissions]\nallow = [\n  "Bash(echo \\"hi\\")",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(result["allow"][0][2], 'Bash(echo "hi")')

    def test_hash_inside_double_quoted_string_not_treated_as_comment(self):
        """
        Given a double-quoted entry whose body contains a literal "#" character
        When parse_permissions_section_with_comments() is called
        Then the "#" is kept as part of the pattern value, not treated as the
            start of a TOML comment (the line-level regex match captures
            everything between the quotes regardless of "#")
        """
        text = '[permissions]\nallow = [\n  "Bash(echo # not a comment)",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(result["allow"][0][2], "Bash(echo # not a comment)")

    def test_comma_inside_quoted_string_kept_intact(self):
        """
        Given a double-quoted entry whose body contains a literal comma
        When parse_permissions_section_with_comments() is called
        Then the comma is kept as part of the single pattern value (this
            parser operates per physical LINE, so an embedded comma inside
            one quoted string on one line never causes a spurious split)
        """
        text = '[permissions]\nallow = [\n  "Bash(echo a,b)",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(result["allow"][0][2], "Bash(echo a,b)")

    def test_parens_and_braces_inside_quoted_string_kept_intact(self):
        """
        Given a double-quoted entry whose body contains parentheses and braces
        When parse_permissions_section_with_comments() is called
        Then all of them are kept as part of the single pattern value
        """
        text = '[permissions]\nallow = [\n  "Bash(echo {a} (b))",\n]\n'
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(result["allow"][0][2], "Bash(echo {a} (b))")

    def test_comment_before_first_rule_and_after_last_rule_both_captured(self):
        """
        Given a comment block before the first rule and another after the last
            rule (before the closing bracket)
        When parse_permissions_section_with_comments() is called
        Then both comment blocks are present as separate comment_block items,
            in their original relative positions
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # top comment\n"
            '  "Bash(a:*)",\n'
            "  # bottom comment\n"
            "]\n"
        )
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [
                ("comment_block", "  # top comment", None),
                ("rule", '  "Bash(a:*)",', "Bash(a:*)"),
                ("comment_block", "  # bottom comment", None),
            ],
        )

    def test_single_line_structured_entry_parses_pattern_from_match_key(self):
        """
        Given a single-line structured entry ({ match = "...", ... })
        When parse_permissions_section_with_comments() is called
        Then it is returned as ONE ('rule', <line>, <pattern>) item whose
            parsed_value is the entry's "match" value (mirroring how a plain
            string entry's parsed_value is its own text) -- not the whole dict
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  { match = "Bash(git status)", additionalContext = "read-only" },\n'
            "]\n"
        )
        result = parse_permissions_section_with_comments(text)
        self.assertEqual(
            result["allow"],
            [
                (
                    "rule",
                    '  { match = "Bash(git status)", additionalContext = "read-only" },',
                    "Bash(git status)",
                )
            ],
        )

    def test_multiline_structured_entry_raises_tomldecodeerror(self):
        """
        Given a structured entry written across multiple physical lines (with a
            full-line leading comment above it, exercising that the leading
            comment does not somehow mask the failure)
        When parse_permissions_section_with_comments() is called
        Then it raises tomllib.TOMLDecodeError rather than silently accepting
            or silently dropping the entry -- TOO-19 corrective change: TOML
            1.0 forbids an inline table from spanning multiple physical lines,
            and this parser previously (wrongly) pre-normalized such an entry
            to make it parse, which let this module's own tooling round-trip a
            shape the runtime config loader could never actually read. A
            multi-line structured entry must now fail loudly here too, the
            same way tomllib itself has always rejected it.
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # about the structured rule\n"
            "  {\n"
            '    match = "Bash(git status)",\n'
            '    additionalContext = "read-only",\n'
            "  },\n"
            "]\n"
        )
        with self.assertRaises(tomllib.TOMLDecodeError):
            parse_permissions_section_with_comments(text)


class TestReassemblePermissionsSectionRoundTrip(unittest.TestCase):
    """
    Characterization tests for reassemble_permissions_section()'s round-trip
    behaviour with parse_permissions_section_with_comments().
    """

    def test_round_trip_byte_identical_for_already_sorted_unchanged_input(self):
        """
        Given [permissions] section text (with a leading comment on one entry
            and a trailing inline comment on another) that is already in
            canonical sort order
        When it is parsed and then reassembled with the same pattern values
            (auto_sort=True, the default)
        Then the reassembled text is byte-identical to the original input
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # leading comment\n"
            '  "Bash(ls:*)",\n'
            '  "Bash(pwd:*)",  # inline\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        new_permissions = {
            "allow": ["Bash(ls:*)", "Bash(pwd:*)"],
            "deny": [],
            "ask": [],
        }
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        self.assertEqual(reassembled, text)

    def test_comma_less_last_element_reemitted_with_comma_after_reorder(self):
        """
        Given a [permissions] array whose LAST element has no trailing comma
            (legal TOML) and which sorting will move out of last position
        When the section is parsed and reassembled with auto_sort=True
        Then the reused element span is normalized to end in a comma, so the
            result is still parseable TOML with both patterns intact

        Regression guard for review finding M5: the reused source span used to
        carry its missing trailing comma verbatim, so moving that element
        forward emitted "Unclosed array".
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(zz)",\n'
            '  "Bash(aa)"\n'  # last element, no trailing comma
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(aa)", "Bash(zz)"], "deny": [], "ask": []}
        )

        loaded = tomllib.loads(reassembled)
        self.assertEqual(loaded["permissions"]["allow"], ["Bash(aa)", "Bash(zz)"])

    def test_comma_less_last_element_with_inline_comment_stays_valid(self):
        """
        Given a comma-less last element that also carries an end-of-line
            comment
        When the section is reassembled with auto_sort=True so that element
            moves forward
        Then the comma is inserted on the CODE side (before the comment), the
            comment stays attached, and the output parses
        """
        text = '[permissions]\nallow = [\n  "Bash(zz)",\n  "Bash(aa)"  # why aa\n]\n'
        parsed = parse_permissions_section_with_comments(text)
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(aa)", "Bash(zz)"], "deny": [], "ask": []}
        )

        loaded = tomllib.loads(reassembled)
        self.assertEqual(loaded["permissions"]["allow"], ["Bash(aa)", "Bash(zz)"])
        self.assertIn("# why aa", reassembled)

    def test_comma_less_last_structured_entry_stays_valid(self):
        """
        Given a comma-less last element that is a single-line STRUCTURED entry
        When the section is reassembled with auto_sort=True so that entry moves
            forward
        Then the output parses and the entry's enrichment survives intact
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(zz)",\n'
            '  { match = "Bash(aa)", additionalContext = "keep me" }\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(aa)", "Bash(zz)"], "deny": [], "ask": []}
        )

        allow = tomllib.loads(reassembled)["permissions"]["allow"]
        self.assertEqual(
            allow[0], {"match": "Bash(aa)", "additionalContext": "keep me"}
        )
        self.assertEqual(allow[1], "Bash(zz)")

    def test_reassemble_omits_perm_types_with_no_entries(self):
        """
        Given new_permissions where "deny" and "ask" are empty lists
        When reassemble_permissions_section() is called
        Then the output contains only the "allow" block -- no "deny = [...]"
            or "ask = [...]" block is emitted at all, even empty ones
        """
        text = '[permissions]\nallow = [\n  "Bash(ls:*)",\n]\n'
        parsed = parse_permissions_section_with_comments(text)
        new_permissions = {"allow": ["Bash(ls:*)"], "deny": [], "ask": []}
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        self.assertNotIn("deny", reassembled)
        self.assertNotIn("ask", reassembled)

    def test_comment_before_first_rule_stays_anchored_to_top_after_reorder(self):
        """
        Given a comment block before the FIRST (unsorted-order) rule, where
            sorting will reorder that rule away from the top
        When the section is parsed and reassembled with auto_sort=True
        Then the comment block stays pinned at the top of the list (anchored
            to the SECTION, not "attached" and traveling with its original
            rule) -- this matches the parser's own documented "anchored to the
            top" behaviour for pre-first-rule comments, not a bug
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # about the zebra rule\n"
            '  "Bash(zebra:*)",\n'
            '  "Bash(apple:*)",\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        new_permissions = {
            "allow": ["Bash(zebra:*)", "Bash(apple:*)"],
            "deny": [],
            "ask": [],
        }
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        expected = (
            "[permissions]\n"
            "allow = [\n"
            "  # about the zebra rule\n"
            '  "Bash(apple:*)",\n'
            '  "Bash(zebra:*)",\n'
            "]\n"
        )
        self.assertEqual(reassembled, expected)

    def test_round_trip_byte_identical_for_unchanged_single_line_structured_entry(
        self,
    ):
        """
        HEADLINE requirement (TOO-19 corrective change: single-line is the ONLY
            valid contract for a structured entry -- see this module's
            top-of-file docstring): given [permissions] section text with a
            single-line structured entry (leading full-line comment above it,
            trailing inline comment on its own -- only -- line)
        When it is parsed and reassembled with a RuleEntry carrying the SAME
            pattern (and a recorded "raw", i.e. has_raw is True -- meaning
            nothing changed about it)
        Then the reassembled text is byte-identical to the original input
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            "  # about the structured rule\n"
            '  { match = "Bash(git status)", additionalContext = "read-only" },'
            "  # trailing note\n"
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        entry = RuleEntry(
            pattern="Bash(git status)",
            metadata=MappingProxyType({"additionalContext": "read-only"}),
            raw={"match": "Bash(git status)", "additionalContext": "read-only"},
        )
        new_permissions = {"allow": [entry], "deny": [], "ask": []}
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        self.assertEqual(reassembled, text)

    def test_sort_and_reassemble_reorders_single_line_structured_entry_verbatim(self):
        """
        Given an allow list with a single-line structured entry for "zebra"
            written FIRST in the file, and a plain "apple" entry written second
            (i.e. out of canonical sort order)
        When the section is parsed and reassembled with auto_sort=True
        Then "apple" now sorts first, and the "zebra" structured entry is
            reordered to second WITHOUT any change to its own text, byte-for-byte
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  { match = "Bash(zebra:*)", additionalContext = "careful" },\n'
            '  "Bash(apple:*)",\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        zebra_entry = RuleEntry(
            pattern="Bash(zebra:*)",
            metadata=MappingProxyType({"additionalContext": "careful"}),
            raw={"match": "Bash(zebra:*)", "additionalContext": "careful"},
        )
        new_permissions = {
            "allow": [zebra_entry, "Bash(apple:*)"],
            "deny": [],
            "ask": [],
        }
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        expected = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(apple:*)",\n'
            '  { match = "Bash(zebra:*)", additionalContext = "careful" },\n'
            "]\n"
        )
        self.assertEqual(reassembled, expected)

    def test_structured_entry_trailing_inline_comment_survives(self):
        """
        Given a single-line structured entry with a trailing "# ..." inline
            comment (after its closing "}" and comma)
        When the section is parsed and reassembled unchanged
        Then that trailing comment is still present in the reassembled output
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  { match = "Bash(git status)" },  # read-only, always safe\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        entry = RuleEntry(
            pattern="Bash(git status)",
            metadata=MappingProxyType({}),
            raw={"match": "Bash(git status)"},
        )
        new_permissions = {"allow": [entry], "deny": [], "ask": []}
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        self.assertIn("},  # read-only, always safe", reassembled)
        self.assertEqual(reassembled, text)

    def test_removing_neighbouring_plain_entry_leaves_structured_entry_verbatim(self):
        """
        Given an allow list with a plain entry AND a single-line structured
            entry
        When the section is reassembled with new_permissions that OMITS the
            plain entry (simulating its removal) but keeps the structured one
        Then the structured entry's own text is reproduced byte-for-byte,
            unaffected by its neighbour's removal
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls:*)",\n'
            '  { match = "Bash(git status)", additionalContext = "read-only" },\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        entry = RuleEntry(
            pattern="Bash(git status)",
            metadata=MappingProxyType({"additionalContext": "read-only"}),
            raw={"match": "Bash(git status)", "additionalContext": "read-only"},
        )
        new_permissions = {"allow": [entry], "deny": [], "ask": []}
        reassembled = reassemble_permissions_section(parsed, new_permissions)
        self.assertNotIn("Bash(ls:*)", reassembled)
        expected_block = (
            '  { match = "Bash(git status)", additionalContext = "read-only" },'
        )
        self.assertIn(expected_block, reassembled)

    def test_same_pattern_different_metadata_entries_both_survive_reassembly(
        self,
    ):
        """
        TOO-19 Change 4 fix: given two structured entries sharing the EXACT
            same pattern but differing ``additionalContext`` values -- the
            shape ``merge_entries``'s case-3 contradiction handling
            deliberately preserves side-by-side so a human can resolve them
        When the section is parsed and reassembled with both entries kept
            unchanged (same relative order as in the original file)
        Then BOTH entries' own original text -- and thus both distinct
            ``additionalContext`` values -- survive byte-for-byte, rather
            than one silently overwriting the other via a pattern-only key
            collision in rule_lines/rule_comments
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  { match = "Bash(git push:*)", additionalContext = "first note" },\n'
            '  { match = "Bash(git push:*)", additionalContext = "second note" },\n'
            "]\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        first_entry = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "first note"}),
            raw={"match": "Bash(git push:*)", "additionalContext": "first note"},
        )
        second_entry = RuleEntry(
            pattern="Bash(git push:*)",
            metadata=MappingProxyType({"additionalContext": "second note"}),
            raw={"match": "Bash(git push:*)", "additionalContext": "second note"},
        )
        new_permissions = {
            "allow": [first_entry, second_entry],
            "deny": [],
            "ask": [],
        }
        reassembled = reassemble_permissions_section(
            parsed, new_permissions, auto_sort=False
        )
        self.assertEqual(reassembled, text)
        self.assertIn("first note", reassembled)
        self.assertIn("second note", reassembled)

    def test_trailing_comment_after_final_array_survives_round_trip(self):
        """
        Given [permissions] section text with a comment (explaining a
            following [hard_deny] section) sitting AFTER the final ']' --
            i.e. outside any allow/deny/ask array
        When the section is parsed and reassembled with the same pattern
        Then the trailing comment is preserved byte-for-byte rather than
            silently dropped (TOO-19 review finding M1 regression fix)
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls *)",\n'
            "]\n"
            "\n"
            "# IMPORTANT: hard_deny below protects secrets\n"
            "\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        self.assertEqual(
            parsed["trailing_comment"],
            "# IMPORTANT: hard_deny below protects secrets\n\n",
        )
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(ls *)"], "deny": [], "ask": []}
        )
        self.assertEqual(reassembled, text)

    def test_multiple_trailing_comment_lines_survive_round_trip(self):
        """
        Given a [permissions] section whose trailing text (after the final
            ']') is TWO consecutive comment lines with no blank line between
            them
        When the section is parsed and reassembled unchanged
        Then both comment lines survive byte-for-byte
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls *)",\n'
            "]\n"
            "\n"
            "# first trailing line\n"
            "# second trailing line\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(ls *)"], "deny": [], "ask": []}
        )
        self.assertEqual(reassembled, text)

    def test_whitespace_only_trailing_text_adds_no_spurious_output(self):
        """
        Given a [permissions] section whose trailing text (after the final
            ']') is only blank lines, no comment
        When the section is parsed and reassembled
        Then no spurious trailing content is introduced -- the reassembled
            text is unchanged from the case with no trailing text at all
        """
        text = '[permissions]\nallow = [\n  "Bash(ls *)",\n]\n\n\n'
        parsed = parse_permissions_section_with_comments(text)
        self.assertIsNone(parsed["trailing_comment"])
        reassembled = reassemble_permissions_section(
            parsed, {"allow": ["Bash(ls *)"], "deny": [], "ask": []}
        )
        self.assertEqual(reassembled, '[permissions]\nallow = [\n  "Bash(ls *)",\n]\n')

    def test_trailing_comment_survives_when_auto_sort_reorders_entries(self):
        """
        Given a [permissions] section with an unsorted allow list AND a
            trailing comment after the final ']'
        When the section is parsed and reassembled with auto_sort=True
            (reordering the entries)
        Then the entries are reordered as expected AND the trailing comment
            still survives, unaffected by the reorder
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(zebra:*)",\n'
            '  "Bash(apple:*)",\n'
            "]\n"
            "\n"
            "# trailing note about hard_deny\n"
        )
        parsed = parse_permissions_section_with_comments(text)
        reassembled = reassemble_permissions_section(
            parsed,
            {"allow": ["Bash(zebra:*)", "Bash(apple:*)"], "deny": [], "ask": []},
        )
        expected = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(apple:*)",\n'
            '  "Bash(zebra:*)",\n'
            "]\n"
            "\n"
            "# trailing note about hard_deny\n"
        )
        self.assertEqual(reassembled, expected)


# =============================================================================
# Part 2 (increment 2): direct tests for the new split_array_elements scanner
# =============================================================================


class TestSplitArrayElements(unittest.TestCase):
    """
    Direct unit tests for split_array_elements() -- the tool-name-agnostic
    top-level array-element boundary scanner added in TOO-19 Phase 0b
    increment 2 and wired into production by increment 3's rewrite of
    parse_permissions_section_with_comments (via _parse_array_body).
    """

    def test_empty_input_returns_no_elements(self):
        """
        Given an empty string (an empty array's interior)
        When split_array_elements() is called
        Then it returns an empty tuple
        """
        self.assertEqual(split_array_elements(""), ())

    def test_whitespace_only_input_returns_no_elements(self):
        """
        Given input containing only whitespace and newlines (no value at all)
        When split_array_elements() is called
        Then it returns an empty tuple -- there is no element to represent
            this text, but the caller already holds the original slice
            directly (it is not lost, just not echoed back as an element)
        """
        self.assertEqual(split_array_elements("\n  \n  \n"), ())

    def test_single_plain_string_element_with_trailing_comma(self):
        """
        Given the interior of a one-element array, "Bash(ls:*)" with a
            trailing comma, surrounded by newlines/indentation
        When split_array_elements() is called
        Then exactly one ArrayElement is returned whose .text is the quoted
            pattern, whose .leading carries the leading padding, and whose
            .trailing is exactly the delimiting comma -- the newline AFTER
            that comma is not part of any element (there is no further
            element to attach it to as leading text); it remains accessible
            via text[element.segment_end:], the documented "leftover" pattern
        """
        text = '\n  "Bash(ls:*)",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        element = elements[0]
        self.assertEqual(element.text, '"Bash(ls:*)"')
        self.assertEqual(element.leading, "\n  ")
        self.assertEqual(element.trailing, ",")
        self.assertEqual(text[element.segment_end :], "\n")

    def test_single_element_with_no_trailing_comma(self):
        """
        Given the interior of a one-element array with NO trailing comma
            (the last-element-before-"]" case)
        When split_array_elements() is called
        Then one ArrayElement is returned, its trailing has no comma, and its
            segment_end reaches the end of the input text
        """
        text = '\n  "Bash(ls:*)"\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        element = elements[0]
        self.assertEqual(element.text, '"Bash(ls:*)"')
        self.assertNotIn(",", element.trailing)
        self.assertEqual(element.segment_end, len(text))

    def test_two_plain_elements_split_on_top_level_comma(self):
        """
        Given two plain-string elements separated by a comma
        When split_array_elements() is called
        Then two ArrayElements are returned with the correct .text values, in order
        """
        text = '\n  "Bash(ls:*)",\n  "Bash(pwd:*)",\n'
        elements = split_array_elements(text)
        self.assertEqual([e.text for e in elements], ['"Bash(ls:*)"', '"Bash(pwd:*)"'])

    def test_comma_inside_quoted_string_not_treated_as_boundary(self):
        """
        Given a single element whose quoted body contains a literal comma
        When split_array_elements() is called
        Then exactly one element is produced (the embedded comma is NOT
            mistaken for a top-level array-element separator)
        """
        text = '\n  "Bash(echo a,b)",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].text, '"Bash(echo a,b)"')

    def test_hash_inside_quoted_string_not_treated_as_comment(self):
        """
        Given a single quoted element whose body contains a literal "#"
        When split_array_elements() is called
        Then the "#" does not trigger comment-skipping (which would otherwise
            swallow the rest of the line, including the closing quote)
        """
        text = '\n  "Bash(echo # x)",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].text, '"Bash(echo # x)"')

    def test_escaped_double_quote_does_not_end_the_string_early(self):
        """
        Given a double-quoted element containing an escaped quote (\\")
        When split_array_elements() is called
        Then the scanner correctly continues past the escaped quote to the
            REAL closing quote, producing the full element text (in contrast
            to the OLD line-regex parser's truncation bug characterized in
            TestParsePermissionsSectionWithComments above)
        """
        text = '\n  "Bash(echo \\"hi\\")",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].text, '"Bash(echo \\"hi\\")"')

    def test_braces_inside_quoted_string_not_counted_as_table_depth(self):
        """
        Given a quoted plain-string element whose body contains "{" and "}"
        When split_array_elements() is called
        Then the braces are treated as ordinary text, not as inline-table
            delimiters (the element is still recognized as a plain string)
        """
        text = '\n  "Bash(echo {a})",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        self.assertEqual(elements[0].text, '"Bash(echo {a})"')

    def test_single_line_inline_table_element(self):
        """
        Given a single-line structured entry: { match = "...", additionalContext = "..." }
        When split_array_elements() is called
        Then one element is returned whose .text is the whole inline table,
            and start_line == end_line (it is on one physical line)
        """
        text = '\n  { match = "Bash(git status)", additionalContext = "read-only" },\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        element = elements[0]
        self.assertEqual(
            element.text,
            '{ match = "Bash(git status)", additionalContext = "read-only" }',
        )
        self.assertEqual(element.start_line, element.end_line)

    def test_nested_braces_in_structured_entry(self):
        """
        Given a structured entry whose value contains a nested inline table
            (brace depth 2)
        When split_array_elements() is called
        Then the element's .text spans all the way to the OUTER closing brace,
            not the first (inner) one
        """
        text = '\n  { match = "Bash(x)", meta = { a = 1, b = 2 } },\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        self.assertEqual(
            elements[0].text, '{ match = "Bash(x)", meta = { a = 1, b = 2 } }'
        )

    def test_multiline_structured_entry_spans_correct_line_range(self):
        """
        Given a structured entry written across multiple physical lines
        When split_array_elements() is called
        Then one element is returned whose start_line is the line with the
            opening "{" and whose end_line is the line with the closing "}"
            (a multi-line span, start_line != end_line)
        """
        text = (
            "\n"
            "  {\n"
            '    match = "Bash(git status)",\n'
            '    additionalContext = "read-only",\n'
            "  },\n"
        )
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 1)
        element = elements[0]
        self.assertEqual(element.start_line, 2)
        self.assertEqual(element.end_line, 5)
        self.assertTrue(element.text.startswith("{"))
        self.assertTrue(element.text.endswith("}"))

    def test_trailing_comma_before_closing_bracket_produces_no_phantom_element(self):
        """
        Given two elements where the SECOND (last) one also has a trailing
            comma (i.e. what would be "[a, b,]" -- text is everything between
            "[" and "]", so this is "a," + "b," with nothing meaningful after)
        When split_array_elements() is called
        Then exactly two elements are returned -- no spurious empty third
            element is created for the text after the final comma
        """
        text = '\n  "Bash(a:*)",\n  "Bash(b:*)",\n'
        elements = split_array_elements(text)
        self.assertEqual([e.text for e in elements], ['"Bash(a:*)"', '"Bash(b:*)"'])

    def test_comment_between_elements_becomes_leading_text_of_next_element(self):
        """
        Given a full-line "#" comment interleaved between two elements
        When split_array_elements() is called
        Then the comment line is not mistaken for element content and appears
            verbatim inside the SECOND element's .leading text (comments
            "travel with" the following element, matching the old parser's
            comment-attachment semantics)
        """
        text = '\n  "Bash(a:*)",\n  # about b\n  "Bash(b:*)",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 2)
        self.assertIn("# about b", elements[1].leading)
        self.assertEqual(elements[1].text, '"Bash(b:*)"')

    def test_element_positions_are_correct_offsets_into_input(self):
        """
        Given a simple single-element input
        When split_array_elements() is called
        Then start_pos/end_pos slice exactly the element's own .text out of
            the original input string
        """
        text = '\n  "Bash(ls:*)",\n'
        element = split_array_elements(text)[0]
        self.assertEqual(text[element.start_pos : element.end_pos], element.text)

    def test_leading_text_trailing_reconstruct_each_elements_own_segment(self):
        """
        Given any element produced by split_array_elements()
        When its leading, text, and trailing are concatenated
        Then the result equals the original input's slice from segment_start
            to segment_end for that element (per-element reconstruction
            invariant)
        """
        text = '\n  # a note\n  "Bash(a:*)",\n  "Bash(b:*)",  # trailing note\n'
        elements = split_array_elements(text)
        for element in elements:
            self.assertEqual(
                element.leading + element.text + element.trailing,
                text[element.segment_start : element.segment_end],
            )

    def test_full_reconstruction_across_all_elements_plus_leftover(self):
        """
        Given a realistic mix of plain and structured elements with comments,
            blank lines, and a trailing comment after the last element with
            no further value (before the array's closing "]")
        When all elements' (leading + text + trailing) are concatenated in
            order, followed by whatever text remains after the LAST element's
            segment_end
        Then the result equals the original input byte-for-byte
        """
        text = (
            "\n"
            "  # leading section note\n"
            '  "Bash(a:*)",\n'
            "\n"
            "  # about the structured one\n"
            '  { match = "Bash(git status)", additionalContext = "ro" },  # inline\n'
            '  "Bash(b:*)"\n'
            "  # trailing note, no comma after b above\n"
        )
        elements = split_array_elements(text)
        rebuilt = "".join(e.leading + e.text + e.trailing for e in elements)
        rebuilt += text[elements[-1].segment_end :]
        self.assertEqual(rebuilt, text)

    def test_inline_table_trailing_inline_comment_is_captured_in_trailing(self):
        """
        Given a structured entry followed by a trailing "# ..." comment on its
            own last line, before the delimiting comma
        When split_array_elements() is called
        Then the element's .trailing contains that inline comment text (this
            is what lets a future config_access.py-style consumer extract a
            trailing comment from a chunk's LAST line, generalized to
            multi-line entries)
        """
        text = '\n  { match = "Bash(x)" }  # note\n  , "Bash(y)",\n'
        elements = split_array_elements(text)
        self.assertEqual(len(elements), 2)
        self.assertIn("# note", elements[0].trailing)

    def test_returned_element_is_array_element_type(self):
        """
        Given any parseable input
        When split_array_elements() is called
        Then each returned item is an instance of ArrayElement
        """
        elements = split_array_elements('\n  "Bash(ls:*)",\n')
        self.assertIsInstance(elements[0], ArrayElement)


# =============================================================================
# Part 3 (TOO-19 corrective change): direct tests for the multi-line
# structured entry diagnostic scanner
# =============================================================================


class TestFindMultilineStructuredEntryLine(unittest.TestCase):
    """
    Direct unit tests for find_multiline_structured_entry_line() -- the
    scanner toolguard.config._parse_source uses to upgrade a raw
    TOMLDecodeError into an actionable message naming the offending line.
    """

    def test_returns_none_for_file_with_no_permissions_section(self):
        """
        Given TOML text with no [permissions] section at all
        When find_multiline_structured_entry_line() is called
        Then it returns None (nothing to scan)
        """
        text = "[general]\nfoo = 1\n"
        self.assertIsNone(find_multiline_structured_entry_line(text))

    def test_returns_none_for_only_single_line_entries(self):
        """
        Given a [permissions] section containing only single-line entries
            (plain and structured)
        When find_multiline_structured_entry_line() is called
        Then it returns None -- there is nothing to diagnose
        """
        text = (
            "[permissions]\n"
            "allow = [\n"
            '  "Bash(ls:*)",\n'
            '  { match = "Bash(git status)", additionalContext = "ro" },\n'
            "]\n"
        )
        self.assertIsNone(find_multiline_structured_entry_line(text))

    def test_finds_line_of_multiline_entry_in_allow(self):
        """
        Given a [permissions] section whose allow list contains one multi-line
            structured entry, preceded by an unrelated single-line entry
        When find_multiline_structured_entry_line() is called
        Then it returns the 1-based line number of the offending entry's own
            opening "{", not the file's first line or the array's own line
        """
        text = (
            "[permissions]\n"  # line 1
            "allow = [\n"  # line 2
            '  "Bash(ls:*)",\n'  # line 3
            "  {\n"  # line 4 -- the opening "{" of the offending entry
            '    match = "Bash(git status)",\n'  # line 5
            "  },\n"  # line 6
            "]\n"  # line 7
        )
        self.assertEqual(find_multiline_structured_entry_line(text), 4)

    def test_finds_line_of_multiline_entry_in_deny(self):
        """
        Given a multi-line structured entry in the "deny" list, with the
            "allow" list (all single-line) coming first
        When find_multiline_structured_entry_line() is called
        Then it still finds it -- every subsection is scanned, not just allow
        """
        text = (
            "[permissions]\n"  # line 1
            "allow = [\n"  # line 2
            '  "Bash(ls:*)",\n'  # line 3
            "]\n"  # line 4
            "deny = [\n"  # line 5
            "  {\n"  # line 6
            '    match = "Bash(rm:*)",\n'  # line 7
            "  },\n"  # line 8
            "]\n"  # line 9
        )
        self.assertEqual(find_multiline_structured_entry_line(text), 6)

    def test_does_not_misattribute_an_unrelated_toml_error(self):
        """
        Given a [permissions] section with a genuinely malformed (but NOT
            multi-line-structured-entry) array -- an unterminated string
        When find_multiline_structured_entry_line() is called
        Then it returns None rather than guessing wrong: a caller building a
            diagnostic message must fall back to the generic tomllib message
            for any cause other than the one this scanner actually detects
        """
        text = '[permissions]\nallow = [\n  "Bash(ls:*)\n]\n'
        self.assertIsNone(find_multiline_structured_entry_line(text))


# =============================================================================
# Part 4 (TOO-19 review-round-2 fix): render_toml_entry must not crash on a
# JSON permissions-list element that is neither a plain string nor a dict.
# =============================================================================


class TestRenderTomlEntry(unittest.TestCase):
    """
    Direct unit tests for render_toml_entry() -- confirmed repro was an
    AttributeError for any non-str, non-dict entry value, since a JSON
    config's permissions.allow list may legitimately hold any JSON value
    (RuleEntry.to_source() deliberately preserves it -- see
    normalize_entries_preserving()). The fix delegates to the module's
    existing total scalar renderer, _render_toml_scalar; these tests cover
    every new shape plus the two previously-supported ones, to confirm no
    behaviour change for those.
    """

    def test_plain_string_pattern_renders_as_quoted_string(self):
        """
        Given a bare pattern string
        When render_toml_entry() is called
        Then it renders as a double-quoted TOML string (unchanged behaviour)
        """
        self.assertEqual(render_toml_entry("Bash(ls)"), '"Bash(ls)"')

    def test_structured_dict_pattern_renders_as_inline_table(self):
        """
        Given a structured entry dict with a pattern and metadata
        When render_toml_entry() is called
        Then it renders as a single-line TOML inline table (unchanged
            behaviour)
        """
        entry = {"match": "Bash(*)", "additionalContext": "x"}
        self.assertEqual(
            render_toml_entry(entry), '{ match = "Bash(*)", additionalContext = "x" }'
        )

    def test_int_entry_value_renders_without_crashing(self):
        """
        Given a RuleEntry.to_source()-like raw int value (e.g. a JSON
            permissions.allow element that is a bare number)
        When render_toml_entry() is called directly on the int
        Then it renders as a bare TOML integer instead of raising
            AttributeError (confirmed repro)
        """
        self.assertEqual(render_toml_entry(42), "42")

    def test_bool_entry_value_renders_without_crashing(self):
        """
        Given a bool entry value
        When render_toml_entry() is called
        Then it renders as a bare TOML boolean literal
        """
        self.assertEqual(render_toml_entry(True), "true")
        self.assertEqual(render_toml_entry(False), "false")

    def test_none_entry_value_renders_without_crashing(self):
        """
        Given a None entry value (e.g. a parsed JSON `null` element)
        When render_toml_entry() is called
        Then it renders via the scalar renderer's str() fallback instead of
            raising AttributeError
        """
        self.assertEqual(render_toml_entry(None), '"None"')

    def test_list_entry_value_renders_without_crashing(self):
        """
        Given a list entry value
        When render_toml_entry() is called
        Then it renders as a bare TOML array instead of raising AttributeError
        """
        self.assertEqual(render_toml_entry(["a", "b"]), '["a", "b"]')

    def test_rule_entry_with_raw_non_str_non_dict_source_does_not_crash(self):
        """
        Given a RuleEntry with an original `raw=42` (has_raw True) -- exactly
            what normalize_entries_preserving() produces for a JSON
            permissions.allow element that is a bare int, since to_source()
            returns `raw` verbatim for any recorded (non-synthesized) entry
        When render_toml_entry() is called on the RuleEntry
        Then it renders the int via the scalar renderer instead of raising
            AttributeError (this is the exact RuleEntry-wrapped shape the
            write path (migrate_permissions/rule_apply) actually feeds
            render_toml_entry, not just a bare int)
        """
        entry = RuleEntry(pattern=repr(42), metadata={}, raw=42)
        self.assertEqual(render_toml_entry(entry), "42")


# =============================================================================
# Part 5 (TOO-19 review-round-2 fix): a malformed structured entry's parsed
# pattern must be recognisable as SYNTHETIC, not mistaken for a real pattern.
# =============================================================================


class TestIsSyntheticPattern(unittest.TestCase):
    """
    Direct unit tests for is_synthetic_pattern() and the SyntheticPattern
    marker _rule_pattern_of_value() now returns for a malformed ("rule") array
    element (e.g. a structured entry missing its "match" key) -- previously a
    bare str indistinguishable from a real pattern, which let
    maintenance._permission_patterns_in_text() feed it into the config-write
    content-loss guard as an "expected" pattern that could never actually
    appear in the written text, wrongly refusing the write.
    """

    def test_malformed_structured_entry_parses_to_synthetic_pattern(self):
        """
        Given a [permissions] section whose sole allow entry is a structured
            table MISSING the required "match" key
        When parse_permissions_section_with_comments() parses it
        Then the "rule" item's parsed_value is recognised by
            is_synthetic_pattern() as synthetic, not a real pattern
        """
        text = '[permissions]\nallow = [\n  { additionalContext = "oops" },\n]\n'
        parsed = parse_permissions_section_with_comments(text)
        (item_type, _content, value) = parsed["allow"][0]
        self.assertEqual(item_type, "rule")
        self.assertTrue(is_synthetic_pattern(value))

    def test_real_pattern_is_not_synthetic(self):
        """
        Given a well-formed plain-string allow entry
        When parse_permissions_section_with_comments() parses it
        Then its parsed_value is NOT reported as synthetic by
            is_synthetic_pattern()
        """
        text = '[permissions]\nallow = [\n  "Bash(ls)",\n]\n'
        parsed = parse_permissions_section_with_comments(text)
        (item_type, _content, value) = parsed["allow"][0]
        self.assertEqual(item_type, "rule")
        self.assertFalse(is_synthetic_pattern(value))

    def test_real_structured_pattern_is_not_synthetic(self):
        """
        Given a well-formed structured allow entry (has a "match" key)
        When parse_permissions_section_with_comments() parses it
        Then its parsed_value (the pattern under "match") is NOT reported as
            synthetic
        """
        text = (
            '[permissions]\nallow = [\n  { match = "Bash(ls)", additionalContext'
            ' = "x" },\n]\n'
        )
        parsed = parse_permissions_section_with_comments(text)
        (item_type, _content, value) = parsed["allow"][0]
        self.assertEqual(item_type, "rule")
        self.assertEqual(value, "Bash(ls)")
        self.assertFalse(is_synthetic_pattern(value))

    def test_synthetic_pattern_still_behaves_as_a_plain_string(self):
        """
        Given a SyntheticPattern value produced for a malformed entry
        When used as a plain string (equality, dict key)
        Then it behaves identically to an ordinary str -- the marker is
            purely a type-level tag, not a behavioural difference, so every
            existing consumer keying off parsed_value keeps working unchanged
        """
        text = '[permissions]\nallow = [\n  { additionalContext = "oops" },\n]\n'
        parsed = parse_permissions_section_with_comments(text)
        (_item_type, _content, value) = parsed["allow"][0]
        self.assertEqual(value, repr({"additionalContext": "oops"}))
        self.assertEqual({value: "ok"}[value], "ok")


if __name__ == "__main__":
    unittest.main()
