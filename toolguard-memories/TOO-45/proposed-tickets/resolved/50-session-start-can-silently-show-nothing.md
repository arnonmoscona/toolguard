---
title: Two ways the SessionStart hook silently shows the user nothing at all
tags:
- TOO-45
- proposed-ticket
permalink: toolguard/too-45/proposed-tickets/50-session-start-can-silently-show-nothing
---

**FIXED in `05f786d` (TOO-45 phase 2).** Both ways SessionStart could silently show nothing are fixed — see `toolguard/session_start.py:65,392`.

# The only recurring notification channel can go quiet without saying so

**Found 2026-08-13. Two RED tests are in the tree. Both defects contradict the module's own documentation.**

SessionStart is the user's **only recurring** notification channel — it is what nags every session until a conflict is resolved. Both defects below end with the user seeing nothing and having no way to know a check was skipped.

## Defect 1 — the checks are not independent, despite the docstring saying they are

`session_start.py`'s module docstring says *"Checks performed, independent of each other"*. In fact `main()` computes **all four detectors inside one `try`** and prints once at the end.

**Any detector that raises silently discards every other detector's findings.** An unresolved takeover conflict, a broken config file, a stale install — all withheld, because an unrelated check threw.

Measured: with a takeover conflict genuinely present and one detector raising, **stdout is empty**. stderr does report the exception, but stdout is the channel the user reads.

**Mutate toward the fix:** wrapping each detector in its own `try`/`except` makes the RED test pass. **At HEAD that same fix produced 0 failures** — the suite saw neither the defect nor its correction.

**RED test:** `test_session_start.TestMain.test_a_failing_checker_does_not_suppress_the_other_checks`.

## Defect 2 — valid-JSON-but-not-an-object silently disables the whole hook

`_parse_session_start_input` catches only `json.JSONDecodeError`. `[1,2,3]`, `"str"`, `5` and `null` all parse successfully and are **returned as-is**, contradicting the function's own docstring ("malformed input yields an empty dict").

Measured with an unresolved takeover conflict present: **stdout empty, `load_configuration` never called**, stderr shows `'list' object has no attribute 'get'`.

Green under a two-line `isinstance` fix.

**RED test:** `test_session_start.TestParseSessionStartInput.test_returns_empty_dict_on_valid_json_that_is_not_an_object` (4 subTests).

**This is the third site in the same family**, alongside proposed tickets 40 (`verify_config_text` accepts any JSON document) and 46 (`config_divergence` crashes on a top-level array). **The codebase assumes a parsed JSON document is a `dict` and checks it in only some places.** Worth one guard at the parse boundary rather than three separate `isinstance` patches.

## Related observation — "reports OK having examined nothing", measured four ways

Four different situations produce one indistinguishable answer:

```
clean dir, examined 1 empty file   -> None
log dir does not exist             -> None
log_dir is None                    -> None
1 real conflict, file unreadable   -> None
```

The last is `_count_conflict_entries`' bare `except: return 0`. **A permission-denied conflict log reads as "no conflicts" — forever**, because the nag is the only thing that would have surfaced it.

Ticket 29's family, now confirmed a sixth time. Not pinned: the correct behaviour (warn? report "unknown"?) is a product decision.

## What the suite could not see

Seven mechanisms had **zero detection** at HEAD, all measured: section ordering, `main()`'s cwd fallback, its exception report, its TTY guard, the unrecognized-fallback-value message, provenance rendering, and the shadow-status gate. Plus a shape-8 tautology comparing `f(a,b)` with `f(a,b,broken_files=())`.

**The working queue's `SST` section claimed the opposite of both**: *"No other vacuous-assertion shapes were found"* and *"Stale/false Given/When/Then flagged: None."* Both false, both reached by reading rather than measuring — the failure mode ticket 31 documents.

The module also had **no test asserting the complete user-visible message**, no test of section ordering, and no end-to-end test of the stale-install alert. All three now exist.