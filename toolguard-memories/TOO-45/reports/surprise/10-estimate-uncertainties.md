---
title: Blind estimate (uncertainties) - item 10 ToolSpec
type: note
permalink: toolguard/too-45/reports/surprise/10-estimate-uncertainties
tags:
- task-memory
- TOO-45
- measurement
---

# Blind estimate (uncertainties) - item 10 ToolSpec

## Named uncertainties

### 1. Is "four membership sets" the true count, or the count someone could name from memory?

**Question:** how many places test a tool name for membership, equality, or dispatch?

**Check:** `grep -rnE '["'"'"'](Bash|Read|Write|Edit|NotebookEdit)["'"'"']' toolguard/ tools/ test/ | grep -vE '^\S+:\s*#'` and, separately, the structural forms: `grep -rnE '(==|!=|\bin\b|\bnot in\b)\s*[({\[]?\s*["'"'"'](Bash|Read|Write|Edit)' toolguard/ tools/`. Also worth the frozen-container form on its own: `grep -rnE 'frozenset\(|= \{"' toolguard/`.

**Why it changes the estimate:** the ticket's own evidence is that two copies were found only by grepping for literal tuples, which means the enumeration method that produced "four" is the same method that already missed two. If the structural grep returns roughly four sites, this is a tight refactor concentrated in the lowest layer plus the hook. If it returns a dozen-plus spread across rule normalization, resolution, auditing and the agent-facing tooling, the mechanism changes from "define a type and derive four views" to "sweep every layer", the diff crosses more layer boundaries, and the risk shifts from design to omission — which is the silent-under-enforcement failure the ticket is trying to eliminate. That difference roughly doubles my production count.

### 2. Are there really only three payload-read sites?

**Question:** how many sites pull the governed subject out of the tool payload, and how many distinct keys are in play?

**Check:** `grep -rn 'tool_input' toolguard/ tools/ test/` and then narrow with `grep -rnE 'get\(\s*["'"'"'](file_path|command|notebook_path|content|pattern|path)["'"'"']' toolguard/ tools/ test/`.

**Why it changes the estimate:** anything that *constructs* a payload is as much a client of the tool-to-key map as anything that reads one, and this codebase has several payload constructors — a behavioural sandbox, a replay/diff harness, a corpus fixture loader, log and transcript harvesters. The ticket counted readers only. If constructors also hardcode keys, the map has to be importable by the test-support and tooling layers as well as the hook, which pushes it decisively into the lowest layer and adds test-tree files to the touch set that a reader-only view would never predict.

### 3. Which layer can legally own the registry?

**Question:** of the modules that hold a membership test or a payload read, what is the *lowest* declared layer among them?

**Check:** read the layer-to-package mapping in the machine-readable architecture config, then intersect it with the module list from uncertainties 1 and 2. Then run the repo's own layer-direction checker and completeness check before and after a trial placement.

**Why it changes the estimate:** the ticket offers two homes, and they are in different layers — one foundation-ish, one config. If any foundation or observability module tests tool membership, the config-layer home is illegal and the checker will say so, forcing the registry down and possibly forcing a *split* (the type in one layer, the instances in another). A split doubles the number of production files that must change and adds an architecture-test change; a single foundation home keeps it to one new or one modified module. This is also the one failure mode that is loud rather than silent, so it is cheap to settle early and expensive to discover late.

### 4. Can the supported-tool set be extended at runtime, and if so what is an unknown tool's payload key?

**Question:** does the config option that adds tools accept arbitrary names, and does anything downstream then need a kind and a payload key for a name the registry has never seen?

**Check:** grep the config loader and validator for the additional-supported-tools option and trace what it feeds; then find a test that adds an unknown tool name and see what the resulting decision does with its payload.

**Why it changes the estimate:** if the set is closed at import time, the registry is a frozen constant and the derived views are comprehensions — trivial. If it is open, the registry cannot be a constant: it becomes a static default plus a config-derived overlay, the payload key for an unregistered tool becomes `Optional`, and every extraction site gains a "no known subject" branch. That branch is a new decision path, not a refactor, and it is exactly the sort of thing the verdict corpus would catch — which makes it a scope question, not a style question. This is my single largest source of estimate variance.

### 5. Do the existing membership tests agree with each other today?

**Question:** do all current membership tests normalize the tool name the same way — case, whitespace, and the scoped `Tool(pattern)` form versus the bare name?

**Check:** for each site found in uncertainty 1, look at what is compared: a raw payload field, a stripped value, a lowercased value, or a name already parsed out of a rule's scope prefix. A targeted way in is to find the rule-scoping code and check whether it lowercases before comparing, then compare that against the validator's set.

**Why it changes the estimate:** unifying divergent normalizations is a behaviour change wearing a refactor's clothes. If one site is case-insensitive and another is not, then after unification some input decides differently, the golden corpus goes red, and the correct response is a deliberate decision about which behaviour is right — plus corpus cases recording it. If they already agree, the corpus should be untouched and a red corpus means a genuine mistake. Knowing which world you are in before running the suite is the difference between "expected diff" and "stop and think".

### 6. Is `NotebookEdit` in scope for this item or deferred?

**Question:** is the pending case being added now, or is the registry merely being made able to accept it later?

**Check:** grep the whole tree (including docs and config fixtures) for the name; if it appears only in a ticket or note, it is deferred. Cross-check whether the file-tool machinery assumes a single path key.

**Why it changes the estimate:** adding it makes the change user-visible, which under this project's conventions pulls in configuration documentation, release notes, and a version bump, and adds a second file-path key name to the map — which is precisely the case that proves the map is needed. Deferring it keeps the item internal and doc-light. My estimate assumes deferred; if it is in scope, add three or four documentation-side files.

### 7. Does anything order or sort by tool, rather than merely test membership?

**Question:** is there a canonical tool ordering used when rules are sorted or written back to config files?

**Check:** grep the sorting and comment-preserving TOML machinery for a tool-name sequence or a priority mapping keyed by tool name.

**Why it changes the estimate:** an ordering is a fifth kind of tool knowledge the ticket does not mention, and it is the dangerous kind: if a registry replaces a hand-written order with, say, declaration or alphabetical order, the next config rewrite reorders users' files wholesale. That is a large, confusing, behaviour-preserving-but-alarming diff, and it would justify keeping the order as an explicit registry attribute rather than an emergent property. Finding one here adds a production file and a test file and changes the shape of the type.

### 8. Does the repo's fitness-predicate instrument expect a new predicate for this?

**Question:** does the project's pattern of encoding structural rules as machine-checked predicates apply to "there is exactly one tool registry"?

**Check:** list the predicate names the fitness instrument already exposes and see whether any is about duplicated constants or unmapped membership sets; also check whether the architecture test module asserts predicates by name.

**Why it changes the estimate:** this project has a documented distrust of prose rules and a preference for programmatic enforcement, and the whole point of the ticket is that the previous duplication was undetectable except by grep. If the convention is "structural rule gets a predicate", the change grows by a predicate plus its tests — and the test module for that instrument is one of the largest in the tree, so a small predicate can look like a large diff in any line-count measure. That would distort a line-based reading of the touch set without changing its architectural substance.

---

## What in the briefing looks misleading

- **A 42-line module reads as a trivial leaf.** The shared-constants module's line count says nothing about how many modules import it, and the inventory shows no import edges at all. It is plausibly the most-imported file in the package and the ticket proposes making it more so. Do not let its size suggest the change is small there.

- **"Thin configuration data types" is a stale docstring.** The module described that way is 1122 lines. The ticket's own evidence cites it growing 369 to 822 — the inventory says it has since grown another 300 lines. Two consequences: the ticket's headline number is already out of date, and the word "thin" cannot be trusted as a signal about what belongs there.

- **Two of the four named production files have no obviously-named test module.** There is no test module named for the shared constants and none named for config validation in the inventory. Their coverage lives under some other name, so predicting "the test that changes" for those two is guesswork, and the actual touch set will likely surprise on the test side more than the production side.

- **The package-init in the test tree is 117 lines, not a marker.** It contains machinery, which means a newly added test module may require a change there — an edge that a naive "one new test file" prediction misses entirely.

- **The architecture config is quoted but absent from the inventory.** I was shown its content and not its line count or its position in the file list, so I cannot see how granular the layer mapping is or how many modules are enumerated. Any prediction about whether a new module needs a layer entry is therefore an inference from the comment text, not an observation.

- **Docstring-first-line only hides the tool-name dependence of the repo-root dev instruments.** Their docstrings all start with the same "Dev-only instrument, NOT shipped" boilerplate, so the first line is uninformative for four large files — the single largest blind spot in this view.
