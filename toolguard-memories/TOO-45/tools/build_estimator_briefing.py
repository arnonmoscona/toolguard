"""Rebuild the surprise-factor estimator briefing.

The estimator sees only what a person who read the ticket and skimmed the tree
would see: each module's path, line count, and FIRST DOCSTRING LINE ONLY --
no code, no imports, no call graph, no git history.

Lives here rather than in the session scratchpad because it has been destroyed
three times by scratchpad cleanup.

Usage: build_estimator_briefing.py <out.md>
"""

import ast
import sys
from pathlib import Path

REPO = Path("/home/arnon/projects/toolguard")
SCANNED = ("toolguard", "tools", "test", "scripts")


def first_docstring_line(path: Path) -> str:
    """Return the module docstring's first line, or '' when there is none."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError, ValueError, OSError:
        return ""
    doc = ast.get_docstring(tree)
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def main() -> int:
    out = Path(sys.argv[1])
    lines = ["# File inventory\n"]
    for root in SCANNED:
        base = REPO / root
        if not base.is_dir():
            continue
        files = sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)
        lines.append(f"\n## {root}/ -- {len(files)} modules\n")
        for p in files:
            rel = p.relative_to(REPO)
            n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
            doc = first_docstring_line(p)
            lines.append(f"- `{rel}` ({n} lines) -- {doc or '(no module docstring)'}")

    pyscn = REPO / ".pyscn.toml"
    if pyscn.is_file():
        lines.append("\n\n# Declared layer map (.pyscn.toml)\n")
        lines.append("```toml")
        keep, on = [], False
        for ln in pyscn.read_text(encoding="utf-8").splitlines():
            if ln.strip().startswith("["):
                on = "layer" in ln.lower() or "depend" in ln.lower()
            if on:
                keep.append(ln)
        lines.append("\n".join(keep) if keep else "(no layer section found)")
        lines.append("```")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
