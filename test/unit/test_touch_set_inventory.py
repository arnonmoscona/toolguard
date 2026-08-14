"""Tests for ``tools/touch_set_inventory.py`` (TOO-45 M2)."""

import ast
import contextlib
import inspect
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools import touch_set_inventory as tsi


class TestModuleDocstring(unittest.TestCase):
    """Requirement: emit the first line of the module's own docstring, or an explicit None."""

    def test_single_line_module_docstring_reported_verbatim(self):
        """
        Given a module whose docstring is exactly one line
        When the module is analyzed
        Then that line is reported as the module's docstring_first_line
        """
        entry, error = tsi.build_module_entry(
            '"""A tiny module."""\n\nX = 1\n', "mod.py", is_test=False
        )
        self.assertIsNone(error)
        self.assertEqual(entry.docstring_first_line, "A tiny module.")

    def test_multi_line_module_docstring_truncated_to_first_line(self):
        """
        Given a module docstring spanning several lines
        When the module is analyzed
        Then only the first physical line is reported
        """
        source = '"""First line.\n\nMore detail that must not appear.\n"""\n'
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        self.assertEqual(entry.docstring_first_line, "First line.")

    def test_missing_module_docstring_is_none_not_empty_string(self):
        """
        Given a module with no docstring at all
        When the module is analyzed
        Then docstring_first_line is None (never the empty string standing in for "absent")
        """
        entry, _ = tsi.build_module_entry("X = 1\n", "mod.py", is_test=False)
        self.assertIsNone(entry.docstring_first_line)


class TestPublicSymbolFiltering(unittest.TestCase):
    """Requirement: public top-level functions/classes only -- not private, not nested,
    not methods, not module-level variables."""

    def test_leading_underscore_symbol_excluded(self):
        """
        Given a top-level function and a top-level function prefixed with an underscore
        When the module is analyzed
        Then only the public one appears in public_symbols
        """
        source = "def public_fn():\n    pass\n\n\ndef _private_fn():\n    pass\n"
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        names = [s.name for s in entry.public_symbols]
        self.assertEqual(names, ["public_fn"])

    def test_nested_function_and_method_not_reported(self):
        """
        Given a top-level class with a method, and a top-level function with a nested helper
        When the module is analyzed
        Then only the two TOP-LEVEL symbols appear -- the method and the nested function do not
        """
        source = (
            "class Foo:\n"
            "    def method(self):\n"
            "        pass\n"
            "\n\n"
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
            "    return inner\n"
        )
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        names = sorted(s.name for s in entry.public_symbols)
        self.assertEqual(names, ["Foo", "outer"])

    def test_module_level_variable_not_reported_as_a_symbol(self):
        """
        Given a module-level constant assignment and a top-level function
        When the module is analyzed
        Then only the function appears -- variables are not "functions and classes"
        """
        source = "CONST = 42\n\n\ndef fn():\n    pass\n"
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        names = [s.name for s in entry.public_symbols]
        self.assertEqual(names, ["fn"])

    def test_async_function_reported_with_its_own_kind(self):
        """
        Given a top-level async function
        When the module is analyzed
        Then it is reported with kind "async function", distinct from a plain function
        """
        source = "async def fetch():\n    pass\n"
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        self.assertEqual(entry.public_symbols[0].kind, "async function")

    def test_symbol_docstring_first_line_captured_and_missing_is_none(self):
        """
        Given one function with a docstring and one function without
        When the module is analyzed
        Then the first has its docstring's first line and the second has None
        """
        source = (
            "def documented():\n"
            '    """Does the thing.\n\n    More detail.\n    """\n'
            "    pass\n\n\n"
            "def undocumented():\n"
            "    pass\n"
        )
        entry, _ = tsi.build_module_entry(source, "mod.py", is_test=False)
        by_name = {s.name: s for s in entry.public_symbols}
        self.assertEqual(by_name["documented"].docstring_first_line, "Does the thing.")
        self.assertIsNone(by_name["undocumented"].docstring_first_line)


class TestParseFailureHandling(unittest.TestCase):
    """Requirement: a file that fails to parse is named explicitly, never silently dropped
    into an empty inventory."""

    def test_syntax_error_reported_not_raised_and_no_entry_produced(self):
        """
        Given source text with a syntax error
        When the module is analyzed
        Then build_module_entry returns (None, message) instead of raising, and the message
        names the file
        """
        entry, error = tsi.build_module_entry(
            "def broken(:\n", "broken.py", is_test=False
        )
        self.assertIsNone(entry)
        self.assertIn("broken.py", error)


class TestLineCountAndIsTest(unittest.TestCase):
    def test_line_count_matches_source_line_count(self):
        """
        Given a 3-line source file
        When analyzed
        Then line_count is exactly 3
        """
        entry, _ = tsi.build_module_entry(
            "a = 1\nb = 2\nc = 3\n", "mod.py", is_test=False
        )
        self.assertEqual(entry.line_count, 3)

    def test_is_test_flag_passed_through_unchanged(self):
        """
        Given is_test=True passed to build_module_entry
        When analyzed
        Then the resulting entry carries is_test=True
        """
        entry, _ = tsi.build_module_entry("x = 1\n", "test_mod.py", is_test=True)
        self.assertTrue(entry.is_test)


class TestRunInventoryNeverSeesADiff(unittest.TestCase):
    """The hard rule: run_inventory takes exactly one tree and nothing else."""

    def test_run_inventory_signature_takes_a_single_tree_only(self):
        """
        Given the run_inventory function
        When its signature is inspected
        Then it accepts exactly one positional tree-root argument -- no second tree, no VCS
        revision parameters exist for it to accidentally be passed
        """
        params = list(inspect.signature(tsi.run_inventory).parameters)
        self.assertEqual(params, ["tree_root"])

    def test_run_inventory_on_small_tree_reports_every_module(self):
        """
        Given a tiny on-disk tree with two Python files
        When run_inventory analyzes it
        Then both modules appear, sorted by path, with no parse failures
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "b_mod.py").write_text('"""B module."""\n\ndef b_fn():\n    pass\n')
            (root / "a_mod.py").write_text('"""A module."""\n')
            result = tsi.run_inventory(root)
            self.assertEqual(result.parse_failures, [])
            self.assertEqual([m.path for m in result.modules], ["a_mod.py", "b_mod.py"])

    def test_run_inventory_names_unparseable_file_explicitly(self):
        """
        Given a tree with one valid file and one file with a syntax error
        When run_inventory analyzes it
        Then the valid file is reported, the broken one appears in parse_failures (not
        silently dropped with no trace), and only the valid module appears in modules
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.py").write_text("x = 1\n")
            (root / "bad.py").write_text("def broken(:\n")
            result = tsi.run_inventory(root)
            self.assertEqual([m.path for m in result.modules], ["good.py"])
            self.assertEqual(len(result.parse_failures), 1)
            self.assertIn("bad.py", result.parse_failures[0])


class TestBuildReportAndTextOutput(unittest.TestCase):
    """The report dict feeds both --json and the text printer; exercised at the dict level."""

    def test_report_json_shape_carries_every_field(self):
        """
        Given a small inventory result
        When build_report is called
        Then the resulting dict has the documented top-level keys and a per-module entry with
        all four required fields
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text(
                '"""A module."""\n\n\ndef public_fn():\n    """Do a thing."""\n    pass\n'
            )
            result = tsi.run_inventory(root)
            report = tsi.build_report(result)
            self.assertEqual(report["modules_found"], 1)
            self.assertEqual(report["parse_failures"], [])
            module = report["modules"][0]
            self.assertEqual(module["path"], "mod.py")
            self.assertEqual(module["docstring_first_line"], "A module.")
            self.assertEqual(len(module["public_symbols"]), 1)
            self.assertEqual(module["public_symbols"][0]["name"], "public_fn")


class TestCollectQualnames(unittest.TestCase):
    """The broader (any-nesting, any-visibility) symbol collector used by
    --validate-predictions, not the restricted set the plain inventory shows."""

    def test_private_and_method_and_nested_all_collected(self):
        """
        Given a module with a private top-level function, a class with a method, and a
        function nested inside another function
        When qualnames are collected
        Then all four are present (public_fn, _private_fn, Outer.method, outer.inner) -- none
        of the visibility/nesting restrictions the plain inventory applies are in effect here
        """
        source = (
            "def public_fn():\n"
            "    pass\n\n\n"
            "def _private_fn():\n"
            "    pass\n\n\n"
            "class Outer:\n"
            "    def method(self):\n"
            "        pass\n\n\n"
            "def outer():\n"
            "    def inner():\n"
            "        pass\n"
            "    return inner\n"
        )
        tree = ast.parse(source)
        qualnames = set(tsi._collect_qualnames(tree))
        self.assertEqual(
            qualnames,
            {
                "public_fn",
                "_private_fn",
                "Outer",
                "Outer.method",
                "outer",
                "outer.inner",
            },
        )


class TestAllLocationsForValidation(unittest.TestCase):
    def test_bare_path_and_qualnames_both_present(self):
        """
        Given a small on-disk tree
        When all_locations_for_validation runs
        Then the bare module path AND every function/class qualname (dotted with '::') are in
        the returned set
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text("def _helper():\n    pass\n")
            locations, parse_failures = tsi.all_locations_for_validation(root)
            self.assertEqual(parse_failures, [])
            self.assertIn("mod.py", locations)
            self.assertIn("mod.py::_helper", locations)

    def test_unparseable_file_named_in_parse_failures_and_contributes_no_locations(
        self,
    ):
        """
        Given a tree with one broken file
        When all_locations_for_validation runs
        Then the broken file is named explicitly in parse_failures and contributes zero
        locations (not silently absent from the failures list)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("def broken(:\n")
            locations, parse_failures = tsi.all_locations_for_validation(root)
            self.assertEqual(len(parse_failures), 1)
            self.assertIn("bad.py", parse_failures[0])
            # assertNotIn on a set is exact membership, so it cannot see "bad.py::fn"
            # sneaking in; assert the file contributes NOTHING under any suffix.
            self.assertEqual([loc for loc in locations if loc.startswith("bad.py")], [])


class TestLoadPredictionLocations(unittest.TestCase):
    def test_valid_file_extracts_locations(self):
        """
        Given a well-formed predictions-shaped file
        When loaded
        Then every location string is extracted with zero errors
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text(
                '[{"location": "mod.py::fn", "kind": "decide"}, {"location": "mod.py"}]'
            )
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(errors, [])
            self.assertEqual(locations, ["mod.py::fn", "mod.py"])

    def test_missing_location_is_a_fatal_error(self):
        """
        Given an entry with no 'location' key
        When loaded
        Then a fatal error is reported and no locations are returned
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text('[{"kind": "decide"}]')
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(locations, [])
            self.assertTrue(errors)

    def test_malformed_json_is_a_fatal_error_not_a_crash(self):
        """
        Given a file that is not valid JSON
        When loaded
        Then a fatal error is reported instead of raising
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text("{not json")
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(locations, [])
            self.assertTrue(errors)


class TestValidatePredictions(unittest.TestCase):
    """End-to-end tests for --validate-predictions -- the mechanism that lets a predictor catch
    a guessed nonexistent location BEFORE it ever reaches the tree-agnostic scorer."""

    def _make_tree(self, tmp: str) -> Path:
        root = Path(tmp)
        (root / "mod.py").write_text(
            "def public_fn():\n"
            "    pass\n\n\n"
            "def _private_helper():\n"
            "    pass\n\n\n"
            "class Foo:\n"
            "    def method(self):\n"
            "        pass\n"
        )
        return root

    def test_public_private_method_and_module_level_all_valid(self):
        """
        Given predictions naming a public function, a PRIVATE function, a METHOD, and the bare
        module path
        When validated against the tree
        Then all four are valid -- existence-checking is deliberately broader than what the
        blind predictor was shown by name
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text(
                '[{"location": "mod.py::public_fn", "kind": "decide"}, '
                '{"location": "mod.py::_private_helper", "kind": "record"}, '
                '{"location": "mod.py::Foo.method", "kind": "transport"}, '
                '{"location": "mod.py", "kind": "record"}]'
            )
            result, errors = tsi.validate_predictions(root, preds_path)
            self.assertEqual(errors, [])
            # The exact set, sorted -- a bare count of 4 cannot see a location being
            # replaced by another real one, nor whether valid_locations is sorted.
            self.assertEqual(
                result.valid_locations,
                [
                    "mod.py",
                    "mod.py::Foo.method",
                    "mod.py::_private_helper",
                    "mod.py::public_fn",
                ],
            )
            self.assertEqual(result.invalid_locations, [])

    def test_guessed_name_reported_invalid(self):
        """
        Given a prediction naming a function that does not exist anywhere in the tree
        When validated
        Then it appears in invalid_locations, distinctly from the valid ones
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text(
                '[{"location": "mod.py::totally_made_up_fn", "kind": "decide"}]'
            )
            result, errors = tsi.validate_predictions(root, preds_path)
            self.assertEqual(errors, [])
            self.assertEqual(result.invalid_locations, ["mod.py::totally_made_up_fn"])
            self.assertEqual(result.valid_locations, [])

    def test_duplicate_prediction_reported_not_fatal(self):
        """
        Given the same location predicted twice
        When validated
        Then it is reported in duplicate_predictions with its count, and validation still
        completes (not a fatal error at this stage)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text(
                '[{"location": "mod.py::public_fn", "kind": "decide"}, '
                '{"location": "mod.py::public_fn", "kind": "record"}]'
            )
            result, errors = tsi.validate_predictions(root, preds_path)
            self.assertEqual(errors, [])
            self.assertEqual(result.duplicate_predictions, {"mod.py::public_fn": 2})

    def test_malformed_predictions_file_returns_none_result_with_errors(self):
        """
        Given a predictions file that fails to load at all
        When validated
        Then result is None and the load errors are returned, rather than a half-populated
        result
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text("{not json")
            result, errors = tsi.validate_predictions(root, preds_path)
            self.assertIsNone(result)
            self.assertTrue(errors)

    def test_main_exits_zero_even_when_a_prediction_is_invalid(self):
        """
        Given a predictions file with one invalid location
        When main() runs in --validate-predictions mode
        Then it STILL exits 0 -- D5: 'invalid' is advisory, not a hard gate, since a static
        walk cannot see every legitimate location a diff judge could cite (runtime names,
        lambda-assigned names) and the false-negative cost of gating was found to exceed the
        false-positive cost of not gating. Only a malformed FILE (bad JSON, missing required
        fields) still exits non-zero -- see the next test.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text('[{"location": "mod.py::nope", "kind": "decide"}]')
            with contextlib.redirect_stdout(io.StringIO()) as out:
                exit_code = tsi.main(
                    ["--tree", str(root), "--validate-predictions", str(preds_path)]
                )
            self.assertEqual(exit_code, 0)
            # The advisory report must still NAME the invalid location -- exiting 0 is
            # only defensible because a human is expected to read it.
            self.assertIn("mod.py::nope", out.getvalue())

    def test_main_exits_nonzero_when_the_predictions_file_itself_is_malformed(self):
        """
        Given a predictions file that is not valid JSON at all
        When main() runs in --validate-predictions mode
        Then it exits non-zero -- a malformed FILE is still a hard failure, distinct from an
        individual invalid LOCATION (which is advisory, see the previous test)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text("{not json")
            with (
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()) as err,
            ):
                exit_code = tsi.main(
                    ["--tree", str(root), "--validate-predictions", str(preds_path)]
                )
            self.assertEqual(exit_code, 2)
            self.assertIn("is invalid", err.getvalue())

    def test_main_exits_zero_when_all_predictions_valid(self):
        """
        Given a predictions file where every location is real
        When main() runs in --validate-predictions mode
        Then it exits 0
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = self._make_tree(tmp)
            preds_path = root / "preds.json"
            preds_path.write_text(
                '[{"location": "mod.py::public_fn", "kind": "decide"}]'
            )
            with contextlib.redirect_stdout(io.StringIO()) as out:
                exit_code = tsi.main(
                    ["--tree", str(root), "--validate-predictions", str(preds_path)]
                )
            self.assertEqual(exit_code, 0)
            self.assertIn("valid (found in tree): 1", out.getvalue())
            self.assertIn("invalid (NOT found in tree): 0", out.getvalue())


class TestD5WidenedQualnameCollection(unittest.TestCase):
    """D5: a dataclass field, a class attribute, or a module constant is a location a diff
    judge would legitimately cite -- the validator must not reject it."""

    def test_module_level_annotated_assignment_collected(self):
        """
        Given a module-level `NAME: type = value` statement
        When qualnames are collected
        Then the bare name is present
        """
        tree = ast.parse("CONST: int = 1\n")
        self.assertIn("CONST", tsi._collect_qualnames(tree))

    def test_module_level_plain_assignment_collected(self):
        """
        Given a module-level `NAME = value` statement
        When qualnames are collected
        Then the bare name is present
        """
        tree = ast.parse("CONST = 1\n")
        self.assertIn("CONST", tsi._collect_qualnames(tree))

    def test_class_level_dataclass_field_collected(self):
        """
        Given a dataclass-shaped class with an annotated field
        When qualnames are collected
        Then "ClassName.field" is present -- this is the exact shape (RuleEntry.pattern) the
        adversarial review found rejected by the pre-fix validator
        """
        source = (
            "class RuleEntry:\n    pattern: str\n    allow_in_auto_mode: bool = False\n"
        )
        tree = ast.parse(source)
        qualnames = set(tsi._collect_qualnames(tree))
        self.assertIn("RuleEntry.pattern", qualnames)
        self.assertIn("RuleEntry.allow_in_auto_mode", qualnames)

    def test_module_level_lambda_assignment_collected(self):
        """
        Given a module-level `NAME = lambda: ...` statement
        When qualnames are collected
        Then the bare name is present -- the collector does not care about the assigned VALUE's
        type, only that the target is a plain Name
        """
        tree = ast.parse("handler = lambda: None\n")
        self.assertIn("handler", tsi._collect_qualnames(tree))

    def test_function_local_assignment_is_not_collected(self):
        """
        Given a function-local variable assignment
        When qualnames are collected
        Then it is NOT present -- assignment-target collection is scoped to class/module level
        only, per D5's suggested fix; an arbitrary local variable is not the kind of location
        this check is for
        """
        source = "def fn():\n    local_var = 1\n    return local_var\n"
        tree = ast.parse(source)
        qualnames = set(tsi._collect_qualnames(tree))
        self.assertNotIn("fn.local_var", qualnames)
        self.assertNotIn("local_var", qualnames)

    def test_nested_class_field_collected_with_full_prefix(self):
        """
        Given a class nested inside another class, with its own field
        When qualnames are collected
        Then "Outer.Inner.field" is present with the full dotted prefix
        """
        source = "class Outer:\n    class Inner:\n        field: int\n"
        tree = ast.parse(source)
        self.assertIn("Outer.Inner.field", set(tsi._collect_qualnames(tree)))


class TestNearestLocationSuggestions(unittest.TestCase):
    def test_close_typo_produces_a_suggestion(self):
        """
        Given an invalid location that is a one-character typo of a real one
        When nearest-location suggestions are computed
        Then the real location is suggested
        """
        all_locations = {
            "mod.py::RuleEntry.pattern",
            "mod.py::RuleEntry.allow_in_auto_mode",
        }
        suggestions = tsi._nearest_locations("mod.py::RuleEntry.patern", all_locations)
        self.assertIn("mod.py::RuleEntry.pattern", suggestions)

    def test_wildly_different_name_produces_no_suggestion(self):
        """
        Given an invalid location bearing no resemblance to anything real
        When nearest-location suggestions are computed
        Then the suggestion list is empty rather than a misleading guess
        """
        all_locations = {"mod.py::RuleEntry.pattern"}
        suggestions = tsi._nearest_locations(
            "completely/unrelated.py::Zzz", all_locations
        )
        self.assertEqual(suggestions, [])

    def test_validation_result_carries_suggestions_for_invalid_locations(self):
        """
        Given a predictions file with a near-miss typo of a real location
        When validated end to end
        Then the ValidationResult's suggestions dict names the real location
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text(
                "class RuleEntry:\n    pattern: str\n    allow_in_auto_mode: bool = False\n"
            )
            preds_path = root / "preds.json"
            preds_path.write_text(
                '[{"location": "mod.py::RuleEntry.patern", "kind": "record"}]'
            )
            result, errors = tsi.validate_predictions(root, preds_path)
            self.assertEqual(errors, [])
            self.assertIn("mod.py::RuleEntry.patern", result.suggestions)
            self.assertIn(
                "mod.py::RuleEntry.pattern",
                result.suggestions["mod.py::RuleEntry.patern"],
            )


class TestD11SafeReadText(unittest.TestCase):
    def test_broken_symlink_reported_not_raised(self):
        """
        Given a broken symlink named *.py
        When _safe_read_text reads it
        Then it returns (None, error) instead of raising
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "broken.py"
            broken.symlink_to(root / "does_not_exist.py")
            content, error = tsi._safe_read_text(broken)
            self.assertIsNone(content)
            self.assertIn("broken.py", error)

    def test_directory_named_py_reported_not_raised(self):
        """
        Given a directory whose name matches *.py
        When _safe_read_text reads it
        Then it returns (None, error) instead of raising IsADirectoryError
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            weird = root / "weird.py"
            weird.mkdir()
            content, error = tsi._safe_read_text(weird)
            self.assertIsNone(content)
            self.assertIn("weird.py", error)

    def test_run_inventory_does_not_crash_on_a_broken_symlink(self):
        """
        Given a tree with one good file and one broken symlink named *.py
        When run_inventory runs
        Then it completes without raising, reporting the broken symlink as a parse failure and
        the good file normally
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.py").write_text("x = 1\n")
            (root / "broken.py").symlink_to(root / "does_not_exist.py")
            result = tsi.run_inventory(root)
            self.assertEqual([m.path for m in result.modules], ["good.py"])
            self.assertTrue(any("broken.py" in f for f in result.parse_failures))

    def test_symlinked_module_deduplicated_by_real_path(self):
        """
        Given a real module and a file symlink alias pointing at it
        When discover_python_files runs
        Then only ONE of the two paths is returned, and it is the FIRST in sorted order
        ("alias.py" < "ok.py") -- KNOWN_LIMITATIONS[1] promises which one survives, and
        asserting only the count leaves the surviving identity, and therefore the sort
        that selects it, unpinned
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("x = 1\n")
            (root / "alias.py").symlink_to(root / "ok.py")
            found = tsi.discover_python_files(root)
            self.assertEqual([str(p) for p in found], ["alias.py"])


class TestD12Gitignore(unittest.TestCase):
    def test_gitignored_directory_excluded_from_discovery(self):
        """
        Given a tree with a top-level .gitignore excluding "tmp/", and a *.py file under tmp/
        When discover_python_files runs with the tree's gitignore patterns
        Then the tmp/ file is excluded
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/\n")
            (root / "tmp").mkdir()
            (root / "tmp" / "scratch.py").write_text("x = 1\n")
            (root / "real.py").write_text("y = 1\n")
            patterns = tsi._load_gitignore_patterns(root)
            found = tsi.discover_python_files(root, patterns)
            self.assertEqual([str(p) for p in found], ["real.py"])

    def test_run_inventory_respects_gitignore_end_to_end(self):
        """
        Given the same tree, driven through the real run_inventory entry point
        When the inventory is built
        Then the gitignored file never appears -- this is the D12 leak (a blind predictor must
        never see a filename like tmp/auto-mode/scan_auto_mode.py that hints at the requirement)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/\n")
            (root / "tmp").mkdir()
            (root / "tmp" / "scan_auto_mode.py").write_text(
                '"""Leaks the subject."""\n'
            )
            (root / "real.py").write_text('"""Fine."""\n')
            result = tsi.run_inventory(root)
            self.assertEqual([m.path for m in result.modules], ["real.py"])

    def test_no_gitignore_file_means_nothing_is_excluded_by_it(self):
        """
        Given a tree with no .gitignore file at all
        When patterns are loaded
        Then an empty pattern list is returned (not an error)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.assertEqual(tsi._load_gitignore_patterns(root), [])

    def test_negation_pattern_is_ignored_not_applied(self):
        """
        Given a .gitignore with a negation ("!") line
        When patterns are loaded
        Then the negation line itself is dropped (not supported -- see KNOWN_LIMITATIONS),
        never misapplied as an ordinary exclude pattern
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("!keep_me.py\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, [])

    def test_negation_re_included_file_stays_excluded_a_named_boundary(self):
        """
        Given a .gitignore that excludes "*.py" and then re-includes "!keep.py"
        When discovery runs
        Then keep.py is STILL excluded -- pinning the direction of the documented
        negation gap. Dropping the "!" line means the re-inclusion never happens, so a
        file the repository owner deliberately tracks is hidden from the blind predictor.
        This is a scope boundary named in KNOWN_LIMITATIONS[0], not a defect, but the
        previous test could not show it: with only a negation line present there is
        nothing to re-include, so "patterns == []" holds either way.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("*.py\n!keep.py\n")
            (root / "keep.py").write_text("x = 1\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, ["*.py"])
            self.assertEqual(tsi.discover_python_files(root, patterns), [])

    def test_nested_gitignore_is_not_consulted_a_named_boundary(self):
        """
        Given a nested per-directory .gitignore that would exclude sub/hidden.py
        When discovery runs from the tree root
        Then sub/hidden.py is STILL discovered -- only the root .gitignore is read, per
        KNOWN_LIMITATIONS[0]. Direction of the error: a file the repository owner ignored
        REACHES the blind predictor, which is the leaking direction.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sub").mkdir()
            (root / "sub" / ".gitignore").write_text("hidden.py\n")
            (root / "sub" / "hidden.py").write_text("x = 1\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, [])
            self.assertEqual(
                [str(p) for p in tsi.discover_python_files(root, patterns)],
                ["sub/hidden.py"],
            )

    def test_git_info_exclude_is_not_consulted_a_named_boundary(self):
        """
        Given a repo-config exclude file at .git/info/exclude naming a *.py file
        When patterns are loaded
        Then it is not consulted -- KNOWN_LIMITATIONS[0]. This is also the strongest
        functional evidence that no `git` process is involved: git itself WOULD honour
        this file, so honouring it is only possible by asking git.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git" / "info").mkdir(parents=True)
            (root / ".git" / "info" / "exclude").write_text("hidden.py\n")
            (root / "hidden.py").write_text("x = 1\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, [])
            self.assertEqual(
                [str(p) for p in tsi.discover_python_files(root, patterns)],
                ["hidden.py"],
            )

    def test_pattern_lines_are_whitespace_stripped(self):
        """
        Given .gitignore lines carrying leading and trailing whitespace
        When patterns are loaded
        Then the stored patterns are stripped -- an unstripped "tmp/ " would never match
        any path component and the exclusion would silently stop working
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/ \n  logs\n\t.cache\t\n")
            self.assertEqual(
                tsi._load_gitignore_patterns(root), ["tmp/", "logs", ".cache"]
            )

    def test_only_the_trees_own_gitignore_is_read_never_a_parent_directory(self):
        """
        Given a parent directory with its own .gitignore and a child tree with a
        different one
        When patterns are loaded for the CHILD
        Then only the child's patterns come back -- a positive control that the function
        reads exactly one named file, rather than cascading upward or asking git (either
        of which would surface the parent's pattern)
        """
        with tempfile.TemporaryDirectory() as tmp:
            parent = Path(tmp)
            (parent / ".gitignore").write_text("parent_only/\n")
            child = parent / "child"
            child.mkdir()
            (child / ".gitignore").write_text("child_only/\n")
            self.assertEqual(tsi._load_gitignore_patterns(child), ["child_only/"])

    def test_module_never_imports_subprocess(self):
        """
        Given this whole module
        When its namespace is inspected for a bound "subprocess" name
        Then none is found -- the blindness guarantee (verified by the adversarial audit's
        addaudithook run: 0 subprocess events) must not be weakened by adding gitignore support.
        A functional check on the module namespace, not a text search of a docstring (which
        legitimately mentions the word "subprocess" while explaining that none is used).
        """
        self.assertNotIn("subprocess", vars(tsi))

    def test_blank_comment_and_negation_lines_are_all_dropped(self):
        """
        Given a .gitignore mixing a directory pattern, a bare name, a comment, a blank
        line and a negation
        When patterns are loaded
        Then only the two real exclude patterns survive, in file order

        (Renamed from ...only_reads_the_local_file_no_other_io: the old Then claimed this
        was "functional confirmation that the git subprocess route was not silently
        reintroduced", which the body never checks -- it only inspects the parsed lines.
        The I/O claim is now carried by tests that can actually fail on it:
        test_git_info_exclude_is_not_consulted_a_named_boundary and
        test_only_the_trees_own_gitignore_is_read_never_a_parent_directory.)
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/\nlogs\n# a comment\n\n!kept.py\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, ["tmp/", "logs"])


class TestExcludedDirNames(unittest.TestCase):
    """EXCLUDED_DIR_NAMES is an unconditional exclusion rule -- it is consulted before
    .gitignore and applies whether or not the tree's owner tracks the directory."""

    def test_every_excluded_dir_name_is_load_bearing(self):
        """
        Given one *.py file under each EXCLUDED_DIR_NAMES directory plus one keeper
        When discovery runs
        Then each excluded directory's file is absent and the keeper is present -- pinning
        every entry individually, so removing any single name from the set fails here
        """
        for name in sorted(tsi.EXCLUDED_DIR_NAMES):
            with self.subTest(excluded_dir=name):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / name).mkdir()
                    (root / name / "m.py").write_text("x = 1\n")
                    (root / "keep.py").write_text("y = 1\n")
                    found = [str(p) for p in tsi.discover_python_files(root, [])]
                    self.assertEqual(
                        found, ["keep.py"], f"{name}/m.py was not excluded"
                    )

    def test_exclusion_applies_at_the_top_level_of_the_tree(self):
        """
        Given an excluded directory sitting directly at the tree root
        When discovery runs
        Then its file is excluded -- the rule scans every directory component, not only
        the nested ones
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "build").mkdir()
            (root / "build" / "top.py").write_text("x = 1\n")
            (root / "a" / "build").mkdir(parents=True)
            (root / "a" / "build" / "nested.py").write_text("x = 1\n")
            self.assertEqual(tsi.discover_python_files(root, []), [])

    def test_the_rule_reads_directory_components_only_never_the_filename(self):
        """
        Given an excluded name that a FILENAME could actually match ("scratch.py"), and a
        tree holding both a file called scratch.py and a directory of the same name
        When discovery runs
        Then the directory's contents are excluded and the FILE is still discovered --
        the rule scans relpath.parts[:-1], so widening it to relpath.parts would lose a
        legitimately-named module.

        EXCLUDED_DIR_NAMES is patched because no real entry ends in ".py": with the
        shipped set the filename half of this rule is unreachable, so a fixture built
        from real entries (build.py, dist.py) cannot produce the negative case and the
        assertion cannot fail. The two assertions below are the control: the first fails
        if the patch is not consulted, the second if the filename is scanned.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scratch.py").write_text("x = 1\n")
            (root / "keep.py").write_text("y = 1\n")
            with patch.object(tsi, "EXCLUDED_DIR_NAMES", {"scratch.py"}):
                found = [str(p) for p in tsi.discover_python_files(root, [])]
            self.assertEqual(found, ["keep.py", "scratch.py"])

    def test_a_directory_matching_an_excluded_name_hides_its_contents(self):
        """
        Given a patched excluded name and a DIRECTORY bearing it
        When discovery runs with and without the patch
        Then the file INSIDE it disappears while the directory entry itself stays -- the
        two runs differ, which is the control proving the patch is consulted rather than
        silently ignored.

        Note the third entry in the unpatched run: rglob("*.py") matches the DIRECTORY
        named scratch.py as well, and the exclusion rule cannot drop it because a
        top-level entry has no parent components to scan. It survives discovery and is
        named as a read failure later, by _safe_read_text -- see
        test_directory_named_py_reported_not_raised.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "scratch.py").mkdir()
            (root / "scratch.py" / "inner.py").write_text("x = 1\n")
            (root / "keep.py").write_text("y = 1\n")
            unpatched = [str(p) for p in tsi.discover_python_files(root, [])]
            with patch.object(tsi, "EXCLUDED_DIR_NAMES", {"scratch.py"}):
                patched = [str(p) for p in tsi.discover_python_files(root, [])]
            self.assertEqual(
                unpatched, ["keep.py", "scratch.py", "scratch.py/inner.py"]
            )
            self.assertEqual(patched, ["keep.py", "scratch.py"])

    def test_excluded_directories_are_dropped_with_no_trace_in_the_report(self):
        """
        Given a tree whose only modules live under an excluded directory
        When the inventory is built
        Then modules is empty AND parse_failures is empty -- the report is byte-identical
        to one taken over a genuinely empty tree.

        Pinned as a boundary, not as correct-by-default: a filename can leak the change
        under test to a blind predictor, so dropping it silently is deliberate. But
        KNOWN_LIMITATIONS documents the SYMLINK and GITIGNORE drops and says nothing about
        EXCLUDED_DIR_NAMES, and this is the one rule that ignores the tree owner's wishes
        entirely -- a real module under a directory called build/, dist/ or cover/ is
        hidden from the predictor even when git tracks it.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dist").mkdir()
            (root / "dist" / "real_module.py").write_text('"""A tracked module."""\n')
            result = tsi.run_inventory(root)
            self.assertEqual(result.modules, [])
            self.assertEqual(result.parse_failures, [])
            report = tsi.build_report(result)
            self.assertNotIn("real_module", json.dumps(report))


class TestDiscoveryOrderIsAContract(unittest.TestCase):
    def test_discovery_is_sorted_not_filesystem_order(self):
        """
        Given several files created in non-alphabetical order across nested directories
        When discovery runs
        Then the returned paths are in sorted order -- discover_python_files promises
        "Sorted for deterministic output", and the symlink de-duplication rule depends on
        it to decide WHICH of two aliases survives
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("z.py", "m/b.py", "a.py", "m/a.py", "B.py"):
                p = root / rel
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text("x = 1\n")
            found = [str(p) for p in tsi.discover_python_files(root, [])]
            self.assertEqual(found, sorted(found))
            self.assertEqual(found, ["B.py", "a.py", "m/a.py", "m/b.py", "z.py"])

    def test_public_symbols_keep_source_order_not_alphabetical_order(self):
        """
        Given a module defining zeta before alpha
        When it is analyzed
        Then public_symbols is in SOURCE order -- the blind predictor is shown the module
        as written. Nothing sorts this list, and nothing documented it either.
        """
        entry, _ = tsi.build_module_entry(
            "def zeta():\n    pass\n\n\ndef alpha():\n    pass\n",
            "mod.py",
            is_test=False,
        )
        self.assertEqual([s.name for s in entry.public_symbols], ["zeta", "alpha"])


class TestIsTestPath(unittest.TestCase):
    """is_test_path decides the is_test flag the predictor sees on every module. It had
    no test of its own."""

    def test_a_test_or_tests_directory_component_marks_the_path(self):
        """
        Given paths with a "test" or "tests" directory component at any depth
        When classified
        Then all are test code
        """
        for rel in ("test/unit/foo.py", "tests/foo.py", "a/b/test/c/foo.py"):
            with self.subTest(path=rel):
                self.assertTrue(tsi.is_test_path(Path(rel)))

    def test_test_prefix_and_test_suffix_filenames_both_marked(self):
        """
        Given test_foo.py and foo_test.py outside any test directory
        When classified
        Then both are test code -- two separate naming rules, each load-bearing
        """
        self.assertTrue(tsi.is_test_path(Path("pkg/test_foo.py")))
        self.assertTrue(tsi.is_test_path(Path("pkg/foo_test.py")))

    def test_production_paths_are_not_marked(self):
        """
        Given paths that trip none of the rules -- including near-misses whose names
        merely CONTAIN "test" and a directory called "testing"
        When classified
        Then all are production
        """
        for rel in (
            "toolguard/hook.py",
            "pkg/latest.py",
            "pkg/contest.py",
            "testing/foo.py",
            "a/testdata/foo.py",
        ):
            with self.subTest(path=rel):
                self.assertFalse(tsi.is_test_path(Path(rel)))

    def test_the_flag_reaches_the_report(self):
        """
        Given a tree with one test module and one production module
        When the inventory is built
        Then each module's is_test flag in the report matches its path -- the classifier
        is wired through run_inventory, not merely defined
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "test_thing.py").write_text("x = 1\n")
            (root / "thing.py").write_text("y = 1\n")
            report = tsi.build_report(tsi.run_inventory(root))
            flags = {m["path"]: m["is_test"] for m in report["modules"]}
            self.assertEqual(flags, {"test_thing.py": True, "thing.py": False})


class TestGitignoreMatchingSemantics(unittest.TestCase):
    """_is_gitignored's two matching rules, pinned directly. Every case below was
    cross-checked against real `git check-ignore` under an isolated HOME with
    GIT_CONFIG_GLOBAL=/dev/null, so "git agrees" / "git does not" is measured."""

    def test_unanchored_pattern_matches_a_component_at_any_depth(self):
        """
        Given a pattern with no "/" left after the trailing slash is stripped
        When matched
        Then it matches that component at any depth (git agrees)
        """
        self.assertTrue(tsi._is_gitignored(Path("tmp/x.py"), ["tmp/"]))
        self.assertTrue(tsi._is_gitignored(Path("a/b/tmp/deep/x.py"), ["tmp/"]))
        self.assertTrue(tsi._is_gitignored(Path("a/b/c.py"), ["*.py"]))
        self.assertFalse(tsi._is_gitignored(Path("a/b/c.py"), ["tmp"]))

    def test_unanchored_pattern_is_fnmatched_per_component_not_over_the_whole_path(
        self,
    ):
        """
        Given the unanchored globs "b*" and "a*py"
        When matched against "a/bee/c.py"
        Then "b*" matches (the middle component alone) and "a*py" does not -- "a*py"
        spans the whole POSIX path and matches nothing component-wise, so it separates
        per-component matching from whole-path matching in both directions. Real git
        agrees with both answers.
        """
        self.assertTrue(tsi._is_gitignored(Path("a/bee/c.py"), ["b*"]))
        self.assertFalse(tsi._is_gitignored(Path("a/bee/c.py"), ["a*py"]))

    def test_anchored_pattern_matches_the_exact_path_or_a_directory_prefix(self):
        """
        Given a pattern still containing "/", which is treated as anchored to the root
        When matched
        Then it matches the path exactly, or as a directory prefix, and nothing else
        (git agrees on all three)
        """
        self.assertTrue(tsi._is_gitignored(Path("a/b.py"), ["a/b.py"]))
        self.assertTrue(tsi._is_gitignored(Path("a/b/c.py"), ["a/b"]))
        self.assertFalse(tsi._is_gitignored(Path("z/a/b.py"), ["a/b.py"]))

    def test_leading_slash_is_stripped_so_a_root_anchored_pattern_still_matches(self):
        """
        Given git's root-anchoring form "/only-root.py"
        When matched against the relative path "only-root.py"
        Then it matches -- relative paths never carry a leading slash, so without the
        lstrip the pattern could match nothing at all
        """
        self.assertTrue(tsi._is_gitignored(Path("only-root.py"), ["/only-root.py"]))
        self.assertTrue(tsi._is_gitignored(Path("a/b.py"), ["/a"]))

    def test_trailing_slash_is_stripped_before_matching(self):
        """
        Given the directory form "tmp/" and the bare form "tmp"
        When matched
        Then both behave identically -- an unstripped "tmp/" would equal no path
        component and would silently exclude nothing
        """
        self.assertEqual(
            tsi._is_gitignored(Path("tmp/x.py"), ["tmp/"]),
            tsi._is_gitignored(Path("tmp/x.py"), ["tmp"]),
        )
        self.assertTrue(tsi._is_gitignored(Path("tmp/x.py"), ["tmp/"]))

    def test_matching_is_case_sensitive(self):
        """
        Given the pattern "Tmp/" and the path "tmp/x.py"
        When matched
        Then it does not match, as on a case-sensitive filesystem git also does not
        """
        self.assertFalse(tsi._is_gitignored(Path("tmp/x.py"), ["Tmp/"]))


class TestGitignoreWildcardsInsideAnchoredPatternsLeak(unittest.TestCase):
    """RED. A pattern containing BOTH a "/" and a wildcard reaches the anchored branch,
    which compares LITERALLY -- fnmatch is never called -- so the file is discovered and
    shown to the blind predictor.

    This is the leaking direction, and it contradicts the guarantee the tool exists to
    provide: "a blind predictor must never see a filename ... that hints at the
    requirement" (see test_run_inventory_respects_gitignore_end_to_end). It is NOT in
    KNOWN_LIMITATIONS[0], which lists only nested cascading, negation, repo-config
    excludes and the git subprocess -- and tools/touch_set_score.py's own
    KNOWN_LIMITATIONS points at that list for "exactly what subset of gitignore syntax is
    and is not supported", so the gap is inherited by the scorer's published limitations.

    Asserting the CORRECT behaviour rather than pinning the defect: real git excludes
    every path below, measured.
    """

    def test_anchored_glob_excludes_matching_files(self):
        """
        Given a .gitignore containing "docs/*.py"
        When docs/a.py is tested
        Then it is excluded (git excludes it)
        """
        self.assertTrue(tsi._is_gitignored(Path("docs/a.py"), ["docs/*.py"]))

    def test_anchored_star_excludes_directory_contents(self):
        """
        Given a .gitignore containing "zz/*"
        When zz/a.py is tested
        Then it is excluded (git excludes it)
        """
        self.assertTrue(tsi._is_gitignored(Path("zz/a.py"), ["zz/*"]))

    def test_globstar_excludes_at_any_depth(self):
        """
        Given a .gitignore containing "**/x.py"
        When a/b/x.py and a root-level x.py are tested
        Then both are excluded (git excludes both)
        """
        self.assertTrue(tsi._is_gitignored(Path("a/b/x.py"), ["**/x.py"]))
        self.assertTrue(tsi._is_gitignored(Path("x.py"), ["**/x.py"]))

    def test_the_leak_reaches_the_predictor_facing_inventory(self):
        """
        Given a real tree whose .gitignore says "secret/*.py"
        When the inventory is built end to end
        Then the ignored module does not appear -- this is the same D12 leak the module
        already guards for the unanchored form, via the path a real repository is most
        likely to use
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("secret/*.py\n")
            (root / "secret").mkdir()
            (root / "secret" / "scan_auto_mode.py").write_text('"""Leaks."""\n')
            (root / "real.py").write_text('"""Fine."""\n')
            self.assertEqual(
                [m.path for m in tsi.run_inventory(root).modules], ["real.py"]
            )

    def test_the_leak_also_reaches_the_validation_location_set(self):
        """
        Given the same tree
        When all_locations_for_validation runs
        Then the ignored module contributes no locations -- its docstring promises it
        "Honours the tree's own gitignore"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("secret/*.py\n")
            (root / "secret").mkdir()
            (root / "secret" / "leak.py").write_text("def leaked():\n    pass\n")
            locations, _ = tsi.all_locations_for_validation(root)
            self.assertEqual([loc for loc in locations if "leak" in loc], [])


class TestGitignoreIsHonouredByTheValidationPath(unittest.TestCase):
    def test_unanchored_gitignore_excludes_locations_from_validation(self):
        """
        Given a tree whose .gitignore excludes tmp/
        When all_locations_for_validation runs
        Then nothing under tmp/ contributes a location -- run_inventory's gitignore
        handling was tested, this second entry point's was not, and it is the one that
        decides whether a predicted location is "real"
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/\n")
            (root / "tmp").mkdir()
            (root / "tmp" / "hidden.py").write_text("def hidden_fn():\n    pass\n")
            (root / "real.py").write_text("def real_fn():\n    pass\n")
            locations, failures = tsi.all_locations_for_validation(root)
            self.assertEqual(failures, [])
            self.assertEqual(locations, {"real.py", "real.py::real_fn"})


class TestNothingWasExamined(unittest.TestCase):
    """Can it report a complete-looking inventory having examined nothing? Measured at
    both levels, because the two answers differ."""

    def test_cli_rejects_a_nonexistent_tree(self):
        """
        Given --tree pointing at a path that does not exist
        When main runs
        Then it exits 2 and says so on stderr -- it does NOT print a clean report reading
        "modules found: 0", which would be indistinguishable from a genuinely empty tree
        """
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "does-not-exist"
            err = io.StringIO()
            with (
                contextlib.redirect_stderr(err),
                contextlib.redirect_stdout(io.StringIO()) as out,
            ):
                exit_code = tsi.main(["--tree", str(missing)])
            self.assertEqual(exit_code, 2)
            self.assertIn("is not a directory", err.getvalue())
            self.assertNotIn("modules found", out.getvalue())

    def test_cli_rejects_a_regular_file_passed_as_the_tree(self):
        """
        Given --tree pointing at a regular file rather than a directory
        When main runs
        Then it exits 2 -- the guard is is_dir(), not exists()
        """
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "not-a-tree.txt"
            f.write_text("hi\n")
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(tsi.main(["--tree", str(f)]), 2)

    def test_cli_rejects_a_nonexistent_tree_in_validate_predictions_mode_too(self):
        """
        Given a well-formed predictions file and a --tree that does not exist
        When main runs in --validate-predictions mode
        Then it exits 2 rather than reporting every real prediction as invalid, which is
        what the underlying validate_predictions would produce unaided
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            preds.write_text('[{"location": "mod.py::fn"}]')
            with (
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                exit_code = tsi.main(
                    [
                        "--tree",
                        str(Path(tmp) / "nope"),
                        "--validate-predictions",
                        str(preds),
                    ]
                )
            self.assertEqual(exit_code, 2)

    def test_library_run_inventory_on_a_nonexistent_tree_returns_a_clean_empty_result(
        self,
    ):
        """
        Given a tree root that does not exist
        When run_inventory is called DIRECTLY
        Then it returns a result indistinguishable from a genuinely empty tree -- zero
        modules, zero parse_failures, no exception.

        Pinned as a boundary so the CLI guard's importance is visible: nothing inside
        run_inventory notices, so main()'s is_dir() check is the ONLY thing standing
        between a typo'd path and a confident empty report. Any future caller that
        bypasses main() inherits that.
        """
        with tempfile.TemporaryDirectory() as tmp:
            result = tsi.run_inventory(Path(tmp) / "does-not-exist")
            self.assertEqual(result.modules, [])
            self.assertEqual(result.parse_failures, [])

    def test_library_validation_on_a_nonexistent_tree_calls_every_real_location_invalid(
        self,
    ):
        """
        Given a predictions file naming real locations and a tree root that does not exist
        When validate_predictions is called DIRECTLY
        Then every location is reported INVALID with no fatal error and no parse failure

        The same boundary from the other side, and the more dangerous one: "all invalid"
        reads as "the predictor guessed everything", which is a substantive finding, and
        it is produced here by a tree that was never opened.
        """
        with tempfile.TemporaryDirectory() as tmp:
            preds = Path(tmp) / "preds.json"
            preds.write_text('[{"location": "mod.py::fn"}]')
            result, errors = tsi.validate_predictions(Path(tmp) / "nope", preds)
            self.assertEqual(errors, [])
            self.assertEqual(result.invalid_locations, ["mod.py::fn"])
            self.assertEqual(result.parse_failures, [])

    def test_a_fully_gitignored_tree_reports_exactly_like_an_empty_one(self):
        """
        Given a tree whose every *.py file is gitignored, and a genuinely empty tree
        When both are inventoried
        Then the two reports are identical apart from tree_root -- discovery-side drops
        leave no trace, so "modules found: 0" cannot distinguish "nothing here" from
        "everything was filtered".

        Deliberate (a filename can leak the change under test) but absent from
        KNOWN_LIMITATIONS, and load-bearing: touch_set_score consumes this inventory as
        the complete picture of a tree.
        """
        with tempfile.TemporaryDirectory() as tmp:
            filtered = Path(tmp) / "filtered"
            filtered.mkdir()
            (filtered / ".gitignore").write_text("*.py\n")
            (filtered / "a.py").write_text('"""Secret."""\n')
            empty = Path(tmp) / "empty"
            empty.mkdir()
            a = tsi.build_report(tsi.run_inventory(filtered))
            b = tsi.build_report(tsi.run_inventory(empty))
            a.pop("tree_root"), b.pop("tree_root")
            self.assertEqual(a, b)
            self.assertEqual(a["modules_found"], 0)
            self.assertEqual(a["parse_failures"], [])


class TestCliInventoryMode(unittest.TestCase):
    """The plain (non-validation) CLI path had no test at all."""

    def test_json_mode_emits_the_report_as_parseable_json(self):
        """
        Given --json
        When main runs over a small tree
        Then stdout parses as JSON carrying the report's documented keys, rather than the
        human-readable text rendering
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text('"""A module."""\n')
            with contextlib.redirect_stdout(io.StringIO()) as out:
                exit_code = tsi.main(["--tree", str(root), "--json"])
            self.assertEqual(exit_code, 0)
            report = json.loads(out.getvalue())
            self.assertEqual(report["modules_found"], 1)
            self.assertEqual(report["modules"][0]["path"], "mod.py")

    def test_text_mode_is_not_json_and_names_every_module(self):
        """
        Given no --json flag
        When main runs over the same tree
        Then the text report is printed (not JSON) and names the module and its purpose
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text('"""A module."""\n')
            with contextlib.redirect_stdout(io.StringIO()) as out:
                exit_code = tsi.main(["--tree", str(root)])
            text = out.getvalue()
            self.assertEqual(exit_code, 0)
            with self.assertRaises(json.JSONDecodeError):
                json.loads(text)
            self.assertIn("modules found: 1", text)
            self.assertIn("A module.", text)

    def test_text_report_names_parse_failures_and_marks_them_excluded(self):
        """
        Given a tree with one unparseable file
        When the text report is printed
        Then the failure is named in the output and flagged as excluded -- print_text_report
        had no test, so this rendering could have been dropped entirely
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "good.py").write_text("x = 1\n")
            (root / "bad.py").write_text("def broken(:\n")
            with contextlib.redirect_stdout(io.StringIO()) as out:
                tsi.main(["--tree", str(root)])
            text = out.getvalue()
            self.assertIn("bad.py", text)
            self.assertIn("EXCLUDED", text)
            self.assertNotIn("Parse/read failures: none.", text)


class TestBuildReportFields(unittest.TestCase):
    def test_parse_failures_are_carried_into_the_report(self):
        """
        Given an inventory carrying a parse failure
        When the report is built
        Then the failure appears in the report's parse_failures -- the existing shape test
        only ever asserted the EMPTY case, which every alternative also produces
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.py").write_text("def broken(:\n")
            report = tsi.build_report(tsi.run_inventory(root))
            self.assertEqual(len(report["parse_failures"]), 1)
            self.assertIn("bad.py", report["parse_failures"][0])

    def test_known_limitations_are_published_with_the_report(self):
        """
        Given any inventory
        When the report is built
        Then it carries the module's KNOWN_LIMITATIONS -- the report is the only thing a
        consumer of the inventory sees, so the limitations travelling with it is the
        mechanism by which they are honoured
        """
        with tempfile.TemporaryDirectory() as tmp:
            report = tsi.build_report(tsi.run_inventory(Path(tmp)))
            self.assertEqual(report["known_limitations"], tsi.KNOWN_LIMITATIONS)
            self.assertTrue(report["known_limitations"])


class TestBlankDocstringIsAbsent(unittest.TestCase):
    def test_whitespace_only_docstring_is_none_not_empty_string(self):
        """
        Given a module whose docstring is present but entirely whitespace
        When the module is analyzed
        Then docstring_first_line is None -- the existing test covers a MISSING docstring,
        which takes the other early return; a blank one is the case where "" could be
        printed as if it were real content
        """
        entry, _ = tsi.build_module_entry('"""   \n\n  """\nX = 1\n', "mod.py", False)
        self.assertIsNone(entry.docstring_first_line)

    def test_leading_blank_lines_are_skipped_to_the_first_real_line(self):
        """
        Given a docstring whose first physical line is blank
        When the first line is taken
        Then the first NON-BLANK line is returned
        """
        self.assertEqual(tsi._first_line("\n\nlead blank\nmore"), "lead blank")


class TestPredictionFileValidation(unittest.TestCase):
    def test_whitespace_only_location_is_a_fatal_error(self):
        """
        Given an entry whose location is present but blank
        When loaded
        Then it is a fatal error and contributes no location -- a blank string would
        otherwise be checked for existence and reported as an ordinary invalid guess
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text('[{"location": "   ", "kind": "decide"}]')
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(locations, [])
            self.assertEqual(len(errors), 1)

    def test_a_json_object_at_the_top_level_is_rejected(self):
        """
        Given a predictions file holding an object instead of an array
        When loaded
        Then a fatal error naming the actual type is returned, not a silent empty result
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text('{"location": "mod.py"}')
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(locations, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("dict", errors[0])

    def test_a_bare_string_entry_is_rejected_not_crashed_on(self):
        """
        Given an array of bare strings rather than objects
        When loaded
        Then each is a fatal error naming its index -- without the isinstance check this
        raises AttributeError on .get
        """
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "preds.json"
            path.write_text('["mod.py::fn"]')
            locations, errors = tsi.load_prediction_locations(path)
            self.assertEqual(locations, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("#0", errors[0])

    def test_an_unreadable_predictions_file_is_a_fatal_error(self):
        """
        Given a predictions path that does not exist
        When loaded
        Then a fatal error is returned instead of an OSError escaping
        """
        with tempfile.TemporaryDirectory() as tmp:
            locations, errors = tsi.load_prediction_locations(Path(tmp) / "nope.json")
            self.assertEqual(locations, [])
            self.assertEqual(len(errors), 1)
            self.assertIn("cannot read", errors[0])


class TestValidationNormalisationAndDeduplication(unittest.TestCase):
    def test_a_location_predicted_twice_appears_once_among_the_valid(self):
        """
        Given the same real location predicted twice
        When validated
        Then valid_locations contains it exactly once -- the duplicate is reported in
        duplicate_predictions instead. Asserting only the duplicate map leaves the
        de-duplication of the valid list itself unpinned.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text("def fn():\n    pass\n")
            preds = root / "preds.json"
            preds.write_text('[{"location": "mod.py::fn"}, {"location": "mod.py::fn"}]')
            result, _ = tsi.validate_predictions(root, preds)
            self.assertEqual(result.valid_locations, ["mod.py::fn"])
            self.assertEqual(result.duplicate_predictions, {"mod.py::fn": 2})

    def test_predicted_locations_are_normalised_before_the_existence_check(self):
        """
        Given predictions spelling a real location as "./mod.py::fn" and with a Windows
        separator
        When validated
        Then both are VALID -- normalize_location is shared with tools/touch_set_score so
        the two tools cannot drift on what "the same location" means; without it a
        cosmetic spelling difference reads as a guessed name
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pkg").mkdir()
            (root / "pkg" / "mod.py").write_text("def fn():\n    pass\n")
            preds = root / "preds.json"
            preds.write_text(
                '[{"location": "./pkg/mod.py::fn"}, {"location": "pkg\\\\mod.py"}]'
            )
            result, errors = tsi.validate_predictions(root, preds)
            self.assertEqual(errors, [])
            self.assertEqual(result.valid_locations, ["pkg/mod.py", "pkg/mod.py::fn"])
            self.assertEqual(result.invalid_locations, [])

    def test_valid_and_invalid_locations_are_sorted(self):
        """
        Given predictions supplied in non-alphabetical order
        When validated
        Then both result lists are sorted, so a report diff between two runs reflects a
        real change rather than authoring order
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "mod.py").write_text(
                "def a():\n    pass\n\n\ndef b():\n    pass\n\n\ndef c():\n    pass\n"
            )
            preds = root / "preds.json"
            preds.write_text(
                '[{"location": "mod.py::c"}, {"location": "mod.py::a"}, '
                '{"location": "mod.py::b"}, {"location": "mod.py::zz"}, '
                '{"location": "mod.py::ay"}]'
            )
            result, _ = tsi.validate_predictions(root, preds)
            self.assertEqual(
                result.valid_locations, ["mod.py::a", "mod.py::b", "mod.py::c"]
            )
            self.assertEqual(result.invalid_locations, ["mod.py::ay", "mod.py::zz"])


class TestNearestLocationLimit(unittest.TestCase):
    def test_suggestions_are_capped_at_three_by_the_default_limit(self):
        """
        Given many locations all close enough to clear the cutoff
        When suggestions are computed WITHOUT passing limit
        Then at most three come back -- exercising the parameter default by omitting the
        argument, which is the only way a caller reaches it (every call site in the module
        omits it)
        """
        pool = {f"mod.py::handler_a{i}" for i in range(9)}
        suggestions = tsi._nearest_locations("mod.py::handler_a", pool)
        self.assertEqual(len(suggestions), 3)

    def test_an_explicitly_passed_limit_is_honoured(self):
        """
        Given the same pool
        When a limit of 1 is passed explicitly
        Then exactly one suggestion comes back -- without this the parameter could be
        ignored inside the body and only the default would ever be observed
        """
        pool = {f"mod.py::handler_a{i}" for i in range(9)}
        self.assertEqual(
            len(tsi._nearest_locations("mod.py::handler_a", pool, limit=1)), 1
        )


class TestQualnameCollectionEdges(unittest.TestCase):
    def test_an_attribute_assignment_target_is_not_collected(self):
        """
        Given a module-level assignment to an ATTRIBUTE rather than a plain name
        When qualnames are collected
        Then nothing is collected for it -- only ast.Name targets are locations; without
        the guard this reaches for a .id that an ast.Attribute does not have
        """
        tree = ast.parse("obj.attr = 1\nPLAIN = 2\n")
        self.assertEqual(set(tsi._collect_qualnames(tree)), {"PLAIN"})

    def test_a_tuple_unpacking_target_is_not_collected(self):
        """
        Given a module-level tuple-unpacking assignment
        When qualnames are collected
        Then neither name is collected -- the target is an ast.Tuple, not an ast.Name
        """
        tree = ast.parse("A, B = 1, 2\nC = 3\n")
        self.assertEqual(set(tsi._collect_qualnames(tree)), {"C"})

    def test_an_assignment_inside_a_function_body_is_not_collected(self):
        """
        Given a class defined inside a function, carrying a field
        When qualnames are collected
        Then the CLASS body's field IS collected with its full prefix, while the
        function's own local is not -- the rule is "module body and any class body", not
        "never inside a function"
        """
        source = (
            "def fn():\n"
            "    local_var = 1\n"
            "    class Inner:\n"
            "        nested_field: int\n"
        )
        qualnames = set(tsi._collect_qualnames(ast.parse(source)))
        self.assertNotIn("fn.local_var", qualnames)
        self.assertIn("fn.Inner.nested_field", qualnames)


class TestNoMachineStateDependence(unittest.TestCase):
    def test_the_module_binds_no_subprocess_socket_or_os_module(self):
        """
        Given the module namespace
        When inspected for modules that could reach outside the tree
        Then only stdlib parsing/formatting modules are bound -- no subprocess, socket,
        shutil or os. The blindness guarantee is that discovery opens files under the tree
        and nothing else.
        """
        bound = {k for k, v in vars(tsi).items() if inspect.ismodule(v)}
        self.assertEqual(bound & {"subprocess", "socket", "shutil", "os"}, set())
        self.assertEqual(
            bound,
            {"argparse", "ast", "dataclasses", "difflib", "fnmatch", "json", "sys"},
        )

    def test_the_inventory_is_unaffected_by_home_and_by_the_working_directory(self):
        """
        Given the same tree inventoried under the real environment and then under an empty
        HOME, a cleared environment and a foreign working directory
        When the two reports are compared
        Then they are identical -- nothing here reads user config, ambient git config, or
        anything relative to cwd
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "tree"
            root.mkdir()
            (root / ".gitignore").write_text("tmp/\n")
            (root / "tmp").mkdir()
            (root / "tmp" / "hidden.py").write_text("x = 1\n")
            (root / "mod.py").write_text('"""A module."""\n')
            baseline = tsi.build_report(tsi.run_inventory(root))

            hostile_home = Path(tmp) / "hostile-home"
            hostile_home.mkdir()
            (hostile_home / ".gitignore").write_text("mod.py\n")
            original_cwd = os.getcwd()
            try:
                os.chdir(tmp)
                with patch.dict(
                    os.environ,
                    {"HOME": str(hostile_home), "GIT_CONFIG_GLOBAL": "/dev/null"},
                    clear=True,
                ):
                    under_hostile = tsi.build_report(tsi.run_inventory(root))
            finally:
                os.chdir(original_cwd)

            self.assertEqual(baseline, under_hostile)
            self.assertEqual(baseline["modules_found"], 1)


if __name__ == "__main__":
    unittest.main()
