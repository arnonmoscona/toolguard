---
title: TOO-45 punch-list 09 plan
type: note
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/too-45-punch-list-09-plan
---

# #09 — `docs/architecture-as-built.md`

**Authorised by Arnon 2026-08-12**, immediately after committing #07's comment sweep. Method: *"two or three passes as you see fit — a proven pattern, blinded review, then corrections, and let me know when that's satisfactory as far as you can tell."*

## Scope decision taken without asking

Ticket 09 leaves one open question: `docs/` (user-facing, linked from `llms.txt`) or somewhere internal. **Taking `docs/architecture-as-built.md`**, as the ticket's own title says. Follow-up if it ships: an entry in `docs/agent-map.md` (which summarises every doc and has no other mechanism keeping it in sync) and a line in `llms.txt`. Arnon can overrule.

## The four sections, from ticket 09

1. The layer model, what each layer is for, including `observability` and why cross-cutting concerns sit low.
2. The verdict altitudes — `LevelMatch` / `UnitVerdict` / `RuntimeVerdict` — and why there are three.
3. The decision path end to end, as a diagram.
4. **The runtime dependencies no import graph shows** — the `permission_resolution <-> resolve` relationship and the Protocols describing it. *This is the section a reader cannot derive from the code, and it is the reason the document is worth having.*

Diagrams in **Mermaid**, small and focused. Arnon is strongly visual and reads diagrams before prose.

Stamped `As of <date> — toolguard <version> — commit <sha>` at the top. **A stamped stale document is useful; an unstamped one is a trap.**

## The deviation from the ticket, made deliberately

Ticket 09 says the document *"needs your review more than my verification."* **Post-#07 that is backwards.** An architecture document is a dense pile of universally quantified claims — the exact artifact type the sweep just spent two days demonstrating is unreliable, and the one whose falsehoods are hardest for a reader to detect because they sound like design intent.

So verification is a first-class pass, not a formality, and it uses the sweep's own method: **execute the claim, do not read it.**

## Passes

| pass | who | what |
|---|---|---|
| 1 | drafting agent | write the document from the code, the layer map, and the branch-side report material. Every claim verified against the code **as it is written**, with the check recorded. |
| 2 | blinded reviewer | read the document **cold**, with no access to the drafter's reasoning. Verify every checkable claim by execution or grep. Report falsehoods and unverifiable assertions separately. |
| 3 | corrections | apply, then a narrow delta check: did a correction strand anything, and did the corrections themselves introduce new claims? |

The loop is the one that worked across ~80 files in #07. **The reviewer must not be the drafter**, and must not see why the drafter believed anything.

## Budget constraint — STALE, superseded 2026-08-14

The original text read *"Weekly at 93%, resets Aug 13 10am ET… stop-dispatch line is 95%"* and would now cause an agent to stop for no reason. **The weekly reset happened.** As of 2026-08-14 00:45 the weekly is at **25%** and Arnon has said it is **not a constraint this week** — he is away four days. The live limit is the **5-hour session window**, which resets at fixed boundaries (7:39pm, 12:39am, 5:39am, 10:39am); work to ~90% of a window, then wait for the next one. **Never compute "5 hours from now."**

## Document state as of 2026-08-14 00:45, measured

`docs/architecture-as-built.md` is **130 lines / 2,226 words**, carrying sections 1-4 plus Sources — i.e. the four sections from ticket 09 and **none of round-2's seven additions**. Both diagram invariants hold: **0** raw mermaid fences, and all 12 referenced paths (6 `.png` + 6 `.mmd`) exist. `core-vs-tooling.{mmd,png}` is built and still deliberately unreferenced, waiting on the core/tooling section.

**So the rework is additive, not a rewrite of what is there** — except for the prose-density pass, which applies to sections 1-3 (section 4 is already the approved worked example).

## Round-2 direction from Arnon, 2026-08-12 (after skimming the pass-1 draft)

He did not read it, because I did not claim it was ready. The observations are shallow by his own description and every one of them is structural — they change what the document **is**, not how it is worded. Pass 2 is therefore no longer "blinded review of the draft"; the draft is a **section-4 prototype**, and the document around it does not exist yet.

**The scope grows:**

1. **Prose density — RAISED TWICE, so treat it as a hard gate, not a preference.** Arnon's second pass: *"large, dense blocks of text with long, long sentences broken by commas... I can go through that because I'm familiar, but someone else would look at it and say 'maybe another day'."* A document nobody finishes has no value however correct it is.

   Measured on the pass-1 draft, then again after reformatting section 4 only:

   | metric | pass 1 | after §4 | target |
   |---|---|---|---|
   | median sentence | 25w | 20w | <= 20w |
   | sentences > 40w | 16 of 72 | 10 | 0 |
   | sentences > 60w | 5 (max **81w, 7 commas**) | 2 | 0 |
   | median paragraph | 78w | 49w | <= 60w |
   | paragraphs > 120w | 5 (max **223w**) | 3 | 0 |

   **Section 4 is the worked example of the target format, and Arnon confirmed it reads better (2026-08-12, after reload).** The format is approved, not proposed — match it, do not re-litigate it. Read section 4 before rewriting the others. What worked there, in order of effect:

   - **A list in prose becomes a list.** Protocol members, before/after states, caveats on a figure. If a sentence contains "and... and... and", it was a list.
   - **A two-axis comparison becomes a table.** The module/Protocol/members mapping was one 70-word sentence; it is now four table cells.
   - **A quoted docstring becomes a blockquote**, not an inline quotation buried at the end of an 81-word sentence.
   - **Split on the "so/but/and" hinge.** Most 60-word sentences are two 25-word sentences joined by a conjunction that adds nothing.
   - **Lead with the claim, then support it.** "This narrows a defect that used to be worse." Full stop. Then the detail.

   Re-run the measurement after rewriting; do not eyeball it. Bullets are not a licence for more words — the word count should FALL, not move sideways into list items.
2. **Diagrams.** The draft has four Mermaid blocks; they are unrendered source where he reads them. `mmdc` **is installed** (`~/.nvm/versions/node/v24.16.0/bin/mmdc`). Requirement: **rendered graphical form in the document, one `.mmd` source file per diagram, document links to the source.** The before/after diagrams produced earlier in this ticket are the quality bar.
3. **`docs/architecture.md` must be reconciled.** Compare against current state; consider deleting; harvest what is still true or clearer. **My recommendation, stated to him and overrulable: merge into one `docs/architecture.md`.** Its ASCII flow diagram is good and out of date — redraw in Mermaid, correct to the current flow.

   **Surveyed 2026-08-14 so the rework does not start by re-deriving this.** `docs/architecture.md` is **384 lines / 2,137 words** — comparable in size to the new document, so this is a merge of two peers, not absorbing a stub. Last touched 2026-08-10 by item 03, so parts of it are current. Its seven real sections:

   | section | disposition |
   |---|---|
   | Contents | drop — regenerate for the merged document |
   | Package structure | reconcile against the layer map; overlaps new §1 |
   | Hook flow | **superseded** by `hook-lifecycle` + `resolution-cascade` diagrams |
   | Writing configuration | **harvest** — this is diagram 15, the guarded write chokepoint and its three checks |
   | Configuration hierarchy | **harvest** — diagram 9, most-specific-level-wins |
   | Pattern matching implementation | **harvest** — diagram 14, DEFAULT/REGEX/GLOB/NATIVE dispatch |
   | Logging | **harvest** — diagram 16, the four log streams |

   **Four of the five "harvest from `architecture.md`" rows in the diagram inventory come from these sections**, which is the argument for merging rather than deleting: the content the inventory wants is here and is mostly still true.

   **Checked and clear**: the `## 2026-01-14 10:15:23`-style lines are example log entries **inside a ```` ```markdown ```` fence**, not real headings. A heading grep matches them; they are not a structural defect and need no fixing.
4. **Static structure AND dynamic behaviour**, both. The draft is mostly static.
5. **Key design decisions need their reasoning**, not just a mention:
   - **the PEG grammar** — mentioned nowhere in the draft, discussed nowhere; the two-phase change rule and "never hand-rolled Python" rationale
   - **stdlib-only runtime** — a hard constraint, absent from the draft entirely
6. **Key requirements as constraints, up front.** The architecture is downstream of them and the draft starts at the layer map, which is an answer with no question attached.
7. **The skills, and the core/tooling separation — his exact wording**: *"the separation between the core and the tooling is not discussed especially because the tooling is where a lot of complexity is present."*

   The second clause is the load-bearing half and goes past my initial reading. An architecture document organised around the hook's decision path describes **the simpler half at length while the complicated half goes unmentioned.** Measured 2026-08-12: `toolguard/tools/` is **11,752 lines across 30 files**, against **15,100** for the whole core package (`toolguard/*.py`, excluding `tools/`, `testing/`, `parser/`) — roughly 44% of the non-test Python. The pass-1 draft mentions it once, in passing, inside a layer diagram.

   The separation itself: the hook is stdlib-only, read-only, one process per tool call; `toolguard/tools/` and the skills are operator-side, write config through the guarded chokepoint, and are covered by `docs/skills.md`. That split is exactly what the `api` layer and the `runtime`/`tooling` layer rules exist to enforce, so it connects straight back to section 1 — `api` was created because `hook.py` was reaching *up* into `tools.decision`.

   **Corroborating evidence that the complexity is real and under-described**: proposed ticket 22 (redundancy analyzers report unsafe deletions as safe) and ticket 29 (`run_guard` reports `ok=True` with zero cases checked) are both tooling defects, both found by execution rather than reading, and neither is derivable from anything the current docs say about `tools/`.

**Consequence for passes.** What was "pass 2 = blinded review" becomes: rework to the new scope, THEN blinded review of the reworked whole. The verification discipline does not relax — the new material (PEG rationale, stdlib-only, requirements) is more universally-quantified prose, which is the artifact type #07 proved unreliable.

## Diagram inventory (Arnon, 2026-08-12: "the diagrams you started sketching are fine... but more small diagrams help understanding")

**Many small single-idea diagrams, not four big ones.** Each one answers exactly one question; if a diagram needs a paragraph to introduce it, it is two diagrams. This also relieves the prose-density complaint without rewriting prose — most dense paragraphs here are dense because they describe a *structure* in sentences.

Rules: one `.mmd` source file per diagram under `docs/diagrams/`, rendered to SVG with `mmdc`, document embeds the rendered form and links the source. **`mmdc` verified working on this box 2026-08-12** (`/home/arnon/.nvm/versions/node/v24.16.0/bin/mmdc`, trivial two-node graph rendered to a 10,687-byte SVG, exit 0) — headless Chromium launches fine under WSL, so the rework does not need a fallback path. **After-state only** — no before/after pairs; the "before" stops mattering once this ships.

Candidate set. The agent must justify each inclusion or drop it; a diagram nobody would consult is cost, not help.

| # | Question it answers | Status |
|---|---|---|
| 1 | What constraints produced this architecture? | new — leads the document |
| 2 | Process model: one process per tool call, what that forbids | new |
| 3 | Core vs tooling: what each half may do | new — carries item 7 |
| 4 | The eight-layer stack | have it (pass 1) |
| 5 | Why `api` exists (the `runtime -> tooling` edge it removed) | new — small, one idea |
| 6 | The three verdict altitudes | have it (pass 1) |
| 7 | Live hook lifecycle: stdin to stdout | split out of pass 1's big flow |
| 8 | The resolution cascade itself | split out of pass 1's big flow |
| 9 | Hierarchy: most-specific-level-wins across config levels | new |
| 10 | Hard-deny pooling and why nothing overrides it | new |
| 11 | PEG decomposition of a compound command into leaves | new — carries the grammar rationale |
| 12 | Strictest-wins combination (deny > ask > allow) | new |
| 13 | Parse-failure ASK floor, including the already-deny exemption | new — the claim we keep getting wrong; a diagram makes the exemption unmissable |
| 14 | Pattern-mode dispatch (DEFAULT / REGEX / GLOB / NATIVE) | harvest from `architecture.md` |
| 15 | The guarded write chokepoint and its three checks | harvest from `architecture.md` |
| 16 | The four log streams | harvest from `architecture.md` |
| 17 | The Protocol seam / the coupling no import graph shows | have it (pass 1) |

Pass 1's single large decision-path diagram becomes 7 + 8, and probably 10 and 13 as well — it is currently four questions in one picture, which is the specific failure "more small diagrams" is aimed at.

## Diagram convention, established end-to-end 2026-08-12 (four built, rendered, inspected)

`docs/diagrams/` now holds **seven** working `.mmd` sources and their rendered `.svg`: `layer-stack`, `verdict-altitudes`, `hook-lifecycle`, `resolution-cascade`, `parse-failure-floor`, `protocol-seam`, `core-vs-tooling`. The convention is proven end-to-end, not proposed — follow it rather than reinventing it.

**Six are embedded in `docs/architecture-as-built.md`; zero raw ```` ```mermaid ```` fences remain.** Embed form, paths relative to `docs/`:

```
<img src="diagrams/name.png" alt="Alt text" width="50%">

<sub>[diagram source](diagrams/name.mmd)</sub>
```

**HTML `<img>`, not markdown `![]()`, and `width` — NOT `style`. Decided by Arnon 2026-08-14 after looking at rendered variants.**

The PNGs are rendered at `-s 2` for print quality and were displaying at roughly twice a comfortable reading size. **Markdown image syntax cannot carry a size**, so the embed had to become HTML.

**`style="width: 50%"` is the trap here**: local renderers honour it — Arnon confirmed a `style` variant scaling correctly in his IDE — but **GitHub's sanitizer strips `style` entirely**, so it would render full-size on the platform where these are mostly read, and the failure would only appear after a push. `width` is in GitHub's allowlist; `style` is in nobody's.

Two consequences worth carrying:

- **Alt text must be written explicitly.** `![alt](src)` carries it for free; `<img>` does not. It is what a screen reader gets and what shows when an image fails to load.
- **A percentage is relative to the container**, so it renders differently in a narrow IDE pane than in GitHub's column. That is the intended behaviour here; a pixel width would be predictable but not responsive.

Checked and clear: `tools/check_doc_links.py` only validates **anchored** links (`...#section`), so image references were never in its scope and the change regresses nothing. The `grep -o 'diagrams/...'` invariant is a substring match and survives the new form.

**Embed PNG, not SVG. This was paid for twice.** SVG was tried first and failed in both the JetBrains preview and an external markdown editor, while rendering perfectly when opened standalone. Two independent renderers failing on the embed but not on the file is the signature of **markdown renderers refusing SVG through image syntax** — it is not fixable inside the SVG. (A separate, real SVG defect was found and fixed along the way — mermaid emits all label text inside `foreignObject`, which `<img>` will not paint, and `width="100%"` with no height gives no intrinsic size. Both were genuine and both were the *wrong* diagnosis for the reported symptom. Fixing a real bug is not evidence that it was *the* bug.)

Render command — `-s 2` for high-DPI, `-b white` so the background is not transparent on dark themes:

```
mmdc -c docs/diagrams/mermaid-config.json -i X.mmd -o X.png -s 2 -b white
```

`docs/diagrams/mermaid-config.json` is committed so renders are reproducible. PNG rasterises through a real browser, so HTML labels work and `<b>`/`<i>` emphasis is available in sources. **Two files per diagram: `.mmd` source, `.png` artifact.** No `.svg` — a third file only raises "which one is canonical".

`core-vs-tooling.svg` is built but **deliberately unreferenced** — the core/tooling section (round-2 item 7) does not exist yet. It is ready for that section, not forgotten. Pass 1's single large decision-path diagram has already been **split into `hook-lifecycle` + `resolution-cascade`** per the inventory.

Check both invariants after any diagram edit — no orphans, no dangling references:

```
grep -c '^```mermaid' docs/architecture-as-built.md          # must be 0
grep -o 'diagrams/[a-z-]*\.\(svg\|mmd\)' docs/architecture-as-built.md | sort -u   # all must exist
```

Render loop (authored shell, disclose it):

```
cd docs/diagrams && for f in *.mmd; do mmdc -i "$f" -o "${f%.mmd}.svg"; done
```

**Rules learned by doing, each one paid for:**

- **TWO BLINDED PASSES REACHED THE SAME CONCLUSION, AND THE SECOND ONE SAYS IT IS "REDUCED, NOT FIXED".** Review 1 found 13 falsehoods, every one in a table cell, a diagram node, or a compressing sentence. Review 2 covered only the material added afterwards — by authors who had been *told* about the failure mode — and **both of its substantive findings were again in a short, hedgeless diagram NOTE box.**

  So this is not a lapse that awareness fixes. **The short form is the defect surface**, and a note box is the shortest form in the document. One of review 2's findings asserted an *"only"* that **the same document contradicts two sections earlier**; the other quoted a reason string **the documented code path cannot emit**.

  **Practical rule: a NOTE box describes the path its diagram describes, and nothing wider.** Both offending notes made a whole-system claim while the diagram showed one path. And when a diagram and the prose disagree on a number, **check the diagram first** — review 2 found the prose saying three importers and the diagram saying five, with the diagram right.

- **THE PROSE IS MEASURED; THE TABLES AND THE SUMMARISING SENTENCES ARE NOT.** The blinded reviewer's closing observation, and the single most useful thing this pass produced: **every one of the 13 falsehoods it found sat in a table cell, a diagram node, or a sentence compressing a hedged paragraph into an absolute.** None was in a paragraph that had been written carefully.

  The mechanism is worth naming: a writer verifies a claim, writes it hedged and correct, and then **summarises it** — in a row, a node label, or a closing sentence — and the summary drops the hedge. The drop is invisible to the writer because the correct version is right there above it.

  **So review tables, diagram labels and topic sentences at a different rate than prose**, and when correcting one, check whether the paragraph above it is already right and the summary is the only lie. It usually is.

  It cuts both ways: the same document's list of *remaining* gaps was more pessimistic than the code, while its list of *closed* gaps was more optimistic. Absolutes fail in whichever direction the writer was leaning.

- **INSPECTING A DIAGRAM AS AN IMAGE VERIFIES LEGIBILITY, NOT TRUTH.** Found 2026-08-14: `core-vs-tooling.mmd` asserted *"fails open, never blocks"* — **false**, the hook fails **closed**, and the fail-open it exists to prevent is exit-0-with-no-decision. That diagram had already been built *and* inspected under this very rule, and the inspection caught layout problems while the false claim went straight through. **Verify the claims in a diagram the same way you verify claims in prose: by execution or grep.** A diagram is a pile of universally quantified assertions with the words removed.
- **"It rendered" is not "it is readable." INSPECT EVERY DIAGRAM AS AN IMAGE.** The first `core-vs-tooling` exited 0 and produced a 21 KB SVG that was genuinely unusable — notes floating unattached, an arrow visually colliding with an unrelated box, and the two halves in reverse reading order. Rasterise to PNG in the **scratchpad** (never the repo) and actually look at it. This is the same lesson as #07's: **exit code 0 is not verification**, and a non-zero byte count is not a picture.
- **Never link a subgraph** (`CORE -.- NOTE`, `CORE --> API`). Mermaid routes subgraph-level edges badly and the note lands loose. Link real nodes inside the subgraph, and put constraint/annotation text **inside** the subgraph as a dashed-border node.
- **Subgraph declaration order is reversed in layout**: the subgraph declared *later* renders further *left*. Declare the one you want read second first.
- Frontmatter `--- title: ... ---` gives every diagram a caption for free; use it to state the question the diagram answers.
- Shared `classDef` palette across diagrams so colour means the same thing everywhere: green = core/unchanged/safe, orange = tooling/clamped, blue = seam or shared type, purple = level-scoped, white dashed = annotation.
- Diagrams are **after-state only** and must be verified against code, not against the pass-1 draft's description of the code. `parse-failure-floor` was drawn from `permission_resolution.py:125` (`if not parse_failures or decision == "deny"`) directly; `layer-stack` from `.pyscn.toml` lines 170-235 directly.

**`parse-failure-floor` is the proof of the whole approach.** The already-deny exemption has now been stated wrongly in four places in prose, including a user-facing string still live in `config.py`. As a two-exit branch in a picture it cannot be skimmed past. Where a claim keeps getting lost in prose, that is the signal to draw it.

## Sources

Code first: `toolguard/`, `.pyscn.toml` (the layer map), `tools/architecture_fitness.py` (what is machine-checked, and therefore what cannot silently rot).

Then the branch-side report material named by ticket 09 — `reports/core-types-and-clarity.md`, `dependencies-before-after.md`, `layer-separation-before-after.md`, `end-state-summary.md` — with **every before/after diagram redrawn as after-only.** The "before" stops mattering once this ships.

`technical-notes.md` holds design rationale and is the other place this material currently lives; the two must not contradict each other.

## Known traps, from the sweep

- **`resolve.py:2` claims "Pure, side-effect-free permission resolver layer"** while matching reads live disk state (`normalization.py` — `exists()`, `is_symlink()`, `resolve()`). Do not repeat that claim in the document.
- *"A broken config file clamps **every** decision to `ask`"* is **false** — an already-`deny` decision is exempt. Corrected hedged form at `config.py:1526`. It has appeared in four places already.
- The layer map is **gameable**: five one-line edits were tried against the one remaining violation and three erased it with nothing catching the edit. Only completeness is pinned by a test; direction is not. If the document says the layer model is enforced, it must say **exactly what is and is not enforced.**