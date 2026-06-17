---
title: TOO-8 Phase 2 Coder Task Recall
type: report
permalink: toolguard/implementation/too-8-phase-2-coder-task-recall
tags:
- TOO-8
- task-memory
- coder-state-for-recovery
- hierarchical-config
---

# TOO-8 Phase 2 Coder Task Recall

Filename: implementation/coder-latest-task-recall.md (this is the canonical recall note)

## Task
Implement TOO-8 Phase 2 (hierarchical discovery + more-specific-wins resolution + project-root-relative paths + cleanup) at /home/arnon/projects/toolguard.

Baseline: 601 tests OK (verified). uv run python -m unittest discover -s test -t .

## Scope (4 items)
1. Hierarchical discovery: walk project_root UP TO ~ inclusive, collecting per-dir-with-.claude the 4 configs (toolguard_hook.local, settings.local, toolguard_hook, settings; TOML>JSON within level). Levels most-specific-first (specificity index 0=project). ALWAYS include ~/.claude as least-specific even if project not under ~. Stop at ~. Toggle `hierarchical_configuration` read ONLY from project-level toolguard_hook config; default TRUE. False => project+user only (today). ConfigLayer carries specificity/order + provenance.
2. More-specific-wins (PERMISSIONS only): evaluate levels most->least specific; within level deny-first; FIRST level with ANY match decides, stop. No match anywhere => DENY. Apply to bash, each compound sub-command independently, and file-path tools. Matching stays in permissions.py/compound.py (typed lists -> decision). Cascade orchestration in a small resolver fed by Configuration.permission_layers(tool). Single path only.
3. NEW: relative config paths ALWAYS relative to PROJECT ROOT (not declaring dir, not cwd). Applies to scalar path settings (backup_dir) and relative Read/Write/Edit patterns (after extended-syntax prefix strip; not starting / or ~). Absolute and ~ unaffected. Document in docstrings + technical-notes.md. TESTS: relative backup_dir + relative R/W/E pattern at project/intermediate/user level all resolve to <project_root>/<relative>.
4. Cleanup (AFTER callers migrated): migrate config_divergence.py + auto_migrate.py onto Configuration API; ONE structural strip _strip_tool_wrapper using re.fullmatch(r'[A-Za-z0-9_]+\((.*)\)'); remove tool-prefix FIXME; underscore-prefix internal config fns once no out-of-module callers; add Configuration.project_root property, migrate hook off find_project_root.

## OUT of scope
hard_deny (P3); conflict logging (P4); governed_tools/takeover/scalar RESOLUTION semantics change (P5) - keep current merge across N levels. LEAVE config_sync user-wins + its FIXME pin test AS-IS (that FIXME is scalar/decision#4 = Phase 5, NOT tool-prefix). Only the tool-prefix FIXME at config.py:605 is resolved here.

## KEY DECISIONS / TENSIONS
- config_sync FIXME (config.py:924) is about scalar resolution flip to project-wins -> Phase 5, LEAVE AS-IS. Confirmed: not tool-prefix. Report this.
- RENAMING TENSION: legacy names (find_project_root, discover_config_files, load_permissions, load_takeover_mode_config, load_governed_tools*, merge_*, load_config_sync_settings, *_from_sources) are referenced as PUBLIC by MANY formal tests (test_config, test_takeover_mode, test_permissions, test_toml_config, test_auto_migrate, test_configuration, test_migration) and external modules (log_writer.py, scripts/migrate_permissions.py use config.find_project_root; env_config.py has its OWN). Prompt authorizes test edits for this phase but warns against churn. DECISION: implement real behavior; for renames keep backward-compat references to avoid 50+ mechanical patch-site churn risk. Underscore the truly-internal new helpers; do not aggressively privatize widely-patched legacy names.

## Tooling
- Tests: uv run python -m unittest discover -s test -t .
- NO ruff format. ruff check only.
- Coverage: uv run python tools/coverage_stdlib.py (>>>>>> = unexecuted)
- Do NOT edit toolguard/parser/bash_parser.py (generated)
- Every new test needs Given/When/Then docstring.

## Files in play
config.py, hook.py, compound.py, permissions.py, config_divergence.py, auto_migrate.py, env_config.py, log_writer.py, scripts/migrate_permissions.py, technical-notes.md (create). Tests under test/unit.
</content>
</invoke>
