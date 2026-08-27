---
title: Blind estimate (uncertainties) - item 04 error reporter
type: note
permalink: toolguard/too-45/reports/surprise/04-estimate-uncertainties
tags:
- task-memory
- TOO-45
- measurement
---

## Named uncertainties

**1. Does a usable reporting seam already exist, so that "one new module" is really "one new function on an existing observability module"?**

Settle it with: `grep -rn "^def \|^    def " toolguard/error_log.py toolguard/log_writer.py toolguard/session_warnings.py` to enumerate the public surface of the observability layer, then `grep -rn "log_warning\|log_error\|log_conflict\|log_crash" toolguard/ test/` to see who already calls it and with what shape.

Effect on the estimate, by mechanism: if the observability layer already exposes a severity-keyed entry point, the change stops being "introduce a module" and becomes "widen an existing module plus 16 call-site edits" — the added-production count drops to zero, the concentration moves out of a new file into an existing one, and the new-test file becomes new test *classes* inside an existing test module instead.

**2. How many hand-rolled stderr writes are there really, and are any outside the four modules the ticket names?**

Settle it with: `grep -rn "sys\.stderr\|stderr\.write\|print(.*stderr" toolguard/ tools/ | cut -d: -f1 | sort | uniq -c | sort -rn`.

Effect: the ticket's "the engine layer has zero" says nothing about the api, runtime, tooling or support layers. If the hook, session-start, installer or update-check paths carry a comparable number of writes, the author faces a scope choice, and either the touch set widens by several large modules or the item lands with a documented carve-out — which changes the *count* far more than it changes the concentration.

**3. Does "visible to Claude" mean the hook's JSON output, and if so does the reporter have to reach the decision-output assembly?**

Settle it with: `grep -rn "additionalContext\|hookSpecificOutput\|systemMessage\|permissionDecisionReason" toolguard/ docs/` and check whether any of those fields is assembled anywhere other than the process entry point.

Effect: routing to stderr and to a log file is a leaf-level side effect and needs no plumbing. Routing *to Claude* is a return value, and a return value has to travel from a config-layer module up through the decision path to whatever serializes the hook response. That is a threading problem, and it would pull the api/decision-orchestration seam and possibly the verdict-comparison harness into the change — none of which the "16 mechanical moves" framing anticipates.

**4. Where does the severity/kind vocabulary come from — new enum, or an existing structured issue type?**

Settle it with: `grep -rn "severity\|class .*Severity\|Level\b" toolguard/*.py` and read the structured configuration issue type end to end (it is 35 lines; the whole answer is in it).

Effect: if a structured issue/severity type already exists, the reporter should consume it and the shared-vocabulary module changes rather than gaining a competitor. If it does not, the reporter defines the vocabulary and a constants/vocabulary module may gain the string names — this is exactly the "literal strings with semantic meaning" rule, so expect names, not bare `"warning"` literals, and expect them somewhere importable by all four config-layer modules.

**5. Can the reporter use the once-per-period facade at all, given the layer order and the store-failure caveat?**

Settle it with: read the layer declarations for the throttle facade and its sqlite store (`grep -n "once_per" .pyscn.toml`), and `grep -rn "^from \|^import " toolguard/once_per.py toolguard/once_per_store.py` to see what the facade drags in.

Effect: if the throttle facade sits at or above the reporter's layer, the reporter cannot import it and throttling has to be inverted (callers of the reporter throttle, or the reporter takes an injected throttler) — which contradicts "noise suppression is not a concern of the calling code" and would force either a layer re-declaration or a re-entrancy guard inside the reporter. Either way the reporter grows a fallback path and at least one test for "the throttle store is itself what failed", which is the case most likely to be skipped.

**6. How much existing test code asserts on stderr, and how?**

Settle it with: `grep -rln "stderr" test/unit/ | wc -l` then `grep -rn "assertIn(.*stderr\|redirect_stderr\|StringIO" test/unit/ | cut -d: -f1 | sort | uniq -c | sort -rn`.

Effect: my test-modify count is the least anchored number in the estimate. If stderr capture is a widespread idiom rather than confined to the four modules' own test files, the churn is broad-but-shallow and the modified-test count roughly doubles without the concentration moving at all. If instead there is a shared capture helper, the churn collapses into that helper.

**7. Does the reporter need test isolation of its own?**

Settle it with: `grep -rn "STORE_PATH\|_PATH =\|Path.home()" toolguard/once_per_store.py toolguard/error_log.py toolguard/log_writer.py` and look at how the existing per-module isolation helpers and real-home guards are wired from the package `__init__` of the test tree.

Effect: this repo has a demonstrated pattern of adding a real-home/real-logs *guard* whenever a module learns to write under the user's home. If the reporter throttles via the sqlite store, or writes anywhere new, expect an isolation helper plus a guard test — two extra test files that a naive reading of the ticket would never predict, and historically these have also been renamed mid-ticket, which shows up in a diff as add+delete rather than modify.

**8. Is there already an enforcement mechanism that will fail once the bypasses are removed — or that should be added to stop them coming back?**

Settle it with: `grep -rn "stderr" tools/architecture_fitness.py .claude/rules/*.md` and `grep -rn "forbidden\|banned\|predicate" tools/architecture_fitness.py | head -40`.

Effect: the ticket's stated failure mode is "left alone they read as the convention". The only durable answer in this repo is a machine check, not prose. If the fitness instrument already has a mechanism for banned constructs, adding one predicate is cheap and the dev-tooling touch is small; if it does not, the author either builds one (a substantial addition to a 4000-line instrument and its 4000-line test file, which would dominate the diff by line count) or skips it (and the item is smaller than I predicted but weaker).

## What in the briefing looks misleading

- **Line counts invert the importance.** The takeover-notice module is 39 lines and is the pivot of the whole classification question; the config module is 2514 lines and contributes 3 mechanical edits. Ranking predicted touches by file size would be exactly backwards here.
- **The docstring for the throttle facade already says "a warning or action" and the briefing says it returns something with `.warn()`.** That is a facade that already has an opinion about severity. It is possible the reporter is largely a *re-labelling* of that facade rather than new policy — or, conversely, that the two overlap and one of them has to give. The briefing cannot distinguish those, and the difference is the whole "the policy is the work" claim.
- **No import graph, no call graph.** I cannot see whether the four config-layer modules already import the observability layer for other reasons. If they do, the "layering was routed around" story is only half true, the edits are local, and nothing structural changes. If they do not, each of the four gains a first-ever dependency on that layer, and the layer checker has something to say about it.
- **The inventory shows a `_real_once_per_home_guard` helper but the working tree is mid-rename in this area.** Helper renames land as add+delete pairs and will inflate any raw file count against the estimate without any of it being substance.
- **"16 hand-rolled stderr writes" is presented as a measured fact with a per-module breakdown, which makes it feel settled.** It is settled only for the config layer. The sentence "the engine layer has zero" is doing quiet work: it is the only other layer mentioned, and the silence about the four layers above it is the single largest gap in what I was shown.
- **The verdict corpus is described as structurally blind here, which is true and also a trap.** It means the corpus will stay green through a completely wrong routing implementation, so the presence of a passing suite is not evidence about this item at all; the only signal is the new per-destination tests.
