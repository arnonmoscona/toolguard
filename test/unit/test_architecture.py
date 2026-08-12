"""
Architectural invariant tests for toolguard's module layering: leaf modules
import only downward, and config.py re-exports the moved types rather than
redefining them.

Static-structure tests -- they parse the source rather than execute it.
"""

import ast
import unittest
from pathlib import Path

from toolguard import config, config_types, issues, rule_entry

TOOLGUARD_ROOT = Path(config.__file__).parent

#: Allowed toolguard-internal imports per leaf module, lowest layer first.
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
        "toolguard.permission_resolution",
        frozenset(
            {
                "toolguard.config_types",
                "toolguard.permissions",
                "toolguard.file_matching",
            }
        ),
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


def _module_imports(path: Path) -> set:
    """Return every module name *path* imports via a real import statement."""
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return found


def _local_imports(path: Path):
    """
    Return ``(module_name, lineno)`` for every function-level import in *path*
    that lacks the ``# noqa: PLC0415`` documented-exception marker.
    """
    source = path.read_text()
    lines = source.splitlines()
    tree = ast.parse(source)

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
        Given every leaf module declared in LAYERS
        When their real import statements are parsed from source
        Then none of them imports toolguard.config
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
        When each one's __module__ is read from config_types
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
        """
        self.assertEqual(config.Configuration.__module__, "toolguard.config")
        self.assertFalse(hasattr(config_types, "Configuration"))


class TestNoNewLocalImports(unittest.TestCase):
    """Function-level imports are a project anti-pattern; ratchet against new ones."""

    def test_production_code_adds_no_undocumented_local_imports(self):
        """
        Given the project rule banning imports inside function bodies
        When every non-generated module under toolguard/ is parsed for
            indented imports
        Then none are found that lack the '# noqa: PLC0415'
            documented-exception marker
        """
        found = set()
        for path in sorted(TOOLGUARD_ROOT.rglob("*.py")):
            if "canopy" in path.parts or path.name.startswith("bash_parser"):
                continue
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
