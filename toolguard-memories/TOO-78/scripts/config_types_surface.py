"""
What does config_types actually contain, and which of it do engine/ and parser/ use?

Decides whether the "give engine and parser their own low-level type package"
idea means moving config_types whole, or splitting it: if the names those two
packages consume are disjoint from the config-structure names, the module is a
mixed bag and the cut runs through it rather than around it.

AST-based: a grep over import blocks over-captures neighbouring lines.
"""

from __future__ import annotations

import ast
from pathlib import Path

TOOLGUARD = Path("/home/arnon/projects/toolguard/toolguard")
TARGET = "toolguard.configuration.config_types"


def imported_names(package: str) -> set:
    """Every name imported from config_types by modules under *package*."""
    found = set()
    for path in sorted((TOOLGUARD / package).rglob("*.py")):
        for node in ast.parse(path.read_text()).body:
            if isinstance(node, ast.ImportFrom) and node.module == TARGET:
                found.update(alias.name for alias in node.names)
    return found


def defined_names() -> list:
    """Top-level classes, functions and constants config_types defines."""
    names = []
    for node in ast.parse(
        (TOOLGUARD / "configuration" / "config_types.py").read_text()
    ).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def main() -> int:
    engine = imported_names("engine")
    parser = imported_names("parser")
    consumers = engine | parser
    defined = [n for n in defined_names() if not n.startswith("_")]

    print(f"config_types defines {len(defined)} public names")
    print(f"engine/ imports {len(engine)}; parser/ imports {len(parser)}")
    print()
    print("USED by engine/ or parser/:")
    for name in sorted(consumers):
        where = []
        if name in engine:
            where.append("engine")
        if name in parser:
            where.append("parser")
        print(f"  {name}  ({', '.join(where)})")
    print()
    print("NOT used by engine/ or parser/:")
    for name in sorted(set(defined) - consumers):
        print(f"  {name}")
    unknown = consumers - set(defined)
    if unknown:
        print()
        print("imported but not defined here (re-exported through config_types):")
        for name in sorted(unknown):
            print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
