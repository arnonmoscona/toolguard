---
title: 102-here-strings-are-misparsed-as-heredocs
type: note
permalink: toolguard/too-45/proposed-tickets/102-here-strings-are-misparsed-as-heredocs
---

# 102 - `<<<` here-strings are misparsed as heredocs, corrupting the leaf and (under one config) evading deny

**Found 2026-08-21** by the ticket-98 chunk-2 implementer, while root-causing corpus diffs. **Pre-existing**: `_HEREDOC_RE` is unchanged since before chunk 1. Chunk 2 only changed *which stage* surfaces the consequence.

Measured by me against an extracted HEAD tree with `PYTHONPATH` pinned and the module path printed by the measuring run, because the working copy was being edited concurrently.

## What happens

`_HEREDOC_RE` matches the first two `<` of a `<<<` here-string and treats the rest as a heredoc redirection.

| command | leaf produced |
|---|---|
| `read -r x <<< "hello"` | `read -r x <__HEREDOC_TO_read__` |
| `for s in a b; do IFS="\|" read -r p q <<< "$s"; done` | `IFS="\|" read -r p q <__HEREDOC_TO_do__` |
| `bash <<< "rm -rf /tmp/zz"` | undecidable -- grammar rejects the residual `bash <` |

Three distinct damages, worth separating:

1. **A stray `<` is left in the leaf text.** The command toolguard matches rules against is not the command the user wrote.
2. **The sink is attributed to a shell keyword.** `__HEREDOC_TO_do__` -- `do` is not a command. Any sink-based reasoning downstream is being handed a keyword.
3. **The here-string's CONTENT is swallowed**, exactly as a heredoc body would be -- but a here-string's content is an argument, not a redirected document.

## It can move a decision, under one supported configuration

With `deny = ["Bash(rm:*)"]`:

| command | `undecidable_fallback` unset | `undecidable_fallback = "allow"` |
|---|---|---|
| `bash <<HD` / `rm -rf /tmp/zz` / `HD` | **deny** | **deny** |
| `bash <<< "rm -rf /tmp/zz"` | ask | **allow** |
| `rm -rf /tmp/zz` (control) | deny | deny |

**The heredoc form is caught and the here-string form is not.** A heredoc to a bash-family sink has its body spliced back in as source, so `rm -rf /tmp/zz` becomes its own matchable leaf. The here-string instead becomes undecidable, and `undecidable_fallback = "allow"` turns that into an allow.

Note the asymmetry is the interesting part: **toolguard already knows how to do this correctly for the heredoc spelling.**

## Exposure - measured, and it is essentially ZERO

| corpus | commands with `<<<` | feeding a shell |
|---|---|---|
| **featherhill** | **0** | **0** |
| toolguard | 2 | **0** |
| instagram | **0** | **0** |

And of toolguard's two, **one is a false positive** -- `grep -rln '^<<<<<<<'`, a merge-conflict-marker search, not a here-string at all. The other is `uv run python -m toolguard.hook <<< '{...}'`, a latency benchmark feeding JSON to the hook, which executes nothing.

**So the dangerous shape has zero occurrences in any corpus.**

## Disposition: FIX, but LOW priority -- and do not sell it as a security fix

Applying `.claude/rules/evidence-before-fixing.md` honestly, the two halves land differently:

- **The deny bypass** needs `bash <<< "..."` *and* `undecidable_fallback = "allow"`. Writing `bash <<<` to dodge a deny rule is **deliberate evasion**, which is explicitly outside this project's threat model. On its own this half is a **defer**.
- **The leaf corruption is accidentally reachable and silent.** Any here-string at all triggers it -- `read -r x <<< "$s"` is ordinary shell -- and the corrupted text is what every rule is matched against. Nobody would ever see this happen. That half meets the "zero occurrences + accidental reachability + silent failure = still a fix" bar.

So it earns a fix on the corruption, not on the bypass. Order it below anything with field evidence.

## Fix direction

`_HEREDOC_RE` must not match `<<<`. A negative lookahead for a third `<` is the obvious move and is a **regex in the pre-pass, not the PEG grammar** -- so the two-phase rule does not apply to that part. But check whether the grammar should also gain a `here_string` production so `bash <<< "x"` parses instead of going undecidable; **that part IS a `.peg` change and the two-phase rule applies to it.** Do not conflate the two in one commit.

Worth deciding explicitly: should a here-string feeding a bash-family sink have its content spliced in as source, the way a heredoc does? That would close the asymmetry above. It is the same question ticket 98 answered for heredocs, and the answer should probably match.
---

# DISPOSITION 2026-08-22 — NO EVIDENCE. Arnon to defer as a YouTrack ticket.

Arnon: *"#102 - sounds like something that should be fixed. Check for evidence in logs. If no evidence - then tell me and I'll defer as a new YouTrack ticket."*

**Checked. There is no evidence, and the raw count overstates it by 3x.**

| corpus | raw `<<<` hits | genuine here-strings |
|---|---|---|
| **featherhill** | 0 | **0** |
| toolguard | 3 | **1** |
| instagram | 0 | **0** |

Two of toolguard's three are **false positives**, which is why the count had to be read line by line rather than tallied:

1. `grep -rln '^<<<<<<<\|^>>>>>>>' toolguard/ test/` — searching for merge-conflict markers. Not a here-string at all.
2. `grep -E "^(FAIL|Ran|FAILED)|sub_command|<<<|gh issue|AssertionError"` — **my own grep pattern from the 2026-08-21 measurement session**, logged because toolguard governs this repo's agent. The self-inflation effect this campaign has now measured three times.

The single genuine here-string is `for i in 1 2 3 4 5; do /usr/bin/time -f "%e" uv run python -m toolguard.hook <<< '{"session_id":"lat",...}'` — a latency benchmark feeding **JSON on stdin** to the hook. It is data, not code; the process reads it as input and executes nothing from it. It does not exercise the dangerous path this ticket describes.

**So the shape that carries the defect — a here-string feeding a shell — has ZERO occurrences across all three corpora.**

The analysis in the body above still stands and is unchanged: the leaf corruption is real and silent, and the deny bypass is real but needs `bash <<< "..."` plus `undecidable_fallback = "allow"`. What the measurement settles is only the *priority*, and it settles it downward.

**No implementation was done. Nothing in this ticket is committed.**
