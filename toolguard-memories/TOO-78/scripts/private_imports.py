"""
Every cross-module import of a private name inside toolguard/.

A leading-underscore name is a module's own business. Importing one from another
module is either a missing public name or a dependency that should not exist --
those are the only two honest outcomes, and this reports the sites so each can
be decided.

Covers ``from mod import _x`` (including the aliased ``_x as _x`` re-export
form). Attribute reaches (``mod._x``) are already covered for the guarded
layers by architecture_fitness's scan_private_reaches; this is the wider,
simpler question of what is imported by name.

Production code only: test/ is excluded deliberately -- a test importing a
private is legitimate.
"""

from __future__ import annotations

import ast
from pathlib import Path

TOOLGUARD = Path("/home/arnon/projects/toolguard/toolguard")


def is_private(name: str) -> bool:
    """Leading underscore, not a dunder."""
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def main() -> int:
    findings = []
    for path in sorted(TOOLGUARD.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(TOOLGUARD.parent)
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            if not node.module.startswith("toolguard"):
                continue
            for alias in node.names:
                if is_private(alias.name):
                    findings.append(
                        (str(rel), node.lineno, node.module, alias.name, alias.asname)
                    )

    print(f"{len(findings)} cross-module private import(s) in production code\n")
    for rel, lineno, module, name, asname in findings:
        reexport = "  [re-export form]" if asname == name else ""
        target = module[len("toolguard.") :]
        print(f"{rel}:{lineno}  {name}  from {target}{reexport}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
