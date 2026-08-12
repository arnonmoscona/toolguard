"""
Verify every internal ``[text](file#anchor)`` link in the documentation resolves.

Anchors here are written by hand, or by an agent recalling GitHub's slug algorithm,
and have twice been produced with the wrong rule -- once dropping underscores, once
collapsing runs of hyphens. Neither is visible in review: the link renders normally
and lands at the top of the page instead of the section.

The rule
--------
GitHub lowercases the heading, deletes punctuation, and turns each remaining space
into a hyphen. It does NOT collapse runs of hyphens, and it does NOT drop
underscores, so punctuation sitting between words leaves consecutive hyphens::

    "Phase 0 -- Preflight"                  -> #phase-0----preflight    (four)
    "Inline interpreter code (`-c` / `-e`)" -> #inline-interpreter-code--c---e
    '`no_match_fallback = "ask"` (default)' -> #no_match_fallback--ask-default

Softening ``--`` to a single ``-`` does NOT help -- the spaces around it still become
hyphens (``"Phase 0 - Preflight"`` -> ``#phase-0---preflight``). Replacing it with a
colon does: ``"Phase 0: Preflight"`` -> ``#phase-0-preflight``.

Usage::

    uv run python tools/check_doc_links.py          # report, exit 1 if broken
    uv run python tools/check_doc_links.py --list   # also list every anchor found
"""

import argparse
import collections
import pathlib
import re
import sys

#: Files whose headings define anchors and whose links are checked.
DOC_GLOBS = ("README.md", "AGENTS.md", "llms.txt", "technical-notes.md", "CLAUDE.md")
DOC_DIRS = ("docs", "skills")

#: A markdown link whose target carries an anchor. The anchor character class MUST
#: include underscores: without them a link like ``(#no_match_fallback--ask-default)``
#: fails to match at all and is skipped in silence.
LINK_RE = re.compile(r"\[([^\]]+)\]\(([A-Za-z0-9_./-]*)#([A-Za-z0-9_-]+)\)")

HEADING_RE = re.compile(r"^(#{2,6})\s+(.*)")


def github_slug(heading: str) -> str:
    """
    Compute GitHub's anchor slug for a heading -- see the module docstring for the
    rule and its traps.

    Args:
        heading: The heading text, without its leading ``#`` markers.

    Returns:
        The anchor slug, without a leading ``#``.
    """
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    return text.replace(" ", "-")


def headings_of(path: pathlib.Path) -> list:
    """
    Extract heading texts from a markdown file, skipping fenced code blocks.

    Matches ``##`` through ``######`` only, so a top-level ``#`` heading contributes
    no anchor and a link aimed at one is reported as a bad anchor.

    Args:
        path: The file to scan.

    Returns:
        Heading texts in document order.
    """
    found, in_fence = [], False
    for line in path.read_text(errors="replace").splitlines():
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = HEADING_RE.match(line)
        if match:
            found.append(match.group(2).strip())
    return found


def anchors_of(path: pathlib.Path) -> set:
    """
    Compute every anchor a file defines, with GitHub's duplicate disambiguation.

    A slug that occurs more than once gets ``-1``, ``-2``, ... appended for the
    second and later occurrences.

    Args:
        path: The file to scan.

    Returns:
        The set of valid anchors for that file.
    """
    seen, anchors = collections.Counter(), set()
    for heading in headings_of(path):
        slug = github_slug(heading)
        index = seen[slug]
        seen[slug] += 1
        anchors.add(slug if index == 0 else f"{slug}-{index}")
    return anchors


def collect_docs(root: pathlib.Path) -> list:
    """
    Gather every documentation file to check.

    Args:
        root: Repository root.

    Returns:
        Existing paths, de-duplicated, in a stable order.
    """
    paths = [root / name for name in DOC_GLOBS]
    for directory in DOC_DIRS:
        paths.extend(sorted((root / directory).rglob("*.md")))
    return [p for p in dict.fromkeys(paths) if p.exists()]


def check(root: pathlib.Path) -> list:
    """
    Check every internal anchor link under ``root``.

    Args:
        root: Repository root.

    Returns:
        A list of ``(kind, source, target, anchor)`` problem tuples, empty when clean.
    """
    docs = collect_docs(root)
    anchor_map = {p.resolve(): anchors_of(p) for p in docs}
    problems = []
    for doc in docs:
        for _label, target, anchor in LINK_RE.findall(doc.read_text(errors="replace")):
            dest = (
                (doc.resolve().parent / target).resolve() if target else doc.resolve()
            )
            if not dest.exists():
                problems.append(("missing file", doc, target, anchor))
            elif dest not in anchor_map:
                problems.append(("unchecked file", doc, target, anchor))
            elif anchor not in anchor_map[dest]:
                problems.append(("bad anchor", doc, target or doc.name, anchor))
    return problems


def main(argv=None) -> int:
    """
    Entry point: report broken links and exit non-zero when any are found.

    Args:
        argv: Argument list, defaulting to ``sys.argv[1:]``.

    Returns:
        0 when every link resolves, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "--list", action="store_true", help="List every anchor each file defines."
    )
    args = parser.parse_args(argv)
    root = pathlib.Path(__file__).resolve().parents[1]

    if args.list:
        for doc in collect_docs(root):
            print(f"\n{doc.relative_to(root)}")
            for anchor in sorted(anchors_of(doc)):
                print(f"  #{anchor}")

    problems = check(root)
    for kind, source, target, anchor in problems:
        print(f"{kind:15} {source.relative_to(root)}: {target}#{anchor}")
    if problems:
        print(f"\n{len(problems)} broken link(s).")
        return 1
    print("All internal documentation links resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
