"""
Unit tests for toolguard.tools.annotate (generated ``# toolguard:`` comments).

Covers annotation building from clarity findings and the idempotent, minimal-diff,
human-comment-preserving section writer.

All tests use stdlib unittest with BDD Given/When/Then docstrings.
"""

import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import List, Optional

from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.annotate import (
    TOOLGUARD_MARKER,
    _annotation_text,
    annotate_config_file,
    annotate_section_text,
    clarity_annotations,
)
from toolguard.tools.clarity import InteractionFinding


def _config(
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
) -> Configuration:
    """Build a single-layer Bash config with wrapped allow/deny/ask patterns."""
    content = MappingProxyType(
        {
            "permissions": {
                "allow": [f"Bash({p})" for p in (allow or [])],
                "deny": [f"Bash({p})" for p in (deny or [])],
                "ask": [f"Bash({p})" for p in (ask or [])],
            }
        }
    )
    prov = Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=0,
    )
    return Configuration(layers=(ConfigLayer(provenance=prov, content=content),), start_dir=None)


def _finding(kind: str, guard_section: str = "deny", explanation: str = "EXPL") -> InteractionFinding:
    """Build a minimal InteractionFinding for annotation-text tests."""
    prov = Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format="toml",
        path=Path("/fake/.claude/toolguard_hook.toml"),
        specificity=0,
    )
    return InteractionFinding(
        tool="Bash",
        provenance=prov,
        kind=kind,
        allow_pattern="git:*",
        guard_section=guard_section,
        guard_pattern="git push:*",
        explanation=explanation,
    )


class TestAnnotationText(unittest.TestCase):
    """_annotation_text renders a short per-kind note, one branch per finding kind."""

    def test_deny_shadows_allow_note(self):
        """
        Given a deny-shadows-allow finding
        When its annotation text is built
        Then it names the shadowing deny and that deny wins
        """
        note = _annotation_text(_finding("deny-shadows-allow"))
        self.assertIn("deny 'git push:*' shadows", note)
        self.assertIn("deny wins", note)

    def test_ask_overlaps_allow_note(self):
        """
        Given an ask-overlaps-allow finding
        When its annotation text is built
        Then it names the ask overlap and the more-specific-wins rule
        """
        note = _annotation_text(_finding("ask-overlaps-allow", guard_section="ask"))
        self.assertIn("ask 'git push:*' overlaps", note)
        self.assertIn("more-specific rule wins", note)

    def test_multi_section_interaction_note(self):
        """
        Given a multi-section-interaction finding
        When its annotation text is built
        Then it flags the extra governing section and the non-obvious verdict
        """
        note = _annotation_text(_finding("multi-section-interaction", guard_section="deny+ask"))
        self.assertIn("also governed by deny+ask", note)
        self.assertIn("non-obvious", note)

    def test_cross_layer_dependent_note(self):
        """
        Given a cross-layer-dependent finding
        When its annotation text is built
        Then it flags the cross-layer interaction and that the verdict spans files
        """
        note = _annotation_text(_finding("cross-layer-dependent"))
        self.assertIn("interacts with deny 'git push:*' in another layer", note)
        self.assertIn("verdict spans files", note)

    def test_unknown_kind_falls_back_to_full_explanation(self):
        """
        Given a finding of an unrecognized kind
        When its annotation text is built
        Then it falls back to the finding's full explanation
        """
        note = _annotation_text(_finding("some-future-kind", explanation="FULL DETAIL"))
        self.assertEqual(note, "FULL DETAIL")


_SECTION = (
    "[permissions]\n"
    "allow = [\n"
    "    # human note: keep me\n"
    "    'Bash(git:*)',\n"
    "    'Bash(ls:*)',\n"
    "]\n"
    "deny = [\n"
    "    'Bash(git push:*)',\n"
    "]\n"
    "ask = []\n"
)


_FAKE_PATH = Path("/fake/.claude/toolguard_hook.toml")


class TestClarityAnnotations(unittest.TestCase):
    """Annotations are grouped per file, then per full rule pattern."""

    def test_confusing_allow_gets_a_note_keyed_by_file_and_full_pattern(self):
        """
        Given a config where allow 'git:*' is shadowed by deny 'git push:*'
        When clarity_annotations is built for Bash
        Then the rule's file maps 'Bash(git:*)' to at least one note
        """
        annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"]), "Bash"
        )
        self.assertIn(_FAKE_PATH, annotations)
        self.assertIn("Bash(git:*)", annotations[_FAKE_PATH])
        self.assertTrue(annotations[_FAKE_PATH]["Bash(git:*)"])

    def test_multiple_interactions_yield_multiple_deduped_notes(self):
        """
        Given an allow 'git:*' overlapping both a deny and an ask
        When clarity_annotations is built
        Then the rule carries more than one distinct note (sorted, de-duplicated)
        """
        annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"], ask=["git commit:*"]),
            "Bash",
        )
        notes = annotations[_FAKE_PATH]["Bash(git:*)"]
        self.assertGreater(len(notes), 1)
        self.assertEqual(notes, sorted(set(notes)))


class TestAnnotateSectionText(unittest.TestCase):
    """The section writer is idempotent, minimal-diff, and human-safe."""

    _ANN = {"Bash(git:*)": ["deny 'git push:*' shadows part of this allow (deny wins)"]}

    def test_note_inserted_above_rule_at_its_indent(self):
        """
        Given a section and an annotation for 'Bash(git:*)'
        When annotate_section_text runs
        Then a '# toolguard:' line appears immediately above the rule, indented
        """
        out = annotate_section_text(_SECTION, self._ANN)
        lines = out.split("\n")
        idx = next(i for i, ln in enumerate(lines) if "'Bash(git:*)'" in ln)
        self.assertTrue(lines[idx - 1].strip().startswith(TOOLGUARD_MARKER))
        self.assertTrue(lines[idx - 1].startswith("    "))

    def test_idempotent(self):
        """
        Given an already-annotated section
        When annotate_section_text runs again with the same annotations
        Then the result is unchanged (no accreted duplicate comments)
        """
        once = annotate_section_text(_SECTION, self._ANN)
        twice = annotate_section_text(once, self._ANN)
        self.assertEqual(once, twice)
        self.assertEqual(once.count(TOOLGUARD_MARKER), 1)

    def test_preserves_human_comments_and_untouched_sections(self):
        """
        Given a section with a human comment and an empty ask list
        When annotate_section_text runs
        Then the human comment, the deny rule, and 'ask = []' are all preserved
        """
        out = annotate_section_text(_SECTION, self._ANN)
        self.assertIn("# human note: keep me", out)
        self.assertIn("'Bash(git push:*)'", out)
        self.assertIn("ask = []", out)

    def test_stale_generated_comment_removed_when_no_longer_annotated(self):
        """
        Given a previously-annotated section
        When annotate_section_text runs with NO annotations (rule no longer confusing)
        Then the generated line is removed but the human comment remains
        """
        once = annotate_section_text(_SECTION, self._ANN)
        cleared = annotate_section_text(once, {})
        self.assertNotIn(TOOLGUARD_MARKER, cleared)
        self.assertIn("# human note: keep me", cleared)

    def test_multiple_notes_become_multiple_marked_lines(self):
        """
        Given two notes for one rule
        When annotate_section_text runs
        Then two '# toolguard:' lines are written above that rule
        """
        ann = {"Bash(git:*)": ["note one", "note two"]}
        out = annotate_section_text(_SECTION, ann)
        self.assertEqual(out.count(TOOLGUARD_MARKER), 2)


class TestAnnotateConfigFile(unittest.TestCase):
    """File-level annotation splices only the permissions section."""

    def test_returns_before_and_after_and_splices_section(self):
        """
        Given a real config file with a confusing rule
        When annotate_config_file computes annotations
        Then it returns (old, new) where new adds the generated comment and keeps
            everything outside the permissions section
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text("[meta]\nname = 'x'\n\n" + _SECTION, encoding="utf-8")
            ann = {"Bash(git:*)": ["deny wins"]}
            old, new = annotate_config_file(path, ann)
            self.assertNotEqual(old, new)
            self.assertIn(TOOLGUARD_MARKER, new)
            self.assertIn("[meta]", new)  # content outside the section is preserved

    def test_no_permissions_section_is_a_noop(self):
        """
        Given a config file with no [permissions] section
        When annotate_config_file runs
        Then old and new text are identical
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text("[meta]\nname = 'x'\n", encoding="utf-8")
            old, new = annotate_config_file(path, {"Bash(git:*)": ["x"]})
            self.assertEqual(old, new)


if __name__ == "__main__":
    unittest.main()
