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
        Then all Bash patterns appear before all Read patterns
        """
        patterns = ["Read(/tmp/*)", "Bash(git status:*)", "Read(/home/*)", "Bash(ls:*)"]
        result = sort_patterns(patterns)
        bash_indices = [i for i, p in enumerate(result) if p.startswith("Bash(")]
        read_indices = [i for i, p in enumerate(result) if p.startswith("Read(")]
        self.assertTrue(max(bash_indices) < min(read_indices))

    def test_tool_priority_order_bash_read_write_edit(self):
        """
        Given a list with Bash, Read, Write, and Edit patterns in reverse order
        When sort_patterns() is called
        Then the order is Bash, Read, Write, Edit
        """
        patterns = [
            "Edit(~/project/file.py)",
            "Write(/tmp/out.txt)",
            "Read(/home/user/*)",
            "Bash(git status:*)",
        ]
        result = sort_patterns(patterns)
        self.assertTrue(result[0].startswith("Bash("))
        self.assertTrue(result[1].startswith("Read("))
        self.assertTrue(result[2].startswith("Write("))
        self.assertTrue(result[3].startswith("Edit("))

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
        self.assertEqual(result[0], "Bash(cat:*)")
        self.assertEqual(result[1], "Bash(git status:*)")
        self.assertEqual(result[2], "Bash(ls:*)")
        self.assertEqual(result[3], "Bash(uv run pytest:*)")

    def test_empty_list_returns_empty(self):
        """
        Given an empty pattern list
        When sort_patterns() is called
        Then an empty list is returned
        """
        self.assertEqual(sort_patterns([]), [])

    def test_single_element_returns_unchanged(self):
        """
        Given a single-element pattern list
        When sort_patterns() is called
        Then the same single element is returned
        """
        self.assertEqual(sort_patterns(["Bash(git diff:*)"]), ["Bash(git diff:*)"])

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
        Given two patterns that normalise to the same key (same lowercase full pattern)
        When sort_patterns() is called
        Then they retain their relative order (stable sort)
        """
        patterns = ["Bash(Git Status:*)", "Bash(git status:*)", "Read(/tmp/*)"]
        result = sort_patterns(patterns)
        bash_in_result = [p for p in result if p.startswith("Bash(")]
        self.assertEqual(len(bash_in_result), 2)
        idx_upper = result.index("Bash(Git Status:*)")
        idx_lower = result.index("Bash(git status:*)")
        self.assertLess(idx_upper, idx_lower)

    def test_case_insensitive_sort_within_tool(self):
        """
        Given Bash patterns with mixed case
        When sort_patterns() is called
        Then sorting within the tool bucket is case-insensitive
        """
        patterns = ["Bash(Zsh:*)", "Bash(awk:*)", "Bash(Curl:*)"]
        result = sort_patterns(patterns)
        bodies_lower = [p.lower() for p in result]
        self.assertEqual(bodies_lower, sorted(bodies_lower))

    def test_unknown_tool_sorts_after_edit(self):
        """
        Given a pattern with an unrecognised tool name
        When sort_patterns() is called
        Then it sorts after Edit (priority 4 > Edit's 3)
        """
        patterns = ["Bash(git:*)", "UnknownTool(some:*)", "Edit(file.py)"]
        result = sort_patterns(patterns)
        self.assertTrue(result[0].startswith("Bash("))
        self.assertTrue(result[-1].startswith("UnknownTool("))

    def test_extended_syntax_prefix_sorts_within_tool_bucket(self):
        """
        Given Bash patterns including extended-syntax prefixed forms
        When sort_patterns() is called
        Then all Bash patterns sort in the Bash bucket, alphabetically by full pattern
        (the [regex] prefix is part of the sort key within the Bash bucket)
        """
        patterns = [
            "Bash([regex]^git\\b)",
            "Bash(uv run:*)",
            "Bash([glob]git/**)",
        ]
        result = sort_patterns(patterns)
        self.assertTrue(all(p.startswith("Bash(") for p in result))
        lowered = [p.lower() for p in result]
        self.assertEqual(lowered, sorted(lowered))


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
        Given allow, deny, and ask lists in arbitrary order
        When sort_layer_rules() is called
        Then all three lists are returned sorted in canonical tool-priority order
        """
        allow = ["Read(z/*)", "Bash(a:*)"]
        deny = ["Write(y.txt)", "Bash(b:*)"]
        ask = ["Edit(x.py)", "Bash(c:*)"]
        sa, sd, sask = sort_layer_rules(allow, deny, ask)
        self.assertTrue(sa[0].startswith("Bash("))
        self.assertTrue(sd[0].startswith("Bash("))
        self.assertTrue(sask[0].startswith("Bash("))

    def test_none_ask_returns_none(self):
        """
        Given None as the ask list
        When sort_layer_rules() is called
        Then the returned ask value is also None
        """
        sa, sd, sask = sort_layer_rules(
            ["Read(b/*)", "Bash(a:*)"], ["Write(d.txt)", "Bash(c:*)"], None
        )
        self.assertIsNone(sask)

    def test_original_lists_not_mutated(self):
        """
        Given allow and deny lists
        When sort_layer_rules() is called
        Then the original lists are not mutated
        """
        allow = ["Read(z/*)", "Bash(a:*)"]
        deny = ["Write(y.txt)", "Bash(b:*)"]
        allow_copy = list(allow)
        deny_copy = list(deny)
        sort_layer_rules(allow, deny)
        self.assertEqual(allow, allow_copy)
        self.assertEqual(deny, deny_copy)

    def test_empty_lists(self):
        """
        Given empty allow and deny lists
        When sort_layer_rules() is called
        Then empty lists are returned
        """
        sa, sd, sask = sort_layer_rules([], [], [])
        self.assertEqual(sa, [])
        self.assertEqual(sd, [])
        self.assertEqual(sask, [])


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
        When patterns are sorted using stable_rule_key as the key
        Then the order matches sort_patterns()
        """
        patterns = [
            "Write(/tmp/out.txt)",
            "Bash(git:*)",
            "Edit(file.py)",
            "Read(/home/*)",
        ]
        by_key = sorted(patterns, key=stable_rule_key)
        by_sort = sort_patterns(patterns)
        self.assertEqual(by_key, by_sort)
