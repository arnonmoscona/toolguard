---
title: TOO-45 punch-list 07 doc comments - coder task spec
type: note
permalink: toolguard/too-45/too-45-punch-list-07-doc-comments-coder-task-spec
tags:
- task-memory
- TOO-45
---

# Punch-list #07 — doc comments say what a thing is, not what a ticket did

Revised after two blind judges reviewed the first draft; their findings are folded in below and several changed the design.

## Why this exists

Arnon's standing rule (global `CLAUDE.md`, "Comments and doc comments"): **a docstring says what a thing *is*; a ticket records a *change*, and change history is git's job.** A ticket reference in a docstring is almost always wrong. In an inline comment one sometimes earns its place — when the answer to "why is this here at all" is a specific past incident — and even then it is one short sentence, the ticket as a pointer, no retelling.

The rule already existed and did not hold: **30 new ticket references were added in punch-list #03's change set alone**, nearly all in docstrings narrating the refactor.

**The cost is measured, not cosmetic.** Reviewing #03, Arnon nearly missed a suspicious empty class in `config_types.py` because that file's diff was +92/-135 of which the *code* was two `class` statements. Prose noise raises the miss rate on real defects in the same diff.

## Measured scope

Counted 2026-08-10 by AST + `tokenize`. **Both judges reproduced these independently and exactly** — treat them as reliable, and report any disagreement you find rather than silently adjusting.

| where | count | what to do |
|---|---|---|
| **docstrings** | **933** | see the disposition rules below — this is *not* a delete-on-sight sweep |
| inline comments | 228 | keep only where it explains a non-obvious why; reduce to one short sentence; otherwise delete |
| code / strings | 32 | **leave alone** unless plainly wrong — mostly test data and tooling that parses ticket IDs |

Docstring references by tree: **`toolguard/` 393 across 53 files, `test/` 481 across 73 files, `tools/` 59 across 5 files.** Heaviest: `test_architecture_fitness.py` 64, `config.py` 52, `compound.py` 48, `tools/architecture_fitness.py` 47, `config_types.py` 46, `test_configuration.py` 40, `test_hook.py` 36, `hook.py` 34, `test_resolve.py` 27, `resolve.py` 26.

## The disposition rule — read this twice

A judge classified all 933 by the shape of the edit each one forces:

| shape | count | edit |
|---|---|---|
| **parenthetical aside** — `(TOO-19)`, `(TOO-45 R2d)` mid-sentence | ~341 | excise the parens; the sentence is untouched |
| **mid-sentence, load-bearing** — `"as of TOO-45 R1d, sets its own returned…"` | ~416 | rewrite the sentence keeping the fact, drop the ticket |
| **paragraph lead** — a block opening `TOO-45 R2: …` | ~168 | **the dangerous one — see below** |

### A paragraph that opens with a ticket is not automatically disposable

Some of them state a **live invariant wearing ticket clothing**. The worked example, `config_types.py:159-168`:

```
TOO-45 R2: the wrapper-INTACT RuleEntry tuples (allow_entries/deny_entries/
ask_entries) are the ONLY storage. The wrapper-stripped pattern tuples
(allow/deny/ask) are derived properties over them, not separately stored --
there is no longer a second, independently-populated collection that could
drift out of alignment with the entries. Before this change the two were
parallel dataclass fields with a hand-documented "same order, same
membership, index-for-index" invariant; that invariant is gone because
there is only one storage.
```

It opens with the delete-on-sight pattern. But the first two sentences state a **current fact about the class**: entries are the only storage, patterns are derived. Only the tail (`Before this change…`) is history. The correct edit keeps the invariant, drops the ticket and the before/after narrative.

**For every paragraph-lead site, ask: does this sentence assert something that is true of the code as it stands?** If yes it is documentation and it stays (minus the ticket). If it only says what changed and when, it goes.

**Why this matters more than it looks:** a deletion hunk shows what went away, never whether the fact survives elsewhere. A reviewer cannot detect this class of loss by reading the diff. You are the last line of defence on these 168 sites.

## Also in scope: prose that is now factually wrong

Verified against the working tree, and re-verified independently by both judges. Do not assume the list is exhaustive; do not inflate it either. **If an item turns out to be already correct, report that** — it is a finding about the list.

1. **`test/unit/test_recommended_protections.py:66-71`** — describes `_anchor_file_pattern` as living in `resolve.py`. It is at `toolguard/file_matching.py:33`. Exactly one site.
2. **`decide_detailed`, a deleted callable, survives in six places** — `permission_resolution.py:43`, `:205`; `tools/architecture_fitness.py:920`; `test_configuration.py:3422`, `:3435`, `:3678`. The three test sites name local closures after it; rename them for what the closure does.
3. **`technical-notes.md:406`** — refers to `hook.resolve_bash_permission_detailed`. Wrong module, and the name no longer exists.
4. **The deleted `toolguard/tools/decision.py` is referenced 158 times; only ~18 are prose.** `tools/architecture_fitness.py` carries 12, of which lines ~210, ~246, ~3269 use `toolguard/tools/decision.py` as the *worked example* in path-resolution docstrings, teaching a path that does not exist. Then `test_architecture.py:84,88`, `config_types.py:681`, `api.py:13`, `test_api.py:885`, `.pyscn.toml:167`.
   - **Replace the worked example with an obviously-synthetic path** (`pkg/mod.py`, `toolguard/example.py`), **not with a live module** — a real module name re-couples the docstring to an identity that can move again. That is the whole defect repeating.
   - **Do not touch `test/verdict_corpus/cases.jsonl` or `goldens.jsonl` (70 occurrences).** Recorded corpus data, not prose.
   - `test_architecture_fitness.py` carries 25-28 synthetic module-path fixtures. Optional; if you change them it is a behaviour-preserving rename and tests must pass unchanged.
5. **`docs/architecture.md`** — no entry for `once_per.py` or `once_per_store.py`; line 63 still describes `session_warnings.py` as "Session-level warning markers", which after punch-list #01 it is not. **Also apply the docstring rule to this file**: lines 51-56 carry "Decision-resolution engine (TOO-45 D1)", "extracted from resolve.py; TOO-45 punch-list #03" and similar. Same rule, same reasons; nothing mechanical will ever catch this file.

## Not in scope

- **General prose rewriting.** Shorten only where removing the ticket narrative leaves something still bloated. An already-short, accurate docstring is finished.
- **Code changes in stages 2-3.** The proof below depends on there being none.
- The four `error_log`/`log_warning` call sites in `hook.py` — a real finding, but code, and it has its own queue entry.

## Stages

### Stage 1 — the instruments, committed

**1a. `tools/generated_files.py`** (new, small). Lift `is_generated_file()` and its marker tuple out of `tools/architecture_fitness.py:140` into this module, and have `architecture_fitness.py` import it. Do not change the detection logic — it detects by **content banner, never by filename**, and its docstring argues why. This exists because the first draft of this spec told you to hardcode `canopy`/`bash_parser*` filenames, which would have put a third copy of the exclusion into `tools/` in the form this repo already documented as wrong.

**1b. `tools/comment_hygiene.py`** (new, stdlib only, imports `generated_files`):

- `docstring_ticket_refs(root)` — walks `*.py`, parses each, yields every `TOO-nnn` occurrence whose line falls inside a module/class/function docstring node. Returns **a frozen dataclass per record** (path, line, owning symbol, matched text) — not tuples, not formatted prose. Rendering happens in `__main__`.
- `comment_ticket_refs(root)` — the same for `#` comment tokens.
- `code_shape(source)` — parses, deletes every docstring node, returns `ast.dump(tree, include_attributes=False)`. Equal shapes mean the sources differ only in docstrings, comments or formatting. **Give the return a named type** (a `NewType` or a one-field frozen dataclass); a bare `str` invites printing an opaque comparison key as though it were a report.
- `__main__`: the hygiene report, plus `--compare-against <git-ref>` listing every changed `.py` whose code shape moved.

State in the module docstring, in one sentence: prose inside string *literals* is invisible to `code_shape`, so such a change reads as a code change. That is the conservative direction — it never certifies a real code change as prose-only.

### Stage 2 — sweep `toolguard/` and `tools/` (452 docstring refs, 58 files)

Plus the stale-reference items falling in those trees.

### Stage 3 — sweep `test/` (481 docstring refs, 73 files)

Plus the remaining items. Test docstrings keep their Given/When/Then structure (`.claude/rules/testing.md`) — you are removing ticket narrative from them, not restructuring them.

### Stage 4 — the guards

**New file `test/unit/test_doc_hygiene.py`.** Not `test_architecture.py`: that module's declared subject is toolguard's module *layering*, and this guard must cover `test/` and `tools/` as well, which do not belong there.

- `test_docstrings_carry_no_ticket_references` — assert `docstring_ticket_refs` is empty **across all three roots (`toolguard/`, `tools/`, `test/`)**. `test/` alone is 52% of the stock and is where #03 added most of its references, so a `toolguard/`-only guard would leave the site most likely to regress unprotected. Failure message names the offenders and points at the rule.
- `test_inline_comment_ticket_references_do_not_increase` — a **numeric may-only-decrease ratchet** with the post-sweep count as the baseline, in a named module constant with a comment saying to lower it, never raise it. This closes the free bypass: without it, satisfying the zero-assertion costs one relocation from a docstring into a comment, and the comment rule is a judgement rule of exactly the kind whose failure this item exists to remedy.

**No escape marker on the docstring guard.** The legitimate case has somewhere to go — an inline comment, now metered. If the sweep leaves a docstring reference you believe genuinely earns its place, **report it and stop**; that is Arnon's call. Do not invent an exemption mechanism — that is how the original rule died.

### Stage 5 — report only, no assertion

Ticket references are inert noise. The four stale-reference items above are a different and worse class: prose naming a symbol or path that has moved or been deleted, which actively teaches a false model. This item hand-fixes those and guards only the inert class, and that asymmetry should be measured rather than left implicit.

Add `--stale-references` to `comment_hygiene.py`: report every `.py`-looking path and every dotted `module.symbol` reference inside a docstring that does not resolve in the tree. **Report only — no test, no assertion.** A judge measured the naive version: 419 `.py` filenames appear in docstrings, a bare existence check flags 41, and roughly 30 of those are legitimate illustrative placeholders (`tools/x.py`, `src/x.py`, `script.py`). Filtering to paths that look like real repo paths should cut most of that.

Put the output in your report. The point is to find out whether a guard here is feasible, not to build one now.

## Verification

1. `uv run python -m unittest discover -s test -t .` — full suite green.
2. **Golden verdict corpus byte-identical.**
3. `uv run ruff format .` and `uv run ruff check .` clean.
4. `tools/comment_hygiene.py --compare-against HEAD` reports **zero** files whose code shape changed, **across stages 2 and 3**. Put the output in your report. If a shape moved, either you changed code (revert it) or it is the string-literal case — name the file and the literal and justify it.
   - Stage 1 legitimately changes code (`architecture_fitness.py` gains an import). Keep it in its own commit so the proof over stages 2-3 is clean.
   - **This proves only that no code moved. It does not prove the surviving prose is correct** — that is the review, and it is not mechanisable. Do not present it as more than it is.
5. Report before/after docstring and comment reference counts per tree.
6. **Note explicitly** that `technical-notes.md`, `docs/architecture.md` and `.pyscn.toml` are outside the instrument, which only walks `.py`. Their three sites need checking by hand.

## For the reviewer, to go in your report

The reviewability judge rated this `high` on **breadth, not depth** — ~540 dispersed judgement sites, no single one requiring more than local context. It recommended, and I agree, that Arnon **sample rather than read exhaustively**: the failure mode here is uncorrelated small losses, not one catastrophic error, so reading ~40 of the ~663 affected docstrings and accepting on a clean sample is defensible in a way it would not be for a behavioural change.

**Weight the sample toward the ~168 paragraph-lead sites in `toolguard/`.** That is where a live invariant can die silently, and production docstrings hold the facts worth keeping. List those sites explicitly in your report so the sample can be drawn from them.

## Reporting

Standard implementation report. Include: before/after counts per tree, the `--compare-against` output, every string-literal exception with its justification, the `--stale-references` output, the list of paragraph-lead sites you judged to contain live invariants (and what you kept), and any stale-reference item you found already correct.
