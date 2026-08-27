---
title: review-78-round5
type: note
permalink: toolguard/too-45/reports/review-78-round5
---

# Review 78 — round 5 (final gate before commit)

**FAIL — 2 blocking, 8 non-blocking.**

Scope: `git diff` restricted to `toolguard/normalization.py`, `toolguard/permissions.py`, `toolguard/path_utils.py`, `toolguard/ambient.py` (no changes), `test/unit/test_normalization.py`, `test/unit/test_permissions.py`, `test/unit/test_ask_resolution.py`, `test/unit/test_ambient.py` (no changes), `docs/permission-patterns.md`, `docs/architecture-as-built.md`. 8 files carried changes, 882 insertions.

Suite: `Ran 3785 tests ... OK (expected failures=4)`, exit 0. No flake seen. `ruff check` clean, `ruff format --check` clean, `tools/architecture_fitness.py --ambient` PASS. `~/.toolguard/errors/` held **1950** entries at start and 1950 at end, so nothing I ran crashed the hook.

Everything below was measured by execution against real `bash` and the real matcher, not read.

---

## What is correct — stated so the clean results are on the record

These were verified, not assumed:

- **All four Bash pattern types see the tilde spelling.** DEFAULT, `[glob]`, `[regex]` and `[native]` each deny `cat ~/.ssh/id_rsa` against a rule written with the absolute path. The defect this project has shipped before (feeding `_command_variants` to DEFAULT alone) is **not** present: the expansion is added in `match_command`'s own `spellings` loop, above the pattern-type dispatch.
- **Read, Write and Edit** each deny `~/.ssh/id_rsa` against an absolute rule. `file_matching.py` reaches the same `expand_tilde`, so `~name` works there too without a change to that file.
- **`~<name>` matches the shell exactly.** With `LOGNAME=root USER=root` bound and a *different* HOME bound, `~root` → `/root`, `~` → the bound HOME, `~nosuchuser` → unchanged. `$USER`/`$LOGNAME` do not influence `~<name>`; only `pw_dir` does. This reproduces the brief's `bash` reference output term for term.
- **Non-throwing on every path.** 16 hostile tokens (embedded NUL, lone surrogate, 5000-char name, 300-digit fd, `>`×200, empty string, `~\x10FFFF`) × 2 entry points = **0 exceptions**. `UnicodeEncodeError` from `getpwnam` is a `ValueError` subclass and is caught by the existing handler. An unresolvable home returns the path unchanged rather than raising.
- **No over-expansion in any redirect position.** Across 22 redirect spellings compared against real `bash`, there is no form where the new code expands a `~` that `bash` leaves alone. The dangerous direction is clean. Quoted (`>'~/x'`, `>"~/x"`) and escaped (`>\~/x`) operands are correctly left alone.
- **The one-directional design is stated accurately, not as symmetry.** `docs/permission-patterns.md` says the reverse direction is "a DEFAULT accommodation, with one `[glob]` exception". Measured: tilde-rule vs absolute-command gives deny under DEFAULT, deny under `[glob]` *only when the pattern begins with `~`*, and allow under `[regex]`/`[native]`. The prose matches the code. **I found no symmetry claim anywhere in the diff.**
- **The `**/<component>/**` claim in `architecture-as-built.md` is true**: `cat ~/x` matches `**/home/**`; bare `~/x` does not, because the command name is not searched.
- **Tests are machine-independent.** Every new test patches `pwd.getpwnam` with a stub directory and binds `ambient.AmbientFacts`. They behave identically with no `arnon` account and as root. (`test_path_utils.py:48` compares against `Path.expanduser()` on both sides, so it is self-consistent anywhere — and it is outside this diff.)
- **No test is weaker than its docstring in a way that would survive a revert.** I specifically checked `test_an_allow_rule_reaches_it_on_the_same_terms`, which asserts `"allow"`: `check_permission` fails closed to `"deny"` when nothing matches, so reverting the expansion fails the test. It is a real assertion, not a fallback artifact.
- **No claim about Claude Code's native permission syntax is introduced by this diff.** The `[native]` references describe toolguard's own pattern type. I fetched `https://code.claude.com/docs/en/permissions.md` on 2026-08-20 anyway, per `.claude/rules/native-fidelity-claims.md` — see B2 and N7, which came out of that fetch.

---

## Blocking

### B1 — `dd if=~/.ssh/id_rsa` walks past an absolute deny rule; same class as the bug this ticket exists to close

`bash` tilde-expands an assignment-style word — a `~` immediately after `=`, or after a `:` inside such a word. `expand_tilde_in_command` only expands a `~` at token offset 0 or after a token-leading redirect operator, so it does not.

Measured against real `bash`:

| word | bash | toolguard |
|---|---|---|
| `if=~/probe` | expands | **no** |
| `of=~/probe` | expands | **no** |
| `foo=~/probe` | expands | **no** |
| `PATHV=a:~/probe` | expands | **no** |
| `--file=~/probe` | literal | literal (agree) |

End-to-end, with deny `Bash(*<home>/.ssh/*)` and allow `Bash(*)`:

```
dd if=<home>/.ssh/id_rsa   -> deny     (rule shape is fine)
dd if=~/.ssh/id_rsa        -> allow    <<< walks past the deny
cat ~/.ssh/id_rsa          -> deny     (the shape the ticket fixed)
tar -cf /tmp/o.tar file=~/.ssh/id_rsa -> allow
```

And `bash -c 'dd if=~/.ssh/id_rsa'` with a seeded temp HOME returns `PRIVATE-KEY-MATERIAL` — the file really is read.

This is the identical failure mode to `>~/.ssh/x`, which round B1 fixed *because* it walked past an absolute deny rule. The reason `>~` was closed and `if=~` was not is not a principled one; both are positions where the shell expands. `permission-patterns.md` does say "a `~` that does not start a token ... [is] left as written", so the *behaviour* is documented — but nowhere is it identified as a deny bypass, and no proposed ticket covers it (77 is a *leading* env assignment, 82 is `sudo`/`env`, 83 is the reverse direction for file paths).

Resolution can be code or paperwork — file it and say so in the docs — but it should not ship as an unrecorded hole in the ticket's own subject area.

### B2 — the change moves a `~` redirect target from `ask` to `allow`, on the one shape native singles out for approval

`https://code.claude.com/docs/en/permissions.md`, fetched **2026-08-20**, "Redirections" (line 241), verbatim:

> "Claude Code checks the target of an output redirection, such as `>`, `>>`, or `2>`, as a file write. The check covers your `Edit` allow and deny rules, protected paths, and the working directories. A rule such as `Bash(git commit *)` allows the command, not the target. A `/dev/null` target isn't checked. **A target that starts with `~` or contains a glob character needs approval.**"

Measured before/after, where "before" re-runs each case with `expand_tilde_in_command` patched to identity:

| case | after | before |
|---|---|---|
| absolute ALLOW rule vs `echo hi >~/notes.txt` | **allow** | ask |
| absolute ALLOW rule vs `echo hi > ~/notes.txt` | **allow** | ask |
| absolute DENY rule vs `echo hi >~/.ssh/ak` | deny | allow (the intended fix) |

The deny row is the fix working. The two allow rows are a **loosening introduced by this change**: a `~`-targeted redirect that previously prompted is now auto-approved, on precisely the shape upstream gates by design.

Offering the expansion to `allow` is a deliberate, documented decision, and its stated justification ("expanding `~` discards nothing — the two spellings name one file") is sound in general. But the redirect-target interaction was not weighed against native's rule, and the ask→allow transition is recorded nowhere. This needs an explicit decision from the owner rather than arriving as a side effect. Accepting it and documenting it is a fine outcome; shipping it unnoticed is not.

---

## Non-blocking

**N1 — `>&~/x`: bash expands, `_REDIRECT_PREFIX_RE` does not, and ticket 87 does not list it.** `bash -c 'true >&~/probe'` creates `$HOME/probe`; the regex consumes only the `>` and leaves the remainder `&~/probe`, which does not begin with `~`. Harmless **today** because the PEG grammar also rejects `>&` and the command lands on `ask` — I verified `echo hi >&~/.ssh/ak` → `ask`. The trap is that ticket 87 enumerates `&>`, `&>>`, `>|`, `<>` and **omits `>&`**; if 87 adds grammar support without adding `>&` to this regex, a fail-closed gap silently becomes a live bypass. Worth adding to 87's list either way.

**N2 — `docs/permission-patterns.md` says every listed operator takes an fd number; two do not.** "Recognized operators: `>`, `>>`, `<`, `<>`, `>|`, `&>`, `&>>`, **each** optionally preceded by a file-descriptor number". Measured: `2&>~/x` and `2&>>~/x` are not expanded. The **code is right** and `bash` agrees (`2&>` is not an fd-prefixed redirect), and the module comment says so explicitly — "`&>` `&>>` (no fd digits -- bash doesn't allow one there)". So the shipped doc directly contradicts the comment on the same behaviour. Fix the doc, not the code. *Note: the review brief repeats the doc's version of this claim; where they conflict, the code and `bash` are right.*

**N3 — the `<<<` rationale is factually false in the module comment and in a test docstring.** Both call the here-string operand "literal here-string content". `bash -c 'cat <<<~/probe'` prints the expanded home path — an unquoted here-string **is** tilde-expanded. The load-bearing half of the claim ("never a path the shell opens") is true, and skipping it is correct, so behaviour is unaffected. Drop the word "literal": `normalization.py` `_REDIRECT_PREFIX_RE` comment, and `test_a_herestring_starting_with_tilde_is_left_alone`.

**N4 — "Deliberately excludes `<<` and `<<<`" describes a mechanism the regex does not contain.** There is no `<<` exclusion. For `<<~EOF` the regex consumes a single `<`, leaving `<~EOF`, which does not start with `~`; for `<<<~/x` it leaves `<<~/x`. The right answer falls out of the alternation, it is not designed in. Both cases are pinned by tests, so this is a comment-accuracy issue — but "deliberately excludes" invites a future editor to believe a guard exists.

**N5 — this change worsens the repo's highest-risk function.** `pyscn`, current tree vs `HEAD`:

| function | CC before | CC after | cognitive before | cognitive after |
|---|---|---|---|---|
| `match_command` | 21 | **24** | 73 | **79** |
| `normalize_path` | 13 | 13 | 28 | 28 |

`match_command` is now CC 24 / cognitive 79 / nesting depth 7 across 133 lines, against `.pyscn.toml`'s `medium_threshold = 19` (it was already over). `max_complexity = 0`, so nothing fails — this is judgement, not a gate. The new nested `for spelling / for variant / if not in` block is a self-contained pure computation; extracting it as `_spellings_to_match(command_str, also_spelled) -> List[str]` would take roughly 4 off CC, remove a nesting level from the most security-critical matcher in the package, and be directly unit-testable. Worth doing while the code is fresh.

**N6 — stray untracked file `~x` in the repo root, not gitignored.** `/home/arnon/projects/toolguard/~x`, 4 bytes, contents `foo`, dated 12:36 today. It is debris from a redirect probe in an earlier round where `~x` did not expand and `bash` created the literal filename. `git check-ignore` does not match it, so `git add -A` would commit it. Delete before staging. (Reported, not removed — I make no writes to the repo.)

**N7 — `[native]` now applies command-side tilde expansion, which is a deviation from native, undated.** Per the fetch above (2026-08-20), the published doc documents `~/path` expansion for **Read/Edit/Cd path patterns** (line 284) and describes Bash rule matching in terms of wrapper and leading-assignment stripping with no tilde expansion of commands. toolguard's new `NATIVE | ... | Per-token tilde expansion` row is therefore a deliberate divergence. `.claude/rules/native-fidelity-claims.md` asks that `[native]` fidelity be scoped with a date; the new table presents the behaviour without noting it departs from native. One clause would settle it.

**N8 — `docs/architecture-as-built.md` bundles unrelated work.** 13 of its ~15 changed hunks convert `![alt](x.png)` to `<img ... width="50%">`, which has nothing to do with ticket 78. The two substantive hunks (the pattern-dispatch bullets and the `ambient` row in the foundation layer, which correctly tracks the `.pyscn.toml` change) are the ticket's. Cosmetic, but it makes the commit harder to read and to revert.

---

## Method notes

- Redirect behaviour was established by running each spelling under real `bash` with a temp `HOME` and a directory literally named `~` in cwd, so both the expanded and the unexpanded target were writable, and observing which file appeared; read-style redirects used two pre-seeded files with distinct contents.
- Permission outcomes used `toolguard.testing.sandbox.experiment()` with `sb.home` interpolated and a leading `*` on deny patterns, per the brief.
- Before/after comparisons patched `toolguard.permissions.expand_tilde_in_command` to identity rather than touching git. **No git write command was run at any point.** `git show HEAD:<path>` (read-only) supplied the baseline files for the complexity comparison.

Scratch artifacts: `/tmp/claude-1000/-home-arnon-projects-toolguard/19b5a95c-bf5a-4909-8a27-d628237d87a9/scratchpad/` (`redirect_oracle.py`, `oracle2.py`, `oracle3.py`, `e2e.py`, `e2e2.py`, `docclaims.py`, `confirm.py`, `native_redirect.py`).

Elapsed ~31 minutes; ~$4 at Opus rates. 8 changed files reviewed. 2 blocking, 8 non-blocking.