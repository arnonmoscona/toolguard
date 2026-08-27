---
title: 04-implementation-and-abstraction-habits
type: note
permalink: toolguard/durable/04-implementation-and-abstraction-habits
---

# Implementation and abstraction habits: how the agents on this campaign wrote bad code

Extracted 2026-08-23 from `TOO-45/`, `TOO-19/`, `implementation/` and `TOO-45/reports/` so those notes can be deleted. Companion to `01-claude-failure-modes-and-mitigations.md`, which covers failures of **reasoning and reporting**. This document covers failures of **design and implementation** — the recurring ways the agents on this campaign produced code that worked and was nonetheless wrong-shaped.

## How to read this

**Every habit below rests on either two or more independent instances, or one instance with a real measurement.** Which one it is, is stated at the top of each entry. A single anecdote with no number is not in here.

**Each entry ends with a RULE.** The rule is the deliverable. The anecdote is evidence for it, and it is included only so a future agent can check whether the rule still applies to the code in front of it.

**Status lines distinguish fixed from live.** Where an entry says a habit is still present at HEAD, I verified it by reading `/home/arnon/projects/toolguard/toolguard/` today and say so at the point of the claim. Where a number is quoted from a source, the source path is given; paths are relative to `toolguard-memories/` unless they start with `toolguard/`, which means the package.

**Numbers keep their original hedges.** Two of the measurements below are explicitly labelled by their own sources as a floor rather than a ceiling, and one headline count was corrected downward by the ticket that produced it. Those qualifications travel.

---

## 1. Prose used as a data structure

**Basis: one measured instance with a large cost, plus at least five further sites and a residual that is live at HEAD.**

### What happened

`config.py` computed a matched pattern, used it to look up provenance, appended the provenance to a human-readable reason string as a `"  [...]"` suffix, **discarded the pattern**, and returned the string. The caller then stripped the suffix it had just added and matched three English-language sentence prefixes to get the value back (`TOO-45/reports/core-types-and-clarity.md`). Separately, `hook._log_allowed_command` recovered the per-sub-command audit breakdown by regex over that same reason prose, keeping only segments containing `" -> "`.

### The measurement

Two independent readings, and they agree to within a denominator definition:

| | ticket headline (`TOO-45/reports/end-state-summary.md`) | independent corpus replay (`TOO-45/reports/core-types-and-clarity.md`) |
|---|---|---|
| compound-allow cases under-logged | **813 of 975 (83%)** | **814 of 978 (83.2%)** |
| sub-commands executed with no audit record at all | **1,943** | **1,956 of 3,607 (54.2%)** |

The replay report explains the gap: *"975 vs 978 is master's own `sub_matches` under-counting escape-hatch leaves, and 1,943 vs 1,956 follows from that same denominator."* It also credits the old code the single whole-command entry it writes when prose recovery yields nothing, so its 1,651-entries-written figure is called *"the generous reading."*

Two further facts from `end-state-summary.md` that matter more than the percentage: **811 of the 813 were in the real-traffic fixture** — this was ordinary use, not synthetic edge cases — and the **worst observed case executed ten sub-commands and wrote one entry.**

The mechanism was one line: `if " -> " in part`. A sub-command allowed by `no_match_fallback` produces a reason with no `" -> "` in it, so it was silently dropped. **The commands still ran.**

The waste, over one 6,401-case corpus replay: **8,304 render-then-re-parse round trips, 17,223 literal-prefix comparisons, 3,923 successful `rindex("  [")` string surgeries** (`core-types-and-clarity.md`). Wall clock was unchanged (9.03 s → 8.76 s) and the report says so plainly — *"If you came looking for a performance win, this is a wash."*

### Where else it appeared

- **`compound.fallback_kind_for_reason`** classified an outcome by substring-matching five markers in the program's own rendered prose (`TOO-45/proposed-tickets/38-fallback-kind-is-re-derived-from-prose.md`). That ticket also contains a correction worth carrying: it claimed a reword would break classification *silently*, and measuring it found **5 test failures above baseline** — the marker text was pinned. *"The ticket's central alarm was inherited from a docstring rather than measured, and the docstring is wrong about its own module."* The design objection survived; the urgency claim did not.
- **The precedent had already been set and ignored.** `fallback_warning`'s own docstring says it replaced a substring-marker approach for exactly this reason (`TOO-45/reports/retrospective.md` §11.2). *"R3 finished a job someone had already started once — which is itself a diagnostic: a fix applied once and not generalised is where the next instance will be."*
- **The fix for one unit kind masked the same parse in another.** `TOO-45/proposed-tickets/90-plain-unit-prose-still-re-parsed-by-combine-strictest.md`: ticket 79 gave `'inline_code'` units a structured tag so the outer combine never had to guess from text, and left the `'plain'` path re-parsing its own already-rendered summary. Observable symptom: a golden line went from 14/16 to 11/12 brackets — *"still unbalanced"* — and an extra `]` survives into the final reason.

### Status: mostly fixed, one instance live at HEAD, and the detector cannot see it

`fallback_kind_for_reason` and `_FALLBACK_REASON_MARKERS` are **gone** from the package (grepped, zero hits). `RuntimeVerdict` and `UnitVerdict` now carry `matched_rule` and `fallback_kind` as structured fields, and `UnitVerdict.matched_rule`'s docstring ends *"Not derived from reason"* (`toolguard/config_types.py`).

**But ticket 90's site is still there.** I read `toolguard/compound.py:1114-1131` today: inside `_combine_strictest` it does `r = uv.reason`, then `if " -> " in r:`, then `pattern_part = r.split(" -> ", 1)[-1]` — recovering the matched pattern from prose in the same function whose `UnitVerdict` argument carries it as a field.

**And the fitness tool reports R3 PASS over it.** I ran `uv run python tools/architecture_fitness.py --predicates` today: R3 reports zero sites, with one exclusion — `R3_SANCTIONED_SITES = {("compound.py", "fallback_kind_for_reason")}` — naming a function that no longer exists. The detector is name-based, not data-flow, and says so in its own docstring; it keys on a receiver *"whose OWN name contains 'reason'"*. The live site's receiver is named `r`.

I confirmed this with a paired control rather than by inference: two files performing the identical parse, differing only in whether the local is called `reason` or `r`. The `reason`-named one was reported at 2 sites; the `r`-named one was reported **zero** times. The control fired, so the instrument was working — it simply cannot see this.

> **RULE.** Never recover a value from a rendered string when the producer still holds it structured. If a function returns prose and the caller needs a fact from that prose, return both — the fact as data, the prose for display. Review question: *"where did this string come from, and does the producer still hold the parts?"* If the producer is in the same process, the answer is almost always yes, and the recovery is a bug report against the producer's interface, not a parsing task.
>
> **Corollary, from the R3 blindness above:** a name-based detector for this habit is defeated by a one-character rename. Do not read an R3 PASS as evidence; read the code.

---

## 2. Re-deriving downstream what the owning component already knows

**Basis: at least four independent instances, three of them counted as such by the campaign at the time.**

The project's standing constraint is that all bash parsing goes through the PEG grammar. The recurring violation is not writing a whole parser — it is re-deriving in Python one specific fact the grammar has already established.

- **`_statement_bounds_containing`** in `multiline.py` re-derived which command owns a heredoc by splitting on `&&`, `||`, `;`, `&` — which is `control_op`, *"a rule the grammar already has"* (`TOO-45/proposed-tickets/98-heredoc-sink-classification-hand-rolls-a-statement-splitter.md`). Raised by Arnon: *"This needs serious justification. I don't like it at all."* The ticket separates what is genuinely forced (a heredoc terminator is context-sensitive; a PEG has no backreferences, so body extraction must precede the grammar) from what is not (*"deciding which command a heredoc belongs to is a structural question, and the grammar answers it"*).
- **`_classify_pipeline_sink`** segmented on `|` only while the grammar already knew `&&`, `||`, `;` — recorded as *"the third instance of 'the grammar already knows, the Python discards it'"* (`TOO-45/TOO-45 phase 3 resume.md`).
- **`tools/mining._command_key`** hand-rolled bash tokenization. Measured consequence, from `TOO-45/proposed-tickets/75-mining-hand-rolls-bash-parsing...md`: `"# INTENT: x\ngit status"` keys as **`#`**, and `TG_INTENT=1 uv run python x.py` keys as **`TG_INTENT=1`**. *"Every disclosed command this project mandates lands in a single meaningless `#` bucket"* — the analyzer was defeated by the repository's own mandated disclosure convention.
- **`_strip_comments`** was believed to be a fourth instance and **was not**, which is why it is the most instructive entry here. See habit 9.

The 98 ticket's spike results are the strongest single piece of evidence that the *structure* was the problem rather than its bugs. Three alternative designs were built and run against a shared 16-case set (`98-...md`): the shipped module scored **14/16** with **5 quote scanners**; designs A, B and C each scored **16/16** with 1 quote scanner. *"All three fix cases 15 and 16, which the shipped module fails... Neither was targeted; the architectures simply lack those failure modes."*

### Status: fixed for `multiline.py`

I read `toolguard/parser/multiline.py` today: `_statement_bounds_containing`, `_split_on_unquoted_pipe` and `_strip_comments` are all gone. What remains is lexical — line endings, backslash joins, heredoc lifting, whitespace collapse. Sink attribution moved out, per Arnon's decision in ticket 98: *"Most of that code I am not sure belongs in multiline.py. It looks and feels like code that should be in parser/command_extractor.py and parser/command_model.py."* Ticket 75 is marked partially fixed in its own header — tokenization now routes through `extract_commands`; the `TG_INTENT=1` bucketing was still open at the time of writing.

> **RULE.** Before writing code that decides a structural fact about an input, ask whether the component that owns that input already decided it. If it did, consume its answer; if it did not, the change belongs in that component. The only legitimate reason to keep work out of the owning component is a genuine limitation of that component — and *name* the limitation, because "it was easier here" and "PEG has no backreferences" look identical from the outside once written.

---

## 3. One concept, several hand-written copies

**Basis: five instances counted by the campaign in one ticket, plus at least three more.**

`TOO-45/proposed-tickets/96-file-path-handler-inlines-what-the-command-handler-factored-out.md` states the running tally: *"This campaign has now paid four times for one concept with several hand-written copies — `_pick_strictest`, `all_parts`, `_corpus_verdict`, and the third `_atomic_write`. This is a fifth instance, sitting on the permission-decision path."*

Others found independently:

- **Four implementations of "once per session."** `TOO-45/proposed-tickets/01-once-per-session-warnings.md`: *"'Once per session' has been wanted three times and implemented zero times. The codebase carries three copy-pasted date-marker mechanisms plus module globals in `hook.py` whose own docstrings concede they cannot work."* `session_warnings.py` is the fourth. *"Four implementations of one idea is the actual defect."*
- **The tool registry, written twice more.** `TOO-45/proposed-tickets/74-item-10s-conversion-stopped-at-the-hook...md` finding 5: `rule_sort.get_tool_priority` hardcodes `{"Bash": 0, "Read": 1, "Write": 2, "Edit": 3}` while `tool_spec.TOOLS_BY_NAME` declares five tools. *"Two hand-maintained lists edited independently."*
- **The decision cascade, re-implemented in the test suite.** `TOO-45/reports/end-state-summary.md`: *"`test_hook.py`'s fake config hand-implemented `resolve_permission_detailed` in ~35 lines whose own comment admitted it was 'API-sync' with the real thing. Those hook tests were exercising a copy, not the product."*

### Two method notes that came out of this

**Mutation testing finds the second copy.** `TOO-45/reports/retrospective.md` finding 6: *"A mutation that refuses to change behaviour is pointing at a second implementation. That is how the duplicated undecidable floor was found."*

**A clone detector does not.** `96-...md` records pyscn flagging `hook.py:1067` and `:1149` as an *"80-line group at 0.98 similarity"* — the package's highest-confidence clone — and the ticket's own reading found *"the similarity is mostly the docstrings, which are long, parallel, and part of the AST that APTED compares."* The genuine duplication was an 11-line block, and the ticket names the line counts (55 vs 44) that show it. *"This is the third time in this campaign that printing a metric's members changed its conclusion."*

**Deliberate redundancy is a different thing.** `retrospective.md` §11.5 draws the line: independent *guards* where removing either leaves the other firing are fine; duplicated *logic* where changing one copy silently does nothing is not.

### Status: mixed, verified at HEAD

Ticket 96 is **fixed** — I read `toolguard/hook.py`: `_log_allowed_command` is defined at line 453 and called at lines 1047 and 1131, so both handlers now share it. Ticket 74 finding 5 is **still live** — `toolguard/rule_sort.py:54-72` still hardcodes the four-entry priority dict, and `toolguard/tool_spec.py` still declares five `ToolSpec`s, the fifth being `mcp__jetbrains__execute_terminal_command`, which therefore still buckets alongside genuinely unknown tools.

> **RULE.** Count workarounds, not their individual justifications. The tell is the **third** hand-written instance of one idea; by then every individual decision to write it again looked reasonable. When you are about to write the second copy, extract instead — and when you find yourself writing the second *hand-maintained list* of something a registry already declares, the registry is the fix, not a third list.

---

## 4. Hand-enumerated sets that a new category silently escapes

**Basis: four instances on a single ticket, counted as they were found.**

This is habit 3's dynamic form, and it has its own signature. From `TOO-45/TOO-45 phase 3 resume.md`, on ticket 79:

> *"Every time a new category of verdict was added, something enumerating the old categories silently stopped covering everything. The fabrication guard twice, and the `no_match_fallback` WARNING once (`judge_unit`'s `warned` any() excluded `deny_check_verdicts`). Round 4 is specifically hunting a fourth."*

Round 4 found the fourth, exactly where it was told to hunt. The fix was **one authority**: `all_parts = (stub, *audit_part_verdicts, *deny_check_verdicts)`, consumed by `_pick_strictest`, the context accumulation and the `warned` check. **Round curve 5 → 4 → 3 → 1.**

Two details worth carrying. The root cause of two of ticket 79's three security weakenings was *"a hand-rolled resolution running parallel to the project's strictest-wins machinery"* — the same defect as habit 3, expressed as an enumeration. And the implementer **refused** the brief's claim that `reason` needed the same treatment, having verified in code that `_combine_inline_code_reason` only ever folded stub plus audit parts. A blanket "apply it everywhere" would have been wrong.

> **RULE.** When you add a category to a union — a new verdict kind, a new part class, a new tool kind — grep for every site that enumerates the existing members and make one of them the authority the others consume. An enumeration that silently under-covers produces no error; it produces a slightly wrong answer that looks right.

---

## 5. One structure answering two questions

**Basis: three instances, one with a costed measurement.**

- **`CommandUnit.kind`** decided both *which policy applies* and *how the leaf is decomposed for the audit breakdown* (`TOO-45/proposed-tickets/97-unit-kind-answers-two-questions.md`). Raising the ASK floor for a leaf reclassified it from `'plain'` to `'inline_code'`, which silently changed its decomposition. **Measured cost:** the actual fix in `command_extractor.py` was **59 lines**; restoring the audit breakdown the reclassification collapsed took **357 lines** across `compound.py` and `resolve.py`. *"Eleven agent runs, four review rounds, and three security weakenings — an unoverridable `hard_deny` downgraded to `ask`, an explicit `ask` lost entirely, and a `no_match_fallback` warning silently dropped — each introduced by the fix for the previous one. All three were caught before commit, none by the suite."*
- **`audit_parts` / `deny_check_parts`** are checked identically and differ only in whether the entry appears in the audit breakdown (`TOO-45/reports/103-compound-concept-map.md`). *"This is one concept — substitutions that must be resolved — split into two fields by a reporting property. The definition of the second is literally 'the first one's complement, same behaviour, different visibility', which is why no shorter wording exists."* The split propagates into `judge_unit`, which takes three parallel verdict sequences the caller must keep in lockstep, each with its own `ValueError` guard.
- **A shared `CommandSpellings` pair widened for one consumer silently changed the other, twice** — once downgrading an unoverridable `hard_deny` to `ask` with a green suite (`DURABLE/01-claude-failure-modes-and-mitigations.md` §5, which is where I found this stated; I did not locate a primary ticket for the two incidents and am relaying it as that document has it).

### The sharpened diagnosis, which is the part worth keeping

Ticket 97's own planning pass produced a **smaller and more precise** statement than its title:

> *"`CommandUnit` already carries a second field, `audits_as_one`, and `resolve.py` already reads it in preference to `kind`, deliberately. Somebody already saw this coupling and separated it at the consumption point. That is half the fix, already done and commented. Where it is still collapsed: at construction."*

Because `_unit_for` set both from one decision, `audits_as_one` was *derivable* from `kind`, so the two could never disagree — **and the case ticket 79 needed was inexpressible**: a unit that takes the floor's policy *and* still decomposes per-part for the audit. *"Not 'one field, two questions' but 'two fields, one of them derived, and the case that needs them to differ is the one that arose.'"*

The extractor had also **already** carried the fact separately: `LeafCommand.ask_floor` is its own field, collapsed into `kind` when the unit is built. *"The fix is not to invent a mechanism — it is to stop discarding one that already exists one layer up."*

### Status: 97 fixed, 106 declined and live at HEAD

I read `toolguard/compound.py` today: `audits_as_one` is now decided by its own function `_audits_as_one` (line 213) rather than derived from `kind`, and `resolve.py:346-350` reads it with a comment saying why. The `audit_parts` / `deny_check_parts` split is **still there** — `CommandUnit` still has 7 fields (`compound.py:207-214`) and the two collections are still separate, ticket 106 having been declined on evidence.

> **RULE.** When a field's value determines two things that are not the same statement, expect the case where they must differ to be the one that arises. Before adding a value to an enum, check what *else* branches on it. And when a fact exists separately one layer up and is collapsed on the way in, the fix is to stop collapsing it, not to reconstruct it downstream.

---

## 6. Under-modelling: bare literals and untyped dicts where a type belongs

**Basis: two tickets with counts, plus my own measurement at HEAD.**

The campaign ran a dedicated literals-to-constants ticket (`TOO-45/proposed-tickets/08-literal-strings-to-constants.md`) and the pattern **came back in every new module**. Arnon's diagnosis, quoted in `TOO-45/proposed-tickets/104-dicts-are-undeclared-types.md`, is the one that stuck:

> *"There are repeated literal strings that should have been constants... But the problem is probably deeper — there is prevalent use of dicts where there should be proper modeling. So the problem is not so much the string literals but the under-modeling pattern overall."*

The mechanism, from that ticket: *"A dict crossing a module boundary is a type nobody declared. Every `d["key"]` at the far end is a field access on that undeclared type... the literals proliferate because there is no type to hang them on. Naming the literals as constants makes the spelling safe and leaves the modelling gap untouched. That is why the cleanup ticket did not stop it recurring."*

**Counts from that ticket, measured 2026-08-21:** `hook_data` subscripted or `.get()`-ed at **8 sites** in `hook.py`, all flowing from `parse_hook_input()` returning `Dict[str, Any]`; `"log_dir"` as a literal at **10 sites**; `"extended_syntax"` at **4**.

Two more shapes in the same family:

- **A contract written twice as literals.** `TOO-45/proposed-tickets/62-the-log-entry-heading-is-a-contract-written-twice-as-literals.md`: the log heading `## <timestamp> - <LEVEL>` is produced by `error_log` and **parsed** by `session_start._count_conflict_entries`, which is how the SessionStart nag knows there are unresolved conflicts. *"Mutating the heading shape from `## <ts> - <LEVEL>` to `### <ts> (<LEVEL>)` produced zero detection across the entire 2,820-test suite."* Both sides' tests supplied their own literal text. *"The writer could have stopped being countable by the only recurring notification channel toolguard has, with a green suite."*
- **A string used as an identity.** `TOO-45/proposed-tickets/02-pattern-string-join-key.md`: the join key between a match result and its rule entry is the pattern string itself, *"and it is known non-unique — `merge_entries` exists precisely to handle same-pattern entries carrying contradictory metadata."* Symptom if it bites: *"wrong provenance or wrong `additionalContext` attached to a correct verdict — plausible-looking output, no error."* The ticket is careful: *"Not currently known to misbehave. It is a latent correctness hazard, not an observed bug."*

Why it matters more than it looks, from ticket 08: *"A typo in a comparison against `"deny"` fails open and silently — the branch simply does not fire."*

### Status: partly fixed; the decision vocabulary is still bare strings at HEAD

Measured by me today over `/home/arnon/projects/toolguard/toolguard/`:

- **45** occurrences of `== "deny"` / `== "allow"` / `== "ask"` in production code. `constants.py` defines `STATUS_ASK = "ASK"` and no `allow`/`deny`/`ask` decision constants. `CommandUnit.kind` is declared `kind: str` (`compound.py:208`), not an enum.
- The heading contract is **still two literals**: `toolguard/error_log.py:97` writes `f"## {timestamp} - {level}\n\n"`; `toolguard/session_start.py:92` counts `line.startswith("## ") and "- CONFLICT" in line`. No shared constant. (Ticket 62's own header says the test blindness was closed and the literal duplication was not — that matches what I read.)
- `parse_hook_input` is **gone**: `toolguard/claude_code_contract.py` now defines `PreToolUseEvent` and `read_pre_tool_use_event()`, and `PreToolUseResponse`. That is ticket 99 item 2 landed.
- I ran `uv run python tools/architecture_fitness.py --undeclared-types`: **4 findings out of 353 public functions/methods examined**, 12 exempt by serialiser-name convention, 3 further returning an undeclared dict but never called outside their own module. The four: `config:164 load_config_file`, `config:2222 config_sync_settings_from_sources`, `rule_sort:488 parse_permissions_section_with_comments`, `subagent:141 identify_current_agent`. The check is report-only and does not fail the build.

### Why the checker is the interesting half

Per `.claude/rules/evidence-before-fixing.md`, a check is strong exactly when it measures conformance to a declaration a human made. Ticket 104's argument: *"This one has a declaration: the return annotation... It never judges whether a dataclass is the right shape — only that a type was declared where one is owed."* It also names its exemptions up front — JSON serialisation boundaries, genuinely open-ended mappings such as a parsed TOML table.

> **RULE.** A value the code *branches on* is a constant; name it. But do not stop there — if the literals cluster around a dict crossing a module boundary, the dict is the defect and the literals are its symptom, and a third literals-cleanup pass *"would buy another few months."* Declare the type at the boundary and the literals become field names that static analysis can check.

---

## 7. Machinery that cannot do its job

**Basis: five instances, two with counts.**

- **Drift guards that never fired.** `ToolPatternLayer` stored three parallel pairs of arrays, defended by two runtime length checks. Over one 6,401-case corpus replay: `config._entry_for_pattern:1523` evaluated **3,982** times, its `return None` **never executed**; `resolve._hard_deny_additional_context:437` evaluated **14** times, same. *"3,996 guarded index lookups, 0 disagreements"* (`TOO-45/reports/core-types-and-clarity.md`). The report's judgement: *"a piece of code whose entire job was to survive a bug that the type system could have made impossible — and it did that job zero times while costing a branch on every enrichment lookup and, more expensively, costing every future reader a paragraph of explanation."* The retrospective states it as a rule: *"a drift guard is evidence that the design is wrong, not that the risk is handled."*
- **Compatibility shims with no consumers.** `BashResolution.__iter__` had **0 callers**; `FileResolution.__iter__` had **8, all in tests**. *"The shims existed to preserve a compatibility nobody in production still used"* (same report).
- **Guards that structurally cannot fire.** `hook.py`'s module globals for once-per-session suppression, *"whose own docstrings concede they cannot work — toolguard is a fresh interpreter per tool call, so a module global is a no-op guard"* (`TOO-45/proposed-tickets/01-once-per-session-warnings.md`).
- **A registry consultation indistinguishable from not consulting it.** `TOO-45/proposed-tickets/74-...md` finding 3: `_command_for_tool` falls back to a literal `"command"` when the registry lookup fails, and `Bash`'s declared `payload_key` *is* `"command"`. *"Proven by an equivalent mutant: deleting Bash's entire registry entry is unobservable... every 'we consult the registry' guarantee is, for the tool that matters most, indistinguishable from not consulting it."*
- **A guard whose no-op state is success.** `run_guard` reported `ok=True` with **zero cases checked** when its case list was empty (ticket 29, per `TOO-45/proposed-tickets/00-INDEX.md`). The same shape recurs across the campaign's instruments — see `01-claude-failure-modes-and-mitigations.md` §1.

### The counter-example, and it is deliberate

`core-types-and-clarity.md` on the derived property that replaced the stored copies: *"`stripped_pattern` is uncached and hot — 1.9 M calls per corpus replay, ~297 per decision. It is currently free (wall clock unchanged) and a cache would be premature optimisation with no measured problem. But it is the one place where 'derived property' could become a real cost if the config grows, and it is worth knowing the number exists."* That is the correct handling: measure, decline to build, record the number so the next person does not have to re-measure.

### Status: fixed for the drift guards and shims

I ran `--predicates` today: R1 reports **0** `__iter__` shims and **0** bare verdict-tuple returns; R2 reports **0** index-parallel access sites and **0** drift guards. The report's own claim is that misaligned `ToolPatternLayer` state is now a `TypeError` — *"there is nothing left for a guard to defend, which is why both guards were deleted."* The once-per-session duplication (ticket 01) was still deferred as of the index.

> **RULE.** Before writing a guard, ask what makes the bad state constructible — and prefer making it unconstructible. Before keeping one, ask how many times it has fired. And never write a fallback that produces the same answer as the mechanism it is a fallback for: it converts "the mechanism works" into an unfalsifiable claim.

---

## 8. Ambient state read at the point of use

**Basis: one instance with a large measurement, plus a second of the same shape.**

`TOO-45/proposed-tickets/44-ambient-state-is-read-at-point-of-use-so-every-read-site-is-a-mock-point.md`, measured 2026-08-13 in answer to Arnon's question about whether the structure made mocking harder than it needed to be. The answer was yes, and the numbers were:

| | count |
|---|---|
| `patch(` occurrences in `test/` | **485** across 33 files |
| uses of `autospec` anywhere | **0** |
| `Path.home()` calls in production | **23**, across **10 files** |
| `os.environ` reads in production | **19**, across 8 files |

The most-patched targets: `sys.stdin` 59, `sys.stdout` 58, `toolguard.hook.log_command` 56, `toolguard.hook.load_configuration` 35, `sys.stderr` 29, `pathlib.Path.home` **18**, `builtins.print` 11.

The diagnosis: *"Ambient state is read at the point of use, deep in the call graph, instead of being resolved once at the edge and passed down. Every read site becomes a seam a test must know about individually... when tests patch stdlib, the codebase has not offered them anything better."* And the reframe that makes it a design finding rather than a testing one: *"The number of mocks a suite needs is a measurement of how many implicit dependencies the code has — 485 is that measurement."*

**The template was validated before the refactor was scoped**, which is the part worth copying. `error_reporter` already met the standard: zero ambient reads, its only external dependency a `log_dir` handed to it, **one `patch()` in 24 tests**, and 24/24 green under a normal environment, an empty `HOME` plus empty `XDG_CONFIG_HOME`, `HOME=/nonexistent`, and a foreign cwd. *"That is the whole thesis of this ticket, demonstrated in a module that already exists."*

The second instance of the same shape is `TOO-45/proposed-tickets/13-anchor-project-root-per-session.md`: the project root is *"recomputed on every single tool call"* from `cwd`. Measured directly — *"planted a `pyproject.toml` in `tmp/cwdprobe/`, `cd`'d there, ran a trivial command — toolguard relocated the project root to that directory and wrote `tmp/cwdprobe/logs/`."* Worse, two resolvers disagreed: rule discovery walked past the nested marker while project-root resolution did not, so *"one session can therefore scatter its audit trail across several `logs/` directories while enforcing one consistent rule set."*

### Status: the production half is fixed; the patch count is not down

Measured by me today with a fixed-string grep over `/home/arnon/projects/toolguard/toolguard/`:

- **`Path.home()`: 2 real call sites, both in `ambient.py`.** (Two further hits are prose inside `testing/sandbox.py` docstrings.) Down from 23 across 10 files.
- **`os.environ`: 2 real reads in `ambient.py`**, plus 3 in `testing/sandbox.py`, which is the test harness itself. Down from 19 across 8 files.

So the "one door" wrapper landed and the ambient reads consolidated onto a single owner. **But the mock count went up, not down:** `patch(` now appears **600** times across **40** files in `test/`, and `autospec` still appears **0** times.

I am not going to convert that into a ratio. The 485 was taken on 2026-08-13 against a suite that `62-...md` describes on the same date as *"the entire 2,820-test suite"* — a unittest run count — whereas my 600 is a grep and my parallel count of `def test_` occurrences at HEAD is 4,020, which is a different instrument. The suite grew a great deal over the same period (`end-state-summary.md` records 2,186 → 2,387 at one snapshot; `TOO-45 phase 3 resume.md` records 3,839 later). **The honest statement is that the raw patch count rose while the ambient read sites collapsed, and I could not normalise the two measurements against each other.**

> **RULE.** Resolve ambient facts — home, cwd, environment, project root — once at the edge, into one invocation-scoped object, and pass it down. toolguard is one process per tool call, so there is exactly one correct value for each for the whole process lifetime. The wrapper does not need to be clever; it needs to be **the only door**, and it must be *handed* its dependencies rather than reading them at point of use — *"the moment it reads `sys.stdout` at point of use it becomes another of the 157 patch points rather than the thing that retires them."*

---

## 9. Stopping at the first working boundary

**Basis: four instances, one with a costed measurement.**

This is the campaign's most consistently self-diagnosed habit: fixing a symptom at the layer where it surfaced rather than at the layer that owns the concept, and then reporting the layer where it surfaced as the fix.

- **A conversion that reached one branch of two.** Punch-list item 10 replaced scattered tool literals with a registry. `TOO-45/proposed-tickets/74-...md`: *"`hook._resolve_event` and `_handle_command_tool` read the target from a literal `"command"` key and call `payload_key()` only on the file-path branch. Meanwhile `transcript_harvest` and `test.verdict_corpus.fixture_loader` honour the registry for command tools. So the contract exists, two consumers follow it, and the hook does not."* The ticket names **three** separate divergences from the registry, and *"all three findings name the same MCP tool."*
- **Compensating downstream for a gap upstream — and the compensation looking like a design.** `TOO-45/proposed-tickets/105-strip-comments-compensates-for-the-extractor.md` is the sharpest case, and it is sharpest because *the campaign got it wrong first*. The ticket claimed `_strip_comments` was redundant because the grammar already parsed comments. The implementing agent refused to build on the premise and disproved it: the `comment` rule *"fires zero times"* while parsing `echo hi # trailing comment`; `#`, `trailing` and `comment` are absorbed as ordinary word tokens. Arnon's decision, quoted in the ticket:

  > *"I did suspect that this extra parsing is masking some PEG problem. You said otherwise, and I wasn't exactly surprised either. Turns out that it is... the right fix is fixing it at the source — the parsing package and the PEG grammar underlying it."*

  And the principle the ticket derives from it, which is the general form of this habit: ***"A gap in the grammar must not be quietly compensated for downstream — because the compensation looks like a design choice, and the gap becomes invisible. `_strip_comments` looked like a pre-pass convenience for two years; it was a grammar hole wearing a pre-pass costume."***
- **A fix that masks rather than removes.** Ticket 79 gave `'inline_code'` units a structured tag so the outer combine never had to guess from prose, and left the identical parse running on `'plain'` units (`90-...md`). *"The fix masks the re-parse for `inline_code`; it does not remove it."*
- **A fix applied once and not generalised.** `retrospective.md` §11.2 states it as a diagnostic in its own right: *"a fix applied once and not generalised is where the next instance will be."*

The costed measurement is ticket 97's (habit 5): the fix at the layer where the symptom appeared was 59 lines; the consequence of not fixing the coupling was 357 lines and three security weakenings. **The agent-run count that usually accompanies this sentence is disputed and should not be quoted flatly** — the corpus states it as 7 runs / ~1.8M tokens (`measurements/79-cost-assessment.md`, the only actual measurement), 9 / ~2.6M, and 11 / ~3M, most likely three points in time on a still-running ticket, though no source says so. See `02-campaign-cost-data.md` C1 and `05-campaign-statistics.md` §9. The line counts and the three weakenings are solid; the run count is not, and the "eleven" version is the one that propagated furthest with the least provenance.

### Status: 105 redirected into the grammar; 74's divergences partly live

`_strip_comments` is gone from `toolguard/parser/multiline.py` (I read it), and the recent commit log shows items 105 phase 1 and 2 landing the grammar change. `rule_sort`'s duplicate tool table is still live, as recorded under habit 3.

> **RULE.** When a defect surfaces in layer B and the cause is a gap in layer A, fix layer A. Before writing a compensation in B, write down what limitation of A forces it — and if you cannot name a real limitation, you have found the bug rather than the workaround. Then count the blast radius before writing "deferred": *"a conversion that reached one of two branches"* is the shape to grep for after any "replace the literals with a registry" change.

---

## 10. Tests that pin the wrong thing

**Basis: a 22-shape catalogue with two independent counts, plus three tickets with their own mutation numbers.**

`TOO-45/proposed-tickets/31-suite-blindness-measured.md` is the primary source and it is careful about what it is claiming. Two measurements by different methods on the same suite:

| measurement | method | result |
|---|---|---|
| tests whose assertions **cannot fail** | read the test, then run the fixture or mutate the mechanism it names | **~65 across ~78 files** |
| mechanisms with **zero test detection** | delete the mechanism in an out-of-tree copy, run all 2,733 tests, subtract the 2-error environmental floor | **~50** |

*"The suite is green and stays green. Neither number is visible from a passing run, which is the entire problem: 2,733 passing tests is the same signal whether these exist or not."*

**The ~50 is explicitly a floor, not a ceiling**, and the ticket says why: *"A mutation that produces failures is not necessarily detected. Three separate batches found mutations that broke tests for an incidental reason while the named mechanism stayed uncovered... Any re-measurement must read the tracebacks."*

**And the ~65 was corrected by the ticket itself.** Per `DURABLE/intermediate/defect-taxonomy.md`: *"31 discovered its own headline number was wrong: '~65 assertions that cannot fail' conflated *cannot fail* with *cannot distinguish*, and the second is the worse defect because it actively certifies the wrong thing while reading as thorough."* The ticket's own correction section also raises `test_compound.py`'s fail-open cluster from 12 to 16, removes one test from that cluster, and flags one queue entry as simply false. **Cite the file, not a remembered shape number** — the ticket says shape numbering drifted between two documents.

The catalogue's 22 shapes are the durable artifact. The ones that recur:

- **20** — an assertion satisfied by a fail-open safety net rather than by correct behaviour. Largest single cluster: `extract_commands` returns `[original.strip()]` on any parse error, so `assertGreater(len(result), 0)` cannot distinguish correct extraction from the fallback.
- **22** — a guard or checker that passes with an empty input set.
- **8** — `assertEqual(x, x)`, or both sides computing the same thing.
- **14** — the fixture's own setup provides an alternative route to the outcome, so the named subject is irrelevant.

The ticket's own framing of why review does not catch these: *"Shapes 14-22 are not 'vacuous' in the naive sense — they assert something real about the **wrong subject**, which is why they read as thorough in review."*

### Corroborating per-module measurements

- `62-...md`: mutating the log heading produced **zero detection across the entire 2,820-test suite**, because *"every test on both sides supplies its own literal text."*
- `74-...md`: *"At HEAD, 10 of 19 mutants produced zero failures, and 9 more were caught only by literal-set pins"* — the module noticed a constant changed and nothing checked the consequence. Repaired to 18 of 19 detected behaviourally. Its sharpest survivor: `Read.is_builtin: True -> False` removes `Read` from `BUILTIN_TOOLS` and `DEFAULT_GOVERNED_TOOLS` while leaving it fully described — **zero failures at HEAD**. *"Nothing in the module ever checked that `Read` is governed, only that it is listed."*
- `75-...md`: *"20 of 46 mutants survived HEAD (43% blind); 0 of 51 survive the repair. 12 -> 43 tests."*

### The sub-habit: a test double that re-implements production

Two independent instances:

- `test_hook.py`'s fake config hand-implemented `resolve_permission_detailed` in ~35 lines *"whose own comment admitted it was 'API-sync' with the real thing"* (`end-state-summary.md`). After the fix, *"the real engine is now entered 10 times through the double where it was previously entered zero times."*
- `TOO-45/proposed-tickets/100-resolve-leaf-is-a-test-only-entry-point.md`: `compound._resolve_leaf` had no production caller and roughly 30 test call sites across two modules. The ticket states the severity at its real size — *"This is NOT '30 tests test dead code'"*, the helpers it calls are live — and then names the actual cost: *"those tests reach the production logic by a route production never takes. They bypass `_combine_strictest` entirely... and the wrapper constructs a `RuntimeVerdict` with `matched_rule`/`provenance` left at defaults — a shape production never produces."*

Ticket 35 is a third of the same family per `00-INDEX.md`: *"the hard-deny test class re-implemented production's ordering, so it detected nothing."*

### Status: partly repaired; `_resolve_leaf` gone at HEAD

I grepped `/home/arnon/projects/toolguard/toolguard/`: `_resolve_leaf` no longer exists. Ticket 31's own header records wave 1 committed (5 modules) with tier 3 (~70 modules) not started.

> **RULE.** Ask *"what would notice if this were wrong?"* rather than *"is this right?"* — the two questions find disjoint defect sets. Include a control that **should** fail. Where a writer and a reader share a format, round-trip the real writer through the real reader rather than asserting each side's own literal. And when a test double implements behaviour rather than returning data, you have a second implementation with no way to disagree loudly.

---

## 11. Fossil signatures an LLM author does not feel

**Basis: two shapes, each with counts, plus a stated mechanism.**

`retrospective.md` §11.1 names the generator-side cause, and it is the single most portable claim in this document:

> *"Humans catch fossil signatures because they hurt. Holding twelve parameters in your head is uncomfortable and the discomfort triggers the refactor. That signal does not fire for an LLM author — evidenced here by reading `log_command`'s eleven parameters and using them as evidence for a different finding without flagging the signature itself, and worse, by planning to add a twelfth."*

### Parameter creep

`log_command` took **11** parameters (`inspect.signature` on the live master module: `command_str, status, violated_rules, log_dir, extra_info, config, matched_rule, note, permission_mode, additional_context, log_format`) and now takes **4**. *"Seven of the eleven became fields of `LogRecord` — and `LogRecord` then gained an eighth field (`provenance`) that master's `_LogRecord` did not have, so the audit log records strictly more while the function signature carries strictly less"* (`core-types-and-clarity.md`).

Two discriminators from `retrospective.md` §11.4 that make parameter count actionable rather than diffuse:

- **Look at where the arguments come from at the call site.** Mostly `result.x, result.y, result.z` → a missing parameter object. Many unrelated sources → the function does too much. *"Same symptom, opposite fixes, one glance to tell apart."* Applied to `log_command`, the parameters fell into three coherent groups — verdict-derived (6), environment (3), invocation context (2) — *"so it was three missing types, not one bloated function."*
- **The type is often already one frame away.** *"The private `_LogRecord` already existed with the right shape, built at the writer boundary instead of the caller boundary... That is common enough to be a review prompt: 'does the shape I need already exist slightly downstream?'"*

**The caveat travels with the rule:** *"parameter count is trivially gameable by bundling into an untyped dict, which is strictly worse than the disease. Diagnostic, never target."* — which is habit 6 arriving from the other direction.

### Prose growth

Comment volume was the *visible* symptom of every missing abstraction in this list:

- **12 live statements of one index-alignment invariant** across `config.py` (7), `resolve.py` (3), `config_types.py` (2), measured by grep on the pre-ticket tree. *"Four separate statements of the same invariant in comments is the artifact a codebase produces once someone has worried about drift and chosen to document rather than eliminate it. Count invariant restatements; each one is a vote that the invariant should be structural"* (`retrospective.md` §11.3).
- **`CommandUnit` has 7 fields and roughly 80 lines of docstring**, and `103-compound-concept-map.md` traces the bulk of it to the one concept nothing owns: *"the definition of the second is literally 'the first one's complement, same behaviour, different visibility', which is why no shorter wording exists."*
- **A module at 55% docstring lines and a diff at 71% prose**, neither flagged while being written, *"including by its author"* (`retrospective.md` §11.6). The failure mode has a name there: **autobiography** — *"prose explaining why the code is not something else, rather than what it is... the form most likely to become false, because it describes a past state."*
- **The overstated justification, authored by the cleanup during the cleanup.** A local import was kept with a comment saying hoisting *"would load the whole tooling layer on the hot path."* Measured: **2 modules and 0.52 ms — 1.6% of `hook`'s import time.** §11.7's reading is the one to keep: *"an overstated justification is a reusable excuse. The next author facing the same choice finds a precedent that appears reasoned, cites it, and the exemption spreads. A comment that is merely absent forces the next author to think; a comment that is confidently wrong forecloses that."*

### Status: fixed for `log_command`; the general tendency is a generator property, not a code state

The docstring-lines-to-executable-lines ratio check §11.6 proposes *"was proposed and never built."*

> **RULE.** Before an edit, answer three questions that need no discomfort to answer: (1) does this **widen a signature**? (2) does it **add another type** to a concept that already has several? (3) does it **add a parse** of something already held as structured data? *"Any 'yes' is not a prohibition; it is a requirement to say so out loud in the change description."*
>
> And: *"a justification containing a quantity is a claim, and a claim must be measured before it is written."* Either measure it and write the number, or write the honest version.

---

## The one meta-finding that explains most of the above

`retrospective.md` finding 3, and it is the reason none of these were caught by review:

> *"Rot accumulates through sequences of locally-correct decisions. Three separate times, widening a narrow tuple contract was correctly judged disproportionate — because ~20 tests actively pinned it. Nobody was wrong; nobody ever paid it once; 1,943 audit records were silently lost."*

§11.1 draws the consequence: *"This is why prevention has to be a ratchet rather than a judgement. A reviewer asking 'is this change reasonable?' gets 'yes' every time, correctly."* The two mechanisms it names as actually working are a **debt register with an owner and a budget** — *"the tell that it is happening is the third workaround for the same missing abstraction — count workarounds, not their individual justifications"* — and **decoupling behaviour-pinning from unit tests early**, because *"the reason each local judgement came out 'disproportionate' is that the tests pinned the shape. An equivalence oracle... does not just make cleanup safe; it changes which cleanups are affordable, and therefore which local judgements come out right."*

---

## What I looked for and could not substantiate

Stated plainly, because a habit list that only contains hits is not calibrated.

- **Premature caching.** I found no instance of a cache built without a measured problem. What I found was the opposite — an explicit decision *not* to cache `stripped_pattern` on the grounds that it *"would be premature optimisation with no measured problem"*, with the 1.9 M-calls figure recorded so the question does not have to be re-opened blind. I have written that up as a counter-example under habit 7 rather than as a habit.
- **A dependency added for something the stdlib does.** The project's runtime is standard-library only by architectural constraint, checked by `tools/architecture_fitness.py --stdlib`. I found no instance of this failure and would not expect one under that constraint.
- **Global mutable state as a shared channel.** The nearest thing is the module globals in `hook.py` used as once-per-session guards (habit 7), which are a *no-op* rather than a shared-state hazard, because toolguard is one process per tool call. I did not find a case of two components communicating through a module global.
- **A second instance for `CommandSpellings`.** `01-claude-failure-modes-and-mitigations.md` §5 says the pair was widened for one consumer and silently changed the other *"twice."* I could not locate a primary ticket for either incident in the corpus and have relayed it under habit 5 attributed to that document rather than to a source I checked.
- **Threading state as a design signal.** This is a standing project preference and appears in ticket 44's reasoning, but I found only that one code instance in this corpus, so it is folded into habit 8 rather than standing alone.
- **A ratio for habit 8's mock count.** See the status note there. The before and after come from different instruments and I declined to divide them.
