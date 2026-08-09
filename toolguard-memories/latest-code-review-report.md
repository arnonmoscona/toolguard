---
title: latest-code-review-report
type: report
tags:
- code-review
- TOO-45
permalink: latest-code-review-report
---

# Code review report -- 2026-08-09

**Ticket**: TOO-45 (punch-list #10 -- ToolSpec registry)
**Scope reviewed** (9 files, as requested):

- `/home/arnon/projects/toolguard/toolguard/tool_spec.py` (new, 96 lines)
- `/home/arnon/projects/toolguard/toolguard/constants.py`
- `/home/arnon/projects/toolguard/toolguard/config_validation.py`
- `/home/arnon/projects/toolguard/toolguard/hook.py`
- `/home/arnon/projects/toolguard/toolguard/tools/installer.py`
- `/home/arnon/projects/toolguard/toolguard/tools/transcript_harvest.py`
- `/home/arnon/projects/toolguard/test/verdict_corpus/fixture_loader.py`
- `/home/arnon/projects/toolguard/tools/architecture_fitness.py`
- `/home/arnon/projects/toolguard/test/unit/test_tool_spec.py` (new, 101 lines)

Also inspected as part of the change set: `/home/arnon/projects/toolguard/.pyscn.toml`.

## Summary

This is a well-executed consolidation: four hand-written tool-name sets and every production `"file_path"` literal now derive from one registry, the dead `hook.COMMAND_TOOLS` was correctly identified as dead (zero readers at HEAD) and deleted, the new module has a declared architectural home in `.pyscn.toml`, and `--layers` passes clean on both completeness and direction. The full suite passes (2721 tests, OK) and ruff is clean on all nine files.

The problems are not in the mechanics but in what the registry *claims*. `governed_by_default` names a set that contradicts the runtime's actual default in two other places, and the derived views are functions in one module and frozen snapshots in another -- so the registry's headline promise ("adding a tool is one entry here") is true for some consumers and false for others, with no test that could tell. Nothing is broken today; both are traps set for the next change.

**Verdict**: no critical or security issues. Two Major findings (both naming/contract, both cheap to fix while the ticket is open), six Minor, four Suggestions.

---

## Critical

None.

## Major

### M1. `governed_by_default()` asserts a default that contradicts the runtime default -- inside the module declared the single source of truth

- `toolguard/tool_spec.py:79-81` -- `governed_by_default()` docstring: *"Tool names governed unless a config's `governed_tools` overrides it"*, returning `{Bash, Read, Write, Edit}`.
- `toolguard/config.py:974-976` -- the runtime default is `("Bash",)` when no layer configures `governed_tools`.
- `toolguard/config_validation.py:80,82` -- independently defaults to `["Bash"]`.
- `test/verdict_corpus/configs/hard_deny.toml:6` and `pattern_forms.toml:5` both document the `("Bash",)` default explicitly, and set the four tools by hand *because* it is not the default.

So "which tools are governed by default" now has three definitions, and the newest one -- in the module whose whole purpose is to be authoritative -- disagrees with the two that actually drive behaviour. This is inert today only because no runtime path reads it. The risk is the obvious next step: a future author wiring `Configuration.governed_tools()`'s fallback to `governed_by_default()`, which the name actively invites, would silently begin governing `Read`/`Write`/`Edit` on every project with no toolguard config.

Look at what the flag's real consumers do with it -- `security_audit.py:353`, `maintenance.py:184,715` (`sorted(GOVERNED_TOOLS)` as the target list) and `transcript_harvest.py:281` (`if tool not in GOVERNED_TOOLS: continue`). None of them mean "default"; all of them mean "the built-in Claude tools we know how to work with", as opposed to the user-specific MCP name.

**Fix**: rename the `ToolSpec` field and the derived view to what the set is -- `is_builtin` / `builtin_tools()` (or `core_tools()`) -- and correct the docstring. Keep `constants.GOVERNED_TOOLS` as the exported name if importers depend on it, but say in its comment that it is the built-in set, not a default. Separately worth folding the two `["Bash"]` fallbacks (`config.py:975`, `config_validation.py:80`) into one named constant, since that *is* the default and it is currently duplicated.

### M2. Derived views are live functions in the registry but frozen snapshots in `constants.py` -- one registry, two view semantics, no test that can see the difference

- `toolguard/constants.py:27,31` -- `GOVERNED_TOOLS = governed_by_default()` and `FILE_TOOLS = file_kind_tools()` bind **at import time**.
- `toolguard/tools/installer.py:901`, `toolguard/tools/transcript_harvest.py:227`, `toolguard/hook.py:731,1094` call the registry functions **at call time**.

`tool_spec.py:36` promises *"Adding a tool is one entry here; every derived view below picks it up automatically"*. That holds for the calling consumers and not for the snapshotting ones. Today the registry is a static module-level tuple so the two can't diverge -- but the function form advertises dynamism the constant form does not have, and `_REGISTRY` is private with no injection seam, so there is no way to write a test that would catch a divergence if one were ever introduced.

**Fix**: make the three derived views module-level frozensets rather than zero-arg functions (`KNOWN_TOOL_NAMES`, `BUILTIN_TOOLS`, `FILE_KIND_TOOLS`), leaving `payload_key()` as the only function. That makes the snapshot semantics uniform and honest, removes three per-call frozenset constructions, and is simpler code than what is there now. If instead the intent really is a live registry, the fix is the opposite -- `constants.py` must call, not snapshot -- but that seems like more machinery than a five-entry static table warrants.

## Minor

### m1. `constants.py` module docstring is now false

`toolguard/constants.py:6-7` -- *"Keeping them here -- in a leaf module that imports nothing from toolguard"*. Line 21 now imports `toolguard.tool_spec`. One-line correction: say it imports only other foundation modules, matching the `.pyscn.toml` foundation definition.

### m2. `tool_spec.py` docstring is self-contradictory and wrong about `Configuration.governed_tools()`

`toolguard/tool_spec.py:7-10` -- *"The CONFIGURABLE governed/supported-tool sets stay exactly as they are -- `Configuration.governed_tools()` and `additional_supported_tools` consume this registry rather than duplicating it"*. The first half and second half contradict each other, and the second half is factually wrong: `Configuration.governed_tools()` (`config.py:949-976`) reads config layers and never touches the registry. Only `config_validation.KNOWN_SUPPORTED_TOOLS` consumes it. Drop the claim about `governed_tools()`.

### m3. Half-converted payload-key dispatch -- the `"command"` literal survives next to the registry

- `test/verdict_corpus/fixture_loader.py:680` -- `key = payload_key(tool) if tool in FILE_PATH_TOOLS else "command"`
- `toolguard/tools/transcript_harvest.py:226-229` -- same shape

The registry knows the payload key for *every* tool, including command-kind ones, so the `FILE_TOOLS` branch plus the hardcoded `"command"` is exactly the duplication the ticket set out to remove -- half-removed. A command-kind tool registered with a non-`command` key would be resolved correctly by the registry and wrongly by these two sites.

**Fix** (both sites):

```python
spec = TOOLS_BY_NAME.get(tool)
key = spec.payload_key if spec else "command"
```

The `else` fallback is still needed for unregistered tools (e.g. `mcp__local-tools__checked_bash`, deliberately not in the registry), but it becomes an unknown-tool fallback rather than a second definition of the command key.

### m4. Deny reason hardcodes `file_path` after the key became dynamic

`toolguard/hook.py:734` and `toolguard/hook.py:1107` both return `reason="No file_path provided in tool input"`, and `hook.py:1094` names the local `file_path`, while the key itself now comes from `_tool_payload_key(tool_name)`. If a file-kind tool ever registers a different key, the message names a key the caller never sent -- and this reason string reaches the user. Interpolate the resolved key. `test/unit/test_hook_eval.py:166` asserts on the substring and must be updated in the same edit.

### m5. Test gaps in `test/unit/test_tool_spec.py`

- **No registry-integrity test.** `TOOLS_BY_NAME` (`tool_spec.py:71`) is a dict comprehension, so a duplicated `name` in `_REGISTRY` collapses silently. Add `assertEqual(len(TOOLS_BY_NAME), len(_REGISTRY))`, plus an assertion that every `payload_key` is non-empty.
- **`test_tool_spec_is_frozen` (line 92)** uses `assertRaises(Exception)`, which would pass on any unrelated error. Use `dataclasses.FrozenInstanceError`.
- **Nothing tests the behaviour that actually changed.** The existing hook, harvest and fixture tests pass `{"file_path": ...}` literals and would pass identically against the pre-refactor code, so the registry seam itself is unpinned. A single test that swaps in a file-kind tool with a different payload key and drives `hook._resolve_event`, `transcript_harvest._command_for_tool` and `fixture_loader.build_hook_payload` would pin it -- and would immediately surface M2 and m3.
- **`test_constants_module_constants_equal_derived_views` (lines 47-50)** is near-tautological: both sides are the same call. It catches only re-hardcoding, which the literal-pinning tests above already cover.

### m6. Public function imported under a private alias

`toolguard/hook.py:51` -- `from toolguard.tool_spec import payload_key as _tool_payload_key`. There is no name collision in `hook.py` to avoid, and the leading underscore makes call sites read as if the function were module-private. Import it plainly, or alias without the underscore.

## Suggestions

### s1. Three names still denote one value -- collapse the alias chain while the ticket is open

`tool_spec.file_kind_tools()` -> `constants.FILE_TOOLS` -> `hook.FILE_PATH_TOOLS`. The last is already carrying a comment saying it exists only because tests import it. The refactor cut *literal* duplication from four sites to one but left the *name* duplication at three. `FILE_PATH_TOOLS` has exactly three readers -- `toolguard/hook.py`, `test/unit/test_hook.py`, `test/verdict_corpus/fixture_loader.py` -- so deleting it is cheap now and gets more expensive later. Per project convention, "it breaks N tests" is not an objection.

### s2. `.pyscn.toml` layer assignment was done correctly -- worth noting because this is the step that usually gets skipped

`tool_spec` was added to the `foundation` packages list, and `uv run python tools/architecture_fitness.py --layers` reports "All modules map to exactly one layer" and "No cross-layer direction violations". An unassigned new file is drift by default and layer checkers commonly fail silently on it; this one did not.

### s3. Keep the `_CANARY_FILE_TOOLS` comment framing

`tools/architecture_fitness.py:3673-3679` replaces a rationale about subprocess-vs-import with the actual reason: *"a check that derives the fact it verifies from the thing it verifies can only ever agree with itself"*. That is the correct and more durable justification for not importing `tool_spec` here, and it generalises to every other canary in that file.

### s4. Typing style in `tool_spec.py`

The module mixes `typing.FrozenSet` / `typing.Mapping` (lines 15, 71, 74, 79, 84) with the builtin generic `tuple[ToolSpec, ...]` (line 37). Use builtin generics and `collections.abc` throughout: `frozenset[str]`, `Mapping` from `collections.abc`.

---

## Architectural drift pass

Run because the change touches six production files and carries a ticket ID. These are observations for judgement, not thresholds.

**Blast radius vs. conceptual size.** One concept (a tool registry) landed in 6 production files + 1 new test + 1 dev-tool comment + 1 corpus fixture + 1 config file. The ratio looks bad in isolation and is not: this is a *consolidation*, and it reduces definition sites (four hand-written tool-name sets and every production `"file_path"` literal collapse to one table). High file count here is the cost of paying down duplication, not evidence of a concept smeared across the tree.

**Logical coupling (co-change).** Over the last 400 commits, 54 touched `toolguard/` (excluding merges and the two >40-file architecture-overhaul commits, which would swamp the signal):

| file | commits | distinct co-change partners |
|---|---|---|
| `toolguard/hook.py` | 29 / 54 (54%) | 60 |
| `toolguard/config.py` | 25 | 68 |
| `toolguard/tools/installer.py` | 12 | 55 |
| `toolguard/config_validation.py` | 3 | 51 |
| `toolguard/tools/transcript_harvest.py` | 2 | 38 |
| `toolguard/constants.py` | 2 | 21 |

`hook.py` changes in over half of all commits touching the package and co-changes with 60 distinct files, at 1445 lines. That is the package's clearest hub, and it is a standing condition rather than something this change created -- the change adds two lines to it. `config.py` is second. Neither is a finding against this change set; both are the reason to keep doing punch-list consolidations like this one.

**100%-coupled pairs** (rarer file never changed without the other, min 4 commits): `config.py <-> config_types.py` (8/8), `resolve.py <-> rule_entry.py` (4/4), `config_types.py <-> rule_entry.py` (4/4), `config.py <-> rule_entry.py` (4/4). Those four files behave as one module. They are untouched here, but that is structurally the *same shape* punch-list #10 just fixed for tool names, and they are the obvious next candidates. (`resolve.py`/`hook.py <-> tools/decision.py` at 5/5 is historical -- `decision.py` was deleted in item 05.)

**New file has an architectural home.** Yes -- see s2. Clean.

**Boundary crossings.** The change spans source (`toolguard/`), dev tooling (`tools/`) and test fixtures (`test/verdict_corpus/`). Not a real crossing: the `tools/architecture_fitness.py` edit is comment-only and its explicit point is that it must *not* import the new module. No boundary was weakened.

**Test cost trend.** 101 new test lines against roughly 126 production lines added/changed, about 0.8:1, versus a standing repo ratio of ~1.9:1 (65,030 test lines / 34,481 production lines, excluding the generated parser). Below the project's norm. Normally that is a good sign for a refactor with existing behavioural coverage -- but here the shortfall lands exactly where it matters (m5): the new tests pin the registry's *contents* while the *seam* the refactor introduced is unpinned, and the pre-existing tests cannot distinguish the new code from the old.

---

## Verification performed

- `uv run python -m unittest discover -s test -t .` -- **Ran 2721 tests, OK**.
- `uv run ruff check` on all nine scoped files -- **All checks passed**.
- `uv run python tools/architecture_fitness.py --layers` -- completeness and direction both clean.
- Confirmed `hook.COMMAND_TOOLS` had zero readers at HEAD (`git grep -n COMMAND_TOOLS HEAD -- '*.py'` returns only its own definition), so the deletion is dead-code removal, not a behaviour change. `mcp__local-tools__checked_bash` dropping out with it is consistent with `KNOWN_SUPPORTED_TOOLS`, which deliberately excluded it as user-specific.
- Confirmed no remaining production `"file_path"` literals outside the registry and the deliberate canary.
- Confirmed the `KNOWN_SUPPORTED_TOOLS` `set` -> `frozenset` change is safe: its only use is `KNOWN_SUPPORTED_TOOLS | set(additional_supported_tools)` (`config_validation.py:90`), and no caller mutates it.
- Confirmed the `installer.py:901` ordering change (`("Read","Write","Edit")` -> `sorted(file_kind_tools())`, i.e. Edit/Read/Write) is cosmetic: `test/unit/test_tools_installer.py:1274` asserts membership, not order.

**pyscn not run** -- the effective diff is ~65 lines across a small set; the layer fitness check above is the relevant structural check for this change. Say the word if you want a full `uvx pyscn analyze` pass before the push.

**code-review-graph note (trial)**: one non-trivial use, `get_impact_radius` on the three foundation files -- 500 nodes / 81 files at depth 2, "risk: high", with `ConfigIsolationMixin` and `isolate_config_environment` as top "key entities". That is what you get asking for blast radius on a foundation constants module: technically true, not actionable, and the named entities were unrelated test scaffolding. Targeted greps for the specific symbol names (`COMMAND_TOOLS`, `GOVERNED_TOOLS`, `FILE_PATH_TOOLS`, `"file_path"`) answered the real question -- who reads this -- faster and exactly. **The graph did not earn this invocation.** Phase: refactoring/consolidation. No staleness refresh was needed (impact radius is an auto-updating layer).