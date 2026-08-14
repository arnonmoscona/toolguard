"""Unit tests for toolguard.tools.environment_audit -- the PYTHONPATH-shadowing finding."""

import hashlib
import io
import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard.tools.danger import Severity
from toolguard.tools.environment_audit import EnvironmentFinding, audit_environment

SHADOW_FINDING_ID = "pythonpath-shadows-hook"

# Captured at import, before any test patches $HOME, so the snapshot below
# anchors on the developer's real files rather than on a fixture.
_REAL_HOME = Path(os.path.expanduser("~"))
# The repo's logs/ is deliberately absent: a concurrent toolguard-governed
# process appends to it, and a snapshot cannot attribute a write to an author.
# In-process log writes are caught by _real_log_dir_guard.py, which can.
_REAL_ANCHORS = (_REAL_HOME / ".claude", _REAL_HOME / ".toolguard")

_DIGEST_CAP = 256 * 1024

_SNAPSHOT_BEFORE: dict[str, tuple] = {}
_SNAPSHOT_TAKEN = False


def _should_digest(path: Path, size: int) -> bool:
    """Whether to record a content digest for *path* as well as size and mtime.

    Size and mtime alone cannot see a same-size rewrite finer than this
    filesystem's mtime granularity -- measured at ~8ms here, so an immediate
    rewrite is invisible. Digesting everything is not an option either:
    hashing all of ~/.claude measured 3.9s per snapshot, against 0.4s for
    ~/.toolguard. So the transcript tree under ~/.claude keeps size+mtime and
    everything toolguard itself writes gets a digest.
    """
    if size > _DIGEST_CAP:
        return False
    claude = _REAL_HOME / ".claude"
    return not (claude in path.parents and path.parent != claude)


def _snapshot(roots) -> dict[str, tuple]:
    """Map every existing file under *roots* to (size, mtime_ns, digest-or-None)."""
    out: dict[str, tuple] = {}
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            try:
                st = path.stat()
                digest = None
                if path.is_file() and _should_digest(path, st.st_size):
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
            except OSError:
                continue
            out[str(path)] = (st.st_size, st.st_mtime_ns, digest)
    return out


def _snapshot_diff(before, after) -> list[str]:
    """Return one description per added, removed or rewritten path."""
    changes = [f"ADDED {p}" for p in sorted(set(after) - set(before))]
    changes += [f"REMOVED {p}" for p in sorted(set(before) - set(after))]
    changes += [
        f"REWRITTEN {p} {before[p]} -> {after[p]}"
        for p in sorted(set(before) & set(after))
        if before[p] != after[p]
    ]
    return changes


# Mutable so the mechanism self-test can point the hooks at a fixture and prove
# they fire without writing anywhere real.
_GUARDED_ROOTS = [str(anchor) for anchor in _REAL_ANCHORS]
_WRITES_UNDER_GUARD: list[tuple[str, str]] = []
_ORIGINAL_WRITERS: dict[str, object] = {}

_WRITE_MODES = set("wxa+")


def _is_guarded(path) -> bool:
    """Whether *path* names a file under a guarded root (a file descriptor never does)."""
    try:
        text = os.fspath(path)
    except TypeError:
        return False
    text = str(text)
    return any(
        text == root or text.startswith(root + os.sep) for root in _GUARDED_ROOTS
    )


def _install_write_recorder():
    """Record every write-mode open, create, delete or rename under a guarded root.

    A snapshot cannot say WHO wrote: measured 2026-08-14, the host agent
    rewrites its own transcript under ~/.claude/projects while the suite runs.
    Wrapping the write entry points can, for this process.
    """
    import builtins

    _ORIGINAL_WRITERS.update(
        {
            "builtins.open": builtins.open,
            "io.open": io.open,
            "os.open": os.open,
            **{
                f"os.{n}": getattr(os, n)
                for n in (
                    "remove",
                    "unlink",
                    "rmdir",
                    "mkdir",
                    "makedirs",
                    "rename",
                    "replace",
                )
            },
        }
    )
    real_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if _WRITE_MODES & set(mode) and _is_guarded(file):
            _WRITES_UNDER_GUARD.append(("open", str(file)))
        return real_open(file, mode, *args, **kwargs)

    real_os_open = os.open

    def guarded_os_open(path, flags, *args, **kwargs):
        writing = flags & (
            os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
        )
        if writing and _is_guarded(path):
            _WRITES_UNDER_GUARD.append(("os.open", str(path)))
        return real_os_open(path, flags, *args, **kwargs)

    def make_recorder(name, real):
        def recorder(*args, **kwargs):
            if args and _is_guarded(args[0]):
                _WRITES_UNDER_GUARD.append((name, str(args[0])))
            return real(*args, **kwargs)

        return recorder

    builtins.open = guarded_open
    io.open = guarded_open
    os.open = guarded_os_open
    for name in ("remove", "unlink", "rmdir", "mkdir", "makedirs", "rename", "replace"):
        setattr(os, name, make_recorder(name, _ORIGINAL_WRITERS[f"os.{name}"]))


def _uninstall_write_recorder():
    """Put the real write entry points back."""
    import builtins

    for dotted, original in _ORIGINAL_WRITERS.items():
        module_name, attribute = dotted.split(".")
        setattr(
            {"builtins": builtins, "io": io, "os": os}[module_name], attribute, original
        )
    _ORIGINAL_WRITERS.clear()


def setUpModule():
    """Record the developer's real config files, and start watching for writes."""
    global _SNAPSHOT_BEFORE, _SNAPSHOT_TAKEN
    _SNAPSHOT_BEFORE = _snapshot(_REAL_ANCHORS)
    _SNAPSHOT_TAKEN = True
    _install_write_recorder()


def tearDownModule():
    """Stop watching; the assertions themselves live in TestZZ... below."""
    _uninstall_write_recorder()


@contextmanager
def _in_directory(path: Path):
    """Run the block with the process cwd at *path*, restoring it afterwards."""
    previous = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class IsolatedEnvironmentTest(unittest.TestCase):
    """Base: a throwaway $HOME, an emptied environment, fixtures built inside that HOME.

    Fixtures live under the fixture HOME so that anything resolving through
    $HOME, or walking upward from a fixture, stays inside the fixture.
    ConfigIsolationMixin does not apply here: nothing under test reaches
    config discovery -- the only ambient input is PYTHONPATH.
    """

    def setUp(self):
        tmp = TemporaryDirectory(prefix="tg-env-audit-home-")
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        patcher = patch.dict(os.environ, {"HOME": str(self.home)}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Falsifies the isolation itself: without clear=True an ambient
        # PYTHONPATH leaks in, and this module's subject IS PYTHONPATH.
        self.assertIsNone(os.environ.get("PYTHONPATH"))
        self.assertEqual(os.environ["HOME"], str(self.home))
        self.assertNotEqual(self.home, _REAL_HOME)

    def plain_dir(self, name: str) -> Path:
        """Create and return an empty fixture directory holding no toolguard package."""
        path = self.home / name
        path.mkdir()
        return path

    def shadow_dir(self, name: str) -> Path:
        """Create a fixture directory holding its own ``toolguard/__init__.py``."""
        path = self.home / name
        (path / "toolguard").mkdir(parents=True)
        (path / "toolguard" / "__init__.py").write_text("")
        return path

    def assert_distinguishable(self, *paths: Path):
        """Fail unless no path string is a substring of another.

        Fixture paths share a parent, so a naive assertIn/assertNotIn pair over
        them can pass for the wrong reason.
        """
        names = [str(p) for p in paths]
        for one in names:
            for other in names:
                if one is not other:
                    self.assertNotIn(one, other)


class TestShadowingFinding(IsolatedEnvironmentTest):
    """audit_environment() -- what it reports for a given PYTHONPATH."""

    def test_absent_pythonpath_produces_no_finding(self):
        """
        Given an environment with no PYTHONPATH at all
        When audit_environment runs
        Then it returns no findings -- the normal case must never nag
        """
        self.assertEqual(audit_environment({}), [])

    def test_empty_pythonpath_produces_no_finding(self):
        """
        Given PYTHONPATH is set to the empty string
        When audit_environment runs
        Then it returns no findings
        """
        self.assertEqual(audit_environment({"PYTHONPATH": ""}), [])

    def test_entry_without_a_toolguard_package_produces_no_finding(self):
        """
        Given PYTHONPATH holds a directory with no toolguard/ package
        When audit_environment runs
        Then it returns no findings
        """
        entry = self.plain_dir("plain-entry")
        self.assertEqual(audit_environment({"PYTHONPATH": str(entry)}), [])

    def test_shadowing_entry_produces_one_high_finding(self):
        """
        Given PYTHONPATH holds a directory with its own toolguard/ package
        When audit_environment runs
        Then it returns exactly one HIGH EnvironmentFinding naming that entry,
        under the stable finding id its consumers key on
        """
        entry = self.shadow_dir("shadow-entry")

        findings = audit_environment({"PYTHONPATH": str(entry)})

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIsInstance(finding, EnvironmentFinding)
        self.assertEqual(finding.finding_id, SHADOW_FINDING_ID)
        self.assertIs(finding.severity, Severity.HIGH)
        self.assertIn(str(entry), finding.description)
        self.assertIn("PYTHONPATH", finding.description)

    def test_the_finding_explains_its_impact(self):
        """
        Given a shadowing PYTHONPATH entry
        When audit_environment runs
        Then the finding carries impact text of its own
        """
        entry = self.shadow_dir("shadow-entry")

        finding = audit_environment({"PYTHONPATH": str(entry)})[0]

        self.assertTrue(finding.impact.strip())
        self.assertNotEqual(finding.impact, finding.description)

    def test_the_finding_offers_a_remediation(self):
        """
        Given a shadowing PYTHONPATH entry
        When audit_environment runs
        Then the finding carries remediation text of its own -- a security
        finding a reader cannot act on is noise
        """
        entry = self.shadow_dir("shadow-entry")

        finding = audit_environment({"PYTHONPATH": str(entry)})[0]

        self.assertTrue(finding.remediation.strip())
        self.assertNotEqual(finding.remediation, finding.description)

    def test_severity_outranks_the_lower_levels(self):
        """
        Given a shadowing PYTHONPATH entry
        When audit_environment runs
        Then the finding's severity ranks above MEDIUM and LOW, not merely
        equal to some named constant
        """
        entry = self.shadow_dir("shadow-entry")

        finding = audit_environment({"PYTHONPATH": str(entry)})[0]

        self.assertGreater(finding.severity, Severity.MEDIUM)
        self.assertGreater(finding.severity, Severity.LOW)

    def test_only_the_shadowing_entry_of_several_is_named(self):
        """
        Given PYTHONPATH holds a harmless entry followed by a shadowing one
        When audit_environment runs
        Then the finding names the shadowing entry and not the harmless one
        """
        plain = self.plain_dir("plain-entry")
        shadow = self.shadow_dir("shadow-entry")
        self.assert_distinguishable(plain, shadow)

        findings = audit_environment(
            {"PYTHONPATH": os.pathsep.join([str(plain), str(shadow)])}
        )

        self.assertEqual(len(findings), 1)
        self.assertIn(str(shadow), findings[0].description)
        self.assertNotIn(str(plain), findings[0].description)

    def test_every_shadowing_entry_is_named_in_a_single_finding(self):
        """
        Given PYTHONPATH holds two shadowing entries
        When audit_environment runs
        Then one finding names both, so neither is dropped
        """
        first = self.shadow_dir("alpha-entry")
        second = self.shadow_dir("bravo-entry")
        self.assert_distinguishable(first, second)

        findings = audit_environment(
            {"PYTHONPATH": os.pathsep.join([str(first), str(second)])}
        )

        self.assertEqual(len(findings), 1)
        self.assertIn(str(first), findings[0].description)
        self.assertIn(str(second), findings[0].description)

    def test_shadowing_entries_are_named_in_pythonpath_order(self):
        """
        Given PYTHONPATH holds two shadowing entries
        When audit_environment runs
        Then the finding names them in PYTHONPATH order, since the earlier
        entry is the one that actually wins the import
        """
        first = self.shadow_dir("alpha-entry")
        second = self.shadow_dir("bravo-entry")
        self.assert_distinguishable(first, second)

        description = audit_environment(
            {"PYTHONPATH": os.pathsep.join([str(second), str(first)])}
        )[0].description

        self.assertLess(description.index(str(second)), description.index(str(first)))

    def test_a_repeated_shadowing_entry_is_named_once(self):
        """
        Given the same shadowing directory appears twice on PYTHONPATH
        When audit_environment runs
        Then one finding names it exactly once
        """
        entry = self.shadow_dir("shadow-entry")

        findings = audit_environment(
            {"PYTHONPATH": os.pathsep.join([str(entry), str(entry)])}
        )

        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].description.count(str(entry)), 1)

    def test_a_toolguard_directory_without_init_py_is_not_reported(self):
        """
        Given PYTHONPATH holds a directory containing a toolguard/ directory
        with no __init__.py
        When audit_environment runs
        Then it returns no findings, because such a namespace portion loses to
        the installed regular package and shadows nothing
        """
        # Measured 2026-08-14 with a child interpreter: with this layout on
        # PYTHONPATH, `import toolguard` still resolves to the installed copy.
        entry = self.plain_dir("namespace-entry")
        (entry / "toolguard").mkdir()

        self.assertEqual(audit_environment({"PYTHONPATH": str(entry)}), [])


class TestWhatTheAuditDoesNotLookAt(IsolatedEnvironmentTest):
    """The predicate is the environment, not this process's own provenance."""

    def test_home_contents_do_not_affect_the_audit(self):
        """
        Given a HOME holding both a toolguard/ package and a toolguard hook
        config, and no PYTHONPATH
        When audit_environment runs
        Then it returns no findings -- the audit reads PYTHONPATH, not HOME
        """
        (self.home / "toolguard").mkdir()
        (self.home / "toolguard" / "__init__.py").write_text("")
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "toolguard_hook.toml").write_text("[hook]\n")

        self.assertEqual(audit_environment({}), [])

    def test_a_shadowing_cwd_alone_produces_no_finding(self):
        """
        Given the process runs inside a directory holding its own toolguard/
        package, with PYTHONPATH unset
        When audit_environment runs
        Then it returns no findings -- how this process was launched is
        deliberately not the question asked
        """
        entry = self.shadow_dir("cwd-entry")

        with _in_directory(entry):
            self.assertEqual(audit_environment({}), [])

    def test_a_relative_entry_is_resolved_against_the_auditing_process_cwd(self):
        """
        Given PYTHONPATH is the relative entry "."
        When audit_environment runs from inside a shadowing directory and then
        from a directory that is not
        Then it reports a finding only in the first case, because a relative
        entry is resolved against the auditing process's own cwd
        """
        shadow = self.shadow_dir("cwd-entry")
        plain = self.plain_dir("plain-entry")

        with _in_directory(shadow):
            from_shadow = audit_environment({"PYTHONPATH": "."})
        with _in_directory(plain):
            from_plain = audit_environment({"PYTHONPATH": "."})

        self.assertEqual(len(from_shadow), 1)
        self.assertEqual(from_plain, [])


class TestWhatTheAuditReads(IsolatedEnvironmentTest):
    """Every path the audit stats, recorded, so "it never touched the machine" is measured."""

    @contextmanager
    def _recording_stat(self):
        """Record every path passed to os.stat while the block runs."""
        recorded: list[str] = []
        real_stat = os.stat

        def recording(path, *args, **kwargs):
            recorded.append(str(path))
            return real_stat(path, *args, **kwargs)

        with patch.object(os, "stat", recording):
            self.assertIs(os.stat, recording)
            yield recorded

    def test_the_audit_stats_only_the_entries_it_was_given(self):
        """
        Given PYTHONPATH holds one shadowing fixture entry
        When audit_environment runs with os.stat recorded
        Then the only paths it stats are inside the fixture
        """
        entry = self.shadow_dir("shadow-entry")

        with self._recording_stat() as recorded:
            findings = audit_environment({"PYTHONPATH": str(entry)})

        self.assertEqual(len(findings), 1)
        # Falsifies the recorder: an inert one would leave this empty.
        self.assertIn(str(entry / "toolguard" / "__init__.py"), recorded)
        self.assertEqual([p for p in recorded if not p.startswith(str(self.home))], [])

    def test_an_absent_pythonpath_makes_the_audit_read_nothing_at_all(self):
        """
        Given an environment with no PYTHONPATH
        When audit_environment runs with os.stat recorded
        Then it stats nothing: the clean answer costs no filesystem access,
        and no ambient location is consulted for one
        """
        with self._recording_stat() as recorded:
            self.assertEqual(audit_environment({}), [])

        self.assertEqual(recorded, [])


class TestDefaultEnvironment(IsolatedEnvironmentTest):
    """The env=None default must actually reach os.environ, at call time."""

    def test_reads_os_environ_when_no_env_is_passed(self):
        """
        Given os.environ itself carries a shadowing PYTHONPATH
        When audit_environment is called with no argument at all
        Then it reports that entry, so the default is exercised rather than
        merely declared
        """
        entry = self.shadow_dir("shadow-entry")
        os.environ["PYTHONPATH"] = str(entry)

        findings = audit_environment()

        self.assertEqual(len(findings), 1)
        self.assertIn(str(entry), findings[0].description)

    def test_the_default_is_read_on_every_call(self):
        """
        Given os.environ gains a shadowing PYTHONPATH between two argument-less
        calls
        When audit_environment runs before and after the change
        Then the first call reports nothing and the second reports the entry,
        so nothing was captured at import time
        """
        entry = self.shadow_dir("shadow-entry")

        before = audit_environment()
        os.environ["PYTHONPATH"] = str(entry)
        after = audit_environment()

        self.assertEqual(before, [])
        self.assertEqual(len(after), 1)


class TestShadowingShapesThatAreMissed(IsolatedEnvironmentTest):
    """Layouts that shadow a real import but are not reported. Expected RED."""

    def test_a_toolguard_module_file_on_the_path_is_reported(self):
        """
        Given PYTHONPATH holds a directory containing a toolguard.py module
        When audit_environment runs
        Then it reports that entry, because such a module wins over the
        installed package for any fresh toolguard import
        """
        # Measured 2026-08-14 with a child interpreter: with this layout on
        # PYTHONPATH, `import toolguard` resolves to the fixture's toolguard.py.
        entry = self.plain_dir("module-entry")
        (entry / "toolguard.py").write_text("")

        findings = audit_environment({"PYTHONPATH": str(entry)})

        self.assertEqual(len(findings), 1)
        self.assertIn(str(entry), findings[0].description)


class TestSnapshotMechanism(unittest.TestCase):
    """The real-file snapshot below is only worth having if it fires."""

    def test_snapshot_diff_reports_a_planted_file_and_an_in_place_rewrite(self):
        """
        Given a snapshot of a directory tree
        When a file is planted, one is deleted, and one is rewritten in place
        with same-length content and its original mtime restored
        Then the diff names all three and leaves the untouched file out
        """
        with TemporaryDirectory(prefix="tg-env-audit-snap-") as tmp:
            root = Path(tmp)
            (root / "kept.txt").write_text("aaaa")
            (root / "rewritten.txt").write_text("aaaa")
            (root / "removed.txt").write_text("aaaa")
            before = _snapshot([root])
            original_mtime = (root / "rewritten.txt").stat().st_mtime_ns

            (root / "planted.txt").write_text("new")
            (root / "removed.txt").unlink()
            (root / "rewritten.txt").write_text("bbbb")
            # Restoring the mtime reproduces deterministically what this
            # filesystem's ~8ms mtime granularity does by accident.
            os.utime(root / "rewritten.txt", ns=(original_mtime, original_mtime))
            changes = _snapshot_diff(before, _snapshot([root]))

        self.assertIn(f"ADDED {root / 'planted.txt'}", changes)
        self.assertIn(f"REMOVED {root / 'removed.txt'}", changes)
        self.assertEqual(
            1,
            len(
                [c for c in changes if c.startswith(f"REWRITTEN {root / 'rewritten'}")]
            ),
        )
        self.assertNotIn(str(root / "kept.txt"), " ".join(changes))


class TestWriteRecorderMechanism(unittest.TestCase):
    """The write recorder is only worth having if every route reaches it."""

    def test_the_recorder_sees_writes_by_every_route_it_claims(self):
        """
        Given a fixture directory temporarily added to the guarded roots
        When a file is written through pathlib, through open(), and a directory
        is created and a file deleted through os
        Then all four writes are recorded, and none is attributed elsewhere
        """
        with TemporaryDirectory(prefix="tg-env-audit-writes-") as tmp:
            _GUARDED_ROOTS.append(tmp)
            try:
                (Path(tmp) / "pathlib.txt").write_text("x")
                with open(Path(tmp) / "builtin.txt", "w") as handle:
                    handle.write("x")
                os.mkdir(Path(tmp) / "made")
                os.remove(Path(tmp) / "pathlib.txt")
                recorded = [e for e in _WRITES_UNDER_GUARD if e[1].startswith(tmp)]
            finally:
                _GUARDED_ROOTS.remove(tmp)
                _WRITES_UNDER_GUARD[:] = [
                    e for e in _WRITES_UNDER_GUARD if not e[1].startswith(tmp)
                ]

        self.assertEqual({op for op, _ in recorded}, {"open", "mkdir", "remove"})
        self.assertEqual(len([e for e in recorded if e[0] == "open"]), 2)


class TestZZRealFilesystemUntouched(unittest.TestCase):
    """Runs last in this module: nothing here may touch the developer's files."""

    def test_no_test_here_wrote_under_a_guarded_root(self):
        """
        Given the write recorder installed before this module's first test
        When every test in this module has run
        Then it recorded no write under ~/.claude or ~/.toolguard

        This is the attributable half: it can only accuse this process.
        """
        self.assertTrue(_ORIGINAL_WRITERS, "the write recorder was never installed")
        self.assertEqual(_WRITES_UNDER_GUARD, [])

    def test_the_real_config_files_are_unchanged(self):
        """
        Given a snapshot of ~/.claude and ~/.toolguard taken before this
        module's tests
        When every test in this module has run
        Then no file under those roots was added, removed or rewritten

        The unattributable half: it catches a write by any means, including
        from a child process, at the cost of also seeing other processes.
        """
        self.assertTrue(_SNAPSHOT_TAKEN, "the before-snapshot never ran")
        if not _SNAPSHOT_BEFORE:
            # Zero files is a pass only when there was provably nothing to
            # guard -- e.g. the suite run against an empty $HOME.
            self.assertEqual([a for a in _REAL_ANCHORS if a.exists()], [])
        # ~/.claude/projects is the host agent's own transcript tree, rewritten
        # while the suite runs (measured 2026-08-14). Excluded because it is
        # foreign churn, not a signal about this module.
        transcripts = str(_REAL_HOME / ".claude" / "projects") + os.sep
        changes = [
            change
            for change in _snapshot_diff(_SNAPSHOT_BEFORE, _snapshot(_REAL_ANCHORS))
            if transcripts not in change
        ]
        self.assertEqual(changes, [])


if __name__ == "__main__":
    unittest.main()
