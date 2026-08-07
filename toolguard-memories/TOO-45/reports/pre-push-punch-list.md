---
title: TOO-45 pre-push punch list
type: note
permalink: toolguard/too-45/reports/pre-push-punch-list
tags:
- task-memory
- TOO-45
- pre-push
---

# TOO-45 pre-push punch list

**Arnon's instruction, 2026-08-07: tackle these BEFORE a push and AFTER the canary experiments.** Nothing here is a canary finding requiring a decision; these are defects and doc drift found along the way. Decisions on the reports themselves wait until his review is done.

This complements [[follow-up-queue]], which holds the earlier accepted bug list. Items 1-4 there (log_writer `sys.exit(1)` fail-open, the pattern-string join key, the three failed once-per-session attempts, the `docs/config-sync.md` marker-path mismatch) are still open and are **not** repeated here.

## Code defects

**1. `DEFAULT_INDICATORS` and `CONFIG_ROOT_INDICATORS` disagree about what a project is.** `toolguard/tools/project_root.py`'s tiered resolver already treats `package.json` as a marker; `toolguard/path_utils.py:105`'s `CONFIG_ROOT_INDICATORS` — used by both runtime `find_project_root` loaders — does not. So the tooling has recognised JavaScript projects all along while the runtime has not. Found by the MR-07 canary on ground the refactor never touched.

**2. `toolguard/session_warnings.py` is named for a session semantic and implements a daily one.** Suppression is by `.toolguard-warned-YYYY-MM-DD` marker files. This is a **fourth** instance of the once-per-session trap already recorded three times in [[follow-up-queue]] item 3 — and this one is encoded in a module name, so it teaches the wrong model to every reader.

**3. `intent-disclosure-rules.example.toml` does not exist.** `CLAUDE.md:170` cites it by name. It and `attest-readonly-rule.example.toml` are sitting in `tmp/new-claude-md/toolguard/` — drafted during TOO-19 and never moved into place. Either move them to the repo root or remove the reference. Found by a blind reader who was told to read the file and could not.

**3a. `log_writer.py` disagrees with itself about the default log format — latent now, live the moment anyone makes the format selectable.** Line 449 picks the extension as `"md" if logging_format == "markdown" else "jsonlines"`; line 465 picks the content as JSONLines only `if logging_format == "jsonlines"`, markdown otherwise. So any third value yields **markdown content in a `.jsonlines` file**. Unreachable today because nothing passes a third value; MR-08's requirement (unrecognised values fall back to markdown) makes it reachable immediately. The fix is one normalisation function at the single entry point rather than two independent comparisons. Found by an MR-08 canary implementer that was not looking for it.

**3b. Two independent hardcoded copies of the file-tools list in `toolguard/tools/danger.py`** — lines 305 and 366, both `if tool in ("Read", "Write", "Edit"):`, wired to no shared constant. Both MR-10 implementers found them, and **neither found them by following code** — only by grepping for literal tuples. Consequence: any new file-path tool is silently misjudged by the arbitrary-exec and destructive-command detectors. Failure direction is false-positive, so not a security hole, but it is undetectable drift.

**3c. `tools/log_harvest.py` matches the resolution log by the `.md` filename only.** Not a defect today, but it means the retained JSONLines renderer can never actually be enabled without breaking corpus harvest, mining and replay — and it would break them **silently**, returning an empty corpus for the day with no error. Worth knowing before anyone treats "the JSONLines renderer is retained for a future setting" as a small piece of remaining work.

## Documentation sweep

**4. `permission_mode` — one of two pages is wrong.** `docs/auto-mode.md:99` says the logs record it "for every decision". `toolguard/log_writer.py:377` writes it conditionally behind `if record.permission_mode:` on an `Optional[str] = None` field, and `docs/architecture.md` omits it from the resolution-entry field list and from both examples.

**5. Whether the foreign-interpreter ASK floor covers command tools other than `Bash` is unstated, and it is security-relevant.** `configuration.md` calls it "the Bash-only inline/heredoc-foreign-code floor", while the JetBrains terminal tool and custom MCP command tools are documented as command tools sharing the `Bash(...)` pattern namespace and compound decomposition. If `python -c` through the JetBrains terminal is not floored, that is an enforcement gap, not a doc gap. **Settle by measurement, not by reading.**

**5a. `docs/architecture.md` describes PRE-TOO-45 behaviour as current, and this drift is ours.** It specifies that compound sub-entries get a different field set from ordinary entries — no `Provenance` field, folded instead into `Matched Rule` in a bracketed format. That was master's behaviour and D1 changed it: provenance is now its own log field. **This is the highest-priority documentation item in this list**, because it is not pre-existing drift but drift this ticket introduced, and because a doc that specifies a divergence reads as a design decision rather than as a description that fell behind. Found by a blind predictor who was misled by it — it pointed at a bespoke string-formatting site that no longer exists.

**6. `docs/configuration.md`'s "Project root detection" section is stale independent of anything above** — it lists only `.git` and `pyproject.toml`, omitting `.hg`, `.jj`, `.claude` and `CLAUDE.md`, which have been strong anchors since TOO-15.

**7. `toolguard/constants.py`'s self-description mis-points.** "Shared immutable constants for toolguard" is exactly where a reader looks for the project-marker list; it holds `FILE_TOOLS`, `DIST_NAME`, `STATUS_*` instead. Cost a blind predictor a wrong first answer in both trees.

**8. `docs/auto-mode.md` recommends the legacy nested `[takeover_mode] no_match_fallback` form** that `configuration.md` and `takeover-mode.md` both tell you not to use in new configs — on the page an agent is most likely to follow verbatim.

**9. `docs/architecture.md` cites a bare internal ticket ID as rationale** in a document linked from `llms.txt` and `README.md`. Worth a sweep for the same pattern elsewhere.

**10. Six further gaps** a blind reader could not resolve from the docs — where the `allow_with_warning` warning is actually written, which warnings are once-per-day versus once-per-session, whether an ordinary file-path denial carries provenance, what `uv` means as a heredoc sink, and `agent-map.md`'s own staleness disclosure. Full list in [[micro-requirements-blind]], final section.

## Tooling note, not a defect

**11. Pin the ruff version when linting matters.** Unpinned `uvx ruff` (0.16.1) reports ~39 violations — UP006, SIM117, DTZ005, RUF022, I001 — that are absent under the project's pinned 0.15.14. Not real debt; ruff's default rule set drifts. Relevant to any agent instructed to "make lint clean".

## Not to be forgotten

**12. `test/unit/test_static_analysis_coverage.py` is still untracked** and was never included in the R6 commit. It is the guard that stops pyscn silently dropping a file from its metrics.

**13. The three new evidence tools are untracked**: `tools/change_role_classifier.py`, `tools/touch_set_inventory.py`, `tools/touch_set_score.py`, plus four test files. Decide whether they belong in the repo at all before pushing — they are experiment instrumentation, not product.
