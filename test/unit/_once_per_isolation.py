"""
Shared test isolation for toolguard.once_per_store._STORE_PATH.

The degraded-notice registry needs no separate reset here: it lives on each
:class:`~toolguard.once_per.OncePer` instance, not as shared module state.
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from toolguard import once_per_store


class IsolatedStoreMixin:
    """Isolate once_per_store._STORE_PATH to a fresh tmp file for each test."""

    def setUp(self):
        """Redirect the shared store to a tmp file for the duration of the test."""
        self._store_tmp = TemporaryDirectory()
        self.addCleanup(self._store_tmp.cleanup)
        patcher = patch.object(
            once_per_store, "_STORE_PATH", Path(self._store_tmp.name) / "once_per.db"
        )
        patcher.start()
        self.addCleanup(patcher.stop)
