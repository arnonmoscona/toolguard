---
title: 'Danger analyzer: advertised detections that never fire, and two blanket allows
  it cannot see'
tags:
- TOO-45
- proposed-ticket
- security
permalink: toolguard/too-45/proposed-tickets/21-danger-analyzer-coverage-gaps
---

# Danger analyzer coverage gaps

`toolguard/tools/danger.py` is the detector behind `toolguard-audit`'s rule findings. It advertises six destructive categories and a blanket-allow check. **Four of the six never fire, and the two patterns that most completely disable governance produce no finding.**

Found during the TOO-45 #07 sweep by executing the module docstring's own claims. Full reproductions in `reports/follow-up-queue.md`, rows DG1–DG8.

## 1. Two complete governance bypasses produce no finding

```
_is_blanket_allow('Bash', '*',  NATIVE)  -> False
   match_pattern(NATIVE,  '*',  'rm -rf /')  -> True

_is_blanket_allow('Bash', '**', DEFAULT) -> False
   match_pattern(DEFAULT, '**', 'rm -rf /')  -> True
```

`Bash([native]*)` and `Bash(**)` each allow every command, and `_is_blanket_allow` recognises neither.

**The cause is not what a first reading suggests.** The GLOB branch exists (`danger.py:354`) and *does* treat `**` as blanket — `_is_blanket_allow('Bash','*',GLOB)` and `('Bash','**',GLOB)` both return `True`. The actual causes are:

- **`PatternType.NATIVE` is handled by no branch at all.**
- **DEFAULT `**` is absent from the DEFAULT branch's one-element list.**

(An earlier draft of this ticket blamed a missing GLOB branch. That would send the implementer to code that is already correct. `danger.py`'s own docstring states it correctly — *"`[native]*` and a DEFAULT `**` both permit everything and both return False here"*.)

### Six bypass forms, not two

End-to-end, `danger()` returns `[]` for all of these:

```
'[regex]^.*' -> []          '[glob]**/*' -> []
'[regex]^'   -> []          '[native]*'  -> []
'**'         -> []          '[regex].*'  -> [('blanket-allow-outside-takeover','CRITICAL')]
```

**`[regex]^.*` is the worst of the set.** It escapes `_is_blanket_allow` (whose REGEX branch is a five-element literal list: `.*`, `.+`, `^.*$`, `^.+$`, `''`) **and** `_is_unanchored_regex`, whose test is `startswith("^")`. So the MEDIUM backstop that would otherwise catch a loose regex allow is silenced by the very character that makes the pattern a complete bypass. Also missed: `^`, `.*$`, `(.*)`, `.*?`, `[\s\S]*` — every one of which `match_pattern(REGEX, body, 'rm -rf /')` returns `True` for.

This is why fix direction 2 (ask the matcher, do not enumerate forms) is the real fix: **no literal list will ever close the regex family.**

## 2. Four of six advertised destructive categories are dead

```
_is_destructive('Bash', <body>, DEFAULT):
  'rm -rf:*'  -> True     'rm -r:*'      -> False    'shred:*'  -> False
  'mkfs:*'    -> True     'rm -r *'      -> False    'shred *'  -> False
  'wipefs:*'  -> True     'rm -r /tmp/x' -> False    'dd if=*'  -> False
  'rm *'      -> False    'rm:*'         -> False    'format *' -> False
```

`_body_fnmatch_matches_any` appends its own `' '` / `':'` separator, so the table entries `'rm -r '`, `'shred '`, `'format '` are unreachable, and `'dd if='` is unreachable in the natural `dd if=*` form. The module docstring listed all six and added *"A wildcard that would match these is also flagged"* — no wildcard is flagged either.

`rm -r` deserves separate note: it is `rm -rf` minus one character, it is equally destructive, and it is not detected.

## 3. `uv run python3` escapes while `uv run python` is caught

```
_is_arbitrary_exec('Bash', 'uv run python:*',            DEFAULT) -> True
_is_arbitrary_exec('Bash', 'uv run python3:*',           DEFAULT) -> False
_is_arbitrary_exec('Bash', 'uv run python3 -m unittest:*', DEFAULT) -> False
```

`uv run python3` is a form Claude Code emits. Seven of the eleven entries in `_ARBITRARY_EXEC_PREFIXES` are dead by the same separator mechanism — e.g. the `"python:"` entry carries the comment *"handle toolguard pattern form python:\*"*, and `_body_fnmatch_matches_any('python:*', ('python:',))` returns `False`. That entry handles nothing; the bare-name loop does the work.

## 4. A prefix word or absolute path escapes both command detectors

```
'sudo rm -rf *'      -> False      '/bin/rm -rf *'       -> False
'sudo python:*'      -> False      '/usr/bin/python3:*'  -> False
```

Same shape as the `self_integrity` hard-deny gap: any prefix token defeats the match.

## 5. Two rationale strings over-claim

Left unedited under the sweep's comments-only rule, so they now contradict the corrected docstrings above them:

- The arbitrary-exec template names `exec`, although the REGEX branch **deliberately excludes** it via negative lookaheads.
- The destructive template names `shred` and `dd`, which per §2 never fire in DEFAULT or GLOB.

## 6. Dead code adjacent to the above

- `ignored_extracted` is computed in `danger()` under the comment *"for blanket-allow check"* and **never read** in `_audit_tool`.
- **The takeover skip in `_audit_tool` is dead on the default path.** `permission_layers` already drops ignored-allow patterns from native layers upstream. Verified with takeover on and `ignored_allow_patterns = ['Bash(*)']`: the native layer's `lr.allow` came back `('rm -rf:*',)` — `Bash(*)` already removed — and `neutralized_by_takeover` returned `False` for every surviving pattern in every layer. It can only fire when a caller passes a `takeover` that disagrees with the config's, which `security_audit` does not do. **No test covers the divergent case.**

## Fix direction

1. **`_is_blanket_allow` first** (§1) — it is the highest-severity gap and the smallest fix. Add the GLOB branch and treat `**` as blanket.
2. **Replace the prefix tables with matcher-based detection** (§2, §3, §4). The tables encode a model of matching that `permissions.match_command` does not share, which is why entries silently die. Ask the matcher whether a candidate dangerous command would be allowed by the pattern, rather than string-matching the pattern body.
3. **Derive the rationale strings from what actually fired** (§5) — prose is output; carry the structured detection result and render at the edge.

## Test obligation

**A coverage test that asserts every entry in `_ARBITRARY_EXEC_PREFIXES` and the destructive table is reachable.** Seven dead entries in one table and four dead categories in another is not a subtle failure — it is the absence of any test that a table row can fire. That test is cheap and would have caught all of §2 and §3. (Counted two ways: 7 of 11 exec entries cannot match their own natural `<entry>*` form; **8 of 11 change no result at all** if deleted. Only `uv run python`, `sh -c` and `bash -c` do any work — and `sh -c:`/`bash -c:` are redundant with the un-colonned entries rather than with the bare-name loop, so their fix differs.)

**An existing test passes vacuously and must be replaced, not kept.** `test_native_blanket_allow_not_flagged_when_takeover_on` (`test/unit/test_tools_danger.py:460`) asserts `danger()` produces no blanket finding for `Bash(*)` — but `Bash(*)` never reaches `danger()`, because `config.permission_layers` strips it upstream. **Deleting the entire `neutralized_by_takeover` guard from `_audit_tool` leaves that test green.** Second instance in this file of "no test proves this code can fire".

## Interaction with the other tickets

Ticket 18 (`match_command` over-matches multi-token DEFAULT prefixes) is upstream of fix direction 2 — a matcher-based detector inherits the matcher's defects. **Fix 18 first.** Tickets 17, 19 and 20 are independent of this one.