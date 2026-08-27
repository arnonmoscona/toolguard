---
title: CASES
type: note
permalink: toolguard/too-45/spikes/cases
---

# Shared test set — every spike must classify these identically

Each case: the command text, and the expected SINK for each heredoc (the command that receives it).
Sinks matter because a bash-family sink means the body is spliced back as shell; a foreign sink means
the body is dropped and the ASK floor is raised.

| # | command | expected sink(s) | why it is here |
|---|---|---|---|
| 1  | `python <<HD\nimport os\nHD` | python | baseline |
| 2  | `bash -c "true" && python <<HD\nimport os\nHD` | python | ticket 19 P2 — an earlier clause must not steal it |
| 3  | `bash -c "true" \|\| python <<HD\n...\nHD` | python | same, `\|\|` |
| 4  | `bash -c "true" ; python <<HD\n...\nHD` | python | same, `;` |
| 5  | `bash -c "true" & python <<HD\n...\nHD` | python | same, bare `&` — SHIPPED as a defect once |
| 6  | `python $(true; true) <<HD\n...\nHD` | python | a separator INSIDE `$(...)` must not split — SHIPPED as a defect once |
| 7  | `python $(which x && echo y) <<HD\n...\nHD` | python | same, `&&` inside `$(...)` |
| 8  | ``python `true; echo -` <<HD\n...\nHD`` | python | same, backticks |
| 9  | `python "$(true; true)" <<HD\n...\nHD` | python | quoted substitution — already correct today |
| 10 | `cat x \| python <<HD\n...\nHD` | python | genuine pipe data-flow: last segment wins |
| 11 | `bash <<HD\nls -la\nHD` | bash | bash-family sink, body spliced as shell |
| 12 | `bash <<A <<B\necho from-A\nA\necho from-B\nB` | bash, bash | ticket 19 P3 — two on one line, bodies in order |
| 13 | `python3 - <<'HD' 2>/dev/null \|\| true\nimport os\nHD` | python3 | real traffic; redirect + `\|\| true` after |
| 14 | `cat <<-HD\n\tindented\nHD` | cat | `<<-` tab-stripping form |
| 15 | `echo "it's" && cat <<HD\nbody\nHD` | cat | P4 — an escaped/embedded apostrophe earlier on the line |
| 16 | `python <<HD \| bash\nimport os\nHD` | python | ticket 92 — the heredoc belongs to python; the pipe governs stdout |

## What each spike must produce

A function `sinks(text) -> list[str]` returning the sink command name per heredoc, in source order.

## What is being judged

**Not** speed, and **not** line count. Arnon is judging **which is easier to reason about and to maintain**.
So: how many places encode "what a quote is", how many encode "what a statement boundary is", and how
obvious is it where to look when a case like #5 or #6 turns out wrong.

---

## READ THIS BEFORE COMPARING — what the spikes do NOT measure

**1. They test sink ATTRIBUTION, not sink NAMING.** Every case asks *which command receives this heredoc*. The shipped module spends most of its sink code on the next question — *is that command bash-family or foreign* — which involves unwrapping `uv run python`, tolerating `python3.13`-style version suffixes, and the `xargs`/wrapper rules. **None of the 16 cases exercise that layer**, so all three spikes will look cheaper than the real port. Judge them on the structure they impose, not on their size.

**2. Case 16 is a case the SHIPPED module gets wrong.** `python <<HD | bash` — the heredoc belongs to `python`; the pipe governs stdout. Today `_split_on_unquoted_pipe` takes the last segment and answers `bash`. It is proposed ticket 92. **A spike that passes case 16 is not matching current behaviour, it is fixing it** — which is a point in its favour, but means the corpus replay will show movement and each moved golden needs justifying.

**3. Case 15 is a known-open defect** (P4, escaped apostrophe) that the shipped module also fails. Same note applies.

**So the acceptance test for the real port is not "matches today".** It is: matches today *except* for cases 15 and 16, where it must differ in the direction these cases specify.

---

## Case 17 — added after the spikes were built, and it is the one that separated them

| # | command | expected sink |
|---|---|---|
| 17 | `if true; then cat <<HD\nbody\nHD\nfi` | `cat` |

**None of the original 16 distinguished the three designs — all passed all 16.** This one does, and it was found by spike B probing beyond the set during its own self-review.

| | answer | failure character |
|---|---|---|
| shipped `multiline.py` | `then` | wrong, silently |
| spike A | `then` | wrong, silently |
| spike B | `then` | wrong, silently |
| **spike C** | `<unresolved>` | **does not know, and says so** |

**A control-structure keyword on the heredoc's own line breaks attribution in every design that computes the sink from tokens.** Only the design that asks the parse tree can decline to answer, because the grammar either attributes the placeholder to a `simple_command` or it does not.

**This is the campaign's own defining failure mode** — a mechanism that fails open and says nothing — reproduced structurally by two of the three candidates.