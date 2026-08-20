"""
Architectural invariant tests for toolguard's module layering: governed modules
import only downward, and config.py re-exports the moved names rather than
redefining them.

Static-structure tests -- they parse the source rather than execute it.
"""

import ast
import importlib
import tempfile
import tomllib
import unittest
from pathlib import Path

from toolguard import config, config_types, issues, rule_entry

TOOLGUARD_ROOT = Path(config.__file__).parent
PYSCN_TOML = TOOLGUARD_ROOT.parent / ".pyscn.toml"

#: Allowed toolguard-internal imports per governed module, lowest layer first.
#: Each set is EXACT: an unused declared edge fails just as an undeclared import
#: does, so the map cannot be loosened without also changing the code.
LAYERS = (
    ("toolguard.issues", frozenset()),
    ("toolguard.ambient", frozenset()),
    ("toolguard.path_utils", frozenset({"toolguard.ambient"})),
    ("toolguard.normalization", frozenset({"toolguard.ambient"})),
    ("toolguard.toml_scan", frozenset()),
    ("toolguard.file_lock", frozenset()),
    ("toolguard.tool_spec", frozenset()),
    ("toolguard.patterns", frozenset({"toolguard.normalization"})),
    ("toolguard.constants", frozenset({"toolguard.tool_spec"})),
    ("toolguard._git", frozenset({"toolguard.constants"})),
    (
        "toolguard.install_provenance",
        frozenset({"toolguard._git", "toolguard.constants"}),
    ),
    (
        "toolguard.install_update",
        frozenset({"toolguard._git", "toolguard.ambient", "toolguard.constants"}),
    ),
    ("toolguard.config_write_guard", frozenset()),
    ("toolguard.rule_entry", frozenset({"toolguard.issues"})),
    (
        "toolguard.rule_sort",
        frozenset({"toolguard.rule_entry", "toolguard.toml_scan"}),
    ),
    ("toolguard.config_types", frozenset({"toolguard.rule_entry"})),
    (
        "toolguard.permissions",
        frozenset(
            {
                "toolguard.config_types",
                "toolguard.normalization",
                "toolguard.patterns",
            }
        ),
    ),
    (
        "toolguard.file_matching",
        frozenset(
            {
                "toolguard.config_types",
                "toolguard.normalization",
                "toolguard.patterns",
                "toolguard.permissions",
            }
        ),
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
    "UnrecognizedFallbackSetting",
)

#: Modules whose presence proves a source walk actually reached the package.
WALK_ANCHORS = frozenset({"config.py", "hook.py", "permissions.py", "issues.py"})


def _module_path(module_name: str) -> Path:
    """The source file of a dotted ``toolguard.*`` module name."""
    return TOOLGUARD_ROOT.joinpath(*module_name.split(".")[1:]).with_suffix(".py")


def _package_of(path: Path) -> str:
    """The dotted package containing *path*, e.g. ``toolguard.parser``."""
    return ".".join(["toolguard", *path.relative_to(TOOLGUARD_ROOT).parent.parts])


def _package_root(path: Path, package: str) -> Path:
    """The directory holding the top-level package that contains *path*."""
    directory = path.parent
    for _ in range(len(package.split("."))):
        directory = directory.parent
    return directory


def _is_module(root: Path, dotted: str) -> bool:
    """Whether *dotted* names a real module or package under *root*."""
    candidate = root.joinpath(*dotted.split("."))
    return (
        candidate.with_suffix(".py").is_file() or (candidate / "__init__.py").is_file()
    )


def _module_imports(path: Path, package: str) -> set:
    """
    Every module *path* imports, as absolute dotted names. *package* is the
    dotted package containing *path*, needed to resolve relative imports.

    ``from pkg import name`` also yields ``pkg.name`` when that submodule
    exists, so importing a sibling module by name is not mistaken for
    importing only its package.
    """
    root = _package_root(path, package)
    parts = package.split(".")
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = parts[: len(parts) - node.level + 1]
                target = ".".join(base + ([node.module] if node.module else []))
            elif node.module:
                target = node.module
            else:
                continue
            found.add(target)
            found.update(
                f"{target}.{alias.name}"
                for alias in node.names
                if _is_module(root, f"{target}.{alias.name}")
            )
    return found


def _internal_imports(path: Path, package: str) -> set:
    """The toolguard modules *path* imports, excluding submodule-attribute noise."""
    imported = _module_imports(path, package)
    return {name for name in imported if name.split(".")[0] == "toolguard"} - {
        "toolguard"
    }


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


def _architecture_config() -> tuple:
    """
    Return ``(layer_of, allow, packages_by_layer)`` from ``.pyscn.toml``: the
    layer each package sits in, the layers each layer may import, and the
    declared package list per layer.
    """
    parsed = tomllib.loads(PYSCN_TOML.read_text())["architecture"]
    layer_of = {}
    packages_by_layer = {}
    for layer in parsed["layers"]:
        packages_by_layer[layer["name"]] = tuple(layer["packages"])
        for package in layer["packages"]:
            layer_of[package] = layer["name"]
    allow = {rule["from"]: frozenset(rule["allow"]) for rule in parsed["rules"]}
    return layer_of, allow, packages_by_layer


def _config_reexports() -> dict:
    """Names config.py imports at module level from each ``toolguard.*`` module."""
    reexports = {}
    for node in ast.parse(_module_path("toolguard.config").read_text()).body:
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "toolguard."
        ):
            reexports.setdefault(node.module, set()).update(a.name for a in node.names)
    return reexports


class TestImportExtraction(unittest.TestCase):
    """The layering guard is only as good as the import forms it can see."""

    def setUp(self):
        """Build a synthetic two-level package so relative imports have a base."""
        self._tmp = tempfile.TemporaryDirectory()
        root = Path(self._tmp.name)
        self.pkg = root / "toolguard"
        (self.pkg / "parser").mkdir(parents=True)
        for name in ("__init__.py", "config.py", "leaf.py"):
            (self.pkg / name).write_text("")
        for name in ("__init__.py", "inner.py"):
            (self.pkg / "parser" / name).write_text("")
        self.addCleanup(self._tmp.cleanup)

    def _imports_of(self, source: str, relative="leaf.py", package="toolguard"):
        """Write *source* into the synthetic package and extract its imports."""
        path = self.pkg / relative
        path.write_text(source)
        return _module_imports(path, package)

    def test_every_syntactic_form_of_an_upward_import_is_seen(self):
        """
        Given the six syntactic forms of importing toolguard.config
        When each is extracted from a module in the package
        Then all six resolve to the absolute name toolguard.config
        """
        forms = (
            "import toolguard.config\n",
            "from toolguard.config import thing\n",
            "from toolguard import config\n",
            "from . import config\n",
            "from .config import thing\n",
            "import toolguard.config as shorthand\n",
        )
        for source in forms:
            with self.subTest(form=source.strip()):
                self.assertIn("toolguard.config", self._imports_of(source))

    def test_a_relative_import_two_levels_up_resolves(self):
        """
        Given a submodule inside toolguard.parser importing from the package above
        When its imports are extracted
        Then the parent-package relative import resolves to toolguard.config
        """
        found = self._imports_of(
            "from ..config import thing\n",
            relative="parser/inner.py",
            package="toolguard.parser",
        )
        self.assertIn("toolguard.config", found)

    def test_a_from_package_import_of_a_non_module_name_is_not_expanded(self):
        """
        Given `from toolguard import SOME_CONSTANT`, where the name is not a module
        When the imports are extracted
        Then only the package name is recorded, not a fabricated submodule
        """
        found = self._imports_of("from toolguard import SOME_CONSTANT\n")
        self.assertEqual(found, {"toolguard"})

    def test_stdlib_imports_are_not_mistaken_for_toolguard_imports(self):
        """
        Given a module importing only from the standard library
        When its internal toolguard imports are extracted
        Then the result is empty
        """
        (self.pkg / "leaf.py").write_text("import os\nfrom pathlib import Path\n")
        self.assertEqual(_internal_imports(self.pkg / "leaf.py", "toolguard"), set())

    def test_a_function_level_import_is_reported_with_its_line(self):
        """
        Given a module with an import inside a function body
        When local imports are collected
        Then the module name and its line number are reported
        """
        path = self.pkg / "leaf.py"
        path.write_text("def f():\n    import json\n    return json\n")
        self.assertEqual(_local_imports(path), [("json", 2)])

    def test_a_documented_local_import_is_excluded(self):
        """
        Given a function-level import carrying the '# noqa: PLC0415' marker
        When local imports are collected
        Then it is not reported
        """
        path = self.pkg / "leaf.py"
        path.write_text("def f():\n    import json  # noqa: PLC0415\n    return json\n")
        self.assertEqual(_local_imports(path), [])

    def test_module_level_imports_are_never_reported_as_local(self):
        """
        Given a module whose imports all sit at module level
        When local imports are collected
        Then nothing is reported
        """
        path = self.pkg / "leaf.py"
        path.write_text("import json\n\n\ndef f():\n    return json\n")
        self.assertEqual(_local_imports(path), [])

    def test_imports_in_methods_and_async_functions_are_reported(self):
        """
        Given function-level imports inside a class method and an async function
        When local imports are collected
        Then both are reported
        """
        path = self.pkg / "leaf.py"
        path.write_text(
            "class C:\n"
            "    def m(self):\n"
            "        import json\n"
            "        return json\n"
            "\n"
            "\n"
            "async def g():\n"
            "    from pathlib import Path\n"
            "    return Path\n"
        )
        self.assertEqual(_local_imports(path), [("json", 3), ("pathlib", 8)])


class TestModuleLayering(unittest.TestCase):
    """The governed modules must never import back up the stack."""

    def test_every_governed_module_resolves_to_a_source_file(self):
        """
        Given the modules declared in LAYERS
        When each is resolved to a path under the package
        Then the file exists, so no row can be checked against nothing
        """
        self.assertNotEqual(
            LAYERS, (), "LAYERS is empty -- every layering test is vacuous"
        )
        for module_name, _allowed in LAYERS:
            with self.subTest(module=module_name):
                self.assertTrue(
                    _module_path(module_name).is_file(),
                    f"{module_name} is declared in LAYERS but has no module behind it",
                )

    def test_governed_modules_do_not_import_config(self):
        """
        Given every module declared in LAYERS
        When their real import statements are parsed from source
        Then none of them imports toolguard.config
        """
        for module_name, _allowed in LAYERS:
            with self.subTest(module=module_name):
                path = _module_path(module_name)
                self.assertNotIn(
                    "toolguard.config",
                    _module_imports(path, _package_of(path)),
                    f"{module_name} imports toolguard.config -- circular layering",
                )

    def test_each_governed_module_imports_only_what_it_declares(self):
        """
        Given a declared allow-list per governed module
        When each module's toolguard-internal imports are parsed
        Then it imports nothing outside its allow-list
        """
        for module_name, allowed in LAYERS:
            with self.subTest(module=module_name):
                path = _module_path(module_name)
                internal = _internal_imports(path, _package_of(path))
                self.assertTrue(
                    internal <= allowed,
                    f"{module_name} imports {sorted(internal - allowed)}, "
                    f"which is not below it in the layering",
                )

    def test_no_declared_edge_is_unused(self):
        """
        Given that an allow-list can only be loosened by adding an edge
        When each declared edge is compared against the module's real imports
        Then every declared edge is backed by an import that exists
        """
        for module_name, allowed in LAYERS:
            with self.subTest(module=module_name):
                path = _module_path(module_name)
                internal = _internal_imports(path, _package_of(path))
                self.assertEqual(
                    sorted(allowed - internal),
                    [],
                    f"{module_name} declares edges it does not use: "
                    f"{sorted(allowed - internal)}. An unused edge is a "
                    f"pre-authorised upward import -- delete it.",
                )

    def test_every_edge_target_inside_the_package_is_itself_governed(self):
        """
        Given that a ratcheted module's dependency can itself drift upward
        When each declared edge's target is looked for among the governed modules
        Then it is governed too, so no row can be deleted while it is depended on
        """
        governed = frozenset(name for name, _ in LAYERS)
        for module_name, allowed in LAYERS:
            with self.subTest(module=module_name):
                ungoverned = sorted(allowed - governed)
                self.assertEqual(
                    ungoverned,
                    [],
                    f"{module_name} depends on {ungoverned}, which no row here "
                    f"ratchets -- the dependency can acquire an upward import "
                    f"unseen",
                )

    def test_every_declared_edge_points_downward(self):
        """
        Given LAYERS ordered lowest layer first
        When each declared edge's target is located in that ordering
        Then it sits strictly lower, so no edge points sideways or up
        """
        index = {name: position for position, (name, _) in enumerate(LAYERS)}
        for position, (module_name, allowed) in enumerate(LAYERS):
            for edge in sorted(allowed):
                with self.subTest(edge=(module_name, edge)):
                    self.assertLess(
                        index[edge],
                        position,
                        f"{module_name} -> {edge} is not strictly below it",
                    )


class TestLayerMapAgreesWithArchitectureConfig(unittest.TestCase):
    """LAYERS and .pyscn.toml describe one model; neither may drift from the other."""

    def setUp(self):
        self.layer_of, self.allow, self.packages_by_layer = _architecture_config()
        self.governed = frozenset(name.split(".", 1)[1] for name, _ in LAYERS)

    def test_the_architecture_config_declares_layers_and_rules(self):
        """
        Given .pyscn.toml as the authoritative layer map
        When it is parsed
        Then it yields a non-empty package map and a rule for every declared layer
        """
        self.assertNotEqual(self.layer_of, {}, "no packages parsed from .pyscn.toml")
        self.assertEqual(
            sorted(self.allow),
            sorted(self.packages_by_layer),
            "every declared layer needs a direction rule and vice versa",
        )

    def test_every_governed_module_is_mapped_by_the_architecture_config(self):
        """
        Given the modules this file governs
        When each is looked up in .pyscn.toml's package map
        Then all of them are mapped, so the two specs cover the same modules
        """
        unmapped = sorted(name for name in self.governed if name not in self.layer_of)
        self.assertEqual(
            unmapped,
            [],
            f"governed here but unmapped in .pyscn.toml: {unmapped}",
        )

    def test_every_foundation_module_is_governed_here(self):
        """
        Given the foundation layer, whose members may import nothing above them
        When its declared packages are compared against LAYERS
        Then every foundation module carries an exact allow-list here
        """
        foundation = self.packages_by_layer["foundation"]
        self.assertNotEqual(foundation, (), "the foundation layer declares no packages")
        missing = sorted(
            package
            for package in foundation
            if _module_path(f"toolguard.{package}").is_file()
            and package not in self.governed
        )
        self.assertEqual(
            missing,
            [],
            f"foundation modules with no allow-list here: {missing}. "
            f"A module added to .pyscn.toml but not to LAYERS silently loses "
            f"its per-module ratchet.",
        )

    def test_layers_never_permits_an_edge_the_architecture_config_forbids(self):
        """
        Given that LAYERS is meant to be a tightening of .pyscn.toml, never a widening
        When each declared edge's source and target layers are compared
        Then the target's layer is one the source's layer is allowed to import
        """
        for module_name, allowed in LAYERS:
            for edge in sorted(allowed):
                with self.subTest(edge=(module_name, edge)):
                    source_layer = self.layer_of[module_name.split(".", 1)[1]]
                    target_layer = self.layer_of[edge.split(".", 1)[1]]
                    self.assertIn(
                        target_layer,
                        self.allow[source_layer],
                        f"{module_name} -> {edge} is permitted here but denied by "
                        f".pyscn.toml ({source_layer} -> {target_layer})",
                    )


class TestReExportIdentity(unittest.TestCase):
    """config.py must re-export the moved names, never redefine them."""

    def test_every_name_config_imports_from_a_leaf_is_the_leaf_s_own_object(self):
        """
        Given every name config.py imports at module level from a toolguard module
        When each is compared against the defining module's attribute
        Then they are the identical object, not a duplicate definition
        """
        reexports = _config_reexports()
        self.assertNotEqual(
            reexports, {}, "no toolguard re-exports parsed from config.py"
        )
        for module_name, names in sorted(reexports.items()):
            owner = importlib.import_module(module_name)
            for name in sorted(names):
                with self.subTest(module=module_name, name=name):
                    self.assertIs(
                        getattr(config, name),
                        getattr(owner, name),
                        f"{name} is duplicated in config.py, not re-exported from "
                        f"{module_name}",
                    )

    def test_the_re_exported_type_list_covers_every_config_types_name(self):
        """
        Given RE_EXPORTED_TYPES, which drives the defining-module checks
        When it is compared against what config.py actually takes from config_types
        Then the two agree, so no re-exported type escapes the check
        """
        declared = frozenset(RE_EXPORTED_TYPES)
        actual = frozenset(_config_reexports().get("toolguard.config_types", ()))
        self.assertEqual(
            sorted(declared),
            sorted(actual),
            f"unguarded: {sorted(actual - declared)}; stale: {sorted(declared - actual)}",
        )

    def test_reexported_types_are_the_same_objects(self):
        """
        Given the types moved out of config.py into config_types.py
        When each name is looked up on both modules
        Then both resolve to the identical class object
        """
        self.assertNotEqual(RE_EXPORTED_TYPES, (), "RE_EXPORTED_TYPES is empty")
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
        self.assertNotEqual(RE_EXPORTED_TYPES, (), "RE_EXPORTED_TYPES is empty")
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
            documented-exception marker, and the walk did reach the package
        """
        found = set()
        scanned = set()
        for path in sorted(TOOLGUARD_ROOT.rglob("*.py")):
            if "canopy" in path.parts or path.name.startswith("bash_parser"):
                continue
            scanned.add(path.name)
            for module_name, _lineno in _local_imports(path):
                found.add((path.name, module_name))

        self.assertNotEqual(WALK_ANCHORS, frozenset(), "the liveness anchors are empty")
        self.assertLessEqual(
            WALK_ANCHORS,
            scanned,
            f"the walk missed {sorted(WALK_ANCHORS - scanned)} -- it did not reach "
            f"the package, so finding nothing proves nothing",
        )
        self.assertEqual(
            found,
            set(),
            "New function-level import(s) introduced. Move them to module level, "
            "or -- if a genuine documented circular dependency -- mark the line "
            f"'# noqa: PLC0415'. Offenders: {sorted(found)}",
        )


if __name__ == "__main__":
    unittest.main()
