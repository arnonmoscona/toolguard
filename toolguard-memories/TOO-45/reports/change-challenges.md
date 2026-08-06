---
title: TOO-45 change challenges -- candidate architecture-probe changes
tags:
- task-memory
- TOO-45
permalink: toolguard/too-45/reports/change-challenges
---

# Change challenges: candidate probes for measuring how toolguard absorbs change

## What this is, and how it was produced

Eight candidate "change challenges": plausible future requirements, designed as *instruments* for measuring architectural quality rather than as a roadmap. Nobody has these lined up. Each is chosen so that a well-structured and a badly-structured version of this codebase would diverge sharply in effort, risk, and localisation -- and each stresses a different architectural axis, because eight variants of one axis would measure one thing eight times.

**Blindness constraint honoured.** Nothing under `toolguard-memories/` was read (this file is the sole exception, as a write target), and no recent commit history was inspected. The analysis is grounded only in `README.md`, `technical-notes.md`, `docs/*`, `CLAUDE.md`, `.pyscn.toml`, `pyproject.toml`, `test/verdict_corpus/README.md`, and the source under `toolguard/` and `test/`. Where a TOO-45 ticket identifier appears in a code comment I read, it is treated purely as an in-code landmark, not as knowledge of what that ticket was for.

**One framing rule applied throughout, per the commissioning refinement:** where a challenge implies persistent or external state, *the store itself is stipulated as solved*. Assume a repository interface, assume transactional guarantees, assume durability and corruption are somebody else's focused problem. None of that tells you anything about this architecture. What tells you something is the code *around* the store: where the state is read, how it enters a decision path that currently has no such input, how it composes with policy that already arrives from three different resolution rules, what has to become substitutable so the change is testable, and which seams the requirement forces open that do not exist today.

---

## Ranked shortlist

Ranked by **discriminating power**: how sharply I expect a well-structured and a badly-structured version of this codebase to diverge on each. Effort is *not* the ranking -- a change that is uniformly expensive discriminates nothing.

| # | Rank | Challenge | Primary axis | Expected divergence |
|---|------|-----------|--------------|---------------------|
| CC-1 | 1 | Per-session budgets and rate limits | Decision-relevant state that outlives the process; a session identifier becoming load-bearing for policy | Very high |
| CC-4 | 2 | Govern a tool whose target is structured arguments, not a command string or a path | Domain-model extensibility; dispatch fan-out | Very high |
| CC-5 | 3 | Run as a resident process serving many events | Process-lifetime inversion; latency; hidden per-call I/O and globals | Very high |
| CC-3 | 4 | Rewrite the tool input instead of only judging it | Output protocol; whether the parsing IR is lossless and reassemblable | High |
| CC-2 | 5 | Rules that expire, or that only apply during a window | Time-dependence and clock seams; identity of a rule vs its pattern string | High |
| CC-8 | 6 | Explain a decision: full derivation and counterfactual | Introspection -- does resolution produce a *result* or a *derivation*? | Medium-high |
| CC-6 | 7 | Org-managed policy fetched from a remote source | External I/O; failure semantics; is "a config source" an abstraction? | Medium |
| CC-7 | 8 | Safe on a shared multi-user host | Multi-tenancy; state-location policy; security boundary | Medium (highest as a *security* probe) |

### What I would run first, and why

**Run CC-1 and CC-4 first, as a pair.** They are the two highest-signal probes and they fail in opposite directions, which makes the pair more informative than either alone. CC-1 attacks the decision path from *underneath* -- it introduces an input that is neither config nor tool event, into a pipeline whose purity is an explicitly documented, test-enforced invariant (`toolguard/tools/decision.py::decide` is described in `test/verdict_corpus/README.md` as "the single side-effect-free entry point that backs both the live hook and `--eval`"). CC-4 attacks it from *above* -- it adds a third shape of governed thing to a pipeline that is hardcoded, in at least five places, to exactly two shapes. If the codebase absorbs both cleanly, the core is genuinely well-factored. If it absorbs one and not the other, you have learned precisely which end is rigid.

**Run CC-2 immediately after CC-1, as a controlled contrast.** They share the time axis but differ on everything else: CC-2 is time-dependent with *no* cross-process state, CC-1 is stateful with *incidental* time-dependence. The delta between them isolates how much of the cost is "the codebase cannot express time" versus "the codebase cannot express state". Running only one leaves that confounded. This is the single most valuable experimental-design point in the set.

**Run CC-3 third if you want a surprise.** It is the one where I have the least confidence in my own prediction, which makes it the highest-information run. See its "risk that this does not discriminate" note.

**Do not start with CC-7.** Its findings are real and some are security-relevant, but a disproportionate share of the work is replacing hardcoded paths, which is a 3x-to-5x difference between good and bad structure rather than the 20x the others should produce.

### Candidates I considered and rejected as uninformative

Knowing which probes are uninformative matters as much as knowing which are not. These would cost real time and teach almost nothing:

- **Add a new `no_match_fallback` value.** The resolution ladder in `permission_resolution._resolve_unclamped` is an if-chain over a normalised string, and `Configuration.resolved_no_match_fallback` already handles alias normalisation for two prior additions. Adding a branch is cheap in any structure.
- **Govern one more command tool** (another MCP terminal). Set membership in `hook.COMMAND_TOOLS` plus a config list entry. Near-zero discrimination.
- **Add a fifth log stream.** `error_log._log_entry(level, stream, ...)` is already parameterised by stream name. It is a one-line addition by construction.
- **Turn on the JSONLines log format.** `docs/architecture.md` states outright that the renderer exists, is tested, and lacks only a selector. Confirmed in `log_writer.py`. This measures whether someone can add an environment variable.
- **Anything measured by renaming.** Explicitly excluded by the brief and correctly so -- test breakage under a rename measures name coupling, not the work.
- **Extend the PEG grammar for one more bash construct.** Tempting, but it measures *compliance with a mandated procedure* (`.claude/rules/bash-grammar.md` prescribes a two-phase gate) rather than whether the architecture absorbs the change. It only becomes a real probe if the requirement forces the grammar change to become *visible to rule authors* -- a new matchable sentinel in the style of `__HEREDOC_TO_<sink>__` -- because that crosses from `parser/` all the way to documentation and the audit tooling.

### One calibration item, listed honestly because I got it wrong

I intended to list **"add a new pattern-type prefix, e.g. `[semver]`"** as the archetypal non-discriminating change, on the reasoning that `patterns.py` (145 lines: a `PatternType` enum, `parse_pattern`, `match_pattern`) is a clean seam. Measurement contradicted me. The *matcher* is three edits in `patterns.py`; wiring the *prefix* correctly is roughly seven more across four modules on the decision path, because the literal prefix tuple `("[regex]", "[glob]", "[native]")` is hand-copied rather than derived from `PatternType`:

- `permissions.py` -- the extended-type bypass tuple in `match_command`; `is_universal_pattern`'s marker tuple; `_literal_prefix_specificity`'s marker tuple (three separate, differing copies)
- `resolve.py` -- `_anchor_file_pattern`'s known-prefix loop, and `_match_file_path_pattern`'s separate file-path-side dispatch
- `permission_migration.py` -- two more `startswith` tuples

Plus silent degradation in eight tooling modules that each carry their own prefix assumption (`danger`, `consolidate`, `redundancy`, `pattern_overlap`, `clarity`, `security_audit`, `decision`, `replay`).

The failure mode of missing one is *silent*: an unrecognised prefix falls through to DEFAULT `fnmatch`, which will happily match something. So I am keeping this in the battery, not as a challenge but as a **calibration control**: a change that both a naive predictor and a careful reader expect to be trivial, whose real cost measures duplicated-vocabulary debt specifically. It is cheap to run and it tells you how much to trust intuition on the others.

---

# The challenges in detail

---

## CC-1. Per-session budgets and rate limits

> "I want to cap how much damage an unattended session can do. Let me write a rule like *at most 20 `git push` calls per session*, or *no more than 5 network fetches in any 10-minute window*, or *after 3 denials of the same command, stop asking and just deny*. When a budget is exhausted, the decision changes -- the same command that was allowed an hour ago is now denied, with a reason that says why."

**Why it is plausible.** This is the direct continuation of a problem the product already names as its own. `README.md` lists "a disciplined answer to approval fatigue" as a headline advantage and commits that "future releases will keep addressing approval fatigue with the same discipline and rigor." `docs/auto-mode.md` is an entire page conceding that in unattended operation `allow_with_warning` is "a detective control for the unmatched case, not a preventive one" -- budgets are exactly the preventive control that gap is asking for. And the mechanism this product exists to replace is a permission system that re-prompts for things already granted; "remember the answer within a session" is the same shape of requirement.

**Axis stressed, and why nothing else covers it.** Decision-relevant state that outlives the process, plus the promotion of an identifier from observational to load-bearing. Every other challenge here leaves the verdict a pure function of `(configuration, event)`. This one does not. CC-2 also makes verdicts vary over time, but from a *declarative* input the config already carries; CC-1 introduces a genuinely new input channel. CC-5 also concerns process lifetime, but from the cost side, with no change to what is decided.

**Why it is hard -- the specific things, not the store.**

Stipulate the store. What remains is four distinct problems, and each of them is a seam that does not currently exist.

1. **`session_id` is read by nothing.** It appears in `hook.parse_hook_input`'s documented input example and in `session_start.py`'s payload description, and that is all -- `grep` across the package finds no other use in any decision or logging path. Scoping a budget to a session makes that field steer a verdict. Contrast `permission_mode`, which *is* read and threaded into `LogRecord`, and is documented at three separate call sites as "recorded for diagnosis only -- it never affects the verdict itself." The codebase currently has a clean, stated separation between fields that describe a call and fields that decide it. CC-1 deliberately violates it, and the interesting measurement is what that costs.

2. **There is no session concept to attach to, and three divergent approximations of one.** `session_warnings.py`, `auto_migrate.py`, and `config_divergence.py` each contain a near-verbatim copy of the same idea: a zero-byte date-stamped marker file in the log directory (`.toolguard-warned-YYYY-MM-DD` and siblings). The granularity is per *day*, not per session, so two concurrent Claude sessions share one marker. `hook.py` also carries three module-level flags -- `_validation_done`, `_divergence_check_done`, `_takeover_conflict_logged` -- whose own docstrings concede they cannot deliver what they advertise, because the process is fresh per call. So "once per session" has been wanted three times, approximated three ways, and never actually implemented. A budget requirement forces that concept to exist for real, once, and the measurement is whether the three existing approximations converge on it or a fourth is added alongside them. (Note also that `docs/config-sync.md` documents these markers as living in `/tmp/toolguard-warnings/`, which the code does not do -- a doc/code divergence worth knowing about before you measure.)

3. **The decision chokepoint's config contract is a deliberately narrow duck-typed surface.** `permission_resolution.py` documents, in its module docstring, that it needs exactly four members from whatever is passed as `config` -- `permission_levels_with_provenance`, `has_any_rules`, `resolved_no_match_fallback`, `parse_failures` -- and that the surface was deliberately *shrunk* from six. A budget check needs something none of those four provide. The clean answer widens one context object at one place. The unclean answer threads a `session_id` parameter down through `resolve_bash_permission_detailed`, into the `_decide`/`_resolve_one`/`_resolve_outer`/`_record_unit` closure family, and across the `resolve_one` callback contract into `compound.resolve_compound_permission_detailed` -- four closures and a published callback signature, for a value none of them conceptually own.

4. **Consumption is not the same event as decision, and the compound case makes that concrete.** A budget must be *charged*, and charging is a write. But `decide()` is contractually side-effect-free, `--eval` exists specifically to "probe a project's safety floor without mutating it", and a compound command produces several `UnitVerdict`s of which only some are allowed. Does `git push && git push` consume one unit or two? Does a command that is ultimately denied because a *later* sub-command failed still charge the earlier one? There is no transaction boundary around "one tool call" anywhere in the current design -- `_log_allowed_command` emits N records for N sub-commands and the hook exits. The requirement forces that boundary into existence.

**What it would likely touch.** `hook.py` (reading `session_id`, constructing the context, deciding where charging happens relative to output); a new module owning session state (the store is stipulated, its *interface* is the deliverable); `permission_resolution.py` (the four-member surface); `resolve.py` and `compound.py` (only if the threading goes badly -- if it goes well, neither should change); `tools/decision.py` (`decide`'s signature and its purity claim); `config.py` plus `rule_entry.py` (budget rules need a schema and `normalize_entry` is the single chokepoint every rule list passes through); `test/verdict_corpus/fixture_loader.py` and `tools/corpus_build.py` (the corpus must keep replaying deterministically).

**How to measure it.**

- **Corpus invariance is the primary instrument.** Run `uv run python tools/corpus_build.py --verify`. A correct additive extension changes **zero** of the roughly 5,000 existing verdicts, because no fixture configures a budget. Any hard-invariant change is a direct measurement that the feature was implemented by modifying the existing path rather than extending it. Then `--verify --strict-prose`: if reason and provenance text also survive untouched, the change did not disturb the plumbing either. This is a far better signal than any file or line count, and it already exists.
- **Signature-change count versus new-function count.** Count functions whose *existing* signature had to change to carry the new input. One (a context object widened at the chokepoint) is the good outcome; five-plus, especially if any of them are the compound closures, is shotgun surgery on a hot path.
- **Purity-invariant status, as a binary.** Does `tools/decision.decide` remain side-effect-free? If not, is the impurity confined to one named, injected collaborator, or is it ambient? This is a stated invariant with a documented owner, so the answer is unambiguous rather than a judgement call.
- **Injection points created versus reused.** Count the new monkeypatch targets the tests must invent. A design that already had a place to put a collaborator needs zero new ones. This is the cleanest available proxy for "did the seam exist."
- **Layer-map response.** `.pyscn.toml` declares an enforced order -- `foundation < config < engine < runtime < tooling < support` -- and `pyscn analyze` validates it. Count *new cross-layer edges*, and separately count any **new upward edge**, which is a violation rather than a cost. A session store read from `engine` is an upward edge into `runtime`; getting it right means the state arrives as data, not as a reachable module.

**Good outcome, structurally.** A `DecisionContext` (or equivalent) value object constructed once in `hook.main` and passed to `decide`, carrying the session identity and a stipulated budget-store handle. `permission_resolution`'s duck-typed surface grows by at most one member. Budget rules are just rules -- they flow through `normalize_entry` like everything else and get provenance for free. Charging happens at exactly one place, after the verdict and before output, expressed as a single "one tool call" boundary. The corpus passes unchanged. A test can substitute a fake store and a fake clock without patching a module global.

**Bad outcome, structurally.** `session_id` threaded as a positional parameter through `resolve_bash_permission_detailed`, `_decide`, `_resolve_one`, `_resolve_outer`, and the published `resolve_one` callback contract in `compound.py`. A module-level counter dict somewhere, which silently does nothing because the process is fresh per call -- the exact failure the three existing `hook.py` flags already document. Budget state read directly from `resolve.py`, creating an upward layer edge. Charging duplicated on the allow path and the ask path because they are different functions. Corpus goldens regenerated to make tests pass, and a fourth date-marker implementation added next to the existing three.

---

## CC-4. Govern a tool whose target is structured arguments

> "Toolguard should govern more than shell commands and file paths. I want rules over an MCP tool that takes structured arguments -- for example `mcp__github__create_pr(repo=..., base=..., draft=...)` -- so I can allow drafts against my own repos and ask for anything targeting `main` on somebody else's. I want the same hierarchy, the same hard-deny floor, the same audit trail, and the same `additionalContext`."

**Why it is plausible.** `docs/configuration.md` already invites users to declare `additional_supported_tools` for "custom MCP tools that execute commands", and the documented recognition-versus-governance distinction exists precisely because the tool vocabulary is meant to grow. Today that growth is confined to tools whose input happens to be a command string. Every real MCP server emits structured arguments, and the moment somebody wants to govern one of those, this requirement appears verbatim.

**Axis stressed, and why nothing else covers it.** Extensibility of the core domain model and the dispatch that sits above it -- what kind of *thing* toolguard can have an opinion about. CC-3 changes what the hook returns; this changes what it accepts. CC-2 and CC-6 extend the config schema and its sources but leave the target model untouched. This is the only challenge that asks whether the two-shape world is a design or an accident.

**Why it is hard.** The entire pipeline is bifurcated into exactly two target shapes, and the bifurcation is expressed as hardcoded sets rather than as a type:

- `constants.FILE_TOOLS` and `hook.COMMAND_TOOLS` -- two frozensets, in two modules, that partition the world
- `hook._resolve_event` and `hook.main` -- `if tool_name in FILE_PATH_TOOLS: ... else: ...`, twice
- `tools/decision.py` -- the same branch again, in `_decide_bash` / `_decide_file_path`
- `resolve.py` -- two parallel resolver functions, `resolve_file_path_permission_detailed` and `resolve_bash_permission_detailed`, with two parallel hard-deny checkers
- `config.allow_deny_for` and the tool-wrapper strip, which assume a pattern body is either a command pattern or a path pattern
- `log_writer.LogRecord`, whose `command_str` field is a string in both worlds

There is one genuinely good piece of news, and finding out whether it holds up under load is the point of the challenge: `permission_resolution.resolve_permission_detailed` is generic over a `decide_detailed` callback and knows nothing about targets at all. A third family *should* be a third callback. Whether it can be is the measurement.

The deeper problem is that **there is no argument model anywhere in the system, for any tool.** Confirmed by reading the parser: `IRSimpleCmd.text` is an opaque string, `LeafCommand` carries `(text, ask_floor)` and nothing else, and the only argument-awareness that exists is a handful of narrow ad-hoc string scans, each solving one local problem -- `_scan_for_inline_flag` splitting on whitespace to find `-c`, `contains_path_component` splitting args on `/`, `match_command`'s `cmd:args` colon split which is textual on the *pattern* side only. So a structured-argument tool does not extend an existing argument model; it introduces the first one. That is a much larger question than "add a third branch", and how the implementation handles it -- a genuinely new target type versus flattening the arguments into a fake command string so the existing matcher can be reused -- is the single most revealing thing this challenge produces.

**What it would likely touch.** `constants.py`, `hook.py`, `tools/decision.py`, `resolve.py`, `config.py` (pattern extraction and wrapper handling), `patterns.py` (matching a structured target is not `fnmatch`), `config_validation.py` (the known-tools list), `log_writer.py` (`LogRecord.command_str`), `docs/permission-patterns.md` and `docs/configuration.md`, and -- the tell -- the tooling layer: `tools/danger.py`, `tools/security_audit.py`, `tools/redundancy.py`, `tools/pattern_overlap.py` all carry per-tool assumptions and will silently produce wrong findings for a family they do not know about.

**How to measure it.**

- **Count the `if tool in <set>` dispatch sites that had to change.** The good design has one, in one place, replaced by a registry lookup. Count them before you start so the delta is honest.
- **Does `permission_resolution.py` change at all?** It is the declared single chokepoint and it is already target-agnostic. If it needs even one edit, the genericity was nominal.
- **Corpus invariance again**, and here it is especially sharp: the new tool family shares no fixture with any existing case, so *every* one of the ~5,000 verdicts must be untouched. Any change is a direct measurement of coupling between families.
- **Tooling-layer leakage, counted as a ratio.** Number of modules under `tools/` that must be edited for a *runtime* capability, divided by the number of runtime modules edited. A well-layered result is near zero; the ratio rising above one means the operator tooling has absorbed knowledge that belongs in the core.
- **The open/closed test, as a yes/no.** Can the third family be delivered as one new module plus one registration line, with no edit to either existing family's code path? This is binary and it is the whole question.
- **Reversibility.** Delete the new module and the registration line. Does everything still work? If not, the change was invasive regardless of how it looked in the diff.

**Good outcome, structurally.** A `TargetKind` / handler registry: each family owns its target extraction, its pattern matching, its hard-deny check, and its log rendering, behind one interface. `permission_resolution.py` is untouched. `hook.main` dispatches through the registry instead of two `if`s. The two existing families are *migrated onto* the registry rather than left as special cases beside it -- if they are not, the registry is a third special case wearing a hat.

**Bad outcome, structurally.** A third `elif` in five places. Structured arguments serialised into a synthetic command string (`create_pr repo=x base=main`) so `fnmatch` can be reused -- which will look like it works, will pass the tests written for it, and will fail the first time an argument value contains a space or a glob character. `LogRecord.command_str` carrying JSON. `tools/security_audit.py` silently scoring the new family's rules as safe because it has no heuristic for them.

---

## CC-5. Run as a resident process serving many events

> "Claude Code now supports a persistent hook: one long-lived process, many events over a pipe, for the whole session. Toolguard should support that mode -- the same verdicts, but without paying process startup, config discovery, and config parsing on every single tool call. Both modes must be supported from one codebase, and a p99 of under 10 ms per event with a six-level hierarchy and several hundred rules."

**Why it is plausible.** It is the natural next step for a hook that fires on every tool call in a high-volume agent loop, and it is a change the *host* could make unilaterally. The current design is explicitly built on the opposite assumption -- `docs/architecture.md`, `technical-notes.md`, and at least four separate code comments all reason from "toolguard is a fresh process per tool call." Requirements that invert a codebase's deepest environmental assumption are the sharpest probes available, and this is that assumption.

**Axis stressed, and why nothing else covers it.** Process lifetime and its consequences: hidden per-call work, module-level mutable state, and cost that is currently invisible because it is amortised over nothing. No other challenge here touches lifetime; CC-1 needs state to *survive* the process, which is a different requirement from the process *not ending*.

**Why it is hard.** Three findings make this much sharper than a generic performance exercise.

1. **Three module-level flags in `hook.py` flip from inert to load-bearing.** `_validation_done`, `_divergence_check_done`, and `_takeover_conflict_logged` are documented as approximating "once per session" and as being unable to deliver it in a fresh-process model. In a resident process they suddenly *do* persist -- and now they are wrong in the other direction: they would suppress validation for a second project served by the same process, and `_takeover_conflict_logged` would hide a genuine conflict. This is the rare case where a latent no-op becomes a live correctness bug purely by changing deployment, and it is exactly the kind of thing a fitness-function battery should be able to detect ahead of time.

2. **The decision path does filesystem I/O per pattern match, not just at config load.** `permissions.match_command` calls `normalize_path_in_command` -> `normalization.normalize_command` -> `normalize_path`, which invokes `Path.exists()`, `Path.is_symlink()`, and `Path.resolve()` (up to three iterations) plus `Path.home()` for every path-like token -- on every match attempt, for every pattern, at every level, for every sub-command. `patterns.match_pattern`'s GLOB branch calls `expand_tilde` -> `Path.home()` as well. This is the finding that turns a performance challenge into a correctness one: `resolve.py`'s module docstring describes itself as the "pure, side-effect-free permission resolver layer," and matching is not a pure function of `(config, command)` -- it is a function of the live filesystem. A resident process makes caching that I/O tempting, and the moment you cache it you have to answer *when a symlink change should invalidate a verdict*, which nobody currently has to answer.

3. **`log_writer` can terminate the process.** Two paths call `sys.exit(1)` -- a missing project root and a missing log directory. In a per-call model that is a bad-but-survivable failure of one decision. In a resident model it kills the permission system for the whole session, and `docs/security.md` already documents that a hook which cannot launch **fails silently**, because Claude Code treats only exit code 2 as blocking. Diagnostics terminating the enforcement path is a layering fault that the current lifetime hides.

Alongside those: `config._parse_config_file_cached` is an unbounded process-global `lru_cache` keyed on `(path, format, mtime_ns, size)`. Today it is harmless and nearly useless. In a resident process it becomes a real, unbounded, long-lived cache with a stale-`stat` window. And `Configuration.project_root` is a *property* that performs a filesystem walk on every access, with `resolve_config_path` calling it per invocation, while `permission_layers()` re-runs `takeover_mode()`'s full layer walk on every call and `has_any_rules()` calls both -- none of it memoised on the instance.

**What it would likely touch.** `hook.py` (an event loop; the globals; `sys.exit` in the request path), `config.py` (caching, invalidation, the `project_root` property, per-call recomputation), `log_writer.py` and `error_log.py` (the exit paths), `normalization.py` and `permissions.py` (the per-token filesystem I/O), `env_config.py` (`get_env_config` currently reads process environment and `.env` per call), `session_warnings.py` and its two clones.

**How to measure it.**

- **Measure, do not count.** Instrument one hook invocation and report the split: interpreter and import startup, config discovery and parse, transcript-tail parse for subagent attribution, and actual decision. That partition tells you what a resident mode could even buy, and whether the modules are separable along it. This is the measurement that should precede the implementation.
- **Count filesystem syscalls per decision** (`strace -c -f -e trace=file`, or a `Path` shim in a test). Then count them again after the change. The interesting number is not the reduction -- it is whether the reduction required touching the *matching* code or only the *loading* code. If matching had to change, the purity boundary was in the wrong place.
- **Global-state census, as a hard number.** Count module-level mutable bindings reachable from the request path. This is objective, cheap, and directly predicts whether a lifetime change is safe. It is also a fitness function worth keeping permanently, independent of whether this challenge is ever run.
- **Idempotence under repetition.** Feed the same event twice into one process and diff both the verdict and the emitted log records. Divergence localises leaked state precisely, and it does so without any implementation at all -- this probe can be run *today*, before deciding whether to run the full challenge.
- **Corpus invariance under both modes.** The end-to-end corpus already drives the real hook binary in a subprocess. A resident mode must reproduce `e2e_goldens.jsonl` exactly. That is a ready-made acceptance oracle for "same verdicts, different lifetime."

**Good outcome, structurally.** A `serve()` loop alongside `main()`, both delegating to one per-event function that takes everything it needs as parameters. Zero module-level mutable state on the request path -- the three flags become fields on an explicit session object, or are deleted once the concept they were faking exists for real. `sys.exit` gone from `log_writer` and `error_log`, replaced by a raised error the entry point owns. Caching lives in `config.py` behind an explicit invalidation policy, and matching stays a pure function because the filesystem-dependent normalisation was hoisted out of the inner loop rather than memoised inside it.

**Bad outcome, structurally.** The globals left as they are, because they "already work" -- with correctness now depending on one process serving one project. An LRU cache added to `normalize_path` to make the numbers look good, silently making verdicts depend on the filesystem state at first observation. A second entry point that copies `main()`'s twelve-step orchestration, so every subsequent change has to be made twice. `sys.exit(1)` still in the logging layer, now taking down the session.

---

## CC-3. Rewrite the tool input instead of only judging it

> "Some things should not be a flat no. If Claude runs `rm -rf build`, I want toolguard to allow it *as* `trash build`. If it runs a migration, I want `--dry-run` injected. A rule should be able to say: allow this, but with the command rewritten to *this*. The rewritten command is what actually runs, and the audit log records both what was asked for and what was executed."

**Why it is plausible.** The product already does the strictly harder half of this. `additionalContext` exists so a deny can say "you can't do this; do X instead", and `README.md` argues that reaching Claude with the alternative at the moment of denial is where the feature earns the most. Rewriting is the same intent, one step further -- do X *for* it. And the Claude Code hook protocol is the sort of thing that grows a field like this; toolguard's output is already a projection into `hookSpecificOutput`, so a new key there is the host's natural extension point.

**Axis stressed, and why nothing else covers it.** The output protocol, and -- through it -- whether the parsing pipeline is lossless. Every other challenge treats the target as read-only. This is the only one that requires reconstructing it. CC-4 changes the input shape but never has to put it back together.

**Why it is hard.** The pipeline from raw command to decision is **deliberately, thoroughly one-way**, and the losses are spread across three modules:

- `multiline.py`'s pre-pass normalises line endings, joins backslash continuations, strips comments, and collapses whitespace. None of that is recorded.
- Heredoc handling *discards the body entirely* for a non-bash sink and replaces `<<DELIM` in place with `__HEREDOC_TO_<sink>__`, with the sink label sanitised to `[A-Za-z0-9_]` (`python3.13` becomes `python3_13`). The original text is not retained.
- `LeafCommand` carries `(text, ask_floor)`. There is no source span, no offset, no back-reference to the original command. `UndecidableSegment` carries `original` -- but only for the segment it could not decompose, which is precisely the case you cannot safely rewrite anyway.
- `bash -c "..."` payloads are re-entered recursively through `multiline.extract_structured`, so a leaf can be nested arbitrarily deep in a string that itself was quoted, with no record of the quoting.
- `compound._extract_outer_command` truncates `python -c "<code>"` to the stub `python -c` for matching, and `_truncate_for_display` bounds it to 120 characters for the prompt. Both are lossy on purpose.

So rewriting a single leaf inside `a && (b | c)` requires knowing where that leaf came from in the original text -- information that is destroyed by design. And CLAUDE.md's grammar rule forbids recovering it by re-scanning with regex, which is exactly what a rushed implementation will reach for.

Beyond reassembly there are two semantic problems the requirement forces into the open. **Which decision does a rewrite belong to?** A compound where three sub-commands each rewrite has three edits to merge, but `_combine_strictest` is a strictness fold that keeps *one* winner's reason and discards the losers. And **rewriting reopens the security question the ask-floor exists to close**: if a rewritten command is what runs, is the rewritten form re-validated? If yes, you need a fixpoint or a recursion bound. If no, a rewrite rule is an authenticated bypass of every other rule -- which `docs/security.md`'s "no-blanket-allow invariant" reasoning would have something to say about.

**What it would likely touch.** `parser/command_model.py` and `parser/command_extractor.py` (source spans in the IR), `parser/multiline.py` (the pre-pass would have to record its edits, not just apply them), `compound.py` (`_combine_strictest` merging rewrites, not just folding decisions), `resolve.py`, `config_types.RuntimeVerdict`, `hook.create_hook_output`, `log_writer.LogRecord` (two targets per record), `rule_entry.py` (a `rewrite` key on the structured entry), and the docs. Possibly the `.peg` grammar -- and if so, under the mandated two-phase procedure.

**How to measure it.**

- **Round-trip fidelity as a property test, before any rewriting exists.** Take every command in the ~5,000-case corpus, decompose it, reassemble it unmodified, and compare to the input. The pass rate on that single test is the honest measure of how lossy the IR is, and it is a *cheap probe that can be run today* to decide whether this challenge is worth running at all. My prediction is a low rate; being wrong about that would be the most useful result in this whole document.
- **Where the position information came from.** If spans were added to the IR in `command_model.py`, the parsing layer absorbed the change correctly. If positions are recovered by searching the original text for the leaf's text, the change was implemented against the grain -- and `.claude/rules/bash-grammar.md` names this exact failure mode ("new logic that still belongs in the grammar, smuggled into Python").
- **End-to-end corpus response.** `test/verdict_corpus/README.md` records that a mutation at the `create_hook_output` seam was caught by *nothing* in the in-process corpus, which is why the e2e corpus exists. A new output field lives at that same seam, so the e2e corpus is the instrument, and whether the implementer knew to extend it is itself a measurement.
- **Re-validation semantics, stated or discovered.** Did the implementation decide, explicitly and in writing, whether rewritten commands are re-checked? An unstated answer here is a security hole regardless of how clean the diff looks. Judge this as present/absent, not as a score.
- **Architecture-fitness interaction.** `test/unit/test_architecture.py` and `tools/architecture_fitness.py` gate an "exactly one runtime verdict type" property. A rewrite payload may need a new type. Whether the fitness test correctly resisted coupling or wrongly obstructed a legitimate extension is a genuine meta-measurement of whether the existing fitness functions encode the right invariant.

**Risk that this does not discriminate.** Real, and worth stating plainly. If the IR turns out to be lossy in *both* a good and a bad version of this codebase -- because losslessness was a deliberate, reasonable trade rather than an oversight -- then both versions pay the same large cost and the challenge measures nothing about structure. That is why I would run the round-trip property test first: it costs an hour, and it tells you whether the full challenge is informative before you spend days on it.

**Good outcome, structurally.** Source spans added once, in `command_model.py`, where raw-tree access is already isolated by design; everything downstream carries them without knowing why. Rewriting expressed as a transformation over the IR with reassembly as its inverse, so `LeafCommand` gains provenance rather than the pipeline gaining a second path. `_combine_strictest` extended to fold rewrites with an explicit, documented merge rule. Re-validation decided deliberately, with a bound.

**Bad outcome, structurally.** `str.replace(leaf_text, new_text)` on the original command -- which will corrupt any command where the leaf text appears twice, or inside a quoted string, and will pass every test anyone thinks to write. Rewrites restricted to non-compound commands "for now", with the restriction enforced by a check in `hook.py` rather than expressed in the model. The rewritten command not re-validated, and nobody noticing.

---

## CC-2. Rules that expire, or that only apply during a window

> "Let me grant a permission temporarily. `{ match = "Bash(terraform apply:*)", expires = "2026-09-01" }` -- after that date the rule is simply not there. And business-hours rules: this deny only applies outside 09:00-18:00 on weekdays. Expired rules should be reported so I can clean them up, and I need to know today what my config will decide next week."

**Why it is plausible.** It is the natural resolution of a tension the docs already name. `docs/security.md` and the maintenance skill both treat over-broad allow rules as the central risk, and `docs/skills.md` describes a whole curation apparatus for rules that accumulate and are never removed. A temporary grant is how you say "I need this for today's task" without permanently widening the surface -- and toolguard is a *desktop* tool where a human is present to want exactly that.

**Axis stressed, and why nothing else covers it.** Time as a first-class domain concept: the same inputs must decide differently later, which forces a clock seam and breaks any golden-replay harness that assumes determinism. CC-1 also involves time but arrives at it through state; here there is no state at all -- the config is static and the *world* moves. That difference is precisely why running both is worth more than running either.

**Why it is hard.** Two findings, one obvious and one not.

The obvious one: **nothing in the decision path reads the clock.** `datetime.now()` appears only in `log_writer.py`, `error_log.py`, and `permission_migration.py` -- all output-side. There is no clock seam, so one must be created, and where it is created determines whether the feature is testable. Worse, `log_writer` deliberately calls `datetime.now()` a second time in `_build_jsonlines_entry`, and its docstring warns that tests patch `datetime.now` with a `side_effect` list and depend on the exact call sequence. So the naive seam -- patching `datetime.now` globally -- is already load-bearing for unrelated tests and will produce confusing failures.

The non-obvious one, and the reason I raised this challenge's rank after reading the code: **the join key between the matching layer and the rule-entry layer is the pattern string itself.** `permissions.match_command` is documented as returning the *raw* list element specifically because `config_types.provenance_for_pattern` looks the layer up by string identity. `entry_for_pattern` does the same. So matching happens over flattened `Tuple[str, ...]` pattern lists, and the `RuleEntry` -- which is where `expires` would live -- is recovered *afterwards*, by searching for the matched string. Expiry has to be applied *before or during* matching, which means either the matching layer starts carrying entries instead of strings, or the config layer filters expired entries out at projection time.

And that string join key is already known to be non-unique: `rule_entry.merge_entries` explicitly handles the case of two structured entries with the *same pattern* and *contradictory metadata*, keeping them separate and emitting a `MergeConflict`. Which means two rules can share a pattern string, differ in `expires`, and be indistinguishable at the point where expiry must be evaluated. That is a latent inconsistency this challenge surfaces without being designed to.

**What it would likely touch.** `rule_entry.py` (`normalize_entry` -- the single chokepoint, which already has a documented policy of warning on unknown keys, so the schema slot exists), `config_types.ToolPatternLayer` (the stripped tuples are derived properties -- filtering there is the clean point), `config.py` (`permission_layers`, `permission_levels_with_provenance`, `hard_deny`), a new clock seam, `test/verdict_corpus/fixture_loader.py` and `tools/corpus_build.py` (freezing time so goldens stay reproducible), `tools/security_audit.py` and `tools/maintenance.py` (an expired rule is a finding), plus the docs.

**How to measure it.**

- **Where does the clock enter?** One injected collaborator that the config layer receives, or `datetime.now()` called at the match site? Count call sites. This is the whole question in one number.
- **Corpus determinism, tested adversarially.** Run the corpus twice with the fake clock set a year apart. Every verdict must be identical, because no fixture uses expiry. If any changed, time leaked into a path that should not see it. This is a stronger test than "the corpus passes."
- **Filtering altitude.** Is expiry applied where entries still exist (`ToolPatternLayer`'s derived properties), or after matching, by re-looking-up the entry from the matched string? The latter is a correctness bug, not just a style one, because an expired rule that matched has already suppressed the rules behind it in the deny-first ordering.
- **Hard-deny symmetry, as a yes/no.** Does `[hard_deny]` honour expiry too, and was that decided deliberately? `hard_deny_entries` is a separate pooled path from `permission_layers`, so a change applied to one and not the other is the predictable failure. `_extract_tool_entries` is the shared worker both go through -- whether the implementation found it is the measurement.
- **Tooling awareness.** Does `toolguard-audit` report expired rules? A time-aware config that only the runtime knows about is half a feature, and the gap indicates the concept was added to the engine rather than to the model.

**Good outcome, structurally.** `expires` is just another key `normalize_entry` recognises. Filtering happens once, in `ToolPatternLayer`'s derived properties, so *every* consumer -- Bash, file paths, hard-deny, and the audit tooling -- gets it without knowing it exists. The clock arrives as an explicit parameter on `load_configuration`, defaulting to real time. The corpus is unchanged and deterministic under a shifted clock.

**Bad outcome, structurally.** `datetime.now()` called inside `match_command`. Expiry checked after matching, by re-deriving the entry from the matched pattern string -- which is both slower and wrong. `[hard_deny]` silently not honouring expiry because it is a different code path. Corpus goldens becoming date-dependent and being regenerated whenever they fail.

---

## CC-8. Explain a decision: full derivation and counterfactual

> "When toolguard denies something, I want the whole story, not the winner. Which levels were consulted, which patterns matched at each, which one won and why, which rules were shadowed by it, and -- the useful part -- the smallest change to my config that would flip the verdict. Available as a command against any hypothetical command, not just after the fact."

**Why it is plausible.** The product is already reaching for this and getting there piecemeal. `toolguard --eval` exists to preview verdicts. `toolguard.testing.sandbox` exists to answer "what would this config decide?". `docs/skills.md` describes a maintenance skill whose whole job is reasoning about which rules are redundant or shadowed. And conflict logging already answers *one* narrowly-scoped counterfactual question -- "did a more-specific allow override a less-specific deny?" -- which is a strong signal that the general question is the real requirement and has been answered once, specially.

**Axis stressed, and why nothing else covers it.** Introspection: does resolution produce a *result* or a *derivation*? This is the observability axis, but deliberately not the logging-plumbing version of it -- adding a log stream or a format is a known non-discriminator (see the rejected list). No other challenge asks whether the computation can describe itself.

**Why it is hard.** Resolution is a fold that discards its alternatives, in three separate places:

- `_resolve_unclamped` iterates levels most-specific-first and `return`s on the first match. Every less-specific level's outcome is never computed.
- `_detect_override` is the tell: to answer one narrow question about the levels it skipped, it re-runs `decide_detailed` over them in a *second, bespoke* pass. That function is a hand-built partial answer to exactly the question this challenge generalises. Its existence is evidence the shape is wrong; its narrowness is evidence nobody has yet paid to fix it.
- `_combine_strictest` folds sub-command decisions to one winner, and `_deciding_sub_match` then has to *re-derive* which sub-command decided, using a documented and quite subtle set of rules about genuine matches versus escape hatches. A derivation would make that re-derivation unnecessary -- and the fact that a 90-line docstring exists to explain the re-derivation is itself a measurement of what the missing structure costs.

The counterfactual half is harder still and is what separates this from "return more fields": *what is the smallest config change that flips this verdict?* That requires reasoning over the rule set rather than evaluating it -- inverting more-specific-wins, deny-first, the hard-deny pool, two independent floors, and both fallbacks. There is no place in the current design where such reasoning could live: `permission_resolution.py` is deliberately a thin decision engine, and the tooling layer has the analysis machinery (`pattern_overlap.py`, `redundancy.py`, `clarity.py`) but sits *above* runtime in the layer order and cannot be reached from it.

**What it would likely touch.** `permission_resolution.py` (the fold), `resolve.py` and `compound.py` (per-unit derivations), `config_types.py` (a trace type -- which will interact with the architecture-fitness predicate that gates the number of verdict types), `hook.py` (a new CLI mode alongside `--eval`), and `tools/` for the counterfactual analysis, with the layer boundary as the interesting question.

**How to measure it.**

- **Cost of the trace when nobody asked for it.** Is the derivation always built and usually discarded, or built on demand? Measure the hot-path cost of a normal verdict before and after. A design that pays for introspection on every tool call has put the seam in the wrong place.
- **Did `_detect_override` disappear?** The clean outcome subsumes it -- conflict detection becomes a query over the derivation instead of a second bespoke pass. If it survives alongside a new trace mechanism, there are now two implementations of "what did the other levels say", and the challenge produced duplication rather than structure. This is a crisp yes/no.
- **Did `_deciding_sub_match` shrink?** Same logic. A derivation that records which unit decided makes the re-derivation unnecessary. Measure the docstring, honestly -- it is currently load-bearing documentation for logic that should not need explaining.
- **Where did the counterfactual land, relative to the layer map?** Runtime reaching up into tooling is a layer violation `pyscn analyze` will report. The good answer moves the shared analysis down, not the caller up.
- **Corpus invariance.** Adding introspection must change zero verdicts. If `--verify --strict-prose` shows reason text moving, the fold was rewritten rather than instrumented.

**Good outcome, structurally.** Resolution optionally emits a `Derivation` -- an ordered record of what each level said -- and the existing verdict becomes a projection of it, the same way `create_hook_output` is already documented as "a projection of the verdict, not the whole of it." `_detect_override` and `_deciding_sub_match` become queries over that record and shrink to near nothing. The counterfactual lives in a layer both the CLI and the tooling can reach.

**Bad outcome, structurally.** A third bespoke re-run pass beside `_detect_override`, answering a third narrow question. The trace built unconditionally and thrown away on the hot path. The counterfactual implemented in `tools/` by re-loading the config and calling `decide()` repeatedly with mutated copies -- which works, is slow, and will silently disagree with the engine the first time the two paths diverge.

---

## CC-6. Org-managed policy fetched from a remote source

> "My team's baseline deny rules should live in one place the whole team pulls from, not copy-pasted into everyone's `~/.claude`. Point toolguard at a URL, have it merge those rules in as a level nobody can weaken locally, verify they came from us, and behave sensibly when the network is down or the payload is garbage."

**Why it is plausible.** The hierarchy already reaches for this and stops just short. `docs/configuration.md` documents a split rules directory whose stated purpose is letting "a large, self-contained concern (e.g. ~60 rules for the `gh` CLI) live in its own file", and ships `docs/gh-cli-rules-example.toml` as a shareable artifact. `[hard_deny]` is documented as "typically declared at the user level so no project can weaken them" -- an org baseline is that idea one tier up. And `docs/configuration.md` already discusses the supply-chain risk of auto-updating a permission authority you do not control, so the trust question is live in the product's own documentation.

**Axis stressed, and why nothing else covers it.** External I/O and its failure modes, plus the question of whether "a configuration source" is an abstraction or a filesystem path. No other challenge introduces an input that can be *slow*, *absent*, *stale*, or *hostile*. CC-4 extends what is governed; this extends where policy comes from.

**Why it is hard.** The store is stipulated -- assume a cache file, assume `urllib` and `hmac`, both stdlib, so **there is no stdlib-only conflict here** (see the constraints note below). What remains:

1. **`Provenance` is filesystem-shaped.** It carries `(level, source_type, file_format, path, specificity)` and `describe_brief()` renders it into resolution reasons, four log streams, and the audit tooling's findings. A remote source has no path. Either `path` becomes a general locator or every renderer learns a second case. The good news, and the thing worth measuring: `ConfigLayer(provenance, content)` holds `content` as a plain mapping, so the layer model is *already* source-agnostic in shape -- the coupling is in `Provenance` and in discovery, not in the layer itself.

2. **`Configuration.parse_failures` is a cross-cutting safety interlock, and a remote source must decide its relationship to it.** A non-empty `parse_failures` clamps *every* decision to `ask`, via a function whose docstring declares the clamp unconditional and warns that no future setting may be threaded in to relax it. So: does a failed *fetch* count as a parse failure? If yes, a network blip clamps the whole machine to `ask` -- correct-by-the-letter and probably unusable. If no, you have created the first config source whose failure does not fail safe, in a system whose entire documented safety argument is that broken config fails closed. There is no third option that does not require thinking, and *whether the implementation noticed the question at all* is the measurement.

3. **Freshness is policy, not mechanism.** How stale may the cache be before it stops being authoritative? Fetching on the hot path is impossible -- the process is per-tool-call and the budget is milliseconds. So the fetch must move to a separate lifecycle (`toolguard-session-start` already exists as a second entry point, and `update_check.py` already models a throttled background check with a stamp file), and the decision path reads only the cache. That split is the architecturally interesting part, and it is entirely about where responsibilities sit, not about how bytes are stored.

4. **Trust.** `docs/security.md` already documents that the hook can be silently shadowed and that a cloned project's config can inject text into Claude's context. Remote rules extend both. Signature verification with `hmac` is stdlib and mechanical; *where the trust decision lives* is the design question -- specifically, whether an unverified payload is ignored, or clamps to `ask`, or is a hard error.

**What it would likely touch.** `config.py` (`_discover_levels`, `_LEVEL_CANDIDATES`, `_rules_dirs`, `load_configuration`), `config_types.Provenance` and every `describe_brief()` consumer, a new fetch/cache module, `session_start.py` (refresh lifecycle), `tools/security_audit.py` and `tools/hierarchy.py` (a level they have never seen), `docs/configuration.md` and `docs/security.md`.

**How to measure it.**

- **Count the places that assume a source is a file.** Do this *before* implementing -- it is a static prediction the implementation then confirms or refutes, which is worth more than measuring after the fact.
- **Was the discovery step separated from the loading step?** If a remote source can be added by supplying a different list of sources to `load_configuration`, discovery and loading were properly separate. If `load_configuration` itself grew network awareness, they were not.
- **Failure-mode matrix, as a table the implementer must fill in.** Network down; slow response; malformed payload; valid payload with a bad signature; cache present but stale; cache absent on first run. For each: what verdict does a governed tool call get? An implementation that cannot answer all six has not designed the feature, whatever the diff looks like. Score presence of an *explicit, documented* answer, not the answer itself.
- **Hot-path I/O, verified.** Assert that no socket is opened during a decision. Easy to test, and it is the one property that must hold absolutely given the process model.
- **Corpus invariance**, as always -- no fixture configures a remote source, so nothing may change.

**Good outcome, structurally.** A source becomes an interface -- something that yields `(provenance, content)` -- with the filesystem as one implementation and the cached remote as another. `Provenance.path` generalises to a locator, and `describe_brief()` is the only renderer that had to change. Fetching lives in `session_start` or a dedicated entry point; the hook only ever reads cache. The `parse_failures` question is answered in writing.

**Bad outcome, structurally.** `urllib` called from inside `load_configuration`, with a timeout, on the tool-call path. A parallel `remote_layers` list beside `layers`, so every method that iterates layers needs a second loop. `Provenance.path` set to the URL string, which then flows into log rendering and audit findings that assume a filesystem path. Fetch failure silently ignored, quietly disabling the org baseline -- the exact failure mode the feature exists to prevent.

**Constraint note.** No stdlib conflict: `urllib.request`, `hmac`, `hashlib`, `json`, and `tomllib` are all standard library. The constraint *would* be violated by a background refresh daemon, a retry library, or a real HTTP client -- so the stdlib-only version is: `urllib` with a hard timeout, called only from a non-hot-path entry point, writing a cache file that the hook reads with ordinary filesystem I/O.

---

## CC-7. Safe on a shared multi-user host

> "We want toolguard on a shared build box and in CI, where several people's sessions run at once under different accounts, and one user's session must not be able to read, corrupt, or silently disable another's. Also: one Claude session working across several git worktrees of the same repo should get each worktree's rules, not whichever one it happened to start in."

**Why it is plausible.** Adoption pressure. The moment a team uses toolguard in CI or on a shared runner, this becomes a prerequisite rather than a nice-to-have -- and `docs/security.md` is already a substantial document whose posture is that toolguard is a security control, which makes "safe under multi-tenancy" a claim the product will eventually be asked to make.

**Axis stressed, and why nothing else covers it.** Multi-tenancy and the security boundary: does a "where does toolguard put its state, and who can reach it" policy exist as a concept, or is it scattered? This is the only challenge whose failure mode is an *attack* rather than a bug.

**Why it is hard.** State locations are decided independently in at least six places, by six different rules:

- `env_config.get_env_config` -- `TOOLGUARD_LOG_DIR`, else `<project_root>/logs`
- `session_warnings.py` -- `<log_dir>/.toolguard-warned-YYYY-MM-DD`
- `auto_migrate.py` and `config_divergence.py` -- the same scheme, copy-pasted, different prefixes
- `log_writer.log_discovery` -- `<log_dir>/toolguard-discovery.log`, keyed by project root, never rotated, read by seeking 64 KiB from the end
- `error_log.log_crash` -- `~/.toolguard/errors/`, deliberately independent of resolved config so it survives a config failure
- `tools/installer.py` and `tools/decision_ledger.py` -- `~/.toolguard/{backups,stage,traces}`, `~/.toolguard/decisions.json`, `<project>/.claude/toolguard_decisions.json`

Three concrete consequences a multi-tenancy requirement forces into the open:

1. **Shared-namespace markers are a denial-of-enforcement vector.** A marker file whose presence suppresses a warning, in a directory another user can write, means another user can pre-create it. Today `log_dir` is usually project-scoped, so this is mostly latent -- but `TOOLGUARD_LOG_DIR` is documented and supported, and the moment two users share one, they share markers, a discovery log, and a resolution log. The 64 KiB tail read on the discovery log is already documented as degrading when other projects' records push an entry out of the window; under multi-tenancy that degradation becomes routine.

2. **Discovery walks upward to `$HOME` and always includes `~/.claude`.** On a shared host with a shared parent directory, one user's ancestor `.claude/` becomes another's config level. `hierarchical_configuration` can limit that -- but it is read *only* from the project level, which is itself in the shared tree. `CLAUDE_SETTINGS_PATH` is already documented in `hook._warn_if_settings_path_override` as a footgun that "silently lets one project's config govern the entire machine."

3. **Verdicts depend on live filesystem state.** Because `normalize_path` calls `Path.exists()`, `is_symlink()`, and `resolve()` during matching (see CC-5), a path pattern's match result depends on what is on disk *at match time*. On a shared host that is a check-to-use gap: another user creating or repointing a symlink between two invocations changes a verdict. This is the finding that lifts this challenge from hygiene to security, and it is not visible from the docs -- only from reading `normalization.py`.

**What it would likely touch.** `env_config.py`, `session_warnings.py` plus its two clones, `log_writer.py`, `error_log.py`, `config.py` (discovery boundaries), `tools/installer.py`, `docs/security.md` and `docs/config-sync.md` (which currently documents a `/tmp` marker location the code does not use).

**How to measure it.**

- **Count the modules that independently decide a state location.** Six today. One after a good change. This is the cleanest number in the whole document and it is countable before starting.
- **Run the suite as two users against one shared `TOOLGUARD_LOG_DIR` and diff.** Cross-contamination shows up as verdict or log divergence, and it is a real, runnable test.
- **Did the three date-marker clones converge?** Same yes/no as in CC-1, from a different direction -- which is exactly why it is worth asking twice. If CC-1 and CC-7 both leave three copies, that duplication is structural rather than incidental.
- **Is the check-to-use gap acknowledged?** Present or absent, in writing. Fixing it may be out of scope; *not noticing it* is the finding.
- **Docs-versus-code drift, counted.** The `/tmp/toolguard-warnings/` discrepancy is already there. Count how many more the change surfaces -- documentation drift around state locations is a decent proxy for the concept being scattered.

**Good outcome, structurally.** One module owns state locations and answers "where does X for tenant Y live" for every artifact. Marker files carry an ownership check or move somewhere unshareable. Discovery has an explicit trust boundary rather than "walk up until `$HOME`". The check-to-use gap is documented even if not closed.

**Bad outcome, structurally.** `os.getuid()` sprinkled into six filename computations. The discovery log made per-user by adding a suffix, leaving the never-rotated, tail-read design intact. The symlink gap unnoticed. A seventh state location added by the fix.

---

## Cross-cutting notes on measurement

### Instruments this repository already has

Unusually for a codebase of this size, several objective instruments are already in place. Use them rather than inventing proxies:

1. **The verdict corpus** (`test/verdict_corpus/`, ~5,000 in-process cases plus ~30 end-to-end) is the single best instrument available. Its two-tier design -- `verdict` as a hard invariant that is never regenerated to make a test pass, versus `reason`/`provenance`/`matched_rule` as tracked-but-not-frozen -- distinguishes exactly the thing that matters: *did behaviour change* versus *did the plumbing move*. For every challenge here, "the corpus passes unchanged" is a precise, cheap statement that the change was additive. Its own README also warns that goldens pin current behaviour including current bugs, so a corpus change is a question, not automatically a failure.

2. **The end-to-end corpus catches what `decide()` is blind to.** Its README records that seeding a mutation at the `create_hook_output` seam was caught by nothing in the in-process corpus. Any challenge that changes the hook's *output* -- CC-3 above all -- must be measured there, and whether the implementer knew that is itself a signal.

3. **The layer map in `.pyscn.toml`** declares an enforced order and `pyscn analyze` validates it. Count new cross-layer edges as a cost and any new *upward* edge as a violation. This turns "is the change well-placed?" from a judgement into a check. The map also warns that an unlisted module is silently unmapped -- so a new module that nobody adds to the map degrades the instrument quietly, which is worth watching for in every challenge.

4. **Existing architecture-fitness tests** (`test/unit/test_architecture.py`, `tools/architecture_fitness.py --predicates`) already gate structural properties such as the number of runtime verdict types. Several challenges will collide with them. Treat each collision as a meta-measurement: did the fitness function correctly resist coupling, or wrongly obstruct a legitimate extension? Both answers are valuable, and the second is how a fitness battery is improved.

### Measures to prefer, and measures to distrust

**Distrust:** files changed, lines changed, tests broken. Files and lines reward small edits in the wrong place. Tests broken by a rename measures name coupling, which the brief correctly excludes; tests broken by a *behaviour* change is a different measurement and should be reported separately from tests broken by a *signature* change.

**Prefer:**

- **Corpus deltas**, split into hard and tracked. The most informative single number available here.
- **Signature changes to existing functions versus new functions added.** The ratio distinguishes "widened one seam" from "threaded a parameter."
- **Injection points created versus reused** -- the sharpest available proxy for whether a seam existed.
- **New cross-layer edges, and new upward edges**, from the enforced layer map.
- **Tooling-layer leakage ratio** -- modules under `tools/` edited per runtime module edited. A *runtime* feature that forces edits under `tools/` has found knowledge in the wrong place.
- **Reversibility**: can the change be removed by deleting one module and one registration? Binary, and it captures open/closed better than any diff statistic.
- **Backtracking count**: how many times an already-"finished" module had to be revisited. A process measure, but it correlates with hidden coupling better than any static one, and it is free to collect if you are watching the work.
- **Predictions recorded before implementation, then scored.** For each challenge, write down which modules you expect to change *before* starting. The prediction error is itself a measurement of how legible the architecture is -- and, per the `[semver]` calibration item above, a reminder that careful reading beats intuition more often than is comfortable.

### On the stdlib-only constraint

None of the eight challenges requires breaking it. CC-1's store is `sqlite3` or a file, both standard library. CC-6's fetch is `urllib` plus `hmac`. CC-5's resident mode needs no dependency at all. The constraint *would* be broken by: a real HTTP client, a retry or scheduling library, a background daemon supervisor, or any database driver. Where a challenge tempts you toward one of those, the stdlib version is stated inline above. The constraint is worth preserving as a challenge *input* precisely because it forces the design question ("where does this responsibility live?") to be answered structurally rather than by importing something that answers it for you.