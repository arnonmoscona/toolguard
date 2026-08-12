"""Tests for ``tools/change_role_classifier.py``; see that module's docstring for role
definitions."""

import ast
import contextlib
import io
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools import change_role_classifier as crc


def _analyze(
    source: str, subjects: list[str], is_test: bool = False
) -> crc.FileAnalysis:
    return crc.analyze_source(
        source, "synthetic.py", subjects, allowed_lines=None, is_test=is_test
    )


def _at(analysis: crc.FileAnalysis, source: str, needle: str) -> list[crc.Occurrence]:
    """Occurrences whose source line contains *needle* (a readable anchor instead of a
    hardcoded line number)."""
    target_lines = {
        i + 1 for i, line in enumerate(source.splitlines()) if needle in line
    }
    return [o for o in analysis.occurrences if o.line in target_lines]


class TestExactIdentifierMatching(unittest.TestCase):
    """Resolves by AST node identity, never by name substring."""

    def test_substring_near_miss_produces_no_occurrences(self):
        """
        Given a subject "mode" and code that only ever uses "auto_mode" and "mode_string"
        When the source is analyzed for subject "mode"
        Then zero occurrences are reported -- neither name is the exact identifier "mode"
        """
        source = (
            "auto_mode = True\n"
            "if auto_mode:\n"
            "    pass\n"
            "mode_string = 'x'\n"
            "print(mode_string)\n"
        )
        analysis = _analyze(source, ["mode"])
        self.assertEqual(analysis.occurrences, [])

    def test_exact_identifier_is_still_found_alongside_near_misses(self):
        """
        Given "mode", "auto_mode" and "mode_string" all present in the same file
        When analyzed for subject "mode"
        Then only the exact "mode" identifier is reported, not the other two
        """
        source = (
            "auto_mode = True\n"
            "mode_string = 'x'\n"
            "mode = auto_mode\n"
            "print(mode_string)\n"
        )
        analysis = _analyze(source, ["mode"])
        self.assertEqual(len(analysis.occurrences), 1)
        self.assertEqual(analysis.occurrences[0].line, 3)


class TestShadowedLocal(unittest.TestCase):
    """Hazard: a same-named local in an unrelated scope must be classified independently."""

    def test_two_unrelated_scopes_classified_independently(self):
        """
        Given two unrelated functions that both happen to use a local named "mode"
        When analyzed for subject "mode"
        Then each occurrence is classified by its OWN local context, not the other scope's
        """
        source = (
            "def uses_flag(mode):\n"
            "    if mode:\n"
            "        return 'auto'\n"
            "    return 'manual'\n"
            "\n"
            "def unrelated_helper():\n"
            "    mode = 'readonly'\n"
            "    return mode.upper()\n"
        )
        analysis = _analyze(source, ["mode"])
        decision_hits = _at(analysis, source, "if mode:")
        self.assertTrue(any(crc.ROLE_DECISION in o.roles for o in decision_hits))
        write_hits = _at(analysis, source, "mode = 'readonly'")
        self.assertTrue(any(crc.ROLE_WRITE in o.roles for o in write_hits))
        conduit_hits = _at(analysis, source, "mode.upper()")
        self.assertTrue(any(crc.ROLE_CONDUIT in o.roles for o in conduit_hits))
        self.assertNotIn(crc.ROLE_DECISION, write_hits[0].roles)

    def test_alias_hop_does_not_leak_across_scopes(self):
        """
        Given one function where a local "tmp" IS an alias of the subject, and a second,
        unrelated function that also has a local "tmp" bound to an unrelated literal
        When analyzed for the subject
        Then only the first function's "tmp" produces an aliased occurrence of the subject
        """
        source = (
            "def check(mode):\n"
            "    tmp = mode\n"
            "    if tmp:\n"
            "        return True\n"
            "    return False\n"
            "\n"
            "def unrelated():\n"
            "    tmp = 'readonly'\n"
            "    if tmp == 'readonly':\n"
            "        return True\n"
            "    return False\n"
        )
        analysis = _analyze(source, ["mode"])
        aliased = [o for o in analysis.occurrences if o.via_alias]
        self.assertEqual(len(aliased), 1)
        self.assertEqual(aliased[0].line, 3)
        self.assertIn(crc.ROLE_DECISION, aliased[0].roles)


class TestSetLiteralIsTransparent(unittest.TestCase):
    """Regression: `ast.Set` has no `.ctx` field, so a set-literal element used to fall through
    to UNCLASSIFIED (found on `rule_entry.py`'s `KNOWN_ENRICHMENT_KEYS` frozenset)."""

    def test_subject_inside_set_literal_walks_up_past_it(self):
        """
        Given the subject as an element of a set literal that is itself passed to a function
        When analyzed
        Then the occurrence is classified via whatever governs the set literal's own use
        (here, CONDUIT -- argument to a call), never UNCLASSIFIED
        """
        source = "def f(mode):\n    return frozenset({mode, 'other'})\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "frozenset({mode")
        self.assertTrue(hits)
        self.assertEqual(hits[0].roles, (crc.ROLE_CONDUIT,))


class TestHiddenDecisions(unittest.TestCase):
    def test_decision_hidden_in_ternary(self):
        """
        Given a value chosen by a conditional expression testing the subject
        When analyzed
        Then the subject's occurrence in the ternary TEST slot is DECISION
        """
        source = "def f(mode):\n    return 'yes' if mode else 'no'\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "if mode else")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_DECISION, hits[0].roles)

    def test_decision_hidden_in_match_case_guard(self):
        """
        Given a match statement whose case guard tests the subject
        When analyzed
        Then the subject's occurrence in the guard is DECISION
        """
        source = (
            "def f(mode, command):\n"
            "    match command:\n"
            "        case _ if mode:\n"
            "            return 'auto'\n"
            "        case _:\n"
            "            return 'manual'\n"
        )
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "case _ if mode:")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_DECISION, hits[0].roles)

    def test_match_subject_expression_is_decision(self):
        """
        Given a match statement switching directly on the subject
        When analyzed
        Then the subject's occurrence as the match subject is DECISION
        """
        source = "def f(mode):\n    match mode:\n        case True:\n            pass\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "match mode:")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_DECISION, hits[0].roles)


class TestConduitThroughAliasToDecision(unittest.TestCase):
    def test_hop_is_conduit_branch_is_decision(self):
        """
        Given the subject assigned to an intermediate local before that local is branched on
        When analyzed
        Then the assignment (the hop) is CONDUIT and the later branch use is DECISION
        """
        source = "def check(mode):\n    tmp = mode\n    if tmp:\n        return True\n    return False\n"
        analysis = _analyze(source, ["mode"])
        hop = _at(analysis, source, "tmp = mode")
        self.assertTrue(hop)
        self.assertIn(crc.ROLE_CONDUIT, hop[0].roles)
        self.assertNotIn(crc.ROLE_DECISION, hop[0].roles)
        branch = _at(analysis, source, "if tmp:")
        self.assertTrue(branch)
        self.assertIn(crc.ROLE_DECISION, branch[0].roles)
        self.assertTrue(branch[0].via_alias)


class TestFStringIsConduitNotWrite(unittest.TestCase):
    def test_fstring_use_is_conduit(self):
        """
        Given the subject used only inside an f-string
        When analyzed
        Then the occurrence is CONDUIT, never WRITE
        """
        source = "def f(mode):\n    return f'value is {mode}'\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "{mode}")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_CONDUIT, hits[0].roles)
        self.assertNotIn(crc.ROLE_WRITE, hits[0].roles)


class TestMutationWrites(unittest.TestCase):
    def test_attribute_assignment_target_is_write(self):
        """
        Given the subject as the attribute name on the left of an assignment (`obj.field = x`)
        When analyzed
        Then that occurrence is WRITE (a mutation)
        """
        source = "def f(rule):\n    rule.mode = True\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "rule.mode = True")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_value_persisted_into_attribute_is_write(self):
        """
        Given the subject used as the VALUE persisted into another object's attribute
        When analyzed
        Then that occurrence is WRITE ('serialised / persisted out')
        """
        source = "def f(rule, mode):\n    rule.enabled = mode\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "rule.enabled = mode")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_dict_value_write(self):
        """
        Given `dict[key] = x` where x is the subject
        When analyzed
        Then the subject's occurrence as the assigned value is WRITE
        """
        source = "def f(data, mode):\n    data['key'] = mode\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "data['key'] = mode")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_dict_key_position_is_conduit_not_write(self):
        """
        Given the subject used as the KEY (not the value) of a subscript write
        When analyzed
        Then that occurrence is CONDUIT -- the subject itself isn't being mutated, the value at
        that key is (a deliberate, documented distinction from the value-position case above)
        """
        source = "def f(data, mode):\n    data[mode] = 'value'\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "data[mode] = 'value'")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_CONDUIT, hits[0].roles)
        self.assertNotIn(crc.ROLE_WRITE, hits[0].roles)


class TestAnnotationIsCeremony(unittest.TestCase):
    def test_bare_annotation_only(self):
        """
        Given the subject appearing only as a type annotation, never assigned or branched on
        When analyzed
        Then the occurrence is CEREMONY
        """
        source = "def f(x: ModeFlag) -> None:\n    return None\n"
        analysis = _analyze(source, ["ModeFlag"])
        hits = _at(analysis, source, "x: ModeFlag")
        self.assertTrue(hits)
        self.assertEqual(hits[0].roles, (crc.ROLE_CEREMONY,))

    def test_annassign_annotation_only_ceremony(self):
        """
        Given a bare `name: Subject` declaration with no assigned value
        When analyzed
        Then the occurrence is CEREMONY, not WRITE (nothing is actually assigned)
        """
        source = "class C:\n    flag: ModeFlag\n"
        analysis = _analyze(source, ["ModeFlag"])
        hits = _at(analysis, source, "flag: ModeFlag")
        self.assertTrue(hits)
        self.assertEqual(hits[0].roles, (crc.ROLE_CEREMONY,))


class TestSignatureCeremony(unittest.TestCase):
    def test_parameter_declaration_is_ceremony(self):
        """
        Given the subject as a bare function parameter name
        When analyzed
        Then the signature occurrence itself is CEREMONY
        """
        source = "def f(mode):\n    return None\n"
        analysis = _analyze(source, ["mode"])
        hits = [o for o in analysis.occurrences if o.kind == "arg"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].roles, (crc.ROLE_CEREMONY,))


class TestDefNameBindsAsWrite(unittest.TestCase):
    """A `def`/property whose own name equals the subject is WRITE, since it binds a new name
    in its enclosing scope; see KNOWN_LIMITATIONS for what this still cannot see."""

    def test_property_def_matching_subject_is_write(self):
        """
        Given a `@property def <subject>(self):` whose name equals the subject
        When analyzed
        Then the def statement itself is WRITE (it binds the subject's name in the class)
        """
        source = (
            "class RuleEntry:\n"
            "    @property\n"
            "    def allow_in_auto_mode(self) -> bool:\n"
            "        value = self.metadata.get(KEY)\n"
            "        return value is True\n"
        )
        analysis = _analyze(source, ["allow_in_auto_mode"])
        def_hits = [o for o in analysis.occurrences if o.kind == "def-name"]
        self.assertEqual(len(def_hits), 1)
        self.assertIn(crc.ROLE_WRITE, def_hits[0].roles)
        self.assertEqual(len(analysis.occurrences), 1)


class TestImportsAndBindings(unittest.TestCase):
    def test_import_is_ceremony(self):
        """
        Given the subject imported by name
        When analyzed
        Then the import occurrence is CEREMONY
        """
        source = "from somewhere import mode\n"
        analysis = _analyze(source, ["mode"])
        self.assertEqual(len(analysis.occurrences), 1)
        self.assertEqual(analysis.occurrences[0].roles, (crc.ROLE_CEREMONY,))

    def test_del_is_write(self):
        """
        Given `del subject`
        When analyzed
        Then the occurrence is WRITE (a deletion mutates the namespace)
        """
        source = "def f():\n    mode = True\n    del mode\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "del mode")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_bare_match_capture_is_write(self):
        """
        Given a bare-name match-case pattern that captures into the subject's name
        When analyzed
        Then the capture occurrence is WRITE (it binds a new value each match)
        """
        source = "def f(command):\n    match command:\n        case mode:\n            return mode\n"
        analysis = _analyze(source, ["mode"])
        capture_hits = [o for o in analysis.occurrences if o.kind == "match-as"]
        self.assertEqual(len(capture_hits), 1)
        self.assertIn(crc.ROLE_WRITE, capture_hits[0].roles)

    def test_keyword_argument_name_is_conduit(self):
        """
        Given the subject used as a call-site keyword-argument name
        When analyzed
        Then that occurrence is CONDUIT (forwarding a value under that name into a call)
        """
        source = "def f(mode):\n    Rule(mode=True)\n"
        analysis = _analyze(source, ["mode"])
        kw_hits = [o for o in analysis.occurrences if o.kind == "keyword-name"]
        self.assertEqual(len(kw_hits), 1)
        self.assertEqual(kw_hits[0].roles, (crc.ROLE_CONDUIT,))

    def test_subject_as_keyword_argument_value_in_branch_test_reaches_decision(self):
        """
        Given the subject passed as a keyword-argument VALUE (not the argument name) inside
        a call that is itself the test of an `if`
        When analyzed
        Then the occurrence carries BOTH CONDUIT (the keyword-argument hop) and DECISION
        (the call's result is the branch test)
        """
        source = "x = None\nif f(key=x):\n    pass\n"
        analysis = _analyze(source, ["x"])
        hits = _at(analysis, source, "if f(key=x):")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_CONDUIT, hits[0].roles)
        self.assertIn(crc.ROLE_DECISION, hits[0].roles)


class TestWalrusDualRole(unittest.TestCase):
    def test_walrus_target_tested_is_write_and_decision(self):
        """
        Given a walrus assignment whose target is immediately truth-tested
        When analyzed
        Then the occurrence carries BOTH WRITE (it binds) and DECISION (it's the test)
        """
        source = "def f(compute):\n    if (mode := compute()):\n        return True\n    return False\n"
        analysis = _analyze(source, ["mode"])
        hits = _at(analysis, source, "mode := compute()")
        self.assertTrue(hits)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)
        self.assertIn(crc.ROLE_DECISION, hits[0].roles)


class TestHonestyRequirements(unittest.TestCase):
    """Never silently skip: parse failures and unhandled constructs are named explicitly, not
    folded into a zero."""

    def test_parse_failure_is_reported_not_silently_dropped(self):
        """
        Given a file with a syntax error
        When analyzed
        Then FileAnalysis.parse_error is set and occurrences is empty (never a false zero)
        """
        analysis = _analyze("def broken(:\n    pass\n", ["mode"])
        self.assertIsNotNone(analysis.parse_error)
        self.assertEqual(analysis.occurrences, [])

    def test_unhandled_construct_is_unclassified_not_dropped(self):
        """
        Given the subject used as a bare-name decorator, a construct this tool has no
        classification rule for
        When analyzed
        Then the occurrence is reported with role UNCLASSIFIED and an explanatory note,
        never silently absent from the results
        """
        source = "@mode\ndef f():\n    pass\n"
        analysis = _analyze(source, ["mode"])
        self.assertEqual(len(analysis.occurrences), 1)
        occ = analysis.occurrences[0]
        self.assertEqual(occ.roles, (crc.ROLE_UNCLASSIFIED,))
        self.assertTrue(occ.notes)

    def test_string_literal_mention_is_surfaced_separately_not_as_a_role(self):
        """
        Given the subject reached only through a string-keyed getattr call
        When analyzed
        Then it is recorded as a string_mention (visible), NOT as a role-classified occurrence
        """
        source = "def f(obj):\n    return getattr(obj, 'mode', False)\n"
        analysis = _analyze(source, ["mode"])
        self.assertEqual(analysis.occurrences, [])
        self.assertEqual(len(analysis.string_mentions), 1)
        self.assertEqual(analysis.string_mentions[0].subject, "mode")

    def test_accumulated_role_with_unhandled_parent_is_surfaced_in_occurrences_with_notes(
        self,
    ):
        """
        Given a bare expression statement where the subject flows through two CONTINUE hops
        (a Call, then an Attribute) before reaching a genuinely unhandled parent (a bare
        `Expr` statement)
        When the report is built
        Then the occurrence has a real role (CONDUIT, not UNCLASSIFIED) AND a non-empty note,
        and it appears in the report's `occurrences_with_notes` section
        """
        source = "x = None\nbool(x).bit_length()\n"
        analysis = _analyze(source, ["x"])
        hits = _at(analysis, source, "bool(x)")
        self.assertTrue(hits)
        self.assertEqual(hits[0].roles, (crc.ROLE_CONDUIT,))
        self.assertTrue(hits[0].notes)

        result = crc.AnalysisResult(
            mode="unit-test",
            subjects=["x"],
            files_analyzed=[
                crc.FileAnalysis(
                    file="f.py",
                    parse_error=None,
                    occurrences=analysis.occurrences,
                    string_mentions=[],
                )
            ],
            parse_failures=[],
            removed_files=[],
            closure=crc.compute_symbol_closure(
                {}, ["x"], crc.DEFAULT_CLOSURE_HOP_LIMIT
            ),
        )
        report = crc.build_report(result)
        self.assertEqual(len(report["occurrences_with_notes"]), 1)
        self.assertEqual(report["unclassified_occurrences"], [])


class TestPrimaryRolePrecedence(unittest.TestCase):
    """`primary_role` reduces a set of roles to one label by fixed precedence."""

    def test_primary_role_precedence(self):
        """
        Given an occurrence with both WRITE and DECISION roles
        When reduced to a single label
        Then DECISION wins (DECISION > WRITE > CONDUIT > CEREMONY)
        """
        self.assertEqual(
            crc.primary_role((crc.ROLE_WRITE, crc.ROLE_DECISION)), crc.ROLE_DECISION
        )


class TestPathBasedTestVsProduction(unittest.TestCase):
    """Test-vs-production is distinguished by path; the rule used is stated in report output."""

    def test_paths_under_test_directory_are_test(self):
        self.assertTrue(crc.is_test_path(Path("test/unit/test_foo.py")))

    def test_test_prefixed_filename_is_test(self):
        self.assertTrue(crc.is_test_path(Path("toolguard/test_helpers.py")))

    def test_suffix_test_filename_is_test(self):
        self.assertTrue(crc.is_test_path(Path("toolguard/foo_test.py")))

    def test_production_path_is_not_test(self):
        self.assertFalse(crc.is_test_path(Path("toolguard/config.py")))

    def test_rule_text_is_present_in_report(self):
        """
        Given a built report
        When printed
        Then the test-vs-production rule used is stated explicitly, not left implicit
        """
        result = crc.AnalysisResult(
            mode="unit-test",
            subjects=["mode"],
            files_analyzed=[],
            parse_failures=[],
            removed_files=[],
            closure=crc.compute_symbol_closure(
                {}, ["mode"], crc.DEFAULT_CLOSURE_HOP_LIMIT
            ),
        )
        report = crc.build_report(result)
        self.assertEqual(report["test_vs_production_rule"], crc.TEST_VS_PRODUCTION_RULE)


class TestChangedLineRestriction(unittest.TestCase):
    def test_only_changed_lines_are_analyzed(self):
        """
        Given an old and a new version of a file where an unchanged assignment is followed by
        newly-added lines
        When computing changed lines and analyzing restricted to them
        Then the occurrence on the unchanged line is excluded, and the one on a newly-added
        line is kept
        """
        old_text = "x = 1\nprint(x)\nmode = False\n"
        new_text = "x = 1\nprint(x)\nmode = False\nif mode:\n    pass\n"
        changed = crc.compute_changed_lines(old_text, new_text)
        analysis = crc.analyze_source(
            new_text, "f.py", ["mode"], allowed_lines=changed, is_test=False
        )
        lines_seen = {o.line for o in analysis.occurrences}
        self.assertNotIn(3, lines_seen)
        self.assertIn(4, lines_seen)


class TestRarerBindingKinds(unittest.TestCase):
    """Binding kinds with their own plain-string AST field (not a Name node), each a distinct
    code path."""

    def test_except_handler_name_is_write(self):
        """
        Given `except ... as <subject>:`
        When analyzed
        Then the occurrence is WRITE (it binds the caught exception under this name)
        """
        source = "def f():\n    try:\n        pass\n    except ValueError as mode:\n        raise mode\n"
        analysis = _analyze(source, ["mode"])
        hits = [o for o in analysis.occurrences if o.kind == "except-name"]
        self.assertEqual(len(hits), 1)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_match_star_capture_is_write(self):
        """
        Given a sequence match pattern `case [first, *mode]:`
        When analyzed
        Then the `*subject` capture is WRITE
        """
        source = "def f(command):\n    match command:\n        case [first, *mode]:\n            return mode\n"
        analysis = _analyze(source, ["mode"])
        hits = [o for o in analysis.occurrences if o.kind == "match-star"]
        self.assertEqual(len(hits), 1)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_match_mapping_rest_is_write(self):
        """
        Given a mapping match pattern `case {"k": v, **mode}:`
        When analyzed
        Then the `**subject` catch-all capture is WRITE
        """
        source = (
            "def f(command):\n"
            "    match command:\n"
            "        case {'k': v, **mode}:\n"
            "            return mode\n"
        )
        analysis = _analyze(source, ["mode"])
        hits = [o for o in analysis.occurrences if o.kind == "match-mapping-rest"]
        self.assertEqual(len(hits), 1)
        self.assertIn(crc.ROLE_WRITE, hits[0].roles)

    def test_global_declaration_is_ceremony(self):
        """
        Given `global <subject>` inside a function
        When analyzed
        Then the declaration is CEREMONY (a scope declaration, not logic)
        """
        source = "mode = False\n\n\ndef f():\n    global mode\n    mode = True\n"
        analysis = _analyze(source, ["mode"])
        hits = [o for o in analysis.occurrences if o.kind == "global"]
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].roles, (crc.ROLE_CEREMONY,))


class TestTwoTreeDiffMode(unittest.TestCase):
    """Regression coverage for `run_two_tree_diff`."""

    def test_restricts_to_changed_lines_and_reports_added_and_removed_files(self):
        """
        Given an OLD tree and a NEW tree where one file changed, one was added, and one was
        removed
        When run_two_tree_diff analyzes them for the subject
        Then the changed file's occurrence is only reported for its new/changed lines, the
        added file is fully analyzed, and the removed file is named in removed_files (never
        silently dropped)
        """
        with (
            tempfile.TemporaryDirectory() as old_dir,
            tempfile.TemporaryDirectory() as new_dir,
        ):
            old_root, new_root = Path(old_dir), Path(new_dir)
            (old_root / "m.py").write_text("x = 1\nprint(x)\nmode = False\n")
            (new_root / "m.py").write_text(
                "x = 1\nprint(x)\nmode = False\nif mode:\n    pass\n"
            )
            (old_root / "gone.py").write_text("mode = True\n")
            (new_root / "added.py").write_text("mode = True\nif mode:\n    pass\n")

            result = crc.run_two_tree_diff(old_root, new_root, ["mode"])

            self.assertEqual(result.removed_files, ["gone.py"])
            occ_by_file = {}
            for fa in result.files_analyzed:
                occ_by_file[fa.file] = {o.line for o in fa.occurrences}
            self.assertNotIn(3, occ_by_file["m.py"])
            self.assertIn(4, occ_by_file["m.py"])
            self.assertEqual(occ_by_file["added.py"], {1, 2})

    def test_byte_identical_move_reports_no_occurrences(self):
        """
        Given a file moved from `pkg/a.py` to `pkg2/a.py` with byte-identical content
        When run_two_tree_diff analyzes old vs. new
        Then it reports ZERO occurrences for the moved file, and the old path is NOT listed
        in removed_files (it was not removed, it moved)
        """
        with (
            tempfile.TemporaryDirectory() as old_dir,
            tempfile.TemporaryDirectory() as new_dir,
        ):
            old_root, new_root = Path(old_dir), Path(new_dir)
            content = "mode = True\nif mode:\n    pass\n"
            (old_root / "pkg").mkdir()
            (old_root / "pkg" / "a.py").write_text(content)
            (new_root / "pkg2").mkdir()
            (new_root / "pkg2" / "a.py").write_text(content)

            result = crc.run_two_tree_diff(old_root, new_root, ["mode"])

            self.assertEqual(len(result.files_analyzed), 1)
            self.assertEqual(result.files_analyzed[0].file, "pkg2/a.py")
            self.assertEqual(result.files_analyzed[0].occurrences, [])
            self.assertEqual(result.removed_files, [])

    def test_move_with_real_edit_still_finds_the_edit(self):
        """
        Given a file moved to a new path AND edited (a new decision added) in the new tree
        When run_two_tree_diff analyzes old vs. new
        Then the new decision IS found -- move detection must not also swallow real edits
        """
        with (
            tempfile.TemporaryDirectory() as old_dir,
            tempfile.TemporaryDirectory() as new_dir,
        ):
            old_root, new_root = Path(old_dir), Path(new_dir)
            (old_root / "pkg").mkdir()
            (old_root / "pkg" / "a.py").write_text("mode = True\n")
            (new_root / "pkg2").mkdir()
            (new_root / "pkg2" / "a.py").write_text("mode = True\nif mode:\n    pass\n")

            result = crc.run_two_tree_diff(old_root, new_root, ["mode"])

            self.assertEqual(result.files_analyzed[0].file, "pkg2/a.py")
            self.assertTrue(
                any(
                    crc.ROLE_DECISION in o.roles
                    for o in result.files_analyzed[0].occurrences
                )
            )


class TestGitDiffMode(unittest.TestCase):
    """Regression coverage for `run_git_diff`, using a throwaway git repo (never the real
    toolguard repo)."""

    def test_reports_changed_lines_from_two_commits(self):
        """
        Given a throwaway git repo with a commit adding a decision on the subject
        When run_git_diff analyzes base..head
        Then the new decision line is reported as DECISION and the file is named as analyzed
        """
        with tempfile.TemporaryDirectory() as repo_dir:
            repo = Path(repo_dir)
            run = lambda *args: subprocess.run(  # noqa: E731
                ["git", "-C", str(repo), *args],
                check=True,
                capture_output=True,
                text=True,
                env={
                    "GIT_AUTHOR_NAME": "t",
                    "GIT_AUTHOR_EMAIL": "t@t.com",
                    "GIT_COMMITTER_NAME": "t",
                    "GIT_COMMITTER_EMAIL": "t@t.com",
                    "PATH": "/usr/bin:/bin",
                },
            )
            run("init", "-q")
            (repo / "m.py").write_text("x = 1\n")
            run("add", "m.py")
            run("commit", "-q", "-m", "base")
            base = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repo / "m.py").write_text("x = 1\nmode = True\nif mode:\n    pass\n")
            run("add", "m.py")
            run("commit", "-q", "-m", "head")
            head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = crc.run_git_diff(repo, base, head, ["mode"])

            self.assertEqual(len(result.files_analyzed), 1)
            fa = result.files_analyzed[0]
            self.assertEqual(fa.file, "m.py")
            decision_lines = {
                o.line for o in fa.occurrences if crc.ROLE_DECISION in o.roles
            }
            self.assertEqual(decision_lines, {3})


def _trees(files: dict[str, str]) -> dict:
    """Parses a {file_label: source} mapping into {file_label: ast.Module}."""
    return {label: ast.parse(source, filename=label) for label, source in files.items()}


class TestSymbolClosure(unittest.TestCase):
    """Closure growth is definition-site based (exact string/identifier equality), never name
    similarity."""

    def test_constant_bound_to_subject_string_read_via_dot_get_is_found(self):
        """
        Given a module-level constant bound to the subject's exact string, read via
        `metadata.get(CONST)` inside an accessor whose own name is the subject
        When the closure is computed
        Then the constant joins at hop 1, and its `.get(...)` usage is found once the tracked
        names are fed into ordinary occurrence scanning
        """
        source = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "class Entry:\n"
            "    @property\n"
            "    def mode(self):\n"
            "        return self.metadata.get(MODE_KEY)\n"
        )
        trees = _trees({"a.py": source})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertIn("MODE_KEY", closure.tracked_names)
        self.assertEqual(closure.members["MODE_KEY"].hop, 1)
        self.assertEqual(
            closure.members["MODE_KEY"].rule, crc.CLOSURE_RULE_STRING_LITERAL
        )

        analysis = crc.analyze_source(
            source, "a.py", closure.tracked_names, None, False
        )
        usage = _at(analysis, source, "metadata.get(MODE_KEY)")
        self.assertTrue(usage)
        self.assertEqual(usage[0].subject, "MODE_KEY")

    def test_decoy_constant_with_similar_name_but_different_string_is_not_found(self):
        """
        Given a constant whose NAME resembles the subject but whose bound STRING is different
        When the closure is computed
        Then it does not join -- matching is on the string value, never the constant's name
        """
        trees = _trees({"a.py": "MODE_DECOY_KEY = 'not_the_subject'\n"})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertNotIn("MODE_DECOY_KEY", closure.tracked_names)

    def test_helper_with_similar_name_that_never_touches_subject_is_not_found(self):
        """
        Given a function whose name resembles the subject but whose body never references any
        tracked symbol
        When the closure is computed
        Then it does not join -- own-name growth requires an EXACT match to a tracked name,
        never a resemblance
        """
        trees = _trees({"a.py": "def mode_like_helper():\n    return 'unrelated'\n"})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertNotIn("mode_like_helper", closure.tracked_names)

    def test_two_hop_chain_call_site_found_at_hop_two(self):
        """
        Given constant -> genuine ACCESSOR (a bare `return CONST`, nothing more) -> call site
        of the accessor, spread across two files, with hop_limit=2
        When the closure is computed and fed into occurrence scanning
        Then the accessor joins at hop 2 via CLOSURE_RULE_RETURNS_TRACKED, and its call site
        (in the OTHER file) is found
        """
        a = "MODE_KEY = 'mode'\n\n\ndef get_mode_key():\n    return MODE_KEY\n"
        b = (
            "from a import get_mode_key\n\n\n"
            "def check(metadata):\n    return metadata[get_mode_key()]\n"
        )
        trees = _trees({"a.py": a, "b.py": b})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertEqual(closure.members["MODE_KEY"].hop, 1)
        self.assertEqual(closure.members["get_mode_key"].hop, 2)
        self.assertEqual(
            closure.members["get_mode_key"].rule, crc.CLOSURE_RULE_RETURNS_TRACKED
        )

        analysis_b = crc.analyze_source(b, "b.py", closure.tracked_names, None, False)
        call_site = _at(analysis_b, b, "get_mode_key()")
        self.assertTrue(any(o.subject == "get_mode_key" for o in call_site))

    def test_function_whose_return_expression_references_tracked_symbol_now_grows_closure(
        self,
    ):
        """
        Given a function whose return expression contains the tracked constant nested
        inside a ternary/isinstance/subscript, not as a bare top-level Name
        When the closure is computed
        Then the function DOES join the closure
        """
        source = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def validate(metadata):\n"
            "    if MODE_KEY not in metadata:\n"
            "        return []\n"
            "    return ['issue'] if not isinstance(metadata[MODE_KEY], bool) else []\n"
        )
        trees = _trees({"a.py": source})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertIn("validate", closure.tracked_names)
        self.assertEqual(
            closure.members["validate"].rule, crc.CLOSURE_RULE_RETURNS_TRACKED
        )

    def test_function_whose_return_never_mentions_tracked_symbol_still_does_not_grow_closure(
        self,
    ):
        """
        Given a function that checks a tracked constant in an earlier statement, then
        returns a value built by a helper call that does not itself reference the constant
        When the closure is computed
        Then the function does NOT join the closure
        """
        source = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def validate(metadata):\n"
            "    has_key = MODE_KEY in metadata\n"
            "    if not has_key:\n"
            "        return []\n"
            "    return build_issue_list(metadata)\n"
        )
        trees = _trees({"a.py": source})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertNotIn("validate", closure.tracked_names)

    def test_stylistic_rewrite_of_predicate_body_does_not_change_closure_membership(
        self,
    ):
        """
        Given the identical predicate logic written both ways
        When the closure is computed for each
        Then BOTH forms admit the predicate function -- the rewrite changes nothing
        """
        boolop_style = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def predicate(decision, entry):\n"
            "    return decision != 'allow' and entry is not None and entry.mode\n"
        )
        early_return_style = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def predicate(decision, entry):\n"
            "    if decision == 'allow' or entry is None:\n"
            "        return False\n"
            "    return entry.mode\n"
        )
        boolop_closure = crc.compute_symbol_closure(
            _trees({"a.py": boolop_style}), ["mode"], hop_limit=2
        )
        early_return_closure = crc.compute_symbol_closure(
            _trees({"a.py": early_return_style}), ["mode"], hop_limit=2
        )
        self.assertIn("predicate", boolop_closure.tracked_names)
        self.assertIn("predicate", early_return_closure.tracked_names)

    def test_three_hop_chain_is_excluded_at_limit_two_and_reported(self):
        """
        Given constant -> genuine accessor (hop 2) -> a second function that bare-returns the
        accessor ITSELF (a callable-forwarding shape -- still a bare `return NAME`, so it
        matches CLOSURE_RULE_RETURNS_TRACKED, and would join at hop 3), with hop_limit=2
        When the closure is computed
        Then the wrapper does NOT join tracked_names, but IS listed in `excluded`, naming the
        hop it would have joined at and why -- never silently dropped
        """
        source = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def get_mode_key():\n"
            "    return MODE_KEY\n"
            "\n\n"
            "def wrapper():\n"
            "    return get_mode_key\n"
        )
        trees = _trees({"a.py": source})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertNotIn("wrapper", closure.tracked_names)
        excluded_names = {c.name: c for c in closure.excluded}
        self.assertIn("wrapper", excluded_names)
        self.assertEqual(excluded_names["wrapper"].would_be_hop, 3)
        self.assertEqual(
            excluded_names["wrapper"].rule, crc.CLOSURE_RULE_RETURNS_TRACKED
        )

    def test_locally_shadowed_parameter_does_not_pull_unrelated_function_into_closure(
        self,
    ):
        """
        Given a function whose PARAMETER happens to share a tracked constant's name, used only
        as that parameter (never as the actual tracked symbol)
        When the closure is computed
        Then the function does NOT join -- a same-spelled local shadow is not credited as a
        reference to the outer tracked symbol
        """
        source = (
            "MODE_KEY = 'mode'\n"
            "\n\n"
            "def unrelated(MODE_KEY):\n"
            "    return MODE_KEY.upper()\n"
        )
        trees = _trees({"a.py": source})
        closure = crc.compute_symbol_closure(trees, ["mode"], hop_limit=2)
        self.assertNotIn("unrelated", closure.tracked_names)

    def test_end_to_end_single_tree_run_expands_subjects_via_closure(self):
        """
        Given a small on-disk tree with the same constant -> genuine accessor -> call-site
        shape
        When run_single_tree analyzes it for the bare subject
        Then the accessor's call site is reported as an occurrence, and the report's closure
        section names both the constant and the accessor with their hop and reason
        """
        with tempfile.TemporaryDirectory() as tree_dir:
            root = Path(tree_dir)
            (root / "a.py").write_text(
                "MODE_KEY = 'mode'\n\n\ndef get_mode_key():\n    return MODE_KEY\n"
            )
            (root / "b.py").write_text(
                "from a import get_mode_key\n\n\n"
                "def check(metadata):\n    return metadata[get_mode_key()]\n"
            )
            result = crc.run_single_tree(root, ["mode"])
            self.assertEqual(result.closure.members["MODE_KEY"].hop, 1)
            self.assertEqual(result.closure.members["get_mode_key"].hop, 2)
            all_subjects = {
                o.subject for fa in result.files_analyzed for o in fa.occurrences
            }
            self.assertIn("get_mode_key", all_subjects)
            self.assertIn("MODE_KEY", all_subjects)


class TestOpaqueHops(unittest.TestCase):
    """Opaque hops count places where a tracked symbol feeds a local that is used again,
    without classifying what happens after."""

    def test_real_property_shape_is_counted(self):
        """
        Given `value = self.metadata.get(THE_KEY); return value is True`
        When analyzed with THE_KEY tracked
        Then one opaque hop is reported, naming the local and the tracked symbol involved
        """
        source = (
            "def f(self):\n"
            "    value = self.metadata.get(THE_KEY)\n"
            "    return value is True\n"
        )
        analysis = _analyze(source, ["THE_KEY"])
        self.assertEqual(len(analysis.opaque_hops), 1)
        hop = analysis.opaque_hops[0]
        self.assertEqual(hop.local_name, "value")
        self.assertEqual(hop.tracked_symbols_involved, ("THE_KEY",))

    def test_assigned_but_never_used_again_is_not_counted(self):
        """
        Given a local bound from a tracked symbol but never referenced again
        When analyzed
        Then it is NOT counted -- nothing is "then used further"
        """
        source = (
            "def f(self):\n    value = self.metadata.get(THE_KEY)\n    return None\n"
        )
        analysis = _analyze(source, ["THE_KEY"])
        self.assertEqual(analysis.opaque_hops, [])

    def test_bare_copy_is_not_double_counted_as_opaque(self):
        """
        Given a plain `alias = tracked_symbol` copy (the existing, followable alias-hop case)
        When analyzed
        Then it is NOT counted as an opaque hop -- that would double-count an event the tool
        already follows via the alias-hop feature
        """
        source = "def f(mode):\n    tmp = mode\n    if tmp:\n        return True\n    return False\n"
        analysis = _analyze(source, ["mode"])
        self.assertEqual(analysis.opaque_hops, [])

    def test_report_splits_production_and_test(self):
        """
        Given one opaque hop in a production file and one in a test file
        When the report is built
        Then the opaque_hops section counts each separately, plus a total
        """
        prod_source = (
            "def f(self):\n    value = self.metadata.get(THE_KEY)\n    return value\n"
        )
        test_source = "def test_f(self):\n    value = self.metadata.get(THE_KEY)\n    assert value\n"
        prod_fa = crc._analyze_tree(
            ast.parse(prod_source), "a.py", ["THE_KEY"], None, is_test=False
        )
        test_fa = crc._analyze_tree(
            ast.parse(test_source),
            "test/unit/test_a.py",
            ["THE_KEY"],
            None,
            is_test=True,
        )
        result = crc.AnalysisResult(
            mode="unit-test",
            subjects=["THE_KEY"],
            files_analyzed=[prod_fa, test_fa],
            parse_failures=[],
            removed_files=[],
            closure=crc.compute_symbol_closure(
                {}, ["THE_KEY"], crc.DEFAULT_CLOSURE_HOP_LIMIT
            ),
        )
        report = crc.build_report(result)
        self.assertEqual(report["opaque_hops"]["production"], 1)
        self.assertEqual(report["opaque_hops"]["test"], 1)
        self.assertEqual(report["opaque_hops"]["total"], 2)


class TestBoolOpCaveatPrintedNotOnlyInLimitations(unittest.TestCase):
    """Regression: the BoolOp-is-unconditional-DECISION caveat used to exist only in
    KNOWN_LIMITATIONS; `print_text_report` must show it next to the role breakdown too."""

    def test_caveat_appears_near_role_breakdown_in_text_output(self):
        result = crc.AnalysisResult(
            mode="unit-test",
            subjects=["mode"],
            files_analyzed=[],
            parse_failures=[],
            removed_files=[],
            closure=crc.compute_symbol_closure(
                {}, ["mode"], crc.DEFAULT_CLOSURE_HOP_LIMIT
            ),
        )
        report = crc.build_report(result)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            crc.print_text_report(report)
        output = buf.getvalue()
        role_breakdown_pos = output.index("ROLE BREAKDOWN")
        caveat_pos = output.index("CAVEAT on DECISION counts")
        production_bucket_pos = output.index("-- PRODUCTION --")
        self.assertLess(role_breakdown_pos, caveat_pos)
        self.assertLess(caveat_pos, production_bucket_pos)


class TestOpaqueHopsReturnScanning(unittest.TestCase):
    """Regression: opaque-hop scanning used to check only assignments, missing `Return`/`Yield`
    values; a Return/Yield-scanning safety net now covers that without double-counting an
    already-promoted accessor."""

    def test_hop_limited_accessor_return_is_flagged(self):
        """
        Given a genuine accessor chain (constant -> accessor -> wrapper -> double-wrapper)
        where hop_limit=2 excludes the double-wrapper from the closure
        When analyzed end-to-end through run_single_tree
        Then the excluded wrapper's own return (which DOES reference a tracked symbol, just
        one hop beyond the limit) is flagged as an opaque hop -- a safety net beyond the
        excluded_by_hop_limit list, which only names the SYMBOL, not where its own return is
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text(
                "KEY = 'flag'\n\n\n"
                "def get_key():\n    return KEY\n\n\n"
                "def wrapper():\n    return get_key\n\n\n"
                "def double_wrapper():\n    return wrapper\n"
            )
            result = crc.run_single_tree(root, ["flag"], closure_hop_limit=2)
            self.assertIn("get_key", result.closure.tracked_names)
            self.assertNotIn("wrapper", result.closure.tracked_names)
            excluded_names = {c.name for c in result.closure.excluded}
            self.assertIn("wrapper", excluded_names)
            fa = result.files_analyzed[0]
            return_hops = [h for h in fa.opaque_hops if h.local_name == "<return>"]
            self.assertTrue(
                any("get_key" in h.tracked_symbols_involved for h in return_hops)
            )

    def test_promoted_accessor_return_is_not_double_flagged(self):
        """
        Given a genuine one-line accessor whose return DOES get it promoted into the closure
        When analyzed end-to-end
        Then its own return is NOT also flagged as an opaque hop -- it is a tracked
        occurrence already, and flagging it too would contradict "tracked" with "opaque" for
        the same location
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text(
                "KEY = 'flag'\n\n\nclass A:\n    def one_liner(self):\n        return KEY\n"
            )
            result = crc.run_single_tree(root, ["flag"], closure_hop_limit=2)
            self.assertIn("one_liner", result.closure.tracked_names)
            fa = result.files_analyzed[0]
            self.assertEqual(fa.opaque_hops, [])

    def test_generator_yield_is_scanned_like_return(self):
        """
        Given a generator function whose `yield` (not `return`) value references a tracked
        symbol, analyzed directly (bypassing closure/growth entirely, so "gen" is never a
        tracked symbol itself)
        When analyzed
        Then the yield is flagged as an opaque hop, the same way a `return` would be
        """
        source = "def gen(items):\n    for x in items:\n        yield x.flag_x\n"
        analysis = _analyze(source, ["flag_x"])
        return_hops = [h for h in analysis.opaque_hops if h.local_name == "<return>"]
        self.assertTrue(
            any("flag_x" in h.tracked_symbols_involved for h in return_hops)
        )


class TestClosureParseFailuresSurfaced(unittest.TestCase):
    """Regression: in git-diff mode, a file fetched only for closure discovery that failed to
    parse used to be silently excluded from closure growth with no trace in the output."""

    def test_non_diff_file_parse_failure_is_reported_not_dropped(self):
        """
        Given a git repo where the diff touches one file, and a SEPARATE, untouched file at
        head has a syntax error
        When run_git_diff analyzes the diff
        Then the untouched file's parse failure is named in closure_parse_failures, not
        silently absent -- and NOT duplicated into the diff-scoped parse_failures list
        """
        with tempfile.TemporaryDirectory() as repo_dir:
            repo = Path(repo_dir)
            env = {
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@t.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@t.com",
                "PATH": "/usr/bin:/bin",
            }
            run = lambda *args: subprocess.run(  # noqa: E731
                ["git", "-C", str(repo), *args],
                check=True,
                capture_output=True,
                text=True,
                env=env,
            )
            run("init", "-q")
            (repo / "m.py").write_text("x = 1\n")
            (repo / "broken.py").write_text("def broken(:\n    pass\n")
            run("add", "m.py", "broken.py")
            run("commit", "-q", "-m", "base")
            base = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            (repo / "m.py").write_text("x = 1\nmode = True\nif mode:\n    pass\n")
            run("add", "m.py")
            run("commit", "-q", "-m", "head")
            head = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()

            result = crc.run_git_diff(repo, base, head, ["mode"])

            self.assertEqual(result.parse_failures, [])
            self.assertEqual(len(result.closure_parse_failures), 1)
            self.assertTrue(result.closure_parse_failures[0].startswith("broken.py:"))


class TestDualRoleThroughCallsAndAttributes(unittest.TestCase):
    """Regression: `_governing_role` used to return a terminal CONDUIT for `Call.args`/
    `Call.func` and `Attribute.value`, scoring a decision expressed through one layer of
    indirection as pure transport."""

    def _decision_present(self, source: str, subject: str = "x") -> tuple:
        analysis = _analyze(source, [subject])
        hits = [o for o in analysis.occurrences if o.line == 2]
        self.assertTrue(hits, f"no occurrence found for: {source!r}")
        return hits[0].roles

    def test_if_bool_call(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif bool(x):\n    pass\n"),
        )

    def test_if_len_compare(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif len(x) > 0:\n    pass\n"),
        )

    def test_if_attribute(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif x.enabled:\n    pass\n"),
        )

    def test_if_attribute_call(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif x.is_ready():\n    pass\n"),
        )

    def test_if_isinstance(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif isinstance(x, str):\n    pass\n"),
        )

    def test_if_dict_get(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present("x = None\nif items.get(x):\n    pass\n"),
        )

    def test_if_walrus_value_not_target(self):
        self.assertIn(
            crc.ROLE_DECISION,
            self._decision_present(
                "x = None\nif (found := x) is not None:\n    pass\n"
            ),
        )

    def test_conduit_role_is_kept_alongside_decision(self):
        """
        Given `if bool(x):` (subject passed through a call that is itself branch-tested)
        When analyzed
        Then the occurrence carries BOTH CONDUIT (it moved through the call) AND DECISION
        (the call's result is the branch test) -- a dual role, not a swap
        """
        roles = self._decision_present("x = None\nif bool(x):\n    pass\n")
        self.assertIn(crc.ROLE_CONDUIT, roles)
        self.assertIn(crc.ROLE_DECISION, roles)

    def test_predicate_function_call_sites_now_register_decision(self):
        """
        Given the same requirement copy-pasted inline at one call site vs. factored into a
        predicate function called from another, where the factored version used to score as
        pure CONDUIT with zero DECISION
        When analyzed
        Then BOTH forms register DECISION: the inline form directly, the factored form via
        the walk now reaching through the `Call` to the enclosing `if`
        """
        inline = "def check(entry, mode):\n    if mode == 'auto' and entry.subject:\n        return True\n    return False\n"
        factored = (
            "def predicate(entry, mode):\n"
            "    return mode == 'auto' and entry.subject\n"
            "\n\n"
            "def check(entry, mode):\n"
            "    if predicate(entry, mode):\n"
            "        return True\n"
            "    return False\n"
        )
        inline_analysis = _analyze(inline, ["subject"])
        factored_analysis = _analyze(factored, ["subject"])
        self.assertTrue(
            any(crc.ROLE_DECISION in o.roles for o in inline_analysis.occurrences)
        )
        self.assertTrue(
            any(crc.ROLE_DECISION in o.roles for o in factored_analysis.occurrences),
            "factored predicate's own body must still register DECISION on `entry.subject`",
        )


class TestStatementSpanLineFiltering(unittest.TestCase):
    """Regression: line-restriction used to check only the occurrence node's own line, so a
    change elsewhere in the same multi-line statement (moved into a branch test, or a
    comparand edit) could report zero occurrences."""

    def test_subject_moved_from_call_arg_into_branch_test(self):
        """
        Given a statement whose meaning changed from "pass the subject to a call" to "branch
        on the subject", where difflib marks a line that is not the subject's own line
        When restricted to changed lines
        Then the occurrence IS found, as DECISION -- not silently zero
        """
        old = "def f(entry, sink):\n    sink(\n        entry.subject,\n    )\n"
        new = "def f(entry, sink):\n    if (\n        entry.subject\n    ):\n        return 1\n"
        changed = crc.compute_changed_lines(old, new)
        analysis = crc.analyze_source(
            new, "f.py", ["subject"], allowed_lines=changed, is_test=False
        )
        self.assertTrue(analysis.occurrences)
        self.assertTrue(any(crc.ROLE_DECISION in o.roles for o in analysis.occurrences))

    def test_decision_comparand_edit_is_found(self):
        """
        Given a multi-line `if entry.subject == "...":` where only the comparand string
        changed, not the subject's own line
        When restricted to changed lines
        Then the occurrence IS found, as DECISION -- not silently zero
        """
        old = 'def f(entry):\n    if (\n        entry.subject\n        == "old_value"\n    ):\n        return 1\n'
        new = 'def f(entry):\n    if (\n        entry.subject\n        == "new_value"\n    ):\n        return 1\n'
        changed = crc.compute_changed_lines(old, new)
        analysis = crc.analyze_source(
            new, "f.py", ["subject"], allowed_lines=changed, is_test=False
        )
        self.assertTrue(analysis.occurrences)
        self.assertTrue(any(crc.ROLE_DECISION in o.roles for o in analysis.occurrences))


_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@t.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@t.com",
    "PATH": "/usr/bin:/bin",
}


def _git_run(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        env=_GIT_ENV,
    )


def _git_head(repo: Path) -> str:
    return _git_run(repo, "rev-parse", "HEAD").stdout.strip()


class TestGitRenameDetection(unittest.TestCase):
    """Regression: without `-M` rename detection, a renamed file's new path has no pre-image at
    base, so the whole file counted as changed even for a byte-identical `git mv`."""

    def test_pure_rename_reports_no_occurrences(self):
        """
        Given a pure `git mv` (byte-identical content) of a file that uses the subject
        When run_git_diff analyzes base..head
        Then it reports ZERO occurrences for the renamed file -- not the whole file's content
        """
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_run(repo, "init", "-q")
            (repo / "a.py").write_text("mode = True\nif mode:\n    pass\n")
            _git_run(repo, "add", "a.py")
            _git_run(repo, "commit", "-q", "-m", "base")
            base = _git_head(repo)

            _git_run(repo, "mv", "a.py", "b.py")
            _git_run(repo, "commit", "-q", "-m", "rename")
            head = _git_head(repo)

            result = crc.run_git_diff(repo, base, head, ["mode"])
            self.assertEqual(len(result.files_analyzed), 1)
            self.assertEqual(result.files_analyzed[0].file, "b.py")
            self.assertEqual(result.files_analyzed[0].occurrences, [])

    def test_rename_with_real_edit_still_finds_the_edit(self):
        """
        Given a rename PLUS a real content edit (a new decision added) in the same commit
        When run_git_diff analyzes base..head
        Then the new decision IS found -- rename detection must not also swallow real edits
        """
        with tempfile.TemporaryDirectory() as d:
            repo = Path(d)
            _git_run(repo, "init", "-q")
            (repo / "a.py").write_text("mode = True\n")
            _git_run(repo, "add", "a.py")
            _git_run(repo, "commit", "-q", "-m", "base")
            base = _git_head(repo)

            _git_run(repo, "mv", "a.py", "b.py")
            (repo / "b.py").write_text("mode = True\nif mode:\n    pass\n")
            _git_run(repo, "add", "-A")
            _git_run(repo, "commit", "-q", "-m", "rename+edit")
            head = _git_head(repo)

            result = crc.run_git_diff(repo, base, head, ["mode"])
            self.assertEqual(result.files_analyzed[0].file, "b.py")
            self.assertTrue(
                any(
                    crc.ROLE_DECISION in o.roles
                    for o in result.files_analyzed[0].occurrences
                )
            )


class TestTestVsProductionAdversarialCases(unittest.TestCase):
    """Edge cases for test-vs-production path classification, including root-context
    forcing."""

    def test_spec_directory_is_test(self):
        self.assertTrue(crc.is_test_path(Path("spec/spec_thing.py")))

    def test_conftest_is_test(self):
        self.assertTrue(crc.is_test_path(Path("src/conftest.py")))

    def test_pointing_tree_at_a_test_subdirectory_forces_test_context(self):
        """
        Given `--tree` pointed directly at a subdirectory that is itself named `test`
        When the root-context check runs
        Then every file under it is forced to test, even one whose relative path (relative to
        THAT root) no longer contains the word "test" at all
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "test" / "unit"
            root.mkdir(parents=True)
            self.assertTrue(crc._root_forces_test_context(root))

    def test_root_not_under_test_directory_does_not_force_test(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "pkg"
            root.mkdir(parents=True)
            self.assertFalse(crc._root_forces_test_context(root))

    def test_distant_unrelated_ancestor_named_test_does_not_force_test(self):
        """
        Given a root whose analysis-relevant path is deeply nested, with "test" appearing only
        as a DISTANT ancestor well outside the bounded trailing window
        When the root-context check runs
        Then it does NOT force test context -- the bound protects against distant,
        unrelated ancestor collisions
        """
        distant = Path(
            "/tmp/test_unrelated_ancestor_name/workspace/scratch/deep/candidate"
        )
        self.assertFalse(crc._root_forces_test_context(distant))

    def test_file_lists_are_printed_in_the_report(self):
        """
        Given a report built from files with a mix of test/production classification
        When printed
        Then both TEST and PRODUCTION file lists appear (not just counts) -- a misfiled tree
        must be visible at a glance
        """
        prod_fa = crc.FileAnalysis(
            file="pkg/a.py",
            parse_error=None,
            occurrences=[],
            string_mentions=[],
            is_test=False,
        )
        test_fa = crc.FileAnalysis(
            file="spec/a_spec.py",
            parse_error=None,
            occurrences=[],
            string_mentions=[],
            is_test=True,
        )
        result = crc.AnalysisResult(
            mode="unit-test",
            subjects=["mode"],
            files_analyzed=[prod_fa, test_fa],
            parse_failures=[],
            removed_files=[],
            closure=crc.compute_symbol_closure(
                {}, ["mode"], crc.DEFAULT_CLOSURE_HOP_LIMIT
            ),
        )
        report = crc.build_report(result)
        self.assertEqual(report["test_files"], ["spec/a_spec.py"])
        self.assertEqual(report["production_files"], ["pkg/a.py"])


class TestFileReadRobustness(unittest.TestCase):
    """Regression: a broken symlink, permission-denied file, `*.py`-named directory, or
    non-UTF-8 file with a PEP 263 cookie used to raise an uncaught exception aborting the whole
    run; each must now degrade to a named `parse_failures` entry."""

    def test_broken_symlink_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "broken.py").symlink_to(root / "does_not_exist.py")
            result = crc.run_single_tree(root, ["mode"])
            self.assertEqual(len(result.parse_failures), 1)
            self.assertIn("broken.py", result.parse_failures[0])

    def test_permission_denied_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            target = root / "secret.py"
            target.write_text("mode = True\n")
            target.chmod(0o000)
            try:
                result = crc.run_single_tree(root, ["mode"])
            finally:
                target.chmod(0o644)
            self.assertEqual(len(result.parse_failures), 1)
            self.assertIn("secret.py", result.parse_failures[0])

    def test_directory_named_dot_py_is_reported_not_crashed(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "weird.py").mkdir()
            result = crc.run_single_tree(root, ["mode"])
            self.assertEqual(len(result.parse_failures), 1)
            self.assertIn("weird.py", result.parse_failures[0])

    def test_latin1_file_with_pep263_cookie_parses_correctly(self):
        """
        Given a file declaring `# -*- coding: latin-1 -*-` and actually encoded as latin-1
        (valid Python, per PEP 263)
        When analyzed
        Then it parses successfully (no parse failure) and the subject inside it is found --
        the naive `errors="surrogateescape"` UTF-8 read used to crash `ast.parse` on this
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            text = "# -*- coding: latin-1 -*-\nmode = True  # caf\xe9\nif mode:\n    pass\n"
            (root / "latin1.py").write_bytes(text.encode("latin-1"))
            result = crc.run_single_tree(root, ["mode"])
            self.assertEqual(result.parse_failures, [])
            fa = result.files_analyzed[0]
            self.assertTrue(any(crc.ROLE_DECISION in o.roles for o in fa.occurrences))

    def test_utf8_bom_file_parses_correctly(self):
        """
        Given a valid Python file with a UTF-8 byte-order-mark
        When analyzed
        Then it parses successfully (no false parse failure)
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "bom.py").write_bytes(
                b"\xef\xbb\xbfmode = True\nif mode:\n    pass\n"
            )
            result = crc.run_single_tree(root, ["mode"])
            self.assertEqual(result.parse_failures, [])


class TestSymlinkedDirectoryTraversal(unittest.TestCase):
    """Regression: `Path.rglob` defaults `recurse_symlinks=False` on Python 3.13+, so a `*.py`
    file reachable only through a symlinked directory used to be silently absent from every
    bucket, including `parse_failures`."""

    def test_file_behind_symlinked_directory_is_discovered(self):
        """
        Given a tree containing a symlink to a directory that holds a `*.py` file
        When discover_python_files walks the tree
        Then the file behind the symlink IS found
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            real_pkg = root.parent / f"{root.name}_real_pkg"
            real_pkg.mkdir()
            (real_pkg / "a.py").write_text("mode = True\n")
            try:
                (root / "linked_pkg").symlink_to(real_pkg, target_is_directory=True)
                found = crc.discover_python_files(root)
                self.assertIn(Path("linked_pkg/a.py"), found)
            finally:
                shutil.rmtree(real_pkg, ignore_errors=True)

    def test_self_referential_symlink_does_not_hang(self):
        """
        Given a directory containing a symlink to itself (a cycle)
        When discover_python_files walks the tree
        Then it terminates (does not hang) and still finds the real file at least once
        """
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "a.py").write_text("mode = True\n")
            (root / "self_link").symlink_to(root, target_is_directory=True)
            found = crc.discover_python_files(root)
            self.assertIn(Path("a.py"), found)


if __name__ == "__main__":
    unittest.main()
