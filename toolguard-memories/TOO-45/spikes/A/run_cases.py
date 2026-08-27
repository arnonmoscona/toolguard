"""Runner for the shared CASES.md test set. Prints PASS/FAIL per case."""

from prepass import sinks

# (case number, command text, expected sinks in source order)
CASES = [
    (1, "python <<HD\nimport os\nHD", ["python"]),
    (2, 'bash -c "true" && python <<HD\nimport os\nHD', ["python"]),
    (3, 'bash -c "true" || python <<HD\nimport os\nHD', ["python"]),
    (4, 'bash -c "true" ; python <<HD\nimport os\nHD', ["python"]),
    (5, 'bash -c "true" & python <<HD\nimport os\nHD', ["python"]),
    (6, "python $(true; true) <<HD\nimport os\nHD", ["python"]),
    (7, "python $(which x && echo y) <<HD\nimport os\nHD", ["python"]),
    (8, "python `true; echo -` <<HD\nimport os\nHD", ["python"]),
    (9, 'python "$(true; true)" <<HD\nimport os\nHD', ["python"]),
    (10, "cat x | python <<HD\nimport os\nHD", ["python"]),
    (11, "bash <<HD\nls -la\nHD", ["bash"]),
    (12, "bash <<A <<B\necho from-A\nA\necho from-B\nB", ["bash", "bash"]),
    (13, "python3 - <<'HD' 2>/dev/null || true\nimport os\nHD", ["python3"]),
    (14, "cat <<-HD\n\tindented\nHD", ["cat"]),
    (15, 'echo "it\'s" && cat <<HD\nbody\nHD', ["cat"]),
    (16, "python <<HD | bash\nimport os\nHD", ["python"]),
]


def main() -> None:
    failures = 0
    for num, command, expected in CASES:
        actual = sinks(command)
        ok = actual == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        print(f"case {num:>2} [{status}] expected={expected} actual={actual}")
    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")


if __name__ == "__main__":
    main()
