---
title: TOO-45 MR-12 blind prediction
type: note
permalink: toolguard/too-45/reports/mr12-prediction
tags:
- task-memory
- TOO-45
- canary
---

# TOO-45 MR-12 blind prediction

## What I read, and what I did not

I read exactly three things: the output of `tools/touch_set_inventory.py --tree /var/tmp/tg-pristine-P1`, the same for `/var/tmp/tg-pristine-P2`, and `README.md` plus `docs/architecture.md`, `docs/agent-guides.md`, `docs/permission-patterns.md`, `docs/configuration.md` (via grep and one targeted read of the Logging section) from `/home/arnon/projects/toolguard` — the working repo, not either pristine tree. I also read `tools/touch_set_inventory.py` and grepped `tools/touch_set_score.py` in the working repo to determine the predictions-file schema the validator accepts, which is tooling, not product code.

I did not open, grep, glob, or read any `.py` file in either pristine tree. I did not run `git log`, `git diff`, or `git blame` anywhere. I did not read anything under either tree's `toolguard-memories/`, and I did not inspect either tree's tests beyond the module/class docstring lines the inventory itself prints. I did not use `--validate-predictions` as a name probe before forming the prediction: I wrote both files in full, then validated once, and changed nothing but the JSON envelope shape afterwards. So no probing contamination applies to any entry — the predictions below are exactly what I wrote blind.

One deviation from the brief worth flagging: the brief's example shows `{"entries": [...]}`, but both `tools/touch_set_inventory.py --validate-predictions` and `tools/touch_set_score.py` require a **top-level JSON array** and reject the wrapper object with exit code 2. I wrote the deliverables as top-level arrays of the same entry objects so the measurement tooling can actually consume them.

## Predictions

`/var/tmp/mr12-P1-predictions.json` — 13 entries. `/var/tmp/mr12-P2-predictions.json` — 13 entries. Validation: 12 of 13 valid in each tree; the single "invalid" in each is `docs/architecture.md`, which the validator's Python-only location set structurally cannot contain. I kept it deliberately — MR-12 changes the documented on-disk log-entry shape, and `docs/architecture.md`'s Logging section spells out the per-entry field list and the compound-sub-command special case by name, so a correct implementation has to touch it. Every private name I guessed from a test-class docstring validated as real: `_parse_compound_match_details` and `_log_allowed_command` in P1, `_handle_command_tool` and `_log_allowed_command` in P2.

### P1

| Location | Kind |
|---|---|
| `toolguard/log_writer.py::log_command` | record |
| `toolguard/hook.py::_log_allowed_command` | record |
| `toolguard/hook.py::_parse_compound_match_details` | parse_validate |
| `toolguard/hook.py::main` | decide |
| `toolguard/resolve.py::SubMatch` | record |
| `toolguard/resolve.py::BashResolution` | transport |
| `toolguard/resolve.py::resolve_bash_permission_detailed` | transport |
| `toolguard/compound.py::resolve_compound_permission_detailed` | transport |
| `docs/architecture.md` | display |
| `test/unit/test_hook.py::TestLogAllowedCommand` | test |
| `test/unit/test_hook.py::TestParseCompoundMatchDetails` | test |
| `test/unit/test_log_writer.py::TestLogging` | test |
| `test/unit/test_log_writer.py::TestLogFormatGoldenFile` | test |

### P2

| Location | Kind |
|---|---|
| `toolguard/log_writer.py::LogRecord` | record |
| `toolguard/log_writer.py::log_command` | record |
| `toolguard/config_types.py::UnitVerdict` | record |
| `toolguard/config_types.py::RuntimeVerdict` | transport |
| `toolguard/hook.py::_handle_command_tool` | decide |
| `toolguard/hook.py::_log_allowed_command` | record |
| `toolguard/resolve.py::resolve_bash_permission_detailed` | transport |
| `toolguard/compound.py::resolve_compound_permission_detailed` | transport |
| `docs/architecture.md` | display |
| `test/unit/test_log_writer.py::TestLogging` | test |
| `test/unit/test_log_writer.py::TestLogFormatGoldenFile` | test |
| `test/unit/test_hook.py::TestHandleCommandToolAuditWiring` | test |
| `test/unit/test_hook.py::TestLogAllowedCommand` | test |

The two sets are **not** identical and did not come out identical by accident. They overlap on four locations that both inventories genuinely describe the same way (`log_writer.py::log_command`, `hook.py::_log_allowed_command`, `resolve.py::resolve_bash_permission_detailed`, `compound.py::resolve_compound_permission_detailed`) plus the docs file and two shared test classes. They diverge on everything that carries the per-sub-command collection: in P1 that is `resolve.py::SubMatch` / `BashResolution` plus a reason-string parser in `hook.py`; in P2 it is `config_types.py::UnitVerdict` / `RuntimeVerdict` plus a typed `log_writer.py::LogRecord`, with no reason-parsing site to touch at all.

## Confidence

**P2: high.** The inventory hands the change to you. `log_writer.LogRecord` is described as "the fields of a single resolution-log entry, in one value" — a new field goes there and nowhere else. `config_types.UnitVerdict` is "per-sub-command resolution record inside a compound Bash permission check", and `config_types.RuntimeVerdict` is "the single runtime verdict type every governed-tool resolution returns", so the collection and its length are already first-class named things. `test_hook.py::TestHandleCommandToolAuditWiring` names the exact seam where a verdict becomes audit records. The only real uncertainty is whether position is *stamped onto* `UnitVerdict` or *derived by enumerate* at the write boundary — I predicted both ends, which is the honest way to be wrong by at most one entry.

**P1: medium.** The write path is locatable (`log_writer.log_command`, `hook._log_allowed_command`), but the collection's whereabouts is genuinely ambiguous from the inventory. `resolve.SubMatch` and `resolve.BashResolution` say the resolver models the set; `test_hook.py::TestParseCompoundMatchDetails` — "test parsing of compound match details from **reason strings**" — says the logging path does *not* consume that set and instead reconstructs it from prose. I could not tell from the inventory which of those two an implementer would actually extend, so I predicted both, and that is where P1's precision will suffer. There is also a real chance an implementer in P1 takes the cheap route (add `part`/`of` arguments to `log_command`, number them inside `_log_allowed_command`, and leave `resolve.py` alone), in which case my three `resolve.py` entries are all false positives.

**P2's inventory made the change substantially easier to locate**, and the reason is specific rather than aesthetic: P2 names the *values* (`LogRecord`, `UnitVerdict`, `RuntimeVerdict`), and MR-12 is a requirement about a value gaining a field. P1 names the *functions*, and functions do not tell you where a collection lives.

## Surprises, and one self-description that pointed me wrong

The genuine surprise was `test_hook.py::TestParseCompoundMatchDetails` in P1. A tree that already has `resolve.SubMatch` — an explicitly modelled per-sub-command record — should not also need to recover per-sub-command detail by parsing a reason string. Seeing both in one inventory is what told me P1 has two compound logging stories, not one. P2 confirms this was recognised as a defect rather than a taste question: `test/unit/test_architecture_fitness.py::TestFindReasonParsingSites` is a *fitness function that hunts for reason-parsing sites, with a sanctioned-site exclusion list*. You do not build a detector for a pattern you are happy with.

The self-description that pointed me wrong — or at least, that I had to actively distrust — is `docs/architecture.md` in the working repo. It states flatly that "compound entries do NOT get a separate Provenance field ... folded back into Matched Rule in the pre-R3 bracketed format". That is a confident, specific description of the P1 behaviour, and P2's `test_log_writer.py::TestProvenanceLogging` ("TOO-45 R3 follow-up: provenance is its OWN log field, **not folded back**") says it is stale for P2. If I had trusted the doc as describing both trees, I would have predicted P2's compound path as a bespoke string-formatting site rather than a typed record. Doc drift in the direction of the older architecture is exactly the failure mode a blind predictor is most exposed to.

A smaller one: P1's `toolguard/tools/decision.py` is 252 lines and defines `Decision` + `decide`; P2's is 38 lines and P2 has a separate `toolguard/api.py` whose sole export is `decide`. The public decision surface moved and thinned. It does not bear on MR-12, but it is the clearest single-number signal in the two inventories that P2 is the restructured tree.

## The lost-collection question: does each tree model the set of sub-results, or stream them?

**P1: it models the set, then throws it away and reconstitutes it from prose.** `resolve.SubMatch` and `resolve.BashResolution` are real, ordered, per-sub-command modelling — so at the resolver, the set exists and the total is knowable. But `hook._parse_compound_match_details` exists, and it exists precisely because the audit writer is downstream of a *string*, not of that set. So P1 has the worst of both: a modelled collection that the requirement's actual consumer cannot see, and a reconstructed collection that is only as complete as the reason text happens to be. I expect the denied-part clause of the acceptance criteria — "the total still reflecting every part that was evaluated" — to be the part that bites in P1, because a deny reason names the *deciding* sub-command; if the reason does not enumerate the parts that were allowed before the denial, the parse cannot produce a correct total and the implementer is forced to thread `BashResolution` into the hook after all. That is the "count the parts twice" outcome the question anticipates, and P1 is where I expect to see it.

**P2: it models the set, and the model reaches the writer.** `RuntimeVerdict` is a single verdict type carrying `UnitVerdict`s, `LogRecord` is a single log-entry value, and there is no reason-parsing test class left in `test_hook.py` — plus an active fitness check policing reason-parsing sites. The total is a `len()` on something the logging path already holds. In P2 this requirement should be close to mechanical.

## Reuse or parallel implementation of the compound logging path?

**P1: parallel, and documented as such.** `docs/architecture.md` does not merely describe a difference, it *specifies* one: compound sub-command entries get a different field set from single-command entries (no `Provenance`, provenance instead folded into `Matched Rule` in a bracketed format). That is not one path handling a list of length one and a list of length three; that is two renderers with two contracts. The reason-string parser is the seam between them. Consequence for MR-12 in P1: the "entries for a non-compound command are unchanged" clause is easy (different code path, untouched), but keeping the two shapes from drifting further is the cost.

**P2: substantially reused, though I would not claim fully converged.** `LogRecord` as a single value type, and `TestProvenanceLogging` asserting provenance is its own field rather than folded, both say the compound entry and the single entry are now the same record. What I cannot tell from the inventory is whether the *call site* is shared — whether `_handle_command_tool` emits one record for a simple command and N records for a compound through one loop, or still branches. I predicted `_handle_command_tool` and `_log_allowed_command` as separate entries to cover both readings. If P2 truly shares the loop, MR-12 there is a one-record-field change plus an `enumerate`, and my `compound.py` / `resolve.py` transport entries in P2 will be false positives — which would be a good outcome for the tree and a bad one for my precision.
