---
title: The corpus-replay safety evidence is strongest exactly when it is emptiest,
  and it cannot corroborate an ASK
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/73-replay-evidence-is-strongest-when-it-is-emptiest
---

**PARTIALLY FIXED in `05f786d`.** Fixed at `toolguard/replay.py:241-242` and `toolguard/corpus.py:98-99,113-118`; still open: `replay.py` still has no examined-nothing guard, and `ReplayDiff` still cannot separate a decided case from an undecidable one.

# The safety argument for merging permission rules

**Found 2026-08-14. One RED test in the tree. Five findings, consolidated because they share one fix owner and one theme: what the replay evidence claims versus what it measured.**

`replay` re-runs historical decisions under a proposed config and reports what changed. `consolidate` and `redundancy` use it as **the safety gate on rule merges** — the evidence that a proposed merge broadens nothing. Everything below is about that evidence being weaker than it reads.

## 1 — An all-undecidable corpus produces the strongest-looking evidence

Measured: commands that do not parse (`git status |`, `$(`, `'unclosed`) resolve to **`ask` under both configs**, via the undecidable floor. They therefore land in the `unchanged` bucket and count as replayed. An empty command resolves to `deny`; a multiline heredoc to `ask`. Nothing is dropped — which is correct — but nothing is *distinguished* either.

**Ticket 51 measured 4.3% of real audit-log `Command` fields as unparseable** (1,783 of 41,442), heredocs hardest.

So `"corpus replay N entries, 0 broadened"` can carry **zero information**, and it is the same string a genuinely corroborating run produces. **Neither `ReplayDiff` nor the evidence string separates "decided" from "undecidable."**

## 1b — THE SAME DEFECT ONE LAYER UP: the harvester cannot say what it examined

**Added 2026-08-14 from `test_tools_corpus.py` (17 of 29 mutants surviving at HEAD, 59% blind, now 0 of 29). Two more RED tests.**

`harvest_corpus` returns a **bare `List[LogEntry]`** and nothing else. **Five unrelated reasons to harvest nothing all produce `[]`, byte-identically**: absent directories, present-but-empty ones, files not matching `toolguard-YYYY-MM-DD.md`, a file whose every section is unparseable, and a window excluding all data. Measured with warnings captured and stderr redirected: **no warning, no stderr, bare list.**

So `"corpus replay N entries, 0 broadened"` with **N = 0** is unfalsifiable, and the reason it is zero is unrecoverable. RED: `test_a_missing_source_directory_is_reported_on_some_channel` — deliberately accepting *any* channel (a warning, stderr, or a return richer than a list) rather than dictating the fix.

### `--max-age-days=-1` is accepted and silently empties the corpus

`maintenance.py:1150` declares it `type=int` with **no range check**, so a negative value reaches `harvest_corpus`, puts the floor **in the future**, and discards everything. The merge-safety argument is then made over an empty corpus. RED: `test_a_negative_window_is_rejected_rather_than_emptying_the_corpus`.

**This is the phase-4 backlog item `--max-age-days reaching harvest_corpus`, and its owner is now settled**: it is not reachable from `replay`, which receives an already-harvested corpus. It lives in `tools/corpus.py`.

### A filter that drops data unread — worth an explicit decision

There are **two** date filters, and they can disagree. The **file-name** filter drops an in-window entry that happens to live in an out-of-window file, **without reading it**; the **entry-timestamp** filter drops an out-of-window entry inside today's file. Both are now pinned with their own detector; queue row CS2 said both were invisible to the entire suite, which is confirmed.

Boundary now pinned: the floor is `today - N` **inclusive**, so `N=0` means today only and `N=1` spans two calendar dates.

### And the one test guarding the empty case could not fail

`test_missing_sources_yield_empty_corpus` asserted `[]` against a fixture that could not produce anything else — **no mutant of the 29 made it fail at any tier.** Replaced with a five-scenario version whose own fixture asserts the positive case in both shapes, so it is falsifiable and three mutants kill it.

Other mechanisms at zero detection here: a silent cap, a silent dedup, `claude_home` not forwarded, the root fallback ignoring `resolution.root`, UTC-to-local conversion dropped, an absent window quietly capped at 30 days, and status / `rule_text` / `log_file` / file-tool field damage. **The max fixture was 2 entries**, which is why a cap at 3 was invisible; it is now 80 entries with 40 exact cross-source duplicates, which also pins the documented absence of dedup (queue MI3 — anything in both sources is double-counted).

## 1c — THE CORPUS IS ALSO POISONED AT THE SOURCE, three ways

**Added 2026-08-14 from `test_tools_transcript_harvest.py` (21 of 42 mutants surviving at HEAD, 50% blind, now 3 of 42).**

- **REFUSED is inferred by a lowercased substring search over the tool's OUTPUT.** A command whose *output* happens to contain "tool use was rejected" is filed as user-declined — and that feeds `mining`'s `SIGNAL_DECLINED`. This is "prose is output, not a data structure" reaching the corpus from a **third** producer (queue MI1 names the conflation).
- **The reason text is silently truncated at 200 characters with no marker**, so a cut reason is indistinguishable from a short one downstream.
- **`agent` is the literal string `"subagent"`, discarding the subagent's name**, while `log_harvest.LogEntry.agent` documents *"'main' or a subagent's name"*. **One field, two meanings, in one merged corpus.**

And the same "nothing to say it harvested nothing" shape: four causes — empty directory, no `.jsonl`, unparseable JSON, valid JSON in a foreign schema — all return the identical `[]`, with `OSError` swallowed to `[]` as a fifth. **Eight separate silent drop points** with no accounting.

Three production branches had **zero** coverage, which is the telling detail: `_index_tool_results`' non-list `content` and falsy `tool_use_id`, and `harvest_transcript_file`'s non-list `content` — i.e. **string-content messages, the bulk of a real transcript, were never in any fixture.**

## 2 — The evidence string is computed from the input, not from the replay

`consolidate.py:412` and `:600` build `f"corpus replay {len(corpus)} entries, 0 broadened"` from **`len(corpus)`**, while the gate reads `diff.broadened_count`. Two variables, one claim — ticket 57's shape.

Benign **only** while `replay` provably never skips an entry, which was an accident and is now a test (`test_every_entry_is_replayed_including_ones_that_do_not_parse`). `diff.total_count` is the correct variable, and no consumer currently reads it.

## 3 — `_verdict_matches_status` cannot corroborate an ASK, and ASK is real traffic

`hook.py:946` writes `status="ask"`; `log_writer.py:262` uppercases it, so the daily log holds `**Status**: ASK`.

**`_verdict_matches_status` knows only EXECUTED and REFUSED.** An entry logged ASK whose replay decides *exactly* `ask` reports `matches_observed=False`. Anything computing a corroboration rate therefore **systematically under-counts**.

Measured on this repo's own August logs: **37,789 EXECUTED, 185 ASK, 96 REFUSED.**

**This is the RED test**: `TestVerdictCorroboration.test_an_ask_verdict_corroborates_an_ask_log_line`. Fix direction: add `STATUS_ASK` and corroborate `ask`; the existing REFUSED -> `{deny, ask}` conflation is then needed only for pre-ASK history.

## 4 — `classify_change` can never report a widening for an unknown verdict

`_STRICTNESS.get(verdict, 0)` defaults an unrecognised verdict to `allow`'s rank. Since `broadened` means "moved toward allow", **an unknown `verdict_a` can never produce `broadened`** — precisely the direction that would hide a widening.

Unreachable today (`RuntimeVerdict.decision` is only ever allow/ask/deny; all construction sites grepped), so it was **not** pinned — pinning it would enshrine a made-up input. It becomes live the moment a fourth verdict kind exists, which is why it is recorded rather than dropped.

## 5 — `replay_single` has no production caller

Grepped the whole tree (`.py`, `.md`, `.toml`): only `replay` is used, by `consolidate` and `redundancy`. So the `matches_observed` machinery — and finding 3 — is **latent**. Wire it into a tool or delete it; leaving a defect in unreachable code is the third option and the worst one.

## The test module was 73% blind

**8 of 11 mutants survived HEAD; 1 of 17 survives the repair.** 18 tests added.

The survivor list is the interesting part: engine attribution stripped from every verdict (`matched_rule`, `provenance`, `reason`, `tool`, `target` all removed — HEAD asserted only `.decision` strings); `extended_syntax` ignored in **both** functions; `replay_single`'s order reversed; its entry mis-bound to `corpus[0]`; `matches_observed` hardcoded `True`; `_verdict_matches_status` always `True`; multiline entries silently dropped.

Now proven by **object identity**: a spy replaces `decide`, and the test asserts `assertIs(returned[i], diff.diffs[j].decision_a)` — self-falsifying, because an inert patch yields real verdicts and the identity check fails.

**Anchored on behaviour, not implementation**: all four functions were reimplemented differently (ordered-list index, comprehensions plus `Counter`, dict dispatch) and the repaired suite passes unchanged against the rewrite.

**Two test names read backwards** and were fixed: `test_broadened_allow_to_deny_is_wrong_direction` asserted `classify_change("deny","allow")`, and `test_tightened_deny_to_ask` asserted `("ask","deny")`. The docstrings were correct; only the names lied.
