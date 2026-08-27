---
title: 09-verification-mechanisms
type: note
permalink: toolguard/durable/09-verification-mechanisms
tags:
- TOO-45
- durable
- verification
- review
- measurement
---

# 09 — Which verification mechanisms actually worked, and against what

**The question**: over ~100 tickets the campaign used a dozen quality mechanisms and never compared them. Which were effective — and effective at *what*?

**Why this is not a ranking.** Aggregate "defects found" is the wrong metric and it is not used here as a headline. The mechanisms do not compete on one axis: blinded review produced **82 gate findings, 63% of them claim defects**, while a HEAD-vs-tree differential produced almost nothing except **the three defects that would have shipped a security regression**. A single ordering would put those on one scale and say something false about both. So the organising axis is **defect class**, and every mechanism is judged against each class separately.

**One headline conclusion, stated up front because it is the finding most likely to change practice**: the mechanism that caught the dangerous class was not review, and it was not the suite, and it was not the replay — **it was execution of a differential, performed inside a review round by a reviewer who chose to run something.** Review supplied the occasion; execution supplied the finding. Everything else in this document is downstream of that distinction.

**Read `08-autonomous-loops-vs-human-in-the-loop.md` first if you have not.** This campaign ran predominantly as an autonomous agent loop, which is not Arnon's normal working pattern. Each section below therefore ends with a **transferability** line saying whether the mechanism's effectiveness is a property of the mechanism (transfers to any mode) or an artifact of nobody being in the loop (does not).

**Cost is stated in two currencies, never summed.** Agent time is elastic, parallel and cheap. Arnon's attention is fixed and serializes the project — his own framing: *"my availability is actually the constraining resource always as this is not my main activity."* A mechanism that burns hours of agent time and five minutes of his is cheap in the currency that binds. The corpus itself records making the wrong-currency mistake and retracting it under a heading reading *"THE CORRECTION THAT MATTERS — I have been costing tickets in the wrong currency"*.

## The four defect classes

| class | definition | why it needs its own column |
|---|---|---|
| **CLAIM** | a comment, docstring, ticket, brief or report asserting something untrue about the code | checkable against something that already exists; a reader can catch it |
| **COMPOSITION** | wrong output or decision when parts combine | cannot exist until the parts run; no amount of reading reaches it |
| **SILENT** | a mechanism failing open and reporting success — the campaign's signature class | produces no error, no prompt, no log line. Absence of evidence is not evidence here |
| **INSTRUMENT** | the measuring tool itself wrong — usually a **clean null**: a tidy, plausible, confident, wrong number | the failure looks exactly like a pass. Review does not catch it; only a control does |

A fifth class — **structure/quality** (naming, duplication, dead code, layering) — is real but is not where this campaign's danger lived, and it is folded into the per-mechanism notes rather than given a column.

## Confidence labels

**high** = re-measured, or multiple independent primaries agree. **moderate** = one primary states it and nothing contradicts it, or it is a judgement resting on measured inputs. **low** = judgement, stated as such, with its basis and its falsifier named. **Never write a judgement in the language of a measurement** — where a line below is opinion, it says so.

---

# The lead table

Rows are ordered by how well the evidence supports them, not by yield. `++` = reliably catches this class, with primary evidence. `+` = catches some. `~` = incidental / unreliable. `-` = provably misses, with a measured instance. Blank = no evidence either way.

| mechanism | CLAIM | COMPOSITION | SILENT | INSTRUMENT | cost: agent | cost: Arnon |
|---|---|---|---|---|---|---|
| **HEAD-vs-working-tree differential** | | `++` | `++` | `~` (its own null lied once) | low per run | ~zero |
| **Mutation testing (in-process)** | `+` | `++` | `++` | `-` (harnesses lied constantly) | **high** (~161k tok/agent, n=12) | ~zero |
| **Comment/docstring verification by execution** | `++` | `+` | `+` | `+` | moderate | low |
| **Diagnostic probes** | `+` | `++` | `++` | `+` | **very low** | ~zero |
| **Blinded review — the reviewer *reads*** | `++` | `~` | `-` | `+` | moderate ($3–15/round) | low |
| **Blinded review — the reviewer *executes a differential*** | `+` | `++` | `++` | `+` | same round, same price | low |
| **Arnon asking a question** | `+` | `+` | `+` | `++` | ~zero | **the scarce currency** |
| **Corpus replay** | | `+` | `-` (verdict-only is blind by construction) | `-` | moderate | ~zero |
| **The unittest suite (4,008 tests)** | `-` | `+` | `-` (green through all 3 security defects) | | low marginal | ~zero |
| **Architecture fitness checks** | `+` (declared checks) | `-` | `-` (PASS over nothing; 4 escapes) | `+` (when it fails loudly) | low | low |
| **Static/lint (ruff, pyscn, pyright, graph)** | `~` | `-` | `-` | `~` | ~zero | ~zero |
| **Golden verdict corpus (equivalence oracle)** | | `+` | `-` (blind in 6 recorded ways) | | high to build, low to run | ~zero |
| **"The brief is unverified — verify it"** | `++` | | | `+` | **~zero** | ~zero |
| **The punch list** (§13) | | | | | **~zero** | ~zero — **and it is the only row he can audit without reading code** |

**One mechanism does not fit these columns, and the columns are the problem, not the mechanism.** §13, the punch list, targets a **fifth defect class — SCOPE-COMPLETION: work declared finished that was not done.** That is not a property of the code, so no column here can score it, and its absence from this table until 2026-08-25 is why it was omitted from the document entirely. Added on Arnon's observation; see §13.
| **Two-phase review of a formal artifact** | `+` | `++` | `+` | | moderate | ~zero |

**The one-line reading**: *claims* are caught by reading and by executing what the prose says; *composition and silence* are caught **only** by differential execution, whoever performs it; *instruments* are caught almost exclusively by a control that should fail, and by Arnon.

## The correction that reorganised this table

**The brief for this document, and `08-autonomous-loops-vs-human-in-the-loop.md:90`, both state that blinded review *missed* the three serious security defects. That is wrong, and the primaries settle it.** All three appear as **blocking findings inside review rounds**, and I read each one in its round file:

- `review-79-round1.md` **B1** — *"A `deny` — and an unoverridable `hard_deny` — inside a substitution is downgraded to `ask`"*, evidenced by *"Measured post-fix vs a pre-fix shadow tree (`git show 7d0646d:` of the three production files, **`PYTHONPATH`-shadowed**; repository untouched)"*.
- `review-78-round2.md` **B1** — *"`~<name>` is expanded to `$HOME`, not to the named account's home"*, evidenced by *"Measured, comparing against **`bash -c 'printf %s ~name'`** in the same environment"* plus a read of the CPython 3.14 stdlib source.
- `review-18-round2.md` **B1** — *"Measured: it also **widens**, and the widening reaches hard-deny carve-outs… Measured old-vs-new over a 38 × 39 pattern/command grid (**old `match_command` loaded from the `HEAD` blob, new from the working tree**)"*.

`06-planning-attribution.md:475` and `02-campaign-cost-data.md:53` both say so plainly — *"found anywhere in these thirty rounds"* — and the "missed" sentence appears exactly once anywhere in the corpus. **`08` line 90 is an error against its two siblings and should be corrected.** The defensible sentence it was reaching for is its own line 113: *"A human reading the diff does not find a `hard_deny` silently becoming `ask`."*

**What the correction does not do is rescue reading.** In all three cases the reviewer found the defect **by running a differential**, not by reading the diff — a `PYTHONPATH`-shadowed HEAD tree, a real `bash` oracle, a HEAD-blob-versus-working-tree grid. So the conclusion changes shape rather than reversing:

> **Blinded review is a container, not a technique.** Its yield against the silent class is entirely attributable to reviewers who executed something. Where a round only read, it returned claims. That is why the table splits the row.

**But "container" is not a deficiency, and an earlier version of this section read as though it were.** Corrected 2026-08-24, after Arnon pointed out that the analysis was treating method variation between reviewers as a comparability problem. It is the mechanism working. Look at what the three techniques actually were: a `PYTHONPATH`-shadowed HEAD tree, a `bash -c 'printf %s ~name'` oracle, and a 38 × 39 pattern/command grid loading the old matcher from a git blob. **Three different reviewers invented three different differentials, and none of the three was briefed.** A uniform, specified review protocol would have found whichever defect its one prescribed method happened to reach, and the other two would have shipped.

Arnon, 2026-08-24: *"Blind reviewers choosing different methods — especially if you, coordinator, did not anticipate them — is where the value of the methodology lies. It yields different perspectives and as a result catches issues you wouldn't otherwise catch. The blinded reviewers are not there to produce predictability. They are there to uncover blind spots, just like the mutation method does. It's the surprises that we're actually looking for, not confirmation."*

**The corpus's own strongest sentence on this points the same way and was previously read as a complaint**: *"Every one was invisible to the instrument used to clear the round before it."* That is a statement about instruments having disjoint reach — which is the argument for varying them, not against. The `Path.absolute()` escape is not a failure of inconsistency; it is a class that needed an instrument nobody had yet built (enumerating `dir(Path)` member by member), and the round that built it is the round that found it.

**What follows for how to read this document**: the reads-versus-executes split in the table is an observation about *what a given round did*, not a prescription to standardise. The operative advice is *"require that something be run"*, never *"require that the same thing be run"*. Uniformity would raise the floor of the weakest round and lower the ceiling of the best, and the three defects that mattered all came from the ceiling.

**Confidence: high** — three primaries read directly, each quoting its own measurement method; the census reconciles independently with `06`'s 82-finding total.

**The genuine miss stands, and it is a different one.** `Path.absolute()` escaped **six** rounds, and its two siblings escaped four and five: *"`expanduser` escaped four blinded review rounds and was a **live isolation hole** returning the developer's real home under a patched `Path.home`; `resolve` escaped five; `absolute` escaped six and was found only by enumerating pathlib's surface rather than by review. **Every one was invisible to the instrument used to clear the round before it.**"* The mechanism is named in the ticket: *"An enumerate-the-bad-list rule cannot catch the route nobody thought of."* **Confidence: moderate on the exact count of six** — only 2 of those 6 rounds survive as files, so the number rests on the ticket author's contemporaneous knowledge; **high on the pattern**, which is stated three times independently and now has a fourth instance (`pwd.getpwnam`).

---

# Per-mechanism

## 1. HEAD-vs-working-tree differential testing

**What it is.** Run the same inputs through the committed tree and the working tree in isolated processes, and diff the outputs — not the tests, the *decisions*.

**What it reliably catches.** Behaviour changes under composition, and specifically **loosenings that nothing else observes**. Three worked instances, all quoted verbatim in `06-planning-attribution.md`:

- **Ticket 79 round 1** — reclassifying a leaf's `kind` silently turned an unoverridable `hard_deny` into a promptable `ask`. The reviewer's own output: `PRE-FIX : deny rule='rm:*'` / `POST-FIX: ask rule=None`, with `rm -rf /tmp/x` *"not merely un-itemised — it is gone: not judged, not recorded"*. **The suite was green and the corpus replay showed nothing.**
- **Ticket 78 round 2** — a `getpass.getuser()` / `Path.home()` disagreement means that with `$LOGNAME=root`, an allow rule `cat /home/arnon/*` **allows** `cat ~root/.ssh/id_rsa`. Establishing it required reading CPython source *and* running a real `bash` under manipulated environments.
- **Ticket 18 round 2** — a change framed by the ticket, the brief and the doc as a one-way narrowing was measured over a 38 × 39 grid: *"8 matches lost, 10 matches gained… Three commands flip from hard-denied to exempt, one of them exfiltrating to an external host through a carve-out whose name says 'localhost'."*

**What it provably misses.** Anything the inputs do not exercise — it is only as good as its input set, and its input sets here came from the same log corpora that are demonstrably thin on rare constructs. It says nothing about claims.

**The instrument's own failure — and it happened TWICE, independently, through the same trap.**

- **Coordinator-side, ticket 19**, the consequential one: a comparison *"agreed exactly"* because both runs imported the working tree. The script lived outside the tree under test, so `sys.path[0]` pointed at the script's directory. The isolation had been "validated" separately via `python -c`, where `sys.path[0]` is the cwd — **proving isolation for an invocation that never happened.** Redone with `PYTHONPATH` pinned and `__file__` printed inside the run: `F1_$(true;true)` gave `ask_floor=False` on the working tree and `True` at HEAD, *"directly contradict[ing] the original brief's 'byte-identical… F1 is NOT a regression' claim."* The reviewer had been right, and the null had been used to override a correct security finding.
- **Reviewer-side, ticket 77 grammar phase 1**, caught by the reviewer itself: *"an early comparison run used `python -c`… **it silently compared the working-tree parser against itself.** All reported measurements come from script-file runs, each of which printed the resolved `toolguard.__file__` it had loaded."* By the delta round it was a standing brief instruction, with the note *"already produced one false measurement in this ticket"*.

**Two independent instances of one trap is the argument for making it structural rather than remembered.** The rule now: **emit module provenance from inside the measurement itself, in the same process that produces the numbers** — `print(m.__file__)` next to the result, not in a prior check.

**Cost — measured, and cheaper than its reputation.** A differential round runs **$4–15 and 13 min–1h25m**: ticket 19's isolated `__file__`-verified A/B took **~7 min** inside a repair round costing **under $1**; ticket 78's round-1 repair bundled two suite runs, four gates, a 26,530×2 replay, a two-tree deny-direction harness and a miss classification into **~44 min / ~$4.20**; review 78 round 2 — **13m16s / ~$4** — **found one of the three serious security defects.** Arnon: essentially zero; he reads a two-line before/after table.

**Transferability: full, and this is the strongest transferable finding in the corpus.** It is mechanical. A human reading a diff does not find a `hard_deny` silently becoming `ask` any more than an agent does — the defect is invisible in the text of the change. **Confidence: high** (three independent instances, each with a quoted differential; the counter-case is an instrument failure, not a method failure).

## 2. Mutation testing, in process

**What it is.** Rebind a live module attribute to a wrong-but-plausible value, run the suite, record which tests fail. `methodology/in-process-mutation-testing.md`.

**What it reliably catches.** Three distinct discovery modes, each measured (`intermediate/practices-with-evidence.md` §1.2):

- **A mutation that refuses to change behaviour points at a second implementation.** That is how the duplicated undecidable floor was found — before any refactoring started — and after unification *"the identical mutation flipped MISSED → CAUGHT"*, a falsifiable proof that a unification is real rather than cosmetic.
- **Mutate toward the fix, not only away from correctness.** For a TOML escaping bug, removing all escaping produced **16 failures** (looks like coverage); applying the *actual fix* produced **0**. *"The suite is blind in both directions"* is strictly stronger than "untested".
- **Mutate what you just built.** Mutating a new field to a plausible wrong value left **all 2,300 tests green**; swapping `matched_rule` and `provenance` at the hook call site corrupts every audit entry and **2,314 tests stayed green**.

**Scale.** Per-module survival before repair: **47% (14/30), 55% (23/42), 58% (over 81 mutants)**, near zero after repair. The suite went 2,733 → 3,628 tests in one commit (77 test modules) as a result.

**The single most severe finding, ticket 35** — worth quoting because it is the shape that argues for the whole mechanism. Production's Bash hard-deny check was bypassed entirely, and `test/unit/test_hard_deny.py` produced *"**exactly one failure**: the end-to-end `main()` test. **All ten tests in `TestHardDenyCommand` — the class named for the mechanism, in the file named for the mechanism — detected nothing.**"* Cause: the class's `_resolve` helper re-implemented production's ordering. After repair, total hard-deny bypass: **0 failures before, 5 after.** The ticket's own summary: *"It was the least-tested mechanism in the file that exists to test it, and the suite was green throughout."* A close second, repo-wide: mutating `discover_config_files` so the `~/.claude` block is a no-op gave *"18/18 green — zero detection"*, and extended across every module reaching it, *"**Zero detection repo-wide. A user's entire `~/.claude` could stop being read and nothing would fail.**"*

**The method's own origin is a datum about agents.** Parallel on-disk mutation was found broken in wave 1 — *"Reported by the `test_hard_deny.py` agent, unprompted… During its mutation windows it twice saw **other** agents' live production mutations in `git diff`."* The in-process fix came from a different agent, also unasked: *"mutate IN PROCESS, never on disk"*, proving 18 repairs by monkeypatching inside the test run and *"never wrote a production file at all."* That property — no production file is ever written — is what makes several agents safe to run concurrently, which is what makes the mechanism affordable in the elastic currency.

**The reading-versus-mutation contrast is the sharpest single datum for this mechanism.** On one module a careful read-only review reported *"one minor redundancy"*; mutation found **13 of 25 mechanisms at zero detection**. Measured six times in one evening across six modules, with the read-only queue's verdict accurate about what it examined and silent about everything else (`intermediate/rejected-methods-and-metrics.md` B5).

**What it provably misses, and the honest caveat that must travel with it: the harnesses lied constantly.** `rejected-methods-and-metrics.md` B4 catalogues **fifteen** distinct traps, every one of which produced a confident wrong number, usually a **false zero-detection** — worse than no reading, because it manufactures a finding that does not exist. Among them: a mutation landing in a *docstring* rather than the code; masking guard pairs; by-value imports where patching the definer no-ops; a `TimeoutError` watchdog swallowed by `except OSError` so a deadlocking mutant read as a clean survivor; `unittest` subTest failures routing through `addSubTest` and never counted; twenty method-level mutants silently un-applied by a restore that rebound the harness's own anchor. The standing rules that came out of it: **never read failure counts — diff the failing test *sets***, and **a mutation run must state its target**, because MISSED against the corpus can be fully pinned by unit tests.

**Yield — the dispute is now partly settled, and this document settles it.** `methodology/in-process-mutation-testing.md` states *"the campaign filed roughly fifty production defect tickets, several security-shaped, from mutations alone"* — the source itself says "roughly". `intermediate/defect-taxonomy.md` attributes **18 of 76** primary tickets to mutation, and both `05-campaign-statistics.md` and `02-...md` report the two as irreconcilable *"because `resolved/` was never classified."*

**Checked for this document, 2026-08-24.** All 18 primary tickets were read: **17 carry explicit provenance** — five say *"Found … by the test-repair campaign"* or *"while repairing `test_configuration.py`"* verbatim, ten carry in-file mutation measurements (ticket 56 `0/14 → 14/14`; 61 `7/26 → 0/30`; 64 `21/48 → 1`; 70 `16/41 → 0/48`; 73 `17/29 → 0/29`; 75 `20/46 → 0/51`), and two are test-repair-era with weaker in-file provenance. **Ticket 53 rests on date plus a RED test alone.** Then the 31 files in `proposed-tickets/resolved/` — the tier nobody had classified — were scanned: **20 carry test-repair/mutation provenance** (28, 35, 41, 43, 46, 48–51, 54, 55, 58–60, 63, 65, 67–69, 76), **7 are the #07 comment sweep** (23–27, 29, 30) and 2 are adversarial-review findings.

**So: 18 of 76 primary tickets; ~38 of 105 distinct ticket subjects.** Materially more than 18 and materially less than 50. **The "roughly fifty" figure remains unsubstantiated at that magnitude. Confidence: moderate-to-high on ~38** (my count, criterion stated above, one tier previously unclassified); **high that mutation was the campaign's largest single discovery instrument**; **low on any figure near fifty.**

**One correction to the DURABLE record while checking this.** `intermediate/VERIFIED-practices-with-evidence.md` attaches a *"floor, not a ceiling"* hedge to the fifty-tickets claim, citing `transferable-practices-evidence.md:61`. That hedge belongs to **ticket 31's ~50 zero-detection *mechanisms***, not to the methodology note's ~50 *tickets*. **Two different fifties were merged.** The real hedge on that line is worth quoting instead: *"I could only independently confirm ONE of the 'three separate batches' in full detail (ticket 23)… Treat 'three' as sourced-but-not-triple-checked."*

**Cost.** Agent: **the highest of any mechanism here, and the only one measured rather than reconstructed.** ~161k tokens per repair agent, range 142k–197k, **n=12** — *the only stated measured token range in the entire corpus*. Twelve agents came to **1.93M tokens, 5 points of the weekly limit (94% → 99%) and ~49 points of the session limit**; at ~11 minutes per agent and 2 concurrent, that exhausts a five-hour session window in **~2.5 hours**. The source's own guidance: *"Expect any mutation-based campaign to cost several times a read-and-edit campaign at equal agent count"* — these agents run the suite dozens of times per module. Arnon: near zero, and this is the point. It is the archetype of a mechanism that is expensive in the elastic currency and free in the binding one — **its real constraint is the rate limit, not anyone's attention.**

**One under-valued output: a null that is genuinely informative.** Tickets 65 and 60 both resolved as *"was test blindness, production was never broken"* / *"the gate was already intact; it was a test coverage gap."* `07-escaped-defects.md` scores that as a success: *"Verification that returns 'no defect, but you could not have known' is a success, and it is cheap."* No other mechanism here produces that answer with any authority.

**Transferability: full as a method, with a warning.** Nothing about mutation depends on who is orchestrating. But the harness traps are the reason to be careful in *either* mode: fifteen ways to get a confident wrong number, most of them producing a clean null, is exactly the failure a human receiving a report cannot see. **Confidence: high on transferability; high on the trap catalogue (each row is `[MEASURED]` in the test-repair plan).**

## 3. Comment / docstring verification by execution

**What it is.** Treat every sentence about behaviour as a claim to be *run*, not read. `methodology/verifying-claims-finds-bugs.md`: *"The only way to judge whether a comment is true is to run the code it describes. There is no reading-only version of the check."*

**What it reliably catches.** Claim defects, obviously — but the finding that matters is that **a sweep scoped as prose tidy-up comes back carrying code defects.** The methodology note records **seventeen proposed defect tickets** (`proposed-tickets/17` through `33`) out of a sweep whose brief forbade code changes, with the index recording *"All eleven were found by executing a claim rather than reading it."* Several tickets carry more than one defect, *"which is how Arnon's running count reached 'something like 40 by now'."* Not cosmetic: among them a matcher whose end anchor made `deny` and `ask` rules silently fail to fire; an over-matching pattern type live in five seeded self-permission rules; a consolidation analyzer documented as *"EQUIVALENCE-PRESERVING"* that escalates `ask` to `allow` and whose `--apply` writes it.

**A tension in the record worth stating rather than smoothing.** `intermediate/defect-taxonomy.md` attributes only **6 → 5 corrected** of 76 primary tickets to *"executing the code's own comments and docstrings"* — 8%. The methodology note attributes seventeen tickets to one sweep. The populations differ (the taxonomy excludes the 29 `resolved/` subjects, and tickets 17–33 straddle both directories), and nobody reconciled them. **The methodology's own diagnosis of why it is under-counted is the more useful sentence**: *"It reads like editing, it gets scheduled like editing, and it returns like debugging."* **Confidence: moderate that this mechanism is systematically under-credited; low on any number.**

**Where to aim if you cannot sweep everything** — measured across five modules: *"nearly every false statement found was an assertion about **another** module's behaviour."* An outward-reaching sentence is worth a probe; an inward-facing one usually is not.

**What it provably misses.** Anything nobody wrote a sentence about. It is aimed at the places a previous author thought worth explaining — a good prior, and a prior nonetheless.

**Its own failure mode, and it is specific.** The editor writes *new* falsehoods. Across twelve files reviewed after the unattended run began, *"every falsehood an editor newly introduced was a claim about what a mechanism **guarantees**, never about what it **does**"* — and new text reads as freshly checked. Hence two standing rules: a second cold review pass over any edit loop, and **prefer deletion to rewording**, because deletion is the only edit that cannot introduce a new false claim.

**Cost.** Agent: repair passes ~27 min and ~40 min, a blinded review pass ~10 min, **~100k tokens per review round**, ~$2.25–$6 per repair and ~$3 for the blinded pass (`02-...md` C-21). The whole #07 sweep: 158 files, ~9,100 lines of prose removed, two days. Arnon: low, but non-zero — he set the comment standard and re-set it repeatedly.

**Transferability: full.** This is a reading practice with an execution requirement bolted on, and the execution requirement is the whole mechanism. It works identically with a human reviewer, and the *"prohibiting the fix increases the yield"* rule (§1.7 of `practices-with-evidence.md`) is a scoping decision anyone can make. **Confidence: high.**

## 4. Diagnostic probes

**What it is.** A three-to-twenty-line throwaway script that imports the real module, feeds it one case, and prints what came back. Discarded afterwards.

**The corpus's own verdict, and it is unusually direct** (`practices-with-evidence.md` §3, headed *"The most valuable practice nobody planned for"*): *"They do not trend, do not gate, and cannot be dashboarded; they answer one question decisively and are discarded. On this ticket they produced more findings per unit cost than either metric class and were the least planned for."* **The mutation battery was built as a gate and did its best work as a probe.**

**Worked instances.** The drift-guard live-fire count settled in one replay a question argued about in prose for months — 3,996 index lookups under replay, the guard fired **0** times and the index answer never once disagreed, *"turning 'is this defensive code earning its place?' from an argument into a measurement, and producing the ticket's cleanest deletion."* The physical module-move probe distinguished rename damage (684) from actual move damage (**1**). A runtime callback census found `config` and `resolve` — **two modules with zero import edges between them — calling each other 46,481 times** over a 6,401-case replay.

**The highest-yield deployment was scheduling, not debugging: measure a ticket BEFORE briefing it.** `TOO-45/measurements/README.md`, verbatim: *"**Measuring a ticket before briefing it is this campaign's highest-yield habit.** It closed ticket 57 with zero work, corrected ticket 20's diagnosis, and grounded 39, 64 and 70."* Four worked cases, each a probe of a few lines:

- **64** — probing reachability *per defect* rather than per ticket **inverted the ticket's priority**: the lock the ticket leads with guards a race requiring deliberate concurrent CLI use, while the unnamed atomic-write defect is single-process-reachable.
- **70** — a three-line probe (`wrap_tool_pattern('Bash','Bash(git:*)') -> 'Bash(Bash(git:*))'`) plus reading one function established that `apply_edits` *"**never references `proposal.tool`**"* — *"which is how a caption reading 'tighten Bash' enacted a `Read` broadening to `/**`."*
- **22** — a corpus probe found the redundancy analyzer *"**names the covering rule as redundant too**… acting on the report by deleting everything it lists removes the coverage entirely."*
- **19** — a counting probe showed the counts were self-manufactured: *"**The toolguard counts are almost entirely this campaign's own probes** … **Printing the lines was what revealed it; the counts alone said the opposite.**"*

**And the habit's own cost, which is the sharpest warning in this document**, from the same README: *"**Appending those measurements to the ticket files destroyed the blinding.** … Contaminated by this route: 20, 39, 57, 64, 70."* The campaign's own verdict: *"measuring before briefing was the campaign's highest-yield habit; writing the result into the ticket is what destroyed the measurement."*

**The analytical move that generalises furthest**: when two instruments disagree about the same code, **the disagreement is the finding — do not reconcile it, explain it.**

**What it provably misses.** Everything nobody thought to ask. A probe has no coverage property at all; it is a targeted answer to a formed question, so its yield is bounded by the quality of the question.

**Probes get things wrong too — four recorded, and the pattern is instructive.** The `sys.path` symmetric null (§1). Ticket 88's harness: *"**My first verification run reported 0/7 ordinary uses permitted.** The recipe appeared to block everything — the exact failure this ticket exists to correct. **The cause was my own test harness**"* — corrected to 7/7 ordinary, 6/6 dangerous, 2/2 controls, and then the *inverse* error surfaced: **two of the six "dangerous excluded" results were not excluded by the pattern at all** but by an unrelated ASK floor. Ticket 20's reviewer worked example was irreproducible while its conclusion held by a route nobody had named. And a corpus README cites a verification mutation *"inside `resolve.py::_resolve_one`"* — **no such function exists**, and its claimed 992 mismatches re-measures to 191. **A probe is cheap enough to re-run; that is its answer to being wrong, and it is a good one.**

**Its own failure mode.** Probes are the artifact most likely to be destroyed: an agent cleaning up its own scratch scripts ran `rm -rf *.py` in a scratchpad shared across the whole campaign and deleted *"exactly the four files review-18-round4.md cites as 'Evidence:' for B1/B2/B3"*. The damage was survivable only because the round's prose had quoted the material output and the next task happened to re-verify by fresh execution — *"that is luck plus an unrelated task requirement, not a safeguard."*

**Cost.** Agent: the lowest of any mechanism here — minutes. Arnon: zero. **This is the best cost-adjusted mechanism in the campaign and the corpus says so explicitly.**

**Transferability: full, and it is the cheapest thing on this list to adopt.** The corpus's actionable form is one line: **budget explicitly for probes**, because they are never planned and always pay. **Confidence: moderate-to-high** — the "more findings per unit cost than either metric class" claim is the retrospective's own judgement rather than a count, and it is corroborated by several independent worked instances.

## 5. Blinded code review rounds

**What it is.** A reviewer agent (Opus-class) reading the diff and the code with no access to the implementer's reasoning, returning blocking and non-blocking findings.

**The census, re-counted for this document.** 27 files named `review-<n>-round<k>.md` survive, across 8 tickets (18, 39, 44, 74, 77, 78, 79, 80), max 6 rounds on one ticket (18). Three further review artifacts do not use the `roundN` name — `review-44-redrift-guard.md`, `review-77-grammar-phase1.md`, `review-77-grammar-phase1-delta.md` — giving **30**, which reconciles exactly with `06-planning-attribution.md`'s population. Every verdict line was read verbatim:

**All 27 rounds report at least one blocking finding. Zero clean rounds. Of the 30 artifacts, 28 FAIL and 2 PASS — both PASSes being the `.peg`-only grammar reviews** (§11 below), and neither PASS was clean: the first raised M1, *"four bypasses that defeat the ticket's purpose"*, and required a second round. Blocking findings summed over the 27 rounds = **78**; +2 from the redrift guard = **80**; +2 mediums on the PASS grammar reviews = **82**, matching `06`'s headline exactly. **Confidence: high — an independent recount reconciles to the same total by a different route.**

**This is a floor, not a rate.** The only zero-blocking round anywhere in the record is ticket 45's round 5, and it has **no surviving file** — it exists solely as the terminal entry of a table. Ticket 44's rounds 1–3 are missing entirely, and an agent that found nothing may simply have left no file.

**One correction to the DURABLE record.** `05-campaign-statistics.md` gives ticket 44's surviving trajectory as **1 → 4 → 1**. Round 4's verdict says *"three verified inaccuracies"* and its metrics line says `Blocking: 3.` — the "1" was read off a sub-category (`2 false universals (1 blocking)`). **Corrected: 3 → 4 → 1.**

**What it reliably catches — measured, by classifying all 82 findings for this document:**

| defect class | findings | share |
|---|---|---|
| **CLAIM** | **52** | **63%** |
| COMPOSITION | 13 | 16% |
| SILENT | 12 | 15% |
| INSTRUMENT | 4 | 5% |
| style/quality | 1 | 1% |

**The proportions are driven by round type, not by chance**, and the caveat matters more than the numbers: tickets 44, 77-r1 and 80 were **explicitly scoped as prose-only reviews** — *"comments, docstrings and user-facing message strings only. Not logic, not design, not coverage."* — and contribute **22 of the 52 claim findings by construction.** `06` reaches the same split independently:

| round type | dominant finding class |
|---|---|
| **prose reviews** (44 r4–r6, 77 r1, 80 r1–r3) | **planning-preventable claim defects** — internal contradictions, claims refuted by a file in the same repo, project rules already written down |
| **behaviour/logic reviews** (18 r1–r2, 39 r2–r3, 78 r2/r4/r5, 79 r1–r4) | **execution-only** — measured differentials, shell oracles, config-shape interactions |
| **grammar reviews** (77 phase 1 + delta) | **execution-only** — every finding came from generating and measuring rejected variants |

**20 of 82 (24%) were CONFIRMED preventable by a step costing under a minute** — a grep, opening one named file, counting a constant's references, reading the sibling document in the same commit. Cleanest instance: ticket 74 round 2's *only* blocking finding cost ~1h05m / ~$9–12 and was three change-history paragraphs added to test docstrings **in the same commit as a sweep deleting nine of them under a rule the project had written down verbatim.**

**What it provably misses: anything reachable only by a route nobody enumerated.** `Path.absolute()` escaped **six** rounds and was found by enumerating pathlib's surface rather than by review; `expanduser` escaped four while being a live isolation hole; `resolve` escaped five. This is not "six lazy reviews" — the technique that found `absolute` appears nowhere in the corpus beforehand. It also misses, structurally, what its own scoping excludes: a prose-only round cannot find a logic defect, by instruction.

**And 39% of gate findings were execution-only** — reachable by no amount of reading, only by differential execution, a shell oracle, or building and measuring a rejected design. See the correction above: the reviewers *did* reach many of these, because they executed.

**The late rounds were not ceremony on security-shaped tickets, and the reason is specific: a large share of review yield is defects the *repair* created.** Review-78 round 5 found `bash -c 'dd if=~/.ssh/id_rsa'` walking past an absolute deny rule and returning `PRIVATE-KEY-MATERIAL`, and caught an `ask→allow` loosening **round 4's own repair had just introduced**. Ticket 79's post-mortem: *"Eleven agent runs, four review rounds, and three security weakenings — each introduced by the fix for the previous one."* **A previously-circulated quantification of this — "roughly half of review yield" — was checked and does not hold**; carry the mechanism, not the fraction.

**The most expensive failure of this mechanism is not a miss — it is re-litigation.** Four consecutive rounds of ticket 18 measured the same axis and got a worse or equally bad answer each time, because each repair addressed the direction the last round complained about and lost the other: r3 *"too narrow to be usable"* → r4 **1 of 15** ordinary variants exempt → r5 **11 of 22** permitted → r6 **1 of 16** realistic invocations allowed. Rounds 4–6 cost roughly **$17–19 and about 1h45m of reviewer time** plus three repair passes. The same shape appears three more times (80's *"most modules"*, 78's dead `_command_variants`, 77's `+=` gap). **Every one was pre-stated in writing by the round before, as a non-blocking finding the repair brief did not carry forward.**

**Reviewer error is rare, and the one consequential override ran the other way.** Across all 30 artifacts I found **no case of a blocking finding being refuted as wrong by a repair agent.** Two reviewers corrected themselves inside their own round — *"(I flagged this as fictional before checking; retracted.)"*, and *"The `except (KeyError, ValueError)` catch is exactly right — not a finding. I suspected an uncaught `OSError` and checked CPython 3.14's `Modules/pwdmodule.c` rather than trusting recall."* One review-driven fix was later fully reverted, but by the correct process: 78-r4 blocked on a redirect-glued tilde bypass, the fix loosened `ask`→`allow`, 78-r5 caught the loosening, and the owner reverted on measured zero exposure — **ten of twelve tests written for the fix were deleted with it.**

**The one override that mattered went against a correct reviewer**, and it is the strongest argument in the corpus for trusting a review finding over your own null: *"A review reported that the fix dropped the ASK floor… **They agreed exactly, so I concluded the reviewer was wrong, and told the implementer not to fix it.**… Redone with `PYTHONPATH` pinned: HEAD `ask`, working tree `allow`, on every shape. **The reviewer was right and my null was an artifact.**"* The campaign's own log states the asymmetry: *"a false positive costs one round, a false negative ships the bug."*

**Cost.** Agent: **19 of the 27 rounds carry a self-reported figure; 8 do not** (30% missing, consistent with the corpus's own 29%). Over those 19, taking range midpoints: **~1,022 minutes ≈ 17h02m of reviewer time and ≈ $137, mean ≈ 54 min and ≈ $7.2 per round.** Range: cheapest **13m16s / ~$4** (78-r2), dearest **~$15** (79-r1) and **2h05m** (79-r2). Extrapolating the mean over all 27 gives roughly **24h / $195** — *an extrapolation, not a measurement.* All Opus-priced, and **every dollar figure is an unmetered self-report**; one round explicitly disowns its own clock. Repairs are priced separately (e.g. review-79 round 2 fix ~80 min / ~$16 at Opus; review-18 round 1 repair ~28 min / ~$2.40 at Sonnet-class), so a full round-trip is review **plus** repair.

Arnon: low — he reads a report, or does not. In this campaign he was consulted on **196 of 61,946 tool calls (0.3%)**, with 90.5% of the work running in `auto` permission mode.

**Transferability: partial, and the split is the useful part.**

- **The *blinding* transfers.** It is a property of the mechanism: a reviewer handed a prior findings list checks that list instead of reading cold, measured directly — *"a fresh blinded reviewer caught a false claim that the previous repair pass had just introduced, which a reviewer working from the previous list would have skipped as already handled."*
- **The *execution mandate* transfers, and it is the part to make explicit.** The rounds that found the dangerous defects were the rounds whose reviewer ran something. Nothing about that depends on the reviewer being an agent — but an agent reviewer will run a differential for the price of a round, and a human reviewer usually will not, which is a real argument for keeping the agent round *in* the collaborative pattern rather than replacing it.
- **The *volume* does not transfer.** Thirty rounds is what you run when nobody is available to read a diff.

**The finding that should change practice in either mode: prose rounds and behaviour rounds find different things and were staffed identically.** A large share of what the prose rounds found was reachable by grep, and they were run by the same expensive blinded-Opus reviewers as the behaviour rounds. **Confidence: high on the census and the 82-finding classification; moderate on the staffing recommendation, which is a judgement — it would be falsified by a cheap-model prose round that still caught the CONFIRMED-tier findings.**

## 6. Arnon asking a question

**What it reliably catches: INSTRUMENT defects, and architecture.** This is the mechanism with the best hit rate against the class nothing else covers. Both of the campaign's most consequential premise-level corrections came this way and neither came from a review, a test or a metric: the `sudo`/`env` ticket filed as a security bypass and found on inspection to be **faithful behaviour** whose evading command cannot even execute; and the re-framing of the entire cost analysis after *"When I ask for statistics I care about meaningful summary stats, not for long tables that do not help to make decisions."*

**The taxonomy attributes 14 of 76 primary tickets (18%) to *"Arnon asking a question, reviewing, or instructing"*** — third behind mutation (18) and direct measurement (15). **Verify this against the tickets before quoting it**; it is `MEASURED-SOURCE` from a taxonomy whose sibling census was refuted by 15 on the same day it was written.

**The mechanism behind the hits is stated in the corpus and is not flattery.** *"Correction rate tracked reviewability, not code quality."* The heaviest architectural objections arrived at turns 357–359, near the end, **after surviving seven directed report agents, a blinded reviewer, `pyscn`, `ruff` and 2,600 passing tests** — and Arnon named the cause himself: *"Now that changes are fewer files I start noticing things."* **A reviewer's detection rate is a function of change-set size and collapses toward zero above some threshold — and a review of a large diff still reports success.** That is a statement about attention, not about humans; it applies to whatever is doing the attending.

**A related claim in wide circulation should NOT be carried forward.** *"Every architectural error caught on this ticket was caught by a human asking a direct question — none by any metric, blinded agent, or automated test"* is sourced **only to auto-memory, never to a primary artifact**, and the architecture-judge back-test contradicts it by finding **eight live defects in already-reviewed, already-shipped code**. The defensible residual is the turns-357–359 observation above. **Confidence: high that the claim is unsourced; moderate that the underlying effect is real.**

**Cost.** Agent: zero. Arnon: **this is the entire scarce budget.** 68.9h of prompt-wait across 557 asks was measured, 96.8% of it before 2026-08-03. Every improvement proposed below is ultimately competing for this one resource.

**Transferability: this mechanism *is* human-in-the-loop.** In Arnon's normal pattern it is not a mechanism at all, it is the baseline. **The finding that transfers is the inverse one**: what the human catches is *instrument*, *architecture* and *synthesis* defects, and what he demonstrably does not catch is the silent security class — none of the three was found by a question. So adding him back does not remove the need for the differential. **Confidence: moderate-to-high** (rests on `06`'s case-by-case argument that the three were execution-only).

**SCOPED 2026-08-25 — do not read the sentence above as a general limit on human-in-the-loop.** It is measured on **repair** work, where the intended behaviour was already settled before the ticket opened. It says nothing about feature development, where the dominant behavioural defect is *we built the wrong thing* — a defect **no differential, mutation harness or replay can reach**, because every instrument in this table checks code against *its own* intent. This section's own headline (*"what it reliably catches: instrument defects, **and architecture**"*) is the closest analogue the corpus has to feature planning, and it is the class where the human scores highest. Arnon, 2026-08-25: *"features… are almost always behavioural and have a very strong track record of human-in-the-loop catching things — especially in the planning phase but also in the review phase… Those happen quite a bit in feature development even with a human in the loop, but are very significantly reduced by it."* Full treatment in `08` §5.

**Also unpriced in this table: what the human's involvement leaves behind in the human.** Every cost column here is agent tokens or Arnon's clock time; none of them credits the system understanding that participation builds and absence forfeits. See `08` §5c — it is a real cost of the autonomous mode and no number in this document reflects it.

## 7. Corpus replay

**Three different things are called "replay" and merging them is an error.** (1) `toolguard/tools/replay.py`, **product code** — re-runs historical decisions under a *proposed config*; it is the safety gate on rule consolidation. (2) **ad-hoc HEAD-vs-tree blast-radius replays** — a harness replaying logged commands through two *package trees*; this is where "26,530" and "53,112" come from. (3) `tools/corpus_build.py --verify` — the **golden oracle**, 6,401 in-process plus 61 e2e frozen cases, run at essentially every commit. Tickets 73 and 93 are about (1); the blind-spot report is about (2). This section covers all three and says which.

**What it reliably catches.** Regressions in shapes the corpus actually contains. Ticket 78's replay — **26,530 distinct real Bash commands × 2 package trees, 0 newly-deny, 0 newly-allow, 0 newly-ask, 0 matched-rule changes, 0 digest differences** — is the sound one, *because it compared `matched_rule` and not only the verdict*, and because it froze the corpus first (*"my first attempt produced 26,520 vs 26,523 and was not comparable"*).

**But the famous null does not mean what it is usually quoted to mean, and this is a correction to the DURABLE record.** `.claude/rules/evidence-before-fixing.md` presents it as *"A real bug, correctly fixed, that had never once fired"*. That is faithful to the number and omits what the primary says two paragraphs later:

> *"all 7 live rules naming an absolute path under home are `allow`, so this config can only be widened by the change and cannot show the direction the ticket is about. **So I synthesized it.**"*

**The null was structurally guaranteed by the config, and the report says so.** The informative half of that session was a *constructed* differential, not the replay: over the 562 real commands naming a home path with `~/`, an absolutely-spelled deny rule caught **0 of 562 pre-change** in every pattern type, and post-change caught DEFAULT **320**, `[glob]` **475**, `[regex]` **555**, `[native]` **555**. **So the honest reading is not "a real bug that never fired" — it is "a real bug whose direction this corpus could not express, measured instead by a purpose-built differential."** **Confidence: high** (read directly in the implementation report).

**Replay did find real defects — four cases, and the best one is a security regression it caught in flight.** Ticket 19's coder implemented the brief's suggested generalisation, which *"broke the sink heuristic for the common real-traffic shape `python3 - <<'EOF' 2>/dev/null || true`… **misclassifying a genuine foreign-executor heredoc as a harmless generic sink and losing its ask_floor**. … **Caught this via the corpus replay, not by inspection.**"* Also: a golden diff on the same ticket proved a defect had occurred in real work rather than in a probe, yielding the reusable rule *"a corpus golden diff is an independent exposure measurement, available **after** a fix and not before."* And on ticket 79, exactly **2 of 6,401** in-process cases moved and the coder **refused to regenerate the goldens** and escalated per the corpus README's process — the model case for how an oracle should be used.

**What it provably misses, by construction — three separate ways, each measured:**

1. **Verdict-only comparison is blind to a rule that starts matching when the fallback already permits.** This repo sets `no_match_fallback = "allow_with_no_warnings"`, so an unmatched command was already a silent `allow`. Measured instance: `Bash(\obsidian search:context *)` matched **nothing** at HEAD and matches **now**; the real command appears 5 times in `logs/`. Ticket 18 reported *"zero flips across 53,112 logged decisions"* and read it as safety. **Zero flips is evidence of neither safety nor inertness.** Scope of the masking, measured: featherhill **0 fallbacks in 3,675 decisions (0%)**, toolguard **9,848 of 51,918 (19%)**, instagram 0 — so featherhill-based claims were never masked, a third independent reason to weight it over dogfood.
2. **A clean corpus is not evidence of no regression for a shape the corpus does not contain.** Three measured instances: ticket 98 chunk 2 reported zero decision changes because **none of its 6,401 cases contained the three shapes being fixed**; ticket 101's brace-group deny bypass would have passed `--verify` cleanly because **the corpus contains no brace groups**.
3. **The corpus records the investigation that is measuring it.** toolguard governs this repo's own agent, so every probe run while investigating a defect is logged as a command exhibiting that defect's shape — and featherhill is *not* immune: of 9 apparently-genuine `find -exec`/`-delete` commands there, **8 are probes and 1 is real work**. A corpus is evidence about a **date range**, not about a project.

4. **A fourth, in the product replay: unparseable commands resolve to `ask` under *both* configs and land in the "unchanged" bucket.** Ticket 51 measured **4.3% of real audit-log `Command` fields unparseable (1,783 of 41,442)**. Ticket 73's consequence: *"`corpus replay N entries, 0 broadened` can carry **zero information**, and it is the same string a genuinely corroborating run produces."* One layer up, `harvest_corpus` returns a bare list, so *"**five unrelated reasons to harvest nothing all produce `[]`, byte-identically**"* — and `--max-age-days=-1` is accepted, which *"puts the floor **in the future**, and discards everything."* Mutation on that test module: **17 of 29 surviving at HEAD, 59% blind, now 0 of 29.**

**The fix, in Arnon's own words and preferred order**: *"you can assume the fallback is always ask even if in this repo it is temporarily an allow."* Re-scoring as if `no_match_fallback` were `ask` makes the **instrument** sensitive rather than requiring a second field to be eyeballed, and models the default configuration. Comparing `matched_rule` is the weaker half and still worth doing.

**Cost — and for the product replay the cost is itself a correctness problem.** Agent: tens of thousands of in-process decisions run in minutes, but corpus construction was a substantial build (`corpus_build.py`, 1,007 lines; verdict fixtures 15,548 lines). Ticket 93 measured the consolidation gate: `propose_consolidations` for `Bash` alone went **0.03s with no corpus to 2.20s over 500 real entries**, linear in corpus size and multiplied by candidate count; against the real **61,208-entry** corpus that extrapolates to *"roughly **4-5 minutes for `Bash` alone**"*, on a baseline that *"exceeded **600s** before this change."* The ticket's own conclusion is the transferable one:

> *"**The cost pushes users onto exactly the path 20a exists to warn about.** … **the verification 20a added is the thing users will now most reliably skip. A safety check nobody can afford to run is a safety check that does not exist.**"*

Filed by Arnon as TOO-68. Arnon's own cost: zero to read a replay result — which is precisely why a replay null is dangerous to hand him.

**Transferability: full as a mechanism, with the caveat that its failure mode is a clean null and therefore invisible to a human recipient.** A tidy "0 differences across 26,530 commands" is exactly the kind of result a human in the loop accepts. **The control belongs in the instrument, not in the reviewer.** **Confidence: high** — each blind spot has a named measured instance.

## 8. The ordinary unittest suite

**Scale.** 2,186 tests on `master` → **4,008 at the branch tip** (+83.3%), 804 test classes. **Re-run for this document, 2026-08-24: `Ran 4008 tests in 60.997s / OK (expected failures=4)`** — reproducing `05-campaign-statistics.md` exactly. 895 of them — 22% of the final suite — arrived in one commit, the phase-1 test-repair commit.

**What it reliably catches.** Regressions. That is the honest scope, and Arnon states it himself in `review-conclusions.md`: *"high-coverage unit testing is necessary but mainly guards against regressions [and rarely uncovers dormant bugs]."*

**What it provably misses — and ticket 31 is the campaign's largest quantitative finding:**

| measurement | method | result |
|---|---|---|
| tests whose assertions **cannot fail** | read, then run the fixture or mutate the named mechanism | **~65 across ~78 files** (the ticket's own amendment says this figure was inflated) |
| mechanisms with **zero test detection** | delete in an out-of-tree copy, run all 2,733 tests, subtract a 2-error environmental floor | **~50** |

**22 distinct shapes** of un-failable assertion were catalogued (later reaching 27). Largest single cluster: `test_compound.py`, **12 of 223 tests** satisfied by a fail-open safety net rather than by correct behaviour — **corrected in the ticket's own amendment to 16, not 12**. And the suite was **green through all three security defects**.

**The ticket's corrections to its own numbers are as important as the numbers**, and they are the model for how to report an instrument's output: *"THE ~65 FIGURE IS INFLATED, and the cause is a systematic conflation"* — an assertion that **cannot fail** and one that **cannot distinguish** were counted as one — *"Do not re-report the ~65 figure without re-deriving it against this distinction."* And *"The ~50 figure is therefore a floor, not a ceiling."*

**The fair reading, in the ticket's own words**, because the numbers above invite an unfair one: *"This ticket does **not** claim the suite is bad. 2,733 tests catch a great deal, and several files came back with **zero** findings after mutation — `test_resolve.py` and `test_once_per_store.py` both had every probe detected. The finding is narrower and more useful: **where the suite is blind, it is blind silently, and the blindness clusters in exactly the layers where toolguard's defects were found.**"*

**Where the suite did work as a gate, it was mutation that showed it.** Item 95 ran four mutations one at a time with verified byte-identical reverts: **30 failures / 20 / exactly 1 / exactly 1**, the last two being the pinning tests the ticket had predicted. *"Every mutation was caught by an existing test. No coverage gap found, so no new test was added."* The log records it as *"first clean mutation-verify in the run"* — **after tickets 97 and 98 chunk 1 both found gaps.** A green suite becomes evidence only once something has tried to make it go red.

### Coverage does not predict any of this

**No repo-wide or campaign-wide coverage figure exists anywhere in the corpus** — searched for this document and not found. Only incidental per-module numbers (`toolguard.ambient` at 100%, TOO-19 at 91.4%). So the question "did coverage predict defect discovery?" cannot be answered by correlation. **What the corpus does record is three independent statements that it does not**, and they agree:

- **The direct measurement.** The orchestration sat at **100% line coverage** with a *"savagely skewed hit distribution"*: distinct cases reaching each `no_match_fallback` branch were `allow` **2,336** : `ask` **34** : `allow_with_warning` **6** : `deny` **6**, with **three defensive lines reached zero times**. Corpus strengthening was consequently gated on mutation-based acceptance rather than on case counts.
- **Arnon's framing**, verbatim: *"high-coverage unit testing is necessary but mainly guards against regressions, and is well known to rarely uncover dormant bugs. Randomized perturbation by blinded agents does the opposite — it surfaces issues nobody thought of."*
- **The explicit anti-correlation**: *"Assertion count, coverage and a green suite all fail to detect this; one mutation detects it in a minute."* And ticket 31's finding that blindness *"clusters in exactly the layers where toolguard's defects were found"* — the correlation runs opposite to what coverage would predict.

**Confidence: high** that coverage is not an indicator of detection here; **the absence of an aggregate figure is itself the finding** — nobody ever measured it, and nothing in the campaign needed it.

**The general form is worse than "some tests are weak".** A test double that re-implements production, a fixture built from defaults so a hardcoding mutant is invisible, a Given/Then that describes something the assertions do not check — all of these produce a green row that is green for the wrong reason, and **the suite cannot distinguish them from a real pass**. `01-...md` §1 lists five measured instances of green-for-the-wrong-reason across the campaign's instruments; ticket 88's is the sharpest: **2 of 6 "correctly excluded" dangerous `find` invocations would have stayed excluded with the rule deleted entirely.**

**Cost.** Agent: marginal cost near zero (58s per full run), build cost enormous — `test/` received 66,640 insertions on this branch. Arnon: zero.

**Transferability: full, and the finding is uncomfortable in both modes.** A suite is a floor, not a verifier, and its size is not informative about what it detects. The only measurement that answers "what does this suite catch?" is mutation. **Confidence: high** (ticket 31's numbers are the campaign's own, with the source's own inflation hedge preserved).

## 9. Architecture fitness checks (`tools/architecture_fitness.py`)

**The two facts that are not in tension** (`rejected-methods-and-metrics.md` B2): it is *"the most valuable custom artifact of the campaign"* **and** *"the home of nearly every instrument defect in it"*. The reason it is valuable is stated precisely: *"Writing the claim down as executable code is what converted nine unknowable beliefs into nine findings."*

**The rule that determines which checks are trustworthy** — established from Arnon's observation that some fitness findings are unambiguous, and it is the single most reusable idea in this document:

> **A check is unambiguous exactly when it measures conformance to intent a human declared, rather than inferring whether the intent is any good.**

**The nine modes, checked against the tool's own constants at HEAD `305caa3`** (all six static modes re-run for this document, 2026-08-24):

| mode | checks against | strength |
|---|---|---|
| `--layers` completeness | the `[architecture]` layer map in `.pyscn.toml` | **strong** — a human declaration; binary, total, no threshold. *"All modules map to exactly one layer" (78 examined)* |
| `--layers` direction | the declared `allow` lists in the same file | **strong for direction**, but the map itself is gameable — see below |
| `--stdlib` | `sys.stdlib_module_names \| STDLIB_ALLOWED_ROOTS` (`= {"toolguard"}`) | **strong** — the declaration is the stdlib set plus a one-name allowlist |
| `--ambient` *ownership* | `OS_IMPORT_OWNERS` (8 entries), `PATH_AMBIENT_OWNERS` ((module, member) → reason) | **strong for what is listed** |
| `--ambient` *enumeration* | `PATH_AMBIENT_MEMBERS = {"absolute","cwd","expanduser","home","resolve"}` — a **human judgement** about which members count | **WEAK — four defects escaped here** |
| `--undeclared-types` | **the return annotation itself**; `UNDECLARED_TYPES_OPEN_ENDED_EXEMPTIONS` is `frozenset()`, empty by design | **strong** |
| `--orphans` | **the leading underscore itself** — its docstring: *"a developer writing `_name` declares 'internal to this package', and this tests conformance to that declaration alone — never whether the function deserves to exist"* | **strong**, with a self-declared blind spot for `getattr`/dispatch reach |
| `--mocks` | no declaration — it *derives* inertness from the import graph | **heuristic**, and correctly non-fatal (`INERT_PATCH_CHECK_IS_FATAL = False`) |
| `--predicates` (R1–R6) | its own name-substring detectors | **heuristic** — R3 demonstrably wrong today |
| `--metrics` | thresholds (`MIN_COUPLING_OBSERVATIONS = 3`) | signal only |
| `--guard` canaries | `GUARD_CANARIES`, 12 fixed `(tool, target, expected verdict)` cases | **strong**, and its maintenance comment is the model: *"Updating an expectation to match whatever the hook now returns defeats the whole check."* |

**Note which modes are strong: every one whose reference is a declaration somebody wrote down, including two — `--orphans` and `--undeclared-types` — whose "declaration" is a syntactic convention in the code itself.** That is the cheapest kind of declaration there is, and it is why those two modes are trustworthy while `--predicates` is not.

**What it provably misses — and every instance is the SILENT class occurring inside the instrument built to prevent it:**

- `run_guard(only_canaries=True)` with an **empty canary set** returns `ok=True` and prints `=== --guard: PASS === (no violations)` — a clean, un-skipped run of zero cases. `check_layers` reports `ok=True` over a tree with **zero modules**; `compute_predicates` reports **R2, R3, R5 and R6 all `pass=True`** over the same empty tree.
- **The layer map is gameable and the checker cannot tell the difference by construction.** Demoting `once_per` manufactures a violation; adding `"observability"` to foundation's allow-list **erases it**, and the renderer prints the identical *"No cross-layer direction violations"* either way. Loosening the map, deleting a row, emptying `LAYERS` entirely and inverting the layer order each failed **zero** tests. A separate probe found **five one-line edits tried against the one remaining violation; three erased it with nothing catching the edit.**
- **`--ambient`'s enumeration has now been escaped four times**: `expanduser`, `resolve`, `absolute`, and — still open — `pwd.getpwnam`. `Path.absolute()` is the one that also escaped six review rounds.
- **`--predicates` R3 currently prints `=== R3: PASS ===` over a live prose re-parse**, because its detector only sees receivers whose own name contains `reason` and the site's receiver is named `r`; its sanction list still names a function that no longer exists. The corpus's own verdict: *"the codebase contains an instance of its most expensively-documented antipattern, and the instrument built to catch that antipattern reports PASS."*

**And the tool blinded the static analyser that was supposed to check it — three levels deep.** A three-name `except json.JSONDecodeError, KeyError, TypeError:` made pyscn print *"Warning: Failed to parse file … syntax errors found in source code"* **and then report Health Score 100/100, Grade A, all five metrics 100/100.** *"So the static analyser the pre-push checklist depends on **reports perfect health for a file it could not read**."* The census the ticket corrected: **6 three-name clauses across 4 files and 23 unparenthesized clauses**, not 3 and 22 — including `test/unit/_real_log_dir_guard.py`, *"**the suite's central safety machinery**… three levels of instrument failing to see itself."* Two further facts from the same ticket: pyscn does not crash on the generated parser, it **hangs** it (killed past six minutes); and `.pyscn.toml` excludes `**/test_*.py`, so **no pyscn-based guard can ever cover the test suite** — which is why the repaired guard is AST-based. **Re-measured at HEAD: fixed** — one two-name bare tuple remains, which is valid under PEP 758 and harmless at that arity.

**What the fitness checks actually caught — and note what the strongest two caught.** Tickets 44 (four surviving `expanduser` home reads plus a live test-isolation hole), 80 (`Path.resolve()` as a fifth route to cwd, 17 call sites), 81 (found **by the agent building the check**), 45/43 (one inert patch whose companion assertion passed vacuously), 66 (PASS-over-nothing in five entry points, 7 of 9 map mutants invisible, a relative-import blind spot, two dead renderers), 29, 30, 100 and 104 (each of which *proposed* a new mode). **`--stdlib` and `--layers` caught nothing during the campaign.** They exist to prevent, and that is a legitimate role — but it means the modes with the strongest declarations are also the ones with no yield to show, and a yield-based ranking would retire exactly the checks worth keeping.

**The single most actionable finding about this whole class of instrument.** For ticket 80, the closing instrument was **a runtime sentinel wrapping `Path.resolve`** — and it already existed in the repo as `test/unit/_real_log_dir_guard.py`, first committed **eighteen days earlier**. *"Estimated saving had the sentinel been chosen first: the AST checker's construction, three tickets' worth of route-table enumeration, and the fifteen-odd review rounds those three routes survived."* **A runtime sentinel catches the route nobody enumerated; an AST enumerator cannot, by construction.** **Confidence: high on the sentinel pre-existing (commit `51045fe`, dated); moderate on the saving, which is the source's own estimate.**

**A related scoping correction on `--mocks`, from Arnon.** Ticket 45 proposed asserting `mock.called` to catch unreached targets; his objection: *"Asserting `called` there **converts an incidental dependency into a specified one**… **That is a worse defect than the one being guarded against.**"* And the ticket's own framing of what all three mechanisms really measure: *"**the number of mocks a suite needs is a measurement of how many implicit dependencies the code has.** Guarding the mocks does not reduce that number; it just stops it hurting silently."*

**The general rule this produced**: *"any check whose configuration lives in the same repository as the code it grades can be edited to pass without the underlying property becoming true."* **Read facts, not labels** — derive the entry-point set from `pyproject.toml [project.scripts]`, a fact about what ships, rather than from an editable layer file.

**Cost.** Agent: low to run — all six static modes complete in seconds — **very high to build**: `architecture_fitness.py` is 4,978 lines with a 4,735-line test module. Arnon: low.

**Transferability: full for the declaration rule, which is the part to keep.** *"Before proposing any new check: name the declaration it checks against. If there is no declaration — if the tool has to supply the judgement itself — it is a heuristic, and it must be labelled one rather than reported as a verdict."* **Confidence: high** (every defect above is `[MEASURED]` in ticket 66 or in `DECISIONS-PENDING.md`).

## 10. Static analysis and lint (ruff, pyscn, pyright/LSP, code-review-graph)

**What it catches.** Local, mechanical, syntactic properties, reliably and free. Two named contributions in the record: a pyright *"not accessed"* warning that found `_resolve_leaf` called by ~30 tests and by **no production code**; and evidence for one architecture-judge defect.

**What it provably misses — and the demonstration is the campaign's own founding defect.** The ticket's **largest** structural change, removing a `config → engine` callback inversion, has **zero import edge**. *"Three independent static instruments (import graph, pyscn layer compliance, ruff) were all blind, all green, on the defect that motivated the ticket."* Runtime said the opposite: `config` and `resolve`, **zero import edges between them, called each other 46,481 times** over a 6,401-case replay; after the fix, config-layer execution on the decision path fell **87%** (~2.9M → ~380k calls) **while `config`'s static fan-in went up by one.** A tool measuring only import edges would have called the change neutral to slightly worse.

**The generalisation** (`rejected-methods-and-metrics.md` B3): *"An import graph measures **declared** dependency. Inversion of control, callbacks, dependency injection, registries, string-keyed dynamic dispatch and monkeypatching all create real dependencies that carry no import edge — and they are exactly the constructs a mature codebase accumulates. A layer checker built on imports is systematically blind to the most sophisticated coupling in the system, and its green is loudest precisely where the design is worst."* Arnon's framing: *"It is easy to hide from static analysis and hard to hide from observed runtime behaviour."*

**Two specific negative results worth keeping.**

- **Never adopt a lint rule without handing it a known positive first.** `PLC2701` looked like the natural enforcement for a step entirely about cross-module private access; it fires only on private imports from a module *external to the importing file's package*, so it reports **clean on the exact line the project's own predicate flags as a violation**, permanently, by construction. It was **considered and rejected**, and `pyproject.toml` ships the rejection.
- **A tool can revert its own fix.** Ticket 30's stated fix for pyscn parse-blindness — parenthesise a three-name `except` tuple — was measured false one day later: `ruff format` reformats it straight back, *"silently reverted by this project's own mandated `uv run ruff format .`, re-blinding pyscn with no signal at all."*

**Also rejected: aggregate architecture scores.** pyscn's health grade, and the general form by extension. Four aggregates were tracked across the campaign and three moved anti-directionally or for arithmetic reasons: 100%-coupled co-change pairs **71 → 134 (+89%) while the architecture demonstrably improved**. Arnon, verbatim, with the scoping clause that a later summary ellipsed out and was corrected for: *"pyscn health score - like any other aggregate 'architecture metric' **we discussed** - it is pretty useless, even as a directional measure."*

**Cost.** Agent and Arnon: both near zero. That is the argument for keeping it — not its yield.

**Transferability: full. Confidence: high.**

## 11. Two-phase review of a formal artifact (the `.peg` grammar rule)

**What it is.** Change the generated artifact first — `.peg` plus canopy regeneration, nothing else — and review that alone, before any consuming Python.

**The evidence, and it is the sharpest single process statistic in the corpus.** Of 30 review rounds, **2 PASS and 27 explicit FAIL** — and both PASSes are the two `.peg`-only reviews. **The asymmetry measures checkability, not review quality.** A `FAIL` verdict is a round yielding findings, which is what a round is for; the 27 are not a poor record. What the two-phase artifact adds is that a reviewer can settle the question *mechanically* instead of judging it, so "nothing wrong here" becomes a statement someone can stand behind rather than an absence of objections. What the reviewers actually did is why the gate held: regenerated the grammar with canopy into a scratch directory and `diff`ed against the committed generated parser — **0 lines**, *"the single worst outcome for this gate, a hand-edited 'generated' file, is ruled out, not assumed"* — then a differential over **23,594 distinct commands with `differing=0`** and parse failures unchanged at `506 → 506`. The delta review **built the rejected variant grammar and measured it**: `variantA vs pre-change: differing=280`, *"274 commands lose nested decomposition… It is also understated: variantA additionally turns 88 commands into parse failures"*; the second variant produced **307 real commands becoming parse failures**.

**Why it works**: the phase separation hands the reviewer an artifact that is *mechanically checkable end to end* — regenerate, diff, replay a corpus — where every other review round in the corpus asked a judge to decide whether a change was correct.

**Two corrections that must travel with it.** Neither PASS was clean: the first raised M1, *"`$(...)` in an assignment value, and `$(...)` as the command word, both defeat the ticket's purpose"*, with *"Decision needed, and it needs to be made now, not in phase 2"*, and required a second phase-1 round. And **it does not immunise phase 2**: ticket 101's brace-grammar attempt passed an isolated validation and then produced **19 unexpected failures** on the real tree, including `{ ls; }` decomposing to `['{ ls', '}']` — *"a real deny-bypass, not just a test-shape mismatch."*

**Transferability: the mechanism transfers; the result may not generalise.** **My judgement, low-to-moderate confidence**: a `.peg` file is small, formally specified, and has a mechanical differential (regenerate and diff over a corpus). Most changes have none of those properties, and the two clean PASSes may be a property of *the artifact* rather than of the sequencing. **What would change my mind**: one clean review round on a two-phase change to a non-generated artifact. The corpus contains none.

## 12. "Tell every subagent the brief is unverified, and to verify it"

Listed because it is a verification mechanism, it is the cheapest item anywhere in the corpus, and it is easy to overlook as process rather than as testing.

**What it is.** One paragraph in every brief: *"do not take my word for any of this — verify it yourself."*

**What it catches: CLAIM defects in the coordinator's own briefs, at a steady rate for the entire campaign — roughly thirty corrections**, including the same figure wrong three times. Two runs of consecutive counting: *"four consecutive, all caught by the agent, none by me"* and later *"seven consecutive, every one caught by the agent"* — **and a 2026-08-23 correction notes these are two moments of the same observer's self-report, not independent runs.**

**It has negative controls, which is why the count is credible.** Three sampled reports record the opposite outcome — *"Nothing in the brief was false. Every one of B1-B7 reproduced exactly as described"*; *"Nothing in the brief was false… This breaks the week's streak"*; *"Nothing in the brief was found false."* The agents were not manufacturing corrections to look diligent.

**The diagnosed cause matters more than the count**: *"A report is a session delta; a review measures HEAD."* The coordinator forwards agent reports as current state, so its briefs go stale in a systematic direction — too tidy, too confident about counts and sole-consumer claims.

**The sharpest contrast in the record.** Tickets 74 and 18 share the same cause (inherited staleness in a brief). **Ticket 18 cost ~11 hours** (agent-run currency; 4h15m by wall clock — the corpus carries both and they rank differently); **ticket 74 cost one command.** *"The difference was execution before work, not better ticket-reading."*

**What it provably misses.** *"It catches false claims, not omissions. Every one of the ~30 corrections was a wrong statement; nothing in the record shows an agent catching something the brief simply failed to mention."*

**Transferability: full, and it changes shape rather than disappearing.** In human-in-the-loop mode the brief-writer is Arnon, and the finding becomes *the human's brief is also unverified*. **Confidence: high on the mechanism, moderate on the ~30 count** (one observer, self-reported, with a correction already applied to its independence claim).

### A HUMAN ASSERTION IS NOT AN ORACLE EITHER — Arnon, 2026-08-25

**This section previously said "the corpus offers no evidence either way on whether a human's brief goes stale at the same rate." That was wrong, and the evidence was in this project's own rule files.**

> *"I can tell you from experience both with you and with human teams that the human assertions are incorrect surprisingly often. It's either that the human had a faulty memory, a misread or misunderstanding of the facts, or operated from an unverified report, or that the assertion was correct at the time it was written, but no longer correct at the time the work started (those can have a different time measured up to years in corporations and even in personal projects). **So human assertions should not be considered an oracle and must be checked just like any AI assertion.**"*

**Four causes, and they are not the same failure.** Faulty memory; misreading the facts; **relaying an unverified report second-hand**; and **time-decay** — true when formed, false when acted on. The third and fourth are the dangerous ones, because in both the assertion was *never wrong at the moment it was made*, so no amount of care by the speaker prevents it.

**The corpus has four documented instances, and none was noticed as a class:**

| instance | cause | source |
|---|---|---|
| **Ticket 82's `sudo`/`env` premise** was approved for fixing, then found on inspection to be **faithful behaviour** whose evading command cannot even execute | approval on reasoning, not evidence | `.claude/rules/evidence-before-fixing.md`, in Arnon's own words: *"I may also have been **too eager to approve** things that are not a real exposure"* → **"Approval is not evidence."** |
| *"Native once took only a trailing wildcard"* | **time-decay** — the textbook case | `.claude/rules/native-fidelity-claims.md`: the recollection *"was correct **for an earlier version**"* |
| *"4 of 425 links skipped, one genuinely broken"* | unsourced recollection quoted as measurement | `intermediate/open-questions.md`: *"Treat it as an **unsourced recollection, not a measurement**"* — the 425 denominator could not be found |
| *"Reviewers were asked and repeatedly produced poor results"* | recollection in tension with the measurement | `10-human-vs-ai-reading.md` §367, which then finds the two askings were not the same kind |

**And the mechanism is the one this section already named, running on a longer clock.** The diagnosis above is *"a report is a session delta; a review measures HEAD."* **A human assertion is the same object with a vastly longer delta** — his point is that the gap runs to *years* in an organisation, and is long even in a personal project. Staleness scales with that gap, and **nobody re-dates a remembered fact**: it is recalled with the confidence it had when formed, stripped of its expiry. So the human version of this failure is not milder than the agent version; on the time-decay axis it is **strictly worse**.

**There is also an authority asymmetry that makes it worse to leave unchecked.** An agent's brief is visibly a derived artifact and this project already instructs everyone to distrust it. A human's assertion arrives as ground truth and is the thing agents are told to obey — so **the assertion least likely to be challenged is the one whose staleness clock has run longest.** Ticket 82 is exactly that shape: an approval, given quickly, that then framed the work until someone fetched the documentation.

**What this changes operationally.** *"The brief is unverified"* must not be scoped to agent-written briefs — **it is a property of assertions, not of authors.** The practice already exists in this repo for the highest-risk case and is written author-blind: `native-fidelity-claims.md` requires that any claim about native behaviour be **fetched and quoted with a date**, *"not restated from memory, from another agent's summary, or from this repository's code"* — and its own worked example of the rule biting is a human recollection. **Generalise that, do not re-derive it**: for any load-bearing claim, record what it rests on and when it was established; treat an undated assertion as unverified regardless of who made it. Where a claim rests on what a note *says*, check what the repo *did*.

**The one thing that does not change.** Checking is not disbelief, and this is why the mechanism is cheap: the negative controls above show agents reporting *"nothing in the brief was false"* three times over. **Verification's cost is the same whether the claim turns out true or false**, so author is the wrong variable to condition on.

## 13. The punch list — verifying the process against itself

**Missing from this document until 2026-08-25, and the omission has a diagnosable cause: every other entry here verifies the *code*, so a mechanism that verifies *whether the work was done* had no column to sit in.** Arnon named it:

> *"You tend to forget what you were supposed to do and declare early completion before work is actually done. The remedy is to make any non-trivial sequence into a punch list that can be verified and reviewed both by you and by me. Whenever we did that, the likelihood of forgetting parts dropped significantly. Not 100% eliminated, but much better. **It's a verification in the process about the process — not against the code or the tests — but verification nonetheless.**"*

**What it is.** Any non-trivial sequence written out as enumerated, individually checkable items, held where both parties can review it against the work actually delivered.

**What it catches: SCOPE-COMPLETION defects** — a step silently dropped, and "done" reported over it. **This class is invisible to every other mechanism in this document.** A differential, a mutation run and a replay all check *the code that exists* against intent; none of them can observe a step that was never taken. Tests pass, the review round passes, and the omission leaves no artifact — the campaign's signature *fails open and says nothing*, applied to the work plan rather than to a mechanism.

**The measured instances, and they are not marginal:**

| instance | what was dropped | cost |
|---|---|---|
| **A11 — the TDD refactor step** | The TOO-19 plan mandates four steps ending *"refactor while green."* **All three** implementation reports restate it as three. **0** files in the whole corpus carry a phase-shaped refactor line, while the control fires (planning 20, implementation 32) | unmeasured, campaign-wide |
| **Item 10's sweep** (`07` C1, `12` A12) | The review found the right defect class and the fix landed in **2 of 3** files, leaving the third in `hook.py`, *the component that governs* | **every non-builtin governed tool bricked for 11 days**; re-derived from scratch 5 days later |
| **The resume note** (`feedback_punch_lists_must_enumerate`) | A punch list that *pointed* — *"then batches 2-4 from `<file>`"* — instead of enumerating. After compaction I acted on the two inline items and never opened the file | **23 of 28 open tickets lost**, including two marked *"fix before push"*, open ten days. Caught by Arnon noticing the queue looked short |

**Why it works, and it is the same principle as A10.** *"A check is unambiguous exactly when it measures conformance to intent a human declared, rather than inferring whether the intent is any good."* **A punch list is that declaration for work.** Without one, "done" is unfalsifiable — there is nothing to compare against, so nobody can be wrong. With one, done-ness becomes conformance to an enumerated list, and an omission is *visible without anyone judging anything.* A11's own diagnosis says precisely this: *"the agent tracked the steps that could be checked… and did not perceive the one that could not. **Not refusal, not eagerness — not encoded.**"*

**This is the general form of several things already recommended separately.** A5 (carry the previous round's non-blocking findings forward), A11 (a required report section per mandated step), A12's queue, and `07`'s sibling sweep are all instances of it — and `08` §6 arrives at the same shape from the follow-through direction: *an artifact slot the reporting template demands.* **They should be understood as one mechanism with several applications**, not as four unrelated tips.

**What it provably does not catch.** The same limit as A6: **items that were never on the list.** A punch list verifies delivery against a declared scope; it says nothing about whether the scope was right or complete. It is also **defeated by enumeration-by-pointer** — the 23-of-28 loss is that failure exactly, and it is silent because *"then batches 2-4 from X" reads like a finished sentence.* So the mechanism's own precondition is a rule: **enumerate every item inline, by identifier and one line; a cross-reference is for detail, never for membership.**

**Cost.** Agent: ~zero. Arnon: ~zero, **and it is the only mechanism in this document he can audit without reading code or trusting a report** — which is why it is worth more in an autonomous loop than its price suggests, and why `08` §5c's unpriced-understanding argument applies to it too.

### The one before/after pair, checked 2026-08-25

**An earlier version of this section said "no before/after evidence exists anywhere in the corpus." That was wrong — I had cited only the *before* half of an incident that has both.** Arnon recalled the after half; per §12 it was checked rather than taken, and it holds.

| | |
|---|---|
| **Before** (2026-08-20) | A resume note whose queue read *"**17**, **18-remainder**, then batches 2-4 from `TOO-45 status 2026-08-14 - phase 2.md`."* After compaction I acted on the two inline items, never opened the file, and **reported a five-item queue against a real ~28** — two of the missing marked *"fix before push"* and open ten days |
| **The switch** | `TOO-45-punch-list-2026-08-20.md` — *"everything still to do… Supersedes any earlier ordering."* **34 items enumerated inline, zero pointer-style membership** |
| **After** | No successor artifact reintroduces the failure |

**The after evidence is structural, not merely an absence of complaints, and that distinction matters here.** The successors carry the rule in their own text: `TOO-45 punch-list 2026-08-22.md` opens *"**Every item spelled out inline. Do not replace an item with a pointer to another file.**"*, and `TOO-45 phase 3 resume.md` declares *"**THE PUNCH LIST IS THE AUTHORITY**… Enumerated, not pointed at."* **So the remediation was encoded into the artifacts rather than remembered**, which is exactly the `12` §C4 form — a slot the template demands, not a prose mandate — and it is why this one did not decay like the four in §A-y.

**What still limits the claim, stated because absence-of-repeat is the weakest evidence shape this project has:** the window is **five days**; n is **one** incident; and the detector for a repeat is the same one that caught the original — **Arnon noticing the queue looked short.** `.claude/rules/evidence-before-fixing.md` warns precisely here: for a failure that is silent by construction, a null measures observability. **The structural evidence is what carries this, because it does not depend on the detector** — the artifacts enumerate whether or not anyone checks them.

**One live residual, found while checking.** The original failing sentence is **still present** at `TOO-45 phase 3 resume.md:36`, above the correction at line ~192 that supersedes it. Superseded, not deleted — a stale pointer sitting in a live file, which is the same shape as the `RED:` markers in `12` §C12. Worth deleting rather than leaving to be re-read.

**Confidence: high on the mechanism and on the direction; the magnitude remains unmeasured.** *"The likelihood of forgetting parts dropped significantly… not 100%"* is Arnon's observation across this campaign and human teams, **dated 2026-08-25**. **There is one documented before/after pair, structurally corroborated — there is no rate**, and none should be invented from a single incident.

---

# What to do differently — ordered by expected value

Expected value = (defect class it addresses × how silently that class fails) ÷ Arnon's attention required. Every item costs agent time and near-zero human attention except where stated.

**1. Make a differential a standing *instruction to the reviewer*, not a separate gate.** The three worst defects were each found inside a review round, by a reviewer who ran a differential rather than reading one — a `PYTHONPATH`-shadowed HEAD tree, a real `bash` oracle, a HEAD-blob-versus-working-tree grid. Nothing else in the campaign found them. The recipe: two isolated trees, `PYTHONPATH` pinned, **module provenance printed from inside the measurement**, diffing `decision` *and* `matched_rule` *and* the sub-command breakdown. **Measured price: as little as 13 minutes and ~$4 — the cheapest of the three rounds that caught a serious defect. Confidence: high.** This is the single highest-value change on the list and it is nearly free.

**2. Every instrument must carry a control that should fail — and name which wrong answer it catches.** Not a validation step; a control, inside the same run. Five measured clean nulls in this campaign (replay masking, isolation symmetry, corpus shape-absence, a grammar `comment` rule firing zero times, `find` rules that pass with the rule deleted), plus several more outside that table. The concrete forms in the corpus's own order of strength: include a case that *should* fail; **delete the mechanism under test and confirm the result changes**; treat a symmetric or universally-clean null as suspicious.

**The half that is usually skipped is the naming**, and ticket 105 is the case that proves why: *"**What makes this the sharpest case: I DID run a control, and it passed, and that is why I was confident.** The control caught a real bug (I had passed a string where a tree was wanted…). Catching it made the instrument feel validated — **for a different class of error than the one I was actually making.**"* **A passing control validates the instrument for one class of error only.** **Confidence: high.** The corollary that matters most for Arnon's normal mode: **a human receiving a clean null has no signal at all. The control belongs in the instrument, not in the reviewer.**

**3. Prefer a runtime sentinel to an enumerated bad-list, wherever one is possible.** `expanduser` escaped four review rounds, `resolve` five, `absolute` six, and `pwd.getpwnam` is escaping now — *"An enumerate-the-bad-list rule cannot catch the route nobody thought of."* The sentinel that finally closed the class was **already in the repo eighteen days before the ticket that needed it**. The generalisation: an AST enumerator answers *"is this on my list?"*; a runtime sentinel answers *"did anything reach the real thing?"* — and only the second question has a bounded answer. **Confidence: high on the mechanism; moderate on how widely a sentinel is available** (it needs a single chokepoint to wrap, which many properties do not have).

**4. Re-score every corpus replay as if `no_match_fallback` were `ask`.** Arnon's own instruction, and it converts an insensitive instrument into a sensitive one rather than asking a reader to eyeball a second column. **Confidence: high.** Cost: one flag.

**5. Measure a ticket before briefing it — and never write the measurement into the ticket file.** The campaign's own highest-yield habit (*"It closed ticket 57 with zero work, corrected ticket 20's diagnosis, and grounded 39, 64 and 70"*), and the way it was spoiled five times: *"Appending those measurements to the ticket files destroyed the blinding."* Put the measurement in the brief, or in a sibling file the estimator cannot read. **Confidence: high on both halves** — the yield claim names four tickets, the contamination names five.

**6. Carry the previous round's non-blocking findings into every repair brief, marked fixed / deferred-with-a-reason / rejected.** Four documented escalations each burned a full extra round on something a previous round had already written down; ticket 18's four-round curl oscillation alone cost ~$17–19 and ~1h45m of reviewer time plus three repair passes. **This is the cheapest fix identified anywhere in the corpus and it is in no project rule today. Confidence: high** on the four instances; **moderate** on the saving, which is a judgement.

**7. Fix the class, not the instance — and record the class where it will be actioned.** 4 of 6 confirmed escaped-defect chains were instance-fixes *with the technique already in hand*. The worst: item 10's own review found the right class and fixed two of three files, leaving the third **in `hook.py`, the component that governs** — every non-builtin governed tool denied on every call for **eleven days**, then re-derived from scratch by ticket 74 five days later with no reference to the earlier finding. The corpus's own rule: *"a product defect recorded only in the queue is a defect that will never be actioned."* **Confidence: high.**

**8. Budget explicitly for diagnostic probes, and give each agent its own scratch directory.** Best findings per unit cost of anything measured, and the least planned for. The scratch-directory half is one line of config and closes a hazard that destroyed a review round's cited evidence and was survived by luck. **Confidence: moderate-to-high** on the yield claim (the retrospective's judgement, corroborated by several worked instances); **high** on the scratchpad hazard.

**9. Staff prose review rounds differently from behaviour review rounds.** They were run identically, by the same Opus-class blinded reviewers. A large share of what the prose rounds found was reachable by grep — internal contradictions, a claim refuted by a file in the same repo, a rule the project had written down. **This is a judgement, moderate confidence**; it would be falsified by a cheap-model prose round that missed the CONFIRMED-tier findings, and that experiment has not been run. It is also the item on this list with the clearest cheap experiment attached.

**10. Before proposing any new check, name the declaration it checks against.** If the tool must supply the judgement itself, label it a heuristic and never report it as a verdict. Four escapes from `--ambient`'s enumeration, three one-line edits that erased a layer violation with nothing catching them, and an R3 check printing PASS over a live instance of the antipattern it exists to catch. **Confidence: high.**

**11. Run mutation on the mechanism you just built, not only on the code you are protecting — and diff failing test *sets*, never counts.** Both rules are earned: 2,314 tests stayed green through a swap that corrupts every audit entry; four mutually contradictory mutants failing the same one test read as detection and was not. **Confidence: high.** Cost: this is the expensive one — ~161k tokens per repair agent — and it is worth it precisely because the currency is elastic.

**12. Keep telling every subagent the brief is unverified.** ~30 caught false claims for one paragraph. **Confidence: high.** In human-in-the-loop mode, apply it to the human's brief too — the corpus cannot say whether that rate holds, which is itself worth measuring once.

**13. Ask the synthesis question at every boundary.** The synthesis gap was observed at four independent scales, and *"it is not a limitation of subagents or of LLMs — it is a property of narrow, exhaustive attention as a method, and it applies to whatever is doing the narrow attending."* The corpus's cheapest human-side fix: **voice unformed smells at quarter-confidence, and ask for them at boundaries** — not *"does this look right"* but *"is there anything bothering you that you haven't raised."* Three of the five most-escalated themes were noticed early and raised late. **Confidence: moderate** (a qualitative finding from the corrections corpus, with named instances).

---

# What the evidence cannot settle

**Whether any of this reduces field defects.** **Zero of 76 primary tickets originate from a user.** Two originate from something actually going wrong and both happened to this repository's own agent. **74 of 76 were manufactured by looking.** Everything above measures how efficiently the campaign found its own defects. Nothing in the corpus could show a user was harmed by a missing verification step, or spared by a present one. **This is the largest single limitation on the entire document.**

**Whether the mechanisms' yields are comparable at all.** They were not deployed against a common population. Mutation ran on the modules the test-repair campaign reached; differentials ran on security-shaped tickets; prose sweeps ran on 158 files chosen by a different rule. **No mechanism was ever run against a defect set another mechanism had found**, with one exception (reading vs mutation on the same module, six times in one evening, and mutation won decisively). That exception is the strongest comparative datum in the corpus and it covers exactly one pair.

**This is a limit on *this document's* ability to rank them. It is not a criticism of the campaign.** Running each mechanism where it fit, rather than running all of them against one population, is what a verification programme is supposed to do; a design that made the mechanisms comparable would have been a worse programme and a better experiment. The same applies to the variation between review rounds — see the correction under *"The correction that reorganised this table"*. **Read every `~` and blank cell in the table as "not measured here", never as "does not work".**

**Rates, for blinded review.** "27 of 27 rounds found something blocking" is a **floor over surviving evidence, not a rate**: ticket 44's rounds 1–3, ticket 78's round 1 headline and ticket 80's rounds 1–2 headlines have no surviving files, rounds are known to have run without producing a file, and the one clean round on record has no file behind it.

**Discovery-method attribution.** The 18 / 15 / 14 split (mutation / measurement / Arnon) is `MEASURED-SOURCE` from a taxonomy over 76 primary tickets that **excludes the 29 `resolved/` subjects entirely** — i.e. every distribution is over the tickets that stayed open longest, a bias the taxonomy declares about itself. The same taxonomy's outcome census was wrong by at least 15 and was corrected the day it was written. Treat the split as indicative.

**Cost, in any currency, for most mechanisms.** No source in the corpus queried a billing or usage API. Every dollar figure is estimated; every token count but one (~161k/agent, n=12, mutation) is a reconstruction; four source files retract their own clock times; and **of fifteen priced practices only three carry a re-measurable cost.** Ten of 35 review reports carry no cost data. 97% of proposed tickets carry none — *and that is the population every scheduling decision was made from.*

**Whether a human in the loop changes any of this.** The corpus contains no controlled comparison. What it does establish is a division: findings that are properties of the *defect* transfer to any mode (planning catches claims and not compositions; silent behaviour defects need a mechanical differential; instance-fixing and re-litigation are pathologies of any team); findings that are properties of *who was orchestrating* do not (the 40% rework rate, the coordinator-error share, the 58.1h availability latency). **The 6–12 month human-in-the-loop counterfactual is Arnon's estimate, not a measurement.**

**How many rounds `Path.absolute()` actually escaped.** Six is the ticket author's contemporaneous figure and **only 2 of those 6 rounds survive as files**, so it is not independently checkable. The *pattern* — three, now four, escapes from one enumeration — is stated independently three times and is solid.

**Whether the two-phase formal-artifact result generalises.** n=1 artifact, 2 rounds. See §11.

**One much-quoted row is unsourced and should not be repeated as measured.** Ticket 98 chunk 2's *"corpus reported zero decision changes because none of its 6,401 cases contained the three shapes"* appears in `01-...md` and `intermediate/practices-with-evidence.md`; the verification pass flagged its only citation as a sibling summary, and an independent search for this document did not find the primary either. It is a plausible and probably-true claim with no measurement behind it — which is precisely the failure shape this corpus keeps finding.

**Long-term maintenance cost.** Task-scoped records cannot see it, and nothing here should be read as trying.

---

# Corrections this document makes to the rest of DURABLE

Five, all found by going to a primary rather than to a sibling summary. Each is stated here so the sibling can be fixed rather than quietly diverging.

1. **`08-...md:90` — *"This campaign's own review rounds were competent and still passed over three silent security defects."* Wrong.** All three appear as blocking findings inside review rounds (79 r1 B1, 78 r2 B1, 18 r2 B1), each found by the reviewer running a differential. `06:475` and `02:53` say so. The "missed" sentence occurs exactly once in the corpus.
2. **`.claude/rules/evidence-before-fixing.md` — *"A real bug, correctly fixed, that had never once fired."*** Faithful to the 26,530-command null and omits that the same report says the config *"can only be widened by the change and cannot show the direction the ticket is about. **So I synthesized it.**"* The null was structurally guaranteed; the finding came from a purpose-built differential (0/562 → 320/475/555/555).
3. **`05-campaign-statistics.md` — ticket 44's surviving round trajectory is 3 → 4 → 1, not 1 → 4 → 1.** Round 4's metrics line reads `Blocking: 3.`; the "1" was read off a sub-category.
4. **`intermediate/VERIFIED-practices-with-evidence.md` — the *"floor, not a ceiling"* hedge is attached to the wrong fifty.** It belongs to ticket 31's ~50 zero-detection *mechanisms*, not to the methodology note's ~50 *tickets*.
5. **The mutation-yield dispute is now partly settled and can stop being reported as irreconcilable.** The `resolved/` tier was classified for this document: **18 of 76 primary tickets, ~38 of 105 distinct subjects.** Neither 18 nor 50.

**Note the shape of four of these five: a claim that is true about the thing it measured and misleading about the thing the reader will conclude.** That is the corpus's own `TRUE BUT MISLEADING` category, and it is the verdict that recurs most in its verification passes.

## One last thing, about this document

It is a synthesis over summaries, and the corpus's own verification pass found that **the recurring failure here is not an obviously wrong claim — it is a plausible claim with a real citation attached, which nobody re-checks.** Four adversarial passes over the sibling documents checked roughly 460 claims and refuted or misattributed about 24; one false claim survived adversarial verification because the verifier **inherited the original's search scope**. Where a figure above is quoted from a `DURABLE/*.md` sibling rather than from a primary, it is because the primary states it and the sibling reproduces it; where the two disagree, both are shown. **The rule that generalises, and the one to apply to this file: for any claim resting on what a note SAYS, check what the repo DID.**
