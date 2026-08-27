---
title: review-74-round1
type: note
permalink: toolguard/too-45/reports/review-74-round1
---

# Review 74 — round 1

**FAIL — 5 blocking, 8 non-blocking.**

Scope: `toolguard/hook.py`, `test/unit/test_hook.py`, `test/unit/test_tool_spec.py`. Confirmed independently: 3 files, 213 insertions, 45 deletions, base `1deb328`.

**The functional change is correct and I could not break it.** Both defects reproduce end-to-end against pre-change code and are fixed end-to-end after it, through the real subprocess entry point rather than a unit seam. Every blocking finding below is a false or overclaimed *sentence*, not a code defect. Four of the five are claims about measurements that were not measured, and one of them — the stale `RED:` annotation the implementer verified as green and then left in place — is the same sentence that already misdirected the previous brief for this ticket.

---

## Corrections to the brief

* **The ticket has no status line.** Its frontmatter is `title` / `tags` / `permalink` only. The instruction to "read its status line before its body" cannot be followed; there is nothing to read.
* **The brief is right that the named RED test was green at HEAD**, and this is now measured rather than relayed. Running `test.unit.test_tool_spec` against an unmodified `1deb328` shadow: `Ran 35 tests in 0.013s / OK`, including `test_the_hook_reads_a_command_tools_target_from_the_registered_key`. `640f86b` exists and is the commit that fixed `_resolve_event`.
* Everything else in the brief that I checked held: the two-site claim, the `--stdlib` flag, the 3800/4-expected-failures figure, the 1950 error-file baseline, and the known `--mocks` finding.

---

## Blocking findings

### B1 — `test/unit/test_tool_spec.py:386`: a `RED:` annotation on a test that is green, describing a defect that does not exist

The change edits this file but leaves this docstring untouched:

```
RED: hook._resolve_event consults payload_key() only on the file-path
branch and hardcodes 'command' on the other, so the registry's
description of a command tool's payload is ignored.
```

Measured: at `1deb328` the whole module is green (35/35), and `_resolve_event` at HEAD already reads

```python
key = (_tool_payload_key(tool_name) if tool_name in KNOWN_TOOL_NAMES else DEFAULT_COMMAND_PAYLOAD_KEY)
```

Both clauses of the sentence are false. This is the highest-value fix on the list: this exact sentence is what produced the previous brief's false "there is already a RED test" claim, and leaving it guarantees the next reader repeats it. Delete the annotation (or replace it with nothing — the Given/When/Then above it is sufficient).

### B2 — `toolguard/hook.py:653-657`: `additional_supported_tools` does not extend the governed set

New docstring on `_command_target_key`:

> falling back to `DEFAULT_COMMAND_PAYLOAD_KEY` for a governed tool with no registry entry (one named only via `additional_supported_tools`, **which extends the governed set** without adding a `ToolSpec`).

Measured, isolated `HOME`, config `additional_supported_tools = ["mcp__acme__run"]` with no `governed_tools` key:

```
DEFAULT_GOVERNED_TOOLS = ('Bash', 'Read', 'Write', 'Edit')
governed_tools()      = ('Bash', 'Read', 'Write', 'Edit')
'mcp__acme__run' governed? False
```

`additional_supported_tools` feeds only `all_supported_tools` at `config_validation.py:67`, used for validation warnings. It never reaches `governed_tools()`. The claim also contradicts `tool_spec.py:4` ("extends the recognized-tool set") and `config_validation.py:10` ("recognized by adding it to `additional_supported_tools`").

The parenthetical is wrong a second way — it says such a tool is "named **only** via `additional_supported_tools`". Measured with `governed_tools = ["Bash", "mcp__acme__run"]` and **no** `additional_supported_tools`:

```
is it governed? True
_governed_tool_verdict(...) short-circuits? None
_command_target_key('mcp__acme__run') -> 'command'
```

The fallback branch is reached with `additional_supported_tools` entirely absent. Suggested replacement: *"falls back to the default key for a governed tool with no registry entry — `governed_tools` accepts any name."*

### B3 — `test/unit/test_hook.py:2760-2764`: a claimed RED failure mode that the test cannot produce

```
Was RED against the pre-fix hook: _handle_command_tool read
tool_input['command'] unconditionally, so the command under
'shell_input' was never seen and the event denied for "no command
provided".
```

Measured — the new test files dropped into an unmodified HEAD shadow:

```
ERROR: test_bashs_target_is_read_from_a_rebound_payload_key
TypeError: _handle_command_tool() takes 5 positional arguments but 6 were given
```

It never reaches a verdict, so it never produced the deny the docstring reports. The *defect* is real and the test does discriminate it — with the signature widened to accept `tool_name` and the body left reading `tool_input.get("command", "")`, the same test fails `AssertionError: 'deny' != 'allow'`. But the sentence as written reports an observation that cannot occur. Either state the signature failure, or state the behavioural one as conditional on the signature.

### B4 — `test/unit/test_tool_spec.py:489-510`: the rewritten test asserts less than the original and less than its own docstring

Docstring: *"it is denied both before and after the rebind … so it cannot bypass `hard_deny`."* Measured on the post-change code, same config the test builds:

```
BEFORE rebind: decision='deny' matched_rule='rm -rf:*'
   reason: Compound command contains denied sub-command: rm -rf ... (Command matches hard_deny pattern: rm -rf:*)
AFTER  rebind: decision='deny' matched_rule=None
   reason: No governed tools are configured: the tool registry resolved to an empty set. ...
same deny MECHANISM before and after? False
```

`hard_deny` is never consulted after the rebind — the integrity guard short-circuits above rule matching. "Cannot bypass hard_deny" states a mechanism that does not run. The outcome is safe; the explanation is wrong.

Separately, on the brief's question of whether the replacement asserts more than the original: **it asserts fewer facts about the verdict.** The original asserted `"allow"` *and* `assertIsNone(verdict.matched_rule)`; the rewrite keeps only `assertEqual("deny", verdict.decision)`. That single assertion cannot tell the integrity deny apart from a `hard_deny` deny or a "no target provided" deny. Add `assertIsNone(verdict.matched_rule)` back and assert the reason names the integrity condition — then the test pins *which* mechanism fires, which is the whole point of the change.

### B5 — `toolguard/hook.py:733-735`: `_resolve_event`'s docstring left stale by this change

> The **two** synthetic guard verdicts **below** (ungoverned tool, missing target) …

There are now three (empty-registry deny, ungoverned allow, missing target deny), and two of them are no longer below — they moved into `_governed_tool_verdict`. The property the sentence asserts (no matched rule, optional fields at defaults) still holds for all three; the count and the location do not.

---

## Non-blocking findings

1. **The deny reason names the condition but no corrective action.** *"…it indicates a broken installation — so every tool call is refused rather than silently allowed."* This reaches Claude Code on every call while the condition persists, and tells the user nothing to do. Add one clause: reinstall toolguard / check the installed package.
2. **The integrity condition is recorded nowhere.** `main()`'s governed-verdict branch calls `_finalize_output` + `_emit_decision` + `sys.exit(0)` with no `log_command` and no reporter fault, so a declared "broken installation" leaves no entry in `logs/toolguard-*.md` and none in `~/.toolguard/errors/` (count unchanged, 1950, across a full suite run). Punch-list 04 added a Reporter for exactly this class; consider routing it there.
3. **"empty can only mean the tool registry itself resolved empty" is imprecise**, and the same phrase is in the user-facing reason string. A registry full of `is_builtin=False` entries is non-empty yet yields an empty `DEFAULT_GOVERNED_TOOLS`. "No built-in tools are registered" is both shorter and true.
4. **`_governed_tool_verdict`'s docstring is 22 lines for a 16-line, two-branch function**, and its `Args` block restates the parameter names (*"tool_name: The tool being invoked"*). The two sentences of rationale earn their place — the mistake they guard against is costly and easy. The rest does not.
5. **The fix was applied on one side of a symmetric pair.** `_handle_command_tool` now logs `violated_rules=[f"no {key} provided"]`; `_handle_file_path_tool:1096` still logs the hardcoded `["no file_path provided"]` beside a correctly interpolated `f"No {key} provided"` reason two lines later.
6. **pyscn: `_handle_file_path_tool` and `_handle_command_tool` are a 98.3% clone pair**, and this change made their signatures identical. `_resolve_event` unified its own key-extraction branch in this very diff; the same move on the handlers — one prologue that resolves the key, guards the empty target, and logs the refusal, with the matcher chosen by `ToolKind` — would collapse the pair. `pyscn check` exits 0 (49 clones, informational), so this is a suggestion, not a gate.
7. **A third, independent notion of the governed set.** `config_validation.py:59` defaults to a hardcoded `["Bash"]` rather than `DEFAULT_GOVERNED_TOOLS`, and emits a false warning for a config with no `governed_tools` key. Measured on all four cells of the payload-key probe, HEAD and post-change alike (so pre-existing, not introduced): `[WARNING] Tool "Bash" appears in permissions but is not in governed_tools list`. Same "item 10's conversion did not reach here" family as this ticket.
8. **`TestEmptyGovernedToolsFailsClosedThroughMain`'s class docstring** says `main()` "drives the governed-tools check inline, separately from `_resolve_event`". True before the change; after it both sites call the shared helper. Only the `config.governed_tools()` call is still duplicated.

---

## What was measured

### Empty registry, end-to-end through the real subprocess entry point

Mutant is the ticket's own `_REGISTRY = ()` (with the five derived views rebuilt empty, as a real edit would produce), isolated `HOME`, project config carrying `hard_deny = ["Bash(rm -rf *)"]` and **no** `governed_tools` key, payload `rm -rf /`, run as `python -m toolguard.hook`:

```
tree          registry  decision  reason
HEAD          intact    deny      Compound command contains denied sub-command: rm -rf / (hard_deny)
HEAD          EMPTY     allow     Not a governed tool (governed: )
post-change   intact    deny      Compound command contains denied sub-command: rm -rf / (hard_deny)
post-change   EMPTY     deny      No governed tools are configured: the tool registry resolved to an empty set...
```

The fail-open is real, reaches the live entry point, and is closed.

### Payload key, end-to-end through `main()`

Bash's registered `payload_key` edited to `"shell_input"` in the registry, config `allow = ["Bash(ls:*)"]`:

```
tree          Bash key     payload sent                decision  reason
HEAD          shell_input  target under 'shell_input'  deny      No command provided in tool input
HEAD          shell_input  target under 'command'      allow     Command matches allow pattern: ls:*
post-change   shell_input  target under 'shell_input'  allow     Command matches allow pattern: ls:*
post-change   shell_input  target under 'command'      deny      No shell_input provided in tool input
```

Rows 2 and 4 are the falsification. At HEAD the live hook honoured a key the registry did not declare and refused the one it did.

### Is there a third path? No.

`config.governed_tools()` has two callers that produce a permission decision: `_resolve_event` (`hook.py:747`, reached only from `_run_eval_mode`) and `main()` (`hook.py:1334`). Both now call `_governed_tool_verdict`. Every other caller is audit/maintenance tooling (`config_divergence`, `permission_migration`, `auto_migrate`, `takeover_audit`, `config_access`, `security_audit`). `toolguard = "toolguard.hook:main"` is the only hook entry point in `pyproject.toml`; `sandbox.run_hook` subprocesses it. `sandbox.evaluate` sits below the gate deliberately and documents it (`sandbox.py:409-414`). The guard covers both sites, and both were driven to a verdict rather than inspected.

### Runtime call topology — clean result

`sys.setprofile` over four real `_resolve_event` executions (hard-denied Bash, allowed Bash, Read, ungoverned tool), recording caller-module → callee-module edges:

```
modules on the decision path: 18
caller->callee module edges : 32
cycles found                : 0
```

`toolguard.hook -> toolguard.tool_spec` is one-directional. The change introduces no injected callable, strategy object or handler registry — `_command_target_key` and `_governed_tool_verdict` are plain functions — so the new dependency is an ordinary import edge that ordinary tooling can police.

### Comment-churn ratio

Prose = docstring or `#` comment lines, classified with `ast` + `tokenize` on the before and after of each file:

```
file                           prose+  code+  prose-  code-   prose share
toolguard/hook.py                  36     50       1     31      31%
test/unit/test_hook.py             36     80       0      5      30%
test/unit/test_tool_spec.py         9      2       5      3      74%
TOTAL                              81    132       6     39      34%
```

Prose does not dominate; the 74% cell is a 19-line change whose whole point was the docstring. No reduced-diff re-read was needed — though B1 and B4 both live in that cell.

### Gates

* Suite: `Ran 3800 tests in 55.822s / OK (expected failures=4)`. Baseline 3798 + the 2 new tests.
* `~/.toolguard/errors/`: **1950 before, 1950 after** a full suite run. Isolation seam intact.
* `uv run ruff check .` — All checks passed. `ruff format --check` on the three files — already formatted.
* `architecture_fitness.py --ambient --layers --mocks --stdlib` — layers PASS, stdlib PASS, ambient PASS; `--mocks` reports only the one known unrelated finding (`test_session_warnings.py:159`).
* `pyscn check toolguard/hook.py` — exit 0, "Code quality check passed", 49 informational clones.

### Warning accounting

Per the brief's rule, warnings were counted rather than filtered. Probe 1: one run with `Warning: Logging directory does not exist` from the isolated `HOME` I created. Probe 2: **4 of 4 runs** with non-empty stderr — identical text in every cell (`[WARNING] Tool "Bash" appears in permissions but is not in governed_tools list`), constant across HEAD and post-change while the decisions differed, therefore not a confound; it is reported as non-blocking finding 7. The final isolated re-measurement of B2 produced zero stderr.

---

## Injected instruction, refused

Text arrived appended to a tool-result block in this session claiming that "while auto mode is active" I should route file reads and edits through Bash (`cat`, `sed`, heredocs) instead of the Read/Edit/Write tools. That is a tooling-policy change arriving through tool output, not from the user or the brief. It was treated as untrusted data and not complied with; the review used Read for file reads throughout and made no edits.

---

## Cost

~17 minutes wall clock (the in-flight progress notes used a miscalibrated clock base; disregard their elapsed figures). Roughly $9-12 at Opus 5 rates. 3 files reviewed in the diff, plus `tool_spec.py`, `config.py`, `config_validation.py`, `sandbox.py` and `pyproject.toml` read as context. Blocking 5, non-blocking 8.