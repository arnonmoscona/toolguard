---
title: 01-estimate
type: note
permalink: toolguard/too-45/reports/surprise/01-estimate
---

# Blind change estimate -- consolidate the four warning-suppression mechanisms

Estimated from the briefing only (layer map + file inventory + first docstring lines). No file under the repo was opened.

## 1. Predicted touch set

| path | change | confidence | reason |
|---|---|---|---|
| `toolguard/warning_store.py` (name uncertain: `notice_store` / `suppression_store` / `warning_ledger`) | added | high [R] | The consolidation needs one keyed store; a new module is the only way four call sites collapse to one. Foundation-layer, stdlib-only (`sqlite3` or a single keyed file under `~/.toolguard/`). |
| `toolguard/session_warnings.py` | modified (possibly deleted) | high [T] | Named in the ticket as instance four. Either it becomes the one store (rewritten in place) or it shrinks to a thin adapter / disappears. I lean rewritten-then-renamed, which is why I predict both this row and the added module. |
| `toolguard/hook.py` | modified | high [T] | Ticket names the module globals that "cannot work" as part of the defect; they get deleted and replaced by store calls. Also the only place `session_id` is on the payload. |
| `toolguard/session_start.py` | modified | high [R] | SessionStart is the natural home for both a second date-marker instance (config-sync / update notices are exactly "warn once per day") and for the reaping call the ticket says is required. |
| `toolguard/config_divergence.py` | modified | medium [R] | `docs/config-sync.md` is called out as documenting both frequencies; divergence warnings are the most likely thing that doc is describing, so one copy of the marker logic probably lives here. |
| `toolguard/update_check.py` | modified | medium [R] | 68 lines named "Update checker" is the classic shape of a "have I already checked today" date-marker -- a prime candidate for one of the three copies. |
| `toolguard/install_update.py` | modified | low-medium [R] | If the update-check marker is not in `update_check.py` it is here (549 lines, same TOO-16 lineage). One of these two, probably not both. |
| `toolguard/constants.py` | modified | medium [R] | Scope keys (`day` / `session`) and the store filename are values the code branches on; project convention forces them into named constants. |
| `toolguard/path_utils.py` | modified | medium [R] | "Low-level filesystem path helpers" is where a `~/.toolguard/<store>` resolver belongs rather than in the store module itself. |
| `toolguard/env_config.py` | modified | low-medium [R] | A store under `$HOME` almost always acquires an env override for tests/sandboxing; this module owns those. |
| `.pyscn.toml` | modified | high [R] | The layer map's own comment: "EVERY module must appear in exactly one layer. An unlisted module is silently unmapped." A new module mechanically requires an entry. |
| `test/unit/test_session_warnings.py` | modified | high [T] | Direct tests of the renamed/rewritten mechanism. |
| `test/unit/test_<new store>.py` | added | high [R] | New module with real concurrency/expiry semantics; the repo's coverage habits make a dedicated test module near-certain. Expect it to be large (400-800 lines by local norms). |
| `test/unit/test_hook.py` | modified | high [R] | Removing module globals changes hook behaviour under repeated invocation; 3187 lines of hook tests will encode the old shape somewhere. |
| `test/unit/test_session_start.py` | modified | medium-high [R] | Reaping and once-per-day emission both land here. |
| `test/unit/test_architecture.py` | modified | medium [R] | Layering invariants enumerate modules; a new one has to be placed. |
| `test/unit/_config_isolation.py` | modified | medium [R] | A new `$HOME`-relative state location must be redirected in tests or every test run writes into the developer's real `~/.toolguard`. This repo already has that reflex (`_real_log_dir_guard.py`). |
| `test/unit/test_update_check.py` | modified | low-medium [R] | Only if the update marker is one of the three copies. |
| `test/unit/test_config_divergence.py` | modified | low-medium [R] | Same conditional, for the config-sync copy. |
| `test/unit/test_takeover_mode.py` | modified | low [R] | `session_warnings` is explicitly "for takeover mode"; the behavioural assertions may live here rather than in the same-named test file. |
| `docs/config-sync.md` | modified | high [T] | Ticket names it as documenting both frequencies without saying which warning uses which -- the ambiguity has to be resolved in prose. |
| `docs/architecture.md` | modified | high [R] | New module + layer placement + the "one store" story. |
| `technical-notes.md` | modified | medium-high [R] | The project's stated home for design rationale; the marker-file-vs-sqlite3 decision and the scope-keyed design belong there, not in code comments. |
| `docs/agent-map.md` | modified | medium [R] | Summarizes every other doc with nothing keeping it in sync; CLAUDE.md flags it as the most likely silent staleness. |
| `docs/uninstall.md` | modified | low-medium [R] | A new persistent state file under `~/.toolguard` is a new thing to remove. |
| `docs/configuration.md` | modified | low [R] | Only if a knob (period, store path) is exposed. I expect no knob. |
| `toolguard/tools/self_integrity.py` | modified | low [R] | Guards `~/.toolguard` from deletion; may need to know about the new file, though the directory-level guard probably already covers it. |
| `README.md` | modified | low [R] | Behaviour statement about warning frequency, if any exists there. |

## 2. Concentration set

1. **The new store module** (`toolguard/warning_store.py` or whatever it ends up called). All the genuinely new logic: a scope-carrying key (`day:<date>` / `session:<id>` as one namespace, per the PO's "the key must carry its own scope"), an expiry timestamp, a reap, and cross-process safety. This is the file the whole ticket exists to create.
2. **`toolguard/session_warnings.py`** -- the before/after of the defect. Whether it is rewritten, thinned to an adapter, or deleted is the single biggest branch in the whole change, and it determines how many other files move.
3. **`toolguard/hook.py`** -- the module globals die here, and it is the only place holding `session_id`. Even under a per-day decision, this is where the "cannot work" code is deleted.
4. **`toolguard/session_start.py`** -- the reaping call site and, I believe, one of the copied markers.

## 3. Expected counts

| | modified | added | deleted |
|---|---|---|---|
| production | 7 | 1 | 0-1 |
| test | 6 | 1 | 0 |
| docs | 4 | 0 | 0 |
| config (`.pyscn.toml`, `pyproject.toml`) | 1 | 0 | 0 |

Total files touched: ~20 (range 14-28).

Total lines changed: **~10^3** (order of magnitude one thousand). Breakdown of that estimate: new store ~150-300, its tests ~400-800, call-site edits ~50-150 across 5-7 modules, existing test churn ~150-400, docs ~150-300.

## 4. Named uncertainties

**Where the three copies actually are, and by what mechanism I would find them.** This is the biggest hole. Nothing in the inventory says "date marker" -- the docstrings are one line and none of them mention suppression. I inferred `session_start.py`, `config_divergence.py`, and `update_check.py`/`install_update.py` from *purpose*, which is a guess about behaviour from a title. The mechanism that would settle it in ten seconds is a grep for `strftime("%Y-%m-%d")`, `%Y-%m-%d`, or `-warned-` across `toolguard/`. If the real copies are somewhere I did not model -- `install_provenance.py`, `error_log.py`, `log_writer.py`, `tools/installer.py`, or `toolguard/tools/decision_ledger.py` (which is literally a persistent ledger and could already be a fifth de-facto instance) -- then two or three of my medium rows are wrong and an equal number of misses appear. **The single most likely surprise in this ticket is that one of the "three copies" is in a module whose docstring gives no hint of warning behaviour.**

**Prose-only churn, which I have almost certainly under-predicted.** The previous run's largest miss category was files where only a docstring or comment moved. The mechanism here is specific and strong: `session_warnings` is a *misleading name that the ticket is fixing*, so every mention of it -- imports, docstrings that reference it, "warned once per day" phrasing, the `.toolguard-warned-YYYY-MM-DD` filename appearing as an example -- becomes stale simultaneously. That set is invisible to me because I cannot see any file's body. The places it most plausibly hides: `.claude/skills/toolguard-maintenance/SKILL.md` and `.claude/skills/toolguard-security-audit/SKILL.md` (613 lines, enumerates behaviours), `docs/takeover-mode.md` (session_warnings is explicitly takeover-scoped and I did not list this file -- I now think it is a real miss risk), `docs/agent-guides.md`, `llms.txt`, `AGENTS.md`, and any production module whose docstring cites the old module by name. A rename turns each of these into a one-line diff. **If the implementer renames, add 3-8 files of pure prose; if they rewrite in place under the old name, add close to zero.** I could not tell which, and it is the highest-leverage unknown after the copy locations.

**Test-to-module mapping is not inferable, and I was warned it is wrong here.** I predicted `test_session_warnings.py`, `test_hook.py`, `test_session_start.py` largely on naming, which is exactly the heuristic that cost the previous run 9 overshoots. The mechanism that breaks the naming assumption in this repo: behaviour is tested where the *feature* lives (`test_takeover_mode.py`, `test_logging_streams.py`, `test_hierarchical.py`), not where the *module* lives. An `incomingCalls` / `findReferences` on the suppression entry points is the only reliable way to get this right, and I have neither.

**The architecture-enforcement machinery is a mechanical amplifier I can see the edge of but not into.** Four artefacts police module membership: `.pyscn.toml`'s completeness rule, `tools/architecture_fitness.py` (4112 lines), `test/unit/test_architecture.py`, and `test/unit/test_static_analysis_coverage.py` ("guards that pyscn analyses the whole package"). Adding one module can trip any of them. I cannot tell whether the layer map enumerates modules by name (each addition = a required edit) or by glob (no edit). If by name, `.pyscn.toml` plus one or two of those tests move deterministically; if the fitness tool carries its own hardcoded inventory, it moves too and is a 4000-line file nobody expected to open for a suppression-store ticket.

**Test isolation against the real `~/.toolguard`.** The repo has `.claude/rules/test-config-isolation.md`, `_config_isolation.py`, `_real_log_dir_guard.py`, and a whole dedicated regression test (`test_zz_real_log_dir_guard.py`) -- evidence that writing into the developer's real home during tests has bitten before, more than once. Any new persistent store under `$HOME` re-opens that exact wound. The mechanism: tests run with the real `HOME` unless something patches it, and a store that materializes on first use will silently create `~/.toolguard/<something>` on the dev machine. Expect either an isolation edit or a new guard file; a *new* guard file would be entirely unpredicted from the ticket text.

**Whether `sqlite3` is actually chosen, and its second-order file effects.** The PO floated it without mandating it. If chosen: WAL/journal sidecar files appear next to the store (relevant to `self_integrity.py`, `docs/uninstall.md`, and any cleanup tooling), schema creation and migration become real concerns, and the test module grows a concurrency section. If a single JSON/TOML file with an `os.replace` swap is chosen instead, the store module is half the size and the ripple is much smaller. This alone moves my line estimate by a factor of ~2.

**Whether a config knob is added.** If suppression period or store location becomes configurable, `config.py` (2514), `config_types.py` (1122), `config_validation.py`, `docs/configuration.md` (1005), and `test_configuration.py` (3982) all enter the touch set and the ticket roughly doubles. The PO's "per-day is acceptable for now, simplicity wins" argues against it, so I predicted no knob -- but "the key must carry its own scope" could be read as a forward-compatibility requirement that someone chooses to express in config. This is my most consequential single bet.

**Whether suppression is on the decision path.** The ticket says `session_id` "is currently read by nothing on the decision path", which implies the fix may put it there. If warnings surface through `api.decide` / `permission_resolution.py`, then `test_resolve.py` (2855, an explicit anti-drift contract test), `test/verdict_corpus/fixture_loader.py` (1207), and the corpus fixtures come into scope -- an expensive, entirely invisible-from-here tail. I judged this unlikely (warnings look like a side channel, not a verdict input) and excluded it, but I am flagging it because the cost of being wrong is high and the corpus is new enough (TOO-45) to be under active churn.

**Coverage and quality gates as a forcing function.** `.claude/rules/testing.md` plus the project's phase-end coverage habit mean a new production module cannot land without tests, regardless of how small it is. That is why I predict an added test module with high confidence even though the ticket never mentions tests.