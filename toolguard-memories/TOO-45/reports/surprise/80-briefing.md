---
title: 80-briefing
type: note
permalink: toolguard/too-45/reports/surprise/80-briefing
---

# File inventory


## toolguard/ — 78 modules

- `toolguard/__init__.py` (3 lines) — Toolguard: a pre-tool-use hook that governs Claude Code tool permissions.
- `toolguard/_git.py` (49 lines) — Shared git-subprocess boilerplate: one place for the argv shape, the output
- `toolguard/ambient.py` (120 lines) — The machine state toolguard reads: home directory, current directory, process
- `toolguard/api.py` (107 lines) — Public decision interface for toolguard.
- `toolguard/auto_migrate.py` (160 lines) — Unattended migration of divergent permissions from settings.local.json into
- `toolguard/compound.py` (1102 lines) — Compound command permission checking for toolguard.
- `toolguard/config.py` (2095 lines) — Configuration loading for toolguard.
- `toolguard/config_divergence.py` (238 lines) — Config divergence detection: permissions present in Claude's native
- `toolguard/config_types.py` (755 lines) — Plain configuration data types, split out of :mod:`toolguard.config` so this module can
- `toolguard/config_validation.py` (139 lines) — Content-level validation of a toolguard permissions section.
- `toolguard/config_write_guard.py` (356 lines) — Self-protection gate for every toolguard config-file write.
- `toolguard/constants.py` (51 lines) — Shared immutable constants for toolguard.
- `toolguard/env_config.py` (193 lines) — Environment-variable and ``.env`` configuration for toolguard: where the
- `toolguard/error_log.py` (185 lines) — Error, warning, conflict, and crash logging for toolguard.
- `toolguard/error_reporter.py` (225 lines) — Central error/warning/notice reporting for toolguard.
- `toolguard/file_lock.py` (164 lines) — Cross-process OS advisory file locking: one context manager, :func:`exclusive`.
- `toolguard/file_matching.py` (252 lines) — File-path pattern matching for toolguard.
- `toolguard/hook.py` (1371 lines) — Claude Code PreToolUse hook entry point: reads one hook event on stdin and
- `toolguard/install_provenance.py` (358 lines) — Detects whether the toolguard package currently governing this process might
- `toolguard/install_update.py` (427 lines) — Detects whether the installed toolguard distribution is behind its git remote.
- `toolguard/issues.py` (25 lines) — Structured configuration issue type.
- `toolguard/log_writer.py` (576 lines) — Writes toolguard's on-disk audit trail: the per-invocation resolution log
- `toolguard/normalization.py` (211 lines) — Path normalization for consistent pattern matching.
- `toolguard/once_per.py` (192 lines) — Facade for throttling a warning or an action to at most once per period, per
- `toolguard/once_per_store.py` (476 lines) — Cross-project ``(project, kind, scope)`` claim store backing "once per
- `toolguard/parser/__init__.py` (7 lines) — Bash command parser package for toolguard.
- `toolguard/parser/bash_parser.py` (6536 lines) — (no module docstring)
- `toolguard/parser/command_extractor.py` (907 lines) — Split a bash command line into the leaf commands a permission rule can match.
- `toolguard/parser/command_model.py` (737 lines) — Abstract Command Model (IR) for the bash command extractor.
- `toolguard/parser/multiline.py` (579 lines) — The lexical pre-pass in front of the bash PEG parser.
- `toolguard/path_utils.py` (318 lines) — Low-level filesystem path helpers: the bounded walk up the parent directories,
- `toolguard/patterns.py` (144 lines) — Extended pattern matching for toolguard.
- `toolguard/permission_migration.py` (1344 lines) — Library implementation of toolguard's permission-migration workflow.
- `toolguard/permission_resolution.py` (444 lines) — The decision engine for permission resolution.
- `toolguard/permissions.py` (426 lines) — Command string matching and permission decisions for the command-kind tools. The two
- `toolguard/resolve.py` (343 lines) — Permission resolver layer for toolguard.
- `toolguard/rule_entry.py` (771 lines) — Structured allow/deny/ask rule entry: shape normalization and tool scoping.
- `toolguard/rule_sort.py` (721 lines) — Canonical rule sorting and comment-preserving ``[permissions]`` machinery.
- `toolguard/scripts/__init__.py` (1 lines) — Toolguard utility scripts.
- `toolguard/scripts/migrate_permissions.py` (96 lines) — The ``toolguard-migrate`` console script.
- `toolguard/session_start.py` (483 lines) — Toolguard SessionStart Hook for Claude Code.
- `toolguard/session_warnings.py` (34 lines) — The takeover-mode notices: enabled-and-bypassed, or a fail-safe conflict.
- `toolguard/subagent.py` (206 lines) — Subagent identification for toolguard.
- `toolguard/testing/__init__.py` (9 lines) — Test and experiment support for toolguard.
- `toolguard/testing/sandbox.py` (671 lines) — An isolated, throwaway toolguard project for behavioural experiments.
- `toolguard/toml_scan.py` (490 lines) — Boundary scanning of raw TOML text: ``[permissions]`` section spans and
- `toolguard/tool_spec.py` (113 lines) — Static registry of the tools toolguard knows how to govern.
- `toolguard/tools/__init__.py` (7 lines) — Deterministic helpers behind the toolguard skills and config tooling.
- `toolguard/tools/annotate.py` (178 lines) — Generated ``# toolguard:`` comments that explain confusing rule interactions.
- `toolguard/tools/clarity.py` (270 lines) — Rule-interaction clarity analyzer.
- `toolguard/tools/config_access.py` (625 lines) — Configuration access for toolguard's own skills and dev tooling: per-layer rule views
- `toolguard/tools/consolidate.py` (963 lines) — Consolidation proposals for toolguard permission rules.
- `toolguard/tools/corpus.py` (124 lines) — Corpus harvesting: combine daily-log and transcript evidence for a project.
- `toolguard/tools/danger.py` (632 lines) — Ranked static risk findings over toolguard allow rules.
- `toolguard/tools/decision_ledger.py` (366 lines) — Prior-decision ledger for the maintenance skill.
- `toolguard/tools/edit_proposal.py` (193 lines) — General rule-edit proposal model and in-memory application.
- `toolguard/tools/environment_audit.py` (88 lines) — Environment shadowing audit: report a ``PYTHONPATH`` that would shadow the
- `toolguard/tools/hierarchy.py` (404 lines) — Hierarchy operations on a config: move a rule between layers, and find rules a
- `toolguard/tools/installer.py` (2338 lines) — ``toolguard-install``: an AGENT-FACING installer helper for toolguard.
- `toolguard/tools/log_harvest.py` (370 lines) — Log harvester for toolguard daily log files.
- `toolguard/tools/maintenance.py` (1327 lines) — Maintenance aggregator: compose the rule-maintenance engines into one report.
- `toolguard/tools/migration_gate.py` (85 lines) — Migration safety pre-flight: combine the project-root and working-tree gates.
- `toolguard/tools/mining.py` (437 lines) — Rule mining: turn a harvested command corpus into actionable rule candidates.
- `toolguard/tools/pattern_overlap.py` (82 lines) — Command-prefix overlap tests for DEFAULT ``cmd:*``/``cmd:**`` patterns.
- `toolguard/tools/project_root.py` (21 lines) — Re-export of the project-root primitives implemented in :mod:`toolguard.path_utils`.
- `toolguard/tools/recommended_protections.py` (203 lines) — Recommended [hard_deny] protections: the curated "Sensitive files" pattern set.
- `toolguard/tools/redundancy.py` (339 lines) — Redundancy detection for toolguard permission rules.  Two independent strategies:
- `toolguard/tools/replay.py` (243 lines) — Decision-replay diff for toolguard config safety verification.
- `toolguard/tools/rule_apply.py` (496 lines) — Apply accepted consolidation proposals to config files and report what changed.
- `toolguard/tools/security_audit.py` (826 lines) — Unified security audit aggregator for toolguard.
- `toolguard/tools/self_integrity.py` (68 lines) — The canonical ``[hard_deny]`` patterns protecting ``~/.toolguard`` -- toolguard's
- `toolguard/tools/self_permission.py` (200 lines) — Self-permissioning: the allow/ask rules toolguard's own skills need to function.
- `toolguard/tools/sorters.py` (59 lines) — Sorting of in-memory toolguard rule arrays.
- `toolguard/tools/takeover_audit.py` (505 lines) — Takeover-mode invariant checker for toolguard.
- `toolguard/tools/transcript_harvest.py` (346 lines) — Transcript harvester: parse Claude Code conversation transcripts into the same
- `toolguard/tools/uninstall_readiness.py` (293 lines) — Uninstall readiness: the fixed rule set an install seeds so toolguard's OWN
- `toolguard/tools/working_tree.py` (87 lines) — Working-tree cleanliness guard for the apply/migrate safety gate.
- `toolguard/update_check.py` (46 lines) — The ``toolguard-update-check`` console script.

## tools/ — 10 modules

- `tools/__init__.py` (0 lines) — (no module docstring)
- `tools/architecture_fitness.py` (4002 lines) — Dev instrument for the TOO-45 architecture-refactoring loop: five modes over this
- `tools/change_role_classifier.py` (2493 lines) — Dev-only measurement instrument, not shipped (the wheel's ``packages`` list is
- `tools/check_doc_links.py` (188 lines) — Verify every internal ``[text](file#anchor)`` link in the documentation resolves.
- `tools/comment_hygiene.py` (563 lines) — Finds ticket-reference narrative (``TOO-nnn``) left in docstrings and comments, and checks that
- `tools/corpus_build.py` (1007 lines) — Dev-only tool that builds and verifies the TOO-45 verdict-equivalence corpus
- `tools/coverage_stdlib.py` (18 lines) — (no module docstring)
- `tools/generated_files.py` (34 lines) — Detects machine-generated ``*.py`` files by content banner, never by filename:
- `tools/touch_set_inventory.py` (792 lines) — Dev-only instrument: the structural inventory of ONE tree, and the input given to the
- `tools/touch_set_score.py` (1102 lines) — Dev-only instrument: the M2 "expected touch set" comparison built for the

## test/ — 89 modules

- `test/__init__.py` (3 lines) — Unit tests for toolguard package.
- `test/unit/__init__.py` (110 lines) — Unit tests for toolguard package modules.
- `test/unit/_config_isolation.py` (146 lines) — Shared test isolation for toolguard's config-discovery hierarchy.
- `test/unit/_once_per_isolation.py` (26 lines) — Shared test isolation for toolguard.once_per_store._STORE_PATH.
- `test/unit/_real_log_dir_guard.py` (200 lines) — Structural regression guard: the developer's real logs/ directory must
- `test/unit/_real_once_per_home_guard.py` (126 lines) — Structural regression guard: the developer's real
- `test/unit/_subprocess_harness.py` (80 lines) — Shared cross-process test harness: spawn a ``python -c <script>`` child with
- `test/unit/test_ambient.py` (320 lines) — Unit tests for toolguard.ambient: where toolguard reads home, cwd and the
- `test/unit/test_api.py` (1072 lines) — Unit tests for toolguard.api: the side-effect-free decide() primitive.
- `test/unit/test_architecture.py` (649 lines) — Architectural invariant tests for toolguard's module layering: governed modules
- `test/unit/test_architecture_fitness.py` (4175 lines) — Unit tests for ``tools/architecture_fitness.py``.
- `test/unit/test_ask_resolution.py` (408 lines) — Resolver tests for the ``ask`` permission list, driving the real decision engine
- `test/unit/test_auto_migrate.py` (701 lines) — Unit tests for auto_migrate.
- `test/unit/test_bash_parser.py` (416 lines) — Unit tests for the Canopy PEG bash parser: the AST structure it produces for
- `test/unit/test_change_role_classifier.py` (2302 lines) — Tests for ``tools/change_role_classifier.py``; see that module's docstring for role
- `test/unit/test_command_extractor_inline_code.py` (449 lines) — Tests for foreign inline-code detection.
- `test/unit/test_compound.py` (2860 lines) — Unit tests for compound command permission checking.
- `test/unit/test_compound_resolve_seam.py` (579 lines) — Tests for the compound/resolve seam: ``RuntimeVerdict.sub_matches`` content
- `test/unit/test_config.py` (502 lines) — Unit tests for toolguard config-file discovery, project-root detection, and
- `test/unit/test_config_divergence.py` (1123 lines) — Unit tests for config_divergence module.
- `test/unit/test_config_write_guard.py` (721 lines) — Unit tests for toolguard.config_write_guard -- the self-protection gate every
- `test/unit/test_configuration.py` (3977 lines) — Unit tests for :func:`toolguard.config.load_configuration` and the
- `test/unit/test_env_config.py` (1078 lines) — Unit tests for toolguard environment configuration.
- `test/unit/test_error_log.py` (266 lines) — Unit tests for toolguard.error_log.
- `test/unit/test_error_reporter.py` (590 lines) — Unit tests for toolguard.error_reporter -- which destination each severity reaches.
- `test/unit/test_file_lock.py` (617 lines) — Unit tests for toolguard.file_lock's exclusive() context manager: single-process
- `test/unit/test_git_helper.py` (273 lines) — Unit tests for toolguard._git -- the shared git-subprocess helper.
- `test/unit/test_hard_deny.py` (709 lines) — Unit tests for the ``[hard_deny]`` safety valve: pooling, carve-outs, and enforcement.
- `test/unit/test_hierarchical.py` (765 lines) — Hierarchical config discovery, more-specific-wins resolution, project-root-relative paths.
- `test/unit/test_hook.py` (3394 lines) — Unit tests for toolguard.hook: the PreToolUse entry point for Bash and file-path tools.
- `test/unit/test_hook_error_reporter.py` (593 lines) — Unit tests for the error-reporter wiring in toolguard.hook: main() owns one
- `test/unit/test_hook_eval.py` (856 lines) — Unit tests for the read-only ``toolguard --eval`` evaluation mode.
- `test/unit/test_install_provenance.py` (1035 lines) — Unit tests for toolguard.install_provenance.
- `test/unit/test_log_writer.py` (1436 lines) — Unit tests for toolguard's logging functionality: file creation, format, and content.
- `test/unit/test_logging_streams.py` (1103 lines) — Unit tests for the per-concern log streams, conflict logging, and provenance in reasons.
- `test/unit/test_migration.py` (2941 lines) — Unit tests for permission migration script.
- `test/unit/test_multiline_bash.py` (743 lines) — Unit tests for TOO-17: multi-line Bash command handling (fail-open bypass fix).
- `test/unit/test_normalization.py` (578 lines) — Unit tests for path normalization.
- `test/unit/test_once_per.py` (642 lines) — Unit tests for toolguard.once_per: the once-per-period facade
- `test/unit/test_once_per_store.py` (974 lines) — Unit tests for toolguard.once_per_store, the shared claim/release/reap store.
- `test/unit/test_patterns.py` (520 lines) — Unit tests for extended pattern matching in toolguard.
- `test/unit/test_permission_resolution.py` (324 lines) — Unit tests for :mod:`toolguard.permission_resolution`.
- `test/unit/test_permissions.py` (800 lines) — Unit tests for toolguard permission checking logic.
- `test/unit/test_recommended_protections.py` (479 lines) — Unit tests for toolguard.tools.recommended_protections.
- `test/unit/test_resolve.py` (2603 lines) — Anti-drift contract test: api.decide() must produce the same verdict as
- `test/unit/test_rule_entry.py` (1338 lines) — Unit tests for :mod:`toolguard.rule_entry`. Every :class:`~toolguard.rule_entry.RuleEntry`
- `test/unit/test_rule_sort.py` (1651 lines) — Unit tests for rule_sort's comment-preserving TOML [permissions] machinery:
- `test/unit/test_sandbox.py` (1308 lines) — Unit tests for :mod:`toolguard.testing.sandbox`.
- `test/unit/test_self_integrity.py` (292 lines) — Unit tests for toolguard.tools.self_integrity: the declarative [hard_deny]
- `test/unit/test_session_start.py` (1580 lines) — Unit tests for toolguard.session_start.
- `test/unit/test_session_warnings.py` (288 lines) — Unit tests for toolguard.session_warnings: the takeover-mode-active notice.
- `test/unit/test_static_analysis_coverage.py` (485 lines) — Guards that `pyscn` can actually read this repository's source.
- `test/unit/test_symlink_hierarchy.py` (566 lines) — Symlinks in the configuration path: project-root anchoring through a symlinked
- `test/unit/test_takeover_mode.py` (543 lines) — Unit tests for takeover mode: toolguard as sole gatekeeper while Claude's
- `test/unit/test_toml_config.py` (954 lines) — Unit tests for TOML configuration support in toolguard.
- `test/unit/test_tool_spec.py` (636 lines) — Unit tests for toolguard.tool_spec: the registry that decides what a governed
- `test/unit/test_tools_annotate.py` (790 lines) — Unit tests for toolguard.tools.annotate (generated ``# toolguard:`` comments):
- `test/unit/test_tools_clarity.py` (576 lines) — Unit tests for the rule-interaction clarity analyzer (toolguard.tools.clarity):
- `test/unit/test_tools_config_access.py` (1284 lines) — Unit tests for toolguard.tools.config_access, the thin facade over Configuration.
- `test/unit/test_tools_consolidate.py` (1039 lines) — Unit tests for toolguard.tools.consolidate -- consolidation proposal engine.
- `test/unit/test_tools_corpus.py` (685 lines) — Unit tests for the corpus harvesting helper (toolguard.tools.corpus).
- `test/unit/test_tools_danger.py` (698 lines) — Unit tests for toolguard.tools.danger -- static risk finding detection.
- `test/unit/test_tools_decision_ledger.py` (670 lines) — Unit tests for :mod:`toolguard.tools.decision_ledger`, the store for the maintenance
- `test/unit/test_tools_edit_proposal.py` (839 lines) — Unit tests for the general edit-proposal model and in-memory application.
- `test/unit/test_tools_environment_audit.py` (675 lines) — Unit tests for toolguard.tools.environment_audit -- the PYTHONPATH-shadowing finding.
- `test/unit/test_tools_hierarchy.py` (734 lines) — Unit tests for toolguard.tools.hierarchy -- moving rules between config layers
- `test/unit/test_tools_installer.py` (3320 lines) — Unit tests for ``toolguard.tools.installer`` -- the agent-facing ``toolguard-install``
- `test/unit/test_tools_log_harvest.py` (923 lines) — Unit tests for toolguard.tools.log_harvest.
- `test/unit/test_tools_maintenance.py` (1860 lines) — Unit tests for the maintenance aggregator (toolguard.tools.maintenance).
- `test/unit/test_tools_migration_gate.py` (300 lines) — Unit tests for the migration safety pre-flight (toolguard.tools.migration_gate).
- `test/unit/test_tools_mining.py` (1187 lines) — Unit tests for toolguard.tools.mining -- classifying a corpus into rule
- `test/unit/test_tools_project_root.py` (488 lines) — Unit tests for :func:`toolguard.tools.project_root.resolve_project_root`, which
- `test/unit/test_tools_redundancy.py` (452 lines) — Unit tests for toolguard.tools.redundancy -- redundant rule detection.
- `test/unit/test_tools_replay.py` (1170 lines) — Unit tests for toolguard.tools.replay.
- `test/unit/test_tools_rule_apply.py` (1032 lines) — Unit tests for toolguard.tools.rule_apply: applying consolidation proposals
- `test/unit/test_tools_security_audit.py` (2615 lines) — Unit tests for toolguard.tools.security_audit -- unified security audit aggregator.
- `test/unit/test_tools_self_permission.py` (359 lines) — Unit tests for toolguard.tools.self_permission.
- `test/unit/test_tools_sorters.py` (387 lines) — Unit tests for toolguard.tools.sorters -- canonical rule-array sorting: tool
- `test/unit/test_tools_takeover_audit.py` (1242 lines) — Unit tests for toolguard.tools.takeover_audit -- takeover invariant checker.
- `test/unit/test_tools_transcript_harvest.py` (1190 lines) — Unit tests for toolguard.tools.transcript_harvest -- transcripts into the LogEntry corpus shape.
- `test/unit/test_tools_uninstall_readiness.py` (603 lines) — Unit tests for toolguard.tools.uninstall_readiness: the declarative table, its
- `test/unit/test_tools_working_tree.py` (449 lines) — Unit tests for the working-tree cleanliness guard (toolguard.tools.working_tree).
- `test/unit/test_touch_set_inventory.py` (1730 lines) — Tests for ``tools/touch_set_inventory.py`` (TOO-45 M2).
- `test/unit/test_touch_set_score.py` (1340 lines) — Tests for ``tools/touch_set_score.py`` (TOO-45 M2).
- `test/unit/test_update_check.py` (1265 lines) — Unit tests for toolguard.install_update and the toolguard.update_check CLI wrapper.
- `test/unit/test_verdict_corpus.py` (549 lines) — Replay tests for the verdict-equivalence corpus: a HARD tier that must never be
- `test/unit/test_zz_real_log_dir_guard.py` (541 lines) — Regression tests for the guards against writes to the real repo ``logs/``
- `test/verdict_corpus/__init__.py` (10 lines) — The TOO-45 verdict-equivalence corpus.
- `test/verdict_corpus/fixture_loader.py` (1165 lines) — Shared fixture-loading, decision-replay, and comparison code for the


# Declared layer map (.pyscn.toml)

```toml
[[architecture.layers]]
name = "foundation"
# Leaves: no toolguard imports at all, or only other foundation modules.
packages = ["ambient", "constants", "issues", "path_utils", "normalization", "patterns", "toml_scan", "_git", "install_provenance", "install_update", "file_lock", "tool_spec"]

[[architecture.layers]]
name = "observability"
# Cross-cutting side-effecting services: logging, error reporting, session
# warnings, update notices. These sit LOW deliberately (TOO-45, after Arnon's
# reading of the MR-08 canary). They were previously in "runtime", whose own
# comment gave the game away -- "entry points AND side-effecting concerns"
# conflates two unrelated criteria. `hook`/`session_start` belong high because
# they ORCHESTRATE; these four are leaves that happen to have side effects, and
# side-effect-ness is orthogonal to dependency direction.
#
# What the old placement cost, measured: config-layer code could not legally
# reach a logging or warning module, so four config modules hand-rolled 8
# direct stderr writes instead (config 1, env_config 2, auto_migrate 4,
# config_divergence 1 -- punch-list #01 removed the rest as a side effect
# when it rewrote auto_migrate/config_divergence onto once_per). The layering
# was not being obeyed there, it was being routed around -- and a
# zero-violation report could never show that, because the map matched the
# code. Consolidated onto `error_reporter` (TOO-45 punch-list #04).
#
# error_log and session_warnings import NOTHING from toolguard; update_check
# imports only foundation; log_writer took exactly one config-layer import
# (config.find_project_root), a thin wrapper over a foundation primitive, now
# path_utils.require_project_root. Configuration reaches log_writer by
# INJECTION already -- a plain dict parameter -- not by import. error_reporter
# imports only error_log, same-layer -- log_writer.resolve_log_dir is called
# by hook.py (runtime layer), which passes the resolved Path in, not by
# error_reporter itself (TOO-45 punch-list #04 follow-up: Reporter).
packages = ["log_writer", "error_log", "session_warnings", "update_check", "once_per_store", "once_per", "error_reporter"]

[[architecture.layers]]
name = "config"
# Owns the configuration model, discovery, validation, and the write path.
packages = ["rule_entry", "config_types", "config", "config_validation", "config_write_guard", "env_config", "rule_sort", "auto_migrate", "config_divergence", "permission_migration"]

[[architecture.layers]]
name = "engine"
# Pure decision logic: pattern matching, command decomposition, resolution.
packages = ["permissions", "compound", "resolve", "parser", "permission_resolution", "file_matching"]

[[architecture.layers]]
name = "api"
# The engine's public decision interface (TOO-45 R6-S2). Sits directly above
# "engine" so both "runtime" and "tooling" can legally import it downward.
packages = ["api"]

[[architecture.layers]]
name = "runtime"
# Entry points only: the modules that ORCHESTRATE a hook invocation. The
# side-effecting logging/warning services that used to share this layer now sit
# in "observability", below "config" -- see the note there.
packages = ["hook", "session_start", "subagent"]

[[architecture.layers]]
name = "tooling"
# Operator tooling behind the skills, plus one-off scripts.
packages = ["tools", "scripts"]

[[architecture.layers]]
name = "support"
# Test/experiment support. May reach anywhere; nothing may depend on it.
packages = ["testing"]

```