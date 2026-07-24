---
title: TOO-30 test isolation refactor - review findings
type: note
permalink: toolguard/too-30/too-30-test-isolation-refactor-review-findings
tags:
- project
- TOO-30
- testing
- review
---

## Review of the test-isolation retrofit (2026-07-23)

Reviewed personally (not just the feature-coder's self-report): `ConfigIsolationMixin` in
`test/unit/_config_isolation.py`, plus all 8 retrofitted files.

**Correctness -- verified sound.** Traced the trickiest parts by hand:
- `test_config.py`'s `TestFindProjectRoot`: 6/7 tests correctly need no isolation at all
  (markers resolve before the walk would reach `Path.home()` -- that's the point, testing
  the real unpatched function); the 7th (`test_raises_when_nothing_found`) correctly uses
  the mixin.
- Chased a suspected classic mock-patching trap in `test_migration.py` (old code patched
  `toolguard.scripts.migrate_permissions.find_project_root`, new code relies on the mixin
  patching `toolguard.config.find_project_root` instead). Resolved as a non-issue: the old
  patch target was actually never called within `migrate()`'s code path.
- Pure in-memory `Configuration`-construction test classes (e.g.
  `TestMoreSpecificWinsResolution`) were correctly left off the mixin -- no file I/O, no
  isolation needed.

**`_IsolatedEnvTestCase` fully retired (2026-07-24 follow-up).** Arnon caught (via Telegram)
that this pre-existing base class in `test_hierarchical.py` -- env-only CLAUDE_SETTINGS_PATH
popping, predates this whole effort, only discovered during this review, never in the
original retirement plan (which only knew about `_isolated_hierarchy`, a different,
already-retired helper) -- was still present alongside the new mixin, expecting full
consolidation onto one mechanism. Investigated: of the 7 hand-rolled
`patch("toolguard.config.find_project_root"...)`/`patch("toolguard.config.Path.home"...)`
sites, 6 needed only "project nested N directories under home" (testing the ancestor walk),
which `ConfigIsolationMixin` didn't support -- so extended it with an optional
`project_under_home` parameter (a '/'-separated relative path, e.g. `"a/b/proj"`) rather than
its fixed sibling layout. Migrated all 6 onto the extended mixin. The 7th
(`test_walk_stops_at_home`) genuinely needs a `.claude` positioned ABOVE home, which the
mixin's model (home as the top of the isolated tree) structurally cannot represent --
left as the one true, documented, irreducible exception, now self-contained (clears
`CLAUDE_SETTINGS_PATH` itself via `enterContext` rather than depending on a shared base
class). `_IsolatedEnvTestCase` class definition deleted entirely; every class in the file now
inherits either `(ConfigIsolationMixin, unittest.TestCase)` or plain `unittest.TestCase`
(for the 3 classes needing zero isolation: `TestMoreSpecificWinsResolution`,
`TestResolveCompoundEdgeCases`, and the no-file-I/O parts of others).
`test/unit/CLAUDE.md`'s "7 such exceptions" reference updated to "1" plus a pointer to try
`project_under_home=` before assuming a new hand-rolled exception is needed. Full suite
1513 tests green, `ruff check` clean after this follow-up.

**Flagged, resolved:** the "partially redundant `_IsolatedEnvTestCase`" item noted after the
first pass is now fully resolved (class removed), not just flagged.
