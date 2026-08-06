---
title: _shared-context
type: note
permalink: toolguard/too-45/reports/shared-context
---

# Shared context for TOO-45 report authors

Read this, then your own brief. Do not re-derive what is here.

## Trees available

| path | commit | tests | what it is |
|---|---|---|---|
| `/home/arnon/projects/toolguard` | `a3e3f27` | 2,387 | **the working tree — READ ONLY for report authors** |
| `/tmp/toolguard-master-copy` | `532de02` | 2,186 | pre-TOO-45 baseline ("before"), full `.git` |
| `/tmp/toolguard-branch-copy` | `a3e3f27` | 2,387 | copy of the finished branch ("after"), full `.git` |

`532de02` is the last commit before TOO-45 began. `a3e3f27` squashes the whole ticket.

**Report authors must not modify any of the three trees.** Only the canary-experiment author modifies the two `/tmp` copies.

## What TOO-45 did

| step | outcome |
|---|---|
| R3 | zero production sites parse structured data out of reason prose |
| D4 | one undecidable floor, not two — proven by a mutation that flipped MISSED to CAUGHT |
| D1a | decision orchestration moved out of `Configuration` into `permission_resolution` (engine layer; imports only `config_types`, never `toolguard.config`) |
| R1 | one runtime verdict type `RuntimeVerdict`; `UnitVerdict`/`Decision`/`LevelMatch` are declared altitudes; 2 `__iter__` shims and 13 bare verdict tuples removed; `log_command` 12 params -> 4 |
| R5 | entry points are leaves; `permission_migration` and `install_update` split out of console scripts; `hook <-> tools.decision` cycle gone |
| R2 | index-parallel access 3 -> 0; prose invariant statements 4 -> 0; both drift guards deleted; misaligned `ToolPatternLayer` state now unconstructible |

**The headline result is not a predicate.** The compound audit trail was 83% lossy — 813 of 975 compound-allow corpus cases under-logged, 1,943 sub-commands executed with no audit record — because `hook.py` recovered the breakdown by regex over reason prose and dropped every segment lacking `" -> "`. Now 0 of 978. Fixing it exposed a second, independent bug: `resolve._deciding_sub_match` and `tools.decision._decide_bash` both attributed provenance with heuristics that only worked *because* escape-hatch leaves were missing from `sub_matches`.

## Measurement discipline — this ticket learned these the hard way

1. **Check that an instrument can express the outcome before using its reading as evidence.** Seven instrument defects were found in one day, each reporting success or failure it had not earned: name-substring matching; a caller scan confined to one directory; a gate on half a predicate's own definition; a scan that could only see classes; a footprint metric blind to positional coupling; a field deliberately named to dodge a detector; a class-name-hardcoded scan a `sed` could defeat. **Six of seven were caught only by running something.**
2. **Rename-and-count measures NAME COUPLING, not work.** Renaming `hard_deny` breaks 106 tests; the actual change to the same code breaks 0. Two blast-radius estimates (88 and 180) both resolved to zero net suite change. Report mechanical vs behavioural separately or not at all.
3. **The enrichment-footprint metric counts identifiers, so it is blind to positional (tuple) coupling** and *rises* when positional coupling is made explicit. Do not use it as a change-cost measure across a tuple-to-dataclass conversion.
4. Label every substantive claim **DEMONSTRATED BY EXECUTION** or **INFERRED BY READING**. This distinction has repeatedly been the difference between a true and a false finding here.

## Useful commands

```bash
uv run python -m unittest discover -s test -t .
uv run python tools/corpus_build.py --verify          # 6,401 in-process + 61 e2e golden cases
uv run python tools/architecture_fitness.py --predicates
uv run python tools/architecture_fitness.py --layers
uv run python tools/architecture_fitness.py --metrics
uv run python tools/architecture_fitness.py --guard    # 12 canaries through the live hook
uv run ruff check --no-cache .                         # ALWAYS --no-cache; the cache has lied
```

`tools/architecture_fitness.py` exists only on the branch, not on master. To measure master with it, copy the tool into the master copy rather than porting the analysis by hand — and say you did.

## Output conventions

- Reports go in `toolguard-memories/TOO-45/reports/` as markdown, tagged `task-memory` and `TOO-45`.
- Diagram sources and rendered images go in `toolguard-memories/TOO-45/reports/img/`.
- **Do not hard-wrap paragraphs** — one paragraph is one line, however long. Blank line between blocks. Arnon reads these rendered in Obsidian.
- **Diagrams must be small and focused.** A diagram with too many elements is unusable. One aspect per diagram, each with accompanying prose explaining the key points and the design motivation. PlantUML (installed, 1.2026.6) is preferred for formal UML; excalidraw-cli 1.2.0 and mermaid 11.16 are available for informal diagrams. Embed rendered PNG/SVG in the markdown; a link is a fallback, not the goal.
- Generate images by running the tool — do not hand-write SVG. Verify each rendered file exists and is non-empty before referencing it.

## Hard rules

- **NEVER run `git checkout`, `git restore`, `git stash`, `git reset`, `commit`, `push` or any git write** in any tree. They are denied by permission rule and HANG waiting for a human. Read-only git (`log`, `diff`, `show`, `status`) is fine everywhere.
- Do not modify `/home/arnon/projects/toolguard` unless your brief explicitly says to.
- `uv run python`, never bare `python`. `unittest`, not pytest.
- This repo requires an INTENT/TOUCHES disclosure comment block plus a `TG_INTENT=1` or `TG_ATTEST_READONLY=1` env prefix on any Bash command carrying code you wrote — heredocs, `python -c`, scratch scripts. See CLAUDE.md.
- Report progress in your transcript as you go; avoid long silent stretches.