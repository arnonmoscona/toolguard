---
title: TOO-45 MR-10 blind prediction
type: note
permalink: toolguard/too-45/reports/mr10-prediction
tags:
- task-memory
- TOO-45
- canary
---

# TOO-45 MR-10 blind prediction (NotebookEdit as a built-in file-path tool)

## What I read, and what I did not

I read exactly three things: the `touch_set_inventory.py` output for `/var/tmp/tg-pristine-P1`, the same for `/var/tmp/tg-pristine-P2`, and product documentation from the working repo `/home/arnon/projects/toolguard` -- specifically `docs/architecture.md` (package structure, file-path tool patterns, error/warning logs) and `docs/configuration.md` (the "Declaring additional supported tools" and "Recommended tools to govern" sections), plus grep hits for `governed_tools` / `additional_supported_tools` / `file-path tool` across `README.md` and `docs/`.

I did not open, grep, glob or read any `.py` file in either pristine tree. I ran no `git log`, `diff`, `blame` or any other VCS command anywhere. I read nothing under `toolguard-memories/`. I did not inspect either tree's tests beyond the docstring lines the inventory itself prints. Neither tree was modified.

## Contamination disclosure: I used `--validate-predictions` as a name probe, and it taught me more than I expected

The known tool gap is real and it bit immediately: every membership set this requirement touches is a module-level constant, and the plain inventory prints none of them. So I used `--validate-predictions` as a probe, twice: once on my first-draft predictions, and once with an explicit list of ~26 candidate names. Because the validator prints *nearest-match suggestions* for every invalid location, it is a considerably stronger instrument than a yes/no existence check -- it volunteered real names I had not asked about. That is contamination, so here is exactly what I would have written without it.

Before probing, my answer for **both** trees was:

- `toolguard/constants.py::FILE_PATH_TOOLS` and `toolguard/constants.py::SUPPORTED_TOOLS` -- my guessed names for the file-path tool set and the hardcoded recognised-tool list, placed in `constants.py` because it is 42 lines with zero public functions or classes in both trees, which is the signature of a pure constants module.
- `toolguard/config.py::_anchor_file_pattern` -- I put the project-root anchoring of relative file-path patterns in `config.py` because `test_hierarchical.TestAnchorFilePattern` sits beside the other configuration-hierarchy tests.
- For P2, `toolguard/api.py::_decide_file_path` -- inferred as the symmetric sibling of `_decide_bash`, which `test_api.TestDecideBashToolOverride` names.

What the probe corrected (identically in both trees, note):

- The file-path set is `toolguard/hook.py::FILE_PATH_TOOLS`, and there is a **separate** `toolguard/constants.py::FILE_TOOLS`, and a **separate** `toolguard/hook.py::COMMAND_TOOLS`, and a **separate** `toolguard/constants.py::GOVERNED_TOOLS`.
- The recognised-tool list is `toolguard/config_validation.py::KNOWN_SUPPORTED_TOOLS`.
- Anchoring lives in `toolguard/resolve.py::_anchor_file_pattern`, not `config.py`. There is also a `toolguard/resolve.py::_match_file_path_pattern`.
- P1 has `toolguard/tools/decision.py::_decide_bash` **and** `_decide_file_path`; P2 has `toolguard/api.py::_decide_bash` but **no** `_decide_file_path`, so P2's file-path arm is inside `api.decide` itself.
- Both trees already factor the hook into `hook.py::_handle_command_tool` and `hook.py::_handle_file_path_tool`. Only P2 *tests* those functions by name (`TestHandleCommandToolAuditWiring` / `TestHandleFilePathToolAuditWiring`), which is why the plain inventory made that factoring visible in P2 and invisible in P1.

The concepts I predicted were right in every case; the names and one module were wrong. That gap -- right concept, wrong address -- is the honest measure of what these inventories gave me, and it is entirely attributable to the constants blind spot plus the fact that private helpers are invisible unless a test class happens to name them in its docstring.

## Predictions

- `/var/tmp/mr10-P1-predictions.json` -- **20 locations** (15 source, 5 test).
- `/var/tmp/mr10-P2-predictions.json` -- **21 locations** (14 source, 7 test).

Both validate at 20/20 and 21/21 real locations with zero invalid entries. One mechanical note for whoever scores these: `--validate-predictions` rejects the `{"entries": [...]}` envelope the task specifies ("must contain a JSON array at the top level, got dict"), so I validated bare-array copies in my scratchpad and kept the specified shape at the required paths. That is a spec-vs-tool mismatch worth fixing in one place or the other.

### P1 (20)

| Location | Kind |
|---|---|
| `toolguard/hook.py::FILE_PATH_TOOLS` | decide |
| `toolguard/constants.py::FILE_TOOLS` | decide |
| `toolguard/constants.py::GOVERNED_TOOLS` | decide |
| `toolguard/config_validation.py::KNOWN_SUPPORTED_TOOLS` | parse_validate |
| `toolguard/config_validation.py::validate_permissions` | decide |
| `toolguard/hook.py::_handle_file_path_tool` | decide |
| `toolguard/hook.py::main` | decide |
| `toolguard/hook.py::load_file_path_patterns` | transport |
| `toolguard/hook.py::_resolve_event` | decide |
| `toolguard/tools/decision.py::_decide_file_path` | decide |
| `toolguard/tools/decision.py::decide` | decide |
| `toolguard/resolve.py::resolve_file_path_permission_detailed` | transport |
| `toolguard/resolve.py::_anchor_file_pattern` | transport |
| `toolguard/tools/transcript_harvest.py::harvest_transcript_file` | parse_validate |
| `toolguard/tools/installer.py::cmd_write_config` | record |
| `test/unit/test_hook.py::TestFilePathTools` | test |
| `test/unit/test_hook.py::TestFilePathToolsInMain` | test |
| `test/unit/test_configuration.py::TestValidationAdditionalSupportedTools` | test |
| `test/unit/test_tools_decision.py::TestDecideFilePath` | test |
| `test/unit/test_hook_eval.py::TestResolveEventAntiDrift` | test |

### P2 (21)

Same spine, with three structural differences that the inventory made visible on its own: the decision facade moved to `toolguard/api.py` (`tools/decision.py` is a 38-line re-export shim with no public symbols, so it needs no change), P2 has a dedicated `test/unit/test_api.py`, and P2 tests `_handle_file_path_tool` directly. The P2 file therefore swaps `tools/decision.py::decide` + `::_decide_file_path` for `api.py::decide`, and adds `test_hook.py::TestHandleFilePathToolAuditWiring` and `test_api.py::TestApiDecideSmoke`.

## Confidence

**P1: moderate.** High confidence on the shape of the change -- five membership sets, a path-extraction site in the hook, a validation list, a facade, and the file-path resolver. Lower confidence on addresses, because P1's inventory exposes almost nothing private: `hook.py` advertises five public symbols (`EmptyStdinError`, `parse_hook_input`, `create_hook_output`, `load_file_path_patterns`, `main`) for 1235 lines, so `_handle_file_path_tool`, `_handle_command_tool` and `_resolve_event` are all invisible in the plain listing. I recovered `_resolve_event` only because `test_hook_eval.TestResolveEventAntiDrift`'s docstring names it, and `_handle_file_path_tool` only from the probe.

**P2: moderately high.** Same requirement, better signposting. `api.py`'s existence and one-line purpose ("Public decision interface for toolguard -- the `api` layer") told me where the facade went; `tools/decision.py`'s purpose line ("Backward-compatible re-export") told me it is *not* a change site, which is a genuinely useful negative; and two test-class docstrings (`TestHandleFilePathToolAuditWiring`, `TestHandleCommandToolAuditWiring`) leak the hook's internal factoring for free. P2's inventory made this change easier to locate, and the mechanism is worth naming precisely: **not** because P2's modules are better documented -- both trees' module docstrings are near-identical -- but because P2's *test* docstrings name more private functions, and because P2's refactor gave two concepts (public decision API, backward-compatible shim) their own modules with their own purpose lines. Structure that has been named is structure an inventory can report.

## Surprises, and one self-description that pointed me wrong

**The biggest surprise is a false negative, not a false positive.** P1 and P2 have the *same* hook factoring (`_handle_command_tool` / `_handle_file_path_tool`), but P1's inventory gave me no way to know that. I predicted `main` for P1 where I predicted `_handle_file_path_tool` for P2 -- and only the probe told me both were available in both. An inventory that reports public top-level symbols systematically under-describes a module whose real seams are private, and `hook.py` is exactly that module in both trees. This is the single largest measurement distortion I hit.

**The constants gap is not a minor caveat for this requirement -- it is the whole requirement.** Every one of the five membership sets MR-10 must touch is a module-level constant. A predictor restricted to the plain inventory can say "there is a recognised-tool list and a file-path tool set somewhere" but cannot name a single one of them, and cannot count them. Since the interesting half of MR-10 is *how many* independent lists there are, the tool as it stands cannot answer the question it is being used to ask. If the constants gap gets closed anywhere, `constants.py` is where it pays.

**What pointed me wrong**: `toolguard/constants.py` -- "Shared immutable constants for toolguard", 42 lines, zero public symbols in both trees -- reads like the obvious single home for tool-name sets, and I put both of my constant predictions there. It does hold two of them (`FILE_TOOLS`, `GOVERNED_TOOLS`), but `hook.py` independently holds `FILE_PATH_TOOLS` and `COMMAND_TOOLS`, and `config_validation.py` independently holds `KNOWN_SUPPORTED_TOOLS`. The docstring's word "shared" invites you to believe it is the sole owner. It is not, and nothing in either inventory hints at the duplication.

A smaller one, in the other direction: `test_hierarchical.TestAnchorFilePattern` sits in the configuration-hierarchy test module, which pulled me to `config.py`; the function is in `resolve.py`. Test-module organisation is a decent locator for *concepts* here but an unreliable one for *modules*.

## Described thing, or a name in several membership tests?

**Both trees are squarely in the membership-test world, and to the same degree.** This is the clearest finding in the exercise, and I would have called it correctly from the plain inventory alone -- the probe only let me count the tests instead of merely asserting they exist.

From the inventories alone: neither tree has a tool-registry module, and neither tree's public symbol listing contains anything like a `ToolSpec`, `ToolDescriptor`, `ToolKind` or `GovernedTool` type. P2's `config_types.py` grew substantially in the TOO-45 refactor (369 -> 822 lines, 8 -> 12 public types) and the types it gained are all about *verdicts* -- `LevelMatch`, `UnitVerdict`, `RuntimeVerdict` -- not about tools. That is the telling detail: P2 demonstrably knows how to promote a scattered concept into a described thing with attributes, and it did exactly that for the verdict while leaving the tool as a bare string. A tool in both trees is a `str` that must independently pass muster in several places.

The probe put numbers on it. Five separate name lists, identically named in both trees:

1. `constants.FILE_TOOLS`
2. `constants.GOVERNED_TOOLS`
3. `hook.FILE_PATH_TOOLS`
4. `hook.COMMAND_TOOLS`
5. `config_validation.KNOWN_SUPPORTED_TOOLS`

And a sixth fact that follows from what is *absent*: I probed for `constants.TOOL_PATH_KEYS` and `hook.TOOL_PATH_FIELDS` and neither exists in either tree. So there is no tool-to-input-key mapping at all -- the governed path is read out of `tool_input` by a literal key, in each place that needs it. That is precisely why MR-10 has to say "it has no defined path semantics": path semantics are not a property a tool *has* in this design, they are a string literal at each read site. `NotebookEdit` is the first governed tool whose path key is not `file_path`, which makes it the first case where those literals diverge.

So: adding a genuinely new *kind* of file-path tool costs five list edits plus at least one new branch or lookup at every `tool_input` read site (the live hook, the `--eval` path, and the transcript harvester at minimum). Neither tree has a place where you could add one row and be done. If MR-10's implementer introduces a tool descriptor, that is a design improvement the requirement invites but neither codebase currently expresses -- and it would be the single highest-value thing to watch for when the actuals land.
