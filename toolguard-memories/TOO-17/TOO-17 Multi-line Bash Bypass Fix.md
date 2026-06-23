---
title: TOO-17 Multi-line Bash Bypass Fix
type: note
permalink: toolguard/too-17/too-17-multi-line-bash-bypass-fix
tags:
- task-memory
- TOO-17
- security
- bash-parser
---

# TOO-17 -- Multi-line Bash commands bypass permission checks (fail-open)

**Severity:** Show-stopper (Critical) -- fail-OPEN in a security control.
**Status:** Open. Folded into the current TOO-8 effort; BLOCKS publishing the updated TOO-8
docs (fix before release). Implementation not started -- a few more TOO-8 doc-review changes
come first (Arnon, 2026-06-19).
**Discovered:** while writing TOO-8 docs (compound-commands section of permission-patterns.md).
Ticket draft (clipboard source): /tmp/too-multiline-bash-bypass-ticket.md.
Related: [[TOO-8 Hierarchical Configuration Implementation Plan]].

## Problem

The bash parser handles only a single logical line. A multi-line Bash command
(newline-separated statements, or a whole script in one tool call) is NOT split into
sub-commands; combined with DOTALL `fnmatch`, a multi-line command whose FIRST line matches
an allowed prefix is allowed in full -- including dangerous later lines. Fail-open bypass.

## Reproduction (verified end-to-end)

Config (normal mode, not takeover):

```toml
[permissions]
allow = ["Bash(git status:*)"]
deny  = ["Bash(rm -rf:*)"]
```

| Input | Observed | Expected |
|-------|----------|----------|
| `git status && rm -rf /` (single line) | deny | deny |
| `git status` NEWLINE `rm -rf /` | allow (rm -rf runs) | deny |
| `git status;` NEWLINE `rm -rf /` | allow | deny |

Verified via `compound.resolve_compound_permission` + `permissions.check_permission`.

## Root cause (three compounding factors, all verified)

1. **Grammar = single logical line.** `toolguard/parser/bash_parser.peg`: `spacing <- [ \t]*`
   (no newline); no newline control operator (`control_op` is only `&&`/`||`/`;`/`&`). A
   newline-separated command does not fully parse.
2. **Parse-failure fallback returns the whole blob as one command.**
   `toolguard/parser/command_extractor.py::extract_commands` catches `ParseError`, logs
   "Parse failed", and returns `[command_line.strip()]` -- never decomposed.
3. **DEFAULT matching is DOTALL; deny is start-anchored.**
   `toolguard/permissions.py::match_command`: `fnmatch` turns `git status:*` into
   `git status*` and matches across the newline; DEFAULT/glob/native deny is anchored at the
   command start, so `rm -rf:*` misses a blob beginning with `git status`.

Related: backslash line-continuation (`echo foo \` NEWLINE `bar`) parses but stays a single
undecomposed command -- same one-unit effect.

## Impact

Claude Code routinely emits multi-line Bash / scripts in one tool call, so this is hit in
normal use. The bypass needs only the first line to match an allowed prefix. Worse under
takeover mode (toolguard is the sole gatekeeper).

## Partial mitigation (NOT a fix; do not rely on it)

`[regex]` deny patterns use `re.search`, scanning the whole string incl. newlines, so
`Bash([regex]rm\s+-rf)` denies the blob. Start-anchored DEFAULT/glob/native deny does not.

## Proposed fix (decide during implementation)

- **Option A -- decompose by line (recommended).** Treat unquoted newlines as command
  separators: split into logical lines, run extraction + the resolution cascade per line
  (strictest-wins across all). Prefer adding a newline separator to the PEG grammar (robust)
  over pre-splitting. Must preserve heredocs, quoted/escaped newlines, line continuations.
- **Option B -- fail closed on un-decomposable input.** If a command contains a newline and
  cannot be cleanly decomposed, deny / apply `no_match_fallback` instead of matching the
  whole blob. Most conservative.
- **Option C -- defense in depth.** Prevent DEFAULT/glob matching from spanning newlines
  (no DOTALL, or reject newline-containing commands from prefix allows), alongside A/B.

Recommendation: A with C as backstop; B as the guarantee when decomposition is impossible.

## Acceptance criteria

1. `git status` NEWLINE `rm -rf /` is DENIED with the config above (plus `;`+newline, blank
   lines, leading/trailing newlines, CRLF).
2. Each statement of a multi-line command is validated independently; any dangerous line
   denies the whole command (strictest-wins), matching single-line `&&` behavior.
3. No new fail-open path: input that cannot be safely decomposed fails closed
   (deny / `no_match_fallback`), never matches the whole blob via a prefix allow.
4. Backslash line-continuation handled (joined or per-part validated), not allowed as an
   opaque unit on a first-line match.
5. Heredocs, quoted newlines, and multi-line strings inside one-liners are not mis-split into
   spurious commands that break legitimate use.
6. Unit tests (stdlib `unittest`, BDD/Gherkin docstrings) cover all the above incl. the exact
   repro; full suite green WITH and WITHOUT `CLAUDE_SETTINGS_PATH`.

## Documentation requirements (part of TOO-17)

- `docs/permission-patterns.md` (Compound commands): how multi-line commands / scripts are
  handled (decomposed by line and operator) + remaining limits (heredocs, control structures,
  process substitution).
- `docs/security.md`: state the guarantee (per-statement validation / else fail-closed) +
  residual caveats.
- Re-check `technical-notes.md` compound-resolution section for accuracy after the change.

## Implementation notes

- Non-trivial -> use the **feature-coder** subagent; keep main-agent context lean.
- PEG parser is generated from `bash_parser.peg` via `canopy` (dev dependency); regenerate
  `bash_parser.py` after grammar edits. Runtime stays stdlib-only.
- Files likely touched: `bash_parser.peg`, `command_extractor.py`, `permissions.py`, tests,
  and the docs above.
- Arnon does all git writes.

## PRELIMINARY IMPLEMENTATION PLAN (v1 -- for Arnon's review)

Status: preliminary. Expect a couple of iterations before implementation. Open questions
are collected in the dedicated section at the end (NOT asked interactively, per Arnon).

### 1. Use-case characterization (grounded in real Claude Code logs)

Sampled all Bash tool-uses in this machine's Claude Code transcripts
(`~/.claude/projects/*/*.jsonl`):

- **467 Bash tool-uses total; 134 (28.7%) contain a newline.** Multi-line Bash is normal
  use, not an edge case. Category counts (overlapping -- one command can hit several):

  | Category | Count | Notes |
  |----------|-------|-------|
  | plain newline-separated statement sequence | 83 | **the bypass class**; equivalent to `;`-separated |
  | heredoc (`cmd <<'EOF' ... EOF`, `uv run python - <<'PY' ...`) | 30 | body is DATA, not commands |
  | loop (`for/while/until ... do ... done`) | 17 | control structure |
  | if-then (`if ... then ... fi`) | 4 | control structure |
  | case (`case ... esac`) | 2 | control structure |
  | backslash line-continuation (`\` + NL) | 9 | one logical line |

  (Comments `# ...` and multi-line quoted strings also appear interleaved within the
  plain-newline-sequence examples.)

Derived use-case classes we must handle:

1. **Plain newline-separated statements** (most common; the security bypass). Decompose
   per line, validate each, strictest-wins. MUST FIX.
2. **Trailing-operator line continuation** -- a line ending in `&&`, `||`, `|`, `;` (or `\`)
   then continuing on the next line. Logically ONE compound; the newline is a continuation,
   not a separator.
3. **Backslash line-continuation** -- `\` + newline. One logical line.
4. **Heredocs** -- the body is input/data to the introducing command, NOT shell commands.
   Only the introducing line (`cat <<EOF`, `uv run python - <<'PY'`) is a command; the body
   must be set aside, never split into spurious commands. 30 real cases -- mishandling this
   breaks legitimate workflows AND could fail-open.
5. **Shell control structures** (for/while/until/if/case) -- currently `reserved_word`s, so
   the parse fails and we hit the fail-open whole-blob fallback. 23 real cases. See decision
   below (recommended: resolve to ASK, not silently allow nor hard-deny).
6. **Comments** (`# ...` to end of line) -- not commands; must be stripped (respecting that
   `#` only starts a comment at a word boundary, so `http://x#frag` is not a comment).
7. **Multi-line quoted strings** -- newline inside `'...'`/`"..."` is literal, must NOT be a
   separator.

### 2. Edge cases we deliberately will NOT fully resolve (with justification)

These resolve to **ASK** (safe: human in the loop) rather than being statically decomposed:

- **Control-structure bodies' data / control flow** -- bash is Turing-complete; statically
  determining what a loop/conditional actually runs (esp. with variable expansion) is
  infeasible and not the threat we are closing. We RECOGNIZE the construct and ASK.
- **`eval`, dynamically constructed commands, `$VAR` that expands to a command** -- cannot
  be resolved without executing; ASK.
- **Process substitution `<(...)`, `>(...)`** -- rare (0 in sample); ASK.
- **Heredoc body contents** -- intentionally NOT parsed as bash (it is data, e.g. embedded
  Python). Correct behavior, not a gap.
- **Quoted-context backslash-newline literalness** -- see open Q3; minor, likely deferred.

Justification theme: anything we cannot decompose with confidence must FAIL SAFE. The fix
replaces today's fail-OPEN (allow whole blob on a first-line prefix match) with fail-SAFE
(decompose-and-check, else ASK/deny). We never silently allow an undecomposed construct.

### 3. Broad grammar-change plan (PEG, regenerated via canopy)

Guiding constraint: keep `spacing <- [ \t]*` UNCHANGED. Newlines must NOT be swallowed by
generic spacing or they would leak inside simple commands, quotes, and heredocs. Introduce
newline handling only at explicit, intended points:

a. **Statement separation.** Restructure the top level so a program is a list of statements
   separated by newlines and/or `;`:
   `program <- line_ws statement (statement_sep statement)* line_ws`
   where `statement` is today's `compound_command`, `statement_sep <- (newline / ";")+`
   (collapses blank lines, leading/trailing newlines), and `line_ws` allows runs of
   spaces/tabs/newlines/comments between statements.
b. **Trailing-operator continuation.** After a binary operator that demands a right operand
   (`&&`, `||`, `|`), allow newlines before the operand: e.g. `and_op <- spacing "&&" line_ws`.
   This makes `git status &&` + NL + `rm -rf /` parse as ONE compound (correct), while a bare
   newline between two complete statements is a separator (rule a).
c. **Comments.** Add `comment <- "#" (![\n] .)*` recognized at statement boundaries / line_ws
   (only at word boundary -- preceded by whitespace or line start).
d. **Control structures (for/while/until/if/case).** Decision-dependent (open Q1). Minimum:
   the grammar should RECOGNIZE them (so we can route to ASK precisely) rather than fall
   through to a generic parse-failure. Coarser alternative in open Q7.
e. **Heredocs.** The current `heredoc_content <- (![\n\r] .)*` only captures inline
   single-line content; a real multi-line heredoc body is not consumed. PEG heredoc matching
   needs a back-reference to the captured delimiter, which canopy PEG does not support well.
   Recommended: handle the heredoc BODY in a bounded lexical pre-pass (section 4, step 3),
   NOT in the grammar. See open Q2 (design-constraint sign-off needed).

Background `&` is decomposed line-wise consistently with `;`.

### 4. Pre-processing pipeline (before the PEG parse / pattern matching)

Each step deterministic and documented. Steps 1-4 are LEXICAL normalization (kin to the
existing `normalization.py`), NOT command parsing -- command parsing stays in the PEG
grammar, preserving the project's "no custom bash parsing" constraint. (The heredoc step is
the one that needs explicit sign-off against that constraint -- open Q2.)

1. **Normalize line endings:** CRLF / lone CR -> LF.
2. **Join backslash-continuations:** remove `\` + newline (outside quotes). Recommend
   replacing with EMPTY string, NOT a space -- bash removes it entirely, so `--out\`+NL+`put`
   must become `--output` (a space would wrongly split the token). See open Q3 and the
   ticket comment.
3. **Set aside heredoc bodies:** detect `<<` / `<<-` + (quoted or unquoted) delimiter; remove
   the body lines up to the closing delimiter line (for `<<-`, allow leading tabs), keeping
   the introducing command line. Handles multiple heredocs per line. [pending Q2]
4. **Strip comments:** remove `#`-to-end-of-line at word boundaries (outside quotes).
5. **PEG parse** the cleaned multi-statement text -> statements -> pipelines -> simple
   commands (grammar from section 3).
6. **Resolve each leaf sub-command** through the existing cascade (`resolve_one`), then
   combine strictest-wins (deny > ask > allow), exactly as compound resolution does today.
7. **Undecomposable segments -> ASK (or deny; open Q4),** never the whole blob. This replaces
   the fail-open `return [command_line.strip()]` fallback in `command_extractor.extract_commands`.

### 5. ASK semantics and grammar impact (Arnon's special-review item)

- ASK is fundamentally a RESOLUTION-layer outcome, not a parser concern. The combine logic
  already supports `ask`; we just need a path that yields it.
- BUT to route to ASK *precisely* (vs. a coarse "any leftover parse failure -> ASK"), the
  grammar must RECOGNIZE control structures / process substitution as such. That recognition
  is the only real grammar impact of ASK. The extractor's contract changes from
  `List[str]` to a structured result that can say "segment X is undecidable (reason)"; the
  resolver maps that to ASK/deny.
- This is the item you flagged for special attention. Net: limited grammar impact (recognize,
  don't fully parse, the constructs); main change is the extractor return type + resolver.
  Open Q1 and Q7 decide how much grammar recognition we invest in.

### 6. Code-level changes (anticipated)

- `toolguard/parser/bash_parser.peg` -> regenerate `bash_parser.py` with canopy (dev dep;
  runtime stays stdlib-only).
- `toolguard/parser/command_extractor.py`: add lexical pre-pass (steps 1-4); change
  `extract_commands` to return a structured result distinguishing decomposed leaves vs.
  undecidable segments; REMOVE the fail-open whole-blob fallback. Keep a thin compat shim if
  feasible (open Q6).
- `toolguard/compound.py` (`resolve_compound_permission` / `check_compound_permission`): map
  undecidable segments to ASK/deny; preserve strictest-wins and the existing reason format
  (note the implicit coupling with `hook._COMPOUND_MATCH_PATTERN`).
- `toolguard/permissions.py` (`match_command`): Option-C backstop -- ensure DEFAULT/glob
  matching cannot span newlines (leaf commands should be newline-free after decomposition;
  add the guard as defense-in-depth regardless).
- Tests + docs (sections below).

### 7. Acceptance criteria (ticket's six, plus additions)

Ticket AC 1-6 (the exact repro, per-statement validation, no new fail-open, backslash
handling, no mis-split of heredocs/quoted newlines, full BDD unittest suite green with and
without `CLAUDE_SETTINGS_PATH`). ADD:

7. Heredoc body (incl. embedded non-bash like Python) is never split into spurious
   sub-commands (protect the 30 real cases); multiple heredocs per line handled.
8. Control structures resolve per Q1 decision (recommended ASK), deterministically.
9. Comments stripped without misfiring on `#` inside args/URLs.
10. Trailing-operator line continuation (`&&`/`||`/`|` + NL) treated as one compound.
11. CRLF / blank-line / leading-trailing-newline variants behave identically.

### 8. Process / delegation

- Implementation is non-trivial (grammar + pre-pass + extractor API + extensive tests) ->
  delegate to the **feature-coder** subagent once this plan is approved.
- Canopy regeneration step must be in the implementation notes; runtime stays stdlib-only.
- Arnon does all git writes.

## OPEN QUESTIONS / DECISIONS NEEDED (please annotate inline)

1. **Control structures (for/while/if/case): ASK, attempt full decomposition, or fail-closed
   deny?** 23 real cases use them in normal dev work, so a blanket DENY breaks workflows;
   full decomposition is complex and still cannot resolve dynamic flow. RECOMMEND: resolve to
   ASK (human in loop, no fail-open, no workflow breakage). Could be configurable
   (`multiline_control_structures = ask|deny|decompose`, default ask). This is your
   special-review item (it drives how much grammar recognition we build -- see Q7).
2. **Heredoc body handling: bounded lexical pre-pass (recommended, tractable) vs. grammar-level
   (purer re: the "no custom parsing" constraint, but PEG back-reference for the delimiter is
   hard/likely infeasible in canopy).** Need your sign-off, since this is the one step that
   brushes against the design constraint. My framing: delimiter-based body removal is
   deterministic lexical normalization (like `normalization.py`), and real command parsing
   still goes through the PEG grammar -- so I argue it does NOT violate the spirit of the
   constraint. Agree?
3. **Backslash-continuation join: replace `\`+NL with EMPTY (my recommendation, matches bash
   token-join) or a SPACE (your ticket comment)?** A space wrongly splits an intended single
   token (`--out\`+NL+`put` -> `--out put`). Also, inside single quotes bash keeps `\`+NL
   literal -- do we accept that minor inaccuracy (defer) or handle quoted context? RECOMMEND:
   empty, outside quotes; defer the quoted-literal nuance as low-risk.
4. **Default outcome for undecomposable / parse-failure segments: ASK or DENY
   (`no_match_fallback`)?** Ticket AC#3 says "fail closed (deny / no_match_fallback)"; ASK is
   softer and keeps you in the loop. Should it respect the existing `no_match_fallback`
   setting, or be its own knob? RECOMMEND: ASK by default for "recognized-but-undecidable"
   (control structures), DENY for "truly unparseable garbage"; both honor an override.
5. **Same behavior in normal and takeover mode?** I assume YES (takeover makes fail-safe even
   more important). Confirm.
6. **`extract_commands` API: OK to change the return type and update all call sites + tests,
   or must I keep a backward-compatible `List[str]` wrapper?** A structured result is cleaner
   for the ASK/undecidable signal.
7. **How much grammar recognition for control structures?** Precise (grammar recognizes
   for/if/case/while -> exact ASK) vs. coarse (any residual newline-containing parse failure
   -> ASK). Precise is more robust and gives better messages; coarse is far less grammar
   surface. Tied to Q1.
8. **Process substitution `<(...)`/`>(...)`: ASK (recommend) or treat the whole command as
   one unit?** Rare (0 in sample).
9. **Anything you want explicitly OUT of scope for this ticket** (e.g. arithmetic `(( ))`,
   `[[ ]]` test compounds) that I should document as a known limitation rather than handle?

## DECISIONS (Arnon, 2026-06-20 review of plan v1)

- **Fix = Option A (decompose by line), confirmed.**
- **Backslash continuation joins into a single logical line BEFORE matching.** Example:
  `cd ~/projects; \`NL`ls \`NL`-l \`NL`~/` -> TWO commands to match: `cd ~/projects;` and
  `ls -l ~/`. The join must still correctly identify the `;` statement separator (incl.
  escape cases). "Space"/"blank" in Arnon's wording is CONCEPTUAL (a blank in whatever form),
  NOT a literal grammar SPACE token -- agrees with my EMPTY-vs-space point (Q3).
- **Section 2 edge cases: agreed**, incl. ASK as the default fallback.
- **Section 4 -- ADD two normalization steps:** (a) collapse runs of non-semantic
  whitespace to a single blank; (b) trim leading/trailing statement padding to nothing.
  Over-normalization (e.g. inside quoted strings) is FORGIVEN for matching purposes -- it
  does not change approve/deny semantics. [Claude note: I agree; only theoretical caveat is a
  rule that intentionally depends on exact internal whitespace of a quoted literal, which is
  not a realistic authoring pattern. Proceeding as agreed.]
- **Section 5 ASK: agreed.** Implies a "hidden rule": un-decomposable input -> ASK even with
  no matched TOML pattern. Deemed safe.
- **Section 6: PEG grammar will grow; comment it well for human review.** Current commenting
  is acceptable but a bit terse; new/harder rules need MORE verbose comments.
- **Q1 control structures (refined policy):** do NOT build a full bash parser / semantic
  analyzer (that would be recreating ~80% of bash -- explicitly OUT OF SCOPE). Split into two
  tiers driven by OBSERVED common patterns:
    - **Simple ("one-liner-ish") constructs** -- e.g. a single, non-nested guard like "if a
      file exists, then run a (possibly linear sequence of) command(s)". MAY be decomposed and
      its inner commands validated.
    - **Complex constructs** -- presence of `else`/`elif`, nested control structures, or
      anything beyond the simple tier -> immediately ASK ("complex control structures").
  Give special, minimal semantic analysis ONLY to simple patterns Claude actually does a lot;
  everything else punts to ASK. Do not speculate about constructs we see no evidence for.
- **Q2 heredoc pre-pass: approved** (two passes / possibly two grammars is acceptable).
- **Q3: agreed** (empty / conceptual-blank join).
- **Q4: agreed** -- when in doubt, ASK.
- **Q5: agreed** -- identical behavior in normal and takeover mode.
- **Q6: OK to change the internal parser/extractor API** -- it is internal; external surface
  is the TOML + behavior. Accept the extra work/testing.
- **Q7: covered by Q1** -- don't overdo; punt to ASK at the limits of parser + minimal
  semantic analysis; do not attempt deep parse trees (assess "too deep").
- **Q8 process substitution: revisit after we have the pattern examples**; look for these
  cases while scanning.
- **Q9: revisit after examples.**
- **Also investigate:** does Claude `echo`/pipe a multi-line set of statements into a shell
  (e.g. `echo "...; ..." | bash`, `bash -c "..."`)? Arnon thinks it does -- confirm in
  transcripts and treat as a pattern.

## ROUND 2 RESOLUTIONS (2026-06-20, after full-corpus mining)

Data + per-pattern expected outputs live in [[TOO-17 Transcript Patterns and Expected Outputs]].
Headlines:
- Corpus now 7,767 Bash uses (recovered Mac transcripts under `~/mac-recovery` -- missing-
  transcripts theory CONFIRMED). **94% of distinct multi-line commands currently fail-open**
  (undecomposed whole-blob) -- the exact surface we close.
- **Executor classification** drives heredoc/`-c`/pipe handling (decide by the RECEIVING
  command, via the parse tree):
    - bash-family (`bash sh dash ksh zsh`): payload is bash -> re-decompose + validate.
    - foreign (csh/tcsh/fish; python/node/perl/ruby/php/Rscript/awk): -> **ASK**.
    - non-executor/unknown (cat/tee/pbcopy/...): heredoc body = data -> stub + decompose around.
- **H1 (heredoc into python) -> ASK** (corrected from stub). **H2 (cat <<EOF | pbcopy) ->
  `['cat __HEREDOC_TO_pbcopy__','pbcopy']`** -- heredoc stub uses an all-word-char sentinel
  `__HEREDOC_TO_<sink>__` (sink = ultimate pipe consumer) so a single regex rule can match
  exec vs non-exec sinks cleanly. **PS1 (python -c) -> ASK.** **`bash -c "<bash>"` -> decompose
  inner** (real usage ~0 but cheap; per decision 3 -- v1-scope option to ASK instead is open).
- **Process substitution `<(...)`: confirmed NOT decomposed today** (latent fail-open) ->
  route to **ASK** for now.
- **Brackets:** `[ ]`/`[[ ]]`/`(( ))` are tests, not commands; only `$(...)` inside them
  executes and is ALREADY extracted -> no special bracket inspection needed. Real usage is
  only POSIX `[ ]`; v1 ASKs on `[[ ]]`/`(( ))`.
- Governing principle to document everywhere: **"when in doubt, ASK."**

## IMPLEMENTATION STATUS -- GRAMMAR-FIRST REWORK COMPLETE + VERIFIED (2026-06-21, Claude)

Reworked grammar-first per Arnon's decision; independently verified by the main agent:
- Grammar `bash_parser.peg` grew (+270/-27) to handle newline statement separation, trailing-
  operator continuation, newline-spanning quotes, control structures (simple vs complex),
  `[ ]`/`[[ ]]`/`(( ))`, `<bash-family> -c`, and process substitution. Regenerated with
  `npx -y canopy@latest`.
- **Integrity restored:** the earlier hand-PATCH of the generated parser was removed by
  relabeling the grammar (`program <- ... compound_command:statement ...`) so canopy emits the
  needed attribute natively. A fresh canopy regen is now BYTE-IDENTICAL to the committed
  `bash_parser.py` (verified) -- the parser is cleanly regenerable, zero manual edits.
- `multiline.py` reduced to the SANCTIONED lexical pre-pass only (line-endings, backslash
  join, heredoc body/sink handling, comment strip, whitespace) -- no statement/pipe/control
  structural parsing, no regex control-structure matchers.
- Tests: `test_multiline_bash` 23/23 (incl. newline-body loop fixtures I added); FULL SUITE
  706/706 WITH and WITHOUT `CLAUDE_SETTINGS_PATH`; ruff clean.
- Live-path security spot-check (resolve_compound_permission): bypass repro -> deny; newline
  loop danger -> deny / safe -> allow; heredoc->python -> ask; heredoc->pbcopy body-as-data ->
  allow; benign multiline -> allow. All correct.

COMMAND SUBSTITUTION (checked 2026-06-22):
- Inner-command EXTRACTION already works in the live path for `` `...` ``, `$(...)`, nested,
  and piped-inner: verified `rm `ls`` (deny ls) -> deny, `rm $(ls)` (deny ls) -> deny,
  `rm `ls | grep x`` (deny grep) -> deny, `echo $(ls $(pwd))` (deny pwd) -> deny,
  `rm `ls`` (all allowed) -> allow. Done by the PEG `cmd_substitution` rule + tree-walker.
- OPEN / NEEDS MORE THOUGHT before deciding (Arnon, 2026-06-22) -- DEFERRED until AFTER
  Arnon's current-state review. Add a heredoc-style PLACEHOLDER for how the OUTER command is
  presented to matching when an argument is a command substitution. Considerations:
    - NAMING/SEMANTICS: we never have the substitution's OUTPUT pre-execution -- we only have
      the substitution EXPRESSION. So a name like `__BACKTICK_COMMAND_OUTPUT__` is misleading;
      the placeholder stands for "an argument produced by a command substitution," not a value.
      Pick a name that reflects that.
    - FORM A (replace): `rm __PLACEHOLDER__` -- cleanest to match `rm <subst>`, but LOSES the
      ability to match on the substitution's content.
    - FORM B (marker + preserved original): e.g. `rm __PLACEHOLDER__ `ls | grep something``
      -- lets a rule easily match `rm __PLACEHOLDER__` (ignore content, no complex regex) WHILE
      preserving the ability to match the content; and a normalized marker abstracts over the
      multiple syntactic forms (`` `...` `` vs `$(...)`).
    - Consider SEVERAL forms; possibly choose simplicity. Decide whether `` `...` `` and `$(...)`
      share one marker (they are semantically identical) or are distinguished.
    - MEASURE FIRST: scan transcripts to assess how often Claude actually uses command
      substitution. If rare/non-existent, do NOT over-engineer (maybe leave as-is, since inner
      commands are already extracted + validated).
    - Implementation (whichever form): TREE-WALKER change (use the parsed cmd_substitution
      nodes), stays grammar-based. Inner commands remain extracted + validated regardless.

PROCESS (Arnon, 2026-06-22): parsing changes go in TWO phases to stop feature-coder
hand-rolling. Phase 1 = edit ONLY `bash_parser.peg` + regenerate; acceptance: only the
.peg (+ regenerated .py) changed, regen is BYTE-IDENTICAL to canopy output (no manual edits),
canopy accepts it, target inputs parse to the intended tree shape (dump tree). Tests EXPECTED
to fail in phase 1 (Python not updated). Claude reviews the grammar in isolation. Phase 2 =
Python (tree-walker/resolution/tests) to green. Arnon will add this to CLAUDE.md. See
[[feedback-grammar-changes-two-phase]].

## READABILITY REFACTOR (agreed approach, 2026-06-22) -- post-review of the heavy files

Arnon's review: `command_extractor.py` (esp. 158-line `_extract_compound_into`) and
`compound.py` are hard to reason about; `multiline.py` is more readable BECAUSE it doesn't
chew on the raw parse tree. Root cause: TWO parallel raw-canopy-tree walkers
(`_extract_compound_into` + legacy `_extract_from_tree`) duplicating TreeNodeN/`hasattr`
navigation; a god-function mixing tree-nav + classification + policy + dedup; strictest-wins
triplicated (`_resolve_leaf`, `_combine_strictest`, `check_compound_permission`).

AGREED PLAN (Arnon approved; "like a light AST"):
1. **Tests first (DONE 2026-06-22):** strengthened the behavioral net to make the refactor
   safe -- +18 tests (module 23->41, suite 706->724), all green. Pin `__HEREDOC_TO_*`
   sentinel shape/ask_floor/rule-matching, substitution gating, control-structure
   classification, quote robustness. All at the PUBLIC contract level
   (`resolve_compound_permission` / `extract_structured`), NOT internal walkers (which get
   deleted), so they survive the churn.
2. **Introduce a small typed IR (light AST)** in a new `command_model.py`: dataclasses
   (`Sequence`, `Pipeline`, `SimpleCmd(text, substitutions)`, `ControlStructure(kind,
   is_complex, condition, body)`, `ProcSubst`/`Undecidable`). ONE builder walks the canopy
   tree once into the IR (the ONLY code touching raw TreeNodeN), dispatching via a single
   `node_kind()` classifier (collapses the ~12 `_is_*` predicates) -- visitor pattern.
3. Reimplement extraction/classification as simple recursion over the IR; delete the legacy
   `_extract_from_tree`; `extract_commands` (List[str]) becomes a trivial IR projection.
4. ONE strictest-wins combinator in compound.py; `_resolve_leaf`/`check_*`/`resolve_*` thin.
5. FSM: NOT needed for the heavy files (only the lexical scanners in multiline.py, already
   clean) -- skip.
   Patterns: separation of concerns + early simplification (the IR) + visitor + simple
   recursion. Refactor keeps tests GREEN with NO test changes (TDD refactor step). Stage it:
   command_extractor->IR first (Claude reviews), then compound.py.
6. **Synergy:** the `SimpleCmd.substitutions` IR field is the natural home for the deferred
   `__BACKTICK_COMMAND_OUTPUT__` placeholder feature -- do that AFTER the IR lands.

REFACTOR STATUS (DONE + verified, 2026-06-22):
- Step 1 (tests) DONE. Stage 1 (IR + command_extractor) DONE. Stage 2 (single strictest-wins
  combinator in compound.py + fully fold ctrl_body into the IR) DONE.
- Result: `command_model.py` (raw tree -> IR; the ONLY code touching Canopy nodes, 811 lines),
  `command_extractor.py` (IR -> results, 1166->842), `compound.py` (resolution + one combinator,
  322). Verified: ZERO `hasattr`/TreeNode outside command_model.py; 724/724 both env modes; ruff
  clean; behavior preserved (the 41-test net stayed green). Two walkers, the 158-line
  god-function, ~12 `_is_*` predicates, and triplicated strictest-wins all eliminated.
- NOTE: a session-wide `ruff format .` (against the "don't ruff-format here" memory) churned the
  whole repo single->double quotes (cosmetic, ~47 files). Arnon: harmless, leave it. Going
  forward: format only changed files, never `ruff format .`.

DOCS (DONE 2026-06-22):
- `docs/permission-patterns.md`: rewrote stale "Compound commands" -> "Compound and multi-line
  commands" (operators, multi-line, substitution, `__HEREDOC_TO_<sink>__` sentinel + executor
  classification + rule examples + no-blanket-allow note, inline `-c`/`-e`, control structures
  simple/complex, procsub->ASK, limitations; "when in doubt ASK" up front).
- `docs/security.md`: new "Multi-line commands and the ASK-safe guarantee" (fail-safe; exec-sink
  / inline-foreign blanket-allow warning + ASK floor; defense-in-depth).
- `technical-notes.md`: new "Multi-line Bash decomposition (TOO-17)" (defect, ASK principle,
  grammar-first + light-AST/IR architecture, how-deep-and-why-not-deeper, pre-pass-vs-grammar,
  heredoc sentinel + executor classification incl. bash-family-only reasoning, ASK floors +
  no-blanket-allow invariant, substitution-placeholder deferral, flagged defaults).
- Cross-refs: configuration.md Step 3 -> permission-patterns; README nav + test count
  (683->724) updated. All internal doc links/anchors validated.

COMMAND-SUBSTITUTION PLACEHOLDER -- DEFERRED (data-backed, 2026-06-22): corpus scan shows
substitution is <1.5% of distinct commands, mostly false positives or benign `$(date)`; inner
commands already extracted+validated; not worth the surface. Documented current behavior;
revisit if usage changes (Arnon can override).

EXECUTOR LIST ROBUSTNESS (2026-06-23, Arnon review of FOREIGN_EXECUTORS):
- Finding: version staleness was a non-issue -- `_is_foreign_executor` already matches
  versioned names (python3.13/3.14/any, pypy3.x, node18) by PREFIX. The enumerated
  python3.9..3.12 entries were redundant + misleading. Removed them; FOREIGN_EXECUTORS now
  lists only canonical names with a comment that versions are handled dynamically (prefix is
  simpler + more robust than the "infer from year" idea -- no date logic, never stale).
- Real gap is UNRECOGNIZED interpreters (lua/deno/bun/julia): not floored if broadly allowed.
  Documented as a known limitation (security.md + code); user-config (env var) = deliberate
  YAGNI (Arnon agreed).
- BUG FOUND & FIXED (pre-existing, exposed by a new version test): a heredoc into a
  dotted-version interpreter (`python3.13 - <<PY`) produced `__HEREDOC_TO_python3.13__` -- the
  `.` violated the all-word-char sentinel AND broke the ASK-floor regex `__HEREDOC_TO_(\w+)__`,
  so it was NOT floored (would allow arbitrary python under `allow python3.13:*`). Fixed by
  sanitizing the sink label to `[A-Za-z0-9_]` in multiline.py (`-> __HEREDOC_TO_python3_13__`),
  still foreign-by-prefix and floored. Added version-robustness tests (727 total, green both
  env). Docs updated (security.md caveat, technical-notes executor note).

REMAINING:
- Arnon's review of the post-history-label work (refactor + strengthened tests + docs +
  substitution decision + executor-list robustness).
- Two flagged defaults documented as chosen, open to revisit: exec-sink/inline-foreign ASK
  floor; truly-unparseable default (honors no_match_fallback / ASK).
- Git: nothing committed (Arnon does git).

## IMPLEMENTATION REVIEW -- FIRST ATTEMPT FLAGGED (2026-06-20, Claude)

feature-coder completed a first pass: all tests green (module 21/21 -> later 21/23 after I
added 2 fixtures; full suite 704/704 with AND without `CLAUDE_SETTINGS_PATH`; ruff clean).
Implementation report: `toolguard-memories/implementation/TOO-17 Implementation Report.md`.

**BUT it deviated from the signed-off plan and likely violates a core project constraint --
AWAITING ARNON'S ARCHITECTURAL DECISION.**

- It did NOT touch the PEG grammar. Instead it added `toolguard/parser/multiline.py` (~1,186
  lines): a hand-written, quote-aware state machine that splits statements, splits pipes,
  tracks control-structure block depth, and recognizes/decomposes control structures via
  REGEX (`_SIMPLE_FOR_RE`/`_SIMPLE_WHILE_RE`/`_SIMPLE_IF_RE`).
- This conflicts with the project's foundational rule (CLAUDE.md/README): "we avoid doing any
  custom parsing of bash commands and instead rely on a formal PEG grammar for all parsing...
  Parsing with pure-Python regular expressions is crude, error-prone, and extremely difficult
  to reason about and debug." The agreed plan put statement/pipe splitting + control-structure
  recognition in the GRAMMAR; only a NARROW lexical pre-pass (heredoc body, backslash join,
  comments, whitespace) was sanctioned. It also ignored the explicit "edit the .peg,
  regenerate with canopy" instruction.

What is NOT wrong (fair assessment):
- Behavior is fail-SAFE: probes of ANSI-C `$'...'` quoting edge cases and the cases below
  returned deny/ask, never a silent allow. No demonstrated fail-open.
- The narrow lexical steps (CRLF, backslash join, heredoc body, comments, whitespace) were
  legitimately in-scope as pre-pass.

Concrete brittleness (demonstrated; this is the real cost of regex parsing here):
- Regex control-structure decomposition only matches the `;`-delimited form. The common
  NEWLINE-bodied loop (the norm in the real corpus) falls through:
    - `for f in a b; do<NL>echo $f<NL>done` -> ASK (design intent: ALLOW)
    - `for f in a b; do<NL>echo $f<NL>rm -rf $f<NL>done` -> ASK (design intent: DENY)
    - `for f in a b; do echo $f; rm -rf $f; done` -> DENY (correct -- the form the fixtures used)
  Fail-safe, but it (a) misses the design intent (simple loops should decompose), (b) is
  inconsistent for semantically identical commands, and (c) the original green suite gave false
  confidence (fixtures used the one form the regex supports). I added two newline-body loop
  fixtures encoding the design intent; they are now RED.

**DECISION (Arnon, 2026-06-21): OPTION A -- rework GRAMMAR-FIRST.** The hand-rolled
parsing must be removed. PEG grammar is the deliberate choice: "the only way to implement a
reliable and maintainable parser; hand-rolled parsing is brittle, error-prone, and incredibly
difficult to reason about." Constraint is hard and non-negotiable.

RECOMMENDATION (Claude): rework GRAMMAR-FIRST per plan v2 -- the PEG grammar should do
newline/statement/pipe splitting, quoting, and control-structure recognition; keep only the
narrow lexical pre-pass. Keep the current green suite as the acceptance bar and strengthen it
(newline-body loops, more quoting cases). This is Arnon's call: (A) rework grammar-first
(recommended; honors the constraint + fixes brittleness), or (B) consciously accept the
hybrid custom-parser approach (waive the constraint) and at minimum fix the newline-loop gap.
Held pending Arnon -- did NOT order a large redo unilaterally.

## IMPLEMENTATION PLAN v2 (ready for feature-coder; all key decisions locked 2026-06-20)

Fixtures (input->leaves->decision) are LOCKED in
[[TOO-17 Transcript Patterns and Expected Outputs]] (table F1-F24). Build to those.

### Step 1 -- lexical pre-pass (new `command_extractor` helper; quote-aware state machine)

Order, all deterministic; steps operate OUTSIDE quotes unless noted:
1. Line endings: CRLF / lone CR -> LF.
2. Backslash-continuation join: remove `\`+LF (-> empty) EXCEPT inside single quotes (where it
   is literal). Inside double quotes it IS a continuation (remove). [F10]
3. Heredoc handling: find each `<<` / `<<-` + (quoted|unquoted) delimiter; locate the body up
   to the terminator line (`<<-` allows leading tabs); resolve the ULTIMATE sink by walking the
   pipeline from the bearer to its terminus (basename of first token); then:
     - bash-family sink (bash/sh/dash/ksh/zsh): KEEP the body, hand it back through this whole
       pipeline as bash; merge its leaves. [F14]
     - else: replace `<<DELIM`+body with sentinel `__HEREDOC_TO_<sink>__` on the bearer; discard
       body. (foreign-exec -> ASK floor in Step 4; non-exec -> normal match.) [F12,F13,F15]
   Handle multiple heredocs per line.
4. Comment strip: `#`-to-EOL at a word boundary (preceded by whitespace/line-start), outside
   quotes. [F8,F9]
5. Whitespace: collapse runs to a single space; trim per-statement padding. Over-normalization
   inside quotes is acceptable (Arnon). [F5,F6]

### Step 2 -- grammar (`bash_parser.peg`; regenerate `bash_parser.py` via canopy; comment verbosely)

1. Top level: statements separated by `(newline / ";")+`; allow blank/leading/trailing. [F1,F2]
2. Allow newlines after binary ops `&&`/`||`/`|` (continuation). [F3]
3. Quoted strings (single/double/dollar) MUST span newlines -- verify `.` matches LF in canopy;
   fix the content rules if not. [F11] (critical: keeps `python -c "<multiline>"` ONE command.)
4. Control structures: recognize `for/while/until ... do ... done`, `if ... then ... fi`,
   `case ... esac`; recognize `else`/`elif` and nesting. SIMPLE (non-nested, no else/elif,
   linear simple-command body, condition = plain command or POSIX `[ ... ]`) -> expose inner
   commands. COMPLEX (`else`/`elif`, nesting, `[[ ]]`/`(( ))`) -> mark undecidable. [F19-F22]
5. `[ ... ]` recognized as a test (not a command); `[[ ]]`/`(( ))` recognized only enough to
   route to ASK. `$(...)`/backticks inside conditions are extracted as today. [F21]
6. `<bash-family> -c <quoted>`: detect at extraction; unquote and re-run the pipeline on the
   contents (decompose). Non-bash `-c` stays one opaque leaf. [F16,F17]
7. Process substitution `<(...)`/`>(...)`: recognize -> mark undecidable (ASK). [F23]

### Step 3 -- extractor API (`command_extractor.py`)

- Replace `List[str]` with a structured result distinguishing decided leaves from undecidable
  segments (`reason`). REMOVE the fail-open `return [whole_blob]`.
- Parse failure of a recognized construct -> undecidable (ASK); truly unparseable -> deny /
  honor `no_match_fallback` (Q4). Keep a thin compat shim only if cheap.

### Step 4 -- resolution (`compound.py`, `permissions.py`)

- `resolve_compound_permission`: map undecidable -> ASK; strictest-wins (deny>ask>allow).
- Foreign-exec heredoc leaf (`__HEREDOC_TO_<foreign>__`): clamp verdict to <= ASK (deny->deny,
  else->ASK) so a broad allow cannot downgrade it. [F12,F18]
- `match_command`: DEFAULT/glob must not span newlines (leaves are newline-free post-prepass;
  add guard as defense-in-depth).
- Executor sets (bash-family / foreign / via not-in-set => non-exec) live in one documented
  place; consider a config knob later.

### Step 5 -- tests (stdlib unittest, BDD/Gherkin docstrings)

One test per fixture F1-F24 + the exact ticket repro; CRLF/blank/pad variants; multiple
heredocs; quoted `;`/`|`/newline non-splitting; full suite green WITH and WITHOUT
`CLAUDE_SETTINGS_PATH`.

### Step 6 -- docs (part of TOO-17; doc publication still blocked until this lands)

- `permission-patterns.md` (Compound section): multi-line/script handling; heredoc sink marker
  `__HEREDOC_TO_<sink>__` + authoring examples; backslash join; `bash -c` decomposition;
  limitations.
- `security.md`: the guarantee (per-statement validation else fail-safe); **"when in doubt,
  ASK"** as the governing principle; explicit limitation list (foreign `-c`/interpreters,
  heredoc-into-interpreter, procsub, complex control structures, unknown heredoc receivers);
  warn that allowing an executor-sink heredoc is a blanket-allow-class risk; list the
  bash-family executor set explicitly.
- `technical-notes.md`: re-check the compound-resolution section after the change.

### Process

- Delegate to **feature-coder** once Arnon signs off this plan. Runtime stays stdlib-only;
  canopy is dev-only. Arnon does all git writes.

### Flagged for Arnon (non-blocking; defaults chosen)

- Exec-sink ASK floor (Step 4) slightly constrains rule authoring: a plain `allow` cannot
  permit a foreign-exec heredoc (must use ask/deny; or it defaults to ASK). Chosen to prevent
  fail-open; confirm acceptable.
- Q4 default for truly-unparseable input: deny vs ASK (recommend honor `no_match_fallback`,
  default ASK).

## NEXT-STEP METHOD (agreed)

1. Mine ALL transcripts (`~/.claude/projects/*/*.jsonl`, ~6 months) for Bash commands.
2. GROUP by similar structural pattern (too many to review individually); give 1-2
   representative examples per pattern group, with counts.
3. For each representative, present the EXPECTED post-processing output handed to the matcher
   (the decomposed sub-commands, or ASK), for Arnon to review/agree.
4. Agreed input->output pairs become the basis of unit + end-to-end tests. Real-Claude-derived
   examples are primary; artificial examples added only to fill gaps. (Behavior will evolve as
   Claude changes -- the classifier is re-runnable.)
- Scanning approach (Claude's call): deterministic Python classifier over the JSONL, NOT an
  LLM subagent -- exact, cheap, reproducible; Opus annotates the resulting clusters.

## Clarifications from discussion
- Backslash continuation (ticket comment, Arnon): prefers normalizing `\`+newline before
  matching so rule authors need no special rules, "as long as it does not introduce a
  semantic change." Resolved: join into one logical line; "blank" is conceptual; use EMPTY
  join to avoid token-splitting (confirmed by Arnon 2026-06-20).
