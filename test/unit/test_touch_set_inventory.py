"""Tests for ``tools/touch_set_inventory.py`` (TOO-45 M2)."""

import ast
import inspect
import tempfile
import unittest
from pathlib import Path

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
            self.assertNotIn("bad.py", locations)


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
            self.assertEqual(len(result.valid_locations), 4)
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
            exit_code = tsi.main(
                ["--tree", str(root), "--validate-predictions", str(preds_path)]
            )
            self.assertEqual(exit_code, 0)

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
            exit_code = tsi.main(
                ["--tree", str(root), "--validate-predictions", str(preds_path)]
            )
            self.assertNotEqual(exit_code, 0)

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
            exit_code = tsi.main(
                ["--tree", str(root), "--validate-predictions", str(preds_path)]
            )
            self.assertEqual(exit_code, 0)


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
        Then only ONE of the two paths is returned -- the module is not inventoried twice
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ok.py").write_text("x = 1\n")
            (root / "alias.py").symlink_to(root / "ok.py")
            found = tsi.discover_python_files(root)
            self.assertEqual(len(found), 1)


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

    def test_load_gitignore_patterns_only_reads_the_local_file_no_other_io(self):
        """
        Given a tree with a .gitignore file
        When _load_gitignore_patterns runs
        Then it returns patterns derived purely from that file's own text content -- functional
        confirmation that the git subprocess route was not silently reintroduced, complementing
        the static "no subprocess import" check above
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".gitignore").write_text("tmp/\nlogs\n# a comment\n\n!kept.py\n")
            patterns = tsi._load_gitignore_patterns(root)
            self.assertEqual(patterns, ["tmp/", "logs"])


if __name__ == "__main__":
    unittest.main()
