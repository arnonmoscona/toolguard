---
title: TOO-45 change-role classifier coder task recall
type: note
permalink: toolguard/too-45/too-45-change-role-classifier-coder-task-recall
tags:
- task-memory
- TOO-45
- coder-task-recall
---

# TOO-45 change-role classifier - coder task recall

Captured at start of feature-coder session, branch `too-45`, repo `/home/arnon/projects/toolguard`.

## Why this exists

Comparing two versions of the codebase by implementing the same small change in both and measuring which absorbed it better. Counting changed FILES measures requirement size, not code quality. Need a sharper instrument: classify what ROLE a changed subject identifier plays at each code location (DECISION / WRITE / CONDUIT / CEREMONY).

**Critical framing from the prompt:** eleven prior measuring instruments in this ticket each had a defect that made them report success incorrectly (substring-matching name detector; single-directory scanner reporting "0 callers" when there were 8; a gate testing half its own definition, passing on a two-line deletion; a checker blind to tuple-shaped cases; a hazard scan catching 1 of 9 synthetic hazards). **This instrument will be adversarially tested by another agent whose job is to make it report the wrong answer.**

## What to build

`tools/change_role_classifier.py` — committed dev tool, stdlib only, `uv run python tools/change_role_classifier.py ...`.

Input: two source trees (or a git diff between two commits), plus a subject (one or more identifiers).

Output per changed code location: ROLE(s) —
- DECISION: participates in branch/comparison/boolean op/predicate/match/conditional-expr test.
- WRITE: assignment target, mutated, or serialised/persisted out.
- CONDUIT: transport only — argument, return, stored into constructor call, forwarded.
- CEREMONY: test fixtures, mocks, imports, docstrings, type annotations, signature-only.

Multiple roles per location allowed; report ALL; precedence for single-label: DECISION > WRITE > CONDUIT > CEREMONY.

Headline number: conduit-to-decision ratio, reported SEPARATELY for production and test code (distinguished by path). Also counts per role, per file, total.

## Non-negotiable requirements

1. Use `ast`. Never match on name substrings. Resolve by AST node identity/scope, not string containment.
2. Do not silently skip anything. Parse failures, unhandled constructs, unresolved subjects -> explicit unclassified/unknown count in OUTPUT, never a zero.
3. Publish a KNOWN LIMITATIONS block in the tool's own printed output (not just docstring). Name concretely: `**kwargs`/`getattr` reach, runtime dynamic dispatch, decision-via-call-site-choice, subject renamed between trees.
4. Ship a hazard suite: synthetic cases a naive impl gets wrong, prove real impl gets them right. Minimum set: substring near-misses; shadowed local same name; ternary-hidden decision; match-case-hidden decision; conduit-through-intermediate-variable-to-branch (DECISION at branch, CONDUIT at hop); f-string-only use (CONDUIT not WRITE); `obj.field = x` mutation; `dict[key] = x` write; annotation-only (CEREMONY). Report hazard pass rate honestly, including failures if any.
5. Tests in `test/unit/`, `unittest`, Given/When/Then docstrings. Verify fail-then-pass: hazard tests must fail against a deliberately naive implementation, pass against the real one (demonstration step, not necessarily a committed second implementation).
6. Test-vs-production distinguished by PATH; state the rule in output.

## Validation on real data

Two throwaway copies exist (do not modify):
- /tmp/toolguard-master-copy (older architecture)
- /tmp/toolguard-branch-copy (newer architecture)

Both implement rule flag `allow_in_auto_mode`. Run classifier on EACH SEPARATELY (not diffed against each other — they are alternate universes, not before/after of one tree) with subject `allow_in_auto_mode`, report role breakdown for both. Do not tune to flatter either tree. Null/counter-intuitive result is fine and must be reported honestly. State any classification uncertainty and what was chosen.

## Report destination

`/home/arnon/projects/toolguard/toolguard-memories/TOO-45/reports/change-role-classifier-report.md`, frontmatter:
```
---
title: TOO-45 change-role classifier - implementation report
type: note
permalink: toolguard/too-45/reports/change-role-classifier-report
tags:
- task-memory
- TOO-45
- report
---
```
Markdown: never hard-wrap paragraphs (one paragraph = one line). Cover: what it does, how roles determined, hazard suite + results incl. failures, known limitations, measured numbers on both trees.

## Conventions observed in this repo before starting

- `tools/` dev tools are stdlib-only, argparse CLI, big module docstring explaining modes/usage (see `tools/architecture_fitness.py`, `tools/corpus_build.py` for the house style). `tools/__init__.py` already exists.
- Tests: `unittest`, Given/When/Then docstrings (`.claude/rules/testing.md`). Run via `uv run python -m unittest discover -s test -t .`.
- `test/unit/_config_isolation.py` / config-isolation rules apply only to tests touching `toolguard.config` discovery — NOT applicable here since this tool doesn't touch config discovery.
- Python 3.14 target (`match` statements, walrus etc. all fine).
- No existing AST parent-tracking utility in the repo to reuse (`architecture_fitness.py` only uses bare `ast.walk`, no parent map) — building fresh is not duplicating existing work.
- `uv run ruff format .` / `uv run ruff check .` before done. `uv run python tools/coverage_stdlib.py` for coverage (not required by prompt but good self-check).

## Design decisions made during planning (see decision log entries to be added)

- Python's own `ast.Store`/`ast.Del` context on Name/Attribute/Subscript nodes is authoritative for WRITE-target detection — avoids hand-rolling target detection (a past defect class in this exact ticket).
- Core algorithm: match exact-identifier nodes (Name.id, Attribute.attr, arg.arg, alias.name/asname, keyword.arg, plus raw-string fields ExceptHandler.name / MatchAs.name / MatchStar.name / MatchMapping.rest / Global/Nonlocal names) then, for Load-context occurrences, walk UP the parent chain through a whitelisted set of TRANSPARENT wrapper node types (Dict/List/Set/Tuple/Starred in Load ctx, comprehension elt) to the nearest governing construct, classifying by (governing type, field slot). Annotation/returns fields short-circuit to CEREMONY at any depth.
- Single-hop, branch-insensitive, per-scope alias tracking for `plain_name = subject` direct aliasing (documented limitation: no cross-function, no multi-hop beyond the tracked chain within one scope's linear statement list, no branch/loop sensitivity).
- String-literal exact-match subjects (e.g. `getattr(x, "allow_in_auto_mode")`) surfaced as a separate non-role-classified "string_literal_mentions" bucket rather than silently invisible — improves honesty without reintroducing substring matching (exact string equality only).
- Three CLI modes: `--tree DIR` (single tree, ALL occurrences = "changed" since subject is newly introduced — this is the mode used for the two throwaway copies); `--old DIR --new DIR` (diff-restricted to changed lines via difflib); `--repo DIR --base REV --head REV` (git diff mode via subprocess `git diff`/`git show`).

## Time tracking

Started: 2026-08-06 ~08:06 local. Phase 1 (planning/context reading) in progress.