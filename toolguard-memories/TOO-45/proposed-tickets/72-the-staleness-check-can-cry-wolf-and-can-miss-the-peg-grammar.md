---
title: The staleness banner can cry wolf about a tree git tracks nothing of, and cannot
  see a change to the PEG grammar
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/72-the-staleness-check-can-cry-wolf-and-can-miss-the-peg-grammar
---

**PARTIALLY FIXED in `05f786d`.** (a) the cry-wolf case, plus the unreadable-file and shadow findings, are fixed; still open: (b) `_hash_py_files` still globs only `*.py`, so a `bash_parser.peg` grammar change remains invisible to the staleness check.

# What is enforcing permissions, and does the banner tell the truth about it?

**Found 2026-08-13. Three RED tests in the tree. The fix direction for the first defect is verified by mutating toward it: both reds go green with zero collateral failures.**

`install_provenance` supplies the boolean behind the SessionStart banner that fires on this machine every session — *"INSTALLED COPY IS STALE… This checkout has changes that are not in the installed distribution."* Two failure directions, both live.

## 1 — FALSE ALARM: the git query is not anchored to the checkout

Cleanliness is asked with `git status --porcelain -- toolguard`, and **git answers from the nearest ancestor repository.**

Measured: an **unversioned checkout nested inside an unrelated repository that gitignores it** is reported **clean**, and `stale_install_report` then returns `is_stale=True`. The banner tells the user their checkout has uncommitted changes relative to the install — **about a tree git tracks nothing of.**

**Fix, verified**: guard with `rev-parse --show-toplevel` and confirm the answer came from the checkout itself. Mutating toward that turns both RED tests green and breaks nothing.

At HEAD the git side of the verdict was **entirely unanchored** — pointing the query at `/` (M06), scoping it to the whole repo instead of `toolguard/` (M07), and dropping the `-C` anchor altogether (M31) each produced **zero failures**. Now 3, 1 and 7 detectors. Note the shape: this is the same "never proven to run git in the directory it was given" defect measured the same evening in `working_tree_status`, one level down, and in `migration_gate`, one level up. **Three modules, one blind spot.**

## 2 — FALSE ALARM: an unreadable file reads as a difference

The digest silently skips a `.py` file it cannot read (`except OSError`), so the two sides differ and the result is **stale**. RED.

## 3 — MISS: the digest is `.py`-only, and the wheel ships the grammar

The hash covers `.py` files. The installed tree also contains **`toolguard/parser/bash_parser.peg`** and `parser/README.md` — verified present.

**So a checkout differing from the install only in the PEG grammar reports *current*.** That is the file `CLAUDE.md` names as *"the single source of truth"* for all bash parsing, and the one thing a two-phase grammar change is required to touch. The staleness check cannot see it.

## 3b — MISS, from the other direction: a `toolguard.py` FILE on `PYTHONPATH` is not detected as shadowing

**Added 2026-08-14 from `test_tools_environment_audit.py` (7 of 18 mutants at zero detection at HEAD; 17 of 17 detected after). RED test in the tree.**

`pythonpath_shadow_entries` looks only for `<entry>/toolguard/__init__.py`. A bare **`toolguard.py` module file** on a `PYTHONPATH` entry also shadows the installed package — **measured with a child interpreter, `import toolguard` resolved to the fixture's `toolguard.py`** — and the audit reports clean.

Same question as the rest of this ticket: *which copy is actually governing?* **One-clause fix, verified**: adding `or (Path(entry) / "toolguard.py").is_file()` flips the RED green with **zero** new failures in that module, zero in the HEAD copy, and no change to `test_install_provenance.py`'s failing set.

Correctly silent, and confirmed **not** shadowing: a `toolguard/` directory with no `__init__.py` — a namespace portion loses to the installed regular package.

Two smaller notes from the same measurement:

- **Fail-quiet**: `Path.is_file()` swallows `OSError`, so an unstattable entry reads as safe. Low severity — such an entry usually cannot be imported either.
- **A relative `PYTHONPATH` entry is resolved against the AUDITING process's cwd** and reported verbatim as `"."`. So the answer depends on where the audit ran, and the finding gives the reader no absolute path to act on. Characterised by a green test asserting both directions, **not** pinned as correct.
- Queue entry **GA1 is still live**: the finding's description says *"Any toolguard console-script or `-m toolguard...` invocation"* — a false universal that **its own remediation contradicts**, since `-E -P` ignores `PYTHONPATH`. Deliberately not pinned.

**And ticket 72 is NOT inherited here**: `audit_environment` never reaches `stale_install_report`, `_git_subtree_is_clean` or `installed_distribution_root`, so no duplicate RED was created.

## 4 — There is no way to say "undetermined"

Not installed, missing metadata, `locate_file` raising — **every failure mode collapses into `is_stale=False`**, the same value as a genuine "checked, and current". Harmless today because `session_start` prints nothing either way, but indistinguishable to any future caller, and it is ticket 29's family in a boolean.

## A negative result worth keeping

A read-only `git archive` of the installed commit (`532de02`) compared against `~/.local/share/uv/tools/.../toolguard` gives **identical `.py` sets and an identical digest** — so there is **no permanent false "stale" from wheel packaging asymmetry.** Measured, not assumed. The banner on this machine is telling the truth for the ordinary reason.

## The test module was 44% blind

36 mutants: HEAD detected 20, **16 survived**; the repair detects 34, with one **proven equivalent** (`rglob` on a file or missing path yields nothing, so the `is_dir` guard is unobservable) and one masked by its own RED until the fix lands. 31 -> 54 tests.

Newly covered, all previously at zero detection **anywhere**: the `os.environ` default, the empty-`PYTHONPATH`-entry guard, order preservation, recursion into subpackages, the relative path's contribution to the digest, the degenerate-hash guard, the `except OSError` skip, and **both arguments of `installed_distribution_root`** — asking metadata for `"definitely-not-toolguard"` or locating `"wrong-package-name/__init__.py"` both survived, because the fake `SimpleNamespace(locate_file=lambda name: init_file)` ignored its argument.

**Anchored on behaviour, not implementation**: three deliberately behaviour-identical rewrites (`--porcelain=v1` with a falsy-empty test, `sha1`, `dict.fromkeys` de-dup) all pass against the repaired module.
