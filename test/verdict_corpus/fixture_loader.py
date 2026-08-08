"""
Shared fixture-loading, decision-replay, and comparison code for the TOO-45
verdict-equivalence corpus.

Used by BOTH ``tools/corpus_build.py`` (the dev-only tool that regenerates
``cases.jsonl``/``goldens.jsonl``/``e2e_cases.jsonl``/``e2e_goldens.jsonl``)
and ``test/unit/test_verdict_corpus.py`` (the replay tests that guard the
refactor), so the two can never drift on how a fixture's committed config
files become a :class:`~toolguard.config.Configuration`, or on how a
:class:`~toolguard.config_types.RuntimeVerdict` (or a raw hook JSON response)
becomes a golden record. ``corpus_build.py --verify`` and the unit tests
literally call the same :func:`compare_goldens` / :func:`compare_e2e_goldens`
-- one prints a CLI diff and exits non-zero, the other asserts.

Two corpora live here, for two different seams:

- The IN-PROCESS corpus (:data:`CASES_PATH` / :data:`GOLDENS_PATH`) calls
  :func:`toolguard.api.decide` directly -- fast (~5,000 cases in a
  few seconds), but it stops at the decision itself and cannot see anything
  downstream of it (e.g. how :func:`toolguard.hook.create_hook_output` turns
  a decision into the actual JSON Claude Code receives).
- The END-TO-END corpus (:data:`E2E_CASES_PATH` / :data:`E2E_GOLDENS_PATH`)
  runs the real ``toolguard`` hook binary in a subprocess via
  :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`, for exactly that
  reason -- deliberately small (a few dozen cases; subprocess startup
  dominates), chosen to span the output-JSON surface rather than to
  re-exercise decision coverage the in-process corpus already has. It is
  ALSO the only place (TOO-45 audit follow-up) that can see
  :class:`~toolguard.config.ConflictOverride`: since TOO-45 R6-S3 unified
  ``Decision`` into :class:`~toolguard.config_types.RuntimeVerdict`,
  :func:`toolguard.api.decide` DOES return it on its own
  ``overrides`` field, but :func:`decision_to_golden` (see that function's
  own docstring) deliberately excludes it from the golden schema, and it
  never appears in the hook's JSON output either -- it exists ONLY as an
  entry in ``logs/toolguard-conflict-*.md``, a THIRD seam neither corpus's
  primary comparison touches. See
  :func:`_new_stream_log_text` and the ``conflict_logged``/``conflict_message``
  golden keys below -- the latter (TOO-45 D1a review debt item E) is also the
  only place the OVERRIDDEN deny's provenance is observable at all, since it
  is embedded only in that log message's text.
  (The ``allow_with_warning`` fallback's own WARNING-stream routing
  was investigated the same way and deliberately NOT instrumented here:
  ``toolguard-warning-*.md`` also receives an unrelated, pre-existing "tool
  not in governed_tools" advisory on every hook run for any fixture that
  does not set ``governed_tools`` explicitly, which would make a
  presence-only signal on that stream noisy rather than diagnostic. The
  in-process corpus's ``reason`` text already pins that fallback firing
  precisely -- see ``fallback_allow_warning``'s cases in ``cases.jsonl``.)

See ``README.md`` (this directory) for what the corpus is for and how to
update it. This module deliberately does NOT start with ``test`` so
``unittest discover`` never imports it as a test module.
"""

import json
import re
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple

from toolguard.api import decide
from toolguard.config import Configuration, ConflictOverride
from toolguard.config_types import RuntimeVerdict, UnitVerdict
from toolguard.hook import FILE_PATH_TOOLS
from toolguard.testing.sandbox import Sandbox, experiment

CORPUS_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = CORPUS_DIR / "configs"
CASES_PATH = CORPUS_DIR / "cases.jsonl"
GOLDENS_PATH = CORPUS_DIR / "goldens.jsonl"
E2E_CASES_PATH = CORPUS_DIR / "e2e_cases.jsonl"
E2E_GOLDENS_PATH = CORPUS_DIR / "e2e_goldens.jsonl"

#: Every fixture id the corpus knows about, in a fixed, stable order. This is
#: the id set --extract writes synthetic cases against and --generate/--verify
#: validate every case's ``fixture`` field falls within; it is NOT the
#: case-processing order (that follows ``cases.jsonl`` and is grouped by
#: fixture internally so each fixture's Configuration loads exactly once).
FIXTURE_IDS = (
    "realistic",
    "empty",
    "fallback_ask",
    "fallback_deny",
    "fallback_allow_warning",
    "fallback_allow_silent",
    "undecidable_ask",
    "undecidable_deny",
    "undecidable_allow",
    "hard_deny",
    "parse_failure",
    "hierarchy_conflict",
    "pattern_forms",
    "enrichment",
    # TOO-45 audit follow-up (config.py's no-match-fallback tail and its
    # thinnest-covered neighbours): 'ask'-rule provenance across multiple
    # hierarchy levels/layers, and allow-over-deny override breadth.
    "ask_provenance",
    "override_breadth",
)

#: Placeholders substituted for the sandbox's own (per-run, ephemeral)
#: absolute paths before a verdict is serialized to a golden record. Without
#: this, ``reason`` (which embeds a bracketed provenance suffix) and
#: ``provenance.path`` would both contain a fresh ``tempfile`` directory name
#: every run, and two regenerations of the same corpus would never be
#: byte-identical -- unrelated to, and on top of, the *machine*-path
#: sanitisation ``corpus_build.py`` applies to real-traffic commands and to
#: the committed ``realistic`` fixture's config text.
PLACEHOLDER_HOME = "<FIXTURE_HOME>"
PLACEHOLDER_PROJECT = "<FIXTURE_PROJECT>"


class FixtureNotFoundError(LookupError):
    """Raised when a fixture id has neither ``configs/<id>.toml`` nor ``configs/<id>/``."""


def _read_text(path: Path) -> str:
    """Read *path* as UTF-8 text."""
    return path.read_text(encoding="utf-8")


def _read_rules_dir(directory: Path) -> Dict[str, str]:
    """Read every ``*.rules.toml`` file directly inside *directory*.

    Returns:
        ``{filename: text}``, empty when *directory* does not exist. Sorted by
        filename so fixture construction is deterministic regardless of
        filesystem iteration order.
    """
    if not directory.is_dir():
        return {}
    return {p.name: _read_text(p) for p in sorted(directory.glob("*.rules.toml"))}


@dataclass
class FixtureFiles:
    """The raw, committed config text for one fixture, before it is written
    into an isolated sandbox and loaded.

    Attributes:
        project_config: Project-level ``toolguard_hook.toml`` text, or
            ``None`` if this fixture has no project-level config.
        user_config: User-level ``toolguard_hook.toml`` text, or ``None``.
        rules_files: ``{filename: text}`` for ``~/.toolguard/rules/*.rules.toml``.
        xdg_rules_files: ``{filename: text}`` for
            ``~/.config/toolguard/rules/*.rules.toml``.
    """

    project_config: Optional[str] = None
    user_config: Optional[str] = None
    rules_files: Dict[str, str] = field(default_factory=dict)
    xdg_rules_files: Dict[str, str] = field(default_factory=dict)


def load_fixture_files(fixture_id: str) -> FixtureFiles:
    """
    Read a fixture's committed config text from ``configs/``.

    Layout convention:

    - ``fixture_id == "empty"`` is special-cased to genuinely no config at
      all (no file on disk represents "nothing" more honestly than an
      almost-empty placeholder file would).
    - ``configs/<id>.toml`` -- a single project-level config; no user level,
      no rules directory. Used by every fixture that needs only one file.
    - ``configs/<id>/`` -- a directory laid out like a miniature real
      filesystem, for fixtures that need a second hierarchy level and/or a
      rules-dir file: ``project/.claude/toolguard_hook.toml``,
      ``home/.claude/toolguard_hook.toml``,
      ``home/.toolguard/rules/*.rules.toml``,
      ``home/.config/toolguard/rules/*.rules.toml`` (all optional).

    Args:
        fixture_id: One of :data:`FIXTURE_IDS`.

    Returns:
        The fixture's raw config text, ready to hand to
        :func:`load_fixture_configuration`.

    Raises:
        FixtureNotFoundError: Neither on-disk form exists for *fixture_id*.
    """
    if fixture_id == "empty":
        return FixtureFiles()

    single = CONFIGS_DIR / f"{fixture_id}.toml"
    if single.is_file():
        return FixtureFiles(project_config=_read_text(single))

    directory = CONFIGS_DIR / fixture_id
    if directory.is_dir():
        project_file = directory / "project" / ".claude" / "toolguard_hook.toml"
        user_file = directory / "home" / ".claude" / "toolguard_hook.toml"
        return FixtureFiles(
            project_config=_read_text(project_file) if project_file.is_file() else None,
            user_config=_read_text(user_file) if user_file.is_file() else None,
            rules_files=_read_rules_dir(directory / "home" / ".toolguard" / "rules"),
            xdg_rules_files=_read_rules_dir(
                directory / "home" / ".config" / "toolguard" / "rules"
            ),
        )

    raise FixtureNotFoundError(
        f"No configs/{fixture_id}.toml or configs/{fixture_id}/ directory found "
        f"under {CONFIGS_DIR}"
    )


def _sanitize_ephemeral(text: Optional[str], sandbox) -> Optional[str]:
    """
    Replace *sandbox*'s own (per-run, random) absolute paths with fixed
    placeholders.

    Args:
        text: A string that may embed ``str(sandbox.home)`` and/or
            ``str(sandbox.project)`` (e.g. a decision ``reason``, or a
            serialized provenance ``path``), or ``None``.
        sandbox: The :class:`~toolguard.testing.sandbox.Sandbox` the text came
            from.

    Returns:
        *text* with ephemeral paths replaced, or ``None`` unchanged.
    """
    if text is None:
        return None
    text = text.replace(str(sandbox.project), PLACEHOLDER_PROJECT)
    text = text.replace(str(sandbox.home), PLACEHOLDER_HOME)
    return text


@contextmanager
def _open_fixture_sandbox(fixture_id: str) -> Iterator[Sandbox]:
    """
    Materialise one fixture's committed config files into a fresh, isolated
    :class:`~toolguard.testing.sandbox.Sandbox`.

    Shared by :func:`load_fixture_configuration` (in-process replay via
    :func:`toolguard.api.decide`) and :func:`load_fixture_sandbox`
    (end-to-end replay via :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`)
    so both go through the identical write-then-isolate step -- neither
    reimplements it.

    Args:
        fixture_id: One of :data:`FIXTURE_IDS`.

    Yields:
        The sandbox, with the fixture's files already written and isolation
        (``Path.home()``, ``find_project_root``, environment, write tripwire)
        active for the duration of the block.
    """
    files = load_fixture_files(fixture_id)
    with experiment(
        project_config=files.project_config,
        user_config=files.user_config,
        rules_files=files.rules_files or None,
        xdg_rules_files=files.xdg_rules_files or None,
    ) as sandbox:
        yield sandbox


@contextmanager
def load_fixture_configuration(
    fixture_id: str,
) -> Iterator[Tuple[Configuration, Callable[[Optional[str]], Optional[str]]]]:
    """
    Materialise one fixture in an isolated sandbox and load its Configuration
    ONCE, for IN-PROCESS replay via :func:`toolguard.api.decide`.

    This is the ONLY place :class:`~toolguard.config.Configuration` is loaded
    for corpus purposes -- callers must run every case for this fixture
    inside the ``with`` block (or at least call the returned ``sanitize``
    function while it is open) rather than reloading per case.

    Args:
        fixture_id: One of :data:`FIXTURE_IDS`.

    Yields:
        ``(config, sanitize)`` where ``config`` is the loaded
        :class:`~toolguard.config.Configuration` and ``sanitize`` strips this
        sandbox's own ephemeral absolute paths out of a string (see
        :func:`_sanitize_ephemeral`), for use when serializing a
        :class:`~toolguard.config_types.RuntimeVerdict` to a golden record.
    """
    with _open_fixture_sandbox(fixture_id) as sandbox:
        config = sandbox.load_configuration()
        yield config, (lambda text: _sanitize_ephemeral(text, sandbox))


@contextmanager
def load_fixture_sandbox(
    fixture_id: str,
) -> Iterator[Tuple[Sandbox, Callable[[Optional[str]], Optional[str]]]]:
    """
    Materialise one fixture in an isolated sandbox for END-TO-END replay via
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`.

    Unlike :func:`load_fixture_configuration`, this does NOT load a
    :class:`~toolguard.config.Configuration` at all -- each
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook` call is its own
    subprocess that re-reads the sandbox's config files itself, exactly like a
    real invocation of the ``toolguard`` binary would. That subprocess
    re-parse is the whole point of the end-to-end corpus: it is what lets this
    corpus see the hook's OUTPUT construction (:func:`toolguard.hook.create_hook_output`),
    which :func:`toolguard.api.decide` never touches.

    Args:
        fixture_id: One of :data:`FIXTURE_IDS`.

    Yields:
        ``(sandbox, sanitize)`` -- callers run one
        :meth:`~toolguard.testing.sandbox.Sandbox.run_hook` per case inside the
        ``with`` block; ``sanitize`` strips this sandbox's own ephemeral
        absolute paths out of a string.
    """
    with _open_fixture_sandbox(fixture_id) as sandbox:
        yield sandbox, (lambda text: _sanitize_ephemeral(text, sandbox))


def provenance_to_dict(
    provenance, sanitize: Callable[[Optional[str]], Optional[str]]
) -> Optional[Dict[str, Any]]:
    """
    Convert a :class:`~toolguard.config.Provenance` (or ``None``) to a
    JSON-safe, sandbox-path-sanitized dict.

    Args:
        provenance: The decision's winning-rule provenance, or ``None``.
        sanitize: Ephemeral-path sanitizer from :func:`load_fixture_configuration`.

    Returns:
        A dict with ``level``/``source_type``/``file_format``/``path``/
        ``specificity``, or ``None`` when *provenance* is ``None``.
    """
    if provenance is None:
        return None
    return {
        "level": provenance.level,
        "source_type": provenance.source_type,
        "file_format": provenance.file_format,
        "path": sanitize(str(provenance.path)),
        "specificity": provenance.specificity,
    }


def unit_verdict_to_dict(
    unit: UnitVerdict, sanitize: Callable[[Optional[str]], Optional[str]]
) -> Dict[str, Any]:
    """
    Convert one :class:`~toolguard.config_types.UnitVerdict` (one entry of
    ``RuntimeVerdict.sub_matches``) to a JSON-safe, sandbox-path-sanitized
    dict, for the golden schema's ``sub_matches`` list (TOO-45 corpus
    sub-verdict extension -- see :func:`decision_to_golden`'s docstring).

    Deliberately narrower than the full :class:`~toolguard.config_types.UnitVerdict`:
    only the four fields the extension's spec calls for --
    ``sub_command``/``decision``/``matched_rule``/``provenance``. ``reason``
    and ``additional_context`` are per-unit PROSE, not the structural
    identity this extension exists to pin (the compound-command's own
    ``reason``/``additional_context`` are already TRACKED at the top level),
    and ``fallback_kind`` is a rendering aid for ``hook.py``'s log
    substitution, not part of the audit-loss surface (a dropped/garbled
    ``UnitVerdict`` is detectable here regardless of ``fallback_kind``).

    Args:
        unit: One entry from ``RuntimeVerdict.sub_matches``.
        sanitize: Ephemeral-path sanitizer from :func:`load_fixture_configuration`.

    Returns:
        ``{"sub_command", "decision", "matched_rule", "provenance"}``.
    """
    return {
        "sub_command": sanitize(unit.sub_command),
        "decision": unit.decision,
        "matched_rule": sanitize(unit.matched_rule),
        "provenance": provenance_to_dict(unit.provenance, sanitize),
    }


def override_to_dict(
    identifier: Optional[str],
    override: ConflictOverride,
    sanitize: Callable[[Optional[str]], Optional[str]],
) -> Dict[str, Any]:
    """
    Convert one ``(identifier, ConflictOverride)`` pair (one entry of
    ``RuntimeVerdict.overrides``) to a JSON-safe, sandbox-path-sanitized dict,
    for the golden schema's ``overrides`` list (TOO-45 corpus sub-verdict
    extension -- see :func:`decision_to_golden`'s docstring).

    Args:
        identifier: The deciding sub-command string (Bash) or the target
            path (file-path); see :class:`~toolguard.config_types.RuntimeVerdict`'s
            ``overrides`` docstring for the identifier convention. Never
            ``None`` in practice for a golden produced from ``decide()``'s
            return value (only the internal, never-returned per-level
            verdict pairs a bare override with ``None``), but sanitized
            defensively the same way every other optional string here is.
        override: The :class:`~toolguard.config.ConflictOverride`.
        sanitize: Ephemeral-path sanitizer from :func:`load_fixture_configuration`.

    Returns:
        ``{"identifier", "winning_pattern", "winning_provenance",
        "overridden_pattern", "overridden_provenance"}``.
    """
    return {
        "identifier": sanitize(identifier),
        "winning_pattern": override.winning_pattern,
        "winning_provenance": provenance_to_dict(override.winning_provenance, sanitize),
        "overridden_pattern": override.overridden_pattern,
        "overridden_provenance": provenance_to_dict(
            override.overridden_provenance, sanitize
        ),
    }


def decision_to_golden(
    fixture_id: str,
    decision: RuntimeVerdict,
    sanitize: Callable[[Optional[str]], Optional[str]],
) -> Dict[str, Any]:
    """
    Build one golden record (the schema stored in ``goldens.jsonl``) from a
    replayed :class:`~toolguard.config_types.RuntimeVerdict`.

    ``sub_matches``/``overrides`` (TOO-45 corpus sub-verdict extension)
    -----------------------------------------------------------------------
    Originally excluded on purpose (see git history for this docstring's
    prior text) -- this corpus is exactly the safety net this project relies
    on, and it did not capture the compound sub-command breakdown, which is
    precisely the structural data whose loss was TOO-45's headline defect:
    ``hook.py``'s audit-log writer used to reconstruct which sub-commands of
    an allowed compound ran by regex-parsing the combined ``reason`` string,
    silently dropping 813 of 975 compound-allow corpus cases' audit entries
    (1,943 sub-commands with no log record at all). ``_log_allowed_command``
    now reads ``verdict.sub_matches`` structurally instead (TOO-45 R1e), but
    nothing pinned that fix against a future regression reintroducing the
    loss -- this extension is that pin, at the ``decide()``-return-value
    altitude (whether ``sub_matches``/``overrides`` themselves are computed
    correctly; NOT whether ``_log_allowed_command``'s own write loop over
    them is correct -- see ``README.md``'s "Sub-command breakdown" section
    for that residual gap and why the end-to-end corpus does not close it
    either).

    Included fields, via :func:`unit_verdict_to_dict`/:func:`override_to_dict`:
    exactly the four fields the extension's spec calls for per
    :class:`~toolguard.config_types.UnitVerdict` (``sub_command``,
    ``decision``, ``matched_rule``, ``provenance``), and the full
    :class:`~toolguard.config.ConflictOverride` shape per override entry.
    Both keys are ALWAYS present as a list -- empty (never omitted) when a
    verdict genuinely has none (every file-path verdict for ``sub_matches``;
    the common case for ``overrides``) -- so a regression that drops a
    genuinely non-empty compound's breakdown down to ``[]`` is a visible
    ``[...N entries...]`` -> ``[]`` diff, not a key that silently stops
    appearing. Both are treated as a NEW HARD comparison tier (see
    :class:`CompoundBreakdownMismatch`/:data:`ComparisonResult.breakdown_mismatches`),
    not the existing TRACKED tier: unlike ``reason``/``additional_context``,
    these are structural facts a legitimate refactor has no reason to reword,
    and the entire point of this extension is to catch STRUCTURAL loss
    (dropped/reordered/malformed entries), the exact failure mode of the
    defect being guarded against.

    ``matched_rule`` (top-level, unrelated to the above) was widened in
    separately (TOO-45 D1a review debt item E): two independent mutations --
    nulling ``matched_rule`` at its source in
    ``permission_resolution._resolve_unclamped`` and nulling an overridden
    deny's provenance in ``permission_resolution._detect_override`` -- each
    failed unit tests but left this corpus reporting no differences, because
    it did not observe either field at all. ``matched_rule`` is tracked here;
    the overridden-deny-provenance half is tracked on the END-TO-END corpus
    instead (see :func:`e2e_decision_to_golden`), since it is observable only
    via the conflict-log message's text, not via ``decide()``'s return value
    at all.

    Args:
        fixture_id: The fixture this case was replayed against.
        decision: The result of :func:`toolguard.api.decide`.
        sanitize: Ephemeral-path sanitizer from :func:`load_fixture_configuration`.

    Returns:
        A JSON-serializable dict.
    """
    return {
        "fixture": fixture_id,
        "tool": decision.tool,
        "target": decision.target,
        "verdict": decision.decision,
        "reason": sanitize(decision.reason),
        "additional_context": sanitize(decision.additional_context),
        "provenance": provenance_to_dict(decision.provenance, sanitize),
        "matched_rule": sanitize(decision.matched_rule),
        "sub_matches": [
            unit_verdict_to_dict(unit, sanitize) for unit in decision.sub_matches
        ],
        "overrides": [
            override_to_dict(identifier, override, sanitize)
            for identifier, override in decision.overrides
        ],
    }


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file (one JSON object per non-blank line). Missing file -> ``[]``."""
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: List[Dict[str, Any]]) -> None:
    """
    Write *records* to *path*, one sorted-key JSON object per line.

    ``sort_keys=True`` and a fixed separator keep the output byte-identical
    across two regenerations of the same input -- the property
    ``corpus_build.py --generate`` is required to prove.
    """
    with path.open("w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True, ensure_ascii=False))
            f.write("\n")


def generate_goldens_in_memory(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Replay every case in *cases* and return the resulting golden records, in
    the SAME order as *cases*.

    Cases are grouped by fixture internally so each fixture's Configuration is
    loaded exactly once regardless of how the fixtures are interleaved in
    *cases* -- this is the single choke point that both ``corpus_build.py``
    and the replay test go through, so they can never disagree on how a
    verdict becomes a golden record.

    Args:
        cases: Records with ``fixture``/``tool``/``target`` keys (the
            ``cases.jsonl`` schema).

    Returns:
        One golden record per case, in input order.
    """
    indices_by_fixture: Dict[str, List[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        indices_by_fixture[case["fixture"]].append(index)

    results: List[Optional[Dict[str, Any]]] = [None] * len(cases)
    for fixture_id, indices in indices_by_fixture.items():
        with load_fixture_configuration(fixture_id) as (config, sanitize):
            for index in indices:
                case = cases[index]
                decision = decide(
                    config, case["tool"], case["target"], extended_syntax=True
                )
                results[index] = decision_to_golden(fixture_id, decision, sanitize)
    return results


# ---------------------------------------------------------------------------
# End-to-end (real hook subprocess) corpus
# ---------------------------------------------------------------------------

#: Response keys :meth:`~toolguard.testing.sandbox.Sandbox.run_hook` adds on
#: top of the hook's actual JSON output, purely for the caller's diagnosis --
#: never part of the hook's real output surface, so never part of the golden.
_RUN_HOOK_DIAGNOSTIC_KEYS = ("_stderr", "_returncode")

#: The two prose fields inside ``hookSpecificOutput`` that may embed an
#: ephemeral sandbox path (via a bracketed provenance suffix or, for
#: ``additionalContext``, the enrichment text itself referencing a path).
_HOOK_OUTPUT_PROSE_FIELDS = ("permissionDecisionReason", "additionalContext")


#: Log streams (see ``toolguard/error_log.py``) whose content this corpus
#: observes as a SIDE EFFECT of ``run_hook``'s subprocess -- filename shape
#: ``toolguard-<stream>-*.md`` under the sandbox's ``log_dir``.
#: ``'warning'`` is deliberately NOT included -- see the end-to-end corpus's
#: module-level rationale above for why that stream is too noisy to use as a
#: presence-only signal.
_OBSERVED_LOG_STREAMS = ("conflict",)


#: Matches the wall-clock timestamp at the start of a log entry header (see
#: ``error_log.py``'s ``_log_entry``, e.g. ``## 2026-08-05 10:20:33 -
#: CONFLICT``). Replaced with a fixed placeholder before a conflict-log
#: message is stored in a golden -- otherwise every regeneration would embed
#: the real wall-clock time it ran at, breaking the byte-identical-across-
#: regenerations property this corpus otherwise guarantees (see README.md's
#: "Sanitization" section), independently of the ephemeral-sandbox-path
#: sanitization :func:`_sanitize_ephemeral` already does.
_LOG_TIMESTAMP_RE = re.compile(
    r"^## \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} - ", re.MULTILINE
)


def _normalize_log_timestamps(text: str) -> str:
    """Replace every log-entry header timestamp in *text* with a fixed placeholder."""
    return _LOG_TIMESTAMP_RE.sub("## <TIMESTAMP> - ", text)


def _stream_log_snapshot(sandbox, stream: str) -> Dict[Path, str]:
    """
    Read the current full text of every ``toolguard-<stream>-*.md`` file in
    *sandbox*'s log directory.

    Args:
        sandbox: The fixture's :class:`~toolguard.testing.sandbox.Sandbox`.
        stream: ``'conflict'`` (see :data:`_OBSERVED_LOG_STREAMS`).

    Returns:
        ``{path: text}`` for every matching file (empty when none exist yet).
    """
    return {
        path: path.read_text(encoding="utf-8")
        for path in sandbox.log_dir.glob(f"toolguard-{stream}-*.md")
    }


def _new_stream_log_text(before: Dict[Path, str], after: Dict[Path, str]) -> str:
    """
    Return the text APPENDED to a log stream between two
    :func:`_stream_log_snapshot` calls taken immediately before/after one
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook` call -- the only way
    this corpus can observe :class:`~toolguard.config.ConflictOverride`
    (routed to the ``'conflict'`` stream): it never reaches
    :func:`toolguard.api.decide`'s return value or the hook's JSON
    output (see the end-to-end corpus's module-level rationale above), and
    (TOO-45 D1a review debt item E) neither does the OVERRIDDEN deny's
    provenance specifically -- it is embedded only in this log message's text
    (see ``hook._format_conflict_message``), so capturing the text (not just
    "did a new entry appear", the previous behaviour) is what lets this
    corpus notice a mutation that nulls it.

    Log entries are always appended, never rewritten, so for each file the
    new content is the after-text with the before-text's prefix removed
    (an empty prefix for a file that did not exist yet in *before*).
    Concatenated across files in stable (sorted-path) order.

    Args:
        before: Snapshot taken immediately before the ``run_hook`` call.
        after: Snapshot taken immediately after it.

    Returns:
        The newly appended text, with log-entry timestamps normalized (see
        :func:`_normalize_log_timestamps`) -- empty string when nothing new
        appeared.
    """
    pieces = []
    for path in sorted(after):
        old = before.get(path, "")
        new = after[path]
        # Defensive: entries are append-only by construction (see
        # error_log.py), but if a file were ever rewritten instead of
        # appended, falling back to the whole new content is safer than
        # silently dropping it.
        pieces.append(new[len(old) :] if new.startswith(old) else new)
    return _normalize_log_timestamps("".join(pieces))


def build_hook_payload(tool: str, target: str) -> Dict[str, Any]:
    """
    Build a minimal ``PreToolUse`` hook event payload for
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`.

    Args:
        tool: Tool name (e.g. ``'Bash'``, ``'Read'``, ``'Write'``, ``'Edit'``).
        target: The command string (Bash) or file path (file tools).

    Returns:
        ``{"tool_name": tool, "tool_input": {...}}`` -- ``run_hook`` fills in
        ``cwd``/``hook_event_name``/``session_id`` defaults. Dispatches on
        :data:`toolguard.hook.FILE_PATH_TOOLS` the SAME way ``decision.py``
        does, so a file-tool target reaches the hook as ``file_path`` and
        everything else as ``command`` -- matching real Claude Code events.
    """
    key = "file_path" if tool in FILE_PATH_TOOLS else "command"
    return {"tool_name": tool, "tool_input": {key: target}}


def e2e_decision_to_golden(
    fixture_id: str,
    tool: str,
    target: str,
    hook_result: Dict[str, Any],
    sanitize: Callable[[Optional[str]], Optional[str]],
    *,
    conflict_message: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build one end-to-end golden record from a real
    :meth:`~toolguard.testing.sandbox.Sandbox.run_hook` response.

    Deliberately golds the FULL response shape (minus the two
    ``run_hook``-only diagnostic keys) rather than re-deriving fields from a
    :class:`~toolguard.config_types.RuntimeVerdict` -- the presence or absence
    of the ``additionalContext`` key is exactly the seam this corpus exists to
    guard, and only the real subprocess response can show it.

    Args:
        fixture_id: The fixture this case was replayed against.
        tool: Tool name.
        target: Command string or file path.
        hook_result: The dict returned by
            :meth:`~toolguard.testing.sandbox.Sandbox.run_hook`.
        sanitize: Ephemeral-path sanitizer from :func:`load_fixture_sandbox`.
        conflict_message: The text newly appended to the ``'conflict'`` log
            stream by THIS case (see :func:`_new_stream_log_text`), already
            sanitized, or ``None`` when no conflict was logged. This is the
            only observable trace of a :class:`~toolguard.config.ConflictOverride`
            -- and (TOO-45 D1a review debt item E) the only place the
            OVERRIDDEN deny's provenance is observable at all, since it is
            embedded in this message's text (see
            ``hook._format_conflict_message``) and nowhere else this corpus
            can see. Included in the golden ONLY when not ``None`` (see
            below).

    Returns:
        ``{"fixture", "tool", "target", "response"}`` where ``response`` is
        the sanitized hook JSON output (``_stderr``/``_returncode`` dropped),
        PLUS ``conflict_logged``/``conflict_message`` -- but ONLY when a
        conflict WAS logged. Omitting both keys otherwise (rather than always
        writing ``conflict_logged: False``) keeps every case that predates
        this instrumentation (none of which triggers a conflict-log entry)
        byte-identical after regeneration; a comparison reads a missing key
        as ``False``/``None`` via ``dict.get`` (see
        :func:`compare_e2e_goldens`), so the two representations are
        equivalent for every purpose that matters here.
    """
    response = {
        key: value
        for key, value in hook_result.items()
        if key not in _RUN_HOOK_DIAGNOSTIC_KEYS
    }
    hook_specific_output = response.get("hookSpecificOutput")
    if isinstance(hook_specific_output, dict):
        for field_name in _HOOK_OUTPUT_PROSE_FIELDS:
            if field_name in hook_specific_output:
                hook_specific_output[field_name] = sanitize(
                    hook_specific_output[field_name]
                )
    golden: Dict[str, Any] = {
        "fixture": fixture_id,
        "tool": tool,
        "target": target,
        "response": response,
    }
    if conflict_message:
        golden["conflict_logged"] = True
        golden["conflict_message"] = conflict_message
    return golden


def generate_e2e_goldens_in_memory(cases: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Replay every end-to-end case in *cases* through the REAL hook binary (a
    subprocess per case) and return the resulting golden records, in the SAME
    order as *cases*.

    Cases are grouped by fixture so each fixture's sandbox is materialised
    (config files written, isolation entered) exactly once; the subprocess
    startup cost per case itself cannot be amortised further -- that IS the
    thing being exercised (:meth:`~toolguard.testing.sandbox.Sandbox.run_hook`
    always re-reads config from disk in a fresh process, the same as a real
    Claude Code invocation).

    Args:
        cases: Records with ``fixture``/``tool``/``target`` keys (the
            ``e2e_cases.jsonl`` schema -- identical shape to ``cases.jsonl``).

    Returns:
        One end-to-end golden record per case, in input order.
    """
    indices_by_fixture: Dict[str, List[int]] = defaultdict(list)
    for index, case in enumerate(cases):
        indices_by_fixture[case["fixture"]].append(index)

    results: List[Optional[Dict[str, Any]]] = [None] * len(cases)
    for fixture_id, indices in indices_by_fixture.items():
        with load_fixture_sandbox(fixture_id) as (sandbox, sanitize):
            for index in indices:
                case = cases[index]
                tool, target = case["tool"], case["target"]
                before = {
                    stream: _stream_log_snapshot(sandbox, stream)
                    for stream in _OBSERVED_LOG_STREAMS
                }
                hook_result = sandbox.run_hook(build_hook_payload(tool, target))
                after = {
                    stream: _stream_log_snapshot(sandbox, stream)
                    for stream in _OBSERVED_LOG_STREAMS
                }
                conflict_text = _new_stream_log_text(
                    before["conflict"], after["conflict"]
                )
                results[index] = e2e_decision_to_golden(
                    fixture_id,
                    tool,
                    target,
                    hook_result,
                    sanitize,
                    conflict_message=sanitize(conflict_text) if conflict_text else None,
                )
    return results


def _golden_key(record: Dict[str, Any]) -> Tuple[str, str, str]:
    """The identity of a golden/case record: (fixture, tool, target)."""
    return (record["fixture"], record["tool"], record["target"])


def _index_by_key(
    records: List[Dict[str, Any]], what: str
) -> Dict[Tuple[str, str, str], Dict[str, Any]]:
    """
    Build a ``{(fixture, tool, target): record}`` index, raising loudly on a
    duplicate key rather than silently letting the second occurrence win.

    Args:
        records: Golden or case records.
        what: Noun used in the error message ("case" or "golden").

    Returns:
        The index.

    Raises:
        ValueError: Two records share the same ``(fixture, tool, target)`` key.
    """
    index: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for record in records:
        key = _golden_key(record)
        if key in index:
            raise ValueError(
                f"duplicate {what} key {key!r} -- every (fixture, tool, target) "
                "triple must be unique across the corpus"
            )
        index[key] = record
    return index


#: The golden fields tracked (not frozen) for equivalence -- a legitimate
#: reword/refactor may change these; a hard invariant (verdict) never should.
#: ``matched_rule`` added by TOO-45 D1a review debt item E (see
#: :func:`decision_to_golden`'s docstring for why it was missing).
TRACKED_FIELDS = ("reason", "additional_context", "provenance", "matched_rule")

#: The golden fields compared as a HARD invariant, same tier as ``verdict``
#: (TOO-45 corpus sub-verdict extension) -- see :func:`decision_to_golden`'s
#: docstring for why ``sub_matches``/``overrides`` are HARD rather than
#: TRACKED, unlike the structurally-similar ``provenance``/``matched_rule``
#: above.
BREAKDOWN_FIELDS = ("sub_matches", "overrides")


@dataclass(frozen=True)
class ProseDiff:
    """One tracked-field difference between an expected and an actual golden."""

    fixture: str
    tool: str
    target: str
    field: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class VerdictMismatch:
    """One HARD verdict difference -- always a test failure."""

    fixture: str
    tool: str
    target: str
    expected_verdict: str
    actual_verdict: str


@dataclass(frozen=True)
class CompoundBreakdownMismatch:
    """
    One HARD difference in the compound sub-command breakdown (TOO-45 corpus
    sub-verdict extension) -- always a test failure, same tier as
    :class:`VerdictMismatch`. See :func:`decision_to_golden`'s docstring for
    why ``sub_matches``/``overrides`` are HARD rather than TRACKED.

    Attributes:
        field: ``"sub_matches"`` or ``"overrides"`` -- which golden list
            differed.
        expected: The committed golden's full list value for *field*.
        actual: The freshly replayed value.
    """

    fixture: str
    tool: str
    target: str
    field: str
    expected: Any
    actual: Any


@dataclass
class ComparisonResult:
    """
    The outcome of comparing expected (committed) goldens against actual
    (freshly regenerated) ones.

    Attributes:
        verdict_mismatches: HARD failures -- any change here means STOP and
            investigate (see README.md); never regenerate to "fix" these.
        breakdown_mismatches: HARD failures in the compound sub-command
            breakdown (``sub_matches``/``overrides``, TOO-45 corpus
            sub-verdict extension) -- same "STOP and investigate" rule as
            ``verdict_mismatches``; see :class:`CompoundBreakdownMismatch`.
        prose_diffs: TRACKED, not frozen -- reason/additional_context/provenance
            differences. Reported for human review; acknowledgeable via
            ``TOOLGUARD_CORPUS_ACCEPT_PROSE=1``.
        missing_goldens: Cases present in ``cases.jsonl`` with no matching
            committed golden -- a corpus data-integrity problem (goldens were
            never regenerated after a case was added), always a hard failure.
        extra_goldens: Committed goldens with no matching case -- likewise a
            data-integrity problem (a case was removed/renamed without
            regenerating), always a hard failure.
    """

    verdict_mismatches: List[VerdictMismatch] = field(default_factory=list)
    breakdown_mismatches: List[CompoundBreakdownMismatch] = field(default_factory=list)
    prose_diffs: List[ProseDiff] = field(default_factory=list)
    missing_goldens: List[Tuple[str, str, str]] = field(default_factory=list)
    extra_goldens: List[Tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_hard_failures(self) -> bool:
        """True if verdicts (or the sub-command breakdown) changed, or the corpus data itself is inconsistent."""
        return bool(
            self.verdict_mismatches
            or self.breakdown_mismatches
            or self.missing_goldens
            or self.extra_goldens
        )

    @property
    def has_prose_diffs(self) -> bool:
        """True if any tracked (non-verdict, non-breakdown) field differs."""
        return bool(self.prose_diffs)


def compare_goldens(
    expected_goldens: List[Dict[str, Any]], actual_goldens: List[Dict[str, Any]]
) -> ComparisonResult:
    """
    Compare committed goldens against freshly regenerated ones.

    Args:
        expected_goldens: Records read from the committed ``goldens.jsonl``.
        actual_goldens: Records from :func:`generate_goldens_in_memory` run
            against the current ``cases.jsonl``.

    Returns:
        A :class:`ComparisonResult` separating hard verdict failures from
        tracked prose differences (see that class's docstring).
    """
    expected_index = _index_by_key(expected_goldens, "golden")
    actual_index = _index_by_key(actual_goldens, "case")

    result = ComparisonResult()
    for key in sorted(actual_index.keys() - expected_index.keys()):
        result.missing_goldens.append(key)
    for key in sorted(expected_index.keys() - actual_index.keys()):
        result.extra_goldens.append(key)

    for key in sorted(actual_index.keys() & expected_index.keys()):
        fixture, tool, target = key
        expected = expected_index[key]
        actual = actual_index[key]
        if expected["verdict"] != actual["verdict"]:
            result.verdict_mismatches.append(
                VerdictMismatch(
                    fixture=fixture,
                    tool=tool,
                    target=target,
                    expected_verdict=expected["verdict"],
                    actual_verdict=actual["verdict"],
                )
            )
        for breakdown_field in BREAKDOWN_FIELDS:
            # .get(..., []) tolerates a golden written before this extension
            # (none should remain committed, but this keeps an old golden a
            # clean breakdown_mismatch rather than a KeyError).
            expected_breakdown = expected.get(breakdown_field, [])
            actual_breakdown = actual.get(breakdown_field, [])
            if expected_breakdown != actual_breakdown:
                result.breakdown_mismatches.append(
                    CompoundBreakdownMismatch(
                        fixture=fixture,
                        tool=tool,
                        target=target,
                        field=breakdown_field,
                        expected=expected_breakdown,
                        actual=actual_breakdown,
                    )
                )
        for tracked_field in TRACKED_FIELDS:
            if expected[tracked_field] != actual[tracked_field]:
                result.prose_diffs.append(
                    ProseDiff(
                        fixture=fixture,
                        tool=tool,
                        target=target,
                        field=tracked_field,
                        expected=expected[tracked_field],
                        actual=actual[tracked_field],
                    )
                )
    return result


# ---------------------------------------------------------------------------
# End-to-end comparison -- a DIFFERENT hard/tracked split than the in-process
# corpus, because the thing being golden is a nested hookSpecificOutput dict,
# not flat fields, and "additionalContext is present at all" is itself a hard
# invariant here (that is precisely the seam this corpus was added to guard).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class E2EHardMismatch:
    """
    One HARD end-to-end difference -- always a test failure.

    Attributes:
        kind: ``"permissionDecision"`` (the decision itself changed),
            ``"additionalContext_presence"`` (the KEY appeared or disappeared
            from ``hookSpecificOutput`` -- independent of what its text
            says), or ``"conflict_logged"`` (a ``ConflictOverride`` was/was
            not written to the conflict log -- TOO-45 audit follow-up).
        expected: The committed golden's value for *kind*.
        actual: The freshly replayed value for *kind*.

    ``conflict_message`` (the conflict-log entry's TEXT, present only when
    both sides logged one) is tracked, not hard -- see :func:`compare_e2e_goldens`.
    """

    fixture: str
    tool: str
    target: str
    kind: str
    expected: Any
    actual: Any


@dataclass
class E2EComparisonResult:
    """
    The outcome of comparing expected (committed) end-to-end goldens against
    actual (freshly replayed) ones. Mirrors :class:`ComparisonResult`'s
    two-tier split (see that class's docstring for the rationale), adapted to
    the nested ``hookSpecificOutput`` shape:

    - HARD (:attr:`hard_mismatches`): ``permissionDecision``, the
      PRESENCE/ABSENCE of the ``additionalContext`` key, and (TOO-45 audit
      follow-up) the presence/absence of a new ``'conflict'``-stream entry
      (see :func:`_new_stream_log_text`) -- presence-only, same rationale as
      ``additionalContext``'s key.
    - TRACKED (:attr:`prose_diffs`, reusing :class:`ProseDiff`):
      ``permissionDecisionReason``'s text, ``additionalContext``'s text when
      present on both sides, and (TOO-45 D1a review debt item E)
      ``conflict_message``'s text when both sides logged a conflict -- the
      only place the overridden deny's provenance is observable at all.
    """

    hard_mismatches: List[E2EHardMismatch] = field(default_factory=list)
    prose_diffs: List[ProseDiff] = field(default_factory=list)
    missing_goldens: List[Tuple[str, str, str]] = field(default_factory=list)
    extra_goldens: List[Tuple[str, str, str]] = field(default_factory=list)

    @property
    def has_hard_failures(self) -> bool:
        """True if a permissionDecision or additionalContext-presence changed, or the corpus data itself is inconsistent."""
        return bool(self.hard_mismatches or self.missing_goldens or self.extra_goldens)

    @property
    def has_prose_diffs(self) -> bool:
        """True if any tracked (reason/additionalContext text) field differs."""
        return bool(self.prose_diffs)


def compare_e2e_goldens(
    expected_goldens: List[Dict[str, Any]], actual_goldens: List[Dict[str, Any]]
) -> E2EComparisonResult:
    """
    Compare committed end-to-end goldens against freshly regenerated ones.

    Args:
        expected_goldens: Records read from the committed ``e2e_goldens.jsonl``.
        actual_goldens: Records from :func:`generate_e2e_goldens_in_memory` run
            against the current ``e2e_cases.jsonl``.

    Returns:
        An :class:`E2EComparisonResult`.
    """
    expected_index = _index_by_key(expected_goldens, "e2e golden")
    actual_index = _index_by_key(actual_goldens, "e2e case")

    result = E2EComparisonResult()
    for key in sorted(actual_index.keys() - expected_index.keys()):
        result.missing_goldens.append(key)
    for key in sorted(expected_index.keys() - actual_index.keys()):
        result.extra_goldens.append(key)

    for key in sorted(actual_index.keys() & expected_index.keys()):
        fixture, tool, target = key
        expected_hso = expected_index[key]["response"].get("hookSpecificOutput", {})
        actual_hso = actual_index[key]["response"].get("hookSpecificOutput", {})

        expected_decision = expected_hso.get("permissionDecision")
        actual_decision = actual_hso.get("permissionDecision")
        if expected_decision != actual_decision:
            result.hard_mismatches.append(
                E2EHardMismatch(
                    fixture=fixture,
                    tool=tool,
                    target=target,
                    kind="permissionDecision",
                    expected=expected_decision,
                    actual=actual_decision,
                )
            )

        expected_has_context = "additionalContext" in expected_hso
        actual_has_context = "additionalContext" in actual_hso
        if expected_has_context != actual_has_context:
            result.hard_mismatches.append(
                E2EHardMismatch(
                    fixture=fixture,
                    tool=tool,
                    target=target,
                    kind="additionalContext_presence",
                    expected=expected_has_context,
                    actual=actual_has_context,
                )
            )

        expected_conflict_logged = expected_index[key].get("conflict_logged", False)
        actual_conflict_logged = actual_index[key].get("conflict_logged", False)
        if expected_conflict_logged != actual_conflict_logged:
            result.hard_mismatches.append(
                E2EHardMismatch(
                    fixture=fixture,
                    tool=tool,
                    target=target,
                    kind="conflict_logged",
                    expected=expected_conflict_logged,
                    actual=actual_conflict_logged,
                )
            )

        expected_reason = expected_hso.get("permissionDecisionReason")
        actual_reason = actual_hso.get("permissionDecisionReason")
        if expected_reason != actual_reason:
            result.prose_diffs.append(
                ProseDiff(
                    fixture=fixture,
                    tool=tool,
                    target=target,
                    field="permissionDecisionReason",
                    expected=expected_reason,
                    actual=actual_reason,
                )
            )

        if expected_has_context and actual_has_context:
            expected_context = expected_hso.get("additionalContext")
            actual_context = actual_hso.get("additionalContext")
            if expected_context != actual_context:
                result.prose_diffs.append(
                    ProseDiff(
                        fixture=fixture,
                        tool=tool,
                        target=target,
                        field="additionalContext",
                        expected=expected_context,
                        actual=actual_context,
                    )
                )

        # TOO-45 D1a review debt item E: conflict_message's TEXT (not just
        # whether a conflict was logged at all, already checked above as a
        # hard mismatch) is where the overridden deny's provenance is
        # observable -- track it the same way additionalContext's text is
        # tracked, only when both sides actually logged a conflict.
        if expected_conflict_logged and actual_conflict_logged:
            expected_message = expected_index[key].get("conflict_message")
            actual_message = actual_index[key].get("conflict_message")
            if expected_message != actual_message:
                result.prose_diffs.append(
                    ProseDiff(
                        fixture=fixture,
                        tool=tool,
                        target=target,
                        field="conflict_message",
                        expected=expected_message,
                        actual=actual_message,
                    )
                )
    return result
