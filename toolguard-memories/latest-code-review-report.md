---
title: latest-code-review-report
type: note
permalink: latest-code-review-report
tags:
- code-review
- TOO-19
---

# Code Review Report -- 2026-07-31

**Scope:** `changed` (`git diff HEAD`), ticket TOO-19 -- Phase 1 `additionalContext`
injection plus the `undecidable_fallback` setting and the test log-dir isolation fix.
**Reviewer:** code-reviewer subagent
**Elapsed:** ~32 minutes | **Files reviewed:** 11 source + 18 test + 8 docs (37)
**Est. cost:** ~$4-5 (Opus, ~250k input / ~15k output tokens)
**Issues:** 1 Critical, 3 Major, 8 Minor, 5 Suggestions

Source files: `toolguard/compound.py`, `config.py`, `config_types.py`, `hook.py`,
`log_writer.py`, `resolve.py`, `rule_entry.py`, `testing/sandbox.py`, `tools/decision.py`,
`tools/takeover_audit.py`, `tools/check_doc_links.py`.

**Verification run:** full suite `Ran 2012 tests ... OK`; `uv run ruff check .` clean;
`uv run ruff format --check .` clean; `uvx pyscn analyze --skip-deps toolguard` (grade B,
report `.pyscn/reports/analyze_20260731_184113.json`).

## Summary

This is high-quality, unusually well-documented work. The threading of `additional_context`
through the resolution stack is disciplined -- backwards-compatible `__iter__` contracts, a
single lookup helper per pattern pool, and the parse-failure floor correctly extracted so the
compound boundary and the per-leaf path cannot drift. Test coverage of the new pure helpers
(`_accumulate_contexts`, `_apply_undecidable_floor`, `_preview_additional_context`) is
thorough, and the `_real_log_dir_guard` mechanism is a genuinely good answer to a checklist
that failed. The findings below are one packaging blocker, one undocumented security surface,
and a real inconsistency in where the 500-word budget is enforced; the rest are minor.

---

## Critical

### C1. Two new test files are untracked, and the tracked `__init__.py` imports one of them

`test/unit/__init__.py` (tracked, modified) executes at package-import time:

```python
from test.unit._real_log_dir_guard import REAL_LOGS_DIR, get_leak_events, install
```

`git status` shows both `test/unit/_real_log_dir_guard.py` and
`test/unit/test_zz_real_log_dir_guard.py` as `??` (untracked). Committing the current tracked
set makes **the entire unit suite fail to import** on any other checkout or on CI -- it passes
here only because the files exist in the working tree. `.gitignore` was also edited in this
change set (added `__pycache__/`), so it is worth confirming nothing else is masked.

**Fix**: `git add test/unit/_real_log_dir_guard.py test/unit/test_zz_real_log_dir_guard.py`
before committing.

---

## Major

### M1. `additionalContext` is an undocumented model-context injection channel from project-level config

`docs/configuration.md` documents the toolguard-config-only restriction, but neither it nor
`docs/security.md` addresses the new threat: a **project-level** `.claude/toolguard_hook.toml`
is discovered from the project directory, so a cloned repository the user did not author can
carry a rule whose `additionalContext` is arbitrary free text injected straight into Claude's
context on the next matching tool call. That is qualitatively different from what a hostile
project config could do before: previously it could grant or withhold permissions (bounded by
`hard_deny` and more-specific-wins), now it can *steer the agent generally*, through a channel
the model is designed to treat as system-provided guidance.

`docs/security.md:26` only says "There is no protection against mistakes or malicious
suggestions", which predates this feature and does not cover it.

**Recommended fix**, in increasing order of cost:

1. Add a `docs/security.md` subsection naming the surface explicitly ("a rule's
   `additionalContext` from a project-level config is text you may not have written").
2. Prefix injected text with its provenance so it is not indistinguishable from toolguard's
   own voice, e.g. `Rule guidance from <config path>:`. Provenance is already resolved
   alongside the entry in `Configuration.decide_at_level` (`config.py:~1645`), so this is
   cheap.
3. Add a `toolguard-audit` finding enumerating rules carrying `additionalContext` with
   project-level provenance, mirroring the new `loose-undecidable-fallback` invariant.

### M2. The 500-word budget guards only one of four injection paths, and silently discards a lone over-budget entry

`compound._accumulate_contexts` is the only place the budget is applied, and
`_combine_strictest` calls it only on the **all-allow** branch:

- `compound.py:~385` -- deny branch returns `denied[0]`'s context **uncapped**.
- `compound.py:~388` -- ask branch returns `asked[0]`'s context **uncapped**.
- `resolve.py:~533` -- `FileResolution.additional_context` (Read/Write/Edit) is taken straight
  from `RuleEntry.additional_context`, **uncapped**.
- `resolve.py:~615` -- `_hard_deny_additional_context` on the Bash hard-deny path, **uncapped**.

Two concrete consequences:

- A `Read` rule with a 5,000-word `additionalContext` is injected in full on every matching
  call, with only a 40-word copy in the log to show for it.
- `_accumulate_contexts` drops a paragraph **whole** when it does not fit, and applies that to
  the *first* paragraph too: a single 501-word entry gives `total_words + words > max_words`
  on the first iteration, `kept` stays empty, and the function returns `None`. So the same
  text that injects in full on a `Read` rule injects **nothing at all** on a Bash allow rule --
  no warning, no log line, and no test covering it (`test_compound.py:2226` only tests an
  in-budget block plus an over-budget *second* paragraph).

**Recommended fix**: enforce the budget once at the injection boundary rather than inside the
compound combinator -- `hook.create_hook_output` or `tools/decision.decide` sees every path.
Leave `_accumulate_contexts` responsible for dedup and joining only. Separately, a single
paragraph that alone exceeds the budget should not vanish silently: either keep it (it is the
only content) or emit a warning via `error_log.log_warning` so the rule author finds out.

### M3. The discovery-JSONL size guard degrades into exactly the noise it was added to remove

`log_writer._last_discovery_levels_for_root` returns `None` when the file exceeds
`_DISCOVERY_JSONL_MAX_READ_BYTES` (1 MB). `log_discovery` reads `None` as "no prior record for
this project root" and therefore **writes** -- both a JSONL record and a markdown discovery
line. Once the file crosses 1 MB, every hook invocation appends to it, growing it faster and
re-introducing the per-invocation discovery spam this change exists to eliminate. The failure
mode is self-accelerating and silent.

The docstring calls this "one extra, harmless log write", which is true for a transient read
failure but not for the size cap, which is a permanent condition once reached.

**Recommended fix**: on exceeding the cap, rotate or truncate the file (keep the last N
records) rather than degrading to "no prior entry" -- or read only the tail via `seek()` from
the end, which removes the cap's purpose entirely.

---

## Minor

### m1. An explicit `ask` rule on an ASK-floor leaf is misattributed to the floor and loses its context

`compound.py::_resolve_leaf`, ask-floor branch: when `resolve_one` returns
`("ask", reason, context)` from a real `ask` rule and `undecidable_fallback` is the default
`"ask"`, `_apply_undecidable_floor` returns `"ask"` unchanged -- the floor decided nothing --
yet the code replaces the reason with `"ASK floor applied (inline/heredoc foreign code): ..."`
and drops the context. The prompt then names a cause that is not the real one, and the rule
author's explanation is discarded.

**Fix**: rewrite the reason and drop the context only when the floor actually raised the
verdict (`floored != decision`); otherwise pass `reason` and `additional_context` through. The
verbatim-wording goal is unaffected -- the allow-to-ask case that existing tests exercise
still takes the rewrite path.

### m2. `resolved_undecidable_fallback` duplicates `resolved_no_match_fallback`'s layer scan verbatim

`config.py:~1755` and `config.py:~1830` contain the same "walk non-native layers, first
`str`-valued top-level key wins" loop. The two settings differ only in key name, legacy alias,
and valid-value set.

**Fix**: extract `_first_toplevel_str_setting(key: str) -> Optional[str]` and have both call
it; `resolved_no_match_fallback` keeps its `[takeover_mode]` alias and `warn_deny`
normalization layered on top.

### m3. Hard-deny pattern recovery by reason-string parsing is now load-bearing for a second consumer

`resolve.py:~600` recovers the matched hard-deny pattern by stripping the literal prefix
`"Command matches hard_deny pattern: "` and suffix `" (cannot be overridden)"` off
`check_hard_deny`'s reason string. That round-trip was already fragile for
`SubMatch.matched_rule`; `_hard_deny_additional_context` now depends on it too, so a wording
change in `check_hard_deny` silently disables enrichment on all hard denies *in addition to*
breaking the logged rule name.

**Fix**: have `check_hard_deny` return the matched pattern as a third element rather than
encoding it in prose.

### m4. `_entry_for_pattern` can attribute a less-specific layer's entry on list drift

`config.py::_entry_for_pattern` puts the `len(entries) == len(candidates)` test *inside* the
per-layer condition. When a layer's parallel lists have drifted, the loop does not stop -- it
moves to the next (less specific) layer, and if that layer also contains the same pattern
string it returns *that* layer's entry, attributing enrichment to a rule that did not win.
`_provenance_for_pattern` is not exposed to this because it has no second list.

**Fix**: `return None` as soon as the pattern is found in a layer whose lists are misaligned.

### m5. Complexity regression on two functions pyscn already flags critical

pyscn (2026-07-31) on the changed files:

| function | cyclomatic | cognitive | nesting |
|---|---|---|---|
| `hook.main` | 28 | 55 | 6 |
| `config.Configuration.validation_issues` | 27 | 62 | 5 |
| `log_writer.log_command` | 24 | 59 | 4 |
| `rule_entry.merge_entries` | 18 | 42 | 4 |
| `compound._combine_strictest` | 14 | 14 | 4 |

All are well past the project's <10 target. `main` and `log_command` were each made worse by
this change (a new parameter plus two new conditional writes), and `log_command` now takes
**10 parameters**. pyscn also reports a critical Type-2 clone cluster (10 fragments, 70%
similarity) at `rule_entry.py:698` (`merge_entries`).

**Suggested refactorings** (brief): split `log_command`'s two output formats into
`_write_jsonl_entry(...)` / `_write_markdown_entry(...)` and pass a small `LogRecord`
dataclass instead of 10 positional-or-keyword parameters; extract `main`'s file-path and Bash
decision blocks into `_handle_file_path_event` / `_handle_bash_event`, which would also remove
the duplicated three-way allow/ask/deny logging ladder those blocks share. Follow-up work, not
required for this ticket.

### m6. `allow_with_warning` does not actually write a warning anywhere

Both `no_match_fallback` and the new `undecidable_fallback` implement `allow_with_warning` as
the word "warning" inside a reason string; nothing reaches `error_log.log_warning`'s warning
stream. `docs/configuration.md` says "allow the command but log a warning", which a reader will
take to mean the warnings log. The new code matches the existing precedent, so this is not a
regression -- but the claim is now made twice.

**Fix**: either route these through `log_warning`, or soften the docs to "allow the command
and say so in the resolution log".

### m7. `log_discovery` and the new JSONL ignore `logging_enabled`

`hook.main` calls `log_discovery` whenever `log_dir` resolves, without consulting
`env_config["logging_enabled"]`. Pre-existing for the markdown line; this change adds a second,
persistent file (`toolguard-discovery.jsonl`) created under the same unconditional path, so a
user who explicitly disabled logging now gets a new file written.

### m8. The accumulated context is stamped on every sub-command log entry

`hook._log_allowed_command` passes the same `additional_context` to `log_command` for each
sub-command of a compound, so a 6-part compound repeats the (40-word-capped) preview 6 times.
The docstring acknowledges this as deliberate; consider logging it once, or on a single
compound-level entry.

---

## Suggestions / notes

- `compound._truncate_for_display` (character budget) and
  `log_writer._preview_additional_context` (word budget) are the only two truncation helpers
  in the package and are genuinely different in unit and purpose -- no consolidation needed.
  Noted so a future reader does not "unify" them.
- `testing/sandbox.py:~583`'s `except OSError, ValueError:` and `_real_log_dir_guard.py:134`'s
  `except TypeError, ValueError, OSError:` are valid PEP 758 syntax under this project's
  `requires-python = ">=3.14"`. ruff produced them, they are real tuples -- do not "fix" them.
- The `os._exit(1)` atexit backstop in `test/unit/__init__.py` is well-reasoned, and the
  finding that `sys.exit()` does not change the exit code from an atexit callback is correct.
  It does pre-empt later atexit handlers; `tools/coverage_stdlib.py` writes its results before
  interpreter shutdown, so coverage runs are unaffected.
- The deliberate separation of `_DECISION_STRICTNESS` from `_combine_strictest`'s own ordering
  is defensible as documented, though one shared `_STRICTNESS` constant with two distinct
  *functions* over it would carry the same argument at lower cost. Not worth changing now.
- Docs are accurate on every claim I spot-checked (floor table, dedup, key-omitted-not-`null`,
  native-layer rejection, absence of a `warn_deny` alias). The one overstatement is the
  500-word cap's reach -- see M2.

## code-review-graph trial note

Phase: **feature work / test hardening** (not refactoring). One non-trivial use:
`semantic_search_nodes` for "is there already a truncation helper this duplicates". Refresh
(`embed` + `postprocess`) was run first and succeeded. Verdict: **mild win** -- it returned
both truncation helpers plus `_collapse_whitespace` ranked above unrelated renderers, which a
name-grep would have missed (`_preview_additional_context` and `_truncate_for_display` share
no substring). `LSP` could not have answered this; it is a concept query, not a symbol query.
Everything else in this review (callers of `check_compound_permission` /
`resolve_compound_permission`, index-alignment invariants, tracked-vs-untracked files) was
answered faster by `grep`, `git`, and reading, and I did not reach for the graph for them.
