"""
Architectural invariant tests for toolguard's module layering.

These are static-structure tests, not behaviour tests: they parse the source
rather than execute it, so they catch a class of regression the functional
suite provably cannot. The two motivating cases, both real:

1. **Layering / circular imports.** TOO-19 had to move ``Issue`` into
   ``toolguard.issues`` and ``RuleEntry`` into ``toolguard.rule_entry``
   precisely because ``config.py`` imports ``config_validation``, so neither
   could host a type both needed. The usual "fix" for that pressure is a
   function-level import, which the project bans outright. Nothing but this
   test stops the layering from silently regressing back.

2. **Re-export identity.** ``config.py`` re-exports the moved types so its ~69
   existing import sites keep working. If a class were ever accidentally left
   defined in BOTH modules, every functional test would still pass while
   ``isinstance()`` silently failed across the module boundary -- the nastiest
   possible outcome of a move refactor, and invisible to behaviour tests.

Adding a module to a layer below ``config`` is expected and fine; adding an
import that points back UP a layer is what these tests exist to reject.
"""

import ast
import unittest
from pathlib import Path

from toolguard import config, config_types, issues, rule_entry

TOOLGUARD_ROOT = Path(config.__file__).parent

#: Allowed toolguard-internal imports per leaf module, lowest layer first.
#: A module may import from any layer strictly BELOW its own, never above.
#: ``config.py`` itself is the top layer and is deliberately unconstrained here.
LAYERS = (
    ("toolguard.issues", frozenset()),
    ("toolguard.config_write_guard", frozenset()),
    ("toolguard.toml_scan", frozenset()),
    ("toolguard.rule_entry", frozenset({"toolguard.issues"})),
    (
        "toolguard.rule_sort",
        frozenset({"toolguard.rule_entry", "toolguard.toml_scan"}),
    ),
    (
        "toolguard.config_types",
        frozenset({"toolguard.issues", "toolguard.rule_entry"}),
    ),
    (
        # TOO-45 D1a review debt (item B): the module's own docstring claims
        # it never imports toolguard.config -- that claim is the entire
        # justification for extracting it out of config.py, and nothing
        # enforced it until this entry was added (a reviewer added the
        # forbidden import and the suite stayed green).
        "toolguard.permission_resolution",
        frozenset({"toolguard.config_types"}),
    ),
)

#: Types that live in ``config_types`` and are re-exported by ``config``.
RE_EXPORTED_TYPES = (
    "Provenance",
    "ConfigLayer",
    "ToolPatternLayer",
    "TakeoverEnabledConflict",
    "TakeoverConfig",
    "ConflictOverride",
    "RuntimeVerdict",
)

#: TOO-45: this used to be GRANDFATHERED_LOCAL_IMPORTS, a three-entry allowance
#: dating from TOO-19. The ratchet has reached zero, so it is gone. One of the
#: three (hook -> tools.decision) was a genuine circular-import escape and
#: carried the PLC0415 suppression marker the convention always called for --
#: R6-S2 removed it entirely (not just relocated the marker) by moving
#: ``decide()`` into ``toolguard.api``, the layer both ``hook`` (runtime) and
#: ``tools.decision`` (now a re-export) are allowed to import from downward,
#: so the local import is gone along with the layer violation it existed to
#: paper over. The second (auto_migrate -> scripts.migrate_permissions) was
#: resolved by R5b: the migration logic that both modules needed moved to
#: toolguard.permission_migration, a module neither of them forms a cycle
#: with, so auto_migrate now imports it as a normal top-level import and the
#: local import + marker are gone entirely, not just relocated. The third --
#: ("log_writer.py", "json") -- NO LONGER EXISTED: the test had been carrying
#: a dead entry, which is why hand-maintained lists of known exceptions are a
#: liability.


def _module_imports(path: Path) -> set:
    """
    Return every module name imported by a file via a real import statement.

    Parses rather than greps: several modules here MENTION import lines such as
    ``from toolguard.config import Issue`` inside explanatory docstrings, which
    naive text matching reports as real imports (this exact false positive was
    hit while developing these tests).

    Args:
        path: Python source file to inspect.

    Returns:
        Set of imported module names.
    """
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _local_imports(path: Path):
    """
    Find function/method-level (indented) imports, ignoring documented ones.

    An import carrying ``# noqa: PLC0415`` is treated as the project's
    documented-and-approved circular-dependency exception and skipped.

    Args:
        path: Python source file to inspect.

    Returns:
        List of ``(module_name, lineno)`` for undocumented local imports.
    """
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)

    # Collect import nodes that sit inside ANY function body. Walking each
    # FunctionDef separately would visit a nested function's imports once per
    # enclosing function and report them N times; keying on node identity
    # makes the pass idempotent regardless of nesting depth.
    inside_function = {}
    for parent in ast.walk(tree):
        if not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(parent):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                inside_function[id(node)] = node

    offenders = []
    for node in inside_function.values():
        if "noqa: PLC0415" in lines[node.lineno - 1]:
            continue
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        else:
            names = [node.module or ""]
        offenders.extend((name, node.lineno) for name in names)
    return sorted(offenders, key=lambda pair: pair[1])


class TestModuleLayering(unittest.TestCase):
    """The leaf modules under config.py must never import back up the stack."""

    def test_leaf_modules_do_not_import_config(self):
        """
        Given the leaf modules issues, rule_entry and config_types
        When their real import statements are parsed from source
        Then none of them imports toolguard.config

        This is the circular-import guard. config.py imports all three, so any
        import in the other direction is a cycle waiting to be "solved" with a
        banned function-level import.
        """
        for module_name, _allowed in LAYERS:
            with self.subTest(module=module_name):
                path = TOOLGUARD_ROOT / f"{module_name.rsplit('.', 1)[1]}.py"
                self.assertNotIn(
                    "toolguard.config",
                    _module_imports(path),
                    f"{module_name} imports toolguard.config -- circular layering",
                )

    def test_each_leaf_imports_only_from_layers_below_it(self):
        """
        Given a declared layer ordering for the leaf modules
        When each module's toolguard-internal imports are parsed
        Then each imports only from layers strictly below its own
        """
        for module_name, allowed in LAYERS:
            with self.subTest(module=module_name):
                path = TOOLGUARD_ROOT / f"{module_name.rsplit('.', 1)[1]}.py"
                internal = {
                    name
                    for name in _module_imports(path)
                    if name.startswith("toolguard")
                }
                self.assertTrue(
                    internal <= allowed,
                    f"{module_name} imports {sorted(internal - allowed)}, "
                    f"which is not below it in the layering",
                )


class TestReExportIdentity(unittest.TestCase):
    """config.py must re-export the moved types, never redefine them."""

    def test_reexported_types_are_the_same_objects(self):
        """
        Given the types moved out of config.py into config_types.py
        When each name is looked up on both modules
        Then both resolve to the identical class object

        Guards the silent-duplicate-definition failure: a class defined in both
        places passes every behaviour test while isinstance() fails across the
        module boundary.
        """
        for name in RE_EXPORTED_TYPES:
            with self.subTest(type=name):
                self.assertIs(
                    getattr(config, name),
                    getattr(config_types, name),
                    f"{name} is duplicated in config.py, not re-exported",
                )

    def test_reexported_types_report_their_defining_module(self):
        """
        Given the types re-exported by config.py
        When their __module__ attribute is read
        Then it names config_types, the module that actually defines them
        """
        for name in RE_EXPORTED_TYPES:
            with self.subTest(type=name):
                self.assertEqual(
                    getattr(config_types, name).__module__,
                    "toolguard.config_types",
                    f"{name} appears to be defined outside config_types",
                )

    def test_leaf_type_reexports_resolve_to_their_leaf_modules(self):
        """
        Given Issue, RuleEntry and is_tool_wrapper, re-exported by config
        When each is compared against its defining leaf module's attribute
        Then they are the identical object, not a duplicate definition

        ``_strip_tool_wrapper`` was in this list until TOO-45 R6-S1 deleted
        config's re-export of it -- that re-export existed only so
        ``toolguard.tools.takeover_audit`` could reach a private name of a
        module it doesn't otherwise depend on, and that caller now imports
        the public ``toolguard.rule_entry.strip_tool_wrapper`` directly
        instead. ``config`` no longer re-exports the private name at all, so
        there is nothing left here for this identity check to make about it.
        """
        for name, owner in (
            ("Issue", issues),
            ("RuleEntry", rule_entry),
            ("is_tool_wrapper", rule_entry),
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(config, name), getattr(owner, name))

    def test_configuration_stays_in_config_module(self):
        """
        Given the deliberate split of thin types away from implementation logic
        When Configuration's defining module is checked
        Then it is still config.py and it is absent from config_types

        Configuration is ~1088 lines with 22 methods and is coupled to
        module-level discovery helpers; it is the logic the types were separated
        FROM, so moving it would defeat the split.
        """
        self.assertEqual(config.Configuration.__module__, "toolguard.config")
        self.assertFalse(hasattr(config_types, "Configuration"))


class TestNoNewLocalImports(unittest.TestCase):
    """Function-level imports are a project anti-pattern; ratchet against new ones."""

    def test_production_code_adds_no_undocumented_local_imports(self):
        """
        Given the project rule banning imports inside function bodies
        When every module under toolguard/ is parsed for indented imports
        Then none are found that lack the documented-exception marker

        Imports marked '# noqa: PLC0415' are the documented, approved
        circular-dependency exception and are ignored.

        ruff enforces PLC0415 too (TOO-45). That is deliberate redundancy, not
        duplicated logic: this test runs in the suite on every change, while
        ruff runs when someone remembers. Removing either leaves the other
        firing.
        """
        found = set()
        for path in sorted(TOOLGUARD_ROOT.rglob("*.py")):
            if "canopy" in path.parts or path.name.startswith("bash_parser"):
                continue  # generated parser code, not hand-maintained
            for module_name, _lineno in _local_imports(path):
                found.add((path.name, module_name))

        self.assertEqual(
            found,
            set(),
            "New function-level import(s) introduced. Move them to module level, "
            "or -- if a genuine documented circular dependency -- mark the line "
            f"'# noqa: PLC0415'. Offenders: {sorted(found)}",
        )


if __name__ == "__main__":
    unittest.main()
