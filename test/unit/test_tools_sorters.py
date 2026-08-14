"""
Unit tests for toolguard.tools.sorters -- canonical rule-array sorting: tool
priority (Bash, Read, Write, Edit, then anything else), and within a bucket
case-insensitive alphabetical on the full pattern string.
"""

import unittest
from types import MappingProxyType

from toolguard.rule_entry import RuleEntry
from toolguard.tools.sorters import sort_patterns, sort_layer_rules, stable_rule_key


class TestSortPatterns(unittest.TestCase):
    """Tests for sort_patterns() -- canonical ordering of a single list."""

    def test_bash_comes_before_read(self):
        """
        Given a list containing both Bash and Read patterns in any order
        When sort_patterns() is called
        Then all Bash patterns appear before all Read patterns, and no pattern
             is lost on the way
        """
        patterns = ["Read(/tmp/*)", "Bash(git status:*)", "Read(/home/*)", "Bash(ls:*)"]
        result = sort_patterns(patterns)
        bash_indices = [i for i, p in enumerate(result) if p.startswith("Bash(")]
        read_indices = [i for i, p in enumerate(result) if p.startswith("Read(")]
        self.assertEqual(len(bash_indices), 2)
        self.assertEqual(len(read_indices), 2)
        self.assertTrue(max(bash_indices) < min(read_indices))

    def test_tool_priority_order_bash_read_write_edit(self):
        """
        Given a list with Bash, Read, Write, and Edit patterns in reverse order
        When sort_patterns() is called
        Then the order is exactly Bash, Read, Write, Edit -- which alphabetical
             order alone would not produce (Edit precedes Read and Write)
        """
        patterns = [
            "Edit(~/project/file.py)",
            "Write(/tmp/out.txt)",
            "Read(/home/user/*)",
            "Bash(git status:*)",
        ]
        result = sort_patterns(patterns)
        self.assertEqual(
            result,
            [
                "Bash(git status:*)",
                "Read(/home/user/*)",
                "Write(/tmp/out.txt)",
                "Edit(~/project/file.py)",
            ],
        )

    def test_within_tool_sorted_alphabetically_by_full_pattern(self):
        """
        Given multiple Bash patterns in non-alphabetical order
        When sort_patterns() is called
        Then they appear in case-insensitive alphabetical order by full pattern
        """
        patterns = [
            "Bash(uv run pytest:*)",
            "Bash(git status:*)",
            "Bash(ls:*)",
            "Bash(cat:*)",
        ]
        result = sort_patterns(patterns)
        self.assertEqual(
            result,
            [
                "Bash(cat:*)",
                "Bash(git status:*)",
                "Bash(ls:*)",
                "Bash(uv run pytest:*)",
            ],
        )

    def test_already_canonical_input_is_unchanged(self):
        """
        Given a list already in canonical order
        When sort_patterns() is called
        Then the order is unchanged -- sorting is idempotent, so a reversed or
             otherwise re-ordered sort is visible even when nothing needs moving
        """
        canonical = [
            "Bash(a:*)",
            "Bash(b:*)",
            "Read(/home/*)",
            "Write(/tmp/out.txt)",
            "Edit(file.py)",
        ]
        self.assertEqual(sort_patterns(canonical), canonical)

    def test_duplicate_patterns_are_all_preserved(self):
        """
        Given a list containing the same pattern more than once
        When sort_patterns() is called
        Then every occurrence survives -- the result has the same length as the
             input and the duplicate appears twice
        """
        patterns = ["Read(/tmp/*)", "Bash(ls:*)", "Bash(ls:*)", "Bash(cat:*)"]
        result = sort_patterns(patterns)
        self.assertEqual(len(result), len(patterns))
        self.assertEqual(
            result, ["Bash(cat:*)", "Bash(ls:*)", "Bash(ls:*)", "Read(/tmp/*)"]
        )

    def test_empty_list_returns_a_new_empty_list(self):
        """
        Given an empty pattern list
        When sort_patterns() is called
        Then a new empty list is returned, not the caller's own list
        """
        source = []
        result = sort_patterns(source)
        self.assertEqual(result, [])
        self.assertIsNot(result, source)

    def test_single_element_returns_unchanged_in_a_new_list(self):
        """
        Given a single-element pattern list
        When sort_patterns() is called
        Then the same single element comes back in a new list
        """
        source = ["Bash(git diff:*)"]
        result = sort_patterns(source)
        self.assertEqual(result, ["Bash(git diff:*)"])
        self.assertIsNot(result, source)

    def test_original_list_not_mutated(self):
        """
        Given a pattern list
        When sort_patterns() is called
        Then the original list is not mutated
        """
        original = ["Read(z/*)", "Bash(a:*)", "Write(m.txt)"]
        original_copy = list(original)
        sort_patterns(original)
        self.assertEqual(original, original_copy)

    def test_stable_sort_preserves_equal_key_order(self):
        """
        Given two patterns differing only in case, lowercase first
        When sort_patterns() is called
        Then they retain their relative order -- the keys tie because the sort
             is case-insensitive, and a stable sort leaves ties alone
        """
        patterns = ["Bash(git status:*)", "Bash(Git Status:*)", "Read(/tmp/*)"]
        result = sort_patterns(patterns)
        bash_in_result = [p for p in result if p.startswith("Bash(")]
        self.assertEqual(len(bash_in_result), 2)
        idx_lower = result.index("Bash(git status:*)")
        idx_upper = result.index("Bash(Git Status:*)")
        self.assertLess(idx_lower, idx_upper)

    def test_case_insensitive_sort_within_tool(self):
        """
        Given Bash patterns with mixed case
        When sort_patterns() is called
        Then sorting within the tool bucket is case-insensitive, so lowercase
             'awk' precedes uppercase 'Curl' and 'Zsh'
        """
        patterns = ["Bash(Zsh:*)", "Bash(awk:*)", "Bash(Curl:*)"]
        result = sort_patterns(patterns)
        self.assertEqual(result, ["Bash(awk:*)", "Bash(Curl:*)", "Bash(Zsh:*)"])

    def test_unknown_tool_sorts_after_edit(self):
        """
        Given a pattern whose unrecognised tool name sorts alphabetically BEFORE
             every known tool
        When sort_patterns() is called
        Then it still sorts last, so only the priority rank (4, above Edit's 3)
             can have put it there
        """
        patterns = ["Bash(git:*)", "AaaTool(some:*)", "Edit(file.py)"]
        result = sort_patterns(patterns)
        self.assertEqual(result, ["Bash(git:*)", "Edit(file.py)", "AaaTool(some:*)"])

    def test_extended_syntax_prefix_sorts_within_tool_bucket(self):
        """
        Given Bash patterns including extended-syntax prefixed forms
        When sort_patterns() is called
        Then all three stay in the Bash bucket ordered by full pattern, which
             puts the '[' -prefixed forms ahead of a plain command
        """
        patterns = [
            "Bash([regex]^git\\b)",
            "Bash(uv run:*)",
            "Bash([glob]git/**)",
        ]
        result = sort_patterns(patterns)
        self.assertEqual(
            result,
            ["Bash([glob]git/**)", "Bash([regex]^git\\b)", "Bash(uv run:*)"],
        )


class TestSortPatternsWithRuleEntry(unittest.TestCase):
    """sort_patterns, as re-exported by sorters, tolerates structured RuleEntry."""

    def test_does_not_raise_on_structured_entry(self):
        """
        Given a list mixing plain string patterns and a structured RuleEntry
        When sort_patterns() (as exported by toolguard.tools.sorters) sorts it
        Then it does not raise and the RuleEntry is present in the result
        """
        structured = RuleEntry(
            pattern="Bash(git *)",
            metadata=MappingProxyType({"additionalContext": "be careful"}),
        )
        result = sort_patterns(["Read(/tmp/*)", structured, "Bash(a:*)"])
        self.assertIn(structured, result)

    def test_orders_by_pattern_ignoring_metadata(self):
        """
        Given two RuleEntry sharing a tool bucket but differing metadata
        When sort_patterns() orders them alongside a plain string
        Then ordering follows each entry's .pattern only -- metadata never
             affects the sort position
        """
        entry_a = RuleEntry(
            pattern="Bash(a:*)", metadata=MappingProxyType({"additionalContext": "x"})
        )
        entry_b = RuleEntry(
            pattern="Bash(b:*)", metadata=MappingProxyType({"additionalContext": "y"})
        )
        result = sort_patterns([entry_b, "Read(/tmp/*)", entry_a])
        self.assertEqual(result, [entry_a, entry_b, "Read(/tmp/*)"])


class TestSortLayerRules(unittest.TestCase):
    """Tests for sort_layer_rules() -- sorting allow/deny/ask independently."""

    def test_all_three_lists_sorted(self):
        """
        Given allow, deny, and ask lists with distinct contents, each unsorted
        When sort_layer_rules() is called
        Then each list comes back sorted and in its own position in the tuple
        """
        allow = ["Read(z/*)", "Bash(a:*)"]
        deny = ["Write(y.txt)", "Bash(b:*)"]
        ask = ["Edit(x.py)", "Bash(c:*)"]
        sa, sd, sask = sort_layer_rules(allow, deny, ask)
        self.assertEqual(sa, ["Bash(a:*)", "Read(z/*)"])
        self.assertEqual(sd, ["Bash(b:*)", "Write(y.txt)"])
        self.assertEqual(sask, ["Bash(c:*)", "Edit(x.py)"])

    def test_none_ask_returns_none(self):
        """
        Given None as the ask list
        When sort_layer_rules() is called
        Then the returned ask value is also None, and allow and deny are sorted
        """
        sa, sd, sask = sort_layer_rules(
            ["Read(b/*)", "Bash(a:*)"], ["Write(d.txt)", "Bash(c:*)"], None
        )
        self.assertIsNone(sask)
        self.assertEqual(sa, ["Bash(a:*)", "Read(b/*)"])
        self.assertEqual(sd, ["Bash(c:*)", "Write(d.txt)"])

    def test_original_lists_not_mutated(self):
        """
        Given allow, deny and ask lists
        When sort_layer_rules() is called
        Then none of the originals is mutated
        """
        allow = ["Read(z/*)", "Bash(a:*)"]
        deny = ["Write(y.txt)", "Bash(b:*)"]
        ask = ["Edit(x.py)", "Bash(c:*)"]
        allow_copy, deny_copy, ask_copy = list(allow), list(deny), list(ask)
        sort_layer_rules(allow, deny, ask)
        self.assertEqual(allow, allow_copy)
        self.assertEqual(deny, deny_copy)
        self.assertEqual(ask, ask_copy)

    def test_empty_lists(self):
        """
        Given empty allow, deny and ask lists
        When sort_layer_rules() is called
        Then empty lists are returned -- an empty ask stays [] and does not
             become None
        """
        sa, sd, sask = sort_layer_rules([], [], [])
        self.assertEqual(sa, [])
        self.assertEqual(sd, [])
        self.assertEqual(sask, [])

    def test_accepts_structured_rule_entries(self):
        """
        Given RuleEntry objects rather than pattern strings
        When sort_layer_rules() is called
        Then they sort by .pattern like any other entry -- the List[str]
             annotation is narrower than the behaviour
        """
        entry_bash = RuleEntry(
            pattern="Bash(a:*)", metadata=MappingProxyType({"additionalContext": "x"})
        )
        entry_read = RuleEntry(
            pattern="Read(/tmp/*)",
            metadata=MappingProxyType({"additionalContext": "y"}),
        )
        sa, sd, sask = sort_layer_rules([entry_read, entry_bash], [], None)
        self.assertEqual(sa, [entry_bash, entry_read])
        self.assertEqual(sd, [])
        self.assertIsNone(sask)


class TestStableRuleKey(unittest.TestCase):
    """Tests for stable_rule_key() -- exposed canonical sort key."""

    def test_bash_has_lowest_tool_priority(self):
        """
        Given a Bash pattern
        When stable_rule_key() is called
        Then the type rank is 0 (sorts first in ascending sort)
        """
        key = stable_rule_key("Bash(git status:*)")
        self.assertEqual(key[0], 0)

    def test_read_has_tool_priority_one(self):
        """
        Given a Read pattern
        When stable_rule_key() is called
        Then the type rank is 1
        """
        key = stable_rule_key("Read(/tmp/*)")
        self.assertEqual(key[0], 1)

    def test_write_has_tool_priority_two(self):
        """
        Given a Write pattern
        When stable_rule_key() is called
        Then the type rank is 2
        """
        key = stable_rule_key("Write(/tmp/out.txt)")
        self.assertEqual(key[0], 2)

    def test_edit_has_tool_priority_three(self):
        """
        Given an Edit pattern
        When stable_rule_key() is called
        Then the type rank is 3
        """
        key = stable_rule_key("Edit(~/project/file.py)")
        self.assertEqual(key[0], 3)

    def test_unknown_tool_has_priority_four(self):
        """
        Given a pattern for an unrecognised tool
        When stable_rule_key() is called
        Then the type rank is 4 (sorts last)
        """
        key = stable_rule_key("UnknownTool(stuff:*)")
        self.assertEqual(key[0], 4)

    def test_body_component_is_lowercased_full_pattern(self):
        """
        Given a Bash pattern with uppercase characters
        When stable_rule_key() is called
        Then the body component of the key is the full pattern, lowercased
        """
        key = stable_rule_key("Bash(GIT STATUS:*)")
        self.assertEqual(key[1], "bash(git status:*)")

    def test_key_ordering_consistent_with_sort(self):
        """
        Given a list of mixed-tool patterns
        When sorted by stable_rule_key and by sort_patterns
        Then both produce the same stated canonical order -- asserted as a
             literal, so a wrong key cannot satisfy both sides by changing them
             together
        """
        patterns = [
            "Write(/tmp/out.txt)",
            "Bash(git:*)",
            "Edit(file.py)",
            "Read(/home/*)",
        ]
        expected = [
            "Bash(git:*)",
            "Read(/home/*)",
            "Write(/tmp/out.txt)",
            "Edit(file.py)",
        ]
        self.assertEqual(sorted(patterns, key=stable_rule_key), expected)
        self.assertEqual(sort_patterns(patterns), expected)
