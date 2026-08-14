"""
Unit tests for toolguard.tools.annotate (generated ``# toolguard:`` comments):
annotation building from clarity findings, and the section writer.

The section writer's output is a TOML file, so most of the writer tests parse the
result back with ``tomllib`` and re-decide against it rather than asserting on the
emitted string alone -- a note is free text landing inside a permission array, and
the only question that matters is whether the file still parses and still decides
the same way.
"""

import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import MappingProxyType
from typing import Dict, List, Optional, Tuple

from toolguard.api import decide
from toolguard.config import ConfigLayer, Configuration, Provenance
from toolguard.tools.annotate import (
    TOOLGUARD_MARKER,
    _annotation_text,
    annotate_config_file,
    annotate_section_text,
    clarity_annotations,
)
from toolguard.tools.clarity import InteractionFinding, find_confusing_interactions

_FAKE_PATH = Path("/fake/.claude/toolguard_hook.toml")


def _provenance(file_format: str = "toml") -> Provenance:
    """Provenance for the single fake layer every fixture in this module uses."""
    return Provenance(
        level="project",
        source_type="toolguard_hook",
        file_format=file_format,
        path=_FAKE_PATH,
        specificity=0,
    )


def _config(
    allow: Optional[List[str]] = None,
    deny: Optional[List[str]] = None,
    ask: Optional[List[str]] = None,
    file_format: str = "toml",
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
    return Configuration(
        layers=(ConfigLayer(provenance=_provenance(file_format), content=content),),
        start_dir=None,
    )


def _finding(
    kind: str,
    guard_section: str = "deny",
    explanation: str = "EXPL",
    allow_pattern: str = "git:*",
    guard_pattern: str = "svn commit:*",
) -> InteractionFinding:
    """
    Build a minimal InteractionFinding for annotation-text tests.

    The default allow and guard patterns share no substring, so an assertion that a
    note names one of them cannot be satisfied by the other.
    """
    return InteractionFinding(
        tool="Bash",
        provenance=_provenance(),
        kind=kind,
        allow_pattern=allow_pattern,
        guard_section=guard_section,
        guard_pattern=guard_pattern,
        explanation=explanation,
    )


_KINDS = (
    ("deny-shadows-allow", "deny"),
    ("ask-overlaps-allow", "ask"),
    ("multi-section-interaction", "deny+ask"),
    ("cross-layer-dependent", "deny"),
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
        self.assertIn("deny 'svn commit:*' shadows", note)
        self.assertIn("deny wins", note)

    def test_ask_overlaps_allow_note(self):
        """
        Given an ask-overlaps-allow finding
        When its annotation text is built
        Then it names the ask overlap and the more-specific-wins rule
        """
        note = _annotation_text(_finding("ask-overlaps-allow", guard_section="ask"))
        self.assertIn("ask 'svn commit:*' overlaps", note)
        self.assertIn("more-specific rule wins", note)

    def test_multi_section_interaction_note(self):
        """
        Given a multi-section-interaction finding
        When its annotation text is built
        Then it flags the extra governing section and the non-obvious verdict
        """
        note = _annotation_text(
            _finding("multi-section-interaction", guard_section="deny+ask")
        )
        self.assertIn("also governed by deny+ask", note)
        self.assertIn("non-obvious", note)

    def test_cross_layer_dependent_note(self):
        """
        Given a cross-layer-dependent finding
        When its annotation text is built
        Then it flags the cross-layer interaction and that the verdict spans files
        """
        note = _annotation_text(_finding("cross-layer-dependent"))
        self.assertIn("interacts with deny 'svn commit:*' in another layer", note)
        self.assertIn("verdict spans files", note)

    def test_unknown_kind_falls_back_to_full_explanation(self):
        """
        Given a finding of an unrecognized kind
        When its annotation text is built
        Then it falls back to the finding's full explanation
        """
        note = _annotation_text(_finding("some-future-kind", explanation="FULL DETAIL"))
        self.assertEqual(note, "FULL DETAIL")

    def test_every_kind_names_the_guard_and_not_the_allow(self):
        """
        Given one finding of each recognized kind, with allow and guard patterns
            sharing no substring
        When each annotation text is built
        Then every note names the GUARD pattern and none names the allow pattern
        """
        for kind, section in _KINDS:
            with self.subTest(kind=kind):
                note = _annotation_text(_finding(kind, guard_section=section))
                self.assertIn("svn commit:*", note)
                self.assertNotIn("git:*", note)

    def test_the_four_kinds_render_four_distinct_notes(self):
        """
        Given one finding of each recognized kind
        When their annotation texts are built
        Then all four differ from one another and from the fallback explanation
        """
        notes = [
            _annotation_text(_finding(kind, guard_section=section))
            for kind, section in _KINDS
        ]
        self.assertEqual(len(set(notes)), len(_KINDS))
        self.assertNotIn("EXPL", notes)

    def test_no_recognized_kind_renders_a_multi_line_note(self):
        """
        Given one finding of each recognized kind
        When their annotation texts are built
        Then none contains a line break -- a note is emitted as a single TOML
            comment line, so a break in it would end the comment mid-array
        """
        for kind, section in _KINDS:
            with self.subTest(kind=kind):
                note = _annotation_text(_finding(kind, guard_section=section))
                self.assertNotIn("\n", note)
                self.assertNotIn("\r", note)


class TestClarityAnnotations(unittest.TestCase):
    """Annotations are grouped per file, then per full rule pattern."""

    def test_confusing_allow_gets_a_note_keyed_by_file_and_full_pattern(self):
        """
        Given a config where allow 'git:*' is shadowed by deny 'git push:*'
        When clarity_annotations is built for Bash
        Then the rule's file maps 'Bash(git:*)' -- and only that pattern -- to a
            note naming the shadowing deny
        """
        annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"]), "Bash"
        )
        self.assertEqual(list(annotations), [_FAKE_PATH])
        self.assertEqual(list(annotations[_FAKE_PATH]), ["Bash(git:*)"])
        notes = annotations[_FAKE_PATH]["Bash(git:*)"]
        self.assertEqual(len(notes), 1)
        self.assertIn("deny 'git push:*' shadows", notes[0])

    def test_multiple_interactions_yield_multiple_deduped_notes(self):
        """
        Given an allow 'git:*' overlapping both a deny and an ask
        When clarity_annotations is built
        Then the rule carries exactly the three expected notes, sorted and distinct
        """
        annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"], ask=["git commit:*"]),
            "Bash",
        )
        notes = annotations[_FAKE_PATH]["Bash(git:*)"]
        self.assertEqual(len(notes), 3)
        self.assertEqual(notes, sorted(set(notes)))
        self.assertEqual([n.split(" ", 1)[0] for n in notes], ["also", "ask", "deny"])

    def test_a_repeated_deny_yields_one_note_not_two(self):
        """
        Given a config whose deny list repeats the same shadowing pattern, so
            clarity reports two identical findings
        When clarity_annotations is built
        Then the duplicate note is collapsed to a single entry
        """
        config = _config(allow=["git:*"], deny=["git push:*", "git push:*"])
        self.assertEqual(len(find_confusing_interactions(config, "Bash")), 2)
        notes = clarity_annotations(config, "Bash")[_FAKE_PATH]["Bash(git:*)"]
        self.assertEqual(len(notes), 1)

    def test_a_non_toml_layer_contributes_no_annotations(self):
        """
        Given the same confusing rule pair in a toml layer and in a json layer
        When clarity_annotations is built for each
        Then the toml layer yields a note and the json layer yields nothing --
            native json settings have nowhere to put a comment
        """
        toml_annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"], file_format="toml"), "Bash"
        )
        json_annotations = clarity_annotations(
            _config(allow=["git:*"], deny=["git push:*"], file_format="json"), "Bash"
        )
        self.assertEqual(list(toml_annotations[_FAKE_PATH]), ["Bash(git:*)"])
        self.assertEqual(json_annotations, {})


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

_NOTE = "deny 'git push:*' shadows part of this allow (deny wins)"


def _permission_lists(section_text: str) -> Dict[str, List[str]]:
    """Parse a section with tomllib and return its allow/deny/ask lists."""
    return tomllib.loads(section_text)["permissions"]


def _config_from_section(section_text: str) -> Configuration:
    """Build a Configuration from a section's own TOML text, as a reader would see it."""
    return Configuration(
        layers=(
            ConfigLayer(
                provenance=_provenance(),
                content=MappingProxyType(tomllib.loads(section_text)),
            ),
        ),
        start_dir=None,
    )


def _verdicts(section_text: str) -> List[Tuple[str, str, Optional[str]]]:
    """
    (command, decision, matched_rule) for commands the fixture decides by a real
    rule match -- matched_rule is asserted alongside the decision so a fail-closed
    or fallback verdict cannot masquerade as a rule match.
    """
    config = _config_from_section(section_text)
    out = []
    for command in ("git status", "git push origin main", "ls -l", "cat /etc/hosts"):
        verdict = decide(config, "Bash", command)
        out.append((command, verdict.decision, verdict.matched_rule))
    return out


def _marker_lines(text: str) -> List[str]:
    """Every generated comment line in *text*, in order, stripped of indentation."""
    return [
        ln.strip() for ln in text.split("\n") if ln.strip().startswith(TOOLGUARD_MARKER)
    ]


def _index_of_line_containing(text: str, needle: str) -> int:
    """Index of the single line containing *needle*; fails the test if not exactly one."""
    hits = [i for i, ln in enumerate(text.split("\n")) if needle in ln]
    if len(hits) != 1:
        raise AssertionError(
            f"expected exactly one line containing {needle!r}, got {hits}"
        )
    return hits[0]


class TestAnnotateSectionText(unittest.TestCase):
    """The section writer is idempotent and minimal-diff."""

    _ANN = {"Bash(git:*)": [_NOTE]}

    def test_note_inserted_above_rule_at_its_indent(self):
        """
        Given a section and an annotation for 'Bash(git:*)'
        When annotate_section_text runs
        Then a '# toolguard:' line carrying that note's exact text appears
            immediately above the rule, at the rule's own indentation
        """
        out = annotate_section_text(_SECTION, self._ANN)
        lines = out.split("\n")
        idx = _index_of_line_containing(out, "'Bash(git:*)'")
        self.assertEqual(lines[idx - 1], f"    {TOOLGUARD_MARKER} {_NOTE}")

    def test_the_note_text_is_written_verbatim(self):
        """
        Given an annotation whose text shares nothing with the rule it describes
        When annotate_section_text runs
        Then the emitted comment line carries that text exactly, so the note's
            content -- not merely the marker -- reaches the file
        """
        out = annotate_section_text(_SECTION, {"Bash(git:*)": ["ZEBRA QUARTZ 42"]})
        self.assertEqual(_marker_lines(out), [f"{TOOLGUARD_MARKER} ZEBRA QUARTZ 42"])

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

    def test_a_changed_note_replaces_the_previous_one(self):
        """
        Given a section already annotated with one note
        When annotate_section_text runs with a DIFFERENT note for the same rule
        Then the new note is the only generated line, and the result equals
            annotating the unannotated section with the new note
        """
        once = annotate_section_text(_SECTION, {"Bash(git:*)": ["FIRST NOTE"]})
        twice = annotate_section_text(once, {"Bash(git:*)": ["SECOND NOTE"]})
        self.assertEqual(_marker_lines(twice), [f"{TOOLGUARD_MARKER} SECOND NOTE"])
        self.assertEqual(
            twice, annotate_section_text(_SECTION, {"Bash(git:*)": ["SECOND NOTE"]})
        )

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

    def test_a_hand_written_toolguard_comment_is_dropped(self):
        """
        Given a section carrying a hand-written line that starts with the
            '# toolguard:' prefix
        When annotate_section_text runs with no annotations
        Then that line is dropped -- the prefix is the mechanism, so a human
            cannot reserve it -- while an ordinary comment on the same rule stays
        """
        section = (
            "[permissions]\n"
            "allow = [\n"
            "    # human note: keep me\n"
            f"    {TOOLGUARD_MARKER} I WROTE THIS BY HAND\n"
            "    'Bash(git:*)',\n"
            "]\n"
        )
        out = annotate_section_text(section, {})
        self.assertNotIn("I WROTE THIS BY HAND", out)
        self.assertIn("# human note: keep me", out)

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
        Then both notes are written, in the given order, above that rule
        """
        ann = {"Bash(git:*)": ["note one", "note two"]}
        out = annotate_section_text(_SECTION, ann)
        self.assertEqual(
            _marker_lines(out),
            [f"{TOOLGUARD_MARKER} note one", f"{TOOLGUARD_MARKER} note two"],
        )
        idx = _index_of_line_containing(out, "'Bash(git:*)'")
        self.assertEqual(out.split("\n")[idx - 1], f"    {TOOLGUARD_MARKER} note two")

    def test_a_pattern_absent_from_the_section_writes_nothing(self):
        """
        Given an annotation keyed by a pattern that is not in the section, and the
            same section with an annotation that IS in it
        When annotate_section_text runs on each
        Then the absent key changes nothing while the present key does -- so the
            "nothing happened" result is attributable to the missing rule and not
            to a writer that never writes
        """
        absent = annotate_section_text(_SECTION, {"Bash(svn commit:*)": ["X"]})
        present = annotate_section_text(_SECTION, {"Bash(ls:*)": ["X"]})
        self.assertEqual(absent, _SECTION)
        self.assertNotEqual(present, _SECTION)
        self.assertEqual(_marker_lines(present), [f"{TOOLGUARD_MARKER} X"])

    def test_an_empty_note_list_writes_no_marker_line(self):
        """
        Given a rule that IS in the section but whose note list is empty
        When annotate_section_text runs
        Then nothing is written for it, while the same rule with one note is
            annotated -- an empty list is distinguishable from a missing key only
            by the positive control, so both are asserted here
        """
        empty = annotate_section_text(_SECTION, {"Bash(ls:*)": []})
        self.assertEqual(empty, _SECTION)
        self.assertEqual(
            _marker_lines(annotate_section_text(_SECTION, {"Bash(ls:*)": ["X"]})),
            [f"{TOOLGUARD_MARKER} X"],
        )

    def test_annotation_leaves_the_permission_lists_and_every_verdict_unchanged(self):
        """
        Given an annotated section
        When it is parsed back with tomllib and re-decided
        Then the allow/deny/ask lists are identical to the unannotated section's
            and every command decides the same way, by the same matched_rule
        """
        out = annotate_section_text(_SECTION, self._ANN)
        self.assertEqual(_permission_lists(out), _permission_lists(_SECTION))
        self.assertEqual(_verdicts(out), _verdicts(_SECTION))
        self.assertEqual(
            _verdicts(_SECTION),
            [
                ("git status", "allow", "git:*"),
                ("git push origin main", "deny", "git push:*"),
                ("ls -l", "allow", "ls:*"),
                ("cat /etc/hosts", "ask", None),
            ],
        )


_HOSTILE_NOTES = {
    "double_quote": 'a " double quote',
    "single_quote": "an ' apostrophe",
    "backslash": "a \\ backslash and a literal \\n",
    "triple_quote": 'a """ triple quote',
    "non_ascii": "naive é, 中文, \U0001f600",
    "array_syntax": "a ] bracket, a , comma and a 'Bash(rm -rf /)' lookalike",
    "hash": "a # hash",
    "tab": "a \t tab",
    "equals": "key = value = [1]",
}


class TestHostileCharactersInANote(unittest.TestCase):
    """
    A note is free text written into a TOML permission array, so it is an escaping
    surface: the questions are whether the file still parses, whether the rules
    still mean the same thing, and whether the note itself survives.
    """

    def test_hostile_notes_keep_the_section_parseable_and_survive_verbatim(self):
        """
        Given a note containing quotes, backslashes, a triple quote, non-ASCII
            characters, TOML array syntax, a hash and a tab
        When the section is annotated and parsed back with tomllib
        Then it parses, the permission lists are byte-identical to the
            unannotated section's, and the note is present verbatim as one
            generated comment line
        """
        for name, note in _HOSTILE_NOTES.items():
            with self.subTest(note=name):
                out = annotate_section_text(_SECTION, {"Bash(git:*)": [note]})
                self.assertEqual(_permission_lists(out), _permission_lists(_SECTION))
                self.assertEqual(_marker_lines(out), [f"{TOOLGUARD_MARKER} {note}"])

    def test_hostile_notes_cannot_change_what_a_rule_means(self):
        """
        Given each hostile note in turn
        When the annotated section is parsed back and re-decided
        Then every command keeps its decision AND its matched_rule -- a note that
            terminated the array early would change one of them
        """
        baseline = _verdicts(_SECTION)
        for name, note in _HOSTILE_NOTES.items():
            with self.subTest(note=name):
                out = annotate_section_text(_SECTION, {"Bash(git:*)": [note]})
                self.assertEqual(_verdicts(out), baseline)

    def test_a_hostile_note_survives_a_real_file_write_and_reread(self):
        """
        Given a config file on disk holding a [meta] section and a [permissions]
            section
        When annotate_config_file's new text is written and read back
        Then the whole file parses, [meta] is intact, and the note is present
        """
        note = _HOSTILE_NOTES["array_syntax"]
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text("[meta]\nname = 'x'\n\n" + _SECTION, encoding="utf-8")
            _old, new = annotate_config_file(path, {"Bash(git:*)": [note]})
            path.write_text(new, encoding="utf-8")
            reread = path.read_text(encoding="utf-8")
            parsed = tomllib.loads(reread)
        self.assertEqual(parsed["meta"], {"name": "x"})
        self.assertEqual(parsed["permissions"], _permission_lists(_SECTION))
        self.assertEqual(_marker_lines(reread), [f"{TOOLGUARD_MARKER} {note}"])

    def test_a_newline_in_a_note_keeps_the_section_parseable(self):
        """
        Given a note containing a line break
        When the section is annotated
        Then the section still parses and the note is emitted as ONE comment line
            with the break normalised to a single space

        RED: a break currently ends the comment mid-array and the section no
        longer parses.  This is proposed ticket 24's defect on a different
        surface -- the comment renderer, not _escape_toml_string -- so the fix
        Arnon decided there (normalise a newline to a space) does not reach it:
        a note is generated prose and never passes through normalize_entry.
        """
        out = annotate_section_text(_SECTION, {"Bash(git:*)": ["one\ntwo"]})
        try:
            parsed = _permission_lists(out)
        except tomllib.TOMLDecodeError as exc:
            self.fail(f"the annotated section no longer parses as TOML: {exc}")
        self.assertEqual(parsed, _permission_lists(_SECTION))
        self.assertEqual(_marker_lines(out), [f"{TOOLGUARD_MARKER} one two"])


_STRUCTURED_ENTRY_SECTION = (
    "[permissions]\n"
    "allow = [\n"
    '    { match = "Bash(git status)", additionalContext = "read-only" },\n'
    "    'Bash(ls:*)',\n"
    "]\n"
    "deny = [\n"
    "    'Bash(git push:*)',\n"
    "]\n"
    "ask = []\n"
)


class TestAnnotateSectionTextStructuredEntry(unittest.TestCase):
    """
    A single-line structured ({ match = ..., ... }) entry is annotated like any other
    rule. Single-line only: a multi-line one is not valid TOML, and
    parse_permissions_section_with_comments rejects it.
    """

    _ANN = {"Bash(git status)": [_NOTE]}

    def test_structured_entry_gets_exactly_one_note_above_its_line(self):
        """
        Given a single-line structured allow entry with an annotation for its
        pattern
        When annotate_section_text runs
        Then exactly one '# toolguard:' line carrying that note is inserted,
        immediately above the entry's own line, at its indentation
        """
        out = annotate_section_text(_STRUCTURED_ENTRY_SECTION, self._ANN)
        idx = _index_of_line_containing(out, 'match = "Bash(git status)"')
        self.assertEqual(out.split("\n")[idx - 1], f"    {TOOLGUARD_MARKER} {_NOTE}")
        self.assertEqual(_marker_lines(out), [f"{TOOLGUARD_MARKER} {_NOTE}"])

    def test_structured_entry_annotation_is_idempotent(self):
        """
        Given an already-annotated single-line structured entry
        When annotate_section_text runs again with the same annotations
        Then the result is unchanged (no accreted duplicate comments)
        """
        once = annotate_section_text(_STRUCTURED_ENTRY_SECTION, self._ANN)
        twice = annotate_section_text(once, self._ANN)
        self.assertEqual(once, twice)
        self.assertEqual(once.count(TOOLGUARD_MARKER), 1)

    def test_structured_entry_preserves_its_own_source_line_verbatim(self):
        """
        Given a single-line structured allow entry
        When annotate_section_text runs
        Then the entry's own line is preserved verbatim and its additionalContext
            still parses back unchanged
        """
        out = annotate_section_text(_STRUCTURED_ENTRY_SECTION, self._ANN)
        self.assertIn(
            '    { match = "Bash(git status)", additionalContext = "read-only" },',
            out,
        )
        self.assertEqual(
            _permission_lists(out)["allow"][0],
            {"match": "Bash(git status)", "additionalContext": "read-only"},
        )


class TestAnnotationIsAttachedToTheNamedRule(unittest.TestCase):
    """Which line a note lands above, when more than one line could claim it."""

    def test_only_the_named_rule_is_annotated_among_several(self):
        """
        Given a section with three distinct allow rules and a note for the middle one
        When annotate_section_text runs
        Then exactly one generated line is written, and it sits directly above the
            named rule -- not above either sibling
        """
        section = (
            "[permissions]\n"
            "allow = [\n"
            "    'Bash(git:*)',\n"
            "    'Bash(ls:*)',\n"
            "    'Bash(cat:*)',\n"
            "]\n"
        )
        out = annotate_section_text(section, {"Bash(ls:*)": ["MIDDLE"]})
        lines = out.split("\n")
        self.assertEqual(_marker_lines(out), [f"{TOOLGUARD_MARKER} MIDDLE"])
        self.assertEqual(
            lines[_index_of_line_containing(out, "'Bash(ls:*)'") - 1],
            f"    {TOOLGUARD_MARKER} MIDDLE",
        )
        for other in ("'Bash(git:*)'", "'Bash(cat:*)'"):
            self.assertNotIn(
                TOOLGUARD_MARKER, lines[_index_of_line_containing(out, other) - 1]
            )

    def test_an_allow_note_is_not_attached_to_an_identically_spelled_deny(self):
        """
        Given a config where the SAME pattern appears in both allow and deny -- an
            overlap clarity itself reports as deny-shadows-allow
        When the file's clarity annotations are applied to its section
        Then only the allow rule is annotated

        RED: _rule_first_line_patterns keys one dict by source line across allow,
        deny and ask, so the allow's note is also inserted above the identical
        deny line, where it reads as a claim about the deny itself.  Follow-up
        queue entry AE1.
        """
        config = _config(allow=["git:*"], deny=["git:*"])
        annotations = clarity_annotations(config, "Bash")[_FAKE_PATH]
        section = (
            "[permissions]\n"
            "allow = [\n"
            "    'Bash(git:*)',\n"
            "]\n"
            "deny = [\n"
            "    'Bash(git:*)',\n"
            "]\n"
            "ask = []\n"
        )
        out = annotate_section_text(section, annotations)
        lines = out.split("\n")
        deny_header = _index_of_line_containing(out, "deny = [")
        self.assertEqual(len(_marker_lines(out)), 1)
        self.assertFalse(
            lines[deny_header + 1].strip().startswith(TOOLGUARD_MARKER),
            f"a generated note was inserted inside the deny list: {lines[deny_header + 1]!r}",
        )


def _tree_snapshot(root: Path) -> Dict[str, Tuple[int, int]]:
    """Path -> (size, mtime_ns) for every file under *root*; a rewrite is visible."""
    snapshot = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            stat = path.stat()
            snapshot[str(path)] = (stat.st_size, stat.st_mtime_ns)
    return snapshot


class TestAnnotateConfigFile(unittest.TestCase):
    """File-level annotation splices only the permissions section."""

    _FILE = "[meta]\nname = 'x'\n\n" + _SECTION + "\n[hard_deny]\npatterns = ['rm:*']\n"

    def test_returns_before_and_after_and_splices_only_the_permissions_section(self):
        """
        Given a config file whose [permissions] section has a section before it and
            a section after it
        When annotate_config_file computes annotations
        Then it returns (old, new) where new inserts exactly the generated comment
            and leaves every byte outside the permissions section untouched
        """
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(self._FILE, encoding="utf-8")
            old, new = annotate_config_file(path, {"Bash(git:*)": [_NOTE]})

        self.assertEqual(old, self._FILE)
        self.assertNotEqual(old, new)
        self.assertEqual(_marker_lines(new), [f"{TOOLGUARD_MARKER} {_NOTE}"])
        self.assertEqual(
            [
                ln
                for ln in new.split("\n")
                if not ln.strip().startswith(TOOLGUARD_MARKER)
            ],
            old.split("\n"),
        )
        parsed = tomllib.loads(new)
        self.assertEqual(parsed["meta"], {"name": "x"})
        self.assertEqual(parsed["hard_deny"], {"patterns": ["rm:*"]})
        self.assertEqual(parsed["permissions"], _permission_lists(_SECTION))

    def test_no_permissions_section_is_a_noop(self):
        """
        Given a config file with no [permissions] section but holding the annotated
            rule's text in another section
        When annotate_config_file runs
        Then old and new text are identical, while the same annotation applied to a
            file that DOES have the section changes it -- so the no-op is
            attributable to the missing section
        """
        without = "[meta]\nname = 'x'\nnote = \"Bash(git:*)\"\n"
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "toolguard_hook.toml"
            path.write_text(without, encoding="utf-8")
            old, new = annotate_config_file(path, {"Bash(git:*)": ["x"]})

            with_section = Path(d) / "other.toml"
            with_section.write_text(without + "\n" + _SECTION, encoding="utf-8")
            control_old, control_new = annotate_config_file(
                with_section, {"Bash(git:*)": ["x"]}
            )
        self.assertEqual(old, new)
        self.assertNotEqual(control_old, control_new)

    def test_annotate_config_file_writes_nothing_to_disk(self):
        """
        Given a config file that annotate_config_file will change
        When it runs
        Then the file's content, size and mtime are unchanged and no file is added
            or removed -- computing the new text is not applying it
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            path = root / "toolguard_hook.toml"
            path.write_text(self._FILE, encoding="utf-8")
            os.utime(path, ns=(0, 0))
            before = _tree_snapshot(root)

            old, new = annotate_config_file(path, {"Bash(git:*)": [_NOTE]})

            after = _tree_snapshot(root)
            content = path.read_text(encoding="utf-8")

        self.assertNotEqual(old, new)
        self.assertEqual(before, after)
        self.assertEqual(content, self._FILE)


if __name__ == "__main__":
    unittest.main()
