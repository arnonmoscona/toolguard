#!/usr/bin/env python
"""
Finds ticket-reference narrative (``TOO-nnn``) left in docstrings and comments, and checks that
a sweep removing it moved no code.

:func:`docstring_ticket_refs` and :func:`comment_ticket_refs` find the sites.
:func:`code_shape` is the check: it parses a file, drops the leading docstring of the module and
of every class and function, and dumps the AST without line and column attributes. Equal shapes
therefore mean equal ASTs apart from those docstrings, so anything an AST does not record is
invisible -- ``#`` comments, and layout down to quote style and how a literal is spelled
(``1_000`` and ``1000`` compare equal, as do ``"a" "b"`` and ``"ab"``). Everything an AST does
record is compared, the value of ordinary string literals included: rewording a message string
reads as a code change.

What ``--compare-against`` does NOT establish
---------------------------------------------
It examines only the files ``git diff --diff-filter=AM <ref> -- '*.py'`` lists, which is tracked
files only. An untracked file is never compared -- silently, since it does not appear in the
report either. Neither is a deleted one. And no AST check can see a comment that other tools act
on, such as ``# noqa`` or ``# type: ignore``.

``--stale-references`` is a separate, report-only scan: ``.py`` paths and dotted
``module.symbol`` references named in docstrings that do not resolve against the tree. It
asserts nothing, several reference shapes are skipped rather than judged, and it is deliberately
best-effort.

Usage::

    uv run python tools/comment_hygiene.py
    uv run python tools/comment_hygiene.py --compare-against HEAD
    uv run python tools/comment_hygiene.py --stale-references
"""

from __future__ import annotations

import argparse
import ast
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import NewType

REPO_ROOT = Path(__file__).resolve().parents[1]

#: The trees this instrument scans, keyed by the name each is reported under.
SWEPT_TREES = {
    "toolguard": REPO_ROOT / "toolguard",
    "tools": REPO_ROOT / "tools",
    "test": REPO_ROOT / "test",
}

_TICKET_RE = re.compile(r"\bTOO-\d+\b")

#: Raised by an unreadable or unparseable source file, treated as "skip it".
_UNREADABLE_SOURCE_ERRORS = (OSError, SyntaxError, UnicodeDecodeError)


def _iter_python_files(root: Path):
    yield from sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def _repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


@dataclass(frozen=True)
class TicketRefSite:
    """One ``TOO-nnn`` occurrence found inside a docstring or a ``#`` comment."""

    path: str  # repo-relative, POSIX
    line: int  # 1-based
    owner: str  # dotted enclosing symbol, or "<module>"
    text: str  # the matched ticket token, e.g. "TOO-45"


def _iter_docstring_owners(tree: ast.Module):
    """Yields ``(node, dotted_owner_name)`` for the module and every class/function definition,
    at any nesting depth."""
    yield tree, "<module>"

    def walk(node: ast.AST, prefix: tuple[str, ...]):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                owner = ".".join((*prefix, child.name))
                yield child, owner
                yield from walk(child, (*prefix, child.name))
            else:
                yield from walk(child, prefix)

    yield from walk(tree, ())


def _docstring_line_for_offset(base_lineno: int, text: str, offset: int) -> int:
    """Physical line number of *offset* within a docstring, given the ``lineno`` of the
    string-literal node the docstring begins on."""
    return base_lineno + text.count("\n", 0, offset)


def docstring_ticket_refs(root: Path) -> list[TicketRefSite]:
    """Every ``TOO-nnn`` occurrence inside a module/class/function docstring under *root*."""
    sites: list[TicketRefSite] = []
    for py_file in _iter_python_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except _UNREADABLE_SOURCE_ERRORS:
            continue
        rel = _repo_relative(py_file)
        for node, owner in _iter_docstring_owners(tree):
            if not node.body:
                continue
            first = node.body[0]
            if not (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                continue
            doc_text = first.value.value
            base_lineno = first.value.lineno
            for match in _TICKET_RE.finditer(doc_text):
                sites.append(
                    TicketRefSite(
                        path=rel,
                        line=_docstring_line_for_offset(
                            base_lineno, doc_text, match.start()
                        ),
                        owner=owner,
                        text=match.group(0),
                    )
                )
    return sites


def comment_ticket_refs(root: Path) -> list[TicketRefSite]:
    """Every ``TOO-nnn`` occurrence inside a ``#`` comment token under *root*. *owner* is always
    ``"<comment>"`` -- a comment has no enclosing docstring-carrying node to attribute it to."""
    sites: list[TicketRefSite] = []
    for py_file in _iter_python_files(root):
        try:
            source_bytes = py_file.read_bytes()
        except OSError:
            continue
        rel = _repo_relative(py_file)
        try:
            tokens = tokenize.tokenize(
                iter(source_bytes.splitlines(keepends=True)).__next__
            )
            for tok in tokens:
                if tok.type != tokenize.COMMENT:
                    continue
                for match in _TICKET_RE.finditer(tok.string):
                    sites.append(
                        TicketRefSite(
                            path=rel,
                            line=tok.start[0],
                            owner="<comment>",
                            text=match.group(0),
                        )
                    )
        except (
            tokenize.TokenizeError,
            SyntaxError,
            IndentationError,
            UnicodeDecodeError,
        ):
            continue
    return sites


#: An AST-shape fingerprint with module, class and function docstrings stripped -- see the
#: module docstring for what equal fingerprints do and do not establish.
CodeShape = NewType("CodeShape", str)


def _strip_docstrings(tree: ast.AST) -> None:
    """Removes the leading docstring ``Expr`` statement, in place, from the module and every
    class/function body that has one."""
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            node.body.pop(0)


def code_shape(source: str) -> CodeShape:
    """Parses *source* and returns its AST shape with module, class and function docstrings
    removed. A string statement anywhere other than first in a body is left in place, so an
    attribute docstring counts as code."""
    tree = ast.parse(source)
    _strip_docstrings(tree)
    return CodeShape(ast.dump(tree, include_attributes=False))


@dataclass(frozen=True)
class ShapeChange:
    """One file whose code shape moved (or could not be checked) between two revisions."""

    path: str
    reason: str


def _changed_python_files(git_ref: str) -> list[str]:
    """Repo-relative POSIX paths of the ``*.py`` files ``git diff`` reports as added or modified
    against *git_ref*. Tracked files only -- a file that has never been ``git add``-ed does not
    appear."""
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=AM", git_ref, "--", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


def _git_show(git_ref: str, path: str) -> str | None:
    """Content of *path* at *git_ref*, or ``None`` if it did not exist there."""
    result = subprocess.run(
        ["git", "show", f"{git_ref}:{path}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.stdout if result.returncode == 0 else None


def compare_code_shape(git_ref: str) -> list[ShapeChange]:
    """For each file :func:`_changed_python_files` reports, compares :func:`code_shape` of the
    old and new content. Returns every file whose shape moved, or that could not be compared
    (added, or fails to parse on either side) -- see :class:`ShapeChange`."""
    changes: list[ShapeChange] = []
    for rel in _changed_python_files(git_ref):
        new_path = REPO_ROOT / rel
        if not new_path.exists():
            continue  # deleted -- not part of the "code moved" proof
        old_source = _git_show(git_ref, rel)
        new_source = new_path.read_text(encoding="utf-8")
        if old_source is None:
            changes.append(ShapeChange(rel, "file added (no prior version to compare)"))
            continue
        try:
            old_shape = code_shape(old_source)
        except SyntaxError:
            changes.append(ShapeChange(rel, "old version does not parse"))
            continue
        try:
            new_shape = code_shape(new_source)
        except SyntaxError:
            changes.append(ShapeChange(rel, "new version does not parse"))
            continue
        if old_shape != new_shape:
            changes.append(ShapeChange(rel, "code shape differs"))
    return changes


# =============================================================================
# --stale-references: report only, no assertion
# =============================================================================

#: Filename stems that are legitimate in a worked example and must not be reported as stale.
#: Best-effort, not exhaustive.
_PLACEHOLDER_PATH_STEMS = frozenset(
    {
        "x",
        "y",
        "z",
        "a",
        "b",
        "c",
        "foo",
        "bar",
        "baz",
        "mod",
        "script",
        "example",
        "path",
        "file",
        "module",
        "thing",
        "pkg",
    }
)

_PY_PATH_TOKEN_RE = re.compile(r"[\w][\w./\-]*\.py\b")
_DOTTED_REF_RE = re.compile(
    r":(?:func|meth|class|mod|data|attr):`~?([\w.]+)`|``([\w]+(?:\.[\w]+){1,})``"
)

#: Top-level package names a plain double-backtick span's leading component must match to be
#: worth resolving. Without the gate a span like ``unit.parts`` -- a local variable's attribute,
#: not a module reference -- gets judged as one. Sphinx roles are not filtered this way.
_KNOWN_PACKAGE_ROOTS = frozenset({"toolguard", "tools", "test"})

#: Standard-library top-level module names appearing in this codebase's docstrings. This
#: resolver has no stdlib symbol table, so these are skipped rather than misreported as stale.
#: Incomplete by nature -- extend it when a new one shows up in the report.
_STDLIB_MODULES = frozenset(
    {
        "os",
        "sys",
        "re",
        "ast",
        "json",
        "shutil",
        "shlex",
        "subprocess",
        "pathlib",
        "dataclasses",
        "argparse",
        "tomllib",
        "importlib",
        "traceback",
        "types",
        "difflib",
        "functools",
        "itertools",
        "collections",
        "typing",
        "tokenize",
    }
)


@dataclass(frozen=True)
class StaleReference:
    """A ``.py``-looking path or dotted ``module.symbol`` reference found in a docstring that
    does not resolve against the tree as it stands."""

    path: str  # file the reference was found in
    line: int
    kind: str  # "path" | "symbol"
    reference: str


def _all_docstrings(root: Path):
    """Yields ``(repo_relative_path, base_lineno, text)`` for every docstring under *root*."""
    for py_file in _iter_python_files(root):
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except _UNREADABLE_SOURCE_ERRORS:
            continue
        rel = _repo_relative(py_file)
        for node, _owner in _iter_docstring_owners(tree):
            if not node.body:
                continue
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                yield rel, first.value.lineno, first.value.value


def _looks_like_real_path_candidate(token: str) -> bool:
    """False for obviously-synthetic placeholders: a stem in :data:`_PLACEHOLDER_PATH_STEMS`,
    or one shorter than two characters."""
    stem = Path(token).stem.lower()
    return stem not in _PLACEHOLDER_PATH_STEMS and len(stem) > 1


def _repo_basenames() -> frozenset[str]:
    """Every ``*.py`` filename (basename only) anywhere in the repo, so that a bare ``hook.py``
    in a docstring resolves even though it is not a repo-root-relative path."""
    return frozenset(
        p.name for p in REPO_ROOT.rglob("*.py") if "__pycache__" not in p.parts
    )


def find_stale_path_references(root: Path) -> list[StaleReference]:
    """Every ``.py``-looking path named in a docstring under *root* that does not exist relative
    to the repo root AND whose bare filename does not match any real file in the repo, after
    filtering out illustrative placeholders. Best-effort and report-only, not authoritative."""
    stale: list[StaleReference] = []
    basenames = _repo_basenames()
    for rel_path, base_lineno, text in _all_docstrings(root):
        for match in _PY_PATH_TOKEN_RE.finditer(text):
            token = match.group(0)
            if not _looks_like_real_path_candidate(token):
                continue
            if (REPO_ROOT / token).exists():
                continue
            if Path(token).name in basenames:
                continue
            stale.append(
                StaleReference(
                    path=rel_path,
                    line=_docstring_line_for_offset(base_lineno, text, match.start()),
                    kind="path",
                    reference=token,
                )
            )
    return stale


def _module_file_for_dotted(prefix_parts: list[str]) -> Path | None:
    """Resolves a leading run of dotted-name parts to a real ``.py`` module file under the repo,
    trying the longest prefix first (``a.b.c`` before ``a.b``)."""
    for n in range(len(prefix_parts), 0, -1):
        candidate = REPO_ROOT.joinpath(*prefix_parts[:n]).with_suffix(".py")
        if candidate.is_file():
            return candidate
        init_candidate = REPO_ROOT.joinpath(*prefix_parts[:n], "__init__.py")
        if init_candidate.is_file():
            return init_candidate
    return None


def _defines_symbol(module_file: Path, symbol: str) -> bool:
    """Best-effort: True if *symbol* occurs anywhere in *module_file* as a ``def``/``class``
    name, a bare name, or an attribute name. Not scope-aware, and a mere read counts the same as
    a definition -- this feeds a report, not a guard."""
    try:
        source = module_file.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except _UNREADABLE_SOURCE_ERRORS:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == symbol:
                return True
        elif isinstance(node, ast.Name) and node.id == symbol:
            return True
        elif isinstance(node, ast.Attribute) and node.attr == symbol:
            return True
    return False


def find_stale_symbol_references(root: Path) -> list[StaleReference]:
    """Dotted ``module.symbol`` references (Sphinx role or double-backtick code span) named in a
    docstring under *root* whose leading module path does not resolve, or whose trailing symbol
    is not found in that module by name. Several shapes are skipped rather than judged -- see
    the guards in the body. Best-effort and report-only."""
    stale: list[StaleReference] = []
    for rel_path, base_lineno, text in _all_docstrings(root):
        for match in _DOTTED_REF_RE.finditer(text):
            is_role_ref = match.group(1) is not None
            reference = match.group(1) or match.group(2)
            parts = reference.split(".")
            if len(parts) < 2:
                continue
            if parts[0] in _STDLIB_MODULES:
                continue
            # A bare double-backtick span (not a Sphinx role) is only worth resolving when it
            # looks like a real package path -- otherwise it is almost always local-variable
            # attribute access (``unit.parts``), not a module reference.
            if not is_role_ref and parts[0] not in _KNOWN_PACKAGE_ROOTS:
                continue
            # A short-form role like ``:meth:`Configuration.validation_issues``` (no
            # ``toolguard.config.`` prefix) resolves against Sphinx's current-module context,
            # which this resolver does not model -- skip rather than misreport as stale.
            if (
                is_role_ref
                and parts[0] not in _KNOWN_PACKAGE_ROOTS
                and parts[0][:1].isupper()
            ):
                continue
            line = _docstring_line_for_offset(base_lineno, text, match.start())
            # Try the whole reference as a module path first ("toolguard.resolve"), falling back
            # to "module + trailing symbol" only when that fails: a submodule is not a symbol
            # defined in its parent's __init__.py, so trying parts[:-1] first misreports it.
            if _module_file_for_dotted(parts) is not None:
                continue
            module_file = _module_file_for_dotted(parts[:-1])
            if module_file is None:
                stale.append(StaleReference(rel_path, line, "symbol", reference))
                continue
            if not _defines_symbol(module_file, parts[-1]):
                stale.append(StaleReference(rel_path, line, "symbol", reference))
    return stale


# =============================================================================
# CLI
# =============================================================================


def _print_hygiene_report() -> None:
    print("Ticket-reference hygiene report")
    print("=" * 40)
    total_doc = total_com = 0
    for name, root in SWEPT_TREES.items():
        doc_sites = docstring_ticket_refs(root)
        com_sites = comment_ticket_refs(root)
        files = len({s.path for s in doc_sites} | {s.path for s in com_sites})
        total_doc += len(doc_sites)
        total_com += len(com_sites)
        print(
            f"{name}/: {len(doc_sites)} docstring refs, {len(com_sites)} comment refs, "
            f"{files} files touched"
        )
    print(f"total: {total_doc} docstring refs, {total_com} comment refs")


def _print_compare_report(git_ref: str) -> None:
    changes = compare_code_shape(git_ref)
    print(f"code-shape comparison against {git_ref}")
    print("=" * 40)
    if not changes:
        print("No changed *.py file's code shape moved.")
        return
    for change in changes:
        print(f"  {change.path}: {change.reason}")


def _print_stale_references_report() -> None:
    print("Stale-reference reconnaissance (report only -- see module docstring)")
    print("=" * 40)
    for name, root in SWEPT_TREES.items():
        paths = find_stale_path_references(root)
        symbols = find_stale_symbol_references(root)
        print(
            f"{name}/: {len(paths)} stale path refs, {len(symbols)} stale symbol refs"
        )
        for ref in paths:
            print(f"  [path]   {ref.path}:{ref.line}  {ref.reference}")
        for ref in symbols:
            print(f"  [symbol] {ref.path}:{ref.line}  {ref.reference}")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compare-against",
        metavar="GIT_REF",
        default=None,
        help="List every changed *.py file whose code shape moved relative to GIT_REF.",
    )
    parser.add_argument(
        "--stale-references",
        action="store_true",
        help="Report .py-looking paths and dotted module.symbol references that don't resolve.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.compare_against is not None:
        _print_compare_report(args.compare_against)
    elif args.stale_references:
        _print_stale_references_report()
    else:
        _print_hygiene_report()
    return 0


if __name__ == "__main__":
    sys.exit(main())
