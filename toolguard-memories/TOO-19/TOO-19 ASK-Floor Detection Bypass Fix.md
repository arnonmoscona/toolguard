---
title: TOO-19 ASK-Floor Detection Bypass Fix
type: note
permalink: toolguard/too-19/too-19-ask-floor-detection-bypass-fix
tags: [TOO-19, task-memory, security]
---

# TOO-19: ASK-Floor Detection Bypass Fix

## Summary

Fixed a security-control bypass in `_detect_foreign_inline_code`
(`toolguard/parser/command_extractor.py`). This function decides whether a leaf
command gets `ask_floor=True` -- the control that forces human review of
foreign (non-bash) inline code such as `python -c "..."`. It previously
inspected only the single token immediately after the executor and required
an exact string match, so an intervening flag (`python -u -c "..."`) or an
attached/bundled flag (`python -cimport os`, `python -uc "..."`) silently
bypassed the ASK floor with a plain `allow`/no prompt at all. Confirmed
real-world impact: this repo's own live config allows `Bash(uv run *)`, so
`uv run python -u -c "<anything>"` resolved to a silent allow while
`uv run python -c "..."` was correctly ask-floored.

`_detect_foreign_inline_code` had zero direct test coverage before this
ticket.

## Files changed

- `toolguard/parser/command_extractor.py` -- the fix. Added
  `INLINE_FLAG_TOKEN_RE` (moved from `compound.py`, see below) and a new
  `_scan_for_inline_flag` helper; rewrote `_detect_foreign_inline_code` to
  use it.
- `toolguard/compound.py` -- now imports `INLINE_FLAG_TOKEN_RE` from
  `command_extractor.py` instead of keeping its own byte-identical copy of
  the regex (removed the now-dead `import re`, which had no other use in
  this module).
- `test/unit/test_command_extractor_inline_code.py` (new) -- 25
  characterization/regression tests calling `_detect_foreign_inline_code`
  directly.

No other files were touched. No live configuration
(`.claude/toolguard_hook.toml`, `.claude/settings*.json`, `~/.toolguard/`,
`~/.config/toolguard/`, `~/.claude/`) was created, edited, deleted, or
moved. No ad-hoc `python -c` / heredoc probes were run at any point --
all validation was via `uv run python -m unittest`. No write git operations
were run.

## Task 1: characterization tests -- before-fix pass/fail inventory

25 tests were written first and run against the *unmodified* code to
verify the ticket's bug analysis before touching any production code.
Result, exactly as the ticket predicted:

**Already passing before the fix (14 tests -- these were never broken):**
- All 7 "already works" positive forms: `python -c`, `python3 -c`, `node -e`,
  `perl -e`, `ruby -e`, `php -r`, `Rscript -e`.
- `uv run python -c "x"` (executor not in token 0).
- All 5 negative/guard cases: `python script.py`,
  `python script.py -c foo`, `python -m mymod -c foo`, `ls -c`,
  `git commit -m "x"`.
- The `-X dev` known-limitation test (see below) -- it asserts `False`,
  which was already the (buggy, but in this one instance "accidentally
  correct in direction") behaviour pre-fix.

**Failing before the fix (11 tests -- confirmed real bypasses, matching the
ticket's list exactly):**
- `python -u -c`, `python -B -c`, `python -I -c`, `python3 -O -c` (intervening
  single-letter/word flag)
- `node --experimental-vm-modules -e` (intervening long flag)
- `perl -w -e`, `ruby -w -e` (intervening flag)
- `python -cimport os` (attached, no separator)
- `python -c'import os'` (attached via quote)
- `python -uc "code"` (bundled short flags)
- `uv run python -u -c "..."` (the real-world `uv run` case)

This matches the ticket's bug list one-for-one, with one exception flagged
below (`-X dev`).

## Task 2: the fix

`_scan_for_inline_flag(remaining, inline_flags)` scans the tokens after the
executor:
- An exact match against `inline_flags` (e.g. `-c`) -> `True`.
- A token starting with `-` that is not an exact match is checked against
  `INLINE_FLAG_TOKEN_RE` for a bundled/attached inline letter (`c`/`e`/`r`)
  -> `True` if it matches; otherwise scanning **continues** (it's just some
  other flag, e.g. `-u`, `-B`, `--experimental-vm-modules`).
- The **first token that does not start with `-`** stops the scan and
  returns `False` -- it's a script path, module name, or similar, and
  everything after it belongs to that context, not to the interpreter.

This is exactly the rule described in the ticket, including the `-m`
handling ("`python -m mymod -c foo` stays `False` because `mymod` is a
non-flag token that ends the scan").

### Regex reuse (per Task 2 instructions)

`toolguard/compound.py`'s `_extract_outer_command` (landed earlier this
session) already had an identical
`_INLINE_FLAG_TOKEN_RE = re.compile(r"^-([a-zA-Z]{0,2})([cer])(.*)$")` for
recognizing bundled/attached `-c`/`-e`/`-r` flags. Rather than write a
second, divergent copy, I moved the single definition into
`command_extractor.py` (as `INLINE_FLAG_TOKEN_RE`, no leading underscore
since it's now imported across module boundaries) and had `compound.py`
import it from there. This direction avoids a circular import:
`compound.py` already imports from `command_extractor.py`
(`extract_commands`), never the reverse. `compound.py`'s own `re` import
became unused as a result and was removed.

### KNOWN LIMITATION found during Task 1 verification: `python -X dev -c`

The ticket lists `python -X dev -c "..."` as a confirmed bypass alongside
the single-token intervening flags. Under the fix design mandated by the
ticket itself (stop scanning at the first non-flag token, with `-m
mymod` as the explicit example of why that's correct), `-X dev` is
**structurally identical** to `-m mymod`: both are a flag followed by its
value in a **separate, non-flag token**. The rule that correctly keeps
`python -m mymod -c foo` at `False` (module argument ends the interpreter's
option list) necessarily also keeps `python -X dev -c "..."` at `False`
(the `-X` value `dev` looks exactly like a non-flag argument).

Distinguishing "`-X`'s value doesn't change context, keep scanning" from
"`-m`'s value does change context, stop scanning" requires a per-executor,
per-flag table of which flags consume a following value-token without
ending the option list (`-X` for python; similarly `-W` for perl, various
gawk long-opts, etc.). That is a materially different, more invasive kind
of fix (a flag-arity table, not a simple stop-scanning rule) and risks the
exact "hand-rolled, overly-clever parsing" anti-pattern this project's
CLAUDE.md explicitly warns against. I judged it out of scope for this fix
and did **not** implement it.

I added a dedicated test,
`test_python_dash_capital_x_dev_dash_c_KNOWN_LIMITATION`, asserting the
current (still-`False`) result with a comment explaining why, so this is a
documented, intentional gap rather than a silently-reintroduced bypass.
**This is flagged for you to decide**: leave as documented residual risk,
or open a follow-up ticket for a flag-arity table if `-X`/`-W`-style
flags are judged worth the added complexity.

## Task 3: the `awk` `-f` entry -- investigated, NOT changed

Per the ticket, I did not change `_FOREIGN_INLINE_FLAGS["awk"] = ["-f"]`.
Investigation (via `man awk` / `gawk --help`) confirms the suspicion in
both directions:

- `-f program-file` (`--file` in gawk) reads the AWK program text **from a
  file**, e.g. `awk -f script.awk data.txt`. It is not inline code -- it
  points at a script file, more analogous to `bash script.sh` than to
  `bash -c "..."`. Flagging this as "foreign inline code" ask-floors a
  file-based invocation that arguably doesn't belong under this specific
  control at all (it may still deserve scrutiny, just not via this
  mechanism/label).
- The actual common inline form is **no flag at all**: `awk '{print $1}'
  file` -- the program text is a bare (usually quoted) positional
  argument. The current mapping cannot detect this case under any
  token-scanning scheme, because there's no flag to scan for.

**Recommendation**: either (a) drop the `awk` entry from
`_FOREIGN_INLINE_FLAGS` entirely and instead detect the bare-first-argument
form structurally (first non-`-`-prefixed token after `awk`/`gawk`, when
there is no `-f`), or (b) keep `-f` but reclassify it as a "reads a script
file" case handled the same way `bash script.sh` is (path-based review, not
inline-code ASK floor), and add separate handling for the bare-argument
case. Both are behavior changes for a very commonly used command family
and deserve their own decision/ticket -- not folded into this fix.

## New commands that will NEWLY be ask-floored

As a direct result of this fix, any command matching a `FOREIGN_EXECUTORS`
member with an inline-code flag preceded by other short/long flags, or with
an attached/bundled inline flag, will now hit the ASK floor where it
previously slipped through as a silent allow/no-prompt. Concretely, for
users whose config allows a broad prefix like `Bash(uv run *)` or
`Bash(python*)`:

- `python -u -c "..."`, `python -B -c "..."`, `python -I -c "..."`,
  `python3 -O -c "..."`, and any other single-token flag before `-c`
  (e.g. `-S`, `-E`, `-s`) for python/python3.
- `node --experimental-vm-modules -e "..."` and similar node long-flags
  before `-e`.
- `perl -w -e "..."`, `ruby -w -e "..."` and similar single-letter flags
  before `-e`.
- `python -cimport os`, `python -c'import os'` (attached, no separator).
- `python -uc "..."` and other bundled short-flag forms ending in `c`/`e`/`r`.
- The `uv run` variants of all of the above (e.g.
  `uv run python -u -c "..."`).
- `awk`/`gawk` invocations where a flag other than `-f` (but ending in one
  of the letters `c`/`e`/`r`, per the shared bundled-flag regex -- an
  incidental, not deliberately targeted, side effect) precedes `-f` in a
  single fused token; this is a minor, expected side effect of reusing the
  general scanning algorithm and does not change the `awk` mapping itself.
  Ordinary `awk -f script.awk file` behaviour (flag as the very first
  remaining token) is unchanged.

**NOT newly ask-floored**: `python -X dev -c "..."` (see Known Limitation
above) and `python -m mymod -c foo` (correctly stays `False`, unchanged).

## Self-review / anti-pattern scan

- No `async`/`await`, no `threading`/`Thread` introduced.
- No new local (in-function) imports. The one pre-existing local import in
  `command_extractor.py` (`multiline.extract_structured`, with
  `# noqa: PLC0415`, a documented circular-dependency exception) is
  untouched by this change.
- Doc comments present on every new/changed function
  (`_scan_for_inline_flag`, `_detect_foreign_inline_code`,
  `INLINE_FLAG_TOKEN_RE`).
- `uv run ruff format toolguard/parser/command_extractor.py
  toolguard/compound.py test/unit/test_command_extractor_inline_code.py` --
  3 files left unchanged (already formatted).
- `uv run ruff check .` -- all checks passed.
- `uv run python -m py_compile` on all three touched files -- clean.

## Test results

- Baseline (before any change): `uv run python -m unittest discover -s test
  -t .` -- **1811 tests, OK**.
- After the fix + new test file: **1836 tests, OK** (1811 + 25 new).
- New test file alone
  (`test.unit.test_command_extractor_inline_code`): 25/25 passing
  (14 baseline/negative + 11 bypass-now-fixed).

## Grep sweep for stale references

Searched the whole repo for `_INLINE_FLAG_TOKEN_RE` / `INLINE_FLAG_TOKEN_RE`
after the move: exactly the two expected definitions/usages remain (the
canonical one in `command_extractor.py`, and the import + usage in
`compound.py`). No other stale copies or references found.

## Nested-directory check

Verified no `toolguard-memories/toolguard-memories/...` directory was
created by this task: this report was written directly to
`toolguard-memories/TOO-19/TOO-19 ASK-Floor Detection Bypass Fix.md` via
the filesystem Write tool (not a basic-memory MCP call with a directory
parameter), and `ls toolguard-memories/TOO-19/` shows no such nesting from
this session. (Pre-existing nested-directory artifacts from earlier
sessions in this ticket, visible in `git status`, are unrelated to this
task and were not touched.)
