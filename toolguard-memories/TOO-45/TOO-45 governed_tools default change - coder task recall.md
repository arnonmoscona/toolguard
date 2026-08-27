---
title: TOO-45 governed_tools default change - coder task recall
type: note
permalink: toolguard/too-45/too-45-governed-tools-default-change-coder-task-recall
tags:
- task-memory
- TOO-45
---

## Task (verbatim intent)

Small, deliberate behaviour change on branch `too-45`, decided by Arnon.

**Change the default governed tools from `("Bash",)` to `Bash, Read, Write, Edit`.**

Default lives at `toolguard/config.py:949` (`Configuration.governed_tools()`), returns
`("Bash",)` at line 975 when no layer in the hierarchy configures `governed_tools`.
Arnon: "it actually is better that the default governed list would be {Bash, Read, Write,
Edit}. I think Bash only is a forgotten remnant."

Evidence already checked by Arnon: `docs/install.md:252` recommends exactly
`Bash, Read, Write, Edit`; `docs/takeover-mode.md:264` uses that set in its example. Project's
own advice was out of step with its default.

**Derive it from the registry.** `toolguard/tool_spec.py`'s `BUILTIN_TOOLS` (punch-list #10)
is exactly this set (Bash, Read, Write, Edit) -- use it instead of a fifth literal. This makes
real the wiring the #10 review warned about (was an accident of a misleading name, now an
explicit intended decision) -- **the `is_builtin` docstring must be updated**: currently says
NOT the governance default; after this change it IS.

## Golden verdict corpus impact

`test/verdict_corpus/api.decide()` does NOT consult `governed_tools()` at all (confirmed:
`toolguard/api.py` docstring "The governed-tools list is NOT checked here"). So the
in-process corpus (`cases.jsonl`/`goldens.jsonl`, ~5000 cases) is UNAFFECTED.

Only the end-to-end corpus (`e2e_cases.jsonl`/`e2e_goldens.jsonl`, ~30 cases, replays through
the real `toolguard.hook.main()` subprocess) actually enforces `governed_tools()`
(`hook.py:723`, `hook.py:1347`). 19 of 24 `configs/*.toml` fixtures do not set
`governed_tools` -- e2e cases against those fixtures using Read/Write/Edit targets may move
from "not governed -> allow" to actually being evaluated against rules/fallback.

**Every changed e2e golden case must be individually justified** -- not bulk-regenerated.
Confirm the new verdict is what governing that tool under that config *should* produce.
Report count + short characterisation. If a change can't be explained by this one behaviour
change, STOP and report.

## Also required

- Documentation: `docs/configuration.md`, `docs/install.md`, `docs/takeover-mode.md`,
  `README.md`, `AGENTS.md`, `llms.txt` -- anything stating/implying the default. A doc
  *recommending* Bash/Read/Write/Edit is now recommending the default -- may make prose
  redundant/confusing, read as a user would.
- Upgrade consequence stated plainly (release notes candidate): an existing project that never
  configured `governed_tools` and never wrote file-path rules will, after upgrading, have
  Read/Write/Edit evaluated against its rules and fall through to `no_match_fallback` --
  silent, warning, or deny depending on that setting.
- A test pinning the new default explicitly (new default narrowed silently in future should
  fail).

## Constraints

- Full suite green (baseline measured: 2731 tests, OK, before any change).
- `uv run python tools/architecture_fitness.py --layers` clean.
- `uv run ruff format .` and `uv run ruff check .`.
- Stdlib only. `unittest`, not pytest.
- Intent disclosure required before any authored Bash logic (heredocs, python -c, scratch
  scripts, authored shell loops/sed/awk) -- `# INTENT:`/`# TOUCHES:`/`# INLINE BECAUSE:` +
  `TG_INTENT=1` / `TG_ATTEST_READONLY=1`.
- Append to existing basic-memory report (do not overwrite). Do not commit -- Arnon does all
  git write ops.

## Existing tests that pin the OLD default (will need updating, not just adding new ones)

`test/unit/test_configuration.py` `TestGovernedAndTakeoverDelegation`:
- `test_governed_tools_default_when_unconfigured` (line ~1060): asserts `("Bash",)` with no
  layers at all.
- `test_governed_tools_tolerates_non_list_value` (line ~1083): asserts `("Bash",)` default
  when malformed value skipped.
- `test_governed_tools_ignores_native_layers` (line ~1093): asserts `("Bash",)` default when
  only a native layer sets governed_tools.

These three literally test "what does the default resolve to" -- since the ticket changes the
default itself, these need their asserted value updated to the new default tuple, plus
docstrings (Given/When/Then) updated to match. This is not test-weakening: the production
default is the literal thing under test and the ticket says to change it. Also check
`test/unit/test_configuration.py:3011-3039` (mentions governed_tools() in a broader hierarchy
test) and any other `("Bash",)` default-literal assertions project-wide before finishing.

## Plan

1. `toolguard/tool_spec.py`: fix `is_builtin` docstring/comment (currently says NOT governance
   default -- now IS, when unconfigured). Need an ORDERED tuple derived from `_REGISTRY`
   (not the unordered `BUILTIN_TOOLS` frozenset) for `governed_tools()`'s literal default, to
   keep tuple ordering deterministic/matching existing test expectations style
   (`Bash, Read, Write, Edit`). Decide: add `BUILTIN_TOOLS_ORDERED: tuple[str, ...]` next to
   `BUILTIN_TOOLS`, built the same way but preserving `_REGISTRY` order, OR just use
   `tuple(t.name for t in _REGISTRY if t.is_builtin)` inline at the config.py call site
   importing `_REGISTRY`... `_REGISTRY` is private (leading underscore) - must not import
   private. So add a public ordered constant in tool_spec.py.
2. `toolguard/config.py::governed_tools()`: import the new ordered constant, change fallback
   return + docstring (currently says "Defaults to ('Bash',)").
3. Update the three existing tests above (assert new default, update docstrings). Add a new
   explicit pinning test if not fully covered by the updated ones (task explicitly asks for a
   test pinning the new default -- likely satisfied by updating
   `test_governed_tools_default_when_unconfigured` itself, but consider whether a SEPARATE
   test naming it as "new default" reads better -- decide during implementation, avoid
   duplicate/redundant tests).
4. grep whole repo for `("Bash",)` / `['Bash']` / other literal defaults mentioning the old
   default in comments/docstrings (config.py has more references at lines ~957, ~975; check
   `permission_migration.py`, `tools/config_access.py`, `tools/takeover_audit.py` docstrings
   too).
5. Regenerate e2e goldens via `tools/corpus_build.py --generate`, diff, individually justify
   every changed e2e case. In-process goldens should NOT change (verify with
   `--verify` first, before regenerating, to see exactly what moves).
6. Documentation sweep per list above.
7. Release-notes-worthy upgrade note -- check if this project keeps a CHANGELOG /
   release-notes file; find and add entry.
8. Full test suite green, ruff format/check, architecture_fitness --layers.


## Status: implemented, verified, self-reviewed

Full details in `implementation/coder-latest-implementation-report` (appended section titled
"TOO-45 -- default governed tools: Bash-only -> Bash/Read/Write/Edit -- implementation
report"). Key outcomes:

- Golden verdict corpus: zero goldens changed (verified, not assumed -- see report for why).
- Full suite: 2733 tests, OK (was 2731).
- ruff format/check clean, architecture_fitness --layers clean.
- Found and flagged (not fixed, out of scope): 5 multi-file verdict-corpus fixtures'
  `.claude/toolguard_hook.toml` files are gitignored and never committed to git (`.gitignore:7`'s
  bare `.claude` pattern matches at any depth). Worth its own ticket.
- Did not create a release-notes file (premature mid-ticket for an unreleased version); put the
  upgrade-consequence note in `docs/configuration.md` instead and flagged it as
  release-notes-worthy for TOO-45's eventual wrap-up.
