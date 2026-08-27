---
title: review-78-round3
type: note
permalink: toolguard/too-45/reports/review-78-round3
---

# Review 78 — round 3 (blinded)

**VERDICT: FAIL — 3 blocking items.**

Scope: uncommitted diffs of `toolguard/ambient.py`, `toolguard/normalization.py`, `toolguard/permissions.py`, `toolguard/path_utils.py`, `test/unit/test_ambient.py`, `test/unit/test_normalization.py`, `test/unit/test_permissions.py`, `docs/permission-patterns.md`, `docs/architecture-as-built.md`. `README.md`, `llms.txt`, `docs/config-sync.md`, `docs/install.md` excluded per brief.

Blocking: 3. Non-blocking: 11.

Everything below was executed, not read. Full suite green: `Ran 3769 tests ... OK (expected failures=4)`. `ruff format --check` and `ruff check` clean.

---

## What the change gets right (measured, not assumed)

These are findings, not the absence of findings.

**The passwd lookup is provably non-throwing.** 38 hostile inputs through `expand_tilde` — unknown name, empty name, embedded NUL, embedded `/`, a 100 000-character name, lone surrogates, `~.`/`~..`/`~-`/`~+`, `~$USER`, `~\t` — produced zero escaping exceptions. Cross-checked against the CPython 3.14.0 `Modules/pwdmodule.c` source (fetched, not recalled): `pwd_getpwnam_impl` has exactly three error exits — `UnicodeEncodeError` and `ValueError` from the encode/embedded-null checks, and `KeyError` for every not-found case *including* an NSS failure (`status != 0` sets `p = NULL`, which falls into the same `PyErr_Format(PyExc_KeyError, ...)` branch). There is no `OSError` route. `except KeyError, ValueError` is therefore complete, not merely adequate. The only uncaught exit is `PyErr_NoMemory`, which is not worth guarding.

**`~<name>` matches a shell exactly, and ignores `$USER`/`$LOGNAME`/`$HOME`.** Run under `USER=root LOGNAME=root HOME=/tmp/fakehome`, toolguard and `bash -c 'echo ...'` agreed on all four probes: `~` → `/tmp/fakehome` (both), `~root` → `/root` (both), `~arnon` → `/home/arnon` (both), `~nosuchuser` → literal (both). The environment governs bare `~` only, via `ambient.home()`; `~<name>` goes to `pwd.getpwnam` and nothing else.

**The ticket's headline case is closed end-to-end, through the real hook process.** Temp project, deny rules spelled with absolute home paths, nine spellings driven through `python -m toolguard.hook`:

```
  deny  cat ~/.ssh/id_rsa
  deny  cat ~arnon/.ssh/id_rsa
  deny  cat /home/arnon/.ssh/id_rsa
  deny  sed -n 1p ~/.ssh/id_rsa            <- [regex] rule
  deny  sed -n 1p ~arnon/.ssh/id_rsa       <- [regex] rule
 allow  cat ~/.ssh/known_hosts             <- correct: different file
 allow  cat ~root/.ssh/id_rsa              <- correct: different file
 allow  cat "~/.ssh/id_rsa"                <- correct: bash does not expand a quoted tilde
```

**The tests are load-bearing.** Mutation-tested in process: neutering `expand_tilde_in_command` fails 16 of 30 new tests; neutering `_expand_named_user` fails 8. No new test survives its own production code being reverted — with the single exception that is blocking finding 2.

**No prose in the diff asserts anything about Claude Code's native permission semantics.** Checked against `https://code.claude.com/docs/en/permissions.md`, fetched. The page's only tilde statements are rule-side path anchors for `Read`/`Edit` (`` `~/path` | Path from home directory | `Read(~/Documents/*.pdf)` | `/Users/alice/Documents/*.pdf` ``) and one redirection rule (`A target that starts with ~ or contains a glob character needs approval`). Neither is contradicted by the diff, and the diff makes no claim about native Bash-command tilde handling. Standing requirement satisfied with nothing to report.

**The one-directional scope is stated honestly.** `docs/permission-patterns.md` says outright that the reverse direction is a DEFAULT accommodation with a single `[glob]` exception, and that `[regex]`/`[native]` get nothing. No symmetry claim anywhere in the diff. Verified by execution: `~`-spelled rule vs absolutely-spelled command gives DEFAULT `True`, `[glob]cat ~/.ssh/*` `False`, `[regex]` `False`, `[native]` `False`.

---

## BLOCKING

### B1 — `toolguard/permissions.py:179-181`: the comment's "the one route" is false, and a test in the same diff refutes it

```python
    # The GLOB branch of match_pattern expands '~' too, but only at the very start of
    # each side: this subsumes its command side, and leaves its pattern side as the
    # one route by which a '~'-spelled rule reaches an absolutely-spelled command.
```

The first two clauses are true — I verified `expand_tilde_in_command` strictly subsumes the GLOB branch's `expand_tilde(command)` (the tokenized form also handles a leading-whitespace command, which the whole-string form does not). The third is false as written.

A DEFAULT `~`-spelled rule reaches an absolutely-spelled command perfectly well, through the home-collapsing normalized variant:

```
match_command("cat /home/testuser/.ssh/id_rsa", ["cat ~/.ssh/id_rsa"])  ->  True
```

That is not an incidental behaviour — it is asserted by `test_a_tilde_spelled_rule_still_fires_on_the_absolute_spelling`, added by this same diff, roughly 650 lines away. `docs/architecture-as-built.md:437` states it correctly with the qualifier ("the one route **among the three**"); the code comment dropped the qualifier and thereby inverted the claim. A reader who trusts it will conclude a `~`-spelled DEFAULT deny does not cover the absolute spelling and go rewrite rules that were already correct.

Fix: add the three-word qualifier the doc already has.

### B2 — `toolguard/permissions.py:120`: the added variant is a no-op, and its docstring claims the opposite

```python
    variants = [command_str]
    for variant in (
        normalize_path_in_command(command_str, resolve_symlinks=False),
        normalize_path_in_command(command_str),
        expand_tilde_in_command(command_str),      # <- this line
    ):
```

`_command_variants` has exactly one caller, `match_command`, which by then has already closed `spellings` under `expand_tilde_in_command` and calls `_command_variants` once per spelling. Since the expansion is idempotent (its output tokens start with `/`), every value this line can produce is already in the list. Two independent measurements:

- Neutralizing **only** this line — leaving `match_command`'s expansion intact — leaves all 30 new tests green (`variants_only -> ran 30 | failures+errors 0`). Neutralizing `expand_tilde_in_command` everywhere fails 16. So this line is the one part of the change that nothing tests, because there is nothing to test.
- The `command_variants` list `match_command` builds is byte-identical with and without the line across a 12-command corpus (`~`, `~name`, `~nosuch`, `~~`, `~/`, leading-`~` command names, `also_spelled` combinations, quoted tildes): **0 cases differ**.

The docstring at lines 105-114 justifies it: *"Each is a spelling a rule author plausibly wrote, so all are kept: dropping one silently narrows every deny rule written in it."* For this entry that is demonstrably false — dropping it narrows nothing. `docs/architecture-as-built.md:432` then repeats the framing to users as one of "four deduplicated spellings".

This matters beyond tidiness: the expansion now has two owners, and a future edit to either site will look load-bearing while only one is. Fix: delete the line, revert the `_command_variants` docstring to the three real variants, and let `match_command` own the expansion — ideally in an extracted `_spellings(command_str, also_spelled)` helper, which also addresses NB5.

### B3 — `docs/permission-patterns.md:177`: the rewritten symlink row is false for relative paths

```
| Symlink resolution | A link, or any symlinked ancestor directory, is replaced by its target -- including a dangling one |
```

This replaced a genuinely wrong claim ("Up to 3 iterations to prevent loops"), which is the right instinct — but the replacement introduces a narrower falsehood in the word **any**. `_involves_a_symlink` deliberately does not examine a relative path's ancestors; its own docstring says so ("The ancestors of a RELATIVE path are deliberately not examined"). Measured on a constructed tree:

```
  abs  <tmp>/link          -> <tmp>/real/f.txt     (resolved)
  abs  <tmp>/linkdir/f.txt -> <tmp>/real/f.txt     (ancestor resolved)
  abs  <tmp>/dangling      -> <tmp>/nowhere        (dangling resolved)
  rel  link                -> <tmp>/real/f.txt     (resolved)
  rel  linkdir/f.txt       -> ./linkdir/f.txt      (ancestor NOT resolved)
  rel  dangling            -> <tmp>/nowhere        (resolved)
```

A user reading this row will believe `cat linkdir/secret` is normalized to its target and therefore covered by a rule naming the target. It is not. Security-relevant in a user-facing permissions doc.

This is the failure mode the global CLAUDE.md names explicitly — compression producing a false universal. Fix: `A link is replaced by its target, including a dangling one; a symlinked ancestor directory is followed too, but only for an absolute path.`

---

## NON-BLOCKING (11)

**NB1 — `toolguard/ambient.py`: the entire diff is whitespace.** `git diff --word-diff=porcelain` on this file returns **nothing** — the 4-added/3-removed lines are a docstring re-wrapped with zero wording change. 100% prose churn, 0% code. It has no business in a tilde-expansion change; it costs a reviewer a file open and buys nothing.

**NB2 — `test/unit/test_ambient.py`: same.** The whole diff explodes `_AMBIENT_READS` from one line to six, with the same six names in the same order. A magic trailing comma forced it (the one-line form is 74 chars, well under the 88 limit, so `ruff format` would not have). Pure noise.

**NB3 — `docs/architecture-as-built.md` is a mixed-concern diff.** Of 42 changed lines, roughly 28 are `![alt](x.png)` → `<img ... width="50%">` conversions across 12 diagrams, plus a layer-map row adding `ambient` to `foundation` (which does correctly mirror the uncommitted `.pyscn.toml` change — verified). About 10 lines relate to ticket 78. This is precisely the pattern this project has measured raising the miss rate on real defects: the diagram-sizing sweep and the layer-map row belong in separate commits.

**NB4 — comment churn dominates the production diff.** Measured by parsing before and after with `ast`+`tokenize` and mapping every diff line to a docstring/comment span or not:

| file | +prose | +code | -prose | -code | prose share |
|---|---|---|---|---|---|
| `toolguard/ambient.py` | 4 | 0 | 3 | 0 | **100%** |
| `toolguard/path_utils.py` | 2 | 0 | 2 | 0 | **100%** |
| `toolguard/permissions.py` | 16 | 7 | 9 | 2 | **74%** |
| `toolguard/normalization.py` | 35 | 32 | 4 | 6 | 51% |
| `test/unit/test_permissions.py` | 131 | 178 | 0 | 0 | 42% |
| `test/unit/test_normalization.py` | 88 | 118 | 2 | 4 | 42% |
| `test/unit/test_ambient.py` | 0 | 8 | 0 | 1 | 0% |

`permissions.py` is 25 prose lines guarding 9 code lines. Reading those 9 in isolation is how B2 surfaced — it is invisible while the rewritten docstring is arguing for it.

**NB5 — `match_command` complexity 21 → 24.** pyscn on the working tree vs `git show HEAD:` blobs. `.pyscn.toml` sets `max_complexity = 0` (no hard limit) but `medium_threshold = 19`, so this is the project's own "high risk" band, already exceeded before the change and pushed 3 further. Suggested extractions, briefly: `_spellings(command_str, also_spelled)` for the new nested dedup loop (which also fixes B2 by giving the expansion one owner), and the `cmd:args` branch at lines 218-252 as its own function. `normalize_path` is unchanged at 13.

**NB6 — `_passwd_home` is a new ambient read that no existing guard can see.** The passwd database is machine state naming a home directory, but the lookup bypasses `toolguard.ambient` entirely. `tools/architecture_fitness.py --ambient` scans only `os` imports and `Path` ambient members (`PATH_AMBIENT_MEMBERS = {absolute, cwd, expanduser, home, resolve}`), so `import pwd` / `pwd.getpwnam` is invisible to it and has no `PATH_AMBIENT_OWNERS` entry. `ConfigIsolationMixin` patches `Path.home` and clears `os.environ`, neither of which governs it. No current test is affected — every new test patches `pwd.getpwnam`, and the one unpatched assertion (`expand_tilde("~~")`) is machine-independent because `getpwnam("~")` raises `KeyError` everywhere. But a future test using a `~name` path under isolation will silently read the real machine's accounts with nothing to catch it. Suggest an owner entry plus a `pwd` arm in the fitness scan.

*(On brief item 3: the premise as stated does not hold for bare `~` — the mixin patches `Path.home` at `_config_isolation.py:96`, so `ambient.home()` is governed. The live hole is the `~name` route described above, which is new.)*

**NB7 — the two sibling tilde expanders now diverge, and one of them raises.** `path_utils.expanduser` routes `~user` to `Path.expanduser`; `normalization.expand_tilde` routes it to `pwd.getpwnam`. Measured:

```
     '~nosuchuser' | path_utils: RAISED RuntimeError | normalization: '~nosuchuser'
   '~nosuchuser/x' | path_utils: RAISED RuntimeError | normalization: '~nosuchuser/x'
              '~~' | path_utils: RAISED RuntimeError | normalization: '~~'
        '~\x00b/x' | path_utils: RAISED ValueError   | normalization: '~\x00b/x'
         '~root/x' | path_utils: '/root/x'           | normalization: '/root/x'
```

Reachable from user-controlled input via `env_config` → `expanduser(log_dir_str)`:

```
$ TOOLGUARD_LOG_DIR='~nosuchuser/logs' python -m toolguard.hook <<< '{...}'
[ERROR] toolguard crashed while deciding: Unexpected error in hook: Could not determine home directory.
{"hookSpecificOutput": {..., "permissionDecision": "deny", ...}}
```

Pre-existing and it **fails closed**, so not a security hole and not introduced here. It is listed because this diff rewrote that exact docstring — `"A ``~user`` form is left to :meth:`pathlib.Path.expanduser`, which resolves it against the password database, override or no override"` — describing the route while omitting that it raises for an unknown name. And because the fix's own stated rationale ("leaves callers with one fewer spelling to match rather than an exception raised mid-match") is the argument that resolves it one function over. Two helpers, one concept, opposite failure policies.

**NB8 — Read/Write/Edit `~name` is untested.** `file_matching.py:166,230` calls `expand_tilde`, so it inherits the new `~<name>` behaviour for free — `~root/x` used to stay literal and now resolves to `/root/x`. That is a behaviour change on the file-path side, the brief lists file-path matching as in scope for the fix, and `test/unit/test_file_matching.py` is unchanged with no coverage of it. The behaviour is correct; the assertion is missing.

**NB9 — `**/<component>/**` quietly widened, including for `allow` rules.** A DEFAULT component rule now matches segments of the home path itself. Verified: `match_command("cat ~/x", ["**/home/**"])` → `True`, `["**/testuser/**"]` → `True`; a command with no arguments (`~/x` alone) → `False`, as `docs/architecture-as-built.md:431` claims. Correct given the expansion, and documented and tested — but on a shape people write casually, and it widens grants as well as restrictions. Worth a release-note line, not only an architecture-doc bullet.

**NB10 — out of ticket, but it caps this fix's value.** The same deny is still walked past by three trivial neighbours of the spelling ticket 78 just closed:

```
 allow  cat ~/.ssh/../.ssh/id_rsa
 allow  cat ~/./.ssh/id_rsa
 allow  cat /home/arnon/.ssh/../.ssh/id_rsa      <- absolute spelling: same result
 allow  cat /home/arnon//.ssh/id_rsa
```

Pre-existing and orthogonal — the absolute spelling behaves identically, so this change neither caused nor worsened it. Worth a ticket alongside 83; a rule author who reads "the tilde spelling is now covered" will reasonably assume more coverage than exists.

**NB11 — `docs/architecture-as-built.md:432` "four deduplicated spellings" reads as a count.** For the ticket's own headline command the real number is two: `_command_variants("cat ~/.ssh/id_rsa")` returns `['cat ~/.ssh/id_rsa', 'cat /home/testuser/.ssh/id_rsa']`, because the two normalized forms dedupe against the raw. "Deduplicated" technically carries it; "up to four" would carry it without the reader having to.

---

## Where I disagree with the brief

**Brief item 4 ("A fact was removed from the ambient facade during this work") does not apply to this diff.** Nothing was removed from `ambient.py` here — `git diff --word-diff` on the file is empty (NB1). Across the whole repository history the only fact ever removed from the facade is `expanduser`, in commit `a2cf3f3` (ticket 80), already committed and outside this scope. Verified there are no remaining `ambient.expanduser` references anywhere (`ambient.home` 56, `ambient.active` 22, `ambient.AmbientFacts` 15, `ambient.cwd` 13, `ambient.env_var` 12, `ambient.env` 9, `ambient.resolve` 7 — no `expanduser`). And `test_ambient.py`'s `_AMBIENT_READS` is not a facade inventory that could silently pass: it is a list of names forbidden *at module scope inside ambient.py*, checked by `test_no_ambient_state_is_read_at_module_scope`. `"expanduser"` belongs in it whether or not the facade exposes a function by that name, so its presence neither asserts nor hides the removal. There is no dead code here.

---

## Metrics

- Elapsed: ~2h 0m (14:22 to 16:22 local).
- Files reviewed: 9 in scope (plus `patterns.py`, `file_matching.py`, `env_config.py`, `_config_isolation.py`, `tools/architecture_fitness.py`, `.pyscn.toml` read as context).
- Findings: 3 blocking, 11 non-blocking.
- Verification performed: full unittest suite (3769 tests), `ruff format --check` + `ruff check`, `pyscn check` on working tree and on HEAD blobs for a complexity delta, 5 authored probe scripts (passwd robustness across 38 inputs, shell-vs-toolguard differential, docs-claim execution, variant-redundancy corpus, prose/code churn via `ast`), 2 end-to-end hook runs (14 subprocess invocations), 1 in-process mutation run across 4 modes, CPython 3.14.0 `pwdmodule.c` fetched, `code.claude.com/docs/en/permissions.md` fetched.
- Estimated cost: roughly $9-12 (Opus 5, ~450k input tokens with cache reuse, ~35k output).