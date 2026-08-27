"""Runner for the shared CASES.md test set (spike B). Prints pass/fail per case."""

from __future__ import annotations

from sinks import sinks

# Mirrors scratchpad/spikes/CASES.md exactly -- (number, command text, expected sinks).
CASES = [
    (1, "python <<HD\nimport os\nHD", ["python"]),
    (2, 'bash -c "true" && python <<HD\nimport os\nHD', ["python"]),
    (3, 'bash -c "true" || python <<HD\n...\nHD', ["python"]),
    (4, 'bash -c "true" ; python <<HD\n...\nHD', ["python"]),
    (5, 'bash -c "true" & python <<HD\n...\nHD', ["python"]),
    (6, "python $(true; true) <<HD\n...\nHD", ["python"]),
    (7, "python $(which x && echo y) <<HD\n...\nHD", ["python"]),
    (8, "python `true; echo -` <<HD\n...\nHD", ["python"]),
    (9, 'python "$(true; true)" <<HD\n...\nHD', ["python"]),
    (10, "cat x | python <<HD\n...\nHD", ["python"]),
    (11, "bash <<HD\nls -la\nHD", ["bash"]),
    (12, "bash <<A <<B\necho from-A\nA\necho from-B\nB", ["bash", "bash"]),
    (13, "python3 - <<'HD' 2>/dev/null || true\nimport os\nHD", ["python3"]),
    (14, "cat <<-HD\n\tindented\nHD", ["cat"]),
    (15, 'echo "it\'s" && cat <<HD\nbody\nHD', ["cat"]),
    (16, "python <<HD | bash\nimport os\nHD", ["python"]),
]


def main() -> int:
    failures = 0
    for number, text, expected in CASES:
        actual = sinks(text)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"[{status}] case {number}: expected={expected} actual={actual}")

    total = len(CASES)
    print(f"\n{total - failures}/{total} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
