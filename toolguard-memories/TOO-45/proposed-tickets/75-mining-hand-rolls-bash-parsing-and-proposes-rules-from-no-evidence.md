---
title: Mining hand-rolls bash tokenization, buckets every disclosed command under
  "#", and proposes rules from evidence it never had
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/75-mining-hand-rolls-bash-parsing-and-proposes-rules-from-no-evidence
---

**PARTIALLY FIXED in `05f786d`.** (a) tokenization now goes through `extract_commands` (`toolguard/tools/mining.py:159-183`); still open: (b) `TG_INTENT=1 ls -la` still buckets under the literal key `TG_INTENT=1` — the same root cause as #77, which remains unfixed.

# The analyzer that proposes new permission rules

**Found 2026-08-14. Seven RED tests in the tree, every one proven falsifiable by mutating toward its fix with zero collateral breakage. 20 of 46 mutants survived HEAD (43% blind); 0 of 51 survive the repair. 12 -> 43 tests.**

Consolidated into one ticket: one module, one fix owner.

## 1 — `_command_key` hand-rolls bash tokenization, against the project's stated constraint

`CLAUDE.md` is unambiguous: *"All bash parsing goes through the PEG grammar — never hand-rolled Python… `toolguard/parser/bash_parser.peg` is the single source of truth."* `.claude/rules/bash-grammar.md` exists **because this has regressed before**.

`_command_key` does its own tokenization, and the measured consequences are worse than the principle suggests:

| input | `_command_key` | `extract_commands` |
|---|---|---|
| `"# INTENT: x\ngit status"` | **`#`** | `['git status']` |
| `"cd /tmp && rm -rf x"` | `cd` | `['cd /tmp', 'rm -rf x']` |
| `"TG_INTENT=1 uv run python x.py"` | `TG_INTENT=1` | — |

**Every disclosed command this project mandates lands in a single meaningless `#` bucket.** The disclosure rule `CLAUDE.md` devotes a whole section to — comment block plus `TG_INTENT=1` prefix — is precisely the shape that defeats the analyzer. Both of the two mandated forms key on the wrong token.

RED: `test_a_disclosure_comment_does_not_split_a_command_from_its_own_group`. Routing the key through `extract_commands` turns it green with zero collateral.

## 2 — A rule can be proposed from zero observations, indistinguishably

```
evaluate_added_allow_rule(config, 'Bash', '*',                 prov, [])            # empty corpus
evaluate_added_allow_rule(config, 'Bash', 'zzz-no-such-cmd:*', prov, <real corpus>) # admits nothing
```

**Byte-identical**: `newly_allowed=()`, `broadened_count=0`, `tightened_count=0`. The first is a **tool-wide grant evaluated against nothing**; the second is a harmless pattern evaluated against real data. The only differing field is `pattern`, which is echoed input, not measurement.

`AddRuleEffect` **carries no corpus size and no reach**, so no consumer can tell them apart. This is ticket 73's shape one layer down: the evidence is strongest when it is emptiest.

Separately measured: `decide(with_layer_allow_replaced(config, 'Bash', prov, set(), ['*']), 'Bash', 'rm -rf /')` returns **`allow`, `matched_rule='*'`** — so the widening is real, and no detector existed anywhere.

## 3 — MI3 confirmed end to end: one real event meets a two-observation threshold

Two `LogEntry` rows identical in `(timestamp, tool, command, status)` and differing only in `log_file` — **exactly what `harvest_corpus` concatenates from the log and the transcript** — produce `occurrences=2` and clear `min_occurrences=2`. `distinct_commands` has one element.

The threshold boundary itself is correct and inclusive (occ=2 survives min=2, dropped at min=3). The defect is upstream double-counting meeting a downstream threshold. A dedup on `(timestamp, tool, command, status)` in `mine_rule_candidates` turns the RED green with zero collateral.

## 4 — A `deny` is summarised away as `ask`, and the distribution is discarded

`mine_rule_candidates` builds a `Counter` of verdicts per cluster, then keeps **only `most_common(1)[0][0]`** and throws the rest away.

Measured: config denying `[regex]^rm -rf /$`; corpus of `rm -rf /`, `rm foo.txt`, `rm bar.txt`, all EXECUTED. Output is one group — `[allow-candidate] Bash rm x3 (now: ask)` — listing `rm -rf /`. **The deny is unrecoverable** from `CommandGroup` and from the rendered report; `observed_counts` holds statuses, not verdicts.

This is the **"prose is output, not a data structure"** rule in its exact form: the structure was computed and then discarded. RED: `test_a_currently_denied_command_is_not_summarised_away_as_ask`; strictest-verdict-wins turns it green.

## 5 — Safety-net verdicts are reported as evidence to add a rule

An **empty command** (deny via the fail-closed empty-extraction net, `matched_rule=None`) and an **unparseable command** (`'unclosed`, ask via the undecidable floor) are both reported as **allow-candidates**. "Add a rule for this" derived from a safety net rather than from a rule.

Ticket 51 measured **4.3% of real audit-log Command fields unparseable**, so this is live traffic, not a hypothetical.

**And mining an unparseable command prints a ~30-line PEG expected-token dump to stderr per entry** — on a real corpus, a wall of noise for 4.3% of rows.

## 6 — The renderer was almost entirely unpinned

**Nine of ten `render_mining_report` mutants survived HEAD.** The tests asserted `assertIn("allow-candidate: 1", out)` and `assertIn("whoami", out)`, so markdown could render as plain text, the command list could vanish, and the declined/denied labels could swap — all green.

Also at zero detection: all four sort-key mutants **including deleting the sort outright**, both `_SIGNAL_ORDER` mutants, `mine-verdict-least-common`, `mine-observed-counts-empty`, `eval-drops-allow-filter`, and `eval-locus-is-path`.

## Production observations

- **`evaluate_added_allow_rule` / `AddRuleEffect` have no production caller** — reachable only from tests, though TOO-15 specifies them. So defect 2 is latent, and the fix is cheap while it stays that way.
- `with_layer_allow_replaced` **correctly** preserves the layer's deny list and `no_match_fallback` — now pinned.

## Method notes worth carrying beyond this module

- **A `sys.modules` identity scan rebound the harness's own `original` variable**, making the restore anchor the mutant. It surfaced only as `AssertionError: mutant is not live`; **without the per-mutant liveness assertion it would have leaked mutants into later rounds and read as universal detection.** Fix: exclude `__main__` from the scan.
- **A name-only directory snapshot cannot see a REWRITE.** The agent's write-detection guard read NOT DETECTED until the snapshot included **size and mtime**.
- `follow-up-queue.md:1447` judged this file's only real defects to be "three deny-vs-ask Givens". That was a read-only pass; mutation found **20** blind mechanisms in the same file. **Eleventh confirmed instance** of the completeness failure mode.
