---
title: TOO-45 micro-requirements (blind author)
type: note
permalink: toolguard/too-45/reports/micro-requirements-blind
tags:
- task-memory
- TOO-45
- report
---

# TOO-45 micro-requirements (blind author)

## What I read, and what I did not

**Read, in full:** `README.md`, `AGENTS.md`, `llms.txt`, and every file under `docs/` that bears on behaviour -- `configuration.md`, `permission-patterns.md`, `architecture.md`, `auto-mode.md`, `security.md`, `skills.md`, `config-sync.md`, `takeover-mode.md`, `agent-guides.md`, `quickstart.md`, `agent-map.md`. I read the first ~40 lines of `docs/gh-cli-rules-example.toml` (the only `*.example.toml`-class file that exists in the repo) to see the shape of a real user-authored rule file. `CLAUDE.md` was injected into my context by the harness before I received the task; I did not open it deliberately and did not use it as a behaviour source except where noted in the documentation-gaps section.

**Did NOT read, open, grep, glob, list contents of, or otherwise inspect:** anything under `toolguard/` (the package source), anything under `test/`, anything under `toolguard-memories/` including the sibling reports that already exist in this very directory, `technical-notes.md` (not on the permitted list, even though it is documentation), `docs/install.md` and `docs/uninstall.md` (permitted, but not needed -- install/uninstall runbooks are outside the behaviour surface these requirements target), and any file whose name mentions TOO-45. I ran `ls` on the repository root and on `docs/` to find which permitted files exist; I did not open any file that listing revealed to be out of bounds.

Everything below is written from the product's *described* behaviour. Where the documentation did not settle a question, I say so in the last section rather than guessing at an implementation.

---

## The twelve micro-requirements

### MR-01 -- Record which pattern dialect decided a call

**Requirement.** Every resolution-log entry that names a matched or violated rule must also state which pattern dialect made that match: `default`, `regex`, `glob`, or `native`. This appears as its own labelled field in the daily resolution log, alongside the existing matched-rule and provenance information. A reader diagnosing "why did this match?" should not have to re-derive the dialect by eyeballing the rule text for a `[regex]` prefix.

**Observable acceptance.** Run a command that a `Bash([regex]...)` rule allows, and a second that a plain `Bash(git status:*)` rule allows. Both entries in `logs/toolguard-YYYY-MM-DD.md` carry a dialect field, reading `regex` and `default` respectively. Do the same for a `Write(...)` path decision and confirm the field is present there too. Entries where no single rule decided (a fallback, a no-rules-at-all `ask`) omit the field rather than printing an empty one.

**Predicted irreducible footprint: 2 places.** (1) Wherever a pattern match is turned into a decision result, that result must start carrying the dialect it matched on -- the dialect is known at match time and thrown away today. (2) Wherever a resolution entry is rendered into the daily log. Nothing else genuinely has to change.

**Why it might discriminate.** If a match already produces a structured result object that carries the rule text and its provenance, adding a third attribute to that object is a one-line change and the renderer is a second. If instead the matched rule is passed around as a bare string -- and especially if the compound-command path re-encodes provenance *into* that string (the docs say compound sub-entries fold provenance into the matched-rule text in a bracketed format), and the file-path path builds its own string separately -- then the same information has to be threaded through three or four parallel paths, and a fourth for the retained JSONLines renderer. The cost here is a direct measure of whether "a decision" is one type in this codebase or several ad-hoc string conventions.

---

### MR-02 -- Attribute an unoverridable denial to the file that declared it

**Requirement.** When a call is refused because it matched a `[hard_deny]` rule, the resolution-log entry must name the configuration level and file that declared the matching rule, in the same provenance field ordinary decisions already use. Today that field is documented as absent for hard-deny matches because hard-deny rules are pooled across all hierarchy levels. A user who is blocked by a rule they did not write needs to know which file to open.

**Observable acceptance.** Declare a `[hard_deny] deny` entry in the user-level `toolguard_hook.toml`, run a matching command, and confirm the refusal entry in the daily log carries a provenance field naming that user-level file. Declare a second hard-deny rule in a project-level file, trigger it, and confirm the entry names the project file instead. The provenance names exactly the file whose rule matched, not the whole pooled set.

**Predicted irreducible footprint: 2 places.** (1) Wherever hard-deny rules from every level are pooled into one set -- each pooled rule has to keep the identity of the file it came from instead of being flattened into an anonymous pattern list. (2) Wherever a hard-deny match is converted into the refusal decision, so the surviving origin is attached. The log renderer should need no change at all, since it already prints this field when a decision carries one.

**Why it might discriminate.** This is a pure "does the data model preserve origin?" probe. A codebase where a configuration rule is a value that knows where it came from pays for this twice, both trivially. A codebase where pooling means "concatenate the strings" has to reintroduce origin tracking through the pooling step, and may discover that the hard-deny check runs before the layer that knows about levels at all -- in which case the change stops being small and starts being a re-plumb. It also tests whether hard-deny is one code path or two (command tools and file-path tools both consult it, per the documented hook flow).

---

### MR-03 -- Say when injected guidance was cut to fit the budget

**Requirement.** The text a rule injects into Claude's context is capped at 500 words, with whole paragraphs dropped or a lone over-long paragraph truncated. When either of those happens, the resolution-log entry for that decision must say so explicitly -- a short marker distinguishing "the text was delivered whole" from "the budget dropped or truncated part of it". The log already records a 40-word preview and the full word count; this adds the one fact those two cannot convey.

**Observable acceptance.** Write a rule whose `additionalContext` is comfortably under 500 words, trigger it, and confirm the log entry shows no truncation marker. Then write a compound-triggering set of rules whose combined context exceeds 500 words, trigger it, and confirm the entry is marked as budget-affected. The text actually injected is unchanged in both cases -- only the log gains the marker.

**Predicted irreducible footprint: 2 places.** (1) Wherever the 500-word budget is applied -- it must report whether it dropped or truncated anything, instead of only returning the surviving text. (2) Wherever the log preview line for injected context is written. If the budget is applied at more than one point (say, once for compound accumulation and once for a single leaf), that count rises, which is itself the finding.

**Why it might discriminate.** The documentation describes the budget as applying "uniformly, to every decision and every governed tool ... at the point it is about to be injected", which reads like a single chokepoint. If that is true in the code, this change is small. If the accumulation rule for compound commands, the single-leaf case, and the file-path case each apply their own capping, the requirement forces the implementer either to edit three sites or to first unify them -- and the honest implementation cost tells you which world you are in. It also probes whether "the text to inject" and "the text to log" are computed from one source or independently.

---

### MR-04 -- Name the offending file in configuration warnings

**Requirement.** A warning about a tool that appears in permission patterns but is unrecognised or ungoverned must name the configuration file the offending pattern was declared in, and its hierarchy level. Today the warning names the tool and gives corrective steps, but a user with a project config, an ancestor config, a user config, and a split rules directory has no way to know which of them to edit. The corrective-steps text is unchanged; only the source attribution is added.

**Observable acceptance.** Put a pattern for an unrecognised tool in a user-level `toolguard_hook.toml`, trigger a hook invocation, and confirm the entry in `logs/toolguard-warning-YYYY-MM-DD.md` names that file. Move the same pattern into a file in the split rules directory and confirm the warning names that specific file instead. The stderr copy of the warning carries the same attribution.

**Predicted irreducible footprint: 2 places.** (1) Wherever startup validation examines the collected permission patterns and raises the issue -- the patterns it inspects must still know which file they came from. (2) Wherever a warning is rendered into the warning-log entry and its stderr copy, to include the new field.

**Why it might discriminate.** Validation is a good place to find a lossy merge. If configuration loading merges every level's patterns into one flat list *before* validating, the origin no longer exists at the point the warning is raised, and the cheap fix (re-scanning the files from the validator) is a duplication of the loader's own discovery logic -- exactly the kind of shortcut a badly-organised codebase invites. A well-organised one validates rules that still know their source, and this is two small edits. Note this shares a shape with MR-02 but exercises a different pipeline (validation rather than resolution), so running both tells you whether origin loss is systemic or local.

---

### MR-05 -- A broken configuration file must warn every time, not once per session

**Requirement.** Toolguard suppresses a repeated warning after its first appearance in a session, using a marker so the terminal is not flooded. The warning that a configuration file failed to parse must be exempt from that suppression: it is emitted on every invocation until the file is fixed. The documentation already frames a broken config as a stop-work item whose friction should be "loud and repeated"; the once-per-session marker currently works against that.

**Observable acceptance.** Introduce a syntax error into a `toolguard_hook.toml` (the documented easy way: split a structured rule entry across two lines). Trigger several tool calls in the same session and confirm the broken-config warning appears on stderr for every one of them, while an unrelated warning -- an ungoverned tool, say -- still appears only once. Fix the file and confirm the warning stops. No marker file is created for the broken-config warning.

**Predicted irreducible footprint: 1 to 2 places.** (1) Wherever the decision "has this warning already been shown this session?" is made -- it needs one exemption for this warning kind. (2) Possibly, wherever the broken-config warning is raised, if warnings do not currently carry a kind that the suppressor can test.

**Why it might discriminate.** This is the classic single-policy-point test. If suppression is one gate that every warning passes through, the change is a single conditional. If the marker-file dance is inlined at each site that warns, the implementer must either find and skip the right one of many copies, or refactor first. It also probes whether warnings are typed values or formatted strings -- because if the only thing distinguishing this warning is its message text, the honest implementation has to match on prose, which is a smell any reviewer would flag and a well-organised codebase would not force.

---

### MR-06 -- Recognise one more foreign interpreter for the ASK floor

**Requirement.** Toolguard applies an ASK floor to inline code and heredoc payloads fed to interpreters it recognises, and documents that an interpreter it does not know (naming `lua`, `deno`, `bun`, `julia`) is *not* floored, so a broad allow would permit its inline code. Add `deno` to the recognised set, so `deno eval "..."` and a heredoc piped to `deno` both get the same ASK floor that `node -e` and a heredoc piped to `python` get today. Nothing else about the floor changes.

**Observable acceptance.** With a broad allow in place that would otherwise permit it, `deno eval "console.log(1)"` resolves to ask rather than allow; a heredoc whose sink is `deno` is classified as an executor sink and likewise floors to ask; an explicit deny for `deno` still denies. A named script -- `deno run app.ts` -- is still matched normally and is not floored. Existing interpreters are unaffected.

**Predicted irreducible footprint: 1 to 2 places.** One, if a single set of recognised foreign interpreters serves both the heredoc-sink classifier and the inline-code classifier. Two, if those are separate lists -- which the documentation hints at by describing them in separate tables with slightly different membership.

**Why it might discriminate.** The documentation describes one rule ("code passed inline to an interpreter is handled by the same executor rule as heredocs") applied in two syntactic situations. If the code honours that, there is one list and one edit. If it does not, the implementer either edits two lists -- and a future maintainer will one day edit only one -- or has to unify them as part of a "one-word" change. The versioned-interpreter behaviour (`python3.13`, `pypy3.11` recognised automatically) adds a second dimension: whether adding a name automatically inherits that treatment, or requires a parallel edit somewhere else.

---

### MR-07 -- Recognise a JavaScript project root

**Requirement.** When no explicit project-root override is set, toolguard walks upward looking for a `.git` directory, then a `pyproject.toml`. Add `package.json` as a third marker, checked after the existing two. A JavaScript or TypeScript project with no git repository and no Python metadata currently resolves its root to some ancestor directory, which silently misplaces the log directory and mis-anchors every relative file-path pattern.

**Observable acceptance.** In a directory tree containing only `package.json` and no `.git` or `pyproject.toml`, toolguard writes its daily logs under that directory rather than an ancestor's, and a relative deny pattern such as `Read(**/.env)` protects that directory's `.env`. In a directory containing both `package.json` and `pyproject.toml`, behaviour is unchanged -- `pyproject.toml` still wins, because the search order is unchanged and only extended.

**Predicted irreducible footprint: 1 place.** Wherever the upward search for a project root decides which filenames count as markers. That list is the only thing that genuinely differs.

**Why it might discriminate.** This is a duplication detector, nothing else. Project root is consumed by log placement, by environment-file loading, by relative-path anchoring for patterns, and by the operator tooling that reports on a project's configuration. If one primitive answers "where is the root", this is a one-line change and every consumer inherits it. If any consumer re-implements the walk -- and a hook that must stay dependency-free is exactly the kind of code where someone inlines a four-line upward search rather than importing one -- the change either misses a consumer (a bug the acceptance test above will catch only if it exercises the right consumer) or costs several edits. It is the cheapest requirement in the set on a well-factored codebase, which makes any measured cost above one meaningful.

---

### MR-08 -- Let the log format be selected

**Requirement.** Toolguard can already render its resolution log in a JSONLines shape, but no configuration selects it, so every installation gets markdown. Add an environment variable, `TOOLGUARD_LOG_FORMAT`, accepting `markdown` (the default, and the behaviour when the variable is unset or set to anything unrecognised) or `jsonlines`. When `jsonlines` is selected, resolution entries are written as one JSON object per line. Only the resolution stream is affected; the error, warning, and conflict streams stay as they are.

**Observable acceptance.** With the variable unset, the daily resolution log is markdown exactly as today. With `TOOLGUARD_LOG_FORMAT=jsonlines`, the same commands produce one JSON object per decision, carrying the same facts the markdown entry carries. With `TOOLGUARD_LOG_FORMAT=nonsense`, output is markdown and toolguard does not fail. The variable appears in the documented environment-variable table with its default.

**Predicted irreducible footprint: 2 places.** (1) Wherever environment configuration is read and defaulted, to add and validate the new variable. (2) Wherever the log writer is invoked for a resolution decision, to pass the selected format instead of assuming markdown.

**Why it might discriminate.** The documentation states the renderer already exists, is tested, and is retained specifically so a future setting can expose it -- so on a well-organised codebase this is genuinely a wiring change: read a value, pass it at one call site. The cost is entirely a function of how many call sites write a resolution entry. If the hook writes decisions from the command path, the file-path path, the compound sub-command path, and a fallback path, each hardcoding the format, this becomes four edits and a latent inconsistency where one path ignores the setting. It also quietly tests whether environment configuration is a single resolved object or a scattering of direct lookups, since a new variable in the latter world has no natural home.

---

### MR-09 -- Strip one more blanket-allow spelling in takeover mode

**Requirement.** In takeover mode, toolguard strips a built-in set of five blanket allow patterns out of native Claude settings so they cannot bypass the real rules. Add `Bash(*:*)` to that built-in set. It is the prefix-syntax spelling of the same blanket grant that `Bash(*)` expresses, and a config carrying it today defeats takeover mode exactly as `Bash(*)` would have before it was defaulted.

**Observable acceptance.** With takeover mode enabled and `Bash(*:*)` present in the native `settings.local.json` allow list, a command that toolguard's own rules do not permit is still not allowed by that native pattern -- it resolves by toolguard's rules and fallback as though the native pattern were absent. The same pattern written in a `toolguard_hook.toml` is *not* stripped, matching the documented rule that only native settings are filtered. With takeover mode off, nothing is stripped. Users' own additions to the additive ignore lists continue to work unchanged.

**Predicted irreducible footprint: 1 place.** Wherever the built-in default ignore set is declared. Both user-facing keys are documented as additive to that set, so a single list gains one entry.

**Why it might discriminate.** The interesting failure is duplication across *tools* rather than across code paths: the security audit reasons about takeover-mode misconfiguration and the maintenance analyzer reasons about over-broad allows, so both plausibly hold their own idea of "what counts as a blanket allow". If the runtime's defaults and the analyzers' notion of a blanket allow are one shared definition, this is one edit and the audit's findings stay consistent with enforcement. If they are three copies, the implementer will either produce a config that toolguard strips but the audit still flags (or worse, the reverse), or will have to touch all three. That divergence-between-tool-and-runtime risk is a real quality signal and is invisible from a single edit count.

---

### MR-10 -- Govern notebook edits as a first-class file-path tool

**Requirement.** Claude Code's `NotebookEdit` tool modifies a file on disk but is not one of toolguard's recognised tools, so governing it today requires declaring it as an additional supported tool and it has no defined path semantics. Make `NotebookEdit` a built-in recognised tool, treated as a file-path tool whose governed path is the notebook path from the tool's input. It must be governed only when it appears in both the hook matchers and `governed_tools`, exactly like every other tool.

**Observable acceptance.** With `NotebookEdit` registered as a hook matcher and listed in `governed_tools`, a rule `NotebookEdit(~/projects/myapp/**)` allows an edit to a notebook under that tree and a call outside it is refused; a `deny` for `NotebookEdit(**/secret/**)` beats the allow. Listing `NotebookEdit` in permissions without adding it to `additional_supported_tools` no longer raises an unsupported-tool warning. An `Edit` rule does not grant `NotebookEdit` permission, consistent with the documented rule that each file-path tool has its own patterns.

**Predicted irreducible footprint: 2 to 3 places.** (1) Wherever the set of recognised tool names is declared. (2) Wherever a governed tool is classified as a command tool or a file-path tool. (3) Wherever the path to check is extracted from the tool's input, since this tool names its path field differently from `Read`/`Write`/`Edit`. This is the largest of the twelve and is included deliberately as an upper anchor.

**Why it might discriminate.** This is the strongest structural probe in the set: it asks whether "a supported tool" is a described thing with attributes -- name, kind, where its subject lives in the payload -- or a name that appears in several independent membership tests. In the first world, the change is one new entry plus, at most, one small extractor. In the second, the implementer must find every place that asks "is this a file-path tool?" and every place that reaches into the payload for a path, with no compiler help and a real chance of missing one. The failure mode of missing one is silent under-enforcement, which is the worst kind of bug this product can have -- so it is also the requirement whose *review* cost differs most between a good and a bad codebase.

---

### MR-11 -- Make the similarity display count configurable

**Requirement.** The migration tool's duplicate/similarity report shows at most three similar patterns per pattern; the documentation states plainly that this is a fixed constant with no configuration key, and the agent-facing map records it as a recurring question. Expose it as `max_similar_matches` under the `[config_sync]` section, defaulting to `3` so existing behaviour is unchanged. A value below 1 or a non-integer is ignored with the default used.

**Observable acceptance.** With no key set, a dry-run migration shows up to three similar matches per pattern, as today. With `max_similar_matches = 5`, the same run shows up to five. With `max_similar_matches = 0` or a string value, it shows three and the run does not fail. The key appears in the annotated configuration reference alongside the other `[config_sync]` keys.

**Predicted irreducible footprint: 2 places.** (1) Wherever `[config_sync]` settings are read and defaulted, to add the key with its default and validation. (2) Wherever the constant currently caps the similarity list. The 0.7 similarity cutoff is deliberately left alone -- one knob, not two.

**Why it might discriminate.** Turning a constant into a setting is the standard test of whether a configuration section is a described schema or a bag that each consumer dips into. If `[config_sync]` is already a typed group with defaults declared in one place, adding a key is mechanical. If each of its existing keys is read ad hoc where it is used, there is no obvious place to put the new one and the implementer invents a fourth convention. It also probes the boundary between the hook (which must not depend on this) and the operator tooling (which consumes it) -- a codebase where the migration tool can read configuration without dragging in the enforcement path pays less here.

---

### MR-12 -- Number the parts of a compound command in the log

**Requirement.** A compound command is logged as one entry per sub-command. Each such entry must state its position within the compound and the total number of parts -- for example, part 2 of 3. A reader scanning the log currently sees several adjacent entries with no indication that they belong to one tool call, or whether any part is missing. Entries for a non-compound command are unchanged and carry no position field.

**Observable acceptance.** Run `git status && git log && ls`; the three resulting entries are marked as parts 1, 2, and 3 of 3, in the order the sub-commands appear. Run `git status` alone; its entry carries no position field. Run a compound in which one part is denied; the denied part's entry carries its correct position and the total still reflects every part that was evaluated.

**Predicted irreducible footprint: 2 places.** (1) Wherever the per-sub-command results are iterated to be logged -- both the index and the total are already in hand at that point. (2) Wherever a resolution entry is rendered, to emit the optional field.

**Why it might discriminate.** This is a deliberately easy change whose only enemy is a lost collection: if sub-command results are written out as they are produced, one at a time, the total is not known at write time and the implementer must either buffer the results or count the parts twice. That is precisely the kind of "we stream where we should have modelled" structure that is invisible until something needs the aggregate. Combined with MR-01, it also shows whether the compound logging path is a genuine reuse of the single-command path or a parallel implementation -- the documentation already reports one behavioural divergence between them (compound entries fold provenance into the rule text instead of using the provenance field), which is a strong hint that they are not the same code.

---

## Considered and rejected

- **Decompose `case`, `if/else`, or nested control structures.** Grammar work. The project's own conventions require a two-phase change to the PEG grammar with its own review, and the blast radius is the whole compound-resolution path. Not a micro-requirement by any reading.
- **Decompose process substitution `<(...)`.** Same reason, plus a genuine design question about what the inner commands mean, which makes it ambiguous as well as large.
- **Add a fifth pattern dialect (say `[fnmatch]` or `[literal]`).** Touches parsing, matching, validation, the migration tool's superset detection, the audit's regex-anchoring findings, and every doc that lists the dialects. It looks small because it is "one more of an existing thing", but the existing thing has five consumers.
- **Make the 500-word `additionalContext` budget configurable.** Two objections. It touches the configuration schema, the budget, the audit (a large budget is arguably a finding), and the docs; and it is a policy question the documentation has not settled, so two developers would build different validation and different audit behaviour. MR-03 extracts the cheap, unambiguous part of the same area.
- **Make `undecidable_fallback` settable per tool or per rule.** A resolution-model change disguised as a configuration change. The floor's strictest-wins semantics would need a per-scope answer at every point it is applied.
- **Add a `--explain` mode that prints why a command resolved as it did.** A new user-facing surface with a whole output format to design. Interesting, but it would measure documentation-writing more than code organisation.
- **Add per-rule auto-mode awareness (a rule that applies only under a given permission mode).** This is a planned feature in its own right, spanning configuration, resolution, and logging. Far too big, and it would contaminate the experiment with design work.
- **Add a fifth log stream, or log rotation/retention.** New subsystem, and retention has real policy questions (what to keep, how to prune safely) that make it ambiguous as well as large.
- **Split `toolguard-update-check`'s exit code 2 into "offline" and "install kind unknown".** Genuinely small and unambiguous -- but predictably one edit at one classification site with no cross-path duplication anywhere, so it would discriminate between codebases hardly at all. Rejected for low signal, not for size.
- **Make the session-warning marker directory configurable.** Same problem: one constant, one consumer, no structural question asked. Also drags in a `/tmp` permissions discussion that is beside the point.
- **Allow structured rule entries (with `additionalContext`) inside native `settings.json`.** The documentation says this rejection is deliberate, not an oversight. A requirement that reverses a stated design decision measures argument, not implementation.
- **"Improve performance of the hook" / "cache the resolved configuration".** No observable behaviour change, no stated problem, no measurement. Unacceptable as a requirement and unfalsifiable as an acceptance test.
- **Reformat or colourise the log output.** Vague; there is no single correct target, so two developers produce two different things.

---

## Where the documentation left me unsure

These are places where a careful blind reader cannot determine current behaviour. Several bear directly on the requirements above, and I have written those requirements to avoid depending on the unresolved part.

1. **`auto-mode.md` recommends the legacy spelling of the setting it is about.** Its recommended configuration block is `[takeover_mode]` / `no_match_fallback = "allow_with_warning"` -- the nested form that `configuration.md` calls a legacy alias honoured only when no level sets the top-level key, and that both `configuration.md` and `takeover-mode.md` tell you not to use in new configs. A reader following the auto-mode page verbatim writes exactly the form the rest of the documentation warns against. This looks like a straightforward doc bug, and it is on the page most likely to be followed literally by an agent.
2. **Whether the foreign-interpreter ASK floor applies to command tools other than `Bash`.** `configuration.md` calls it "the Bash-only inline/heredoc-foreign-code floor", but the JetBrains terminal tool and custom MCP command tools are documented as command tools that share the `Bash(...)` pattern namespace and, by implication, the same compound decomposition. If a `python -c` issued through the JetBrains terminal is *not* floored, that is a security-relevant asymmetry that no page states outright. MR-06's acceptance is written against `Bash` only, for this reason.
3. **Whether `permission_mode` actually appears in the resolution log.** `auto-mode.md` states that toolguard's logs record Claude Code's own `permission_mode` for every decision. `architecture.md`'s enumeration of what a resolution entry records does not mention it, and neither its markdown example nor its JSONLines example contains it. One of the two pages is wrong, and a reader cannot tell which. This matters to MR-01 and MR-12, since both add a field to the same entry.
4. **Whether an ordinary file-path denial gets provenance.** The documented example of a refused `Write` shows no provenance field and a violated-rules value of "Path does not match any allow patterns" -- which is a fallback, not a rule. Whether a path denied by an explicit `deny` rule carries provenance is never stated. MR-02 is scoped to hard-deny to stay clear of this.
5. **What `uv` means as a heredoc sink.** The heredoc table lists `uv` among foreign interpreters, alongside `python` and `node`. But `uv` is a package manager that also runs non-interpreter things, and the inline-code table's example is the compound `uv run python -c`. Whether a heredoc piped to a bare `uv` is floored, and whether `uv run ./script.sh` is treated as an interpreter invocation, is not determinable from the docs.
6. **Which warnings use "once per day" rather than "once per session".** `config-sync.md` documents both frequencies but never says which warning uses which, nor whether anything can configure it. MR-05 is written as an exemption from suppression generally, so it does not depend on the answer -- but the gap is real, and a user cannot predict when they will see a given warning again.
7. **Where the `allow_with_warning` warning is written.** `auto-mode.md` says the unmatched decision is logged to the daily resolution log "with a warning marker". `configuration.md`'s description of the stricter `allow` value says it produces no warning "not in the resolution log reason, not in the WARNING log stream", implying `allow_with_warning` writes to both. Neither page says so directly, so a reader auditing an unattended run does not know which file to read.
8. **`intent-disclosure-rules.example.toml` does not exist.** The repository's own `CLAUDE.md` points at it by name, twice, as the reference for the intent-disclosure rules; the only `*example*.toml` in the repository is `docs/gh-cli-rules-example.toml`. I was explicitly told to read any `*.example.toml` to see the config surface users write, and there is none to read beyond the `gh` one. Either the file was never committed or it was removed without updating the reference.
9. **A user-facing document cites an internal ticket as an explanation.** `docs/architecture.md`'s package listing annotates one component with a bare ticket identifier as its rationale. A ticket ID means nothing to anyone outside this repository, and the surrounding document is linked from `llms.txt` and `README.md` as general reference. Worth a pass for the same pattern elsewhere.
10. **`agent-map.md` warns that it is itself likely to be stale.** Its own drift warning says the hand-curated question-and-pointer section has no regeneration path. I did not find a contradiction between it and the underlying docs, but a reader is being told, in the document, not to trust the document -- which is a reasonable disclosure and also a standing maintenance liability worth naming.
