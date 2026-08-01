---
title: TOO-19 Phase 1 increment 9 documentation report
type: note
permalink: toolguard/too-19/too-19-phase-1-increment-9-documentation-report
tags:
- task-memory
- TOO-19
---

## Summary

Increment 9, documentation-only, for TOO-19 Phase 1's now-shipped `additionalContext` rule
enrichment feature (increments 1-8, landed, 1949 tests green). No production code changed.
No git operations performed (per instructions).

## Files changed (7, all docs)

1. `docs/configuration.md`
   - Corrected the false "reserved for a future release" paragraph in
     `### Structured rule entries, and the single line rule` (was: "the two forms mean
     exactly the same thing... additional keys are reserved for a future release"). Kept the
     two true facts from the old paragraph (toolguard's own tooling emits the structured
     form; unrecognized key is a warning, otherwise ignored) and kept the entire single-line
     rule subsection + warning block byte-for-byte unchanged, as instructed.
   - Added a worked example: a realistic allow (`git push`) and a realistic deny
     (`rm -rf` via `[regex]`), each with `additionalContext`.
   - Added a new subsection `### additionalContext: injecting guidance alongside a decision`
     (anchor `#additionalcontext-injecting-guidance-alongside-a-decision`), covering: the
     toolguard-config-only restriction, string-only values (non-string -> error issue, rule
     still applies), the deciding-match-only rule, compound accumulation/dedup/500-word
     greedy-first-fit cap, the two ASK floors (Bash-only inline/heredoc floor vs. the
     all-tools config-parse-failure floor) both dropping context on a non-deny clamp, the
     "key omitted not null" JSON shape, the 40-word log preview, and `--eval`/sandbox preview
     support.
   - Added both new anchors to the `## Contents` list at the top.

2. `README.md` -- new `## Explaining decisions to Claude` section between the "Why
   Toolguard?" bullets and "## Documentation": one paragraph ("what it's for," leading with
   the deny use case) plus one worked deny example, then a link to the new
   `docs/configuration.md` subsection for full behaviour. Deliberately does not restate the
   compound/ASK-floor mechanics.

3. `docs/architecture.md` -- one sentence appended after the Hook Flow ASCII diagram's
   closing paragraph, noting `hookSpecificOutput.additionalContext` and linking to
   configuration.md. No new heading (kept this a body-text cross-link, not a new TOC entry,
   to avoid inflating the architecture doc for a docs-only increment).

4. `docs/security.md` -- two cross-links added to existing prose (no new headings):
   - In "Multi-line commands and the ASK-safe guarantee" -> the foreign-interpreter ASK
     floor bullet now notes it also drops `additionalContext`.
   - In "A broken config file also fails safe, not open" -> added a sentence noting the
     parse-failure floor also clears `additionalContext` (except on an already-deny
     decision, which the floor never touches).

5. `AGENTS.md` -- one new bullet in "Key facts an agent should not get wrong," describing
   `additionalContext` briefly and linking to the new configuration.md anchor.

6. `llms.txt` -- the "Configuration" bullet's description now mentions
   `` `additionalContext` rule enrichment `` alongside the other reference-doc contents.

7. `docs/agent-map.md`:
   - Master TOC: added `README.md`'s new `## Explaining decisions to Claude` heading and
     `docs/configuration.md`'s new `### additionalContext: ...` heading, in their correct
     document positions.
   - Added a new Q&A entry under "Rules & patterns": "Can a rule explain itself to Claude...
     ?" pointing at the new configuration.md anchor.

## New anchors added (all verified via `tools/check_doc_links.py`)

- `README.md#explaining-decisions-to-claude`
- `docs/configuration.md#additionalcontext-injecting-guidance-alongside-a-decision`

Every internal link added or referenced (including the two above and the existing
`configuration.md#a-broken-config-file-also-fails-safe-not-open` /
`permission-patterns.md#inline-interpreter-code--c---e---r` cross-links reused from
elsewhere) was checked by the mechanical GitHub-slug checker; the script exits 0.

## Verification performed

- `uv run python tools/check_doc_links.py` -> "All internal documentation links resolve."
  (exit 0), run twice (before and after the final edit pass).
- `TMPH=$(mktemp -d); TMPX=$(mktemp -d); HOME="$TMPH" XDG_CONFIG_HOME="$TMPX" uv run python
  -m unittest discover -s test -t .; rm -rf "$TMPH" "$TMPX"` -> `Ran 1949 tests ... OK`,
  exit 0. Unchanged from the pre-task baseline, as expected for a docs-only change.
- Sanity-parsed the two new TOML snippets (README.md's deny example and
  configuration.md's allow+deny example) through stdlib `tomllib` in a throwaway script to
  confirm the `\\s+-rf` regex escaping in the doc examples is valid TOML and decodes to the
  intended pattern -- matches the escaping style already used elsewhere in
  `docs/configuration.md` (e.g. `Bash([regex]rm\\s+-rf\\s+/)` in the existing annotated
  template).
- `git diff --stat` confirms only the 7 doc files above changed; `toolguard/*.py` and
  `test/*.py` are untouched by this session (the pre-existing uncommitted diffs in
  `toolguard/rule_entry.py`, `toolguard/compound.py`, etc. visible in `git status` predate
  this task -- they are increments 1-8's landed-but-uncommitted work, not touched here).

## Behavioural claims verified against code (all matched the ticket's summary -- no
discrepancy found)

Read in full and cross-checked every claim before writing docs:
- `toolguard/rule_entry.py`: `ADDITIONAL_CONTEXT_KEY`, `KNOWN_ENRICHMENT_KEYS`,
  `RuleEntry.additional_context` (non-string -> None; blank/whitespace -> None),
  `normalize_entry` (native-layer dict rejection with a warning; unknown key -> warning;
  `_additional_context_issues` -> error-level Issue for a non-string value, entry still
  returned).
- `toolguard/compound.py`: `_accumulate_contexts` (dedup by exact text equality, greedy
  first-fit 500-word cap via `_MAX_CONTEXT_WORDS`, whole-paragraph drop, blank-line-joined),
  `_combine_strictest` (deny/ask -> single deciding leaf's context passes through unchanged;
  allow -> every allowed leaf accumulated, including the single-leaf case), `_resolve_leaf`
  (ASK-floor branch: explicit deny keeps context, clamp-to-ask drops it via `None`).
- `toolguard/hook.py`: `create_hook_output` -- `additionalContext` key present in
  `hookSpecificOutput` ONLY when the value is truthy (non-empty string), omitted otherwise
  (not set to `null`).
- `toolguard/resolve.py` / `toolguard/config.py`: `resolve_permission_detailed` ->
  `_apply_parse_failure_ask_floor` (clamps allow/ask -> ask when any config file failed to
  parse, deny is left alone, and the returned `ResolvedDecision` has `provenance`/
  `override`/`additional_context` all cleared to `None`); the deciding-rule lookup itself is
  `Configuration._entry_for_pattern` inside `_resolve_permission_detailed_unclamped`,
  feeding `winning_entry.additional_context`.
- `toolguard/log_writer.py`: `_LOG_CONTEXT_PREVIEW_WORDS = 40`,
  `_preview_additional_context` -- confirms the "40-word preview plus full word count" claim
  exactly.
- `toolguard/tools/decision.py` + `toolguard/testing/sandbox.py`: confirmed `--eval` (via
  `_resolve_event` -> `create_hook_output`) and the sandbox CLI/`.evaluate()` both surface
  `additional_context`.

No discrepancy between the ticket's summary and the code was found anywhere in this list.

## Judged out of scope

- **`technical-notes.md`**: left unchanged. It has no existing section describing
  `RuleEntry`/structured-entry design (grepped for "enrichment", "structured entr",
  "RuleEntry" -- nothing), and the feature's developer-facing design rationale already lives
  in extensive docstrings across `rule_entry.py`, `compound.py`, `resolve.py`, `hook.py`,
  and `config.py` (all read and verified above), which is the project's established pattern
  for "developer, not end-user" documentation on this ticket. Adding a new full
  design-narrative section to a 900-line file for a docs-only increment felt like scope
  creep beyond "sweep for stale/should-cross-link" -- there was nothing stale to fix and no
  existing heading to extend with a one-liner the way architecture.md/security.md had. Flag
  this for a human call: if a technical-notes.md summary is wanted for this feature, it's a
  small, separate addition.
- Did not touch `docs/permission-patterns.md`, `docs/quickstart.md`, `docs/agent-guides.md`,
  `docs/skills.md`, `docs/takeover-mode.md`, `docs/auto-mode.md`, `docs/config-sync.md`,
  `docs/install.md`, `docs/uninstall.md`, or the two `skills/*/SKILL.md` files -- none
  mention structured entries, enrichment keys, or make any claim this feature contradicts
  (grepped for "additionalContext", "enrichment", "structured" across the doc tree; only the
  files listed above had relevant hits).

## Self-review

- Ran `uv run ruff format .` / `uv run ruff check .` -- not applicable; no `.py` files were
  touched this session.
- Style check: plain ASCII throughout; all new headings use single hyphens (no `--`) so
  their GitHub slugs stay simple and predictable -- verified mechanically by
  `check_doc_links.py`, which implements GitHub's actual slug algorithm.
- Every new prose paragraph states the consequence, not just the rule (e.g. "the floor
  decided the verdict, not the rule match, so injecting that rule's guidance would
  misrepresent why the prompt appeared" rather than just "context is dropped").

## Elapsed time / cost estimate

- Phase 1 (requirements capture, code verification): ~20 min. Rough cost: mid five-figure
  token count for reading `rule_entry.py`, `compound.py`, `resolve.py`, `hook.py`,
  `config.py`, `permissions.py`, `log_writer.py`, `tools/decision.py`, `testing/sandbox.py`
  in full or in large part -- call it ~$0.30-0.50 at Sonnet pricing.
- Phase 2 (writing all 7 doc edits): ~15 min, ~$0.20-0.30.
- Phase 3 (verification: doc-link checker x2, full test suite, TOML sanity check, diff
  review): ~5 min, ~$0.05-0.10.
- Phase 4 (this report, IDE opens): ~5 min, ~$0.05-0.10.
- Total: ~45 min wall clock, rough total cost estimate ~$0.60-1.00.
