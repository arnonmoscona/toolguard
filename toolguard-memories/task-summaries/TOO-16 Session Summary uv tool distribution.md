---
title: TOO-16 Session Summary uv tool distribution
type: note
permalink: toolguard/task-summaries/too-16-session-summary-uv-tool-distribution
tags:
- task-summary
- TOO-16
---

# TOO-16 Session Summary: uv tool distribution

**Status**: COMPLETE (2026-06-23), pushed + validated on the real global install.

**What it did**: made toolguard installable/runnable as a `uv tool` without being a project
dependency. Shipped: install + hook-config docs (git+https and local-path), validation command,
`run_hook.sh` retired; a `toolguard-update-check` console script that detects git/local/editable
installs and reports/upgrades appropriately (offline-safe, `--upgrade`/`--quiet`, exit 0/1/2);
`--help` + interactive-tty guard on the `toolguard`/`toolguard-session-start` hooks. Version 0.3.1,
774 tests green.

**Key facts**: plain `uv tool upgrade toolguard` re-resolves git HEAD (no `--reinstall`). Installed
commit lives in PEP-610 `direct_url.json`. ruff on 3.14 strips `except (A,B):` parens (valid).

**Deferred (future ticket)**: PyPI publish at ~RC1 needs a DISTRIBUTION rename (`toolguard` taken
on PyPI) + then native upgrade replaces the custom checker. Full details: [[TOO-16 uv tool distribution]].
