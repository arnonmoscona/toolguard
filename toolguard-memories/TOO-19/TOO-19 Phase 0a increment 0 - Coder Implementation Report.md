---
title: TOO-19 Phase 0a increment 0 - Coder Implementation Report
type: note
permalink: toolguard/too-19/too-19-phase-0a-increment-0-coder-implementation-report
tags:
- TOO-19
- task-memory
---

## Summary

Fixed the `~/.toolguard/rules/` scanning gap: `toolguard/config.py`'s rules-directory
discovery previously scanned ONLY `$XDG_CONFIG_HOME/toolguard/rules` (default
`~/.config/toolguard/rules`), silently never enforcing anything placed in the separate,
pre-existing `~/.toolguard/rules/` directory. `_rules_dir() -> Path` was replaced by
`_rules_dirs() -> Tuple[Path, Path]`, returning both candidate directories in precedence
order (XDG first). Also fixed `_level_for_path()` mislabelling a file resolved through a
symlink as `"project"` instead of `"user"` when the symlink's real target lived under the
(previously unrecognised) legacy directory -- the exact real-world stopgap workaround in
place on this machine (`~/.config/toolguard/rules/gh.rules.toml` symlinked to
`~/.toolguard/rules/gh.rules.toml`).

Strict TDD: all new/changed tests were written first, run to confirm failure for the
right reason (4 `AttributeError` for not-yet-existing `_rules_dirs`/`shadowed_path`, 6
behavioral failures for the unscanned legacy dir / missing shadow warning / stale
`_level_for_path` anchor), then the implementation was added to turn them green.

## Files changed

1. **`toolguard/config.py`** (+292/-90 net across the diff)
   - `_rules_dir() -> Path` replaced by `_rules_dirs() -> Tuple[Path, Path]` (XDG dir,
     legacy `~/.toolguard/rules` dir), preserving the exact empty-string-means-unset XDG
     semantics.
   - Extracted `_resolve_stem_formats(by_stem)` from the TOML-over-JSON winner logic that
     used to live inline in `_discover_rules_files`; both the single-dir and new
     multi-dir discovery functions now share it (no duplicated precedence logic).
   - `_discover_rules_files(rules_dir)` kept as a single-directory primitive, unchanged
     signature/behaviour (all 8 pre-existing unit tests for it pass unmodified).
   - New `_merged_rules_by_stem(rules_dirs)`: first-directory-wins per-stem merge across
     the two candidate directories.
   - New `_discover_rules_files_multi(rules_dirs)`: multi-dir discovery wrapper
     (`_resolve_stem_formats` + `_merged_rules_by_stem`), used by `_discover_levels`.
   - New `_shadowed_rules_stems(rules_dirs)`: detects stems present in more than one
     candidate directory, returning `{stem: representative_shadowed_path}`.
   - `_discover_levels()`: rules-dir loop now calls `_discover_rules_files_multi(_rules_dirs())`
     instead of `_discover_rules_files(_rules_dir())`. Docstring updated.
   - `_level_for_path()`: anchor tuple is now `(Path.home() / ".claude",) + _rules_dirs()`
     -- both candidate dirs are recognised "user" anchors. Docstring updated.
   - `ConfigLayer`: new field `shadowed_path: Optional[Path] = None`, documented parallel
     to the existing `duplicate_format` field; explicitly notes `duplicate_format` is now
     computed WITHIN the winning directory only (via `_merged_rules_by_stem`, not
     `_group_rules_files_by_stem` directly), so a cross-directory format mismatch (e.g.
     `gh.toml` in XDG + `gh.json` in legacy) is correctly classified as shadowing, not a
     format duplicate.
   - `load_configuration()`: added lazy `rules_shadowed_stems` computation alongside the
     existing lazy `rules_duplicate_stems` (which now uses `_merged_rules_by_stem` instead
     of the single-dir `_group_rules_files_by_stem`); sets `shadowed_path` on each
     `toolguard_hook_rules` layer.
   - `Configuration.validation_issues()`: new check (section "1b", between the existing
     "both formats" check and the `takeover_mode` check) iterating layers for
     `shadowed_path is not None` and emitting a `warning`-level `Issue` naming both the
     winning path and the shadowed path. Docstring's detection list updated.

2. **`test/unit/test_configuration.py`** (+393/-5 net)
   - Renamed the 3 white-box `_rules_dir()` tests to `_rules_dirs()`, asserting the full
     2-tuple (XDG entry + legacy entry) for the set/unset/empty-string cases.
   - Added `test_config_layer_shadowed_path_defaults_to_none` (mirrors the existing
     `unexpected_keys` default test).
   - Added to `TestRulesDirectoryDiscovery` (extended, per the ticket's instruction, not a
     new class): `test_legacy_toolguard_dir_file_discovered_end_to_end` (the actual
     reported bug), `test_different_stems_in_both_dirs_both_load`,
     `test_same_stem_in_both_dirs_xdg_wins_and_shadow_warning_emitted`,
     `test_cross_dir_format_mismatch_is_shadowing_not_duplicate_format`,
     `test_missing_legacy_toolguard_dir_is_a_no_op`,
     `test_empty_legacy_toolguard_dir_is_a_no_op`.
   - Added to `TestRulesDirectoryValidationAndProvenance`:
     `test_level_for_path_returns_user_for_legacy_toolguard_dir_path` and
     `test_level_for_path_returns_user_for_symlinked_legacy_toolguard_dir_path` (the
     latter reproduces the exact real symlink direction found on this machine -- real file
     under `~/.toolguard/rules`, symlink placed inside the XDG dir -- confirmed by
     inspecting `~/.config/toolguard/rules/` and `~/.toolguard/rules/` directly before
     writing the test; my first draft had the symlink direction backwards and the red-phase
     run caught it).
   - Updated the historical TOO-30 RED-phase header comment and the
     `TestRulesDirectoryDiscovery` class docstring to describe the TOO-19 additions.
   - Every new test carries a Given/When/Then BDD docstring.

3. **`test/unit/_config_isolation.py`** -- module docstring updated to mention the second
   candidate directory (`~/.toolguard/rules/`) and to state explicitly that both
   directories derive from `Path.home()`, so the existing `Path.home()` patch already
   isolates both -- no new mixin parameter was needed.

4. **`test/unit/CLAUDE.md`** -- "Why this file exists" section updated to mention
   `~/.toolguard/rules/` alongside the existing XDG-directory mention, and to state that
   both derive from `Path.home()` so no new anchor/parameter was required for TOO-19. The
   "Before pushing" checklist section was left as-is (already generically worded to catch
   this class of change; no TOO-19-specific edit needed there).

## Answers to the report-back questions

- **Shadowing warning vs. `duplicate_format` precedent**: fit the precedent directly, no
  extra plumbing needed. Added one `Optional[Path]` field to `ConfigLayer`
  (`shadowed_path`), computed lazily once per `load_configuration()` call via a new
  `_shadowed_rules_stems()` helper (structurally parallel to the existing
  `rules_duplicate_stems` computation), and one new block in `validation_issues()`
  structurally parallel to the existing "both formats" block. No new control flow, no new
  hierarchy concept, no new module.
- **`Path.home()` isolation coverage**: confirmed. `_rules_dirs()`'s legacy entry is
  `Path.home() / ".toolguard" / "rules"` -- the same `Path.home()` that
  `ConfigIsolationMixin.isolate_config_environment()` already patches for the `~/.claude`
  anchor. No mixin changes were needed; verified by every new end-to-end/discovery test
  using only the existing mixin (no hand-rolled patching) and passing.
- **Deviations / things worth flagging**:
  - The four call sites named in the spec (`_discover_levels` ~540, `_level_for_path`
    ~1867, `load_configuration`'s duplicate-stem block ~1981, and the
    `_RULES_FILE_ALLOWED_SECTIONS`-adjacent docstring) were confirmed complete via
    `grep -n "_rules_dir\b"` before starting -- there were no other call sites in
    `toolguard/` or `test/`.
  - User-facing docs (`docs/configuration.md`, `docs/architecture.md`,
    `docs/agent-map.md`, `docs/agent-guides.md`) describe the "split user-level rules
    directory" as XDG-only and were NOT updated -- the ticket's doc-update scope was
    explicitly limited to `test/unit/CLAUDE.md` and `_config_isolation.py`. Flagging this
    as a real, pre-existing doc-drift gap that should probably be a small follow-up (it is
    user-visible behaviour, not just test infra), but I did not fold it into this
    increment to avoid scope creep beyond what was asked.
  - `toolguard/tools/hierarchy.py`'s module docstring and `HierarchyMigration.to_provenance`
    docstring mention `~/.config/toolguard/rules/` specifically when describing the
    "never auto-promote into a rules-directory layer" guardrail. No functional change was
    needed there -- the guardrail checks `source_type == "toolguard_hook_rules"`, which
    both candidate directories share -- but the docstring's specific path mention is now
    slightly incomplete. Left untouched (comment-only, not a functional gap); noting it
    for awareness.
  - My first draft of the symlink `_level_for_path` test had the symlink direction
    backwards (real file outside both dirs, symlink placed inside the legacy dir) --
    which does NOT reproduce the actual reported bug and would not have been fixed by the
    KISS anchor-list approach. I inspected the real
    `~/.config/toolguard/rules/gh.rules.toml` -> `~/.toolguard/rules/gh.rules.toml` symlink
    on this machine before finalizing the test, confirming the real direction (symlink in
    XDG dir, real file in legacy dir) and rewrote the test to match. Worth double-checking
    this detail if it comes up again elsewhere.

## Self-review / Definition of Done

- Full suite: `uv run python -m unittest discover -s test -t .` -> 1522 tests, OK (1513
  baseline + 9 net new test methods; some renames replace old ones 1:1).
- `uv run ruff check .` (repo-wide, lint only) -> All checks passed.
- `uv run ruff format` run ONLY on the touched files
  (`toolguard/config.py`, `test/unit/test_configuration.py`, `test/unit/_config_isolation.py`)
  -- confirmed idempotent afterwards (`ruff format --check` on the same three files: "3
  files already formatted").
- `uv run python -m py_compile` on all three touched `.py` files -> OK.
- Anti-pattern scan: no `async`/`await`, no `threading`, no local/in-function imports
  introduced.
- All new/changed public and private functions carry docstrings (Args/Returns), matching
  the existing module's style.
- Requirements cross-checked line-by-line against the task recall memory
  (`TOO-19/TOO-19 Phase 0a increment 0 - coder task recall.md`) -- all items covered.

## Elapsed time / rough cost estimate

- Phase 1 (planning, reading code, task recall): ~15 min
- Phase 2 (TDD: writing tests, red-phase run, implementation, green-phase run,
  symlink-direction correction): ~35 min
- Phase 3 (self-review: ruff, py_compile, anti-pattern scan, doc-drift sweep,
  requirements cross-check): ~10 min
- Phase 4 (this report, IDE file opening, handoff): ~5 min
- Total: ~65 min. Estimated cost (Sonnet-class model, this size of diff/context): roughly
  $2-4 in API-equivalent tokens -- a rough order-of-magnitude estimate, not a metered
  figure.


## Update: coordinator review defect fix (post-initial-report)

The coordinator reviewed the diff (well-factored, suite green, `_resolve_stem_formats`
extraction praised) and probed it against the LIVE config on this machine, finding a real
defect plus a smaller latent-annotation issue.

### Defect: false-positive shadowing warning for a symlinked same-file case

**Root cause**: `_shadowed_rules_stems()` treated "stem present in both directories" as
sufficient to call it shadowed, without checking whether the two directory entries were
actually the SAME real file. On this machine,
`~/.config/toolguard/rules/gh.rules.toml` is a symlink to
`~/.toolguard/rules/gh.rules.toml` (the exact stopgap workaround that motivated this
ticket) -- so the stem existed in both directories but nothing was actually being
ignored; the warning was factually wrong and would have fired every session. The
coordinator correctly noted this is not just about that one stopgap symlink: anyone doing
`ln -s` to migrate one rules directory into the other (a natural compatibility move) would
get a false warning for every stem they own, training users to ignore exactly the warning
that matters.

**Fix**: `_shadowed_rules_stems()` now compares `Path.resolve()` of the XDG-side and
legacy-side representative paths and excludes the stem from the shadowed-map when they
resolve to the same real file. Verified via the coordinator's read-only probe script
(`check_symlink_shadow.py`) against the live config: `_shadowed_rules_stems()` now
returns `(none)` and `validation_issues()` reports nothing for the live `gh.rules.toml`
symlink, confirming the false positive is gone.

**New tests** (`test/unit/test_configuration.py`, TDD as before):
- White-box, no `Path.home()` involvement (direct temp dirs, matching the existing
  `_discover_rules_files` white-box style): `test_shadowed_rules_stems_reports_distinct_real_files`,
  `test_shadowed_rules_stems_excludes_stem_resolving_to_same_real_file`,
  `test_shadowed_rules_stems_stem_only_in_legacy_dir_not_reported`.
- End-to-end (`TestRulesDirectoryDiscovery`, `ConfigIsolationMixin`):
  `test_symlinked_same_file_across_dirs_is_not_reported_as_shadowed` -- reproduces the
  real bug shape (XDG entry is a symlink to the legacy real file), asserts exactly one
  `toolguard_hook_rules` layer is produced (the "loads exactly once" check the coordinator
  asked for -- `allow.count("gh *") == 1`, not a duplicate), and asserts no shadowing
  warning.
- Regression guard for the pre-existing genuinely-distinct-files case: rather than adding
  a near-duplicate test, extended the existing
  `test_same_stem_in_both_dirs_xdg_wins_and_shadow_warning_emitted` docstring to state
  explicitly that it guards against the new resolve()-based exclusion over-suppressing a
  genuine shadowing case (it already used two distinct real files with different content,
  no symlink -- re-ran it after the fix, still passes).

### Smaller item: `_shadowed_rules_stems` return-value truncation for N>2 dirs

Took the coordinator's mildly-preferred option: **narrowed the annotation and docstring**
(rather than generalizing to report all shadowed paths). `_shadowed_rules_stems` is now
typed `Tuple[Path, Path] -> Dict[str, Path]` (matching `_rules_dirs()`'s exact
`(xdg_dir, legacy_dir)` return shape) and unpacks positionally
(`xdg_dir, legacy_dir = rules_dirs`) rather than looping over an arbitrary-length tuple.
The docstring now states this is intentionally two-directory-only (YAGNI) and that adding
a third candidate directory would need this function revisited. `_merged_rules_by_stem`
and `_discover_rules_files_multi` were left generic (`Tuple[Path, ...]`) since they were
not flagged and their first-dir-wins loop is correct for any length.

### Re-confirmation (per coordinator's request)

- Full suite: `uv run python -m unittest discover -s test -t .` -> 1526 tests, OK (1522
  from the first round + 4 net new: 3 white-box `_shadowed_rules_stems` tests + 1
  end-to-end symlink test; the existing regression-guard test's docstring was edited in
  place, not counted as new).
- `uv run ruff check .` (repo-wide) -> All checks passed.
- `uv run ruff format` re-run on the touched `.py` files only -> no changes (already
  formatted).
- `uv run python -m py_compile` on all three touched files -> OK.
- Re-ran the coordinator's probe script
  (`/tmp/claude-1000/.../scratchpad/check_symlink_shadow.py`) against the live
  `~/.config/toolguard/rules/` + `~/.toolguard/rules/` -> confirmed `_shadowed_rules_stems()`
  returns `(none)` and `validation_issues()` prints nothing; the spurious warning is gone.
