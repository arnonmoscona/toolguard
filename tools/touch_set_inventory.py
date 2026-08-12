#!/usr/bin/env python
"""
Dev-only instrument: the structural inventory of ONE tree, and the input given to the
BLIND PREDICTOR in TOO-45's M2 "expected touch set" measure (see
``toolguard-memories/TOO-45/reports/micro-canary-protocol.md``).

A predictor must be able to form sensible expectations about where things live
WITHOUT seeing the change. So for every module in the tree this tool emits: the
module's own path, the first line of its module docstring (its self-described
purpose), its line count, and its PUBLIC top-level symbols, each with the first line
of its own docstring.

Hard rule, non-negotiable
--------------------------
This tool NEVER reads or emits anything derived from a diff, a second tree, or
version control history, and there is deliberately no ``--old``/``--new``/``--repo``
mode -- if it could see the answer, the prediction it is meant to seed would be
worthless. The gitignore support below reads one local file with ``Path.read_text``
and never invokes ``git`` as a subprocess.

What counts as "public"
-------------------------
A top-level (module-body-level) ``def``/``async def``/``class`` whose name does
not start with ``_``. Methods, nested functions, and module-level variables/
constants are NOT included. A symbol's own docstring is truncated to its first line,
same as the module docstring.

Failures are named, not folded away
-------------------------------------
A file that fails to parse, or fails to even be READ (see :func:`_safe_read_text`),
is named in ``parse_failures`` and excluded from ``modules``. A module or symbol with
no docstring at all gets an explicit ``null``/``None``, never an empty string standing
in for "absent". Files dropped during DISCOVERY are a different case -- an
:data:`EXCLUDED_DIR_NAMES` directory, or a ``.gitignore`` match -- and appear nowhere in
the report at all.

Usage::

    uv run python tools/touch_set_inventory.py --tree /path/to/tree
    uv run python tools/touch_set_inventory.py --tree /path/to/tree --json

Validating predictions at authoring time (``--validate-predictions``)
--------------------------------------------------------------------------
A predictor's biggest unforced error is naming a function that does not exist.
:mod:`tools.touch_set_score` cannot catch this itself -- it reads no tree at all, so
a guessed name is indistinguishable there from an ordinary miss on a real, untouched
location. The check therefore belongs here, at authoring time:

    uv run python tools/touch_set_inventory.py --tree /path/to/tree \\
        --validate-predictions predictions.json

This checks every ``location`` in *predictions.json* against the FULL set of locations
that exist in the tree (see :func:`all_locations_for_validation`), BROADER than the
public-top-level-only symbols the plain inventory shows: a prediction naming a real
private helper, method, or field is not a guess just because the blind predictor was
never shown it by name.

**Invalid is advisory, not a hard gate**: this mode always exits 0 for a well-formed
predictions file, however many locations are invalid (a malformed FILE -- bad JSON,
missing required fields -- still exits 2). No static walk can see a name that exists
only at runtime, so invalid locations are reported with nearest-real-location
suggestions for a human to read, not enforced.
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import difflib
import fnmatch
import json
import sys
from pathlib import Path
from typing import Sequence

# Shared rather than reimplemented so the two tools' notion of "the same location string"
# cannot drift apart.
from tools.touch_set_score import normalize_location

KNOWN_LIMITATIONS = [
    "gitignore support (see _load_gitignore_patterns) is best-effort and reads ONLY the tree "
    "root's own top-level .gitignore file -- no nested per-directory .gitignore cascading, no "
    "negation (!) patterns, no global or repo-config excludes (.git/info/exclude), and NEVER a "
    "`git` subprocess call (this file-discovery path must never spawn a process -- see the "
    "module docstring's blindness guarantee, verified by an audit hook). A repo whose ignore "
    "rules live somewhere other than a root .gitignore, or that rely on negation, will not have "
    "those rules honoured here.",
    "A module reachable through more than one path via a FILE symlink is de-duplicated by "
    "resolved real path (keeping the first, sorted, path to reach it); a directory-symlink loop "
    "is not specially guarded against beyond whatever recursion behaviour Path.rglob itself has.",
    "--validate-predictions's location set includes class/module-level AnnAssign/Assign targets "
    "(dataclass-style fields, module constants) in addition to functions/classes at any nesting "
    "depth/visibility, but still cannot see a name that exists only at runtime (a lambda "
    "assigned dynamically, a name built by metaprogramming, an attribute set via setattr) -- "
    "those always report invalid even when a diff judge could legitimately cite them. Because "
    "that false-negative is costlier than a false positive, 'invalid' is advisory (with "
    "nearest-real-location suggestions), never a hard exit-1 gate -- see the module docstring.",
]

# --------------------------------------------------------------------------
# File discovery, test-vs-production, gitignore, symlink dedup
# --------------------------------------------------------------------------
#
# Discovery and the test/production rule are duplicated here rather than imported from
# tools.change_role_classifier, deliberately: this tool depends on that module nowhere.

EXCLUDED_DIR_NAMES = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".pyscn",
    "build",
    "dist",
    "cover",
}


def _load_gitignore_patterns(tree_root: Path) -> list[str]:
    """Read *tree_root*'s OWN top-level ``.gitignore`` as ordinary file content, NEVER via a
    ``git`` subprocess call (see the module docstring's hard rule). Returns the non-blank,
    non-comment, non-negation pattern lines unprocessed; :func:`_is_gitignored` decides what
    they mean. A missing or unreadable ``.gitignore`` returns an empty list rather than
    raising -- there is simply nothing extra to exclude."""
    gitignore_path = tree_root / ".gitignore"
    if not gitignore_path.is_file():
        return []
    try:
        text = gitignore_path.read_text(encoding="utf-8", errors="surrogateescape")
    except OSError:
        return []
    patterns: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("!"):
            # Negation is unsupported: drop the line rather than let it act as an ordinary
            # exclude, which would invert its meaning.
            continue
        patterns.append(stripped)
    return patterns


def _is_gitignored(relpath: Path, patterns: list[str]) -> bool:
    """Best-effort match of *relpath* (relative to the tree root) against *patterns*. A
    trailing ``/`` is stripped before either rule below is applied.

    A pattern that then still contains a ``/`` is treated as anchored to the tree root and
    compared LITERALLY against the relative POSIX path -- equality, or that path as a
    directory prefix. ``fnmatch`` is not reached on this branch, so a wildcard in an anchored
    pattern is compared as an ordinary character: ``docs/*.py`` does not exclude
    ``docs/a.py``.

    A pattern with no ``/`` left is ``fnmatch``ed against each path component separately, at
    any depth, so ``tmp/`` does exclude ``tmp/anything/deep/file.py``.
    """
    posix = relpath.as_posix()
    parts = relpath.parts
    for pattern in patterns:
        pat = pattern[:-1] if pattern.endswith("/") else pattern
        anchored = "/" in pat
        pat = pat.lstrip("/")
        if not pat:
            continue
        if anchored:
            if posix == pat or posix.startswith(pat + "/"):
                return True
        elif any(fnmatch.fnmatch(part, pat) for part in parts):
            return True
    return False


def discover_python_files(
    root: Path, gitignore_patterns: list[str] | None = None
) -> list[Path]:
    """Every ``*.py`` file under *root*, as paths relative to *root*, skipping any
    :data:`EXCLUDED_DIR_NAMES` directory and, when *gitignore_patterns* is given, anything
    :func:`_is_gitignored` matches. A module reachable through more than one path via a FILE
    symlink is kept once, under the first path in sorted order. Sorted for deterministic
    output."""
    candidates: list[Path] = []
    for path in root.rglob("*.py"):
        relpath = path.relative_to(root)
        if any(part in EXCLUDED_DIR_NAMES for part in relpath.parts[:-1]):
            continue
        if gitignore_patterns and _is_gitignored(relpath, gitignore_patterns):
            continue
        candidates.append(relpath)
    candidates.sort()

    found: list[Path] = []
    seen_real: set[Path] = set()
    for relpath in candidates:
        try:
            real = (root / relpath).resolve()
        except OSError:
            # An unresolvable path is not this function's problem to report -- it surfaces
            # again, named, when _safe_read_text tries to actually read the file. Give it its
            # own identity here so discovery never silently drops it.
            real = root / relpath
        if real in seen_real:
            continue
        seen_real.add(real)
        found.append(relpath)
    return found


def is_test_path(relpath: Path) -> bool:
    """A path is TEST code if any directory component is exactly ``test``/``tests``, or the
    filename matches ``test_*.py``/``*_test.py``. Everything else is production."""
    if any(part in ("test", "tests") for part in relpath.parts[:-1]):
        return True
    name = relpath.name
    return name.startswith("test_") or name.endswith("_test.py")


def _safe_read_text(path: Path) -> tuple[str | None, str | None]:
    """Reads *path* as UTF-8-with-surrogateescape text, turning ``OSError`` (a broken symlink,
    a directory matching ``*.py``, a permission-denied file) and ``UnicodeError`` into a named
    failure, so ONE bad file in a large tree does not crash the whole run. Returns
    ``(content, error)`` -- exactly one is ``None``."""
    try:
        return path.read_text(encoding="utf-8", errors="surrogateescape"), None
    except (OSError, UnicodeError) as exc:
        return None, f"{path}: {exc.__class__.__name__}: {exc}"


# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class SymbolEntry:
    """One public top-level function or class, as reported to the blind predictor."""

    name: str
    kind: str  # "function" | "async function" | "class"
    docstring_first_line: str | None


@dataclasses.dataclass(frozen=True)
class ModuleEntry:
    """One module's structural summary -- everything the blind predictor is allowed to see
    about it."""

    path: str
    is_test: bool
    line_count: int
    docstring_first_line: str | None
    public_symbols: tuple[SymbolEntry, ...]


@dataclasses.dataclass
class InventoryResult:
    tree_root: str
    modules: list[ModuleEntry]
    parse_failures: list[str]  # "path: message"


# --------------------------------------------------------------------------
# Docstring handling
# --------------------------------------------------------------------------


def _first_line(docstring: str | None) -> str | None:
    """The first non-blank line of *docstring*, whitespace-stripped. Returns ``None`` -- never
    ``""`` -- when there is no docstring at all or it is entirely blank, so "absent" is never
    printed as if it were real content."""
    if docstring is None:
        return None
    stripped = docstring.strip()
    if not stripped:
        return None
    return stripped.splitlines()[0].strip()


# --------------------------------------------------------------------------
# Per-file analysis
# --------------------------------------------------------------------------


def _symbol_kind(
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> str:
    if isinstance(node, ast.AsyncFunctionDef):
        return "async function"
    if isinstance(node, ast.FunctionDef):
        return "function"
    return "class"


def build_module_entry(
    source: str, relpath: str, is_test: bool
) -> tuple[ModuleEntry | None, str | None]:
    """Parses *source* and returns ``(entry, None)`` on success or ``(None, error_message)``
    on a syntax error -- callers must name the failure explicitly rather than silently omitting
    the file from the inventory. Only TOP-LEVEL (module-body) ``def``/``class`` statements are
    considered; methods and nested functions are deliberately excluded."""
    try:
        tree = ast.parse(source, filename=relpath)
    except SyntaxError as exc:
        return None, f"{relpath}: {exc}"

    symbols: list[SymbolEntry] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue
        symbols.append(
            SymbolEntry(
                name=node.name,
                kind=_symbol_kind(node),
                docstring_first_line=_first_line(ast.get_docstring(node, clean=True)),
            )
        )

    entry = ModuleEntry(
        path=relpath,
        is_test=is_test,
        line_count=len(source.splitlines()),
        docstring_first_line=_first_line(ast.get_docstring(tree, clean=True)),
        public_symbols=tuple(symbols),
    )
    return entry, None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def run_inventory(tree_root: Path) -> InventoryResult:
    """Builds the inventory for exactly one tree. Opens only paths under *tree_root* -- no
    other path, no VCS metadata, no second tree; see the module docstring's "Hard rule". A
    file that cannot be read or parsed is named in ``parse_failures`` rather than silently
    omitted."""
    modules: list[ModuleEntry] = []
    parse_failures: list[str] = []
    gitignore_patterns = _load_gitignore_patterns(tree_root)
    for relpath in discover_python_files(tree_root, gitignore_patterns):
        source, read_error = _safe_read_text(tree_root / relpath)
        if read_error is not None:
            parse_failures.append(read_error)
            continue
        entry, parse_error = build_module_entry(
            source, str(relpath), is_test_path(relpath)
        )
        if parse_error is not None:
            parse_failures.append(parse_error)
            continue
        modules.append(entry)

    modules.sort(key=lambda m: m.path)
    return InventoryResult(
        tree_root=str(tree_root), modules=modules, parse_failures=parse_failures
    )


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def build_report(result: InventoryResult) -> dict:
    """The full structured report, shared by the text and ``--json`` presentations."""
    return {
        "tree_root": result.tree_root,
        "modules_found": len(result.modules),
        "parse_failures": result.parse_failures,
        "modules": [
            {
                "path": m.path,
                "is_test": m.is_test,
                "line_count": m.line_count,
                "docstring_first_line": m.docstring_first_line,
                "public_symbols": [
                    {
                        "name": s.name,
                        "kind": s.kind,
                        "docstring_first_line": s.docstring_first_line,
                    }
                    for s in m.public_symbols
                ],
            }
            for m in result.modules
        ],
        "known_limitations": KNOWN_LIMITATIONS,
    }


def print_text_report(report: dict) -> None:
    print(f"touch-set structural inventory -- tree: {report['tree_root']}")
    print(f"modules found: {report['modules_found']}")
    print()

    if report["parse_failures"]:
        print(
            f"PARSE/READ FAILURES ({len(report['parse_failures'])}) -- EXCLUDED from the "
            "inventory below:"
        )
        for failure in report["parse_failures"]:
            print(f"  - {failure}")
        print()
    else:
        print("Parse/read failures: none.")
        print()

    print(
        "NOTE: this inventory describes exactly one tree, as it stands. No diff, no second "
        "tree, no VCS history was consulted to produce it."
    )
    print()

    for m in report["modules"]:
        doc = m["docstring_first_line"] or "(no module docstring)"
        tag = " [test]" if m["is_test"] else ""
        print(f"{m['path']}{tag} -- {m['line_count']} lines")
        print(f"  purpose: {doc}")
        if not m["public_symbols"]:
            print("  public top-level symbols: none")
        else:
            print(f"  public top-level symbols ({len(m['public_symbols'])}):")
            for s in m["public_symbols"]:
                sdoc = s["docstring_first_line"] or "(no docstring)"
                print(f"    - [{s['kind']}] {s['name']} -- {sdoc}")
        print()

    print("KNOWN LIMITATIONS:")
    for i, limitation in enumerate(report["known_limitations"], start=1):
        print(f"  {i}. {limitation}")


# --------------------------------------------------------------------------
# Prediction-existence validation (--validate-predictions)
# --------------------------------------------------------------------------
#
# Deliberately SEPARATE from the ModuleEntry/SymbolEntry machinery above: the plain inventory
# shows a blind predictor only PUBLIC TOP-LEVEL symbols, but existence-validation must not
# reject a real prediction just because it names a private helper, a method, or a
# data-carrying field the predictor was never shown by name. The broader location set
# collected here serves only the "does this string correspond to something real" check, and
# never feeds the printed/JSON inventory a predictor sees.


def _collect_qualnames(tree: ast.Module) -> list[str]:
    """Every FunctionDef/AsyncFunctionDef/ClassDef qualname, at ANY nesting depth and ANY
    visibility, PLUS simple assignment targets (``AnnAssign``/``Assign`` with a plain ``Name``
    target) -- a dataclass field, a class attribute, or a module constant is a location a diff
    judge would legitimately cite.

    Assignment targets are taken from the module body and from class bodies only -- not from a
    function's locals, which are not the kind of location this check is for, and not from a
    module-level assignment nested inside a block such as ``if TYPE_CHECKING:``, since only the
    module body's own statements are scanned."""
    qualnames: list[str] = []

    def scan_body_for_assigns(body: list[ast.stmt], prefix: tuple[str, ...]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                qualnames.append(".".join((*prefix, stmt.target.id)))
            elif isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        qualnames.append(".".join((*prefix, target.id)))

    def walk(node: ast.AST, prefix: tuple[str, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qualnames.append(".".join((*prefix, child.name)))
                walk(child, (*prefix, child.name))
            elif isinstance(child, ast.ClassDef):
                qualnames.append(".".join((*prefix, child.name)))
                scan_body_for_assigns(child.body, (*prefix, child.name))
                walk(child, (*prefix, child.name))
            else:
                walk(child, prefix)

    scan_body_for_assigns(tree.body, ())
    walk(tree, ())
    return qualnames


def all_locations_for_validation(tree_root: Path) -> tuple[set[str], list[str]]:
    """Every location string (bare module path, AND ``path::Qual.Name`` for every function/
    class/field found by :func:`_collect_qualnames`) that exists anywhere in *tree_root*.
    Honours the tree's own gitignore and never crashes on an unreadable file. Returns
    ``(locations, parse_failures)`` -- a file that fails to read or parse contributes no
    locations and is named in the failures."""
    locations: set[str] = set()
    parse_failures: list[str] = []
    gitignore_patterns = _load_gitignore_patterns(tree_root)
    for relpath in discover_python_files(tree_root, gitignore_patterns):
        source, read_error = _safe_read_text(tree_root / relpath)
        label = str(relpath)
        if read_error is not None:
            parse_failures.append(read_error)
            continue
        try:
            tree = ast.parse(source, filename=label)
        except SyntaxError as exc:
            parse_failures.append(f"{label}: {exc}")
            continue
        locations.add(label)
        for qualname in _collect_qualnames(tree):
            locations.add(f"{label}::{qualname}")
    return locations, parse_failures


def load_prediction_locations(path: Path) -> tuple[list[str], list[str]]:
    """Minimal loader for ``--validate-predictions``: extracts every ``location`` string from a
    predictions-shaped JSON file. Deliberately does NOT validate ``kind`` or any other field --
    this mode only asks whether a predicted LOCATION exists in a given tree. Returns
    ``(locations, errors)``; :func:`validate_predictions` treats any error as fatal rather than
    checking part of a broken file and reporting as if the rest were fine."""
    errors: list[str] = []
    try:
        raw_text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [], [f"cannot read {path}: {exc}"]

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        return [], [f"{path} is not valid JSON: {exc}"]

    if not isinstance(data, list):
        return (
            [],
            [
                f"{path} must contain a JSON array at the top level, got {type(data).__name__}"
            ],
        )

    locations: list[str] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            errors.append(
                f"{path} entry #{i}: expected an object, got {type(item).__name__}"
            )
            continue
        location = item.get("location")
        if not isinstance(location, str) or not location.strip():
            errors.append(
                f"{path} entry #{i}: 'location' must be a non-empty string, got {location!r}"
            )
            continue
        locations.append(location)
    return locations, errors


@dataclasses.dataclass
class ValidationResult:
    tree_root: str
    predictions_path: str
    valid_locations: list[str]
    invalid_locations: list[str]
    suggestions: dict[str, list[str]]
    duplicate_predictions: dict[str, int]
    parse_failures: list[str]


def _nearest_locations(
    location: str, all_locations: set[str], limit: int = 3
) -> list[str]:
    """Up to *limit* nearest real locations for an invalid prediction, via stdlib ``difflib``
    -- a "did you mean", not a semantic match. Empty when nothing clears the cutoff."""
    return difflib.get_close_matches(location, all_locations, n=limit, cutoff=0.6)


def validate_predictions(
    tree_root: Path, predictions_path: Path
) -> tuple[ValidationResult | None, list[str]]:
    """Checks every location named in *predictions_path* against the FULL location set of
    *tree_root* (see :func:`all_locations_for_validation`). Meant to run BEFORE scoring, at
    authoring time, so a guessed nonexistent location is caught and fixed by the predictor
    instead of silently becoming an indistinguishable miss. Returns ``(result, fatal_errors)``;
    *result* is ``None`` only when the predictions file itself failed to load -- a tree-side
    parse/read failure is named in ``result.parse_failures`` instead, since other files in the
    tree may still be checkable."""
    raw_locations, load_errors = load_prediction_locations(predictions_path)
    if load_errors:
        return None, load_errors

    all_locations, parse_failures = all_locations_for_validation(tree_root)

    normalized = [normalize_location(loc) for loc in raw_locations]
    counts: dict[str, int] = {}
    for loc in normalized:
        counts[loc] = counts.get(loc, 0) + 1
    duplicates = {loc: n for loc, n in sorted(counts.items()) if n > 1}

    seen: set[str] = set()
    valid: list[str] = []
    invalid: list[str] = []
    suggestions: dict[str, list[str]] = {}
    for loc in normalized:
        if loc in seen:
            continue
        seen.add(loc)
        if loc in all_locations:
            valid.append(loc)
        else:
            invalid.append(loc)
            near = _nearest_locations(loc, all_locations)
            if near:
                suggestions[loc] = near

    result = ValidationResult(
        tree_root=str(tree_root),
        predictions_path=str(predictions_path),
        valid_locations=sorted(valid),
        invalid_locations=sorted(invalid),
        suggestions=suggestions,
        duplicate_predictions=duplicates,
        parse_failures=parse_failures,
    )
    return result, []


def build_validation_report(result: ValidationResult) -> dict:
    """The full structured validation report, shared by the text and ``--json`` presentations."""
    return {
        "tree_root": result.tree_root,
        "predictions_file": result.predictions_path,
        "parse_failures": result.parse_failures,
        "valid_count": len(result.valid_locations),
        "invalid_count": len(result.invalid_locations),
        "valid_locations": result.valid_locations,
        "invalid_locations": result.invalid_locations,
        "suggestions": result.suggestions,
        "duplicate_predictions": result.duplicate_predictions,
        "known_limitations": KNOWN_LIMITATIONS,
    }


def print_validation_report(report: dict) -> None:
    print(f"prediction-existence validation -- tree: {report['tree_root']}")
    print(f"predictions file: {report['predictions_file']}")
    print()
    print(
        "'invalid' below is ADVISORY, not a gate -- this mode always exits 0 for a well-formed "
        "file. See KNOWN LIMITATIONS."
    )
    print()

    if report["parse_failures"]:
        print(
            f"TREE PARSE/READ FAILURES ({len(report['parse_failures'])}) -- these files could "
            "not contribute locations to the existence check:"
        )
        for f in report["parse_failures"]:
            print(f"  - {f}")
        print()

    print(f"valid (found in tree): {report['valid_count']}")
    print(f"invalid (NOT found in tree): {report['invalid_count']}")
    print()

    if report["invalid_locations"]:
        print("INVALID PREDICTED LOCATIONS (review before scoring; not auto-rejected):")
        for loc in report["invalid_locations"]:
            near = report["suggestions"].get(loc)
            if near:
                print(f"  - {loc}  (did you mean: {', '.join(near)}?)")
            else:
                print(f"  - {loc}  (no close match found in the tree)")
        print()

    if report["duplicate_predictions"]:
        print(
            f"DUPLICATE PREDICTIONS ({len(report['duplicate_predictions'])} locations named "
            "more than once in the predictions file -- not fatal here, but "
            "tools/touch_set_score.py will report these as ambiguous when scoring):"
        )
        for loc, n in report["duplicate_predictions"].items():
            print(f"  - {loc} (x{n})")
        print()

    print(
        "NOTE: this check uses the FULL location set (every function/class at any nesting "
        "depth/visibility, plus class- and module-level assignment targets) -- broader than the "
        "public-top-level-only symbols shown in the plain inventory. A location being 'valid' "
        "here means only that the name is real; it does not mean tools/touch_set_score.py will "
        "find a matching entry for it in an actuals file."
    )
    print()
    print("KNOWN LIMITATIONS:")
    for i, limitation in enumerate(report["known_limitations"], start=1):
        print(f"  {i}. {limitation}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Emit the structural inventory of ONE tree (path, module-docstring first "
            "line, line count, public top-level symbols with their own docstring first "
            "line) -- the input a blind predictor is given for the TOO-45 M2 "
            "'expected touch set' measure. Never reads a diff, a second tree, or VCS "
            "history: see tools/touch_set_score.py for the tool that compares predictions "
            "made from this inventory against a separately judged actuals file (or two)."
        )
    )
    parser.add_argument(
        "--tree", type=Path, required=True, help="Root of the single tree to inventory."
    )
    parser.add_argument(
        "--validate-predictions",
        type=Path,
        default=None,
        metavar="PREDICTIONS_JSON",
        help=(
            "Instead of printing the inventory, check every 'location' in this predictions "
            "JSON file against the FULL location set of --tree (any nesting depth, any "
            "visibility, plus class/module-level fields) and report which ones are real, with "
            "nearest-match suggestions for the rest. Advisory only -- always exits 0 for a "
            "well-formed file; run this before scoring with tools/touch_set_score.py."
        ),
    )
    parser.add_argument(
        "--json", action="store_true", help="Print the machine-readable report as JSON."
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    if not args.tree.is_dir():
        print(f"--tree {args.tree} is not a directory", file=sys.stderr)
        return 2

    if args.validate_predictions is not None:
        result, errors = validate_predictions(args.tree, args.validate_predictions)
        if errors:
            print(
                f"predictions file {args.validate_predictions} is invalid:",
                file=sys.stderr,
            )
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 2
        report = build_validation_report(result)
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
        else:
            print_validation_report(report)
        return 0

    result = run_inventory(args.tree)
    report = build_report(result)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print_text_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
