"""
Which changed files carry real edits, and which are only churn?

Almost every file in this change set differs only because modules moved. To
separate those from files worth reading, each removed/added line pair is
normalised back to its pre-refactor spelling -- layer package stripped from the
dotted and file path forms, and the eight privates-made-public renamed back. If
the normalised added lines equal the normalised removed lines, the file changed
only by churn.

Anything left over is a real edit, and the file is listed for review.
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

REPO = Path("/home/arnon/projects/toolguard")

PACKAGES = (
    "integration",
    "foundation",
    "model",
    "install",
    "observability",
    "configuration",
    "engine",
)

#: Names made public in phase A, normalised back so the rename alone is churn.
PRIVATISED = {
    "locate_subsection": "_locate_subsection",
    "detect_foreign_inline_code": "_detect_foreign_inline_code",
    "combine_strictest": "_combine_strictest",
    "LiftedHeredocs": "_LiftedHeredocs",
    "UnattributableHeredocError": "_UnattributableHeredocError",
    "attribute_and_substitute": "_attribute_and_substitute",
    "normalised_body": "_normalised_body",
    "strip_tool_wrapper": "_strip_tool_wrapper",
}

_DOTTED = re.compile(r"\btoolguard\.(?:" + "|".join(PACKAGES) + r")\.")
_FILED = re.compile(r"\btoolguard/(?:" + "|".join(PACKAGES) + r")/")
_SPLIT = re.compile(r"\bmodel\.decision_types\b|\bdecision_types\b")


def normalise(line: str) -> str:
    """Undo the refactor's spelling changes, so only real edits survive."""
    line = _DOTTED.sub("toolguard.", line)
    line = _FILED.sub("toolguard/", line)
    line = _SPLIT.sub("config_types", line)
    for public, private in PRIVATISED.items():
        line = re.sub(rf"\b{public}\b", private, line)
    return line.strip()


def per_file_residue() -> dict:
    """
    ``{path: residue counter}`` from ONE whole-tree diff.

    One diff, not one per path: a per-path invocation defeats git's rename
    detection, so a moved file reads as wholly added and every move looks like
    a rewrite. That mistake inflated this report by two orders of magnitude
    before it was caught.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--cached", "-M", "-U0"],
        capture_output=True,
        text=True,
        check=True,
    )
    result: dict = {}
    path = None
    added: Counter = Counter()
    removed: Counter = Counter()

    def flush() -> None:
        if path is None:
            return
        net = Counter(added)
        net.subtract(removed)
        result[path] = Counter({k: v for k, v in net.items() if v > 0 and k})

    for line in out.stdout.splitlines():
        if line.startswith("diff --git "):
            flush()
            path = line.split(" b/", 1)[1]
            added, removed = Counter(), Counter()
        elif line.startswith(("+++", "---", "index ", "similarity ", "rename ")):
            continue
        elif line.startswith("+"):
            added[normalise(line[1:])] += 1
        elif line.startswith("-"):
            removed[normalise(line[1:])] += 1
    flush()
    return result


def main() -> int:
    churn = []
    real = []
    for path, left in per_file_residue().items():
        if not path.endswith((".py", ".toml", ".md", ".txt")):
            continue
        (real if left else churn).append((path, sum(left.values())))

    print(f"{len(churn)} file(s) changed ONLY by move/rename churn\n")
    print(f"{len(real)} file(s) with real edits:\n")
    for path, count in sorted(real, key=lambda item: -item[1]):
        print(f"  {count:5d}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
