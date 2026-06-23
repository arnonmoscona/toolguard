---
title: TOO-17 Transcript Patterns and Expected Outputs
type: note
permalink: toolguard/too-17/too-17-transcript-patterns-and-expected-outputs
tags:
- task-memory
- TOO-17
- security
- bash-parser
- test-fixtures
---

# TOO-17 -- Multi-line Bash patterns (from real transcripts) + expected matcher input

Companion to [[TOO-17 Multi-line Bash Bypass Fix]]. Purpose: agree, per pattern group, on
what the matcher should receive AFTER pre-processing + decomposition. Agreed input->output
pairs become unit + end-to-end test fixtures.

## Corpus

- Source: all `~/.claude/projects/*/*.jsonl` on this machine -- **25 sessions, 468 Bash
  tool-uses** (458 distinct). Logs appear to be rotated, so this is the available window, not
  6 months. Re-runnable as Claude evolves.
- **135 / 468 (28.8%) are multi-line.** Multi-line Bash is normal use.

## KEY FINDING -- detection must be structural, not lexical

The quick regex classifier over-counted control structures and pipe-into-shell because shell
keywords / metacharacters appear NON-structurally in three places that the real parser must
treat as opaque:

1. **Comments & echo banners** -- `# Check for ...`, `=== ... for consistency ===`,
   `=== ... while the plugin was down ===`. The words `for`/`if`/`while`/`in` are English.
2. **`python -c "..."` / `bash -c "..."` argument strings** -- contain foreign code with
   `for`/`if`/`import` (e.g. Python dict comprehensions `{k:v for k,v in d.items() if ...}`).
3. **Heredoc bodies and quoted regex args** -- `grep "a\|b"` has a literal `\|`; heredoc
   bodies contain arbitrary code.

Implication for implementation: NEVER decide "control structure -> ASK" (or pipe-split) from
a raw-text keyword/regex scan. Decide it from the PEG parse tree, where quoted strings,
`-c` args, comments, and heredoc bodies are already opaque. A lexical gate would mis-route a
large fraction of linear command sequences to ASK. This is a direct argument for the
grammar-first approach and the heredoc/quote handling below.

## Answer to "does Claude pipe multi-line bash into a shell?"

In this corpus: **no evidence of `echo "...; ..." | bash` or `bash -c "<bash>"`.** The
apparent hits were false positives (`\|bash` inside a grep pattern). What Claude DOES do
heavily is pipe/here-doc into a NON-shell interpreter -- `python3 -c "..."`,
`uv run python - <<'PY'` -- where the payload is Python (data), not bash to decompose.

Latent same-class bypass to note (NOT seen here, decision deferred): `bash -c "git status;
rm -rf /"` embeds sub-commands in a quoted arg the matcher would see as one opaque string --
exactly the multi-line fail-open class, one level down. Flagging for Arnon: handle `-c`
decomposition now, or document as a known limitation and open a follow-up? (Recommend:
document + follow-up unless we find real cases; out of the observed scope.)

## Pipeline recap (agreed)

CRLF->LF -> join `\`+NL (empty) -> remove heredoc bodies (keep introducing line) -> strip
`#` comments (word-boundary, outside quotes) -> collapse whitespace / trim padding -> PEG
parse into statements (NL/`;`) -> pipelines (`|`) -> control-ops (`&&`/`||`) -> simple
commands (recurse subshell/brace/cmd-subst) -> resolve each leaf, strictest-wins;
un-decomposable -> ASK. Path normalization (`/home/arnon`->`~`, `./` prefixing) happens in
the matcher as today; expected-output below shows decomposition PRE path-normalization for
clarity.

---

# Pattern groups and expected matcher input

Legend: **REAL** = verbatim-ish from transcripts (trimmed); **ARTIFICIAL** = constructed to
pin a rule/edge. "Leaves" = the list of sub-commands handed to the matcher; final decision =
strictest across leaves (deny > ask > allow).

## P1 -- linear banner sequence (REAL; dominant, ~64 distinct)

Input:
```
cd /home/arnon/projects/toolguard
echo "=== ruff check test/ ===" && uv run ruff check test/ 2>&1 | tail -3
echo ""
echo "=== green? ===" && uv run python -m unittest test.unit.test_x 2>&1 | grep -E "^(OK|Ran )"
```
Leaves (split on NL, then `&&`, then `|`):
```
cd /home/arnon/projects/toolguard
echo "=== ruff check test/ ==="
uv run ruff check test/ 2>&1
tail -3
echo ""
echo "=== green? ==="
uv run python -m unittest test.unit.test_x 2>&1
grep -E "^(OK|Ran )"
```
Asserts: NL == `;` separator; `echo ""` (empty arg) ok; `&&` and `|` decomposed; banners are
plain `echo` leaves, never re-parsed for their `===`/keyword contents.

## P2 -- the security repro (ARTIFICIAL; must-fix core)

| Input | Leaves | Decision (allow `git status:*`, deny `rm -rf:*`) |
|-------|--------|--------|
| `git status\nrm -rf /` | `['git status','rm -rf /']` | **deny** |
| `git status;\nrm -rf /` | `['git status','rm -rf /']` | **deny** |
| `git status\n\n  rm -rf /\n` (blank/pad) | `['git status','rm -rf /']` | **deny** |
| `git status\r\nrm -rf /` (CRLF) | `['git status','rm -rf /']` | **deny** |
| `git status &&\nrm -rf /` (trailing op) | `['git status','rm -rf /']` (ONE compound) | **deny** |

## H1 -- heredoc into interpreter (REAL; ~most heredocs)

Input:
```
cd /home/arnon/projects/toolguard
uv run python - <<'PY'
import re, pathlib
root = pathlib.Path('.')
def slugs(p): ...
PY
```
Leaves: `['cd /home/arnon/projects/toolguard', 'uv run python - <<'PY'']`
(the heredoc body is removed; the introducing simple command keeps its heredoc redirection;
matches e.g. `uv run python:*`). **Assert: none of `import`, `root = ...`, `def slugs...`
appear as commands.**

## H2 -- heredoc into a pipe (REAL)

Input:
```
cat <<'EOF' | pbcopy
TOO-8 Phase 5: ...
multi-line clipboard text
EOF
```
Leaves: `['cat <<'EOF'', 'pbcopy']` (body removed; pipeline split). Variant seen:
`cat << 'TICKET' | ~/bin/pbcopy`. Assert body lines are not commands.

## H3 -- heredoc mid-sequence (REAL)

Input:
```
cd /home/arnon/projects/toolguard
echo "=== validate JSON blocks ==="
grep -rn "needle" docs/*.md || echo NONE
uv run python - <<'PY'
... python ...
PY
```
Leaves: `['cd ...', 'echo "=== validate JSON blocks ==="', 'grep -rn "needle" docs/*.md',
'echo NONE', 'uv run python - <<'PY'']`. Mix of P1 + heredoc-body-removal; `||` decomposed.

## PS1 -- pipe into `python -c "code"` (REAL; the genuine "pipe-shell")

Input:
```
cat ~/.claude/settings.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d)" 2>/dev/null || echo "no key"
```
Leaves: `['cat ~/.claude/settings.json', 'python3 -c "import json,sys; ...print(d)" 2>/dev/null',
'echo "no key"']`. **Assert: the `-c` Python string is OPAQUE -- its `import`/`for`/`if` are
never parsed as bash.** Matches e.g. `python3 -c:*` / `python3:*`.

## Q1 -- multi-line quoted-string argument (REAL; e.g. `python -c "<multiline>"`)

Input (newline is INSIDE the double-quoted arg):
```
uv run python -c "
from dotenv import load_dotenv
load_dotenv()
print('ok')
"
```
Leaves: `['uv run python -c "<the whole multi-line string>"']` -- a SINGLE command.
**Assert: the embedded Python lines are not split into commands.** Requires the grammar's
quoted-string rules to consume newlines (verify `.` matches NL inside quotes). Same protection
as heredoc, via quoting. (This is the bulk of the ctrl-complex false positives -- they are
really one `python -c "..."` command each.)

## BS1 -- backslash continuation (REAL + Arnon's example)

Input (REAL):
```
# Also check commented-out lines
grep -n "PATTERN" \
  /home/arnon/.zshrc /home/arnon/.bashrc \
  2>/dev/null | sed 's/=.*/=x/'
```
After comment-strip + `\`+NL join (empty):
`grep -n "PATTERN" /home/arnon/.zshrc /home/arnon/.bashrc 2>/dev/null | sed 's/=.*/=x/'`
Leaves: `['grep -n "PATTERN" /home/arnon/.zshrc /home/arnon/.bashrc 2>/dev/null',
"sed 's/=.*/=x/'"]`.

Input (Arnon's, ARTIFICIAL):
```
cd ~/projects; \
ls \
-l \
~/
```
Join -> `cd ~/projects; ls -l ~/` -> Leaves: `['cd ~/projects', 'ls -l ~/']`.
Asserts: empty-join keeps `ls -l` correct (no spurious token split); `;` still separates after
join; trailing `~/` line folded in.

## C1 -- simple for/while loop, linear body (REAL; DECISION NEEDED)

Input:
```
for fn in load_takeover_mode_config _load_permissions; do
  echo "=== $fn ==="
  grep -rn "\b$fn\b" toolguard/ | grep -v "test/"
done
```
PROPOSED (simple tier -> decompose body, validate inner commands; loop var left unexpanded):
Leaves: `['echo "=== $fn ==="', 'grep -rn "\b$fn\b" toolguard/', 'grep -v "test/"']`.
ALTERNATIVE (conservative): whole thing -> **ASK** ("control structure").
Recommendation: decompose non-nested `for`/`while ... do <linear simple cmds> done` (and
`if`, C2) -- these are common in Arnon's real usage; ASK on all loops would be noisy. The
unexpanded `$fn` only risks falling through to ASK on an over-specific allow, which is safe.

## C2 -- simple if-guard (ARTIFICIAL; Arnon's archetype; DECISION NEEDED)

Input: `if grep -q foo file; then cp file file.bak; rm tmp; fi`
PROPOSED (simple tier -> decompose condition + body):
Leaves: `['grep -q foo file', 'cp file file.bak', 'rm tmp']`. Validate all; strictest-wins.
(So a deny on `rm:*` would deny the whole guard.)

## C3 -- complex / nested control -> ASK (REAL; ~8 genuine)

Inputs (both REAL):
```
grep ... | sort -u | while read t; do
  p="${t%%#*}"
  if [ -e "$p" ]; then echo "OK $t"; else echo "MISS $t"; fi
done
```
```
for f in README.md docs/*.md; do
  grep ... | while read -r link; do
    case "$link" in http*) continue;; esac
    ...
  done
done
```
Decision: **ASK** ("complex control structure") -- has `else`/`elif` and/or nesting
(while>if, for>while>case). No decomposition. This is the boundary set by Q1.

## EXTRA edge fixtures (ARTIFICIAL; pin behavior)

- Comment-only / interleaved comment lines are dropped, never commands:
  `# note\nls` -> `['ls']`.
- `#` inside an argument is NOT a comment: `echo http://x#frag` -> `['echo http://x#frag']`.
- Quoted `;`/newline/`|` are not separators: `echo "a; b"` -> `['echo "a; b"']`.
- Process substitution `diff <(sort a) <(sort b)` -> Q8 (PROPOSED **ASK**; revisit -- 0 real
  cases here).
- `bash -c "git status; rm -rf /"` -> latent bypass; PROPOSED: document as known limitation +
  follow-up unless decomposition of `-c` is brought in scope (0 real cases here).

---

## LOCKED FIXTURES (test-ready; config: allow `git status:*`,`cd:*`,`cat:*`,`echo:*`,`grep:*`,`uv run*`; deny `rm -rf:*`)

Decision = strictest across leaves (deny > ask > allow). Path normalization applied by matcher.

| # | Input (NL = newline) | Leaves handed to matcher | Decision |
|---|----------------------|--------------------------|----------|
| F1 | `git status`NL`rm -rf /` | `git status`, `rm -rf /` | deny |
| F2 | `git status;`NL`rm -rf /` | `git status`, `rm -rf /` | deny |
| F3 | `git status &&`NL`rm -rf /` | `git status`, `rm -rf /` (one compound) | deny |
| F4 | `git status\r\nrm -rf /` (CRLF) | `git status`, `rm -rf /` | deny |
| F5 | `\n\n  git status \n` (blank/pad) | `git status` | allow |
| F6 | `cd x`NL`echo "=== a ===" && grep -rn p f`NL`echo ""` | `cd x`,`echo "=== a ==="`,`grep -rn p f`,`echo ""` | allow |
| F7 | `echo "a; b"` (quoted sep) | `echo "a; b"` | allow |
| F8 | `# note`NL`git status` | `git status` (comment dropped) | allow |
| F9 | `echo http://x#frag` | `echo http://x#frag` (# not a comment) | allow |
| F10 | `cd ~/p; \`NL`ls \`NL`-l \`NL`~/` (backslash join) | `cd ~/p`, `ls -l ~/` | (per ls/cd rules) |
| F11 | `uv run python -c "`NL`import os`NL`os.system('x')`NL`"` | `uv run python -c "<multiline>"` (ONE leaf, opaque) | **ask** (inline foreign code floor; even with `uv run*` allowed) |
| F12 | `uv run python - <<'PY'`NL`import os`NL`PY` (heredoc->python) | `uv run python - __HEREDOC_TO_uv__` | **ask** (foreign-exec floor) |
| F13 | `cat <<'EOF' \| pbcopy`NL`text`NL`EOF` | `cat __HEREDOC_TO_pbcopy__`, `pbcopy` | (per cat/pbcopy rules; body NOT parsed) |
| F14 | `cat <<'EOF' \| bash`NL`git status`NL`rm -rf /`NL`EOF` (heredoc->bash) | body decomposed: `git status`, `rm -rf /` | deny |
| F15 | `tee /etc/passwd <<'EOF'`NL`x`NL`EOF` | `tee /etc/passwd __HEREDOC_TO_tee__` | (per tee/Write deny) |
| F16 | `bash -c "git status; rm -rf /"` | inner decomposed: `git status`, `rm -rf /` | deny |
| F17 | `python3 -c "import os; os.system('rm -rf /')"` | `python3 -c "..."` (opaque, foreign) | ask |
| F18 | `cat f \| python3 -c "..." \|\| echo x` | `cat f`, `python3 -c "..."`(ask), `echo x` | ask |
| F19 | `for f in a b; do echo $f; grep $f g; done` (simple loop) | `echo $f`, `grep $f g` | allow |
| F20 | `if grep -q foo f; then cp a b; rm t; fi` (simple if) | `grep -q foo f`, `cp a b`, `rm t` | (per cp/rm rules) |
| F21 | `if [ -f f ]; then cat f; fi` (POSIX test cond) | `cat f` (test `[ -f f ]` is not a command) | allow |
| F22 | `while read l; do if [ -e "$l" ]; then echo ok; else echo no; fi; done` (nested+else) | -- (complex) | **ask** |
| F23 | `diff <(sort a) <(sort b)` (procsub) | -- (undecidable) | **ask** |
| F24 | unparseable garbage w/ NL that can't decompose | -- | ask (or deny per `no_match_fallback`) |

(F11/F17 "allow/ask" assume the stated config; the point is the LEAF SHAPE + opacity, not the
specific verdict. F19/F20 leave the loop/condition vars unexpanded.)

## ROUND 2 -- FULL-CORPUS DATA + RESOLVED DESIGN (2026-06-20)

### Corpus (now includes the recovered Mac transcripts)

Sources combined: featherhill toolguard/checked_bash logs + `~/.claude/projects` +
`~/mac-recovery/dot_files/.claude/projects` (146 transcript files). The missing-transcripts
theory is CONFIRMED -- the old machine's history lives under `~/mac-recovery`.

- **7,767 Bash uses (5,175 distinct).**
- **Multi-line: 262 distinct, 322 weighted (~4.1% overall).** (Note the rate is
  work-dependent: ~29% in dev/analysis-heavy sessions, ~1-2% in routine app work.)
- **94% of distinct multi-line commands (247/262) currently fail to parse and hit the
  whole-blob fail-open path.** This is the exact exposed surface TOO-17 closes -- nearly every
  multi-line command today is undecomposed.

### Hard data on the contested patterns

| Question | Finding |
|----------|---------|
| Heredoc receivers | 120 heredoc cmds. First token: **uv 74** (`uv run python - <<PY`), **cat 39**, **pbcopy 5**, **python3 2**. Heredoc-into-a-SHELL: **~0** (the 3 hits are false positives). => heredocs feed the **Python interpreter** or **cat/pbcopy (data)**; never bash. |
| `-c` inline code | 274 uses. **`<bash-family> -c`: 3 (negligible).** **`<interpreter> -c` (python/node/...): 235.** => `bash -c` essentially unused; `python -c` is the real, common case. |
| pipe into a shell (`\| bash`) | 5 candidates, all `\|sh`/`\|bash` **inside quoted grep patterns** => real `\| bash` ~0. |
| bracket conditionals | real `if [ ... ]`: ~4; **`[[ ... ]]`: 0; `(( ... ))`: 0.** (`if <word>` counts are dominated by English "if" in comments/banners.) |
| process substitution `<(...)` | Confirmed in code: **NOT decomposed today** -- `diff <(sort a) <(sort b)` -> `['diff <(sort a) <(sort b)']`. Inner `sort a`/`sort b` are NOT extracted (a latent fail-open of its own). |

### Executor classification (the core model that resolves H1/H2/H3/PS1/`-c`)

A heredoc body, a `-c` argument, and (potentially) a piped payload are **code for whatever
receives them**. Decide by the RECEIVING command (identified from the parse tree, never by
raw-text scan):

- **Bash-family executor** -- `bash`, `sh`, `dash`, `ksh`, `zsh`: the payload is bash ->
  **re-run it through the same decomposition pipeline** and validate the inner commands
  (closes the same-class bypass). (zsh/ksh differ slightly but are close enough for
  command-level splitting.)
- **Foreign executor** -- non-bash shells (`csh`, `tcsh`, `fish`) and interpreters
  (`python*`, `node`, `perl`, `ruby`, `php`, `Rscript`, `awk`): payload is not bash, cannot be
  validated -> **ASK** ("opaque <lang> code").
- **Non-executor / unknown receiver** -- `cat`, `tee`, `pbcopy`, and anything not in the sets
  above: the heredoc body is **data** -> replace it with a stub and decompose the surrounding
  commands normally. The receiver command itself is still matched against rules, so an
  unknown receiver is gated by its own rule (no fail-open).

Documentation MUST list the bash-family set explicitly (Arnon's decision 3). The sets could
be config knobs later; hardcode for v1.

### RESOLVED expected outputs (supersede the proposals above where they differ)

- **H1 `uv run python - <<'PY' ... PY` -> ASK.** Heredoc feeds the Python interpreter
  (foreign executor); body is opaque code. (Was: stub. Corrected per Arnon.)
- **H2 `cat <<'EOF' | pbcopy` -> decompose with a heredoc STUB carrying the sink.** Leaves:
  `['cat __HEREDOC_TO_pbcopy__', 'pbcopy']` (see "Marker representation" below for the agreed
  all-word-char sentinel and why the sink is folded in).
- **H3 = receiver-dependent.** Mixed linear sequence + a heredoc: if the heredoc is into
  cat/non-executor -> stub + decompose the linear parts; if into Python (the common
  `uv run python - <<PY` case) -> that leaf is ASK, so the whole compound is **ASK**
  (strictest-wins).
- **PS1 `cat f | python3 -c "..." || echo x` -> ASK** (the `python3 -c "..."` leaf is foreign
  inline code -> ASK; strictest-wins makes the compound ASK). The Python string is never
  parsed as bash.
- **`-c`:** `<bash-family> -c "<bash>"` -> decompose the inner string through the pipeline;
  `<interpreter> -c "<code>"` -> ASK. (Real `bash -c` ~0, but the rule is cheap given we
  already parse bash, and it closes the bypass -- IMPLEMENT per Arnon decision 3.)
- **C1 for/while:** non-nested, linear simple-command body -> decompose inner commands; any
  nesting -> ASK. (Confirmed.)
- **C2 if-guard:** non-nested `if <cond>; then <linear cmds>; fi`, no else/elif -> decompose
  the condition + body. **Bracket handling (deep-dive answer):** `[ ... ]`, `[[ ... ]]`,
  `(( ... ))` are TEST constructs, not commands to validate; the ONLY thing inside them that
  executes is command substitution `$(...)`/backticks, which the existing extractor already
  pulls out. So **no special inside-the-bracket inspection is needed** beyond existing
  `$(...)` extraction. Given real usage is only POSIX `[ ... ]` (no `[[ ]]`/`(( ))`), v1
  decomposes `if` only when the condition is a plain command or a `[ ... ]` test; if it uses
  `[[ ]]`/`(( ))` (or else/elif/nesting) -> ASK.
- **C3 complex/nested -> ASK.** (Confirmed.)
- **Process substitution `<(...)` -> ASK** (and note it is a pre-existing fail-open we are
  also closing by routing to ASK). Could extract inner commands in a later ticket.

### Governing principle (document prominently)

**"When in doubt, ASK."** Every construct beyond the simple, common, observed-in-real-use
cases above resolves to ASK -- never to a silent allow of an undecomposed blob, and never to
a hard deny that breaks a legitimate workflow. All limitations (foreign `-c`, heredoc-into-
interpreter, procsub, complex control structures, `bash -c` inner decomposition scope, unknown
heredoc receivers) get documented in `security.md` and `permission-patterns.md`.

### Heredoc sink encoded into the marker (Arnon, 2026-06-20 -- AGREED)

Fold the heredoc's ultimate SINK into the stub marker so a single, orthogonally-evaluated
rule can distinguish executable vs non-executable targets (impossible otherwise -- leaves are
matched independently; we will not manage cross-leaf context).

**Marker representation (Arnon, 2026-06-20): use an all-word-character sentinel** so regex
rules stay clean (no shell-ish `<<`/`->` punctuation to clutter/escape):
**`__HEREDOC_TO_<sink>__`** (replaces the whole `<<DELIM` redirection).
- `<sink>` = basename of the resolved ultimate-pipe consumer; unresolved -> `unknown`.
- Examples: `cat <<EOF | pbcopy` -> `cat __HEREDOC_TO_pbcopy__`; `cat <<EOF | bash` ->
  `cat __HEREDOC_TO_bash__`; `uv run python - <<PY` -> `uv run python - __HEREDOC_TO_uv__`.
- Clean authoring: any heredoc `[regex]__HEREDOC_TO_`; exec sinks
  `[regex]__HEREDOC_TO_(bash|sh|zsh|dash|ksh|python\d*|node|perl|ruby|uv)__` -> ask; data sinks
  `[regex]__HEREDOC_TO_(cat|tee|pbcopy)__` -> allow.
- Caveat: a sink basename can still contain `.`/`-` (`python3.11`) -- same as any command name
  in any rule today; basename minimizes it. Final spelling (`__HEREDOC_TO_` vs alternatives)
  pending Arnon's OK.

- **Sink = ultimate pipe consumer**, resolved by walking the pipeline from the heredoc-bearing
  command to its terminus -- NOT just the next token. So `cat <<EOF | bash` -> sink `bash`
  (executable), `cat <<EOF | pbcopy` -> sink `pbcopy`, `uv run python - <<PY` (no pipe) ->
  sink `uv` (== bearer).
  - `cat <<'EOF' | pbcopy` -> `['cat <<__HEREDOC__->pbcopy', 'pbcopy']`
  - `cat <<'EOF' | bash`   -> `['cat <<__HEREDOC__->bash',   'bash']`
- **Safety invariant:** an executor-sink heredoc must NEVER be blanket-`allow`ed -- that would
  allow an arbitrary unseen body (re-opening the fail-open). For executor sinks the only safe
  verdicts are ask / deny / (future) decompose-the-body. For non-executor sinks, `allow` is
  fine (body is data). Default for an unmatched heredoc-sink leaf = ASK. Ship a recommended
  template: allow non-exec sinks, ask exec sinks (== Arnon's example, now authorable). Document
  that allowing an executor-sink heredoc is a blanket-allow risk.
- This makes the exec/non-exec distinction RULE-DRIVEN (policy in TOML) rather than hardcoded,
  consistent with toolguard's philosophy; the bash-family/foreign/non-exec executor sets are
  still used (to compute the sink class for the shipped template + safety checks) and are
  documented + potentially configurable.

### FINAL CONFIRMATIONS (Arnon, 2026-06-20)

- **Bash-family executor set:** bash, sh, dash, ksh, zsh (exclude csh/tcsh/fish). CONFIRMED.
- **v1 executor scope:** **decompose bash-family payloads** (heredoc body fed to a bash-family
  sink, AND `<bash-family> -c "<bash>"`); **ASK for anything else** (foreign interpreters +
  non-bash shells). CONFIRMED.
- **Marker spelling:** `__HEREDOC_TO_<sink>__` -- APPROVED.

### Unified rule: INLINE foreign-interpreter code -> ASK floor (consistency fix, 2026-06-20)

Foreign-executor code is treated identically whether delivered by heredoc/stdin or by an
inline flag:
- **Bash-family** inline/stdin code (`<bash-family> -c "<bash>"`, heredoc into bash-family) ->
  decompose + validate.
- **Foreign** inline/stdin code -> **ASK floor** (un-downgradable by a plain `allow`):
  `<foreign> -c/-e/-r "<code>"` (python `-c`, node/perl/ruby `-e`, php `-r`), heredoc/stdin
  into a foreign interpreter. So `uv run python -c "..."` -> ask even if `uv run*` is allowed.
- **Named scripts / ordinary args** (`python x.py`, `node app.js`) -> normal opaque matching
  (a `python:*` allow works) -- only INLINE code gets the floor.
Rationale: inline foreign code is unreviewable; a broad runner allow must not silently permit
it. Symmetric with the heredoc exec-sink floor. (Flagged tightening -- consistent + safe.)

### Heredoc leaf representation + the exec-sink ASK floor (resolves the safety invariant)

- The heredoc leaf KEEPS the bearer command and its other args, replacing only the `<<DELIM`
  redirection with the sentinel -- because the bearer's args can themselves be dangerous
  (`tee /etc/passwd <<EOF` -> `tee /etc/passwd __HEREDOC_TO_tee__`; a `Write(/etc/passwd)`-class
  / `tee` deny must still catch it). We do NOT collapse to a bare sentinel.
- Consequence + fix: a broad receiver allow (`allow = cat:*`) would otherwise match
  `cat __HEREDOC_TO_python3__` and re-open the fail-open. So **a FOREIGN-executor-sink heredoc
  gets an ASK floor**: its resolved verdict is clamped to at most ASK (deny -> deny;
  allow/no-match -> ASK). A plain allow cannot downgrade it; an explicit deny still applies.
- Asymmetry (clean):
    - **bash-family sink** -> body decomposed + validated; NO sentinel leaf emitted.
    - **foreign-exec sink** (python/node/csh/fish/...) -> `bearer __HEREDOC_TO_<sink>__` leaf,
      ASK floor.
    - **non-exec sink** (cat/tee/pbcopy/unknown) -> `bearer __HEREDOC_TO_<sink>__` leaf, normal
      matching (a normal allow is fine -- body is data).
- The marker still buys: log visibility of the sink, explicit per-sink deny, and clean regex
  authoring; the ASK floor guarantees no fail-open regardless of broad allows.
