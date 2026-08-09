"""
Shared test isolation helper for toolguard.once_per_store._STORE_PATH.

One copy, used by every test module that needs a fresh, isolated claim
store per test method. Previously four byte-identical private copies of
this mixin (test_auto_migrate.py, test_config_divergence.py,
test_session_warnings.py, test_once_per_store.py), three of them also
poking a module-level degraded-notice registry via a function-local import
-- both symptoms of the primitive not owning its own state (TOO-45
punch-list #01, item 10). The degraded-notice registry is now a per-
:class:`~toolguard.once_per.OncePer` instance attribute (item 8), so no
reset is needed here: each production throttled thing (e.g.
``auto_migrate.AUTO_MIGRATION``) is exercised by its degraded-notice path in
at most one test in the whole suite, and test_once_per.py mints a fresh
instance per test via the ``once_per.day(...)`` factory.
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
