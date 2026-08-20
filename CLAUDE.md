# CLAUDE.md

General directives are in `~/.claude/CLAUDE.md`, loaded before this file.

## Project overview

toolguard is primarily a Claude Code hook that manages permissions better than the built-in
system. It governs `Bash`, `Read`, `Write`, `Edit`, with most attention on `Bash`. It accepts
native Claude permission syntax as a drop-in replacement, and extends it with regex and glob
command matching (glob is native for Read/Write/Edit but not for Bash). Full behaviour is in
[README.md](README.md).

Ticket prefix: `TOO-`. basic-memory project: `toolguard`.

## Two architectural constraints

**Runtime is standard-library only.** Running toolguard must require nothing but the Python
standard library. Add a runtime dependency only when it is genuinely unavoidable.

**All bash parsing goes through the PEG grammar -- never hand-rolled Python.** Compound
commands must be split into parts and matched per-part, or the rules become brittle. Regex
and hand-written tokenizers are error-prone and near-impossible to debug, so
`toolguard/parser/bash_parser.peg` is the single source of truth. `canopy` (dev-only,
installed on the dev machine) generates the base parser from it; `command_extractor.py`
consumes that. The generated code depends only on the stdlib, so this adds no runtime
dependency. The grammar is deliberately not full bash -- only the compound-command patterns
Claude Code actually emits.

See `.claude/rules/bash-grammar.md` for the mandatory two-phase change procedure. That rule
exists because grammar changes have repeatedly been implemented as Python instead, even when
the instruction to use the grammar was explicit.

## Testing

`unittest`, not pytest -- pytest is not installed.

```bash
uv run python -m unittest discover -s test -t .
```

Conventions and coverage tooling: `.claude/rules/testing.md`.

## Running toolguard's own skills against this repo: pass `--dev`

`toolguard-maintenance` and `toolguard-security-audit` default to the installed console
scripts (`toolguard-maintain`, `toolguard-audit`), which is right for every *other* project
and wrong here -- in this repo we want the working branch, not the installed release. Pass
**`--dev`** to switch them to the in-repo module form. The skills also auto-detect the source
repo, but prefer the explicit flag.

Never bake the `uv run python -m ...` form into a self-permission rule or into a skill body;
it lives only in each skill's "Development mode" section. This has regressed once after a
compaction.

## Announce intent before code the hook cannot see

**The general rule now lives in `~/.claude/CLAUDE.md` ("Disclose code you wrote before you run
it") and applies in every project and to every subagent.** This section is toolguard's own
layer on top: the env-var markers, the measured evidence for the wording, and the enforcement
status. When the two disagree, the global one states the principle and this one states the
mechanics -- don't let them drift into two different rules.

**The test is authorship, not length.** Every Bash command you issue is one of two kinds:

- **A tool invocation**: you are running a program that already existed -- `grep`, `ls`,
  `git diff`, `ruff`, `unittest`, a committed project script like `tools/coverage_stdlib.py`.
  You chose flags and paths; you did not write the logic. **No disclosure.**
- **Program delivery**: the command *carries a program you just authored*, or points at one. A
  heredoc into an interpreter, a `-c`/`-e` argument, or the path to a script you wrote for this
  task. The flags are not the point -- the code is. **Disclose.**

The word "one-liner" is banned from this decision. `python -c` followed by forty lines of code is
a single shell command and is not a one-liner in any sense that matters here; the shell syntax is
a delivery mechanism for a program you wrote. Likewise `uv run python fix.py` is short, but its
shortness is the problem -- the program is in the file, and only the filename reaches the reviewer.

Ask: **did I write the logic that is about to execute?** If yes, disclose it, however short the
command looks.

Concretely, that question comes out "yes" for any of these, **anywhere in the command text**,
including after a `cd`, a `&&`, a pipe, or inside a subshell:

1. A heredoc into an interpreter -- `<<'PY'`, `<<EOF`, `<<-` into `python`/`node`/`sh`/`bash`.
2. Inline code in an argument -- `python -c`, `uv run python -c`, `node -e`, `perl -e`,
   `ruby -e`, `bash -c`, `sh -c`, `jq -f`.
3. **A path to a script you or a subagent wrote for this task** -- `uv run python tmp/x.py`,
   `python scratchpad/probe.py`, `bash /tmp/fix.sh`, `node scratch.js`.
4. **Shell you composed rather than invoked** -- `sed -e`/`-i` substitution programs, `awk`
   programs, `for`/`while` loops, `xargs` with an authored command, multi-stage `$(...)`
   pipelines whose logic is the point. The interpreter is `sh` and the program is the command
   line. **This is the case that gets missed**, because shell does not *look* like a program.

No exceptions for short, for read-only, for "I just showed the code", or for "a rule will
reject it anyway". The exemption covers only what is *not* on that list: `grep`, `ls`,
`git diff`, `uv run ruff check .`, `uv run python -m unittest ...`, and **committed** project
scripts (`tools/coverage_stdlib.py`, `toolguard/...`, `~/bin/...`,
`~/projects/youtrack_api/...`) -- files that were reviewed once and are not being written
right now.

**Measured 2026-08-09**: of 17 qualifying commands in one day, 7 were disclosed and 10 were
not, and every miss on the main agent's side was case 4 or an undisclosed scratch script. The
misses were not random -- everything that felt like *a program in a file* got a block, and
everything that felt like *shell* got nothing. That is the file-versus-shell test, which is not
the test. The test is authorship.

**Disclosure is not only decision support.** It also feeds after-the-fact analysis of what the
agent actually did, which is why it is required even when the command will be blocked, even
when it fails, and even when nobody is at the keyboard. A rejected command with a disclosure is
a usable record; a rejected command without one is a bare path.

**This applies to subagents exactly as it applies to the main agent** -- `feature-coder`,
`code-reviewer`, and anything else with a Bash tool. A subagent's commands land in the same
`logs/toolguard-*.md` and, because subagent identification is currently broken, are attributed
to `main`. An agent that skips disclosure therefore corrupts the main agent's record too.

This wording is not a guess. The previous version said "don't announce ordinary one-liners whose
full effect is visible in the command text", which a short `python -c` satisfies as well as `grep`
does -- so the carve-out ate the rule. Five candidate rewrites were scored against 77 real
commands drawn from the logs; the authorship framing above was the only one to clear 95% (98.7%
on Sonnet, vs 85.7% for the "one-liner" text, with its single error a false positive). Notably it
beat a purely mechanical version of the same trigger list (90.9%) -- naming the underlying
question generalizes where enumerating syntax does not, which is why the framing leads and the
list is subordinate to it. Full results: basic-memory note *Intent-disclosure phrasing experiment
-- winning wording and results* (`TOO-19`).

**Case 3 is the one that actually gets missed, and it is the one that matters most.** Measured over
`logs/toolguard-2026-07-29.md` and `-07-30.md`: 34 commands qualified, 20 were undisclosed, and
**every single scratch-script run was undisclosed (5/5)**. One of them, `uv run python
fix_agents.py --apply`, rewrote 15 files under `~/.claude/` -- outside the project -- and logged as
`EXECUTED`, not `ASK`, because `uv run python *` matches an allow rule. Nothing prompted, nothing
was recorded but a filename, and the disclosure that was the only remaining signal was absent.

The mechanism is specific and worth naming so you can catch it: **you had just written the file in
the same turn.** The `Write` is right there in the transcript, so running it feels already
explained. It is not -- the log gets a bare path, and the permission prompt gets a bare path.
So: **`Write`/`Edit` of a script, followed by running it, is a disclosure trigger by itself.**
If a script is worth writing rather than inlining, its `--apply` run is worth one comment block.

**Judge each command on its own.** The misses cluster in runs -- once one undisclosed heredoc goes
out, the next four inherit it. A batch of similar commands is a batch of separate decisions.

Announce as a Bash comment on the lines immediately before the invocation, so it travels with
the command into all three places that matter -- the permission prompt where Arnon decides,
the transcript, and `logs/toolguard-*.md`:

```bash
# INTENT: <what the code does, in plain language -- not a restatement of the code>
# TOUCHES: reads <paths>; writes <paths>   (say "writes nothing" when it writes nothing)
# INLINE BECAUSE: <why this isn't a file you could have been asked to run>
uv run python - <<'PY'
...
PY
```

For case 3 the third field doesn't apply -- it *is* a file -- so use `NOT INLINE BECAUSE` and say
why the code deserved a file. Never drop the block just because the third line doesn't fit; that
friction is part of why this case gets skipped:

```bash
# INTENT: rewrite the model: field in the two code-reviewer variants to match the opus definition
# TOUCHES: reads ~/.claude/agents/*.md; WRITES ~/.claude/agents/code-reviewer-{fable,sonnet}.md
# NOT INLINE BECAUSE: multi-file rewrite with a --apply dry-run gate; too long to read inline
uv run python scratchpad/fix_agents.py --apply
```

Note what that `TOUCHES` line does that nothing else in the pipeline does: it puts
"writes 15 files under `~/.claude/`" in front of Arnon *before* the command runs. The rule that
allows it sees only `uv run python *`. Where a command writes outside the project, put the write
in capitals as above.

Prose in the terminal reaches only the transcript, so use the comment form even when you add
prose as well. A leading comment does not affect rule matching -- the PEG parser discards it and
matches the real leaf command.

### Always add the machine-checkable marker too

The comment block is what Arnon reads, but **a comment can never be matched by a permission
rule** -- the PEG parser strips comments before matching (verified via
`toolguard.testing.sandbox`, 2026-07-29: a comment-only marker behaved identically to no marker
at all). So whenever the disclosure applies, also add an **env-var prefix**, which is inside the
leaf command and therefore visible:

| Prefix | Meaning |
|---|---|
| `TG_INTENT=1` | a disclosure block precedes this command |
| `TG_ATTEST_READONLY=1` | same, **plus** every leaf here is read-only (implies `TG_INTENT`) |

```bash
# INTENT: count call sites of resolve_project_root across the package
# TOUCHES: reads toolguard/**/*.py; writes nothing
# INLINE BECAUSE: needs import-alias resolution, not a grep
TG_ATTEST_READONLY=1 uv run python tmp/count_calls.py
```

**No rule enforces any of this today, and the previous wording here claimed otherwise.** It said
undisclosed inline code was "rejected by rule" and pointed at
`intent-disclosure-rules.example.toml`. That file is not in this repo, and nothing in
`.claude/`, `~/.claude/*.json` or `~/.toolguard/` matches `TG_INTENT` or `TG_ATTEST_READONLY`.
The markers are written and nothing reads them. The design work is in
`tmp/intent-disclosure-enforcement.md`, still marked "nothing here is adopted".

So the only thing standing between this rule and a silent miss is compliance -- which is exactly
the failure mode the "Encoding rules as guidance vs. enforcing them" section of the global
CLAUDE.md predicts, and it has now been measured happening. Until the rules exist, treat every
qualifying command as one you will be audited on, because the log is the audit.

Use `TG_ATTEST_READONLY=1` only when *every* leaf is read-only. Do **not** attest a compound
containing a write, redirect, delete, or install -- not even an incidental one. If part of the
work writes, split it: attest the read-only part, let the writing part take a normal decision.
This is an attestation you make on your own authority, and a false one is worse than none,
because the rules trust it.

**Known limitation**: a heredoc still hits the ASK floor for inline/heredoc foreign code even
when attested -- that floor overrides allow rules by design. Attestation currently buys silence
for scratch-script runs and ordinary leaf commands, not heredocs. Mark heredocs anyway: it costs
nothing, it records the claim, and it keeps them out of the deny rule.

This is not a request for permission and doesn't replace one. Arnon reads these when deciding
where to keep or remove friction, so specific beats short. If the honest answer to "why
inline" is "no good reason", write it to a file and run that instead.

## code-review-graph

Installed here. Generic guidance: `~/.claude/reference/search.md` and
`~/.claude/reference/code-review-graph.md`. This repo's own deviations:

* **"Which tests cover this function?" is an `LSP` question now, not a graph one.** Pyright is
  configured for this repo (2026-07-31): `incomingCalls` names each calling function, resolving
  class-based `unittest.TestCase` methods individually. The graph's `tests_for` returns false
  zeros here for exactly that reason -- its `TESTED_BY` heuristic misses them. The old
  workaround (`query_graph pattern="callers_of"` filtered to `is_test:true`) still works if you
  need it, but prefer the LSP.
* **Semantic search is true vector mode.** Embeddings are built (local
  `sentence-transformers`) and communities post-processed (igraph). The `hybrid` mode and
  small (~0.015) scores are RRF fusion artifacts, not keyword-only fallback -- ignore them. If
  a fresh `uv sync` wipes the venv, re-run `embed` + `postprocess` and restart the session.
* A backgrounded `SessionStart` hook runs `embed` + `postprocess` here, so the usual manual
  refresh is normally already done -- but the staleness symptoms in the reference still apply.

## Pre-push, in addition to the global checklist

* `uv run python tools/architecture_fitness.py --ambient` -- fails on an `os` import or a
  home/cwd/absolute/expanduser read with no owner entry. Exit 0 does not mean nothing reads
  ambient state directly: owner entries exempt real reads, and an unowned `resolve()` is
  reported without failing. The suite asserts this too, so this is a second reading rather
  than the only one.
* Do the code changes require updates to the maintenance skill or the security-audit skill?
* Do they require updates to `install.md`?
* Release notes?
* Consider running the toolguard maintenance skill -- a push is a good curation checkpoint.
* If anything under `docs/`, `README.md`, `AGENTS.md`, or `llms.txt` changed since the last
  push, run `/documentation-review`. This is the main defense against doc drift, and
  `docs/agent-map.md` summarizes every other doc with no other mechanism keeping it in sync,
  so it is the most likely thing to go stale silently. Don't skip it because a change looks
  small -- several of this project's own doc bugs came from small, individually reasonable
  edits.
* *After* the push, ask whether to refresh the governing toolguard:

  ```bash
  uv tool upgrade toolguard      # re-resolves master; correct again as of 2026-08-03
  ```

  Then **smoke-test it**, because a hook that cannot launch fails SILENTLY -- Claude Code treats
  only exit code 2 as blocking, so a broken registration means no permission hook at all, with
  no error anywhere:

  ```bash
  echo '{"session_id":"t","hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls"},"cwd":"'$PWD'"}' | ~/.local/bin/toolguard
  ```

  Worth keeping: between 2026-08-02 and 2026-08-03 the install was a **local path** build, and
  `uv tool upgrade` was the WRONG command for that window, because upgrade tracks the original
  install source. Resolved -- the source is `git+https://github.com/arnonmoscona/toolguard`
  again (0.5.1 @ 532de02; `install` pins the resolved commit, `upgrade` re-resolves). If it is
  ever a local path again, `upgrade` silently does the wrong thing: check `uv tool list` first.
  The SessionStart check now also raises staleness by itself when the tree is clean and differs
  from the installed copy, so this no longer depends solely on remembering.
* **Open commitment (Arnon, 2026-08-02): after pushing TOO-19, remove the hooks and config that
  are no longer needed** -- both configuration entries and hook code. Known candidate:
  `.claude/toolguard_hook.toml:58` is marked *"TEMPORARY -- TOO-19 Phase 0 unattended
  implementation run (2026-07-25)"*. Sweep for other `TEMPORARY` / `FIX after` markers, the
  auto-mode `soft_deny` rules added to `~/.claude/settings.json` during TOO-19, and any hook
  registration that only existed to support this ticket. Ask before touching anything outside
  the project.

## Technical notes

Deeper design rationale is in [technical-notes.md](technical-notes.md) -- read the relevant
section on demand, not at launch.

<!--
Maintainer notes (stripped before entering context).

302 -> 118 lines, plus 2 path-scoped rules that load only when relevant.

NO @AGENTS.md IMPORT -- and do not add one back. An earlier draft of this file added it, on the
reasoning that AGENTS.md and CLAUDE.md being separate unlinked files is a doc-drift risk. That
was the wrong trade: AGENTS.md is written for agents encountering the repo from OUTSIDE (a user
saying "install toolguard"), not for a session developing toolguard, and imports load in full at
launch -- they organize, they do not save. Measured 2026-07-31: the import cost 1.7k tokens of
every single session for a file whose audience is someone else entirely. Claude Code does not
read AGENTS.md on its own, so without the import it costs nothing here. The drift risk is real
but belongs to the pre-push documentation check, which already covers AGENTS.md.

GEMINI.md and QODER.md were installer cruft for agents Arnon does not use; deleted 2026-07-31.

Moved out to path-scoped rules (load on demand, not every session):
  - PEG/canopy two-phase procedure -> .claude/rules/bash-grammar.md
  - unittest/BDD/coverage conventions -> .claude/rules/testing.md

Removed as redundant with current models:
  - The inlined 15-line `tools/coverage_stdlib.py` source. The file exists in the repo; the
    rule now names the command.
  - The `ignoredirs=[sys.prefix, sys.exec_prefix]` explanation and the "trace is line-only
    and slower than coverage.py" caveat.
  - "Claude has a strong tendency to implement parsing using regex" as a standalone
    subsection. The tendency is real and stays documented, but as one sentence pointing at
    the procedure that prevents it, not a section about Claude's psychology.
  - Long restatement of the code-review-graph tool table -- now in the shared reference.

Kept close to verbatim, deliberately: the announce-intent rule and the --dev rule. Both are
project-specific, empirically earned, and have regressed before. The announce block is the
biggest remaining chunk and I compressed it about a third; I would not cut it further.
-->
