---
title: TOO-45 punch-list 2026-08-22
type: note
permalink: toolguard/too-45/too-45-punch-list-2026-08-22
---

# TOO-45 punch list — 2026-08-22, approved by Arnon

Every item spelled out inline. Do not replace an item with a pointer to another file.

## Approved, in Arnon's words

> * I accept your proposal. Do the writeup on compound.py and we'll see what we do from there (#103)
> * #100 - fix
> * #101 - fix only if you find concrete evidence in the toolguard logs. Looks like a very unlikely corner case
> * #102 - sounds like something that should be fixed. Check for evidence in logs. If no evidence - then tell me and I'll defer as a new YouTrack ticket
> * #104 - fix
> * #105 - fix

## The two evidence-gated items — MEASURED 2026-08-22, both resolved

**#101 — EVIDENCE FOUND, so it is a FIX.** 13 raw bare-`{}` commands in `logs/`; 4 are this campaign's own scratchpad probes; **9 genuine**, spread over 2026-08-01 to 2026-08-21. Ordinary idiom: `xargs -I{}`, `find -exec ... {}`. **One logged a real ASK**; the other 8 were allowed by `[fallback allow -- no rule matched]`. That silence is an artifact of this repo's `no_match_fallback = "allow_with_no_warnings"`, marked TEMPORARY pending TOO-28 — under the shipped default (`ask`) every one prompts. Sandbox confirms current behaviour: *"Undecidable segment (command did not parse; cannot safely decompose)"*. **Not a regression**: bare `{}` failed to parse at `f11ba43` (pre-98) too.

**#102 — NO EVIDENCE. Report to Arnon; he defers as a YouTrack ticket.** featherhill **0**, instagram **0**, toolguard **3 raw of which 2 are false positives** — `grep -rln '^<<<<<<<'` (merge-conflict markers) and a grep pattern from my own 2026-08-21 measurement. The one genuine here-string is `uv run python -m toolguard.hook <<< '{...}'`, a latency benchmark feeding JSON — data, not code, and not the dangerous shape. **Do NOT implement.**

## Work items

- [ ] **#100 — delete two orphaned module-private functions.** `_resolve_leaf` (`compound.py:808`, ~30 test call sites, zero production callers) and `_discover_rules_files` (`config.py:398`, superseded by `_discover_rules_files_multi` 43 lines below). Bounded at exactly 2 of 383 module-private functions, measured by AST sweep. Repoint `_resolve_leaf`'s tests at `resolve_compound_permission_detailed` so they exercise the path production actually runs, combining step included. Also add `architecture_fitness.py --orphans` — a STRONG check, since the leading underscore is the declaration it tests against; report rather than fail, and state the dispatch-table/`getattr` blind spots up front.
- [ ] **#104 — dicts are undeclared types.** `parse_hook_input()` returns `Dict[str, Any]` and belongs to the contract seam, not `hook.py`; return `PreToolUseEvent`, which already exists and which `testing/sandbox.py` already uses for the inverse direction. That removes the 8 `hook_data[...]`/`.get()` sites and the 6 surviving contract KEY imports. This IS ticket 99 item 2, folded in. Then add `architecture_fitness.py --undeclared-types`: flag public functions returning a bare dict across a module boundary. Exemptions stated up front — `to_json_dict()` and parsed TOML tables. Literals measured: `"log_dir"` 10 sites, `"extended_syntax"` 4 sites.
- [ ] **#105 — delete `_strip_comments`.** MEASURED: the grammar already has a `comment` production (`bash_parser.peg:67`) and correctly distinguishes a quoted `#` from a real one; it also already drops whole-line comments. What it does not do is trim a TRAILING comment out of the leaf's TEXT, which is what rules match against. So the hand-rolled scanner compensates for the EXTRACTOR, not for the grammar. Fix in `command_extractor.py` by excluding `comment` nodes when rebuilding leaf text, then delete `_strip_comments`. **Extractor work, not grammar work — the two-phase rule does NOT apply.** Removes the third hand-rolled quote model from `multiline.py`. Companion: a technical note on `multiline.py`'s flow (Arnon accepted drift risk explicitly).
- [ ] **#101 — grammar must accept a bare `{}` word.** **TWO-PHASE, MANDATORY** per `.claude/rules/bash-grammar.md`: phase 1 is `bash_parser.peg` + canopy regeneration, reviewed ALONE; phase 2 is any Python. Do NOT special-case `{}` in `command_extractor.py`. Check at the same time whether other unquoted punctuation words are missing — `+` alone parses, so the gap may be narrow.
- [ ] **#103 — compound.py concept map.** NOT a flow doc. One page naming the four concepts that look interleaved — structure, decidability, policy, combination — and which type owns each. **The map is a DIAGNOSTIC**: if it is easy to write, the abstraction exists and only the code obscures it, so ship the map and stop. If it is hard to write, that difficulty IS the refactor spec. Run AFTER #100, which changes `compound.py`.
- [ ] **#102 — REPORT ONLY, no code.** Tell Arnon there is no evidence so he can file the YouTrack deferral.

## Ordering and conflicts

**Parallel now** (disjoint files): #100 (`compound.py`, `config.py`, tests) · #104 (`hook.py`, `claude_code_contract.py`, `architecture_fitness.py`) · #105 (`command_extractor.py`, `multiline.py`, docs).
**Then** #101 (grammar) after #105 lands — both can reach the parse path.
**Then** #103 after #100 lands — it reads `compound.py`.

## Standing requirements for every item

Pre-register a touch-set estimate BEFORE implementing, score it AFTER, into `reports/surprise/`. Gates: full suite (baseline **3990 OK**, expected failures=4), `corpus_build.py --verify` **OK: no differences**, `ruff format`/`check`, `architecture_fitness.py --stdlib --ambient --layers`. Mutation-verify anything with logic. Concurrent agents: scope `ruff format` to your own files, never repo-wide.
---

# PROGRESS 2026-08-22 — 5 of 7 items resolved, 1 running, 1 awaiting Arnon

| item | state | commit |
|---|---|---|
| **#100** delete two orphans + `--orphans` | **DONE** | `b63257c`, `e32d3da` |
| **#104** parse_hook_input returns a type + `--undeclared-types` | **DONE** | `61ecd7b`, `e32d3da` |
| **#103** compound.py concept map | **DONE** | artifact `reports/103-compound-concept-map.md`; follow-up filed as **#106** at Arnon's request |
| **#105** doc half | **DONE** | `da09faa` |
| **#105** code half | **RE-SCOPED by Arnon** — premise refuted, now grammar work; queued behind #101 | — |
| **#101** grammar accepts a bare `{}` | **RUNNING** — phase 1 (.peg + canopy regen) only | — |
| **#102** here-strings | **NO EVIDENCE, reported** — Arnon to defer as a YouTrack ticket | — |

Suite **4000 OK** (expected failures=4), corpus verify clean, ruff clean, `--stdlib --ambient --layers --orphans --undeclared-types` all pass.

## Findings worth carrying out of this batch

1. **#100's fix validated its own thesis.** Repointing the tests exposed drift the two shapes had been hiding: the single-unit path carries a real `fallback_kind`/`fallback_warning` where the deleted wrapper left defaults, **and no test asserted on either field** — which is why it survived.
2. **#105's premise was mine and it was false.** The grammar never recognises a trailing comment; `_strip_comments` is load-bearing. Arnon suspected exactly this and I told him otherwise. Now re-scoped to fix it at the source.
3. **Cause `S` fired twice** (99 and 104) — predicting a number that required violating a constraint I wrote myself. The fix from the first instance was recorded in a per-ticket scoring file and never fired. **Both lessons are now in auto-memory instead**, which is the actual correction.
4. **`--undeclared-types` reports 4 findings** — `config.load_config_file`, `config.config_sync_settings_from_sources`, `rule_sort.parse_permissions_section_with_comments`, `subagent.identify_current_agent`. **None fixed; that is Arnon's call, not a subagent's.**

## Still owed before any push

Coverage · `pyscn analyze` · **`/documentation-review`** (user-invoked; `docs/` gained `multiline-parsing-flow.md` and diagrams) · the push · then `uv tool upgrade toolguard` **plus the smoke test**, since a hook that cannot launch fails silently.

---

# FINDING 2026-08-22 — a grammar change's blast radius is INVISIBLE to the corpus

Caught during ticket 101, before commit. Recording it as a standing rule for every future `.peg` change, because the mechanism will recur.

**What happened.** The first attempt at accepting a bare `{}` removed `{` and `}` from the grammar's `delimiter` character class. All four target cases parsed. It also, silently:

- **opened a deny bypass**: `{ rm -rf /tmp/zz; }` went **deny -> allow**, because `word` began consuming `{`, so the inner command stopped being its own leaf and the command word became `{`. `Bash(rm:*)` cannot match `{ rm -rf /tmp/zz`.
- changed brace **expansion** — `echo a{b,c}d` went from `ParseError` to parsing. Nobody asked for that.

**Why the gates would not have caught it.** The corpus has no brace-group commands, so `corpus_build.py --verify` comes back clean while a construct is broken. **This is the third measured instance of the same blind spot**, after ticket 18's replay null and ticket 98 chunk 2 correcting three defects with zero corpus movement.

**And the `.peg` comment justifying the change was FALSE**: *"brace_group matches them as literals at the pipeline_element position, never through word/delimiter."* Once `{` is not a delimiter, `word` consumes it first. Measured, not argued — which is the only way this class of claim can be settled.

## The rules this establishes

1. **Never widen a shared character class to admit one token.** `delimiter` is consumed by every word in the grammar; editing it is a change to every production that touches words. Prefer an explicit alternative at the specific position.
2. **Diff a grammar change construct-by-construct against the previous commit**, with `PYTHONPATH` pinned to each tree and provenance printed by the measuring run. Not against the corpus, which cannot see what it does not contain.
3. **`test/unit/test_deny_penetrates_constructs.py` is now the standing guard** — 17 constructs, one subTest each, plus a benign-control test so it cannot pass by denying everything. Any `.peg` change must keep it green. Measured against `e32d3da`: all 17 denied correctly, so the surface was sound before today.
