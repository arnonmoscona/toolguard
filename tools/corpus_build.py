#!/usr/bin/env python
"""
Dev-only tool (repo-root ``tools/``, NOT shipped -- see ``.pyproject.toml``'s
``[tool.hatch.build.targets.wheel] packages`` list, which does not include
this directory) that builds and verifies the TOO-45 verdict-equivalence
corpus under ``test/verdict_corpus/``.

The corpus is the safety guard for the upcoming permission-engine refactor: it
replays a fixed set of ``(config, tool, target)`` cases through
:func:`toolguard.tools.decision.decide` and pins the result. See
``test/verdict_corpus/README.md`` for what the corpus is for and how goldens
are meant to be updated (never by blindly regenerating after a failure).

Stdlib only -- this project's runtime carries no third-party dependency, and
this tool, while not shipped, follows the same discipline so it never needs
one either.

Two corpora, one CLI
--------------------
Every mode below drives BOTH the fast in-process corpus (``cases.jsonl`` /
``goldens.jsonl``, calling :func:`toolguard.tools.decision.decide` directly)
and the small end-to-end corpus (``e2e_cases.jsonl`` / ``e2e_goldens.jsonl``,
running the real hook binary in a subprocess via
:meth:`~toolguard.testing.sandbox.Sandbox.run_hook`). The end-to-end corpus
exists because the in-process one stops at the decision itself and cannot see
:func:`toolguard.hook.create_hook_output` -- the seam that turns a decision
into the actual JSON Claude Code receives (and where a real defect once
silently dropped ``additionalContext`` from the hook's output entirely,
undetected by decision-level testing). See
``test/verdict_corpus/README.md`` for the full rationale.

Modes
-----
``--extract``
    Rebuild ``cases.jsonl`` from two sources: (1) real traffic, parsed from
    ``logs/toolguard-*.md`` (READ ONLY) into the ``realistic`` fixture, and
    (2) hand-authored synthetic cases (see :data:`SYNTHETIC_CASES` below) for
    every other fixture in :data:`~test.verdict_corpus.fixture_loader.FIXTURE_IDS`.
    Also rebuilds ``e2e_cases.jsonl`` from :data:`E2E_CASES`.
``--generate``
    Replay every case in ``cases.jsonl`` through :func:`~toolguard.tools.decision.decide`
    and (re)write ``goldens.jsonl``. Also replays every case in
    ``e2e_cases.jsonl`` through the real hook subprocess and (re)writes
    ``e2e_goldens.jsonl``.
``--verify``
    Replay every case IN MEMORY and diff the result against the committed
    goldens (both corpora). Writes nothing. Exits non-zero on any hard
    difference (verdict; for the end-to-end corpus, also the presence/absence
    of the ``additionalContext`` key) or corpus data-integrity problem (a case
    with no golden, or a golden with no case); prints tracked-field
    (reason/context/provenance) differences for human review without failing
    the exit code, UNLESS ``--strict-prose`` is also given.

Usage::

    uv run python tools/corpus_build.py --extract
    uv run python tools/corpus_build.py --generate
    uv run python tools/corpus_build.py --verify
"""

import argparse
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Repo root is already on sys.path (editable install of the `toolguard`
# package adds it), so `import test...` and `import toolguard...` both work
# regardless of the cwd this script is invoked from -- verified empirically
# rather than assumed; see the TOO-45 coder task-recall note for the check.
from test.verdict_corpus.fixture_loader import (
    CASES_PATH,
    CORPUS_DIR,
    E2E_CASES_PATH,
    E2E_GOLDENS_PATH,
    FIXTURE_IDS,
    GOLDENS_PATH,
    compare_e2e_goldens,
    compare_goldens,
    generate_e2e_goldens_in_memory,
    generate_goldens_in_memory,
    read_jsonl,
    write_jsonl,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = REPO_ROOT / "logs"

# ---------------------------------------------------------------------------
# Sanitization -- machine-specific strings, applied to extracted commands AND
# (once, by hand, when the `realistic` fixture's config files were snapshotted)
# to the fixture's config text, so pattern matching is preserved on both sides.
# ---------------------------------------------------------------------------

#: The real project root, computed rather than hardcoded so this keeps working
#: if the repo is ever cloned somewhere else. Replaced FIRST (an exact literal
#: prefix), before the looser username-only rule below.
_REAL_PROJECT_ROOT = str(REPO_ROOT)

#: `/home/arnon` followed by a non-word character (or end of string) is the
#: real user's home. The trailing `\b` deliberately does NOT match
#: `/home/arnontoho` or `/home/arno` -- both distinct, already-fake usernames
#: that appear in the logs from unrelated sandboxed experiments -- since
#: there is no word boundary between "arnon" and a following word character.
_HOME_ARNON_RE = re.compile(r"/home/arnon\b")


def sanitize_machine_paths(text: str) -> str:
    """
    Replace real-machine-specific absolute paths with portable placeholders.

    Args:
        text: Raw text (an extracted command, or fixture config content).

    Returns:
        *text* with the real repo root replaced by
        ``/home/tguser/projects/toolguard`` and any other ``/home/arnon``
        occurrence replaced by ``/home/tguser``.
    """
    text = text.replace(_REAL_PROJECT_ROOT, "/home/tguser/projects/toolguard")
    text = _HOME_ARNON_RE.sub("/home/tguser", text)
    return text


# ---------------------------------------------------------------------------
# Log parsing (case source 1: real traffic)
# ---------------------------------------------------------------------------

_ENTRY_HEADER_RE = re.compile(r"^## \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
_DISCOVERY_PREFIX = "- **Discovery**:"
_COMMAND_PREFIX = "- **Command**: `"
_FILE_TOOL_RE = re.compile(
    r"^(Write|Edit|Read|MultiEdit|NotebookEdit)\((.*)\)$", re.DOTALL
)


class LogFormatError(ValueError):
    """Raised when a log entry does not match the verified format."""


def _extract_command(block: List[str], start_index: int) -> str:
    """
    Accumulate a (possibly multi-line) ``- **Command**: `...``` field's value.

    A naive "keep reading until the total backtick count is even" parity rule
    (the most literal reading of "accumulate until backticks balance") turns
    out to be WRONG on real data: a genuine, verified single-line entry exists
    (``logs/toolguard-2026-07-24.md:157``, ``grep -n "^#### \\`"``) whose
    command text contains exactly one unpaired literal backtick, making the
    line's total backtick count odd even though the field is not continued.
    "Balance" therefore cannot mean literal parity of every backtick on the
    line -- the log writer never escapes backticks inside the command, so a
    lone one is indistinguishable from a delimiter by counting alone.

    The rule that IS reliable on this corpus (checked against all 9,896
    Command entries, both single- and multi-line): the log writer always
    places the closing delimiter as the LAST character of ITS line, with
    nothing following it -- true for every observed single-line entry and
    every observed multi-line one (the closing backtick sits at the very end
    of the final continuation line, immediately before the next field or
    blank line). So: keep appending whole lines until the current line ends
    with a backtick, then take everything up to that backtick's position
    (found via ``rfind``, which is exactly right even when the command's OWN
    text also ends in a backtick, since that backtick and the closing
    delimiter would then be adjacent and ``rfind`` still locates the last of
    the two -- the true delimiter -- correctly).

    Args:
        block: All lines of this log entry.
        start_index: Index of the line starting with :data:`_COMMAND_PREFIX`.

    Returns:
        The command text, with the wrapping backticks removed.

    Raises:
        LogFormatError: No line ends with a backtick before the block ends.
    """
    first_line = block[start_index]
    buf = [first_line[len(_COMMAND_PREFIX) :]]
    index = start_index
    while not buf[-1].endswith("`"):
        index += 1
        if index >= len(block):
            raise LogFormatError(
                f"Command field starting at block line {start_index} never "
                f"finds a closing backtick: {block[start_index]!r}"
            )
        buf.append(block[index])
    text = "\n".join(buf)
    return text[: text.rfind("`")]


def _parse_tool_target(command_text: str) -> Tuple[str, str]:
    """
    Split an extracted command string into ``(tool, target)``.

    Args:
        command_text: The raw value of a Command field.

    Returns:
        ``(tool, target)`` -- a file-tool wrapper's name and inner argument
        when the text matches ``^(Write|Edit|Read|MultiEdit|NotebookEdit)\\(.*\\)$``,
        otherwise ``('Bash', command_text)``.
    """
    match = _FILE_TOOL_RE.match(command_text)
    if match:
        return match.group(1), match.group(2)
    return "Bash", command_text


class LogParseStats:
    """Running counts across every parsed log file, for the verified-count check."""

    def __init__(self) -> None:
        self.total_entries = 0
        self.discovery_entries = 0
        self.command_entries = 0


def parse_log_file(path: Path, stats: LogParseStats) -> List[Tuple[str, str]]:
    """
    Parse one ``logs/toolguard-*.md`` file into sanitized ``(tool, target)`` pairs.

    Args:
        path: The log file to parse.
        stats: Running totals, updated in place.

    Returns:
        One ``(tool, target)`` pair per Command entry in this file (not yet
        deduplicated across files).

    Raises:
        LogFormatError: An entry has neither a Discovery nor a Command field.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    header_indices = [i for i, line in enumerate(lines) if _ENTRY_HEADER_RE.match(line)]
    pairs: List[Tuple[str, str]] = []
    for position, start in enumerate(header_indices):
        end = (
            header_indices[position + 1]
            if position + 1 < len(header_indices)
            else len(lines)
        )
        block = lines[start:end]
        stats.total_entries += 1

        if any(line.startswith(_DISCOVERY_PREFIX) for line in block):
            stats.discovery_entries += 1
            continue

        command_index = next(
            (i for i, line in enumerate(block) if line.startswith(_COMMAND_PREFIX)),
            None,
        )
        if command_index is None:
            raise LogFormatError(
                f"{path}:{start + 1}: entry has neither a Discovery nor a Command field"
            )
        stats.command_entries += 1
        command_text = _extract_command(block, command_index)
        tool, target = _parse_tool_target(command_text)
        pairs.append((tool, sanitize_machine_paths(target)))
    return pairs


#: The three counts the spec requires the parser to reproduce exactly.
EXPECTED_TOTAL_ENTRIES = 16906
EXPECTED_DISCOVERY_ENTRIES = 7010
EXPECTED_COMMAND_ENTRIES = 9896


#: Matches ONLY the date-stamped decision logs (``toolguard-YYYY-MM-DD.md``).
#: ``logs/`` also holds ``toolguard-warning-*.md`` and ``toolguard-error-*.md``,
#: which use a completely different entry format (``## <timestamp> - WARNING``
#: with ``**Message**``/``**Corrective Steps**`` fields, no Status/Command).
#: Their headers happen not to collide with :data:`_ENTRY_HEADER_RE` (the
#: trailing `` - WARNING`` breaks the anchored match), so a loose
#: ``toolguard-*.md`` glob turned out NOT to be the cause of the count
#: mismatch investigated below -- excluding them is still correct on intent
#: (they are not decision-log entries and must never be parsed as one), just
#: not what explained the discrepancy that day.
_DECISION_LOG_RE = re.compile(r"^toolguard-\d{4}-\d{2}-\d{2}\.md$")


def parse_all_logs() -> Tuple[List[Tuple[str, str]], LogParseStats]:
    """
    Parse every date-stamped ``logs/toolguard-YYYY-MM-DD.md`` decision log, in
    sorted (deterministic) order. Deliberately excludes
    ``toolguard-warning-*.md`` and ``toolguard-error-*.md`` -- see
    :data:`_DECISION_LOG_RE`.

    Returns:
        ``(pairs, stats)`` -- all extracted ``(tool, target)`` pairs (NOT yet
        deduplicated) across every file, and the aggregate :class:`LogParseStats`.
    """
    stats = LogParseStats()
    all_pairs: List[Tuple[str, str]] = []
    paths = sorted(p for p in LOGS_DIR.glob("*.md") if _DECISION_LOG_RE.match(p.name))
    for path in paths:
        all_pairs.extend(parse_log_file(path, stats))
    return all_pairs, stats


def dedupe_pairs(pairs: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Deduplicate ``(tool, target)`` pairs, preserving first-seen order."""
    return list(dict.fromkeys(pairs))


def check_log_counts(stats: LogParseStats) -> None:
    """
    Report parsed counts and compare them against the TOO-45 spec's verified
    snapshot (7,010 Discovery / 9,896 Command / 16,906 total).

    ``logs/`` is a live, append-only directory that keeps growing -- including
    from this very tool's own read-only diagnostic runs during development --
    so an exact match is not expected on every invocation; a HIGHER total than
    the snapshot is normal, not a bug. What WOULD indicate a genuine parser
    bug is a mismatched ``discovery_entries`` count specifically (config
    discovery is logged at most once per session, so it grows far more slowly
    than Command entries) -- checked and flagged separately from the other
    two. See the TOO-45 coder task-recall note (basic-memory) for the
    isolation experiment (excluding just the actively-growing file for today's
    date reproduces the spec's three numbers exactly).

    Args:
        stats: Aggregate counts from :func:`parse_all_logs`.
    """
    print(
        f"Parsed {stats.total_entries} total log entries "
        f"({stats.discovery_entries} Discovery, {stats.command_entries} Command).",
        file=sys.stderr,
    )
    exact = (
        stats.total_entries,
        stats.discovery_entries,
        stats.command_entries,
    ) == (EXPECTED_TOTAL_ENTRIES, EXPECTED_DISCOVERY_ENTRIES, EXPECTED_COMMAND_ENTRIES)
    if exact:
        print("Matches the TOO-45 spec's verified counts exactly.", file=sys.stderr)
        return
    print(
        "NOTE: does not exactly match the TOO-45 spec's verified snapshot "
        f"(total={EXPECTED_TOTAL_ENTRIES}, discovery={EXPECTED_DISCOVERY_ENTRIES}, "
        f"command={EXPECTED_COMMAND_ENTRIES}). Expected: logs/ keeps growing. "
        f"discovery_entries {'MATCHES' if stats.discovery_entries == EXPECTED_DISCOVERY_ENTRIES else 'DIFFERS -- investigate'}.",
        file=sys.stderr,
    )


# ---------------------------------------------------------------------------
# Case source 2: synthetic fixtures (hand-authored, 15-30 cases per fixture)
# ---------------------------------------------------------------------------

#: Shared by the four `fallback_*` fixtures, whose configs differ ONLY in
#: `no_match_fallback`'s value -- replaying the SAME cases against all four
#: directly shows how one command's outcome changes across every setting.
_FALLBACK_CASES: List[Tuple[str, str]] = [
    ("Bash", "ls -la"),
    ("Bash", "pwd"),
    ("Bash", "sudo reboot"),
    ("Bash", "sudo -l"),
    ("Bash", "echo hello"),
    ("Bash", "whoami"),
    ("Bash", "date"),
    ("Bash", "ls -la && echo done"),
    ("Bash", "sudo reboot && ls -la"),
    ("Bash", "ls -la | wc -l"),
    ("Bash", "cat file.txt"),
    ("Read", "/home/tguser/projects/toolguard/README.md"),
    ("Write", "./scratch/x.txt"),
    ("Edit", "~/.bashrc"),
    ("Bash", "ls -la /tmp"),
]

#: Shared by the three `undecidable_*` fixtures, whose configs differ ONLY in
#: `undecidable_fallback`'s value.
_UNDECIDABLE_CASES: List[Tuple[str, str]] = [
    ("Bash", "ls -la"),
    ("Bash", "sudo reboot"),
    ("Bash", "diff <(ls) <(ls -la)"),
    ("Bash", "comm -13 <(sort a) <(sort b)"),
    ("Bash", "diff <(cat a) <(cat b) && ls -la"),
    ("Bash", "sudo reboot && diff <(ls) <(pwd)"),
    ("Bash", "echo $(cat <(echo hi))"),
    ("Bash", "diff <(ls -la) <(pwd)"),
    ("Bash", "ls -la | diff - <(pwd)"),
    ("Bash", "unmatched-command-xyz"),
    ("Read", "/home/tguser/projects/toolguard/README.md"),
    ("Bash", "diff <(git log) <(git log --oneline)"),
    ("Bash", "cat <<'EOF' | diff - <(echo hi)\nfoo\nEOF"),
    ("Bash", "sudo -l"),
    ("Bash", "ls -la /tmp"),
]

SYNTHETIC_CASES: Dict[str, List[Tuple[str, str]]] = {
    "empty": [
        ("Bash", "ls -la"),
        ("Bash", "pwd"),
        ("Bash", "echo hello"),
        ("Bash", "sudo reboot"),
        ("Bash", "rm -rf /"),
        ("Bash", "ls -la && pwd"),
        ("Bash", "false || true"),
        ("Bash", "echo a; echo b"),
        ("Bash", "ls | grep foo"),
        ("Bash", "cat <<'EOF'\nhello\nEOF"),
        ("Bash", "diff <(ls) <(ls -la)"),
        ("Read", "/home/tguser/projects/toolguard/README.md"),
        ("Write", "./scratch/new.txt"),
        ("Edit", "~/.bashrc"),
        ("Bash", "git status"),
    ],
    "fallback_ask": list(_FALLBACK_CASES),
    "fallback_deny": list(_FALLBACK_CASES),
    "fallback_allow_warning": list(_FALLBACK_CASES),
    "fallback_allow_silent": list(_FALLBACK_CASES),
    "undecidable_ask": list(_UNDECIDABLE_CASES),
    "undecidable_deny": list(_UNDECIDABLE_CASES),
    "undecidable_allow": list(_UNDECIDABLE_CASES),
    "hard_deny": [
        ("Bash", "rm -rf /"),
        ("Bash", "rm file.txt"),
        ("Bash", "rm -rf /tmp/foo"),
        ("Bash", "curl https://evil.example.com"),
        ("Bash", "curl -X POST https://api.example.com"),
        ("Bash", "curl localhost:8080/health"),
        ("Bash", "curl localhost"),
        ("Bash", "curl 127.0.0.1:9000/status"),
        ("Bash", "curl 127.0.0.1"),
        ("Read", "/home/tguser/.env"),
        ("Read", "/home/tguser/projects/toolguard/.env"),
        ("Read", "/home/tguser/.ssh/id_rsa"),
        ("Read", "/home/tguser/projects/toolguard/notes.md"),
        ("Read", "/home/tguser/projects/toolguard/config/.ssh/known_hosts"),
        ("Bash", "rm file.txt && curl localhost"),
        ("Bash", "rm -rf / && ls"),
        ("Bash", "sudo rm -rf /"),
    ],
    "parse_failure": [
        ("Bash", "ls -la"),
        ("Bash", "ls"),
        ("Bash", "rm -rf /"),
        ("Bash", "unmatched-command"),
        ("Bash", "cat file.txt"),
        ("Read", "/home/tguser/projects/toolguard/README.md"),
        ("Bash", "ls -la && rm -rf /"),
        ("Bash", "sudo ls"),
        ("Write", "./scratch/x.txt"),
        ("Bash", "ls -la /var/log"),
        ("Bash", "curl bad"),
        ("Edit", "~/.bashrc"),
        ("Bash", "rm -rf /tmp"),
        ("Bash", "ls -la && cat notes.txt"),
        ("Bash", "ls -la /home"),
    ],
    "hierarchy_conflict": [
        ("Bash", "rm important-file backup.txt"),
        ("Bash", "rm important-file old.log"),
        ("Bash", "ls -la"),
        ("Bash", "ls"),
        ("Bash", "rm important-file"),
        ("Bash", "ls /tmp"),
        ("Bash", "rm important-file backup.txt && ls -la"),
        ("Bash", "pwd"),
        ("Bash", "echo hi"),
        ("Bash", "rm important-file a.txt && rm important-file b.txt"),
        ("Bash", "ls -la && ls -l"),
        ("Bash", "rm important-file data/report.csv"),
        ("Bash", "ls -la /var"),
        ("Bash", "rm important-file with spaces file.txt"),
        ("Bash", "ls -R"),
    ],
    "pattern_forms": [
        ("Bash", "git status"),
        ("Bash", "git log"),
        ("Bash", "git log --oneline"),
        ("Bash", "git show abc123"),
        ("Bash", "git show"),
        ("Bash", "git diff HEAD~1"),
        ("Bash", "git diff"),
        ("Bash", "git push origin main"),
        ("Bash", "git reset --hard HEAD~1"),
        ("Bash", "git commit -m 'x'"),
        ("Read", "./docs/architecture.md"),
        ("Read", "./README.md"),
        ("Read", "./test/unit/test_hook.py"),
        ("Read", "./docs/nested/sub/file.md"),
        ("Write", "./scratch/output.txt"),
        ("Read", "./other/file.txt"),
        ("Write", "./elsewhere/file.txt"),
    ],
    "enrichment": [
        ("Bash", "ls -la"),
        ("Bash", "cat file.txt"),
        ("Bash", "pwd"),
        ("Bash", "rm file.txt"),
        ("Bash", "sudo reboot"),
        ("Bash", "curl -X DELETE https://api.example.com/x"),
        ("Bash", "ls -la && cat file.txt"),
        ("Bash", "cat a.txt && cat b.txt"),
        ("Bash", "sudo reboot && ls -la"),
        ("Bash", "ls -la && rm file.txt"),
        ("Bash", "rm a.txt && rm b.txt"),
        ("Bash", "pwd && ls -la"),
        ("Bash", "echo hi"),
        ("Bash", "curl -X GET https://api.example.com/x"),
        ("Bash", "sudo reboot && curl -X DELETE https://x"),
        ("Bash", "cat a.txt && sudo reboot && ls -la"),
    ],
}


def build_synthetic_cases() -> List[Dict[str, str]]:
    """
    Turn :data:`SYNTHETIC_CASES` into ``cases.jsonl``-shaped records.

    Returns:
        One ``{"fixture", "tool", "target"}`` dict per synthetic case, in
        :data:`~test.verdict_corpus.fixture_loader.FIXTURE_IDS` order (skipping
        ``realistic``, whose cases come from real traffic instead).
    """
    records = []
    for fixture_id in FIXTURE_IDS:
        if fixture_id == "realistic":
            continue
        cases = SYNTHETIC_CASES.get(fixture_id)
        if not cases:
            raise ValueError(f"no synthetic cases defined for fixture {fixture_id!r}")
        for tool, target in cases:
            records.append({"fixture": fixture_id, "tool": tool, "target": target})
    return records


#: End-to-end cases: (fixture, tool, target) triples, replayed through the
#: REAL hook subprocess (see ``e2e_cases.jsonl``/``e2e_goldens.jsonl``).
#: Deliberately small (subprocess startup dominates) and deliberately reuses
#: EXISTING fixtures rather than inventing new ones -- no new configuration
#: shape is needed to exercise the output-JSON seam, only a hand-picked subset
#: of cases already known to hit allow/ask/deny, the enrichment paths (present,
#: absent, and multi-part accumulated), the parse-failure ASK floor, the
#: undecidable floor, hard_deny, a compound command, and a file-tool target.
E2E_CASES: List[Tuple[str, str, str]] = [
    # --- enrichment: present / absent / multi-part accumulation ---
    ("enrichment", "Bash", "ls -la"),  # allow, additionalContext present
    ("enrichment", "Bash", "pwd"),  # allow, additionalContext ABSENT (plain rule)
    ("enrichment", "Bash", "rm file.txt"),  # ask, additionalContext present
    ("enrichment", "Bash", "sudo reboot"),  # deny, additionalContext present
    (
        "enrichment",
        "Bash",
        "curl -X DELETE https://api.example.com/x",
    ),  # hard deny, additionalContext present
    ("enrichment", "Bash", "ls -la && cat file.txt"),  # allow, MULTI-PART accumulated
    ("enrichment", "Bash", "cat a.txt && cat b.txt"),  # allow, same-rule accumulation
    (
        "enrichment",
        "Bash",
        "pwd && ls -la",
    ),  # allow, accumulation with a no-context rule
    ("enrichment", "Bash", "echo hi"),  # ask (unmatched fallback), no context
    # --- parse_failure: ASK floor clamps a would-be allow; deny stays deny ---
    ("parse_failure", "Bash", "ls -la"),
    ("parse_failure", "Bash", "rm -rf /"),
    # --- undecidable floor, all three settings ---
    ("undecidable_ask", "Bash", "diff <(ls) <(ls -la)"),
    ("undecidable_deny", "Bash", "diff <(ls) <(ls -la)"),
    ("undecidable_allow", "Bash", "diff <(ls) <(ls -la)"),
    # --- hard_deny: deny, carve-out allow, and a file-tool hard deny ---
    ("hard_deny", "Bash", "rm -rf /"),
    ("hard_deny", "Bash", "curl https://evil.example.com"),
    ("hard_deny", "Bash", "curl localhost:8080/health"),
    ("hard_deny", "Read", "/home/tguser/.env"),
    ("hard_deny", "Bash", "rm -rf / && ls"),  # compound; hard-deny wins
    # --- plain allow/ask/deny baseline ---
    ("fallback_ask", "Bash", "ls -la"),
    ("fallback_ask", "Bash", "sudo reboot"),
    ("fallback_ask", "Bash", "echo hello"),
    ("empty", "Bash", "ls -la"),  # no config at all
    # --- file-tool targets: allow (regex form matches the raw relative
    # target directly), ask (unmatched), and hard_deny's Read('.env') above
    # covers file-tool deny ---
    ("pattern_forms", "Read", "./docs/architecture.md"),
    ("pattern_forms", "Write", "./scratch/output.txt"),
    # --- pattern forms / compound / hierarchy ---
    ("pattern_forms", "Bash", "git status"),
    ("pattern_forms", "Bash", "git push origin main"),
    ("hierarchy_conflict", "Bash", "rm important-file backup.txt && ls -la"),
    # --- the full realistic config stack, end to end ---
    ("realistic", "Bash", "git status"),
    ("realistic", "Bash", "gh status"),
]


def build_e2e_cases() -> List[Dict[str, str]]:
    """
    Turn :data:`E2E_CASES` into ``e2e_cases.jsonl``-shaped records.

    Returns:
        One ``{"fixture", "tool", "target"}`` dict per end-to-end case.
    """
    return [
        {"fixture": fixture_id, "tool": tool, "target": target}
        for fixture_id, tool, target in E2E_CASES
    ]


def build_realistic_cases() -> List[Dict[str, str]]:
    """
    Parse ``logs/toolguard-*.md`` and build the ``realistic`` fixture's cases.

    Returns:
        One ``{"fixture": "realistic", "tool", "target"}`` dict per distinct
        sanitized ``(tool, target)`` pair found in real traffic.
    """
    pairs, stats = parse_all_logs()
    check_log_counts(stats)
    deduped = dedupe_pairs(pairs)
    print(
        f"{len(pairs)} Command entries -> {len(deduped)} distinct (tool, target) pairs.",
        file=sys.stderr,
    )
    return [
        {"fixture": "realistic", "tool": tool, "target": target}
        for tool, target in deduped
    ]


# ---------------------------------------------------------------------------
# CLI modes
# ---------------------------------------------------------------------------


def cmd_extract(_args: argparse.Namespace) -> int:
    """Rebuild ``cases.jsonl`` and ``e2e_cases.jsonl`` from their sources."""
    cases = build_realistic_cases() + build_synthetic_cases()
    write_jsonl(CASES_PATH, cases)
    print(f"Wrote {len(cases)} cases to {CASES_PATH}", file=sys.stderr)

    e2e_cases = build_e2e_cases()
    write_jsonl(E2E_CASES_PATH, e2e_cases)
    print(
        f"Wrote {len(e2e_cases)} end-to-end cases to {E2E_CASES_PATH}", file=sys.stderr
    )
    return 0


def cmd_generate(_args: argparse.Namespace) -> int:
    """Regenerate ``goldens.jsonl`` and ``e2e_goldens.jsonl`` by replaying their cases."""
    cases = read_jsonl(CASES_PATH)
    if not cases:
        print(
            f"No cases found at {CASES_PATH} -- run --extract first.", file=sys.stderr
        )
        return 1
    started = time.monotonic()
    goldens = generate_goldens_in_memory(cases)
    elapsed = time.monotonic() - started
    write_jsonl(GOLDENS_PATH, goldens)
    print(
        f"Wrote {len(goldens)} goldens to {GOLDENS_PATH} ({elapsed:.2f}s)",
        file=sys.stderr,
    )

    e2e_cases = read_jsonl(E2E_CASES_PATH)
    if not e2e_cases:
        print(
            f"No end-to-end cases found at {E2E_CASES_PATH} -- run --extract first.",
            file=sys.stderr,
        )
        return 1
    started = time.monotonic()
    e2e_goldens = generate_e2e_goldens_in_memory(e2e_cases)
    elapsed = time.monotonic() - started
    write_jsonl(E2E_GOLDENS_PATH, e2e_goldens)
    print(
        f"Wrote {len(e2e_goldens)} end-to-end goldens to {E2E_GOLDENS_PATH} ({elapsed:.2f}s)",
        file=sys.stderr,
    )
    return 0


def _print_comparison(result) -> None:
    """Print a human-readable report of a :class:`~test.verdict_corpus.fixture_loader.ComparisonResult`."""
    if result.missing_goldens:
        print(
            f"\n{len(result.missing_goldens)} case(s) with NO committed golden (run --generate):"
        )
        for key in result.missing_goldens:
            print(f"  MISSING GOLDEN: {key}")
    if result.extra_goldens:
        print(
            f"\n{len(result.extra_goldens)} committed golden(s) with NO matching case:"
        )
        for key in result.extra_goldens:
            print(f"  STALE GOLDEN: {key}")
    if result.verdict_mismatches:
        print(
            f"\n{len(result.verdict_mismatches)} VERDICT MISMATCH(ES) -- STOP AND INVESTIGATE, do not regenerate:"
        )
        for mismatch in result.verdict_mismatches:
            print(
                f"  [{mismatch.fixture}] {mismatch.tool}({mismatch.target!r}): "
                f"expected={mismatch.expected_verdict!r} actual={mismatch.actual_verdict!r}"
            )
    if result.prose_diffs:
        print(
            f"\n{len(result.prose_diffs)} tracked (reason/context/provenance) "
            "difference(s) -- review, and see README.md for the acknowledgement procedure:"
        )
        for diff in result.prose_diffs:
            print(f"  [{diff.fixture}] {diff.tool}({diff.target!r}).{diff.field}:")
            print(f"    expected: {diff.expected!r}")
            print(f"    actual  : {diff.actual!r}")


def _print_e2e_comparison(result) -> None:
    """Print a human-readable report of an :class:`~test.verdict_corpus.fixture_loader.E2EComparisonResult`."""
    if result.missing_goldens:
        print(
            f"\n{len(result.missing_goldens)} end-to-end case(s) with NO committed golden (run --generate):"
        )
        for key in result.missing_goldens:
            print(f"  MISSING E2E GOLDEN: {key}")
    if result.extra_goldens:
        print(
            f"\n{len(result.extra_goldens)} committed end-to-end golden(s) with NO matching case:"
        )
        for key in result.extra_goldens:
            print(f"  STALE E2E GOLDEN: {key}")
    if result.hard_mismatches:
        print(
            f"\n{len(result.hard_mismatches)} E2E HARD MISMATCH(ES) -- STOP AND INVESTIGATE, do not regenerate:"
        )
        for mismatch in result.hard_mismatches:
            print(
                f"  [{mismatch.fixture}] {mismatch.tool}({mismatch.target!r}).{mismatch.kind}: "
                f"expected={mismatch.expected!r} actual={mismatch.actual!r}"
            )
    if result.prose_diffs:
        print(
            f"\n{len(result.prose_diffs)} tracked E2E (reason/additionalContext text) "
            "difference(s) -- review, and see README.md for the acknowledgement procedure:"
        )
        for diff in result.prose_diffs:
            print(f"  [{diff.fixture}] {diff.tool}({diff.target!r}).{diff.field}:")
            print(f"    expected: {diff.expected!r}")
            print(f"    actual  : {diff.actual!r}")


def cmd_verify(args: argparse.Namespace) -> int:
    """Regenerate both corpora in memory and diff against their committed goldens. Writes nothing."""
    cases = read_jsonl(CASES_PATH)
    expected = read_jsonl(GOLDENS_PATH)
    e2e_cases = read_jsonl(E2E_CASES_PATH)
    e2e_expected = read_jsonl(E2E_GOLDENS_PATH)
    if not cases or not expected:
        print(
            f"cases.jsonl or goldens.jsonl missing/empty under {CORPUS_DIR}.",
            file=sys.stderr,
        )
        return 1
    if not e2e_cases or not e2e_expected:
        print(
            f"e2e_cases.jsonl or e2e_goldens.jsonl missing/empty under {CORPUS_DIR}.",
            file=sys.stderr,
        )
        return 1

    started = time.monotonic()
    actual = generate_goldens_in_memory(cases)
    in_process_elapsed = time.monotonic() - started
    result = compare_goldens(expected, actual)
    _print_comparison(result)

    started = time.monotonic()
    e2e_actual = generate_e2e_goldens_in_memory(e2e_cases)
    e2e_elapsed = time.monotonic() - started
    e2e_result = compare_e2e_goldens(e2e_expected, e2e_actual)
    _print_e2e_comparison(e2e_result)

    print(
        f"\nIn-process: {len(cases)} cases in {in_process_elapsed:.2f}s. "
        f"End-to-end: {len(e2e_cases)} cases in {e2e_elapsed:.2f}s."
    )

    hard_failure = result.has_hard_failures or e2e_result.has_hard_failures
    prose_diff = result.has_prose_diffs or e2e_result.has_prose_diffs
    if hard_failure:
        print("\nFAIL: hard verdict/output/data-integrity differences found.")
        return 1
    if prose_diff and args.strict_prose:
        print("\nFAIL: tracked-field differences found and --strict-prose was given.")
        return 1
    if prose_diff:
        print(
            "\nOK (verdicts/output unchanged); tracked-field differences above are "
            "informational. Re-run with --strict-prose to fail on them too."
        )
        return 0
    print("\nOK: no differences.")
    return 0


def _build_argparser() -> argparse.ArgumentParser:
    """Build the CLI parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Build and verify the TOO-45 verdict-equivalence corpus "
            "(test/verdict_corpus/)."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--extract",
        action="store_true",
        help="Rebuild cases.jsonl from logs + synthetic fixtures.",
    )
    mode.add_argument(
        "--generate",
        action="store_true",
        help="Regenerate goldens.jsonl by replaying cases.jsonl.",
    )
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Regenerate in memory and diff against goldens.jsonl.",
    )
    parser.add_argument(
        "--strict-prose",
        action="store_true",
        help="With --verify: also fail (exit 1) on tracked reason/context/provenance differences.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    args = _build_argparser().parse_args(argv)
    if args.extract:
        return cmd_extract(args)
    if args.generate:
        return cmd_generate(args)
    return cmd_verify(args)


if __name__ == "__main__":
    sys.exit(main())
