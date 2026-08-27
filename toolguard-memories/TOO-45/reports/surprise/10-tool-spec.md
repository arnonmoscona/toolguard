---
title: Surprise factor - item 10 (ToolSpec registry)
type: note
permalink: toolguard/too-45/reports/surprise/10-tool-spec
tags:
- task-memory
- TOO-45
- measurement
---

# Item 10 — make "a supported tool" a described thing

Protocol: [[surprise-factor-protocol]]. Estimate pre-registered in [[10-estimate-predictions]] (sealed until green) and [[10-estimate-uncertainties]] (read before implementing). **Blinding held.** First item scored with `|A|/|P|` and `n/(n-1)` dropped.

## Actual touch set — 10 files

| group | files |
|---|---|
| production, added | `tool_spec.py` |
| production, modified | `constants.py`, `config_validation.py`, `hook.py`, `tools/installer.py`, `tools/transcript_harvest.py` |
| dev instrument | `tools/architecture_fitness.py` |
| config | `.pyscn.toml` |
| tests, added | `test_tool_spec.py` |
| tests, modified | `test/verdict_corpus/fixture_loader.py` |

Verified: 2,721 tests OK, **golden verdict corpus byte-identical**, `--layers` clean, ruff clean, and all three membership sets confirmed derived with no literal left behind.

## Scoring

`|P| = 25`, `|A| = 10`, **hits = 8**, surprises = 2, overshoots = 17.

| | raw | production | test |
|---|---|---|---|
| **recall** | **80%** | 75% (6/8) | **100%** (2/2) |
| precision | 32% | 38% (6/16) | 22% (2/9) |

**Leak discount.** The ticket names five files with line numbers. On the six unnamed files, **recall is 67%** (4/6).

**Best recall of the series, worst precision of the series.** The estimator cast a very wide net — 25 predictions for a 10-file change — and it bought coverage at the cost of a 68% false-positive rate. Worth recording that it *was* already filtering: it explicitly listed 13 further files it declined to predict, with reasons. So the width was deliberate, not sloppy.

### The two surprises

| file | cause | note |
|---|---|---|
| `tools/installer.py` | **C** | A live hardcoded `("Read", "Write", "Edit")` tuple wired to no constant, in a module the ticket never mentions. This is the item's own thesis — tool membership is scattered — turning up an instance the ticket's author missed. The estimator predicted the *mechanism* precisely in its uncertainties: *"the enumeration method that produced 'four' is the same method that already missed two."* It just could not name the file. |
| `tools/architecture_fitness.py` | **E** | The dev instrument's canary set and a comment restating the payload-key rule. Not predictable: repo-root `tools/` modules all share the boilerplate docstring *"Dev-only instrument, NOT shipped"*, so first-line-only tells the estimator nothing about four large files. **It flagged exactly this as "the single largest blind spot in this view" — and the surprise landed there.** |

**Third item running in which the estimator predicted its own miss** (05: none; 01: 5 of 5; 04: mechanism-level; 15: the memories-tree blind spot; 10: this). The uncertainties half continues to be worth more than the prediction half.

### The ticket was wrong again, and this is now a pattern

The ticket's premise is *"four independent membership sets"*. Measurement gave a different picture entirely:

| claim | reality |
|---|---|
| four membership sets | **three live, one dead.** `hook.COMMAND_TOOLS` had exactly one occurrence in the tree — its own definition. Zero readers. |
| `danger.py` holds two hardcoded copies | **already fixed.** It imports `FILE_TOOLS`. The ticket's own "until the current bug batch" hedge was true, and the estimator still predicted it — an estimator error on a *named* file. |
| (unmentioned) | a fifth copy in `tools/installer.py`, a sixth encoding in `tools/architecture_fitness.py`, a seventh in `fixture_loader.py`, and a look-alike in `config.py` |

**Second consecutive item whose ticket evidence did not survive measurement** — #04 claimed 16 hand-rolled stderr writes and there were 8. Both tickets were written from a code reading rather than a count, and both were wrong in the same direction on the headline number while *undercounting* the true spread. The cheap fix is to count when writing the ticket, not when writing the code.

### The durable output is an inventory, not a type

The item's real finding is that "duplicate" was three different things wearing one name, and the correct treatment differs:

| kind | example | treatment |
|---|---|---|
| **one concept duplicated** | the three membership sets; the payload-key literals; `installer.py`'s tuple; `fixture_loader.py`'s branch | derive from the registry |
| **deliberate independent oracle** | `architecture_fitness.py`'s `_CANARY_FILE_TOOLS` | **keep duplicated.** Its purpose is to disagree when production drifts; deriving it would make it assert the code equals itself. Reason now written into the code so it is not "fixed" later. |
| **look-alike** | `config.py`'s `_DEFAULT_IGNORED_ALLOW_PATTERNS` | **keep separate.** Textually derivable today, but deriving it would couple takeover semantics to registry membership — adding a tool would silently change which native allow patterns takeover ignores. The lists agreeing is a coincidence of the current tool set, not a shared definition. |

The coder escalated the oracle case rather than following the spec, which had told it to derive. **The spec was wrong and the escalation was right.**

## RESCORED after the review fix pass — 16 files

The review found two contract defects, and fixing them grew the item from 10 files to 16.

`|P| = 25`, `|A| = 16`, **hits = 10**. **Recall 63%** (was 80%), **precision 40%** (was 32%).

**Recall fell as the item grew — the same pattern as #01**, and for the same structural reason: a touch-set prediction made against the original ticket cannot score well against a set that grew for reasons the ticket never contained.

| new surprise | cause | why |
|---|---|---|
| `tools/maintenance.py`, `tools/security_audit.py` | **R** | Consumers of `GOVERNED_TOOLS`, renamed to `BUILTIN_TOOLS` because the old name asserted a falsehood. The rename came from review, not the ticket. |
| `test_hook_eval.py`, `test_verdict_corpus.py` | **R** | Seam-pinning tests, added because the review measured the test-to-production ratio at 0.8:1 against a repo norm of 1.9:1 and located the gap precisely at the unpinned view seam. |

**Final cause assignment:** 1 `C`, 1 `E`, 4 `R`. No `E` beyond the dev-instrument blind spot the estimator had already named.

### What the review caught, and why it mattered more than usual here

Both Majors were **contract** defects — the registry asserting things that are not true — which is the sharpest possible failure for a module whose entire purpose is to become the one place people trust.

1. **`governed_by_default()` returned `{Bash, Read, Write, Edit}` and documented itself as "governed unless config overrides".** The actual runtime default is `("Bash",)`. All four real consumers used it to mean "the tools toolguard ships knowledge about", never as a governance default. The danger was the name: it invited wiring into `governed_tools()`'s fallback, which would have silently governed `Read`/`Write`/`Edit` in every unconfigured project. Renamed to `BUILTIN_TOOLS` / `is_builtin`, with the docstring now saying explicitly what it is **not**. No live bug existed — checked every importer.
2. **One registry, two view semantics.** `constants.py` snapshotted the derived views at import; three other sites called them live, and the docstring claimed automatic pickup that only some consumers got. No test could observe the difference. Now all three views are module-level frozensets computed once, `constants.py` re-exports the same objects (pinned with `assertIs`, not `assertEqual`), and `payload_key()` remains the only function because it takes an argument and is a lookup rather than a view.

**Note the shape:** item #10 set out to remove duplicated *values* and the review found duplicated *semantics* — two ways of reading one registry, and a name asserting a default that was not one. The value duplication was the easy half.

## Complexity ratings

- **Blind judge: `low`** — 9 trivial locations against 2 substantive. Key reasoning: all new thinking sits in one 97-line flat declarative table with no branching, every other site is a one-line substitution, and `test_tool_spec.py` pins each derived view against its exact prior literal set, so a reviewer verifies value preservation in one file instead of cross-referencing eight.
- **Arnon: `low`.** *"Easy to review for the same reasons as before. The only thing is my confusion about additional_supported_tools and ToolSpec and how it should relate overall to tool configurations, fallbacks, and documentation."*

**Judge and owner agree again — second consecutive agreement under the corrected brief** (item 15 was the first), against maximum disagreement on item 04 under the old one.

**But note what his rating did NOT capture, and it is the important part.** He rated the change easy to read and, in the same breath, identified the design gap that became `TOO-51` — an abstraction that is partial, under-explained, and possibly not fully thought through. **Reading cost and design soundness are independent, and the complexity scale only measures the first.** A change can be trivial to read and wrong in a way no rating would surface. That is consistent with his broader finding that metrics catch bugs while manual review catches architectural error, and it is an argument against ever treating a `low` as an all-clear.

**Notable: the judge said the ticket alone predicts `medium`** — *"a new foundation type fanning out to eight modules sounds like held-together reading"* — and departed downward with a stated mechanism. That is the ticket prior working as a **check** rather than an anchor, which is what the corrected brief asked for, and it is evidence against the worry that the new brief simply produces `low` for everything.

**Size, now recorded separately** (added to the protocol after Arnon's item-15 remark): 10 files, 11 substantive locations, one 97-line new module. Comparable in size to #15 (11 files), and rated the same. **Shape and size are still confounded across every item so far**, and #10 does not break the tie. #03 is the first candidate that might.
