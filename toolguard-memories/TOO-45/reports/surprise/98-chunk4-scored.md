---
title: 98-chunk4-scored
type: note
permalink: toolguard/too-45/reports/surprise/98-chunk4-scored
---

# Ticket 98 chunk 4 scored - the documentation page

Commit `726fd09`. Informed estimate; ineligible for the blinded series.

## Production files

| predicted | actual |
|---|---|
| **zero** | **zero** |

**Hit.** Second deliberate zero-production ticket in the series, after 88.

## Files predicted vs actual

| predicted | actual |
|---|---|
| one new `docs/` page | `docs/heredoc-parsing-design.md` |
| `docs/agent-map.md` | yes |
| -- | `docs/diagrams/heredoc-pipeline.mmd` + `.png` **(unpredicted)** |
| -- | `technical-notes.md` **(unpredicted)** |
| -- | `docs/permission-patterns.md` **(unpredicted)** |

**Predicted 2, actual 5. Recall 2/2 = 100%, precision 2/5 = 40%** -- I named everything that moved *of what I thought about*, and missed a whole category.

## The miss is the informative part: I predicted the ARTIFACT and not the CONSEQUENCE

The two unpredicted prose files are the real finding. `technical-notes.md` and `docs/permission-patterns.md` both stated that a heredoc's sink *"follows the pipe"* unconditionally. **Chunk 2 made that false** -- a bash-family or foreign bearer now wins outright even mid-pipeline, which is precisely case 16's fix -- and neither chunk 2 nor chunk 3 noticed.

So the doc chunk did not merely describe the work; **it found that two earlier chunks had silently invalidated documentation elsewhere in the tree**, three commits after the fact.

I estimated chunk 4 as "write a page about what we did". The correct model was "make every document in the repo true again after a behaviour change". Those have very different file sets, and only the second one is what a documentation chunk is *for*.

**Proposed as a general rule for the consolidated report**: for any behaviour-changing ticket, the touch-set estimate should include *the documents asserting the old behaviour*, and the estimator should be asked "what did this make false?" rather than "what does this need described?" That is a question I can ask at estimate time and did not.

## Uncertainties

- **U1 HIT.** I predicted `docs/agent-map.md` would be missed unless the brief named it explicitly, so the brief named it explicitly, and it was updated. A prediction that changed the instruction and thereby prevented its own outcome -- worth logging as such rather than claiming foresight.
- **U2 MISS, in the good direction.** I predicted the first draft would be too long, because a design-rationale page is where "long is thorough" fails. It came in at **51 lines** with a mermaid diagram carrying the pipeline. Being wrong about this is the outcome I wanted.

## Verification note

I checked the two prose fixes against the code rather than accepting them, and confirmed **both halves** of the corrected rule -- the executor bearer winning mid-pipeline (`python <<HD | bash` -> python, ASK floor) *and* the non-executor bearer falling through (`cat <<EOF | bash` -> body spliced as bash source), plus the doc's own dangerous-bearer example (`tee /etc/passwd <<EOF` keeps its arguments). Only the first half had been tested before; the second and third were claims no test covered.