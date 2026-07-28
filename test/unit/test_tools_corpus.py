"""Unit tests for the corpus harvesting helper (toolguard.tools.corpus)."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from toolguard.tools.corpus import harvest_corpus, resolve_logs_dir
from toolguard.tools.log_harvest import LogEntry


def _entry(stamp: str, command: str) -> LogEntry:
    """Build a minimal Bash LogEntry at the given ``YYYY-MM-DD HH:MM:SS`` stamp."""
    return LogEntry(
        timestamp=datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S"),
        tool="Bash",
        command=command,
        status="EXECUTED",
        rule_text=None,
        agent="main",
        log_file=None,
    )


class TestResolveLogsDir(unittest.TestCase):
    """resolve_logs_dir maps a project to its daily-log directory."""

    def test_returns_logs_subdir_of_resolved_root(self):
        """
        Given a directory whose project root resolves to ROOT
        When resolve_logs_dir is called
        Then it returns ROOT/logs.
        """
        resolution = mock.Mock(root=Path("/proj/root"))
        with mock.patch(
            "toolguard.tools.corpus.resolve_project_root", return_value=resolution
        ):
            self.assertEqual(
                resolve_logs_dir(Path("/proj/root/sub")), Path("/proj/root/logs")
            )

    def test_falls_back_to_start_dir_when_root_unresolved(self):
        """
        Given a directory whose project root cannot be resolved (root is None)
        When resolve_logs_dir is called
        Then it falls back to start_dir/logs rather than raising.
        """
        resolution = mock.Mock(root=None)
        with mock.patch(
            "toolguard.tools.corpus.resolve_project_root", return_value=resolution
        ):
            self.assertEqual(
                resolve_logs_dir(Path("/somewhere")), Path("/somewhere/logs")
            )


class TestHarvestCorpus(unittest.TestCase):
    """harvest_corpus merges the daily-log and transcript corpora."""

    def test_merges_both_sources_sorted_by_timestamp(self):
        """
        Given the log harvester and transcript harvester each yield one entry
        When harvest_corpus runs
        Then both entries are returned, merged and sorted oldest-first.
        """
        log_entry = _entry("2026-06-20 10:00:00", "git status")
        transcript_entry = _entry("2026-06-19 09:00:00", "ls -la")
        resolution = mock.Mock(root=Path("/proj"))
        with (
            mock.patch(
                "toolguard.tools.corpus.resolve_project_root", return_value=resolution
            ),
            mock.patch(
                "toolguard.tools.corpus.harvest", return_value=[log_entry]
            ) as log_harvest,
            mock.patch(
                "toolguard.tools.corpus.harvest_transcripts",
                return_value=[transcript_entry],
            ) as transcript_harvest,
            mock.patch(
                "toolguard.tools.corpus.transcript_dir_for_project",
                return_value=Path("/home/.claude/projects/x"),
            ),
        ):
            corpus = harvest_corpus(Path("/proj"), max_age_days=30)
        self.assertEqual([e.command for e in corpus], ["ls -la", "git status"])
        # The daily logs were read from <root>/logs, transcripts from the project dir.
        self.assertEqual(log_harvest.call_args.args[0], Path("/proj/logs"))
        self.assertEqual(log_harvest.call_args.kwargs["max_age_days"], 30)
        self.assertEqual(transcript_harvest.call_args.kwargs["max_age_days"], 30)

    def test_missing_sources_yield_empty_corpus(self):
        """
        Given a project whose logs and transcript directories do not exist
        When harvest_corpus runs against real (absent) directories
        Then it returns an empty list rather than raising.
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corpus = harvest_corpus(
                root,
                logs_dir=root / "logs",
                transcripts_dir=root / "transcripts",
            )
        self.assertEqual(corpus, [])

    def test_explicit_overrides_bypass_resolution(self):
        """
        Given explicit logs_dir and transcripts_dir overrides
        When harvest_corpus runs
        Then those exact directories are passed to the harvesters (no default
            <root>/logs or transcript-dir derivation).
        """
        resolution = mock.Mock(root=Path("/proj"))
        with (
            mock.patch(
                "toolguard.tools.corpus.resolve_project_root", return_value=resolution
            ),
            mock.patch(
                "toolguard.tools.corpus.harvest", return_value=[]
            ) as log_harvest,
            mock.patch(
                "toolguard.tools.corpus.harvest_transcripts", return_value=[]
            ) as transcript_harvest,
        ):
            harvest_corpus(
                Path("/proj"),
                logs_dir=Path("/custom/logs"),
                transcripts_dir=Path("/custom/transcripts"),
            )
        self.assertEqual(log_harvest.call_args.args[0], Path("/custom/logs"))
        self.assertEqual(
            transcript_harvest.call_args.args[0], Path("/custom/transcripts")
        )


if __name__ == "__main__":
    unittest.main()
