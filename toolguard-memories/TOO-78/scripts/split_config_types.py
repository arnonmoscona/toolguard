"""
What must move if the decision vocabulary leaves config_types?

Starts from the names engine/ and parser/ import, then closes over the
references between top-level definitions inside config_types: a name the moving
set mentions has to move with it, or the new package would import back into
configuration and the whole point is lost.

Prints the closed moving set, what stays, and any name that both sides need --
the last is what would make a clean split impossible.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Dict, Set

TOOLGUARD = Path("/home/arnon/projects/toolguard/toolguard")
CONFIG_TYPES = TOOLGUARD / "configuration" / "config_types.py"
TARGET = "toolguard.configuration.config_types"


def consumed_below() -> Set[str]:
    """Names engine/ and parser/ import from config_types."""
    found: Set[str] = set()
    for package in ("engine", "parser"):
        for path in sorted((TOOLGUARD / package).rglob("*.py")):
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, ast.ImportFrom) and node.module == TARGET:
                    found.update(alias.name for alias in node.names)
    return found


def definitions_and_references():
    """``({name: node}, {name: {referenced top-level names}})`` for config_types."""
    tree = ast.parse(CONFIG_TYPES.read_text())
    defined: Dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            defined[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            defined[node.target.id] = node

    refs: Dict[str, Set[str]] = {}
    for name, node in defined.items():
        mentioned: Set[str] = set()
        for inner in ast.walk(node):
            if isinstance(inner, ast.Name):
                mentioned.add(inner.id)
            elif isinstance(inner, ast.Attribute):
                pass
            elif isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                # Forward references live in string annotations.
                if inner.value in defined:
                    mentioned.add(inner.value)
        refs[name] = {m for m in mentioned if m in defined and m != name}
    return defined, refs


def main() -> int:
    defined, refs = definitions_and_references()
    seed = consumed_below() & set(defined)

    moving = set(seed)
    while True:
        grown = set(moving)
        for name in moving:
            grown |= refs.get(name, set())
        if grown == moving:
            break
        moving = grown

    staying = set(defined) - moving

    # A staying name that references a moving one is fine (configuration may
    # import model). A MOVING name referencing a staying one is the blocker.
    blockers = {
        name: sorted(refs[name] & staying)
        for name in sorted(moving)
        if refs[name] & staying
    }

    print(f"config_types defines {len(defined)} top-level names")
    print(f"engine/parser import {len(seed)} of them directly")
    print(f"closure of the moving set: {len(moving)}")
    print()
    print("MOVES to the new package:")
    for name in sorted(moving):
        pulled = "" if name in seed else "   (pulled in by a reference)"
        print(f"  {name}{pulled}")
    print()
    print("STAYS in configuration:")
    for name in sorted(staying):
        print(f"  {name}")
    print()
    if blockers:
        print("BLOCKERS -- moving names that reference staying names:")
        for name, targets in blockers.items():
            print(f"  {name} -> {', '.join(targets)}")
    else:
        print("No blockers: the moving set is closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
