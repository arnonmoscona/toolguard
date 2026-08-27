---
title: TOO-45 comment standard
type: note
permalink: toolguard/too-45/too-45-comment-standard
tags:
- task-memory
- TOO-45
---

# The comment standard for punch-list #07

## The test

**Read the module. Does it make sense?**

A reader who never saw the ticket should come away understanding what the module does and what they must not get wrong, without wading through anything that did not help them get there.

There is no target number — not of lines, words, ratios, or ticket references. **Any number here gets optimised instead of the thing it stands for, and that has already happened once on this item**: a first attempt driven by a ticket-reference count deleted the IDs, left the useless prose in place, satisfied its own metric, and made the codebase worse. Measurement has one legitimate use: finding files worth looking at. It never says a file is done.

## The rules that do most of the work

These came from Arnon's review of the first accepted file. They are in rough order of how much text they remove.

**0. A claim that reaches outside its own file is where the falsehoods live.** Measured across five modules: nearly every false statement found was an assertion about *another* module's behaviour — what the hook does, what a caller reads, what the package as a whole guarantees. Nothing reviewing this file will ever check those, so they rot silently and are believed. `config.py`'s constant doc-comments say what the value is and what constrains it, and do not reach outward; that is the difference between the accepted files and the rest. **Prefer scoping every claim to the file it sits in. When a sentence asserts something about another module, prefer deleting it to correcting it** — the fact belongs where it is implemented, and that is where someone will look.

**1. Never document anything static analysis can find.** Callers, call graphs, "used by X", "the only importer is Y", "mirrors Z". Whoever is reading has an IDE; whoever is editing has grep and an LSP. This text is pure cost: it is long, it goes stale silently, and it is wrong often enough to mislead. *Applies across the board.*

**2. Do not explain short, simple code.** A paragraph explaining a one-line private function is always wrong. A three-line rationale on a function whose body is a single expression is always wrong. Low cognitive complexity needs no commentary.

**3. When complexity genuinely needs explanation, put it in the body, next to the complexity — not in the docstring.** And first ask whether the answer is to **simplify instead of explain**. A function that needs heavy commentary to follow is usually a function that should be split.

**4. Public and private are held to different standards.**
- **Public** (the module's external interface) tolerates more detail — but about the **external contract and how it is used**, briefly. *Not* about how it works.
- **Private** gets less. It is read in the narrow scope of its own module by someone who can see the body.

**5. Know who the audience is.** Arnon, 2026-08-11: *"the comments are mostly for you when they help you and for me when I read the code."* Two proficient readers. No documentation site exists today; if one is ever built it would be great-docs, which as far as he knows also understands Sphinx markup — so **the existing reST roles stay**, they are a possible future asset and stripping them tree-wide would be churn for style. What follows from the audience is only this: prefer the shortest reference that is unambiguous to those two readers, and do not *add* new fully-qualified `:func:`~pkg.mod.name`` chains where a bare name reads better, particularly for a target in the same module.

`#:` versus an attribute docstring is likewise a readability choice, not a convention question — and a real attribute docstring is an AST node, hence a *code* change, so `#:` is the only form available under a comments-only rule.

**5a. Assume a proficient reader.** They need to know *which particulars to pay attention to*, not to be taught. A justified explanation at a third of its length is easier to understand, not harder. Long is not thorough; long is unread.

**6. When a long explanation IS justified, say so.** `Intentionally two-directory-only:` earns the paragraph that follows it by telling the reader this is deliberate and worth their attention. **This is not a licence to prepend attention-phrases as an excuse for length** — it is what you do on the rare occasion length is already warranted.

**7. Justification is about the mistake, not the code.** `_multiline_structured_entry_diagnostic` is simple code with a long explanation, and that is correct: the syntax error it detects is very easy to make, with hard evidence of both humans and agents making it. **Weigh how likely and how costly the mistake is, not how complex the code is.** Judgement beats pattern here.

**8. Constants get docstrings, not hash comments.** Same content, proper form.

**9. There is no backward compatibility to preserve.** toolguard is self-contained; nothing outside it imports it. Any comment justifying something "so existing importers keep working" is defending a requirement that does not exist — cut the comment, and flag the code if it exists only for that reason.

## Claims this codebase keeps getting wrong — check these in every file

Not a checklist to satisfy; a list of assertions that have already been found false in more than one module. If a file makes one of these claims, verify it before keeping it.

- **What happens when a config file fails to parse.** Found wrong in three separate files, in three different directions: "fail-open policy" (it is fail-*safe*), "fail-closed to `deny`" (it resolves to `'ask'`), and "EVERY decision is clamped to `'ask'`" (an already-`deny` verdict is exempt, and that exemption is defended by a named regression test). The truth: `permission_resolution` clamps every governed decision to `'ask'` **except** one already resolved to `'deny'`, and an entirely unconfigured tool resolves to `'ask'` so a fresh install is never bricked.
- **Enumerations of legal values.** `no_match_fallback` and `undecidable_fallback` each take four values; docstrings have dropped one, twice, and the dropped one was `'allow_with_warning'` both times — the value that produces the WARNING stream. **Count every enumeration against its `_VALID_*` frozenset.**
- **Which tools are file-kind versus command-kind.** The complement of `{Read, Write, Edit}` is not "Bash" — MCP terminal tools are command-kind too.
- **"Only caller" / "used by X" claims.** Wrong more often than right, and rule 1 says they should not be there at all.
- **What a test does.** Two prescriptive warnings cited test behaviour that the test file contradicts. Open the test.
- **Pattern-matching semantics.** Wildcards, separators, anchoring, newlines, case. Two were found wrong in one file: `fnmatch`'s `*` already crosses `/`, so the `*`-versus-`**` distinction holds only for GLOB patterns; and only DEFAULT patterns are newline-restricted, because the bypass branch runs before the guard. **Run the matcher in an interpreter. A claim about matching semantics that has not been executed has not been verified** — this is the one area where reading the code carefully is reliably not enough.
- **Claims about the past.** "This used to…", "nothing writes this anymore", "kept for the old format". These are checkable with `git log -S '<the string>'` and they are often wrong — on one file, two legacy-filename constants described a history that never happened: the names appear in exactly one commit in the whole repository, the one that *added the cleanup code for them*. **A past-tense claim is a factual claim; verify it or cut it**, and prefer cutting, since history belongs to git either way.

## Keep / cut / move

**Keep** — what a competent reader cannot get from the code: what the thing is, what it takes, what it returns; a non-obvious constraint or invariant; a runtime corner case or failure mode; a *why* that is genuinely not evident, especially where the obvious alternative is wrong and someone would otherwise "fix" it back. Keep the hazard, drop its history.

**Cut** — anything derivable by reading the body; change history in any form; ticket narrative and phase/increment labels; arguments with a hypothetical future maintainer; the same fact restated in one docstring; cross-references that exist to show the author checked something.

**Move** — real design rationale too long for a docstring goes to `technical-notes.md` with a one-line pointer. **Deleting genuine knowledge is a different failure with the same cause.** But prefer cutting to moving for anything scoped to one private function: in `technical-notes.md` it is a *bigger* drift risk, because it is further from the code.

**Pointer instead of argument, not both.** Moving something means the code keeps a one-line pointer and the argument lives in one place. A docstring that restates the relocated section *and then* links to it has added text rather than moved it, and created a second copy to drift.

**Never write a pointer to something that is not there yet.** The opposite failure, and the worse one: replacing an inline explanation with "see technical-notes.md" or "see X's docstring" when that section or docstring does not contain it. The argument then lives in **zero** places and the reader's search ends nowhere — strictly worse than the verbosity it replaced. Two of these were produced in a single pass on `resolve.py`, one of them forming a closed loop with `file_matching.py`, which pointed back at the site that now pointed away.

**Before writing any pointer, open the target and confirm it says the thing.** And if you are not permitted to edit the destination — as in a concurrent run where `technical-notes.md` is off limits — then **keep the content inline** and propose the move in your report. Relocation is a two-step operation; do not perform the first half alone.

**One fact, one home.** When the same point is worth making in several places, it is worth making in the most specific one and nowhere else. If a fact appears in a module docstring, two wrappers, the function it is about, and `technical-notes.md`, four of those five are noise — and they will diverge.

## When you are unsure, cut

Given how many comments in this codebase turned out to be false, contradictory or misleading, **no comments at all would still be an improvement on the starting point.** So:

- Unsure whether a comment earns its place? **Cut it.**
- Unsure whether a claim is true? **Verify it, or cut it. Never keep an unverified claim.**

**A hazard note is not exempt — it is the most costly kind to get wrong.** Everything above says to keep a *why that is genuinely not evident*, especially where the obvious alternative is wrong. That protection makes a **false** hazard permanent: it is prescriptive ("do NOT clean this up", "X depends on this exact shape"), it will be believed, and the standard itself shields it from deletion. Two were found on one file — one claiming tests patch `datetime.now` with a `side_effect` list when they use a fixed `return_value`, one claiming a consumer depends on a record shape it actually *skips*. **Before keeping any prescriptive warning, open the test, open the consumer, and confirm the thing it warns about is real.** A hazard you cannot verify is not a hazard; it is a rumour.

**And this applies to what you KEEP, not only to what you write.** Measured on `config_types.py`: six of seven false claims were pre-existing text carried through untouched — *"shortening was done carefully; verifying was not done at all."* Every editing pass so far has verified its own new wording and waved through the sentences it did not edit. **A sentence you leave in place is a sentence you are vouching for.** Walk the surviving prose and check each factual assertion against the code, weighting anything that reaches outside the file.

A missing comment costs a reader time. A false one sends them the wrong way and is trusted while doing it.

## Comment distribution is a refactoring signal

**If a docstring numbers the things a function does**, the function should probably be that many functions, each named for what it does and needing far less explanation as a result. `config.validation_issues` is the worked example: seven rules in one body, each with its own comment, is seven private methods and a delegating accumulator.

**And the enumeration is not required.** A long function whose *branches* each need their own commentary is the same signal without the numbering — `compound.judge_unit` carries eleven inline blocks across its conditionals, and those comments would read perfectly well as the docstrings of the extracted branch functions. Arnon caught this from the shape alone after two reviewers and an editor missed it. **Look at where the comments cluster, not just whether they are numbered.**

**In this ticket you may not act on it — comments only.** Flag it in `reports/follow-up-queue.md` and move on.

## Which tree you are in

**`toolguard/`** — everything above applies in full. This is where judgement is required and where Arnon reviews.

**`test/`** — far simpler. A test docstring keeps its Given/When/Then and **that is all it keeps**; every other comment in a test file is deleted outright. The one real job is that **the Given/When/Then must correctly describe what the test actually does** — a stale one is worse than none, since it reports what the test was supposed to check. That verification is *local* to the test body, which is what makes the test tree tractable at speed.

**`tools/`** — dev instruments. Treat as production; lower stakes, same rules.

## Comments only. Strings are code.

**The allowed scope is comments and docstrings, full stop.** A message string, a `corrective_steps` text, any literal is **code** and does not change here **even when it is wrong**. Verifying a comment sweep is confusing enough without a code change hidden inside it.

Found a false string? **Flag it** in the code-level defects table in `reports/follow-up-queue.md`, with the refuting code, and leave it alone. This means code and comments will disagree until the flagged item is fixed separately — that is the intended trade, because the disagreement is recorded and visible where a silent code edit would not be.

**Acceptance test: `tools/comment_hygiene.py --compare-against HEAD` reports zero code-shape drift.** Not "one expected difference" — zero.

## Arnon reviews the final file, never the diff

1. **A deleted fact is invisible in the final outcome.** The loss check — did a hazard, invariant or corner case disappear, and does it survive in the code, another comment, or `technical-notes.md` — is **entirely the reviewer agent's job**, done against the diff before handover. It can never be delegated to the human.
2. **The code-shape proof is what makes skipping the diff safe.** Its job is to guarantee no logic moved among the prose.
3. Nothing but comments changes, so there is nothing else to disclose.

## Process

**One file at a time.** An editor pass rewrites every comment and docstring. A separate reviewer, working from the rewritten file read cold and then from the diff, returns what is still wrong. Repeat until nothing comes back.

The reviewer answers, in order:

1. **Read the module cold. Does it make sense?** Anything that stops you, or that you read twice, is the finding.
2. **Verify every checkable claim against the code.** Return shapes, which aliases a resolver honours, what is public, what a function does *not* do, whether a stated guard is the whole guard. This step finds the most.
3. **Is anything worth keeping now missing?**
4. **Is anything still present that should not be?**

The reviewer must never check whether any count went down.

**Known failure mode, seen in seven consecutive passes across two files: compression adds quantifiers.** "only", "every", "never", "always" appear in shortened text where the original was hedged, because the short form wants a crisp universal and reality is not. After any pass, re-read every place two sentences became one and verify the *specific* claim it now makes — not its general sense — against the code.

**When it happens, the first question is not how to state it accurately in fewer words.** It is: **does the accurate form earn its place at all, or can the whole statement go without harming the comment?** A statement that resists compression is often a statement carrying more detail than it is worth. Deleting it is a legitimate and frequently better answer than fixing it.

Why deletion is favoured: **every statement in a comment is an ongoing tax.** It can drift, and it must be re-read and re-verified every time anyone touches the code. It therefore has to justify a recurring cost, not a one-time writing cost — and volume alone is a cost even when every sentence is true.

**Compression turns a hedged negative into an unqualified positive, and narrows what can be true.** "None of X's parameters are typed against this Protocol" is true even where a parameter carries no annotation at all. Rewrite it as "they are typed against that one instead" and it becomes false of the unannotated case. A negative claim covers absence; its positive restatement does not. **When you flip a negation, check the cases the negative form quietly covered.**

**When a deletion leaves a gap, the default is to leave the gap.** On `file_matching.py` every defect in a pass came from prose the pass *wrote*, not from what it cut — the cuts were all sound. Text you add to fill a hole carries exactly the same verification burden as text you found, and you have less evidence for it. If the code reads fine without the sentence, that is the answer.

**Deleting a clause can strand the antecedent the surviving clauses depended on.** On `log_writer.py`, cutting a false contrast also removed the words "a missing directory", and the remaining sentence — *"Creates the directory when `create_log_dir` is set; otherwise warns and disables logging"* — became a false universal: with the flag at its default and the directory present, which is every normal run, neither half happens. **After any deletion, re-read the surrounding sentence as a stranger would and ask what it is now quantified over.** The scope-setting words are often in the part you removed.

**When a justification turns out to be unsupported, delete it — do not supply a different one.** Seen on `once_per_store.py`: told that a constant's stated reason was unsupported, the pass cut it and wrote a fresh plausible reason in its place. The original was the true one and the replacement was invented. **Supplying a new rationale for code you did not write is inventing knowledge, and it is worse than the unsupported claim, because it reads as verified.** If you do not know why the code is the way it is, say nothing.

**Sharpening a vague claim can create a false one.** A woolly sentence is often too imprecise to be wrong; replace it with something checkable and it becomes checkably wrong. Seen on `log_writer.py`: *"a vague stale claim was sharpened into a checkable wrong one."* **Making prose precise is an edit that needs verifying, exactly like shortening it** — and if the vague original was carrying no real content, the answer is deletion rather than a sharper version of nothing.

**Compression also picks the wrong half.** It does not only add false universals. Given "A **or** B", a shortened form keeps one — and it may keep the one that cannot happen. Seen here: a note naming two collision sources, `additionalContext` *or* a pattern name, compressed to the first, which never reaches the function at all. When you shorten a disjunction, check which half is real before choosing.

**Deleting a named anchor breaks pointers from other files.** A distinctive title inside a docstring ("Fabrication guard", "Intentionally two-directory-only") is a cross-reference target other modules point at by name, and nothing catches the break. **Before removing or re-titling one, grep the repo for the phrase.** Fix it on the side you are already editing rather than opening another file.

**Add on evidence, not on estimation.** Most comments are written from a guess about what a future reader might want. That guess is usually wrong and always unfalsifiable. A statement can be added later, when an actual reader actually stumbles — and then it will be aimed at a real gap rather than an imagined one. Absence is cheap to fix; accumulated speculative prose is not.
